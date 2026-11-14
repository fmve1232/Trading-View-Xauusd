# P-0 Notification delivery integrity — implementation record (draft PR; not merged, not deployed)

Built on production `30a3da10d` from the specification `docs/deploy/P0_NOTIFICATION_INTEGRITY_SPEC.md` (dev branch
`claude/session-01fdjaothuvhxscxtl7ysa-y3n4w4`, commit `23c2b66ca`) with the operator's decisions of 14 Nov 2026:
**D1** full message text kept in the ledger records; **D2** resend, marked RESENT, when ntfy's cache cannot be read;
**D3** the undelivered block in every REPEAT and follow-up until the plan closes; **D4** the `xq-<key>` tag stays
visible; **D5** no second channel added.

No message was sent to any phone or channel while building or testing this. Every test and replay ran against a
stand-in transport, behind a proxy address that refuses all connections. Mobile delivery remains unverified: the system
has no device acknowledgement, which is why an accepted message ends `DELIVERY_UNCONFIRMED` and never "delivered".

## 1. What changed

| File | Change |
|---|---|
| `quantum/notify.py` | `send()` rewritten (per-attempt states, one retry, ntfy tags and cache checks, records, splitting); `_say()` / `_say_tf()` pass each message's events; undelivered-plan block, prefix and DELIVERY WARNING; `alerts_notify.json`; `notifications/<YYYY-MM-DD>.jsonl` (one file per run day); `merge_ledger()` + `python -m quantum.notify --merge-ledger`; optional `refs` argument on `messages()` and `plan_updates()` (output unchanged) |
| `.github/workflows/quantum-site.yml` | `DELIVERY_RETRY: ${{ vars.DELIVERY_RETRY }}` in the Run pipeline env; one guarded merge line in "Save the forward ledger" (a failure only prints a warning) |
| `tests/test_notify_delivery.py` (new) | 60 tests: T1–T14, the cases below and one regression test per review finding (§2a) |
| `tests/test_stale_signals.py` | the one test that drives the real `send()` now pins the kill-switch path (`DELIVERY_RETRY=0` = exactly the old single attempt) and forbids any cache read |
| `audit/tools/mutation_notify_delivery.py` (new) | 41 mutants; a mutant that does not compile counts as INVALID, never as killed |
| `audit/tools/alert_replay_transport.py` (new) | the replay harness with the tree's real `send()` and a stand-in ntfy (`--fail` / `--arrive` inject failures) |
| `audit/tools/alert_replay_transport_check.py` (new) | posted bytes vs a send-captured replay of the deployed tree |
| `audit/tools/offline_payloads.py` (new) | rebuilds past site payloads offline (used for 13 Nov, whose payloads had expired) |

**Not touched:** `pipeline.py` and every other engine source (freeze key `5e4630924d663fc5:a6f2be58c74887ed`
unchanged), `config.py`, `holdout.py`, `fwd_b24.py` (B24 stays OFF), `outage_notice.py`, `research/`, `artefacts/`,
`audit/PREREGISTRATION.md`, `audit/MANIFEST.sha256`, every registration and record. B15 is unchanged.

## 2. Deviations from the specification, and why

| # | Specification | Implemented | Evidence |
|---|---|---|---|
| 1 | split at ntfy > 3,800 bytes / Discord > 1,900 characters | split only when the body could pass the channel's **hard** limit (ntfy 4,096 bytes; Telegram 4,096 / Discord 2,000 characters) once a RESENT line (and on Telegram / Discord a ref line) is added: one message up to 3,985 bytes on ntfy | 12 Nov replay, ALERT_MODE=all: three messages of 3,808–3,946 bytes were shown in full and stay single; six over 4,096 bytes (ntfy turned them into **file attachments**) and one of 4,083 bytes are split. Sixty mode (production) peaked at 1,250 bytes: nothing split |
| 2 | every message keyed by its events | cross-run de-duplication applies only to events with a deterministic key (plan OPEN / REPEAT / TP1 / TP2 / BE / TP / SL / BOTH / EXPIRED, NOT ACTIONABLE notices, setups and 4h breakouts with their id, the daily report, news). Lines with no event of their own get a key unique to the run | without this, the 12 Nov all-mode replay suppressed **127** messages: H-setup info lines that the deployed code re-sends while a bar is open. A regression test pins that identical later content is sent again |
| 3 | T5 "with an empty cache it resends marked RESENT" | when only the alert state was lost (a crash before it was written), the store's own record stops the resend on **every** channel, Telegram included, cache or no cache; an earlier run's *failed* attempt is resent marked `RESENT (an earlier run's attempt failed: …)`. When the **whole store** is lost **and** ntfy's cache is empty, nothing the run can read remembers the first send: the message goes out again, unmarked | pinned by `test_t5_limitation_…` (named as a limitation, not a pass) |
| 4 | — | **reconcile**: an earlier failure whose tag ntfy's cache later shows (an uncertain error: the server had it) is reclassified; its block and warning are removed, so no message claims it "never reached you" | `test_t4b_…`; mutant D14 |
| 5 | ledger step `cp -r store/notifications/. ledger/notifications/` | a union by record id (`merge_ledger`), so a store that went back (a lost save) never removes a record from the ledger's current tree | `test_ledger_merge_is_a_union_…` |
| 6 | records in `alerts_delivery.json` and the ledger | the full text (D1) only in `notifications/<YYYY-MM-DD>.jsonl` (the ledger); `alerts_delivery.json` and the site payload carry the same records without the text | `test_t6_the_opening_attempts_…` |
| 7 | — | an opening re-sent after a crash never carries the block of its own plan; once it is accepted its entry is removed | `test_t5_an_earlier_runs_failed_attempt_…`; mutants D18, D28 |

## 2a. Independent review (14 Nov 2026, before any merge): 9 findings, 7 fixed, 2 left as they are

| # | Finding | Verdict | Change (each has a regression test that fails on the code before it, and a mutant) |
|---|---|---|---|
| 1 | a message skipped as already delivered by an earlier run cleared a pending warning it never showed | real bug | a warning counts as shown only if part 1 was sent and accepted in this run |
| 2 | with no channel configured, every message built phone-facing state (warnings, UNDELIVERED blocks) that would flood the first real message | real | no channel: a record and an Actions warning only |
| 3 | the store's own record ignored a cache-hit acceptance, so after a crash an arrived message could be resent | real bug | the record check accepts every accepted state |
| 4 | a message regenerated after a crash could carry a warning about itself | real (crash case) | excluded from its own body, cleared when it is accepted |
| 5 | a split message with part 1 (the opening) accepted and part 2 failed marked the plan undelivered | real (bodies over 3,985 bytes only) | judged by the part that holds the opening headline; the warning says "only partly delivered" |
| 6 | hanging channels could make the retry path slow (unbounded in total) | real risk | 120 s delivery budget per run, then no retries or cache reads |
| 7 | one month file re-read and re-uploaded every run (about 21 MB a month in all mode) | real | one file per run day |
| 8 | module-level context instead of arguments | design preference, no defect | kept: preserves `send(lines)` for the 24 existing fakes and the replay harness |
| 9 | the ntfy poll duplicates `outage_notice.py`; the topic is not URL-quoted | ntfy topics are `[-_A-Za-z0-9]` only; `outage_notice.py` is out of P-0's scope | no change |

## 3. Verification (local runs on this container, Python 3.11.18 / numpy 2.4.6 / pandas 3.1.1; **not** GitHub CI)

| Check | Result |
|---|---|
| full suite `python -m pytest -q tests` | **733 passed, 2 skipped** (base `30a3da10d`: 673 passed, 2 skipped; +60 new) |
| P-0 mutation test (`mutation_notify_delivery.py`) | **41 of 41 killed**, each by a failing test, 0 invalid |
| stale-gate mutation test (existing) | 24 of 24 killed |
| outage-notice mutation test (existing) | 24 of 24 killed |
| pyflakes on every changed / new Python file | clean |
| freeze key, `fwd_b24.on()`, MANIFEST, registrations B15 / B16 / B24 / A1 / A2 | unchanged / False / all OK / byte-identical to base |
| Pine checkers (as PR #99 would run them; no `.pine` changed) | precheck, pinelimits, undeclared, order, deadcode, diag_parity all pass |

**Real-payload replays** (production payloads of 12 Nov; store copy of run 3099; nothing sent):

| Replay | Result |
|---|---|
| send captured, deployed vs P-0, 4 scenarios (sixty / all × normal / 15:00–16:00 outage) | **identical**: 635 messages, every line, final alert state and every record file; rules R1–R4: no violation |
| real `send()`, stand-in ntfy, working transport, sixty (production mode) | **8 of 8 messages posted byte-identical**; state and records identical |
| same, all mode | 633 of 647 byte-identical; 14 = the 7 over-limit messages per scenario, posted as parts that rejoin to the original; 0 unexplained |
| plan #7 (15m SELL 3871.20, 12 Nov 15:05): opening fails twice | RESENT with the same tag; the 15:20 message opens with the DELIVERY WARNING, then the block with plan #7's own levels, the TP1 follow-up and the REPEAT prefixed; the 16:05 break-even follow-up carries the block; plan #8 and the daily report untouched; state and records identical to the working run |
| plan #7: client timeout but ntfy has it | found in ntfy's cache before the retry: nothing resent, no block, no warning |

**Plan #12, 13 Nov 2026** (the reference case). Its payloads had expired, so they were rebuilt offline from the
market-data store as of 13:34 (`offline_payloads.py`, deployed tree, Twelve Data prices asserted). The rebuild was
checked against production before use: all **7 15m signals match** production's records exactly (bar, entry, engine SL,
TP1, the opening's TQ), no other signal on any timeframe that morning; the deployed code on the rebuild produces
production's **8 messages** in order, **6 byte-identical** to production's recorded hashes (the opening differs only by
its TIMING line: replay sent 07:20, production 07:19:35; the 08:19 REPEAT agrees in the 80 characters production
logged, and the rest of its headline comes from data revised after the run). Starting state: the store's state with plan
#12 and its six REPEAT rows removed (no plan was open at 06:45).

| Replay | Result |
|---|---|
| P-0, working transport | posted bodies byte-identical to the deployed code; state and records identical |
| P-0, the opening fails twice (production's case) | the 07:35 REPEAT opens with `DELIVERY WARNING: 1 alert was NOT delivered (13 Nov 07:20 UTC, 15m SELL plan #12, 2 attempts, ConnectionError). Its levels follow where it matters.`; **all six REPEATs and the TP1 follow-up** carry `ORIGINAL ALERT NOT DELIVERED — plan #12 …` and `PLAN #12 LEVELS: entry 3897.97 \| SL 3910.97 (-$650) \| TP1 3884.97 (+$325 on half, then SL to entry) \| TP2 3877.97 (+$500)`, the REPEAT / follow-up lines prefixed `UNDELIVERED PLAN #12 …`; plan #12 opens once, reaches TP1 and stays tracked; state and records byte-identical to the deployed run |

The replay's TP1 message is at 13:35 rather than production's 13:21: the harness runs on a fixed 15-minute grid.

## 4. Residual risks and limitations

1. **Phone receipt is never confirmed.** `DELIVERY_UNCONFIRMED` means a server holds the message. Whether the Android
   phone showed it is still unverified. That needs the operator's check on the device.
2. **"its alert never reached you"** (the approved wording). After two failed attempts and a cache miss the message may
   still have reached the server, through an uncertain error on attempt 2. The next run's cache read (6 h window)
   corrects this through reconcile; outside that window the wording can overstate.
3. **Lost store + empty ntfy cache** → an unmarked duplicate is possible (deviation 3). Telegram / Discord have no
   readable cache, so their cross-run protection is the store's own record.
4. **Mixed messages** in the all / quality modes (an event plus lines with no event) get a run-unique key, so they have
   no cross-run de-duplication. Sixty-mode phone messages (production) consist of events only.
5. **Run time.** One ntfy cache read per run that sends. Once a run has spent 120 s in requests and cache reads, it
   makes no more retries or cache reads (one attempt per message, at most 15 s each), so hanging channels cannot use up
   the job's 20-minute limit.
6. **Store growth.** One `notifications/<YYYY-MM-DD>.jsonl` per day with full text: about 10 KB a day in sixty mode,
   about 0.7 MB a day if ALERT_MODE=all. Only the current day's file changes in a run. Nothing prunes the store copy
   yet; the ledger keeps the history.
7. **No CI on this PR yet.** The pull-request checks workflow is PR #99, which is not merged. Every result above is
   local.

## 5. Rollback and switches

- Revert the merge commit. The old code ignores `alerts_notify.json` and the extra record fields; the ledger's
  `notifications/` files stay as history. No record or plan is migrated.
- Repository variable `DELIVERY_RETRY=0` turns off the retry and every cache / record check without a revert. Records,
  blocks and warnings stay.

## 6. Merge notes (PRs #99–#103 stay separate)

- **#101** (disclaimer) wraps the same send sites (`send(trade_msg(...))`). Resolve it as `_say(stream, trade_msg(lines), ...)`
  and `_say_tf(..., trade_msg)`. The DELIVERY WARNING is added inside `send()`, so with #101 it must be inserted after
  the disclaimer lines: the specification requires the disclaimer to stay first. That is one small change at merge time.
- **#102** (daily report split) and **#103** (engine reference levels) edit `notify.py` near the report lines and the
  SIGNAL headline. These are textual conflicts only; this PR does not change those lines' text.
- **#99** (PR checks) and **#100** (environment versions) do not overlap.
