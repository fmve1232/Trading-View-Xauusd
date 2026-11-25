# B31b-W8 development results (2026-11-25): NO CANDIDATE

**Question (registered 19 Nov, `research/registrations/B31b-W8.json`):** do quality-selected M15 / M30 breakout entries
reach **+$10 before the stop** often enough to make money at the operator's broker cost, with $650 planned loss?

- **Data:** development partition only, 24 Jan 2020 – 24 Jan 2023 (data hash `f113f97ad2105ff9`, the same as W3–W7). The validation and holdout partitions were not opened.
- **Cost:** `research/registrations/B31b-W8-cost.json`, committed before the run.
  - The broker's spread was read from the operator's MT5 screenshots: $0.52 at 06:25 UTC on 19 Nov and $0.45 at 06:53 UTC on 25 Nov, both in the Asian session.
  - Commission, contract size and the other sessions' spreads cannot be read from a chart. They stay the W3 model, labelled ASSUMED.
- **Code:** `quantum/research/w8quality.py` (sha256 `c74571033767e677…`), unchanged since its tests were committed.

## Result

| Entry | Ready trades | +$10 first (95%) | Break-even | Net R (day-clustered 95%) | $ / trade at $650 | vs random entries (Holm p) | vs the non-selected breakouts (p) | Candidate |
|---|---|---|---|---|---|---|---|---|
| E0:M15 (market at the breakout close) | 67 | 50.7% (39–62%) | 55.8% | −0.108 (−0.313 to +0.097) | −70 | 50.7% vs 49.7% (0.431) | 0.412 | no |
| E0:M30 | 74 | 58.1% (47–69%) | 59.6% | −0.022 (−0.203 to +0.172) | −14 | 58.1% vs 49.9% (0.159) | 0.010 | no |
| E1:M15 (market at the confirmation close) | 49 | 53.1% (39–66%) | 56.1% | −0.035 (−0.298 to +0.215) | −23 | 53.1% vs 47.1% (0.355) | 0.279 | no |
| E1:M30 | 68 | 60.3% (48–71%) | 58.8% | +0.042 (−0.171 to +0.247) | +28 | 60.3% vs 49.5% (0.092) | 0.041 | no |

- +$15 and +$20 are negative for all four entries: net R from −0.04 to −0.37.
- No trade lost more than the $650 planned. The worst was $650 including costs.

**Why none is a candidate.** The registered rule needs all four of the following:
- Holm p < 0.05 against random entries.
- A positive net R whose day-clustered 95% lower bound is also above zero.
- At least 100 decided trades.
- The selected breakouts beating the non-selected ones.

No entry meets them. The closest, E1:M30, has 68 trades, Holm p 0.092 and a lower bound of −0.171. By the registration, validation is opened only for a candidate, so it stays sealed.

## What the quality selection did

- **The quality score does separate breakouts.** Its out-of-fold AUC is 0.668 for "the breakout does not close back inside within 16 bars". On M30, the selected breakouts reached +$10 first more often than the non-selected ones (58–60% vs 44–49%; p = 0.010 and 0.041).
- **Few of the selected breakouts pass ENTRY READY.** Of 655–1,195 selected orders per entry, only 49–74 are ready. Most fail the "entry at most 1.0 × ATR beyond the level" check, because a strong breakout candle has already travelled. Those checks are registered and unchanged.
- **Cost sensitivity.** With the full W3 model, E1:M30's net R is +0.042. At 1.5 × cost it is +0.006, and at 2 × cost it is −0.027. The other three stay negative.

## Verdict

**NO CANDIDATE.** These results do not support a validated entry that reaches +$10 before the stop often enough to make money at the measured broker cost. The reliability table of the quality score is in the JSON; it is **not** a validated probability.

Files:
- `research/results/b31b_w8_development_2026-11-25.json`
- `research/results/b31b_w8_trades_development_2026-11-25.csv.gz`
- The trial record appended to `research/trials.jsonl`.
