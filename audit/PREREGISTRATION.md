# Forward-test pre-registration — XAUUSD Quantum (build v32)

Written **2026-09-27**, before any holdout data exists. Everything below is fixed until the
decision in §5. Changing a rule after seeing forward results turns the test back into a
backtest (`AUDIT_PROMPT.md` §9).

## 1. Why

The history cannot answer "does this make money?".

- The rules were developed while looking at it, and the rolling IS/OOS boundary slides
  (F-037).
- On it, the Treatment arm breaks even: 86–90 trades, PF 0.96–0.99 (F-A34).
- Its score does not separate winners from losers: every bucket shows an 18–24% observed
  rate (F-A34).

Only trades that happen **after** the rules are frozen can show an edge.

## 2. Freeze

| Item | Value |
|---|---|
| Holdout start | **2026-09-28 00:00 UTC** (first market open after this document) |
| Chart | OANDA:XAUUSD, **1H**, the same layout for every arm |
| Frozen scripts (SHA-256) | see table below; any change restarts the clock |

| File | SHA-256 |
|---|---|
| `XAUUSD_Quantum_5_0_Master.pine` | `0506208a373b4b60745443f966c63081d156de3d0f5d19d28601167a4f424f7a` |
| `XAUUSD_Quantum_5_0_Strategy.pine` (Treatment) | `f43b6882b250c1a1401a14b73ee898122b107e37e782dea2aad13cc62834abf1` |
| `XAUUSD_Quantum_5_0_Strategy_OLDGATES.pine` (Control) | `2f0d987e2b715e636657c2b5e7cc0ef28b70f697bac2a635df04bdc499e14030` |
| `XAUUSD_Quantum_5_0_Strategy_CHALLENGER.pine` (H1) | `b5762a04fc0b647f01ec85de40e9839bef2f34b1df358c7271a339bd2745449a` |

Settings stay at the script defaults, except `MT5 Price Offset`, which is display only.
Strategy Properties stay at the code defaults: initial capital 10,000, 1 oz fixed, costs as
pinned in the code.

**Allowed during the holdout:**
- a fix for a compile or runtime error that does not change any signal, logged in
  `CHANGELOG.md` with its reason;
- display-only changes to the Master, Diagnostics or Visuals.

**Not allowed:** any threshold, weight, gate, input default or engine change in the four
files above.

## Amendment before the start (2026-09-27, build v32)

Made **before the holdout start**, so no holdout data exists and no result was seen.

- **What changed:** the Cornish-Fisher guard (F-A38) in the Master and all three arms,
  identically. It only affects bars where the inverse does not exist; there the raw z is kept
  instead of a runaway value (up to 1e213) that pinned `mrComposite` at ±100.
- **What did not change:** the holdout start, the chart, the metrics, the decision rules,
  H1, and every threshold, weight, gate and input default.
- **Hashes:** the table in §2 now lists the v32 files. The v31 hashes are superseded, and the
  v31 files must not be used for the forward test.
- **Why now:** the defect was found on the first live data. Fixing it after the start would
  have restarted the clock; fixing it now costs nothing.

## Amendment 2 before the start (2026-09-27 18:20 UTC): the website is the primary test

Made **before the holdout start**, so no holdout data exists and no result was seen. On the
operator's instruction ("website primary, TradingView withdrawn"), production runs on the
independent Python website, not on TradingView.

- **Primary forward test:** §7, the website engine (1H decides; Treatment, Control and
  Challenger; R per trade).
- **TradingView arms (§2 to §5): withdrawn, not run.** No TradingView trades are counted, and
  the *Arm Trades* sheet of the workbook is not used.
- **Pine v32 stays at the §2 hashes as the reference implementation of the model.** It is
  used, if at all, to validate the website (same-bar parity), never to trade or to decide.
- **Live arm:** the trades the operator actually executes, now on the website's 1H decisions.
  They are still logged by hand in the workbook's *Live Log*, in R, independent of the
  website's own log, with the same §4 rules and minimum-lot sizing until it shows EDGE SHOWN.
- **What did not change:** the start (2026-09-28 00:00 UTC), the decision rules and
  thresholds, the decision date, H1, and the website's freeze key in §7.

## Amendment 3 before the start (2026-09-27 20:10 UTC): the primary decision and shared defects

Made **before the holdout start**: no holdout data exists and no result was seen. It clarifies how the
results are read. No rule, threshold, arm, timeframe or data source changes, and the website's freeze key
(§7) is unchanged.

- **Primary decision: the Treatment arm on 1H.** Whether the live system has an edge is answered by the
  Treatment arm's §4 verdict alone.
- **Challenger: one directional hypothesis (H1).** It is decided only by the ADOPT H1 rule in §4 (EDGE SHOWN
  *and* a higher mean than Treatment over the same window). It is not a second, independent chance to
  declare that the system has an edge.
- **Control: a comparison arm.** Its verdict is reported and decides nothing.
- **Multiplicity.** Three 95% intervals are computed and no family-wise correction is applied, because only
  the Treatment verdict and the H1 rule are decisions. Reading "any arm shows EDGE SHOWN" as evidence for the
  system is not allowed: with three arms and no real edge, at least one interval lies above 0 by chance up to
  about 7% of the time (one-sided, 3 × 2.5%, before the profit-factor filter), against 2.5% for the primary
  arm alone.
- **Shared defects.** The arms differ only in the entry gate. Everything upstream (scores, calibration,
  trade quality, plan) is computed once and shared, so the known defects affect all three arms identically:
  `mrComposite` at ±100 on about 60% of bars, the open outcome-horizon issue (F-035), and the score's lack of
  resolution on the history (F-A34). No arm's result is free of them, and a difference between arms is not
  evidence about them.
- **Timeframes.** Only 1H decides (§7). Price-check outliers on 5m/15m (the weekly `xcheck-prices` report)
  cannot affect a decision; they are tracked so that affected trades can be identified.

## Amendment 4 (2026-09-28, after the start): data-integrity fixes and a restart of the website test

Made **after** the start, so it follows the restart rule instead of editing history: the fixes change the
engine's inputs, which changes the freeze key, and the website test **restarts from the first run of the new
code**. The earlier freeze (2026-09-28 00:00 UTC, code hash `32babc71ed938b30`) is kept in the manifest's
history and its log entries are archived, not deleted.

- **When it was decided:** the restart was recommended and approved at about 10:00 UTC on 28 Sep, when the
  earlier freeze had **no 1H trades** (only one 5m trade each in Treatment and Challenger). A tooling outage
  delayed the merge to 29 Sep.
- **What the earlier freeze holds at the merge** (merged 3 Oct, market closed; `forward-ledger` as of
  2 Oct 11:21 UTC; no open positions; price source `twelvedata:XAU/USD`). All trades below were entered
  after the decision:

  | TF | Treatment | Control | Challenger |
  |---|---|---|---|
  | **1H (decides)** | 1 trade, **-1.021R** | 0 | 1 trade, **-1.021R** |
  | 15m | 3 trades, 0 wins, -3.140R | 2 trades, 0 wins, -2.093R | 3 trades, 0 wins, -3.140R |
  | 5m | 8 trades, 4 wins, -0.762R | 2 trades, 0 wins, -2.158R | 7 trades, 3 wins, -1.128R |
  | 4H | 0 | 0 | 0 |

  The 1H trade is the same SHORT in Treatment and Challenger, entered 28 Sep 16:00 UTC and stopped out
  29 Sep 14:00 UTC. The merge waited on the operator from 29 Sep to 3 Oct, which is when the 5m and
  15m trades accrued.
- **Rule, so a restart can never hide a result:** the final report lists every archived trade of every
  earlier freeze next to the result of the counted test. Every trade in the table above is part of that record.

Found by comparing the website with TradingView (OANDA) on the same minute (02:02 UTC, 28 Sep) and checking the
stored bars:

- **Gold's trading hours.** Twelve Data prints the last quote with a few cents of jitter while spot gold is
  shut. The site treated Sunday 17:00-18:00 New York and the daily 17:00-18:00 break as trading (about one fake
  hourly bar a day). Gold is now shut Friday 17:00 -> Sunday 18:00 and daily 17:00-18:00 New York.
- **The first print of each session is stale.** It is the quote carried through the closure. On 27 Sep it set
  Monday's high at 4287.25 against OANDA's 4275.33. The session's first bar is repaired from 5-minute data; the
  repaired high is 4275.33, the same as TradingView.
- **Yahoo quote snapshots stored as bars.** Rows at off-minute times (e.g. 22:04:41; about 20-34 per series in
  September) in the futures, silver, EUR/USD and dollar-index series, one carrying Friday's close into Sunday.
  They are now dropped.

Unchanged: every rule, threshold, arm, timeframe, the decision date, H1 and the configuration hash. Only the
data the engine reads is corrected. Pine is unaffected (OANDA has none of these artefacts); the website's
differences D-09 and D-10 in `docs/PLATFORM.md` record them.

## 3. What is measured

| Arm | Source | Unit |
|---|---|---|
| **Live** (Master decisions you execute on MT5) | `XAUUSD_Forward_Test_Log.xlsx` → *Live Log* | R (result ÷ entry-to-SL distance) |
| **Treatment / Control / Challenger** | Strategy Tester → List of Trades, pasted into *Arm Trades* | $ per trade at 1 oz, net of the pinned costs |

Only trades **opened at or after the holdout start** count. The workbook enforces this by
the date.

**H1 (Challenger).**
- Treatment's entry trend gate needs `bullTrendScore >= 60`, and half the score's points
  are slow terms (EMA200, EMA100).
- F-A36 measured 60% of $30+ move episodes stopping at that gate.
- H1 replaces only the gate's trend term with the fast terms the score already contains:
  `close > EMA20 and EMA20 > EMA20[3]`, mirrored for shorts.
- No new parameter or threshold is introduced, and nothing else differs.

## 4. Decision rules (fixed now)

For each arm, over counted trades:

- **COLLECTING** while N < **50**.
- **EDGE SHOWN** when N ≥ 50, the 95% t-interval of the mean per-trade result lies entirely
  above 0, and the profit factor is ≥ **1.2**.
- **NOT SHOWN** otherwise.

Challenger vs Treatment, once both have N ≥ 50:
- **ADOPT H1** (move the fast trend gate into the Master, then pre-register again) only if
  the Challenger is EDGE SHOWN **and** its mean $ per trade exceeds the Treatment's over the
  same window.
- Otherwise **KEEP TREATMENT**.

Live trading size:
- until the Live arm shows EDGE SHOWN, trade the **minimum lot**;
- keep the Master's daily loss and losing-streak limits ON.

## 5. When to decide

At 50 counted trades per arm, or on **2027-03-31**, whichever comes first. If an arm has fewer
than 50 trades on that date, it is reported as "insufficient data", not as a pass or a fail.

## 6. What this cannot show

- A pass means an edge on this instrument and timeframe over the holdout window only.
- 50 trades detect only a fairly large edge. A small real edge can still read NOT SHOWN, and
  that is the conservative error, chosen deliberately.
- Only one hypothesis (H1) is tested, so no multiple-testing correction is needed. Adding
  another arm later needs its own pre-registration.

## 7. Website arm — the independent Python engine (added 2026-09-27, before the start)

Added **before the holdout start**, like the amendment above: no holdout data exists and no
result was seen. Since Amendment 2 this is the **primary** forward test. This section registers an
independent forward test run by the website engine (`quantum/`), which does not depend on
TradingView.

| Item | Value |
|---|---|
| Start | **2026-09-28 00:00 UTC**, the same as §2 (`quantum/holdout.py: HOLDOUT_START`) |
| Engine | `quantum/`, `ENGINE_VERSION` Q7.2-web.4, the port of the v32 Master and its three arms (web.3 until the Amendment 4 restart) |
| Freeze key | config hash `5e4630924d663fc5` + engine code hash `3252a9f0d312db75` (was `32babc71ed938b30` until Amendment 4) |
| Price data | Twelve Data spot XAU/USD (`twelvedata:XAU/USD`); each logged trade records its price source |
| Deciding timeframe | **1H**. 5m, 15m and 4h are logged and shown, but they are descriptive only and decide nothing |
| Arms | Treatment, Control and Challenger (H1), with the same definitions as §3 |
| Unit | R per trade, net of the modelled costs (session spread + 2 × slippage + commission) |
| Log | append-only per timeframe and arm; on the `market-data` branch, and with full git history on `forward-ledger` |

**Counted trades.**
- Only closed trades **entered at or after the start**, recorded under the freeze key above,
  with price source `twelvedata:XAU/USD`, are counted.
- A trade logged while the pipeline had fallen back to another price source is reported
  separately. It is never counted.

**Decision rules.** These are §4 and §5 applied to the 1H log in R:
- COLLECTING while N < 50.
- EDGE SHOWN when N ≥ 50, the 95% t-interval of mean R lies entirely above 0, and PF ≥ 1.2.
- ADOPT H1 only if the Challenger is EDGE SHOWN and its mean R exceeds the Treatment's over
  the same window.
- Decide at 50 trades per arm or on 2027-03-31, whichever comes first. With fewer than 50
  trades on that date, the arm is "insufficient data".

**What restarts it.** It restarts automatically, and nobody can skip that.
- A change to the configuration, or to any source file in
  `holdout.ENGINE_SOURCES`, changes the freeze key.
- The next run then starts a new holdout from that moment.
- The old one is kept in the manifest's `history`, and its log entries move to
  `holdout/archive/`.

Display-only files (`report.py`, `notify.py`, `site/`) and documents are outside the key.

**Independence from the Excel log.**
- The pipeline alone writes the website log. The operator alone writes
  `XAUUSD_Forward_Test_Log.xlsx`.
- Neither reads the other.
- At the decision, both are reported side by side. Differences are expected: OANDA versus
  Twelve Data prices, and the differences D-01 … D-08 in `docs/PLATFORM.md`. They are listed,
  never merged.

**Known before the start. None of these may be tuned during the holdout.**
- **Parity not demonstrated.** Same-bar parity between the website and the TradingView
  Master has not been shown. It is scheduled for the first week.
  - If it reveals a website bug, fixing it restarts this arm (by the rule above).
  - It does not restart the TradingView arms.
- **Mean-reversion saturation.** `mrComposite` sits at ±100 on about 60% of bars. It is computed once and
  shared, so it affects all three arms identically (Amendment 3).
- **Open horizon mismatch.** F-035 is open.
- **No-resolution score.** Calibration has no resolution on the history (F-A34).

## Amendment 5 (2026-10-04, approved by the operator before any H2 result was computed): arm H2 "Sweep and Value"

A **new, separate arm**. It does not change the Treatment, Control or Challenger arms, the engine,
or their freeze key (`5e4630924d663fc5:3252a9f0d312db75`). The rules were proposed in chat, approved
by the operator verbatim, and written here **before** H2 was run on any price history, in-sample
or forward. Any change to a rule after this point restarts H2.

**Inputs** (all already produced by the frozen engine and features on the treatment arm's bars):
- EMA20, EMA100 and EMA200 on the chart timeframe, and ATR(14);
- the session quality (`sq`);
- the rolling 100-bar volume profile (POC, VAH, VAL; volume = COMEX GC futures, D-06);
- the PDL/PWL/PML and PDH/PWH/PMH pool sweeps (the engine's `SWEEP` events);
- the active pivot swing low and high (`active_sup` / `active_res`).

**LONG at the close of bar i**, when all of these hold (SHORT is the exact mirror):
1. **Trend:** close[i] > EMA200[i] and EMA20[i] > EMA100[i].
2. **Sweep:** for some bar j with i−3 ≤ j ≤ i, bar j swept sell-side liquidity: either the engine's
   bullish `SWEEP` event (low ≤ PDL/PWL/PML and close above it), or low[j] < active_sup[j−1]
   and close[j] > active_sup[j−1].
3. **Value:** low[j] ≤ VAL[j].
4. **Confirmation:** close[i] > high[i−1].
5. **Session:** sq[i] ≥ 30.

**Completing the specification** (written before any test; not tuned):
- One signal per sweep bar j: the first confirming bar uses it.
- If LONG and SHORT both qualify on the same bar, there is no signal.
- If the trend, session or value condition is missing a value (warm-up), there is no signal.

**Plan:**
- **Entry:** close[i].
- **Stop:** min(low[j..i]) − 0.1 × ATR[i]. R = entry − stop; no signal if R ≤ 0.
- **TP1:** POC[i] if POC[i] − entry ≥ R, else entry + R.
- **TP2:** the nearer of VAH[i] and active_res[i] that lies above TP1; if neither does, TP1 + R.

**Execution and costs:** identical to the other arms (`backtest.simulate`): entry at the close, stop
first on a same-bar tie, 50% off at TP1, then breakeven, and the same cost model.

**Freeze:**
- H2's key = the engine freeze key + SHA-256 of `quantum/arm_h2.py`. If either changes, H2 restarts.
  Its ledger is `holdout/<tf>_h2.json`, and earlier keys are archived, never deleted.
- **H2's forward test starts at the first pipeline run after this amendment is merged.** Trades
  entered before that are reported as **in-sample** only.

**Decision (same standard as §7):**
- The **1H** H2 forward record decides.
- After **N ≥ 50** closed trades, H2 shows an edge only if the 95% t-interval of mean R is above 0
  **and** PF ≥ 1.2. Decide by 2027-03-31; with fewer than 50 trades, the answer is **NOT SHOWN**.
- Other timeframes are reported, not decisive.
- **Multiplicity:** H2 is a fourth hypothesis on the same market and period. If both the Treatment
  and H2 pass, each is still reported on its own terms; neither borrows the other's evidence.

## Amendment 6 (2026-10-06, operator decision "option 1"): one system of record — the website

**Why.** A second Claude session developed the Pine line separately from build v31 onwards, on branch
`claude/xauusd-developed-files-tmnk9g` (builds v32–v41, head `98d9ab5`). That line has its own
pre-registration:
- amendments A1–A6, with a **15M** decision and holdout restarts on 2, 5 and 6 Oct;
- its own **H2 "sweep-to-value"** rule, frozen on 4 Oct within minutes of this file's Amendment 5 H2,
  from the same operator request.

Two pre-registrations of the same idea with different rules, run in parallel, would let the better-looking
one be chosen after the fact. They would also multiply the number of tests (about nine arms in total), and
one of them would likely clear a 95% bar by chance. The operator chose a single system of record.

**Decision.**
1. **The only counted forward tests are the website's**, as defined in this file:
   - §7: Treatment, Control and Challenger on 1H, freeze key `5e4630924d663fc5:3252a9f0d312db75`,
     started 2026-10-03 10:37 UTC;
   - Amendment 5: H2 "Sweep and Value", key `…:adeaccb163806651`, started 2026-10-04 07:55 UTC.
   Their decision rules and dates are unchanged.
2. **The TradingView line (builds v33–v41) is DISPLAY ONLY.** Its scorecards, verdicts and amendments
   A1–A6 are **not counted** and must not be cited as evidence for or against any arm. Its files may be
   used as chart visuals. File hashes at this decision, for the record:

   | File (branch head `98d9ab5`) | SHA-256 (first 16) |
   |---|---|
   | Master | `d8cf5eaaf6cb24d4` |
   | Strategy (Treatment) | `2f43566ff43fcec2` |
   | Strategy_OLDGATES (Control) | `a927a6e3ba3921db` |
   | Strategy_CHALLENGER | `2f14870f4ca9861c` |
   | Strategy_H2 (sweep-to-value) | `e9114048b13e4f85` |
   | Diagnostics | `98c2833b2296e895` |
   | Visuals | `262844d089805c75` |

3. **The Pine reference stays at v32** (the hashes in §2) for validating the website, as in Amendment 2.
   The Pine line's findings F-A39 (Cornish-Fisher outside its domain), F-A40 (MTF denominator) and F-A41
   (HTF two bars old in history) were checked against the website engine on this date:
   - F-A41 does not apply: it aligns to the last completed HTF bar;
   - F-A40 does not apply: it has real 5m/15m data, so every layer votes;
   - F-A39 is already guarded: an unsolved inverse keeps the observed z.

   Nothing is ported, and the freeze keys are unchanged.
4. **Open item, recorded rather than acted on.** In every Pine strategy file (v32 and v41) the exit orders
   are placed only once a position exists. With `process_orders_on_close`, that probably leaves the first
   bar after entry without its stop and targets. The website's backtest protects that bar, so the website
   arms are unaffected. It is listed for the Pine reference only.

## Amendment 7 (2026-10-11, operator decision; written before any code below was changed or run)

**Why.** The operator supplied the TradingView line at its current builds (Master v50, Strategy arms v41–v48;
file hashes in `reference/pine-v50/SHA256SUMS`) and asked that the website use the same standard. The operator
chose (11 Oct, in chat): port the engine defects that also exist on the website and restart the forward test;
keep H2; add the Pine line's H2 rule as a separate arm. The Pine files are stored as a **display-only
reference** in `reference/pine-v50/`; Amendment 6 still holds: only the website's records count, and the Pine
line's own scorecards and amendments are not evidence. `artefacts/` (v32) stays the frozen Pine reference of §2.

**Correction to Amendment 6, item 3.** It said F-A40 "does not apply" to the website. That was wrong. The
website's MTF layers at or below the chart timeframe are neutral, exactly as in Pine (`features.py`: a layer
votes only when the chart is faster than it), so on 1H only the 4H layer can vote and the fixed denominators
cap the scores by timeframe. F-A41 (HTF data age) and F-A39 (Cornish-Fisher domain) remain as stated there.

**1. Engine changes (the §7 forward test restarts).** Each is a defect fix taken from the Pine line, not a
change of any threshold, weight or gate value; nothing was measured on price history to choose them.

| Pine finding | Defect | Website change |
|---|---|---|
| F-A40 (v34) | MTF confluence score divides by a fixed 10 votes and MTF confidence by a fixed 5 layers, although layers at or below the chart timeframe can never vote: the cap is 70 and 40 on 1H | divide by the votes available on the chart's timeframe (MTF layers above the chart + 6 macro votes; HTF layers above the chart, minimum 1). Identical wherever every layer votes |
| F-A48 (v43) | on bars without a signal the plan takes its side from the bias composite, while the bias label and WAIT reason use the final scores, so a LONG plan can sit under BEAR-ISH | the plan is built after the final scores and, without a signal, takes the side of the final bull vs bear score. It therefore also reads this bar's refreshed analog statistics (as Pine v43) |
| F-A38 (v33, Pine line's numbering) | calibration fit: a slope ≤ 0 is rejected and the previous fit kept; a slope floor of 0.02 invents resolution the bins do not show; the intercept is clamped to ±1 for the raw slope | slope projected onto [0, 0.25] (bear fit [−0.25, 0]); a degenerate variance gives slope 0, i.e. the weighted base rate; the intercept is re-solved for the slope used and guarded at ±5 |
| F-A45 (v40, display) | feature direction accuracy divides by all analogs, timeouts included, so every feature reads about 25 points under a coin flip | accuracy among resolved analogs only, shown when at least 10 are resolved |

Already equal on the website, so not ported: F-A41, F-A46 (D-06), F-A44, F-A47 (the backtest protects the
first bar after entry), F-A39 (guarded since web.1, D-08).

**Effect on the records.** The engine code hash changes, so the §7 key changes, and so does H2's key, which
contains it (Amendment 5). Both restart at the first pipeline run of the new code. At this decision (ledger
`forward-ledger` @ `034d7960`, 2026-10-11 16:21 UTC; no open positions) the records that move to the archive are:

| Arm | 1H (decides) | 4H | 15m | 5m |
|---|---|---|---|---|
| Treatment | 1 trade, **−1.035R** (SHORT 7 Oct 14:00 → SL 8 Oct 01:00 UTC) | 1, −1.014R | 0 | 2, 1 win, −0.537R |
| Control | 0 | 0 | 0 | 2, 0 wins, −2.221R |
| Challenger | 1 trade, **−1.035R** (the same SHORT) | 1, −1.014R | 0 | 2, 1 win, −0.537R |
| H2 | 0 | 0 | 1, −1.067R | 3, 1 win, −0.840R |

The Amendment 4 rule applies: the final report lists every archived trade of every earlier freeze next to
the counted result. Decision rules and the decision date (2027-03-31) are unchanged.

**2. Display-only changes (outside the freeze key):** the regime size haircut in the dashboard's risk sizing
(Pine v32 already applied it to the risk %; F-A52 to the $ and lots too); first-appearance alerts for BOS,
CHoCH, MSS and liquidity sweeps (v49). F-A53 (macro label) needs no change: the website already writes
BULL-ISH / BEAR-ISH with the score beside it.

**3. Arm H3 "Sweep-to-Value" — the Pine line's H2 rule, as a new arm.** Rules transcribed from
`reference/pine-v50/XAUUSD_Quantum_5_0_Strategy_H2.pine` (block `H2-BEGIN … H2-END` and `H2-TREND`), fixed
here before H3 is run on any price history. Any change restarts H3.

- **Trend:** for each of 1H, 4H and 1D, score = 40 × [close₁ > EMA200] + 40 × [EMA20 > EMA100] + 20 ×
  [close₁ > EMA20], where close₁ is the last completed bar of that timeframe and the EMAs are of close₁
  (the engine's HTF alignment, D-01); a missing close₁ scores 50. Up = at least 2 of the 3 scores ≥ 60; down
  = at least 2 of the 3 ≤ 40. All three layers are used on every chart timeframe.
- **Swings:** 5-bar pivots (`pivothigh/pivotlow(5, 5)`, the engine's pivot function). The last pivot low
  (high) is liquidity until a bar trades through it, which consumes it; a newly confirmed pivot replaces it.
- **Sweep (bar i):** low[i] < swing low and close[i] > swing low (short: high[i] > swing high and close[i] <
  swing high), using the swing as it stood before bar i.
- **Value:** the engine's per-bar volume profile (100 bars, 40 bins, typical price, POC and 70% value area;
  the same construction as the Pine block; volume per D-07). Long only if close[i] ≤ POC[i]; short only if
  close[i] ≥ POC[i].
- **Risk:** R = close − (low − 0.15 × ATR14) for a long (short: high + 0.15 × ATR14 − close); signal only if
  0.5 × ATR ≤ R ≤ 5 × ATR.
- **Plan:** entry close[i]; stop = entry ∓ R; TP1 = the farther of POC and 1R; TP2 = the farther of VAH
  (short: VAL) and 2R.
- **Execution and costs:** `backtest.simulate`, as every other arm (one position; an opposite signal flips).
- **Freeze:** key = §7 engine key + SHA-256 of `quantum/arm_h3.py`; ledger `holdout/<tf>_h3.json`; starts at
  the first pipeline run after this amendment is merged; earlier trades are in-sample only.
- **Decision:** the same standard as H2: the 1H record decides; N ≥ 50, the 95% t-interval of mean R above 0
  and PF ≥ 1.2; by 2027-03-31, otherwise NOT SHOWN. **Multiplicity:** H3 is a fifth hypothesis on the same
  market and period; each arm is reported on its own terms and none borrows another's evidence.

**Amendment 7 — start record** (filled in after the merge; facts only, nothing decided here). PR #27 merged
2026-10-11 (merge commit `295a2e56`); the first pipeline run of the new code (workflow run `38163424458`) froze:

| Test | Freeze key | Start (UTC) | Status |
|---|---|---|---|
| §7 Treatment / Control / Challenger | `5e4630924d663fc5:92b67584f33cc1f0` | 2026-10-11 18:22:45 | RESET (previous key `…:3252a9f0d312db75` in the manifest history) |
| H2 (Amendment 5) | `5e4630924d663fc5:92b67584f33cc1f0:adeaccb163806651` | 2026-10-11 18:22:45 | RESET |
| H3 (Amendment 7 §3) | `5e4630924d663fc5:92b67584f33cc1f0:0eb650f81d99803e` | 2026-10-11 18:22:45 | STARTED |

Checked on `forward-ledger` @ `da366f16`: the archived 1H Treatment ledger holds both earlier trades (28 Sep, −1.021R;
7 Oct, −1.035R) and every new ledger starts empty. The decision rules and the decision date are unchanged.

## Amendment 8 (2026-10-12, operator request; written before H4 was run on any price history): arm H4 "Playbook"

**Why.** On bars without a signal the site shows a conditional playbook ("sell below X / buy above Y on a
close"). The operator asked that it be measured, so its directions are judged by a forward record and not by
how they look. H4 is a **new, separate arm**. It changes nothing in the engine, the §7 arms, H2 or H3, or their
freeze keys. The rule below is fixed here before H4 is run on any data; any change restarts H4.

**Levels at bar i** (all already published per bar by the frozen engine): PDH, PDL, PWH, PWL, PMH, PML, EQH,
EQL, the current day's high and low, the internal pivot high and low (`active_res` / `active_sup`), and the
100-bar volume profile's VAH, VAL and POC. ATR = the engine's adaptive ATR; stop distance D = the engine's regime
stop multiple × ATR. Levels closer than 0.05 ATR to one already listed are merged.

**The playbook at the close of bar i−1** (P = close[i−1], A = ATR[i−1], D = D[i−1]):
- sell trigger S = the highest level below P − 0.1·A; buy trigger B = the lowest level above P + 0.1·A;
- for each side, TP1 = the first further level at least 1·D beyond the trigger, TP2 = the next one; with no
  such level TP1 = trigger ∓ 2·D, and TP2 = TP1 when there is no second level.

**Signal at the close of bar i:**
- **SHORT** if close[i] < S; **LONG** if close[i] > B (both cannot happen on one bar).
- Entry close[i]; stop = S + D (LONG: B − D); TP1 / TP2 as above.
- No signal if close[i] is already beyond TP1, or if a value is missing (warm-up).
- No session or trend filter: it is the playbook as displayed (the site warns outside London / New York).

**Execution and costs:** `backtest.simulate`, as every other arm: one position at a time; an opposite signal
flips; stop first on a same-bar tie; 50% off at TP1, then breakeven.

**Freeze:** key = the §7 engine key + SHA-256 of `quantum/arm_h4.py`; ledger `holdout/<tf>_h4.json`; starts at the
first pipeline run after this amendment is merged. Earlier trades are in-sample only. The playbook the site
displays is the one `arm_h4.py` publishes for the last closed bar, so what is shown is what is measured.

**Decision:** the **15m** record decides, because the playbook is used on the site's default 15m chart; other
timeframes are reported only. After N ≥ 50 closed trades, H4 shows an edge only if the 95% t-interval of mean R
is above 0 and PF ≥ 1.2; decide by 2027-03-31, otherwise NOT SHOWN. **Multiplicity:** H4 is a sixth hypothesis
on the same market and period; each arm is reported on its own terms and none borrows another's evidence.

## Amendment 9 (2026-10-17, operator decision; written before any code below was changed or run)

**Why.** The operator asked that every improvement of the TradingView line up to its current build (v73; files on
branch `claude/xauusd-developed-files-tmnk9g`, reference copy and hashes in `reference/pine-v73/`) be brought to the
website. Amendment 6 still holds: only the website's records count; the Pine line's scorecards are not evidence.
Of the Pine builds v51–v73, two engine fixes also apply to the website. The operator chose (17 Oct, in chat): port
both and restart the forward test. Every other item is display only (§3).

**1. F-A64 (Pine v64): macro correlations over the same period.** Each macro series is read as `close[1]` of its
last bar before the chart bar's close (D-01 alignment, no look-ahead), but the engine correlated those returns with
gold's return over the *current* bar: gold now against the asset one bar earlier. Measured on the website's own
store (17 Oct, 1H, median |r| over the last 1,500 bars; the fix is chosen by the defect, not by these numbers):
silver 0.09 instead of 0.83, EURUSD 0.09 instead of 0.50, DXY 0.09 instead of 0.53. These correlations set the
macro weights, the correlation health (half of macro confidence) and the stability.
- Chart-timeframe assets (silver, EURUSD, SPX): correlated with gold's previous-bar return, `gold_ret[i−1]`, the
  period their `close[1]` return spans.
- Macro-timeframe assets (DXY, US10Y, TIPS; 1H): correlated with gold read exactly as they are, the gold 1H series
  through the same alignment (`close[1]` of the last 1H bar before the chart bar's close). Windows are counted in
  1H bars: length × k, k = max(1, ⌊3600 / chart seconds⌋), so a 1H series on a 15m chart keeps the sample its
  significance threshold assumes; a window over 4,500 chart bars reads as no data.
- Nothing reads an unfinished bar; the Bonferroni thresholds, windows (30 / 60 / 120), caps and signs are unchanged.

**2. F-A65 (Pine v65): each macro factor counted once.**
- **Dollar:** EURUSD is 57.6% of DXY. EURUSD votes, weighs (by its |corr|, cap 30, instead of a fixed 20) and adds
  its ±5 momentum term only when DXY has no data. The score term is gated as well, so the fallback weights cannot
  count the dollar twice.
- **TIPS:** off while its source is the 10Y yield itself (`tips_source = "us10y"`, the default). It is on only for
  its own feed (`fred_dfii10`).
- **Majority:** pool = 4 (USD, 10Y, SPX, silver) + TIPS when on + GC when valid; need = ⌈pool / 2⌉ (the existing
  rule over independent factors). Confidence availability = valid feeds / (5 + TIPS on).
- Not changed: vote directions, thresholds, the caps of DXY / 10Y / silver / SPX, the DXY and 10Y momentum terms.

**Effect on the records.** `features.py` is in the engine key, so the §7 key and every arm key that contains it
(H2, H3, H4) change; all restart at the first pipeline run of the new code. At this decision (ledger
`forward-ledger` @ `a48c4653`, 2026-10-17 01:00 UTC; no open positions) the records that move to the archive are
(closed trades / wins / total R):

| Arm | 1H | 4H | 15m | 5m |
|---|---|---|---|---|
| Treatment | 0 | 0 | 0 | 2 / 0 / −2.256R |
| Control | 0 | 0 | 0 | 0 |
| Challenger | 0 | 0 | 0 | 2 / 0 / −2.256R |
| H2 | 0 | 1 / 0 / −1.024R | 0 | 2 / 0 / −2.216R |
| H3 | 1 / 0 / −1.054R | 0 | 3 / 1 / +0.518R | 3 / 0 / −3.920R |
| H4 | 13 / 4 / −3.410R | 9 / 2 / −0.420R | **72 / 21 / −8.767R** | 232 / 80 / −36.971R |

**H4 interim reading, recorded before the restart.** H4's deciding record (15m, Amendment 8) passed N ≥ 50 on
2026-10-15 (50th closed trade exit 22:15 UTC). At this decision: N = 72, mean −0.122R, 95% t-interval
[−0.318, +0.075], PF 0.681. Under Amendment 8's rule that is **no edge shown**. This reading stays with the
archived trades and is reported beside H4's final result; the restart does not erase it.

The Amendment 4 rule applies: the final report lists every archived trade of every earlier freeze next to the
counted result. Decision rules and the decision date (2027-03-31) are unchanged.

**3. Display only (outside the freeze key; no record restarts for these).** Ported from v51–v73 where the website
lacked them: every indicator arrow coloured by what it means for gold, flat or weakly correlated (|r| ≤ 0.25) shown
as ≈ (F-A54), as a "gold arrows" grid; the five further gold drivers USDJPY, oil, real 10Y yield, 10Y breakeven and
US 2Y (v65; the website already shows USDJPY and oil); the in-sample overfit flag !FIT (in-sample win rate more than
rolling + 15, v61); "price through it: fires if this bar closes here" for a crossed playbook trigger (v61); MTF
layers that cannot vote on the chart's timeframe shown as "—" (F-A63); the engine's liquidity destination as
"liquidity draw", distinct from the nearest-level target (v57); ADX with DI+ / DI− (v67); a vetoed bar names its
block (F-A55). Already on the website: F-A62 (London DST from the IANA database, D-02), F-A60 (the website's H3
reads raw HTF scores), F-A55's DO NOW rule, the Market Brief (v52 was ported from the website).

**Amendment 9 — start record** (filled in after the merge; facts only, nothing decided here). PR #39 merged 2026-10-17
(merge commit `a7ef371e`); the first pipeline run of the new code (workflow run `39070785877`, engine `Q7.2-web.6`) froze:

| Test | Freeze key | Start (UTC) | Status |
|---|---|---|---|
| §7 Treatment / Control / Challenger | `5e4630924d663fc5:6f3964ad97813cc9` | 2026-10-17 21:26:18 | RESET (previous key `…:92b67584f33cc1f0` in the manifest history) |
| H2 (Amendment 5) | `5e4630924d663fc5:6f3964ad97813cc9:adeaccb163806651` | 2026-10-17 21:26:18 | RESET |
| H3 (Amendment 7 §3) | `5e4630924d663fc5:6f3964ad97813cc9:0eb650f81d99803e` | 2026-10-17 21:26:18 | RESET |
| H4 (Amendment 8) | `5e4630924d663fc5:6f3964ad97813cc9:090418672c210848` | 2026-10-17 21:26:18 | RESET |

Checked on `forward-ledger` @ `4cd5cb3b`: every new ledger starts empty, and the archive holds the earlier trades (H4 15m: all
72; H4 1h: 13; Treatment 5m: 12 across both earlier freezes). The decision rules and the decision date are unchanged.

## Amendment 10 (2026-10-20, operator request; written before H5 was run on any price history): arm H5 "High confidence"

**Why.** The operator asked for "quality trades to avoid loss", with a 90% win rate. A win rate cannot be promised:
no rule on this market can guarantee one, and choosing rules on past prices until they look accurate would be tuning
(§9 of the audit prompt), which this registration forbids. H5 is therefore a **stricter filter written down before
it is run**, measured forward like every other arm. It changes nothing in the engine, the §7 arms or H2–H4.

**Rule at the close of bar i** (every input is already published per bar by the frozen engine; no new threshold):
- **LONG** only if all of:
  1. the treatment engine itself signals BUY on bar i after all its own gates and vetoes (`exec_buy[i]`);
  2. the bias label is **BULL** (the engine's existing ≥ 62 conviction label, not BULL-ISH);
  3. every higher-timeframe trend layer that is live on the chart's timeframe among **4H and 1D** reads up (score ≥ 60,
     the engine's own HTF threshold), and at least one of them is live;
  4. the macro vote is bullish (`macro_bull[i]`, the engine's majority rule);
  5. session quality ≥ 30 (London / New York; the engine's own session gate, restated).
- **SHORT** is the mirror (SELL, BEAR, ≤ 40, `macro_bear`).
- **Plan:** the engine's own entry (close), stop and targets for that bar (`plan_sl`, `plan_tp1`, `plan_tp2`).
- **Execution and costs:** `backtest.simulate`, as every other arm: one position at a time, stop first on a same-bar
  tie, 50% at TP1 then breakeven.

**Freeze:** key = the §7 engine key + SHA-256 of `quantum/arm_h5.py`; ledger `holdout/<tf>_h5.json`; starts at the first
pipeline run after this amendment is merged. Earlier trades are in-sample only and are labelled so.

**Decision:** the **1H** record decides (the engine's registered timeframe); others are reported. After N ≥ 30 closed
trades (fewer than other arms because the filter is strict; set now, before any count is seen), H5 shows an edge only if
the 95% t-interval of mean R is above 0 and PF ≥ 1.2; decide by 2027-03-31, otherwise NOT SHOWN. The **win rate is
reported, not used to decide**: a trade that reaches TP1 and is then stopped at breakeven counts as a win at about +0.5R,
so the win rate depends on the exit design, and only the mean R and PF say whether money is made. **Multiplicity:** H5 is a
seventh hypothesis on the same market and period; it is a subset of the treatment arm's signals and borrows no evidence
from it.

## Amendment 11 (2026-10-22, operator decision; written before any historical data below was downloaded): research data split and validation protocol

**Why.** The research audit (`audit/RESEARCH_AUDIT_WEB_PHASE1.md`) found no out-of-sample intraday history in the store
and no measured edge in the live arms. New hypotheses need a sealed history. This amendment fixes the split, the data
source and the test protocol **before** the data exists here, so no boundary can be chosen by looking at results. It
changes nothing in the engine, the §7 arms or H2–H5.

**Data source.** Spot XAU/USD from **Twelve Data**, the feed the live engine already uses (no basis to a different
feed), intervals **1h** and **15min**, fetched backwards from the present to 2010-01-01 or the earliest bar the feed
serves, whichever is later. Stored on the branch `research-data` in the store format (`<series>/<YYYY-MM>.csv`), never
read by the engine or the site. (Dukascopy was the plan in the audit; it refuses GitHub's cloud addresses and its terms
restrict redistribution, so it is not used.) Every download is logged with its row counts and first / last bar.

**Split (calendar, fixed now):**

| Period | Dates (UTC) | Use |
|---|---|---|
| Development | earliest bar – 2019-12-31 | rules may be explored and parameters chosen, with walk-forward and purging |
| Validation | 2020-01-01 – 2022-12-31 | one evaluation per registered variant; no re-tuning on it |
| Sealed holdout | 2023-01-01 – 2025-12-31 | opened **once** per hypothesis that passed validation; its result is final |
| Live | from each hypothesis's registration | the forward ledger, as for every arm |

If the feed serves less than 3 years of development data for a timeframe, that timeframe is reported as "insufficient
history" and is not tested without a new amendment; the boundaries above do not move.

**Protocol (applies to every hypothesis tested on this data):**
1. The hypothesis (rules, timeframe, exits, costs, decision rule) is registered as an amendment before it is run on
   validation data.
2. Outcomes use a triple barrier: TP, SL and a time limit fixed in the registration; a win is TP before SL within the
   limit, after costs (the `backtest.py` cost model; plus a stress run at 2× costs and a 1-bar entry delay).
3. Development uses walk-forward folds with purging and an embargo of at least the time limit.
4. The number of variants tried on development is recorded. Selection among variants reports the Probability of
   Backtest Overfitting (CSCV) and the Deflated Sharpe Ratio.
5. **Pass on validation and on the holdout**: mean R > 0 with a t-statistic > 3.0 when chosen among several variants
   (> 2.0 for a single pre-registered rule), profit factor ≥ 1.2, and positive mean R under the stress run. White's
   Reality Check against "no trade" is reported.
6. The win rate is always reported with its Wilson 95% interval and never decides alone.
7. A hypothesis that passes the holdout becomes a new live arm with its own freeze key; only its live record is
   evidence on the site.

**Amendment 11 — data record** (facts only, nothing decided here). Workflow runs `39698853623` and `39699734825`
(2026-10-22) stored on `research-data`: TD_XAU_USD_1h 42,835 bars and TD_XAU_USD_15min 170,863 bars, both from
**2020-01-24 02:00 UTC** to the present. Requests for earlier bars return HTTP 404 for both intervals: that is the first
intraday bar the feed serves. Under this amendment's rule the development period (earliest bar – 2019-12-31) is empty, so
**1h and 15min are "insufficient history"**; no hypothesis is tested on them without a new amendment, and the boundaries
above do not move. No hypothesis has been run on this data.

## Amendment 12 (2026-10-31, operator decision "New arm H6 + relabel"; written before H6 was run on any price history): arm H6 "No score veto"

**Why.** The engine's calibrated long / short score (`cal_p_long` / `cal_p_short`; the Pine engines' calibrated P) gates
signals through the calibration veto (`cal_veto`: score < `cal_gate_min_p` = 0.50 once calibration is live). It was
measured against the event it is defined on: the race from the close, unit R = `aatr` × `reg_sl_mult` (nz 1.5), +1R
before −1R within the outcome horizon N (15m: 4 bars, 1h: 3), a bar touching both counting as a loss (the engine's own
`label_outcome` convention), labelled independently of the engine's own bookkeeping. The engine was run read-only on
a copy of the market-data store (`audit/tools/engine_dump.py`, `audit/tools/engine_calibration.py`; the scorer is
validated on synthetic perfect and constant forecasts). Results:
- **15m** (2026-08-05 → 2026-10-30, 3,043 resolved races): AUC 0.484 (block bootstrap 0.453–0.511); Brier 0.2637 vs
  0.2496 for a constant base rate (skill −0.056). The same before the forward start (AUC 0.499) and after (0.464).
- **1h** (2026-03-02 → 2026-10-30, 1,661 races): AUC 0.515 (0.483–0.548); skill −0.042.
- Reliability is flat: on 15m, quintile mean scores of 0.30 / 0.44 / 0.50 / 0.54 / 0.62 were followed by 0.50 / 0.51 /
  0.49 / 0.43 / 0.48.

The score does not rank outcomes, so the veto may remove trades at random. This is a measurement of the frozen engine;
**nothing in the engine, `config.py`, the §7 arms or H2–H5 changes**, and no forward record restarts.

**1. Display (outside the freeze key, no restart).** The site no longer presents the score as a probability:
- the veto reads "score below minimum (a score without measured skill, Amendment 12)";
- the score card's note and the method page state the measurement;
- the calibration table's column reads "Score at entry".

**2. Arm H6 "No score veto": the treatment engine's own signal without the calibration veto.** The rule at the close
of bar i, using only values the frozen engine publishes per bar:
- **LONG** if `should_buy[i]` (the seven entry gates) and none of `tq_floor_veto[i]`, `ev_veto[i]`, or (when
  `use_risk_limits`) `risk_lock[i]`. **SHORT** is the mirror with `should_sell[i]`.
- This is the engine's own `exec_buy` / `exec_sell` line without `cal_veto[i]`.
- The risk lock is the engine's, tracked on the treatment arm's own signals; it is not re-run on H6's trades.
- **Plan:** the engine's entry (close), `plan_sl`, `plan_tp1`, `plan_tp2` for that bar.
- **Execution and costs:** `backtest.simulate`, as every other arm. Each H6 signal the treatment arm did not take is
  marked `score_vetoed`.

**Freeze:** key = the §7 engine key + SHA-256 of `quantum/arm_h6.py`; ledger `holdout/<tf>_h6.json`; starts at the first
pipeline run after this amendment is merged. Earlier trades are in-sample only and are labelled so.

**Decision:** the **1H** record decides, as for the treatment arm and H5; other timeframes are reported. After
**N ≥ 50** closed trades, H6 shows an edge only if the 95% t-interval of mean R is above 0 and PF ≥ 1.2. Decide by
2027-03-31, otherwise NOT SHOWN. The win rate is reported, not used to decide.

**Reading against the treatment arm (reported, not decided):**
- H6's signals are a superset of the treatment arm's.
- If the veto is uninformative, H6's mean R matches the treatment arm's, with more trades.
- If H6 is worse on the score-vetoed trades (`score_vetoed`), the veto carried information the AUC missed.

**Multiplicity:** H6 is an eighth hypothesis on the same market and period. It is reported on its own terms and
borrows no evidence from the treatment arm.

## Amendment 13 (2026-10-31, operator decision "3y / 1.5y / 1.5y"; written before any research data was opened): research split re-registered

**Why.** Amendment 11 fixed the split 2010–2019 / 2020–2022 / 2023–2025 before the download. The feed serves intraday
XAU/USD only from **2020-01-24 02:00 UTC**, so its development period is empty and 1h / 15min are "insufficient history"
(A11 data record). Since then, **no hypothesis has been run on the research data and no statistic has been computed
from it**:
- the 2026-10-31 institutional audit (Pine line) deliberately did not open it;
- the A11 workflow logs record only row counts and first / last bars.

The boundaries below are therefore chosen blind, by the calendar.

**Split (replaces the A11 table; every other A11 rule is unchanged, including its ≥ 3-year minimum):**

| Period | Dates (UTC) | Length | Use |
|---|---|---|---|
| Development | 2020-01-24 02:00 – 2023-01-24 01:59 | 3.0 years | rules may be explored and parameters chosen, with walk-forward and purging |
| Validation | 2023-01-24 02:00 – 2024-06-30 23:59 | ~1.4 years | one evaluation per registered variant; no re-tuning on it |
| Sealed holdout | 2024-07-01 00:00 – 2025-12-31 23:59 | 1.5 years | opened **once** per hypothesis that passed validation; its result is final |
| Live | from each hypothesis's registration | — | the forward ledger, as for every arm |

The development period runs exactly three years from the first bar, so A11's minimum is met without being changed.
The operator's choice was "Development 2020 – 2022"; 2020-01-24 – 2022-12-31 is 2.94 years, so the boundary is set at
the third anniversary of the first bar rather than lowering the minimum. The protocol of A11 (registration before
validation, triple barrier, purged walk-forward folds, variant count, CSCV / PBO, Deflated Sharpe, pass thresholds,
stress run, White's Reality Check, Wilson-reported win rates, a new live arm only after the holdout) applies unchanged.
**Nothing has been tested yet**: the first hypothesis still needs its own registration under these rules.


## Amendment 14 (2026-11-01, operator approval "Apprive it and Merge it"; written and approved before any engine code was changed): realistic stop and target fills when a bar opens beyond them

**Approval record.** The operator approved the proposal `audit/AMENDMENT_14_GAP_STOP_PROPOSAL.md` (merged in PR #51,
commit `cc2ecd9d3`) in writing on 2026-11-01. The text below is that proposal's sections 1–12, copied verbatim; the
proposal file stays as the record of what was reviewed.

**Execution notes, fixed at approval:**

- **Commission.** No commission change rides along: the operator's MT5 evidence is not in yet, so `commission_l` stays
  $7 per lot round turn (§9 step 4 option not taken).
- **The web.6 engine.** It is preserved as merge commit `cc2ecd9d351d88ce4ae23de4f65497ae2e4bd698` on
  `claude/audit-prompt-real-artefacts-nekqv6`. The tag `engine-web.6-final` of §9 step 2 could not be pushed from the
  session (HTTP 403); the commit is the reference.
- **New exit labels.** The labels `SL_GAP` / `BE_GAP` are read by two consumers: H2's display statistic
  `next_move_stats` ("stop first" counts `SL` and `SL_GAP`) and the site's exit wording. No arm rule changes. H2's arm
  hash changes with that line, at the same restart that the engine key forces on every arm.

### 1. Current behaviour and its limitation

`quantum/backtest.py` (lines 23–69), on each bar after entry:

1. **Stop test:** long if `low ≤ stop`, short if `high ≥ stop`. The fill is at the **stop price**, labelled SL, or BE
   after TP1.
2. Otherwise **TP1:** if `high ≥ TP1` (long), half the position fills at **TP1**.
3. **TP2:** if `high ≥ TP2`, the rest fills at **TP2**. Otherwise, after TP1, the stop moves to entry from the next
   bar.
4. Stop first on a bar that touches both (conservative).

**The limitation (B-02):** when a bar **opens beyond the stop**, the stop is filled at the stop price. That price
never traded.

- The open is the first price at which the stop could have filled, so a real stop order fills at the open (or worse).
- The losses this optimism hides are the gap losses that matter most: weekend reopens, the daily 17:00 New York
  break, and news.
- Symmetrically, a TP limit that the bar opens beyond fills at the open in reality, which is **better** than the
  limit. That is a smaller, opposite error.

### 2. Proposed rule

For an open position on bar i (i > entry bar), using **only bar i's own OHLC**. Long is shown; short is the mirror
image.

| Step | Condition (long) | Condition (short) | Fill | Exit label |
|---|---|---|---|---|
| A1 | `open ≥ TP2` | `open ≤ TP2` | everything left at the **open**. If TP1 was not yet done, its half also fills at the open | TP2 |
| A2 | otherwise, TP1 not done and `open ≥ TP1` | `open ≤ TP1` | half at the **open** | (continue to B) |
| B1 | `open ≤ stop` | `open ≥ stop` | the rest at the **open** | `SL_GAP`, or `BE_GAP` after TP1 |
| B2 | otherwise `low ≤ stop` | `high ≥ stop` | the rest at the **stop price** (unchanged) | SL / BE |
| C | otherwise | otherwise | TP1 / TP2 intrabar exactly as now | TP1 / TP2 |

**Why the open goes first:** the open is the earliest price in the bar. A level the bar opens beyond was crossed
before any other price in that bar, so there is no ordering ambiguity and the stop-first tie rule does not apply.
Within the bar after the open, the existing stop-first rule is kept.

The new rule applies to the stop and both targets. Unchanged:

- entry at the signal bar's close;
- the flip at the close;
- the breakeven move from the next bar;
- the 50% split;
- open trades marked at the last close.

**Not adopted: a separate "gap slippage" charge.** A gap fill at the open already records the gap loss. Adding more
would invent a number that OHLC data cannot measure (§4).

### 3. Long and short positions

The rule is written once per side and mirrored. Long uses `open ≤ stop` and `open ≥ TP`; short uses `open ≥ stop` and
`open ≤ TP`. R stays `net / |entry − initial stop|`, unchanged, so an `SL_GAP` exit can be below −1 R. This is
intended: it is the real loss. Tests check each side separately (§7).

### 4. What OHLC data can and cannot show

- **Can:** that the first traded (quoted) price of the bar was beyond the level. The open is a recorded price.
- **Cannot:**
  - the path inside the bar;
  - the depth available at the open;
  - whether the broker's first fill was worse than the feed's open;
  - bid / ask at the open.

  The fill at the open is therefore a **lower bound on the damage**, not an exact broker fill. Real gap fills can be
  worse.
- **Reopen bars:**
  - The Sunday 22:00 UTC reopen bars (most gap exits measured here) carry an open that `sources.repair_reopen`
    rebuilt from 5-minute bars (D-09), because Twelve Data's first print is the quote carried through the closure.
    That open is itself an estimate, capped by `_cap_stale_open`.
  - The rule inherits that estimate.
  - It cannot be bettered without tick data, which the free data sources do not give.
- **Tick data:** an exact fill model would need the operator's broker ticks, or MT5 history with real fills. That is
  out of scope; it is listed as an open limitation.

### 5. Spread, slippage and commission: no double counting

- **Unchanged:** the round-trip cost `session spread + 2 × slippage + commission / 100`, charged **once per trade at
  entry** (§6.4 of the audit report).
- **The gap fill moves only the exit price.** It does not add a cost.
  - The spread is still charged once (the half-spread on each side is inside it).
  - Slippage is still 0.20 per side.
  - Commission is still per lot round turn.
- **A partial exit (TP1 at the open) does not charge a second commission:** commission is already a whole-trade
  round-turn figure.
- **Prices:** the feed's OHLC are quotes, used without bid / ask adjustment, as now. So a gap fill at the open is
  comparable with a normal fill at the stop.

### 6. Before and after (stored window; forward window = entries from 2026-10-17 21:26:18 UTC)

Two variants were measured:

- **"stop":** steps B1 / B2 only.
- **"proposed":** the full rule, A + B + C.

#### 6.1 Treatment (the engine's own BUY / SELL), every timeframe

| TF | n | Mean R | PF | Max DD (R) |
|---|---|---|---|---|
| 5m | 37 | +0.189 | 1.30 | 8.56 |
| 15m | 12 | +0.589 | 2.55 | 3.14 |
| 1h | 30 | +0.052 | 1.48 | 5.51 |

There were **no gap exits** on any timeframe, so **no trade changes**: these figures are the same before and after,
and the forward ledgers are unaffected.

#### 6.2 H4 Playbook (the only arm that trades through gaps)

| TF | Window | n | Current: mean R / PF / sum R / max DD R | Stop only: mean R / PF / sum R / max DD R | Proposed: mean R / PF / sum R / max DD R | Gap exits | Limit gap fills |
|---|---|---|---|---|---|---|---|
| 5m | all, 09-09 → 10-30 | 1731 | −0.1758 / 0.613 / −304.30 / 314.59 | −0.1771 / 0.612 / −306.56 / 316.84 | −0.1758 / 0.613 / −304.39 / 314.76 | 8 | 5 |
| 5m | forward | 498 | −0.1845 / 0.582 / −91.89 / 99.05 | −0.1847 / 0.581 / −91.97 / 99.14 | −0.1847 / 0.581 / −91.97 / 99.14 | — | — |
| 15m | all, 08-05 → 10-30 | 986 | −0.1073 / 0.675 / −105.83 / 111.11 | −0.1082 / 0.673 / −106.67 / 111.94 | −0.1077 / 0.674 / −106.15 / 111.42 | 12 | 3 |
| 15m | forward | 170 | −0.1095 / 0.727 / −18.61 / 22.75 | −0.1099 / 0.726 / −18.69 / 22.83 | −0.1099 / 0.726 / −18.69 / 22.83 | — | — |
| 1h | all, 03-02 → 10-30 | 729 | −0.0391 / 0.896 / −28.52 / 40.84 | −0.0443 / 0.884 / −32.32 / 44.33 | −0.0406 / 0.892 / −29.58 / 44.20 | 13 | 5 |
| 1h | forward | 49 | −0.1859 / 0.545 / −9.11 / 11.03 | unchanged | unchanged | — | — |

**Worst single gap exits:**

| TF | Exits |
|---|---|
| 5m | −2.94 R (2026-09-13 22:00, a Sunday reopen) |
| 1h | −2.78 R (2026-05-24 22:00) and −2.42 R (2026-06-14 22:00), both Sunday reopens |
| 15m | ≤ −0.26 R |

Under the current rule each of these was recorded at about −1 R.

**Win rate** falls by at most 0.3 points (1h: 39.09 → 38.82%).

### 7. Tests required before any engine change is merged

**Unit tests** (`tests/test_backtest_gaps.py`, hand-worked bars, written before the code):

1. Long, `open < stop`: exits at the open, label SL_GAP, R < −1 by exactly `(stop − open) / risk` plus cost.
2. Short, `open > stop`: the mirror of 1.
3. Long, open between the stop and entry, `low < stop`: fills at the stop (unchanged behaviour).
4. Long, `open ≥ TP2` with TP1 not done: both halves at the open; label TP2.
5. Long, TP1 ≤ open < TP2: half at the open, then the rest of the bar as now (it can still hit TP2 or the stop in the
   same bar).
6. After TP1 (breakeven stop), `open < entry`: BE_GAP at the open, which can now lose.
7. Short versions of 4–6.
8. A bar with open = stop exactly: counts as a gap (`≤` / `≥`), and fills at the same price either way.
9. NaN open: falls back to the existing rule. The data loader never emits one, but it is defended.
10. Costs: `cost_pts` is identical before and after for every trade (no double counting).

**Integration tests:**

11. `engine.run` → `backtest.simulate` on `load_synthetic` with forced gaps: every SL_GAP / BE_GAP trade has
    `exit = open[exit_i]`, and no trade's exit lies outside that bar's [low, high].
12. All arms (H2–H6, control, challenger) use the new fills through `backtest.simulate`; their own tests still pass.
13. `test_no_lookahead` and every arm's look-ahead test: a fill on bar i reads only bar i.

**Regression tests:**

14. On a fixture with **no gaps**, the new simulator gives trade lists identical to web.6's (entry, exit, P&L,
    labels).
15. Golden numbers from §6 (the stored window, frozen fixture): trade counts, number of gap exits, and sum R to 1e-3.
16. `holdout`: the new engine hash produces a new freeze key; `load_or_freeze` archives web.6 and starts web.7; no
    ledger entry is deleted.

**Edge cases:**

17. A gap on the bar right after entry.
18. A gap on a flip bar.
19. A gap on the last bar while the trade is open.
20. A Sunday reopen bar rebuilt by `repair_reopen`.
21. TP1 = TP2 (H4's no-second-level case).
22. A stop gapped exactly to TP on a short.

### 8. Expected effects

| Measure | Expected change |
|---|---|
| Expectancy | Lower for any arm holding through gaps; unchanged where no trade gaps. Measured: H4 −0.0009 to −0.0052 R per trade (stop only); −0.0000 to −0.0015 with symmetric limit fills; treatment 0 |
| Profit factor | Slightly lower (H4 −0.002 to −0.013); treatment unchanged |
| Max drawdown | Higher where gap losses cluster (H4 1h: 40.8 → 44.2–44.3 R); unchanged elsewhere |
| Individual trades | A few become worse than −1 R (to −2.9 R here). Some TP fills improve slightly. Win rate falls by ≤ 0.3 points |
| Conclusions | **None change.** H4 stays significantly negative (5m t −8.4 → −8.36 / −8.46). The treatment's small positive mean stays insignificant |

The correction makes the record **more honest, not better**. Its size is small on this sample because few positions
are held across gaps.

### 9. Engine version and forward-test restart procedure (on approval only)

1. Copy this text into `audit/PREREGISTRATION.md` as Amendment 14, with the approval date and the operator's words.
   Commit that **before** any code.
2. Tag the last web.6 commit `engine-web.6-final`, so the original engine stays checkable.
3. Write the tests of §7 first. They fail on web.6 (except 3, 14 and 15, which define the unchanged behaviour).
4. Change `backtest.simulate` only. Set `ENGINE_VERSION = "Q7.2-web.7"`. No other change rides along unless it is
   separately approved, for example the commission profile of `audit/COST_PROFILES.md` §5, if you choose to bundle it.
5. Run `python -m pytest -q tests` (all tests, including look-ahead) and the re-simulation of §6. The golden numbers
   must match.
6. Merge, then dispatch `quantum-site.yml`. On its first run:
   - `holdout.load_or_freeze` sees the new engine hash, sets status RESET, records web.6 in `history` with its
     `ended_utc`, and starts web.7 with a new freeze time.
   - Every arm key (engine key + arm hash) changes with it, so H2–H6 restart together.
7. Verify: the new main key is published; web.6 is in `history`; web.6 ledger entries are in `holdout/archive/` on
   `forward-ledger`; no file is deleted.
8. Record the web.7 start in `PREREGISTRATION.md` (key, time, run ID), as was done for Amendment 9.

### 10. Preserving the original engine and its records

- **The web.6 record:**
  - Its ledgers stay in git history on `forward-ledger` (normal commits, never force-pushed).
  - On restart they are moved, not deleted, to `holdout/archive/<tf>_<arm>.json` (`holdout.update_ledger`).
  - Every trade carries its `freeze_key`, so web.6 and web.7 trades can always be told apart.
- **The web.6 engine:** the tag `engine-web.6-final` and `holdout_manifest.json`'s `history` (key, version, start,
  end).
- **A web.6 summary to write at the restart:**
  - `audit/FORWARD_WEB6_FINAL.md`, with per-arm N, win %, mean R, t and PF from the archived ledgers.
  - So the original result is stated separately, and it is never pooled with web.7.
- **No pooling.** web.6 and web.7 results are reported separately. A verdict uses only one key's trades, as now.

### 11. Cost and alternative (for the operator's decision)

**The cost of approving:** every forward test restarts, losing about two weeks of counted record. The record is kept
in the archive, but it no longer counts toward a verdict. On the measured data the correction changes the forward
ledgers by at most 0.09 R in total (5m H4), and by 0 for the treatment.

**The alternative (not recommended as permanent):**

- Record a **shadow ledger** under the new rule from a module outside `ENGINE_SOURCES`, display only. Keep web.6
  counting; switch at the next restart that is needed anyway.
- This avoids a restart now. But the counted record would keep the optimistic fill until then, and a display-only
  ledger must never be cited as evidence (CLAUDE.md, one system of record).

**Recommendation:** approve the replacement (§9). Optionally bundle it with the commission profile of your verified
main account, once your MT5 evidence is in, so that the forward test restarts only once.

### 12. Open assumptions and limitations

1. The fill at the open is a lower bound on the gap damage; there is no tick data (§4).
2. Reopen-bar opens are estimates rebuilt from 5-minute bars (D-09).
3. Re-simulating today's store gives 498 / 170 forward H4 trades (5m / 15m), against 511 / 171 in the recorded
   ledgers. The recorded ledger is the record. Re-simulation depends on the store's start date: the engine's state is
   path-dependent, and each recorded run began from the store as it was then. The §6 forward rows are therefore
   indicative, not a restatement of the ledger.
4. The impact figures are in-sample, on 2–8 months of data: small samples, one market regime.
5. The broker commission and spread are not yet verified from MT5 evidence (`audit/COST_PROFILES.md`).

**Amendment 14 start record (2026-10-31 UTC).** Deployed by merge `3e32d4ba44940893bfbdd3ad42bda49ebfc90cc5` (PR #52), run
`quantum-site` #2280 (Actions run 41224028153). The run recorded the following on `forward-ledger` @ `5f72626c81ee11bf91e5cf9ebbf000f1a8a14de8`:

| Item | Value |
|---|---|
| Main key | `5e4630924d663fc5:60bb01794d03c9ac` |
| Engine | Q7.2-web.7 |
| Freeze (start) | **2026-10-31 17:23:01.937700 UTC** |
| Status | RESET |

The web.6 key `5e4630924d663fc5:6f3964ad97813cc9` (2026-10-17 21:26:18 → 2026-10-31 17:23:01) is in `history`.

Arm keys, each started at the same time:

| Arm | Key suffix | Note |
|---|---|---|
| H2 | `19433c9889d94f09` | the "stop first" label line changed |
| H3 | `0eb650f81d99803e` | |
| H4 | `090418672c210848` | |
| H5 | `40d438ea0c144199` | |
| H6 | `7c4ac023578836c6` | |

Every arm keeps its previous key in its own manifest's `history`.

**Archive check:**

- The 798 web.6 trades in the last web.6 snapshot (`a9bc97a1`) are all in `holdout/archive/`; none were lost.
- No web.6 trade remains in a live ledger.
- The web.6 summary is `audit/FORWARD_WEB6_FINAL.md`.
