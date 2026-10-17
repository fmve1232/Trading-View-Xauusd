#!/usr/bin/env python3
"""Compiled-token estimate for TradingView's 100,256 limit (v68, F-A66). Replaces "lexical x 2.515".

TradingView expands user-function calls. Counting the lexical tokens PLUS, for every call, the expanded body of the
function (recursively: helpers that call helpers) fits the compiler's own reports:
    v23 Master  100,820 reported  ->  1.6197 per (lexical + expanded)
    v67 Master  100,335 reported  ->  1.6190            "            (lexical alone gave 2.515 vs 2.581)
    v14 Master  100,627 reported  ->  1.5798   outlier, kept on record
A second model counts the expansion WITHOUT the definitions (top-level code + expanded calls): 2.1293 / 2.1884 / 2.1497.
Both are estimates. Gates (each chart script and arm): best-fit <= 98% of the limit, pessimistic < 100%. The real
compiler is the judge; a reported figure is added to CALIBRATION below.
Usage: python3 audit/tools/compile_est.py [files]   (default: every artefact)"""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lexcount import toks  # noqa: E402

LIMIT = 100256
CALIBRATION = {"v14": 100627, "v23": 100820, "v67": 100335}   # compiler-reported totals (Master)
# Compiled WITHOUT error (operator), i.e. under 100,256: the model must not put these over the limit.
# v66 Master (39,029 lexical) compiled while v67 (38,870 lexical, FEWER) did not: lexical x ratio is refuted.
KNOWN_UNDER = {"v60 Master": "eb3e0c00", "v66 Master": "a5fc12ce"}
BEST, PESS = 1.6197, 2.1497        # best fit (v23 / v67, the higher); pessimistic model at its v67 ratio


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


if __name__ == "__main__":
    files = sys.argv[1:] or sorted(glob.glob("artefacts/*.pine"))
    fails = 0
    for p in files:
        la, lt, inl = model(open(p, encoding="utf-8").read())
        b, w = (la + inl) * BEST, (lt + inl) * PESS
        ok = b <= 0.98 * LIMIT and w < LIMIT
        fails += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {os.path.basename(p):46s} best-fit {b:9,.0f} ({b / LIMIT - 1:+.2%})"
              f"   pessimistic {w:9,.0f} ({w / LIMIT - 1:+.2%})   lexical {la:,}")
    import subprocess
    for tag, commit in KNOWN_UNDER.items():      # the model must agree with every compile the operator confirmed
        t = subprocess.run(["git", "show", f"{commit}:artefacts/XAUUSD_Quantum_5_0_Master.pine"], capture_output=True, text=True).stdout
        if t:
            la, lt, inl = model(t)
            agree = (la + inl) * BEST < LIMIT and (lt + inl) * PESS < LIMIT
            fails += not agree
            print(f"{'PASS' if agree else 'FAIL'}  calibration: {tag} compiled; model best-fit {(la + inl) * BEST:,.0f}, pessimistic {(lt + inl) * PESS:,.0f}")
    print("RESULT:", "PASS" if not fails else "FAIL", "-- estimates calibrated on compiler reports", CALIBRATION,
          "; the compiler is the judge")
    sys.exit(1 if fails else 0)
