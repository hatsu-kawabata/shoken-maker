#!/usr/bin/env python3
"""上位200駅の日本語slug→ローマ字slug対応表(en_slugs.json)を検証付きで生成する。

対応表は手書き（駅名の読みは機械変換だと誤りが出るため）。gen_pages.pyの
slug割当と同じ順序・同名衝突規則を前提に、カバレッジと一意性を検証する。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
N_EN = 200

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


def top_slugs(n: int) -> list[str]:
    stations = json.loads((ROOT / "web" / "data" / "stations.json").read_text())
    slugs, used = {}, {}
    for i, s in enumerate(stations):
        k = used.get(s["n"], 0) + 1
        used[s["n"]] = k
        slugs[i] = s["n"] if k == 1 else f'{s["n"]}-{k}'
    idx = {id(s): i for i, s in enumerate(stations)}
    return [slugs[idx[id(s)]] for s in stations if s.get("p")][:n]


def main() -> None:
    targets = top_slugs(N_EN)
    missing = [s for s in targets if s not in EN]
    extra = [s for s in EN if s not in targets]
    dup = [v for v in EN.values() if list(EN.values()).count(v) > 1]
    bad = [v for v in EN.values() if not all(c.islower() or c.isdigit() or c == "-" for c in v)]
    assert not missing, f"対応表に不足: {missing}"
    assert not extra, f"対応表に余剰(top{N_EN}外): {extra}"
    assert not dup, f"ローマ字slug衝突: {sorted(set(dup))}"
    assert not bad, f"不正な文字: {bad}"
    out = ROOT / "scripts" / "en_slugs.json"
    out.write_text(json.dumps({s: EN[s] for s in targets}, ensure_ascii=False, indent=0) + "\n")
    print(f"ok: {len(targets)} entries -> {out}")


if __name__ == "__main__":
    main()
