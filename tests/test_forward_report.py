"""audit/tools/forward_report.py: the race, the metrics and the cost sensitivity, on hand-made trades and bars."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "audit", "tools"))
import forward_report as F


def _bars(rows, t0="2026-11-16 00:00"):
    idx = pd.date_range(t0, periods=len(rows), freq="5min", tz="UTC", unit="us")    # pandas 3 resolution, as stored
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def test_seconds_do_not_depend_on_the_index_resolution():
    a = _bars([(1, 1, 1, 1)] * 2)
    b = a.copy()
    b.index = b.index.as_unit("ns")
    assert list(F.secs(a.index)) == list(F.secs(b.index)) == [1794787200, 1794787500]


def test_race_first_touch_ambiguous_bar_counts_as_the_stop_and_gaps_fill_at_the_level():
    rows = [(100, 100.5, 99.5, 100), (100, 101, 99.8, 100.5), (100.5, 103, 98, 101), (101, 106, 100.9, 105)]
    b = _bars(rows)
    t, o, h, l = F.secs(b.index), b["open"].to_numpy(), b["high"].to_numpy(), b["low"].to_numpy()
    assert F.race(t, o, h, l, 1, 1, 100, 98.5, 102) == "SL"        # bar 2 touches both: the stop
    assert F.race(t, o, h, l, 3, 1, 100, 98.5, 102) == "TP"        # bar 3 trades through the target only
    assert F.race(t, o, h, l, 3, -1, 100, 101.5, 90) == "SL"       # short: bar 3 trades above the stop
    assert F.race(t, o, h, l, 1, 1, 100, 90, 200) is None          # neither within the data


def _trade(r, pts, day, reason="SL", tp1=False, entry=100.0, sl=90.0, cost=0.77):
    return {"r": r, "pts": pts, "gross_pts": pts + cost, "cost_pts": cost, "entry": entry, "sl": sl, "tp1": entry + 10,
            "tp2": entry + 20, "dir": "LONG", "exit_reason": reason, "tp1_hit": tp1,
            "entry_time": f"{day}T10:00:00+00:00", "exit_time": f"{day}T10:30:00+00:00"}


def test_metrics_by_hand():
    tr = [_trade(1.0, 10, "2026-11-16", "TP2", True), _trade(-1.0, -10, "2026-11-16"), _trade(-1.0, -10, "2026-11-17"),
          _trade(-0.5, -5, "2026-11-18", "FLIP"), _trade(0.5, 5, "2026-11-19", "BE", True), _trade(2.0, 20, "2026-11-20", "TP2", True)]
    m = F.metrics(tr, np.random.default_rng(1))
    assert (m["trades"], m["wins"], m["losses"]) == (6, 3, 3)
    assert m["profit_factor"] == round(3.5 / 2.5, 3) and m["sum_r"] == 1.0
    assert m["max_drawdown_r"] == 2.5 and m["longest_losing_streak"] == 3
    assert m["avg_win_r"] == round(3.5 / 3, 4) and m["avg_loss_r"] == round(-2.5 / 3, 4)
    assert m["tp1_reached"] == 3 and m["stop_exits"] == 2 and m["trading_days"] == 5
    assert m["mean_r_boot95_days"][0] is not None and m["avg_hold_min"] == 30.0
    # a wider spread costs (spread - 0.30) / stop distance in R, nothing else changes
    assert m["mean_r_at_spread"]["spread_0.80"] == round(1.0 / 6 - 0.5 / 10, 4)


def test_day_clustering_widens_the_interval_when_a_day_carries_the_result():
    rng = np.random.default_rng(3)
    r = np.array([1.0] * 20 + [-0.2] * 20)
    days = ["d0"] * 20 + [f"d{i}" for i in range(1, 21)]
    lo_t, hi_t = F.boot_mean(r, rng)
    lo_d, hi_d = F.boot_day(r, days, rng)
    assert hi_d - lo_d > hi_t - lo_t
