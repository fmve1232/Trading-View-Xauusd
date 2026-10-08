# Forward-test pre-registration — XAUUSD Quantum (build v42, amendments A1–A7) — SUPERSEDED: the record is the website

## Amendment A7 — 2026-10-08: this pre-registration is SUPERSEDED; the website is the only system of record

**Operator decision, confirmed in this session on 2026-10-08:** "Website only". It confirms the decision recorded on
the default branch (`claude/audit-prompt-real-artefacts-nekqv6`, `audit/PREREGISTRATION.md`, Amendment 6 of 2026-10-06, "option 1").

1. **Nothing on this branch is counted.** The TradingView 15M arms (Treatment, Control, Challenger, H2 sweep-to-value),
   their on-chart scorecards and this file's amendments A1–A6 are **display only**. They must not be cited as evidence
   for or against any arm, and the decision rules of §4 are not applied to them.
2. **The counted tests are the website's**, as written in the default branch's pre-registration: §7 Treatment /
   Control / Challenger on 1H (started 2026-10-03 10:37 UTC) and its Amendment 5 H2 "Sweep and Value" (started
   2026-10-04 07:55 UTC). This branch does not change them.
3. **No more holdout restarts here.** Changes to these files no longer restart anything. The §2 hashes below are kept
   as history of builds v33–v41 and are not a freeze.
4. **Fix made under this amendment (F-A47):** exits are placed on the entry bar (they were placed one bar late, so
   the first bar after every entry had no stop or targets). This changes the TradingView backtests only.
5. The Pine reference used to validate the website stays at v32 on the default branch, as its Amendments 2 and 6 say.

## Amendment A6 — 2026-10-06, during the A5 holdout; the clock restarts for the engine arms (operator decision)

| # | Change | Why |
|---|---|---|
| A6.1 | **Engine fix F-A46** in the Master, Treatment, Control, Challenger (and Diagnostics): the volume profile is rebuilt on every confirmed bar instead of the last bar only | Its POC/VAH/VAL are stop/target candidates and feed the plan EV veto, so recorded (recomputed) trades and live signals used different plans. Changes signals; under §2 that restarts the clock. |
| A6.2 | New holdout start **2026-10-07 00:00 UTC** for the Live arm, Treatment, Control and Challenger; their §2 hashes replaced | About 10 hours of the A5 holdout are discarded for these arms. |
| A6.3 | **H2 keeps its 2026-10-06 00:00 UTC start**: its file is unchanged (its own profile was always rebuilt every confirmed bar). The workbook counts H2 from Read Me D5, the others from B5. | H2 is not affected, so its record is not reset. |

Nothing else changes: 15M, N = 50, §4, §5, H1, H2 (A3.2). For the H1/H2 vs Treatment comparisons, "the same window" (A3.3) is the window from 2026-10-07, where all arms are counting.

## Amendment A5 — 2026-10-05, after the planned start; the holdout clock restarts (operator decision)

| # | Change | Why |
|---|---|---|
| A5.1 | **Compile fix F-A42** in the four strategy arms (scorecard start input) | All four arms failed to compile on the operator's chart (CE10123), so none of them recorded anything from the 2026-10-05 start. Signal-neutral. |
| A5.2 | **Engine fix F-A41** in the Master, all four arms, Diagnostics and Visuals: higher-timeframe `request.security` of offset values uses `lookahead_on` | The Diagnostics probe measured the daily value two days old on 6,027 of 6,091 historical bars but one day old live, so the recorded (recomputed) trades and the live alerts used different data. This changes signals; under §2 it restarts the clock. The operator chose to fix and restart. |
| A5.3 | New holdout start **2026-10-06 00:00 UTC**, and the new hashes in §2 | No arm had recorded a position (they did not compile); the Master's live DECISION on 2026-10-05 is outside the record either way. |

A5.4 (v39, 2026-10-05, before the new start; display only): the PDL-first count restored in the three twins (F-A44) and the Master's H2 line split in two for the desktop cell. No signal changes; §2 hashes updated.

A5.5 (v40, display only): the per-feature directional edge is computed over resolved analogs (F-A45) in the Master and the three twins; Diagnostics relabels it. No signal changes; §2 hashes updated.

Everything else is unchanged: 15M, N = 50, the rules of §4, the decision date of §5, H1 and the H2 rule (A3.2, confirmed in A4). Trades opened before 2026-10-06 00:00 UTC do not count.

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
| Holdout start | **2026-10-07 00:00 UTC** (A6) for Live / Treatment / Control / Challenger; **H2 2026-10-06 00:00 UTC** (A5, unaffected by A6) |
| Chart | OANDA:XAUUSD, **15M** (A1; was 1H), the same layout for every arm |
| Frozen scripts (SHA-256) | see table below; any change restarts the clock |

| File | SHA-256 |
|---|---|
| `XAUUSD_Quantum_5_0_Master.pine` | `d8cf5eaaf6cb24d48ab2517ec1416d23694bc872952347b7460c9c5749879a4e` |
| `XAUUSD_Quantum_5_0_Strategy.pine` (Treatment) | `2f43566ff43fcec2fbdcc7b8709b5b1383f725c58f8f00c2a6328a9cb01d7d59` |
| `XAUUSD_Quantum_5_0_Strategy_OLDGATES.pine` (Control) | `a927a6e3ba3921db15df5e1641c0f1d09fbee64714082bb37d9a3cf44f9ca7b7` |
| `XAUUSD_Quantum_5_0_Strategy_H2.pine` (H2) | `e9114048b13e4f85e3a4df42c3b5075b6b85a8b31618a047d79ba6d13054d34d` |
| `XAUUSD_Quantum_5_0_Strategy_CHALLENGER.pine` (H1) | `2f14870f4ca9861c7bfb113b35ab22eeefb80329e3dc2fa822d412dd71326984` |

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
