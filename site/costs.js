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
  const api = { OZ, sides, commissionPerLot, costPerOz, newsState, wilson };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.QCosts = api;
})(typeof window !== "undefined" ? window : globalThis);
