#!/usr/bin/env python3
"""v104 (operator, 2026-11-14): "dashboard should be re design and re aligned with Master dashboard and master dashboard can
be optimised to save space as POC lines have multiple ... all required information, values and best display of dashboard
with clear chart area" -> chosen: "Re-wrap, keep every value" and "Repeated POC text".

MASTER (fewer tokens, no value removed):
  * The H2 block leaves its own row: it was the only cell of the dashboard's row 3, six lines tall (rows share one height),
    under DECISION. It now follows the DECISION footer in row 2 (3 + 4 = 7 lines, row 2 is already 7 tall from SIGNAL's
    detail), so row 3 is gone: about six tiny lines less dashboard height. The cell takes the H2 colour while a signal
    fires, as the H2 cell did.
  * The H2 text is re-wrapped to 4 lines, each <= 32 characters (the v39 / v55 limit: longer lines clip in these columns):
        H2 DOWN · last 11-12 18:30 / swept 3884.78 / SELL entry 3884.01 SL 3889.08 / TP1 3873.81 · TP2 3858.37
  * The POC number leaves the H2 text (it was repeated): it is shown ONCE, in Visuals' strip cell under the Master's PRICE
    column ("VALUE · POC"), from the same H2 code (h2_parity: byte-identical block), MT5 prices as the Master printed it.
VISUALS:
  * The VALUE tile reads e.g. "under POC 3882.22" under the header "VALUE · POC"; the ticker label no longer repeats it.
  * The dock gap default 24% -> 16% of the chart height (the Master's dashboard is shorter); the operator's saved value is
    kept by TradingView, so set it once in Visuals -> Settings (the input keeps its position, F-A93).
Every output is computed before any file is written. Usage: python3 audit/tools/fix_v104.py (from the repo root)"""
M = "artefacts/XAUUSD_Quantum_5_0_Master.pine"
V = "artefacts/XAUUSD_Quantum_5_5_Visuals.pine"

M_EDITS = [
    ('(h2Long ? "BUY" : "SELL") + " entry " + str.tostring(close + mt5Offset, "#.##") + "\\nSL " + str.tostring(h2Sl + mt5Offset, "#.##") + "\\nTP1 " + str.tostring(h2Tp1 + mt5Offset, "#.##") + " TP2 "',
     '(h2Long ? "BUY" : "SELL") + " entry " + str.tostring(close + mt5Offset, "#.##") + " SL " + str.tostring(h2Sl + mt5Offset, "#.##") + "\\nTP1 " + str.tostring(h2Tp1 + mt5Offset, "#.##") + " · TP2 "'),
    ('string h2Line = "H2 " + (h2TrendUp ? "UP" : h2TrendDn ? "DOWN" : "MIXED") + " · POC " + (na(h2Poc) ? "—" : str.tostring(h2Poc + mt5Offset, "#.##")) + "\\nlast " + h2Last',
     '// v104: four lines <= 32 characters; the POC number is shown once, in Visuals\' strip under PRICE (same H2 code)\n'
     'string h2Line = "H2 " + (h2TrendUp ? "UP" : h2TrendDn ? "DOWN" : "MIXED") + " · last " + h2Last'),
    ('        tcb(8, 2, _decFoot, C_TEXT, _cn, _seSize, _w8)\n'
     '        // v57: H2 in its own cell under DECISION (it crowded and clipped the footer)\n'
     '        tcb(8, 3, h2Line, h2Long ? cBloomBull : h2Short ? cBloomBear : C_TEXT, _cn, _seSize, _w8)\n',
     '        // v57: H2 had its own cell under DECISION (long lines clipped the footer). v104: its lines are <= 32 characters,\n'
     '        // so it follows the footer again and the dashboard loses its row 3 (six lines of height); same values, same colour\n'
     '        tcb(8, 2, _decFoot + "\\n" + h2Line, h2Long ? cBloomBull : h2Short ? cBloomBear : C_TEXT, _cn, _seSize, _w8)\n'),
    ('// ║  BUILD STAMP — this file last CHANGED in v100  (one BUY / SELL alert per run) ║',
     '// ║  BUILD STAMP — this file last CHANGED in v104  (H2 into row 2, POC once)      ║'),
]
V_EDITS = [
    ('f_tk(1, 5, "VALUE", na(h2Poc) ? "building" : close > h2Vah ? "above value" : close < h2Val ? "below value" : close >= h2Poc ? "over POC" : "under POC", na(h2Poc) ? _tmV : close < h2Val ? _tmUp : close > h2Vah ? _tmDn : _tmV, "value · POC " + _h2p(h2Poc),',
     'f_tk(1, 5, "VALUE · POC", na(h2Poc) ? "building" : (close > h2Vah ? "above value " : close < h2Val ? "below value " : close >= h2Poc ? "over POC " : "under POC ") + _h2p(h2Poc), na(h2Poc) ? _tmV : close < h2Val ? _tmUp : close > h2Vah ? _tmDn : _tmV, "value · 100 bars",'),
    ('gdGap = input.int(24, "Dock gap below the Master dashboard', 'gdGap = input.int(16, "Dock gap below the Master dashboard'),
    ('// ║  BUILD STAMP — this file last CHANGED in v103  (strip under the Master)       ║',
     '// ║  BUILD STAMP — this file last CHANGED in v104  (POC once, under PRICE)        ║'),
]


def apply(src, edits):
    out = src
    for o, n in edits:
        assert out.count(o) == 1, (o[:70], out.count(o))
        if "BUILD STAMP" in o:
            assert len(o) == len(n), ("stamp width", len(o), len(n))
        out = out.replace(o, n)
    return out


def master(src):
    return apply(src, M_EDITS)


def visuals(src):
    return apply(src, V_EDITS)


if __name__ == "__main__":
    m, v = master(open(M, encoding="utf-8").read()), visuals(open(V, encoding="utf-8").read())
    open(M, "w", encoding="utf-8").write(m)
    open(V, "w", encoding="utf-8").write(v)
    print("wrote", M, "and", V)
