#!/usr/bin/env python3
"""v76: the H2 card's signal age / outcome / STALE marking, EXECUTED as written (display only).

Runs Visuals' v76 block line by line with pine_exec, bar by bar over random price paths with random H2 signals and
trend votes, against an independent Python reference of the rule stated in its comment:
  outcome  after the signal bar, each confirmed bar: stop first if touched (also when a target is touched in the same
           bar), else TP2, else TP1; after TP1 a stop reads "TP1 hit, then stop"; a closed signal is not re-evaluated
  stale    closed (stopped / TP2 / TP1-then-stop), older than h2StaleBars bars, or the 1H/4H/1D vote no longer agrees
  state    0 none, 1 live BUY, -1 live SELL, 2 stale; the status line carries the age, the outcome and the trend note
It also checks the H2 block is not touched by the change (h2_parity.py checks it byte for byte).
Usage: python3 audit/tools/h2_age_check.py"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402

V = open("artefacts/XAUUSD_Quantum_5_5_Visuals.pine", encoding="utf-8").read().split("\n")
a = next(i for i, l in enumerate(V) if l.startswith("var int h2SigBar = na"))
b = next(i for i, l in enumerate(V) if l.startswith("string h2SigStat = "))
VARS = [l for l in V[a:b + 1] if l.startswith("var ")]
STEP = [l for l in V[a:b + 1] if not l.startswith("var ")]
assert len(VARS) == 7 and STEP[0].startswith("if h2Long or h2Short")


def ref(path, stale_bars):
    """independent reference: returns the (state, outcome, ageB, agrees) after each bar"""
    out, sig = [], None
    for k, bar in enumerate(path):
        if bar["long"] or bar["short"]:
            sig = {"bar": k, "dir": 1 if bar["long"] else -1, "sl": bar["sl"], "t1": bar["t1"], "t2": bar["t2"], "out": ""}
        elif sig and bar["conf"] and sig["out"] not in ("stopped", "TP2 hit", "TP1 hit, then stop"):
            d = sig["dir"]
            sl = bar["low"] <= sig["sl"] if d == 1 else bar["high"] >= sig["sl"]
            t1 = bar["high"] >= sig["t1"] if d == 1 else bar["low"] <= sig["t1"]
            t2 = bar["high"] >= sig["t2"] if d == 1 else bar["low"] <= sig["t2"]
            if sl:
                sig["out"] = "TP1 hit, then stop" if sig["out"] == "TP1 hit" else "stopped"
            elif t2:
                sig["out"] = "TP2 hit"
            elif t1:
                sig["out"] = "TP1 hit"
        if not sig:
            out.append((0, "", None, True))
            continue
        age = k - sig["bar"]
        agrees = bar["up"] if sig["dir"] == 1 else bar["dn"]
        done = sig["out"] in ("stopped", "TP2 hit", "TP1 hit, then stop")
        stale = done or age > stale_bars or not agrees
        out.append((2 if stale else sig["dir"], sig["out"], age, agrees))
    return out


rng = random.Random(76)
bad = n = 0
outcomes = set()
for trial in range(400):
    stale_bars = rng.choice([1, 3, 24, 200])
    px, path = 4150.0, []
    for k in range(rng.randint(20, 80)):
        o = px
        c = o + rng.gauss(0, 3)
        hi, lo = max(o, c) + abs(rng.gauss(0, 2)), min(o, c) - abs(rng.gauss(0, 2))
        px = c
        sig = rng.random() < 0.06
        lg = sig and rng.random() < 0.5
        sh = sig and not lg
        r = abs(rng.gauss(4, 2)) + 0.5
        sl = c - r if lg else c + r
        t1 = c + r if lg else c - r
        t2 = c + 2 * r if lg else c - 2 * r
        path.append({"open": o, "high": hi, "low": lo, "close": c, "long": lg, "short": sh, "sl": sl, "t1": t1, "t2": t2,
                     "conf": rng.random() < 0.9, "up": rng.random() < 0.5, "dn": rng.random() < 0.5})
    want = ref(path, stale_bars)
    env = P.Env(h2StaleBars=float(stale_bars))
    P.run(VARS, env)
    for k, bar in enumerate(path):
        env.update({"bar_index": float(k), "time": float(k) * 900000.0, "high": bar["high"], "low": bar["low"],
                    "close": bar["close"], "h2Long": bar["long"], "h2Short": bar["short"], "h2Sl": bar["sl"],
                    "h2Tp1": bar["t1"], "h2Tp2": bar["t2"], "barstate.isconfirmed": bar["conf"],
                    "h2TrendUp": bar["up"], "h2TrendDn": bar["dn"]})
        P.run(STEP, env)
        st, oc, age, agrees = want[k]
        got = (int(env["h2SigState"]), env["h2SigOut"])
        n += 1
        outcomes.add(oc)
        stat = env["h2SigStat"]
        ok = got == (st, oc)
        if st != 0:
            ok = ok and (("○ STALE" in stat) == (st == 2)) and (oc == "" or (" · " + oc) in stat) \
                 and (("trend no longer" in stat) == (not agrees)) and ("this bar" in stat) == (age == 0)
        else:
            ok = ok and stat == ""
        bad += not ok
        if not ok and bad <= 3:
            print("   mismatch trial", trial, "bar", k, "want", want[k], "got", got, repr(stat))
print(f"{'PASS' if bad == 0 else 'FAIL'}  H2 signal age / outcome / STALE, Visuals v76 block executed vs reference: "
      f"{n} bars, mismatches {bad}; outcomes seen {sorted(outcomes)}")
cover = {"", "TP1 hit", "TP2 hit", "stopped", "TP1 hit, then stop"} <= outcomes
print(f"{'PASS' if cover else 'FAIL'}  every outcome exercised")
print(f"RESULT: {'PASS' if bad == 0 and cover else 'FAIL'} -- Pine text executed in Python; TradingView runtime NOT exercised")
sys.exit(0 if bad == 0 and cover else 1)
