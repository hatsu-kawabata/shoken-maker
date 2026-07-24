#!/usr/bin/env python3
"""e-Stat 統計GIS から 2020年国勢調査 500mメッシュ(その1 人口等基本集計)を取得する。

出典: 政府統計の総合窓口(e-Stat) 統計GIS https://www.e-stat.go.jp/gis
statsId T001141 = 2020年国勢調査 500mメッシュ その1(人口等基本集計に関する事項)

使い方:
  python3 scripts/fetch_mesh.py            # 関東プリセット
  python3 scripts/fetch_mesh.py 5235 5236  # 1次メッシュコード指定
  python3 scripts/fetch_mesh.py --sweep    # 全国スイープ(日本の可住域を覆う1次メッシュ格子を
                                           # 総当たりし、データが存在するものだけ保存)
"""
import sys
import time
import urllib.request
from pathlib import Path

import os

# T001141=2020国調その1(総数・世帯) / T001173=2020国調5歳階級(500m) / T001177=2015国調5歳階級(500m)
STATS_ID = os.environ.get("STATS_ID", "T001141")
URL = "https://www.e-stat.go.jp/gis/statmap-search/data?statsId={sid}&code={code}&downloadType=2"
RAW = Path(__file__).resolve().parent.parent / "raw"

KANTO = ["5339", "5239", "5340", "5240", "5439", "5440", "5338"]


def fetch(code: str) -> bool:
    dst = RAW / f"{STATS_ID}_{code}.zip"
    if dst.exists() and dst.stat().st_size > 1000:
        print(f"{code}: cached")
        return True
    req = urllib.request.Request(
        URL.format(sid=STATS_ID, code=code),
        headers={"User-Agent": "shoken-maker/0.1 (personal research)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = r.read()
    except Exception as e:
        print(f"{code}: ERROR {e}")
        return False
    if not body.startswith(b"PK"):
        print(f"{code}: no data (not a zip, {len(body)} bytes)")
        return False
    dst.write_bytes(body)
    print(f"{code}: {len(body)} bytes")
    return True


def sweep_codes() -> list[str]:
    """日本の可住域(与那国24.4N/122.9E〜北海道45.5N/148E台)を覆う1次メッシュ格子。
    p=緯度×1.5の整数部(36..68)、q=経度-100(22..46)。海上のみの区画はe-Stat側に
    データが無くスキップされるので、格子は広めで害がない。"""
    return [f"{p}{q:02d}" for p in range(36, 69) for q in range(22, 47)]


def main() -> None:
    if sys.argv[1:] == ["--sweep"]:
        codes = sweep_codes()
    else:
        codes = sys.argv[1:] or KANTO
    RAW.mkdir(exist_ok=True)
    ok = 0
    for i, code in enumerate(codes):
        if fetch(code):
            ok += 1
        if i < len(codes) - 1:
            time.sleep(0.8)  # e-Statへの負荷配慮
    print(f"done: {ok}/{len(codes)}")


if __name__ == "__main__":
    main()
