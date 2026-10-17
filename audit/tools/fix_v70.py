"""v70: the gold drivers in the Master (operator: "all macros in the Master"), paid for without removing anything.

transform(master_v69_text, fence) -> master_v70_text; refactor_check.py requires
    Master == fix_v70.transform(fix_v68.transform(v66 commit), GD block)   byte for byte.
  1. The 20 tcb(...) calls in f_dashRender are queued as DCell records and written by f_dashFlush, whose table.cell
     is tcb's, field for field (TradingView expands every call: 20 copies of tcb cost ~2,000 compiled tokens; the
     queue keeps one). Nothing else writes the table inside f_dashRender, so the final table is the same.
  2. The GD block (byte-identical with Visuals / Brief, macro_check.py E) goes in before the H2 block.
  3. The MACRO detail cell shows the five drivers as arrows; their full text is that cell's tooltip.
  4. The same queue for the plan panel (8 tcp calls) and the phone card (9 _bc calls): each is flushed right after its
     last call, in the same block, by tcp's / _bc's own table.cell; nothing else writes those tables in between.
"""
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402

STAMP = "// ║  BUILD STAMP — this file last CHANGED in v70   (gold drivers in Master)"
TCB_DEF = ("tcb(col, row, txt, tcol, bg, ts, w) =>",
           "    if not _dashMobile and (not _dashStrip or row < 2)",
           "        table.cell(tblA, _dashStrip ? col % 3 : col, _dashStrip ? int(col / 3) * 2 + row : row, txt, text_color=tcol, bgcolor=bg, text_size=_dashStrip ? _szSe : ts, width=_dashStrip ? 0 : w)")
NEW_DEF = ["// v70: one dashboard cell. f_dashRender queues its cells and f_dashFlush writes them with tcb's own table.cell",
           "// (same condition, coordinates, colours, size, width); a cell may carry a hover tooltip (tip).",
           "type DCell",
           "    int col",
           "    int row",
           "    string txt",
           "    color tcol",
           "    color bg",
           "    string ts",
           "    int w",
           "    string tip = na",
           "    string val = na",
           "f_dashFlush(DCell[] cells) =>",
           "    for c in cells",
           "        if not _dashMobile and (not _dashStrip or c.row < 2)",
           "            table.cell(tblA, _dashStrip ? c.col % 3 : c.col, _dashStrip ? int(c.col / 3) * 2 + c.row : c.row, c.txt, text_color=c.tcol, bgcolor=c.bg, text_size=_dashStrip ? _szSe : c.ts, width=_dashStrip ? 0 : c.w, tooltip=c.tip)",
           "// v70: the plan panel's and the phone card's queued cells, written with tcp's / _bc's own table.cell",
           "f_planFlush(DCell[] q) =>",
           "    for c in q",
           "        table.cell(_dashMobile ? tblBrief : tblPlan, _dashMobile ? 1 : c.col, _dashMobile ? 9 + c.col : 0, c.txt, bgcolor=c.bg, text_color=C_TEXT, text_size=c.ts, width=0, text_halign=_dashMobile ? text.align_left : text.align_center)",
           "f_cardFlush(DCell[] q) =>",
           "    for c in q",
           "        table.cell(tblBrief, 0, c.row + 1, c.txt, text_color=#8FA3B8, text_size=c.ts, text_halign=text.align_left)",
           "        table.cell(tblBrief, 1, c.row + 1, c.val, text_color=c.tcol, text_size=c.ts, text_halign=text.align_left)",
           "// v70: a driver's arrow, as the Brief / Visuals grid prints it",
           'f_gdG(float d) => na(d) ? "—" : d >= 2 ? "▲▲" : d > 0 ? "▲" : d <= -2 ? "▼▼" : d < 0 ? "▼" : "≈"']
MACRO_OLD = 'tcb(6, 2, _macroLine2 + " CR" + _si(_crVal) + "%\\n" + _macroRow2, _macro2Col, color.new(_crCol, 88), _seSize, _w6)'
MACRO_NEW = ('array.push(_cells, DCell.new(6, 2, _macroLine2 + " CR" + _si(_crVal) + "%\\n" + _macroRow2 + "\\nJPY" + f_gdG(brJd) + " OIL"'
             ' + f_gdG(brOd) + " RY" + f_gdG(brRd) + " BE" + f_gdG(brBd) + " 2Y" + f_gdG(br2d), _macro2Col, color.new(_crCol, 88),'
             ' _seSize, _w6, "USDJPY: " + brJh + "\\nOIL: " + brOh + "\\nREAL YLD: " + brRh + "\\nBREAKEVEN: " + brBh + "\\nUS 2Y: " + br2h))')


def _calls(l, name):
    """[(start, end, args)] of each call of `name` in line l"""
    out, pat, i = [], re.compile(r"(?<![\w.])" + re.escape(name) + r"\("), 0
    while True:
        m = pat.search(l, i)
        if not m:
            return out
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
        out.append((m.start(), j + 1, P._split_args(l[m.end():j])))
        i = j + 1


def transform(text, fence):
    L = text.split("\n")
    i = next(k for k, l in enumerate(L[:6]) if "BUILD STAMP" in l)
    L[i] = STAMP + " " * (len(L[i + 1]) - len(STAMP) - 1) + "║"
    t = L.index(TCB_DEF[0])
    assert tuple(L[t:t + 3]) == TCB_DEF, "tcb is not the v69 definition"
    L[t:t + 3] = NEW_DEF
    h = next(k for k, l in enumerate(L) if l.startswith("f_dashRender() =>"))
    e = h + 1
    while e < len(L) and (L[e].startswith(" ") or not L[e].strip()):
        e += 1
    while L[e - 1].strip() == "":
        e -= 1
    n = 0
    for k in range(h + 1, e):
        l = L[k]
        if l.lstrip().startswith("//"):
            continue
        if MACRO_OLD in l:
            L[k] = l.replace(MACRO_OLD, MACRO_NEW)
            n += 1
            continue
        for s, f, args in reversed(_calls(l, "tcb")):
            assert len(args) == 7, (k, args)
            l = l[:s] + "array.push(_cells, DCell.new(" + ", ".join(args) + "))" + l[f:]
            n += 1
        L[k] = l
    assert n == 20, n
    L[h + 1:h + 1] = ["    DCell[] _cells = array.new<DCell>()    // v70: the cells, written once by f_dashFlush below"]
    e += 1
    L[e:e] = ["    f_dashFlush(_cells)"]
    # 4. plan panel (tcp) and phone card (_bc): queue, then flush after the last call in the same block
    TCP = "tcp(col, txt, bg, ts) => table.cell(_dashMobile ? tblBrief : tblPlan, _dashMobile ? 1 : col, _dashMobile ? 9 + col : 0, txt, bgcolor=bg, text_color=C_TEXT, text_size=ts, width=0, text_halign=_dashMobile ? text.align_left : text.align_center)"
    BC = ["_bc(int _r, string _k, string _v, color _c, _ts) =>",
          "    table.cell(tblBrief, 0, _r + 1, _k, text_color=#8FA3B8, text_size=_ts, text_halign=text.align_left)",
          "    table.cell(tblBrief, 1, _r + 1, _v, text_color=_c, text_size=_ts, text_halign=text.align_left)"]
    k = L.index(TCP)
    L[k] = "// v70: tcp() is queued (DCell) and written by f_planFlush, with this same table.cell"
    k = L.index(BC[0])
    assert L[k:k + 3] == BC
    L[k:k + 3] = ["// v70: _bc() is queued (DCell) and written by f_cardFlush, with these same two table.cells"]
    for name, q, flush, mk in (("tcp", "_pq", "f_planFlush", lambda a_: f"DCell.new({a_[0]}, 0, {a_[1]}, C_TEXT, {a_[2]}, {a_[3]}, 0)"),
                               ("_bc", "_bq", "f_cardFlush", lambda a_: f"DCell.new(0, {a_[0]}, {a_[1]}, {a_[3]}, color(na), {a_[4]}, 0, val = {a_[2]})")):
        sites = [k for k, l in enumerate(L) if not l.lstrip().startswith("//") and _calls(l, name)]
        first, last = sites[0], sites[-1]
        ind = len(L[last]) - len(L[last].lstrip())
        for k in sites:
            l = L[k]
            for s_, f_, args in reversed(_calls(l, name)):
                l = l[:s_] + f"array.push({q}, " + mk(args) + ")" + l[f_:]
            L[k] = l
        # declare the queue at the flush's indentation, before the first call's enclosing statement at that level
        d = first
        while len(L[d]) - len(L[d].lstrip()) > ind or L[d].lstrip().startswith("//"):
            d -= 1
        L[last + 1:last + 1] = [" " * ind + f"{flush}({q})"]
        L[d:d] = [" " * ind + f"DCell[] {q} = array.new<DCell>()"]
    a = L.index("// H2-BEGIN")
    L[a:a] = fence.split("\n")
    return "\n".join(L)


if __name__ == "__main__":
    V = open("artefacts/XAUUSD_Quantum_5_5_Visuals.pine", encoding="utf-8").read()
    fence = V[V.index("// GD-BEGIN"):V.index("// GD-END") + len("// GD-END")]
    M = "artefacts/XAUUSD_Quantum_5_0_Master.pine"
    src = open(M, encoding="utf-8").read()          # read first: opening for "w" would truncate it
    out = transform(src, fence)
    open(M, "w", encoding="utf-8").write(out)
    print("wrote the v70 Master")
