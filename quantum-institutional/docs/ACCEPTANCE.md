# Acceptance criteria

Master prompt §86. **Nothing is ticked that was not executed.** An unticked box
is the honest state, not an oversight.

## §86 final acceptance

- [ ] Historical data pipeline works
- [ ] Chunk processing works — *planner and resume built and tested; no pipeline yet*
- [ ] Data validation works — *checks built and tested on synthetic bars; never run at scale*
- [ ] Quantum 5.0 parity established
- [ ] Formula registry complete
- [ ] SMC engine validated
- [ ] Statistical engine validated
- [ ] Probability engine validated
- [ ] Calibration validated
- [ ] Transaction costs implemented
- [ ] Backtest engine validated
- [ ] Walk-forward validation works
- [ ] ML pipeline validated
- [ ] Macro pipeline works
- [ ] News pipeline works
- [ ] Live market pipeline works
- [ ] Data freshness monitoring works — *budgets defined; no feed to measure*
- [ ] Risk engine validated
- [ ] API works — *3 of 17 endpoints real; 14 correctly return 503*
- [ ] Database works — *schema written; never applied to a live database*
- [ ] Realtime works
- [ ] Dashboard works
- [ ] Traceability works — *version stamping built; `/trace` not implemented*
- [ ] GitHub CI works — *workflow written; first run happens on first push*
- [ ] Regression tests work — *edge-case suite green; no golden dataset yet*
- [ ] Paper trading works
- [ ] Security review passes

**0 of 27 complete.** Several have real work behind them, noted in italics.
None meets its criterion.

## Phase 0 criteria — met

- [x] Repository structure per §55
- [x] Quantum 5.0 vendored read-only, hash-verified, CI-enforced
- [x] Pine semantics layer, with all four divergences demonstrated from both sides
- [x] 72-case edge harness ported; 2 stale cases recorded as F-A18, not hidden
- [x] Typed contracts with UTC enforced at construction
- [x] Point-in-time access with a raising lookahead tripwire
- [x] Deterministic aggregation that refuses partial bars by default
- [x] Provider ABCs with no implementations and no stub data
- [x] Execution mode defaults to PAPER; an unrecognised value raises
- [x] API declares every §46 route; the unimplemented ones return `503 DATA_UNAVAILABLE`
- [x] Database schema with version stamping on every analytical table
- [x] 212 tests passing, 2 strict xfail
- [x] The §87 planning set

## Standing rules

1. A box is ticked only after the check has been **run** and its output recorded.
2. `NOT RUN` is a permitted and preferred verdict.
3. A phase gate failing is information, not an obstacle to route around.
