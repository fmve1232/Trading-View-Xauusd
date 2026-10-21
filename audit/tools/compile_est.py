#!/usr/bin/env python3
"""Compiled-token estimate for TradingView's 100,256 limit (v68, F-A66). Replaces "lexical x 2.515".

TradingView expands user-function calls. Counting the lexical tokens PLUS, for every call, the expanded body of the
function (recursively: helpers that call helpers) fits the compiler's own reports:
    v23 Master  100,820 reported  ->  1.6197 per (lexical + expanded)
    v67 Master  100,335 reported  ->  1.6190            "            (lexical alone gave 2.515 vs 2.581)
    v14 Master  100,627 reported  ->  1.5798   outlier, kept on record
A second model counts the expansion WITHOUT the definitions (top-level code + expanded calls): 2.1293 / 2.1884 / 2.1497.
Both are estimates. Gates (each chart script and arm), v69:
  * best-fit and pessimistic both below the limit, AND at most the estimate of a build that really compiled
    (the v66 Master, 100,204 / 100,109; the Brief's own v66, which compiled at a model 101,003 / 104,385);
  * MAIN BODY (lexical tokens outside function definitions) at most 26,538, the largest that compiled (v68
    Diagnostics). TradingView has a separate main-body limit: the v68 Master failed at 28,122 with CE10295 "The main
    body of the script is too long" after single-call functions were inlined. So never inline big functions.
  * F-A68: the Master with the GD block (five gold drivers) FAILED twice, at 103,989 (v70) and 104,510 (v71), where this
    model said ~99,600. The model misses ~4,400-4,900 tokens there and the cause is NOT identified (v70's record type was
    blamed first; v71 had none and came out higher). So the model is NOT trusted for that block: a Master containing
    `// GD-BEGIN` FAILS here, and both reports are listed in KNOWN_OVER (the model's miss is shown, not hidden).
The real compiler is the judge; every report is added below.
Usage: python3 audit/tools/compile_est.py [files]   (default: every artefact)"""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lexcount import toks  # noqa: E402

LIMIT = 100256
CALIBRATION = {"v14": 100627, "v23": 100820, "v67": 100335}   # compiler-reported totals (Master) the model fits
# compiler-reported FAILURES the model does not reproduce (F-A68): shown on every run, never fitted away
KNOWN_OVER = {"v70 Master": ("Master", "cb88ecc0", 103989), "v71 Master": ("Master", "adbe2bc1", 104510),
              "v84 Master": ("Master", "c56ec329", 100332)}
# Compiled WITHOUT error (operator), i.e. under 100,256: the model must not put these over the limit.
# v66 Master (39,029 lexical) compiled while v67 (38,870 lexical, FEWER) did not: lexical x ratio is refuted.
# (file, commit). A confirmed compile the model puts OVER the limit means the model is cautious for that file (safe
# side): reported as INFO. The v66 Brief compiled although the model said ~101,000.
KNOWN_UNDER = {"v60 Master": ("Master", "eb3e0c00"), "v66 Master": ("Master", "a5fc12ce"), "v66 Brief": ("Brief", "a5fc12ce"),
               "v69 Master": ("Master", "61871d60"), "v68 Brief": ("Brief", "c524e2a7"), "v68 Diagnostics": ("Diagnostics", "c524e2a7"),
               "v70 Brief": ("Brief", "cb88ecc0"), "v72 Master": ("Master", "89078a56")}
BEST, PESS = 1.6197, 2.1497        # best fit (v23 / v67, the higher); pessimistic model at its v67 ratio
MAIN_BODY_OK, MAIN_BODY_FAIL = 26538, 28122   # v68 Diagnostics compiled / v68 Master CE10295
CEILING = {"Brief": (101003, 104385),       # a file's own confirmed compile, where the model is cautious for it
           # v85 (F-A72): the Master's lineage since v68 compiled at 99,542 / 99,004 (v72 = v83) and FAILED at 100,332 with
           # 99,602 / 99,084 (v84, +~40 raw tokens of alert text). The v66 ceiling is too loose for it: the Master may not
           # exceed the v72 estimate until a compile proves otherwise. Real headroom at v72: under ~80 tokens.
           "Master": (99543, 99005)}   # rounded up: the v72 estimate is 99,542.3 / 99,004.x
DEFAULT_CEILING = (100204, 100109)          # the v66 Master compiled at these estimates


def model(text):
    L = text.split("\n")
    funcs, deflines, i = {}, set(), 0
    while i < len(L):
        m = re.match(r"^([A-Za-z_]\w*)\((.*?)\)\s*=>\s*(.*)$", L[i])
        if m:
            body = [m.group(3)] if m.group(3).strip() else []
            j = i + 1
            while j < len(L) and (L[j].startswith(" ") or not L[j].strip()):
                body.append(L[j])
                j += 1
            funcs[m.group(1)] = body
            deflines |= set(range(i, j))
            i = j
        else:
            i += 1

    def calls_in(lines):
        out = {}
        for l in lines:
            c = l.split("//")[0] if '"' not in l else l
            for f in funcs:
                n = len(re.findall(r"(?<![\w.])" + re.escape(f) + r"\s*\(", c))
                if n:
                    out[f] = out.get(f, 0) + n
        return out
    memo = {}

    def cost(f, stack=()):
        if f in memo:
            return memo[f]
        if f in stack:
            return 0
        c = sum(len(toks(b)) for b in funcs[f])
        for g, n in calls_in(funcs[f]).items():
            if g != f:
                c += n * cost(g, stack + (f,))
        memo[f] = c
        return c
    top = [l for k, l in enumerate(L) if k not in deflines]
    lex_all = sum(len(toks(l)) for l in L)
    lex_top = sum(len(toks(l)) for l in top)
    inl = sum(n * cost(f) for f, n in calls_in(top).items())
    return lex_all, lex_top, inl


def estimate(text):
    la, lt, inl = model(text)
    return (la + inl) * BEST, (lt + inl) * PESS, lt


if __name__ == "__main__":
    files = sys.argv[1:] or sorted(glob.glob("artefacts/*.pine"))
    fails = 0
    for p in files:
        b, w, lt = estimate(open(p, encoding="utf-8").read())
        cb, cw = next((v for k, v in CEILING.items() if k in os.path.basename(p)), DEFAULT_CEILING)
        txt = open(p, encoding="utf-8").read()
        gd = "Master" in os.path.basename(p) and "// GD-BEGIN" in txt
        ok = b <= max(cb, 0) and w <= max(cw, 0) and (b < LIMIT or cb >= LIMIT) and lt <= MAIN_BODY_OK and not gd
        if gd:
            print("FAIL  the Master contains the GD block: v70 / v71 with it failed to compile and the model misses why (F-A68)")
        fails += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {os.path.basename(p):46s} best-fit {b:9,.0f} ({b / LIMIT - 1:+.2%})"
              f"   pessimistic {w:9,.0f} ({w / LIMIT - 1:+.2%})   main body {lt:,} (max OK {MAIN_BODY_OK:,})")
    import subprocess
    for tag, (fname, commit) in KNOWN_UNDER.items():   # every compile the operator confirmed
        t = subprocess.run(["git", "show", f"{commit}:artefacts/XAUUSD_Quantum_5_0_{fname}.pine"], capture_output=True, text=True).stdout
        if t:
            b, w, lt = estimate(t)
            tag2 = "agrees" if b < LIMIT and w < LIMIT else "is CAUTIOUS for this file (it compiled; the model said over)"
            print(f"INFO  calibration: {tag} compiled; model best-fit {b:,.0f}, pessimistic {w:,.0f} -- model {tag2}")
    for tag, (fname, commit, rep) in KNOWN_OVER.items():   # every compile that FAILED: the model must say over
        t = subprocess.run(["git", "show", f"{commit}:artefacts/XAUUSD_Quantum_5_0_{fname}.pine"], capture_output=True, text=True).stdout
        if t:
            b, w, lt = estimate(t)
            ok = b > LIMIT or w > LIMIT
            print(f"INFO  calibration: {tag} FAILED at {rep:,}; model best-fit {b:,.0f}, pessimistic {w:,.0f}"
                  f" -- {'model agrees' if ok else 'model MISSES this failure by ' + format(rep - max(b, w), ',.0f') + ' (cause not identified, F-A68)'}")
    print("RESULT:", "PASS" if not fails else "FAIL", "-- estimates calibrated on compiler reports", CALIBRATION,
          "; the compiler is the judge")
    sys.exit(1 if fails else 0)
