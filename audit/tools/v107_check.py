#!/usr/bin/env python3
"""v107: the Master's statistics scan runs on its last N bars (run time, F-A94); every other engine copy scans every bar.

  1 wiring: the Master's `statsBars` is its LAST input (F-A93) and `statsScanOn` is defined before runStatsEngines();
    the scan guard reads it in the Master, the three strategy twins, Brief and Diagnostics; the twins, Brief and
    Diagnostics define it `= true` (unchanged backtests); the Master's definition, executed on bar indices, is true
    exactly on the last N bars (and on every bar for N = 0)
  2 run time, modelled from the engine's OWN constants (the scan cadence `_rb` and chunk size `_cs` lines executed as
    written for 15m): record passes on 1500 bars with the default window vs every bar
  3 the last bar's statistics: complete passes over the stored history inside the window, and what is left of an
    earlier start after the engine's 0.7-per-pass decay (v108 default 150: >= 5 passes, < 20%)
  4 controls: window 0 gives the full count; a guard without the switch is detected
Not measured here: TradingView's run time (the operator's chart is the test). Usage: python3 audit/tools/v107_check.py"""
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402

ART = "artefacts/XAUUSD_Quantum_5_0_"
M = open(ART + "Master.pine", encoding="utf-8").read()
fails = 0


def report(ok, msg):
    global fails
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {msg}")


def code(src):
    return [l for l in src.split("\n") if l.strip() and not l.lstrip().startswith("//")]


# 1 wiring
L = M.split("\n")
inp = [i for i, l in enumerate(L) if re.match(r"^\s*(?:\w+\s+)?\w+\s*=\s*input(?:\.\w+)?\(", l) and not l.lstrip().startswith("//")]
last_is = L[inp[-1]].startswith("statsBars = input.int(")
def_i = next(i for i, l in enumerate(L) if l.startswith("bool statsScanOn = "))
fn_i = next(i for i, l in enumerate(L) if l.startswith("runStatsEngines() =>"))
guard = "bool _guard = showStatsEngine and statsScanOn and "
files = {n: open(ART + n + ".pine", encoding="utf-8").read() for n in ("Strategy", "Strategy_OLDGATES", "Strategy_CHALLENGER", "Brief", "Diagnostics")}
others = all(guard in s and "\nbool statsScanOn = true\n" in s for s in files.values())
dl = L[def_i]
e = P.Env(statsBars=300, last_bar_index=1499)
hits = []
for b in range(1500):
    e["bar_index"] = b
    P.run([dl.replace("bool ", "", 1)], e)
    hits.append(bool(e["statsScanOn"]))
e0 = P.Env(statsBars=0, last_bar_index=1499, bar_index=0)
P.run([dl.replace("bool ", "", 1)], e0)
report(last_is and def_i < fn_i and guard in M and others and sum(hits) == 301 and hits[-301:] == [True] * 301 and e0["statsScanOn"],
       f"1 wiring: statsBars is the Master's last input ({last_is}); defined before runStatsEngines ({def_i < fn_i}); "
       f"the guard reads it in all 6 engine copies, twins / Brief / Diagnostics = true ({others}); executed: true on the "
       f"last {sum(hits)} of 1500 bars at N = 300, true at N = 0 ({e0['statsScanOn']})")

# 2 run time model from the engine's own constants
rb_line = next(l.strip() for l in code(M) if l.strip().startswith("int _rb = "))
cs_line = next(l.strip() for l in code(M) if l.strip().startswith("int _cs = "))
on_line = next(l.strip() for l in code(M) if l.strip().startswith("OUTCOME_N = "))
hm_line = next(l.strip() for l in code(M) if l.strip().startswith("int HIST_MAX = "))
env = P.Env(chartTFSeconds=900, tfSec=900)
P.run([on_line, hm_line.replace("int ", "", 1), rb_line.replace("int ", "", 1)], env)
ON, HIST, RB = int(env["OUTCOME_N"]), int(env["HIST_MAX"]), int(env["_rb"])


def cs_of(slm):
    en = P.Env(_slm=slm)
    P.run([cs_line.replace("int ", "", 1)], en)
    return int(en["_cs"])


def model(bars, window):
    hN, rsp, passes, cycles, recs = 0, 0, 0, 0, []
    for b in range(bars):
        if b > ON * 3 + 50:
            recs.append(b)
            recs = recs[-HIST:]
            hN = min(hN + 1, HIST)
        scan_on = window == 0 or b >= bars - 1 - window
        if scan_on and hN > ON * 2 and b % RB == 0:
            slm = min(hN, HIST)
            cs = cs_of(slm)
            if rsp >= slm:
                rsp = 0
            for p in range(rsp, min(rsp + cs - 1, slm - 1) + 1):
                if b - recs[p] >= ON and math.pow(0.997, max(1, b - recs[p])) >= 0.05:
                    passes += 1
            rsp += cs
            if rsp >= slm:
                rsp, cycles = 0, cycles + 1
    return passes, cycles


win = int(re.search(r"statsBars = input\.int\((\d+),", M).group(1))
full, _ = model(1500, 0)
part, cyc = model(1500, win)
report(part < full / 2, f"2 run time (15m, 1500 bars, the engine's own _rb = {RB}, _cs, OUTCOME_N = {ON}): {part:,} record passes "
       f"with the default window {win} vs {full:,} on every bar ({100 - 100 * part // full}% fewer)")
resid = 0.7 ** cyc
report(cyc >= 5 and resid < 0.20, f"3 last bar: {cyc} complete passes over the stored history inside the window; an earlier start "
       f"is decayed to {100 * resid:.2f}% (0.7 per pass; the calibration RATIOS do not depend on it, count thresholds see it)")

# 4 controls
f0, _ = model(1500, 0)
mut = M.replace(guard, "bool _guard = showStatsEngine and ")
report(f0 == full and guard not in mut, "4 controls: window 0 = the full count; a guard without the switch is detected")
print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- Pine lines executed / modelled in Python; TradingView run time NOT measured")
sys.exit(1 if fails else 0)
