"""v67: `(x ? 1 : 0)` -> `_b1(x)` in the engine (identical int; a v6 bool is never na), to give the companions token
room for wiring every value they compute. Same edit in the Master and the three arms (Diagnostics / Brief are rebuilt
from the Treatment). Not applied inside the H2 block (byte-identical with Visuals / Strategy_H2) or f_sessionIntel
(identical with Visuals' SESSIntel block). refactor_check.py proves every changed line equals its v66 original."""
import re
import sys
FILES = ["artefacts/XAUUSD_Quantum_5_0_" + f + ".pine" for f in ("Master", "Strategy", "Strategy_OLDGATES", "Strategy_CHALLENGER")]
PAT = re.compile(r"\(([A-Za-z_][A-Za-z0-9_.]*) \? 1 : 0\)")
DEF = "_b1(bool b) => b ? 1 : 0"
ANCHOR = "safeDiv(a, b) =>"


def protected(L):
    keep = set()
    for a_pat, b_pat in (("// H2-BEGIN", "// H2-END"), ("f_sessionIntel() =>", "[sessId, curSessId,")):
        a = next((i for i, l in enumerate(L) if l.startswith(a_pat)), None)
        if a is not None:
            b = next(i for i in range(a, len(L)) if L[i].startswith(b_pat))
            keep |= set(range(a, b + 1))
    return keep


for p in FILES:
    L = open(p, encoding="utf-8").read().split("\n")
    keep = protected(L)
    n = 0
    for i, l in enumerate(L):
        if i in keep or l.lstrip().startswith("//"):
            continue
        code, sep, cmt = l.partition("//") if '"' not in l else (l, "", "")
        new = PAT.sub(r"_b1(\1)", code)
        if new != code:
            n += len(PAT.findall(code))
            L[i] = new + sep + cmt
    old_def = [i for i, l in enumerate(L) if l == DEF]
    if old_def:                                           # the Master: move its display-section definition up
        L.pop(old_def[0])
    a = next(i for i, l in enumerate(L) if l.startswith(ANCHOR))
    L[a + 1:a + 1] = ["// v67: (x ? 1 : 0) as a function, defined before the engine's first use (identical int)", DEF]
    open(p, "w", encoding="utf-8").write("\n".join(L))
    print(f"{p}: {n} rewritten")
