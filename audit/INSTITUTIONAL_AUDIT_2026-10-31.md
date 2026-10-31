# Institutional audit — XAUUSD website (system of record), 2026-10-31

Scope: the website engine (`quantum/`), its arms, its data, the site (`site/`) and the relay (`relay/`), at
`6fca44dcf` plus this change. Pine files are reference only (Amendment 6) and were checked only where the site claims
parity with them. Every number below was **executed in this session** on the stored data (`market-data` @ `0bb2c8a96`,
`forward-ledger` @ `b8148d0a9`, `research-data` @ `d15e2b800`), unless it is marked **NOT RUN**.

**Bottom line.**

- The software is largely sound: every core formula re-derived independently matches the production code.
- **No strategy arm has shown an edge.** The result that is significant is a negative one: H4 Playbook loses, before
  and after costs.
- The model's probability and EV figures are **not calibrated**: Brier skill is negative on every timeframe.
- A 90% win rate is not supported by any evidence in this system, and the audit does not claim one.
- **Acceptance for live capital: NOT ACCEPTED.** The software for analysis: accepted with the fixes below.

All freeze keys are unchanged by this change (verified):

- Main: `5e4630924d663fc5:6f3964ad97813cc9`.
- Arms H2–H6: `adeaccb1…`, `0eb650f8…`, `09041867…`, `40d438ea…`, `7c4ac023…`.

No forward test restarts.

---

## 1. System inventory

### 1.1 Components

| Component | Purpose | Inputs | Processing | Outputs | Dependencies | Test status | Defects |
|---|---|---|---|---|---|---|---|
| `data/sources.py` (285 lines) | fetch and clean | Twelve Data, Yahoo, FRED, CFTC | retry, key redaction, drop off-grid quotes, drop market-shut bars, reopen repair | DataFrames | requests | test_live_path, test_xcheck | — |
| `data/market.py` (357) | build the chart and aligned assets | store + live | merge, `align` (last bar opened before the chart close, `close[1]`) | `Market` | sources, store | test_engine, test_no_lookahead | — |
| `data/store.py` (60) | monthly CSV store | DataFrames | merge, dedupe | CSV on `market-data` | pandas | indirect | — |
| `ta.py` (299) | Pine `ta.*` port | arrays | SMA/EMA/RMA/ATR/RSI/DMI/stdev/corr/pivots/VWAP | arrays | numpy | test_ta, **test_independent_math (new)** | — |
| `sessions.py` (97) | sessions and DST | index | IANA zoneinfo | calendar frame | zoneinfo | test_engine | — |
| `features.py` (582) | indicators, macro, MTF | Market | F-A64 / F-A65 macro, HTF scores | `F` dict | ta | test_macro_factors | — |
| `analog.py` (421) | analog / race / touch statistics | features | scan, Bayes rates | hit_prob, race_prob, oos_wr | — | test_engine | P-01 (calibration) |
| `engine.py` (1737) | scores, gates, vetoes, plan | F | bar-by-bar engine | rows, events, last | all above | test_engine (392 lines) | P-01 |
| `backtest.py` (177) | arm simulation | rows | stop first, 50% at TP1, breakeven, flip, costs | trades, metrics | numpy | **hand-worked path (new)** | B-01, B-02 |
| `config.py` (126) | frozen defaults | — | — | hash | — | test_integrity | L-04 |
| `holdout.py` (150) | freeze keys, ledgers | code + config | SHA-256 | manifests | — | test_h2..h6 | — |
| `arm_h2..h6.py` (78–173) | pre-registered arms | engine output | own rules | exec_buy / exec_sell | backtest | test_h2..h6 | C-01 (H4 loses) |
| `report.py` (605) | payload for the site | engine and arms | Kelly, gate sides, arrows, sections | JSON | — | test_gate_sides, test_gold_arrows, test_signal_status, **test_sizing (new)** | R-01 (**fixed**) |
| `macro_panel.py` (193) | macro boxes | Yahoo, FRED, relay | the \|r\| rule, daily trend | JSON | — | test_macro_panel | — |
| `notify.py`, `events.py`, `mt5.py`, `reference.py`, `manifest.py` | alerts, calendar, MT5 read, reference check, manifest | — | — | — | — | test_mt5, test_xcheck | — |
| `research/history.py` (176) | research backfill | Twelve Data | paged backfill | `research-data` | — | test_research_history | D-R1 (**fixed**) |
| `site/app.js` (1677), `index.html`, `style.css` | dashboard | JSON | rendering, live tick indicators | UI | lightweight-charts (vendored) | test_integrity, Playwright render (this audit) | DB-01 (**fixed**), P-01 wording (**fixed**) |
| `relay/worker.js` (174) | live tick relay | Finnhub stream | Durable Object, `mhist` | WebSocket | Cloudflare | relay.test.mjs | — |
| `.github/workflows/*` (5) | site build, scheduler, research, xcheck, relay | secrets | — | Pages, data branches | GitHub | runs on GitHub | — |

### 1.2 Data flow

```
sources → store (market-data) → market.align → features → engine (treatment / control / challenger)
  → arms H2–H6 (own freeze keys) → backtest → holdout ledgers (forward-ledger)
  → report → site/data/*.json → app.js
```

The relay feeds only the live chip and live indicator updates. Signals stay on closed bars.

### 1.3 Initial risk assessment

| Risk | Rating | Reason |
|---|---|---|
| Trading losses | **highest** | no demonstrated edge; see §6 |
| Overconfidence | **highest** | uncalibrated scores read as probabilities; see §7 |
| Software | moderate | see the defect register |

---

## 2. Code audit (static and paths)

`pyflakes` and `ruff` (rule sets E9, F, B, DTZ, PLE) were run over `quantum/`.

- **No syntax errors**, no bare `except:`. Broad `except Exception` appears 28 times. Each one either logs the reason
  (redacted) or is a deliberate optional-feature fallback (`notify.py`).
- **B023 (closure in loop), 24 hits in `engine.py`, `features.py` and `market.py`.** Each was read by hand. Every
  closure is called inside the same iteration that defines it, so they are **false positives**.
- **Unused code:** `numpy` in `arm_h4.py` and the variable `o` in `arm_h2.py:89`. These files are inside their arms'
  freeze keys, so removing them would restart H2 and H4 (L-01). Left as they are.
- **pandas 3.1 deprecations:** `dayofweek` and the join `lsuffix`, about 190 warnings in tests. They sit in
  `ENGINE_SOURCES` (L-02). They become errors only on pandas 4. Pin `pandas<4` until the next engine amendment.
- **Timezones:** all indexes are UTC-aware; sessions use the IANA database (D-02). No naive `datetime.now()` in
  `quantum/` (DTZ clean).

---

## 3. Mathematical and indicator validation (Phases 3 and 5)

`tests/test_independent_math.py` (new, 14 tests, **all pass**) re-implements each formula with plain Python loops
from its definition, then compares the result with production on random OHLC data that includes a flat stretch.

| Formula | Reference used | Result |
|---|---|---|
| SMA, EMA (α = 2/(n+1), SMA seed), RMA (α = 1/n) | Pine reference | equal to 1e-9 |
| EMA20 hand values (seed 10.5 on 1..20) | hand | equal |
| True range, ATR (Wilder) | Wilder 1978 | equal to 1e-9 |
| RSI | Wilder seed + smoothing; dn = 0 → 100, up = 0 → 0 | equal to 1e-8 |
| Bollinger stdev | population (Pine `biased = true`) | equal to 1e-7 |
| Pearson correlation | two-pass, on returns **and** on price levels near 2000 | equal to 1e-7 / 1e-6 (no cancellation problem) |
| Pivots | strict, `left` / `right`, reported `right` bars later | equal |
| Percent rank | share of the previous n values that are ≤ the current one | equal |
| Anchored VWAP | Σpv / Σv, equal weights until volume (D-07) | equal to 1e-12 |
| DMI and ADX | Pine reference (fixnan, `sum == 0 ? 1`) | equal to 1e-8 |
| Win rate, expectancy, t, PF, max drawdown (fixed-fractional and R), losing streak | hand | equal |
| Trade path: entry, 50% at TP1, stop moved to breakeven, exit | hand: R = (1.0 − 0.77) / 2 | equal |
| Wilson 95% lower bound | Wilson 1927 (p 0.6, n 50 → 0.462) | equal |

**Repainting.**

- Signals, scores and decisions use closed bars only (`test_no_lookahead`, `test_h4` / `h5` / `h6` no-look-ahead
  tests pass).
- HTF values read `close[1]` of the last bar that opened before the chart bar's close (D-01).
- Pivots are published `right` bars late, so a pivot is never drawn before it is confirmed.
- Only the drawn EMA, VWAP and day high / low move with live ticks, and the site states this.

---

## 4. Data integrity

Checks run on every stored series: duplicates, monotonic order, NaN, OHLC consistency (h ≥ max(o, c), l ≤ min(o, c),
h ≥ l), non-positive prices, grid alignment, gaps, and returns beyond 8σ.

| Series | Bars | From → to | Duplicates / NaN / bad OHLC | Note |
|---|---|---|---|---|
| XAU_USD 5m / 15m / 60m (Twelve Data) | 14,982 / 8,327 / 5,831 | 2026-09-09 / 08-05 / 03-02 → 10-31 | 0 / 0 / 0 | **the store keeps the 24/7 quote bars**: 1,682 on 60m inside the weekend closure, median range $0.27 against $14.90 on weekdays. `sources.trading_week_only` drops them before the engine; verified |
| XAU_USD 1d | 5,166 | 2007 → 2026 | 0 | weekend dailies dropped by the loader |
| GC=F, SI=F, DXY, EURUSD, ^GSPC, ^TNX (Yahoo) | 2.5k–20k | various | 0 | ^GSPC / ^TNX 60m bars sit on :30 / :20 (Yahoo's own grid). `align` is asof, so this is safe |
| Research TD_XAU_USD_1h / 15min | 42,835 / 170,863 | 2020-01-24 → 2026-10-22 | 0 | **D-R1:** 3,117 / 12,242 shut-window bars, in 2025–26 only (893 in 2025). **Fixed:** `research.history.load()` filters them (39,718 bars remain); test added |
| Largest moves (research 1h) | — | — | — | 2026-01-29 15:00 −5.96%, 2021-08-08 22:00 (the Sunday flash crash, −3.8%), 2020-03-16. Real events. Not cross-checked against Dukascopy in this session: **NOT RUN** (the `xcheck-dukascopy` workflow does that on GitHub) |

**Labelling.** The site already labels each item as LIVE, LIVE EST. (10Y bridge), delayed (Yahoo), store (fetch
failed) or missing. No silent substitution was found: a fallback writes `store (live fetch failed)` into the status.

---

## 5. Macro and intermarket

These were verified in earlier work and re-read for this audit.

- **F-A64:** same-period pairing.
- **F-A65:** each factor is counted once; the pool is 4 + tips_on + gc_valid, and a vote needs ceil(pool / 2).
- `test_macro_factors` passes.
- Macro is a vote, not a forecast. No macro factor's predictive value has been measured on the forward record:
  **NOT RUN** (n is too small).

---

## 6. Strategy engines, backtest and overfitting

### 6.1 Forward record (system of record, current key)

Ledgers on `forward-ledger` @ b8148d0a9, closed trades only.

| Arm / TF | N | Win % [Wilson 95%] | Mean R | t | PF |
|---|---|---|---|---|---|
| **H4 5m** | 511 | 33.5 [29.5, 37.7] | −0.179 | **−4.75** | 0.58 |
| **H4 15m** | 171 | 38.6 [31.6, 46.1] | −0.092 | −1.50 | 0.76 |
| **H4 1h** | 49 | 32.7 [21.2, 46.6] | −0.187 | −2.06 | 0.55 |
| Treatment 5m | 8 | 50.0 [21.5, 78.5] | +0.94 | 1.05 | 3.17 |
| Challenger 5m | 8 | 50.0 [21.5, 78.5] | +0.90 | 1.04 | 3.29 |
| H3 5m | 14 | 64.3 [38.8, 83.7] | +0.55 | 1.11 | 3.69 |
| All other arm / TF ledgers | 0–3 each | — | — | — | — |

- Only H4 has enough trades to judge, and it **loses**. H4's mean gross R before costs is −0.03 on 5m and 15m, so it
  has no edge before costs either.
- The positive arms have n ≤ 14, with t ≈ 1. That is indistinguishable from luck.

### 6.2 Cost and delay stress (in-sample, the whole stored window, executed)

| TF / arm | Base mean R (t) | 2× costs | Pine commission 0.385/oz | Zero cost | 1-bar entry delay |
|---|---|---|---|---|---|
| 5m treatment (n 37) | +0.19 (0.66) | +0.08 | +0.15 | +0.30 | **−1.31** (entries past the stop) |
| 15m treatment (n 12) | +0.59 (1.21) | +0.54 | +0.57 | +0.64 | +0.34 |
| 1h treatment (n 30) | +0.05 (0.18) | +0.02 | +0.04 | +0.09 | **−0.15** |
| 5m H4 (n 1731) | −0.18 (−8.4) | −0.32 | −0.23 | −0.04 | −0.23 |
| 15m H4 (n 986) | −0.11 (−4.0) | −0.18 | −0.13 | −0.04 | −0.04 |
| 1h H4 (n 729) | −0.04 (−1.3) | −0.07 | −0.05 | −0.01 | −0.05 |

- No in-sample result is significant (|t| < 2) except H4's losses.
- The treatment's small positive mean does not survive a one-bar delay on 1h or 5m.
- With so few trades, a Deflated Sharpe Ratio (Bailey & López de Prado 2014) or PBO (Bailey et al. 2017) would add
  nothing: **NOT RUN, by design.** Amendment 13's purged walk-forward on the 2020–2026 research data has no registered
  hypothesis yet.

### 6.3 Execution model

- **Sound:**
  - entry at the close of the signal bar;
  - exits from the next bar;
  - stop first on a two-way bar (conservative);
  - costs charged on every trade.
- **B-02:** a stop is filled at the stop price even when the bar *opened* beyond it, as on weekend or news gaps. This
  understates losses by 1.7 R (15m H4, 12 gaps), 2.8 R (5m H4) and 4.4 R (1h H4) over the window. The treatment had no
  such gaps. The fix (fill at min(open, stop)) is an engine change, so it needs an amendment.
- **B-01:** the website charges commission $7 per lot round-turn (0.07/oz, `commission_l`). The Pine strategy twins
  charge 0.385/oz. This difference was **not documented**; it is recorded here. Measured effect: −0.01 to −0.05 R per
  trade. Exness Raw Spread charges up to $3.50 per lot per side, which supports 0.07/oz, but the operator should
  confirm their own account's commission.

---

## 7. Probability calibration

Engine `cal_p` (P of TP1 before SL) at entry, against the outcome, in-sample over the whole stored window:

| TF | n | Mean P | Observed | Brier | Brier skill | AUC |
|---|---|---|---|---|---|---|
| 5m | 37 | 0.62 | 0.49 | 0.276 | **−0.10** | 0.515 |
| 15m | 12 | 0.63 | 0.58 | 0.251 | **−0.03** | 0.514 |
| 1h | 30 | 0.64 | 0.43 | 0.322 | **−0.31** | **0.38** |

The forward analysis of Amendment 12 found the same: AUC 0.48 on 15m and 0.52 on 1h.

**P-01:** the model's P, EV and touch rates carry **no measurable skill** and are over-confident by 5–20 points.

- Already done (Amendment 12, earlier site work): scores relabelled "not probabilities".
- This change adds the caveat to the plan card, beside the race EV and the touch rates.
- Recalibration (isotonic or Platt on the Amendment 13 development set, assessed on validation) is the proper fix. It
  is a research task under Amendment 13, not a change to the frozen engine.

---

## 8. Risk and position sizing (Phase 10)

**XAUUSD contract assumptions:** 1 lot = 100 oz; $1 move = $100 per lot; minimum and step 0.01 lot.
Checking these against the operator's own MT5 symbol specification: **NOT RUN** (no broker access; only an investor
password should ever be used for that).

**R-01 (High, fixed).** Lots were computed as risk $ / (stop distance × 100). The loss at the stop is the distance
**plus** the round-trip cost, so the real loss exceeded the chosen risk %:

| TF | Median cost / stop | Real loss at a 1% risk setting |
|---|---|---|
| 5m | 0.14 | ≈ 1.14% |
| 15m | 0.08 | ≈ 1.08% |

**The fix:**

- `report.kelly` and the site now size on (distance + cost) × 100.
- The risk tile shows "Loss at stop per lot: stop + costs".
- A float-safe floor to the 0.01 lot step.
- Recorded as D-13 in `docs/PLATFORM.md`.
- `tests/test_sizing.py` hand-checks the arithmetic: $10,000 × 1%, stop 6.00 + cost 0.77 → $677 per lot → 0.14 lot.
  It also covers the regime haircut, the minimum lot and zero distance.

**Kelly.** Binary Kelly on the Wilson lower bound, halved, then the tail, drawdown and regime haircuts, capped at the
configured risk %. It is mathematically correct, but it rests on P-01's uncalibrated rates. In practice it sizes to 0
when the edge is negative; the current 1h payload shows raw −16% → 0 lots, which is correct behaviour.

---

## 9. Decision engine and dashboard (Phases 11 and 12)

- **Decision and plan consistency:** both sides' gates are published only when they match the engine log
  (`gate_sides`). Signals come from closed bars. Vetoes are named.
- **DB-01 (fixed):** EMA20 is now **white (#FFFFFF)** in the dark theme, as in Pine Visuals (`cFast = #FFFFFF`). The
  light theme keeps the dark neutral, because white is not applicable on a white chart.
- Rendered with Playwright, 1600 px and 390 px, dark:
  - `--ov-ema20` = `#ffffff`;
  - no page errors;
  - no horizontal scroll;
  - the risk tile shows the new row.
- The layout and the other colours are unchanged.

---

## 10. Red team

| Question | Finding |
|---|---|
| Could a user read a score as a probability? | Mitigated: the scores are labelled; the plan-card caveat is added. |
| Is any profitability claimed? | None. The H4 card shows "Verdict: losing" and "Stay flat" at N ≥ 50 with t ≤ −2. |
| Can a stale or fallback feed pass as live? | No. Status labels are explicit; weekend quotes are dropped. |
| Look-ahead? | Tests pass; alignment uses `close[1]`. |
| Secrets? | None in the repo. Keys are only in Actions / Worker secrets; errors are redacted. |
| Hidden tuning? | All freeze keys are unchanged; no threshold was changed. |
| Remaining weak points | P-01, B-02, and the small n on every arm except H4. |

---

## 11. Defect register (Phase 15)

| ID | Severity | Area | Defect | Status |
|---|---|---|---|---|
| C-01 | **Critical** | strategy | No arm has positive out-of-sample expectancy. H4 loses (t −4.75, n 511). A 90% win rate has no support. | Disclosed on the site. Not fixable by code; needs research under Amendment 13. |
| P-01 | **High** | probability | P, EV and touch rates have negative Brier skill and AUC ≈ 0.5 (0.38 on 1h). | Display caveats done. Recalibration = research (Amendment 13). |
| R-01 | **High** | risk | Lot size ignored round-trip costs; real loss at the stop was up to 1.14× the chosen risk. | **Fixed** (D-13, tests). |
| B-02 | Medium | backtest | Stops fill at the stop price on gaps (understates losses by 1.7–4.4 R per window for H4). | Registered. Needs an engine amendment. |
| B-01 | Medium | backtest | Commission 0.07/oz on the web against 0.385/oz in the Pine twins; undocumented. | Documented here, impact measured. Confirm the broker commission. |
| D-R1 | Medium | data | Research history held 3,117 (1h) / 12,242 (15m) market-shut quote bars, 2025–26. | **Fixed** (`research.history.load`, test). |
| B-03 | Medium | robustness | The treatment's in-sample mean does not survive a 1-bar delay (1h, 5m). | Informational. Any future hypothesis must pass a delay test. |
| DB-01 | Low | dashboard | EMA20 grey, not white as in Pine. | **Fixed**. |
| L-01 | Low | code | Unused import and variable in `arm_h4.py` / `arm_h2.py`. | Kept: inside the arms' freeze keys. |
| L-02 | Low | code | pandas 3.1 deprecations in engine sources. | Registered; pin pandas < 4. |
| L-03 | Low | code | B023 closure warnings. | Verified false positives. |
| L-04 | Low | config | `commission_per_oz` is defined but unused. | Registered (config is frozen). |

---

## 12. Tests (Phase 13)

**Python:** 158 → **176 tests pass** (the suite runs in about 2.5 minutes).

- New: 14 independent-math tests, 3 sizing tests, 1 research-loader test.
- Engine look-ahead tests included.

**JavaScript:** 2 suites pass (relay, scheduler); `node --check site/app.js` passes.

**Not executed (NOT RUN):**

- the Pine compiler (no change to Pine);
- the live deploy (it happens after merge);
- the MT5 symbol specification;
- the Dukascopy cross-check;
- DSR / PBO / White's Reality Check (no registered hypothesis).

---

## 13. Scorecard (Phase 16)

| Area | Weight | Score / 10 | Basis |
|---|---|---|---|
| Code quality | 10 | 7.5 | clean static pass; large single-file engine; frozen low-severity leftovers |
| Mathematical correctness | 15 | 9.0 | every core formula independently re-derived and matching |
| Data integrity | 10 | 7.5 | clean OHLC; shut-bar handling verified; research loader fixed; cross-check not run here |
| TA and structure | 10 | 8.0 | non-repainting, Pine-faithful |
| Strategy performance | 10 | **1.5** | no edge; H4 significantly negative |
| Probability calibration | 15 | **2.0** | negative Brier skill everywhere |
| Backtest validity | 10 | 7.0 | honest model; the gap fill (B-02) is optimistic |
| Risk and sizing | 10 | 7.5 | correct after R-01; contract not verified with the broker |
| Dashboard | 5 | 8.0 | consistent, labelled, EMA20 fixed |
| Testing | 5 | 8.0 | 176 tests, independent references |
| **Weighted** | 100 | **6.2 / 10** | |

**Acceptance:** the software is *accepted for analysis and forward testing*. It is **not accepted for trading
capital**, because no strategy has shown out-of-sample edge (C-01) and the probabilities are uncalibrated (P-01).

---

## 14. Recommended next steps (in priority order)

1. Keep trading flat or on paper only; let the frozen arms accumulate trades. H5 and H6 have none yet.
2. Under Amendment 13, write one hypothesis before running any data, for example "recalibrated P ≥ 0.6 longs in the
   NY session". Then:
   - develop it on 2020–2023 only;
   - require t > 3 (Harvey, Liu & Zhu 2016), DSR > 0, PBO < 0.2, and survival of the 2× cost and 1-bar delay tests on
     validation;
   - open the sealed 2024-07 → 2025-12 holdout once.
3. Write an amendment that fixes B-02 (gap fills) together with the next unavoidable engine change, so that the
   forward tests restart only once.
4. Confirm the broker's commission and contract specification (B-01, §8).
