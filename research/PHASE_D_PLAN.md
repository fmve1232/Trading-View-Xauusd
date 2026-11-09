# Phase D: institutional order flow, lower-timeframe validation and incremental predictive value

**Status (2026-11-09): D0, D1 and D2 complete; D3–D5 are waiting on external data.**
- **Registered:** `registrations/PHASE_D.json`, before any data.
- **Code:** built and tested on synthetic data only.
- **Data:** no Dukascopy, MT5 or broker data has been received, so every Phase D result document reads **INSUFFICIENT DATA — RESEARCH INCOMPLETE**.
- **Phase C:** frozen and unchanged; its verdict, NO QUALIFIED STRATEGY, stands.

| Item | Value |
|---|---|
| Branch | `claude/research-phase-d`, created from `claude/research-phase-c` at `c0496c13c` (the Phase C final commit) |
| Phase C evidence | pinned by `PHASE_C_FROZEN.sha256` (74 files) and `tests/test_phase_c_frozen.py`. The test also pins the first 3,808 lines of `trials.jsonl`. |
| Registration | `registrations/PHASE_D.json` (hypotheses, data, alignment, features, labels, models, costs, tests, C1–C6, outputs, compute) |
| Trial log | `phase_d_trials.jsonl`, separate and hash-chained (`quantum/research/d_log.py`); created at the first real run |
| Production | unchanged (no file outside `research/`, `quantum/research/` and `tests/`) |

---

## 1. Phase C is unchanged

**What Phase C touched.** Phase C changed no file outside `research/`, `quantum/research/` and `tests/`: the diff from `claude/research-sym15` to `c0496c13c` is empty outside those paths.

**What is pinned.** `PHASE_C_FROZEN.sha256` hashes 74 files:
- the reports (`PHASE_C_*`, `B26_BASELINE`, `B27`/`B28`/`B29_RESULTS`, `FEATURE_AUDIT`);
- the registrations B26–B29;
- every results folder (`b26`, `b27`, `b27_fix`, `b28`, `b29`, `b29_fix`, `phasec`);
- the code that produced them: `b22`, `b26`–`b29`, `harness`, `history` and the `phasec_*` / `b26`/`b27`/`b29` tools.

**How the pin is enforced.** The pinned test fails on any byte change to those files. It also fails if the first 3,808 lines of `trials.jsonl` change.

**How Phase D uses Phase C code.** Phase D imports that code and never edits it. The ±$15 benchmark is built by the same function (`b27.labels` → `b26.run_population`) on the same populations, so it reproduces Phase C exactly.

## 2. D0 audit: what exists and what was wrong

### 2.1 B5c (Dukascopy order flow), as registered in Phase C

**Implementation.** `quantum/research/b5c_dukascopy.py`:
- decodes Dukascopy hour files (LZMA records `>3I2f`: ms, ask, bid, ask volume, bid volume);
- reduces each hour at once to 15-minute sums (Cont–Kukanov–Stoikov OFI, queue imbalance, tick imbalance, tick count, spread, last / first mid);
- caches one CSV of sums per day, so a run resumes;
- detects the price scale against the spot paths;
- runs amendment A1 (lag check) and A2 (integrity gates, quarantine).

Its test is B5's machinery: 30 rules and 3 models, a −$10 stop with +$10 / +$15 / +$20 targets, on development only.

| # | Finding | Severity | Fix |
|---|---|---|---|
| B5c-1 | **Every real download would have crashed.** `_session` was defined twice. A2's session-label helper `_session(idx)` replaced the HTTP-session helper `_session()`, so `fetch_hour` and `research_data` raise `TypeError` on the first request. Every test injected a mock `get` and never took the default path. | **Critical** (the run could not start) | The helper is renamed `_session_of`. A new test takes the real path, and it fails on the Phase C code. Recorded as B5C.json amendment A3, signal-neutral. |
| B5c-2 | The boundary day 2023-01-24 fetched 22 hours of the **sealed** validation period and then discarded them unread. | Governance | `day_hours` never returns a sealed hour (A3). |
| B5c-3 | **Development only:** no 2026 period, so it has no independent out-of-sample check. | Design gap | Phase D's extractor adds 2026 behind a sealed-period guard. |
| B5c-4 | Its labels are B5's −$10 stop, **not** the ±$15 benchmark. | Scope | Phase D uses B26's labels; B5c stays its own experiment. |
| B5c-5 | Its sums cannot form the ten Phase D families, and it keeps no executable bid / ask path. | Design gap | `d_dukascopy` adds 23 sums per bar and one-minute best-bid / best-ask OHLC. It writes B5c's own day files with B5c's own function, so one download serves both. |

### 2.2 MT5 M1 importer (`tools/mt5_m1_check.py`, Phase C version)

| # | Defect | Consequence | Fix (Phase D version) |
|---|---|---|---|
| M-1 | Assumed UTF-8 | MT5's usual "Unicode" export is UTF-16, which fails or is misread | BOM / NUL sniffing: UTF-16 LE / BE, UTF-8, UTF-8 with BOM |
| M-2 | Tab only; exact `<…>` headers only | Comma / semicolon files and plain headers are refused | Separator sniffed from the header; `<>` optional |
| M-3 | `format="mixed"` date parsing | Silent misparses possible; unparseable rows not counted | Explicit formats; every unparsed row counted; any unparsed row → NOT USABLE |
| M-4 | No "New York + 7" server zone | The most common MT5 convention could not be expressed. Europe/Athens is an hour wrong for about 3 weeks a year (US vs EU daylight-saving dates). | `--server-tz NY+7` |
| M-5 | Clock check was global only | **A daylight-saving mismatch passes**: the overall peak stays at lag 0. The new test shows exactly this. | Lag check per ISO week; any misaligned week → NOT USABLE; `--suggest-zone` (information only) |
| M-6 | No partition guard | Sealed validation / holdout rows were read, and integrity statistics were computed on them | Sealed rows are dropped right after the UTC conversion and only counted; development and 2026 kept |
| M-7 | No discontinuity, spike or digits-change check | Bad prints and broker price-scale changes would pass | Consecutive-minute jumps (> 0.1%), one-minute ranges > 1%, month-to-month scale changes > 20% |
| M-8 | No coverage by month or year | Partial months would go unnoticed | Bars against the trading-schedule minutes, per month and year; months below 90% listed |
| M-9 | No Saturday or daily-break check | A wrong zone shows here first | Both counted; Saturday bars → NOT USABLE |
| M-10 | No broker / symbol / point record | The file is untraceable and the spread cannot be converted to $ | `--broker --symbol --point --contract-oz` recorded, `NOT SUPPLIED` when absent. The point is inferred from the decimals and cross-checked. The spread is converted to $ only with a supplied point. |
| M-11 | **USABLE without a clock check** | An unchecked clock could enter research | NOT USABLE until checked against a reference (`--reference` or `--reference-rd`) |
| M-12 | `MT5_M1_IMPORT.md` lets `<SPREAD>` replace the modelled spread | MT5 does not document whether a bar's spread is its minimum, last or average | Phase D keeps ENG as the primary cost and uses MT5 spreads as a sensitivity only. The Phase C document gets a superseded note at the top; its text is left as written. |

### 2.3 Other findings

- **Intermarket.** Development has no intraday intermarket history: B27's DXY / US10Y / EURUSD / silver 60m data exist only for 2026, and B7's daily FRED / Yahoo series are reachable only from GitHub Actions.
  - Phase D therefore probes Dukascopy for EURUSD, XAGUSD, a US dollar index CFD and a US T-bond CFD (same file format), and uses only what is actually served.
  - The T-bond CFD is a **price**, an inverse proxy of long yields, **not** the 10-year yield.
  - COMEX order flow is unavailable free (B5 used Databento once).
- **News.** News timestamps are dated only for 2020-01-24 → 2023-01-25 and from 2026-10-28 (`b26.DATED`). January–October 2026 stays **NOT DATED**; nothing is back-filled.
- **Isolation and randomness.** Research code must stay invisible to production, and `np.random` is forbidden anywhere under `quantum/` (`test_integrity`). Phase D modules are flat `quantum/research/d_*.py` and draw randomness only from `harness.seeded_rng`.

## 3. Separation and governance

**Four tracks, kept apart.** Each has its own multiple-testing family:
1. **The ±$15 benchmark (B26), unchanged:** descriptive; it is the base rate.
2. **The order-flow-informed ±$15 family:** 5 sets × 4 algorithms × 4 rules, up to 80 strategies.
3. **The dynamic TP / SL family:** 3 ATR brackets × 3 sets × 2 algorithms × 4 rules = 72 strategies.
4. **Descriptive measurements:** P(favourable $5–$20), adverse-first, time to exit, delay, the one-minute grid, stop entries, the spread.

**B5c** stays its own registered experiment (33 trials) on the same download.

**Rules carried from the brief.** Registration came before any data. No tuning. No removed losers. No outcome redefinition. No synthetic order flow. No raw tick data in Git. Sealed periods are never downloaded. Every trial is logged.

## 4. Workstreams → code

| Workstream | Code | Tests (synthetic) |
|---|---|---|
| A — extraction | `quantum/research/d_dukascopy.py`: 15-minute sums for the ten families (`PD_COLS`), one-minute bid / ask (`M1_COLS`), intermarket mid bars; sealed-period guard; B5c-compatible day files; resumable | `tests/test_research_phase_d_data.py` |
| A — features | `quantum/research/d_features.py` (`FAMILIES_OF`: families 1–10 → 27 columns plus a missing flag); no look-ahead | the same file (`order_flow` on truncated data equals the full run) |
| A — alignment | B5c A1 / A2 gates per period, plus order-flow coverage ≥ 90% (`d_run.data_stage`) | `tests/test_research_phase_d_run.py` (a failed gate → INSUFFICIENT DATA) |
| B — M1 | `research/tools/mt5_m1_check.py` (validator); `quantum/research/d_m1.py` (bid / ask race at one minute, stop entries, worst / best bounds); `d_run.m1_study` | `tests/test_mt5_m1_check.py`; the M1 race agrees **exactly** with B26 on every trade whose 15-minute bars are unambiguous |
| C — benchmark | unchanged B26 through `b27.labels`; ENG primary; the one-minute race measures the real spread separately | as above |
| D — incremental value | `quantum/research/d_study.py`: Baseline / A / B / C / D on identical folds; log-loss gain per New York day with a stationary bootstrap; AUC, Brier, ECE, reliability next to net expectancy, PF, drawdown, frequency and CIs | `tests/test_research_phase_d_study.py`: a planted order-flow edge is found (ΔLL 0.057, CI [0.040, 0.074]); two nulls are not (p 0.37, 1.0) |
| E — ML | LR, RF, LightGBM, GB (b22's settings), multinomial P(TP / SL / neither) summing to 1; per-fit temperature from the training window only; quarterly walk-forward with a one-day exit purge; refit once and applied once to 2026 | the same file (folds never read later outcomes; every algorithm gives three probabilities) |
| F — context | sessions / hour / weekday / news proximity (Baseline), volatility / trend / structure (A), Dukascopy intermarket returns (C, only if served); no period identifiers as features | `NotAvailable` → the set is reported NOT RUN, never substituted |
| Acceptance | `d_study.criteria` (C1–C6), BH q = 0.10, White's Reality Check, Holm on 2026 | every criterion is shown necessary |
| Broker | `research/broker/BROKER_SPEC_TEMPLATE.json`, `quantum/research/d_broker.py` (refuses missing / ASSUMED values; separates $ / oz from account P&L) | the same study test file |
| Log | `quantum/research/d_log.py` (seq + SHA-256 chain; refuses to append to a broken chain) | the same study test file |
| Run | `quantum/research/d_run.py`: one resumable command on the operator's computer | the end-to-end test on a synthetic cache written by the real extractor |

## 5. Execution sequence

| Stage | What | Status |
|---|---|---|
| D0 | Audit Phase C, separation, B5c and the MT5 importer; register | **done** (sections 1–3; `PHASE_D.json`) |
| D1 | B5c / order-flow preparation and synthetic tests only | **done** (defect B5c-1 fixed; extractor, features, race and study all tested) |
| D2 | MT5 M1 preparation and exact export instructions | **done** (`PHASE_D_DATA_REQUIREMENTS.md` §3; validator v2) |
| D3 | The controlled run once data exist: `d_dukascopy` (development, then 2026), then `d_run` | **waiting on Dukascopy data** (and optionally MT5 M1 and the broker specification) |
| D4 | Independent statistical audit of D3's outputs: reproduce every figure from the committed outputs, recompute BH / Reality Check / Holm, check the log chain and coverage | after D3 |
| D5 | Final recommendation: QUALIFIES FOR FURTHER VALIDATION, NO QUALIFIED STRATEGY, or INSUFFICIENT DATA — RESEARCH INCOMPLETE | after D4. If nothing qualifies, Quantum keeps reporting NO TRADE. |

## 6. Compute estimates

| Step | Size | Time (4-core laptop) |
|---|---|---|
| Dukascopy gold, development | ~22,000 hour files (~1.5–3 GB transferred) | 30–60 min at 6 workers, resumable |
| Dukascopy gold, 2026 | ~5,500 hour files | 10–20 min |
| Cache on disk | daily CSVs of sums plus one-minute bars | ~200–400 MB |
| Intermarket (optional) | 4 instruments × both periods (EURUSD ticks are dense) | a few hours, sequential, resumable |
| B27 feature build | 72k development bars plus 2026 | ~4–6 min |
| Benchmark study | 20 walk-forwards × ~8 folds (RF / GB dominate) | ~1.5–3 h |
| Dynamic track | 9 bracket-label passes plus 18 walk-forwards | ~0.5–1 h |
| Descriptive questions | 8 labels × 3 sets × 2 algorithms | ~0.5–1 h |
| One-minute measurements | ~2.3 million races per period | 5–15 min |
| **Total** | | **≈ 1 h download plus 3–5 h compute** |

## 7. External inputs required (nothing else blocks Phase D)

1. **Dukascopy data:** an operator run of `d_dukascopy` on their computer. Dukascopy refuses GitHub's servers, and its terms restrict redistribution.
2. **Where D3 runs (operator decision):**
   - **(a) on the operator's computer** (the default; only summaries and price-free trade lists come back); or
   - **(b) the derived 15-minute sums and one-minute bars uploaded privately to this session**, never committed, for this session to run D3. Option (b) is the operator's call under Dukascopy's terms.
3. **The MT5 M1 export (optional, recommended)** for development and 2026, plus the server time zone.
4. **The broker specification** (`BROKER_SPEC_TEMPLATE.json`), for account-level P&L and drawdown. Without it, Phase D reports $ / oz and R only.
