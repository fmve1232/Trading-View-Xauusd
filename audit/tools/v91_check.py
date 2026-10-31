#!/usr/bin/env python3
"""v91 (B-01, B-02 of the independent v90 audit, operator-approved 2026-10-31), EXECUTED as written (pine_exec).

1 identical output: the v91 sizing lines vs the v90 lines WITH the v91 cost term inserted (so only the three removed
  guards differ: pointValue > 0, math.max(_kellyPct, 0.0), math.max(_lotsFloored, 0.0)), on the inputs' own domain:
  pointValue >= 1 (minval), _kellyPct >= 0 or na (every write is >= 0), regSizeMult in {0.5, 0.75, 1}, any stop
2 the ceiling: v91 lots x (stop + cost) x $/pt <= the stated $ risk on every case; the v90 lines exceed it on some
  (positive control: the defect the change removes is still detectable)
3 the cost: _liveCostATR x adaptiveATR (v91) == the plan's own cost (the Master's _cR line x stop) in every session
  state, and the v90 line differs in the Asian / off-session tier (positive control)
4 one account default: the Master's accountSize == Visuals' rkEquity (25,000), and accountSize is outside the
  DECISION slice (v90_slice.py), so it is display only
5 the Master == fix_v91.master(v90 Master), byte for byte
Usage: python3 audit/tools/v91_check.py"""
import os, random, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402
import fix_v91 as F91  # noqa: E402

M = "artefacts/XAUUSD_Quantum_5_0_Master.pine"
V90 = "ff9536959"
now = open(M, encoding="utf-8").read()
old = subprocess.run(["git", "show", f"{V90}:{M}"], capture_output=True, text=True, check=True).stdout
fails = 0


def report(ok, msg):
    global fails
    print(("PASS  " if ok else "FAIL  ") + msg)
    fails += not ok


def block(text, first, last):
    L = text.split("\n")
    a = next(i for i, l in enumerate(L) if l.strip().startswith(first))
    b = next(i for i in range(a, len(L)) if L[i].strip().startswith(last))
    return [l.strip() for l in L[a:b + 1] if l.strip() and not l.strip().startswith("//")]


NEWB = block(now, "float _riskUSD = accountSize", "float _lots = ")
OLDB = block(old, "float _riskUSD = accountSize", "float _lots = ")
OLDC = [l.replace("_riskUSD / (tpDist * pointValue)", "_riskUSD / ((tpDist + _liveCostATR * adaptiveATR) * pointValue)") for l in OLDB]
assert OLDC != OLDB, "v90 lot line not found"
rng = random.Random(91)
bad1 = over_new = over_old = n = 0
for _ in range(30000):
    st = dict(accountSize=rng.choice([100.0, 1e4, 2.5e4, 1e6, rng.uniform(100, 5e6)]),
              _kellyPct=P.NA if rng.random() < .03 else rng.choice([0.0, 0.05, 0.5, 1.0, rng.uniform(0, 2)]),
              regSizeMult=rng.choice([0.5, 0.75, 1.0]), pointValue=rng.choice([1.0, 100.0, rng.uniform(1, 500)]),
              tpDist=P.NA if rng.random() < .03 else rng.choice([0.0, 0.01, rng.uniform(0.05, 80)]),
              adaptiveATR=rng.uniform(0.3, 40), _liveCostATR=rng.uniform(0, 1.5))
    eN, eC, eO = P.Env(**st), P.Env(**st), P.Env(**st)
    P.run(NEWB, eN); P.run(OLDC, eC); P.run(OLDB, eO)
    n += 1
    same = all((P.isna(eN[k]) and P.isna(eC[k])) or eN[k] == eC[k] for k in ("_riskUSD", "_rawLots", "_lotsFloored", "_lotsBelowMin", "_lots"))
    bad1 += not same
    if not P.isna(eN["_lots"]) and not P.isna(st["tpDist"]) and not P.isna(st["_kellyPct"]):
        cost = st["_liveCostATR"] * st["adaptiveATR"]
        risk = eN["_riskUSD"]
        over_new += eN["_lots"] * (st["tpDist"] + cost) * st["pointValue"] > risk * (1 + 1e-9) + 1e-9
        over_old += eO["_lots"] * (st["tpDist"] + cost) * st["pointValue"] > risk * (1 + 1e-9) + 1e-9
report(bad1 == 0, f"1 identical output: v91 sizing lines == v90 lines + the cost term (only the 3 redundant guards removed), {n} cases "
       f"on the inputs' domain incl. na / zero stop / Kelly 0: mismatches {bad1}")
report(over_new == 0 and over_old > 0, f"2 ceiling: loss at the stop incl. round-trip cost <= stated risk: v91 exceeds it in {over_new} cases; "
       f"v90 in {over_old} (positive control)")

cr = next(l.strip() for l in now.split("\n") if l.strip().startswith("float _cR = ((_sessSpread + 2.0 * slippagePts)"))
cr_e = cr.split("=", 1)[1].strip()
lc_new = next(l for l in now.split("\n") if l.startswith("float _liveCostATR = ")).split("=", 1)[1].strip()
lc_old = next(l for l in old.split("\n") if l.startswith("float _liveCostATR = ")).split("=", 1)[1].strip()
bad3 = diff_old = 0
for _ in range(5000):
    st = dict(spreadCost=rng.choice([0.0, 0.1, 0.3, 0.5, rng.uniform(0, 5)]), slippagePts=rng.choice([0.0, 0.2, rng.uniform(0, 2)]),
              commissionL=rng.choice([0.0, 7.0, rng.uniform(0, 50)]), pointValue=rng.choice([1.0, 100.0, rng.uniform(1, 500)]),
              adaptiveATR=rng.uniform(0.3, 40), tpDist=rng.uniform(0.1, 60))
    st["_sessSpread"] = rng.choice([max(0.18, st["spreadCost"]), max(0.22, st["spreadCost"]), max(0.30, st["spreadCost"]), max(0.50, st["spreadCost"])])
    plan = P.evaluate(cr_e, P.Env(**st)) * st["tpDist"]
    got = P.evaluate(lc_new, P.Env(**st)) * st["adaptiveATR"]
    was = P.evaluate(lc_old, P.Env(**st)) * st["adaptiveATR"]
    bad3 += abs(got - plan) > 1e-9 * max(1, plan)
    diff_old += abs(was - plan) > 1e-9 * max(1, plan)
report(bad3 == 0 and diff_old > 0, f"3 cost: v91 _liveCostATR x ATR == the plan's _cR x stop in every session tier, mismatches {bad3}; "
       f"v90 differed in {diff_old} / 5000 (positive control: the flat spread)")

V = open("artefacts/XAUUSD_Quantum_5_5_Visuals.pine", encoding="utf-8").read()
am = re.search(r'^accountSize = input\.float\(([\d.]+),', now, re.M)
rv = re.search(r'^rkEquity = input\.float\(([\d.]+),', V, re.M)
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "v90_slice.py")).read().split("# ---- per-section")[0]
ns = {"__file__": os.path.join(os.path.dirname(os.path.abspath(__file__)), "v90_slice.py"), "__name__": "x"}
import contextlib, io  # noqa: E402
_argv = sys.argv
sys.argv = ["x"]
with contextlib.redirect_stdout(io.StringIO()):
    exec(src, ns)
sys.argv = _argv
disp = not any(v in ns["seen"] for v in ("accountSize", "_riskUSD", "_rawLots", "_lots", "_liveCostATR"))
report(am and rv and float(am.group(1)) == float(rv.group(1)) == 25000.0 and disp,
       f"4 one account default: Master accountSize {am.group(1) if am else '?'} == Visuals rkEquity {rv.group(1) if rv else '?'}; "
       f"accountSize / _riskUSD / _rawLots / _lots / _liveCostATR outside the DECISION slice: {disp}")
report(F91.master(old) == now, "5 Master == fix_v91.master(v90 Master @ ff9536959), byte for byte")
print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- Pine text executed in Python; TradingView runtime NOT exercised")
sys.exit(1 if fails else 0)
