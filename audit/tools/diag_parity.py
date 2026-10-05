#!/usr/bin/env python3
"""Diagnostics engine parity: the Diagnostics companion must run the Treatment twin's engine.

Compares CODE (comments and blank lines ignored, string literals kept) of
  artefacts/XAUUSD_Quantum_5_0_Diagnostics.pine  with every `// DIAG-BEGIN ... // DIAG-END`
                                                  block removed, and the indicator() line dropped
  artefacts/XAUUSD_Quantum_5_0_Strategy.pine     up to its execution layer (`bool _costModelValid`),
                                                  with the strategy() line dropped.
They must be identical line for line. Any engine edit to the twins has to be carried into the
Diagnostics file, or this fails -- the parity class behind F-A01 and F-A08.

Usage: python3 audit/tools/diag_parity.py
"""
import sys

DIAG = "artefacts/XAUUSD_Quantum_5_0_Diagnostics.pine"
TWIN = "artefacts/XAUUSD_Quantum_5_0_Strategy.pine"


def code(line):
    out, q, i = [], None, 0
    while i < len(line):
        c = line[i]
        if q:
            out.append(c)
            if c == "\\" and i + 1 < len(line):
                out.append(line[i + 1])
                i += 2
                continue
            if c == q:
                q = None
        elif c in "\"'":
            q = c
            out.append(c)
        elif c == "/" and line[i:i + 2] == "//":
            break
        else:
            out.append(c)
        i += 1
    return "".join(out).rstrip()


def lines(path, stop=None, fenced=False, decl=("strategy(", "indicator(")):
    res, skip = [], False
    for n, l in enumerate(open(path, encoding="utf-8").read().split("\n"), 1):
        s = l.strip()
        if fenced and s.startswith("// DIAG-BEGIN"):
            skip = True
            continue
        if fenced and s.startswith("// DIAG-END"):
            skip = False
            continue
        if skip:
            continue
        if stop and l.startswith(stop):
            break
        c = code(l)
        if not c.strip() or c.lstrip().startswith(decl):
            continue
        res.append((n, c))
    return res


d = lines(DIAG, fenced=True)
t = lines(TWIN, stop="bool _costModelValid")
bad = [(a, b) for a, b in zip(d, t) if a[1] != b[1]]
if len(d) != len(t) or bad:
    print(f"FAIL  engine drift: diagnostics {len(d)} code lines, twin {len(t)}")
    for a, b in bad[:5]:
        print(f"  DIAG L{a[0]}: {a[1][:90]}\n  TWIN L{b[0]}: {b[1][:90]}")
    sys.exit(1)
print(f"PASS  Diagnostics engine == Treatment twin engine ({len(d)} code lines, DIAG blocks excluded)")

# v39 (F-A44): the stats engine must match between the Master and the Treatment twin, because
# Diagnostics displays the twin's values for readouts the Master moved there (v37). Allowed
# differences: the two documented lines where the Master also refreshes on the last bar.
import difflib
MASTER = "artefacts/XAUUSD_Quantum_5_0_Master.pine"


def stats_body(p):
    L = open(p, encoding="utf-8").read().split("\n")
    a = next(i for i, l in enumerate(L) if l.startswith("runStatsEngines() =>"))
    b = next(i for i, l in enumerate(L) if l.startswith("[__b, __be"))
    out = []
    for l in L[a:b + 1]:
        c = l.split("//")[0].rstrip() if "//" in l and '"' not in l.split("//")[0] else l.rstrip()
        if c.strip() and not c.lstrip().startswith("//"):
            out.append(c)
    return out


def norm(l):  # the Master's documented last-bar refresh, reduced to the twin's form
    return l.replace(" or barstate.islast", "").replace(" and not barstate.islast", "").replace("timeframe.in_seconds()", "chartTFSeconds")


m, t2 = stats_body(MASTER), stats_body(TWIN)
nd = sum(1 for a in m if "barstate.islast" in a)
real = [l for l in difflib.unified_diff([norm(a) for a in m], [norm(b) for b in t2], lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
if real:
    print(f"FAIL  stats engine Master != Treatment ({len(real)} lines):")
    for l in real[:8]:
        print("  " + l[:110])
    sys.exit(1)
print(f"PASS  stats engine Master == Treatment ({len(t2)} code lines; {nd} documented last-bar refresh lines normalised)")
