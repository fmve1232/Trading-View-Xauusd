#!/usr/bin/env python3
"""v106 (operator, 2026-11-27, screenshots): v105 still stops with "Script takes too long to calculate" -- the Master
alone and Visuals alone, each the only script on the chart. The same code ran on 2026-11-14, so the load or TradingView's
limit changed; both scripts were already near it. Two changes, both measured by the next screenshot only:

VISUALS: the footprint's three request.security_lower_tf calls (1-minute intrabars of EVERY bar: about 15 x the chart's
bars of data, loaded three times) ran even while the footprint is OFF (its default since v81). Now ONE tuple request,
and while the footprint is off it asks for the chart's own timeframe (one intrabar per bar), so no 1-minute history is
loaded. The arrays are read only under `if showFP`, so every output is identical; with the footprint ON the values are
the same three series as before.
ALL FOUR CHART SCRIPTS: calc_bars_count 3000 -> 1500 (about 16 trading days on 15m, 5 days on 5m, 2 months on 1H).
Run time falls in proportion. The longest chart-timeframe window is 200 bars and weekly levels need two weeks (~920 15m
bars), so every value still has its history; history-counted statistics count the last 1500 bars (the engine's sample on
15m fills about half of its 3000-record buffer). Brief / Diagnostics through their builders.
Usage: python3 audit/tools/fix_v106.py (from the repo root), then build_brief.py and build_diag.py"""
M = "artefacts/XAUUSD_Quantum_5_0_Master.pine"
V = "artefacts/XAUUSD_Quantum_5_5_Visuals.pine"
OLD, NEW = 3000, 1500

M_EDITS = [
    (f'max_bars_back=5000, calc_bars_count={OLD})', f'max_bars_back=5000, calc_bars_count={NEW})'),
    ('// ║  BUILD STAMP — this file last CHANGED in v105  (last 3000 bars: run time)     ║',
     '// ║  BUILD STAMP — this file last CHANGED in v106  (last 1500 bars: run time)     ║'),
]
V_EDITS = [
    (f'max_bars_back = 5000, calc_bars_count = {OLD})', f'max_bars_back = 5000, calc_bars_count = {NEW})'),
    ('array<float> ltfC = request.security_lower_tf(syminfo.tickerid, fpTf, close)\n'
     'array<float> ltfO = request.security_lower_tf(syminfo.tickerid, fpTf, open)\n'
     'array<float> ltfV = request.security_lower_tf(syminfo.tickerid, fpTf, volume)\n',
     '// v106 (run time, F-A94): ONE request, and 1-minute data only while the footprint is ON; off, it asks for the chart\'s\n'
     '// own timeframe (one intrabar per bar). The arrays are read only under `if showFP`, so the output is unchanged.\n'
     '[ltfC, ltfO, ltfV] = request.security_lower_tf(syminfo.tickerid, showFP ? fpTf : timeframe.period, [close, open, volume])\n'),
    ('// ║  BUILD STAMP — this file last CHANGED in v105  (last 3000 bars: run time)     ║',
     '// ║  BUILD STAMP — this file last CHANGED in v106  (footprint data off, 1500 bars)║'),
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
