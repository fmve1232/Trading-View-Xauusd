# Build v1 → v2 — applied fixes

Four findings applied. Three deliberately not applied. Nothing was tuned: no
threshold, weight, lookback or gate condition changed value. Every edit is either
a parity port of existing Master code, a correction of a display that contradicted
the engine, a removal of code with no consumer, or a comment fix.

Verify: `sha256sum -c audit/MANIFEST.sha256` · line mapping: `audit/LINE_MAP_v2.md`

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
