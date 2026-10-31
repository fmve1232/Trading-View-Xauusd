"""Per-account cost profiles (display-only sizing). The engine profile must equal the frozen cost model exactly."""
import math

import pytest

from quantum import cost_profiles as cp
from quantum import holdout
from quantum.config import DEFAULT

P = {p["id"]: p for p in cp.PROFILES}


def test_engine_profile_is_the_frozen_cost_model():
    e = P["engine"]
    assert e["commission"]["rate"] == DEFAULT.commission_l and e["slippage"] == DEFAULT.slippage_pts
    assert e["commission"]["basis"] == "round_turn" and DEFAULT.point_value == cp.CONTRACT_OZ
    for spread in (0.30, 0.50):                                  # in-session / off-session session spread
        want = spread + 2.0 * DEFAULT.slippage_pts + DEFAULT.commission_l / DEFAULT.point_value
        assert cp.round_trip_cost_per_oz(e, 4000.0, spread) == pytest.approx(want)
    assert cp.round_trip_cost_per_oz(e, 4000.0, 0.30) == pytest.approx(0.77)


def test_fixed_and_percentage_commission_by_hand():
    assert cp.commission_per_lot(P["fp_standard"], 4000.0) == pytest.approx(10.0)          # unconfirmed -> per side (higher)
    assert cp.commission_per_lot(P["fp_standard"], 4000.0, conservative=False) == pytest.approx(5.0)
    # FundedNext's own worked example: 1 lot XAUUSD at 4466.22 x 100 oz x 0.0016% = 7.1459 per side
    one_side = 100 * 4466.22 * 0.0016 / 100
    assert one_side == pytest.approx(7.1459, abs=1e-4)
    assert cp.commission_per_lot(P["fn_stellar_2step"], 4466.22) == pytest.approx(2 * one_side)
    assert cp.commission_per_lot(P["fn_stellar_instant"], 4466.22) == pytest.approx(one_side)    # open only
    assert cp.commission_per_lot(P["fn_stellar_lite"], 4000.0) == pytest.approx(2 * 100 * 4000 * 0.0018 / 100)
    assert math.isnan(cp.commission_per_lot(P["fn_stellar_lite"], float("nan")))


def test_no_double_counting_and_fixed_spread_override():
    p = dict(P["custom"], spread={"mode": "fixed", "value": 0.25}, slippage=0.1, commission={"type": "fixed", "rate": 6.0, "basis": "round_turn"})
    assert cp.round_trip_cost_per_oz(p, 4000.0, engine_spread=9.99) == pytest.approx(0.25 + 0.2 + 0.06)


def test_nothing_is_marked_verified_and_profiles_stay_outside_the_freeze_key():
    assert {p["status"] for p in cp.PROFILES} <= {"FROZEN", "UNVERIFIED", "USER"}
    assert all(p["commission"]["basis"] in cp.BASES and p["source"] for p in cp.PROFILES)
    assert "cost_profiles.py" not in holdout.ENGINE_SOURCES
    ids = [p["id"] for p in cp.PROFILES]
    assert len(ids) == len(set(ids)) and ids[0] == "engine"
