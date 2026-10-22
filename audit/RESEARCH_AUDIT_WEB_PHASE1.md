# XAUUSD system: research audit (Phase 1) and engineering plan (Phase 2), website engine

Date: 2026-10-22. Scope: the website engine (`quantum/`, `site/`), the system of record (Amendments 2 and 6).
The Pine files are a display-only reference (`reference/pine-v73/`). A separate session's Pine-branch audit (forwarded
by the operator in chat; not inspected here) reported the same headline numbers; every number below was recomputed
here from the primary sources, not copied. **No code was changed for this document.**

Evidence sources:
- Forward ledger: branch `forward-ledger` @ `e22e01bcf` (2026-10-22 00:04 UTC). Freeze start for §7 / H2–H4: 2026-10-17
  21:26 UTC (Amendment 9); H5: 2026-10-20 23:30 UTC (Amendment 10).
- Stored market data: branch `market-data`.
- In-sample run of the current engine on the store of 2026-10-20 (`quantum.pipeline`, offline).
- Literature: every reference in §2 was looked up on 2026-10-22; links are to publisher, SSRN, NBER or society pages.

---

## 1. Existing-code inventory

| Layer | Module(s) | Lines | Status |
|---|---|---:|---|
| Data | `data/sources.py` (Twelve Data, Yahoo, FRED, CFTC), `data/market.py` (alignment, D-01), `data/store.py` | 702 | Works. One alignment rule for every external series: last bar opened before the chart bar's close, read as `close[1]` (no look-ahead). |
| Sessions / calendar | `sessions.py` | 97 | IANA DST (D-02); verified correct (F-A62 does not apply). |
| Features | `features.py`, `ta.py` | 881 | Works. Macro correlations fixed to same-period pairing and factors counted once (Amendment 9). |
| Engine (decision) | `engine.py`, `analog.py` | 2,158 | Port of Pine Master v32 + v33–v65 fixes. Decides on closed bars only. |
| Execution model | `backtest.py` | 177 | Entry at the signal bar's close; exits from the next bar; stop first on a two-way bar; 50% at TP1 then breakeven; opposite signal flips; costs = session spread (0.18–0.50) + 0.2 slippage + 0.385/oz commission. |
| Forward test | `holdout.py`, `manifest.py` | 331 | Freeze key = hash of `ENGINE_SOURCES` + config; append-only ledgers; archives on restart. |
| Research arms | `arm_h2.py` … `arm_h5.py` | 527 | Each pre-registered, own freeze key, same execution model. |
| Display | `report.py`, `notify.py`, `macro_panel.py`, `site/app.js` | 2,551 | Outside the freeze key. |
| Tests | `tests/` (19 files) | 126 functions | Include `test_no_lookahead` (engine and every arm), integrity guards, relay tests. |

Verified **not** to be causes of poor trades: look-ahead (truncation tests on engine and arms), repainting (decisions
on closed bars; HTF = last completed bar), timezone/DST (IANA), macro timing (fixed in web.6).

## 2. Research bibliography (checked 2026-10-22)

**Statistical validation (peer-reviewed)**
1. Bailey, Borwein, López de Prado, Zhu, "The Probability of Backtest Overfitting", *Journal of Computational Finance*
   20(4), 2017, doi:10.21314/jcf.2016.322 — [SSRN](https://papers.ssrn.com/abstract=2326253),
   [open copy](https://escholarship.org/content/qt4w1110bb/qt4w1110bb.pdf). CSCV estimate of the probability that the
   best backtest is overfit. *Use:* PBO for any selection among variants.
2. Bailey, López de Prado, "The Deflated Sharpe Ratio", *Journal of Portfolio Management* 40(5), 2014, 94–107 —
   [SSRN](https://papers.ssrn.com/abstract=2460551). Sharpe ratio adjusted for the number of trials and non-normality.
3. Bailey, Borwein, López de Prado, Zhu, "Pseudo-Mathematics and Financial Charlatanism", *Notices of the AMS* 61(5),
   2014, 458–471 — [author copy](https://www.carmamaths.org/resources/jon/FTbackfit.pdf). Overfitting a few parameters
   on pure noise yields impressive backtests.
4. Harvey, Liu, Zhu, "…and the Cross-Section of Expected Returns", *Review of Financial Studies* 29(1), 2016, 5–68 —
   [NBER w20592](https://nber.org/papers/w20592). With extensive data mining a new finding needs t > 3.0, not 2.0.
   (Counterpoint: [arXiv 2206.15365](https://arxiv.org/pdf/2206.15365).)
5. White, "A Reality Check for Data Snooping", *Econometrica* 68(5), 2000, 1097–1126 —
   [Econometric Society](https://www.econometricsociety.org/publications/econometrica/2000/09/01/reality-check-data-snooping).
   Bootstrap test of whether the best of many models beats a benchmark.

**Gold (peer-reviewed / central bank)**
6. Barsky, Epstein, Lafont-Mueller, Yoo, "What Drives Gold Prices?", *Chicago Fed Letter* 464, 2021 —
   [Chicago Fed](https://www.chicagofed.org/publications/chicago-fed-letter/2021/464). Inflation expectations, real
   rates, pessimism.
7. Erb, Harvey, "The Golden Dilemma", NBER w18706, 2013 (*Financial Analysts Journal*) —
   [RePEc](https://ideas.repec.org/e/pha102.html). Gold is a poor short-run inflation hedge.
8. Baur, Lucey, "Is Gold a Hedge or a Safe Haven?", *The Financial Review* 45, 2010, 217–229 —
   [UTS](https://opus.lib.uts.edu.au/handle/10453/14038). Hedge on average, safe haven briefly.

**Trading-rule evidence (peer-reviewed)**
9. Moskowitz, Ooi, Pedersen, "Time Series Momentum", *Journal of Financial Economics* 104(2), 2012, 228–250 —
   [SSRN](https://papers.ssrn.com/abstract=2089463). 1–12-month trend persistence across 58 futures, gold included.
   Critiques: much of the effect comes from volatility scaling; weak in 2009–2013 ([Quantpedia](https://quantpedia.com/?p=637)).

**Books (practitioner / textbook)**
10. López de Prado, *Advances in Financial Machine Learning*, Wiley 2018 — triple-barrier labels (§3.4), meta-labeling
    (§3.6), purged k-fold CV with embargo (§7.4), combinatorial purged CV.
11. Aronson, *Evidence-Based Technical Analysis*, Wiley 2006 — data-mining bias; 6,400 rules on the S&P 500 tested
    with bias-aware statistics ([Wiley](https://www.wiley-vch.de/en/areas-interest/finance-economics-law/evidence-based-technical-analysis-978-0-470-00874-4)).
12. Harris, *Trading and Exchanges*, Oxford University Press (ISBN 9780195144703) — spreads, liquidity, adverse selection.
13. Chan, *Quantitative Trading*, Wiley 2008 (2nd ed. 2021) — reproducible backtesting.
14. Carver, *Systematic Trading*, Harriman House 2015 — forecast combination, volatility-scaled sizing, costs.
15. Pardo, *The Evaluation and Optimization of Trading Strategies*, Wiley 2008 (2nd ed.) — walk-forward analysis.

**Practitioner concepts without peer-reviewed evidence found:** BOS / CHoCH / MSS, order blocks, fair value gaps,
liquidity sweeps ("smart money concepts"). They are treated here as hypotheses to test, never as established effects.

## 3. Evidence-based assessment of the current system

**Forward record** (official; since the 17 Oct restart; Wilson interval for the win rate, t-interval for mean R):

| Arm | TF | N | Win % [95%] | Mean R [95%] | PF |
|---|---|---:|---|---|---:|
| H4 Playbook | 5m | 179 | 33.0 [26.5, 40.1] | −0.224 [−0.324, −0.123] | 0.46 |
| H4 Playbook | **15m (decides)** | 65 | 33.8 [23.5, 46.0] | −0.227 [−0.394, −0.060] | 0.43 |
| H4 Playbook | 1h | 17 | 41.2 [21.6, 64.0] | −0.185 [−0.497, +0.127] | 0.46 |
| H3 | 5m | 6 | 66.7 [30.0, 90.3] | +0.385 [−1.136, +1.906] | 1.86 |
| Treatment / Challenger | 5m | 1 | — | +0.415 | — |
| Control, H2, H5, all 1h / 4h | — | 0–1 | — | — | — |

- **H4 (the conditional playbook the site shows) is significantly negative on 15m.** It has passed its pre-registered
  N ≥ 50; under Amendment 8 the verdict is "no edge", and the interval says it loses money. Its 5m record agrees.
- Every other arm has 0–6 trades: nothing can be concluded.
- **In-sample** (rules fixed, history Mar–Oct 2026, not evidence): treatment 1h 27 trades, 44% won, +0.08R, t = 0.25.
- **Calibration:** the engine's "P(win)" does not rank outcomes. 1h treatment trades: predicted 65% → observed 33%
  (n 6), predicted 84% → observed 0% (n 2). Analog statistics: predicted 20 → 40% across bins, observed flat at
  17–25% (n 85–197 per bin). It is a score, not a probability.

## 4. Ranked root causes

| # | Root cause | Evidence | Consequence |
|---|---|---|---|
| R1 | **The entry signals carry no measured predictive power.** | H4 5m gross (before costs) −0.06R per trade; treatment in-sample t = 0.25; flat calibration. | No filter or exit can turn a coin flip into 90%. |
| R2 | **Exits are dominated by flips.** One position; an opposite signal closes and reverses. | H4 5m: 121 of 179 exits are flips (mean −0.34R); median holding 3 bars. 15m: 40 of 65. | Trades are cut before stop or target; costs are paid on every flip. |
| R3 | **Costs are large relative to intraday stops.** | Mean cost 0.85 pts vs median stop 5.75 pts on 5m (cost = 17% of risk), 9.85 on 15m (9%), 19.4 on 1h (4%). | Low timeframes start ~0.1–0.2R behind before any signal value. |
| R4 | **Trading thin hours.** H4 has no session filter. | 55 of 179 H4 5m trades in the Asian session. | More noise, wider spreads. |
| R5 | **Scores shown as probabilities.** | §3 calibration. | Over-confidence in individual trades. |
| R6 | **Too little clean history for intraday research.** | Spot store: 1h from 2026-03, 15m from 2026-08, 5m from 2026-09; daily from 2008. GC futures 1h from 2024-05. The engine's own rolling "OOS" statistics are a rolling slice, not a holdout (F-037), and its defaults come from the Pine line, tuned on charts of unknown span. | No intraday out-of-sample period exists in the store. |
| R7 | **Multiplicity.** Seven hypotheses (§7, H2–H5) on one market and period. | Pre-registration list. | Any single "winner" must clear a multiple-testing hurdle (refs 2, 4, 5). |

What is **not** wrong, verified: look-ahead, repainting, DST, macro timing, stop-before-target ordering, cost model
presence.

## 5. Strategy comparison matrix

| Hypothesis | Evidence level | Existing coverage | Data it needs | Testable now? |
|---|---|---|---|---|
| A. HTF trend + LTF pullback | Peer-reviewed for daily trend (ref 9); pullback timing practitioner | Treatment / Challenger, H5 | ≥ 10 y daily + 1h | With Dukascopy history (§7) |
| B. Breakout and retest | Practitioner | Engine BOS / displacement trigger | 1h/15m, multi-year | Same |
| C. Failed-breakout reversal | Practitioner | H2, H3 (sweep fades) | Same | Same |
| D. Liquidity sweep + structure reversal | Practitioner (no peer review found) | H2, H3 | Same | Same |
| E. Momentum / volatility expansion | Peer-reviewed (daily, ref 9) | Engine regime + displacement | Daily, 1h | Daily: yes now (2008→) |
| F. Range mean reversion | Practitioner | none | 1h/15m | With history |
| G. Macro / event filter | Peer-reviewed drivers (refs 6–8) | Macro vote, news calendar (display) | Daily FRED, DXY | Partly now |
| H. Meta-labeling of an existing primary signal | Textbook (ref 10) | none | Labels from A–D | After A–D have history |

## 6. Proposed architecture (maps to existing modules)

1. **Data integrity** — `data/` + `reference.py` cross-checks (exists). *Add:* a multi-year history loader (Twelve Data, Amendment 11).
2. **Regime** — `features.py` regime (exists). *Add:* daily trend state (12-month and 50/200-day) as a separate layer.
3. **Directional bias** — engine scores + HTF + macro (exists). *Change proposal:* the daily layer gates direction.
4. **Setup detection** — engine triggers, H2/H3 sweeps (exist), each a separate registered hypothesis.
5. **Entry confirmation** — closed bar beyond trigger (exists).
6. **Trade validation** — *new:* triple-barrier labels (TP before SL within a time limit) and an out-of-sample
   calibrated probability, only if it beats the base rate (Brier) on unseen data.
7. **Cost and execution** — `backtest.py` (exists). *Add:* cost ×2 stress and a 1-bar entry delay.
8. **Risk** — Kelly/haircut display (exists). *Add:* fixed-fraction policy, daily loss stop, kill switch (§9).
9. **Decision and reporting** — site (exists), with NO TRADE as the default state.

## 7. Data requirements and gaps

| Need | Source | Status |
|---|---|---|
| Spot XAU/USD intraday, ≥ 10 years | **Twelve Data** (the live feed), paged back to 2010 by `quantum/research/history.py` into the `research-data` branch | **Being fetched** (Amendment 11). *Correction:* this audit first proposed Dukascopy; its feed refuses GitHub's cloud addresses and its terms restrict redistribution (noted in `audit/tools/xcheck_dukascopy.py`), so it is not used. |
| Daily spot 2008→ | store | Have. |
| GC futures 1h 2024→, daily 2016→ | store | Have (basis vs spot to be measured). |
| DXY, US10Y, real yield, breakeven, 2Y | Yahoo / FRED | Have (daily FRED; 1h Yahoo short). |
| Event calendar history | none free and complete | Gap; forward only. |

**Proposed sealed split (fixed now, before any data is fetched):** development 2010–2019; validation 2020–2022;
sealed holdout 2023–2025, opened once per registered hypothesis; then the live forward ledger. Caveat: older years may
have been looked at on TradingView when the Pine defaults were chosen, so even the holdout is "not used by this website",
not "never seen by anyone".

## 8. Statistical validation protocol

1. Register each hypothesis (rules, timeframe, exits, decision rule) **before** running it, as Amendments 5–10 do.
2. Label every signal with a triple barrier: TP, SL, time limit; a win = TP before SL within the limit, net of costs.
3. Development: purged, embargoed walk-forward (ref 10); no parameter is chosen on validation or holdout.
4. Selection among variants: report the number of trials; PBO via CSCV (ref 1); Deflated Sharpe (ref 2).
5. Acceptance on the sealed holdout: mean R > 0 with t > 3.0 when chosen among many (ref 4), PF ≥ 1.2, White's
   Reality Check / SPA against "no trade" (ref 5), positive after cost ×2 and 1-bar entry delay.
6. Win rate always reported with its Wilson interval. **A 90% claim needs volume:** an observed 90% has a 95% lower
   bound ≥ 85% only from **184** trades (≥ 80% from 54). Win rate alone never decides: at 1 : 1 reward-to-risk the
   breakeven win rate is 50%, at 1.5 : 1 it is 40%, at 0.5 : 1 it is 67% (before costs).
7. Live: paper forward test until the registered N; the site shows the record, never the backtest, as the headline.

## 9. Risk-management framework (operator policy, not fitted)

- Risk per trade a fixed fraction of the account (practitioner norm 0.25–1%; the operator chooses); never sized up to
  compensate for weak signals.
- Daily loss stop and consecutive-loss pause (the engine has a risk lock; make it the operator's limits).
- Kill switch: no new trades when data is stale, spreads are abnormal, or a high-impact USD release is near (exists as
  display warnings; make it a hard NO TRADE).
- **Immediate:** do not trade the H4 playbook with real money; its record is significantly negative (§3).

## 10. Prioritised roadmap

| P | Step | Acceptance test | Restarts a forward test? |
|---|---|---|---|
| 1 | Relabel "P(win)" as a score everywhere; add H4's verdict and a "do not trade" note to the playbook | Site text; tests | No (display) |
| 2 | History loader (Twelve Data, GitHub Actions) into `research-data` | Bars back to 2010 or the feed's first bar; gaps and row counts logged | No |
| 3 | Research harness `quantum/research/`: triple-barrier labels, purged walk-forward, Wilson / t / DSR / PBO / Reality Check | Unit tests on synthetic data with known answers (zero-edge series must show PBO ≈ 0.5 and DSR insignificant) | No (outside the engine key) |
| 4 | Baseline: run the existing engine and arms on 2010–2019 development data | Report per arm, with costs and Wilson CIs | No |
| 5 | Register hypotheses A–G one by one (amendments), test on development, then validation | Protocol §8 | No (new arms) |
| 6 | Meta-labeling (H) only for a primary signal that passed step 5 | Calibrated on unseen data; Brier better than base rate | No |
| 7 | Sealed holdout, once per surviving hypothesis; then live forward test | §8 item 5 | New arm only |

---

# Phase 2 — engineering plan

| Module | Action | Acceptance |
|---|---|---|
| `quantum/engine.py`, `features.py`, `config.py` | **Preserve** (frozen; changes only by amendment) | Freeze keys unchanged by Phase 2 |
| `quantum/arm_h2…h5.py` | Preserve | Unchanged hashes |
| `site/app.js`, `report.py` | Change (display): P(win) → "score"; H4 verdict banner | Integrity tests; render check |
| `quantum/research/history.py` | **Add** (done 22 Oct): Twelve Data paging backwards to 2010 / the feed's first bar, then forwards; store format on `research-data` | Simulated-feed tests: reaches the first bar, respects the floor, resumes, no duplicates |
| `.github/workflows/research-history.yml` | **Add** (done 22 Oct): backfill on demand and monthly | Run summary with the log |
| `quantum/research/labels.py` | **Add**: triple-barrier labelling with costs | Hand-computed cases |
| `quantum/research/cv.py` | **Add**: purged, embargoed walk-forward folds | No index overlap between train and test (+ embargo) |
| `quantum/research/stats.py` | **Add**: Wilson, t-CI, DSR, PBO (CSCV), White RC bootstrap | Known-answer tests (noise → PBO ≈ 0.5) |
| `quantum/research/run.py` | **Add**: registered-hypothesis runner writing reports to `audit/research/` | Reproducible from a commit and a data hash |
| `audit/PREREGISTRATION.md` | Amendment 11: the sealed split (§7) and the protocol (§8), written before any data is fetched | Committed before step 2 |

**Decision needed from the operator before Phase 3:** approve Amendment 11 (split and protocol), the history backfill
in GitHub Actions, and the display changes in roadmap step 1. **Approved 22 Oct; done** (Amendment 11 committed first).
