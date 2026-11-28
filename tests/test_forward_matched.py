"""audit/tools/forward_matched.py: the fixed-rule replay equals the production exit model (backtest.simulate) on random
paths, races and excursions are worked by hand, the random matches respect every matching rule, and the verdicts follow
the rule fixed in the docstring. No network, no stored data."""
import math
import os
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "audit", "tools"))
import forward_matched as M

from quantum import backtest

T0 = int(pd.Timestamp("2026-11-17T14:00:00Z").timestamp())     # a Tuesday, 09:00 New York


def bars(rows, start=T0):
    a = np.array(rows, float)
    t = start + 300 * np.arange(len(a), dtype=np.int64)
    return {"t": t, "o": a[:, 0], "h": a[:, 1], "l": a[:, 2], "c": a[:, 3], "reopen": np.zeros(len(a), bool)}


def test_manage_by_hand():
    # long 2000, stop 1990, TP1 2010, TP2 2020, cost 0.5
    P = bars([(2000, 2005, 1995, 2004), (2004, 2011, 2003, 2009), (2009, 2012, 2000, 2001), (2001, 2025, 2001, 2024)])
    end = T0 + 4 * 300
    # bar 1 reaches TP1 (half at 2010) -> stop to 2000 from bar 2; bar 2's low 2000 touches the break-even stop
    assert M.manage(P, 0, end, 1, 2000.0, 1990.0, 2010.0, 2020.0, 0.5) == (0.5 * 10 + 0.5 * 0 - 0.5) / 10
    # a time exit after two bars: half at TP1, the rest at bar 1's close 2009
    assert M.manage(P, 0, T0 + 2 * 300, 1, 2000.0, 1990.0, 2010.0, 2020.0, 0.0) == (0.5 * 10 + 0.5 * 9) / 10
    # data ending before the time exit: no result
    assert M.manage(P, 0, T0 + 10 * 300, 1, 2000.0, 1980.0, 2100.0, 2200.0, 0.0) is None
    # a short whose stop is opened through: filled at the open
    G = bars([(2000, 2001, 1999, 2000), (2015, 2016, 2014, 2015)])
    assert M.manage(G, 0, T0 + 600, -1, 2000.0, 2010.0, 1990.0, 1980.0, 0.0) == -15 / 10


def test_manage_equals_the_production_exit_model_on_random_paths():
    rng = np.random.default_rng(3)
    n_cases = 0
    for _ in range(300):
        n = 60
        c = 2000 + np.cumsum(rng.normal(0, 2.0, n))
        o = np.concatenate([[2000.0], c[:-1] + rng.normal(0, 0.5, n - 1)])
        h = np.maximum(o, c) + rng.uniform(0, 2, n)
        l = np.minimum(o, c) - rng.uniform(0, 2, n)
        side = int(rng.choice([1, -1]))
        d = float(rng.uniform(3, 8))
        e = float(c[0])
        sl, tp1, tp2 = e - side * d, e + side * d, e + side * 2 * d
        idx = pd.date_range(pd.Timestamp(T0, unit="s", tz="UTC"), periods=n, freq="5min")
        F = {"o": o, "h": h, "l": l, "c": c, "index": idx, "sess_spread": np.full(n, 0.4),
             "session_label": np.array(["NY"] * n), "mkt_regime": np.array(["TREND"] * n)}
        R = {"exec_buy": [1 if side == 1 else 0] + [0] * (n - 1), "exec_sell": [1 if side == -1 else 0] + [0] * (n - 1),
             "plan_sl": [sl] + [math.nan] * (n - 1), "plan_tp1": [tp1] + [math.nan] * (n - 1),
             "plan_tp2": [tp2] + [math.nan] * (n - 1), "tq": [0] * n, "cal_p_long": [math.nan] * n,
             "cal_p_short": [math.nan] * n, "plan_ev": [math.nan] * n}
        cfg = SimpleNamespace(slippage_pts=0.0, commission_l=0.0, point_value=100.0)
        tr = backtest.simulate(SimpleNamespace(F=F, rows=R), cfg)
        if tr[0]["exit_reason"] == "OPEN":
            continue
        P = {"t": idx.as_unit("s").asi8.astype(np.int64), "o": o, "h": h, "l": l, "c": c, "reopen": np.zeros(n, bool)}
        got = M.manage(P, 1, int(P["t"][-1]) + 300, side, e, sl, tp1, tp2, 0.4)       # managed from the bar after entry
        assert abs(got - tr[0]["r"]) < 1e-3, (tr[0], got)
        n_cases += 1
    assert n_cases > 200


def test_races_and_excursions_by_hand():
    P = bars([(2000, 2004, 1998, 2003), (2003, 2011, 2002, 2010), (2010, 2016, 2009, 2015), (2015, 2015, 1985, 1990)])
    r = M.races(P, 0, 1, 2000.0, 1990.0)
    assert r[10] == (1, 10.0) and r[15] == (1, 15.0) and r[20] == (0, None)
    assert M.races(P, 0, -1, 2000.0, 2010.0)[10] == (0, None)            # bar 1's high 2011 stops the short first
    both = bars([(2000, 2011, 1989, 2000)])                               # one bar touches +$10 and the stop
    assert M.races(both, 0, 1, 2000.0, 1990.0)[10] == (0, None)          # the stop, as in the engine
    assert M.excursions(P, 0, T0 + 3 * 300, 1, 2000.0) == (16.0, 2.0)
    assert M.excursions(P, 0, T0 + 3 * 300, -1, 2000.0) == (2.0, 16.0)


def test_random_matches_respect_every_matching_rule():
    # five weekdays of 5-minute bars, flat at 2000 with small ranges
    days = []
    for k in range(5):
        start = T0 - 3 * 3600 + k * 86400
        days.append(bars([(2000, 2001, 1999, 2000)] * 72, start))           # 06:00-12:00 New York each day
    P = {x: np.concatenate([d[x] for d in days]) for x in ("t", "o", "h", "l", "c", "reopen")}
    t = {"dir": "LONG", "entry_time": pd.Timestamp(T0 - 900, unit="s", tz="UTC").isoformat(),
         "exit_time": pd.Timestamp(T0 + 900, unit="s", tz="UTC").isoformat(), "entry": 2000.0, "sl": 1995.0,
         "tp1": 2005.0, "tp2": 2010.0, "r": 0.1, "gross_pts": 0.9, "cost_pts": 0.4}
    cand = M.candidates(P, "15m")
    assert (cand["close"] % 900 == 0).all()
    seen = []

    class Spy:                                   # records the candidate pool the tool draws from
        def __init__(self):
            self.rng = np.random.default_rng(0)

        def choice(self, pool, size, replace):
            seen.extend(int(cand["close"][q]) for q in pool)
            return self.rng.choice(pool, size=size, replace=replace)

    rec = M.one(t, "15m", P, cand, 50, Spy())
    fill_min = M.ny_minute(T0)
    assert seen and all(M.nyday(x) != M.nyday(T0) for x in seen)
    assert all(min(abs(M.ny_minute(x) - fill_min), 1440 - abs(M.ny_minute(x) - fill_min)) <= 60 for x in seen)
    assert rec["random_r"] and all(abs(x - (-0.4 / 5)) < 1e-9 for x in rec["random_r"])   # flat path: time exit, cost only


def test_day_bootstrap_holm_bh_and_wilson():
    rng = np.random.default_rng(0)
    assert M.day_boot(np.array([1.0, 1.0]), ["a", "b"], rng)["ci95_days"] is None          # fewer than 5 days
    out = M.day_boot(np.array([1.0] * 10), list("abcdefghij"), rng)
    assert out["ci95_days"] == [1.0, 1.0] and out["p_le_0"] == 0.0
    assert M.holm([0.01, 0.04, 0.03]) == [0.03, 0.06, 0.06] and M.bh([0.01, 0.04, 0.03]) == [0.03, 0.04, 0.04]
    assert M.wilson(0, 0) is None and M.wilson(5, 10) == [0.2366, 0.7634]


def test_the_bar_loader_drops_shut_and_off_grid_rows_and_marks_reopens(tmp_path):
    d = tmp_path / "XAU_USD_5m"
    d.mkdir()
    rows = ["datetime,open,high,low,close,volume",
            "2026-11-20 21:50:00+00:00,1,1,1,1,", "2026-11-20 21:55:00+00:00,1,1,1,1,",   # Friday 16:50-16:55 NY
            "2026-11-21 12:00:00+00:00,1,1,1,1,",                                         # Saturday: shut
            "2026-11-22 23:00:00+00:00,2,3,0.5,2,",                                       # Sunday 18:00 NY: reopen
            "2026-11-22 23:02:10+00:00,2,2,2,2,", "2026-11-22 23:05:00+00:00,2,2,2,2,"]
    (d / "2026-11.csv").write_text("\n".join(rows) + "\n")
    P = M.load_bars(str(tmp_path))
    assert len(P["t"]) == 4 and P["reopen"].tolist() == [False, False, True, False]


def test_verdicts_follow_the_fixed_rule():
    def led(n, ci, p):
        return {"trades": n, "net_r_modelled_cost": {"ci95_days": ci}, "recorded_minus_random": {"p_le_0": p}}
    per = {"a": led(100, [0.05, 0.3], 0.001), "b": led(100, [-0.1, 0.2], 0.001), "c": led(100, [0.05, 0.3], 0.03),
           "d": led(29, [0.5, 0.9], 0.0), "e": led(40, [0.05, 0.3], 0.045)}
    assert M.verdicts(per) == ["a", "b", "c", "e"]
    assert per["a"]["verdict"] == "EDGE (forward evidence)"                       # Holm 4 x 0.001 = 0.004
    assert per["b"]["verdict"].startswith("NO EDGE")                              # interval includes zero
    assert per["c"]["recorded_minus_random"]["p_holm"] == 0.06                    # 2 x 0.03: raw 0.03 is not enough
    assert per["c"]["verdict"].startswith("NO EDGE")
    assert per["e"]["recorded_minus_random"]["p_holm"] == 0.06 and per["e"]["verdict"].startswith("NO EDGE")
    assert per["d"]["verdict"] == "INSUFFICIENT SAMPLE"                           # 29 < MIN_N, however good
