"""B9-GRAB-FWD (research/registrations/B9-GRAB-FWD.json): the registered live test of the liquidity GRAB. One trade per
pool per trading day at the first timeframe, entry at the bar's close, +$13 / -$13 on 5-minute bars for one trading day
with quantum/trade_race.py's rules, verdict only at 30, 40 ... 100 decided results, record kept in the store."""
import json

import numpy as np
import pytest

from quantum import notify as N
from quantum import trade_race as TR

T0 = 1793692800                  # 2026-11-03 08:00 UTC (Tue)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("PLAN", "PLAN_LOT", "PLAN_SL_USD", "PLAN_TP_USD", "MT5_PRICE_OFFSET", "ALERT_LIQUIDITY", "PLAN_LATE_FRAC",
              "MT5_SERVER_UTC_OFFSET", "ALERT_LOCAL_TZ"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ALERT_STRUCTURE", "0")


def _tf(tf, t_last, markers=(), closes=None, src="twelvedata:XAU/USD"):
    sec = N.TF_SEC[tf]
    t = [t_last - i * sec for i in range(5, -1, -1)]
    c = closes or [4000.0] * len(t)
    return {"meta": {"tf": tf, "synthetic": False, "generated_utc": "2026-11-03T09:00:00+00:00", "price_source": src},
            "markers": list(markers), "decisions": [], "chart": {"t": t, "c": c, "h": c, "l": c, "o": c}}


def _p5(t0, ohlc, src="twelvedata:XAU/USD"):
    t = [t0 + 300 * i for i in range(len(ohlc))]
    return {"meta": {"tf": "5m", "synthetic": False, "price_source": src, "generated_utc": "2026-11-03T09:00:00+00:00"},
            "markers": [], "decisions": [], "chart": {"t": t, "o": [x[0] for x in ohlc], "h": [x[1] for x in ohlc],
                                                      "l": [x[2] for x in ohlc], "c": [x[3] for x in ohlc]}}


def _sweep(t, d=1, pools=(("PDL", 3990.0),)):
    return {"t": t, "type": "SWEEP", "dir": d, "px": 3989.0 if d == 1 else 4011.0,
            "lvl": [{"name": n, "px": p} for n, p in pools]}


def test_one_trade_per_pool_per_day_the_first_timeframe_wins():
    seen: dict = {}
    t = T0                                                    # a 15m bar opening at 08:00, closing 08:15
    p15 = _tf("15m", t, [_sweep(t, 1, (("PDL", 3990.0), ("PWL", 3989.5)))])
    new = N.grab_new(p15, t - 1, started=T0 - 3600, seen=seen)
    assert len(new) == 1 and new[0]["pools"] == ["PDL", "PWL"] and new[0]["dir"] == 1          # two pools, one trade
    assert new[0]["entry"] == 4000.0 and (new[0]["tp"], new[0]["sl"]) == (4013.0, 3987.0) and new[0]["t_close"] == t + 900
    p1h = _tf("1h", t, [_sweep(t, 1, (("PDL", 3990.0),))])
    assert N.grab_new(p1h, t - 1, T0 - 3600, seen) == []      # the same pool later on 1h: already tested today
    again = _tf("15m", t + 900, [_sweep(t + 900, 1, (("PDL", 3990.0),))])
    assert N.grab_new(again, t, T0 - 3600, seen) == []        # swept again the same day: nothing
    nxt = T0 + 86400
    assert len(N.grab_new(_tf("15m", nxt, [_sweep(nxt)]), nxt - 1, T0 - 3600, seen)) == 1        # next trading day
    assert N.grab_new(_tf("15m", t, [_sweep(t, -1, (("PDH", 4012.0),))]), t - 1, started=t + 900, seen={}) == []  # before start
    sell = N.grab_new(_tf("15m", t, [_sweep(t, -1, (("PDH", 4012.0),))]), t - 1, T0 - 3600, {})[0]
    assert sell["dir"] == -1 and (sell["tp"], sell["sl"]) == (3987.0, 4013.0)


def _tr(d=1, e=4000.0, t_close=T0, src="twelvedata:XAU/USD"):
    return {"id": 1, "tf": "15m", "t": t_close - 900, "t_close": t_close, "dir": d, "entry": e, "tp": e + d * 13,
            "sl": e - d * 13, "src": src, "status": "OPEN", "pools": ["PDL"], "levels": [3990.0], "mfe": 0.0, "mae": 0.0}


def test_resolution_on_five_minute_bars_with_the_race_rules():
    flat = (4000, 4001, 3999, 4000)
    r = N.grab_resolve(_tr(), _p5(T0, [flat, (4000, 4013.1, 3995, 4010)]), T0 + 900)
    assert r["status"] == "TP" and r["t_res"] == T0 + 300 and r["bars"] == 2 and r["mfe"] == pytest.approx(13.1)
    assert N.grab_resolve(_tr(), _p5(T0, [flat, (4000, 4005, 3986.9, 3990)]), T0 + 900)["status"] == "SL"
    both = N.grab_resolve(_tr(), _p5(T0, [(4000, 4014, 3986, 4000)]), T0 + 900)
    assert both["status"] == "SL"                                                     # both in one bar: a loss ...
    assert N.grab_resolve(_tr(), _p5(T0, [(4013.5, 4014, 3986, 4000)]), T0 + 900)["status"] == "TP"   # ... unless it opened beyond TP
    short = N.grab_resolve(_tr(d=-1), _p5(T0, [(4000, 4002, 3986.9, 3990)]), T0 + 900)
    assert short["status"] == "TP"
    part = N.grab_resolve(_tr(), _p5(T0, [flat] * 10), T0 + 3000)
    assert part["status"] == "OPEN"                                                   # still inside the day
    none = N.grab_resolve(_tr(), _p5(T0, [flat] * N.GRAB_H), T0 + 86400)
    assert none["status"] == "NONE" and none["bars"] == N.GRAB_H                     # not counted
    assert N.grab_resolve(_tr(), _p5(T0 + 600, [flat] * 5), T0 + 3000)["status"] == "GAP"          # path start not stored
    other = _tr(src="yahoo:GC=F")
    assert N.grab_resolve(other, _p5(T0, [flat]), T0 + 3000)["status"] == "OPEN"     # another source: wait ...
    assert N.grab_resolve(other, _p5(T0, [flat]), T0 + N.GRAB_STALE + 1)["status"] == "GAP"       # ... then GAP


def test_resolution_matches_trade_race_on_random_paths(monkeypatch):
    monkeypatch.setattr(TR, "TP_GRID", (13.0,))
    monkeypatch.setattr(TR, "SL_GRID", (13.0,))
    g = np.random.default_rng(4)
    n = 6000
    c = 4000 + np.cumsum(g.normal(0, 1.1, n))
    o = np.r_[c[0], c[:-1]] + g.normal(0, 0.3, n)
    h = np.maximum(o, c) + g.exponential(0.6, n)
    l = np.minimum(o, c) - g.exponential(0.6, n)
    t = T0 + 300 * np.arange(n)
    path = {"t": t, "o": o, "h": h, "l": l, "c": c, "H": TR.HORIZON_SEC // 300}
    p5 = {"meta": {"synthetic": False, "price_source": "td"}, "chart": {"t": t.tolist(), "o": o.tolist(), "h": h.tolist(), "l": l.tolist()}}
    starts = np.arange(5, n - 300, 37)
    for d in (1, -1):
        mine = [N.grab_resolve(_tr(d=d, e=float(c[k - 1]), t_close=int(t[k]), src="td"), p5, int(t[-1]) + 300)["status"]
                for k in starts]
        ref = TR.race(path, t[starts], c[starts - 1], np.full(len(starts), d))
        assert mine.count("TP") == ref["win"][0][0] and mine.count("SL") == ref["loss"][0][0]
        assert mine.count("NONE") == ref["n"] - ref["win"][0][0] - ref["loss"][0][0]


def _decided(results, t0=T0):
    return [{"id": i + 1, "status": s, "t_res": t0 + i} for i, s in enumerate(results)]


def test_verdict_is_checked_only_at_the_registered_looks():
    s = N.grab_verdict(_decided(["TP"] * 25 + ["SL"] * 4), {}, T0)
    assert s["verdict"] is None and s["checks"] == [] and "first check at 30" in s["status"]    # 86% on 29: no verdict
    s = N.grab_verdict(_decided(["TP"] * 21 + ["SL"] * 9), {}, T0)
    assert s["verdict"]["verdict"] == "PROVEN" and s["verdict"]["at_n"] == 30                  # 21 / 30: lower bound > 51%
    s20 = N.grab_verdict(_decided(["TP"] * 20 + ["SL"] * 10), {}, T0)
    assert s20["verdict"] is None and s20["checks"][0]["proven"] is False and s20["next_check"] == 40
    book = {"checks": s["checks"], "verdict": s["verdict"]}
    later = N.grab_verdict(_decided(["TP"] * 21 + ["SL"] * 40), book, T0)
    assert later["verdict"]["verdict"] == "PROVEN" and later["verdict"]["at_n"] == 30          # final once given
    jump = N.grab_verdict(_decided(["SL"] * 12 + ["TP"] * 21), {}, T0)                          # 33 decided in one go:
    assert [c["n"] for c in jump["checks"]] == [30] and jump["checks"][0]["tp"] == 18           # judged on the first 30
    coin = N.grab_verdict(_decided(["TP", "SL"] * 50), {}, T0)
    assert coin["verdict"]["verdict"] == "NOT PROVEN" and len(coin["checks"]) == 8
    late = N.grab_verdict(_decided(["TP", "SL"] * 5), {}, 1806580800)                         # 2027-04-01 12:00 UTC
    assert late["verdict"]["verdict"] == "NOT PROVEN"


def test_run_records_alerts_follows_up_and_keeps_the_record(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(N, "send", lambda lines: sent.append(N.without_disclaimer(lines)) or ["test"])
    store = str(tmp_path)
    t = T0
    base = {"15m": _tf("15m", t - 900), "1h": _tf("1h", t - 3600), "5m": _p5(t - 3000, [(4000, 4001, 3999, 4000)] * 10)}
    N.run(store, base, ["15m", "1h"], sent_t=t - 60)                         # first run: start, replay nothing
    book = json.loads((tmp_path / N.GRAB_DIR / N.GRAB_FILE).read_text())
    assert book["trades"] == [] and book["started_utc"] == t - 60
    sw = _sweep(t, 1, (("PDL", 3990.0),))
    pays = {"15m": _tf("15m", t, [sw]), "1h": _tf("1h", t, [sw]), "5m": _p5(t - 3000, [(4000, 4001, 3999, 4000)] * 13)}
    rep = N.run(store, pays, ["15m", "1h"], sent_t=t + 900 + 400)
    test_msg = [b for b in sent if any("GRAB FORWARD TEST" in x for x in b)]
    assert len(test_msg) == 1
    msg = test_msg[0]
    assert msg[0].startswith("XAUUSD 15m GRAB FORWARD TEST #1: BUY after PDL 3990.00 swept, closed back above at 4000.00")
    assert any(x.startswith("TEST TRADE: entry 4000.00 TP 4013.00 (+$650) SL 3987.00 (-$650) | ON MT5: BUY at market, "
                            "then SL = your fill - 13.00, TP = your fill + 13.00") for x in msg)
    assert any(x.startswith("TIMING: bar closed 08:15 UTC") for x in msg)
    assert msg[-1].startswith("Registered test B9-GRAB-FWD, not a proven signal: COLLECTING: no result yet")
    assert rep["grab_test"]["counts"]["OPEN"] == 1 and rep["grab_test"]["open"][0]["tf"] == "15m"   # 1h saw it second
    sent.clear()
    up = [(4000, 4001, 3999, 4000)] * 15 + [(4000, 4013.4, 3999, 4012)]
    pays["5m"] = _p5(t - 3000, up)
    rep = N.run(store, pays, ["15m", "1h"], sent_t=t + 2400)
    done = [x for b in sent for x in b if x.startswith("XAUUSD GRAB TEST #1")]
    assert len(done) == 1 and "TP 4013.00 HIT +$650" in done[0] and "1 results, 100% TP first; first check at 30" in done[0]
    book = json.loads((tmp_path / N.GRAB_DIR / N.GRAB_FILE).read_text())
    assert book["trades"][0]["status"] == "TP" and rep["grab_test"]["counts"]["TP"] == 1 and rep["grab_test"]["n"] == 1
    sent.clear()
    N.run(store, pays, ["15m", "1h"], sent_t=t + 3000)                       # nothing repeated
    assert not any("GRAB" in x for b in sent for x in b)


def test_the_record_is_saved_with_git_history_on_the_forward_ledger():
    with open(".github/workflows/quantum-site.yml") as f:
        wf = f.read()
    assert "cp -r store/research_forward/. ledger/research_forward/" in wf                  # saved with history
    assert "cp -r ledger/research_forward store/" in wf                                     # restored if the store lost it
    with open("research/registrations/B9-GRAB-FWD.json") as f:
        reg = json.load(f)
    assert reg["approved_by_operator"] is True and reg["rule"]["take_profit_price"] == N.GRAB_TP == 13.0
    assert reg["rule"]["stop_loss_price"] == N.GRAB_SL == 13.0 and reg["rule"]["timeframes"].startswith("15m, 30m, 1h, 4h")
    assert N.GRAB_LOOKS == (30, 40, 50, 60, 70, 80, 90, 100) and N.GRAB_DEADLINE == "2027-03-31"
    assert N.GRAB_BE == pytest.approx(0.51, abs=1e-3)
