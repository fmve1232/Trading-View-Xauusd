"""TA primitives against brute-force reference implementations of the Pine definitions."""

import numpy as np
import pytest

from quantum import ta

rng = np.random.default_rng(3)
X = 100 + np.cumsum(rng.normal(0, 1, 400))


def test_sma_and_nan_window():
    x = X.copy()
    s = ta.sma(x, 10)
    assert np.isnan(s[8]) and abs(s[9] - x[:10].mean()) < 1e-12
    x[50] = np.nan
    s = ta.sma(x, 10)
    assert np.isnan(s[50]) and np.isnan(s[59]) and not np.isnan(s[60])


def test_ema_is_sma_seeded():
    e = ta.ema(X, 20)
    a = 2 / 21
    ref = X[:20].mean()
    assert abs(e[19] - ref) < 1e-12
    for i in range(20, 60):
        ref = a * X[i] + (1 - a) * ref
    assert abs(e[59] - ref) < 1e-9


def test_rma_and_atr():
    h, l, c = X + 1, X - 1, X
    tr = ta.tr(h, l, c)
    assert tr[0] == 2.0          # first bar: high - low (handle_na=True)
    assert np.isnan(ta.tr(h, l, c, handle_na=False)[0])
    a = ta.atr(h, l, c, 14)
    ref = tr[:14].mean()
    for i in range(14, 40):
        ref = (tr[i] + 13 * ref) / 14
    assert abs(a[39] - ref) < 1e-9


def test_rsi_bounds_and_extremes():
    r = ta.rsi(X, 14)
    v = r[~np.isnan(r)]
    assert v.min() >= 0 and v.max() <= 100
    up = ta.rsi(np.arange(50, dtype=float), 14)
    assert up[-1] == 100.0


def test_stdev_population():
    s = ta.stdev(X, 20)
    assert abs(s[30] - np.std(X[11:31], ddof=0)) < 1e-12


def test_percentrank_previous_values_only():
    x = np.array([1, 2, 3, 4, 5, 3.0])
    pr = ta.percentrank(x, 5)
    # previous 5 values 1..5 ; current 3 -> values <= 3 among previous: 1,2,3 -> 60%
    assert pr[5] == 60.0 and np.isnan(pr[4])


def test_correlation_matches_numpy():
    y = X * 0.5 + rng.normal(0, 3, len(X))
    c = ta.correlation(X, y, 30)
    assert abs(c[100] - np.corrcoef(X[71:101], y[71:101])[0, 1]) < 1e-9


def test_pivots_reported_right_bars_later():
    h = np.array([1, 2, 5, 2, 1, 1, 1.0])
    ph = ta.pivothigh(h, 2, 2)
    assert ph[4] == 5 and np.isnan(ph[3]) and np.isnan(ph[2])
    l = -h
    assert ta.pivotlow(l, 2, 2)[4] == -5


def test_pivot_plateau_is_not_a_pivot():
    h = np.array([1, 2, 5, 5, 2, 1, 1.0])
    assert np.isnan(ta.pivothigh(h, 2, 2)).all()


def test_anchored_vwap_resets():
    src = np.array([10, 20, 30, 40.0])
    vol = np.array([1, 1, 1, 3.0])
    v = ta.anchored_vwap(src, vol, np.array([False, False, True, False]))
    assert v[1] == 15 and v[2] == 30 and v[3] == (30 + 120) / 4
    z = ta.anchored_vwap(src, np.array([0, 0, 2, 0.0]), np.array([False, False, False, False]))
    assert z[0] == 10 and z[1] == 15 and z[2] == 30 and z[3] == 30   # no volume yet -> equal-weight mean


@pytest.mark.parametrize("x,want", [(0.5, 1), (1.5, 2), (2.5, 3), (-2.5, -3), (-0.4, 0), (69.49, 69)])
def test_pine_round_half_away_from_zero(x, want):
    assert ta.pine_round(x) == want


def test_epoch_seconds_any_resolution():
    import pandas as pd
    idx = pd.DatetimeIndex(["2026-01-02 03:04:05"], tz="UTC")
    for unit in ("s", "ms", "us", "ns"):
        assert ta.epoch_s(idx.as_unit(unit))[0] == 1767323045
