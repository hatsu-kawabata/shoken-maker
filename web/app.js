import { meshCentroid, primaryMeshesInBBox, circleBBox, aggregateCircle, bandSum, N_BANDS } from "./mesh.js";

const map = L.map("map").setView([35.681, 139.767], 13);
L.tileLayer("https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png", {
  maxZoom: 18,
  attribution: '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank" rel="noopener">地理院タイル</a>',
}).addTo(map);

const els = {
  radius: document.getElementById("radius"),
  radiusOut: document.getElementById("radiusOut"),
  status: document.getElementById("status"),
  results: document.getElementById("results"),
  pop: document.getElementById("pop"),
  hh: document.getElementById("hh"),
  mf: document.getElementById("mf"),
  meanAge: document.getElementById("meanAge"),
  ageBars: document.getElementById("ageBars"),
  pyramid: document.getElementById("pyramid"),
  maskNote: document.getElementById("maskNote"),
  missingNote: document.getElementById("missingNote"),
  meta: document.getElementById("meta"),
};

let manifest = null;
const meshCache = new Map(); // code1 -> {cells} | "missing" | Promise
let center = null;
let circle = null;
let computeSeq = 0;

// URL共有: ?lat=..&lng=..&r=.. で状態を復元する
function applyUrlState() {
  const p = new URLSearchParams(location.search);
  const lat = parseFloat(p.get("lat")), lng = parseFloat(p.get("lng")), r = parseInt(p.get("r"), 10);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
  if (Number.isFinite(r) && r >= 300 && r <= 5000) {
    els.radius.value = r;
    els.radiusOut.textContent = `${(r / 1000).toFixed(1)} km`;
  }
  const ll = L.latLng(lat, lng);
  map.setView(ll, 14);
  setCenter(ll);
}

function syncUrl() {
  if (!center) return;
  const p = new URLSearchParams();
  p.set("lat", center.lat.toFixed(5));
  p.set("lng", center.lng.toFixed(5));
  p.set("r", els.radius.value);
  history.replaceState(null, "", `?${p}`);
}

fetch("data/manifest.json")
  .then((r) => r.json())
  .then((m) => { manifest = m; applyUrlState(); })
  .catch(() => { els.status.textContent = "manifest.json を読めません。build_data.py を実行してください"; });

async function loadMesh(code1) {
  if (meshCache.has(code1)) return meshCache.get(code1);
  const p = (async () => {
    if (manifest && !manifest.meshes.includes(code1)) return "missing";
    try {
      const rows = await (await fetch(`data/${code1}.json`)).json();
      const cells = rows.map((r) => {
        const [la, lo] = meshCentroid(r[0]);
        return { la, lo, v: r.slice(1) };
      });
      return { cells };
    } catch {
      return "missing";
    }
  })();
  meshCache.set(code1, p);
  const v = await p;
  meshCache.set(code1, v);
  return v;
}

const fmt = (n) => n.toLocaleString("ja-JP");

// 人口ピラミッド(5歳階級×男女)。横幅は「性別バンド人口/総人口」の%を左右対称スケールで描く
const BAND_LABELS = ["0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39",
  "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70-74", "75-79", "80-84",
  "85-89", "90-94", "95+"];

function renderPyramid(bands, total) {
  els.pyramid.replaceChildren();
  if (total <= 0) return;
  const maxPct = Math.max(
    0.1,
    ...bands.map((b) => Math.max(b.m, b.f) / total * 100),
  );
  for (let i = N_BANDS - 1; i >= 0; i--) {
    const { m, f } = bands[i];
    const pm = (m / total) * 100, pf = (f / total) * 100;
    const row = document.createElement("div");
    row.className = "pyr-row";
    row.title = `${BAND_LABELS[i]}歳: 男 ${fmt(m)}人 / 女 ${fmt(f)}人`;
    row.innerHTML = `
      <div class="pyr-side"><div class="pyr-bar male" style="width:${(pm / maxPct) * 100}%"></div></div>
      <span class="pyr-lbl">${BAND_LABELS[i]}</span>
      <div class="pyr-side right"><div class="pyr-bar female" style="width:${(pf / maxPct) * 100}%"></div></div>`;
    els.pyramid.append(row);
  }
}

function barRow(label, value, pct, sub = false) {
  const row = document.createElement("div");
  row.className = "bar-row" + (sub ? " sub" : "");
  const w = Math.max(0, Math.min(100, pct));
  row.innerHTML = `
    <span class="lbl">${label}</span>
    <div class="bar-track">
      <div class="grid-line"></div>
      <div class="bar-fill" style="width:${w}%"></div>
      <div class="bar-val" style="left:${w}%">${fmt(value)}人 (${pct.toFixed(1)}%)</div>
    </div>`;
  return row;
}

async function recompute() {
  if (!center || !manifest) return;
  const seq = ++computeSeq;
  const r = +els.radius.value;
  els.status.textContent = "計算中…";
  els.status.hidden = false;

  const [latMin, latMax, lonMin, lonMax] = circleBBox(center.lat, center.lng, r);
  const codes = primaryMeshesInBBox(latMin, latMax, lonMin, lonMax);
  const loaded = await Promise.all(codes.map(loadMesh));
  if (seq !== computeSeq) return; // 古い計算は破棄

  const missing = codes.filter((_, i) => loaded[i] === "missing");
  const cells = loaded.filter((m) => m !== "missing").flatMap((m) => m.cells);
  const agg = aggregateCircle(cells, center.lat, center.lng, r);
  const { pop: total, male, female, hh, meanAge, bands, cellCount, maskedPop } = agg;

  els.status.hidden = true;
  els.results.hidden = false;
  els.pop.innerHTML = `${fmt(total)}<span class="unit">人</span>`;
  els.hh.innerHTML = `${fmt(hh)}<span class="unit">世帯</span>`;
  els.mf.textContent = `${fmt(male)} / ${fmt(female)}`;
  els.meanAge.innerHTML = meanAge == null ? "–" : `${meanAge.toFixed(1)}<span class="unit">歳</span>`;

  els.ageBars.replaceChildren();
  if (total > 0) {
    const a0_14 = bandSum(bands, 0, 2);
    const a15_64 = bandSum(bands, 3, 12);
    const a65p = bandSum(bands, 13, N_BANDS - 1);
    const a75p = bandSum(bands, 15, N_BANDS - 1);
    const pct = (v) => (v / total) * 100;
    els.ageBars.append(
      barRow("0〜14歳", a0_14, pct(a0_14)),
      barRow("15〜64歳", a15_64, pct(a15_64)),
      barRow("65歳以上", a65p, pct(a65p)),
      barRow("うち75歳〜", a75p, pct(a75p), true),
    );
  }
  renderPyramid(bands, total);

  // 年齢内訳に出ない分 = 年齢不詳 + 秘匿セル(合算先計上)
  const shortfall = total - bandSum(bands, 0, N_BANDS - 1);
  els.maskNote.hidden = shortfall < total * 0.005;
  if (!els.maskNote.hidden) {
    els.maskNote.textContent = `※ 約${fmt(shortfall)}人(${((shortfall / total) * 100).toFixed(1)}%)は年齢内訳なし（年齢不詳・秘匿セル）`;
  }
  els.missingNote.hidden = missing.length === 0;
  if (missing.length > 0) {
    els.missingNote.textContent = `⚠ 未取込メッシュ ${missing.join(", ")} が圏内に掛かっています（fetch_mesh.py で追加可能）`;
  }
  els.meta.textContent = `半径 ${(r / 1000).toFixed(1)}km / 500mメッシュ ${fmt(cellCount)}セル / 中心 ${center.lat.toFixed(4)}, ${center.lng.toFixed(4)}`;
  syncUrl();
}

function setCenter(latlng) {
  center = latlng;
  const r = +els.radius.value;
  if (!circle) {
    circle = L.circle(latlng, { radius: r, color: "#2a78d6", weight: 2, fillOpacity: 0.08 }).addTo(map);
  } else {
    circle.setLatLng(latlng);
    circle.setRadius(r);
  }
  recompute();
}

map.on("click", (e) => setCenter(e.latlng));

// ---- 住所検索（地理院 AddressSearch API・CORS開放済み） ----
const addrInput = document.getElementById("addr");
const addrList = document.getElementById("addrList");
let addrSeq = 0;

function closeAddrList() {
  addrList.hidden = true;
  addrList.replaceChildren();
}

async function searchAddress(q) {
  const seq = ++addrSeq;
  const url = `https://msearch.gsi.go.jp/address-search/AddressSearch?q=${encodeURIComponent(q)}`;
  let feats = [];
  try {
    feats = await (await fetch(url)).json();
  } catch {
    feats = [];
  }
  if (seq !== addrSeq) return;
  addrList.replaceChildren();
  if (!feats.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "見つかりませんでした";
    addrList.append(li);
  }
  for (const f of feats.slice(0, 8)) {
    const [lon, lat] = f.geometry.coordinates;
    const li = document.createElement("li");
    li.textContent = f.properties.title;
    li.addEventListener("click", () => {
      closeAddrList();
      addrInput.value = f.properties.title;
      const ll = L.latLng(lat, lon);
      map.setView(ll, Math.max(map.getZoom(), 13));
      setCenter(ll);
    });
    addrList.append(li);
  }
  addrList.hidden = false;
}

let addrDebounce = null;
addrInput.addEventListener("input", () => {
  clearTimeout(addrDebounce);
  const q = addrInput.value.trim();
  if (q.length < 2) { closeAddrList(); return; }
  addrDebounce = setTimeout(() => searchAddress(q), 300);
});
addrInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    clearTimeout(addrDebounce);
    const q = addrInput.value.trim();
    if (q) searchAddress(q);
  } else if (e.key === "Escape") {
    closeAddrList();
  }
});
document.addEventListener("click", (e) => {
  if (!e.target.closest(".search")) closeAddrList();
});

let debounce = null;
els.radius.addEventListener("input", () => {
  els.radiusOut.textContent = `${(+els.radius.value / 1000).toFixed(1)} km`;
  if (circle) circle.setRadius(+els.radius.value);
  clearTimeout(debounce);
  debounce = setTimeout(recompute, 120);
});
