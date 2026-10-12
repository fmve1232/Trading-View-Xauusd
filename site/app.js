/* XAUUSD Quantum -- front-end. Renders the JSON the pipeline publishes; decides nothing itself. */
"use strict";

const TFS = ["5m", "15m", "1h", "4h"];
const $ = (s) => document.querySelector(s);
const store = {
  get(k, d) { try { const v = localStorage.getItem("q5." + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("q5." + k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
};
const S = {
  tf: store.get("tf", "15m"),
  data: null,
  index: null,
  mt5: store.get("mt5", 0),
  tz: store.get("tz", "local"),
  account: store.get("account", null),
  tab: store.get("tab", "overview"),
  btArm: "treatment",
  toggles: store.get("toggles", { ema: true, vwap: true, bb: false, levels: true, zones: true, sr: false, signals: true, structure: true, sweeps: false, plan: true, cone: true, vp: false, h2: true }),
};

/* ---------- formatting ---------- */
const isNum = (x) => typeof x === "number" && isFinite(x);
const f = (x, d = 2) => (isNum(x) ? x.toFixed(d) : "—");
const fs = (x, d = 2) => (isNum(x) ? (x > 0 ? "+" : "") + x.toFixed(d) : "—");
const pct = (x, d = 0) => (isNum(x) ? x.toFixed(d) + "%" : "—");
// A statistic over zero observations is the engine's placeholder (analog.default_outputs), not a measurement.
const pctN = (x, n, d = 0) => (n > 0 ? pct(x, d) : "—");
const px = (x) => (isNum(x) ? (x + Number(S.mt5 || 0)).toFixed(2) : "—");
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
// A malformed system locale (e.g. "en-US@posix") makes Intl throw; fall back to en-US.
const LOCALE = (() => { const l = (navigator.language || "en-US").split("@")[0]; try { new Intl.DateTimeFormat(l); return l; } catch (e) { return "en-US"; } })();
function tfmt(epochSec, withDate = true) {
  const opt = { hour: "2-digit", minute: "2-digit", hour12: false };
  if (withDate) Object.assign(opt, { month: "short", day: "2-digit" });
  if (S.tz !== "local") opt.timeZone = S.tz;
  return new Intl.DateTimeFormat(LOCALE, opt).format(new Date(epochSec * 1000));
}
const ago = (iso) => {
  const m = (Date.now() - new Date(iso).getTime()) / 60000;
  if (!isFinite(m)) return "—";
  if (m < 1) return "just now";
  if (m < 60) return Math.round(m) + " min ago";
  if (m < 1440) return (m / 60).toFixed(1) + " h ago";
  return (m / 1440).toFixed(1) + " d ago";
};
const kv = (rows) => `<div class="kv">${rows.map(([k, v]) => `<div>${k}</div><div>${v}</div>`).join("")}</div>`;
const card = (title, body, extra = "") => `<div class="card"><div class="hd"><h3>${title}</h3>${extra}</div><div class="bd">${body}</div></div>`;
const pill = (txt, cls = "") => `<span class="pill ${cls}">${esc(txt)}</span>`;
const dirCls = (x) => (x > 0 ? "bull" : x < 0 ? "bear" : "");

/* ---------- theme / controls ---------- */
function applyTheme(t) {
  if (t) document.documentElement.setAttribute("data-theme", t); else document.documentElement.removeAttribute("data-theme");
}
applyTheme(store.get("theme", null));
// header height -> CSS, so the sticky decision column starts just under it
const setHdr = () => { const h = document.querySelector("header.top"); if (h) document.documentElement.style.setProperty("--hdr-h", h.offsetHeight + "px"); };
new ResizeObserver(setHdr).observe(document.querySelector("header.top")); setHdr();
$("#theme").onclick = () => {
  const cur = document.documentElement.getAttribute("data-theme") || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
  const nx = cur === "light" ? "dark" : "light";
  store.set("theme", nx); applyTheme(nx); rebuildCharts(); syncTV();
};
$("#mt5").value = S.mt5;
$("#mt5").oninput = (e) => { S.mt5 = Number(e.target.value) || 0; store.set("mt5", S.mt5); renderSide(); };
$("#tz").value = S.tz;
$("#tz").onchange = (e) => { S.tz = e.target.value; store.set("tz", S.tz); rebuildCharts(); renderAll(); };
$("#tf-tabs").innerHTML = TFS.map((t) => `<button data-tf="${t}">${t}</button>`).join("");
$("#tf-tabs").onclick = (e) => { const t = e.target.dataset.tf; if (t) { S.tf = t; store.set("tf", t); load(); if (typeof syncTV === "function") syncTV(); } };
$("#tabs").onclick = (e) => { const t = e.target.dataset.tab; if (t) showTab(t); };
function showTab(t) {
  S.tab = t; store.set("tab", t);
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === t));
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("hidden", s.id !== "tab-" + t));
  if (t === "backtest") setTimeout(renderEquity, 0);
}
const TOGGLES = [["ema", "EMA 20/100/200"], ["vwap", "VWAP D/W/M"], ["bb", "Bollinger"], ["levels", "Levels"], ["zones", "OB / FVG"],
  ["sr", "S/R"], ["vp", "Value area"], ["signals", "Signals"], ["structure", "BOS / CHoCH"], ["sweeps", "Sweeps"], ["plan", "Plan"], ["cone", "Vol cone"], ["h2", "H2 signals"], ["h3", "H3 signals"]];
if (S.toggles.h2 === undefined) S.toggles.h2 = true;   // added after viewers saved their toggles
if (S.toggles.h3 === undefined) S.toggles.h3 = true;
// v-labels (Oct 2026): sweeps and structure labels on by default once, now that they are readable labels
if (!store.get("labels_v1", false)) { S.toggles.sweeps = true; S.toggles.structure = true; store.set("toggles", S.toggles); store.set("labels_v1", true); }
$("#toolbar").innerHTML = TOGGLES.map(([k, l]) => `<span class="toggle ${S.toggles[k] ? "on" : ""}" data-k="${k}">${l}</span>`).join("") +
  `<button class="toggle fit" type="button" data-act="fit" title="Fit the latest bars to the screen and re-enable auto price scale">⤢ Fit</button>`;
$("#toolbar").onclick = (e) => {
  if (e.target.dataset.act === "fit") { fitView(); return; }
  const k = e.target.dataset.k; if (!k) return;
  S.toggles[k] = !S.toggles[k]; store.set("toggles", S.toggles);
  e.target.classList.toggle("on", S.toggles[k]); renderChart();
};

/* ---------- data ---------- */
async function getJSON(u) {
  const r = await fetch(u + (u.includes("?") ? "&" : "?") + "v=" + Date.now(), { cache: "no-store" });
  if (!r.ok) throw new Error(u + " -> HTTP " + r.status);
  return r.json();
}
async function load() {
  document.querySelectorAll("#tf-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tf === S.tf));
  try {
    S.index = await getJSON("data/index.json");
  } catch (e) { S.index = null; }
  try {
    S.data = await getJSON(`data/${S.tf}.json`);
  } catch (e) {
    S.data = null;
    $("#banners").innerHTML = `<div class="banner error">No data for ${esc(S.tf)} yet (${esc(e.message)}). The pipeline publishes it on its next run.</div>`;
    return;
  }
  renderAll();
  loadEvents();
  loadMacroPanel();
  loadReference();
  loadMt5();
  pollLive();
  startStream();
}
setInterval(async () => {
  try {
    const ix = await getJSON("data/index.json");
    if (!S.index || ix.generated_utc !== S.index.generated_utc) load();
    else renderHeader();
  } catch (e) { /* offline: keep what we have */ }
}, 20000);   // a new engine run is picked up within 20 s of being published, without a page reload

/* ---------- live spot ticker (DISPLAY ONLY: the engine never reads it) ---------- */
const LIVE_URL = "https://api.gold-api.com/price/XAU";
const LIVE_TITLE = "Live spot from gold-api.com, read by your browser. DISPLAY ONLY: the engine never uses it; signals come from closed bars.";
const LIVE = { px: null, t: null, err: "" };
// Spot gold is shut from Friday 17:00 to Sunday 18:00 New York, and 17:00-18:00 Monday to
// Thursday: the same rule as the pipeline's sources.gold_shut (web.4).
function marketClosed(d) {
  const ny = new Date(d.toLocaleString("en-US", { timeZone: "America/New_York" }));
  const dow = ny.getDay(), h = ny.getHours();
  return dow === 6 || (dow === 5 && h >= 17) || (dow === 0 && h < 18) || (dow >= 1 && dow <= 4 && h === 17);
}
let LIVE_FAILS = 0;
async function pollLive() {
  if (document.hidden || streaming()) return;
  if (LIVE_FAILS && Date.now() < (LIVE.next || 0)) return;            // backing off after errors
  try {
    const r = await fetch(LIVE_URL, { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const j = await r.json();
    const p = Number(j && j.price);
    const ts = j && j.updatedAt ? Date.parse(j.updatedAt) : NaN;
    const ref = S.data && S.data.dashboard ? S.data.dashboard.close : null;
    if (!isNum(p) || p <= 0) throw new Error("no price in the response");
    // a feed glitch must not look like a market move: reject anything >5% from the engine's last close
    if (isNum(ref) && Math.abs(p / ref - 1) > 0.05) throw new Error(`rejected ${p.toFixed(2)} (more than 5% from the engine close ${ref.toFixed(2)})`);
    Object.assign(LIVE, { px: p, t: isFinite(ts) ? ts : Date.now(), err: "", src: "gold-api", rx: Date.now() });
    LIVE_FAILS = 0;
  } catch (e) { LIVE.err = (e && e.message) || "unavailable"; LIVE_FAILS++; LIVE.next = Date.now() + Math.min(5000 * 2 ** LIVE_FAILS, 120000); }
  renderLive();
}
function renderLive() {
  const chip = $("#chip-live"); if (!chip) return;
  chip.classList.remove("ok", "stale", "bad");
  if (LIVE.px === null) {
    $("#live").textContent = "unavailable"; $("#live-meta").textContent = "";
    chip.classList.add("bad"); chip.title = LIVE_TITLE + (LIVE.err ? " Last error: " + LIVE.err : ""); return;
  }
  const ageMin = (Date.now() - LIVE.t) / 60000;
  const ref = S.data && S.data.dashboard ? S.data.dashboard.close : null;
  const closed = marketClosed(new Date());
  $("#live").textContent = LIVE.px.toFixed(2);
  const src = LIVE.src === "stream" && streaming() ? "stream" : "gold-api";
  const age = src === "stream" ? (ageMin < 1 ? Math.max(0, Math.round(ageMin * 60)) + " s" : Math.round(ageMin) + " min") : (ageMin < 1 ? "<1 min" : Math.round(ageMin) + " min");
  $("#live-meta").textContent = closed ? "market closed · last quote" : `${src} · ${age}${isNum(ref) ? " · Δ " + fs(LIVE.px - ref, 2) + " vs last bar" : ""}`;
  chip.classList.add(!closed && !LIVE.err && ageMin < 10 ? "ok" : "stale");
  try { renderQuote(); renderBrief(); } catch (e) { console.error(e); }
  chip.title = (src === "stream" ? "Streaming ticks (Finnhub via the relay), at most 4 updates a second. DISPLAY ONLY: the engine never uses them; signals come from closed bars." : LIVE_TITLE) +
    (STREAM.url ? ` Stream: ${STREAM.status || "—"}.` : "") + (closed ? " The market is closed (Friday 17:00 to Sunday 18:00 New York, and the daily 17:00-18:00 break): the feed repeats the last quote with a fresh timestamp." : "") +
    ` Price as of ${new Date(LIVE.t).toUTCString()}.` + (LIVE.err ? " Last refresh failed: " + LIVE.err : "");
  renderGuard();
}
// Every 5 s while the tab is visible, the market is open and the tick stream is not delivering
// (the stream, when it works, sends up to 4 ticks a second). Errors back off to 2 minutes.
setInterval(() => { if (!marketClosed(new Date()) || LIVE.px === null) pollLive(); }, 5000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) pollLive(); });

/* ---------- streaming ticks via the relay (DISPLAY ONLY; never read by the engine) ---------- */
// data/stream.json carries the relay address (repository variable STREAM_URL). Without it, or
// while the stream is down, the chip falls back to the 60 s gold-api poll above.
const STREAM = { url: "", ws: null, status: "", rx: 0, retry: 2000, bar: null };
async function startStream() {
  let cfg = null;
  try { cfg = await getJSON("data/stream.json"); } catch (e) { return; }
  const u = String((cfg && cfg.url) || "").trim();
  if (!/^wss:\/\/[^\s"'<>]+$/.test(u) || STREAM.url === u) return;
  STREAM.url = u; connectStream();
}
function connectStream() {
  let ws;
  try { ws = new WebSocket(STREAM.url); } catch (e) { STREAM.status = "cannot connect"; renderLive(); return; }
  STREAM.ws = ws; STREAM.status = "connecting";
  ws.onopen = () => { STREAM.retry = 2000; };
  ws.onmessage = (ev) => {
    let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
    if (m.type === "hello" || m.type === "status") { STREAM.status = String(m.status || "").slice(0, 80); if (m.last) onTick(m.last, true); if (m.macro) onMacro(m.macro); renderLive(); }
    else if (m.type === "macro") onMacro(m.q);
    else if (m.type === "tick") onTick(m, false);
  };
  ws.onclose = () => {
    STREAM.ws = null; STREAM.status = "disconnected"; renderLive();
    setTimeout(connectStream, STREAM.retry); STREAM.retry = Math.min(STREAM.retry * 2, 60000);
  };
}
const streaming = () => STREAM.ws && Date.now() - STREAM.rx < 90000;
function onTick(k, replay) {
  const p = Number(k.p), t = Number(k.t);
  if (!isNum(p) || p <= 0 || !isNum(t)) return;
  const ref = S.data && S.data.dashboard ? S.data.dashboard.close : null;
  if (isNum(ref) && Math.abs(p / ref - 1) > 0.05) { STREAM.status = `rejected ${p.toFixed(2)} (>5% from the engine close)`; renderLive(); return; }
  if (!replay) STREAM.rx = Date.now();
  Object.assign(LIVE, { px: p, t, err: "", src: "stream", rx: Date.now() });
  if (!replay) updateLiveBar({ p, t, h: Number(k.h), l: Number(k.l) });
  renderLive();
}
// The forming candle only: bars the engine has closed are never touched.
function updateLiveBar(k) {
  if (!C || !S.data) return;
  const D = S.data, tf = D.meta.tf_sec, ts = D.chart.t, lastClosed = ts[ts.length - 1];
  const open = Math.floor(k.t / 1000 / tf) * tf;
  if (open <= lastClosed) return;
  let b = STREAM.bar && STREAM.bar.time === open ? STREAM.bar : null;
  if (!b) {
    const fb = D.meta.forming;
    b = fb && fb.t === open ? { time: open, open: fb.o, high: fb.h, low: fb.l, close: fb.c } : { time: open, open: k.p, high: k.p, low: k.p, close: k.p };
  }
  b.high = Math.max(b.high, isNum(k.h) ? k.h : k.p); b.low = Math.min(b.low, isNum(k.l) ? k.l : k.p); b.close = k.p;
  STREAM.bar = b;
  applyLiveBar();
}
function applyLiveBar(lastTime) {
  const b = STREAM.bar; if (!C || !b) return;
  if (isNum(lastTime) && b.time < lastTime) return;           // an engine update has moved past it
  try { C.candles.update({ ...b, color: css("--neutral") + "88", wickColor: css("--neutral"), borderColor: css("--neutral") }); } catch (e) { /* older than the series end */ }
  if (C.labels && (C.labels.lastT === null || b.time > C.labels.lastT)) C.labels.set({ lastT: b.time });   // levels reach the live candle
}

/* ---------- TradingView's free Advanced Chart widget (DISPLAY ONLY; loaded on demand) ----------
   A visual cross-check: TradingView's own OANDA:XAUUSD chart. Nothing reads from it, it never
   feeds the engine, and its third-party script is fetched only after the viewer presses Show. */
const TV_SRC = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
const TV_INTERVAL = { "5m": "5", "15m": "15", "1h": "60", "4h": "240" };
const tvTheme = () => document.documentElement.getAttribute("data-theme") || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
function tvConfig() {
  let tz = "Etc/UTC";
  try { tz = S.tz === "local" ? Intl.DateTimeFormat().resolvedOptions().timeZone || "Etc/UTC" : S.tz; } catch (e) { /* keep UTC */ }
  return { autosize: true, symbol: "OANDA:XAUUSD", interval: TV_INTERVAL[S.tf] || "15", timezone: tz, theme: tvTheme(), style: "1",
           locale: "en", allow_symbol_change: false, calendar: false, hide_side_toolbar: true, support_host: "https://www.tradingview.com" };
}
function loadTV() {
  const w = $("#tv-wrap"); if (!w) return;
  const cfg = tvConfig();
  w.innerHTML = "";
  const box = document.createElement("div");
  box.className = "tradingview-widget-container tv-box";
  const inner = document.createElement("div");
  inner.className = "tradingview-widget-container__widget";
  inner.style.height = "calc(100% - 24px)";
  const cp = document.createElement("div");
  cp.className = "tradingview-widget-copyright dim";            // attribution required by TradingView's widget terms
  cp.innerHTML = '<a href="https://www.tradingview.com/symbols/XAUUSD/?exchange=OANDA" rel="noopener nofollow" target="_blank">XAUUSD chart by TradingView</a>';
  const sc = document.createElement("script");
  sc.type = "text/javascript"; sc.async = true; sc.src = TV_SRC;
  sc.text = JSON.stringify(cfg);                                  // the widget reads its config from this script's text
  sc.onerror = () => { w.innerHTML = '<p class="warn">The TradingView widget could not load (blocked by the browser or network, or TradingView is unreachable). Nothing else on this page depends on it.</p>'; };
  box.append(inner, cp, sc);
  w.append(box);
  S.tvShown = { tf: S.tf, tz: S.tz, theme: cfg.theme };
}
function setTV(on) {
  S.tvOn = on; store.set("tvOn", on);
  const b = $("#tv-toggle"); if (b) b.textContent = on ? "Hide" : "Show";
  if (on) loadTV();
  else { S.tvShown = null; $("#tv-wrap").innerHTML = '<p class="muted">Hidden. Press <b>Show</b> to load TradingView\'s live OANDA:XAUUSD chart (third-party script).</p>'; }
}
// reload only when the timeframe, time zone or theme it was built for has changed
function syncTV() {
  if (!S.tvOn) return;
  const t = S.tvShown;
  if (!t || t.tf !== S.tf || t.tz !== S.tz || t.theme !== tvTheme()) loadTV();
}
$("#tv-toggle").onclick = () => setTV(!S.tvOn);
if (store.get("tvOn", false)) setTV(true);

/* ---------- reference prices (DISPLAY AND VALIDATION ONLY; quantum/reference.py) ---------- */
// Each provider is shown as it reported itself: raw values, its own timestamp precision and
// status. A divergence is shown with both raw prices; neither is replaced or reconciled.
async function loadReference() {
  try { S.ref = await getJSON("data/reference.json"); } catch (e) { S.ref = null; }
  renderReference();
}
const REF_CLS = { CONSISTENT: "bull", MINOR_DIVERGENCE: "", SIGNIFICANT_DIVERGENCE: "warn", CRITICAL_DIVERGENCE: "bear", UNAVAILABLE: "" };
const nsAgo = (ns) => (isNum(ns) ? ago(new Date(ns / 1e6).toISOString()) : "—");
function renderReference() {
  const R = S.ref, el = $("#refs"), st = $("#ref-state"); if (!el) return;
  if (!R || !Array.isArray(R.observations)) {
    el.innerHTML = '<span class="muted">No reference file yet; it appears after the next pipeline run.</span>';
    st.textContent = "—"; st.className = "pill"; return;
  }
  const b = R.bar_divergence_1h || {}, lv = R.live_divergence;
  const worst = [b.status, lv && lv.status].includes("CRITICAL_DIVERGENCE") ? "CRITICAL_DIVERGENCE"
    : [b.status, lv && lv.status].includes("SIGNIFICANT_DIVERGENCE") ? "SIGNIFICANT_DIVERGENCE" : b.n ? b.status : lv ? lv.status : "UNAVAILABLE";
  st.textContent = worst.replace("_DIVERGENCE", "").replace("_", " "); st.className = "pill " + (REF_CLS[worst] || "");
  const rows = R.observations.map((o) => `<tr><td>${esc(o.provider_id)}<div class="dim">${esc(String(o.market_type).replace(/_/g, " ").toLowerCase())}</div></td>
    <td>${o.bid !== null && o.ask !== null ? `${f(o.bid)} / ${f(o.ask)}<div class="dim">spread ${f(o.spread, 2)}</div>` : isNum(o.mid) ? f(o.mid) + '<div class="dim">mid only</div>' : "—"}</td>
    <td>${esc(o.status)}<div class="dim">${esc(o.quality)} · ${esc(o.timestamp_precision)}${isNum(o.latency_ms) ? " · age " + f(o.latency_ms / 1000, 1) + " s at receipt" : ""}</div></td></tr>
    ${o.note ? `<tr><td colspan="3" class="dim" style="white-space:normal">${esc(o.note)}</td></tr>` : ""}`).join("");
  const bars = b.n ? kv([
    ["Same 1h bar vs " + esc(R.primary.replace("twelvedata:", "Twelve Data ")), `${fs(b.diff, 2)} (${fs(b.diff_pct, 3)}%) · ${esc(b.status)}`],
    ["Over " + b.n + " bars: median / p95 |Δ| / max", `${fs(b.median_diff, 2)} / ${f(b.p95_abs_diff, 2)} / ${f(b.max_abs_diff, 2)}`],
    ["Robust z of the last bar", isNum(b.robust_z) ? f(b.robust_z, 1) : "—"],
    ["Observed spread median / p90", `${f(b.spread_median, 2)} / ${f(b.spread_p90, 2)}`],
    ["Primary inside the reference spread", f(b.inside_spread_pct, 0) + "% of bars"]])
    : `<p class="muted">Bar comparison unavailable${b.note ? ": " + esc(b.note) : ""}.</p>`;
  const live = lv ? kv([[`${esc(lv.a)} vs ${esc(lv.b)} now`, `${fs(lv.diff, 2)} (${fs(lv.diff_pct, 3)}%) · ${esc(lv.status)}${isNum(lv.source_time_gap_ms) ? " · Δt " + f(lv.source_time_gap_ms / 1000, 1) + " s" : ""}`]]) : "";
  el.innerHTML = `<table class="t"><tr><th>Source</th><th>Bid / ask</th><th>Status</th></tr>${rows}</table>${bars}${live}
    <p class="note">Checked ${nsAgo(R.generated_ts_ns)}. Bands (fixed, not fitted): &lt;${R.thresholds_pct.CONSISTENT}% consistent, &lt;${R.thresholds_pct.MINOR_DIVERGENCE}% minor, &lt;${R.thresholds_pct.SIGNIFICANT_DIVERGENCE}% significant, otherwise critical. The engine never reads these prices.</p>`;
}

/* ---------- the operator's MT5 broker feed via MetaApi (DISPLAY AND VALIDATION ONLY; quantum/mt5.py) ---------- */
async function loadMt5() {
  try { S.mt5feed = await getJSON("data/mt5.json"); } catch (e) { S.mt5feed = null; }
  renderMt5();
}
function renderMt5() {
  const X = S.mt5feed, el = $("#mt5feed"), st = $("#mt5-state"); if (!el) return;
  // Hidden until a MetaApi account is actually connected (MetaApi bills per account-hour,
  // so most viewers will never connect one); nothing empty or broken is shown.
  const card = $("#mt5-card"); if (card) card.style.display = X && X.status === "OK" ? "" : "none";
  if (!X) { el.innerHTML = '<span class="muted">No MT5 file yet; it appears after the next pipeline run.</span>'; st.textContent = "—"; st.className = "pill"; return; }
  $("#mt5-sym").textContent = X.symbol ? "(" + X.symbol + (X.broker && X.broker.server ? " · " + X.broker.server : "") + ")" : "";
  st.textContent = X.status; st.className = "pill " + (X.status === "OK" ? "bull" : X.status === "UNAVAILABLE" ? "" : "warn");
  if (X.status !== "OK") { el.innerHTML = `<p class="muted">${esc(X.note || "unavailable")}</p>`; return; }
  const k = X.tick || {}, h = (X.candles || {})["1h"] || {};
  const vs = Object.entries(X.vs_primary || {}).filter(([, v]) => v && v.n).map(([tf, v]) =>
    [`Same ${tf} bar: engine − MT5`, `${fs(v.diff, 2)} (${fs(v.diff_pct, 3)}%) · ${esc(v.status)} · median ${fs(v.median_diff, 2)} over ${v.n}`]);
  const fp = X.footprint || {}, lv = (fp.levels || []);
  const near = lv.slice().sort((a, b) => Math.abs(a.price - (k.mid || 0)) - Math.abs(b.price - (k.mid || 0))).slice(0, 14).sort((a, b) => b.price - a.price);
  const mx = Math.max(1, ...near.map((r) => r.buy + r.sell));
  const fpRows = near.map((r) => `<tr><td>${f(r.price, 2)}${r.price === fp.poc ? ' <span class="dim">POC</span>' : ""}</td><td class="bull">${f(r.buy, 0)}</td><td class="bear">${f(r.sell, 0)}</td>
    <td class="${r.delta >= 0 ? "bull" : "bear"}">${fs(r.delta, 0)}</td><td style="width:35%"><div style="height:6px;border-radius:3px;background:var(--neutral);width:${Math.round(((r.buy + r.sell) / mx) * 100)}%"></div></td></tr>`).join("");
  const label = fp.method === "DEAL_SIDE_VOLUME" ? "real deal side and volume from the broker" : "PROXY: ticks classed by the tick rule (up-tick = buy); spot gold has no central traded volume";
  el.innerHTML = kv([
    ["Bid / ask (broker)", isNum(k.bid) ? `${f(k.bid)} / ${f(k.ask)} · spread ${f(k.spread, 2)}` : "—"],
    ["Last tick", isNum(k.source_ts_ns) ? `${tfmt(k.source_ts_ns / 1e9)} · ${esc(k.timestamp_precision)} · ${esc(k.quality)}` : "—"],
    ["1h tick volume (last / median 100)", `${f(h.tick_volume, 0)} / ${f(h.tick_volume_median, 0)}`],
    ...vs]) +
    (near.length ? `<h4 class="evh" style="margin-top:10px">Footprint · last ${fp.n} ticks · step $${f(fp.step, 2)} · Δ ${fs(fp.delta, 0)}</h4>
      <table class="t"><tr><th>Price</th><th>Buy</th><th>Sell</th><th>Δ</th><th></th></tr>${fpRows}</table>
      <p class="note">${esc(label)}. Tick volume is the count of price changes, not traded volume.</p>` : "") +
    `<p class="note">Read in the cloud through MetaApi on each update (about every 15 minutes); the live chip above streams OANDA. Display only: the engine never reads this feed.</p>`;
}

/* ---------- upcoming events (DISPLAY ONLY) ---------- */
async function loadEvents() {
  try { S.events = await getJSON("data/events.json"); } catch (e) { S.events = null; }
  renderEvents();
  renderGuard();
}
const until = (sec) => (sec < 3600 ? Math.max(1, Math.round(sec / 60)) + " min" : sec < 86400 ? (sec / 3600).toFixed(1) + " h" : (sec / 86400).toFixed(1) + " d");
function renderEvents() {
  const E = S.events, el = $("#events"), st = $("#ev-state"); if (!el) return;
  if (!E || !Array.isArray(E.events)) {
    el.innerHTML = '<span class="muted">No calendar published yet; it appears after the next pipeline run.</span>';
    st.textContent = "—"; st.className = "pill"; return;
  }
  const now = Date.now() / 1000;
  const up = E.events.filter((e) => e.t > now - 3 * 3600).slice(0, 12);
  const next = up.find((e) => e.t > now && e.impact === "High");
  st.textContent = !E.ok ? "estimate only" : next ? "high-impact in " + until(next.t - now) : "no high-impact left";
  st.className = "pill " + (!E.ok || (next && next.t - now < 3600) ? "warn" : "");
  const rows = up.map((e) => `<div class="evl${e.t < now ? " past" : ""}${e.impact === "High" ? " hi" : ""}"><span class="mono">${tfmt(e.t)}</span>
    <span>${esc(e.title)}${e.estimated ? ' <span class="dim">(estimate)</span>' : ""}</span>
    <span class="dim">${e.forecast ? "f " + esc(e.forecast) : ""}${e.previous ? " · p " + esc(e.previous) : ""}</span></div>`).join("");
  const safeLink = (u) => (/^https?:\/\//.test(u || "") ? u : "");
  const hl = (E.headlines || []).slice(0, 10).map((h) => {
    const l = safeLink(h.link), t = esc(h.title);
    return `<div class="evl news"><span class="mono">${tfmt(h.t)}</span><span>${l ? `<a href="${esc(l)}" target="_blank" rel="noopener noreferrer nofollow">${t}</a>` : t}</span><span class="dim">${esc(h.source)}</span></div>`;
  }).join("");
  const feeds = (E.feeds || []).map((x) => `<span class="${x.ok ? "" : "warn"}" title="${esc(x.host + ": " + x.note)}">${esc(x.name)} ${x.ok ? x.n : "✕"}</span>`).join(" · ");
  el.innerHTML = `<div class="cal-news"><div><h4 class="evh">Calendar <span class="dim">(high / medium impact)</span></h4>` +
    (rows || '<span class="muted">No USD high/medium-impact events left this week.</span>') +
    `<p class="note">${esc(E.source)} · fetched ${ago(E.generated_utc)}.${E.ok ? "" : " " + esc(E.note) + "."} Display only: the engine's news window is its own rule, and news suppression is off by default.</p></div>` +
    (E.feeds ? `<div><h4 class="evh">News <span class="dim">(gold / USD / rates, last 48 h)</span></h4>${hl || '<span class="muted">No relevant headlines in the last 48 h.</span>'}<p class="note">Feeds: ${feeds || "—"}. Hover a feed for its status. Headlines link to the publisher; display only.</p></div>` : "") + `</div>`;
}

/* ---------- freshness and event guard (DISPLAY ONLY) ---------- */
// The decision and the plan describe the last PROCESSED bar. When bars have closed since, or the
// live price has moved far from that bar's close, or a high-impact USD release is near, say so
// above them and dim the plan. Nothing is recomputed in the browser and no price is changed.
const GUARD_ATR = 1.5;           // fixed a priori (display only): a move this large makes the plan's levels moot
const GUARD_EVENT_MIN = 30;      // minutes either side of a high-impact USD release
function freshness() {
  const D = S.data; if (!D) return null;
  const tf = D.meta.tf_sec, last = Date.parse(D.meta.last_bar_close) / 1000, now = Date.now() / 1000;
  const closed = marketClosed(new Date());
  const behind = closed || !isNum(last) ? 0 : Math.max(0, Math.floor((now - last) / tf));   // bars closed since
  const atr = D.dashboard.atr, ref = D.dashboard.close;
  const liveOk = LIVE.px !== null && !LIVE.err && Date.now() - LIVE.t < 10 * 60000 && !closed;
  const move = liveOk && isNum(ref) ? LIVE.px - ref : null;
  return { behind, move, moveAtr: isNum(move) && isNum(atr) && atr > 0 ? Math.abs(move) / atr : null, last };
}
function nearEvent() {
  const E = S.events; if (!E || !Array.isArray(E.events)) return null;
  const now = Date.now() / 1000;
  return E.events.find((e) => e.impact === "High" && Math.abs(e.t - now) <= GUARD_EVENT_MIN * 60) || null;
}
function renderGuard() {
  const el = $("#guard"); if (!el || !S.data) return;
  const fr = freshness(), ev = nearEvent(), out = [];
  const old = fr && (fr.behind >= 2 || (isNum(fr.moveAtr) && fr.moveAtr >= GUARD_ATR));
  if (old) {
    const why = [fr.behind >= 2 ? `${fr.behind} ${S.data.meta.tf} bars have closed` : "", isNum(fr.move) ? `price has moved ${fs(fr.move, 2)} (${f(fr.moveAtr, 1)} × ATR)` : ""].filter(Boolean).join(" and ");
    out.push(`<div class="banner error"><b>OUT OF DATE.</b> The decision and plan below are for the bar that closed at ${tfmt(fr.last)}. Since then ${why}. Do not act on this plan; wait for the next update.</div>`);
  }
  if (ev) {
    const now = Date.now() / 1000;
    out.push(`<div class="banner info"><b>High-impact USD release${ev.estimated ? " (estimated time)" : ""}:</b> ${esc(ev.title)} at ${tfmt(ev.t)} (${ev.t > now ? "in " + until(ev.t - now) : until(now - ev.t) + " ago"}). Spreads widen and stops can be skipped; the engine's news filter is off (Pine default).</div>`);
  }
  el.innerHTML = out.join("");
  const planCard = $("#plan") && $("#plan").closest(".card");
  if (planCard) planCard.classList.toggle("outdated", !!old);
}
setInterval(() => { if (S.data) { renderGuard(); renderHeader(); } }, 30000);

/* ---------- header / banners ---------- */
/* ---------- macro panel: DXY, USD/JPY, US 10Y, WTI beside gold (DISPLAY ONLY) ----------
   15-minute data from quantum/macro_panel.py (every engine run) plus, when the relay streams them,
   live quotes once a second: USD/JPY and WTI directly, DXY from its six pairs with the ICE formula,
   and the 10Y yield's direction from the T-note price (price up = yield down). Green = the move
   supports gold going up, red = supports gold going down (measured correlation, else textbook). */
const MQ = {};                                     // relay symbol -> {p, t, first:{p,t}} (first seen within 5 min)
function onMacro(q) {
  if (!q) return;
  const now = Date.now();
  for (const [k, v] of Object.entries(q)) {
    if (!v || !isNum(v.p)) continue;
    const prev = MQ[k];
    const first = prev && prev.first && now - prev.first.rx < 300000 ? prev.first : { p: v.p, rx: now };
    MQ[k] = { p: v.p, t: v.t, rx: now, first };
  }
  renderMacroPanel();
}
const freshQ = (k) => MQ[k] && Date.now() - MQ[k].rx < 600000 ? MQ[k] : null;
function liveMacro(key) {
  if (key === "USDJPY") { const q = freshQ("OANDA:USD_JPY"); return q ? { v: q.p, t: q.t } : null; }
  if (key === "WTI") { const q = freshQ("OANDA:WTICO_USD"); return q ? { v: q.p, t: q.t } : null; }
  if (key === "DXY") {                             // ICE U.S. Dollar Index from its six currency pairs
    const P = ["EUR_USD", "USD_JPY", "GBP_USD", "USD_CAD", "USD_SEK", "USD_CHF"].map((x) => freshQ("OANDA:" + x));
    if (P.some((x) => !x)) return null;
    const [eu, uj, gu, uc, us, uf] = P.map((x) => x.p);
    return { v: 50.14348112 * eu ** -0.576 * uj ** 0.136 * gu ** -0.119 * uc ** 0.091 * us ** 0.042 * uf ** 0.036, t: Math.max(...P.map((x) => x.t)) };
  }
  if (key === "US10Y") {                           // direction only: T-note price over the last few minutes, inverted
    const q = freshQ("OANDA:USB10Y_USD"); if (!q || q.p === q.first.p) return q ? { dir: 0, t: q.t } : null;
    return { dir: q.p > q.first.p ? -1 : 1, t: q.t };
  }
  return null;
}
async function loadMacroPanel() { try { S.macroPanel = await getJSON("data/macro_panel.json"); } catch (e) { S.macroPanel = null; } renderMacroPanel(); }
function spark(it, gold) {
  const v = it.spark && it.spark.v; if (!v || v.length < 2) return "";
  const W = 220, H = 54, pad = 3, n = v.length;
  const mm = (a) => { const b = a.filter(isNum); return [Math.min(...b), Math.max(...b)]; };
  const [lo, hi] = mm(v), xs = (i) => pad + (i / (n - 1)) * (W - 2 * pad), ys = (x, l, h) => H - pad - ((x - l) / ((h - l) || 1)) * (H - 2 * pad);
  const path = (a, l, h) => a.map((x, i) => (isNum(x) ? `${i && isNum(a[i - 1]) ? "L" : "M"}${xs(i).toFixed(1)},${ys(x, l, h).toFixed(1)}` : "")).join("");
  const g = it.spark.gold; let gp = "";
  if (g && g.filter(isNum).length > 2) { const [gl, gh] = mm(g); gp = `<path d="${path(g, gl, gh)}" class="sg"/>`; }
  const col = it.gold > 0 ? "var(--bull)" : it.gold < 0 ? "var(--bear)" : "var(--muted)";
  const lastY = ys(v[n - 1], lo, hi).toFixed(1);
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" class="spk" role="img" aria-label="${esc(it.label)} last 2 days with gold">${gp}` +
    `<path d="${path(v, lo, hi)}" fill="none" stroke="${col}" stroke-width="1.6" vector-effect="non-scaling-stroke"/>` +
    `<circle cx="${xs(n - 1).toFixed(1)}" cy="${lastY}" r="2.6" fill="${col}"/></svg>`;
}
function renderMacroPanel() {
  const el = $("#macro-panel"); if (!el) return;
  const M = S.macroPanel;
  if (!M || !Array.isArray(M.items)) { el.innerHTML = `<div class="mp-empty muted">Macro panel appears after the next pipeline run.</div>`; return; }
  el.innerHTML = M.items.map((it) => {
    if (!it.ok) {
      const lv0 = liveMacro(it.key);                 // no 15-minute data, but the relay may still have a live quote
      return `<div class="mbox"><div class="mh"><b>${esc(it.label)}</b><span class="lt ${lv0 ? "on" : ""}">${lv0 ? "live" : esc(it.symbol)}</span></div>` +
        (lv0 && isNum(lv0.v) ? `<div class="mv"><span class="num">${it.unit === "$" ? "$" : ""}${lv0.v.toFixed(it.dec)}</span><span class="dim">no 24 h history yet</span></div>` : "") +
        `<div class="muted mnote">15-minute data unavailable${it.note ? " · " + esc(it.note) : ""}</div></div>`;
    }
    const lv = liveMacro(it.key);
    let last = it.last, chg = it.change, live = false, dirOnly = null;
    if (lv && isNum(lv.v)) { last = lv.v; chg = lv.v - it.ref; live = true; }
    if (lv && it.key === "US10Y") dirOnly = lv.dir;
    // what the move means for gold: sign(move) x sign(r) when r is clear, else the textbook relation
    const sgnR = isNum(it.corr) && Math.abs(it.corr) >= 0.2 ? Math.sign(it.corr) : it.textbook;
    const gimp = dirOnly ? dirOnly * sgnR : chg ? Math.sign(chg) * sgnR : 0;
    const cls = gimp > 0 ? "bull" : gimp < 0 ? "bear" : "";
    const pct = it.ref ? chg / it.ref * 100 : null;
    const fmt = (x) => (isNum(x) ? x.toFixed(it.dec) : "—");
    const arrow = chg > 0 ? "▲" : chg < 0 ? "▼" : "■";
    const view = { ...it, gold: gimp };
    return `<div class="mbox ${cls}">
      <div class="mh"><b>${esc(it.label)}</b><span class="lt ${live || dirOnly !== null ? "on" : ""}">${live ? "live" : dirOnly !== null ? "live dir" : "15 min"}</span></div>
      <div class="mv"><span class="num">${it.unit === "$" ? "$" : ""}${fmt(last)}${it.unit === "%" ? "%" : ""}</span>
        <span class="mchg ${cls}">${arrow} ${chg >= 0 ? "+" : ""}${fmt(chg)} (${isNum(pct) ? (pct >= 0 ? "+" : "") + pct.toFixed(2) : "—"}%)</span></div>
      ${spark(view)}
      <div class="mf"><span class="gi ${cls}">${gimp > 0 ? "▲ supports gold up" : gimp < 0 ? "▼ supports gold down" : "■ neutral for gold"}</span>
        <span class="dim" title="${esc(it.basis || "")}">r ${isNum(it.corr) ? (it.corr >= 0 ? "+" : "") + it.corr.toFixed(2) : "—"} vs gold</span></div>
      ${dirOnly !== null ? `<div class="dim mnote">live: T-note ${dirOnly > 0 ? "falling → yield rising" : dirOnly < 0 ? "rising → yield falling" : "flat"}</div>` : ""}
    </div>`;
  }).join("") + `<div class="mp-key dim">24 h change · 2-day 15-minute line in colour, gold dashed grey · <span class="bull">green = supports gold up</span> · <span class="bear">red = supports gold down</span> · r = correlation of 15-minute returns with gold over the last day</div>`;
}

/* ---------- quote header (display only) ---------- */
// Previous trading day's close: the last bar before the latest New York 17:00 rollover (the engine's
// trading-day rule: a bar belongs to the date of its New York open time + 7 hours).
function prevDayClose(D) {
  const ch = D && D.chart; if (!ch || !ch.t || !ch.t.length) return null;
  const day = (t) => new Date(t * 1000 + 7 * 3600e3).toLocaleDateString("en-CA", { timeZone: "America/New_York" });
  const last = day(ch.t[ch.t.length - 1]);
  for (let i = ch.t.length - 2; i >= 0; i--) if (day(ch.t[i]) !== last) return ch.c[i];
  return null;
}
let QPREV = null;
function renderQuote() {
  const D = S.data, pxEl = $("#q-px"), chEl = $("#q-chg"), mk = $("#q-mkt"); if (!D || !pxEl) return;
  const closed = marketClosed(new Date());
  const fb = D.meta && D.meta.forming;
  const eng = fb && isNum(fb.c) ? fb.c : D.dashboard.close;
  const live = !closed && LIVE.px !== null && !LIVE.err ? LIVE.px : null;
  const p = isNum(live) ? live : eng;
  const pc = prevDayClose(D);
  pxEl.textContent = isNum(p) ? p.toFixed(2) : "—";   // the feed price (the MT5 offset applies to plan levels only)
  pxEl.classList.remove("up", "dn");
  if (isNum(QPREV) && isNum(p) && p !== QPREV) pxEl.classList.add(p > QPREV ? "up" : "dn");
  QPREV = p;
  if (isNum(p) && isNum(pc)) {
    const d = p - pc;
    chEl.textContent = `${d >= 0 ? "+" : ""}${d.toFixed(2)}  ${d >= 0 ? "+" : ""}${(d / pc * 100).toFixed(2)}%`;
    chEl.className = d >= 0 ? "bull" : "bear";
  } else { chEl.textContent = "—"; chEl.className = "muted"; }
  const sess = (D.dashboard.session && D.dashboard.session.label) || "";
  const SESS = { ASIAN: "Asia", LONDON: "London", NY: "New York", "LON-KZ": "London killzone", "LON-FIX": "London fix",
    "LON-CL": "London close", "NY-KZ": "New York killzone", KZ: "killzone", OFF: "off-session" };
  mk.textContent = closed ? "Market closed" : `Open · ${SESS[sess] || sess.toLowerCase() || "—"}`;
  mk.className = "mkt " + (closed ? "closed" : "open");
  mk.title = closed ? "Spot gold is shut Friday 17:00 to Sunday 18:00 New York and daily 17:00-18:00." : `Session of the last closed ${D.meta.tf} bar (engine label ${sess}).`;
}
function renderHeader() {
  const D = S.data; if (!D) return;
  const M = D.meta;
  $("#engine-ver").textContent = `engine ${M.engine_version} · schema B${M.schema_build} · cfg ${M.config_hash}`;
  const fr = freshness();
  $("#updated").textContent = ago(M.generated_utc) + (fr && fr.behind >= 2 ? ` · ${fr.behind} bars behind` : "");
  const chip = $("#chip-updated");
  chip.classList.remove("ok", "stale", "bad");
  chip.classList.add(M.synthetic ? "bad" : fr && fr.behind >= 2 ? "stale" : "ok");
  chip.title = `Last confirmed ${M.tf} bar closed ${new Date(M.last_bar_close).toUTCString()}. Markets close at weekends, so a weekend gap is expected.`;
  $("#source").textContent = M.synthetic ? "SYNTHETIC" : M.price_source.replace("yahoo:", "Yahoo ").replace("twelvedata:", "Twelve Data ");
  $("#freeze").textContent = D.holdout && D.holdout.freeze_utc ? new Date(D.holdout.freeze_utc).toISOString().slice(0, 16).replace("T", " ") + " UTC" : "—";
  const pend = D.holdout && D.holdout.freeze_utc && Date.now() < Date.parse(D.holdout.freeze_utc);
  $("#freeze-lbl").textContent = pend ? "holdout starts" : "holdout since";
  const b = [];
  if (M.synthetic) b.push(`<div class="banner synthetic"><b>SYNTHETIC DATA.</b> This build was generated offline from simulated prices to exercise the engine. Nothing on this page describes the real gold market.</div>`);
  if (S.index && S.index.errors && Object.keys(S.index.errors).length) b.push(`<div class="banner error"><b>Pipeline errors:</b> ${Object.entries(S.index.errors).map(([k, v]) => esc(k + ": " + v)).join(" · ")}</div>`);
  if (!M.synthetic && M.price_source.includes("GC=F")) b.push(`<div class="banner info">Price source is <b>COMEX gold futures</b> (spot XAU/USD was unavailable). Futures trade at a premium to spot; set the <b>MT5 offset</b> to your broker's difference. Add a free Twelve Data key to use spot.</div>`);
  if (M.volume_source && M.volume_source.startsWith("NONE")) b.push(`<div class="banner error">No volume source: volume-gated signals (BOS, displacement, climax) cannot fire.</div>`);
  $("#banners").innerHTML = b.join("");
  renderQuote();
}

/* ---------- side panels ---------- */
/* ---------- arm H2 "Sweep and Value" (pre-registered, Amendment 5; computed by quantum/arm_h2.py) ---------- */
function renderH2() {
  const D = S.data, el = $("#h2"), st = $("#h2-state"); if (!el || !D) return;
  const H = D.h2;
  if (!H || H.error) { el.innerHTML = `<p class="muted">${esc((H && H.error) || "not published yet")}</p>`; st.textContent = "—"; st.className = "pill"; return; }
  const now = H.signal_now, ck = H.checklist || {};
  const open = (H.open || [])[0];
  // backtest.simulate holds one position at a time: a same-side signal while H2 is already in a trade
  // is not taken, so the open trade's levels are the ones that count.
  const held = !!(now && open && open.dir === now.dir && Date.parse(open.entry_time) / 1000 < now.t);
  st.textContent = now ? `${now.dir} ${held ? "held" : "signal"}` : "no setup"; st.className = "pill " + (now ? (now.dir === "LONG" ? "bull" : "bear") : "");
  const score = (c) => (c ? Object.values(c).filter(Boolean).length : 0);
  // The side shown: the live signal's side; else the side the trend rule favours; else the side with
  // more rules met. (Showing the higher count alone put "Long side" on screen in a clear downtrend.)
  const tl = !!(ck.long && ck.long.trend), ts = !!(ck.short && ck.short.trend);
  const side = now ? (now.dir === "LONG" ? "long" : "short") : tl !== ts ? (tl ? "long" : "short")
    : score(ck.long) >= score(ck.short) ? "long" : "short", c = ck[side] || {};
  const other = side === "long" ? "short" : "long";
  const rows = (H.rules || []).map(([k, lt, stx]) => `<li class="${c[k] ? "ok" : "bad"}"><span class="sr">${c[k] ? "met:" : "missing:"}</span>${esc(side === "short" ? stx : lt)}</li>`).join("");
  const p = now || H.last_signal;
  const planHtml = p ? `<div class="why"><b>${now ? "Signal now" : "Last signal"}${held ? " (not taken)" : ""}:</b> ${esc(p.dir)} ${tfmt(p.t)} · entry ${px(p.entry)} · SL ${px(p.sl)} · TP1 ${px(p.tp1)} · TP2 ${px(p.tp2)} <span class="dim">(sweep bar ${tfmt(p.sweep_t)})</span>` +
    (held ? ` <span class="warn">H2 already holds this ${esc(open.dir)} since ${tfmt(Date.parse(open.entry_time) / 1000)}; it takes one position at a time, so the open trade below is the one that counts.</span>` : "") + `</div>` : "";
  const openHtml = open ? `<div class="why"><b>Open H2 trade:</b> ${esc(open.dir)} since ${tfmt(Date.parse(open.entry_time) / 1000)} · entry ${px(open.entry)} · SL ${px(open.sl)} · TP1 ${px(open.tp1)}</div>` : "";
  const nm = H.next_move_in_sample || {}, fw = H.forward || {}, fr = H.freeze || {};
  const next = nm.n ? `After ${nm.n} past H2 signals on ${esc(D.meta.tf)} (in-sample): TP1 reached first ${f(nm.tp1_first_pct, 0)}%, stop first ${f(nm.stop_first_pct, 0)}%, mean ${fs(nm.mean_r, 2)} R, median ${fs(nm.median_r, 2)} R, about ${f(nm.avg_bars, 0)} bars to the exit.` : "No past H2 signals on this timeframe yet.";
  const fwd = fw.n ? `${fw.n} closed · win ${f(fw.win_rate, 0)}% · mean ${fs(fw.avg_r, 2)} R · PF ${f(fw.profit_factor, 2)}` : "no closed trades yet";
  el.innerHTML = `<div class="why"><div class="rhead"><b>${esc(side === "long" ? "Long" : "Short")} side · ${score(c)}/5 rules met</b>${ruleMeter(score(c), 5)}<span class="dim">${other} side ${score(ck[other])}/5</span></div><ul class="gates">${rows}</ul></div>` + planHtml + openHtml +
    `<div class="why"><b>Next movement:</b> ${next} <span class="dim">Small samples: a pattern, not a forecast.</span></div>` +
    `<div class="why"><b>Forward record</b> (since ${fr.freeze_utc ? tfmt(Date.parse(fr.freeze_utc) / 1000) : "—"}; only this counts): ${fwd}. Decision on 1H after 50 trades (Amendment 5).</div>`;
}

/* ---------- arm H3 "Sweep-to-Value" (the Pine line's H2 rule; Amendment 7; computed by quantum/arm_h3.py) ---------- */
function renderH3() {
  const D = S.data, el = $("#h3"), st = $("#h3-state"); if (!el || !D) return;
  const H = D.h3;
  if (!H || H.error) { el.innerHTML = `<p class="muted">${esc((H && H.error) || "not published yet")}</p>`; st.textContent = "—"; st.className = "pill"; return; }
  const now = H.signal_now, ck = H.checklist || {}, open = (H.open || [])[0];
  // one position at a time (backtest.simulate): a same-side signal while H3 already holds a trade is not taken
  const held = !!(now && open && open.dir === now.dir && Date.parse(open.entry_time) / 1000 < now.t);
  st.textContent = now ? `${now.dir} ${held ? "held" : "signal"}` : "no setup"; st.className = "pill " + (now ? (now.dir === "LONG" ? "bull" : "bear") : "");
  const keys = (H.rules || []).map((r) => r[0]);
  const score = (c) => (c ? keys.filter((k) => c[k]).length : 0);
  const tl = !!(ck.long && ck.long.trend), ts = !!(ck.short && ck.short.trend);
  const side = now ? (now.dir === "LONG" ? "long" : "short") : tl !== ts ? (tl ? "long" : "short")
    : score(ck.long) >= score(ck.short) ? "long" : "short", c = ck[side] || {};
  const other = side === "long" ? "short" : "long";
  const rows = (H.rules || []).map(([k, lt, stx]) => `<li class="${c[k] ? "ok" : "bad"}"><span class="sr">${c[k] ? "met:" : "missing:"}</span>${esc(side === "short" ? stx : lt)}</li>`).join("");
  const sc = ck.scores || {};
  const trendLine = `<span class="dim">trend scores 1H ${f(sc["60"], 0)} · 4H ${f(sc["240"], 0)} · 1D ${f(sc.D, 0)} · swing ${side === "long" ? "low " + px(ck.swing_low) : "high " + px(ck.swing_high)}</span>`;
  const p = now || H.last_signal;
  const planHtml = p ? `<div class="why"><b>${now ? "Signal now" : "Last signal"}${held ? " (not taken)" : ""}:</b> ${esc(p.dir)} ${tfmt(p.t)} · entry ${px(p.entry)} · SL ${px(p.sl)} · TP1 ${px(p.tp1)} · TP2 ${px(p.tp2)} <span class="dim">(swept ${px(p.swept)})</span>` +
    (held ? ` <span class="warn">H3 already holds this ${esc(open.dir)} since ${tfmt(Date.parse(open.entry_time) / 1000)}; it takes one position at a time, so the open trade below is the one that counts.</span>` : "") + `</div>` : "";
  const openHtml = open ? `<div class="why"><b>Open H3 trade:</b> ${esc(open.dir)} since ${tfmt(Date.parse(open.entry_time) / 1000)} · entry ${px(open.entry)} · SL ${px(open.sl)} · TP1 ${px(open.tp1)}</div>` : "";
  const nm = H.next_move_in_sample || {}, fw = H.forward || {}, fr = H.freeze || {};
  const next = nm.n ? `After ${nm.n} past H3 signals on ${esc(D.meta.tf)} (in-sample): TP1 reached first ${f(nm.tp1_first_pct, 0)}%, stop first ${f(nm.stop_first_pct, 0)}%, mean ${fs(nm.mean_r, 2)} R, median ${fs(nm.median_r, 2)} R, about ${f(nm.avg_bars, 0)} bars to the exit.` : "No past H3 signals on this timeframe yet.";
  const fwd = fw.n ? `${fw.n} closed · win ${f(fw.win_rate, 0)}% · mean ${fs(fw.avg_r, 2)} R · PF ${f(fw.profit_factor, 2)}` : "no closed trades yet";
  el.innerHTML = `<div class="why"><div class="rhead"><b>${side === "long" ? "Long" : "Short"} side · ${score(c)}/${keys.length} rules met</b>${ruleMeter(score(c), keys.length)}<span class="dim">${other} side ${score(ck[other])}/${keys.length}</span></div><ul class="gates">${rows}</ul>${trendLine}</div>` + planHtml + openHtml +
    `<div class="why"><b>Next movement:</b> ${next} <span class="dim">Small samples: a pattern, not a forecast.</span></div>` +
    `<div class="why"><b>Forward record</b> (since ${fr.freeze_utc ? tfmt(Date.parse(fr.freeze_utc) / 1000) : "—"}; only this counts): ${fwd}. Decision on 1H after 50 trades (Amendment 7).</div>`;
}

/* ---------- Market Brief: the six answers a trader needs in the first seconds (display only) ----------
   Everything here is read from what the engine already published for the last closed bar; nothing is
   forecast here. "Where it is heading" is the engine's own lean and liquidity reach, not a prediction. */
const IC = {
  up: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 11 8 5l5 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  dn: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 5l5 6 5-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  side: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 8h12M10 4l4 4-4 4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  drop: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2s4.5 5 4.5 8a4.5 4.5 0 0 1-9 0C3.5 7 8 2 8 2Z" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>',
  target: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="8" cy="8" r="2.4" fill="currentColor"/></svg>',
  hand: '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3" y="3" width="10" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>',
  plan: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 3h10M3 8h10M3 13h6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
};
const htfDir = (sc) => (!isNum(sc) || sc === 50 ? "n/a" : sc >= 60 ? "up" : sc <= 40 ? "down" : "mixed");
function lastSweep(D) {
  const ch = D.chart, sw = (D.markers || []).filter((m) => m.type === "SWEEP");
  if (!sw.length) return null;
  const m = sw[sw.length - 1], i = ch.t.indexOf(m.t);
  // which pool it took: the PDH/PWH (PDL/PWL) level the wick went through, closest to the wick
  const cands = m.dir < 0 ? [["PDH", ch.pdh], ["PWH", ch.pwh]] : [["PDL", ch.pdl], ["PWL", ch.pwl]];
  let pool = m.dir < 0 ? "PMH" : "PML", lvl = null;
  if (i >= 0) for (const [nm, arr] of cands) {
    const v = arr && arr[i];
    if (isNum(v) && (m.dir < 0 ? m.px >= v : m.px <= v) && (lvl === null || Math.abs(m.px - v) < Math.abs(m.px - lvl))) { pool = nm; lvl = v; }
  }
  return { ...m, pool, lvl, barsAgo: i >= 0 ? ch.t.length - 1 - i : null };
}
function nextLevels(D, price) {
  const d = D.dashboard, lq = d.liquidity || {}, P = lq.pools || {}, st = d.struct || {};
  const L = [["PDH", P.PDH], ["PDL", P.PDL], ["PWH", P.PWH], ["PWL", P.PWL], ["PMH", P.PMH], ["PML", P.PML], ["EQH", P.EQH], ["EQL", P.EQL],
    ["Day high", lq.cdh], ["Day low", lq.cdl], ["Swing high", st.swing_res], ["Swing low", st.swing_sup]].filter(([, v]) => isNum(v));
  const uniq = (arr) => arr.filter((x, k) => !arr.slice(0, k).some((y) => Math.abs(y[1] - x[1]) < 0.01));
  const above = uniq(L.filter(([, v]) => v > price).sort((a, b) => a[1] - b[1]));
  const below = uniq(L.filter(([, v]) => v < price).sort((a, b) => b[1] - a[1]));
  return { above, below };
}
// The live price for display: fresh (< 2 min) and the market open; otherwise null.
function livePrice() {
  if (marketClosed(new Date()) || LIVE.px === null || LIVE.err) return null;
  return Date.now() - (LIVE.rx || LIVE.t) < 120000 ? LIVE.px : null;
}
// 1-second clock: live badge, countdown to the bar close and to the next engine refresh.
function tickClock() {
  const D = S.data, lv = $("#brief-live"), ck = $("#brief-clock"); if (!D || !lv || !ck) return;
  const closed = marketClosed(new Date()), now = Date.now();
  if (closed) { lv.className = "lpill off"; lv.textContent = "Market closed"; }
  else if (livePrice() !== null) {
    const age = Math.max(0, (now - (LIVE.rx || LIVE.t)) / 1000), src = LIVE.src === "stream" && streaming() ? "ticks" : "gold-api · 5 s";
    lv.className = "lpill on"; lv.textContent = `Live · ${src} · ${age < 10 ? age.toFixed(1) : Math.round(age)} s ago`;
  } else { lv.className = "lpill stale"; lv.textContent = "Live price unavailable"; }
  const tf = D.meta.tf_sec, t = now / 1000, nextClose = (Math.floor(t / tf) + 1) * tf;
  const mmss = (x) => `${Math.floor(x / 60)}:${String(Math.floor(x % 60)).padStart(2, "0")}`;
  // the scheduler dispatches at :01 / :16 / :31 / :46; a run takes about 2-3 minutes to publish
  const d0 = new Date(now), m = d0.getUTCMinutes(), slot = [1, 16, 31, 46].find((x) => x > m);
  const disp = new Date(Date.UTC(d0.getUTCFullYear(), d0.getUTCMonth(), d0.getUTCDate(), d0.getUTCHours() + (slot === undefined ? 1 : 0), slot === undefined ? 1 : slot) + 180000);
  ck.textContent = closed ? "engine resumes when the market reopens" : `${D.meta.tf} bar closes in ${mmss(nextClose - t)} · next engine update ≈ ${tfmt(disp.getTime() / 1000, false)}`;
}
setInterval(tickClock, 1000);
function renderBrief() {
  const el = $("#brief"), D = S.data; if (!el || !D) return;
  const d = D.dashboard, ch = D.chart, p = d.plan || {}, M = D.meta;
  const fb = M.forming, eng = fb && isNum(fb.c) ? fb.c : d.close, lp = livePrice(), price = isNum(lp) ? lp : eng;
  const last = ch.t.length - 1, e200 = ch.ema200[last], up = d.bull_score >= d.bear_score;
  const tile = (cls, icon, k, v, sub) => `<div class="bt ${cls}"><div class="bk">${IC[icon] || ""}${k}</div><div class="bv">${v}</div><div class="bs">${sub}</div></div>`;
  // 1 trend
  const bl = d.bias_label || "—", tUp = /BULL/.test(bl), tDn = /BEAR/.test(bl);
  const st = d.struct || {}, sType = st.bull_act ? `bullish ${st.bull_type}` : st.bear_act ? `bearish ${st.bear_type}` : "no active break";
  const sAge = st.bull_act ? st.bull_age : st.bear_act ? st.bear_age : null;
  const mtf = (d.mtf && d.mtf.scores) || {};
  const t1 = tile(tUp ? "bull" : tDn ? "bear" : "", tUp ? "up" : tDn ? "dn" : "side", `Current trend · ${esc(M.tf)}`, esc(bl.replace("-ISH", "ISH").replace("BULLISH", "Bullish").replace("BEARISH", "Bearish").replace("BULL", "Bull").replace("BEAR", "Bear").replace("RANGE", "Range").replace("NEUTRAL", "Neutral")),
    ((tUp && htfDir(mtf["240"]) === "down" && htfDir(mtf.D) === "down") || (tDn && htfDir(mtf["240"]) === "up" && htfDir(mtf.D) === "up") ? '<b class="warn">Against the 4H and 1D trend.</b><br>' : "") + `Price ${isNum(e200) ? (price > e200 ? "above" : "below") + " EMA 200" : ""} · structure ${esc(sType)}${isNum(sAge) && sAge >= 0 ? ` (${sAge} bars ago)` : ""}<br>Higher timeframes: 4H ${htfDir(mtf["240"])} · 1D ${htfDir(mtf.D)} · ${esc(d.regime ? d.regime.label.toLowerCase() : "")}`);
  // 2 where it is heading (the engine's lean, not a forecast)
  const rs = (d.liquidity && d.liquidity.reach_scores) || {};
  const lean = Math.abs(d.bull_score - d.bear_score) < 5 ? "No clear lean" : up ? "Leaning up" : "Leaning down";
  const t2 = tile(lean === "No clear lean" ? "" : up ? "bull" : "bear", lean === "No clear lean" ? "side" : up ? "up" : "dn", `Where it is heading · ${esc(M.tf)}`, lean,
    `Long ${f(d.bull_score, 0)}% · Short ${f(d.bear_score, 0)}% · Range ${f(d.range_score, 0)}%<br>${isNum(rs.PDH) ? `Reach: PDH ${f(rs.PDH, 0)}% vs PDL ${f(rs.PDL, 0)}%` : ""} <span class="dim">engine scores, not a forecast</span>`);
  // 3 last liquidity sweep
  const sw = lastSweep(D);
  const t3 = sw ? tile(sw.dir < 0 ? "bear" : "bull", "drop", "Last liquidity taken", `${sw.dir < 0 ? "Buy-side" : "Sell-side"} @ ${px(sw.px)}`,
    `Wick through ${sw.pool}${isNum(sw.lvl) ? " " + px(sw.lvl) : ""}, closed back ${sw.dir < 0 ? "below" : "above"}<br>${tfmt(sw.t)}${isNum(sw.barsAgo) ? ` · ${sw.barsAgo} bars ago` : ""}`)
    : tile("", "drop", "Last liquidity taken", "None in view", "No PDH/PDL/PWH/PWL sweep on the chart window");
  // 4 next target: the nearest liquidity on the side of the lean; the other side is the risk
  const nl = nextLevels(D, price), tgt = (up ? nl.above : nl.below)[0], nxt = (up ? nl.above : nl.below)[1], opp = (up ? nl.below : nl.above)[0];
  const t4 = tgt ? tile(up ? "bull" : "bear", "target", "Next target", `${esc(tgt[0])} ${px(tgt[1])}`,
    `${fs(tgt[1] - price, 2)} from price${nxt ? ` · then ${esc(nxt[0])} ${px(nxt[1])}` : ""}<br>${opp ? `Opposite liquidity: ${esc(opp[0])} ${px(opp[1])} (${fs(opp[1] - price, 2)})` : ""}`)
    : tile("", "target", "Next target", "—", "No liquidity level on that side");
  // 5 what to do now
  const dec = d.decision, sig = dec === "BUY" || dec === "SELL";
  const fr = freshness(), ev = nearEvent();
  const log = String(d.decision_log || ""), mm = log.match(/^([▲▼])\d\/7(?: \[✗([^\]]*)\])?/);
  const fails = mm ? (mm[2] || "").split(/\s+/).filter(Boolean).map((x) => (x.startsWith("HTF") ? "HTF" : x)) : [];
  const need = fails.map((k) => (GATES.find((g) => g[0] === k) || [k, k])[1].replace(" (London / New York)", "")).join(" · ");
  const doNow = sig ? `${dec} now` : dec === "WAIT" ? "Stay flat · wait" : dec === "RISK LOCK" ? "Stop · risk lock" : "No trade";
  const warn = (fr && fr.behind >= 2 ? `Data ${fr.behind} bars old: do not act. ` : "") + (ev ? `High-impact USD event near (${esc(ev.title || ev.event || "release")}). ` : "") + (marketClosed(new Date()) ? "Market closed. " : "");
  const t5 = tile(sig ? (dec === "BUY" ? "bull act" : "bear act") : "warn act", sig ? (dec === "BUY" ? "up" : "dn") : "hand", "What to do now", esc(doNow),
    (warn ? `<b class="warn">${warn}</b><br>` : "") + (sig ? `Entry ${px(p.entry)} · stop ${px(p.sl)} · TQ ${d.trade_quality}` : /^RANGE/.test(log) ? "Market is ranging: no side has an edge." : need ? `Waiting for: ${esc(need)}` : esc(d.blk_why || "")));
  // 6 trade plan
  const side = p.long ? "LONG" : "SHORT";
  const planV = isNum(p.entry) ? `<span class="${p.long ? "bull" : "bear"}">${side}</span> ${px(p.entry)}` : "—";
  const t6 = `<div class="bt plan ${sig ? (p.long ? "bull" : "bear") : ""}"><div class="bk">${IC.plan}Trade plan ${sig ? "" : '<span class="hyp">hypothetical · no signal</span>'}</div>
    <div class="bv">${planV}</div>
    <div class="pl"><span><i>Stop</i><b class="bear">${px(p.sl)}</b></span><span><i>TP1</i><b class="bull">${px(p.tp1)}</b></span><span><i>TP2</i><b class="bull">${px(p.tp2)}</b></span><span><i>TP3</i><b class="bull">${px(p.tp3)}</b></span><span><i>R:R</i><b>1:${f(p.rr1, 1)}</b></span></div>
    <div class="bs">${isNum(p.sl) && isNum(p.tp1) ? `Price ${px(price)} · to stop <b class="bear">${fs(p.sl - price, 2)}</b> · to TP1 <b class="bull">${fs(p.tp1 - price, 2)}</b><br>` : ""}${esc((p.tp_basis || []).length ? `Targets ${p.tp_basis.join(" / ")} · stop ${p.sl_basis || ""}` : "")}${d.kelly ? ` · risk ${f(d.kelly.kelly_pct, 2)}%` : ""}</div></div>`;
  el.innerHTML = `<div class="bhd"><span class="btitle">Market brief</span><span class="lpill" id="brief-live"></span><span class="bpx">${px(price)}</span>` +
    `<span class="dim">XAUUSD · ${esc(M.tf)} · analysis as of the bar closed ${tfmt(Date.parse(M.last_bar_close) / 1000)}</span><span class="dim clk" id="brief-clock"></span></div>
    <div class="bgrid">${t1}${t2}${t3}${t4}${t5}${t6}</div>`;
  tickClock();
}

// segmented progress for "n of total rules met" (display only)
function ruleMeter(n, total) {
  const cls = n === total ? "full" : n >= total - 1 ? "near" : "";
  return `<span class="rmeter ${cls}" role="img" aria-label="${n} of ${total} rules met">${Array.from({ length: total }, (_, i) => `<i class="${i < n ? "on" : ""}"></i>`).join("")}</span>`;
}

/* ---------- decision transparency (DISPLAY ONLY; reads what the engine already published) ---------- */
// The engine's decision log, e.g. "▼5/7 [✗Sess Trig] NO-TRIG ctx:RgM+R+", in plain words.
const GATES = [["Trend", "Trend strong enough"], ["HTF", "Higher timeframe not against it"], ["Sess", "Active session (London / New York)"],
  ["Recent", "Recent bar"], ["News", "No news block"], ["DD", "No drawdown lock"], ["Trig", "Trigger bar: structure break or displacement"]];
function whyHtml(d, D) {
  const log = String(d.decision_log || "");
  if (/^RANGE/.test(log)) return `<div class="why"><b>Why ${esc(d.decision)}:</b> the market is ranging, so no side has an edge. The engine trades only in a trend.</div>`;
  const m = log.match(/^([▲▼])\d\/7(?: \[✗([^\]]*)\])?/); if (!m) return "";
  const side = m[1] === "▲" ? "long" : "short", fails = (m[2] || "").split(/\s+/).filter(Boolean).map((x) => (x.startsWith("HTF") ? "HTF" : x));
  const rows = GATES.map(([k, txt]) => `<li class="${fails.includes(k) ? "bad" : "ok"}"><span class="sr">${fails.includes(k) ? "missing:" : "met:"}</span>${txt}${k === "Sess" && d.blk_why && d.blk_why.startsWith("SESS") ? ` <span class="dim">(${esc(d.blk_why)})</span>` : ""}${k === "Trend" && d.blk_why && d.blk_why.startsWith("TREND") ? ` <span class="dim">(${esc(d.blk_why)})</span>` : ""}</li>`).join("");
  const fn = d.funnel || {}, rate = fn.bars ? fn.sig / fn.bars : null, wk = 5 * 23 * 3600 / D.meta.tf_sec;
  const passed = isNum(fn.pass_) && fn.bars ? fn.pass_ / fn.bars : null;
  const waitFor = d.decision === "WAIT" ? (fails.length === 1 && fails[0] === "Trig" ? `Everything is in place for a ${side}. It is waiting for a trigger bar.` :
    `A ${side} still needs: ${fails.map((f) => (GATES.find((g) => g[0] === f) || [f, f])[1]).join("; ")}.`) : "";
  return `<div class="why"><div class="rhead"><b>${d.decision === "WAIT" ? "Why WAIT" : "Gates"} · ${side} side · ${7 - fails.length}/7 gates</b>${ruleMeter(7 - fails.length, 7)}</div>${waitFor ? `<p class="lead">${esc(waitFor)}</p>` : ""}<ul class="gates">${rows}</ul>` +
    (rate !== null ? `<div class="dim">Over the last ${fn.bars} ${esc(D.meta.tf)} bars, entry signals fired on ${fn.sig} (${(rate * 100).toFixed(1)}%)` +
      (passed !== null ? ` and ${fn.pass_} also passed the quality, EV and probability vetoes (about ${(passed * wk).toFixed(1)} a week)` : "") +
      `. Most bars are WAIT by design: an entry needs every gate on the same bar.</div>` : "") + `</div>`;
}
function lastSignalHtml(D) {
  const B = D.backtest && D.backtest.treatment; if (!B) return "";
  const open = (B.open || [])[0], tr = (B.trades || []).filter((t) => !t.open), last = tr[tr.length - 1];
  const when = (iso) => tfmt(Date.parse(iso) / 1000);
  if (open) return `<div class="why"><b>Open trade:</b> ${esc(open.dir)} since ${when(open.entry_time)} · entry ${px(open.entry)} · SL ${px(open.sl)} · TP1 ${px(open.tp1)} · TP2 ${px(open.tp2)} <span class="dim">(treatment arm; WAIT on later bars does not close it)</span></div>`;
  if (last) return `<div class="why dim">Last signal: ${esc(last.dir)} ${when(last.entry_time)} at ${px(last.entry)} → ${esc(last.exit_reason)} ${fs(last.r, 2)} R (${when(last.exit_time)})</div>`;
  return "";
}
// Is P better than always quoting the base rate? Brier of the trades' entry P vs the constant base rate.
function calCheck(D) {
  const c = D.backtest && D.backtest.treatment && D.backtest.treatment.calibration;
  if (!c || !isNum(c.brier) || !c.n) return "—";
  const b = c.base_rate / 100, ref = b * (1 - b), better = c.brier < ref;
  return `Brier ${f(c.brier, 3)} vs ${f(ref, 3)} for always ${pct(c.base_rate)} · n${c.n} · <span class="${better ? "" : "warn"}">${better ? "better than the base rate" : "NOT better than the base rate: read P as a ranking, not a probability"}</span>`;
}

function renderSide() {
  const D = S.data; if (!D) return;
  const d = D.dashboard, p = d.plan, a = D.analog, M = D.meta;
  const dec = d.decision;
  const cls = dec === "BUY" ? "buy" : dec === "SELL" ? "sell" : dec === "NO TRADE" ? "notrade" : dec === "RISK LOCK" ? "risk" : "";
  const sub = dec === "BUY" || dec === "SELL" ? `confidence ${d.confidence}/100 (agreement score, not a probability)`
    : dec === "NO TRADE" ? `setup vetoed — ${[d.tq_floor_veto ? "TQ below floor" : "", d.ev_veto ? "race EV < 0" : "", d.cal_veto ? "P below minimum" : "", d.risk && d.risk.lock ? "risk lock" : ""].filter(Boolean).join(", ")}`
    : dec === "RISK LOCK" ? d.risk.lock_str
    : dec === "WARMUP" ? `statistics warming up: ROLL effective N ${d.oos_neff}/10`
    : `no setup${d.blk_why ? " — " + d.blk_why : ""}`;
  const b = d.bull_score, s = d.bear_score, r = d.range_score;
  $("#decision").className = "card decision " + cls;
  $("#decision").innerHTML = `
    <div class="sub">DECISION · ${esc(M.tf)} · bar closed ${tfmt(Date.parse(M.last_bar_close) / 1000)}</div>
    <div class="label ${dec === "BUY" ? "bull" : dec === "SELL" ? "bear" : dec === "NO TRADE" || dec === "RISK LOCK" ? "warn" : ""}">${esc(dec)}</div>
    <div class="sub">${esc(sub)}</div>
    <div class="bar3" title="Bull / Range / Bear composite"><span style="width:${b}%;background:var(--bull)"></span><span style="width:${r}%;background:var(--neutral)"></span><span style="width:${s}%;background:var(--bear)"></span></div>
    <div class="sub mono">L ${f(b, 0)} · R ${f(r, 0)} · S ${f(s, 0)} · bias <b>${esc(d.bias_label)}</b> · ${esc(d.regime.label)} ${esc(d.regime.vol_tag)} · ${esc(d.session.label)}</div>
    <div class="sub mono" title="Which gate terms pass">${esc(d.decision_log)}</div>` + whyHtml(d, D) + lastSignalHtml(D);

  const sig = dec === "BUY" || dec === "SELL";
  $("#plan-dir").textContent = (p.long ? "LONG" : "SHORT") + (sig ? "" : " · no signal");
  $("#plan-dir").className = "pill " + (sig ? (p.long ? "bull" : "bear") : "");
  $("#plan-dir").title = sig ? "Side of the current signal." : `No signal: a hypothetical plan on the side of the final scores (L${f(d.bull_score, 0)} ${p.long ? "≥" : "<"} S${f(d.bear_score, 0)}), the same scores as the bias label (web.5, Pine v43). WAIT means no trade.`;
  $("#plan-mt5").textContent = Number(S.mt5) ? `(MT5 ${fs(Number(S.mt5))})` : "";
  const planTxt = `XAUUSD ${M.tf} ${p.long ? "BUY" : "SELL"} | entry ${px(p.entry)} SL ${px(p.sl)} TP1 ${px(p.tp1)} TP2 ${px(p.tp2)} TP3 ${px(p.tp3)}`;
  const touch = isNum(p.p_tp1) ? `~${f(p.p_tp1, 0)} / ${f(p.p_tp2, 0)} / ${f(p.p_tp3, 0)}% · SL ~${f(p.p_sl, 0)}%` : "—";
  $("#plan").innerHTML = `
    <div class="plan-grid">
      <div class="cell"><div class="k">Entry</div><div class="v">${px(p.entry)}</div></div>
      <div class="cell sl"><div class="k">Stop · ${esc(p.sl_basis)}</div><div class="v">${px(p.sl)}</div></div>
      <div class="cell"><div class="k">Risk</div><div class="v">${f(p.dist, 2)}</div></div>
      <div class="cell tp"><div class="k">TP1 · ${esc(p.tp_basis[0])}</div><div class="v">${px(p.tp1)}</div></div>
      <div class="cell tp"><div class="k">TP2 · ${esc(p.tp_basis[1])}</div><div class="v">${px(p.tp2)}</div></div>
      <div class="cell tp"><div class="k">TP3 · ${esc(p.tp_basis[2])}</div><div class="v">${px(p.tp3)}</div></div>
    </div>
    ${kv([["R multiples", `1:${f(p.rr1, 1)} / 1:${f(p.rr2, 1)} / 1:${f(p.rr3, 1)}`],
      ["Race EV (TP1 vs SL)", isNum(p.ev) ? `<span class="${p.ev >= 0 ? "bull" : "bear"}">${fs(p.ev, 2)} R</span> <span class="dim">n${f(p.race_n, 0)}</span>` : "—"],
      [`Touch within ${p.horizon_bars} bars`, touch]])}
    <p class="note">Touch rates are marginal excursion frequencies over ${p.horizon_bars} bars, not a TP-before-SL race; the race EV is the expectancy. ${sig ? "Plan direction follows the signal." : `<b>No signal:</b> this is a hypothetical plan on the side of the final scores (L${f(d.bull_score, 0)} vs S${f(d.bear_score, 0)}), the same scores as the bias label, not a trade.`}</p>
    <button class="icon-btn copy" id="copy-plan" style="margin-top:8px;width:100%">Copy plan for MT5</button>`;
  $("#copy-plan").onclick = () => { navigator.clipboard && navigator.clipboard.writeText(planTxt); $("#copy-plan").textContent = "Copied"; setTimeout(() => ($("#copy-plan").textContent = "Copy plan for MT5"), 1500); };

  const fitted = d.cal_fit && isNum(d.cal_fit[0]);
  $("#p-state").textContent = fitted ? (d.cal_drift ? "DRIFT → raw" : "fitted in-sample") : "unfitted";
  $("#p-state").className = "pill " + (fitted && !d.cal_drift ? "" : "warn");
  $("#p-state").title = "A calibration curve fitted on the development history. It is not validated out of sample, and on that history the scores did not separate winners from losers (F-A34). Only the forward holdout can show whether these probabilities hold.";
  $("#prob").innerHTML = kv([
    ["P(long resolves up)", isNum(d.p_long) ? pct(d.p_long * 100) : "—"],
    ["P(short resolves down)", isNum(d.p_short) ? pct(d.p_short * 100) : "—"],
    ["Calibration gate", d.cal_gate_ready ? `live · min P ${pct(M.config.cal_gate_min_p * 100)}` : "inactive (needs a fit and ROLL N≥10)"],
    ["Analog EV / match", `${a.match > 0 ? fs(a.ev, 2) + " R" : "—"} · A${a.match}${a.match < 30 ? " LOW" : ""}`],
    ["Win rate (ROLL)", `${pctN(a.oos_wr, a.oos_n)} · n${a.oos_n}`],   // no ±: a rolling slice is not a holdout (F-037 / F-A14)
    ["IS vs ROLL", `${pctN(a.is_wr, a.is_n)} / ${pctN(a.oos_wr, a.oos_n)}${a.is_n > 0 && a.oos_n > 0 && a.is_wr - a.oos_wr > 15 ? ' <span class="warn">!FIT</span>' : ""}`],
    ["Calibration grade", `${esc(a.cal_grade)} ${a.cal_grade_pct}/100 ${esc(a.cal_detail || "")}`],
    ["Check on this timeframe's trades", calCheck(D)],
  ]) + `<p class="note">ROLL is a rolling trailing slice, <b>not</b> a holdout (F-037). The only out-of-sample evidence is the frozen forward holdout in the Backtest tab.</p>`;

  const tq = d.trade_quality;
  $("#tq-grade").textContent = `${d.tq_grade} · floor ${d.eff_tq_min}`;
  $("#tq-grade").className = "pill " + (tq >= d.eff_tq_min ? "bull" : "warn");
  $("#tq").innerHTML = `<div style="display:flex;align-items:baseline;gap:8px"><div style="font:800 26px var(--mono)">${tq}</div><div class="muted">/100 ${esc(d.tq_basis || "")}</div></div>
    <div class="meter" style="margin:6px 0 10px"><span style="width:${tq}%"></span></div>` +
    kv([["Vetoes", esc([d.tq_floor_veto ? "TQ<floor" : "", d.ev_veto ? "EV<0" : "", d.cal_veto ? "P<min" : "", d.risk && d.risk.lock ? "risk lock" : ""].filter(Boolean).join(" · ")) || '<span class="bull">none</span>'],
      ["Confidence", `${d.confidence}/100 ${esc(d.conf_label)}`], ["Structure", esc(structStr(d.struct))], ["Auction", `${esc(d.auction.state)} ${d.auction.prob}% ${esc(d.auction.cycle)}`]]);

  const k = d.kelly;
  const acct = S.account || M.config.account_size;
  const lots = p.dist > 0 ? Math.floor((acct * Math.max(k.kelly_pct, 0) / 100 / (p.dist * M.config.point_value)) / 0.01) * 0.01 : 0;
  $("#risk-state").textContent = d.risk.lock ? "LOCKED" : "open";
  $("#risk-state").className = "pill " + (d.risk.lock ? "bear" : "bull");
  $("#risk").innerHTML = kv([
    ["Tracker today", esc(d.risk.lock_str || "—")],
    ["Open tracked plan", isNum(d.risk.open_entry) ? `${d.risk.open_long ? "BUY" : "SELL"} ${px(d.risk.open_entry)} → SL ${px(d.risk.open_sl)} / TP1 ${px(d.risk.open_tp)}` : "none"],
    ["Kelly (half, Wilson LB)", `${f(k.kelly_pct, 2)}% <span class="dim">${esc(k.detail)}</span>`],
    ["Account", `<input id="acct" type="number" value="${acct}" style="width:90px;background:var(--bg-2);color:var(--text);border:1px solid var(--line);border-radius:6px;padding:2px 5px;font:12px var(--mono)"> USD`],
    ["Lots (100 oz)", lots >= 0.01 ? f(lots, 2) : (k.kelly_pct > 0 ? "below 0.01 minimum" : "0 (no edge sized)")],
  ]) + `<p class="note">Sizing is a ceiling (floored to 0.01 lot). The tracker follows the engine's own signals in virtual R; it cannot see your broker account.</p>`;
  $("#acct").onchange = (e) => { S.account = Number(e.target.value) || null; store.set("account", S.account); renderSide(); };
}
function structStr(st) {
  if (st.bull_act) return `▲${st.bull_type} ${st.bull_age}b`;
  if (st.bear_act) return `▼${st.bear_type} ${st.bear_age}b`;
  return "no active structure";
}

/* ---------- chart ---------- */
let C = null;
/* ---------- chart labels layer: level segments with end tags, and event labels (display only) ----------
   Levels run from the bar where they formed to the current candle and carry their name at that end;
   overlay lines (EMAs, VWAPs, bands) are named at their last point; BOS / CHoCH / MSS / sweep / signal
   events get a filled label above (bearish) or below (bullish) the bar, stacked so they never overlap. */
class LabelsPrimitive {
  constructor() { this.segs = []; this.ends = []; this.events = []; this.hl = new Map(); this.lastT = null; }
  attached({ chart, series, requestUpdate }) { this.chart = chart; this.series = series; this.req = requestUpdate; }
  detached() {}
  set(o) { Object.assign(this, o); this.req && this.req(); }
  updateAllViews() {}
  paneViews() {
    const self = this;
    return [{ zOrder: () => "top", renderer: () => ({ draw: (target) => target.useBitmapCoordinateSpace((sc) => self.draw(sc)) }) }];
  }
  draw(sc) {
    const ctx = sc.context, hr = sc.horizontalPixelRatio, vr = sc.verticalPixelRatio, ts = this.chart.timeScale(), se = this.series;
    const W = sc.bitmapSize.width / hr, xEnd = this.lastT !== null ? ts.timeToCoordinate(this.lastT) : null;
    if (xEnd === null) return;
    const font = (px, w = 600) => `${w} ${px * vr}px Inter, system-ui, sans-serif`;
    const pill = (x, y, text, bg, fg, border) => {     // x, y in CSS px; returns width
      ctx.font = font(10.5, 700);
      const tw = ctx.measureText(text).width / hr, w = tw + 10, h = 16;
      ctx.fillStyle = bg; ctx.beginPath(); ctx.roundRect(x * hr, (y - h / 2) * vr, w * hr, h * vr, 3 * hr); ctx.fill();
      if (border) { ctx.strokeStyle = border; ctx.lineWidth = 1 * hr; ctx.stroke(); }
      ctx.fillStyle = fg; ctx.textBaseline = "middle"; ctx.fillText(text, (x + 5) * hr, y * vr + 0.5 * vr);
      return w;
    };
    // 1 level segments: origin bar -> current candle
    for (const g of this.segs) {
      const y = se.priceToCoordinate(g.price); if (y === null) continue;
      let x0 = ts.timeToCoordinate(g.t0); if (x0 === null) x0 = 0;
      ctx.strokeStyle = g.color; ctx.lineWidth = (g.w || 1) * hr;
      ctx.setLineDash(g.dash === 1 ? [2 * hr, 3 * hr] : g.dash === 2 ? [6 * hr, 4 * hr] : []);
      ctx.beginPath(); ctx.moveTo(Math.max(0, x0) * hr, Math.round(y * vr) + 0.5); ctx.lineTo(xEnd * hr, Math.round(y * vr) + 0.5); ctx.stroke();
    }
    ctx.setLineDash([]);
    // 2 end tags beside the current candle, spread so they never overlap (a leader joins a moved tag)
    const tags = [];
    for (const g of [...this.segs.filter((s) => s.label), ...this.ends]) {
      const y = se.priceToCoordinate(g.price); if (y !== null) tags.push({ ...g, y, ty: y });
    }
    tags.sort((a, b) => a.y - b.y);
    for (let k = 1; k < tags.length; k++) if (tags[k].ty - tags[k - 1].ty < 17) tags[k].ty = tags[k - 1].ty + 17;
    const x = xEnd + 10;
    for (const g of tags) {
      if (Math.abs(g.ty - g.y) > 1) { ctx.strokeStyle = g.color; ctx.lineWidth = 1 * hr; ctx.beginPath(); ctx.moveTo(xEnd * hr, g.y * vr); ctx.lineTo((x - 2) * hr, g.ty * vr); ctx.stroke(); }
      pill(x, g.ty, g.label, g.solid ? g.color : this.bg, g.solid ? "#ffffff" : g.color, g.color);
    }
    // 3 event labels above / below their bar, in lanes so they do not collide
    const placed = { up: [], dn: [] };
    for (const e of this.events) {
      const xb = ts.timeToCoordinate(e.t); if (xb === null || xb < -40 || xb > W + 40) continue;
      const hl = this.hl.get(e.t); if (!hl) continue;
      const above = e.dir < 0, base = se.priceToCoordinate(above ? hl[0] : hl[1]); if (base === null) continue;
      ctx.font = font(10.5, 700);
      const w = ctx.measureText(e.text).width / hr + 10, x0 = xb - w / 2;
      // place the label clear of every label already drawn (true box collision), moving away from the bar
      const boxes = placed[above ? "up" : "dn"].concat(placed[above ? "dn" : "up"]);
      let y = above ? base - 22 : base + 22, tries = 0;
      const hit = (yy) => boxes.some((r) => x0 < r.x1 + 3 && x0 + w > r.x0 - 3 && Math.abs(yy - r.y) < 18);
      while (tries < 3 && hit(y)) { y += above ? -18 : 18; tries++; }
      if (hit(y)) continue;                                             // too crowded: the shape and the legend still show it
      placed[above ? "up" : "dn"].push({ x0, x1: x0 + w, y });
      // a hairline from the label to its bar
      ctx.strokeStyle = e.color; ctx.globalAlpha = 0.5; ctx.lineWidth = 1 * hr; ctx.beginPath();
      ctx.moveTo(xb * hr, (above ? y + 8 : y - 8) * vr); ctx.lineTo(xb * hr, (above ? base - 4 : base + 4) * vr); ctx.stroke(); ctx.globalAlpha = 1;
      pill(x0, y, e.text, e.solid ? e.color : this.bg, e.solid ? "#ffffff" : e.color, e.color);
    }
  }
}
class ZonesPrimitive {
  constructor() { this.zones = []; this.cone = null; }
  attached({ chart, series, requestUpdate }) { this.chart = chart; this.series = series; this.req = requestUpdate; }
  detached() {}
  set(zones) { this.zones = zones; this.req && this.req(); }
  updateAllViews() {}
  paneViews() {
    const self = this;
    return [{
      zOrder: () => "bottom",
      renderer: () => ({
        draw: (target) => {
          target.useBitmapCoordinateSpace((scope) => {
            const ctx = scope.context, hr = scope.horizontalPixelRatio, vr = scope.verticalPixelRatio;
            const ts = self.chart.timeScale();
            for (const z of self.zones) {
              let x0 = ts.timeToCoordinate(z.t0), x1 = z.t1 ? ts.timeToCoordinate(z.t1) : scope.bitmapSize.width / hr;
              if (x0 === null) x0 = 0;
              if (x1 === null) x1 = scope.bitmapSize.width / hr;
              const y0 = self.series.priceToCoordinate(z.hi), y1 = self.series.priceToCoordinate(z.lo);
              if (y0 === null || y1 === null) continue;
              ctx.fillStyle = z.fill; ctx.strokeStyle = z.stroke; ctx.lineWidth = 1 * hr;
              const X = Math.round(x0 * hr), Y = Math.round(Math.min(y0, y1) * vr), W = Math.max(1, Math.round((x1 - x0) * hr)), H = Math.max(1, Math.round(Math.abs(y1 - y0) * vr));
              ctx.fillRect(X, Y, W, H); ctx.strokeRect(X, Y, W, H);
              if (z.label) { ctx.fillStyle = z.stroke; ctx.font = `${10 * vr}px Inter, sans-serif`; ctx.fillText(z.label, X + 4 * hr, Y + 11 * vr); }
            }
          });
        },
      }),
    }];
  }
}
// Axis tick labels follow the Time selector (the library's default labels are UTC, which put the
// axis five hours away from the legend and the decision card for a UTC+5 viewer).
function tickFmt(t, type) {
  if (!isNum(t)) return "";
  const opt = type === 0 ? { year: "numeric" } : type === 1 ? { month: "short" } : type === 2 ? { day: "numeric", month: "short" }
    : { hour: "2-digit", minute: "2-digit", hour12: false, ...(type === 4 ? { second: "2-digit" } : {}) };
  if (S.tz !== "local") opt.timeZone = S.tz;
  try { return new Intl.DateTimeFormat(LOCALE, opt).format(new Date(t * 1000)); } catch (e) { return ""; }
}
function chartOpts() {
  const tf = (t) => { try { return isNum(t) ? tfmt(t, true) : ""; } catch (e) { return ""; } };
  return {
    layout: { background: { type: "solid", color: css("--card") }, textColor: css("--muted"), fontFamily: "Inter, system-ui, sans-serif", fontSize: 11, attributionLogo: true },
    grid: { vertLines: { color: css("--grid") }, horzLines: { color: css("--grid") } },
    rightPriceScale: { borderColor: css("--line") },
    watermark: { visible: true, text: `XAUUSD · ${S.tf}`, color: css("--text") + "0d", fontSize: 44, fontFamily: "Inter, system-ui, sans-serif", fontStyle: "800" },
    timeScale: { borderColor: css("--line"), timeVisible: true, secondsVisible: false, rightOffset: 14, tickMarkFormatter: tickFmt },
    crosshair: { mode: 0, vertLine: { color: css("--dim"), style: 3, labelBackgroundColor: css("--card-2") }, horzLine: { color: css("--dim"), style: 3, labelBackgroundColor: css("--card-2") } },
    localization: { timeFormatter: tf, locale: LOCALE },
    handleScroll: true, handleScale: true,
  };
}
function rebuildCharts() {
  if (C) { C.main.remove(); C.sub.remove(); C = null; }
  if (S.data) renderChart();
}
function buildCharts() {
  const LC = window.LightweightCharts;
  // autoSize: both panes follow their box (CSS sizes it to the viewport), width and height.
  const main = LC.createChart($("#chart"), { ...chartOpts(), autoSize: true, rightPriceScale: { ...chartOpts().rightPriceScale, scaleMargins: { top: 0.12, bottom: 0.08 } } });
  const sub = LC.createChart($("#subchart"), { ...chartOpts(), autoSize: true, watermark: { visible: false }, timeScale: { ...chartOpts().timeScale, visible: false } });
  // Overlays never drive the price scale: a weekly level or a cone far from price used to squeeze
  // the candles into ~40% of the pane. The scale follows the candles (and the plan, below).
  // every line is named: its title shows on the price-axis label (levels already carry named price lines)
  // the price axis is kept for the current price and CDH / CDL / PDH / PDL / POC; lines are named at their end in the chart
  const line = (color, w = 1, style = 0, title = "") => main.addLineSeries({ color, lineWidth: w, lineStyle: style, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false, autoscaleInfoProvider: () => null });
  const candles = main.addCandlestickSeries({ upColor: css("--candle-up"), downColor: css("--candle-dn"), wickUpColor: css("--candle-up"), wickDownColor: css("--candle-dn"), borderVisible: false,
    autoscaleInfoProvider: (orig) => planScale(orig()) });
  const zones = new ZonesPrimitive();
  candles.attachPrimitive(zones);
  const labels = new LabelsPrimitive();
  candles.attachPrimitive(labels);
  const L = {
    // overlay hues (blue / gold / magenta) pass colour-blind separation in both themes; EMA20 and the bands are neutral
    ema20: line(css("--ov-ema20"), 1, 0, "EMA 20"), ema100: line(css("--ov-ema100"), 1, 0, "EMA 100"), ema200: line(css("--ov-ema200"), 2, 0, "EMA 200"),
    vwap: line(css("--ov-vwap"), 2, 0, "VWAP D"), wvwap: line(css("--ov-vwap") + "99", 1, 2, "VWAP W"), mvwap: line(css("--ov-vwap") + "66", 1, 2, "VWAP M"),
    bb_up: line(css("--ov-band") + "aa", 1, 0, "BB upper"), bb_lo: line(css("--ov-band") + "aa", 1, 0, "BB lower"), bb_mid: line(css("--ov-band") + "66", 1, 2, "BB basis"),
    // levels are neutral (their price-line labels name them); line style separates day / week / value area
    pdh: line(css("--muted") + "aa", 1, 1), pdl: line(css("--muted") + "aa", 1, 1), pwh: line(css("--dim") + "aa", 1, 2), pwl: line(css("--dim") + "aa", 1, 2),
    vpoc: line(css("--text") + "88", 1, 3, "POC"), vah: line(css("--muted") + "77", 1, 3, "VAH"), val: line(css("--muted") + "77", 1, 3, "VAL"),
    cone_u: line(css("--dim"), 1, 2, "Cone upper"), cone_l: line(css("--dim"), 1, 2, "Cone lower"),
  };
  const subS = {
    bull: sub.addLineSeries({ color: css("--bull"), lineWidth: 1, priceLineVisible: false, lastValueVisible: true, title: "Long score" }),
    bear: sub.addLineSeries({ color: css("--bear"), lineWidth: 1, priceLineVisible: false, lastValueVisible: true, title: "Short score" }),
    range: sub.addLineSeries({ color: css("--neutral"), lineWidth: 1, priceLineVisible: false, lastValueVisible: true, title: "Range" }),
    tq: sub.addHistogramSeries({ color: css("--accent") + "55", priceScaleId: "tq", priceLineVisible: false, lastValueVisible: false }),
  };
  sub.priceScale("tq").applyOptions({ scaleMargins: { top: 0.6, bottom: 0 }, visible: false });
  let syncing = false;
  main.timeScale().subscribeVisibleLogicalRangeChange((r) => { if (!r || syncing) return; syncing = true; sub.timeScale().setVisibleLogicalRange(r); syncing = false; });
  sub.timeScale().subscribeVisibleLogicalRangeChange((r) => { if (!r || syncing) return; syncing = true; main.timeScale().setVisibleLogicalRange(r); syncing = false; });
  main.subscribeCrosshairMove((prm) => legend(prm));
  C = { main, sub, candles, zones, labels, L, subS, priceLines: [], fitted: false };
}
function series(t, arr, breaks) {
  // `breaks`: bar indices where an anchored series restarts (VWAP resets) -> draw a gap, not a cliff
  const out = [], br = new Set(breaks || []);
  for (let i = 0; i < t.length; i++) {
    if (br.has(i)) out.push({ time: t[i] });
    else if (isNum(arr[i])) out.push({ time: t[i], value: arr[i] });
  }
  return out;
}
function renderChart() {
  const D = S.data; if (!D) return;
  if (!C) buildCharts();
  const ch = D.chart, t = ch.t, T = S.toggles;
  const bars = t.map((x, i) => ({ time: x, open: ch.o[i], high: ch.h[i], low: ch.l[i], close: ch.c[i] })).filter((b) => isNum(b.open));
  if (D.meta.forming && D.meta.forming.t > t[t.length - 1]) {
    const fb = D.meta.forming; bars.push({ time: fb.t, open: fb.o, high: fb.h, low: fb.l, close: fb.c, color: css("--neutral") + "88", wickColor: css("--neutral"), borderColor: css("--neutral") });
  }
  C.candles.setData(bars);
  C.main.applyOptions({ watermark: { text: `XAUUSD · ${S.tf}` } });
  if (bars.length) applyLiveBar(bars[bars.length - 1].time);
  const set = (k, on) => C.L[k].setData(on ? series(t, ch[k], ch.anchor && ch.anchor[k]) : []);
  ["ema20", "ema100", "ema200"].forEach((k) => set(k, T.ema));
  ["vwap", "wvwap", "mvwap"].forEach((k) => set(k, T.vwap));
  ["bb_up", "bb_lo", "bb_mid"].forEach((k) => set(k, T.bb));
  ["pdh", "pdl", "pwh", "pwl", "vpoc", "vah", "val"].forEach((k) => set(k, false));   // drawn as current segments (labels layer)
  // volatility cone into the future
  const cone = D.cone, lastT = t[t.length - 1], lastC = ch.c[ch.c.length - 1];
  if (T.cone && cone && cone.upper && cone.upper.length) {
    const up = [{ time: lastT, value: lastC }], lo = [{ time: lastT, value: lastC }];
    cone.upper.forEach((v, k) => { up.push({ time: lastT + (k + 1) * D.meta.tf_sec, value: v }); lo.push({ time: lastT + (k + 1) * D.meta.tf_sec, value: cone.lower[k] }); });
    C.L.cone_u.setData(up); C.L.cone_l.setData(lo);
  } else { C.L.cone_u.setData([]); C.L.cone_l.setData([]); }
  // zones
  const z = [];
  if (T.zones) for (const zz of D.zones) {
    const col = zz.type === "OB" ? css("--ob") : css("--fvg");
    z.push({ t0: zz.t0, t1: zz.t1, hi: zz.hi, lo: zz.lo, fill: col + (zz.t1 ? "14" : "26"), stroke: col + (zz.t1 ? "55" : "aa"),
      label: `${zz.type}${zz.dir > 0 ? "▲" : "▼"}${zz.failed ? " (failed disp.)" : ""}` });
  }
  C.zones.set(z);
  // markers. Vetoes and sweeps are frequent (dozens a day on 15m), so they are drawn as dots without
  // text, which piled up into unreadable "veto EV" stacks; the hovered bar's labels go in the legend.
  const mk = [], tags = new Map(), ev = [];
  const tag = (t, s) => tags.set(t, (tags.get(t) || []).concat(s));
  for (const m of D.markers) {
    if (m.type === "SIGNAL" && T.signals) { mk.push({ time: m.t, position: m.dir > 0 ? "belowBar" : "aboveBar", color: m.dir > 0 ? css("--bull") : css("--bear"), shape: m.dir > 0 ? "arrowUp" : "arrowDown" });
      ev.push({ t: m.t, dir: m.dir, text: `${m.dir > 0 ? "BUY" : "SELL"} · TQ ${m.tq}`, color: m.dir > 0 ? css("--candle-up") : css("--candle-dn"), solid: true }); }
    else if (m.type === "VETO" && T.signals) { mk.push({ time: m.t, position: m.dir > 0 ? "belowBar" : "aboveBar", color: css("--warn"), shape: "circle", size: 0.5 }); tag(m.t, `veto ${m.dir > 0 ? "▲" : "▼"} ${m.why}`); }
    else if (m.type === "TRACK_EXIT" && T.signals) mk.push({ time: m.t, position: "inBar", color: (m.r || 0) >= 0 ? css("--bull") : css("--bear"), shape: "square", text: `${fs(m.r, 1)}R` });
    else if ((m.type === "BOS" || m.type === "CHoCH" || m.type === "MSS") && T.structure) { mk.push({ time: m.t, position: m.dir > 0 ? "belowBar" : "aboveBar", color: m.dir > 0 ? css("--bull") + "cc" : css("--bear") + "cc", shape: "circle", size: 0.5 });
      ev.push({ t: m.t, dir: m.dir, text: `${m.type} ${m.dir > 0 ? "▲" : "▼"}`, color: m.dir > 0 ? css("--bull") : css("--bear") }); }
    else if (m.type === "SWEEP" && T.sweeps) { mk.push({ time: m.t, position: m.dir > 0 ? "belowBar" : "aboveBar", color: "#e040fb", shape: "circle", size: 0.4 }); tag(m.t, `sweep ${m.dir > 0 ? "▲" : "▼"}`);
      ev.push({ t: m.t, dir: m.dir, text: m.dir > 0 ? "Sweep SSL" : "Sweep BSL", color: "#d55181" }); }
  }
  mk.sort((a, b) => a.time - b.time);
  if (T.h2 && D.h2 && Array.isArray(D.h2.signals)) {                     // arm H2 (toggle on by default)
    const t0 = D.chart.t[0];
    D.h2.signals.filter((g) => g.t >= t0).forEach((g) => { mk.push({ time: g.t, position: g.dir === "LONG" ? "belowBar" : "aboveBar", color: "#b084ff",
      shape: g.dir === "LONG" ? "arrowUp" : "arrowDown" }); ev.push({ t: g.t, dir: g.dir === "LONG" ? 1 : -1, text: `H2 ${g.dir === "LONG" ? "BUY" : "SELL"}`, color: "#9b6dff", solid: true }); });
    mk.sort((a, b) => a.time - b.time);
  }
  if (T.h3 && D.h3 && Array.isArray(D.h3.signals)) {                     // arm H3 (Amendment 7)
    const t0 = D.chart.t[0];
    D.h3.signals.filter((g) => g.t >= t0).forEach((g) => { mk.push({ time: g.t, position: g.dir === "LONG" ? "belowBar" : "aboveBar", color: "#26c6da",
      shape: g.dir === "LONG" ? "arrowUp" : "arrowDown" }); ev.push({ t: g.t, dir: g.dir === "LONG" ? 1 : -1, text: `H3 ${g.dir === "LONG" ? "BUY" : "SELL"}`, color: "#0f9fb3", solid: true }); });
    mk.sort((a, b) => a.time - b.time);
  }
  C.candles.setMarkers(mk);
  C.tags = tags;
  // ---- levels: drawn from where they formed to the current candle, named at that end ----
  C.priceLines.forEach((p) => C.candles.removePriceLine(p)); C.priceLines = [];
  const d = D.dashboard, n = t.length, curT = bars.length ? bars[bars.length - 1].time : t[n - 1];   // the current candle
  const since = (arr, v) => { if (!arr || !isNum(v)) return t[Math.max(0, n - 24)]; let k = n - 1; while (k > 0 && isNum(arr[k - 1]) && Math.abs(arr[k - 1] - v) < 0.005) k--; return t[k]; };
  const dayStart = since(ch.pdh, ch.pdh[n - 1]);
  const segs = [], seen = [];
  const seg = (price, t0, label, color, dash = 0, w = 1, solid = false) => {
    if (!isNum(price) || seen.some((x) => Math.abs(x - price) < 0.005)) return;
    seen.push(price); segs.push({ price, t0, label: `${label} ${px(price)}`, color, dash, w, solid });
  };
  if (T.plan) {
    const p = d.plan, p0 = t[Math.max(0, n - 10)];
    seg(p.sl, p0, `SL · ${p.sl_basis}`, css("--bear"), 0, 1.5, true);
    seg(p.tp1, p0, `TP1 · ${p.tp_basis[0]}`, css("--bull"), 0, 1.5, true); seg(p.tp2, p0, `TP2 · ${p.tp_basis[1]}`, css("--bull"), 2); seg(p.tp3, p0, `TP3 · ${p.tp_basis[2]}`, css("--bull"), 2);
  }
  const lq = d.liquidity || {}, P = lq.pools || {};
  if (T.levels) {
    const cdIdx = (v, hi) => { for (let k = n - 1; k >= 0 && t[k] >= dayStart; k--) if (isNum(v) && Math.abs((hi ? ch.h[k] : ch.l[k]) - v) < 0.02) return t[k]; return dayStart; };
    seg(lq.cdh, cdIdx(lq.cdh, true), "CDH", "#4dd0e1", 2); seg(lq.cdl, cdIdx(lq.cdl, false), "CDL", "#4dd0e1", 2);
    seg(P.PDH, since(ch.pdh, P.PDH), "PDH", "#f0b04a", 2); seg(P.PDL, since(ch.pdl, P.PDL), "PDL", "#f0b04a", 2);
    seg(P.PWH, since(ch.pwh, P.PWH), "PWH", "#b98cff", 2); seg(P.PWL, since(ch.pwl, P.PWL), "PWL", "#b98cff", 2);
    const mon = (x) => new Date((x + 7 * 3600) * 1000).toLocaleDateString("en-CA", { timeZone: "America/New_York" }).slice(0, 7);
    let mk0 = n - 1; while (mk0 > 0 && mon(t[mk0 - 1]) === mon(t[n - 1])) mk0--;
    seg(P.PMH, t[mk0], "PMH", "#9aa5b1", 1); seg(P.PML, t[mk0], "PML", "#9aa5b1", 1);
    seg(P.EQH, dayStart, "EQH", css("--bear"), 1); seg(P.EQL, dayStart, "EQL", css("--bull"), 1);
  }
  const fl = d.flow || {};
  if (T.vp) {
    const v0 = t[Math.max(0, n - 100)];                               // the 100-bar profile window
    seg(fl.vpoc, v0, "POC", css("--text"), 1, 1.5); seg(fl.vah, v0, "VAH", css("--muted"), 1); seg(fl.val, v0, "VAL", css("--muted"), 1);
  }
  if (T.sr && D.sr) {
    const s0 = t[Math.max(0, n - 40)];
    D.sr.res.forEach((r, k) => seg(r.price, s0, `R${k + 1} ×${r.touches}`, css("--bear") + (r.touches >= 3 ? "" : "99"), 1));
    D.sr.sup.forEach((r, k) => seg(r.price, s0, `S${k + 1} ×${r.touches}`, css("--bull") + (r.touches >= 3 ? "" : "99"), 1));
  }
  // overlay lines named at their last point
  const ends = [];
  const NAME = { ema20: ["EMA 20", "--ov-ema20"], ema100: ["EMA 100", "--ov-ema100"], ema200: ["EMA 200", "--ov-ema200"], vwap: ["VWAP D", "--ov-vwap"],
    wvwap: ["VWAP W", "--ov-vwap"], mvwap: ["VWAP M", "--ov-vwap"], bb_up: ["BB upper", "--ov-band"], bb_lo: ["BB lower", "--ov-band"] };
  for (const [tg, keys] of [["ema", ["ema20", "ema100", "ema200"]], ["vwap", ["vwap", "wvwap", "mvwap"]], ["bb", ["bb_up", "bb_lo"]]]) {
    if (T[tg]) for (const k of keys) if (isNum(ch[k][n - 1])) ends.push({ price: ch[k][n - 1], label: NAME[k][0], color: css(NAME[k][1]) });
  }
  const hl = new Map(); for (let k = 0; k < n; k++) hl.set(t[k], [ch.h[k], ch.l[k]]);
  ev.sort((a, b) => a.t - b.t);
  const tfS = D.meta.tf_sec, lastSw = {};
  const evs = ev.filter((e) => {
    if (!/^Sweep/.test(e.text)) return true;
    const k = e.dir, keep = !(lastSw[k] && e.t - lastSw[k] <= 6 * tfS);
    lastSw[k] = e.t; return keep;                                       // the rest of a sweep cluster keeps its dot
  });
  C.labels.set({ segs, ends, events: evs, hl, lastT: curT, bg: css("--card") });
  // the price axis: current price (the candle series) and only CDH / CDL / PDH / PDL / POC
  const ax = (price, color, title) => { if (isNum(price)) C.priceLines.push(C.candles.createPriceLine({ price, color, lineVisible: false, axisLabelVisible: true, title })); };
  ax(lq.cdh, "#4dd0e1", "CDH"); ax(lq.cdl, "#4dd0e1", "CDL"); ax(P.PDH, "#f0b04a", "PDH"); ax(P.PDL, "#f0b04a", "PDL"); ax(fl.vpoc, css("--muted"), "POC");
  // sub pane
  C.subS.bull.setData(series(t, ch.bull)); C.subS.bear.setData(series(t, ch.bear)); C.subS.range.setData(series(t, ch.range));
  C.subS.tq.setData(series(t, ch.tq));
  C.nBars = bars.length;
  if (!C.fitted || C.fittedTf !== S.tf) { fitView(); C.fitted = true; C.fittedTf = S.tf; }
  legend(null);
}
// Keep the plan's SL and TP1 on screen when they are near price; a level further than a quarter of
// the candles' own range away is left off so it cannot squeeze the candles again (its axis label
// and the decision card still give the price).
function planScale(info) {
  const D = S.data;
  if (!info || !D || !S.toggles.plan) return info;
  const r = info.priceRange, span = r.maxValue - r.minValue, p = D.dashboard && D.dashboard.plan;
  if (!p || !(span > 0)) return info;
  let lo = r.minValue, hi = r.maxValue;
  for (const v of [p.sl, p.tp1]) if (isNum(v) && v > r.minValue - span / 4 && v < r.maxValue + span / 4) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
  return { ...info, priceRange: { minValue: lo, maxValue: hi } };
}
// Fit to screen: about 6 px per bar (TradingView's default spacing), so a phone shows ~50 bars and
// a wide screen up to 200, with room on the right for the volatility cone; price auto-scale back on.
function fitView() {
  if (!C || !C.nBars) return;
  const D = S.data, n = C.nBars, w = C.main.timeScale().width() || $("#chart").clientWidth;
  const show = Math.max(40, Math.min(200, Math.round(w / 6)));
  const pad = Math.max(S.toggles.cone && D && D.cone && D.cone.upper ? D.cone.upper.length + 2 : 0, 26);   // room for the end tags
  C.main.priceScale("right").applyOptions({ autoScale: true });
  C.main.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - show), to: n - 1 + pad });
}
// The chart key: every visible line by name, with its colour, style and value at the hovered bar.
const KEY = [["ema", [["ema20", "EMA 20", "--ov-ema20", "solid"], ["ema100", "EMA 100", "--ov-ema100", "solid"], ["ema200", "EMA 200", "--ov-ema200", "thick"]]],
  ["vwap", [["vwap", "VWAP D", "--ov-vwap", "thick"], ["wvwap", "VWAP W", "--ov-vwap", "dash"], ["mvwap", "VWAP M", "--ov-vwap", "dash"]]],
  ["bb", [["bb_up", "BB upper", "--ov-band", "solid"], ["bb_mid", "BB basis", "--ov-band", "dash"], ["bb_lo", "BB lower", "--ov-band", "solid"]]],
  ["levels", [["pdh", "PDH", "--muted", "dot"], ["pdl", "PDL", "--muted", "dot"], ["pwh", "PWH", "--dim", "dash"], ["pwl", "PWL", "--dim", "dash"]]],
  ["vp", [["vpoc", "POC", "--text", "dot"], ["vah", "VAH", "--muted", "dot"], ["val", "VAL", "--muted", "dot"]]]];
function legend(prm) {
  const D = S.data; if (!D) return;
  const ch = D.chart;
  let i = ch.t.length - 1;
  if (prm && prm.time) { const k = ch.t.indexOf(prm.time); if (k >= 0) i = k; }
  const col = ch.c[i] >= ch.o[i] ? "bull" : "bear";
  const chg = i > 0 && isNum(ch.c[i]) && isNum(ch.c[i - 1]) ? ch.c[i] - ch.c[i - 1] : null;
  const keys = KEY.filter(([t]) => S.toggles[t]).flatMap(([, ls]) => ls).filter(([k]) => ch[k] && isNum(ch[k][i]))
    .map(([k, name, v, st]) => `<span class="lk"><i class="sw ${st}" style="--c:${css(v)}"></i>${name} <b>${f(ch[k][i])}</b></span>`).join("");
  const tags = C && C.tags && C.tags.get(ch.t[i]);
  const ohlc = [["O", ch.o[i]], ["H", ch.h[i]], ["L", ch.l[i]], ["C", ch.c[i]]].map(([k, v]) => `<span class="q"><i>${k}</i><b class="${col}">${f(v)}</b></span>`).join("");
  const score = (k, v, cls) => `<span class="sc"><i>${k}</i><b class="${cls}">${f(v, 0)}</b></span>`;
  $("#legend").innerHTML =
    `<div class="lrow head"><span class="sym">XAUUSD</span><span class="tfb">${esc(D.meta.tf)}</span><span class="tm">${tfmt(ch.t[i])}</span>${ohlc}` +
    (isNum(chg) ? `<span class="chg ${chg >= 0 ? "up" : "dn"}">${chg >= 0 ? "▲ +" : "▼ "}${chg.toFixed(2)} (${(chg / ch.c[i - 1] * 100).toFixed(2)}%)</span>` : "") + `</div>` +
    `<div class="lrow">${score("Long", ch.bull[i], "bull")}${score("Range", ch.range[i], "")}${score("Short", ch.bear[i], "bear")}${score("TQ", ch.tq[i], "")}` +
    (ch.session[i] ? `<span class="tag">${esc(ch.session[i])}</span>` : "") + (tags ? `<span class="tag warn">${esc(tags.join(" · "))}</span>` : "") + `</div>` +
    (keys ? `<div class="lrow keys">${keys}</div>` : "");
}

/* ---------- tabs ---------- */
function renderOverview() {
  const D = S.data, d = D.dashboard, M = D.meta;
  const reg = d.regime, se = d.session, mtf = d.mtf, mac = d.macro, au = d.auction, fl = d.flow, li = d.liquidity;
  const html = [
    card("Bias composite", kv([["Bull / Range / Bear", `<span class="bull">${f(d.bull_score, 0)}</span> / ${f(d.range_score, 0)} / <span class="bear">${f(d.bear_score, 0)}</span>`],
      ["Pre-history score", `${f(d.bull_pre, 0)} bull`], ["Bias label", esc(d.bias_label)], ["Regime call", `${esc(d.bias_call)} (L${f(d.bull_bias, 0)} S${f(d.bear_bias, 0)} R${f(d.range_bias, 0)})`],
      ["Signal agreement", `▲${d.signals.bull} / ▼${d.signals.bear}${d.signals.conflict ? ' <span class="warn">CONFLICT</span>' : ""}`],
      ["Forecast adj.", fs(d.f_adj, 2)]])),
    card("Regime", kv([["Regime", `${esc(reg.label)} ${esc(reg.vol_tag)}`], ["Composite", `${reg.composite}/100 (${reg.strong ? "strong" : reg.moderate ? "moderate" : "weak"})`],
      ["ATR percentile", pct(reg.atr_pct)], ["SL multiple", f(reg.sl_mult, 2) + " × ATR"], ["Confidence cap", reg.conf_cap],
      ["Persistence", `T${reg.transitions.T} R${reg.transitions.R} D${reg.transitions.D}`]])),
    card("Session", kv([["Session", `${esc(se.label)} · quality ${se.quality}/100`], ["Spread model", f(se.spread, 2) + " pts"], ["Range vs avg", pct(se.exp_pct)],
      ["Manipulation / continuation", `${pct(se.manip_prob)} / ${pct(se.cont_prob)}`], ["Opening type", esc(se.open_type || "—")], ["Conf. multiplier", f(se.conf_mult, 2)]])),
    card("Multi-timeframe", kv([["Agreement", `${esc(mtf.tier)} (${mtf.conf_score})`], ["Align long / short", `${mtf.align_long} / ${mtf.align_short}`],
      ...Object.entries(mtf.scores).filter(([k]) => ({ 5: 300, 15: 900, 60: 3600, 240: 14400, D: 86400 }[k] || 0) > M.tf_sec)
        .map(([k, v]) => [`HTF ${k === "60" ? "1h" : k === "240" ? "4h" : k === "D" ? "1D" : k + "m"}`, `<span class="${v >= 60 ? "bull" : v <= 40 ? "bear" : ""}" title="0-100: price vs EMA200 (40) + EMA20 vs EMA100 (40) + price vs EMA20 (20)">${f(v, 0)}</span>`])])),
    card("Macro", kv([["Macro", `${esc(mac.label)} (${fs(mac.strength, 0)})`], ["Votes bull / bear", `${mac.bull_votes} / ${mac.bear_votes}`], ["Confidence", mac.conf],
      ["DXY / US10Y", `${arrow(D.macro.DXY)} / ${arrow(D.macro.US10Y)}`], ["EUR / XAG / SPX / TIPS", `${arrow(D.macro.EURUSD)} ${arrow(D.macro.XAG)} ${arrow(D.macro.SPX)} ${arrow(D.macro.TIPS)}`],
      ["VIX", f(D.macro.vix, 1)]])),
    card("Auction", kv([["State", `${esc(au.state)} ${au.prob}% ${esc(au.cycle)}`], ["Bias", esc(au.bias)], ["Discovery", esc(au.disc)], ["Acceptance", `${au.accept} ${esc(au.accept_grade)}`],
      ["Value migration", esc(au.value_mig)], ["Last sweep", au.sweep_q ? `${esc(au.sweep_grade)} ${au.sweep_q}` : "—"]])),
    card("Volume (proxy, not order flow)", kv([["Bar-signed volume", fl.cvd_bull ? '<span class="bull">bull</span>' : '<span class="bear">bear</span>'], ["Volume delta (50)", f(fl.vd_k, 1) + "k"],
      ["Value area", `${esc(fl.va_pos)} POC ${f(fl.vpoc)} (${f(fl.va_ratio, 0)}%)`], ["Rel. volume", f(fl.rel_vol, 2) + "×"], ["Volume pct", pct(fl.vol_pct)],
      ["Climax", fl.climax_up ? '<span class="bull">up</span>' : fl.climax_dn ? '<span class="bear">down</span>' : "—"]]) +
      `<p class="note">${esc(M.volume_source || "")}. Volume is signed by the bar's direction (close vs open); this is a proxy, not true CVD: no trade-by-trade aggressor data is used.</p>`),
    card("Liquidity target", kv([["Destination", `${esc(li.dest)} ${li.dest_score} ${esc(li.dest_conf)}`], ["Reach score", f(li.reach, 0) + "/100"], ["Health", li.health + "/100"],
      ["PDH / PDL reach", `${f(li.reach_scores.PDH, 0)} / ${f(li.reach_scores.PDL, 0)}`], ["Sweep", li.sweep_bull ? "bull sweep" : li.sweep_bear ? "bear sweep" : "—"]])),
  ];
  $("#tab-overview").innerHTML = html.join("");
}
function arrow(m) {
  if (!m || !m.valid) return '<span class="dim">—</span>';
  return m.gold_bullish ? '<span class="bull">▲</span>' : m.gold_bearish ? '<span class="bear">▼</span>' : "≈";
}
function renderMacro() {
  const D = S.data, m = D.macro;
  const rows = [["DXY", m.DXY, "inverse"], ["US10Y", m.US10Y, "inverse"], ["TIPS" + (m.tips_source === "us10y" ? " (=US10Y, Pine default)" : ""), m.TIPS, "inverse"],
    ["EURUSD", m.EURUSD, "direct"], ["XAG", m.XAG, "direct"], ["SPX", m.SPX, "direct"]];
  const t = `<div class="scroll"><table class="t"><tr><th>Asset</th><th>Value</th><th>EMA10/20</th><th>For gold</th><th>ρ30</th><th>ρ60</th><th>ρ120</th><th>Health</th></tr>` +
    rows.map(([n, r, rel]) => `<tr><td>${n} <span class="dim">${rel}</span></td><td>${r.valid ? f(r.value, 3) : '<span class="dim">n/a</span>'}</td><td>${f(r.ema10, 3)} / ${f(r.ema20, 3)}</td><td>${arrow(r)}</td>` +
      r.corr.map((x) => `<td class="${x > 0 ? "bull" : x < 0 ? "bear" : ""}">${f(x, 2)}</td>`).join("") + `<td>${f(r.health, 0)}</td></tr>`).join("") + `</table></div>` +
    `<p class="note">Correlations of chart-bar returns; the significance band is the Bonferroni-corrected t critical value (|ρ| ≥ ${Object.values(m.corr_sig).map((x) => f(x, 2)).join(" / ")} for 30/60/120). Health 50 = no evidence either way.</p>`;
  $("#tab-macro").innerHTML = card("Cross-asset drivers", t) +
    card("Rates, volatility, positioning", kv([["2s10s curve", `${f(m.curve_2s10s, 2)} ${m.curve_steepening ? "steepening" : "flattening"}`], ["VIX (prior close)", f(m.vix, 2)],
      ["CFTC COT percentile", m.cot.valid ? `${f(m.cot.pct, 0)} ${m.cot.crowded_long ? '<span class="warn">LONG-CROWDED</span>' : m.cot.crowded_short ? '<span class="warn">SHORT-CROWDED</span>' : ""}` : "—"],
      ["COT gates entries", m.cot.gating ? "yes" : "no (Pine default off; display only)"],
      ["Open interest", m.oi.valid ? `${esc(m.oi.state)} ${fs(m.oi.chg_pct, 2)}%` : "—"],
      ["Gold futures (GC)", m.gc.enabled ? (m.gc.valid ? (m.gc.diverges ? "diverges" : m.gc.strong_bull ? "++" : m.gc.strong_bear ? "--" : m.gc.confirms_bull ? "+" : m.gc.confirms_bear ? "−" : "~") : "invalid " + esc(m.gc.fail)) : "off"],
      ["Data status", esc(m.status_line)], ["Avg corr health / stability", `${f(m.avg_corr_health, 0)} / ${f(m.avg_stability, 2)}`]]) +
      `<p class="note">${esc(m.oi.note)}. COT is aligned on its public release (Friday 15:30 New York), so no backtest bar sees a report before it was published.</p>`);
}
function renderLiquidity() {
  const D = S.data, d = D.dashboard, li = d.liquidity, st = d.struct, z = d.zones, c = d.close, atr = d.aatr;
  const pools = Object.entries(li.pools).map(([k, v]) => `<tr><td>${k}</td><td>${f(v)}</td><td>${isNum(v) ? f((v - c) / atr, 2) : "—"}</td><td>${f(li.scores[k], 0)}</td></tr>`).join("");
  $("#tab-liquidity").innerHTML =
    card("Liquidity pools", `<table class="t"><tr><th>Pool</th><th>Price</th><th>Dist (ATR)</th><th>Score</th></tr>${pools}
      <tr><td>CDH / CDL</td><td colspan="3">${f(li.cdh)} / ${f(li.cdl)}</td></tr></table>`) +
    card("Market structure", kv([["Active", esc(structStr(st))], ["Struct score", f(st.struct_score, 0)], ["BOS label", st.bos_label_bull ? "▲" : st.bos_label_bear ? "▼" : "—"],
      ["CHoCH / MSS", `${st.choch_bull ? "CHoCH▲ " : ""}${st.choch_bear ? "CHoCH▼ " : ""}${st.mss_bull ? "MSS▲ " : ""}${st.mss_bear ? "MSS▼" : ""}` || "—"],
      ["Displacement", st.disp_up ? '<span class="bull">up</span>' : st.disp_dn ? '<span class="bear">down</span>' : "—"],
      ["Internal res / sup", `${f(st.active_res)} / ${f(st.active_sup)}`], ["Swing res / sup", `${f(st.swing_res)} / ${f(st.swing_sup)}`]])) +
    card("Zones", kv([["Bull OB", z.ob_bull ? `${f(z.ob_bull[0])} – ${f(z.ob_bull[1])} (mit ${f(z.ob_bull_mit, 0)}%)` : "—"],
      ["Bear OB", z.ob_bear ? `${f(z.ob_bear[0])} – ${f(z.ob_bear[1])} (mit ${f(z.ob_bear_mit, 0)}%)` : "—"],
      ["FVG", z.fvg ? `${f(z.fvg[0])} – ${f(z.fvg[1])} ${z.fvg[2] ? "▲" : "▼"}` : "—"], ["EQH / EQL", `${f(z.eqh)} / ${f(z.eql)}`]]) +
      `<p class="note">These zones FEED the decision (F-A30: detection is on by default), and they are the same definitions the chart draws.</p>`) +
    card("Support / resistance scanner", `<table class="t"><tr><th>Side</th><th>Price</th><th>Touches</th></tr>${[...D.sr.res.map((r) => ["R", r]), ...D.sr.sup.map((r) => ["S", r])].map(([s, r]) => `<tr><td class="${s === "R" ? "bear" : "bull"}">${s}</td><td>${f(r.price)}</td><td>${r.touches}</td></tr>`).join("")}</table>`) +
    card("What-if scenarios", kv(Object.entries(d.what_if).map(([k, v]) => [k.replace("_", " "), isNum(v) ? f(v, 0) + "/100" : "n/a"])) + `<p class="note">Heuristic scores clamped 10–90, not probabilities.</p>`);
}
function renderAnalog() {
  const A = S.data.analog, d = S.data.dashboard;
  const rel = `<table class="t"><tr><th>Bin</th><th>n</th><th>Predicted</th><th>Observed</th><th>|Err|</th></tr>${A.reliability.map((r) => `<tr><td>B${r.bin}</td><td>${f(r.n, 0)}</td><td>${f(r.pred, 1)}</td><td>${f(r.obs, 1)}</td><td>${isNum(r.pred) && isNum(r.obs) ? f(Math.abs(r.pred - r.obs), 1) : "N<30"}</td></tr>`).join("")}</table>`;
  const rp = A.race_prob || [];
  const race = rp.length && isNum(rp[0]) ? `<table class="t"><tr><th></th><th>1R</th><th>2R</th><th>3R</th></tr>
    <tr><td>Long TP first</td><td>${f(rp[0], 0)}%</td><td>${f(rp[1], 0)}%</td><td>${f(rp[2], 0)}%</td></tr>
    <tr><td>Long SL first</td><td>${f(rp[3], 0)}%</td><td>${f(rp[4], 0)}%</td><td>${f(rp[5], 0)}%</td></tr>
    <tr><td>Short TP first</td><td>${f(rp[6], 0)}%</td><td>${f(rp[7], 0)}%</td><td>${f(rp[8], 0)}%</td></tr>
    <tr><td>Short SL first</td><td>${f(rp[9], 0)}%</td><td>${f(rp[10], 0)}%</td><td>${f(rp[11], 0)}%</td></tr>
    <tr><td>Timeout MTM long (R)</td><td>${f(rp[12], 2)}</td><td>${f(rp[13], 2)}</td><td>${f(rp[14], 2)}</td></tr></table><p class="note">n = ${f(A.race_n, 0)} ROLL analogs. Stop assumed first on a same-bar tie.</p>` : "<p class='muted'>Needs ≥ 20 ROLL analogs.</p>";
  const hp = A.hit_prob || [];
  const hit = hp.length && isNum(hp[0]) ? kv([["Long MFE ≥1/2/3R", `${f(hp[0], 0)} / ${f(hp[1], 0)} / ${f(hp[2], 0)}%`], ["Long MAE ≥1R", f(hp[3], 0) + "%"],
    ["Short MFE ≥1/2/3R", `${f(hp[4], 0)} / ${f(hp[5], 0)} / ${f(hp[6], 0)}%`], ["n", f(A.hit_n, 0)]]) : "<p class='muted'>Needs ≥ 20 ROLL analogs.</p>";
  const sc = A.scan || {};
  $("#tab-analog").innerHTML =
    card("Analog engine", kv([["Buffer / matched", `${sc.hN || 0} / ${A.match}`], ["Similarity threshold", sc.sim_thresh], ["Bull / bear / range", `${f(A.bull, 0)} / ${f(A.bear, 0)} / ${f(A.range, 0)}`],
      ["Weighted win rate", pctN(A.wr, A.match)], ["Avg win / loss (R)", A.match > 0 ? `${f(A.avg_w, 2)} / ${f(A.avg_l, 2)}` : "—"], ["Expectancy", A.match > 0 ? fs(A.ev, 2) + " R" : "—"],
      ["Profit factor", f(A.profit_factor, 2)], ["Avg MAE", f(A.max_adverse_atr, 2) + " ATR"], ["Notional max DD", f(A.max_dd, 1) + "%"],
      ["BOS continuation / fail", `${f(A.bos_cont, 0)} / ${f(A.bos_fail, 0)}%`], ["PDH-first / PDL-first", `${A.pdh1st ?? "—"} / ${A.pdl1st ?? "—"}%`], ["Regime persistence", pct(A.reg_per)]]) +
      `<p class="note">Each confirmed bar is compared with up to ${S.data.meta.hist_max} past states on 10 weighted features; every count is a count of distinct analogs.</p>`) +
    card("Calibration (ROLL bins)", rel + kv([["Grade", `${esc(A.cal_grade)} ${A.cal_grade_pct}/100`], ["Brier (bin means)", f(A.cal_brier, 3)], ["Base rate", pct(A.base_rate)],
      ["Platt fit bull k / b", d.cal_fit ? `${f(d.cal_fit[0], 3)} / ${f(d.cal_fit[1], 3)}` : "—"], ["Platt fit bear k / b", d.cal_fit_bear ? `${f(d.cal_fit_bear[0], 3)} / ${f(d.cal_fit_bear[1], 3)}` : "—"],
      ["Quantile edges", (A.cal_q || []).map((x) => f(x, 0)).join(" / ")]])) +
    card("TP-before-SL race", race) + card("Excursion touch rates", hit) +
    card("Feature direction accuracy", kv([["Trend", fs(A.feat_str, 1)], ["HTF", fs(A.feat_htf, 1)], ["Liquidity", fs(A.feat_liq, 1)], ["Mean reversion", fs(A.feat_mr, 1)], ["Correlation", fs(A.feat_cor, 1)]]) +
      `<p class="note">Pine's definition, kept: percentage points above 50%, with timed-out analogs in the denominator. A feature with no edge therefore reads about −(timeout share ÷ 2), not 0 — compare features with each other, not with zero.</p>`) +
    card("Similarity weights", kv(Object.entries(sc.weights || {}).map(([k, v]) => [k, f(v, 1) + "%"]).concat([["zone (fixed)", "8.0%"]])));
}
function mRow(label, a, b, fmt = (x) => f(x, 2), c = undefined) {
  const cell = (m) => `<td>${m && m.n ? fmt(m) : "—"}</td>`;
  return `<tr><td>${label}</td>${cell(a)}${cell(b)}${c === undefined ? "" : cell(c)}</tr>`;
}
let EQ = null;
function renderBacktest() {
  const B = S.data.backtest, H = S.data.holdout;
  if (!B || !B.treatment) { $("#tab-backtest").innerHTML = card("Backtest", "<p class='muted'>No backtest yet.</p>"); return; }
  const tr = B.treatment, ct = B.control || {}, ch = B.challenger || {};
  const rows = (x, y, z) => { const R = (lab, fmt) => mRow(lab, x, y, fmt, z); return `<table class="t"><tr><th>Metric</th><th>Treatment (live gate)</th><th>Control (old gates)</th><th>Challenger (H1)</th></tr>
    <tr><td>Trades</td><td>${x ? x.n : 0}</td><td>${y ? y.n : 0}</td><td>${z ? z.n : 0}</td></tr>${R("Win rate", (m) => pct(m.win_rate, 1))}${R("Expectancy (R/trade)", (m) => fs(m.expectancy_r, 3))}
    ${R("t-stat of mean R", (m) => f(m.t_stat, 2))}${R("Profit factor", (m) => f(m.profit_factor, 2))}${R("Net points ($/oz)", (m) => fs(m.net_pts, 1))}
    ${R("Sum R", (m) => fs(m.sum_r, 2))}${R("Max DD (1% risk)", (m) => pct(m.max_dd_pct, 1))}${R("Max DD (R)", (m) => f(m.max_dd_r, 2))}
    ${R("Final equity (1% risk)", (m) => fs(m.final_equity_pct, 1) + "%")}${R("Sharpe / Sortino per trade", (m) => `${f(m.sharpe_per_trade, 2)} / ${f(m.sortino_per_trade, 2)}`)}
    ${R("TP1 hit rate", (m) => pct(m.tp1_rate, 0))}${R("Longest losing streak", (m) => m.longest_losing_streak)}${R("Longs / shorts", (m) => `${m.longs} / ${m.shorts}`)}
    ${R("Avg bars held", (m) => f(m.avg_bars, 1))}</table>`; };
  const anyPost = [tr, ct, ch].some((a) => a.holdout && a.holdout.n);
  const hold = anyPost ? rows(tr.holdout, ct.holdout, ch.holdout) : `<p class="muted">${H.status === "PENDING" ? "The forward test starts" : "No trade has been entered since the freeze"} (${H.freeze_utc ? H.freeze_utc.slice(0, 16).replace("T", " ") : "—"} UTC). This is the only evidence that is genuinely out of sample; it fills with time. Pre-registered in audit/PREREGISTRATION.md §7: 1H decides; three arms; N ≥ 50.</p>`;
  const wf = (tr.walk_forward || []).map((w, k) => `<tr><td>F${k + 1} ${w.from.slice(0, 10)}</td><td>${w.n}</td><td>${w.n ? pct(w.win_rate, 0) : "—"}</td><td>${w.n ? fs(w.expectancy_r, 3) : "—"}</td><td>${w.n ? f(w.profit_factor, 2) : "—"}</td></tr>`).join("");
  const mc = tr.monte_carlo && tr.monte_carlo.runs ? kv([["Runs × trades", `${tr.monte_carlo.runs} × ${tr.monte_carlo.trades}`], ["Final equity p5 / p50 / p95", `${fs(tr.monte_carlo.final_equity_pct.p5, 1)} / ${fs(tr.monte_carlo.final_equity_pct.p50, 1)} / ${fs(tr.monte_carlo.final_equity_pct.p95, 1)}%`],
    ["Max DD p5 / p50 / p95", `${f(tr.monte_carlo.max_dd_pct.p5, 1)} / ${f(tr.monte_carlo.max_dd_pct.p50, 1)} / ${f(tr.monte_carlo.max_dd_pct.p95, 1)}%`], ["P(loss)", pct(tr.monte_carlo.prob_loss, 1)]]) + `<p class="note">${esc(tr.monte_carlo.note)}</p>` : "<p class='muted'>Needs ≥ 5 closed trades.</p>";
  const cal = tr.calibration && tr.calibration.bins ? `<table class="t"><tr><th>P at entry</th><th>n</th><th>Predicted</th><th>TP1 hit</th></tr>${tr.calibration.bins.map((b) => `<tr><td>${f(b.lo, 1)}–${f(b.hi, 1)}</td><td>${b.n}</td><td>${f(b.pred, 0)}%</td><td>${f(b.obs, 0)}%</td></tr>`).join("")}</table>${kv([["Brier", f(tr.calibration.brier, 3)], ["Base rate", pct(tr.calibration.base_rate, 0)]])}` : `<p class="muted">Needs ≥ 10 trades with a calibrated P (n=${tr.calibration ? tr.calibration.n : 0}).</p>`;
  const brk = (o) => `<table class="t"><tr><th></th><th>n</th><th>Win</th><th>E[R]</th></tr>${Object.entries(o || {}).map(([k, m]) => `<tr><td>${esc(k)}</td><td>${m.n}</td><td>${m.n ? pct(m.win_rate, 0) : "—"}</td><td>${m.n ? fs(m.expectancy_r, 2) : "—"}</td></tr>`).join("")}</table>`;
  const arm = S.btArm === "control" ? ct : S.btArm === "challenger" ? ch : tr;
  const trades = (arm.trades || []).slice().reverse().map((x) => `<tr><td>${tfmt(Date.parse(x.entry_time) / 1000)}</td><td class="${x.dir === "LONG" ? "bull" : "bear"}">${x.dir}</td><td>${f(x.entry)}</td><td>${f(x.sl)}</td><td>${f(x.tp1)}</td><td>${f(x.exit)}</td><td>${esc(x.exit_reason)}</td><td class="${x.r >= 0 ? "bull" : "bear"}">${fs(x.r, 2)}</td><td>${fs(x.pts, 2)}</td><td>${x.tq}</td><td>${isNum(x.p) ? f(x.p * 100, 0) : "—"}</td><td>${x.bars}</td></tr>`).join("");
  $("#tab-backtest").innerHTML = `
    <div class="grid wide">
      ${card("Frozen forward holdout", hold, pill(H.status || "—", H.status === "ACTIVE" ? "bull" : "warn"))}
      ${card("Whole sample (contaminated by development — read as diagnostics)", rows(tr.metrics, ct.metrics, ch.metrics))}
    </div>
    <div style="height:12px"></div>
    ${card("Cumulative R", `<div id="equity"></div><p class="note">Closed trades: treatment (gold), control (blue), challenger (violet). Entry at signal close; stop first on same-bar ties; 50% at TP1 then breakeven; rest at TP2; costs = session spread + 2×slippage + commission.</p>`)}
    <div style="height:12px"></div>
    <div class="grid wide">
      ${card("Walk-forward stability (treatment)", `<table class="t"><tr><th>Fold</th><th>n</th><th>Win</th><th>E[R]</th><th>PF</th></tr>${wf}</table><p class="note">Equal time slices; nothing is refitted between folds.</p>`)}
      ${card("Monte Carlo (treatment)", mc)}
      ${card("Calibration of P at entry (F-A12)", cal)}
      ${card("By session", brk(tr.by_session))}${card("By regime", brk(tr.by_regime))}${card("By direction", brk(tr.by_dir))}
    </div>
    <div style="height:12px"></div>
    ${card("Trades", `<div class="scroll"><table class="t"><tr><th>Entry</th><th>Dir</th><th>Entry</th><th>SL</th><th>TP1</th><th>Exit</th><th>Why</th><th>R</th><th>Pts</th><th>TQ</th><th>P%</th><th>Bars</th></tr>${trades || "<tr><td colspan=12 class='muted'>no trades</td></tr>"}</table></div>`,
      `<span><span class="toggle ${S.btArm === "treatment" ? "on" : ""}" data-arm="treatment">Treatment</span> <span class="toggle ${S.btArm === "control" ? "on" : ""}" data-arm="control">Control</span> <span class="toggle ${S.btArm === "challenger" ? "on" : ""}" data-arm="challenger">Challenger</span></span>`)}`;
  document.querySelectorAll("[data-arm]").forEach((b) => (b.onclick = () => { S.btArm = b.dataset.arm; renderBacktest(); }));
  if (EQ) { EQ.remove(); EQ = null; }
  if (!document.querySelector("#tab-backtest").classList.contains("hidden")) renderEquity();
}
function renderEquity() {
  const B = S.data && S.data.backtest; const el = $("#equity");
  if (!B || !el || !el.clientWidth) return;
  if (EQ) { EQ.remove(); EQ = null; }
  EQ = LightweightCharts.createChart(el, { ...chartOpts(), height: 260 });
  const mk = (arm, color) => {
    const pts = []; let last = 0;
    for (const e of (B[arm] && B[arm].equity) || []) { let t = Math.floor(Date.parse(e.t) / 1000); if (t <= last) t = last + 1; last = t; pts.push({ time: t, value: e.r }); }
    const s = EQ.addLineSeries({ color, lineWidth: 2, priceLineVisible: false }); s.setData(pts);
  };
  mk("treatment", css("--accent")); mk("control", css("--info")); mk("challenger", css("--arm3"));
  EQ.timeScale().fitContent();
}
function renderDiagnostics() {
  const D = S.data, d = D.dashboard, fn = d.funnel, sh = d.shadow, ce = d.census;
  const fr = (label, v, max) => `<div class="row"><div>${label}</div><div class="b" style="width:${max ? Math.max(0.5, (v / max) * 100) : 0}%"></div><div class="mono">${v}</div></div>`;
  const funnel = `<div class="funnel">${fr("Bars", fn.bars, fn.bars)}${fr("Trend", fn.trend, fn.bars)}${fr("+ HTF not opposed", fn.htf, fn.bars)}${fr("+ session / recent / DD", fn.pre, fn.bars)}${fr("+ trigger = SIGNALS", fn.sig, fn.bars)}</div>
    ${kv([["Vetoed: TQ below floor", fn.tq], ["Vetoed: race EV < 0", fn.ev], ["Vetoed: P below min", fn.cal], ["Vetoed: risk lock", fn.risk], ["Passed", `<b>${fn.pass_}</b>`]])}
    <p class="note">Why the system trades as often as it does, stage by stage, over the whole sample (Diagnostics §7). Diagnose, don't tune.</p>`;
  const ds = D.data_status.map((s) => `<tr><td>${esc(s.name)}</td><td class="${s.ok ? "bull" : "bear"}">${s.ok ? "OK" : "FAIL"}</td><td>${esc(s.source)}</td><td>${s.rows || ""}</td><td>${s.last ? esc(s.last.slice(0, 16).replace("T", " ")) : ""}</td><td class="muted" style="white-space:normal;text-align:left">${esc(s.note || "")}</td></tr>`).join("");
  const dows = ["", "", "Mo", "Tu", "We", "Th", "Fr"].map((n, k) => { if (k < 2) return ""; const b = d.dow_bull[k], r = d.dow_bear[k]; return b + r > 5 ? `${n} ${f((b / (b + r)) * 100, 0)}%` : ""; }).filter(Boolean).join(" · ");
  const hist = (D.holdout.history || []).map((h) => `${h.config_hash} ${h.freeze_utc.slice(0, 10)} → ${h.ended_utc.slice(0, 10)}`).join("<br>") || "none";
  $("#tab-diagnostics").innerHTML =
    card("Gate funnel (treatment)", funnel) +
    card("Frozen holdout manifest", kv([["Status", esc(D.holdout.status)], ["Freeze (UTC)", esc(D.holdout.freeze_utc)], ["Config hash", esc(D.holdout.config_hash)], ["Engine", esc(D.holdout.engine_version)], ["Earlier freezes", hist]]) +
      `<p class="note">A new configuration hash starts a new holdout. Evidence never carries over between configurations.</p>`) +
    card("Volatility cone", kv([["Band (Z=2)", f(D.cone.band, 2)], ["Horizon", D.cone.bars + " bars"], ["Last bar", D.cone.breach_up ? "breached ↑" : D.cone.breach_dn ? "breached ↓" : "inside"]]) + `<p class="note">${esc(D.cone.note)}</p>`) +
    card("V1 / V2 regime shadow", kv([["Bars", sh.bars], ["Composite differs", sh.dcomp], ["Regime class differs", sh.regchg], ["Crosses 40 / 70", `${sh.x40} / ${sh.x70}`], ["Max |Δ|", sh.maxabs]]) +
      `<p class="note">How often the GC/OI data layer (schema V2) changes the regime versus V1 on the same bar.</p>`) +
    card("Data census", kv([["Stored observations", ce.n], ["With GC confirmation", pct(ce.gc_pct, 0)], ["With OI conviction", pct(ce.oi_pct, 0)], ["Schema V2 share", pct(ce.v2_pct, 0)], ["Imputed-volume bars", D.meta.vol_imputed_bars]])) +
    card("Day-of-week bias", `<p class="mono">${dows || "not enough history"}</p><p class="note">Share of trend-and-macro-aligned bull bars per weekday (decayed).</p>`) +
    card("Decision timeline", `<div class="scroll" style="max-height:260px"><table class="t"><tr><th>Bar</th><th>From</th><th>To</th></tr>${D.decisions.slice().reverse().map((x) => `<tr><td>${tfmt(x.t)}</td><td>${esc(x.from)}</td><td>${esc(x.to)}</td></tr>`).join("")}</table></div>`) +
    `<div class="card" style="grid-column:1/-1"><div class="hd"><h3>Data sources</h3><span class="pill">${esc(D.meta.price_source)} · volume ${esc(D.meta.volume_source)}</span></div><div class="bd scroll"><table class="t"><tr><th>Series</th><th>State</th><th>Source</th><th>Rows</th><th>Last</th><th>Note</th></tr>${ds}</table></div></div>` +
    `<div class="card" style="grid-column:1/-1"><div class="hd"><h3>Frozen configuration</h3><span class="pill">${esc(D.meta.config_hash)}</span></div><div class="bd"><details><summary class="muted">show all ${Object.keys(D.meta.config).length} parameters</summary><div class="scroll"><table class="t">${Object.entries(D.meta.config).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join("")}</table></div></details></div></div>`;
}
async function renderMethod() {
  if ($("#tab-method").dataset.loaded) return;
  try {
    const r = await fetch("method.html", { cache: "no-store" });
    $("#tab-method").innerHTML = `<div class="card method"><div class="bd">${await r.text()}</div></div>`;
    $("#tab-method").dataset.loaded = "1";
  } catch (e) { $("#tab-method").innerHTML = card("Method", "Could not load method.html"); }
}
/* ---------- one-line summary strip (the Master's top table, read left to right) ---------- */
function renderStrip() {
  const el = $("#sumstrip"); const D = S.data; if (!el || !D) return;
  const d = D.dashboard, p = d.plan || {}, lq = (d.liquidity && d.liquidity.pools) || {}, ch = D.chart || {};
  const vw = ch.vwap && ch.vwap.length ? ch.vwap[ch.vwap.length - 1] : null;
  const dec = d.decision, sig = dec === "BUY" || dec === "SELL";
  const cell = (k, v, sub, cls = "") => `<div class="sc ${cls}"><span class="k">${k}</span><span class="v">${v}</span><span class="s">${sub}</span></div>`;
  el.innerHTML = [
    cell("Signal", esc(dec), `L ${f(d.bull_score, 0)} · S ${f(d.bear_score, 0)} · R ${f(d.range_score, 0)}`, dec === "BUY" ? "bull" : dec === "SELL" ? "bear" : ""),
    cell("Structure", esc(structStr(d.struct)), esc(d.regime ? d.regime.label : "")),
    cell("Liquidity", esc(d.liquidity ? d.liquidity.dest : "—"), `PDH ${px(lq.PDH)} · PDL ${px(lq.PDL)}`),
    cell("Price", px(d.close), `VWAP D ${px(vw)}`),
    cell("Macro", esc(d.macro ? d.macro.label : "—"), d.macro ? `${fs(d.macro.strength, 0)} · votes ${d.macro.bull_votes}/${d.macro.bear_votes}` : ""),
    cell("Risk", isNum(p.rr1) ? `1:${f(p.rr1, 1)} · SL ${f(p.dist, 2)}` : "—", `Kelly ${d.kelly ? f(d.kelly.kelly_pct, 2) : "—"}%${sig ? "" : " · no signal"}`),
    cell("Decision", `${esc(dec)} · TQ ${d.trade_quality}${esc(d.tq_grade || "")}`, `${esc(d.bias_label)} · ${esc(d.session.label)} ${d.session.quality}/30`, dec === "NO TRADE" || dec === "RISK LOCK" ? "warn" : ""),
  ].join("");
}
function renderAll() {
  renderHeader(); renderSide(); renderChart();
  const safe = (fn) => { try { fn(); } catch (e) { console.error(e); } };
  safe(renderBrief); safe(renderStrip); safe(renderH2); safe(renderH3); safe(renderOverview); safe(renderEvents); safe(renderReference); safe(renderMt5); safe(renderGuard); safe(syncTV); safe(renderLive); safe(renderMacro); safe(renderLiquidity); safe(renderAnalog); safe(renderBacktest); safe(renderDiagnostics); renderMethod();
  showTab(S.tab);
}
load();
