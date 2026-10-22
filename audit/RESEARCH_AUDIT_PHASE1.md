# XAUUSD trade-selection engine: Phase 1 research and existing-code audit

Date: 2026-10-21. Branch: `claude/xauusd-developed-files-tmnk9g` (display only, A7). Scope: the research mandate's
Phase 1 (§12 deliverables 1-10). **No Pine Script was changed for this report.**

## 0. Summary for the operator

1. **No edge has been shown, and one deciding arm now shows a negative one.** The system of record (the website's
   forward ledger, read 2026-10-21 23:49 UTC) gives arm H4, 5m: N = 179 closed trades, mean −0.224 R, 95% CI
   [−0.324, −0.123], PF 0.46, win rate 33.0% (Wilson 95% CI 26.5-40.1%). Its deciding record (15m): N = 65,
   mean −0.227 R, CI [−0.392, −0.062], PF 0.43. Both intervals lie entirely **below** zero. The other arms (Control,
   Treatment, Challenger, H2, H3, H5) have 0-6 trades since the Amendment 9 restart, so nothing can be read from them.
2. **Where the loss comes from (diagnosis, not tuning).** On H4 5m, the average trade is about −0.06 R **before costs**,
   which is indistinguishable from zero. Costs (spread + 2 × slippage + commission, mean 0.85 points) take it to
   −0.22 R. Two exits in three are a **signal flip** (121 of 179); the median hold is **3 bars**. The signal therefore
   has no gross edge, and its churn turns zero into a loss.
3. **A 90% win rate cannot be promised or engineered honestly.** A win rate is set mostly by the exit design: a tight
   target and a wide stop give 90% wins and still lose money. Proving a true 90% (lower 95% bound ≥ 85%) needs about
   **184 closed trades** at an observed 90%. The pre-registered way to pursue "high confidence" already exists: arm
   **H5** (Amendment 10). It decides on 1H at N ≥ 30 by mean R and PF, not by win rate, and has 0 trades so far.
4. **The chart's own probability is not calibrated** (Diagnostics, display only). The top bucket predicts 52% and
   delivers 26%. Buckets 1-4 barely separate (observed 31 / 28 / 26 / 26% against predicted 29-39%). A "P(win)"
   number on the chart is therefore not yet a probability.
5. **The data cannot support intraday research yet.** XAU_USD history on the website's data branch: 60m since
   2026-03, 15m since 2026-08, 5m since 2026-09; daily back to 2008. GC_F 60m since 2024-05. Seven months of hourly
   data cover roughly one volatility regime, so no intraday rule can be validated across regimes from it.
6. **Where the work belongs.** Research, backtests, purged cross-validation, PBO and the Deflated Sharpe all need the
   website's Python pipeline (`quantum/`). That is the system of record, and this line of work must not edit it, its
   freeze key or the default branch (CLAUDE.md, A7). **Phase 2/3 therefore need your explicit authorisation.**
   Section 10 sets out the options.

Status labels in this report: **MEASURED** (computed here from the ledger or data, reproducible), **CITED** (from
verified literature; G9's volume number is from the DOI record), **DISPLAY-ONLY** (from this branch's chart tools; not evidence under A7) and **HYPOTHESIS**
(to be tested; not a result).

---

## 1. Code inventory (deliverable 1)

### 1.1 Chart scripts (this branch, display only)

| File | Lines | Role | Engine |
|---|---:|---|---|
| `XAUUSD_Quantum_5_0_Master.pine` (v83 file) | 5,882 | Indicator. DECISION, dashboard, MT5 plan, alerts, H2 SETUP. **About 45-85 compiled tokens free** (measured, v85 probes). | Treatment engine + stats |
| `XAUUSD_Quantum_5_5_Visuals.pine` (v85) | 1,672 | Drawings, terminal panel, dock, bottom ticker, H2 card, gold drivers (GD), sweep alerts | H2 block = Master; GD block = Brief |
| `XAUUSD_Quantum_5_0_Brief.pine` | 5,609 | Market Brief (website `arm_h4.py` / `app.js` replicated); ENGINE / DATA rows | Treatment verbatim |
| `XAUUSD_Quantum_5_0_Diagnostics.pine` | 5,656 | Reliability, funnel, missed moves, rolling WR | Treatment verbatim |
| `Strategy.pine` / `_OLDGATES` / `_CHALLENGER` | 5,419 / 5,419 / 5,430 | Strategy twins (A/B: 5 hunks; T vs C: 4) | Treatment / Control / H1 |
| `Strategy_H2.pine` | 374 | Arm H2 display | H2 block |
| `EdgeCases.pine` | 395 | Run-once harness. **Raised "Runtime error: Unknown error" on the chart; remove it.** | — |

The Master reads 13 external symbols (GC1!, GC1!_OI, DXY, US10Y, US02Y, VIX, SPX, EURUSD, USDJPY, XAGUSD, WTI,
T10YIE, DFII10) and has 94 inputs. External series use `close[1]` with `lookahead_on` (the non-repainting idiom). The
static checkers report 0 look-ahead hits (`bug_scan.py` R1-R4).

### 1.2 Website pipeline (system of record, default branch, read only here)

| Module | What it does |
|---|---|
| `quantum/engine.py`, `features.py`, `ta.py`, `sessions.py`, `events.py` | Python port of the Treatment engine; sessions; calendar |
| `quantum/backtest.py` | Entry at the signal bar's close; stops and targets live from the next bar; **stop first when SL and TP1 share a bar**; 50% at TP1 then break-even; cost = session spread + 2 × slippage (0.2) + commission |
| `quantum/holdout.py`, `manifest.py` | Freeze key = config + engine code hash; the forward ledger restarts on any change |
| `quantum/arm_h2.py` … `arm_h5.py` | Pre-registered arms (sweep-to-value, H3, H4 playbook, H5 high confidence) |
| `quantum/data/` | Market data store (branch `market-data`) |
| `quantum/macro_panel.py`, `analog.py`, `report.py`, `notify.py`, `mt5.py` | Display, analogues, report, notifications, MT5 export |

**Assessment.** The website's design is already conservative and largely in line with the literature: costs are
charged, ties are resolved against the trader, the forward test is frozen, and decisions are pre-registered. The
main gaps are research tooling: no purged / embargoed CV, no PBO or CSCV, no Deflated Sharpe, no register of how
many variants were tried, and no event-surprise data. The fault does not lie in the backtest arithmetic.

### 1.3 Multiplicity already incurred

- **On the record:** 7 arms (Control, Treatment, Challenger, H2, H3, H4, H5) × 4 timeframes = 28 ledgers.
- **On this branch:** 85 display builds. Before A7 these included amendments A1-A6 and parameters chosen on the same
  price window (AUDIT_PROMPT §9).
- **Consequence:** any future "best arm" must be judged against that number of trials (§8: DSR / PBO), not alone.

---

## 2. Verified bibliography (deliverable 2)

Every entry below was checked against a publisher, journal or repository page on 2026-10-21. Books are cited by
edition; I did not re-read their full text for this report.

### 2.1 Overfitting, multiple testing, validation

| # | Reference | Used for |
|---|---|---|
| B1 | Bailey, Borwein, López de Prado, Zhu (2017). *The Probability of Backtest Overfitting.* J. Computational Finance 20(4). doi:10.21314/JCF.2016.322. [SSRN](https://papers.ssrn.com/abstract=2326253) · [Risk.net](https://www.risk.net/journal-of-computational-finance/2471206/the-probability-of-backtest-overfitting) | PBO and CSCV (§8) |
| B2 | Bailey, López de Prado (2014). *The Deflated Sharpe Ratio.* J. Portfolio Management 40(5), 94-107. doi:10.3905/jpm.2014.40.5.094. [SSRN](https://papers.ssrn.com/abstract=2460551) | Correcting for trial count and non-normality |
| B3 | Bailey, Borwein, López de Prado, Zhu (2014). *Pseudo-Mathematics and Financial Charlatanism.* Notices of the AMS 61(5), 458-471. [Bailey](https://davidhbailey.com/) | Why tuning on one history fails |
| B4 | Bailey, López de Prado (2021). *How "Backtest Overfitting" in Finance Leads to False Discoveries.* Significance 18(6), 22-25. doi:10.1111/1740-9713.01588. [OUP](https://academic.oup.com/jrssig/article/18/6/22/7038278) · [eScholarship](https://escholarship.org/uc/item/9tq3327h) | Lay summary. B1's example: with 5 years of daily data, try no more than 45 variants |
| B5 | Harvey, Liu, Zhu (2016). *…and the Cross-Section of Expected Returns.* Rev. Financial Studies 29(1), 5-68. [NBER w20592](https://nber.org/papers/w20592) | New-factor hurdle t > 3.0 |
| B6 | White (2000). *A Reality Check for Data Snooping.* Econometrica 68(5), 1097-1126. doi:10.1111/1468-0262.00152. [Econometric Society](https://www.econometricsociety.org/publications/econometrica/2000/09/01/reality-check-data-snooping) | Testing the best of many rules |
| B7 | Hansen (2005). *A Test for Superior Predictive Ability.* J. Business & Economic Statistics 23, 365-380 (volume and pages from a secondary source, [nm.dev](https://nm.dev/2011/07/28/on-whites-2000-reality-check/)) | A more powerful variant of B6 |
| B8 | López de Prado (2018). *Advances in Financial Machine Learning.* Wiley | Purged k-fold, embargo, triple-barrier labels, meta-labelling |
| B9 | Aronson (2006). *Evidence-Based Technical Analysis.* Wiley | Data-mining bias in TA rules |
| B10 | Pardo (2008). *The Evaluation and Optimization of Trading Strategies*, 2nd ed. Wiley | Walk-forward analysis |

### 2.2 Gold drivers and microstructure

| # | Reference | Used for |
|---|---|---|
| G1 | Barsky, Epstein, Lafont-Mueller, Yoo (2021). *What Drives Gold Prices?* Chicago Fed Letter 464. doi:10.21033/cfl-2021-464. [Chicago Fed](https://www.chicagofed.org/publications/chicago-fed-letter/2021/464) | Real rates, inflation expectations, risk / safe-haven demand |
| G2 | Erb, Harvey (2013). *The Golden Dilemma.* Financial Analysts Journal 69(4), 10-42. [NBER w18706](https://www.nber.org/papers/w18706) · [CFA](https://rpc.cfainstitute.org/research/financial-analysts-journal/2013/the-golden-dilemma) | Gold is an unreliable inflation hedge over practical horizons; the real price mean-reverts |
| G3 | Baur, Lucey (2010). *Is Gold a Hedge or a Safe Haven?* Financial Review 45(2), 217-229. [UTS](https://opus.lib.uts.edu.au/handle/10453/14038) | Safe-haven effect is short-lived |
| G4 | Baur, McDermott (2010). *Is Gold a Safe Haven? International Evidence.* J. Banking & Finance 34(8), 1886-1898. [EconPapers](https://econpapers.repec.org/paper/iisdispap/iiisdp310.htm) | Safe-haven effect differs by market |
| G5 | Cai, Cheung, Wong (2001). *What Moves the Gold Market?* J. Futures Markets 21(3), 257-278. [IDEAS](https://ideas.repec.org/a/wly/jfutmk/v21y2001i3p257-278.html) | Intraday volatility pattern; employment, GDP, CPI and personal income move COMEX gold most |
| G6 | Gu et al. (2023). *Monetary Policy and Uncertainty Resolution in Commodity Markets.* Finance Research Letters. [UMN](https://experts.umn.edu/en/publications/monetary-policy-and-uncertainty-resolution-in-commodity-markets/) | FOMC resolves gold implied volatility, more strongly with the SEP |
| G7 | Harris (2003). *Trading and Exchanges.* Oxford UP | Spreads, liquidity, who is on the other side |
| G9 | Moskowitz, Ooi, Pedersen (2012). *Time Series Momentum.* J. Financial Economics 104(2), 228-250. doi:10.1016/j.jfineco.2011.11.003. [SSRN](https://papers.ssrn.com/abstract=2089463) · [AQR](https://www.aqr.com/library/journal-articles/time-series-momentum). Critique: Kim, Tse, Wald (2016) attribute much of the effect to volatility scaling | 12-month trend in 58 futures incl. gold (R1) |
| G8 | Chan (2008/2021). *Quantitative Trading.* Wiley; Carver (2015). *Systematic Trading.* Harriman House | Cost discipline, position sizing, forecast scaling |

**Not cited, by design:** retail "smart money" / ICT sources (order blocks, liquidity sweeps, CHoCH, kill zones). I
found no peer-reviewed evidence for them. Here they are features to **test**, not established effects (§5).

---

## 3. Evidence-based assessment of the current system (deliverable 3)

### 3.1 Forward record (MEASURED; ledger branch `forward-ledger`, read-only)

Since the Amendment 9 restart (2026-10-17 21:26 UTC). WR = share of closed trades with R > 0.

| Arm / TF | N | WR (Wilson 95%) | Mean R (95% t) | PF | Sum R |
|---|---:|---|---|---:|---:|
| H4 5m | 179 | 33.0% (26.5-40.1) | −0.224 (−0.324, −0.123) | 0.46 | −40.04 |
| **H4 15m (deciding)** | 65 | 33.8% (23.5-46.0) | −0.227 (−0.392, −0.062) | 0.43 | −14.74 |
| H4 1H | 17 | 41.2% (21.6-64.0) | −0.185 (−0.478, +0.108) | 0.46 | −3.15 |
| H3 5m | 6 | 66.7% (30.0-90.3) | +0.385 (−0.774, +1.544) | 1.86 | +2.31 |
| All others | 0-1 | — | — | — | — |

**Status.** H4 15m has passed N ≥ 50 with the whole interval below 0. Applying the pre-registered decision rule to
it is the website's job (Amendment 8/9), not this branch's. The figures are reported here as facts.

### 3.2 Decomposition of the H4 loss (MEASURED; a diagnosis, not a parameter search)

| Quantity | 5m | 15m |
|---|---:|---:|
| Mean R before costs (approx.) | −0.056 | −0.136 |
| Mean cost per trade (points) | 0.85 | 0.87 |
| Costs ÷ \|gross move\| | 27% | 15% |
| Exit by FLIP / SL / BE / TP2 | 121 / 17 / 17 / 24 | 40 / 11 / 9 / 5 |
| Mean R of FLIP exits | −0.34 | −0.24 |
| TP1 reached | 27.9% | 29.2% |
| Median bars held | 3 | 3 |
| Break-even win rate at the realised payoff | 51.5% | 54.4% |

**Reading.** Most H4 trades are closed by the next opposite signal within three bars. On 5m, before costs, they
average about zero. The realised payoff (average win 0.59 R against average loss 0.62 R) needs a win rate above 51%
to break even, and the arm wins 33%. **Splitting these results by session or exit type in order to pick a filter
would be tuning on the holdout. I report the splits only as a diagnosis.**

### 3.3 The chart's probability model (DISPLAY-ONLY; Diagnostics screenshot)

| Bucket | n | Predicted | Observed |
|---|---:|---:|---:|
| B0 | 228 | 22% | 8% |
| B1 | 224 | 29% | 31% |
| B2 | 305 | 34% | 28% |
| B3 | 229 | 39% | 26% |
| B4 | 93 | 52% | 26% |

- **Summary statistics:** base rate 24%, Brier 0.189, calibration error 12 points.
- **Calibration:** the score is not monotone above B1, so it adds little beyond the base rate.
- **The cause is structural.** The probability terms were weighted on the same history they were scored on, which
  is in-sample by construction.
- **The gates add no measured value.** In the gate funnel, 5,243 bars become 220 signals and then 47 PASS. Of 277
  moves of $30 or more, 3 were missed at ENTRY and 170 at the trend gate. The data cannot show whether this filtering
  adds value, so its value is unmeasured.

### 3.4 Engineering quality (MEASURED on this branch)

The display stack is heavily verified. Of the 22 checkers, all pass on the deployed files:

- 0 dead values;
- `formula_trace` 61/61;
- every timeframe executes (`tf_check`);
- look-ahead 0;
- every division guarded.

That proves the code does what it says. **It says nothing about whether what it says makes money.**

---

## 4. Ranked root causes (deliverable 4)

| Rank | Root cause | Evidence | Fix class |
|---|---|---|---|
| 1 | **No gross edge in the entry signal.** Reversal churn: the signal flips within about 3 bars. | §3.2: about 0 R before costs; 2/3 FLIP exits; median 3 bars | Research a different signal family (§5), validated as in §8. Not a re-tune. |
| 2 | **Costs too large relative to the target on low timeframes.** 0.85 points per round trip against stops sized from 5m / 15m ATR. | 27% of the gross move on 5m | Prefer horizons where the expected move ≫ cost (≥ 1H); model costs per session |
| 3 | **Parameters and weights chosen in-sample**, plus about 85 builds and 28 ledgers of trials | AUDIT_PROMPT §9; §1.3 | Trial register; DSR / PBO; one frozen holdout per hypothesis |
| 4 | **Uncalibrated probability shown as "P(win)"** | §3.3 reliability table | Out-of-sample calibration (isotonic / Platt) or drop the probability label |
| 5 | **Intraday history too short** for regime-robust validation | §7 data inventory | Acquire longer intraday data (§7) before intraday research |
| 6 | **Drivers measured at the wrong frequency or proxy.** Real yields (G1's main driver) are daily-only (DFII10), and the Master uses nominal US10Y intraday. | Master line 510 tooltip; v65 note | Test drivers at the frequency they exist (daily regime filter), not on 1H bars |
| 7 | **Win rate as the target** (the operator's 90%) | §0.3 | Optimise expectancy with intervals; report WR only alongside payoff |
| 8 | Unpriced event risk (NFP, CPI, FOMC) beyond a time-window block | G5, G6; no surprise data | Event calendar with consensus / actual, used as features or exclusions |

---

## 5. Strategy comparison matrix (deliverable 5)

"Evidence" means published evidence for gold or futures specifically. **None of these is claimed to work here; each
is a candidate hypothesis for §8.**

| Family | Mechanism | Literature evidence | Horizon | Cost sensitivity | Testable on current data? |
|---|---|---|---|---|---|
| Time-series trend (momentum) | Return persistence across futures | Strong, 58 futures incl. gold (G9); partly a vol-scaling effect (critique in G9) | Daily-weekly | Low | **Yes**: XAU daily since 2008 |
| Macro regime filter (real yield, USD, risk) | Gold vs real rates / USD / stress (G1, G2, G3) | Strong at monthly-daily; weak intraday | Daily+ | Low | Yes, daily (DFII10, DXY) |
| Event-driven (post-NFP / CPI / FOMC drift or fade) | Information arrival (G5, G6) | Volatility effect strong; direction weak | Minutes-hours | High | **No**: needs surprise data and long intraday history |
| Session breakout (Asia range → London / NY) | Liquidity transitions (G7) | Practitioner; little peer review for gold | Intraday | Medium | Marginal (7 months 60m) |
| Mean reversion to VWAP / value (H2 family) | Inventory / liquidity provision | Mixed; cost-dominated | Intraday | High | Marginal |
| Liquidity sweep / CHoCH / OB ("SMC") | Stop-run then reversal | **None peer-reviewed** | Intraday | High | Marginal; current H4 evidence is negative |
| Volatility-regime position sizing | Vol targeting (Carver) | Strong for **risk**, not direction | Any | — | Yes |
| Meta-labelling over a primary signal (B8) | Learn when a primary signal works | Method sound; needs many labels | Any | — | Only once a primary signal has a gross edge |

**Implication.** Every family with strong evidence works at **daily** horizons, and the current system trades 5m-1H.
The proposed architecture therefore puts a daily, evidence-backed regime layer in charge. Intraday logic only times
entries inside it.

---

## 6. Proposed architecture and signal definitions (deliverable 6)

```
Layer 0  Data            versioned bars, costs per session, event calendar (actual vs consensus)
Layer 1  Regime (daily)  trend sign + macro state, pre-registered, at most 2-3 inputs
Layer 2  Setup (1H)      one primary signal family per hypothesis
Layer 3  Timing (15m)    entry refinement only; may veto, never originates
Layer 4  Risk            vol-scaled size, daily loss cap, event exclusion, kill switch (§9)
Layer 5  Display (Pine)  shows Layers 1-4 computed by frozen rules; no tuning on the chart
```

The candidate definitions below are **HYPOTHESES, each to be frozen before any test.** Parameters are fixed a priori
from conventional values, not searched.

- **R1 (regime): trend.** Sign of the 12-month XAU return, plus the price above or below its 200-day mean. Long-only
  when both are positive, short-only when both are negative, otherwise flat.
- **R2 (regime): macro.** 20-day change in DFII10 (real yield) and DXY. Gold-supportive when both are falling (G1).
  Used as a filter on R1, and tested on its own.
- **S1 (setup): pullback in trend.** In an R1-long regime, buy on 1H when price returns to the 20-period EMA and the
  bar closes back above it. Stop at 1.5 × ATR(14, 1H); target 2 R, time stop 24 bars; **no flip exits.**
- **S2 (setup): session breakout.** Asia range (00:00-07:00 London). Enter a London break in the regime direction;
  stop at the opposite side of the range.
- **E1 (exclusion).** No entries from 30 minutes before to 30 minutes after a scheduled NFP / CPI / FOMC release.

**Why this design.** Its main feature is that it trades fewer, longer trades: the expected move must be several times
the 0.85-point cost. It deliberately counters root causes 1 and 2.

**How it fits the existing system.** The current Treatment / H2 / H4 / H5 arms are **not removed**: they stay on the
record and on the chart (operator rule: delete nothing). New arms are added beside them.

---

## 7. Data requirements and gaps (deliverable 7)

| Need | Have (website `market-data`) | Gap | Option (to verify: licence and cost) |
|---|---|---|---|
| XAU intraday, ≥ 5 years | 60m from 2026-03; 15m from 2026-08; 5m from 2026-09 | **Years missing** | Dukascopy historical feed; broker (MT5) history export; GC futures from a vendor |
| XAU daily, long | 2008-02 → present | OK | — |
| GC futures, continuous | 1d 2016+; 60m 2024-05+ | Roll-adjusted intraday | Vendor continuous contract |
| Real yield | DFII10 daily (TradingView; FRED) | Not on the website store | FRED DFII10 (public) |
| USD | DX-Y.NYB 60m 2024-05+ | Long daily history | FRED broad dollar index (public) |
| Event surprises | Calendar times only | **Consensus vs actual** | Public calendars (needs scraping + licence check) |
| Realistic costs | Session spread model (0.3 / 0.2) | Broker-specific spread history | Log the operator's MT5 spreads (forward) |
| Positioning (optional) | — | CFTC COT | CFTC public weekly |

**Hard constraint.** Without at least 3-5 years of intraday data, no intraday rule (S1, S2) can be validated across
regimes. Until that data exists, only the daily layer (R1, R2) can be researched.

---

## 8. Validation protocol (deliverable 8)

1. **Trial register.** Before any test, write down every hypothesis and variant in a new pre-registration amendment
   on the website. Count trials from the start, including the 28 ledgers already run.
2. **Splits.** Use purged k-fold with an embargo of at least the maximum holding period (B8) for model building. Run
   CSCV on the matrix of all variants to estimate PBO (B1). **Reject a family if PBO > 0.2.**
3. **Statistics per candidate:**
   - mean R with a 95% interval (t and stationary bootstrap);
   - PF;
   - Deflated Sharpe at the registered trial count (B2);
   - for the best-of-many, White's Reality Check / Hansen SPA (B6, B7);
   - a new effect needs t ≥ 3.0 (B5).
4. **Win rate is reported only with its Wilson interval and next to the payoff.** It is never a pass criterion.
5. **Out-of-sample decision.** One frozen forward holdout per surviving family. Use the existing rule (N ≥ 50, mean-R
   interval > 0, PF ≥ 1.2), with sample sizes set in advance from the measured R dispersion (sd ≈ 0.68 R):
   - N ≈ 46 to detect +0.2 R;
   - N ≈ 180 to detect +0.1 R;
   - N ≈ 184 to support a 90% WR claim with a lower bound ≥ 85%.
6. **Stop rules.** If the holdout's interval lies entirely below 0 at N ≥ 50, the arm has failed. **It is not
   re-tuned**: a changed rule is a new hypothesis with a new trial count.
7. **Execution parity.** The Pine display must reproduce the Python rule bar for bar, using the existing parity
   tooling (`brief_trace.py` pattern).

---

## 9. Risk framework (deliverable 9)

| Control | Rule | Basis |
|---|---|---|
| Risk per trade | 0.25-0.5% of equity at the stop while no edge is proven; 1% only after an arm shows an edge | Carver; the current CI is negative |
| Volatility sizing | Size ∝ target risk ÷ (stop distance in $) | Vol targeting |
| Daily loss cap | Stop for the day at −2 R | Bounds the run-of-losses tail (33% WR ⇒ long losing streaks are likely) |
| Event exclusion | E1 window; flat into FOMC unless the hypothesis is event-based | G5, G6 |
| Cost check | Skip if expected move to TP1 < 4 × round-trip cost | Root cause 2 |
| Kill switch | Stop live use of any arm whose forward mean-R interval lies entirely below 0 | §8.6 |
| Correlation | One XAU position at a time; no stacking of arms in the same direction | Arms share the engine |

**A practical point for now.** H4 is the arm whose playbook the Brief shows ("what to do"). Its forward interval is
entirely negative, so I recommend **not trading H4's playbook live with real money** while the website records its
verdict. That is a risk-management statement, not a change to any rule.

---

## 10. Prioritised roadmap (deliverable 10)

| # | Step | Where | Needs your approval? | Effort |
|---|---|---|---|---|
| 1 | Record the H4 reading under its pre-registered rule; mark H4 FAILED / continue as the rule says | Website (record) | **Yes**: default branch | S |
| 2 | Add the Chart "P(win)" caveat: label it "score", not probability, until calibrated (display text only) | This branch (Visuals has room; Master about 45-85 tokens) | Yes (display change) | S |
| 3 | Data acquisition: long XAU intraday + FRED DFII10 / broad USD + event surprises (licences checked) | Website data store | **Yes** | M |
| 4 | Research tooling: trial register, purged k-fold + embargo, CSCV / PBO, DSR, SPA, Wilson/bootstrap CIs | Website `quantum/research/` (new module, outside the frozen engine) | **Yes** | M |
| 5 | Pre-register R1/R2 (daily) as Amendment 11 **before** running them; then run CSCV on the daily history | Website | **Yes** | M |
| 6 | If R1/R2 survive (PBO < 0.2, DSR > 0): pre-register S1/S2 under them; forward holdout | Website | Yes | M |
| 7 | Pine display of surviving arms (new companion, or Visuals; the Master cannot grow) | This branch | Yes | M |
| 8 | Calibrate the chart score out of sample, or keep it labelled "score" | Website → this branch | Yes | S |

**Phase 2 (engineering plan) is steps 3-4.** Phase 3 (strategy) is steps 5-7. Nothing in steps 1 or 3-6 can be done
from this branch under the current rules. Your options:

- **(a)** authorise work on the website / default branch for steps 1, 3-6; or
- **(b)** authorise a separate research branch that writes nothing to the website until you merge it; or
- **(c)** keep this line display-only. Then only steps 2, 7 and 8 are possible here.

## Appendix: reproduction

- **Ledger statistics:** `git show origin/forward-ledger:holdout/<tf>_<arm>.json` for each file. Exclude
  `open: true`.
  - WR is the share with r > 0, with a Wilson 95% interval.
  - Mean R uses a 95% normal-approximation t interval (z = 1.96).
  - PF is the sum of positive R divided by the absolute sum of negative R.
  - "Before costs" scales each trade's R by `gross_pts / pts`.
- **Sample sizes:**
  - N to detect a mean of m: ⌈(1.96 · sd / m)²⌉.
  - N for the 90% claim: the smallest n with Wilson lower(0.9n, n) ≥ 0.85.
- **Reliability table:** from the Diagnostics script (display only).
