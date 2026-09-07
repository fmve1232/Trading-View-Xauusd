# XAUUSD Quantum — Independent Audit Prompt

**Status:** binding instructions for the auditor.
**Scope:** the five Pine v6 artefacts listed in §1 and nothing else.
**Generated against:** the artefact set committed under `artefacts/`.

This is not a generic code-review template. It is pinned to this project's
actual state: the file hashes are exact, the line references are real, and the
traps in §4 are findings that already cost this project weeks to locate. Read
§1 and §8 before you read anything else.

---

## §1 — Artefact manifest and the stop rule

You are auditing exactly these five files. Nothing else in the repository is in
scope, and no other build of these scripts is in scope.

| File | Lines | Bytes | SHA-256 |
|---|---:|---:|---|
| `artefacts/XAUUSD_Quantum_5_0_Master.pine` | 5516 | 351459 | `60a4511919a1ff8d4c90652b6aba7dc4bc32c38cacd4a8cce038bfb91097fe02` |
| `artefacts/XAUUSD_Quantum_5_0_Strategy.pine` | 4893 | 300038 | `22017af0b2fb7849fc6fc591598ea1a316b352bacccd995f663659b7344e28f6` |
| `artefacts/XAUUSD_Quantum_5_0_Strategy_OLDGATES.pine` | 4893 | 300103 | `c6814aaddc1f4856b64a423a127a383bdafe7e3d334860ae6439e1e456d37767` |
| `artefacts/XAUUSD_Quantum_5_0_EdgeCases.pine` | 276 | 18506 | `4559de25ed4afa9f7fe391ef03cb18718af91c659021eaac4c32093aeab25c83` |
| `artefacts/XAUUSD_Quantum_5_5_Visuals.pine` | 931 | 57494 | `28dd76cb07b3f6863b89e24a0933247836f64c621c8bfb72b5034fc6655c0e6b` |

> **BUILD v4 — this prompt pins the current build.** The originally audited build
> (v1) is superseded. Findings F-A01, F-A03, F-A04 and F-A06 from
> `FINDINGS_TRACEABILITY.md` were applied in v2; **F-A07 in v3** (marked basis);
> **F-A02 and F-A05 in v4**, via a single calibrated-probability veto folded into
> `tqVeto`. **All seven findings are now applied.**
>
> **§4.2 is NOT superseded by that.** Wiring the calibrated probability into the
> gate does not make it valid: the IS/OOS boundary still slides and the window is
> still development-contaminated. The engine now *acts* on a statistic whose
> calibration quality remains unestablished. An auditor must still answer §11's
> Question B as **not established** — and should now also ask what the gate is
> doing to trade selection on that basis.
> Provenance of the superseded v1 hashes:
>
> | File | v1 SHA-256 (superseded) | v2 |
> |---|---|---|
> | `XAUUSD_Quantum_5_0_Master.pine` | `27d4ab4e6ccbbe2a…` | **changed** |
> | `XAUUSD_Quantum_5_0_Strategy.pine` | `d4acc741dfbbaa2a…` | **changed** |
> | `XAUUSD_Quantum_5_0_Strategy_OLDGATES.pine` | `44465cdbb3c15752…` | **changed** |
> | `XAUUSD_Quantum_5_0_EdgeCases.pine` | `4559de25ed4afa9f…` | unchanged |
> | `XAUUSD_Quantum_5_5_Visuals.pine` | `28dd76cb07b3f686…` | unchanged |
>
> **Line references in §4, §6, §7 and §10 were captured against v1.** Every anchor's
> v1→v2 line number is mapped mechanically in `audit/LINE_MAP_v2.md`; shifts are −3
> before the decision-log block and +13 after. Use that map, not arithmetic.

Line counts are newline counts (`wc -l`). Every line reference in this document
is 1-indexed against these exact files.

**Verify before you begin:**

```
sha256sum -c audit/MANIFEST.sha256
```

**STOP RULE.** If any hash mismatches, stop. Do not audit the file you have.
Report the mismatch, name the file, and request the correct build. A finding
written against a different build is worse than no finding: it is a false
record that will be trusted later. This rule has no exceptions and no
"close enough" case — a one-byte difference between the two Strategy arms is
precisely how the A/B control and treatment are distinguished (§7).

---

## §2 — What each file is, and what it is not

**`Master.pine` — the canonical live indicator.** Declared `indicator()`, L2.
This is the production decision engine and dashboard, the only file intended to
be traded from (L8–11). `QVERSION = "Q7.2"` at L6.

**`Strategy.pine` — A/B treatment arm. Backtest only, not a deployment
target** (L58–59). Declared `strategy()` at L57 as `"XAUUSD Quantum 5.0 — Treatment"`.

**`Strategy_OLDGATES.pine` — A/B control arm, pre-Q5.5 gates. Backtest only,
DO NOT DEPLOY** (L58–59). Declared `strategy()` at L57 as `"XAUUSD Quantum 5.0 — Control"`.

**`EdgeCases.pine` — a standalone diagnostic harness.** Declared `indicator()`,
L31. It imports nothing from the Master, writes nothing, trades nothing, and is
not on the decision path (L7–9). It carries 72 assertions across groups A–J.

**`Visuals.pine` — a chart-drawing companion,** run alongside the Master. It
exists because the Master's compiled build hit Pine's token ceiling and the
drawing layer had to be evicted (Master L13–18).

None of these files is a specification. Where a comment and the code disagree,
**the code is the fact and the comment is a claim to be tested.** Several
comments in these files are themselves audit findings written in place; treat
them as leads, never as evidence.

---

## §3 — Classification and evidence standard

Classify every finding with exactly one of the tags the project already uses
(`EdgeCases.pine` L27–29):

| Tag | Meaning |
|---|---|
| `BUG` | The code does not do what it was written to do. |
| `STAT` | Statistical correction — the number is computed as intended but does not mean what it is presented to mean. |
| `NUM` | Numerical stability — truncation, rounding, saturation, `na` propagation, division. |
| `PRES` | Presentation — the value is correct, the label or display is not. |
| `DESIGN` | A design assumption or accepted limitation, not a defect. |

**Evidence standard.** Every finding must cite `file:line`. Every finding must
state a concrete failure scenario: specific inputs or state, and the specific
wrong output or behaviour that follows. "This looks fragile" is not a finding.

**Severity is separate from classification.** A `DESIGN` item can be critical
(the SL/TP race, §4.1) and a `BUG` can be trivial. Grade severity by what it
does to a trading decision, not by how alarming the tag sounds.

---

## §4 — Pre-loaded traps

These are already-established findings. They are stated here so you do not
spend your budget rediscovering them, and so that you cannot accidentally
contradict them without noticing. **Your job on each is to verify it still
holds in the hashed build and to look for consequences that have not yet been
traced** — not to re-derive it.

If you conclude any of these is wrong, say so explicitly and show the code.
That is a legitimate and valuable outcome.

### 4.1 `~touch` is a marginal excursion frequency, not a race

`Master.pine` L2748–2761. The figures rendered as `~touch(<=Nb):a/b/c%` and
`~SLtouch d%` in `planReason` (L2767) come from `_gHit`, which counts
**marginal excursion touches**: `gHit[0]` increments when MFE ≥ 1R at *any*
point in the window, `gHit[3]` when MAE ≥ 1R, **independently**. One analog can
increment both.

Therefore these are marginal touch rates over the same population, **not
mutually exclusive outcomes of a TP-before-SL race**, and they do not sum to
100. `planExpectancy` (L2747) is computed as `pTP1/100 - pSLhit/100` — a
difference of two marginal frequencies.

Note the separate, genuine race at **L3021–3026** (`_oRes`, resolution expression
at L3025, guarded by `if _oR > 0` at L3022), asserted in EdgeCases group B.
**Do not conflate the two.** One is a race; the other is not. They live ~270
lines apart in the same file.

(EdgeCases L82 cites this as "Master L2957-59". That citation is stale — see
§4.5. The transcription is faithful; only the pointer is wrong.)

Also check the scan bound at L3020: `_oScan = math.max(OUTCOME_N - 60, 0)` caps
the race at the first 60 bars of the window. Where `OUTCOME_N > 60`, the race
and the `~touch` frequencies of this section are measured over **different
horizons** — trace whether anything compares them.

Also at L2751–2753: the window is `OUTCOME_N` bars, which is 60 minutes below
20M and then **3 bars** above it. The same ~26pt target measured 3% on 30M and
18% on 4H purely because the window differs. F-035 remains open as a design
decision.

Frequencies on this path are **raw — no Bayesian shrinkage** (L2757–2758).
`bayesRate` applies to the calibration bins, a different statistic.

### 4.2 `ROLL` is a sliding boundary, not a holdout

`Master.pine` L3504–3516; `Strategy.pine` L3295–3300; `OLDGATES.pine` L3295–3300.

`_sbMin`/`_sbMax` are recomputed every cycle from the live rolling buffer, so
the IS/OOS boundary **slides**: today's "OOS" row becomes tomorrow's training
row. Everything gated by `_isOosEarly` is a rolling diagnostic estimate.

The file already names all three consequences (L3509–3511): selection bias,
uncorrected multiple testing, non-independence.

Consequences to verify:
- The presentation layer labels it `ROLL`, not `OOS` — `Master.pine` L4745
  renders `"RELIABILITY (ROLL, NOT A HOLDOUT)"` and appends
  `"VALIDITY: NOT ESTABLISHED"`.
- The confidence interval is **suppressed**, not deleted — L4204–4214.
  `oOosCI` (L4215) is deliberately write-only: 1 declaration, 0 reads.
  **Do not flag it as a dead-code orphan.** It is dormant awaiting a genuine
  frozen holdout.
- The `~touch` population of §4.1 inherits this, per L2760.
- `holdoutRatio` input, `Strategy.pine` L378, defaults to 0.20.

Separately and worse (`Master.pine` L3516 onward): the historical window is
**contaminated by development** — Quantum 5.x parameters were selected against
this instrument's history. A genuine final holdout requires data collected
*after* a parameter freeze. No amount of code correctness fixes this.

### 4.3 Visuals runs a different structure algorithm and cannot produce MSS

`Visuals.pine` L66–72 (F-030).

| | Master | Visuals |
|---|---|---|
| Pivot scales | two | one (`pivotLen`, L73) |
| Break test | HH/HL/LH/LL sequence validation, ATR-distance and bar-spacing filters | simple close-through-pivot (L320–321) |
| Event window | `structWindow` = 8 bars (L352, L1541–1565) | none — bias-flip CHoCH only |
| MSS | detected (`mssEventBull/Bear`, `mssActiveBull/Bear`, feeds `bullStructType`) | **cannot be produced at all** |

A `~BOS`/`~CHoCH` marker on the chart is **not** evidence the engine scored a
structure break. The `~` prefix exists to say so on the chart itself (L71).

Verify the asymmetry rather than assuming it: `MSS` appears 8 times in
`Master.pine` and exactly once in `Visuals.pine` — at L69, in the comment that
admits the absence.

This matters beyond cosmetics: `bullStructActive`/`bearStructActive` are in the
**treatment arm's entry trigger** (§7). A visual marker that looks like the
trigger, but is produced by a different algorithm, is a live
misreading hazard.

### 4.4 PMH/PML use a third date convention

There are **three** distinct date conventions in this artefact set. Confusing
any two produces levels that are wrong but plausible.

1. **NY 17:00 session anchor** — PDH/PDL, PWH/PWL, CDH/CDL. Read via
   `hour(time, "America/New_York")`, `Visuals.pine` L216–218 (F-033); Master
   equivalent at L567. DST comes from the IANA zone, so the boundary is 21:00
   UTC in EDT and 22:00 UTC in EST.
2. **Exchange-calendar week** — `Visuals.pine` L253–254: on D-and-above,
   `crossedNYWeek` falls back to `timeframe.change("1W")`, which resolves off
   the exchange calendar, not the NY anchor. Intraday keeps convention 1.
3. **Exchange-calendar month** — PMH/PML. `Master.pine` L1980
   (`request.security(syminfo.tickerid, "M", [high[1], low[1]], ...)`),
   assigned to `poolPmH`/`poolPmL` at L2006–2007. `Visuals.pine` L292 does the
   same. **This is never NY-anchored.**

So `poolPdH` and `poolPmH` sit in the same liquidity-destination scorer
(`Master.pine` L2135–2176) and in the same trade-plan TP candidate arrays, on
two different definitions of when a period starts.

Also verify the timeframe suppressions that were added around this
(`Master.pine` L1990–2004, P1-LVL-002 (b) and (c)): `poolPdH/PdL` are forced to
`na` above D, and `poolPwH/PwL` above W, because the detector would otherwise
publish a previous-week or previous-month extreme under a PDH/PWH label.
`poolPmH/PmL` receive **no such suppression** — check whether they need one.

### 4.5 EdgeCases' Master line citations are systematically stale

**This trap was found while building this prompt and has not been through a
full review. Treat it as a lead with evidence attached, not a settled finding.**

`EdgeCases.pine` transcribes expressions out of the Master and cites the Master
line each came from. **Every one of those citations is wrong against the hashed
Master build.** The offsets differ by region — measured at +7, +33, +43, +64, +101,
+118, +125, +126 and +143 lines — which is consistent with the Master having been edited at several points after
the harness was written.

| Group | EdgeCases cites | Actually in the hashed Master |
|---|---|---|
| A — regime rounding | L1823 | **L1866** `regimeComposite = int(math.round(regimeCompositeRaw))`; the thresholds are at **L1868–1869** |
| B — SL/TP race | L2957–59 | **L3021–3026**, expression at L3025, `if _oR > 0` guard at L3022 |
| C — calibration bins | L3636–3661 | `c0t`/`c0b` increments at **L3754 / L3757** |
| C — expectancy (D-001) | L3535 | `_pnlPct` at **L3661** |
| D — `bayesRate` | L260 | **L267** |
| E — bucket N ≥ 30 gate | L3854 | **L3955**, **L3990**, and `_ctF >= 30` at **L4022** |
| F — Platt/WLS clamps | L3910–3919 | **L4035–4040** (`_pfVr > 1e-6` L4036, slope clamp L4039, intercept clamp L4040) |
| G — sigmoid output clamp | L4243 / L4247 | **L4386–4387** (`_calP` clamp at L4387) |
| H — `macroRegime` | L1821 | **L1854** |

**The substance survives; the pointers do not.** Two checks confirm this:

- Group B's transcribed expression matches L3025 exactly in structure — SL
  tested first, conservative branch — and the `_oR > 0` guard that B7 asserts
  really is there at L3022.
- Group A's F-021 claim **holds**: `strongTrend`/`moderateTrend` at L1868–1869
  test `regimeCompositeRaw`, the *unrounded* composite, so the documented 40/70
  boundaries are the real ones and the 69.5 artefact is genuinely gone.
  `regimeComposite` (rounded, L1866) still exists and is used elsewhere —
  check every one of its consumers, because the rounded and unrounded values
  disagree on exactly the boundary cases group A enumerates.

**Why this matters, and why it is not pedantry.** `EdgeCases.pine` L22–25
states its own limitation precisely: the harness proves how *Pine* evaluates
these expressions, but **not** that the Master is wired to them, because
"transcription is verified by eye, not by the compiler". Stale line numbers are
the exact failure that admission predicts. Every assertion in the harness is
now unanchored: a reader cannot mechanically confirm that any `chk()` still
corresponds to live Master code, and the harness cannot detect it if the Master
drifts again.

**Audit task.** For each of the ten rows above, confirm the corrected line and
confirm the transcribed expression still matches the Master's current form —
not just its location. Report any case where the *expression* has drifted, not
only the number. That is a `BUG`-class finding; a stale line number alone is
`PRES`.

---

## §5 — Cross-file parity surface

The Master and Visuals are designed to be run together on one chart, and
several definitions are duplicated by hand between them. Every duplicate is a
place they can silently diverge. Check each:

- EMA 20/100/200 lengths — Master vs `Visuals.pine` L39–42 (user-editable
  inputs in Visuals; the tooltip at L40 warns they must stay matched).
- FVG bounds — `Visuals.pine` L353–356 vs the Master's definition.
- Order Block displacement — five conditions in `Visuals.pine` L395–400
  (body size, direction, close beyond prior extreme, body ≥ 70% of range,
  volume > 1.3× the 20-bar average) vs `Master.pine` L1516–1517.
- Session windows and DST — `Visuals.pine` L434–474 vs the Master's `euIsDST`/
  `usIsDST` trackers. `sessionQuality` gates trades, so a disagreement here
  means the chart shades a different session than the engine scores.
- S/R — the Master's scanner was **migrated** to `Visuals.pine` L705–748 and is
  documented as ported verbatim (L87–96), driven with `maxSR 6`, `scanLen 100`.
  Note that Visuals also runs a *second*, different S/R path (ATR-clustered
  touch counts, L482–519). `Master.pine` L298–299 warns the two algorithms
  disagree on level prices. Confirm which one publishes to the price axis and
  which one, if either, the Master still consumes. The Master's
  `activeResistance`/`activeSupport` come from the pivot path and remain in the
  Master (L1813).

For each: same numbers, or divergence? If divergence, does it reach a decision
or is it display-only? Say which.

---

## §6 — Repainting and intrabar stability

**Keep these two apart. Do not collapse them into one verdict.**

**(a) Historical repainting** — whether a closed bar's rendering can change.
The macro and HTF feeds use `[1]` with `lookahead_off` throughout
(`Master.pine` L539, L951, L543–547), which is the correct construction. The
4H marker in `Visuals.pine` L817 reads `high[1]/low[1]/open[1]/close[1]` and is
non-repainting by construction. The forming-4H overlay at L818 **does** repaint
and is behind an opt-in that names the cost (L806).

**(b) Intrabar stability** — whether the live, forming bar shows a decision
that reverses before close. `Master.pine` L4610–4620 documents that the
dashboard's decision chain has no `barstate.isconfirmed` gate, while alerts and
both Strategy twins **are** confirmed-gated. The stated fix is a separate
confirmed snapshot with a secondary `LIVE:` tag on divergence.

**(b) has never been tested on a live forming candle** (§8). A single
"non-repainting: PASS" verdict covering both is a false record. Report them
separately, and mark (b) `NOT RUN` unless you actually ran it.

Also in scope here: the touch alerts at `Visuals.pine` L896–923 fire in
realtime on the forming bar, deliberately (L900–905). Verify the claim at
L902–904 that they feed nothing — no gate, no score, no plotted history.

---

## §7 — A/B experiment integrity

`Strategy.pine` (treatment) and `Strategy_OLDGATES.pine` (control) are both
4776 lines and differ in exactly **four** hunks. Verify this yourself:

```
diff artefacts/XAUUSD_Quantum_5_0_Strategy_OLDGATES.pine \
     artefacts/XAUUSD_Quantum_5_0_Strategy.pine
```

Expected: L57 (strategy title), L59 (file-role comment), L2426–2427
(pre-filters), L2429/L2431 (trigger). The substantive change:

| | Control (OLDGATES) | Treatment (Strategy) |
|---|---|---|
| Pre-filter | `bullTrend and htfBullScoreGate and macroBull and regimeConfHigh and bullRsiDiv and recentBars and sessionQuality>=30 and not inNewsWindow and not _ddBreach` | `bullTrend and not htfBearScoreGate and recentBars and sessionQuality>=30 and not inNewsWindow and not _ddBreach` |
| Trigger | `bullBOS or displacementUp` | `bullStructActive or displacementUp` |

The treatment **drops** `macroBull`, `regimeConfHigh` and `bullRsiDiv`,
**weakens** the HTF gate from "bull confirmed" to "bear not confirmed", and
**widens** the trigger from a momentary BOS to an 8-bar structure window that
also admits MSS and CHoCH. This is a large, deliberate loosening. Both mirror
symmetrically on the sell side.

Audit questions:
1. Are the two arms identical in **every** respect that affects cost and
   scoring? Both must carry the same `commission_value=0.035` and
   `slippage=35` (L57 on each) — confirm the diff shows no other change.
2. `Strategy.pine` L20–56 derives those cost constants and asserts they were
   proven equal by `cost_invariant.py`. That file is **absent** (§8). The
   derivation itself is reproducible by hand: `commission_value =
   commissionL / pointValue / 2` and `slippage_ticks = (spreadCost +
   2*slippagePts) / 2 / mintick`. **Recompute both and report whether the
   stated values follow.** Do not accept them on the strength of a harness you
   cannot run.
3. L49–53 documents an accepted residual: off-session bars carry a 0.50 spread
   floor in the selector vs the 0.30 folded into the scorer. The argument that
   this affects no trade rests on `sessionQuality >= 30` excluding off-session
   bars. Is that gate actually sufficient?
4. Given §4.2, what does a win-rate difference between these two arms
   establish, and what does it not?

---

## §8 — Never executed. These must be marked `NOT RUN`.

**This is the section most likely to be quietly ignored, and it is the one that
matters most.** The following have never been executed. For each, the only
permitted verdicts are `NOT RUN` or a result you personally produced and can
evidence. **`PASS` is forbidden.** A reasoned argument that something *would*
pass is not a pass; record it as `NOT RUN` with your reasoning attached.

1. **Pine compiler check on the Master.** `EdgeCases.pine` L12 states plainly:
   *"The Master has no measured compiler baseline yet."* `Master.pine` L13–14
   records that the drawing layer was removed to satisfy the 100,256
   compiled-token limit, from a build measured at **128,210**. Whether the
   current 5448-line build compiles at all is **unknown**. Nothing in this
   audit may assume it does.

2. **The 72-assertion EdgeCases harness.** The file carries exactly 72 `chk()`
   calls (A:12, B:7, C:5, D:6, E:5, F:11, G:6, H:7, I:8, J:5). L250–253 records
   that TradingView threw *"Row 70 is out of table bounds"* at runtime, and the
   table was widened to 100 rows. **Whether the corrected build has been re-run,
   and whether all 72 pass, is unrecorded.** Note L22–25: the harness proves how
   *Pine* evaluates these expressions; it does **not** prove the Master is wired
   to them. Transcription was verified by eye, not by the compiler — and §4.5
   shows every line citation into the Master is now stale, so that wiring is
   currently unanchored.

3. **The forming-candle / intrabar stability test.** §6(b). Never run on a live
   forming bar.

4. **The `NEEDS-MASTER` cases M1–M8.** `EdgeCases.pine` L237–248 lists eight
   cases that depend on live wiring, buffer state or feed availability and are
   explicitly **not asserted**: warm-up boundary, insufficient history, GC
   unavailable mid-session, OI unavailable, all macro feeds unavailable, session
   transition and gaps, ring-buffer wrap at `HIST_MAX`, extreme spike against
   `adaptiveATR`. L239 states §16 is not complete without them.

5. **The Python harnesses.** `cost_invariant.py` (`Strategy.pine` L29) and
   `validate.py` (`Strategy.pine` L4730) are cited as authority but are **not
   present in this artefact set**. Their results cannot be reproduced.

   **Do not reconstruct them from memory, from the comments that describe them,
   or from inference about what they must have done.** A reimplementation would
   test your reconstruction, not the original — the same trap `EdgeCases.pine`
   L20–21 names for Pine semantics. If you need them, request them. If they
   cannot be produced, every claim resting on them is unsupported, and you
   should say so in those words.

**Related, and equally not-a-pass:** `Master.pine` L4652–4660 records that
`hN` has no reset path, so `hN == 0` proves the write at L2988 **never
executed** rather than that a sample was collected and lost. Static analysis
cannot say which of the four gate terms failed — all four hold on a normal
chart with default inputs. The remaining candidates differ only at runtime.
If you find `hN == 0`, report it as an unresolved runtime question, not as a
diagnosed defect.

---

## §9 — Recorded run observations. Do not tune.

The following were observed across backtest runs of this system. They are
recorded here as **context for interpreting your findings**, not as targets.

- **Six separate Profit Factor readings** were obtained across the run history.
  *(Individual values live in the run log and are not recoverable from these
  artefacts; obtain them from the operator before citing any specific figure.
  Do not infer, interpolate, or estimate them.)*
- **The win rate swung from ~80% to ~28%** across configuration changes over
  the same instrument.

**INSTRUCTION, and it is not optional: do not tune anything in response to
these numbers.** Do not propose parameter changes, threshold adjustments,
gate reweightings, or filter additions aimed at improving them. Do not
recommend which of the six PF readings to prefer.

The reason is §4.2. The historical window is development-contaminated and the
IS/OOS boundary slides. Any adjustment made to improve a number measured on
that window **restarts the contamination cycle** and destroys what little
independence remains. The competent instinct on seeing a 28% win rate is to fix
it. That instinct is the failure mode here.

What you *may* do: explain **why** a spread that wide is consistent with, or
inconsistent with, the statistical structure you find in §4.2 and §7. A swing
of that size across gate configurations (§7 shows the treatment arm dropped
three filters and weakened a fourth) is itself evidence about how much of the
original 80% was selection. That analysis is in scope. Retuning is not.

---

## §10 — Expected answers

These are the answers this project currently holds. They are stated
deliberately rather than withheld.

If your independent reading agrees, say so briefly and move on — do not pad.
**If it disagrees, say so loudly and show the code.** A disagreement means
either you found something that was missed, or you are agreeing with the
document instead of reading the file. Both are worth knowing, and the second is
why these are written down: a disagreement you *report* is useful, a
disagreement you *suppress* is not.

| # | Question | Expected answer |
|---|---|---|
| 1 | Do `~touch` and `~SLtouch` sum to 100? | **No.** Marginal frequencies over the same population; one analog can increment both. §4.1 |
| 2 | Is `planExpectancy` a true expected value? | **No.** It is a difference of two marginal touch frequencies. §4.1 |
| 3 | Is `ROLL` an out-of-sample holdout? | **No.** Sliding boundary, re-drawn every cycle. §4.2 |
| 4 | Is `oOosCI` dead code to be removed? | **No.** Deliberately write-only, dormant pending a real holdout. Removing it is a defect. §4.2 |
| 5 | Does a `~BOS` marker in Visuals mean the engine scored a BOS? | **No.** Different algorithm, one pivot scale, no MSS. §4.3 |
| 6 | Do PDH and PMH use the same period convention? | **No.** NY 17:00 anchor vs exchange-calendar month. §4.4 |
| 7 | Is the SL/TP race at L3021–3026 a bug? | **No — `DESIGN`.** Pine cannot order intrabar events without lower-timeframe data; SL-first is the conservative branch. EdgeCases group B. |
| 8 | Does the Master compile? | **UNKNOWN.** No measured baseline. §8.1 |
| 9 | Do all 72 EdgeCases assertions pass? | **UNKNOWN / `NOT RUN`.** §8.2 |
| 10 | Is the system non-repainting? | **Split answer.** Historical repainting: correctly constructed. Intrabar stability: `NOT RUN`. §6 |
| 11 | Do EdgeCases' Master line citations point at the right code? | **No — all of them are stale**, by +7 to +143 lines. The transcribed expressions still match; the pointers do not. §4.5 |
| 12 | Is the code correct? | **Question A in §11 — and a different question from Question B. Answer them separately, in separate words.** |

---

## §11 — Two questions, kept apart, and the deliverable

**These two questions have had different answers at every stage of this
project. Keeping them apart is the single most important thing this audit
does.**

### Question A — Is the code correct?
Does each computation do what its author intended? Are there `BUG`/`NUM`
defects: truncation, rounding at boundaries, `na` leaking into a silent number,
saturation destroying information, division by a near-zero that the `== 0`
guard misses (EdgeCases I7), off-by-one in a forward window, an uncapped
drawing object, a desynchronised `ta.*` call evaluated inside a conditional?

Question A is answerable by reading code and running the harness.

### Question B — Are the statistics valid?
Do the numbers this system produces support the claims made for them? This is
where §4.1, §4.2 and §9 live. A `~touch` figure can be **computed perfectly**
and still be **meaningless as a trade probability**. A `ROLL` win rate can be
**arithmetically flawless** and establish **nothing** about out-of-sample
performance.

Question B is not answerable by reading code alone. It requires reasoning about
what the population is, how it was selected, and what was already fitted to it.

**Do not let a clean answer to A imply anything about B.** The most likely
failure of this audit is a report that establishes A thoroughly and lets the
reader infer B. State B's answer explicitly, in its own section, even when — 
especially when — it is "not established".

### Deliverable

Produce a report with:

1. **Manifest verification** — hashes checked, pass or stop. §1
2. **Findings**, each with: `file:line`, classification (§3), severity, and a
   concrete failure scenario. Ranked most severe first.
3. **§4 trap verification** — for each of the five: still holds / no longer
   holds / new consequence found.
4. **A `NOT RUN` register** — the five items of §8, each explicitly marked.
   If this section contains the word `PASS`, the report is invalid.
5. **Question A verdict** — code correctness.
6. **Question B verdict** — statistical validity. Separate section. Separate
   words. No inference from A.
7. **§10 disagreements** — any expected answer you read differently, with code.

Do not fix anything. Do not tune anything (§9). Do not reconstruct the missing
Python (§8.5). Report.
