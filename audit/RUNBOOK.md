# Runbook — what to collect after pasting, and why

Ordered by value. **Steps 1 and 2 are worth more than everything else combined**, because
they close gaps that no amount of analysis here can: the Master has never been compiled and
the 92 assertions (72 until v13, +20 in v14) have never been run.

Read §9 at the end before running the strategies. It is short and it changes what the data
is allowed to do.

---

## Step 0 — the check that decides whether any backtest is valid at all

**Do this first. If it fails, every later step produces nothing.**

Entries in both strategy arms are hard-gated on:

```pine
bool _costModelValid = math.abs(syminfo.mintick - 0.01) <= 1e-9
```

If your broker's XAUUSD feed has a tick size other than `0.01`, **no trades will fire** and
the backtest will look broken when it is actually refusing to run on a cost model that does
not match. A label saying `A/B INVALID — COST MODEL MISMATCH` is drawn on the last bar.

**What to do:** add either strategy to your XAUUSD chart and look for that label.

- **No label** → tick size is 0.01, cost model valid, continue.
- **Label present** → send me the `mintick=` value it prints. The commission and slippage
  constants have to be re-derived for your feed before any run means anything.

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

92 assertions that have never been run (v14: 72 original + 20 in GROUP K). The last recorded attempt hit a runtime error
(`Row 70 is out of table bounds`), which was fixed — but the corrected build's result was
never recorded.

1. Add `XAUUSD_Quantum_5_0_EdgeCases.pine` to any chart. It is standalone: it imports
   nothing, trades nothing and writes nothing.
2. A table appears top-left. The **top-right cell** is the summary:
   `ALL PASS 92`, or `<n> FAIL / 92`. The header cell must read `§16 EDGE CASE v14`.
3. **Screenshot the whole table.** If anything fails, I need the failing row's
   `GOT` / `WANT` / `CLASS` values.
4. Remove it afterwards — it is diagnostic only.

A green `ALL PASS 92` establishes how Pine evaluates the arithmetic. It does **not**
establish that the Master is wired to those expressions — that is a separate, known limit.

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
inputs. Only the script differs.

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

- **Dashboard**: set Dash Mode → `MobileLand`. Five columns, readable, no clipping.
- **Order blocks**: visibly fewer than before — the threshold was 2.5× too loose.
- **Analog EV**: lower than the previous build, most in chop.
- **Plan basis**: look for a `°` suffix (e.g. `SL:VAL°`). It marks a level that exists only
  at the live edge and no historical bar could have produced.
- **Decision log**: should now name the filter that actually blocked, plus a `ctx:` suffix.
- **v14 plan panel**: the expectancy reads `EVrace x.xxR` (was `E x.xxR`). It is now a real
  expectancy in R, net of cost, so it can exceed 1 on a good-geometry setup.
- **v14 SIGNAL cell**: `mP=62/S31%` once the bear map fits (`/S` = the bear probability),
  and `mP unfit` before either map exists — the old heuristic value is gone.
- **v14 EdgeCases**: header reads `§16 EDGE CASE v14`, **92** rows, all PASS expected.

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
| 1 | Compile result for all five files — clean, or the exact error text |
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
