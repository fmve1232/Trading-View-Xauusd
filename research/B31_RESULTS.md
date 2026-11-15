# B31: liquidity-aware opportunity selection — results

The study ran in a fixed order:
1. Registration `research/registrations/B31.json` and design `research/B31_PLAN.md`, committed `179814194` and pushed before any code.
2. Code, committed `daf26e730`: 13 tests, 15 of 15 mutants killed. The code ran once, on all four periods.

Records:
- Results: `research/results/b31_all_partitions_2026-11-15.json`.
- Trials: appended to `research/trials.jsonl`.
- Code under test: production `51f9142d8`, freeze key `5e4630924d663fc5:a6f2be58c74887ed`, unchanged.
- F-ENG arm: the F1–F4 branch `4232dea8e`.

## 1. Answer

**No module is supported. B31 cannot recommend any of A–E, or their combination, for live use.**

| Unit | Out-of-sample trades (2023–25) | TP1 first | Matched random TP1 first | Net R per trade (bootstrap 95%) | Holm p | Development net R | Verdict |
|---|---|---|---|---|---|---|---|
| A sweep reversal | 0 | — | — | — | — | (0 trades) | INSUFFICIENT |
| B continuation after a grab | 0 | — | — | — | — | +1.03 (1 trade) | INSUFFICIENT |
| C breakout and retest | 24 | 41.7% | 39.8% | −0.05 (−0.53 to +0.40) | 1.00 | −0.20 | INSUFFICIENT (< 30) |
| D VWAP mean reversion | 23 | 47.8% | 39.8% | +0.07 (−0.36 to +0.52) | 1.00 | −0.02 | INSUFFICIENT (< 30) |
| E session expansion | 3 | 33% | 45% | −0.22 | 1.00 | −0.39 | INSUFFICIENT |
| COMBINED (A–E, one position at a time) | 48 | 43.8% | 41.0% | −0.01 (−0.32 to +0.31) | 1.00 | −0.07 | **NOT SUPPORTED** |
| COMBINED, score ≥ 75 | 4 | 50% | 36% | +0.14 | 1.00 | −0.01 | INSUFFICIENT |

Where trades exist (C, D, COMBINED):
- TP1-first rates sit 2–8 points above the matched random control.
- Net R is close to zero. It improves on random entries by about the cost and no more.
- Every interval is wide and includes zero.

## 2. Why so few trades: the two findings that matter most

### 2.1 The eligibility rules leave a $5–8.4 stop window

A +$10 first target with **net reward / risk ≥ 1.0** after costs of about $0.8 / oz requires a structural stop of at most about $8.4. B19's floor is $5. Most structural stops fall outside that window.

Rejection reasons, development 2020–22:

| Module | Setups | Stop below $5 | Net R:R < 1 (stop above ~$8.4) | Room to TP1 | Cost | Executed |
|---|---|---|---|---|---|---|
| C | 1,542 (589 repeats) | 499 | 214 | 125 | 55 | 23 |
| D | 2,003 (664 repeats) | 922 | 123 | 178 | 80 | 36 |
| E | 174 | 71 | 40 | 47 | 5 | 4 |
| Production engine | 64 | — | 64 | — | — | **0** |
| F1–F4 engine | 289 | 13 | 223 | 38 | 3 | 12 |

- **For A / B setups,** the stop distance is a median **$8.72**; the middle half runs **$5.41–16.43**. Only **22%** fall inside $5–8.4.
- **The production engine's own stops are wider than $8.4 every time.** None of its signals can meet the eligibility rule with a $10 first target.
- **Same pattern in every period.** Validation, holdout and 2026 behave alike (results file).

**This is the arithmetic of the objective, not a filter that can be loosened without evidence.** A $10 target can only be favourable against a structural stop if that stop is tighter than about $8.4. On 15m gold, most structural invalidation points are further away than that.

### 2.2 The engine's BOS needs volume, and the 2020–25 history has none (a flaw in B31's design)

Found after the run, from the development funnel (`research/tools/b31_funnel.py`):
- **Rejected sweeps:** 4,334.
- **With a trade-direction structure event within 8 bars:** 117.
- **Setups:** 21 for A and 6 for B, all with an FVG entry.

The engine's structure events fire only once every 87 bars, and **every one of them is an MSS / CHoCH: no BOS at all**. The reason is in the code:
- The engine's BOS rule needs a high-volume candle: volume > 1.2 × its 20-bar average (`engine.py:356-370`).
- Its displacement rule needs volume too.
- The research history has no volume, so neither can fire.

Consequences:
- **Modules A and B, the operator's priority strategies, were not effectively tested.** B lost its main signal (BOS continuation), and A had almost no confirmations to work with.
- **I should have checked that the registered detectors fire on volume-free data before registering.** That is my error.
- **The rules cannot be changed and re-run under B31.** All four periods have now been read, so that would be tuning after the fact.

## 3. The measurements the operator asked for (where trades exist)

Primary plan: TP1 +$10 or the structural stop; model cost; $ at $650 risk per trade.

| Unit, period | Trades | TP1 / TP2 / TP3 first | SL first | Same-bar ambiguous | Net R | Profit factor | Max drawdown | MFE / MAE ($) | Median time to TP1 | Median stop | Break-even TP1 rate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C, development | 23 | 35 / 35 / 30% | 65% | 0% | −0.20 | 0.67 | $3,645 | 6.7 / 6.6 | 53 min | $6.2 | 44% |
| C, holdout | 17 | 41 / 29 / 24% | 59% | 0% | −0.07 | 0.84 | $2,600 | 7.6 / 6.0 | 45 min | $6.6 | 45% |
| C, 2026 | 19 | 42 / 26 / 21% | 58% | 0% | −0.02 | 0.86 | $2,344 | 7.2 / 5.3 | 23 min | $6.8 | 45% |
| D, development | 36 | 44 / 36 / 31% | 56% | 0% | −0.02 | 0.99 | $6,245 | 7.6 / 6.7 | 75 min | $6.2 | 44% |
| D, holdout | 21 | 43 / 29 / 19% | 52% | 5% | −0.03 | 0.89 | $3,091 | 8.5 / 8.1 | 30 min | $6.7 | 45% |
| D, 2026 | 21 | 43 / 24 / 19% | 57% | 0% | −0.07 | 0.90 | $2,315 | 7.3 / 6.7 | 30 min | $6.9 | 46% |
| COMBINED, development | 60 | 42 / 37 / 32% | 58% | 0% | −0.07 | 0.89 | $7,239 | 7.4 / 6.6 | 75 min | $6.3 | 44% |
| COMBINED, holdout | 39 | 41 / 28 / 21% | 56% | 3% | −0.07 | 0.83 | $4,661 | 7.9 / 7.3 | 45 min | $6.7 | 45% |
| COMBINED, 2026 | 40 | 42 / 25 / 20% | 57% | 0% | −0.05 | 0.88 | $3,482 | 7.2 / 6.0 | 30 min | $6.8 | 45% |
| Matched random, COMBINED holdout | 780 | 42% | — | — | −0.08 | — | — | — | — | same stops | — |

Notes:
- No trade hit the 24-hour time stop.
- Missed limit orders (not filled within 8 bars), development: C 37, E 7.
- **False breakouts:** none were counted, by construction. A limit at the level fills on any touch, so only a bar opening back through the level could count, and none did (registration wording noted in §6).
- **The three-part plan** (thirds at +$10 / +$15 / +$20, stop to entry after TP1) does not change the picture: COMBINED net R −0.03 / −0.07 / −0.10 (development / holdout / 2026).
- **Operator cost** ($0.26 / oz): the lower cost lets more setups pass the reward and cost checks (COMBINED development 60 → 93 trades), so the trade set changes as well as the results. COMBINED net R: +0.03 development, −0.20 validation (15 trades), −0.00 holdout (49), +0.11 in 2026; −0.05 out of sample over 64 trades. The verdicts are unchanged.
- **The engine arms are too small to compare:**
  - production engine: 3 trades out of sample;
  - F1–F4 engine: 11 trades out of sample (validation 4, holdout 7), TP1 first 6 of 11 against 39–41% random, net R +0.55 and −0.07 by period.

## 4. The operator's 100-point score and probability estimates

All modules were pooled: 64 development trades, 50 out of sample.

| Target | AUC, development | AUC, out of sample (95%) | Brier, out of sample | Brier, constant base rate |
|---|---|---|---|---|
| TP1 +$10 before SL | 0.48 | 0.47 (0.31–0.64) | 0.244 | 0.248 |
| TP2 +$15 before SL | 0.49 | 0.45 (0.28–0.62) | 0.223 | 0.225 |
| TP3 +$20 before SL | 0.46 | 0.51 (0.32–0.71) | 0.204 | 0.202 |

TP1 first by score class, out of sample:

| Class | Trades | TP1 first |
|---|---|---|
| High (85+) | 0 | — |
| Qualified (75–84) | 4 | 50% |
| Watchlist (65–74) | 9 | 56% |
| Reject (< 65) | 37 | 41% |

**The score does not rank outcomes.** Its AUC sits at 0.5 within noise, and the calibrated probabilities are no better than a constant base rate. As the operator required, it must not be shown as a probability, and the provisional classes have no evidential basis yet.

The volume, news and cross-market parts were held constant because those data are not available (registration). Volatility, structure, liquidity, entry type and target space alone carry no information here.

## 5. What this means and what is recommended

1. **No production change** follows from B31.
2. **A decision only the operator can make: the eligibility policy.**
   - With TP1 at +$10 and net R:R ≥ 1 on TP1, only stops of $5–8.4 qualify. Few setups have them, and those did not beat random.
   - Each alternative changes the objective and needs its own registration. None may be chosen by looking at these results:
     - (a) measure R:R on the target ladder rather than on TP1 alone;
     - (b) set TP1 at the next opposing liquidity pool, never less than $10;
     - (c) accept R:R < 1 where a measured hit rate justifies it.
3. **A fair test of A and B (proposed B31b)** needs either:
   - a declared volume-free structure rule (for example the engine's own pivot-break rule without its volume clause); or
   - historical volume. Options: Dukascopy tick volume (the B5c path on the operator's laptop) or CME GC 1-minute bars (paid).

   B31 produced no A / B trades, so it revealed nothing about their outcomes. A B31b registration would still have to disclose that B2 / B16 / B21 read the same periods.
4. **The decisive test is prospective.** No historical period is untouched. Production now has futures volume, the news calendar and cross-market data.
   - The right next step is a **forward shadow tracker for modules A–E**: a separately registered record with no alerts, using live data, decided only by future results.
5. **The news calendar** needs verified 2023–26 release dates (BLS / BEA / Federal Reserve schedules) before the news layer can be tested out of sample.

## 6. Limitations and errors

- **Design error (§2.2).** The registration relied on the engine's structure events, which need volume. Detectors should have been verified on volume-free data before registering.
- **Small samples.** Most cells have fewer than 30 trades. "INSUFFICIENT" means the question is open, not that the strategy loses.
- **Data already seen.** The out-of-sample periods had been read by earlier studies (registration).
- **15m bars.** The order inside a bar is unknown. A fill bar can only stop, and same-bar stop-and-target bars count as stops; both choices are conservative.
- **Costs** are the engine's model and are not broker-verified (audit D1).
- **Registration wording.** C's "close back through the level before the fill" cannot happen with a limit at the level, because the touch fills first. Only bars opening back through the level could count, and there were none.
