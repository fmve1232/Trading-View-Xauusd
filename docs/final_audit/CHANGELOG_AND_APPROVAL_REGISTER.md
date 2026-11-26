# Changelog and approval register (2026-11-26)

**Nothing in this round was merged or deployed. Production is unchanged.**

| | Branch | Commit | Freeze key |
|---|---|---|---|
| Production | `claude/audit-prompt-real-artefacts-nekqv6` | `505f05ecc` | `1f88aad357497da4:4440d52587f5cc6b`, recomputed today, unchanged |
| Remediation (all changes below) | `claude/session-01fdjaothuvhxscxtl7ysa-y3n4w4-remediation` | — | unchanged on this branch too |

The remediation branch starts from the audit pack (`claude/session-01fdjaothuvhxscxtl7ysa-y3n4w4-audit-pack`,
`35c9b4627`).

No engine source (`holdout.ENGINE_SOURCES`), `quantum/config.py`, frozen Pine file, registered rule, forward record or
historical dataset was changed.

## 1. Immutable baseline (recorded before any change)

| Item | Value |
|---|---|
| Production commit | `505f05ecc59b76393dd5b6c9fb21f9363db40f68` (2026-11-25) |
| Freeze key | `1f88aad357497da4:4440d52587f5cc6b` |
| `quantum/config.py` SHA-256 | `3ea5827a0de7465b53e934b6ba50690e496e776aa2383acffa412bd2b46d67fc` |
| `forward-ledger` head | `c8a99d64e7e79866fffeea0b45befe9765f816df` (2026-11-26 11:04:17 UTC) |
| `market-data` head | `054751950fe251beb23db3eaee9a14de4229e265` (2026-11-26 11:04:14 UTC); `alerts_state.json` SHA-256 `e562417ca6ac284fa73283216865ba2cd5832f0005df7d7c939a522a8bc0de14` |
| `research-data` head | `daae39c7c4cb651e2557e5b741abef293995147a` (2026-11-25) |
| Engine sources | `ta.py`, `sessions.py`, `features.py`, `analog.py`, `engine.py`, `backtest.py`, `config.py`, `pipeline.py`, `data/sources.py`, `data/market.py`, `data/store.py` |

## 2. Commits on the remediation branch

| Commit | Gap | Files and functions | Production effect if merged |
|---|---|---|---|
| `55f50727e` | GA-03 | **new** `quantum/outcomes.py` (`canonical`, `sha`, `versions`, `final_reason`, `records`, `read_dir`, `append`, `merge_ledger`, `verify`, `main`); `.github/workflows/quantum-site.yml` (a step "Durable outcome log" before the store save; a merge line in "Save the forward ledger"); **new** `tests/test_outcomes.py`; evidence | every run appends record versions to `store/outcomes/` and merges them into `forward-ledger/outcomes/`; alerts and detection unchanged |
| `ed6813c59` | GA-21, GA-09, GA-17, GA-24, GA-19 | `audit/tools/ledger_check.py` (`CLOSED_ARMS`, the closed-arm branch in `check`); **new** `audit/tools/forward_report.py`, `tests/test_forward_report.py`; `tests/test_inventory.py` (`test_the_committed_appendix_is_what_the_tool_generates_now`); `docs/inventory/PRODUCTION_CONSTANTS.md` regenerated; `audit/tools/xcheck_dukascopy.py` (`mid_minutes`, `compare`, the GC basis join: `pd.merge(..., suffixes=...)`); `audit/tools/__pycache__/trace.cpython-311.pyc` untracked | audit tools only. `xcheck_dukascopy.py` runs in the scheduled `xcheck-dukascopy` workflow, with the same results |
| `acb78b4ff` | GA-07 | `quantum/notify.py` (`RETRY_429_PAUSE_SEC`; the pause before attempt 2 in `_deliver`); `tests/test_notify_delivery.py` (two tests); `audit/tools/mutation_notify_delivery.py` (D27 retargeted, D27b added); appendix regenerated; evidence | after an HTTP 429 the one retry waits 30 s instead of 5 s |
| `aad2af48d` | GA-01, GA-02 | **new** `audit/tools/lineage.py`; **new** `research/lineage/` (`trials_union.jsonl`, `partition_access.json`, `registrations.json`) | records only |
| final commit of this round | GA-10, §9 | `audit/tools/forward_report.py` (loss tail: `worst_r`, `share_below_minus_1r`, `r_p01`); **new** `audit/tools/levels_check.py`; `docs/final_audit/` (10 documents and evidence) | audit tools and documents only |

## 3. Approvals required from the operator

| # | Decision | Why it needs approval | Risk if approved | Risk if not |
|---|---|---|---|---|
| 1 | Merge GA-03 (durable outcome log + workflow step) | changes the production workflow | one more step per run (well under 1 s on 119 records); a failure shows as a red run while the saves still run | breakout records start to be deleted around 11 Dec; the registered H1 / H4 checks become impossible |
| 2 | Merge GA-07 (30 s pause after a 429) | changes alert timing | a rate-limited message arrives up to 30 s later | a rate-limited message is retried after 5 s and may be lost, as on 22 Nov |
| 3 | Merge the audit tools and lineage records (GA-01, GA-02, GA-09, GA-10, GA-17, GA-19, GA-21, GA-24) | repository content | none in production behaviour | auditors use the branch |
| 4 | Provide the MT5 symbol specification, an account statement and spread samples (GA-04, GA-05, GA-28) | operator data | — | costs stay ASSUMED; no execution validation |
| 5 | Decide storage for research input data and check vendor licences (GA-15, GA-16) | legal and storage | — | reproducibility depends on refetching; possible licence exposure |
| 6 | Registration approvals on GitHub (GA-06) | process | — | the order of work rests on author-set dates |
| 7 | Alert wording: name the POC type, label DXY / US10Y context as untested (GA-11, GA-12) | changes phone text | none in behaviour | possible misreading of proxies as order flow |

## 4. What was not changed (by rule)

- No stop, target, threshold, filter or parameter.
- No forward test restarted, stopped early or edited.
- No historical result, trial line, registration or ledger rewritten.
- No production merge, deployment, workflow run on production, or phone message.
- No new strategy or signal.
- B24 stays OFF.
