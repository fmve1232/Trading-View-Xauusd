# XAUUSD Quantum: final independent audit report (2026-11-26)

**Verdict**

| Measure | Result |
|---|---|
| Engineering verification, production as deployed (`505f05ecc`) | **45.9%** |
| Engineering verification, production plus the remediation branch (not deployed) | **68.0%** |
| 90% designation | **not achieved** in either case, because a P0 requirement is not verified |
| Trading-performance evidence | **INSUFFICIENT**, and negative where the sample is large enough |

The two kinds of result are kept apart and never combined:
- **Engineering:** do the code, data and records do what they claim?
- **Trading:** does any strategy make money?

**Suitability**

| Use | Suitable? | Why |
|---|---|---|
| Research | yes | |
| Paper / forward recording | yes, as now | after GA-03 is merged, the records will also be durable |
| Live trading | **no** | no strategy has shown positive expectancy; costs and fills are not verified at the broker |

**Scope of this round**
- Every change is on branch `claude/session-01fdjaothuvhxscxtl7ysa-y3n4w4-remediation`. Nothing was merged or deployed.
- Production and the freeze key `1f88aad357497da4:4440d52587f5cc6b` are unchanged.
- The forward test was not touched.

## 1. What was actually investigated

| Area | Investigation | Document |
|---|---|---|
| 28 gaps | each with file, evidence, correction, tests, status | `GAP_REMEDIATION_REGISTER.md` |
| Research integrity | every trial record on 16 branches (4,045), every registration (38), every partition read, boundary leakage, selection decisions | `RESEARCH_LINEAGE_REGISTER.md` |
| Data integrity and durability | stores, ledgers (754 live trades), the alert state, look-ahead tests, an independent recomputation of the cited daily / weekly levels | `DATA_INTEGRITY_REPORT.md` |
| Broker costs | each cost input classified as measured, assumed or unverified; forward results re-costed at measured spreads | `BROKER_COST_VALIDATION.md` |
| Strategy performance | every arm and timeframe: wins, losses, average win / loss, PF, mean R with trade-level and day-clustered intervals, drawdown, streaks, holding time, exits, loss tail, power, cost sensitivity, matched random-entry baseline; why H4 loses | `STRATEGY_PERFORMANCE_REPORT.md` |
| Alert delivery | 377 delivery records against 377 SENT stages; states, duplicates, latency, the 429 loss | `ALERT_DELIVERY_AUDIT.md` |
| Forward tests | every registered test against its registered looks | `FORWARD_TEST_STATUS.md` |
| Reproducibility | pinned-environment run, GitHub checks, commands with expected outputs | `REPRODUCIBILITY_GUIDE.md` |

## 2. What was actually fixed (on the branch; production needs approval)

| Gap | Fix | Verified by |
|---|---|---|
| **GA-03** (P0) | durable, append-only outcome log, `quantum/outcomes.py`, plus a workflow step | 8 tests. Replay on the real 07:33 and 11:04 UTC states: 120 lines, 119 records, 0 problems. Pruning, store loss, tampering and duplication all behaved as designed |
| **GA-21** (P0, audit records) | the ledger checker knows the closed H6 arm | 13 → 0 problems; a planted violation is still caught |
| **GA-07** (P0, partly) | a 30 s pause before the retry after HTTP 429 | 2 tests; mutation tool 42 of 42 killed. Live effect UNVERIFIED |
| GA-09, GA-10 | `audit/tools/forward_report.py`: day-clustered intervals, random baseline, cost sensitivity, loss tail | `tests/test_forward_report.py` |
| GA-01, GA-02 | `audit/tools/lineage.py` and `research/lineage/` | reproducible from `git show` |
| GA-17 | appendix regenerated; test enforces it | the test failed on the stale appendix, then passed |
| GA-19, GA-24 | bytecode file untracked; pandas 3 joins | tests pass; 0 deprecation warnings from that tool |
| §9 | `audit/tools/levels_check.py`: independent previous-day / week levels | 8 of 8 cited levels agree |

## 3. What remains unresolved

**P0**
- **GA-07:** live effect of the 429 fix; device delivery is unobservable. This is the one P0 that is not verified on
  the branch.
- **GA-03 and GA-21:** fixed on the branch only. Production keeps the defects until the merge.

**P1**

| Gap | Status | Waiting on |
|---|---|---|
| GA-04 (broker costs), GA-05 (broker vs feed price), GA-28 (no broker fills) | BLOCKED | operator data |
| GA-06 (registration timing evidence) | OPEN | process |
| GA-08 (sample sizes) | OPEN | time |
| GA-01 erratum on the W-series documents | IN PROGRESS | — |
| GA-02 program-level multiple-testing correction | IN PROGRESS | — |

**P2:** GA-11, 12, 14/18, 15, 16, 20, 22, 23, 26. See the register.

## 4. Files and functions changed

Full list: `CHANGELOG_AND_APPROVAL_REGISTER.md` §2.

| Area | Changed |
|---|---|
| Production code | `quantum/outcomes.py` (new); `quantum/notify.py` `_deliver` and `RETRY_429_PAUSE_SEC`; `.github/workflows/quantum-site.yml` (two additions) |
| Tools | `audit/tools/ledger_check.py`, `forward_report.py` (new), `lineage.py` (new), `levels_check.py` (new), `weighted_score.py` (new), `xcheck_dukascopy.py`, `mutation_notify_delivery.py` |
| Tests | `tests/test_outcomes.py` (new), `test_forward_report.py` (new), `test_inventory.py`, `test_notify_delivery.py` |
| Records and documents | `research/lineage/`, `docs/inventory/PRODUCTION_CONSTANTS.md`, `docs/final_audit/` |

## 5. Commits and branches

**Remediation branch** `claude/session-01fdjaothuvhxscxtl7ysa-y3n4w4-remediation`:

| Commit | Contents |
|---|---|
| `55f50727e` | GA-03 |
| `ed6813c59` | audit tools |
| `acb78b4ff` | GA-07 |
| `aad2af48d` | lineage |
| the final commit of this round | documents, levels check, loss tail, score |

It is based on `claude/session-01fdjaothuvhxscxtl7ysa-y3n4w4-audit-pack` (`35c9b4627`). Production remains
`claude/audit-prompt-real-artefacts-nekqv6` at `505f05ecc`.

## 6. Test results and environment

| Check | Result | Where |
|---|---|---|
| Python suite, pinned environment (Python 3.11.18, numpy 2.4.6, pandas 3.1.1, pytest 9.2.0; Linux x86_64) at `aad2af48d` | 1,092 passed, 2 skipped (B22 tests needing the research-only `hmmlearn` / `scikit-learn`) in 7 min 45 s | local, 2026-11-26 11:28–11:36 UTC |
| JavaScript (Node v22.23.4) | 20 of 20 | local |
| GitHub `pr-checks` at `aad2af48d` (suite on `requirements.lock`, Pine checkers, manifest) | success, run 45810883836 | GitHub |
| Freeze key | `1f88aad357497da4:4440d52587f5cc6b`, unchanged | local |
| Manifest, Pine checkers, diag_parity, inventory, actionlint | 7 / 7 OK; clean; PASS; 41 modules, 47 switches, none unreferenced; 0 findings | local |
| Mutation (delivery) | 42 of 42 killed | local |
| Production runs | latest 40 `quantum-site` runs succeeded (25 Nov 21:31 → 26 Nov 07:46 UTC) | GitHub |

## 7. Actual strategy performance by timeframe

Closed trades under the current key since 15 Nov; model cost; simulated fills at feed prices.

| Arm | 5m | 15m | 30m | 1h | 4h |
|---|---|---|---|---|---|
| H4 Playbook | 410 trades, −0.138 R (days 95%: −0.209 to −0.064) | 148, −0.060 (−0.252 to +0.132) | 70, +0.028 (−0.204 to +0.402) | 37, −0.308 (−0.418 to −0.205) | 8, +0.432 (too few) |
| Treatment | 17, −0.214 | 6, +0.012 | 3, −1.039 | 4, +0.157 | 1, +1.487 |
| Challenger | 13, +0.099 | = Treatment | = Treatment | = Treatment | = Treatment |
| H3 / H5 / H2 / Control | 1–8 trades each | | | | |

**The random-entry baseline (TP1 before the stop, same geometry):**
- **5m H4 entries:** 45.7% vs 41.4% (one-sided p 0.043, uncorrected).
- **1h H4 entries:** 47.2% vs 55.8% (worse; p 0.19).

**Why 5m H4 loses:**
- 64% of its trades are closed by an opposite signal before reaching TP1 or the stop.
- Costs take 0.10 R per trade on a median $9.28 stop.

Everything is in `STRATEGY_PERFORMANCE_REPORT.md`. No registered look has been reached (`FORWARD_TEST_STATUS.md`).

## 8. Broker-cost validation evidence

| Input | Status |
|---|---|
| Asia spread | MEASURED: $0.45–0.52 |
| New York close spread | one reading, about $0.80 |
| Every other session's spread | ASSUMED |
| Commission, contract size, tick value | ASSUMED |
| Slippage | ASSUMED |
| Swap, fills | UNVERIFIED |

At a $0.50 or $0.80 spread, every negative ledger gets worse (5m H4: −0.161 / −0.197 R), and no ledger changes sign.
Validating costs needs the MT5 symbol specification, an account statement and spread samples
(`BROKER_COST_VALIDATION.md` §3).

## 9. Alert-delivery reliability

| Measure | Result |
|---|---|
| SENT stages accepted by the ntfy server | 377 of 377 |
| Sent twice | 0 |
| Bar close to acceptance | median 248 s, maximum 597 s |
| Lost to HTTP 429 | 1 stage (22 Nov 23:52 UTC), not recovered |
| Device display and acknowledgement | not observable by the system |

## 10. Data-integrity and research-lineage findings

**Data**
- The ledgers are consistent (0 problems), append-only (312 commits) and inside their key windows.
- The engine input excludes market-shut quotes, and the cited levels reproduce (8 of 8).
- The live outcome records are not durable in production (GA-03); the fix is on the branch.

**Research**
- No historical period is untouched. Validation was read by 8 studies (from 1 Nov), the holdout by 3 (B30, B31 from 15 Nov; B31b-W2).
- Partition boundaries do not leak: bars are sliced to each partition, and trades near the end are censored.
- B31's registration lists the readers wrongly; corrected in the register (GA-27).
- 4,045 trial records exist; Holm is applied only within studies.

## 11. Weighted completion score

Computed by `audit/tools/weighted_score.py`; output in `evidence/weighted_score_2026-11-26.json`.

**Rules**
- A requirement counts only when VERIFIED with evidence. OPEN, FAIL, UNVERIFIED, NOT RUN and BLOCKED count 0.
- A failed P0 requirement blocks the 90% designation whatever the total.

| Category (weight) | Production as deployed | With the remediation branch |
|---|---|---|
| Data integrity and durability (20%) | 3 / 8 | 5 / 8 |
| Strategy and statistical validation (20%) | 3 / 9 | 7 / 9 |
| Execution cost and risk accuracy (15%) | 3 / 8 | 4 / 8 |
| Signal and alert reliability (15%) | 6 / 8 | 6 / 8 |
| Research integrity (10%) | 2 / 6 | 4 / 6 |
| Automated testing and reproducibility (10%) | 6 / 8 | 6 / 8 |
| Monitoring and operational reliability (5%) | 3 / 5 | 3 / 5 |
| Documentation and traceability (5%) | 1 / 5 | 4 / 5 |
| **Weighted total** | **45.9%** | **68.0%** |
| P0 requirements not verified | D4 (audit tool), D5 (durability), A5 (rate-limit loss) | A5 |
| Designation | 90% NOT ACHIEVED | 90% NOT ACHIEVED |

Production = 0.20 × 3/8 + 0.20 × 3/9 + 0.15 × 3/8 + 0.15 × 6/8 + 0.10 × 2/6 + 0.10 × 6/8 + 0.05 × 3/5 + 0.05 × 1/5
= 45.9%. The branch column uses the same formula on its column.

**What stands between 68% and 90%:**
- **Operator data:**
  - the MT5 specification, statements and spreads would add up to 4 cost requirements (+7.5 points);
  - storage and licence decisions would add D7 and D8 (+5 points).
- **Live evidence:** a 429 handled without loss (A5), the cross-check inspected (O5), the payload archive checked
  (D6).
- **Process:** server-side registration times (R1) and the W-series errata (C5).
- **Never available:** R5 (an untouched historical holdout) is spent for good. S9 (untouched out-of-sample data of
  sufficient size) depends on time.

## 12. Risks requiring the operator's approval

`CHANGELOG_AND_APPROVAL_REGISTER.md` §3 has the full list.

- **Merge GA-03.** Without it, breakout records start to be deleted around 11 Dec.
- **Merge GA-07.**
- **Merge the audit tools.**
- **Provide broker data.**
- **Decide data storage and licensing.**
- **Approve registrations on GitHub.**
- **Approve the alert-wording changes** (GA-11, GA-12).

## 13. Suitability

| Use | Verdict | Evidence |
|---|---|---|
| Research | **Suitable** | reproducible tooling, append-only records, look-ahead tests, lineage |
| Paper trading / forward recording | **Suitable as it runs now**, and fully so once GA-03 is merged (records durable) | `DATA_INTEGRITY_REPORT.md` |
| Live trading | **Not suitable** | no strategy with positive expectancy (`STRATEGY_PERFORMANCE_REPORT.md`); two H4 ledgers reliably negative; costs and fills unverified at the broker (`BROKER_COST_VALIDATION.md`); no registered forward look reached (`FORWARD_TEST_STATUS.md`) |

Even a 90% engineering score would not mean a 90% chance of a winning trade. That can only come from statistically
valid, untouched forward evidence, which does not yet exist.

## 14. Evidence index

| Claim | Evidence |
|---|---|
| Outcome-log replay | `evidence/GA-03_outcome_log_replay.txt` |
| Ledger consistency | `evidence/ledger_check_2026-11-26.txt` |
| Forward statistics | `evidence/forward_report_2026-11-26.json` and `.txt` |
| Delivery cross-check | `evidence/alert_delivery_2026-11-26.txt` |
| Level check | `evidence/levels_check_2026-11-26.txt` |
| Score | `evidence/weighted_score_2026-11-26.json` |
| Lineage | `research/lineage/` |
