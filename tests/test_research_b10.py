"""Phase B10 (quantum/research/b10.py, research/registrations/B10.json): the gate-release masks, the +13 / -13 first
passage (scaled, tie rule), the regime-filtered liquidity events and Holm, on synthetic inputs."""
import json

import numpy as np
import pandas as pd

from quantum.research import b10 as B


def test_weekly_release_starts_on_a_close_above_and_ends_on_the_opposite_close_or_the_cap():
    c = np.array([99, 101, 102, 100, 97, 103, 104, 105, 106, 107], float)
    up, dn = np.full(10, 100.0), np.full(10, 98.0)
    m = B.release_mask(c, up, dn, max_bars=3)
    assert m.tolist() == [False, True, True, True, False, True, True, True, True, False]  # off below 98, cap 3 bars
    assert not B.release_mask(c, np.full(10, np.nan), dn, 3).any()                       # no level, no release


def test_daily_release_lasts_the_rest_of_the_day_and_the_next():
    c = np.array([99, 101, 100, 100, 100, 100], float)
    day = np.array(["d1", "d1", "d1", "d2", "d2", "d3"])
    m = B.release_mask(c, np.full(6, 100.0), np.full(6, 90.0), None, day)
    assert m.tolist() == [False, True, True, True, True, False]


def _path(rows, t0="2020-06-01 00:00"):
    idx = pd.date_range(t0, periods=len(rows), freq="15min", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def test_first_passage_is_scaled_and_a_both_bar_is_a_loss_unless_it_opened_beyond():
    flat = (2000, 2000.5, 1999.5, 2000)
    tp = 13 * 2000 / 4000                                       # $6.50 at a $2,000 price
    rows = [flat] * 5 + [(2000, 2000 + tp + 0.1, 1999, 2006)] + [flat] * 100
    p = _path(rows)
    t0 = int(p.index[0].timestamp())
    o = B.outcomes(p, np.array([t0]), np.array([2000.0]), np.array([1]), np.array([0.8]))
    assert o["win"][0] and not o["loss"][0] and o["net"][0] == (13 - 0.8) * 0.5
    both = _path([flat, (2000, 2007, 1993, 2000)] + [flat] * 100)
    assert B.outcomes(both, np.array([t0]), np.array([2000.0]), np.array([1]), np.array([0.8]))["loss"][0]
    gap = _path([flat, (2007, 2008, 1993, 2000)] + [flat] * 100)
    assert B.outcomes(gap, np.array([t0]), np.array([2000.0]), np.array([1]), np.array([0.8]))["win"][0]
    short = B.outcomes(_path([flat] * 20), np.array([t0]), np.array([2000.0]), np.array([1]), np.array([0.8]))
    assert not short["ok"][0]                                   # the 96-bar path is not complete: not counted


def test_holm_and_the_registration_match():
    assert B.holm({"a": 0.01, "b": 0.02, "c": 0.04}) == {"a": True, "b": True, "c": True}
    assert B.holm({"a": 0.01, "b": 0.03, "c": 0.04}) == {"a": True, "b": False, "c": False}
    with open("research/registrations/B10.json") as f:
        reg = json.load(f)
    assert reg["approved_by_operator"] and reg["partitions"] == ["development"]
    assert (B.TP, B.SL, B.PATH_BARS, B.MIN_N) == (13.0, 13.0, 96, 30) and B.RELEASE_BARS == {"15m": 480, "1h": 120}
    assert B.RANGE_REGIMES == ("RANGE", "COMPRESS") and B.TREND_REGIMES == ("STRONG TR", "EXPANSION")
