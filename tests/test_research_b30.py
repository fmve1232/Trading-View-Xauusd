"""B30 (research/registrations/B30.json): the confirmation, lifecycle and exits on hand-built 15m paths, worked by hand.
P0 = 4000, so the scale s = 1 and every distance is in plain $."""
import numpy as np
import pandas as pd
import pytest

from quantum.research import b19, b30
from quantum.research import harness as H

N = 400
J0 = 40                                   # the first 15m bar after the trigger close


def _path(edits: dict[int, tuple[float, float, float, float]]):
    idx = pd.date_range("2023-03-01 00:00", periods=N, freq="15min", tz="UTC")
    o = np.full(N, 4000.0)
    h, l, c = o + 0.5, o - 0.5, o.copy()
    for j, (oo, hh, ll, cc) in edits.items():
        o[j], h[j], l[j], c[j] = oo, hh, ll, cc
    df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 0.0}, index=idx)
    P = b19.make_path(df)
    trig = [{"tf": "15m", "kind": "ENG", "i": J0 - 1, "t_close": int(idx[J0].timestamp()), "dir": 1, "p0": 4000.0,
             "sl_eng": 3990.0, "tp1_eng": 4020.0}]
    return P, b19.attach(trig, P)


def _one(P, A, X, plan="G1"):
    res = b30.run_model(P, A, X, plan)
    return res, (res["T"]["outcome"][0] if len(res["idx"]) else None)


def test_baseline_tp1_then_tp2_is_16_50_before_cost():
    P, A = _path({J0: (4000, 4013.5, 4000.5, 4012), J0 + 1: (4012, 4020.5, 4011, 4020)})   # TP1, then TP2 next bar
    res, out = _one(P, A, 0.0)
    cost = res["cost"][0]
    assert out == "TP1+TP2"
    assert res["T"]["net"][0] == pytest.approx(0.5 * 13 + 0.5 * 20 - cost)
    assert res["T"]["r"][0] == pytest.approx((16.5 - cost) / (13 + cost))
    assert res["delay"][0] == 0.0


def test_a_bar_touching_stop_and_tp1_is_ambiguous_and_scored_as_the_stop():
    P, A = _path({J0 + 2: (4000, 4013.5, 3986.5, 4000)})
    res, out = _one(P, A, 0.0)
    assert out == "AMBIGUOUS"
    assert res["T"]["net"][0] == pytest.approx(-13 - res["cost"][0]) and res["T"]["r"][0] == pytest.approx(-1.0)
    st = b30.stats(res)
    assert st["ambiguous"]["k"] == 1 and st["tp1_first"]["k"] == 0 and st["sl_first"]["k"] == 0


def test_tp1_bar_reaching_back_to_entry_scores_the_second_half_at_entry():
    P, A = _path({J0 + 1: (4000, 4013.5, 3999.5, 4012),          # TP1 and the moved stop in one bar: order unknown
                  J0 + 2: (4012, 4020.5, 4011, 4020)})           # TP2 on the next bar does not undo it
    res, out = _one(P, A, 0.0)
    assert out == "TP1+BE" and res["T"]["net"][0] == pytest.approx(6.5 - res["cost"][0])


def test_ten_dollar_confirmation_needs_a_close_not_a_touch_and_recalculates_the_plan():
    P, A = _path({J0 + 1: (4000, 4012, 4001, 4008),               # touches +10, closes +8: not confirmed
                  J0 + 2: (4008, 4011.5, 4007, 4011),             # first close +10 or more -> entry 4011
                  J0 + 5: (4011, 4024.5, 4012, 4024),             # TP1 = 4011 + 13 = 4024 from the ACTUAL entry
                  J0 + 6: (4024, 4031.5, 4025, 4031)})            # TP2 = 4011 + 20 = 4031
    res, out = _one(P, A, 10.0)
    C = res["C"]
    assert C["touch10"][0] == 1 and C["status"][0] == "CONFIRMED" and C["k"][0] == J0 + 2
    assert res["T"]["outcome"][0] == "TP1+TP2" and out == "TP1+TP2"
    assert res["T"]["net"][0] == pytest.approx(0.5 * 13 + 0.5 * 20 - res["cost"][0])   # +13 / +20 from 4011, not from P0
    assert res["delay"][0] == pytest.approx(45.0)                 # three 15m bars after the trigger close
    c15 = b30.run_model(P, A, 15.0)["C"]
    assert c15["status"][0] == "CONFIRMED" and c15["k"][0] == J0 + 5     # $15 needs the later close (4024)


def test_thirteen_against_first_invalidates_before_confirmation():
    P, A = _path({J0 + 1: (4000, 4001, 3986.9, 3990), J0 + 4: (3990, 4016, 3990, 4015)})
    res, _ = _one(P, A, 10.0)
    assert res["C"]["status"][0] == "INVALIDATED" and res["C"]["inv_kind"][0] == "price" and not len(res["idx"])


def test_no_close_beyond_in_96_bars_expires():
    P, A = _path({})
    res, _ = _one(P, A, 15.0)
    assert res["C"]["status"][0] == "EXPIRED" and not len(res["idx"])


def test_g2_rejects_when_too_little_reward_remains_after_confirmation():
    """Engine levels fixed at the trigger: stop 3990, TP1 4020. Entered at the trigger: 20 of reward for 10 of risk.
    Entered after a $10 confirmation at 4011: 9 of reward for 21 of risk -> REJECTED (net R:R < 1)."""
    P, A = _path({J0 + 2: (4000, 4011.5, 4000, 4011)})
    base = b30.run_model(P, A, 0.0, "G2")
    conf = b30.run_model(P, A, 10.0, "G2")
    assert base["execute"][0] and not conf["execute"][0] and conf["rejected"][0]


def test_validation_and_holdout_open_only_under_the_approved_registration():
    df = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]},
                      index=pd.DatetimeIndex([pd.Timestamp("2023-06-01", tz="UTC")]))
    assert len(H.partition(df, "validation", "B30")) == 1
    with pytest.raises(H.SealedPartition):
        H.partition(df, "validation", "B30-NOT-REGISTERED")
