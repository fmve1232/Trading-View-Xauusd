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
            out.append(dict(p=p, price=price, sp=sp, comm=cp.commission_per_lot(p, price), oz=cp.round_trip_cost_per_oz(p, price, sp)))
print(json.dumps(out))`], { cwd: new URL("..", import.meta.url).pathname }).toString());
  assert.ok(py.length >= 40);
  for (const r of py) {
    assert.ok(Math.abs(C.commissionPerLot(r.p, r.price) - r.comm) < 1e-9, r.p.id);
    assert.ok(Math.abs(C.costPerOz(r.p, r.price, r.sp) - r.oz) < 1e-9, r.p.id);
  }
});

test("unconfirmed basis sizes on the higher reading", () => {
  const p = { commission: { type: "fixed", rate: 5, basis: "unconfirmed" }, spread: { mode: "engine" }, slippage: 0.2 };
  assert.equal(C.commissionPerLot(p, 4000), 10);
  assert.equal(C.commissionPerLot(p, 4000, false), 5);
  assert.ok(Math.abs(C.costPerOz(p, 4000, 0.3) - 0.8) < 1e-12);
});
