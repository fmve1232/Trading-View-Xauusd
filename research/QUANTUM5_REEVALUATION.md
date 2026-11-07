# Quantum 5 XAUUSD: complete re-evaluation (operator master instruction, 2026-11-07)

**Scope:**
- Every component of the system.
- Every strategy built so far (B1–B21).
- Three new registered studies for this instruction: B21 (confirmed liquidity / breakout), B22 (calibrated machine
  learning on every confirmation family) and B23 (the one lead B22 produced).

**Method:**
- Each study was registered before its code.
- Each was run once on 2020–22, with independent data opened only for what passed.
- Costs are charged on every trade.
- No result was changed after it was seen.

**Production:** alerts, engine, config and the B15 live test are unchanged. Every study is research code with tests.

## 1. The answer, first

1. **90% is not achievable** for "+$15 (or +$20) before a −$13 stop" in gold with any information this system has.
   - **The arithmetic.** With no directional knowledge, the chance is S / (S + T): 46% at +$15 and 39% at +$20.
     Measured on 130,000 random entries it is 46.2% and 39.0%. Reaching 90% needs a known drift of about **$5.7 an
     hour ($137 a day)** in the trade's direction, at gold's measured 15-minute volatility of $4.07 (B22).
   - **The measurement.** 1,186 recorded tests over 23 studies covered:
     - SMC, liquidity, breakouts, levels, trend, momentum, VWAP / Bollinger / RSI / MACD / ATR;
     - sessions, news, macro, real COMEX order flow and candle runs;
     - two-stage confirmation;
     - seven model families with calibration and HMM regimes.
   - **No component, rule or model** beat a random entry on data it was not built on.
   - The best development result ever recorded (75.8% at the extreme tail of a model) fell to **38.1%** on independent
     data (B23).
2. **The highest reliably achievable rate is the geometric one:** about 46% at +$15 / −$13 and about 39% at +$20 /
   −$13. These are the success rates every method converges to out of sample.
   - The best out-of-sample point estimate was B23's 52.8% (394 rows on 38 days). Its 95% range is 30–76%, which
     cannot be told apart from 46%.
   - **The honest "statistically validated probability" for any qualifying signal today is therefore the base rate,
     with its interval.** Never a higher number.
3. **Waiting for confirmation does not change the next move.** This was tested three ways:
   - a $15 / $20 close beyond a trigger (B19);
   - candle runs (B20);
   - confirmed liquidity sweeps and breakouts (B21).

   Each time, after confirmation the next +$15 before −$13 was 43–50%.
## 2. Audit of every Quantum 5 component (master instruction section 2)

**How to read the table:**

- **Evidence** names the study that measured the component against random entries.
- **"Information?"** asks whether the component changes the odds of +$15 / +$20 before −$13, or only reduces the
  number of signals.

| # | Component | What the code does | Evidence | Information? | Action |
|---|---|---|---|---|---|
| 1 | All strategies | Engine arms (treatment, control, challenger), H2–H6 playbooks, setups, liquidity alerts | Catalogue §3, B1–B22 | None beats random at −$13 | Keep frozen as the forward test; no new money behind any |
| 2 | Entry / exit | Entry at the signal close; −$13 / +$13 / +$20 plan; one plan per idea | B13, B15, B19 | Exit geometry sets the hit rate, not the edge | Kept; B19 tested $10 / $13 / ATR / structure stops |
| 3 | BUY / SELL logic | Treatment gate: trend AND no opposite HTF gate AND recent bar AND session ≥ 30 AND no news / DD block; trigger = active structure break or displacement; vetoes: TQ < 55, EV, calibration | B10, B13-1, erratum | Per idea: 52% of 23 (2020–22), 46% of 24 (2023–24) at ±$13 | No edge; signals are rare and cluster |
| 4 | HTF trend confirmation | 1h / 4h / D gates | B6, B10, B14, B17, B20, B22 | Agreement did not help (B6: 36.5%; B20: 46.2% vs 46.0%) | No measured value |
| 5 | Multi-timeframe alignment | 5m–4h alerts; D context | B6, B12, B14, B17 | None | As 4 |
| 6 | EMA 20 / 100 / 200 | Trend score, distances, slopes | B1, B3, B17, B18, B20, B22 | None | Features in B22 |
| 7 | VWAP, Bollinger | Session VWAP, bands | B19 (STR trigger), B22 | None | Features in B22 |
| 8 | RSI, MACD, ATR, momentum | RSI, ATR in engine; MACD not in engine | B1, B4, B13-3, B19 F1, B20, B22 | Momentum absent at 15m–1h in gold (B13-3, B20) | Features in B22 |
| 9–13 | SMC: BOS / CHoCH / MSS, sweeps, FVG, order blocks | Engine structure, sweeps, FVG, OB | B2, B3, B16, B19, B21 | None (B16: 46.6% / 46.1% vs 46.2%) | No measured value |
| 14–16 | PD / PW / today's highs and lows; S / R | Levels, liquidity pools, value area | B12, B16, B17, B21 | None | No measured value |
| 17 | Volume | Spot has none; the engine uses COMEX GC volume bar for bar; research data 2020–24 has no volume | B5 (real COMEX order flow) | AUC 0.50 | Cannot be validated on spot history; order flow rejected |
| 18 | News filter | Engine news window | B8 | Follow / fade CPI, NFP, FOMC: none | Keep as risk control, not edge |
| 19 | DXY, US10Y, EURUSD, XAGUSD | Engine macro votes (live only) | B7 (daily) | None (Reality Check p 0.999) | Live-only inputs cannot be validated on 2020–24 intraday data |
| 20 | Spread / slippage / commission | Session spread 0.30 / 0.50, 2 × 0.20 slippage, $7 / lot | Harness; operator $0.26 | 6–7.5% of a $13 stop | Model kept conservative; operator line reported |
| 21 | Probability engine | `cal_p_long / short`, analog hit and race probabilities, TQ score, Kelly | CURRENT_STRATEGY_AUDIT §2 | `cal_p`: AUC 0.38–0.52, negative Brier skill; TQ is a score | **Shown as scores, never as probabilities.** Only measured rates are probabilities |
| 22 | Filters that block / delay | Trend, HTF, Recent, Session, News, DD, Trigger, TQ, EV, calibration vetoes | 3-day audit (HTF gate blocked BUYs through a +$249 rally), B10 (releasing it adds 3 signals in 3 years), B14 | They reduce signals; no measured gain | Frozen with the engine; evidence logged |
| 23 | Data freshness, API, candle sync | Twelve Data, 15-minute runs, forming bar excluded, 24/7 quotes removed, as-of HTF | DATA_INTEGRITY_AUDIT; MT5 check 2026-11-06 | Prices match MT5 within $1–3; 10 of 10 outcomes recomputed | OK |
| 24 | Backtest / forward / reporting | Harness labeller (ties = loss, gaps at open), forward ledger, B9 / B15 live tests, weekly validation | B13-0 labeller CONSISTENT; 2026-11-06 recompute | Correct; four reporting bugs found and fixed this week | OK |

## 3. Weaknesses and missed opportunities found

1. **Inflated sample sizes.** The engine's 64% / 61% records counted every repeated signal of one idea. Per idea, they
   are 52% of 23 and 46% of 24 (B19 erratum). The "alerts above 60%" mode rests on that count.
2. **Late signals.** On 3 Nov eight SELLs came within $13 of the low after a $55 fall (MT5 validation 2026-11-06).
   B20 shows this is general: a run already $15–20 old continues less often (44.2%) than a random entry.
3. **The stop sits inside normal noise.** A typical 15m–1h move is $12–15, and costs are 6–7.5% of the stop.
4. **Inputs that cannot be validated.** Intraday macro and volume inputs have no 2020–24 history in the research
   data, so their live contribution cannot be validated historically.
5. **Scores shown like probabilities.** TQ and `cal_p` look like probabilities but are not calibrated.
6. **Reporting bugs fixed this week:**
   - the 4h follow-up label;
   - the weekend expiry of setups;
   - the "any time" baseline (B21);
   - a test failure hidden by a pipe in a commit (B20).

## 4. Comparative analysis of all strategies

`STRATEGY_CATALOGUE.md` lists every study with its procedure, indicators, literature, result and verdict. Out-of-sample
summary of the leads that reached independent data:

| Lead | Development | Independent data | Verdict |
|---|---|---|---|
| Engine 15m signals (B10 → B13-1) | 64.3% of 70 per signal; **52.2% of 23 per idea** | 61.4% of 44 per signal; **45.8% of 24 per idea** | No edge (repeat counting inflated it) |
| Round numbers (B4) | 47.6% vs 43.3% break-even | 41.5% vs 40.3% random | FAIL |
| Structure trigger + $15 confirmation (B19) | +$2.32 / oz, 125 trades | **−$3.04 / oz**, 49 trades | FAIL |
| Raw-ensemble top 0.5% (B22 → B23) | 62.2% of 471 | **52.8% of 394 (38 days), 30–76%** | FAIL |
| Liquidity grab, 15m (B9 → live) | 61.7% of 60 (live window); 49.4% of 913 (2020–22) | Live test: 1 of 3 | Running |
| Engine signals, one per idea (B15, live) | — | 0 results | Running |

## 5. The post-entry confirmation engine (section 3)

Every confirmation mechanism the instruction names was built and measured:

| Mechanism | Built as | Result (+$15 before −$13) |
|---|---|---|
| Breakout, then successful retest | B19 entry E2 (limit at the breakout level after confirmation) | No better than E1; FAIL |
| Liquidity sweep, then displacement | B21 SWEEP / GRAB + a $15 close beyond | 43.4–49.6% vs 46.2% |
| Structure shift, then continuation | B19 STR (BOS / MSS / CHoCH + bias), then a $15 close | Development +$2.32 → validation −$3.04 |
| Strong candle-body expansion | B20 body ≥ 2.5 × ATR | 50.5% of 291, not significant |
| ATR-adjusted momentum | B19 SATR stops; B20 body / ATR; B22 features | No gain |
| Volume expansion | No volume in spot history; B5 real COMEX order flow | AUC 0.50 |
| Multi-timeframe agreement | B6, B14, B17, B20, B22 | None |
| Dynamic support / resistance | B12, B16, B21 | None |
| Volatility / trend regime | B19 / B20 regimes, B22 HMM | None |

**The state machine B19 built** is in `quantum/research/b19.py`, with 19 tests:

```
TRIGGERED -> CONFIRMATION PENDING -> 15 / 20 CONFIRMED | INVALIDATED | EXPIRED
```

- A touch never confirms; only a candle close does.
- The direction is never reversed.
- Nothing is read from the future.

It is exactly the "prevent entry until confirmed" mechanism the instruction describes. It works as a gate. Measured
honestly, though, the gate does not raise the hit rate.

## 6. Advanced quantitative methods (section 6)

| Method | Tested in | Out-of-sample result |
|---|---|---|
| XGBoost, LightGBM, scikit-learn gradient boosting | B22 (and B13, B5) | AUC 0.49–0.51; log loss no better than the base rate |
| Random forest | B22 | AUC 0.49; its raw tail fell from 75% to 38% (B23) |
| Logistic regression | B22, B20, B5 | AUC 0.48–0.49 |
| Bayesian (Gaussian naive Bayes) | B22 | AUC 0.48 |
| Ensemble | B22, B23 | AUC 0.50; tail failed validation |
| Hidden Markov regimes (forward-filtered, no look-ahead) | B22 features | No measurable contribution |
| Change-point (CUSUM) | B22 features | No measurable contribution |
| ATR-based dynamic thresholds | B19 (SATR), B20 | No gain |
| Momentum / mean-reversion models | B1, B4, B13, B20 | None; a faint reversal after long runs |
| Platt / isotonic calibration | B22 | Calibrates to the base rate (there is nothing to calibrate) |

**None improves on the baseline**, so none is added to production. That follows the instruction: "Do not add machine
learning just to make the system look sophisticated."

## 7. The signal acceptance framework (section 7) and the dashboard (section 5)

**Rule.** A signal may be shown as a trade only when its type has a **validated** out-of-sample success rate above
break-even. Today no type has one.

**What the framework would therefore show:**

```
NO TRADE — INSUFFICIENT CONFIRMATION
(no signal type has a validated success rate above break-even; measured base: +$15 first 46%, +$20 first 39%)
```

**The dashboard panel is now built** (`quantum/confirm_panel.py`, the website card "Two-stage confirmation"; on PR #90,
live once the PR is merged). It runs the B19 state machine on the site's 15m closes for every live alert type. It is
website only: the phone alerts, the plans, the B9 / B15 tests and the freeze key are unchanged, and a test runs the
alerts with the panel on and off and requires identical sends. Section 10 has the details.

| Field | Content |
|---|---|
| Direction | BUY / SELL (never reversed) |
| Trigger price, time, timeframe, type | Engine signal / liquidity grab / break / sweep / breakout |
| Confirmation price and timeframe | The first 15m close ≥ $15 beyond, before −$13 or an opposite structure break |
| Status | TRIGGERED / CONFIRMATION PENDING / 15 CONFIRMED / 20 CONFIRMED / INVALIDATED / EXPIRED |
| Executable entry | The confirming close (the operator places SL / TP as distances from the fill) |
| SL / TP1 / TP2 | −$13 / +$15 / +$20, plus the structure stop for reference |
| Risk / reward | 15 : 13 = 1.15 and 20 : 13 = 1.54 |
| **Validated probability** | The measured out-of-sample rate for that type, with its interval (about 46% / 39% today) |
| Confidence score | Shown separately and labelled as a score (TQ / engine score), never as a probability |
| Costs | Model spread + slippage + commission; the operator's measured $0.26 per oz |
| Holding period | Average measured for that type (about 2–7 hours) |
| Why other entries were rejected | Invalidation reason, expiry, R:R or cost rejection |

## 8. Performance report (section 9)

**Basis:** success = target before stop, from the executable entry, after costs. Ties count as losses; open trades
are reported separately.

| Metric | Existing engine, one per idea, ±$13 (2020–22 / 2023–24) | Best new candidate: B23 ensemble top 0.5%, +$15 / −$13 (validation) |
|---|---|---|
| Qualifying signals | 64 / 24 | 394 rows on 38 days |
| BUY success | — | 49.8% (333) |
| SELL success | — | 68.9% (61) |
| +$15 target hit first | — (±$13 plan) | 52.8% (95% 30–76%) |
| +$20 target hit first | — | 38.4% (separate +$20 model) |
| +$13 hit first (the alert plan) | 42.2% / 45.8% | — |
| Stop hit first | 57.8% / 54.2% | 47.2% |
| Neither within the horizon | 0% / 0% | Undecided rows excluded (about 3% of rows at +$15) |
| Profit factor | 0.65 / 0.75 | about 1.15 (net +$0.88 / oz) |
| Expectancy after model costs | −$2.82 / −$1.88 per oz | +$0.88 per oz (not significant) |
| Maximum drawdown | 17.7 R / 7.4 R | Not resampled (failed validation) |
| Monte Carlo, 100 trades at 1% risk | 98% / 92% chance of a ~10 R drawdown | — |
| Out-of-sample accuracy | 45.8% (2023–24), 47.3% (2026) | 52.8%, not distinguishable from 46% |
| Average favourable / adverse excursion | Not measured in these studies | Not measured |
| Costs | Included (model $0.77–0.97 per oz) | Included |

## 9. Old versus new

| | Existing engine and alerts | Every new method (B19–B23) |
|---|---|---|
| Out-of-sample TP-first at +$15 / −$13 | About 46% (per idea) | 43–53%, none distinguishable from 46% |
| After costs | Negative | Negative or not significant |
| What improved | — | Correct counting (one per idea), honest probabilities, a tested confirmation gate, sealed-data discipline, four bugs fixed |

## 10. Implementation, tests and commits

**In code now (research modules, each with tests):**

| Module | What it is |
|---|---|
| `quantum/research/b19.py` | The two-stage confirmation engine (19 tests) |
| `b20.py` | Run calibration (6 tests) |
| `b21.py` | Confirmed liquidity / breakout (4 tests) |
| `b22.py` | ML with HMM and calibration (6 tests) |
| `b23.py` | The frozen tail test (2 tests) |

**Full suite:** 447 passed. The website freeze key is unchanged.

**Commits:**

| Study | Commits |
|---|---|
| B19 | `2c4843f77` … `442130bac` |
| B20 | `8ef843101`, `245ba4b03`, `73f002672`, `e648a2083` |
| B21 | `efee99854`, `a1961488a`, `a16ff70a4` |
| B22 | `4ec79159d`, `e3839c04d`, `51c3743a6` |
| B23 | `fc77a5f28`, `b0a825a15`, `dd5d52e34`, `48aad06fd` |

All are on PR #90.

**Implemented on this PR (website only; merged only on the operator's approval):**

| File | What it does |
|---|---|
| `quantum/confirm_panel.py` | The acceptance framework and confirmation engine of sections 3, 5 and 7, live: every trigger type → CONFIRMATION PENDING → $15 CONFIRMED (the first 15m close $15 beyond, before −$13 or an opposite structure break; $20 tracked beside it) / INVALIDATED / EXPIRED → entry at the confirming close, SL −$13, TP1 +$15, TP2 +$20, R:R 1.15 / 1.54, each resolved as in B19. Verdict per row: WAIT, NO TRADE (with the reason), or TRADE only for a type with a registered out-of-sample pass. None has one, so the card reads **NO TRADE — INSUFFICIENT CONFIRMATION**. |
| `site/app.js`, `index.html`, `style.css` | The card: direction, trigger price and time, confirmation price and timeframe (15m), structure justification, entry, SL, TP1 / TP2, R:R, the measured probability with its 95% interval (kept apart from the confidence score, which is labelled as a count of checks), holding time, costs and break-even, result with best / worst excursion, and why each other entry was rejected (invalidated, expired, folded into the same idea). |
| `quantum/notify.py` | Calls the panel (a failure there cannot stop the alerts), and returns its report without NaN (the bug below). |
| `tests/test_confirm_panel.py` | 18 tests: the live functions equal `b19.py` trade for trade on random paths; touch / same-bar / structure / gap / ambiguous / expiry / SELL edge cases; the shown rates equal the committed results; nothing is accepted without validation; repeat folding, repaint and vanish flags; phone output identical with the panel on or off; strict JSON. |
| `research/tools/excursions.py` | Section 9's missing metrics on 2020–22, using the panel's own exit function; it stops if live and research outcomes differ on any trade. |

**A production bug found while building it (fixed on this PR):** since the validation report was added
(`ef6620013`), its empty "today" / "this week" blocks carried NaN. The browser's JSON parser rejects NaN, so on any
day with nothing decided the site could not read the alerts block of `index.json` and every alert card stayed empty.
Reproduced with the production code on a copy of the live store; fixed in `notify.run` (NaN → null) and, for older
files, in the site's loader.

**Still waiting for the operator's approval (not done):**
1. Phone alerts only after a confirmation, labelled with their measured odds.
2. Correcting the "above 60%" mode, whose basis was the inflated count.
