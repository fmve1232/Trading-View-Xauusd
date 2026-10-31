"""Audit 2026-10-31 R-01 / D-13: lot sizing for XAUUSD (100 oz per lot, 0.01 lot step) includes the round-trip cost."""
import math

import pytest

from quantum import report
from quantum.config import DEFAULT


def _last(dist, long_=True):
    # no ROLL history: Kelly falls back to the configured risk % (1%)
    return {"analog": {}, "oos_neff": 0, "oos_bear_wr": math.nan, "plan": {"dist": dist, "long": long_}}


def test_lots_by_hand_with_costs():
    # $10,000 x 1% = $100. Stop 6.00 + cost 0.77 = 6.77 per oz -> $677 per lot -> 0.1477 -> 0.14 lot
    k = report.kelly(_last(6.0), DEFAULT, 30, 1.0, cost_pts=0.77)
    assert k["kelly_pct"] == pytest.approx(1.0) and k["risk_usd"] == pytest.approx(100.0)
    assert k["risk_per_lot"] == pytest.approx(677.0)
    assert k["lots"] == pytest.approx(0.14)
    assert k["lots"] * k["risk_per_lot"] <= k["risk_usd"] + 1e-9           # the loss at the stop stays inside the risk


def test_without_cost_matches_the_pine_formula():
    k = report.kelly(_last(5.0), DEFAULT, 30, 1.0)
    assert k["risk_per_lot"] == pytest.approx(500.0) and k["lots"] == pytest.approx(0.20)   # exact multiple: no float floor loss


def test_regime_haircut_minimum_lot_and_cap():
    k = report.kelly(_last(6.0), DEFAULT, 30, 0.5, cost_pts=0.77)
    assert k["kelly_pct"] == pytest.approx(0.5) and k["lots"] == pytest.approx(0.07)
    tiny = report.kelly(_last(150.0), DEFAULT, 30, 1.0, cost_pts=0.8)      # $100 / $15,080 per lot < 0.01
    assert tiny["lots"] == 0.0 and tiny["below_min"]
    assert report.kelly(_last(0.0), DEFAULT, 30, 1.0, cost_pts=0.8)["lots"] == 0.0
    assert report.kelly(_last(6.0), DEFAULT, 30, 1.0, cost_pts=math.nan)["cost_pts"] == 0.0
