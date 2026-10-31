#!/usr/bin/env python3
"""v92 (B-03, B-09 of the independent v90 audit, operator-approved 2026-10-31), EXECUTED as written (pine_exec).

1 B-09 risk lock after a reload: the Master's recentBars line and its whole risk-tracker block (var slots initialised
  once, the rest run bar by bar) on a synthetic 5m NY day: three losing signals early in the day, the chart "reloaded"
  250 bars later (signals older than 120 bars). backtestAllBars ON (v92 default): the lock is engaged on the last bar,
  as the reference that counts every signal says. OFF (the v91 behaviour): the lock is gone (positive control).
2 B-09 the live bar: recentBars is true on the last bar for every setting, so the DECISION shown is unchanged; the
  Master's backtestAllBars input line is byte-identical to the twins'
3 B-03 news cost: Visuals' ckCost line == (spread + 2 x slippage) x m + commission / $pt inside a news window and the
  v91 cost outside it; the RISK lots are computed on it (smaller in the window); the COST text names the multiplier
  only inside the window
4 identical-output rewrites paying for B-09: `tpDist > 0 and not na(_liveCostATR)` == `tpDist > 0` (the _liveCostATR
  line as written never returns na), and math.abs(tpSL - tpEntry) == tpDist (f_tradePlan's own line), na included
5 Master == fix_v92.master(v91 Master), Visuals == fix_v92.visuals(v91 Visuals), byte for byte
Usage: python3 audit/tools/v92_check.py"""
import os, random, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402
import fix_v92 as F92  # noqa: E402

M, V, S = ("artefacts/XAUUSD_Quantum_5_0_Master.pine", "artefacts/XAUUSD_Quantum_5_5_Visuals.pine",
           "artefacts/XAUUSD_Quantum_5_0_Strategy.pine")
V91 = "1888cd6bd"
ML = open(M, encoding="utf-8").read().split("\n")
VL = open(V, encoding="utf-8").read().split("\n")
fails = 0


def report(ok, msg):
    global fails
    print(("PASS  " if ok else "FAIL  ") + msg)
    fails += not ok


# ---- 1 / 2
rb = next(l for l in ML if l.startswith("recentBars = "))
a = next(i for i, l in enumerate(ML) if l.startswith("var float rkEntry = na"))
b = next(i for i in range(a, len(ML)) if ML[i].startswith("tqVeto := tqVeto or (useRiskLimits and riskLock)"))
blk = [l for l in ML[a:b + 1] if l.strip() and not l.strip().startswith("//")]
VARS = [l for l in blk if l.startswith("var ")]
BODY = [l.replace("barstate.isconfirmed", "isConf") for l in blk if not l.startswith("var ")]
inputs = {k: float(re.search(rf"^{k}\s*=\s*input\.\w+\(([\d.]+)", "\n".join(ML), re.M).group(1))
          for k in ("maxDailyLossR", "maxTradesDay", "maxConsecLoss", "lockoutBars", "recentBarsLen")}


def day(setting, n=260, sig=(10, 30, 50, 200)):
    env = P.Env(useRiskLimits=True, perfMode=True, mt5Offset=0.0, isConf=True, adaptiveATR=4.0,
                last_bar_index=float(n - 1), backtestAllBars=setting, **inputs)
    for l in VARS:
        nm = l.split("=")[0].split()[-1]
        env[nm] = P.evaluate(l.split("=", 1)[1].strip(), P.Env())
    for i in range(n):
        env["bar_index"] = float(i)
        P.run([rb], env)
        raw = i in sig
        env.update(crossedNYDay=(i == 0), shouldBuy=raw and env["recentBars"], shouldSell=False, tqVeto=False,
                   close=2000.0, tpSL=1994.0, tp1=2010.0,
                   low=1990.0 if (i - 1) in sig else 1999.0, high=2001.0)
        P.run(BODY, env)
    return env
on, off = day(True), day(False)
report(on["riskLock"] and not off["riskLock"] and on["rkDayR"] <= -3.0,
       f"1 risk lock after a reload (5m day, 3 early losses, reloaded 260 bars in): backtestAllBars ON -> lock "
       f"{on['riskLock']} ({on['riskLockStr']}, day R {on['rkDayR']:+.1f}, the reference); OFF (v91) -> lock {off['riskLock']} "
       f"(day R {off['rkDayR']:+.1f}: the early losses forgotten, positive control)")
live = all(P.evaluate(rb.split("=", 1)[1].strip(), P.Env(backtestAllBars=s_, bar_index=float(k), last_bar_index=float(k),
                                                          recentBarsLen=float(r))) for s_ in (True, False) for k in (0, 50, 5000) for r in (50, 120, 500))
twin = next(l for l in open(S, encoding="utf-8").read().split("\n") if l.startswith("backtestAllBars = "))
mine = next(l for l in ML if l.startswith("backtestAllBars = "))
report(live and twin == mine, f"2 live bar: recentBars true on the last bar for every setting: {live}; the Master's backtestAllBars line == the twins': {twin == mine}")

# ---- 3
ck = next(l for l in VL if l.startswith("float ckCost = ")).split("=", 1)[1].strip()
lots = next(l for l in VL if l.startswith("float rkLots = ")).split("=", 1)[1].strip()
perlot = next(l for l in VL if l.startswith("float rkPerLot = ")).split("=", 1)[1].strip()
rng = random.Random(92)
bad3 = smaller = elig = n3 = 0
for _ in range(4000):
    st = dict(ckSpread=rng.choice([0.18, 0.3, 0.5, rng.uniform(0, 5)]), slippagePts=rng.choice([0.0, 0.2, rng.uniform(0, 2)]),
              commissionL=rng.choice([0.0, 7.0, rng.uniform(0, 50)]), pointValue=rng.choice([1.0, 100.0]),
              nwCostMult=rng.choice([1.0, 3.0, 5.0, rng.uniform(1, 10)]), rkStopD=rng.uniform(0.5, 30), rkRisk=rng.uniform(10, 5000))
    out = {}
    for inwin in (False, True):
        e = P.Env(nwBarIn=inwin, **st)
        c = P.evaluate(ck, e)
        want = (st["ckSpread"] + 2 * st["slippagePts"]) * (st["nwCostMult"] if inwin else 1.0) + st["commissionL"] / max(st["pointValue"], 1.0)
        bad3 += abs(c - want) > 1e-9
        e2 = P.Env(ckCost=c, **st)
        e2["rkPerLot"] = P.evaluate(perlot, e2)
        out[inwin] = P.evaluate(lots, e2)
    n3 += 1
    if st["nwCostMult"] > 1.0 and (st["ckSpread"] + st["slippagePts"]) > 0:
        elig += 1
        smaller += out[True] <= out[False]
cost_row = next(l for l in VL if '"COST"' in l and "_tmRow" in l)
tag = '(nwBarIn and nwCostMult > 1.0 ? " (NEWS ×"' in cost_row
report(bad3 == 0 and tag and smaller == elig and elig > 0, f"3 news cost: ckCost == (spread + 2 slip) x m (in window) / x 1 (outside) + commission, {n3} x 2 cases, "
       f"mismatches {bad3}; RISK lots never larger inside the window ({smaller} / {elig} cases with m > 1); COST row names the multiplier only in the window: {tag}")

# ---- 4
v91m = subprocess.run(["git", "show", f"{V91}:{M}"], capture_output=True, text=True, check=True).stdout
lc = next(l for l in ML if l.startswith("float _liveCostATR = ")).split("=", 1)[1].strip()
nana = sum(P.isna(P.evaluate(lc, P.Env(adaptiveATR=x, _sessSpread=0.3, slippagePts=0.2, commissionL=7.0, pointValue=100.0)))
           for x in (P.NA, 0.0, 1e-9, 0.5, 40.0))
td = next(l.strip() for l in ML if l.strip().startswith("float tpDist = ")).split("=", 1)[1].strip()
bad4 = 0
for _ in range(3000):
    e = P.Env(tpEntry=P.NA if rng.random() < .05 else rng.uniform(1500, 4500), tpSL=P.NA if rng.random() < .05 else rng.uniform(1500, 4500),
              adaptiveATR=rng.uniform(0.3, 40))
    d = P.evaluate(td, e)
    x = P.evaluate("math.abs(tpSL - tpEntry) / adaptiveATR", e)
    y = P.evaluate("tpDist / adaptiveATR", P.Env(tpDist=d, adaptiveATR=e["adaptiveATR"]))
    bad4 += not ((P.isna(x) and P.isna(y)) or x == y)
report(nana == 0 and bad4 == 0, f"4 identical rewrites: the _liveCostATR line returns na in {nana} of 5 states (na / 0 / tiny / normal ATR), so "
       f"`not na(_liveCostATR)` was always true; math.abs(tpSL - tpEntry) / ATR vs tpDist / ATR, 3000 cases incl. na: mismatches {bad4}")

# ---- 5
v91v = subprocess.run(["git", "show", f"{V91}:{V}"], capture_output=True, text=True, check=True).stdout
report(F92.master(v91m) == "\n".join(ML) and F92.visuals(v91v) == "\n".join(VL),
       "5 Master == fix_v92.master(v91), Visuals == fix_v92.visuals(v91), byte for byte")
print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- Pine text executed in Python; TradingView runtime NOT exercised")
sys.exit(1 if fails else 0)
