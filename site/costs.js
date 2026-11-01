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
  const api = { OZ, sides, commissionPerLot, costPerOz, newsState, wilson, tradeMath, raceIndex, raceCell, matchedRandom };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.QCosts = api;
})(typeof window !== "undefined" ? window : globalThis);
