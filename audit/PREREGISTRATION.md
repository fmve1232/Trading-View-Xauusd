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
