// 業種ごとの「主な客層＝年齢階級の範囲」と注記。純関数のみ(nodeテスト可能)。
//
// 総人口だけでは出店判断に足りない。学習塾に必要なのは10代の数で、
// 介護に必要なのは75歳以上の数であって、どちらも総人口とは相関しない。
// 業種を選ぶと該当年齢層の実数が出る＝選ぶ理由がユーザー本人の側にある。
//
// バンドiは [5i, 5i+4] 歳（i=19 は95歳以上）。

export const INDUSTRIES = [
  { id: "", label: "（業種を選ぶと主な客層の人口が出ます）" },
  {
    id: "food", label: "飲食店", from: 4, to: 12, target: "20〜64歳",
    note: "飲食店は昼間の人口に強く依存します。ここに出るのは常住（夜間）人口なので、" +
      "オフィス街・駅前では実際の需要を大きく下回ります。",
  },
  {
    id: "cafe", label: "カフェ・喫茶", from: 4, to: 9, target: "20〜49歳",
    note: "滞在型の業態は昼間人口と回遊の影響が大きく、常住人口だけでは測れません。",
  },
  {
    id: "juku", label: "学習塾・進学塾", from: 2, to: 3, target: "10〜19歳",
    note: "通塾率は小学校高学年から上がり、中学生でおおむね最大になります。" +
      "0〜9歳が厚い地域は数年後に対象層が増えます。",
  },
  {
    id: "kids", label: "保育・幼児教育", from: 0, to: 0, target: "0〜4歳",
    note: "0〜4歳は5年で完全に入れ替わります。現在の実数より、" +
      "20〜39歳（親世代）の厚みの方が数年先を示します。",
  },
  {
    id: "beauty", label: "美容室・理容室", from: 3, to: 12, target: "15〜64歳",
    note: "来店頻度は女性の方が高い傾向があります。男女比も併せて見てください。",
  },
  {
    id: "clinic", label: "クリニック（内科等）", from: 13, to: 19, target: "65歳以上",
    note: "受診頻度は高齢層ほど高く、65歳以上は現役世代の数倍になります。" +
      "総人口が同じでも年齢構成で需要は大きく変わります。",
  },
  {
    id: "seikotsu", label: "整骨院・整体・鍼灸", from: 8, to: 15, target: "40〜79歳",
    note: "中高年層が中心です。通院は徒歩・自転車圏が多く、半径を小さめに見る方が実態に近くなります。",
  },
  {
    id: "kaigo", label: "介護・デイサービス", from: 15, to: 19, target: "75歳以上",
    note: "75歳以上は多くの地域で今後10年増加します。現在の実数は下限として見てください。",
  },
  {
    id: "fitness", label: "フィットネス・ジム", from: 4, to: 11, target: "20〜59歳",
    note: "継続利用は徒歩・自転車圏の比率が高く、半径1km以内の実数が効きます。",
  },
  {
    id: "grocery", label: "食品スーパー・コンビニ", from: 0, to: 19, target: "全年齢",
    note: "日用品は世帯単位で動くため、人口より世帯数の方が需要に近い指標です。",
  },
  {
    id: "realestate", label: "不動産（賃貸仲介）", from: 4, to: 7, target: "20〜39歳",
    note: "住み替えの中心層です。世帯数÷人口が小さいほど単身世帯が多く、回転も速くなります。",
  },
];

export function industryById(id) {
  return INDUSTRIES.find((i) => i.id === id) ?? INDUSTRIES[0];
}

// bands = [{m, f} × 20]。業種の対象年齢層の人口を返す。業種未選択なら null。
export function targetPopulation(bands, ind) {
  if (!ind || ind.from == null) return null;
  let s = 0;
  for (let i = ind.from; i <= ind.to; i++) s += bands[i].m + bands[i].f;
  return s;
}

// 対象層が総人口に占める割合(%)。総人口0なら null。
export function targetShare(target, total) {
  return total > 0 && target != null ? (target / total) * 100 : null;
}
