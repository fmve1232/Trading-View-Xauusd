# B27: the maximum achievable TP-first rate for +$15 / −$15 (2026-11-08)

| Item | Where |
|---|---|
| Registration | `research/registrations/B27.json`, committed `0065cadb1` before any code |
| Code, tests and the null check | `quantum/research/b27.py`, `tests/test_research_b27.py` (9 tests), `research/tools/b27_null_check.py`; committed `acca0426f` before any real result |
| Results | `research/results/b27/` |
| Tables | generated from the summary by `research/tools/b27_tables.py` (appendix) |

The full set of result files:
- `b27_summary.json`;
- `b27_leaderboard.csv`;
- `b27_S1/S2/S3/S5.csv.gz`, one row per configuration;
- `b27_frozen_trades.csv.gz`: every trade of the 20 frozen candidates, 15,856 rows over 2020–22, 2026 and 2026 on 5m bars.

**Branch:** `claude/research-sym15`. Research only. Production, web.8, the frozen Pine files, the alerts and PRs #90 / #91 are untouched.

## The answer

**On the data available, the highest TP-first rate for +$15 before −$15 that survives an honest test is the coin-flip rate.**

| | Rate (decided trades) |
|---|---|
| Before costs | about 50% |
| After the engine's costs | about 48% |
| Break-even | 50.6% |

1. **1,192 configurations were tested on 2020–22 development data** (all frozen before any 2026 look):
   - 518 single conditions;
   - 582 entry setups (13 trigger families × immediate / $3–$20 confirmation / retest / stop / structure-limit entries × BUY / SELL);
   - 70 selections from five calibrated probability models;
   - 22 regime-and-direction groups.

   **None** beat its matched random baseline after the multiple-testing correction (BH, 5%). None was INFORMATIVE and none was TRADEABLE.
2. **The best development results are what a random walk produces.**

   | Configurations with at least 300 independent trades | Real 2020–22 | Same framework on a pure random walk |
   |---|---|---|
   | Configurations | 898 | 679 |
   | Best TP-first rate | 54.5% | 53.8% |
   | Best 95% lower bound | 49.2% | 50.0% |
   | Smallest p-value (BH needs about 0.00004) | 0.002 | 0.010 |

   On the random walk the framework flagged **0 of 1,186** configurations, so it does not manufacture winners. On real data it also flags none.
3. **The 20 best candidates were frozen and re-measured on 2026. None held; none cleared break-even.**
   - Every development "winner" fell back to the market's rate:
     - buying a PDH/PDL sweep: 53.6% → 44.6%;
     - selling an EMA pullback after a $15 confirmation: 54.0% → 48.5%;
     - buying a liquidity-sweep retest at $20: 59.7% → 36.6%.
   - The best 2026 result with at least 100 trades was selling an FVG retest at $12: **53.9%** on 304 trades. The 2026 random rate for the same direction, sessions and months was 52.7%, and the lower bound 48.3%: no difference shown.
4. **Against your targets:**

   | Target | Best result |
   |---|---|
   | 70% / 80% / 85% / 90% / 95% | Not reached by any configuration, in development or 2026, at any sample size |
   | Best development lower bound with at least 30 trades | 52.5% |

   For a symmetric ±$15, a 90% rate needs a known drift of about $4.9 an hour in your favour (2020–22 volatility). No tested input carries that.
5. **Only one thing has measurable information: knowing when not to trade.**
   - The models' small edge (out-of-sample AUC 0.52) comes almost entirely from weekday and hour.
   - That edge identifies late-week entries that the weekend closes before either level is reached.
   - Taking out the time / news features drops AUC to 0.504. Taking out liquidity, structure / SMC, momentum, trend or oscillators raises it. **They add noise, not information.**
   - The calibrated model never predicts above about 48% for any group of trades, and its top tenth realises 47%.

## What was tested, and how

| Study | What | Count |
|---|---|---|
| S1 conditions | Every feature alone, in quintiles or as a flag, in the trade's favour, BUY and SELL separately | 518 |
| S2 entries | 13 trigger families × 23 entry modes × direction | 582 |
| S3 models | LR, HGB, LightGBM, separate BUY / SELL LightGBM, ensemble; isotonic calibration; quarterly purged walk-forward 2021-01 → 2023-01 (about 100,000 test rows); top 50 / 20 / 10 / 5 / 2 / 1 / 0.5% | 70 |
| S4 ranking | Univariate AUC, permutation importance on the test quarters, ablation of each of 9 families | — |
| S5 regimes | Strong / weak bull and bear, sideways, expansion, contraction, reversal, news, post-news, liquidity | 22 |
| S6 intermarket | DXY, US 10Y, EURUSD, silver, S&P 500: 4-hour change quintiles, 2026 only, descriptive | 50 |

**S2's 13 trigger families:**
- every hour (the control);
- the engine's signal, sweep, grab, break and BOS / MSS / CHoCH;
- new FVG; displacement candle; EMA 20 pullback in the 1h trend;
- volatility expansion after contraction; London break of the Asian range;
- failed 20-bar breakout; PDH / PDL sweep-and-reclaim.

**S2's 23 entry modes:**
- immediate;
- confirmation by a 15m close of $3 / 5 / 7 / 10 / 12 / 15 / 20, with TP / SL recalculated from the new fill;
- a retest limit at the confirmation level;
- a stop order at the distance (breakout continuation);
- the family's own structure limit (FVG midpoint, half the displacement body, the Asian range edge, the swept level).

**Every trade is B26's trade:**
- decided at a 15m close and filled at the next open (BUY at the ask, SELL at the bid);
- TP / SL ±$15 from the actual fill;
- a bar touching both levels counts as the stop;
- engine cost model ($0.30 spread in session, $0.50 off, $0.20 slippage, $7 a lot).

**Method:**
- **Statistic.** The decided TP-first rate on the independent-trade series (the next entry only after the previous one exited), with a Wilson interval.
- **Baseline.** Random entries with the same direction, session and month (post-stratified).
- **Selection** used 2020–22 only. The 2026 check (15m, and 5m exits from September) used frozen rules and thresholds.
- **Sealed.** Validation (2023-01 → 2024-07) and the holdout (2024-07 → 2026-01) were not read.

**Not testable, and not substituted:**
- true VWAP, volume profile / POC and relative volume (the feed has no traded volume; the engine's "VWAP" is the session's average price and is labelled so);
- intraday intermarket bars for 2020–22 (2026 only, descriptive);
- PCE (no dated list);
- news for 2023-02 → 2026-10 (no dated list).

## Results by question

### Entry price and confirmation (S2, the "every hour" control, 2020–22)

**Confirmation does not move the odds; it only removes trades.**

| Confirmation distance | Hourly BUY triggers confirmed | Rate after confirming | Immediate entry |
|---|---|---|---|
| $3 | 75% | 47.9% | 48.1% |
| $15 | 45% | 48.0% | 48.1% |
| $20 | 38% | 47.0% | 48.1% |

- **At $15 the funnel is a coin.** 7,303 of 16,138 hourly BUY triggers confirmed, 8,442 were invalidated first and 393 expired. A random walk gives that split.
- Per trigger, larger confirmation loses less money only because it trades less.

**Retest limits score 48.6–49.3%,** about 0.7 points above market entries. That is the slippage a limit order saves (theory: 49.0% vs 48.3%), not information.

**Stop-order (breakout-continuation) entries get worse with distance:** 47.8% at $3, 43.4% at $12, 40.0% at $20. Momentum through a level is not followed by another $15 more often than chance, and the bar that fills you can also stop you.

**Best mode per trigger family (n ≥ 300, development).**
- Every one lies inside its random rate's range, or fails the correction.
- The highest was buying the PDH/PDL sweep at market: 53.6% (49.0–58.2) on 442 trades, against 46.8% random.
- In 2026 that setup gave 44.6% against 44.1% random.

### Probability models (S3)

| Model | Out-of-sample AUC | Brier (constant 0.2475) |
|---|---|---|
| LR | 0.498 | 0.2487 |
| HGB | 0.524 | 0.2451 |
| LGBM | 0.521 | 0.2457 |
| LGBM, BUY and SELL separate | 0.519 | 0.2468 |
| Ensemble | 0.523 | 0.2454 |

- **Calibration.** The calibrated probabilities run from 32% to 48% and track what happened (ensemble deciles: 32%→34%, 44–48%→45–47%).
- **The model is honest and has nothing to say above the base rate.** Its best top-1% selection was 51.7% SELL (LGBM, 895 trades, against 49.9% random). Frozen on 2026 it gave 51.2% on 455 trades, against 50.6% random.
- **Separate BUY and SELL models were not better** than one model with the direction as a feature.
- **Isotonic plateau (2026).** The frozen LGBM's top calibrated level held about 18% of the 2026 SELL trades. So its top 0.5% to 10% selections are the same 455 trades. The calibration has only a few levels at the top; this does not change the result.

### What carries information (S4)

| Rank | Feature (permutation AUC drop) |
|---|---|
| 1 | weekday +0.016 |
| 2 | hour +0.011 |
| 3 and below | every structure, liquidity, trend, oscillator, volatility or HMM feature, at about +0.002 or less |

- **Ablation.** Only removing TIME_NEWS hurts (−0.016). Removing LIQUIDITY (+0.011), STRUCTURE_SMC (+0.006), MOMENTUM (+0.006), TREND (+0.003) or OSCILLATOR (+0.002) improves the model.
- **Proposed specification.** Per your instruction, a factor with no predictive value is removed from the proposed strategy specification. On this evidence that is every factor except time-of-week, and time-of-week only says when **not** to trade (a weekend closure is near).

### Regimes (S5, development)

- **Highest regime-direction rates:** liquidity BUY 50.1% (47.6–52.6) and news BUY 50.3% (44.8–55.9).
- **Strong-trend regimes:** 46.5–49.4%.
- **No regime differs from its random rate.** No regime has to be rejected for being worse, and none can be selected for being better.
- **BUY vs SELL, and with vs against the trend, make no reliable difference** (also in B26).

### Intermarket, 2026 (S6, descriptive)

- Of 50 quintile groups (5 series × 5 × 2 directions), none is significant.
- All lie within about 4 points of the matched random rate.
- Dollar, yields, EURUSD, silver and the S&P carried no usable information for the next ±$15 in 2026.

## Failure analysis: why nothing works

1. **A ±$15 bracket is about 2 × the 15m ATR,** about an hour's range; it resolves in a median of 60–135 minutes. Over that horizon gold moved like a random walk in both periods:
   - direction is right 48–53% of the time after 1 and 4 hours (B26);
   - the bracket's first touch is a coin.
2. **Every input is built from past prices** (and the engine's own outputs from them). Short-horizon gold returns had no usable memory in these data. The excursions agree:
   - winners first go about $6 against you;
   - losers first show about $5–6 of profit;
   - at the time of entry the two look the same.
3. **The selection effect is large.**
   - With 1,192 configurations, the best ones reach 54–60% by chance (the random walk did too).
   - Every one fell back to the base rate on 2026.
   - Ranking by a raw historical win rate would have "found" a 60% strategy that loses money.
4. **Costs then decide the sign.** At a coin's 48% after spread and slippage against a 50.6% break-even, 96% of the 898 development configurations with at least 300 trades lost money.
   - Median −$0.81 per oz; the middle 80% ran −$1.47 to −$0.35. That is about −$40 per 0.50 lot per trade, ASSUMED 100 oz.
   - The 4% with a positive average are the selection-noise winners above.
5. **2026 looks better for SELL setups only because gold fell 31%.**
   - All 12 frozen candidates with a positive 2026 average are SELL setups; five of them are the same model selection counted at five thresholds.
   - None is significant (Holm p = 1.0) and none has a lower bound above its random rate or break-even. The 20 averaged −$0.40 per oz.
6. **The one cluster worth a note does not hold together.** On 2020–22, SELL entries on a $10–15 retest after a liquidity / PDH-PDL sweep scored 51.6–57.5% (p 0.009–0.07 before correction), and they were positive again in 2026.
   - Their BUY mirrors at the same distances scored 44–51%.
   - At $20 the pattern flips: BUY retests 55–60%, SELL 47–49%.
   - The $10 / $12 / $15 variants share most of their trades, so they are not independent evidence.
   - A mechanism does not change direction between $15 and $20. A search over 1,192 overlapping variants does produce this, and 2026's SELL drift explains its 2026 result.
   - I do not recommend spending the sealed validation period on it. If you want it tested anyway, it has to be registered as one pre-specified hypothesis first.

## Recommended architecture (on this evidence)

**The default output is NO TRADE.** Under your own approval rule, the hierarchy (A exceptional / B high-conviction / C wait / D no trade) has no validated basis for A or B:
- no configuration has a calibrated probability above the base rate;
- none has a lower bound above break-even;
- none survived its out-of-sample check.

What can honestly be shown:

| Field | Value |
|---|---|
| Probability | The base rate with its interval: about 48% after costs; 50% before |
| Break-even | 50.6% |
| Expected value | Negative |
| Warning | The weekend / closure warning (the one measurable effect) |
| Decision | D (no trade) |

No dashboard probability above 50% would be supportable. The Master and Visual specification therefore stays at the research stage. **No production or TradingView code is proposed** (deliverable 12 needs a validated strategy and your separate approval). Nothing is proposed for the sealed validation period, because nothing qualified to be tested there.

## What could still change the answer

| Option | What it would take |
|---|---|
| Data with information the price history does not have | Real bid / ask and depth from your broker (MetaApi or an MT5 tick export) for spread-aware entries. Order flow: CME GC trades were tested in B5 with no edge; depth was not. News surprise (actual vs consensus, not just the release time). Options-implied volatility. Each needs its own registration. |
| A longer 5m history (MT5 M1) | Your execution timeframe has only 2 months of bars here. 15m resolution changes ±$15 outcomes on only 0.1% of trades (B26), so a different answer at 5m is unlikely, but it is untested over years. |
| Changing the trade | A high hit rate is easy with an asymmetric bracket (e.g. +$15 / −$45 is 75% for a coin). Its expectancy after costs is still negative, so it is not a better trade. |

**Not done, by design:** no threshold was lowered, no losing period removed and no failed candidate re-tested. The holdout was not opened.

## Checks

| Check | Result |
|---|---|
| `python -m pytest -q tests/test_research_b27.py` | 9 passed: feature causality on truncated data, confirmation / stop / limit / fill-bar rules, market fill = B26's race, time-correct calibration split, selection rules, BH / Holm, Pareto |
| Null check (`research/tools/b27_null_check.py`, the whole framework on synthetic random walks) | 0 of 1,186 configurations flagged |
| Independent re-computation of 30 sampled entry trades (`research/tools/b27_spotcheck.py`, B26's race) | 30 of 30 match |
| Development baseline vs B26 | identical (48.0% / 48.0% on 3,808 / 3,819) |
| Full suite (`python -m pytest -q tests`) | 512 passed |

**Matched baseline caveat.** In 2026 the all-bar matched random rate for BUY (about 43.5%) sits about 2.7 points below the independent-trade baseline (46.2%). In a falling market, overlapping entries over-count long grinding losses. That makes the 2026 check easier for BUY candidates, not harder; none held anyway.

**Multiple testing.** 1,212 lines were added to `research/trials.jsonl` (1,192 configurations and 20 frozen 2026 checks), all with their verdicts. The log now holds 2,595 trials.

## Appendix: full tables (generated from `research/results/b27/b27_summary.json` by `research/tools/b27_tables.py`)

### Baseline (independent trades, ENG)

| Population | BUY r (95%) | SELL r (95%) | BUY n | SELL n | BUY exp/oz | SELL exp/oz |
| --- | --- | --- | --- | --- | --- | --- |
| DEV | 48.0% (46.4–49.5) | 48.0% (46.4–49.6) | 3808 | 3819 | -0.72 | -0.81 |
| Y2026 | 46.2% (44.2–48.1) | 49.2% (47.2–51.1) | 2563 | 2585 | -1.34 | -0.43 |
| Y2026_5m | 45.3% (40.4–50.2) | 49.9% (45.1–54.7) | 393 | 413 | -1.64 | -0.16 |

### Counts

| Study | Tested | BH-significant | INFORMATIVE | TRADEABLE |
| --- | --- | --- | --- | --- |
| S1 | 518 | 0 | 0 | 0 |
| S2 | 582 | 0 | 0 | 0 |
| S3 | 70 | 0 | 0 | 0 |
| S5 | 22 | 0 | 0 | 0 |

### Leaderboard (frozen on development; 2026 is the check)

| Candidate | Board | Dev r (95%) | Dev n | Dev random | Dev exp/oz | PF | Trades/wk | DD 0.5 lot (MC95) | Min | 2026 r (95%) | 2026 n | 2026 random | 2026 exp/oz | Holm p | Holds | 2026 5m r (n) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S3 LGBM top0.5% SELL | top_n300 | 53.2% (49.2–57.1) | 607 | 52.2% | +0.75 | 1.11 | 4.2 | 14143 (21599) | 210 | 51.2% (46.6–55.8) | 455 | 50.6% | +0.18 | 1.000 | no | 54.1% (74) |
| S2 PD_SWEEP IMM BUY | top_n300 | 53.6% (49.0–58.2) | 442 | 46.8% | +0.90 | 1.13 | 3.1 | 11744 (18376) | 165 | 44.6% (37.8–51.6) | 195 | 44.1% | -1.78 | 1.000 | no | — (—) |
| S2 EMA_PULLBACK CONF_15 SELL | top_n300 | 54.0% (48.9–59.1) | 359 | 51.4% | +0.97 | 1.14 | 2.5 | 9680 (16482) | 135 | 48.5% (42.2–54.9) | 237 | 52.8% | -0.64 | 1.000 | no | — (—) |
| S2 PD_SWEEP LIMIT BUY | top_n300 | 54.5% (48.8–60.0) | 303 | 46.8% | +1.17 | 1.17 | 2.1 | 8558 (14791) | 165 | 36.0% (27.7–45.1) | 114 | 43.6% | -4.36 | 1.000 | no | — (—) |
| S3 LGBM top2% SELL | top_n300 | 51.8% (48.6–55.0) | 924 | 49.8% | +0.36 | 1.05 | 6.4 | 24460 (30236) | 180 | 51.2% (46.6–55.8) | 455 | 50.6% | +0.18 | 1.000 | no | 54.1% (74) |
| S3 LGBM top1% SELL | top_n300 | 51.7% (48.5–55.0) | 895 | 49.9% | +0.33 | 1.05 | 6.2 | 24460 (30802) | 180 | 51.2% (46.6–55.8) | 455 | 50.6% | +0.18 | 1.000 | no | 54.1% (74) |
| S1 sg_in_fvg =1 SELL | top_n300 | 50.9% (48.1–53.7) | 1233 | 48.1% | +0.03 | 1.00 | 8.9 | 18160 (43010) | 210 | 51.0% (46.6–55.4) | 486 | 52.2% | +0.15 | 1.000 | no | 54.2% (107) |
| S2 FVG RETEST_12 SELL | top_n300 | 51.8% (48.1–55.5) | 693 | 49.0% | +0.26 | 1.04 | 4.9 | 20410 (28935) | 172 | 53.9% (48.3–59.5) | 304 | 52.7% | +0.99 | 1.000 | no | — (—) |
| S3 LGBM top10% SELL | top_n300 | 50.3% (48.0–52.6) | 1836 | 50.7% | -0.10 | 0.99 | 12.7 | 45199 (57486) | 165 | 51.2% (46.6–55.8) | 455 | 50.6% | +0.18 | 1.000 | no | 54.1% (74) |
| S3 LGBM top5% SELL | top_n300 | 50.3% (48.0–52.6) | 1836 | 50.7% | -0.10 | 0.99 | 12.7 | 45199 (57486) | 165 | 51.2% (46.6–55.8) | 455 | 50.6% | +0.18 | 1.000 | no | 54.1% (74) |
| S2 SWEEP RETEST_20 BUY | low_frequency | 59.7% (52.5–66.5) | 186 | 46.8% | +2.51 | 1.42 | 1.4 | 4842 (9057) | 195 | 36.6% (27.0–47.4) | 82 | 43.0% | -4.23 | 1.000 | no | — (—) |
| S2 ASIA_BREAKOUT RETEST_3 SELL | low_frequency | 59.7% (51.2–67.6) | 134 | 50.2% | +2.50 | 1.41 | 0.9 | 5130 (8448) | 165 | 47.1% (31.5–63.3) | 34 | 53.0% | -1.06 | 1.000 | no | — (—) |
| S2 ASIA_BREAKOUT RETEST_5 SELL | low_frequency | 59.5% (50.6–67.8) | 121 | 50.3% | +2.56 | 1.41 | 0.8 | 6176 (7808) | 150 | 54.5% (38.0–70.2) | 33 | 52.3% | +1.20 | 1.000 | no | — (—) |
| S2 PD_SWEEP RETEST_20 BUY | low_frequency | 57.9% (49.9–65.5) | 152 | 46.9% | +2.01 | 1.33 | 1.1 | 4808 (9330) | 180 | 33.9% (22.9–47.0) | 56 | 42.8% | -5.03 | 1.000 | no | — (—) |
| S2 PD_SWEEP RETEST_12 SELL | low_frequency | 56.5% (49.7–63.1) | 207 | 48.0% | +1.42 | 1.22 | 1.5 | 8903 (12618) | 262 | 54.2% (41.7–66.3) | 59 | 52.7% | +1.01 | 1.000 | no | — (—) |
| S2 ASIA_BREAKOUT RETEST_7 SELL | low_frequency | 58.1% (49.1–66.7) | 117 | 50.7% | +2.25 | 1.35 | 0.8 | 6142 (8484) | 150 | 50.0% (33.6–66.4) | 32 | 52.2% | -0.17 | 1.000 | no | — (—) |
| S2 GRAB RETEST_15 SELL | low_frequency | 57.5% (49.0–65.5) | 134 | 47.8% | +1.45 | 1.23 | 1.0 | 7589 (10200) | 225 | 55.2% (37.5–71.6) | 29 | 52.3% | +1.56 | 1.000 | no | — (—) |
| S2 PD_SWEEP RETEST_15 SELL | low_frequency | 56.0% (48.8–63.1) | 182 | 48.0% | +0.94 | 1.14 | 1.4 | 11365 (13663) | 255 | 60.3% (47.5–71.9) | 58 | 52.0% | +2.83 | 1.000 | no | — (—) |
| S2 SWEEP RETEST_15 SELL | low_frequency | 55.1% (48.7–61.4) | 234 | 47.3% | +0.82 | 1.12 | 1.8 | 8238 (15387) | 218 | 56.4% (45.4–66.9) | 78 | 51.9% | +1.69 | 1.000 | no | — (—) |
| S2 PD_SWEEP RETEST_10 SELL | low_frequency | 54.8% (48.5–60.9) | 241 | 47.9% | +1.17 | 1.18 | 1.8 | 8019 (13251) | 255 | 47.8% (36.5–59.4) | 69 | 52.0% | -0.99 | 1.000 | no | — (—) |

### S2 confirmation distance, every hour (development)

| Mode | BUY r | BUY n | BUY fill | BUY exp/trigger | SELL r | SELL n | SELL exp/trigger | MAE | min to TP |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| IMM | 48.1% | 3078 | 100% | -0.74 | 47.9% | 3089 | -0.90 | 10.61 | 165 |
| CONF_3 | 47.9% | 2473 | 74% | -0.79 | 47.5% | 2463 | -0.79 | 10.60 | 195 |
| CONF_5 | 47.7% | 2286 | 68% | -0.69 | 46.5% | 2267 | -0.69 | 10.53 | 180 |
| CONF_7 | 47.4% | 2083 | 62% | -0.67 | 46.7% | 2075 | -0.58 | 10.66 | 165 |
| CONF_10 | 47.7% | 1804 | 55% | -0.63 | 46.8% | 1806 | -0.43 | 10.66 | 172 |
| CONF_12 | 47.7% | 1645 | 51% | -0.59 | 47.1% | 1627 | -0.38 | 10.70 | 165 |
| CONF_15 | 48.0% | 1429 | 45% | -0.52 | 46.6% | 1394 | -0.37 | 10.59 | 165 |
| CONF_20 | 47.0% | 1140 | 38% | -0.33 | 48.0% | 1074 | -0.38 | 10.72 | 150 |
| RETEST_3 | 48.7% | 2209 | 59% | -0.55 | 48.1% | 2163 | -0.58 | 10.15 | 210 |
| RETEST_5 | 48.2% | 2043 | 54% | -0.50 | 47.9% | 2017 | -0.43 | 10.24 | 225 |
| RETEST_7 | 48.6% | 1931 | 49% | -0.44 | 48.3% | 1883 | -0.38 | 10.13 | 195 |
| RETEST_10 | 49.0% | 1689 | 44% | -0.38 | 47.7% | 1626 | -0.37 | 10.04 | 195 |
| RETEST_12 | 49.3% | 1566 | 41% | -0.38 | 48.8% | 1505 | -0.34 | 10.02 | 195 |
| RETEST_15 | 49.3% | 1340 | 36% | -0.35 | 47.2% | 1302 | -0.33 | 10.05 | 195 |
| RETEST_20 | 49.1% | 1098 | 30% | -0.26 | 49.1% | 1010 | -0.38 | 10.10 | 180 |
| STOP_3 | 47.8% | 2656 | 83% | -0.69 | 47.0% | 2669 | -0.91 | 10.34 | 180 |
| STOP_5 | 46.4% | 2416 | 75% | -0.64 | 45.3% | 2425 | -0.82 | 10.57 | 195 |
| STOP_7 | 46.5% | 2166 | 68% | -0.60 | 44.8% | 2183 | -0.85 | 10.55 | 195 |
| STOP_10 | 45.1% | 1850 | 59% | -0.66 | 43.3% | 1867 | -0.80 | 10.70 | 195 |
| STOP_12 | 43.4% | 1645 | 54% | -0.75 | 42.9% | 1673 | -0.82 | 10.95 | 195 |
| STOP_15 | 40.4% | 1434 | 47% | -0.94 | 40.2% | 1442 | -1.07 | 11.16 | 195 |
| STOP_20 | 40.0% | 1162 | 39% | -0.86 | 37.8% | 1147 | -1.36 | 11.16 | 180 |

### S2 best mode per trigger family (development, by Wilson lower bound, n >= 300)

| Family | Dir | Best mode | r (95%) | n | random | exp/oz | IMM r | triggers |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BOS | BUY | STOP_5 | 50.7% (46.0–55.4) | 430 | 47.6% | +0.09 | 49.5% | 748 |
| BOS | SELL | IMM | 46.1% (41.8–50.4) | 521 | 48.0% | -1.39 | 46.1% | 681 |
| BREAK | BUY | IMM | 48.3% (43.4–53.3) | 389 | 49.2% | -0.56 | 48.3% | 449 |
| BREAK | SELL | IMM | 47.1% (41.8–52.5) | 333 | 49.5% | -1.06 | 47.1% | 375 |
| DISPLACEMENT | BUY | CONF_5 | 50.5% (45.0–55.9) | 321 | 47.9% | -0.05 | 47.5% | 621 |
| DISPLACEMENT | SELL | CONF_5 | 51.9% (46.6–57.0) | 351 | 49.5% | +0.31 | 48.5% | 675 |
| EMA_PULLBACK | BUY | RETEST_20 | 49.2% (43.8–54.7) | 323 | 49.7% | -0.13 | 45.6% | 5291 |
| EMA_PULLBACK | SELL | CONF_15 | 54.0% (48.9–59.1) | 359 | 51.4% | +0.97 | 47.6% | 4355 |
| EVERY_HOUR | BUY | RETEST_12 | 49.3% (46.8–51.8) | 1566 | 48.2% | -0.34 | 48.1% | 16138 |
| EVERY_HOUR | SELL | RETEST_12 | 48.8% (46.3–51.4) | 1505 | 48.6% | -0.56 | 47.9% | 16138 |
| FAILED_BREAKOUT | BUY | RETEST_3 | 49.8% (46.7–52.9) | 992 | 47.3% | -0.28 | 48.6% | 3534 |
| FAILED_BREAKOUT | SELL | LIMIT | 49.8% (46.7–52.9) | 1024 | 47.6% | -0.29 | 48.7% | 3882 |
| FVG | BUY | LIMIT | 48.9% (46.0–51.8) | 1160 | 47.9% | -0.45 | 47.1% | 3365 |
| FVG | SELL | RETEST_12 | 51.8% (48.1–55.5) | 693 | 49.0% | +0.26 | 46.8% | 3110 |
| GRAB | BUY | IMM | 52.5% (47.5–57.5) | 377 | 46.5% | +0.61 | 52.5% | 416 |
| GRAB | SELL | CONF_3 | 45.6% (40.1–51.2) | 305 | 47.3% | -1.58 | 44.1% | 492 |
| PD_SWEEP | BUY | IMM | 53.6% (49.0–58.2) | 442 | 46.8% | +0.90 | 53.6% | 1253 |
| PD_SWEEP | SELL | CONF_7 | 49.7% (44.1–55.3) | 302 | 47.3% | -0.35 | 46.7% | 1476 |
| SWEEP | BUY | IMM | 51.0% (47.0–55.1) | 580 | 46.4% | +0.12 | 51.0% | 1703 |
| SWEEP | SELL | RETEST_10 | 51.6% (46.1–57.1) | 308 | 47.2% | +0.27 | 44.9% | 2109 |
| VOL_EXPANSION | BUY | IMM | 50.3% (46.0–54.6) | 513 | 47.7% | -0.08 | 50.3% | 906 |
| VOL_EXPANSION | SELL | CONF_5 | 47.9% (42.7–53.1) | 355 | 49.0% | -0.81 | 44.9% | 933 |

### S3 models (walk-forward 2021-01 .. 2023-01)

| Model | AUC | AUC BUY | AUC SELL | Brier | Brier const | top 1% BUY r (n) | top 1% SELL r (n) | top 10% BUY r | top 10% SELL r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LR | 0.4982 | 0.4911 | 0.5092 | 0.2487 | 0.2475 | 47.2% (1573) | 48.1% (1574) | 47.5% | 48.9% |
| HGB | 0.5240 | 0.5184 | 0.5317 | 0.2451 | 0.2475 | 45.6% (1119) | 50.4% (1216) | 46.8% | 48.7% |
| LGBM | 0.5208 | 0.5153 | 0.5293 | 0.2457 | 0.2475 | 45.5% (789) | 51.7% (895) | 45.6% | 50.3% |
| LGBM_SEP | 0.5190 | 0.5225 | 0.5187 | 0.2468 | 0.2475 | 47.4% (620) | 47.8% (579) | 45.8% | 49.5% |
| ENS | 0.5234 | 0.5204 | 0.5320 | 0.2454 | 0.2475 | 45.2% (810) | 50.9% (914) | 46.5% | 49.6% |

Reliability (ENS, walk-forward): 32.3%→34.1%; 44.1%→45.9%; 44.8%→47.3%; 45.0%→45.6%; 46.0%→47.0%; 46.5%→45.0%; 46.8%→45.0%; 47.1%→47.2%; 48.4%→47.3%

### S4 ranking

| Family dropped | AUC without | Change |
| --- | --- | --- |
| ENGINE | 0.5223 | +0.0016 |
| TREND | 0.5240 | +0.0033 |
| OSCILLATOR | 0.5232 | +0.0024 |
| VOLATILITY | 0.5211 | +0.0003 |
| LIQUIDITY | 0.5320 | +0.0112 |
| STRUCTURE_SMC | 0.5270 | +0.0062 |
| MOMENTUM | 0.5263 | +0.0056 |
| TIME_NEWS | 0.5043 | -0.0164 |
| MARKOV | 0.5196 | -0.0011 |

Permutation AUC drop (top 12): nd_weekday +0.0160; nd_hour_sin +0.0111; nd_atr_rank +0.0021; sg_di_diff +0.0021; sg_d_e200 +0.0019; nd_ny +0.0019; sg_prem_disc +0.0017; sg_since_up_minus_dn +0.0016; sg_d_e100 +0.0014; sg_pct_b +0.0014; sg_slope100 +0.0011; sg_d_vwap +0.0011

Univariate AUC furthest from 0.5 (top 12): nd_weekday 0.4754; nd_hour_sin 0.5243; nd_ny 0.4778; sg_trend_1d 0.5143; nd_range_atr 0.5113; nd_sess_q 0.4896; sg_day_pos_c 0.4913; nd_atr_ratio 0.4915; sg_prem_disc 0.5083; sg_di_diff 0.5074; sg_slope100 0.5073; sg_pct_b 0.4934

### S5 regimes (development)

| Regime | BUY r (95%) | BUY n | BUY random | SELL r (95%) | SELL n | SELL random |
| --- | --- | --- | --- | --- | --- | --- |
| CONTRACTION | 48.9% (45.2–52.5) | 714 | 48.4% | 47.3% (43.7–50.9) | 717 | 46.7% |
| EXPANSION | 47.9% (45.4–50.4) | 1487 | 47.7% | 48.7% (46.1–51.2) | 1494 | 48.2% |
| LIQUIDITY | 50.1% (47.6–52.6) | 1526 | 47.6% | 46.5% (44.0–49.0) | 1539 | 48.2% |
| NEWS | 50.3% (44.8–55.9) | 308 | 46.6% | 45.3% (39.8–50.9) | 307 | 49.3% |
| POST_NEWS | 49.2% (40.7–57.8) | 128 | 47.6% | 44.5% (36.2–53.2) | 128 | 48.0% |
| REVERSAL | 49.3% (45.9–52.8) | 801 | 47.8% | 46.5% (43.1–50.0) | 798 | 47.9% |
| SIDEWAYS | 48.8% (45.9–51.7) | 1125 | 48.1% | 47.9% (45.0–50.8) | 1130 | 47.7% |
| STRONG_BEAR | 47.2% (44.0–50.5) | 915 | 45.4% | 47.9% (44.7–51.2) | 901 | 50.5% |
| STRONG_BULL | 46.5% (43.1–49.9) | 807 | 49.6% | 49.4% (46.0–52.8) | 820 | 46.2% |
| WEAK_BEAR | 48.0% (45.2–50.7) | 1249 | 47.4% | 48.5% (45.7–51.3) | 1228 | 48.3% |
| WEAK_BULL | 48.4% (45.7–51.2) | 1257 | 48.0% | 46.8% (44.1–49.6) | 1279 | 47.8% |

### S6 intermarket, 2026 (descriptive)

| Series / quintile | r | n | random | BH |
| --- | --- | --- | --- | --- |
| S6 DXY Q1 BUY | 45.8% | 767 | 43.6% | no |
| S6 DXY Q2 BUY | 43.9% | 724 | 44.2% | no |
| S6 DXY Q3 BUY | 48.0% | 711 | 44.7% | no |
| S6 DXY Q4 BUY | 43.7% | 764 | 43.7% | no |
| S6 DXY Q5 BUY | 44.2% | 849 | 43.3% | no |
| S6 DXY Q1 SELL | 50.1% | 840 | 52.2% | no |
| S6 DXY Q2 SELL | 50.9% | 768 | 51.8% | no |
| S6 DXY Q3 SELL | 48.1% | 711 | 50.8% | no |
| S6 DXY Q4 SELL | 50.4% | 728 | 51.3% | no |
| S6 DXY Q5 SELL | 49.9% | 757 | 52.0% | no |
| S6 US10Y Q1 BUY | 43.5% | 565 | 42.9% | no |
| S6 US10Y Q2 BUY | 46.0% | 559 | 43.9% | no |
| S6 US10Y Q3 BUY | 41.5% | 573 | 43.5% | no |
| S6 US10Y Q4 BUY | 48.4% | 574 | 44.0% | no |
| S6 US10Y Q5 BUY | 45.3% | 695 | 43.4% | no |
| S6 US10Y Q1 SELL | 49.9% | 696 | 52.1% | no |
| S6 US10Y Q2 SELL | 46.4% | 582 | 51.4% | no |
| S6 US10Y Q3 SELL | 52.9% | 490 | 51.7% | no |
| S6 US10Y Q4 SELL | 49.8% | 613 | 51.8% | no |
| S6 US10Y Q5 SELL | 51.3% | 561 | 52.8% | no |
| S6 EURUSD Q1 BUY | 44.8% | 837 | 42.9% | no |
| S6 EURUSD Q2 BUY | 43.4% | 760 | 44.3% | no |
| S6 EURUSD Q3 BUY | 45.3% | 706 | 44.0% | no |
| S6 EURUSD Q4 BUY | 46.1% | 729 | 44.5% | no |
| S6 EURUSD Q5 BUY | 45.6% | 769 | 43.7% | no |
| S6 EURUSD Q1 SELL | 50.5% | 764 | 51.9% | no |
| S6 EURUSD Q2 SELL | 48.1% | 729 | 51.0% | no |
| S6 EURUSD Q3 SELL | 50.3% | 706 | 51.3% | no |
| S6 EURUSD Q4 SELL | 51.8% | 755 | 51.2% | no |
| S6 EURUSD Q5 SELL | 50.2% | 832 | 52.6% | no |
| S6 SILVER Q1 BUY | 45.2% | 893 | 43.0% | no |
| S6 SILVER Q2 BUY | 44.7% | 704 | 44.0% | no |
| S6 SILVER Q3 BUY | 46.7% | 685 | 44.5% | no |
| S6 SILVER Q4 BUY | 44.3% | 742 | 44.3% | no |
| S6 SILVER Q5 BUY | 47.5% | 733 | 43.8% | no |
| S6 SILVER Q1 SELL | 47.7% | 733 | 51.8% | no |
| S6 SILVER Q2 SELL | 50.7% | 743 | 51.1% | no |
| S6 SILVER Q3 SELL | 50.5% | 691 | 51.0% | no |
| S6 SILVER Q4 SELL | 50.9% | 698 | 51.7% | no |
| S6 SILVER Q5 SELL | 49.4% | 890 | 52.7% | no |
| S6 SPX Q1 BUY | 46.8% | 720 | 43.9% | no |
| S6 SPX Q2 BUY | 45.8% | 592 | 43.8% | no |
| S6 SPX Q3 BUY | 46.8% | 504 | 44.2% | no |
| S6 SPX Q4 BUY | 44.2% | 536 | 43.8% | no |
| S6 SPX Q5 BUY | 44.3% | 618 | 43.3% | no |
| S6 SPX Q1 SELL | 51.2% | 609 | 52.5% | no |
| S6 SPX Q2 SELL | 51.8% | 541 | 52.0% | no |
| S6 SPX Q3 SELL | 47.9% | 511 | 51.1% | no |
| S6 SPX Q4 SELL | 50.1% | 589 | 51.8% | no |
| S6 SPX Q5 SELL | 48.2% | 722 | 51.6% | no |
