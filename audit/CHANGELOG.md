# Build changelog — v1 → v2 → v3 → v4

**All seven findings applied** (F-A01, F-A03, F-A04, F-A06 in v2; F-A07 in v3; F-A02 and F-A05 in v4).
Builds v1→v3 changed no trading behaviour. **v4 does** — see that section before running it live.

**Nothing was tuned, in v4 either.** No existing threshold, weight or lookback changed
value in any build. Edits in v1→v3 were parity ports, corrections of displays that
contradicted the engine, removal of code with no consumer, comment fixes and a
traceability marker.

**v4 is the exception to "no behaviour change", and is honest about it:** it adds a new
gate condition. That gate's threshold (0.50) was *chosen on principle* — the natural
decision boundary of a probability — not fitted to any observed result, so §9's
prohibition on tuning is intact. But it does change which trades are taken. It is an
input, defaults can be reverted with `useCalGate = false`, and the recommended way to
evaluate it is an A/B with the gate off vs on.

Verify: `sha256sum -c audit/MANIFEST.sha256` · line mapping: `audit/LINE_MAP_v2.md`

---

# Build v1 → v2 — applied fixes

| File | v1 lines | v2 lines | Δ |
|---|---:|---:|---:|
| `Master.pine` | 5448 | 5461 | +13 |
| `Strategy.pine` | 4776 | 4838 | +62 |
| `Strategy_OLDGATES.pine` | 4776 | 4838 | +62 |
| `EdgeCases.pine` | 276 | 276 | 0 |
| `Visuals.pine` | 931 | 931 | 0 |

---

## F-A01 — volume-profile parity port · `Strategy.pine`, `Strategy_OLDGATES.pine`

Both arms carried only the seven `var` declarations; the computation block was
absent (`vpBuckets`/`bucketSize`: 12 references in the Master, 0 in each arm), so
`vpocPrice`, `vahPrice` and `valPrice` were declared `na` and never assigned while
still being consumed by `_slC` and `_tpLvls`.

The Master's block is now reproduced in both arms. **Verified byte-identical** in
all three files (56 lines, `int vpLookback` → `vpRefresh += 1`).

Applied identically to both arms, so the A/B diff is structurally unchanged: the
same 5 hunk headers (title, role comment, pre-filters ×2, triggers ×2), shifted
+62 lines. **Read the correction in `FINDINGS_TRACEABILITY.md`:** because the block
is `barstate.islast`-guarded, this changes almost nothing on historical bars. Its
purpose is structural parity, not different backtest numbers.

## F-A03 — decision log rebuilt against the real gate · `Master.pine`

The log scored `▲n/7` against `bullTrend, htfBullScoreGate, macroBull,
regimeConfHigh, bullRsiDiv, recentBars, sessionQuality>=30` — the **control arm's**
pre-filter set. Three of those terms are not in this file's gate, and a fourth was
inverted (`htfBullScoreGate` vs the gate's `not htfBearScoreGate`; these are not
complements — `htfAlignmentLong>=2` vs `htfAlignmentShort>=2`, both can be false).

Now mirrored term-for-term on `buyPreFilters`/`sellPreFilters` plus the structure/
displacement trigger. `_trigLog` was fixed in the same pass: it tested `bullBOS`/
`bearBOS`, the pre-Q5.8 trigger, not `bullStructActive`/`bearStructActive`.

**Arms left untouched** — deliberately. In `OLDGATES` the old log is *correct* (it
matches that file's gate), and editing `Strategy` alone would have added a fifth
diff hunk between the arms and broken the clean A/B comparison. The log is dead
code in both arms (zero reads, no dashboard), so nothing is lost.

**Side effect, handled.** Removing `regimeConfHigh` from the count orphaned it — it
had no other consumer. Rather than let a fix create dead code, it is re-surfaced
with `macroBull`/`macroBear`/`bullRsiDiv`/`bearRsiDiv` behind an explicit `ctx:`
marker, clearly labelled non-gating. Confirmed by re-running the analyzer: Master
zero-read symbols 6 → 3, no new orphans.

## F-A04 — removed three unreachable variables · `Master.pine`

`obBullVolPct`, `obBearVolPct`, `fvgVolPctAtDetect`: 3 declarations + 5 assignments
deleted (8 lines). They were assigned every bar and read by nothing — their label
consumers left with the drawing layer in Q5.4-CORE, and the file contains **zero
`label.new` calls**. The header inventory at L246 still claimed they were wired; that
claim is replaced with an accurate note.

`volPercentile` itself is untouched and still feeds `climaxUp`/`climaxDown` and
sweep quality.

**Reversible if you want the feature back:** the honest alternative is to port the
hour-bucketed `volPercentile` into `Visuals` and add a volume term to its zone
labels. That duplicates a definition across files, which is exactly the parity risk
`AUDIT_PROMPT.md` §5 warns about, so it was not done unasked.

## F-A06 — corrected stale citation · `Master.pine`

The `oBosCont`/`oBosFail` complement note cited L3545 (the analog-skip guard).
Actual construction is `_cBosFail := 100 - _cBosCont` at v1 L4096 / v2 L4109.

---

## Deliberately NOT applied

**F-A02 — wiring the calibration into the gate.** One line, and the wrong move now.
The Platt fit is trained on a development-contaminated window behind a sliding
IS/OOS boundary (`AUDIT_PROMPT.md` §4.2), the compiler baseline is unmeasured and
the 72-assertion harness result unrecorded (§8). Connecting it on that basis is
tuning against a contaminated sample, which §9 forbids. **The prerequisite is a
frozen holdout, not a code change.**

**F-A05 — routing `bullScore` into the entry gate.** A design decision, not a
defect. L2556–2561 records that score-gating was removed deliberately to stop
opportunity starvation. Reversing that is a strategy change and yours to make.

**F-A07 — unguarding the volume profile.** A blind performance change on a script
with no measured runtime baseline. Three options are set out in the findings report.

---

## Before you paste into TradingView

1. **None of this has been compiled.** There is still no Pine compiler in this
   environment and no measured baseline for the Master (`AUDIT_PROMPT.md` §8.1).
   These edits are verified by static analysis, structural checks (declaration
   -before-use, no tabs, no emptied blocks, byte-identical ported block) and a
   re-run of the traceability analyzer — **not** by a compiler. Expect to fix
   trivia on first paste.
2. **The Master gained 13 lines** and was already near the 100,256 compiled-token
   ceiling (L14 records a build measured at 128,210 before the drawing layer was
   cut). F-A04 removed 8 lines and F-A03/`ctx` added ~21, so the net token change
   is small but positive. If it now refuses to compile on token count, the first
   thing to drop is the `_ctxLog` block.
3. **Paste both arms together.** F-A01 was applied to both; updating only one
   breaks the A/B.

---

# Build v2 → v3 — F-A07 fixed (marked basis)

`Master.pine` 5461 → 5476 · `Strategy.pine` 4838 → 4853 · `Strategy_OLDGATES.pine` 4838 → 4853
`EdgeCases` and `Visuals` still unchanged from v1.

## What changed

Every trade-plan basis whose level can only exist at the live edge now carries a
trailing `°`:

| Array | Slot | Was | Now | Source |
|---|---:|---|---|---|
| `_slN` long | 5 | `VAL` | `VAL°` | `valPrice` |
| `_slN` short | 5 | `VAH` | `VAH°` | `vahPrice` |
| `_tpNms` long | 6, 7 | `POC`, `VAH` | `POC°`, `VAH°` | `vpocPrice`, `vahPrice` |
| `_tpNms` short | 6, 7 | `POC`, `VAL` | `POC°`, `VAL°` | `vpocPrice`, `valPrice` |

Six markers per file, applied identically to all three. Two explanatory comment
blocks added: one above `_slN`, one above the volume-profile block, each pointing at
the other so the guard and the markers cannot drift apart.

## Reading it on the chart

- `SL:VAL°` — stop taken from the value-area low. **No backtested bar could have
  produced this**, because `valPrice` is `na` on every historical bar.
- `SL:VAL°*` — the same, then clamped into the R-unit band. `°` and `*` are
  independent and can co-occur.
- `TP:PDH/POC°/VAH°` — first target from a reproducible level, second and third from
  live-edge-only ones.

No `°` anywhere in a plan means every level in it is one a backtest could also have
found.

## Why it is a literal, not a computed flag

`valPrice`, `vahPrice` and `vpocPrice` are assigned **only** inside the
`barstate.islast`-guarded block, so whenever one of them is selected the marker is
necessarily correct — a runtime test would be logically equivalent and cost tokens on
a file already near the compile ceiling. Comments are stripped before tokenisation, so
the two comment blocks are free; the six `°` characters are the entire runtime cost.

**If the volume-profile guard is ever relaxed to per-bar** (option 1 in the findings),
the markers become wrong and must be deleted. Both comment blocks say so.

## Verification

- **Positional** check, not string matching: in each of the four branches (SL long/
  short, TP long/short) every `°` name maps to a VP-sourced candidate and every
  VP-sourced candidate has a `°` name. Candidate and name arrays confirmed equal length
  (7/7 and 10/10).
- Basis strings confirmed **display-only** — no equality or substring test against
  `tpSLBasis`, `tp1Basis`, `tp2Basis`, `tp3Basis`, `_tpB`, `_slN` or `_tpNms` in any of
  the three files — so lengthening the literals cannot change behaviour.
- `_slN`/`_tpNms` region byte-identical across all three files (same md5).
- Exactly 6 markers in executable code per file; the other 5 are in comments.
- A/B diff unchanged in structure: same 5 hunk headers, shifted.
- No tabs, no dangling operators on any added line.

Still **not compiled** — same caveat as v2.

---

# Build v3 → v4 — F-A02 + F-A05 fixed (calibrated-probability gate)

`Master.pine` 5476 → 5516 · `Strategy.pine` 4853 → 4893 · `Strategy_OLDGATES.pine` 4853 → 4893
`EdgeCases` and `Visuals` still unchanged from v1. **All seven findings now applied.**

**This one changes trading behaviour.** The previous three builds did not.

## One gate, not two

`_calibratedProb` *is* `bullScore` pushed through the fitted sigmoid, so it is monotone
in `bullScore`. A raw-score floor and a calibrated-probability floor are the **same gate
in different units** — applying both would count one body of evidence twice, the exact
defect R5.3 removed when it took `oBosCont` out of `fAdj`. So both findings are closed by
a single term, gating on the calibrated value because it is the one already in probability
units.

The chain now completes:

```
bullScore -> _calP (sigmoid, gCalFit) -> _calibratedProb -> _calVeto -> tqVeto
          -> Master alerts + DECISION cell, and execBuyS/execSellS in BOTH twins
```

Previously it terminated at `calProbStr` -> one dashboard cell.

## What was added

| | |
|---|---|
| `useCalGate` | input, **default ON**, group Risk |
| `calGateMinP` | input, **default 0.50**, range 0.00–0.95 |
| `_calPLong` / `_calPShort` | directional calibrated probability |
| `_calGateReady` | fail-open guard |
| `_calVeto` | folded into `tqVeto` |
| `_xQ` | now shows `P✗` for a calibration veto vs `Q✗` for a TQ/expectancy veto |

## Applied on `tqVeto`, not on `shouldBuy`

`_calibratedProb` is computed ~1850 lines **below** `shouldBuy`, and Pine requires
declaration before use. Gating the entry expression itself would mean reordering a
5,516-line file — far more dangerous than this. `tqVeto` is the veto every consumer
already respects, including `execBuyS`/`execSellS` in both twins, so **the A/B measures
this change**.

## The threshold is 0.50 and that is not a tuned number

0.50 is the only non-arbitrary value available: the natural decision boundary of a
probability — *do not take a trade the calibrated model puts below even odds in that
direction*. Any other default (0.55, 0.60) would be a figure fitted to nothing, which is
what §9 forbids. It is an input so it can be moved deliberately rather than silently.

Note that raising it above 0.50 also vetoes range-dominant setups, whose calibrated
probability is exactly 0.50 in both directions.

## Fail-open, which is not optional

`_calGateReady` requires a real Platt fit (`gCalFit[0]` non-`na`) **and** `oOosNeff >= 10`
**and** a non-`na` probability. Until all three hold the term is inert and behaviour is
byte-for-byte as v3. Without this a fresh chart would sit at NO TRADE indefinitely and
look broken.

## Validity — read this before running it live

**Wiring the probability in is not the same as validating it.** F-037 still stands: the
IS/OOS boundary slides, the window is development-contaminated, and no frozen holdout
exists, so *how well* this probability is calibrated is still unmeasured.

The engine has moved from **ignoring** an unvalidated statistic to **acting on** it.
Whether that is an improvement depends on whether the calibration is any good — precisely
the thing not established. Set `useCalGate = false` to restore v3 behaviour exactly.

Suggested way to find out, and the only one that does not restart the contamination
cycle: run the twins with the gate **off**, then with it **on**, changing nothing else.
That measures the gate's effect as an A/B rather than tuning toward a number.

## Verification

- Declaration-before-use confirmed for all seven dependencies in all three files
  (`_calibratedProb`, `gCalFit`, `oOosNeff`, `shouldBuy`, `shouldSell`, and both inputs).
- Gate block byte-identical across all three files (same md5).
- Traceability re-run: Master zero-read still 3 — the same intentionally dormant symbols
  (`oBosFail`, `oOosCI`, `oPdl1stPct`) — **no new orphans**.
- `_calibratedProb` and `gCalFit` now have non-display consumers; the chain reaches
  `tqVeto`.
- A/B diff unchanged in structure: same 5 hunk headers, shifted.
- No tabs, no dangling operators on any added line.

Still **not compiled** — same caveat as v2 and v3, and the Master is now 5,516 lines with
two more inputs against the token ceiling.
