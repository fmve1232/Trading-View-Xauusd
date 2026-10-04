# Runbook — what to collect after pasting, and why

Ordered by value. **Steps 1 and 2 are worth more than everything else combined**, because
they close gaps that no amount of analysis here can: the Master has never been compiled and
the 99 assertions (72 until v13, +20 in v14, +5 in v16, +2 in v29) had not been run until the 2026-09-27 chart run.

Read §9 at the end before running the strategies. It is short and it changes what the data
is allowed to do.

---

## Step 0 — the check that decides whether any backtest is valid at all

**Do this first. If it fails, every later step produces nothing.**

Entries in both strategy arms are hard-gated on (v15):

```pine
bool _costModelValid = syminfo.pointvalue == 1.0 and syminfo.currency == "USD"
```

Up to v14 the gate tested `mintick == 0.01`, and OANDA:XAUUSD (mintick 0.001) was blocked.
v15 charges all costs as cash per contract (`commission_value = 0.385`, `slippage = 0`), so
tick size no longer matters. What the cash figures do depend on is 1 contract = $1 per
point, in USD. If that doesn't hold, **no trades fire** and a label saying
`A/B INVALID — COST MODEL MISMATCH` is drawn on the last bar.

**What to do:** add either strategy to your XAUUSD chart and look for that label.

- **No label** → cost model valid, continue.
- **Label present** → send me the `pointvalue=` and `currency=` values it prints.

Also note your broker/exchange prefix (e.g. `OANDA:XAUUSD`, `FX:XAUUSD`, `CAPITALCOM:GOLD`).
Different feeds have different tick sizes, spreads and session calendars.

---

## Step 1 — Compile the Master  *(closes the biggest open gap)*

The Master has **no measured compiler baseline**. A build was once measured at 128,210
compiled tokens against a 100,256 limit, and the drawing layer was cut to fit. Whether the
current build (v14: Master 5,850 lines) compiles is unknown.

1. Open the Pine editor, paste `XAUUSD_Quantum_5_0_Master.pine` over the **whole** script
   body (select all first — do not splice).
2. Press **Save**. Compilation happens on save.
3. Record the result **exactly**:
   - Compiles clean → say so. That single fact closes §8.1.
   - Any error → **copy the full error text and the line number verbatim.** Do not
     paraphrase. Pine reports one error at a time, so send them as they appear and I will
     work through them.

Repeat for the other four files. Expect trivia on first paste — every check I ran was
static, not a compiler.

**If it fails on token count**, tell me and delete the `_ctxLog` block first (the `ctx:`
context readout near the decision log). It is display-only.

---

## Step 2 — Run the Edge Case harness  *(closes §8.2)*

97 assertions that have never been run (72 original + 20 in GROUP K, v14 + 5 in GROUP L, v16). The last recorded attempt hit a runtime error
(`Row 70 is out of table bounds`), which was fixed — but the corrected build's result was
never recorded.

1. Add `XAUUSD_Quantum_5_0_EdgeCases.pine` to any chart. It is standalone: it imports
   nothing, trades nothing and writes nothing.
2. A table appears top-left. The **top-right cell** is the summary:
   `ALL PASS 99`, or `<n> FAIL / 99`. The header cell must read `§16 EDGE CASE v33`. Since v20
   **failing rows are drawn first**, and a *Table text size* input (default Small) keeps them legible.
3. **Screenshot the whole table.** If anything fails, I need the failing row's
   `GOT` / `WANT` / `CLASS` values.
4. Remove it afterwards — it is diagnostic only.

A green `ALL PASS 99` establishes how Pine evaluates the arithmetic. It does **not**
establish that the Master is wired to those expressions — that is a separate, known limit.

---

## Step 2b — Diagnostics companion (v17)

`XAUUSD_Quantum_5_0_Diagnostics.pine` runs the Treatment engine and shows the six diagnostic
features that no longer fit in the Master: forecast cone, V1/V2 shadow audit, reliability
buckets, rolling 95% intervals, what-if scenario scores and the data-source census.

1. Add it to the XAUUSD chart and let it load fully. It runs the full engine, so it's as
   slow to load as a strategy arm.
2. Screenshot the panel (top right by default; there's a position input). The header must
   read `QUANTUM DIAGNOSTICS v24 Q7.2 B5`. Row **Auction** (v24) carries the auction layer
   that moved out of the Master for the token limit: auction bias, state and cycle, discovery,
   acceptance, value migration, opening type and sweep quality. Row **Volume (free plan)** compares OANDA tick
   volume with real COMEX GC1! volume (delayed on a free plan, so compared on closed bars):
   `corr` near 1 means the volume filters can be trusted; a WEAK reading means treat
   volume-based signals with caution. Bottom-left: the dashboard mirror (the Master's
   dashboard values recomputed from the same engine); bottom-right: the MT5 plan. Input
   *Engine zones overlay* draws the engine's own OB / FVG / liquidity levels to compare with
   Visuals. The **Gate funnel** rows show how many
   historical bars pass each entry stage and how often each veto fires; send them with any
   backtest that takes few or no trades.
   Row **Missed moves** (v27): for every move of at least *move size* (default 30) within
   *N bars* (default 12) on the loaded history, where the entry chain stopped in that
   direction (trend, HTF, sess/news/DD, trigger, TQ, EV, P, risk), or ENTRY if a signal
   fired while the move was still ahead. ENTRY does not mean the trade won. Send this row
   with the gate funnel.
3. It trades and alerts nothing. Keep it if you want the auction read (v24); nothing else
   depends on it.

> **EdgeCases (v28):** the red header cell names the first failing test with its GOT / WANT,
> e.g. `1 FAIL / 99 · I4 got 5 want na`. Send that cell.
>
> **Saving a paste.** After pasting, press **Save** (Ctrl+S). A chart keeps running the last
> *saved* version: the v21 EdgeCases showed "3 FAIL / 97" in natural row order because the
> editor still said *Unsaved version*. A saved v21+ harness draws failing rows first and its
> header reads `v21`.

---

## Step 2b′ — Phone view (v23; one Mobile mode since v25)

On the Master's settings choose **Dash Mode → Mobile** (or tick *☰ Mobile Layout*). v25 merged
the old MobileLand, MobilePort and MobileBrief into this one mode. If a saved chart still
holds an old option name, pick **Mobile** again. The card has four sections, and everything
in it is built from the same engine values and strings as the desktop view:

| Section | Headline | Detail (Standard / Spacious) |
|---|---|---|
| 1 TREND | composite bias · regime · HTF bias · bull/bear score | bias strength and C/S/I breakdown, agreement · 5M–1D arrows, session, volume, CVD, delta, regime, session stats · macro verdict, day-of-week tracker |
| 2 TARGET | liquidity destination at its **MT5** price, reach % | nearest liquidity above/below and target score/reach/open FVG, both at TradingView prices |
| 3 PREV → NEXT | last structure event, last bar's change → calibrated 1R UP vs DOWN, race EV | price + change · forecast L/S/R · EV, calibrated P, confidence · WR/ROLL/PF · (Spacious) engine cross-check line |
| 4 DECISION | the desktop DECISION box (confirmed label, grade, TQ, bias + block reason, LIVE tag); on BUY/SELL the MT5 entry, SL, TP1, TP2 | RR, SL in ATR, risk %, $, lots, cost · decision log, MTF agreement |

Below it, the **full trade plan** (direction, entry, SL/TP1–3 with hit probabilities, RR and
lots, plan reason) is listed inside the same card, so nothing can overlap on a narrow
screen. **Density → Compact** shows the four headlines only, which is the old MobileBrief.
TradingView keeps settings per chart layout, so use a separate layout for the phone.
*Text Size* enlarges the card.

---

## Step 2c — Alerts for manual MT5 execution (v21)

One alert on the **Master** delivers everything. In TradingView choose **Create Alert**, then
**Condition: XAUUSD Quantum 5.0 → "Any alert() function call"**, and set expiry and your
notification channel (app / e-mail / webhook). It fires only on **closed bars**, with:

| Event | Message carries |
|---|---|
| BUY / SELL signal | MT5 entry, SL, TP1, TP2, TP3, RR, directional P, race EV, bias, TQ, session |
| DECISION changes (e.g. BUY → NO TRADE, WAIT → SELL) | old → new state; the MT5 plan when the new state is a trade |
| Tracked plan hits SL or TP1 | which level (MT5 price) and the result in R |
| Risk lock engages | the lock reason; new entries are blocked |

MT5 prices use the **MT5 Price Offset** input (MT5 − TradingView). Set it from your broker's
quote before trading. The separate "Nexus Buy/Sell Signal" and "Bull/Bear BOS" alertconditions
remain available and are confirmed-bar gated too.

---

## Step 2d — Forward test (v33, from 2026-10-05 00:00 UTC, **15M** — amendment A1)

The rules are frozen in `audit/PREREGISTRATION.md`. Only trades opened after the freeze count.

1. **Add the Challenger** (`Strategy_CHALLENGER.pine`) to the same **15M** chart as Treatment and
   Control. Leave all three at their code defaults, 10K capital.
2. **Live trades:** for every MT5 trade taken from a confirmed Master BUY/SELL alert, add a
   row to *Live Log* in `audit/XAUUSD_Forward_Test_Log.xlsx`. Fill the blue columns only.
3. **Weekly:** in each arm's Strategy Tester open *List of Trades* and paste the arm name,
   entry time and net P&L of any new trades into *Arm Trades*.
   The `~X% ±Y` next to SL/TP on the plan is a **90%** interval on the effective sample.
4. **On-chart scorecards (v34).** Each strategy shows a FORWARD TEST card: positions since the
   start, mean $ per position, 95% CI, PF and the pre-registered verdict. With several arms on one
   chart, give each its own corner (input *Scorecard position*), or show one arm at a time. Every
   week, copy each card into the workbook's **TV Snapshots** sheet. TradingView recomputes the
   card from the loaded bars only; once the history no longer reaches the start, its Coverage row
   turns orange, and the snapshots are then the record.
5. **5M and 15M.** The registered decision chart is **15M**: take only 15M confirmed BUY/SELL. Use
   the 5M chart to time the entry inside that signal (e.g. a 5M structure break in the same
   direction). A scorecard on 5M says "NOT 15M: does not count". On a free plan, the 5M history
   covers only ~2–3 weeks, so its statistics are thin by construction.
6. **H2 sweep-to-value (v36).** Add `Strategy_H2.pine` to the same 15M chart (defaults, 10K), and
   paste the new Visuals.
   - Visuals marks H2 signals with "H2" triangles, and its **H2 card** shows: the 1H/4H/1D trend,
     the unswept swing high/low, VAL/POC/VAH, the last sweep, the next movement, and the last
     signal at MT5 prices.
   - Set *MT5 price offset* in Visuals to the same value as in the Master.
   - H2's own record is the scorecard of `Strategy_H2`.
   - Adoption of H1 or H2 needs the 97.5% interval (Stats rows 35–37).
   - **v37:** the Master shows the same H2 signal as **H2 SETUP** (desktop: under the decision
     footer; phone: card row "5 H2 SETUP") with its own MT5 plan and alert. It is a second
     decision, separate from DECISION: an H2 SETUP you execute is **not** a Live Log trade (A4.2).
   - The H2 card in Visuals now also shows the session (range, open, expansion vs average,
     swept-previous-extreme flag), session history (manipulation / continuation %) and session
     volume — moved from the Master's market cell. The analog-evidence numbers (A / WR / Cal /
     IS-ROLL / weights) moved from the Master's cross-check line to Diagnostics' *Analog evidence* row.
7. **Read *Stats*.** Verdicts stay COLLECTING until 50 trades per arm. Do not change any
   setting or rule before the decision date in PREREGISTRATION §5.

---

## Step 3 — Record the run configuration

Before any strategy run, capture this. Without it the export is not reproducible and I
cannot tell you what a number means.

| Item | Where |
|---|---|
| Symbol + exchange prefix | chart header |
| Timeframe | chart header |
| Chart date range | first and last visible bar |
| `mintick` | Step 0 |
| Every input value you changed from default | Settings → Inputs |
| Broker cost assumptions | `spreadCost`, `slippagePts`, `commissionL`, `pointValue` |
| `holdoutRatio` | default 0.20 |
| `useCalGate`, `calGateMinP` | default `true`, `0.50` |
| `useDDBreaker` | default `false` |

Easiest: screenshot the whole Inputs tab. Two screenshots beat a transcription error.

---

## Step 4 — Export the List of Trades

Run **each strategy arm separately**, same chart, same timeframe, same date range, same
inputs. Only the script differs. Leave **Backtest all bars** ON (default since v20); OFF
confines entries to the last *Signal Lookback Bars* (120), which is why v19 took 0 trades.

1. Add `XAUUSD Quantum 5.0 — Control` (OLDGATES) to the chart.
2. Open the **Strategy Tester** panel (bottom).
3. **Performance Summary** tab → screenshot it. That is your PF, win rate, max DD, trade
   count.
4. **List of Trades** tab → use the export/download icon on that panel → save as CSV.
5. Remove that script, add `XAUUSD Quantum 5.0 — Treatment`, repeat.
6. Send both CSVs, clearly labelled **control** and **treatment**.

If you have Deep Backtesting available, use it and say so — the bar count matters for every
sample-size gate in the engine.

### What is inside the export

Each entry's **Signal / comment** column carries engine state, in this format:

```
TQ<n>|CG<n>|B<n>V<n>|D<n>|P<pct>
```

| Field | Meaning |
|---|---|
| `TQ` | trade quality 0–100 (the heuristic the veto uses) |
| `CG` | calibration grade at entry |
| `B`, `V` | schema build / regime feature version |
| `D` | bar data status |
| `P` | **calibrated probability that *this trade* wins**, in percent |

`P` is new — it was promised by a code comment but never actually emitted, so the field a
calibration test most needs was the one field missing. It is the *directional* probability
the gate used for that trade.

**From v14 (`B3`) `P` means something different, so never pool `B2` and `B3` trades.**
Once both the bull and the bear calibration maps have fitted, `P` is
`P(win | resolved) = P(win) / (P(win) + P(loss))` from the trade direction's own fit — the
probability that the target comes before the stop. Before the bear map fits, it is the
v12 value (`P(bull)` for longs, `1 − P(bull)` for shorts). Build 2 and build 3 rows
answer different questions; a reliability curve over both is meaningless.

**This is why Step 4 must come after pasting the current build.** Alerts cannot backfill
history, so the entry comment is the only way to attach per-trade engine state to
historical trades. Running on the old build means re-running everything later.

---

## Step 5 — The one comparison actually worth running

Not a parameter sweep. **Four runs, one variable at a time:**

| Run | Script | `useCalGate` |
|---|---|---|
| A | Control (OLDGATES) | `false` |
| B | Treatment | `false` |
| C | Control (OLDGATES) | `true` |
| D | Treatment | `true` |

- **A vs B** isolates the gate change (the original A/B question).
- **A vs C** and **B vs D** isolate the calibrated-probability veto that was wired in.

Change nothing else between runs. Four CSVs plus four Performance Summary screenshots.

---

## Step 6 — The forming-candle test *(cannot be exported)*

Whether the dashboard shows a decision that reverses before the bar closes has never been
tested. This needs live observation, not a file.

On a live 5M or 15M chart during an active session, watch the DECISION cell through several
forming candles and note whether it flips before close, and whether a `LIVE:` tag appears.
A short screen recording or a few timestamped screenshots is enough.

Alerts and both strategy arms are confirmed-bar gated; the dashboard is not. This checks
whether that distinction behaves as documented.

---

## Step 7 — Sanity checks against the changes just made

Quick visual confirmations that the fixes behave:

- **Dashboard**: set Dash Mode → `Mobile`. One card, four sections, readable, no clipping.
- **Order blocks**: visibly fewer than before — the threshold was 2.5× too loose.
- **Analog EV**: lower than the previous build, most in chop.
- **Plan basis**: look for a `°` suffix (e.g. `SL:VAL°`). It marks a level that exists only
  at the live edge and no historical bar could have produced.
- **Decision log**: should now name the filter that actually blocked, plus a `ctx:` suffix.
- **v14 plan panel**: the expectancy reads `EVrace x.xxR` (was `E x.xxR`). It is now a real
  expectancy in R, net of cost, so it can exceed 1 on a good-geometry setup.
- **v14 SIGNAL cell**: `mP=62/S31%` once the bear map fits (`/S` = the bear probability),
  and `mP unfit` before either map exists — the old heuristic value is gone.
- **v14 EdgeCases**: header reads `§16 EDGE CASE v33`, **99** rows, all PASS expected.

Any of these not matching means a fix did not take — tell me which.

---

## §9 — What this data can and cannot be used for

I have to be straight about this, because it decides whether the exercise is worth anything.

**What it legitimately establishes:**

- Whether the code compiles and the assertions pass (Steps 1–2). Pure fact.
- Whether the wiring fixes behave as intended (Step 7).
- Whether the gate change and the calibration veto help or hurt, **as a controlled
  comparison** (Step 5).
- Whether the probabilities are calibrated — a reliability curve of `P` against realised
  outcomes, from Step 4. This is the first time that has been measurable.

**What it cannot establish, and what I will not do with it:**

I will **not** tune thresholds, weights or gates to improve the PF or win rate on this data.
That is not caution, it is the whole problem: the IS/OOS boundary in this engine *slides*
(today's "out-of-sample" row becomes tomorrow's training row), and the price history has
already had Quantum 5.x parameters selected against it. Any parameter I move to improve a
number measured on that window makes the number better and the system worse, and destroys
what little independence is left.

So if the results look poor, the honest answer is a diagnosis, not a fix.

**The one path to genuine calibration** — and it is the only one:

1. **Freeze the parameters now.** Whatever they are. Record every input value and the date.
2. Run the backtest to establish the frozen baseline (Steps 4–5).
3. **Collect forward data from that date onward** — paper or live, either works.
4. Evaluate against *that* data. It is the first sample the parameters were not chosen on.

That is a genuine out-of-sample test. Everything before it, including everything in this
runbook, is a diagnostic. Useful, worth doing — but not validation.

---

## What to send me

| Priority | Item |
|---|---|
| 1 | Compile result for all six files — clean, or the exact error text |
| 2 | Screenshot of the Edge Case harness table |
| 3 | Symbol, timeframe, date range, `mintick`, Inputs screenshots |
| 4 | Four Performance Summary screenshots (runs A–D) |
| 5 | Four List of Trades CSVs, labelled |
| 6 | Step 7 sanity observations |
| 7 | Forming-candle recording, if you can get one |

Send 1 and 2 on their own if you like — they are independently valuable and I can act on
them immediately.

**On the missing Python:** `cost_invariant.py` and `validate.py` are referenced by the code
but absent. I will not reconstruct them from the comments describing them — that would test
my reconstruction, not the original. If you have them, send them. If not, I will write
fresh analysis for your CSVs, clearly labelled as new work rather than as those harnesses.
