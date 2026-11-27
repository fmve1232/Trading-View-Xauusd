"""audit/tools/risk_analytics.py (G5): CVaR, drawdown, the day-block Monte Carlo and the expectancy split, worked by hand
on hand-made ledgers in a throwaway store."""
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "audit", "tools"))
import risk_analytics as RA


def test_tail_by_hand():
    x = np.arange(-10, 10, dtype=float)                     # 20 values: k = ceil(0.05 * 20) = 1
    assert RA.tail(x) == {"n": 20, "k": 1, "var": -10.0, "cvar": -10.0, "note": "k = 1: the single worst outcome"}
    y = np.r_[np.full(38, 1.0), -3.0, -1.0]                 # 40 values: k = 2, the two worst are -3 and -1
    assert RA.tail(y) == {"n": 40, "k": 2, "var": -1.0, "cvar": -2.0, "note": ""}
    z = np.r_[np.full(28, 1.0), -4.0, -2.0]                 # 30 values: k = ceil(1.5) = 2, not 1
    assert RA.tail(z)["k"] == 2 and RA.tail(z)["cvar"] == -3.0
    assert RA.tail(np.array([]))["cvar"] is None


def test_max_drawdown_by_hand():
    assert RA.max_drawdown(np.array([1, -2, 1, -3, 5], float)) == 4.0      # equity 0 1 -1 0 -3 2: peak 1, trough -3
    assert RA.max_drawdown(np.array([-1, -1], float)) == 2.0               # the start is a peak at 0
    assert RA.max_drawdown(np.array([1, 2, 3], float)) == 0.0
    assert RA.max_drawdown(np.array([])) == 0.0


def test_the_session_day_starts_at_17_new_york():
    assert RA.session_day("2026-11-17T21:59:00+00:00") == "2026-11-17"      # 16:59 New York (EST)
    assert RA.session_day("2026-11-17T22:00:00+00:00") == "2026-11-18"      # 17:00 New York: the next session
    assert RA.session_day("2026-07-14T20:59:00+00:00") == "2026-07-14"      # 16:59 New York (EDT)
    assert RA.session_day("2026-07-14T21:00:00+00:00") == "2026-07-15"


def test_stationary_bootstrap_blocks():
    rng = np.random.default_rng(1)
    run = RA.stationary_days(50, 1e12, rng)                                 # one block: consecutive days, wrapping
    assert all((run[i + 1] - run[i]) % 50 == 1 for i in range(49))
    many = RA.stationary_days(10_000, 1.0, np.random.default_rng(2))       # mean block 1: every day a fresh draw
    assert abs(np.mean(np.diff(many) % 10_000 == 1) - 1e-4) < 2e-3
    a = RA.stationary_days(100, 5.0, np.random.default_rng(3))
    starts = 1 + np.sum(np.diff(a) % 100 != 1)
    assert 10 <= starts <= 35                                               # about 100 / 5 = 20 blocks


def test_monte_carlo_keeps_each_day_whole_and_in_order():
    day = np.array([2.0, -3.0, -1.0, 1.0])                                  # one day: drawdown 4 inside it
    dd = RA.mc_drawdown([day], 2.0, 200, np.random.default_rng(0))
    assert np.all(dd == 4.0)                                                # only that day, always in its own order
    two = RA.mc_drawdown([np.array([-1.0]), np.array([-1.0])], 1.0, 500, np.random.default_rng(0))
    assert np.all(two == 2.0)


def test_day_bootstrap_of_the_mean():
    same = [np.array([1.0, -1.0]), np.array([0.5, -0.5])]                   # every day has mean 0
    assert RA.day_boot_mean(same, 1000, np.random.default_rng(0)) == [0.0, 0.0]
    assert RA.day_boot_mean([np.array([1.0])], 1000, np.random.default_rng(0)) is None


def _t(entry_time, exit_time, r, gross, cost=0.5, entry=4000.0, sl=3990.0, key="k1", **kw):
    t = {"dir": "LONG", "entry_time": entry_time, "exit_time": exit_time, "entry": entry, "sl": sl, "r": r,
         "gross_pts": gross, "cost_pts": cost, "pts": gross - cost, "open": False, "freeze_key": key}
    t.update(kw)
    return t


def _store(tmp_path, files):
    d = tmp_path / "store"
    (d / "holdout").mkdir(parents=True)
    for name, rows in files.items():
        (d / "holdout" / name).write_text(json.dumps(rows))
    return str(d)


LED = [_t("2026-11-17T10:00:00+00:00", "2026-11-17T11:00:00+00:00", 0.95, 10.0),       # day 17: +0.95
       _t("2026-11-17T12:00:00+00:00", "2026-11-17T13:00:00+00:00", -1.05, -10.0),     # day 17: -1.05
       _t("2026-11-18T10:00:00+00:00", "2026-11-18T11:00:00+00:00", -1.05, -10.0),     # day 18: -1.05
       _t("2026-11-18T23:00:00+00:00", "2026-11-18T23:30:00+00:00", 1.95, 20.0)]       # 18:30 NY: day 19


def test_analyse_a_hand_made_ledger(tmp_path):
    d = _store(tmp_path, {"15m_h4.json": LED + [_t("2026-11-19T10:00:00+00:00", "2026-11-19T10:15:00+00:00", 9, 9, open=True)],
                          "manifest_h4.json": [], "15m_h4_old.json": LED})
    out = RA.run(d, sims=500, seed=7)
    assert list(out["groups"]) == ["h4|15m|k1"]
    g = out["groups"]["h4|15m|k1"]
    assert (g["n"], g["days"], g["first_exit_day"], g["last_exit_day"]) == (4, 3, "2026-11-17", "2026-11-19")
    e = g["expectancy_r"]
    assert e["before_cost"] == 0.25 and e["after_modelled_cost"] == 0.2 and e["modelled_cost"] == 0.05   # (1-1-1+2)/4 ...
    assert e["after_measured_cost"] is None and e["measured_cost_status"].startswith("NOT AVAILABLE")
    assert e["usd_at_650_per_r_after_modelled_cost"] == 130.0
    assert g["tail_per_trade_net_r"]["cvar"] == -1.05 and g["tail_per_day_net_r"]["cvar"] == -1.05      # day 18: -1.05
    assert g["observed_max_drawdown_r"] == 2.1                     # +0.95, -1.05, -1.05: from 0.95 down to -1.15
    mc = g["monte_carlo_drawdown"]
    assert set(mc) == {"L=1d", "L=2d", "L=5d"} and all(v["p95_r"] >= 0 for v in mc.values())
    assert mc["L=1d"]["p95_usd_at_650_per_r"] == round(mc["L=1d"]["p95_r"] * 650, 0)
    assert mc["L=1d"]["p50_r"] < mc["L=1d"]["p95_r"] <= mc["L=1d"]["p99_r"]


def test_drawdown_is_taken_in_exit_order_not_ledger_order(tmp_path):
    # the ledger lists trades by entry: A (-1) opened first but closed last; in exit order B +1, C -1, A -1
    a = _t("2026-11-17T10:00:00+00:00", "2026-11-17T16:00:00+00:00", -1.0, -10.0)
    b = _t("2026-11-17T11:00:00+00:00", "2026-11-17T12:00:00+00:00", 1.0, 10.0)
    c = _t("2026-11-17T13:00:00+00:00", "2026-11-17T14:00:00+00:00", -1.0, -10.0)
    g = RA.run(_store(tmp_path, {"15m_h4.json": [a, b, c]}), sims=50)["groups"]["h4|15m|k1"]
    assert g["observed_max_drawdown_r"] == 2.0                  # entry order would give 1.0


def test_reproducible_and_groups_seeded_by_their_own_key(tmp_path):
    d = _store(tmp_path, {"15m_h4.json": LED})
    a, b = RA.run(d, sims=300, seed=7), RA.run(d, sims=300, seed=7)
    assert a == b
    d2 = _store(tmp_path / "x", {"15m_h4.json": LED, "5m_h2.json": LED})                  # another group added
    c = RA.run(d2, sims=300, seed=7)
    assert c["groups"]["h4|15m|k1"] == a["groups"]["h4|15m|k1"]


def test_freeze_keys_are_kept_apart_and_zero_stops_excluded(tmp_path):
    old = [_t("2026-11-10T10:00:00+00:00", "2026-11-10T11:00:00+00:00", -1.0, -10.0, key="k0")]
    zero = [_t("2026-11-17T14:00:00+00:00", "2026-11-17T15:00:00+00:00", 0.0, 0.0, sl=4000.0)]
    out = RA.run(_store(tmp_path, {"15m_h6.json": LED + old + zero}), sims=100, seed=1)
    assert set(out["groups"]) == {"h6|15m|k0", "h6|15m|k1"}
    assert out["groups"]["h6|15m|k1"]["excluded_zero_stop"] == 1 and out["groups"]["h6|15m|k1"]["n"] == 4
    assert out["groups"]["h6|15m|k0"]["monte_carlo_drawdown"] == {"note": "fewer than 2 trading days: not computed"}


def test_limitations_and_assumptions_are_written_into_the_output(tmp_path):
    m = RA.run(_store(tmp_path, {"15m_h4.json": LED}), sims=50)["method"]
    assert m["usd_per_r_status"].startswith("ASSUMPTION") and m["sims"] == 50 and m["seed"] == 20261127
    assert any("lower bound" in x for x in m["limitations"]) and any("G2" in x for x in m["limitations"])


@pytest.mark.parametrize("seed", range(5))
def test_monte_carlo_never_below_the_worst_single_day_and_never_above_the_total_loss(seed):
    rng = np.random.default_rng(seed)
    days = [rng.normal(0, 1, rng.integers(1, 6)) for _ in range(8)]
    dd = RA.mc_drawdown(days, 2.0, 400, np.random.default_rng(seed))
    worst_inside = max(RA.max_drawdown(x) for x in days)
    total_loss = sum(-v for x in days for v in x if v < 0)
    assert dd.min() >= 0 and dd.max() <= total_loss * len(days) + 1e-9
    assert np.quantile(dd, 0.99) >= worst_inside - 1e-9 or worst_inside == 0


def test_the_g5_document_is_what_the_evidence_gives():
    root = os.path.join(os.path.dirname(__file__), "..")
    ev = os.path.join(root, "docs", "final_audit", "evidence", "g5_risk_analytics_2026-11-27.json")
    assert RA.write_doc(ev, os.path.join(root, "docs", "final_audit", "G5_RISK_ANALYTICS.md"), check=True) == 0
