# PR #90: final independent audit and deployment decision (2026-11-07)

Operator request 2026-11-07 ("PR #90 FINAL INDEPENDENT AUDIT, VALIDATION & DEPLOYMENT DECISION"). Nothing is merged,
deployed or activated by this audit. Two standards are kept apart throughout:

- **Software reliability:** does the code do what it says, without breaking anything?
- **Trading reliability:** has any strategy shown a validated edge?

Passing software tests is evidence only for the first.

## 1. What PR #90 changes (diff against the base `219f89272`)

| Area | Files | Effect |
|---|---|---|
| Production Python | `quantum/confirm_panel.py` (new), `quantum/notify.py` (3 hunks: the `json_safe` helper, the guarded panel call, the return through `json_safe`) | Website data only |
| Production website | `site/app.js`, `site/index.html`, `site/style.css` | One new card; a tolerant JSON loader |
| Research | `quantum/research/b19.py` … `b23.py`, `research/` write-ups, registrations, results, tools; `research/trials.jsonl` (appended only) | Never imported by production (`tests/test_integrity.py`) |
| Tests | `tests/test_confirm_panel.py`, `tests/test_index_json_strict.py`, `tests/test_research_b19.py` … `b23.py` | |
| Docs | `docs/PLATFORM.md` (rows added), this file, `docs/deploy/PR90_OPTION_A.patch` | |

**Not changed:**
- no Pine artefact, and no file in `holdout.ENGINE_SOURCES` (the freeze key is unchanged);
- no `config.py`, no workflow;
- no phone-alert code path;
- no B9 / B15 rule;
- the above-60% mode.

Every modified non-code file only gains lines.

## 2. Confirmation engine audit

| Requirement | Evidence |
|---|---|
| Confirmation needs a completed 15m close | The 15m chart holds closed bars only: `sources.drop_incomplete` moves a still-forming bar to the display-only `meta.forming`. The rule compares the bar's close; a high or low never confirms (`test_a_touch_never_confirms_and_96_bars_expire`). |
| No intrabar confirmation | The same bar touching −$13 and closing $15 beyond counts as INVALIDATED (`test_a_bar_that_invalidates_and_closes_beyond_is_invalid`). |
| No future information | On every prefix of random price paths the state machine reads PENDING until its event bar, and from then on exactly what the full history says. Exits behave the same way (`test_no_look_ahead_on_every_prefix`). |
| Each bar examined once; nothing shown is rewritten | **Fixed in this audit.** Before, every run re-read all bars, so a vendor revision of a past bar could have confirmed a pending row "in the past" or moved an entry. Now each run examines only bars no earlier run examined. A displayed confirmation, entry, invalidation, expiry or exit never changes. A revision that would change a decision is flagged `revised`, not applied. Tests: `test_a_revised_bar_never_changes_a_decision_already_shown`, `test_a_pending_row_is_not_confirmed_on_a_bar_already_examined`, `test_incremental_runs_equal_one_full_run`. |
| Expired triggers cannot become confirmed | A finished row leaves the tracked list and is never re-evaluated (`test_an_expired_row_never_becomes_confirmed`). |
| SL / TP consistency | SL = entry − $13, TP1 = entry + $15, TP2 = entry + $20 (mirrored for SELL). The exit rule is identical to B19: a gap fills at the open, a two-level bar counts as the stop, 192-bar time stop. |
| The entry price is executable | **Partly.** The entry shown is the confirming 15m close, a price that traded. You can only act when the page updates: 3–66 minutes after the close in the 5 live cases recorded. Section 3 measures what a 15-minute delay costs. The card says "Entry (reference)" and to set SL / TP from your own fill. |
| Rejected triggers stay visible | On the card for 3 days ("Why no entry was taken"); 500 rows in the state; and every finished row, accepted or rejected, appended to `research_forward/CONFIRM-LIVE.json`. The workflow copies that file to `forward-ledger` every run, and it is never trimmed (`test_every_finished_row_goes_to_the_durable_audit_file`). |
| Research and live give the same result | Trade for trade on random paths (`test_live_state_machine_and_exits_equal_b19_on_random_paths`). On 2020–22 history, every trade agrees (`research/tools/excursions.py`); that check found and fixed one rounding difference in the live time-stop price. |
| Reported examples against the raw vendor bars | All 20 panel rows of 4–6 Nov were recomputed from `XAU_USD_15m/2026-11.csv` with plain `csv` code: **20 of 20 match.** #7 BREAK BUY: trigger 4,078.75, confirmed 4,108.97, +$15 and +$20 hit. #17 GRAB SELL: confirmed 4,050.16, best +$13.43 (within $1.57 of TP1), then the stop. |
| Trigger prices | Every trigger price checked against the raw close of its own bar on its own timeframe: 23,894 (2020–22) + 5,812 (2026), **0 mismatches**. |

## 3. Statistical validation (`research/tools/pr90_audit.py`, `research/results/pr90_audit_2026-11-07.json`)

**Trade definition:**
- Direction and entry: the trigger's direction. Entry at the first 15m close $15 beyond the trigger price (or at the trigger, for random entries).
- Before entry: invalid if price first trades $13 against, or an opposite 15m structure break prints; expired after 96 bars.
- Exits: SL −$13, TP +$15 / +$20 from the entry. A bar opening beyond a level fills at the open; a bar touching both counts as the stop; 192-bar time stop.
- Scaling: **distances are scaled to price / 4000**, so at $1,800 gold "+$15" is +$6.75. Results are $ per oz at $4,000.
- Costs: the model cost ($0.77–0.97: spread, 2 × slippage, commission) or your $0.26.

**Reproduction:** an independent loop written from this text, not from the research code, reproduces every trade with **0 mismatches** in outcome, net result or confirmation bar.

### 2020–22 (development; the figures reported before)

| Population | Trades | +$15 before −$13 (95%) | +$20 | Stop first | Neither | Expectancy, model / your cost | PF | Max DD | Longest losing run | BUY / SELL |
|---|---|---|---|---|---|---|---|---|---|---|
| Random entries | 16,384 | **46.3%** (46–47) | 39.2% | 53.7% | 0% | −$0.90 / −$0.31 | 0.88 | 1,138 R* | 9 | 47% / 46% |
| Engine signal after a $15 close | 20 | **60.0%** (39–78) | 50.0% | 40.0% | 0% | +$2.97 / +$3.54 | 1.53 | 4.3 R | 4 | 75% of 8 / 50% of 12 |
| Liquidity grab after a $15 close | 302 | **43.4%** (38–49) | 35.1% | 56.6% | 0% | −$1.68 / −$1.11 | 0.79 | 45.0 R | 10 | 44% / 43% |
| Breakout after a $15 close | 958 | **48.4%** (45–52) | 40.6% | 51.6% | 0% | −$0.17 / +$0.39 | 0.98 | 32.9 R | 9 | 48% / 49% |

\* Over all 16,384 random trades: drawdown grows with the number of trades.

### Is the engine's 60% meaningful? No, not as evidence of an edge.

1. **Small sample.** 12 of 20; 95% interval 39–78%. Against random triggers through the same confirmation (45.3%), one-sided p = 0.14. Against break-even, p = 0.23.
2. **Selection.** B19 measured 144 engine configurations on these data. With that many 20-trade samples, at least one reaching 12 of 20 by luck is practically certain (the configurations overlap, but the point stands).
3. **Clustering.** Three of the 12 wins are one day (24 Feb 2022, the invasion of Ukraine), on three timeframes. Without that day: 9 of 17 (53%).
4. **Fragile to timing.** Entered one 15-minute bar later, the same 20 trades win 30% (6 of 20), expectancy −$5.43.
5. **Out of sample:**
   - 2023–24 validation (B19, +$20 only): 5 of 7.
   - 2026 (Mar–Nov, unsealed, never used to choose anything): 13 of 23 = **56.5%** (95% 37–74%), +$2.01 per oz; 21 of the 23 are SELLs in a falling market.
   - Pooled 2020–22 + 2026: 25 of 43 = 58% (95% 43–72%), which still includes the random rate.

It is a lead, not an edge. The only honest next step is a registered forward test, which needs your approval.

### By regime, session and year (2020–22, +$15)

| Population | Trending | Ranging | Volatile | News | Best / worst session |
|---|---|---|---|---|---|
| Engine after a $15 close | 65% of 17 | — | 64% of 14 | 2 of 2 | London+NY 78% of 9 / New York 0% of 3 |
| Breakout after a $15 close | 48% of 377 | 48% of 322 | 47% of 240 | 54% of 41 | London+NY 53% / London 43% |
| Random | 46% | 46% | 46% | 45% | 46–47% everywhere |

Every split is inside the noise of its own sample size.

### 2026, the newest data (descriptive)

| Population | Trades | +$15 before −$13 (95%) | Expectancy (model cost) |
|---|---|---|---|
| Random entries | 3,970 | 46.1% (45–48); BUY 42%, SELL 50% | −$0.94 |
| Engine after a $15 close | 23 | 56.5% (37–74) | +$2.01 |
| Grabs after a $15 close | 81 | 53.1% (42–64) | +$0.98 |
| Breakouts after a $15 close | 305 | 52.8% (47–58) | +$0.92 |

The 2026 figures are higher than 2020–22. They are not validation:

- these are 24 looks;
- 2026 was a directional year (random SELLs won 50%);
- the confirmed breakout rule failed its registered development test (B21 H7), so it was never eligible for a validation run.

If you want it tested, it needs a new registration.

## 4. The dashboard's probabilities

| Shown on the card | What it is | Label |
|---|---|---|
| "Target-before-stop probability" | +$15 (or +$20) reached before −$13, after a $15 confirmation, with its trades, period and 95% interval | Status of that type: `NOT VALIDATED: its registered test failed` (grab, break, sweep, breakout) or **`INSUFFICIENT DATA — NOT STATISTICALLY VALIDATED`** (engine: 20 trades; 4h: never measured after a confirmation) |
| "Target touch, stop ignored" | +$15 / +$20 reached within 24 h | Explicitly "not a profit measure" |
| "+$15 before −$13, entered at the trigger" (evidence table) | The same plan without waiting | Its own column |
| "Confidence score n / 7 checks" | A count of conditions met | "a count, not a probability and not validated" |
| Live record | Results since the panel started | `INSUFFICIENT DATA — NOT STATISTICALLY VALIDATED (fewer than 30)` until 30 results |
| Headline | — | `NO TRADE — INSUFFICIENT CONFIRMATION` while no type is validated |

`test_every_probability_carries_its_sample_period_and_status` checks that every rate has a sample size, a period and a status.

## 5. Software checks

| Check | Result |
|---|---|
| Full test suite, PR head | 475 passed (the final commit; ruff clean on the new files) |
| Full test suite, option A tree | 412 passed |
| Production regression | Base vs PR vs option A on identical real inputs: the live store's state, real payloads, replays of 0, 1 and 3 days. With every alert stream on: **55 phone messages / 484 lines, 137 report lines, the full state and every store file are identical**. The only differences are the new panel block, the new audit file and NaN → null. |
| Rollback | The old code, run on the state the new code left, works. It keeps the panel's state key untouched; the audit file is inert. |
| Browser (Chromium, 1400 px and 390 px) | Old site + today's index.json (14 NaN values): the plan card stays empty (bug reproduced). Option A, with that file or a strict one: renders. Option B: renders, plus the card. No script errors, no horizontal scroll. |
| Strict JSON | index.json, the five chart files, the state file and the audit file all parse strictly. |
| Panel cost | 0.05 s per run; state 34 kB; audit file about 0.7 kB per finished trigger (about 2 MB a year) |

## 6. Known limitations

1. The entry is the confirming close. Your fill comes 3–66 minutes later. On the 20 engine trades a 15-minute delay changed 60% into 30%.
2. Research distances are scaled to price / 4000; live distances are literal dollars.
3. The live panel reads the site's feed (Twelve Data). MT5 prices differ by $1–3, and the MT5 offset setting shifts the display only.
4. Structure invalidation uses the engine's 15m BOS / MSS / CHoCH markers. They are causal, but they are not in the raw CSV, so the raw check used the chart's markers.
5. A trigger can appear late: one seen only after its bar was processed is flagged; one that later vanishes is kept and flagged.
6. The card is long on a phone (about 2,800 px with the current 3 days of rows); rejected rows are folded.
7. Nothing on the card is validated. It cannot tell you that a trade will work.

## 7. Rollback

1. **Option A or B merged:** `git revert -m 1 <merge commit>` on `claude/audit-prompt-real-artefacts-nekqv6`, then run the `quantum-site` workflow. The site returns to the previous build within one run. The alert state stays compatible (tested).
2. **Option B only:** the code has a `CONFIRM_PANEL=0` switch, but the workflow does not pass that variable today. Using it needs a one-line workflow change, so a revert is simpler.
3. Leftovers are harmless: `alerts_state.json` → `confirm` (ignored by the old code) and `research_forward/CONFIRM-LIVE.json` (inert; delete it from `market-data` and `forward-ledger` if wanted).

## 8. Deployment options

| | Option A: strict JSON only | Option B: PR #90 as is |
|---|---|---|
| Contents | `docs/deploy/PR90_OPTION_A.patch`: `notify.json_safe`, the tolerant loader, its test, one doc row (21 lines + test) | A + the confirmation card, its state and audit file, and the research |
| Fixes the empty alert cards | Yes | Yes |
| Phone alerts | Identical (tested on real data) | Identical (tested on real data) |
| New trading behaviour | None | None: display only, every row NO TRADE |
| Risk | Very low | Low for software. For trading: it shows exact entries, stops and targets for strategies that have no validated edge; the labels say so, but the numbers invite action. |
| Benefit | The site shows every alert card again on days with nothing decided | Plus a timestamped, durable record of every trigger and its confirmation, which a registered forward test could later use |
| If A goes first | PR #90 would need a merge of the base (an identical-hunk overlap; `docs/PLATFORM.md` needs one manual resolution) | — |

## 9. Recommendation: Option A now; hold Option B

- **Option A** fixes a real, reproduced production bug: the website's alert cards are empty on most days. It is a minimal change, and real-data replays show no other effect. It meets the software standard, and the trading standard does not apply to it.
- **Option B** meets the software standard. It does not serve the trading standard: everything it shows is unvalidated, and its main output is NO TRADE. Its useful role would be as the display for a registered forward test of the one lead (engine signal + $15 confirmation), which needs your approval of a registration first.
- **Neither** is the wrong choice: the bug is live now.

Merging, deploying, or opening a separate pull request for option A each waits for your explicit approval.
