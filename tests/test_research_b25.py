"""B25 (research/registrations/B25.json): every entry model and exit mode, written against the registered rule text."""
import numpy as np
import pandas as pd
import pytest

from quantum import ta
from quantum.research import b25

T0 = 1700000100 - 1700000100 % 900


def bars(rows, sec=900, up=(), dn=()):
    n = len(rows)
    a = np.array(rows, float)
    u, d = np.zeros(n, bool), np.zeros(n, bool)
    u[list(up)] = True
    d[list(dn)] = True
    return b25.Bars(np.arange(n, dtype=np.int64) * sec + T0, a[:, 0], a[:, 1], a[:, 2], a[:, 3], u, d, np.full(n, 0.8), sec)


FLAT = (4000.0, 4002.0, 3998.0, 4000.0)


# ---------------- exits ----------------
def test_exit_close_mode_gap_fills_at_the_open():
    B = bars([FLAT, (3980.0, 3985.0, 3978.0, 3982.0)])
    assert b25.exit_from(B, 1, 4000.0, 1, 15.0, 1.0, 5, "close")[:2] == ("SL", 3980.0)


def test_exit_open_mode_ignores_the_entry_bars_open_and_counts_both_levels_as_the_stop():
    B = bars([FLAT, (4000.0, 4016.0, 3986.0, 4001.0)])            # entered at this open; touches +15 and -13
    out = b25.exit_from(B, 1, 4000.0, 1, 15.0, 1.0, 5, "open")
    assert out[0] == "AMBIGUOUS" and out[1] == pytest.approx(3987.0)


def test_exit_fill_mode_credits_only_the_stop_in_the_fill_bar():
    B = bars([FLAT, (4000.0, 4031.0, 4005.0, 4029.0), (4029.0, 4031.0, 4025.0, 4030.0)])
    out = b25.exit_from(B, 1, 4015.0, 1, 15.0, 1.0, 5, "fill")     # the fill bar reaches 4031 (+16): not credited
    assert out[0] == "TP" and out[1] == pytest.approx(4030.0)       # ... the next bar's high is the target
    B2 = bars([FLAT, (4000.0, 4016.0, 3986.0, 4010.0)])
    assert b25.exit_from(B2, 1, 4015.0, 1, 15.0, 1.0, 5, "fill")[0] == "SL"   # the fill bar touches entry - 13: stopped


def test_exit_timeout_at_the_last_close():
    B = bars([FLAT] * 6)
    out = b25.exit_from(B, 1, 4000.0, 1, 15.0, 1.0, 4, "close")
    assert out[0] == "TIMEOUT" and out[1] == 4000.0
    assert b25.exit_from(B, 1, 4000.0, 1, 15.0, 1.0, 9, "close")[0] == "OPEN"


# ---------------- the stop order (model E) ----------------
def test_stop_order_cases():
    gap = bars([FLAT, (4017.0, 4020.0, 4016.0, 4018.0)])
    assert b25.stop_order(gap, 1, 4000.0, 1, 1.0, 10)[:4] == ("FILLED", 1, 4017.0, "gap")
    touch = bars([FLAT, (4000.0, 4016.0, 3999.0, 4010.0)])
    assert b25.stop_order(touch, 1, 4000.0, 1, 1.0, 10)[:4] == ("FILLED", 1, 4015.0, "touch")
    both = bars([FLAT, (4000.0, 4016.0, 3986.0, 4010.0)])
    st = b25.stop_order(both, 1, 4000.0, 1, 1.0, 10)
    assert st[3] == "touch+invalid" and b25.exit_from(both, 1, st[2], 1, 15.0, 1.0, 5, "fill")[0] == "SL"   # the worst case
    gap_against = bars([FLAT, (3985.0, 4020.0, 3984.0, 4010.0)])
    assert b25.stop_order(gap_against, 1, 4000.0, 1, 1.0, 10)[0] == "INVALIDATED"
    struct = bars([FLAT, (4000.0, 4010.0, 3995.0, 4005.0), (4005.0, 4020.0, 4004.0, 4016.0)], dn=[1])
    assert b25.stop_order(struct, 1, 4000.0, 1, 1.0, 10)[0] == "INVALIDATED"
    assert b25.stop_order(bars([FLAT] * 5), 1, 4000.0, 1, 1.0, 3)[0] == "EXPIRED"
    sell = bars([FLAT, (4000.0, 4001.0, 3984.0, 3990.0)])
    assert b25.stop_order(sell, 1, 4000.0, -1, 1.0, 10)[:3] == ("FILLED", 1, 3985.0)


def test_confirmation_needs_a_close_and_a_same_bar_invalidation_wins():
    assert b25.confirm(bars([FLAT, (4000.0, 4016.0, 3999.0, 4010.0)] + [FLAT] * 3), 1, 4000.0, 1, 1.0, 4)[0] == "EXPIRED"
    assert b25.confirm(bars([FLAT, (4000.0, 4016.0, 3986.0, 4015.5)]), 1, 4000.0, 1, 1.0, 4)[0] == "INVALIDATED"
    assert b25.confirm(bars([FLAT, (4000.0, 4016.0, 3999.0, 4015.5)]), 1, 4000.0, 1, 1.0, 4) == ("CONFIRMED", 1)


# ---------------- the models on one trigger ----------------
def _A(j0, p0, d):
    return {"d": np.array([d]), "p0": np.array([p0]), "j0": np.array([j0]),
            "trig": [{"t_close": int(T0 + 900 * j0), "tf": "15m", "regime": "", "dir": d, "p0": p0}]}


def test_every_15m_model_on_one_confirmed_trigger():
    rows = [FLAT, (4000.0, 4016.0, 3999.0, 4015.0),                 # bar 1: confirms at its close (A entry 4015)
            (4016.0, 4020.0, 4014.0, 4018.0),                       # bar 2: B0 = its open 4016, B15 = its close 4018
            (4018.0, 4019.0, 4010.0, 4012.0)] + [(4012.0, 4040.0, 4011.0, 4035.0)] + [FLAT] * 200
    B = bars(rows)
    r = b25.run_models(B, _A(1, 4000.0, 1), False)[0]
    m = r["m"]
    assert r["A_status"] == "CONFIRMED"
    assert (m["A"]["entry"], m["B0"]["entry"], m["B15"]["entry"], m["B30"]["entry"]) == (4015.0, 4016.0, 4018.0, 4012.0)
    assert m["A"]["t_entry"] == T0 + 2 * 900 and m["B15"]["t_entry"] == T0 + 3 * 900
    assert m["C"]["entry"] == 4015.0 and m["C"]["t_entry"] == T0 + 2 * 900 + 450   # bar 2 trades back to 4015 (low 4014)
    assert m["E"]["entry"] == 4015.0 and m["E"]["how"] == "touch"           # the stop at 4015 fills inside bar 1
    assert m["A"]["T15"]["out"] == "TP" and m["B15"]["T15"]["out"] == "TP"


def test_retest_missed_and_a_false_confirmation_of_the_stop_order():
    up = [FLAT, (4000.0, 4016.0, 3999.0, 4015.0)] + [(4020.0, 4031.0, 4019.0, 4030.0)] * 10 + [FLAT] * 200
    r = b25.run_models(bars(up), _A(1, 4000.0, 1), False)[0]
    assert r.get("C_missed") and "C" not in r["m"] and r["m"]["A"]["T15"]["out"] == "TP"      # a missed opportunity
    s = b25.summarize([r], "C")
    assert s["missed"] == 1 and s["missed_opportunities"] == 1 and s["fill_rate"] == 0
    false = [FLAT, (4000.0, 4016.0, 3999.0, 4005.0), (4005.0, 4006.0, 3985.0, 3990.0)] + [FLAT] * 200   # touch, then -13
    r2 = b25.run_models(bars(false), _A(1, 4000.0, 1), False)[0]
    assert r2["A_status"] == "INVALIDATED" and "E" in r2["m"] and "A" not in r2["m"]
    assert b25.summarize([r2], "E")["false_confirmations"] == 1


def test_5m_structure_events_land_on_the_5m_bar_that_closes_with_the_15m_bar():
    idx15 = pd.date_range("2026-09-01 00:00", periods=4, freq="15min", tz="UTC")
    P = type("P", (), {})()
    P.t = np.asarray(ta.epoch_s(idx15), np.int64)
    P.up_evt, P.dn_evt = np.array([False, True, False, False]), np.zeros(4, bool)
    P.cost = np.array([0.8, 0.9, 1.0, 1.1])
    idx5 = pd.date_range("2026-09-01 00:00", periods=12, freq="5min", tz="UTC")
    df5 = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}, index=idx5)
    B5 = b25.bars5(df5, P)
    assert np.flatnonzero(B5.up).tolist() == [5]                     # the 15m bar 00:15 closes with the 5m bar 00:25
    assert B5.cost.tolist() == [0.8] * 3 + [0.9] * 3 + [1.0] * 3 + [1.1] * 3


# ---------------- statistics ----------------
def _row(day, a_net, m_net):
    return {"day": day, "dir": 1, "m": {"A": {"T15": {"net": a_net, "out": "TP" if a_net > 0 else "SL"}},
                                        "X": {"T15": {"net": m_net, "out": "TP" if m_net > 0 else "SL"}}}}


def test_paired_bootstrap_is_day_clustered_and_deterministic():
    rows = [_row(f"2021-01-{d:02d}", 14.0, 14.0 - 2.0) for d in range(1, 21)]
    a, b = b25.paired(rows, "X"), b25.paired(rows, "X")
    assert a == b and a["diff"] == pytest.approx(-2.0) and a["p"] == 0.0 and a["days"] == 20
    assert b25.holm({"x": 0.01, "y": 0.04, "z": 0.5}) == {"x": 0.03, "y": 0.08, "z": 0.5}
