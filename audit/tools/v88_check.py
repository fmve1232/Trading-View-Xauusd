#!/usr/bin/env python3
"""v88: Visuals' MACRO is the Master's MACRO (operator, 2026-10-29: "Visuals & Master show different directions").

  1 verbatim: every code line between MX-BEGIN and MX-END in Visuals is a Master line, in the Master's order
  2 complete: a backward slice of the Master from macroIntelScore / macroIntelLabel / macroIntelValid (every top-level
    statement that defines a name they need, transitively) is present in Visuals verbatim; the two inputs Visuals
    already had (macroTF, corrMedLen) may differ only in their group= text (inputs_check.py holds default and bounds)
  3 the MACRO text: mxVerdict is the Master's _macroVerdict expression, character for character
  4 executed: the score-to-verdict tail (weights, ms*, macroStrengthScore, macroIntelLabel, mxVerdict, mxDir, mxGlyph,
    mxWhy) run from BOTH files on random component states: identical outputs; direction / glyph agree with the label;
    no "NaN" in any text
  5 display: the ticker's macro tile, the panel's MACRO row and the glance read the Master's verdict (mxGlyph /
    mxVerdict / macroIntelScore); the five extra drivers are labelled context and no headline shows their net
  6 noise: the five v87 drawings (FVG, OB, session shading, pivots, PMH/PML) are OFF again
Usage: python3 audit/tools/v88_check.py"""
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402

M = open("artefacts/XAUUSD_Quantum_5_0_Master.pine", encoding="utf-8").read().split("\n")
V = open("artefacts/XAUUSD_Quantum_5_5_Visuals.pine", encoding="utf-8").read().split("\n")
fails = 0
rng = random.Random(88)


def report(ok, msg):
    global fails
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    fails += not ok


# ---- 1 verbatim, in order
a = V.index(next(l for l in V if l.startswith("// MX-BEGIN")))
b = V.index("// MX-END")
code = [l for l in V[a + 1:b] if l.strip() and not l.lstrip().startswith("//")]
pos, ok1 = -1, True
for l in code:
    try:
        pos = M.index(l, pos + 1)
    except ValueError:
        ok1 = False
        print("   not a Master line (or out of order):", l[:100])
        break
report(ok1 and len(code) > 150, f"1 MX block: {len(code)} code lines, each a Master line, in the Master's order")


# ---- 2 complete: backward slice of the Master
def strip(l):
    if '"' in l:
        l = re.sub(r'"(?:\\.|[^"\\])*"', '""', l)
    return l.split("//")[0]


KW = set("if else for to in while and or not na true false var varip int float bool string color switch break continue".split())
stmts, i = [], 0
while i < len(M):
    l = M[i]
    if not l.strip() or l.startswith("//") or l.startswith(" "):
        i += 1
        continue
    j = i + 1
    while j < len(M) and (M[j].startswith(" ") or not M[j].strip() or M[j].startswith("//")):
        j += 1
    k = j
    while k > i + 1 and (not M[k - 1].strip() or M[k - 1].lstrip().startswith("//")):
        k -= 1
    stmts.append((i, k))
    i = j


def du(a_, b_):
    body = [strip(x) for x in M[a_:b_]]
    head = body[0]
    m = re.match(r'^([A-Za-z_]\w*)\s*\(.*\)\s*=>', head)
    if m:
        params = set(re.findall(r'([A-Za-z_]\w*)\s*(?:,|\))', head.split("=>")[0].split("(", 1)[1]))
        return {m.group(1)}, set(re.findall(r'(?<![\w.])([A-Za-z_]\w*)', " ".join(body).split("=>", 1)[1])) - params
    txt = "\n".join(body)
    d = {mm.group(1) for mm in re.finditer(r'(?m)^\s*(?:var\s+|varip\s+)?(?:(?:float|int|bool|string|color|array<\w+>|\w+\[\])\s+)?'
                                            r'([A-Za-z_]\w*)\s*(?::=|=(?!=)|\+=|-=)', txt)}
    for mm in re.finditer(r'(?m)^\s*\[([^\]]+)\]\s*=(?!=)', txt):
        d |= {x.strip() for x in mm.group(1).split(",")}
    return d, set(re.findall(r'(?<![\w.])([A-Za-z_]\w*)', txt))


info = [(a_, b_) + du(a_, b_) for a_, b_ in stmts]
need, want, done = set(), {"macroIntelScore", "macroIntelLabel", "macroIntelValid"}, set()
while want:
    n = want.pop()
    done.add(n)
    for idx, (a_, b_, d, u) in enumerate(info):
        if n in d and idx not in need:
            need.add(idx)
            want |= {x for x in u - KW if x not in done}
Vset = set(V)
def _ng(l):
    return re.sub(r',\s*(?:group|tooltip)\s*=\s*(?:"[^"]*"|\w+)', "", l)


nogroup = {_ng(l) for l in V}
missing = []
for idx in sorted(need):
    a_, b_ = info[idx][:2]
    for l in M[a_:b_]:
        if not l.strip() or l.lstrip().startswith("//") or l in Vset:
            continue
        if _ng(l) in nogroup and "input." in l:
            continue
        if re.match(r'^grp\w+ = ', l):           # group names only label the settings dialog
            continue
        missing.append(l[:90])
report(not missing, f"2 complete: the Master's macro slice ({len(need)} statements) is in Visuals verbatim (2 inputs differ only by "
       f"group / tooltip text)" + (f" -- missing {missing[:3]}" if missing else ""))

# ---- 3 the MACRO text
mexpr = next(l.strip() for l in M if l.strip().startswith("string _macroVerdict = ")).split("=", 1)[1].strip()
vexpr = next(l for l in V if l.startswith("string mxVerdict = ")).split("=", 1)[1].strip()
report(mexpr == vexpr, "3 mxVerdict == the Master's _macroVerdict expression, character for character")


# ---- 4 executed tail from both files
def tail(lines, start, end):
    s_ = lines.index(next(l for l in lines if l.startswith(start)))
    e_ = lines.index(next(l for l in lines[s_:] if l.startswith(end)), s_)
    return [l for l in lines[s_:e_ + 1] if l.strip() and not l.lstrip().startswith("//")]


mt = tail(M, "_wDXYr = ", "macroStrengthScore = ") + [l for l in M if l.startswith("macroIntelScore = ") or l.startswith("macroIntelValid = ")
                                                       or l.startswith("string macroIntelLabel = ")]
vt = tail(V, "_wDXYr = ", "macroStrengthScore = ") + [l for l in V if l.startswith("macroIntelScore = ") or l.startswith("macroIntelValid = ")
                                                       or l.startswith("string macroIntelLabel = ")]
disp = [l for l in V if l.startswith(("string mxVerdict = ", "int mxDir = ", "string mxGlyph = ", "string mxWhy = "))]
env = P.Env()
P.define([next(l for l in V if l.startswith("f_mxC(string n, bool v, float pts) =>"))], env)
bad4 = nan4 = n4 = 0
GLY = {"BULL": "▲▲", "BULL-ISH": "▲", "BEAR": "▼▼", "BEAR-ISH": "▼", "MIXED": "≈", "N/A": "—"}
for _ in range(5000):
    b_ = lambda: rng.random() < 0.5
    v_ = lambda x: P.NA if rng.random() < 0.15 else x
    st = {k: b_() for k in ("dxyValid", "yieldValid", "spxValid", "eurusdValid", "silverValid", "tipsValid", "dxyBear", "dxyBull",
                            "yieldFalling", "yieldRising", "spxBull", "spxBear", "eurusdBull", "eurusdBear", "tipsFalling", "tipsRising",
                            "dxyMomBear", "dxyMomBull", "ratePressureDown", "ratePressureUp")}
    st.update({k: rng.choice([0.0, rng.uniform(-1, 1)]) for k in ("avgCorrDXY", "avgCorrYld", "avgCorrSlv", "avgCorrSPX", "avgCorrEUR", "avgCorrTIPS")})
    st.update(silverClose=rng.uniform(20, 40), silverEMA=rng.uniform(20, 40), eurusdROC=rng.uniform(-0.5, 0.5),
              _rawDXYRSI=v_(rng.uniform(0, 100)), _silverRSI=v_(rng.uniform(0, 100)))
    em, ev = P.Env(funcs=env.funcs, **st), P.Env(funcs=env.funcs, **st)
    P.run(mt, em)
    P.run(vt + disp, ev)
    n4 += 1
    same = (em["macroStrengthScore"], em["macroIntelLabel"]) == (ev["macroStrengthScore"], ev["macroIntelLabel"])
    lab = ev["macroIntelLabel"]
    agree = ev["mxGlyph"] == GLY[lab] and int(ev["mxDir"]) == (1 if lab.startswith("BULL") else -1 if lab.startswith("BEAR") else 0)
    bad4 += not (same and agree)
    nan4 += "NaN" in ev["mxVerdict"] or "NaN" in ev["mxWhy"]
report(bad4 == 0 and nan4 == 0, f"4 executed from both files, {n4} random component states: score and label identical, glyph / direction "
       f"agree with the label, mismatches {bad4}; NaN in the texts {nan4}")

# ---- 5 display
txt = "\n".join(V)
tile3 = next(l.strip() for l in V if l.strip().startswith("f_tk(3, "))
dock = next(l.strip() for l in V if l.strip().startswith("table.cell(dkT, 6, 1, "))
okd = ("mxGlyph" in tile3.split('"macro')[0] and "f_tmC(_tNet)" not in tile3 and '"macro · = Master"' in tile3
       and '"OTHER DRIVERS · context"' in dock and "f_tmG(_net)" not in dock.split("tooltip")[0]
       and '_tmRow(r, "MACRO", mxVerdict + " (= the Master\'s MACRO cell)"' in txt and "mxGlyph + \" \" + (macroIntelLabel" in txt
       and "the Master's MACRO: \" + mxVerdict" in txt and '"daily regime · untested"' in txt and 'f_tk(_c, rgTxt, ' in txt)
report(okd, "5 display: ticker macro tile, panel MACRO row, glance rows show the Master's verdict; the five extra drivers are "
       "'OTHER DRIVERS · context' with their net only in tooltips; the daily-regime tile carries no macro mark")

# ---- 6 noise
offs = all(re.search(r"(?m)^" + n + r"\s*= input\.bool\(false,", txt) for n in ("showFVG", "showOB", "showSess", "showPivots", "showMonthly"))
report(offs, "6 the v87 drawings (FVG, OB, session shading, pivots, PMH/PML) are OFF by default again")
print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- Pine text read and executed in Python; TradingView runtime NOT exercised")
sys.exit(1 if fails else 0)
