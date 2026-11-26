# Gap remediation register (2026-11-26)

This register lists every gap from `docs/AUDIT_PACK.md` (GA-01 … GA-26) and two found in this round (GA-27, GA-28).

**How the work was done**
- Fixes were made on branch `claude/session-01fdjaothuvhxscxtl7ysa-y3n4w4-remediation`, never on production.
- Production is still commit `505f05ecc`, with freeze key `1f88aad357497da4:4440d52587f5cc6b`.
- A fix reaches production only after the operator approves the merge.

**Priority** (from the mandate)
- **P0:** data loss, false alerts, incorrect calculations, execution risk, broken audit records.
- **P1:** statistical validity, forward testing, broker costs, signal reliability.
- **P2:** reproducibility, monitoring, documentation, usability.

**Status**

| Status | Meaning |
|---|---|
| VERIFIED (branch) | fixed on the remediation branch and checked by a test or by real records; production needs the operator's approval |
| VERIFIED | true now, with evidence; no change needed |
| IN PROGRESS | part done; the rest is named |
| OPEN | not done |
| BLOCKED | needs something only the operator can provide |

A gap is never closed by documentation alone.

**Evidence files** are in `docs/final_audit/evidence/`. Commits are on the remediation branch:

| Commit | Contents |
|---|---|
| `55f50727e` | outcome log |
| `ed6813c59` | audit tools |
| `acb78b4ff` | 429 pause |
| `aad2af48d` | lineage |
| (final commit) | levels check, loss tail, these documents |

## Priority 0

| ID | Gap | Affected code | Evidence | Correction | Tests and before / after | Approval | Status |
|---|---|---|---|---|---|---|---|
| GA-03 | Live sweep and breakout outcome records are capped at 300 each and kept in a branch replaced every run | `quantum/sweeps.py` `scan` (KEEP), `quantum/breakouts.py` `scan` (KEEP_EVENTS), `.github/workflows/quantum-site.yml` (store save) | `market-data` has 1 commit; caps in code; the W7 registration says records are "kept" | New `quantum/outcomes.py` (`append`, `merge_ledger`, `verify`): each record version appended once, with its SHA-256, into `store/outcomes/`, then merged by union into `forward-ledger/outcomes/` (never force-pushed). Two workflow lines. Detection, alerts and engine unchanged | `tests/test_outcomes.py` (8). Real-record replay: 120 lines for 119 records, 0 problems; pruning 60 records lost none; store loss removed nothing; a tamper and a duplicate were flagged (`GA-03_outcome_log_replay.txt`). Before: 300 cap, 1 orphan commit. After: every version kept | **Yes** (workflow and new module) | VERIFIED (branch) |
| GA-07 | Phone alerts can be lost to the ntfy rate limit; device display is not observable | `quantum/notify.py` `_deliver` | 2 RETRY_FAILED rows (HTTP 429, 22 Nov 23:52 UTC; 1 message); 375 DELIVERY_UNCONFIRMED (`alert_delivery_2026-11-26.txt`) | `RETRY_429_PAUSE_SEC = 30` before the one retry after a 429; other failures keep 5 s. Device display cannot be measured by the system | `test_a_rate_limited_send_waits_longer_before_its_one_retry`, `test_a_rate_limited_channel_waits_once_per_run`; mutation tool 42 of 42 killed (new D27b). Effect on a shared-IP limit: UNVERIFIED until it meets a real 429 | **Yes** (alert timing) | IN PROGRESS: fix VERIFIED (branch); live effect and device delivery UNVERIFIED |
| GA-21 | The ledger checker reported 13 false "problems" (H6's final record after its closure) | `audit/tools/ledger_check.py` | 13 flags, all H6 trades of 5–13 Nov | Closed-arm rule: a closed arm's trade is valid under its own key when entered before the closure | Real ledger: 13 → 0 problems; a planted H6 trade after the closure is still flagged (`ledger_check_2026-11-26.txt`) | No (audit tool) | VERIFIED (branch) |

## Priority 1

| ID | Gap | Affected code / record | Evidence | Correction | Tests and before / after | Approval | Status |
|---|---|---|---|---|---|---|---|
| GA-01 | The 2023–25 "out-of-sample" history was already read | `research/trials.jsonl` (all branches); `research/registrations/B31.json` | Partition-access ledger: validation read by B4-V, B13, B19, B23, CF-VALIDATION, B30, B31, B31b-W2; holdout by B30, B31, B31b-W2 (`research/lineage/partition_access.json`) | Partition-use ledger built (`audit/tools/lineage.py`); `RESEARCH_LINEAGE_REGISTER.md` states that no historical period is untouched; the forward period from 15 Nov is the only unseen data | Lineage tool reproducible from `git show` | No (records) | IN PROGRESS: ledger VERIFIED (branch); erratum notes on the W-series documents (on their own branches) not yet appended |
| GA-02 | The trial log is split across branches and undercounts hypotheses | `research/trials.jsonl` | 1,560 lines on production; 4,045 distinct records across 16 branches | `research/lineage/trials_union.jsonl`: every distinct record once, with its branches; no original line changed | Counts recomputed by the tool | Yes (to merge records) | IN PROGRESS: union VERIFIED (branch). A program-level correction (Deflated Sharpe / PBO over all trials) is not yet computed, because many records hold summaries, not trade series |
| GA-04 | Broker costs are not verified | `quantum/config.py` (spread 0.30, slippage 0.20, commission 7), `B31b-W8-cost.json` | MT5 screenshots: Asia $0.45–0.52; about $0.80 at 20:55 UTC (1 reading). Commission, contract size and swap: ASSUMED | `BROKER_COST_VALIDATION.md`: verified vs estimated, and the forward ledgers re-costed at $0.50 / $0.80 | `forward_report.py` `mean_r_at_spread` | — | BLOCKED: needs the MT5 symbol specification and an account statement |
| GA-05 | Feed price vs broker price | `notify.py` (`MT5_PRICE_OFFSET`), `quantum/mt5.py` (not connected) | $0.4–0.5 difference in screenshots | Per-session comparison of an MT5 M1 export with the feed (importer on `research-phase-d`) | — | — | BLOCKED: needs an MT5 M1 export or a MetaApi connection |
| GA-06 | "Registered before code" rests on author-set commit times | `research/registrations/*` | `research/lineage/registrations.json` holds committer dates only | Use GitHub's server-side times, or the operator's approval on GitHub, for future registrations | — | Process decision | OPEN |
| GA-08 | Live samples are small; no registered look reached | `research_forward/*.json`, `holdout/*.json` | B15b 20 of 30; B9 23 of 30; sweeps 21 (100 per level timeframe registered) | None possible except time, plus GA-03 so the records survive | `FORWARD_TEST_STATUS.md` | — | OPEN (time) |
| GA-09 | Forward statistics assumed independent trades | `audit/tools/forward_stats.py` | Trade-level bootstrap only | `audit/tools/forward_report.py`: day-clustered bootstrap next to the trade-level one | `tests/test_forward_report.py` (clustering widens the interval when one day carries the result). 5m H4 day-clustered 95%: −0.209 to −0.064 R | No (audit tool) | VERIFIED (branch) |
| GA-10 | The loss tail was not reported | forward summaries | Worst gap losses of $6,061 (W5) and $2,922 (W7) on $650 plans in history | `forward_report.py`: worst trade, share below −1 R, 1st percentile | Forward worst trade −1.25 R (5m H4); share below −1 R: 14.6% (5m H4), 29.7% (1h H4) | No | VERIFIED (branch) for the forward ledgers; the historical study files keep their own tails |
| GA-13 | No calibrated probability exists | `site/app.js`, `report.py` | Engine `p` labelled NOT CALIBRATED; B22 AUC 0.47–0.51 | None until a supported mechanism exists; labels kept | `test_uncalibrated_labels` | — | VERIFIED (labels correct; nothing to calibrate) |
| GA-28 *(new)* | Forward results are simulated fills at feed prices, not broker fills | `quantum/backtest.py` (`simulate`), `holdout/*.json` | Every ledger trade is the engine's simulated fill on Twelve Data bars; no broker statement has been compared | Compare with account statements for any trade actually taken | — | — | BLOCKED: needs account statements |

## Priority 2

| ID | Gap | Affected | Correction | Evidence | Approval | Status |
|---|---|---|---|---|---|---|
| GA-11 | Order flow and volume are proxies | `sweeps.tpo_poc`, `features.py` volume profile (D-07) | Name the POC type in alerts and on the site; run B5c | — | Yes (alert text) | OPEN; B5c BLOCKED (operator's laptop) |
| GA-12 | Intraday DXY / US10Y context has no historical test | `sweeps.context_lines`, `market-data` DX-Y.NYB / ^TNX 60m from 2024-05 | Label the lines "context, untested" | — | Yes (alert text) | OPEN |
| GA-14 / GA-18 | W3–W13 research code exists only on branches | `quantum/research/w*.py` | Merge as research-only code (`test_integrity` forbids production imports) | — | Yes | OPEN |
| GA-15 | Research input data is not kept immutably | `research-data` (one force-pushed commit) | A private, immutable copy per data hash | — | Operator decision (storage) | BLOCKED |
| GA-16 | Vendor data on public branches | `market-data`, `research-data` | The operator checks each vendor's terms | — | Operator | BLOCKED |
| GA-17 | The inventory appendix was stale and nothing enforced it | `docs/inventory/PRODUCTION_CONSTANTS.md`, `tests/test_inventory.py` | Regenerated; new test compares it with the tool's output | The test failed on the stale file, then passed after regeneration (41 modules) | No | VERIFIED (branch) |
| GA-19 | Tracked bytecode file | `audit/tools/__pycache__/trace.cpython-311.pyc` | Removed from the index (`__pycache__/` already ignored) | `git ls-files` lists 0 `.pyc` | No | VERIFIED (branch) |
| GA-20 | A stale `prod` branch and about 60 branches | repository | Name the production branch in the README; archive finished branches | — | Yes (branch deletion is outward-facing) | OPEN |
| GA-22 | The research-history workflow fails on a normal end of history | `.github/workflows/research-history.yml`, `quantum/research/history.py` | Treat "no data before the first bar" as the end | — | Yes | OPEN |
| GA-23 | Replays depend on 2-decimal rounding; the replay scripts are not committed | `report.py` | Commit the replay as a tool with a test | — | No | OPEN |
| GA-24 | pandas 3 deprecation in the cross-check tool | `audit/tools/xcheck_dukascopy.py` (`mid_minutes`, `compare`, the GC basis join) | `pd.merge(..., suffixes=...)`, the same semantics | `tests/test_xcheck.py` passes on both versions; 0 suffix warnings after | No | VERIFIED (branch) |
| GA-25 | The A/B comparison carries information on 5m only | ledgers | None (a property of this window) | Treatment = Challenger on 15m / 30m / 1h / 4h | — | VERIFIED (documented) |
| GA-26 | Two spellings of the holdout end | documents | One spelling | — | No | OPEN |
| GA-27 *(new)* | B31's registration lists B10 and B20–B22 among the studies that read validation / holdout; their records and documents show development only. It also omits CF-VALIDATION and B4-V | `research/registrations/B31.json` line 12 | The registration is not rewritten (registrations are immutable); the correction is in `RESEARCH_LINEAGE_REGISTER.md` | `partition_access.json` | No | VERIFIED (erratum recorded) |

## Totals

| Status | Count | Gaps |
|---|---|---|
| VERIFIED (branch) | 7 | GA-03, GA-09, GA-10, GA-17, GA-19, GA-21, GA-24 |
| VERIFIED | 3 | GA-13, GA-25, GA-27 |
| IN PROGRESS | 3 | GA-01, GA-02, GA-07 |
| OPEN | 9 | GA-06, GA-08, GA-11, GA-12, GA-14/18, GA-20, GA-22, GA-23, GA-26 |
| BLOCKED on the operator | 5 | GA-04, GA-05, GA-15, GA-16, GA-28 (GA-11's B5c run too) |

The 27 rows cover all 28 IDs; GA-14 and GA-18 share one row.

**P0 status**
- **In production:** GA-03 and GA-07 are open, because their fixes are not merged.
- **On the branch:**
  - GA-03 and GA-21 are fixed.
  - GA-07 is mitigated, but its live effect is unverified, and device delivery cannot be verified by the system.
