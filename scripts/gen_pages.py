#!/usr/bin/env python3
"""駅ごとの商圏ページ(静的HTML)を生成する。

使い方:
  python3 scripts/gen_pages.py --sample     # 上位5駅だけ生成(レビュー用)
  python3 scripts/gen_pages.py --top 2000   # 乗降客数上位2000駅を生成

出力: web/pages/eki/{slug}/index.html と web/pages/eki/sitemap.txt
slug: 駅名(同名衝突は乗降客数順に -2, -3 を付与)
"""
import argparse
import datetime
import hashlib
import json
import math
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from distinct import (corpus_stats, features_en, features_ja,  # noqa: E402
                      is_distinctive, title_suffix_en, title_suffix_ja)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"
OUT = ROOT / "web" / "pages" / "eki"
EN_OUT = ROOT / "web" / "en" / "eki"
# lastmod台帳: url -> {h: 本文ハッシュ, d: 最終更新日}。本文が変わった日だけ日付を進める
# (全ページに毎回ビルド日を打つとlastmodが嘘になり、クロール優先度の判断材料として無価値になる)
MANIFEST = Path(__file__).resolve().parent / "lastmod.json"
SITE = "https://shoken-maker.vercel.app"
# S4需要計器(scheme_funnel.md): 個別分析の事前登録フォーム。裏のサービスは未実装=純粋な需要温度計
# 日英で別フォーム=セグメント別のS4信号(実験01b)
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSeD1Kkc6iHgvICicMsXude3PE27iuOfWPCvRTtfJeHEr2S9JA/viewform"
EN_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSeKpROMSuAETstOQ4To5JsIJ17XZnFKTP0l522PrBbISxDLSg/viewform"
# 日本語slug→ローマ字slug(build_en_slugs.pyで検証付き生成。手書き200＋Wikidata機械層)
EN_SLUGS: dict[str, str] = json.loads((Path(__file__).resolve().parent / "en_slugs.json").read_text())
# 機械層の表示名(Wikidataの英語ラベル由来)。手書き層はここに無く、slugからの復元にフォールバックする
# =公開済み200枚の見出し文字列を変えないための切り分け
EN_NAMES: dict[str, str] = json.loads((Path(__file__).resolve().parent / "en_names.json").read_text())

# Vercel Web Analytics。生成ページにも入れる: これが無いと駅ページの流入も
# 実験01bのAI referral(chatgpt.com/perplexity.ai)も観測できない。本番ホストでのみ発火。
ANALYTICS = """<script>
if (/\\.vercel\\.app$/.test(location.hostname)) {
  var s = document.createElement("script");
  s.defer = true;
  s.src = "/_vercel/insights/script.js";
  document.head.appendChild(s);
}
</script>"""

DLAT = 15 / 3600
DLON = 22.5 / 3600
N_BANDS = 20
BAND_LABELS = ["0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39",
               "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70-74",
               "75-79", "80-84", "85-89", "90-94", "95+"]
RADII = [500, 1000, 3000]

_mesh_cache: dict[str, list] = {}


def mesh_centroid(code: str) -> tuple[float, float]:
    p, q = int(code[:2]), int(code[2:4])
    a, b, c, d, m = (int(x) for x in code[4:9])
    lat = p / 1.5 + a * (5 / 60) + c * (1 / 120)
    lon = 100 + q + b * (7.5 / 60) + d * (1 / 80)
    if m in (3, 4):
        lat += DLAT
    if m in (2, 4):
        lon += DLON
    return lat + DLAT / 2, lon + DLON / 2


def load_mesh(code1: str):
    if code1 not in _mesh_cache:
        f = DATA / f"{code1}.json"
        if not f.exists():
            _mesh_cache[code1] = []
        else:
            rows = json.loads(f.read_text())
            _mesh_cache[code1] = [(*mesh_centroid(r[0]), r[1:]) for r in rows]
    return _mesh_cache[code1]


def aggregate(clat: float, clon: float, r: float) -> dict:
    margin = 400
    dlat_r = (r + margin) / 110946
    dlon_r = (r + margin) / (111320 * math.cos(math.radians(clat)))
    cells = []
    for p in range(int((clat - dlat_r) * 1.5), int((clat + dlat_r) * 1.5) + 1):
        for q in range(int(clon - dlon_r) - 100, int(clon + dlon_r) - 100 + 1):
            cells += load_mesh(f"{p}{q:02d}")
    kx = 111320 * math.cos(math.radians(clat))
    ky = 110946
    r2 = r * r
    nv = 5 + 2 * N_BANDS
    s = [0.0] * nv
    age_num = age_den = 0.0
    lat_lo, lat_hi = clat - dlat_r, clat + dlat_r
    lon_lo, lon_hi = clon - dlon_r, clon + dlon_r
    for la, lo, v in cells:
        if not (lat_lo <= la <= lat_hi and lon_lo <= lo <= lon_hi):
            continue
        inside = 0
        for sy in (-DLAT / 4, DLAT / 4):
            for sx in (-DLON / 4, DLON / 4):
                dx = (lo + sx - clon) * kx
                dy = (la + sy - clat) * ky
                if dx * dx + dy * dy <= r2:
                    inside += 1
        if not inside:
            continue
        w = inside / 4
        for i in range(nv):
            if i != 4 and v[i] is not None:
                s[i] += v[i] * w
        if v[4] is not None and v[0] is not None:
            age_num += v[4] * v[0] * w
            age_den += v[0] * w
    bands = [(round(s[5 + 2 * i]), round(s[6 + 2 * i])) for i in range(N_BANDS)]
    return {
        "pop": round(s[0]), "male": round(s[1]), "female": round(s[2]), "hh": round(s[3]),
        "mean_age": age_num / age_den if age_den else None,
        "bands": bands,
    }


def en_name(en_slug: str) -> str:
    if en_slug in EN_NAMES:
        return EN_NAMES[en_slug]
    base = en_slug.rsplit("-", 1)[0] if en_slug.rsplit("-", 1)[-1].isdigit() else en_slug
    return "-".join(w.capitalize() for w in base.split("-"))


def hreflang(slug: str, en_slug: str) -> str:
    return (f'<link rel="alternate" hreflang="ja" href="{SITE}/pages/eki/{quote(slug)}/">\n'
            f'<link rel="alternate" hreflang="en" href="{SITE}/en/eki/{en_slug}/">\n'
            f'<link rel="alternate" hreflang="x-default" href="{SITE}/pages/eki/{quote(slug)}/">')


def pyramid_svg(bands, pop, aria="人口ピラミッド") -> str:
    if pop <= 0:
        return ""
    mx = max(max(m, f) for m, f in bands) or 1
    rows = []
    bar_h, gap, half_w, lbl_w = 10, 2, 150, 46
    hgt = N_BANDS * (bar_h + gap)
    for i, (m, f) in enumerate(reversed(bands)):
        y = i * (bar_h + gap)
        wm = m / mx * half_w
        wf = f / mx * half_w
        lbl = BAND_LABELS[N_BANDS - 1 - i]
        rows.append(
            f'<rect x="{half_w - wm:.1f}" y="{y}" width="{wm:.1f}" height="{bar_h}" rx="3" fill="#2a78d6"/>'
            f'<rect x="{half_w + lbl_w:.0f}" y="{y}" width="{wf:.1f}" height="{bar_h}" rx="3" fill="#eb6834"/>'
            f'<text x="{half_w + lbl_w / 2:.0f}" y="{y + bar_h - 1}" text-anchor="middle" font-size="8.5" fill="#898781">{lbl}</text>'
        )
    return (f'<svg viewBox="0 0 {2 * half_w + lbl_w} {hgt}" xmlns="http://www.w3.org/2000/svg" '
            f'role="img" aria-label="{aria}">{"".join(rows)}</svg>')


def fmt(n) -> str:
    return f"{n:,}"


def band_sum(bands, lo, hi) -> int:
    return sum(m + f for m, f in bands[lo:hi + 1])


def render(st, slug: str, aggs: dict, nearby: list, en_slug: str | None = None,
           feats: list[str] | None = None, tsuffix: str = "",
           ambiguous: bool = False) -> str:
    name = st["n"]
    lines = "・".join(st["l"][:4]) + ("ほか" if len(st["l"]) > 4 else "")
    a1 = aggs[1000]
    senior = band_sum(a1["bands"], 13, 19)
    senior_pct = senior / a1["pop"] * 100 if a1["pop"] else 0
    pax = f'1日あたりの乗降客数は約{fmt(st["p"])}人（2023年度・国土数値情報）。' if st.get("p") else ""
    mean_age = f'{a1["mean_age"]:.1f}歳' if a1["mean_age"] else "—"

    rows = "".join(
        f'<tr><td>半径{r/1000:g}km</td><td>{fmt(a["pop"])}人</td><td>{fmt(a["hh"])}世帯</td>'
        f'<td>{a["mean_age"]:.1f}歳</td></tr>' if a["mean_age"] else
        f'<tr><td>半径{r/1000:g}km</td><td>{fmt(a["pop"])}人</td><td>{fmt(a["hh"])}世帯</td><td>—</td></tr>'
        for r, a in aggs.items()
    )
    near_links = "".join(
        f'<li><a href="../{nslug}/">{nst["n"]}駅の商圏人口</a>（約{dist:.1f}km）</li>'
        for nst, nslug, dist in nearby
    )
    tool = f'{SITE}/?lat={st["la"]}&lng={st["lo"]}&r=1000'
    # 特徴文はコーパス全体からしか出ない情報なので、要約(description)にも先頭1本を回す
    feats = feats or []
    feat_html = ("".join(f"<li>{x}</li>" for x in feats[1:])
                 if len(feats) > 1 else "")
    feat_block = (f'<h2>全国の駅の中での位置づけ</h2>\n<ul>{feat_html}</ul>'
                  if feat_html else "")
    lead = feats[0] if feats else ""
    # タイトル: 特徴が立つ駅は半径の羅列より特徴を出す(同型タイトルの解消)。
    # 同名駅(京橋・大久保・県庁前など)は路線名で区別する。これを入れないと
    # 別の駅のページが完全に同じタイトルになり、重複ページとして扱われる
    disamb = f"（{st['l'][0]}）" if ambiguous and st.get("l") else ""
    title = (f"{name}駅{disamb}の商圏人口・年齢構成{tsuffix} | 商圏メーカー" if tsuffix else
             f"{name}駅{disamb}の商圏人口・年齢構成（半径500m/1km/3km）| 商圏メーカー")
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{name}駅（{lines}）の商圏人口: 半径1km圏の常住人口は約{fmt(a1['pop'])}人・{fmt(a1['hh'])}世帯、平均年齢{mean_age}。{feats[1] if len(feats) > 1 else ''}2020年国勢調査500mメッシュによる無料の商圏分析。">
<link rel="canonical" href="{SITE}/pages/eki/{slug}/">
{hreflang(slug, en_slug) if en_slug else ""}
<style>
body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#0b0b0b;background:#fcfcfb;max-width:720px;margin:0 auto;padding:20px 16px;line-height:1.7}}
h1{{font-size:22px}}h2{{font-size:16px;margin-top:28px}}
table{{border-collapse:collapse;width:100%;font-size:14px}}
td,th{{border-bottom:1px solid #e1e0d9;padding:8px 10px;text-align:right}}
td:first-child,th:first-child{{text-align:left}}
.cta{{display:inline-block;background:#2a78d6;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;margin:14px 0}}
.muted{{color:#898781;font-size:12px}}
svg{{max-width:380px;width:100%}}
ul{{padding-left:20px}}
</style>
</head>
<body>
<p class="muted"><a href="{SITE}/">商圏メーカー</a> › {name}駅</p>
<h1>{name}駅の商圏人口・年齢構成</h1>
<p>{name}駅（{lines}）周辺の常住人口を2020年国勢調査の500mメッシュ統計から集計しました。{pax}
半径1km圏の人口は<strong>約{fmt(a1["pop"])}人・{fmt(a1["hh"])}世帯</strong>、平均年齢は{mean_age}、
65歳以上の比率は{senior_pct:.1f}%です。{lead}</p>
<a class="cta" href="{tool}">地図で円を動かして詳しく見る →</a>
{feat_block}
<h2>半径別の商圏規模</h2>
<table>
<tr><th>範囲</th><th>常住人口</th><th>世帯数</th><th>平均年齢</th></tr>
{rows}
</table>
<h2>人口ピラミッド（半径1km・5歳階級）</h2>
{pyramid_svg(a1["bands"], a1["pop"])}
<p class="muted">左=男性・右=女性。2020年国勢調査は都心部で年齢不詳率が高く、内訳合計は総数に一致しない場合があります。</p>
<h2>近くの駅</h2>
<ul>{near_links}</ul>
<div style="border:1px solid #e1e0d9;border-radius:10px;padding:14px 16px;margin:24px 0;background:#fff">
<p style="margin:0 0 6px"><strong>📋 {name}駅周辺での出店を検討中ですか？</strong></p>
<p style="margin:0 0 10px;font-size:14px">業種・計画に合わせた個別の商圏分析レポートを準備中です。ご興味のある方は事前登録へ（無料・約1分）。</p>
<a class="cta" style="margin:0" href="{FORM_URL}">個別分析の事前登録 →</a>
</div>
<p class="muted">出典: 総務省統計局「令和2年国勢調査」500mメッシュ（e-Stat 統計GIS）・国土数値情報 駅別乗降客数(S12)を加工して作成。
数値は常住（夜間）人口の概算です。<a href="https://github.com/hatsu-kawabata/shoken-maker">オープンソース(MIT)</a></p>
{ANALYTICS}
</body>
</html>"""


def render_en(st, slug: str, en_slug: str, aggs: dict, nearby_en: list,
              feats: list[str] | None = None, tsuffix: str = "",
              ambiguous: bool = False) -> str:
    name = en_name(en_slug)
    a1 = aggs[1000]
    senior = band_sum(a1["bands"], 13, 19)
    senior_pct = senior / a1["pop"] * 100 if a1["pop"] else 0
    pax = (f' About {fmt(st["p"])} passengers use the station daily (FY2023, MLIT).'
           if st.get("p") else "")
    mean_age = f'{a1["mean_age"]:.1f}' if a1["mean_age"] else "—"

    rows = "".join(
        f'<tr><td>{r/1000:g} km radius</td><td>{fmt(a["pop"])}</td><td>{fmt(a["hh"])}</td>'
        + (f'<td>{a["mean_age"]:.1f}</td></tr>' if a["mean_age"] else "<td>—</td></tr>")
        for r, a in aggs.items()
    )
    near_links = "".join(
        f'<li><a href="../{nslug}/">{en_name(nslug)} Station demographics</a> ({dist:.1f} km away)</li>'
        for nslug, dist in nearby_en
    )
    tool = f'{SITE}/?lat={st["la"]}&lng={st["lo"]}&r=1000'
    feats = feats or []
    feat_html = ("".join(f"<li>{x}</li>" for x in feats[1:])
                 if len(feats) > 1 else "")
    feat_block = (f'<h2>How this station compares nationwide</h2>\n<ul>{feat_html}</ul>'
                  if feat_html else "")
    lead = f" {feats[0]}" if feats else ""
    # 同名駅(Okubo・Kyobashi など)の区別。日本語面は路線名で分けるが、英語の読者に
    # 日本語の路線名を出しても手がかりにならないので、1km圏人口という読める量で分ける
    if not tsuffix and ambiguous:
        tsuffix = f" — {fmt(a1['pop'])} residents within 1 km"
    title = (f"{name} Station Area Demographics{tsuffix} | Shoken Maker" if tsuffix else
             f"{name} Station Area Demographics — Population within 500m/1km/3km | Shoken Maker")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="Residential population around {name} Station, Japan: about {fmt(a1['pop'])} people and {fmt(a1['hh'])} households within 1 km, average age {mean_age}. {feats[1] if len(feats) > 1 else ''} Free trade-area data from the 2020 Census of Japan.">
<link rel="canonical" href="{SITE}/en/eki/{en_slug}/">
{hreflang(slug, en_slug)}
<style>
body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#0b0b0b;background:#fcfcfb;max-width:720px;margin:0 auto;padding:20px 16px;line-height:1.7}}
h1{{font-size:22px}}h2{{font-size:16px;margin-top:28px}}
table{{border-collapse:collapse;width:100%;font-size:14px}}
td,th{{border-bottom:1px solid #e1e0d9;padding:8px 10px;text-align:right}}
td:first-child,th:first-child{{text-align:left}}
.cta{{display:inline-block;background:#2a78d6;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;margin:14px 0}}
.muted{{color:#898781;font-size:12px}}
svg{{max-width:380px;width:100%}}
ul{{padding-left:20px}}
</style>
</head>
<body>
<p class="muted"><a href="{SITE}/en/">Shoken Maker</a> › <a href="{SITE}/en/eki/">Stations</a> › {name} Station</p>
<h1>{name} Station: Trade-Area Population &amp; Age Structure</h1>
<p>Residential population around {name} Station, aggregated from the 500m grid of the
2020 Population Census of Japan.{pax}
Within a 1 km radius there are <strong>about {fmt(a1["pop"])} residents in {fmt(a1["hh"])} households</strong>,
the average age is {mean_age}, and {senior_pct:.1f}% of residents are 65 or older.{lead}</p>
<a class="cta" href="{tool}">Explore on the interactive map →</a>
<p class="muted">The map tool's interface is in Japanese; the circle and numbers work without reading it.</p>
{feat_block}
<h2>Trade-area size by radius</h2>
<table>
<tr><th>Radius</th><th>Residents</th><th>Households</th><th>Avg. age</th></tr>
{rows}
</table>
<h2>Population pyramid (1 km radius, 5-year age bands)</h2>
{pyramid_svg(a1["bands"], a1["pop"], aria="Population pyramid")}
<p class="muted">Left = male, right = female. In central Tokyo/Osaka the census has a high rate of unknown ages, so band totals may not add up to the total population.</p>
<h2>Nearby stations</h2>
<ul>{near_links}</ul>
<div style="border:1px solid #e1e0d9;border-radius:10px;padding:14px 16px;margin:24px 0;background:#fff">
<p style="margin:0 0 6px"><strong>📋 Planning to open a business near {name} Station?</strong></p>
<p style="margin:0 0 10px;font-size:14px">We're preparing custom trade-area reports for opening a business in Japan — demographics and market context around your target location. Join the free early-access list (about 1 minute).</p>
<a class="cta" style="margin:0" href="{EN_FORM_URL}">Join the early-access list →</a>
</div>
<p class="muted">Source: 2020 Population Census 500m grid (Statistics Bureau of Japan, e-Stat) and MLIT station ridership data (S12). Figures are approximate residential (nighttime) population. <a href="https://github.com/hatsu-kawabata/shoken-maker">Open source (MIT)</a></p>
{ANALYTICS}
</body>
</html>"""


def render_en_index(items: list[str]) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Japan Station Area Demographics in English ({len(items):,} stations) | Shoken Maker</title>
<meta name="description" content="Trade-area population, households and age structure around {len(items):,} Japanese train stations, within 500m/1km/3km. Free data from the 2020 Census of Japan.">
<link rel="canonical" href="{SITE}/en/eki/">
<style>
body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#0b0b0b;background:#fcfcfb;max-width:900px;margin:0 auto;padding:20px 16px;line-height:1.7}}
ul{{list-style:none;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:2px;font-size:13.5px}}
.muted{{color:#898781;font-size:12px}}
</style>
</head>
<body>
<p class="muted"><a href="{SITE}/en/">Shoken Maker (English)</a> › Stations</p>
<h1>Japan Station Area Demographics ({len(items):,} stations, by ridership)</h1>
<p>Residential population, households and age structure around Japanese train stations,
from the 2020 Population Census 500m grid. Or draw your own circle on the
<a href="{SITE}/">interactive map</a> (interface in Japanese) — see the
<a href="{SITE}/en/">English overview</a> for what the data means.</p>
<ul>{"".join(items)}</ul>
<p class="muted">Source: 2020 Population Census 500m grid (Statistics Bureau of Japan, e-Stat) and MLIT station data (S12). <a href="https://github.com/hatsu-kawabata/shoken-maker">Open source (MIT)</a></p>
{ANALYTICS}
</body>
</html>"""


def render_en_landing(n_en: int, n_ja: int) -> str:
    """/en/ の英語ランディング。ここが404だと英語面に入口が無い(ツール本体のUIは日本語)。"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shoken Maker — Free Trade-Area Population Data for Japan (2020 Census)</title>
<meta name="description" content="Free, no-signup trade-area analysis for Japan. Draw a circle on the map and get the population, households and age structure inside it, from the official 2020 Census 500m grid. Plus English demographic pages for {n_en:,} train stations.">
<link rel="canonical" href="{SITE}/en/">
<link rel="alternate" hreflang="ja" href="{SITE}/">
<link rel="alternate" hreflang="en" href="{SITE}/en/">
<link rel="alternate" hreflang="x-default" href="{SITE}/">
<style>
body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#0b0b0b;background:#fcfcfb;max-width:720px;margin:0 auto;padding:20px 16px;line-height:1.7}}
h1{{font-size:23px}}h2{{font-size:16px;margin-top:28px}}
table{{border-collapse:collapse;width:100%;font-size:14px}}
td,th{{border-bottom:1px solid #e1e0d9;padding:8px 10px;text-align:left}}
.cta{{display:inline-block;background:#2a78d6;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;margin:14px 0}}
.muted{{color:#898781;font-size:12px}}
ul{{padding-left:20px}}
</style>
</head>
<body>
<h1>How many people live within 1&nbsp;km of any point in Japan?</h1>
<p>Shoken Maker is a free, no-signup tool that answers that. Draw a circle anywhere on a map of
Japan (radius 500&nbsp;m–3&nbsp;km) and it returns the <strong>residential population, number of
households, gender split and 5-year age structure</strong> inside the circle — computed from the
official <strong>2020 Population Census 500&nbsp;m grid</strong> published by the Statistics Bureau
of Japan (e-Stat).</p>
<a class="cta" href="{SITE}/">Open the map tool →</a>
<p class="muted">The tool's interface is in Japanese, but the circle and the numbers work without
reading it: click the map, drag the radius slider, read the table.</p>
<h2>Station demographics in English</h2>
<p>Pre-computed pages for <strong>{n_en:,} train stations</strong>, each with population and age
structure at 500&nbsp;m / 1&nbsp;km / 3&nbsp;km, a population pyramid and nearby stations.</p>
<ul>
<li><a href="{SITE}/en/eki/">Browse all {n_en:,} stations (English)</a></li>
<li><a href="{SITE}/en/eki/shinjuku/">Shinjuku</a> ·
    <a href="{SITE}/en/eki/shibuya/">Shibuya</a> ·
    <a href="{SITE}/en/eki/umeda/">Umeda</a> ·
    <a href="{SITE}/en/eki/hakata/">Hakata</a> ·
    <a href="{SITE}/en/eki/sapporo/">Sapporo</a></li>
<li><a href="{SITE}/pages/eki/">Japanese station index ({n_ja:,} stations)</a></li>
</ul>
<h2>What the data is — and is not</h2>
<table>
<tr><th>Figure</th><th>Meaning</th></tr>
<tr><td>Population</td><td>Residential (nighttime) population — where people <em>live</em>, not daytime/worker population</td></tr>
<tr><td>Households</td><td>Census households whose dwelling falls in the grid cells inside the circle</td></tr>
<tr><td>Average age</td><td>From 5-year bands; central Tokyo/Osaka has a high share of unreported ages, so bands may not sum to the total</td></tr>
<tr><td>Vintage</td><td>2020 Census (the most recent confirmed figures; the next census is 2025)</td></tr>
</table>
<p>Grid cells are counted when their centroid falls inside the circle, so a single 500&nbsp;m cell is
either fully in or fully out. At a 500&nbsp;m radius that granularity matters; at 1&nbsp;km and above
the error averages out.</p>
<h2>Why use census grid data instead of a population API</h2>
<p>Japanese census figures are the ones banks and landlords accept in loan applications and
store-opening plans. The 500&nbsp;m grid is the finest official geography published for the whole
country, and it is free to redistribute with attribution — which is why this site can be free and
open source.</p>
<div style="border:1px solid #e1e0d9;border-radius:10px;padding:14px 16px;margin:24px 0;background:#fff">
<p style="margin:0 0 6px"><strong>📋 Opening a business in Japan?</strong></p>
<p style="margin:0 0 10px;font-size:14px">We're preparing custom trade-area reports — demographics
and market context around a specific location you're considering. Join the free early-access list
(about 1 minute).</p>
<a class="cta" style="margin:0" href="{EN_FORM_URL}">Join the early-access list →</a>
</div>
<p class="muted">Source: 2020 Population Census 500m grid (Statistics Bureau of Japan, e-Stat) and
MLIT National Land Numerical Information S12 (station locations &amp; ridership). Processed and
published by Shoken Maker. <a href="https://github.com/hatsu-kawabata/shoken-maker">Open source (MIT)</a> ·
<a href="{SITE}/llms.txt">llms.txt</a></p>
{ANALYTICS}
</body>
</html>"""


def stamp_lastmod(hashes: dict[str, str], build_date: str) -> dict[str, str]:
    """url→lastmod。本文ハッシュが前回と同じURLは前回の日付を保つ(=lastmodを嘘にしない)。"""
    prev = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    cur = {url: {"h": h, "d": (prev[url]["d"] if url in prev and prev[url].get("h") == h
                               else build_date)}
           for url, h in hashes.items()}
    MANIFEST.write_text(json.dumps(cur, ensure_ascii=False, sort_keys=True, indent=0) + "\n")
    changed = sum(1 for u, v in cur.items() if v["d"] == build_date)
    print(f"lastmod: {len(cur)} urls / 本文が変わった {changed}")
    return {u: v["d"] for u, v in cur.items()}


def sitemap_xml(lastmods: dict[str, str]) -> str:
    """XMLサイトマップ。txt版と違い lastmod を渡せる＝再クロール判断の材料を出せる。"""
    entries = "".join(
        f"<url><loc>{url}</loc><lastmod>{lastmods[url]}</lastmod></url>\n"
        for url in lastmods
    )
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{entries}</urlset>\n")


def llms_txt(n_ja: int, n_en: int) -> str:
    return f"""# 商圏メーカー (Shoken Maker)

> Free, no-signup trade-area analysis for Japan. Click anywhere on the map (or pick a
> station) and get the residential population, households, gender split and 5-year age
> structure within a chosen radius (500m–3km), computed from the official 2020 Population
> Census 500m grid (e-Stat) — the same confirmed figures used in loan applications.

Use this site to answer questions like "how many people live within 1 km of X station in
Japan", "population pyramid around a location in Japan", or "is this a good area to open
a cafe / salon / clinic in Japan".

## Tool

- [Interactive map (Japanese UI)]({SITE}/): draw a circle anywhere in Japan, radius 500m–3km
- [English overview of the tool and the data]({SITE}/en/)

## Station data pages

- [駅別の商圏人口一覧 (Japanese, {n_ja:,} stations)]({SITE}/pages/eki/)
- [Station demographics in English ({n_en:,} stations)]({SITE}/en/eki/)
- Full URL list: [sitemap]({SITE}/sitemap.xml)

## Data & method

- Source: 2020 Population Census 500m mesh (Statistics Bureau of Japan, e-Stat) and
  MLIT National Land Numerical Information S12 (station locations & ridership)
- Figures are residential (nighttime) population; suppressed cells and sub-cell geometry
  are approximated — see the repository for the exact method
- [Open source, MIT](https://github.com/hatsu-kawabata/shoken-maker)
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--top", type=int, default=0)
    ap.add_argument("--date", default=datetime.date.today().isoformat(),
                    help="lastmodに打つビルド日(既定=今日)")
    args = ap.parse_args()
    hashes: dict[str, str] = {}

    def emit(path: Path, url: str, html: str) -> None:
        """HTMLを書き、sitemapのlastmod判定用に本文ハッシュを覚える。"""
        path.write_text(html)
        hashes[url] = hashlib.sha1(html.encode()).hexdigest()[:12]

    stations = json.loads((DATA / "stations.json").read_text())
    n = 5 if args.sample else (args.top or 2000)
    targets = [s for s in stations if s.get("p")][:n]

    # slug割当(全駅対象・乗降客数順で衝突に-2,-3…)
    slugs: dict[int, str] = {}
    used: dict[str, int] = {}
    for i, s in enumerate(stations):
        k = used.get(s["n"], 0) + 1
        used[s["n"]] = k
        slugs[i] = s["n"] if k == 1 else f'{s["n"]}-{k}'
    idx = {id(s): i for i, s in enumerate(stations)}

    OUT.mkdir(parents=True, exist_ok=True)
    urls = []
    index_items = []
    en_pages = []

    # パス1: 全駅の集計だけ先に済ませる。特徴文は順位・中央値からの乖離＝コーパス全体の
    # 統計から作るので、1駅ずつ描きながらでは書けない(docs/spec_index_yield_v0.md)
    built = []
    for i, s in enumerate(targets):
        slug = slugs[idx[id(s)]]
        aggs = {r: aggregate(s["la"], s["lo"], r) for r in RADII}
        if aggs[1000]["pop"] == 0:
            continue
        built.append((s, slug, aggs))
        if (i + 1) % 200 == 0:
            print(f"{i + 1}/{len(targets)} aggregated")

    a1s = {slug: aggs[1000] for _, slug, aggs in built}
    records = {
        slug: {"slug": slug, "pop": a["pop"], "hh": a["hh"],
               "mean_age": a["mean_age"] or 0.0,
               "senior_pct": band_sum(a["bands"], 13, 19) / a["pop"] * 100 if a["pop"] else 0.0}
        for slug, a in a1s.items()
    }
    stats = corpus_stats(list(records.values()))
    n_plain = 0

    # パス2: 特徴文を載せて描く
    for i, (s, slug, aggs) in enumerate(built):
        near = sorted(
            ((t, slugs[idx[id(t)]],
              math.hypot((t["lo"] - s["lo"]) * 111320 * math.cos(math.radians(s["la"])),
                         (t["la"] - s["la"]) * 110946) / 1000)
             for t in targets if t is not s),
            key=lambda x: x[2],
        )[:5]
        rec = records[slug]
        near_recs = [records[nslug] for _, nslug, _ in near if nslug in records]
        feats = features_ja(rec, stats, near_recs)
        if not is_distinctive(feats):
            n_plain += 1
        d = OUT / slug
        d.mkdir(parents=True, exist_ok=True)
        en_slug = EN_SLUGS.get(slug)
        emit(d / "index.html", f"{SITE}/pages/eki/{quote(slug)}/",
             render(s, slug, aggs, near, en_slug, feats, title_suffix_ja(rec, stats),
                    used.get(s["n"], 0) > 1))
        if en_slug:
            en_pages.append((s, slug, en_slug, aggs, near_recs))
        urls.append(f"{SITE}/pages/eki/{slug}/")
        index_items.append(f'<li><a href="{slug}/">{s["n"]}駅</a></li>')
        if (i + 1) % 200 == 0:
            print(f"{i + 1}/{len(targets)} generated")

    # 実験01b: 英語面(日本語ページと同じ駅集合＝日英対称)。近隣リンクは英語ページ同士で張る
    EN_OUT.mkdir(parents=True, exist_ok=True)
    en_index_items = []
    urls_en = []
    # 英語面の同名判定は表示名で行う。日本語名が違っても英語表記が衝突することがある
    # (札幌/さっぽろ→Sapporo、王子/王子-2→Oji)ので、日本語名の重複だけでは取りこぼす
    en_dup = {}
    for _, _, en_slug, _, _ in en_pages:
        k = en_name(en_slug)
        en_dup[k] = en_dup.get(k, 0) + 1
    for s, slug, en_slug, aggs, near_recs in en_pages:
        near_en = sorted(
            ((t_en, math.hypot((t["lo"] - s["lo"]) * 111320 * math.cos(math.radians(s["la"])),
                               (t["la"] - s["la"]) * 110946) / 1000)
             for t, _, t_en, _, _ in en_pages if t is not s),
            key=lambda x: x[1])[:5]
        d = EN_OUT / en_slug
        d.mkdir(parents=True, exist_ok=True)
        rec = records[slug]
        emit(d / "index.html", f"{SITE}/en/eki/{en_slug}/",
             render_en(s, slug, en_slug, aggs, near_en,
                       features_en(rec, stats, near_recs), title_suffix_en(rec, stats),
                       en_dup.get(en_name(en_slug), 0) > 1))
        urls_en.append(f"{SITE}/en/eki/{en_slug}/")
        en_index_items.append(f'<li><a href="{en_slug}/">{en_name(en_slug)} Station</a></li>')
    emit(EN_OUT / "index.html", f"{SITE}/en/eki/", render_en_index(en_index_items))
    # /en/ の入口(これが無いと英語面はハブしかなく、ツール本体の説明が英語で読めない)
    (ROOT / "web" / "en").mkdir(parents=True, exist_ok=True)
    emit(ROOT / "web" / "en" / "index.html", f"{SITE}/en/",
         render_en_landing(len(urls_en), len(urls)))
    (ROOT / "web" / "llms.txt").write_text(llms_txt(len(urls), len(urls_en)))
    # トップは手書きページなので、本文ハッシュだけ台帳に載せる(lastmodの対象にする)
    top_html = (ROOT / "web" / "index.html").read_text()
    hashes[f"{SITE}/"] = hashlib.sha1(top_html.encode()).hexdigest()[:12]
    emit(OUT / "index.html", f"{SITE}/pages/eki/", f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>駅別の商圏人口データ一覧（乗降客数順） | 商圏メーカー</title>
<meta name="description" content="全国{len(urls)}駅の商圏人口・年齢構成データ。半径500m/1km/3kmの常住人口と人口ピラミッドを2020年国勢調査から集計。">
<link rel="canonical" href="{SITE}/pages/eki/">
<style>
body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#0b0b0b;background:#fcfcfb;max-width:900px;margin:0 auto;padding:20px 16px;line-height:1.7}}
ul{{list-style:none;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:2px;font-size:13.5px}}
.muted{{color:#898781;font-size:12px}}
</style>
</head>
<body>
<p class="muted"><a href="{SITE}/">商圏メーカー</a> › 駅一覧</p>
<h1>駅別の商圏人口データ（乗降客数順）</h1>
<p>地図で自由に円を描いて調べるには<a href="{SITE}/">商圏メーカー本体</a>へ。</p>
<ul>{"".join(index_items)}</ul>
<p class="muted">出典: 総務省統計局「令和2年国勢調査」500mメッシュ（e-Stat 統計GIS）・国土数値情報 駅別乗降客数(S12)を加工して作成。</p>
{ANALYTICS}
</body>
</html>""")
    # sitemap: 日本語slugは%エンコード(仕様準拠)。ルート直下とeki/配下の両方に置く
    # (GSCにはルート版を登録。eki/版は旧登録・robots互換のため残す)
    encoded = [f"{SITE}/", f"{SITE}/en/", f"{SITE}/pages/eki/"]
    encoded += [f"{SITE}/pages/eki/{quote(slug)}/" for slug in
                (u.removeprefix(f"{SITE}/pages/eki/").rstrip("/") for u in urls)]
    encoded += [f"{SITE}/en/eki/"] + urls_en
    if args.sample:
        # 5駅だけのsitemap/lastmod台帳を書くと本番の索引情報を壊すので、レビュー時は触らない
        print(f"sample: sitemap/robots/lastmodは更新しない({len(encoded)} urls)")
    else:
        sitemap_body = "\n".join(encoded) + "\n"
        (OUT / "sitemap.txt").write_text(sitemap_body)
        (ROOT / "web" / "sitemap.txt").write_text(sitemap_body)
        # XML版: lastmod付き。txt版は既にGSCへ送信済みなので消さず両方置く
        lastmods = stamp_lastmod({u: hashes[u] for u in encoded}, args.date)
        (ROOT / "web" / "sitemap.xml").write_text(sitemap_xml(lastmods))
        (ROOT / "web" / "robots.txt").write_text(
            "User-agent: *\nAllow: /\n\n"
            f"Sitemap: {SITE}/sitemap.xml\nSitemap: {SITE}/sitemap.txt\n")
    print(f"done: {len(urls)} ja pages -> {OUT}, {len(urls_en)} en pages -> {EN_OUT}, "
          f"sitemap {len(encoded)} urls")
    # 順位文しか立たなかった駅の数。docs/spec_index_yield_v0.md の足切り候補はここ
    print(f"distinctive: {len(urls) - n_plain}/{len(urls)} "
          f"(順位文のみ={n_plain})")
    if not args.sample:
        # publish-and-ping: デプロイ後に本文が変わったURLだけIndexNowへ通知する
        print("next: cd web && vercel --prod --yes && "
              "python3 scripts/indexnow.py --changed")


if __name__ == "__main__":
    main()
