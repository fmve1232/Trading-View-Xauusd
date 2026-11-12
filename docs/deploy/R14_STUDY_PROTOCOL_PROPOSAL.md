# R14 study protocol: Yahoo auxiliary-data revisions and decision-time volume (PROPOSAL v2, not registered)

**Status: proposal for the operator's review. Not approved, not registered, not started.**
- It amends no registration and adds nothing to `research/trials.jsonl`.
- It changes no engine, `config.py`, data layer, threshold, record or the freeze key.
- **It is a data-integrity measurement, not a strategy test.** It estimates no edge, win rate or P&L, and tunes no
  threshold, weight or gate.
- v1 (12 Nov) listed the questions and metrics. v2 adds the hypotheses, data, sample sizes, method, statistics and
  protections the operator asked for.

## 1. Background (pilot results, exploratory)
- **Volume source.** The website's spot bars carry COMEX GC futures volume from Yahoo (`docs/PLATFORM.md` D-07, since
  26 Sep). The reason: Twelve Data's XAU/USD rows have no volume.
- **That volume enters the engine through:**
  - the volume gates (×1.0, ×1.2, ×1.3);
  - `high_volume`;
  - VWAP;
  - the volume profile, which places many plan stops and targets.
- **Two effects were found in a pilot** (`R14_AUX_REVISIONS_2026-11-12.md`):
  1. **Version flips.** Yahoo alternates between two versions of the auxiliary history. A flip changes stops and
     targets (up to $9.51 on 4h) and probabilities (≤ 1.35 pp at p95). It never changed a live decision (20 of 20 checks).
  2. **Decision-time completeness (R18).** The decision bar's GC 15m volume is 46–77% complete when the site reads it
     (9 of 9 bars). In a counterfactual at 64%, 3 of 21 historical 15m signals do not fire on their bar.
- **Pilot status.** The pilot is **exploratory**. The thresholds in §7 were written after seeing it. For that reason
  **the confirmatory reading uses only data collected after approval**; the pilot is reported separately.

## 2. Research questions and hypotheses
All hypotheses are **materiality** statements for data integrity. Each is read against pre-declared thresholds (§7),
not with a significance test.

| # | Question | Null hypothesis (immaterial) | Endpoint |
|---|---|---|---|
| Q1 | Does a version flip change what the alerting engine decides live? | A flip never changes the live 15m treatment decision (signal or no signal, direction) at the last closed bar. | **E1 (primary):** share of flip events with a changed live 15m treatment decision |
| Q2 | Does a flip move plan levels? | For matched signals, \|ΔSL\| and \|ΔTP1–3\| ≤ $0.50 at p95. | M3 |
| Q3 | Does a flip move the probability shown? | \|Δ calibrated p\| ≤ 1 pp at p95, at the live bar. | M4 |
| Q4 | Is the effect from volume or price revisions? | descriptive | M5 |
| Q5 | How complete is the decision bar's volume at the read? | descriptive, by session | **E2 (primary):** median completeness of the GC 15m decision bar, per session |
| Q6 | Does incomplete volume change live decisions? | With final decision-bar volume, the live 15m treatment decision never differs; live-p shift ≤ 1 pp and \|ΔSL\| ≤ $0.50 at p95. | **E3 (primary):** share of production reads whose live 15m decision differs (M7b) |

- **Primary scope:** the treatment arm on 15m, the engine that alerts in production (sixty mode).
- **Secondary, descriptive only:** 5m, 30m, 1h and 4h, and the control and challenger arms.

## 3. Data
**Sources (read only):**
- the production market-data store (branch `market-data`), one commit per site run:
  - Yahoo auxiliary series: GC=F and SI=F (5m, 15m, 30m, 60m; GC also 1d); EURUSD=X and ^GSPC (5m–60m); DX-Y.NYB and
    ^TNX (60m); ^VIX (1d);
  - Twelve Data XAU/USD (5m–1d), which serves as the unchanged reference;
- the site runs' step times from the GitHub Actions API, giving the read time.

**Pilot sample (done; exploratory):**
- **12 snapshots:** 10 consecutive runs on 12 Nov 00:06–02:21 (3090–3099), plus 10 Nov 06:51 and 07:21.
- **Engine history inside each snapshot** (MAX_BARS-limited):

  | Timeframe | Bars | From |
  |---|---|---|
  | 5m | 12,520 | 9 Sep |
  | 15m | 6,447 | 5 Aug |
  | 30m | 3,685 | 22 Jul |
  | 1h | 4,194 | 2 Mar 2026 |
  | 4h | 1,094 | 2 Mar 2026 |

  All run up to 12 Nov.

**Prospective sample (if approved):**
- **Length:** at least 4 weeks **and** at least 20 flip events, with a hard stop at 8 weeks. If the stop comes first,
  the report uses what exists and says so.
- **Expected volume:** about 96 site reads per market day, so about 1,900 reads in 4 weeks.

**Number of version comparisons:**

| | Pilot (done) | Prospective (planned) |
|---|---|---|
| Consecutive-snapshot census | 11 transitions: 4 flips, 6 normal, 1 cross-version over 41 h | every consecutive pair of reads (≈ 1,900) |
| Engine A/B (full production path) | 14: 4 flips, 6 same-version or normal, 2 long-horizon, 2 attribution (+ null checks) | every flip event up to 40, one direction each (the pilot showed the reverse is the mirror image); 1 same-version control + 1 null check per weekly batch; attribution (volume only, price only) on every 5th flip |
| Completeness counterfactual | 15m: 42 bars × 4 levels; 1h: 66 bars × 2 | every read (M7b), plus session-level scaling (M7a) |

## 4. Methods
### 4.1 Revision census, volume measured apart from price
For each consecutive pair of snapshots (A read at t_A, then B) and each series:
- **Scope:** only bars that had **closed** by t_A (open time + interval ≤ t_A) and exist in both are compared. A forming
  bar finishing is not a revision.
- **What is counted:**
  - **price changed:** any of open, high, low or close differs by more than 1e-6;
  - **volume changed:** \|Δvolume\| > 1e-6;
  - **volume only:** volume changed while all four prices are equal;
  - **removed:** closed bars of A missing in B;
  - **gap-filled:** bars at or before t_A that are present in B and missing in A. Today's tool does not yet count these;
    the count is to be added.
- **Size of a revision:** the relative volume change \|v_B − v_A\| / v_A (for v_A > 0), reported as median and max,
  together with the newest changed bar.
- **Flip event:** a transition with more than 1,000 revised closed GC bars.
  - In the pilot, normal transitions revised 8–23 closed bars over all series together.
  - Flips revised about 28,600, of which about 9,700 were GC price bars and 8,100 GC volume bars.
- **Version labels** (A or B) are assigned by clustering. Each snapshot is compared with the first snapshot of each known
  version, and a new label is created only when it differs from all of them by more than 1,000 bars.
- **Tool:** `audit/tools/aux_revision_census.py` (read-only), unchanged except for the gap-filled count.

### 4.2 Decision-time completeness
- **Read time:** the start of the site run's "Run pipeline" step, taken from the Actions API. The pilot used the
  store commit time minus 90 s.
- **Decision bar:** for each read and for GC 5m, 15m and 60m, the newest bar whose close is at or before the read
  time.
- **Completeness** = the volume at the read divided by the final volume.
  - The final volume is taken from the first read at least 30 minutes after the bar's close, and must be confirmed
    unchanged by the next read. The pilot shows bars are final after about 14 minutes.
  - A bar missing at the read, or with volume 0, counts as 0% and is also reported separately. Missing volume enters
    the engine as 0 (D-07).
- **Strata:**
  - sessions by the bar's close time: Asia 22:00–07:00, London 07:00–12:00, New York 12:00–21:00 UTC;
  - weekday;
  - the daily shut and weekends are excluded.
- **M0, coverage (descriptive).** The share of engine bars with volume 0 per timeframe. In the pilot:
  - 30m: 30.7%, of which 1,072 bars come before GC 30m data begins on 25 Aug;
  - 1h: 6.5%; 4h: 2.7%; 15m: 1.8%; 5m: 0.5%.

### 4.3 Engine impact (the production code path offline, XAU/USD byte-identical)
**Code path:** `download_all` with fetches disabled, `build_market`, features, the treatment / control / challenger
engines, and `report.build`, at the commit production runs. That commit is recorded; its freeze key is checked at each
batch.

| # | Measure | Matching rule |
|---|---|---|
| M1 | Live decision at the last closed bar: signal or no signal, direction, WAIT | per TF × arm |
| M2 | Signals lost or gained over the whole history | key = (bar, direction, entry) |
| M3 | Matched signals: \|Δentry\| (expected 0, the entry is the XAU close), \|ΔSL\|, \|ΔTP1\|, \|ΔTP2\|, \|ΔTP3\| in $ | same key |
| M4 | Calibrated probability: bars changed; median, p95 and max \|Δ\| in pp; at the live bar | bar by bar |
| M5 | Attribution: M1–M4 with only the volume swapped, and with only the prices swapped | on common bars |
| M6 | Every live engine signal recorded during the window, re-run with the other version | its decision bar |
| M7a | Session-level counterfactual (`aux_volume_completeness.py`): the decision bar's volume scaled to each session's median and p10 completeness; signals lost or gained, levels, live-p shift | each historical signal bar + an equal number of random control bars (seed 7) |
| M7b | **Per-read counterfactual:** each production read re-run with its decision bar's *final* volume; live decision, live p, SL and TP compared with what the read produced | every read |

**Controls in every batch:**
- **Null check:** the series re-saved unchanged must give 0 differences in every TF × arm and in the payload.
- **Same-version pair:** at least one, which must show only normal revisions.
- **Exact reproduction (M7):** with final volume, every cut run must equal the full run at its bar, field for field,
  and every control bar must stay without a signal. The tool reports this as `exact_with_final_volume` and
  `control_clean_with_final_volume`. A failure stops the batch.

## 5. Statistical analysis
- **Proportions** (E1, E3, signals lost / gained): count / n with **exact Clopper–Pearson 95% intervals**.
- **Medians** (E2, completeness by session): distribution-free 95% interval from the binomial order statistics.
  - Sensitivity check: a **day-block bootstrap** (10,000 resamples, fixed seed). Reads on the same day are correlated,
    so the day is the resampling unit.
- **Magnitudes** ($ and pp): median, p95 and max; the p95 interval comes from the same day-block bootstrap.
- **No p-values and no hypothesis tests.** The readings in §7 use point estimates and interval bounds that are
  declared in advance.
- **Multiplicity:** 3 primary endpoints (E1–E3). Everything else is descriptive and cannot by itself trigger a
  "material" reading.
- **Precision.**
  - If no flip event changes a live decision, the upper 95% bound for E1 is:

    | Flip events (N) | Upper 95% bound |
    |---|---|
    | 20 | 16.8% |
    | 40 | 8.8% |
    | 60 | 6.0% |

  - Changed live decisions under E3 are expected to be rare. In the pilot, 3 of 21 signal bars changed, and a signal
    occurs on about 0.7% of bars. With about 1,800 reads, E3 may therefore rest on a handful of events; its interval
    will be reported as it is.

## 6. Analysis plan and outputs
- **Batches:** weekly, plus a final report.
- **Contents of each batch:**
  - E1–E3 with intervals;
  - M0–M7 tables per TF × arm;
  - the census;
  - the flip frequency per day;
  - all control results.
- **Where results go:** `docs/deploy/` only. They are never written into a forward ledger, a scorecard or the site.

## 7. Pre-declared reading (it decides only what to *propose*, never what to change)
| Finding (prospective data only) | Reading | What would be proposed |
|---|---|---|
| E1 = 0, M3 p95 ≤ $0.50, M4 live-bar p95 ≤ 1 pp | flips immaterial for decisions | bookkeeping only (PR-H: record volume revisions) |
| E1 ≥ 1, or M3 p95 > $0.50, or M4 live-bar p95 > 1 pp | flips material | a data-layer amendment, e.g. keep the first stored version of closed auxiliary bars. **Restarts the holdout.** |
| E3 = 0, M7b live-p p95 ≤ 1 pp, M7b \|ΔSL\| p95 ≤ $0.50 | completeness immaterial | document only |
| E3 ≥ 1, or M7b live-p p95 > 1 pp, or \|ΔSL\| p95 > $0.50 | completeness material | an amendment, choosing one option (below) |

**The options if completeness is material:**
- **(a)** Label it on the site and in alerts (display only).
- **(b)** Evaluate the volume gates on the last *complete* bar. This is an engine change and **restarts the holdout**.
- **(c)** Wait until the bar is final. This makes every signal about 20 minutes old (DELAYED), so it is not recommended.

**Why the thresholds:** they are materiality limits for data integrity.
- $0.50 is 5% of a $10 stop.
- 1 pp is a materiality judgement: a smaller shift is unlikely to change how a probability shown with its interval is
  read.
- They were set after the pilot was seen (§1), which is why only prospective data count.

**Signal frequency.** Options (b) and (c) would make live inputs match the history the engine was validated on. That
can change the live signal frequency, because today's live gates are stricter than in that history. It would not relax
any validation criterion.
- Neither option would be taken without the operator's explicit approval and a new amendment.
- This study proposes no change to signal frequency.

## 8. Protection of the holdout and registered records (confirmations)
- **Read only.**
  - The study only fetches `market-data` with git and reads the Actions API.
  - It never writes to `market-data`, the forward ledger, `gh-pages` or `research/`.
  - It never touches production alert state.
- **Unchanged:**
  - the engine, `config.py`, the data layer and the thresholds;
  - `holdout.ENGINE_SOURCES` and the freeze key `5e4630924d663fc5:a6f2be58c74887ed`, which every batch checks and
    records. A change stops the study.
- **Forward records** (the §7 arms, the Amendment 5 H2, B9, B15, SETUP-LIVE, B24's void record) are never recomputed,
  re-labelled or annotated.
- **B24 stays OFF.** `FWD_B24` is never set.
- **No research amendment and no registration** without separate approval. The study is not entered in
  `research/trials.jsonl`.
- **No vendor data in the repository.**
  - Snapshots exist only as short-lived workflow artifacts: 1 day for per-read snapshots, 90 days for flip pairs (at
    most 40).
  - The study records derived numbers only.
- **No credentials beyond `GITHUB_TOKEN`** (contents: read, actions: read).
  - No Twelve Data, ntfy or MetaApi secret, so it cannot send an alert or use API quota.

## 9. Collection: what needs approval
GitHub runs scheduled and `workflow_run` workflows **only from the default branch**, and GitHub's own cron delivers 1–7
of 96 runs a day (R15). An unattended collector therefore needs a workflow file on the default branch:
- the file touches no production file;
- it is still a repository change on the deploy branch, so **it needs explicit approval**.

| Option | How | Sample | Production impact |
|---|---|---|---|
| **C1 (recommended)** | New `r14-collector.yml` on the default branch, triggered by `workflow_run` when `quantum-site` completes; read-only; about 1–3 min per run | every read; full M7b | none: it runs after the site run has finished and shares no concurrency group |
| C2 | The same file on GitHub cron | 1–7 reads a day; enough for flip existence, too sparse for M7 | none |
| C3 | No new workflow: retrospective only (the 12 pilot snapshots) plus ad hoc sampling from a session | small, irregular | none |

**Tools still to be built** (read-only, on the development branch, with tests):
- the gap-filled count (§4.1);
- the M7b per-read re-run;
- the collector itself.

## 10. Limitations
- **Observational.** Yahoo's behaviour (flip frequency, delay) can change during or after the study.
- **Offline re-runs** lack the FRED (DFII10, DGS2) and CFTC inputs, for both sides alike (common mode).
- **Sessions** are fixed UTC windows. DST shifts their market meaning by an hour.
- **The two pilot versions may not be the only ones.** The clustering rule (§4.1) can add more.
- **E3 events are expected to be rare** (§5), so its interval will be wide.
- **Collector delivery.** C1 depends on GitHub delivering `workflow_run` events. Missed reads are counted and reported,
  not imputed.
- **Not a strategy evaluation.** Nothing here says the engine is profitable, accurate or validated.

## 11. Cost and effort
- **GitHub Actions:** under C1, about 96 short runs a day plus about 5 min per flip event. That is free on a public
  repository.
- **No vendor API calls.**
- **Effort:** about one day to build and test the tools and collector after approval, then weekly batches and a final
  report.

## 12. Approval needed (each separately)
1. This protocol: the hypotheses, endpoints, readings and protections.
2. The collector option: C1 (a new read-only workflow on the default branch), C2, or C3 (no new workflow).
3. The duration: at least 4 weeks and at least 20 flip events, stopping at 8 weeks.
4. Whether to register the study later. It is not registered now.
