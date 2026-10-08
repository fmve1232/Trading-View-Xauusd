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
  ["sr", "S/R"], ["vp", "Value area"], ["signals", "Signals"], ["structure", "BOS / CHoCH"], ["sweeps", "Sweeps"], ["plan", "Plan"], ["cone", "Vol cone"], ["h2", "H2 signals"]];
if (S.toggles.h2 === undefined) S.toggles.h2 = true;   // added after viewers saved their toggles
$("#toolbar").innerHTML = TOGGLES.map(([k, l]) => `<span class="toggle ${S.toggles[k] ? "on" : ""}" data-k="${k}">${l}</span>`).join("");
$("#toolbar").onclick = (e) => {
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
}, 60000);

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
async function pollLive() {
  if (document.hidden || streaming()) return;
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
    Object.assign(LIVE, { px: p, t: isFinite(ts) ? ts : Date.now(), err: "", src: "gold-api" });
  } catch (e) { LIVE.err = (e && e.message) || "unavailable"; }
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
  chip.title = (src === "stream" ? "Streaming ticks (Finnhub via the relay), at most 4 updates a second. DISPLAY ONLY: the engine never uses them; signals come from closed bars." : LIVE_TITLE) +
    (STREAM.url ? ` Stream: ${STREAM.status || "—"}.` : "") + (closed ? " The market is closed (Friday 17:00 to Sunday 18:00 New York, and the daily 17:00-18:00 break): the feed repeats the last quote with a fresh timestamp." : "") +
    ` Price as of ${new Date(LIVE.t).toUTCString()}.` + (LIVE.err ? " Last refresh failed: " + LIVE.err : "");
  renderGuard();
}
setInterval(pollLive, 60000);
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
    if (m.type === "hello" || m.type === "status") { STREAM.status = String(m.status || "").slice(0, 80); if (m.last) onTick(m.last, true); renderLive(); }
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
  Object.assign(LIVE, { px: p, t, err: "", src: "stream" });
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
}

/* ---------- side panels ---------- */
/* ---------- arm H2 "Sweep and Value" (pre-registered, Amendment 5; computed by quantum/arm_h2.py) ---------- */
function renderH2() {
  const D = S.data, el = $("#h2"), st = $("#h2-state"); if (!el || !D) return;
  const H = D.h2;
  if (!H || H.error) { el.innerHTML = `<p class="muted">${esc((H && H.error) || "not published yet")}</p>`; st.textContent = "—"; st.className = "pill"; return; }
  const now = H.signal_now, ck = H.checklist || {};
  st.textContent = now ? `${now.dir} signal` : "no setup"; st.className = "pill " + (now ? (now.dir === "LONG" ? "bull" : "bear") : "");
  const score = (c) => (c ? Object.values(c).filter(Boolean).length : 0);
  // The side shown: the live signal's side; else the side the trend rule favours; else the side with
  // more rules met. (Showing the higher count alone put "Long side" on screen in a clear downtrend.)
  const tl = !!(ck.long && ck.long.trend), ts = !!(ck.short && ck.short.trend);
  const side = now ? (now.dir === "LONG" ? "long" : "short") : tl !== ts ? (tl ? "long" : "short")
    : score(ck.long) >= score(ck.short) ? "long" : "short", c = ck[side] || {};
  const other = side === "long" ? "short" : "long";
  const rows = (H.rules || []).map(([k, lt, stx]) => `<li class="${c[k] ? "ok" : "bad"}">${c[k] ? "✓" : "✗"} ${esc(side === "short" ? stx : lt)}</li>`).join("");
  const p = now || H.last_signal;
  const planHtml = p ? `<div class="why"><b>${now ? "Signal now" : "Last signal"}:</b> ${esc(p.dir)} ${tfmt(p.t)} · entry ${px(p.entry)} · SL ${px(p.sl)} · TP1 ${px(p.tp1)} · TP2 ${px(p.tp2)} <span class="dim">(sweep bar ${tfmt(p.sweep_t)})</span></div>` : "";
  const open = (H.open || [])[0];
  const openHtml = open ? `<div class="why"><b>Open H2 trade:</b> ${esc(open.dir)} since ${tfmt(Date.parse(open.entry_time) / 1000)} · entry ${px(open.entry)} · SL ${px(open.sl)} · TP1 ${px(open.tp1)}</div>` : "";
  const nm = H.next_move_in_sample || {}, fw = H.forward || {}, fr = H.freeze || {};
  const next = nm.n ? `After ${nm.n} past H2 signals on ${esc(D.meta.tf)} (in-sample): TP1 reached first ${f(nm.tp1_first_pct, 0)}%, stop first ${f(nm.stop_first_pct, 0)}%, mean ${fs(nm.mean_r, 2)} R, median ${fs(nm.median_r, 2)} R, about ${f(nm.avg_bars, 0)} bars to the exit.` : "No past H2 signals on this timeframe yet.";
  const fwd = fw.n ? `${fw.n} closed · win ${f(fw.win_rate, 0)}% · mean ${fs(fw.avg_r, 2)} R · PF ${f(fw.profit_factor, 2)}` : "no closed trades yet";
  el.innerHTML = `<div class="why"><b>${esc(side === "long" ? "Long" : "Short")} side, ${score(c)}/5 rules met</b> <span class="dim">(${other} side ${score(ck[other])}/5)</span><ul class="gates">${rows}</ul></div>` + planHtml + openHtml +
    `<div class="why"><b>Next movement:</b> ${next} <span class="dim">Small samples: a pattern, not a forecast.</span></div>` +
    `<div class="why"><b>Forward record</b> (since ${fr.freeze_utc ? tfmt(Date.parse(fr.freeze_utc) / 1000) : "—"}; only this counts): ${fwd}. Decision on 1H after 50 trades (Amendment 5).</div>`;
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
  const rows = GATES.map(([k, txt]) => `<li class="${fails.includes(k) ? "bad" : "ok"}">${fails.includes(k) ? "✗" : "✓"} ${txt}${k === "Sess" && d.blk_why && d.blk_why.startsWith("SESS") ? ` <span class="dim">(${esc(d.blk_why)})</span>` : ""}${k === "Trend" && d.blk_why && d.blk_why.startsWith("TREND") ? ` <span class="dim">(${esc(d.blk_why)})</span>` : ""}</li>`).join("");
  const fn = d.funnel || {}, rate = fn.bars ? fn.sig / fn.bars : null, wk = 5 * 23 * 3600 / D.meta.tf_sec;
  const passed = isNum(fn.pass_) && fn.bars ? fn.pass_ / fn.bars : null;
  const waitFor = d.decision === "WAIT" ? (fails.length === 1 && fails[0] === "Trig" ? `Everything is in place for a ${side}. It is waiting for a trigger bar.` :
    `A ${side} still needs: ${fails.map((f) => (GATES.find((g) => g[0] === f) || [f, f])[1]).join("; ")}.`) : "";
  return `<div class="why"><b>${d.decision === "WAIT" ? "Why WAIT" : "Gates"} (${side} side):</b> ${esc(waitFor)}<ul class="gates">${rows}</ul>` +
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
  $("#plan-dir").title = sig ? "Side of the current signal." : `No signal: a hypothetical plan on the regime-call side (L${f(d.bull_bias, 0)} ${p.long ? "≥" : "<"} S${f(d.bear_bias, 0)}). The bias label uses the final scores (L${f(d.bull_score, 0)} / S${f(d.bear_score, 0)}), so the two can differ. WAIT means no trade.`;
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
    <p class="note">Touch rates are marginal excursion frequencies over ${p.horizon_bars} bars, not a TP-before-SL race; the race EV is the expectancy. ${sig ? "Plan direction follows the signal." : `<b>No signal:</b> this is a hypothetical plan on the regime-call side (L${f(d.bull_bias, 0)} vs S${f(d.bear_bias, 0)}), not a trade. The bias label above uses the final scores, so it can point the other way.`}</p>
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
    grid: { vertLines: { color: css("--line") + "80" }, horzLines: { color: css("--line") + "80" } },
    rightPriceScale: { borderColor: css("--line") },
    timeScale: { borderColor: css("--line"), timeVisible: true, secondsVisible: false, rightOffset: 14, tickMarkFormatter: tickFmt },
    crosshair: { mode: 0 },
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
  const main = LC.createChart($("#chart"), chartOpts());
  const sub = LC.createChart($("#subchart"), { ...chartOpts(), timeScale: { ...chartOpts().timeScale, visible: false } });
  const line = (color, w = 1, style = 0) => main.addLineSeries({ color, lineWidth: w, lineStyle: style, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false });
  const candles = main.addCandlestickSeries({ upColor: css("--bull"), downColor: css("--bear"), wickUpColor: css("--bull"), wickDownColor: css("--bear"), borderVisible: false });
  const zones = new ZonesPrimitive();
  candles.attachPrimitive(zones);
  const L = {
    ema20: line("#e6edf6", 1), ema100: line("#4da3ff", 1), ema200: line("#f2c96b", 2),
    vwap: line("#00bcd4", 2), wvwap: line("#00bcd499", 1, 2), mvwap: line("#00bcd466", 1, 2),
    bb_up: line("#b084ff99", 1), bb_lo: line("#b084ff99", 1), bb_mid: line("#b084ff55", 1, 2),
    pdh: line("#ffd54f", 1, 1), pdl: line("#ffd54f", 1, 1), pwh: line("#ff8a65", 1, 1), pwl: line("#ff8a65", 1, 1),
    vpoc: line("#ffd54fcc", 1, 3), vah: line("#ffd54f77", 1, 3), val: line("#ffd54f77", 1, 3),
    cone_u: line("#9aa5b1", 1, 2), cone_l: line("#9aa5b1", 1, 2),
  };
  const subS = {
    bull: sub.addLineSeries({ color: css("--bull"), lineWidth: 1, priceLineVisible: false, lastValueVisible: true }),
    bear: sub.addLineSeries({ color: css("--bear"), lineWidth: 1, priceLineVisible: false, lastValueVisible: true }),
    range: sub.addLineSeries({ color: css("--neutral"), lineWidth: 1, priceLineVisible: false, lastValueVisible: false }),
    tq: sub.addHistogramSeries({ color: css("--accent") + "55", priceScaleId: "tq", priceLineVisible: false, lastValueVisible: false }),
  };
  sub.priceScale("tq").applyOptions({ scaleMargins: { top: 0.6, bottom: 0 }, visible: false });
  let syncing = false;
  main.timeScale().subscribeVisibleLogicalRangeChange((r) => { if (!r || syncing) return; syncing = true; sub.timeScale().setVisibleLogicalRange(r); syncing = false; });
  sub.timeScale().subscribeVisibleLogicalRangeChange((r) => { if (!r || syncing) return; syncing = true; main.timeScale().setVisibleLogicalRange(r); syncing = false; });
  main.subscribeCrosshairMove((prm) => legend(prm));
  new ResizeObserver(() => { main.applyOptions({ width: $("#chart").clientWidth }); sub.applyOptions({ width: $("#subchart").clientWidth }); }).observe($("#chart"));
  C = { main, sub, candles, zones, L, subS, priceLines: [], fitted: false };
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
  if (bars.length) applyLiveBar(bars[bars.length - 1].time);
  const set = (k, on) => C.L[k].setData(on ? series(t, ch[k], ch.anchor && ch.anchor[k]) : []);
  ["ema20", "ema100", "ema200"].forEach((k) => set(k, T.ema));
  ["vwap", "wvwap", "mvwap"].forEach((k) => set(k, T.vwap));
  ["bb_up", "bb_lo", "bb_mid"].forEach((k) => set(k, T.bb));
  ["pdh", "pdl", "pwh", "pwl"].forEach((k) => set(k, T.levels));
  ["vpoc", "vah", "val"].forEach((k) => set(k, T.vp));
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
  // markers
  const mk = [];
  for (const m of D.markers) {
    if (m.type === "SIGNAL" && T.signals) mk.push({ time: m.t, position: m.dir > 0 ? "belowBar" : "aboveBar", color: m.dir > 0 ? css("--bull") : css("--bear"), shape: m.dir > 0 ? "arrowUp" : "arrowDown", text: `${m.dir > 0 ? "BUY" : "SELL"} TQ${m.tq}` });
    else if (m.type === "VETO" && T.signals) mk.push({ time: m.t, position: m.dir > 0 ? "belowBar" : "aboveBar", color: css("--warn"), shape: "circle", text: `veto ${m.why}` });
    else if (m.type === "TRACK_EXIT" && T.signals) mk.push({ time: m.t, position: "inBar", color: (m.r || 0) >= 0 ? css("--bull") : css("--bear"), shape: "square", text: `${fs(m.r, 1)}R` });
    else if ((m.type === "BOS" || m.type === "CHoCH" || m.type === "MSS") && T.structure) mk.push({ time: m.t, position: m.dir > 0 ? "belowBar" : "aboveBar", color: m.dir > 0 ? css("--bull") + "cc" : css("--bear") + "cc", shape: "circle", size: 0.5, text: m.type });
    else if (m.type === "SWEEP" && T.sweeps) mk.push({ time: m.t, position: m.dir > 0 ? "belowBar" : "aboveBar", color: "#e040fb", shape: "circle", size: 0.4, text: "sweep" });
  }
  mk.sort((a, b) => a.time - b.time);
  if (T.h2 && D.h2 && Array.isArray(D.h2.signals)) {                     // arm H2 (toggle on by default)
    const t0 = D.chart.t[0];
    D.h2.signals.filter((g) => g.t >= t0).forEach((g) => mk.push({ time: g.t, position: g.dir === "LONG" ? "belowBar" : "aboveBar", color: "#b084ff",
      shape: g.dir === "LONG" ? "arrowUp" : "arrowDown", text: `H2 ${g.dir === "LONG" ? "BUY" : "SELL"}` }));
    mk.sort((a, b) => a.time - b.time);
  }
  C.candles.setMarkers(mk);
  // price lines
  C.priceLines.forEach((p) => C.candles.removePriceLine(p)); C.priceLines = [];
  // One line per price: a level the plan already names ("TP1 CDL") is not drawn again ("CDL"),
  // which stacked two labels on the same price.
  const drawn = [];
  const pl = (price, color, title, style = 2, w = 1) => {
    if (!isNum(price) || drawn.some((x) => Math.abs(x - price) < 0.005)) return;
    drawn.push(price);
    C.priceLines.push(C.candles.createPriceLine({ price, color, lineWidth: w, lineStyle: style, axisLabelVisible: true, title }));
  };
  const d = D.dashboard;
  if (T.plan) {
    const p = d.plan;
    pl(p.sl, css("--bear"), `SL ${p.sl_basis}`, 0, 1);
    pl(p.tp1, css("--bull"), `TP1 ${p.tp_basis[0]}`, 0, 1); pl(p.tp2, css("--bull"), `TP2 ${p.tp_basis[1]}`, 2); pl(p.tp3, css("--bull"), `TP3 ${p.tp_basis[2]}`, 2);
  }
  if (T.levels) {
    const lq = d.liquidity.pools;
    pl(lq.PDH, "#f0b04a", "PDH", 2); pl(lq.PDL, "#f0b04a", "PDL", 2);
    pl(lq.PWH, "#c79bff", "PWH", 2); pl(lq.PWL, "#c79bff", "PWL", 2);
    pl(lq.PMH, "#9aa5b1", "PMH", 1); pl(lq.PML, "#9aa5b1", "PML", 1);
    pl(d.liquidity.cdh, "#4dd0e1", "CDH", 3); pl(d.liquidity.cdl, "#4dd0e1", "CDL", 3);
    pl(lq.EQH, "#ef5350", "EQH", 3); pl(lq.EQL, "#26a69a", "EQL", 3);
  }
  if (T.sr && D.sr) {
    D.sr.res.forEach((r, k) => pl(r.price, css("--bear") + (r.touches >= 3 ? "cc" : "77"), `R${k + 1} ×${r.touches}`, 1));
    D.sr.sup.forEach((r, k) => pl(r.price, css("--bull") + (r.touches >= 3 ? "cc" : "77"), `S${k + 1} ×${r.touches}`, 1));
  }
  // sub pane
  C.subS.bull.setData(series(t, ch.bull)); C.subS.bear.setData(series(t, ch.bear)); C.subS.range.setData(series(t, ch.range));
  C.subS.tq.setData(series(t, ch.tq));
  if (!C.fitted || C.fittedTf !== S.tf) {
    const n = bars.length;
    C.main.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - 220), to: n + 12 });
    C.fitted = true; C.fittedTf = S.tf;
  }
  legend(null);
}
function legend(prm) {
  const D = S.data; if (!D) return;
  const ch = D.chart;
  let i = ch.t.length - 1;
  if (prm && prm.time) { const k = ch.t.indexOf(prm.time); if (k >= 0) i = k; }
  const col = ch.c[i] >= ch.o[i] ? "bull" : "bear";
  $("#legend").innerHTML = `<span>${tfmt(ch.t[i])}</span><span class="${col}">O <b>${f(ch.o[i])}</b> H <b>${f(ch.h[i])}</b> L <b>${f(ch.l[i])}</b> C <b>${f(ch.c[i])}</b></span>` +
    `<span>EMA20 <b>${f(ch.ema20[i])}</b> 200 <b>${f(ch.ema200[i])}</b></span><span>VWAP <b>${f(ch.vwap[i])}</b></span>` +
    `<span>L/R/S <b class="bull">${f(ch.bull[i], 0)}</b>/<b>${f(ch.range[i], 0)}</b>/<b class="bear">${f(ch.bear[i], 0)}</b> TQ <b>${f(ch.tq[i], 0)}</b></span><span>${esc(ch.session[i] || "")}</span>`;
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
  safe(renderStrip); safe(renderH2); safe(renderOverview); safe(renderEvents); safe(renderReference); safe(renderMt5); safe(renderGuard); safe(syncTV); safe(renderLive); safe(renderMacro); safe(renderLiquidity); safe(renderAnalog); safe(renderBacktest); safe(renderDiagnostics); renderMethod();
  showTab(S.tab);
}
load();
