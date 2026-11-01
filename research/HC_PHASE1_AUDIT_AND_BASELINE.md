# High-confidence confirmation engine — Phase 1 audit and Phase 2 baseline (2026-11-01)

This answers the operator's brief "XAUUSD QUANTUM — HIGH-CONFIDENCE TRADE CONFIRMATION ENGINE", Phases 1 and 2.

**No production code was changed for this report.** It maps every requirement of the brief onto the code as it
stands, building on the earlier audits and verified against the code and data as of today:
- `audit/INSTITUTIONAL_AUDIT_2026-10-31.md`
- `research/CURRENT_STRATEGY_AUDIT.md`
- `research/DATA_INTEGRITY_AUDIT.md`
- `research/CURRENT_PERFORMANCE_AUDIT.md`

**Version audited**

| Item | Value |
|---|---|
| Default branch | `3b6bba043` |
| Working branch | `b4f82240f` (adds the unmerged B3 research) |
| Engine | **Q7.2-web.7**, freeze key `5e4630924d663fc5:60bb01794d03c9ac`, forward test started 2026-10-31 17:23 UTC |
| Ledger read | `forward-ledger` @ `fafed1be9` |
| Market data read | `market-data` @ `c50566bec` |

---

## 0. Summary

| Brief requirement | State today | Verdict |
|---|---|---|
| Reliable, traceable data (Stage 1) | Closed-bar engine, cleaning, one instrument per run, source recorded, stale-data banner | **Partly met.** No bid/ask, no DATA UNAVAILABLE decision, and a futures fallback that is used rather than blocked |
| Exact broker contract maths (§2 D) | 100 oz per lot, $7 per lot, modelled spread, account in USD | **Not met.** The broker's MT5 symbol specification has never been obtained |
| Regime classification (Stage 2) | Six regimes plus bias labels per timeframe; EMA 20/100/200, VWAP, structure, ADX, ATR percentile | **Partly met.** No EMA50; the classes differ from the brief's eight; regime suitability is unmeasured |
| Entry confirmation (Stage 3) | Gates and named vetoes | **Exists, but no factor has shown measurable incremental value** (§4) |
| Microstructure (Stage 4) | No order book, no bid/ask, no spot volume | **Mostly not observable** with the current feeds |
| News (Stage 5) | NFP / CPI / FOMC dates to 2027-12, weekly calendar feed, macro panel | **Partly met.** No PCE or jobless claims; the engine's news filter is off in the frozen config |
| **TP-first probability (§4)** | The engine's `cal_p` / `race_prob` have **no skill** (AUC 0.38–0.52). The "Your trade" panel gives empirical TP-first rates (mostly in-sample) | **Not met.** No validated, calibrated TP-first model exists |
| Three TP profiles (§5) | Measured for +$10 / +$15 / +$20 against −$10 and −$20 (study, B2, B2c, B3, live window) | **Statistics exist; no validated model** |
| Nine-layer approval (§6) | Engine labels BUY / SELL / WAIT / NO TRADE / RISK LOCK / WARMUP | **Partial.** No DATA UNAVAILABLE or MODEL NOT VALIDATED |
| Dashboard panel (§12) | Plan, risk and "Your trade" cards cover about 15 of the 25 fields | **Partial** |
| 30 required tests (§13) | 4 exist, 13 partial, 13 missing | **Partial** |
| 90% gate (§10) | 400 development trials and 600 recorded live decisions | **Not supported by any evidence so far** (§5) |

**The single most important fact for this project:**
- No feature the system has, or that has been tested, moves the TP-first rate more than about **3 points** above random entries.
- At a −$10 stop, random entries reach +$10 / +$15 / +$20 first about **50% / 40% / 33%** of the time.
- A 90% profile at those targets would need 40–57 points of edge. Nothing measured comes within an order of magnitude.
- The engine can be made far more **honest** (calibrated, traceable, able to say NO TRADE). On this evidence it cannot be made 90% accurate at these targets.

---

## 1. Constraints that govern any change

1. **The frozen forward test.**
   - Changing any file in `holdout.ENGINE_SOURCES` or `config.py` restarts web.7.
   - Changing `arm_h2…h6.py` restarts that arm (each arm hashes its own file).
   - The operator's standing instruction (2026-11-01): "No further engine changes, configuration changes affecting the frozen test, or forward-test restarts are authorised without my explicit written approval."
   - So the confirmation engine must be built **beside** the frozen engine:
     - as display code (no key change);
     - as research;
     - or as a **new, separately registered arm**.
2. **Amendment 13 data partitions.**

| Partition | Window | Status |
|---|---|---|
| Development | 2020-01-24 → 2023-01-24 | open |
| Validation | → 2024-06-30 | sealed |
| Holdout | 2024-07-01 → 2025-12-31 | sealed |

   - Validation and the holdout open only with an approved registration (`harness.partition`).
   - **That is the brief's chronological split, already enforced in code.**
3. **One system of record.** Only the website's forward tests count (Amendment 6).
4. **Research rules** (operator's brief of 2026-11-01): no tuning on test data, no cherry-picking, no invented probabilities, every trial logged (`research/trials.jsonl`, 424 records).

---

## 2. Architecture and dependency map

```
EXTERNAL FEEDS                      INGEST (quantum/data)                         ENGINE (frozen, web.7)
Twelve Data XAU/USD 5m/15m/1h/1d ─┐  sources._get: timeout 30 s, 4 tries,       features.py  EMA20/100/200, VWAP d/w/m, ATR, ADX/DMI,
Yahoo XAUUSD=X (fallback 1)       ├─► backoff 1-2-4-8 s, no retry on 4xx          │            RSI, BB, sessions, regimes, macro factors
Yahoo GC=F (fallback 2: futures)  ┘  market.download_all: ONE instrument for all   │            (DXY, US10Y, silver, EUR, SPX, TIPS, VIX, COT, OI)
Yahoo DXY/^TNX/SI/EURUSD/SPX/VIX    intervals; Twelve Data reopen repair          analog.py    analog scan → hit_prob, race_prob, cal_p (P-01: no skill)
FRED TIPS/US2Y, CFTC COT            _fetch_merge → store (market-data branch,      engine.py    scores → gates → vetoes (TQ, EV, P, risk lock)
                                    monthly CSV) → drop off-grid / shut bars       │            → decision label, plan (entry = close, SL, TP1-3)
                                    drop_incomplete: forming bar split off         ▼
                                    build_market: base (closed bars) + htf      ARMS H2-H6 (own freeze keys) → backtest.simulate (Amendment 14 fills)
                                                                                 → holdout.update_ledger (forward-ledger branch, append-only)
DISPLAY / BOOKKEEPING (outside every key)
report.py: payload per timeframe (decision, plan, Kelly sizing on stop + cost, checks, gate sides, arms, cost profiles,
           news, trade_race) → site/data/{5m,15m,1h,4h}.json        notify.py → alerts      manifest.py → data manifest
events.py (Myfxbook RSS), reference.py (gold-api mid; OANDA practice if a token is set), macro_panel.py, mt5.py (MetaApi,
           unconfigured) → site/data/*.json
site/app.js + costs.js: renders; recomputes only viewer-specific numbers (account size, cost profile, "Your trade" inputs)
relay/ (Cloudflare Worker, Finnhub WebSocket): live price chip and live indicator values. Display only; never a signal
SCHEDULE: Cloudflare cron every 15 min (GitHub cron :02/:17/:32/:47 Sun-Fri as backup) → quantum-site.yml
           → tests → pipeline (15m, 1h, 4h, 5m in parallel) → ledgers → Pages deploy; concurrency group, no cancel
```

### Where each important displayed metric comes from

| Displayed | Computed in | From |
|---|---|---|
| Decision (BUY / SELL / WAIT / NO TRADE / RISK LOCK) | `engine.py` (`conf_dir_label`) | closed bars of that timeframe |
| Entry / SL / TP1–3 | `engine.py` plan (entry = the signal bar's close) | regime-scaled ATR, structure levels |
| "Score" P, EV, touch rates | `analog.py` | analog matches; **labelled "not probabilities"** (P-01) |
| Lots | `report.kelly` (Python) and `app.js` (account size, profile) | Kelly on the Wilson lower bound, sized on stop + cost |
| Costs | `cost_profiles.py` and `costs.js` (parity-tested) | frozen model or selected profile (UNVERIFIED) |
| TP-first rates ("Your trade") | `trade_race.py` | stored 5-minute bars; triggers from the engine and arms; random baseline |
| Forward record | `holdout` ledgers → `backtest.metrics` | real-time closed trades |
| Data status / staleness | `market.status` → payload; `app.js freshness()` | last bar close against the clock and the live chip |

---

## 3. Requirement-by-requirement audit

### 3.1 Stage 1 — market data validation

| Brief item | Current behaviour | Gap |
|---|---|---|
| Price is current | The engine runs every 15 min on closed bars. The page shows **OUT OF DATE** when 2 or more bars have closed since, or price has moved 1.5 × ATR (`renderGuard`) | **G1.** The decision is still shown under the banner. There is no engine-level **DATA UNAVAILABLE** |
| Valid timestamps | UTC everywhere; off-grid rows dropped; market-shut bars dropped; Sunday reopen repaired (tested) | — |
| Unexplained gaps | Market-shut gaps removed. Other holes are not flagged in live data (the research and trade-race code skip paths across holes over 3 days) | **G2.** No live missing-bar detector |
| Bid/ask available | **No.** Twelve Data gives a single quote series. gold-api gives a mid only. OANDA practice is supported but no token is set. MetaApi is supported but unconfigured | **G3 (high).** Spread is modelled (session table), never observed |
| Spread within limits | Modelled spread; cost vs ATR check (amber > 15%, red > 25%) is display only | Depends on G3 |
| Correct symbol | One instrument across all intervals; `price_source` in the payload and ledger | **G4.** Fallback 2 is **GC futures** (a different instrument, roughly $20–40 basis). Decisions still run on it, labelled but not blocked |
| Consistent timeframes | `market.align` (last bar opened before the chart close); no look-ahead (7 tests) | — |
| Historical vs live candle | `drop_incomplete`: the forming bar is split off and display only | — |
| Open / closed classification | as above | — |
| Stale, duplicated, out of sequence | `store.merge` dedupes (newer wins) and sorts | **G5.** No tests for duplicates or out-of-order rows |
| Validated fallback | Twelve Data → Yahoo spot → Yahoo GC; the store is used if the live fetch fails ("store (live fetch failed)" in `data_status`) | G4 |
| Record source, timestamp, symbol, price per decision | Payload: `price_source`, `generated_utc`, `last_bar_close`, `data_status`. Ledger: `price_source` | Adequate |
| **Cadence** | Decisions every 15 min (runs at :02 / :17 / :32 / :47, plus about 4 min to build and deploy). A 5m signal can reach the page up to about 3 bars (15–20 min) late | **G6 (high for 5m entries).** For entries that need current prices, the 15-minute batch is a structural limit |

API reliability:
- **In place:** timeouts, exponential backoff, no retry on 4xx, the store as cache, keys redacted, and data status published.
- **Missing:**
  - No `Retry-After` handling.
  - No circuit breaker. This matters little in a 15-minute batch.
  - Twelve Data credit-limit errors arrive as HTTP 200 JSON. They raise `FetchError` and fall back to the store or Yahoo, and the fallback is visible in `data_status`.

### 3.2 Stage 2 — higher-timeframe direction and regime

**Present**
- **Moving averages:** EMA20, EMA100 and EMA200 (`features.py`). **EMA50 is not in the engine** (G7).
- **VWAP:** session, week and month.
- **Structure:** pivots, BOS / CHoCH / MSS events.
- **Trend strength and volatility:** ADX / DMI, and the ATR percentile.
- **Regime, per timeframe:** ABNORMAL / COMPRESS / EXPANSION / STRONG TR / WEAK TR / RANGE.
- **Bias, per timeframe:** BULL / BEAR / RANGE.
- **Higher timeframes:** scores read from closed higher-timeframe bars only.

**Gaps**
- **G8.** The brief's eight classes are not one-to-one with these. "Potential reversal" maps to the auction rejection state; there is no single "uncertain / conflicting" class.
- **Strategy-to-regime suitability is unmeasured.**
  - Regimes scale the SL, horizon and size; nothing tests whether a strategy has an edge in a regime.
  - The one regime test so far, volatility-tercile momentum (B1), was **rejected**.
  - B3's 1h trend filter changed the success rate by **−1.2 points** against random entries filtered the same way.

### 3.3 Stage 3 — entry confirmation

- **Existing gates:** trend threshold, trade-quality floor, EV veto, calibration veto, risk lock, plus the arms' rules.
- **The brief's test (incremental predictive value) has been run** for the main confirmation families:
  - **B2 / B2b / B2c:** nine SMC setups.
  - **B3:** 1h trend alignment, a confirmation entry, sweep → MSS → FVG sequences.
- **Result:** every family is within about ±3 points of random entries given the same treatment. 0 of 400 trials pass.
- **Not yet tested:**
  - distance to the next opposing level;
  - "extended move" / entry-overshoot filters;
  - candle-body strength;
  - VWAP position;
  - ATR-normalised momentum as model features.

  These are natural inputs to the TP-first model (§6, step B), tested as features rather than as hand-set gates.

### 3.4 Stage 4 — microstructure and liquidity

**Observable today**
- bar ranges and gaps;
- session;
- modelled spread;
- swept levels (prior day / week, equal highs and lows);
- price relative to pools.

**Not observable**
- order book;
- real bid/ask;
- spot tick volume. Twelve Data spot has none; GC futures volume is used and labelled as such.

`mt5.py` labels its footprint as a "tick-rule proxy" (tested). **G9:** any Stage 4 output must say *inferred*. The site must not claim knowledge of order flow, hidden liquidity or stop locations, and today it does not.

### 3.5 Stage 5 — news and macro

**In place**
- **Calendar:** 38 official NFP / CPI / FOMC dates to 2027-12-10 (`news_calendar.py`), plus the weekly feed (Myfxbook calendar and news).
- **News window (±30 min):** costs ×3 in sizing, an alert once per window, and a banner.
- **Macro panel:** DXY, US10Y, silver, EURUSD, SPX, TIPS real yield, VIX, US2Y, COT, open interest. Correlation-based and display only.

**Gaps**
- **G10.** No PCE or jobless claims / unemployment dates.
- **The engine's news filter is OFF** (Pine default, frozen config). A news restriction can only be applied by a new layer outside the engine, which is allowed as display or as a new arm.

### 3.6 TP-first probability model (§4 of the brief, the central requirement)

| Piece | State |
|---|---|
| Barrier labels (TP first / SL first / neither / ambiguous) | **Exist in research:** `harness.simulate` (WIN / LOSS / AMBIGUOUS / TIMEOUT) and `b2.Paths` (level or gapping-open fills; ties = LOSS unless the bar opened beyond the target; open at horizon) |
| Ambiguity resolved on a lower timeframe | Partly: decisions are walked on 5-minute or 15-minute paths. No tick data (Dukascopy is used only to cross-check; it may not be stored publicly) |
| Chronological validation, purging, embargo | **Exist:** partitions, `purged_folds`, PBO / CSCV, Deflated Sharpe, Reality Check, Benjamini-Hochberg, registry |
| Logistic / gradient-boosted / random-forest / regime / survival models | **Not built** |
| Calibration (Platt, isotonic, reliability, Brier, ECE) | **Not built.** The engine's `cal_p`: Brier skill −0.03 to −0.31; AUC 0.38–0.52 |
| Probability shown on the site | Scores, labelled "not probabilities". The "Your trade" panel shows empirical TP-first rates with Wilson ranges against random (in-sample except the recorded-forward row) |

**G11 (critical).** There is no model of P(TP before SL | information at entry) validated out-of-sample. Building one is the main work of Phase 4/5 (§6).

### 3.7 Contract specification and money maths (§2 D)

- **Assumed:** 1 lot = 100 oz; tick 0.01; $1 of price = $100 per lot; commission $7 per lot round trip (engine). Five prop-firm profiles are marked UNVERIFIED. Account currency is USD. There is no pip-convention field.
- **G12 (blocker for "exact").** The operator's MT5 symbol specification has never been obtained: contract size, tick size, tick value, digits, account currency, commission, swap.
- **Consequence for Scenario D.** On a 100 oz contract, $1,000 at 0.50 lot is a **$20** move (2,000 points at 0.01, or 200 "pips" at the common 0.10 pip). It is **not $10–15**. $10–15 would equal $1,000 only on a contract of 133–200 oz, or at 0.67–1.0 lot. The brief rightly forbids assuming this. The spec is needed.

### 3.8 Approval layers (§6) and decision labels

| Brief layer | Exists today as | Gap |
|---|---|---|
| 1 Data quality | page banner (display) | engine still decides (G1, G4) |
| 2 Regime suitability | regime multipliers only | no measured suitability (G8) |
| 3 Directional evidence | scores, gates | no measured skill (§4) |
| 4 Entry quality | TQ floor; H4 entry overshoot (display) | — |
| 5 Target feasibility | nearest levels shown; plan TPs from structure | not used as a gate |
| 6 Probability validation | calibration veto on an uncalibrated P | G11 |
| 7 Execution | modelled cost vs ATR (display) | G3 |
| 8 Risk | risk lock (daily −3 R, 12% drawdown), Kelly to 0 with no edge | adequate |
| 9 Final | BUY / SELL / WAIT / NO TRADE / RISK LOCK / WARMUP | **no DATA UNAVAILABLE or MODEL NOT VALIDATED** |

### 3.9 Dashboard (§12)

**Already shown** (about 15 of 25 fields):
- current price, data source, freshness;
- regime and bias per timeframe;
- direction; entry, SL, TP; lot size;
- SL distance;
- cost and spread (modelled);
- ATR;
- news status;
- rejection reasons (veto names);
- last update.

**The "Your trade" card adds:**
- custom TP / SL / lot;
- break-even win rate;
- net if TP / if SL;
- TP-first rate with Wilson range per source, against random.

**Missing:**
- one consolidated high-confidence panel;
- profile selectors for TP $10 / $15 / $20;
- a **calibrated** TP-first probability with its interval;
- model status;
- expected holding time;
- the "confirmation status" wording.

### 3.10 Code audit items (§7)

| Item | Finding |
|---|---|
| Look-ahead / repainting | Covered: 7 no-look-ahead tests; closed bars only; the forming bar is display only |
| Duplicated calculations | Sizing is computed in Python and again in JS (needed: the account size is a viewer input). Costs are parity-tested; **sizing has no JS ↔ Python parity test (G13)** |
| Dead code | Python: 1 unused import (`arm_h4.py`), 1 unused variable (`arm_h2.py`). **Do not remove:** both files are hashed into their arms' freeze keys, so removing either restarts those forward tests. Pine dead code is tracked by `deadcode.py` |
| Hard-coded contract assumptions | 100 oz per lot in `config.point_value` (frozen) and `costs.js` `OZ` (G12) |
| Race conditions | Workflow concurrency group, no cancel; ledgers append-only; documented in `audit/CONCURRENCY_AND_MIGRATION.md` |
| Data leakage / overfitting | Partition guard; research never imported by production (tested) |

### 3.11 Required tests (§13): 4 exist, 13 partial, 13 missing

| # | Test | Status | Existing coverage |
|---|---|---|---|
| 1 | Stale market data | partial | `test_stale_by_age_or_trend` (signal staleness); page guard has no test |
| 2 | Missing candles | partial | shut-bar and hole handling; no live detector |
| 3 | Duplicate candles | **missing** | `store.merge` dedupes, untested |
| 4 | Incorrect timestamps | partial | off-grid rows, daily break |
| 5 | API rate limits | **missing** | — |
| 6 | Primary API failure | partial | `test_live_pipeline_offline` |
| 7 | Fallback API failure | **missing** | — |
| 8 | Incorrect contract specification | **missing** | no spec model |
| 9 | Lot size | exists | `test_lots_by_hand_with_costs`, minimum lot, cap |
| 10 | Tick value | **missing** | no tick-value concept |
| 11 | SL/TP conversion | partial | `costs.test.mjs` (dollars ↔ price at 100 oz) |
| 12 | Spread widening | partial | news multiplier |
| 13 | Slippage | partial | cost tests |
| 14 | High-impact news | exists | calendar, DST, alert once |
| 15 | Conflicting timeframes | **missing** | — |
| 16 | Sideways markets | **missing** | — |
| 17 | Volatility expansion | **missing** | — |
| 18 | Repainting | partial | truncation identity tests |
| 19 | Look-ahead | exists | 7 tests |
| 20 | Future-data leakage | partial | `SealedPartition`, research import guard |
| 21 | Ambiguous TP/SL bar | exists | `test_stop_counts_first…`, `test_fills_level_gap_tie_and_open` |
| 22 | Insufficient observations | **missing** | — |
| 23 | Calibration failure | **missing** | — |
| 24 | Model drift | **missing** | — |
| 25 | Dashboard ↔ engine mismatch | partial | costs parity, `gate_sides`, trade-race = study |
| 26 | Missing risk limits | partial | risk lock in the engine |
| 27 | Zero / invalid prices | partial | zero-R race, NaN open |
| 28 | Account currency | **missing** | USD assumed |
| 29 | Out-of-order data | **missing** | — |
| 30 | Repeated / duplicate signals | partial | ledger dedupe, `forward_triggers` dedupe |

---

## 4. Phase 2 baseline (executed today)

### 4.1 Tests

| Suite | Result |
|---|---|
| `python -m pytest -q tests` | **245 passed** |
| `node --test tests/costs.test.mjs` | 6 passed |
| `node --test tests/relay.test.mjs` | 7 passed |
| `node --test tests/scheduler.test.mjs` | 4 passed |
| CI on the deployed commit (run 2286) | passed |

### 4.2 Out-of-sample record (the system of record)

**web.7** (current key, since 2026-10-31 17:23 UTC): **0 closed trades**. The market closed for the weekend shortly after the start, so there is no web.7 baseline yet.

**web.6** (previous key, 2026-10-17 → 31, archived), `audit/tools/forward_stats.py`:

| Ledger | n | Win % [Wilson 95%] | Mean R [bootstrap 95%] | t | PF |
|---|---|---|---|---|---|
| 5m H4 playbook | 511 | 33.5 [29.5, 37.7] | −0.179 [−0.251, −0.104] | **−4.75** | 0.58 |
| 15m H4 playbook | 171 | 38.6 [31.6, 46.1] | −0.092 [−0.210, +0.033] | −1.50 | 0.76 |
| 1h H4 playbook | 49 | 32.7 [21.2, 46.6] | −0.187 [−0.360, −0.004] | −2.06 | 0.55 |
| 5m treatment | 8 | 50.0 [21.5, 78.5] | +0.938 | +1.05 | 3.17 |
| 5m H3 | 14 | 64.3 [38.8, 83.7] | +0.553 | +1.11 | 3.69 |
| All other ledgers | 1–12 each | — | — | — | — |

The only ledger with significant evidence (5m H4) is significantly negative. The small positive ledgers have n ≤ 14 and intervals that include zero.

Every calibration check of the recorded P returned **NOT ASSESSABLE**: no ledger has 10 or more trades with a recorded P.

### 4.3 TP-first baseline for the brief's profiles

Re-run today on the latest data (`audit/tools/target_move_study.py`; it reproduces the stored study except about 8 H4 triggers from revised bars). Window: stored 5-minute paths, 2026-09-09 → 10-30, one trading day.

| Profile at 0.5 lot (100 oz) | Break-even after costs | Recorded live decisions (n 600) | Random long / short, same window | Best in-sample source, n ≥ 100 |
|---|---|---|---|---|
| A: SL −$10, TP +$10 | 54–55% | **44.8%** [40.9, 48.8] | 43.3% / 56.2% | 59.5% (5m engine; 95% shorts; random short 56.2%) |
| B: SL −$10, TP +$15 | 43–44% | **34.8%** [31.1, 38.7] | 32.7% / 45.7% | 50.5% (same) |
| C: SL −$10, TP +$20 | 36–37% | **28.8%** [25.4, 32.6] | 27.1% / 39.1% | 43.2% (same) |
| D: SL −$20, TP +$20 | 52% | **47.0%** [43.0, 51.0] | 43.1% / 55.5% | 56.3% (same) |

**On development data (2020-01-24 → 2023-01-24), 400 trials:**

| Profile | Random entries | Best of 9 setups | Best of 210 B3 combinations | Pass the rule |
|---|---|---|---|---|
| A (+$10 / −$10) | ~50% | 51.6% | 57.1% (n 84) | none |
| B (+$15 / −$10) | ~40% | 42.9% | 48.6% (n 37) | none |
| C (+$20 / −$10) | ~33% | 35.8% | 43.5% (n 23) | none |
| D (+$20 / −$20) | ~50% | 52.6% | — | none |

- The B3 maxima are small-sample luck: each one's 95% interval includes random.
- Details: `B2_…`, `B2B_…`, `B2C_…` and `B3_DEVELOPMENT_RESULTS.md`.

---

## 5. The 90% gate on today's evidence

- **For a model to label a subset 90% TP-first at a −$10 stop**, that subset must win **+$10 first 9 times in 10**, against a base rate of about 50%.
- **The precision bar is set.** The brief's gate and research doc `09` §4 both require n ≥ 184 for a 90% claim with an 85% lower bound, on data not used to build the model.
- **Nothing measured comes close.**
  - The best improvement found anywhere is about **+3 points** over random.
  - Across 400 trials, the largest observed gaps are within what luck explains.
- **Where 90% is easy, it is unprofitable.**
  - A 90% success rate appears only when the stop is wide relative to the target. For example, +$10 before −$90 succeeds about 90% of the time even at random.
  - That buys win rate with risk: the break-even rises to match, and costs make it negative.
- **Honest expectation for the brief's model.**
  - A calibrated TP-first model will most likely output probabilities close to the base rates (about 50 / 40 / 33%) with a narrow spread.
  - The engine will then say **NO TRADE / MODEL NOT VALIDATED** almost always.
  - That is the correct, honest behaviour the brief's acceptance criteria ask for (items 8–10). It is not a failure of the code.
- **This is a forecast from evidence, not a result.** The model has not been built yet, and §6 builds and tests it properly.

---

## 6. Findings ranked by impact (Phase 3 input) and the proposed plan (Phase 4 design, not started)

| Rank | Finding | Impact | Evidence |
|---|---|---|---|
| 1 | **G11:** no validated, calibrated TP-first model; the engine's P has no skill | critical | AUC 0.38–0.52; Brier skill < 0 |
| 2 | **No measured edge in any tested confirmation family** | critical (sets expectations) | 400 trials; 600 live decisions |
| 3 | **G12:** broker contract specification unknown; Scenario D's "$10–15 = $1,000 at 0.5 lot" does not hold on a 100 oz contract | high | config; arithmetic |
| 4 | **G3:** no bid/ask; spread is modelled | high | feeds audited |
| 5 | **G1 / G4:** no DATA UNAVAILABLE; futures fallback used for decisions | high | `pipeline`, `market` |
| 6 | **G6:** 15-minute cadence for 5m entries | high (for 5m) | schedule |
| 7 | **G10:** no PCE or jobless claims; engine news filter off | medium | `news_calendar` |
| 8 | **G7 / G8:** no EMA50; regime classes not the brief's; suitability unmeasured | medium | features; B1 / B3 |
| 9 | 13 of the 30 required tests missing, 13 partial | medium | §3.11 |
| 10 | **G13:** no JS ↔ Python sizing parity test; 2 lint items that must not be "fixed" (they are in freeze-key files) | low | ruff |

### Proposed plan, in reviewable steps

None of these steps is started; each waits for the operator's go-ahead.

**Step A — display and data layer** (no freeze key changes)
- **Contract model.** A `contract.py` module holding the broker spec: contract size, tick size, tick value, digits, account currency, commission. Defaults are labelled UNVERIFIED until the operator's MT5 spec is entered.
- **Profit and loss in money.** All dollar ↔ price ↔ pip maths goes through `contract.py` (tests 8, 10, 11, 28).
- **New decision statuses.** DATA UNAVAILABLE, MODEL NOT VALIDATED and INSUFFICIENT EVIDENCE.
  - They come from data checks: stale, holes, duplicates, out-of-order, zero or invalid prices, futures fallback.
  - They **override what the page shows, not what the engine records.**
- **The high-confidence panel.** Profile selectors for $10 / $15 / $20 / custom, built on the "Your trade" card.
- **Bid/ask source.** If the operator adds a free OANDA practice token, `reference.py` already reads OANDA's bid/ask.
- **Calendar.** PCE and jobless-claims dates.
- **Tests.** The 13 missing tests and the 13 partial ones completed.

**Step B — research** (declared before running; development data only)
- **Labels.** Barrier labels for profiles A–D at each decision bar.
- **Features.** The engine's own outputs, plus the untested Stage 3 candidates (distance to the next level, extension, body strength, VWAP position, ATR-normalised momentum, session, news proximity).
- **Models.** Logistic regression (baseline) against gradient-boosted trees, compared with random forest and a regime-conditioned empirical table.
- **Validation and calibration.** Purged walk-forward inside development. Calibration by Platt / isotonic. Reported with Brier, log loss, ECE and reliability tables.
- **Gate.** The decision threshold is set on development folds only, before any validation data is seen.

**Step C — one validation run** (needs an approved registration under Amendment 13)
- **The run.** The frozen Step B model is evaluated once on 2023-01 → 2024-06.
- **If it passes the predeclared gate:** it becomes a **new forward arm in shadow mode**, with its own freeze key. web.7 stays untouched. The holdout is opened once, at the end.
- **If it does not pass:** the panel keeps saying MODEL NOT VALIDATED, and the report states the strongest supported profile.

### Decisions needed from the operator before Step A / B

1. **MT5 symbol specification** for XAUUSD at your broker. In MT5: Market Watch → right-click XAUUSD → Specification, then send:
   - contract size, tick size, tick value, digits;
   - account currency;
   - commission per lot;
   - a typical spread.

   No password is needed.
2. **Bid/ask feed (optional, free).** An OANDA practice API token, as a GitHub secret. Without it, spreads stay modelled and labelled as such.
3. **Where the engine lives.**
   - (a) **Recommended:** a display panel plus research model now, and a new arm only after validation. No restart.
   - (b) Change the frozen engine. This restarts web.7 and is not recommended.
4. **Approval of Step A**, which is display-only. Steps B and C come back to you with their declarations before they run.
5. **Merge of the pending B3 research branch** (`b4f82240f`), which is not yet merged.


---

## 7. Step A delivered (2026-11-01, operator approval)

Display only. No file in `ENGINE_SOURCES`, no arm file and no config value changed: the engine code hash is still
`60bb01794d03c9ac`. See `docs/PLATFORM.md`, "web.7 + high-confidence panel (Step A)".

| Gap | Status after Step A |
|---|---|
| G1 no DATA UNAVAILABLE | **closed** on the panel. The engine record is unchanged by design |
| G2 missing-bar detector | **closed** (last 20 bars block, older bars degrade) |
| G4 futures fallback used for decisions | **closed** on the panel: DATA UNAVAILABLE |
| G5 duplicates / out-of-order untested | **closed** |
| G10 PCE / jobless claims | **partly closed**: the panel blocks on the weekly feed's high-impact events, which include them. The official dated list still covers only NFP / CPI / FOMC |
| G11 no validated TP-first model | **open** (Steps B / C). The panel says MODEL NOT VALIDATED and never confirms without one |
| G12 contract specification | **tooling closed** (spec module, validation, editor on the page). **Data open**: needs the operator's MT5 specification |
| G3 bid/ask, G6 cadence, G7 EMA50, G8 regime classes | open. G3 needs a feed (OANDA practice token); G7 / G8 would change the frozen engine |

**Required tests after Step A: 25 exist, 4 partial, 1 missing.**

| # | Test | Status |
|---|---|---|
| 1–17 | all | exist (`test_confirm.py`, `test_contract.py`, cost and news tests) |
| 18 | repainting | partial (closed-bar identity tests; the panel reads closed bars only) |
| 19 | look-ahead | exists |
| 20 | future-data leakage | partial (partition guard, research import guard) |
| 21–22 | all | exist |
| 23 | calibration failure | partial: the gate is tested (nothing confirms without a validated model); the calibration procedure itself is Step B |
| 24 | model drift | **missing**: there is no model to drift until Step C |
| 25–29 | all | exist (JS ↔ Python parity tests, risk-state, prices, currency, order) |
| 30 | repeated signals | partial (ledger and forward-trigger dedupe) |

**Mutation check of the new tests.** Six planted bugs in `confirm.py` were all caught, after one test was added:
- the original suite missed a bug that used the point estimate instead of the 95% lower bound for the 90% gate;
- the added case covers it: a 92% point estimate on n = 200, whose lower bound is 87.5%, must be NO TRADE.
