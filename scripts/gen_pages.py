#!/usr/bin/env python3
"""駅ごとの商圏ページ(静的HTML)を生成する。

使い方:
  python3 scripts/gen_pages.py --sample     # 上位5駅だけ生成(レビュー用)
  python3 scripts/gen_pages.py --top 2000   # 乗降客数上位2000駅を生成

出力: web/pages/eki/{slug}/index.html と web/pages/eki/sitemap.txt
slug: 駅名(同名衝突は乗降客数順に -2, -3 を付与)
"""
import argparse
import json
import math
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"
OUT = ROOT / "web" / "pages" / "eki"
EN_OUT = ROOT / "web" / "en" / "eki"
SITE = "https://shoken-maker.vercel.app"
# S4需要計器(scheme_funnel.md): 個別分析の事前登録フォーム。裏のサービスは未実装=純粋な需要温度計
# 日英で別フォーム=セグメント別のS4信号(実験01b)
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSeD1Kkc6iHgvICicMsXude3PE27iuOfWPCvRTtfJeHEr2S9JA/viewform"
EN_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSeKpROMSuAETstOQ4To5JsIJ17XZnFKTP0l522PrBbISxDLSg/viewform"
# 上位200駅のローマ字slug(build_en_slugs.pyで検証付き生成)
EN_SLUGS: dict[str, str] = json.loads((Path(__file__).resolve().parent / "en_slugs.json").read_text())

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


def render(st, slug: str, aggs: dict, nearby: list, en_slug: str | None = None) -> str:
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
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name}駅の商圏人口・年齢構成（半径500m/1km/3km）| 商圏メーカー</title>
<meta name="description" content="{name}駅（{lines}）の商圏人口: 半径1km圏の常住人口は約{fmt(a1['pop'])}人・{fmt(a1['hh'])}世帯、平均年齢{mean_age}。2020年国勢調査500mメッシュによる無料の商圏分析。">
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
65歳以上の比率は{senior_pct:.1f}%です。</p>
<a class="cta" href="{tool}">地図で円を動かして詳しく見る →</a>
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


def render_en(st, slug: str, en_slug: str, aggs: dict, nearby_en: list) -> str:
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
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} Station Area Demographics — Population within 500m/1km/3km | Shoken Maker</title>
<meta name="description" content="Residential population around {name} Station, Japan: about {fmt(a1['pop'])} people and {fmt(a1['hh'])} households within 1 km, average age {mean_age}. Free trade-area data from the 2020 Census of Japan.">
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
<p class="muted"><a href="{SITE}/en/eki/">Shoken Maker</a> › {name} Station</p>
<h1>{name} Station: Trade-Area Population &amp; Age Structure</h1>
<p>Residential population around {name} Station, aggregated from the 500m grid of the
2020 Population Census of Japan.{pax}
Within a 1 km radius there are <strong>about {fmt(a1["pop"])} residents in {fmt(a1["hh"])} households</strong>,
the average age is {mean_age}, and {senior_pct:.1f}% of residents are 65 or older.</p>
<a class="cta" href="{tool}">Explore on the interactive map →</a>
<p class="muted">The map tool's interface is in Japanese; the circle and numbers work without reading it.</p>
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
<title>Japan Station Area Demographics in English ({len(items)} busiest stations) | Shoken Maker</title>
<meta name="description" content="Trade-area population, households and age structure around Japan's {len(items)} busiest train stations, within 500m/1km/3km. Free data from the 2020 Census of Japan.">
<link rel="canonical" href="{SITE}/en/eki/">
<style>
body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#0b0b0b;background:#fcfcfb;max-width:900px;margin:0 auto;padding:20px 16px;line-height:1.7}}
ul{{list-style:none;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:2px;font-size:13.5px}}
.muted{{color:#898781;font-size:12px}}
</style>
</head>
<body>
<h1>Japan Station Area Demographics (by ridership)</h1>
<p>Residential population, households and age structure around Japan's busiest train stations,
from the 2020 Population Census 500m grid. Or draw your own circle on the
<a href="{SITE}/">interactive map</a> (interface in Japanese).</p>
<ul>{"".join(items)}</ul>
<p class="muted">Source: 2020 Population Census 500m grid (Statistics Bureau of Japan, e-Stat) and MLIT station data (S12). <a href="https://github.com/hatsu-kawabata/shoken-maker">Open source (MIT)</a></p>
{ANALYTICS}
</body>
</html>"""


LLMS_TXT = f"""# 商圏メーカー (Shoken Maker)

> Free, no-signup trade-area analysis for Japan. Click anywhere on the map (or pick a
> station) and get the residential population, households, gender split and 5-year age
> structure within a chosen radius (500m–3km), computed from the official 2020 Population
> Census 500m grid (e-Stat) — the same confirmed figures used in loan applications.

Use this site to answer questions like "how many people live within 1 km of X station in
Japan", "population pyramid around a location in Japan", or "is this a good area to open
a cafe / salon / clinic in Japan".

## Tool

- [Interactive map (Japanese UI)]({SITE}/): draw a circle anywhere in Japan, radius 500m–3km

## Station data pages

- [駅別の商圏人口一覧 (Japanese, ~2,000 stations)]({SITE}/pages/eki/)
- [Station demographics in English (200 busiest stations)]({SITE}/en/eki/)
- Full URL list: [sitemap]({SITE}/sitemap.txt)

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
    args = ap.parse_args()

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
    for i, s in enumerate(targets):
        slug = slugs[idx[id(s)]]
        aggs = {r: aggregate(s["la"], s["lo"], r) for r in RADII}
        if aggs[1000]["pop"] == 0:
            continue
        near = sorted(
            ((t, slugs[idx[id(t)]],
              math.hypot((t["lo"] - s["lo"]) * 111320 * math.cos(math.radians(s["la"])),
                         (t["la"] - s["la"]) * 110946) / 1000)
             for t in targets if t is not s),
            key=lambda x: x[2],
        )[:5]
        d = OUT / slug
        d.mkdir(parents=True, exist_ok=True)
        en_slug = EN_SLUGS.get(slug)
        (d / "index.html").write_text(render(s, slug, aggs, near, en_slug))
        if en_slug:
            en_pages.append((s, slug, en_slug, aggs))
        urls.append(f"{SITE}/pages/eki/{slug}/")
        index_items.append(f'<li><a href="{slug}/">{s["n"]}駅</a></li>')
        if (i + 1) % 200 == 0:
            print(f"{i + 1}/{len(targets)} generated")

    # 実験01b: 英語面(上位200駅・LLMO)。近隣リンクは英語ページ同士で張る
    EN_OUT.mkdir(parents=True, exist_ok=True)
    en_index_items = []
    urls_en = []
    for s, slug, en_slug, aggs in en_pages:
        near_en = sorted(
            ((t_en, math.hypot((t["lo"] - s["lo"]) * 111320 * math.cos(math.radians(s["la"])),
                               (t["la"] - s["la"]) * 110946) / 1000)
             for t, _, t_en, _ in en_pages if t is not s),
            key=lambda x: x[1])[:5]
        d = EN_OUT / en_slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(render_en(s, slug, en_slug, aggs, near_en))
        urls_en.append(f"{SITE}/en/eki/{en_slug}/")
        en_index_items.append(f'<li><a href="{en_slug}/">{en_name(en_slug)} Station</a></li>')
    (EN_OUT / "index.html").write_text(render_en_index(en_index_items))
    (ROOT / "web" / "llms.txt").write_text(LLMS_TXT)
    # sitemap: 日本語slugは%エンコード(仕様準拠)。ルート直下とeki/配下の両方に置く
    # (GSCにはルート版を登録。eki/版は旧登録・robots互換のため残す)
    encoded = [f"{SITE}/"] + [f"{SITE}/pages/eki/{quote(slug)}/" for slug in
                              (u.removeprefix(f"{SITE}/pages/eki/").rstrip("/") for u in urls)]
    encoded += [f"{SITE}/en/eki/"] + urls_en
    sitemap_body = "\n".join(encoded) + "\n"
    (OUT / "sitemap.txt").write_text(sitemap_body)
    (ROOT / "web" / "sitemap.txt").write_text(sitemap_body)
    (OUT / "index.html").write_text(f"""<!DOCTYPE html>
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
    print(f"done: {len(urls)} ja pages -> {OUT}, {len(urls_en)} en pages -> {EN_OUT}")


if __name__ == "__main__":
    main()
