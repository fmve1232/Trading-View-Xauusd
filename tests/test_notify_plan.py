"""The operator's plan in every SIGNAL alert (quantum/notify.py): levels from the fixed money stop / target at a fixed
lot, one follow-up alert when TP or SL is hit, nothing repeated, and the engine untouched (notify.py is outside the
freeze key)."""
import json

import pytest

from quantum import holdout, notify


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("PLAN", "PLAN_LOT", "PLAN_SL_USD", "PLAN_TP_USD", "PLAN_COST_PER_LOT", "MT5_PRICE_OFFSET", "ALERT_STRUCTURE",
              "PLAN_LATE_FRAC", "MT5_SERVER_UTC_OFFSET", "ALERT_LOCAL_TZ", "ALERT_LIQUIDITY", "LIQ_NEAR_USD"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ALERT_STRUCTURE", "0")


def test_defaults_are_the_operators_650_plan_and_levels_follow_the_direction():
    pl = notify.plan_cfg()
    assert (pl["lot"], pl["sl_usd"], pl["tp_usd"]) == (0.5, 650.0, 650.0) and pl["sl_px"] == pytest.approx(13.0)
    assert notify.plan_levels(4000.0, 1, pl) == pytest.approx((3987.0, 4013.0))
    assert notify.plan_levels(4000.0, -1, pl) == pytest.approx((4013.0, 3987.0))
    line = notify.plan_line(4000.0, -1, pl, off=-2.61)
    assert "YOUR PLAN 0.5 lot: SL 4010.39 (-$650) TP 3984.39 (+$650)" in line and "TP first ~50%" in line and "break-even 51%" in line


def test_variables_change_the_plan_and_plan_0_turns_it_off(monkeypatch):
    monkeypatch.setenv("PLAN_LOT", "0.25")
    monkeypatch.setenv("PLAN_TP_USD", "325")
    pl = notify.plan_cfg()
    assert pl["sl_px"] == pytest.approx(26.0) and pl["tp_px"] == pytest.approx(13.0)
    assert "TP first ~67%" in notify.plan_line(4000.0, 1, pl)
    monkeypatch.setenv("PLAN_LOT", "nonsense")
    assert notify.plan_cfg()["lot"] == 0.5
    monkeypatch.setenv("PLAN", "0")
    assert notify.plan_cfg() is None


def _chart(rows):
    return {"t": [r[0] for r in rows], "h": [r[1] for r in rows], "l": [r[2] for r in rows]}


def test_first_touch_after_the_signal_bar():
    pl = {"tf": "15m", "t": 100, "dir": 1, "entry": 4000.0, "sl": 3987.0, "tp": 4013.0, "sl_usd": 650, "tp_usd": 650}
    assert notify.plan_result(pl, _chart([(100, 4020, 3980), (200, 4005, 3995)])) is None       # the signal bar itself is ignored
    assert notify.plan_result(pl, _chart([(100, 4020, 3980), (200, 4005, 3995), (300, 4013.5, 3999)])) == ("TP", 300)
    assert notify.plan_result(pl, _chart([(200, 4001, 3986.9), (300, 4020, 3999)])) == ("SL", 200)
    assert notify.plan_result(pl, _chart([(200, 4014, 3986)])) == ("BOTH", 200)
    short = {**pl, "dir": -1, "sl": 4013.0, "tp": 3987.0}
    assert notify.plan_result(short, _chart([(200, 4001, 3986.5)])) == ("TP", 200)


def test_updates_send_once_and_expire():
    pl = {"tf": "15m", "t": 100, "dir": 1, "entry": 4000.0, "sl": 3987.0, "tp": 4013.0, "sl_usd": 650, "tp_usd": 650}
    other = {**pl, "tf": "1h"}
    lines, keep, done = notify.plan_updates([pl, other], "15m", _chart([(200, 4013.2, 3999)]), 200)
    assert len(lines) == 1 and "TP 4013.00 HIT +$650 -- trade closed in profit" in lines[0] and keep == [other]
    assert done[0]["result"] == "TP" and done[0]["t_res"] == 200
    lines, keep, done = notify.plan_updates([pl], "15m", _chart([(200, 4005, 3995)]), 200)
    assert lines == [] and keep == [pl] and done == []
    lines, keep, done = notify.plan_updates([pl], "15m", _chart([(200, 4005, 3995)]), 100 + notify.PLAN_TRACK_SEC + 1)
    assert "no TP or SL after 3 days" in lines[0] and keep == [] and done[0]["result"] == "EXPIRED"


def _payload(t_last, markers, bars):
    return {"meta": {"tf": "15m", "synthetic": False, "generated_utc": "2026-11-02T10:00:00+00:00"}, "markers": markers,
            "decisions": [], "news": None, "chart": {"t": [b[0] for b in bars] + [t_last], "h": [b[1] for b in bars] + [None],
                                                     "l": [b[2] for b in bars] + [None]}}


def test_run_end_to_end(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send", lambda lines: sent.append(list(lines)) or ["test"])
    store = str(tmp_path)
    notify.run(store, {"15m": _payload(1000, [], [])}, ["15m"])                      # first run: position only
    assert sent == []
    sig = {"t": 1900, "type": "SIGNAL", "dir": -1, "px": 4000.0, "tq": 70, "sl": 4010.0, "tp1": 3990.0, "tp2": 3980.0, "tp3": 3970.0}
    notify.run(store, {"15m": _payload(2000, [sig], [(1900, 4001, 3999)])}, ["15m"])
    assert len(sent) == 1 and sent[0][0].startswith("XAUUSD 15m SELL") and sent[0][1].startswith("YOUR PLAN 0.5 lot: SL 4013.00 (-$650) TP 3987.00")
    state = json.loads((tmp_path / notify.STATE).read_text())
    assert state["plans"][0]["tp"] == 3987.0 and state["plans"][0]["dir"] == -1
    notify.run(store, {"15m": _payload(2900, [sig], [(1900, 4001, 3999), (2000, 4003, 3990), (2900, 3995, 3986.8)])}, ["15m"])
    assert len(sent) == 2 and "TP 3987.00 HIT +$650 -- trade closed in profit" in sent[1][0] and len(sent[1]) == 1
    notify.run(store, {"15m": _payload(3800, [sig], [(1900, 4001, 3999), (2900, 3995, 3986.8)])}, ["15m"])
    assert len(sent) == 3 and sent[2] == []                                           # nothing repeated
    st = json.loads((tmp_path / notify.STATE).read_text())
    assert st["plans"] == [] and st["plan_tally"] == {"TP": 1} and st["plan_log"][0]["result"] == "TP"


def test_report_feeds_the_website_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(notify, "send", lambda lines: [])
    monkeypatch.setenv("NTFY_TOPIC", "secret-topic-name")
    notify.run(str(tmp_path), {"15m": _payload(1000, [], [])}, ["15m"])
    sig = {"t": 1900, "type": "SIGNAL", "dir": 1, "px": 4000.0, "tq": 70, "sl": 3990.0, "tp1": 4010.0, "tp2": 4020.0, "tp3": 4030.0}
    rep = notify.run(str(tmp_path), {"15m": _payload(2000, [sig], [(1900, 4001, 3999)])}, ["15m"])
    pl = rep["plans"]
    assert pl["cfg"] == {"lot": 0.5, "sl_usd": 650.0, "tp_usd": 650.0, "cost_usd": 13.0} and pl["tp_first"] == pytest.approx(0.5)
    assert pl["open"][0]["tp"] == 4013.0 and pl["recent"] == [] and pl["tfs"] == ["15m"] and pl["late_frac"] == 0.3
    assert rep["channels"] == ["ntfy"] and "secret-topic-name" not in json.dumps(rep)


def test_notify_stays_outside_the_frozen_engine():
    assert "notify.py" not in holdout.ENGINE_SOURCES


# ---------------- validation: daily / weekly success rate and where it lags ----------------
def test_sessions_and_the_new_york_trading_day():
    t = int(pd_ts("2026-11-02 21:59"))                 # 16:59 New York (EST): still Monday's trading day
    assert notify.trading_day(t) == "2026-11-02" and notify.trading_day(t + 60) == "2026-11-03"
    assert notify.session_of(int(pd_ts("2026-11-02 03:00"))) == "Asia" and notify.session_of(int(pd_ts("2026-11-02 13:00"))) == "London+NY"
    sun = int(pd_ts("2026-11-08 23:30"))               # Sunday evening session belongs to Monday
    assert notify.trading_day(sun) == "2026-11-09" and notify.trading_week(sun) == "2026-W46"
    fri_close = int(pd_ts("2026-11-06 22:10"))          # Friday after 17:00 New York: the weekend belongs to next week
    assert notify.trading_day(fri_close) == "2026-11-07" and notify.trading_week(fri_close) == "2026-W46"
    assert notify.trading_week(int(pd_ts("2026-11-06 14:00"))) == "2026-W45"


def pd_ts(s):
    from datetime import datetime, timezone
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()


def test_path_measures_how_far_price_went_each_way():
    pl = {"t": 100, "dir": 1, "entry": 4000.0, "sl": 3987.0, "tp": 4013.0}
    r = notify.plan_path(pl, _chart([(200, 4011, 3995), (300, 4005, 3986)]))
    assert r == {"result": "SL", "t_res": 300, "mfe": 11.0, "mae": 14.0, "bars": 2}
    assert notify.plan_path(pl, _chart([(200, 4005, 3995)]))["result"] is None


def _rec(tf, res, dir_=1, session="London", mfe=0.0, mae=0.0, t=1793500000):
    e = 4000.0
    return {"tf": tf, "t": t, "t_dec": t + 900, "dir": dir_, "entry": e, "sl": e - 13 * dir_, "tp": e + 13 * dir_, "sl_usd": 650.0,
            "tp_usd": 650.0, "lot": 0.5, "result": res, "session": session, "dow": "Mon", "mfe": mfe, "mae": mae}


def test_summary_counts_money_and_flags_only_clear_evidence():
    recs = [_rec("5m", "SL", session="Asia")] * 28 + [_rec("5m", "TP", session="Asia")] * 6 + \
           [_rec("1h", "TP")] * 5 + [_rec("1h", "SL", mfe=11.0)] * 4 + [_rec("15m", "EXPIRED")]
    sm = notify.summarize(recs, 26.0)
    assert (sm["n"], sm["tp"], sm["sl"], sm["expired"]) == (43, 11, 32, 1)
    assert sm["rate"] == pytest.approx(11 / 43) and sm["expected"] == pytest.approx(0.5) and sm["break_even"] == pytest.approx(663 / 1300)
    assert sm["net_usd"] == pytest.approx(11 * 650 - 32 * 650 - 43 * 13)
    assert sm["by"]["timeframe"]["5m"]["flag"] == "WEAK" and sm["by"]["timeframe"]["1h"]["flag"] == ""     # 1h: only 9 results
    assert sm["by"]["session"]["Asia"]["flag"] == "WEAK" and sm["near_misses"] == 4
    adv = " ".join(sm["advice"])
    assert "against your 90% target" in adv and "WEAK - timeframe 5m: 6/34" in adv and "1h" not in adv.split("WEAK")[1]
    assert notify.summarize([], 26.0)["advice"][0].startswith("No validated signals yet")


def test_daily_and_weekly_reports_are_sent_once_at_the_close(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send", lambda lines: sent.append(list(lines)) or ["test"])
    store = str(tmp_path)

    def pay(t_last, now, markers=(), bars=()):
        p = _payload(t_last, list(markers), list(bars))
        p["meta"]["generated_utc"] = now
        return {"15m": p}
    t0 = int(pd_ts("2026-11-06 14:00"))                                     # Friday, London+NY
    notify.run(store, pay(t0, "2026-11-06T14:05:00+00:00"), ["15m"])
    sig = {"t": t0 + 900, "type": "SIGNAL", "dir": 1, "px": 4000.0, "tq": 70, "sl": 3990.0, "tp1": 4010.0, "tp2": 4020.0, "tp3": 4030.0}
    notify.run(store, pay(t0 + 1800, "2026-11-06T14:35:00+00:00", [sig], [(t0 + 900, 4001, 3999)]), ["15m"])
    rep = notify.run(store, pay(t0 + 2700, "2026-11-06T14:50:00+00:00", [sig], [(t0 + 900, 4001, 3999), (t0 + 1800, 4013.5, 3998)]), ["15m"])
    v = rep["plans"]["validation"]
    assert v["today"]["n"] == 1 and v["today"]["tp"] == 1 and v["all"]["rate"] == 1.0 and v["day"] == "2026-11-06"
    assert not any("VALIDATION" in x for b in sent for x in b)
    n0 = len(sent)
    notify.run(store, pay(t0 + 2700, "2026-11-06T22:10:00+00:00"), ["15m"])   # after 17:00 New York on Friday
    rep_lines = [x for b in sent[n0:] for x in b]
    assert any(x.startswith("XAUUSD DAILY VALIDATION Fri 06 Nov: 1 signals closed, TP first 1/1 = 100%") for x in rep_lines)
    assert any(x.startswith("XAUUSD WEEKLY VALIDATION 2026-W45: 1 signals closed") for x in rep_lines)
    n1 = len(sent)
    notify.run(store, pay(t0 + 2700, "2026-11-06T22:25:00+00:00"), ["15m"])
    assert not any("VALIDATION" in x for b in sent[n1:] for x in b)          # once per day / week
    n2 = len(sent)
    notify.run(store, pay(t0 + 2700, "2026-11-07T22:10:00+00:00"), ["15m"])   # Saturday: nothing to report, nothing sent
    assert not any("VALIDATION" in x for b in sent[n2:] for x in b)
    assert len(json.loads((tmp_path / notify.VALIDATION).read_text())) == 1


# ---------------- MT5 vs the site: clocks, the price now, ON MT5 distances, LATE, close calls ----------------
def _ts(s):
    from datetime import datetime
    return int(datetime.fromisoformat(s).timestamp())


def test_mt5_server_clock_is_new_york_plus_7_and_can_be_fixed(monkeypatch):
    winter, summer = _ts("2026-11-03T06:30:00+00:00"), _ts("2026-07-03T06:30:00+00:00")
    assert notify.clocks(winter) == "06:30 UTC = 08:30 MT5 = 11:30 PKT"         # after the US clock change: UTC+2
    assert notify.clocks(summer) == "06:30 UTC = 09:30 MT5 = 11:30 PKT"         # US summer time: UTC+3
    monkeypatch.setenv("MT5_SERVER_UTC_OFFSET", "3")
    assert notify.clocks(winter).startswith("06:30 UTC = 09:30 MT5")
    monkeypatch.setenv("MT5_SERVER_UTC_OFFSET", "nonsense")                     # unreadable -> the default, not a crash
    monkeypatch.setenv("ALERT_LOCAL_TZ", "Not/AZone")
    assert notify.clocks(winter) == "06:30 UTC = 08:30 MT5 = 11:30 PKT"
    monkeypatch.setenv("ALERT_LOCAL_TZ", "Europe/London")
    assert notify.clocks(winter).endswith("06:30 GMT")


def _p(tf, forming_c=None, closes=(4000.0,), t0=1000, gen="2026-11-03T06:35:27+00:00", synthetic=False):
    sec = notify.TF_SEC[tf]
    t = [t0 + i * sec for i in range(len(closes))]
    return {"meta": {"tf": tf, "synthetic": synthetic, "generated_utc": gen, "price_source": "Twelve Data XAU/USD",
                     "forming": None if forming_c is None else {"t": t[-1] + sec, "o": 1, "h": 1, "l": 1, "c": forming_c}},
            "chart": {"t": t, "c": list(closes)}}


def test_price_now_prefers_the_5m_forming_bar_then_the_last_close():
    gen = _ts("2026-11-03T06:35:27+00:00")
    assert notify.price_now({"5m": _p("5m", 4003.1), "15m": _p("15m", 4001.0)}, "15m") == {"px": 4003.1, "t": gen, "live": True}
    assert notify.price_now({"15m": _p("15m", 4001.0)}, "15m")["px"] == 4001.0                    # no 5m payload
    assert notify.price_now({"5m": _p("5m", 4003.1, synthetic=True), "15m": _p("15m", 4001.0)}, "15m")["px"] == 4001.0
    fut = _p("5m", 4031.0)
    fut["meta"]["price_source"] = "COMEX GC=F (fallback)"                     # another source: never compared with spot
    assert notify.price_now({"5m": fut, "15m": _p("15m", 4001.0)}, "15m")["px"] == 4001.0
    last = notify.price_now({"5m": _p("5m", None, (3999.0, 4002.5, None)), "15m": _p("15m")}, "15m")  # market closed
    assert last == {"px": 4002.5, "t": 1000 + 300 + 300, "live": False}                            # that bar's close time
    assert notify.price_now({}, "15m") is None


def _sig(d=-1, px=4000.0, t=1800):
    return {"t": t, "type": "SIGNAL", "dir": d, "px": px, "tq": 70, "sl": px + 10 * d * -1, "tp1": px - 10 * d * -1,
            "tp2": px, "tp3": px}


def test_signal_alert_has_fill_based_levels_timing_and_a_late_warning(monkeypatch):
    pay = {"meta": {"tf": "15m"}, "markers": [_sig(-1, t=1800)], "decisions": []}
    t_sent = 1800 + 900 + 380                                                    # 6.3 min after the bar close
    on_time = notify.messages(pay, 1000, {"t": t_sent, "px": 4001.17, "t_px": t_sent - 50, "live": True})
    assert [x.split(":")[0].split(" ")[0] for x in on_time] == ["XAUUSD", "YOUR", "ON", "TIMING"]
    assert on_time[2] == ("ON MT5: SELL at market, then SL = your fill + 13.00, TP = your fill - 13.00 "
                          "(= -$650 / +$650 at 0.5 lot, at any broker price)")
    assert "alert 6 min after the close" in on_time[3] and "$1.17 toward SL since the signal" in on_time[3]
    late = notify.messages(pay, 1000, {"t": t_sent, "px": 4003.90, "t_px": t_sent - 50, "live": True})
    assert late[1].startswith("LATE: price already moved $3.90 toward SL") and "limit $3.90 = 30% of the stop" in late[1]
    toward_tp = notify.messages(pay, 1000, {"t": t_sent, "px": 3995.0, "t_px": t_sent - 50, "live": True})
    assert toward_tp[1].startswith("LATE: price already moved $5.00 toward TP")
    monkeypatch.setenv("PLAN_LATE_FRAC", "0.5")                                 # the limit is a variable
    assert not notify.messages(pay, 1000, {"t": t_sent, "px": 3995.0, "t_px": t_sent - 50, "live": True})[1].startswith("LATE")
    buy = notify.messages({**pay, "markers": [_sig(1)]}, 1000, {"t": t_sent})    # no price known: no move, no LATE
    assert "BUY at market, then SL = your fill - 13.00, TP = your fill + 13.00" in buy[2] and buy[3].endswith("after the close")
    monkeypatch.setenv("MT5_PRICE_OFFSET", "-2.61")                             # offsets move prices, never the distances
    off = notify.messages(pay, 1000, {"t": t_sent, "px": 4001.17, "t_px": t_sent - 50, "live": True})
    assert "SL = your fill + 13.00" in off[2] and "price 3998.56" in off[3] and "$1.17 toward SL" in off[3]


def test_follow_ups_decided_by_cents_say_confirm_in_mt5():
    pl = {"tf": "15m", "t": 100, "dir": 1, "entry": 4000.0, "sl": 3987.0, "tp": 4013.0, "sl_usd": 650, "tp_usd": 650}
    clear = notify.plan_updates([pl], "15m", _chart([(200, 4014.0, 3999)]), 200)[0][0]
    assert "HIT +$650" in clear and "confirm in MT5" not in clear and " MT5 bar)" in clear
    thin = notify.plan_updates([pl], "15m", _chart([(200, 4013.2, 3999)]), 200)[0][0]
    assert "only $0.20 past TP on the site's prices: confirm in MT5" in thin
    near_tp = notify.plan_updates([pl], "15m", _chart([(200, 4012.7, 3999), (300, 4001, 3985.0)]), 300)[0][0]
    assert "SL 3987.00 HIT" in near_tp and "price came within $0.30 of TP" in near_tp and "past SL" not in near_tp
    thin_sl = notify.plan_updates([pl], "15m", _chart([(200, 4001, 3986.9)]), 200)[0][0]
    assert "only $0.10 past SL" in thin_sl and "of TP" not in thin_sl


def test_run_records_when_each_alert_went_out_and_the_move_by_then(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send", lambda lines: sent.append(list(lines)) or ["test"])
    store = str(tmp_path)
    notify.run(store, {"15m": _payload(1000, [], [])}, ["15m"])
    sig = {"t": 1900, "type": "SIGNAL", "dir": -1, "px": 4000.0, "tq": 70, "sl": 4010.0, "tp1": 3990.0, "tp2": 3980.0, "tp3": 3970.0}
    p15 = _payload(2000, [sig], [(1900, 4001, 3999)])
    p5 = _p("5m", 4004.5, gen="2026-11-02T10:00:00+00:00")
    p5["meta"]["price_source"] = p15["meta"].get("price_source")
    rep = notify.run(store, {"15m": p15, "5m": p5}, ["15m"], sent_t=1900 + 900 + 420)
    assert sent[0][1].startswith("LATE: price already moved $4.50 toward SL") and sent[0][2].startswith("YOUR PLAN")
    op = rep["plans"]["open"][0]
    assert (op["t_alert"], op["px_alert"], op["move_alert"], op["late"]) == (3220, 4004.5, -4.5, True)
    assert rep["plans"]["open"][0]["entry"] == 4000.0 and rep["plans"]["open"][0]["tp"] == 3987.0   # the plan itself is unchanged


# ---------------- liquidity alerts: NEAR a pool, GRAB (swept, closed back), BREAK (closed beyond) ----------------
T0 = 1793692800                                                     # 2026-11-03 08:00 UTC (Tue), one trading day


def _liq_payload(tf="15m", bars=(), markers=(), pools=None, forming=None, gen="2026-11-03T09:00:00+00:00"):
    """bars: (t, h, l, c, pdh, pdl)."""
    return {"meta": {"tf": tf, "synthetic": False, "generated_utc": gen, "price_source": "td", "forming": forming},
            "markers": list(markers), "decisions": [],
            "dashboard": {"liquidity": {"pools": pools or {}}},
            "chart": {"t": [b[0] for b in bars], "h": [b[1] for b in bars], "l": [b[2] for b in bars], "c": [b[3] for b in bars],
                      "pdh": [b[4] for b in bars], "pdl": [b[5] for b in bars], "pwh": [None] * len(bars), "pwl": [None] * len(bars)}}


def test_grab_is_the_engines_sweep_once_per_pool_per_day_and_timeframe():
    bars = [(T0 + i * 900, 3985, 3970, 3978.0 + i, 4069.89, 3975.83) for i in range(4)]
    sw = [{"t": T0 + i * 900, "type": "SWEEP", "dir": 1, "px": 3971.5, "lvl": [{"name": "PDL", "px": 3975.83}]} for i in range(3)]
    seen: dict = {}
    ev = notify.liquidity_events(_liq_payload(bars=bars, markers=sw), T0 - 1, seen)
    assert [(r["kind"], r["name"], r["t"]) for r in ev] == [("GRAB", "PDL", T0)]          # 3 sweep bars -> 1 alert
    assert notify.liq_text(ev[0]).startswith("XAUUSD 15m LIQUIDITY GRAB: PDL 3975.83 swept -- low 3971.50, closed back "
                                             "above at 3978.00 (sell-side liquidity taken, then rejected) | 15m bar 08:00 UTC = 10:00 MT5")
    assert notify.liquidity_events(_liq_payload(bars=bars, markers=sw), T0 - 1, seen) == []   # nothing repeated
    assert len(notify.liquidity_events(_liq_payload("1h", bars=bars, markers=sw), T0 - 1, seen)) == 1  # 1h is its own
    nxt = T0 + 86400                                                                        # next trading day: may alert again
    assert len(notify.liquidity_events(_liq_payload(bars=[(nxt, 1, 1, 3978, 1, 1)], markers=[{**sw[0], "t": nxt}]), nxt - 1, seen)) == 1
    hi = {"t": T0, "type": "SWEEP", "dir": -1, "px": 4071.0, "lvl": [{"name": "PDH", "px": 4069.89}]}
    txt = notify.liq_text(notify.liquidity_events(_liq_payload(bars=bars[:1], markers=[hi]), T0 - 1, {})[0])
    assert "PDH 4069.89 swept -- high 4071.00, closed back below at 3978.00 (buy-side liquidity taken" in txt


def test_break_is_a_close_beyond_a_pool_once_per_day():
    up = [(T0, 4070, 4060, 4068.0, 4069.89, 4006.15), (T0 + 900, 4074, 4066, 4072.1, 4069.89, 4006.15),
          (T0 + 1800, 4076, 4068, 4069.0, 4069.89, 4006.15), (T0 + 2700, 4078, 4069, 4073.0, 4069.89, 4006.15)]
    seen: dict = {}
    ev = notify.liquidity_events(_liq_payload(bars=up), T0 - 1, seen)
    assert [(r["kind"], r["name"], r["t"]) for r in ev] == [("BREAK", "PDH", T0 + 900)]    # the re-break later: same day, not repeated
    assert notify.liq_text(ev[0]).startswith("XAUUSD 15m LIQUIDITY BREAK: PDH 4069.89 broken -- closed above at 4072.10 "
                                             "(buy-side liquidity taken, price holding beyond)")
    wick = [(T0, 4070, 4060, 4068.0, 4069.89, 4006.15), (T0 + 900, 4075, 4066, 4069.5, 4069.89, 4006.15)]
    assert notify.liquidity_events(_liq_payload(bars=wick), T0 - 1, {}) == []              # wick above, close below: no break
    dn = [(T0, 4010, 4007, 4008.0, 4069.89, 4006.15), (T0 + 900, 4009, 4001, 4003.0, 4069.89, 4006.15)]
    assert [r["name"] for r in notify.liquidity_events(_liq_payload(bars=dn), T0 - 1, {})] == ["PDL"]
    later = notify.liquidity_events(_liq_payload(bars=up), T0 + 900, {})                  # only bars after since_t:
    assert [r["t"] for r in later] == [T0 + 2700]                                          # the re-break, with a fresh memory


def test_near_is_the_untaken_side_on_a_live_price_once_per_day(monkeypatch):
    pools = {"PDH": 4069.89, "PDL": 4006.15, "PWH": 4190.13, "EQH": None}
    bars = [(T0, 4060, 4050, 4058.0, 4069.89, 4006.15)]
    live = {"t": T0 + 900, "o": 4058, "h": 4066.0, "l": 4057, "c": 4065.10}
    p = {"15m": _liq_payload(bars=bars, pools=pools, forming=live)}
    seen: dict = {}
    ev = notify.liquidity_near(p, ["15m"], seen, T0 + 1000)
    assert [(r["name"], r["dist"]) for r in ev] == [("PDH", 4.79)]                       # PDL $59 away, PWH far: not near
    assert notify.liq_text(ev[0]).startswith("XAUUSD LIQUIDITY NEAR: price 4065.10 is $4.79 below PDH 4069.89 (buy-side "
                                             "liquidity above) | 09:00 UTC = 11:00 MT5 = 14:00 PKT | watch for a grab")
    assert notify.liquidity_near(p, ["15m"], seen, T0 + 1900) == []                      # once per pool per day
    taken = {"15m": _liq_payload(bars=[(T0, 4071, 4050, 4058.0, 4069.89, 4006.15)], pools=pools, forming=live)}
    assert notify.liquidity_near(taken, ["15m"], {}, T0 + 1000) == []                    # already traded through today
    above = {"15m": _liq_payload(bars=bars, pools=pools, forming={**live, "h": 4072.0, "c": 4071.0})}
    assert notify.liquidity_near(above, ["15m"], {}, T0 + 1000) == []                    # price beyond it: not "near"
    assert notify.liquidity_near({"15m": _liq_payload(bars=bars, pools=pools)}, ["15m"], {}, T0 + 1000) == []  # no live price
    monkeypatch.setenv("LIQ_NEAR_USD", "3")
    assert notify.liquidity_near(p, ["15m"], {}, T0 + 1000) == []


def test_run_sends_liquidity_alerts_publishes_them_and_can_be_turned_off(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send", lambda lines: sent.append(list(lines)) or ["test"])
    store = str(tmp_path)
    notify.run(store, {"15m": _liq_payload(bars=[(T0 - 900, 3990, 3980, 3985, 4069.89, 3975.83)])}, ["15m"], sent_t=T0)
    sw = {"t": T0, "type": "SWEEP", "dir": 1, "px": 3971.5, "lvl": [{"name": "PDL", "px": 3975.83}]}
    bars = [(T0 - 900, 3990, 3980, 3985, 4069.89, 3975.83), (T0, 3985, 3971.5, 3978.0, 4069.89, 3975.83)]
    rep = notify.run(store, {"15m": _liq_payload(bars=bars, markers=[sw])}, ["15m"], sent_t=T0 + 1200)
    assert any(x.startswith("XAUUSD 15m LIQUIDITY GRAB: PDL 3975.83") for x in sent[0])
    assert not any("SWEEP-LOW" in x for x in sent[0])                                   # not also in a structure line
    assert rep["liquidity"]["on"] is True and rep["liquidity"]["near_usd"] == 5.0
    assert rep["liquidity"]["recent"][0]["kind"] == "GRAB" and rep["liquidity"]["recent"][0]["name"] == "PDL"
    st = json.loads((tmp_path / notify.STATE).read_text())
    assert list(st["liq_seen"].values()) == ["2026-11-03"] and len(st["liq_log"]) == 1
    monkeypatch.setenv("ALERT_LIQUIDITY", "0")
    sent.clear()
    sw2 = {**sw, "t": T0 + 900, "lvl": [{"name": "PWL", "px": 3972.0}]}
    notify.run(store, {"15m": _liq_payload(bars=[*bars, (T0 + 900, 3980, 3971, 3976, 4069.89, 3975.83)], markers=[sw, sw2])},
               ["15m"], sent_t=T0 + 2100)
    assert not any("LIQUIDITY" in x for x in sent[0])
