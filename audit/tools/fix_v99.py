#!/usr/bin/env python3
"""v99 (F-A87): the NY trading-day rollover = a change of the trading-day KEY, as the website's engine computes it.

Found by level_check.py (v99): the time-of-day test compared both bars with the CURRENT bar's 17:00 New York boundary.
On the US DST-start Sunday with an 18:00 New York open (spot gold is closed Friday 17:00 -> Sunday 18:00), Friday's
last bar (16:55 EST = 21:55 UTC) lies after the new boundary (17:00 EDT = 21:00 UTC) and before Sunday's first bar
(22:00 UTC): neither branch fired and Friday + Monday became one "day". Real 1H feed, 2026-03-08: PDH / PDL wrong for
23 bars; CDH / CDL, PWH / PWL and everything keyed on crossedNYDay inherit it. The website (system of record) is
correct here: quantum/sessions.py rolls when the trading date (New York + 7 h) changes.

The same edit goes into every engine copy that carries the block (Master, the three strategy twins, Visuals);
Diagnostics and the Brief are rebuilt from the Treatment twin. The hunk counts between the twins are unchanged.
Every output is computed before any file is written. Usage: python3 audit/tools/fix_v99.py  (from the repo root)"""
import subprocess
import sys

OLD = ["bool crossedNYDay = false",
       "if not na(time[1])",
       "    int tMod = time % msInDay",
       "    int t1Mod = time[1] % msInDay",
       "    if tMod > t1Mod",
       "        crossedNYDay := t1Mod < nyCloseDayMs and tMod >= nyCloseDayMs",
       "    else",
       "        crossedNYDay := t1Mod < nyCloseDayMs or tMod >= nyCloseDayMs"]
NEW = ["// CHANGE ID: F-A87 (v99) | Day rollover = a change of the trading-day KEY, as the website's engine computes it",
       "// (quantum/sessions.py: crossed_day = the trading date, New York time + 7 h, differs from the previous bar's).",
       "// DEFECT. The time-of-day test (kept below as comments) compared both bars with the CURRENT bar's 17:00 boundary.",
       "// On the US DST-start Sunday with an 18:00 New York open (spot gold: closed Friday 17:00 -> Sunday 18:00), Friday's",
       "// last bar (16:55 EST = 21:55 UTC) lies after the new boundary (17:00 EDT = 21:00 UTC) and before Sunday's first",
       "// bar (22:00 UTC): no branch fired and Friday + Monday became one day (real 1H feed, 2026-03-08: PDH / PDL wrong",
       "// for 23 bars). FIX. Each bar's key counts whole days of (time - its OWN nyCloseDayMs), so it changes exactly when",
       "// New York crosses 17:00, whatever the gap or the DST state, and only once per day (F-004 cannot recur).",
       "// level_check.py: == the website's semantics on every bar (real 5m / 15m / 1h, generated 1m ... 4H, 17:00 and",
       "// 18:00 opens, 2024-2025). On D and above the key changes every bar, as the old test did there (P1-LVL-002).",
       "int _tdKey = math.floor((time - nyCloseDayMs) / msInDay)",
       "bool crossedNYDay = not na(time[1]) and _tdKey != _tdKey[1]",
       "// OLD (to v98):"]

HAND = ["artefacts/XAUUSD_Quantum_5_0_Master.pine", "artefacts/XAUUSD_Quantum_5_0_Strategy.pine",
        "artefacts/XAUUSD_Quantum_5_0_Strategy_OLDGATES.pine", "artefacts/XAUUSD_Quantum_5_0_Strategy_CHALLENGER.pine",
        "artefacts/XAUUSD_Quantum_5_5_Visuals.pine"]


def fix(src):
    L = src.split("\n")
    a = L.index(OLD[0])
    assert L.count(OLD[0]) == 1
    end = next(i for i in range(a, len(L)) if L[i] == OLD[-1])
    code = [i for i in range(a, end + 1) if not L[i].lstrip().startswith("//")]
    assert [L[i] for i in code] == OLD, "block differs"
    out = L[:a] + NEW
    for i in range(a, end + 1):
        l = L[i]
        if l.lstrip().startswith("//"):
            out.append(l)
        else:
            ind = len(l) - len(l.lstrip())
            out.append(" " * ind + "// " + l.lstrip())
    return "\n".join(out + L[end + 1:])


def unfix(src):
    """the exact inverse of fix(): the v98 code lines back, comments as they were (refactor_check uses it)"""
    L = src.split("\n")
    a = L.index(NEW[0])
    assert L[a:a + len(NEW)] == NEW
    out, k, i = L[:a], 0, a + len(NEW)
    olds = [x.strip() for x in OLD]
    while k < len(OLD):
        l = L[i]
        body = l.lstrip()
        if body.startswith("// ") and body[3:] == olds[k]:
            out.append(l[:len(l) - len(body)] + body[3:])
            k += 1
        else:
            out.append(l)
        i += 1
    return "\n".join(out + L[i:])


def master(src):
    """the v99 Master from the v98 Master (refactor_check's chain)"""
    return stamp(fix(src), "day rollover = website key")


def stamp(src, text):
    L = src.split("\n")
    i = next(k for k, l in enumerate(L[:6]) if "BUILD STAMP" in l)
    body = "// ║  BUILD STAMP — this file last CHANGED in v99   (" + text + ")"
    assert len(body) < len(L[i]), "stamp too long"
    L[i] = body + " " * (len(L[i]) - len(body) - 1) + "║"
    return "\n".join(L)


if __name__ == "__main__":
    outs = {}
    for tool, old, new in (("audit/tools/build_diag.py", "in v83   (news window: NY time)", "in v99   (day rollover = website key)"),
                           ("audit/tools/build_brief.py", "in v98   (H4 record as the site, web.7)", "in v99   (day rollover = website key)")):
        t = open(tool, encoding="utf-8").read()
        assert t.count(old) == 1, tool
        outs[tool] = t.replace(old, new)
    for p in HAND:
        s = open(p, encoding="utf-8").read()
        outs[p] = stamp(fix(s), "challenger H1; day rollover" if "CHALLENGER" in p else "day rollover = website key")
    for p, s in outs.items():
        open(p, "w", encoding="utf-8").write(s)
        print("wrote", p)
    for tool in ("audit/tools/build_diag.py", "audit/tools/build_brief.py"):
        r = subprocess.run([sys.executable, tool], capture_output=True, text=True)
        print(r.stdout.strip() or r.stderr.strip())
        if r.returncode:
            sys.exit(r.returncode)
