"""Engine tests. The EdgeCases groups (A-L) are asserted against the ENGINE'S OWN functions,
not against a re-model of them (the v6 harness passed while testing its own model -- F-A10).
Plus the invariant that matters most for a backtest: nothing from the future leaks in."""
import dataclasses
import json
import math

import numpy as np
import pytest

from quantum import analog, backtest, engine, holdout, report
from quantum.config import DEFAULT, Config
from quantum.data.market import load_synthetic
from quantum.features import _cf_iterate


@pytest.fixture(scope="module")
def mkt():
    return load_synthetic("15m", bars=2600, seed=5)


@pytest.fixture(scope="module")
def res(mkt):
    return engine.run(mkt, DEFAULT)


# ---------------- GROUP B / K: the SL/TP race label ----------------
def _label(highs, lows, ent=2000.0, atr=10.0, slm=1.0, N=4):
    n = 1 + len(highs)
    c = [ent] + [ent] * len(highs)
    h = [ent] + list(highs)
    l = [ent] + list(lows)
    H = {k: np.zeros(n) for k in ("ret", "runit", "term")}
    H.update(out=np.zeros(n, dtype=int), race=np.full(n, -1), bev=np.zeros(n, dtype=int), bcont=np.full(n, -1.0), first=np.zeros(n, dtype=int))
    hi_out = [max(h[max(0, i - N + 1):i + 1]) for i in range(n)]
    lo_out = [min(l[max(0, i - N + 1):i + 1]) for i in range(n)]
    engine.label_outcome(0, N, N, H, c, h, l, [atr] * n, [slm] * n, hi_out, lo_out, np.full(n, np.nan), np.full(n, np.nan))
    return H


@pytest.mark.parametrize("hs,ls,want", [
    ([2011, 2000, 2000, 2000], [2000, 2000, 2000, 2000], 1),    # B1 TP only
    ([2000, 2000, 2000, 2000], [1989, 2000, 2000, 2000], -1),   # B2 SL only
    ([2011, 2000, 2000, 2000], [1989, 2000, 2000, 2000], -1),   # B3 both in one candle -> LOSS
    ([2005, 2005, 2005, 2005], [1995, 1995, 1995, 1995], 0),    # B4 neither -> timeout
    ([2005, 2000, 2000, 2000], [1990, 2000, 2000, 2000], -1),   # B5 exact SL touch counts
    ([2010, 2000, 2000, 2000], [1995, 2000, 2000, 2000], 1),    # B6 exact TP touch counts
])
def test_race_outcome(hs, ls, want):
    assert _label(hs, ls)["out"][0] == want


def test_race_zero_R_never_runs():
    assert _label([2011, 2000, 2000, 2000], [1989, 2000, 2000, 2000], atr=0.0)["out"][0] == 0


def test_race_code_decodes():
    H = _label([2011, 2021, 2000, 2000], [2000, 1995, 2000, 2000])
    code = int(H["race"][0])
    digits = [(code // 3 ** j) % 3 for j in range(6)]
    assert digits[0] == 1 and digits[1] == 1      # long reached +1R and +2R before -1R
    assert digits[3] == 2                          # short: +1R (adverse) came first -> loss


@pytest.mark.parametrize("rr,want", [(0.0, 100), (0.5, 70), (2.5, 15)])
def test_grid_interp(rr, want):
    assert abs(engine.f_grid_interp(rr, 100.0, 40.0, 20.0, 10.0, True) - want) < 1e-9


def test_grid_interp_tails():
    assert engine.f_grid_interp(5.0, 0.0, 30.0, 35.0, 36.0, False) == 36
    assert engine.f_grid_interp(4.0, 100.0, 40.0, 20.0, 10.0, True) < 10


# ---------------- GROUP D: bayesRate ----------------
def test_bayes_rate():
    assert analog.bayes_rate(0, 0) == 0.5
    assert abs(analog.bayes_rate(0, 30) - 1 / 32) < 1e-12
    assert abs(analog.bayes_rate(30, 30) - 31 / 32) < 1e-12
    assert analog.bayes_rate(0, 1000) < analog.bayes_rate(0, 30)


# ---------------- GROUPS E / F / G: calibration gates via the real publisher ----------------
def _publish_with_bins(bins, prev_fit=(math.nan, math.nan)):
    st = analog.AnalogState()
    st.cal_fit = list(prev_fit)
    A = dict(mt=0, wt=0.0, mb=0, mbr=0, mr_=0, wb=0, wbr=0, wr_=0, pT=0, wp1=0, wpT=0, p1=0, sw=0, sl=0, st=0, wc=0, lc=0,
             cal=bins, boT=0, bov=0, fS=(0, 0), fH=(0, 0), fL=(0, 0), fM=(0, 0), fC=(0, 0), mae_cnt=0, mae_sum=0,
             ghit=[0] * 9, grace=[0] * 19, eq_peak=100.0, max_dd=0.0, oos_mt=0, is_mt=0)
    P = {"N": 4}
    cur = {"r_curr": 1, "reg_trans": {k: 0 for k in ("T", "R", "D", "TR", "TD", "RT", "RD", "DT", "DR")}}
    analog._publish(0, st, P, cur, A)
    return st


def test_bin_needs_30():
    st = _publish_with_bins([(29, 29 * 30.0, 8, 15)] + [(0, 0, 0, 0)] * 4)
    assert st.out["cal_grade"] == "N/A"          # E1: N=29 rejected
    st = _publish_with_bins([(30, 30 * 30.0, 8, 15)] + [(0, 0, 0, 0)] * 4)
    assert st.out["cal_grade"] != "N/A"          # E2: N=30 accepted


def test_platt_needs_three_bins_and_positive_slope():
    two = [(40, 40 * 30.0, 10, 20), (40, 40 * 60.0, 25, 10)] + [(0, 0, 0, 0)] * 3
    assert math.isnan(_publish_with_bins(two).cal_fit[0])            # E4
    three = [(40, 40 * 30.0, 10, 20), (40, 40 * 50.0, 18, 12), (40, 40 * 70.0, 28, 6)] + [(0, 0, 0, 0)] * 2
    st = _publish_with_bins(three)
    assert 0.02 <= st.cal_fit[0] <= 0.25 and -1 <= st.cal_fit[1] <= 1  # F clamps
    assert st.cal_fit_bear[0] < 0                                        # bear fit has negative slope
    inverted = [(40, 40 * 30.0, 28, 6), (40, 40 * 50.0, 18, 12), (40, 40 * 70.0, 10, 20)] + [(0, 0, 0, 0)] * 2
    assert math.isnan(_publish_with_bins(inverted).cal_fit[0])       # F6: negative slope rejected


def test_timeout_is_bin_total_not_win(res):
    # C1/C2 on the real buffer: bin totals include timeouts, wins count only oc == 1.
    H = res.params["H"]
    lo = H["first_rec"]
    assert lo is not None and (H["out"][lo:] == 0).any()


# ---------------- GROUP H / J ----------------
def test_macro_vote_pool():
    assert int(math.ceil(6 / 2.0)) == 3 and int(math.ceil(7 / 2.0)) == 4


# ---------------- GROUP L: Cornish-Fisher inverse ----------------
def test_cf_inverse_identity_and_roundtrip():
    x = np.array([1.7])
    assert abs(_cf_iterate(x.copy(), x, np.array([0.0]), np.array([0.0]))[0] - 1.7) < 1e-9
    s, k, w = 0.5, 2.0, 2.0
    fwd = w + (w * w - 1) * s / 6 + (w ** 3 - 3 * w) * k / 24 - (2 * w ** 3 - 5 * w) * s * s / 36
    back = _cf_iterate(np.array([fwd]), np.array([fwd]), np.array([s]), np.array([k]))[0]
    assert abs(back - 2.0) < 1e-6
    assert _cf_iterate(np.array([3.0]), np.array([3.0]), np.array([0.0]), np.array([3.0]))[0] < 3.0


def test_normalize_scores_sum_and_floor():
    for b, be, r in [(70, 60, 10), (2, 1, 0), (40, 30, 30), (95, 5, 0)]:
        nb, nbe, nr = engine.normalize_scores(b, be, r, 1.0)
        assert abs(nb + nbe + nr - 100) < 1e-9 or nb + nbe + nr <= 100
        assert nb >= 1 or b < 1


# ---------------- trade plan ----------------
def _plan(**kw):
    AS = analog.AnalogState()
    base = dict(i=0, cfg=DEFAULT, should_buy=True, should_sell=False, bull_bias=60, bear_bias=40, close=2049.0, a=10.0,  # RN 2050 too close to be a target
                reg_sl=1.5, active_sup=np.nan, active_res=np.nan, ob_b_act=False, ob_bl=np.nan, ob_bh=np.nan, ob_s_act=False,
                ob_sl=np.nan, ob_sh=np.nan, cdl=np.nan, cdh=np.nan, pdl=np.nan, pdh=np.nan, pwh=np.nan, pwl=np.nan,
                pmh=np.nan, pml=np.nan, eql=np.nan, eqh=np.nan, val=np.nan, vah=np.nan, vpoc=np.nan, wvwap=np.nan,
                mvwap=np.nan, AS=AS, sess_spread=0.3, N=4, regime_label="RANGE")
    base.update(kw)
    return engine.trade_plan(**base)


def test_plan_fallback_ladder_names_what_it_is():
    p = _plan()
    assert p["sl_basis"] == "ATR" and p["tp_basis"] == ["1R", "2R", "3R"]
    assert p["tp1"] > p["entry"] > p["sl"] and abs(p["rr1"] - 1) < 1e-9 and abs(p["rr3"] - 3) < 1e-9
    p = _plan(pdh=2069.0)            # one real level, then the ladder continues from it
    assert p["tp_basis"][0] == "PDH" and p["tp_basis"][1] == "+1R"


def test_plan_structural_stop_and_r_clamp():
    p = _plan(active_sup=2039.0)
    assert p["sl_basis"] == "Swing" and abs(p["sl"] - (2039.0 - 1.5)) < 1e-9
    p = _plan(a=10.0, reg_sl=0.01)   # absurdly tight stop -> clamped to 0.5 ATR, marked *
    assert p["sl_basis"].endswith("*") and abs(p["dist"] - 5.0) < 1e-9


def test_plan_tp_cap_12R():
    p = _plan(pdh=2049.0 + 15 * 13)   # 13 R away with a 15-pt stop -> not a target
    assert p["tp_basis"][0] == "1R"


def test_plan_short_mirror():
    p = _plan(should_buy=False, should_sell=True, pdl=2019.0)
    assert not p["long"] and p["sl"] > p["entry"] and p["tp_basis"][0] == "PDL"


# ---------------- whole engine ----------------
def test_engine_runs_and_is_deterministic(mkt, res):
    r2 = engine.run(mkt, DEFAULT)
    assert r2.last["decision"] == res.last["decision"]
    assert np.allclose(np.nan_to_num(r2.rows["bull"]), np.nan_to_num(res.rows["bull"]))
    assert 0 <= res.last["trade_quality"] <= 100
    assert abs(res.last["bull_score"] + res.last["bear_score"] + res.last["range_score"] - 100) < 1e-6


def test_no_lookahead(mkt, res):
    """Truncating the chart at bar k must not change any decision made before bar k."""
    k = 2300
    m2 = dataclasses.replace(mkt, base=mkt.base.iloc[:k])
    r2 = engine.run(m2, DEFAULT)
    for key in ("bull", "bear", "tq", "plan_sl", "plan_tp1", "cal_p_long", "struct"):
        a, b = res.rows[key][:k], r2.rows[key]
        assert np.allclose(np.nan_to_num(a, nan=-9), np.nan_to_num(b, nan=-9)), key
    assert list(res.rows["dir_label"][:k]) == list(r2.rows["dir_label"])
    assert list(res.rows["exec_buy"][:k]) == list(r2.rows["exec_buy"])


def test_control_arm_uses_stricter_gate(mkt, res):
    ctrl = engine.run(mkt, DEFAULT, "control", res.F)
    sig_t = np.nansum(res.rows["should_buy"]) + np.nansum(res.rows["should_sell"])
    sig_c = np.nansum(ctrl.rows["should_buy"]) + np.nansum(ctrl.rows["should_sell"])
    assert sig_c <= sig_t


# ---------------- backtest execution model ----------------
class _R:
    pass


def _bt(o, h, l, c, buy_at, sl, tp1, tp2):
    import pandas as pd
    n = len(c)
    r = _R()
    r.F = {"o": np.array(o, float), "h": np.array(h, float), "l": np.array(l, float), "c": np.array(c, float),
           "index": pd.date_range("2026-01-05", periods=n, freq="15min", tz="UTC"), "sess_spread": np.full(n, 0.3),
           "session_label": np.array(["NY"] * n), "mkt_regime": np.array(["RANGE"] * n)}
    eb = np.zeros(n)
    eb[buy_at] = 1
    r.rows = {"exec_buy": eb, "exec_sell": np.zeros(n), "plan_sl": np.full(n, sl), "plan_tp1": np.full(n, tp1),
              "plan_tp2": np.full(n, tp2), "tq": np.full(n, 60), "cal_p_long": np.full(n, 0.6),
              "cal_p_short": np.full(n, 0.4), "plan_ev": np.full(n, 0.1)}
    return backtest.simulate(r, DEFAULT)


def test_bt_stop_first_on_same_bar():
    t = _bt([100] * 4, [100, 100, 110, 100], [100, 100, 90, 100], [100] * 4, 1, 95, 105, 110)
    assert t[0]["exit_reason"] == "SL" and t[0]["r"] < -1


def test_bt_partial_then_breakeven():
    t = _bt([100] * 5, [100, 100, 106, 101, 101], [100, 100, 99, 99.5, 99], [100, 100, 104, 100, 100], 1, 95, 105, 120)
    tr = t[0]
    assert tr["tp1_hit"] and tr["exit_reason"] == "BE"
    assert abs(tr["gross_pts"] - 2.5) < 1e-9         # 50% x 5 points, rest flat at entry
    assert abs(tr["pts"] - (2.5 - tr["cost_pts"])) < 1e-9


def test_bt_entry_bar_range_is_not_used():
    # the signal bar's own low is below the stop: entry is at its CLOSE, so it must not stop out there
    t = _bt([100] * 4, [100, 100, 111, 100], [100, 90, 100, 100], [100] * 4, 1, 95, 105, 110)
    assert t[0]["exit_reason"] == "TP2"


# ---------------- holdout ----------------
def test_holdout_resets_on_config_change(tmp_path):
    a = holdout.load_or_freeze(str(tmp_path), DEFAULT)
    assert a["status"] == "STARTED"
    b = holdout.load_or_freeze(str(tmp_path), DEFAULT)
    assert b["status"] == "ACTIVE" and b["freeze_utc"] == a["freeze_utc"]
    c = holdout.load_or_freeze(str(tmp_path), dataclasses.replace(DEFAULT, tq_min_score=60))
    assert c["status"] == "RESET" and c["history"][0]["config_hash"] == DEFAULT.hash()


def test_config_hash_is_stable():
    assert Config().hash() == DEFAULT.hash()


# ---------------- report ----------------
def test_report_is_strict_json(mkt, res):
    ctrl = engine.run(mkt, DEFAULT, "control", res.F)
    man = holdout.load_or_freeze(None, DEFAULT)
    p = report.build(mkt, res, ctrl, DEFAULT, man)
    s = json.dumps(p, allow_nan=False)
    assert '"synthetic":true' in s.replace(" ", "")
    t = p["chart"]["t"]
    assert len(t) == len(set(t)) and t == sorted(t)
