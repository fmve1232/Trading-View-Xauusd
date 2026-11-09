# B28: Track A — eight new trigger families at +$15 / −$15 (2026-11-09)

| Item | Where |
|---|---|
| Registration | `research/registrations/B28.json`, committed `ffc0b6857` before any code |
| Code, tests and the null check | `quantum/research/b28.py`, `tests/test_research_b28.py`, `research/tools/phasec_null_check.py`; committed `9a86c684c` before any real result |
| Results | `research/results/b28/`: `b28_summary.json`, `b28_configs.csv.gz` (one row per configuration), `b28_frozen_trades.csv.gz` (every trade of the 10 frozen candidates, development and 2026) |
| Resolution check of order entries | `research/tools/phasec_fillbar_check.py` → `research/results/phasec/phasec_fillbar.json` (after the run; descriptive) |
| Tables | `research/tools/phasec_tables.py` (appendix of `PHASE_C_REPORT.md`) |

**Branch:** `claude/research-phase-c`. Research only. Production, web.8, the frozen Pine files, the alerts and PRs #90 / #91 are untouched.

## The answer

**None of the eight new families beats its matched random rate at ±$15, with any of the 20 entry mechanisms, in either direction.**

1. **320 configurations** (8 families × 20 entry modes × BUY / SELL) were tested on 2020–22 development data:
   - families: LONDON_ORB, NY_ORB, ENGULF_LEVEL, PINBAR_LEVEL, CHOCH_RETEST, OB_RETEST, SWEEP_DISPLACEMENT, SUPERTREND;
   - modes: immediate entry ($0); close-confirmation, retest-limit and stop entries at $3 / 5 / 8 / 10 / 15 / 20; the structure limit.

   **0 BH-significant, 0 INFORMATIVE, 0 TRADEABLE.** Only 2 of 320 have a raw one-sided p below 0.05 (16 are expected by chance). The smallest p is 0.020 (NY_ORB STOP_3 BUY, 214 trades).
2. **The real results are no better than a random walk's.**

   | B28 on | Configurations with ≥ 300 trades | Largest lift over random | Smallest p | Positive expectancy (≥ 300 trades) |
   |---|---|---|---|---|
   | Real 2020–22 | 93 | +3.2 points | 0.020 | 10 |
   | Path-consistent random walk (same framework) | 25 | +4.8 points | 0.004 | 9 |

   The synthetic development history is shorter (26,964 15m bars against 70,173), so fewer of its configurations reach 300 trades.

3. **Combinations were not tested.** The registered rule allows combinations only of INFORMATIVE single hypotheses (B27 or B28), and there are none.
4. **The 10 frozen candidates all fell back on 2026** (Holm p = 1.000 for every one). Examples:
   - NY_ORB IMM BUY: 53.8% → 40.0%;
   - SUPERTREND CONF_8 BUY: 51.3% → 44.6%;
   - ENGULF_LEVEL CONF_5 BUY: 50.9% → 41.0%.

## Confirmation distance and entry mechanism (pooled over the 8 families and both directions, 2020–22)

| Mode | Trades | TP-first | Matched random | Lift (points) | Exp / oz per trade | Fill rate | Exp / oz per trigger |
|---|---|---|---|---|---|---|---|
| IMM ($0) | 7,075 | 47.5% | 48.0% | −0.5 | −0.95 | 100% | −0.91 |
| CONF_3 | 5,069 | 47.8% | 48.2% | −0.4 | −0.85 | 71% | −0.59 |
| CONF_5 | 4,608 | 48.1% | 48.3% | −0.2 | −0.76 | 64% | −0.46 |
| CONF_8 | 4,031 | 48.5% | 48.5% | −0.0 | −0.67 | 57% | −0.42 |
| CONF_10 | 3,733 | 47.5% | 48.5% | −1.1 | −0.96 | 52% | −0.49 |
| CONF_15 | 3,054 | 46.2% | 48.6% | −2.4 | −1.29 | 44% | −0.57 |
| CONF_20 | 2,567 | 47.1% | 48.6% | −1.6 | −1.04 | 37% | −0.36 |
| RETEST_3 | 4,142 | 47.9% | 48.0% | −0.1 | −0.84 | 57% | −0.45 |
| RETEST_5 | 3,741 | 48.2% | 48.3% | −0.0 | −0.72 | 52% | −0.35 |
| RETEST_8 | 3,278 | 47.9% | 48.5% | −0.6 | −0.80 | 45% | −0.36 |
| RETEST_10 | 3,072 | 48.5% | 48.4% | +0.1 | −0.63 | 42% | −0.29 |
| RETEST_15 | 2,462 | 46.6% | 48.4% | −1.8 | −1.17 | 34% | −0.39 |
| RETEST_20 | 2,058 | 47.5% | 48.6% | −1.1 | −0.90 | 29% | −0.25 |
| STOP_3 | 5,899 | 47.4% | 48.1% | −0.7 | −0.99 | 83% | −0.76 |
| STOP_5 | 5,266 | 47.6% | 48.2% | −0.6 | −0.90 | 74% | −0.62 |
| STOP_8 | 4,513 | 47.3% | 48.3% | −1.0 | −0.95 | 63% | −0.64 |
| STOP_10 | 4,111 | 46.6% | 48.4% | −1.8 | −1.19 | 58% | −0.75 |
| STOP_15 | 3,356 | 40.7% | 48.7% | −8.0 | −2.86 | 47% | −1.32 |
| STOP_20 | 2,755 | 39.3% | 48.8% | −9.5 | −3.27 | 39% | −1.29 |
| LIMIT (structure) | 3,419 | 48.1% | 47.8% | +0.4 | −0.67 | 50% | −0.31 |

Pooled descriptively (trades weighted); each configuration was tested on its own.

**What the table shows:**
- **Waiting for confirmation does not raise the hit rate.** No mode is more than 0.4 points above its random rate. Every mode is within 2.4 points below it, except stop entries of $10 or more (next section).
- **Confirmation lowers the loss per signal only by skipping trades.**
  - At $20, only 29–39% of triggers ever fill, so the loss per trigger is smaller.
  - The loss per trade taken is the same or worse.
  - "Fewer trades" is not an edge.
- **Confirmed shares are what a driftless price gives.** A trigger reaches a close $3 beyond its entry before touching −$15 in 71% of cases, $8 in 57% and $20 in 37%. A random walk touching the level gives 83% / 65% / 43%; requiring a close rather than a touch lowers these.

### Resolution of order entries (audit, after the run)

**The rule being checked.** Retest, stop and structure-limit orders fill inside a 15m bar. B27 / B28 count that bar only against the trade: its adverse extreme can stop the trade, and its favourable extreme never counts. On 15m bars the order of the two extremes is unknown, so this is the **worst case**.

**Why stop entries are hit hardest.** A $15–$20 stop entry is usually filled by one large bar whose low lies near the trigger. The worst case then books a loss that needs the low to come *after* the fill.

**The check.** `phasec_fillbar_check.py` raced every order entry of all 21 families (B27's 13 and B28's 8) again in the **best case** for the fill bar: the adverse extreme came before the fill, and the favourable extreme after it. B29's rule then marks a gap above 2 points INCONCLUSIVE.

| Mode (pooled over 21 families, both directions) | Trades | Stopped on the fill bar (worst) | TP-first worst | TP-first best | Gap | Random | Verdict |
|---|---|---|---|---|---|---|---|
| Structure LIMIT | 9,368 | 1.4% | 48.6% | 49.4% | +0.8 | 47.8% | conclusive |
| RETEST, X < $15 | 74,648 | 1.0% | 48.4% | 49.2% | +0.9 | 48.3% | conclusive |
| RETEST, X ≥ $15 | 20,083 | 1.9% | 48.1% | 49.4% | +1.3 | 48.6% | conclusive |
| STOP_3 / 5 / 7 / 8 | 65,639 | 1.1–3.3% | 46.4–47.3% | 47.5–49.1% | +0.7 to +1.8 | 48.1–48.3% | conclusive |
| STOP_10 / STOP_12 | 28,689 | 4.2% / 5.8% | 45.6% / 43.9% | 48.0% / 47.4% | +2.4 / +3.5 | 48.4–48.5% | **INCONCLUSIVE** |
| STOP_15 / STOP_20 | 24,853 | 10.5% / 14.5% | 40.8% / 39.1% | 47.5% / 46.4% | +6.7 / +7.3 | 48.6–48.7% | **INCONCLUSIVE** |

**What the check shows:**
- **The −8 to −9.5 point "lift" of STOP_15 / STOP_20 is a resolution artefact, not a measured reversal.** In the best case they are still **at or below random** (47.5% / 46.4% against 48.6–48.7%). So neither bound shows an edge; only the size of the loss is uncertain.
- **Retest and limit entries are resolved at 15m** (gap ≤ 1.5 points).
- **No order-entry configuration of any family passes BH even in the best case** (0 of 582; smallest p = 0.0003, against a BH threshold of about 0.0001).
  - The best-case leaders are the same configurations that failed on 2026, for example PD_SWEEP LIMIT BUY: 54.5% worst, 55.3% best, against 46.8% random, and 36.0% on 2026.
- **The worst case cannot create a false winner;** it can only hide one. The best-case check shows it hid none.
- **Large stop entries need 5m or 1m data** to be measured, not bounded.

## Best mode per family (2020–22, by Wilson lower bound, ≥ 300 trades)

| Family | Dir | Best mode | TP-first (95%) | n | Random | Exp / oz | Immediate | Triggers |
|---|---|---|---|---|---|---|---|---|
| LONDON_ORB | BUY | IMM | 44.0% (38.7–49.4) | 332 | 46.2% | −1.99 | 44.0% | 339 |
| LONDON_ORB | SELL | IMM | 48.9% (43.4–54.4) | 311 | 50.0% | −0.48 | 48.9% | 328 |
| NY_ORB | BUY | — (no mode with 300 trades) | | 266 (IMM) | 48.8% | +0.90 (IMM) | 53.8% | 297 |
| NY_ORB | SELL | — (no mode with 300 trades) | | 278 (IMM) | 48.7% | −0.89 (IMM) | 47.8% | 303 |
| ENGULF_LEVEL | BUY | CONF_5 | 50.9% (46.2–55.6) | 438 | 47.9% | +0.12 | 47.6% | 899 |
| ENGULF_LEVEL | SELL | IMM | 49.4% (45.8–53.0) | 725 | 48.3% | −0.44 | 49.4% | 1,014 |
| PINBAR_LEVEL | BUY | STOP_5 | 48.1% (43.2–53.0) | 395 | 47.2% | −0.70 | 46.9% | 664 |
| PINBAR_LEVEL | SELL | LIMIT | 48.1% (43.0–53.2) | 362 | 47.7% | −0.82 | 43.8% | 559 |
| CHOCH_RETEST | BUY | IMM | 50.8% (45.4–56.1) | 333 | 48.0% | +0.04 | 50.8% | 364 |
| CHOCH_RETEST | SELL | IMM | 48.5% (43.1–53.9) | 324 | 48.2% | −0.71 | 48.5% | 361 |
| OB_RETEST | BUY | CONF_5 | 51.0% (45.4–56.4) | 314 | 47.9% | +0.09 | 46.9% | 605 |
| OB_RETEST | SELL | CONF_5 | 51.3% (46.0–56.6) | 337 | 49.4% | +0.16 | 48.1% | 644 |
| SWEEP_DISPLACEMENT | BUY | — (no mode with 300 trades) | | 156 (IMM) | 46.5% | −1.72 (IMM) | 44.9% | 169 |
| SWEEP_DISPLACEMENT | SELL | — (no mode with 300 trades) | | 163 (IMM) | 47.9% | −0.72 (IMM) | 48.5% | 180 |
| SUPERTREND | BUY | CONF_8 | 51.3% (46.6–56.0) | 427 | 48.3% | +0.25 | 46.4% | 870 |
| SUPERTREND | SELL | RETEST_10 | 50.9% (45.5–56.4) | 320 | 49.8% | +0.04 | 45.9% | 867 |

**Notes on the families:**
- **Opening-range breakouts:**
  - London's lose in both directions.
  - New York's BUY looked best on development (53.8%, 266 trades, p = 0.058) and gave 40.0% on 2026.
- **Reversal candles at a level** (engulfing, pin bar):
  - Immediately, three of the four are within about 1 point of random; the pin-bar SELL is 3.9 points below.
  - The best confirmation mode adds up to 3 points on development (engulfing BUY, CONF_5). That is not significant after BH, and it gave 41.0% on 2026.
- **Supertrend flips** (ATR 10 × 3):
  - Immediately: about 46% in both directions, 1.5–2.5 points below random.
  - The best confirmed / retest modes reach up to 3 points above random, which is not significant after BH. The frozen one (CONF_8 BUY) gave 44.6% on 2026.
- **Sweep then displacement** is rare: 349 triggers in three years, so no mode reaches 300 trades.

## Frozen candidates on 2026

| Candidate | Dev TP-first (n) | Dev random | Dev exp / oz | 2026 TP-first (n) | 2026 random | 2026 exp / oz |
|---|---|---|---|---|---|---|
| SUPERTREND CONF_8 BUY | 51.3% (427) | 48.3% | +0.25 | 44.6% (112) | 44.1% | −1.79 |
| ENGULF_LEVEL CONF_5 BUY | 50.9% (438) | 47.9% | +0.12 | 41.0% (100) | 43.7% | −2.89 |
| ENGULF_LEVEL CONF_8 BUY | 51.2% (377) | 48.0% | +0.12 | 43.4% (83) | 44.8% | −2.26 |
| OB_RETEST CONF_5 SELL | 51.3% (337) | 49.4% | +0.16 | 45.3% (75) | 51.8% | −1.58 |
| OB_RETEST CONF_3 SELL | 50.9% (369) | 49.2% | +0.07 | 45.7% (81) | 52.0% | −1.51 |
| NY_ORB STOP_3 BUY | 55.6% (214) | 48.4% | +1.25 | 42.9% (56) | 43.9% | −2.49 |
| NY_ORB IMM BUY | 53.8% (266) | 48.8% | +0.90 | 40.0% (70) | 43.6% | −3.08 |
| OB_RETEST RETEST_5 SELL | 53.2% (280) | 49.3% | +0.74 | 46.8% (62) | 51.8% | −1.05 |
| SWEEP_DISPLACEMENT RETEST_8 SELL | 58.3% (72) | 47.9% | +2.23 | 46.7% (15) | 52.0% | −0.82 |
| NY_ORB LIMIT BUY | 54.0% (161) | 48.4% | +1.17 | 40.0% (40) | 43.0% | −2.72 |

**Holm p = 1.000 for all ten; none holds.** Every one fell to within 1 point of its 2026 random rate, or below it. This is the pattern of selection noise, not of an edge that decays.

## Checks

- **The null check came first.** Before the real run, the same code on a path-consistent synthetic random walk flagged 0 of 320 configurations.
- **Causality** is tested by recomputing every event on truncated data (`tests/test_research_b28.py`):
  - opening ranges use only bars inside their window;
  - Supertrend's final bands use only earlier bars;
  - the order block and the sweep are looked up before the displacement bar.
- **Every configuration is logged.** All 320 configurations and the 10 frozen 2026 checks are in `research/trials.jsonl`.
- **Break-even comparator (audit, after the run).** The `break_even` field in the summary is the break-even of the TP share of *all* trades. Compared with the decided rate, it understates the break-even by 5.5–6.8 points for the New York candidates, whose closures run 10–12%.
  - The consistent field `break_even_decided` was added to the code afterwards; see `PHASE_C_REPORT.md` §6.
  - No verdict depends on it.
