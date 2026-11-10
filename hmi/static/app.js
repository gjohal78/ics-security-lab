/* ics-security-lab HMI: polls /api/state and renders the page. */
"use strict";

/* ===================== Configuration ===================== */
const CONFIG = {
  endpoint: "/api/state",
  pollMs: 1000,          // how often to ask the backend
  timeoutMs: 2500,       // give up on a request after this long
  staleAfterS: 3,        // data older than this is shown as STALE
  levelMin: 0,           // scale of the tank graphic and trend y-axis
  levelMax: 100,
  levelUnit: "%",
  levelDecimals: 1,
  // Threshold ticks drawn on the tank and trend. DISPLAY ONLY: the real
  // setpoints live in the PLC program, so keep these in sync with it
  // (or set marks to [] to hide them).
  marks: [
    { key: "hihi", label: "HH", value: 95 },
    { key: "hi",   label: "H",  value: 85 },
    { key: "lo",   label: "L",  value: 15 },
  ],
  tableRows: 20,         // rows in the accessible table view
};

/* Alarm definitions, in priority order. `field` is the key in `current`. */
const ALARMS = [
  { field: "trip_hihi", name: "HH level trip", desc: "Level reached 95 % — latched until operator reset at the PLC", severity: "critical" },
  { field: "alarm_hi",  name: "High level",    desc: "Level above high alarm limit",       severity: "warning" },
  { field: "alarm_lo",  name: "Low level",     desc: "Level below low alarm limit",        severity: "warning" },
];

/* ===================== Small helpers ===================== */
const $ = (id) => document.getElementById(id);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const fmtLevel = (v) => (Number.isFinite(v) ? v.toFixed(CONFIG.levelDecimals) : "—");
const isOn = (v) => v === true || v === 1 || v === "1" || v === "true";

/**
 * History timestamps may arrive as epoch seconds, epoch milliseconds,
 * or ISO strings depending on the backend. Normalise to epoch ms.
 */
function toMs(t) {
  if (typeof t === "number") return t > 1e12 ? t : t * 1000;
  const parsed = Date.parse(t);
  return Number.isNaN(parsed) ? NaN : parsed;
}
const fmtTime = (ms) =>
  new Date(ms).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });

/* ===================== Static setup ===================== */
$("level-unit").textContent = CONFIG.levelUnit;

// Build the alarm rows once; updates only toggle classes and text.
const alarmEls = {};
const ICONS = {
  // Triangle with "!" — shape differs from the circle used for "normal",
  // so state is never conveyed by colour alone.
  active: '<svg class="icon" viewBox="0 0 24 24"><path d="M12 2 L23 21 H1 Z" fill="currentColor"/><path d="M12 9 V14 M12 17 V17.5" stroke="var(--panel)" stroke-width="2.4" stroke-linecap="round"/></svg>',
  normal: '<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2"/></svg>',
};
for (const a of ALARMS) {
  const li = document.createElement("li");
  li.className = `alarm ${a.severity}`;
  li.innerHTML = `<span class="icon-slot"></span><div><div class="name"></div><div class="desc"></div></div><span class="state"></span>`;
  li.querySelector(".name").textContent = a.name;   // static text, but keep the habit
  li.querySelector(".desc").textContent = a.desc;
  $("alarms").appendChild(li);
  alarmEls[a.field] = li;
}

// Threshold ticks on the tank graphic.
const TANK = { top: 70, bottom: 270, left: 140, right: 300 };
const levelToY = (v) => {
  const f = (clamp(v, CONFIG.levelMin, CONFIG.levelMax) - CONFIG.levelMin) / (CONFIG.levelMax - CONFIG.levelMin);
  return TANK.bottom - f * (TANK.bottom - TANK.top);
};
for (const m of CONFIG.marks) {
  const y = levelToY(m.value);
  const ns = "http://www.w3.org/2000/svg";
  const line = document.createElementNS(ns, "line");
  Object.entries({ x1: TANK.left - 10, x2: TANK.left, y1: y, y2: y, stroke: "var(--ink-3)", "stroke-width": 2 })
    .forEach(([k, v]) => line.setAttribute(k, v));
  const text = document.createElementNS(ns, "text");
  Object.entries({ x: TANK.left - 14, y: y + 4, "font-size": 11, fill: "var(--ink-3)", "text-anchor": "end" })
    .forEach(([k, v]) => text.setAttribute(k, v));
  text.textContent = `${m.label} ${m.value}`;
  $("marks").append(line, text);
}

/* ===================== Rendering: live values ===================== */
let lastState = null;     // last good payload, kept so we can redraw on resize
let lastOkAt = 0;         // when we last heard from the backend (ms)

function renderConnection({ reachable, online, error, age }) {
  const badge = $("badge"), text = $("badge-text"), banner = $("banner");
  const stale = !reachable || !online || !Number.isFinite(age) || age > CONFIG.staleAfterS;
  document.body.classList.toggle("is-stale", stale);

  badge.className = "badge";
  if (!reachable) {
    badge.classList.add("offline"); text.textContent = "HMI BACKEND UNREACHABLE";
  } else if (!online) {
    badge.classList.add("offline"); text.textContent = "PLC OFFLINE";
  } else if (stale) {
    badge.classList.add("stale"); text.textContent = "STALE DATA";
  } else {
    badge.classList.add("online"); text.textContent = "PLC ONLINE";
  }

  $("age").textContent = Number.isFinite(age) ? `updated ${age.toFixed(1)} s ago` : "—";

  // Show the error string from the API (as text, never HTML).
  const msg = !reachable ? `Cannot reach ${CONFIG.endpoint}: ${error}` : error;
  banner.textContent = msg || "";
  banner.classList.toggle("show", Boolean(msg));
}

function renderCurrent(cur) {
  const level = Number(cur.level);
  const pumpOn = isOn(cur.pump);

  // Tank fill
  const y = Number.isFinite(level) ? levelToY(level) : TANK.bottom;
  $("liquid").setAttribute("y", y);
  $("liquid").setAttribute("height", TANK.bottom - y);
  $("level").textContent = fmtLevel(level);

  // Pump: filled dark when running, hollow when stopped (shape + text, not colour)
  $("pump-body").setAttribute("fill", pumpOn ? "var(--run)" : "var(--panel)");
  $("pump-arrow").setAttribute("stroke", pumpOn ? "var(--panel)" : "var(--steel)");
  $("pump-arrow").setAttribute("fill", pumpOn ? "var(--panel)" : "none");
  $("pump-text").textContent = pumpOn ? "RUNNING" : "STOPPED";
  $("pump-value").textContent = pumpOn ? "Running" : "Stopped";

  // Alarms
  for (const a of ALARMS) {
    const active = isOn(cur[a.field]);
    const li = alarmEls[a.field];
    li.classList.toggle("active", active);
    li.querySelector(".icon-slot").innerHTML = active ? ICONS.active : ICONS.normal; // our own constant SVG
    li.querySelector(".state").textContent = active ? "ACTIVE" : "Normal";
  }
}

function renderTable(rows) {
  const body = $("table-body");
  body.replaceChildren();
  for (const r of rows.slice(-CONFIG.tableRows).reverse()) {
    const tr = document.createElement("tr");
    for (const cell of [fmtTime(r.t), `${fmtLevel(r.level)} ${CONFIG.levelUnit}`, r.pump ? "Running" : "Stopped"]) {
      const td = document.createElement("td");
      td.textContent = cell;
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }
}

/* ===================== Rendering: trend chart ===================== */
/*
 * One canvas, two stacked plots sharing the time axis:
 *   - top: level line (0..levelMax)
 *   - bottom: a thin strip that is filled where the pump was running.
 * Level and pump have different units, so they get separate plots rather
 * than a confusing second y-axis.
 */
const canvas = $("trend");
const ctx = canvas.getContext("2d");
let series = [];          // [{t, level, pump}] normalised history
let geom = null;          // plot geometry from the last draw, used by hover
let hoverIdx = null;

function parseHistory(history) {
  if (!Array.isArray(history)) return [];
  return history
    .map(([t, level, pump]) => ({ t: toMs(t), level: Number(level), pump: isOn(pump) }))
    .filter((r) => Number.isFinite(r.t) && Number.isFinite(r.level))
    .sort((a, b) => a.t - b.t);
}

function drawTrend() {
  // Match the canvas backing store to its CSS size for sharp lines on HiDPI.
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth, H = canvas.clientHeight;
  canvas.width = Math.round(W * dpr);
  canvas.height = Math.round(H * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);

  const pad = { left: 44, right: 30, top: 10 };   // right gutter holds the HH/H/L labels
  const stripH = 18, gap = 26, axisH = 22;
  const plot = { x: pad.left, y: pad.top, w: W - pad.left - pad.right, h: H - pad.top - stripH - gap - axisH };
  const strip = { x: plot.x, y: plot.y + plot.h + gap, w: plot.w, h: stripH };
  geom = { plot, strip };

  ctx.font = "11px system-ui, sans-serif";
  const ink3 = css("--ink-3"), grid = css("--grid");

  // Y grid + labels
  ctx.textAlign = "right"; ctx.textBaseline = "middle";
  const yOf = (v) => plot.y + plot.h - ((v - CONFIG.levelMin) / (CONFIG.levelMax - CONFIG.levelMin)) * plot.h;
  for (let i = 0; i <= 4; i++) {
    const v = CONFIG.levelMin + (i / 4) * (CONFIG.levelMax - CONFIG.levelMin);
    const y = Math.round(yOf(v)) + 0.5;
    ctx.strokeStyle = grid; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(plot.x, y); ctx.lineTo(plot.x + plot.w, y); ctx.stroke();
    ctx.fillStyle = ink3; ctx.fillText(`${v}${CONFIG.levelUnit}`, plot.x - 6, y);
  }

  // Threshold reference lines (dashed, muted, labelled in the right gutter)
  ctx.textAlign = "left"; ctx.textBaseline = "middle";
  for (const m of CONFIG.marks) {
    const y = Math.round(yOf(m.value)) + 0.5;
    ctx.setLineDash([4, 4]); ctx.strokeStyle = ink3;
    ctx.beginPath(); ctx.moveTo(plot.x, y); ctx.lineTo(plot.x + plot.w, y); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = ink3; ctx.fillText(m.label, plot.x + plot.w + 6, y);
  }

  // Pump strip label + outline
  ctx.textAlign = "right"; ctx.textBaseline = "middle"; ctx.fillStyle = ink3;
  ctx.fillText("Pump", strip.x - 6, strip.y + strip.h / 2);
  ctx.strokeStyle = grid;
  ctx.strokeRect(strip.x + 0.5, strip.y + 0.5, strip.w - 1, strip.h - 1);

  if (series.length < 2) {
    ctx.textAlign = "center"; ctx.fillStyle = ink3;
    ctx.fillText("Waiting for history…", plot.x + plot.w / 2, plot.y + plot.h / 2);
    return;
  }

  const t0 = series[0].t, t1 = series[series.length - 1].t;
  const xOf = (t) => plot.x + ((t - t0) / (t1 - t0 || 1)) * plot.w;
  geom.xOf = xOf; geom.yOf = yOf;

  // Pump running periods: each sample's state holds until the next sample.
  // Merge consecutive "on" samples into one rect so there are no seams.
  ctx.fillStyle = css("--run");
  for (let i = 0; i < series.length - 1; i++) {
    if (!series[i].pump) continue;
    let j = i;
    while (j < series.length - 1 && series[j].pump) j++;
    const xa = xOf(series[i].t), xb = xOf(series[j].t);
    ctx.fillRect(xa, strip.y + 3, Math.max(2, xb - xa), strip.h - 6);
    i = j;
  }

  // Level line
  ctx.strokeStyle = css("--liquid"); ctx.lineWidth = 2; ctx.lineJoin = "round";
  ctx.beginPath();
  series.forEach((r, i) => {
    const x = xOf(r.t), y = yOf(clamp(r.level, CONFIG.levelMin, CONFIG.levelMax));
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.stroke();

  // X axis time labels (about one every 110 px)
  ctx.fillStyle = ink3; ctx.textBaseline = "top";
  const n = Math.max(2, Math.floor(plot.w / 110));
  for (let i = 0; i <= n; i++) {
    const t = t0 + (i / n) * (t1 - t0);
    ctx.textAlign = i === 0 ? "left" : i === n ? "right" : "center";
    ctx.fillText(fmtTime(t), xOf(t), strip.y + strip.h + 6);
  }

  // Hover crosshair + marker
  if (hoverIdx != null && series[hoverIdx]) {
    const r = series[hoverIdx];
    const x = Math.round(xOf(r.t)) + 0.5, y = yOf(clamp(r.level, CONFIG.levelMin, CONFIG.levelMax));
    ctx.strokeStyle = css("--ink-2"); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, plot.y); ctx.lineTo(x, strip.y + strip.h); ctx.stroke();
    ctx.fillStyle = css("--liquid"); ctx.strokeStyle = css("--panel"); ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  }
}

// Hover: snap to the nearest sample (binary search on time) and show a tooltip.
canvas.addEventListener("mousemove", (e) => {
  if (!geom || !geom.xOf || series.length < 2) return;
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const t0 = series[0].t, t1 = series[series.length - 1].t;
  const t = t0 + ((mx - geom.plot.x) / geom.plot.w) * (t1 - t0);
  let lo = 0, hi = series.length - 1;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; series[mid].t < t ? (lo = mid) : (hi = mid); }
  hoverIdx = Math.abs(series[lo].t - t) < Math.abs(series[hi].t - t) ? lo : hi;
  drawTrend();

  const r = series[hoverIdx], tip = $("tooltip");
  tip.replaceChildren();
  const line1 = document.createElement("div"); line1.className = "t"; line1.textContent = fmtTime(r.t);
  const line2 = document.createElement("div"); line2.className = "num";
  line2.textContent = `Level ${fmtLevel(r.level)} ${CONFIG.levelUnit} · Pump ${r.pump ? "running" : "stopped"}`;
  tip.append(line1, line2);
  tip.style.display = "block";
  const x = geom.xOf(r.t);
  // Keep the tooltip inside the chart: flip to the left near the right edge.
  const left = x + 12 + tip.offsetWidth > canvas.clientWidth ? x - 12 - tip.offsetWidth : x + 12;
  tip.style.left = `${left}px`;
  tip.style.top = `${geom.plot.y + 4}px`;
});
canvas.addEventListener("mouseleave", () => { hoverIdx = null; $("tooltip").style.display = "none"; drawTrend(); });
window.addEventListener("resize", drawTrend);
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", drawTrend);

/* ===================== Polling loop ===================== */
async function fetchState() {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), CONFIG.timeoutMs);
  try {
    const res = await fetch(CONFIG.endpoint, { cache: "no-store", signal: ctrl.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

async function tick() {
  try {
    const s = await fetchState();
    lastState = s; lastOkAt = Date.now();
    renderConnection({ reachable: true, online: Boolean(s.online), error: s.error, age: s.age == null ? NaN : Number(s.age) });  // age is null before the first good poll
    if (s.current) renderCurrent(s.current);
    series = parseHistory(s.history);
    if (hoverIdx != null && hoverIdx >= series.length) hoverIdx = null;
    renderTable(series);
    drawTrend();
  } catch (err) {
    // Backend down: keep the last picture on screen (greyed out) and say so.
    const age = lastOkAt ? (Date.now() - lastOkAt) / 1000 + (Number(lastState?.age) || 0) : NaN;
    renderConnection({ reachable: false, online: false, error: err.name === "AbortError" ? "timed out" : err.message, age });
  } finally {
    // setTimeout (not setInterval) so a slow request never overlaps the next one.
    setTimeout(tick, CONFIG.pollMs);
  }
}

drawTrend();
tick();
