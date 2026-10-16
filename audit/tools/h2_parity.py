#!/usr/bin/env python3
"""H2 parity: the block between `// H2-BEGIN` and `// H2-END` must be byte-identical in Visuals
(chart signals), Strategy_H2 (the forward-test arm) and, since v37, the Master (H2 SETUP row),
so every screen shows exactly what is tested.
v37 also checks the session intelligence that moved from the Master to Visuals: the block between
`// SESSIntel-BEGIN` / `// SESSIntel-END` in Visuals must equal the Treatment engine's
f_sessionIntel() definition and its tuple call, line for line.
v62 (F-A60) also checks the block's INPUTS, which sit outside the fences and so escaped the byte check: in every
file h2S1 / h2S4 / h2SD must be a score function applied straight to the 1H / 4H / 1D request (no availability gate,
no other score in between), the three requests must be the same text everywhere, and the score functions must give
the same value on an executed grid (na, ties, every ordering of close / EMA20 / EMA100 / EMA200).
Usage: python3 audit/tools/h2_parity.py"""
import itertools
import re
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import pine_exec as P  # noqa: E402

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

# ---- v62 (F-A60): the H2 block's inputs ------------------------------------------------------------------------
TFS = {"h2S1": '"60"', "h2S4": '"240"', "h2SD": '"D"'}
REQ, FNS = {}, {}
fail0 = fail
fail = 0
for p in FILES:
    L = open(p, encoding="utf-8").read().split("\n")
    for v, tf in TFS.items():
        d = [l for l in L if re.match(rf"^(?:float |int )?{v} = ", l)]
        if len(d) != 1:
            print(f"FAIL  {p.split('/')[-1]}: {len(d)} definitions of {v}")
            fail = 1
            continue
        m = re.match(rf"^(?:float |int )?{v} = (\w+)\(([\w, ]+)\)$", d[0])
        if not m:
            print(f"FAIL  {p.split('/')[-1]}: {v} is not a score of the raw request: {d[0]!r}")
            fail = 1
            continue
        fn, args = m.group(1), [a.strip() for a in m.group(2).split(",")]
        r = [l for l in L if l.startswith("[" + ", ".join(args) + "] = request.security(")]
        rq = r[0].split(" = ", 1)[1] if len(r) == 1 else None
        if rq is None or f"syminfo.tickerid, {tf}," not in rq:
            print(f"FAIL  {p.split('/')[-1]}: {v} does not read exactly one {tf} request")
            fail = 1
            continue
        REQ.setdefault(v, set()).add(rq)
        if fn not in FNS:
            h = next(i for i, l in enumerate(L) if l.startswith(fn + "("))
            e = next(i for i in range(h + 1, len(L)) if not L[i].startswith(" "))
            FNS[fn] = P.define(L[h:e], P.Env(funcs={}))
for v in TFS:
    if len(REQ.get(v, ())) > 1:
        print(f"FAIL  {v}: the {TFS[v]} request differs between files")
        fail = 1
vals = [P.NA, 1.0, 2.0, 3.0, 4.0]
grid = [g for g in itertools.product(vals, repeat=4)]
ref_fn = next(iter(FNS))
bad = [(f, g) for f in FNS for g in grid if FNS[f](*g) != FNS[ref_fn](*g)]
if bad:
    print(f"FAIL  score functions differ: {bad[0]}")
    fail = 1
elif not fail and len(REQ) == 3 and all(len(x) == 1 for x in REQ.values()):
    print(f"PASS  H2 inputs: h2S1/h2S4/h2SD = {' == '.join(FNS)} on the raw 60/240/D requests in all "
          f"{len(FILES)} files, no availability gate ({len(grid)} cases executed)")
sys.exit(fail or fail0)
