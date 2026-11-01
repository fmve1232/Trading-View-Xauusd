"""Phase B5 exploratory order-flow proxy (quantum/research/b5_flow_proxy.py): bulk volume classification, the hourly
imbalance and the trailing-percentile signal use only past bars; contract rolls are excluded."""
import numpy as np

from quantum.research import b5_flow_proxy as B


def _series(n=3000, seed=4):
    g = np.random.default_rng(seed)
    c = 3000 + np.cumsum(g.normal(0, 1.0, n))
    v = g.integers(100, 1000, n).astype(float)
    return c, v


def test_bvc_sign_follows_the_price_move_and_is_bounded():
    c, v = _series()
    imb = B.bvc_imbalance(c, v)
    ok = np.isfinite(imb)
    assert ok.sum() > 2500 and np.all(np.abs(imb[ok]) <= 1.0)
    up = c.copy()
    up[-12:] = up[-13] + np.arange(1, 13) * 2.0          # a steady rise over the last hour
    assert B.bvc_imbalance(up, v)[-1] > 0.5


def test_rolls_are_excluded():
    c, v = _series()
    c2 = c.copy()
    c2[-6:] += 40.0                                       # a contract-roll jump six bars ago
    imb = B.bvc_imbalance(c2, v)
    base = B.bvc_imbalance(c, v)
    assert abs(imb[-1] - base[-1]) < 0.35                 # the jump bar itself carries no volume or sign


def test_no_look_ahead_in_imbalance_and_signals():
    c, v = _series(4000)
    full_i, full_s = B.bvc_imbalance(c, v), B.signals(B.bvc_imbalance(c, v))
    for k in (2600, 3500):
        part = B.bvc_imbalance(c[:k], v[:k])
        assert np.allclose(part, full_i[:k], equal_nan=True)
        assert np.array_equal(B.signals(part), full_s[:k])
    assert (full_s != 0).sum() > 50 and set(np.unique(full_s)) <= {-1.0, 0.0, 1.0}


def test_declared_constants():
    assert B.TARGETS == {"T10": (10.0, 10.0), "T15": (15.0, 10.0), "T20": (20.0, 10.0)}
    assert (B.SIGMA_BARS, B.WINDOW_BARS, B.ROLL_SIGMA, B.PCT, B.PCT_BARS) == (100, 12, 8.0, 0.90, 2000)
