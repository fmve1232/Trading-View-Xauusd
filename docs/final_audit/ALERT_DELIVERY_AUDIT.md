# Alert delivery audit (2026-11-26)

**Finding: every alert stage the monitors marked SENT reached the ntfy server, once, a median 4.1 minutes after its
bar closed. One stage was lost to an ntfy rate limit (HTTP 429) on 22 Nov and never recovered. Whether a message
appeared on the phone is not observable by the system.**

**Sources:**
- `forward-ledger` `c8a99d64e`: `notifications/*.jsonl`, 12 day files, 15–26 Nov, 377 delivery records.
- `market-data` `alerts_state.json` at 11:04 UTC.
- Counts only: `evidence/alert_delivery_2026-11-26.txt`.

## 1. The pipeline and its states

`quantum/notify.py`, delivery integrity log (P-0). Each step and what is recorded:

| Step | Code | Recorded as | Observable? |
|---|---|---|---|
| Signal generated | monitors: `breakouts.scan`, `sweeps.scan`, `keyzones`, `confirm_entry`; engine plans | stage in `alerts_state.json` with phone status `DUE` / `LATE` | yes |
| Eligibility | freshness: only the newest bar's stage, within 20 min (`FRESH_SEC`); stale-signal gate for trade plans; `ALERT_MODE` and per-stream switches | `LATE` (never sent) | yes |
| Duplicate prevention | one stage per record id; tags `xq-<key>`; an earlier run's acceptance is checked first (`_prior`), and the cache is checked before a retry (`_poll_tags`) | `SERVER_ACCEPTED` with "already accepted … not sent again" | yes |
| Message creation | `breakouts.message`, `sweeps.message`, `bundle` (more than 5 in a run go as one), disclaimer first on trade alerts | `text`, `body_sha16`, `bytes`, `part` | yes |
| Queue persistence | not a queue: each run sends its due stages and writes every attempt to `<store>/notifications/<day>.jsonl`, merged into `forward-ledger` | delivery records | yes |
| Retry | one retry for 429 / 5xx / connection errors, after a pause; channel marked down after a second failure; time budget 120 s per run | `attempt` 1 / 2, `RETRY_SUCCEEDED` / `RETRY_FAILED` | yes |
| Rate limiting | ntfy.sh limits anonymous senders per IP (GitHub runners share IPs) | HTTP 429 | yes (as a response) |
| Server accepted | ntfy HTTP 200 + message id | `SERVER_ACCEPTED` → final `DELIVERY_UNCONFIRMED` | yes |
| Device delivered | — | — | **no** (ntfy reports server acceptance only) |
| User acknowledged | — | — | **no** |
| Missed-alert recovery | a stage not accepted is not re-sent in a later run (its 20-minute freshness has passed); the plan path re-sends an opening that never reached the server | `SEND_FAILED` stays in the state | yes |

## 2. Measured

| Measure | Value |
|---|---|
| Delivery records, 15 Nov – 26 Nov 11:04 UTC | 377: breakouts 257, sweeps 51, 15m engine 26, key zones 21, C1 confirmation 13, daily report 9 |
| Final states | DELIVERY_UNCONFIRMED 375; RETRY_FAILED 2 (one message, two attempts) |
| SENT stages in the state with a server-accepted record | 377 of 377 (breakouts 326, sweeps 51); missing 0 |
| Event keys accepted more than once | 0 |
| Bar close → server accepted (attempt 1) | median 248 s, 90th percentile 454 s, maximum 597 s; share over 20 minutes 0.000 |
| LATE stages (seen after the freshness window, not sent by design) | 5 |
| Lost stage | `BRK:M15:1795388400:UP:CONFIRMED`: HTTP 429 at +1.4 s and again at +6.9 s (5 s pause), run 2026-11-22 23:52:22 UTC; the run's only message; never re-sent |

## 3. Change on the remediation branch (needs approval)

| Item | Detail |
|---|---|
| Fix | `RETRY_429_PAUSE_SEC = 30`: after a 429 the one retry waits 30 s; other failures keep 5 s; at most once per channel per run |
| Code | `quantum/notify.py` `_deliver` |
| Tests | `tests/test_notify_delivery.py`: `test_a_rate_limited_send_waits_longer_before_its_one_retry` (429 → 30 s; 503 and connection reset → 5 s), `test_a_rate_limited_channel_waits_once_per_run` (two 429s → one 30 s pause, RETRY_FAILED) |
| Mutation | `audit/tools/mutation_notify_delivery.py`: D27 retargeted and D27b (429 back to 5 s) added; 42 of 42 mutants killed |
| Duplicate risk | unchanged: the retry still checks ntfy's cache first, so a first attempt that did arrive is not sent twice |
| Not verified | whether 30 s is enough against a shared-IP limit; it will only be known from a real 429 after deployment |

## 4. What cannot be established, and what would

- **Device display and acknowledgement.** ntfy confirms that its server accepted a message, not that the phone showed
  it. Options:
  - an operator-run reconciliation: the ntfy app's message list compared with the log on sample days;
  - an acknowledgement action button on each message, which posts back when tapped. That is a change to the alerts
    and needs a receiving endpoint and the operator's approval.
- **A rate limit tied to an account instead of a shared IP** would need an ntfy account and token. That is an
  operator decision, and its effect is UNVERIFIED here.

## 5. Planned risk vs guaranteed loss in the messages

- **C1 plan alerts:** they carry `GAP RISK: the $<risk> loss at the stop is planned, NOT guaranteed: a price that
  jumps over the stop fills at the next price …` (`confirm_entry.gap_line`). Where they apply, it also names the
  weekend close and high-impact news.
- **Directional trade alerts:** they open with `RECORD — NOT A VALIDATED SIGNAL — NO TRADE`
  (`notify.TRADE_DISCLAIMER`; `tests/test_alert_disclaimer.py`, 16 tests).
- **Breakout and sweep messages:** they carry no plan or $ risk. They give levels and the invalidation (the wick or
  level) only.

## 6. Addendum, 26 Nov 2026: separate delivery statuses (operator decision B)

The operator approved the 429 change on the condition that server acceptance is never described as delivery to the
phone, with separate statuses. From the change that follows this audit, every delivery record carries:

| Status | Values | What it means | Verifiable? |
|---|---|---|---|
| `SENT_TO_NTFY` | YES / PARTLY / NO / NOT_CONFIGURED | ntfy's server accepted every part / some parts / none; no ntfy channel | yes (HTTP 2xx + message id, or ntfy's cache) |
| `PHONE_DELIVERY` | NOT_VERIFIABLE | the message reached the phone | **no**: ntfy reports server acceptance only |
| `PHONE_DISPLAY` | NOT_VERIFIABLE | the phone showed it | **no** |
| `SEND_FAILED` | YES / NO | an attempt failed (on any channel) | yes |
| `RETRY_ATTEMPTED` | YES / NO | a second request was sent (a cache check that found attempt 1 had arrived sends nothing) | yes |

- **Code:** `quantum/notify.py` `delivery_status`, `STATUS_NAMES`; the records keep their existing fields
  (`state`, `trail`, `final_state` = `DELIVERY_UNCONFIRMED`).
- **Report:** `audit/tools/delivery_status.py <notifications dir>` recomputes the statuses from the attempt fields
  alone, independently of `notify.py`, for old records too, and lists any message whose stored status disagrees.
- **Measured on `forward-ledger` `624ed94d2` (26 Nov 13:53 UTC):** 381 attempt records, 380 messages:
  `SENT_TO_NTFY` YES 379, NO 1 (the 22 Nov breakout stage, HTTP 429 twice); `SEND_FAILED` YES 1;
  `RETRY_ATTEMPTED` YES 1; `PHONE_DELIVERY` and `PHONE_DISPLAY` NOT_VERIFIABLE for all 380.
- **Wording fixed with it:** "(only partly delivered)" → "(only partly accepted by the server)"; the site's "sent" →
  "sent to server (accepted)".
