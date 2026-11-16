// Coil Spring Designer – browser front end.
// The server does the engineering (same Python code as the desktop app) in mm / N / MPa;
// this file handles input, unit conversion, drawing and charts.
import * as THREE from "./vendor/three.module.min.js";
import { OrbitControls } from "./vendor/OrbitControls.js";

const MM_PER_IN = 25.4, N_PER_LBF = 4.448221615, MPA_PER_KSI = 6.894757, KGF = 9.80665;
const MPA_PER_PSI = 0.006894757, MM2_PER_IN2 = MM_PER_IN * MM_PER_IN;
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ------------------------------------------------------------------ units
class Units {
  constructor(system) {
    this.system = system;                        // 0 in/lbf, 1 mm/N, 2 mm/kgf
    this.imperial = system === 0;
    this.kg = system === 2;
    this.fN = this.imperial ? N_PER_LBF : this.kg ? KGF : 1;
    this.sM = this.imperial ? MPA_PER_KSI : this.kg ? KGF : 1;
  }
  get lenUnit() { return this.imperial ? "in" : "mm"; }
  get forceUnit() { return this.imperial ? "lbf" : this.kg ? "kgf" : "N"; }
  get rateUnit() { return `${this.forceUnit}/${this.lenUnit}`; }
  get stressUnit() { return this.imperial ? "ksi" : this.kg ? "kgf/mm²" : "MPa"; }
  get areaUnit() { return this.imperial ? "in²" : "mm²"; }
  len(mm) { return this.imperial ? mm / MM_PER_IN : mm; }
  lenIn(v) { return this.imperial ? v * MM_PER_IN : v; }
  force(n) { return n / this.fN; }
  forceIn(v) { return v * this.fN; }
  rate(k) { return k * this.lenIn(1) / this.fN; }
  rateIn(v) { return v * this.fN / this.lenIn(1); }
  stress(m) { return m / this.sM; }
  area(mm2) { return this.imperial ? mm2 / MM2_PER_IN2 : mm2; }
  areaIn(v) { return this.imperial ? v * MM2_PER_IN2 : v; }
  mass(g) { return this.imperial ? g / 28.349523 : g; }
  fl(mm) { return `${this.len(mm).toFixed(this.imperial ? 4 : 2)} ${this.lenUnit}`; }
  ff(n) { return `${this.force(n).toFixed(2)} ${this.forceUnit}`; }
  fr(k) { return `${this.rate(k).toFixed(3)} ${this.rateUnit}`; }
  fs(m) { return `${this.stress(m).toFixed(1)} ${this.stressUnit}`; }
  lenDecimals() { return this.imperial ? 4 : 3; }
}

// ------------------------------------------------------------------ state
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private window */ } },
};

let META = null;
let U = new Units(store.get("csd.units", 0));
const S = {
  spring: null,            // mm / N (server format, without work_length)
  diaMode: "od",
  target: { mode: "rate", rate: null, force: null, distance: null, kind: "deflection" },
  snap: true,
  op: { use: false, kind: "travel", val: 0 },   // val: travel or working length, mm
  result: null, compute: null,
  clamp: {
    source: 1, cat_rate: 5.3 * KGF, cat_free: 17.0, cat_solid: 9.17, part_no: "LHP 063D 02S",
    n: 8, disp: 4.5, tol_terms: [0.1, 0.05, 0.05, 0.05, 0.05, 0.05], rate_tol: 0.10,
    area_mode: 0, area: 6000, area_L: 100, area_W: 60, method: 0,
  },
  clampOut: null,
};

function workLength() {
  if (!S.op.use) return null;
  return S.op.kind === "travel" ? S.spring.free_length - S.op.val : S.op.val;
}
function springPayload() { return { ...S.spring, work_length: workLength() }; }

function persist() {
  store.set("csd.state", { spring: S.spring, diaMode: S.diaMode, target: S.target, snap: S.snap, op: S.op, clamp: S.clamp });
}

// ------------------------------------------------------------------ helpers
async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : "Check the inputs – one value is out of range."; } catch (e) {}
    throw new Error(msg);
  }
  return r;
}
const apiJson = async (p, b) => (await api(p, b)).json();

function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
function num(id) { const v = parseFloat($(id).value); return Number.isFinite(v) ? v : NaN; }
function setNum(id, v, dec) { $(id).value = Number.isFinite(v) ? (+v.toFixed(dec)).toString() : ""; }

let toastTimer;
function toast(msg, bad = false) {
  const t = $("toast");
  t.textContent = msg; t.classList.toggle("bad", bad); t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, bad ? 6000 : 3000);
}

async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); return true; }
  } catch (e) { /* fall through */ }
  const ta = document.createElement("textarea");      // works on plain http:// too
  ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.appendChild(ta); ta.select();
  let ok = false; try { ok = document.execCommand("copy"); } catch (e) {}
  ta.remove(); return ok;
}

function download(blob, filename) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 10000);
}

function niceTicks(min, max, count = 6) {
  const span = max - min;
  if (!(span > 0)) return { ticks: [min], dec: 0 };
  const raw = span / count, mag = 10 ** Math.floor(Math.log10(raw)), e = raw / mag;
  const step = (e >= 7.5 ? 10 : e >= 3.5 ? 5 : e >= 1.5 ? 2 : 1) * mag;
  const ticks = [];
  for (let v = Math.ceil(min / step - 1e-9) * step; v <= max + step * 1e-9; v += step) ticks.push(+v.toFixed(12));
  return { ticks, dec: Math.max(0, -Math.floor(Math.log10(step) + 1e-9)) };
}
const svgEl = (tag, attrs, text) => {
  const a = Object.entries(attrs).map(([k, v]) => `${k}="${v}"`).join(" ");
  return text === undefined ? `<${tag} ${a}/>` : `<${tag} ${a}>${text}</${tag}>`;
};
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// ============================================================ SPRING DESIGN
function fillStaticSelects() {
  $("material").innerHTML = META.materials.map((m) => `<option>${esc(m.name)}</option>`).join("");
  $("end_type").innerHTML = META.end_types.map((e) => `<option>${esc(e)}</option>`).join("");
  $("k-method").innerHTML = META.methods.map((m, i) => `<option value="${i}">${esc(m)}</option>`).join("");
}

function material() { return META.materials.find((m) => m.name === S.spring.material) || META.materials[0]; }

function fillWireChart() {
  const opts = ['<option value="">Std…</option>'];
  for (const { d, sut } of material().chart) {
    const v = U.len(d);
    let label = U.imperial ? v.toFixed(4).replace(/0$/, "") : (+v.toFixed(3)).toString();
    if (sut) label += `  (${U.fs(sut)})`;
    opts.push(`<option value="${d}">${label}</option>`);
  }
  $("wire-std").innerHTML = opts.join("");
}

function applyUnitLabels() {
  const map = { len: U.lenUnit, rate: U.rateUnit, force: U.forceUnit, area: U.areaUnit };
  document.querySelectorAll(".unit[data-u]").forEach((el) => { el.textContent = map[el.dataset.u]; });
  const step = U.imperial ? 0.001 : 0.01;
  ["wire_d"].forEach((id) => { $(id).step = step; });
  ["dia", "free_len", "target-x", "work-val", "k-free", "k-solid", "k-disp", "k-L", "k-W"].forEach((id) => { $(id).step = step * 10; });
  $("k-area").step = U.imperial ? 0.1 : 10;
}

function diaValue() {
  const s = S.spring;
  return S.diaMode === "od" ? s.mean_d + s.wire_d : S.diaMode === "id" ? s.mean_d - s.wire_d : s.mean_d;
}

function pushSpringInputs() {
  const s = S.spring, dec = U.lenDecimals();
  $("material").value = s.material;
  fillWireChart();
  setNum("wire_d", U.len(s.wire_d), dec);
  document.querySelectorAll('input[name="dia-mode"]').forEach((r) => { r.checked = r.value === S.diaMode; });
  $("dia-label").textContent = { od: "OD", id: "ID", mean: "Mean Ø" }[S.diaMode];
  setNum("dia", U.len(diaValue()), dec);
  $("end_type").value = s.end_type;
  setNum("active", s.active_coils, 2);
  setNum("free_len", U.len(s.free_length), dec);
  $("hand").value = s.right_hand ? "1" : "0";
  // target
  $("target-mode").value = S.target.mode;
  setNum("target-k", U.rate(S.target.rate), 4);
  setNum("target-f", U.force(S.target.force), 3);
  $("target-xkind").value = S.target.kind;
  setNum("target-x", U.len(S.target.distance), dec);
  $("snap").checked = S.snap;
  // operating point
  $("use-work").checked = S.op.use;
  $("work-kind").value = S.op.kind;
  $("work-label").textContent = S.op.kind === "travel" ? "Travel" : "Working length";
  setNum("work-val", U.len(S.op.val), dec);
  $("work-kind").disabled = $("work-val").disabled = !S.op.use;
  showTargetRows();
}

// Boxes show rounded values. Only take a box's number when the person changed it;
// otherwise keep the exact stored value (e.g. 4.5 mm shown as 0.1772 in stays 4.5 mm).
function keep(stored, id, toDisp, fromDisp, dec) {
  const v = num(id);
  if (stored != null && Number.isFinite(stored) && Number.isFinite(v) && Math.abs(v - +toDisp(stored).toFixed(dec)) < 0.5 * 10 ** -dec) return stored;
  return fromDisp(v);
}
const keepLen = (stored, id) => keep(stored, id, (x) => U.len(x), (x) => U.lenIn(x), U.lenDecimals());

function readSpringInputs() {
  const old = S.spring;
  const d = keepLen(old.wire_d, "wire_d");
  const newMode = document.querySelector('input[name="dia-mode"]:checked').value;
  const oldDia = { od: old.mean_d + old.wire_d, id: old.mean_d - old.wire_d, mean: old.mean_d }[newMode];
  const v = newMode === S.diaMode ? keepLen(oldDia, "dia") : U.lenIn(num("dia"));
  S.diaMode = newMode;
  const mean = S.diaMode === "od" ? v - d : S.diaMode === "id" ? v + d : v;
  S.spring = {
    ...S.spring, wire_d: d, mean_d: mean, active_coils: num("active"), free_length: keepLen(old.free_length, "free_len"),
    end_type: $("end_type").value, material: $("material").value, right_hand: $("hand").value === "1",
  };
  S.target.mode = $("target-mode").value;
  S.target.rate = keep(S.target.rate, "target-k", (x) => U.rate(x), (x) => U.rateIn(x), 4);
  S.target.force = keep(S.target.force, "target-f", (x) => U.force(x), (x) => U.forceIn(x), 3);
  const kind = $("target-xkind").value;
  S.target.distance = kind === S.target.kind ? keepLen(S.target.distance, "target-x") : U.lenIn(num("target-x"));
  S.target.kind = kind;
  S.snap = $("snap").checked;
  S.op.use = $("use-work").checked;
  const opKind = $("work-kind").value;
  S.op.val = opKind === S.op.kind ? keepLen(S.op.val, "work-val") : U.lenIn(num("work-val"));
  S.op.kind = opKind;
}

function showTargetRows() {
  const force = S.target.mode === "force";
  document.querySelectorAll("[data-target]").forEach((el) => { el.hidden = (el.dataset.target === "force") !== force; });
}

function springValid() {
  const s = S.spring;
  return [s.wire_d, s.mean_d, s.active_coils, s.free_length].every((v) => Number.isFinite(v) && v > 0);
}

// ---- compute ----
let computeSeq = 0;
async function recompute() {
  persist();
  updateInfoLines();
  if (!springValid()) { renderInvalid("Fill in wire diameter, diameter, coils and free length."); return; }
  const seq = ++computeSeq;
  try {
    const out = await apiJson("/api/compute", springPayload());
    if (seq !== computeSeq) return;
    S.compute = out; S.result = out.result;
    renderResults();
    if (DEV.on) scheduleTrace();
    if (activeView === "3d") scheduleMesh(); else meshStale = true;
    if (activePage === "clamp" || S.clamp.source === 0) scheduleClamp();
  } catch (e) {
    if (seq === computeSeq) renderInvalid(e.message);
  }
}
const scheduleCompute = debounce(recompute, 120);

function updateInfoLines() {
  const s = S.spring, m = material();
  const g = U.imperial ? `${(U.stress(m.G) / 1000).toFixed(1)} Mpsi` : `${Math.round(U.stress(m.G)).toLocaleString()} ${U.stressUnit}`;
  $("mat-info").textContent = `G = ${g}  ·  allow ${Math.round(m.allow * 100)}% Sut`;
  const others = [["OD", s.mean_d + s.wire_d], ["ID", s.mean_d - s.wire_d], ["Mean", s.mean_d]].filter(([n]) => n.toLowerCase() !== S.diaMode);
  $("dia-info").textContent = springValid() ? others.map(([n, v]) => `${n} ${U.fl(v)}`).join("  ·  ") : "";
  updateTargetHint();
}

function updateTargetHint() {
  if (S.target.mode !== "force") return;
  const x = targetDeflection();
  const el = $("target-hint");
  if (x === null) { el.innerHTML = `<span class="msg bad">Compressed length must be shorter than the free length.</span>`; return; }
  const k = S.target.force / x;
  let html = `Required rate: <b>${U.fr(k)}</b>  ·  ` +
    (S.target.kind === "deflection" ? `at length ${U.fl(S.spring.free_length - x)}` : `deflection ${U.fl(x)}`);
  const r = S.result;
  if (r && r.ok && S.spring.free_length - x < r.solid_length)
    html += `<br><span class="msg warn">That position is below the current solid height (${U.fl(r.solid_length)}).</span>`;
  el.innerHTML = html;
}

function targetDeflection() {
  let x = S.target.distance;
  if (!Number.isFinite(x)) return null;
  if (S.target.kind === "length") x = S.spring.free_length - x;
  return x > 0 ? x : null;
}

function setCard(id, value, state) {
  const el = $(id); el.textContent = value;
  el.classList.remove("good", "warn", "bad"); if (state) el.classList.add(state);
}

function renderMessages(el, errors, warnings, okText) {
  const items = [
    ...errors.map((e) => `<p class="msg bad"><b>✕</b>${esc(e)}</p>`),
    ...warnings.map((w) => `<p class="msg warn"><b>!</b>${esc(w)}</p>`),
  ];
  el.innerHTML = items.length ? items.join("") : `<p class="msg good">✓ ${okText}</p>`;
}

function renderInvalid(msg) {
  ["c-rate", "c-solid", "c-fsolid", "c-stress"].forEach((id) => setCard(id, "—"));
  $("c-solid-s").textContent = $("c-stress-s").textContent = "";
  $("details").innerHTML = ""; $("work-box").hidden = true;
  renderMessages($("messages"), [msg], [], "");
  S.result = null; S.compute = null;
  drawDrawing(); drawLoadChart();
  $("btn-step").disabled = $("btn-stl").disabled = true;
}

function renderResults() {
  const r = S.result, s = S.spring;
  $("total-info").textContent = r.total_coils ? `${+r.total_coils.toFixed(2)} total coils` : "";
  if (r.errors.length && !r.rate) { renderInvalid(r.errors[0]); return; }
  setCard("c-rate", U.fr(r.rate));
  setCard("c-solid", U.fl(r.solid_length)); $("c-solid-s").textContent = `travel ${U.fl(r.max_deflection)}`;
  setCard("c-fsolid", U.ff(r.force_solid));
  const ratio = r.allow ? r.stress_solid / r.allow : 0;
  setCard("c-stress", U.fs(r.stress_solid), ratio > 1 ? "bad" : ratio > 0.85 ? "warn" : "good");
  $("c-stress-s").textContent = `${Math.round(ratio * 100)}% of allowable ${U.fs(r.allow)}  ·  safety factor ${r.safety_solid == null ? "∞" : r.safety_solid.toFixed(2)}`;

  const rows = [
    ["OD", U.fl(s.mean_d + s.wire_d)], ["ID", U.fl(s.mean_d - s.wire_d)], ["Mean diameter", U.fl(s.mean_d)],
    ["Spring index C", r.index.toFixed(2)], ["Total coils", +r.total_coils.toFixed(2)],
    ["Active pitch", U.fl(r.pitch)], ["Pitch angle", `${r.pitch_angle_deg.toFixed(2)}°`],
    ["Max deflection", U.fl(r.max_deflection)], ["Stress correction Kb", r.bergstrasser.toFixed(3)],
    ["Wire Sut", U.fs(r.sut) + (r.sut_from_chart ? "  (chart)" : "")], ["Allowable (solid)", U.fs(r.allow)],
    ["OD at solid", U.fl(r.od_solid)], ["L₀ / D", `${r.slenderness.toFixed(2)}  (limit ${r.buckling_limit.toFixed(2)})`],
    ["Natural freq.", `${Math.round(r.nat_freq).toLocaleString()} Hz`], ["Wire length", U.fl(r.wire_length)],
    ["Mass", `${U.mass(r.mass).toFixed(3)} ${U.imperial ? "oz" : "g"}`],
  ];
  $("details").innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}${devBtn(DETAIL_KEYS[k], k)}</dd>`).join("");

  const wl = workLength();
  if (wl !== null && r.work_force !== null) {
    $("work-box").hidden = false;
    $("work-details").innerHTML = [
      ["Travel", U.fl(r.work_deflection)], ["Length", U.fl(wl)], ["Force", U.ff(r.work_force)],
      ["Stress", U.fs(r.work_stress)], ["% of allowable", `${Math.round(r.work_stress / r.allow * 100)}%`],
    ].map(([k, v]) => `<dt>${k}</dt><dd>${v}${devBtn(WORK_KEYS[k], k)}</dd>`).join("");
  } else $("work-box").hidden = true;

  renderMessages($("messages"), r.errors, r.warnings, "No design issues found.");
  $("btn-step").disabled = $("btn-stl").disabled = !r.ok;
  updateTargetHint();
  drawDrawing(); drawLoadChart();
}

// ---- solve ----
async function solve(which) {
  readSpringInputs();
  if (!springValid()) return;
  const t = S.target;
  if (t.mode === "force" && targetDeflection() === null) {
    $("solve-info").innerHTML = `<span class="msg bad">Compressed length must be shorter than the free length.</span>`; return;
  }
  const body = {
    spring: springPayload(), solve: which, dia_mode: S.diaMode, snap: S.snap,
    target: { mode: t.mode, rate: t.rate, force: t.force, distance: t.distance, distance_kind: t.kind },
  };
  try {
    const out = await apiJson("/api/solve", body);
    const { work_length, ...sp } = out.spring;
    S.spring = sp;
    let txt = which === "coils"
      ? `Exact: ${out.exact.toFixed(3)} active coils → rounded to ${out.chosen}.`
      : `Exact: ${U.fl(out.exact)}` + (out.snapped ? ` → chart size ${U.fl(out.chosen)}${out.outside_chart ? " (outside the chart range)" : ""}` : "") + ".";
    if (out.achieved_force !== undefined) {
      S.op.use = true;
      S.op.val = S.op.kind === "travel" ? out.deflection : sp.free_length - out.deflection;
      const pct = (out.achieved_force / out.target_force - 1) * 100;
      txt += `<br>Gives ${U.ff(out.achieved_force)} at that distance (${pct >= 0 ? "+" : ""}${pct.toFixed(1)}% vs target).`;
    }
    pushSpringInputs();
    $("solve-info").innerHTML = txt;
    recompute();
  } catch (e) { $("solve-info").innerHTML = `<span class="msg bad">${esc(e.message)}</span>`; }
}

// ---- side drawing (SVG) ----
function drawDrawing() {
  const svg = $("drawing");
  const W = svg.clientWidth || 600, H = svg.clientHeight || 500;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const c = S.compute, s = S.spring, r = S.result;
  if (!c || !c.centerline || !r || !r.ok) {
    svg.innerHTML = svgEl("text", { x: W / 2, y: H / 2, "text-anchor": "middle", style: "fill:var(--dim)" }, "Enter a valid spring");
    return;
  }
  const od = s.mean_d + s.wire_d, idd = s.mean_d - s.wire_d, L0 = s.free_length;
  const ml = 70, mr = 160, mt = 86, mb = 74, aw = W - ml - mr, ah = H - mt - mb;
  const sc = Math.max(0.01, Math.min(aw / od, ah / L0));
  const cx = ml + aw / 2, z0 = mt + (ah + L0 * sc) / 2;
  const X = (x) => cx + x * sc, Y = (z) => z0 - z * sc;
  const lw = Math.max(s.wire_d * sc, 1);
  const ground = s.end_type.includes("ground");

  const paths = { back: [], front: [] };
  let cur = null, curFront = null;
  for (const [x, y, z] of c.centerline) {
    const front = y <= 0;
    if (front !== curFront) { cur = []; (front ? paths.front : paths.back).push(cur); curFront = front; }
    cur.push(`${X(x).toFixed(1)},${Y(z).toFixed(1)}`);
  }
  const d = (runs) => runs.filter((p) => p.length > 1).map((p) => "M" + p.join("L")).join("");
  const off = lw * 0.18;
  let out = "";
  out += `<defs><clipPath id="gclip"><rect x="0" y="${Y(L0)}" width="${W}" height="${L0 * sc}"/></clipPath></defs>`;
  out += `<g ${ground ? 'clip-path="url(#gclip)"' : ""} fill="none" stroke-linecap="round" stroke-linejoin="round">`;
  out += `<path d="${d(paths.back)}" style="stroke:var(--wire);stroke-opacity:.42" stroke-width="${lw}"/>`;
  out += `<path d="${d(paths.front)}" style="stroke:var(--wire)" stroke-width="${lw}"/>`;
  out += `<path d="${d(paths.front)}" transform="translate(${-off},${-off})" style="stroke:#fff;stroke-opacity:.32" stroke-width="${Math.max(lw * 0.25, 0.6)}"/>`;
  out += `</g>`;
  const dim = "stroke:var(--dim)", acc = "stroke:var(--accent)", ink = "fill:var(--ink)";
  // end planes and axis
  for (const z of [0, L0]) out += svgEl("line", { x1: X(-od * 0.75), y1: Y(z), x2: X(od * 0.75), y2: Y(z), style: dim, "stroke-dasharray": "4 3" });
  out += svgEl("line", { x1: cx, y1: Y(-L0 * 0.05), x2: cx, y2: Y(L0 * 1.05), style: dim + ";stroke-opacity:.6", "stroke-dasharray": "10 3 2 3" });
  const arrowH = (x1, x2, y) => `<path d="M${x1},${y}L${x2},${y}M${x1 + 6},${y - 3}L${x1},${y}L${x1 + 6},${y + 3}M${x2 - 6},${y - 3}L${x2},${y}L${x2 - 6},${y + 3}" style="${acc}" fill="none"/>`;
  const arrowV = (x, y1, y2) => `<path d="M${x},${y1}L${x},${y2}M${x - 3},${y1 + 6}L${x},${y1}L${x + 3},${y1 + 6}M${x - 3},${y2 - 6}L${x},${y2}L${x + 3},${y2 - 6}" style="${acc}" fill="none"/>`;
  const txt = (x, y, t, anchor = "middle", extra = "") => svgEl("text", { x, y, "text-anchor": anchor, style: ink + extra, "font-size": "12.5" }, esc(t));
  // OD above
  const yOd = Y(L0) - 24;
  for (const sgn of [-1, 1]) out += svgEl("line", { x1: X(sgn * od / 2), y1: Y(L0) - 4, x2: X(sgn * od / 2), y2: yOd - 4, style: dim });
  out += arrowH(X(-od / 2), X(od / 2), yOd) + txt(cx, yOd - 7, `OD ${U.fl(od)}`);
  // ID below
  const yId = Y(0) + 28;
  for (const sgn of [-1, 1]) out += svgEl("line", { x1: X(sgn * idd / 2), y1: Y(0) + 4, x2: X(sgn * idd / 2), y2: yId + 4, style: dim });
  out += arrowH(X(-idd / 2), X(idd / 2), yId) + txt(cx, yId + 17, `ID ${U.fl(idd)}`);
  // free length + solid height
  const xr = X(od / 2) + 30;
  for (const z of [0, L0]) out += svgEl("line", { x1: X(od * 0.75) + 2, y1: Y(z), x2: xr + 4, y2: Y(z), style: dim });
  out += arrowV(xr, Y(L0), Y(0)) + txt(xr + 9, (Y(L0) + Y(0)) / 2 + 4, `L₀ ${U.fl(L0)}`, "start");
  out += txt(xr + 9, Y(0) - 10, `Ls ${U.fl(r.solid_length)}`, "start", ";fill:var(--dim)");
  out += txt(12, 22, `Ø wire ${U.fl(s.wire_d)}   ·   ${s.end_type}   ·   ${s.right_hand ? "RH" : "LH"}   ·   ${+r.total_coils.toFixed(2)} total / ${s.active_coils} active coils`, "start");
  svg.innerHTML = out;
}

// ---- generic XY chart frame ----
function chartFrame(svg, xr, yr, xLabel, yLabel, invertX = false) {
  const W = svg.clientWidth || 600, H = svg.clientHeight || 400;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const m = { l: 62, r: 18, t: 18, b: 48 };
  const w = W - m.l - m.r, h = H - m.t - m.b;
  const sx = (v) => m.l + (invertX ? (xr[1] - v) : (v - xr[0])) / (xr[1] - xr[0]) * w;
  const sy = (v) => m.t + h - (v - yr[0]) / (yr[1] - yr[0]) * h;
  let out = "";
  const xt = niceTicks(xr[0], xr[1], Math.max(3, Math.round(w / 90)));
  const yt = niceTicks(yr[0], yr[1], Math.max(3, Math.round(h / 60)));
  for (const v of xt.ticks) {
    out += svgEl("line", { x1: sx(v), y1: m.t, x2: sx(v), y2: m.t + h, style: "stroke:var(--grid)" });
    out += svgEl("text", { x: sx(v), y: m.t + h + 18, "text-anchor": "middle", "font-size": "12", style: "fill:var(--axis)" }, v.toFixed(xt.dec));
  }
  for (const v of yt.ticks) {
    out += svgEl("line", { x1: m.l, y1: sy(v), x2: m.l + w, y2: sy(v), style: "stroke:var(--grid)" });
    out += svgEl("text", { x: m.l - 8, y: sy(v) + 4, "text-anchor": "end", "font-size": "12", style: "fill:var(--axis)" }, v.toFixed(yt.dec));
  }
  out += svgEl("rect", { x: m.l, y: m.t, width: w, height: h, fill: "none", style: "stroke:var(--border)" });
  out += svgEl("text", { x: m.l + w / 2, y: H - 10, "text-anchor": "middle", "font-size": "12.5", style: "fill:var(--axis)" }, esc(xLabel));
  out += svgEl("text", { x: 16, y: m.t + h / 2, "text-anchor": "middle", "font-size": "12.5", transform: `rotate(-90 16 ${m.t + h / 2})`, style: "fill:var(--axis)" }, esc(yLabel));
  return { out, sx, sy, m, w, h };
}
const polyline = (pts, style, extra = "") => `<polyline points="${pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ")}" fill="none" style="${style}" ${extra}/>`;

function drawLoadChart() {
  const svg = $("loadchart");
  const r = S.result, s = S.spring, c = S.compute;
  if (!r || !r.ok || !c) { svg.innerHTML = ""; return; }
  const fAllow = U.force(c.f_allow);
  const top = Math.max(U.force(r.force_solid), fAllow) * 1.1;
  const xr = [U.len(r.solid_length) * 0.95, U.len(s.free_length) * 1.02];
  const f = chartFrame(svg, xr, [0, top], `Length (${U.lenUnit})`, `Force (${U.forceUnit})`, true);
  let out = f.out;
  const pts = [];
  for (let i = 0; i <= 40; i++) {
    const L = s.free_length + (r.solid_length - s.free_length) * i / 40;
    pts.push([f.sx(U.len(L)), f.sy(U.force(r.rate * (s.free_length - L)))]);
  }
  out += svgEl("line", { x1: f.m.l, y1: f.sy(fAllow), x2: f.m.l + f.w, y2: f.sy(fAllow), style: "stroke:var(--accent)", "stroke-dasharray": "5 4" });
  out += svgEl("text", { x: f.m.l + 8, y: f.sy(fAllow) - 6, "font-size": "12", style: "fill:var(--accent)" }, "allowable");
  const xs = f.sx(U.len(r.solid_length));
  out += svgEl("line", { x1: xs, y1: f.m.t, x2: xs, y2: f.m.t + f.h, style: "stroke:var(--dim)", "stroke-dasharray": "5 4" });
  out += svgEl("text", { x: xs - 6, y: f.m.t + f.h / 2, "text-anchor": "end", "font-size": "12", style: "fill:var(--dim)" }, "solid");
  out += polyline(pts, "stroke:var(--wire);stroke-width:2.5");
  const wl = workLength();
  if (wl !== null && r.work_force !== null)
    out += svgEl("circle", { cx: f.sx(U.len(wl)), cy: f.sy(U.force(r.work_force)), r: 5.5, style: "fill:var(--accent)" });
  svg.innerHTML = out;
}

// ---- 3D view (three.js) ----
let three = null, meshStale = true, lastSize = null, meshSeq = 0;
function init3D() {
  const canvas = $("c3d");
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100000);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = false;
  scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 1.6));
  const key = new THREE.DirectionalLight(0xffffff, 2.2); key.position.set(3, 5, 4); scene.add(key);
  const fill = new THREE.DirectionalLight(0xffffff, 0.8); fill.position.set(-4, 1, -2); scene.add(fill);
  const group = new THREE.Group(); group.rotation.x = -Math.PI / 2; scene.add(group);   // spring axis z -> screen up
  const material = new THREE.MeshStandardMaterial({ color: 0x9fb4c7, metalness: 0.55, roughness: 0.38 });
  const mesh = new THREE.Mesh(new THREE.BufferGeometry(), material); group.add(mesh);
  let grid = null;
  three = { renderer, scene, camera, controls, group, mesh, material, get grid() { return grid; }, set grid(g) { grid = g; } };
  const render = () => renderer.render(scene, camera);
  three.render = render;
  controls.addEventListener("change", render);
  new ResizeObserver(() => {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); render();
  }).observe(canvas);
  theme3D();
}

function theme3D() {
  if (!three) return;
  three.scene.background = new THREE.Color(cssVar("--plot"));
  three.material.color = new THREE.Color(cssVar("--wire"));
  if (three.grid) three.grid.material.color = new THREE.Color(cssVar("--dim"));
  three.render();
}

async function loadMesh() {
  if (!three || !S.result || !S.result.ok) return;
  const seq = ++meshSeq;
  try {
    const m = await apiJson("/api/mesh", springPayload());
    if (seq !== meshSeq) return;
    const s = S.spring;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(m.verts, 3));
    geo.setAttribute("normal", new THREE.Float32BufferAttribute(m.normals, 3));
    geo.setIndex(m.faces);
    three.mesh.geometry.dispose(); three.mesh.geometry = geo;
    three.mesh.position.z = -s.free_length / 2;
    const od = s.mean_d + s.wire_d, size = Math.max(s.free_length, od);
    if (three.grid) { three.scene.remove(three.grid); three.grid.geometry.dispose(); }
    const step = 10 ** Math.floor(Math.log10(Math.max(od, 1e-3)));
    const gsize = Math.ceil(od * 2.5 / step) * step;
    const grid = new THREE.GridHelper(gsize, Math.max(2, Math.round(gsize / step)));
    grid.material.transparent = true; grid.material.opacity = 0.35; grid.material.color = new THREE.Color(cssVar("--dim"));
    grid.position.y = -s.free_length / 2;
    three.scene.add(grid); three.grid = grid;
    if (lastSize === null || Math.abs(size - lastSize) / lastSize > 0.25) {
      const dist = size * 2.2, el = 18 * Math.PI / 180, az = 35 * Math.PI / 180;
      three.camera.position.set(dist * Math.cos(el) * Math.sin(az), dist * Math.sin(el), dist * Math.cos(el) * Math.cos(az));
      three.camera.near = size / 100; three.camera.far = size * 100; three.camera.updateProjectionMatrix();
      three.controls.target.set(0, 0, 0); three.controls.update();
      lastSize = size;
    }
    meshStale = false;
    three.render();
  } catch (e) { /* compute() already shows the error */ }
}
const scheduleMesh = debounce(loadMesh, 200);

// ---- view tabs ----
let activeView = "3d", activePage = "design";
function showView(v) {
  activeView = v;
  document.querySelectorAll(".view-tab").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.view === v)));
  $("view-3d").hidden = v !== "3d"; $("view-drawing").hidden = v !== "drawing"; $("view-chart").hidden = v !== "chart";
  if (v === "3d" && meshStale) loadMesh();
  if (v === "drawing") drawDrawing();
  if (v === "chart") drawLoadChart();
  store.set("csd.view", v);
}
function showPage(p) {
  activePage = p;
  document.querySelectorAll(".page-tab").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.page === p)));
  $("page-design").hidden = p !== "design"; $("page-clamp").hidden = p !== "clamp";
  if (p === "clamp") clampRecompute(); else if (activeView === "3d") three && three.render();
  store.set("csd.page", p);
}

// ============================================================ CLAMPING PRESSURE
function parseSum(text) {
  const parts = text.replace(/\s/g, "").split(/[+,;]/).filter(Boolean);
  const vals = parts.map(Number);
  return vals.length && vals.every((v) => Number.isFinite(v) && v >= 0) ? vals : null;
}
function fmtTerm(mm) { const v = U.len(mm); return v ? (+v.toFixed(U.imperial ? 5 : 4)).toString() : "0"; }

function pushClampInputs() {
  const k = S.clamp, dec = U.lenDecimals();
  $("k-source").value = String(k.source);
  $("k-part").value = k.part_no || "";
  setNum("k-rate", U.rate(k.cat_rate), 4);
  setNum("k-free", U.len(k.cat_free), dec);
  setNum("k-solid", U.len(k.cat_solid), dec);
  $("k-n").value = k.n;
  setNum("k-disp", U.len(k.disp), dec);
  $("k-tol").value = k.tol_terms.map(fmtTerm).join(" + ");
  setNum("k-rtol", k.rate_tol * 100, 2);
  $("k-amode").value = String(k.area_mode);
  setNum("k-area", U.area(k.area), U.imperial ? 4 : 1);
  setNum("k-L", U.len(k.area_L), dec);
  setNum("k-W", U.len(k.area_W), dec);
  $("k-method").value = String(k.method);
  clampModes();
}

function clampModes() {
  const design = S.clamp.source === 0;
  ["k-rate", "k-free", "k-solid"].forEach((id) => { $(id).readOnly = design; });
  $("k-part-row").hidden = design;
  $("k-source-hint").textContent = design ? "Rate, free and solid height come from the Spring design page." : "Values from the spring catalog / datasheet.";
  document.querySelectorAll("[data-amode]").forEach((el) => { el.hidden = el.dataset.amode !== String(S.clamp.area_mode); });
  $("k-c-stress-card").hidden = !design;
}

let tolOk = true;
function readClampInputs() {
  const k = S.clamp;
  k.source = +$("k-source").value;
  k.part_no = $("k-part").value;
  if (k.source === 1) {
    k.cat_rate = keep(k.cat_rate, "k-rate", (x) => U.rate(x), (x) => U.rateIn(x), 4);
    k.cat_free = keepLen(k.cat_free, "k-free"); k.cat_solid = keepLen(k.cat_solid, "k-solid");
  }
  k.n = Math.max(1, Math.round(num("k-n")) || 1);
  k.disp = keepLen(k.disp, "k-disp");
  const terms = parseSum($("k-tol").value);
  tolOk = terms !== null;
  const shownTol = k.tol_terms.map(fmtTerm).join("+");
  if (terms && $("k-tol").value.replace(/\s/g, "") !== shownTol) k.tol_terms = terms.map((t) => U.lenIn(t));
  k.rate_tol = keep(k.rate_tol, "k-rtol", (x) => x * 100, (x) => (x || 0) / 100, 2);
  k.area_mode = +$("k-amode").value;
  k.area_L = keepLen(k.area_L, "k-L"); k.area_W = keepLen(k.area_W, "k-W");
  k.area = k.area_mode === 1 ? k.area_L * k.area_W
    : keep(k.area, "k-area", (x) => U.area(x), (x) => U.areaIn(x), U.imperial ? 4 : 1);
  k.method = +$("k-method").value;
}

let clampSeq = 0;
async function clampRecompute() {
  persist();
  const k = S.clamp, tol = k.tol_terms.reduce((a, b) => a + b, 0);
  $("k-tol-hint").textContent = `= ± ${U.fl(tol)}` + (tolOk ? "" : "   (can't read that – using the last value)");
  $("k-area-hint").textContent = k.area_mode === 1
    ? `= ${U.area(k.area).toLocaleString(undefined, { maximumFractionDigits: U.imperial ? 4 : 0 })} ${U.areaUnit}`
    : `≈ ${(Math.sqrt(k.area) / (U.imperial ? MM_PER_IN : 1)).toFixed(3)} ${U.lenUnit} square`;
  if (k.source === 0) {
    const r = S.result;
    if (r && r.ok) { setNum("k-rate", U.rate(r.rate), 4); setNum("k-free", U.len(S.spring.free_length), U.lenDecimals()); setNum("k-solid", U.len(r.solid_length), U.lenDecimals()); }
  }
  const body = {
    source: k.source === 0 ? "design" : "catalog", spring: k.source === 0 ? springPayload() : null,
    rate: k.cat_rate, free_length: k.cat_free, solid_length: k.cat_solid, n_springs: k.n,
    displacement: k.disp, disp_tol: tol, rate_tol: k.rate_tol, area: k.area, method: k.method,
  };
  const bad = [body.displacement, body.area, body.rate, body.free_length].some((v) => !(v > 0));
  if (bad) { clampBlank("Fill in rate, heights, displacement and area."); return; }
  const seq = ++clampSeq;
  try {
    const out = await apiJson("/api/clamp", body);
    if (seq !== clampSeq) return;
    S.clampOut = out; renderClamp();
    if (DEV.on) scheduleTrace();
  } catch (e) { if (seq === clampSeq) clampBlank(e.message); }
}
const scheduleClamp = debounce(clampRecompute, 120);

function clampBlank(msg) {
  ["k-c-p", "k-c-range", "k-c-force", "k-c-travel", "k-c-stress"].forEach((id) => setCard(id, "—"));
  ["k-c-p-s", "k-c-range-s", "k-c-force-s", "k-c-travel-s", "k-c-stress-s"].forEach((id) => { $(id).textContent = ""; });
  renderMessages($("k-messages"), [msg], [], "");
  $("k-chart").innerHTML = ""; S.clampOut = null;
}

function renderClamp() {
  const { result: r, input: c, wire_stress: ws } = S.clampOut;
  if (!r.ok && !r.force_total) { clampBlank(r.errors[0] || "Check the inputs."); return; }
  const psi = (m) => m / MPA_PER_PSI;
  setCard("k-c-p", `${psi(r.pressure).toFixed(2)} psi`);
  $("k-c-p-s").textContent = `${r.pressure.toFixed(4)} MPa  ·  ${(r.pressure * 1000).toFixed(1)} kPa  ·  ${(r.pressure * 1e6 / KGF / 1e4).toFixed(3)} kgf/cm²`;
  const lo = (1 - r.pressure_low / r.pressure) * 100, hi = (r.pressure_high / r.pressure - 1) * 100;
  const band = Math.abs(lo - hi) < 0.05 ? `±${hi.toFixed(1)}%` : `−${lo.toFixed(1)}% / +${hi.toFixed(1)}%`;
  setCard("k-c-range", `${psi(r.pressure_low).toFixed(1)} – ${psi(r.pressure_high).toFixed(1)} psi`);
  $("k-c-range-s").textContent = `${r.pressure_low.toFixed(4)} – ${r.pressure_high.toFixed(4)} MPa  ·  ${band}`;
  setCard("k-c-force", U.ff(r.force_total));
  $("k-c-force-s").textContent = `${c.n_springs} × ${U.ff(r.force_spring)}  ·  ${r.force_total.toLocaleString(undefined, { maximumFractionDigits: 1 })} N  ·  ${(r.force_total / KGF).toFixed(1)} kgf`;
  setCard("k-c-travel", `${Math.round(r.pct_travel * 100)}%  ·  ${r.status}`, r.errors.length ? "bad" : r.pct_travel > 0.8 ? "warn" : "good");
  $("k-c-travel-s").textContent = `of ${U.fl(r.travel)} travel  ·  height ${U.fl(r.height)}`;
  if (ws) {
    const ratio = ws.high / ws.allow;
    setCard("k-c-stress", U.fs(ws.high), ratio > 1 ? "bad" : ratio > 0.85 ? "warn" : "good");
    $("k-c-stress-s").textContent = `${Math.round(ratio * 100)}% of allowable ${U.fs(ws.allow)}  ·  nominal ${U.fs(ws.nominal)}`;
  }
  renderMessages($("k-messages"), r.errors, r.warnings, "No issues.");
  drawClampChart();
}

function drawClampChart() {
  const svg = $("k-chart"), o = S.clampOut;
  if (!o || !o.curve) { svg.innerHTML = ""; return; }
  const { curve: cv, result: r, input: c } = o, psi = 1 / MPA_PER_PSI;
  const xs = cv.x.map((v) => U.len(v));
  const ymax = Math.max(...cv.high, r.pressure_high) * psi * 1.08;
  const f = chartFrame(svg, [0, U.len(r.travel) * 1.04], [0, ymax], `Displacement (${U.lenUnit})`, "Pressure (psi)");
  let out = f.out;
  const P = (arr) => arr.map((v, i) => [f.sx(xs[i]), f.sy(v * psi)]);
  const lo = P(cv.low), hi = P(cv.high);
  out += `<polygon points="${[...hi, ...lo.slice().reverse()].map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ")}" style="fill:var(--band)"/>`;
  out += polyline(lo, "stroke:var(--accent)", 'stroke-dasharray="5 4"') + polyline(hi, "stroke:var(--accent)", 'stroke-dasharray="5 4"');
  out += polyline(P(cv.nominal), "stroke:var(--wire);stroke-width:2.5");
  const xsol = f.sx(U.len(r.travel));
  out += svgEl("line", { x1: xsol, y1: f.m.t, x2: xsol, y2: f.m.t + f.h, style: "stroke:var(--dim)", "stroke-dasharray": "5 4" });
  out += svgEl("text", { x: xsol - 6, y: f.m.t + 16, "text-anchor": "end", "font-size": "12", style: "fill:var(--dim)" }, "solid");
  const xm = f.sx(U.len(c.displacement));
  out += svgEl("line", { x1: xm, y1: f.sy(r.pressure_low * psi), x2: xm, y2: f.sy(r.pressure_high * psi), style: "stroke:var(--accent);stroke-width:2" });
  out += svgEl("circle", { cx: xm, cy: f.sy(r.pressure * psi), r: 6, style: "fill:var(--accent)" });
  svg.innerHTML = out;
}

function clampText() {
  const o = S.clampOut; if (!o) return "";
  const { result: r, input: c } = o, psi = (m) => (m / MPA_PER_PSI).toFixed(2), k = S.clamp;
  const method = META.methods[c.method].split(" (")[0].toLowerCase();
  return [
    "SPRINGS IN PARALLEL – CLAMPING PRESSURE",
    `Spring:               ${k.source === 0 ? "Spring design" : "Catalog spring"}${k.source === 1 && k.part_no ? `  (${k.part_no})` : ""}`,
    `Rate (each):          ${U.fr(c.rate)}`,
    `Free / solid height:  ${U.fl(c.free_length)} / ${U.fl(c.solid_length)}`,
    `Number of springs:    ${c.n_springs}`,
    `Displacement:         ${U.fl(c.displacement)}  (± ${U.fl(c.disp_tol)})`,
    `Rate tolerance:       ± ${(c.rate_tol * 100).toFixed(1)}%`,
    `Contact area:         ${U.area(c.area).toLocaleString(undefined, { maximumSignificantDigits: 4 })} ${U.areaUnit}`,
    `Height at load:       ${U.fl(r.height)}`,
    `% of travel:          ${(r.pct_travel * 100).toFixed(1)}%  (${r.status})`,
    `Force per spring:     ${U.ff(r.force_spring)}`,
    `Total force:          ${U.ff(r.force_total)}  (${r.force_total.toFixed(1)} N)`,
    `Pressure:             ${psi(r.pressure)} psi  (${r.pressure.toFixed(4)} MPa)`,
    `Pressure low / high:  ${psi(r.pressure_low)} / ${psi(r.pressure_high)} psi  (${method} method)`,
  ].join("\n");
}

// ============================================================ DEVELOPER MODE
// Same trace as the desktop app (coilspring/trace.py), computed by the server.
const DETAIL_KEYS = {
  "OD": "OD", "ID": "ID", "Mean diameter": "D", "Spring index C": "C", "Total coils": "Nt", "Active pitch": "p",
  "Pitch angle": "lam", "Max deflection": "dmax", "Stress correction Kb": "Kb", "Wire Sut": "Sut",
  "Allowable (solid)": "Sallow", "OD at solid": "od_s", "L₀ / D": "slender", "Natural freq.": "fn",
  "Wire length": "Lwire", "Mass": "mass",
};
const WORK_KEYS = { "Travel": "dw", "Length": "Lw", "Force": "Fw", "Stress": "tau_w", "% of allowable": "pct_w" };
const devBtn = (key, label) => key ? `<button class="devbtn" type="button" data-key="${key}" title="Show how ${esc(label)} is calculated">ƒ</button>` : "";

const DEV = { on: store.get("csd.dev", false), panel: true, trace: null, byKey: {}, current: "k", tab: "var", seq: 0 };

function fmtNum(v) {
  if (typeof v === "string") return v;
  if (v === null || v === undefined || !Number.isFinite(v)) return "∞";
  return (+v.toPrecision(6)).toString();
}
const traceVal = (v) => typeof v.value === "string" ? v.value : `${fmtNum(v.value)} ${v.unit}`.trim();

function shownValue(v) {
  if (typeof v.value !== "number") return "";
  const x = v.value;
  switch (v.kind) {
    case "len": return U.fl(x);
    case "force": return U.ff(x);
    case "rate": return U.fr(x);
    case "stress": case "mod": return U.fs(x);
    case "press": return `${(x / MPA_PER_PSI).toFixed(2)} psi`;
    case "mass": return U.imperial ? `${U.mass(x).toFixed(3)} oz` : "";
    default: return "";
  }
}

function setDev(on) {
  DEV.on = on; store.set("csd.dev", on);
  document.body.classList.toggle("dev", on);
  $("btn-dev").setAttribute("aria-pressed", String(on));
  showInspector(on);
}
function showInspector(on) {
  DEV.panel = on;
  $("inspector").hidden = !on;
  if (on) scheduleTrace();
  // the 3D canvas and charts resize themselves (ResizeObserver)
}

async function loadTrace() {
  if (!DEV.on || $("inspector").hidden || !S.spring || !springValid()) return;
  const seq = ++DEV.seq, k = S.clamp, tol = k.tol_terms.reduce((a, b) => a + b, 0);
  const clampBody = (k.disp > 0 && k.area > 0) ? {
    source: k.source === 0 ? "design" : "catalog", spring: k.source === 0 ? springPayload() : null,
    rate: k.cat_rate, free_length: k.cat_free, solid_length: k.cat_solid, n_springs: k.n,
    displacement: k.disp, disp_tol: tol, rate_tol: k.rate_tol, area: k.area, method: k.method,
  } : null;
  try {
    const out = await apiJson("/api/trace", { spring: springPayload(), dia_mode: S.diaMode, clamp: clampBody });
    if (seq !== DEV.seq) return;
    DEV.trace = out.vars; DEV.byKey = Object.fromEntries(out.vars.map((v) => [v.key, v]));
    renderInspector();
  } catch (e) {
    $("insp-detail").innerHTML = `<p class="msg bad">${esc(e.message)}</p>`;
  }
}
const scheduleTrace = debounce(loadTrace, 150);

function renderInspector() {
  if (!DEV.trace) return;
  const f = $("insp-filter").value.trim().toLowerCase();
  let html = "", group = null;
  for (const v of DEV.trace) {
    const hay = `${v.symbol} ${v.name} ${v.key}`.toLowerCase();
    if (f && !hay.includes(f)) continue;
    if (v.group !== group) { group = v.group; html += `<div class="insp-group">${esc(group)}</div>`; }
    const bad = v.matches === false;
    html += `<button type="button" class="insp-item${bad ? " bad" : ""}" role="option" data-goto="${v.key}" aria-selected="${v.key === DEV.current}">` +
            `<span><span class="sym">${esc(v.symbol)}</span>${esc(v.name)}</span><span class="val">${esc(traceVal(v))}${bad ? " ≠" : ""}</span></button>`;
  }
  $("insp-vars").innerHTML = html || `<p class="hint" style="padding:8px 10px">No variables match.</p>`;
  renderVar(DEV.current);
  renderLog();
}

function linkFor(key) {
  const v = DEV.byKey[key];
  if (!v) return esc(key);
  return `<button type="button" class="link" data-goto="${key}"><b>${esc(v.symbol)}</b> <span>${esc(v.name)} = ${esc(traceVal(v))}</span></button>`;
}

function renderVar(key) {
  const v = DEV.byKey[key], el = $("insp-detail");
  if (!v) { el.innerHTML = `<p class="hint">No value to show – the spring isn't valid right now, or this page isn't in use.</p>`; return; }
  const shown = shownValue(v), val = traceVal(v);
  let h = `<h3>${esc(v.symbol)} <span>– ${esc(v.name)}</span></h3><p class="sub">${esc(v.group)} · key <code>${esc(v.key)}</code></p><table>`;
  h += `<tr><td>Formula</td><td class="formula">${esc(v.formula)}</td></tr>`;
  if (v.subst) h += `<tr><td>With values</td><td>= ${esc(v.subst)}</td></tr>`;
  h += `<tr><td>Result</td><td>= <span class="result">${esc(val)}</span>` +
       (shown && shown.replace(/\s/g, "") !== val.replace(/\s/g, "") ? ` <span class="hint">(shown as ${esc(shown)})</span>` : "") + `</td></tr>`;
  if (v.matches === true) h += `<tr><td></td><td class="ok">✓ Matches the value the app uses (<code>${esc(v.check_label)}</code>)</td></tr>`;
  if (v.matches === false) h += `<tr><td></td><td class="no">≠ The app uses ${esc(fmtNum(v.check))} (<code>${esc(v.check_label)}</code>). The code has changed – update the formula text in trace.py to match.</td></tr>`;
  h += `</table>`;
  if (v.note) h += `<p style="color:var(--muted)">${esc(v.note)}</p>`;
  if (v.deps.length) h += `<p class="label">Depends on</p>` + v.deps.map(linkFor).join("");
  if (v.used_by.length) h += `<p class="label">Used by</p>` + v.used_by.map(linkFor).join("");
  if (v.sources.length) {
    h += `<p class="label">Source code</p>`;
    for (const [file, line, code] of v.sources)
      h += `<p class="where">${esc(file)}${line ? `, line ${line}` : ""}</p><pre class="code">${esc(code)}</pre>`;
  }
  el.innerHTML = h;
}

function renderLog() {
  const lines = ["# Coil Spring Designer – calculation log (internal units: mm, N, MPa)", ""];
  let group = null;
  for (const v of DEV.trace) {
    if (v.group !== group) { group = v.group; lines.push("", `## ${group}`); }
    const check = v.matches === true ? "  ✓" : v.matches === false ? `  ≠ app uses ${fmtNum(v.check)}` : "";
    const loc = v.sources.filter((s) => s[1]).map((s) => `${s[0]}:${s[1]}`).join(", ");
    const sym = v.symbol.padEnd(12);
    if (v.formula === "input" || v.formula === "material table" || !v.subst) {
      lines.push(`${sym} = ${traceVal(v).padEnd(22)} ${v.formula}${loc ? `   [${loc}]` : ""}${check}`);
    } else {
      lines.push(`${sym} = ${v.formula}`, `${"".padEnd(12)} = ${v.subst}`, `${"".padEnd(12)} = ${traceVal(v)}${loc ? `   [${loc}]` : ""}${check}`);
    }
  }
  $("insp-log").textContent = lines.join("\n");
}

function selectVar(key) {
  DEV.current = key;
  showITab("var");
  document.querySelectorAll("#insp-vars .insp-item").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.goto === key)));
  const it = document.querySelector(`#insp-vars .insp-item[data-goto="${key}"]`);
  if (it) it.scrollIntoView({ block: "nearest" });
  renderVar(key);
}
function showITab(t) {
  DEV.tab = t;
  document.querySelectorAll(".insp-tab").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.itab === t)));
  $("insp-detail").hidden = t !== "var"; $("insp-logbox").hidden = t !== "log";
}

function wireDev() {
  $("btn-dev").addEventListener("click", () => setDev(!DEV.on));
  $("insp-close").addEventListener("click", () => showInspector(false));
  document.addEventListener("click", (e) => {
    const b = e.target.closest(".devbtn");
    if (b) {
      e.preventDefault();
      if (!DEV.on) setDev(true);
      if ($("inspector").hidden) showInspector(true);
      DEV.current = b.dataset.key;
      if (DEV.trace) selectVar(b.dataset.key); else scheduleTrace();
      return;
    }
    const g = e.target.closest("[data-goto]");
    if (g && $("inspector").contains(g)) selectVar(g.dataset.goto);
  });
  $("insp-filter").addEventListener("input", renderInspector);
  document.querySelectorAll(".insp-tab").forEach((b) => b.addEventListener("click", () => showITab(b.dataset.itab)));
  $("insp-copy").addEventListener("click", async () => toast((await copyText($("insp-log").textContent)) ? "Calculation log copied" : "Couldn't copy – select the text manually"));
  // drag the top edge to resize the panel
  const grip = $("insp-grip");
  grip.addEventListener("pointerdown", (e) => {
    grip.setPointerCapture(e.pointerId);
    const startY = e.clientY, startH = $("inspector").getBoundingClientRect().height;
    const move = (ev) => {
      const h = Math.max(180, Math.min(window.innerHeight * 0.75, startH + startY - ev.clientY));
      document.documentElement.style.setProperty("--insp-h", `${h}px`);
    };
    const up = () => { grip.removeEventListener("pointermove", move); grip.removeEventListener("pointerup", up);
      try { localStorage.setItem("csd.inspH", getComputedStyle(document.documentElement).getPropertyValue("--insp-h")); } catch (err) {} };
    grip.addEventListener("pointermove", move); grip.addEventListener("pointerup", up);
  });
  try { const h = localStorage.getItem("csd.inspH"); if (h) document.documentElement.style.setProperty("--insp-h", h); } catch (e) {}
  setDev(DEV.on);
}

// ============================================================ TOOLBAR
function defaultName(ext) {
  const s = S.spring;
  return `spring_${U.len(s.wire_d).toFixed(3)}x${U.len(s.mean_d + s.wire_d).toFixed(3)}OD_${U.len(s.free_length).toFixed(3)}L_${U.lenUnit}.${ext}`;
}

async function exportCad(fmt) {
  readSpringInputs();
  const btn = $(fmt === "step" ? "btn-step" : "btn-stl"), label = btn.textContent;
  btn.disabled = true; btn.textContent = "Building…";
  try {
    const r = await api(`/api/export/${fmt}`, springPayload());
    download(await r.blob(), defaultName(fmt));
    toast(`Exported ${fmt.toUpperCase()} (geometry in mm)`);
  } catch (e) { toast(`Export failed: ${e.message}`, true); }
  finally { btn.textContent = label; btn.disabled = !(S.result && S.result.ok); }
}

function saveDesign() {
  readSpringInputs();
  const data = { app: "Coil Spring Designer", version: "1.0", units_mm_N: true, spring: springPayload(), clamp: S.clamp };
  download(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }), defaultName("spring.json"));
}

async function openDesign(file) {
  try {
    const data = JSON.parse(await file.text());
    const sp = data.spring;
    if (!sp || !(sp.wire_d > 0)) throw new Error("No spring found in that file.");
    let mat = sp.material;
    if (!META.materials.some((m) => m.name === mat)) { toast(`“${mat}” isn't in the material list – using ${META.materials[0].name}.`, true); mat = META.materials[0].name; }
    const { work_length, ...rest } = sp;
    S.spring = { ...S.spring, ...rest, material: mat };
    S.op = work_length == null ? { ...S.op, use: false } : { use: true, kind: "travel", val: sp.free_length - work_length };
    if (data.clamp) S.clamp = { ...S.clamp, ...data.clamp };
    pushSpringInputs(); pushClampInputs(); recompute(); clampRecompute();
    toast(`Opened ${file.name}`);
  } catch (e) { toast(`Couldn't open that file: ${e.message}`, true); }
}

function specText() {
  const s = S.spring, r = S.result; if (!r) return "";
  const lines = [
    "COMPRESSION SPRING SPECIFICATION",
    `Material:        ${s.material}`, `Wire diameter:   ${U.fl(s.wire_d)}`,
    `Outside dia:     ${U.fl(s.mean_d + s.wire_d)}`, `Inside dia:      ${U.fl(s.mean_d - s.wire_d)}`,
    `Free length:     ${U.fl(s.free_length)}`, `Active coils:    ${s.active_coils}`,
    `Total coils:     ${+r.total_coils.toFixed(2)}`, `Ends:            ${s.end_type}`,
    `Wind:            ${s.right_hand ? "Right hand" : "Left hand"}`, `Rate:            ${U.fr(r.rate)}`,
    `Solid height:    ${U.fl(r.solid_length)}`, `Load at solid:   ${U.ff(r.force_solid)}`,
    `Stress at solid: ${U.fs(r.stress_solid)}  (allow ${U.fs(r.allow)})`,
  ];
  const wl = workLength();
  if (wl !== null && r.work_force !== null) lines.push(`Load at ${U.fl(wl)} (travel ${U.fl(r.work_deflection)}): ${U.ff(r.work_force)}`);
  return lines.join("\n");
}

function newDesign() {
  S.spring = { ...META.default_spring }; delete S.spring.work_length;
  S.diaMode = "od"; S.op = { use: false, kind: "travel", val: 0 };
  S.target = { mode: "rate", rate: null, force: null, distance: null, kind: "deflection" };
  initTargets(); pushSpringInputs(); $("solve-info").textContent = ""; lastSize = null; recompute();
}

function initTargets() {
  // sensible starting values from the current spring (like the desktop app)
  const s = S.spring, G = material().G;
  const k = G * s.wire_d ** 4 / (8 * s.mean_d ** 3 * s.active_coils);
  if (!(S.target.rate > 0)) S.target.rate = k;
  if (!(S.target.force > 0) || !(S.target.distance > 0)) { S.target.distance = s.free_length * 0.25; S.target.force = k * S.target.distance; }
}

// ---- theme ----
let themeChoice = store.get("csd.themeChoice", null) || (() => { try { return localStorage.getItem("csd.theme") || "Dark"; } catch (e) { return "Dark"; } })();
const mq = matchMedia("(prefers-color-scheme: dark)");
function applyTheme() {
  const dark = themeChoice === "Dark" || (themeChoice === "Follow system" && mq.matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  try { localStorage.setItem("csd.theme", themeChoice); } catch (e) {}
  theme3D();
}
mq.addEventListener("change", () => { if (themeChoice === "Follow system") applyTheme(); });

// ============================================================ WIRING
function wire() {
  const onSpring = () => { readSpringInputs(); scheduleCompute(); };
  ["wire_d", "dia", "active", "free_len", "work-val", "target-k", "target-f", "target-x"].forEach((id) => $(id).addEventListener("input", onSpring));
  ["end_type", "hand", "snap"].forEach((id) => $(id).addEventListener("change", onSpring));
  $("material").addEventListener("change", () => { readSpringInputs(); fillWireChart(); scheduleCompute(); });
  $("wire-std").addEventListener("change", (e) => {
    const d = parseFloat(e.target.value); e.target.value = "";
    if (d > 0) { setNum("wire_d", U.len(d), U.lenDecimals()); onSpring(); }
  });
  document.querySelectorAll('input[name="dia-mode"]').forEach((r) => r.addEventListener("change", () => {
    S.diaMode = r.value; $("dia-label").textContent = { od: "OD", id: "ID", mean: "Mean Ø" }[S.diaMode];
    setNum("dia", U.len(diaValue()), U.lenDecimals()); updateInfoLines();
  }));
  $("target-mode").addEventListener("change", () => { readSpringInputs(); showTargetRows(); $("solve-info").textContent = ""; updateTargetHint(); persist(); });
  $("target-xkind").addEventListener("change", () => {        // same spring position, other way round
    const v = U.lenIn(num("target-x")), L0 = S.spring.free_length;
    if (L0 - v > 0) setNum("target-x", U.len(L0 - v), U.lenDecimals());
    readSpringInputs(); updateTargetHint(); persist();
  });
  ["target-f", "target-x", "target-k"].forEach((id) => $(id).addEventListener("input", () => { $("solve-info").textContent = ""; }));
  $("solve-coils").addEventListener("click", () => solve("coils"));
  $("solve-wire").addEventListener("click", () => solve("wire"));
  $("use-work").addEventListener("change", () => {
    readSpringInputs();
    if (S.op.use && S.result && S.result.ok) {
      const pos = (S.spring.free_length + S.result.solid_length) / 2;
      S.op.val = S.op.kind === "travel" ? S.spring.free_length - pos : pos;
    }
    pushSpringInputs(); recompute();
  });
  $("work-kind").addEventListener("change", () => {
    const L0 = S.spring.free_length, v = U.lenIn(num("work-val"));
    setNum("work-val", U.len(Math.max(L0 - v, 0)), U.lenDecimals());
    readSpringInputs(); pushSpringInputs(); recompute();
  });

  document.querySelectorAll(".view-tab").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
  document.querySelectorAll(".page-tab").forEach((b) => b.addEventListener("click", () => showPage(b.dataset.page)));

  const onClamp = () => { readClampInputs(); clampModes(); scheduleClamp(); };
  $("k-source").addEventListener("change", () => {
    // back to catalog: show the saved catalog spring, not the design's numbers
    if ($("k-source").value === "1" && S.clamp.source === 0) {
      setNum("k-rate", U.rate(S.clamp.cat_rate), 4);
      setNum("k-free", U.len(S.clamp.cat_free), U.lenDecimals());
      setNum("k-solid", U.len(S.clamp.cat_solid), U.lenDecimals());
    }
  });
  ["k-part", "k-rate", "k-free", "k-solid", "k-n", "k-disp", "k-tol", "k-rtol", "k-area", "k-L", "k-W"].forEach((id) => $(id).addEventListener("input", onClamp));
  ["k-source", "k-amode", "k-method"].forEach((id) => $(id).addEventListener("change", onClamp));
  $("k-copy").addEventListener("click", async () => toast((await copyText(clampText())) ? "Clamping results copied" : "Couldn't copy – select the text manually", false));

  $("units").addEventListener("change", () => {
    // state is already in mm / N from the input events; re-reading rounded display values would drift
    U = new Units(+$("units").value); store.set("csd.units", U.system);
    applyUnitLabels(); pushSpringInputs(); pushClampInputs(); recompute(); clampRecompute();
    if (DEV.trace) renderInspector();
  });
  $("theme").addEventListener("change", () => { themeChoice = $("theme").value; applyTheme(); });
  $("btn-new").addEventListener("click", newDesign);
  $("btn-save").addEventListener("click", saveDesign);
  $("btn-open").addEventListener("click", () => $("file-open").click());
  $("file-open").addEventListener("change", (e) => { if (e.target.files[0]) openDesign(e.target.files[0]); e.target.value = ""; });
  $("btn-copy").addEventListener("click", async () => toast((await copyText(specText())) ? "Specification copied" : "Couldn't copy – select the text manually"));
  $("btn-step").addEventListener("click", () => exportCad("step"));
  $("btn-stl").addEventListener("click", () => exportCad("stl"));

  const redraw = debounce(() => { if (activeView === "drawing") drawDrawing(); if (activeView === "chart") drawLoadChart(); if (activePage === "clamp") drawClampChart(); }, 60);
  new ResizeObserver(redraw).observe($("drawing")); new ResizeObserver(redraw).observe($("loadchart")); new ResizeObserver(redraw).observe($("k-chart"));
}

async function main() {
  META = await apiJson("/api/meta");
  fillStaticSelects();
  const saved = store.get("csd.state", null);
  S.spring = { ...META.default_spring }; delete S.spring.work_length;
  if (saved && saved.spring && saved.spring.wire_d > 0) {
    Object.assign(S, { diaMode: saved.diaMode || "od", target: { ...S.target, ...saved.target }, snap: saved.snap !== false,
                       op: { ...S.op, ...saved.op }, clamp: { ...S.clamp, ...saved.clamp } });
    S.spring = { ...S.spring, ...saved.spring };
    if (!META.materials.some((m) => m.name === S.spring.material)) S.spring.material = META.materials[0].name;
  }
  initTargets();
  $("units").value = String(U.system);
  $("theme").value = themeChoice;
  applyUnitLabels();
  pushSpringInputs(); pushClampInputs();
  try { init3D(); } catch (e) { $("view-3d").innerHTML = '<p class="view-note">3D view needs WebGL, which this browser has turned off.</p>'; }
  applyTheme();
  wire();
  wireDev();
  showView(store.get("csd.view", "3d"));
  showPage(store.get("csd.page", "design"));
  await recompute();
}

main().catch((e) => {
  document.body.insertAdjacentHTML("afterbegin", `<p class="msg bad" style="padding:12px">Couldn't reach the spring server: ${esc(e.message)}. Is run_web still running?</p>`);
});
