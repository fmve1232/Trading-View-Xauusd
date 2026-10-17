"""v71: the gold drivers in the Master WITHOUT a user-defined type (F-A68).

The v70 Master queued its cells as DCell records; TradingView reported 103,989 compiled tokens (limit 100,256) where
compile_est.py said 99,616. The 4,373 missing tokens are ~73 raw tokens per DCell.new call (37 calls x 1.6197): the
compiler expands a UDT constructor at every call, like a user function. v71 starts again from the v69 Master (which
compiled) and queues the same cells in plain arrays, one per argument, read back by index.

transform(master_v69_text, fence) -> master_v71_text; refactor_check.py requires
    Master == fix_v71.transform(fix_v68.transform(v66 commit), GD block)   byte for byte.
  1. The 20 tcb(...) calls in f_dashRender push their 7 arguments onto 7 arrays; one loop at the end of f_dashRender
     writes them with tcb's own condition and table.cell. Nothing else writes tblA inside f_dashRender (refactor_check).
  2. The same for the plan panel (8 tcp calls, 4 arrays) and the phone card (9 _bc calls, 5 arrays): each queue is
     declared before its first call and written right after its last, in the same block, by tcp's / _bc's table.cell.
  3. The GD block (byte-identical with Visuals / Brief, macro_check.py E) goes in before the H2 block.
  4. The MACRO detail cell ends with the five drivers as arrows; their full text is that cell's tooltip, set with
     table.cell_set_tooltip where the cell is drawn (desktop / tablet, not Strip or Mobile: tcb's own condition).
"""
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fix_v70 import _calls, TCB_DEF  # noqa: E402

STAMP = "// ║  BUILD STAMP — this file last CHANGED in v71   (drivers, no UDT)"
NEW_DEF = ["// v71: tcb() is queued: f_dashRender pushes each cell's 7 arguments onto _dq* and writes them once, at its end,",
           "// with tcb's own condition and table.cell (TradingView expands every call; v70's DCell records cost more, F-A68)",
           "// v70: a driver's arrow, as the Brief / Visuals grid prints it",
           'f_gdG(float d) => na(d) ? "—" : d >= 2 ? "▲▲" : d > 0 ? "▲" : d <= -2 ? "▼▼" : d < 0 ? "▼" : "≈"']
MACRO_OLD = 'tcb(6, 2, _macroLine2 + " CR" + _si(_crVal) + "%\\n" + _macroRow2, _macro2Col, color.new(_crCol, 88), _seSize, _w6)'
MACRO_NEW = ('tcb(6, 2, _macroLine2 + " CR" + _si(_crVal) + "%\\n" + _macroRow2 + "\\nJPY" + f_gdG(brJd) + " OIL"'
             ' + f_gdG(brOd) + " RY" + f_gdG(brRd) + " BE" + f_gdG(brBd) + " 2Y" + f_gdG(br2d), _macro2Col, color.new(_crCol, 88),'
             ' _seSize, _w6)')
TIP = ('"USDJPY: " + brJh + "\\nOIL: " + brOh + "\\nREAL YLD: " + brRh + "\\nBREAKEVEN: " + brBh + "\\nUS 2Y: " + br2h')
TCP = ("tcp(col, txt, bg, ts) => table.cell(_dashMobile ? tblBrief : tblPlan, _dashMobile ? 1 : col, _dashMobile ? 9 + col : 0, "
       "txt, bgcolor=bg, text_color=C_TEXT, text_size=ts, width=0, text_halign=_dashMobile ? text.align_left : text.align_center)")
BC = ["_bc(int _r, string _k, string _v, color _c, _ts) =>",
      "    table.cell(tblBrief, 0, _r + 1, _k, text_color=#8FA3B8, text_size=_ts, text_halign=text.align_left)",
      "    table.cell(tblBrief, 1, _r + 1, _v, text_color=_c, text_size=_ts, text_halign=text.align_left)"]
# per queue: (pushed argument positions -> arrays, element types, flush lines). Arguments NOT pushed are fixed by the
# call's position and asserted call by call in _queue (CHECK), so the flush rebuilds exactly what the call passed.
Q = {
    # tcb(col, row, txt, tcol, bg, ts, w): 28 cells, unconditional, in this order: the header loop (k = 0..8, row 0),
    # row 1 cols 0..8, row 2 cols 0..8, then (8, 3). So cell j is col j % 9, row int(j / 9) (j < 27), or (8, 3).
    "tcb": ({2: "_dqT", 3: "_dqF", 4: "_dqB"}, {"_dqT": "string", "_dqF": "color", "_dqB": "color"},
            ["int[] _dqW = array.from(_w0, _w1, _w2, _w3, _w4, _w5, _w6, _w7, _w8)",
             "for [j, txt] in _dqT",
             "    int col = j < 27 ? j % 9 : 8",
             "    int row = j < 27 ? int(j / 9) : 3",
             "    if not _dashMobile and (not _dashStrip or row < 2)",
             "        table.cell(tblA, _dashStrip ? col % 3 : col, _dashStrip ? int(col / 3) * 2 + row : row, txt, "
             "text_color=array.get(_dqF, j), bgcolor=array.get(_dqB, j), text_size=_dashStrip ? _szSe : row == 0 ? _hdSize : "
             "row == 1 ? _prSize : _seSize, width=_dashStrip ? 0 : row == 0 ? 0 : array.get(_dqW, col))",
             "if not _dashMobile and not _dashStrip",
             "    table.cell_set_tooltip(tblA, 6, 2, " + TIP + ")"]),
    # tcp(col, txt, bg, ts): 8 calls in one block, col 0..7 in order, ts = _pSz
    "tcp": ({1: "_pqT", 2: "_pqB"}, {"_pqT": "string", "_pqB": "color"},
            ["for [col, txt] in _pqT",
             "    table.cell(_dashMobile ? tblBrief : tblPlan, _dashMobile ? 1 : col, _dashMobile ? 9 + col : 0, txt, "
             "bgcolor=array.get(_pqB, col), text_color=C_TEXT, text_size=_pSz, width=0, "
             "text_halign=_dashMobile ? text.align_left : text.align_center)"]),
    # _bc(r, k, v, c, ts): 9 calls, some conditional: every argument is pushed
    "_bc": ({0: "_bqR", 1: "_bqK", 2: "_bqV", 3: "_bqC", 4: "_bqS"},
            {"_bqR": "int", "_bqK": "string", "_bqV": "string", "_bqC": "color", "_bqS": "string"},
            ["for [i, r] in _bqR",
             "    table.cell(tblBrief, 0, r + 1, array.get(_bqK, i), text_color=#8FA3B8, text_size=array.get(_bqS, i), text_halign=text.align_left)",
             "    table.cell(tblBrief, 1, r + 1, array.get(_bqV, i), text_color=array.get(_bqC, i), text_size=array.get(_bqS, i), "
             "text_halign=text.align_left)"]),
}


def CHECK(name, n, args):
    """the arguments the queue does not push must be what the flush rebuilds for the n-th call"""
    if name == "tcb":
        exp = (["k", "0", None, None, None, "_hdSize", "0"] if n == 0 else
               ["8", "3", None, None, None, "_seSize", "_w8"] if n == 19 else
               [str((n - 1) % 9), str(1 + (n - 1) // 9), None, None, None, "_prSize" if n <= 9 else "_seSize", f"_w{(n - 1) % 9}"])
    elif name == "tcp":
        exp = [str(n), None, None, "_pSz"]
    else:
        exp = [None] * 5
    assert all(e is None or e == a.strip() for e, a in zip(exp, args)), (name, n, args)


def _queue(L, name, lo, hi):
    """Rewrite every call of `name` in L[lo:hi] as pushes; return (first push line, last push line)."""
    pos = Q[name][0]
    sites = []
    k = lo - 1
    while k + 1 < hi:
        k += 1
        l = L[k]
        if l.lstrip().startswith("//") or not _calls(l, name):
            continue
        ind = l[:len(l) - len(l.lstrip())]
        calls = _calls(l, name)
        assert len(calls) == 1 and l.lstrip().startswith(name + "("), (k, l)
        s, f, args = calls[0]
        CHECK(name, len(sites), args)
        tail = l[f:]
        assert tail == "" or tail.lstrip().startswith("//"), (k, tail)
        pushes = [ind + f"array.push({a}, {args[i].strip()})" for i, a in pos.items()]
        pushes[0] += tail
        L[k:k + 1] = pushes
        hi += len(pushes) - 1
        sites.append((k, k + len(pushes) - 1))
    return sites[0][0], sites[-1][1]


def transform(text, fence):
    L = text.split("\n")
    i = next(k for k, l in enumerate(L[:6]) if "BUILD STAMP" in l)
    L[i] = STAMP + " " * (len(L[i + 1]) - len(STAMP) - 1) + "║"
    t = L.index(TCB_DEF[0])
    assert tuple(L[t:t + 3]) == TCB_DEF, "tcb is not the v69 definition"
    L[t:t + 3] = NEW_DEF
    k = L.index(TCP)
    L[k] = "// v71: tcp() is queued (_pq*) and written after its last call with this same table.cell"
    k = L.index(BC[0])
    assert L[k:k + 3] == BC
    L[k:k + 3] = ["// v71: _bc() is queued (_bq*) and written after its last call with these same two table.cells"]
    # 1. the dashboard, inside f_dashRender
    h = next(k for k, l in enumerate(L) if l.startswith("f_dashRender() =>"))
    e = h + 1
    while e < len(L) and (L[e].startswith(" ") or not L[e].strip()):
        e += 1
    while L[e - 1].strip() == "":
        e -= 1
    n = sum(1 for k in range(h + 1, e) if MACRO_OLD in L[k])
    assert n == 1
    L[h + 1:e] = [l.replace(MACRO_OLD, MACRO_NEW) for l in L[h + 1:e]]
    n0 = len(L)
    first, last = _queue(L, "tcb", h + 1, e)
    e += len(L) - n0
    assert sum(1 for k in range(h + 1, e) if "array.push(_dqT" in L[k]) == 20
    assert L[e - 1].strip() == "true", L[e - 1]
    L[e - 1:e - 1] = ["    " + x for x in Q["tcb"][2]]
    L[h + 1:h + 1] = ["    // v71: the cells, written once at the end (tcb's condition and table.cell)"] + [
        f"    {t_}[] {a} = array.new<{t_}>()" for a, t_ in Q["tcb"][1].items()]
    # 2. plan panel and phone card: declare before the first call's enclosing statement at the flush's level
    for name in ("tcp", "_bc"):
        first, last = _queue(L, name, 0, len(L))
        ind = len(L[last]) - len(L[last].lstrip())
        d = first
        while len(L[d]) - len(L[d].lstrip()) > ind or L[d].lstrip().startswith("//"):
            d -= 1
        L[last + 1:last + 1] = [" " * ind + x for x in Q[name][2]]
        L[d:d] = [" " * ind + f"{t_}[] {a} = array.new<{t_}>()" for a, t_ in Q[name][1].items()]
    a = L.index("// H2-BEGIN")
    L[a:a] = fence.split("\n")
    return "\n".join(L)


if __name__ == "__main__":
    import subprocess
    import fix_v68 as F68
    V = open("artefacts/XAUUSD_Quantum_5_5_Visuals.pine", encoding="utf-8").read()
    fence = V[V.index("// GD-BEGIN"):V.index("// GD-END") + len("// GD-END")]
    M = "artefacts/XAUUSD_Quantum_5_0_Master.pine"
    v66 = subprocess.run(["git", "show", "a5fc12ce:" + M], capture_output=True, text=True, check=True).stdout
    out = transform(F68.transform(v66, inline_one_call=False), fence)
    open(M, "w", encoding="utf-8").write(out)
    print("wrote the v71 Master")
