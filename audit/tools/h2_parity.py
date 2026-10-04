#!/usr/bin/env python3
"""H2 parity: the block between `// H2-BEGIN` and `// H2-END` must be byte-identical in Visuals
(chart signals), Strategy_H2 (the forward-test arm) and, since v37, the Master (H2 SETUP row),
so every screen shows exactly what is tested.
v37 also checks the session intelligence that moved from the Master to Visuals: the block between
`// SESSIntel-BEGIN` / `// SESSIntel-END` in Visuals must equal the Treatment engine's
f_sessionIntel() definition and its tuple call, line for line.
Usage: python3 audit/tools/h2_parity.py"""
import sys

V = "artefacts/XAUUSD_Quantum_5_5_Visuals.pine"
FILES = [V, "artefacts/XAUUSD_Quantum_5_0_Strategy_H2.pine", "artefacts/XAUUSD_Quantum_5_0_Master.pine"]
T = "artefacts/XAUUSD_Quantum_5_0_Strategy.pine"


def block(p, b0="// H2-BEGIN", b1="// H2-END"):
    L = open(p, encoding="utf-8").read().split("\n")
    a = [i for i, l in enumerate(L) if l == b0]
    b = [i for i, l in enumerate(L) if l == b1]
    if len(a) != 1 or len(b) != 1 or b[0] < a[0]:
        sys.exit(f"FAIL  expected exactly one {b0} ... {b1} fence pair in {p}")
    return L[a[0]:b[0] + 1]


def first_diff(x, y):
    return next((i for i in range(min(len(x), len(y))) if x[i] != y[i]), min(len(x), len(y))) + 1


fail = 0
ref = block(FILES[0])
for p in FILES[1:]:
    y = block(p)
    if y == ref:
        print(f"PASS  H2 block identical: {p.split('/')[-1]} == Visuals ({len(ref) - 1} lines)")
    else:
        print(f"FAIL  H2 block in {p.split('/')[-1]} differs from Visuals at block line {first_diff(ref, y)}")
        fail = 1

s = block(V, "// SESSIntel-BEGIN", "// SESSIntel-END")[1:-1]
TL = open(T, encoding="utf-8").read().split("\n")
a = next(i for i, l in enumerate(TL) if l.startswith("f_sessionIntel() =>"))
b = next(i for i, l in enumerate(TL) if l.startswith("[sessId, curSessId,"))
if s == TL[a:b + 1]:
    print(f"PASS  Visuals f_sessionIntel == Treatment engine ({len(s)} lines)")
else:
    print(f"FAIL  Visuals f_sessionIntel differs from Treatment at line {first_diff(TL[a:b + 1], s)}")
    fail = 1
sys.exit(fail)
