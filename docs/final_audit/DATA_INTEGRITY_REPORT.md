# Data integrity report (2026-11-26)

**Finding: the engine's inputs and the forward ledgers are consistent, append-only and traceable. One serious defect
remains in production: the live sweep and breakout outcome records are capped and overwritten (GA-03).** A durable
replacement is built and verified on the remediation branch, and waits for approval.

## 1. Stores and records

| Store | Location | History | Integrity check | Result |
|---|---|---|---|---|
| Market data (engine input) | branch `market-data`, `quantum/data/store.py` | one orphan commit, replaced every run (by design; month files merged each run) | weekend and break-hour quotes removed before use (`quantum/data/sources.py` `trading_week_only`); independent level check below | consistent |
| Forward ledgers | branch `forward-ledger`, `holdout/*.json` | 312 normal commits, never force-pushed | `audit/tools/ledger_check.py`: attribution, duplicates, key windows, arithmetic (pts = gross − cost, R = pts / risk), level order, exit labels | **0 problems** with the closed-arm rule (`evidence/ledger_check_2026-11-26.txt`); 754 live trades under the current key, plus 13 H6 final-record trades |
| Run manifests | `forward-ledger/manifests/` (`quantum/manifest.py`) | per run | data hashes, versions, run id | present |
| Payload archive | Actions artifact `payloads-<run>-<attempt>`, kept 90 days; SHA-256 in the manifest | 90 days | `audit/tools/payload_archive_check.py` | not re-run in this round (NOT RUN) |
| Phone delivery log | `forward-ledger/notifications/*.jsonl` | union merge, never removes | `ALERT_DELIVERY_AUDIT.md` | 377 records, consistent with the monitors' records |
| **Sweep / breakout outcomes** | `market-data/alerts_state.json` (`brk.sw`, `brk.events`) | **at most 300 each; replaced every run** | — | **P0 defect in production (GA-03)** |
| Durable outcome log (branch) | `store/outcomes/` merged into `forward-ledger/outcomes/` (`quantum/outcomes.py`) | append-only, union merge | per-record SHA-256, duplicates, conflicting finals, versions missing from the log | real-record replay: 120 lines, 119 records, **0 problems** (`evidence/GA-03_outcome_log_replay.txt`) |

## 2. The durable outcome log (GA-03), how it meets the mandate

| Requirement (mandate §5) | How | Verified by |
|---|---|---|
| Never overwrite previous outcomes | append-only lines; merge is a union over (record, version) | `test_pruned_records_stay_in_the_ledger_and_a_lost_store_removes_nothing`; store-loss replay: 0 added, 0 lost |
| Every timeframe separately | `tf` on every line (level timeframe for sweeps, timeframe for breakouts); `verify` counts per kind and timeframe | replay: 8 kind / timeframe groups |
| Original signal ID and timestamp | `id`, `t`, `t_close` | schema |
| Entry, stop, targets, market conditions | the whole record as the monitor holds it: close, wick or level, +$10 / +$15 / +$20 prices, ATR, session, the A4 context; breakout shadow entries with their stop and targets | schema |
| Actual outcome and closure reason | `final`, `reason` (FAILED / MOVE20 / CLOSED / DONE) and the record's stages and results | `test_every_record_is_logged_once_with_its_finality` |
| Strategy and configuration versions | `versions`: module ids, SHA-256 of `sweeps.py` and `breakouts.py`, `GITHUB_SHA` | schema |
| Duplicates detected | `verify`: the same (record, version) twice | tamper / duplicate replay: flagged |
| Missing records detected | `verify --state`: any current record version not in the log | `test_verify_finds_tampering_duplicates_conflicts_and_unlogged_versions` |
| Recovery and backup verification | the ledger copy survives a lost store; `verify` re-checks every line | store-loss replay |
| Checksums | SHA-256 of each record's canonical JSON | tamper replay: flagged |
| Original records not deleted or migrated before verification | the module only reads `alerts_state.json` (`test_the_state_file_is_only_read`); the monitors and their caps are unchanged | — |

**Completeness of the backfill:**
- The current state holds every sweep since 23 Nov 07:24 UTC and every breakout since 19 Nov 12:22 UTC (21 and 93 at 07:33; nothing has reached the cap).
- So the first run after approval logs the full live history.
- Records pruned before then would be unrecoverable, but none have been pruned.
- At about 14 breakouts a day, the cap would start deleting around 11 Dec 2026.

## 3. Look-ahead, alignment and calculation checks

| Check | Evidence | Result |
|---|---|---|
| Engine sees only closed bars | `tests/test_engine.py::test_no_lookahead` | pass (suite) |
| Breakout and sweep detection identical from the bars closed by each event | `test_breakouts::test_no_look_ahead_every_event_is_the_same_from_the_bars_closed_by_it`, `test_sweeps::test_no_look_ahead_every_sweep_is_the_same_from_the_bars_closed_by_it` | pass |
| Confirmation panel, entry intelligence, backtest | `test_confirm_panel::test_no_look_ahead_on_every_prefix`, `test_entry_intel::test_no_look_ahead_run_by_run_equals_one_pass`, `test_backtest_gaps::test_13_no_lookahead_trades_closed_before_a_cut_are_identical` | pass |
| Higher-timeframe levels used only from the next bar | `test_sweeps::test_an_h1_swing_is_watched_on_15m_bars_from_the_next_h1_bar_and_never_before` | pass |
| Indicator maths (EMA, SMA, RMA, ATR, RSI, Bollinger, correlation, pivots, anchored VWAP, DMI / ADX, backtest metrics, Wilson) | `tests/test_independent_math.py` (14), recomputed independently of `quantum/ta.py` | pass |
| PDH / PDL / PWH / PWL cited by live alerts | `audit/tools/levels_check.py` (new; no production import; own New York 17:00 rollover and market hours) | **8 of 8 agree** (PDH 4, PDL 3, PWL 1) (`evidence/levels_check_2026-11-26.txt`). A first version without the market-hours filter disagreed on two Monday PDH levels, because the store keeps the feed's weekend quotes; production removes them and its cited level equals Friday's high |
| Timezones and DST | IANA zoneinfo (`quantum/sessions.py`; PLATFORM D-02); `test_breakouts` session-level tests | pass |
| Research partition boundaries | `harness.partition` slices bars; W4 trade file: 0 outcomes after the development end | no leakage; censoring only |

**Limits of these checks:**
- The level check covers the M15 events in the live window, a small sample.
- BOS / CHoCH / MSS, order blocks and FVG are checked by the unit tests on synthetic bars, not recomputed on live data in this round (NOT RUN).

## 4. Open data items

| Gap | Status |
|---|---|
| GA-15: research input data not kept immutably (the data hash is recorded) | BLOCKED: storage decision |
| GA-16: vendor data on public branches | BLOCKED: operator's licence check |
| GA-23: replay scripts not committed | OPEN |
| Payload archive check not re-run in this round | NOT RUN |
| Twelve Data vs Dukascopy cross-check: last scheduled result not inspected in this round | NOT RUN |
