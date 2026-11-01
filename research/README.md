# XAUUSD Quantum — research programme (started 2026-11-01)

This folder answers the operator's "Deep quantitative research, strategy optimization & 90% accuracy" brief.

**Phase A** (audit and research design) is complete and was reviewed (PR #56). **Phase B0** (research harness, `quantum/research/harness.py`, tested), **Phase B1** (published-evidence families on development data), **Phases B2 / B2b / B2c** (SMC setups against the operator's trades), **Phase B3** (trend + confirmation + sequences) and **Phase B4** (entry-price hypotheses) are done: 448 trials, none passes its declared rules, none near 90%. Nothing in production strategy logic was
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
| `TARGET_MOVE_90PCT_STUDY.md` | done (executed): "90% of trades move $10–20 my way": every decision source = a random entry; 90% only with ~$90 room (coin-flip arithmetic) |
| `B1_DEVELOPMENT_RESULTS.md` | **Phase B1 done** (development data only): 100 trials, 0 with positive net expectancy; nothing registered for validation |
| `B2_DEVELOPMENT_RESULTS.md` | **Phase B2 done** (development data only): 9 SMC setups × 15min / 1h × the operator's trade (+$20 / +$10 / +$2 before −$10) = 54 trials; none above break-even, none beats random; nothing registered |
| `B2B_DEVELOPMENT_RESULTS.md` | **Phase B2b done** (development data only): the same nine setups on +$20 before −$20 (SL / TP $1,000 at 0.5 lot) = 18 trials; none passes (best 1h FVG retest 52.6% against a 52.1% break-even: t +0.44, z +1.69, Reality Check p 0.996) |
| `B2C_DEVELOPMENT_RESULTS.md` | **Phase B2c done**: +$15 before −$10 (18 new trials), reported beside B2's +$10 and +$20 before −$10; 0 of 54 setup-target pairs net-positive; nothing registered |
| `B3_DEVELOPMENT_RESULTS.md` | **Phase B3 done**: trend alignment + confirmation entries + SMC sequences on the −$10 stop, +$10 / +$15 / +$20: 210 trials; highest success 57.1% / 48.6% / 43.5% on small samples; 0 near 90%; none passes |
| `HC_PHASE1_AUDIT_AND_BASELINE.md` | **High-confidence confirmation engine brief, Phases 1–2** (no production change): requirement-by-requirement audit, dependency map, test coverage (4 / 13 / 13 of 30), executed baseline (245 + 17 tests; web.6 forward; TP-first profiles A–D), the 90% gate on current evidence, ranked findings and the proposed Step A / B / C plan awaiting approval |
| `ENTRY_PRICE_RESEARCH.md` | **Entry-price research + Phase B4** (development only): why no entry price can confirm +$10 (optional stopping; the drift 90% would need: ≈ $11 / hour), literature review with sources, 48 declared trials. Session-open momentum: nothing; limit entries: no benefit; round-number crossings ($50 / $100): the one consistent lead (47.6% vs 43.3% break-even at +$15, z +2.35) but not confirmed; nothing near 90% |

## Reproduce

```sh
TWELVEDATA_API_KEY=offline PYTHONPATH=. python audit/tools/h4_outcome_audit.py <market-data copy> 15m out.json
TWELVEDATA_API_KEY=offline PYTHONPATH=. python audit/tools/exec_sensitivity.py <market-data copy> 5m,15m,1h out.json
python audit/tools/forward_stats.py <forward-ledger checkout> 5e4630924d663fc5:6f3964ad97813cc9 --archive
```

The key only selects the stored Twelve Data series; network calls are disabled. **Without it the loader falls back
to GC futures:** this audit's first run did, and was discarded.
