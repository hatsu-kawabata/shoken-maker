// 500mメッシュ(世界測地系)の座標計算と円内集計。純関数のみ(nodeテスト可能)。

export const DLAT = 15 / 3600;   // 500mメッシュの緯度幅
export const DLON = 22.5 / 3600; // 500mメッシュの経度幅

// 9桁メッシュコード → セル中心 [lat, lon]
export function meshCentroid(code) {
  const p = +code.slice(0, 2), q = +code.slice(2, 4);
  const a = +code[4], b = +code[5], c = +code[6], d = +code[7], m = +code[8];
  let lat = p / 1.5 + a * (5 / 60) + c * (1 / 120);
  let lon = 100 + q + b * (7.5 / 60) + d * (1 / 80);
  if (m === 3 || m === 4) lat += DLAT;
  if (m === 2 || m === 4) lon += DLON;
  return [lat + DLAT / 2, lon + DLON / 2];
}

// bboxに掛かる1次メッシュコード一覧
export function primaryMeshesInBBox(latMin, latMax, lonMin, lonMax) {
  const out = [];
  for (let p = Math.floor(latMin * 1.5); p <= Math.floor(latMax * 1.5); p++) {
    for (let q = Math.floor(lonMin) - 100; q <= Math.floor(lonMax) - 100; q++) {
      out.push(`${p}${String(q).padStart(2, "0")}`);
    }
  }
  return out;
}

// 円のbbox [latMin, latMax, lonMin, lonMax]（セル半対角のマージン付き）
export function circleBBox(lat, lon, r) {
  const margin = 400; // m: セル中心がbbox外でもサブ点が円に入る余地
  const dLat = (r + margin) / 110946;
  const dLon = (r + margin) / (111320 * Math.cos((lat * Math.PI) / 180));
  return [lat - dLat, lat + dLat, lon - dLon, lon + dLon];
}

export const N_BANDS = 20;

// cells: [{la, lo, v}] (v = [総数,男,女,世帯,平均年齢, b0m,b0f,...,b19m,b19f])
// 2x2サブ点でセルの円内含有率を近似して重み付き合計する
export function aggregateCircle(cells, clat, clon, r) {
  const kx = 111320 * Math.cos((clat * Math.PI) / 180);
  const ky = 110946;
  const r2 = r * r;
  const oLat = DLAT / 4, oLon = DLON / 4;
  const nv = 5 + 2 * N_BANDS;
  const sum = new Array(nv).fill(0);
  let cellCount = 0, maskedPop = 0;
  let ageNum = 0, ageDen = 0;
  for (const c of cells) {
    let inside = 0;
    for (const sy of [-oLat, oLat]) {
      for (const sx of [-oLon, oLon]) {
        const dx = (c.lo + sx - clon) * kx;
        const dy = (c.la + sy - clat) * ky;
        if (dx * dx + dy * dy <= r2) inside++;
      }
    }
    if (inside === 0) continue;
    const w = inside / 4;
    cellCount++;
    for (let i = 0; i < nv; i++) {
      if (i !== 4 && c.v[i] != null) sum[i] += c.v[i] * w;
    }
    if (c.v[4] != null && c.v[0] != null) {
      ageNum += c.v[4] * c.v[0] * w;
      ageDen += c.v[0] * w;
    }
    if (c.v[0] != null && c.v[5] == null) maskedPop += c.v[0] * w;
  }
  const bands = [];
  for (let i = 0; i < N_BANDS; i++) {
    bands.push({ m: Math.round(sum[5 + 2 * i]), f: Math.round(sum[6 + 2 * i]) });
  }
  return {
    pop: Math.round(sum[0]),
    male: Math.round(sum[1]),
    female: Math.round(sum[2]),
    hh: Math.round(sum[3]),
    meanAge: ageDen > 0 ? ageNum / ageDen : null,
    bands,
    cellCount,
    maskedPop: Math.round(maskedPop),
  };
}

// バンド範囲和(総数)。from/toはバンドindex(含む)
export function bandSum(bands, from, to) {
  let s = 0;
  for (let i = from; i <= to; i++) s += bands[i].m + bands[i].f;
  return s;
}
