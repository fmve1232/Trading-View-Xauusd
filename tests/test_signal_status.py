"""Pine v76 port: the last H2 / H3 signal's age, outcome and LIVE / STALE (report.signal_status, display only)."""
import numpy as np

from quantum.report import signal_status


def F(h, l):
    return {"c": np.array(h, float), "h": np.array(h, float), "l": np.array(l, float)}


SHORT = {"dir": "SHORT", "sl": 110.0, "tp1": 95.0, "tp2": 90.0}
LONG = {"dir": "LONG", "sl": 90.0, "tp1": 105.0, "tp2": 110.0}


def test_outcomes_in_order():
    assert signal_status(F([100, 101, 102], [99, 99, 99]), 0, SHORT, True) | {} == {
        "bars": 2, "outcome": "open", "closed": False, "trend_ok": True, "stale": False, "why": [], "stale_bars": 24}
    assert signal_status(F([100, 111], [99, 99]), 0, SHORT, True)["outcome"] == "stopped"
    assert signal_status(F([100, 100, 100], [99, 94, 89]), 0, SHORT, True)["outcome"] == "TP2 hit"
    s = signal_status(F([100, 100, 112], [99, 94, 99]), 0, SHORT, True)
    assert s["outcome"] == "TP1 hit, then stop" and s["closed"] and s["stale"] and s["why"] == ["trade over"]
    assert signal_status(F([100, 106], [99, 99]), 0, LONG, True)["outcome"] == "TP1 hit"


def test_stop_counts_first_on_a_bar_that_touches_both():
    assert signal_status(F([100, 111], [99, 89]), 0, SHORT, True)["outcome"] == "stopped"
    assert signal_status(F([100, 111], [99, 89]), 0, LONG, True)["outcome"] == "stopped"


def test_stale_by_age_or_trend():
    n = 30
    s = signal_status(F([100] * n, [99] * n), 0, SHORT, True)
    assert s["stale"] and s["why"] == ["older than 24 bars"] and s["bars"] == n - 1
    s = signal_status(F([100, 100], [99, 99]), 0, SHORT, False)
    assert s["stale"] and s["why"] == ["trend no longer agrees"]
    assert not signal_status(F([100], [99]), 0, SHORT, True)["stale"]          # the signal bar itself: live
