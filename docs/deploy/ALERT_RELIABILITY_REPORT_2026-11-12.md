# Alert reliability report (2026-11-12): PR-A, PR-B and the R2 / R14 / R15 investigations

**Nothing is merged and nothing is deployed.**
- Production still runs `d47948258`.
- B24 stays off (`FWD_B24` unset; `fwd_b24.on()` is False).
- No threshold, engine logic, research registration, frozen record or live-trading setting was changed.
- No test notification was sent.

All times are UTC.

| Item | Where | Head commit | State |
|---|---|---|---|
| PR-A: outage notice | [PR #97](https://github.com/fmve1232/Trading-View-Xauusd/pull/97), branch `claude/session-01fdjaothuvhxscxtl7ysa-y3n4w4-outage-notice` | `f9a74570f` | draft, awaiting the operator's approval |
| PR-B: stale-signal gate | [PR #98](https://github.com/fmve1232/Trading-View-Xauusd/pull/98), branch `claude/session-01fdjaothuvhxscxtl7ysa-y3n4w4-stale-gate` | `6ffd8e3be` | draft, awaiting the operator's approval |
| This report, the production check, the R14 tool | `claude/session-01fdjaothuvhxscxtl7ysa-y3n4w4` | see §9 | documentation and tools only |

- **Both PRs are cut from the deploy branch at `d47948258` and share no file**, so either can merge first.
- The earlier drafts `d5f221338` and `c499d32b5` on the development branch are superseded by the two PR branches.
- The repository runs no CI on pull requests. The suites below were run in a venv built only from `requirements.txt`,
  as the deploy gate does.

## 1. Decisions for the operator
1. **Approve, or not, PR #97** (outage notice). It can send phone messages after a failed or timed-out run.
2. **Approve, or not, PR #98** (stale-signal gate). It changes one phone wording and two bookkeeping details.
3. **R15 / R2: approve the design in §4 and §6 before any code is written.** It is a self-healing dispatcher, a
   duplicate-free slot gate and a watchdog. It would send phone messages and change the deploy gate.
4. **Two settings only you can change:**
   - GitHub → Settings → Notifications → Actions: "Send notifications for failed workflows only" by email.
   - Check the expiry date of the fine-grained token `GH_DISPATCH_TOKEN` used by the Cloudflare scheduler (R17).
5. **R14: decide whether to register a study (§5).** Any data-layer change would need an amendment, because the data
   layer is inside the freeze key.

## 2. PR-A: outage notice ([#97](https://github.com/fmve1232/Trading-View-Xauusd/pull/97))
**Findings**
- **The deployed condition never runs.** It is `failure() && vars.OUTAGE_NOTICE != '0'`.
  - `OUTAGE_NOTICE` is unset, so it is `null`, and `null != '0'` is false in GitHub's loose comparison.
  - Probe run 43125115555 proved it.
  - It was skipped on 3038, 3078 and 3094.
- **The first fix (`d5f221338`) had two more defects, found here:**
  1. Its de-duplication skipped a notice when *any* other run had failed in the last 60 minutes. A Pages-only failure
     (no notice, by design) would then have silenced a real pipeline failure 15 minutes later.
  2. It had no `cancelled()`. Probe run 43172558297 showed that a job timed out in the pipeline ran no `failure()`
     step: a hung run would have stayed silent.

**Change**
- **Condition:** `(failure() || cancelled()) && format('x{0}', vars.OUTAGE_NOTICE) != 'x0' && (steps.pipeline.outcome !=
  'success' || steps.savestore.outcome != 'success')`.
- **`quantum/outage_notice.py`** (stdlib only, so it still runs when `pip install` failed):
  - "XAUUSD SITE DOWN" when the pipeline did not succeed;
  - "XAUUSD ALERT STATE NOT SAVED" when the alerts went out but their state was not saved.
- **De-duplication** reads ntfy's record of delivered outage notices (tag `xau-outage`, 180 min). If that record cannot
  be read, the notice is sent anyway.

**Tests and evidence**

| Check | Result |
|---|---|
| GitHub's own evaluation (probe 43172558297: 10 failure cases × 10 condition variants) | Sends for the test-gate, store-load, pipeline and store-save failures and the timeout. Silent for ok, ledger, display step, Pages upload and Pages deploy. `OUTAGE_NOTICE=0` is silent in every case. |
| `tests/test_outage_notice.py` | 53 tests. An evaluator reproduces all 100 GitHub results, and the workflow's condition must be exactly the probed text. Plus the module's decision, de-duplication, boundaries, fail-open, HTTP errors, topic secrecy and stdlib-only imports. |
| Mutation (`audit/tools/mutation_outage_notice.py`) | **24 / 24 killed**: 14 on the module, 10 on the condition and its wiring |
| Before / after, all 3,118 real runs (`audit/tools/outage_replay.py`) | Deployed 0 notices, first fix 7, **this PR 9** (detail below) |
| Full suite (requirements-only venv) | 635 passed, 2 skipped |
| Freeze key / `audit/MANIFEST.sha256` | `5e4630924d663fc5:a6f2be58c74887ed` unchanged / all OK |

**This PR's 9 notices in the replay:**
- 10 Nov 12:16, 15:31 and 18:31: the 9-hour test-gate outage, one notice and two reminders.
- Six "state not saved" notices, for runs 864, 1400, 2105, 2541, 2663 and 2689 (store push rejected by GitHub).
- None for the 28 Pages-only failures or the 4 ledger-only failures.

**Residual risk**
- A run that never starts (`startup_failure`), or a dispatcher that stops, cannot be reported from inside the workflow
  (§6).
- If the checkout itself fails, the step cannot run (it logs a warning).

**Rollback**
- Revert the merge commit.
- Or, without code: set the repository variable `OUTAGE_NOTICE=0`.

## 3. PR-B: stale-signal gate ([#98](https://github.com/fmve1232/Trading-View-Xauusd/pull/98))
**Rules unchanged.**
- ≤ 15 min FRESH.
- 15–60 min DELAYED only after a live price check.
- Over 60 min, or a failed check, NOT ACTIONABLE.
- Constants 900 / 3600 / 300 are untouched.
- The 30 boundary and path tests also pass on the deployed code; only the 5 edge-case tests fail there.

**Three edge cases closed** (none occurred in production):
1. An unpriced SIGNAL marker is now classified, and is never DELAYED.
2. Pruning can no longer release a still-open NOT ACTIONABLE plan:
   - DELAYED decisions are pruned first;
   - NOT ACTIONABLE ones only after 14 days;
   - the newest decision never.
3. A FRESH repeat of a NOT ACTIONABLE plan no longer says "still open ... don't add a trade".

| Check | Result |
|---|---|
| `tests/test_stale_gate_paths.py` (new) + `tests/test_stale_signals.py` | 35 + 20 tests, all passing |
| Mutation (`audit/tools/mutation_stale_gate.py`) | **24 / 24 killed**: 12 rule-boundary or check mutants, 5 that undo a fix, 7 other routes to actionable |
| Before / after on real production payloads (`audit/tools/alert_replay.py` + `alert_replay_check.py`) | 20 deployed-vs-branch pairs, 1,612 runs, 43,069 phone lines. 18 byte-identical (phone, state, records). 2 differ only in 11 REPEAT lines (fix 3). **0 rule violations before and after.** Includes the real 10 Nov outage gap and real signals pushed 20 / 30 / 35 min late. |
| Full suite (requirements-only venv) | 620 passed, 2 skipped |
| Freeze key / manifest | unchanged / all OK |

**Normal fresh alerts are unchanged:** every normal-timing window is byte-identical.

**Historical or repeated stale signals cannot become actionable.**
- The checker found no plan line for a signal over 60 minutes old.
- Every 15–60-minute plan line was labelled DELAYED.
- No result line appeared for any of the 14 NOT ACTIONABLE plans.
- The mutation test shows each of those properties is pinned by a test.

**Rollback:** revert the merge commit. `fresh_gate` keeps its format; no data change is needed.

## 4. R15: why the backup cron runs about 4 times a day instead of 96
**Evidence**
- **Schedule runs of `quantum-site` per day:**

  | Period | Schedule runs a day |
  |---|---|
  | 27 Sep – 6 Oct | 61–90 on weekdays (Sundays: 79 on 27 Sep, 15 on 4 Oct) |
  | 7 Oct | 49 |
  | from 8 Oct | 1–7 (Saturdays 1), every day since |

- **The drop is the day the Cloudflare dispatcher started.** Dispatch runs: 0–4 a day before 8 Oct, 47 on 8 Oct, 84 on
  9 Oct, and since 13 Oct a median of 92 on weekdays (one per market-hour slot).
- **Nothing changed in the workflow then.**
  - The cron line became `2,17,32,47 * * * 0-5` on 3 Oct (it was `*/15 * * * 0-5`), and the stand-down gate was added
    the same day.
  - The concurrency group has existed since the first version (26 Sep).
  - Schedule runs stayed high on 5–7 Oct after those changes.
- **It is not a clash with dispatched runs.**
  - On Sunday 8 Nov the dispatcher was idle until 23:01, and GitHub still started only 4 schedule runs (03:54, 10:58,
    16:55, 20:55).
  - Of the 145 schedule runs since 9 Oct, 30 were created while a dispatched run was in progress, so overlap does not
    stop them either.
  - Missing runs are not cancelled ones: run numbers are consecutive, and only 2 schedule runs were ever cancelled.
- **Low-frequency crons in the same repository run reliably:** weekly `xcheck-dukascopy` 6 of 6, monthly
  `research-history` 1 of 1.
- **GitHub's documentation calls the `schedule` event best-effort.** It may be delayed or, under high load, dropped.
  - Sources: the community discussions and guides found by search, e.g.
    [GitHub community discussion](https://github.com/orgs/community/discussions/185355),
    [HackerNoon](https://hackernoon.com/your-github-actions-cron-job-can-disappear-without-failing).
  - docs.github.com is not reachable from this session, so the wording could not be quoted from the source.

**Conclusion.**
- GitHub's scheduler starts roughly 1 in 20 of this workflow's 15-minute slots, and has done so for five weeks.
- The trigger is internal to GitHub and not documented beyond "best-effort". Its start coincides with the dispatcher's,
  but the Sunday data rule out the overlap mechanism.
- **Either way, the GitHub cron is not a 15-minute backup and cannot be made one from the workflow side.**

**Proposed solution** (design only; no code until approved):

| # | Part | What it does | Why no duplicate runs |
|---|---|---|---|
| a | **Slot gate** (workflow `gate` job) | A run stands down if another run of this workflow, of any event, was created in the same 15-minute slot and did not end in `startup_failure` or `cancelled`. It replaces today's "dispatched in the last 10 minutes". | The workflow's `concurrency: quantum-site` already serialises runs. A second trigger for the same slot waits, then its gate sees the first run and stands down in seconds, without a data download. |
| b | **Self-healing dispatcher** (Cloudflare Worker) | A second check at :06 / :21 / :36 / :51. If the GitHub API shows no run for the current slot, or only a `startup_failure`, it dispatches once more. | The slot gate makes a re-dispatch harmless; the Worker also stops after one retry per slot. |
| c | **Watchdog** (same Worker) | One ntfy notice when no run has succeeded for 35 minutes during market hours (also covers R2), and one when the dispatch token is near expiry or rejected. De-duplicated like PR-A. | Sends messages only; starts no runs. |
| d | GitHub cron kept as tertiary | Unchanged; it stands down through the slot gate. | Same gate. |

- **Cost:** about 8 more GitHub API calls an hour from the Worker. Twelve Data usage is unchanged, because stood-down
  runs download nothing.
- **Verification plan:** unit tests of the gate and the Worker, plus a probe on the development branch (two triggers
  for one slot leave exactly one build).

## 5. R14: effect of Yahoo auxiliary-series revisions on the engine
**Method.** `audit/tools/aux_revision_ab.py` ran offline and read-only on store snapshots kept from the production runs.
- **The swap.** Each store snapshot was run twice. The second time, every auxiliary series was replaced by the
  alternate version Yahoo served on the next run, truncated to the same last bar.
  - The auxiliary series are GC and silver futures, DXY, EURUSD, US10Y, S&P and VIX.
  - XAU/USD stayed byte-identical.
- **What ran:** the production code path. That means `download_all` with fetches disabled, `build_market`, features, the
  treatment / control / challenger engines and `report.build`.
- **Pairs:**
  - two independent version flips: runs 3093 ↔ 3094 and 3095 ↔ 3096;
  - a normal-revision control: 3092 ↔ 3097;
  - a harness null check: re-saving the series unchanged gave **0 differences** in 5 TFs × 3 arms and the site payload.
- **Not available offline:** FRED (DFII10, DGS2) and CFTC. They were missing for both arms alike.

**What differs between the two Yahoo versions** (run 3093 vs 3094):
- **GC futures volume:**
  - 5m 4,288 bars, 15m 1,721, 30m 970, 1h 1,106.
  - It is the volume of the spot bars: VWAP, volume profile, volume-gated rules.
  - The revision log never records it: `manifest.py` compares prices only (R16).
- **GC and silver prices:** hundreds to thousands of bars, close changes up to 0.57% (GC 1h) and 1.03% (silver 1h).
- **Smaller changes:** DXY ≤ 0.026%, EURUSD ≤ 0.044%, US10Y ≤ 0.13%.

**Effect** (both flips give the same numbers to within a few bars; the treatment arm is shown):

| | 15m | 30m | 1h | 4h | 5m |
|---|---|---|---|---|---|
| Live decision at the last bar | WAIT = WAIT | WAIT = WAIT | WAIT = WAIT | WAIT = WAIT | WAIT = WAIT |
| Engine signals (bar, direction, entry) | 67 = 67 | 38 vs **39** | 91 = 91 | 50 = 50 | 233 = 233 |
| Same signal, SL / TP levels changed (engine) | 5 | 4 | 11 | 19 | 16 |
| Site markers with a changed SL | 0 of 11 | — | 2 of 33 (max $0.29) | 9 of 50 (max $9.51) | — |
| Calibrated probability changed (bars) | 4,562 of 6,447 | 2,089 of 3,685 | 2,869 of 4,194 | 652 of 1,094 | 11,871 of 12,520 |
| … median / p95 / max change (pp) | 0.06 / 0.54 / 9.8 | 0.004 / 0.15 / 2.1 | 0.02 / 0.70 / 9.9 | 0.004 / 1.35 / 6.2 | 0.015 / 0.72 / 40.8 |
| … at the last bar (p_long) | 46.83 → 47.69% | 21.84 → 21.84% | 36.79 → 36.75% | 33.89 → 34.31% | 42.29 → 42.52% |
| Bull / bear score changed (bars; max points) | 364; 4.96 | 13; 4.4 | 99; 4.3 | 31; 3.2 | 575; 14 |
| Trade quality changed (bars; max) | 38; 18 | 15; 2 | 61; 14 | 23; 15 | 213; 19 |
| Bias label changed (bars) | 7 | 0 | 4 | 1 | 34 |

- **The only signal that exists in one version and not the other** is a historical 30m SELL of 28 Sep 15:00. It appears
  in both flips.
- **The challenger arm** has that same extra 30m signal, plus one 1h signal replaced by another.
- **The control arm** has no signal change.
- **The site's displayed statistics move.** Examples:
  - backtest averages, e.g. avg R 1.3252 → 1.3251;
  - the 30m backtest's SHORT block, because of that extra signal;
  - trade-race counts, e.g. 978 → 979;
  - VWAP / VPOC lines: one 1h VPOC moves by $137.
- **The normal-revision control (3092 ↔ 3097)** shows no signal change in any arm, and levels changed on 3 30m signals.
  The probability changed on 45 of 6,446 15m bars only.
- **Reproducibility of the measurement.** The committed tool re-ran pair 3093 ↔ 3094 and gave byte-identical results.
  The harness null check gave 0 differences again. The tables come from `audit/tools/aux_revision_summary.py`.

**Conclusion**
- The alternating Yahoo versions do not change the live decisions in these snapshots.
- They do change, between consecutive runs:
  - the calibrated probabilities shown (typically by < 1 percentage point, up to 0.86 pp at the live 15m bar);
  - plan levels on part of the historical signals;
  - one historical 30m signal.
- **The registered forward tests are recorded at decision time and are not recomputed**, so their records are not
  affected.
- **What is affected is reproducibility.** The same history can give slightly different site statistics and
  probabilities from one run to the next.
- The risk of a live flip (a decision near a threshold at the moment of a version flip) is real but rare. Per bar it
  was 1 signal in about 28,000 bar evaluations per flip.

**Options** (each needs a decision; none is made here):
1. Record volume revisions too (PR-H; bookkeeping only).
2. Store a hash of the auxiliary inputs with each forward decision (bookkeeping; outside the freeze key if done in
   `manifest.py`).
3. A data-layer rule that keeps the first stored version of a closed auxiliary bar, so later Yahoo versions no longer
   overwrite it. This changes `data/store.py` / `data/market.py`, which are in the freeze key, so it **needs an
   amendment and restarts the holdout**.
4. A pre-registered study before (3): how often a version flip changes a decision at decision time, over the ledger's
   history.

## 6. R2: runs that never start
**Evidence**
- In 3,118 runs since 26 Sep there were 2 `startup_failure` runs: 3079 (11 Nov 20:31) and 3080 (20:46).
  - Both were accepted dispatches, on the same commit `d47948258` as the successful runs before and after.
  - GitHub created no job (0 jobs; empty check suite), and marked the runs failed 4–8 minutes later.
- 15 minutes earlier, run 3078 failed because GitHub's artifact service answered with an HTML page.
- **Reading:** a GitHub-side degradation from about 20:16 to 20:50, not a workflow defect.
  - No public incident for 11 Nov was found by the third-party status trackers.
  - githubstatus.com is not reachable from this session.

**Why no in-workflow fix can cover it.** No step runs, so PR-A cannot report it.
- A `workflow_run` listener would itself be a GitHub Actions run, exposed to the same degradation.
- So would anything that depends on GitHub's scheduler (R15).

**Related, not yet observed: R17.** The scheduler's fine-grained token can expire. Dispatches would then fail with 401,
and the site would fall back to the GitHub cron's few runs a day, with nothing reporting it. The Worker's `/check`
endpoint reports the expiry date.

**Detection (proposed in §4 c).** The watchdog runs in the Cloudflare Worker, outside GitHub Actions.
- It sends one ntfy notice when no run has succeeded for 35 minutes during market hours.
- It sends one when the dispatch is refused or the token is near expiry.
- The self-healing dispatch (§4 b) re-dispatches a slot whose run ended in `startup_failure`.

**Interim cover:** GitHub's e-mail notifications for failed workflow runs (§1). Whether GitHub e-mails on
`startup_failure` is not verified here.

## 7. Risk register changes (against `docs/deploy/PRODUCTION_CHECK_2026-11-12.md`)
| # | Change |
|---|---|
| R1 | Fixed by PR #97 once approved. |
| R2 | Cause established (GitHub-side; §6). Detection needs the external watchdog (§4 c). |
| R6 | **Correction: observed, not hypothetical.** 7 runs failed at the store save (12 Oct, 20 Oct, 29 Oct, 4 Nov × 2, 5 Nov × 2). GitHub rejected the push ("remote rejected ... fatal error in commit_refs_rules"), in 4 of them together with the ledger push. Before 11 Nov the next run could re-send those alerts as normal ones; since the gate, as DELAYED / NOT ACTIONABLE. PR #97 notifies it. |
| R14 | Measured (§5). |
| R15 | Cause and limits established (§4). |
| R16 (new) | The revision log (`manifest.py`) compares prices only. GC volume revisions, which feed the engine, are never recorded. Bookkeeping fix: PR-H. |
| R17 (new) | The expiry of the dispatch token is not monitored (§6). |

## 8. Rollback procedures
| Change | Rollback | Data |
|---|---|---|
| PR #97 | Revert the merge commit, or set `OUTAGE_NOTICE=0` (no code change) | none |
| PR #98 | Revert the merge commit | none (`fresh_gate` format unchanged) |
| Development-branch documents and tools | not deployed; nothing to roll back | none |

## 9. Safeguards and artefacts
- **Freeze key** `5e4630924d663fc5:a6f2be58c74887ed` at HEAD of both PR branches and in all 160 ledger manifest lines
  since 10 Nov.
- **`audit/MANIFEST.sha256`:** all OK on both branches.
- **Research registration hashes unchanged:** B24 6078abc269e9d7fe, A1 f3799d529cbf97ce, A2 272ec21e7ae748f8,
  B15 70571cecc01c3ed6, B16 051def8c7d1cde76.
- **B24 stays off.** `FWD_B24` is unset and not touched; the store holds only its void record.
- **Records unchanged and still counting:** B15 5 results, B9 9 results.
- **No order placement code exists.**
- **Probe workflows** (development branch only, no secrets, no writes): `zz-probe-outage3.yml` added in `09b6d018c`
  and removed in `f3f971c17`.
- **Vendor data:** store snapshots and payloads used for the replays stayed in the session's scratch space. None was
  committed.
