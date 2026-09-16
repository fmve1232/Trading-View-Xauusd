# Findings raised by the Python parity work

Findings that originate in **this** repository, against the Quantum 5.0 build
vendored under `reference/quantum_5_0/`. They continue the upstream numbering in
`Trading-View-Xauusd/audit/FINDINGS_TRACEABILITY.md`, which ends at F-A16.
`F-A14` is taken by `audit/FORENSIC_AUDIT_Q5.md`.

Classification follows the upstream scheme:
`BUG` · `STAT` statistical correction · `NUM` numerical stability ·
`PRES` presentation · `DESIGN` design assumption, not a defect.

| ID | Severity | Class | Summary | Status |
|---|---|---|---|---|
| F-A17 | **HIGH** | `STAT` | F-021 was applied to regime classification but not to the liquidity-reach score bump, which still thresholds the **rounded** composite and reaches expected value at 20% weight | **OPEN** |
| F-A18 | MEDIUM | `PRES` | EdgeCases A3 and A6 carry pre-F-021 expected values, so the harness reports `2 FAIL / 72` on TradingView | **OPEN** |

Neither is fixed here. This repository does not modify the Pine source — the
vendored artefacts are hash-pinned and CI fails if they move. Both fixes are
behaviour changes to a live trading script and are the operator's call.

---

## F-A17 — F-021 is only half applied `HIGH` `STAT`

### What F-021 did

F-021 moved the regime **classification** off the rounded composite and onto the
raw one. `Master.pine` L1891–1896:

```pine
float regimeCompositeRaw = (regimeScore * 0.30) + (volRegime * 0.15) + (structureRegime * 0.20) + (macroRegime * 0.20) + (sessionRegime * 0.15)
regimeComposite = int(math.round(regimeCompositeRaw))

bool strongTrend   = regimeCompositeRaw >= 70
bool moderateTrend = regimeCompositeRaw >= 40 and regimeCompositeRaw < 70
bool weakTrend     = regimeCompositeRaw < 40
```

That is correct, and the edge-case harness A7 asserts it: the boundary is 70,
not 69.5.

### What it did not do

`regimeComposite` — the **rounded int** from L1892 — is still the value compared
at `Master.pine` **L2274**, and identically at `Strategy.pine` /
`Strategy_OLDGATES.pine` **L2218**:

```pine
baseScore += regimeComposite >= 70 ? 8.0 : regimeComposite >= 40 ? 4.0 : 0.0
```

Because `math.round` is half **away from zero**, a raw composite of `69.50`
rounds to `70`. So in the same bar, on the same composite:

| Raw composite | `strongTrend` (L1894) | `baseScore` bump (L2274) |
|---:|---|---|
| 69.49 | false — moderate | +4.0 |
| **69.50** | **false — moderate** | **+8.0 — strong** |
| 70.00 | true — strong | +8.0 |

The same inconsistency exists at the lower boundary: a raw composite in
`[39.50, 40.00)` classifies as weak and scores as moderate, `+4.0` instead of
`+0.0`.

### Why it matters

`baseScore` is not display-only. The chain is:

```
L2274  baseScore       += regimeComposite >= 70 ? 8.0 : ...
L2278  liqReachScore   := clamp(baseScore, 5, 95)
L4441  fEvBase         += nz(liqReachScore, 50) * 0.20
```

So the discrepancy reaches **expected value at 20% weight**, in the Master and
in **both** A/B arms. At the boundary the error in `fEvBase` is `4.0 * 0.20 =
0.8` points.

The effect is bounded and it is not random: it fires on a specific, recurring
band of composite values, and it always pushes EV **up**.

### Why the harness did not catch it

Group A of the harness models `regimeCat` on L1894–1896 only. A7 therefore
proves F-021 closed *for classification* and says nothing about L2274. This is
precisely the caveat the harness states about itself:

> DOES NOT PROVE: that the Master is WIRED to these expressions.

### Proposed fix — not applied

Change L2274 (Master) and L2218 (both arms, identically) to threshold the raw
composite, matching L1894–1896:

```pine
baseScore += regimeCompositeRaw >= 70 ? 8.0 : regimeCompositeRaw >= 40 ? 4.0 : 0.0
```

This is a **behaviour change**: it alters `fEvBase` on bars in the boundary
bands, so it changes which trades clear the EV gate. Per `CLAUDE.md` it must go
to both arms identically to keep the A/B diff at its five hunk headers, and per
`AUDIT_PROMPT.md` §9 it must not be accompanied by any threshold retuning.

Note also `Master.pine` L3005 / L3007, where the V1/V2 divergence detector
compares **rounded** composites:

```pine
if (regimeCompositeV1 < 40) != (regimeComposite < 40)
```

Lower severity — it is a diagnostic, not a gate — but it can miss a genuine
divergence, or report one that does not exist, when the two raw composites
straddle a rounding boundary. Fix it in the same pass or record why not.

### Pinned as an executable statement

`tests/test_edge_case_parity.py::test_f021_is_not_closed_everywhere_in_the_master`
asserts the **defect**, deliberately. It fails the day L2274 changes, which
forces this entry to be closed in the same commit rather than drifting.

---

## F-A18 — two harness assertions are stale `MEDIUM` `PRES`

### The defect

`XAUUSD_Quantum_5_0_EdgeCases.pine` L80–81 defines:

```pine
regimeCat(float _raw) =>
    _raw >= 70 ? 0 : _raw >= 40 ? 1 : 2     // 0 strong, 1 moderate, 2 weak
```

Then L86 and L89 assert:

```pine
chk("A3  raw 39.51 -> category", i(regimeCat(39.51)), "1", "STAT")
chk("A6  raw 69.51 -> category", i(regimeCat(69.51)), "0", "STAT")
```

Evaluate them: `39.51 >= 40` is false, so `regimeCat(39.51)` is `2`, not `1`.
`69.51 >= 70` is false, so `regimeCat(69.51)` is `1`, not `0`.

**Both assertions fail.** They are only correct under the *pre*-F-021
behaviour, where the composite was rounded before comparison —
`round(39.51) = 40 → 1` and `round(69.51) = 70 → 0`.

When F-021 was applied, A2, A5 and A7 were updated and A3 and A6 were not. The
file's own header says the group was "UPDATED FOR F-021"; two of its six
boundary cases were missed.

### Consequence

The harness renders `2 FAIL / 72` on TradingView, permanently, with two red
rows that are not defects in the engine. Two standing red rows in a diagnostic
table is worse than a single wrong value: it teaches the reader that red in
this table is normal.

This finding was produced by the Python port, not by reading the file — the
transcription was faithful and the suite went red. That is the port earning its
place.

### Proposed fix — not applied

```pine
chk("A3  raw 39.51 -> category", i(regimeCat(39.51)), "2", "STAT")
chk("A6  raw 69.51 -> category", i(regimeCat(69.51)), "1", "STAT")
```

And, because the interesting boundary moved from 39.5/69.5 to 40/70, add the
cases that actually probe it now — `39.99 → 2`, `40.00 → 1`, `69.99 → 1`,
`70.00 → 0`. The Python port already carries these, in
`test_regime_boundaries_are_40_and_70_after_f021`.

Adding cases means the row count moves off 72; the table is already sized for
100 rows, and `tests/test_edge_case_parity.py::test_case_count_matches_the_pine_harness`
must be updated in the same commit.

### Pinned

A3 and A6 are marked `xfail(strict=True)` in the port, with `xfail_strict = true`
in `pyproject.toml`. If the Pine harness is corrected, the unexpected pass
**fails CI**, which is the signal to update the port and close this entry
together.
