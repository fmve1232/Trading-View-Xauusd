#!/usr/bin/env python3
"""v101 (F-A92): Visuals' ten display blocks wrapped in functions change nothing but the main body's size.

  1 Visuals == fix_v101.fix(Visuals @ v100, 4e1da3cab), byte for byte; fix_v101.unfix(Visuals) == the v100 file
  2 every line that differs from v100 is the same line indented by four spaces, or one of the wrapper's lines (the v101
    comment, `f_v101X() =>`, `    0`, `f_v101X()`), or the build stamp: nothing else changed
  3 each wrapper is defined once and called exactly once, on the line right after its body, at the top level
  4 the main body: compile_est's main-body + strings model (CE10295) for v100 vs v101, with the known failure
  5 controls: fix_v101's safety checks refuse a block that reassigns a global (the BRACKET tracker), one that calls ta.*,
    and one that calls a plot-family function
Usage: python3 audit/tools/v101_check.py"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compile_est as CE  # noqa: E402
import fix_v101 as F  # noqa: E402

V = "artefacts/XAUUSD_Quantum_5_5_Visuals.pine"
fails = 0


def report(ok, msg):
    global fails
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {msg}")


cur = subprocess.run(["git", "show", "05c2c469a:" + V], capture_output=True, text=True, check=True).stdout   # v101 build (v102 refreshed typed records)
v100 = subprocess.run(["git", "show", "4e1da3cab:" + V], capture_output=True, text=True, check=True).stdout
live = open(V, encoding="utf-8").read()
report(F.fix(v100) == cur and F.unfix(cur) == v100 and all(f"{b[2]}() =>" in live for b in F.BLOCKS),
       "1 Visuals @ v101 (05c2c469a) == fix_v101.fix(v100 @ 4e1da3cab) byte for byte, unfix() == v100; the current file still carries the 10 wrappers")

names = [b[2] for b in F.BLOCKS]
# an independent reconstruction (not fix_v101.unfix): drop each wrapper's four lines, de-indent its body by exactly four
# spaces (every non-blank body line must carry them), and compare with v100 (stamp aside)
out, i, Lc, bad_ind, nb = [], 0, cur.split("\n"), 0, 0
while i < len(Lc):
    l = Lc[i]
    if l == F.HEAD and i + 1 < len(Lc) and Lc[i + 1].endswith("() =>") and Lc[i + 1][:-5] in names:
        n, j = Lc[i + 1][:-5], i + 2
        while Lc[j] != f"{n}()":
            j += 1
        body = Lc[i + 2:j - 1]
        assert Lc[j - 1] == "    0"
        bad_ind += sum(1 for x in body if x.strip() and not x.startswith("    "))
        out += [x[4:] if x.strip() else x for x in body]
        nb += len(body)
        i = j + 1
        continue
    out.append(l)
    i += 1
strip_ = lambda t: [x for x in t if "BUILD STAMP" not in x]
report(strip_(out) == strip_(v100.split("\n")) and bad_ind == 0,
       f"2 independent reconstruction: removing the 10 wrappers and de-indenting their {nb} body lines by 4 spaces gives v100 "
       f"exactly (stamp aside); body lines without the 4 spaces: {bad_ind}")

L = cur.split("\n")
bad3 = []
for n in names:
    d = [i for i, l in enumerate(L) if l == f"{n}() =>"]
    c = [i for i, l in enumerate(L) if l == f"{n}()"]
    refs = [i for i, l in enumerate(L) if n + "(" in l]
    if len(d) != 1 or len(c) != 1 or len(refs) != 2 or L[c[0] - 1] != "    0":
        bad3.append(n)
        continue
    body_ok = all((not l.strip()) or l.startswith("    ") for l in L[d[0] + 1:c[0]])
    if not body_ok:
        bad3.append(n)
report(not bad3, f"3 {len(names)} wrappers, each defined once and called once right after its body ({', '.join(names)})"
       + ("" if not bad3 else f"; wrong: {bad3}"))

m100, m101 = CE.main_str(v100), CE.main_str(cur)
v99 = subprocess.run(["git", "show", "2f8b3b796:" + V], capture_output=True, text=True, check=True).stdout
report(m101 <= CE.MAIN_BODY_STR_OK < CE.main_str(v99),
       f"4 main body + strings (CE10295 model): v99 {CE.main_str(v99):,} FAILED on the chart, v100 {m100:,}, v101 {m101:,}; "
       f"largest that compiled {CE.MAIN_BODY_STR_OK:,}")

VL = v100.split("\n")


def refused(lines):
    try:
        F.check(lines)
        return False
    except AssertionError:
        return True


tr = next(i for i, l in enumerate(VL) if l.startswith("if trkShow and barstate.isconfirmed"))
j = tr + 1
while VL[j].strip() == "" or VL[j][0] in " \t":
    j += 1
c1 = refused(VL[tr:j])
c2 = refused(["if barstate.islast", "    float x = ta.sma(close, 5)"])
c3 = refused(["if barstate.islast", "    plot(close)"])
report(c1 and c2 and c3, f"5 controls refused: a block reassigning globals (the BRACKET tracker) {c1}, ta.* {c2}, plot() {c3}")
print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- text transformation proved; TradingView compile NOT RUN for v101")
sys.exit(1 if fails else 0)
