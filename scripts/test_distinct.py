"""python3 scripts/test_distinct.py — distinct.py の純関数チェック。

docs/spec_index_yield_v0.md の操作的証人を機械で確かめる:
特徴文がコーパス統計からのみ導かれ、互いに一意で、数値が再計算と一致すること。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from distinct import (AGE_DEV_MIN, corpus_stats, features_en, features_ja,  # noqa: E402
                      hh_size, is_distinctive, rank_phrase, title_suffix_ja,
                      work_ratio)

fails = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global fails
    print(f"{'ok ' if cond else 'NG '} {name}{'  ' + detail if detail else ''}")
    if not cond:
        fails += 1


def rec(slug, pop, hh, age, senior, emp=None):
    # emp 既定は常住人口の0.4倍＝平凡な住宅地。職住比の中央値をここに寄せる
    return {"slug": slug, "pop": pop, "hh": hh, "mean_age": age, "senior_pct": senior,
            "emp": int(pop * 0.4) if emp is None else emp}


# 分位ルール(上位/下位5%)を踏むには母数が要るので、平凡な98駅＋両端の外れ値2駅で組む。
# 65歳以上比率は実コーパス同様に連続値にする(同値だらけにすると分位判定が退化して、
# 平凡な駅まで『全国上位5%』を名乗ってしまう。値ベース判定に変えた理由でもある)。
# 人口と65歳以上比率は実際には相関しきらないので、添字をずらして無相関にしておく
# (相関させると『人口1位かつ高齢化率最低』のような、片方の規則がもう片方を隠す駅ができる)
PLAIN = [rec(f"p{i:02d}", 90000 - i * 500, (90000 - i * 500) // 2, 45.0,
             20.0 + ((i * 37 + 41) % 98) * 0.04)
         for i in range(98)]
OLD = rec("old", 10000, 5000, 58.0, 46.0)     # 高齢・世帯人員2.00
YOUNG = rec("young", 1000, 400, 30.0, 2.0)    # 若年・人口最少・世帯人員2.50
OFFICE = rec("office", 5000, 3000, 44.0, 21.0, emp=400000)   # 職住分離の極
BEDTOWN = rec("bed", 40000, 16000, 44.5, 21.5, emp=2000)      # 住宅地型の極
CORPUS = PLAIN + [OLD, YOUNG, OFFICE, BEDTOWN]
S = corpus_stats(CORPUS)

# 1. 順位が降順で振られる
check("人口1位は最大の駅", S["rank_pop"]["p00"] == 1 and S["rank_pop"]["young"] == 102,
      f'p00={S["rank_pop"]["p00"]} young={S["rank_pop"]["young"]}')
check("65歳以上1位は最も高い駅",
      S["rank_senior"]["old"] == 1 and S["rank_senior"]["young"] == 102)

# 2. 中央値
check("平均年齢の中央値", abs(S["median_age"] - 45.0) < 1e-9, f'{S["median_age"]}')
check("世帯人員の中央値", abs(S["median_hhsize"] - 2.0) < 0.01, f'{S["median_hhsize"]:.3f}')

# 3. 順位の言い換え(設計時に踏んだバグの固定): 下位側を「上位98%」と書かない
side_hi, pct_hi = rank_phrase(1, 100)
side_lo, pct_lo = rank_phrase(98, 100)
check("上位側は『上位』", side_hi == "上位" and abs(pct_hi - 1.0) < 1e-9, f"{side_hi}{pct_hi:.0f}%")
check("下位側は『下位』", side_lo == "下位" and abs(pct_lo - 3.0) < 1e-9, f"{side_lo}{pct_lo:.0f}%")
check("境界(ちょうど半分)は上位", rank_phrase(50, 100)[0] == "上位")

# 4. 特徴文の中身
f_old = features_ja(OLD, S, [])
check("高齢の駅に65歳以上・上位5%の文が立つ",
      any("65歳以上の比率は全国上位5%" in x for x in f_old), " / ".join(f_old))
check("中央値より高い側は『高い』と書く", any("13.0歳高い" in x for x in f_old))
f_young = features_ja(YOUNG, S, [])
check("若年の駅に下位5%の文が立つ", any("全国下位5%" in x for x in f_young), " / ".join(f_young))
check("中央値より低い側は『低い』と書く", any("15.0歳低い" in x for x in f_young))
check("世帯人員が離れていれば書く",
      any("家族世帯の比重が高い" in x for x in f_young))

# 5. 乖離が閾値未満なら年齢の文は立たない(境界の作り込み)
borderline = rec("edge", 5000, 2500, 45.0 + AGE_DEV_MIN - 0.01, 22.0)
S2 = corpus_stats(PLAIN + [borderline])
check("閾値未満では年齢の特徴文を出さない",
      not any("平均年齢は全国中央値より" in x for x in features_ja(borderline, S2, [])))

# 6. 近隣比較
near = [PLAIN[1], PLAIN[2]]
check("近隣で最多なら『最も多い』",
      any("最も多い駅" in x for x in features_ja(PLAIN[0], S, near)))
check("近隣で最少なら『最も少ない』",
      any("最も少ない駅" in x for x in features_ja(YOUNG, S, near)))
check("中位なら近隣の文は立たない",
      not any("近隣" in x for x in features_ja(PLAIN[2], S, [PLAIN[1], PLAIN[3]])))

# 7. distinctive の定義: 順位文だけの駅は偽
plain = features_ja(PLAIN[40], S, [])
check("順位文だけなら distinctive でない", not is_distinctive(plain), " / ".join(plain))
check("特徴が立てば distinctive", is_distinctive(f_old))

# 8. 事実性: 文中の数値が再計算と一致する
check("世帯人員は pop/hh", abs(hh_size(YOUNG) - 2.5) < 1e-9)

# 9. タイトル補助は強い順に1つだけ
t = title_suffix_ja(OLD, S)
check("タイトルは最も強い特徴を1つだけ返す", t.count("—") == 1 and "65歳以上" in t, t)
check("平凡な駅のタイトルは空", title_suffix_ja(PLAIN[40], S) == "",
      repr(title_suffix_ja(PLAIN[40], S)))
check("人口上位はタイトルに出る", "全国1位" in title_suffix_ja(PLAIN[0], S),
      title_suffix_ja(PLAIN[0], S))

# 10. 英語面も同じ計算を共有し、同じ本数の文が立つ
check("日英で立つ特徴文の本数が一致",
      len(features_ja(OLD, S, near)) == len(features_en(OLD, S, near)))
check("英語の順位表現", "of 102 stations nationwide" in features_en(PLAIN[0], S, [])[0],
      features_en(PLAIN[0], S, [])[0])

# 11. 職住比(施策3): 昼間人口はメッシュ統計に無いので従業者数で代用している軸
check("職住比は emp/pop", abs(work_ratio(OFFICE) - 80.0) < 1e-9, f"{work_ratio(OFFICE)}")
f_off = features_ja(OFFICE, S, [])
check("職住分離が強い駅に『職住分離』の文が立つ",
      any("職住分離が強い" in x for x in f_off), " / ".join(f_off))
f_bed = features_ja(BEDTOWN, S, [])
check("住宅地型の駅に『住宅地型』の文が立つ",
      any("住宅地型" in x for x in f_bed), " / ".join(f_bed))
check("平凡な駅には職住比の文が立たない",
      not any("職住分離" in x or "住宅地型" in x for x in features_ja(PLAIN[40], S, [])))
check("emp が無ければ職住比の文は出ない",
      not any("働く人" in x for x in features_ja(
          {**PLAIN[40], "emp": 0}, S, [])))
check("英語面にも職住比が出る",
      any("work-oriented" in x for x in features_en(OFFICE, S, [])),
      " / ".join(features_en(OFFICE, S, [])[-1:]))

# 12. 一意性: 順位が違えば文が分かれる(平凡な駅同士でも順位文で割れる)
sigs = {tuple(features_ja(r, S, [])) for r in CORPUS}
check("全駅の特徴文セットが互いに一意", len(sigs) == len(CORPUS), f"{len(sigs)}/{len(CORPUS)}")

print(f"\n{'FAILED' if fails else 'all passed'}: {fails} failure(s)")
sys.exit(1 if fails else 0)
