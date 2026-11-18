"""B31b-W3 (research/registrations/B31b-W3.json): the liquidity event study's detector, measurements and gates.

Hand-worked series, a truncation (no look-ahead) check, race equivalence and the partition order."""
import json
import math
import os

import numpy as np
import pandas as pd
import pytest

from quantum.research import harness as H
from quantum.research import w3liq as W

FLAT = (4000.0, 4000.5, 3999.5, 4000.0)


def frame_of(rows, start="2026-03-02 00:00"):
    idx = pd.date_range(start, periods=len(rows), freq="15min", tz="UTC")
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"]).assign(volume=np.nan)


def h1_of(m15):
    return m15.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(
        subset=["open"])


def pdh_sweep_series():
    """Monday: flat at 4000 with one spike to 4005 at 10:00 UTC (the PDH for Tuesday). Tuesday 08:00 UTC: a bar runs
    to 4006.5 and closes back at 4000.2 (below every level it crossed), then price falls to 3988."""
    rows = [FLAT] * 40 + [(4000.0, 4005.0, 3999.5, 4000.0)] + [FLAT] * (128 - 41)        # Mon 00:00 .. Tue 07:45
    rows += [(4000.0, 4006.5, 3999.5, 4000.2)]                                              # Tue 08:00 sweep
    rows += [(4000.2, 4000.4, 3996.0, 3996.5), (3996.5, 3996.8, 3991.0, 3991.2), (3991.2, 3991.5, 3988.0, 3988.5)]
    rows += [(3988.5, 3989.0, 3988.0, 3988.5)] * 120
    return frame_of(rows)


def build_all(m15, score_from=None, m5=None):
    h1 = h1_of(m15)
    P, F15, F30, _ = W.frames(m15, h1, m5)
    sf = int(m15.index[0].timestamp()) if score_from is None else score_from
    piv = W.m5_pivots(P)
    ev, tr, st = W.build(P, F15, sf, piv, log=lambda *_: None)
    return P, F15, ev, tr, st


def test_hand_worked_pdh_sweep_event_class_and_immediate_entry():
    m15 = pdh_sweep_series()
    P, F, ev, tr, _ = build_all(m15)
    t_sweep = int(pd.Timestamp("2026-03-03 08:00", tz="UTC").timestamp())
    e = [x for x in ev if int(F.t[x["i"]]) == t_sweep and x["side"] == 1]
    assert len(e) == 1
    e = e[0]
    assert e["disp"] == "SWEEP" and e["primary"] == "PD" and "PDH" in e["names"]
    assert e["L"] == pytest.approx(4000.5) and e["L_out"] == pytest.approx(4005.0) and e["ext"] == pytest.approx(4006.5)
    assert 1 in e["types"] and 3 in e["types"] and 7 in e["types"]          # buy-side sweep, PDH, London session
    assert e["cls"] == "A" and e["cls_sub"] == "A1"
    assert e["first10"] == "REV"
    imm = [r for r in tr if r["ev_id"] == e["id"] and r["m"] == "A-IMM"][0]
    atr = F.atr[e["i"]]
    stop = 4006.5 + 0.2 * atr
    s = 4000.2 / 4000.0
    D = (stop - 4000.2) / s
    assert imm["d"] == -1 and imm["e"] == pytest.approx(4000.2) and imm["stop"] == pytest.approx(stop)
    assert imm["D"] == pytest.approx(D)
    assert imm["cost"] == pytest.approx(0.77)                                 # London, outside the kill zone
    assert imm["lots"] == math.floor(650.0 / ((D + 0.77) * 100.0) * 100.0) / 100.0
    assert imm["lots"] * (D + 0.77) * 100.0 <= 650.0
    assert imm["eligible"] and imm["tp10"] == "TP"
    assert imm["tp10_r"] == pytest.approx((10.0 - 0.77) / (D + 0.77))        # target exactly at +$10 x s


def test_gap_beyond_a_level_is_consumed_without_an_event():
    rows = [FLAT] * 40 + [(4000.0, 4005.0, 3999.5, 4000.0)] + [FLAT] * (128 - 41)
    rows += [(4007.0, 4008.0, 4006.5, 4007.5)] + [(4007.5, 4008.0, 4007.0, 4007.5)] * 20     # Tuesday opens above 4005
    m15 = frame_of(rows)
    P, F, ev, tr, st = build_all(m15)
    t_gap = int(pd.Timestamp("2026-03-03 08:00", tz="UTC").timestamp())
    assert not [x for x in ev if int(F.t[x["i"]]) == t_gap and x["side"] == 1]
    assert st["gapped"] >= 1


def random_walk(n=2600, seed=7):
    rng = H.seeded_rng(seed)
    steps = rng.normal(0, 1.4, n)
    c = 4000 + np.cumsum(steps)
    o = np.concatenate([[4000.0], c[:-1]])
    hi = np.maximum(o, c) + np.abs(rng.normal(0, 0.8, n))
    lo = np.minimum(o, c) - np.abs(rng.normal(0, 0.8, n))
    return frame_of(list(zip(o, hi, lo, c)))


def test_no_lookahead_events_and_their_before_during_measures_do_not_change_with_future_bars():
    full = random_walk()
    cut = 1800
    _, F1, e1, _, _ = build_all(full)
    _, F2, e2, _, _ = build_all(full.iloc[:cut])
    keys = ("i", "side", "L", "L_out", "n_lv", "names", "primary", "ext", "disp", "opp", "next_same", "age", "b_dist", "b_atrr",
            "b_comp", "b_e20", "b_e200", "b_stack", "b_twap", "b_mom", "room_rev", "room_cont", "d_pen", "d_wick", "d_close",
            "fvg_rev", "fvg_cont", "two_sided", "b_h1", "b_h4", "b_m30")
    a = {(x["i"], x["side"]): x for x in e1 if x["i"] < cut - 3}
    b = {(x["i"], x["side"]): x for x in e2 if x["i"] < cut - 3}
    assert a.keys() == b.keys() and len(a) > 50
    for k in a:
        for f in keys:
            va, vb = a[k][f], b[k][f]
            if isinstance(va, float) and math.isnan(va):
                assert isinstance(vb, float) and math.isnan(vb), (k, f)
            else:
                assert va == vb, (k, f, va, vb)


def test_fast_race_equals_reference_race():
    m15 = random_walk(1500, seed=3)
    P = W.make_path(m15, None)
    rng = H.seeded_rng(5)
    for _ in range(400):
        k = int(rng.integers(20, 1300))
        d = int(rng.choice([-1, 1]))
        e = float(P.c[k])
        D, T = float(rng.uniform(1, 8)), float(rng.choice([10.0, 15.0, 20.0]))
        stop, tgt = e - d * D, e + d * T
        assert W.race(P, k + 1, d, e, stop, tgt) == W.race_fast(P, k + 1, d, e, stop, tgt)


def test_m5_orders_a_15m_bar_that_touches_both_and_one_m5_bar_touching_both_stays_ambiguous():
    m15 = frame_of([(4000.0, 4006.0, 3994.0, 4000.0)] * 3)
    t0 = m15.index[1]
    m5 = pd.DataFrame([(4000.0, 4006.0, 3999.0, 4005.0), (4005.0, 4005.5, 3994.0, 3995.0), (3995.0, 3996.0, 3995.0, 3995.5)],
                      index=pd.date_range(t0, periods=3, freq="5min"), columns=["open", "high", "low", "close"])
    P = W.make_path(m15, m5)
    # long from 4000, stop 3995, target 4005: the first M5 bar reaches the target first
    assert W.race(P, 1, 1, 4000.0, 3995.0, 4005.0)[0] == "TP"
    assert W.race_fast(P, 1, 1, 4000.0, 3995.0, 4005.0)[0] == "TP"
    m5b = m5.copy()
    m5b.iloc[0] = (4000.0, 4006.0, 3994.0, 4000.0)                           # one M5 bar touches both
    P2 = W.make_path(m15, m5b)
    assert W.race(P2, 1, 1, 4000.0, 3995.0, 4005.0)[0] == "AMBIGUOUS"
    P3 = W.make_path(m15, None)
    assert W.race(P3, 1, 1, 4000.0, 3995.0, 4005.0)[0] == "AMBIGUOUS"         # no M5: the stop (conservative)


def test_limit_retest_fills_at_the_level_and_a_fill_bar_reaching_the_stop_is_a_loss():
    m15 = pdh_sweep_series()
    rows = m15.copy()
    k = rows.index.get_loc(pd.Timestamp("2026-03-03 08:15", tz="UTC"))
    rows.iloc[k, :4] = (4000.2, 4000.9, 3999.0, 3999.2)                           # trades back up through 4000.5: fills the sell limit
    P, F, ev, tr, _ = build_all(rows)
    e = [x for x in ev if x["disp"] == "SWEEP" and x["side"] == 1 and x["primary"] == "PD"][0]
    rt = [r for r in tr if r["ev_id"] == e["id"] and r["m"] == "A-RETEST"][0]
    assert rt["status"] == "FILLED" and rt["e"] == pytest.approx(4000.5) and rt["t_fill"] == int(rows.index[k].timestamp())
    assert not rt["fill_bar_stop"]
    rows.iloc[k, :4] = (4000.2, 4008.0, 3999.0, 3999.2)                           # the fill bar also runs through the stop
    P, F, ev, tr, _ = build_all(rows)
    e = [x for x in ev if x["disp"] == "SWEEP" and x["side"] == 1 and x["primary"] == "PD"][0]
    rt = [r for r in tr if r["ev_id"] == e["id"] and r["m"] == "A-RETEST"][0]
    assert rt["fill_bar_stop"] and rt["tp10"] == "SL" and rt["tp20"] == "SL"


def test_break_accepted_then_continuation_is_class_b_and_orders_b_close_and_b_acc():
    rows = [FLAT] * 40 + [(4000.0, 4005.0, 3999.5, 4000.0)] + [FLAT] * (128 - 41)
    rows += [(4000.0, 4006.0, 3999.8, 4005.8), (4005.8, 4007.0, 4005.5, 4006.8), (4006.8, 4008.0, 4006.5, 4007.8)]
    rows += [(4007.8, 4012.0, 4007.5, 4011.8), (4011.8, 4017.0, 4011.5, 4016.8)] + [(4016.8, 4017.0, 4016.5, 4016.8)] * 120
    P, F, ev, tr, _ = build_all(frame_of(rows))
    e = [x for x in ev if x["side"] == 1 and "PDH" in x["names"]][0]
    assert e["disp"] == "BREAK" and 12 in e["types"] and 11 not in e["types"]
    assert e["cls"] == "B"
    ms = {r["m"] for r in tr if r["ev_id"] == e["id"]}
    assert {"B-CLOSE", "B-ACC", "B-RETEST"} <= ms


def test_false_breakout_then_reversal_is_class_c_and_type_11():
    rows = [FLAT] * 40 + [(4000.0, 4005.0, 3999.5, 4000.0)] + [FLAT] * (128 - 41)
    rows += [(4000.0, 4006.0, 3999.8, 4005.6), (4005.6, 4005.8, 4000.1, 4000.3)]              # break, then back inside
    rows += [(4000.3, 4000.4, 3994.0, 3994.5), (3994.5, 3994.6, 3989.0, 3989.5)] + [(3989.5, 3990.0, 3989.0, 3989.5)] * 120
    P, F, ev, tr, _ = build_all(frame_of(rows))
    e = [x for x in ev if x["side"] == 1 and "PDH" in x["names"]][0]
    assert e["disp"] == "BREAK" and 11 in e["types"] and 12 not in e["types"]
    assert e["cls"] == "C"


def test_m30_needs_both_15m_bars():
    m15 = frame_of([FLAT] * 6)
    m15 = m15.drop(m15.index[3])
    m30, incomplete = W.make_m30(m15)
    assert len(m30) == 2 and incomplete == 1


def test_one_position_per_variant():
    rows = [{"m": "A-IMM", "tf": "M15", "t_fill": 0, "ev_id": "a", "tp10_exit": 1000.0},
            {"m": "A-IMM", "tf": "M15", "t_fill": 500, "ev_id": "b", "tp10_exit": 900.0},
            {"m": "A-IMM", "tf": "M30", "t_fill": 500, "ev_id": "c", "tp10_exit": 900.0},
            {"m": "A-IMM", "tf": "M15", "t_fill": 1000, "ev_id": "d", "tp10_exit": 2000.0}]
    assert [r["ev_id"] for r in W.one_position(rows)] == ["a", "c", "d"]


def test_lots_never_exceed_the_650_risk():
    for D in (0.5, 3.0, 7.3, 21.0, 640.0):
        for c in (0.58, 0.77, 0.97):
            lots = W.lots_for(D, c)
            assert lots * (D + c) * 100 <= 650.0 + 1e-9
            assert (lots + 0.01) * (D + c) * 100 > 650.0
    assert W.lots_for(700.0, 0.77) == 0.0


def test_partition_gate_order(tmp_path):
    res, fz = tmp_path / "res", tmp_path / "freeze.json"
    res.mkdir()
    with pytest.raises(H.SealedPartition):
        W.gate("validation", str(res), str(fz))
    fz.write_text(json.dumps({"code_sha256": "not-this-code"}))
    with pytest.raises(H.SealedPartition):
        W.gate("validation", str(res), str(fz))
    fz.write_text(json.dumps({"code_sha256": W.code_sha()}))
    W.gate("validation", str(res), str(fz))                                      # allowed once
    with pytest.raises(H.SealedPartition):
        W.gate("holdout", str(res), str(fz))
    (res / "b31b_w3_validation_x.json").write_text(json.dumps({"candidates": [{"verdict": "FAIL"}]}))
    with pytest.raises(H.SealedPartition):
        W.gate("validation", str(res), str(fz))                                  # a second opening
    with pytest.raises(H.SealedPartition):
        W.gate("holdout", str(res), str(fz))                                     # no PASS
    (res / "b31b_w3_validation_x.json").write_text(json.dumps({"candidates": [{"verdict": "PASS"}]}))
    W.gate("holdout", str(res), str(fz))


def test_registration_is_committed_and_approved_for_the_sealed_partitions():
    reg = json.load(open(os.path.join(H.REG_DIR, "B31b-W3.json")))
    assert reg["approved_by_operator"] is True and set(reg["partitions"]) == {"development", "validation", "holdout"}


def test_walk_forward_never_trains_on_trades_whose_outcome_window_reaches_the_test_fold():
    t = np.arange(0, 600) * 86400 // 2
    rows = [{"t_fill": int(x), "tp10": "TP" if (k % 3) else "SL", **{f: float((k * 7 + j) % 11) for j, f in enumerate(W.FEATURES)}}
            for k, x in enumerate(t)]
    p = W.walk_forward(rows, W.FEATURES, int(t[0]), int(t[-1]) + 1)
    edges = np.linspace(t[0], t[-1] + 1, 7)
    assert np.isnan(p[t < edges[1]]).all() and np.isfinite(p[t >= edges[1]]).all()
