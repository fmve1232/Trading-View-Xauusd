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
  function costPerOz(p, price, engineSpread, conservative = true) {
    const spread = p.spread.mode === "engine" ? engineSpread : Number(p.spread.value);
    return spread + 2 * Number(p.slippage) + commissionPerLot(p, price, conservative) / OZ;
  }
  const api = { OZ, sides, commissionPerLot, costPerOz };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.QCosts = api;
})(typeof window !== "undefined" ? window : globalThis);
