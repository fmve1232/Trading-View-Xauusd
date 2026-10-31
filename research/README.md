# XAUUSD Quantum — research programme (started 2026-11-01)

This folder answers the operator's "Deep quantitative research, strategy optimization & 90% accuracy" brief.

**Phase A** (audit and research design) is complete and awaits review. Nothing in production strategy logic was
changed. The engine (web.7), its freeze key `5e4630924d663fc5:60bb01794d03c9ac` and the forward test are untouched.

## Headline

1. **The playbook's "35% of 986" is measured correctly and loses money for a real reason:** its triggers carry
   **no directional information**.
   - Direction is right 48–50% of the time, on every timeframe.
   - Gross expectancy is −0.035 R; costs take it to −0.108 R.
   - The advertised 2:1 is measured from the trigger, not the entry: 1.26:1 from the entry. Most trades are then
     closed early by the next opposite trigger, so the realised payoff is 1.32 and the break-even win rate 43%.
   - See `03`.
2. **No arm has a demonstrated edge**, in-sample or forward, and **no displayed probability is calibrated**
   (`CURRENT_PERFORMANCE_AUDIT.md`).
3. **"90% accuracy" is admissible only for narrowly defined events**, with coverage, net expectancy and n ≥ 184
   (`09` §4). Nothing today meets that.

## Documents

| File | Status |
|---|---|
| `CURRENT_STRATEGY_AUDIT.md` | done |
| `CURRENT_PERFORMANCE_AUDIT.md` | done (executed) |
| `SIGNAL_OUTCOME_AUDIT.md` | done (executed) |
| `DATA_INTEGRITY_AUDIT.md` | done (executed) |
| `01_RESEARCH_LITERATURE_REVIEW.md` | done (references verified; per-method tests NOT TESTED) |
| `02_XAUUSD_MARKET_BEHAVIOUR_STUDY.md` | Phase B1 (needs runs on development data) |
| `03_CURRENT_35_PERCENT_PERFORMANCE_ROOT_CAUSE.md` | done (executed) |
| `04_STRATEGY_COMPARISON_MATRIX.md` | done (existing arms measured; library NOT TESTED) |
| `05`–`08`, `10`–`13` | Phase B; written from measured results, not before |
| `09_BACKTEST_AND_VALIDATION_FRAMEWORK.md` | done (specification) |
| `14_IMPLEMENTATION_ROADMAP.md` | done; prioritised table and approval gates |
| `15_ACCEPTANCE_TESTS.md` | done |

## Reproduce

```sh
TWELVEDATA_API_KEY=offline PYTHONPATH=. python audit/tools/h4_outcome_audit.py <market-data copy> 15m out.json
TWELVEDATA_API_KEY=offline PYTHONPATH=. python audit/tools/exec_sensitivity.py <market-data copy> 5m,15m,1h out.json
python audit/tools/forward_stats.py <forward-ledger checkout> 5e4630924d663fc5:6f3964ad97813cc9 --archive
```

The key only selects the stored Twelve Data series; network calls are disabled. **Without it the loader falls back
to GC futures:** this audit's first run did, and was discarded.
