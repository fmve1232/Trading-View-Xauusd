# Signal and outcome audit — the 20 questions of the research brief, Part 1 (2026-11-01)

These are answers for the H4 Playbook record shown on the site. The same execution model (`quantum/backtest.py`)
serves every arm, so the answers about measurement apply to all of them.

Numbers come from `audit/tools/h4_outcome_audit.py`, 15m, 2026-08-05 → 10-30, unless stated otherwise.
`03_CURRENT_35_PERCENT_PERFORMANCE_ROOT_CAUSE.md` has the full tables.

| # | Question | Answer | Evidence |
|---|---|---|---|
| 1 | Closed trades or theoretical triggers? | **Closed simulated trades** (986), from 1,628 trigger bars | `report.h4_section` → `in_sample`; tool §1 |
| 2 | Are the 986 unique and independent? | Unique (one position at a time). **Not independent in time:** 834 of 985 next entries happen on the previous exit bar (flips). Lag-1 autocorrelation of R is −0.025 | tool `independence` |
| 3 | Several signals from one move? | Yes: 641 triggers fired while a same-direction trade was open and were ignored; consecutive opposite triggers cause flips | tool `triggers` |
| 4 | Overlapping trades counted twice? | No; the simulator holds one position | `backtest.simulate` |
| 5 | Outcome measured at? | The **final net R** of the whole trade. A "win" is R > 0 | `backtest.metrics` |
| 6 | Partial profits included? | Yes: 50% at TP1, then breakeven; the rest at TP2, the stop, breakeven or a flip | `backtest.simulate` |
| 7 | Stop-loss outcome correct? | Yes: the stop price, or the bar's open when it gapped through (web.7). 23 tests; mutation test 13 / 15 (2 equivalent) | `audit/WEB7_VERIFICATION_2026-11-01.md` |
| 8 | TP-before-SL verified with ticks? | **No tick data exists** for this project. Bars only; a 5-minute re-walk of 15m / 1h trades changed 15 of 595 and 4 of 171 trades | `audit/GAP_SENSITIVITY_2026-11-01.md` §3 |
| 9 | Both barriers touched in one candle? | 8 of 986 trades (0.8%) had a bar touching both the stop and TP1 | tool `excursions` |
| 10 | Ambiguous outcomes misclassified? | Resolved **stop first** (the conservative choice), never in the trade's favour. Not labelled AMBIGUOUS: that label would need an engine amendment. At most 8 outcomes are affected | `backtest.py` docstring |
| 11 | Spread? | Included, once per trade: 0.30 in session, 0.50 off session | §6.4 of the audit report |
| 12 | Commission? | Included: $7 per lot round turn (frozen; broker rate unverified) | `config.commission_l` |
| 13 | Slippage? | Included: 0.20 per side | `config.slippage_pts` |
| 14 | Rollover / swap? | **Not included.** 56 of 986 trades (5.7%) were held over 17:00 New York | tool `excursions` |
| 15 | Thin liquidity? | Signals fire in every session. Off session: 117 trades; Asian: 358, the worst at −0.18 R | `03` §4 |
| 16 | During market closure or rollover? | **Closure: no.** Market-shut bars are removed before the engine (`sources.trading_week_only`). **Rollover hour:** the 17:00–18:00 New York break is removed; the reopen bar is repaired (D-09) | `quantum/data/sources.py` |
| 17 | Regimes mixed? | Yes, in the headline; split in `03` §4. No regime is significantly positive | `03` §4 |
| 18 | Buy and sell combined? | Yes, in the headline. Long −0.126 R, short −0.088 R; both negative | `03` §4 |
| 19 | Sessions combined? | Yes, in the headline; split in `03` §4 | `03` §4 |
| 20 | Training, validation or unseen data? | **In-sample.** H4 was pre-registered and never fitted, but this window is not unseen. The only out-of-sample record is the forward ledger: web.6 15m n 171, −0.09 R (archived); web.7 started 31 Oct | `audit/FORWARD_WEB6_FINAL.md` |

**Conclusion.** The measurement is sound. Its weaknesses are the absence of ticks and of swap, and both are small.
The negative result is a property of the signal (§0 of `03`).
