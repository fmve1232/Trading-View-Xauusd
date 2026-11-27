"""G5-SENS (research/registrations/G5-SENS.json), written before any of its code: development partition only, one
parameter at a time around the FROZEN values, and the frozen values are those of config.py and arm_h4.py."""
import json
import os

import pandas as pd
import pytest

from quantum import arm_h4, config
from quantum.research import harness

REG = os.path.join(os.path.dirname(__file__), "..", "research", "registrations", "G5-SENS.json")


def _reg():
    with open(REG) as f:
        return json.load(f)


def test_development_only_and_no_decision():
    r = _reg()
    assert r["partitions"] == ["development"] and r["decision"].startswith("NONE")
    df = pd.DataFrame({"close": [1.0, 2.0]}, index=pd.DatetimeIndex(["2023-06-01", "2025-01-01"], tz="UTC"))
    for name in ("validation", "holdout"):
        with pytest.raises(harness.SealedPartition):
            harness.partition(df, name, "G5-SENS")


def test_the_middle_value_of_every_list_is_the_frozen_value():
    p = _reg()["parameters"]
    cfg = config.Config()
    for name, vals in p["engine (config.py; affects both arms)"].items():
        assert vals[len(vals) // 2] == getattr(cfg, name), name
        assert vals == sorted(vals) and len(set(vals)) == len(vals)
    for name, vals in p["h4 (module constants; H4 only)"].items():
        assert vals[len(vals) // 2] == getattr(arm_h4, name), name
    assert 1.0 in p["cost of record (both arms; not a strategy parameter)"][
        "cost multiplier on spread_cost, slippage_pts and commission_l together"]


def test_the_declared_cell_count_matches_the_lists():
    p = _reg()["parameters"]
    eng = sum(len(v) - 1 for v in p["engine (config.py; affects both arms)"].values())
    h4 = sum(len(v) - 1 for v in p["h4 (module constants; H4 only)"].values())
    cost = len(next(iter(p["cost of record (both arms; not a strategy parameter)"].values()))) - 1
    per_tf = (eng + cost + 1) + (eng + h4 + cost + 1)
    assert per_tf * len(_reg()["timeframes"]) == 144
