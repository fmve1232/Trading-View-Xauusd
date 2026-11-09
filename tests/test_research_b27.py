"""B27 framework (quantum/research/b27.py) against its registration (research/registrations/B27.json)."""
import math

import numpy as np
import pandas as pd
import pytest

from quantum.research import b26, b27
from quantum.research import harness as H

T0 = pd.Timestamp("2026-11-02 08:00", tz="UTC")


def _bars(rows, start=T0, step=900):
    idx = pd.date_range(start, periods=len(rows), freq=f"{step}s", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def _flat(n, px=4000.0):
    return [(px, px + 0.5, px - 0.5, px)] * n


def _walk(n=1600, seed=5):
    rng = H.seeded_rng(seed)
    c = 4000.0 + np.cumsum(rng.normal(0.0, 4.0, n))
    o = np.r_[4000.0, c[:-1]]
    hi = np.maximum(o, c) + np.abs(rng.normal(0, 1.5, n))
    lo = np.minimum(o, c) - np.abs(rng.normal(0, 1.5, n))
    idx = pd.date_range("2026-03-02", periods=n, freq="900s", tz="UTC")
    return pd.DataFrame({"open": o, "high": hi, "low": lo, "close": c, "volume": np.nan}, index=idx)


def test_added_features_never_change_when_later_bars_are_removed():
    m = _walk()
    rng = H.seeded_rng(9)
    up, dn = rng.random(len(m)) < 0.03, rng.random(len(m)) < 0.03
    tr = np.sign(rng.normal(size=len(m)))
    full = b27.extra_features(m, up, dn, tr)
    for cut in (700, 1111):
        part = b27.extra_features(m.iloc[:cut], up[:cut], dn[:cut], tr[:cut])
        a, b = full.iloc[:cut].to_numpy(float), part.to_numpy(float)
        assert np.array_equal(np.isnan(a), np.isnan(b)) and np.allclose(np.nan_to_num(a), np.nan_to_num(b))


def test_confirmation_needs_a_close_beyond_before_the_original_stop():
    rows = _flat(1) + [(4000, 4004, 3999, 4003.5), (4003.5, 4007, 4003, 4006.0), (4006, 4012, 4005, 4011.0)] + _flat(5, 4011.0)
    P = b26.make_path(_bars(rows), 900)
    r = b27.confirm_scan(P, 0, 1, 1.0, xs=(3, 5, 10, 15))
    assert r[3] == ("CONFIRMED", 1) and r[5] == ("CONFIRMED", 2) and r[10] == ("CONFIRMED", 3) and r[15][0] == "EXPIRED"
    rows = _flat(1) + [(4000, 4001, 3984.9, 3990.0)] + [(3990, 4020, 3989, 4016.0)]
    r = b27.confirm_scan(b26.make_path(_bars(rows), 900), 0, 1, 1.0, xs=(5,))
    assert r[5] == ("INVALIDATED", 1)                                                  # the original stop traded first


def test_a_market_fill_race_is_b26s_race():
    rng = H.seeded_rng(4)
    c = 4000 + np.cumsum(rng.normal(0, 4, 400))
    o = np.r_[4000.0, c[:-1]]
    df = _bars(list(zip(o, np.maximum(o, c) + 1, np.minimum(o, c) - 1, c, strict=True)))
    P = b26.make_path(df, 900)
    for f in (1, 50, 200):
        for d in (1, -1):
            a = b26.race(P, f, d, 0.3, 0.2, 0.2, 1.0, 192)
            fill = P.o[f] + d * (0.15 + 0.2)
            b = b27.race_fill(P, f, fill, d, 0.3, 0.2, 1.0, 192)
            assert b26.OUTCOMES[a[0]] == b[0] and a[3] == b[1] and (a[2] == pytest.approx(b[2]) or math.isnan(a[2]))


def test_stop_order_fills_on_the_way_through_and_its_fill_bar_only_counts_against_it():
    rows = _flat(1) + [(4000, 4010.5, 3999, 4010.0)] + [(4010, 4030, 4009, 4028.0)] + _flat(3, 4028.0)
    P = b26.make_path(_bars(rows), 900)
    j, fill = b27.stop_fill(P, 0, 4010.0, 1, 0.3, 0.2, 1.0)
    assert j == 1 and fill == pytest.approx(4010.2)                                    # ask high 4010.65 >= 4010
    oc, xt, *_ = b27.race_fill(P, j, fill, 1, 0.3, 0.2, 1.0, 192, fill_bar=j)
    assert oc == "TP" and xt == P.t[2] + 900                                           # the target is not credited on bar 1
    rows = _flat(1) + [(4000, 4010.5, 3990, 3995.0)] + _flat(3, 3995.0)                # fills, then falls through the new stop
    P = b26.make_path(_bars(rows), 900)
    j, fill = b27.stop_fill(P, 0, 4010.0, 1, 0.3, 0.2, 1.0)
    assert b27.race_fill(P, j, fill, 1, 0.3, 0.2, 1.0, 192, fill_bar=j)[0] == "SL"
    rows = _flat(1) + [(4000, 4001, 3984.0, 3990.0)] + [(3990, 4020, 3989, 4015.0)]   # cancelled by the original stop first
    assert b27.stop_fill(b26.make_path(_bars(rows), 900), 0, 4010.0, 1, 0.3, 0.2, 1.0)[0] is None


def test_limit_fills_at_the_level_or_the_better_open():
    rows = _flat(1) + [(4000, 4001, 3994.0, 3995.0)] + _flat(3, 3995.0)
    P = b26.make_path(_bars(rows), 900)
    assert b27.limit_fill(P, 1, 3995.0, 1, 0.3) == (1, 3995.0)                         # ask low 3994.15 <= 3995
    rows = _flat(1) + [(3990, 3991, 3989.0, 3990.0)] + _flat(3, 3990.0)
    P = b26.make_path(_bars(rows), 900)
    j, px = b27.limit_fill(P, 1, 3995.0, 1, 0.3)
    assert j == 1 and px == pytest.approx(3990.15)                                     # gapped through: the ask at the open
    assert b27.limit_fill(b26.make_path(_bars(_flat(12)), 900), 1, 3990.0, 1, 0.3)[0] is None


def test_calibration_split_is_by_time_even_when_rows_are_not_time_ordered():
    t = np.r_[np.arange(0, 100) * 86400, np.arange(0, 100) * 86400]                  # BUY block then SELL block
    ex = t + 3600
    usable = np.ones(200, bool)
    fit_m, cal_m = b27.split_fit_cal(t, ex, usable)
    assert cal_m.sum() == 2 * 20 or cal_m.sum() == 2 * 21
    assert t[fit_m].max() < t[cal_m].min() and (ex[fit_m] < t[cal_m].min() - 86400 + 1).all()
    assert fit_m[:100].sum() == fit_m[100:].sum()                                      # both directions in both parts


def test_series_never_overlap_and_the_matched_baseline_is_post_stratified():
    dec = np.array([0, 1, 2, 5, 6, 9])
    ex = np.array([3, 4, 5, 8, 7, 12])
    out = np.array(["TP", "SL", "TP", "SL", "TP", "OPEN"])
    assert b27.seq_rows(dec, ex, out).tolist() == [0, 3]
    rates = {(1, "LONDON", "2020-05"): 0.40, (1, "NY", "2020-05"): 0.60}
    assert b27.matched(rates, np.array([1, 1, 1]), np.array(["LONDON", "LONDON", "NY"]), np.array(["2020-05"] * 3)) == pytest.approx(
        (0.4 + 0.4 + 0.6) / 3)


def test_multiple_testing_helpers():
    assert b27.bh([0.001, 0.02, 0.04, 0.5]) == [True, True, False, False]
    assert b27.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    pts = [{"id": "a", "r": 0.6, "per_week": 1, "exp_oz": 1.0, "dd": 10}, {"id": "b", "r": 0.5, "per_week": 1, "exp_oz": 0.5, "dd": 20},
           {"id": "c", "r": 0.5, "per_week": 9, "exp_oz": 0.1, "dd": 30}]
    assert b27.pareto(pts) == ["a", "c"]


def test_selection_rules_need_significance_size_and_the_matched_rate():
    def cand(k, n, b, be=0.506, e=0.1):
        lo, hi = H.wilson(k, n)
        return {"id": f"{k}/{n}", "stats": {"n_decided": n, "ci95": [lo, hi], "matched_random": b, "break_even": be, "break_even_decided": be, "exp_oz": e,
                                            "p_vs_random": b27.binom_p(k, n, b)}}
    cs = [cand(200, 330, 0.48), cand(60, 100, 0.48), cand(170, 330, 0.48), cand(330, 600, 0.48, e=-0.1)]
    b27.flag(cs)
    assert [c["informative"] for c in cs] == [True, False, False, True]               # 100 trades is too few; 51.5% is not enough
    assert [c["tradeable"] for c in cs] == [True, False, False, False]                 # negative expectancy is not tradeable


def test_break_even_decided_is_the_decided_rate_of_zero_expectancy():
    """Phase C audit: break_even (TP share of all trades) is too low as the comparator of the decided rate when timeouts /
    closures are common; break_even_decided is exact: r > break_even_decided iff the series' expectancy > 0."""
    W, L, N = 14.4, -15.8, -2.0
    out = np.array(["TP"] * 40 + ["SL"] * 50 + ["CLOSURE"] * 10)
    net = np.r_[np.full(40, W), np.full(50, L), np.full(10, N)]
    assert b27.break_even_decided(out, net) == pytest.approx((-L - (10 / 90) * N) / (W - L))
    st = b27.stats_of(out, net, np.full(100, 60.0), None, np.ones(100, int), np.array(["NY"] * 100), np.array(["2021-01"] * 100),
                      np.array(["2021-01-04"] * 100), {}, 1.0)
    assert st["break_even"] < st["break_even_decided"] - 0.04          # the old field is about 4.7 points too low here
    for k in range(1, 90):
        o = np.array(["TP"] * k + ["SL"] * (90 - k) + ["TIMEOUT"] * 10)
        x = np.r_[np.full(k, W), np.full(90 - k, L), np.full(10, N)]
        assert (k / 90 > b27.break_even_decided(o, x)) == (x.mean() > 0)
    assert math.isnan(b27.break_even_decided(np.array(["TP", "CLOSURE"]), np.array([1.0, -1.0])))


def test_top_q_selection_selects_about_q_on_raw_scores():
    """Phase C audit: a quantile threshold of isotonic-calibrated probabilities admits a whole step (share >> q); on the
    raw score (the same order, no ties) the training-window quantile selects about q."""
    rng = np.random.default_rng(3)
    n = 20000
    d = np.where(np.arange(n) % 2 == 0, 1, -1)
    raw = rng.uniform(0, 1, n)
    y = (rng.uniform(0, 1, n) < 0.45 + 0.02 * raw).astype(int)           # almost no information: isotonic collapses to few steps
    cal, te = np.arange(n) < n // 2, np.arange(n) >= n // 2
    old = b27.SELECT_ON
    try:
        shares = {}
        for mode in ("calibrated", "raw"):
            b27.SELECT_ON = mode
            thr = b27.thresholds(raw[cal], y[cal], d[cal])
            sc = raw[te] if mode == "raw" else b27.isotonic(raw[cal], y[cal], raw[te])
            shares[mode] = float((sc[d[te] == -1] >= thr[(-1, 0.01)]).mean())
        assert shares["raw"] == pytest.approx(0.01, abs=0.005)
        assert shares["calibrated"] > 0.05                               # the defect the fix removes
        L = pd.DataFrame({"fill_utc": np.arange(n), "d": d})
        wf = {"res": {"M": {"p": np.where(te, b27.isotonic(raw[cal], y[cal], raw), np.nan), "raw": np.where(te, raw, np.nan),
                            "thr": {(-1, 0.01): [(n // 2, b27.thresholds(raw[cal], y[cal], d[cal])[(-1, 0.01)])]}}}}
        b27.SELECT_ON = "raw"
        rows = b27.wf_selections(L, wf, "M")[(-1, 0.01)]
        assert len(rows) / (te & (d == -1)).sum() == pytest.approx(0.01, abs=0.005)
    finally:
        b27.SELECT_ON = old
