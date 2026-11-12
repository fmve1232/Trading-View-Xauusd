# System audit, 13 Nov 2026 (00:00–04:30 PKT; 12 Nov 19:00–23:30 UTC): every feature, its evidence, and an improvement plan

**Scope.** The production website platform (`quantum/`, `site/`), the phone alerts, the records, the schedulers and
Workers, the research registry and the Pine reference.
- Audited at deploy head `30a3da10d` (PR #97 + #98 merged 23:03 UTC).
- **Read-only throughout.** No production setting, engine, threshold, record, registration or freeze key was changed.
- The only actions with effects outside this session: one read-only `alert-delivery-check` run, which sends nothing.

**How to read the evidence column.**
- **LIVE**: observed in production on 12–13 Nov.
- **TEST**: the suite. It ran locally in a requirements-only venv on a tree identical to the deploy head. Production's
  own gate also ran it on GitHub at 23:16–23:19 UTC (run 3182) and passed.
- **CHECK**: a repository checker.
- **NOT VERIFIED**: not checked in this audit, with the reason.

## 1. Results at a glance
| Area | Verdict | Key evidence |
|---|---|---|
| Deployment of PR #97 + #98 | **LIVE OK** | Run 3182 (23:16 UTC) on `30a3da10d`: tests, pipeline, store and ledger save, Pages deploy all succeeded; the new outage step was skipped (normal). Deployed tree = tested tree (`293eaff7`). |
| Phone delivery (server side) | **LIVE OK** | 11 Nov 22:29 – 12 Nov 23:05 UTC: 7 of 7 messages accepted by ntfy (HTTP 200, `alerts_delivery.json`): 2 × 15m SELL, 3 follow-ups, and the daily validations of 11 and 12 Nov. ntfy's cache held the 12 Nov validation (23:05:25 UTC, sha256 `0b019c2e`). |
| Phone delivery (on the handset) | **NOT VERIFIED** | Needs the operator's observation, or the controlled test once `NTFY_TEST_TOPIC` exists. |
| Test suite | **TEST OK** | 673 passed, 2 skipped (research-only ML libraries). 528 test functions. JS suites (costs, relay, scheduler) pass. Mutation tests 24/24 + 24/24. |
| Pine reference (v32) | **CHECK OK** | precheck / undeclared / order / deadcode / pinelimits: 0 findings in 7 files. diag_parity PASS. MANIFEST all OK. The 4 frozen hashes match `PREREGISTRATION.md` §2. |
| Freeze key and ledger | **CHECK OK** | `5e4630924d663fc5:a6f2be58c74887ed` in code, in `holdout_manifest.json` and in every run manifest. `ledger_check.py`: 0 problems (505 live + 1,286 archived records). |
| Research registry | **CHECK OK** | 18 registrations, 1,367 trial rows. Every recorded hash (4/4) matches its file. B24 stays OFF (void record kept). |
| Data feed (XAU/USD) | **LIVE OK** | 0 missing bars in 10 days on 5m / 15m / 60m. |
| Signal validity | **NOT VALIDATED** | No alert stream has passed a registered forward test (§4). |
| Security | **OK, with hygiene items** | No credential-shaped strings or hard-coded topics in the tree. Tests run without secrets. Least-privilege permissions per workflow. Dependency and tool pinning gaps (§3, F-03). |

## 2. Feature register (35 features)
### A. Data
| # | Feature | Status | Evidence | Open risk |
|---|---|---|---|---|
| 1 | XAU/USD spot bars, Twelve Data (5m–1d) | working | LIVE: 0 gaps in 10 days; 0–5 revised closed bars per run, manifest | none new |
| 2 | Spot volume = COMEX GC volume (D-07) | working, with caveats | LIVE | **R18:** 46–77% complete at the read. R16: revisions unlogged. 30m history 30.7% zero volume (before GC 30m data begins on 25 Aug). |
| 3 | Auxiliary series (GC, SI, DXY, EURUSD, US10Y, S&P, VIX) | working | LIVE: GC 5m 4 missing of 2,207 bars in 10 days | R14 version flips: low live impact |
| 4 | FRED / CFTC macro inputs | NOT VERIFIED | offline runs lack them; production fetches them | — |
| 5 | Store (one orphan commit per run) and manifest | working | LIVE: store and ledger saved 23:05 and 23:20 | No store history is kept, which limits audits. **The manifest records neither volume revisions nor library versions (F-03).** |

### B. Engine and statistics
| # | Feature | Status | Evidence | Open risk |
|---|---|---|---|---|
| 6 | Treatment / control / challenger arms × 5 timeframes | frozen, working | CHECK: freeze key; TEST: no-look-ahead tests in the gate | Treatment has 1–3 closed forward trades per timeframe since 3 Nov: no evidence either way |
| 7 | Research arms H2–H6 (forward ledger) | recording | `forward_stats.py` | 5m H4: mean −0.145 R [−0.240, −0.042] over 296 trades, the only interval that excludes 0. 15m H4 −0.024 R (79). 30m H4 +0.140 R (45). 1h H4 +0.178 R (24). |
| 8 | Calibrated probabilities | shown | — | **Calibration not assessable:** no ledger has ≥ 10 trades with a recorded probability. They are built on final volume (R18). |
| 9 | Backtest and site statistics | shown | — | Use final volume, so not fully representative of live inputs (R18) |

### C. Phone alerts (production mode `sixty`: only 15m engine signals and their follow-ups, registered-test checks, the daily report, news)
| # | Feature | Status | Evidence | Open risk |
|---|---|---|---|---|
| 10 | 15m engine signal alerts | working | LIVE 12 Nov: SELL 3871.20 sent 6.5 min after the close, SELL 3854.59 sent 5.8 min after (both FRESH) | **Not validated** (§4). The headline shows the engine's SL / TP next to the plan's $13 levels: two stops on the phone (PR-I). |
| 11 | Plan follow-ups (TP1, SL, back at entry) | working | LIVE: 3 follow-ups delivered | — |
| 12 | Stale-signal gate (PR #96 + #98) | working | TEST + mutation 24/24; LIVE: plan 11 (4h, 65 min) correctly NOT ACTIONABLE | The last bar before the daily shut is always processed after 60 min (25 of 28 days late). Benign: the market is shut that hour. |
| 13 | Daily validation + ENGINE status | working | LIVE 23:05:25 UTC. Recomputed from `plan_validation.json`: 4 closed, 1 TP first, matches. | **Mixes record-only plans (4h, 30m) with phone alerts (15m):** "4 signals closed" while the phone received 2 signals |
| 14 | Outage notice (PR #97) | deployed | TEST, probe, mutation; LIVE: skipped on 2 successful runs | Not yet exercised by a real failure (correct so far) |
| 15 | News lines | NOT VERIFIED | none in the window | — |
| 16 | Registered-test check messages (B15) | working | no check due yet (first look at 30 results) | — |

### D. Records and research
| # | Feature | Status | Evidence | Note |
|---|---|---|---|---|
| 17 | Frozen holdout ledger (§7 arms, Amendment 5 H2, H3–H6) | intact | `ledger_check` 0 problems | — |
| 18 | B15-ENGINE-FWD (registered) | collecting | 4 TP / 5 SL of 9 = 44% [19%, 73%]; break-even 51.0% | First look at 30 needs 21/30, i.e. 17 of the next 21. Between looks it is COLLECTING, not a verdict. |
| 19 | B9-GRAB-FWD (registered) | collecting | 4 / 10 = 40% [17%, 69%] | — |
| 20 | SETUP-LIVE (B16 rules, record only, not on the phone) | recording | BREAKOUT 32/47 = 68% [54%, 80%] reached +$15 before −$13. SWEEP 12/28. 4H BREAKOUT 7/16. 4H CONFIRMED 1/4. CONFIRMED 0/1. | **No registered forward decision rule.** BREAKOUT was picked after looking at 5 kinds, and overlapping setups are correlated. Exploratory only (§5, P2-3). |
| 21 | CONFIRM-LIVE / events (display) | recording | 98 rows, 291 events | — |
| 22 | B24-CONFIRM-FWD | **OFF** | void record kept; `FWD_B24` unset | as required |
| 23 | Research registry and trial log | intact | hashes 4/4 | — |

### E. Operations
| # | Feature | Status | Evidence | Open risk |
|---|---|---|---|---|
| 24 | Cloudflare dispatcher (:01 / :16 / :31 / :46) | working | LIVE: every slot 21:01–23:16 | R15 duplicates; R2 no watchdog; **R17 token expiry unknown** (Worker deployed 8 Oct; /check URL not in the repository) |
| 25 | GitHub cron backup | unreliable by GitHub | 1–7 of 96 a day | design only |
| 26 | GitHub Pages deploy | working | LIVE run 3182 | 28 historical Pages-only failures (no alert impact) |
| 27 | Stream relay Worker (live price chip) | deployed 12 Oct | JS tests pass | live chip NOT VERIFIED (site unreachable from here) |
| 28 | Reference prices, MT5 MetaApi, macro panel | steps succeed | LIVE steps OK | content NOT VERIFIED (display only) |
| 29 | Weekly Dukascopy price cross-check | working | last run 7 Nov success | — |
| 30 | alert-test / alert-delivery-check | working | LIVE run 5 (read-only) | — |
| 31 | Website itself | deployed | Pages step OK | rendering NOT VERIFIED here (host unreachable from this environment) |

### F. Engineering hygiene
| # | Item | Status | Evidence |
|---|---|---|---|
| 32 | Test coverage map | good on the core | engine 12 test files, notify 15, holdout 18, data.market 15; `quantum.sessions` has none of its own (covered indirectly) |
| 33 | CI on pull requests | **absent** | 0 check runs on PRs; tests run only in production's gate, i.e. after the merge |
| 34 | Dependency pinning | **absent** | `requirements.txt` sets minimums only (numpy ≥ 1.26, pandas ≥ 2.2). Test venv: numpy 2.4.6, pandas 3.1.1, Python 3.11. Workflow tools float: `wrangler@4`, actions pinned by major tag. |
| 35 | Documentation | mostly accurate | PLATFORM.md lists D-01 … D-13. **R18 is not listed**, which by the repository's rule makes it a defect. Two earlier statements of mine were wrong and are corrected (§6). |

## 3. Findings (new in this audit)
| # | Finding | Severity | Type |
|---|---|---|---|
| F-01 | **No alert stream is validated.** The phone's 15m stream was chosen for 64% on 2020–22 (61% on 2023–24, not passed after Holm). Live it shows 32% of 22 (Sep–Nov, B9-explore) and B15 4/9. Alerts carry "not proven" in their record line, but the phone still presents plan levels to trade. | HIGH (decision risk) | operator decision |
| F-02 | **R18:** decision-time volume incomplete. Live and history differ, and the difference is undocumented versus Pine. | MEDIUM–HIGH | study first; amendment to fix |
| F-03 | **Library versions are neither pinned nor recorded.** The freeze key hashes source files only, and each run installs the newest numpy / pandas. The frozen engine's behaviour can change under an unchanged key, and the records could not show it. | MEDIUM (holdout integrity) | bookkeeping first, then pin |
| F-04 | **No CI on pull requests.** Every check before a merge is local. | MEDIUM (process) | ops |
| F-05 | **The daily report mixes record-only plans with phone alerts.** | LOW–MEDIUM (clarity) | display |
| F-06 | **Two stops on the phone:** engine headline SL / TP next to the plan's $13 levels (PR-I). | LOW–MEDIUM (clarity) | display |
| F-07 | The last 15m bar before the daily shut is always processed > 60 min late (25 of 28 days). Benign because the market is shut; it also moves the daily report to about 23:05 UTC. | LOW | information |
| F-08 | The dispatch token's expiry is unknown (R17). | MEDIUM until checked | operator check |
| F-09 | SETUP-LIVE BREAKOUT shows 68% [54, 80] live but has no registered decision rule. | INFO (opportunity, not evidence) | registration if wanted |
| F-10 | 5m H4 research arm is significantly negative on the frozen ledger. | INFO | none (research arm, not alerted) |

## 4. What "validated" means here, and where each stream stands
A stream counts as validated only when a **registered** forward test passes its pre-declared rule on new data.

| Stream | Registered test | Status |
|---|---|---|
| 15m engine signals (the phone) | B15-ENGINE-FWD | 4/9, COLLECTING; first look at 30 results; deadline 30 Jun 2027 |
| Liquidity grabs | B9-GRAB-FWD | 4/10, COLLECTING |
| Operator setups (B16 rules) | none for the live record | exploratory |
| Engine + $15 confirmation | B24 | OFF |

Under the operator's rule ("No valid signal = No trade"), **none of today's alert streams is a valid signal yet.**

## 5. Improvement plan
Each item states its class and what it would need.
- Nothing here tunes a threshold or changes the engine.
- Items marked **amendment** restart the frozen holdout and need a written amendment first.

### P0: operator, now (no code)
1. **Phone check.** In the ntfy app's history, look for the 7 messages of 11–13 Nov: 15:06, 15:21, 15:35, 15:50 and 16:04 UTC on 12 Nov, and the daily validations at 22:29 UTC on 11 Nov and 23:05 UTC on 12 Nov. Say which appear and which showed a banner.
2. **Controlled test.** Add `NTFY_TEST_TOPIC`; then I send the one labelled message.
3. **Trading stance (F-01).** Treat every alert as information, not a trade signal, until B15 or another registered test passes.
   - Option, for approval: switch phone trade alerts to an explicit **"RECORD — NOT A VALIDATED SIGNAL, NO TRADE"** wording, keeping the plan line for the record only. This is display only.
4. **Token expiry (F-08).** Check `GH_DISPATCH_TOKEN` on GitHub (Settings → Developer settings → Fine-grained tokens): note the expiry date, or renew it with 90 days.

### P1: low-risk bookkeeping and operations (each needs approval; no freeze-key change)
| # | Item | Class | Effort | Benefit |
|---|---|---|---|---|
| 1 | Record Python / numpy / pandas versions in every run manifest | bookkeeping | S | Makes F-03 visible from the next run |
| 2 | Pin dependencies to the versions production installs today (constraints file), verified byte-identical outputs before and after | ops | S | Closes F-03 without changing behaviour |
| 3 | PR CI: a `pull_request` workflow running pytest + node tests, no secrets, read-only | ops | S | Real GitHub verification before any merge (F-04) |
| 4 | Daily report: separate "phone alerts (15m)" from "record only (30m / 1h / 4h)" | display | S | F-05 |
| 5 | PR-I: label the headline levels as engine levels; one stop on the phone | display | S | F-06 |
| 6 | Scheduler reliability (R15 / R2 design): one run per slot, re-check and retry, watchdog, token-expiry notice | ops | M | Duplicates → 0; missed runs reported within 35 min |
| 7 | PR-H: log volume revisions; split XAU vs auxiliary counts | bookkeeping | S | R16 |
| 8 | Document R18 in PLATFORM.md as D-14 (it stays a defect until measured and decided) | docs | S | Makes the live / backtest difference explicit |
| 9 | Pin `wrangler` exactly; consider SHA-pinned actions | ops | S | Supply-chain hygiene |

### P2: read-only research (approval of each protocol)
1. **R14 / R18 study** (protocol v2): decision-time completeness by session, and the per-read counterfactual.
2. **B15** continues unchanged to its first look.
3. **Optional:** register a forward test for SETUP BREAKOUT (B16 rules) **before** reading any further results. The 47 so far are exploratory and cannot count.

### P3: only after P2 evidence, each an **amendment**
1. R18 fix, if the study reads "material": volume gates on the last complete bar, or a data-layer change.
2. R14 fix, if material: keep the first stored version of closed auxiliary bars.

### Not recommended
- **Reading data earlier (PR-E):** it worsens R18.
- **Dispatching inside the shut hour:** the market is closed, so it gains nothing tradeable.
- **Raising signal frequency or relaxing any threshold:** the operator's rule.

## 6. Corrections to earlier statements
- **"No 15m signal since 10 Nov"** (in my 12 Nov evening update and in `MOBILE_DELIVERY_TEST.md`) was wrong. Two 15m SELL alerts and three follow-ups went out on 12 Nov, 15:06–16:04 UTC (20:06–21:04 PKT). The test plan is corrected.
- **"Daily validation at 03:25–03:35 PKT"** was wrong. It is sent by the first run after the New York close, normally about 04:05 PKT (corrected in `a19439c58`).

## 7. Not verified in this audit (and why)
- **Handset display:** needs the operator.
- **Website rendering and the live price chip:** the Pages host is unreachable from this environment.
- **Worker `/check` endpoint and token expiry:** the URL is not in the repository.
- **FRED / CFTC inputs:** offline only.
- **News lines:** none occurred in the window.
