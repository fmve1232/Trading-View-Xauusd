# Mobile delivery test (operator-authorised; one message to a dedicated test topic)

**Purpose:** establish whether a message accepted by ntfy.sh appears on the operator's Android phone. That is the one
link no server log can prove.
- PR #97 (outage notice) does not test it.
- This test does not test trading signals.
- It sends **no** signal, plan or price.
- It touches no store, ledger, record or alert state.
- **It never uses the production topic.**

## 1. Production configuration (what is known without reading the secret)
| Item | Value | Evidence |
|---|---|---|
| Server | `https://ntfy.sh` (public instance) | `quantum/notify.py` `send()`; `alert-delivery-check.yml` |
| Topic | repository secret `NTFY_TOPIC`; letters, digits, `-` and `_` only | `alert-test` run of 2 Nov passed its format check; the topic value is never printed |
| Message format | plain text, title `XAUUSD Quantum`, **default priority (3)**, no tags | `notify.send()` headers |
| Messages reach the server | YES: ntfy's cache held the daily validation of 11 Nov 22:29:25 (sha256 af7c9b2bfe014103) | `alert-delivery-check` runs 43124819608 and 43141415446 |
| Phone receipt | NOT EVIDENCED | ntfy has no read receipts |

**What the phone receives in production** (`ALERT_MODE` unset = sixty):
- 15m engine signals and their plan results, which are rare (none since 10 Nov);
- B15 checks;
- the daily validation, about 22:25–22:35 UTC on trading days (03:25–03:35 PKT);
- news.

**A quiet phone is therefore normal most of the day.**

## 2. Android checklist (before any test)
1. **ntfy app → the production subscription.**
   - The server must be `ntfy.sh`, not a custom server.
   - The topic must match the secret exactly; topics are case-sensitive.
2. **Instant delivery.** In the subscription's settings, turn on "Instant delivery". Without it the app relies on
   Firebase push, which some phones delay or drop.
3. **Android notification permission.** Settings → Apps → ntfy → Notifications → allowed. Android 13+ asks for it
   explicitly.
4. **The notification category for default priority** (the one production uses) must be on and not silent. ntfy has
   one category per priority: Settings → Apps → ntfy → Notifications → the "Default priority" category.
5. **Battery.** Settings → Apps → ntfy → Battery → *Unrestricted*. Some phones have their own "auto-launch" or
   "background activity" switch, which must also be on.
6. **Do Not Disturb**, or a focus mode, must allow ntfy.
7. **A check that needs no test at all.** Open the production subscription in the app and look at its message list.
   - If the daily validation of a recent night is listed, the phone received it, even if no notification popped up.
   - In that case the problem is in steps 3–6, not in delivery.

## 3. The test (only after the operator authorises it in writing)
| Step | Who | What |
|---|---|---|
| 1 | operator | Subscribe in the ntfy app: server ntfy.sh, the **test** topic given in chat (never committed), Instant delivery on. |
| 2 | operator | Add the repository secret `NTFY_TEST_TOPIC` with the same test topic (Settings → Secrets and variables → Actions → New repository secret). |
| 3 | operator | Authorise the send in writing. |
| 4 | Claude | Push branch `claude/session-01fdjaothuvhxscxtl7ysa-y3n4w4-ntfy-test` (one commit, workflow `zz-ntfy-delivery-test.yml`). The push is the trigger, so nothing is sent before it. |
| 5 | workflow | Refuses if the test secret is missing, malformed or equal to `NTFY_TOPIC`. Sends one message, titled `XAUUSD TEST - not a signal`, body "DELIVERY TEST ONLY - NOT A TRADING SIGNAL ... Test id T-2026-11-12-A ...", with production's options (plain text, default priority, no tags). Records the HTTP status, ntfy message id and body SHA-256, then reads the test topic's cache back. |
| 6 | Claude | Report the server-side evidence (HTTP, id, hash, in cache) **separately** from the phone. |
| 7 | operator | Confirm whether the notification appeared, and when (PKT), by replying with the test id. |
| 8 | Claude | Remove the workflow (delete the branch). The operator may then delete the secret and the test subscription. |

## 4. Reading the result
| Server (step 6) | Phone (step 7) | Meaning | Next step |
|---|---|---|---|
| HTTP 200, in cache | appeared | The phone, app and channel work for a new subscription. | If production messages are still missing, the production subscription is wrong (topic or server) or muted: redo checklist items 1, 2 and 4 for it. |
| HTTP 200, in cache | not shown, but listed in the app | Delivered to the app; the notification was suppressed. | Checklist items 3–6. |
| HTTP 200, in cache | not in the app at all | The app did not receive it. | Instant delivery, battery, network; re-open the app (it fetches cached messages for 12 h). |
| not 200 or not in cache | — | Send-side failure (not seen in production so far). | Investigate on the server side before anything else. |

## 5. What this test does not prove
- That trading alerts are correct or profitable.
- That every future alert will arrive. Delivery can still fail later, e.g. after an app update or a battery-setting
  change.
- A repeatable check would need an acknowledgement (PR-G, not proposed for now).
