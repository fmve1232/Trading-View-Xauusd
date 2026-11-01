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

test("contract maths in the page equal quantum/contract.py (parity)", () => {
  const py = JSON.parse(execFileSync("python3", ["-c", `
import json, math
from quantum import contract as C
S = dict(C.DEFAULT_SPEC)
specs = [S, {**S, "contract_size": 50.0, "tick_value": 0.5}, {**S, "account_currency": "EUR", "tick_value": 0.86}, {**S, "tick_value": 2.0},
         {**S, "pip_size": 0.01}, {**S, "contract_size": 0}, {**S, "volume_step": 0.1, "volume_min": 0.1}]
out = []
for sp in specs:
    v = C.validate(sp)
    row = {"spec": sp, "ok": v["ok"], "nerr": len(v["errors"]), "nwarn": len(v["warnings"])}
    if v["ok"]:
        row.update(m=C.money_per_price(sp, 0.5), p=C.money_to_price(sp, 1000.0, 0.5), pips=C.to_pips(sp, 10.0), pts=C.to_points(sp, 10.0),
                   lots=C.lots_for_risk(sp, 1000.0, 10.0, 0.97), tm=C.trade_money(sp, 0.5, 15.0, 10.0, 0.97))
    out.append(row)
print(json.dumps(out))`], { cwd: new URL("..", import.meta.url).pathname }).toString());
  assert.equal(py.length, 7);
  for (const r of py) {
    const v = C.specValidate(r.spec);
    assert.equal(v.ok, r.ok, JSON.stringify(r.spec)); assert.equal(v.errors.length, r.nerr); assert.equal(v.warnings.length, r.nwarn);
    if (!r.ok) continue;
    const close = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} vs ${b}`);
    close(C.moneyPerPrice(r.spec, 0.5), r.m); close(C.moneyToPrice(r.spec, 1000, 0.5), r.p);
    close(C.toPips(r.spec, 10), r.pips); close(C.toPoints(r.spec, 10), r.pts); close(C.lotsForRisk(r.spec, 1000, 10, 0.97), r.lots);
    const tm = C.tradeMoney(r.spec, 0.5, 15, 10, 0.97);
    for (const k of Object.keys(r.tm)) close(tm[k], r.tm[k]);
  }
});

test("the page's nine-layer approval equals quantum/confirm.approve on the same inputs (parity)", () => {
  const py = JSON.parse(execFileSync("python3", ["-c", `
import json, random
from quantum import confirm
rnd = random.Random(11)
cases = []
for k in range(400):
    x = {"data": {"status": rnd.choice(["OK", "OK", "DEGRADED", "UNAVAILABLE"]), "reasons": ["r"] if rnd.random() < 0.5 else []},
         "market_open": rnd.random() < 0.85, "regime": rnd.choice(["RANGE", "ABNORMAL", "STRONG TR", "WEAK TR"]),
         "signal": {"dir": rnd.choice([-1, 0, 1, 1]), "bars_since": rnd.choice([0, 0, 0, 1, 3])},
         "htf": {"4H": rnd.choice([-1, 0, 1, None]), "1H": rnd.choice([-1, 0, 1, None])},
         "profile": {"tp": rnd.choice([10.0, 15.0, 20.0, 12.5]), "sl": rnd.choice([10.0, 20.0])},
         "level_ahead": rnd.choice([None, {"name": "PDH", "dist": round(rnd.uniform(0.5, 30), 3)}]),
         "cost_px": round(rnd.uniform(0.3, 2.5), 3), "atr": round(rnd.uniform(1, 12), 3), "news": {"in_window": rnd.random() < 0.15},
         "risk_lock": rnd.choice([False, False, True, None]), "model": {"validated": rnd.random() < 0.5}, "target": 0.9,
         "race": None}
    if rnd.random() < 0.8:
        n = rnd.choice([0, 20, 150, 184, 400, 2000]); x["race"] = {"n": n, "win": int(n * rnd.choice([0.3, 0.5, 0.9, 0.93, 0.97])), "random": 0.5}
    out = confirm.approve(x)
    cases.append({"x": x, "status": out["status"], "states": [[l["id"], l["state"]] for l in out["layers"]], "be": out["break_even"],
                  "lo": out["probability"]["lo"] if out["probability"] else None, "nreasons": len(out["reasons"])})
print(json.dumps(cases))`], { cwd: new URL("..", import.meta.url).pathname }).toString());
  assert.equal(py.length, 400);
  const seen = new Set();
  for (const c of py) {
    const o = C.hcApprove(c.x);
    assert.equal(o.status, c.status, JSON.stringify(c.x));
    assert.deepEqual(o.layers.map((l) => [l.id, l.state]), c.states);
    assert.ok(Math.abs(o.break_even - c.be) < 1e-12);
    if (c.lo === null) assert.equal(o.probability, null); else assert.ok(Math.abs(o.probability.lo - c.lo) < 1e-12);
    assert.equal(o.reasons.length, c.nreasons);
    seen.add(o.status);
  }
  for (const s of ["DATA UNAVAILABLE", "NO TRADE", "WAIT FOR CONFIRMATION", "MODEL NOT VALIDATED", "INSUFFICIENT EVIDENCE"]) assert.ok(seen.has(s), s);
});
