# Prioritised remediation plan — XAUUSD Quantum (2026-11-14)

**Source:** the operator's master directive of 2026-11-14 ("complete all identified issues …").
**Builds on:** the independent audit `docs/audit/INSTITUTIONAL_AUDIT_2026-11-14.md` (findings IA-01 … IA-24) and the
eight draft PRs #105–#112.

**What this document is:** the plan the directive asks for *before any frozen production component changes*. Nothing
here is merged or deployed. Every claim cites a file, a record or a command result.

---

## 1. Two approval gates (operator governance, adopted)

**Software correctness is not trading profitability.** A strategy is eligible for live trading only when **both** gates
pass.

| Gate | Passes when | Status today |
|---|---|---|
| **A — Technical** | Data, calculations, execution instructions and alerts are correct, consistent across engine / payload / site / phone / MT5 text, reproducible, and tested (each test fails when its rule is broken) | **Not yet.** 8 fixes in draft (#105–#112); new items N1–N8 below; engine defects F1–F3 need approval |
| **B — Trading** | A pre-registered out-of-sample test **and** a forward test show an edge after realistic costs: Wilson 95% lower bound above break-even, matched-random comparison, multiple-testing correction | **Not met by any strategy.** Engine signals: B15 forward 5/13 (38.5%, 95% 17.7–64.5%) vs break-even 51.0%. Breakout / sweep: development at random (46.1% of 6,729 / 46.6% of 5,918 vs 46.2–46.3%). B17 / B18 / B19 / B21 / B22 / B23: FAIL |

**Until Gate B passes for a strategy, every alert from it stays "NOT A VALIDATED SIGNAL — NO TRADE"** (as now). No
change in this plan turns an alert into a recommendation.

## 2. What is frozen (exact)

| Protected item | What it covers | Changing it means |
|---|---|---|
| Freeze key `5e4630924d663fc5:a6f2be58c74887ed` | = `config.hash()` : hash of `holdout.ENGINE_SOURCES` = `ta.py, sessions.py, features.py, analog.py, engine.py, backtest.py, config.py, pipeline.py, data/sources.py, data/market.py, data/store.py` | The website holdout restarts (new key; old ledgers archived) |
| B15-ENGINE-FWD | "a SIGNAL event of the **frozen** treatment engine" (`research/registrations/B15-ENGINE-FWD.json`) | **Any engine change changes the stream B15 measures**, so the registration must be amended or B15 ends |
| Pine reference | 7 files in `artefacts/` at the hashes in `audit/MANIFEST.sha256` / `PREREGISTRATION.md` §2 | Engine fixes must go to Master, Strategy, CHALLENGER and Diagnostics identically (CLAUDE.md) |
| Registrations | 18 files in `research/registrations/` | Never edited; changes go into a dated amendment |
| Registered constants in non-frozen files | `notify.py` `ENG_PX / ENG_BE / ENG_LOOKS / ENG_DEADLINE` (B15), `GRAB_TP / GRAB_SL / GRAB_BE` (B9), `SETUP_TP_PX / SETUP_SL_PX` (B16); `fwd_b24.py` `OP_COST / BREAK_EVEN` (B24) | Not in the freeze key but registered: never changed silently |
| Records | `forward-ledger` (holdout ledgers + archive, `research_forward/*.json`, manifests), `market-data` | Append-only; never rewritten |

**Verified unchanged by all eight draft PRs:** each PR's tree gives the same freeze key, `audit/MANIFEST.sha256` OK,
and no registration or record file is touched.

## 3. The eight draft PRs — state

| PR | Item | GitHub CI | Mutants caught | Replay / browser |
|---|---|---|---|---|
| #105 | IA-01 RECORD line from records, per idea, Wilson | green | 6/6 | only RECORD lines change |
| #106 | IA-07 conditional MT5 wording | green | 4/4 | only ON MT5 lines change |
| #107 | IA-02 NOT CALIBRATED labels | green | — (template tests) | 0 page errors |
| #108 | IA-06 both costs, one definition | green | 7/7 | only YOUR PLAN lines change |
| #109 | IA-12 payload archive + SHA-256 | green | 6/6 | end-to-end on the real store |
| #110 | IA-04 engine levels named; phone plan shown | green | 5/5 | values checked in the browser |
| #111 | IA-13 fixed-risk sizing (stacked on #110; conflict resolved in `e94713ae5`) | green on the stacked head | 5/5 | 0 page errors |
| #112 | IA-19 / IA-21 completeness warning + lock | green | 7/7 | clean venv = production versions |

**All eight combined** (scratch tree): 814 passed, 2 skipped. A two-day replay changes only RECORD / ON MT5 / YOUR PLAN
lines; plans and logs are identical.

## 4. Prioritised backlog

**Classes:**
- **N** — not frozen: safe to build now as separate draft PRs.
- **F** — frozen: needs an amendment and the operator's approval first.
- **D** — needs operator data or a decision.
- **R** — research: pre-registered, development data only.

| Pri | ID | Class | Severity | Issue (evidence) | Proposed fix | Acceptance |
|---|---|---|---|---|---|---|
| 1 | **N1** | N + D | **High (new)** | **The phone plan risks 2.6% per trade, not 1%.** It is 0.5 lot × $13 stop = $650 on `ACCOUNT_USD` $25,000 (`notify.py:348`, `plan_cfg` defaults); with costs, 2.65%. The directive sets 1% | Lot = floor(account × risk% ÷ ((stop + cost/oz) × 100), volume step), from `PLAN_RISK_PCT` (default 1.0). Reject the plan line (NO TRADE: "lot below the broker minimum / above maximum") when outside [min, max]. Price levels unchanged, so B15 is unaffected | Hand-worked examples: $25,000, 1%, $13 stop, $0.26 → 0.18 lot; at $0.97 → 0.17 lot. Mutants; replay shows only lot / money figures change |
| 2 | **N2** | N | High | **Alert fields missing** (audit H.2): no visible signal ID, no status, no data-freshness line, no invalidation statement, no "why" | Add a header `#<plan id> · <STATUS>` (ACTIVE = confirmed close; follow-ups already send TP1 / BE / TP2 / SL / EXPIRED), a freshness line (bar close age, price source, LATE flag already exists), "Invalid if: SL hit or 3 days without a result", and the engine's met-gates line | Field checklist test on a real rendered alert; replay diff limited to the added lines |
| 3 | **N3** | N | High | **No cross-surface consistency test**: the same signal's levels are computed in `notify.plan_levels`, `site/app.js myPlanPx` (#110), the MT5 line, `plan_validation.json` | One test builds a signal and asserts identical entry / SL / TP1 / TP2 / lot / money in all four (Node for the JS) | The test fails under each single-surface mutant |
| 4 | **N4** | N | Medium | **Concurrent exposure not shown** (IA-17): B15 had 13 SELLs in 4 days, 11 non-overlapping | The phone line shows the open plans in the same direction and today's realised R; a warning above the daily-loss limit (existing `DAILY_LIMIT_PCT`) | Unit tests on exposure arithmetic |
| 5 | **N5** | N | Medium | **Strategy detectors live inside `notify.py`** (2,997 lines; `_run` complexity 180) (IA-15) | Move SETUP / H4 / GRAB detection to `quantum/strategies.py` (pure functions); notify only formats and sends | Byte-identical replay of all records and messages over 2 weeks |
| 6 | **N6** | N | Medium | **No unit tests for `site/app.js` logic** (IA-18) | Node harness that loads pure functions (sizing, plan, labels) as #110 / #111 do | Coverage of every money / level function on the page |
| 7 | **N7** | N | Low | **Unused code outside frozen files** (IA-22): `confirm_panel.SEEN_SEC`, `news_calendar.now_utc`, `arm_h2` unused local, `arm_h4` unused import | Remove after tracing; document what stays (`contract.py` mirrors `costs.js`) | pyflakes / vulture clean on non-frozen modules |
| 8 | **N8** | N | Medium | **Event risk invisible on the phone** (P-4); spread is modelled, never measured | Event-risk line near NFP / CPI / FOMC (display only; B8 found no robust effect, so no blocking); spread labelled "modelled" | Window tests |
| 9 | **F1** | F | Medium | **PWH / PWL omit each day's first bar** (IA-05; 4h: 9/37 weeks wrong, up to $30.29), in Pine too | Update the weekly accumulators on every bar (`engine.py:294-306`, Pine Master / Strategy / CHALLENGER / Diagnostics) | Independent check 0 differences on 15m / 1h / 4h; `diag_parity.py`; hunk-count rules |
| 10 | **F2** | F | High | **The EV gate evaluates the engine's ATR plan, not the plan sent** (IA-04) | One plan of record: evaluate EV on the alerted geometry, or send the engine's levels. Operator decision | Pre-registered; forward test restarts |
| 11 | **F3** | F | High | **An uncalibrated p drives the calibration gate and EV** (IA-02) | Remove p from gates (or replace it with a validated model) | As F2 |
| 12 | **F4** | F | Low | Daily HTF series on UTC days vs NY-17:00 levels (IA-20); unused `config.commission_per_oz`, `sources._empty` | NY-session daily bars; remove dead fields | Parity / replay |
| 13 | **D1** | D | **High** | **Broker facts unverified**: contract size, tick size / value, volume min / step / max, commission, swap, spread, execution mode (IA-08, IA-06, IA-09) | Operator provides MT5 *Specification* + one closed trade's IN / OUT deals (or connects MetaApi with the **investor** password for live bid / ask) | `contract.py` status VERIFIED; costs from deals; spread measured |
| 14 | **D2** | D | High | **Account balance / equity and prop rules** (daily loss, overall drawdown) unknown to the system | Operator confirms balance and firm limits; they become repository variables | N1 / N4 use them |
| 15 | **D3** | D | Medium | Phone delivery to the device never acknowledged | Operator confirms on the phone after the Sunday open; optional `NTFY_TEST_TOPIC` one-shot test | Device confirmation recorded |
| 16 | **R1** | R | — | Breakout / sweep definitions per the brief (penetration in ATR, reclaim, rejection-wick ratio, displacement, MSS / CHoCH within N bars, retest) | One small pre-declared family, development data, validation once, Holm | Net expectancy 95% LB > 0 and beats matched random |
| 17 | **R2** | R | — | Fixed-dollar targets across price regimes (IA-14) | Volatility-scaled targets study | As R1 |
| 18 | **R3** | R | — | Calibrated probability on the phone | Only if a model shows skill out of sample (B22: none). Otherwise show the base rate and the geometry, as now | Reliability / Brier vs base rate on validation |

### The "$15–20 favourable movement" confirmation (directive §6): already measured, not adopted

| Study | What was tested | Result | Verdict |
|---|---|---|---|
| B19 | Wait for a 15m close $15 / $20 beyond the trigger | development +$2.32 / oz (t 1.52), **validation −$3.04 / oz** | FAIL |
| B21 | The same after GRAB / BREAK / SWEEP / BREAKOUT | 43.4–49.6% target-first vs 46.2% random; "any time" 62–72% vs 64–66% random | FAIL 8 of 8 |
| B25 | Execution timing after the $15 close | close 46.4%, +15 min 47.5%, +30 min 48.9%, retest 45.2%, stop order 39.9% vs 46.3% | No gain |

**Conclusion:** the confirmation delays the entry by $15–20 without improving the outcome. It is a late entry, not a
filter, so it stays a website research panel (B24 recorder OFF) and is not a release condition.

### Lifecycle states (directive §6) — what exists, what N2 adds

| State | Exists today | Where |
|---|---|---|
| Setup detected | yes (website) | SETUP / confirmation panel "INITIAL SETUP (not a trade)" |
| Setup confirmed | yes (website) | confirmation panel CONFIRMED |
| Entry activated | implicit (the alert is sent at the confirmed close) | N2 makes it explicit: `ACTIVE (entry = the signal bar's close)` |
| Invalidated | yes | confirmation panel INVALIDATED; stale gate "NOT ACTIONABLE" |
| TP / SL reached, expired | yes | plan follow-ups (TP1, BE, TP2, SL, EXPIRED) |

## 5. Order of work

1. **Now (no approval needed beyond this directive):**
   - N2, N3, N5, N6, N7 and N8 as separate draft PRs, each with tests, mutants, a replay and a browser check where relevant;
2. **Needs operator input:**
   - **N1** needs the account balance and risk % confirmed (default 1% of $25,000 → 0.17–0.18 lot, replacing 0.5 lot);
   - **D1–D3:** broker specification, one closed deal's history, prop-firm limits, device confirmation.
3. **Needs operator approval and an amendment:**
   - F1–F4 batched into **one** amendment, so the holdout restarts once (IA-10);
   - **B15 decision:** amend now, or after its first look at 30 results; recommendation in §6.
4. **Research (only with a registration the operator approves):** R1–R3.

## 6. Recommendation on frozen fixes vs B15

- B15 measures the frozen engine. Fixing F1–F3 changes that engine, so B15 must be amended or closed.
- The operator's standing instruction is "continue B15 unchanged until its registered decision point".

**Recommendation:**
- Build F1–F4 now on a branch, with the amendment text, the parity checks and a replay showing which past signals would
  change. **Do not merge.**
- Merge it at B15's first look (30 decided results, needs 21; currently 5 of 13) or at a date the operator chooses.
- Arithmetic for that look: B15 needs 16 wins in the next 17 trades. If the true rate is at break-even, the chance it
  ever passes is about 1.5% (audit F.6).

## 7. What is not promised

- No accuracy or profitability is claimed or targeted.
- Gate A can be completed by engineering.
- Gate B can only be passed by evidence: today none exists for any strategy, and NO TRADE remains the correct verdict.
