# Design: one run per 15-minute slot, self-healing dispatch and an external watchdog (R15 / R2)

**Status: DESIGN ONLY. Not implemented, not deployed.** It needs the operator's approval before any code is written. All
times are UTC.

**Goal: every 15-minute market slot gets exactly one site run.**
- A missing run is retried once.
- A run that cannot happen is reported once, by a monitor that does not depend on the failing system.
- Nothing in the design touches the engine, `config.py`, thresholds, records, registrations, `FWD_B24` or the freeze
  key.
- It changes only *when* the existing pipeline runs, never *what* it decides.

## 1. Evidence from the run history (13 Oct – 12 Nov, 2,050 market-hour slots)
| Observation | Count | Example | Today's cover |
|---|---|---|---|
| Slot with no build at all | 13 | 15 Oct 22:00–23:45 (8 slots: no dispatch, GitHub cron silent); 4 Nov 11:15 (dispatch missing); 11 Nov 20:30, 20:45 (`startup_failure`); 19 Oct 16:00, 16:30 (cancelled) | none: nothing reports it |
| Slot with two builds | ≈ 58 (estimated from run times; 1 verified) | 21 Oct 15:15: dispatched run 15:16 **and** GitHub cron run 15:28 both ran the pipeline | harmless to alerts (runs are serialised and the alert state de-duplicates), but Twelve Data is called twice |
| Jobs that never got a runner | 9 runs, 5 Oct 18:59–21:11 | gate job queued with no runner, cancelled after 15 min | none |
| GitHub cron delivery | 1–7 runs a day since 8 Oct, against 96 asked | — | not a 15-minute backup (R15) |

**Why today's rule allows duplicates.** A scheduled run stands down only if a dispatched run *started in the last 10
minutes*. GitHub's cron often runs 10–25 minutes late, so it builds again.

**Why today's rule cannot recover a gap.** Nothing checks that a dispatch produced a run, and the backup cron is too
sparse.

## 2. Architecture
```
  Cloudflare Worker "xau-scheduler" (free plan; one cron expression)
  ├─ :01 :16 :31 :46   DISPATCH  POST workflow_dispatch (input reason=primary)                 [exists today]
  ├─ :07 :22 :37 :52   RE-CHECK  list this slot's runs; none / only startup_failure → one retry [new]
  ├─ :12 :27 :42 :57   RE-CHECK 2 the same, for late startup_failure (it took 4–8 min on 11 Nov)  [new]
  ├─ every tick        WATCHDOG  store age, dispatch / API health, token expiry → ntfy (de-duplicated) [new]
  └─ KV "xau-sched"    audit records per slot (30-day TTL), watchdog state                     [new]
             │ dispatch (token: Actions R/W)                    │ ntfy (Worker secret NTFY_TOPIC)
             ▼                                                  ▼
  GitHub Actions  quantum-site.yml                               ntfy.sh  →  operator's phone
  ├─ triggers: workflow_dispatch (primary / retry), schedule (GitHub cron, tertiary), push
  ├─ concurrency: quantum-site (serialises every run; unchanged)
  ├─ job "gate"  SLOT GATE: the first run of a slot builds; every later one stands down          [changed]
  └─ job "build" unchanged pipeline … + PR #97's outage notice (tag xau-outage)
```

### 2.1 Slot gate (workflow `gate` job): one execution per slot
- **The slot:** `slot = floor(created_at / 900) × 900`, from the run's own `created_at` (not from when it starts).
  It is the 15-minute bar that has just closed.
- **Rule.** The run lists this workflow's runs created in its slot (`GET .../runs?created=>=<slot>`; the token is
  `GITHUB_TOKEN` with `actions: read`, which exists today). It **builds only if no earlier run of the same slot owns
  it**.
  - A run owns the slot unless it ended `startup_failure`, or was `cancelled` before any job ran (e.g. a pending run
    replaced in the concurrency queue).
- **Late runs yield.** If the run starts in a later slot than it was created in (it waited), it stands down when the
  current slot already has a run. The current slot's own run processes the newest bar.
- **No race.** `concurrency: quantum-site` already lets only one run of the workflow execute at a time. A second trigger
  for the same slot therefore runs its gate after the first run has finished, sees it, and stands down in about 10
  seconds without downloading anything.
- **If the API call fails:**
  - a run with `reason=primary` proceeds (a missed slot costs more than a rare duplicate);
  - a `retry` or `schedule` run stands down.
- **No retry after a build failure.** A failed test gate or pipeline is not retried in the same slot: it would most
  likely fail again, and PR #97 already reports it. Only runs that never started are retried.
- **Off switch:** repository variable `SLOT_GATE=0`, tested with the `format()` pattern that PR #97 proved. It restores
  today's 10-minute rule.

### 2.2 Dispatcher re-check and one controlled retry (Worker)
- **Re-check at +6 and +11 minutes after each dispatch.** List the slot's runs:
  - **none**: the dispatch failed or GitHub created no run. Dispatch once more with `reason=retry`.
  - **only `startup_failure`**: dispatch once more.
  - **queued or in progress**: do nothing. If it is a runner shortage (5 Oct), a retry would starve as well; the
    watchdog reports it.
  - **any other conclusion**: do nothing.
- **At most one retry per slot,** enforced by KV key `slot:<epoch>.retried`. The slot gate makes even a mistaken
  second dispatch harmless.
- **A dispatch answered with anything but 204 is logged.** The re-check handles it; there is no immediate retry loop.
- **A retried slot reads its data later.** The read is about 10–15 minutes after the close instead of about 5.
  - It therefore sees more complete GC volume than a normal slot (R18 in `R14_AUX_REVISIONS_2026-11-12.md`), so its
    decision is not directly comparable with a normal slot's.
  - Safety is unchanged: the stale-signal gate classifies the signal by its age, as for any run.
  - The audit record marks the slot `retry`, so such decisions can be told apart.

### 2.3 External watchdog (Worker; outside GitHub Actions)
- **Health signal:** the commit time of branch `market-data`. Each successful build saves the store, and with it the
  alert state, so this time is "the last run that processed alerts". It costs one API call and is independent of Pages.
- **Alert rule:**
  - the market has been open for at least 35 minutes, and
  - the store is older than 35 minutes (two missed slots plus margin).
  - Then send "XAUUSD ALERTS DELAYED: no completed site run since HH:MM UTC (N min). Alerts may be missing; do not act
    on old alerts."
- **Recovery:** when the store is again younger than 20 minutes after a delay notice, send one "XAUUSD ALERTS RESUMED
  HH:MM UTC" message.
- **It covers:** runs that never start, runner starvation, a dead or skipped dispatch with a silent cron, and
  token-rejected dispatches. Those are the gaps PR #97 cannot see.

### 2.4 GitHub cron as an additional fallback
- The cron stays exactly as it is (`2,17,32,47 * * * 0-5`).
- With the slot gate it builds only when its slot has no run, so it costs nothing when the dispatcher works and fills
  in when it does not.
- At GitHub's current rate (1 in 20 slots) it is a last resort, not a backup to rely on.

### 2.5 GH_DISPATCH_TOKEN expiry monitoring
- Every authenticated GitHub response to a fine-grained token carries `github-authentication-token-expiration`. The
  Worker's `/check` already reads it.
- **The watchdog notifies:**
  - once when fewer than 14 days remain;
  - daily when fewer than 3 days remain;
  - at once (and every 6 hours while it persists) on 401 / 403.
- **Recommendation for the operator:** a 90-day token with a calendar reminder. The notice is the safety net, not the
  plan.

### 2.6 Failure alerts without duplicate notifications
- **One record for both systems: ntfy's own cache, as in PR #97.**
- Every outage-class notice carries tag `xau-outage`, from either the workflow (PR #97) or the Worker (watchdog).
- Before sending, either side polls the topic's last 180 minutes and stays silent if such a notice is already there.
- **Result:** one notice per outage plus at most one reminder per 3 hours, whichever system notices first.
- **Fallback when ntfy's record cannot be read:** a KV timestamp `watchdog:last_alert`. If that fails too, the system
  fails open and sends.
- **Other notice types:** token and resumed notices use tag `xau-ops`, each with its own de-duplication key in KV.
- **Content:** no notice contains a price, a signal or a plan, and none is written to any trading record.

### 2.7 Recovery, rollback and audit logging
- **Recovery is automatic.**
  - A missing slot is retried once.
  - A delayed or failed slot is followed by the next slot's normal run.
  - The stale-signal gate (PR #96 / #98) then marks anything recovered late as DELAYED or NOT ACTIONABLE.
- **Audit, Worker side:** KV record `audit:<slot>` holding:
  - the dispatch time and HTTP status;
  - the re-check results with the run ids seen;
  - retry yes / no with its HTTP status;
  - the watchdog state and token days left;
  - the notices sent (ntfy id).
  - TTL 30 days. A read-only `GET /audit?hours=N` returns them without any secret, protected by a key header (see §5).
- **Audit, workflow side:** the gate writes one line per run into its step summary and a `::notice`. For example:
  "slot 2026-11-12T07:15Z: BUILD (first run)", or "STAND DOWN: run 4313… owns the slot".
- **Optional weekly reconciliation** (read-only workflow): lists every market slot with 0 or 2+ builds from the API,
  so the invariant is measured, not assumed.

## 3. Failure scenarios
| # | Scenario | What happens | Notices |
|---|---|---|---|
| 1 | Normal | :01 dispatch → run → gate builds | none |
| 2 | Dispatch HTTP 5xx / timeout | no run; :07 re-check dispatches once (`retry`) | none if the retry builds |
| 3 | 204 but GitHub creates no run (4 Nov 11:16 type) | as 2 | as 2 |
| 4 | `startup_failure` (11 Nov 20:31) | re-check at :07 or :12 sees it, dispatches once | none if the retry builds; watchdog after 35 min if not |
| 5 | Runner starvation (5 Oct) | run queued; no retry (it would starve too) | watchdog after 35 min (one notice), RESUMED later |
| 6 | Test gate or pipeline fails | no retry in the slot; next slot runs | PR #97 "SITE DOWN" (one, then ≤ 1 per 3 h); the watchdog stays silent (same tag) |
| 7 | Store save fails | alerts sent, state not saved; no retry | PR #97 "ALERT STATE NOT SAVED" |
| 8 | Duplicate triggers (dispatch + retry + late cron) | slot gate: the first builds, the rest stand down in ~10 s | none |
| 9 | Cloudflare outage / Worker gone | no dispatch and no watchdog; the GitHub cron fills about 1 slot in 20 | **not covered** unless option D (§6) |
| 10 | Token expired or revoked | dispatch 401 | watchdog at once: "dispatch token rejected" (ntfy needs no GitHub) |
| 11 | GitHub API down | gate API call fails: `primary` proceeds, retry / cron stand down; re-check cannot see runs and does nothing | watchdog if the store goes stale |
| 12 | ntfy.sh down | notices fail; KV records the failure; retried on the next tick (bounded) | GitHub e-mail for failed runs (operator setting) |
| 13 | Daily shut, weekends | dispatch and watchdog suppressed by `goldShut`; watchdog waits 35 min after the open | none |
| 14 | Late run crosses a slot boundary | it stands down if the current slot has a run | none |

## 4. Change impact
| Component | Change | Trading behaviour |
|---|---|---|
| `.github/workflows/quantum-site.yml` gate job | the slot rule replaces the 10-minute rule; dispatch input `reason` | none: the same pipeline, at most once per slot |
| `scheduler/worker.js`, `wrangler.toml` | re-check, retry, watchdog, token monitor, KV, `/audit` | none |
| `scheduler.yml` | also stores `NTFY_TOPIC` as a Worker secret; binds KV | none |
| Engine, config, data layer, notify, records, registrations, freeze key | **unchanged** | — |

## 5. Security
- **GitHub token.**
  - Fine-grained, this repository only, Actions read / write, as today.
  - The watchdog's read of `market-data` may need **Contents: read-only**. Verify on a test token first; it adds no
    write access.
- **New Worker secret `NTFY_TOPIC`.**
  - The topic name is the capability to read and post alerts.
  - The Worker publishes with ntfy's JSON API (`POST https://ntfy.sh` with the topic in the body), so the topic never
    appears in a URL or a log.
  - It is never returned by `/check` or `/audit`.
- **Public endpoints.** Workers are public URLs.
  - `/` and `/check` expose nothing sensitive, as today.
  - `/audit` gets a Worker secret `AUDIT_KEY` checked from a request header.
  - The free plan's 100k requests a day absorb casual traffic.
- **No new GitHub permissions for the workflow.** The gate already has `actions: read`.
- **Supply chain.** Pin `wrangler` to an exact version in `scheduler.yml` (today `wrangler@4`).
- **Deploy control.** `scheduler.yml` auto-deploys the Worker on every push to `scheduler/**` on the deploy branch. A
  merge *is* a deploy, so the Worker PR must be merged only with explicit approval. The staged flags (§7) start
  everything in log-only mode.

## 6. Options outside the baseline
- **A.** An immediate retry on a dispatch 5xx (30 s later), besides the re-check. Marginal; not recommended.
- **B.** Retry once after a failed build. Not recommended: it can double partial sends, and most failures repeat.
- **C.** A second independent scheduler (another provider) dispatching with `reason=primary`. The slot gate makes it
  duplicate-free. Adds a second copy of the dispatch token.
- **D.** An external dead-man's switch (e.g. a free heartbeat service that notifies ntfy).
  - The store-save step would ping a heartbeat URL, and the service alerts if no ping arrives for 35 minutes.
  - **This is the only cover for scenario 9** (Cloudflare down).
  - It needs a third-party account; the ping carries no data.

## 7. Rollout (each stage only with approval)
1. Slot gate in **log-only** mode for 48 h: it computes and logs BUILD / STAND DOWN but does not stand down. Compare with
   today's rule.
2. Slot gate enforced.
3. Worker re-check in log-only mode for 48 h (logs "would retry"). Then retries enabled.
4. Watchdog in log-only mode (logs "would notify") for 48 h. Then notices enabled.
5. Token-expiry notices enabled.

**Flags:** Worker `[vars]` `RECHECK`, `RETRY`, `WATCHDOG`, `NOTIFY` = `log` / `on` / `off`, and repository variable
`SLOT_GATE`.

## 8. Verification plan
- **Unit tests** (`tests/scheduler.test.mjs`, node):
  - slot arithmetic across DST;
  - the re-check decisions for none / startup_failure / queued / done;
  - one retry per slot;
  - watchdog thresholds, the shut and reopening, and de-duplication through a fake ntfy cache and KV;
  - token-expiry boundaries;
  - the topic never in a URL or a log.
- **Workflow gate:**
  - Python unit tests of the decision function (the same pattern as `tests/test_outage_notice.py`);
  - a probe on the development branch: two triggers for one slot leave exactly one build, and a `startup_failure`
    stand-in is ignored.
- **Replay over the real run history:** the gate rule against 3,118 real runs. Expected: the ≈ 58 duplicate slots go to
  0, with no new missed slot.
- **After each stage:** the weekly reconciliation, i.e. slots with 0 builds and slots with 2+ builds.

## 9. Expected costs
| Resource | Today | With the design | Free-tier limit |
|---|---|---|---|
| Worker invocations | 96 / day | about 300 / day (12 ticks per hour, market hours) + `/audit` | 100,000 / day |
| KV writes | 0 | ≈ 200–300 / day (one or two per slot, plus watchdog changes) | 1,000 / day |
| KV reads | 0 | ≈ 300 / day | 100,000 / day |
| GitHub API (dispatch token) | ≈ 96 / day | ≈ 400 / day | 5,000 / hour |
| GitHub Actions minutes | unchanged | stand-down runs about 10–15 s each, a few a day | free (public repository) |
| Twelve Data calls | ≈ 384 / day + duplicates (≈ 58 duplicate builds a month) | ≈ 384 / day, no duplicates | 800 / day |
| ntfy messages | — | a few a month (outages, token) | free |

**Engineering estimate:** Worker about 150 lines plus tests; gate about 40 lines plus tests. 1–2 days including the
probe, then 3 × 48 h of log-only stages.

## 10. Rollback
| Part | Instant (no code) | Full |
|---|---|---|
| Slot gate | repository variable `SLOT_GATE=0` → today's 10-minute rule | revert the commit |
| Re-check / retry | Worker var `RECHECK=off` / `RETRY=off` (redeploy) | `wrangler rollback` to the previous version, or revert `scheduler/` (auto-deploys) |
| Watchdog / notices | Worker var `WATCHDOG=off` / `NOTIFY=off` | as above |
| KV | delete the namespace (nothing reads it except the Worker) | — |

**No rollback touches market data, alert state, records or the freeze key.**
