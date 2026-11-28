"""quantum/research/g5_sens.py (G5-SENS + A1): the cell plan equals the registration, configuration copies never touch
the frozen defaults, H4 constants are restored, and the measurements are worked by hand. No research data needed."""
import json
import os

import numpy as np
import pandas as pd
import pytest

from quantum import arm_h4, config
from quantum.research import g5_sens as G

REG = os.path.join(os.path.dirname(__file__), "..", "research", "registrations", "G5-SENS.json")


def test_the_plan_is_the_registered_one():
    with open(REG) as f:
        reg = json.load(f)
    p = reg["parameters"]
    assert G.ENGINE == p["engine (config.py; affects both arms)"] and G.H4 == p["h4 (module constants; H4 only)"]
    assert G.COST == next(iter(p["cost of record (both arms; not a strategy parameter)"].values()))
    cells = G.plan()
    assert len(cells) == 144 and list(G.TFS) == reg["timeframes"]
    assert sum(c["group"] == "frozen" for c in cells) == 6
    assert not any(c["arm"] == "treatment" and c["group"] == "h4" for c in cells)
    assert reg["amendments"][0]["id"] == "A1"


def test_configuration_copies_leave_the_frozen_defaults_alone():
    before = config.DEFAULT
    c = G.cfg_for({"group": "engine", "param": "atr_len", "value": 20})
    assert c.atr_len == 20 and config.DEFAULT.atr_len == 14 and config.DEFAULT is before
    k = G.cfg_for({"group": "cost", "param": "cost_mult", "value": 2.0})
    assert (k.spread_cost, k.slippage_pts, k.commission_l) == (0.6, 0.4, 14.0) and config.DEFAULT.spread_cost == 0.3
    assert G.cfg_for({"group": "frozen", "param": None, "value": None}) is config.DEFAULT


def test_h4_constants_are_restored_even_after_an_error():
    with pytest.raises(RuntimeError), G.h4_constants({"GAP_ATR": 0.2, "MIN_TP_R": 1.5}):
        assert arm_h4.GAP_ATR == 0.2
        raise RuntimeError
    assert arm_h4.GAP_ATR == 0.1 and arm_h4.MIN_TP_R == 1.0


def _p5(rows, start="2022-06-01T10:00:00Z"):
    t = pd.date_range(start, periods=len(rows), freq="5min", tz="UTC").as_unit("s").asi8
    a = np.array(rows, float)
    return {"t": t, "o": a[:, 0], "h": a[:, 1], "l": a[:, 2]}


def test_target_races_by_hand():
    # entry 2000 (scale 0.5): +$10 -> 2005, +$15 -> 2007.5, +$20 -> 2010; stop 1995
    P5 = _p5([(2000, 2003, 1998), (2003, 2006, 2002), (2006, 2008, 2004), (2008, 2008, 1994)])
    t = {"dir": "LONG", "entry_time": "2022-06-01T09:45:00+00:00", "entry": 2000.0, "sl": 1995.0}
    out = G.races([t], 900, P5)
    assert out["usd10"]["target"] == 1 and out["usd15"]["target"] == 1 and out["usd20"]["stop"] == 1
    early = {**t, "entry_time": "2022-06-01T08:00:00+00:00"}                 # fill before the 5m coverage
    assert G.races([early], 900, P5)["excluded_before_5m_coverage"] == 1
    short = {"dir": "SHORT", "entry_time": "2022-06-01T09:45:00+00:00", "entry": 2000.0, "sl": 2004.0}
    assert G.races([short], 900, P5)["usd10"]["stop"] == 1                    # 2006 high hits the stop first


def test_holm_and_bh_by_hand():
    assert G.holm([0.01, 0.04, 0.03]) == [0.03, 0.06, 0.06]
    assert G.bh([0.01, 0.04, 0.03]) == [0.03, 0.04, 0.04]


def _cell(tf, arm, group, param, value, mean, ci, n=100):
    return {"tf": tf, "arm": arm, "group": group, "param": param, "value": value,
            "m": {"n": n, "mean_net_r": mean, "mean_net_r_day_boot95": ci}}


def test_fragility_shapes_by_hand():
    f = _cell("15m", "treatment", "frozen", None, None, 0.10, [0.05, 0.15])
    plateau = [_cell("15m", "treatment", "engine", "atr_len", 10, 0.08, [0.03, 0.13]),
               _cell("15m", "treatment", "engine", "atr_len", 20, 0.12, [0.07, 0.17])]
    peak = [_cell("15m", "treatment", "engine", "struct_window", 5, -0.10, [-0.2, 0.0]),
            _cell("15m", "treatment", "engine", "struct_window", 12, 0.01, [-0.05, 0.04])]
    out = {(x["param"]): x for x in G.fragility([f, *plateau, *peak])}
    assert out["atr_len"]["shape"] == "PLATEAU" and out["atr_len"]["sign_stable"] and out["atr_len"]["frozen_rank"] == 2
    assert out["struct_window"]["shape"] == "PEAK" and out["struct_window"]["sign_stable"] is False
    assert out["struct_window"]["max_abs_change_mean_net_r"] == 0.2 and out["struct_window"]["intervals_overlap_frozen"] is False


def test_metrics_by_hand():
    P5 = _p5([(2000, 2001, 1999)] * 10)
    tr = [{"dir": "LONG", "entry_time": "2022-06-01T09:45:00+00:00", "exit_time": "2022-06-01T11:00:00+00:00", "entry": 2000.0,
           "sl": 1990.0, "r": 1.0, "gross_pts": 10.5, "pts": 10.0, "cost_pts": 0.5, "regime": "TREND", "session": "LONDON", "open": False},
          {"dir": "LONG", "entry_time": "2022-06-02T09:45:00+00:00", "exit_time": "2022-06-02T11:00:00+00:00", "entry": 2000.0,
           "sl": 1990.0, "r": -1.05, "gross_pts": -10.0, "pts": -10.5, "cost_pts": 0.5, "regime": "RANGE", "session": "LONDON", "open": False}]
    m = G.metrics(tr, 900, P5, np.random.default_rng(0))
    assert m["n"] == 2 and m["mean_net_r"] == -0.025 and m["mean_gross_r"] == 0.025 and m["win_rate"] == 0.5
    assert m["max_dd_r"] == 1.05 and m["pf"] == round(10 / 10.5, 4) and m["share_at_or_below_minus_1r"] == 0.5
    assert m["by"]["regime"] == {"RANGE": {"n": 1, "mean_net_r": -1.05}, "TREND": {"n": 1, "mean_net_r": 1.0}}
    rp = G.repriced(tr, 2.0)
    assert rp["mean_net_r"] == round(((10.5 - 1.0) / 10 + (-10.0 - 1.0) / 10) / 2, 4)


def test_the_results_document_is_what_the_run_file_gives():
    """research/G5_SENS_RESULTS.md is generated from research/G5_SENS_RESULTS.json (audit/tools/g5_sens_doc.py)."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "audit", "tools"))
    import g5_sens_doc
    assert g5_sens_doc.main(["--check"]) == 0
    with open(os.path.join(os.path.dirname(__file__), "..", "research", "G5_SENS_RESULTS.json")) as f:
        run = json.load(f)
    assert run["cells_run"] == run["cells_planned"] == 144 and not run["feasibility_only"]
