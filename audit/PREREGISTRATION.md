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
