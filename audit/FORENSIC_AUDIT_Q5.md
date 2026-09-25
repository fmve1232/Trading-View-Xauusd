# QUANTUM 5.0 — MASTER FORENSIC AUDIT

**Mode:** READ-ONLY. No source file was modified in producing this report.
**Build audited:** v11 · commit `5d516ef` · hashes in `audit/MANIFEST.sha256`.
**Date:** 2026-09-09

---

## 0. SCOPE AND HARD LIMITS — READ FIRST

This audit brief asks for 65 sections, 12 tables, line-by-line classification of 16,700
lines, and independent recomputation of every critical formula. Three of those are
**not achievable in this environment**, and saying so plainly is worth more than a
padded document.

| Required | Status | Why |
|---|---|---|
| §52 Independent golden recomputation (EMA/ATR/VWAP/σ/z/corr/Sharpe…) | **BLOCKED** | **There is no XAUUSD price data here.** Recomputing an EMA requires bars. I have source code only. |
| §28/§29 Multi-timeframe testing across 1m…1W | **BLOCKED** | Requires executing Pine. No runtime. |
| §37 Monte Carlo, §36 walk-forward, §35 backtest realism | **BLOCKED** | Requires trade data. None exists — no backtest has been run. |
| §13 Numerical verification of every formula | **PARTIAL** | Unit/dimension and structural analysis: done. Numerical difference vs reference: blocked as above. |
| §9 Line-by-line GREEN/…/BLACK for 16,700 lines | **PARTIAL** | 100% of *symbols* traced mechanically. Per-line colour classification of every line is not defensible without execution; material findings are given instead. |

**What this means:** any section below marked `NOT RUN` is genuinely not run. Per the
project's own discipline, `NOT RUN` is never rendered as PASS. The blocked items are
exactly what `audit/RUNBOOK.md` exists to collect.

**One finding overrides everything else and is stated here rather than buried:**

> **The Master had never compiled.** `f_tradePlan()` read `OUTCOME_N` twelve lines before
> its declaration — `Undeclared identifier "OUTCOME_N"` — and that defect is present in the
> **originally supplied v1 source**. Every statistic, probability, score and dashboard value
> in this system has therefore **never executed**. Fixed in v10; compilation still
> unconfirmed at the time of writing.

---

## 1. EXECUTIVE SUMMARY

Quantum 5.0 is an **architecturally coherent, unusually well-documented, and statistically
unvalidated** system. Its engineering discipline is above average — the source contains its
own audit trail, names its own defects, and refuses to overclaim in several places where it
easily could. That same trail is also where several defects were hiding, because a comment
describing an intended fix is not a fix.

**The central structural finding**, established mechanically rather than by opinion:

Until the changes made during this engagement, the two most sophisticated components in the
system — the **Platt/WLS probability calibration** and the **weighted evidence composite**
where trend, structure, flow, macro and liquidity converge — **reached no decision**. Both
terminated in dashboard strings. The only probability-shaped gate ran on an uncalibrated
weighted average of hand-set constants, vetoed by the sign of a quantity that is not an
expectancy.

**The central statistical finding:** there is no out-of-sample evidence anywhere in this
system. The IS/OOS boundary is recomputed every cycle from a rolling buffer, so it slides;
the price history was already used to select Quantum 5.x parameters; and **326 distinct
hardcoded comparison thresholds** exist in the Master alone, none with out-of-sample
validation. The system's own presentation layer is honest about this — it labels the readout
`ROLL, NOT A HOLDOUT` and appends `VALIDITY: NOT ESTABLISHED`.

**Verdict: D — NOT READY.** See §65. The path to C (Research Ready) is short and specific.

---

## 2. SOURCE MANIFEST

| File | Lines | Bytes | SHA-256 (16) | Role |
|---|---:|---:|---|---|
| `XAUUSD_Quantum_5_0_Master.pine` | 5,615 | 359,886 | `b81db1b65bbf9f2a` | Canonical live indicator |
| `XAUUSD_Quantum_5_0_Strategy.pine` | 4,972 | 306,878 | `339e972fda81085e` | A/B **treatment** arm |
| `XAUUSD_Quantum_5_0_Strategy_OLDGATES.pine` | 4,972 | 306,943 | `a53d4841f670ebe1` | A/B **control** arm |
| `XAUUSD_Quantum_5_5_Visuals.pine` | 994 | 62,656 | `2d7de37f3e737efa` | Chart companion |
| `XAUUSD_Quantum_5_0_EdgeCases.pine` | 301 | 21,307 | `538f8eee0a652851` | 72-assertion harness |

---

## 3–4. ARCHITECTURE AND CODE INVENTORY

| Metric | Master | Strat A | Strat B | Visual | Edge |
|---|---:|---:|---:|---:|---:|
| Code lines (comments/strings stripped) | 3,582 | 3,199 | 3,199 | 646 | 138 |
| Inputs | 97 | 89 | 89 | 63 | 0 |
| Functions (`=>`) | 29 | 21 | 21 | 6 | 19 |
| Arrays | 46 | 54 | 54 | 21 | 5 |
| `for` / `while` loops | 19 / 5 | 18 / 5 | 18 / 5 | 17 / 11 | 2 / 0 |
| `if` statements | 320 | 294 | 294 | 86 | 12 |
| `request.security` | 19 | 19 | 19 | 3 | 0 |
| `request.security_lower_tf` | 0 | 0 | 0 | 3 | 0 |
| `strategy.*` calls | 0 | 8 | 8 | 0 | 0 |
| Drawing objects (label/line/box) | 0 | 1 | 1 | 26 | 0 |
| `var`/`varip` declarations | 320 | 332 | 332 | 51 | 6 |
| `ta.*` / `math.*` calls | 84 / 296 | 84 / 278 | 84 / 278 | 16 / 27 | 0 / 11 |
| `na()`/`nz()` guards | 253 | 206 | 206 | 51 | 5 |

**Architectural note:** the Master contains **zero** drawing objects. The drawing layer was
evicted to `Visuals` under Pine's compiled-token ceiling. This is the root of several
integration defects (§8).

---

## 5–7. VARIABLE / FUNCTION / LINE AUDIT

**Method:** mechanical traceability over **100% of symbols in all five files** —
declarations, assignments, reads, params, scope — then hand-verification of every hit.
Tooling committed at `audit/tools/{trace,precheck,undeclared,order}.py`.

**Result — unread symbols (producer with no consumer):**

| File | Zero-read symbols | Assessment |
|---|---:|---|
| Master | 3 | All three **intentionally dormant** and documented: `oOosCI` (awaiting a real holdout), `oBosFail` and `oPdl1stPct` (exact arithmetic complements). **Not defects.** |
| Strategy A / B | 62 | Dashboard-layer remnants; the render block was stripped from the twins. Harmless but dead. |
| Visuals | 2 | `_diPV`/`_diMV` — structurally required, `ta.dmi` returns a 3-tuple. |
| EdgeCases | 0 | Clean. |

**Inputs:** 97/97 consumed in the Master. **Zero orphaned inputs.**

**Declaration-before-use:** 0 violations across all five files *after* the F-A13 fix. Before
it, exactly 3 — matching the compiler's reported lines precisely.

---

## 8. FIVE-FILE INTEGRATION AUDIT

This is where the most material defects were found.

| ID | Producer → Consumer | Defect | Severity |
|---|---|---|---|
| F-A01 | Master VP engine → twins' SL/TP arrays | Volume-profile block **absent from both arms** (`vpBuckets`: 12 refs Master, 0 arms) while `vpocPrice`/`vahPrice`/`valPrice` were still consumed. `na`-guarded consumers skipped them **silently**. | P1 |
| F-A07 | VP engine → trade plan | VP is `barstate.islast`-gated: values exist **only on the final bar**. The live plan can select a stop/target no historical bar could reproduce. | P1 |
| F-A08 | Master displacement → Visuals OB | Visuals used `body > atr14 × 1.0`; Master requires `adaptiveATR × 2.5`. **2.5× looser**, not edge-gated, while the comment claimed "Master logic mirrored". | P1 |
| F-A04 | `volPercentile` → OB/FVG labels | Computed every bar, **zero consumers** — label consumers left with the drawing layer; Master has 0 `label.new`. | P2 |
| F-A03 | Gate → Decision Log | Explainability surface scored against the **control arm's** filter set; 3 terms absent from the real gate, a 4th inverted. | P1 |

**Orphan / duplication / conflict summary:** no circular dependencies found. Duplicated
calculations between Master and Visuals: EMA lengths, FVG bounds, session/DST windows and
S/R — **FVG and session verified in parity**; OB displacement was **not** (F-A08).

---

## 9–12. DATA FLOW, DASHBOARD TRACEABILITY

Actual verified chain (only components that exist):

```
OHLCV → derived series → features (trend/momentum/vol/liquidity/session/macro)
      → evidence sub-scores (evTrendBull, evStructBull, evFlowBull, evMacroBull, evLiqBull…)
      → bullScore / bearScore / rangeScore  (weighted composite, renormalised)
      → [pre-v4: DEAD END → display]
      → Platt sigmoid (gCalFit) → _calibratedProb
      → _calVeto → tqVeto → alerts + execBuyS/execSellS
ENTRY GATE (separate path): bullTrend ∧ ¬htfBearScoreGate ∧ recentBars ∧ sessionQuality≥30
      ∧ ¬news ∧ ¬ddBreach ∧ (structActive ∨ displacement)
```

**Critical traceability finding:** the entry gate is a **conjunction of boolean state flags
only**. `bullScore` — the composite where liquidity, macro and flow converge — does not
appear in it. Direction and presentation, not permission. (F-A05.)

---

## 11/14. UNIT & DIMENSION AUDIT — a real defect found

**This section produced the most consequential mathematical finding.**

`fr = array.get(hRet, i)` — `hRet` was redefined by Q7.0 as **realised R**.
`_costATR` divided cost by `adaptiveATR` — **ATR units**.
`frAdj = fr − _costATR` therefore **subtracted ATR units from R units**.

Wrong whenever the SL multiple ≠ 1.0, and `regSLMult` defaults to **1.5**. **Every
cost-adjusted win and loss was mis-scaled**, not merely the timeouts. (F-A10.)

Second unit issue in the same block: timeouts entered the expectancy **denominator**
(`wt`/`mt` count them) while contributing **zero** to the numerator — so analog EV was
optimistic by the full transaction cost of every timeout, worst in chop and low-ADX where
timeouts cluster and where a negative-expectancy read should bind hardest.

---

## 15–19. PROBABILITY / SCORE-VS-PROBABILITY AUDIT — P0 class

**"Probability of WHAT, exactly?"** — applied to every displayed probability:

| Displayed | What it actually is | Valid as a probability? |
|---|---|---|
| `~touch(<=Nb) a/b/c%` | **Marginal excursion frequencies.** `gHit[0]` increments when MFE ≥ 1R *at any point*; `gHit[3]` when MAE ≥ 1R, **independently**. One analog increments both. | **NO.** Not mutually exclusive, do not sum to 100, **not a TP-before-SL race.** |
| `~SLtouch d%` | Same population, same marginal construction. | **NO** (as a race complement). |
| `planExpectancy` | `pTP1/100 − pSLhit/100` — a **difference of two marginal frequencies**. | **NO.** Not an expected value. **And it gates trades.** |
| `mP=nn%` (`_calibratedProb`) | Platt-mapped `bullScore`. Genuinely probability-shaped. | Shape yes; **calibration quality NOT ESTABLISHED**. |
| `oCalGrade` | `100 − 2×mean|pred−obs|` — an **accuracy grade**. | Correctly **not** labelled a probability (F-022 holds). |
| `WR nn% ±x%` | Win rate over the **rolling** analog population. | Point estimate yes; the **±x% is a false validity claim** — see F-A14. |

**Horizon defect (F-035, still OPEN by the file's own admission):** the `~touch` window is
`OUTCOME_N` bars — 60 min below 20M, then **3 bars** above it. The same ~26pt target measures
**3% on 30M and 18% on 4H** purely because the window differs. A probability whose value is
an artefact of chart timeframe is not a trade probability.

---

## 16/20. CALIBRATION AUDIT

**Implementation present:** Platt/WLS logistic calibration over 5 quantile-adaptive bins,
slope clamped [0.02, 0.25], intercept [−1, 1], rejected on `slope ≤ 0` or variance
`≤ 1e-6`, minimum 3 qualifying bins at N ≥ 30 each. Beta(1,1) shrinkage via `bayesRate`.
Brier decomposition (Murphy) present. **This is a competent implementation.**

**Defect (F-A02):** until v4 it **terminated in a dashboard cell**. `gCalFit` was read at
exactly two lines, feeding `_calP → _calibratedProb → calProbStr →` one table cell. The fit
could have been perfect or rejected outright and **not one trade would have changed**.

**Cold-start coupling (new, P2):** when no fit exists, the fallback slope is set from
`oCalGrade` — `_k = 8 + (grade−50)/50 × 12`, i.e. 8.0…20.0. The probability map's steepness
is parameterised by a quality score computed on the same contaminated population, with no
derivation given. Not an F-022 regression (it is not consumed *as* a probability) but an
unvalidated coupling.

**Never calibrate on the test set (§20):** structurally impossible to violate here for the
simple reason that **no test set exists**. That is not compliance; it is absence.

---

## 18/22/23. STATISTICAL, TIME-SERIES, EFFECTIVE-N AUDIT

| Concern | Finding |
|---|---|
| IID | **Violated by construction.** Analog outcomes overlap over `OUTCOME_N` bars. |
| Effective N | **Correctly handled in places** — `oOosNeff = oOosN / OUTCOME_N`, and `_ciN = gHitN / OUTCOME_N`. Credit where due: the overlap correction is present and thoughtful. |
| Effective N — inconsistency | `_wrCI95` uses a **different** correction: a hardcoded intra-cluster ρ = 0.3 (`_effN = oMatch / (1 + 2ρ/(1−ρ))`). Two different effective-N methods on the same dashboard, one derived, one a magic constant. §23 explicitly warns against blindly applying one correction everywhere — the opposite failure is present: two, unreconciled. |
| Stationarity | A variance-ratio guard exists (`Ratio > 3.0 → rolling statistics unreliable`). Present and appropriate. |
| Autocorrelation / clustering / fat tails | Cornish-Fisher adjustment with rolling skew/kurtosis is implemented — genuinely more than most retail systems attempt. |
| Multiple testing | **Uncorrected.** The sliding boundary implies thousands of implicit re-tests; the file says so itself. |

---

## 22/26. DATA LEAKAGE AUDIT

| Vector | Result | Evidence |
|---|---|---|
| `request.security` lookahead | **CLEAN** | All 19 Master calls use `lookahead_off` with `[1]` indexing. |
| Future bars in normalisation | **CLEAN** — none found | Percentile/z-score paths use trailing windows. |
| Test-set calibration | **N/A** | No test set exists. |
| Threshold optimisation on test set | **UNKNOWN** | 326 hardcoded thresholds, provenance undocumented (§38). |
| Development contamination | **PRESENT, ACKNOWLEDGED** | Quantum 5.x parameters were selected against this instrument's history. This is leakage at the *project* level and no code change fixes it. |

---

## 23/27. REPAINTING AUDIT

**The two must not be collapsed into one verdict.**

| Component | Historical repaint | Intrabar stability | Verdict |
|---|---|---|---|
| Macro/HTF feeds (19 `request.security`) | Correct — `[1]` + `lookahead_off` | n/a | **PASS** |
| 4H marker (Visuals) | Non-repainting by construction | n/a | **PASS** |
| Forming-4H overlay | **Repaints** | — | **PASS — opt-in, cost named** |
| Pivots / structure | Confirm `pivotLen` bars back | n/a | **PASS** |
| Alerts, both strategy twins | Confirmed-bar gated | Gated | **PASS** |
| **Dashboard decision chain** | — | **No `barstate.isconfirmed` gate** | **NOT RUN** — a confirmed snapshot with a `LIVE:` divergence tag is implemented; **never tested on a live forming candle.** |

---

## 30/31/32. XAUUSD, SMC AND VOLUME AUDIT

**Gold-specific handling — genuinely strong:**
NY 17:00-anchored day/week via IANA `America/New_York` (DST by calendar, not arithmetic);
separate EU/US DST trackers; session-quality gating; news-window blocking; a day-of-week
profile; DXY / 10Y / TIP / EUR / XAG / SPX correlation layer; `mintick == 0.01` hard gate
that **refuses to trade** on a feed whose cost model does not match.

**Volume — correctly and explicitly labelled.** The source states that spot XAUUSD `volume`
is a **tick count, not contracts**, that Pine has no bid/ask tape, and that the "absorption"
and "footprint" layers are **documented approximations**. It does not claim exchange order
flow. **This is the correct treatment and the audit brief's §32 concern does not apply.**

**SMC:** BOS / CHoCH / MSS / sweeps / OB / FVG / displacement all implemented with formal
operational definitions (two pivot scales, HH/HL/LH/LL sequence validation, ATR-distance and
bar-spacing filters, 8-bar `structWindow`). **Visuals implements a different, simpler
algorithm and cannot produce MSS at all** — marked `~` on-chart to say so. Honest.

---

## 38. THRESHOLD AUDIT — **326 distinct hardcoded thresholds**

Excluding the 97 configurable inputs. Sample of the most-used:

| Threshold | Uses | Origin | OOS validation |
|---|---:|---|---|
| `oOosNeff >= 10` | 12 | undocumented | **none** |
| `sessionQuality >= 30` | 9 | undocumented | **none** |
| `bodyPct > 70` | 6 | SMC convention | **none** |
| `atrPercentile >= 80` / `<= 20` | 8 | undocumented | **none** |
| `oMatch >= 30`, `c0t..c4t >= 30` | 25 | classical N≥30 heuristic | **none** |
| `regimeCompositeRaw >= 70 / >= 40` | 3 | "heuristic breakpoints" (file's own word) | **none** |
| Platt clamps `[0.02, 0.25]`, `[−1, 1]` | 2 | undocumented | **none** |
| `_rhoEst = 0.3` | 1 | undocumented; sets CI width | **none** |

**Verdict:** not one threshold in this system has out-of-sample validation, because no
out-of-sample data exists. **No threshold may be called "optimal".**

---

## 39. EDGE CASE AUDIT

The harness is a genuinely good artefact: 72 assertions across 10 groups (A rounding,
B SL/TP race, C timeout accounting, D `bayesRate`, E sample minimums, F Platt clamps,
G sigmoid clamps, H `macroRegime` saturation, I `na`/zero-division, J vote pool). It is
standalone, imports nothing, trades nothing.

**It states its own limit correctly:** it proves how *Pine* evaluates these expressions; it
does **not** prove the Master is wired to them, because transcription was verified by eye.
Eight `NEEDS-MASTER` cases (M1–M8) are explicitly **not asserted**.

**Status: NOT RUN.** The 72 assertions have never produced a recorded result.

**Defect found (F-A09):** every `Master L<n>` citation in the harness was **stale**, by +7 to
+143 lines — the expressions still matched, the pointers did not. Re-derived mechanically.

**Defect found via that re-derivation (F-A10):** Group C's claim was re-verified against live
code and found still true *for a different reason than documented* — the D-001 fix that the
Master claims closed it does not bite (§11/14).

---

## 40–42. STRATEGY A/B AND MASTER/VISUAL AUDIT

**A/B integrity: sound.** The twins differ in exactly 5 hunk headers — title, role comment,
pre-filters (×2), triggers (×2). Same commission (`0.035`), same slippage (`35`), same
`abTestQty`. Treatment arm's gates are **byte-identical** to the Master's.

| | Control (OLDGATES) | Treatment |
|---|---|---|
| Pre-filter | `bullTrend ∧ htfBullScoreGate ∧ macroBull ∧ regimeConfHigh ∧ bullRsiDiv ∧ …` | `bullTrend ∧ ¬htfBearScoreGate ∧ …` |
| Trigger | `bullBOS ∨ displacementUp` | `bullStructActive ∨ displacementUp` |

The treatment **drops three filters, weakens a fourth, and widens the trigger** from a
momentary BOS to an 8-bar window admitting MSS and CHoCH. A large, deliberate loosening.

**Master/Visual separation: violated in one direction.** Visuals is *not* pure presentation —
it independently recalculates structure, order blocks, S/R, FVG and sessions. Where those
recalculations disagree with the Master (F-A08), the chart shows the operator something the
engine never scored.

---

## 43/46. NUMERICAL STABILITY

Statically reviewed; **execution NOT RUN**. Notable:

- Division guards are `== 0`, not epsilon-based. `safeDiv(10, 1e-12)` passes the guard and
  explodes — asserted by the harness (I7) but never executed.
- `math.exp` overflow guarded by a ±10 clamp on the tanh argument. Correct.
- `int()` truncation vs `math.round()` half-away-from-zero: both used; harness Group A
  establishes the difference. **NOT RUN.**
- Clamp saturation destroys information deliberately (Platt slopes 0.5 and 0.9 both → 0.25).
  Documented, asserted (F11), **NOT RUN**.

---

## 47/48. PINE LIMITS & PERFORMANCE

The Master compiled at **128,210 tokens against a 100,256 ceiling** in a prior build, which
is why the drawing layer was evicted. Current lexical token growth from all audit fixes:
**+0.35%** on the Master — negligible. Ceiling risk is **low but unmeasured**.

`HIST_MAX` scales 1,200→4,500 by timeframe; `max_bars_back = 5000`. The stats engine chunks
its work to avoid timeout. VP is `barstate.islast`-gated **for performance** — which is the
direct cause of F-A07.

---

## 50. HISTORICAL REGRESSION FINDINGS (§51 of the brief)

| ID | Equivalent code exists? | Still present? | Fix correct? | New variant introduced? |
|---|---|---|---|---|
| **F-020** | **No trace in any of the five files** | — | — | Cannot assess. Provide the original text if this must be closed. |
| **F-022** (calibration grade ≠ probability) | Yes, L3200 | **No** — correctly labelled and never consumed as a probability | **Correct** | **Adjacent issue:** `oCalGrade` parameterises the cold-start sigmoid slope (L4497). Not a regression; unvalidated coupling. |
| **F-035** (horizon mismatch) | Yes, L2824–2842 | **YES — still present** | **Labelling only.** The file itself says: *"the horizon mismatch itself (F-035) remains OPEN as a design decision."* | No new variant. |
| **F-036** (read-before-assign on `oOosN`) | Yes, L4306 | **No** — `oOosN := __on` (L4316) precedes `_wNeffD` (L4318) and `oOosNeff` (L4321) | **Correct**, and already correct in v1 | **Live charts still show the pre-fix symptom** (`0/10eff` at `100%hist`) — because both are running a build older than v1. |
| **F-037** (ROLL is not a holdout) | Yes, L3581 / L4322 | **Partially** | Relabelling **correct** (`ROLL`, `VALIDITY: NOT ESTABLISHED`); `oOosCI` suppression **correct and verified write-only** | **YES — new variant. See F-A14 below.** |

### F-A14 (new, P2) — F-037's suppression is incomplete

F-037 suppressed `oOosCI` because *"a ±x% interval is the standard notation for a fixed
independent holdout; rendering one over a continuously re-drawn population is a false
validity claim."*

A **second, different** interval — `_wrCI95 → wrCIStr` (L4968–4975) — still renders
`+/-x%` on that same dashboard row, over `oMatch`, the same rolling population, using a
hardcoded ρ = 0.3. **The false-validity notation F-037 set out to remove is still on screen**,
reached through a different variable. Visible in the operator's live screenshots as
`WR 74%+/-4%`.

---

## 52–57. FINDINGS REGISTER

| ID | Sev | File | Component | Finding | Status |
|---|---|---|---|---|---|
| F-A13 | **P0** | all 3 | `f_tradePlan` | `Undeclared identifier "OUTCOME_N"` — **never compiled**, present in v1 | Fixed v10 |
| F-A02 | **P0** | Master | calibration | Entire Platt chain display-only; no calibrated probability gated any trade | Wired v4 |
| F-A10 | **P1** | all 3 | expectancy | Cost subtracted in **ATR units from R units**; timeouts in denominator, zero in numerator | Fixed v7 |
| F-A08 | **P1** | Visuals | order blocks | 2.5× looser threshold than the engine, while claiming parity | Fixed v5 |
| F-A03 | **P1** | Master | decision log | Explains against the control arm's gate set | Fixed v2 |
| F-A07 | **P1** | Master | volume profile | Last-bar-only levels reach the live plan | Marked v3 |
| F-A01 | **P1** | twins | volume profile | Engine absent from both arms, still consumed | Ported v2 |
| F-A12 | **P1** | twins | export | Promised per-trade `P<pct>` never emitted | Fixed v9 |
| F-035 | **P1** | Master | `~touch` | Horizon is timeframe-dependent; 3% on 30M vs 18% on 4H | **Mitigated v14** for both gates (race EV with MTM, conditional P); `~touch` display still per-horizon, labelled |
| F-A05 | **P2** | Master | evidence | `bullScore` did not gate entry | Wired v4 |
| F-A14 | **P2** | Master | CI display | F-037 suppression incomplete — `wrCIStr` still renders ±x% | Fixed v13 |
| — | **P2** | Master | calibration | Cold-start sigmoid slope parameterised by `oCalGrade`, underived | Fixed v14 (identity map, `mP unfit`) |
| — | **P2** | Master | effective-N | Two unreconciled effective-N methods (`/OUTCOME_N` vs ρ=0.3) | Fixed v14 (`/OUTCOME_N` throughout) |
| F-A16…F-A20 | P0–P2 | all 3 + EdgeCases | probability / expectancy | See `FINDINGS_TRACEABILITY.md` | Fixed v14 |
| F-A04/06/09/11 | P2–P3 | various | wiring/docs | dead vars, stale citations, mobile layout | Fixed |

---

## 58–60. REQUIRED CALIBRATION / ML / FUTURE ARCHITECTURE

**Calibration — the only defensible sequence:**
1. **Freeze every parameter and record the date.** Nothing else can proceed first.
2. Establish the frozen baseline (`RUNBOOK.md` §4–5).
3. Collect **forward** data from the freeze date — paper or live.
4. Evaluate on that. It is the first sample the parameters were not chosen on.
5. Only then fit calibration, and only on data disjoint from the evaluation fold.

**ML readiness — honest assessment: NOT READY, but the groundwork is unusually good.**
The feature set (9-dim cosine analog vector: 7 features + session + regime) is well defined,
the missing-data policy is correct (an analog with a failed lookback is **skipped**, not
substituted — the file fixed the opposite behaviour under F-010/F-015), and per-trade state
is now exported. What blocks ML is not features: it is the **absence of any train/validate/
test separation that is not a sliding window**.

**Target definition:** the current label (`hRet` = realised R; ±1 on race resolution, else
terminal excursion) is closest to **triple-barrier**, which is the right family. The
recommendation is to make it explicitly triple-barrier with a documented vertical barrier,
because `OUTCOME_N` currently *is* the vertical barrier and it is timeframe-dependent
(F-035).

**Model recommendation:** logistic regression first — it is the honest baseline for a
calibrated binary probability, is directly comparable to the Platt layer already present,
and its coefficients remain auditable. Gradient boosting only after a frozen holdout exists.
**Deep learning is not warranted** at this sample size and would forfeit the explainability
this system has deliberately built.

---

## 61–63. TESTING / GOLDEN DATASET / REGRESSION SPEC

**Golden dataset (minimum):** XAUUSD OHLCV with explicit broker/feed identity and `mintick`,
covering ≥2 full years, spanning at least one high-volatility regime (a CPI/FOMC week) and
one compression regime; exported at each tested timeframe. Without the feed identity the
data is not reproducible, because session and tick-size behaviour differ per feed.

**Regression spec:** every finding in §52 requires a named check. Four exist as executable
tools (`trace/precheck/undeclared/order`). The 72-assertion harness covers the arithmetic.
**The gap is behavioural regression**, which needs the golden dataset.

---

## 64. INSTITUTIONAL READINESS SCORE

Scored 0–100. **`n/s` = not scoreable without execution or data — not a low score, an absent one.**

| Dimension | Score | Basis |
|---|---:|---|
| Mathematics | 62 | Competent throughout; a real unit defect (F-A10) survived to this audit |
| Statistics | 45 | Overlap correction and stationarity guard present; two unreconciled effective-N methods; multiple testing uncorrected |
| Probability | 35 | Marginal frequencies presented as trade probabilities; one such quantity **gates trades** |
| Calibration | 40 | Good implementation, disconnected until v4, validity unestablished |
| ML readiness | 30 | Features and missing-data policy good; no non-sliding train/test split |
| XAUUSD methodology | 78 | Best area. NY anchoring, DST, sessions, feed-mismatch refusal |
| SMC | 70 | Formal operational definitions; companion divergence now fixed |
| Market structure | 72 | Two pivot scales, sequence validation, event window |
| Volume/CVD | 80 | Correctly labelled a tick-count proxy; claims nothing it cannot support |
| Risk | 55 | Kelly present; **was fed an uncalibrated probability** — §36's exact warning |
| Backtesting | **n/s** | Never run |
| Repainting safety | 75 | Historical clean; intrabar **NOT RUN** |
| Lookahead safety | 88 | 19/19 `lookahead_off` with `[1]` |
| Data-leakage safety | 40 | Code clean; project-level development contamination |
| Timeframe robustness | **n/s** | Never executed on any timeframe |
| MTF correctness | 70 | Statically sound; runtime unverified |
| Code quality | 68 | Well documented; comments described fixes that did not exist |
| Performance | **n/s** | Never compiled until now |
| Architecture | 66 | Coherent; token ceiling forced a split that caused real defects |
| Dashboard | 58 | Rich; several fields overstated validity |
| Traceability | 74 | Now fully mechanically traceable |
| Explainability | 80 | Genuine strength — decision log, plan basis, honest labels |
| **Overall institutional readiness** | **≈ 42** | Weighted toward correctness and validity |

---

## 65. FINAL VERDICT

# **D — NOT READY**

Not because the system is unsophisticated. It is more carefully built than most retail
quantitative systems, and in several places — gold session handling, the honesty of its
volume labelling, its explainability layer — it is genuinely good.

**It is NOT READY for three specific reasons, in priority order:**

**1. It has never executed.** The Master failed to compile with an undeclared identifier, in
the source as originally supplied. No number this system has ever displayed has been
produced by a successful run of the current code. Everything downstream of that — every
score, probability, backtest and dashboard value — is unverified in the strongest sense.

**2. Its central probabilities do not mean what they are presented to mean.** `~touch` and
`~SLtouch` are marginal excursion frequencies over one population, not race outcomes. Their
difference, `planExpectancy`, is not an expected value — **and it vetoes trades.** A
timeframe-dependent horizon (F-035) means the same target reads 3% or 18% depending on the
chart. That is a P0-class validity problem, not a presentation one.

**3. There is no out-of-sample evidence of any kind.** The IS/OOS boundary slides; the
history already had parameters selected on it; 326 hardcoded thresholds have no validation.
The system's own readout is correct when it says `VALIDITY: NOT ESTABLISHED`.

### What moves it to C — RESEARCH READY

Three things, none of which require a code change beyond confirming the last:

1. **Confirm the Master compiles**, then run the 72-assertion harness and record the result.
2. **Freeze the parameters and record the date.** This costs nothing and is the only act
   that makes future validation possible.
3. **Collect forward data from the freeze date.** Everything before it is a diagnostic.

### What would move it to B — CONDITIONALLY READY

A frozen holdout with enough forward observations to measure a reliability curve on the
per-trade `P` now exported, plus resolution of F-035 (a horizon that does not change meaning
with the chart timeframe).

**Do not deploy capital against these probabilities until at minimum step 1 and 2 above are
complete.** Complexity is not evidence of quality, and this system's own source says so more
honestly than most auditors would.

---

*Read-only audit. No source file was modified. Findings are separated from corrections as
§4 of the brief requires; corrections applied in earlier builds are recorded in
`audit/CHANGELOG.md` and were made before this audit was commissioned.*
