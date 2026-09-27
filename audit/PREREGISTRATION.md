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
| Engine | `quantum/`, `ENGINE_VERSION` Q7.2-web.3, the port of the v32 Master and its three arms |
| Freeze key | config hash `5e4630924d663fc5` + engine code hash `32babc71ed938b30` |
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
- **Mean-reversion saturation.** `mrComposite` sits at ±100 on about 60% of bars.
- **Open horizon mismatch.** F-035 is open.
- **No-resolution score.** Calibration has no resolution on the history (F-A34).
