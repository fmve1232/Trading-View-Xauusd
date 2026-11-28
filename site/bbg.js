/* The terminal band at the top of the page (mandate 2026-11-28, Parts 18-19). DISPLAY ONLY.
   model(D, I, x) lays out values that are already published: D = data/<tf>.json and I = data/index.json from the
   pipeline, plus what app.js already derives and passes in as x (freshness, the live quote, the forward-record verdict,
   the wording of a WAIT reason, the trend-vote wording, the MT5 offset). It computes no signal, score or probability and
   fills nothing in: a missing input is shown as N/A, UNAVAILABLE, DELAYED, UNTESTED or STALE. Every cell names its field
   in FIELDS, the field map; docs/DASHBOARD_FIELD_MAP.md is generated from FIELDS (audit/tools/dashboard_field_map.py). */
(function (root) {
  "use strict";
  const isNum = (v) => typeof v === "number" && isFinite(v);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const W = { NA: "N/A", UN: "UNAVAILABLE", DL: "DELAYED", UT: "UNTESTED", ST: "STALE" };
  const RUN = "each engine run";
  const LIVE_F = "browser: gold-api.com every 5 s, or the relay's tick stream";
  const NOTE_IDX = "index.json, written by quantum/notify.py on each engine run";

  // id -> [section, label, source field(s), how the cell is formed, update frequency]
  const FIELDS = {
    "A.instrument": ["A", "Instrument", "meta.price_source", "XAUUSD; INDICATIVE when the source is COMEX futures (GC=F) standing in for spot", RUN],
    "A.tf": ["A", "Timeframe", "meta.tf", "as published", RUN],
    "A.source": ["A", "Data source", "meta.price_source, meta.synthetic", "as published; SYNTHETIC if meta.synthetic", RUN],
    "A.fresh": ["A", "Freshness", "meta.last_bar_close, meta.generated_utc; app.js freshness()", "bar close and run age; STALE when 2 or more bars have closed since (the site's existing OUT OF DATE rule)", "every second (age), each run (values)"],
    "A.market": ["A", "Market", "app.js marketClosed(); dashboard.session.label", "CLOSED Friday 17:00 to Sunday 18:00 and daily 17:00-18:00 New York (the pipeline's gold_shut rule); else the session of the last closed bar", "every second"],
    "A.warn": ["A", "Warnings", "meta.synthetic, meta.price_source, index.errors, data_status[].ok, app.js freshness(), the live quote", "a list of what is synthetic, indicative, stale, failed or unavailable; 'none' if nothing", RUN],
    "B.engine": ["B", "Engine", "dashboard.decision", "as published (BUY / SELL / WAIT / NO TRADE / WARMUP / RISK LOCK) for the last closed bar; STALE as A.fresh", RUN],
    "B.setup": ["B", "Setup", "alerts.c1.open[0] (index.json); dashboard.decision", "the open C1 setup (an engine signal on the phone's 15m alerts), else 'engine signal' when the engine says BUY / SELL, else none", RUN],
    "B.tf": ["B", "Signal TF", "alerts.c1.open[0].tf; meta.tf", "the open setup's timeframe, else this chart's when the engine signals; else N/A", RUN],
    "B.confirm": ["B", "Confirmation", "alerts.c1.open[0].status, .p0, .ladder; alerts.c1.min_usd", "PENDING = waiting for a 15m close at least min_usd beyond P0; ACTIVE / TP1 = confirmed (quantum/confirm_entry.py)", RUN],
    "B.score": ["B", "Score", "none (deliberately)", "never shown: the engine's scores are not validated as probabilities (AUC about 0.5, Amendment 12; IA-02); UNTESTED", "fixed"],
    "B.entry": ["B", "Entry", "alerts.c1.decision.word, .until, .why", "BUY / SELL = ENTRY ELIGIBLE until 'until'; WAIT = not an entry; NO TRADE = no entry (the phone's own decision, the same object the alert text is built from)", RUN],
    "C.bos": ["C", "BOS", "dashboard.struct.bos_label_bull / _bear; markers[type=BOS]", "▲ / ▼ when on the last closed bar; otherwise the last one with its age in bars, grey (not current)", RUN],
    "C.choch": ["C", "CHoCH", "dashboard.struct.choch_bull / _bear; markers[type=CHoCH]", "as C.bos", RUN],
    "C.mss": ["C", "MSS", "dashboard.struct.mss_bull / _bear; markers[type=MSS]", "as C.bos", RUN],
    "C.active": ["C", "Active", "dashboard.struct.bull_act / bear_act, bull_type / bear_type, bull_age / bear_age", "the engine's active structure and its age in bars", RUN],
    "C.mtf": ["C", "By TF", "dashboard.mtf.scores (5, 15, 60, 240, D); app.js htfDir()", "each timeframe's trend vote in the site's existing wording (>= 60 up, <= 40 down, 50 = n/a); votes, not odds", RUN],
    "C.align": ["C", "Alignment", "dashboard.mtf.align_long / align_short", "the engine's count of timeframes aligned each way; green / red when one side has more, amber when level, grey when none", RUN],
    "D.pdx": ["D", "PDH / PDL", "dashboard.liquidity.pools.PDH / PDL", "as published, plus the MT5 offset the viewer set (app.js px())", RUN],
    "D.pwx": ["D", "PWH / PWL", "dashboard.liquidity.pools.PWH / PWL", "as D.pdx", RUN],
    "D.pmx": ["D", "PMH / PML", "dashboard.liquidity.pools.PMH / PML", "as D.pdx", RUN],
    "D.eqx": ["D", "EQH / EQL", "dashboard.liquidity.pools.EQH / EQL", "as D.pdx; N/A when the engine has none", RUN],
    "D.cdx": ["D", "Day H / L", "dashboard.liquidity.cdh / cdl", "as D.pdx", RUN],
    "D.draw": ["D", "Engine draw", "dashboard.liquidity.dest", "the level the engine names as its liquidity target; UNTESTED as a forecast (no score or confidence shown)", RUN],
    "D.swept": ["D", "Sweep confirmed", "dashboard.liquidity.sweep_bull / sweep_bear; markers[type=SWEEP]", "CONFIRMED when the engine flags a sweep on the last closed bar; otherwise the last SWEEP marker with its age, grey", RUN],
    "D.monitor": ["D", "Sweep monitor", "alerts.sweeps.events[] (index.json; B31b-W7-A3)", "the newest event: confirmed at its bar close; DEVELOPING while its +$10 / +$15 / +$20 follow-through is open (done = false)", RUN],
    "D.possible": ["D", "Possible sweep", "none published", "N/A: a sweep is confirmed only at the bar close; nothing is published for the forming bar, and the page does not guess one", "fixed"],
    "E.price": ["E", "Price", "the live quote (app.js LIVE, display only); dashboard.close", "LIVE when fresh and the market is open; otherwise the engine's last close, DELAYED (or CLOSED)", LIVE_F],
    "E.time": ["E", "Timestamp", "the live quote's time; meta.last_bar_close", "the time of the price shown in E.price", LIVE_F],
    "E.ema": ["E", "EMA 20/100/200", "chart.ema20 / ema100 / ema200 (last bar)", "as published, at the last bar close (calculated, not live); STALE as A.fresh", RUN],
    "E.vwap": ["E", "VWAP D/W/M", "chart.vwap / wvwap / mvwap (last bar)", "as E.ema", RUN],
    "E.bb": ["E", "BB U/M/L", "chart.bb_up / bb_mid / bb_lo (last bar)", "as E.ema", RUN],
    "E.sr": ["E", "Res / Sup", "dashboard.struct.active_res / active_sup", "the engine's active levels; N/A when none", RUN],
    "E.plan": ["E", "Entry·SL·TP1·TP2", "alerts.c1.open[].plan (when ENTRY ELIGIBLE); dashboard.plan (when the engine says BUY / SELL)", "the phone's plan while an entry is eligible, else the engine's plan on a signal bar, else N/A (no signal)", RUN],
    "F.DXY": ["F", "DXY", "macro.DXY.value / .valid / .gold_bullish / .gold_bearish; data_status[DX-Y.NYB_60m]", "value, as-of time and the engine's read for gold; UNAVAILABLE if not valid or the feed failed; STALE if 2+ bars old while the market is open; DELAYED if the run fell back to the store", RUN],
    "F.US10Y": ["F", "US10Y", "macro.US10Y; data_status[^TNX_60m]", "as F.DXY (yield, %)", RUN],
    "F.EURUSD": ["F", "EURUSD", "macro.EURUSD; data_status[EURUSD=X_<tf>]", "as F.DXY", RUN],
    "F.XAG": ["F", "XAGUSD", "macro.XAG; data_status[SI=F_<tf>]", "as F.DXY (COMEX silver futures stand in for spot silver)", RUN],
    "F.SPX": ["F", "SPX", "macro.SPX; data_status[^GSPC_<tf>]", "as F.DXY", RUN],
    "F.GC": ["F", "COMEX GC", "macro.gc.enabled / .valid / .value; meta.price_source", "OFF when the engine input is off; UNAVAILABLE when on but not valid", RUN],
    "F.OI": ["F", "GC open int.", "macro.oi.valid / .state", "weekly CFTC open interest; UNAVAILABLE when not valid", RUN],
    "F.COT": ["F", "COT", "macro.cot.valid / .pct", "weekly CFTC report; UNAVAILABLE when not valid", RUN],
    "G.rr": ["G", "R:R", "alerts.c1.open[].plan.rr_net; dashboard.plan.rr1 / rr2", "net R:R after costs (phone plan) or the engine plan's gross R:R; N/A without a plan", RUN],
    "G.stop": ["G", "Stop dist.", "alerts.c1.open[].plan.entry / sl; dashboard.plan.dist", "|entry - stop| of the plan shown in E.plan, in $ of price; N/A without a plan", RUN],
    "G.targets": ["G", "Targets", "the plan's tp1 / tp2", "as E.plan", RUN],
    "G.position": ["G", "Position risk", "alerts.c1.open[].plan.risk_usd / budget / lot; the viewer's MT5 specification (app.js S.spec, checked by QCosts.specValidate) and account (S.account)", "the phone plan's loss at the stop including costs and its budget, UNTESTED (contract and broker costs unverified, G2); the lot only once the viewer has entered a valid MT5 specification and an account", RUN],
    "G.spread": ["G", "Spread", "dashboard.session.spread (model); data/mt5.json tick.spread (broker, when connected)", "the engine's modelled session spread; the broker's live spread beside it when an MT5 feed is connected, amber if wider than the model; UNAVAILABLE otherwise", RUN],
    "G.commission": ["G", "Commission", "cost_profiles[id=engine].commission", "the frozen cost model (quantum/config.py); UNTESTED against the broker (G2)", RUN],
    "G.slippage": ["G", "Slippage", "cost_profiles[id=engine].slippage", "modelled points per side; actual slippage not measured, UNTESTED (G2)", RUN],
    "G.costwarn": ["G", "Cost alerts", "dashboard.checks.cost_pts / cost_pct_atr / cost_amber_pct / cost_red_pct; news (QCosts.newsState)", "HIGH / ABNORMAL COST at the engine's own amber / red thresholds; NEWS WINDOW with the modelled cost multiplier", RUN],
    "H.final": ["H", "Final", "app.js recordVerdict(backtest.treatment.holdout); alerts.c1.decision.word", "NO TRADE / INSUFFICIENT EVIDENCE unless the engine arm's frozen forward holdout on this timeframe shows an edge (N >= 50, 95% interval of mean R above 0, PF >= 1.2); then the phone's decision", RUN],
    "H.phone": ["H", "Phone", "alerts.c1.decision.word / .why", "as published (the phone and the site show this one decision)", RUN],
    "H.engine": ["H", "Engine", "dashboard.decision, dashboard.blk_why (app.js whyPlain()), dashboard.tq_floor_veto, dashboard.risk.lock", "the engine's decision with its reason in the site's existing wording; STALE as A.fresh", RUN],
    "H.evidence": ["H", "Evidence", "backtest.treatment.holdout.n / avg_r / t_stat / profit_factor; app.js recordVerdict()", "the forward holdout record and its verdict (the site's RECORD rule)", RUN],
    "H.confirm": ["H", "Confirm by", "alerts.c1.min_usd", "a 15m close at least min_usd beyond the trigger (C1, quantum/confirm_entry.py)", RUN],
    "H.invalid": ["H", "Invalid if", "alerts.c1.inv_usd; the plan's sl", "the stop once a plan is live; before confirmation, inv_usd against the trigger or an opposite 15m BOS / MSS / CHoCH or engine signal (C1)", RUN],
    "I.open": ["I", "Open trade", "manual trade ledger (mandate Part 14; not published to the site yet)", "UNAVAILABLE until a ledger is published; then its open trade", "when the ledger is published"],
    "I.single": ["I", "Trade slot", "manual trade ledger", "UNAVAILABLE until a ledger is published; then AVAILABLE or BLOCKED (one trade at a time)", "when the ledger is published"],
    "I.sid": ["I", "Latest signal", "alerts.c1.open[] and alerts.c1.recent[] (newest t_close)", "its id, timeframe and side", RUN],
    "I.stime": ["I", "Signal time", "the same setup's t_close", "the close of its signal bar", RUN],
    "I.sstatus": ["I", "Signal status", "the same setup's status / why", "as published (PENDING, ACTIVE, TP1, TP2, BE, SL, INVALIDATED, EXPIRED, REJECTED ...)", RUN],
    "I.outcome": ["I", "Latest outcome", "alerts.c1.recent[] with a plan result (TP2, BE, SL, AMBIGUOUS, TIMEOUT)", "the alert record's result on 15m bars; not an executed trade", RUN],
    "I.blocked": ["I", "Blocked?", "manual trade ledger; alerts.c1.decision.word", "UNAVAILABLE until a ledger is published; then YES when an entry is eligible while a trade is open", "when the ledger is published"],
  };
  // Part 19 item 4: what is missing, delayed, stale, untested or unavailable by construction (field id -> why)
  const GAPS = {
    "B.score": "UNTESTED by design: the engine has no validated score or probability (Amendment 12; IA-02), so none is shown",
    "D.draw": "UNTESTED: the engine's named target level has not been validated as a forecast",
    "D.possible": "NOT PUBLISHED: the pipeline publishes no forming-bar sweep state; showing one would need a new pipeline field",
    "E.price": "LIVE only while the market is open and the browser reaches gold-api.com or the relay; otherwise the last close, DELAYED",
    "F.DXY": "free Yahoo series: DELAYED when the run falls back to the stored series, STALE when 2+ bars old while gold trades (also F.US10Y, F.EURUSD, F.XAG, F.SPX)",
    "F.GC": "OFF: the engine's COMEX confirmation input is off (Pine default)",
    "F.OI": "UNAVAILABLE whenever the weekly CFTC fetch fails (also F.COT)",
    "G.position": "UNTESTED: the contract and the broker's costs are unverified (G2); no lot without the viewer's valid MT5 specification and account (Part 9)",
    "G.spread": "broker spread only with a connected MT5 feed (data/mt5.json); otherwise the modelled spread, UNTESTED",
    "G.commission": "UNTESTED against the broker (G2) (also G.slippage)",
    "I.open": "NOT PUBLISHED: needs the manual trade ledger (Part 14) published to the site; wiring it in needs approval (also I.single, I.blocked)",
  };
  const SECTIONS = [["A", "MARKET"], ["B", "SIGNAL"], ["C", "STRUCTURE"], ["D", "LIQUIDITY"], ["E", "PRICE"], ["F", "MACRO"], ["G", "RISK"], ["H", "DECISION"], ["I", "TRADING STATUS"]];
  const STCLS = { "N/A": "na", UNAVAILABLE: "na", UNTESTED: "na", DELAYED: "amb", STALE: "amb", INDICATIVE: "amb", CLOSED: "na", SYNTHETIC: "bear" };

  function cell(id, v, o) {
    if (!FIELDS[id]) throw new Error("bbg: no field map entry for " + id);
    o = o || {};
    const st = o.st || "";
    const value = v === null || v === undefined || v === "" ? (st || W.NA) : String(v);
    return { id, k: o.k || FIELDS[id][1], v: value, st: value === st ? "" : st, c: o.c || STCLS[st] || "", note: o.note || "", src: FIELDS[id][2] };
  }
  const bars = (k) => `${k} bar${k === 1 ? "" : "s"}`;
  const dirWord = (d) => (d > 0 ? "BUY" : d < 0 ? "SELL" : "");
  const dirCls = (d) => (d > 0 ? "bull" : d < 0 ? "bear" : "");
  const srcName = (s) => String(s || "").replace("twelvedata:", "Twelve Data ").replace("yahoo:", "Yahoo ");
  const last = (a) => (Array.isArray(a) && a.length ? a[a.length - 1] : null);
  const FINAL_RES = ["TP2", "BE", "SL", "AMBIGUOUS", "TIMEOUT"];
  const MACRO_DS = { DXY: () => "DX-Y.NYB_60m", US10Y: () => "^TNX_60m", EURUSD: (yi) => `EURUSD=X_${yi}`, XAG: (yi) => `SI=F_${yi}`, SPX: (yi) => `^GSPC_${yi}` };
  const YINT = { "5m": "5m", "15m": "15m", "30m": "30m", "1h": "60m", "4h": "60m" };
  const DS_SEC = { "5m": 300, "15m": 900, "30m": 1800, "60m": 3600, "1d": 86400 };

  function unavailable(why) {
    const out = {};
    for (const [s] of SECTIONS) out[s] = Object.keys(FIELDS).filter((id) => FIELDS[id][0] === s).map((id) => cell(id, null, { st: W.UN, note: why }));
    return { sections: out, final: { v: W.UN, c: "na", note: why }, stale: false };
  }

  function model(D, I, x) {
    if (!D || !D.meta || !D.dashboard) return unavailable("data/<tf>.json could not be read");
    const M = D.meta, d = D.dashboard, ch = D.chart || {}, px = x.px, t = x.tfmt;
    const A = (I && I.alerts) || null, c1 = A && A.c1 && A.c1.on !== false ? A.c1 : null;
    const fr = x.fresh || {}, stale = isNum(fr.behind) && fr.behind >= 2, ST = stale ? W.ST : "";
    const barT = Date.parse(M.last_bar_close) / 1000, barTxt = isNum(barT) ? t(barT) : "—";
    const dec = d.decision, sig = dec === "BUY" || dec === "SELL";
    const S = {};

    // ---- A. MARKET / INSTRUMENT
    const src = M.price_source || "", gc = /GC=F/.test(src), syn = !!M.synthetic;
    const failed = (D.data_status || []).filter((r) => r && r.ok === false).map((r) => r.name);
    const live = x.live && isNum(x.live.px) ? x.live : null;
    const warn = [syn ? "SYNTHETIC data" : "", gc ? "futures stand in for spot" : "", stale ? `${fr.behind} bars behind` : "",
      !I ? "index.json unavailable" : I.errors && Object.keys(I.errors).length ? "pipeline errors: " + Object.keys(I.errors).join(", ") : "",
      failed.length ? `${failed.length}/${(D.data_status || []).length} feeds failed` : "", !x.closed && !live ? "live quote unavailable" : ""].filter(Boolean);
    S.A = [
      cell("A.instrument", "XAUUSD", gc ? { st: "INDICATIVE", note: "COMEX gold futures (GC=F) stand in for spot on this run; futures trade at a premium to spot" } : { note: srcName(src) }),
      cell("A.tf", M.tf),
      cell("A.source", syn ? "SYNTHETIC" : srcName(src) || null, syn ? { c: "bear", note: "simulated prices: nothing here describes the real market" } : { st: src ? "" : W.UN }),
      cell("A.fresh", `bar ${barTxt} · run ${x.ago(M.generated_utc)}`, { st: ST, note: stale ? `${fr.behind} ${M.tf} bars have closed since this run's last bar: values are out of date` : "" }),
      cell("A.market", x.closed ? "CLOSED" : `OPEN · ${(d.session && d.session.label) || "—"}`, x.closed ? { c: "na", note: "Spot gold is shut Friday 17:00 to Sunday 18:00 New York and daily 17:00-18:00" } : { note: "session of the last closed bar" }),
      cell("A.warn", warn.length ? warn.join(" · ") : "none", { c: warn.length ? (syn ? "bear" : "amb") : "", note: failed.length ? "failed feeds: " + failed.join(", ") : "" }),
    ];

    // ---- B. SIGNAL
    const op = c1 && Array.isArray(c1.open) ? c1.open : [];
    const set0 = op.length ? op[0] : null, cw = c1 && c1.decision ? c1.decision : null;
    const decCls = dec === "BUY" ? "bull" : dec === "SELL" ? "bear" : dec === "WAIT" || dec === "NO TRADE" ? "amb" : "na";
    const confTxt = !c1 ? null : !set0 ? "no open setup" : set0.status === "PENDING" ? `waiting: a 15m close $${c1.min_usd ?? "—"} beyond ${px(set0.p0)}` : set0.status === "ACTIVE" || set0.status === "TP1" ? `CONFIRMED · ${set0.status}` : set0.status;
    const entTxt = !cw ? null : cw.word === "BUY" || cw.word === "SELL" ? `${cw.word} ENTRY ELIGIBLE until ${isNum(cw.until) ? t(cw.until) : "—"}` : cw.word === "WAIT" ? "NOT AN ENTRY · waiting for confirmation" : "NO ENTRY";
    S.B = [
      cell("B.engine", dec, { c: decCls, st: ST, note: `the engine's decision on the ${M.tf} bar that closed ${barTxt}` }),
      cell("B.setup", set0 ? `C1 setup #${set0.id} · ${set0.tf} ${dirWord(set0.dir)}` : sig ? "engine signal" : "none", { c: set0 ? dirCls(set0.dir) : sig ? decCls : "na" }),
      cell("B.tf", set0 ? set0.tf : sig ? M.tf : null, { st: set0 || sig ? "" : W.NA }),
      cell("B.confirm", confTxt, { st: c1 ? "" : W.UN, c: set0 && set0.status === "PENDING" ? "amb" : set0 ? dirCls(set0.dir) : "na", note: set0 && set0.ladder ? set0.ladder : "" }),
      cell("B.score", "NOT SHOWN", { st: W.UT, c: "na", note: "The engine's scores are not validated as probabilities (AUC about 0.5, Amendment 12): no score, confidence or probability is shown here." }),
      cell("B.entry", entTxt, { st: cw ? "" : W.UN, c: cw && (cw.word === "BUY" || cw.word === "SELL") ? dirCls(cw.word === "BUY" ? 1 : -1) : cw && cw.word === "WAIT" ? "amb" : "na", note: cw ? cw.why || "" : "alerts.c1 is missing from index.json" }),
    ];

    // ---- C. MARKET STRUCTURE
    const st = d.struct || {}, n = Array.isArray(ch.t) ? ch.t.length : 0;
    const lastMk = (type) => {
      const a = (D.markers || []).filter((m) => m.type === type); if (!a.length) return null;
      const m = a[a.length - 1], i = n ? ch.t.indexOf(m.t) : -1;
      return { ...m, ago: i >= 0 ? n - 1 - i : null };
    };
    const ev = (id, type, bull, bear) => {
      if (bull || bear) return cell(id, `${bull ? "▲" : "▼"} on the last bar`, { c: bull ? "bull" : "bear", st: ST, note: `confirmed at the ${barTxt} close` });
      const m = lastMk(type);
      if (!m) return cell(id, "none in the chart window", { c: "na" });
      return cell(id, `last ${m.dir > 0 ? "▲" : m.dir < 0 ? "▼" : "·"} ${isNum(m.ago) ? bars(m.ago) + " ago" : ""}`.trim(), { c: "na", note: `${t(m.t)}: not current` });
    };
    const votes = [["5", "5m"], ["15", "15m"], ["60", "1h"], ["240", "4h"], ["D", "1D"]].map(([k, nm]) => {
      const dir = x.htfDir(((d.mtf || {}).scores || {})[k]);
      return { t: `${nm} ${dir === "up" ? "▲" : dir === "down" ? "▼" : dir === "mixed" ? "◆" : "—"}`, c: dir === "up" ? "bull" : dir === "down" ? "bear" : dir === "mixed" ? "amb" : "na" };
    });
    const al = d.mtf || {}, aL = al.align_long, aS = al.align_short;
    S.C = [
      ev("C.bos", "BOS", st.bos_label_bull, st.bos_label_bear),
      ev("C.choch", "CHoCH", st.choch_bull, st.choch_bear),
      ev("C.mss", "MSS", st.mss_bull, st.mss_bear),
      cell("C.active", st.bull_act ? `▲ ${st.bull_type} · ${bars(st.bull_age)}` : st.bear_act ? `▼ ${st.bear_type} · ${bars(st.bear_age)}` : "none", { c: st.bull_act ? "bull" : st.bear_act ? "bear" : "na", st: ST }),
      { ...cell("C.mtf", votes.map((v) => v.t).join(" "), { st: d.mtf ? ST : W.UN, note: "trend votes, not odds" }), parts: d.mtf ? votes : null },
      cell("C.align", isNum(aL) && isNum(aS) ? `long ${aL} · short ${aS}` : null, { st: isNum(aL) ? ST : W.UN, c: !isNum(aL) ? "na" : aL > aS ? "bull" : aS > aL ? "bear" : aL > 0 ? "amb" : "na" }),
    ];

    // ---- D. LIQUIDITY
    const lq = d.liquidity || {}, P = lq.pools || {}, hasDraw = !!lq.dest && lq.dest !== "—";
    const pair = (id, a, b) => (isNum(a) || isNum(b) ? cell(id, `${isNum(a) ? px(a) : "—"}/${isNum(b) ? px(b) : "—"}`, { st: ST }) : cell(id, null, { st: d.liquidity ? W.NA : W.UN }));
    const sw = lastMk("SWEEP"), sweeps = A && A.sweeps && Array.isArray(A.sweeps.events) ? A.sweeps.events.slice().sort((p, q) => q.t - p.t) : null, e0 = sweeps && sweeps.length ? sweeps[0] : null;
    const stages = e0 && e0.stages ? Object.keys(e0.stages) : [];
    S.D = [
      pair("D.pdx", P.PDH, P.PDL), pair("D.pwx", P.PWH, P.PWL), pair("D.pmx", P.PMH, P.PML), pair("D.eqx", P.EQH, P.EQL), pair("D.cdx", lq.cdh, lq.cdl),
      cell("D.draw", hasDraw ? lq.dest : null, { st: hasDraw ? W.UT : d.liquidity ? W.NA : W.UN, c: "na", note: "the engine's named liquidity target; not tested as a forecast" }),
      lq.sweep_bull || lq.sweep_bear
        ? cell("D.swept", `CONFIRMED ${lq.sweep_bull ? "▲ sell-side (a low) taken" : "▼ buy-side (a high) taken"}`, { c: lq.sweep_bull ? "bull" : "bear", st: ST, note: `on the ${barTxt} close` })
        : cell("D.swept", sw ? `last ${sw.dir < 0 ? "high" : "low"} ${(sw.lvl && sw.lvl[0] && sw.lvl[0].name) || ""} · ${isNum(sw.ago) ? bars(sw.ago) + " ago" : t(sw.t)}` : "none in the chart window", { c: "na", note: sw ? `${t(sw.t)}, wick ${px(sw.px)}: not current` : "" }),
      !sweeps ? cell("D.monitor", null, { st: W.UN, note: "alerts.sweeps is missing from index.json" })
        : !e0 ? cell("D.monitor", "no event", { c: "na" })
          : cell("D.monitor", `${e0.done ? "done" : "DEVELOPING"} · ${e0.dir > 0 ? "▲" : "▼"} ${e0.ref_kind} ${e0.ref_tf} ${px(e0.ref)} · ${t(e0.t_close)}`,
            { c: e0.done ? "na" : "amb", note: `swept and confirmed at the ${t(e0.t_close)} close; stages so far: ${stages.join(", ") || "—"}${e0.done ? "" : "; the +$10 / +$15 / +$20 follow-through is still open"}` }),
      cell("D.possible", null, { st: W.NA, c: "na", note: "a sweep is confirmed only at the bar close; the forming bar is not published and the page does not guess one" }),
    ];

    // ---- E. PRICE / TECHNICAL LEVELS
    const v3 = (a, b, c) => [a, b, c].map((k) => (isNum(last(ch[k])) ? px(last(ch[k])) : "—")).join("/");
    const any3 = (a, b, c) => [a, b, c].some((k) => isNum(last(ch[k])));
    const eligible = cw && (cw.word === "BUY" || cw.word === "SELL") ? op.find((s) => s.id === cw.id && s.plan) || null : null;
    const plan = eligible ? { ...eligible.plan, src: `phone plan, setup #${eligible.id}`, dir: eligible.dir } : sig && d.plan && isNum(d.plan.entry) ? { ...d.plan, src: "engine plan", dir: d.plan.long ? 1 : -1 } : null;
    S.E = [
      live ? cell("E.price", live.px.toFixed(2), { k: "Price (live)", c: "", note: `${live.src || "live"} quote, display only: the engine never uses it` })
        : cell("E.price", isNum(d.close) ? d.close.toFixed(2) : null, { k: "Price (last close)", st: x.closed ? "CLOSED" : W.DL, note: x.closed ? "the market is closed: the engine's last close" : "live quote unavailable: the engine's last close" }),
      cell("E.time", live ? t(live.t / 1000) : barTxt, { note: live ? "time of the live quote" : "close of the last engine bar" }),
      cell("E.ema", any3("ema20", "ema100", "ema200") ? v3("ema20", "ema100", "ema200") : null, { st: any3("ema20", "ema100", "ema200") ? ST : W.UN, note: `at the ${barTxt} close (calculated)` }),
      cell("E.vwap", any3("vwap", "wvwap", "mvwap") ? v3("vwap", "wvwap", "mvwap") : null, { st: any3("vwap", "wvwap", "mvwap") ? ST : W.UN, note: `at the ${barTxt} close (calculated)` }),
      cell("E.bb", any3("bb_up", "bb_mid", "bb_lo") ? v3("bb_up", "bb_mid", "bb_lo") : null, { st: any3("bb_up", "bb_mid", "bb_lo") ? ST : W.UN, note: `at the ${barTxt} close (calculated)` }),
      cell("E.sr", isNum(st.active_res) || isNum(st.active_sup) ? `${isNum(st.active_res) ? px(st.active_res) : "—"}/${isNum(st.active_sup) ? px(st.active_sup) : "—"}` : null, { st: d.struct ? ST : W.UN }),
      plan ? cell("E.plan", `${px(plan.entry)}/${px(plan.sl)}/${px(plan.tp1)}/${px(plan.tp2)}`, { c: dirCls(plan.dir), note: plan.src })
        : cell("E.plan", null, { st: W.NA, c: "na", note: "no signal: no entry, stop or target" }),
    ];

    // ---- F. MACRO
    const mac = D.macro || null, ds = {}, yi = YINT[M.tf] || "60m";
    for (const r of D.data_status || []) if (r && r.name) ds[r.name] = r;
    const nowS = x.nowMs / 1000;
    const macroCell = (key, dp, unit) => {
      const id = "F." + key, m = mac && mac[key], r = ds[MACRO_DS[key](yi)];
      if (!m || !m.valid || !isNum(m.value)) return cell(id, null, { st: W.UN, note: r && r.note ? String(r.note).slice(0, 160) : "not valid on this run" });
      if (r && r.ok === false) return cell(id, null, { st: W.UN, note: String(r.note || "").slice(0, 160) });
      const asof = r && r.last ? Date.parse(r.last) / 1000 : NaN, sec = r ? DS_SEC[String(r.name).split("_").pop()] : null;
      const old = !x.closed && isNum(asof) && isNum(sec) && nowS - (asof + sec) >= 2 * sec;
      const viaStore = r && /store/.test(String(r.source || ""));
      const g = m.gold_bullish ? 1 : m.gold_bearish ? -1 : 0;
      return cell(id, `${m.value.toFixed(dp)}${unit} · gold ${g > 0 ? "▲" : g < 0 ? "▼" : "◆"}`,
        { st: old ? W.ST : viaStore ? W.DL : "", c: old || viaStore ? "amb" : g > 0 ? "bull" : g < 0 ? "bear" : "",
          note: `${r ? r.name : "series"} as of ${isNum(asof) ? t(asof) : "—"}${viaStore ? " (the live fetch failed; the stored series was used)" : ""}; the engine's read for gold, not a tested forecast` });
    };
    const g0 = mac && mac.gc, oi = mac && mac.oi, cot = mac && mac.cot;
    S.F = [
      macroCell("DXY", 3, ""), macroCell("US10Y", 3, "%"), macroCell("EURUSD", 5, ""), macroCell("XAG", 3, ""), macroCell("SPX", 2, ""),
      !g0 ? cell("F.GC", null, { st: W.UN }) : !g0.enabled ? cell("F.GC", "OFF", { c: "na", note: `engine input off (Pine default)${gc ? "; this run's gold price itself is GC=F" : ""}` })
        : g0.valid && isNum(g0.value) ? cell("F.GC", g0.value.toFixed(2)) : cell("F.GC", null, { st: W.UN, note: g0.fail || "" }),
      !oi || !oi.valid ? cell("F.OI", null, { st: W.UN, note: (oi && oi.note) || "" }) : cell("F.OI", oi.state, { note: oi.note || "" }),
      !cot || !cot.valid ? cell("F.COT", null, { st: W.UN }) : cell("F.COT", isNum(cot.pct) ? `${cot.pct.toFixed(0)} pct-ile` : "valid", { note: "weekly CFTC positioning percentile (not a probability)" }),
    ];

    // ---- G. RISK
    const prof = (D.cost_profiles || []).find((p) => p && p.id === "engine") || null, chk = d.checks || {}, se = d.session || {};
    const specOk = !!(x.spec && x.specOk && x.account > 0), oz = M.config && isNum(M.config.point_value) ? M.config.point_value : null;
    const nw = x.news || {}, cpa = chk.cost_pct_atr;
    const cw2 = [isNum(cpa) && isNum(chk.cost_red_pct) && cpa > chk.cost_red_pct ? `ABNORMAL COST ${cpa.toFixed(0)}% of ATR` : isNum(cpa) && isNum(chk.cost_amber_pct) && cpa > chk.cost_amber_pct ? `HIGH COST ${cpa.toFixed(0)}% of ATR` : "",
      nw.in_window ? `NEWS WINDOW: ${nw.in_window.name} · modelled costs × ${(D.news && D.news.cost_mult) || "—"}` : ""].filter(Boolean);
    const brk = x.mt5 && x.mt5.status === "OK" && x.mt5.tick && isNum(x.mt5.tick.spread) ? x.mt5.tick.spread : null;
    S.G = [
      plan ? cell("G.rr", isNum(plan.rr_net) ? `${plan.rr_net.toFixed(2)} net` : isNum(plan.rr1) ? `1:${plan.rr1.toFixed(1)} / 1:${plan.rr2.toFixed(1)} gross` : null, { note: plan.src }) : cell("G.rr", null, { st: W.NA, c: "na", note: "no plan" }),
      plan ? cell("G.stop", isNum(plan.dist) ? `$${plan.dist.toFixed(2)}` : isNum(plan.entry) && isNum(plan.sl) ? `$${Math.abs(plan.entry - plan.sl).toFixed(2)}` : null, { note: plan.src }) : cell("G.stop", null, { st: W.NA, c: "na" }),
      plan ? cell("G.targets", `${px(plan.tp1)}/${px(plan.tp2)}`, { c: dirCls(plan.dir), note: plan.src }) : cell("G.targets", null, { st: W.NA, c: "na" }),
      plan && isNum(plan.risk_usd)
        ? cell("G.position", `$${plan.risk_usd.toFixed(0)} at stop incl. costs · budget $${isNum(plan.budget) ? plan.budget.toFixed(0) : "—"}${specOk ? ` · ${plan.lot} lot` : " · lot NOT SIZED"}`,
          { st: W.UT, c: specOk && oz !== x.spec.contract_size ? "amb" : "",
            note: specOk ? `the pipeline sized ${plan.lot} lot on a ${oz ?? "—"} oz contract (meta.config.point_value); your MT5 specification says ${x.spec.contract_size} per lot`
              : `No lot is shown until you enter a valid MT5 specification and account (mandate Part 9). The figures use an unverified ${oz ?? "—"} oz contract (meta.config.point_value) and the modelled costs (G2).` })
        : cell("G.position", null, { st: W.NA, c: "na", note: "no plan: nothing is sized without a signal" }),
      cell("G.spread", isNum(se.spread) ? `model ${se.spread.toFixed(2)}${isNum(brk) ? ` · broker ${brk.toFixed(2)}` : ""}` : null,
        { st: isNum(se.spread) ? (isNum(brk) ? "" : W.UT) : W.UN, c: isNum(brk) && isNum(se.spread) && brk > se.spread ? "amb" : "", note: isNum(brk) ? "broker spread from the connected MT5 feed" : "the engine's modelled session spread; no broker spread feed is connected (UNAVAILABLE)" }),
      prof && prof.commission ? cell("G.commission", `$${Number(prof.commission.rate).toFixed(2)}/lot ${String(prof.commission.basis || "").replace("_", " ")}`, { st: W.UT, note: "the frozen cost model: " + (prof.source || "") + "; the broker's commission is not verified (G2)" }) : cell("G.commission", null, { st: W.UN }),
      prof && isNum(prof.slippage) ? cell("G.slippage", `${prof.slippage.toFixed(2)} pts`, { st: W.UT, note: "the frozen cost model, points per side; actual slippage not measured (G2)" }) : cell("G.slippage", null, { st: W.UN }),
      cell("G.costwarn", cw2.length ? cw2.join(" · ") : isNum(cpa) ? `none · cost ${cpa.toFixed(0)}% of ATR` : null,
        { st: isNum(cpa) ? "" : W.UN, c: cw2.some((w) => /ABNORMAL|NEWS/.test(w)) ? "bear" : cw2.length ? "amb" : "", note: isNum(cpa) ? `cost ${isNum(chk.cost_pts) ? chk.cost_pts.toFixed(2) : "—"} pts; amber above ${chk.cost_amber_pct}%, red above ${chk.cost_red_pct}% of ATR (the engine's thresholds)` : "" }),
    ];

    // ---- H. DECISION
    const hold = D.backtest && D.backtest.treatment ? D.backtest.treatment.holdout : null;
    const rv = x.verdict(hold), evOk = rv && rv.lv === 1;
    const word = cw ? cw.word : null;
    const final = !evOk ? { v: "NO TRADE / INSUFFICIENT EVIDENCE", c: "nt", note: "the engine arm's forward holdout shows no edge yet on this timeframe" }
      : word === "BUY" || word === "SELL" ? { v: word, c: word === "BUY" ? "bull" : "bear", note: cw.why || "" }
        : word ? { v: word, c: "amb", note: cw.why || "" } : { v: W.UN, c: "na", note: "the phone's decision (alerts.c1) is missing" };
    const why = d.blk_why ? x.why(d.blk_why) : "", veto = [d.tq_floor_veto ? "trade quality below the floor" : "", d.risk && d.risk.lock ? "risk lock" : ""].filter(Boolean).join(", ");
    const liveSl = eligible && eligible.plan && isNum(eligible.plan.sl) ? eligible.plan.sl : null;
    S.H = [
      cell("H.final", final.v, { c: final.c === "nt" ? "amb" : final.c, note: final.note }),
      cell("H.phone", word ? `${word}${cw.why ? " · " + cw.why : ""}` : null, { st: word ? "" : W.UN, c: word === "BUY" ? "bull" : word === "SELL" ? "bear" : word ? "amb" : "na" }),
      cell("H.engine", `${dec}${why ? " · " + why : ""}${veto ? " · " + veto : ""}`, { c: decCls, st: ST }),
      cell("H.evidence", hold && hold.n ? `holdout ${M.tf}: n ${hold.n} · ${rv.txt}` : `holdout ${M.tf}: ${rv ? rv.txt : "—"}`, { c: !rv ? "na" : rv.lv === 1 ? "bull" : rv.lv === -1 ? "bear" : "amb", st: hold ? "" : W.UN,
        note: rv && isNum(rv.lo) ? `mean ${hold.avg_r} R, 95% interval ${rv.lo.toFixed(3)} to ${rv.hi.toFixed(3)} R, PF ${hold.profit_factor}` : "" }),
      cell("H.confirm", c1 && isNum(c1.min_usd) ? `a 15m close ≥ $${c1.min_usd} beyond the trigger` : null, { st: c1 ? "" : W.UN }),
      cell("H.invalid", isNum(liveSl) ? `stop ${px(liveSl)}` : c1 && isNum(c1.inv_usd) ? `before confirmation: $${c1.inv_usd} against the trigger, or an opposite 15m BOS / MSS / CHoCH or engine signal` : null, { st: c1 ? "" : W.UN }),
    ];

    // ---- I. TRADING STATUS
    const L = x.ledger || null, noL = "No execution ledger is published to the site yet (mandate Part 14): this page cannot say whether a trade is open.";
    const setups = c1 ? [...(c1.open || []), ...(c1.recent || [])].filter((s) => s && isNum(s.t_close)).sort((p, q) => q.t_close - p.t_close) : [];
    const s0 = setups[0] || null, out0 = c1 ? (c1.recent || []).find((s) => FINAL_RES.includes(s.status)) : null;
    const lopen = L ? L.open || null : null;
    S.I = [
      L ? cell("I.open", lopen ? `${lopen.signal_id || ""} ${lopen.side || ""} OPEN`.trim() : "NO OPEN TRADE", { c: lopen ? "amb" : "" }) : cell("I.open", null, { st: W.UN, note: noL }),
      L ? cell("I.single", lopen ? "BLOCKED · one trade at a time" : "AVAILABLE", { c: lopen ? "amb" : "bull" }) : cell("I.single", null, { st: W.UN, note: noL }),
      cell("I.sid", s0 ? `#${s0.id} · ${s0.tf} ${dirWord(s0.dir)}` : c1 ? "none" : null, { st: c1 ? "" : W.UN, c: s0 ? dirCls(s0.dir) : "na" }),
      cell("I.stime", s0 ? t(s0.t_close) : null, { st: c1 ? (s0 ? "" : W.NA) : W.UN }),
      cell("I.sstatus", s0 ? s0.status : null, { st: c1 ? (s0 ? "" : W.NA) : W.UN, note: s0 ? s0.why || "" : "" }),
      cell("I.outcome", out0 ? `${out0.status} · setup #${out0.id}` : null, { st: c1 ? (out0 ? "" : W.NA) : W.UN, c: out0 ? (out0.status === "SL" ? "bear" : out0.status === "TP2" ? "bull" : "") : "na", note: "the alert record's result on 15m bars; not an executed trade" }),
      L ? cell("I.blocked", lopen && (word === "BUY" || word === "SELL") ? "YES · a trade is open" : "NO", { c: lopen && (word === "BUY" || word === "SELL") ? "amb" : "" }) : cell("I.blocked", null, { st: W.UN, note: noL }),
    ];
    return { sections: S, final, stale };
  }

  function render(m) {
    const row = (c) => `<div class="r" title="${esc((c.note ? c.note + " · " : "") + "source: " + c.src)}"><span class="k">${esc(c.k)}</span>` +
      `<span class="v ${esc(c.c)}">${c.parts ? c.parts.map((p) => `<i class="${esc(p.c)}">${esc(p.t)}</i>`).join(" ") : esc(c.v)}${c.st ? `<span class="st ${esc(STCLS[c.st] || "")}">${esc(c.st)}</span>` : ""}</span></div>`;
    return `<div class="bbg-hd"><b>XAUUSD</b><span>TERMINAL</span><span class="dim">display only · every value is published by the engine run; hover a row for its source</span>${m.stale ? '<span class="st amb">STALE</span>' : ""}</div>` +
      `<div class="bbg-grid">${SECTIONS.map(([s, title]) => `<section class="bbg-p sec-${s}" aria-label="${esc(title)}"><h4><b>${s}</b>${esc(title)}</h4>` +
        (s === "H" ? `<div class="bbg-final ${esc(m.final.c)}" title="${esc(m.final.note || "")}">${esc(m.final.v)}</div>` : "") +
        `${(m.sections[s] || []).filter((c) => !(s === "H" && c.id === "H.final")).map(row).join("")}</section>`).join("")}</div>`;
  }

  const api = { FIELDS, GAPS, SECTIONS, WORDS: W, model, render };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.QBbg = api;
})(typeof window !== "undefined" ? window : globalThis);
