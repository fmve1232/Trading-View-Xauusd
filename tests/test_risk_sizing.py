"""N1 (operator, 2026-11-14: "Use 2.6% of $25,000"). The phone plan's lot comes from a fixed risk budget that holds AFTER
costs; the price geometry ($13 stop, $13 TP1, $20 TP2) is unchanged, so B15 / B9 count exactly the same plans. Values are
worked by hand: lot = floor(budget / ((stop + cost/oz) x 100 oz) / step) x step, cost = the higher of the operator's $0.26
and the research model's $0.97, step 0.02 with two targets (two equal halves), 0.01 with one."""
import pytest

from quantum import notify as N
from tests.test_alert_sixty import T, _pay, _sig

KEYS = ("PLAN", "PLAN_LOT", "PLAN_SL_USD", "PLAN_TP_USD", "PLAN_TP2_USD", "PLAN_COST_PER_LOT", "PLAN_RISK_PCT", "ACCOUNT_USD",
        "PLAN_SIZING", "PLAN_LOT_MAX", "DAILY_LIMIT_PCT", "ALERT_MODE", "ALERT_STRUCTURE")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)


def test_default_is_2_6_percent_of_25000_after_costs():
    pl = N.plan_cfg()
    # budget 25,000 x 2.6% = 650; per lot (13 + 0.97) x 100 = 1,397; 650 / 1,397 = 0.465 -> 0.46 (0.02 steps)
    assert pl["sizing"] == "risk" and pl["budget"] == pytest.approx(650.0) and pl["size_cost_oz"] == pytest.approx(0.97)
    assert pl["lot"] == pytest.approx(0.46)
    assert (pl["sl_px"], pl["tp_px"], pl["tp2_px"]) == pytest.approx((13.0, 13.0, 20.0))          # geometry unchanged
    assert (pl["sl_usd"], pl["tp_usd"], pl["tp2_usd"]) == pytest.approx((598.0, 598.0, 920.0))
    assert pl["loss_at_stop_max"] == pytest.approx(0.46 * 1397) and pl["loss_at_stop_max"] <= 650.0
    assert pl["risk_pct_actual"] == pytest.approx(100 * 642.62 / 25000) and not pl["over_budget"]


def test_the_alert_lines_follow_the_size():
    pl = N.plan_cfg()
    assert N.plan_line(4300.0, -1, pl).startswith("YOUR PLAN 0.46 lot: SL 4313.00 (-$598) | TP1 4287.00: close half (+$299)")
    assert N.sizing_line(pl) == ("SIZE: 0.46 lot = risk budget 2.6% of $25,000 ($650); loss at the stop incl. cost up to $643 "
                                 "= 2.57% (sized at $0.97/oz, the higher of your cost and the research model)")
    assert "2 x 0.23 lot at market" in N.mt5_line(-1, pl) and "(= -$598 total / +$299 then +$460" in N.mt5_line(-1, pl)
    assert N.ladder_line(pl).endswith("2 stops in a day = -$1,220 (4.9% of $25,000): inside a 5% daily limit")   # 2 x (598 + 11.96)


@pytest.mark.parametrize("pct, acct, lot", [("1", "25000", 0.16),       # 250 / 1,397 = 0.179 -> 0.16 (0.02 steps)
                                            ("2.6", "100000", 1.86),    # 2,600 / 1,397 = 1.861 -> 1.86
                                            ("0.5", "10000", 0.02)])    # 50 / 1,397 = 0.036 -> 0.02
def test_budget_and_account_drive_the_lot(monkeypatch, pct, acct, lot):
    monkeypatch.setenv("PLAN_RISK_PCT", pct)
    monkeypatch.setenv("ACCOUNT_USD", acct)
    assert N.plan_cfg()["lot"] == pytest.approx(lot)


def test_one_target_sizes_in_0_01_steps(monkeypatch):
    monkeypatch.setenv("PLAN_TP2_USD", "0")
    assert N.plan_cfg()["lot"] == pytest.approx(0.46)                   # floor(0.4653 / 0.01) = 46
    monkeypatch.setenv("PLAN_RISK_PCT", "1")
    assert N.plan_cfg()["lot"] == pytest.approx(0.17)                   # 250 / 1,397 = 0.179 -> 0.17


def test_the_higher_cost_is_used_for_sizing(monkeypatch):
    monkeypatch.setenv("PLAN_COST_PER_LOT", "150")                      # $1.50/oz > the model's $0.97
    pl = N.plan_cfg()
    assert pl["size_cost_oz"] == pytest.approx(1.50) and pl["lot"] == pytest.approx(0.44)   # 650 / 1,450 = 0.448 -> 0.44


def test_below_the_minimum_is_no_trade(monkeypatch):
    monkeypatch.setenv("ACCOUNT_USD", "500")                            # budget $13: far below 0.02 lot x $1,397
    pl = N.plan_cfg()
    assert pl["lot"] == pytest.approx(0.02) and pl["over_budget"] is True
    assert N.sizing_line(pl).startswith("NO TRADE at this size: SIZE: 0.02 lot = risk budget 2.6% of $500 ($13)")
    assert N.sizing_line(pl).endswith("-- the minimum lot exceeds the budget")


def test_the_cap_and_the_fixed_mode(monkeypatch):
    monkeypatch.setenv("ACCOUNT_USD", "10000000")
    monkeypatch.setenv("PLAN_LOT_MAX", "5")
    assert N.plan_cfg()["lot"] == pytest.approx(5.0)
    monkeypatch.setenv("PLAN_SIZING", "fixed")
    monkeypatch.setenv("ACCOUNT_USD", "25000")
    pl = N.plan_cfg()
    assert pl["lot"] == 0.5 and pl["sl_usd"] == pytest.approx(650.0) and pl["sizing"] == "fixed"
    assert N.sizing_line(pl).startswith("SIZE: fixed 0.5 lot (PLAN_SIZING=fixed): loss at the stop up to $698 = 2.79%")   # 0.5 x 1,397


def test_a_real_alert_carries_the_size_and_b15_still_counts_the_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("ALERT_MODE", "sixty")
    sent = []
    monkeypatch.setattr(N, "send", lambda lines: sent.append(N.without_disclaimer(lines)) or ["test"] if lines else [])
    store = str(tmp_path)
    N.run(store, {"15m": _pay("15m", T - 900)}, ["15m"], sent_t=T)
    rep = N.run(store, {"15m": _pay("15m", T + 2700, [_sig(T + 2700, 3906.34, -1)])}, ["15m"], sent_t=T + 3600 + 300)
    flat = [x for b in sent for x in b]
    assert any(x.startswith("SIZE: 0.46 lot = risk budget 2.6% of $25,000") for x in flat)
    plan = rep["plans"]["open"][0]
    assert plan["lot"] == pytest.approx(0.46) and abs(plan["entry"] - plan["sl"]) == pytest.approx(13.0)
    trades, excluded = N.eng_trades([{**plan, "result": "SL", "t_res": T + 9000}], 0)
    assert len(trades) == 1 and excluded == 0                           # B15 counts it: $13 of price, whatever the lot
