#!/usr/bin/env python3
"""日本語slug→ローマ字slug対応表(en_slugs.json)を検証付きで生成する。

2層構成:
  1. 手書き層 EN (上位200駅) = 正本。既に公開・インデックス済みのURLなので不変。
  2. 機械層 = Wikidataの駅項目の英語ラベル(CC0)。座標2km以内での一致を必須にして
     同名別駅の誤接続を防ぐ。ローマ字は読みの機械変換ではなく人が書いたラベルなので、
     「読み間違い」は原理的に起きない(取りこぼしと表記ゆれだけが起きる)。

機械層の検定: 手書き200件と機械層を突き合わせ、不一致を分類して表示する。
2026-07-26の実測では187/200が完全一致、残り13件は(a)ハイフン位置の差
(b)同名衝突の連番 (c)Wikidataラベルへの運営会社名・括弧の混入 の3種のみで、
読みの誤りは0件だった。よって手書き層を優先しつつ機械層で拡張する設計を採る。

使い方:
  python3 scripts/build_en_slugs.py              # キャッシュから生成
  python3 scripts/build_en_slugs.py --fetch      # Wikidataを引き直してキャッシュ更新
  python3 scripts/build_en_slugs.py --audit      # 手書き層 vs 機械層の検定を表示
"""
import argparse
import json
import math
import re
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
# 手書き層のカバー範囲(乗降客数上位N駅)。この200件はURL不変の約束がある
N_EN = 200
# 機械層で英語ページを出す上限(日本語ページと同じ駅集合＝日英対称にする)
N_EN_MACHINE = 2000
WD_CACHE = HERE / "wikidata_stations.json"
# 和名一致に加えてこの距離以内を要求する(同名別駅の誤接続を防ぐ操作的証人)
MATCH_KM = 2.0
WD_QUERY = """SELECT DISTINCT ?ja ?en ?coord WHERE {
  ?s wdt:P31/wdt:P279* wd:Q55488 .
  ?s wdt:P17 wd:Q17 .
  ?s wdt:P625 ?coord .
  ?s rdfs:label ?ja . FILTER(lang(?ja)="ja")
  ?s rdfs:label ?en . FILTER(lang(?en)="en")
}"""
UA = "shoken-maker/1.0 (https://shoken-maker.vercel.app) python-urllib"

EN = {
    "新宿": "shinjuku", "池袋": "ikebukuro", "渋谷": "shibuya", "横浜": "yokohama",
    "東京": "tokyo", "北千住": "kita-senju", "品川": "shinagawa", "名古屋": "nagoya",
    "高田馬場": "takadanobaba", "新橋": "shimbashi", "大阪": "osaka", "大宮": "omiya",
    "秋葉原": "akihabara", "目黒": "meguro", "西船橋": "nishi-funabashi", "京都": "kyoto",
    "押上": "oshiage", "上野": "ueno", "天王寺": "tennoji", "博多": "hakata",
    "町田": "machida", "金山": "kanayama", "新大阪": "shin-osaka", "梅田": "umeda",
    "大手町": "otemachi", "武蔵小杉": "musashi-kosugi", "大阪梅田": "osaka-umeda",
    "蒲田": "kamata", "中野": "nakano", "有楽町": "yurakucho", "藤沢": "fujisawa",
    "吉祥寺": "kichijoji", "大崎": "osaki", "川崎": "kawasaki", "綾瀬": "ayase",
    "柏": "kashiwa", "五反田": "gotanda", "船橋": "funabashi", "中目黒": "naka-meguro",
    "西日暮里": "nishi-nippori", "京橋": "kyobashi", "新横浜": "shin-yokohama",
    "日暮里": "nippori", "大井町": "oimachi", "日吉": "hiyoshi", "恵比寿": "ebisu",
    "鶴橋": "tsuruhashi", "仙台": "sendai", "市ヶ谷": "ichigaya", "飯田橋": "iidabashi",
    "国分寺": "kokubunji", "登戸": "noborito", "小竹向原": "kotake-mukaihara",
    "立川": "tachikawa", "錦糸町": "kinshicho", "四ツ谷": "yotsuya", "新木場": "shin-kiba",
    "淀屋橋": "yodoyabashi", "溝の口": "mizonokuchi", "戸塚": "totsuka",
    "名鉄名古屋": "meitetsu-nagoya", "松戸": "matsudo", "海老名": "ebina",
    "九段下": "kudanshita", "代々木上原": "yoyogi-uehara", "浜松町": "hamamatsucho",
    "日本橋": "nihombashi", "荻窪": "ogikubo", "田町": "tamachi", "豊洲": "toyosu",
    "長津田": "nagatsuta", "難波": "namba", "三ノ宮": "sannomiya", "神田": "kanda",
    "千葉": "chiba", "下北沢": "shimokitazawa", "御茶ノ水": "ochanomizu",
    "難波-2": "namba-2", "大和": "yamato", "三軒茶屋": "sangen-jaya", "銀座": "ginza",
    "巣鴨": "sugamo", "新今宮": "shin-imamiya", "神保町": "jimbocho",
    "新宿三丁目": "shinjuku-sanchome", "大船": "ofuna", "橋本": "hashimoto",
    "本町": "hommachi", "神戸三宮": "kobe-sannomiya", "浅草": "asakusa", "栄": "sakae",
    "泉岳寺": "sengakuji", "上大岡": "kamiooka", "新宿-2": "shinjuku-2", "練馬": "nerima",
    "あざみ野": "azamino", "三宮": "sannomiya-2", "川越": "kawagoe",
    "六本木": "roppongi", "中央林間": "chuo-rinkan", "赤羽": "akabane",
    "水道橋": "suidobashi", "桜木町": "sakuragicho", "門前仲町": "monzen-nakacho",
    "本八幡": "moto-yawata", "浦和": "urawa", "姪浜": "meinohama",
    "津田沼": "tsudanuma", "王子": "oji", "日比谷": "hibiya", "表参道": "omote-sando",
    "小田原": "odawara", "札幌": "sapporo", "三鷹": "mitaka", "菊名": "kikuna",
    "和光市": "wakoshi", "八丁堀": "hatchobori", "東梅田": "higashi-umeda",
    "大阪梅田-2": "osaka-umeda-2", "青山一丁目": "aoyama-itchome", "大通": "odori",
    "湘南台": "shonandai", "分倍河原": "bubaigawara", "大森": "omori",
    "さっぽろ": "sapporo-2", "東銀座": "higashi-ginza", "浅草橋": "asakusabashi",
    "舞浜": "maihama", "武蔵溝ノ口": "musashi-mizonokuchi", "八王子": "hachioji",
    "武蔵境": "musashi-sakai", "大阪難波": "osaka-namba", "朝霞台": "asakadai",
    "川口": "kawaguchi", "南流山": "minami-nagareyama",
    "流山おおたかの森": "nagareyama-otakanomori", "西武新宿": "seibu-shinjuku",
    "新小岩": "shin-koiwa", "関内": "kannai", "広島": "hiroshima",
    "天下茶屋": "tengachaya", "南越谷": "minami-koshigaya", "代々木": "yoyogi",
    "大阪阿部野橋": "osaka-abenobashi", "鶴見": "tsurumi", "新越谷": "shin-koshigaya",
    "大曽根": "ozone", "二子玉川": "futako-tamagawa", "心斎橋": "shinsaibashi",
    "月島": "tsukishima", "自由が丘": "jiyugaoka", "北朝霞": "kita-asaka",
    "天神": "tenjin", "岡山": "okayama", "亀戸": "kameido", "原宿": "harajuku",
    "霞ヶ関": "kasumigaseki", "本厚木": "hon-atsugi", "天満橋": "temmabashi",
    "駒込": "komagome", "御徒町": "okachimachi", "京急川崎": "keikyu-kawasaki",
    "千里中央": "senri-chuo", "西鉄福岡（天神）": "nishitetsu-fukuoka-tenjin",
    "人形町": "ningyocho", "小岩": "koiwa", "調布": "chofu",
    "相模大野": "sagami-ono", "高槻": "takatsuki", "新百合ヶ丘": "shin-yurigaoka",
    "東陽町": "toyocho", "辻堂": "tsujido", "平塚": "hiratsuka",
    "武蔵小金井": "musashi-koganei", "三越前": "mitsukoshimae",
    "海浜幕張": "kaihin-makuhari", "市川": "ichikawa", "久喜": "kuki",
    "中野坂上": "nakano-sakaue", "静岡": "shizuoka", "蕨": "warabi",
    "南浦和": "minami-urawa", "東川口": "higashi-kawaguchi", "弁天町": "bentencho",
    "小倉": "kokura", "山科": "yamashina", "馬喰横山": "bakuro-yokoyama",
    "西梅田": "nishi-umeda", "茅場町": "kayabacho", "西川口": "nishi-kawaguchi",
    "新鎌ヶ谷": "shin-kamagaya", "西九条": "nishikujo",
    "さいたま新都心": "saitama-shintoshin", "大塚": "otsuka", "神戸": "kobe",
    "茅ヶ崎": "chigasaki", "鎌倉": "kamakura", "堺筋本町": "sakaisuji-hommachi",
    "東戸塚": "higashi-totsuka", "中山": "nakayama",
}


def stations_in_order() -> list[tuple[str, dict]]:
    """gen_pages.pyと同一のslug割当で(slug, 駅)を乗降客数順に返す。"""
    stations = json.loads((ROOT / "web" / "data" / "stations.json").read_text())
    slugs, used = {}, {}
    for i, s in enumerate(stations):
        k = used.get(s["n"], 0) + 1
        used[s["n"]] = k
        slugs[i] = s["n"] if k == 1 else f'{s["n"]}-{k}'
    return [(slugs[i], s) for i, s in enumerate(stations) if s.get("p")]


def norm_ja(name: str) -> str:
    """和名の表記ゆれを畳む(ヶ/ケ・全角半角・中黒・空白・丸括弧)。"""
    s = unicodedata.normalize("NFKC", name)
    for a, b in (("ヶ", "ケ"), ("・", ""), ("･", ""), (" ", ""), ("　", "")):
        s = s.replace(a, b)
    return s


MACRON = str.maketrans({"ō": "o", "Ō": "O", "ū": "u", "Ū": "U", "ā": "a", "Ā": "A",
                        "ī": "i", "Ī": "I", "ē": "e", "Ē": "E", "â": "a", "ô": "o"})
# ラベルに混入していたら機械層では採用しない語(運営会社名・路線名などの混入検出)
DIRTY = ("station", "corporation", "railway", "railroad", "line", "company", "co ltd")


def label_to_slug(label: str) -> str | None:
    """Wikidataの英語ラベル→slug。混入が残るものはNone(=機械層では出さない)。"""
    s = re.sub(r"\([^)]*\)", " ", label)          # 曖昧さ回避の括弧を落とす
    s = re.sub(r"\bstation\b", " ", s, flags=re.IGNORECASE)
    s = s.translate(MACRON)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower().replace("'", "").replace(".", "")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if not s or len(s) > 40 or any(w in s.replace("-", " ") for w in DIRTY):
        return None
    return s


def label_to_name(label: str) -> str:
    """表示名(H1・リンク文字列用)。マクロンは残さず、括弧と Station は落とす。"""
    s = re.sub(r"\([^)]*\)", " ", label)
    s = re.sub(r"\bstation\b", " ", s, flags=re.IGNORECASE)
    s = s.translate(MACRON)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip(" -")


def dist_km(la1: float, lo1: float, la2: float, lo2: float) -> float:
    return math.hypot((lo2 - lo1) * 111320 * math.cos(math.radians(la1)),
                      (la2 - la1) * 110946) / 1000


def fetch_wikidata() -> dict:
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode(
        {"query": WD_QUERY, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/sparql-results+json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        rows = json.load(r)["results"]["bindings"]
    out: dict[str, list] = {}
    for row in rows:
        m = re.match(r"Point\(([-0-9.]+) ([-0-9.]+)\)", row["coord"]["value"])
        if not m:
            continue
        ja = row["ja"]["value"].removesuffix("駅")
        out.setdefault(ja, []).append(
            [row["en"]["value"], round(float(m.group(2)), 5), round(float(m.group(1)), 5)])
    WD_CACHE.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":"),
                                   sort_keys=True) + "\n")
    print(f"fetched: {len(rows)} rows / {len(out)} 和名 -> {WD_CACHE}")
    return out


def resolve_label(slug: str, st: dict, by_name: dict) -> tuple[str | None, float | None]:
    """和名一致＋座標{MATCH_KM}km以内でWikidataラベルを1つ選ぶ。"""
    base = re.sub(r"-\d+$", "", slug)
    cands = by_name.get(norm_ja(base))
    if not cands:
        return None, None
    label, la, lo = min(cands, key=lambda c: dist_km(st["la"], st["lo"], c[1], c[2]))
    d = dist_km(st["la"], st["lo"], la, lo)
    return (label, d) if d <= MATCH_KM else (None, d)


def build(targets: list[tuple[str, dict]], by_name: dict) -> tuple[dict, dict, dict]:
    """手書き層優先＋機械層で拡張したslug表・表示名表・不採用理由を返す。"""
    en_slugs: dict[str, str] = {}
    en_names: dict[str, str] = {}
    skipped: dict[str, str] = {}
    taken = set(EN.values())                       # 手書き層のslugを先に予約
    for slug, st in targets[:N_EN_MACHINE]:
        if slug in EN:                             # 手書き層は無条件で優先(URL不変)
            en_slugs[slug] = EN[slug]
            continue
        label, d = resolve_label(slug, st, by_name)
        if label is None:
            skipped[slug] = "和名一致なし" if d is None else f"座標が{d:.0f}km離れている"
            continue
        cand = label_to_slug(label)
        if cand is None:
            skipped[slug] = f"ラベルに混入: {label}"
            continue
        base, k = cand, 1
        while cand in taken:                       # 同名衝突は日本語側と同じ規則で連番
            k += 1
            cand = f"{base}-{k}"
        taken.add(cand)
        en_slugs[slug] = cand
        en_names[cand] = label_to_name(label)
    return en_slugs, en_names, skipped


def fold_reading(s: str) -> str:
    """slugを「読みが同じなら同じ」正規形に畳む。

    ハイフンの位置(shin-osaka / shinosaka)と、撥音のヘボン式表記ゆれ
    (kaihimmakuhari / kaihin-makuhari のように m/n が b・m・p の前で入れ替わる)は
    どちらも同じ読みを指す。ここで一致しないものだけが本当の読みの差。
    """
    s = s.replace("-", "")
    return re.sub(r"m(?=[bmp])", "n", s)


def audit(by_name: dict, targets: list[tuple[str, dict]]) -> None:
    """手書き200 vs 機械層の一致検定(機械経路を信用してよいかの操作的証人)。"""
    kinds: dict[str, list[str]] = {"一致": [], "表記差(読み同じ)": [], "連番(同名衝突)": [],
                                   "ラベル混入": [], "副名の欠落": [], "読みの差": []}
    for slug, st in targets[:N_EN]:
        gold = EN.get(slug)
        label, _ = resolve_label(slug, st, by_name)
        mech = label_to_slug(label) if label else None
        if mech == gold:
            kinds["一致"].append(slug)
        elif mech and gold and fold_reading(mech) == fold_reading(gold):
            kinds["表記差(読み同じ)"].append(f"{slug}: 手書き={gold} 機械={mech}")
        elif gold and re.search(r"-\d+$", gold):
            kinds["連番(同名衝突)"].append(f"{slug}: 手書き={gold} 機械={mech}")
        elif mech is None:
            kinds["ラベル混入"].append(f"{slug}: 手書き={gold} ラベル={label}")
        elif mech and gold and fold_reading(gold).startswith(fold_reading(mech)):
            # 括弧の中身を落としたぶんだけ短い(例: 西鉄福岡（天神）→ nishitetsu-fukuoka)
            kinds["副名の欠落"].append(f"{slug}: 手書き={gold} 機械={mech}")
        else:
            kinds["読みの差"].append(f"{slug}: 手書き={gold} 機械={mech}")
    print(f"\n=== 検定: 手書き{N_EN} vs 機械層 ===")
    for k, v in kinds.items():
        print(f"  {k}: {len(v)}")
        if k not in ("一致",):
            for line in v:
                print(f"    - {line}")
    assert not kinds["読みの差"], "機械層に読みの差がある→ 手書き層(EN)に追加して固定する"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="Wikidataを引き直してキャッシュ更新")
    ap.add_argument("--audit", action="store_true", help="手書き層との一致検定を表示")
    args = ap.parse_args()

    targets = stations_in_order()
    hand = [s for s, _ in targets[:N_EN]]
    missing = [s for s in hand if s not in EN]
    extra = [s for s in EN if s not in hand]
    assert not missing, f"手書き層に不足: {missing}"
    assert not extra, f"手書き層に余剰(top{N_EN}外): {extra}"

    by_name = fetch_wikidata() if args.fetch else {
        norm_ja(k): v for k, v in json.loads(WD_CACHE.read_text()).items()}
    if args.fetch:
        by_name = {norm_ja(k): v for k, v in by_name.items()}
    if args.audit:
        audit(by_name, targets)

    en_slugs, en_names, skipped = build(targets, by_name)
    vals = list(en_slugs.values())
    dup = sorted({v for v in vals if vals.count(v) > 1})
    bad = [v for v in vals if not all(c.islower() or c.isdigit() or c == "-" for c in v)]
    assert not dup, f"ローマ字slug衝突: {dup}"
    assert not bad, f"不正な文字: {bad}"
    # 公開済みURLの不変性(これが崩れると既にインデックスされた200枚が404になる)
    for slug, v in EN.items():
        assert en_slugs[slug] == v, f"公開済みslugが変わった: {slug} {v} -> {en_slugs[slug]}"

    (HERE / "en_slugs.json").write_text(json.dumps(en_slugs, ensure_ascii=False, indent=0) + "\n")
    (HERE / "en_names.json").write_text(json.dumps(en_names, ensure_ascii=False, indent=0) + "\n")
    n_target = len(targets[:N_EN_MACHINE])
    print(f"ok: {len(en_slugs)}/{n_target} entries "
          f"(手書き{N_EN} + 機械{len(en_slugs) - N_EN}) -> en_slugs.json")
    print(f"不採用 {len(skipped)}件:")
    for slug, why in list(skipped.items())[:20]:
        print(f"  - {slug}: {why}")


if __name__ == "__main__":
    main()
