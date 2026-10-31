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
