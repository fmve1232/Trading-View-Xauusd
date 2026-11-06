# Phase B13: the operator's target, +$10 to +$20 (ideal +$15) before a −$13 stop (2026-11-05)

**Verdict.**

- **Every primary FAILS.**
- **Development, Holm over four:**
  - the overnight BUY (B13-2a);
  - the day SELL (B13-2b);
  - intraday momentum (B13-3);
  - a gradient-boosted model (B13-4).
- **Validation, opened once, Holm over two:** the B10 lead, the engine's own 15m signals (B13-1).
- The labeller audit (B13-0) is **CONSISTENT**: random entries match S / (T + S) within 0.5 points.

The rules were registered in `research/registrations/B13.json` and committed before any code or data. The operator
approved on 2026-11-05: "you have full rights to evaluate and audit … If we need any modification and improvement,
that is approved from my side."

| Item | Location |
|---|---|
| Code | `quantum/research/b13.py`; `research/tools/b13_prop_pass.py` (arithmetic only) |
| Results | `research/results/b13_development_2026-11-05.json`, `b13_validation_2026-11-05.json`, `b13_live_geometry_2026-11-05.json`, `b13_prop_pass_2026-11-05.json` |
| Trial records | 24 in `research/trials.jsonl` (phase `B13`) |
| Order of work | Development results were committed (33dba7080) before the validation partition was read |

**Settings.**

- Outcome: +T before −13, in dollars at $4,000, scaled by entry / 4000, on 15-minute bars of the same partition.
- Tie rule: a bar reaching both levels is a loss unless it opened beyond the target.
- Net results are in dollars at $4,000 per ounce. Two costs are used:
  - the frozen model's cost: $0.77 in session, $0.97 off session;
  - the operator's measured $0.26 round trip.

## 1. The geometry check (B13-0)

For a price with no predictable drift, the chance of reaching +T before −S is **S / (T + S)**. That holds whatever
indicator, timeframe, level or volume picked the entry (optional stopping theorem). So the first question is whether
our labeller reproduces it on random entries. If it didn't, every earlier B-phase number would be suspect.

| +T before −13 | Development 2020–22 (43,000+ random entries) | Live window 9 Sep – 5 Nov 2026 (7,308, real $) | S / (T + S) |
|---|---|---|---|
| +$10 | 56.4% | 56.6% | 56.5% |
| +$13 | 49.8% | — | 50.0% |
| **+$15** | **46.2%** | **46.1%** | **46.4%** |
| +$20 | 39.0% | 39.0% | 39.4% |

- **All 24 development cells** (T 10 / 13 / 15 / 20 × S 10 / 13 / 15 / 20 / 26 / 30) lie within 0.5 points of theory.
  The exceptions are the S = 30 cells (+1.1 to +1.7 points): with a wide stop more trades stay open, and those that
  resolve lean toward the nearer level.
- **The live window agrees within 0.8 points on average.** But longs reached +$15 first only 40.2% of the time and
  shorts 52.0%: gold fell for eight weeks. That drift was the only thing that mattered, and no rule tested here knew
  it in advance.
- **Ties** (a bar touching both levels) are 0.2–0.4% of entries on 15m and about 1% on the live 5m path. That is
  small, so the conservative tie rule does not distort results.
- **Median time to resolution** of +$15 / −$13 on the live window: 115 minutes overall; 90 in London, 175 in New
  York, 115 in Asia and off-hours.

## 2. Development (2020-04 → 2023-01)

| Primary (+15 / −13) | n | Target first | 95% range | Random | z | Net / oz at $4,000 (t) | Operator's cost (t) | Verdict |
|---|---|---|---|---|---|---|---|---|
| B13-2a overnight BUY 13:30 → 08:30 NY | 641 | 48.0% | 44.2–51.9% | 44.9% (time-matched) | +1.58 | −$0.32 (−0.57) | +$0.19 (+0.35) | **FAIL** |
| B13-2b day SELL 08:30 → 13:30 NY | 618 | 47.7% | 43.8–51.7% | 46.1% | +0.80 | −$0.40 (−0.72) | +$0.11 (+0.19) | **FAIL** |
| B13-3 intraday momentum 09:00 → 13:30 NY | 599 | 45.7% | 41.8–49.7% | 46.0% | −0.13 | −$0.96 (−1.69) | −$0.45 (−0.79) | **FAIL** |
| B13-4 gradient-boosted model, top decile | 1,377 | 47.3% | 44.7–49.9% | 46.2% | +0.78 | −$0.60 (−1.59) | −$0.02 (−0.06) | **FAIL** |

**The literature effects.**

- The overnight drift in gold (Blose et al. 2018) points the right way in 2020–22: +2.8 basis points a night, t = 1.07,
  and 48.0% against a time-matched 44.9%.
- It is not significant. Even if real, it is worth about one dollar per trade before costs.
- The intraday momentum of Gao et al. (2018) is absent in gold (+0.5 bp, t = 0.25).

**The model** used 31 features, including every input of the operator's B12 criteria: distance to the day / week /
month highs and lows, the three trend votes, bar shape, session, ATR and range used today.

| Measure | Result | Reading |
|---|---|---|
| Out-of-fold AUC | 0.506 long, 0.510 short (folds 0.49–0.55) | 0.50 is a coin |
| Brier score | 0.265 against 0.249 for the base rate | Its probabilities are **worse than always saying 46%** |
| Logistic regression (secondary) | AUC 0.49 | Below random |
| Top-decile trades | 47.3% against 46.2% random | Below break-even |

The inputs a discretionary trader reads carry no usable information about the next +$15 / −$13 on 15-minute bars.

## 3. Validation (2023-01-24 → 2024-07-01, opened once)

| B13-1: the engine's own 15m signals | n | Target first | 95% range | Random | z | p (one-sided) | Net / oz at $4,000 (t) | Verdict |
|---|---|---|---|---|---|---|---|---|
| +13 / −13 | 44 | 61.4% | 46.6–74.3% | 50.8% | +1.40 | 0.081 | +$2.18 (+1.13) | **FAIL** |
| +15 / −13 | 44 | 61.4% | 46.6–74.3% | 47.6% | +1.83 | 0.033 | +$3.41 (+1.64) | **FAIL** (Holm needs 0.025; t < 1.645) |
| +10 / −13 (secondary) | 44 | 61.4% | | 56.9% | +0.59 | | +$0.34 | — |
| +20 / −13 (secondary) | 44 | 56.8% | | 40.3% | +2.24 | | +$4.98 (+2.00) | — |

**The lead stayed above random on unseen data, but not by enough to pass its pre-registered test.**

- Development: 64.3% of 70. Validation: 61.4% of 44.
- 39 of the 44 trades were BUYs in the 2023–24 rally. Random longs won 47.9% there, so the signals beat random BUYs by
  about 13 points.
- The registered power was 40–50% for a true 64%. This test could not separate "a real edge of that size" from luck.
- Two facts argue against it:
  - On the live window, the live engine's 15m signals did 31.8% (22 trades; B9-explore).
  - The site's alert plans on 15m have 3 SL of 3 so far.
- **By the registration, the lead earns no forward test from B13** and no change to anything. The live engine's
  signals keep being measured anyway: every alerted 15m signal's ±$13 plan result is on the site's validation card,
  and the frozen forward test continues.

## 4. What the geometry means for a prop account (arithmetic, `b13_prop_pass_2026-11-05.json`)

- **Rules:** two-step challenge on $25,000 (8% then 5%; daily loss 5% of the start-of-day balance; static 10% maximum
  loss).
- **Trading:** at most two trades a day; a trade is skipped when its loss would break the daily limit; $0.26 round
  trip.
- 40,000 simulated challenges per row. No edge means p = S / (T + S).

| Geometry | $ win / loss | Target first | EV per trade | Pass phase 1 | Pass both | Median days, phase 1 |
|---|---|---|---|---|---|---|
| 0.50 lot, SL $13, TP $13 | +637 / −663 | 50.0% | −$13 | 49.4% | 30.0% | 7 |
| 0.50 lot, SL $13, **TP $15** | +737 / −663 | 46.4% | −$13 | 50.3% | 30.7% | 6 |
| 0.50 lot, SL $13, TP $10 | +487 / −663 | 56.5% | −$13 | 50.4% | 31.1% | 8 |
| 0.50 lot, SL $13, TP $20 | +987 / −663 | 39.4% | −$13 | 49.3% | 30.5% | 5 |
| 0.43 lot, SL $15, TP $15 | +634 / −656 | 50.0% | −$11 | 49.6% | 30.2% | 7 |
| 0.25 lot, SL $26, TP $15 | +369 / −657 | 63.4% | −$7 | 52.6% | 33.5% | 10 |
| 0.22 lot, SL $30, TP $15 | +324 / −666 | 66.7% | −$6 | 52.6% | 34.2% | 12 |

- **The hit rate can be set anywhere from 39% to 67% by moving the stop. The chance of passing barely moves (30–34%),
  because the expected value of every row is the cost.**
- A wider stop at a smaller lot is slightly better only because the dollar cost per trade is smaller.
- With a genuine 3-point edge, every geometry would pass both phases 41–53% of the time. The edge, not the geometry,
  is what changes the outcome.
- **Daily-limit fact at 0.5 lot and a $13 stop:**
  - Two stops in one day = −$1,326 = 5.3% of $25,000, over a 5% daily limit. Only one loss a day fits.
  - At 0.45 lot two stops are −$1,193 (4.8%), with almost no slippage buffer.
  - At **0.40 lot** two stops are −$1,061 (4.2%), with about $190 to spare.

## 5. What changed because of this audit (display only; freeze keys unchanged)

- **Alert plans are now resolved on the 5-minute path** (`notify.plan_path5`), with the trade_race tie rule, when the
  same feed's 5m bars cover the signal's close.
  - Before, a 1h or 4h plan was judged on its own bars. A whole 4h bar spanning both $13 levels counted as a loss, and
    the TP / SL alert came only when that bar closed.
  - Re-resolving the 10 closed plans on 5m bars gives the same results, but the two 4h alerts had arrived 40 and
    120 minutes after the level was hit.
- **Every signal alert carries a LADDER line:**
  - the driftless odds of +$10 / +$13 / +$15 / +$20 before the plan's stop, and their value at the plan's lot;
  - whether two stops in a day fit the daily limit (ACCOUNT_USD, DAILY_LIMIT_PCT).
- **B10 erratum:** see `B10_DEVELOPMENT_RESULTS.md`.

## Erratum (2026-11-07, B19)

- **What was counted:** B13-1 (61.4% of 44 on validation) counted every engine SIGNAL, as B10 did.
- **One per idea:** under the live REPEAT rule, the 2023–24 engine signals (15m–4h pooled) are 24 ideas, 45.8% of 24 at ±$13 (B19's exit rule).
- **Development:** the 15m lead (64.3% of 70) is 52.2% of 23.
- **Source:** `research/B19_RESULTS.md` section 5. The numbers above are left as they were.
