# B21: liquidity and breakout alerts WITH confirmation, no session filter (2026-11-07)

**Request (operator):** "liquidity & price breakout should be notified with confirmation as after alert it should
move $15 to $20 in the direction of alert notified" (not about sessions).

**Registration:** `research/registrations/B21.json`, commit `efee99854`, committed before code.

**Code:**
- Module: `quantum/research/b21.py`.
- Tests: `tests/test_research_b21.py`, 4 tests.

**Results:** `research/results/b21_development_2026-11-07.json`.

**Data:** development 2020–22, the site's own four alert types, one per idea, with no session filter.

**Two measures:**
- **"First":** +$15 / +$20 reached before −$13, from the actual entry, after costs.
- **"Any time":** +$15 / +$20 reached at some point in the next trading day, ignoring any stop. This is the operator's
  literal measure.

## Results at +$15

| Alert (ideas) | Entry | Trades | +$15 first | Any time | Net $ / oz |
|---|---|---|---|---|---|
| GRAB (855) | at the alert | 855 | 47.3% | 66.7% | −0.64 |
| | after a $15 close beyond | 302 | 43.4% | 69.9% | −1.68 |
| | after a $20 close beyond | 238 | 49.6% | 68.1% | +0.09 |
| BREAK (781) | at the alert | 781 | 46.5% | 61.8% | −0.88 |
| | after $15 | 277 | 43.7% | 66.8% | −1.60 |
| | after $20 | 210 | 48.1% | 71.9% | −0.34 |
| SWEEP (2,928) | at the alert | 2,928 | 46.4% | 64.7% | −0.87 |
| | after $15 | 949 | 46.0% | 67.0% | −0.88 |
| | after $20 | 757 | 46.4% | 64.7% | −0.74 |
| BREAKOUT (2,882) | at the alert | 2,882 | 46.3% | 65.8% | −0.88 |
| | after $15 | 958 | 48.4% | 69.0% | −0.17 |
| | after $20 | 763 | 47.7% | 71.2% | −0.43 |
| **Random entries** | — | — | **46.2%** | **65.0%** (64–66%) | about −0.9 |
| Random triggers + $15 confirmation | — | 5,263 | 45.3% | 66.1% | −1.10 |

## Verdict

- **All eight pre-registered tests (H1–H8) FAIL.** Every Holm-adjusted p is 1.00, and the best net result is +$0.09 per
  oz (t 0.10).
- Confirmation changes the odds by −3 to +3 points, inside the noise. The validation and holdout partitions stay
  closed.
- **At +$20 the picture is the same:**
  - first-touch 35–43% against 39% random;
  - "any time" 53–64% against 53–56% random.

## Correction made during the run

The random baseline for "any time" first came out as 100%. The function used drops the trades that never reach the
target, so only winners were left.

- **The fix:** it is now computed with `b21.reached_any`, and a test was added.
- **Corrected baseline:** +$15 at 66.4% (BUY) / 63.7% (SELL); +$20 at 56.3% / 53.0%.
- **Scope:** no alert figure or verdict depended on it.
