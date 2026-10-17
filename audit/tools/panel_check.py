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


a = L.index(next(l for l in L if l.startswith("if not vSep and barstate.islast")))
blk = []
for l in L[a + 1:]:
    if l and not l.startswith(" "):
        break
    blk.append(l)
card = {args(l, "_h2Row")[1]: args(l, "_h2Row") for l in L if l.strip().startswith("_h2Row(") and "=>" not in l}
term = {args(l, "_tmRow")[1]: args(l, "_tmRow") for l in blk if l.strip().startswith("_tmRow(")}
MAP = {"_h2t": "_tmV", "_h2u": "_tmUp", "_h2d": "_tmDn"}
bad = []
for k, c in card.items():
    if k == '"NOTE"':
        continue
    t = term.get(k)
    col = re.sub(r"\b(_h2[tud])\b", lambda m: MAP[m.group(1)], c[3])
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
rows = [args(l, "_tmRow") for l in blk if l.strip().startswith('_tmRow(r, "') and "f_tmG(" in l]
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
print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- static read of the Pine text; TradingView runtime NOT exercised")
sys.exit(1 if fails else 0)
