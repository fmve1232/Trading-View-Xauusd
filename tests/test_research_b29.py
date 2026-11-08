"""B29 vectorised dynamic-exit engine (quantum/research/b29.py) against research/registrations/B29.json."""
import math

import numpy as np
import pandas as pd
import pytest

from quantum.research import b26, b29
from quantum.research import harness as H


def _bars(o, h, l, c, start="2026-11-02 08:00", gaps=None):
    t, cur = [], pd.Timestamp(start, tz="UTC")
    for i in range(len(c)):
        cur = cur + pd.Timedelta(seconds=(gaps or {}).get(i, 0))
        t.append(cur)
        cur = cur + pd.Timedelta(seconds=900)
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c}, index=pd.DatetimeIndex(t))


def _walk(n=900, seed=8):
    rng = H.seeded_rng(seed)
    c = 4000 + np.cumsum(rng.normal(0, 4, n))
    o = np.r_[4000.0, c[:-1]] + rng.normal(0, 0.3, n)
    return _bars(o, np.maximum(o, c) + np.abs(rng.normal(0, 1.5, n)), np.minimum(o, c) - np.abs(rng.normal(0, 1.5, n)), c,
                 gaps={400: 3 * 86400})


def ref_race(P, f, d, s, si, so, tp, sl, horizon):
    """A plain one-trade reference with B26's rules and TP != SL."""
    fill = P.o[f] + d * (s / 2 + si)
    TP, SL = fill + d * tp, fill - d * sl
    off = -d * s / 2
    for j in range(f, min(f + horizon, P.n)):
        oj, hj, lj = P.o[j] + off, P.h[j] + off, P.l[j] + off
        if (d > 0 and oj <= SL) or (d < 0 and oj >= SL):
            return "SL", d * (oj - fill) - so
        if (d > 0 and oj >= TP) or (d < 0 and oj <= TP):
            return "TP", tp
        ht = hj >= TP if d > 0 else lj <= TP
        hs = lj <= SL if d > 0 else hj >= SL
        if hs:
            return ("AMBIGUOUS" if ht else "SL"), -sl - so
        if ht:
            return "TP", tp
        if j == P.n - 1:
            return "OPEN", math.nan
        if P.closure_end[j]:
            return "CLOSURE", d * (P.c[j] + off - fill) - d * d * so
        if j == f + horizon - 1:
            return "TIMEOUT", d * (P.c[j] + off - fill) - d * d * so
    return "OPEN", math.nan


@pytest.mark.parametrize("tp,sl", [(15, 15), (5, 10), (20, 10), (30, 20), (3, 30)])
def test_the_vectorised_engine_matches_a_plain_race(tp, sl):
    P = b26.make_path(_walk(), 900)
    dec = np.arange(0, 850, 3)
    for d in (1, -1):
        lab = b29.label_block(P, dec, d, np.full(len(dec), 0.30), np.ones(len(dec)), "ENG", 192, fixed=((tp, sl),))[(tp, sl)]
        for x, i in enumerate(dec):
            out, net = ref_race(P, int(i) + 1, d, 0.30, 0.20, 0.20, tp, sl, 192)
            got = b29.OUT_NAMES[lab["worst"][x]]
            assert got == out, (i, d, got, out)
            if out != "OPEN":
                assert lab["net_w"][x] == pytest.approx(net - 0.07, abs=1e-3)


def test_symmetric_bracket_is_b26s_race():
    P = b26.make_path(_walk(seed=3), 900)
    dec = np.arange(0, 850, 5)
    lab = b29.label_block(P, dec, 1, np.full(len(dec), 0.30), np.ones(len(dec)), "ENG", 192, fixed=((15, 15),))[(15, 15)]
    for x, i in enumerate(dec):
        r = b26.race(P, int(i) + 1, 1, 0.30, 0.20, 0.20, 1.0, 192)
        assert b29.OUT_NAMES[lab["worst"][x]] == b26.OUTCOMES[r[0]]


def test_a_bar_reaching_both_levels_is_reported_both_ways():
    o = np.r_[4000.0, 4000.0, 4000.0, 4000.0]
    h = np.r_[4000.5, 4000.5, 4012.0, 4000.5]
    l = np.r_[3999.5, 3999.5, 3988.0, 3999.5]
    P = b26.make_path(_bars(o, h, l, o), 900)
    lab = b29.label_block(P, np.array([0]), 1, np.array([0.0]), np.array([1.0]), "GROSS", 192, fixed=((10, 10),))[(10, 10)]
    assert b29.OUT_NAMES[lab["worst"][0]] == "AMBIGUOUS" and b29.OUT_NAMES[lab["best"][0]] == "TP"
    assert lab["net_w"][0] == pytest.approx(-10.0) and lab["net_b"][0] == pytest.approx(10.0)


def test_a_gap_through_the_stop_fills_at_the_open():
    o = np.r_[4000.0, 4000.0, 3980.0, 3980.0]
    P = b26.make_path(_bars(o, o + 0.5, o - 0.5, o), 900)
    lab = b29.label_block(P, np.array([0]), 1, np.array([0.30]), np.array([1.0]), "ENG", 192, fixed=((10, 10),))[(10, 10)]
    assert b29.OUT_NAMES[lab["worst"][0]] == "SL" and lab["gap"][0]
    assert lab["net_w"][0] == pytest.approx((3980.0 - 0.15) - (4000.0 + 0.35) - 0.20 - 0.07)


def test_atr_brackets_use_each_entrys_own_atr():
    P = b26.make_path(_walk(seed=5), 900)
    dec = np.arange(20, 800, 7)
    atr = np.full(P.n, 4.0)
    lab = b29.label_block(P, dec, 1, np.full(len(dec), 0.30), np.ones(len(dec)), "ENG", 192, fixed=((10, 10),), atr=atr,
                          atr_grid=((2.5, 2.5),))
    a, f = lab[("ATR", 2.5, 2.5)], lab[(10, 10)]
    assert (a["worst"] == f["worst"]).all()                                           # 2.5 x ATR 4 = $10


def test_theory_matches_the_registered_formulas():
    p0, be = b29.theory(3, 30, 0.30, "ENG")
    assert p0 == pytest.approx((30 - 0.5) / 33) and be == pytest.approx((30 + 0.2 + 0.07) / (33 + 0.2))
    p0, be = b29.theory(15, 15, 0.30, "GROSS")
    assert p0 == pytest.approx(0.5) and be == pytest.approx(0.5)


def test_time_series_momentum_reads_only_completed_days():
    idx = pd.date_range("2026-01-05 00:00", periods=96 * 90, freq="900s", tz="UTC")
    rng = H.seeded_rng(2)
    m = pd.DataFrame({"close": 4000 + np.cumsum(rng.normal(0, 3, len(idx)))}, index=idx)
    full = b29.tsmom(m, 20)
    cut = 96 * 60 + 37
    part = b29.tsmom(m.iloc[:cut], 20)
    assert np.array_equal(np.isnan(full[:cut]), np.isnan(part)) and np.allclose(np.nan_to_num(full[:cut]), np.nan_to_num(part))


def test_closest_fixed_bracket_and_the_one_sided_test():
    assert b29.closest_fixed(9.6, 14.2) == (10, 15)
    x = np.r_[np.ones(50), np.zeros(50)] * 0.5
    assert b29.welch_greater(x + 0.3, x) < 0.05 and b29.welch_greater(x, x + 0.3) > 0.5
