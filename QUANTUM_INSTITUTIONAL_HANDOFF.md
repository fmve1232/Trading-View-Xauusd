# Quantum Institutional — handoff

The Python platform that treats this repository's Pine artefacts as its
reference layer. The full Phase 0 repository is in
[`quantum-institutional/`](quantum-institutional/), ready to be published as its
own GitHub repository.

**Nothing in `artefacts/` was modified.** The five Pine files are byte-identical
to build v12 / commit `b5fd337`, and the new repository verifies that in CI
before any other job runs.

---

## Publishing it

The GitHub App available to this session cannot create repositories — it lacks
`Administration: write` on the account, so `POST /user/repos` returns
`403 Resource not accessible by integration`. Two steps, locally:

**1. Create the empty repository** at <https://github.com/new>

- Name: `quantum-institutional`
- Visibility: **Public** (as chosen)
- Do **not** add a README, `.gitignore` or licence — the tree already has them

**2. Push this directory as its initial commit**

```sh
git clone --branch claude/quantum-institutional-repo-79ba4w \
  https://github.com/fmve1232/Trading-View-Xauusd.git /tmp/tvx
cd /tmp/tvx/quantum-institutional

git init -b main
git add -A
git commit -m "Phase 0: Quantum Institutional scaffold with Quantum 5.0 as reference layer"
git remote add origin https://github.com/fmve1232/quantum-institutional.git
git push -u origin main
```

CI runs on that first push: reference integrity, ruff, strict mypy, and the test
suite on Python 3.11 and 3.12.

### Before you publish, read this

The repository is public and it **vendors the Quantum 5.0 Pine source**, so the
gate logic, the evidence composite and the calibration design become
world-readable and permanently cloneable. That was a deliberate choice. If it
should not be, make the repository **private** at step 1 — it is reversible in
that direction and not in the other.

## Verified before handoff

Executed, with output, not asserted:

| Check | Result |
|---|---|
| `sha256sum -c` on the vendored artefacts | **PASS** — 5/5, hash set identical to `audit/MANIFEST.sha256` |
| Test suite | **PASS** — 212 passed, 2 xfailed (strict) |
| `ruff check` | **PASS** |
| `ruff format --check` | **PASS** — 79 files |
| `mypy` (strict) | **PASS** — 35 source files |

§86 acceptance stands at **0 of 27**. Quantum 5.0 parity is **NOT ESTABLISHED** —
that is the Phase 6 gate, and nothing downstream should start before it.

---

## Two new findings against build v12

Both were produced by porting the edge-case harness to Python. Neither is fixed:
this repository's artefacts are the hash-pinned reference, and both are
behaviour changes to a live trading script. Full detail and proposed patches in
[`quantum-institutional/docs/FINDINGS.md`](quantum-institutional/docs/FINDINGS.md).

### F-A17 — F-021 is only half applied · `HIGH` · `STAT` · **OPEN**

F-021 moved the regime **classification** onto the unrounded composite
(`Master.pine` L1894–1896):

```pine
bool strongTrend = regimeCompositeRaw >= 70
```

It did **not** move the liquidity-reach score bump. `Master.pine` **L2274**, and
identically `Strategy.pine` / `Strategy_OLDGATES.pine` **L2218**, still compare
the **rounded** value from L1892:

```pine
baseScore += regimeComposite >= 70 ? 8.0 : regimeComposite >= 40 ? 4.0 : 0.0
```

`math.round` is half away from zero, so a raw composite of `69.50` rounds to
`70`. In the same bar, on the same composite:

| Raw | `strongTrend` (L1894) | `baseScore` bump (L2274) |
|---:|---|---|
| 69.49 | moderate | +4.0 |
| **69.50** | **moderate** | **+8.0 — strong** |
| 70.00 | strong | +8.0 |

The same split exists at the lower boundary: `[39.50, 40.00)` classifies weak and
scores moderate.

**It is not display-only:**

```
L2274  baseScore     += regimeComposite >= 70 ? 8.0 : ...
L2278  liqReachScore := clamp(baseScore, 5, 95)
L4441  fEvBase       += nz(liqReachScore, 50) * 0.20
```

So it reaches **expected value at 20% weight**, in the Master and both A/B arms.
At the boundary the error in `fEvBase` is `0.8` points, and it is always upward.

The harness missed it because Group A models `regimeCat` on L1894–1896 only — the
exact caveat the harness states about itself: *"DOES NOT PROVE: that the Master
is WIRED to these expressions."*

Proposed fix: threshold `regimeCompositeRaw` at L2274 / L2218. This is a
**behaviour change** — it must go to both arms identically to keep the A/B diff
at its five hunk headers (`CLAUDE.md`), and no threshold may be retuned
alongside it (`AUDIT_PROMPT.md` §9).

Also worth a look in the same pass: `Master.pine` L3005 / L3007, where the V1/V2
divergence detector compares **rounded** composites and can therefore miss a real
divergence, or report one that does not exist, at a boundary.

### F-A18 — two harness assertions are stale · `MEDIUM` · `PRES` · **OPEN**

`EdgeCases.pine` L80–81 defines `regimeCat` on the **unrounded** composite, then
L86 and L89 assert:

```pine
chk("A3  raw 39.51 -> category", i(regimeCat(39.51)), "1", "STAT")
chk("A6  raw 69.51 -> category", i(regimeCat(69.51)), "0", "STAT")
```

`39.51 >= 40` is false, so `regimeCat(39.51)` is `2`, not `1`. `69.51 >= 70` is
false, so `regimeCat(69.51)` is `1`, not `0`. **Both fail.**

Those WANT values are correct only under the *pre*-F-021 rounding behaviour
(`round(39.51) = 40 → 1`). When F-021 was applied, A2, A5 and A7 were updated;
A3 and A6 were missed, although the file's header says the group was "UPDATED
FOR F-021".

**Consequence: the harness renders `2 FAIL / 72` on TradingView.** Two permanent
red rows that are not engine defects, which teaches the reader that red in that
table is normal.

Proposed fix: `A3 → "2"`, `A6 → "1"`, and add cases at the boundary that now
matters — `39.99 → 2`, `40.00 → 1`, `69.99 → 1`, `70.00 → 0`. The row count then
moves off 72; the table is already sized for 100 rows.

Both findings are pinned by tests in the new repository that **fail if the Pine
source is corrected without closing the finding in the same commit**.

---

## What the Python side actually contains

| | |
|---|---|
| Pine v6 semantics in Python | four divergences that are silent in a direct transcription, each demonstrated from both sides |
| Edge-case port | all 72 assertions (§60); known defects reproduced, not fixed |
| Point-in-time access | `publication_time` filtering, lookahead tripwire that raises |
| Contracts | UTC enforced at construction; volume carries its type |
| Validation / aggregation / chunking | §11, §12, §61 |
| API | 3 endpoints real; 14 return `503 DATA_UNAVAILABLE` naming their phase |
| Database | 24-table PostgreSQL schema with version stamping throughout |
| Docs | the §87 planning set, parity plan, divergence register, findings |

### The four Pine/Python divergences

| Expression | Pine | Python | If unhandled |
|---|---|---|---|
| `round(2.5)` | `3` | `2` (banker's) | every exact `.5` boundary classifies differently |
| `max(5, na)` | `na` | `5.0` | a missing value silently becomes a real number |
| `exp(250000)` | `inf` → sigmoid `0` | `OverflowError` | crash on input Pine handles |
| `7 / 2` (ints) | `3` | `3.5` | not reproducible by transcription at all |

The second is the one to watch: Python's `max` is correct for one argument order
and wrong for the other, with no error and no NaN downstream to notice later.

## Next step

Phase 6 parity, per
[`quantum-institutional/docs/PARITY_PLAN.md`](quantum-institutional/docs/PARITY_PLAN.md).
It needs exported TradingView series from the Master — **including the input
OHLCV**, not only the engine outputs. Parity measured against a separately
sourced XAUUSD history measures the feed difference, not the engine.
