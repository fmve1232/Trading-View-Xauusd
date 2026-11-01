// node --test tests/costs.test.mjs : site/costs.js must give the same numbers as quantum/cost_profiles.py
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
const require = createRequire(import.meta.url);
const C = require("../site/costs.js");

test("JS sizing costs equal the Python profiles for every profile", () => {
  const py = JSON.parse(execFileSync("python3", ["-c", `
import json
from quantum import cost_profiles as cp
out=[]
for p in cp.export():
    for price in (4000.0, 4466.22):
        for sp in (0.30, 0.50):
            for nm in (1.0, 3.0):
                out.append(dict(p=p, price=price, sp=sp, nm=nm, comm=cp.commission_per_lot(p, price), oz=cp.round_trip_cost_per_oz(p, price, sp, True, nm)))
print(json.dumps(out))`], { cwd: new URL("..", import.meta.url).pathname }).toString());
  assert.ok(py.length >= 40);
  for (const r of py) {
    assert.ok(Math.abs(C.commissionPerLot(r.p, r.price) - r.comm) < 1e-9, r.p.id);
    assert.ok(Math.abs(C.costPerOz(r.p, r.price, r.sp, true, r.nm) - r.oz) < 1e-9, r.p.id);
  }
});

test("unconfirmed basis sizes on the higher reading", () => {
  const p = { commission: { type: "fixed", rate: 5, basis: "unconfirmed" }, spread: { mode: "engine" }, slippage: 0.2 };
  assert.equal(C.commissionPerLot(p, 4000), 10);
  assert.equal(C.commissionPerLot(p, 4000, false), 5);
  assert.ok(Math.abs(C.costPerOz(p, 4000, 0.3) - 0.8) < 1e-12);
});

test("news multiplier widens spread + slippage only; Wilson and window state", () => {
  const p = { commission: { type: "fixed", rate: 7, basis: "round_turn" }, spread: { mode: "engine" }, slippage: 0.2 };
  assert.ok(Math.abs(C.costPerOz(p, 4000, 0.3, true, 3) - ((0.3 + 0.4) * 3 + 0.07)) < 1e-12);
  assert.ok(Math.abs(C.costPerOz(p, 4000, 0.3, true, 0.5) - 0.77) < 1e-12);      // < 1 is ignored
  const [lo, hi] = C.wilson(30, 50);
  assert.ok(Math.abs(lo - 0.4618) < 1e-3 && hi > 0.72 && hi < 0.74);
  const news = { before_min: 30, after_min: 30, events: [{ t: 1000000, name: "NFP" }, { t: 2000000, name: "CPI" }] };
  assert.equal(C.newsState(news, 1000000 - 1800).in_window.name, "NFP");
  assert.equal(C.newsState(news, 1000000 + 1801).in_window, null);
  assert.equal(C.newsState(news, 1000000 + 1801).next.name, "CPI");
});

test("Your trade: dollars to price, cost, break-even (SL $500 / TP $1,000 / TP $100 at 0.5 lot)", () => {
  const T = C.tradeMath(500, 1000, 0.5, 0.77);
  assert.equal(T.oz, 50);
  assert.ok(Math.abs(T.sl - 10) < 1e-12 && Math.abs(T.tp - 20) < 1e-12);
  assert.ok(Math.abs(T.cost - 38.5) < 1e-9);
  assert.ok(Math.abs(T.be - (500 + 38.5) / 1500) < 1e-12);         // 35.9%
  const U = C.tradeMath(500, 100, 0.5, 0.77);
  assert.ok(Math.abs(U.tp - 2) < 1e-12 && Math.abs(U.be - 538.5 / 600) < 1e-12);   // 89.75%
  assert.equal(C.tradeMath(0, 100, 0.5, 0.77), null);
  assert.equal(C.tradeMath(500, 100, 0, 0.77), null);
  assert.ok(Number.isNaN(C.tradeMath(500, 100, 0.5, NaN).be));
});

test("Your trade: an off-grid trade is read on a stricter cell (harder TP, tighter SL)", () => {
  const R = { tp_grid: [1, 2, 3, 4], sl_grid: [2, 5, 10, 20] };
  assert.deepEqual(C.raceIndex(R, 2, 10), { i: 1, j: 2, tp: 2, sl: 10, exact: true });
  const x = C.raceIndex(R, 2.3, 9);                                  // TP 2.3 -> 3 (harder), SL 9 -> 5 (tighter)
  assert.equal(x.tp, 3); assert.equal(x.sl, 5); assert.equal(x.exact, false);
  assert.equal(C.raceIndex(R, 5, 10), null);                         // TP beyond the grid
  assert.equal(C.raceIndex(R, 2, 1), null);                          // SL inside the smallest
  assert.equal(C.raceIndex(R, 2.0000000001, 10).exact, true);         // float noise from $ / oz
});

test("Your trade: cell arithmetic and the direction-matched random baseline", () => {
  const ix = { i: 0, j: 0 };
  const src = { n: 10, long: 6, short: 4, win: [[7]], loss: [[2]], mark: [[1.5]] };
  const c = C.raceCell(src, ix, 1000, 500, 50, 40);
  assert.equal(c.open, 1); assert.equal(c.p, 0.7);
  assert.ok(Math.abs(c.ev - ((7 * 1000 - 2 * 500 + 1.5 * 50) / 10 - 40)) < 1e-9);
  const R = { random: { long: { n: 100, win: [[40]], loss: [[60]], mark: [[0]] }, short: { n: 100, win: [[20]], loss: [[80]], mark: [[0]] } } };
  const m = C.matchedRandom(R, src, ix, 1000, 500, 50, 40);
  assert.ok(Math.abs(m.p - (6 * 0.4 + 4 * 0.2) / 10) < 1e-12);
  const onlyShort = C.matchedRandom(R, { long: 0, short: 5 }, ix, 1000, 500, 50, 40);
  assert.ok(Math.abs(onlyShort.p - 0.2) < 1e-12);
  assert.ok(Number.isNaN(C.matchedRandom(R, { long: 0, short: 0 }, ix, 1000, 500, 50, 40).p));
  assert.ok(Number.isNaN(C.raceCell({ n: 0, win: [[0]], loss: [[0]], mark: [[0]] }, ix, 1, 1, 1, 0).ev));
});
