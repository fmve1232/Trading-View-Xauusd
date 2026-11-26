#!/usr/bin/env python3
"""v105: the chart scripts calculate on the last 3000 bars (calc_bars_count), so they stay under TradingView's run-time limit.

  1 the four chart scripts (Master, Visuals, Brief, Diagnostics) declare the SAME calc_bars_count; the repo-set
    strategy arms do not (their A/B hunks are unchanged)
  2 the engine fits in it: the longest literal chart-timeframe window (ta.* length, [n] history reference, loop over
    past bars) in every chart script is at most a tenth of it, and the stats ring buffer on 15m (HIST_MAX) is no larger
  3 Brief / Diagnostics carry it through their builders (a rebuild reproduces the files byte for byte)
  4 control: a script without it, and one with a different value, are detected
Not checked here: TradingView's run time itself (only the compiler / chart can measure it; the operator's screenshot is
the test). Usage: python3 audit/tools/v105_check.py"""
import glob
import re
import subprocess
import sys

CHART = ["artefacts/XAUUSD_Quantum_5_0_Master.pine", "artefacts/XAUUSD_Quantum_5_5_Visuals.pine",
         "artefacts/XAUUSD_Quantum_5_0_Brief.pine", "artefacts/XAUUSD_Quantum_5_0_Diagnostics.pine"]
fails = 0


def report(ok, msg):
    global fails
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {msg}")


def decl(src):
    line = next(l for l in src.split("\n") if l.startswith(("indicator(", "strategy(")))
    m = re.search(r"calc_bars_count\s*=\s*(\d+)", line)
    return int(m.group(1)) if m else None


def same(srcs):
    vals = [decl(s) for s in srcs]
    return vals, len(set(vals)) == 1 and vals[0] is not None


src = {p: open(p, encoding="utf-8").read() for p in CHART}
vals, ok = same(src.values())
arms = [p for p in glob.glob("artefacts/*Strategy*.pine") if decl(open(p, encoding="utf-8").read()) is not None]
report(ok and not arms, f"1 chart scripts calc_bars_count {vals}; strategy arms with it: {arms}")
N = vals[0] or 0

worst = (0, "")
for p, s in src.items():
    for l in s.split("\n"):
        code = l.split("//")[0]
        for m in re.finditer(r"ta\.\w+\([^()]*?,\s*(\d+)\s*\)|\[(\d+)\]|for \w+ = (\d+) to 0|for \w+ = 0 to (\d+)\b", code):
            n = int(next(g for g in m.groups() if g))
            if n > worst[0]:
                worst = (n, f"{p.split('_')[-1]}: {code.strip()[:70]}")
hm = re.search(r"int HIST_MAX = .*?tfSec <= 900 \? (\d+)", src[CHART[0]])
report(worst[0] * 10 <= N and hm and int(hm.group(1)) <= N,
       f"2 longest literal window {worst[0]} bars ({worst[1]}) <= {N} / 10; HIST_MAX on 15m {hm.group(1) if hm else '?'} <= {N}")

before = {p: src[p] for p in CHART[2:]}
for b in ("audit/tools/build_brief.py", "audit/tools/build_diag.py"):
    subprocess.run([sys.executable, b], check=True, capture_output=True)
after = {p: open(p, encoding="utf-8").read() for p in CHART[2:]}
report(before == after, "3 Brief / Diagnostics rebuilt by their builders: byte-identical, calc_bars_count included")

s0 = list(src.values())
m1 = [re.sub(r",\s*calc_bars_count\s*=\s*\d+", "", s0[0], count=1)] + s0[1:]
m2 = [s0[0].replace(f"calc_bars_count={N}", f"calc_bars_count={N + 1000}", 1)] + s0[1:]
report(not same(m1)[1] and not same(m2)[1], "4 controls: a script without it, and one with another value, are detected")
print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- declarations read; TradingView run time NOT measured (needs the chart)")
sys.exit(1 if fails else 0)
