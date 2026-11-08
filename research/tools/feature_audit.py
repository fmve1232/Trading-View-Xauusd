"""Deliverable 2 of Phase C: research/FEATURE_AUDIT.md, every research feature with its formula, the moment it is
available, its data caveat and its MEASURED value (B27: univariate AUC on 2020-22, LightGBM permutation AUC drop on the
2021-23 walk-forward test quarters, and its family's ablation). Numbers are read from research/results/b27.

  python research/tools/feature_audit.py research/results/b27/b27_summary.json > research/FEATURE_AUDIT.md
"""
import json
import sys

sys.path.insert(0, ".")
from quantum.research import b27

AVAIL = "close of the decision bar (15m); higher-timeframe parts from bars closed by then"
F = {
    # name: (formula, data caveat)
    "nd_atr_pct": ("ATR14 (Wilder, 15m) / close", ""),
    "nd_atr_rank": ("percent rank of ATR14 over the previous 2,880 bars (30 days)", ""),
    "nd_range_atr": ("(high - low) / ATR14 of the bar", ""),
    "nd_body_atr": ("|close - open| / ATR14", ""),
    "nd_bb_width": ("4 x stdev20(close) / ATR14 (Bollinger width in ATR)", ""),
    "nd_rsi_abs": ("|RSI14 - 50|", ""),
    "nd_run_length": ("consecutive closes in the same direction, capped at 10 (B20)", ""),
    "nd_tq": ("the production engine's trade quality (0-100) at the bar", "engine output; the engine's own inputs"),
    "nd_sess_q": ("the engine's session quality (0-100)", "engine output"),
    "nd_hour_sin": ("sin(2 pi hour / 24), UTC", ""),
    "nd_hour_cos": ("cos(2 pi hour / 24), UTC", ""),
    "nd_weekday": ("UTC weekday 0-6", "predicts weekend / holiday closures (B27 S4), not direction"),
    "nd_london": ("1 inside the London session (sessions.calendar)", ""),
    "nd_ny": ("1 inside the New York session", ""),
    "nd_day_pos": ("(close - day low so far) / (day high - day low so far), New York trading day", ""),
    "nd_fvg": ("the engine's bullish FVG flag", "engine output"),
    "nd_reg_ABNORMAL": ("engine regime = ABNORMAL (news window, |z| > 3 or ATR > 2.5 x its 100-bar mean)", "engine output"),
    "nd_reg_COMPRESS": ("engine regime = COMPRESS (Bollinger width pct <= 20 and ADX < 20)", "engine output"),
    "nd_reg_EXPANSION": ("engine regime = EXPANSION", "engine output"),
    "nd_reg_RANGE": ("engine regime = RANGE", "engine output"),
    "nd_reg_STRONG TR": ("engine regime = STRONG TR", "engine output"),
    "nd_reg_WEAK TR": ("engine regime = WEAK TR", "engine output"),
    "nd_adx": ("ADX14 (Pine ta.dmi reference)", ""),
    "nd_atr_ratio": ("ATR14 / ATR100 (expansion > 1.3, contraction < 0.75)", ""),
    "nd_bbw_rank": ("percent rank of the Bollinger width over 500 bars", ""),
    "nd_news_to_next": ("minutes to the next dated CPI / NFP / FOMC release, capped at 600", "NaN where no dated list (2023-02 .. 2026-10)"),
    "nd_news_since": ("minutes since the last dated release, capped at 600", "as above"),
    "sg_d_e20": ("(close - EMA20) / ATR14, x direction", ""),
    "sg_d_e100": ("(close - EMA100) / ATR14, x direction", ""),
    "sg_d_e200": ("(close - EMA200) / ATR14, x direction", ""),
    "sg_slope20": ("(EMA20 - EMA20 4 bars ago) / ATR14, x direction", ""),
    "sg_slope100": ("(EMA100 - EMA100 4 bars ago) / ATR14, x direction", ""),
    "sg_trend_1h": ("sign(EMA20 - EMA100) of 1h closes, last closed 1h bar, x direction", ""),
    "sg_trend_4h": ("as 1h on New York 4h bars", ""),
    "sg_trend_1d": ("sign(EMA20 - EMA50) of New York daily closes, last closed day, x direction", ""),
    "sg_d_vwap": ("(close - session mean price) / ATR14, x direction", "NOT a VWAP: the feed has no volume, so the engine's VWAP is the equal-weighted session mean"),
    "sg_pct_b": ("Bollinger %B(20, 2) - 0.5, x direction", ""),
    "sg_rsi": ("RSI14 - 50, x direction", ""),
    "sg_macd_hist": ("MACD(12, 26, 9) histogram / ATR14, x direction", ""),
    "sg_ret1": ("(close - close 1 bar ago) / ATR14, x direction", ""),
    "sg_ret4": ("4-bar return / ATR14, x direction", ""),
    "sg_ret16": ("16-bar return / ATR14, x direction", ""),
    "sg_wick_skew": ("(lower wick - upper wick) / ATR14, x direction", ""),
    "sg_run_size": ("$ moved by the current candle run / 10, x direction (B20)", ""),
    "sg_since_up_minus_dn": ("(bars since the last bearish structure event - bars since the last bullish) / 96, x direction", "engine BOS / MSS / CHoCH"),
    "sg_sweep": ("the engine's SWEEP event direction at the bar, x direction", "engine output"),
    "sg_grab": ("liquidity GRAB event direction (B10), x direction", ""),
    "sg_break": ("liquidity BREAK event direction (B10), x direction", ""),
    "sg_signal": ("the engine's SIGNAL direction at the bar, x direction", "engine output"),
    "sg_bull_minus_bear": ("(engine bull score - bear score) / 100, x direction", "engine output"),
    "sg_d_pdh": ("(close - previous day high) / ATR14, x direction", "engine's PDH"),
    "sg_d_pdl": ("(close - previous day low) / ATR14, x direction", "engine's PDL"),
    "sg_d_pwh": ("(close - previous week high) / ATR14, x direction", ""),
    "sg_d_pwl": ("(close - previous week low) / ATR14, x direction", ""),
    "sg_day_pos_c": ("position in the day's range so far - 0.5, x direction", ""),
    "sg_di_diff": ("DI+ - DI- (14), x direction", ""),
    "sg_consec": ("signed count of consecutive same-direction closes, capped +-8, x direction", ""),
    "sg_in_fvg": ("+1 inside an unfilled bullish FVG (created <= 48 bars ago), -1 bearish, x direction", ""),
    "sg_ob_retest": ("+1 retesting a bullish order block (last opposite candle before a displacement, <= 48 bars), -1 bearish", ""),
    "sg_eq_liquidity": ("+1 equal highs (two confirmed 5/5 pivots within 0.15 ATR) within 1.5 ATR above, -1 equal lows below", "pivots confirmed 5 bars late (causal)"),
    "sg_asia_pos": ("(close - Asian mid) / Asian range, 07:00-21:00 UTC, x direction", ""),
    "sg_prem_disc": ("position in the 96-bar range - 0.5 (premium > 0), x direction", ""),
    "sg_flip": ("direction of a structure flip (CHoCH-like) within the last 8 bars", "engine structure events"),
    "sg_disp": ("displacement candle direction (range >= 2 ATR, body >= 70%)", ""),
    "sg_fvg_new": ("new FVG direction (gap >= 0.3 ATR) at the bar", ""),
    "hmm_calm": ("forward-filtered probability of the calmest of 3 Gaussian HMM states on 1h [return, |return|]", "fitted on each training window only"),
    "hmm_mid": ("the middle state's probability", "as above"),
    "hmm_wild": ("the wildest state's probability", "as above"),
    "hmm_cusum_signed": ("CUSUM of 1h returns (24-bar window), x direction", ""),
    "direction": ("+1 BUY, -1 SELL", ""),
}
EVENTS = {
    "B28 LONDON_ORB / NY_ORB": "first 15m close beyond the 30-minute opening range (08:00 London / 09:30 New York local) inside the window; available at that close",
    "B28 ENGULF_LEVEL / PINBAR_LEVEL": "the pattern's bar at a PDH / PDL / Asian / 20-bar level; available at its close",
    "B28 CHOCH_RETEST": "the first bar of a structure flip; available at its close (the engine's structure events are themselves closed-bar)",
    "B28 OB_RETEST / SWEEP_DISPLACEMENT": "the displacement bar's close (order block / sweep looked up in the bars before it)",
    "B28 SUPERTREND": "the bar whose close flips the Supertrend (ATR 10, x3); final bands use only earlier bars",
}
NOT = ["true VWAP, volume profile / POC, relative volume (no traded volume; tick volume is not volume)",
       "bid / ask spread, tick-by-tick changes, price velocity / acceleration, aggressor proxies, intrabar sequence (no tick or quote data; not derived from OHLC)",
       "order-book depth (never available); COMEX trade flow was tested in B5 (no edge)",
       "intraday DXY / 10Y / EURUSD / silver / S&P for 2020-22 (2026 descriptive only, B27 S6)",
       "PCE (no dated list)"]


def main(path: str) -> None:
    with open(path) as fh:
        s = json.load(fh)
    u, p = s["S4"]["univariate_auc"], s["S4"]["permutation_auc_drop"]
    print("# Phase C, deliverable 2: feature and indicator audit\n")
    print("Generated by `research/tools/feature_audit.py` from `research/results/b27/b27_summary.json` (B27, development 2020-22).")
    print("\nEvery feature is computed from bars closed at or before the decision bar (tested by recomputing on truncated data:")
    print("`tests/test_research_b27.py`, `tests/test_research_b28.py`). **Available at:** " + AVAIL + ".")
    print("\n**Measured value:**")
    print("- **AUC** is the univariate AUC for TP first at +-$15 (0.5 = no information).")
    print("- **Perm** is the LightGBM AUC lost when the feature is shuffled on the walk-forward test quarters.")
    print("- **Family** is the AUC change when the whole family is removed (+ = the model is better without it).\n")
    abl = s["S4"]["ablation"]
    print("| Feature | Family | Formula | Caveat | AUC | Perm | Family ablation |")
    print("|---|---|---|---|---|---|---|")
    for nm in u:
        fam = b27.family(nm)
        form, cav = F.get(nm, ("(see code)", ""))
        a = abl.get(fam, {}).get("change")
        print(f"| `{nm}` | {fam} | {form} | {cav} | {u[nm]:.4f} | {p.get(nm, 0):+.4f} | {'' if a is None else f'{a:+.4f}'} |")
    print("\n## Event definitions added in Phase C (B28)\n")
    print("| Family | Availability |")
    print("|---|---|")
    for k, v in EVENTS.items():
        print(f"| {k} | {v} |")
    print("\n## Not tested (data does not exist here); never substituted\n")
    for x in NOT:
        print(f"- {x}")
    print("\n## Verdict\n")
    print("- **Only weekday and hour carry measurable information** (permutation +0.016 / +0.011).")
    print("  - Removing the TIME_NEWS family is the only removal that hurts (-0.016 AUC).")
    print("  - That information predicts weekend / holiday closures, not direction.")
    print("- **Every structure, liquidity, SMC, trend, oscillator, volatility and Markov feature adds nothing.**")
    print("  - Their permutation drops are at most about 0.002.")
    print("  - Removing whole families (liquidity, structure / SMC, momentum, trend, oscillator) improves the out-of-sample AUC.")
    print("- **No feature is carried into a strategy specification on this evidence** (operator rule: \"If an indicator adds no")
    print("  predictive value, remove it from the proposed strategy specification\").")


if __name__ == "__main__":
    main(sys.argv[1])
