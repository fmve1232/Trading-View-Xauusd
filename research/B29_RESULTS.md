# B29: Track B — dynamic TP / SL (2026-11-09)

| Item | Where |
|---|---|
| Registration | `research/registrations/B29.json`, committed `ffc0b6857` before any code. Three amendments to study V's test, committed in `9a86c684c`, were all found by the null check before any real result. |
| Code, tests and the null check | `quantum/research/b29.py`, `tests/test_research_b29.py`, `research/tools/phasec_null_check.py`; committed `9a86c684c` before any real result |
| Results | `research/results/b29/` (listed below) |
| Diagnostics (after the run, descriptive) | `research/tools/b29_grid_extra.py` (monthly and regime results for every pair), `research/tools/phasec_c_diagnostic.py` (where the model AUC comes from), `research/tools/phasec_breakeven_audit.py`; outputs in `research/results/b29/` and `research/results/phasec/` |
| Tables | `research/tools/phasec_tables.py` (appendix of `PHASE_C_REPORT.md`), `research/tools/phasec_risk.py` |

**Result files in `research/results/b29/`:**
- `b29_summary.json`;
- `b29_grid.csv`: every pair × direction × cost scenario;
- `b29_grid_extra.csv.gz`;
- `b29_V/M/C/E.csv.gz`;
- `b29_frozen_trades.csv.gz`: every trade of the 30 frozen candidates, development and 2026.

**Branch:** `claude/research-phase-c`. Research only. Production, web.8, the frozen Pine files, the alerts and PRs #90 / #91 are untouched.

## The answer

**Changing the TP / SL pair changes the hit rate exactly as a driftless price predicts, and never the sign of the result. No pair, volatility scaling, trend signal, model or trigger family makes money after costs.**

1. **The grid (101 pairs × BUY / SELL, every eligible bar, 2020–22) is the no-information arithmetic, measured.**
   - **Measured rates match theory.** 96.5% of the 202 rows lie within 2 points of the theory rate p₀ = (SL − Δ) / (TP + SL). None is significantly above it; the largest shortfalls are the small brackets marked INCONCLUSIVE.
   - **Every row loses after costs.** 0 of 202 rows have positive expectancy under the engine's costs. Expectancy runs from −$1.32 to −$0.14 per oz (median −$0.79), whatever the pair.
   - **The highest hit rate loses money.** +$3 / −$30 SELL wins 89.5% of decided trades, but needs 91.2% to break even. At 0.50 lot (ASSUMED 100 oz) one stop costs about $1,538, which is 12.7 wins of $121. Expectancy: −$40 a trade, about −$2,000 a week at its trade rate.
   - **The least-bad pair is a drift effect.** +$25 / −$30 BUY loses $0.14 per oz (−$0.005 per $ of risk).
     - The least-bad rows are all BUYs on large brackets, because gold rose over 2020–22.
     - The mirror SELLs lose $1.17–1.24 per oz.
     - On 2026 the same BUY lost $2.42 per oz.
2. **Volatility-scaled exits (V, 25 ATR brackets): 0 of 50 pass.**
   - The registered test, pooled BUY + SELL ENG expectancy > 0, fails for every bracket (p ≥ 0.997).
   - ATR scaling lands within a few hundredths of a dollar per $ of risk of the fixed-dollar pair of the same median size, sometimes better and sometimes worse. It is a different sizing of the same coin.
3. **Time-series momentum (M, 20 / 60 days, 7 large brackets): 0 of 14 pass.**
   - The best is TSMOM20 at +$25 / −$25: 50.3% against a 48.8% direction-neutral random, p = 0.17, expectancy −$0.04 per oz.
   - The past trend did pick the month's eventual direction more often than not: the same-direction random is 1.7–3.9 points above the neutral one.
   - But its own trades realised the neutral rate, not the same-direction rate. **No momentum is usable at a 2-day trade horizon.**
4. **A calibrated model per bracket (C, 7 brackets): 0 of 84 pass.**
   - **The AUC rises with bracket size:** 0.504 → 0.534. The same model on a random walk rises the same way: 0.498 → 0.544.
   - **The rise is closures, not direction.**
     - On decided trades only (TP against SL), the AUC is 0.496–0.506.
     - A forecast from weekday × hour alone scores higher than the model.
     - The extra AUC is the model learning that late-Friday entries end at the weekend close.
5. **Every trigger family per bracket (E, 21 families × 7 brackets): 0 of 294 pass.**
   - The best lift is PD_SWEEP BUY at +$30 / −$20: 44.9% against 38.4% random (n = 312), p = 0.011 against a BH threshold of about 0.0002.
   - The random walk's best lift under the same framework is +5.3 points.
6. **Frozen and checked on 2026: none of 30 holds** (Holm p = 1.000 for 29, 0.879 for one). Every grid candidate lost more on 2026 than on development.

## The grid: rates against theory (2020–22, ENG)

| Pair | Dir | TP-first worst | TP-first best | Theory p₀ (in session) | Break-even | Exp / oz | Exp / $ risk | PF | Neither | Trades / wk |
|---|---|---|---|---|---|---|---|---|---|---|
| +3 / −3 | BUY | 37.2% | 46.3% | 41.7% | 52.7% | −0.96 | −0.321 | 0.53 | 0.1% | 263 |
| +3 / −30 | SELL | 89.5% | 89.6% | 89.4% | 91.2% | −0.79 | −0.026 | 0.76 | 2.1% | 50 |
| +5 / −10 | BUY | 62.2% | 63.2% | 63.3% | 67.6% | −0.83 | −0.083 | 0.79 | 0.8% | 87 |
| +8 / −10 | BUY | 52.4% | 53.1% | 52.8% | 56.4% | −0.72 | −0.072 | 0.85 | 1.4% | 63 |
| +10 / −10 | BUY | 47.4% | 47.9% | 47.5% | 50.8% | −0.67 | −0.067 | 0.87 | 1.7% | 53 |
| +15 / −15 | BUY | 48.0% | 48.1% | 48.3% | 50.6% | −0.72 | −0.048 | 0.91 | 4.0% | 27 |
| +20 / −10 | BUY | 31.7% | 32.0% | 31.7% | 34.0% | −0.52 | −0.052 | 0.92 | 3.6% | 30 |
| +20 / −20 | BUY | 48.6% | 48.8% | 48.8% | 50.4% | −0.64 | −0.032 | 0.94 | 6.8% | 16 |
| +25 / −30 | BUY | 54.9% | 55.1% | 54.5% | 56.3% | −0.14 | −0.005 | 0.99 | 13.9% | 10 |
| +30 / −30 | BUY | 49.2% | 49.2% | 49.2% | 50.3% | −0.23 | −0.008 | 0.98 | 17.3% | 8 |
| +30 / −30 | SELL | 49.0% | 49.0% | 49.2% | 50.3% | −1.17 | −0.039 | 0.92 | 16.9% | 8 |

The full 101-pair table, both directions, with SL-first share, minutes to TP / SL, longest losing run, drawdown and the four cost scenarios, is in `b29_grid.csv` and the appendix of `PHASE_C_REPORT.md`.

**Reading the grid:**
- **TP-first rises with SL / TP and falls with TP / SL exactly as p₀ says.** The break-even rises in step, so the expectancy stays negative everywhere.
- **Costs are a larger share of small brackets.**
  - +$3 / −$3 loses about a third of the risk per trade (−0.321 per $ of risk).
  - +$30 / −$30 loses under 1% (−0.008 per $ of risk) and trades 8 times a week instead of 263.
- **GROSS and OP are upper references, not achievable.**
  - 74 of 202 rows show positive GROSS expectancy and 12 positive OP expectancy ($0.26 spread only).
  - Both fill the stop exactly at its level. On a moving price a stop fills beyond it, and that omission favours the brackets that are stopped most (registration amendment 3, measured on the random walk).
  - The positive OP rows are all large-bracket BUYs, the drift of the period.
  - ENG's $0.20 stop slippage covers the overshoot; 0 rows are positive under ENG or ADV.

### Resolution: 15m bounds against the store's 5m bars (Sep–Nov 2026, same decisions)

| Pair / dir | n | 15m worst | 15m best | 5m worst | 5m best |
|---|---|---|---|---|---|
| +3 / −3 BUY | 3,807 | 33.7% | 47.3% | 37.5% | 41.7% |
| +5 / −5 BUY | 3,801 | 39.8% | 43.6% | 40.7% | 41.7% |
| +5 / −10 BUY | 3,773 | 58.9% | 60.4% | 59.3% | 59.8% |
| +10 / −10 BUY | 3,742 | 41.8% | 42.9% | 42.2% | 42.8% |
| +15 / −15 BUY | 3,688 | 41.9% | 43.2% | 42.0% | 43.2% |
| +3 / −30 BUY | 3,763 | 87.6% | 88.2% | 87.6% | 88.2% |

- **Small brackets are bounded, not measured.** At 15m, 12 rows are INCONCLUSIVE: the six smallest pairs (+3 / −3, +3 / −5, +3 / −7, +5 / −3, +5 / −5, +7 / −3), both directions. 5m narrows +$3 / −$3 from 13.6 points to 4.2, and the 5m best case (41.7%) is the no-information rate. **No bound of any small bracket reaches its break-even.**
- **From +$5 / −$10 up, 15m and 5m agree to within a point.**

### Per-pair stability (`b29_grid_extra.csv.gz`)

- **No pair has half its months profitable.**
  - The median pair is profitable in 23.5% of its 34 months.
  - The best is 47.1% (16 of 34 months), reached by six pair-and-direction rows, among them +$15 / −$30 BUY and SELL.
  - Pairs profitable in at least half the months: 0 of 202.
- **Regimes do not rescue any pair.**
  - The TP-first rate moves a median 1.2 points across volatility terciles (at most 7.5).
  - 95 of 2,229 regime cells (volatility tercile, trend state, session; ≥ 100 trades) have positive expectancy: 4.3%. Noise around a negative mean produces about that many.

## V: volatility-scaled exits (TP = a × ATR14, SL = b × ATR14; a, b ∈ {0.5, 1, 1.5, 2, 3})

- **Every bracket's pooled ENG expectancy is negative:** from −$0.69 to −$0.94 per oz; one-sided p ≥ 0.997. **0 BH, 0 INFORMATIVE.**
- **Against the fixed-dollar pair of the same median size** (described, not tested):
  - ATR scaling is better on 24 rows, worse on 26, by at most 0.08 per $ of risk.
  - Example: ATR 1× / 1× BUY (median $4.7 / $4.7) gives −0.170 per $ of risk against −0.178 for +$5 / −$5.
- **The highest-rate ATR bracket repeats the grid's lesson:** 0.5× / 3× (median $2.4 / $14.2) wins 82% and loses $0.75–0.82 per oz.

## M: time-series momentum (Moskowitz, Ooi and Pedersen 2012), direction-neutral baseline

| Signal / bracket | TP-first (95%) | n | Neutral random | Same-direction random | Exp / oz | p |
|---|---|---|---|---|---|---|
| TSMOM20 +25 / −25 | 50.3% (47.3–53.3) | 1,055 | 48.8% | 51.6% | −0.04 | 0.173 |
| TSMOM60 +30 / −30 | 50.3% (46.8–53.9) | 753 | 49.0% | 51.8% | −0.13 | 0.236 |
| TSMOM20 +30 / −30 | 50.0% (46.5–53.5) | 776 | 49.0% | 52.9% | −0.23 | 0.294 |
| TSMOM60 +30 / −20 | 38.9% (36.0–41.8) | 1,050 | 38.4% | 40.6% | −0.18 | 0.391 |
| TSMOM20 +20 / −20 | 47.8% (45.2–50.4) | 1,420 | 48.5% | 51.0% | −0.95 | 0.703 |

All 14 rows are in the appendix. **0 BH.**
- **The past 20 / 60 days chose the right month more often than not.** The same-direction random is above the neutral one on every row.
- **The trades did not benefit.** They realised the neutral rate, not the same-direction rate.
- **The registration anticipated this:** a same-direction, same-month baseline already contains the drift the signal is trying to predict, so it is not the test.

## C: a calibrated LightGBM per bracket (walk-forward 2021-01 → 2023-01)

| Bracket | AUC | AUC on decided trades only | Weekday × hour forecast AUC | Same model on a random walk |
|---|---|---|---|---|
| +5 / −10 | 0.504 | 0.496 | 0.517 | 0.498 |
| +10 / −10 | 0.514 | 0.500 | 0.522 | 0.504 |
| +10 / −15 | 0.523 | 0.500 | 0.534 | 0.510 |
| +15 / −10 | 0.523 | 0.506 | 0.527 | 0.511 |
| +20 / −10 | 0.520 | 0.504 | 0.527 | 0.516 |
| +20 / −20 | 0.531 | 0.499 | 0.557 | 0.539 |
| +30 / −20 | 0.534 | 0.499 | 0.559 | 0.544 |

**What the table shows:**
- **No direction information.** Every bracket's model is at 0.50 on the trades that reach TP or SL, and below the calendar-only forecast on all trades.
- **The AUC is the calendar.** It rises with the share of trades ending without TP or SL (weekend / holiday closures, 2-day limit), and a random walk shows the same rise.
- **Brier barely beats the constant forecast.** The best margin is 0.0029 at +$20 / −$20, and at +$5 / −$10 the model is worse than the constant.

**"Top q" selections are not q.**
- **What the threshold does.** The training window's threshold is a quantile of isotonic-calibrated probabilities. Isotonic output is a step function, so a threshold at a step admits the whole step.
- **The effect.** The realised selected shares are far above the nominal q (appendix). That is why top 1% and top 50% give almost the same trades.
- **It does not change the result:** every share selected is at the random rate.
- **B27 saw the same effect on 2026** ("isotonic plateau"). Here it is measured in the walk-forward too.

## E: every trigger family per bracket (immediate entry, each family's own direction)

| Bracket | Best family / dir (by lower bound, n ≥ 300) | TP-first (95%) | n | Random | Exp / oz |
|---|---|---|---|---|---|
| +5 / −10 | EVERY_HOUR SELL | 63.0% (62.0–64.1) | 8,056 | 63.1% | −0.72 |
| +10 / −10 | EVERY_HOUR SELL | 46.9% (45.5–48.2) | 5,527 | 47.0% | −0.82 |
| +10 / −15 | EVERY_HOUR SELL | 57.6% (56.1–59.2) | 4,094 | 57.8% | −0.84 |
| +15 / −10 | PD_SWEEP BUY | 41.2% (37.1–45.3) | 554 | 36.5% | +0.14 |
| +20 / −10 | PD_SWEEP BUY | 33.5% (29.6–37.7) | 513 | 30.0% | −0.01 |
| +20 / −20 | BOS BUY | 52.1% (47.6–56.6) | 474 | 49.1% | +0.79 |
| +30 / −20 | PD_SWEEP BUY | 44.9% (39.4–50.4) | 312 | 38.4% | +2.56 |

- **0 of 294 are BH-significant.** The 17 rows with positive development expectancy (≥ 300 trades) are BUYs on brackets of +$15 and more, the period's drift again; none is significant.
- **The frozen E candidates fell on 2026**, e.g. PD_SWEEP +$5 / −$10 BUY: 64.0% → 56.4% against a 58.8% random.
- **Registered ranking, noted for future registrations.** Ranking the frozen set by the absolute lower bound favours high-base-rate brackets (the +$5 / −$10 rows fill E's top-5) rather than the largest lift. A future registration should rank by lift over random. The lift leaders here were not frozen and were not checked on 2026, per the registration.

## Frozen candidates on 2026 (30)

V 5, M 5, C 5, E 10, G 5; every one is in leaderboard B in the appendix of `PHASE_C_REPORT.md`.
- **Holm p = 1.000 for 29 and 0.879 for one** (+$20 / −$30 BUY). None holds.
- **The 5 grid candidates (large-bracket BUYs) lost $2.0–2.4 per oz on 2026**, against −$0.14 to −$0.40 in development. Gold's 2026 drift ran the other way: the drift is not a forecast.

## Checks

- **The engine equals a plain race.**
  - It reproduces a line-by-line race on (15, 15), (5, 10), (20, 10), (30, 20) and (3, 30) (`tests/test_research_b29.py`).
  - Its ±$15 row equals B26 exactly: BUY 47.95% on 3,808 trades, −$0.722 per oz; SELL 48.00% on 3,819 trades, −$0.810.
- **The null check:**
  - **Before the real run**, on a path-consistent synthetic random walk, it flagged 0 of 442 V / M / C / E configurations.
  - **It found three biases in study V's registered test** (size mismatch, drift, stop overshoot). All three were corrected by amendment before any real result.
- **Causality.** TSMOM uses only completed New York days. Every model feature is from closed bars.
- **Every configuration is logged.** All 202 grid rows, 442 configurations and 30 frozen 2026 checks are in `research/trials.jsonl`.
- **Break-even comparator (audit, after the run).**
  - **The defect.** The summary's `break_even` is the break-even of the TP share of *all* trades. Beside the decided rate it is too low when closures are common: by 6.7–9.8 points for the M and large-grid candidates, whose closures run 13–20%.
  - **The fix.** The consistent `break_even_decided` was added afterwards, with a test, and the tier rules now use it.
  - **No verdict changes** (nothing was INFORMATIVE); `PHASE_C_REPORT.md` §6 has the detail.
  - **The grid tables never used the old field;** they show the theory break-even.
