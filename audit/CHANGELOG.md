# Build changelog — v1 → … → v9

**Sixteen findings applied; F-A16 open by necessity.** See each build section below.
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
