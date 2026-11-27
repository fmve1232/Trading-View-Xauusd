# Broker cost validation (2026-11-26)

**Finding: only the Asian-session spread has been measured at the operator's broker. Every other cost input is
estimated or assumed.** The production engine uses one flat $0.30 spread. The broker showed $0.45–0.52 in Asia and
about $0.80 near the New York close (one reading). No account statement or MT5 symbol specification has been
supplied, so commission, contract size, tick value, swap, slippage, execution delay and stop / target fills are
UNVERIFIED. Nothing below is invented to fill those gaps.

## 1. What each cost input is

| Input | Value used | Where | Status | Evidence |
|---|---|---|---|---|
| Spread, Asia | $0.485 / oz (W8 decision cost); engine $0.30 | `research/registrations/B31b-W8-cost.json`; `quantum/config.py` `spread_cost` | **MEASURED** (2 screenshot sets, 19 and 25 Nov, about 06:25 and 06:53 UTC): M15 $0.52 and $0.45; M30 $0.61 and $0.49; H1 $0.55 and $0.33 | `research/tools/spread_from_screenshots.py` (W8 branch); fit error ≤ $0.17 |
| Spread, New York close | — | — | **MEASURED, 1 reading:** about $0.80 at a 20:55 clock reading on one day of the 23–25 Nov screenshots (M15 / H1). Erratum 26 Nov: first written as "20:55 UTC on 26 Nov", a time that had not yet occurred; the day and the clock's time zone are in the operator's private screenshots and are not re-checked here; a single reading near the daily rollover, not a session average | screenshot analysis of 26 Nov (operator's screenshots, not committed: private) |
| Spread, London / New York / overlap / off-hours | $0.30 (London / New York), $0.50 (off), W3 model | `B31b-W8-cost.json` `assumed` | **ASSUMED** | none |
| Spread during high-impact news | not modelled separately | — | **UNVERIFIED** | none |
| Commission | $7 per 100-oz lot round trip ($0.07 / oz) | `config.py` `commission_l` | **ASSUMED** | none |
| Contract size / tick value | 100 oz per lot; $1 per $0.01 per lot | `config.py` `point_value`; `quantum/contract.py` | **ASSUMED** | none |
| Slippage | $0.20 per side | `config.py` `slippage_pts` | **ASSUMED** | none |
| Swap | not modelled | — | **UNVERIFIED** (most positions close the same day; the 1h and 4h arms hold for hours to days) | forward 1h H4 average hold: 217 min |
| Execution delay | phone alert median 248 s after the bar close (server acceptance) | delivery log | **MEASURED to the ntfy server only** | `evidence/alert_delivery_2026-11-26.txt` |
| Stop / target execution | simulated: a bar opening through the stop fills at its open (gap); a bar touching both counts as the stop | `quantum/backtest.py` `simulate` (Amendment 14) | **MODELLED**; never compared with broker fills (GA-28) | `tests/test_backtest_gaps.py` (23) |
| Weekend and market gaps | as above; GAP RISK line on C1 plan alerts | `confirm_entry.gap_line` | **MODELLED**; historical worst gap losses $6,061 (W5) and $2,922 (W7) on $650 plans | study result files |

The engine's round-trip cost per oz is $0.77 ($0.30 spread + 2 × $0.20 slippage + $0.07 commission). Every live H4
trade carries exactly this (`cost_pts_used: [0.77]` in `evidence/forward_report_2026-11-26.json`).

## 2. Effect on the forward results (sensitivity, not validation)

Net P&L = gross P&L − spread − commission − slippage − swap. Only the spread is varied here; swap is not modelled.
The engine's R is net points / stop distance, so a wider spread costs (spread − $0.30) / stop distance in R.

| Ledger | Trades | Median stop | Cost / stop (median) | Mean R at the model cost | at $0.50 spread | at $0.80 spread |
|---|---|---|---|---|---|---|
| 5m H4 | 410 | $9.28 | 9.0% | −0.138 | −0.161 | −0.197 |
| 15m H4 | 148 | $16.46 | 5.1% | −0.060 | -0.073 | -0.093 |
| 30m H4 | 70 | $22.06 | 3.9% | +0.028 | +0.019 | +0.005 |
| 1h H4 | 37 | $42.63 | 2.0% | −0.308 | −0.313 | −0.322 |

Every ledger's figures at both spreads are in `evidence/forward_report_2026-11-26.json` (`mean_r_at_spread`). Two
points follow from the arithmetic:
- **Short stops are the most cost-sensitive.** On 5m, the model cost already takes about 0.10 R per trade, which is
  most of the gap between the gross result (−0.039 R) and the net one (−0.138 R).
- **Wider measured spreads only make the result worse.** No spread in the measured range turns a negative ledger
  positive.

## 3. What is needed to validate costs (from the operator)

| Item | How | Closes |
|---|---|---|
| MT5 symbol specification for XAUUSD | MT5: Market Watch, right-click XAUUSD, Specification (contract size, tick size and value, commission, swap long / short, stops level) | commission, contract size, tick value, swap |
| An account statement with fills | MT5: History, right-click, Report (any closed XAUUSD trades) | slippage, real stop / target fills, GA-28 |
| Spread by session | the spread column of an MT5 M1 or tick export covering a full week, or timed screenshots in each session | spread by session and around news |

Until these arrive, the cost section of the engineering score counts them as UNVERIFIED, and every expectancy figure
in this programme carries the label "model cost".
