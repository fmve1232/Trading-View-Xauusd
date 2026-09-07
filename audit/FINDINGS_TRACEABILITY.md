# Traceability & Wiring Audit — Findings

**Artefacts:** the five files in `artefacts/`, hashes per `audit/MANIFEST.sha256` (verified `OK` before and after this audit).
**Question asked:** end-to-end traceability — is every feature wired, is anything dead, are the engines aligned and calibrated.
**Method:** mechanical symbol-level traceability over **100% of symbols in all five files** (declarations, assignments, reads, function params, scope-aware occurrence counting), followed by hand-verification of every hit and manual trace of the decision path and each named engine.

**Coverage statement, stated honestly.** Every symbol in all 16,207 lines was mechanically traced. The decision path, the SL/TP construction, the probability/calibration chain and the liquidity / volume-profile / trend engines were then read and verified by hand. I did *not* give equal manual attention to all 16,207 lines, and I do not claim to have. Where a finding is mechanical, the evidence is reproducible; where it is judgement, it is labelled.

**Nothing was changed.** No tuning, no fixes — per `AUDIT_PROMPT.md` §9.

---

## Summary

| ID | Severity | Class | Finding |
|---|---|---|---|
| F-A01 | **CRITICAL** | `BUG` | Volume-profile engine is absent from both backtest arms while still consumed by the SL/TP candidate arrays |
| F-A02 | **CRITICAL** | `STAT` | The calibration engine is display-only; no calibrated probability gates any trade |
| F-A03 | HIGH | `BUG` | The Decision Log explains failures against a gate set the engine no longer uses |
| F-A04 | HIGH | `BUG` | OB/FVG volume-quality values are computed every bar and consumed by nothing |
| F-A05 | MEDIUM | `STAT` | The weighted evidence composite (`bullScore`) does not gate entry |
| F-A06 | LOW | `PRES` | Stale line citation for the BOS complement (same class as `AUDIT_PROMPT.md` §4.5) |

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

**Question B — are the statistics valid?** **Not established, and F-A02 lowers the ceiling further.** Prior to this audit the position was that `ROLL` is not a holdout and the window is development-contaminated (`AUDIT_PROMPT.md` §4.2). This audit adds that the calibration layer — the part of the system that would make a probability *mean* something — is not connected to any decision. The system does not currently apply a calibrated probability to a trading decision. It applies an uncalibrated weighted heuristic, vetoed by the sign of a marginal-frequency difference.

Neither answer follows from the other, and B is not improved by fixing A.
