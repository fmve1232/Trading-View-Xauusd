# XAUUSD decision-support system: institutional audit (build v90, 2026-10-31)

**Scope.**
- The nine Pine v6 artefacts on this branch (display only, A7).
- The website pipeline `quantum/` on the default branch (the system of record), **read, never edited**.
- Its forward ledger (`forward-ledger`) and its market-data store (`market-data`).

**Method.** Every statement below is backed by one of three things:
- an executed check, with its output saved and reproducible with the command given;
- a calculation done here from raw records;
- or an explicit **NOT RUN / BLOCKED** label.

**Constraints that bind this audit.**
- **A7:** the website decides; nothing here is evidence for or against an arm's pre-registered verdict.
- **AUDIT_PROMPT §9:** nothing is tuned on this price history.
- **Amendment 11:** the 2020–2025 research data is a sealed validation and holdout set. This audit **did not open it**;
  doing so outside the registered protocol would contaminate it permanently.

Status vocabulary:

| Label | Meaning |
|---|---|
| **VERIFIED** | Executed against an independent reference |
| **HISTORICAL** | Measured on recorded market data |
| **SIMULATED** | Executed on synthetic data |
| **PARTIAL** | Partially validated |
| **NOT RUN** | Not tested |
| **FAILED** | Tested and failed |
| **BLOCKED** | Missing data or access |

---

## 1. Executive summary

**Overall score: 6.3 / 10, "functional with material limitations".** **Not ready for probability-driven live
decisions.**

The software does what it says: 30 executed checkers pass, and the formulas match independent references. The analytics
do not yet do what the dashboard implies:

1. **The engine's probability has no predictive skill.** This is a critical, analytical defect (F-A78).
   - The engine's calibrated `P` (the Master's `mP`; `cal_p_long` on the website) was scored here against the event it
     is defined on, labelled independently.
   - 15m, 3,043 resolved races: AUC **0.484** (block-bootstrap 95% 0.453–0.511), Brier skill **−0.056** against a
     constant base rate.
   - 1h, 1,661 races: AUC **0.515** (0.483–0.548), Brier skill **−0.042**.
   - It ranks outcomes no better than chance and predicts worse than always saying "48%". This holds both before and
     after the forward-test start.
   - The engine's "P below minimum" veto is built on it.
2. **No strategy has a demonstrated edge.** The forward ledger to 2026-10-31 shows:

   | Strategy · timeframe | Trades | Mean R (95% t) | PF | Verdict |
   |---|---:|---|---:|---|
   | H4 · 15m (deciding) | 171 | −0.092 (−0.213 … +0.029) | 0.75 | not shown |
   | H4 · 5m | 511 | −0.179 (−0.253 … −0.105) | 0.60 | **losing** (t −4.75) |
   | H3 (the H2-card rule), 1h deciding | 3 | — | — | undecided; 5m reported: 14 trades, +0.55R, range spans 0 |
   | H5 | 0 | — | — | — |

   Before costs, H4 is about zero: −0.027R (5m) and −0.011R (15m). Costs (20% / 12% of the gross move) turn that into a
   loss.
3. **The Brief drifted from the website (F-A77, high, FIXED v90).**
   - Since 2026-10-22 the website withholds "Wait for a trigger" on a timeframe whose live H4 record is losing
     (N ≥ 50, t ≤ −2).
   - The Brief kept saying it. **On 5m right now it gave the opposite advice to the system of record.**
   - Fixed. `brief_trace.py` runs the site's own JavaScript against it: 1,080 states, 0 mismatches. Mutation-tested.

**Strengths:**
- Exhaustive executed verification of the arithmetic.
- No look-ahead: bug_scan R1 = 0 across all files; higher-timeframe requests use `[1]` + `lookahead_on`.
- DST and sessions are executed on every timeframe against the IANA zones.
- The website's conservative backtest: stop first on ties, costs charged.
- Pre-registration, a frozen forward holdout, and a sealed research holdout.

**Readiness:**
- **Research:** yes.
- **Paper trading and observation:** yes, as a levels / structure / risk display.
- **Live decision support:**
  - Yes, for levels, liquidity, sessions, the news calendar and position-size arithmetic.
  - No, for the engine's probabilities, its BUY / SELL signals or the H4 playbook triggers, until a pre-registered
    test shows an edge.

---

## 2. System inventory (Phase 1)

| Component | Purpose | Inputs | Processing | Outputs | Dependencies | Test status | Defects |
|---|---|---|---|---|---|---|---|
| **Master.pine** (5,882 lines) | Main dashboard, DECISION, MT5 plan, alerts | Chart OHLCV; 13 symbols (DXY, US10Y, US02Y, VIX, SPX, EURUSD, USDJPY, XAGUSD, WTI, GC1!, GC OI, DFII10, T10YIE) | Treatment engine: trend / HTF / structure / liquidity / macro scores → gates → TQ / EV / calibration vetoes → DECISION; analog stats; plan | 9-column dashboard, plan strip, `alert()` | none (single script) | VERIFIED: diag_parity, decision, regime, formula_trace, expectancy, macro, inputs, refactor, compile_est (~45–85 tokens free) | F-A78 (its `mP` / P-veto has no skill); F-A74 (guessed news window); F-A36 open |
| **Visuals.pine** (2,090) | Drawings, terminal panel, docks, ticker, CHECKS · RISK | Chart OHLCV; GD symbols; DXY / 10Y / silver / SPX / EURUSD / TIPS (MX copy); DFII10 daily | H2 block (byte = Master); SESSIntel (= Treatment); GD block (= Brief); MX block (= the Master's macro chain); calendar; cost; risk | Panel, docks, 8-tile ticker, banner, 7 alert types | Master (same code, by copy) | VERIFIED: panel, h2_parity, h2_trace, h2_age, v86, v88, macro, tf | none open |
| **Brief.pine** (5,634) | The website's Market Brief on the chart | Treatment engine verbatim + panel | arm_h4 playbook; site doNow + h4Losing (v90) | Brief panel, gold-arrow grid, playbook alert | Treatment twin; website app.js / arm_h4.py | VERIFIED: brief_trace (11 sections, Node + Python vs the site), diag_parity | **F-A77 fixed v90** |
| **Diagnostics.pine** (5,656) | Reliability, funnel, missed moves | Treatment engine verbatim | Engine stats displays | Diagnostics tables | Treatment | VERIFIED: diag_parity | Reliability table shows the miscalibration F-A78 measures |
| **Strategy / _OLDGATES / _CHALLENGER** | Display-only arms (A7) | Engine | Strategy orders, forward scorecard | TradingView backtest | each other (A/B hunks 5 / 4) | VERIFIED: expectancy (scorecard), inputs frozen | Not evidence (A7) |
| **Strategy_H2** (374) | H2 arm display | H2 block | Sweep-to-value | Orders | H2 block | VERIFIED: h2_parity, h2_trace | — |
| **EdgeCases** (401) | Pine-semantics assertions | Constants | 99 assertions at bar 0 | Table | — | PARTIAL: v86_check 10 (pure); runtime NOT RUN on the chart since v86 | F-A75 open |
| **quantum/engine.py** (website) | Python port of the Treatment engine | Market from the data store | Same pipeline | rows: DECISION, plan, cal_p, ev | features.py, ta.py | Run READ-ONLY here (15m: 5,704 bars; 1h: 4,009) | F-A78 |
| **quantum/backtest.py** | Forward and in-sample trades | Engine rows | Entry at close; stops next bar; **stop first on ties**; 50% at TP1, then break-even; costs | Trades, metrics (t_stat, PF, DD) | engine | Read; t_stat formula used for F-A77 | — |
| **quantum/holdout.py, arm_h2..h5.py** | Pre-registered arms, freeze keys | Engine rows | Arm rules | forward-ledger JSON | PREREGISTRATION | Read; ledger analysed (§5) | — |
| **forward-ledger** | System of record (out-of-sample) | Pipeline | — | holdout/<tf>_<arm>.json (+ archive) | — | HISTORICAL: ledger_stats.py | — |
| **market-data store** | Live-period bars | Twelve Data spot (TD key), Yahoo fallbacks | Merge, off-grid drop, trading week | CSV per month | — | Read; 15m from 2026-08-05, 1h from 2026-03-02 | Short history (§4) |
| **research-data** | Sealed research history (A11) | Twelve Data | — | 1h / 15min from 2020-01-24 | — | **Deliberately not opened** | Development period empty → "insufficient history" (A11 record) |
| **audit/tools** (51 scripts) | Verification | Artefacts, website, ledger | Static + executed checks | PASS / FAIL | pine_exec.py | Run this session (§9) | — |

**Data flow (Pine):**
- Chart bars + `request.security` (completed bars only, `[1]` + `lookahead_on`) feed the engine stages: trend → HTF →
  structure / liquidity → macro → regime → scores → gates → vetoes → DECISION → plan.
- The engine feeds the dashboard and `alert()`.
- Visuals reproduces the parts it shows by **verbatim copies**, each held equal by a checker (H2, SESSIntel, GD, MX,
  cost lines, inputs). It never computes a second opinion under the same label (F-A76).

**Disconnected / dead code:** `deadcode.py` reports **0 dead and 0 structural in all nine files** (companion-wired
values are listed). **Hard-coded values presented as live:**
- The Visuals record banner and the Brief's H4 records are **typed-in ledger figures**, labelled with their as-of
  time. Defaults are recomputed from the ledger by `v86_check` 7 and `brief_trace` 7.
- The news calendar is a coded list of official dates, ending 2027-12-10. The panel says so.

---

## 3. Code audit (Phase 2) and defect register (Phase 15)

This session's run: 30 tool outputs, **0 FAIL** (one stale table regenerated; line numbers only).

| Check | Result |
|---|---|
| precheck · undeclared · order · deadcode · pinelimits · sequence | 0 issues, 9 files |
| bug_scan | R1 look-ahead 0; repaint / timenow / alert / division hits all triaged (catalogue §2–3) |
| `tf_check.py` (every timeframe 1m–1M, DST vs IANA) | see the build record |

Defect register, by severity (new this audit, plus open ones carried forward):

| ID | Sev. | Component | Defect | Evidence | Impact | Status |
|---|---|---|---|---|---|---|
| **F-A78** | **Critical (analytical)** | engine `cal_p_long` / `cal_p_short` (website + all Pine engine copies); the Master's `mP`; `cal_veto` | The calibrated probability has no discrimination and negative skill out of sample | `engine_calibration.py` on the engine's own event: 15m AUC 0.484 (0.453–0.511), BSS −0.056; 1h AUC 0.515 (0.483–0.548), BSS −0.042; flat reliability | A "P" read as win odds misleads; the P-veto removes trades at random | **OPEN; BLOCKED by A7.** The engine is the website's frozen code, so the fix needs a website amendment. **Mitigated on the chart:** v86 prints "score"; v90 SCORE row states the measured result |
| **F-A77** | High | Brief DO NOW / PLAYBOOK | Did not replicate the site's `h4Losing` (2026-10-22): said "Wait for a trigger" where the site says don't trade the triggers | brief_trace 7 crashed on the new site line; 5m H4 t = −4.75 | Opposite advice to the system of record on 5m | **FIXED v90**, brief_trace 7: 1,080 states, 0 mismatches; mutation-tested |
| F-A74 | Medium | engine `newsWindow` | Guessed NFP / CPI dates: misses 2 of 14 NFP and all 10 FOMC; 46 of 73 flagged days have no release | v86 measurement | Wrong ABNORMAL regime on those days | Recorded; Visuals shows the official calendar; an engine fix needs the website |
| F-A75 | Low | EdgeCases | "Runtime error: Unknown error" on the chart (2026-10-21) | Operator screenshot | Diagnostic only | Mitigated v86; chart run NOT RUN since |
| F-A36 | Medium | engine gates | "WAIT while the market moved $30–50" | Diagnostics funnel: most missed moves stop at the trend gate | Missed moves; by design of the gates | OPEN (measured v27) |
| F-A56 | Low | Brief / Diagnostics | Engine twins refresh stats every 2–12 bars; the Master also on the last bar | By design | Brief / Master can differ for a few bars | Disclosed on the panel |

No defect was found in the arithmetic of position sizing, the cost model, the Wilson / t intervals, the session
engine, the H2 rule, the macro copy or the alert logic.

---

## 4. Data integrity (Phase 4)

**Inventory:**

| Series | Source | Coverage (store) | Status |
|---|---|---|---|
| XAU/USD 15m | Twelve Data spot | 2026-08-05 → 2026-10-30 (5,704 bars) | HISTORICAL, read |
| XAU/USD 1h | Twelve Data spot | 2026-03-02 → 2026-10-30 (4,009 bars) | HISTORICAL, read |
| GC=F 60m | Yahoo | from 2024-05 | not analysed here |
| DXY 60m, _TNX, EURUSD, SI=F, _GSPC | Yahoo | various, 2024–2026 | not analysed here |
| Research 1h / 15min | Twelve Data | from 2020-01-24 | **sealed (A11), not opened** |

**Verified:**
- Non-repaint of every higher-timeframe request: bug_scan R1 0; pinelimits G10.
- DST / session boundaries on every timeframe: `tf_check`.
- Macro correlations pair the same completed bar: `macro_check`.
- The website marks a series read from the store "store (live fetch failed)". Seen in this run.

**Known, disclosed differences:**
1. **Chart feed vs website feed.** TradingView chart (OANDA / broker XAUUSD) vs the website (Twelve Data spot). Levels
   can differ by the basis.
2. **Volume.** Pine uses OANDA tick volume; the website uses COMEX GC futures volume on spot bars. Volume-gated
   signals can differ.
3. **MT5 price offset.** Unknown. It is an operator input (`mt5Offset`, `h2Mt5`, `brOffset`).

**BLOCKED:**
- Live-feed verification: no TradingView / MT5 access from here.
- The broker's XAUUSD contract spec: contract size, tick value, minimum lot and commission.

---

## 5. Statistical model and strategy validation (Phases 6–8)

Sources:
- `audit/tools/ledger_stats.py`: from the raw forward-ledger records; Wilson, exact-t and bootstrap intervals; profit
  factor; drawdown; cost share. Its functions are unit-tested against hand values.
- `audit/tools/engine_calibration.py`: the engine run read-only; its scorer validated on synthetic perfect and constant
  forecasters (Brier 0 / AUC 1 and log loss ln 2 / AUC 0.5).

**Forward ledger (out of sample, system of record; as of 2026-10-31 00:58 UTC):**

| Arm · timeframe | N | Win (Wilson) | Mean R (t) | Bootstrap | PF | Max DD (R) | Before costs |
|---|---:|---|---|---|---:|---:|---:|
| H4 5m | 511 | 33.5% (29.5–37.7) | −0.179 (−0.253 … −0.105) | −0.252 … −0.106 | 0.60 | 99.2 | −0.027 |
| H4 15m (deciding) | 171 | 38.6% (31.6–46.1) | −0.092 (−0.213 … +0.029) | −0.210 … +0.035 | 0.75 | 19.9 | −0.011 |
| H4 1h | 49 | 32.7% (21.2–46.6) | −0.187 (−0.369 … −0.004) | −0.354 … −0.012 | 0.48 | 11.1 | −0.152 |
| H3 5m | 14 | 64.3% (38.8–83.7) | +0.553 (−0.520 … +1.626) | −0.305 … +1.566 | 2.13 | 4.2 | +0.800 |
| Treatment / Challenger 5m | 8 / 8 | 50% | +0.94 / +0.90 (spans 0) | — | 2.66 / 2.60 | 2.2 | — |
| H5 | 0 | — | — | — | — | — | — |

**Readings:**
- **H4 has no gross edge.** Before costs it is about zero on 5m and 15m, so costs alone make it lose. This is the
  Phase 1 diagnosis, now on 3–7× more trades.
- **Exits:** two-thirds of H4's exits are signal flips, at −0.27R on 5m. Session and regime splits are printed by the
  tool **for diagnosis only**; choosing filters from them would be tuning on the holdout.
- **Everything else is too small to judge.** H3 / Treatment / Challenger: N ≤ 14, every interval spans zero. Treatment
  and Challenger share most signals, so they are not independent.
- **The forward trades carry no usable probability.** The H4 / H3 / H5 trades carry no engine probability (they are
  playbook entries), and the engine arms have ≤ 20 trades. So **calibration was tested on the engine's every-bar
  forecasts instead**, below.

**Engine probability calibration** (F-A78; `engine_calibration.py`):
- **Event, labelled independently:** the race from the close, unit R = adaptive ATR × regime stop multiple. +1R before
  −1R within N bars (15m: 4, 1h: 3). A bar touching both counts as a loss (the engine's own convention).
- **Scope:** p is scored on resolved races.

| Timeframe · period | n | Base | Mean p | Brier | Skill vs base / running base | AUC (block bootstrap) | Calibration error |
|---|---:|---:|---:|---:|---|---|---:|
| 15m · before 2026-09-28 | 1,829 | 0.489 | 0.463 | 0.2646 | −0.059 / −0.053 | 0.499 (0.463–0.535) | 0.109 |
| 15m · forward | 1,214 | 0.469 | 0.507 | 0.2623 | −0.053 / −0.051 | 0.464 (0.419–0.507) | 0.110 |
| 1h · before | 1,410 | 0.461 | 0.430 | 0.2586 | −0.041 / −0.032 | 0.530 (0.491–0.568) | 0.092 |
| 1h · forward | 251 | 0.434 | 0.442 | 0.2592 | −0.055 / −0.051 | 0.395 (0.317–0.485) | 0.148 |

Reliability is flat. On 15m, forecasts of 0.30 / 0.44 / 0.50 / 0.54 / 0.62 by quintile were followed by 0.50 / 0.51 /
0.49 / 0.43 / 0.48.

**Caveats:**
- About 3 months (15m) and 8 months (1h) of one regime.
- Overlapping races are autocorrelated, hence the block bootstrap.
- p is the engine's live, causal estimate. The verdict "no skill" is robust: every interval includes or lies below
  chance, and every skill score is negative.

**Backtesting controls (website):**
- Entry at the close; stops live from the next bar; stop first on ties; costs = session spread + 2 × slippage +
  commission.
- Frozen forward holdout (freeze key = config + code hash).
- Amendment 11 protocol: purged walk-forward, CSCV / PBO, Deflated Sharpe, a t > 3 hurdle, White's Reality Check.
  Registered, but **not yet executable** (development period empty).

**On this branch:** the Pine strategy arms are display only (A7). No backtest here is evidence.

---

## 6. Mathematical validation (Phase 3)

Every critical formula below is executed **as written in the .pine** (`pine_exec.py`) against an independent
reference.

| Formula | Reference | Cases | Max error | Tool |
|---|---|---:|---|---|
| Calibration / Murphy decomposition, Brier, Wilson-low p′, Kelly f* | First principles | 61 blocks; 3,000 random each | ≤ 1e-13 (display rounding 5e-4) | formula_trace |
| Inverse Cornish-Fisher | Bisection | 2,000 | 2.8e-7 | formula_trace |
| Race EV = Pw·RR − Pl + E[timeout] − cost | Book formula | 2,000 | 0 | expectancy_check |
| Scorecard: mean, SD, PF, t-interval | Exact Student t | 300 histories | t error ≤ 0.0038 at df 9 | expectancy_check |
| Regime engine across all ATR percentiles; SL multiple bounds | Spec | all percentiles | 0 violations | regime_check |
| DECISION precedence, gates, veto | Spec | 5,000 | 0 | decision_check |
| H2 volume profile, signal, plan; sweep state machine | Independent spec + engine VP | 300 + 3,000 + 200 paths | 0 | h2_trace |
| Lots = floor(risk / ((stop + cost) × $/pt), 0.01); never above risk | Python | 4,000 (Visuals) + 3,000 (Master, F-A52) | 0 | v86_check 7, earlier |
| Wilson 95% | Independent + by hand | 4,000 | 1e-12 | v86_check 1 |
| Student-t 97.5% (Cornish-Fisher) | Exact table | df 10..1000 | ≤ 1.7e-4 | v86_check 2 |
| Cost model (Visuals copy) | The Master's own lines, executed | 384 | 0 | v86_check 3 |
| Macro verdict (Visuals copy) | The Master's lines, executed | 5,000 | 0 | v88_check 4 |
| Macro correlation pairing | Model with known r | 4 regimes | r recovered ±0.01 | macro_check |

**NOT independently re-derived here:** TradingView built-ins (`ta.ema`, `ta.atr`, `ta.rsi`, `ta.vwap`, `ta.pivothigh`).
They are platform functions, used as documented.

---

## 7. Risk management (Phase 10)

**VERIFIED (arithmetic):**
- Risk $ = equity × risk %.
- Lots floor to 0.01, with cost included in the loss per lot.
- Never above the risk budget (4,000 cases).
- Daily cap lock at the typed R.
- The Master's lots apply the regime size haircut (F-A52).

**BLOCKED (broker):**
- Contract size: the 100 oz / lot assumption, input `pointValue`.
- Tick value, minimum / maximum lot and step, commission.
- Account-currency conversion: USD assumed.

These must be read from the operator's MT5 symbol specification. Defaults are $25,000 at 1% (operator). The Phase 1
report suggests 0.25–0.5% while no edge is shown.

---

## 8. Dashboard (Phase 12)

**Verified:**
- Every Visuals headline value is the Master's own computation or a labelled, checked copy: macro (v88), H2, sessions
  and cost.
- No "NaN" reaches the screen in any executed text (panel_check 9, v86_check 8).
- EMA20 is white (#FFFFFF), EMA100 blue and EMA200 gold.
- Scores are labelled "score", not %, and the SCORE row now states the measured AUC.
- Stale records show their as-of time.

**NOT RUN:** compiling v86–v90 in TradingView. The Master is 7 tokens smaller than the compiled v83 file; Visuals and
the Brief are estimated under the limit (Brief 98.8–99.4%). **The compiler is the judge.**

---

## 9. Test suite (Phase 13)

**Command list:** `CLAUDE.md` "Generate it with", plus:
- `ledger_stats.py`
- `engine_dump.py` + `engine_calibration.py`, run as:

```sh
git archive origin/market-data | tar -x -C <store>
git archive origin/claude/audit-prompt-real-artefacts-nekqv6 quantum | tar -x -C <web>
PYTHONPATH=<web> python3 audit/tools/engine_dump.py 15m <store> eng15.pkl
python3 audit/tools/engine_calibration.py eng15.pkl
```

This session:
- 30 tool runs, 0 FAIL.
- **Mutation tests:** the reverted Brief DO NOW rule gives 108 mismatches; a changed ledger default FAILs; a changed
  weight in Visuals' macro copy FAILs v88 sections 1, 2 and 4.
- Unit tests of `ledger_stats` (Wilson, exact t, AUC vs brute force, Spearman, drawdown) and of the calibration scorer
  (synthetic perfect / constant) pass.

**Not testable here:**
- The TradingView runtime: the compiler, `request.security` behaviour, rendering.
- MT5.
- Live feeds.

---

## 10. Red-team (Phase 14)

| Question | Answer from evidence |
|---|---|
| Profitable via leakage? | No profitable arm exists to explain. Look-ahead screens are 0, and the website enters at the close with next-bar stops. |
| High accuracy, negative EV? | Yes, the risk is real. H4 wins 33–39% of trades but needs about 46% at its realised payoff to break even (5m: 0.666 / (0.790 + 0.666); 15m: 0.600 / (0.716 + 0.600)), so it is negative. The win rate is never a pass criterion. |
| Calibrated but unprofitable / correlated indicators? | The probability is not even calibrated (F-A78). Many engine inputs derive from the same price (EMA stacks, structure), so "agreement" overstates evidence. That is why the scores are labelled scores. |
| Stale inputs? | Typed records show their as-of time; the website marks store-fallback series. A stale MT5 offset or record is an operator risk. |
| Costs eliminate the edge? | **Yes, observed.** H4's gross ≈ 0 becomes −0.09 to −0.18R net. |
| Broker spec distorts sizing? | Possible: the contract size and commission are assumed (BLOCKED). |
| Horizon / target defined improperly? | The engine's "next-1R in N bars" event is short (1h). About 47% of 15m races time out, so p describes a narrow event. |

---

## 11. Scorecard (Phase 16)

| Dimension | Weight | Score | Evidence |
|---|---:|---:|---|
| Code correctness and reliability | 10% | 8 | 0 static issues, 30 executed tools; compile of v86–v90 NOT RUN; EdgeCases runtime open |
| Mathematical and statistical correctness | 15% | 8 | Every critical formula executed vs references (§6); built-ins not re-derived |
| Market data integrity | 10% | 6 | Non-repaint and DST verified; live feed, basis and MT5 offset BLOCKED; tick vs GC volume differs |
| Technical indicators and structure | 10% | 7 | Engine copies and alerts verified; Visuals approximations labelled; no evidence that structure labels predict |
| Strategy engine and signal integrity | 10% | 6 | Rules execute as specified (decision, h2, brief traces); no arm with a shown edge; H4 5m losing |
| Probability calibration and forecasting | 15% | **2** | F-A78: no discrimination, negative skill, out of sample; now labelled, not fixed |
| Backtesting and overfitting controls | 10% | 8 | Pre-registration, frozen holdout, conservative fills, sealed A11 holdout; research protocol not yet executable |
| Risk management and sizing | 10% | 6 | Arithmetic verified; broker spec BLOCKED |
| Dashboard accuracy and integration | 5% | 7 | Copies verified, NaN-free, measured caveats shown; compile NOT RUN |
| Automated testing and resilience | 5% | 7 | Broad executed suite with mutation tests; no Pine runtime tests possible |
| **Weighted total** | 100% | **6.3** | **Functional, with material limitations.** Not production-ready for probability-driven decisions while F-A78 is open. |

---

## 12. Outstanding work, by value

**Update (2026-10-31):** items 1 and 2 are in **website PR #49, merged 2026-10-31** (Amendment 12: score relabelled + arm H6; Amendment 13: split re-registered). H6's record starts at the next pipeline run.

1. **Website (needs the operator, A7): address F-A78.**
   - **Option A (simplest):** register an amendment that stops using `cal_p` as a veto and as "P" on the site.
   - **Option B:** pre-register a re-calibration, e.g. isotonic on a chronological split, judged out of sample.
2. **Website: Amendment 11 is blocked by "insufficient history".**
   - Only data from 2020 exists, and the registered development period ends 2019-12-31.
   - The operator must decide: a new amendment re-splitting 2020–2025 *before* anyone looks at it, or longer history
     from another licensed source.
3. **Operator inputs:** broker spread / commission, contract size, MT5 offset. These remove the BLOCKED items in §4 and
   §7.
4. **Compile v86–v90 in TradingView** and report the token counts (calibration of `compile_est`).
5. **Refresh the typed ledger records** weekly (Visuals banner, Brief H4 records). Ask, and they will be recomputed.
