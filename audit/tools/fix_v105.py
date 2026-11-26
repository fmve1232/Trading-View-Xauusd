#!/usr/bin/env python3
"""v105 (operator, 2026-11-26, screenshots): the Master and Visuals stop with "Script takes too long to calculate"
(TradingView's run-time limit: 20 s on the Basic plan; both scripts had shown the "Heavy script" warning since v39 / v68).

Fix (TradingView's own advice: "limit the bars it runs on"): every chart script calculates on the last CALC_BARS bars
only, `calc_bars_count = 3000` in its declaration. Run time grows with the number of bars, so this lowers it in
proportion to the bars the chart had loaded; no formula, threshold, input or display changes.
  * 3000 bars = about 31 trading days on 15m (the decision timeframe), 10 days on 5m, 4 months on 1H.
  * Fits the engine: the longest chart-timeframe window is 200 bars; the stats engine's ring buffer is 3000 records on
    15m (HIST_MAX) and fills from the first ~70 bars; weekly levels need two weeks of bars; daily / weekly / monthly
    requests read their own timeframe's history.
  * What it changes on the screen: statistics counted over the loaded history (the engine's history sample, the H2 card's
    record, the BRACKET row, the CHURN count) count the last 3000 bars, not every bar the plan loaded. The forward record is
    the website's (A7) and is typed in, so it does not change.
Applied to the four chart scripts: Master and Visuals here; Brief and Diagnostics through build_brief.py / build_diag.py.
The strategy arms (repo set, not on the chart) are unchanged, so the A/B hunk counts stay as they are.
Usage: python3 audit/tools/fix_v105.py (from the repo root), then build_brief.py and build_diag.py"""
M = "artefacts/XAUUSD_Quantum_5_0_Master.pine"
V = "artefacts/XAUUSD_Quantum_5_5_Visuals.pine"
CALC_BARS = 3000

M_EDITS = [
    ('indicator("XAUUSD Quantum 5.0", overlay=true, max_lines_count=500, max_labels_count=500, max_boxes_count=500, max_bars_back=5000)',
     f'indicator("XAUUSD Quantum 5.0", overlay=true, max_lines_count=500, max_labels_count=500, max_boxes_count=500, max_bars_back=5000, calc_bars_count={CALC_BARS})'),
    ('// ║  BUILD STAMP — this file last CHANGED in v104  (H2 into row 2, POC once)      ║',
     '// ║  BUILD STAMP — this file last CHANGED in v105  (last 3000 bars: run time)     ║'),
]
V_EDITS = [
    ('max_boxes_count = 500, max_bars_back = 5000)',
     f'max_boxes_count = 500, max_bars_back = 5000, calc_bars_count = {CALC_BARS})'),
    ('// ║  BUILD STAMP — this file last CHANGED in v104  (POC once, under PRICE)        ║',
     '// ║  BUILD STAMP — this file last CHANGED in v105  (last 3000 bars: run time)     ║'),
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
