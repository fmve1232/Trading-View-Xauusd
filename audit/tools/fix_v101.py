#!/usr/bin/env python3
"""v101 (F-A92): Visuals failed to compile with CE10295 "The main body of the script is too long" (operator's
screenshot, 2026-11-04, the v99 file). compile_est's main-body model (lexical tokens outside functions, calibrated on
the Master) said 23,962 against a 26,538 ceiling, so TradingView measures the main body differently; the last Visuals
confirmed to compile (v85, 8feb2166b) had 14,865 on that measure.

Fix, as the compiler suggests: ten DISPLAY-ONLY top-level blocks (the terminal panel, the ticker, the S/R and tag
drawings, the H2 card, the three docks, the drivers card, the structure labels) each become a function defined
exactly where the block was and called on the next line. Each block:
  * reassigns no global (Pine forbids `:=` on a global inside a function), checked here;
  * calls no ta.* / request.* (their state would become per call site), checked here;
  * calls no plot / bgcolor / fill / alertcondition (not allowed in a local scope);
  * declares nothing that later code reads (everything declared in an `if` block was already local to it).
The function is defined where the block was, so every global it reads is declared above it, as before. The body is
the block indented by four spaces, unchanged, plus `0` so a mixed-type `if` is never the return value. Output is the
same by construction; `unfix()` is the exact inverse (checked by v101_check.py). Every output is computed before
any file is written. Usage: python3 audit/tools/fix_v101.py  (from the repo root)"""
import re

V = "artefacts/XAUUSD_Quantum_5_5_Visuals.pine"
# (first line, the next code line or None, function name)
BLOCKS = [
    ('if not vSep and barstate.islast and (glShow and not tkOn or showCandle or h2Show and not h2Docked or gdPos != "Hidden" and not gdDocked or lqInPanel or ckPanel)', None, "f_v101Panel"),
    ("if tkOn and barstate.islast", None, "f_v101Ticker"),
    ("if barstate.islast", "    while array.size(tgLn) > 0", "f_v101Tags"),
    ("if vSep and h2Show and not h2Docked and barstate.islast", None, "f_v101H2Card"),
    ("if h2Docked and h2Show and barstate.islast", None, "f_v101H2Dock"),
    ("if gdDocked and barstate.islast", None, "f_v101GdDock"),
    ("if lqDocked and barstate.islast", None, "f_v101LqDock"),
    ("if barstate.islast", "    // F-031: this passed ta.atr(14) INSIDE the barstate.islast branch, so the call was", "f_v101Levels"),
    ('if vSep and barstate.islast and gdPos != "Hidden" and not gdDocked', None, "f_v101GdCard"),
    ("if showStruct and barstate.isconfirmed", None, "f_v101Struct"),
]
HEAD = "// v101 (F-A92): display-only block wrapped in a function (CE10295, main body too long); same code, same order"
STAMP_OLD = "// ║  BUILD STAMP — this file last CHANGED in v99   (rollover; NOT A GATE row)     ║"
STAMP_NEW = "// ║  BUILD STAMP — this file last CHANGED in v101  (main body: 10 blocks wrapped) ║"
FORBID = re.compile(r"\b(plot|plotshape|plotchar|bgcolor|fill|alertcondition|hline)\(")


def find(L, first, second):
    hits = [i for i, l in enumerate(L) if l == first and (second is None or (i + 1 < len(L) and L[i + 1] == second))]
    assert len(hits) == 1, (first, second, len(hits))
    i = hits[0]
    j = i + 1
    while j < len(L) and (not L[j].strip() or L[j][0] in " \t"):
        j += 1
    while L[j - 1].strip() == "":          # trailing blank lines stay outside
        j -= 1
    return i, j


def check(block):
    code = [l for l in block if l.strip() and not l.lstrip().startswith("//")]
    declared = set()
    for l in code:
        m = re.match(r"^\s*(?:var\s+)?(?:[A-Za-z_][\w.<>\[\]]*\s+)?([A-Za-z_]\w*)\s*=(?!=)", l)
        if m and not re.match(r"^\s*(if|for|while|else)\b", l):
            declared.add(m.group(1))
        m = re.match(r"^\s*for\s+(\w+)\s*=", l)
        if m:
            declared.add(m.group(1))
        m = re.match(r"^\s*\[([^\]]+)\]\s*=", l)
        if m:
            declared |= {x.strip().split()[-1] for x in m.group(1).split(",")}
    asg = {m.group(1) for l in code for m in re.finditer(r"\b([A-Za-z_]\w*)\s*(?::=|\+=|-=|\*=|/=)", l)} - declared
    assert not asg, ("global reassignment", sorted(asg))
    assert not any(re.search(r"\bta\.\w+\(|request\.\w+\(", l) for l in code), "ta / request call"
    assert not any(FORBID.search(re.sub(r'"[^"]*"', "", l)) for l in code), "plot-family call"
    assert not any(re.match(r"^\s*var\s", l) for l in code), "var inside"


def fix(src):
    L = src.split("\n")
    assert L.count(STAMP_OLD) == 1
    L[L.index(STAMP_OLD)] = STAMP_NEW
    spans = []
    for first, second, name in BLOCKS:
        i, j = find(L, first, second)
        check(L[i:j])
        spans.append((i, j, name))
    for i, j, name in sorted(spans, reverse=True):
        body = ["    " + l if l.strip() else l for l in L[i:j]]
        L[i:j] = [HEAD, f"{name}() =>"] + body + ["    0", f"{name}()"]
    return "\n".join(L)


def unfix(src):
    """the exact inverse: the v100 text back (v101_check.py proves fix(unfix(x)) == x and unfix(fix(v100)) == v100)"""
    L = src.split("\n")
    if STAMP_NEW in L:                     # a later build has its own stamp: left as it is
        L[L.index(STAMP_NEW)] = STAMP_OLD
    for _, _, name in BLOCKS:
        a = L.index(f"{name}() =>")
        assert L[a - 1] == HEAD
        b = L.index(f"{name}()", a)
        assert L[b - 1] == "    0"
        body = [l[4:] if l.startswith("    ") else l for l in L[a + 1:b - 1]]
        L[a - 1:b + 1] = body
    return "\n".join(L)


if __name__ == "__main__":
    src = open(V, encoding="utf-8").read()
    out = fix(src)
    assert unfix(out) == src, "inverse mismatch"
    open(V, "w", encoding="utf-8").write(out)
    print("wrote", V)
