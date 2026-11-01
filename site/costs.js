// Per-account cost profiles for POSITION SIZING only (display; mirrors quantum/cost_profiles.py, checked by
// tests/costs.test.mjs). The engine and every forward-test ledger keep the frozen cost model.
(function (root) {
  const OZ = 100;
  const sides = (basis, conservative = true) =>
    basis === "per_side" ? 2 : basis === "round_turn" || basis === "open_only" ? 1 : conservative ? 2 : 1;
  function commissionPerLot(p, price, conservative = true) {
    const c = p.commission, rate = Number(c.rate);
    if (!(rate >= 0) || !isFinite(rate)) return NaN;
    let per = rate;
    if (c.type === "pct") { if (!(price > 0) || !isFinite(price)) return NaN; per = OZ * price * rate / 100; }
    return per * sides(c.basis, conservative);
  }
  // (spread + 2 x slippage) x newsMult + commission / 100 oz; newsMult (Pine v92) only inside a dated news window
  function costPerOz(p, price, engineSpread, conservative = true, newsMult = 1) {
    const spread = p.spread.mode === "engine" ? engineSpread : Number(p.spread.value);
    const m = newsMult >= 1 ? newsMult : 1;
    return (spread + 2 * Number(p.slippage)) * m + commissionPerLot(p, price, conservative) / OZ;
  }
  // the dated news window that epoch t (seconds) is in, and the next release (mirrors quantum/news_calendar.state)
  function newsState(news, t) {
    let cur = null, nxt = null;
    if (!news || !news.events) return { in_window: null, next: null };
    for (const e of news.events) {
      if (!cur && e.t - news.before_min * 60 <= t && t <= e.t + news.after_min * 60) cur = e;
      if (!nxt && e.t > t) nxt = e;
    }
    return { in_window: cur, next: nxt };
  }
  // Wilson 95% interval for k of n (0-1)
  function wilson(k, n) {
    if (!(n > 0)) return [NaN, NaN];
    const z = 1.959964, p = k / n, d = 1 + z * z / n, c = (p + z * z / (2 * n)) / d;
    const h = z * Math.sqrt(Math.max(p * (1 - p) / n + z * z / (4 * n * n), 0)) / d;
    return [Math.max(0, c - h), Math.min(1, c + h)];
  }
  /* "Your trade" panel (display only; data from quantum/trade_race.py).
     Account dollars -> price distances at the lot (1 lot = 100 oz), the round-trip cost of the trade, and the win
     rate at which it breaks even after costs: a win nets TP - cost, a loss costs SL + cost, so p* = (SL + cost) / (TP + SL). */
  function tradeMath(slUsd, tpUsd, lot, costOz) {
    const oz = lot * OZ;
    if (!(oz > 0) || !(slUsd > 0) || !(tpUsd > 0)) return null;
    const cost = isFinite(costOz) && costOz >= 0 ? costOz * oz : NaN;
    return { oz, sl: slUsd / oz, tp: tpUsd / oz, cost, be: isFinite(cost) ? (slUsd + cost) / (tpUsd + slUsd) : NaN };
  }
  // The stored cell to read for a TP / SL in price: the nearest TP at or ABOVE it (harder to reach) and the nearest SL
  // at or BELOW it (tighter), so an off-grid trade is read on a stricter stand-in, never a kinder one.
  function raceIndex(R, tp, sl) {
    const e = 1e-6;
    const i = R.tp_grid.findIndex((a) => a >= tp - e);
    let j = -1;
    R.sl_grid.forEach((b, k) => { if (b <= sl + e) j = k; });
    if (i < 0 || j < 0) return null;
    return { i, j, tp: R.tp_grid[i], sl: R.sl_grid[j], exact: Math.abs(R.tp_grid[i] - tp) < e && Math.abs(R.sl_grid[j] - sl) < e };
  }
  // One source at one cell: wins, losses, open paths, and the expected $ per trade after costs (wins pay TP, losses
  // pay SL, a path still open after one day is marked at its horizon close).
  function raceCell(src, ix, tpUsd, slUsd, oz, costUsd) {
    const n = src.n, w = src.win[ix.i][ix.j], l = src.loss[ix.i][ix.j], mark = src.mark[ix.i][ix.j];
    const ev = n > 0 && isFinite(costUsd) ? (w * tpUsd - l * slUsd + mark * oz) / n - costUsd : NaN;
    return { n, w, l, open: n - w - l, p: n > 0 ? w / n : NaN, ev };
  }
  // Random entries in the SAME direction mix as the source: the long and short baselines weighted by its longs / shorts.
  function matchedRandom(R, src, ix, tpUsd, slUsd, oz, costUsd) {
    const nl = src.long, ns = src.short;
    if (!(nl + ns > 0)) return { p: NaN, ev: NaN };
    const L = raceCell(R.random.long, ix, tpUsd, slUsd, oz, costUsd), S = raceCell(R.random.short, ix, tpUsd, slUsd, oz, costUsd);
    const mix = (a, b) => ((nl ? nl * a : 0) + (ns ? ns * b : 0)) / (nl + ns);
    return { p: mix(L.p, S.p), ev: mix(L.ev, S.ev) };
  }
  /* Broker contract specification (mirrors quantum/contract.py; parity-tested). MT5 quotes the tick value in the
     ACCOUNT currency, so money per 1.00 of price per lot = tick_value / tick_size whatever the account currency. */
  const DEFAULT_SPEC = { symbol: "XAUUSD", contract_size: 100, tick_size: 0.01, tick_value: 1, digits: 2, account_currency: "USD",
    pip_size: 0.1, volume_min: 0.01, volume_step: 0.01, status: "UNVERIFIED" };
  const posNum = (v) => typeof v === "number" && isFinite(v) && v > 0;
  function specValidate(spec) {
    const err = [], warn = [];
    for (const k of ["contract_size", "tick_size", "tick_value", "pip_size", "volume_min", "volume_step"]) if (!posNum(spec[k])) err.push(`${k} must be a positive number`);
    const cur = String(spec.account_currency || "").toUpperCase();
    if (!/^[A-Z]{3}$/.test(cur)) err.push("account_currency must be a 3-letter code");
    if (!err.length) {
      const implied = spec.contract_size * spec.tick_size;
      if (cur === "USD" && Math.abs(spec.tick_value - implied) > 0.01 * implied) err.push(`tick_value ${spec.tick_value} does not match contract_size x tick_size = ${+implied.toFixed(10)} for a USD account`);
      if (cur !== "USD") warn.push(`${cur} account: the tick value moves with the ${cur}/USD rate; re-read it from MT5 when it changes`);
      if (spec.pip_size < spec.tick_size) err.push("pip_size cannot be smaller than tick_size");
      if (spec.volume_step > spec.volume_min + 1e-12 && Math.abs(Math.round(spec.volume_min / spec.volume_step) * spec.volume_step - spec.volume_min) > 1e-9) warn.push("volume_min is not a multiple of volume_step");
    }
    return { ok: !err.length, errors: err, warnings: warn };
  }
  const moneyPerPrice = (spec, lots) => (lots * spec.tick_value) / spec.tick_size;
  const priceToMoney = (spec, move, lots) => move * moneyPerPrice(spec, lots);
  const moneyToPrice = (spec, money, lots) => { const m = moneyPerPrice(spec, lots); return m > 0 ? money / m : NaN; };
  const toPips = (spec, move) => move / spec.pip_size;
  const toPoints = (spec, move) => move / spec.tick_size;
  function lotsForRisk(spec, riskMoney, stopMove, costPerPrice = 0) {
    const perLot = (stopMove + costPerPrice) * moneyPerPrice(spec, 1);
    if (!(perLot > 0) || !(riskMoney > 0)) return 0;
    const lots = Math.floor(riskMoney / perLot / spec.volume_step + 1e-9) * spec.volume_step;
    return lots >= spec.volume_min - 1e-12 ? Math.round(lots * 1e8) / 1e8 : 0;
  }
  function tradeMoney(spec, lots, tpMove, slMove, costPerPrice) {
    const m = moneyPerPrice(spec, lots), cost = costPerPrice * m;
    return { money_per_price: m, gross_tp: tpMove * m, gross_sl: -slMove * m, cost, net_tp: tpMove * m - cost, net_sl: -slMove * m - cost,
      tp_pips: toPips(spec, tpMove), sl_pips: toPips(spec, slMove), tp_points: toPoints(spec, tpMove), sl_points: toPoints(spec, slMove),
      break_even: tpMove + slMove > 0 ? (slMove + costPerPrice) / (tpMove + slMove) : NaN };
  }
  // round-trip cost in PRICE units for the viewer's profile and contract: (spread + 2 x slippage) x news + commission / money per 1.00
  function costPerPrice(p, price, engineSpread, conservative = true, newsMult = 1, spec = DEFAULT_SPEC) {
    const spread = p.spread.mode === "engine" ? engineSpread : Number(p.spread.value);
    const m = newsMult >= 1 ? newsMult : 1;
    return (spread + 2 * Number(p.slippage)) * m + commissionPerLot(p, price, conservative) / moneyPerPrice(spec, 1);
  }
  /* The nine-layer approval (mirrors quantum/confirm.approve; parity-tested on the same inputs). */
  const HC_MIN_N = 184, HC_COST_RED = 25;
  function hcApprove(x) {
    const layers = [], L = (id, name, state, detail) => layers.push({ id, name, state, detail });
    const dq = x.data, d = Math.trunc(x.signal.dir), tp = +x.profile.tp, sl = +x.profile.sl, cost = +x.cost_px;
    if (dq.status === "UNAVAILABLE") L(1, "Data quality", "fail", (dq.reasons && dq.reasons.length ? dq.reasons : ["data unavailable"]).join("; "));
    else if (!x.market_open) L(1, "Data quality", "fail", "market closed");
    else L(1, "Data quality", dq.status === "OK" ? "pass" : "warn", (dq.reasons || []).join("; ") || "current and consistent");
    if (x.regime === "ABNORMAL") L(2, "Market regime", "warn", "ABNORMAL volatility (the engine halves size here); suitability by regime not measured");
    else L(2, "Market regime", "info", `${x.regime}; suitability by regime not measured (no regime showed an edge)`);
    if (d === 0) L(3, "Directional evidence", "wait", "no engine BUY / SELL on the last closed bar");
    else {
      const avail = Object.entries(x.htf || {}).filter(([, v]) => v !== null && v !== undefined);
      const against = avail.filter(([, v]) => v === -d).map(([k]) => k);
      const side = d > 0 ? "BUY" : "SELL";
      if (avail.length >= 2 && against.length === avail.length) L(3, "Directional evidence", "warn", `engine ${side}; ${against.join(" and ")} trend against it`);
      else L(3, "Directional evidence", "pass", `engine ${side}` + (against.length ? `; ${against.join(", ")} against` : ""));
      const bs = Math.trunc(x.signal.bars_since);
      L(4, "Entry quality", bs > 0 ? "fail" : "pass", bs > 0 ? `late: the signal bar closed ${bs} bar(s) ago` : "entry at the signal bar's close");
      const la = x.level_ahead;
      if (la && la.dist < tp) L(5, "Target feasibility", "warn", `${la.name} is ${la.dist.toFixed(2)} away, before the TP (${tp.toFixed(2)})`);
      else L(5, "Target feasibility", "pass", !la ? `no engine level before the TP (${tp.toFixed(2)})` : `nearest opposing level ${la.name} ${la.dist.toFixed(2)} away`);
    }
    const be = tp + sl > 0 ? (sl + cost) / (tp + sl) : NaN;
    const r = x.race;
    let prob = null;
    if (r && r.n > 0) { const [lo, hi] = wilson(r.win, r.n); prob = { p: r.win / r.n, lo, hi, n: r.n, random: r.random, sample: r.sample || "in-sample" }; }
    const meas = prob ? `measured ${(prob.p * 100).toFixed(1)}% [${(prob.lo * 100).toFixed(0)}-${(prob.hi * 100).toFixed(0)}] n ${prob.n} (${prob.sample})` : "no measurement";
    if (!x.model.validated) L(6, "Probability validation", "not_validated", `no validated TP-first model; ${meas}`);
    else if (!prob || prob.n < HC_MIN_N) L(6, "Probability validation", "insufficient", `${prob ? prob.n : 0} comparable cases; ${HC_MIN_N} needed`);
    else if (prob.lo < Math.max(be, x.target)) L(6, "Probability validation", "fail", `${meas}: lower bound below ${(Math.max(be, x.target) * 100).toFixed(0)}%`);
    else L(6, "Probability validation", "pass", meas);
    const costPct = x.atr > 0 ? (cost / x.atr) * 100 : NaN, why = [];
    if (x.news && x.news.in_window) why.push("inside a high-impact news window");
    if (isFinite(costPct) && costPct > HC_COST_RED) why.push(`costs ${costPct.toFixed(0)}% of 1 ATR (limit ${HC_COST_RED}%)`);
    L(7, "Execution", why.length ? "fail" : "pass", why.join("; ") || (isFinite(costPct) ? `costs ${costPct.toFixed(0)}% of 1 ATR; spread modelled` : "spread modelled"));
    const rl = x.risk_lock;
    L(8, "Risk", rl === null || rl === undefined || rl ? "fail" : "pass", rl === null || rl === undefined ? "risk state unavailable" : rl ? "engine risk lock (daily loss or drawdown limit)" : "within the engine's daily loss and drawdown limits");
    const st = Object.fromEntries(layers.map((l) => [l.id, l.state]));
    let status;
    if (st[1] === "fail") status = dq.status === "UNAVAILABLE" ? "DATA UNAVAILABLE" : "NO TRADE";
    else if (d === 0) status = "WAIT FOR CONFIRMATION";
    else if ([4, 7, 8].some((k) => st[k] === "fail")) status = "NO TRADE";
    else if (st[6] === "not_validated") status = "MODEL NOT VALIDATED";
    else if (st[6] === "insufficient") status = "INSUFFICIENT EVIDENCE";
    else if (st[6] === "fail") status = "NO TRADE";
    else status = d > 0 ? "CONFIRMED BUY" : "CONFIRMED SELL";
    const reasons = layers.filter((l) => ["fail", "not_validated", "insufficient", "wait", "warn"].includes(l.state)).map((l) => `L${l.id} ${l.name}: ${l.detail}`);
    L(9, "Final", status.startsWith("CONFIRMED") ? "pass" : "fail", status);
    return { status, direction: d, layers, break_even: be, target: x.target, probability: prob, reasons };
  }
  const api = { OZ, sides, commissionPerLot, costPerOz, newsState, wilson, tradeMath, raceIndex, raceCell, matchedRandom,
    DEFAULT_SPEC, specValidate, moneyPerPrice, priceToMoney, moneyToPrice, toPips, toPoints, lotsForRisk, tradeMoney, costPerPrice, hcApprove };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.QCosts = api;
})(typeof window !== "undefined" ? window : globalThis);
