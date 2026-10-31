# Independent audit of v90: audit state (read-only)

| | |
|---|---|
| **Started** | 2026-10-31 |
| **Baseline** | v90, commit `ff9536959`. No Pine file is modified by this audit. |
| **Mandate** | Operator's "MASTER PROMPT — XAUUSD QUANT SYSTEM V90" (23 sections, 13 reports). Implementation needs separate approval. |
| **Method** | Independent of the earlier checkers wherever possible. Each result is labelled with how it was established. |

**Result labels:**

| Label | Meaning |
|---|---|
| EXECUTED-PINE | The Pine text itself was run (`pine_exec`). |
| EXECUTED-TRANSCRIBED | My own Python transcription of the Pine line(s) was run against an independent truth. This tests my reading, so the transcription is listed. |
| READ | The code was read and the algebra checked by hand. Nothing was run. |
| BLOCKED | Needs TradingView or the operator. |

## Stage plan

| Stage | Scope | Reports | Status |
|---|---|---|---|
| S1 | File verification, structural inventory, architecture | 1 (part), 10 (part) | **DONE** |
| S2 | Targeted independent verification: cost, news, levels, sessions, MTF, sizing, Kelly, calibration, alerts, scorecard | 3, 6, 8, 9 (part) | **DONE** |
| S3 | Machine variable register (all 9 files) plus validation of every checker's assumptions | 2, 16 | **DONE** |
| S4 | Engine-by-engine audit plus dependency map (raw data → DECISION → dashboard) | 4, 7 | **DONE** (lexical slice; per-engine detail in S8 report) |
| S5 | Indicator and structure formulas (ATR, EMA, VWAP, BB, pivots, BOS / CHoCH / MSS, EQH / EQL, FVG, OB, sweeps) | 3 | **DONE** |
| S6 | Strategy comparison (Treatment, OLDGATES, CHALLENGER, H2) against ledger evidence | 5 | **DONE** |
| S7 | Macro and intermarket; edge cases and stress | 9, 11 | **PARTIAL** (stress tests to design in S8) |
| S8 | Research-based improvements (cited), remediation roadmap, executive summary | 12, 13, 1 | **DONE**: `AUDIT_REPORT_v90.md` |

## S1: file verification and inventory (DONE)

All nine files match the operator's SHA-256 list (`sha256sum -c`, 9 / 9 OK). The working tree was clean at
`ff9536959`.

Structural counts, grepped from the raw code:

| File | Lines | `input` | `request.security` | `lookahead_on` / `_off` (code) | `var` | `table.new` | `alertcondition` / `alert()` | `strategy.*` orders |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Master | 5882 | 94 | 21 | 17 / 4 | 306 | 3 | 4 / 4 | 0 |
| Visuals | 2090 | 142 | 28 | 18 / 4 | 107 | 6 | 8 / 16 | 0 |
| Brief | 5634 | 113 | 26 | 22 / 4 | 351 | 2 | 0 / 1 | 0 |
| Diagnostics | 5656 | 103 | 23 | 18 / 4 | 366 | 3 | 0 / 0 | 0 |
| Strategy / OLDGATES / CHALLENGER | 5419 / 5419 / 5430 | 94 | 21 | 17 / 4 | 342 | 1 | 0 / 2 | 19 |
| Strategy_H2 | 374 | 4 | 3 | 3 / 0 | 13 | 1 | 0 / 1 | 19 |
| EdgeCases | 401 | 1 | 0 | 0 / 0 | 6 | 1 | 0 / 0 | 0 |

Master architecture, in source order (from its section headers):

1. Inputs and cost model (L303–527).
2. Core engine: EMA, VWAP, BB (L528).
3. Higher-timeframe stack, 5M–1D (L570–760).
4. Adaptive-ATR regime (L753).
5. Mean reversion (L769).
6. Session engine with DST (L870).
7. Macro and intermarket requests (L975–1260).
8. Weighted trend (L1391).
9. Dual structure, BOS / CHoCH / MSS, displacement (L1416–1606).
10. EQH / EQL, FVG, OB (L1607–1824).
11. Regime engine (L1855).
12. Liquidity pools, PDH / PDL, PWH / PWL, PMH / PML, CDH / CDL (L1971–2050).
13. Structure persistence (L2051), liquidity destination (L2113), MTF confluence (L2245), macro intelligence (L2273).
14. Statistical evidence engine (L2351), analogs (L2461).
15. Entry gates (L2496–2570), trade plan (L2603–2850), stats / calibration (L2850–4600).
16. Calibrated P and vetoes (L4572–4850).
17. Dashboard (L4955–5850), alerts (L5854–5882).

## S2: findings so far

Severity scale as in the mandate, section 20. All findings below are **proposed, not implemented**. The website (system
of record, A7) runs the same engine, so engine-level corrections there need a website amendment.

### B-01 · MEDIUM · Master position size leaves trading cost out of the risk per lot · CONFIRMED (EXECUTED-TRANSCRIBED)

- **Where:** Master `f_dashData2`, L5392–5410.
- **Code:** `_rawLots = _riskUSD / (tpDist * pointValue)`, where `tpDist = |tpEntry - tpSL|` (L2676).
- **Expected:** the F-002 comment in the same block says "intended risk as a CEILING". The loss at the stop includes
  spread, two-sided slippage and commission: `cost = 0.30 + 2 × 0.20 + 7 / 100 = 0.77` points at defaults (the same
  formula the Master uses for plan cost, L2812). Visuals already sizes as `(stop + ckCost) × pointValue`
  (Visuals L1745).

Worked example: $10,000 account, 1% risk (Kelly at or above the cap), 0.01 lot steps.

| Stop distance | Master lots | Loss at the stop | Overshoot of the $100 ceiling |
|---:|---:|---:|---:|
| 3.0 | 0.33 | $124.41 | +24.4% |
| 6.0 | 0.16 | $108.32 | +8.3% |
| 10.0 | 0.10 | $107.70 | +7.7% |

- **Impact:** realised risk runs 8–24% above the ceiling the dashboard states. The overshoot is larger on tight
  (5m) stops.
- **Why MEDIUM, not HIGH:** the overshoot is bounded (about 0.08–0.24% of equity per trade), and the Visuals risk box
  shows the size with cost included.
- **Proposed fix:** divide by `(tpDist + cost) × pointValue`. This is display-only (the twins trade 1 oz) and adds a
  few tokens, so it needs a measured token saving first (Master headroom under ~80).
- **Test:** an executed check that loss-at-stop ≤ intended risk for stops of 1–50 points.

### B-02 · MEDIUM · Two different position sizes for the same trade on the chart · CONFIRMED (READ)

| | Master (L349, L5337–5410) | Visuals (L1645–1746) |
|---|---|---|
| Account default | `accountSize` $10,000 | `rkEquity` $25,000 (operator, 2026-10-31) |
| Risk % | half-Kelly from the out-of-sample analog win rate (Wilson lower bound), capped at `riskPercent` 1%, × `regSizeMult` | `rkPct` 1% |
| Stop | the engine's plan stop | 1 × ATR(14) unless typed |
| Example: plan stop 6.0, Kelly ≥ 1% | 0.16 lots | 0.36 lots with stop typed (0.23 at a 10.0 stop) |

The Master's account size was never moved to the operator's $25,000.

- **Proposed fix:** set the Master's `accountSize` default to 25,000 (no token change), and state in the Visuals
  RISK row which stop it uses.
- **Test:** `inputs_check` asserts the two account defaults are equal.

### B-03 · MEDIUM · No news-time transaction cost, and news entry suppression is off by default · CONFIRMED (READ)

- The mandate says the design "includes elevated transaction costs around major news events, 3–5×". **No such
  multiplier exists in any of the nine files.** A grep for news × spread finds none. The cost tiers are session
  only: Master L971, Visuals L1710.
- `useNewsSuppress = false` and `newsSession = ""` by default (Master L370–371). So NFP, CPI and FOMC bars are not
  blocked from BUY / SELL.
- The engine's own news flag (L784–794) guesses NFP / CPI windows from the date (F-A74) and has **no FOMC window**:
  FOMC is 14:00 ET, which is 18:00 / 19:00 UTC, outside its 12:15–14:00 UTC window.
- Visuals' official calendar (v86) shades and alerts but does not feed the engine.
- **Impact:** the plan's cost-in-R (`_cR`, L2812) uses a 0.30 spread at the release minute. Example: a 6-point stop
  charges 0.128 R, while 3× spread plus 2× slippage would be about 0.30 R.
- **Proposed (operator decision; an engine change also needs a website amendment):**
  - (a) Display: Visuals' COST row × a news multiplier input during its dated events.
  - (b) Engine: use the dated calendar for `newsWindow`, plus a cost multiplier.
- **Test:** executed cost on the 38 dated events.

### B-04 · LOW · The session spread tiers do nothing at the default spread · CONFIRMED (READ, arithmetic)

- `max(0.18, 0.30) = max(0.22, 0.30) = max(0.30, 0.30) = 0.30`. At `spreadCost = 0.30`, killzone, NY and London all
  cost 0.30; only off-session differs (0.50).
- The P1-CAL-001 reordering has no effect unless the operator lowers `spreadCost` below 0.30.
- **Proposed:** document it in the tooltip, or treat the tiers as absolute values when broker data arrives (needs the
  broker spread, BLOCKED).

### B-05 · LOW–MEDIUM · Session definitions differ from common gold-session conventions · CONFIRMED (READ), definitional

- NY session and NY killzone start at **10:00 ET** (`nyOpen` 14 / 15 UTC, L917–921). The NY killzone is
  10:00–13:00 ET.
- US data releases at 08:30 ET fall inside "LONDON" (or LON-FIX), not NY. The common ICT NY killzone is
  07:00–10:00 ET.
- London opens at a fixed 07:00 UTC: one hour early in winter, which the code documents.
- `sessionQuality` (an entry gate ≥ 30) and `sessionConfMult` depend on these windows.
- **Not a math error:** DST is correct (below).
- **Proposed:** operator decision. Any change is an engine change (website amendment) and must not be chosen from
  results (§9).

### B-06 · MEDIUM · The strategy scorecard verdict uses $ per ounce, while the registered rule is on R · CONFIRMED (READ plus example)

- **Where:** Strategy, OLDGATES and CHALLENGER (identical) L5386–5405. The mean, t-interval and PF are computed on
  `strategy.closedtrades.profit` (1 oz).
- **Labels:** "Mean $ / position" is honest, but the verdict prints **"EDGE SHOWN"** when the $ interval > 0. The
  pre-registered rule (website) is on the mean **R**.
- **Example:** two positions, +$10 on $20 risk (+0.5 R) and −$2 on $1 risk (−2 R). The mean is +$4.00 but −0.75 R.
  With ATR-scaled stops the signs can differ.
- **Impact:** display only (A7: the website decides), but the wording claims the decision rule.
- **Proposed:** compute R per position (`profit / (|entry − stop| × qty)`), or rename the verdict "$ edge (not the
  registered rule)". Twins must change identically (hunk counts).

### B-07 · LOW · Misleading name · CONFIRMED (READ)

`tpDist` (Master L2676) is the **stop** distance, `|entry − SL|`. It is used correctly everywhere checked (sizing,
`_cR`, cost %), but the name invites a future error. Rename only with an identical-output check.

### C-01 · Checker note (not a defect)

- `deadcode.py` prints "0 dead" for the Brief, Strategy ×3 and Strategy_H2. These files still compute **55 / 62 / 1**
  values they do not display; the values are "wired through" a companion file (Diagnostics, or Visuals for H2).
- My independent lexical register (`v90_register.py`) finds 45 / 52 / 1 lexically unread, for example `wiPdhCont`,
  `oBosFail`, `confLabel`, and the dashboard inputs in the twins.
- This is the documented operator-accepted design. But **"0 dead" must be read as "0 dead outside the companion
  rule"**, not "every value in this file is used here".

### Verified in S2 (no defect)

| Item | Method | Result |
|---|---|---|
| Hashes | executed | 9 / 9 |
| NY 17:00 day boundary `crossedNYDay` (Master L603–622): PDH / PDL / PWH / PWL / CDH / CDL key off it | EXECUTED-TRANSCRIBED vs IANA `America/New_York`, 2019–2026, 1m / 5m / 15m / 1h / 4h steps, weekend closure modelled | 3,871,147 bar pairs, **0 mismatches** |
| US / EU DST trackers (L870–902) | EXECUTED-TRANSCRIBED vs IANA, every day 2015–2030 | 5,844 days, **0 mismatches**. Flips at 00:00 UTC on the DST Sunday, while gold is closed, so harmless. |
| HTF requests (L580–584, 975–1258, 1972) | READ | `[1]` + `lookahead_on` on higher timeframes gives the last completed bar, with no future data. Same-timeframe macro uses `[1]` + `lookahead_off` with gold on the same completed bar (macro_check). Lower-TF results are discarded by `htf*Available` (`<`, strict). |
| BUY / SELL `alertcondition` (L5858) | READ | `shouldBuy and not tqVeto and barstate.isconfirmed`. `tqVeto` holds the TQ floor, negative EV, calibration veto and risk lock (L4794–4848) = the engine's executed signal. All `alert()` calls use `freq_once_per_bar_close`. |
| Kelly (L5337–5363) | READ | f = (p·b − (1−p)) / b; p = Wilson 95% lower bound at the overlap-corrected effective N; b = average win / average loss (out of sample); half-Kelly, capped at `riskPercent`, haircut for skew / kurtosis. Correct formula. Its inputs rest on analog win rates whose skill is unproven (F-A78 family). |
| Regime size haircut | READ | Applied once per display path (L5392, L5615); not doubled |
| Plan expectancy (L2806–2813) | READ | E = P(win)·RR1 − P(loss) + E[timeout R] − cost / stop; grid slots 12–17 = timeout mark-to-market / N (L4310). Units consistent (R). |
| Platt-style fit (L4141–4200) | READ | Grouped-logit WLS with Berkson weights n·p(1−p); slope projected onto [0, 0.25]; intercept re-solved through the weighted centroid; ≥ 3 bins of ≥ 30. Uses resolved outcomes only (online, no look-ahead). It is fitted, but measured skill is nil out of sample (F-A78). |
| Scorecard t quantile (Cornish–Fisher, Strategy L5391) | executed vs the exact Student-t | Error −0.0027 at df 10, < 0.0001 at df ≥ 30. The claimed "< 0.003 for df ≥ 10" holds. |
| Strategy costs | READ | `commission_value = 0.385` $ / oz per fill = 0.77 round trip, the same as the cost model (0.30 + 0.40 + 0.07). `slippage = 0`, so slippage is not double counted. The scorecard reads net profit, so cost is not deducted twice. |
| EMA20 colour (Visuals L213, L289) | READ | `cFast = #FFFFFF`; EMA20 plotted in white |
| H2 pivots (H2 L126–140) | READ | `ta.pivothigh / low(5, 5)`: a level exists only 5 bars after the pivot; sweeps are checked on confirmed bars before the new pivot is assigned. No look-ahead. |

## S3: register (generated)

`python3 audit/tools/v90_register.py` writes `audit/v90_audit/register/<file>.csv`: every global symbol with line,
kind, reads, writes, how many other files declare it, and its definition.

| File | Symbols |
|---|---:|
| Master | 1,234 |
| Visuals | 702 |
| Brief | 1,275 |
| Diagnostics | 1,274 |
| Strategy / OLDGATES / CHALLENGER | 1,183–1,185 each |
| Strategy_H2 | 57 |
| EdgeCases | 38 |
| **Total** | **8,131** |

This is Report 2's machine part. The hand audit of the values the operator acts on continues in S4–S5 against
`audit/VALUE_TRACEABILITY.md`.

## S3: checker validation

### What each checker really tests

Read from each tool's code and docstring, then confirmed by the mutation run below.

| Class | Tools | What a PASS means | What it cannot see |
|---|---|---|---|
| **Static screens** | precheck, undeclared, order, pinelimits, sequence, deadcode | No identifier, order, scope or declared-limit errors of the classes they encode | Any wrong number; anything the TradingView compiler rejects for other reasons (three false-confidence episodes are on record) |
| **Executed Pine** (`pine_exec`) | formula_trace, decision_check, regime_check, expectancy_check, h2_trace, h2_age_check, v86_check (§1–8), v88_check, brief_trace, pine_web_parity, tf_check | The Pine lines, **as written**, give the reference's numbers on random and boundary inputs | Only the blocks each tool extracts. Pine built-ins (`ta.*`, `request.security`) are modelled, not run. Nothing is executed bar by bar on real data inside TradingView. |
| **Parity** | diag_parity, h2_parity, v88_check (§1), macro_check (A), inputs_check (consistency) | The copies of the engine, H2, MX and inputs are identical across files | Whether the shared code is right: a defect copied into every engine copy passes (see m13) |
| **Tripwires** (frozen text) | refactor_check, v86_check §9, edgecase_cites, value_map, moved_check | The file equals a frozen transform of an older commit, or its anchors still exist | Nothing about behaviour. They fail on **any** edit, and pass again once refreshed. |
| **Maths only** (re-typed) | race_model_check, formula_check | The mathematics is correct | Whether the Pine says the same: they re-type it, as their own docstrings state |
| **Screens that never fail** | bug_scan | Prints hit counts for a human to triage | **Exits 0 even with a look-ahead hit.** The seeded repaint `close` in a daily `lookahead_on` request was printed as `R1 L1119` with exit 0 (C-02). |

### C-02 · MEDIUM (process) · `bug_scan.py` is not a gate

- Its look-ahead (R1), alert (A1) and `timenow` (R4) screens print hits but the tool always exits 0.
- A checklist read as "exit 0 = pass" would pass a repaint defect. That is how I first ran it in this audit, before
  reading the counts.
- **Proposed:** exit 1 when R1 / A1 / R4 exceed a committed allowlist of triaged hits. Today that is Visuals A1 11
  and R4 3; all other files 0.

### Mutation test: do the checkers catch real defects?

`audit/tools/v90_mutation.py` seeds **one realistic defect** at a time into a scratch copy of the repository (never
the baseline) and runs 26 checkers. Each kill is classified as either **semantic** (a checker tested the behaviour) or
**tripwire-only** (a frozen-text anchor noticed the edit).

Results: **8 / 18 caught by a behavioural test** (2 of them only through `bug_scan`'s printed counts), 1 incidental, 8 tripwire-only, 1 missed (EMA20 colour). Full table: `AUDIT_REPORT_v90.md`, "Mutation results".

## S4: engines and dependency map

### What can change a BUY / SELL

`audit/tools/v90_slice.py` computes a lexical backward slice from `shouldBuy / shouldSell / tqVeto /
_confDirLabel`. It includes enclosing `if` / `for` conditions and the bodies of called functions. "Not in the slice"
**proves** no influence; "in the slice" only means it may influence.

The DECISION chain, read from the code (Master):

```text
DECISION (_confDirLabel, L4931; confirmed bars)
  = RISK LOCK | NO TRADE (tqVeto) | BUY (shouldBuy) | SELL | WARMUP | WAIT
shouldBuy (L2509–2512) = bullTrend (weighted trend score >= trendThreshold)
                         AND NOT htfBearScoreGate (>= 2 of the higher timeframes bearish)
                         AND recentBars (last 120 bars; see B-09)
                         AND sessionQuality >= 30
                         AND NOT inNewsWindow (OFF by default; see B-03)
                         AND NOT _ddBreach (OFF by default)
                         AND (bullStructActive OR displacementUp)
tqVeto (L4796, L4848)  = TradeQuality < effTqMin (55 ± regime / COT adjustments)
                         OR planExpectancy < 0
                         OR calibration veto (cal P < 0.50 once live; F-A78: no skill)
                         OR risk lock (3R daily loss / 4 signals / 3 losses in a row)
```

Per engine section: global writes that can reach the DECISION, out of all global writes in the section.

| Engine (Master section) | Reach | Cannot influence the DECISION (display / alert / companion only) |
|---|---:|---|
| Core EMA / VWAP / BB | 19 / 26 | RSI value, VIX, VWAP ±2σ bands and rejection |
| HTF trend stack | 63 / 65 | `htfFullLong / Short` (all-5 alignment) |
| Session engine | 29 / 31 | `sessionConfMult`, `sessionLabel` |
| Macro requests / rates / COT / OI / GC | 71 / 79, 83 / 93, 44 / 58 | 2s10s curve, DXY RSI, stability metrics, `macroStrengthConf`, GC / OI / COT **state labels**. GC confirm, OI conviction and COT crowding **do** reach. |
| Structure BOS / CHoCH / MSS | 60 / 66 | BOS **label** flags (drawing). BOS / CHoCH / MSS scores reach. |
| Displacement / structure bias | 16 / 26 | **RSI divergence** (all pivots-RSI values), structure age / type |
| EQH / EQL | 7 / 16 | climax volume, volume-by-hour |
| FVG / OB | 19 / 30, 10 / 10 | mitigation % and drawing objects |
| S/R (moved) | 0 / 10 | **SMT divergence**, gold / silver RSI at the last swing: display only |
| Regime engine | 20 / 32 | **CVD / volume delta, value area** |
| Liquidity pools | 20 / 22 | `ranEqH / ranEqL` |
| Structure persistence | 5 / 7 | peak / trough |
| Liquidity destination | 39 / 46 | `liqDestScore` (**the destination ranking itself**), its confidence, **liquidity sweeps** |
| MTF confluence | 8 / 12 | agreement tiers |
| **V27 bias-score / EI confidence block** (L2273–2350) | **0 / 46** | EI confidence, bull / bear bias scores, signal-agreement counts: **all display** |
| Statistical evidence (L2351) | 53 / 53 | — |
| Stats / calibration engine | 122 / 164 | schema / version stamps, display text |

**Interpretation for the operator.** Many prominent dashboard items never change a BUY / SELL:

- the EI confidence and bias scores;
- liquidity destination and sweeps;
- RSI divergence;
- SMT;
- CVD / value area;
- VIX;
- the 2s10s curve.

They are context, not inputs. This is not a defect in itself, and the code comments say so for most of them. It
matters because the dashboard can look strongly bullish on these items while the DECISION is WAIT, or the reverse.
Recorded as **B-14 (MEDIUM, presentation)**.

**Proposed:** mark decision-driving rows (for example with a "▸" marker) versus "context" rows, in Visuals or in the
Master's legend. This needs a token measurement for the Master.

### B-09 · MEDIUM · The Master's signals (and its risk lock) depend on how much history is loaded · CONFIRMED (READ)

- **Code:** `recentBars = bar_index > last_bar_index - recentBarsLen` (Master L563, default 120 bars) is an entry
  gate. The twins, Diagnostics and Brief override it with `backtestAllBars = true`; the Master does not.
- **Consequence 1:** on the Master's history, every signal older than 120 bars is WAIT ("OLD-BAR"). The history
  never shows what a trader saw live. This is mandate §11's "historical vs real-time divergence". It is by design,
  for clutter.
- **Consequence 2:** the **risk lock** (L4810–4848) counts only signals that passed `shouldBuy / shouldSell`, so it
  counts only the last 120 bars after any reload (chart reopen, timeframe or input change). The NY day lasts 23
  trading hours:

  | Chart | 120 bars covers | Same-day losses older than that |
  |---|---|---|
  | 15m | 30 h | none lost |
  | 5m | 10 h | forgotten after a reload |
  | 1m | 2 h | forgotten after a reload |

  On 5m and 1m, a DAYLOSS / MAXTRADES / LOSSSTREAK lock set earlier the same NY day can **lift after a reload**.
  A server-side alert created before the losses keeps its own state, so alerts and the chart can then disagree.
- **Proposed:** let the Master's risk tracker evaluate signals on every bar (`shouldBuy` without `recentBars`) while
  the markers keep the 120-bar limit. This needs a token measurement. Display only; no website change.
- **Test:** executed bar by bar on a synthetic 5m day with 3 early losses, then the history truncated.

## S5: formula findings

| ID | Severity | Item | Evidence |
|---|---|---|---|
| **B-08** | LOW–MEDIUM (statistical) | Evidence engine (Master L2351–2445; the same in every engine copy and the website port). `rawBull + rawBear` is normalised to exactly 100, so `rangeResidual = 100 − rawBull − rawBear` is **identically 0**, and its 0.70 weight in `rangeBlended` never acts. Before the stats engine warms up, `rangeScore ≤ 20`, so the "RANGE" bias (≥ 62) is reachable only through the history blend. The session and correlation-health "evidence" streams add **equal** amounts to the bull and bear sides: they carry no direction and only pull both scores toward 50. 2 of the "8 streams" are not directional evidence. | **EXECUTED-PINE:** the block run as written (`ta.sma` modelled), 20,000 random states: max \|rangeResidual\| 2.8e-14, max rangeScore 20.0, weights always sum to 1. Non-negativity for every regime strength k ∈ [−1, 1] follows by algebra (smallest: wMR = 0.05 − 0.05k ≥ 0). |
| B-10 | LOW (definitional) | CHoCH = first higher low after an LH / LL sequence. MSS = higher low plus higher high. Both are pivot-sequence definitions, not "close through the last lower high". They are confirmed `pivotLen` bars after the swing, then labelled at least 3 bars after the last pivot (`barSpaceOk`). The decaying score stays "active" for 5 bars: 15 × 0.85^k > 7.5 ⇔ k ≤ 4. BOS uses pre-update snapshots, so it cannot fire on a level price already exceeded (a pivot high exceeds the right-side bars' highs). | READ, with the algebra shown |
| B-11 | LOW | The "VWAP ±2σ" bands use a 20-bar stdev of `close − VWAP`. That measures how fast the gap changes, not dispersion around VWAP, so the band sits close to VWAP. `vwapRejectBull` (low ≤ lower band and close > VWAP) fires on **11.9%** of XAU 15m bars (8,327 bars, 2026-08-05 → 10-31, equal-weight VWAP because the feed has no volume). It feeds only the display-only EI agreement count. | Measured on the website's live `market-data` store (not the sealed research data) |
| B-12 | LOW (definitional) | `atrPercentile = ta.percentrank(adaptiveATR, 50)` ranks against the last 50 bars (12.5 h on 15m). The "HV / LV" tags and the 0.75 size haircut are relative to the last half-day, not to long-run volatility. | READ |
| B-13 | LOW | `liqSweepBull / Bear` (L2242) have no `barstate.isconfirmed`, so the live dashboard can show a sweep that is gone by the close. The alerts use bar close, so alerts are fine. | READ |
| B-15 | LOW | Pine strategy fills: `process_orders_on_close = true`, and same-bar stop / limit ties follow TradingView's broker-emulator bar-path assumption. The website uses stop-first. The Pine backtest can therefore be slightly optimistic against the system of record on tie bars. Display only (A7). | READ. TradingView docs, "Strategies → Broker emulator" |

**Verified (no defect):**

- adaptive ATR: ATR(21)↔ATR(7) blended by ADX strength, floored at 1 bp of price;
- EMA and BB definitions (`ta.stdev`, population);
- FVG: the 3-candle definition with a 0.3 ATR minimum, on confirmed bars;
- EQH / EQL tolerance (ATR × multiplier);
- BOS snapshot ordering;
- evidence weights: they sum to 1 under every regime modulation (executed);
- TIPS: auto-off while it equals the yield symbol (Master L1039), so no double count.

## S6: strategy comparison (evidence from the system of record's ledger)

The forward ledger (`ledger_stats.py`, branch `forward-ledger` @ `b8148d0`, 2026-10-18 → 10-30) holds closed
positions by arm. Registered timeframe 15m:

| Arm (Pine file) | Entry rule (diff vs Treatment, code) | 5m N / mean R | 15m N | 1h N / mean R | Evidence of edge |
|---|---|---|---:|---|---|
| Treatment (Strategy) | weighted trend score; not HTF-opposed; structure **state** or displacement | 8 / +0.94 (t-interval −1.17 … +3.04) | 1 | 3 / −0.16 | **None measurable.** N far below 50. |
| Control (OLDGATES) | adds HTF **alignment** + macro agreement + EI confidence + **mandatory RSI divergence**; momentary BOS | 1 / — | 0 | 0 | None. The conjunctive gates are nearly never all true. |
| Challenger | trend = close > EMA20 and EMA20 rising over 3 bars | 8 / +0.90 (−1.16 … +2.97) | 1 | 2 / +0.29 | None. On 5m it took almost the same trades as Treatment (sum +7.23 vs +7.50 R), so the A/B cannot separate them yet. |
| H2 (Strategy_H2) | sweep of a 5/5 pivot, back into the 100-bar value area, 2 of 3 HTF votes | 3 / −0.31 | 1 | 0 | None |

Ledger context (website-only arms the Pine shows):

- **H4** has the only decisive record, and it is **negative**: 5m N 511, mean −0.179 R (t-interval −0.253 … −0.105);
  1h N 49, −0.187 R.
- **H3:** 5m N 14, +0.55 R; the interval spans 0.

**Assessment (Report 5):** no Pine strategy has evidence of an edge in either direction; all are **"not yet
empirically verified"**.

- Complexity does not buy evidence. OLDGATES' extra gates mostly remove trades.
- Challenger's simpler trend rule behaves like Treatment so far.
- No component can be called useful or harmful from these samples. Any selection now would be tuning on noise (§9).

## S7: macro and edge cases (partial)

**Macro, verified:**

- Symbols: `TVC:DXY`, `TVC:US10Y`, `OANDA:XAGUSD`, `OANDA:EURUSD`, `SP:SPX`. TIPS is off by default.
- Each series is invalid after 2 unchanged bars (`MACRO_STALE_MAX = 2`, Master L1026), so stale data drops out
  rather than voting. SPX drops out outside US cash hours.
- GC has its own freshness check (≤ 3 chart bars, L1162) and a magnitude sanity check.
- Same-bar return pairing is checked by `macro_check`.
- The macro score feeds the DECISION only through the evidence score, so only through TQ and the calibration veto.

**Open:** directional assumptions are fixed signs (falling DXY or yield = bullish gold). Regime-dependent
correlation is only partly handled (correlation-health weighting).

**EdgeCases coverage:** unit-style maths cases (category boundaries, race ties, timeout cost, calibration bins,
shrinkage, Platt-fit guards, macro vote pool, race grid). **Not covered there:**

- NA macro;
- zero volume;
- price gaps and weekend bars;
- invalid or zero stop distance;
- zero or negative RR;
- rapid flips;
- insufficient history.

Some of these are covered elsewhere: regime_check (ATR floor), panel_check 9 / v86_check (NaN text), tf_check
(every timeframe, DST). The list of proposed tests is in Report 11 (S8).

## Blocked (needs the operator)

- TradingView compile of v86–v90. **Status: static audit passed; compilation unverified; live-chart behaviour
  unverified.**
- EdgeCases chart run (F-A75).
- Broker spread / commission / contract size / MT5 offset (B-03, B-04).
- An export of `mP` history, to measure F-A78 on the Pine engine itself.

## Next: operator review of the roadmap (Report 13). Nothing is implemented without approval.

Continue from here. Do not modify the baseline.
