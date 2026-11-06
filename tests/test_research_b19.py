"""B19 (research/registrations/B19.json): every rule of the two-stage study on hand-built 15m paths at $4,000 (s = 1),
so each distance is plain dollars."""
import numpy as np
import pandas as pd
import pytest

from quantum.research import b19

N, BASE, J0 = 420, 4000.0, 100


def _path():
    idx = pd.date_range("2026-03-02 00:00", periods=N, freq="15min", tz="UTC")
    df = pd.DataFrame({"open": BASE, "high": BASE + 1.0, "low": BASE - 1.0, "close": BASE, "volume": 0.0}, index=idx)
    P = b19.make_path(df)
    P.atr[:] = 4.0
    P.rsi[:] = 60.0
    P.ema20[:] = BASE - 5.0
    P.cost[:] = 0.77
    return P


def _bar(P, i, o=None, h=None, l=None, c=None):
    if o is not None:
        P.o[i] = o
    if h is not None:
        P.h[i] = h
    if l is not None:
        P.l[i] = l
    if c is not None:
        P.c[i] = c
        if i + 1 < len(P.c_prev):
            P.c_prev[i + 1] = c


def _hold_from(P, i, px):
    """Flat bars at px from bar i on (no further move)."""
    P.o[i:], P.h[i:], P.l[i:], P.c[i:] = px, px + 1.0, px - 1.0, px
    P.c_prev[i + 1:] = px


def _A(P, d=1, p0=BASE, j0=J0):
    return b19.attach([{"tf": "15m", "kind": "ENG", "i": 0, "t_close": int(P.t[j0]), "dir": d, "p0": p0, "regime": "",
                        "bull": 0.0, "bear": 0.0, "sl_eng": None, "tp1_eng": None}], P)


def test_a_touch_of_15_is_not_a_confirmation():
    P = _path()
    _bar(P, 105, h=4016.0, c=4010.0)
    C = b19.confirm(P, _A(P), "X15F0")
    assert C["reached15"][0] and C["status"][0] == "EXPIRED" and C["k"][0] == -1


def test_a_close_beyond_15_confirms_on_that_bar_and_20_needs_20():
    P = _path()
    _bar(P, 105, h=4017.0, c=4016.0)
    assert (b19.confirm(P, _A(P), "X15F0")["status"][0], b19.confirm(P, _A(P), "X15F0")["k"][0]) == ("CONFIRMED", 105)
    assert b19.confirm(P, _A(P), "X20F0")["status"][0] == "EXPIRED"


def test_price_invalidation_before_confirmation():
    P = _path()
    _bar(P, 103, l=3986.0)                                     # -14 first
    _bar(P, 105, h=4017.0, c=4016.0)
    C = b19.confirm(P, _A(P), "X15F0")
    assert (C["status"][0], C["inv_kind"][0]) == ("INVALIDATED", "price")


def test_a_bar_that_invalidates_and_closes_beyond_is_invalidated():
    P = _path()
    _bar(P, 105, h=4017.0, l=3986.0, c=4016.0)
    assert b19.confirm(P, _A(P), "X15F0")["status"][0] == "INVALIDATED"


def test_an_opposite_structure_event_invalidates():
    P = _path()
    P.dn_evt[104] = True
    _bar(P, 105, h=4017.0, c=4016.0)
    C = b19.confirm(P, _A(P), "X15F0")
    assert (C["status"][0], C["inv_kind"][0]) == ("INVALIDATED", "structure")


def _ramp(P):
    """A calm climb: 103 -> 4008, 104 -> 4013, 105 -> 4016 (beyond 15), 106 -> 4014, 107 -> 4017 (beyond 15); ranges <= 6."""
    for i, (o, h, l, c) in {103: (4000, 4009, 3999.5, 4008), 104: (4008, 4014, 4007.5, 4013), 105: (4013, 4017, 4012, 4016),
                            106: (4016, 4016.5, 4013.5, 4014), 107: (4014, 4018, 4013.5, 4017)}.items():
        _bar(P, i, o=o, h=h, l=l, c=c)


def test_f1_needs_momentum_structure_cost_and_calm_bars():
    P = _path()
    _ramp(P)
    P.up_evt[102] = True                                        # same-direction structure after the trigger
    P.rsi[105] = 50.0                                           # momentum fails at 105
    C = b19.confirm(P, _A(P), "X15F1")
    assert (C["status"][0], C["k"][0]) == ("CONFIRMED", 107)    # pending at 105, confirmed at 107 when all pass
    assert b19.confirm(P, _A(P), "X15F0")["k"][0] == 105        # F0 confirms at the first close beyond
    P.up_evt[102] = False
    assert b19.confirm(P, _A(P), "X15F1")["status"][0] == "EXPIRED"        # no structure continuation
    P.up_evt[102] = True
    P.cost[107] = 0.97                                          # off-session cost
    assert b19.confirm(P, _A(P), "X15F1")["status"][0] == "EXPIRED"
    P.cost[107] = 0.77
    _bar(P, 107, h=4030.0, l=4005.0)                            # range 25 > 2.5 x ATR 4
    assert b19.confirm(P, _A(P), "X15F1")["status"][0] == "EXPIRED"
    _bar(P, 107, o=4019.0, h=4019.5, l=4016.5)                  # gap 5 from the 4014 close > 0.5 x ATR 4
    assert b19.confirm(P, _A(P), "X15F1")["status"][0] == "EXPIRED"
    _bar(P, 107, o=4014.0, h=4018.0, l=4013.5)
    assert b19.confirm(P, _A(P), "X15F1")["k"][0] == 107
    P.ema20[107] = 4020.0                                       # a close below EMA20 fails momentum
    assert b19.confirm(P, _A(P), "X15F1")["status"][0] == "EXPIRED"


def test_sell_is_symmetric_and_the_direction_is_never_reversed():
    P = _path()
    _bar(P, 105, h=3984.0 + 1, l=3983.0, c=3984.0)              # -16 close: a SELL confirmation
    C = b19.confirm(P, _A(P, d=-1), "X15F0")
    assert (C["status"][0], C["k"][0]) == ("CONFIRMED", 105)
    P = _path()
    _bar(P, 105, h=4017.0, c=4016.0)                            # +16 against a SELL: invalidated, never a BUY
    C = b19.confirm(P, _A(P, d=-1), "X15F0")
    assert C["status"][0] == "INVALIDATED" and C["k"][0] == -1


def test_no_lookahead_later_bars_do_not_change_the_confirmation():
    P = _path()
    _bar(P, 105, h=4017.0, c=4016.0)
    a = b19.confirm(P, _A(P), "X15F0")
    _bar(P, 110, l=3900.0, c=3905.0)                            # a crash after the confirmation bar
    P.dn_evt[111] = True
    b = b19.confirm(P, _A(P), "X15F0")
    assert (a["status"][0], a["k"][0]) == (b["status"][0], b["k"][0]) == ("CONFIRMED", 105)


def _trade(P, conf="X15F0", entry="E1", stop="S13", T=20.0):
    A = _A(P)
    C = b19.confirm(P, A, conf)
    return b19.plan_and_exit(P, A, C, conf, entry, stop, T)


def _confirmed_path():
    P = _path()
    _bar(P, 105, h=4017.0, c=4016.0)
    _hold_from(P, 106, 4016.0)
    return P


def test_e1_entry_at_the_confirmation_close_and_tp_first():
    P = _confirmed_path()
    _bar(P, 108, h=4040.0, l=4010.0)                            # TP 4036 (SL 4003 untouched)
    T_ = _trade(P)
    assert T_["execute"][0] and T_["entry"][0] == 4016.0 and T_["outcome"][0] == "TP"
    assert T_["net"][0] == pytest.approx(20.0 - 0.77) and T_["r"][0] == pytest.approx((20.0 - 0.77) / 13.0)
    assert T_["hold_min"][0] == 3 * 15.0


def test_a_bar_touching_both_levels_is_ambiguous_and_a_loss():
    P = _confirmed_path()
    _bar(P, 108, h=4040.0, l=4000.0)
    T_ = _trade(P)
    assert T_["outcome"][0] == "AMBIGUOUS" and T_["net"][0] == pytest.approx(-13.0 - 0.77)


def test_gaps_fill_at_the_open_and_a_timeout_exits_at_the_close():
    P = _confirmed_path()
    _bar(P, 108, o=3990.0, h=3995.0, l=3985.0, c=3990.0)        # opens below the 4003 stop
    T_ = _trade(P)
    assert T_["outcome"][0] == "SL" and T_["net"][0] == pytest.approx(-26.0 - 0.77)
    P = _confirmed_path()
    T_ = _trade(P)
    assert T_["outcome"][0] == "TIMEOUT" and T_["net"][0] == pytest.approx(0.0 - 0.77)


def test_e2_limit_fills_on_a_retest_and_is_missed_without_one():
    P = _confirmed_path()
    _bar(P, 107, o=4016.0, h=4017.0, l=4014.0, c=4015.5)        # trades back to the 4015 threshold
    _bar(P, 110, h=4036.0, l=4014.0)                            # TP 4035 from the 4015 fill
    T_ = _trade(P, entry="E2")
    assert T_["entry"][0] == 4015.0 and T_["outcome"][0] == "TP"
    P = _confirmed_path()
    _hold_from(P, 106, 4020.0)                                  # never back to 4015 within 8 bars
    T_ = _trade(P, entry="E2")
    assert T_["missed"][0] and not T_["execute"][0]


def test_the_plan_is_rejected_without_a_favourable_risk_reward():
    P = _confirmed_path()
    P.atr[:] = 20.0                                             # SATR = 60 > 40 and 20 / 60 < 1
    T_ = _trade(P, stop="SATR")
    assert T_["rejected"][0] and not T_["execute"][0]
    P = _confirmed_path()
    _bar(P, 102, l=3988.5)                                      # structure low 3988.5 - 0.8: stop 28.3 > target 20
    T_ = _trade(P, stop="SSTR")
    assert T_["D"][0] == pytest.approx(4016.0 - (3988.5 - 0.2 * 4.0)) and T_["rejected"][0]
    T_ = _trade(P, stop="SSTR", T=30.0)
    assert T_["execute"][0]


def test_trigger_only_enters_at_the_trigger_price():
    P = _path()
    _bar(P, 103, h=4021.0, l=3999.0)
    A = _A(P)
    C = b19.confirm(P, A, "none")
    T_ = b19.plan_and_exit(P, A, C, "none", "E1", "S13", 20.0)
    assert T_["entry"][0] == BASE and T_["outcome"][0] == "TP" and T_["net"][0] == pytest.approx(20.0 - 0.77)


def test_repeat_rule_keeps_one_trigger_per_idea():
    t = 1_793_000_000
    tr = [{"tf": "15m", "t_close": t, "dir": 1, "p0": 4000.0}, {"tf": "1h", "t_close": t + 3600, "dir": 1, "p0": 4005.0},
          {"tf": "15m", "t_close": t + 3600, "dir": -1, "p0": 4005.0}, {"tf": "4h", "t_close": t + 5 * 3600, "dir": 1, "p0": 4004.0},
          {"tf": "30m", "t_close": t + 1800, "dir": 1, "p0": 4020.0}]
    kept = b19.dedupe(tr)
    assert [(x["tf"], x["dir"], x["p0"]) for x in kept] == [("15m", 1, 4000.0), ("30m", 1, 4020.0), ("15m", -1, 4005.0), ("4h", 1, 4004.0)]


def test_statistics_helpers():
    assert b19.max_drawdown(np.array([1.0, -2.0, -1.0, 3.0, -4.0])) == 4.0
    adj = b19.holm_adjusted({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adj == pytest.approx({"a": 0.03, "c": 0.06, "b": 0.06})
    assert b19.welch_p(np.array([2.0, 3.0, 4.0, 5.0]), np.array([0.0, 1.0, 0.0, 1.0])) < 0.01


def test_validation_and_holdout_stay_sealed_without_the_registration():
    from quantum.research import harness as H
    df = pd.DataFrame({"close": [1.0]}, index=pd.DatetimeIndex([pd.Timestamp("2025-01-01", tz="UTC")]))
    with pytest.raises(H.SealedPartition):
        H.partition(df, "holdout", "B19-not-registered")
    assert len(H.partition(df, "holdout", "B19")) == 1          # B19 is approved for it; the run gate is in b19.main


def test_the_holdout_run_refuses_a_configuration_that_did_not_pass_validation(tmp_path):
    vr = tmp_path / "val.json"
    vr.write_text('{"validation_pass": {"ENG X15F0 E1 S13 T20": false}}')
    with pytest.raises(SystemExit, match="passed validation"):
        b19.main(["--rd", str(tmp_path), "--part", "holdout", "--configs", "ENG X15F0 E1 S13 T20", "--out", str(tmp_path / "o.json"),
                  "--val-results", str(vr)])
    with pytest.raises(SystemExit, match="declared configurations"):
        b19.main(["--rd", str(tmp_path), "--part", "validation", "--out", str(tmp_path / "o.json")])
