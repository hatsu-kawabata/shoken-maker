#!/usr/bin/env python3
"""raw/T001163_{1次メッシュ}.zip から「そのメッシュで働く人の数」を前集計する。

なぜこれを作るか(docs/spec_index_yield_v0.md 施策3):
駅ページの数字は常住(夜間)人口だけで、新宿駅の半径1km人口が全国1,334位という、
出店判断としては明らかに足りない絵になっていた。昼と夜の差を入れたい。

**昼間人口そのものは地域メッシュ統計に存在しない**(2026-07-29 定義書で実測):
国勢調査メッシュ 別表02(T001143)の「従業地・通学地」は
「当地に**常住する**15歳以上就業者・通学者」＝居住地ベースで、
そこへ通勤してくる人の数ではない。市区町村・小地域には昼間人口があるが、
メッシュには無い。

そこで従業者数(令和3年経済センサス-活動調査, T001163001=A〜S全産業)を使う。
これは「そこに勤め先がある人の数」で、昼間人口の全部ではない(買い物客・通学者・
観光客を含まない)が、職住分離を測るには十分に効く。ページでは昼間人口と呼ばず
「そこで働く人」と書くこと。

入力: raw/T001163_{code}.zip（compete_checker と同一ファイル。無ければ
      STATS_ID=T001163 python3 scripts/fetch_mesh.py --sweep で取得できる）
出力: data_emp/{1次メッシュ}.json = {メッシュコード9桁: 従業者数}
      web/ の外に置く: 生成にしか使わないので本番バンドルに載せる必要がない
"""
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
OUT = ROOT / "data_emp"
STATS_ID = "T001163"
# A〜S全産業。1回目の出現が事業所数、2回目が従業者数(総数)
COL_ALL = "T001163001"


def read_emp(code1: str) -> dict[str, int]:
    zp = RAW / f"{STATS_ID}_{code1}.zip"
    if not zp.exists():
        return {}
    with zipfile.ZipFile(zp) as z:
        text = z.open(z.namelist()[0]).read().decode("cp932", "replace")
    lines = text.splitlines()
    codes = lines[0].split(",")
    labels = [s.strip() for s in lines[1].split(",")]
    i = codes.index(COL_ALL)
    occ = [j for j, lb in enumerate(labels) if j > 0 and lb == labels[i]]
    if len(occ) < 2:
        raise SystemExit(f"{code1}: 従業者数列が見つからない (occ={occ})")
    emp_i = occ[1]

    out = {}
    for line in lines[2:]:
        if not line.strip():
            continue
        p = line.split(",")
        if emp_i >= len(p):
            continue
        try:
            v = int(p[emp_i].strip())
        except ValueError:  # "*"(秘匿) "-" 空欄
            continue
        if v:
            out[p[0].strip()] = v
    return out


def main() -> None:
    OUT.mkdir(exist_ok=True)
    codes = sorted(zp.name[len(f"{STATS_ID}_"):-len(".zip")]
                   for zp in RAW.glob(f"{STATS_ID}_*.zip"))
    total_cells = total_emp = 0
    for code1 in codes:
        d = read_emp(code1)
        if not d:
            continue
        (OUT / f"{code1}.json").write_text(json.dumps(d, separators=(",", ":")))
        total_cells += len(d)
        total_emp += sum(d.values())
    # 検算(2026-07-29 実測): 合計 62,427,891人。公表の「民営事業所の従業者数」約5,795万人
    # との差 約450万人は国・地方公共団体分で、T001163001=Ａ〜Ｓ全産業が公務を含むため。
    # 同じ読み方で T001163002(Ｃ〜Ｅ第２次産業)=12,561,357人 も公表値と整合したので、
    # 「同じラベルの2回目の出現＝従業者数」という列の当て方は正しいと確認できている
    print(f"{len(codes)} 区画 / {total_cells:,} メッシュ / 従業者数合計 {total_emp:,}人")


if __name__ == "__main__":
    main()
