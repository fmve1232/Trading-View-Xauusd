# Parity fixtures

**Empty.** Phase 6.

This directory will hold TradingView-exported series from the Master, on the
build hashed in `reference/quantum_5_0/MANIFEST.sha256`, collected per
`Trading-View-Xauusd/audit/RUNBOOK.md`.

Two rules:

1. **Export the input OHLCV too**, not just the engine outputs. Parity against
   a separately sourced XAUUSD history measures the feed difference, not the
   engine (D-08).
2. **Nothing synthetic goes in here.** Test fixtures in `tests/conftest.py`
   exercise code paths; they do not represent XAUUSD and must never be used as a
   parity baseline.
