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
