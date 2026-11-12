# R14 study protocol: PROPOSAL for the operator's approval (not registered)

**Status: proposal only.**
- It is not a registration and amends no registration.
- It adds nothing to `research/trials.jsonl`.
- It changes no engine, data layer, threshold, record or the freeze key.
- If approved, it would run read-only, as the measurements in `R14_AUX_REVISIONS_2026-11-12.md` did.

## 1. Question
Yahoo serves two alternating versions of the auxiliary history (GC and silver futures, DXY, EURUSD, US10Y, S&P). How
often, and by how much, does that change what the engine **decides at decision time**?
1. Does it change the live signal or decision at the last closed bar?
2. Does it change the level of a live plan (entry, SL, TP)?
3. Does it change the calibrated probability shown with it?
4. Is the effect driven by the volume or the price revisions?
5. **Decision-time completeness (added after the first measurements):** how complete is the decision bar's GC volume
   when the site reads it, per trading session? How often does the difference from the final volume change the live
   decision, plan levels or probability? The 9 measured 15m decision bars (7 on 12 Nov, 2 on 10 Nov) were 46–77% complete (median about 64%).
   The backtest and all historical statistics see final volume.

**This is a data-integrity measurement, not a strategy test.** No edge is estimated, and no threshold is tuned.

## 2. Why the existing data cannot answer it fully
- The market-data store is force-pushed as one orphan commit per run, so earlier versions disappear.
- The ledger keeps per-file SHA-256 (`manifests/state.json`) and price revisions only, never volume (R16).
- The measurements so far rest on the 12 snapshots that happened to be kept locally:
  - ten runs on 12 Nov 00:01–02:16;
  - two on 10 Nov.
- In those, the version flipped four times in a row and decisions were never at a threshold.

## 3. Data collection (read-only, outside the production workflow)
- **One read-only collector workflow** on a development branch, manually dispatched or on a sparse cron. It is *not*
  `quantum-site` and has no secrets beyond `GITHUB_TOKEN`.
- **What it keeps.** It clones `market-data` and keeps the auxiliary series only when their combined hash is not yet
  stored. Two versions are known today, so retention stays small. Kept as workflow artifacts, 90 days.
- **What it never touches:** the store or the ledger.
- **Duration:** 4 weeks, or 20 distinct flip events, whichever is later. A flip event is a pair of consecutive runs
  whose auxiliary hashes differ in more than 1,000 bars.
- **Vendor data stays out of the repository**, in artifacts only.
- **For M7, a small per-run record.** For GC and SI (5m, 15m, 30m, 60m), it keeps the newest four bars: their
  timestamps and volumes, and the store's commit time. The final value comes from the first record at least 30 minutes
  later. The record is a few kB per run, in artifacts.

## 4. Measurements per flip event (`audit/tools/aux_revision_ab.py`, unchanged method)
| # | Metric | Arms |
|---|---|---|
| M1 | Live decision at the last closed bar, per timeframe (15m, 30m, 1h, 4h, 5m) | treatment, challenger, control |
| M2 | Signal existence on all historical bars (lost / gained), per timeframe | the three arms |
| M3 | For matched signals: \|Δ entry\|, \|Δ SL\|, \|Δ TP1 / TP2 / TP3\| in $ | the three arms |
| M4 | Calibrated probability: bars changed, median / p95 / max \|Δ\| in percentage points, and at the last bar | treatment |
| M5 | Attribution: M1–M4 with only the volume swapped, and with only the prices swapped | treatment |
| M6 | Counterfactual for every live engine signal recorded during the window: re-run its decision bar with the other version; would the signal, its SL / TP or its alert have differed? | treatment |
| M7 | Decision-time completeness: the decision bar's volume at the read as a share of its final volume, per series and per session (Asia 22–07, London 07–12, New York 12–21 UTC). Then the counterfactual of `audit/tools/aux_volume_completeness.py` at each session's measured median and p10: signals lost or gained, levels changed, and the shift of the live probability. Also every live engine signal of the window re-run with final volume. | treatment |

**Controls in every batch:**
- the harness null check (re-saving the series unchanged must give 0 differences);
- one same-version pair (normal revisions only).

## 5. Pre-declared reading (decides what to propose next; changes nothing by itself)
| Finding over the window | Reading | What would be proposed |
|---|---|---|
| M1 and M6 never differ, M3 \|Δ\| ≤ $0.50 at p95, M4 ≤ 1 pp at p95 | noise for decisions | document; bookkeeping only (PR-H: record volume revisions) |
| M1 or M6 differs in ≥ 1 event, or M3 > $0.50 at p95, or M4 > 1 pp at p95 | material | a data-layer amendment for approval. Options: keep the first stored version of closed auxiliary bars, or take volume from a non-revising source. **Either restarts the frozen holdout and needs a new amendment.** |
| M7: median completeness ≥ 95% in every session, and the counterfactual changes no live decision | immaterial | document only |
| M7: median < 95% in any session, or the counterfactual loses or gains ≥ 1 signal | material: live and historical inputs differ | an amendment for approval, choosing one option. **Options (b) and (c) restart the frozen holdout.** (a) Keep the engine; label on the site and in alerts that live volume gates are stricter than in history (display only). (b) Read the volume gates on the last *complete* bar (an engine change). (c) Wait until the GC bar is final. This makes every signal about 20 minutes old, i.e. DELAYED, so it is not recommended. |

**Statistics:** counts with exact (Clopper-Pearson) 95% intervals per event type. There is no hypothesis test and no
p-value hunting.

## 6. What this study does not do
- It does not change how forward results are counted. They are recorded at decision time and stay as recorded.
- It does not touch B9, B15, SETUP-LIVE, the holdout or B24 (B24 stays OFF).
- It does not tune any threshold, weight or gate.

## 7. Cost and effort
- **GitHub Actions:** the collector runs about 2 minutes, a few times a day; free on a public repository.
- **Artifacts:** about 15 MB per distinct version, a handful of versions.
- **Offline analysis:** about 4 minutes per flip event on 4 cores.
- **Effort:** half a day to set up the collector, then a weekly batch and a final report.

## 8. Approval needed
1. The collector workflow (new, read-only, on a development branch).
2. The pre-declared reading in §5.
3. Whether the study should later be entered in the research registry (it is not entered now).
4. The M7 per-run record (§3) and the M7 reading (§5).
