"""v68 (F-A66): fit TradingView's compiled-token limit, which v67 exceeded (the Master reported 100,335 / 100,256).
TradingView expands every user-function call, so a helper called many times, or a large function called once (its
definition and its expansion both count, on the evidence of the compiles of v23 and v67), costs more than the lexical
count suggests. Nothing is removed: each call becomes the code it expands to.

transform(master_v66_text) -> master_v68_text, used both to build v68 and by refactor_check.py, which requires
transform(v66 commit) == the Master as it stands, and checks that every expanded helper uses each parameter once.
  1. f_dashData1 / f_dashData2 / f_dashRender (one call each) -> their body at the call site, inside `if true`
     (keeps each body's locals in their own scope, as the function did);
  2. _gS / _gC / _gF (i) -> array.get(gDashS / gDashC / gDashF, i);  tc(...) -> tcb(..., color(na), ...);
     _m(x) -> str.tostring(x + mt5Offset, "#.##")   (not inside the H2 block, which stays byte-identical).
"""
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402

STAMP = "// ║  BUILD STAMP — this file last CHANGED in v68   (fits the compiler limit)"
HELPERS = {
    "_gS": (["i"], "array.get(gDashS, i)"), "_gC": (["i"], "array.get(gDashC, i)"), "_gF": (["i"], "array.get(gDashF, i)"),
    "tc": (["col", "row", "txt", "tcol", "ts", "w"], "tcb(col, row, txt, tcol, color(na), ts, w)"),
    "_m": (["_x"], 'str.tostring(_x + mt5Offset, "#.##")'),
}
ONE_CALL = ("f_dashData1", "f_dashData2", "f_dashRender")


def _span(L, name):
    h = next(i for i, l in enumerate(L) if l.startswith(name + "() =>"))
    j = h + 1
    while j < len(L) and (L[j].startswith(" ") or not L[j].strip()):
        j += 1
    while L[j - 1].strip() == "":
        j -= 1
    return h, j


def _expand(l, name, params, body):
    pat = re.compile(r"(?<![\w.])" + re.escape(name) + r"\(")
    while True:
        m = pat.search(l)
        if not m:
            return l
        d, j = 0, m.end() - 1
        while True:
            c = l[j]
            if c == '"':
                j = l.index('"', j + 1)
            elif c == "(":
                d += 1
            elif c == ")":
                d -= 1
                if d == 0:
                    break
            j += 1
        args = P._split_args(l[m.end():j])
        out = body
        for p_, a in zip(params, args):
            out = re.sub(r"(?<![\w.])" + re.escape(p_) + r"(?!\w)", lambda _m: a, out)
        l = l[:m.start()] + out + l[j + 1:]


def transform(text):
    L = text.split("\n")
    i = next(k for k, l in enumerate(L[:6]) if "BUILD STAMP" in l)
    L[i] = STAMP + " " * (len(L[i + 1]) - len(STAMP) - 1) + "║"
    bodies = {}
    for f in ONE_CALL:
        h, j = _span(L, f)
        bodies[f] = L[h + 1:j]
    for f in sorted(ONE_CALL, key=lambda f: _span(L, f)[0], reverse=True):
        h, j = _span(L, f)
        L[h:j] = ["// v68: " + f + "() was called once; its body now sits at the call site (scoped in `if true`), so the",
                  "// compiler no longer counts it twice. Same statements, same order, same scope rules."]
    for f in ONE_CALL:
        c = [k for k, l in enumerate(L) if l == "    " + f + "()"]
        assert len(c) == 1, (f, c)
        L[c[0]:c[0] + 1] = ["    if true    // v68: was " + f + "() (one call)"] + [("    " + b if b.strip() else b) for b in bodies[f]]
    a, b = L.index("// H2-BEGIN"), L.index("// H2-END")
    for name, (params, body) in HELPERS.items():
        for k, l in enumerate(L):
            if a <= k <= b or l.startswith(name + "(") or l.lstrip().startswith("//"):
                continue
            L[k] = _expand(l, name, params, body)
        code = "\n".join(x for x in L if not x.lstrip().startswith("//"))
        if len(re.findall(r"(?<![\w.])" + re.escape(name) + r"\(", code)) == 1:   # only the definition is left
            k = next(i for i, x in enumerate(L) if x.startswith(name + "("))
            L[k] = "// v68: " + name + "() was written out at each call site (TradingView expands every call; same expression each time)"
    return "\n".join(L)


def params_once(text):
    """each expanded helper's definition in the OLD text uses every parameter exactly once (so expansion is exact)"""
    bad = []
    for name, (params, body) in HELPERS.items():
        d = next(l for l in text.split("\n") if l.startswith(name + "("))
        rhs = d.split("=>", 1)[1].split("//")[0]
        got = [x.split()[-1] for x in d[len(name) + 1:d.index(")")].split(",")]
        if got != params or any(len(re.findall(r"(?<![\w.])" + re.escape(p_) + r"(?!\w)", rhs)) != 1 for p_ in params) \
                or rhs.strip() != body:
            bad.append(name)
    return bad


if __name__ == "__main__":
    import subprocess
    src = subprocess.run(["git", "show", "a5fc12ce:artefacts/XAUUSD_Quantum_5_0_Master.pine"], capture_output=True,
                         text=True, check=True).stdout
    open("artefacts/XAUUSD_Quantum_5_0_Master.pine", "w", encoding="utf-8").write(transform(src))
    print("wrote the v68 Master from the v66 commit")
