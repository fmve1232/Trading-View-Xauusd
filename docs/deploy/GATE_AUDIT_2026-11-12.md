# Stale-signal gate audit (2026-11-12): three edge cases closed, rules unchanged

**Status: proposal (PR), not deployed until the operator approves.** All times are UTC.

The gate was deployed in PR #96 after the 2026-11-10 outage (`docs/deploy/INCIDENT_2026-11-10_ALERT_OUTAGE.md`).
The operator asked to "verify that no alert can bypass the 15-minute, 15-60-minute and over-60-minute rules", across all
four alert paths, and that "repeated NOT ACTIONABLE signals cannot become actionable".

## The rules (unchanged by this change)
| Age after the bar close | Decision | What the phone gets |
|---|---|---|
| ≤ 15 min (`FRESH_SEC` 900) | FRESH | the alert as before |
| 15–60 min (`RECOVERY_SEC` 3600) | DELAYED only if a live quote ≤ 5 min old (`PRICE_FRESH_SEC` 300) shows the move inside the LATE limit and the stop / first target not yet traded | the alert with a DELAYED ALERT line |
| > 60 min, or a failed check | NOT ACTIONABLE | one summary line: no plan, no MT5 line; later results website-only (`RECORD ONLY`) |

**Evidence that the rules are unchanged.** The 35 path tests below were run against the deployed code (`d47948258`).
- All 30 boundary and path tests pass there too.
- Only the 5 tests of the three edge cases fail, as they should.

## What held (deployed code)
- **Four paths audited:** engine plans, 15m SETUP, 4h candle breakouts and grab test trades.
- Every path applies all three rules at their boundaries (14 / 15 / 16 / 59 / 60 / 61 / 306 minutes).
- In production (`ALERT_MODE` unset = sixty), only 15m engine plans reach the phone. Setups, 4h breakouts and grab
  test trades are website only.
- **No repeat of a NOT ACTIONABLE plan ever got a plan or an MT5 line:**
  - a DELAYED repeat is turned into NOT ACTIONABLE;
  - a FRESH repeat gets only its headline and a REPEAT line.

## The three edge cases (none occurred in production)
1. **A SIGNAL marker without a price got no decision**, and its headline was shown however late it was.
   - It is now classified by its age.
   - It can never be DELAYED: there is no price to re-check.
2. **Pruning could release a quiet plan.** `fresh_gate` kept the newest 300 decisions. After 300 later decisions, a NOT
   ACTIONABLE plan that was still open lost its flag, and its SL / TP result would have reached the phone.
   - Pruning now drops DELAYED decisions first.
   - NOT ACTIONABLE ones are dropped only after `GATE_HOLD_SEC` (14 days), well after any plan (3 days), setup (7) or
     grab trade (5) stops being tracked.
   - The newest decision is never pruned.
3. **A FRESH repeat of a NOT ACTIONABLE plan was mislabelled.** It said "still open ... don't add a trade", as if the
   operator held that plan.
   - It now says: "REPEAT of #N (...), which was NOT ACTIONABLE (sent late, no plan): the same idea -- no plan from this
     repeat either".
   - Still no plan and no MT5 line.

**Outside the four paths (not changed here).** In `ALERT_MODE=all` only, H2–H6 setup lines and DECISION lines are not
gated, so after an outage they replay unclassified. In production (sixty) they never reach the phone; a test confirms it.

## Verification
**Regression tests**
- `tests/test_stale_gate_paths.py` (new, 35 tests):
  - the rule boundaries on the phone;
  - the decision's own boundaries: price age 300 / 301 s, a quote not marked live, the LATE limit hit exactly in both
    directions, levels traded at or after the close;
  - repeats;
  - the three edge cases;
  - the 4h breakout path at every boundary;
  - sixty mode sending no setup, 4h, grab or H-setup line.
- `tests/test_stale_signals.py` (20 tests, 3 of them new).

**Mutation test.** `audit/tools/mutation_stale_gate.py`: **24 of 24 mutants killed.**
- 12 move a rule boundary or remove a check: the boundaries, the price age, the live flag, the LATE limit, the traded
  levels, the DELAYED label.
- 5 undo one of the fixes.
- 7 open another path to actionable: a DELAYED repeat kept DELAYED, quiet plans forgotten, RECORD ONLY lines on the
  phone, no NOT ACTIONABLE summary, and each of the setup, 4h and grab paths ungated.
- One mutant, the LATE limit made exclusive, first survived. Floating-point rounding meant the test never hit the limit
  exactly. The test now uses exactly representable prices.

**Before / after on real production payloads.** `audit/tools/alert_replay.py` replays a tree's alert code on real
payloads, with a run every 15 minutes. `audit/tools/alert_replay_check.py` compares two trees and checks four rules from
the records (no plan line for a signal over 60 minutes old; a DELAYED label on every 15–60-minute plan line; no result
line for a NOT ACTIONABLE plan; no RECORD ONLY line on the phone).
- **Inputs:**
  - the site payloads of production run 07:03 UTC on 10 Nov;
  - payloads recomputed offline by the deployed engine from the exact production store of 12 Nov 01:18 UTC (FRED and
    CFTC unavailable offline, the same for both trees).
- **Scope:** deployed `d47948258` vs this branch, ten windows × two alert modes (sixty = production, all).
  - Normal timing on 3 Nov, 9–10 Nov and 10–12 Nov.
  - Simulated outages, including **the real 10 Nov outage gap (12:15–21:30)**.
  - Three delays placed to push real signals into the 15–60-minute window: the 15m SELL of 10 Nov 16:15, 20 and 35
    minutes late, and a 30m signal 30 minutes late.

| Total | Result |
|---|---|
| 20 replay pairs, 1,612 runs, 3,421 phone messages, 43,069 lines | 18 pairs byte-identical (phone, state, every record file) |
| 2 pairs differing | the two 15m late cases in sixty mode: 11 REPEAT lines changed wording (fix 3); state and records identical |
| Rules violated | **0 before, 0 after**, over 20 plan lines (2 DELAYED, both labelled) and 14 NOT ACTIONABLE plans |

**Full suite** (requirements-only venv): 620 passed, 2 skipped.

## Records and keys
- Plan, setup, B9, B15 and SETUP-LIVE records are unchanged; the replay found byte-identical record files.
- The engine, `config.py`, the thresholds and the freeze key are unchanged. `notify.py` is outside
  `holdout.ENGINE_SOURCES`.

## Rollback
Revert the merge commit. No data change is needed. The state key `fresh_gate` keeps its format, and the old code reads
it as it is (it would simply prune to the newest 300 decisions again).
