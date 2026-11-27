#!/usr/bin/env python3
"""v105 / v106: the chart scripts calculate on the last N bars (3000 in v105, 1500 in v106) (calc_bars_count), so they stay under TradingView's run-time limit.

  1 the four chart scripts (Master, Visuals, Brief, Diagnostics) declare the SAME calc_bars_count; the repo-set
    strategy arms do not (their A/B hunks are unchanged)
  2 the engine fits in it: the longest literal chart-timeframe window (ta.* length, [n] history reference, loop over
    past bars) in every chart script is at most a fifth of it, and two trading weeks of 15m bars fit (weekly levels);
    v106: 3000 -> 1500, so the 15m stats buffer (HIST_MAX 3000) is filled to about half
  3 Brief / Diagnostics carry it through their builders (a rebuild reproduces the files byte for byte)
  4 control: a script without it, and one with a different value, are detected
  5 v106: Visuals' footprint asks for intrabar data in ONE request, at the chart timeframe while the footprint is off
    (every read of the arrays is inside `if showFP`)
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
# v108: the three ENGINE copies (Master, Brief, Diagnostics) share one value; Visuals (its own, lighter engine) may
# calculate on more bars (it runs at 1500 on the free plan where the Master runs at ~1000)
vals = [decl(src[p]) for p in CHART]
eng = [vals[0], vals[2], vals[3]]
ok = len(set(eng)) == 1 and eng[0] is not None and vals[1] is not None and vals[1] >= eng[0]
arms = [p for p in glob.glob("artefacts/*Strategy*.pine") if decl(open(p, encoding="utf-8").read()) is not None]
report(ok and not arms, f"1 calc_bars_count: Master / Brief / Diagnostics {eng} (equal), Visuals {vals[1]} (>= them); "
       f"strategy arms with it: {arms}")
N = min(v for v in vals if v) if all(vals) else 0

worst = (0, "")
for p, s in src.items():
    for l in s.split("\n"):
        code = l.split("//")[0]
        for m in re.finditer(r"ta\.\w+\([^()]*?,\s*(\d+)\s*\)|\[(\d+)\]|for \w+ = (\d+) to 0|for \w+ = 0 to (\d+)\b", code):
            n = int(next(g for g in m.groups() if g))
            if n > worst[0]:
                worst = (n, f"{p.split('_')[-1]}: {code.strip()[:70]}")
hm = re.search(r"int HIST_MAX = .*?tfSec <= 900 \? (\d+)", src[CHART[0]])
WEEK2_15M = 2 * 5 * 92          # two trading weeks of 15m bars: the weekly levels' history (v106)
report(worst[0] * 5 <= N and WEEK2_15M <= N and hm is not None,
       f"2 longest literal window {worst[0]} bars ({worst[1]}) <= {N} / 5; two weeks of 15m bars ({WEEK2_15M}) <= {N}; "
       f"the 15m stats buffer (HIST_MAX {hm.group(1) if hm else '?'}) holds up to {N} records at this cap")

before = {p: src[p] for p in CHART[2:]}
for b in ("audit/tools/build_brief.py", "audit/tools/build_diag.py"):
    subprocess.run([sys.executable, b], check=True, capture_output=True)
after = {p: open(p, encoding="utf-8").read() for p in CHART[2:]}
report(before == after, "3 Brief / Diagnostics rebuilt by their builders: byte-identical, calc_bars_count included")

s0 = list(src.values())
m1 = re.sub(r",\s*calc_bars_count\s*=\s*\d+", "", s0[0], count=1)
m2 = s0[0].replace(f"calc_bars_count={eng[0]}", f"calc_bars_count={eng[0] + 1000}", 1)
report(decl(m1) is None and decl(m2) != eng[1], "4 controls: a Master without it, and one with another value than Brief / "
       "Diagnostics, are detected")
V = src[CHART[1]]
calls = re.findall(r"request\.security_lower_tf\(([^\n]*)\)\s*$", V, re.M)
uses = [i for i, l in enumerate(V.split("\n")) if re.search(r"\bltf[COV]\b", l.split("//")[0]) and "security_lower_tf" not in l]
gate = next(i for i, l in enumerate(V.split("\n")) if l.startswith("if showFP and barstate.isconfirmed"))
body_end = next(i for i, l in enumerate(V.split("\n")) if i > gate and l and not l.startswith((" ", "\t")))
report(len(calls) == 1 and "showFP ? fpTf : timeframe.period" in calls[0] and all(gate < i < body_end for i in uses),
       f"5 v106 Visuals: {len(calls)} intrabar request, 1-minute data only while the footprint is on; its {len(uses)} "
       f"reads all inside `if showFP` (lines {gate + 1}-{body_end}), so the output is unchanged")
print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- declarations read; TradingView run time NOT measured (needs the chart)")
sys.exit(1 if fails else 0)
