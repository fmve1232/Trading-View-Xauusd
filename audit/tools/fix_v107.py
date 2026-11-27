#!/usr/bin/env python3
"""v107 (operator, 2026-11-27): the Master v106 still stops with "Script takes too long to calculate" on the free plan
(20 s), with Visuals working beside it. "Fix the master file ... without compromising on the features".

Where the time goes (read from the code, not measured -- TradingView's Profiler cannot report a script that times out):
runStatsEngines() re-scores the stored history against the current market in chunks of 200-300 records on every 4th
bar (15m). On 1500 bars that is about 71,000 passes of a ~150-statement body (`v107_check.py` 1 counts them); nothing
else in the Master comes close (the volume profiles are ~180 loop steps a bar, the other loops 5-12).

Fix: the SCAN (only the scan) runs on the last N bars, input "Statistics scan: last N bars" (default 300, 0 = every bar).
  * Records are still written on EVERY bar, so the scan at the end sees the same stored history as before.
  * 300 bars = 75 scans = about 12 complete passes over the history on 15m; the counts the engine carries between
    passes decay by 0.7 a pass, so 12 passes leave < 2% of any earlier start: the last bar's statistics are the same
    computation on the same records (they were never the website's: the website rescans the whole buffer every bar,
    D-03 / D-04 in quantum/analog.py).
  * Bars older than the window show the statistics warming up (as the first bars of any chart always did): their
    EV / calibration gates use the defaults, so old history can show fewer BUY / SELL marks. Live bars are unaffected.
  * About 19,000 passes instead of 71,000.
The strategy twins (OLDGATES, CHALLENGER, Treatment) and therefore Brief / Diagnostics get `bool statsScanOn = true`
(every bar, as before), so their backtests do not change and the engines stay line-for-line equal (diag_parity).
The new input is the Master's LAST input (F-A93: saved settings keep their positions).
Usage: python3 audit/tools/fix_v107.py (from the repo root), then build_brief.py and build_diag.py"""
M = "artefacts/XAUUSD_Quantum_5_0_Master.pine"
TWINS = {"artefacts/XAUUSD_Quantum_5_0_Strategy.pine": ("// ║  BUILD STAMP — this file last CHANGED in v99   (day rollover = website key)   ║",
                                                        "// ║  BUILD STAMP — this file last CHANGED in v107  (stats scan switch, = all)     ║"),
         "artefacts/XAUUSD_Quantum_5_0_Strategy_OLDGATES.pine": ("// ║  BUILD STAMP — this file last CHANGED in v99   (day rollover = website key)   ║",
                                                                 "// ║  BUILD STAMP — this file last CHANGED in v107  (stats scan switch, = all)     ║"),
         "artefacts/XAUUSD_Quantum_5_0_Strategy_CHALLENGER.pine": ("// ║  BUILD STAMP — this file last CHANGED in v99   (challenger H1; day rollover)  ║",
                                                                   "// ║  BUILD STAMP — this file last CHANGED in v107  (challenger H1; stats switch)  ║")}
RECENT = "recentBars = backtestAllBars or bar_index > last_bar_index - recentBarsLen\n"
GUARD_OLD = "    bool _guard = showStatsEngine and hN > OUTCOME_N * 2 and "
GUARD_NEW = "    bool _guard = showStatsEngine and statsScanOn and hN > OUTCOME_N * 2 and "
TWIN_LINE = ("// v107 (F-A94): the Master scans its statistics on its last N bars only (run time); every twin scans every bar\n"
             "bool statsScanOn = true\n")
MASTER_LINES = ("// v107 (F-A94): runStatsEngines() re-scores the stored history every 4th bar, the bulk of the run time; on the\n"
                "// free plan's 20 s it SCANS on the last statsBars bars only. Records are still written on every bar, so the last\n"
                "// bar's statistics use the same history; older bars show them warming up. 0 = every bar (the twins: always).\n"
                "statsBars = input.int(300, \"Statistics scan: last N bars (0 = all)\", minval=0, group=grpHist)\n"
                "bool statsScanOn = statsBars == 0 or bar_index >= last_bar_index - statsBars\n")


def apply(src, edits):
    out = src
    for o, n in edits:
        assert out.count(o) == 1, (o[:70], out.count(o))
        if "BUILD STAMP" in o:
            assert len(o) == len(n), ("stamp width", len(o), len(n))
        out = out.replace(o, n)
    return out


def master(src):
    return apply(src, [(RECENT, RECENT + MASTER_LINES), (GUARD_OLD, GUARD_NEW),
                       ("// ║  BUILD STAMP — this file last CHANGED in v106  (last 1500 bars: run time)     ║",
                        "// ║  BUILD STAMP — this file last CHANGED in v107  (stats scan: last 300 bars)    ║")])


def twin(path, src):
    return apply(src, [(RECENT, RECENT + TWIN_LINE), (GUARD_OLD, GUARD_NEW), TWINS[path]])


def untwin(src):
    """The exact inverse of twin() on the code (the stamp is left as is): used by refactor_check's arm comparison."""
    return apply(src, [(RECENT + TWIN_LINE, RECENT), (GUARD_NEW, GUARD_OLD)])


if __name__ == "__main__":
    out = {M: master(open(M, encoding="utf-8").read())}
    for p in TWINS:
        out[p] = twin(p, open(p, encoding="utf-8").read())
    for p, s in out.items():
        open(p, "w", encoding="utf-8").write(s)
    print("wrote", ", ".join(out))
