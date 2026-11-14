#!/usr/bin/env python3
"""v103 (operator, 2026-11-14): "Too much text on Visuals chart please optimize it as i can't see candles now. Make it
more professional and add bars like master but placement shouldn't overlap with master" -> "please ensure real switches
exist in visuals but display with the master file. Alignment & design".

  * A STRIP directly under the Master's dashboard, in the docks' table (same anchor, same gap, the Master's nine column
    widths x Density), so each Visuals cell sits under the Master column it belongs to: 0 MARKET daily regime, 1 BIAS
    trend, 2 SIGNAL H2, 3 STRUCTURE last sweep, 4 LIQUIDITY room, 5 PRICE value, 6 MACRO macro (= the Master's),
    7 RISK checks, 8 DECISION the forward record. Two rows like the Master: a grey header, a coloured value; the long
    explanations are hover tooltips. The tiles are the bottom ticker's (one f_tk call draws both), so the strip can
    never show a different value from the ticker.
  * Real switches (group LAYOUT): the strip (default ON) and the detail panel (default OFF). The ticker, the full
    dock cards (liquidity, gold drivers, H2) and every panel section keep their own switches; their DEFAULTS move to
    off / "In the panel" so the candles are clear. Nothing is removed: every option still selects the v102 layout.
  * The optional dock cards start two rows lower while the strip is on (it takes rows 1-2 of the same table).
Every output is computed before any file is written. Usage: python3 audit/tools/fix_v103.py (from the repo root)"""
V = "artefacts/XAUUSD_Quantum_5_5_Visuals.pine"

EDITS = [
    # the LAYOUT switches, before the terminal panel group
    ('grpTm = "TERMINAL PANEL (v73)"\n',
     '// v103 (operator 2026-11-14: "too much text ... can\'t see candles"; "real switches in Visuals but display with the\n'
     '// Master file. Alignment & design"): a strip under the Master\'s dashboard is the default view; the detail panel,\n'
     '// the bottom ticker and the full dock cards are off by default and each has its own switch (nothing removed).\n'
     'grpLy = "LAYOUT (v103): what shows on the chart"\n'
     'stShow = input.bool(true, "Strip under the Master\'s dashboard (one cell per Master column)", group = grpLy, tooltip = '
     '"Two rows directly under the Master\'s dashboard, on its nine columns: daily regime, trend, H2, last sweep, room, '
     'value, macro, checks, forward record. Hover a cell for the detail. Set Dash Mode / Text Size / Density as in the '
     'Master; the gap is \'Dock gap below the Master dashboard\'.")\n'
     'pnShow = input.bool(false, "Detail panel (bottom left)", group = grpLy, tooltip = "The full terminal panel: market at '
     'a glance, candle, H2 card, drivers, liquidity, checks & risk, bracket, record. Its sections keep their own switches.")\n'
     'grpTm = "TERMINAL PANEL (v73)"\n'),
    # defaults: ticker, docks
    ('glPlace = input.string("Bottom ticker", "Glance placement",', 'glPlace = input.string("In the panel", "Glance placement",'),
    ('gdDock = input.string("Under the Master\'s MACRO", "Gold drivers placement",', 'gdDock = input.string("In the panel / card", "Gold drivers placement",'),
    ('h2Dock = input.string("Under the Master\'s DECISION", "H2 card placement",', 'h2Dock = input.string("In the panel / card", "H2 card placement",'),
    ('lqDock = input.string("Under the Master\'s LIQUIDITY", "Liquidity & sweeps placement",', 'lqDock = input.string("Hidden", "Liquidity & sweeps placement",'),
    # strip flag; the candle card leaves the strip's corner too
    ('bool dkOn = gdDocked or lqDocked or h2Docked\n',
     'bool stOn = stShow and dashMode != "Mobile"   // v103: the strip follows the docks\' rule (no dock on a phone layout)\n'
     'bool dkOn = gdDocked or lqDocked or h2Docked or stOn\n'),
    # the detail panel switch
    ('    if not vSep and barstate.islast and (glShow and not tkOn or showCandle',
     '    if pnShow and not vSep and barstate.islast and (glShow and not tkOn or showCandle'),
    # dock table: two more rows; cards start below the strip
    ('    table.cell(t, col, r, txt, text_color = tc, bgcolor = _dbg, text_size = _dsz, width = int(array.get(_dkW, col) * _dw), text_halign = text.align_left)\n',
     '    table.cell(t, col, r + (stOn ? 2 : 0), txt, text_color = tc, bgcolor = _dbg, text_size = _dsz, width = int(array.get(_dkW, col) * _dw), text_halign = text.align_left)   // v103: below the strip\n'),
    ('var table dkT = table.new(dashMode == "Tablet" ? position.top_left : position.top_right, 9, 10, border_width = 0, frame_width = 0)',
     'var table dkT = table.new(dashMode == "Tablet" ? position.top_left : position.top_right, 9, 12, border_width = 0, frame_width = 0)'),
    ('    table.clear(dkT, 0, 0, 8, 9)\n', '    table.clear(dkT, 0, 0, 8, 11)\n'),
    ('if (gdDocked or lqDocked or h2Docked and h2Show) and barstate.islast\n', 'if (gdDocked or lqDocked or h2Docked and h2Show or stOn) and barstate.islast\n'),
    # f_tk draws the ticker tile and / or the strip cell
    ('f_tk(int c, string v, color vc, string lbl, string tip) =>\n'
     '    table.cell(tkT, c, 1, v,',
     '// v103: one tile, two places: the bottom ticker (tkOn) and the strip under the Master (stOn), column sc, header sh\n'
     'f_tk(int c, int sc, string sh, string v, color vc, string lbl, string tip) =>\n'
     '    if stOn\n'
     '        table.cell(dkT, sc, 1, sh, text_color = color.new(#7D8FA3, 0), bgcolor = color.new(#131A24, 20), text_size = size.tiny, width = int(array.get(_dkW, sc) * _dw), tooltip = lbl + "\\n" + tip)\n'
     '        table.cell(dkT, sc, 2, v, text_color = vc, bgcolor = _dbg, text_size = _dsz, width = int(array.get(_dkW, sc) * _dw), tooltip = lbl + "\\n" + tip)\n'
     '    if tkOn\n'
     '        table.cell(tkT, c, 1, v,'),
    ('    table.cell(tkT, c, 2, lbl, text_color = color.new(#7D8FA3, 0), bgcolor = color.new(#0F141B, 0), text_size = size.tiny, tooltip = tip)\n',
     '        table.cell(tkT, c, 2, lbl, text_color = color.new(#7D8FA3, 0), bgcolor = color.new(#0F141B, 0), text_size = size.tiny, tooltip = tip)\n'),
    ('    if tkOn and barstate.islast\n        [_tUpP, _tUpN] = f_glNear(true, close)', '    if (tkOn or stOn) and barstate.islast\n        [_tUpP, _tUpN] = f_glNear(true, close)'),
    ('        f_tk(0, h2TrendUp ?', '        f_tk(0, 1, "TREND 1H·4H·1D", h2TrendUp ?'),
    ('        f_tk(1, na(h2Poc) ?', '        f_tk(1, 5, "VALUE", na(h2Poc) ?'),
    ('        f_tk(2, "↓"', '        f_tk(2, 4, "ROOM $" + str.tostring(glMoveA, "#"), "↓"'),
    ('        f_tk(3, mxGlyph', '        f_tk(3, 6, "MACRO · = Master", mxGlyph'),
    ('        f_tk(4, na(pvLastLvl) ?', '        f_tk(4, 3, "LAST SWEEP", na(pvLastLvl) ?'),
    ('        f_tk(5, h2SigDir == 0 ?', '        f_tk(5, 2, "H2 SIGNAL", h2SigDir == 0 ?'),
    ('            f_tk(_c, rgTxt,', '            f_tk(_c, 0, "DAILY REGIME", rgTxt,'),
    ('        f_tk(_c, _ckTx == ""', '        f_tk(_c, 7, "CHECKS", _ckTx == ""'),
    # the record: banner in the ticker, a cell under DECISION in the strip
    ('        if lgShow\n            table.cell(tkT, 0, 0,', '        if lgShow and stOn\n'
     '            table.cell(dkT, 8, 1, "RECORD · " + str.replace_all(lgArm, " (deciding)", ""), text_color = color.new(#7D8FA3, 0), bgcolor = color.new(#131A24, 20), text_size = size.tiny, width = int(array.get(_dkW, 8) * _dw), tooltip = lgLine + " · " + tfNote + (lg2Show ? "\\n" + lg2Line + (lg2Note != "" ? " · " + lg2Note : "") : ""))\n'
     '            table.cell(dkT, 8, 2, lgVerdict, text_color = lgLv == -1 ? _tmDn : lgLv == 1 ? _tmUp : color.new(#FFB74D, 0), bgcolor = _dbg, text_size = _dsz, width = int(array.get(_dkW, 8) * _dw), tooltip = lgLine + " · " + tfNote)\n'
     '        if lgShow and tkOn\n            table.cell(tkT, 0, 0,'),
    ('        for c = 0 to 7\n            table.cell(tkT, c, 3, "", height = tkLift, bgcolor = color(na))\n',
     '        if tkOn\n            for c = 0 to 7\n                table.cell(tkT, c, 3, "", height = tkLift, bgcolor = color(na))\n'),
    ('// ║  BUILD STAMP — this file last CHANGED in v102  (records: web.8 live)          ║',
     '// ║  BUILD STAMP — this file last CHANGED in v103  (strip under the Master)       ║'),
]


def fix(src):
    out = src
    for o, n in EDITS:
        assert out.count(o) == 1, (o[:70], out.count(o))
        out = out.replace(o, n)
    return out


if __name__ == "__main__":
    s = open(V, encoding="utf-8").read()
    o = fix(s)
    a = [l for l in s.split("\n") if "BUILD STAMP" in l][0]
    b = [l for l in o.split("\n") if "BUILD STAMP" in l][0]
    assert len(a) == len(b), "stamp width"
    open(V, "w", encoding="utf-8").write(o)
    print("wrote", V)
