/* ═══════════════════════════════════════════════════════════════
   NSR-AEGIS  ·  Panama Canal Digital Twin
   app.js — Navigation, Forecast, Charts
════════════════════════════════════════════════════════════════ */

"use strict";

/* ── Color palette (mirrors CSS tokens) ─────────────────────── */
const C = {
  ink:    "#07131e",
  deep:   "#030d16",
  navy:   "#0a2840",
  blue:   "#0b3a5d",
  canal:  "#0092c4",
  green:  "#0fa882",
  brass:  "#d4a017",
  clay:   "#c0412c",
  paper:  "#f2f6f9",
  bone:   "#dce7ef",
  white:  "#ffffff",
  line:   "rgba(7,19,30,.10)",
  lineDk: "rgba(255,255,255,.10)",
};

/* ── State ───────────────────────────────────────────────────── */
const state = {
  t: 0,
  activePanel: "home",
  lakeLevel: 24.9,
  maxDraft: 13.6,
  stress: 34.0,
  precipitation: 210,
  avgTemp: 28.7,
  sstAnomaly: 0.8,
  analysis: null,
};

/* ── DOM refs ────────────────────────────────────────────────── */
const sidenav        = document.getElementById("sidenav");
const sidenavOverlay = document.getElementById("sidenavOverlay");
const mobileToggle   = document.getElementById("mobileNavToggle");
const allPanels      = Array.from(document.querySelectorAll(".panel[data-panel]"));
const allNavBtns     = Array.from(document.querySelectorAll(".sidenav-item[data-panel]"));
const predForm       = document.getElementById("predictionForm");

/* ══════════════════════════════════════════════════════════════
   ACCORDION NAV
════════════════════════════════════════════════════════════════ */
function initAccordion() {
  document.querySelectorAll(".sidenav-section-label").forEach(label => {
    label.addEventListener("click", () => {
      const group = label.closest(".nav-group");
      const isOpen = group.classList.contains("open");

      // Close all groups
      document.querySelectorAll(".nav-group").forEach(g => {
        g.classList.remove("open");
        g.querySelector(".sidenav-section-label").setAttribute("aria-expanded", "false");
      });

      // Open clicked one if it was closed
      if (!isOpen) {
        group.classList.add("open");
        label.setAttribute("aria-expanded", "true");
      }
    });
  });
}

/* ══════════════════════════════════════════════════════════════
   PANEL SWITCHING
════════════════════════════════════════════════════════════════ */
function setPanel(name) {
  state.activePanel = name;

  // Show/hide panels
  allPanels.forEach(p => {
    const active = p.dataset.panel === name;
    p.classList.toggle("active", active);
  });

  // Highlight nav button + open its group
  allNavBtns.forEach(btn => {
    btn.classList.toggle("active", btn.dataset.panel === name);
  });

  // Auto-open the group containing the active item
  const activeBtn = allNavBtns.find(b => b.dataset.panel === name);
  if (activeBtn) {
    const group = activeBtn.closest(".nav-group");
    if (group && !group.classList.contains("open")) {
      // Close all, open this one
      document.querySelectorAll(".nav-group").forEach(g => g.classList.remove("open"));
      group.classList.add("open");
      group.querySelector(".sidenav-section-label").setAttribute("aria-expanded", "true");
    }
  }

  // Scroll to top
  window.scrollTo({ top: 0 });
  closeSidenav();

  // Redraw charts for the newly active panel
  requestAnimationFrame(drawAllCharts);
}

/* ── Mobile nav ─────────────────────────────────────────────── */
function openSidenav()  {
  sidenav.classList.add("open");
  sidenavOverlay.classList.add("visible");
  mobileToggle.setAttribute("aria-expanded", "true");
}
function closeSidenav() {
  sidenav.classList.remove("open");
  sidenavOverlay.classList.remove("visible");
  mobileToggle.setAttribute("aria-expanded", "false");
}

function initNav() {
  // Nav buttons
  allNavBtns.forEach(btn => {
    btn.addEventListener("click", () => setPanel(btn.dataset.panel));
  });

  // CTA buttons in hero
  document.querySelectorAll("[data-panel]").forEach(el => {
    if (el.classList.contains("btn-primary") || el.classList.contains("btn-ghost")) {
      el.addEventListener("click", () => setPanel(el.dataset.panel));
    }
  });

  // Mobile toggle
  if (mobileToggle) mobileToggle.addEventListener("click", () => {
    sidenav.classList.contains("open") ? closeSidenav() : openSidenav();
  });
  if (sidenavOverlay) sidenavOverlay.addEventListener("click", closeSidenav);
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeSidenav(); });
}

/* ══════════════════════════════════════════════════════════════
   RANGE INPUTS — live value display
════════════════════════════════════════════════════════════════ */
function initRangeDisplays() {
  const map = [
    ["precipInput", "precipVal", v => `${v} mm`],
    ["tempInput",   "tempVal",   v => `${parseFloat(v).toFixed(1)}°C`],
    ["sstInput",    "sstVal",    v => `${parseFloat(v) >= 0 ? "+" : ""}${parseFloat(v).toFixed(1)}°C`],
  ];
  map.forEach(([inputId, displayId, fmt]) => {
    const input   = document.getElementById(inputId);
    const display = document.getElementById(displayId);
    if (!input || !display) return;
    const update = () => { display.textContent = fmt(input.value); };
    update();
    input.addEventListener("input", update);
  });
}

/* ══════════════════════════════════════════════════════════════
   FORECAST ENGINE
════════════════════════════════════════════════════════════════ */
function safeNum(v, fallback = 0) {
  const n = Number(v); return Number.isFinite(n) ? n : fallback;
}

function fallbackForecast(data) {
  const p   = safeNum(data.get("precipitation_mm"), 210);
  const tmp = safeNum(data.get("avg_temp_c"), 28.7);
  const sst = safeNum(data.get("sst_anomaly_c"), 0.8);
  const lake  = 24.2 + p / 260 - Math.max(0, tmp - 28) * 0.18 - sst * 0.28;
  const draft = lake - 10.7;
  const stress = 28 + Math.max(0, 14 - draft) * 11 + sst * 4;
  return {
    lake_level_m: lake,
    max_allowable_draft_m: draft,
    structural_stress_mpa: stress,
    transit_recommendation: lake < 24.8 ? "DIVERT_OR_AUCTION_SLOT" : "REDUCE_DRAFT_AND_WAIT_WINDOW",
  };
}

function normalizeRec(raw) {
  const map = {
    DIVERT_OR_AUCTION_SLOT:            "Divert or bid for a priority slot.",
    TRANSIT_WITH_LOCK_STRESS_MONITORING: "Transit with lock-stress monitoring.",
    REDUCE_DRAFT_AND_WAIT_WINDOW:       "Reduce draft and wait for the window.",
    PANAMA_TRANSIT_ACCEPTABLE:          "Panama transit is acceptable.",
  };
  return map[raw] || raw || "Forecast complete.";
}

function applyForecast(result, modeLabel) {
  state.lakeLevel = safeNum(result.lake_level_m, state.lakeLevel);
  state.maxDraft  = safeNum(result.max_allowable_draft_m, state.maxDraft);
  state.stress    = safeNum(result.structural_stress_mpa, state.stress);

  setText("lakeLevel", state.lakeLevel.toFixed(2));
  setText("maxDraft",  state.maxDraft.toFixed(2));
  setText("stress",    state.stress.toFixed(1));

  const rec = normalizeRec(result.transit_recommendation);
  const el  = document.getElementById("recommendation");
  if (el) el.textContent = rec;

  const mode = document.getElementById("predictionMode");
  if (mode) mode.textContent = `Mode: ${modeLabel}`;

  state.analysis = buildAnalysis(result);
  updateAllText();
  drawAllCharts();
}

async function runForecast(e) {
  if (e) e.preventDefault();

  const form = document.getElementById("predictionForm");
  if (!form) return;
  const data = new FormData(form);

  state.precipitation = safeNum(data.get("precipitation_mm"), 210);
  state.avgTemp       = safeNum(data.get("avg_temp_c"), 28.7);
  state.sstAnomaly    = safeNum(data.get("sst_anomaly_c"), 0.8);

  if (window.location.protocol === "file:") {
    applyForecast(fallbackForecast(data), "offline — mathematical fallback");
    return;
  }

  try {
    const params = new URLSearchParams({
      month:             data.get("month"),
      precipitation_mm:  data.get("precipitation_mm"),
      avg_temp_c:        data.get("avg_temp_c"),
      sst_anomaly_c:     data.get("sst_anomaly_c"),
    });
    const res = await fetch(`/api/predict?${params}`);
    if (!res.ok) throw new Error("API error");
    applyForecast(await res.json(), "Random Forest model");
  } catch {
    applyForecast(fallbackForecast(data), "offline — mathematical fallback");
  }
}

/* ── Analysis builder ────────────────────────────────────────── */
function buildAnalysis(result) {
  const lake  = safeNum(result.lake_level_m, state.lakeLevel);
  const draft = safeNum(result.max_allowable_draft_m, state.maxDraft);
  const stress = safeNum(result.structural_stress_mpa, state.stress);

  const dry       = Math.max(0, 25.4 - lake);
  const waitDays  = Math.max(1.5, 2.4 + dry * 5.6 + Math.max(0, state.sstAnomaly) * 1.8);
  const queueCost = waitDays * 145000;
  const auctionPremium = Math.max(450000, dry * 1850000 + Math.max(0, 13.8 - draft) * 950000);
  const magellanDelta  = 1180000 + Math.max(0, 13.4 - draft) * 620000;
  const transitRisk    = Math.min(99, Math.round(18 + dry * 22 + Math.max(0, 14 - draft) * 11 + stress * 0.35));
  const fatigue        = Math.min(96, Math.round(34 + waitDays * 4.2 + Math.max(0, state.avgTemp - 29) * 5));
  const bunkerTonsDay  = 38 + Math.max(0, transitRisk - 45) * 0.35;
  const ecoSpeed       = Math.max(10.8, 14.2 - dry * 0.55 - Math.max(0, state.sstAnomaly) * 0.28);
  const co2Tons        = bunkerTonsDay * (waitDays + 7.2) * 3.206;
  const panamaCost     = 2150000 + queueCost + Math.max(0, transitRisk - 55) * 18000;
  const auctionCost    = 2150000 + auctionPremium + 260000;
  const magellanCost   = 3450000 + magellanDelta;
  const draftMargin    = draft - 14.0;
  const engineEff      = Math.max(72, Math.min(96, 94 - Math.max(0, transitRisk - 40) * 0.18 - dry * 1.7));
  const bioDrag        = Math.max(4.5, Math.min(16, 6.5 + waitDays * 0.42 + Math.max(0, state.avgTemp - 28) * 0.8));
  const delayPenalty   = waitDays * 210000;

  let best, verdict;
  if (panamaCost <= auctionCost && panamaCost <= magellanCost) { best = "WAIT"; }
  else if (auctionCost <= magellanCost)                        { best = "AUCTION"; }
  else                                                         { best = "DIVERT"; }

  if (best === "WAIT") verdict = `Optimal: wait ${waitDays.toFixed(1)} days. Cost ${fmt(panamaCost)}.`;
  else if (best === "AUCTION") verdict = `Auction slot premium ${fmt(auctionPremium)} saves delays.`;
  else verdict = `Divert via Magellan. Total cost ${fmt(magellanCost)}.`;

  return {
    lake, draft, stress, dry, waitDays, queueCost, auctionPremium,
    magellanDelta, transitRisk, fatigue, bunkerTonsDay, ecoSpeed,
    co2Tons, panamaCost, auctionCost, magellanCost,
    draftMargin, engineEff, bioDrag, delayPenalty, best, verdict,
  };
}

/* ── Text helpers ────────────────────────────────────────────── */
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}
function fmt(v) {
  if (v >= 1e6) return `$${(v/1e6).toFixed(1)}M`;
  if (v >= 1000) return `$${Math.round(v/1000)}K`;
  return `$${Math.round(v)}`;
}

function updateAllText() {
  const a = state.analysis;
  if (!a) return;

  // Forecast Engine
  setText("lakeLevel", a.lake.toFixed(2));
  setText("maxDraft",  a.draft.toFixed(2));
  setText("stress",    a.stress.toFixed(1));

  // Analysis
  setText("transitRisk",    `${a.transitRisk}/100`);
  setText("crewFatigue",    `${a.fatigue}/100`);
  setText("dryStress",      a.dry.toFixed(2));
  setText("queueCost",      fmt(a.queueCost));
  setText("waitDays",       `${a.waitDays.toFixed(1)} days`);
  setText("panamaCost",     fmt(a.panamaCost));
  setText("auctionPremium", fmt(a.auctionPremium));
  setText("auctionCost",    fmt(a.auctionCost));
  setText("magellanDelta",  fmt(a.magellanDelta));
  setText("magellanCost",   fmt(a.magellanCost));

  // Command Matrix
  setText("rm-queue",          fmt(a.queueCost));
  setText("rm-eco",            `${a.ecoSpeed.toFixed(1)} kn`);
  setText("rm-panama",         fmt(a.panamaCost));
  setText("rm-auction-premium",fmt(a.auctionPremium));
  setText("rm-auction",        fmt(a.auctionCost));
  setText("rm-magellan",       fmt(a.magellanCost));

  // Bridge
  const riskLabel = a.transitRisk > 65 ? "HIGH" : a.transitRisk > 40 ? "MODERATE" : "LOW";
  setText("arpaLock",       `Lock approach CPA nominal. Risk index ${a.transitRisk}/100 — ${riskLabel}.`);
  setText("commsStatus",    "AIS Class A transmitting. GMDSS Inmarsat-C operational. No DSC alert in NAVAREA XI.");
  setText("pilotTugStatus", `Panama Canal pilot requested. ${a.waitDays.toFixed(0)} vessel queue. 2 tugs confirmed.`);
  setText("environmentStatus", `Wind ${Math.round(14 + a.dry * 3)} kt. Visibility ${a.lake > 25 ? "8.5" : "6.2"} NM. Gatun Lake ${a.lake.toFixed(2)} m.`);

  // Engineering
  setText("engStress",        `${a.stress.toFixed(1)} MPa`);
  setText("engDraftMargin",   `${a.draftMargin.toFixed(2)} m`);
  setText("engineEfficiency", `${a.engineEff.toFixed(0)}%`);
  setText("biofoulingDrag",   `${a.bioDrag.toFixed(1)}%`);
  setText("fwaStatus",        `Freshwater allowance penalty: +${(a.dry * 0.12).toFixed(2)} m on draft. Net max draft ${a.draft.toFixed(2)} m vs 14.0 m reference.`);

  // Commercial
  setText("bunkerBurn",               `${a.bunkerTonsDay.toFixed(1)} t/day VLSFO`);
  setText("ecoSpeed",                 `${a.ecoSpeed.toFixed(1)} knots`);
  setText("delayPenalty",             fmt(a.delayPenalty));
  setText("co2Exposure",              `${Math.round(a.co2Tons)} t CO₂e`);
  setText("insurancePosture",         a.transitRisk > 60 ? "Elevated — war risk rider active" : "Standard P&I cover");
  setText("commercialRecommendation", a.verdict);

  // Audit
  const physVeto = a.draft < 12.5
    ? `VETOED: draft ${a.draft.toFixed(2)} m below 12.5 m safety floor. Canal transit blocked.`
    : `APPROVED: draft ${a.draft.toFixed(2)} m within safety envelope. Structural stress ${a.stress.toFixed(1)} MPa — acceptable.`;
  setText("physicalVeto",    physVeto);
  setText("commercialVerdict", a.verdict);
}

/* ══════════════════════════════════════════════════════════════
   CANVAS UTILITIES
════════════════════════════════════════════════════════════════ */
function fitCanvas(id) {
  const canvas = document.getElementById(id);
  if (!canvas) return null;
  const ratio = window.devicePixelRatio || 1;
  const rect  = canvas.getBoundingClientRect();
  const W = Math.max(1, rect.width);
  const H = Math.max(1, rect.height);
  canvas.width  = Math.floor(W * ratio);
  canvas.height = Math.floor(H * ratio);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { ctx, W, H };
}

function clearCanvas(ctx, W, H, fill = C.white) {
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = fill;
  ctx.fillRect(0, 0, W, H);
}

function frame(ctx, W, H, dark = false) {
  ctx.strokeStyle = dark ? C.lineDk : C.line;
  ctx.lineWidth = 1;
  ctx.strokeRect(0.5, 0.5, W - 1, H - 1);
}

function monoFont(size, weight = 700) {
  return `${weight} ${size}px "JetBrains Mono", Consolas, monospace`;
}

function currentAnalysis() {
  return state.analysis || buildAnalysis({
    lake_level_m: state.lakeLevel,
    max_allowable_draft_m: state.maxDraft,
    structural_stress_mpa: state.stress,
  });
}

/* ══════════════════════════════════════════════════════════════
   CHARTS
════════════════════════════════════════════════════════════════ */

/* ── Lake Gauge (animated) ───────────────────────────────────── */
function drawLakeGauge() {
  const f = fitCanvas("lakeGauge");
  if (!f) return;
  const { ctx, W, H } = f;
  clearCanvas(ctx, W, H, C.deep);

  const t    = state.t;
  const lake = state.lakeLevel;
  const maxL = 28, minL = 22;
  const fill = (lake - minL) / (maxL - minL);

  // Water fill
  const waterY = H * (1 - fill * 0.82);
  ctx.fillStyle = C.canal;
  ctx.globalAlpha = 0.22;
  ctx.fillRect(0, waterY, W, H - waterY);
  ctx.globalAlpha = 1;

  // Animated wave
  ctx.beginPath();
  for (let x = 0; x <= W; x++) {
    const wave = Math.sin((x / W) * Math.PI * 4 + t * 2.5) * 5 + Math.cos((x / W) * Math.PI * 6 + t * 1.8) * 3;
    if (x === 0) ctx.moveTo(x, waterY + wave);
    else ctx.lineTo(x, waterY + wave);
  }
  ctx.lineTo(W, H); ctx.lineTo(0, H); ctx.closePath();
  ctx.fillStyle = C.canal;
  ctx.globalAlpha = 0.35;
  ctx.fill();
  ctx.globalAlpha = 1;

  // Grid lines
  ctx.strokeStyle = "rgba(255,255,255,.08)";
  ctx.lineWidth = 1;
  for (let i = 1; i < 6; i++) {
    const y = H * i / 6;
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
  }

  // Level label
  ctx.fillStyle = C.white;
  ctx.font = monoFont(32, 800);
  ctx.textAlign = "center";
  ctx.fillText(`${lake.toFixed(2)} m`, W / 2, H / 2 + 12);

  ctx.fillStyle = "rgba(255,255,255,.42)";
  ctx.font = monoFont(11, 700);
  ctx.fillText("GATUN LAKE LEVEL", W / 2, H / 2 - 18);

  // Draft limit line
  const draftY = H * (1 - ((lake - 10.7 - minL) / (maxL - minL)) * 0.82);
  ctx.strokeStyle = C.brass;
  ctx.lineWidth = 1.5;
  ctx.setLineDash([6, 4]);
  ctx.beginPath(); ctx.moveTo(0, draftY); ctx.lineTo(W, draftY); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = C.brass;
  ctx.font = monoFont(10, 700);
  ctx.textAlign = "right";
  ctx.fillText(`MAX DRAFT ${(lake - 10.7).toFixed(2)} m`, W - 10, draftY - 4);
}

/* ── Radar Chart ─────────────────────────────────────────────── */
function drawRadarChart() {
  const f = fitCanvas("radarChart");
  if (!f) return;
  const { ctx, W, H } = f;
  clearCanvas(ctx, W, H, C.deep);

  const cx = W / 2, cy = H / 2;
  const r  = Math.min(W, H) * 0.4;
  const t  = state.t;

  // Rings
  for (let i = 1; i <= 4; i++) {
    ctx.beginPath();
    ctx.arc(cx, cy, r * i / 4, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(0,146,196,.14)";
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  // Sweep
  const sweepAngle = (t * 1.4) % (Math.PI * 2);
  const grad = ctx.createConicalGradient
    ? null  // not universally supported
    : null;
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(sweepAngle);
  const swpGrad = ctx.createLinearGradient(0, 0, r, 0);
  swpGrad.addColorStop(0, "rgba(0,146,196,.0)");
  swpGrad.addColorStop(1, "rgba(0,146,196,.22)");
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.arc(0, 0, r * 1.02, -Math.PI * 0.4, 0);
  ctx.closePath();
  ctx.fillStyle = swpGrad;
  ctx.fill();
  ctx.restore();

  // Sweep line
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(sweepAngle);
  ctx.strokeStyle = "rgba(0,146,196,.70)";
  ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(r * 1.02, 0); ctx.stroke();
  ctx.restore();

  // Spokes
  ctx.strokeStyle = "rgba(0,146,196,.09)";
  for (let i = 0; i < 8; i++) {
    const a = (i / 8) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
    ctx.stroke();
  }

  // Contacts
  const contacts = [
    { r: 0.38, a: 0.8,  label: "Lock A" },
    { r: 0.62, a: 2.1,  label: "Canal tug" },
    { r: 0.81, a: 4.4,  label: "Vessel ahead" },
    { r: 0.55, a: 5.5,  label: "Pilot boat" },
  ];
  contacts.forEach(({ r: cr, a, label }) => {
    const px = cx + Math.cos(a) * r * cr;
    const py = cy + Math.sin(a) * r * cr;
    const blink = Math.sin(t * 3 + a) > 0;
    ctx.beginPath();
    ctx.arc(px, py, 4, 0, Math.PI * 2);
    ctx.fillStyle = blink ? C.green : C.canal;
    ctx.fill();
    ctx.fillStyle = "rgba(255,255,255,.52)";
    ctx.font = monoFont(9, 700);
    ctx.textAlign = "left";
    ctx.fillText(label, px + 7, py + 4);
  });

  // Own ship
  ctx.beginPath(); ctx.arc(cx, cy, 6, 0, Math.PI * 2);
  ctx.fillStyle = C.white; ctx.fill();

  // Center text
  ctx.fillStyle = "rgba(0,146,196,.35)";
  ctx.font = monoFont(9, 700);
  ctx.textAlign = "center";
  ctx.fillText("RADAR  ·  LOCK APPROACH", cx, H - 12);
}

/* ── Engine Gauge ────────────────────────────────────────────── */
function drawEngineChart() {
  const f = fitCanvas("engineChart");
  if (!f) return;
  const { ctx, W, H } = f;
  clearCanvas(ctx, W, H, C.paper);
  frame(ctx, W, H);
  const a = currentAnalysis();

  // Eco-speed needle gauge
  const cx = W / 2, cy = H * 0.55;
  const r  = Math.min(W * 0.35, H * 0.42);
  const minSpd = 9, maxSpd = 17;
  const frac = Math.max(0, Math.min(1, (a.ecoSpeed - minSpd) / (maxSpd - minSpd)));
  const startA = Math.PI * 0.75, endA = Math.PI * 2.25;

  // Track
  ctx.beginPath();
  ctx.arc(cx, cy, r, startA, endA);
  ctx.strokeStyle = C.bone;
  ctx.lineWidth = 12;
  ctx.lineCap = "round";
  ctx.stroke();

  // Fill
  const needleA = startA + frac * (endA - startA);
  ctx.beginPath();
  ctx.arc(cx, cy, r, startA, needleA);
  ctx.strokeStyle = frac > 0.65 ? C.clay : frac > 0.45 ? C.brass : C.green;
  ctx.lineWidth = 12;
  ctx.stroke();

  // Needle
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(needleA);
  ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(r * 0.88, 0);
  ctx.strokeStyle = C.ink; ctx.lineWidth = 2; ctx.lineCap = "round"; ctx.stroke();
  ctx.restore();

  // Center label
  ctx.fillStyle = C.ink;
  ctx.font = monoFont(22, 800);
  ctx.textAlign = "center";
  ctx.fillText(`${a.ecoSpeed.toFixed(1)} kn`, cx, cy + 8);

  ctx.fillStyle = "rgba(7,19,30,.42)";
  ctx.font = monoFont(10, 700);
  ctx.fillText("ECO-SPEED", cx, cy + 26);

  // Footnotes
  ctx.textAlign = "left";
  ctx.fillStyle = "rgba(7,19,30,.48)";
  ctx.font = monoFont(10, 700);
  ctx.fillText(`Efficiency ${a.engineEff.toFixed(0)}%`, 14, H - 30);
  ctx.fillText(`Biofouling ${a.bioDrag.toFixed(1)}% drag`, 14, H - 14);
}

/* ── Stability Chart ─────────────────────────────────────────── */
function drawStabilityChart() {
  const f = fitCanvas("stabilityChart");
  if (!f) return;
  const { ctx, W, H } = f;
  clearCanvas(ctx, W, H);
  frame(ctx, W, H);
  const a = currentAnalysis();

  const roll  = a.dry * 1.2;
  const pitch = a.dry * 0.5;
  const cx = W / 2, cy = H * 0.5;
  const rx = W * 0.36, ry = H * 0.30;

  // Safe envelope ellipse
  ctx.beginPath();
  ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
  ctx.strokeStyle = C.bone;
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 4]);
  ctx.stroke();
  ctx.setLineDash([]);

  // Waterline
  const lean = Math.tan(roll * Math.PI / 180);
  const col = Math.abs(roll) > 8 ? C.clay : C.green;
  ctx.beginPath();
  ctx.moveTo(0, cy + lean * W / 2);
  ctx.lineTo(W, cy - lean * W / 2);
  ctx.strokeStyle = col;
  ctx.lineWidth = 3;
  ctx.stroke();

  // CG marker
  ctx.beginPath();
  ctx.arc(cx + roll * 2.5, cy - pitch * 2.5, 8, 0, Math.PI * 2);
  ctx.fillStyle = col;
  ctx.fill();
  ctx.strokeStyle = C.white;
  ctx.lineWidth = 2;
  ctx.stroke();

  // Labels
  ctx.fillStyle = "rgba(7,19,30,.52)";
  ctx.font = monoFont(10, 700);
  ctx.textAlign = "left";
  ctx.fillText(`Roll ${roll.toFixed(1)}°`, 12, H - 28);
  ctx.fillText(`Pitch ${pitch.toFixed(1)}°`, 12, H - 12);

  ctx.textAlign = "right";
  const ukc = a.lake - a.draft - 7.8;
  ctx.fillStyle = ukc < 1.5 ? C.clay : "rgba(7,19,30,.52)";
  ctx.fillText(`UKC ${ukc.toFixed(1)} m`, W - 12, H - 12);
}

/* ── Fatigue Chart ───────────────────────────────────────────── */
function drawFatigueChart() {
  const f = fitCanvas("fatigueChart");
  if (!f) return;
  const { ctx, W, H } = f;
  clearCanvas(ctx, W, H);
  frame(ctx, W, H);
  const a = currentAnalysis();

  const PAD = { t: 36, r: 20, b: 40, l: 42 };
  const cW  = W - PAD.l - PAD.r;
  const cH  = H - PAD.t - PAD.b;
  const x0  = PAD.l, y0 = H - PAD.b;

  // Grid
  ctx.strokeStyle = C.line;
  ctx.lineWidth = 1;
  for (let i = 1; i <= 4; i++) {
    const y = y0 - (cH * i) / 4;
    ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x0 + cW, y); ctx.stroke();
    ctx.fillStyle = "rgba(7,19,30,.32)";
    ctx.font = monoFont(9, 700);
    ctx.textAlign = "right";
    ctx.fillText(`${(20 + i * 13).toFixed(0)}`, x0 - 6, y + 4);
  }

  // Limit line
  const limitY = y0 - (a.stress > 55 ? 0.85 : 0.65) * cH;
  ctx.strokeStyle = C.clay;
  ctx.lineWidth = 1.2;
  ctx.setLineDash([5, 3]);
  ctx.beginPath(); ctx.moveTo(x0, limitY); ctx.lineTo(x0 + cW, limitY); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = C.clay;
  ctx.font = monoFont(9, 700);
  ctx.textAlign = "right";
  ctx.fillText("LIMIT", x0 + cW, limitY - 3);

  // Stress curve
  ctx.strokeStyle = a.stress > 55 ? C.clay : C.canal;
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  for (let i = 0; i <= 80; i++) {
    const p = i / 80;
    const sv = a.stress + Math.sin(p * Math.PI * 7) * 4 + Math.cos(p * Math.PI * 3) * 2.4;
    const x  = x0 + p * cW;
    const y  = y0 - (Math.max(20, Math.min(72, sv)) - 20) / 52 * cH;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.stroke();

  // Title
  ctx.fillStyle = C.ink;
  ctx.font = monoFont(12, 700);
  ctx.textAlign = "left";
  ctx.fillText(`${a.stress.toFixed(1)} MPa  —  lock-transit stress`, PAD.l, PAD.t - 6);
}

/* ── Fuel Curve ──────────────────────────────────────────────── */
function drawFuelCurveChart() {
  const f = fitCanvas("fuelCurveChart");
  if (!f) return;
  const { ctx, W, H } = f;
  clearCanvas(ctx, W, H, C.deep);
  const a = currentAnalysis();

  const PAD = { t: 44, r: 18, b: 42, l: 40 };
  const cW  = W - PAD.l - PAD.r;
  const cH  = H - PAD.t - PAD.b;
  const x0  = PAD.l, y0 = H - PAD.b;

  // Axes
  ctx.strokeStyle = C.lineDk;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(x0, PAD.t); ctx.lineTo(x0, y0); ctx.lineTo(x0 + cW, y0);
  ctx.stroke();

  // Grid
  for (let i = 1; i <= 4; i++) {
    const y = y0 - (cH * i) / 4;
    ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x0 + cW, y);
    ctx.strokeStyle = "rgba(255,255,255,.06)"; ctx.stroke();
    ctx.fillStyle = "rgba(255,255,255,.28)";
    ctx.font = monoFont(9, 700);
    ctx.textAlign = "right";
    ctx.fillText(`${(i * 18).toFixed(0)}`, x0 - 6, y + 4);
  }

  // Curve
  ctx.strokeStyle = C.green;
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  for (let i = 0; i <= 70; i++) {
    const p = i / 70;
    const speed = 9 + p * 8;
    const fuel  = 22 + Math.pow(speed / 14, 3) * 34 + a.bioDrag * 0.7;
    const x = x0 + p * cW;
    const y = y0 - (Math.min(72, fuel) / 72) * cH;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.stroke();

  // Eco-speed marker
  const sp   = (a.ecoSpeed - 9) / 8;
  const xPt  = x0 + Math.max(0, Math.min(1, sp)) * cW;
  const yPt  = y0 - (a.bunkerTonsDay / 72) * cH;
  ctx.beginPath();
  ctx.arc(xPt, yPt, 6, 0, Math.PI * 2);
  ctx.fillStyle = C.brass;
  ctx.fill();

  // Tooltip
  ctx.fillStyle = C.brass;
  ctx.font = monoFont(10, 700);
  ctx.textAlign = "left";
  ctx.fillText(`${a.ecoSpeed.toFixed(1)} kn  ·  ${a.bunkerTonsDay.toFixed(1)} t/day`, xPt + 10, yPt - 6);

  // Labels
  ctx.fillStyle = "rgba(255,255,255,.32)";
  ctx.font = monoFont(9, 700);
  ctx.textAlign = "left";
  ctx.fillText("SPEED (kn)", x0 + cW / 2, y0 + 16);

  ctx.fillStyle = C.bone;
  ctx.font = monoFont(12, 700);
  ctx.fillText(`Bunker ${a.bunkerTonsDay.toFixed(1)} t/day VLSFO`, PAD.l, PAD.t - 10);
}

/* ── Emissions Bars ──────────────────────────────────────────── */
function drawEmissionsChart() {
  const f = fitCanvas("emissionsChart");
  if (!f) return;
  const { ctx, W, H } = f;
  clearCanvas(ctx, W, H, C.deep);
  const a = currentAnalysis();

  const bars = [
    { label: "CO₂e",  value: a.co2Tons,             color: C.canal },
    { label: "Delay", value: a.delayPenalty / 1000,  color: C.brass },
    { label: "Risk",  value: a.transitRisk * 24,      color: C.clay  },
  ];

  const PAD = { t: 48, r: 18, b: 36, l: 18 };
  const cW  = W - PAD.l - PAD.r;
  const cH  = H - PAD.t - PAD.b;
  const max = Math.max(...bars.map(b => b.value)) * 1.12 || 1;
  const barW = cW / bars.length - 20;

  bars.forEach((bar, i) => {
    const xx   = PAD.l + i * (barW + 20) + 10;
    const barH = Math.max(6, (bar.value / max) * cH);
    const yTop = PAD.t + cH - barH;

    // Track
    ctx.fillStyle = "rgba(255,255,255,.06)";
    ctx.fillRect(xx, PAD.t, barW, cH);

    // Bar
    ctx.fillStyle = bar.color;
    ctx.fillRect(xx, yTop, barW, barH);

    // Value on top of bar — clamp so it doesn't clip
    ctx.fillStyle = C.white;
    ctx.font = monoFont(11, 700);
    ctx.textAlign = "center";
    const valLabelY = Math.max(PAD.t + 14, yTop - 5);
    ctx.fillText(bar.value.toFixed(0), xx + barW / 2, valLabelY);

    // Label below
    ctx.fillStyle = C.bone;
    ctx.font = monoFont(10, 700);
    ctx.fillText(bar.label, xx + barW / 2, H - PAD.b + 14);
  });

  // Title
  ctx.fillStyle = C.bone;
  ctx.font = monoFont(12, 700);
  ctx.textAlign = "left";
  ctx.fillText("CO₂ / Delay / Risk Exposure", PAD.l + 10, PAD.t - 12);
}

/* ── Draw dispatcher ─────────────────────────────────────────── */
function drawAllCharts() {
  drawLakeGauge();
  drawRadarChart();
  drawEngineChart();
  drawStabilityChart();
  drawFatigueChart();
  drawFuelCurveChart();
  drawEmissionsChart();
}

/* ── Animation loop ─────────────────────────────────────────── */
function tick() {
  state.t += 0.012;
  if (state.activePanel === "intelligence") drawLakeGauge();
  if (state.activePanel === "bridge")       drawRadarChart();
  requestAnimationFrame(tick);
}

/* ══════════════════════════════════════════════════════════════
   INIT
════════════════════════════════════════════════════════════════ */
function init() {
  initAccordion();
  initNav();
  initRangeDisplays();

  // Form live update
  if (predForm) {
    predForm.addEventListener("submit", runForecast);
    predForm.addEventListener("input", () => {
      clearTimeout(window.__forecastTimer);
      window.__forecastTimer = setTimeout(runForecast, 300);
    });
  }

  window.addEventListener("resize", drawAllCharts);

  // Bootstrap
  setPanel("home");
  runForecast();
  tick();
}

document.readyState === "loading"
  ? document.addEventListener("DOMContentLoaded", init)
  : init();