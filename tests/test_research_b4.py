"""Phase B4 (quantum/research/b4.py): the entry-price hypotheses use only past bars and their mechanics are exact."""
import numpy as np
import pandas as pd

from quantum.research import b2, b4
from tests.test_research_b2 import _walk


def test_declared_grid():
    assert b4.TARGETS == {"T10": (10.0, 10.0), "T15": (15.0, 10.0), "T20": (20.0, 10.0)}
    assert b4.ROUND_LEVELS == (10.0, 50.0, 100.0) and b4.LIMIT_OFFSETS == (2.0, 5.0) and b4.LIMIT_BARS == 4


def test_round_cross_fires_once_per_level_and_respects_the_lookback():
    c = np.array([1795.0, 1799.0, 1801.0, 1802.0, 1798.0, 1801.0] + [1801.0] * 25 + [1799.0, 1802.0])
    s = b4.round_cross(c, 10.0)
    assert s[2] == 1                         # 1799 -> 1801 crosses 1800 up
    assert s[4] == 0 and s[5] == 0           # back and forth within 20 bars: not a fresh cross
    assert s[-2] == -1 and s[-1] == 0        # down through 1800 26 bars after the last cross: fresh; straight back up: not
    s2 = b4.round_cross(np.array([1805.0, 1795.0]), 10.0)
    assert s2[1] == -1
    s3 = b4.round_cross(np.array([1790.0, 1825.0]), 10.0)   # three levels at once: one signal
    assert s3.tolist() == [0.0, 1.0]


def test_round_reject_needs_a_touch_from_one_side_and_a_close_back():
    o = np.array([1798.0, 1802.0, 1798.0]); h = np.array([1800.2, 1803.0, 1799.5]); l = np.array([1797.0, 1799.9, 1797.0])
    c = np.array([1799.0, 1801.0, 1798.5])
    s = b4.round_reject(o, h, l, c, 10.0)
    assert s.tolist() == [-1.0, 1.0, 0.0]    # rejected at 1800 from below; from above; no touch


def test_session_open_momentum_uses_the_first_30_minutes_only():
    idx = pd.date_range("2021-03-03 06:00", periods=40, freq="15min", tz="UTC")   # London = UTC in early March
    c = np.full(40, 1700.0)
    i_open = list(idx).index(pd.Timestamp("2021-03-03 08:00", tz="UTC"))
    c[i_open - 1] = 1700.0
    c[i_open + 1] = 1703.0                   # 08:15 bar closes at 08:30 above the 07:45 close
    df = pd.DataFrame({"open": c, "high": c, "low": c, "close": c}, index=idx)
    s = b4.session_open(df, "Europe/London", 8, 0)
    assert np.flatnonzero(s).tolist() == [i_open + 1] and s[i_open + 1] == 1
    full = b4.session_open(_walk(3000), "America/New_York", 8, 30)
    part = b4.session_open(_walk(3000).iloc[:1700], "America/New_York", 8, 30)
    assert (full != 0).sum() > 5 and np.array_equal(part, full[:1700])


def test_limit_fill_price_and_window(monkeypatch):
    monkeypatch.setattr(b2, "HORIZON", 4)
    idx = pd.date_range("2021-03-01", periods=12, freq="15min", tz="UTC")
    o = np.array([100, 100, 99.5, 97.0, 99, 99, 99, 99, 99, 99, 99, 99], float)
    df = pd.DataFrame({"open": o, "high": o + 0.5, "low": o - 1.0, "close": o}, index=idx)
    P = b2.Paths(df)
    t0 = P.t[0] + 900                        # decision at the close of bar 0
    filled, jj, fill = b4.limit_fills(P, np.array([t0]), np.array([100.0]), np.array([1.0]), np.array([2.0]))
    assert filled[0] and jj[0] == 3 and fill[0] == 97.0     # bar 3 opens at 97, through the 98 limit: filled at the open
    filled, jj, fill = b4.limit_fills(P, np.array([t0]), np.array([100.0]), np.array([1.0]), np.array([1.5]))
    assert filled[0] and jj[0] == 2 and fill[0] == 98.5     # bar 2's low 98.5 touches the 98.5 limit
    filled, *_ = b4.limit_fills(P, np.array([t0]), np.array([100.0]), np.array([1.0]), np.array([5.0]))
    assert not filled[0]                                     # never reached within 4 bars


def test_fill_bar_bounds(monkeypatch):
    monkeypatch.setattr(b2, "HORIZON", 3)
    idx = pd.date_range("2021-03-01", periods=8, freq="15min", tz="UTC")
    # fill at 98 inside bar 1 whose high 108 may have printed BEFORE the fill; bar 2 then falls through the stop
    df = pd.DataFrame({"open": [100, 100, 97, 97, 97, 97, 97, 97.0], "high": [100, 108, 97.5, 97, 97, 97, 97, 97.0],
                       "low": [100, 98, 87, 97, 97, 97, 97, 97.0], "close": [100, 99, 88, 97, 97, 97, 97, 97.0]}, index=idx)
    P = b2.Paths(df)
    one = {"T10": (10.0, 10.0)}
    _, ev = b4.evaluate_fills(P, np.array([1]), np.array([98.0]), np.array([1.0]), one, np.array([1.0]), "conservative")
    assert ev[0]["out"][0] == 0                               # the 108 high does not count: the stop at 88 is hit in bar 2
    assert P.h[1] == 108 and P.o[1] == 100                    # the shared bars are untouched
    _, ev = b4.evaluate_fills(P, np.array([1]), np.array([98.0]), np.array([1.0]), one, np.array([1.0]), "optimistic")
    assert ev[0]["out"][0] == 0                               # from bar 2 on: stop too
