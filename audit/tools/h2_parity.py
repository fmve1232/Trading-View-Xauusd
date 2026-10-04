#!/usr/bin/env python3
"""H2 parity: the block between `// H2-BEGIN` and `// H2-END` must be byte-identical in Visuals
(chart signals) and Strategy_H2 (the forward-test arm), so the chart shows exactly what is tested.
Usage: python3 audit/tools/h2_parity.py"""
import sys

A = "artefacts/XAUUSD_Quantum_5_5_Visuals.pine"
B = "artefacts/XAUUSD_Quantum_5_0_Strategy_H2.pine"


def block(p):
    L = open(p, encoding="utf-8").read().split("\n")
    a = [i for i, l in enumerate(L) if l == "// H2-BEGIN"]
    b = [i for i, l in enumerate(L) if l == "// H2-END"]
    if len(a) != 1 or len(b) != 1 or b[0] < a[0]:
        sys.exit(f"FAIL  expected exactly one // H2-BEGIN ... // H2-END fence pair in {p}")
    return "\n".join(L[a[0]:b[0] + 1])


x, y = block(A), block(B)
if x == y:
    print(f"PASS  H2 block identical in Visuals and Strategy_H2 ({x.count(chr(10))} lines)")
else:
    xl, yl = x.split("\n"), y.split("\n")
    k = next(i for i in range(min(len(xl), len(yl))) if xl[i] != yl[i]) if any(a != b for a, b in zip(xl, yl)) else min(len(xl), len(yl))
    sys.exit(f"FAIL  H2 blocks differ at block line {k + 1}")
