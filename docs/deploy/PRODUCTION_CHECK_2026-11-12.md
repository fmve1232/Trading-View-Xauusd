# Production check 2026-11-12: live alerts, ten runs, stale-signal gate, roadmap

**Scope: read-only verification.** Nothing in production was changed.
- No test notification was sent.
- B24 stays OFF.
- No engine, threshold, config or record change was made.

Two proposals are prepared on the development branch and are **not merged**: PR-A and PR-B in §7. All times are UTC;
the operator's clock is PKT = UTC+5.

## 0. Five different things, reported separately
| What | Verdict | Evidence |
|---|---|---|
| **Deployment success** | YES | Every run since 11 Nov 08:31 ran the deployed commit `d47948258`, including all ten below. The site was published by 9 of the ten (§3). |
| **Workflow success** | MOSTLY | Ten runs: 9 success, 1 failure. Run 3094 failed at `deploy-pages` only, after its alerts, store and ledger were saved. Since the deploy: 3 Pages failures (3038, 3078, 3094) and 2 runs that never started (3079, 3080, `startup_failure`). |
| **ntfy acceptance** | YES for every message sent since the deploy | One phone message since the deploy: 11 Nov 22:29:24, HTTP 200, ntfy id `jhdwImUqCgSm`, in ntfy's cache with the same SHA-256. None was due in the ten runs, and none was sent: ntfy's cache for 14:27–02:27 holds exactly that one message (run 43141415446). |
| **Phone (Android) receipt** | **NOT EVIDENCED** | ntfy issues no read or delivery receipts. Only the ntfy app's history on the phone can show it (§2). |
| **Trading-strategy accuracy** | **NOT ASSESSED; not claimed** | The registered live records are below their first check: B15-ENGINE-FWD has 5 results (3 TP / 2 SL; first look at 30) and B9-GRAB-FWD has 9 (4 TP / 5 SL). Working delivery says nothing about the strategy's edge. |

## 1. Live alert confirmation
**No genuine 15m engine alert has occurred since the deployed commit d47948258** (first run 11 Nov 08:31; checked to
the end of run 3099, 12 Nov 02:21). Engine tallies from the production state and logs:
- 11 Nov: 0 signals in 90 15m bars;
- 12 Nov, to the end of the ten runs: 0 signals in 9 15m bars (00:00–02:00 opens). The 15m engine said WAIT in all
  ten runs.

Nothing artificial was generated to fill the gap.

**The latest genuine 15m trading alert (before the gate existed): plan #1**
| Field | Value |
|---|---|
| Signal | plan #1; 15m engine SIGNAL of the 16:15 bar; bar closed 10 Nov 16:30 UTC |
| Direction | SELL |
| Entry | 4024.98 |
| Plan SL / TP1 / TP2 | 4037.98 / 4011.98 (half) / 4004.98 |
| Engine levels in the headline | SL 4055.30 (see R13) |
| Sent | 10 Nov 21:35:34 UTC = 11 Nov 02:35 PKT, **306 min after the close**. It was recovered after the 10 Nov outage and sent before the gate existed. |
| Freshness-gate decision | none at the time (no gate). Under today's gate it is NOT ACTIONABLE: >60 min (`test_the_outage_replica_is_not_actionable_and_its_record_is_unchanged`). |
| ntfy HTTP | **not recorded**: the old `send()` did not log status codes. Acceptance is proved by ntfy's own cache instead (§2). |
| In ntfy's cache | YES: 21:35:34, 2550 characters, SHA-256 4e09f2315d336581 (`alert-delivery-check` runs 42983184602 and 42983325195) |
| Result | Stop traded on the 23:55 bar. The SL alert went at 11 Nov 00:05:04 UTC (126 characters, SHA-256 6bfcc530778e79de, in the cache): "SL 4037.98 HIT -$650" |

**Plans created since the deploy.** All are 30m, all FRESH, and **none was sent to the phone**: in the default sixty
mode the phone gets only 15m signals.
| Plan | Signal | Entry / SL / TP1 / TP2 | Alert age | Gate | Phone | Website result |
|---|---|---|---|---|---|---|
| #3 | 30m SELL, closed 11 Nov 11:00 | 4050.55 / 4063.55 / 4037.55 / 4030.55 | 6.2 min | FRESH | not sent (sixty) | TP1 + TP2, 13:35 |
| #4 | 30m SELL, closed 15:00 | 4016.93 / 4029.93 / 4003.93 / 3996.93 | 4.5 min | FRESH | not sent | TP1 + TP2, 15:30 |
| #5 | 30m SELL, closed 18:00 | 3993.54 / 4006.54 / 3980.54 / 3973.54 | 6.3 min | FRESH | not sent | TP1 + TP2, 23:35 |

These results are site-price records for the registered tests, not proof of accuracy. No plan was created in the ten
runs (`plan_seq` stayed at 5).

**Every non-FRESH decision since the deploy.**
- Only `setup:62`: a 15m SETUP of the bar closing 22:00. It was handled by the backup cron at 22:29, 29.4 min late,
  with no live price because the market was in its daily shut, so it is **NOT ACTIONABLE**.
- Setups are website only in sixty mode, so nothing reached the phone.
- **In the ten runs, every decision was FRESH.** Four 15m setups were recorded, all website only:

  | Setup | Bar closed | Recorded | Age | Gate |
  |---|---|---|---|---|
  | #65 BREAKOUT SELL 3979.68 | 00:00 | 00:06:15 (run 3090) | 6.2 min | FRESH |
  | #66 BREAKOUT SELL 3974.71 | 00:15 | 00:19:19 (3091) | 4.3 min | FRESH |
  | #67 SWEEP SELL 3993.79 | 01:30 | 01:35:13 (3096) | 5.2 min | FRESH |
  | #68 SWEEP BUY 3984.65 | 02:00 | 02:04:09 (3098) | 4.2 min | FRESH |

  `fresh_gate` gained no entry; it records non-FRESH decisions only.

## 2. ntfy acceptance and Android receipt
**Every phone message since the deploy was accepted by ntfy:**
| Sent (UTC) | PKT | Message | HTTP | ntfy id | Body SHA-256 (log) | In ntfy cache (SHA-256) |
|---|---|---|---|---|---|---|
| 11 Nov 22:29:24 | 12 Nov 03:29 | XAUUSD DAILY VALIDATION Wed 11 Nov … (7 lines) | **200** | jhdwImUqCgSm | af7c9b2bfe014103 | **YES**, 1256 characters, af7c9b2bfe014103 (run 43124819608, 12 Nov 00:06) |

**In the ten runs no phone message was due, and none was sent.**
- `alerts_delivery.json` gained no attempt.
- No 15m engine signal occurred, and setups are website only in sixty mode.
- The daily validation goes out after 22:00.
- **ntfy's own cache agrees.** The read-only `alert-delivery-check` run 43141415446 read the topic at 02:27 for the
  last 12 hours. It found exactly one message: 22:29:25, 1256 characters, SHA-256 af7c9b2bfe014103, the daily validation
  above. Nothing reached ntfy unlogged during the ten runs. (The first attempt failed with "Network is unreachable"
  on GitHub's runner before reaching ntfy; one re-run succeeded.)

**Android receipt: not evidenced.**
- ntfy issues no delivery or read receipts. Its cache proves the server accepted a message, not that a phone showed it.
- **Device-side evidence needs you.** Open the ntfy app's history for the topic and look for:
  - 10 Nov 21:35 UTC (11 Nov 02:35 PKT): "XAUUSD 15m SELL (confirmed close) | entry 4024.98 …";
  - 11 Nov 00:05 UTC (05:05 PKT): "… SL 4037.98 HIT -$650";
  - 11 Nov 22:29 UTC (12 Nov 03:29 PKT): "XAUUSD DAILY VALIDATION Wed 11 Nov …".
- **Not on the phone but in the cache** → the problem is delivery or the phone (battery optimisation, notification
  settings, a different topic subscribed).
- **No test notification was sent.** A test would go to a separate test topic, only after your approval (PR-G would
  make receipt measurable with an Acknowledge button).

## 3. The ten production runs after the request
Runs 3090–3099, 12 Nov 00:01–02:21. All were dispatched by the Cloudflare scheduler on commit `d47948258`.
| Run | Started | Workflow | Data feed (last closed 15m bar processed) | Signal generation | Alert generation | ntfy delivery | Freshness gate | Website (Pages, after the bar close) |
|---|---|---|---|---|---|---|---|---|
| 3090 | 00:01 | success, 322 s | OK, 23:45 bar | all five TFs WAIT | setup #65 (website) | none due, none sent | #65 FRESH 6.2 min | published 00:06:36 (+6.6 min) |
| 3091 | 00:16 | success, 214 s | OK, 00:00 | all WAIT | setup #66 (website) | none | #66 FRESH 4.3 min | 00:19:46 (+4.8) |
| 3092 | 00:31 | success, 329 s | OK, 00:15 | all WAIT | none | none | no decision | 00:36:41 (+6.7) |
| 3093 | 00:46 | success, 308 s | OK, 00:30 | all WAIT | none | none | no decision | 00:51:20 (+6.3) |
| **3094** | 01:01 | **failure**, 219 s | OK, 00:45 | all WAIT | none | none | no decision | **FAILED** at `deploy-pages`. The site stayed on 3093's build until 01:21. |
| 3095 | 01:16 | success, 286 s | OK, 01:00 | all WAIT | none | none | no decision | 01:21:03 (+6.0) |
| 3096 | 01:31 | success, 285 s | OK, 01:15 | all WAIT | setup #67 (website) | none | #67 FRESH 5.2 min | 01:36:03 (+6.0) |
| 3097 | 01:46 | success, 252 s | OK, 01:30 | all WAIT | none | none | no decision | 01:50:31 (+5.5) |
| 3098 | 02:01 | success, 191 s | OK, 01:45 | all WAIT | setup #68 (website) | none | #68 FRESH 4.2 min | 02:04:29 (+4.5) |
| 3099 | 02:16 | success, 320 s | OK, 02:00 | all WAIT | none | none | no decision | 02:21:38 (+6.6) |

**Common to all ten runs:**
- Test gate: 582 passed, 2 skipped.
- Every step through the ledger save succeeded, including in 3094.
- The ledger manifest carries the freeze key `5e4630924d663fc5:a6f2be58c74887ed` (`freeze_key_ok` true, 10 of 10).
- Live reference: gold-api LIVE. Macro feeds: 9 / 9 OK. OANDA and MetaApi are not configured.
- **Errors and warnings:**
  - **Run 3094.** `deploy-pages` reported: "No artifacts named "github-pages" were found for this workflow run … Is
    githubstatus.com reporting issues …". `upload-pages-artifact` had succeeded in the same run, so this was GitHub's
    artifact service.
  - **Every run, display only:** Myfxbook news XML ParseError, and FXStreet RSS HTTP 403. The calendar feed was OK.
  - **Every run:** a Node.js 20 deprecation warning.
- **Outage notice: skipped in all ten**, including 3094.
  - With the deployed condition it never runs (R1).
  - Under PR-A it would also have been skipped in 3094, by design: the pipeline and the store save succeeded, so that
    run's alerts were unaffected.
- **Data revisions** (from the ledger manifests):
  - XAU_USD 5m: one revised closed bar in 6 of the 10 runs. It was always the 5m bar that had closed just before the
    previous run fetched it. The close moved $0.53–$2.23; highs and lows only extended.
  - Auxiliary Yahoo series: 3–15 revised bars on six runs, and 15,194–15,214 on four (3093–3096).
    - In run 3093 the 15,196 auxiliary bars were 9,724 COMEX gold futures (GC=F), 5,203 silver futures, 198 US10Y,
      42 EURUSD, 20 DXY and 9 S&P.
    - 88% of them had opened before 5 Nov. Yahoo re-sends the futures history in two alternating versions (R14).
- **Scheduler:** the dispatcher started one run per market-hour slot (92 a day on 10 and 11 Nov). GitHub's backup
  cron started only 4 a day (R15).

## 4. Stale-signal gate audit (all four alert paths)
**Method.**
- The deployed `quantum/notify.py` (d47948258) was read line by line.
- It was then exercised by 20 scratch tests. They are not committed, and they run against the deployed code through
  its own test fixtures.
- Each rule was checked at its boundary on every path:
  - 14 and 15 minutes → FRESH;
  - 16 minutes with a live price → DELAYED;
  - 16 minutes without a live price → NOT ACTIONABLE;
  - 59 and 60 minutes → DELAYED;
  - 61 and 306 minutes → NOT ACTIONABLE.

| Path | Phone in production (ALERT_MODE unset = sixty) | ≤ 15 min | 15–60 min | > 60 min | Follow-ups of a NOT ACTIONABLE one |
|---|---|---|---|---|---|
| Engine signal plans | 15m only | FRESH, unchanged | DELAYED only with a live price ≤ 5 min old, the move inside the LATE limit, and stop / TP1 not yet traded; otherwise NOT ACTIONABLE | NOT ACTIONABLE: one summary line, no plan, no MT5 line | `RECORD ONLY`, website only |
| 15m SETUP | never (website only) | as above | as above | as above | excluded from the phone |
| 4h candle breakout | never (website only) | as above | as above | as above | excluded from the phone |
| Grab test trades (B9) | never (website only) | as above | as above | as above | `RECORD ONLY` |

The setup, 4h and grab rows were tested in `ALERT_MODE=all`, the only mode in which those alerts reach the phone.
The 4h breakout path had no end-to-end test in the deployed suite; the scratch tests added five.

**Repeated NOT ACTIONABLE signals cannot become actionable.** A repeat of a non-actionable plan is handled as follows,
and in every case it gets no plan and no MT5 line:
- arriving DELAYED: it is turned into NOT ACTIONABLE ("repeat of plan #1, which was not actionable");
- arriving FRESH: it gets only the headline and a REPEAT line;
- arriving NOT ACTIONABLE: it gets the summary line only.

**Three gaps found.** All are closed in PR-B; none occurred in production.
1. **A SIGNAL marker without a price** got no decision, and its headline was shown however late it was.
   - In practice this is theoretical: the price is the bar close.
   - Shown by the scratch test `test_signal_without_price_is_shown_unclassified_BYPASS`.
2. **Pruning could release a quiet plan.** `fresh_gate` keeps the newest 300 decisions. After 300 later decisions (a
   very long outage), a NOT ACTIONABLE plan that was still open lost its flag, and its SL / TP result would have
   reached the phone. Shown by `test_gate_keep_pruning_releases_a_still_open_quiet_plan_BYPASS`.
3. **A FRESH repeat of a NOT ACTIONABLE plan was mislabelled.** It said "still open ... don't add a trade", as if the
   operator held that plan. This is wording only: no plan is issued.

**Outside the four paths.** In `ALERT_MODE=all` only (not production), these lines are not gated:
- H2–H6 setup lines, which carry entry / SL / TP and are tagged "info, not a DECISION";
- DECISION lines.

After an outage they replay unclassified. In production (sixty) they never reach the phone; a test confirms this.
Proposed as PR-B2 if the mode is ever used.

## 5. Outstanding production risks
Ranked by consequence × likelihood.
| # | Risk | Evidence | Severity | Mitigation |
|---|---|---|---|---|
| R1 | **The outage notice never fires.** | Unset variable → `null`, and `null != '0'` is false. Skipped on runs 3038, 3078 and 3094. Proved by probe run 43125115555. | HIGH (safety feature inert) | PR-A (ready, probe-verified) |
| R2 | **Runs that never start are invisible.** | 3079 and 3080 ended in `startup_failure` with no job, so no step can notify. Same for a dead dispatcher. | HIGH | Operator setting now: GitHub → Settings → Notifications → Actions → failed workflows by email. PR-F (watchdog). |
| R15 | **The GitHub backup cron is not a 15-minute backup.** | Its cron (`2,17,32,47 * * * 0-5`) asks for 96 runs a day. GitHub started 4 a day on 10 and 11 Nov, and none in the ten runs. The Cloudflare dispatcher started 92 a day, one per market-hour slot. | HIGH if the dispatcher stops: alerts could stop for hours with nothing reporting it | PR-F (watchdog in the dispatcher's own tick, plus the GitHub email setting of R2) |
| R3 | **The 5m spot feed finalises closed bars late.** | 738 in-session XAU_USD 5m bars were revised on the next run, Oct–Nov, about 13% of bars. Median $0.93, max $7.65. In 732 the close changed; highs and lows only **extended** (6 shrank, all in one re-fetch on 30 Oct). In the ten runs: 6 bars, $0.53–$2.23, only extended. | MEDIUM: TP / SL hits are decided on these bars and can be reported up to one run late. No false hits from shrinkage were seen. | PR-J (research measurement first). The data layer is in the freeze key: any fix needs an amendment. |
| R14 | **The engine's auxiliary inputs are revised between runs.** DXY 1h, US10Y, silver, EURUSD, S&P and GC feed the engine's macro, correlation and volume features; they are **not** display-only. | Yahoo re-sends the GC and silver futures history in two alternating versions: 4 of the ten runs revised about 15,200 bars, 98% of them GC or silver, 88% opened before 5 Nov. Recent bars flip too: the 11 Nov 23:00 DXY bar went 102.911 → 102.903 → 102.911 on consecutive runs. Close changes since 11 Nov: DXY ≤ 0.03%, EURUSD 15m ≤ 0.02%, US10Y ≤ 0.18%, silver 15m ≤ 0.32%, GC 1h ≤ 0.57%. | MEDIUM–LOW: the changes are small, but their effect on the engine's decisions has **not been measured**. | Measure first (extend PR-J to the auxiliary series). Any change to the data the engine reads is in the freeze key and needs an amendment. |
| R4 | **Repository growth.** | GitHub estimate 3.71 GB. The forward-ledger checkout is about 790 MB, 713 MB of it `revisions/`. Most is Yahoo history re-sent each run: GC_F_60m 258 MB, SI_F_60m 143 MB, SI_F_15m 94 MB, _TNX_60m 54 MB. CI clones the ledger every run (18 s median). | MEDIUM (months of runway; GitHub's soft guidance is under 5 GB) | PR-H (gzip of closed months measured at 11% of the size) |
| R5 | **GitHub Pages / artifact service failures.** | 3 of 68 build runs: 3038 `deploy-pages`; 3078, where the artifact service returned HTML; 3094 "No artifacts named github-pages". | LOW–MEDIUM: the site is stale for one cycle; alerts are unaffected. | none needed. PR-A no longer pages for this case. |
| R6 | **A store-save failure would replay alerts.** | The state lives in the store. If its save fails, the next run re-sends that run's signals, marked DELAYED or NOT ACTIONABLE. **Correction (later the same day): observed 7 times since 12 Oct (GitHub rejected the store push); see `ALERT_RELIABILITY_REPORT_2026-11-12.md` §7.** | LOW | The PR-A message warns "do not open a second trade". |
| R7 | **News feeds are broken** (display only). | FXStreet HTTP 403 on 68 of 68 runs. Myfxbook news XML ParseError (HTML entity) on 41 of 58, then 10 of 10. The calendar, which the news window uses, was OK every run. | LOW | PR-C |
| R8 | **One spot source for the alerts.** | Twelve Data only. OANDA practice and MetaApi are not configured; the gold-api reference is mid only (LIVE 65 of 68). | LOW–MEDIUM | PR-K (cross-check line) |
| R9 | **The FWD_B24 variable is not set** (the operator believes it is "0"). | Probe and production env both show it empty. | LOW: B24 is OFF by the code default since PR #93. | Leave as is, or set "0": either is OFF. |
| R10 | **The test gate takes about half of every run.** | Median 148 s of 300 s; alerts go out about 5.3 min after the bar close. Ten runs: Pages published 4.5–6.7 min after the close. | LOW (latency) | PR-E |
| R11 | **Node.js 20 deprecation.** | `configure-pages@v5`, `upload-artifact@v4` are forced to Node 24 every run; they work today. | LOW | Bump at a quiet time, after checking versions |
| R14 / R15 update | Measured and investigated later the same day: `ALERT_RELIABILITY_REPORT_2026-11-12.md` §4 (R15) and §5 (R14). | | | |
| R12 | **The last bar before the daily shut** (closes 22:00 UTC) is handled only by the backup cron. | 22:01 falls in the shut hour, so the dispatcher skips it (by design). setup:62 → NOT ACTIONABLE (29.4 min, no live price). | INFO: correct; the market is shut. | none |
| R13 | **Two stops in one phone alert.** | The headline shows the engine's own SL / TP (e.g. SL 4055.30). The plan line shows the $13 plan (SL 4037.98). | LOW (confusion) | PR-I |

## 6. Improvement roadmap (ranked)
**Scoring.**
- Impact = what goes wrong today without it.
- Risk = the chance the change itself harms production.
- Effort: S ≤ 1 day, M ≤ 1 week, L > 1 week.

**What the research says.** Several areas were already tested on development data:
- B7 macro and B8 news: REJECT, 54 / 54 trials;
- B14 multi-timeframe BREAK: FAIL, 48.0% of 229 against a 46.3% base;
- B22 / B23 calibrated ML: FAIL;
- B20 continuation: not significant.

These areas rank low for production work. **Nothing below tunes a threshold or changes the engine.** A strategy-side
idea needs a new pre-registered study on unseen data.

| Rank | Area | Proposal | Impact | Risk | Effort | Measurable benefit | Freeze key | Production alerts |
|---|---|---|---|---|---|---|---|---|
| 1 | ntfy delivery monitoring | PR-A outage notice fix; PR-F run watchdog; PR-D daily ntfy reconciliation; PR-G acknowledge button | HIGH | LOW | S–M | Time to detect an outage: 9 h on 10 Nov → ≤ 30 min, including a dead dispatcher (R15). Share of sent alerts reconciled against ntfy's cache: today manual → 100% daily. Phone receipt evidenced by an ack (PR-G). | untouched | PR-A / F / G add phone messages or headers (approval). PR-D none. |
| 2 | Live XAUUSD feed reliability | PR-K independent price cross-check line (gold-api mid vs the alert price); PR-J measure 5m bar finalisation | MED–HIGH | LOW (K), none (J) | S / M | \|feed − reference\| per alert. Share of plan results decided on bars later revised. | untouched (K, J); a data-layer fix would need an amendment | K adds one line (approval) |
| 3 | Website publishing speed | PR-E run the test gate once per commit, not every 15 min. **On hold (added 12 Nov, R18 in `R14_AUX_REVISIONS_2026-11-12.md`):** the decision bar's GC volume is only about 64% complete at today's read time. An earlier read would lower that further and widen the live / backtest mismatch. | MED | LOW–MED | S | Alert latency −2.5 min (median about 5.3 → about 2.8 min after the close). Site publish 4.5–6.7 → about 2.5–4 min. | untouched | timing only (approval) |
| 4 | Historical data integrity | PR-L daily read-only integrity report: revisions per series, gaps, shut-hour rows, Dukascopy cross-check (`audit/tools/xcheck_dukascopy.py` exists) | MED | NONE | S–M | Gaps or revisions detected within 1 day, not by chance | untouched | none |
| 5 | Yahoo auxiliary-series revisions | PR-H keep the full record, gzip closed months, and split the manifest count into XAU vs auxiliary. PR-J extended to measure whether the auxiliary revisions (R14) ever change an engine decision. | MED (repo health; R14) | LOW (H is lossless); none (J) | S–M | `revisions/` about −89% by gzip alone (measured on GC_F_60m 2026-10). The manifest shows XAU revisions apart from the auxiliary ones; in the ten runs the counts were 1 XAU bar against up to 15,214 auxiliary. Also fixes a bookkeeping defect: a "series re-based" count row is appended under the `old_open` column, so the CSV reads as misaligned (7 such rows in run 3093). | untouched (`manifest.py` is not an engine source) | none |
| 6 | Risk and reward calculations | PR-I label the headline's engine levels as "engine levels, not your plan"; keep the plan line | MED | LOW | S | No second stop on the phone | untouched | wording (approval) |
| 7 | Economic news filters | PR-C repair the two broken feeds (display). Any trading filter (e.g. no new plan ±N min around high-impact USD events) only as a registered **risk** rule, not an edge (B8 rejected the edge) | LOW–MED | LOW (C) / MED (filter) | S / M | Feed availability 0% / about 30% → over 95% | untouched | C: none. A filter would suppress plans (registration + approval). |
| 8 | Signal probability calibration | Live reliability panel for B15 (Wilson intervals at the registered looks); audit that every probability shown carries n and CI | LOW–MED | LOW | S | Honest calibration once n ≥ 30 (B15 has 5 results today) | untouched | none |
| 9 | Multi-timeframe confirmation | No production change (B14 FAIL). Only a new pre-registered study on held-out data | LOW | MED | M | none proven | would restart the holdout if put in the engine | none |
| 10 | DXY and US10Y correlation | Display only: show the rolling correlation's instability (window CI). No gating (B7 REJECT). R14 is the data-quality side. | LOW | LOW | S | Display clarity only | untouched | none |

## 7. PR proposals (separate; none merged, none opened)
Each item is self-contained.
- **Ready.** PR-A and PR-B are committed on `claude/session-01fdjaothuvhxscxtl7ysa-y3n4w4`. They can be opened as two
  separate PRs on your word.
- **Not yet written.** PR-C … PR-L are proposals only; no code exists for them.

| PR | Title | Files | Status | Verification | Needs approval because |
|---|---|---|---|---|---|
| **PR-A** | Outage notice: make it run, and page only when alerts may be affected | `.github/workflows/quantum-site.yml`, incident note, PLATFORM row | **READY** (commit d5f221338) | Probe run 43127410617: pipeline failure → notice; store-save failure → notice; Pages-only failure → no notice. YAML parsed. Production run 3094 (a Pages-only failure) is the case it leaves silent. | It can send a phone message |
| **PR-B** | Stale-signal gate: close three edge cases | `quantum/notify.py`, `tests/test_stale_signals.py`, incident note | **READY** (commit c499d32b5) | 3 new tests; full suite 585 passed, 2 skipped (requirements.txt env). Real-payload replay: deployed vs PR-B byte-identical in 8 / 8 cases (phone, records, state). | It changes phone wording in edge cases |
| PR-B2 | Gate H2–H6 / DECISION lines older than 15 min in `ALERT_MODE=all` | `quantum/notify.py` | proposal | tests | phone output in `all` mode |
| PR-C | Repair news feeds (HTML entities before XML parse; replace or drop FXStreet) | `quantum/events.py` | proposal | fixture tests | none to alerts (display) |
| PR-D | Daily ntfy reconciliation (read-only): every `ok` entry of `alerts_delivery.json` must be in ntfy's cache with the same SHA-256 prefix; a mismatch fails the workflow, so GitHub emails you | new workflow | proposal | manual check today: 1 of 1 matched (af7c9b2bfe014103) | new workflow (sends nothing) |
| PR-E | Test gate once per commit (cache keyed by commit SHA + requirements hash; full suite still on every new commit) | `quantum-site.yml` | proposal | timing before / after | deploy gate behaviour |
| PR-F | Run watchdog: the Cloudflare scheduler checks the last successful run each tick; one ntfy notice if none in 35 min during market hours (covers `startup_failure`; a separate check for the dispatcher itself, since the GitHub cron cannot back it up, R15) | `scheduler/worker.js`, Worker secret `NTFY_TOPIC` (you add it) | proposal | worker unit tests | sends phone messages |
| PR-G | Acknowledge button on trade alerts (ntfy `Actions` header → relay worker `/ack?id=…`, recorded with the ntfy id) | `quantum/notify.py`, `relay/` | proposal | worker tests + one test-topic message **with your approval** | alert headers change |
| PR-H | Revisions log: gzip closed months, XAU vs auxiliary counts, write the "series re-based" count row in its own column. No tolerance that drops records: the auxiliary series are engine inputs (R14). | `quantum/manifest.py`, workflow | proposal | before / after sizes; every record kept | bookkeeping record |
| PR-I | Headline levels labelled "engine levels, not your plan" | `quantum/notify.py` | proposal | tests | phone wording |
| PR-J | Research: effect of 5m bar finalisation and of auxiliary-series revisions on plan results and engine decisions (pre-registered, read-only on the ledger) | `research/` | proposal | registration before code | none (research) |
| PR-K | Price cross-check line: alert price vs the gold-api mid of the same run | `quantum/notify.py` | proposal | tests | phone wording |
| PR-L | Daily data-integrity report (read-only) | new workflow + `audit/tools/` | proposal | dry run | none |

## 8. Safeguards confirmed intact
Verified at branch head c499d32b5 and in production, at the end of the ten runs.
- **Freeze key.** At HEAD it is `5e4630924d663fc5:a6f2be58c74887ed`. Every ledger manifest line since 10 Nov carries
  it, including the ten runs.
- **Research hashes.** Registration SHA-256 prefixes are unchanged:
  - B24 6078abc269e9d7fe
  - B24-A1 f3799d529cbf97ce
  - B24-A2 272ec21e7ae748f8
  - B15 70571cecc01c3ed6
  - B16 051def8c7d1cde76
- **Audit manifest.** `audit/MANIFEST.sha256`: every line OK.
- **No protected file touched.** The branch diff touches nothing in `research/`, `audit/`, `artefacts/`, the engine,
  `config.py`, `holdout.py` or `data/`.
- **B24 is OFF.** `fwd_b24.on()` is False with the variable unset. The production store holds only the tombstone and
  the void copy; no B24 trade.
- **Live records keep counting** (records unchanged by this work; store of run 3099):
  - B15-ENGINE-FWD: 5 results, 3 TP / 2 SL, no check yet (the first look is at 30);
  - B9-GRAB-FWD: 9 results, 4 TP / 5 SL;
  - SETUP-LIVE continues (setups #65–#68 were added in the ten runs).
- **No automatic trading.** No order placement or broker write access exists; MetaApi is not configured.
- **No test notification was sent.** None was approved.
- **Read-only checks.** `alert-delivery-check` only reads ntfy's cache for the topic and sends nothing.
- **Probes.** Two temporary workflows ran on the development branch with no secrets and no writes. Both were removed
  in the following commit. Net branch diff: PR-A + PR-B, and this note.
