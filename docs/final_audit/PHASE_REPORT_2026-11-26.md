# Phase report for the next audit (2026-11-26)

This report follows the operator's decision of 26 Nov 2026 and its reporting requirements.

**Status:** live trading NOT APPROVED and not done; paper (forward) testing continuing, unchanged; research continuing.

## Summary

| | |
|---|---|
| Engineering score | 45.9 % → 68.0 % (production). Designation: **90 % NOT ACHIEVED**: P0 item A5 is unverified, and the total is below 90 % |
| Trading edge | **None shown.** No arm or timeframe beats matched random entries after a multiple-testing correction. H4 is negative on 5m, 15m and 1h |
| Production | `c59d49bca` (PR #141 and #142 merged). Engine frozen; freeze key `1f88aad357497da4:4440d52587f5cc6b` unchanged |
| Open for approval | PR #143 (H4 forward diagnosis) and the PR carrying this report. Both are records and tools only |

## 1. Previous and current score

Source: `audit/tools/weighted_score.py`; evidence `evidence/weighted_score_2026-11-26_phase.json`. Engineering only;
trading performance is not part of it.

| | Before (26 Nov 11:04, production `505f05ecc`) | Now (production `c59d49bca`) |
|---|---:|---:|
| Weighted total | 45.9 % | **68.0 %** |
| Data (20 %) | 3 / 8 | 5 / 8 |
| Statistics (20 %) | 3 / 9 | 7 / 9 |
| Cost (15 %) | 3 / 8 | 4 / 8 |
| Alerts (15 %) | 6 / 8 | 6 / 8 |
| Research (10 %) | 2 / 6 | 4 / 6 |
| Tests (10 %) | 6 / 8 | 6 / 8 |
| Operations (5 %) | 3 / 5 | 3 / 5 |
| Documents (5 %) | 1 / 5 | 4 / 5 |
| P0 not verified | D4, D5, A5 | **A5** (rate-limit resilience: the fix is merged, but no HTTP 429 has occurred since) |

**What changed the score:**
- Merging the approved remediation (PR #141).
- The branch figures of the last round are now true in production, and each was verified on production runs
  (§3).
- No requirement was added, removed or re-weighted.
- The chronology work (§8) leaves R1 UNVERIFIED: 9 registrations cannot be ordered by server time.

## 2. Remaining gaps, with severity

P0 = data loss, false alerts, wrong calculations, execution risk, broken records. P1 = statistical validity, forward
testing, costs, signal reliability. P2 = reproducibility, monitoring, documents.

| Gap | Severity | Status | What closes it |
|---|---|---|---|
| A5 / GA-07: an alert lost to ntfy's rate limit | P0 | MITIGATED (30 s pause merged), live effect UNVERIFIED | a real 429 recovered, or an account-based ntfy token (operator decision) |
| A6: delivery to and display on the phone | P1 | NOT VERIFIABLE with ntfy; the records now say so (`PHONE_DELIVERY` / `PHONE_DISPLAY` = NOT_VERIFIABLE) | an acknowledgement on the device (needs approval) or an operator reconciliation of the ntfy app list |
| GA-04 / GA-05 / GA-28: broker contract, costs and fills | P1 | BLOCKED on the operator | MT5 symbol specification, an account statement with fills, spread samples per session |
| GA-01 / GA-08: no untouched out-of-sample data; small forward samples | P1 | OPEN | forward records reaching the registered looks (§6 power column) |
| GA-02: multiple-testing correction over all 4,045 research trials | P1 | OPEN | the forward comparisons are corrected (Holm / BH, §5); the research programme as a whole is not |
| GA-13: no calibrated probability | P1 | OPEN | none until a study passes; alerts show no unverified probability (decision D, merged) |
| GA-06: registration before code | P1 | 26 of 38 PROVEN by GitHub push times; 9 same push; 0 after; 3 no evidence (§8) | registrations pushed (or approved on GitHub) before any code, in a separate push |
| GA-15: research input data not immutable | P1 | BLOCKED (storage decision) | a private, hash-addressed copy |
| GA-16: vendor data licences | P2 | BLOCKED (operator) | the operator checks each vendor's terms |
| GA-11 (B5c order-flow study) | P2 | BLOCKED (operator's laptop) | run B5c |
| GA-14 / GA-18: W-series research code only on branches | P2 | OPEN | merge as research-only code |
| GA-20: about 69 branches | P2 | OPEN | archive finished branches (deletion is outward-facing: operator approval) |
| GA-22: research-history workflow fails at a normal end of history | P2 | OPEN | treat "no data before the first bar" as the end |
| GA-23: replay tool not committed | P2 | OPEN | commit the replay as a tested tool |
| GA-26: two spellings of the holdout end | P2 | OPEN | one spelling |
| New: point-in-time revision of a 5m bar (22 Nov 23:00) | P1 | FOUND (H4 diagnosis §6) | keep the bars each run used (the payload archive, D6) and compare |
| New: a date error in `BROKER_COST_VALIDATION.md` | P2 | CORRECTED here (§7) | — |

## 3. Files, functions and commits of this phase

**Merged to production with the operator's approval:**

| Commit | What | Verification |
|---|---|---|
| `db7cd6a14` (PR #141, head `fde25ed99`) | durable outcome log (`quantum/outcomes.py`, workflow step); 429 retry pause (`notify._deliver`, `RETRY_429_PAUSE_SEC`); audit tools; ten audit documents | pr-checks 45831024797: both jobs success. Production run 45832483937: success; outcome log 120 lines = store copy; `--verify` problems [] |
| `c59d49bca` (PR #142, head `bee33142c`) | decision B (`notify.delivery_status`, `STATUS_NAMES`; status on every delivery record; `levels_accepted_utc`; site labels; `audit/tools/delivery_status.py`); decision D (`sweeps.POC_KIND`, `MACRO_HEAD`, `context_lines`; `notify.SETUP_POC_KIND`, `NO_EDGE_NOTE`) | pr-checks on `bee33142c`: both success. Production run 45837411129: success. The two sweep alerts it sent carry the new lines and statuses; stored vs recomputed statuses: 0 disagreements |

**Open, awaiting approval (records and tools only):**
- PR #143 `97f33a860`: `audit/tools/h4_forward_diagnosis.py` and `docs/final_audit/H4_FORWARD_DIAGNOSIS.md`, with
  evidence.
- This report's PR:
  - `audit/tools/registration_chronology.py` (§8);
  - `weighted_score.py`, updated for what is merged;
  - this report and its evidence;
  - the erratum in `BROKER_COST_VALIDATION.md`.

**Not changed:**
- the engine sources, `config.py`, the frozen Pine files, any registration or forward record, and any stop, target or
  threshold;
- B24 stays OFF.

## 4. Tests

| Check | Result |
|---|---|
| Full suite, pinned `requirements.lock` (PR #142 head) | **1,104 passed, 2 skipped** |
| Skipped | the two B22 research tests that need `hmmlearn` and `scikit-learn`. These are research-only extras, not in the production lock file |
| GitHub pr-checks, PR #141 / #142 heads | success (full suite on `requirements.lock`; Pine checkers and frozen-file manifest) |
| Delivery mutation test | 46 of 46 mutants killed (D39–D42 new for decision B) |
| JavaScript tests | 20 of 20 |
| H4 diagnosis tool | 44 tests, among them its exit replica against `backtest.simulate` on 40 random paths with gaps |
| Delivery-status tool | 10 tests (the tool and the system agree on 9 delivery paths) |
| Chronology tool | 3 tests on a scripted repository (first push, first study line, definition vs mention) |
| Freeze key, manifest | recomputed on each merged tree: unchanged; 7 of 7 OK |

## 5. Reproduced performance calculations

- **`forward_report.py`** was re-run on `forward-ledger` `624ed94d2` and `market-data` `092e2c41e` (evidence
  `forward_report_2026-11-26_phase.json` / `.txt`). Its figures for the earlier inputs match the 26 Nov 11:04
  evidence.
- **The H4 exits were reproduced independently.** The diagnosis tool re-implements the backtest exit model and
  reproduces 260 of 261 recorded non-flip exits. The one miss is a store bar revised after the run.
- **Correction to the last round.** The last round's "5m H4 entries 45.7 % TP1-first vs 41.4 % random" compared
  against random entries at any time of day.
  - Against matched twins (same UTC hour, direction, distances, cost and follow-up), the difference disappears:
    45.7 % against 47.6 % (p 0.40).
  - No comparison survives Holm or BH: H4 alone, 18–30 tests; all seven arms, 54–66 tests.
  - The last round's "entries better than random" reading is withdrawn (`H4_FORWARD_DIAGNOSIS.md` §5).

## 6. Strategy-wise and timeframe-wise forward results (paper), with sample sizes and intervals

Freeze key `1f88aad357497da4:4440d52587f5cc6b`, 15 Nov 11:46 → 26 Nov 13:50 UTC; costs of record.

| Arm, timeframe | Trades (days) | Win rate (Wilson 95 %) | Mean R | 95 % by trades | 95 % by days | Profit factor | Max drawdown R | n for 80 % power at 0.10 R |
|---|---:|---|---:|---|---|---:|---:|---:|
| H4 5m | 413 (11) | 34.6 % (30.2–39.3) | −0.136 | −0.210 … −0.060 | −0.206 … −0.061 | 0.65 | 59.6 | 482 |
| H4 15m | 149 (10) | 40.3 % (32.7–48.3) | −0.065 | −0.189 … +0.063 | −0.257 … +0.125 | 0.82 | 14.3 | 488 |
| H4 30m | 71 (10) | 40.8 % (30.2–52.5) | +0.032 | −0.172 … +0.250 | −0.192 … +0.392 | 1.10 | 11.6 | 649 |
| H4 1h | 38 (9) | 34.2 % (21.2–50.1) | −0.293 | −0.497 … −0.081 | −0.400 … −0.194 | 0.37 | 11.4 | 350 |
| H4 4h | 8 (7) | 62.5 % (30.6–86.3) | +0.432 | −0.090 … +1.009 | −0.063 … +1.033 | 3.91 | 0.7 | 580 |
| Treatment 5m | 17 (8) | 35.3 % (17.3–58.7) | −0.214 | −0.798 … +0.464 | −0.886 … +0.592 | 0.70 | 6.8 | 1,523 |
| Challenger 5m | 13 (7) | 46.2 % (23.2–70.9) | +0.099 | −0.674 … +0.951 | −0.794 … +1.191 | 1.17 | 4.5 | 1,859 |
| Treatment / Challenger 15m | 6 each | 50 % | +0.012 | −0.73 … +0.81 | — | 1.02 | — | — |
| H3 5m | 8 | 50 % | +0.865 | −0.69 … +2.63 | −0.62 … +2.76 | 2.49 | — | — |
| H5 5m | 7 | 14 % | −0.686 | −1.13 … +0.16 | −1.12 … +0.37 | 0.28 | — | — |

- The other ledgers have 1–4 trades; they are in the evidence JSON, with no interval.
- **H4 is significantly negative on 5m and 1h**: both intervals exclude zero.
- No ledger is significantly positive.
- No forward test has reached the sample its power calculation needs.

## 7. Broker costs: actual against assumed

| Input | Assumed (engine) | Actual | Status |
|---|---|---|---|
| Spread, Asia | $0.30 / oz | $0.45–0.52 (M15), $0.49–0.61 (M30), $0.33–0.55 (H1), from screenshots of 19 and 25 Nov | MEASURED (2 sets) |
| Spread, New York close | $0.30 | about $0.80, one reading near the daily rollover | MEASURED once (see the erratum below) |
| Spread, London / New York / overlap | $0.30 | — | ASSUMED |
| Commission | $7 per lot round trip | — | ASSUMED |
| Slippage | $0.20 per side | — | ASSUMED |
| Contract size, tick value | 100 oz; $1 per $0.01 per lot | — | ASSUMED |
| Swap | not modelled | — | UNVERIFIED |
| Fills at stop / target | simulated (gap at the open, stop first) | — | never compared with broker fills |

- **Effect of the measured spreads.** At the measured spreads, every negative ledger gets more negative. 5m is hit
  hardest: the cost is already 0.099 R per trade at the assumed $0.30 spread.
- **What closes it:** the MT5 symbol specification, an account statement with fills, and spread samples per session.
  All are requested from the operator; nothing is invented in their place.
- **Erratum, `BROKER_COST_VALIDATION.md` §1.** It dated the New York-close reading "20:55 UTC on 26 Nov". That time
  had not occurred when the document was written.
  - The reading comes from the operator's screenshots reviewed for 23–25 Nov.
  - Its day, and the time zone of its 20:55 clock, are in the operator's private files and cannot be re-checked here.
  - The document now says so.

## 8. Registration chronology (GA-06), from GitHub's own push times

**Tool and method:**
- `audit/tools/registration_chronology.py` reads the repository activity API, a server-side record of every push and
  merge since 7 Sep 2026.
- For each registration it finds the first push of three commits: the commit that added the registration, the first
  commit that defined the study in code, and the first commit that wrote a result.
- Evidence: `evidence/registration_chronology_2026-11-26.json` / `.txt`.

| Verdict | Count | Registrations |
|---|---:|---|
| BEFORE: the registration reached GitHub before any code or result | 26 | B13, B14, B15-ENGINE-FWD, B16, B17, B18, B19, B20, B21, B22, B23, B24-CONFIRM-FWD, B25, B30, B31, B31b-SHADOW-FWD, B31b-W1, -W2, -W3, -W4, -W5, -W7, -W8, -W8-cost, -W12, -W13 |
| SAME_PUSH: registration and first code / result arrived in one push; only the commit order (parent links) shows the registration first | 9 | B4-RN-V1, B9-GRAB-FWD, B10, B15b-ENGINE-FWD, B26, B27, B28, B29, PHASE_D |
| AFTER | 0 | — |
| NO_EVIDENCE: no code or result (amendments; a study not run) | 3 | B24-CONFIRM-FWD-A1, -A2, B5C |

**Notes:**
- **Same push.** In all 9 SAME_PUSH cases the registration commit is an ancestor of the first evidence commit.
  Commit order is not proof of time, so R1 stays UNVERIFIED.
- **Gap when BEFORE.** Median 0.1 hours, range 0.01–48 hours. A registration minutes before its code is proven
  first, but it was not reviewed by anyone in between.
- **Shallow clone.** The session's clone was shallow.
  - A first run on it gave 22 BEFORE / 13 SAME_PUSH. It credited B19–B22 to a later push that held their commits.
  - The code branches' history was then fetched back to 28 Oct, before the first registration (1 Nov 16:12 UTC).
  - The rerun (the evidence file) separates B19's registration, code and first result into three pushes on 6 Nov
    (22:48, 22:54 and 23:04 UTC).
  - The remaining unresolved pushes are on `forward-ledger`, `research-data` and `research-orderflow`, or before
    1 Nov. `research-orderflow` holds B5's results, and B5 has no registration file among the 38.
- **Forward ledger.** `forward-ledger` has 3,572 pushes since 27 Sep 2026 and no force push. This is server evidence
  for requirement D2.

## 9. Alert delivery and failures

Records: `forward-ledger` `notifications/` to 26 Nov 14:22 UTC; tool `audit/tools/delivery_status.py`.

| Measure | Value |
|---|---|
| Attempt records / messages | 383 / 382 (15–26 Nov) |
| `SENT_TO_NTFY` | YES 381, NO 1 |
| `SEND_FAILED` / `RETRY_ATTEMPTED` | 1 / 1 (the same message) |
| `PHONE_DELIVERY` / `PHONE_DISPLAY` | NOT_VERIFIABLE for all 382 |
| Lost message | the 22 Nov 23:52 UTC breakout stage: HTTP 429 twice, 5 s apart (before the 30 s pause) |
| Duplicates | 0 event keys accepted twice (to 26 Nov 11:04) |
| Bar close → server accepted | median 248 s, 90th percentile 454 s, maximum 597 s (377 records to 26 Nov 11:04) |
| Records with the new status block | 2 (the first run after the merge); stored and recomputed statuses agree |
| By stream | breakouts 259 (1 lost), sweeps 54, 15m engine 26, key zones 21, C1 confirmations 13, daily report 9 |

## 10. Status of each part

| Part | Status |
|---|---|
| Live trading, automatic execution, MT5 orders | **NOT APPROVED; none exists.** No order path in the code |
| Phone alerts | **PAPER / MONITORING.** Trade alerts open "RECORD — NOT A VALIDATED SIGNAL — NO TRADE"; breakout and sweep alerts say "Entry: Not validated"; no unverified probability is shown |
| Forward tests: treatment, control, challenger, H2–H5, B9, B15b, B31b shadow | **PAPER**, untouched, records append-only (H6 closed by Amendment F; B15 ended, B15b running) |
| Research (B-series, W-series, Phase C / D) | **RESEARCH.** Development data only unless a registration opened more; validation and holdout already read by B4-V, B13, B19, B23, CF-VALIDATION, B30, B31 and B31b-W2 |
| Engine | **FROZEN**, freeze key `1f88aad357497da4:4440d52587f5cc6b` |
