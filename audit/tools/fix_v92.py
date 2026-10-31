"""v92 (independent v90 audit, operator-approved 2026-10-31: "Go ahead with B-03 and B-09"). DISPLAY / RISK-TRACKER only.

B-09 (Master)  The entry gate's `recentBars = bar_index > last_bar_index - recentBarsLen` (120 bars) also limited the
     signals the RISK LOCK counts, so after a reload on 5m (120 bars = 10 h) or 1m (2 h) the lock forgot losses from
     earlier the same NY day and could lift. The Master draws nothing historically and recentBars is always true on the
     live bar, so the window changed nothing visible except that. The Master now carries the twins' own switch,
     byte-identical (`backtestAllBars`, default ON: the gate is evaluated on every bar, as in the arms and on the
     website); OFF restores the 120-bar behaviour. The live DECISION is unchanged on every bar where it is shown.
B-03 (Visuals) No file raised the cost at news: Visuals' COST / RISK rows now multiply spread + slippage by a
     News-window cost multiplier (default 3x: the low end of the operator's stated 3-5x design, not fitted to any
     result; replace with the broker's figures) on bars inside the dated NFP / CPI / FOMC windows, so the lot size
     is computed on the news-time cost; the NEWS row states that the engine itself neither blocks nor re-costs news.
     The ENGINE part (dated calendar in newsWindow, FOMC, a news block by default) changes signals: it is frozen
     engine code shared with the website (A7) and is NOT done here; it needs a website amendment."""

M_PAIRS = [
    ("recentBars = bar_index > last_bar_index - recentBarsLen\n",
     "// v92 (B-09): the twins' switch, byte-identical. ON: the gate runs on every bar, so the risk lock counts every signal\n"
     "// of the NY day after a reload (it forgot those older than 120 bars on 5m / 1m). Nothing historical is drawn here.\n"
     'backtestAllBars = input.bool(true, "Backtest all bars (ignore Signal Lookback Bars)", group=grpCore, tooltip="ON for backtests: '
     "the entry gate is evaluated on every historical bar. OFF reproduces the live indicator's behaviour, where signals are shown "
     "only in the last 'Signal Lookback Bars'.\")\n"
     "recentBars = backtestAllBars or bar_index > last_bar_index - recentBarsLen\n"),
]
# Paid for (Master headroom < 80 tokens, F-A72) by two identical-output rewrites in the RISK cell, executed in v92_check:
# `not na(_liveCostATR)` is always true (its definition returns 0.0 when adaptiveATR is na or 0), and
# math.abs(tpSL - tpEntry) IS tpDist (f_tradePlan computes tpDist = math.abs(tpEntry - tpSL) after its last tpSL write).
M_PAIRS += [
    ("float _costToTargetPct = tpDist > 0 and not na(_liveCostATR) ? _liveCostATR * adaptiveATR / tpDist * 100.0 : 0.0",
     "float _costToTargetPct = tpDist > 0 ? _liveCostATR * adaptiveATR / tpDist * 100.0 : 0.0"),
    ("str.tostring(math.abs(tpSL - tpEntry) / adaptiveATR,", "str.tostring(tpDist / adaptiveATR,"),
]
STAMP_M = "// ║  BUILD STAMP — this file last CHANGED in v92   (risk lock: every bar)"

V_PAIRS = [
    ('nwShade = input.bool(true, "Shade the news windows", group = grpCk)\n',
     'nwShade = input.bool(true, "Shade the news windows", group = grpCk)\n'
     'nwCostMult = input.float(3.0, "News window: cost multiplier (spread + slippage)", minval = 1.0, maxval = 10.0, step = 0.5, '
     'group = grpCk, tooltip = "v92 (B-03): inside an NFP / CPI / FOMC window the COST and RISK rows charge spread + slippage x this '
     "(commission is per lot and does not widen). Default 3: the low end of the 3-5x design, not fitted to any result; set it from "
     "your broker's news-time spreads. Display only: the Master's engine does not re-cost or block news.\")\n"),
    ("float ckCost = (ckSpread + 2.0 * slippagePts) + commissionL / math.max(pointValue, 1.0)\n",
     "// v92 (B-03): spread + slippage widen in a dated news window (nwBarIn); commission does not.\n"
     "float ckCost = (ckSpread + 2.0 * slippagePts) * (nwBarIn ? nwCostMult : 1.0) + commissionL / math.max(pointValue, 1.0)\n"),
    ('" pts round trip = "', '" pts round trip" + (nwBarIn and nwCostMult > 1.0 ? " (NEWS ×" + str.tostring(nwCostMult, "#.#") + ")" : "") + " = "'),
    ('" min · official BLS / Fed dates"', '" min · official BLS / Fed dates · the Master\'s engine neither blocks nor re-costs news"'),
]
STAMP_V = "// ║  BUILD STAMP — this file last CHANGED in v92   (news-time cost)"


def _apply(text, pairs, stamp):
    for old, new in pairs:
        assert text.count(old) == 1, f"not the v91 text: {old[:70]}"
        text = text.replace(old, new)
    L = text.split("\n")
    i = next(k for k, l in enumerate(L[:6]) if "BUILD STAMP" in l)
    L[i] = stamp + " " * (len(L[i + 1]) - len(stamp) - 1) + "║"
    return "\n".join(L)


def master(text):
    """the v92 Master from the v91 Master"""
    return _apply(text, M_PAIRS, STAMP_M)


def visuals(text):
    """the v92 Visuals from the v91 Visuals"""
    return _apply(text, V_PAIRS, STAMP_V)


if __name__ == "__main__":
    for p, f in (("artefacts/XAUUSD_Quantum_5_0_Master.pine", master), ("artefacts/XAUUSD_Quantum_5_5_Visuals.pine", visuals)):
        src = open(p, encoding="utf-8").read()
        open(p, "w", encoding="utf-8").write(f(src))
    print("fixed Master and Visuals (v92)")
