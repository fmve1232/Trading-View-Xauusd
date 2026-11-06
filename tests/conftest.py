"""Shared test setup.

ALERT_MODE: the default became "sixty" on 2026-11-06 (operator: "ALERTS WITH MORE THAN 60% SUCCESSFUL TRADES ONLY"), which
sends only the engine's 15m signals to the phone. The tests written before then check what the other streams send, so
they run in the previous default, "quality", unless they set the mode themselves; tests/test_alert_sixty.py covers the
new default (it deletes the variable).
"""
import pytest


@pytest.fixture(autouse=True)
def _alert_mode_quality(monkeypatch):
    monkeypatch.setenv("ALERT_MODE", "quality")
