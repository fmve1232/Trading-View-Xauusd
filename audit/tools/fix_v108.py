#!/usr/bin/env python3
"""v108 (operator, 2026-11-27): the Master v107 runs only up to ~950 calculated bars (Statistics scan 100) on the free
plan's 20 s, and Density = Spacious tips it over. TradingView's Profiler could not be read on the operator's screen, so
this build removes work that provably changes no output (identical-output rewrites, checked by v108_check.py):

1. H2 BLOCK (byte-identical in the Master, Visuals and Strategy_H2, h2_parity): the 100-bar volume profile was rebuilt
   on EVERY confirmed bar (~180 loop steps with history reads). Its POC / VAH / VAL are read only
     * by h2Long / h2Short / h2Tp1 / h2Tp2, which are false / na unless h2SweepL or h2SweepH is true on that bar, and
     * by displays drawn on the last bar (Visuals' H2 card, strip, panel; h2Next is shown nowhere else),
   so the profile is now rebuilt only when h2SweepL or h2SweepH, or on the last two bars (the last confirmed bar and the
   forming one). Every signal, plan and display reads the same profile of the same 100 bars as before.
2. QUANTILE PASS (all six engine copies): `for _qi = 0 to hN - 1 / array.push(_tmpQ, array.get(hPred, _qi))` -> one
   native `array.copy(array.slice(hPred, 0, hN))`: the same hN values in the same order (hN <= HIST_MAX = size(hPred)).
3. DEFAULTS from the operator's chart (950 bars loaded with Statistics scan 100): Statistics scan 300 -> 150; calc_bars_count of the engine
   copies (Master, Brief, Diagnostics) 1500 -> 1000 (the operator's chart: 950 loaded before items 1-2). Visuals keeps
   1500 (it runs there). A saved Calculated bars / Statistics scan value on the chart is kept by TradingView.
Usage: python3 audit/tools/fix_v108.py (from the repo root), then build_brief.py and build_diag.py"""
A = "artefacts/XAUUSD_Quantum_5_0_"
M = A + "Master.pine"
V = "artefacts/XAUUSD_Quantum_5_5_Visuals.pine"
H2 = A + "Strategy_H2.pine"
TWINS = [A + "Strategy.pine", A + "Strategy_OLDGATES.pine", A + "Strategy_CHALLENGER.pine"]

VP_OLD = "if barstate.isconfirmed and bar_index >= 100 and h2VHi > h2VLo\n"
VP_NEW = ("// v108 (run time): rebuilt only where it is read -- a sweep bar (h2Long / h2Short / plan) or the last two bars\n"
          "// (displays). Same 100 bars, same profile, same signals; the other bars never read it.\n"
          "if barstate.isconfirmed and bar_index >= 100 and h2VHi > h2VLo and (h2SweepL or h2SweepH or bar_index >= last_bar_index - 1)\n")
Q_OLD = ("    float[] _tmpQ = array.new<float>()\n"
         "    for _qi = 0 to hN - 1\n"
         "        array.push(_tmpQ, array.get(hPred, _qi))\n")
Q_NEW = ("    // v108 (run time): the same hN values in the same order, copied natively (was a 1-by-1 loop)\n"
         "    float[] _tmpQ = array.copy(array.slice(hPred, 0, hN))\n")
STAMPS = {
    M: ("// ║  BUILD STAMP — this file last CHANGED in v107  (stats scan: last 300 bars)    ║",
        "// ║  BUILD STAMP — this file last CHANGED in v108  (run time: H2 VP, quantiles)   ║"),
    V: ("// ║  BUILD STAMP — this file last CHANGED in v106  (footprint data off, 1500 bars)║",
        "// ║  BUILD STAMP — this file last CHANGED in v108  (H2 VP where it is read)       ║"),
    H2: ("// ║  BUILD STAMP — this file last CHANGED in v51   (card header version)         ║",
         "// ║  BUILD STAMP — this file last CHANGED in v108  (H2 VP where it is read)      ║"),
    TWINS[0]: ("// ║  BUILD STAMP — this file last CHANGED in v107  (stats scan switch, = all)     ║",
               "// ║  BUILD STAMP — this file last CHANGED in v108  (quantile copy native)         ║"),
    TWINS[1]: ("// ║  BUILD STAMP — this file last CHANGED in v107  (stats scan switch, = all)     ║",
               "// ║  BUILD STAMP — this file last CHANGED in v108  (quantile copy native)         ║"),
    TWINS[2]: ("// ║  BUILD STAMP — this file last CHANGED in v107  (challenger H1; stats switch)  ║",
               "// ║  BUILD STAMP — this file last CHANGED in v108  (challenger H1; quantiles)     ║"),
}


def apply(src, edits):
    out = src
    for o, n in edits:
        assert out.count(o) == 1, (o[:70], out.count(o))
        if "BUILD STAMP" in o:
            assert len(o) == len(n), ("stamp width", len(o), len(n))
        out = out.replace(o, n)
    return out


def master(src):
    return apply(src, [(VP_OLD, VP_NEW), (Q_OLD, Q_NEW),
                       ("max_bars_back=5000, calc_bars_count=1500)", "max_bars_back=5000, calc_bars_count=1000)"),
                       ('statsBars = input.int(300, "Statistics scan', 'statsBars = input.int(150, "Statistics scan'),
                       STAMPS[M]])


def visuals(src):
    return apply(src, [(VP_OLD, VP_NEW), STAMPS[V]])


def h2arm(src):
    return apply(src, [(VP_OLD, VP_NEW), STAMPS[H2]])


def twin(path, src):
    return apply(src, [(Q_OLD, Q_NEW), STAMPS[path]])


def untwin(src):
    """The exact inverse of twin() on the code (stamps are ignored by its users)."""
    return apply(src, [(Q_NEW, Q_OLD)])


if __name__ == "__main__":
    out = {M: master(open(M, encoding="utf-8").read()), V: visuals(open(V, encoding="utf-8").read()),
           H2: h2arm(open(H2, encoding="utf-8").read())}
    for p in TWINS:
        out[p] = twin(p, open(p, encoding="utf-8").read())
    for p, s in out.items():
        open(p, "w", encoding="utf-8").write(s)
    print("wrote", ", ".join(out))
