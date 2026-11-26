# XAUUSD Quantum — third-party audit pack (2026-11-26)

**Purpose.** On 2026-11-26 the operator asked for a list of every feature built so far, so that a third party can
audit it, verify it and run a gap analysis that improves its validity. This document is that list. It gives:
- each feature's code, tests, basis (registration or amendment) and evidence;
- each feature's status, and how an auditor checks it;
- the live records as of today;
- the commands an auditor runs, with the results measured today;
- a prioritised gap analysis.

**Baseline audited**

| Item | Value |
|---|---|
| Repository | `fmve1232/trading-view-xauusd` (public) |
| Production branch | `claude/audit-prompt-real-artefacts-nekqv6`: the repository's default branch, which the scheduler dispatches |
| Production commit | `505f05ecc` (merge of PR #140, 2026-11-25) |
| Engine freeze key | `1f88aad357497da4:4440d52587f5cc6b`, frozen since 2026-11-15 11:46:48 UTC (web.8 + Amendment F) |
| Records read | `forward-ledger` at 2026-11-26 07:33 UTC; `market-data` at 07:33 UTC |
| Pack written on | branch `claude/session-01fdjaothuvhxscxtl7ysa-y3n4w4-audit-pack` (not merged) |

**Labels used below**

| Label | Meaning |
|---|---|
| MEASURED | executed today, and the result is shown |
| RECORDED | read from a committed record, not recomputed |
| ASSUMED | a value nobody has verified (for example the broker's commission) |
| NOT RUN | not executed in this pack |

Nothing is called validated, calibrated or PASS unless it was executed and the evidence supports it.

**What this pack does not claim.**
- No entry rule in this system has shown a positive expectancy after costs out of sample.
- Every directional phone message says so: "RECORD — NOT A VALIDATED SIGNAL — NO TRADE", or "Entry: Not validated".
- The auditor should take this as the system's own finding, not as a disclaimer added for form.

---

## 1. Summary for the auditor

1. **Production** is a Python port of a frozen Pine engine. It runs every 15 minutes on GitHub Actions:
   - it downloads prices;
   - it runs the engine and seven forward-test arms;
   - it publishes a GitHub Pages site;
   - it sends non-directional monitoring alerts (breakouts, sweeps, key zones) to the operator's phone through ntfy.
   - Its records go to an append-only branch.
2. **The forward test** has run under one freeze key since 2026-11-15.
   - No arm has reached a registered decision point.
   - Two H4 Playbook ledgers are negative with 95% intervals that exclude zero: 5m, 404 trades, −0.138 R; 1h, 37 trades, −0.308 R.
3. **Research.** About 40 studies, each declared or registered before it ran (B1 – B31, B31b-W1 – W13), tested entries on 2020–2023 development data, some also on 2023–2025.
   - None found an entry that beats matched random entries after costs.
   - The closest is session continuation at the London / New York open (W13 rank 1): −0.001 R per trade (95% −0.073 to +0.070), negative at 1.5× cost.
4. **The 2023–2025 history is not untouched.** B10, B13, B19, B20–B23, B30 and B31 read the validation and holdout periods (B31's own registration says so). The only unseen test data is the forward period.
5. **Trial records are split.**
   - The production `research/trials.jsonl` has 1,560 lines.
   - Across all branches there are 4,045 distinct trial records.
   - Several studies log one line for many mechanisms (W13: 50 in one line).
6. **Costs are not broker-verified.**
   - Spreads read from the operator's MT5 screenshots: $0.45–0.52 in Asia; about $0.80 at 20:55 UTC near the New York close (one reading).
   - The model uses $0.30.
   - Commission and contract size are ASSUMED.
7. **Phone delivery** is proven only to the ntfy server.
   - 365 of 367 sends since 15 Nov ended "DELIVERY_UNCONFIRMED", the success state by design.
   - 2 were lost to HTTP 429 (rate limit) on 22 Nov 23:52 UTC.
8. **The live sweep and breakout outcome records are not durable.**
   - They hold at most 300 entries each.
   - They live in a branch that is replaced every run.
   - The registered "100 decided per timeframe" check therefore cannot be reached on H1 / H4 at the current rates.
9. **Today's checks (local runs, not GitHub CI):**
   - 1,077 Python tests passed;
   - 20 JavaScript tests passed;
   - the seven Pine checkers are clean;
   - the frozen-file manifest is 7 of 7 OK;
   - the freeze key is unchanged.
   - The latest 40 production runs on GitHub succeeded.
10. **The 26 gaps (GA-01 … GA-26) are in section 7.** The first six affect whether any result here can be trusted.

---

## 2. How the system runs

```
Cloudflare Worker (scheduler/worker.js)  -- dispatch at :01:55 :16:55 :31:55 :46:55, Sun 22:00 -> Fri 21:00 UTC,
                                            plus the slot after each daily / weekly close (PR #139)
GitHub cron (quantum-site.yml)           -- backup; stands down within 900 s of a dispatched run
        |
        v
quantum-site.yml
  unit-test gate      full suite on the first run of each UTC day / commit / runner image
  data                Twelve Data spot XAU/USD 5m 15m 30m 1h (4h built from 1h on the 17:00 New York grid);
                      Yahoo GC=F SI=F DX-Y.NYB EURUSD=X ^TNX ^GSPC ^VIX; FRED; CFTC
  store               market-data branch (ONE orphan commit, replaced every run; month files)
  engine              quantum/engine.py + features.py + analog.py + ta.py + sessions.py (frozen by the freeze key)
  arms                treatment, control, challenger, H2, H3, H4, H5 (H6 closed) on 5m 15m 30m 1h 4h
  monitors            breakouts (M15 M30 H1 H4), sweeps (every 15m close), key zones, entry intel, C1 confirmation,
                      confirmation panel, B31b shadow
  alerts              notify.py -> ntfy (Telegram / Discord optional) + delivery log; MT5_PRICE_OFFSET on prices
  records             forward-ledger branch (normal commits, never force-pushed; 312 commits); payload artifacts (90 days)
  site                report.py -> index.json -> GitHub Pages; deployment smoke test
```

---

## 3. Feature register

Column guide:
- **Tests**: collected test count for the file (`pytest --collect-only`, today).
- **Basis**: the registration, amendment or operator decision the feature rests on.
- **Status**:
  - LIVE: runs in production;
  - LIVE-DISPLAY: runs, website only;
  - LIVE-PHONE: runs, sends to the phone;
  - OFF: present, switched off;
  - CLOSED: kept read-only;
  - RESEARCH: never imported by production;
  - BRANCH: not on the production branch.

### 3.1 Data and scheduling

| ID | Feature | Code | Tests | Basis | Status | How to verify |
|---|---|---|---|---|---|---|
| A-01 | Scheduler: 15-minute dispatch, close slot | `scheduler/worker.js`, `scheduler/wrangler.toml` | `scheduler.test.mjs` 5 | PR #139 (`runSlot(d) = !goldShut(d) \|\| !goldShut(d − 2 min)`) | LIVE | `node --test tests/scheduler.test.mjs`; the Actions run list shows runs at :x1:55 / :x6:55 |
| A-02 | Backup cron and its stand-down gate | `.github/workflows/quantum-site.yml` | `test_site_gate` 9 | R15 design; PR "gate-15min" | LIVE | test file; run list shows no duplicate run within 15 min |
| A-03 | Gold bars (Twelve Data spot) | `quantum/data/sources.py`, `quantum/data/market.py` | `test_engine` 41, `test_live_path` 9, `test_tf30` 4 | `docs/PLATFORM.md` D-09, D-10 | LIVE | tests; `market.py` aligns without look-ahead (`test_engine::test_no_lookahead`) |
| A-04 | Auxiliary and macro series | `sources.py`, `market.py` | `test_macro_factors` 3 | D-05 (COT on its Friday release), D-07 (COMEX GC volume as proxy), D-10 | LIVE | test file; `docs/PLATFORM.md` parity table |
| A-05 | Market-data store | `quantum/data/store.py`; branch `market-data` | via engine tests | PREREGISTRATION A4 | LIVE | `git rev-list --count origin/market-data` = 1 (replaced every run, by design) |
| A-06 | Price cross-check, Twelve Data vs Dukascopy | `audit/tools/xcheck_dukascopy.py`; `xcheck-dukascopy.yml` | `test_xcheck` 10 | data-integrity audit | LIVE (scheduled) | workflow runs; test file |
| A-07 | Reference prices (OANDA, optional) | `quantum/reference.py` | — | web.4 + validation | LIVE-DISPLAY when keys are set | panel hidden without keys |
| A-08 | MT5 broker feed through MetaApi | `quantum/mt5.py` | `test_mt5` 6 | web.4 + MT5 | **OFF: not connected** (no account set) | `METAAPI_*` unset; panel hidden |
| A-09 | Live tick chip (relay) | `relay/worker.js` | `relay.test.mjs` 7, `test_relay` 3 | web.3 + stream | LIVE-DISPLAY | `node --test tests/relay.test.mjs` |
| A-10 | Research history download | `quantum/research/history.py`; `research-history.yml`; branch `research-data` | `test_research_history` 7 | Amendments 11 and 13 | RESEARCH | branch holds TD XAU/USD 15min / 1h / 5min and EUR/USD 15min; one orphan commit (force-pushed) |

### 3.2 Engine and forward-test arms

| ID | Feature | Code | Tests | Basis | Status | How to verify |
|---|---|---|---|---|---|---|
| B-01 | Master engine port: structure, liquidity, FVG / OB, volume profile, sessions, HTF scores, macro, analog engine, scores, gates | `engine.py` (1,745 lines), `features.py`, `analog.py`, `ta.py`, `sessions.py`, `config.py` | `test_engine` 41, `test_ta` 17, `test_independent_math` 14, `test_engine_reference_levels` 9, `test_pine_v92_port` 8 | PREREGISTRATION §7; Amendments 7, 9 and F; deliberate differences D-01 … D-15 | LIVE (frozen) | tests; `docs/PLATFORM.md` lists every deliberate difference; any other is a bug |
| B-02 | Freeze key and forward holdout | `quantum/holdout.py` (`ENGINE_SOURCES`, `freeze_key`) | `test_integrity` 16, `test_engine_forward` 8 | PREREGISTRATION §7 | LIVE | `python -c "from quantum import holdout, config; print(holdout.freeze_key(config.Config()))"` |
| B-03 | Gap-aware fills (a bar opening through the stop fills at its open) | `quantum/backtest.py` | `test_backtest_gaps` 23 | Amendment 14 (web.7) | LIVE (frozen) | tests; `audit/tools/mutation_gaps.py` |
| B-04 | Treatment, Control, Challenger arms | `engine.py` arms; `backtest.py` | `test_engine`, `test_gate_sides` 2 | §7; Amendment 3 | LIVE | ledgers `holdout/<tf>_{treatment,control,challenger}.json` |
| B-05 | H2 "Sweep and Value" | `quantum/arm_h2.py` | `test_h2` 11 | Amendment 5 | LIVE-DISPLAY | ledgers `holdout/<tf>_h2.json` |
| B-06 | H3 "Sweep-to-Value" | `quantum/arm_h3.py` | `test_h3` 13 | Amendment 7 §3 | LIVE-DISPLAY | `holdout/<tf>_h3.json` |
| B-07 | H4 "Playbook" (nearest liquidity level as trigger, next levels as targets) | `quantum/arm_h4.py` | `test_h4` 5, `test_h4_display` 3 | Amendment 8 | LIVE-DISPLAY | `holdout/<tf>_h4.json`; `audit/tools/h4_outcome_audit.py` |
| B-08 | H5 "High confidence" (all layers agree) | `quantum/arm_h5.py` | `test_h5` 5 | Amendment 10 | LIVE-DISPLAY | `holdout/<tf>_h5.json` |
| B-09 | H6 "No score veto" | `quantum/arm_h6.py` | `test_h6` 7, `test_amendment_f` 8 | Amendments 12 and F | CLOSED (final record shown) | ledgers keep the pre-F key (see GA-21) |
| B-10 | Strategy-twin backtest for the site's records | `quantum/backtest.py` | `test_backtest_gaps`, `test_signal_record` 6 | §7 | LIVE | tests |

### 3.3 Monitors and display panels (non-directional or display only)

| ID | Feature | Code | Tests | Basis | Status | How to verify |
|---|---|---|---|---|---|---|
| C-01 | Breakout monitor M15 / M30 / H1 / H4 (DETECTED, CONFIRMED, RETEST, FAILED, MOVE +$10 / +$15 / +$20) | `quantum/breakouts.py` | `test_breakouts` 36 (incl. no look-ahead) | `B31b-W7.json` + A1, A2 | LIVE-PHONE (`ALERT_BREAKOUTS`) | tests; W7 study: detection exact on 2020–23 |
| C-02 | Sweep monitor on every 15m close (M15 levels; M30 / H1 / H4 swing, equal and range levels) | `quantum/sweeps.py` | `test_sweeps` 30 | W7 amendment A3 | LIVE-PHONE (`ALERT_SWEEPS`) | tests; replay of 17–20 Nov: 29 sweeps |
| C-03 | Sweep context lines: session boundary, run into the sweep, H1 trend, previous-day TPO POC, DXY and US 10Y 1-hour change | `sweeps.context`, `sweeps.context_lines`, `sweeps.macro_from_store` | in `test_sweeps` | W7 amendment A4; PR #140 | LIVE-PHONE (display only) | replay: every breakout message identical, SWEEP messages identical apart from the added lines |
| C-04 | Key zones and structure | `quantum/keyzones.py` | `test_keyzones` 18 | Workstream 4 | LIVE-PHONE (`ALERT_ZONES`, at most 4 a day) | tests |
| C-05 | Entry Price Intelligence (entry check, path record) | `quantum/entry_intel.py` | `test_entry_intel` 34 | Workstream 5 | LIVE-DISPLAY | tests (incl. run-by-run = one pass) |
| C-06 | C1 confirmation: a $10 confirming close before an entry is offered; plan, $650 risk, GAP RISK line | `quantum/confirm_entry.py` | `test_confirm_entry` 40 | operator directive 2026-11-15 | LIVE (record `CONFIRM-LIVE.json`) | tests; record counts in §4 |
| C-07 | Two-stage confirmation panel (trigger → $15 / $20 → plan, verdict) | `quantum/confirm_panel.py` | `test_confirm_panel` 79 | PR #90 option A | LIVE-DISPLAY | tests (no look-ahead on every prefix) |
| C-08 | Data-quality checks and nine-layer approval | `quantum/confirm.py` | `test_confirm` 33 | Step A (high-confidence brief) | LIVE-DISPLAY | tests |
| C-09 | B31 five-module shadow test | `quantum/shadow.py` | `test_shadow` 16 | `B31b-SHADOW-FWD.json` | LIVE (records only, no alerts) | `research_forward/B31b-SHADOW-FWD.json` |
| C-10 | B24 confirmation forward recorder | `quantum/fwd_b24.py` | `test_fwd_b24` 29 | `B24-CONFIRM-FWD*.json` | **OFF** (`FWD_B24` never set); voided start kept | `research_forward/B24-CONFIRM-FWD.void-*.json` |
| C-11 | "Your trade" panel (TP-before-SL frequencies per source vs random) | `quantum/trade_race.py` | `test_trade_race` 10 | web.7 | LIVE-DISPLAY | tests |
| C-12 | Macro panel (DXY, EUR/USD, JPY/USD, US10Y, WTI, BTC) | `quantum/macro_panel.py` | `test_macro_panel` 7 | web.5 / web.6 | LIVE-DISPLAY | tests |
| C-13 | Economic events and NFP / CPI / FOMC calendar | `quantum/events.py`, `quantum/news_calendar.py` | `test_pine_v92_port` | web.3 + news; Pine v86 / v92 | LIVE-DISPLAY | tests |
| C-14 | Contract specification and cost profiles | `quantum/contract.py`, `quantum/cost_profiles.py`, `site/costs.js` | `test_contract` 12, `test_cost_profiles` 4, `test_cost_record` 7, `costs.test.mjs` 8 | Step A; IA-06; D-13 | LIVE-DISPLAY (100 oz per lot ASSUMED) | tests |
| C-15 | Operator's level rules as SETUP records | `notify.py` setup functions | `test_setup_live` 8, `test_setup_rules` 3 | B16 – B18 | LIVE (record `SETUP-LIVE.json`; phone only in `ALERT_MODE=all`) | record counts in §4 |

### 3.4 Phone alerts and delivery

| ID | Feature | Code | Tests | Basis | Status | How to verify |
|---|---|---|---|---|---|---|
| D-01 | Alert streams and modes (`ALERT_MODE` default "sixty"; breakouts, sweeps, zones, C1 entries, daily report) | `quantum/notify.py` (3,289 lines) | `test_alert_sixty` 3, `test_alert_quality` 5, `test_signal_status` 3 | operator choices of 6 Nov and later | LIVE-PHONE | `audit/tools/inventory.py`: 47 of 47 switches passed |
| D-02 | $650 plan: sized from `ACCOUNT_USD` × `PLAN_RISK_PCT` (defaults $25,000 × 2.6%), round-trip cost included; TP1 +$13, TP2 +$20 | `notify.plan_cfg` and the plan functions | `test_notify_plan` 28, `test_risk_sizing` 10, `test_sizing` 3, `test_fixed_risk` 2 | N1; D-13 | LIVE | tests; cost is the model's, not the broker's (GA-04) |
| D-03 | Stale-signal gate (no trade alert from an old bar) | `notify.py` | `test_stale_gate_paths` 35, `test_stale_signals` 20 | PR-B, 2026-11-12 | LIVE | tests; `audit/tools/mutation_stale_gate.py` |
| D-04 | Delivery integrity log (attempt, retry, cache check, final state) | `notify._deliver` and related | `test_notify_delivery` 61 | P-0 specification | LIVE | `forward-ledger:notifications/*.jsonl`; `mutation_notify_delivery.py` |
| D-05 | Outage notice (one message when a run may have lost or repeated alerts) | `quantum/outage_notice.py` | `test_outage_notice` 53 | PR-A | LIVE | tests; `audit/tools/outage_replay.py` |
| D-06 | Disclaimer first on every trade alert | `notify.TRADE_DISCLAIMER` | `test_alert_disclaimer` 16 | PR #101 | LIVE | tests; `mutation_alert_disclaimer.py` |
| D-07 | Daily validation report | `notify.py` | `test_daily_report_split` 9 | PR D | LIVE-PHONE | delivery log `stream=report` |
| D-08 | MT5 prices and wording (`MT5_PRICE_OFFSET`, conditional order lines, LATE flag) | `notify.py` | `test_mt5_wording` 6 | IA-07; MT5 timing | LIVE | tests |
| D-09 | Bundling (more than 5 messages in a run go as one) and a 20-minute freshness limit | `breakouts.BUNDLE_AT`, `FRESH_SEC` | `test_breakouts` | W7 | LIVE | tests |
| D-10 | Manual test-alert and delivery-check workflows | `alert-test.yml`, `alert-delivery-check.yml` | — | operator setup | manual only | never run without the operator's approval |

### 3.5 Records

| ID | Feature | Where | Tests | Status | How to verify |
|---|---|---|---|---|---|
| E-01 | Forward ledgers per arm and timeframe | `forward-ledger:holdout/*.json`, `holdout_manifest.json` | `test_engine_forward` | LIVE (never force-pushed) | `audit/tools/ledger_check.py`; `audit/tools/forward_stats.py` |
| E-02 | Run manifest (data hashes, versions, run id) | `quantum/manifest.py`; `forward-ledger:manifests/` | `test_manifest_env` 5 | LIVE | manifest per run |
| E-03 | Revision records (data revisions per day) | `forward-ledger:revisions/` | — | LIVE | day files |
| E-04 | Payload archive (each run's JSON payloads, SHA-256 in the manifest) | Actions artifact `payloads-<run>-<attempt>`, kept 90 days | `test_payload_archive` 4 | LIVE | `audit/tools/payload_archive_check.py` |
| E-05 | Registered forward tests B15 / B15b / B9 / B31b-SHADOW / C1 / SETUP | `forward-ledger:research_forward/` | `test_grab_forward` 6, `test_engine_forward` 8 | LIVE | counts in §4 |
| E-06 | Phone delivery log | `forward-ledger:notifications/YYYY-MM-DD.jsonl` | `test_notify_delivery` | LIVE | §4.4 |
| E-07 | Sweep and breakout outcome records | `market-data:alerts_state.json` → `brk.sw`, `brk.events` (at most 300 each) | `test_sweeps`, `test_breakouts` | LIVE, **not durable** (GA-03) | `git show origin/market-data:alerts_state.json` |
| E-08 | Operator's forward log (spreadsheet) | `audit/XAUUSD_Forward_Test_Log.xlsx` | formulas checked against Python | manual | — |

### 3.6 Website

| ID | Feature | Code | Tests | Status |
|---|---|---|---|---|
| F-01 | Site and method page | `site/index.html`, `site/method.html`, `site/app.js`, `site/style.css` | `test_index_json_strict` 2, `test_uncalibrated_labels` 3, `test_plan_labels` 2, `test_gold_arrows` 1 | LIVE |
| F-02 | Site JSON builder (presentation only) | `quantum/report.py` (OHLC rounded to 2 decimals) | via the suite | LIVE |
| F-03 | Deployment smoke test (the live site serves this run's files) | `quantum/smoke.py` | `test_smoke` 5 | LIVE |
| F-04 | Partial-failure warning | `quantum/run_check.py` | `test_run_hygiene` 5 | LIVE (warnings only) |
| F-05 | Probability labels: the engine's `p` and the figures derived from it are labelled NOT CALIBRATED | `site/app.js`, `report.py` | `test_uncalibrated_labels` | LIVE |

### 3.7 Build, CI and code-quality tools

| ID | Feature | Where | Status |
|---|---|---|---|
| G-01 | Unit-test gate inside the production workflow | `quantum-site.yml` | LIVE |
| G-02 | Pull-request checks (tests and reference checkers, read-only) | `pr-checks.yml`; `test_pr_checks` 7 | LIVE |
| G-03 | Pinned dependencies | `requirements.lock` (numpy 2.4.6, pandas 3.1.1); versions recorded per run | LIVE |
| G-04 | Inventory and wiring check: every switch passed, nothing unreferenced | `audit/tools/inventory.py`; `test_inventory` 2; appendix `docs/inventory/PRODUCTION_CONSTANTS.md` | LIVE (appendix regenerated in this branch, GA-17) |
| G-05 | Integrity rules: research code never imported by production; seeded random streams | `test_integrity` 16 | LIVE |
| G-06 | Mutation tests of the critical rules | `audit/tools/mutation_*.py` (8 tools) | manual |
| G-07 | Forward-record tools | `ledger_check.py`, `forward_stats.py`, `exec_sensitivity.py`, `h4_outcome_audit.py` | manual |

### 3.8 Pine reference (frozen; display only since Amendment 6)

| ID | Feature | Where | Status |
|---|---|---|---|
| H-01 | Seven Pine v6 artefacts (Master, Strategy, OLDGATES, CHALLENGER, Diagnostics, EdgeCases, Visuals) | `artefacts/` | frozen at the hashes in `audit/PREREGISTRATION.md` §2 |
| H-02 | Frozen-file manifest | `audit/MANIFEST.sha256` | 7 of 7 OK today |
| H-03 | Static checkers | `audit/tools/precheck.py`, `undeclared.py`, `order.py`, `deadcode.py`, `pinelimits.py`, `diag_parity.py` | clean today; they do not replace the compiler |

### 3.9 Research programme

| ID | Feature | Where | Status |
|---|---|---|---|
| R-01 | Harness: triple-barrier labeller, purged walk-forward, CPCV / PBO, Deflated Sharpe, Reality Check, registry | `quantum/research/harness.py`; `test_research_harness` 8 | RESEARCH |
| R-02 | Partitions: development 2020-01-24 → 2023-01-24; validation → 2024-07-01; holdout → 2026-01-01 | `audit/PREREGISTRATION.md` Amendment 13 | defined; validation and holdout already read (GA-01) |
| R-03 | Registrations before code | `research/registrations/` (25 files on production; W3, W4, W5, W8, W8-cost, W12, W13 on their branches) | evidence of order is commit order (GA-06) |
| R-04 | Trial log | `research/trials.jsonl` (production 1,560 lines) | split across branches (GA-02) |
| R-05 | Study modules B1 – B31 | `quantum/research/b*.py` and `validate_rn.py` (27 study modules on production, plus `harness.py` and `history.py`) with `tests/test_research_*` | RESEARCH |
| R-06 | Study modules B31b-W3 … W13 | `w3liq.py`, `w4pull.py`, `w5entry.py`, `w7breakout.py`, `w8quality.py`, `w12session.py`, `w13precision.py` | BRANCH (GA-18) |
| R-07 | Literature review (26 sources, each with a verification status) | `research/01_RESEARCH_LITERATURE_REVIEW.md`; `16_CONFIRMED_TRADE_LITERATURE.md`; `ENTRY_PRICE_RESEARCH.md`; `ORDER_FLOW_RESEARCH.md` | done (R24 not verified) |

**Studies and verdicts.** Development data unless marked. "OOS" means the study also scored validation or holdout.

| Study | Question | Verdict | Where |
|---|---|---|---|
| B1 / B1b | published families: time-series momentum, Donchian, sessions, volatility scaling | 0 of 100 net-positive | production |
| B2 / B2b / B2c | 9 SMC setups at +$2 … +$20 against −$10 / −$20 | none above break-even or random | production |
| B3 | trend + confirmation + SMC sequences (210 trials) | none passes | production |
| B4 / B4-RN-V1 | round numbers, session-open momentum, limit entries | one lead failed its one validation (41.5% vs 40.3% random) | production |
| B5 / B5-explore | real COMEX order flow (74.5M trades, Databento) | reject; AUC 0.50 | production |
| B6, B9-explore, B12 | multi-timeframe agreement; all site sources at ±$13; level criteria | none better than random; the GRAB lead became forward test B9 | production |
| B7 / B8 | macro (dollar, yields, VIX, oil, COT); US news | reject all 54 | production |
| B10, B13 (OOS), B14 | gate release; overnight / intraday effects, 31-feature model; multi-timeframe BREAK | fail / insufficient | production |
| B16 – B18 | sweep / breakout level rules; all-confirmation setups; 4h candle breakout | fail (46–52% vs 46% random) | production |
| B19 – B23 (OOS) | two-stage confirmation; run continuation; liquidity alerts with confirmation; calibrated ML (AUC 0.47–0.51) | fail | production |
| B25 | execution timing after a $15 confirmation | delay does not hurt; nothing beats the close | production |
| B26 – B29 | symmetric ±$15 baseline; maximum-TP-first discovery; Phase C tracks A / B | no configuration beats random; NO QUALIFIED | branches `research-sym15`, `research-phase-c` |
| Phase D (D3-P) | price-only sets on real data | NO QUALIFIED STRATEGY | branch `research-phase-d` |
| B30 (OOS) | $0 / $10 / $15 / $20 confirmation thresholds | none supported out of sample | production |
| B31 (OOS) | liquidity-aware selection, modules A–E | no out-of-sample edge | production |
| B31b W1 – W2 | structure detector; why few trades | descriptive | production |
| B31b W3 | sweep reversals before / during / after (14,090 events) | 48–50% +$10 first; no method beats random | branch |
| B31b W4 | 15 continuation / reversal / retest methods | none beats random (Holm p 1.00) | branch |
| B31b W5 | 20 executable entry mechanisms, 4,223 impulses | all negative after costs (−0.05 to −0.12 R) | branch |
| B31b W7 | breakout entries E0–E4 on M15 / M30 | detection exact; no entry positive after costs | branch |
| B31b W8 | quality-selected breakouts at the screenshot broker cost | NO CANDIDATE | branch |
| W11 | 151 measured plans on one yardstick (reads committed results only) | no plan positive after costs | branch |
| B31b W12 | session-boundary sweep after a run (2,100 events) | +$10 first 26% vs 33% needed; NO CANDIDATE | branch |
| B31b W13 | 50 registered mechanisms in six families, one cost, walk-forward, regimes; W12 revalidation | NO SUPPORTED MECHANISM; best −0.001 R | branch |

---

## 4. Current records (RECORDED, 2026-11-26)

### 4.1 Forward ledgers (current freeze key; closed trades)

Source: `audit/tools/forward_stats.py`. Its bootstrap treats trades as independent, so the true intervals are wider (GA-09).

| Ledger | n | Win % [Wilson 95%] | Mean R [bootstrap 95%] | Sum R |
|---|---|---|---|---|
| 5m treatment | 17 | 35.3 [17.3, 58.7] | −0.214 [−0.796, +0.472] | −3.64 |
| 5m challenger | 13 | 46.2 [23.2, 70.9] | +0.099 [−0.666, +0.950] | +1.29 |
| 15m treatment (= challenger) | 6 | 50.0 [18.8, 81.2] | +0.012 [−0.733, +0.808] | +0.07 |
| 30m treatment (= challenger) | 3 | 0.0 [0.0, 56.2] | −1.039 | −3.12 |
| 1h treatment (= challenger) | 4 | 50.0 [15.0, 85.0] | +0.157 | +0.63 |
| 4h treatment (= challenger) | 1 | 100.0 [20.7, 100.0] | +1.487 | +1.49 |
| 5m H3 | 8 | 50.0 [21.5, 78.5] | +0.865 [−0.685, +2.605] | +6.92 |
| 5m H5 | 7 | 14.3 [2.6, 51.3] | −0.686 [−1.130, +0.158] | −4.80 |
| **5m H4** | **404** | 34.7 [30.2, 39.4] | **−0.138 [−0.212, −0.063]** | −55.73 |
| 15m H4 | 146 | 40.4 [32.8, 48.5] | −0.054 [−0.176, +0.077] | −7.92 |
| 30m H4 | 70 | 40.0 [29.3, 51.7] | +0.028 [−0.180, +0.249] | +1.97 |
| **1h H4** | **37** | 32.4 [19.6, 48.5] | **−0.308 [−0.511, −0.093]** | −11.38 |
| 4h H4 | 8 | 62.5 [30.6, 86.3] | +0.432 [−0.087, +0.996] | +3.45 |

Control, H2 and the other small ledgers each have 1–4 trades (full output: `forward_stats.py`).

### 4.2 Registered forward tests

| Test | Since (UTC) | Record | Registered check |
|---|---|---|---|
| B15-ENGINE-FWD | 2026-11-06 → ended 2026-11-15 (Amendment F) | 5 TP, 8 SL of 13 | ended, no verdict |
| B15b-ENGINE-FWD (+$13 before −$13 from each engine signal) | 2026-11-15 11:48 | 12 TP, 8 SL of 20 | first look at 30 |
| B9-GRAB-FWD | 2026-11-04 23:47 | 12 TP, 11 SL of 23 | first look at 30 decided; "proven" needs the Wilson lower bound above 51% (21 of 30) |
| B31b-SHADOW-FWD | 2026-11-15 13:23 | 84 setups | no verdict |
| C1 CONFIRM-LIVE | 2026-11-10 21:35 | 347 rows: 94 CONFIRMED, 217 INVALIDATED, 36 EXPIRED | descriptive |
| SETUP-LIVE | 2026-11-06 | 275 setups | descriptive |
| B24-CONFIRM-FWD | — | OFF; its voided start is kept | — |

### 4.3 Live monitor records (`market-data:alerts_state.json`)

- **Sweeps, since 2026-11-23 07:24:**
  - 21 sweeps, all decided at the +$10 race.
  - 5 reached +$10 first (23.8%); 3 reached +$15 and 3 reached +$20 first.
  - Wilson intervals are shown from 30 decided; the registered descriptive threshold is 100 per level timeframe.
- **Breakouts, since 2026-11-19 12:22:**
  - 93 events: M15 49, M30 24, H1 12, H4 8.
  - Stage counts: CONFIRMED 75, MOVE +$10 41, +$15 38, +$20 34, RETEST 29, FAILED 60, CLOSED 28.
  - Stages are not exclusive: an event can move +$10 and later fail.

### 4.4 Phone delivery log (`forward-ledger:notifications/`, 15–26 Nov)

| Stream | Messages |
|---|---|
| breakouts | 249 |
| sweeps | 49 |
| 15m engine | 26 |
| key zones | 21 |
| C1 confirmation | 13 |
| daily report | 9 |
| **Total** | **367** |

How the sends ended:
- **365** were accepted by ntfy (HTTP 200) and ended `DELIVERY_UNCONFIRMED`. This is the success state by design: nothing confirms that the phone showed the message.
- **2** ended `RETRY_FAILED` with HTTP 429 (ntfy rate limit), both breakouts at 2026-11-22 23:52 UTC, the weekly open.

Report timing: the Friday 20 Nov report went out at 02:44 UTC Saturday, before the close-slot fix (PR #139). The 25 Nov report went out at 22:04 UTC.

---

## 5. Verification guide (for the auditor)

Run from a clone of the repository at the production commit. Python 3.11, Node 20+.

```sh
git checkout 505f05ecc
pip install -r requirements.lock

# 1. Tests
python -m pytest -q tests                      # expect: 1077 passed
node --test tests/*.mjs                        # expect: 20 pass, 0 fail

# 2. Engine freeze key (must not change; any change restarts the forward test)
python -c "from quantum import holdout, config; print(holdout.freeze_key(config.Config()))"
#                                              expect: 1f88aad357497da4:4440d52587f5cc6b

# 3. Pine reference
sha256sum -c audit/MANIFEST.sha256             # expect: 7 x OK
for t in precheck undeclared order deadcode pinelimits; do python3 audit/tools/$t.py artefacts/*.pine; done
python3 audit/tools/diag_parity.py             # expect: PASS

# 4. Production wiring
python3 audit/tools/inventory.py --md /tmp/inv.md   # expect: 40 modules; 47 of 47 switches passed; none unreferenced

# 5. Forward records (read-only)
git fetch origin forward-ledger market-data
mkdir fl && git archive origin/forward-ledger | tar -x -C fl
python3 audit/tools/ledger_check.py fl         # today: 13 flags, all H6 trades under its closed pre-Amendment-F key (GA-21)
python3 audit/tools/forward_stats.py fl 1f88aad357497da4
git show origin/market-data:alerts_state.json > state.json     # sweep (brk.sw) and breakout (brk.events) records

# 6. Research reproduction (research branches; development partition only)
W13=claude/session-01fdjaothuvhxscxtl7ysa-y3n4w4-w13-entry-precision
git fetch origin research-data $W13
git worktree add ../rd origin/research-data && git worktree add ../w13 origin/$W13
cd ../w13
python -m quantum.research.w12session --rd ../rd --cost research/registrations/B31b-W8-cost.json --out w12.json
python -m quantum.research.w7breakout --part development --rd ../rd --out w7.json --csv w7.csv
python -m quantum.research.w13precision --rd ../rd \
       --w4 research/results/b31b_w4_trades_development_2026-11-19.csv \
       --w5 research/results/b31b_w5_trades_development_2026-11-19.csv.gz \
       --cost research/registrations/B31b-W8-cost.json --out w13.json
# compare data_hash (f113f97ad2105ff9), code_sha256 and the counts with the committed results JSON
```

What to check by reading, not running:
- **Order of work.** Each registration commit comes before its code commit, and the code commit before its result
  commit (`git log --follow` on each file).
- **No look-ahead.** Each feature's value at a bar uses only bars closed by then:
  - `test_engine::test_no_lookahead`;
  - `test_breakouts::test_no_look_ahead_every_event_is_the_same_from_the_bars_closed_by_it`;
  - `test_confirm_panel::test_no_look_ahead_on_every_prefix`;
  - `test_entry_intel::test_no_look_ahead_run_by_run_equals_one_pass`;
  - `test_backtest_gaps::test_13_no_lookahead_trades_closed_before_a_cut_are_identical`.
- **Labels.** Every number shown as a probability is labelled with what it is. The engine's `p` is labelled NOT
  CALIBRATED; the rates are measured frequencies with Wilson intervals.
- **Costs.** Each study's cost file: every value is either measured (with its source) or labelled ASSUMED.

---

## 6. Verified today (MEASURED, 2026-11-26)

These are local runs on the production commit, not GitHub CI.

| Check | Result |
|---|---|
| Python tests | 1,077 passed, 0 failed, 0 skipped (6 min 20 s). Local pandas 3.1.0 against the pinned 3.1.1; numpy 2.4.6 as pinned. 2,243 warnings, including a pandas deprecation at `audit/tools/xcheck_dukascopy.py:286` |
| JavaScript tests | 20 passed, 0 failed |
| Freeze key | `1f88aad357497da4:4440d52587f5cc6b`, unchanged |
| Frozen-file manifest | 7 of 7 OK |
| Pine checkers | precheck OK; 0 unresolved; 0 order violations; 0 dead; 0 limit issues; `diag_parity` PASS (3,291 engine lines) |
| Wiring (`inventory.py`) | 40 modules, 15,095 lines; 47 of 47 switches passed; no unreferenced definitions. The committed appendix was stale (sweeps.py 246 → 361 lines; 7 constants added by PR #140 missing): regenerated in this branch |
| Production runs (GitHub) | the latest 40 `quantum-site` runs (2026-11-25 21:31 → 2026-11-26 07:46 UTC) all succeeded on `505f05ecc` |
| Ledger check | 13 flags, all H6 trades of 5–13 Nov under the pre-Amendment-F key (H6 closed by design) |

---

## 7. Gap analysis (prioritised)

Each gap gives:
- the evidence;
- why it matters for validity;
- the improvement;
- how its fix is verified.

None of these changes is made in this branch except GA-17 (a regenerated documentation appendix). Production changes wait for the operator's approval.

### Priority 1: whether any result can be trusted

**GA-01. The 2023–2025 "out-of-sample" history has already been used.**
- *Evidence:*
  - `research/registrations/B31.json` line 12: "the validation … and holdout … partitions have been read by B10, B13, B19, B20-B23 and B30. No historical period is untouched."
  - The W3 – W13 documents say "validation and holdout were not opened" (meaning: by that study).
- *Why it matters:* any future "validation" on 2023–2025 is a second look. Selection across studies leaks into it.
- *Improvement:*
  1. A partition-use ledger: every study that read validation or holdout, with date, commit and what was scored.
  2. An erratum note on the W-series documents saying "not opened by this study". Append a note; never rewrite the record.
  3. Treat the forward period from the 2026-11-15 freeze as the only untouched test.
- *Verify:* the ledger lists every registration whose `partitions` field includes validation or holdout, and every results file scored on them.

**GA-02. The trial log is split across branches and undercounts the hypotheses tested.**
- *Evidence:*
  - `research/trials.jsonl` has 1,560 lines on production.
  - Branches hold 1,495 to 3,808 lines; there are 4,045 distinct records across all branches.
  - B27 (1,212), B29 (674) and B28 (330) exist only on the Phase C / D branches.
  - W-studies log one line per run although each run tests many rules (W13: 50 mechanisms; W4: 15; W5: 20).
- *Why it matters:* Holm is applied inside each study only. A program-level correction (Deflated Sharpe, PBO, Reality Check over everything tried) cannot be computed from any one branch.
- *Improvement:*
  - Append the union of all branches' records to the production log, without rewriting any line.
  - From now on, write one line per mechanism tested, with its registration id, code hash and data hash.
  - Report a program-level multiple-testing figure.
- *Verify:* distinct-record count on production equals the union count; every results JSON's mechanism count matches its lines.

**GA-03. The registered live sweep and breakout records are not durable.**
- *Evidence:*
  - `sweeps.KEEP = 300` and `breakouts.KEEP_EVENTS = 300`: older records are deleted.
  - They live in `market-data:alerts_state.json`, a single orphan commit replaced every run.
  - The W7 registration says every live breakout "is kept"; checks are "descriptive until … 100 decided".
- *Rates today:*
  - Breakouts run at about 14 a day, so the cap is reached around 11 Dec.
  - H4 breakouts run at about 8 a week, so 100 decided would take about 12 weeks, while the cap keeps about 3 weeks.
  - Sweeps run at about 7 a day.
  - Nothing has been deleted yet.
- *Why it matters:* the registered checks for H1 / H4 can never be reached from the retained record. A failed write can also lose the whole record.
- *Improvement:* append each decided sweep and breakout record, once, to `forward-ledger` (day files, never force-pushed). Detection, messages and the freeze key are unchanged; `sweeps.py` and `breakouts.py` are outside `ENGINE_SOURCES`.
- *Verify:* after N days, records in the ledger = all sweeps and breakouts since each `since`, and a replay of the archived payloads gives the same set.

**GA-04. Costs are not the broker's.**
- *Evidence:*
  - Model: spread $0.30, slippage $0.20 per side, commission $7 per lot (`config.py`).
  - Spreads measured from the operator's MT5 screenshots: Asia $0.45–0.52 (19 and 25 Nov); about $0.80 at 20:55 UTC on 26 Nov (one reading near the daily close).
  - Commission and contract size (100 oz) are ASSUMED (`B31b-W8-cost.json`, `contract.py`).
- *Why it matters:* every net-R figure and the $650 sizing depend on cost. A +$10 target against a structural stop of a few dollars (W12 median $3.35) is very sensitive to $0.50 of spread.
- *Improvement:*
  - Read the MT5 symbol specification: contract size, commission, swap, stops level.
  - Take a spread sample in every session (an MT5 export with the spread column, or many timed screenshots).
  - Register it as a cost amendment before it is used; re-cost the studies' trade files with the existing formula.
- *Verify:* the cost file has no ASSUMED field; the re-costed results reproduce from the committed trade files.

**GA-05. Feed price vs broker price.**
- *Evidence:*
  - The website uses Twelve Data spot. The operator's MT5 differs by about $0.4–0.5 (screenshot comparisons).
  - The offset is one constant (`MT5_PRICE_OFFSET`).
  - The MetaApi feed (`mt5.py`) is not connected.
- *Why it matters:* level touches, sweeps (to 2 decimals) and the +$10 / +$15 / +$20 races can differ at the broker. A move of +$10 on the feed can be +$9.5 at the broker.
- *Improvement:* compare an MT5 M1 export with the feed bar by bar per session (the importer exists on branch `research-phase-d`), and measure the offset's distribution, not one value.
- *Verify:* the offset distribution by session, and the share of sweeps whose level is breached on one source only.

**GA-06. "Registered before code" rests on commit timestamps the author sets.**
- *Evidence:*
  - The approvals are quoted from chat in each registration.
  - Commits are made by the assistant's account.
  - Git author and committer dates can be set freely.
- *Why it matters:* a third party cannot confirm independently that a rule was fixed before its data was seen.
- *Improvement:*
  - Use GitHub's server-side times (push events, pull-request timelines) as the evidence of order.
  - The operator approves each registration on GitHub (a pull-request review), or the registration hash is timestamped externally before the run.
- *Verify:* for each study, the server-side push time of the registration is earlier than that of its code and result.

### Priority 2: what the live evidence can and cannot show

**GA-07. Phone delivery is proven only to the ntfy server.**
- *Evidence:* 365 of 367 sends ended `DELIVERY_UNCONFIRMED` (HTTP 200); 2 were lost to HTTP 429 at the 22 Nov weekly open.
- *Why it matters:* "the alert reached the phone at time T" is not measured. A burst can drop messages.
- *Improvement:*
  - Space or bundle the sends when a run has many messages (the weekly open).
  - A periodic, operator-run reconciliation of the ntfy app's message list against the log, on a sample of days.
- *Verify:* zero `RETRY_FAILED` over a month; the reconciliation sample matches the log.

**GA-08. The live samples are small and no registered look has been reached.**
- *Evidence:* B15b 20 of 30; B9 23 of 30; sweeps 21 (100 per level timeframe needed); the engine arms 1–17 trades each.
- *Why it matters:* no verdict and no calibration is possible yet.
- *Improvement:* none beyond time, plus GA-03 so the records survive to their checks.
- *Verify:* the counts at each registered look.

**GA-09. Two H4 ledgers are negative; the forward statistics assume independent trades.**
- *Evidence:* 5m H4 −0.138 R [−0.212, −0.063] (n 404); 1h H4 −0.308 R [−0.511, −0.093] (n 37); trade-level bootstrap.
- *Why it matters:* overlapping trades on the same day are not independent, so the intervals are too narrow.
- *Improvement:*
  - A day-clustered bootstrap in `forward_stats.py`, as the research studies use.
  - Apply the decision rules of PREREGISTRATION §4 / §5 at their registered points only.
- *Verify:* the clustered intervals are reported next to the trade-level ones.

**GA-10. Losses beyond $650.**
- *Evidence:* the planned loss is not a maximum. Worst gap losses measured: $6,061 (W5) and $2,922 (W7) on $650 plans.
- *Already in place:* C1 plan alerts carry a GAP RISK line (`confirm_entry.gap_line`).
- *Why it matters:* the mean R hides the tail that decides an account's survival.
- *Improvement:* every study and forward summary reports the loss tail next to the mean: the share beyond 1 R, the 99th percentile and the worst.
- *Verify:* the tail columns are present in the result files.

**GA-11. Order flow and volume are proxies.**
- *Evidence:*
  - No live order flow.
  - The engine's volume profile uses COMEX GC futures volume (D-07).
  - The sweep context's POC is a time-based (TPO) POC on spot bars.
  - B5 (real COMEX trades) found AUC 0.50.
  - B5c (Dukascopy ticks) is pending on the operator's laptop.
- *Why it matters:* "order flow / POC" in an alert means a proxy, and an auditor should not read it as broker or exchange volume.
- *Improvement:* name the POC type in every place it is shown (TPO or GC-volume); run B5c when the laptop is available.
- *Verify:* site and message text.

**GA-12. The intraday dollar and yield history starts in 2024.**
- *Evidence:* `market-data` holds DX-Y.NYB and ^TNX 60m from 2024-05. The 2020–23 development studies used EUR/USD 15min as the dollar factor.
- *Why it matters:* the DXY and US10Y 1-hour changes now on every SWEEP message have no historical test at all.
- *Improvement:* label them "context, untested"; any test of them needs a separate registration, with a source that covers the development period.
- *Verify:* the message label.

**GA-13. No calibrated probability exists.**
- *Evidence:*
  - Engine `p` is labelled NOT CALIBRATED.
  - B22's models reached AUC 0.47–0.51.
  - Live rates are frequencies with Wilson intervals.
- *Why it matters:* the operator's target asks for calibrated alerts. Calibration needs a mechanism with an edge first.
- *Improvement:* keep the current labels. A probability is shown only after a supported mechanism has been calibrated on data it was not selected on.
- *Verify:* `test_uncalibrated_labels`.

### Priority 3: reproducibility and auditor friction

**GA-14. Research code for W3 – W13 is only on branches.**
- *Evidence:*
  - `w3liq.py`, `w4pull.py`, `w5entry.py`, `w7breakout.py`, `w8quality.py`, `w12session.py` and `w13precision.py` are not on production.
  - The W12 and W13 branches were rebuilt from production (their history is unrelated to W3 – W8).
- *Why it matters:* an auditor must assemble the programme from about 60 branches.
- *Improvement:* merge the research modules, registrations and results onto production as research only. `test_integrity` already forbids production from importing them.
- *Verify:* one checkout reproduces every committed result.

**GA-15. Research input data is not kept immutably.**
- *Evidence:* `research-data` is a single force-pushed orphan commit. Each result records the data hash (`f113f97ad2105ff9`), but the bars themselves are replaced.
- *Improvement:* keep one immutable, private copy of each study's input, identified by its hash. Not in the public repository (vendor terms, GA-16).
- *Verify:* the hash of the retained copy equals the result's `data_hash`.

**GA-16. Vendor data on public branches.**
- *Evidence:* `market-data` and `research-data` hold Twelve Data and Yahoo bars, written by the workflows in a public repository.
- *Why it matters:* redistribution may breach the vendors' terms.
- *Improvement:* the operator checks each vendor's terms; if needed, keep the stores private.
- *Verify:* a written check per vendor.

**GA-17. The inventory appendix was stale and nothing enforced it.**
- *Evidence:* `docs/inventory/PRODUCTION_CONSTANTS.md` predated PR #140. `test_inventory` checks switches and unreferenced code, not the appendix.
- *Fixed here:* the appendix is regenerated in this branch.
- *Improvement:* a test that regenerates it and compares.
- *Verify:* the test fails on a stale appendix.

**GA-18. W-series results cite branch-only code.** Merged with GA-14. Each results document names its module and hash; the auditor needs the branch named in §3.9.

**GA-19. A tracked bytecode file.**
- *Evidence:* `audit/tools/__pycache__/trace.cpython-311.pyc` is in git and changes whenever the tools run.
- *Improvement:* remove it from the index and ignore `__pycache__`.

**GA-20. A stale `prod` branch and about 60 other branches.**
- *Evidence:* `origin/prod` stops at PR #138; production is the default branch.
- *Improvement:* state the production branch in the README; tag and archive finished branches.

**GA-21. `ledger_check.py` does not know that H6 is closed.**
- *Evidence:* 13 flags, all H6 trades of 5–13 Nov under the pre-Amendment-F key.
- *Improvement:* read the closed-arm window from the holdout manifest and report these as "closed arm (Amendment F)".
- *Verify:* 0 problems on today's ledger.

**GA-22. The research-history workflow reports failure on a normal end of history.**
- *Evidence:* HTTP 400 at the feed's first bar, after the data was saved.
- *Improvement:* treat "no data before the first bar" as the end of history, so that red means a real failure.

**GA-23. Replays depend on the payload's 2-decimal rounding.**
- *Evidence:* `report.py` rounds OHLC to 2 decimals. A replay at 6 decimals disagreed in 7 stages; at 2 decimals it matched 180 of 180. The replay scripts are not committed.
- *Improvement:* commit the replay as an audit tool with a test on an archived payload.

**GA-24. Library deprecation.**
- *Evidence:* `xcheck_dukascopy.py:286` uses `DataFrame.join(lsuffix=…, rsuffix=…)`, deprecated in pandas 3.1.
- *Improvement:* switch to `suffixes=`.

**GA-25. Forward arm bookkeeping.**
- *Evidence:* Treatment and Challenger are identical on 15m / 30m / 1h / 4h in this window (they differ only by the fast trend term).
- *Why it matters:* the A/B comparison has information on 5m only so far.
- *Improvement:* none; report it with each comparison.

**GA-26. The research partition dates mix "2024-07 → 2026-01" and "2024-07-01 → 2025-12-31".** Both mean the same period. Use one form in all documents.

---

## 8. Honest status

What the system does:
- It runs on time and records everything it decides.
- It detects breakouts and sweeps on M15 / M30 / H1 / H4 as they close, at MT5-offset prices, with the +$10 / +$15 / +$20 levels.
- It says on every directional message that the entry is not validated.

What the system does not do:
- It does not know in advance which alert will reach +$10 before its stop.
- Across about 40 studies and 4,045 logged trial records, no entry rule beat matched random entries after costs.
- The live forward samples are too small to give a verdict.

A planned $650 loss can be exceeded by a price gap. 100% accuracy is not reachable.

The gaps that most limit validity:
- **GA-01 – GA-03:** the record of what was tried, which data was already seen, and whether the live records survive.
- **GA-04 – GA-05:** the broker's real costs and prices.

Fixing them does not create an edge. It makes the evidence, for or against, trustworthy.

---

## Appendix A. Tests per file (collected today; 1,077 in all)

confirm_panel 79 · notify_delivery 61 · outage_notice 53 · engine 41 · confirm_entry 40 · breakouts 36 ·
stale_gate_paths 35 · entry_intel 34 · confirm 33 · sweeps 30 · fwd_b24 29 · notify_plan 28 · backtest_gaps 23 ·
stale_signals 20 · research_b19 19 · keyzones 18 · ta 17 · shadow 16 · research_b5_orderflow 16 · integrity 16 ·
alert_disclaimer 16 · independent_math 14 · research_b31w2 13 · research_b31 13 · h3 13 · contract 12 · h2 11 ·
xcheck 10 · trade_race 10 · risk_sizing 10 · research_b31w1 10 · research_b25 10 · site_gate 9 · live_path 9 ·
engine_reference_levels 9 · daily_report_split 9 · setup_live 8 · research_harness 8 · research_b5c_dukascopy 8 ·
research_b30 8 · pine_v92_port 8 · engine_forward 8 · amendment_f 8 · research_history 7 · research_b2 7 · pr_checks 7 ·
macro_panel 7 · h6 7 · cost_record 7 · signal_record 6 · research_b7 6 · research_b4 6 · research_b22 6 ·
research_b20 6 · mt5_wording 6 · mt5 6 · grab_forward 6 · smoke 5 · run_hygiene 5 · research_b3 5 · manifest_env 5 ·
h5 5 · h4 5 · alert_quality 5 · validate_rn 4 · tf30 4 · research_b5 4 · research_b21 4 · research_b13 4 ·
research_b10 4 · payload_archive 4 · cost_profiles 4 · uncalibrated_labels 3 · sizing 3 · signal_status 3 ·
setup_rules 3 · research_b8 3 · relay 3 · macro_factors 3 · h4_display 3 · alert_sixty 3 · research_b6 2 ·
research_b23 2 · plan_labels 2 · inventory 2 · index_json_strict 2 · gate_sides 2 · fixed_risk 2 · gold_arrows 1.
JavaScript: costs 8 · relay 7 · scheduler 5.

## Appendix B. Where things are

| What | Branch |
|---|---|
| Production code, site, registrations B1 – B31b-W7 | `claude/audit-prompt-real-artefacts-nekqv6` (default) |
| Forward ledgers, manifests, revisions, delivery log | `forward-ledger` (append-only) |
| Market-data store and alert state | `market-data` (one orphan commit) |
| Research bars | `research-data` (one orphan commit) |
| B5 order-flow and B7 macro runs | `research-orderflow`, `research-macro` |
| B26 – B29, Phase C / D | `claude/research-sym15`, `claude/research-phase-c`, `claude/research-phase-d` |
| W3, W4, W5, W7, W8, W11, W12, W13 | `claude/session-01fdjaothuvhxscxtl7ysa-y3n4w4-{w3-liquidity, w4-research, w5-entry, w7-study, w8-quality, w11-scoreboard, w12-session-sweeps, w13-entry-precision}` |
| The separate Pine line v33 – v104 (display only, never evidence) | `claude/xauusd-developed-files-tmnk9g` |

Earlier detail: `docs/SYSTEM_INVENTORY.md` (23 Nov), `docs/PLATFORM.md`, `audit/PREREGISTRATION.md`,
`audit/FINDINGS_TRACEABILITY.md`, `research/README.md`, `research/STRATEGY_CATALOGUE.md`.
