# Concurrent Processing Audit + Master→Visuals Migration Proposal

**Mode:** READ-ONLY. No source file modified. Proposal only — nothing moves without your approval.
**Build:** v11 · `5d516ef` · **Focus timeframe: 5m** · **Scenario: 4 scripts on one chart**

---

## PART A — CONCURRENT PROCESSING AUDIT

### A0. What is *not* a problem (checked first, so effort goes where it matters)

**Drawing-object budgets do not contend.** `max_lines_count` / `max_labels_count` /
`max_boxes_count` are **per-script** in Pine, not per-chart. Each of the four declares its own
500/500/500. Four scripts = 4 independent budgets, not one shared pool.

| Script | lines | labels | boxes | max_bars_back |
|---|---:|---:|---:|---:|
| Master | 500 | 500 | 500 | 5000 |
| Strategy A | 500 | 500 | 500 | 5000 |
| Strategy B | 500 | 500 | 500 | 5000 |
| Visuals | 500 | 500 | 500 | 5000 |

**No action needed here.** The 500-object cap that bit the structure layer previously was a
*within-Visuals* problem, and it is capped now.

---

### C-01 — 77 simultaneous data requests · **P2**

| Script | `request.*` calls |
|---|---:|
| Master | 22 |
| Strategy A | 22 |
| Strategy B | 22 |
| Visuals | 11 |
| **All four loaded** | **77** |

Pine caps requests at **40 per script** — each file is individually compliant. But the cap is
per-script, so loading all four issues **77 concurrent external data requests** on one chart.

**Worse: they are largely the same requests.** The Master and both strategy arms each pull the
same macro set — DXY, 10Y, TIP, EUR, XAG, SPX, and the HTF ladder. TradingView does **not**
deduplicate identical requests *across* scripts. The same DXY series is fetched **three times**.

**Impact:** slower chart load, more to go wrong on a feed hiccup, and on a weak connection a
higher chance one script's macro layer resolves while another's does not — which makes the
two disagree for reasons that have nothing to do with the code.

---

### C-02 — Triple-redundant statistics engine · **P1 · the dominant cost**

This is the real concurrency finding.

**The Master and both strategy arms each contain a complete, independent copy of the entire
statistics engine.** Not a shared library — three separate full implementations, each running
every bar:

- the analog scan over the rolling history buffer
- the 9-dimension cosine similarity vector per candidate
- MFE/MAE excursion counters
- the calibration bins and Platt/WLS fit
- the expectancy, Kelly and drawdown accumulators

**Sizing on a 5m chart** (`tfSec = 300`):

| Quantity | Value |
|---|---:|
| `HIST_MAX` | **2,000** |
| `OUTCOME_N` | **12 bars** |
| Arrays per engine copy | 46 (Master) / 54 (each arm) |
| Engine copies if all four loaded | **3** |

So on 5m, all four scripts loaded means roughly **three complete engines**, ~154 arrays of up
to 2,000 elements, plus 4 × `max_bars_back = 5000` historical buffers.

**But here is the thing that makes this avoidable rather than expensive:**

> **Both strategy arms are backtest-only by their own file headers.**
> `FILE ROLE: A/B TREATMENT ARM — BACKTEST ONLY. Canonical live file = the Master.`
> `FILE ROLE: A/B CONTROL ARM — DEPRECATED GATES, BACKTEST ONLY. DO NOT DEPLOY.`

They are not meant to run alongside the Master. Running all four simultaneously computes the
same engine three times and **produces no information the Master does not already give you**.

**This is an operational fix, not a code fix.** No feature is lost.

---

### C-03 — Recommended chart configurations

| Purpose | Load | Requests | Engines |
|---|---|---:|---:|
| **Live trading / monitoring** | Master + Visuals | 33 | **1** |
| **A/B run — control** | Strategy B (OLDGATES) **alone** | 22 | 1 |
| **A/B run — treatment** | Strategy A **alone** | 22 | 1 |
| **Harness check** | EdgeCases alone, then remove | 0 | 0 |
| ~~All four together~~ | — | 77 | 3 |

Run the two arms **separately, not together**. Beyond halving the load, TradingView's Strategy
Tester reports on **one** strategy at a time, so running both simultaneously gives you no extra
result anyway — just a slower chart and an ambiguous tester panel.

**All features remain intact in every configuration.** Nothing is removed; the arms are simply
loaded when you are actually running the A/B, which is what they exist for.

---

### C-04 — Cross-script disagreement surface (post-F-A08)

| Definition | Master | Visuals | Status |
|---|---|---|---|
| FVG bounds | `low[0] > high[2]` / `low[2] > high[0]` | identical | **parity** |
| Session windows + DST | `euIsDST` / `usIsDST` trackers | replicated | **parity** |
| OB displacement threshold | `adaptiveATR × 2.5` | now identical (F-A08) | **parity** |
| OB **retention** | one active OB per side + mitigation lifecycle + reversal path | last N boxes | **still differs** |
| Structure (BOS/CHoCH/MSS) | 2 pivot scales, sequence validation, MSS | 1 pivot scale, no MSS | **differs — marked `~` on chart** |

The two remaining differences are **documented in the files themselves** and marked on-chart.
Neither affects a trading decision — Visuals gates nothing.

---

## PART B — MASTER → VISUALS MIGRATION

### B1. The hard constraint that shapes everything

**Pine scripts cannot share variables.** Two indicators on one chart are fully isolated — no
imports of state, no cross-script reads.

Therefore a feature can move to Visuals **only if every input it needs is derivable from raw
OHLCV inside Visuals**. Anything consuming engine values (scores, probabilities, calibration,
analog statistics) **cannot move** — you would have to move the engine with it, which is the
opposite of freeing budget.

### B2. Measured token distribution — where the Master's budget actually goes

Master total: **42,339 lexical tokens.**

| Block | % of Master | Movable? |
|---|---:|---|
| Statistics / analog / calibration engine | **17.4%** | **No** — it *is* the product |
| Bloomberg dashboard render | **14.1%** | **No** — consumes ~200 engine values |
| Macro correlation layer (22 requests) | ~5% | **No** — feeds `bullScore`, feeds the decision |
| Order-block detection | 2.6% | **No** — feeds the trade plan |
| Session engine | 2.5% | **No** — `sessionQuality` is a hard gate |
| **V1/V2 shadow schema** (diagnostic, default OFF) | **0.56%** | **Yes** — feeds nothing |
| **Reliability table** (observability, default OFF) | **0.54%** | Removable |
| **Forecast cone** (default OFF) | **0.38%** | Removable |

### B3. Already migrated in earlier work

S/R scanner · OB/FVG box drawing · structure markers · key levels (PDH/PDL/PWH/PWL/CDH/CDL) ·
session shading · EMA/VWAP/BB rendering · zone labels. **The Master now contains zero
`label.new`, `line.new`, `box.new` and `plot` calls.** The self-contained display layer has
already gone.

### B4. Recommendation — **do not migrate yet, and here is why**

**Everything genuinely movable totals 1.48% of the Master** (628 tokens). Removing all three
diagnostic blocks would buy you roughly one and a half percent, at the cost of losing the
V1/V2 causal-sensitivity check and the reliability readout.

**And the premise is unverified.** The "128,210 against a 100,256 ceiling" figure that drove
the original split **predates the drawing-layer eviction**. Since then the Master lost its
entire drawing layer, and the audit fixes added only **+0.35%**. Nobody knows the current
compiled token count, **because the Master has never compiled successfully.**

> **Compile it first.** TradingView reports the real compiled-token figure on save. If it is
> comfortably under 100,256 — which the measured composition suggests — **there is no problem
> to solve**, and restructuring would be pure added risk.

That risk is not hypothetical. **The previous Master→Visuals split directly caused two of this
audit's P1 findings:** F-A01 (volume-profile engine left behind in the strategy arms while
still being consumed) and F-A08 (order-block threshold 2.5× looser on the chart than in the
engine, while the comment claimed parity). Splitting a system across files that cannot share
state is exactly how definitions drift apart.

### B5a. Ready contingency (v19): Master → Visuals, if the save reports a ceiling problem

> **Measured 2026-09-27 on v23: 100,820 > 100,256 (ratio 2.515, not 2.466).** Acted on in v24
> with a larger, cleaner move than this list: the auction layer went to **Diagnostics**. It
> already ran the identical function on the Treatment engine, so no second definition was
> created and no F-A08-style drift is possible. See `FINDINGS_TRACEABILITY.md` F-A32. The list
> below stays as the next reserve. `liqReachScore` is no longer movable: it now feeds the
> forecast and the MobileBrief card.

v19 estimates (lexical × 2.466): Master ~97,000, Diagnostics ~89,300, twins ~85,300 (v14's
~85,100 compiled and ran), Visuals ~17,800. Only the Master is tight. If its save reports
more than 100,256, these move to Visuals. Each was traced mechanically: it reads **no engine
value** (scores, probabilities, analogs), uses only OHLCV, `ta.*` or `request.*` data
Visuals can fetch itself, and **feeds no gate** (`shouldBuy/Sell`, `tqVeto`, `_calVeto`,
`tradeQuality`, `riskLock`):

| Feature (Master dashboard) | Symbols |
|---|---|
| Auction acceptance + value migration | `acceptScore`, `acceptGrade`, `valueMigStr` |
| Session manipulation / continuation rates | `sessManipProb`, `sessContProb` |
| Session volume anomaly, CVD direction | `vol{Asian,London,Ny}EWMA`, `cvdBull` |
| PDH / liquidity reach | `pdhReachScore`, `liqReachScore` |

Estimated saving ~1,000–1,500 compiled tokens. **Not movable** (they feed the veto):
`distEma20ATR` / `distEma200ATR`. Moving anything re-opens the F-A08 risk of the chart and
the engine computing "the same" feature differently. Each move needs a parity check like
`diag_parity.py`, and none is done unless the compiler asks for it.

### B5. If the compiler *does* report a ceiling problem — ordered plan

> **Measured 2026-09-26 on v14:** `Compiled code contains too many tokens: 100627. The limit
> is 100256.` That is 42,339 → 40,803 lexical tokens at a ratio of **2.466 compiled per
> lexical**. v13 (39,359 lexical) estimates to ~97,100, so **the v14 probability-layer
> additions are what crossed the limit**. Step 1 below was executed in v15: −1,010 lexical,
> an estimated ~98,100 compiled (~2% headroom). That is an estimate until the next save
> reports the real figure.

Only then, and in this order (cheapest and safest first):

1. **Delete the three default-OFF diagnostic blocks** — V1/V2 shadow, reliability table,
   forecast cone. ~628 tokens, no feature that affects a decision. *Reversible, in git.*
2. **Prune the 62 dead dashboard-layer symbols in the strategy arms** — the render block was
   stripped from the twins but its remnants were not. Zero risk: they are already unread.
3. **Only if still over:** consider a Pine **library** (`export`) for pure stateless helpers.
   Libraries cannot carry the engine's per-bar `var` state, so this helps far less than it
   sounds — but it is the correct mechanism, not another copy-paste split.
4. **Never** duplicate a definition across files again without a parity test. That is what
   `audit/tools/trace.py` is for.

---

## PART C — "PRODUCTION-LEVEL CODE"

The forensic audit rates this **D — NOT READY**, overall readiness ≈ 42/100. Production quality
is not reached by restructuring files. In priority order, from `FORENSIC_AUDIT_Q5.md` §65:

1. **Confirm the Master compiles.** It never has. Everything else is theoretical until then.
2. **Run the 72-assertion harness** and record the result.
3. **Freeze the parameters and record the date.** Costs nothing, and it is the only act that
   makes any future validation possible.
4. Collect forward data from that date. Everything before it is a diagnostic, not evidence.

Steps 1–3 can be done today and move the system from **D** to **C — Research Ready**.
Restructuring for token budget does not move it at all.

---

## SUMMARY OF ACTIONS

| # | Action | Type | Cost | Feature loss |
|---|---|---|---|---|
| 1 | Run **Master + Visuals only** for live use | operational | none | **none** |
| 2 | Run the two arms **separately** when A/B testing | operational | none | **none** |
| 3 | Compile the Master; read the real token count | operational | minutes | none |
| 4 | Migration — **hold** pending #3 | — | — | — |
| 5 | If over ceiling: drop 3 default-OFF diagnostics (628 tokens) | code | small | 3 diagnostics |

**Nothing in items 1–3 removes a single feature, and they address the entire measured
concurrency cost.**
