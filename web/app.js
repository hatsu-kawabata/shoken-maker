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
  single: document.getElementById("single"),
  compare: document.getElementById("compare"),
  pop: document.getElementById("pop"),
  hh: document.getElementById("hh"),
  mf: document.getElementById("mf"),
  meanAge: document.getElementById("meanAge"),
  pyramid: document.getElementById("pyramid"),
  cmpTable: document.getElementById("cmpTable"),
  pyramidA: document.getElementById("pyramidA"),
  pyramidB: document.getElementById("pyramidB"),
  cmpToggle: document.getElementById("cmpToggle"),
  moveTarget: document.getElementById("moveTarget"),
  maskNote: document.getElementById("maskNote"),
  missingNote: document.getElementById("missingNote"),
  meta: document.getElementById("meta"),
};

const COLOR = { A: "#2a78d6", B: "#4a3aa7" };

let manifest = null;
const meshCache = new Map(); // code1 -> {cells} | "missing" | Promise
const centers = { A: null, B: null };
const circles = { A: null, B: null };
let compareMode = false;
let moveTarget = "A";
let computeSeq = 0;

// ---- URL共有: ?lat&lng&r(&lat2&lng2) ----
function applyUrlState() {
  const p = new URLSearchParams(location.search);
  const lat = parseFloat(p.get("lat")), lng = parseFloat(p.get("lng")), r = parseInt(p.get("r"), 10);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
  if (Number.isFinite(r) && r >= 300 && r <= 5000) {
    els.radius.value = r;
    els.radiusOut.textContent = `${(r / 1000).toFixed(1)} km`;
  }
  map.setView([lat, lng], 14);
  setPoint("A", L.latLng(lat, lng));
  const lat2 = parseFloat(p.get("lat2")), lng2 = parseFloat(p.get("lng2"));
  if (Number.isFinite(lat2) && Number.isFinite(lng2)) {
    setCompareMode(true);
    setPoint("B", L.latLng(lat2, lng2));
  }
}

function syncUrl() {
  if (!centers.A) return;
  const p = new URLSearchParams();
  p.set("lat", centers.A.lat.toFixed(5));
  p.set("lng", centers.A.lng.toFixed(5));
  p.set("r", els.radius.value);
  if (compareMode && centers.B) {
    p.set("lat2", centers.B.lat.toFixed(5));
    p.set("lng2", centers.B.lng.toFixed(5));
  }
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

async function aggregateAt(center, r) {
  const [latMin, latMax, lonMin, lonMax] = circleBBox(center.lat, center.lng, r);
  const codes = primaryMeshesInBBox(latMin, latMax, lonMin, lonMax);
  const loaded = await Promise.all(codes.map(loadMesh));
  const missing = codes.filter((_, i) => loaded[i] === "missing");
  const cells = loaded.filter((m) => m !== "missing").flatMap((m) => m.cells);
  return { agg: aggregateCircle(cells, center.lat, center.lng, r), missing };
}

// ---- 人口ピラミッド(5歳階級×男女) ----
const BAND_LABELS = ["0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39",
  "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70-74", "75-79", "80-84",
  "85-89", "90-94", "95+"];

function renderPyramid(container, bands, total) {
  container.replaceChildren();
  if (total <= 0) return;
  const maxPct = Math.max(0.1, ...bands.map((b) => Math.max(b.m, b.f) / total * 100));
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
    container.append(row);
  }
}

function renderSingle(agg) {
  const { pop: total, male, female, hh, meanAge, bands } = agg;
  els.pop.innerHTML = `${fmt(total)}<span class="unit">人</span>`;
  els.hh.innerHTML = `${fmt(hh)}<span class="unit">世帯</span>`;
  els.mf.textContent = `${fmt(male)} / ${fmt(female)}`;
  els.meanAge.innerHTML = meanAge == null ? "–" : `${meanAge.toFixed(1)}<span class="unit">歳</span>`;
  renderPyramid(els.pyramid, bands, total);
}

function renderCompare(aggA, aggB) {
  const row = (label, va, vb) => `<tr><td>${label}</td><td>${va}</td><td>${vb}</td></tr>`;
  const age = (a) => (a.meanAge == null ? "–" : `${a.meanAge.toFixed(1)}歳`);
  const seniorPct = (a) => (a.pop > 0 ? `${(bandSum(a.bands, 13, N_BANDS - 1) / a.pop * 100).toFixed(1)}%` : "–");
  const diff = aggA.pop > 0 ? ((aggB.pop - aggA.pop) / aggA.pop) * 100 : null;
  els.cmpTable.innerHTML = `
    <tr><th></th><th><span class="dot" style="background:${COLOR.A}"></span>地点A</th>
        <th><span class="dot" style="background:${COLOR.B}"></span>地点B</th></tr>
    ${row("人口", fmt(aggA.pop), fmt(aggB.pop) + (diff == null ? "" : ` <span class="delta">(${diff >= 0 ? "+" : ""}${diff.toFixed(0)}%)</span>`))}
    ${row("世帯数", fmt(aggA.hh), fmt(aggB.hh))}
    ${row("平均年齢", age(aggA), age(aggB))}
    ${row("65歳以上", seniorPct(aggA), seniorPct(aggB))}`;
  renderPyramid(els.pyramidA, aggA.bands, aggA.pop);
  renderPyramid(els.pyramidB, aggB.bands, aggB.pop);
}

async function recompute() {
  if (!centers.A || !manifest) return;
  const seq = ++computeSeq;
  const r = +els.radius.value;
  els.status.textContent = "計算中…";
  els.status.hidden = false;

  const resA = await aggregateAt(centers.A, r);
  const resB = compareMode && centers.B ? await aggregateAt(centers.B, r) : null;
  if (seq !== computeSeq) return; // 古い計算は破棄

  els.status.hidden = true;
  els.results.hidden = false;
  const showCompare = resB != null;
  els.single.hidden = showCompare;
  els.compare.hidden = !showCompare;
  if (showCompare) {
    renderCompare(resA.agg, resB.agg);
  } else {
    renderSingle(resA.agg);
    if (compareMode) els.status.hidden = false, els.status.textContent = "地図をクリックして地点Bを指定してください";
  }

  const agg = resA.agg;
  const shortfall = agg.pop - bandSum(agg.bands, 0, N_BANDS - 1);
  els.maskNote.hidden = showCompare || shortfall < agg.pop * 0.005;
  if (!els.maskNote.hidden) {
    els.maskNote.textContent = `※ 約${fmt(shortfall)}人(${((shortfall / agg.pop) * 100).toFixed(1)}%)は年齢内訳なし（年齢不詳・秘匿セル）`;
  }
  const missing = [...resA.missing, ...(resB ? resB.missing : [])];
  els.missingNote.hidden = missing.length === 0;
  if (missing.length > 0) {
    els.missingNote.textContent = `⚠ 未取込メッシュ ${missing.join(", ")} が圏内に掛かっています`;
  }
  els.meta.textContent = `半径 ${(r / 1000).toFixed(1)}km / 中心A ${centers.A.lat.toFixed(4)}, ${centers.A.lng.toFixed(4)}` +
    (showCompare ? ` / 中心B ${centers.B.lat.toFixed(4)}, ${centers.B.lng.toFixed(4)}` : "");
  syncUrl();
}

function setPoint(key, latlng) {
  centers[key] = latlng;
  const r = +els.radius.value;
  if (!circles[key]) {
    circles[key] = L.circle(latlng, { radius: r, color: COLOR[key], weight: 2, fillOpacity: 0.08 }).addTo(map);
  } else {
    circles[key].setLatLng(latlng);
    circles[key].setRadius(r);
  }
  recompute();
}

function removePoint(key) {
  centers[key] = null;
  if (circles[key]) {
    circles[key].remove();
    circles[key] = null;
  }
}

function setCompareMode(on) {
  compareMode = on;
  els.cmpToggle.textContent = on ? "比較を終了" : "別の地点と比較";
  els.cmpToggle.classList.toggle("active", on);
  els.moveTarget.hidden = !on;
  moveTarget = on ? "B" : "A";
  updateMoveTargetUI();
  if (!on) {
    removePoint("B");
  }
  recompute();
}

function updateMoveTargetUI() {
  for (const b of els.moveTarget.querySelectorAll("button")) {
    b.classList.toggle("active", b.dataset.t === moveTarget);
  }
}

els.cmpToggle.addEventListener("click", () => setCompareMode(!compareMode));
els.moveTarget.addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  moveTarget = b.dataset.t;
  updateMoveTargetUI();
});

map.on("click", (e) => setPoint(compareMode ? moveTarget : "A", e.latlng));

// ---- 検索: 駅名(ローカル・乗降客数順) + 住所(地理院 AddressSearch API) ----
const addrInput = document.getElementById("addr");
const addrList = document.getElementById("addrList");
let addrSeq = 0;
let stations = null; // 遅延ロード

async function loadStations() {
  if (stations) return stations;
  try {
    stations = await (await fetch("data/stations.json")).json();
  } catch {
    stations = [];
  }
  return stations;
}

function closeAddrList() {
  addrList.hidden = true;
  addrList.replaceChildren();
}

function resultItem(label, sub, lat, lon, zoom) {
  const li = document.createElement("li");
  li.innerHTML = sub ? `${label} <span class="cand-sub">${sub}</span>` : label;
  li.addEventListener("click", () => {
    closeAddrList();
    addrInput.value = label.replace(/<[^>]*>/g, "");
    const ll = L.latLng(lat, lon);
    map.setView(ll, Math.max(map.getZoom(), zoom));
    setPoint(compareMode ? moveTarget : "A", ll);
  });
  return li;
}

async function searchAddress(q) {
  const seq = ++addrSeq;
  const norm = q.replace(/駅$/, "");
  const [sts, feats] = await Promise.all([
    loadStations(),
    fetch(`https://msearch.gsi.go.jp/address-search/AddressSearch?q=${encodeURIComponent(q)}`)
      .then((r) => r.json())
      .catch(() => []),
  ]);
  if (seq !== addrSeq) return;
  addrList.replaceChildren();

  const pre = sts.filter((s) => s.n.startsWith(norm));
  const part = sts.filter((s) => !s.n.startsWith(norm) && s.n.includes(norm));
  for (const s of [...pre, ...part].slice(0, 6)) {
    const paxTxt = s.p ? `${s.p.toLocaleString("ja-JP")}人/日` : "";
    const lineTxt = s.l.slice(0, 2).join("・") + (s.l.length > 2 ? " ほか" : "");
    addrList.append(resultItem(`<b>${s.n}駅</b>`, `${lineTxt} ${paxTxt}`, s.la, s.lo, 15));
  }
  for (const f of feats.slice(0, 6)) {
    const [lon, lat] = f.geometry.coordinates;
    addrList.append(resultItem(f.properties.title, "", lat, lon, 13));
  }
  if (!addrList.children.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "見つかりませんでした";
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
  for (const k of ["A", "B"]) if (circles[k]) circles[k].setRadius(+els.radius.value);
  clearTimeout(debounce);
  debounce = setTimeout(recompute, 120);
});
