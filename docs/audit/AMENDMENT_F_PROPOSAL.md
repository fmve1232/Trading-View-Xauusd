# Amendment F (F1–F4): PROPOSED — NOT IN FORCE

**Status:** a proposal on an unmerged branch.
- Nothing here applies to production until the operator approves it and merges this branch.
- Production keeps the frozen engine and the freeze key `5e4630924d663fc5:a6f2be58c74887ed`.
- On approval, the text in section 7 is appended to `audit/PREREGISTRATION.md` as the next amendment.

**Sources:**
- `docs/audit/INSTITUTIONAL_AUDIT_2026-11-14.md`: findings IA-02, IA-04, IA-05 and IA-20, plus the dead-code list;
- `docs/audit/REMEDIATION_PLAN_2026-11-14.md`: items F1–F4;
- operator instruction 2026-11-14: "build F1–F4 unmerged".

## 1. What changes

| Item | File | Change | Commit |
|---|---|---|---|
| F1 | `quantum/engine.py` | The weekly high / low accumulators update on **every** bar, including the first bar of each trading day (they skipped it, except on the week's first day) | `0120ae4e7` |
| F3 / F2 | `quantum/engine.py`, `quantum/arm_h6.py`, `site/app.js` | The calibration veto and the negative-EV veto **no longer block** a signal. Both are still computed and published as shadow flags. Only the TQ floor and the risk lock block a signal. H6 reads the engine's applied blocks. The site never names a shadow flag as the reason for NO TRADE | `1b4bd14c0` |
| F3b | `quantum/engine.py` | The race-grid EV no longer enters trade quality (it was 10% of it). The engine's existing no-EV path now applies on every bar, so no weight is added or changed. **A separate commit, so the operator can take F3 without it** | `cfa56db09` |
| F4 | `quantum/config.py`, `quantum/data/sources.py` | Removes two unused definitions: `Config.commission_per_oz` and `sources._empty` | `962b266e7` |
| — | `docs/PLATFORM.md` | Adds **D-14** (F1) and **D-15** (F3 / F3b) as deliberate differences from the frozen Pine reference | this commit |

**Not changed:**
- The Pine artefacts stay at their manifest hashes. TradingView is not a dependency (operator decision 2026-09-27); the differences are documented as D-14 / D-15.
- Thresholds, weights and every other gate are unchanged.
- No registration file is changed.
- **F4's second half is deferred:** moving the daily higher-timeframe series to NY sessions (IA-20). The 1h history starts on 2026-03-02, which is too short for the EMA200 it would feed.

## 2. Why each change is necessary (defects, not tuning)

**F1 — IA-05.**
- The previous week's high / low missed every day-opening bar, so PWH / PWL could understate the true range.
- Size of the error, from the audit's independent recomputation on 4h: 9 of 37 weeks were wrong, by up to $30.29.
- These levels feed:
  - the liquidity pools;
  - the sweep detector;
  - the engine's plan targets;
  - the phone's BREAK / GRAB lines.

**F3 / F2 — IA-02, IA-04.**
- The calibration veto compares an **uncalibrated** p with 0.50. Measured on unique forward trades: 34.9% won against 62.5% predicted (43 trades, exact p = 0.00017).
- The EV veto uses the same self-estimated race grid. It also evaluates the engine's ATR / structure plan, not the $13 / $13 / $20 plan the phone sends.
- On the live record (payload markers, per idea, ±$13, one day), vetoed signals did not do worse than the ones that passed:

| Group | TP1 first | Rate |
|---|---|---|
| SIGNAL (passed every gate) | 27 / 70 | 38.6% |
| VETO-EV | 13 / 30 | 43.3% |
| VETO-P | 16 / 31 | 51.6% |
| VETO-TQ | 15 / 38 | 39.5% |

- A gate built on an invalid probability is a defect. Keeping it would show the operator a "filter" that does not filter.

**F3b.**
- Same reason: the EV term carried the uncalibrated race grid into the TQ floor gate.

**F4.**
- Dead definitions (audit L-04 and IA-01).
- Removing the config field changes the config hash. That is harmless here, because the amendment restarts the holdout once for all four items.

## 3. Impact on the frozen records (this is why approval is needed)

| Record | Effect if merged | Proposed handling |
|---|---|---|
| Website holdout (§7 arms: treatment / control / challenger; H2–H6) | **Restarts.** The freeze key changes `5e4630924d663fc5:a6f2be58c74887ed` → `1f88aad357497da4:4440d52587f5cc6b`; every arm key changes with it | Records up to the merge stay archived under the old key (Amendment 14 practice); nothing is rewritten |
| H6 "No score veto" (Amendment 12) | Its question cannot be asked once no arm applies the score veto. H6 now equals the treatment arm (arm hash `7c4ac023578836c6` → `3ffb9bdf4fb149c1`) | **Close H6 at merge.** Its record to the merge is final |
| B15-ENGINE-FWD | Measures "a SIGNAL event of the frozen treatment engine". The amended engine sends **more** signals (section 4), so B15's object changes | **End B15 at merge**, its record final. Optionally register **B15b**: the same rule (TP1 +$13 before −$13, looks at 30 … 100, Wilson lower bound > 51.0%) on the amended engine from the merge date |
| B9-GRAB-FWD | Counts the engine's SWEEP events on 15m / 30m / 1h / 4h. F1 changes 4 of 285 4h sweeps in the replay window (section 4); other timeframes are unchanged | Continue B9 with a dated note, or restart it: **operator decision** |
| B24-CONFIRM-FWD | OFF (operator instruction) | Unchanged |
| Research registrations (B4–B30) | Research code reads the frozen engine at the commit it ran on | Unchanged; past results stay as recorded |

**Recommended timing:**
- Merge at B15's first look (30 decided results) or on a date the operator chooses, so B15 is not cut short silently.
- At that look B15 needs 21 of 30. With 5 of 13 on 2026-11-14, it needed 16 of the next 17; if the true rate is at break-even, the chance of passing is about 1.5% (audit F.6).

## 4. Impact replay (real data, offline, nothing sent)

**Method:**
- The production engine (`51f9142d8`) and each step of this branch ran on the same store copy, with the pipeline's own `download_all` → `build_market` → 16,000-bar window and every network call blocked.
- Last bar: 2026-11-14 14:30 UTC.
- Tools: `audit/tools/ia/engine_impact.py` (one tree → events and levels) and `audit/tools/ia/engine_impact_compare.py` (two dumps → this table). The store copy is not committed (vendor data).

| Step | 15m signals | 30m | 1h | 4h | 5m | Phone ideas / day (15m + 1h, REPEAT rule, 100 days) | Other changes |
|---|---|---|---|---|---|---|---|
| Production | 78 | 44 | 91 | 53 | 233 | 0.36 | — |
| + F1 | 78 | 44 | 91 | 53 | 233 | 0.36 | PWH / PWL differ on 270 of 1,106 4h bars (up to $30.29) and 115 1h bars (≤ $0.03); 4h SWEEP: 3 removed, 1 added of 285 |
| + F3 | 186 | 89 | 172 | 56 | 364 | 0.77 | the added signals had been vetoed for P (61 on 15m) or EV (47 on 15m) |
| + F3b | 193 | 90 | 173 | 56 | 371 | 0.80 | TQ differs on most bars; the TQ-floor decision flips on 95 of 6,624 15m bars, 7 of which become signals |
| + F4 | 193 | 90 | 173 | 56 | 371 | 0.80 | none (key only) |

What the replay shows:
- Every production signal on 15m, 30m, 1h and 4h is kept. On 5m, 7 of 233 change (risk-lock and TQ-floor interplay).
- **The engine would send about twice as many ideas.**
  - There is no evidence the extra ones are worse (the veto table in section 2).
  - There is no evidence any of them have an edge either. Engine p and EV remain **uncalibrated** and are labelled so on the site (#107).
  - **NO TRADE remains the verdict** for a signal without validated edge.

## 5. Verification (local; GitHub CI runs on the PR)

- **Full suite:** the only failures before the test updates were the five freeze-key pins and the two H6 tests that encode the old rule, all by design.
  - The pins now name the proposed key, each with the production key in a comment.
  - The H6 tests now check that H6 equals the treatment arm.
- **`tests/test_amendment_f.py` (new, 8 tests):**
  - PWH **and** PWL equal an independent pandas recomputation, with 0 differences on 15m, 1h and 4h;
  - a hand-built week whose high is set on a Tuesday-opening bar;
  - only the TQ floor and the risk lock block a signal, with at least one shadow-flagged signal taken;
  - TQ is unchanged when the EV is shifted;
  - the F4 removals;
  - the key differs from production.
- **The new tests fail on production:** all 8 fail on `51f9142d8` and pass on the branch.
- **Mutation:** 9 of 9 mutants killed:
  - F1 reverted;
  - only the high updated;
  - the EV veto restored;
  - the score veto restored;
  - EV back in TQ;
  - a shadow flag given as the VETO reason;
  - H6 applying the EV flag;
  - H6 counting taken trades as vetoed;
  - the dead field restored.
- **One gap found by mutation and fixed:** the first version compared PWH only.

## 6. Rollback

- Revert the merge commit. That restores the engine code and its key.
- Forward records made under the amended key stay archived under that key; none is deleted or rewritten.

## 7. Text to append to `audit/PREREGISTRATION.md` on approval (draft)

> **Amendment F (YYYY-MM-DD, operator approval quoted here):** engine defects F1 (weekly range, IA-05), F3 / F2
> (calibration and EV vetoes as shadow flags, IA-02 / IA-04), F3b (EV out of trade quality) and F4 (dead
> definitions). Freeze key `5e4630924d663fc5:a6f2be58c74887ed` → `1f88aad357497da4:4440d52587f5cc6b`; the holdout and
> every arm restart at the merge; records to the merge are archived under the old key. H6 closes. B15-ENGINE-FWD
> ends at the merge, its record final; B15b [registered / not registered]. B9-GRAB-FWD [continues with this note /
> restarts]. Pine artefacts unchanged (D-14, D-15). Written before the merge; no threshold or weight changed.
