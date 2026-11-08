"""B28 new trigger families (quantum/research/b28.py) against research/registrations/B28.json."""
import numpy as np
import pandas as pd
import pytest

from quantum.research import b28
from quantum.research import harness as H


def _walk(n=1500, seed=11, start="2026-03-02"):
    rng = H.seeded_rng(seed)
    c = 4000.0 + np.cumsum(rng.normal(0.0, 4.0, n))
    o = np.r_[4000.0, c[:-1]]
    hi = np.maximum(o, c) + np.abs(rng.normal(0, 1.5, n))
    lo = np.minimum(o, c) - np.abs(rng.normal(0, 1.5, n))
    idx = pd.date_range(start, periods=n, freq="900s", tz="UTC")
    return pd.DataFrame({"open": o, "high": hi, "low": lo, "close": c, "volume": np.nan}, index=idx)


def _F(m, seed=2):
    rng = H.seeded_rng(seed)
    n = len(m)
    pick = lambda p: np.where(rng.random(n) < p, np.where(rng.random(n) < 0.5, 1.0, -1.0), 0.0)
    return pd.DataFrame({"sg_flip": pick(0.03), "ev_disp": pick(0.03), "sg_sweep": pick(0.02), "ev_pdsweep": pick(0.01),
                         "ev_failbo": pick(0.02)}, index=m.index)


def test_new_events_never_change_when_later_bars_are_removed():
    m = _walk()
    F = _F(m)
    full = b28.new_events(m, F)
    for cut in (600, 1201):
        part = b28.new_events(m.iloc[:cut], F.iloc[:cut])
        a, b = full.iloc[:cut].to_numpy(float), part.to_numpy(float)
        assert np.array_equal(np.isnan(a), np.isnan(b)) and np.allclose(np.nan_to_num(a), np.nan_to_num(b))


def test_supertrend_flips_once_on_a_rise_then_a_fall():
    c = np.r_[np.linspace(4000, 4100, 200), np.linspace(4100, 3950, 200)]
    h, l = c + 1.0, c - 1.0
    tr, line = b28.supertrend(h, l, c)
    flips = np.flatnonzero(np.diff(tr[tr != 0]) != 0)
    assert len(flips) == 1 and tr[150] == 1 and tr[-1] == -1
    assert (line[tr > 0][-50:] < c[tr > 0][-50:]).all()                                # the line sits under price in an up-trend


def test_london_opening_range_breakout_fires_once_inside_its_window():
    idx = pd.date_range("2026-11-03 07:00", periods=24, freq="900s", tz="UTC")          # London = UTC in November
    c = np.full(24, 4000.0)
    h, l = c + 1.0, c - 1.0
    h[4], l[4], h[5], l[5] = 4005.0, 3995.0, 4004.0, 3996.0                            # 08:00 and 08:15: the range
    c[6], c[7], c[9] = 4003.0, 4006.0, 4008.0                                          # 08:30 inside, 08:45 beyond, then again
    ev, lv = b28._orb(idx, h, l, c, "Europe/London", (8, 0), (11, 0))
    assert np.flatnonzero(ev).tolist() == [7] and ev[7] == 1 and lv[7] == 4005.0
    c2 = c.copy()
    c2[7] = c2[9] = 4000.0
    c2[17] = 4010.0                                                                    # 11:15: outside the window
    assert not b28._orb(idx, h, l, c2, "Europe/London", (8, 0), (11, 0))[0].any()


def test_engulfing_needs_the_level_and_the_body():
    n = 40
    idx = pd.date_range("2026-03-03 10:00", periods=n, freq="900s", tz="UTC")
    o = np.full(n, 4000.0)
    c = o + np.where(np.arange(n) % 2 == 0, 0.6, -0.6)
    h, l = np.maximum(o, c) + 0.5, np.minimum(o, c) - 0.5
    o[30], c[30], h[30], l[30] = 4000.0, 3997.0, 4000.5, 3996.5                        # down bar
    o[31], c[31], h[31], l[31] = 3996.8, 4001.5, 4002.0, 3996.4                        # engulfs it, low near the 20-bar low
    m = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": np.nan}, index=idx)
    F = pd.DataFrame(0.0, index=idx, columns=["sg_flip", "ev_disp", "sg_sweep", "ev_pdsweep", "ev_failbo"])
    ev = b28.new_events(m, F)
    assert ev["ev_ENGULF_LEVEL"].iloc[31] == 1 and ev["lv_ENGULF_LEVEL"].iloc[31] == (3996.8 + 4001.5) / 2


def test_sweep_must_come_before_the_displacement():
    m = _walk(200)
    F = pd.DataFrame(0.0, index=m.index, columns=["sg_flip", "ev_disp", "sg_sweep", "ev_pdsweep", "ev_failbo"])
    F.iloc[100, F.columns.get_loc("sg_sweep")] = 1.0
    F.iloc[102, F.columns.get_loc("ev_disp")] = 1.0                                     # 2 bars after the sweep
    F.iloc[150, F.columns.get_loc("ev_disp")] = 1.0                                     # no sweep before it
    F.iloc[160, F.columns.get_loc("ev_disp")] = -1.0
    F.iloc[158, F.columns.get_loc("ev_failbo")] = 1.0                                   # a sweep in the other direction
    ev = b28.new_events(m, F)["ev_SWEEP_DISPLACEMENT"].to_numpy()
    assert np.flatnonzero(ev).tolist() == [102]


def test_direction_neutral_rate_is_the_mean_of_buy_and_sell():
    rates = {(1, "LONDON", "2020-05"): 0.40, (-1, "LONDON", "2020-05"): 0.56}
    assert b28.neutral_rates(rates)[("LONDON", "2020-05")] == pytest.approx(0.48)
