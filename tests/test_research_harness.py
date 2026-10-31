"""Phase B0 research harness (research/09): hand-worked fills, partition guard, and statistics that detect a planted
edge and do not invent one in noise."""
import json

import numpy as np
import pandas as pd
import pytest

from quantum import holdout
from quantum.research import harness as H


def _df(closes, opens=None, highs=None, lows=None, start="2021-03-01 10:00"):
    c = np.asarray(closes, float)
    o = c.copy() if opens is None else np.asarray(opens, float)
    h = np.maximum(o, c) + 1.0 if highs is None else np.asarray(highs, float)
    lo = np.minimum(o, c) - 1.0 if lows is None else np.asarray(lows, float)
    idx = pd.date_range(start, periods=len(c), freq="1h", tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx)


# ---------------- fills ----------------
def _flat(n=30, px=100.0):
    return [px] * n


def test_fill_cases_by_hand():
    base = _flat()                          # range 2 on every bar -> ATR(14) = 2 from bar 13 on (Wilder seeded by SMA)
    zero = np.zeros(40)
    sig = np.zeros(40)
    sig[30] = 1                             # long at bar 30's close 100, R = 2: stop 98, target (k=2) 104
    # target hit intrabar
    c = base + [100, 103, 105, 105, 105, 105, 105, 105, 105, 105]
    o = base + [100, 100, 103, 105, 105, 105, 105, 105, 105, 105]
    df = _df(c, opens=o)
    tr = H.simulate(df, sig, k=2, h=5, cost=zero)
    assert tr.iloc[0].outcome == "WIN" and tr.iloc[0].gross_r == pytest.approx(2.0)
    # opened through the stop: fill at the open
    c = base + [100, 95, 95, 95, 95, 95, 95, 95, 95, 95]
    o = base + [100, 96, 95, 95, 95, 95, 95, 95, 95, 95]
    tr = H.simulate(_df(c, opens=o), sig, k=2, h=5, cost=zero)
    assert tr.iloc[0].outcome == "LOSS" and tr.iloc[0].gross_r == pytest.approx((96 - 100) / 2)
    # both barriers inside one bar: AMBIGUOUS, charged as a full loss
    hi = [x + 1 for x in base] + [101, 105, 101, 101, 101, 101, 101, 101, 101, 101]
    lo = [x - 1 for x in base] + [99, 97, 99, 99, 99, 99, 99, 99, 99, 99]
    tr = H.simulate(_df(base + [100] * 10, highs=hi, lows=lo), sig, k=2, h=5, cost=zero)
    assert tr.iloc[0].outcome == "AMBIGUOUS" and tr.iloc[0].gross_r == pytest.approx(-1.0)
    # time stop at the close of bar i + h
    c = base + [100, 101, 101, 101, 101, 102.5, 101, 101, 101, 101]
    tr = H.simulate(_df(c), sig, k=2, h=5, cost=zero)
    assert tr.iloc[0].outcome == "TIMEOUT" and tr.iloc[0].exit_i == 35 and tr.iloc[0].gross_r == pytest.approx(1.25)
    # cost charged once, in R
    tr = H.simulate(_df(base + [100] * 10), sig, k=2, h=5, cost=np.full(40, 0.5))
    assert tr.iloc[0].cost_r == pytest.approx(0.25) and tr.iloc[0].net_r == pytest.approx(tr.iloc[0].gross_r - 0.25)


def test_cost_model_is_the_frozen_engine_model():
    idx = pd.DatetimeIndex(["2021-03-02 13:00", "2021-03-02 02:00", "2021-03-02 21:30"], tz="UTC")   # London, Asia, after NY
    c = H.cost_pts(idx)
    assert c[0] == pytest.approx(0.30 + 0.40 + 0.07) and c[2] == pytest.approx(0.50 + 0.40 + 0.07)


# ---------------- partitions ----------------
def test_partition_guard(tmp_path, monkeypatch):
    idx = pd.date_range("2022-12-01", "2023-03-01", freq="1D", tz="UTC")
    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}, index=idx)
    dev = H.partition(df, "development")
    assert dev.index.max() < H.DEV[1] and len(dev) > 0
    monkeypatch.setattr(H, "REG_DIR", str(tmp_path))
    with pytest.raises(H.SealedPartition):
        H.partition(df, "validation")
    (tmp_path / "x.json").write_text(json.dumps({"approved_by_operator": False, "partitions": ["validation"]}))
    with pytest.raises(H.SealedPartition):
        H.partition(df, "validation", "x")
    (tmp_path / "y.json").write_text(json.dumps({"approved_by_operator": True, "partitions": ["validation"]}))
    assert H.partition(df, "validation", "y").index.min() >= H.VAL[0]
    with pytest.raises(H.SealedPartition):
        H.partition(df, "holdout", "y")


# ---------------- statistics: planted edge versus noise ----------------
def _walk(n, phi, seed):
    rng = np.random.default_rng(seed)
    e = rng.normal(0, 1, n)
    r = np.zeros(n)
    for t in range(1, n):
        r[t] = phi * r[t - 1] + e[t]
    c = 1000 + np.cumsum(r)
    o = np.concatenate([[c[0]], c[:-1]])
    h = np.maximum(o, c) + np.abs(rng.normal(0, 0.3, n))
    lo = np.minimum(o, c) - np.abs(rng.normal(0, 0.3, n))
    idx = pd.date_range("2020-02-03", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx)


def _momentum(df):
    c = df["close"].to_numpy()
    s = np.sign(np.concatenate([[0], np.diff(c)]))
    return s


def test_planted_edge_is_detected_and_noise_is_not():
    edge = _walk(6000, 0.35, 1)
    noise = _walk(6000, 0.0, 2)
    z = np.zeros(6000)
    se = H.summary(H.simulate(edge, _momentum(edge), k=1, h=8, cost=z))
    sn = H.summary(H.simulate(noise, _momentum(noise), k=1, h=8, cost=z))
    assert se["t"] > 3 and se["net_r"] > 0.05
    assert abs(sn["t"]) < 3


def test_reality_check_pbo_dsr_bh():
    rng = np.random.default_rng(5)
    noise = rng.normal(0, 1, (400, 30))
    rc = H.reality_check(noise, B=300)
    assert rc["p_value"] > 0.05
    planted = noise.copy()
    planted[:, 7] += 0.4
    rc2 = H.reality_check(planted, B=300)
    assert rc2["p_value"] < 0.05 and rc2["best"] == 7
    # PBO: noise -> about 0.5; one dominant config -> about 0
    # (one noise matrix varies widely, 0.09-0.99 over 60 seeds; the average is the property)
    assert 0.40 < np.mean([H.pbo_cscv(np.random.default_rng(s).normal(0, 1, (64, 20)))["pbo"] for s in range(40)]) < 0.60
    good = rng.normal(0, 1, (64, 20))
    good[:, 3] += 1.5
    assert H.pbo_cscv(good)["pbo"] < 0.1
    # DSR: the best of 30 noise Sharpes is not significant after deflation
    srs = list(noise.mean(axis=0) / noise.std(axis=0, ddof=1))
    j = int(np.argmax(srs))
    d = H.deflated_sharpe(srs[j], 400, 0.0, 3.0, srs)
    assert d["dsr"] < 0.95
    assert H.benjamini_hochberg([0.001, 0.2, 0.03, 0.5], q=0.10) == [True, False, True, False]
    lo, hi = H.wilson(90, 100)
    assert lo == pytest.approx(0.826, abs=1e-3)


def test_harness_is_outside_the_engine():
    assert all("research" not in f for f in holdout.ENGINE_SOURCES)
    assert holdout.freeze_key(__import__("quantum.config", fromlist=["DEFAULT"]).DEFAULT) == "5e4630924d663fc5:60bb01794d03c9ac"


def test_purged_folds_never_overlap_label_windows():
    for tr, te in H.purged_folds(1000, 5, span=16, embargo=8):
        a, b = te.min(), te.max() + 1
        assert not (((tr + 16) >= a) & (tr < b)).any()            # no training label window touches the test fold
        assert not ((tr >= b) & (tr < b + 8)).any()                 # embargo after the fold
        assert len(set(tr) & set(te)) == 0


def test_screens_are_one_sided_and_pbo_reports_oos_loss():
    assert H.t_pvalue(-10.0, 1000) > 0.99 and H.t_pvalue(3.0, 1000) < 0.002
    rng = np.random.default_rng(9)
    losing = rng.normal(-1, 0.1, (64, 10))
    losing[:, 2] += 0.5                       # consistently the "best", but still losing
    p = H.pbo_cscv(losing)
    assert p["pbo"] < 0.1 and p["oos_mean_of_is_best"] < 0 and p["p_oos_loss_of_is_best"] == 1.0
