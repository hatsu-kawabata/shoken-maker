// node scripts/test_mesh.mjs — mesh.jsの座標計算と円内集計の妥当性チェック
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { meshCentroid, primaryMeshesInBBox, circleBBox, aggregateCircle, bandSum, DLAT, DLON, N_BANDS } from "../web/mesh.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
let fails = 0;
const check = (name, cond, detail = "") => {
  console.log(`${cond ? "ok " : "NG "} ${name}${detail ? "  " + detail : ""}`);
  if (!cond) fails++;
};

// 1. メッシュコード→座標: 1次メッシュ5339のSW隅は lat=35.3333, lon=139
{
  const [la, lo] = meshCentroid("533900001");
  check("5339のSW端セル中心", Math.abs(la - (53 / 1.5 + DLAT / 2)) < 1e-9 && Math.abs(lo - (139 + DLON / 2)) < 1e-9,
    `(${la.toFixed(5)}, ${lo.toFixed(5)})`);
}
// 2. 500m四分位オフセット: m=4はm=1からDLAT,DLONずれる
{
  const [la1, lo1] = meshCentroid("533945001");
  const [la4, lo4] = meshCentroid("533945004");
  check("500m四分位(m=4)", Math.abs(la4 - la1 - DLAT) < 1e-9 && Math.abs(lo4 - lo1 - DLON) < 1e-9);
}
// 3. 逆写像: 皇居(35.685,139.753)は1次メッシュ5339
{
  const codes = primaryMeshesInBBox(35.685, 35.685, 139.753, 139.753);
  check("皇居→5339", codes.length === 1 && codes[0] === "5339", codes.join(","));
}
// 4. bboxが1次メッシュ境界(lat=36.0)を跨ぐと5339と5439の両方が出る
{
  const [latMin, latMax, lonMin, lonMax] = circleBBox(35.999, 139.5, 2000);
  const codes = primaryMeshesInBBox(latMin, latMax, lonMin, lonMax);
  check("境界跨ぎで2メッシュ", codes.includes("5339") && codes.includes("5439"), codes.join(","));
}

// 5. 実データ集計の妥当性
const load = (c) =>
  JSON.parse(readFileSync(join(ROOT, "web", "data", `${c}.json`), "utf8")).map((r) => {
    const [la, lo] = meshCentroid(r[0]);
    return { la, lo, v: r.slice(1) };
  });
const cells5339 = load("5339");

// 新宿駅1km圏: 昼間人口でなく夜間(常住)人口なので 2〜8万人程度が妥当域
{
  const a = aggregateCircle(cells5339, 35.690, 139.700, 1000);
  check("新宿駅1km圏 常住人口", a.pop > 20000 && a.pop < 80000, `${a.pop}人 / ${a.cellCount}セル`);
  check("新宿 男+女≒総数", Math.abs(a.pop - (a.male + a.female)) / a.pop < 0.02,
    `総数${a.pop} 男+女${a.male + a.female}`);
  // 都心は年齢不詳率が高い(新宿1km圏で実測15%)。バンド和は総数の75〜100%が妥当域
  const bandsTotal = bandSum(a.bands, 0, N_BANDS - 1);
  check("新宿 バンド和が総数の75〜100%", bandsTotal > a.pop * 0.75 && bandsTotal <= a.pop * 1.001,
    `バンド和${bandsTotal} 総数${a.pop} (${(bandsTotal / a.pop * 100).toFixed(1)}%)`);
  check("新宿 平均年齢が妥当域", a.meanAge != null && a.meanAge > 30 && a.meanAge < 60,
    `${a.meanAge?.toFixed(1)}歳`);
  const a20s = bandSum(a.bands, 4, 5), a70s = bandSum(a.bands, 14, 15);
  check("新宿 20代>70代(都心の年齢構造)", a20s > a70s, `20代${a20s} 70代${a70s}`);
}
// 皇居中心500m圏: ほぼ無人(数百人以下)
{
  const a = aggregateCircle(cells5339, 35.6825, 139.7530, 500);
  check("皇居500m圏はほぼ無人", a.pop < 500, `${a.pop}人`);
}
// 半径単調性: 同一中心で半径を増やすと人口は非減少
{
  const p1 = aggregateCircle(cells5339, 35.690, 139.700, 800).pop;
  const p2 = aggregateCircle(cells5339, 35.690, 139.700, 1600).pop;
  const p3 = aggregateCircle(cells5339, 35.690, 139.700, 3200).pop;
  check("半径単調性", p1 <= p2 && p2 <= p3, `${p1} ≤ ${p2} ≤ ${p3}`);
}
// 全域の内部整合: 男+女≒総数
{
  let t = 0, m = 0, f = 0;
  for (const c of cells5339) {
    if (c.v[0] != null) t += c.v[0];
    if (c.v[1] != null) m += c.v[1];
    if (c.v[2] != null) f += c.v[2];
  }
  check("5339全域 男+女≒総数", Math.abs(t - (m + f)) / t < 0.01, `総数${t} 男+女${m + f}`);
  let band = 0;
  for (const c of cells5339) {
    for (let i = 5; i < 5 + 2 * N_BANDS; i++) if (c.v[i] != null) band += c.v[i];
  }
  check("5339全域 バンド和が総数の95%以上(不詳2.9%を許容)", band > t * 0.95 && band <= t * 1.001,
    `${(band / t * 100).toFixed(2)}%`);
  console.log(`   (参考: 1次メッシュ5339の常住人口合計 = ${t.toLocaleString()}人)`);
}
// 年齢詳細がnullのセル(秘匿・T001173未整備)でも落ちない — 合成データで恒久的に検証
{
  const [la, lo] = meshCentroid("533945004");
  const v = [100, 50, 50, 40, null, ...new Array(2 * N_BANDS).fill(null)];
  const a = aggregateCircle([{ la, lo, v }], la, lo, 800);
  check("年齢詳細nullセルでも集計可", a.pop === 100 && a.meanAge === null && bandSum(a.bands, 0, N_BANDS - 1) === 0,
    `pop=${a.pop} meanAge=${a.meanAge}`);
}
// 全国カバレッジ: 札幌駅1km圏・那覇市中心1km圏が妥当な人口を返す
{
  const sap = aggregateCircle(load("6441"), 43.0687, 141.3508, 1000);
  check("札幌駅1km圏", sap.pop > 15000 && sap.pop < 120000, `${sap.pop}人 平均${sap.meanAge?.toFixed(1)}歳`);
  const naha = aggregateCircle(load("3927"), 26.2124, 127.6809, 1000);
  check("那覇市中心1km圏", naha.pop > 10000 && naha.pop < 100000, `${naha.pop}人 平均${naha.meanAge?.toFixed(1)}歳`);
}

process.exit(fails ? 1 : 0);
