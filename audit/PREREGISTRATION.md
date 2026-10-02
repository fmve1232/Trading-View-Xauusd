# Forward-test pre-registration — XAUUSD Quantum (build v33, amendment A1)

## Amendment A1 — 2026-10-02, operator decision; the holdout clock restarts

| # | Change | Why |
|---|---|---|
| A1.1 | Engine fixes **F-A38** (calibration fit made a constrained least-squares fit) and **F-A39** (Cornish-Fisher only inside its monotone domain), in the Master and all three arms | Found by executing the Pine formula text (`formula_trace.py`). Both change signals, so the v31 holdout (2026-09-28 → 10-02) is void. No forward trade had been logged. |
| A1.2 | Timeframe **1H → 15M** | Operator's choice: about 4× more signals, so the 50-trade decision comes sooner. **Disclosed:** before choosing, the operator saw 15M Strategy Tester results for Jul–Sep 2026 (Treatment PF 1.54, Challenger PF 1.52). That history is therefore **not evidence** for any arm; only trades after the new start count. |
| A1.3 | New holdout start **2026-10-05 00:00 UTC** and the new frozen hashes below | The first market open after the v33 files are delivered. |

Nothing else changes: the decision rules (§4), the decision date (§5) and H1 are as written on
2026-09-27. This amendment is written before any v33 forward data exists.

---

Original text (2026-09-27), with §2 updated by A1:


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
| Holdout start | **2026-10-05 00:00 UTC** (A1; was 2026-09-28) |
| Chart | OANDA:XAUUSD, **15M** (A1; was 1H), the same layout for every arm |
| Frozen scripts (SHA-256) | see table below; any change restarts the clock |

| File | SHA-256 |
|---|---|
| `XAUUSD_Quantum_5_0_Master.pine` | `6708cfb7cf51270371933cb7a194852443594445705310778cc599b1a08befed` |
| `XAUUSD_Quantum_5_0_Strategy.pine` (Treatment) | `4d544c9976c1d2ff806ef84db9a8c4b8b7e86b65c45158a478d321de456b243e` |
| `XAUUSD_Quantum_5_0_Strategy_OLDGATES.pine` (Control) | `7da48be0e80fbe1d6d07bb48ae746f0e7b41b3b3522306880ad6bcf114cbcce3` |
| `XAUUSD_Quantum_5_0_Strategy_CHALLENGER.pine` (H1) | `67bd4253f9e3133d1336aa906a66109a44ca6e47f8655f5cb36de1becb43f62e` |

Settings stay at the script defaults, except `MT5 Price Offset`, which is display only.
Strategy Properties stay at the code defaults: initial capital 10,000, 1 oz fixed, costs as
pinned in the code.

**Allowed during the holdout:**
- a fix for a compile or runtime error that does not change any signal, logged in
  `CHANGELOG.md` with its reason;
- display-only changes to the Master, Diagnostics or Visuals.

**Not allowed:** any threshold, weight, gate, input default or engine change in the four
files above.

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
