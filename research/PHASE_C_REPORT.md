# Phase C: dual-track strategy discovery — the report (2026-11-09)

**Branch:** `claude/research-phase-c`, cut from `claude/research-sym15` (B26 / B27). Research only.

**Untouched:**
- web.8;
- the production engine and `quantum/config.py`;
- the frozen Pine reference files;
- the alerts;
- PRs #90 and #91;
- the validation (2023-01 → 2024-07) and holdout (2024-07 → 2026-01) partitions, which stay sealed.

**No Pine code was written.**

| Deliverable | Where |
|---|---|
| 1. Research architecture and registration | §1; `PHASE_C_PLAN.md`; `registrations/B28.json`, `registrations/B29.json` |
| 2. Feature and indicator audit | §2; `FEATURE_AUDIT.md` |
| 3. Track A results (±$15) | §3; `B28_RESULTS.md` (new families); `B27_RESULTS.md` (the 13 earlier families) |
| 4. Track B results (dynamic TP / SL) | §4; `B29_RESULTS.md` |
| 5. Machine-learning evaluation | §5 |
| 6. Statistical validation | §6 |
| 7. Leaderboards A / B / C, BUY / SELL, named bests | §7; appendix |
| 8. Trade-level CSVs | §8 |
| 9. Failure analysis | §9 |
| 10. Recommended architecture | §10 |
| 11. Risk management and position sizing | §11 |
| 12. Final recommendation | §12 |

## The answer in one paragraph

**Nothing deserves validation.** Across both tracks, 1,954 configurations were selected on 2020–22 development data and then checked:
- B27: 1,192 at ±$15;
- B28: 320 at ±$15;
- B29: 442 dynamic, plus a 202-row descriptive grid.

**No configuration beats its matched random rate after the multiple-testing correction, and none of the 60 frozen candidates holds on 2026.**

**Changing TP and SL moves the hit rate exactly along the no-information line p₀ = (SL − Δ) / (TP + SL), and the break-even moves with it.** So every pair loses $0.14–$1.32 per oz after costs.

**A 90% hit rate exists only as geometry:**
- +$3 / −$30 wins 89.5% and needs 91.2%;
- a 90% target needs a stop of at least 9 × TP + $5, and loses money without information.

**The only measurable information in the features is the calendar.** Late-week entries end at the weekend close; that is not direction.

The recommended output stays **NO TRADE / WAIT, with the base rate shown.**

## 1. Research architecture and registration

```
data      Twelve Data 15m / 1h, 2020-01-24 .. 2023-01-24 (development, scored from 2020-04-01); 2026-01-01 .. (check, scored
          from 2026-03-01); the live store's 5m bars (Sep-Nov 2026, resolution check); 60m intermarket (2026, descriptive)
          SEALED: validation 2023-01 .. 2024-07, holdout 2024-07 .. 2026-01
trade     decision at a 15m close, fill at the next open (BUY at the ask, SELL at the bid, + entry slippage), TP / SL from the
          ACTUAL fill, levels trigger on the exit side, gap / same-bar / 2-day / closure rules (B26), k = price / 4000 in
          development, 1 in 2026; costs GROSS / OP ($0.26) / ENG (engine model, primary) / ADV
features  B22 engine features + B27 additions + B28 events, all from closed bars (FEATURE_AUDIT.md)
Track A   B27: 13 families x 23 entry modes; S1 conditions; S3 models; S5 regimes           (+-$15)
          B28: 8 new families x 20 entry modes ($0, confirm / retest / stop at $3-$20, structure limit)
Track B   B29: G grid (101 pairs), V ATR brackets (25), M time-series momentum (14), C model per bracket (7 x 6 q x 2),
          E 21 families x 7 brackets
selection development only; matched random (same bracket, direction, session, month; M direction-neutral); BH within
          each study; tiers INFORMATIVE (BH, lower bound > random, n >= 300) and TRADEABLE (also > break-even, exp > 0)
check     frozen per study (informative, top 5 with n >= 300, top 5 with 30-299), then 2026 with Holm across the frozen set;
          nothing is selected on 2026
log       research/trials.jsonl, append-only (every configuration, every 2026 check)
```

**Registration timeline (commit hashes):**

| Step | Commit | What |
|---|---|---|
| Plan and registrations, before any code | `ffc0b6857` | `PHASE_C_PLAN.md`, `B28.json`, `B29.json` |
| Code, tests, null check, before any real result | `9a86c684c` | `b28.py`, `b29.py`, tests, `phasec_null_check.py`; B29 amendments 1–3 (study V's test) |
| Feature audit | `3a8728429` | `FEATURE_AUDIT.md`, generated from B27's measured values |
| Results as run, diagnostics, two fixes | `627b2d2a3` | `results/b28`, `results/b29`, `results/phasec`; `break_even_decided`; top-q selection on the raw score |
| Corrected model re-runs and this report | this commit | `results/b27_fix`, `results/b29_fix`; `B28_RESULTS.md`, `B29_RESULTS.md`, `PHASE_C_REPORT.md` |

**The null check ran first.** The full framework was run on a path-consistent synthetic random walk before any real result. It found three biases in study V's registered test, all fixed by amendment before the real run, and in the final version it flags 0 of 762 configurations.

## 2. Feature and indicator audit (`FEATURE_AUDIT.md`)

**What the audit lists.** Each of the 69 model features, with:
- its formula;
- when it is available (the decision bar's close);
- its data caveat;
- its measured value: univariate AUC, permutation drop and family ablation.

**What it found:**
- **Only weekday and hour carry information.** Removing the time family is the only removal that hurts (−0.016 AUC), and §5 shows that information is about closures.
- **Everything else adds nothing.** Every structure, liquidity, SMC, trend, oscillator, volatility and Markov feature has a permutation drop of at most about 0.002, and removing whole families improves the out-of-sample AUC.
- **No indicator is carried into a strategy specification.**

**Microstructure: not tested, and never substituted.** True VWAP, volume profile, relative volume, bid / ask spread, tick velocity / acceleration, aggressor proxies, intrabar sequence and order-book depth all need traded volume, quotes or ticks, which this feed does not have. They are not derived from OHLC.
- **Spreads are modelled,** not measured.
- **COMEX trade flow was tested in B5,** with no edge.
- **Dukascopy tick data (B5c)** is the pending free route.

## 3. Track A: fixed +$15 / −$15 (B27 and B28)

| Study | Configurations | BH | INFORMATIVE | Frozen | Hold on 2026 |
|---|---|---|---|---|---|
| B27 (13 families, conditions, models, regimes) | 1,192 | 0 | 0 | 20 | 0 |
| B28 (8 new families) | 320 | 0 | 0 | 10 | 0 |

**Confirmation distance** ($0, 3, 5, 7, 8, 10, 12, 15, 20, by close, retest, stop or structure limit; 21 families) **never raises the hit rate.**
- No mode is more than 0.4 points above random. Every mode is within 2.4 points below it, except stop entries of $10 or more.
- Those stop entries' deficit (−8 to −9.5 points at $15–$20) is a worst-case resolution artefact. Their best case is at random: `B28_RESULTS.md`, "Resolution of order entries".
- Waiting skips trades, so it lowers the loss per signal, not the loss per trade taken.

**The new families (opening-range breakouts, reversal candles at levels, CHoCH retest, order-block retest, sweep then displacement, Supertrend) behave like the old ones:**
- within a few points of random on development;
- the frozen best fell to or below random on 2026.

The best is NY_ORB IMM BUY: 53.8% on 266 trades → 40.0% on 70.

## 4. Track B: dynamic TP / SL (B29)

| Study | Configurations | BH | INFORMATIVE | Frozen | Hold on 2026 |
|---|---|---|---|---|---|
| G grid (101 pairs × 2, descriptive) | 202 | — | — | 5 | 0 |
| V ATR-scaled brackets | 50 | 0 | 0 | 5 | 0 |
| M time-series momentum | 14 | 0 | 0 | 5 | 0 |
| C model per bracket (corrected re-run, §5) | 84 | see §5 | see §5 | 5 | see §5 |
| E families per bracket | 294 | 0 | 0 | 10 | 0 |

- **The grid is the no-information arithmetic, measured.** 96.5% of rows are within 2 points of p₀, none is significantly above it, and 0 of 202 make money under ENG.
- **The least-bad rows are BUYs on large brackets.** That is the period's drift, not a signal: the mirror SELLs lose most, and the frozen BUYs lost $2.0–2.4 per oz on 2026.
- **The per-pair detail:** TP-first, SL-first, R:R, expectancy, PF, drawdown and its Monte Carlo 95th percentile, losing runs, minutes to TP / SL, trades per week, monthly results, 95% intervals and regime stability.
  - Monthly results and regime stability are in `b29_grid_extra.csv.gz`; everything else is in `b29_grid.csv`.
  - No pair is profitable in half its months (best 47.1%).

**Resolution.** The 15m bounds for small brackets are wide: +$3 / −$3 is 37.2–46.3% at 15m and 37.5–41.7% at 5m. From +$5 / −$10 up, 15m and 5m agree to within a point. No bound of any pair reaches its break-even.

## 5. Machine-learning evaluation (B27 S3 and B29 C)

**Models.** Logistic regression, histogram gradient boosting, LightGBM, separate BUY / SELL LightGBMs, and an ensemble (B27). LightGBM per bracket (B29).
- **Calibration:** isotonic, on the last 20% of each training window.
- **Walk-forward:** quarterly and purged, from 2021-01 to 2023-01, with a 1-day embargo.

**Outputs.**
- **The registered models are binary** (P(TP first)).
- **The three-way split comes from the outcome table below.** It shows that P(TP first | decided) is the no-information rate on every weekday, and that only P(neither) moves.

<!-- C_SECTION -->

**Baselines.** Each selection is compared with:
- the matched random rate (same direction, session and month);
- the plain all-bar BUY and SELL rates (`b29_grid.csv`);
- the same-direction and direction-neutral rates (M);
- the model's own constant forecast (Brier).

**Multiple testing:** BH within each study, Holm across each study's frozen set on 2026.

## 6. Statistical validation

| Check | What it guards against | Result |
|---|---|---|
| Independent series (next entry after the previous exit) | overlapping trades inflating n | all statistics |
| Wilson 95% intervals; day-clustered bootstrap for all-bar figures | false precision | all tables |
| Matched random (direction × session × month) | drift and session effects posing as skill | primary baseline |
| Direction-neutral random (M) | a same-month baseline absorbing the drift being predicted | registered in advance |
| BH within each study; Holm on 2026 | multiple testing | 0 BH-significant anywhere |
| Null check on a path-consistent random walk | a framework that manufactures winners | 0 of 762 flagged; real results no better than the walk's (appendix) |
| Worst / best resolution bounds; 5m check | 15m bars hiding the order of extremes | grid: 12 small-bracket rows INCONCLUSIVE; order entries: STOP_10 to STOP_20 INCONCLUSIVE, best case still at random |
| Four cost scenarios | cost assumptions deciding the sign | 0 of 202 rows positive under ENG or ADV; GROSS / OP positives explained by stop overshoot and drift (`B29_RESULTS.md`) |
| B29 ±$15 row = B26 exactly; engine = plain race on five pairs | engine bugs | identical |

**Audit findings after the run, disclosed and fixed:**

1. **Break-even comparator.**
   - **The defect.** The registered tables' `break_even` is the break-even of the TP share of *all* trades. Beside the decided rate it understates the comparator by up to 9.8 points when closures are common; at ±$15, by 0–7 points.
   - **The fix.** `break_even_decided`, the decided rate at which the series' expectancy is zero, was added with a test, and the tier rules use it.
   - **Impact on the frozen sets.** Under the old field, 24 of 120 frozen-candidate rows (development and 2026) had a lower bound "above break-even". Under the consistent one, 2 do, both development rows with fewer than 300 trades. The only 2026 row (TSMOM60 +$30 / −$30) drops out.
   - **No verdict changes,** because nothing was INFORMATIVE. `results/phasec/breakeven_audit.md` lists every row.
2. **"Top q" model selections were not q.** The training-window threshold was a quantile of isotonic-calibrated probabilities, a step function, so a nominal top 1% admitted 21–66% of test rows. B27 S3 and B29 C therefore never tested their registered small tails. The fix ranks on the raw score (the same order, with no ties); both studies were re-run (§5).
3. **Order-entry resolution.** Fills inside a bar are worst case at 15m (above). It cannot create a false winner. The best case shows it hid none.

## 7. Leaderboards

**The full tables are in the appendix, generated from the summaries:**
- A (±$15);
- B (dynamic);
- C (best risk-adjusted across both tracks);
- BUY;
- SELL;
- the named bests.

**None is a validated strategy.**

<!-- BOARDS_SECTION -->

## 8. Trade-level CSVs

| File | Rows | What |
|---|---|---|
| `results/b26/b26_trades_P1/P2/P3.csv.gz` | every eligible bar | B26's ±$15 baseline, all cost scenarios |
| `results/b27/b27_frozen_trades.csv.gz` | 15,856 | B27's 20 frozen candidates (as run), development, 2026 and 2026 on 5m |
| `results/b28/b28_frozen_trades.csv.gz` | 3,830 | B28's 10 frozen candidates, development and 2026 |
| `results/b29/b29_frozen_trades.csv.gz` | 172,630 | B29's 30 frozen candidates (as run), development and 2026 |
| `results/b27_fix/`, `results/b29_fix/` | see the folders | the corrected re-runs' frozen trades |
| `results/b28/b28_configs.csv.gz`, `results/b29/b29_*.csv.gz`, `results/b29/b29_grid.csv` | one row per configuration | every configuration's statistics |

**Columns:** candidate, period, fill / exit time (UTC epoch), outcome (TP / SL / AMBIGUOUS / TIMEOUT / CLOSURE), net $ per oz (4,000-equivalent in development), cost, minutes, session, direction, and net $ at 0.50 lot (ASSUMED 100 oz).

## 9. Failure analysis: why nothing works

1. **The arithmetic.**
   - Without directional information, TP-first = (SL − Δ) / (TP + SL), and the break-even is always higher.
   - The grid measures exactly that on 202 rows. A rule must move the rate above the break-even, and none moves it at all.
2. **Costs set the sign; the pair sets the size.** Every pair loses about the cost of a round trip: a median $0.79 per oz, range $0.14–$1.32. Small brackets lose a third of their risk per trade, large ones under 1%.
3. **Development winners are selection noise.**
   - Every frozen candidate regressed to its random rate or below on 2026.
   - The real results' best lift, smallest p and count of positive-expectancy configurations match the random walk's.
4. **Drift masquerades as an edge.**
   - Gold rose over 2020–22, so large-bracket BUYs are the least-bad rows and many BUY trigger families look positive at large brackets.
   - Pooled with SELL, or checked on 2026, they lose.
   - Time-series momentum, the registered test of whether drift is predictable, picked the month's direction more often than not, but its trades still realised the neutral rate.
5. **The calendar masquerades as model skill.** Models "learn" that Friday entries end at the weekend close, which gives AUCs up to 0.53 on any bracket, a random walk included. On decided trades their AUC is 0.50.
6. **Resolution hides, it does not create.** The worst-case 15m rules make small brackets and large stop entries look worse than they are. The best case shows no edge either.
7. **What the data cannot test.** Order flow, true volume, quotes and ticks, and multi-year 5m / 1m bars are all missing (§2, §12). These are the remaining places an edge could exist; none can be claimed or excluded here.

## 10. Recommended architecture (on this evidence)

```
                      +--------------------------------------------+
 closed 15m bar  -->  | default: NO TRADE / WAIT                   |
                      | show: p0, break-even, cost, expectancy for |
                      | the operator's TP / SL (no-information)    |
                      +--------------------------------------------+
                                       |
          a signal is shown as tradeable ONLY if it has passed, in order:
          registration -> null check -> development (BH, lower bound > matched random, n >= 300)
          -> frozen 2026 check (Holm) -> sealed validation (operator approval) -> forward shadow record
```

**How the site should present it:**
- **Keep the site's NO TRADE verdict and base-rate display** (the PR #90 confirmation panel is display only). Present every setup with its measured rate beside the random and break-even rates, never as a probability above them.
- **Rank exits by expectancy per $ of risk, not by hit rate.** A high hit rate is chosen by the stop, not earned.
- **Close or skip late-Friday entries.** That is the one calendar fact the data supports. It reduces the trades that end at the weekend gap; it does not make the rest profitable.
- **Before any new hypothesis,** get the data that can test what OHLC cannot (§12).

## 11. Risk management and position sizing

The table is computed from the measured grid by `research/tools/phasec_risk.py`. Money is at 0.50 lot, ASSUMED to be 100 oz per lot, i.e. $50 per $1 move. The daily limits shown are examples, not your account's rules.

<!-- RISK_TABLE -->

**What the table means:**
- **Kelly says zero.** f* = (p·b − q) / b is negative for every pair: the optimal position without an edge is none, and no sizing rule turns a negative expectancy positive.
- **A high hit rate is fragile.**
  - At +$3 / −$30, one stop ($1,538 at 0.50 lot) erases 12.7 wins.
  - A $1,000 daily limit is breached by a single stop, and a $5,000 limit by four.
- **Losing runs are certain at symmetric brackets.**
  - At ±$10–$15, five losses in a row occur in 86–88% of 100-trade samples.
  - Ten in a row occur in 16–18% of 250-trade samples.

**Sizing rules for any future validated edge:**
1. **Size from the validation lower bound, never from development.**
2. **Risk at most a fraction of the fractional Kelly:** ≤ ¼ Kelly on the lower bound, and ≤ 0.5% of the account per trade.
3. **A daily stop of two losses.**
4. **A halt rule on the forward record:** stop if the cumulative result falls below the registered random-entry band (SPRT or CUSUM).
5. **Confirm the broker's contract size first.** All money here is ASSUMED.

## 12. Final recommendation

**What deserves further validation: nothing.**
- No configuration is TRADEABLE or INFORMATIVE on development.
- None of the frozen candidates holds on 2026.
- Opening the sealed validation period for any of them would spend it on noise. **No approval is requested.**

**What must be rejected:**
- every B28 family and entry mode at ±$15;
- every TP / SL pair as a stand-alone strategy (G);
- ATR-scaled exits (V);
- 20 / 60-day time-series momentum at a 2-day horizon (M);
- the calibrated models per bracket (C, corrected re-run);
- every trigger family per bracket (E);
- the B27 configurations (already rejected).

**The 90% target:** it exists only with a tiny target and a huge stop.
- **The geometry.** p₀ ≥ 90% needs SL ≥ 9 × TP + 10Δ: with Δ = $0.50, +$3 needs a $32 stop and +$5 a $50 stop. The break-even is then about 91.7%.
- **The best measured is just below.** +$3 / −$30 measured 89.2–89.5% (5m: 87.6–88.2% on Sep–Nov 2026) and loses $40 a trade at 0.50 lot.
- **With information instead of geometry,** ±$15 would need a known drift of about $4.9 an hour (B27). No tested input has it.

**Decisions only you can make:**
1. **5m / 1m history.**
   - Either approve a 5m history fetch from Twelve Data (it shares the production API key and its daily credits, so it could starve web.8's live data), or export MT5 M1 history (read-only investor login).
   - This is what turns the small-bracket and stop-entry bounds into measurements.
2. **Broker specification:** contract size (100 oz ASSUMED), commission, and typical spreads by session.
3. **Order flow:** whether to run B5c (Dukascopy ticks, free, on your Windows laptop). It is the only untested data class that could carry direction.
