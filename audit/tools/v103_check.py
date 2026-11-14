#!/usr/bin/env python3
"""v103: Visuals' strip under the Master's dashboard -- alignment, one source, the default view, the switches.

  1 ALIGNMENT: the Master's nine column headers are read from its own code (`for [k, h] in array.from("MARKET", ...`);
    each strip cell (an f_tk call's strip column, and the RECORD cell) sits under the column it belongs to:
    MARKET daily regime, BIAS trend, SIGNAL H2, STRUCTURE last sweep, LIQUIDITY room, PRICE value, MACRO macro,
    RISK checks, DECISION record -- every column used exactly once. The dock table is the Master's anchor (top right;
    top left on Tablet) with the Master's column widths (panel_check 5 holds _dkW = the Master's).
  2 ONE SOURCE: f_tk writes the strip and the ticker from the same value and colour (v, vc), so they cannot disagree.
  3 COMPACT: every strip value and header is one line (no "\\n"); the detail is in the tooltips.
  4 DEFAULT VIEW (the inputs' defaults, the layout flags executed as written): the strip is on; the detail panel, the
    bottom ticker and the three dock cards are off; the panel's own condition is false.
  5 SWITCHES: each section has its own input.
  6 controls: a tile moved to the wrong column, and the panel switched on by default, are detected.
Usage: python3 audit/tools/v103_check.py"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402

V = open("artefacts/XAUUSD_Quantum_5_5_Visuals.pine", encoding="utf-8").read()
M = open("artefacts/XAUUSD_Quantum_5_0_Master.pine", encoding="utf-8").read()
fails = 0
WANT = {"DAILY REGIME": "MARKET", "TREND 1H·4H·1D": "BIAS", "H2 SIGNAL": "SIGNAL", "LAST SWEEP": "STRUCTURE",
        "ROOM": "LIQUIDITY", "VALUE": "PRICE", "MACRO · = Master": "MACRO", "CHECKS": "RISK", "RECORD": "DECISION"}


def report(ok, msg):
    global fails
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {msg}")


def args(line, name):
    i = line.index(name + "(") + len(name) + 1
    out, depth, cur, q = [], 0, "", False
    for ch in line[i:]:
        if ch == '"':
            q = not q
        if not q and ch in "([":
            depth += 1
        if not q and ch in ")]":
            if depth == 0:
                out.append(cur.strip())
                return out
            depth -= 1
        if not q and ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
            continue
        cur += ch
    return out


def strip_cells(src):
    cells = []
    for l in src.split("\n"):
        s = l.strip()
        if s.startswith("f_tk(") and "=>" not in s:
            a = args(s, "f_tk")
            head = re.match(r'"([^"]*)"', a[2])
            cells.append((int(a[1]), head.group(1) if head else a[2], a[3]))
        if s.startswith("table.cell(dkT, 8, 1, "):
            cells.append((8, "RECORD", args(s, "table.cell")[3]))
    return cells


def alignment(src):
    hdr = re.search(r'for \[k, h\] in array\.from\(((?:"[A-Z]+", ){8}"[A-Z]+")\)', M)
    H = re.findall(r'"([A-Z]+)"', hdr.group(1))
    bad, used = [], []
    for col, head, _ in strip_cells(src):
        key = next((k for k in WANT if head.startswith(k) or (k == "ROOM" and head.startswith('"ROOM')) or head.startswith(k)), None)
        if key is None and head.startswith('"ROOM'):
            key = "ROOM"
        if key is None or H[col] != WANT[key]:
            bad.append((head, col, H[col] if col < len(H) else "?"))
        used.append(col)
    return H, bad, sorted(used)


H, bad, used = alignment(V)
report(not bad and used == list(range(9)), f"1 alignment: the Master's columns {H}; strip cells under {used}"
       + ("" if not bad else f"; MISPLACED {bad}"))
anchor = 'var table dkT = table.new(dashMode == "Tablet" ? position.top_left : position.top_right, 9, 12,' in V
m_anchor = re.search(r'tblA := table\.new\(_dashStrip \? position\.top_center : _mode2 == "Desktop" \? position\.top_right : position\.top_left, _dashStrip \? 3 : 9,', M) is not None   # the Master: Desktop top right, else top left (9 columns); the strip is off on Mobile
report(anchor and m_anchor, "1 the strip is in the docks' table, on the Master's anchor (top right; top left on Tablet)")

ftk = V[V.index("f_tk(int c, int sc, string sh, string v, color vc, string lbl, string tip) =>"):]
ftk = ftk[:ftk.index("\nif barstate.islast")]
one = (re.search(r"table\.cell\(dkT, sc, 2, v, text_color = vc", ftk) and re.search(r"table\.cell\(tkT, c, 1, v,", ftk)
       and "if stOn" in ftk and "if tkOn" in ftk)
report(bool(one), "2 one source: f_tk draws the strip value (dkT, row 2) and the ticker value (tkT, row 1) from the same v / vc")

multi = [(h, v) for _, h, v in strip_cells(V) if "\\n" in h or "\\n" in v]
report(not multi, f"3 compact: {len(strip_cells(V))} strip headers and values, none spans two lines" + ("" if not multi else f": {multi}"))


def defaults(src):
    e = P.Env()
    for name in ("stShow", "pnShow", "glShow", "vLayout", "glPlace", "dashMode", "gdDock", "gdPos", "h2Dock", "lqDock",
                 "showCandle", "h2Show", "ckPanel"):
        m = re.search(rf'^{name}\s*=\s*input\.(bool|string)\(([^,]+),', src, re.M)
        v = m.group(2).strip()
        e[name] = (v == "true") if m.group(1) == "bool" else v.strip('"')
    for l in src.split("\n"):
        if re.match(r"^bool (vSep|tkOn|gdDocked|h2Docked|lqDocked|stOn|lqInPanel) = ", l):
            P.run([l.split("//")[0].replace("bool ", "", 1)], e)
    cond = next(l.strip() for l in src.split("\n") if l.strip().startswith("if pnShow and not vSep and barstate.islast and ("))
    e["barstate.islast"] = True
    panel = P.evaluate(cond[3:], e)
    return e, bool(panel)


e, panel = defaults(V)
dv = dict(strip=e["stOn"], panel=panel, ticker=e["tkOn"], lq=e["lqDocked"], gd=e["gdDocked"], h2=e["h2Docked"])
report(dv == dict(strip=True, panel=False, ticker=False, lq=False, gd=False, h2=False),
       f"4 default view (inputs' defaults, flags executed as written): {dv}")

sw = ["stShow", "pnShow", "glShow", "glPlace", "lqDock", "gdDock", "gdPos", "h2Dock", "h2Show", "showCandle", "ckPanel",
      "lgShow", "lg2Show", "rgShow"]
miss = [s for s in sw if not re.search(rf"^{s}\s*=\s*input\.", V, re.M)]
report(not miss, f"5 switches: {len(sw) - len(miss)} of {len(sw)} sections have their own input ({', '.join(sw)})")

mut = V.replace('f_tk(0, 1, "TREND 1H·4H·1D"', 'f_tk(0, 2, "TREND 1H·4H·1D"')
assert mut != V
_, b2, _ = alignment(mut)
mut2 = V.replace('pnShow = input.bool(false,', 'pnShow = input.bool(true,')
assert mut2 != V
_, p2 = defaults(mut2)
report(bool(b2) and p2, f"6 controls: trend moved under SIGNAL detected {bool(b2)}; panel on by default detected {p2}")
print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- Pine text read and its layout flags executed; TradingView rendering NOT checked")
sys.exit(1 if fails else 0)
