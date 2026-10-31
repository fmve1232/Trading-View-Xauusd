#!/usr/bin/env python3
"""v90 independent audit, Stage 4: which engines can change the DECISION? (lexical backward slice of the Master)

Every statement (top-level and in blocks) that WRITES a global contributes the identifiers it reads -- including the
enclosing if / for / while / switch conditions -- to that global's dependencies; a user-function call contributes the
function's body. The slice from the DECISION targets is the closure. Lexical, so it OVER-approximates (a name in a branch
that can never run is still counted): "not in the slice" is a proof of no influence, "in the slice" is only a
possibility. Usage: python3 audit/tools/v90_slice.py [target ...]"""
import re, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from v90_register import strip  # noqa: E402  (same comment / string stripper)

F = "artefacts/XAUUSD_Quantum_5_0_Master.pine"
L = [strip(l).rstrip() for l in open(F, encoding="utf-8").read().split("\n")]
W = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
FUN = re.compile(r"^([A-Za-z_]\w*)\(([^)]*)\)\s*=>(.*)$")
ASG = re.compile(r"^\s*(?:var\s+|varip\s+)?(?:[A-Za-z_<>\[\].]+\s+)?([A-Za-z_]\w*)\s*(=|:=|\+=|-=|\*=|/=)(?!=)(.*)$")
TUP = re.compile(r"^\s*\[([^\]]+)\]\s*(=|:=)(.*)$")
funcs, deps = {}, {}
i = 0
while i < len(L):
    m = FUN.match(L[i])
    if m:
        body = [m.group(3)]
        j = i + 1
        while j < len(L) and (not L[j].strip() or L[j][0] in " \t"):
            body.append(L[j])
            j += 1
        funcs[m.group(1)] = set(W.findall(" ".join(body))) - set(x.strip().split()[-1] for x in m.group(2).split(",") if x.strip())
        i = j
        continue
    i += 1
stack = []  # (indent, condition identifiers)
for l in L:
    if not l.strip() or FUN.match(l):
        continue
    ind = len(l) - len(l.lstrip())
    while stack and stack[-1][0] >= ind:
        stack.pop()
    s = l.strip()
    ctx = set().union(*[c for _, c in stack]) if stack else set()
    if re.match(r"^(if|else if|while|for|switch)\b", s) or s == "else":
        stack.append((ind, set(W.findall(s)) - {"if", "else", "while", "for", "switch", "to", "by", "in"}))
        continue
    m = TUP.match(l)
    if m:
        rhs = set(W.findall(m.group(3))) | ctx
        for t in m.group(1).split(","):
            deps.setdefault(t.strip(), set()).update(rhs)
        continue
    m = ASG.match(l)
    if m:
        deps.setdefault(m.group(1), set()).update(set(W.findall(m.group(3))) | ctx)
    elif "array.set(" in s or "array.push(" in s or "array.unshift(" in s:
        a = re.search(r"array\.(?:set|push|unshift)\(\s*([A-Za-z_]\w*)", s)
        if a:
            deps.setdefault(a.group(1), set()).update(set(W.findall(s)) | ctx)
    for fn in W.findall(s):  # a called function's body counts where it is called
        if fn in funcs:
            for tgt in ([m.group(1)] if m else []):
                deps.setdefault(tgt, set()).update(funcs[fn])

targets = sys.argv[1:] or ["shouldBuy", "shouldSell", "tqVeto", "_confDirLabel"]
seen, todo = set(), list(targets)
while todo:
    v = todo.pop()
    if v in seen:
        continue
    seen.add(v)
    todo.extend(deps.get(v, ()))
    for fn in (x for x in deps.get(v, ()) if x in funcs):
        todo.extend(funcs[fn])
probe = ["macroIntelScore", "macroStrengthScore", "mtfConfluenceScore", "liqDestScore", "structPersistScore", "sessionConfMult",
         "regConfCap", "biasLabel", "cotNetPct", "gcValid", "oiState", "vixD", "fvgBullActive", "bullOBActive", "equalHighs",
         "liqSweepBull", "chochBullScore", "mssLabelBull", "bullBOS", "vwap", "bbBasis", "rsiVal", "mrComposite", "avgCorrHealth",
         "_calPLong", "planExpectancy", "tradeQuality", "riskLock", "inNewsWindow", "newsWindow", "regAbnormal", "h2SweepL"]
print(f"slice of {targets}: {len(seen)} identifiers")
for p in probe:
    print(f"  {p:20s} {'IN slice (may influence)' if p in seen else 'NOT in slice (cannot influence)'}")

# ---- per-section report: for each engine section (line range), which of its global writes reach the DECISION
SECT = [(528, "core EMA / VWAP / BB"), (570, "HTF trend stack"), (753, "adaptive-ATR regime"), (769, "mean reversion"),
        (870, "session engine"), (975, "macro / intermarket requests"), (1080, "COT / OI / GC"), (1231, "rates / correlation breakdown"),
        (1391, "weighted trend"), (1416, "structure BOS / CHoCH / MSS"), (1533, "displacement / struct bias"), (1607, "EQH / EQL"),
        (1643, "FVG"), (1698, "order blocks"), (1825, "S/R moved"), (1855, "regime engine"), (1971, "liquidity pools PDH..PML"),
        (2023, "CDH / CDL"), (2051, "structure persistence"), (2113, "liquidity destination"), (2245, "MTF confluence"),
        (2273, "macro intelligence label"), (2351, "statistical evidence"), (2461, "analog placeholders"), (2496, "entry gates"),
        (2603, "trade plan"), (2850, "stats / calibration engine"), (4560, "calibrated P / vetoes / risk lock"), (4955, "dashboard"),
        (5854, "alerts"), (99999, "")]
Lraw = open(F, encoding="utf-8").read().split("\n")
print("\nsection -> global writes that can reach the DECISION / all global writes in the section")
for (a, name), (b, _) in zip(SECT, SECT[1:]):
    w = set()
    for l in L[a - 1:min(b - 1, len(L))]:
        m = TUP.match(l)
        if m and l[0] not in " \t":
            w.update(t.strip() for t in m.group(1).split(","))
            continue
        m = ASG.match(l)
        if m and l[0] not in " \t":
            w.add(m.group(1))
    w = {x for x in w if x and x != "_"}
    inn = sorted(x for x in w if x in seen)
    out = sorted(x for x in w if x not in seen)
    print(f"  L{a:<5d} {name:34s} {len(inn):3d}/{len(w):3d}   not reaching: {', '.join(out[:14])}{' ...' if len(out) > 14 else ''}")
