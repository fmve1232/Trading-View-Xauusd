#!/usr/bin/env python3
"""v73: Visuals' terminal panel shows what the three v72 cards show (static, on the Pine text as written).

  1. H2: every card row _h2Row(n, KEY, text, colour) has a terminal row _tmRow(r, KEY, text', colour') with the SAME
     text expression, and the same colour once the palette names are mapped (_h2t/_h2u/_h2d -> _tmV/_tmUp/_tmDn);
     the card's NOTE row is the panel's footer.
  2. Gold drivers: f_tmG / f_tmC are the drivers card's glyph and colour expressions; the five rows (Standard) and
     the one-line tape (Compact) read the five fenced values and their texts.
  3. Candle: every value the candle card prints (O H L C, range, range/ATR, ATR%, direction, RVOL, ADX, DI+ / DI-) is
     printed by the MARKET section.
  4. Rows: the most rows the panel can write (every branch taken) fit its table.
Usage: python3 audit/tools/panel_check.py"""
import re
import sys

V = open("artefacts/XAUUSD_Quantum_5_5_Visuals.pine", encoding="utf-8").read()
L = V.split("\n")
fails = 0


def report(ok, msg):
    global fails
    fails += not ok
    print(("PASS  " if ok else "FAIL  ") + msg)


def args(line, name):
    s = line.strip()
    assert s.startswith(name + "(") and s.endswith(")")
    out, d, cur, q = [], 0, "", False
    for c in s[len(name) + 1:-1]:
        if c == '"':
            q = not q
        if not q and c in "([":
            d += 1
        if not q and c in ")]":
            d -= 1
        if c == "," and d == 0 and not q:
            out.append(cur.strip())
            cur = ""
        else:
            cur += c
    return out + [cur.strip()]


a = L.index(next(l for l in L if l.startswith("if not vSep and barstate.islast and (")))
blk = []
for l in L[a + 1:]:
    if l and not l.startswith(" "):
        break
    blk.append(l)
card = {args(l, "_h2Row")[1]: args(l, "_h2Row") for l in L if l.strip().startswith("_h2Row(") and "=>" not in l}
term = {args(l, "_tmRow")[1]: args(l, "_tmRow") for l in blk if l.strip().startswith("_tmRow(")}
MAP = {"_h2t": "_tmV", "_h2u": "_tmUp", "_h2d": "_tmDn", "_h2s": "_tmS"}
bad = []
for k, c in card.items():
    if k == '"NOTE"':
        continue
    t = term.get(k)
    col = re.sub(r"\b(_h2[tuds])\b", lambda m: MAP[m.group(1)], c[3])
    if not t or t[2] != c[2] or t[3] != col:
        bad.append(k)
foot = next((l for l in blk if "H2 record: the website" in l), None)
report(not bad and len(card) == 10 and foot is not None,
       f"H2: the card's {len(card) - 1} rows have identical text and colour in the panel; NOTE is the footer" + (f" -- differ: {bad}" if bad else ""))

gd = "\n".join(L[next(i for i, l in enumerate(L) if l.startswith("f_gdRow(")):][:4])
glyph = '(na(d) ? "—" : d >= 2 ? "▲▲" : d > 0 ? "▲" : d <= -2 ? "▼▼" : d < 0 ? "▼" : "≈")'
col = 'na(d) ? color.new(#787B86, 0) : d > 0 ? color.new(#26A69A, 0) : d < 0 ? color.new(#EF5350, 0) : color.new(#B2B5BE, 0)'
tg = next(l for l in L if l.startswith("f_tmG(float d) => ")).split("=> ", 1)[1]
tc = next(l for l in L if l.startswith("f_tmC(float d) => ")).split("=> ", 1)[1]
rows = [args(l, "_tmRow") for l in blk if l.strip().startswith('_tmRow(r, "') and "f_tmG(" in l
        and not re.match(r'_tmRow\(r, "\d ', l.strip())]   # v79: the glance rows ("5 MACRO") are checked in 7
want = [('"USDJPY "', "brJ"), ('"OIL "', "brO"), ('"REAL YLD "', "brR"), ('"BREAKEVEN "', "brB"), ('"US 2Y "', "br2")]
rows_ok = [(r_[1], r_[2], r_[3]) for r_ in rows] == [(f"{n} + f_tmG({v}d)", f"{v}h", f"f_tmC({v}d)") for n, v in want]
tape = next((l for l in blk if '"JPY" + f_tmG(brJd)' in l), "")
tape_ok = all(f"f_tmG({v}d)" in tape and f"{v}h" in tape for _, v in want)
report(f"({tg})" == glyph and col in gd and glyph in gd and tc == col and rows_ok and tape_ok,
       "gold drivers: same glyphs and colours as the drivers card; 5 rows (Standard) and the tape + hover text (Compact)")

ct = next(l for l in L if l.strip().startswith("string cTxt = "))
need = {"open": "open", "high": "high", "low": "low", "close": "close", "atr14": "atr14", "volSma20": "volSma20",
        "adxValV": "adxValV", "_diPV": "_diPV", "_diMV": "_diMV", "ATR%": "ATR%", "RVOL": "RVOL", "▲ UP": "▲ UP", "▼ DOWN": "▼ DOWN"}
mk = "\n".join(l for l in blk[:blk.index(next(l for l in blk if "if h2Show" in l))])
miss = [k for k, v in need.items() if (v in ct or k in ("volSma20", "atr14")) and v not in mk]
report(not miss, "candle: every value of the candle card is printed in the MARKET section" + (f" -- missing {miss}" if miss else ""))

n = sum(l.strip() == "r += 1" for l in blk) + 1
size = int(re.search(r"var table tblV = table\.new\(.*?, 2, (\d+),", V).group(1))
clear = re.search(r"table\.clear\(tblV, 0, 0, 1, (\d+)\)", V)
report(n <= size and clear and int(clear.group(1)) == size - 1,
       f"rows: at most {n} written (every branch), table has {size}, clear covers all")
# ---- 5 (v74): the docked drivers line up under the Master's MACRO column, read from the Master's own code
M = open("artefacts/XAUUSD_Quantum_5_0_Master.pine", encoding="utf-8").read()
mw = [int(x) for x in re.findall(r"int _w\d = int\((\d+) \* _densW\)", M)]
mdens = re.search(r"float _densW = (.*)", M).group(1).strip()
vw = [int(x) for x in re.search(r"int\[\] _dkW = array\.from\(([\d, ]+)\)", V).group(1).split(",")]
vdens = re.search(r"float _dw = (.*)", V).group(1).strip()
manch = re.search(r"tblA := table\.new\((.*?), _dashStrip \? 3", M).group(1)
anch = re.findall(r"var table (\w+) = table\.new\((.*?), 9, \d+, border_width = 0, frame_width = 0\)", V)
# v77: ONE dock table, the only table that can take the top-right corner (TradingView shows one table per position per
# script: v76's three top-right tables showed only the last); the candle card leaves it while a dock is on
tops = re.findall(r"table\.new\([^\n]*?position\.top_right", V)
cand = 'candlePos == "Top Right" ? (dkOn ? position.middle_right : position.top_right)' in V
vanch = (len(anch) == 1 and anch[0][1] == 'dashMode == "Tablet" ? position.top_left : position.top_right' and len(tops) == 2
         and cand and "bool dkOn = gdDocked or lqDocked or h2Docked" in V)
mframe = "border_width=0, frame_width=0" in re.search(r"tblA := table\.new\(.*", M).group(0)
msz = re.search(r'(?m)^string _szSe = (.*)', M).group(1).split("//")[0].strip()
vsz = re.search(r'string _dsz = (.*)', V).group(1).strip()
spacer = "for [c, w] in _dkW\n        table.cell(t, c, 0, \"\", width = int(w * _dw), height = c == col ? gap : 0)" in V
dcell = "width = int(array.get(_dkW, col) * _dw)" in V
cells = re.findall(r'f_dkCell\(dkT, 6, (\d), "([A-Z 0-9]+) " \+ f_tmG\((\w+)\) \+ "\\n" \+ (\w+), f_tmC\((\w+)\)\)', V)
want = [("2", "USDJPY", "brJd", "brJh", "brJd"), ("3", "OIL", "brOd", "brOh", "brOd"), ("4", "REAL YLD", "brRd", "brRh", "brRd"),
        ("5", "BREAKEVEN", "brBd", "brBh", "brBd"), ("6", "US 2Y", "br2d", "br2h", "br2d")]
ok5 = (vw == mw and len(mw) == 9 and vdens == mdens.replace("_densW", "_dw") and mframe
       and manch.endswith('_mode2 == "Desktop" ? position.top_right : position.top_left')
       and vanch and spacer and dcell and msz == vsz and cells == want)
report(ok5, f"dock: Master column widths {mw} x Density, anchor, no border / frame and detail text size reproduced; "
       "the five driver cells read their own value and text, in the MACRO column (6)")
# ---- 6 (v75): the H2 dock (under DECISION, col 8) shows the card's rows; the liquidity dock (col 4) and the panel's
# LIQUIDITY section show all eight levels and both sweeps
dock = {}
for l in L:
    if l.strip().startswith("f_dkCell(dkT, 8, "):
        x = args(l, "f_dkCell")
        m = re.match(r'"([A-Z]+)  " \+ (.*)$', x[3])
        if m:
            dock['"' + m.group(1) + '"'] = (m.group(2), x[4])
# v78: SIGNAL is split into two 2-line cells: the split text must be exactly "SIGNAL  " + the card's text, and both
# cells take the card's SIGNAL colour (mapped); every other row is a single cell as before
sig = card['"SIGNAL"']
sp = re.search(r'array<string> _sp = str\.split\("SIGNAL  " \+ (.*), "\\n"\)', V)
sgc = re.search(r"color _sgc = (.*)", V)
sig_ok = (sp and sp.group(1) == sig[2] and sgc and sgc.group(1).strip() == re.sub(r"\b(_h2[tuds])\b", lambda m: MAP[m.group(1)], sig[3])
          and "f_dkCell(dkT, 8, 2, _ns > 1 ? array.get(_sp, 0) + \"\\n\" + array.get(_sp, 1) : array.get(_sp, 0), _sgc)" in V
          and 'f_dkCell(dkT, 8, 3, _ns > 2 ? array.join(array.slice(_sp, 2, _ns), "\\n") : "", _sgc)' in V)
dock['"SIGNAL"'] = (sig[2], re.sub(r"\b(_h2[tuds])\b", lambda m: MAP[m.group(1)], sig[3])) if sig_ok else None
bad6 = [k for k, c in card.items() if k not in ('"NOTE"', '"SESSION"', '"HISTORY"', '"VOLUME"')
        and dock.get(k) != (c[2], re.sub(r"\b(_h2[tuds])\b", lambda m: MAP[m.group(1)], c[3]))]
note = any("f_dkCell(dkT, 8, 9, " in l and "H2 record: the website" in l for l in L)
# v78: the band's rows share heights: every body cell of the three docks is at most 2 lines, headers 1
blines = [l for l in L if l.strip().startswith(("f_dkCell(dkT, ", "table.cell(dkT, 6, 1,"))]
hdr1 = all(l.count("\\n") == 0 for l in blines if re.search(r"\(dkT, \d, 1, ", l))
body2 = all(re.sub(r'str\.replace_all\([^)]*\)', "", l).count("\\n") <= 1 for l in blines if not re.search(r"\(dkT, \d, 1, ", l)) and len(blines) == 21
lv = ["pdh", "pdl", "pwh", "pwl", "pmh", "pml", "cdh", "cdl"]
lqd = "\n".join(l for l in L if "f_dkCell(dkT, 4," in l)
lqp = "\n".join(blk)
lv_ok = all(f'f_lv("{x.upper()}", {x})' in lqd and f'f_lv("{x.upper()}", {x})' in lqp for x in lv) and all(
    x in lqd and x in lqp for x in ("pvLastSweep", "h2LastSweep"))
report(not bad6 and len(dock) == 6 and note and lv_ok and hdr1 and body2,
       "H2 dock: the card's 6 rows, same text and colour (SIGNAL split in two cells), + its note; liquidity dock and panel "
       "section: 8 levels + both sweeps; every dock cell <= 2 lines, headers 1 (rows share heights)"
       + (f" -- differ: {bad6}" if bad6 else ""))
# ---- 7 (v79): MARKET AT A GLANCE -- executed: the nearest-level search and the ROOM marks against a reference;
# statically: every row reads the value it names, and the two engine rows point at the Master instead of a number
import os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pine_exec as P  # noqa: E402
fn = []
i0 = next(i for i, l in enumerate(L) if l.startswith("f_glNear(bool up, float from) =>"))
for l in L[i0:]:
    if fn and l and not l.startswith(" "):
        break
    fn.append(l)
NAMES = ["PDH", "PDL", "PWH", "PWL", "PMH", "PML", "CDH", "CDL"]
VARS = [x.lower() for x in NAMES]
rng = random.Random(79)
bad7 = n7 = 0
def near_ref(lv, up, frm):
    c = [(abs(p - frm), k) for k, p in enumerate(lv) if p is not None and (p > frm if up else p < frm)]
    return (None, "") if not c else (lv[min(c)[1]], NAMES[min(c)[1]])
body = "\n".join(fn)
try:
    env = P.Env()
    P.define(fn, env)
    exec_ok = True
except Exception as ex:   # pine_exec cannot run it: say so, do not pass silently
    exec_ok = False
    print("      note: f_glNear not executable by pine_exec:", ex)
if exec_ok:
    for _ in range(3000):
        close_ = 4130 + rng.gauss(0, 20)
        lv = [None if rng.random() < 0.15 else 4130 + rng.gauss(0, 40) for _ in NAMES]
        env.update({v: (P.NA if x is None else x) for v, x in zip(VARS, lv)})   # globals: the defining scope
        e = P.Env(funcs=env.funcs, close=close_)
        for up in (True, False):
            frm = close_ if rng.random() < 0.5 else close_ + rng.gauss(0, 10)
            got = P.evaluate(f"f_glNear({'true' if up else 'false'}, {frm!r})", e)
            want = near_ref(lv, up, frm)
            gp = None if P.isna(got[0]) else got[0]
            n7 += 1
            bad7 += not ((gp is None and want[0] is None) or (gp is not None and want[0] is not None and abs(gp - want[0]) < 1e-9 and got[1] == want[1]))
gl = "\n".join(l for l in blk if "_tmRow(r, \"" in l and re.search(r'_tmRow\(r, "\d ', l))
static7 = all(x in gl for x in ('"1 TREND", h2Trend', '"3 HEADING", h2Next', 'pvLastSweep', '_upN', '_dnN', '"5 MACRO"', 'f_tmC(_gNet)',
                                'glMoveA', 'glMoveB', 'sessManipProb', 'sessContProb', 'h2SigOut', "the Master's BIAS + DECISION",
                                "the Master's SIGNAL cell")) and gl.count('_tmRow(r, "') == 8
# the ROOM row, executed: ✓ $B when the room reaches the target, ✓ $A when it reaches the minimum, else ✗ (+ the next level)
room = args(next(l for l in blk if l.strip().startswith('_tmRow(r, "6 ROOM"')), "_tmRow")[2]
nr = br = 0
for _ in range(3000):
    A_, B_ = rng.choice([(10.0, 20.0), (5.0, 15.0)])
    up_, dn_ = (P.NA if rng.random() < 0.1 else rng.choice([A_, B_, A_ - 0.01, B_ - 0.01, abs(rng.gauss(12, 10))])
                for _k in range(2))   # the exact boundaries too: "at least $10" includes $10
    e = P.Env(_upR=up_, _dnR=dn_, glMoveA=A_, glMoveB=B_, close=4130.0, _up2P=4160.0, _dn2P=4100.0, _up2N="PWH", _dn2N="PWL")
    txt = P.evaluate(room, e)
    upline, dnline = txt.split("\n")
    for r_, line in ((up_, upline), (dn_, dnline.split(" · plan")[0])):
        nr += 1
        want = "—" if P.isna(r_) else f"✓ ${B_:g}" if r_ >= B_ else f"✓ ${A_:g}" if r_ >= A_ else f"✗ <${A_:g}"
        br += want not in line or (want.startswith("✗") and "(then " not in line)
report(br == 0, f"glance ROOM: ✓ target / ✓ minimum / ✗ + next level, executed ({nr} cases, mismatches {br})")
report(exec_ok and bad7 == 0 and n7 > 0 and static7,
       f"glance: nearest tagged level above / below executed vs reference ({n7} cases, mismatches {bad7}); 8 rows, each "
       "reads its value; bias and odds point at the Master's cells")
print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- static read of the Pine text; TradingView runtime NOT exercised")
sys.exit(1 if fails else 0)
