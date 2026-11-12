# Incident 2026-11-10: nine-hour production alert outage, and a stale alert recovered after it

**Status: closed. Corrective actions are deployed and verified (below).** All times are UTC.

## Impact
- **No alerts and no site updates from 12:16 to 21:31 UTC** (37 consecutive runs). Nothing was written to the
  market-data store or the forward ledger during the gap.
- **One stale plan reached the phone.** At the first good run, 21:35:34, the existing alert code delivered the 15m
  SELL plan of the 16:15 bar (entry 4024.98) as a normal plan.
  - It went out 306 minutes after its bar closed.
  - Its TIMING line said so, but there was no LATE warning: the move of $2.86 was under the $3.90 limit.
  - Six folded repeat signals were in the same message.
  - At 00:05:04 on 11 Nov the plan hit its stop: "SL 4037.98 HIT -$650".
- **Recorded but not sent:**
  - the 1h SELL plan of 20:00, because in the default alert mode the phone gets only 15m signals;
  - nine 15m SETUP records recovered from the gap (website only in this mode).
- **No registered record was corrupted.** B9, B15 and SETUP-LIVE entries are unchanged, and the freeze key is unchanged.
- **Delivery is verified from ntfy.sh's own cache**, read with the read-only `alert-delivery-check` workflow
  (PR #94 / #95), not from the site's state. It held exactly three messages from the last 12 hours:
  - 21:35:34, the recovered plan (2550 characters);
  - 23:05:01, the daily validation;
  - 00:05:04, the stop hit.

## Timeline
| UTC | Event |
|---|---|
| 12:01 | PR #90 merged (`4bf0fa495`) |
| 12:16 | First run on it: the test gate fails; the pipeline, store, ledger and site steps are skipped |
| 12:16–21:16 | 37 runs fail the same way |
| 21:30 | PR #92 merged (`9dc38db7c`): the failing test is guarded |
| 21:31–21:35 | First good run. The recovered plan is delivered at 21:35:34 |
| 00:05 (11 Nov) | That plan's stop is hit; the result alert is delivered |

## Root cause
- `tests/test_research_b22.py::test_evaluate_counts_precision_in_the_top_fraction_and_net_after_cost` needs
  scikit-learn, a research-only dependency that is not in `requirements.txt`.
- The workflow installs only `requirements.txt`, so the gate failed with `ModuleNotFoundError: sklearn`.
- PR #90 had been verified in an environment that had scikit-learn installed, so its "547 passed" did not reproduce CI.

## Contributing factors
- **Nothing reported the failure.** A failed gate sends nothing, so the outage was silent. It lasted 9 hours, partly
  because the agent session that would have noticed was restarting.
- **The alert code had no notion of a recovered signal.** It presented a 306-minute-old signal as a normal plan.
  Its only guard was LATE, which looks at the price move and not at the age.
- **`send()` counted any HTTP answer as delivered.** The state therefore could not prove delivery.

## Corrective actions (all deployed)
1. **The deploy gate is reproduced locally (PR #92).**
   - The research test is guarded with `pytest.importorskip`, as the same file already did for hmmlearn.
   - Every suite run is now done in a venv built only from `requirements.txt`, which is what CI uses.
2. **Stale-signal protection** (`quantum/notify.py`; operator brief 2026-11-11). Every new trade alert is classified
   before it is shown: engine plans, SETUP, 4h breakouts and grab-test trades.
   - **FRESH**: at most 15 minutes after the bar closed. Unchanged. Normal in-session alerts were measured at
     2.2–7.8 minutes after the close (41 of 41, 3–11 Nov).
   - **DELAYED**: 15–60 minutes. Issued only after a fresh market-price check:
     - a live quote read at most 5 minutes before the alert;
     - the move since the signal inside the LATE limit;
     - the stop and the first target not yet traded since the close.

     Such alerts are labelled DELAYED.
   - **NOT ACTIONABLE**: over 60 minutes, or the price check failed.
     - No plan and no MT5 line are sent; one summary line says why.
     - Later results stay off the phone; they appear on the website only, prefixed `RECORD ONLY`.
     - A REPEAT of a non-actionable plan is non-actionable too.
   - **Records are written exactly as before.** The registered tests count signals from their close, not from the alert.
3. **Delivery proof.**
   - A channel counts as sent only on HTTP 2xx.
   - Every attempt is appended to `<store>/alerts_delivery.json`: time, channel, HTTP status, ntfy message id,
     body hash and first line. No secret and no full text are stored.
4. **Outage notice.** The site workflow sends one phone message on the first failed run (no other failed run in the
   last 60 minutes). `OUTAGE_NOTICE=0` turns it off. **See the correction below: as first deployed it never ran.**
5. **The `alert-delivery-check` workflow** lists what ntfy.sh holds for the topic. It is read-only and sends nothing.

## Verification
See the PR that deployed items 2–4. In summary:
- the suite passes in the `requirements.txt` environment;
- old and new alert code were replayed on the same real payloads, with runs every 15 minutes over 30 hours:
  - **normal timing**: the phone output and every record are byte-identical;
  - **simulated outages**: the records are byte-identical, and the phone gets NOT ACTIONABLE lines instead of the
    old code's stale plans.

## Correction (2026-11-12): the outage notice of item 4 never ran
- **What happened.** Two runs on the deployed commit failed after their alerts had gone out:
  - run 3038 (11 Nov 10:31): `deploy-pages` failed;
  - run 3078 (11 Nov 20:16): `upload-pages-artifact` failed (GitHub's artifact service answered with an HTML page).

  In both, the outage-notice step was **skipped**.
- **Cause (proved by a probe run).** The step condition was `failure() && vars.OUTAGE_NOTICE != '0'`.
  - The variable `OUTAGE_NOTICE` is not set. An unset variable is `null` inside an expression.
  - GitHub's loose comparison coerces `null` to 0, so `null != '0'` is false, and the step could never run while the
    variable was unset.
  - Probe run 43125115555 showed it. `format('x{0}', vars.OUTAGE_NOTICE) != 'x0'` runs as intended.
- **Same probe: `FWD_B24` is not set** as a repository or environment variable either.
  - B24 is off because the code's own default is off (`fwd_b24.on()` is true only for "1"), not because of a stored "0".
- **Not covered by any in-workflow notice.** Two runs (3079, 3080) ended in `startup_failure`: GitHub ran no job, so
  no step of the workflow could send anything.
- **Proposed fix (not deployed; needs the operator's approval).**
  - Use the `format()` condition.
  - Send the notice only when the alerts themselves may be affected: the pipeline did not succeed, or the store that
    holds the alert state was not saved.
  - A Pages-only failure sends nothing: that run's alerts went out, and the next run republishes the site.
  - Probe run 43127410617 checked the three cases.

## Gate audit (2026-11-12): three edge cases hardened (proposal, not merged)
**What held.** An audit of the four paths (engine plans, setups, 4h breakouts, grab test trades) found the three
rules held on every path:
- 15 minutes or less: FRESH;
- 15–60 minutes: DELAYED, only after a live-price check;
- over 60 minutes: NOT ACTIONABLE.

No repeat of a NOT ACTIONABLE plan ever got a plan or an MT5 line.

**Three gaps were found and are fixed in the proposal:**
1. **A SIGNAL marker without a price got no decision.** Its headline was shown however late it was. It is now
   classified by its age, and can never be DELAYED (there is no price to re-check).
2. **Pruning could release a quiet plan.** `fresh_gate` kept the newest 300 decisions. After 300 later decisions, a
   NOT ACTIONABLE plan that was still open lost its flag, and its result would have reached the phone. Pruning now
   drops DELAYED decisions first, and NOT ACTIONABLE ones only after 14 days. Every plan, setup and grab trade stops
   being tracked well before that.
3. **A FRESH repeat of a NOT ACTIONABLE plan was mislabelled.** It said "still open ... don't add a trade", as if the
   operator held that plan. It now says the plan was not actionable, and still issues no plan.

**Records are unchanged.** A replay of the deployed code and of the proposal on the same real payloads (3 and 9–10
Nov, normal timing and simulated outages, sixty and all modes) gave byte-identical phone output, records and state.
