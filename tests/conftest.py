"""Shared test setup.

ALERT_MODE: the default became "sixty" on 2026-11-06 (operator: "ALERTS WITH MORE THAN 60% SUCCESSFUL TRADES ONLY"), which
sends only the engine's 15m signals to the phone. The tests written before then check what the other streams send, so
they run in the previous default, "quality", unless they set the mode themselves; tests/test_alert_sixty.py covers the
new default (it deletes the variable).

CONFIRM_MIN_USD: C1 (operator directive 2026-11-15) makes every SIGNAL alert a SETUP that waits for a $10 confirming close
before an ENTRY ELIGIBLE alert. The tests written before then check the previous alert text, so they run with C1 off (0)
unless they set it themselves; tests/test_confirm_entry.py covers C1 as deployed (it deletes the variable: $10).
"""
import pytest


@pytest.fixture(autouse=True)
def _alert_mode_quality(monkeypatch):
    monkeypatch.setenv("ALERT_MODE", "quality")
    monkeypatch.setenv("CONFIRM_MIN_USD", "0")
