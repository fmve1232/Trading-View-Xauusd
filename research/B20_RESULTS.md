# B20: run-continuation calibration (2026-11-07)

**Registration:** `research/registrations/B20.json`, commit `8ef843101`, committed before any code.

**Code:**
- Module: `quantum/research/b20.py`.
- Tests: `tests/test_research_b20.py`, 6 tests.

**Results:** `research/results/b20_development_2026-11-07.json`.

**Trials:** 58, phase `B20`.

**Question (operator):** when 15m candles are already running in one direction, does price reach +$15 / +$20 in that
direction before −$13?

**Answer: no.**

| Event | +$15 before −$13 | Random | +$20 before −$13 | Random |
|---|---|---|---|---|
| Every 15m close traded with its own direction (64,838) | 46.1% | 46.2% | 39.0% | 39.0% |

**By feature:**
- **No bin of any feature** moved the odds by more than ±2.2 points, except one: the 291 closes with a candle body
  ≥ 2.5 × ATR reached 50.5%. That is not significant (Holm p 1.00).
- **The declared combined rule** (≥ 3 candles, ≥ $15 already moved, 1h trend agrees) reached 44.6% of 1,364 at +$15
  and 38.8% at +$20.
- **The purged logistic model** had AUC 0.486 (+$15) and 0.477 (+$20). Its most confident tenth did worse than the
  rest.

**Outcome:**
- No candidate met the development screen, so the validation and holdout partitions stay closed.
- The full tables and the catalogue of every strategy tested are in `STRATEGY_CATALOGUE.md`, section 4.

**Commits:**

| Item | Commit |
|---|---|
| Registration | `8ef843101` |
| Code and tests | `245ba4b03` |
| Test fix (enough bars for ATR14; the earlier test failure was hidden by a pipe and is corrected) | `73f002672` |
| Development results | `e648a2083` |
