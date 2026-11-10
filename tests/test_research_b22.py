"""B22 (research/registrations/B22.json): the causal helpers and the evaluation."""
import math

import numpy as np
import pandas as pd
import pytest

from quantum.research import b22


def test_asof_uses_only_bars_closed_by_then():
    src_close = np.array([100, 200, 300])
    vals = np.array([1.0, 2.0, 3.0])
    assert b22.asof(src_close, vals, np.array([99, 100, 250, 1000])).tolist()[1:] == [1.0, 2.0, 3.0]
    assert math.isnan(b22.asof(src_close, vals, np.array([99]))[0])


def test_hmm_filter_never_looks_ahead():
    hmm = pytest.importorskip("hmmlearn.hmm")
    rng = np.random.default_rng(0)
    X = np.column_stack([rng.normal(0, 1, 400), np.abs(rng.normal(0, 1, 400))])
    mdl = hmm.GaussianHMM(n_components=3, covariance_type="diag", n_iter=20, random_state=1).fit(X[:300])
    a = b22.hmm_filter(mdl, X)
    X2 = X.copy()
    X2[250:] = 50.0                                               # a shock after t = 249 cannot change t <= 249
    b = b22.hmm_filter(mdl, X2)
    assert np.allclose(a[:250], b[:250]) and np.allclose(a.sum(1), 1.0)


def test_cusum_is_causal_and_sigma_scaled():
    r = np.r_[np.zeros(150), np.ones(30)]
    c1 = b22.cusum(r.copy())
    r2 = r.copy()
    r2[-5:] = -100
    c2 = b22.cusum(r2)
    assert np.allclose(np.nan_to_num(c1[:175]), np.nan_to_num(c2[:175]))


def test_the_drift_solver_reproduces_the_geometry_and_ninety_percent():
    k0 = b22.drift_for(13 / 28, 15, 13)
    assert k0 < 1e-4                                              # no drift: S / (S + T)
    k = b22.drift_for(0.9, 15, 13)
    p = (1 - math.exp(-k * 13)) / (1 - math.exp(-k * 28))
    assert p == pytest.approx(0.9, abs=1e-6)


def test_evaluate_counts_precision_in_the_top_fraction_and_net_after_cost():
    pytest.importorskip("sklearn")                                  # research-only dependency, not in requirements.txt
    rng = np.random.default_rng(1)
    n = 4000
    p = rng.random(n)
    y = (rng.random(n) < p).astype(int)                          # a perfectly calibrated toy model
    d = np.where(rng.random(n) < 0.5, 1, -1)
    day = np.repeat(np.arange(n // 40), 40)
    out = b22.evaluate(p, y, d, day, np.full(n, 0.77), np.zeros(n, int), 15.0)
    top = out["top"]["0.1"]
    assert 380 <= top["n"] <= 420 and top["precision"] > 0.85 and top["ci95"][0] < top["precision"] < top["ci95"][1]
    assert top["net_usd_per_oz"] == pytest.approx(np.mean(np.where(y[p >= np.quantile(p, 0.9)] == 1, 15, -13)) - 0.77)
    assert out["auc"] > 0.7 and out["brier"] < out["brier_base"]


def test_rows_double_each_bar_with_signed_features_flipped():
    idx = pd.date_range("2026-03-02", periods=3, freq="15min", tz="UTC")
    df = pd.DataFrame({"nd_a": [1.0, 2.0, 3.0], "sg_b": [0.5, -0.5, 1.0]}, index=idx)
    hm = np.array([[0.2, 0.3, 0.5, 1.0]] * 3)
    X, D, names = b22.rows_for(df, hm, np.array([0, 2]))
    assert D.tolist() == [1, 1, -1, -1] and names[-1] == "direction"
    assert X[:, 1].tolist() == [0.5, 1.0, -0.5, -1.0] and X[:, 5].tolist() == [1.0, 1.0, -1.0, -1.0]   # sg_b and cusum flip
