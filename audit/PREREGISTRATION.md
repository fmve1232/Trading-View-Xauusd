# Forward-test pre-registration — XAUUSD Quantum (build v37, amendments A1–A4)

## Amendment A4 — 2026-10-04, before the holdout start (operator: "show both, H2 as a second decision")

| # | Change | Why |
|---|---|---|
| A4.1 | The **Master shows H2** beside its DECISION: an H2 SETUP line (desktop decision footer, phone card row 5) with its own MT5 plan, and an H2 SETUP alert labelled "separate from DECISION". | The operator wants both signals on the decision screen. The H2 block is byte-identical to Strategy_H2 and Visuals (`h2_parity.py`, three files); on 5M/15M the Master's 1H/4H/1D trend scores are the H2 arm's (same requests, same 40/40/20 rule). |
| A4.2 | **The Master's DECISION is unchanged.** Its engine, gates and DECISION/BUY/SELL alerts are untouched; the only other Master changes are display strings moved to companions (session intelligence → Visuals H2 card; analog-evidence readout → Diagnostics "Analog evidence" row), to stay under the compiled-token limit. | Display only, as §2 allows; the Live arm's rule (execute the Master's DECISION) is unchanged. **An H2 SETUP executed on MT5 is NOT a Live-arm trade**: log it separately, or not at all; H2's record is the Strategy_H2 scorecard. |
| A4.3 | Strategy_H2 hash changes: the trend prelude moved out of the H2 block and two display strings moved to Visuals. **Signals identical** (same expressions; `h2_trace.py` PASS). | Lets the Master reuse the block without duplicate requests. |

Start date, timeframe, N, decision date and every rule are unchanged. §2 has the new Master and H2 hashes.

**Operator confirmation (2026-10-04, before the start):** "Keep H2 as it is, approved." The H2 rule in A3.2 is
confirmed unchanged; a sweep of previous day/week/month levels was considered and NOT added (it would be a
separate arm, H3, with its own pre-registration).

## Amendment A3 — 2026-10-04, before the holdout start (operator: signals from volume profile, trend, liquidity sweep, swings, next movement)

| # | Change | Why |
|---|---|---|
| A3.1 | New arm **H2 — sweep-to-value**, `XAUUSD_Quantum_5_0_Strategy_H2.pine` | The operator's specification. It is a different trading idea, so it is a new hypothesis. The Master's decision is not altered mid-test; H2 runs beside it. |
| A3.2 | H2 rule, fixed now with every value borrowed from the existing system (none fitted). **Trend:** ≥ 2 of the engine's HTF trend scores on completed 1H / 4H / 1D bars ≥ 60 (≤ 40 for down). **Swing:** the last unconsumed 5-bar pivot. **Sweep:** the confirmed bar trades through it and closes back inside. **Value:** the engine's volume profile (100 bars, 40 bins, POC, 70% value area) rebuilt every confirmed bar. **Entry:** long at or below POC, short at or above POC. **Plan:** SL = sweep wick ± 0.15 ATR with risk 0.5–5 ATR; TP1 = max(POC, 1R); TP2 = max(VAH, 2R) (mirrored for shorts). **Execution, costs, unit and scorecard:** identical to the other arms. | The signal block is byte-identical in Visuals (`h2_parity.py`); `h2_trace.py` executes it against this specification, and its volume profile equals the engine's VP code on the same bars. |
| A3.3 | **Multiple comparisons.** Two challengers (H1, H2) are now compared with the Treatment, so adoption of either uses a **97.5%** t-interval (Bonferroni, 0.05 / 2), plus PF ≥ 1.2 and a higher mean $ per position than the Treatment over the same window. Each arm's own EDGE SHOWN / NOT SHOWN verdict stays at 95% and is descriptive. | Testing two ideas at 95% each would give roughly a 1-in-10 chance of a false "better". |
| A3.4 | Same holdout start (2026-10-05 00:00 UTC), timeframe (15M), decision date and N = 50 for H2 | One protocol for every arm. |

The H2 hash is added to §2 below.

## Amendment A2 — before the holdout start (operator request: records inside TradingView; 5M and 15M)

| # | Change | Why |
|---|---|---|
| A2.1 | Engine fix **F-A40**: MTF confluence and MTF confidence normalised by the layers available on the chart's timeframe (Master and all arms) | The fixed denominator capped the score by timeframe (9/10 votes on 5M, 8/10 on 15M), so the same market scored differently on the operator's two charts. It feeds trade quality, so it changes signals. Made **before** the 2026-10-05 start: no holdout data is affected. |
| A2.2 | Each arm shows an on-chart **forward-test scorecard** (display only) | The operator wants the record inside TradingView. Its numbers follow the §4 rule exactly. |
| A2.3 | **Unit = position.** The arms close 50% at TP1 and the rest later; the two exits of one entry are ONE observation, with their P&L summed. A position still partly open is not counted until it closes. | §3 said "$ per trade". The List of Trades shows each partial exit as its own row, which would double-count and correlate the observations. |
| A2.4 | **15M stays the registered timeframe. 5M is for timing only:** a 15M BUY/SELL may be entered on a 5M trigger, but the record is the 15M arm. A scorecard on any other timeframe labels itself "does not count". | One registered timeframe keeps the test single-hypothesis (§6). |

The holdout start (2026-10-05 00:00 UTC), the decision rules (§4) and the decision date (§5)
are unchanged. The new hashes replace those in §2.

A2.5 (v35, display only): the scorecard verdict treats a record with no losing position as PF = ∞
(passes the PF rule) instead of na (failed it). No signal changes; the arms' hashes in §2 are updated.

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
| `XAUUSD_Quantum_5_0_Master.pine` | `1fce11001d0a549d894de4ad792ed59003b0bb469c8686d3a9ea02e37aa540c5` |
| `XAUUSD_Quantum_5_0_Strategy.pine` (Treatment) | `86193648198fd1d2c947658457af811d6396f6c156215e823befeddffa3b8d38` |
| `XAUUSD_Quantum_5_0_Strategy_OLDGATES.pine` (Control) | `256eaf50d61526bbd36897828f23d140fd5053b37e9c39d5e3d69637bb4869b7` |
| `XAUUSD_Quantum_5_0_Strategy_H2.pine` (H2) | `7f110a9f89387b3e19e148cd1682de263c08462e0f39b3a18cd80095e3ae77bb` |
| `XAUUSD_Quantum_5_0_Strategy_CHALLENGER.pine` (H1) | `8db04fbbc1db9818e6390d8c659b4183e2f93e49450d348bbdc29889272025ae` |

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
