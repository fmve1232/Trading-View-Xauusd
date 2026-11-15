"""B31b-SHADOW-FWD (research/registrations/B31b-SHADOW-FWD.json): the forward shadow test of B31's modules.

Hand-built bars check each rule (the ladder eligibility, the race, the fill bar, the order's life, REPEAT, timeliness,
immutability); synthetic engine payloads check that recording bar by bar equals one pass over all the data (no look-ahead,
no duplicate, no retrospective record); expected statistics are computed by hand. Synthetic data only."""
import json
import math

import numpy as np
import pytest

from quantum import engine, holdout, report, shadow as SH
from quantum.config import DEFAULT
from quantum.data.market import load_synthetic

T0 = 1795000000 - 1795000000 % 900


def ctx(o, h, l, c, **kw):
    """A hand-built context: bars from T0 every 15 minutes, no pools or structure unless given."""
    X = SH.Ctx()
    n = len(c)
    X.t = np.array([T0 + 900 * i for i in range(n)], np.int64)
    X.o, X.h, X.l, X.c = (np.asarray(a, float) for a in (o, h, l, c))
    X.atr = np.full(n, 5.0)
    X.aatr = np.full(n, 5.0)
    X.cost = np.full(n, 0.77)
    X.date = np.array(["2026-11-16"] * n, object)
    X.sess = np.array(["LONDON"] * n, object)
    X.pools = {k: np.full(n, np.nan) for k in SH.SELL_SIDE + SH.BUY_SIDE + ("CDH", "CDL")}
    X.asia_date = np.array([None] * n, object)
    for k in ("up_any", "dn_any", "up_shift", "dn_shift", "ranging", "htf_up", "htf_dn"):
        setattr(X, k, np.zeros(n, bool))
    for k in ("ob_bull_hi", "ob_bear_lo", "vwap", "lo2", "up2", "v"):
        setattr(X, k, np.full(n, np.nan))
    for k, v in kw.items():
        setattr(X, k, v)
    return X


def flat(n, px=4000.0):
    return [px] * n, [px + 1] * n, [px - 1] * n, [px] * n


# ---------------- the rules ----------------
def test_eligibility_is_on_the_ladder_not_on_tp1():
    X = ctx(*flat(5))
    s = lambda stop: {"dir": 1, "stop": stop}
    assert SH.check(X, s(4000 - 13.0), 4000.0, 2, 0.77) is None             # (15 - .77) / (13 + .77) = 1.033
    assert SH.check(X, s(4000 - 14.0), 4000.0, 2, 0.77) == "reward"         # 14.23 / 14.77 = 0.963
    assert SH.check(X, s(4000 - 4.9), 4000.0, 2, 0.77) == "stop"            # the $5 minimum
    assert SH.check(X, s(4000 - 6.0), 4000.0, 2, 0.97) == "cost"            # 0.97 > 15% of 6
    assert SH.check(X, s(4000 + 1.0), 4000.0, 2, 0.77) == "stop on the wrong side"
    X.pools["PDH"][2] = 4009.0                                               # an opposing pool inside TP1
    assert SH.check(X, s(4000 - 8.0), 4000.0, 2, 0.77) == "room"
    X.pools["PDH"][2] = 4010.5
    assert SH.check(X, s(4000 - 8.0), 4000.0, 2, 0.77) is None
    assert SH.check(X, {"dir": 1, "stop": 3992.0, "vwap": 4009.0}, 4000.0, 2, 0.77) == "room"   # D: the VWAP beyond TP1


def test_race_tp_sl_ambiguous_gap_open_and_timeout():
    o, h, l, c = flat(120)
    X = ctx(o, h, l, c)
    assert SH.race(X, 0, 1, 3990.0, 4010.0) == ("TIMEOUT", SH.HOLD - 1, 4000.0)
    h2 = list(h); h2[5] = 4010.0
    assert SH.race(ctx(o, h2, l, c), 0, 1, 3990.0, 4010.0) == ("TP", 5, 4010.0)
    l2 = list(l); l2[5] = 3990.0
    assert SH.race(ctx(o, h, l2, c), 0, 1, 3990.0, 4010.0) == ("SL", 5, 3990.0)
    assert SH.race(ctx(o, h2, l2, c), 0, 1, 3990.0, 4010.0) == ("AMBIGUOUS", 5, 3990.0)   # both in one bar: the stop
    o2 = list(o); o2[4] = 3985.0
    assert SH.race(ctx(o2, h, l, c), 0, 1, 3990.0, 4010.0) == ("SL", 4, 3985.0)          # opened beyond the stop
    o3 = list(o); o3[4] = 4012.0
    assert SH.race(ctx(o3, h, l, c), 0, 1, 3990.0, 4010.0) == ("TP", 4, 4012.0)
    short = ctx(*flat(30))
    assert SH.race(short, 0, 1, 3990.0, 4010.0) == ("OPEN", None, None)                 # not decided by the data yet
    assert SH.race(ctx(o, h2, l, c), 0, -1, 4010.0, 3990.0) == ("SL", 5, 4010.0)        # the mirror loses there


def test_side_the_fill_bar_can_only_stop_and_the_mirror_is_symmetric():
    o, h, l, c = flat(120)
    l[3] = 3989.0                                                             # the fill bar reaches the long stop
    X = ctx(o, h, l, c)
    own = SH.side(X, 3, 4, 1, 4000.0, 10.0, True)
    assert own["out"] == ["SL"] * 3 and own["th"] == -10.0
    mir = SH.side(X, 3, 4, -1, 4000.0, 10.0, True)                            # the short's stop (4010) was not touched
    assert mir["out"] == ["TIMEOUT"] * 3
    h2 = list(h); h2[10] = 4021.0
    up = SH.side(ctx(o, h2, flat(120)[2], c), 3, 4, 1, 4000.0, 10.0, True)
    assert up["out"] == ["TP", "TP", "TP"] and up["bars1"] == 7
    assert up["th"] == pytest.approx(10.0 / 3)       # one bar through all three: TP1 only, then back to the entry (B31)
    o3, h3, l3, c3 = flat(120)
    for i in range(10, 120):
        o3[i], l3[i], c3[i] = 4001.0, 4000.5, 4001.0   # never back to the entry after TP1
    h3[10], h3[12], h3[14] = 4010.5, 4015.5, 4020.5
    ladder = SH.side(ctx(o3, h3, l3, c3), 3, 4, 1, 4000.0, 10.0, True)
    assert ladder["th"] == pytest.approx(15.0)       # thirds at +10 / +15 / +20


def test_thirds_moves_the_stop_to_the_entry_after_tp1():
    o, h, l, c = flat(120)
    h[5] = 4010.0                                                             # TP1
    l[8] = 3999.0                                                             # back to the entry: the rest at break-even
    h[10], h[12] = 4015.5, 4020.5                                             # TP2 / TP3 only after that
    X = ctx(o, h, l, c)
    assert SH.thirds(X, 0, 1, 4000.0, 3990.0) == pytest.approx(10.0 / 3)      # with the original stop it would be 15


# ---------------- the order's life ----------------
def _rec(**kw):
    r = {"module": "C", "dir": 1, "order_t": T0, "limit": 4000.0, "market": None, "stop": 3990.0, "inval": None,
         "false_break": False, "cost": 0.77, "status": "PENDING"}
    r.update(kw)
    return r


def test_limit_fill_missed_invalidated_false_breakout_overlap_and_lost():
    o, h, l, c = ([4005.0] * 150 for _ in range(4))
    h = [4006.0] * 150
    l = [4004.0] * 150
    l2 = list(l); l2[3] = 3999.0                                             # touches the 4000 limit on bar 3
    r = _rec()
    SH.follow(ctx(o, h, l2, c), r, [])
    assert r["status"] == "DONE" and r["entry"] == 4000.0 and r["fill_t"] == T0 + 900 * 3 and r["day"] == "2026-11-16"
    r = _rec()
    SH.follow(ctx(o, h, l, c), r, [])
    assert r["status"] == "MISSED"                                            # not filled within 8 bars
    r = _rec()
    SH.follow(ctx(o[:5], h[:5], l[:5], c[:5]), r, [])
    assert r["status"] == "PENDING"                                           # the 8 bars are not there yet
    o2 = list(o); o2[2] = 3998.0
    r = _rec(false_break=True)
    SH.follow(ctx(o2, h, l, c), r, [])
    assert r["status"] == "FALSE_BREAKOUT"
    r = _rec(inval=3995.0)
    o3 = list(o); o3[2] = 3994.0
    SH.follow(ctx(o3, h, l, c), r, [])
    assert r["status"] == "INVALIDATED"                                       # opened beyond the sweep extreme
    r = _rec()
    SH.follow(ctx(o, h, l2, c), r, [(T0, None)])
    assert r["status"] == "OVERLAP"                                           # the module's trade was still open
    r = _rec()
    SH.follow(ctx(o, h, l2, c), r, [(T0 - 3600, T0 + 900 * 2)])
    assert r["status"] == "DONE"                                              # it closed on the bar before the fill
    r = _rec(order_t=T0 + 450)
    SH.follow(ctx(o, h, l2, c), r, [])
    assert r["status"] == "LOST"


def test_done_record_has_the_money_and_the_mirror():
    o, h, l, c = flat(150)
    for i in range(1, 150):
        o[i], l[i], c[i], h[i] = 4001.0, 4000.5, 4001.0, 4002.0
    h[6], h[8], h[10] = 4010.5, 4015.5, 4020.5                               # TP1, TP2, TP3 on separate bars
    r = _rec(limit=None, market=4000.0, stop=3990.0)
    SH.follow(ctx(o, h, l, c), r, [])
    assert r["status"] == "DONE" and r["out"] == ["TP", "TP", "TP"] and r["D"] == 10.0
    assert r["ladder_r"] == pytest.approx((15.0 - 0.77) / (10.0 + 0.77), abs=1e-4)
    assert r["ladder_usd"] == pytest.approx((15.0 - 0.77) / (10.0 + 0.77) * 650, abs=0.01)    # $858.82 at $650 risk
    assert r["lots"] == pytest.approx(650 / (100 * 10.77), abs=1e-3)
    assert r["mirror"]["out"] == ["SL", "SL", "SL"] and r["mirror"]["ladder_r"] == pytest.approx(-1.0, abs=1e-4)
    assert r["fill_t"] == T0 + 900 and r["min_to_tp1"] == 6 * 15


# ---------------- recording: once, timely, REPEAT, immutable ----------------
def _breakout_ctx(n=200):
    """A buy-side pool at 4010 broken and accepted with a bullish FVG, then a retest of the level."""
    o, h, l, c = ([4000.0] * n for _ in range(4))
    h, l = [4001.0] * n, [3999.0] * n
    seq = {50: (4001, 4004, 4000, 4003), 51: (4003, 4009, 4003, 4008), 52: (4008, 4016, 4012, 4015),
           53: (4015, 4018, 4013, 4016), 54: (4016, 4019, 4014, 4017)}
    for i, (a, b, d_, e) in seq.items():
        o[i], h[i], l[i], c[i] = a, b, d_, e
    for i in range(55, n):
        o[i], h[i], l[i], c[i] = 4016.0, 4017.0, 4015.0, 4016.0
    o[56], l[56] = 4012.0, 4009.0                                             # the retest touches the 4010 level
    X = ctx(o, h, l, c)
    X.pools["PWH"] = np.full(n, 4010.0)
    X.pools["PWH"][:40] = np.nan
    X.date = np.array(["2026-11-16"] * n, object)
    return X


def test_a_setup_is_recorded_once_timely_and_frozen_when_decided():
    X = _breakout_ctx()
    s = SH.setups(X, "C", SH.crossings(X, SH.SELL_SIDE + SH.BUY_SIDE))
    assert len(s) == 1 and s[0]["dir"] == 1 and s[0]["limit"] == 4010.0 and s[0]["order_bar"] == 54
    book = {"started_utc": int(X.t[0]), "setups": [], "days": [], "verdicts": {}}
    late = int(X.t[54]) + 900 + SH.TIMELY_SEC + 1
    SH.update(book, X, late)
    assert len(book["setups"]) == 1 and book["setups"][0]["timely"] is False   # recorded too late: outside the primary
    SH.update(book, X, late + 900)
    assert len(book["setups"]) == 1                                           # never twice
    done = json.dumps(book["setups"][0], sort_keys=True)
    assert book["setups"][0]["status"] in ("DONE", "REJECTED")
    X.h[60:] += 50.0                                                          # a later revision of the data
    SH.update(book, X, late + 1800)
    assert json.dumps(book["setups"][0], sort_keys=True) == done              # a decided record is frozen


def test_a_done_trade_is_never_recomputed_after_a_data_revision():
    o, h, l, c = flat(150)
    for i in range(1, 150):
        o[i], l[i], c[i], h[i] = 4001.0, 4000.5, 4001.0, 4002.0
    h[6] = 4010.5
    X = ctx(o, h, l, c)
    rec = _rec(limit=None, market=4000.0, key="k", order_close=T0 + 900, timely=True, p_ref=4000.0)
    book = {"started_utc": T0, "setups": [rec], "days": [], "verdicts": {}}
    SH.update(book, X, T0 + 900 * 140)
    assert rec["status"] == "DONE" and rec["out"][0] == "TP"
    frozen = json.dumps(rec, sort_keys=True)
    X.h[6], X.l[6] = 4001.0, 3989.0                                           # the vendor revises the bar: now a stop
    SH.update(book, X, T0 + 900 * 141)
    assert json.dumps(rec, sort_keys=True) == frozen


def test_nothing_before_the_start_and_the_repeat_rule():
    X = _breakout_ctx()
    book = {"started_utc": int(X.t[54]) + 901, "setups": [], "days": [], "verdicts": {}}
    SH.update(book, X, int(X.t[60]))
    assert book["setups"] == []                                               # its order bar closed before the start
    book = {"started_utc": int(X.t[0]), "setups": [{"key": "x", "module": "C", "dir": 1, "order_t": int(X.t[50]),
                                                     "p_ref": 4005.0, "status": "MISSED", "timely": True}],
            "days": [], "verdicts": {}}
    SH.update(book, X, int(X.t[54]) + 1000)
    assert book["setups"][-1]["status"] == "REPEAT"                           # same side within 4 h and $15


# ---------------- streaming equals one pass, on synthetic engine payloads ----------------
@pytest.fixture(scope="module")
def payloads():
    out = {}
    for tf in ("15m", "1h", "4h"):
        m = load_synthetic(tf, bars=1600, seed=11)
        res = engine.run(m, DEFAULT)
        ctrl = engine.run(m, DEFAULT, "control", res.F)
        out[tf] = report.build(m, res, ctrl, DEFAULT, holdout.load_or_freeze(None, DEFAULT))
    return out


def test_report_publishes_the_rows_on_15m_only_and_the_freeze_key_is_unchanged(payloads):
    ch = payloads["15m"]["chart"]
    for k in ("atr", "aatr", "vwap_lo2", "vwap_up2", "eqh", "eql", "regime"):
        assert len(ch[k]) == len(ch["t"])
    assert "regime" not in payloads["1h"]["chart"] and "eqh" not in payloads["4h"]["chart"]
    assert holdout.freeze_key(DEFAULT) == "1f88aad357497da4:4440d52587f5cc6b"
    assert SH.run(None, payloads, 0)["status"].startswith("no live 15m payload")   # synthetic data is never recorded


def test_recording_bar_by_bar_equals_one_pass(payloads):
    p15 = payloads["15m"]
    t = p15["chart"]["t"]
    n, k0 = len(t), len(t) - 400

    def trunc(k):
        ch = {key: (v[:k] if isinstance(v, list) and len(v) == n else v) for key, v in p15["chart"].items()}
        return {"meta": p15["meta"], "chart": ch, "markers": [m for m in p15["markers"] if m["t"] <= t[k - 1]]}
    start = t[k0 - 1] + 900
    a = {"started_utc": start, "setups": [], "days": [], "verdicts": {}}
    for k in range(k0, n + 1):
        SH.update(a, SH.context(trunc(k), payloads["1h"], payloads["4h"]), t[k - 1] + 900 + 120)
    b = {"started_utc": start, "setups": [], "days": [], "verdicts": {}}
    SH.update(b, SH.context(p15, payloads["1h"], payloads["4h"]), t[-1] + 900 + 120)
    strip = lambda r: {x: v for x, v in r.items() if x not in ("recorded_utc", "timely")}
    assert a["setups"], "the synthetic window should produce setups"
    assert [strip(r) for r in a["setups"]] == [strip(r) for r in b["setups"]]
    assert all(r["timely"] for r in a["setups"]) and len({r["key"] for r in a["setups"]}) == len(a["setups"])


# ---------------- statistics and the registered look ----------------
def test_statistics_by_hand():
    assert SH.wilson(5, 13) == [0.1771, 0.6448]
    assert SH.sign_p(3, 0) == 0.125 and SH.sign_p(0, 0) == 1.0
    assert SH.sign_p(6, 2) == pytest.approx((math.comb(8, 6) + math.comb(8, 7) + 1) / 256)
    assert SH.t975(1) == 12.706 and SH.t975(30) == 2.042 and SH.t975(60) == pytest.approx(1.96 + 2.372 / 60)
    tr = [{"day": "d1", "ladder_r": 1.0}, {"day": "d1", "ladder_r": 0.0}, {"day": "d2", "ladder_r": 1.0}]
    m = np.array([0.5, 1.0])
    half = 12.706 * m.std(ddof=1) / math.sqrt(2)
    assert SH.day_ci(tr) == [round(0.75 - half, 4), round(0.75 + half, 4)]


def _done(i, unit, own_tp1, mir_tp1, r):
    return {"key": f"{unit}{i}", "module": unit, "dir": 1, "status": "DONE", "timely": True, "fill_t": T0 + 900 * i,
            "exit_t": T0 + 900 * i + 900, "day": f"d{i % 40}", "out": ["TP" if own_tp1 else "SL", "SL", "SL"],
            "ladder_r": r, "ladder_r_op": r, "mfe": 1.0, "mae": 1.0, "mirror": {"out": ["TP" if mir_tp1 else "SL"] * 3}}


def test_the_look_is_once_at_100_with_holm_and_the_deadline():
    book = {"setups": [_done(i, "C", i % 4 != 0, i % 4 == 0, 0.3 + 0.01 * (i % 7)) for i in range(120)], "verdicts": {}}
    v = SH.verdicts(book, T0)
    assert book["verdicts"]["C"]["at_n"] == 100 and v["C"] == "SUPPORTED" and v["A"] == "COLLECTING"
    frozen = dict(book["verdicts"]["C"])
    book["setups"] += [_done(200 + i, "C", False, True, -1.0) for i in range(50)]
    SH.verdicts(book, T0 + 10**6)
    assert book["verdicts"]["C"] == frozen                                    # the look happens once
    weak = {"setups": [_done(i, "D", i % 2 == 0, i % 2 == 1 and i % 10 != 1, 0.2) for i in range(100)], "verdicts": {}}
    assert SH.verdicts(weak, T0)["D"] in ("HOLM PENDING", "NOT SUPPORTED")
    mid = [_done(i, "B", True, False, 0.3 + 0.01 * (i % 7)) for i in range(30)] \
        + [_done(30 + i, "B", False, True, 0.3 + 0.01 * (i % 7)) for i in range(17)] \
        + [_done(47 + i, "B", True, True, 0.3 + 0.01 * (i % 7)) for i in range(53)]
    pend = {"setups": mid, "verdicts": {}}
    assert 0.05 / 6 <= SH.sign_p(30, 17) < 0.05
    assert SH.verdicts(pend, T0)["B"] == "HOLM PENDING"                       # depends on units not yet looked at
    assert SH.verdicts(pend, after_deadline())["B"] == "NOT SUPPORTED"        # the others count as p = 1: Holm says no
    neg = {"setups": [_done(i, "E", True, False, -0.1) for i in range(100)], "verdicts": {}}
    assert SH.verdicts(neg, T0)["E"] == "NOT SUPPORTED"                       # money below zero: never supported
    assert SH.verdicts({"setups": [], "verdicts": {}}, after_deadline())["A"] == "INSUFFICIENT"


def after_deadline() -> int:
    return int(np.datetime64("2027-07-01T00:00:00").astype("datetime64[s]").astype(np.int64))


# ---------------- isolation: the alert run ----------------
def test_a_tracker_failure_never_stops_the_alert_run(tmp_path, monkeypatch):
    from quantum import notify as N
    from tests.test_alert_sixty import T, _pay
    monkeypatch.setattr(N, "send", lambda lines: ["test"] if lines else [])
    monkeypatch.setattr(SH, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    rep = N.run(str(tmp_path), {"15m": _pay("15m", T - 900)}, ["15m"], sent_t=T)
    assert rep["shadow"] == {"id": SH.ID, "error": "RuntimeError: boom"}
    assert "plans" in rep and "grab_test" in rep                              # the rest of the run went ahead


# ---------------- what each bar may know (direct; the streaming test passes these inputs whole) ----------------
def test_htf_trend_reads_only_completed_bars():
    p = {"chart": {"t": [T0, T0 + 3600], "ema20": [2.0, 0.0], "ema100": [1.0, 1.0]}}
    up, dn = SH.htf_trend(np.array([T0 + 3600, T0 + 3600 + 1800, T0 + 7200]), p, 3600)
    assert list(up) == [True, True, False] and list(dn) == [False, False, True]   # the 2nd bar counts once it is closed
    up, dn = SH.htf_trend(np.array([T0 + 900]), p, 3600)
    assert not up[0] and not dn[0]                                                # nothing completed yet: no trend


def test_pools_exist_only_after_their_period():
    h = np.array([5.0, 7.0, 6.0, 9.0, 8.0, 4.0])
    l = np.array([1.0, 2.0, 3.0, 0.5, 2.0, 3.0])
    flag = np.array([True, True, False, True, False, False])
    hi, lo, _ = SH.last_completed_session(flag, h, l, np.array(["d"] * 6, object))
    assert np.isnan(hi[0]) and np.isnan(hi[1]) and hi[2] == 7.0 and lo[2] == 1.0 and hi[3] == 7.0   # run 2 still open
    assert hi[4] == 9.0 and lo[4] == 0.5                                           # the 2nd run, only after it ended
    key = np.array(["a", "a", "b", "b", "c", "c"], object)
    assert list(SH.prev_group(key, h, "max")[2:]) == [7.0, 7.0, 9.0, 9.0] and np.isnan(SH.prev_group(key, h, "max")[0])
    import pandas as pd
    cal = pd.DataFrame({"trading_date": pd.to_datetime(["2026-11-16"] * 3), "in_asian": [False] * 3,
                        "in_london": [False] * 3, "in_ny": [False] * 3})
    pools, _ = SH.build_pools(h[:3], l[:3], cal, np.array([np.nan, 10.0, 20.0]), np.array([np.nan] * 3))
    assert np.isnan(pools["EQH"][1]) and pools["EQH"][2] == 10.0                  # the engine's level at the bar before
    assert np.isnan(pools["CDH"][0]) and pools["CDH"][1] == 5.0 and pools["CDH"][2] == 7.0
