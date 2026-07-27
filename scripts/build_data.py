#!/usr/bin/env python3
"""raw/ の e-Stat 500mメッシュzipを前集計し web/data/{1次メッシュ}.json を生成する。

入力(1次メッシュごと):
  T001141_{code}.zip — 2020国調その1: 総数・男女・世帯総数
  T001192_{code}.zip — 2020国調5歳階級: 20階級(0-4..95+)×男女・平均年齢(無ければnull埋め)

測地系は両方とも世界測地系JGD2011で揃えること。e-Statは同一調査・同一解像度でも
JGD2000版とJGD2011版を並存させており、混ぜると同じメッシュコードがわずかに違う領域を指す。
(2026-07-27まで5歳階級側にJGD2000版のT001173を使っており、T001141=JGD2011と混在していた)

出力フォーマット(1行1セル、サイズ最小化のため配列):
  [KEY_CODE(9桁文字列), 総数, 男, 女, 世帯総数, 平均年齢, b0m, b0f, ..., b19m, b19f]
  バンドは 0-4,5-9,...,90-94,95+ の20階級×(男,女)=40値。
緯度経度はメッシュコードからクライアント側で導出するため持たない。
秘匿セル("*")は null: 総数は原則開示されるが内訳が秘匿の場合がある。
合算セルの内訳は合算先メッシュに含まれる(円境界付近で僅かな誤差要因)。
"""
import csv
import io
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
OUT = ROOT / "web" / "data"

N_BANDS = 20


def val(s: str):
    try:
        return int(s.strip())
    except ValueError:  # "*"(秘匿) "-" "Y"(非公表) 空欄など
        return None


def fval(s: str):
    try:
        return float(s.strip())
    except ValueError:
        return None


def read_zip(zp: Path) -> list[list[str]]:
    with zipfile.ZipFile(zp) as z:
        name = next(n for n in z.namelist() if n.endswith(".txt"))
        text = z.read(name).decode("cp932")
    rows = list(csv.reader(io.StringIO(text)))[2:]
    return [r for r in rows if r and r[0].strip()]


def build(code1: str) -> int:
    # T001141: col4=総数 5=男 6=女 37=世帯総数
    base = {r[0]: [val(r[i]) if i < len(r) else None for i in (4, 5, 6, 37)]
            for r in read_zip(RAW / f"T001141_{code1}.zip")}
    # T001192: col4-6=総数(検算用) 7+3i/8+3i/9+3i=バンドi総/男/女 67=平均年齢
    ages: dict[str, list] = {}
    age_zip = RAW / f"T001192_{code1}.zip"
    if age_zip.exists():
        for r in read_zip(age_zip):
            bands = []
            for i in range(N_BANDS):
                bands += [val(r[8 + 3 * i]) if 8 + 3 * i < len(r) else None,
                          val(r[9 + 3 * i]) if 9 + 3 * i < len(r) else None]
            ages[r[0]] = [fval(r[67]) if len(r) > 67 else None] + bands

    empty_age = [None] * (1 + 2 * N_BANDS)
    rows = []
    for key in base.keys() | ages.keys():
        b = base.get(key)
        a = ages.get(key, empty_age)
        if b is None:
            # 年齢側にしかないセル: 総数をバンド和で補完
            band_vals = [x for x in a[1:] if x is not None]
            b = [sum(band_vals) if band_vals else None, None, None, None]
        rows.append([key] + b + a)
    rows.sort(key=lambda r: r[0])

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{code1}.json").write_text(
        json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    )
    return len(rows)


def main() -> None:
    codes = sorted(zp.name[len("T001141_"):-len(".zip")] for zp in RAW.glob("T001141_*.zip"))
    n_ages = 0
    for code1 in codes:
        n = build(code1)
        has_age = (RAW / f"T001192_{code1}.zip").exists()
        n_ages += has_age
        print(f"{code1}: {n} cells{'' if has_age else ' (年齢詳細なし)'}")
    manifest = {
        "format": 2,
        "source": "2020年国勢調査(e-Stat 統計GIS) T001141+T001192 (ともにJGD2011)",
        "bands": ["0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39",
                  "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70-74",
                  "75-79", "80-84", "85-89", "90-94", "95+"],
        "meshes": codes,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"manifest: {len(codes)} meshes (うち年齢詳細あり {n_ages})")


if __name__ == "__main__":
    main()
