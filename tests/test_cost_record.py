"""IA-06 (audit 2026-11-14): the phone's plan used $0.26/oz round trip, the research and the engine $0.77-0.97/oz, and
neither is broker-verified. One definition of each (notify), and every plan break-even shows both. Expected values are
worked by hand: break-even = (SL$ + cost/oz x lot x 100) / (SL$ + TP$)."""
import os

import pytest

from quantum import confirm_panel as C
from quantum import fwd_b24 as B
from quantum import notify as N
from tests.test_alert_sixty import T, _pay, _sig

NOTE = "at your $0.26/oz cost (53%-54% at the research cost model $0.77-0.97/oz; neither broker-verified)"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("PLAN", "PLAN_LOT", "PLAN_SL_USD", "PLAN_TP_USD", "PLAN_COST_PER_LOT", "PLAN_TP2_USD", "ALERT_MODE"):
        monkeypatch.delenv(k, raising=False)


def test_break_even_by_hand():
    pl = N.plan_cfg()                                   # 0.5 lot, SL $650, TP $650
    assert N.break_even_at(pl, 0.26) == pytest.approx((650 + 13.0) / 1300)      # 51.0%
    assert N.break_even_at(pl, 0.77) == pytest.approx((650 + 38.5) / 1300)      # 52.96%
    assert N.break_even_at(pl, 0.97) == pytest.approx((650 + 48.5) / 1300)      # 53.73%


@pytest.mark.parametrize("tp2", ["", "0"])
def test_both_plan_lines_show_both_costs(monkeypatch, tp2):
    monkeypatch.setenv("PLAN_TP2_USD", tp2)
    line = N.plan_line(4300.0, -1, N.plan_cfg())
    assert ("break-even 51% TP1 first " + NOTE if not tp2 else "break-even 51% " + NOTE) in line


def test_the_operator_cost_follows_the_setting(monkeypatch):
    monkeypatch.setenv("PLAN_COST_PER_LOT", "40")
    line = N.plan_line(4300.0, 1, N.plan_cfg())
    assert "break-even 52% TP1 first at your $0.40/oz cost (53%-54% at the research cost model" in line   # (650+20)/1300


def test_one_definition_of_each_cost():
    assert C.OP_COST == N.PLAN_COST_PER_LOT_DEFAULT / 100.0 == 0.26
    assert C.MODEL_COST is N.COST_MODEL_OZ and N.COST_MODEL_OZ == (0.77, 0.97)
    assert B.OP_COST == C.OP_COST                     # B24 keeps its registered constant; it must agree


def test_the_website_block_carries_both(tmp_path, monkeypatch):
    monkeypatch.setattr(N, "send", lambda lines: ["test"] if lines else [])
    store = str(tmp_path)
    N.run(store, {"15m": _pay("15m", T - 900)}, ["15m"], sent_t=T)
    rep = N.run(store, {"15m": _pay("15m", T + 2700, [_sig(T + 2700, 3906.34, -1)])}, ["15m"], sent_t=T + 3600 + 300)
    P = rep["plans"]
    assert P["break_even"] == pytest.approx(0.51) and P["cost_oz"] == pytest.approx(0.26)
    assert P["cost_model_oz"] == [0.77, 0.97] and P["break_even_model"] == pytest.approx([688.5 / 1300, 698.5 / 1300])


def test_the_site_row_says_neither_is_verified():
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site", "app.js")) as f:
        js = f.read()
    row = js[js.index("<div>Break-even after costs</div><div>${pct(100 * P.break_even)}"):].split("\n", 1)[0]
    assert "P.break_even_model" in row and "research cost model" in row and "neither broker-verified" in row
