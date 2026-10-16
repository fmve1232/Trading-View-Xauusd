# Pre-deployment verification — build v60 (Master `911d38accdbef0ad`)

Requested by the operator on 2026-10-16: verify every value, calculation, method and engine order end to end before
deployment.

Each line below names the tool that checked the claim and what it executed. **PASS** means the check was executed.
**NOT RUN** means it was not; nothing is marked PASS without being executed.

## A. Calculations — executed against first-principles references

| Area | What was checked | Tool | Result |
|---|---|---|---|
| Probability calibration | constrained WLS Platt fit, sigmoid clamp [0.05, 0.95], bear fit | `formula_trace.py` | PASS |
| Cornish-Fisher | Newton inverse vs bisection; the non-monotone (Maillard) domain keeps the raw z | `formula_trace.py`, `formula_check.py` | PASS |
| Race model | TP-before-SL probabilities, E[R] = Pw·RR − Pl + E[timeout] − cost | `formula_trace.py`, `race_model_check.py` | PASS |
| Expectancy | W·AvgW − L·AvgL + T·AvgT; profit factor; break-even WR = AvgL / (AvgW + AvgL); 95% t-interval | `expectancy_check.py` | PASS |
| Kelly sizing | f* = (pb − q) / (b(p + q)) vs a numeric argmax; half-Kelly on the Wilson lower bound; regime haircut | `formula_check.py`, `formula_trace.py` | PASS |
| Brier / Murphy | UNC + REL − RES equals direct Brier | `formula_check.py` | PASS |
| Student t quantile | Fisher expansion vs exact (df 9 – 118) | `formula_check.py`, `expectancy_check.py` | PASS |
| Regime engine | all ATR percentiles: ABNORMAL > COMPRESS > EXPANSION > STRONG > WEAK > RANGE; SL multiple monotone, bounded [1.0, 2.2]; size 1.0 / 0.75 / 0.5; ATR floor | `regime_check.py` | PASS |
| Volume profile | POC / VAH / VAL vs an independent implementation; the engine VP equals the spec | `h2_trace.py` | PASS |
| H2 signal | sweep, trend, value side, 0.5–5 ATR risk, SL / TP1 / TP2; swing state machine bar by bar | `h2_trace.py` | PASS |
| Market Brief | playbook, fired, next target, last sweep, DO NOW vs the website's own code (Python + Node) | `brief_trace.py` | PASS |
| Gold arrows | flat market = ≈ (never ▼); colour = direction for gold; Brief grid = Master arrows | `brief_trace.py` | PASS |

## B. Logic — executed

| Area | What was checked | Tool | Result |
|---|---|---|---|
| Entry gate | every one of the 7 conditions is necessary; BUY and SELL are exclusive | `decision_check.py` | PASS |
| Vetoes | never BUY / SELL on a vetoed bar (TQ floor, negative EV, calibration, risk lock) | `decision_check.py` | PASS |
| DECISION precedence | RISK LOCK > NO TRADE > BUY / SELL > WARMUP > WAIT | `decision_check.py` | PASS |
| Alerts | structure / sweep alerts fire on the first bar of an event only; all 6 alert messages unchanged | `decision_check.py`, `refactor_check.py` | PASS |
| Display rewrites | every token-saving rewrite prints what the code it replaced printed (51,000+ cases) | `refactor_check.py` | PASS |
| Mobile Strip fold | 9 headers + 9 values on unique cells; each header above its value; details skipped | `refactor_check.py` | PASS |

## C. Engine identity and wiring

| Claim | Tool | Result |
|---|---|---|
| The Diagnostics and Brief engines equal the Treatment twin (3,294 code lines) | `diag_parity.py` | PASS |
| The stats engine is the same in the Master and the twin (894 lines) | `diag_parity.py` | PASS |
| The 22 DECISION / gate / veto / reach lines are the same in the Master and the twin | `diag_parity.py` | PASS |
| The H2 block is byte-identical in Visuals, Strategy_H2 and the Master | `h2_parity.py` | PASS |
| The moved features keep their v56 definitions in both the Master and the Brief, and are displayed in both | `moved_check.py` | PASS |
| Master: 0 dead, 0 structural, 0 values computed but never shown | `deadcode.py` | PASS |
| All nine files: 0 unresolved names, 0 order violations | `undeclared.py`, `order.py` | PASS |
| Known compile-error classes (G1–G12, including call arity and shadowing) | `pinelimits.py` | PASS |
| 33 operator-facing values traced: screen → variable → line → formula → verifier | `value_map.py` | PASS |
| EdgeCases' 27 code citations each match exactly one Master line | `edgecase_cites.py` | PASS |

## D. Engine sequence (same-bar order)

`sequence.py` lists every read that runs before the last same-bar write; each was triaged by hand:

- **Score pipeline** (L4463–L4529): evidence → analog blend (30%) → forecast engine → normalisation. Each step reads
  the previous step on purpose.
- **History record** (L2997): it first stores the pre-blend score. After the final scores it is overwritten for the
  current bar only (R5.3-M3, L4553–L4558). The analog scan reads only records at least OUTCOME_N bars old, so there is
  no look-ahead.
- **Risk kernel `tqVeto`** (L4832 before L4840): the same condition also requires `not riskLock`, so it is equivalent.
- **Previous-bar state, by design:**
  - pivot S/R and broken levels, order-block and FVG states;
  - calibration quantiles;
  - the open virtual trade;
  - the drawdown breaker (acts on the previous bar's MaxDD, R5-F4).
- **Call order verified:**
  - the regime and HTF data come before the evidence;
  - the entry gate reads no scores;
  - the plan is built on the FINAL scores (F-A48);
  - the calibrated probability comes before the vetoes, and the vetoes before the DECISION;
  - the MT5 prices, risk and alerts come after the DECISION.
- **Higher timeframes:** every request reads the last COMPLETED bar with `lookahead_on` (F-A41), the same in history
  and live.

## E. Not verified — the honest limits

| Item | Status | What it means for you |
|---|---|---|
| TradingView compile of v60 | **NOT RUN** | Paste the Master and check that it loads. Static checks have missed compile errors before (F-A57). |
| TradingView runtime (request.security, ta.*, table rendering) | **NOT RUN** | The tools execute the Pine text in Python; TradingView's own engine is not exercised. |
| Header widths after the v60 header loop | visual check | Confirm the desktop columns look the same as v59. |
| **Whether the signals make money** | **NOT ESTABLISHED** | The calculations are correct; the edge is not proven. The probabilities are fitted on this history behind a sliding IS/OOS boundary (ROLL, not a holdout). The record of record is the website (A7), and its forward samples are small. H4's in-sample mean R is negative (−0.11R, PF 0.67), and H2 is 1 win / 3 losses so far. |
| Brief vs Master timing | known (F-A56) | The Brief can trail the Master for a few bars. The Master rules. |
| Broker economics | assumption | Spread, commission and slippage defaults are placeholders, and the MT5 offset is set by hand. Size from your own fills. |
| Volume-based signals | approximation | OANDA tick volume, not exchange volume (Diagnostics "Volume (free plan)" row). |

**Correction (v62, F-A60).** Row A "H2 signal" and row C "H2 block byte-identical" were executed and passed, but neither covered the block's inputs, which sit outside the fences. On 1H and higher charts the Master fed H2 the engine's timeframe-gated trend scores, so its H2 SETUP could never fire there while Visuals' H2 card did. Fixed in v62; `h2_parity.py` now checks the inputs and fails on v60 / v61.

**Verdict.** Every calculation, gate, veto, decision rule, sequence and display that can be executed outside
TradingView has been executed and passes. No value is computed without being shown. Two things are not established:
that the build compiles on TradingView, and that the signals are profitable. The first needs your paste. The second
needs a frozen forward record, which no code check can supply.
