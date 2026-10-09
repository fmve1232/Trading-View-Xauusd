# Build changelog — v1 → … → v43

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
