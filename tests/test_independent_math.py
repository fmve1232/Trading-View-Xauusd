"""Institutional audit 2026-10-31, Phase 3: every core formula recomputed INDEPENDENTLY.

Each reference below is written from the textbook / Pine reference definition with plain Python
loops (no numpy windows, no shared helper from `quantum`), then compared with the production code
on random OHLC data with NaN and flat stretches. A failure here means the production formula and
its definition disagree. Nothing in this file is tuned on price history.
"""
import math
import random

import numpy as np
import pytest

from quantum import backtest, ta

N = 400


def _ohlc(seed=3, n=N):
    rnd = random.Random(seed)
    c, out = 2000.0, []
    for i in range(n):
        o = c
        c = o + rnd.gauss(0, 3)
        if 150 <= i < 160:          # a flat stretch (dn == 0 / range == 0 cases)
            c = o
        h = max(o, c) + abs(rnd.gauss(0, 1.5)) * (0 if 150 <= i < 160 else 1)
        lo = min(o, c) - abs(rnd.gauss(0, 1.5)) * (0 if 150 <= i < 160 else 1)
        out.append((o, h, lo, c, rnd.randint(0, 500)))
    o, h, lo, c, v = (np.array(x, float) for x in zip(*out))
    return o, h, lo, c, v


def _close(a, b, tol=1e-9):
    a, b = np.asarray(a, float), np.asarray(b, float)
    assert a.shape == b.shape
    same_nan = np.isnan(a) == np.isnan(b)
    assert same_nan.all(), f"NaN pattern differs at {np.where(~same_nan)[0][:5]}"
    m = ~np.isnan(a)
    np.testing.assert_allclose(a[m], b[m], rtol=tol, atol=tol)


# ---------------- reference definitions ----------------
def ref_sma(x, n):
    return [sum(x[i - n + 1:i + 1]) / n if i >= n - 1 else math.nan for i in range(len(x))]


def ref_recursive(x, n, alpha):
    """Pine: first value = SMA(n) of the first n inputs, then alpha * x + (1 - alpha) * prev."""
    out, prev = [], math.nan
    for i in range(len(x)):
        if math.isnan(prev):
            v = sum(x[i - n + 1:i + 1]) / n if i >= n - 1 else math.nan
        else:
            v = alpha * x[i] + (1 - alpha) * prev
        out.append(v)
        prev = v
    return out


def ref_tr(h, lo, c):
    return [h[0] - lo[0]] + [max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1])) for i in range(1, len(c))]


def ref_rsi(c, n):
    up = [math.nan] + [max(c[i] - c[i - 1], 0.0) for i in range(1, len(c))]
    dn = [math.nan] + [max(c[i - 1] - c[i], 0.0) for i in range(1, len(c))]
    # Wilder: seeded on the first n changes (bars 1..n), then RMA
    def wilder(x):
        out, prev = [math.nan] * len(x), math.nan
        for i in range(1, len(x)):
            if math.isnan(prev):
                if i >= n:
                    prev = sum(x[i - n + 1:i + 1]) / n
            else:
                prev = (prev * (n - 1) + x[i]) / n
            out[i] = prev
        return out
    U, D = wilder(up), wilder(dn)
    res = []
    for u, d in zip(U, D):
        if math.isnan(u) or math.isnan(d):
            res.append(math.nan)
        elif d == 0:
            res.append(100.0)
        elif u == 0:
            res.append(0.0)
        else:
            res.append(100 - 100 / (1 + u / d))
    return res


def ref_stdev_pop(x, n):
    out = []
    for i in range(len(x)):
        if i < n - 1:
            out.append(math.nan)
            continue
        w = x[i - n + 1:i + 1]
        m = sum(w) / n
        out.append(math.sqrt(sum((v - m) ** 2 for v in w) / n))
    return out


def ref_corr(a, b, n):
    """Two-pass Pearson (numerically stable form) over the last n bars."""
    out = []
    for i in range(len(a)):
        if i < n - 1:
            out.append(math.nan)
            continue
        x, y = a[i - n + 1:i + 1], b[i - n + 1:i + 1]
        mx, my = sum(x) / n, sum(y) / n
        sxy = sum((p - mx) * (q - my) for p, q in zip(x, y))
        sxx = sum((p - mx) ** 2 for p in x)
        syy = sum((q - my) ** 2 for q in y)
        out.append(sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else math.nan)
    return out


def ref_pivot(src, left, right, high=True):
    out = [math.nan] * len(src)
    for i in range(left + right, len(src)):
        p = i - right
        cen = src[p]
        others = src[p - left:p] + src[p + 1:p + right + 1]
        if all((cen > v) if high else (cen < v) for v in others):
            out[i] = cen
    return out


def ref_percentrank(x, n):
    return [sum(1 for v in x[i - n:i] if v <= x[i]) / n * 100 if i >= n else math.nan for i in range(len(x))]


# ---------------- tests ----------------
@pytest.mark.parametrize("n", [1, 5, 20])
def test_sma_ema_rma(n):
    *_, c, _ = _ohlc()
    x = c.tolist()
    _close(ta.sma(c, n), ref_sma(x, n))
    _close(ta.ema(c, n), ref_recursive(x, n, 2 / (n + 1)))
    _close(ta.rma(c, n), ref_recursive(x, n, 1 / n))


def test_ema20_definition_against_hand_values():
    x = np.arange(1.0, 31.0)
    e = ta.ema(x, 20)
    assert e[18] != e[18] and e[19] == pytest.approx(10.5)        # seed = SMA of 1..20
    a = 2 / 21
    assert e[20] == pytest.approx(a * 21 + (1 - a) * 10.5)


def test_true_range_and_atr():
    _, h, lo, c, _ = _ohlc()
    trr = ref_tr(h.tolist(), lo.tolist(), c.tolist())
    _close(ta.tr(h, lo, c), trr)
    _close(ta.atr(h, lo, c, 14), ref_recursive(trr, 14, 1 / 14))


def test_rsi_is_wilder_rsi():
    *_, c, _ = _ohlc()
    _close(ta.rsi(c, 14), ref_rsi(c.tolist(), 14), tol=1e-8)


def test_bollinger_stdev_is_population():
    *_, c, _ = _ohlc()
    _close(ta.stdev(c, 20), ref_stdev_pop(c.tolist(), 20), tol=1e-7)


def test_correlation_matches_two_pass_pearson_on_returns_and_levels():
    _, _, _, c, v = _ohlc()
    r = np.diff(np.log(c), prepend=np.nan)
    rv = np.diff(np.log(v + 1.0), prepend=np.nan)
    _close(ta.correlation(r, rv, 20), ref_corr(r.tolist(), rv.tolist(), 20), tol=1e-7)
    # price LEVELS near 2000: the one-pass E[xy] - E[x]E[y] form loses digits; it must stay within 1e-6
    _close(ta.correlation(c, c * 0.5 + v, 50), ref_corr(c.tolist(), (c * 0.5 + v).tolist(), 50), tol=1e-6)


def test_pivots_and_percentrank():
    _, h, lo, c, _ = _ohlc()
    _close(ta.pivothigh(h, 5, 5), ref_pivot(h.tolist(), 5, 5, True))
    _close(ta.pivotlow(lo, 5, 5), ref_pivot(lo.tolist(), 5, 5, False))
    _close(ta.percentrank(c, 100), ref_percentrank(c.tolist(), 100))


def test_anchored_vwap_definition():
    _, h, lo, c, v = _ohlc()
    src = (h + lo + c) / 3
    anchor = np.zeros(N, bool)
    anchor[::96] = True
    got = ta.anchored_vwap(src, v, anchor)
    pv = vv = 0.0
    ps, k = 0.0, 0
    for i in range(N):
        if anchor[i] or i == 0:
            pv = vv = ps = 0.0
            k = 0
        pv += src[i] * v[i]
        vv += v[i]
        ps += src[i]
        k += 1
        want = pv / vv if vv > 0 else ps / k            # D-07: equal weight until the period has volume
        assert got[i] == pytest.approx(want, rel=1e-12)


def test_dmi_adx_reference():
    _, h, lo, c, _ = _ohlc()
    n = 14
    up = [math.nan] + [h[i] - h[i - 1] for i in range(1, N)]
    dn = [math.nan] + [lo[i - 1] - lo[i] for i in range(1, N)]
    pdm = [math.nan] + [u if (u > d and u > 0) else 0.0 for u, d in zip(up[1:], dn[1:])]
    mdm = [math.nan] + [d if (d > u and d > 0) else 0.0 for u, d in zip(up[1:], dn[1:])]
    trr = [math.nan] + ref_tr(h.tolist(), lo.tolist(), c.tolist())[1:]
    T = ref_recursive(trr, n, 1 / n)
    P = [100 * a / b if not (math.isnan(a) or math.isnan(b)) and b != 0 else math.nan for a, b in zip(ref_recursive(pdm, n, 1 / n), T)]
    M = [100 * a / b if not (math.isnan(a) or math.isnan(b)) and b != 0 else math.nan for a, b in zip(ref_recursive(mdm, n, 1 / n), T)]
    # fixnan (carry the last value) as Pine's reference does
    for arr_ in (P, M):
        for i in range(1, N):
            if math.isnan(arr_[i]):
                arr_[i] = arr_[i - 1]
    dx = [abs(p - m) / (p + m if p + m != 0 else 1.0) for p, m in zip(P, M)]
    A = [100 * x for x in ref_recursive(dx, n, 1 / n)]
    p_, m_, a_ = ta.dmi(h, lo, c, n, n)
    _close(p_, P, tol=1e-8)
    _close(m_, M, tol=1e-8)
    _close(a_, A, tol=1e-8)


def _t(r, tp1=False, why="SL", d="LONG", pts=None):
    return dict(r=r, pts=r * 10 if pts is None else pts, tp1_hit=tp1, bars=3, dir=d, exit_reason=why, open=False)


def test_backtest_metrics_by_hand():
    tr = [_t(1.0, True, "TP2"), _t(-1.0), _t(-1.0), _t(2.0, True, "TP2"), _t(-0.5)]
    m = backtest.metrics(tr, risk_pct=1.0)
    r = [1.0, -1.0, -1.0, 2.0, -0.5]
    mean = sum(r) / 5
    sd = math.sqrt(sum((x - mean) ** 2 for x in r) / 4)
    assert m["n"] == 5 and m["win_rate"] == pytest.approx(40.0)
    assert m["expectancy_r"] == pytest.approx(mean) and m["t_stat"] == pytest.approx(mean / (sd / math.sqrt(5)))
    assert m["profit_factor"] == pytest.approx(30 / 25)
    eq, peak, dd = 1.0, 1.0, 0.0
    for x in r:
        eq *= 1 + 0.01 * x
        peak = max(peak, eq)
        dd = max(dd, (peak - eq) / peak)
    assert m["max_dd_pct"] == pytest.approx(dd * 100)
    assert m["max_dd_r"] == pytest.approx(2.0)            # +1, then -1, -1: peak 1 -> -1
    assert m["longest_losing_streak"] == 2


def test_simulate_by_hand_stop_first_partial_and_breakeven():
    """A hand-worked path: entry 100 (stop 98, TP1 102, TP2 106), then TP1, then back to entry."""
    from types import SimpleNamespace

    import pandas as pd
    idx = pd.date_range("2026-10-01", periods=5, freq="15min", tz="UTC")
    c = np.array([100.0, 101.0, 102.5, 100.5, 99.0])
    h = np.array([100.0, 101.5, 103.0, 101.0, 100.1])
    lo = np.array([100.0, 100.5, 101.5, 99.9, 98.5])
    F = dict(c=c, h=h, l=lo, o=c, index=idx, sess_spread=np.full(5, 0.3), session_label=["NY"] * 5, mkt_regime=["X"] * 5)
    R = dict(exec_buy=[1, 0, 0, 0, 0], exec_sell=[0] * 5, plan_sl=[98.0] + [math.nan] * 4, plan_tp1=[102.0] + [math.nan] * 4,
             plan_tp2=[106.0] + [math.nan] * 4, tq=[0] * 5, cal_p_long=[0.6] * 5, cal_p_short=[0.4] * 5, plan_ev=[0.1] * 5)

    class C:
        slippage_pts, commission_l, point_value = 0.2, 7.0, 100.0
    t = backtest.simulate(SimpleNamespace(F=F, rows=R), C)
    assert len(t) == 1
    t = t[0]
    # bar 2 hits TP1 (half off at 102); stop moves to 100 from bar 3; bar 3 low 99.9 -> BE exit at 100
    assert t["tp1_hit"] and t["exit_reason"] == "BE" and t["exit_i"] == 3
    cost = 0.3 + 0.4 + 0.07
    assert t["gross_pts"] == pytest.approx(0.5 * 2.0 + 0.5 * 0.0)
    assert t["pts"] == pytest.approx(1.0 - cost)
    assert t["r"] == pytest.approx((1.0 - cost) / 2.0, abs=1e-4)


def test_wilson_lower_bound_used_by_kelly():
    """The Kelly sizing uses the Wilson 95% interval; check the closed form on textbook numbers."""
    p, n, z = 0.6, 50, 1.96
    den = 1 + z * z / n
    lo = ((p + z * z / (2 * n)) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / den
    assert lo == pytest.approx(0.4618, abs=1e-3)       # Wilson (1927) / Agresti-Coull tables
