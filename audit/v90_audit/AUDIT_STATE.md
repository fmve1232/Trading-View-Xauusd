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
| S2 | Targeted independent verification: cost, news, levels, sessions, MTF, sizing, Kelly, calibration, alerts, scorecard | 3, 6, 8, 9 (part) | **IN PROGRESS** (findings below) |
| S3 | Machine variable register (all 9 files) plus validation of every checker's assumptions | 2, 16 | Register generated; checker review open |
| S4 | Engine-by-engine audit plus dependency map (raw data → DECISION → dashboard) | 4, 7 | Open |
| S5 | Indicator and structure formulas (ATR, EMA, VWAP, BB, pivots, BOS / CHoCH / MSS, EQH / EQL, FVG, OB, sweeps) | 3 | Open |
| S6 | Strategy comparison (Treatment, OLDGATES, CHALLENGER, H2) against ledger evidence | 5 | Open |
| S7 | Macro and intermarket; edge cases and stress | 9, 11 | Open |
| S8 | Research-based improvements (cited), remediation roadmap, executive summary | 12, 13, 1 | Open |

## S1: file verification and inventory (DONE)

All nine files match the operator's SHA-256 list (`sha256sum -c`, 9 / 9 OK). The working tree was clean at
`ff9536959`.

Structural counts, grepped from the raw code:

| File | Lines | `input` | `request.security` | `lookahead_on` | `var` | `table.new` | `alertcondition` / `alert()` | `strategy.*` orders |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Master | 5882 | 94 | 21 | 1 line + 18 in-call | 306 | 3 | 4 / 4 | 0 |
| Visuals | 2090 | 142 | 28 | 6 | 107 | 6 | 8 / 16 | 0 |
| Brief | 5634 | 113 | 26 | — | 351 | 2 | 0 / 1 | 0 |
| Diagnostics | 5656 | 103 | 23 | — | 366 | 3 | 0 / 0 | 0 |
| Strategy / OLDGATES / CHALLENGER | 5419 / 5419 / 5430 | 94 | 21 | — | 342 | 1 | 0 / 2 | 19 |
| Strategy_H2 | 374 | 4 | 3 | — | 13 | 1 | 0 / 1 | 19 |
| EdgeCases | 401 | 1 | 0 | — | 6 | 1 | 0 / 0 | 0 |

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

## Blocked (needs the operator)

- TradingView compile of v86–v90. **Status: static audit passed; compilation unverified; live-chart behaviour
  unverified.**
- EdgeCases chart run (F-A75).
- Broker spread / commission / contract size / MT5 offset (B-03, B-04).
- An export of `mP` history, to measure F-A78 on the Pine engine itself.

## Next: S3 (checker validation), then S4

Continue from here. Do not modify the baseline.
