# P-0 Notification delivery integrity — technical specification (for review; nothing is built)

Status: **specification only.** No code, no test message, no merge, no deploy, no production change. Requested by the
operator on 13 Nov 2026 after the stage-2 verification found a lost alert. Implementation needs a separate approval
and goes to one draft PR.

## 0. Scope and invariants

**In scope:** how a phone message is sent, retried, de-duplicated, recorded and explained. **Out of scope and
unchanged:** signal generation, entry conditions, SL / TP, plan creation and tracking, probabilities, the stale-signal
gate's rules, research registrations, frozen records, the freeze key, B15, B24 (OFF).

Invariants the implementation must prove (with/without comparison on real payloads, byte for byte):

| Must stay identical | Why |
|---|---|
| every file in `holdout.ENGINE_SOURCES` (ta, sessions, features, analog, engine, backtest, config, **pipeline**, data/*) | freeze key `5e4630924d663fc5:a6f2be58c74887ed` |
| `plan_validation.json`, the `plans` / `plan_log` / `plan_repeats` content of `alerts_state.json`, `research_forward/*` (B15, B9, B24 void, SETUP-LIVE, CONFIRM-*), `holdout/*` | records |
| every website alert line (`report[tf]["lines"]`) | display of the engine's output |
| the set and order of plans opened, their levels and results | requirement 8 |

What changes: the text of **phone** messages in the failure cases below, `alerts_delivery.json` (more fields, more
records), two new files (`alerts_notify.json` in the store; `notifications/<YYYY-MM>.jsonl` in the forward ledger), one
copy line in the workflow's ledger step and one environment line (the `DELIVERY_RETRY` switch).

## 1. Reference case: plan #12, 13 Nov 2026 (from the records; nothing re-sent)

Sources: production store `market-data` @ `8e982370d` — `alerts_state.json` (sha256 988fbb17…435),
`alerts_delivery.json` (3d35372a…081); B15 record (f719c101…bd6).

| Time (UTC) | Record | What happened |
|---|---|---|
| 07:15 | plan #12 (`alerts_state.plans`) | 15m SELL, bar 07:00–07:15, entry 3897.97, SL 3910.97 (−$650), TP1 3884.97, TP2 3877.97, TQ 68, London |
| 07:19:35 | delivery log | the opening alert (7 lines: headline, plan, MT5, LADDER, TIMING, CONTEXT, RECORD) → ntfy, `http None`, `ConnectionError`, **not retried** |
| 07:34:50 … 09:06:06 | `plan_repeats` (6 rows, `of_id` 12) + delivery log (6 × HTTP 200) | six 2-line messages: an engine headline (e.g. "entry 3895.24 SL 3906.01 TP1 3875.22 …") and "REPEAT of #12 (15m SELL from 3897.97 at 07:15 UTC, still open): the same idea -- don't add a trade (no new plan)". **They name plan #12's entry but not its SL / TP; the headline's SL / TP are the engine's, not the plan's.** |
| 13:15 / 13:21:32 | `t_tp1`; delivery log (HTTP 200) | "XAUUSD 15m YOUR PLAN SELL from 3897.97: TP1 3884.97 HIT +$325 on half -- close half, move the other half's SL…" — written as if the operator held the trade |
| — | B15 | plan #12 is tracked and will count (requirement 8 already holds) |

**Not knowable from the records:** whether ntfy accepted the 07:19 message. A `ConnectionError` can occur after the
server received the request; the log keeps only the exception class, and ntfy's 12-hour cache has expired. The
operator's ntfy app history at 07:19 UTC (12:19 PKT) is the only remaining evidence. The full text of the failed
message was not logged (the log stores the first 80 characters, a hash and the line count by design).

What P-0 would have done: retry once after 5 s, having first checked ntfy's cache for the message's tag; if both
attempts failed, the 07:34 message would have opened with a DELIVERY WARNING and the plan's own levels, and every later
REPEAT and the TP1 follow-up would have said that the original alert was not delivered (exact text in §5.4).

## 2. Current architecture (as is, `30a3da10d`)

```
workflow quantum-site (concurrency group "quantum-site", cancel-in-progress: false → runs never overlap)
 └ step "Run pipeline": python -m quantum.pipeline          (pipeline.py is an ENGINE SOURCE: not touched by P-0)
     └ notify.run(store, payloads, alert_tfs)               (quantum/notify.py, outside the freeze key)
         ├ per timeframe: plan_updates() → follow-up lines; messages() → SIGNAL / REPEAT / stale lines
         │   report[tf] = {"lines", "sent": send(trade_msg?(phone_only(phone_lines)))}     12 send sites in total:
         │   tf, setup_alerts, setup_stale, setup_updates, h4_alerts, h4_stale, grab_test_alert, turn_warning,
         │   engine_test_alert, liquidity_near, validation_report, news
         ├ send(lines): one attempt per configured channel (ntfy / Telegram / Discord), timeout 15 s, no retry;
         │   _post() → ok only on HTTP 2xx; appends {t, sha16, lines, first, channel, http, id, ok, error?} to _DELIVERIES
         ├ json.dump(state)  → store/alerts_state.json          (at the END of run: a crash before this loses "sent")
         └ save_deliveries() → store/alerts_delivery.json      (bounded to the last 1,000 records)
 └ step "Save the market-data store": ONE orphan commit, force-pushed (no history)
 └ step "Save the forward ledger": normal commits (history kept) — holdout/, research_forward/ only
 └ step "Outage notice" (on failure only): stdlib, ntfy Tags "xau-outage", de-duplicated by polling ntfy's cache
```

Gaps P-0 closes:

| # | Gap | Evidence |
|---|---|---|
| G1 | no retry | `send()` loops channels once |
| G2 | a failure is visible only in `alerts_delivery.json` | plan #12 |
| G3 | follow-ups and REPEATs assume the opening alert arrived | plan #12 timeline |
| G4 | no link between a message and the plan / event it carries | delivery record has no plan id |
| G5 | uncertain failures cannot be told from certain ones | only the exception class is kept |
| G6 | a lost store save (or a crash before `json.dump(state)`) re-sends alerts next run; the outage notice warns, nothing de-duplicates | outage_notice.py `"state"` message |
| G7 | the audit trail is bounded (1,000) and lives on the history-less `market-data` branch | workflow step |
| G8 | Discord bodies are cut at 1,900 characters silently; ntfy turns bodies > 4,096 bytes into attachments | `send()`; ntfy limit |
| G9 | "sent" = HTTP 2xx is the only state; nothing says device receipt is unconfirmed | `_post()` |
| G10 | no configured channel → nothing sent, nothing said | `send()` returns [] |

## 3. Delivery states (requirement 4; HTTP 2xx never means "received on the phone" — requirement 5)

Per **event** (one plan occurrence: OPEN, REPEAT, TP1, TP2, BE, SL, EXPIRED, NOT-ACTIONABLE notice, setup / 4h / grab
events, report, news, test check): `SIGNAL_GENERATED` when the engine output creates it (plans are created exactly as
today, before and independently of any send).

Per **notification** (one phone message, carrying ≥ 1 events) and per **channel**:

| State | Meaning | Entered when |
|---|---|---|
| `SEND_ATTEMPTED` | a request is being made (attempt 1 or 2) | before each HTTP call |
| `SERVER_ACCEPTED` | the channel's server answered 2xx, or ntfy's cache holds this message's tag | 2xx on attempt 1, or cache hit |
| `SEND_FAILED` | attempt 1 did not get a 2xx | exception or non-2xx on attempt 1 |
| `RETRY_SUCCEEDED` | attempt 2 got a 2xx, or the cache showed attempt 1 had in fact arrived | 2xx / cache hit after `SEND_FAILED` |
| `RETRY_FAILED` | attempt 2 did not get a 2xx | exception / non-2xx on attempt 2 |
| `DELIVERY_UNCONFIRMED` | **final state of every accepted message**: the server has it; the phone's receipt is not confirmed (the system has no device acknowledgement) | after `SERVER_ACCEPTED` or `RETRY_SUCCEEDED` |

Final state per notification = `DELIVERY_UNCONFIRMED` if **any** channel reached it, else the worst channel state
(`RETRY_FAILED`, or `SEND_FAILED` when no retry was allowed). A notification with no configured channel is
`SEND_FAILED` with reason `no channel configured`. The word "delivered" is never used for a state.

```
SIGNAL_GENERATED ─► SEND_ATTEMPTED(1) ─2xx──────────────────────────────► SERVER_ACCEPTED ─► DELIVERY_UNCONFIRMED
                          │
                          └─fail─► SEND_FAILED ─┬─ non-retryable ───────────────────────────────► (final: SEND_FAILED)
                                                ├─ ntfy cache has the tag ─► RETRY_SUCCEEDED ──► DELIVERY_UNCONFIRMED
                                                └─ retryable ─► SEND_ATTEMPTED(2) ─2xx─► RETRY_SUCCEEDED ─► DELIVERY_UNCONFIRMED
                                                                         └─fail─► RETRY_FAILED (final) ─► operational warning
```

## 4. Retry and idempotency (requirements 1, 2)

**Timeouts and backoff.** `requests.post(..., timeout=(5, 10))` (connect 5 s, read 10 s; today one 15 s value). Attempt 2
after a 5 s pause. At most **2 attempts per channel per notification**. Per-run budget: after the first `RETRY_FAILED`
on a channel in a run, that channel's remaining notifications in the same run are tried once (no retry: "channel down
this run"), so a dead channel cannot add more than ~30 s to a run (job limit 20 min).

**Retryable:** connection errors, timeouts, `ChunkedEncodingError`, HTTP 429, 500, 502, 503, 504. **Not retryable:**
HTTP 400, 401, 403, 404, 413 and other 4xx (credentials, topic, size), missing configuration.

**Uncertain vs certain failure.** A connect timeout or a DNS / refused connection means the request never reached the
server (certain). A read timeout, a reset after the request was written, or a `ConnectionError` with no response means
it may have arrived (uncertain). The class is recorded; the policy does not depend on telling them apart, because:

**Idempotency key.** Every event has a deterministic key that does not depend on the alert state (so it is the same
after a lost store save):

| Event | Key |
|---|---|
| plan opening alert | `OPEN:<tf>:<signal bar open epoch>:<side>` |
| plan follow-up | `<TP1 / TP2 / BE / SL / EXPIRED>:<tf>:<signal bar>:<side>` |
| REPEAT | `REPEAT:<tf>:<repeat bar>:<side>` |
| setup / 4h / grab / stale notice | `<stream>:<id or bar>:<side>:<event>` |
| daily / weekly report, news, test check | `<stream>:<trading day or event time>` |

The notification key = SHA-256 of its sorted event keys, first 10 hex digits; the ntfy **Tags** header carries
`xq-<key>` (the mechanism `outage_notice.py` already uses with `xau-outage`). Telegram / Discord get the key on a
`ref <key>` line only on a resent message.

**Before attempt 2 on ntfy:** poll `https://ntfy.sh/<topic>/json?poll=1&since=15m` (the call `outage_notice.py` makes)
and look for the tag. Found → `RETRY_SUCCEEDED (found in ntfy's cache)`, nothing resent. Not found → resend with the same
tag and a first line `RESENT (first attempt failed: <class>)`. Poll unavailable → resend (fail open, as the outage
notice does: a lost alert costs more than a marked duplicate). A resend can therefore at worst produce a second copy that
says RESENT and carries the same tag — never a second, independent-looking alert.

**Across runs (duplicate invocation, lost store save, crash before the state is written).** Before the first ntfy send
of a run, one poll of the last 6 h (ntfy keeps 12 h); any notification whose tag is already in the cache is not sent
again and is recorded `SERVER_ACCEPTED (found in ntfy's cache from an earlier run)`. Runs never overlap (workflow
concurrency group), so this is sequential. Telegram / Discord keep no readable record: a re-send after a lost save is
possible there and is marked RESENT; documented limitation.

## 5. Undelivered opening alerts (requirements 6, 7, 8)

### 5.1 State

New store file `alerts_notify.json` (not a record; `alerts_state.json` stays byte-identical):
`{"open": {"<plan id>": {"open_key", "tf", "bar", "side", "entry", "sl", "tp", "tp2", "sl_usd", "tp_usd", "tp2_usd",
"first_attempt_utc", "final_state", "redelivered_utc"}}, "pending_warnings": [...]}`. Levels are copied from the plan
record when the plan opens (never recomputed from the current configuration). An entry is dropped 3 days after its plan
closes.

### 5.2 Rule

A plan's opening alert counts as **not delivered** when its notification's final state is `SEND_FAILED` or
`RETRY_FAILED` on every channel (any `DELIVERY_UNCONFIRMED` counts as delivered: the system cannot know more). Then
every later phone message that carries an event of that plan — a REPEAT naming it, a TP1 / TP2 / BE / SL / EXPIRED
follow-up, a NOT-ACTIONABLE notice — carries, before its own lines, the undelivered block (§5.4), until the plan closes.
Plans, their tracking, their results and B15 are unaffected; a plan's outcome is never hidden because its alert failed.

### 5.3 Where it plugs in (no change to what the lines say otherwise)

- `plan_updates(...)` gains an optional `refs: list | None = None` argument; when given, it appends
  `(line_index, plan_id, event)` for each line it returns. Default `None`: return values and lines unchanged (its 8 test
  call sites keep working).
- REPEAT lines: `messages()` already has `ctx["repeats"][bar] = plan`; the plan id is taken from there.
- The per-message events are handed to `send()` through a module-level context set by `run()` just before each call
  (`_EVENTS.set([...])`), so `send(lines)` keeps its signature and the 24 test fakes that replace `send` keep working.
  notify is single-threaded (it runs after the pipeline's process pool), so a module-level context is safe; a test pins
  that `_EVENTS` is cleared after every send.

### 5.4 Exact phone text (plan #12 values)

Undelivered block (two lines, before the follow-up line):
```
ORIGINAL ALERT NOT DELIVERED — plan #12: 15m SELL, bar closed 07:15 UTC; the 07:19 UTC alert failed twice (ConnectionError)
PLAN #12 LEVELS: entry 3897.97 | SL 3910.97 (-$650) | TP1 3884.97 (+$325 on half, then SL to entry) | TP2 3877.97 (+$500)
```
REPEAT and follow-up lines of such a plan are prefixed:
```
UNDELIVERED PLAN #12 (its alert never reached you; if you did not enter it, there is nothing to manage): XAUUSD 15m YOUR PLAN SELL from 3897.97: TP1 3884.97 HIT …
```
Delivery warning (first lines of the next accepted message, any stream, once per failure):
```
DELIVERY WARNING: 1 alert was NOT delivered (13 Nov 07:19 UTC, 15m SELL plan #12, 2 attempts, ConnectionError). Its levels follow where it matters.
```
With PR #101 merged, the disclaimer stays first; these lines follow it. With PR #103, the plan stop wording applies to
the headline only; the block above always uses the plan's levels.

## 6. Operational warning when both attempts fail (requirement 9)

1. **GitHub Actions:** `notify.run` prints `::warning title=phone alert not delivered::<stream> <event keys>` (parsed by
   Actions from the pipeline's output; no workflow change) and appends a line to `$GITHUB_STEP_SUMMARY` when set.
2. **Phone:** the next accepted message (same or a later run) opens with the DELIVERY WARNING above; `pending_warnings`
   is cleared only when a message carrying it reaches `DELIVERY_UNCONFIRMED`.
3. **Other channel:** if a second channel is configured and accepted the message, the warning is recorded there too.
4. **Website (separate display PR, optional):** a "phone delivery" card from `alerts_delivery.json`.

Limitation: when ntfy itself is down, the phone warning waits until ntfy accepts again; the Actions warning is
immediate.

## 7. Audit trail (requirements 3, 10)

One record per **attempt** (in `_DELIVERIES` → `alerts_delivery.json`, extended additively; nothing else reads it):
`notif_key, event_keys, plan_ids, stream, channel, attempt (1/2), t_start, t_end (ms), http, exception (class),
error_detail (redacted, ≤ 160 chars), uncertain (bool), cache_check (none / hit / miss / unavailable), ntfy_id, state,
final_state, tag, body_sha16, bytes, lines, first (the message's own first line)`. Secrets (topic, bot token, webhook
URL) are never written (`sources.redact`).

**Preserved in full:** the same records are appended to `store/notifications/<YYYY-MM>.jsonl` and copied by the ledger
step (one line: `cp -r store/notifications/. ledger/notifications/`) to the forward ledger, which keeps git history and
is never force-pushed. `alerts_delivery.json` keeps its 1,000-record window for the website.

**Operator decision D1:** store the **full message text** in the ledger (the repository is public; texts carry trading
levels but no personal data). Without it, "what exactly did the phone get" stays unanswerable, as it is for plan #12.

## 8. Failure and recovery

| Scenario | Behaviour |
|---|---|
| ntfy connection error once | cache check (miss) → resend after 5 s → `RETRY_SUCCEEDED` or `RETRY_FAILED` |
| timeout after the server accepted | cache check (hit) → `RETRY_SUCCEEDED (cache)`, no resend |
| ntfy down for hours | each message 1 attempt + (first one) 1 retry per run; Actions warning every run; plans tracked; the first accepted message carries the warning and the undelivered blocks |
| HTTP 401 / 403 / 404 (bad topic or token) | `SEND_FAILED`, no retry, Actions warning "credentials or topic rejected" |
| no channel configured | `SEND_FAILED (no channel)`, Actions warning, every run |
| store save fails after sending (outage notice "state") | next run: cache poll finds the tags → nothing re-sent on ntfy |
| crash after a send, before `json.dump(state)` | same as above |
| duplicate workflow invocation | sequential (concurrency group); the second run sees the first's state or, if the save was lost, the cache |
| poll of the cache fails | send (fail open), record `cache_check: unavailable` |
| multi-channel, one fails | final `DELIVERY_UNCONFIRMED`; the failed channel's warning recorded |
| body too long | ntfy > 3,800 bytes or Discord > 1,900 characters: split into `(1/2)`, `(2/2)` parts (same key + part suffix); the undelivered block and warning go in part 1; never silently truncated |

## 9. Files

| File | Change |
|---|---|
| `quantum/notify.py` | `send()` attempts / retry / cache check / states / records; `_EVENTS` context; `plan_updates(refs=None)`; undelivered block, prefix, delivery warning; `alerts_notify.json` load / save; `notifications/*.jsonl`; message splitting |
| `.github/workflows/quantum-site.yml` | the one `cp` line in "Save the forward ledger", and `DELIVERY_RETRY: ${{ vars.DELIVERY_RETRY }}` in the "Run pipeline" step's env (the kill switch, §11); nothing else (the gate is unchanged) |
| `tests/test_notify_delivery.py` (new) | §10 |
| `audit/tools/mutation_notify_delivery.py` (new) | §10 |
| **not touched** | `pipeline.py` and every engine source; `holdout.py`; `fwd_b24.py`; `outage_notice.py`; `research/`; `artefacts/`; `audit/PREREGISTRATION.md`; registrations; records |

## 10. Tests (transport faked; no request ever leaves the test; no message to the operator's phone)

Each test runs `notify.run` on real-shaped payloads with a fake `requests.post` / poll; each asserts the delivery records
and states, the phone text, and that `plan_validation.json`, plans, `research_forward/*` and website lines are
byte-identical to a run with a working transport.

| # | Case | Assertions |
|---|---|---|
| T1 | first attempt succeeds | 1 attempt, `SERVER_ACCEPTED` → `DELIVERY_UNCONFIRMED`; text unchanged vs today |
| T2 | attempt 1 `ConnectionError`, cache miss, attempt 2 200 | 2 attempts, `RETRY_SUCCEEDED`, message starts `RESENT`, same tag |
| T3 | both attempts fail | `RETRY_FAILED`; `::warning` printed; next run's first accepted message starts with DELIVERY WARNING; then cleared |
| T4 | read timeout, cache **hit** | no resend; `RETRY_SUCCEEDED (cache)` |
| T5 | duplicate invocation: run twice on the same store, second with the state save "lost" (store restored) | second run sends nothing already in the fake cache; with an empty cache it resends marked RESENT |
| T6 | plan #12 timeline: opening alert fails twice, then 6 REPEAT runs and the TP1 follow-up | every REPEAT and the TP1 message carry the undelivered block with SL 3910.97 / TP1 3884.97 / TP2 3877.97; the follow-up has the UNDELIVERED PLAN prefix; plan #12 opens once, resolves TP1, B15 counts it |
| T7 | TP1 and SL after a failed opening alert | blocks present; results recorded as without P-0 |
| T8 | two channels (ntfy fails, Telegram 200) | final `DELIVERY_UNCONFIRMED`; no undelivered block later |
| T9 | no channel configured; invalid credentials (401) | `SEND_FAILED`, no retry on 401, warnings |
| T10 | body over the ntfy / Discord limits | split into parts; nothing truncated; block in part 1 |
| T11 | no duplicate plan creation | the plan sequence and `plan_validation.json` identical across all of T1–T10 |
| T12 | invariants | engine sources' hashes, freeze key, `fwd_b24.on()` False, registrations unchanged |
| T13 | `_EVENTS` hygiene | cleared after every `send`; a send without events still records |
| T14 | real-payload replay (12 Nov, the existing harness) with a working fake transport | every message byte-identical to today's code |

Mutation test (each must make a test fail): no retry; retry on 401; resend without the cache check; tag missing or
different on the resend; DELIVERY_UNCONFIRMED replaced by "delivered"; undelivered block dropped; levels recomputed from
the current config; warning not cleared / never shown; `_EVENTS` not cleared; Discord truncation restored.

## 11. Rollback

Revert the merge commit. Old code ignores `alerts_notify.json` and the extra fields in `alerts_delivery.json`; the
ledger's `notifications/` files remain as history (append-only, harmless). No record or plan is migrated, so nothing
needs undoing. A repository variable `DELIVERY_RETRY=0` disables the retry and the cache checks without a revert
(the records and blocks stay).

## 12. Decisions for the operator before implementation

| # | Decision | Default proposed |
|---|---|---|
| D1 | store full message text in the public forward ledger | yes (otherwise "what the phone got" stays unknowable) |
| D2 | resend after an uncertain failure when the cache cannot be read (risk: a marked duplicate) | yes (loss is worse than a marked duplicate) |
| D3 | undelivered block in **every** REPEAT and follow-up of that plan (as you asked) vs only until one is accepted | every one |
| D4 | the `xq-<key>` tag is visible in the ntfy notification | yes (it is how duplicates are recognised) |
| D5 | add a second channel (e.g. Telegram) so warnings have another path | your choice; needs secrets you add yourself |

## 13. Confirmations

This specification changes nothing: no file outside `docs/deploy/` was modified; no message was sent; production,
B15, B24 (OFF), the freeze key, registrations and records are untouched. Two corrections to my stage-2 summary: plan #12
had **six** REPEAT messages (07:34–09:06), not five; and whether ntfy accepted the 07:19 message is **UNVERIFIABLE**
from the records (§1).
