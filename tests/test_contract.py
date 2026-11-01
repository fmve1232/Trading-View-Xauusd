"""Broker contract arithmetic (quantum/contract.py). Brief section 13 tests 8-11 and 28: contract specification,
lot size, tick value, SL / TP conversion, account currency."""
import math

import pytest

from quantum import contract as C

STD = dict(C.DEFAULT_SPEC)


def test_standard_contract_is_valid_and_labelled_unverified():
    v = C.validate(STD)
    assert v["ok"] and not v["errors"] and STD["status"] == "UNVERIFIED"
    assert C.money_per_price(STD, 1.0) == pytest.approx(100.0)      # $1 of price = $100 per lot on 100 oz


@pytest.mark.parametrize("change, msg", [
    ({"contract_size": 0}, "contract_size"),
    ({"tick_size": -0.01}, "tick_size"),
    ({"tick_value": float("nan")}, "tick_value"),
    ({"tick_value": 2.0}, "does not match"),                         # a USD account cannot have $2 per 0.01 on 100 oz
    ({"pip_size": 0.001}, "pip_size cannot be smaller"),
    ({"account_currency": "US"}, "3-letter"),
])
def test_incorrect_specifications_are_rejected(change, msg):
    v = C.validate({**STD, **change})
    assert not v["ok"] and any(msg in e for e in v["errors"])


def test_operator_scenario_d_on_a_standard_contract():
    # $1,000 at 0.50 lot on 100 oz is a $20 move: 200 pips at 0.10, 2,000 points at 0.01. Not $10-15.
    move = C.money_to_price(STD, 1000.0, 0.5)
    assert move == pytest.approx(20.0)
    assert C.to_pips(STD, move) == pytest.approx(200.0) and C.to_points(STD, move) == pytest.approx(2000.0)
    assert C.price_to_money(STD, 10.0, 0.5) == pytest.approx(500.0)   # a $10 move pays $500 at 0.5 lot
    one_pip_broker = {**STD, "pip_size": 0.01}
    assert C.to_pips(one_pip_broker, 10.0) == pytest.approx(1000.0)   # the same $10 is 1,000 "pips" there


def test_tick_value_drives_the_money_whatever_the_contract():
    small = {**STD, "contract_size": 50.0, "tick_value": 0.5}
    assert C.validate(small)["ok"]
    assert C.money_per_price(small, 0.5) == pytest.approx(25.0)
    assert C.money_to_price(small, 1000.0, 0.5) == pytest.approx(40.0)


def test_non_usd_account_uses_mt5_tick_value_and_warns():
    eur = {**STD, "account_currency": "EUR", "tick_value": 0.86}      # MT5 shows the tick value in EUR
    v = C.validate(eur)
    assert v["ok"] and any("EUR" in w for w in v["warnings"])
    assert C.price_to_money(eur, 10.0, 1.0) == pytest.approx(860.0)


def test_lots_for_risk_include_costs_and_respect_the_step():
    # $1,000 risk, $10 stop, $0.97 per 1.00 of costs: (10.97 x 100) per lot -> 0.91 lot
    assert C.lots_for_risk(STD, 1000.0, 10.0, 0.97) == pytest.approx(0.91)
    assert C.lots_for_risk(STD, 5.0, 10.0, 0.97) == 0.0                # below the minimum lot
    assert C.lots_for_risk(STD, 1000.0, 0.0, 0.0) == 0.0
    assert C.lots_for_risk({**STD, "volume_step": 0.1, "volume_min": 0.1}, 1000.0, 10.0, 0.97) == pytest.approx(0.9)


def test_trade_money_and_break_even():
    m = C.trade_money(STD, 0.5, 10.0, 10.0, 0.97)
    assert m["gross_tp"] == pytest.approx(500.0) and m["gross_sl"] == pytest.approx(-500.0)
    assert m["cost"] == pytest.approx(48.5) and m["net_tp"] == pytest.approx(451.5) and m["net_sl"] == pytest.approx(-548.5)
    assert m["break_even"] == pytest.approx(10.97 / 20.0)
    assert m["tp_pips"] == pytest.approx(100.0) and m["sl_points"] == pytest.approx(1000.0)
    assert math.isnan(C.trade_money(STD, 0.5, 0.0, 0.0, 0.97)["break_even"])
