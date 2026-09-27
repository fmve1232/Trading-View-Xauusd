# Traceability & Wiring Audit — Findings

**Artefacts:** the five files in `artefacts/`, hashes per `audit/MANIFEST.sha256` (verified `OK` before and after this audit).
**Question asked:** end-to-end traceability — is every feature wired, is anything dead, are the engines aligned and calibrated.
**Method:** mechanical symbol-level traceability over **100% of symbols in all five files** (declarations, assignments, reads, function params, scope-aware occurrence counting), followed by hand-verification of every hit and manual trace of the decision path and each named engine.

**Coverage statement, stated honestly.** Every symbol in all 16,207 lines was mechanically traced. The decision path, the SL/TP construction, the probability/calibration chain and the liquidity / volume-profile / trend engines were then read and verified by hand. I did *not* give equal manual attention to all 16,207 lines, and I do not claim to have. Where a finding is mechanical, the evidence is reproducible; where it is judgement, it is labelled.

**Nothing was changed.** No tuning, no fixes — per `AUDIT_PROMPT.md` §9.

> ## ⚠ CORRECTION AND FIX STATUS (applied after this report was first written)
>
> **F-A01's severity rationale was wrong and is corrected below.** The volume-profile
> block is guarded by `barstate.islast` (v1 L1914 / v2 L1911), so it computes **only on
> the chart's final bar** — in the Master as well. My original claim that the Master
> "picks a stop from 7 candidates and a target from 10" while the arms pick from 6 and 8
> is true **only on the last bar**; on every historical bar the Master's VP candidates
> were `na` too. The A/B's absolute PF and win-rate figures are therefore **not**
> distorted the way I stated. The real defect that guard exposes is different, is inside
> the Master, and is recorded as **F-A07** below.
>
> **Applied:** F-A01/F-A03/F-A04/F-A06 (v2), F-A07 (v3), **F-A02 + F-A05 (v4)**.
> All seven are now applied; F-A08 … F-A20 followed, status per row in the Summary
> table below. **F-A02's wiring is not a validation** — see the
> revised Question B below.
> Build v2 hashes are in `audit/MANIFEST.sha256`; v1→v2 line mapping in
> `audit/LINE_MAP_v2.md`.

---

## Summary

| ID | Severity | Class | Finding |
|---|---|---|---|
| F-A01 | MEDIUM *(was CRITICAL — see correction)* | `BUG` | Volume-profile engine absent from both arms while still consumed by the SL/TP candidate arrays — **FIXED** (parity port) |
| F-A02 | **CRITICAL** | `STAT` | Calibration engine display-only; no calibrated probability gated any trade — **WIRED in v4**; underlying validity still unestablished |
| F-A03 | HIGH | `BUG` | The Decision Log explains failures against a gate set the engine no longer uses — **FIXED** |
| F-A04 | HIGH | `BUG` | OB/FVG volume-quality values computed every bar, consumed by nothing — **FIXED** (removed) |
| F-A05 | MEDIUM | `STAT` | Weighted evidence composite (`bullScore`) did not gate entry — **WIRED in v4** through the same calibrated channel |
| F-A06 | LOW | `PRES` | Stale line citation for the BOS complement — **FIXED** |
| F-A07 | **HIGH** | `STAT` | *(new)* Volume profile is last-bar-only, so the live plan can use levels no historical bar could — **FIXED** (option 3, marked basis) |
| F-A08 | **HIGH** | `BUG` | *(new)* Visuals drew order blocks on a 2.5× looser threshold than the Master while claiming parity — **FIXED** (engine ported) |
| F-A15 | **P0** | `BUG`+`STAT` | Platt map fitted on `bullScore` was evaluated on `bearScore`; since F-A02 this **gated entries** — **FIXED v12** |
| F-A14 | P2 | `PRES` | F-037's suppression incomplete: `wrCIStr` still rendered a ±x% interval over the rolling population (`WR 74%+/-4%`) — **FIXED v13** |
| F-A16 | P2 | `STAT` | Short probability was the complement of a bull fit whose denominator includes timeouts — optimistic by the timeout rate — **FIXED v14** (bear fit + conditional gate) |
| F-A17 | **P1** | `BUG` | Plan touch probabilities read a 1.5×ATR-unit histogram with plan-stop-unit distances; SL always the 1-unit rate — **FIXED v14** |
| F-A18 | P2 | `BUG` | Regime adjustment could push the calibrated probability to 1.175 (short complement negative) — **FIXED v14** (clamp) |
| F-A19 | **P0** | `STAT` | `planExpectancy` (a difference of marginal touch rates) vetoed trades as if it were an expectancy — **FIXED v14** (race expectancy) |
| F-A20 | MEDIUM | `PRES` | EdgeCases C3/C5 asserted pre-F-A10 behaviour and passed, because they tested the harness's own model — **FIXED v14** |
| F-A21 | MEDIUM | `BUG` | Dead and broken code: a what-if scenario engine that computed factors and never used them, unread/self-only accumulators, write-only buffers, 394 lines of dashboard remnants per strategy arm, and 2 inputs orphaned by v15 — **FIXED v16** |
| F-A22 | **P1** | `STAT` | Cornish-Fisher applied FORWARD to an observed z-score, counting fat tails twice (99th pct: 6.64 vs a true 2.33); feeds `mrComposite` and an analog feature — **FIXED v16** (Newton inverse) |
| F-A23 | P2 | `STAT` | Kelly used the bull win rate for shorts, and 1−p as the loss probability, so timeouts counted as losses — **FIXED v16** (f* = (pb−q)/(b(p+q))) |
| F-A24 | P2 | `STAT` | Platt WLS weighted each bin by n, not the inverse variance of its logit, n·p(1−p) — **FIXED v16** (Berkson) |
| F-A25 | P3 | `STAT` | Brier decomposition mixed smoothed frequencies with the raw base rate over different bin sets, so the identity failed — **FIXED v16** |
| F-A27 | MEDIUM | `PRES` | EdgeCases A3/A6 asserted the pre-F-021 rounded categories and FAILED on the chart (engine correct) — **FIXED v20** |
| F-A28 | P2 | `PRES` | Dashboard "WR" for a bearish bias was 1 − P(bull) = "bear OR timeout" (showed 80% on a ~20% chart) — **FIXED v20** (bear rate) |
| F-A29 | **P0** | `BUG` | Strategy entries required `recentBars` (last 120 bars): the backtest could only trade the final ~5 days, so it took 0 trades — **FIXED v20** (switchable, default all bars) |
| F-A30 | **P0** | `BUG` | OB, FVG, displacement, SMT and climax DETECTION were gated by display toggles defaulting OFF: the decision ignored the zones Visuals draws, and half the entry trigger was disabled — **FIXED v21** (engine inputs, default ON) |
| F-A31 | P1 | `PRES` | BUY/SELL alertconditions not confirmed-bar gated; alert text had no MT5 plan; no alert on decision change, SL/TP1 or risk lock — **FIXED v21** |
| F-A32 | **P0** | `BUG` | *(compiler-reported)* Master v23: `too many tokens: 100820` (limit 100,256); the lexical estimator's ratio had drifted 2.466 → 2.515 — **FIXED v24** (auction layer moved to Diagnostics) |
| F-A33 | P3 | `NUM` | *(compiler-reported)* Diagnostics: `ta.correlation` in a ternary skipped bars in its window; `_v` shadowed a global — **FIXED v24** |
| F-A38 | P2 | `NUM` | *(first live data, web engine)* The Cornish-Fisher Newton inverse ran away where the cubic has no inverse (K < 0, \|z\| > ~3): up to 1e213 on 147 of ~3,500 live 5M bars, pinning `mrComposite` at ±100. The v16 comment claimed q' > 0 over the clamped region — false — **FIXED v32** (inverse kept only where it solves q(w) = z) |
| F-A37 | P3 | `PRES` | *(first executed harness result)* EdgeCases I7 asserted IEEE semantics ("`== 0` lets 1e-12 through"); Pine returned false — its float `==` is tolerant. The premise was never executed — **CORRECTED v29**; chart run of v29: I7 and I9 PASS (`1e-12 == 0.0` is true), I10 `1e-12 > 0.0` FALSE. **Resolved on the chart (v30, 2026-09-27): ALL PASS 99.** `1e-12 * 1e12` = 1, so the literal keeps its value and Pine's `==` AND `>` are tolerance-based. `safeDiv`'s `abs(b) > 1e-10` needs no change — **CLOSED** |
| F-A36 | **P1** | `STAT` | *(operator report)* DECISION "mostly WAIT" while price moved $30–50: the entry chain passes 1.5% of bars (152 / 10,269 on 1H); the trigger stage alone removes 86% of eligible bars — **MEASURED v27** (missed-move audit), **not tuned** (§9) |
| F-A35 | P2 | `PRES` | *(sequence audit)* `biasLabel` and the WAIT reason were computed from the evidence-stage scores but shown beside the final scores (label could contradict the numbers; alert text too) — **FIXED v26** |
| F-A34 | **P1** | `STAT` | *(first chart data)* raw score buckets predict 21→54% but observe 18–24%: no resolution on this history; Treatment PF 0.989 over 90 trades — **OPEN, not fixable by code** (needs a frozen holdout, §9) |
| F-A26 | P3 | `NUM` | t-quantile Fisher expansion evaluated one term at an already-corrected z (numerically ~1e-5) — **FIXED v16** |
| F-A13 | **CRITICAL** | `BUG` | *(compiler-reported)* `Undeclared identifier "OUTCOME_N"` — the Master and both twins never compiled — **FIXED** |
| F-A12 | **HIGH** | `BUG` | *(new)* Entry comment promised `P<pct>` per trade for the calibration test but never emitted it — **FIXED before the baseline run** |
| F-A11 | **HIGH** | `PRES` | *(new, from a mobile screenshot)* "Mobile Layout" changed only the font size — the 9-column desktop table was still rendered on phones — **FIXED** (real column reduction) |
| F-A10 | **HIGH** | `STAT` | The D-001 timeout-cost fix did not bite, **and the existing cost subtraction was in the wrong units** — **FIXED in v7** (R-unit conversion + timeout term) |
| F-A09 | MEDIUM | `PRES` | *(new)* EdgeCases' Master line citations stale (§4.5) — **FIXED** (re-derived) |

**Verified clean:** 95/95 inputs consumed (zero orphans); treatment-arm entry gates byte-identical to the Master; `EdgeCases` and `Visuals` carry zero unread symbols; plan direction cannot contradict signal direction; three flagged symbols confirmed *intentionally* dormant.

---

## F-A01 — Volume profile is inert in both backtest arms `CRITICAL` `BUG`

**Where.** `Master.pine` L1904–1956 vs `Strategy.pine` L1857–1861 and `Strategy_OLDGATES.pine` (identical).

**Evidence.**

| | Master | Strategy | OLDGATES |
|---|---:|---:|---:|
| `vpBuckets` / `bucketSize` references | 12 | **0** | **0** |
| `vpocPrice :=` assignments | 1 (L1935) | **0** | **0** |
| `vahPrice` / `valPrice` assignments | 2 (L1952–1953) | **0** | **0** |

In the Master the profile is built (L1918–1935: bucket clear, price seeding, volume accumulation, POC selection) and the value area is walked out at L1939–1953. In **both** strategy arms `vpocPrice`, `vahPrice`, `valPrice` are declared `var float … = na` and **never assigned** — the entire computation block is absent.

Both arms nevertheless still *consume* them:
- `Strategy.pine` L2485 — `_slC`, the **stop-loss** candidate array, includes `valPrice` (long) / `vahPrice` (short).
- `Strategy.pine` L2530 — `_tpLvls`, the **take-profit** candidate array, includes `vpocPrice` and `vahPrice`/`valPrice`.

**Why it is silent.** The consumer loop guards with `if not na(_lv)` (`Master.pine` L2623). A permanently-`na` candidate is skipped without warning. Nothing errors; the arrays just quietly shrink.

**Failure scenario.** On any bar where the live Master would place a stop at the value-area low, the backtest cannot: `"VAL"` is unreachable as a `tpSLBasis`, and `"VPOC"`/`"VAH"` are unreachable as TP bases. The Master chooses a stop from 7 candidates and a target from 10; both arms choose from 6 and 8. Stops and targets therefore land at systematically different prices, which changes every R-multiple, every win/loss classification, and every resulting PF and win-rate figure.

**Consequence for the A/B.** Both arms are affected **identically**, so the *comparison between arms* remains internally consistent and still isolates the gate change. But neither arm reproduces the Master's trade plan, so the **absolute** PF and win-rate numbers from either arm do not describe the live file's behaviour. Read the A/B as a relative gate experiment only.

---

## F-A02 — The calibration engine is display-only `CRITICAL` `STAT`

**The chain, traced end to end in `Master.pine`:**

```
calibration bins (c0..c4)        L3754, L3757
  -> WLS Platt fit               L4035-4037   (_pfVr > 1e-6 guard, slope from weighted least squares)
  -> clamped + stored            L4039-4040   (gCalFit[0] slope, gCalFit[1] intercept)
  -> read back                   L4383-4385   (_pfK2, _pfB2)   <-- the ONLY reads of gCalFit
  -> sigmoid                     L4386        (_calP)
  -> clamped [0.05, 0.95]        L4387
  -> _calibratedProb             L4394, L4402 (regime adjustment)
  -> calProbStr                  L4403        ("mP=NN%")
  -> table cell                  L5308        <-- TERMINAL
```

`_calibratedProb` has no consumer other than `calProbStr`; `calProbStr` has no consumer other than the dashboard cell at L5308. Verified by exhaustive occurrence search: `gCalFit` appears at 5 lines total, `_calibratedProb` at 7, `calProbStr` at 4.

**What actually gates a trade.** `Master.pine` L4554:

```pine
bool tqVeto = (effTqMinCot > 0 and tradeQuality < effTqMinCot)
              or (not na(planExpectancy) and planExpectancy < 0.0)
```

Neither term is calibrated:

- **`tradeQuality`** (L4472) is `_tqSum / _tqW` — a weighted average of hand-set heuristic components: zone 0.10, macro 0.15, session 0.08–0.12, regime 0.09, history 0–0.10, timing 0.05, forecast 0.10 (L4432–4471). The weights are literal constants, not fitted.
- **`planExpectancy`** (L2747) is `pTP1/100 - pSLhit/100` — the difference of two **marginal excursion frequencies** over the same population, per `AUDIT_PROMPT.md` §4.1. It is not an expected value.

**Failure scenario.** The Platt fit could be perfectly calibrated, badly calibrated, or rejected outright (negative slope, L4038's `if _pfK > 0`), and **not one trade would change**. The Brier decomposition (L4041–4045), the credible intervals (L2790–2795), the calibration grade — all are observability. The system's actual selectivity is an uncalibrated heuristic average plus a sign test on a quantity that is not an expectancy.

**Direct answer to "are the engines calibrated".** The calibration machinery is real and, so far as this audit can tell without executing it, correctly constructed. It is **not connected to the decision**. Wiring it would change trading behaviour and is a decision for the operator, not an audit action — see *Recommendations*.

---

## F-A03 — The Decision Log explains against the wrong gate set `HIGH` `BUG`

**The engine's actual gate** — `Master.pine` L2544:

```pine
bool buyPreFilters = bullTrend and not htfBearScoreGate and recentBars
                     and sessionQuality >= 30 and not inNewsWindow and not _ddBreach
```

**What the Decision Log reports** — `Master.pine` L2568–2578, scored out of **7**:

`bullTrend`, `htfBullScoreGate`, `macroBull`, `regimeConfHigh`, `bullRsiDiv`, `recentBars`, `sessionQuality >= 30`

Three of those (`macroBull`, `regimeConfHigh`, `bullRsiDiv`) are **not in the gate at all**. A fourth is inverted: the log tests `htfBullScoreGate`, the gate tests `not htfBearScoreGate` — different conditions, not complements (`htfAlignmentLong >= 2` vs `htfAlignmentShort >= 2`, L702–703; both can be false simultaneously).

That 7-filter set is exactly the **control arm's** pre-filter (`Strategy_OLDGATES.pine` L2426). The Master's explainability surface is wired to the pre-Q5.5 gate configuration.

**Reaches the screen:** `_buyLog` (L2578) → `decisionLog` (L2592) → dashboard cell (L5334).

**Failure scenario.** The engine declines to trade because `htfBearScoreGate` is true. The log shows `▲6/7 [✗Macro]`, blaming a filter that has no bearing on the decision, while never mentioning the condition that actually blocked it. Operator diagnosis is misdirected on every such bar — and this is the surface built specifically to answer "why no trade".

---

## F-A04 — OB/FVG volume-quality computed, consumed by nothing `HIGH` `BUG`

`obBullVolPct` (L1663, assigned L1698/L1726), `obBearVolPct` (L1664, assigned L1686/L1712), `fvgVolPctAtDetect` (L1625, assigned L1644) each have **zero reads**.

**Why there is no consumer.** `Master.pine` contains **0 `label.new` calls** (exhaustive count). The zone labels these values were computed for were removed with the drawing layer under Q5.4-CORE (L13–18).

**The comment is wrong.** L246 still asserts `obBull/BearVolPct→OB labels; fvgVolPctAtDetect→FVG label`. Two lines above, L243–244 correctly records that a *different* set of transfer vars was removed because "their dashboard consumers no longer existed; this comment claimed otherwise." The same correction was never applied to L246.

**The replacement does not carry the data.** `Visuals.pine` now draws these labels — L370 (`"FVG"`), L411 (`"OB▲"`), L417 (`"OB▼"`) — as plain text with no volume term, and `Visuals` has no access to the Master's `volPercentile` (L1616). So the volume-quality read on a zone exists in **neither** file's output while still costing computation every bar in the Master.

---

## F-A05 — The weighted evidence composite does not gate entry `MEDIUM` `STAT`

`bullScore` (`Master.pine` L2431–2458, then re-normalised L4345–4350) is where the evidence engines converge — L2406:

```pine
rawBullScore = evTrendBull*wTrend + evStructBull*wStruct + evFlowBull*wFlow
             + evMacroBull*wMacro + evLiqBull*wLiq + ...
```

That includes the **liquidity** engine (`evLiqBull`, L2367, fed by the PDH/PDL/PWH/PWL/PMH/EQH pool scorer at L2135–2176).

`bullScore` does **not** appear in `shouldBuy`/`shouldSell` (L2544–2549) or in `tqVeto` (L4554). Its consumers are: `biasLabel` (display), `hPred` (calibration record, L2958/L4363), the forecast blend (L4273–4350), `_calibratedProb` (→ display, F-A02), auction state (L4510), `_bullPct` (display), and `_bullSide` (L2564).

The entry decision is a conjunction of boolean state flags only — `bullTrend` (EMA/ADX/volume score ≥ threshold, L1369–1390), `htfBearScoreGate` (HTF alignment count, L703), session, news, drawdown, and a structure/displacement event.

**Judgement, not defect.** This is defensible design: score gates opportunity-starve, which L2556–2561 says was the explicit reason for the Q5.8 change. But it means liquidity and macro evidence influence *direction and presentation*, not *whether to enter*. Anyone reasoning about "the liquidity engine gating trades" is reasoning about a path that does not exist.

**Verified non-issue:** `_bullSide` (L2564) sits inside `if not shouldBuy and not shouldSell`, so it is diagnostic-only. The plan's direction **cannot** contradict the signal's direction.

---

## F-A06 — Stale complement citation `LOW` `PRES`

`Master.pine` L4723 states `oBosFail` and `oBosCont` "sum to 100 by construction **at L3545**". L3543–3548 is the analog-skip guard for missing lookbacks — unrelated code. The actual construction is **L4096** (`_cBosFail := 100 - _cBosCont`). The claim itself is true; the pointer is wrong. Same failure class as `AUDIT_PROMPT.md` §4.5.

---

## F-A07 — Volume profile is last-bar-only `HIGH` `STAT` *(new; FIXED in v3, option 3)*

**Where.** `Master.pine` v2 L1911 (v1 L1914):

```pine
if barstate.islast and barstate.isconfirmed and not perfMode
```

**What it means.** `vpocPrice`, `vahPrice` and `valPrice` are assigned **only inside this
guard**, and `barstate.islast` is true only on the chart's final bar. On every historical
bar they are `na`. They are nonetheless consumed on every bar by `_slC` (stop candidates)
and `_tpLvls` (target candidates), whose loops skip `na` silently.

**Failure scenario.** On the live bar the plan may select a stop at the value-area low or
a target at the VPOC — `tpSLBasis` reads `"VAL"`, a TP basis reads `"VPOC"`. No historical
bar could ever have produced those bases, because the values did not exist then. **The
live trade plan is therefore drawn from a candidate set that no backtest bar used**, which
is precisely the property a backtest exists to rule out. It is a live-vs-history asymmetry
*inside the Master* — not, as F-A01 originally claimed, a Master-vs-arms asymmetry.

**Why it was not fixed.** The obvious change — drop `barstate.islast`, keep the existing
`vpRefresh % 5` throttle — makes a 100-iteration inner loop run every fifth confirmed bar
across all history. On a 5,461-line script with **no measured compile or runtime baseline**
(`AUDIT_PROMPT.md` §8.1) that is a blind performance change, and `perfMode`/`barstate.islast`
exist specifically to avoid timeouts. Making it would be guessing.

**Options, for the operator to choose:**

1. **Measure first, then unguard.** Establish the runtime baseline (§8.1), then change the
   guard to `barstate.isconfirmed and not perfMode` and re-measure. Highest fidelity,
   needs the baseline that does not yet exist.
2. **Exclude VP from the plan.** Drop `vpocPrice`/`vahPrice`/`valPrice` from `_slC` and
   `_tpLvls`. Live then matches history exactly, at the cost of the feature.
3. **Mark it.** Keep as-is but suffix the basis string (e.g. `"VAL*"`) when the level came
   from a last-bar-only source, so the plan is honest about it.

**RESOLVED in v3 by option 3.** Every plan basis whose level can only exist at the live
edge now carries a trailing `°`: `VAL°`/`VAH°` in the stop-candidate names and
`POC°`/`VAH°`/`VAL°` in the target-candidate names, applied identically in all three
files. Marker placement was verified **positionally**, not by string match: in each of
the four branches (SL long/short, TP long/short) every `°` name maps to a VP-sourced
candidate and every VP-sourced candidate has a `°` name.

The marker is a literal inside the existing name arrays, so it costs **zero runtime
tokens** — which matters on a file near the compile ceiling. It is distinct from `*`
(a stop clamped into the R-unit band); both can appear, e.g. `VAL°*`.

Verified safe: the basis strings are display-only — no equality or substring test is
performed against them anywhere in any of the three files, so lengthening the literals
cannot change behaviour.

**This marks the asymmetry; it does not remove it.** The live plan can still select a
level no historical bar could produce — it now says so. Option 1 (measure, then unguard)
remains the correct structural fix if you ever get a runtime baseline.

---

## F-A08 — Visuals drew order blocks the engine would never recognise `HIGH` `BUG` *(FIXED in v5)*

**Where.** `Visuals.pine` OB block vs `Master.pine` L1524–1527, L1686–1700.

| | Master | Visuals (before) |
|---|---|---|
| Threshold | `adaptiveATR × dispMult`, **dispMult default 2.5** | `atr14 × obDispATR`, **default 1.0** |
| Hysteresis | 2.5× enter / 1.5× hold, latched | none |
| Trigger | `dispOnsetUp` — the **onset edge** | `dispUp` — true every bar of the run |
| Extra filter | none | `close[1] < open[1]` |
| ATR source | `adaptiveATR` | `ta.atr(14)` |

The block's own comment claimed *"Master logic mirrored"*. It was not mirrored.

**Failure scenario.** At default settings `showAdaptiveATR` is OFF and `atrLen` is 14, so
`adaptiveATR` collapses to `ta.atr(14)` and the ATR sources agree — meaning the entire gap
was the **2.5× multiplier**. Any candle with a body between 1.0 and 2.5 ATR (plus the
shared direction/body%/volume terms) was drawn as an order block on the chart while the
Master's engine did not register displacement at all. Because `dispUp` is not edge-gated,
a sustained displacement also pushed a **fresh box every bar** of the run.

**Fixed** by porting the Master's displacement engine verbatim — adaptive-ATR regime blend,
the five displacement terms, the hysteresis latch, and the `dispOnsetUp`/`dispOnsetDown`
edge the Master's OB detector actually triggers on. `obDispATR` default moved 1.0 → 2.5 to
match `dispMult`, and the local `close[1] < open[1]` filter removed (the Master takes the
previous bar regardless of its direction).

**Residual, documented in the file:** the Master keeps ONE active OB per side with a
mitigation lifecycle and a reversal-OB path; Visuals keeps the last N boxes and has
neither. **Detection now matches; retention does not.**

---

## F-A09 — EdgeCases' Master citations were stale `MEDIUM` `PRES` *(FIXED in v5)*

This is §4.5 of `AUDIT_PROMPT.md`, and it was the one finding never actioned. All ten
citations have been mechanically re-derived against the current Master and a provenance
banner added stating they must be re-derived whenever the Master changes.

The harness is now re-anchored: a reader can follow any `chk()` back to live Master code.

---

## F-A10 — timeout cost discarded, and cost subtracted in the wrong units `HIGH` `STAT` *(FIXED in v7)*

Found by the expression-drift pass that §4.5 asks for — checking that EdgeCases'
transcribed expressions still match the Master, not merely that the line numbers do.

**The Master's claim.** The D-001 note states: *"a timed-out trade is still ENTERED and
EXITED and still pays spread + commission, but oc == 0 was charged nothing… **Cost now
applies to all three outcome codes.**"*

**What the code does.** `frAdj = fr - _costATR` does run for every analog. But for
`oc == 0` the result is then **discarded**:

- `absFrAdj` is read only inside the `if oc == 1` / `else if oc == -1` branches.
- `_pnlPct` is `0.0` on the timeout branch.
- `wt` and `mt` **do** count timeouts (there is an explicit `else if oc == 0` branch
  incrementing both).

So `_cEvVal = wr*avgW − lr*avgL`, with timeouts in the **denominator** contributing
**zero to the numerator** — instead of the round trip they actually paid.

**Failure scenario.** In chop, compression or low-ADX regimes — exactly where timeouts
cluster and where a negative-expectancy read should bind hardest — analog EV is
optimistic by the full transaction cost of every timed-out analog. The displayed EV is
biased upward precisely where it most needs to be pessimistic. **This is the original
D-001 defect, still live**, with a comment asserting it was fixed.

**Severity is bounded by wiring, not by correctness.** `oEvVal`/`oEvLabel` are
**display-only** — consumed once for the dashboard EV cell. The gating expectancy is
`planExpectancy`, a different quantity (§4.1). Nothing is gated on this.

### A second, larger defect found while fixing this

Implementing the R-unit conversion surfaced that **the existing cost subtraction was
already mis-united**. `fr = array.get(hRet, i)`, and Q7.0 redefined `hRet` as **realised
R**. But `_costATR` divided cost by `adaptiveATR`, giving **ATR units**. So
`frAdj = fr - _costATR` subtracted an ATR-unit quantity from an R-unit one — wrong
whenever the SL multiple is not 1.0, and `regSLMult` defaults to **1.5**. Every
cost-adjusted win and loss was mis-scaled by that factor, not only the timeouts.

### Fixed in v7, in four parts

1. **Units.** Cost is now divided by the analog's own R unit — the risk distance in points
   it was normalised by — putting `_costR` on the same scale as `fr`, `avgW` and `avgL`.
   That R unit (`_oR`) is local to the outcome-recording loop, so it is now persisted
   per analog in a new `hRUnit` history array and read at the expectancy site.
2. **The timeout is charged.** A new accumulator sums each timed-out analog's *signed*
   cost-adjusted realised R. Signed, not magnitude: a timeout can end either side of
   entry, and forcing a magnitude would fabricate a loss. `mr_`/`wr_` already carried the
   timeout rate, so only the sum was missing.
3. **The equity curve too.** `_pnlPct`'s timeout branch was `0.0`, reproducing the same
   defect in `_cumEq`/`_maxDD`. It now contributes like any other outcome. **This feeds
   `oMaxDD` → `_ddForBreaker`, so it can move the drawdown breaker when `useDDBreaker` is
   ON — it defaults OFF.**
4. **EV.** `_cEvVal = (wr × avgW) − (lr × avgL) + (tr × avgT)`. Added rather than
   subtracted because `avgT` carries its own sign, unlike `avgW`/`avgL` which are
   magnitudes with the sign written into the formula. The three terms now partition every
   analog, so EV is a true expected R per matched state.

Verified that `st` and `mr_` see the same population — same loop iteration, same nesting,
no intervening `continue` or `_isOos` guard — so `avgT = st / mr_` is sound.

**Expect analog EV to fall**, most in chop, compression and low-ADX regimes where timeouts
cluster. That is the correction working, not a regression.

---

## F-A11 — "Mobile Layout" was a font-size toggle, not a layout `HIGH` `PRES` *(FIXED)*

**Found from a mobile screenshot of the live dashboard**, then confirmed in code.

**What the screenshot showed.** Every cell overflowing into its neighbour, both edges
clipped off-screen: `4406.46` rendered as `406.46`, `CHoCH— MH4510/PDL4` running into
`V 4373.17` running into `(Y≈ R33 10Y`, and the DECISION column truncated mid-word.

**What the code did.**

- `_respCols := 9` and `_respRows := 4` were set **unconditionally** — mobile or not.
- All nine logical columns 0–8 were written regardless of mode.
- `_mobUI` (the only thing "Mobile Layout" drove) changed `_hdSize`/`_seSize` to `tiny`
  and moved the table's corner. **That is the entire mobile path.**

Nine columns do not fit a phone at any font size. The toggle made the text smaller and
the overlap worse.

**Second defect in the same block.** `dashMode` offers `"Auto"`, which resolves to
`"Desktop"` — Pine cannot detect viewport size, so `Auto` is a promise the platform cannot
keep, and it is the **default**. A phone user on defaults gets the desktop table.

**Fixed.**

- `_dashMobile` drops the four *context* columns (STRUCTURE, LIQUIDITY, PRICE, MACRO) and
  keeps the five that answer *what do I do*: MARKET, BIAS, SIGNAL, RISK, DECISION.
  Table is created with 5 columns; mobile widths sum to exactly 100, weighted toward
  SIGNAL / RISK / DECISION.
- `_dashPort` additionally drops the two dense sub-rows on portrait; landscape keeps them.
- A logical→physical column map guards `tc`/`tcb` in **one place**, so all ~30 call sites
  are unchanged. Returning −1 skips the cell.
- The `Auto` tooltip now states plainly that Pine cannot detect screen size.

**Bounds invariant, verified mechanically** — this is the class of bug that only appears at
runtime (`"Row 70 is out of table bounds"`, EdgeCases L250): logical columns written are
`{0..8}`; kept on mobile `{0,1,2,7,8}` → physical `{0,1,2,3,4}`, max **4**, against
`_respCols = 5` → valid `0..4`. Confirmed the only two `table.cell(tblA, …)` sites are the
guarded ones, so nothing can bypass the map.

**Master only.** The strategy arms define `tc`/`tcb` but never create `tblA` and never call
them — the dashboard was stripped from the backtest twins — so the A/B diff is untouched.

**Not addressed:** the price-axis label crowding also visible in the screenshot. Those are
chart labels from the Visuals tag registry, which already does collision avoidance; on a
narrow viewport there are simply too many. Existing knobs: raise `tagGapATR`, lower
`srCount`, lower `srMaxDistATR`, or turn off `showTags` groups. Changing those defaults
would alter every chart, so it is left as a user setting.

---

## F-A12 — the per-trade probability the export promised was never emitted `HIGH` `BUG` *(FIXED)*

Found while writing the data-collection runbook — i.e. by asking "what will actually be in
the file the operator sends back?"

**The promise.** `Strategy.pine` states that the entry comment exists because *"validate.py's
calibration test needs a `prob` and `tq` per trade, and those are internal engine values
absent from the standard export… Format `"TQ<n>|P<pct>"` parses trivially into the two
columns."* It also states, correctly, that this **must precede the baseline run**, because
`alert()` fires only forward in real time and can never backfill a backtest.

**What was emitted.** `TQ<n>|CG<n>|B<n>V<n>|D<n>` — trade quality, calibration grade, schema
build, feature version, bar-data status. **No probability field at all.**

**Failure scenario.** The operator runs a full backtest, exports the List of Trades, and
discovers the one field a calibration test requires is the one field missing. By the code's
own reasoning that costs a **second complete backtest**, since no alert can backfill it. The
defect hid behind a comment describing the *intended* format rather than the real one.

**Fixed** in both arms, and deliberately before any baseline run. `|P<pct>` is appended, and
it is the **directional** probability — `_calibratedProb` for longs, `1 − _calibratedProb`
for shorts — i.e. P(*this trade* wins) rather than P(bullish). A reliability curve needs the
former; using the latter would invert every short.

Emitted format is now `TQ<n>|CG<n>|B<n>V<n>|D<n>|P<pct>`, and the comment describes what the
code does. Applied identically to both arms, so the A/B diff is unchanged.

---

## F-A13 — `Undeclared identifier "OUTCOME_N"` — it never compiled `CRITICAL` `BUG` *(FIXED)*

**The first finding from an actual compiler.** Reported by the operator with the exact
error, from all three files.

```
Error at 2815:168   Undeclared identifier "OUTCOME_N"     (Master)
Error at 2712:168   Undeclared identifier "OUTCOME_N"     (both twins)
```

`f_tradePlan()`'s `planReason` string calls `str.tostring(OUTCOME_N)`, but `OUTCOME_N` was
declared **12 lines below the function**. Pine requires declaration before use.

**This was present in the originally audited v1 build** — `OUTCOME_N` used at v1 L2767,
declared at v1 L2779. So **§8.1 is closed as a fact: the Master had never compiled.** Every
"still not compiled" caveat in this audit was pointing at something real.

**The previous fix attempt was incomplete, and said so.** A note at the old site records
hitting this same error before: *"Q7.3 FIX: this block reads OUTCOME_N, so it must sit BELOW
that declaration. Moving it above f_tradePlan in Q7.1 also moved it above OUTCOME_N →
Undeclared identifier."* That moved a **different** block below the declaration — fixing
that reader and leaving `f_tradePlan` broken, because the function sits above either way.

**Fixed** by moving the `tfSec` / `HIST_MAX` / `OUTCOME_N` block **above** `f_tradePlan`
instead. `chartTFSeconds` is declared at L686, far earlier, so nothing the block needs is
out of reach, and declaring earlier cannot break a later reader. Verified: one declaration
each (no duplicates), `OUTCOME_N` L2658 < `f_tradePlan` L2660 < first use L2834, and the
A/B diff is unchanged.

### My checker missed it — that gap is now closed

`undeclared.py` asked only whether a name was bound **anywhere** in the file. `OUTCOME_N`
is, so it passed. The rule Pine actually enforces is **declaration before use**: a use
inside a function may reach that function's params/locals, or a global declared before the
**function definition line**.

`audit/tools/order.py` implements that rule. Run against the broken build it reported
**exactly the compiler's three lines** — Master L2815, twins L2712 — and nothing else, so
this class is clean across all five files.

That is the second checker gap this session, and the third time a static pass gave false
confidence. Worth stating plainly: these tools narrow the search, they do not replace the
compiler.

---

## F-A15 — calibration map applied to the wrong variable `P0` `BUG`+`STAT` *(FIXED v12)*

**Found from a live 15M screenshot**, then confirmed arithmetically.

`hPred` stores **`bullScore`** at both write sites, so the Platt fit is a map
**`bullScore → P(bull resolution)`**. The bear branch fed **`bearScore`** into that same
fitted map and took the complement.

**A map fitted on one variable, evaluated on another.** Nothing establishes symmetry between
the two scores, and the three-way normalisation (`bull + bear + range ≈ 100`) means they are
not on a comparable scale — a *dominant* score sits routinely in the 40s, i.e. **below** the
sigmoid's 50 centre, so the dominant direction mapped to a **low** probability.

**Observed symptom.** Live 15M: `L 31 / S 42 / R 26` — bear dominant, `BIAS BEAR-ISH`, plan
`SHORT` — and the panel printed **`mP=73%`**, which reads bullish. The dashboard contradicted
its own bias and its own trade plan on the same row.

**Why it was not cosmetic.** Since the F-A02 wiring, `_calibratedProb` **gates entries**:

| | short directional prob | gate @ 0.50 |
|---|---:|---|
| v10 — `1 − sigmoid(bearScore=42)` → 0.69 | **0.31** | **VETO** |
| v12 — `1 − sigmoid(bullScore=31)` → 0.13 | **0.87** | **PASS** |

Same bar, same data, opposite decision.

**Fix.** Evaluate the map on `bullScore` always — `_calP` already *is*
`clamp(sigmoid(bullScore))`. Direction is applied at the gate, which already reads
`_calibratedProb` for longs and `1 − _calibratedProb` for shorts. The range-dominant branch is
kept (0.5 = no directional opinion; it misuses no map). `_pBear` removed — **0 executable
occurrences** in any file.

**Expected behaviour change:** the rule becomes symmetric in `bullScore` — longs need it
above ~50, shorts below ~50. **Fewer longs, more shorts** than v10. `useCalGate = false`
holds the previous behaviour.

---

## F-A14 — F-037's suppression was incomplete `P2` `PRES` *(FIXED v13)*

Recorded in `FORENSIC_AUDIT_Q5.md` §50. F-037 suppressed `oOosCI` because a ±x% interval is
the notation for a fixed independent holdout, and the population it sat on is a rolling,
continuously re-drawn one. A **second** interval, `_wrCI95 → wrCIStr`, still rendered
`+/-x%` in the dashboard risk cell over `oMatch`, the same rolling population, so the claim
F-037 set out to remove stayed on screen as `WR 74%+/-4%`.

**Fix (Master only).** The render drops `wrCIStr`; the cell now reads `WR nn% ROLL …`. The
formula is unchanged and still computed. As with `oOosCI`, the variable is **deliberately
write-only** (1 declaration, 1 assignment, 0 reads, verified by search), feeds no gate,
probability, risk term or alert, and is annotated so an orphan sweep does not delete it. It
is restored when a genuine frozen holdout exists (F-037B). Two header comments that claimed
the interval was displayed are corrected.

**Not changed:** the strategy twins have no dashboard. Their `wrCIStr` was already
write-only, so they are untouched and the A/B diff stays at five hunks. The `~touch …%±x`
credible interval on the plan panel is a different construction (Beta-Binomial on analog
hit rates, Q6.8) and was not part of this finding.

---

## F-A16 — short probability inherits the timeout rate `P2` `STAT` *(FIXED v14)*

**v14 resolution.** The bear map *could* be fitted after all. The race label `hOut` is
symmetric (+1 = up first, −1 = down first, 0 = timeout), so P(bear resolution | bullScore)
comes from the same bins and the same x as the bull fit, just with `oc == −1` as the
target. v14 adds that fit (`gCalFitBear`, negative slope required, bounds mirroring the
bull fit's).

The gate then compares like with like. With three outcomes, 0.50 is the right boundary
only for the probability **conditional on resolution**, P(win)/(P(win)+P(loss)).
Comparing the *unconditional* P(win) with 0.50 vetoes by the timeout rate, and that rate
depends on timeframe: in a fair market with a 3-bar horizon only ~70% of races resolve, so
P(win) ≈ 0.35 (`audit/tools/race_model_check.py`). Each direction now uses its own fit,
conditioned. Until the bear map fits, the v12 behaviour holds exactly. The TQ history term
uses the published OOS bear rate instead of `100 − oOosWr`.

*Original finding, kept for the record:*

The calibration counts `oc == 1` as a win against a denominator that also contains timeouts
(`oc == 0`). So `sigmoid(bullScore)` is P(bull resolution) over **all** outcomes, and its
complement — what a short now uses — covers **"bear OR timeout"**. Short probabilities are
therefore **optimistic by the timeout rate**.

Not fixable from the bull fit: it needs a calibration fitted on **bear** outcomes, which does
not exist. Recorded rather than guessed at.

---

## F-A17 — plan probabilities read in the wrong unit `P1` `BUG` *(FIXED v14)*

`_gHit` measures MFE/MAE in units of **1.5 × ATR** (`_rU`). The plan looked it up with
`tpRR = distance / tpDist`, in units of the **plan's structural stop** (0.6 ATR … 1.6 ×
regime ATR), so every `~touch` figure was read at the wrong point whenever
`tpDist ≠ 1.5 ATR`. `pSLhit` was always the **1-unit** touch rate, whatever the stop, and
below 1 unit the interpolation returned the 1-unit value. Tight stops were therefore
credited with the much lower touch rate of a wide one. That fed `planExpectancy`, and so
the veto.

Fixed: distances are converted into the histogram's unit. The SL touch uses the adverse
ladder (long: MAE slots 4–6; short: MFE slots 0–2), and the grid has an explicit anchor at
0 units.

## F-A18 — calibrated probability could exceed 1 `P2` `BUG` *(FIXED v14)*

`_calibratedProb := 0.5 + (p − 0.5) × _regAdj` with `_regAdj ∈ [0.67, 1.5]`. At p = 0.95
that gives **1.175**, and the short complement is **−0.175**. Now clamped to the fitted
map's own [0.05, 0.95]. The bear map is deliberately not regime-adjusted: `_regAdj` is
built from bull win rates only, and using it on the bear side would repeat F-A15's error.

## F-A19 — the veto quantity was not an expectancy `P0` `STAT` *(FIXED v14)*

This was the forensic audit's verdict reason #2. `planExpectancy = pTP1 − pSLhit` is a
difference of two **marginal** touch rates over one population (F-038): not mutually
exclusive, not a race, and with no payoff in it. It still vetoed trades via `tqVeto`.

**Measured on synthetic data where the truth is known** (`race_model_check.py`,
driftless price, true E[R] = 0 at every RR): the old estimator reads **−0.27 at RR 2 and
−0.34 to −0.46 at RR 3**, so it systematically vetoed well-structured trades in a fair
market. The v14 estimator reads within about ±0.03 R at every RR and both horizons. That
residue is the simulation's own fill-overshoot artefact.

**v14 estimator.** A chronological first-touch label `hRace` for six races (long and
short, TP at 1R/2R/3R against a 1R stop, stop first on a same-bar tie), plus the horizon
mark-to-market `hTerm` for races still open at the horizon:

    E[R] = P(TP1 first)·RR1 − P(SL first) + E[timeout MTM] − cost_R

The MTM term is what keeps it horizon-robust. For a bracket held past the horizon, MTM is
the optimal-stopping-unbiased estimate of its eventual P&L when price is driftless;
counting timeouts as 0 while charging cost would have biased E[R] negative wherever the
horizon is short (F-035).

**Approximation, stated:** the grid's stop is 1 regime-R and the plan's is structural.
Reading RR1 off the grid assumes the race is scale-free in stop distance, which is exact
only when the plan uses its regime-ATR fallback.

**Model check ≠ Pine test.** The simulator re-implements the maths; it does not execute
the `.pine`. `SCHEMA_BUILD` 2 → 3 so exported trades from the two definitions never pool.

## F-A20 — EdgeCases asserted a fixed defect and passed `MEDIUM` `PRES` *(FIXED v14)*

C3 "timeout charged ZERO cost" and C5 encoded the pre-F-A10 behaviour. The Master has
charged timeouts since v7 (`st += frAdj`). They passed because the harness tests its own
transcription of the Master, not the Master. They are corrected, all citations are
re-derived against v14, and GROUP K adds 20 assertions for the v14 maths (92 total).

---

## F-A21 … F-A26 — the v16 traceability and formula pass *(FIXED v16)*

**Wiring.** `audit/tools/deadcode.py` checks every symbol in all five files for four
failure classes: never read, read only by its own update (`x += …`), write-only arrays,
and functions never called. It iterates, because removing one dead symbol can orphan
another. After v16 the result is **0 dead** in every file. What remains is structural and
documented in the tool: the stats-engine tuple slots in the twins (Pine requires every
element to be named; the Master reads them all), `ta.dmi`'s unused slots in Visuals, and
the three inputs each strategy arm computes only because the *other* arm's gate reads them
(this is what keeps the arms identical apart from the gate). Pruning a symbol that was dead
in only one arm broke the A/B identity (7 hunks). So the pruning was redone to remove only
symbols dead in **both** arms, and the diff is back to 5.

**Formulas.** Checked against textbook definitions:
- Verified correct: raw-moment skewness and kurtosis; the A–S 26.2.23 normal quantile
  (constants checked); the correlation critical value r = t/√(df+t²) with Bonferroni over
  18 tests; the Wilson bound; binary Kelly; Laplace smoothing; the Beta-posterior interval.
- Five deviations, fixed and checked numerically (`audit/tools/formula_check.py`):

| | Old | Correct | Evidence |
|---|---|---|---|
| F-A22 | forward CF q(x) on an observed x | w with q(w) = x (Newton, 6 steps) | 99th pct: true 2.33, inverse 2.29, forward 6.64 |
| F-A23 | (p b − (1−p))/b, bull p for shorts | (p b − q)/(b(p+q)), direction's own p | p .35, q .30, b 1: optimum 7.7%, old −30% |
| F-A24 | WLS weight n | n p(1−p) (Berkson min-logit χ²) | Var logit(p̂) ≈ 1/(n p(1−p)) |
| F-A25 | smoothed o_k, N≥30 bins | raw o_k, all bins | identity exact to 1e-10; old off by 0.0035 |
| F-A26 | 2nd Fisher term at corrected z | both terms at original z | textbook form; effect ~1e-5 |

**Behaviour.** F-A22 changes `mrComposite`, and through it the stored analog feature `cM`.
F-A24 changes the fitted calibration maps. Both change which trades fire, so
`SCHEMA_BUILD` goes 3 → 4. F-A23 changes the *size guidance*, not the gate. It can
recommend a **larger** size than v15 whenever timeouts are common, because v15 counted
every timeout as a loss.

---

## v17 — features restored, not deleted (operator instruction)

v15 and v16 removed six **features** from the Master: v15 to get under the compiled-token
limit, v16 as dead code. The operator's rule is to wire features, never delete them.
Measured: the Master has about 1,430 lexical tokens of headroom, and restoring and wiring all
six costs about 1,300–1,500, so they cannot all fit back safely. Converting the engine's
repeated code into arrays was measured too, and it *adds* tokens: each `x += y` becomes an
`array.set(…array.get…)` call. So they live in `Diagnostics.pine`, which runs the
Treatment twin's engine verbatim and draws them in a panel:

| Feature | v14 state | v17 |
|---|---|---|
| Forecast cone + clean/professional hide switches | shown | shown, restored verbatim |
| V1/V2 schema shadow audit | shown (default OFF) | shown, default ON |
| Rolling reliability buckets + base rate + Brier | shown (default OFF) | shown; observed = raw frequency, as in the v16 Brier |
| What-if scenarios (PDH/PDL continuation, VWAP hold/fail) | **computed, never shown** | **wired**, with the [10, 90] clamp the R5.1 note promised but never applied |
| Rolling 95% intervals (WR, OOS) | suppressed (F-037/F-A14) | shown only under the panel's "ROLL, NOT A HOLDOUT" heading |
| Data-source census (`hDataStatus`) | **write-only** | **wired**: % of stored observations where GC / OI contributed |

**v18 — the non-features restored too (operator instruction).** The dashboard code in the
strategy twins, `calBrier`, the two complements (`oPdl1stPct`, `oBosFail`, with their engine
outputs and tuple slots) and the two trimmed request-tuple slots are all back. The twins are
their v15 text plus exactly the v16 formula corrections: each formula block is byte-identical
to the Master's. The Master's restored lines sit exactly where v15 had them (checked
neighbour by neighbour; one statement-order slip was corrected). None of this code has a
reader, so it cannot change any output. `deadcode.py` lists it as RETAINED
(`audit/tools/retained.txt`, 64 names, each verified absent from v16) instead of dead; any
dead symbol not on that list still fails.

`diag_parity.py` fails if the Diagnostics engine differs from the Treatment engine by one
code line (verified by injecting a one-character change).

---

## F-A27 … F-A29 — from the operator's first full chart run *(FIXED v20)*

The first v19 run established that all six scripts compile. The Master is under the token
limit: it renders v14+ fields (`EVrace … n885`). The strategy arms show only warnings. It
also exposed three defects:

- **F-A29 (P0).** Both arms took **0 trades** (Jan 2025 – Sep 2026, 1H). Both pre-filters
  require `recentBars = bar_index > last_bar_index - recentBarsLen` (default 120). That is a
  live-display filter present since the audited v1, and in a strategy it confines every entry
  to the last ~5 days of the chart. It is kept, not removed: a new input *Backtest all bars*
  (default ON in the arms) makes it switchable. The Master keeps its live behaviour.
  Whatever else binds, the Diagnostics **gate funnel** now shows it, stage by stage, over the
  whole history. Diagnose, don't tune.
- **F-A28.** The Diagnostics panel read `WR 80%` beside `base 20%`. For a bearish bias the
  WR cell showed 1 − P(bull), which counts every timeout as a bear win (the F-A16 error in a
  display). It now shows the engine's bear-resolution share, `oBear`, in the Master, both arms
  and Diagnostics.
- **F-A27.** EdgeCases `3 FAIL / 97`. A3 (39.51) and A6 (69.51) still expected the ROUNDED
  categories that F-021 removed; the engine is right. Fixed, and failing rows now render
  first at a readable size, because the third failure was below the visible part of the
  screenshot and is still unidentified.

---

## F-A30, F-A31 and the v21 wiring pass *(FIXED v21)*

**F-A30 (P0), the chart and the decision disagreed.** In the Master (and the engine copies)
`showOB`, `showFVG`, `showDisplacement`, `showSMT` and `showClimax` gate **detection**, not
drawing, and all default OFF. That has been so since v1: the comment claiming "detection still
runs and feeds the decision path" was untrue at defaults. Consequences:
- displacement, half of the entry trigger (`bullStructActive or displacementUp`), never fired;
- no order block ever formed (its onset is a displacement), so none reached the SL/TP
  candidates, trade quality or the analog zone feature;
- FVGs were ignored.

Meanwhile Visuals draws OBs and FVGs by default, with the same definitions. The toggles are
now engine inputs defaulting ON, with the same definitions as Visuals (checked: OB onset,
displacement thresholds, FVG size). `SCHEMA_BUILD` 4 → 5.

**Checked identical, Master vs Visuals:** the NY-17:00 day roll behind PDH/PDL (28 code lines,
0 differences); daily/weekly/monthly VWAP; BB(20) basis; monthly high/low request.

**F-A31, alerts for manual MT5 execution.** Details in `RUNBOOK.md` Step 2c.

**Wiring pass.** Every name retained in v18 is now wired:
- Master: `oPdl1stPct` and `oBosFail` shown beside their partners; `calBrier` becomes the
  n-weighted RMS calibration error in the calibration detail (engine, all copies).
- Strategy twins: the dashboard builder, table helpers, display strings, layout inputs and
  drawing handles are wired through Diagnostics, which runs the same engine verbatim. That
  gives a dashboard mirror, an MT5 plan table, cross-check rows, and an engine-zones overlay
  (OB/FVG handles, and S/R containers filled with the engine's scored liquidity pools).
- The twins' dashboard builder was brought in line with the Master's (the v16 Kelly fix and
  the history-gate hint).
- The what-if factors are published by the engine instead of recomputed by the panel.

`deadcode.py` now counts drawing handles redrawn via delete/new as live. It also treats a twin
symbol read by Diagnostics as wired through the companion. Result: 0 dead, 0 retained in all
six files; `retained.txt` is empty.

---

## F-A32 … F-A34 — from the v21–v23 chart run *(F-A32, F-A33 FIXED v24; F-A34 OPEN)*

**F-A32 (P0), Master over the token ceiling.** The save reported 100,820 against 100,256. The
estimate was ~98,850 because the ratio measured on v14 (2.466) no longer held; v23 gives
2.515. A block-level backward slice from every `alert`, `alertcondition` and `plot` in the
Master found the auction layer (`f_auctionIntel`, `aucBias`; ~1,330 lexical) outside it. It
feeds only the dashboard text.

Diagnostics already carries the identical function on the Treatment engine. The layer moved
there; its "Auction" row now shows by default. `climaxUp/Down` lost their only Master reader,
so they are now displayed (`CLIMAX▲/▼`) instead of dropped.

Result: the Master drops to 38,759 lexical, ~97,480 compiled at 2.515. The B5a list
(`CONCURRENCY_AND_MIGRATION.md`) was not used: its items are small, and `liqReachScore` now
feeds the forecast and the MobileBrief card.

**F-A33 (P3), Diagnostics.** A `ta.*` call inside a ternary does not run on the bars the other
branch is taken, so its window is not the last 100 bars. The call is hoisted. `_v` → `_dsv`.
The twins' two `barstate.islast` warnings are benign: they run on bar close only, where the
last bar is both `islast` and `isconfirmed`.

**F-A34 (P1, OPEN), the score does not discriminate.** Diagnostics reliability, 1H, 2,624
resolved observations:

| Bucket | N | Predicted | Observed |
|---|---:|---:|---:|
| 0 | 534 | 21% | 18% |
| 1 | 506 | 29% | 24% |
| 2 | 513 | 34% | 18% |
| 3 | 439 | 41% | 22% |
| 4 | 632 | 54% | 19% |

Base rate 20%, Brier 0.202. The Platt map therefore pulls the calibrated probability toward
the base rate, which is the honest output, and the calibration gate blocks accordingly. The
Treatment backtest agrees: 90 trades, 44% winners, PF 0.989.

This is a statement about the *signal*, not the code. Per §9 nothing is re-weighted against
it; the only valid test is data collected after a parameter freeze.

---

## F-A35 — engine sequence audit *(FIXED v26)*

`audit/tools/sequence.py` lists every read of a global that runs **before a later write of it
on the same bar**, with function bodies placed at their call site. Master v25: 65 hits,
triaged by hand.

- **Defect (fixed).** `bullScore/bearScore/rangeScore` pass through four stages: evidence
  (L~2446), analog blend (L~4465), forecast (L~4537), normalisation (L~4542).
  - `biasLabel` was computed after stage 1.
  - All its readers come after stage 4: the DECISION box BIAS row, the Mobile TREND row and
    the BUY/SELL alert text. They print it beside the final scores, so "BEAR-ISH" could
    appear next to "B55/S40".
  - The WAIT reason `_blkWhy` chose its side from stage 1 too. After the label moved, it
    could have explained the bull side under a bearish label.
  - Both now run after stage 4, with the same formula and thresholds. They feed no gate.
    The twins do not carry them, so the A/B is untouched.
- **Intended, verified.**
  - The forecast reads the blended score, and normalisation reads the forecast.
  - The calibration record stores the stage-1 score, then R5.3-M3 overwrites it with the
    final one.
  - Every `var` hit is a state machine that reads last bar's state, then updates it:
    structure breaks, order-block arrays, FVG, calibration quantiles, the risk tracker.
  - The risk tracker reads `tqVeto` before the lock is folded in, but checks `riskLock`
    itself.
  - `pdh/pdlReachScore` is a paired clamp.
- **Accepted lag.** The trade plan (L~2636) reads `gRaceProb`/`gHitProb` written by the stats
  engine (L~3201), so the plan's hit probabilities and race EV are from the previous refresh.
  - The engine refreshes periodically anyway (every `_rb` bars or on the last bar).
  - Each refresh aggregates hundreds of outcomes, so one refresh moves the numbers
    negligibly.
  - Re-ordering would move the 7,000-token engine in all four engine copies.
  - Not changed.

---

## F-A36 — "WAIT while the market moved $30–50" *(operator report; MEASURED v27, OPEN)*

The gate funnel from the operator's Diagnostics screenshot (1H, 10,269 confirmed bars,
Treatment engine = the Master's gate):

| Stage | Bars left | Share of the previous stage |
|---|---:|---:|
| trend (EMA stack) | 7,436 | 72% |
| + HTF not opposed | 5,838 | 79% |
| + session ≥ 30, no news, no DD breach | 3,377 | 58% |
| + trigger: structure break (8-bar life) or displacement | **481** | **14%** |
| − vetoes (TQ 162, EV<0 230, P<min 149; they overlap) | **152** | 32% |

So DECISION reads BUY/SELL on 1.5% of bars and WAIT on the rest. That is the design: DECISION
answers "enter now?", and the trigger is an EVENT, so inside a trend it is false between
structure breaks. A sustained $30–50 leg can pass through with no new break, or with its only
break rejected by a veto.

**Why it is not loosened here.**
- The trades the chain DOES take break even: 90 trades, PF 0.989 (F-A34).
- Opening the trigger or lowering the veto floors on this history is exactly the §9
  prohibition. It would add trades whose value is unknown, chosen by looking at the moves.

**What v27 adds instead.** A *Missed moves* row in Diagnostics.
- It counts every move episode of at least `dgMoveUSD` (default 30) within `dgMoveBars`
  (default 12) bars.
- For each episode it records the furthest the entry chain got in that direction.
- That turns the complaint into a count per gate, measured on the operator's own chart.
- A change to that gate can then be pre-registered and tested on data collected AFTER it is
  frozen. That is the only test that would show it helps.
- **v31:** done: hypothesis H1 (fast trend gate) is pre-registered in `PREREGISTRATION.md` as the
  Challenger arm, and will be judged on the holdout from 2026-09-28 only.

**Measured (operator's chart, 1H, v27, 2026-09-27).**
Row text: `moves >=30 in 12 bars: up 544 / down 512  ENTRY 22 | stopped at: trend 632 HTF 93
sess/news/DD 77 trigger 202 TQ 20 EV 7 P 3 risk 0`. The stages sum to 1,056 = 544 + 512.

| Furthest stage reached in the move's direction | Episodes | Share |
|---|---:|---:|
| trend score below threshold on every start bar | 632 | 60% |
| HTF opposed | 93 | 9% |
| session / news / DD | 77 | 7% |
| no trigger (structure break or displacement) | 202 | 19% |
| TQ / EV / P vetoes | 30 | 3% |
| ENTRY signalled while the move was ahead | 22 | 2% |

**Reading.** The vetoes are NOT what misses the big moves; **the trend filter is**.
- It is an EMA20/100/200 and ADX score (≥ 60 of 100), so it lags by construction.
- A $30 leg that starts as a reversal begins while the score still points the old way.
- The trigger is the second cause.
- This is a diagnosis. A different trend definition would be a new, pre-registered hypothesis,
  to be frozen and judged only on bars after the freeze (§9). It would not be a fix measured
  on these 1,056 episodes.

Pre-v21 note: before F-A30 (v21), displacement detection was OFF by default, so half the trigger
never fired. Experience from those builds overstates today's WAIT rate.

---

## Confirmed clean

| Check | Result |
|---|---|
| Inputs consumed | **95 / 95**, zero orphans (Master) |
| Treatment-arm entry gates vs Master | **Identical** (L2426–2431 vs L2544–2549) — the A/B validly isolates the gate change |
| `EdgeCases.pine` unread symbols | **0** |
| `Visuals.pine` unread symbols | **0** |
| Plan direction vs signal direction | **Cannot conflict** — `_bullSide` is diagnostic-only |
| SL/TP candidate sources other than volume profile | All present and assigned in **both** Master and arms |

**Three symbols flagged by the analyzer, confirmed intentional — not defects:**

- `oOosCI` (L4215) — deliberately write-only, dormant pending a genuine frozen holdout (L4210–4214). Must not be swept as dead code.
- `oBosFail` (L3089) — exact complement of `oBosCont` (`100 - x`, L4096); intentionally not printed twice.
- `oPdl1stPct` (L3086) — exact complement of `oPdh1stPct` (`100 - x`, L3930); L4779 documents showing only one.

---

## Recommendations (not applied)

Ordered by ratio of decision-impact to risk. **None of these were performed** — F-A02 and F-A05 in particular change trading behaviour and are the operator's call.

1. **F-A01 — port the volume-profile block into both arms.** Pure parity fix: copy `Master.pine` L1904–1956 into each arm unchanged. This makes the backtest's trade plan match the live file's. Do it to **both** arms in one change, or the A/B breaks.
2. **F-A03 — rewrite the Decision Log against L2544's actual terms.** Display-only, zero decision risk, and it restores the diagnostic surface.
3. **F-A04 — decide: wire or delete.** Either pass the volume percentile into the `Visuals` zone labels, or drop the three variables and correct L246. Leaving a false wiring claim in the header is the worst of the three.
4. **F-A06 — correct L4723's citation to L4096.**
5. **F-A02 — the real question.** Connecting `_calibratedProb` to `tqVeto` is a one-line change and would be a mistake to make casually: it is currently untestable. Per `AUDIT_PROMPT.md` §8, the compiler baseline is unmeasured and the 72-assertion harness result is unrecorded; per §4.2, the calibration is fitted on a development-contaminated window behind a sliding IS/OOS boundary. Wiring a calibrated probability into the gate on that basis would be tuning against a contaminated sample — precisely what §9 forbids. **The prerequisite is a genuine frozen holdout, not a code change.**

---

## The two questions, kept apart

**Question A — is the code correct?** Largely yes, with four genuine wiring defects (F-A01, F-A03, F-A04, F-A06). The engines that are wired are constructed carefully: guards are present, `na` handling is deliberate, clamps are explicit, inputs are fully consumed. F-A01 is the one that changes numbers.

**Question B — are the statistics valid?** **Still not established, and v4 changed the
shape of the risk rather than removing it.**

Before v4 the calibration layer was disconnected: the engine applied an uncalibrated
weighted heuristic, vetoed by the sign of a marginal-frequency difference, and the
Platt fit could have been perfect or rejected with no trade changing. After v4 the
calibrated probability gates entries through `tqVeto`.

That closes the *wiring* defect. It does **not** close the *validity* one. `ROLL` is
still a sliding boundary, the history is still development-contaminated, and no frozen
holdout exists — so how well that probability is calibrated remains unmeasured. The
engine has moved from **ignoring** an unvalidated statistic to **acting on** it.

Whether that is an improvement depends entirely on whether the calibration is any good,
which is precisely the thing not established. The change is defensible — a calibrated
probability is the right quantity to gate on, and 0.50 is the right boundary — but it
should be read as a wiring correction taken with the defect documented, not as evidence
the numbers are now trustworthy.

Neither answer follows from the other, and B is still not improved by fixing A.
