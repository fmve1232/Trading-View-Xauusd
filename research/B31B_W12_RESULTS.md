# B31b-W12 development results (2026-11-25): NO CANDIDATE

**The operator's pattern (registered before any code, `research/registrations/B31b-W12.json`):**
1. Before a session opens or closes, price runs in one direction.
2. It sweeps liquidity (a wick through a live level that closes back inside).
3. It reverses.

The question: from the sweep close, does the reversal reach +$10 (preferably +$15 / +$20) before price returns through the wick, at the broker cost with $650 planned loss?

**Setup:**
- **Data:** development 24 Jan 2020 – 24 Jan 2023 (hash `f113f97ad2105ff9`). Validation and holdout were not opened.
- **Events:** the production sweep detector found 5,771 sweeps, about 38 a week.
  - 2,100 of them (about 14 a week) match the pattern (H1): the sweep bar closes within 60 minutes of a session boundary, after a run of at least 1 ATR over the 4 bars before.
  - The boundaries are the Asia open, London open, New York open, London close and New York close.
- **EUR/USD** (the dollar factor) covers 99.8% of the bars.

## Result

| Candidate | Trades | +$10 before the wick (95%) | Break-even | Net R (day-clustered 95%) | $ / trade at $650 | Random entries | Holm p |
|---|---|---|---|---|---|---|---|
| H1: boundary sweep after a run | 2,100 | 26.2% (24–28%) | 32.9% | −0.255 (−0.313 to −0.195) | −166 | 26.5% | 1.00 |
| H1 + trend (H1 EMA20 vs EMA50) | 1,008 | 27.0% | 33.1% | −0.239 | −155 | 26.6% | 1.00 |
| H1 + value (previous day's POC on the reversal side) | 1,389 | 24.6% | 32.7% | −0.304 | −197 | 25.7% | 1.00 |
| H1 + dollar (EUR/USD did not confirm the run) | 618 | 29.1% | 34.7% | −0.188 (−0.292 to −0.077) | −122 | 28.8% | 1.00 |
| H1 + all three | 116 | 27.2% | 34.7% | −0.306 | −199 | 30.0% | 1.00 |

- +$15 and +$20 are negative for every candidate (−0.15 to −0.34 R).
- 27 of the 2,100 losses were larger than $650 because of gaps. The worst was $1,163.

## What the data says about the pattern

- **The timing is real.** Sweeps at session boundaries reached +$10 first more often than sweeps at other times: 26.2% vs 21.0% (p < 0.001). The run matters too: boundary sweeps without the run reached 17.7%.
- **It is not enough to profit.** A stop just beyond the wick (median $3.35 at the $4,000 scale) is crossed again before +$10 in about three trades out of four. This holds in every stop-size band:

  | Stop size | Reached +$10 first | Needed |
  |---|---|---|
  | $0–3 | 14.5% | 21.4% |
  | $3–6 | 28.9% | 35.3% |
  | $6–10 | 39.8% | 47.3% |
  | $10–20 | 53.8% | 59.5% |

  Every band falls short. These splits are descriptive and were not used to select anything.
- **The confirmations:**
  - The H1 trend adds nothing (+1.6 points, p 0.22).
  - Price being away from the previous day's POC makes it worse (−4.6 points).
  - EUR/USD not confirming the run adds +4.2 points (p 0.037, a secondary comparison) but stays below break-even.
- **By boundary (H1):** the New York open is the closest (31.3% vs 37.0% needed). The Asia open is the weakest (21.1% vs 27.5%).

## Not tested here, as registered

- **US 10Y yields:** no free intraday history before 2024.
- **Order flow:** real COMEX order flow was tested in B5 (reject). The tick-data study B5c needs the operator's laptop.

Both will be shown on the live sweep alerts as context (part B) and counted forward. That is not evidence yet.

## Verdict

**NO CANDIDATE.** The registered rule needs Holm p < 0.05, a positive net R with a positive lower bound, and at least 100 decided trades. No candidate meets it, so validation stays sealed.

Files:
- `research/results/b31b_w12_development_2026-11-25.json`
- `research/results/b31b_w12_trades_development_2026-11-25.csv.gz`
- The trial record appended to `research/trials.jsonl`.
