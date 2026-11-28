// node --test tests/bbg.test.mjs : the terminal band (site/bbg.js) shows only published values, says UNAVAILABLE /
// N/A / STALE / UNTESTED / DELAYED instead of filling gaps, never shows a score or probability, and its final line is
// NO TRADE / INSUFFICIENT EVIDENCE unless the forward holdout shows an edge. The verdict, WAIT wording and trend-vote
// wording are app.js's own functions, extracted from its source (as tests/test_site_dashboard.py does).
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
const require = createRequire(import.meta.url);
const B = require("../site/bbg.js");
const SRC = readFileSync(new URL("../site/app.js", import.meta.url), "utf8");
const BBG = readFileSync(new URL("../site/bbg.js", import.meta.url), "utf8");
const slice = (a, b) => { const i = SRC.indexOf(a), j = SRC.indexOf(b, i); assert.ok(i >= 0 && j > i, a); return SRC.slice(i, j); };
const H = new Function(`const isNum = (x) => typeof x === "number" && isFinite(x);
${slice("const t975 = ", "// Visuals f_glNear")}
${slice("function whyPlain(", "/* ---------- Playbook")}
${slice("const htfDir = ", "function lastSweep(")}
return { recordVerdict, whyPlain, htfDir };`)();

const T0 = Date.parse("2026-11-30T10:20:00Z") / 1000;            // a Monday, market open
const series = (v) => [v - 2, v - 1, v];
function payload() {
  return {
    meta: { tf: "15m", tf_sec: 900, price_source: "twelvedata:XAU/USD", synthetic: false, generated_utc: "2026-11-30T10:18:00+00:00",
      last_bar_close: "2026-11-30T10:15:00+00:00", config: { point_value: 100 } },
    dashboard: {
      close: 4000, decision: "WAIT", blk_why: "HTF-OPP", tq_floor_veto: false, risk: { lock: false },
      confidence: 987654, cal_prob: 0.123456, cal_prob_bear: 0.654321, bull_score: 55.5555, bear_score: 44.4444, p_long: 0.777777,
      struct: { bos_label_bull: false, bos_label_bear: false, choch_bull: false, choch_bear: false, mss_bull: false, mss_bear: false,
        bull_act: false, bear_act: false, active_res: 4010, active_sup: 3990 },
      mtf: { scores: { 5: 70, 15: 30, 60: 50, 240: 45, D: 80 }, align_long: 1, align_short: 2 },
      liquidity: { pools: { PDH: 4020, PDL: 3980, PWH: 4050, PWL: 3950, PMH: 4100, PML: 3900, EQH: null, EQL: null }, cdh: 4005, cdl: 3995,
        dest: "PDH", sweep_bull: false, sweep_bear: false },
      session: { label: "LONDON", spread: 0.3 },
      checks: { cost_pts: 0.77, cost_pct_atr: 6, cost_amber_pct: 15, cost_red_pct: 25 },
      plan: { long: true, entry: 4000, sl: 3987, dist: 13, tp1: 4013, tp2: 4020, rr1: 1, rr2: 1.5 },
    },
    chart: { t: [T0 - 2700, T0 - 1800, T0 - 900], ema20: series(4001), ema100: series(3999), ema200: series(3990), vwap: series(3998),
      wvwap: series(3970), mvwap: series(3950), bb_up: series(4012), bb_mid: series(4000), bb_lo: series(3988) },
    markers: [],
    macro: { DXY: { valid: true, value: 104.014, gold_bearish: true }, US10Y: { valid: true, value: 4.2 }, EURUSD: { valid: true, value: 1.09 },
      XAG: { valid: true, value: 50.1, gold_bullish: true }, SPX: { valid: true, value: 7000 }, gc: { enabled: false }, oi: { valid: false }, cot: { valid: false } },
    data_status: [
      { name: "DX-Y.NYB_60m", ok: true, last: "2026-11-30T09:00:00+00:00", source: "yahoo" }, { name: "^TNX_60m", ok: true, last: "2026-11-30T09:00:00+00:00", source: "yahoo" },
      { name: "EURUSD=X_15m", ok: true, last: "2026-11-30T10:00:00+00:00", source: "yahoo" }, { name: "SI=F_15m", ok: true, last: "2026-11-30T10:00:00+00:00", source: "yahoo" },
      { name: "^GSPC_15m", ok: true, last: "2026-11-30T10:00:00+00:00", source: "yahoo" }],
    backtest: { treatment: { holdout: { n: 9, avg_r: 0.1056, t_stat: 0.2142, profit_factor: 1.0687 } } },
    cost_profiles: [{ id: "engine", commission: { rate: 7, basis: "round_turn" }, slippage: 0.2, source: "quantum/config.py" }],
    news: { cost_mult: 3, events: [] },
  };
}
const index = () => ({ errors: {}, alerts: {
  c1: { on: true, min_usd: 10, inv_usd: 13, decision: { word: "NO TRADE", id: null, why: "no setup is open: no qualifying opportunity" }, open: [], recent: [] },
  sweeps: { events: [] } } });
const ctx = (o = {}) => ({ nowMs: T0 * 1000, closed: false, fresh: { behind: 0 }, live: null, verdict: H.recordVerdict, why: H.whyPlain, htfDir: H.htfDir,
  px: (v) => (typeof v === "number" && isFinite(v) ? v.toFixed(2) : "—"), tfmt: (s) => new Date(s * 1000).toISOString().slice(0, 16), ago: () => "2 min ago",
  news: { in_window: null, next: null }, mt5: null, spec: null, specOk: false, account: null, ledger: null, ...o });
const cells = (m) => Object.values(m.sections).flat();
const byId = (m) => Object.fromEntries(cells(m).map((c) => [c.id, c]));

test("every cell names a field of the map, in its own section, and every field is shown", () => {
  const m = B.model(payload(), index(), ctx());
  const ids = cells(m).map((c) => c.id);
  assert.deepEqual([...ids].sort(), Object.keys(B.FIELDS).sort());
  for (const [s, list] of Object.entries(m.sections)) for (const c of list) { assert.equal(B.FIELDS[c.id][0], s, c.id); assert.equal(c.src, B.FIELDS[c.id][2]); }
  for (const id of Object.keys(B.GAPS)) assert.ok(B.FIELDS[id], "gap " + id);
});

test("no score, confidence or probability reaches the page", () => {
  const D = payload(); D.dashboard.decision = "BUY";
  const I = index(); I.alerts.c1.decision = { word: "BUY", id: 3, until: T0 + 600, why: "ENTRY ELIGIBLE" };
  I.alerts.c1.open = [{ id: 3, tf: "15m", dir: 1, p0: 3985, t_close: T0 - 900, status: "ACTIVE", plan: { entry: 3996, sl: 3983, tp1: 4009, tp2: 4016, lot: 0.46, risk_usd: 642.6, budget: 650, rr_net: 1.11 } }];
  const html = B.render(B.model(D, I, ctx()));
  // the engine's confidence, model p (long / short, raw and as %), scores and p_long, in any rounding the page could use
  for (const s of ["987654", "0.123", "12.3", "12%", "0.654", "65.4", "65%", "55.5", "56", "44.4", "0.777", "77.8", "78%"]) assert.ok(!html.includes(s), s);
  const pctOk = new Set(["F.US10Y", "G.costwarn"]);           // a yield and a cost share of ATR: neither is a probability
  for (const c of cells(B.model(D, I, ctx()))) if (/%/.test(c.v)) assert.ok(pctOk.has(c.id), `${c.id}: ${c.v}`);
  const reads = BBG.match(/(?:\.|\[")(bull_score|bear_score|range_score|bull_pre|confidence|conf_label|cal_prob\w*|p_long|p_short|kelly|race_\w+|hit_\w+|p_tp\d|p_sl|ev|reach|dest_score|dest_conf|analog|tq_grade|trade_quality)\b/g);
  assert.equal(reads, null, "bbg.js reads an engine score field: " + reads);
});

test("a missing payload shows UNAVAILABLE in every cell, and so does the final line", () => {
  const m = B.model(null, null, ctx());
  assert.ok(cells(m).every((c) => c.v === "UNAVAILABLE"));
  assert.equal(m.final.v, "UNAVAILABLE");
  assert.equal(cells(m).length, Object.keys(B.FIELDS).length);
});

test("missing or failed sources show status words, never a filled-in value", () => {
  let D = payload(); delete D.macro;
  let c = byId(B.model(D, index(), ctx()));
  for (const k of ["DXY", "US10Y", "EURUSD", "XAG", "SPX", "GC", "OI", "COT"]) assert.equal(c["F." + k].v, "UNAVAILABLE", k);
  D = payload(); D.macro.SPX.valid = false;                      // a number the engine marked invalid is not shown
  assert.equal(byId(B.model(D, index(), ctx()))["F.SPX"].v, "UNAVAILABLE");
  D = payload(); D.data_status[0].ok = false; D.data_status[0].note = "HTTP 500";
  c = byId(B.model(D, index(), ctx()));
  assert.equal(c["F.DXY"].v, "UNAVAILABLE"); assert.match(c["A.warn"].v, /1\/5 feeds failed/);
  c = byId(B.model(payload(), null, ctx()));
  for (const id of ["B.confirm", "B.entry", "H.phone", "H.confirm", "H.invalid", "I.sid", "I.stime", "I.sstatus", "I.outcome", "D.monitor"]) assert.equal(c[id].v, "UNAVAILABLE", id);
  assert.match(c["A.warn"].v, /index\.json unavailable/);
  D = payload(); delete D.dashboard.liquidity;
  c = byId(B.model(D, index(), ctx()));
  for (const id of ["D.pdx", "D.pwx", "D.pmx", "D.eqx", "D.cdx", "D.draw"]) assert.equal(c[id].v, "UNAVAILABLE", id);
  D = payload(); D.chart = { t: [] };
  c = byId(B.model(D, index(), ctx()));
  for (const id of ["E.ema", "E.vwap", "E.bb"]) assert.equal(c[id].v, "UNAVAILABLE", id);
  D = payload(); D.meta.price_source = "yahoo:GC=F";              // COMEX futures standing in for spot
  c = byId(B.model(D, index(), ctx()));
  assert.equal(c["A.instrument"].st, "INDICATIVE"); assert.match(c["A.warn"].v, /futures stand in for spot/); assert.equal(c["A.source"].v, "Yahoo GC=F");
  D = payload(); D.meta.synthetic = true;
  c = byId(B.model(D, index(), ctx()));
  assert.equal(c["A.source"].v, "SYNTHETIC"); assert.equal(c["A.source"].c, "bear"); assert.match(c["A.warn"].v, /SYNTHETIC data/);
  c = byId(B.model(payload(), index(), ctx({ live: { px: 4001, t: T0 * 1000, src: "gold-api.com" } })));
  assert.equal(c["A.instrument"].st, ""); assert.equal(c["A.warn"].v, "none");
  c = byId(B.model(payload(), index(), ctx()));
  assert.equal(c["D.eqx"].v, "N/A"); assert.equal(c["D.possible"].v, "N/A"); assert.equal(c["F.GC"].v, "OFF");
  assert.equal(c["F.OI"].v, "UNAVAILABLE"); assert.equal(c["B.score"].st, "UNTESTED"); assert.equal(c["D.draw"].st, "UNTESTED");
});

test("two or more bars behind marks every bar-derived cell STALE", () => {
  const c = byId(B.model(payload(), index(), ctx({ fresh: { behind: 3 } })));
  for (const id of ["A.fresh", "B.engine", "C.active", "C.mtf", "D.pdx", "E.ema", "E.vwap", "E.bb", "H.engine"]) assert.equal(c[id].st, "STALE", id);
  const ok = byId(B.model(payload(), index(), ctx({ fresh: { behind: 1 } })));
  assert.equal(ok["B.engine"].st, ""); assert.equal(ok["A.fresh"].st, "");
});

test("the live price is labelled LIVE only when fresh; otherwise the last close, DELAYED or CLOSED", () => {
  let c = byId(B.model(payload(), index(), ctx({ live: { px: 4003.5, t: T0 * 1000 - 3000, src: "gold-api.com" } })));
  assert.equal(c["E.price"].v, "4003.50"); assert.equal(c["E.price"].k, "Price (live)"); assert.equal(c["E.price"].st, "");
  c = byId(B.model(payload(), index(), ctx()));
  assert.equal(c["E.price"].v, "4000.00"); assert.equal(c["E.price"].st, "DELAYED"); assert.match(c["A.warn"].v, /live quote unavailable/);
  c = byId(B.model(payload(), index(), ctx({ closed: true })));
  assert.equal(c["E.price"].st, "CLOSED"); assert.equal(c["A.market"].v, "CLOSED");
});

test("macro: STALE when old while gold trades, DELAYED when the run used the stored series", () => {
  const D = payload(); D.data_status[0].last = "2026-11-30T05:00:00+00:00"; D.data_status[2].source = "store (live fetch failed)";
  let c = byId(B.model(D, index(), ctx()));
  assert.equal(c["F.DXY"].st, "STALE"); assert.equal(c["F.EURUSD"].st, "DELAYED"); assert.equal(c["F.XAG"].st, "");
  assert.match(c["F.DXY"].v, /^104\.014 · gold ▼$/);
  c = byId(B.model(D, index(), ctx({ closed: true })));
  assert.equal(c["F.DXY"].st, "");                             // the weekend is not staleness
});

test("Section I says UNAVAILABLE until an execution ledger is published, then follows it", () => {
  let c = byId(B.model(payload(), index(), ctx()));
  for (const id of ["I.open", "I.single", "I.blocked"]) assert.equal(c[id].v, "UNAVAILABLE", id);
  c = byId(B.model(payload(), index(), ctx({ ledger: { open: null } })));
  assert.equal(c["I.open"].v, "NO OPEN TRADE"); assert.equal(c["I.single"].v, "AVAILABLE"); assert.equal(c["I.blocked"].v, "NO");
  const I = index(); I.alerts.c1.decision = { word: "SELL", id: 4, until: T0 + 300, why: "ENTRY ELIGIBLE" };
  c = byId(B.model(payload(), I, ctx({ ledger: { open: { signal_id: "Q-0001", side: "BUY" } } })));
  assert.equal(c["I.open"].v, "Q-0001 BUY OPEN"); assert.match(c["I.single"].v, /^BLOCKED/); assert.match(c["I.blocked"].v, /^YES/);
});

test("latest signal, status and outcome come from the phone's setup record; an outcome is never called an executed trade", () => {
  const I = index();
  I.alerts.c1.recent = [{ id: 7, tf: "15m", dir: -1, t_close: T0 - 9000, status: "INVALIDATED", why: "price traded $13 against" },
    { id: 6, tf: "15m", dir: -1, t_close: T0 - 90000, status: "TP2" }];
  I.alerts.c1.open = [{ id: 8, tf: "15m", dir: 1, p0: 3990, t_close: T0 - 900, status: "PENDING", ladder: "CONFIRMATION STATUS: ..." }];
  const c = byId(B.model(payload(), I, ctx()));
  assert.equal(c["I.sid"].v, "#8 · 15m BUY"); assert.equal(c["I.sstatus"].v, "PENDING"); assert.equal(c["I.outcome"].v, "TP2 · setup #6");
  assert.match(c["I.outcome"].note, /not an executed trade/);
  assert.equal(c["B.confirm"].v, "waiting: a 15m close $10 beyond 3990.00"); assert.equal(c["B.setup"].v, "C1 setup #8 · 15m BUY");
});

test("the final line is NO TRADE / INSUFFICIENT EVIDENCE unless the holdout shows an edge; the actual decisions stay visible", () => {
  const D = payload(); D.dashboard.decision = "BUY";
  const I = index(); I.alerts.c1.decision = { word: "BUY", id: 3, until: T0 + 600, why: "ENTRY ELIGIBLE, setup #3" };
  let m = B.model(D, I, ctx()), c = byId(m);
  assert.equal(m.final.v, "NO TRADE / INSUFFICIENT EVIDENCE");
  assert.equal(c["B.engine"].v, "BUY"); assert.match(c["H.phone"].v, /^BUY/); assert.match(c["H.evidence"].v, /n 9 · UNDECIDED · N < 50/);
  D.backtest.treatment.holdout = { n: 60, avg_r: 0.3, t_stat: 3.0, profit_factor: 1.5 };     // the RECORD rule's EDGE SHOWN case
  m = B.model(D, I, ctx());
  assert.equal(m.final.v, "BUY"); assert.equal(m.final.c, "bull");
  I.alerts.c1.decision = { word: "NO TRADE", why: "no setup is open" };
  assert.equal(B.model(D, I, ctx()).final.v, "NO TRADE");
  D.backtest.treatment.holdout = { n: 60, avg_r: 0.3, t_stat: 3.0, profit_factor: 1.1 };     // interval above 0 but PF < 1.2
  assert.equal(B.model(D, I, ctx()).final.v, "NO TRADE / INSUFFICIENT EVIDENCE");
  delete D.backtest;
  m = B.model(D, I, ctx());
  assert.equal(m.final.v, "NO TRADE / INSUFFICIENT EVIDENCE"); assert.equal(byId(m)["H.evidence"].st, "UNAVAILABLE");
  assert.match(B.render(m), /class="bbg-final nt"[^>]*>NO TRADE \/ INSUFFICIENT EVIDENCE</);
});

test("entry, stop and targets appear only with a signal; no lot without a valid MT5 specification and account", () => {
  let c = byId(B.model(payload(), index(), ctx()));
  for (const id of ["E.plan", "G.rr", "G.stop", "G.targets", "G.position"]) assert.equal(c[id].v, "N/A", id);
  const D = payload(); D.dashboard.decision = "BUY";
  c = byId(B.model(D, index(), ctx()));
  assert.equal(c["E.plan"].v, "4000.00/3987.00/4013.00/4020.00"); assert.equal(c["G.rr"].v, "1:1.0 / 1:1.5 gross"); assert.equal(c["G.stop"].v, "$13.00");
  assert.equal(c["G.position"].v, "N/A");                      // the engine plan carries no sizing
  const I = index(); I.alerts.c1.decision = { word: "SELL", id: 5, until: T0 + 600, why: "ENTRY ELIGIBLE" };
  I.alerts.c1.open = [{ id: 5, tf: "15m", dir: -1, p0: 4015, t_close: T0 - 900, status: "ACTIVE", plan: { entry: 4001, sl: 4014, tp1: 3988, tp2: 3981, lot: 0.46, risk_usd: 642.62, budget: 650, rr_net: 1.1117 } }];
  c = byId(B.model(D, I, ctx()));
  assert.equal(c["E.plan"].v, "4001.00/4014.00/3988.00/3981.00"); assert.equal(c["E.plan"].c, "bear");
  assert.equal(c["G.rr"].v, "1.11 net"); assert.equal(c["G.stop"].v, "$13.00"); assert.equal(c["H.invalid"].v, "stop 4014.00");
  assert.equal(c["G.position"].v, "$643 at stop incl. costs · budget $650 · lot NOT SIZED"); assert.equal(c["G.position"].st, "UNTESTED");
  c = byId(B.model(D, I, ctx({ spec: { contract_size: 100 }, specOk: true, account: 25000 })));
  assert.match(c["G.position"].v, /· 0\.46 lot$/); assert.equal(c["G.position"].c, "na");     // grey: UNTESTED
  c = byId(B.model(D, I, ctx({ spec: { contract_size: 1 }, specOk: true, account: 25000 })));
  assert.equal(c["G.position"].c, "amb");                      // the viewer's contract differs from the one the plan was sized on
  c = byId(B.model(D, I, ctx({ spec: { contract_size: 100 }, specOk: false, account: 25000 })));
  assert.match(c["G.position"].v, /lot NOT SIZED$/);
  c = byId(B.model(D, I, ctx({ spec: { contract_size: 100 }, specOk: true, account: null })));   // no account entered
  assert.match(c["G.position"].v, /lot NOT SIZED$/);
});

test("structure off the last bar is grey with its age; on the last bar it is coloured", () => {
  const D = payload(); D.markers = [{ t: T0 - 2700, type: "BOS", dir: 1 }, { t: T0 - 1800, type: "CHoCH", dir: -1 }];
  let c = byId(B.model(D, index(), ctx()));
  assert.equal(c["C.bos"].v, "last ▲ 2 bars ago"); assert.equal(c["C.bos"].c, "na");
  assert.equal(c["C.choch"].v, "last ▼ 1 bar ago"); assert.equal(c["C.mss"].v, "none in the chart window");
  D.dashboard.struct.bos_label_bull = true; D.dashboard.struct.bull_act = true; D.dashboard.struct.bull_type = "BOS"; D.dashboard.struct.bull_age = 1;
  c = byId(B.model(D, index(), ctx()));
  assert.equal(c["C.bos"].v, "▲ on the last bar"); assert.equal(c["C.bos"].c, "bull"); assert.equal(c["C.active"].v, "▲ BOS · 1 bar");
  assert.equal(c["C.mtf"].v, "5m ▲ 15m ▼ 1h — 4h ◆ 1D ▲"); assert.equal(c["C.align"].c, "bear");
});

test("sweeps: CONFIRMED on the last bar, DEVELOPING while the follow-through is open, never a guessed possible sweep", () => {
  const D = payload(); D.dashboard.liquidity.sweep_bull = true;
  const I = index(); I.alerts.sweeps.events = [{ t: T0 - 1800, t_close: T0 - 900, dir: 1, ref_kind: "PDL", ref_tf: "15m", ref: 3980, stages: { SWEEP: {} } },
    { t: T0 - 90000, t_close: T0 - 89100, dir: -1, ref_kind: "PDH", ref_tf: "1h", ref: 4020, stages: { SWEEP: {}, MOVE10: {} }, done: true }];
  const c = byId(B.model(D, I, ctx()));
  assert.match(c["D.swept"].v, /^CONFIRMED ▲/); assert.equal(c["D.swept"].c, "bull");
  assert.match(c["D.monitor"].v, /^DEVELOPING · ▲ PDL 15m 3980\.00/); assert.equal(c["D.monitor"].c, "amb");
  assert.equal(c["D.possible"].v, "N/A");
});

test("cost warnings use the engine's own thresholds and the dated news window", () => {
  const D = payload(); D.dashboard.checks.cost_pct_atr = 18;
  assert.match(byId(B.model(D, index(), ctx()))["G.costwarn"].v, /^HIGH COST 18% of ATR$/);
  D.dashboard.checks.cost_pct_atr = 30;
  const c = byId(B.model(D, index(), ctx({ news: { in_window: { name: "NFP" } } })));
  assert.equal(c["G.costwarn"].v, "ABNORMAL COST 30% of ATR · NEWS WINDOW: NFP · modelled costs × 3"); assert.equal(c["G.costwarn"].c, "bear");
  const b = byId(B.model(payload(), index(), ctx({ mt5: { status: "OK", tick: { spread: 0.45 } } })));
  assert.equal(b["G.spread"].v, "model 0.30 · broker 0.45"); assert.equal(b["G.spread"].c, "amb");
});

test("text from the payload is escaped", () => {
  const I = index(); I.alerts.c1.decision = { word: "NO TRADE", why: '<img src=x onerror="alert(1)">' };
  const html = B.render(B.model(payload(), I, ctx()));
  assert.ok(!html.includes("<img") && html.includes("&lt;img"));
});
