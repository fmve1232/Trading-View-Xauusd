# Build changelog — v1 → … → v51

**All F-A findings through F-A20 applied (v14).** F-035 mitigated, not closed. See each build section below.
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

---

# Build v4 → v5 — F-A08 + F-A09 (chart/engine parity, harness re-anchored)

`Master.pine` unchanged · `Strategy.pine` unchanged · `Strategy_OLDGATES.pine` unchanged
`Visuals.pine` 931 → 986 · `EdgeCases.pine` 276 → 287

**Both remaining files are now touched, and no trading behaviour changes.** Visuals and
EdgeCases are display/diagnostic only — neither gates a trade.

## F-A08 — Visuals order blocks did not match the engine

The chart's OB test was `body > atr14 × 1.0`; the Master's is
`body > adaptiveATR × dispMult` with **dispMult = 2.5**. At Master defaults
`showAdaptiveATR` is OFF and `atrLen` is 14, so `adaptiveATR` collapses to `ta.atr(14)`
and equals this file's `atr14` — **the entire divergence was the 2.5× multiplier.** Every
candle with a body between 1.0 and 2.5 ATR was drawn as an order block the engine does not
recognise. And because the old test was not edge-gated, a sustained displacement pushed a
**new box every bar** of the run.

Ported verbatim from the Master: the adaptive-ATR regime blend (with its ADX dependency),
the five displacement terms, the 2.5×-enter / 1.5×-hold hysteresis latch, and the
`dispOnsetUp`/`dispOnsetDown` onset edge the Master's OB detector actually fires on.
`obDispATR` default 1.0 → **2.5**, min 0.3 → 1.5, to match `dispMult` exactly. The local
`close[1] < open[1]` filter was removed — the Master takes the previous bar as the OB
regardless of its direction, so that filter was suppressing boxes the engine records.

**Residual, stated in the file:** the Master keeps one active OB per side with a mitigation
lifecycle and a reversal-OB path; Visuals keeps the last N boxes and has neither.
**Detection now matches; retention still does not.**

`_diPV` / `_diMV` are unread on purpose — `ta.dmi` returns a 3-tuple and Pine requires
every element be named. Commented so they are not swept as dead code.

## F-A09 — EdgeCases re-anchored to the Master

§4.5 of the audit prompt was the one finding never actioned: every `Master L<n>` citation
in the harness was stale, by +7 to +143 lines against the originally audited build, and
further adrift after v2–v4. All ten were re-derived mechanically against this build and a
provenance banner added stating they must be re-derived whenever the Master changes.

The harness is re-anchored: a reader can follow any `chk()` back to live Master code. This
does **not** change what the harness asserts, and §8.2 still stands — **the 72 assertions
have still never been run.**

## Verification

- All five files re-run through `audit/tools/trace.py`. Master zero-read 3 (unchanged,
  the documented dormant three); EdgeCases 0; Visuals 2, both the documented `ta.dmi`
  tuple remainders.
- Declaration-before-use confirmed for every symbol in the ported Visuals block.
- A/B diff unchanged: same 5 hunk headers.
- No tabs, no dangling operators on any added line.
- Master, Strategy and OLDGATES **byte-identical to v4** — re-pasting them is optional.

Still **not compiled**.

---

# Build v5 → v6 — pre-compile checks, and F-A10 found

`Master` 5516 → 5527 · `Strategy` 4893 → 4904 · `OLDGATES` 4893 → 4904 · `EdgeCases` 286 → 292
`Visuals` unchanged. **All changes in this build are comments. No behaviour changes at all.**

## Two new checkers (`audit/tools/`)

`precheck.py` — balanced delimiters, indentation multiples of 4, no indent jumps > 4,
block openers followed by an indented body, no stray colon block syntax. **All five files
pass.**

`undeclared.py` — identifiers used but never bound, after excluding Pine's binding forms
(function params, tuple destructuring at any indent, `for` variables, `:=` targets),
named call arguments and `#RRGGBB` literals. **All five files: 0 unresolved.** That is the
error class the Master's own comments record hitting twice ("Undeclared identifier"), so a
clean result here is worth something — though it is still not a compiler.

## Token-ceiling risk was overstated — correction

I repeatedly warned that the Master was gaining lines against the 100,256 compiled-token
ceiling and that `_ctxLog` should be dropped first if it failed. Measured lexical tokens
against the audited v1 build:

| file | v1 | current | Δ |
|---|---:|---:|---:|
| Master | 41,973 | 42,119 | **+0.35 %** |
| Strategy / OLDGATES | 34,937 | 35,490 | +1.58 % |
| Visuals | 8,107 | 8,339 | +2.86 % |
| EdgeCases | 2,502 | 2,502 | 0 % |

Lexical tokens are not TradingView's compiled tokens, but the **delta** is the meaningful
signal and all the added code is straight-line global scope with no inlining multiplier.
**If v1 compiled, this build almost certainly does.** The earlier warnings were too strong.

## F-A10 — the D-001 timeout-cost fix does not bite

The §4.5 expression-drift check — verifying EdgeCases' transcribed expressions still match
the Master, not just their line numbers — turned this up.

The Master's D-001 note claims *"Cost now applies to all three outcome codes."*
`frAdj = fr - _costATR` does run for every analog, but for `oc == 0` the result is
**discarded**: `absFrAdj` is read only in the `oc == 1` / `oc == -1` branches and `_pnlPct`
is `0.0` on the timeout branch. Meanwhile `wt`/`mt` **do** count timeouts. So a timed-out
analog sits in the EV denominator contributing zero instead of the round trip it paid, and
analog EV stays optimistic — worst in chop and low-ADX, exactly where it should bind
hardest. **The original D-001 defect is still live and the comment was hiding it.**

**Not changed, deliberately.** Charging it correctly means expressing `_costATR` (ATR
units) as an R-multiple per analog, since `avgW`/`avgL` are R-multiples; mixing units
silently would be worse than a documented bias. `oEvVal` is display-only — the gating
quantity is `planExpectancy` — so nothing is gated on it meanwhile. Two options are set out
in the findings report; both are modelling decisions.

What did change: the false comment, in all three files, and EdgeCases group C, which now
records that C3/C5 still describe live behaviour but for a different reason than the
original defect.

---

# Build v6 → v7 — F-A10 fixed (R-unit conversion), and a units bug found doing it

`Master` 5527 → 5566 · `Strategy` 4904 → 4943 · `OLDGATES` 4904 → 4943 · `EdgeCases`/`Visuals` unchanged.

**This changes displayed statistics, and can move the drawdown breaker when it is enabled.**

## A larger defect surfaced while implementing the fix

`fr = array.get(hRet, i)`, and Q7.0 redefined `hRet` as **realised R**. But `_costATR`
divided cost by `adaptiveATR`, giving **ATR units**. So `frAdj = fr - _costATR` was
subtracting an ATR-unit quantity from an R-unit one — wrong whenever the SL multiple is
not 1.0, and `regSLMult` defaults to **1.5**. **Every cost-adjusted win and loss was
mis-scaled**, not only the timeouts. The units trap I warned about was already in the code.

## The fix, in four parts

1. **Units.** Cost is divided by the analog's own R unit (risk distance in points), putting
   `_costR` on the same scale as `fr`, `avgW`, `avgL`. `_oR` is local to the
   outcome-recording loop, so it is now persisted per analog in a new `hRUnit` array.
2. **Timeout charged.** A new accumulator sums each timed-out analog's **signed**
   cost-adjusted realised R. Signed, not magnitude — a timeout can end either side of
   entry and forcing a magnitude would fabricate a loss.
3. **Equity curve.** `_pnlPct`'s timeout branch was `0.0`, reproducing the defect in
   `_cumEq`/`_maxDD`. Now contributes like any other outcome. **Feeds `oMaxDD` →
   `_ddForBreaker`, so it can move the DD breaker when `useDDBreaker` is ON (defaults OFF).**
4. **EV.** `_cEvVal = (wr × avgW) − (lr × avgL) + (tr × avgT)`. Added, not subtracted,
   because `avgT` carries its own sign. The three terms now partition every analog.

**Expect analog EV to fall**, most in chop, compression and low-ADX where timeouts cluster.
That is the correction working.

## I made a real mistake here, and the checker missed it

The first attempt inserted the `else` branch **before** `else if oc == -1`, producing
`else` followed by `else if` — invalid Pine. `precheck.py` passed it.

Both are fixed: the branch is relocated, and `precheck.py` gained an else/else-if chain
check. It was then **verified against a re-created copy of the exact defect**, which it now
reports as `'else if' with no matching 'if'`. All five real files still pass.

## Verification

- `st` and `mr_` confirmed to see the same population — same loop iteration, same nesting,
  no intervening `continue` or `_isOos` guard — so `avgT = st / mr_` is sound.
- The fix lines are **byte-identical** across all three files.
- A/B diff unchanged: same 5 hunk headers.
- `precheck.py` and `undeclared.py` clean on all five files (0 unresolved).

Still **not compiled**.

---

# Build v7 → v8 — F-A11 (the mobile dashboard was never a mobile layout)

`Master` 5566 → 5596. **Master only** — the other four are unchanged, and the A/B diff is
untouched. Display layer only: no gate, score, probability or risk value changes.

## What a screenshot showed that static analysis could not

A phone screenshot of the live dashboard: every cell overflowing into its neighbour,
both edges clipped, `4406.46` rendering as `406.46`, `CHoCH—` running into `V 4373.17`
running into `(Y≈ R33 10Y`.

## What was actually wrong

- `_respCols := 9` and `_respRows := 4` set **unconditionally**, mobile or not.
- All nine columns written regardless of mode.
- `_mobUI` — the only thing "☰ Mobile Layout" drove — changed the font to `tiny` and moved
  the table's corner. **That was the entire mobile path.** Nine columns do not fit a phone
  at any font size; the toggle made the text smaller and the overlap worse.
- `dashMode` defaults to `"Auto"`, which resolves to `"Desktop"`. Pine cannot detect
  viewport size, so `Auto` was a promise the platform cannot keep — and the default.

## Fixed

`_dashMobile` drops the four **context** columns (STRUCTURE, LIQUIDITY, PRICE, MACRO) and
keeps the five that answer *what do I do*: MARKET, BIAS, SIGNAL, RISK, DECISION. Mobile
widths sum to exactly 100, weighted toward SIGNAL / RISK / DECISION. `_dashPort` also drops
the two dense sub-rows in portrait; landscape keeps them. A logical→physical column map
guards `tc`/`tcb` in **one place**, so all ~30 call sites are unchanged — returning −1 skips
the cell. The `Auto` tooltip now says plainly that Pine cannot detect screen size.

Nothing is lost: switch Dash Mode to Desktop for the full nine columns.

## Bounds invariant — checked, because this class only fails at runtime

Writing past the declared column count is a runtime error (the same class as the harness's
`"Row 70 is out of table bounds"`). Verified mechanically: logical columns written `{0..8}`;
kept `{0,1,2,7,8}` → physical `{0,1,2,3,4}`, max **4**, against `_respCols = 5` → valid
`0..4`. Confirmed the only two `table.cell(tblA, …)` sites are the guarded ones, so nothing
bypasses the map. `_respCols` and the map must stay in step — both comments say so.

## Not addressed

The price-axis label crowding also visible in the screenshot. Those are Visuals tag-registry
chart labels, which already do collision avoidance; a narrow viewport simply has too many.
Knobs: raise `tagGapATR`, lower `srCount` or `srMaxDistATR`, or disable `showTags` groups.
Changing those defaults would alter every chart, so it stays a user setting.

Also unverified: a literal `u00b7` appeared in the screenshot's DECISION column. That string
exists in **no committed version** of any file here, so it is either from a build predating
these artefacts or an artefact of the compressed image. Not claimed as a finding.

Still **not compiled**.

---

# Build v8 → v9 — F-A12, and the data-collection runbook

`Strategy` 4943 → 4952 · `OLDGATES` 4943 → 4952. Master, Visuals and EdgeCases unchanged.
A/B diff unchanged.

## F-A12 — the export was missing the one field that matters

Found by asking what would actually be *in* the file the operator sends back.

The code states the entry comment exists so a calibration test has a per-trade `prob`, gives
the format as `"TQ<n>|P<pct>"`, and correctly notes it **must precede the baseline run**
because alerts cannot backfill history. What it emitted was
`TQ<n>|CG<n>|B<n>V<n>|D<n>` — **no probability field at all.**

The cost of finding that after a run is a second complete backtest. Fixed now, before any
baseline: `|P<pct>` appended in both arms, carrying the **directional** probability
(`1 − p` for shorts) so a reliability curve is meaningful rather than inverted on every
short.

## `audit/RUNBOOK.md`

Step-by-step collection guide, ordered by value: the mintick gate that silently blocks all
entries on a mismatched feed, then compiling the Master (§8.1), running the 72 assertions
(§8.2), recording the run configuration, exporting the trades, the four-run design that
isolates one variable at a time, the forming-candle test, and sanity checks for the fixes.

It closes with what the data can and cannot establish, and the frozen-holdout path — the
only route to genuine calibration, since everything measured on the existing window is a
diagnostic rather than validation.

Still **not compiled**.

---

# Build v9 → v10 — F-A13: the first real compiler error

`Master` 5595 → 5606 · `Strategy` 4952 → 4963 · `OLDGATES` 4952 → 4963. A/B diff unchanged.

## It never compiled, and now that is a fact

The operator pasted and got, from all three files:

```
Error at 2815:168   Undeclared identifier "OUTCOME_N"     (Master)
Error at 2712:168   Undeclared identifier "OUTCOME_N"     (both twins)
```

`f_tradePlan()`'s `planReason` reads `OUTCOME_N`, which was declared **12 lines below the
function**. Present in the **originally audited v1 build** (used v1 L2767, declared v1
L2779), so **§8.1 is closed as fact: the Master had never compiled.**

The prior attempt at this bug is recorded in the file and was incomplete — it moved a
*different* block below the declaration, fixing that reader while leaving `f_tradePlan`
broken, since the function sits above either way.

**Fixed** by moving `tfSec` / `HIST_MAX` / `OUTCOME_N` **above** `f_tradePlan`.
`chartTFSeconds` (L686) is far earlier, so the block's own dependency is satisfied and
declaring earlier cannot break a later reader.

## New checker: `audit/tools/order.py`

`undeclared.py` asked only whether a name was bound *anywhere*. Pine enforces
**declaration before use** — a use inside a function may reach its params/locals or a
global declared before the **function definition line**.

Run against the broken build, `order.py` reported **exactly the compiler's three lines and
nothing else**. Now 0 violations across all five files.

Second checker gap this session, third false-confidence pass. These tools narrow the
search; they do not replace the compiler.

---

# Build v10 → v11 — build stamps (no code change)

All five files gain a header banner; `EdgeCases` also shows its build in the on-chart
table header. **No executable change in any file.**

## Why

The operator hit `Row 70 is out of table bounds` from `EdgeCases`. That is not a defect in
any build here: **every** version in this repo, including the originally audited v1, creates
the table with **100** rows. The chart was running an older copy — the error names 70 rows,
and the editor showed `plot()` at line 272 against 292 in the shipped build.

That is the exact risk `CLAUDE.md` names: pasting by hand across five scripts with no way to
tell, from TradingView, which build a given script is on. A stale script throws errors
already fixed, and the time goes into re-diagnosing a solved problem.

## The stamp

A banner directly under `//@version=6` reading **"this file last CHANGED in vN"**.

It moves **only when that file changes**, so an unchanged file keeps its old number and
still matches the record — which preserves the "which files changed" signal instead of
making every file differ on every build. Compare the banner against the record in chat: if
they differ, that script is stale.

`EdgeCases` additionally carries its build in the table's header cell (`§16 EDGE CASE v6`),
because that is the file that was stale and its table is the only thing on screen.

Verified: `//@version=6` remains line 1 in all five, the EdgeCases table is untouched at 100
rows, A/B diff unchanged at five hunk headers, all checkers clean.

---

# Build v11 → v12 — F-A15: calibration applied to the wrong variable

`Master` 5615→5644 · `Strategy` 4972→5001 · `OLDGATES` 4972→5001. Visuals and EdgeCases
unchanged. **This changes which trades fire.**

`hPred` stores `bullScore`, so the Platt fit maps `bullScore → P(bull resolution)`. The bear
branch fed `bearScore` into that same fitted map. A map fitted on one variable, evaluated on
another — and since the F-A02 wiring, that quantity **gates entries**.

Live 15M evidence: `L 31 / S 42 / R 26`, bear dominant, `BIAS BEAR-ISH`, plan `SHORT` — panel
printed `mP=73%`, reading bullish. Short directional probability computed 0.31 → VETO, where
using the fitted variable gives 0.87 → PASS. **Opposite decision on identical data.**

Fixed by evaluating the map on `bullScore` always; direction is applied at the gate, which
already handles it. Range-dominant branch kept at 0.5. `_pBear` gone — 0 executable
occurrences anywhere.

**Expect fewer longs and more shorts than v10.** That is the correction. `useCalGate = false`
reverts.

F-A16 recorded and left open: the bull fit's denominator includes timeouts, so the short's
complement covers "bear OR timeout" and is optimistic by the timeout rate. Fixing it needs a
bear-outcome calibration that does not exist.

---

# Build v12 → v13 — F-A14: the rolling win rate's ±x% interval suppressed

`Master` 5645 → 5652 (by `wc -l`). Strategy, OLDGATES, Visuals and EdgeCases unchanged.
**Display only — no trading behaviour changes.**

F-037 suppressed `oOosCI` because a ±x% interval implies a fixed independent holdout, and
the win-rate population here is rolling. A second interval, `wrCIStr`, still put that claim
on the dashboard as `WR 74%+/-4%`, over the same rolling `oMatch` population.

The risk cell now reads `WR 74% ROLL …`. `wrCIStr` is still computed, unchanged, and is
deliberately write-only with an F-A14 annotation, matching how `oOosCI` is handled, so it
can be restored once a frozen holdout exists. Two header comments that said the interval was
displayed are corrected.

The twins have no dashboard and their `wrCIStr` was already unread, so they are not
touched. A/B diff unchanged at five hunk headers. All checkers clean. **Compile NOT RUN.**

---

# Build v13 → v14 — the probability layer made coherent (F-A16 … F-A20)

`Master` 5652 → 5850 · `Strategy` / `OLDGATES` 5002 → 5200 (identical edits, A/B diff
still five hunk headers) · `EdgeCases` 301 → 343 · Visuals unchanged.
**This changes which trades fire.** `SCHEMA_BUILD` 2 → 3; never pool B2 and B3 exports.

| ID | What was wrong | Fix |
|---|---|---|
| F-A19 (P0) | The veto used `pTP1 − pSLhit`, a difference of marginal touch rates, as if it were an expectancy. Under a fair game it reads −0.27…−0.46 at RR 2–3 | Race expectancy from a first-touch label, with timeouts at horizon mark-to-market, net of cost |
| F-A17 (P1) | Touch probabilities were read from a 1.5×ATR-unit histogram using plan-stop-unit distances; SL was always the 1-unit rate | Converted to the histogram's unit; SL on the adverse ladder; 0-anchor on the grid |
| F-A16 (P2) | A short used 1 − P(bull), i.e. "bear or timeout" | Bear Platt fit; gate on P(win \| resolved) from each direction's own fit |
| F-A18 (P2) | The regime multiplier could push the probability to 1.175 | Clamped to [0.05, 0.95] |
| F-A20 | EdgeCases C3/C5 asserted pre-v7 behaviour and passed | Corrected; citations re-derived; GROUP K (+20 assertions, 92 total) |
| P2 | Cold-start slope derived from an accuracy grade | Identity map, `mP unfit` |
| P2 | Two effective-N methods | `N / OUTCOME_N` throughout |

**Nothing tuned.** No existing threshold, weight or lookback changed value. The bear fit
mirrors the bull fit's bounds, the gate stays at 0.50 (now the correct boundary, because
the probability is conditional), and the 0.7 taper is the existing one.

**Expected on the chart.**
- Fewer spurious vetoes on setups with RR ≥ 2 (the old quantity penalised them).
- More vetoes where costs are large relative to the stop (cost is now inside E[R]).
- On ≥30M charts the gate stops blocking by the timeout rate once both maps fit.
- Plan panel shows `EVrace`; SIGNAL cell shows `mP=L/S%` or `mP unfit`.

**Verification.** precheck / undeclared / order clean; manifest updated;
`audit/tools/race_model_check.py` PASS on two seeds (tests the maths, not the Pine).
**Compile NOT RUN. Harness NOT RUN. Backtest NOT RUN.**

**Token budget.** About +90 executable lines across the probability layer. The compiled
token count is still unmeasured (`CONCURRENCY_AND_MIGRATION.md` B4). If TradingView
reports a ceiling problem on save, follow B5 of that file; do not split the engine.

---

# Build v14 → v15 — first compile results acted on

The operator's first v14 run established three facts:

1. **The Master failed on tokens: 100,627 against a 100,256 limit.** The v14 additions
   (+1,444 lexical tokens) are what crossed it. Both strategy twins and Visuals **compiled
   and ran**, and they carry the same v14 engine code. So the v14 logic compiles, and the
   Master's only error was size.
2. **OANDA:XAUUSD has mintick 0.001.** The P0-CAL-005 gate therefore blocked every
   strategy entry, correctly.
3. **EdgeCases compiled and ran: 3 FAIL / 92.** The failing rows were not legible in the
   screenshot. **NOT diagnosed yet.**

**Master** 5850 → 5726. Executed step 1 of `CONCURRENCY_AND_MIGRATION.md` B5: removed the
three default-OFF diagnostics (forecast cone, V1/V2 schema shadow audit, rolling
reliability readout) and their inputs. None fed a decision. −1,010 lexical tokens, an
estimated ~98,100 compiled. **Estimate; the save reports the real figure.**
My first pass also claimed the reliability string was never rendered. It is rendered
(inside `crossCheck`); `undeclared.py` caught the dangling reference, and the claim was
withdrawn before commit.

**Strategy / OLDGATES** (identical, A/B diff still five hunk headers): P0-CAL-006. Costs
are now charged as cash per contract (`commission_value 0.385`, `slippage 0`), so tick
size doesn't matter. The gate now checks `pointvalue == 1` and `currency == USD`. Accepted
residual: TP-limit fills are charged up to 0.35 pts/oz more than TradingView's slippage
model would (conservative).

**EdgeCases**: all Master citations re-derived against v15; header now `v15`. No assertion changed.

**Nothing tuned.** Compile of v15 NOT RUN.

---

# Build v15 → v16 — end-to-end wiring and formula compliance (F-A21 … F-A26)

`Master` 5726 → 5698 · `Strategy` / `OLDGATES` 5214 → 4735 (identical; A/B diff still five
hunk headers) · `EdgeCases` 343 → 367 (97 assertions) · Visuals unchanged.
**Changes which trades fire** (F-A22, F-A24). `SCHEMA_BUILD` 3 → 4.

- **Wiring:** `deadcode.py` reports 0 dead symbols in all five files. Removed: the what-if
  scenario engine (never read), unread and self-only accumulators, the write-only
  `hDataStatus` buffer, two engine outputs no file used, the two inputs v15 orphaned, and
  the twins' dashboard remnants (dead in *both* arms only). Two dormant ±x% intervals
  (F-037/F-A14) are no longer computed; their formulas are kept verbatim in comments.
- **Formulas:** Cornish-Fisher inverted (F-A22); Kelly with timeouts and in the plan's
  direction (F-A23); Berkson-weighted Platt fits (F-A24); exact Brier decomposition
  (F-A25); t-quantile expansion order (F-A26). `formula_check.py` PASS.
- **EdgeCases:** citations re-derived and verified line by line against v16; GROUP L adds
  5 assertions for the corrected formulas.
- **Token estimate:** Master 39,224 lexical tokens (≈96,700 compiled at the measured 2.466
  ratio, ~3.5% headroom). An estimate until the save reports it.

**Nothing tuned.** Compile of v16 NOT RUN. EdgeCases' 3 v14 failures still undiagnosed
(screenshot not legible).

---

# Build v16 → v17 — no feature deleted: Diagnostics companion

New sixth artefact `XAUUSD_Quantum_5_0_Diagnostics.pine`: the Treatment engine verbatim plus
a panel showing the six features v15/v16 took out of the Master (cone, V1/V2 shadow,
reliability buckets, rolling intervals, what-if scores, data-source census). Two of them
were never visible before and are now wired. Master, twins, Visuals and EdgeCases are
**unchanged**. New `audit/tools/diag_parity.py` enforces engine identity. deadcode: 0 dead.
Details in `FINDINGS_TRACEABILITY.md` ("v17"). Compile of Diagnostics NOT RUN.

---

# Build v17 → v18 — removed non-features restored

Operator instruction: restore the removed non-features too.
- **Strategy / OLDGATES** 4735 → 5244: v15 text restored in full (dashboard remnants, request
  tuple slots, complements, `calBrier`, scenario factors), plus exactly v16's formula
  corrections (blocks byte-identical to the Master's). A/B diff: five hunk headers.
- **Master** +14 lines: `calBrier` and the two complements with their engine outputs and
  tuple slots, back in their v15 positions. Tuples identical to v15. ~39,349 lexical tokens,
  an estimated ~97,040 compiled.
- **Diagnostics** rebuilt on the restored engine. Panel names are `dg`-prefixed where the
  engine now declares the same name; the census reads the engine's own `hDataStatus`. No
  duplicate globals (checked). `diag_parity.py` PASS.
- **EdgeCases** citations re-mapped through the diff and verified line by line.

**No output changes**: every restored line is unread. `SCHEMA_BUILD` stays 4. Compile NOT RUN.

---

# Build v18 → v19 — pre-paste compile recheck

New `audit/tools/pinelimits.py` covers compile-error classes the other checkers miss:
- G1: a function modifying a global.
- G2: a duplicate declaration in one scope.
- G3: tuple arity.
- G4: a float array index.
- G6: `bool = na`.
- G8: an indicator with no output call.
- It also reports variables per scope and request sites.

Each rule was proven on injected errors and calibrated on a build that ran on the chart (v14 twin: 0 issues).

**It found a real error:** the v17/v18 Diagnostics script had **no output function call**, which TradingView
rejects ("Script must have at least one output function call"). Fixed with a hidden
`plot(na)`, as in EdgeCases. Also checked clean in all six files: no tabs, non-breaking
spaces, nested functions, table bounds or loop bounds.

Token estimates for every script; only the Master is tight (~97,000). A traced Master →
Visuals contingency is recorded in `CONCURRENCY_AND_MIGRATION.md` B5a, to use only if the
save reports an overflow. Only Diagnostics changed. Compile NOT RUN.

---

# Build v19 → v20 — first full chart run acted on (F-A27 … F-A29)

**Confirmed on the chart:** all six compile. The Master is under the token limit, so no
Visuals move is needed. The arms show only `barstate.islast` warnings, which are harmless.
- **F-A29 (P0):** 0 trades in both arms, because `recentBars` confined entries to the last
  120 bars. Now switchable with *Backtest all bars*, default ON in both arms (identical; A/B
  diff still five hunk headers).
- **F-A28:** bearish-bias WR showed 1 − P(bull); now the bear rate (Master, arms,
  Diagnostics).
- **F-A27:** EdgeCases A3/A6 expectations corrected; failures render first; text size input.
- **Diagnostics:** gate funnel (bars → trend → HTF → session/news/DD/recent → trigger →
  vetoes → PASS).

The strategy arms will now trade history. Compile of v20 NOT RUN.

---

# Build v20 → v21 — decision, alerts, chart parity, full wiring (F-A30, F-A31)

- **F-A30 (P0):** OB / FVG / displacement / SMT / climax detection is on by default as engine
  inputs (Master and both arms, identically). The decision now sees the zones Visuals
  draws. **Changes which trades fire**; `SCHEMA_BUILD` 5.
- **F-A31:** alerts are confirmed-bar only and MT5-ready: plan with MT5 prices, P, EV. New:
  decision-change, tracked SL/TP1, risk-lock alerts. BOS alerts on by default.
- **Wiring:** every retained name is wired (see FINDINGS). The Diagnostics panel gains a
  dashboard mirror, an MT5 plan table, cross-check rows and an engine-zones overlay; the
  twins' dashboard builder matches the Master's.
- **Parity verified:** NY day roll (PDH/PDL) identical in Master and Visuals; OB and FVG
  definitions identical.
- **Estimates:** Master ~97,700, Diagnostics ~94,200, twins ~85,900. Compile NOT RUN.

---

# Build v21 → v22 — real-volume check within a free TradingView plan

Operator request: "actual" volume, liquidity and order-block data via free API keys.
- Pine cannot make web requests, so there is no API or key route.
- Order blocks and liquidity are price-derived patterns, not a data feed.
- The only real volume reachable on a free plan is COMEX GC1!: delayed ~10 min, and
  already loading on the operator's chart (Diagnostics showed GC 98%).

**Diagnostics** gains a *Volume (free plan)* row:
- the 100-bar correlation between OANDA tick volume and COMEX GC1! volume (both previous
  bar, so both complete despite the delay);
- whether the previous bar's displacement was backed by real COMEX volume expansion.

It is display only; no engine, gate or Master change. Compile NOT RUN.

---

# Build v22 → v23 — MobileBrief phone card (Master only)

New Dash Mode option **MobileBrief**: a 4-row card (TREND, TARGET, PREV → NEXT, DECISION) in
place of the dashboard and plan strip. It uses only values the engine already computes: bias,
regime, HTF bias, liquidity destination (MT5 price), structure event, calibrated 1R
probabilities, race EV, the confirmed decision and the MT5 plan. Every other mode is
unchanged; no feature is removed; no decision logic touched.

Master estimate ~98,850 compiled (~1.4% headroom), the tightest yet. If the save overflows,
apply `CONCURRENCY_AND_MIGRATION.md` B5a. Compile NOT RUN.

---

# Build v23 → v24 — act on the v21–v23 chart run (Master token ceiling, Diagnostics warnings)

**Measured on the operator's chart (2026-09-27):**

| Script | Result |
|---|---|
| Master v23 | **`Compiled code contains too many tokens: 100820. The limit is 100256`** |
| Treatment / Control twins (v21) | Compiled. Two warnings each: `barstate.islast` without `calc_on_every_tick` (L1936 volume-profile refresh, L5185 cost-model warning label). Both benign: the twins run on bar close, where `islast` and `isconfirmed` are both true. |
| Diagnostics v22 | Compiled. Warnings: `ta.correlation` inside a ternary (L5453), `_v` shadows a global (L5292). |
| Visuals | Compiled. |
| EdgeCases | "3 FAIL / 97", rows in natural order and no `v21` header, so the chart was still running a pre-v21 copy (the editor showed the v21 code as **Unsaved version**). |

**F-A32, Master over the ceiling.** v23 is 40,081 lexical tokens, so the true ratio is
**2.515** compiled per lexical, not the 2.466 measured on v14; the estimate (~98,850) was
~2,000 low. **Fix:** the Q5.3/Q5.4 auction layer (`f_auctionIntel` and `aucBias`) moves to
Diagnostics, which already runs the identical function on the Treatment engine. A block-level
backward slice from every `alert`, `alertcondition` and `plot` showed that nothing in it feeds a
gate, alert, plot or plan value. Moved, not deleted:
- Diagnostics' "Auction" row is now shown in Standard density too (auction read only);
  Spacious adds the full cross-check prefix, as before.
- `climaxUp` / `climaxDown` fed only the auction layer in the Master. They are now shown as
  `CLIMAX▲/▼` on the dashboard cross-check line (`xcheckStr`, formerly `auctionStr`).

Master: 40,081 → 38,759 lexical. At the measured 2.515 that is **~97,480 compiled (~2.8%
headroom)**. Even at 2.548, the highest ratio consistent with v20 compiling, it is ~98,760.

**F-A33, Diagnostics warnings.**
- `ta.correlation` was called only on bars where `gcValid`, so its 100-bar window skipped the
  other bars. It now runs every bar, and the ternary only chooses what to display.
- The census loop's `_v` is renamed `_dsv`; there is no behaviour change.
- The generator is now committed as `audit/tools/build_diag.py`.

**Observed, not fixed (F-A34, `STAT`).** From Diagnostics' reliability rows:
- The raw-score buckets predicted 21/29/34/41/54% but observed 18/24/18/22/19% (n 439–632 each).
- The score has **no resolution** on this history.
- The Treatment backtest agrees: 90 trades, PF 0.989, −$9.55 at 1 oz.
- Control: 12 trades, PF 1.72, +$60.58. That is too few trades to tell apart from zero.

Nothing is tuned in response (§9); the remedy is a frozen holdout.

Unchanged: Strategy, Strategy_OLDGATES, EdgeCases, Visuals. Compile of v24 NOT RUN.

---

# Build v24 → v25 — one Mobile mode (Master only)

Operator request: merge the phone views into one without losing any feature.
- **Dash Mode** options are now `Auto / Desktop / Tablet / Mobile`. `MobileLand`,
  `MobilePort` and `MobileBrief` are merged into `Mobile`, and *☰ Mobile Layout* = `Mobile`.
- The card keeps the four MobileBrief headlines. Each section gains a detail row made of the
  desktop cells' **own strings**: the renderer names them and hands them over in `gDashS`
  slots 25–34, so nothing is recomputed. The detail rows carry everything MobileLand showed
  (MARKET, BIAS, SIGNAL, RISK, DECISION) plus the LIQUIDITY and MACRO columns it dropped.
- The DECISION headline is now the desktop DECISION box (grade, TQ, bias + block reason,
  LIVE tag), not the bare label.
- The trade plan is written **into the card** (rows 8–15) rather than a second table, so the
  two cannot overlap on a phone.
- Density: `Compact` shows the headlines only (the old MobileBrief); `Standard` adds the
  details and the plan; `Spacious` adds the engine cross-check line.
- Removed as layout plumbing, not features: the 5-column map `_dCol`, the portrait row cut
  `_dashPort`, the mobile widths and size ladder, and `_respRows/_respCols`.
- Desktop and Tablet output is unchanged: the same cells, positions, sizes and widths.

Master 38,759 → 38,918 lexical, ~97,880 compiled at 2.515 (~2.4% headroom). Twins and
Diagnostics are untouched: their layout inputs only size the Diagnostics panel. Compile NOT RUN.

---

# Build v25 → v26 — engine sequence audit (Master only)

A new tool, `audit/tools/sequence.py`, lists every read of a value that runs before a later
write of it on the same bar. Of 65 hits in the Master, one was a real defect (F-A35):
- `biasLabel`, and the WAIT reason beside it, were computed from the evidence-stage scores.
- They were displayed beside the final (blended, forecast, normalised) scores, and also used
  in the BUY/SELL alert text.
- Both now run after the final stage. The formula and thresholds are unchanged, and no gate
  reads either.

**Visible change:** the BIAS word on the DECISION box, the Mobile TREND row and in alerts now
always agrees with the B/S numbers shown next to it.

Also verified: the plan's SL/TP geometry against a $10–20 target. On 1H (ATR ≈ $16) the SL is
about $10–25 and TP1 about $10–20. Twins and Diagnostics are unchanged. Compile NOT RUN.

---

# Build v26 → v27 — missed-move audit (Diagnostics only)

Operator report: DECISION "mostly remained WAIT although the market moved 30 to 50 dollars".
Diagnosed as F-A36 from the operator's own gate funnel:
- the chain passes 1.5% of bars;
- the trigger stage (structure break or displacement) removes 86% of eligible bars;
- the vetoes remove two thirds of what is left.

Not tuned (§9): the trades the chain takes already break even (F-A34).

New Diagnostics row **Missed moves**: move episodes of at least 30 (input) within 12 bars
(input), each tallied at the furthest gate the entry chain reached in that direction.
- It is DIAG-fenced and reads only existing values; `diag_parity` passes.
- Diagnostics ~38,810 lexical, ~97,600 compiled at 2.515.
- Master, twins, EdgeCases and Visuals are unchanged. Compile NOT RUN.

---

# Build v27 → v28 — review of the first v24–v27 chart run

**Measured on the operator's chart (2026-09-27, 1H):**
- **Compile:** all six scripts compiled and were added to the chart, including the Master
  (v26) that overflowed at v23. This closes F-A32. Its real token count is not reported on a
  successful save.
- **Master dashboard:** BIAS MIXED (L34 / S37 / R27) and DECISION `WAIT TQ34D`, with
  `BIAS BEAR-ISH · SESS 13/30`. The label agrees with the final scores (the v26 fix).
  - The WAIT reason is the session (weekend, market closed).
  - Plan: SHORT, SL hit ~40% vs TP1 ~13%, race EV −0.01R, Kelly 0% → 0.00 lots.
  - Consistent with F-A34.
- **Diagnostics v27:** all rows render. Auction (Standard density) and Missed moves are
  populated, and the Missed-moves stages sum to their episode count. The numbers are in
  F-A36: the trend filter, not the vetoes, is where 60% of $30+ moves stop.
- **Strategy arms at 10K:**
  - Treatment: 86 trades, 39.5% winners, PF 0.957, −$39.57, max DD $479.95.
  - Control: 12 trades, PF 1.718, +$60.58.
  - Treatment was 90 trades / PF 0.989 at 25K. No gate reads capital (`_ddBreach` is OFF by
    default and reads the analog drawdown), so the difference is unexplained.
  - Other Properties settings, or the loaded history, are the candidates. Operator asked for
    the Properties tab.
- **EdgeCases:** `1 FAIL / 97` with failing rows first, so the harness is now saved at v21.
  The failing row is unreadable in both screenshots.

**Change (EdgeCases only):** the red header cell now reads `N FAIL / 97 · <id> got <x> want
<y>` for the first failure. It changes no assertion. Master, Diagnostics, the twins and
Visuals are unchanged. Compile NOT RUN.

---

# Build v28 → v29 — EdgeCases I7 corrected from the chart (F-A37)

The operator's photo of the v21 harness shows the one failure:
- test: `I7  safeDiv near-zero NOT guarded`;
- got `false`, want `true`, class NUM.

96 of 97 passed.

**Cause: the assertion, not the engine.**
- I7 assumed IEEE equality: that `b == 0` lets b = 1e-12 through, so 10 / 1e-12 ≈ 1e13
  "explodes".
- Pine returned 0 from that guard, so its float `==` treated 1e-12 as equal to 0.
- The harness had asserted a premise that was never executed in Pine (FORENSIC_AUDIT_Q5
  §351 already said so).
- The engine's `safeDiv` uses `abs(b) > 1e-10` and is unaffected either way.

**Change:**
- I7 now asserts the measured result.
- Two new tests check the explanation:
  - I9 `1e-12 == 0.0` → true (tolerant equality);
  - I10 `1e-12 > 0.0` → true (the literal is not read as zero).
- If either fails, the explanation is wrong and I7 is reopened.
- Now 99 assertions + header = 100 rows, exactly the table's capacity; the `_row <= 99` guard
  holds. A 100th assertion needs a larger table.

Only EdgeCases changed. Compile NOT RUN.

---

# Build v29 → v30 — EdgeCases I10 made discriminating

Chart run of v29 (operator photo, 2026-09-27): `1 FAIL / 99 · I10 got false want true`.
- I7 PASS: the `== 0` guard catches 1e-12.
- I9 PASS: `1e-12 == 0.0` is true.
- I10 FAIL: `1e-12 > 0.0` is false.

Two explanations fit: Pine reads the literal `1e-12` as 0, or `>` is tolerant as well as `==`.
With the table full (99 + header = 100 rows), I10 is replaced by `1e-12 * 1e12`: "1" means
the literal is kept, so comparisons are tolerant; "0" means the literal is read as zero.

**Engine relevance, pending that answer:**
- If the literal is read as zero, `safeDiv`'s `abs(b) > 1e-10` (Master L278, and the engine
  copies) degrades to `abs(b) > 0`. The fix would then be a decimal-form constant.
- The Platt variance floors (`> 1e-6`) are also bounded by the slope clamps, and F8
  ("near-zero variance rejected") PASSED on the chart.
- No engine change until measured.

Only EdgeCases changed. Compile NOT RUN.

**Result (operator photo, 2026-09-27): `ALL PASS 99`.**
- `1e-12 * 1e12` = 1, so Pine keeps the literal, and its `==` and `>` compare with a
  tolerance.
- Engine consequence: none. `safeDiv`'s guard stays as it is.
- This is the first complete executed pass of the harness: §8.2 is closed by execution, not
  by assumption.
- No artefact changed after v30.

---

# Build v30 → v31 — forward test pre-registered; Challenger arm; forward-test workbook

Operator request: "what can we do to achieve 100/100" → both the log and the challenger.

- **`audit/PREREGISTRATION.md`** fixes, before any holdout data exists:
  - the holdout start (2026-09-28 00:00 UTC) and the frozen SHA-256 of the Master,
    Treatment, Control and Challenger;
  - the metrics;
  - the decision rules: N ≥ 50, the 95% t-interval of the mean above 0, and PF ≥ 1.2;
  - the Challenger adoption rule;
  - the decision date, 2027-03-31.
- **`Strategy_CHALLENGER.pine`** (new artefact, H1): identical to Treatment except the entry
  trend gate.
  - The gate becomes `close > EMA20 and EMA20 > EMA20[3]`, mirrored for shorts. These are
    the fast terms of the existing trend score; no new parameter or threshold is added.
  - Motivated by F-A36: 60% of $30+ move episodes stop at the trend gate.
  - Diff vs Treatment: 4 hunks (stamp, title, role, gate).
  - About 34,860 lexical tokens, ~87,700 compiled.
  - All checkers clean; 0 dead.
- **`audit/XAUUSD_Forward_Test_Log.xlsx`** has four sheets: Read Me with the pre-registered
  settings, Live Log (R), Arm Trades ($ at 1 oz) and Stats. Stats reports:
  - N, win rate with Wilson interval, mean R with t-interval, profit factor;
  - max drawdown in R;
  - the dashboard's TP1 % against the realised rate;
  - the verdicts and the Challenger decision.
- **Workbook checks:**
  - 11,046 formulas, 0 errors on LibreOffice recalculation.
  - Filled with 60 synthetic live trades and 3 × 55 arm trades: all 26 statistics match an
    independent Python calculation.
  - The pre-freeze example rows are excluded, as designed.
- The Master, twins, Diagnostics, EdgeCases and Visuals are unchanged. Compile of the
  Challenger NOT RUN.

**Chart result (operator screenshot, 2026-09-27 14:35 UTC+5):**
- The Challenger saved, compiled and was added to the chart. Its only warning is the benign
  `barstate.islast` one at L5196, the same as the twins' (F-A33 note).
- Compile: PASS by execution.
- The first report frame, still marked "Updating report", showed figures identical to the
  Treatment's (86 trades, PF 0.957, −$39.57). This is presumed to be a stale frame and
  awaits a settled screenshot: identical settled figures would mean the H1 gate is not
  taking effect.

**Chart result (operator screenshots, 2026-09-29, 15M chart, tester range 2026-07-01 → 09-29):**
- **H1 gate confirmed live.** At identical settings:
  - Challenger: +$66.09, PF 1.516, max DD $59.08, 15/34 winners.
  - Treatment: +$71.74, PF 1.539, max DD $56.91, 15/34 winners.
  - Different P&L means different trades, so the stale-frame concern above is closed.
- **Protocol deviation:** the screenshots are on **15M**; PREREGISTRATION §2 registers 1H.
  - The operator was advised to return to 1H.
  - A switch to 15M would be a documented amendment, with the holdout clock restarted at
    that moment. It must not be judged on the 15M history already seen (Jul–Sep, PF ~1.5).
- **Diagnostics on 15M (v27):** the same picture as 1H.
  - Missed moves: up 148 / down 168, ENTRY 7; stopped at trend 183 (58%), HTF 49,
    sess/news/DD 26, trigger 44, TQ 5, EV 1, P 1.
  - Reliability buckets: predicted 22/30/36/42/54%, observed 19/29/25/18/15%. There is no
    resolution; the top bucket is the worst (F-A34 holds on 15M).
- **EdgeCases:** ALL PASS 99 (saved v30 confirmed).
- **Master DECISION box:** `WAIT TQ49D · BIAS BEAR-ISH · TREND 50/60`. The block reason
  names the trend gate, consistent with F-A36.

---

# Build v31 → v32 — formulas executed as written; F-A38, F-A39; Diagnostics probes

Operator request: re-verify every value and calculation with the best available maths and
statistics.

- **New tools.** `pine_exec.py` runs Pine source lines in Python. `formula_trace.py` uses it
  to execute 9 probability and statistics blocks from each engine copy against first-principles
  references.
  - 7 PASS.
  - 2 defects, identical in the Master, Treatment, Control, Challenger and Diagnostics:
    **F-A38** (calibration fit) and **F-A39** (Cornish-Fisher domain). See FINDINGS.
- **Fix prepared, not applied:** `audit/tools/pending_fix_v33.py`.
  - It changes signals, so applying it restarts the forward test; operator decision pending.
  - Patched copies pass 10/10 blocks.
- **Diagnostics v32** (display-only, not a frozen file) adds a *Math probes* row:
  - daily `close[1]` historical lag;
  - Cornish-Fisher out-of-domain count and max |z|;
  - the calibration fit in use.
  - About 39,170 lexical tokens, ~98,500 compiled. It is the closest file to the limit; if the
    save overflows, the probe row is the first to trim.
- The Master, the three strategy arms, EdgeCases and Visuals are unchanged, so the holdout is
  intact. Compile of Diagnostics v32 NOT RUN.

---

# Build v32 → v33 — F-A38 and F-A39 fixed; forward test restarted on 15M (amendment A1)

The operator decided (2026-10-02) to apply the fixes now and to restart the test on 15M.

- **F-A38 (calibration)**, in the Master, Treatment, Control, Challenger and Diagnostics: the
  Platt/WLS fit is now a constrained least-squares fit.
  - The slope is projected onto [0, 0.25], or [−0.25, 0] for the bear fit; 0 means the
    weighted base rate.
  - The fit updates on every refresh, so no stale fit survives.
  - The 0.02 floor is gone.
  - The intercept is re-solved for the slope used.
  - The intercept limit is a ±5 numerical guard, replacing the ±1 clamp.
- **F-A39 (Cornish-Fisher)**, same files: the inverse is applied only inside the monotone
  (Maillard) domain; elsewhere the observed z is used.
- **Verification:**
  - `formula_trace.py`: every block passes in all five engine copies (8/10 before).
  - `formula_check.py` and `race_model_check.py` pass.
  - `sequence.py`: no early reads of the changed symbols.
  - Treatment vs Control: 5 hunks. Treatment vs Challenger: 4. `diag_parity` passes.
- **EdgeCases v33:**
  - The F group (11 assertions) and K19 are rewritten to the constrained fit; K20 is
    unchanged.
  - All 13 were executed through `pine_exec.py` with 0 mismatches; still 99 assertions.
- **Diagnostics v33:** the regenerated engine plus the v32 *Math probes* row.
- **PREREGISTRATION amendment A1:**
  - holdout start 2026-10-05 00:00 UTC;
  - 15M chart;
  - new frozen hashes;
  - disclosure that 15M history (Jul–Sep 2026) was seen before the switch;
  - v31 holdout void, with no trades logged.
  - The workbook's freeze date is updated; 0 errors on recalculation.
- **What visibly changes:**
  - `mP=` and the plan's calibrated probabilities move toward the base rates (about 20–25%)
    when the bins show no resolution.
  - The calibration gate then acts by the bull vs bear base rates rather than by the score.
  - On bars outside the Cornish-Fisher domain, the mean-reversion evidence is no longer
    pinned at ±100.
- Tokens:
  - Master ~38,970 lexical, ~98,000 compiled (2.3% headroom).
  - Diagnostics ~39,210 lexical, ~98,600 compiled; tightest, and the first to trim if a save
    overflows.
  - Compile NOT RUN for the six changed files.

---

# Build v33 → v34 — records inside TradingView; 5M/15M consistency (F-A40); amendment A2

Operator request: keep the required information in TradingView, readable from each file's
result, and make the system right on both 5M and 15M, which the operator watches together.

- **F-A40 (5M/15M review).** Layers at or below the chart timeframe score a neutral 50, so they
  never vote, yet MTF confluence (it feeds trade quality) divided by a fixed 10 and MTF
  confidence by a fixed 5.
  - The maximum score was 9/10 on 5M, 8/10 on 15M and 7/10 on 1H, so the same market scored
    lower on 15M than on 5M.
  - Now normalised by the votes available on the chart. It is identical wherever all layers
    vote (1M).
  - Applied to the Master, all arms and Diagnostics (`fix_v34.py`).
  - New `formula_trace` check: 1M/5M/15M/1H/4H × 300 cases, exact.
  - The HTF *gate* (≥ 2 opposed among the layers above the chart) was reviewed and left as is:
    a layer at the chart's own timeframe is not a higher timeframe.
- **On-chart FORWARD TEST scorecard**, identical in Treatment, Control and Challenger
  (display only):
  - It shows positions since the start, wins, mean $, a 95% t-interval (Fisher expansion,
    error < 0.004 at df ≥ 9 vs the exact t), PF, net $, the pre-registered verdict, the
    timeframe check and coverage.
  - Unit = position: partial exits are summed, and open positions are excluded.
  - The counting logic was executed through `pine_exec.py` on 400 random trade lists (partial
    exits, a half-open position, pre-start trades): 0 mismatches.
- **Workbook:**
  - a **TV Snapshots** sheet, the weekly copy of each card and the permanent record;
  - an Arm Trades note: one row per position;
  - 0 errors on recalculation.
- **PREREGISTRATION A2:**
  - F-A40 and the scorecard, made before the start;
  - unit = position;
  - 15M registered, 5M for timing only;
  - new hashes. Start date, rules and decision date unchanged.
- **Checks:**
  - precheck, undeclared, order, deadcode and pinelimits: 7/7 each (`undeclared.py` learned
    the builtin `timestamp`).
  - Treatment vs Control: 5 hunks. Treatment vs Challenger: 4. `diag_parity` passes.
  - `formula_trace`: all PASS in every engine copy. `sequence`: clean.
- **Visible:**
  - a FORWARD TEST card in each arm, bottom right by default. On 5M it says "NOT 15M: does not
    count".
  - Trade-quality and MTF-agreement readings are slightly higher on 15M and 1H than before,
    because they are no longer capped by the timeframe.
- Tokens:
  - Master ~39,020 lexical, ~98,100 compiled (2.1% headroom).
  - Arms ~35,800 lexical, ~90,000 compiled.
  - Diagnostics ~39,270 lexical, ~98,800 compiled; tightest.
  - Compile NOT RUN.

---

# Build v34 → v35 — validation pass; scorecard verdict edge case

Operator request: review and validate.
- Full pass on v34 found everything clean except one display defect:
  - manifest 7/7, frozen hashes, all checkers 7/7, `diag_parity`;
  - A/B 5 hunks, T/C 4;
  - `formula_trace` PASS in every engine copy; `formula_check` and `race_model_check` PASS;
  - the scorecard identical in the three arms, with no shadowed names.
- **Defect:** the scorecard verdict marked a record with N ≥ 50 and no losing position as NOT
  SHOWN, because PF is na there.
  - Fixed identically in the three arms: no losses means PF = ∞, which passes the PF rule.
  - The Profit factor row says "no losses yet (infinite)".
  - Display only (PREREGISTRATION A2.5).
  - Executed: all-win → EDGE SHOWN, edge → EDGE SHOWN, no edge → NOT SHOWN, N 20 →
    COLLECTING 20/50.
- The Master, Diagnostics, EdgeCases and Visuals are unchanged. Compile NOT RUN.

---

# Build v35 → v36 — H2 sweep-to-value arm (operator's signal specification)

Operator request: a signal from the volume profile, market trend, liquidity sweep, swing
highs/lows and the next movement of the market.

**Why a new arm, not a change to the Master.** That is a different trading idea. It is
pre-registered as **H2** (amendment A3), before the 2026-10-05 start, and runs beside the
frozen arms, so the forward test can tell whether it is better.

- **H2 rule:**
  - trend ≥ 2 of the 1H/4H/1D HTF trend scores (the engine's scoring);
  - the last unconsumed 5-bar swing;
  - a sweep = trade-through and close back;
  - the engine's volume profile (100 × 40, POC, 70% value area) rebuilt every confirmed bar;
  - long ≤ POC / short ≥ POC;
  - SL at the wick ± 0.15 ATR (risk 0.5–5 ATR), TP1 = max(POC, 1R), TP2 = max(VAH, 2R);
  - every value borrowed from the existing system, none fitted.
- **Files:**
  - `Strategy_H2.pine` (new, ~2,290 lexical tokens): the H2 block, plus the Treatment's
    execution layer, cost model and scorecard, verbatim apart from the signal and levels.
  - Visuals: the same H2 block, "H2" chart markers, an H2 card (trend, unswept swings,
    VAL/POC/VAH, last sweep, next movement, last signal at MT5 prices), and an H2 alert. About
    8,940 lexical tokens.
- **Verification:**
  - `h2_parity.py`: the block is identical in both files.
  - `h2_trace.py`, executing the Pine text:
    - volume profile vs an independent spec, 300 series: 0 mismatches;
    - volume profile vs the engine's own VP code on the same bars: 0;
    - signal + plan, 3,000 cases: 0;
    - swing/sweep state machine, 200 × 300 bars, ~2,000 sweeps: 0.
  - `pine_exec` gained series semantics, `while` and `break`.
  - `deadcode` treats H2 display values read by Visuals as wired.
- **Workbook:**
  - an H2 column;
  - a Bonferroni adoption interval (97.5%, Read Me B11), and H1/H2 decisions that use it;
  - H2 in the arm lists;
  - 11,058 formulas, 0 errors.
  - Checked on synthetic data: H2 column = Python; a case with a 95% EDGE SHOWN and a negative
    97.5% low → "KEEP TREATMENT".
- **PREREGISTRATION A3:** the H2 rule, Bonferroni adoption, the same start/timeframe/N/date,
  and the H2 hash in §2.
- **Unchanged:** the Master, Treatment, Control, Challenger, Diagnostics and EdgeCases.
- Compile NOT RUN (Strategy_H2 and Visuals).

# Build v36 → v37 — H2 shown on the Master as a second decision

Operator: "unfreeze and update our files"; then, from the options offered, **"Show both, H2 as a
second decision"**. Made before the 2026-10-05 holdout start, as PREREGISTRATION amendment A4.

- **Master:**
  - the H2 block, byte-identical to Strategy_H2 and Visuals. Its 1H/4H/1D trend reads the engine's
    own `htf1hScore` / `htf4hScore` / `htf1dScore`: same requests, same 40/40/20 rule, so the
    same values on 5M/15M. On 1H+ charts the engine sets its unavailable layer to 50.
  - **H2 SETUP**: desktop, a line under the decision footer (trend, POC, last setup with entry /
    SL / TP1 / TP2 / swept level at MT5 prices); phone, card row "5 H2 SETUP" (coloured on a
    signal bar); an alert "H2 SETUP … separate from DECISION".
  - **DECISION unchanged.** The diff touches no engine, gate, DECISION or BUY/SELL alert line.
- **Moved, not deleted (token ceiling):**
  - Session intelligence (`f_sessionIntel`, verbatim from the Treatment engine) and the
    session-volume EWMA → the Visuals H2 card, rows *Session now* / *Session history* /
    *Session volume*. Visuals' session clock has the engine's hours.
  - The cross-check line's analog-evidence readout (A / WR / ROLL n, PDH1st / MAE / BOS cont,
    Cal example, Cal grade + Brier, IS vs ROLL + !FIT, feature weights) → a Diagnostics
    *Analog evidence* row, through `build_diag.py`.
  - The Master's cross-check line keeps the mode, GC/OI/COT/curve, T/S/L/M/Q, TQ, C, VA,
    structure, risk lock, VIX and CLIMAX.
- **Strategy_H2:** the trend prelude moved out of the H2 block (`H2-TREND` fence, per file), and
  two display strings moved to Visuals. Same expressions, so the signals are identical; hash
  updated in PREREG §2.
- **Tokens (lexical):** Master 38,970 ≈ 98,010 compiled = 2.24% under 100,256 (target ≥ 2%).
  Without the moves it was 39,245 ≈ 98,701 (1.55%).
- **Checkers:**
  - `h2_parity.py` now compares three files and checks Visuals' `SESSIntel` block against the
    Treatment's `f_sessionIntel`.
  - `deadcode.py` applies its companion rule to the Master, for the six stats now displayed
    by Diagnostics.
  - `precheck`, `undeclared`, `order`, `deadcode`, `pinelimits`, `diag_parity`, `h2_parity`,
    `h2_trace` and `formula_trace`: all PASS.
- **PREREGISTRATION:**
  - A4;
  - Master and H2 hashes in §2;
  - the A1 heading, lost in v36, restored.
- **Workbook:** Read Me title v37; A13 says an H2 SETUP is not a Live-arm trade. Recalculated in
  LibreOffice; 11,058 formulas.
- **Unchanged:** Treatment, Control, Challenger, EdgeCases.
- Compile NOT RUN (Master, Visuals, Diagnostics, Strategy_H2).

# Build v37 → v38 — first chart run: two defects found, fixed; holdout restarts 2026-10-06

From the operator's screenshots of v37 on the 15M chart (2026-10-05):

- **F-A42 (P0, compile):** the strategy arms failed to compile.
  - Treatment, Control, Challenger and H2 all stopped at `fwdStart = input.time(timestamp("UTC",
    2026, 10, 5, 0, 0), ...)`: CE10123. `timestamp()` with a timezone gives a simple int, and
    input.time needs a const.
  - The bug dates from the v34 scorecards, and no checker covered that class.
  - Fixed with a const literal (epoch ms). New `pinelimits.py` **G9** flags any input default that
    is a function call; it catches the old file and nothing in v38.
- **F-A41 (P1, signals):** live and history used different higher-timeframe data.
  - Diagnostics' Math-probes row measured the daily `close[1]` request at **two days back on 6,027
    of 6,091 bars** (one day back live).
  - All 15 higher-timeframe requests of offset values per engine copy are affected: the 1H/4H/1D
    (and 5M/15M where available) trend layers, macro feeds, VIX, COT, OI, daily closes and monthly
    H/L.
  - Also the H2 trend (Visuals, Strategy_H2; the Master via the engine) and Visuals' monthly and
    4H levels.
  - These now use `lookahead_on` with the offset: the last completed bar, identical live and in
    history, with no lookahead.
  - Unchanged:
    - same-timeframe requests (silver, EURUSD, SPX, GC);
    - Visuals' live 4H `[high, low]`, which has no offset, so `lookahead_on` would read the future.
  - New `pinelimits.py` **G10** flags the pattern: 15 hits in the old Treatment, 0 in v38.
  - The Diagnostics probe now makes the engine's call and should read "=1d back".
- **Holdout:** start moved to **2026-10-06 00:00 UTC** (PREREGISTRATION A5, operator decision).
  - The scorecard input default changed with it.
  - Workbook Read Me B5 = 2026-10-06; 2,501 formulas gate on it.
  - No arm had recorded anything (none compiled).
- **Parity:** Treatment/Control 5 hunks, Treatment/Challenger 4; `diag_parity`, `h2_parity` and
  `h2_trace` PASS.
- **Seen on the chart, not changed:**
  - The Master compiled, with TradingView's "Heavy script — close to the plan's 20 s runtime
    limit".
  - The pasted Diagnostics was v36 (its header said v34, its last panel row was Engine), so the v37
    Analog-evidence row had not reached the chart yet.
  - F-A43: the EdgeCases line citations are stale (comments only).
- Compile NOT RUN for v38 (all seven chart files changed except EdgeCases).

# Build v38 → v39 — v38 chart run reviewed; two display fixes

From the operator's v38 screenshots (2026-10-05, 15M):

- **Verified on the chart:**
  - All seven chart scripts compile; the four arms run.
  - F-A41: Diagnostics' Math probes read `D close[1]: =1d back 6094 / =2d back 0 / other 0`. That
    is the opposite of v36's 64 / 6027 / 0, so the fix holds.
  - The Visuals H2 card and its session rows display (London range, open, expansion,
    swept-previous-extreme, manipulation 80% / continuation 39%).
  - Diagnostics shows the v37 *Analog evidence* row.
- **F-A44 (P3, display):** that row read PDH1st 100 / PDL 0%.
  - The three twins (and so Diagnostics, built from the Treatment) lack the Master's
    `else if fh_ == 2` branch, so only PDH-first analogs were counted. The gap is in the twins
    since the originally audited build.
  - v37's move to Diagnostics assumed "same engine, same numbers", which was wrong for this value.
  - Restored identically in Treatment, Control and Challenger; Diagnostics rebuilt. `p2`/`pT` feed
    nothing but this readout, so there is no signal change.
  - `diag_parity.py` now also compares `runStatsEngines` Master vs Treatment, allowing only the
    two documented last-bar refresh lines. It fails on v38's twin and passes v39.
- **Master H2 line:** the desktop decision-footer cell clipped the one-line H2 text at both ends.
  It is now two lines:
  - `H2 <trend> · POC <p> · last <time> swept <lvl>`
  - `<side> entry … SL … TP1 … TP2 …`
- **Seen, not changed:**
  - Treatment's and H2's Strategy Tester show 25K initial capital (Control and Challenger 10K;
    code default 10,000). That is a saved Properties setting on the chart, and the registered
    default is 10,000.
  - Several reports were captured while "Updating report", and the Challenger and H2 screenshots
    show identical figures (104 trades, PF 1.734, +215.99). Not validated: re-capture each after
    "updated successfully".
  - These backtests cover Jul–Oct 2026, the development window. They are not evidence (A1.2).
- Hunk counts 5 / 4. All checkers pass. Compile NOT RUN for v39.

# Build v39 → v40 — feature "weights" baseline (F-A45, display only)

Operator: "Fix the feature weights baseline too."

- The Diagnostics readout `W-22/-22/-26/-26/-17` was not similarity weights.
  - It was each feature's directional accuracy minus 50%, over all analogs, timeouts included
    (`c / t`).
  - With about three-quarters of analogs timing out, every feature sat about 25 points under the
    coin-flip line whatever its real skill.
- **Now:** accuracy among resolved analogs, `c / (c + w)`, minus 50, in points.
  - 0 = coin flip; + = the feature picks the side that resolves.
  - na below 10 resolved analogs.
- **Files:** the Master and the three twins, identically (the stats-engine parity holds).
  Diagnostics relabels the readout "edge S/H/L/M/C".
- **Display only:** `_cFeat*` / `__fs.. __fc` are read by nothing but this readout.
- **Executed check:** the formula text taken from the Pine, on c = 26, w = 4, t = 100, gives +36.7
  (the old formula gave −24.0).
- **Tokens (lexical):** Master 39,000 ≈ 98,085 compiled (2.17% under). Diagnostics 39,611 ≈
  99,622: v38 compiled at 39,567, so this adds 44 and leaves ~0.6% under the limit on the estimate.
  **Diagnostics has no room left;** nothing more should be added to it without moving something
  out.
- All checkers pass; hunk counts 5 / 4. Compile NOT RUN.

# Build v40 → v41 — volume profile rebuilt every bar (F-A46); engine arms restart 2026-10-07

From the operator's v40 screenshots (2026-10-06). TradingView warned "barstate.islast may not
initially return true" at the arms' L1948.

- **The defect (F-A46):** that line guarded the engine's volume-profile rebuild.
  - The POC/VAH/VAL it produces are stop and target candidates (`_slC`, `_tpLvls`), and they feed
    `planExpectancy`, whose EV < 0 test is part of `tqVeto`.
  - On historical bars the levels were na; live they existed. So the record a reload recomputes
    was planned differently from the signals that fired live.
  - It was known as F-A07 and deferred until a runtime baseline existed. The operator chose to fix.
- **Fix:** `if barstate.isconfirmed and not perfMode` (same 5-bar rebuild cadence), identically in
  the Master and the three twins. Diagnostics was rebuilt.
  - `h2_trace`: the engine VP code still equals H2's specification on the same bars.
  - H2 is unaffected; its own profile was always rebuilt every confirmed bar.
- **Holdout (A6):**
  - The Live arm, Treatment, Control and Challenger now start **2026-10-07 00:00 UTC**; their
    scorecard inputs were changed.
  - H2 keeps 2026-10-06; its file is unchanged.
  - Workbook: Read Me B5 = 2026-10-07 and new D5 = H2 start. Arm Trades "Counts?" picks D5 for H2.
    Tested on a scratch copy: H2 10-06 12:00 counts; Treatment 10-06 12:00 does not; Treatment 10-07
    counts; H2 10-05 does not.
- **Runtime:** the rebuild adds about 50 loop steps per bar (H2's own profile is ~180). The
  scripts already show TradingView's "Heavy script" notice; watch for a runtime error after
  pasting.
- **Also seen in the v40 run, not changed:**
  - The other two "islast" warnings (cost-model note, scorecard draw) are display-only: the card
    draws at the first close after load.
  - PDH1st now reads 0 / PDL 100. The counting code is identical in all engines and symmetric. The
    value may be real for the matched analogs, but it is unverified without the counts.
  - The feature edge reads 1/0/1/−4/5 (≈ coin flip, consistent with F-A34).
  - The bear calibration slope fits at 0 (flat).
  - The Strategy Tester panels again showed figures belonging to other arms while updating.
- All checkers pass; hunk counts 5 / 4. Compile NOT RUN.

# Build v41 → v42 — one system of record (A7); exits on the entry bar (F-A47)

From the operator's 2026-10-08 screenshots (TradingView v41 and the website).

- **Two records were found.**
  - A second session runs the website (Python port, GitHub Pages) on the default branch `claude/audit-prompt-real-artefacts-nekqv6`. Its
    pre-registration Amendment 6 (2026-10-06, written after v41) made the website the only system of record and
    this TradingView line display only. That contradicted this branch's A5/A6 restarts.
  - Asked here, the operator chose **"Website only"**. PREREGISTRATION A7 marks this branch superseded and display
    only; CLAUDE.md, the RUNBOOK and the workbook say so.
- **F-A47 (P2):** exits were placed only once `strategy.position_size` showed the position, one bar after the entry
  under `process_orders_on_close`, so the first bar after every entry had no stop or targets. Raised by the website
  session; confirmed in these files.
  - Fix: both exits are also placed in the entry block, after the levels are set, in Treatment, Control, Challenger
    and H2 identically (hunk counts 5 / 4).
  - It changes the TradingView backtests. Since A7 those are not counted.
- **Display:**
  - The scorecards are headed "BACKTEST CARD (NOT COUNTED: record = website)".
  - Visuals' H2 card reads v42 (it read v37).
- **Checked on the website's own data** (`market-data` branch, read only):
  - its PDL 4061.73 is a real 10-07 12:45 UTC drop;
  - weekend quotes and missing spot volume are already handled by its engine (weekend bars dropped; COMEX volume, D-07);
  - the TradingView-H2 SELL of 10-06 18:15 (SL 4173.92) was stopped on that feed at 18:45 (high 4176.59) before the drop.
- **Not changed:** the website, its freeze keys and the default branch.
- All checkers pass. Compile NOT RUN.

# Build v42 → v43 — plan, TQ and bias aligned (F-A48)

Operator's 5M Master screenshot (2026-10-09), "all values should be well calibrated and aligned to each other".

- **Contradiction on screen:** DECISION read `WAIT TQ47D · BIAS BEAR-ISH · TREND 20/60` and SIGNAL read L 31 / S 55 / R 13,
  yet the plan line read **LONG** (entry 4183.66, SL 4180.29, TP1 4195.41, EV −0.01R).
- **Cause:**
  - `f_tradePlan()` ran ~1,700 lines before the final scores.
  - On a WAIT bar it chose its side from `bullBiasScore >= bearBiasScore`, a structure / liquidity / macro / HTF / momentum
    / session composite; BIAS uses the final `bullScore` / `bearScore`.
  - Trade quality grades the plan's side, so TQ47D was the quality of a long.
- **Fix:**
  - The call is moved to just after the final normalisation (`rangeScore := nr2_`), in the Master and the three twins
    identically. Nothing read the plan before that point, so no reader moves.
  - The WAIT-bar side is `bullScore >= bearScore`, the same rule as BIAS and the WAIT reason. On BUY/SELL bars nothing
    changes: the plan already followed the signal.
  - Side effect: the plan uses this bar's refreshed race probabilities rather than the previous bar's. `sequence.py`
    previously listed `gHitProb` / `gRaceN` / `gRaceProb` as read before their same-bar write; those three entries are gone,
    and no new ones appear.
- **Tokens:** unchanged (Master 38,998, Diagnostics 39,609 lexical); lines moved, none added except comments.
- All checkers pass; hunk counts 5 / 4. Display only under A7. Compile NOT RUN.

# Build v43 → v44 — expectancy review against "Trading is Math" (F-A49)

Operator shared chapter 1 of S. & H. Burns, *Trading is Math* (expectancy = W x AvgWin - L x AvgLoss; an edge only
where expectancy > 0; recompute every 25-50 trades).

- **New tool `audit/tools/expectancy_check.py`** (executes the Pine text):
  - the book's worked examples: 171.40, -17.60, 166, 210 and +26.5%;
  - the engine's EV line: equal to the book formula with no timeouts, and to W*AvgW - L*AvgL + T*AvgT with timeouts
    (2000 cases each, |diff| 0);
  - the scorecard block on 300 random histories (split exits, open position, start filter): positions, mean $ per
    position (= the book's expectancy), SD, PF, 95% t-interval and verdict, 0 mismatches;
  - the t quantile against an exact Student t: -0.004 at df 9, 0.0000 at df 49 (the N = 50 decision);
  - the 95% interval of each book example at n = 50 / 100.
- **What the book's rule needs, quantitatively.** "Expectancy > 0" is a point estimate. At n = 50:
  - the 42% / 850 / 320 strategy is +171 [+7, +336];
  - the 56% / 650 / 450 strategy is +166 [+11, +321];
  - the 68% / 280 / 650 strategy is -17.6 [-141, +106], indistinguishable from zero.
  That is why the scorecard requires the 95% interval's low end > 0 (and PF >= 1.2) at N >= 50, not just a positive mean.
- **F-A49 (display):**
  - the panel WR's direction now follows the final scores, like the plan since v43 (Master, twins, Diagnostics CI row);
  - the panel PF is relabelled `PFres`: wins / losses over resolved analogs only. The EV already includes timeouts.
- **Unchanged:** the regime call and the decision log keep the 130-point bias composite; they are labelled as such.
- Tokens unchanged. All checkers pass; hunk counts 5 / 4. Display only under A7. Compile NOT RUN.

# Build v44 → v45 — "why is our win ratio too low" (F-A50, F-A51)

Operator's 4H Strategy Tester runs, Jan 2023 - Oct 2026, captured after "updated":

| Arm | TV trades | Wins | PF | Net $ | Avg win | Avg loss | Break-even WR |
|---|---:|---:|---:|---:|---:|---:|---:|
| Treatment | 80 | 41.2% | 1.285 | 179.06 | 24.46 | 13.37 | 35.3% |
| Challenger | 86 | 41.9% | 1.395 | 283.07 | 27.77 | 14.33 | 34.0% |
| H2 | 48 | 33.3% | 1.243 | 67.08 | 21.45 | 8.63 | 28.7% |
| Control | 0 | — | — | — | — | — | — |

(Avg win / loss derived from PF, net and the win count: GL = net/(PF-1), GP = PF*GL.)

- **Why the win rate is low, and why that is not itself the problem:**
  - The plans aim 1.5-5R away against a 1R structural stop. With no edge at all, a 2R target is hit first 33% of the
    time and a 3R target 25%.
  - Each arm's win rate is ABOVE the break-even rate its payoff requires (41% vs 35%, 42% vs 34%, 33% vs 29%).
  - TradingView's figure also counts each partial exit as a trade, and the post-TP1 break-even remainder as a small
    loss.
  - These are in-sample backtests, not evidence: the record is the website (A7), and Diagnostics flags IS 38% vs
    ROLL 17% "!FIT" on 4H.
- **The real limit:** the reliability buckets on 4H predict 24-59% and observe 17-24%. The score does not separate
  winners, so "being more selective" cannot raise the win rate here (F-A34).
- **F-A50 (display):** the scorecard gains a row "Win rate vs break-even" in all four arms, computed per POSITION:
  - win rate;
  - avg win / avg loss;
  - BE = avgL / (avgW + avgL);
  - green when above.
  Set the card's start input back to 2023 to see it over the whole loaded history. Verified by `expectancy_check.py`.
- **F-A51 (recorded):** at 4H and above only the 1D layer can vote, so Control's ">= 2 aligned HTF layers" gate can
  never pass (0 trades) and Treatment's HTF filter removes nothing (funnel trend 4172 > +HTF 4172). Not changed:
  display-only arms; the registered timeframe was 15M.
- **Not done, on purpose:** moving targets closer, or adding filters, to raise the win rate. That would be tuning on
  this history (AUDIT_PROMPT §9). A change of plan would be a new hypothesis, pre-registered on the website.
- All checkers pass; hunk counts 5 / 4. Diagnostics unchanged. Compile NOT RUN.

# Build v45 → v46 — MT5 execution review (F-A52)

Operator: every value is executed by hand on MT5; review all of them.

- **MT5 prices: consistent.**
  - The offset (`MT5 Price Offset`) is applied to entry / SL / TP1-3 in the plan, to the H2 SETUP line and alert, to
    the risk-tracker alert and to the TARGET row.
  - The BUY / SELL / DECISION alerts reuse the exact plan strings, so an alert and the screen cannot differ.
  - Structure, liquidity and VWAP figures in the dashboard and in Visuals are TradingView prices: reference levels,
    not order prices.
- **Sizing: units checked.** 1 lot = 100 oz (`Value per Point per Lot` 100).
  - lots = floor(risk $ / (SL distance x 100) to 0.01), clamped 0-100, with the below-minimum case flagged.
  - Risk % = half-Kelly on the Wilson 95% lower win probability, capped at the `Risk %` input; 0% means no proven edge.
- **F-A52 (fixed, Master only):**
  - the regime haircut reached the Risk % text but not the $ and lots;
  - "-1.00L" showed instead of "<min";
  - the % was truncated and zero lots printed ".00L".
  - Sizing lines executed on 3000 random cases: 0 mismatches; realised risk never above the intended risk.
- Master 39,009 lexical (~98,108 compiled, 2.1% under). All checkers pass. Compile NOT RUN.

# Build v46 → v47 — volatility robustness and end-to-end traceability (tools only; no artefact changed)

Operator: the code must work in high, medium and low volatility, with calibrated, validated values and end-to-end
traceability.

- **`regime_check.py`** executes the regime engine on 20,000 states across every ATR percentile:
  - exactly one regime per bar, in the documented priority;
  - LV/NV/HV tags at the 20th / 80th percentiles;
  - SL multiple within [1.0, 2.2] and non-decreasing in volatility for each regime;
  - size 1.0 / 0.75 (HV) / 0.5 (ABNORMAL); confidence cap 60 in ABNORMAL; forecast >= 4 bars;
  - adaptiveATR never 0 or na after the first bar (floor 0.01% of price). The first bar has no previous close, so it is
    warm-up.
  - It passes on the Master, Treatment and Diagnostics.
- **Divisions by a volatility measure** (ATR, order-block range, VP bucket size) are all guarded; scan of the Master
  and Treatment.
- **Low volatility and costs.** Round-trip cost is $0.65-0.97/oz by session, i.e. 32-49% of R at a $2 stop and 4-7% at
  $15. The engine subtracts it in EV (race formula, verified), so it declines trades where cost eats the reward.
- **`decision_check.py`** executes the decision chain:
  - trend scores sum <= 100, so with the threshold >= 51 (the input's minimum) BUY and SELL can never both fire;
  - the entry rule, every condition necessary;
  - the veto truth table; a missing EV does not veto;
  - DECISION precedence RISK LOCK > NO TRADE > BUY > SELL > WARMUP > WAIT, and BUY/SELL never shown while vetoed.
  - It passes on the Master, Treatment and Diagnostics. Control and Challenger gates differ by design.
- **`value_map.py` -> `audit/VALUE_TRACEABILITY.md`:** 21 operator-facing values, data -> regime -> evidence -> scores
  -> gates -> plan -> veto -> decision -> MT5 order values. Each row gives the variable, its current Master line (found
  by anchor, not typed), the formula and the executed check that verifies it. `--check` fails if code moved.
- No artefact changed: the v46 files and hashes stand.

# Build v47 → v48 — review and validate (labels only)

- **Full suite on v47: all pass.**
  - precheck, undeclared, order, deadcode, pinelimits;
  - diag_parity, h2_parity, h2_trace;
  - formula_trace, expectancy_check, regime_check, decision_check, race_model_check, formula_check;
  - value_map --check.
  - The sequence audit is unchanged (61 entries, as at v43). Hashes and AUDIT_PROMPT pins are consistent.
- **Stale labels removed.** They implied the 15M chart counts, which has not been true since A7:
  - the scorecards and the Visuals H2 card said "(registered)" on 15M and an orange "NOT 15M: does not count" elsewhere;
  - they now read "display only" in white, and the `_fwtfOk` flag (display helper) is gone;
  - the Visuals H2 card header reads v48.
- **Still open (unchanged):**
  - F-A43 (EdgeCases line citations, comments only);
  - Diagnostics prints "NaN" for a feature edge with fewer than 10 resolved analogs (no token room in Diagnostics);
  - the Master runtime "Heavy script" notice.
- Compile NOT RUN.

# Build v48 → v49 — structure and liquidity-sweep alerts (Master)

Operator: "add alert when CHoCH, MSS or BOS and liquidity sweep occurs".

- **One `alert()` at bar close (Master)** when any of these FIRST appears:
  - the engine's BOS, CHoCH or MSS, either side;
  - a liquidity sweep (wick through PDH/PDL, PWH/PWL or PMH/PML and close back).
- **Same flags as the dashboard's STRUCTURE cell.** Visuals' "~BOS / ~CHoCH" are an approximation and are not used.
- **CHoCH / MSS are states** that persist until the next swing, so a rising-edge helper `_ev()` alerts only on the
  first bar. `decision_check.py` executes it on 300 random flag sequences (0 mismatches) and checks that all 8 flags
  are covered.
- **Message:** `XAUUSD 15 CHoCH▲ SWEEP-LOW | info, not a DECISION`. The H2 SETUP text (same trigger, same MT5 plan)
  now rides in the same alert instead of a second `alert()` call.
- **Tokens:** a helper `_m(x)` replaces 12 copies of `str.tostring(x + mt5Offset, "#.##")` with identical output.
  Master 39,053 lexical ~ 98,218 compiled = 2.03% under the limit.
- **Unchanged:** the named "Bull BOS" / "Bear BOS" alert conditions (filtered BOS that can trigger entries); the
  DECISION rule.
- All checks pass (value map 22 values). Compile NOT RUN.

# Build v49 → v50 — macro label (F-A53)

Operator: "the macro was bull, now it shows bearish -- why?"

- **What the verdict is.** `macroStrengthScore` (-100..+100) on completed 1H bars:
  - DXY and US yields / TIPS falling are bullish for gold; EURUSD, silver and SPX rising are bullish;
  - each vote is weighted by its |correlation| with gold, normalised to 100;
  - plus DXY momentum (+/-10) and rate pressure (+/-10).
- **Labels:** >= 40 BULL, 15..39 bull-ish, -14..14 MIX, -39..-15 bear-ish, <= -40 BEAR.
  - 10-05 "BULL+" was the weak bullish band; 10-08 "BEAR" was a strongly bearish reading.
  - It is a live reading and changes as those markets move. The website's stored data showed the dollar up on 10-05
    and down on 10-06 (rough proxy).
  - That data ends on 10-06, so the 10-08 reading could not be re-derived here.
- **F-A53:** `BULL+` / `BEAR+` printed for the WEAKER readings; they now read `bull-ish` / `bear-ish`, followed by the
  score, e.g. `Macro BEAR -52`. Master 39,060 lexical (2.01% under).
- VALUE_TRACEABILITY gains the macro row (23 values). All checks pass. Compile NOT RUN.

# Build v50 → v51 — chart run of v48-v50 reviewed; card header

The operator's 15M screenshots (2026-10-11) show every recent fix live:
- all scripts compile, EdgeCases ALL PASS 99;
- `Macro BULL 75` (v50), `Risk 0.0% $0 0.00L` (v46), `PFres` (v44), "display only (A7)" (v48);
- the plan follows the bias: BULL-ISH -> LONG (v43);
- the H2 card row `25% vs 83% needed (avg win 1.8 / avg loss 8.97)` (v45).

- **Fixed:** the scorecard header still printed a hard-coded "v42"; it now carries no build number (the BUILD STAMP
  at the top of each file is the build).
- **Observed, not changed:** H2's 4 positions since 2026-10-06 are 1 win / 3 losses. The average win ($1.80) is the
  TP1 half closed at about 1R with the remainder stopped at break-even, against full-R losses. With N = 4 this is not
  evidence of anything; the H2 record of record is the website's (A7).
- Checks pass. Compile NOT RUN.

# Build v51 → v52 — Market Brief on the chart (new companion: Brief.pine)

Operator: "Our dashboard should also tell us these information as well" (the website's Market Brief).

- **Where:** the Master has 5 lexical tokens of headroom and Diagnostics is full. The brief therefore goes in a new
  companion, `XAUUSD_Quantum_5_0_Brief.pine`, built like Diagnostics:
  - the Treatment engine, verbatim (`diag_parity.py` now checks both companions);
  - plus a fenced panel (`audit/tools/brief_panel.pine`, assembled by `build_brief.py`).
  - Size: 37,323 lexical ~ 93,867 compiled, 6.4% under the limit.
- **What it shows** (definitions taken from `site/app.js` renderBrief and `quantum/arm_h4.py` on the default
  branch, read only):
  - TREND: BIAS, price vs EMA200, the active BOS / CHoCH / MSS and its age, 4H / 1D direction, regime, and
    "against the 4H and 1D trend" when it applies.
  - HEADING: the lean (|L − S| < 5 is "no clear lean"), L / S / R %, and PDH vs PDL reach.
  - LIQ TAKEN: the engine's last confirmed sweep, with its price, pool, time (UTC) and bars ago.
  - TARGET: the nearest pool / day / swing level on the lean side, the one after it, and the opposite liquidity.
  - DO NOW: an engine signal, "Wait for a trigger" (sell below X / buy above Y on a close), or "Stay flat", plus what
    the engine is waiting for.
  - PLAYBOOK SELL / BUY: the arm-H4 rule with trigger, stop, TP1, TP2, R:R and distance away.
  - GATES: n/7 on the bias side.
  - When the next close trades a playbook, a "fired" line and an optional alert ("info, not a DECISION").
- **Not a decision.** The Master's DECISION rules; it also applies RISK LOCK and the TQ floor, which this companion
  does not compute. The playbook is conditional; its record is the website's arm H4 (A7). Nothing here is counted.
- **Gates:** the brief scores the seven conditions of `shouldBuy` / `shouldSell` themselves. It does not use the
  twin's `decisionLog`, which still scores the control set (F-A03 fixed that in the Master only; the twins keep it
  to hold their A/B hunk count).
- **Executed** (`brief_trace.py`, new) against the website's own code, run unchanged (Python for `arm_h4.py`, Node for
  `app.js`):
  - level list == `arm_h4.LEVELS`;
  - playbook sides vs `arm_h4.playbook`;
  - fired vs `arm_h4.evaluate`;
  - target / then / opposite vs `nextLevels`;
  - last-sweep pool vs `lastSweep`;
  - gate row 7/7 ⇔ the engine signal.
  - Known difference (by reading, not executed): three levels within 1.2 cents of each other can choose a different "then" level from the
    site's chained de-duplication.
- **Tools:**
  - `pine_exec.py` now runs arrays, `for … in`, tuple returns and user functions, and caches compiled expressions;
  - `undeclared.py` reads `for [i, x] in`;
  - `deadcode.py` treats the Brief like the twins (engine symbols wired through Diagnostics);
  - `value_map.py` adds five Brief rows (28 values).
- **Unchanged:** every other artefact (same hashes as v51).
- Compile NOT RUN.

# v52 (docs only) — smaller paste set

Operator, 2026-10-13: "Can we decrease the number of files?"

- **Measured:**
  - The shared engine alone is about 87% of TradingView's compiled-token limit. The six engine-bearing files therefore
    cannot be merged.
  - Comments are about 35% of the lines and 45% of the bytes, but they do not count toward the limit.
- **Operator chose:**
  - Paste routinely only the chart set: Master, Visuals and Brief (plus Diagnostics when wanted).
  - Keep the strategy arms and EdgeCases in the repo, unchanged, and send them only when they change.
  - Keep the comments.
- **Merging the four strategy arms was not chosen.** It would have meant one strategy with an Arm input, 9 → 6 files
  and about 3% headroom.
- No artefact changed. CLAUDE.md's delivery rule is updated; the build record still lists all nine hashes.

# Build v52 → v53 — every arrow coloured by what it means for gold (F-A54)

Operator: "indicators with an arrow: green if they support gold up, red if they support gold down".

- **Bug (F-A54 a):** the Master's macro arrows printed ▼ / ▼▼ whenever the gold-bullish side was false. A FLAT DXY,
  10Y, EUR, XAG or TIPS therefore read as gold-bearish; executed on v52, a flat DXY with a strong correlation printed
  ▼▼. Now `_arrowStr(valid, up, dn, mag)`:
  - ▲ / ▲▲ supports gold up; ▼ / ▼▼ supports gold down;
  - ≈ when flat or when the correlation is weak (|r| <= 0.25); — when there is no data.
  - SPX uses the same helper.
- **Colours (F-A54 b), Master:**
  - MTF / session line: the text now follows MTF confluence (green / red / grey); session quality stays as the tint.
  - Macro line 2 (EUR / XAG / SPX / TIP): the text now follows the net gold direction of those arrows; correlation
    health stays as the tint, and CR% is still printed.
  - C / S / I bias breakdown: now takes the BIAS colour (it was always grey).
  - Unchanged, already correct: structure, Corr (DXY / 10Y / TIP), and the Visuals labels (BOS / CHoCH / OB /
    absorption).
- **A table cell has one colour.** A Master cell with several arrows shows their net direction. The Brief's new
  **GOLD ARROWS** grid gives every indicator its own cell, coloured green / red / grey:
  - trend, structure, bias, liquidity, EMA200, VWAP, value area, MTF, 5M / 15M / 1H / 4H / 1D, CVD, displacement,
    RSI divergence;
  - DXY, 10Y, TIPS, EURUSD, silver, SPX, macro score.
  - Macro cells show the effect on gold, then what the market itself did ("DXY ▲ / dollar falling").
  - CLIMAX is amber: the engine scores a climax as exhaustion, not as a side.
  - New input "Gold-arrow grid position" (default Bottom Right; "Hidden" turns it off).
- **Tokens:** Master 39,058 lexical, 2 fewer than v52, by removing duplicated validity checks. Brief 38,297 lexical
  (3.9% under the limit).
- **Executed:** `brief_trace.py` §6 (4,000 states each):
  - the grid's glyph equals the Master's `_arrowStr`, with both files' lines executed;
  - colour equals the gold direction, and flat is never ▼.
- Compile NOT RUN.

# Build v53 → v54 — re-audit (F-A55, F-A56; F-A43 closed)

Operator: "recheck every value and re-audit ... zero error or bug, end-to-end traceability, zero unwired or dead features".

- **F-A55 (bug, Brief):** DO NOW read the raw entry signal; it now reads the engine's DECISION `_confDirLabel`.
  - Before, on a bar the Master vetoes (NO TRADE, RISK LOCK), the Brief said "BUY signal" and hid the playbook.
  - The twin's DECISION, gate and veto lines are identical to the Master's. `diag_parity.py` now pins 22 of them, plus
    the Brief's BIAS formula against the Master's `biasLabel`.
  - DO NOW follows the website's doNow rule and is executed against that line in Node (24 states).
  - When all 7 gates pass but the DECISION is vetoed, the panel now names the block instead of an empty "waits for:".
- **F-A56 (disclosed):** the twin engine refreshes its statistics every 2–12 bars (the Master also on the last bar), and
  its risk kernel counts all bars (the Master's only the last 120 signal bars). L/S/R, the DECISION and RISK LOCK can
  therefore differ from the Master's for a few bars. The Brief panel says so: the Master rules.
- **Checked equal, Master vs twin:**
  - trade quality (`f_tqEngine`, 45 lines);
  - the trade plan (`f_tradePlan`, differing only in the MT5-offset strings);
  - the volume-profile block and its confirmed-bar gate;
  - reach scores.
- **Diagnostics:** the cone row (breach ↑ / ↓) and the auction row (value migration ⇈ ↑ / ⇊ ↓) are now coloured
  green / red by direction. Diagnostics is 39,647 lexical tokens, about 0.5% under the limit.
- **F-A43 closed:** EdgeCases cites Master code instead of line numbers.
  - 27 anchors, each matching exactly one Master line, enforced by the new `edgecase_cites.py`.
  - Comments only; no assertion changed.
- **Dead or unwired code:**
  - 0 in all nine files, and the retained list is empty.
  - The "structural" hits are tuple slots, `ta.dmi`'s unused outputs and the A/B arms' cross-gate variables.
- **Value map:** 31 values (adds the macro arrows, DO NOW and the GOLD ARROWS grid).
- Compile NOT RUN.

# Build v54 → v55 — Brief compile fix (F-A57); H2 card and mobile dashboard redesigned for phones

Operator's chart (2026-10-14):
- v54 Brief failed with CE10165 ×10 ("No value assigned to the sz parameter in f_brC()") and 1 shadowing warning.
- EdgeCases shows ALL PASS 99; Diagnostics and the Master compile.
- Request: "redesign the H2 card and the mobile dashboard for the size of a mobile screen".

- **F-A57 fixed:**
  - `f_brC` takes the text size from the global `brSz`; the f_brSide local `tp1` is renamed `t1`.
  - New `pinelimits.py` checks: G11 (user-function call arity) and G12 (local shadows an earlier global).
  - Run on the v54 file, they report exactly the compiler's 10 errors and 1 warning; all nine v55 files read 0.
- **Design rules for a phone-width chart** (about 360 px wide):
  - two columns, keys of at most 8 characters;
  - every value line at most about 30 characters, wrapped with line breaks instead of " · " runs;
  - no `size.tiny` text;
  - MT5 prices throughout;
  - colour = what the row means for gold.
- **Master mobile card** (Dash Mode = Mobile), token-neutral (39,062 lexical, still at least 2% under the limit):
  - Keys TREND / TARGET / NEXT / DECISION / H2.
  - Each value wraps into short lines.
  - The DECISION row lists the MT5 entry, SL, TP1 and TP2 one per line.
  - The long desktop detail strings now appear only at Density = Spacious; Standard shows the headlines plus the plan.
  - Detail text is never tiny (Small → small).
  - The H2 line breaks before "last" and before TP1, also in its alert text.
- **Visuals H2 card:**
  - New inputs "H2 card layout": Compact (phone), the default with 7 short rows, or Full, which adds the session /
    history / volume rows (nothing removed). Plus "H2 card text size": Small or Normal.
  - Rows: SIGNAL (time, then entry + SL, then TP1 + TP2), TREND, VALUE, SWINGS, SWEEP, NEXT, NOTE.
  - "NEXT" is now in MT5 prices; it was in TradingView prices while every other row was MT5.
  - The header no longer carries a stale build number ("v48").
  - Colours: a low-sweep / below-value / BUY row is green; a high-sweep / above-value / SELL row is red.
- **H2 block:** unchanged, byte-identical in all three files (`h2_parity.py`).
- Compile NOT RUN on v55.

# Build v55 → v56 — phone card fits the screen; Brief lines re-flowed

The operator's screenshots (2026-10-16) show v55 compiling: the Brief, the GOLD ARROWS grid, the H2 card and the Master
Mobile card. On a phone (1H) the Master's Mobile card was wider than the screen and clipped on the left.

- **Master mobile card** (39,064 lexical, still at least 2% under the limit):
  - The plan rationale line (about 75 characters, the cause of the clipping) shows on the mobile card at Spacious only.
  - The card sits at the top LEFT, so it no longer covers the live candle and the price scale.
  - The plan bar reads "LONG PLAN" / "SHORT PLAN" (a plan, not an instruction; the DECISION decides).
  - The HTF line is labelled "15m-4h" (it counts 15m / 1H / 4H; the Brief's 4H / 1D lines are a different measure).
  - The H2 lines break before SL and before "swept"; the H2 alert text breaks there too.
  - Paid for by collapsing a two-branch ternary that v55 left with identical branches (−5 tokens).
- **Brief panel:**
  - Every value line is now about 34 characters at most: header, TREND, HEADING, LIQ TAKEN, DO NOW, SELL / BUY (close <
    trigger · away, then stop · R:R, TP1, TP2, "not yet triggered"), and GATES (two lines).
  - The PLAYBOOK note shrinks to 4 short lines.
  - Same values; only the layout changes.
- **Reviewed and not a bug:**
  - The Master's mobile "HTF BULL" and the Brief's "4H down · 1D down" measure different timeframes.
  - The desktop "TGT —" and the mobile "TARGET PDH" screenshots are 2 minutes apart, across a 5m bar close.
- Compile NOT RUN on v56.

# Build v56 → v57 — professional phone card; LIQ DRAW; H2 cell; cross-check moved to the Brief

Operator: "Approve all, rename to LIQ DRAW and move features".

- **Moved (not deleted), Master → Brief:** the engine cross-check line.
  - Contents: T / S / L / M / Q, TQ / C, VA, structure, risk lock, VIX, CLIMAX; GC / OI / COT / 2s10s; the GC / OI / 2Y /
    COT feed status and the schema state.
  - The Brief runs the same engine (`diag_parity.py`) and shows them as the ENGINE and DATA rows.
  - The Master no longer computes those display strings or the VIX feed. That frees 745 lexical tokens and one
    request.security call; nothing that feeds a gate, the DECISION or the plan was touched.
  - Dropped with it: two labels that echoed settings, the Dash Mode tag "[Desktop]" and the "SR@Visuals" pointer (whose
    `showSR` input did nothing else; S/R is drawn by Visuals).
- **Master phone card** (Dash Mode = Mobile):
  - A title row reads "XAUUSD <tf> · <DECISION> · MT5 prices".
  - DECISION is the FIRST headline, then TREND, LIQ DRAW and NEXT; Spacious details follow the same order.
  - Plan rows are left-aligned.
  - New switches: "Mobile card: NEXT row" and "Mobile card: H2 row".
  - LIQ DRAW shows its distance from price, e.g. "PDH 4177.46 (-2.7)".
- **LIQ DRAW:** the Master's engine liquidity destination was labelled TARGET / TGT, the same word as the Brief's
  nearest-level TARGET. It now reads LIQ DRAW (mobile) and DRAW (desktop).
- **Desktop DECISION:** the footer wraps onto 3 lines, and H2 SETUP has its own cell underneath (row 3), green / red by
  side.
- **Brief:**
  - The ENGINE and DATA rows are added.
  - New "Panel layout" input: Full, or Compact (phone) showing header, TREND, DO NOW, SELL, BUY and GATES.
- **Tokens:** Master 38,461 lexical (≈ 3.5% under the limit; it was 39,064); Brief 38,595.
- **Value map:** 32 values (adds the ENGINE / DATA rows).
- Compile NOT RUN on v57.

# Build v57 → v58 — no value computed unseen; moved features verified (F-A58)

Operator: "no compromise on quality, every feature maintained, wired up properly, end-to-end traceability".

- **Moved features verified** (`moved_check.py`, new). Each of the 23 values the v57 move took to the Brief is checked
  against its definition frozen from the v56 Master (commit 2f7f56d7):
  - the T/S/L/M/Q arrows, structure, risk lock;
  - the GC / OI / COT / 2s10s states and the VIX feed;
  - the feed status codes, value area, climax and confidence.
  - All 23 are identical, and each must still be displayed by the Brief panel.
  - Documented equivalences: COT_STATUS (same value for every input) and `f_tqEngine` (body compared).
  - The schema text now uses the Master's exact wording ("BUILD v5  SCHEMA_V2 CLEAN" / "V1 100%" / "MIXED_SCHEMA V1 x%
    V2 y%"); v57 had shown the twin's shorter wording.
  - Mutation-tested: dropping VIX from the panel, editing a definition, and re-adding a string to the Master each fail.
- **F-A58 (my v57 regression, fixed):** the move left the Master computing seven values it no longer showed. They are
  removed from the Master; the Brief's engine computes and displays each one.
  - Removed: the volume-climax block (relative volume, same-hour EWMA, climax flags, `showClimax` /
    `volClimaxPerc` / `volLookback` inputs); `vaRatio` / `vaPos`; the V2 census counter and the `hSchemaVer` ring
    buffer; the 2s10s spread, `y2Valid` and the US 2Y feed (`y2Symbol`, one request.security); the GC
    volume-expansion flag and `gcVolMult`.
  - `deadcode.py` now FAILS if the Master computes a value only a companion reads. Seven are allowed and documented:
    six stats-engine outputs held identical to the twin, and one request tuple slot. Mutation-tested.
  - **Settings that moved:** VIX symbol, US 2Y symbol, Volume Climax switch / percentile / lookback, and the GC
    volume-expansion threshold now live only in the Brief's settings (they only fed the moved displays).
- **Master:** 37,984 lexical tokens (≈ 5% under the limit); 18 request.security call sites (was 20).
- **RUNBOOK:** the phone-card table is rewritten for the v57 rows.
- Compile NOT RUN on v58.

# Build v58 → v59 — nothing removed: every value restored and wired (operator)

Operator: "We'll not remove anything as we have to maintain every feature and every value was added with a purpose, so
we have to link it up / wire it up. Show me the mobile dashboard as well."

- **Rebuilt from v56** (the last Master before any removal, commit 2f7f56d7). Only the additive v57 work was replayed:
  - phone card: title row, DECISION first, LIQ DRAW with distance, left-aligned plan, NEXT / H2 switches;
  - desktop: DRAW label, wrapped DECISION footer, H2 in its own cell.
- **Everything v57 / v58 removed is back in the Master:**
  - the cross-check line on the desktop cell and in the Spacious phone details;
  - the GC / OI / COT / 2s10s states, VIX, the schema / feed status, the volume climax, the value area, the V2 census;
  - the settings: VIX symbol, US 2Y symbol, climax, `gcVolMult`, `showSR`.
  - The Brief keeps its ENGINE / DATA copy as well.
  - `moved_check.py` now holds BOTH copies to the frozen v56 definitions.
- **Values the Master computed but never showed (since v37), now wired** into the SIGNAL cell (third and fourth lines,
  also in the Spacious NEXT details):
  - the analog structure evidence: PDH-first / PDL-first %, BOS continue / fail %, MAE, calibration detail;
  - the calibration grade and Brier score;
  - the in-sample win rate and n;
  - the per-feature edges S / H / L / M / C.
- **Result:** `deadcode.py` reports the Master at 0 dead, 0 structural, and 0 values read only by a companion. The
  guard now allows no exceptions.
- **Token room without removing anything:** identical-output rewrites in the display layer.
  - Helpers: `_gS` / `_gC` / `_gF` (dashboard array reads), `_pp` (plan-row probabilities), `_si`, `_sg`, `_b1`, `_v`,
    `_ud`, `_byDest`, and `_al` (alert prefix and frequency).
  - `tcp` loses two parameters that were always 0.
  - Two redundant guards are removed: the na-check before na-false comparisons, and the duplicated BUY / SELL branches.
  - `refactor_check.py` (new) executes each rewrite against the v56 code it replaced: 51,000+ cases, 0 mismatches; all
    6 alert messages are unchanged.
- **Master:** 39,033 lexical tokens (2.09% under the limit).
- **Mobile dashboard preview:** `audit/mobile_card_preview_v59.png`. It is a layout render of the v59 card using the
  code's rows, order and colours, with sample values from the operator's 16 Oct screenshots; not live data.
- Compile NOT RUN on v59.

# Build v59 → v60 — Mobile "Strip": the desktop dashboard as a top band (operator)

Operator: "the mobile dashboard should look like the web dashboard, but adjusted to 15-20% at the top of the screen so
the candles are visible".

- **New setting "Mobile layout"** under Dash Mode = Mobile:
  - **Strip (top band)** is the new default. It shows the desktop dashboard's OWN header and primary cells (MARKET, BIAS,
    SIGNAL / STRUCTURE, LIQUIDITY, PRICE / MACRO, RISK, DECISION) folded into three columns at the top centre, with the
    MT5 plan on one line underneath: "LONG PLAN entry · SL · TP1 · TP2".
  - **Card** is the v57 phone card, unchanged. Nothing is removed: the desktop detail rows, H2 and the full plan stay in
    the Card layout and on desktop.
- **Size:** text is tiny (small at Text Size Medium / Large), so the band is about 18% of a phone's chart area in the
  preview (`audit/mobile_strip_preview_v60.png`, sample values from the operator's 16 Oct 13:09 screenshot).
- **Mechanism:** one cell writer, `tcb`. In Strip it maps desktop column k to (k % 3, 2 · int(k / 3) + row) and skips the
  detail rows. `refactor_check.py` executes that fold: 9 headers and 9 values on unique cells of the 3 × 6 grid, each
  header directly above its value, details skipped.
- **Token room, by identical-output rewrites** (`refactor_check.py`, executed):
  - the nine header cells become one loop (same names, same order; header width auto, the value row sets the column);
  - `tc` = `tcb` with no background;
  - the text-size mappings are computed once (`_szHd`, `_szSe`; all four Text Size values give the same sizes);
  - `color.new(#rrggbb, 0)` becomes `#rrggbb` (8 places, identical opaque colours).
- **Master:** 39,037 lexical tokens (2.08% under the limit). 0 dead, 0 structural, 0 values computed unseen.
- Compile NOT RUN on v60.

# Build v60 → v61 — review of the v60 chart run (F-A59)

The operator's 4H screenshots (2026-10-16) show v60 compiling: Master, Brief, Diagnostics, Visuals.

- **Cross-checked and consistent across scripts:**
  - the gates (Master "▲6/7 [✗Trend]" = Brief GATES);
  - the rolling WR (Master WR 16% / ROLL 17% = Diagnostics);
  - the levels (PDH 4177.46, PML 4110 = Visuals);
  - the gate funnel and vetoes (Diagnostics);
  - L/S/R (Master 39/33/26 vs Brief 40/34/26: the known F-A56 lag);
  - the H2 cell and the header widths.
- **Fixed (F-A59):**
  - "NaN" edges become "—" (Master `_si`, Diagnostics `f_dgI`).
  - The Master's analog lines are re-flowed to fit the SIGNAL column: "H/L 1st · BOS", then "MAE · calibration
    detail", then "Cal / Brier · IS WR n !FIT", then "edge S/H/L/M/C".
  - The Master shows the overfit flag **!FIT** (in-sample WR more than rolling + 15, the same rule as Diagnostics). On
    this chart it fires: IS 38% vs ROLL 17%.
  - Diagnostics: the header no longer says "v44"; the row "Decision log (control set)" is labelled as the twin's
    control-arm filter log.
  - Brief:
    - a crossed trigger reads "price through it: fires if this bar closes here";
    - layers with no data on the chart's timeframe read "— no data on this TF";
    - "1 bar ago";
    - TP2 is shown only when it differs from TP1;
    - the GOLD ARROWS grid defaults to Bottom Left.
- **Reviewed, not a bug:** "Macro BULL 82" while every macro arrow is ≈.
  - The score is the direction consensus: DXY falling, EURUSD and silver rising, the rest flat, weighted by |r| and
    normalised.
  - The arrows show the IMPACT magnitude, ≈ when |r| <= 0.25.
  - With weak correlations the macro case is unanimous but weakly coupled to gold today; the macro confidence (MED)
    carries that.
- **Tokens:** Master 39,056 lexical (2.02% under the limit); Brief 38,732; Diagnostics 39,652.
- Compile NOT RUN on v61.

---

# Build v61 → v62 — Master H2 SETUP disagreed with the H2 arm above 30M (F-A60)

The operator's v60 4H screenshots: Visuals' H2 card read TREND DOWN (1H 100, 4H 20, 1D 0) with a last SELL on 05-29;
the Master read H2 MIXED, last none yet. The POC matched (4163.12).

- **Cause:** the H2 block is byte-identical in the three files, but its inputs are not inside the fences.
  - The Master set `h2S1 = htf1hScore`, `h2S4 = htf4hScore`, `h2SD = htf1dScore`.
  - Those are the engine's availability-gated scores: 50 when the layer is not above the chart timeframe.
  - On a 4H chart, 1H and 4H were 50, so "2 of 3 agree" could not happen and the Master's H2 could never fire on 1H,
    4H or D charts.
  - Visuals and Strategy_H2 use the raw scores of the same requests (`h2HtfScore`, the same formula).
  - On 15M and 30M every layer is available, so the two always agreed there. 15M is the registered timeframe.
- **Fix (Master only, token-neutral):**
  - `int h2S1 / h2S4 / h2SD = htfTrendScore(...)` are the raw scores, computed once.
  - The engine reads `htf1hScore = htf1hAvailable ? h2S1 : 50` (and 4H / 1D), the same values as before.
  - The H2 block reads the raw ones, as the H2 arm does.
- **Checks:**
  - `h2_parity.py` now traces the inputs: one definition each, a score function applied straight to exactly one
    60 / 240 / D request, the request text the same in all three files, and `h2HtfScore == htfTrendScore` executed on
    625 cases (na and every ordering).
  - It FAILS on v61 (verified).
  - `refactor_check.py`: the engine's `htf1hScore / htf4hScore / htf1dScore` in v62 equal the v61 lines (12,000 cases).
    A deliberate mutation fails (1,642 mismatches).
  - `pine_exec.py` can now run a function whose body is an if / else expression (`htfTrendScore`).
- **Visible change:**
  - On 1H, 4H and D charts the Master's H2 SETUP now shows the same trend, signal, last signal and alert as Visuals'
    H2 card.
  - On 15M and 30M nothing changes.
  - The DECISION, the gates and the engine HTF scores are unchanged.
- **Unchanged:** Visuals, Brief, Diagnostics and the repo set (Brief and Diagnostics take their engine from the
  Treatment twin, which has no H2 block).
- **Tokens:** Master 39,056 lexical (unchanged, 2.02% under).
- Compile NOT RUN on v62.

---

# Build v62 → v63 — every timeframe and every input, executed (F-A61, F-A62, F-A63)

The operator asked for the code to run correctly on every timeframe, and for every input, default and calibration
setting to be verified. Two new tools execute that.

- **`tf_check.py`:**
  - It runs the timeframe-dependent code of each engine copy as written for 13 chart timeframes (1m … 1M).
  - **Sizing:** history sizes and offsets stay inside `max_bars_back`.
  - **Layers:** each higher-timeframe layer is live only above the chart. No raw higher-timeframe value is read
    without its gate (H2 excepted, F-A60).
  - **Sessions:** the session engine runs bar by bar over 2020–2027 with its `var` state, and its DST flags are
    checked against the IANA zones.
  - **Visuals:** its session shading must equal the engine's sessions.
- **`inputs_check.py`:** covers all 644 inputs in the nine files. Each default must be valid (bounds, step,
  options) and consistent across engine copies, and must equal the frozen v33 build in the five pre-registered files.
  Tooltips that state a default must be right. Lengths must have `minval >= 1`. Reviewed differences print with
  their reason; anything else fails.

**Fixed:**
- **F-A62 (P1), London DST.** It was wrong on up to 5 trading days a year (38 days over 2020–2027; 52,560 one-minute
  bars). The last Sunday of March / October is now computed from the date. The fix is in the Master, the three arms,
  Diagnostics, Brief and Visuals. Result: 0 errors on every timeframe; US DST was already correct. This changes
  `sessionQuality` on those days only, and so the entry gate, TQ and confidence there.
- **F-A61, length bounds.** EMA / ATR / ADX lengths now have `minval=1` in every engine copy and in Visuals. Typing 0
  no longer stops the script. No default changed.
- **F-A63, MTF display.** C / S / I print "—" for a layer that is not live, INST averages live layers only, and
  "Agree %" is over the live layers ("—" on D and above). It equals v62 wherever every layer is live.

**Identical-output rewrites:** `_htfBullCnt` / `_htfBearCnt` reuse `_inst*Cnt`, and `_agreeCount` reuses
`htfFull*`. `refactor_check.py` checks these on 12,288 cases.

**Defaults:** none changed. Every default in the pre-registered files equals the frozen build (`inputs_check.py`
check 3). The best results are not a reason to change a default: choosing defaults on this history is tuning
(AUDIT_PROMPT §9).

**Timeframe facts (not changed; they are the design):**
- The entry gate needs `sessionQuality >= 30`. A D / W / M bar opens at the 17:00 New York rollover and scores 13, so
  BUY / SELL cannot occur there. The DECISION shows the reason (`SESS 13/30`).
- The HTF veto needs 2 live layers of 15m / 1H / 4H / 1D, so it cannot fire on 4H and above.
- The registered timeframe is 15M.

**Tokens (lexical):** Master 39,035 (2.08% under the limit); Diagnostics 39,697 (≈ 99,840 compiled, 0.42% under);
Brief 38,777.

**Pre-registration:** F-A62 changes engine code in the arms. Under A7 every file on this branch is display only, and
the website on the default branch is the system of record, so nothing restarts and nothing here is counted. The
website was not touched.

Compile NOT RUN on v63.

---

# Build v63 → v64 — macro correlations measured over the same bar (F-A64)

The operator asked for every macro factor to be checked, then for the best fix for the real XAUUSD spot market.

- **Defect:**
  - `goldRet` is this bar's return. Every macro return is built from `request.security(…, close[1], …)`, so it is the
    bar before.
  - Each `ta.correlation(goldRet, <asset>Ret, n)` therefore measured gold now against the asset one bar earlier.
  - Model (`macro_check.py` B): a true +0.80 reads −0.003, and a true −0.60 reads +0.04. On a 15M chart the 1H assets
    change on 1 bar in 4, giving +0.18 for +0.80.
  - Affected:
    - the adaptive weights (`|avg corr|`), so the fixed-20 EURUSD weight dominated;
    - correlation health, which is 50% of macro confidence;
    - the arrow strength (the "every arrow ≈" screen).
  - Not affected: the vote directions.
- **Fix:**
  - Silver, EURUSD and SPX (chart timeframe) are paired with `goldRetL = goldRet[1]`.
  - DXY, US10Y and TIPS (macroTF) are paired with `goldRetM`, the chart symbol requested exactly as they are
    (macroTF, `close[1]`, lookahead_on).
  - Their windows are counted in macroTF bars (`_kM` = macroTF / chart TF), so a 1H series on a 15M chart keeps the
    sample size its significance threshold assumes.
  - A window over 4,500 bars (e.g. 120 hours on 1m) reads as no data.
  - Nothing reads an unfinished bar.
  - Applied to the Master and the three arms; Diagnostics and Brief rebuilt. One more request (`_gM`).
- **Paid for by identical-output rewrites** (`refactor_check.py`, 12,000 cases):
  - the valid-feed count is computed once (it was `_numStab`, `_numValid` and an inline sum in `macroStrengthConf`);
  - the session literals `int((25.0))` / `int((10.0))` become `25` / `10`.
- **Visible change:**
  - macro arrows and their strength, macro confidence and the weights now reflect the measured same-period
    relationship;
  - so the macro score, the evidence score, the TQ and the DECISION can differ from v63.
  - Directions, gates and thresholds are unchanged, and nothing was tuned.
- **Tokens (lexical):**
  - Master 39,056 (2.02% under the limit);
  - Diagnostics 39,718 (≈ 99,890 compiled, 0.37% under);
  - Brief 38,798.
- **Pre-registration:** A7, display only; nothing restarts. The website was not touched; whether its engine shares
  this construction was NOT checked from here.
- Compile NOT RUN on v64.

---

# Build v64 → v65 — each macro factor counted once (F-A65); five more gold drivers in the Brief

The operator approved options 1, 3 and 4 of the macro review. Option 1 (same-bar correlations) shipped in v64.

**Option 3, each factor counted once (F-A65; engine: Master, three arms, Diagnostics, Brief).**
- **USD:** DXY carries the dollar. EURUSD votes, weighs (by its |corr|, capped 30, instead of a fixed 20) and adds its
  ±5 momentum only when DXY has no data.
  - The score term is gated as well: with every |corr| at 0 the fallback weights still gave EURUSD 20, so the dollar
    would have been counted twice again.
  - `macro_check.py` C found this gap in the first pass (70 states) before the fix.
- **TIPS:** the layer is off while its symbol equals the 10Y yield's (the default `TVC:US10Y`). The tooltip says why,
  and that the daily `FRED:DFII10` belongs in the Brief, not in a 1H correlation.
- **Majority:** `_macroPool` = 4 + TIPS-as-own-feed + GC-when-valid, and the need is ceil(pool / 2): the same rule
  over independent factors. On the default settings that is 2 of 4 (3 of 5 with GC), where it was 3 of 6 (4 of 7).
- **Confidence:** availability is over the same feeds.
- **Diagnostics:** the V1 shadow uses the same majority.
- **Not changed:** the vote directions, the thresholds, the weights' caps for DXY / 10Y / silver / SPX, the momentum
  terms of DXY and the 10Y. Nothing was tuned.

**Room:** the 36 correlation lines are now one `f_cc3` call per asset. Each call expands to exactly the v64 lines;
`refactor_check.py` compares them with the v64 commit itself. Master 39,029 lexical (2.10% under the limit);
Diagnostics 39,713 (0.38% under).

**Option 4, five drivers in the Brief (display only: no vote, weight or gate; the DECISION is unchanged).**
- Rows 7–8 of the GOLD ARROWS grid add five drivers, each read as the engine reads DXY (`close[1]`, EMA10 / EMA20,
  lookahead_on):
  - USDJPY (`OANDA:USDJPY`, rising = gold down);
  - OIL (`OANDA:WTICOUSD`, rising = up);
  - REAL YLD (`FRED:DFII10`, daily, rising = down);
  - BREAKEVEN (`FRED:T10YIE`, daily, rising = up);
  - US 2Y (the engine's `y2Symbol`, rising = down).
- USDJPY and oil carry the same-bar correlation (v64 pairing), which scales the arrow as for DXY.
- The daily series show their level and direction only.
- Every symbol is an input, and a blank symbol is off.
- `macro_check.py` D executes the five cells (54 cases).
- The TIPS cell reads "off: same feed as 10Y"; the EUR cell says "confirms DXY" or "USD vote".
- Brief 39,603 lexical (≈ 99,600 compiled, 0.65% under); 22 request call sites (26 at runtime, the Pine limit is 40).

**Visible change:**
- the macro score, its confidence and the macro verdict can differ from v64, and through them the evidence score, the
  TQ and the DECISION;
- the Brief grid grows by two rows.

**Not verified here:** whether the free plan serves `OANDA:WTICOUSD`, `FRED:DFII10` and `FRED:T10YIE` (NOT RUN). An
unavailable one shows "—" / "no data".

**Pre-registration:** A7, display only; nothing restarts. The website was not touched.

Compile NOT RUN on v65.

---

# Build v65 → v66 — the five gold drivers in Visuals too (Master + Visuals = the everyday pair)

The operator: the free TradingView plan allows two indicators per chart. Merging the four chart scripts into two was
measured and is not possible without cutting features:
- Master, Brief and Diagnostics each carry the same ~34,600-token engine, at 98–99.6% of the per-script limit.
- Their unique parts (Brief panel 5,024, Diagnostics blocks 4,954, Visuals 9,861) do not fit beside it.

Plan, approved:
- Master + Visuals are always on the chart.
- Brief and Diagnostics are swapped into the second slot when needed. Nothing is deleted.

**v66:** the five drivers that only the Brief showed are copied into Visuals: USDJPY, oil, real 10Y yield, 10Y
breakeven and US 2Y (display only, as in v65).
- **The fence:** their whole definition (helpers, inputs, requests, same-bar correlation, arrow and text) sits
  between `// GD-BEGIN` and `// GD-END`. The block is byte-identical in `brief_panel.pine`, the Brief and Visuals.
- **The engine lines it reads:** `safeDiv`, `chartTFSeconds`, `_kM`, `_gM`, `goldRetM`, `_wM`, `_fM` are copied into
  Visuals from the Master, line for line.
- **The inputs:** `macroTF`, `y2Symbol` and `corrMedLen` keep the Master's names, defaults and bounds
  (`inputs_check.py` compares them).
- **Checks:** `macro_check.py` E checks the fence, the dependency lines and the panel wiring; a one-character
  mutation of the fenced block fails it. D now evaluates the fenced variables.
- **The Brief:** its five cells read the fenced values. It shows the same arrows and text as v65, and the four driver
  symbol inputs move to the group "GOLD DRIVERS (display only)".

**Visible change:**
- a "GOLD DRIVERS" panel in Visuals, bottom right by default (Bottom Center / Bottom Left / Middle Right / Hidden);
- in the Brief, the driver symbol inputs move to their own settings group.

**Unchanged:** no engine change, and the DECISION is unchanged.

**Tokens (lexical):** Visuals 11,221 (≈ 28% of the limit), 11 request call sites; Brief 39,643 (≈ 0.55% under).

Compile NOT RUN on v66.

---

# Build v66 → v67 — every value wired, in every file (operator rule, 2026-10-17)

Operator: "maintain all the features without deleting any feature or dead code; everything was added with a purpose,
so don't delete anything, look for its purpose and wire it up."

**Audit:** `deadcode.py --all` (new flag) listed the values a file computes but never shows.
- The Master was already clean (0 dead, 0 structural).
- **Visuals:** DI+ / DI− (`_diPV` / `_diMV`) were computed by `ta.dmi` but only ADX was used. They are now shown, with
  ADX, in the candle info panel. ADX itself had not been displayed in Visuals.
- **Stats-engine tuple slots** (`__ev __el __pf __cg __cb __iw __in __fs __fh __fl __fm __fc`): the Master shows all
  twelve (SIGNAL cell, EV, PF). Elsewhere:
  - **Diagnostics** read 9 and now also shows EV and PF on its "Analog evidence" row.
  - **Brief** read none; a new STATS row (Full layout) shows all twelve, formatted as the Master's.
  - **The three arms** read none; a new "Engine stats (display)" row on the forward-test scorecard, identical in all
    three arms, shows them. The A/B hunks stay at 5 and 4.
- **Companion-wired values** (computed in the Brief or an arm, displayed by Diagnostics): 63 names, each checked to be
  read by Diagnostics. 40 of them are also shown in the Master; the other 23 are engine extras the Diagnostics panel
  shows (order-block / FVG line handles, auction state, what-if stats, the WR interval text, data status, debug).

**Enforced:** `deadcode.py` has no exemptions any more (the `__` tuple-slot and named STRUCTURAL exemptions are
gone). Any unread value in any file fails the build; the v66 Visuals now fails it.

**Room for the new rows, without removing anything:**
- `(x ? 1 : 0)` → `_b1(x)` across the engine: 53 sites in the Master, 67 in each arm, outside the H2 block and
  `f_sessionIntel`.
  - `_b1` moves above the engine.
  - `refactor_check.py`: each engine file equals its v66 commit after that substitution only (13,744 lines). A
    one-argument mutation fails it.
- In the Brief panel:
  - the five timeframe cells go through `f_brT`;
  - the drivers' trend states are computed once (in the GD block, so Visuals gets the same edit);
  - the "x% " prefix is `f_brL`;
  - one position mapping serves both tables.
- `pine_exec.py` registers `_b1`; `refactor_check.py` asserts that it equals the file's own definition.

**Tokens (lexical):**
- Master 38,870 (2.5% under the limit);
- Diagnostics 39,573 (0.73% under);
- Brief 39,586 (0.70% under);
- Visuals 11,224.

**Visible change:**
- Visuals' candle panel shows "ADX x  DI+ y / DI- z";
- Diagnostics' Analog evidence row ends "EV ±x PF y";
- the Brief has a STATS row;
- the arms' scorecard has an "Engine stats" row.

**Unchanged:** the engine values. The DECISION is identical to v66.

Compile NOT RUN on v67.

---

# Build v67 → v68 — fit the compiler limit (F-A66, P0)

The operator pasted the v67 Master. TradingView reported `Compiled code contains too many tokens: 100335. The limit is
100256` (CE10117).

**Why the estimate was wrong:**
- The checks multiplied lexical tokens by 2.515, which gave ~97,800.
- TradingView expands every user-function call, so a helper called many times costs its body each time.
- v67's `(x ? 1 : 0)` → `_b1(x)` (53 calls in the Master) lowered the lexical count but raised the compiled one.
- The same holds for earlier helper rewrites (`_gS/_gC/_gF`, `tc`, `_m`, `_si`, v59–v61).
- Counting lexical tokens plus every call's expanded body (recursively) fits two compiler reports to 0.04%: v23
  (1.6197) and v67 (1.6190). v14 is an outlier at 1.5798.
- In that model a large function called once is counted twice (definition + expansion). The v67 Brief was over by the
  same model (~101,860) and had not been pasted yet.

**v68: nothing removed, every value and feature unchanged.**
- **Engine:** `_b1` rewrite undone in the Master and the three arms (the v66 engine text). The arms keep the v67
  engine-stats scorecard row.
- **Master:**
  - `f_dashData1`, `f_dashData2` and `f_dashRender` (one call each) sit at their call site, each in an `if true`
    block that keeps its locals private as the function did.
  - `_gS/_gC/_gF(i)` → `array.get(gDash*, i)`, `tc(...)` → `tcb(..., color(na), ...)`, `_m(x)` →
    `str.tostring(x + mt5Offset, "#.##")` (64 + 15 + 12 calls; not in the H2 block).
  - `fix_v68.py` holds the transformation. `refactor_check.py` requires the Master to equal `transform(v66 commit)`
    byte for byte, and every expanded helper to use each parameter exactly once.
- **Brief:**
  - The GOLD ARROWS grid is one `table.cell` in a loop over its 28 cells (names, arrows and texts pushed in cell order,
    cell 23 the CLIMAX cell as before), instead of 28 expanded `f_brA` / `f_brT` calls.
  - `brief_trace.py` and `macro_check.py` read the glyph / colour rule from the loop line.
- **Diagnostics:** rebuilt (engine text back to v66).
- **Visuals:** unchanged.

**Estimates** (`compile_est.py`, new; the gates are best-fit ≤ 98% of the limit and pessimistic < 100%):

| Script | best-fit | pessimistic |
|---|---:|---:|
| Master | 92,500 | 99,000 |
| Brief | 96,600 | 98,700 |
| Diagnostics | 94,800 | 97,500 |
| Visuals | 25,700 | 30,100 |
| Arms | ~84,000 | ~84,000 |

The tool puts the v67 Master at 100,340–100,380 (actual 100,335) and the v60 Master at about 99,300–99,500 (compiled).

**Visible change:** none. The same cells, text and values as v67.

Compile NOT RUN on v68: the compiler is the judge, and a reported figure goes into `compile_est.py`'s CALIBRATION.

**Calibration added after v68 (operator, 2026-10-17): "V66 was also working fine".** The v66 Master (39,029 lexical)
compiled; the v67 Master (38,870 lexical, fewer) reported 100,335. This refutes lexical × ratio outright. The expansion
model has the v66 Master at 100,100–100,200 (under) and the v67 Master at 100,340–100,380 (over): it agrees with both.
The v68 Master is the v66 Master plus changes that only lower the expanded count, so it should compile with more room
than v66. `compile_est.py` now also checks every confirmed compile (KNOWN_UNDER: v60, v66).
The operator also confirmed the **v66 Brief compiled**. The model put it at ~101,000 best-fit and ~104,400 pessimistic,
so for the Brief the model is cautious (by ≥ 0.7%). That is the safe side, and the v68 Brief is lower under both models.
`compile_est.py` lists each confirmed compile (v60 Master, v66 Master, v66 Brief) as INFO.

---

# Build v68 → v69 — the Master's main body back under its limit (F-A67, P0)

**Operator's v68 paste:**
- **Brief, Visuals and Diagnostics:** compiled. The Brief shows a "Heavy script" notice: it is close to the free plan's
  20 s run-time limit. That is a warning, not an error.
- **Master:** failed, `The main body of the script is too long. Try wrapping code in functions` (CE10295).

**Cause:** v68 inlined `f_dashData1`, `f_dashData2` and `f_dashRender` to save compiled tokens. That moved their code
into the main body: 23,732 → 28,122 lexical tokens outside function definitions. TradingView limits the main body
separately; the largest that compiled is 26,538 (v68 Diagnostics).

**v69:**
- The three functions stay functions (`fix_v68.transform(..., inline_one_call=False)`).
- The Master is the v66 Master (which compiled) plus only the small-helper write-outs (`_gS/_gC/_gF`, `tc`, `_m`):
  - main body 23,794 (v60: 23,796, compiled);
  - model 99,000–99,540, against v66 at 100,100–100,200 (compiled).
- `refactor_check.py` derives it from the v66 commit byte for byte.
- Nothing is removed, and no value or display changes. The Brief, Visuals, Diagnostics and arms are unchanged from v68.

**Gates (`compile_est.py`), now evidence-based:**
- both models below the limit and no higher than a build that compiled;
- main body ≤ 26,538.

They fail the v67 Master (tokens) and the v68 Master (main body).

Compile NOT RUN on v69.

---

# Build v69 → v70 — every macro factor in the Master (operator: "all macros can be adjusted in master")

The operator's v69 paste compiled (Master, plus the v68 Brief / Diagnostics and the v67 Visuals). These are recorded in
`compile_est.py` KNOWN_UNDER.

**What the Master shows now:**
- The five gold drivers the Brief and Visuals show (USDJPY, oil, real 10Y yield, 10Y breakeven, US 2Y) are in the
  MACRO detail cell: `JPY▼ OIL≈ RY≈ BE▼ 2Y▲`, the same arrows as the grid.
- Their full text (direction, level, same-bar r) is that cell's hover tooltip.
- They come from the same GD block as Visuals and the Brief, byte-identical (`macro_check.py` E now includes the Master).
- They are display only: no vote, weight or gate, and the DECISION is unchanged.

**How it fits (nothing removed, every output the same):**
- **Dashboard cells:** f_dashRender's 20 `tcb(...)` calls are queued as `DCell` records (a Pine type).
  `f_dashFlush` writes them with tcb's own `table.cell`.
- **Plan panel and phone card:** the same queue for the 8 `tcp` calls and the 9 `_bc` calls, flushed right after the
  last call of each block by tcp's / _bc's own `table.cell`. Nothing else writes those tables in between, so the order
  is the same.
- **The GD block:** leaner. Seven helpers used only inside it are written out at their uses: `f_brQ`, `f_brV`,
  `f_brUp/Dn`, `f_brRv`, `f_brN`, `f_brL`.
  - Each correlation is still computed every bar and gated afterwards.
  - Same in Visuals and the Brief.
- **The Brief's GOLD ARROWS grid:** drawn by `f_brGrid()`, its unchanged body in a function. This keeps ~900 tokens
  out of the main body, which the leaner block had pushed above 26,538.
- **Derivation:** `fix_v70.py` holds the Master transformation. `refactor_check.py` requires the Master to equal
  `fix_v70.transform(fix_v68.transform(v66 commit), GD block)` byte for byte.
- **Tools:** `trace.py` and `undeclared.py` now understand `type` blocks.

**Size** (`compile_est.py`):

| Script | best-fit | pessimistic | main body |
|---|---:|---:|---:|
| Master | 99,616 | 98,467 | 24,932 |
| Brief | 97,938 | 98,265 | 25,439 |
| Visuals | 25,091 | 29,683 | 9,653 |
| Diagnostics (unchanged) | 94,845 | 97,450 | 26,538 |

The Master's figures are between those of the v69 (99,542 / 99,004) and v66 (100,204 / 100,109) Masters, both of which
compiled.

Compile NOT RUN on v70.

---

# Build v70 → v71 — F-A68: the v70 Master failed to compile; the drivers stay, without a user-defined type

**Compiler report (operator's v70 paste, 2026-10-18):**
- Master v70: `Compiled code contains too many tokens: 103989. The limit is 100256` (CE10117).
- The Brief v70, Visuals v70 and Diagnostics v68 compiled. The v70 Brief is recorded in `compile_est.py` KNOWN_UNDER.

**Cause (F-A68):**
- `compile_est.py` had said 99,616. v70's only new construct was the `DCell` record type (37 `DCell.new` calls).
- The 4,373 missing tokens are 73.0 raw tokens per constructor call. TradingView expands a UDT constructor at every
  call, as it does a user function, so the queue cost more than the ~2,000 tokens it saved.
- `compile_est.py` now counts UDT constructors (73.0 best fit, 69.4 pessimistic, fitted on this report). It lists the
  v70 Master in KNOWN_OVER and fails if the model ever puts it under the limit again.
- CLAUDE.md: no user-defined types in chart scripts.

**v71 Master** — rebuilt from the v69 Master, which compiled (`fix_v71.py`); nothing removed, every output the same:
- **Dashboard (20 `tcb` calls, 28 cells):**
  - Each cell pushes only its text, text colour and background onto three arrays. One loop at the end of
    f_dashRender writes them with tcb's own condition and `table.cell`.
  - The calls are unconditional and in a fixed order, so cell j is col `j % 9` and row `int(j / 9)`, or (8, 3) for the
    last cell. Its size and width follow from the row and column.
  - `fix_v71.py` asserts this for every call. `refactor_check.py` executes the loop's expressions against all 28 cells
    of the v69 calls.
- **Plan panel:** the 8 `tcp` calls push text and background; the column is the queue index and the size is `_pSz`.
- **Phone card:** the 9 `_bc` calls (some conditional) push all five arguments.
- No other code writes those tables between a queue's first push and its loop.
- **Gold drivers:**
  - The same GD block as Visuals and the Brief.
  - The MACRO detail cell ends `JPY▲ OIL≈ RY≈ BE▼ 2Y▲`.
  - The hover text is set with `table.cell_set_tooltip` where the cell is drawn: desktop / tablet, not Strip or Mobile
    (tcb's own condition).
- **Derivation:** `refactor_check.py` requires `Master == fix_v71.transform(fix_v68.transform(v66 commit), GD block)`
  byte for byte.

**Size** (`compile_est.py`):

| Script | best-fit | pessimistic | main body |
|---|---:|---:|---:|
| Master v71 | 99,602 | 98,605 | 25,045 |
| *v69 Master (compiled)* | *99,542* | *99,004* | *23,794* |
| *v70 Master (FAILED at 103,989)* | *103,989* | *103,989* | *24,932* |

Visuals, Brief, Diagnostics and the arms are unchanged.

Compile NOT RUN on v71.

---

# Build v71 → v72 — the v71 Master failed too (104,510); the Master goes back to v69

**Compiler report (operator's v71 paste, 2026-10-18):** `Compiled code contains too many tokens: 104510. The limit is
100256` (CE10117). `compile_est.py` had said 99,602.

**What this shows (F-A68 revised):**
- v71 had no record type, and it came out 521 tokens HIGHER than v70. So the record-type explanation is refuted.
- Beyond the v69 Master (which compiled), v70 and v71 share two things: the GD block and a cell queue. The model misses
  4,400-4,900 tokens there, and the cause is not identified. The model's record-type term is removed.

**v72:**
- **Master:** the v69 file, byte for byte (SHA `1f9e48dc…`), which compiled. Its stamp still reads v69, because that is
  the build of its content.
- **The five gold drivers** stay on screen in Visuals, which is always on the chart beside the Master, and in the Brief.
- **`compile_est.py`:** lists the v70 / v71 failures in KNOWN_OVER and prints the model's miss on every run. It FAILS a
  Master that contains the GD block.
- **`macro_check.py` E:** the GD block must be identical in the panel source, the Brief and Visuals, and absent from the
  Master.
- **`refactor_check.py`:** back to its v69 form (Master == `fix_v68.transform(v66)`).
- `fix_v70.py` / `fix_v71.py` are kept as the record and are not applied.

Compile: the Master is the same bytes as the v69 Master, which the operator compiled. **Confirmed (operator, 2026-10-18): v72 Master compiled and runs (5,882 lines).**

---

# Build v72 → v73 — Visuals: one terminal panel instead of three cards (operator: "professional layout, institutional level")

**Before:** Visuals drew three cards, each in its own style:
- CANDLE, top right. This is where the Master's dashboard sits.
- H2, middle left.
- GOLD DRIVERS, bottom right. This is where the Master's trade plan sits.

**v73: one docked panel, `TERMINAL PANEL` (default: Middle Left, Standard detail).**
- **Title bar:** `XAUUSD · <timeframe>` and the bar time in UTC.
- **Three sections:**
  - **MARKET:** price O H L C, then range / ATR / ATR%, then flow (RVOL, ADX, DI+ / DI-).
  - **H2 SWEEP → VALUE:** signal, trend, value, swings, sweep, next; with the H2 layout set to Full, also session,
    history and volume.
  - **GOLD DRIVERS:** USDJPY, oil, real yield, breakeven, US 2Y.
- **Footer:** "display only · the DECISION is the Master's · H2 record: the website".
- **One palette:** grey labels, white values, colour only for direction (teal up / supports gold, red down), and
  thin borders.
- **Compact detail:** price + flow, signal + next, and the five drivers as one line (`JPY▲ OIL≈ RY≈ BE▼ 2Y▲`) with the
  detail on hover.
- **Sections follow the cards' own switches:** Show candle info panel / Show H2 signals and card / Gold drivers
  panel = Hidden.
- **The three v72 cards are unchanged and selectable** (Panel layout = Separate cards (v72)). Nothing is removed.

**Checks:**
- `panel_check.py` (new):
  - each H2 row in the panel has the card's own text expression and colour;
  - the drivers use the card's glyphs and colours;
  - every candle value is printed;
  - the rows fit the table.
- Mutation-tested: a changed colour and a swapped driver text each FAIL.
- The H2 and GD blocks are untouched (`h2_parity.py`, `macro_check.py` E).

**Confirmed (operator, 2026-10-18): Visuals v73 compiled and draws the panel** (MARKET hidden there: the chart has
"Show candle info panel" off, so the section follows that switch).

Visuals size: best-fit 30,306 / pessimistic 36,126 (limit 100,256). Master, Brief, Diagnostics and the arms are
unchanged. Compile NOT RUN on v73.

---

# Build v73 → v74 — Visuals: the gold drivers under the Master's MACRO column (operator: "look like one feature")

**What changes on the chart:**
- **The five gold drivers sit directly under the Master dashboard's MACRO cell**, in its column width, background and
  detail text size.
  - The header is `GOLD DRIVERS <net arrow>`.
  - Then one cell per driver: `USDJPY ≈` with its text on the line below.
  - The Master's macro information and the drivers read as one block.
- **The terminal panel** (market + H2) moves to **bottom left**, the lower area. Its drivers section is left out while
  the drivers are docked.

**How it lines up:**
- The Master's dashboard has fixed geometry: top right on Desktop / Auto (top left on Tablet), no border, no frame, and
  column widths 10/10/12/11/13/10/11/11/13 % of the chart × Density (0.8 / 1.0 / 1.25).
- Visuals' docked table uses the same anchor and frame and the same nine widths. Its column 6 therefore lands exactly
  under MACRO, at every chart width.
- Row 0 is a transparent spacer, **Gap below the Master dashboard** (% of chart height, default 17). The Master's height
  depends on its text, so this is the one value to adjust.
- `dashMode`, `textSize` and `density` are the Master's own inputs, copied (same names, options and defaults).
  `inputs_check.py` holds them equal, and they must be set as in the Master.
- Not docked with the Master on Mobile. Set **Gold drivers placement = In the panel / card** to bring them back into
  the terminal panel or the separate card.

**Checks:**
- `panel_check.py` 5 reads the widths, Density scaling, anchor, frame and detail text size from the Master's own code
  and requires Visuals to reproduce them. It also checks that each driver cell reads its own value and text.
- Mutation-tested: one width changed, or one driver text swapped, each FAIL.

Visuals size: best-fit 32,002 / pessimistic 38,376. Master, Brief, Diagnostics and the arms are unchanged. Compile and
the on-screen alignment are NOT RUN on v74 (TradingView renders the tables; only a screenshot confirms the fit).

---

# Build v74 → v75 — Visuals: the H2 card and liquidity / sweeps docked under the Master (operator: "like the macro indicators")

**What changes on the chart:** each block sits under its matching Master column.

| Master column | Docked below it (Visuals) |
|---|---|
| LIQUIDITY | **LIQUIDITY · SWEEPS** (new view of existing values): PDH/PDL, PWH/PWL, PMH/PML, CDH/CDL, each with its distance from price (TradingView prices, as the level tags); the last pivot sweep (the ✕ markers) and the last H2 sweep |
| MACRO | GOLD DRIVERS (v74) |
| DECISION | **H2 SWEEP → VALUE**: the H2 card's signal, trend, value, swings, sweep, next and note |

**Each dock is its own table with its own gap** (% of chart height). The Master's DECISION column is the tallest (its
H2 SETUP cell), so the H2 dock defaults to 30 %. LIQUIDITY and MACRO default to 17 %.

**H3:** on the website (the system of record), arm **H3 "Sweep-to-Value" is the TradingView line's H2 rule**,
pre-registered there under that name (`quantum/arm_h3.py`). It is the same signal, so the H2 dock is labelled
"website: arm H3, same rule". No separate H3 signal exists on the chart.

**Behaviour:**
- The bottom-left terminal panel leaves out whatever is docked, and is drawn only while it still has a section.
- New inputs in group `DOCK UNDER THE MASTER (v75)`:
  - H2 card placement and H2 gap;
  - Liquidity & sweeps placement (under LIQUIDITY / in the panel / hidden) and Liquidity gap.
- With the Master on Mobile, nothing docks: H2 and liquidity go back into the panel.
- The gold-driver, layout and Master-matching inputs moved up the file so the H2 card can read them (same names and
  defaults).
- The only new state is `pvLastSweep`, the last ✕ marker's level and time. Everything else displays values Visuals
  already computes.

**Checks:**
- `panel_check.py` 5 covers all three dock tables: the anchor, frame and widths come from the Master's code, and every
  dock cell uses the shared spacer and width.
- `panel_check.py` 6 (new):
  - the H2 dock's six rows are the card's own text and colour, plus its note;
  - the liquidity dock and the panel's LIQUIDITY section show all eight levels and both sweeps.
- Mutation-tested: a changed colour or a dropped level each FAIL.

Visuals size: best-fit 36,518 / pessimistic 44,030. Master, Brief, Diagnostics and the arms are unchanged. Compile and
the on-screen alignment are NOT RUN on v75.

---

# Build v75 → v76 — H2 card: the last signal's age, outcome and LIVE / STALE (operator: "market going up but H2 says sell")

**Why:**
- The SIGNAL row showed the LAST H2 signal with no age. On 18-19 Oct it still read `SELL 10-16 02:30 UTC` while price
  rose, which looked like a live sell.
- H2's trend is a 2-of-3 vote of the completed 1H / 4H / 1D bars. 1H 80 / 4H 20 / 1D 0 = DOWN, so H2 can only sell
  there. It is a fade setup: it sells a failed push above a swing high.
- Nothing was wrong in the rule. The display was ambiguous.

**What changes on the chart** (the H2 card, the terminal panel's H2 section and the H2 dock under DECISION):
- The SIGNAL row gains a status line, for example `○ STALE · 47 bars · 2 d ago · stopped · trend no longer DOWN`, or
  `● LIVE · 3 bars · 1.5 h ago · TP1 hit`.
- A stale signal is grey; a live one keeps its green / red.
- **Outcome:** on each confirmed bar after the signal, the bar's range is checked against the signal's own stop, TP1 and
  TP2 (TradingView prices). If one bar touches both the stop and a target, the stop is taken first: the order inside a
  bar is unknown, so this is the conservative reading. After TP1, a stop reads "TP1 hit, then stop".
- **STALE** = closed (stopped, TP2, or TP1 then stop), older than **Mark the last H2 signal stale after (bars)** (new
  input, default 24, display only), or H2's trend vote no longer agrees with the signal's direction.

**Unchanged:** the H2 rule and the H2 block (byte-identical, `h2_parity.py`), the alerts, the Master, and the website's
arm H3. The Master's own H2 SETUP line has no age; the Master has no token room.

**Checks:**
- `h2_age_check.py` (new) runs the v76 block line by line over 400 random paths (19,565 bars) against an independent
  Python reference: 0 mismatches, and every outcome exercised.
- Mutation-tested: target-before-stop, or evaluating unconfirmed bars, each FAIL.
- `panel_check.py` maps the grey stale colour across the card, panel and dock.

Visuals size: best-fit 37,198 / pessimistic 44,933. Compile NOT RUN on v76.

---

# Build v76 → v77 — F-A69: the liquidity and gold-driver docks were hidden; all docks in one table

**Operator's v76 screenshot (2026-10-20):**
- Visuals v76 compiled. The H2 dock under DECISION showed the new status line (`○ STALE · 213 bars · … · stopped`).
- But nothing appeared under LIQUIDITY or MACRO.

**Cause:**
- The three docks were three tables, all at `position.top_right`.
- TradingView displays one table per position per script, the last one created, so only the H2 dock showed.
- This is a rendering rule; none of the static checkers model it.

**v77:**
- **One dock table, `dkT`:**
  - column 4 = LIQUIDITY · SWEEPS;
  - column 6 = GOLD DRIVERS;
  - column 8 = H2 SWEEP → VALUE;
  - one transparent spacer row.
- **One gap: "Dock gap below the Master dashboard"**, default 25 % (the v76 screenshot puts the Master's DECISION column,
  its tallest, ending at ~23 %).
  - The v75 per-dock `lqGap` / `h2Gap` inputs are gone: one table has one spacer, so they could not work.
  - The rows line up as a second band under the Master's dashboard.
- **Corners:** in the separate-cards layout, the candle card's "Top Right" moves to middle right while any dock is on,
  since the docks take that corner. The Terminal position tooltip warns that the docks take Top Left with the Master on
  Tablet.
- **`panel_check.py` 5:** now requires exactly one dock table, no other top-right table, and the candle card's move.

Values, rows, colours and the H2 rule are unchanged. Visuals only. Compile / rendering NOT RUN on v77.

**Confirmed (operator's v77 screenshot, 2026-10-21):**
- Visuals v77 compiled.
- All three docks render in one band under the Master: LIQUIDITY · SWEEPS under LIQUIDITY, GOLD DRIVERS under MACRO,
  and H2 SWEEP → VALUE (STALE, stopped) under DECISION. Each is aligned to its column.
- The rows share heights across the band, so the liquidity and driver cells are spaced to the taller H2 rows.

---

# Build v77 → v78 — the dock band's rows tightened (operator: "tighten the spacing … save space")

**Why the gaps:**
- The three docks are one table, and a table's rows share heights: every row is as tall as its tallest cell.
- Two H2 cells set the height. The H2 header was 2 lines where the others were 1, and the SIGNAL cell was 4 lines (the
  signal's 3 lines plus the v76 status line) where every liquidity and driver cell is 2.
- So the liquidity and driver lines sat with blank space between them.

**v78:**
- The H2 header is one line: `H2 SWEEP → VALUE · 15 · = website H3`.
- The SIGNAL text is split into two 2-line cells, rows 2 and 3, in the same colour. Their text, joined, is exactly the
  card's `"SIGNAL  " + h2SigCard + h2SigStat`.
- The other H2 rows move down one, rows 4-9.
- Every row of the band is now 2 lines (headers 1), so the liquidity and driver cells sit tight.
- Each driver keeps its own colour, and nothing is merged or removed.
- The band ends where H2 ends. The liquidity and driver blocks end four rows earlier.

**Checks:**
- `panel_check.py` 6 now requires:
  - the split text is exactly the card's SIGNAL text;
  - both cells take the card's SIGNAL colour;
  - every dock cell is at most 2 lines and every header 1. A `"\n"` inside `str.replace_all` does not count, since it
    removes line breaks.
- Mutation-tested: a 2-line header, or swapped SIGNAL colours, each FAIL.

Visuals only. The gap stays at 25 %, which the v77 screenshot shows clearing the Master's DECISION column. Compile /
rendering NOT RUN on v78.
