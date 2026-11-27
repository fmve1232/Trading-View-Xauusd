"""audit/tools/h4_forward_diagnosis.py: the exit replica against quantum/backtest.simulate itself, the races, the matched
permutation test and the multiplicity corrections, on hand-made and random synthetic bars (no market data)."""
import os
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from quantum import backtest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "audit", "tools"))
import h4_forward_diagnosis as H

CFG = SimpleNamespace(slippage_pts=0.1, commission_l=7.0, point_value=100.0)


def _res(o, h, l, c, sig_i, long, sl, tp1, tp2):
    n = len(c)
    nan = np.full(n, np.nan)
    eb, es = np.zeros(n, int), np.zeros(n, int)
    (eb if long else es)[sig_i] = 1
    psl, p1, p2 = nan.copy(), nan.copy(), nan.copy()
    psl[sig_i], p1[sig_i], p2[sig_i] = sl, tp1, tp2
    F = {"o": o, "h": h, "l": l, "c": c, "index": pd.date_range("2026-11-16", periods=n, freq="5min", tz="UTC"),
         "sess_spread": np.full(n, 0.37), "session_label": np.array(["NY"] * n), "mkt_regime": np.array(["RANGE"] * n)}
    R = {"exec_buy": eb, "exec_sell": es, "plan_sl": psl, "plan_tp1": p1, "plan_tp2": p2, "tq": np.zeros(n),
         "cal_p_long": nan, "cal_p_short": nan, "plan_ev": nan}
    return SimpleNamespace(F=F, rows=R)


def _path(rng, n, gap_every=0):
    c = 4000 + np.cumsum(rng.normal(0, 1.2, n))
    o = np.r_[c[0], c[:-1]] + rng.normal(0, 0.15, n)
    if gap_every:
        o[::gap_every] += rng.normal(0, 6.0, len(o[::gap_every]))        # opens far from the last close: gap fills
    h = np.maximum(o, c) + rng.exponential(0.8, n)
    lo = np.minimum(o, c) - rng.exponential(0.8, n)
    return o, h, lo, c


@pytest.mark.parametrize("seed", range(40))
def test_the_replica_reproduces_backtest_simulate_on_random_paths_with_gaps(seed):
    rng = np.random.default_rng(seed)
    n = 400
    o, h, lo, c = _path(rng, n, gap_every=int(rng.integers(0, 2)) * int(rng.integers(5, 30)))
    i = int(rng.integers(5, 50))
    long = bool(rng.integers(0, 2))
    d = float(rng.uniform(2, 8))
    s = 1 if long else -1
    e = c[i]
    sl, tp1, tp2 = e - s * d, e + s * d * float(rng.uniform(0.8, 2.0)), e + s * d * float(rng.uniform(2.1, 4.0))
    ref = [t for t in backtest.simulate(_res(o, h, lo, c, i, long, sl, tp1, tp2), CFG) if not t.get("open")]
    B = {"t": np.arange(n) * 300, "o": o, "h": h, "l": lo, "c": c}
    cost = 0.37 + 2 * 0.1 + 7.0 / 100.0
    m = H.manage(B, i + 1, n, long, e, sl, tp1, tp2, cost)
    if not ref:                                            # still open at the end of the data
        assert m["reason"] == "OPEN_AT_HORIZON"
        return
    t = ref[0]
    assert (m["reason"], m["exit_i"], m["tp1_done"]) == (t["exit_reason"], t["exit_i"], t["tp1_hit"])
    assert m["gross"] == pytest.approx(t["gross_pts"], abs=1e-3) and m["r"] == pytest.approx(t["r"], abs=1e-3)


def test_races_stop_first_on_a_shared_bar_and_hours_to_the_target():
    #           bar 0     bar 1 (TP1 3)  bar 2 (+10 and stop together)
    B5 = {"t": np.array([0, 300, 600, 900]), "o": np.array([100.0, 101, 103, 104]),
          "h": np.array([101.0, 103.5, 111, 112]), "l": np.array([99.5, 100.5, 94, 103])}
    r = H.races(B5, 0, 4, True, 100.0, 95.0, {"tp1": 103.0, "usd10": 110.0, "far": 200.0})
    assert r["tp1"] == ("TP", (300 + 300) / 3600.0)        # touched on bar 1: its close is 10 minutes after the entry
    assert r["usd10"] == ("SL", None)                      # the same bar touched the stop: stop first
    assert r["far"] == ("SL", None) and r["stopped"] is True
    assert r["mfe_usd"] == pytest.approx(3.5)              # before the stop bar (which is excluded)
    short = H.races(B5, 0, 2, False, 100.0, 105.0, {"tp": 90.0})
    assert short["tp"] == (None, None) and short["stopped"] is False


def test_holm_and_bh_match_their_definitions():
    ps = [0.01, 0.04, 0.03, 0.20]
    assert H.holm(ps) == pytest.approx([0.04, 0.09, 0.09, 0.20])
    assert H.bh(ps) == pytest.approx([0.04, 0.0533333, 0.0533333, 0.20], abs=1e-6)


def test_the_matched_permutation_p_is_small_only_when_the_entries_differ_from_their_random_twins():
    rng = np.random.default_rng(1)
    rnd = (rng.random((60, 999)) < 0.4).astype(float)
    same = (rng.random(60) < 0.4).astype(float)
    better = np.ones(60)
    assert H.perm_p(same, rnd)["p_two_sided"] > 0.05
    out = H.perm_p(better, rnd)
    assert out["p_two_sided"] == pytest.approx(1 / 1000) and out["actual"] == 1.0 and 0.35 < out["null_mean"] < 0.45
    assert out["p_normal"] < 1e-20 and H.perm_p(same, rnd)["p_normal"] > 0.05       # the normal tail goes past 1 / (K + 1)
    few = H.perm_p(np.array([1.0, np.nan, np.nan]), rnd[:3])
    assert few["p_two_sided"] is None                      # fewer than five decided: no test


def test_a_degenerate_null_gives_no_p_value_rather_than_zero():
    """Found on the first real run: 4h trades with two distinct twins gave a null with no spread, and the normal tail
    returned p = 0 (a false 'significant'). Such a null now gives no p-value."""
    rnd = np.ones((8, 500))
    out = H.perm_p(np.r_[np.ones(5), np.zeros(3)], rnd)
    assert out["p_two_sided"] is None and out["p_normal"] is None and out["note"] == "degenerate null"
