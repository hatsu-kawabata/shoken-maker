"""駅ページの「特徴文」を作る純関数群。

なぜこれが要るか: 生成ページの本文はe-Statの数字の転記だけで、1,992枚が同型の鋳型だった。
任意の1枚が他の1枚でも汎用LLMの回答でも置換可能な状態で、Googleは実際に
「クロール済み - インデックス未登録」を返している(2026-07-29実測 3/61)。

ここで作るのは **コーパス全体を持たないと書けない文** だけ。順位・中央値からの乖離・
近隣比較は、1駅分のデータからは絶対に書けず、全駅を集計して初めて出る。
docs/spec_index_yield_v0.md の操作的証人:

    distinctive(page) ⇔ 順位以外の特徴文が1本以上ある

順位文は全駅に必ず立つので、これを数に入れると条件が空虚になる。「その駅が何かの点で
平凡でない」ことを要求するために、順位文は distinctive の判定から除く。

すべて純関数。入出力はプレーンなdict/listで、I/Oも乱数も時計も持たない。
"""

# 全国中央値からこれ以上離れたら「特徴」として書く(歳)
AGE_DEV_MIN = 2.0
# タイトルに出すのはこれ以上離れた駅だけ(歳)。本文より厳しくする
AGE_DEV_TITLE = 5.0
# 上位/下位◯%を「際立つ」とみなす境界
EXTREME_Q = 0.05
# 世帯あたり人員が全国中央値からこれ以上離れたら書く(人)
HHSIZE_DEV_MIN = 0.25
# 人口の多さをタイトルに出す上限順位。母数が小さいコーパスでも
# 「全国◯位」が安売りにならないよう、分位(EXTREME_Q)との小さい方を採る
TOP_POP_TITLE = 50
# 職住比が全国中央値のこの倍率以下なら「住宅地型」と書く
WORK_LOW_FACTOR = 0.5
# 「職住分離が強い」は分位を超えるだけでなく中央値のこの倍率以上であることも要る。
# 分位だけだと、値が同じ駅ばかりの退化した分布で分位＝中央値になり、
# 平凡な駅まで「職住分離が強い」を名乗ってしまう(テストで踏んだ)
WORK_HIGH_FACTOR = 1.5


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if not n:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def hh_size(rec: dict) -> float:
    """世帯あたり人員。単身が多い都心と家族世帯が多い郊外を分ける軸。"""
    return rec["pop"] / rec["hh"] if rec.get("hh") else 0.0


def work_ratio(rec: dict) -> float:
    """そこで働く人 ÷ そこに住む人。職住分離の度合い。

    昼間人口ではない(買い物客・通学者・観光客を含まない)。地域メッシュ統計に
    昼間人口は存在せず、代わりに経済センサスの従業者数を使っている。
    常住人口だけを見ていると新宿駅の商圏が全国1,334位に見える穴を埋めるための軸。
    """
    return rec["emp"] / rec["pop"] if rec.get("emp") and rec.get("pop") else 0.0


def corpus_stats(records: list[dict]) -> dict:
    """全駅を1度だけ走査して、順位表と中央値を作る。

    records の各要素は {"slug", "pop", "hh", "mean_age", "senior_pct"}。
    順位は降順(1位=最大)で、同値は先に現れた方を上にする(安定ソート)。
    """
    n = len(records)
    by_pop = sorted(records, key=lambda r: -r["pop"])
    by_senior = sorted(records, key=lambda r: -r["senior_pct"])
    seniors = sorted(r["senior_pct"] for r in records)
    works = [work_ratio(r) for r in records if work_ratio(r)]
    return {
        "n": n,
        "rank_pop": {r["slug"]: i + 1 for i, r in enumerate(by_pop)},
        "rank_senior": {r["slug"]: i + 1 for i, r in enumerate(by_senior)},
        "median_age": _median([r["mean_age"] for r in records if r["mean_age"]]),
        "median_hhsize": _median([hh_size(r) for r in records if r.get("hh")]),
        # 「上位5%」は順位でなく値の分位で判定する。同値の駅が並ぶと順位は任意に決まり、
        # 2位と50位に意味の差がなくなるため(テストで踏んだ)。値で切れば主張が事実に一致する
        "senior_hi": _quantile(seniors, 1 - EXTREME_Q),
        "senior_lo": _quantile(seniors, EXTREME_Q),
        "median_workratio": _median(works) if works else 0.0,
        "work_hi": _quantile(sorted(works), 1 - EXTREME_Q) if works else 0.0,
        "rank_work": {r["slug"]: i + 1 for i, r in enumerate(
            sorted(records, key=lambda r: -work_ratio(r)))},
    }


def _quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    i = min(len(sorted_values) - 1, max(0, int(round(q * (len(sorted_values) - 1)))))
    return sorted_values[i]


def is_senior_high(rec: dict, stats: dict) -> bool:
    return bool(stats["senior_hi"]) and rec["senior_pct"] >= stats["senior_hi"]


def is_senior_low(rec: dict, stats: dict) -> bool:
    return rec["senior_pct"] <= stats["senior_lo"]


def rank_phrase(rank: int, n: int) -> tuple[str, float]:
    """順位を『上位X%』『下位Y%』のどちらで言うかを決める。

    降順の順位をそのまま『上位X%』と書くと、最下位付近の駅が『上位98%』という
    意味の通らない文になる(設計時のプロトタイプで実際に踏んだ)。半分を境に言い換える。
    """
    if rank <= n / 2:
        return "上位", max(rank / n * 100, 0.1)
    return "下位", max((n - rank + 1) / n * 100, 0.1)


def rank_phrase_en(rank: int, n: int) -> tuple[str, float]:
    if rank <= n / 2:
        return "top", max(rank / n * 100, 0.1)
    return "bottom", max((n - rank + 1) / n * 100, 0.1)


def _age_dev(rec: dict, stats: dict) -> float:
    if not rec["mean_age"] or not stats["median_age"]:
        return 0.0
    return rec["mean_age"] - stats["median_age"]


def _neighbor_rank(rec: dict, neighbors: list[dict], key) -> tuple[int, int]:
    """近隣駅を含めた中での順位(1位=最大)と母数を返す。"""
    group = [rec] + list(neighbors)
    ordered = sorted(group, key=lambda r: -key(r))
    return ordered.index(rec) + 1, len(group)


def features_ja(rec: dict, stats: dict, neighbors: list[dict]) -> list[str]:
    """日本語の特徴文。先頭が順位文で、以降が distinctive の根拠になる。"""
    n = stats["n"]
    rp = stats["rank_pop"][rec["slug"]]
    side, pct = rank_phrase(rp, n)
    out = [f"半径1km圏の人口は全国{n:,}駅中 第{rp:,}位（{side}{pct:.0f}%）。"]

    dev = _age_dev(rec, stats)
    if abs(dev) >= AGE_DEV_MIN:
        out.append(
            f"平均年齢は全国中央値より{abs(dev):.1f}歳{'低い' if dev < 0 else '高い'}"
            f"（{rec['mean_age']:.1f}歳 / 中央値{stats['median_age']:.1f}歳）＝"
            f"{'若年層' if dev < 0 else '高齢層'}に厚い商圏です。"
        )

    rs = stats["rank_senior"][rec["slug"]]
    if is_senior_high(rec, stats):
        out.append(f"65歳以上の比率は全国上位5%（第{rs:,}位・{rec['senior_pct']:.1f}%）。")
    elif is_senior_low(rec, stats):
        out.append(
            f"65歳以上の比率は全国下位5%（第{rs:,}位・{rec['senior_pct']:.1f}%）＝"
            "現役世代が集中しています。"
        )

    if neighbors:
        nr, nn = _neighbor_rank(rec, neighbors, lambda r: r["pop"])
        if nr == 1:
            out.append(f"近隣{nn - 1}駅と比べると、半径1km圏の人口は最も多い駅です。")
        elif nr == nn:
            out.append(f"近隣{nn - 1}駅と比べると、半径1km圏の人口は最も少ない駅です。")

    hs, med_hs = hh_size(rec), stats["median_hhsize"]
    if hs and abs(hs - med_hs) >= HHSIZE_DEV_MIN:
        out.append(
            f"1世帯あたりの人員は{hs:.2f}人（全国中央値{med_hs:.2f}人）で、"
            f"{'単身世帯' if hs < med_hs else '家族世帯'}の比重が高い構成です。"
        )

    wr, med_wr = work_ratio(rec), stats["median_workratio"]
    if wr and med_wr:
        rw = stats["rank_work"][rec["slug"]]
        if wr >= max(stats["work_hi"], med_wr * WORK_HIGH_FACTOR):
            out.append(
                f"そこで働く人は住む人の{wr:.2f}倍（全国中央値{med_wr:.2f}倍・第{rw:,}位）で、"
                "職住分離が強い＝昼と夜で人の数が大きく変わる商圏です。"
            )
        elif wr <= med_wr * WORK_LOW_FACTOR:
            out.append(
                f"そこで働く人は住む人の{wr:.2f}倍（全国中央値{med_wr:.2f}倍）にとどまり、"
                "勤め先より住まいが多い住宅地型の商圏です。"
            )
    return out


def features_en(rec: dict, stats: dict, neighbors: list[dict]) -> list[str]:
    """英語面の特徴文。順位も数値も言語非依存なので同じ計算を共有する。"""
    n = stats["n"]
    rp = stats["rank_pop"][rec["slug"]]
    side, pct = rank_phrase_en(rp, n)
    out = [f"Its 1 km population ranks {rp:,} of {n:,} stations nationwide "
           f"({side} {pct:.0f}%)."]

    dev = _age_dev(rec, stats)
    if abs(dev) >= AGE_DEV_MIN:
        out.append(
            f"The average age is {abs(dev):.1f} years "
            f"{'below' if dev < 0 else 'above'} the national median "
            f"({rec['mean_age']:.1f} vs {stats['median_age']:.1f}), i.e. a trade area "
            f"weighted toward {'younger' if dev < 0 else 'older'} residents."
        )

    rs = stats["rank_senior"][rec["slug"]]
    if is_senior_high(rec, stats):
        out.append(f"The share of residents aged 65+ is in the national top 5% "
                   f"(rank {rs:,}, {rec['senior_pct']:.1f}%).")
    elif is_senior_low(rec, stats):
        out.append(f"The share of residents aged 65+ is in the national bottom 5% "
                   f"(rank {rs:,}, {rec['senior_pct']:.1f}%) — a working-age concentration.")

    if neighbors:
        nr, nn = _neighbor_rank(rec, neighbors, lambda r: r["pop"])
        if nr == 1:
            out.append(f"Among the {nn - 1} nearest stations it has the largest "
                       "1 km population.")
        elif nr == nn:
            out.append(f"Among the {nn - 1} nearest stations it has the smallest "
                       "1 km population.")

    hs, med_hs = hh_size(rec), stats["median_hhsize"]
    if hs and abs(hs - med_hs) >= HHSIZE_DEV_MIN:
        out.append(
            f"Average household size is {hs:.2f} (national median {med_hs:.2f}), "
            f"indicating a higher share of {'single-person' if hs < med_hs else 'family'} "
            "households."
        )

    wr, med_wr = work_ratio(rec), stats["median_workratio"]
    if wr and med_wr:
        rw = stats["rank_work"][rec["slug"]]
        if wr >= max(stats["work_hi"], med_wr * WORK_HIGH_FACTOR):
            out.append(
                f"There are {wr:.2f} times as many people working here as living here "
                f"(national median {med_wr:.2f}, rank {rw:,}) — a strongly "
                "work-oriented area where daytime and nighttime populations differ sharply."
            )
        elif wr <= med_wr * WORK_LOW_FACTOR:
            out.append(
                f"Only {wr:.2f} times as many people work here as live here "
                f"(national median {med_wr:.2f}), i.e. a primarily residential area."
            )
    return out


def is_distinctive(features: list[str]) -> bool:
    """順位文以外の特徴文が1本以上あるか。docs/spec_index_yield_v0.md の合格条件。"""
    return len(features) > 1


def title_suffix_ja(rec: dict, stats: dict) -> str:
    """タイトルに足す短い特徴。強い順に1つだけ採る(欲張ると事実性が落ちる)。"""
    n = stats["n"]
    rs = stats["rank_senior"][rec["slug"]]
    if is_senior_high(rec, stats):
        return f" — 65歳以上{rec['senior_pct']:.1f}%（全国{rs:,}位）"
    if is_senior_low(rec, stats):
        return f" — 65歳以上{rec['senior_pct']:.1f}%（全国{n - rs + 1:,}番目に低い）"
    dev = _age_dev(rec, stats)
    if abs(dev) >= AGE_DEV_TITLE:
        return f" — 平均年齢{rec['mean_age']:.1f}歳（全国中央値{stats['median_age']:.1f}歳）"
    rp = stats["rank_pop"][rec["slug"]]
    if rp <= min(TOP_POP_TITLE, n * EXTREME_Q):
        return f" — 1km圏{rec['pop']:,}人（全国{rp}位）"
    return ""


def title_suffix_en(rec: dict, stats: dict) -> str:
    n = stats["n"]
    rs = stats["rank_senior"][rec["slug"]]
    if is_senior_high(rec, stats):
        return f" — {rec['senior_pct']:.1f}% aged 65+ (rank {rs:,} nationwide)"
    if is_senior_low(rec, stats):
        return f" — {rec['senior_pct']:.1f}% aged 65+ ({n - rs + 1:,}th lowest nationwide)"
    dev = _age_dev(rec, stats)
    if abs(dev) >= AGE_DEV_TITLE:
        return f" — average age {rec['mean_age']:.1f} (national median {stats['median_age']:.1f})"
    rp = stats["rank_pop"][rec["slug"]]
    if rp <= min(TOP_POP_TITLE, n * EXTREME_Q):
        return f" — {rec['pop']:,} residents within 1 km (rank {rp} nationwide)"
    return ""
