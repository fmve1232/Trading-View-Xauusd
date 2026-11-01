"""Phase B2 (quantum/research/b2.py): setups use only past bars, fills and one-position bookkeeping are exact."""
import numpy as np
import pandas as pd
import pytest

from quantum.research import b2


def _walk(n=3000, seed=5):
    g = np.random.default_rng(seed)
    idx = pd.date_range("2021-03-01 00:00", periods=n * 2, freq="15min", tz="UTC")
    idx = idx[idx.dayofweek < 5][:n]
    c = 1800 + np.cumsum(g.normal(0, 1.0, n))
    o = np.r_[1800.0, c[:-1]]
    h = np.maximum(o, c) + np.abs(g.normal(0, 0.7, n))
    l = np.minimum(o, c) - np.abs(g.normal(0, 0.7, n))
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 0.0}, index=idx)


def test_every_declared_setup_fires_and_uses_only_past_bars():
    df = _walk()
    full = b2.signals(df)
    assert tuple(full) == b2.SETUPS
    for name, s in full.items():
        assert set(np.unique(s)) <= {-1.0, 0.0, 1.0}
        assert (s != 0).sum() >= 3, name             # ~6 weeks of bars: weekly sweeps are few
    for k in (1200, 2100):
        part = b2.signals(df.iloc[:k])
        for name in b2.SETUPS:
            assert np.array_equal(part[name], full[name][:k]), (name, k)


def test_prior_period_levels_and_one_sweep_per_level_per_period():
    h = np.array([10, 12, 11, 13, 12.5, 14, 10.5], float)
    l = np.array([9, 10, 8, 11, 10, 12, 7], float)
    key = np.array(["d1", "d1", "d1", "d2", "d2", "d2", "d3"])
    ph, pl, codes = b2._prior_period_hl(h, l, key)
    assert np.isnan(ph[0]) and ph[3] == 12 and pl[3] == 8 and ph[6] == 14 and pl[6] == 10
    c = np.array([9.5, 11, 9, 11.5, 11.8, 11.9, 10.2])
    s = b2._sweep(h, l, c, ph, pl, codes)
    # bar 3 wicks above 12 and closes back below: SHORT; bar 5 does it again on the same day: not repeated
    assert s.tolist()[3] == -1 and s[5] == 0
    assert s[6] == 1          # day 3 wicks below 10 (day 2's low) and closes back above


def test_structure_breaks_carry_the_previous_break_direction():
    # pivot highs (3 / 3): 109 at bar 3 (known at bar 6), 111 at 9 (known at 12), 109 at 16 (known at 19)
    # pivot lows: 99 at bar 6 (known at 9), 95 at bar 13 (known at 16)
    h = np.array([100, 101, 102, 109, 102, 101, 100, 103, 105, 111, 110, 108, 106, 104, 106, 108, 109, 105, 103, 101, 99, 97, 95, 93], float)
    l = np.array([99, 100, 101, 108, 101, 100, 99, 102, 104, 109, 108, 106, 104, 95, 104, 106, 107, 103, 101, 99, 97, 94, 92, 90], float)
    c = (h + l) / 2
    c[9], c[21] = 110.5, 94.5
    brk, prev = b2._structure(h, l, c)
    assert np.flatnonzero(brk).tolist() == [9, 21]
    assert (brk[9], prev[9]) == (1, 0)              # the first break: no previous one (neither BOS nor CHOCH)
    assert (brk[21], prev[21]) == (-1, 1)           # down after up: a CHOCH
    h2, c2 = h.copy(), c.copy()
    h2[8], c2[8] = 110.0, 109.5                     # a close above 109 one bar earlier breaks the bar-3 pivot at bar 8
    assert np.flatnonzero(b2._structure(h2, l, c2)[0]).tolist()[0] == 8


@pytest.fixture
def short_horizon(monkeypatch):
    monkeypatch.setattr(b2, "HORIZON", 4)


def _paths(o, h, l, c):
    idx = pd.date_range("2021-03-01", periods=len(c), freq="15min", tz="UTC")
    return b2.Paths(pd.DataFrame({"open": o, "high": h, "low": l, "close": c}, index=idx))


def test_fills_level_gap_tie_and_open(short_horizon):
    a, b = np.array([2.0]), np.array([10.0])
    one = lambda P: P.evaluate(np.array([0]), np.array([100.0]), np.array([1.0]), [(a, b)])[0]
    r = one(_paths([100, 101, 101, 101], [102.5, 101, 101, 101], [99, 100, 100, 100], [101] * 4))
    assert (r["out"][0], r["pnl"][0], r["exit"][0]) == (1, 2.0, 0)                 # target at the level
    r = one(_paths([103, 101, 101, 101], [104, 101, 101, 101], [99, 100, 100, 100], [101] * 4))
    assert (r["out"][0], r["pnl"][0]) == (1, 3.0)                                  # opened beyond: fill at the open
    r = one(_paths([100, 88, 88, 88], [101, 89, 89, 89], [99, 86, 86, 86], [88] * 4))
    assert (r["out"][0], r["pnl"][0], r["exit"][0]) == (0, -12.0, 1)               # gapped through the stop: the open
    r = one(_paths([100, 100, 100, 100], [103, 100, 100, 100], [89, 100, 100, 100], [100] * 4))
    assert (r["out"][0], r["pnl"][0]) == (0, -10.0)                                # both on one bar: loss at the stop
    r = one(_paths([100] * 4, [101] * 4, [99] * 4, [100, 100, 100, 100.7]))
    assert r["out"][0] == -1 and abs(r["pnl"][0] - 0.7) < 1e-9 and r["exit"][0] == 3   # open: the horizon close


def test_locate_drops_paths_outside_the_window_or_across_a_hole(short_horizon):
    P = _paths([100] * 10, [101] * 10, [99] * 10, [100] * 10)
    t = P.t
    _, ok = P.locate(np.array([t[0] - 900, t[0], t[6], t[9] + 900]))
    assert ok.tolist() == [False, True, True, False]


def test_one_position_waits_for_the_exit():
    keep = b2.one_position(np.array([0, 10, 20, 30, 31]), np.array([25, 15, 40, 35, 50]))
    assert keep.tolist() == [0, 3]
