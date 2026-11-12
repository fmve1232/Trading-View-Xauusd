# R14: Yahoo auxiliary data in the engine: revisions, version flips and decision-time volume (read-only)

**Status: investigation only.**
- No engine, data layer, threshold, registration, record or freeze-key change.
- Store snapshots stayed in the session's scratch space; no vendor data is committed.
- All times are UTC.
- A study protocol for approval is in `R14_STUDY_PROTOCOL_PROPOSAL.md`.

## 1. Data and tools
**Snapshots.** Twelve production store snapshots with clean provenance:
- ten consecutive runs on 12 Nov (3090–3099; store commits 00:06–02:21), from the local clone's reflog of
  `market-data`;
- two runs on 10 Nov (store commits 06:51 `1909d4b` and 07:21 `33bc795`).

Other local store copies have no provenance record and were **not** used.

**Tools** (all in `audit/tools/`, read-only):
- `aux_revision_census.py` counts revised closed bars per series, with volume separated from price.
- `aux_revision_ab.py` runs the full production code path offline on one snapshot, with every auxiliary series replaced
  by another snapshot's version. XAU/USD stays byte-identical. `price` / `volume` modes swap only one kind.
  - The path covered: download from the store with fetches disabled, `build_market`, features, the treatment /
    control / challenger engines, `report.build`.
- `aux_revision_summary.py` builds the per-timeframe tables.
- `aux_volume_completeness.py` runs the decision-time volume counterfactual (§6).

**Controls:**
- **Harness null check:** re-saving the series unchanged gives 0 differences in 5 TFs × 3 arms and the payload (twice).
- **Reproduction:** a re-run reproduced byte-identical results.
- **Same-version pairs:** these give near-zero effects.

## 2. Why gold-futures volume is the spot volume
- **Documented deliberate difference D-07** in `docs/PLATFORM.md`, present since the first web version (`febc34914`,
  26 Sep).
  - Pine uses OANDA tick volume.
  - The Python port uses "COMEX GC futures volume, bar for bar; missing = 0 (counted)", described as "real traded
    volume".
- **The spot source has no volume.** The Twelve Data XAU/USD rows in the store have an empty `volume` column.
- **Code:** `quantum/data/market.py` `build_market` sets `raw["volume"] = gc_chart["volume"]` on the spot bars.
- **Where that volume is used:**
  - VWAP and its bands;
  - the volume profile (VAH / VAL / POC, which place many plan stops and targets);
  - `high_volume`;
  - the volume gates in the engine: break of structure ×1.2, break of active support / resistance ×1.0, displacement
    ×1.3, relative volume / climax.
- **GC also feeds the GC confirmation layer** (`gc_confirms_*`, which counts in the macro score), through values
  shifted by one bar.

## 3. Census: what revises (12 snapshots, 11 transitions)
| Transition | Hours | XAU price bars | GC price bars | GC volume bars | of which volume only | Silver price / volume | DXY / EURUSD / US10Y / S&P price |
|---|---|---|---|---|---|---|---|
| normal (7 transitions) | 0.2–0.5 | 0–1 | 1–5 | 2–5 | 0–1 | 1–4 / 2–4 | 0–1 / 0 / 0–6 / 0 |
| **version flip** (3092→3093, 3093→3094, 3094→3095, 3095→3096) | 0.2–0.3 | 0–1 | **9,724–9,730** | **8,083–8,090** | **2,811–2,814** | **5,203–5,207 / 5,270–5,277** | 20–21 / 37–45 / 198–204 / 9 |
| 10 Nov 07:21 → 12 Nov 00:06 | 40.8 | 1 | 9,598 | 7,973 | 2,765 | 5,190 / 5,198 | 20 / 37 / 198 / 9 |

- **Two versions, confirmed.** Snapshots of the same version differ by only 1–12 bars:
  - 3092 ↔ 3094 ↔ 3096;
  - 3093 ↔ 3095.
- **Yahoo alternates between two versions of the history.** Version A was served on 3090–3092, 3094, 3096–3099;
  version B on 3093 and 3095.
- **What a flip changes:**
  - GC volume moves on about 8,085 bars, by a median of 0.37% (small changes on many bars);
  - 2,811 of those bars change volume only.
- **Normal runs change only the newest 1–3 bars.** Their volume changes by a median of 29–116%, because those bars are
  still filling (§6).
- **XAU/USD (Twelve Data):** 0–1 revised closed bar per run, as the manifest reports.

## 4. Engine impact of a version flip (4 flips, both directions, two independent flip pairs)
Treatment arm, the alerting engine. The two flip pairs agree to the bar; the reverse direction is the mirror image.

| | 15m | 30m | 1h | 4h | 5m |
|---|---|---|---|---|---|
| Live decision at the last bar | unchanged (WAIT) in all 4 | unchanged | unchanged | unchanged | unchanged |
| Signals (bar, direction, entry) | 67 = 67 | 38 ↔ 39 | 91 = 91 | 50 = 50 | 233 = 233 |
| Entry of a matched signal | identical (it is the XAU close) | identical | identical | identical | identical |
| Same signal, SL changed (max $) | 5 ($0.01) | 1 ($1.03) | 13 ($0.28) | 19 ($9.51) | 7 ($0.00) |
| Same signal, TP changed (max $) | ($0.00) | ($0.02) | ($0.28) | ($9.51) | ($0.03) |
| Calibrated probability: bars changed | 4,561–4,564 of 6,447 | 2,089 of 3,685 | 2,869 of 4,194 | 652 of 1,094 | ~11,870 of 12,520 |
| … p95 / max change (percentage points) | 0.54 / 9.8 | 0.15 / 2.1 | 0.70 / 9.9 | 1.35 / 6.2 | 0.72 / 40.8 |
| … at the live bar | up to 1.08 pp (56.63 → 57.71%) | 0 | ≤ 0.04 | 0.42 | ≤ 0.23 |

- **One signal exists in one version only:** the historical 30m SELL of 28 Sep 15:00, the same in every flip. The
  challenger arm also has it, plus one 1h signal replaced by another. The control arm never changes.

**Attribution** (flip 3093 → 3094, one kind swapped at a time):

| Swapped | Signal existence | SL / TP changes | Calibrated probability (p95 pp; live 15m) |
|---|---|---|---|
| volume only | unchanged | **all of them** (5 / 1 / 13 / 19 / 7) | 0.01–0.37; **46.83 → 47.69%** |
| prices only | **the 30m signal** | none | 0.15–1.35 (most of the variance); 46.83 → 46.83% |

**Conclusion of the attribution.**
- Plan levels move because of the GC **volume** revisions, through the volume profile.
- The historical signal and most probability changes come from the **price** revisions of silver, DXY, US10Y and the
  GC confirmation layer.

**Same-version and normal pairs** (3092 ↔ 3097, 3090 → 3091, 3097 → 3098, 3098 → 3099, 3096 → 3097):
- no signal, level or live-decision change;
- probabilities change on at most 45 15m bars (3092 ↔ 3097, five hours apart) and on 0–1 bar in consecutive runs;
- **but that one bar is the live bar.** The live 15m probability moved 1.75 pp (3097 → 3098, 23.86 → 22.11%) and 0.42 pp
  (3098 → 3099). In a normal pair the only volume that changes is the newest bar's, which is still filling, so this is
  the decision-time completeness effect of §6, not a version effect.

**Long horizon** (10 Nov data against 12 Nov data, truncated to the 10 Nov read; about 42 hours apart). Both 10 Nov
snapshots are version B (the 06:51 → 07:21 pair is normal; 07:21 against 12 Nov 00:06, version A, is flip-sized).

| Pair | What differs in the auxiliary data | Treatment arm: signals and levels | Live bar (decision; calibrated probability) |
|---|---|---|---|
| 10 Nov 06:51 → 07:21 (normal) | 1 bar per series | no change | WAIT = WAIT; 15m 33.74 → 34.13% |
| 10 Nov 06:51 with 12 Nov 00:50 (3093), **same version B** | GC 15m: 47 bars revised (44 on 1–2 Sep, the oldest end of Yahoo's window; 3 on 10 Nov, the newest), one bar (04:45) missing at the read and filled later, and **the decision bar 06:30: 531 contracts at the read, 851 final (62%)** | no signal change; one 30m SL $1.13 | WAIT = WAIT; **15m 33.74 → 40.80% (+7.06 pp, the largest change on any bar)**; 5m 33.18 → 33.41% |
| 10 Nov 07:21 with 12 Nov 01:50 (3097), version A | a flip, plus the 15m decision bar 07:00 at 68% (895 → 1,322) and **the newest GC 5m bar (07:10) at 0 contracts at the read (427 final)** | as in the flips: the 30m signal of 28 Sep appears, 19 4h SL / TP changes (max $9.51) | WAIT = WAIT; 15m 43.24 → 43.25%; **5m 36.26 → 44.77% (+8.5 pp)**; 4h 47.27 → 43.24% (−4.0 pp, the version effect) |

- **What the same-version comparison shows:**
  - Over two days, the history of one version is not static. It revises a few bars at the far end of Yahoo's window, and
    it fills in bars that were missing.
  - It is the **decision-time completeness** of the newest bar that moves the live probability. This is a real
    production read, not a simulation (§6).
- **The same incompleteness does not always move the probability.** The 07:21 15m decision bar was 68% complete, and
  the probability changed by 0.01 pp; the 06:51 bar was 62% complete and it moved 7.06 pp. The effect depends on where
  the volume sits relative to the 20-bar mean and the gates.

## 5. What a flip means for the registered records
- Forward results are recorded at decision time and never recomputed, so B15, B9, SETUP-LIVE and the holdout ledgers
  keep what was decided.
- **A flip affects reproducibility.**
  - The same history yields slightly different site statistics and probabilities from one run to the next.
  - A live decision could differ if a flip coincided with a decision near a threshold. In 4 flips × 5 timeframes no
    live decision changed.

## 6. Decision-time volume completeness (a separate and larger effect)
**What the snapshots show.** The newest GC bars are incomplete when the pipeline reads them. Same-version pairs, the
volume at read time as a share of the next run's value:

| Series | Age of the bar at read time | Share of the final volume |
|---|---|---|
| GC 15m (the 15m engine's decision bar) | 4–6 min | **46–77%** (median about 64%). 9 of 9 incomplete: 7 on 12 Nov, plus 62% and 68% on 10 Nov. |
| GC 5m, newest bar | about 5 min | once 0% (10 Nov 07:21: 0 at the read, 427 final) |
| GC 5m | 9–11 min | 48–94% (median 82–93%) |
| GC 5m / 15m | ≥ 14 min | 100% (final) |
| GC 1h | 4–6 min | about 90–92% |

- **When the read happens** (step times of run 3123, the 08:01 slot):
  - dispatch at 08:01:18, one minute after the 15m bar closes;
  - the unit-test step runs 08:01:45–08:04:42;
  - the pipeline step, which downloads the data, runs 08:05:05–08:06:20;
  - the store commit is at 08:06:25.

  The read is therefore about 5 minutes after the close. The ages in the table use the store commit time minus 90 s.
- **Cause (inferred):** Yahoo's COMEX data is delayed, so the bar that has just closed is still filling when it is read.
- **The backtest and every historical statistic see final volumes. Live decisions see incomplete ones.**
- **Gate-level proxy** (15m, last 6,000 bars; final vs decision-time volume, with the bar's own volume in its 20-bar
  mean):

  | Completeness | `volume > 20-bar mean` | ×1.2 | ×1.3 |
  |---|---|---|---|
  | final | 42.1% of bars pass | 31.2% | 27.3% |
  | 77% | 28.4% | 18.7% | 15.4% |
  | **64% (median)** | **18.5%** | 11.9% | 9.7% |
  | 46% | 8.7% | 4.9% | 3.9% |

- **Engine-level counterfactual** (`aux_volume_completeness.py`, treatment arm). History is cut at each historical signal
  bar and at an equal number of random non-signal bars, and the engine is re-run. With final volume every signal must
  reproduce (the engine is causal); then the bar's volume is scaled to the measured completeness.
  - **Setup.** Store of 12 Nov 02:21 (run 3099). 15m treatment arm, last 3,000 bars (about 7 weeks): 21 signal bars and
    21 random non-signal bars.
  - **Check.** With final volume, all 21 cut runs reproduce the full run's signal exactly: direction, entry, SL, TP1 and
    trade quality. All 21 control bars stay without a signal. The tool reports both as `exact_with_final_volume` and
    `control_clean_with_final_volume`.

  | Decision-bar volume | Signals kept | Lost on their bar (95% CI) | Levels changed | New signals on control bars |
  |---|---|---|---|---|
  | final | 21 | 0 | 0 | 0 |
  | 77% | 19 | 2 (10%; 1–30%) | 4 | 0 |
  | **64% (median measured)** | **18** | **3 (14%; 3–36%)** | 5 | 0 |
  | 46% | 18 | 3 (14%; 3–36%) | 5 | 0 |

  - **Counted per idea.** The 21 signal bars form 5 runs of signal bars (gaps of up to 4 bars). **At 64%, 3 of the 5
    runs start one bar later** than in the history. No run disappears.
  - **Which signals are lost.** All SELL, and each is the **first bar** of a run of consecutive signal bars:
    - 28 Sep 14:30 (lost at 46% and 64%, kept at 77%);
    - 1 Oct 08:30;
    - 10 Nov 16:15, the signal used in PR #98's replay.
  - **The next bar still fires in all three.** At that bar the earlier bar's volume is final. In live operation the first
    alert of the idea would therefore come one bar (15 minutes) later, at a different entry:
    - $7.21 lower (4,124.00 → 4,116.79, worse for a SELL);
    - $3.03 higher (4,150.32 → 4,153.35, better);
    - $5.15 lower (4,024.98 → 4,019.83, worse).

    How the alert layer presents the earlier bar's signal, once it appears in the history, is not tested here. It would
    be about 20 minutes old, the case that the stale-signal gate handles.
  - **Level changes are small.** Trade quality changes by 2 points on 2 signals. The SL moves by at most $0.38 at 64% and
    $0.58 at 46%, through VWAP and the volume profile. TP1 does not change.
  - **No signal is created** by lower volume. That is expected: the volume gates are "volume above a multiple of the
    mean".

- **1h** (the same store, last 1,500 bars, 33 signal bars and 33 control bars; the 1h decision bar is about 90%
  complete):
  - all 33 signals are kept;
  - 5 SL values move by at most $0.23;
  - no new signal.
  - The exact-reproduction check passed again: 33 of 33 signals and 33 of 33 control bars.
- **Reading.** The completeness effect matters for the **15m engine**, which is the engine that alerts in production
  (sixty mode). At 1h it is negligible.

## 7. Limitations
- **Snapshots:** twelve production snapshots, all from 10 and 12 Nov.
  - Version flips were seen only on 12 Nov 00:36–01:35 and in the 10 → 12 Nov comparison.
  - The flip frequency over weeks is unknown.
- **Missing inputs offline:** FRED (DFII10, DGS2) and CFTC were unavailable, for both arms alike. This is a common-mode
  difference from production.
- **Completeness ratios** come from 7 same-version pairs in one night session (12 Nov 00:00–02:20) and two reads on
  10 Nov (06:51, 07:21). Volume completeness may differ in the London and New York sessions.
- **The counterfactual scales only the decision bar's volume.** At decision time the bar before is also slightly
  incomplete on 5m, so the effect is, if anything, understated.
- **One uniform completeness per run.** The real completeness varies from bar to bar (46–77% measured on 15m).
- **Small samples.** 21 signal bars in 5 runs, on one timeframe's last 3,000 bars, give wide intervals (3–36% for 3 of
  21).
- **No result here says the live engine is wrong or right.** It shows that live and historical inputs differ, and by how
  much.

## 8. Changed production risk
| Risk | Before | Now |
|---|---|---|
| R14 version flips | unmeasured | measured: levels and probabilities move, one historical signal, no live decision in 20 checks; MEDIUM–LOW |
| **R18 (new): decision-time volume completeness** | unknown | The decision bar's GC volume is about 64% complete when the site reads it (§6). History and the backtest see final volume. At 64%, 3 of 21 historical 15m signal bars do not fire on their bar, and 3 of 5 ideas start 15 minutes later at a different entry; none disappears. On the real 10 Nov 06:51 read, the live probability was 7.06 pp lower than with final volume. This is a live / backtest input mismatch. It is also an undocumented difference from the Pine reference, which reads complete tick volume at the close. D-07 documents the volume source, not its incompleteness. By the repository's rule (CLAUDE.md: any difference not listed in PLATFORM.md is a bug) it is a defect. Any fix changes frozen code and needs an amendment. **MEDIUM–HIGH until measured across sessions** (protocol M7). |
| R16 volume revisions unlogged | known | confirmed: the census shows about 8,000 GC volume revisions per flip that `manifest.py` never records |
| PR-E (run the test gate once per commit, roadmap rank 3) | proposed for speed | **would make R18 worse:** without the 3-minute test step the read would move to about 2 minutes after the close. Do not pursue before R18 is resolved. |
