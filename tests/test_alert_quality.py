"""Part A of the 2026-11-05 signal audit (operator: "approve A without daily loss guard"), in quantum/notify.py:
A1 one idea, one alert (REPEAT: same direction within 4 h and $15 of an open plan, any timeframe, opens no plan);
A2 the trend-change warning (same-direction BREAKs on 2+ timeframes against the higher-timeframe gate);
A3 the context line on every signal (higher timeframes, regime, session, against today's break)."""
import pytest

from quantum import notify as N

NOV3_0800 = 1793692800            # 2026-11-03 08:00 UTC (Tue)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("PLAN", "PLAN_LOT", "PLAN_SL_USD", "PLAN_TP_USD", "MT5_PRICE_OFFSET", "ALERT_LIQUIDITY", "PLAN_LATE_FRAC"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ALERT_STRUCTURE", "0")


def _plan(tf="5m", t=NOV3_0800, d=-1, e=3906.34, pid=1):
    return {"id": pid, "tf": tf, "t": t, "t_dec": t + N.TF_SEC[tf], "dir": d, "entry": e}


def test_a1_repeat_is_same_direction_within_4_hours_and_15_dollars_of_an_open_plan():
    plans = [_plan()]
    sig = {"t": NOV3_0800 + 3600, "dir": -1, "px": 3902.04}
    assert N.repeat_of(sig, "15m", plans)["id"] == 1                                  # another timeframe: still the same idea
    assert N.repeat_of({**sig, "dir": 1}, "15m", plans) is None                       # the other direction
    assert N.repeat_of({**sig, "px": 3890.0}, "15m", plans) is None                   # $16.34 away
    assert N.repeat_of({**sig, "t": NOV3_0800 + 4 * 3600 + 301}, "5m", plans) is None  # more than 4 hours later
    assert N.repeat_of(sig, "15m", []) is None                                        # no open plan
    line = N.repeat_line(sig, "15m", plans[0])
    assert line == ("REPEAT of #1 (5m SELL from 3906.34 at 08:05 UTC, still open): the same idea -- don't add a trade "
                    "(no new plan)")


def _pay(tf, t_last, markers=(), dash=None, gen="2026-11-03T10:20:00+00:00"):
    sec = N.TF_SEC[tf]
    t = [t_last - i * sec for i in range(11, -1, -1)]
    c = [3905.0] * len(t)
    return {"meta": {"tf": tf, "synthetic": False, "generated_utc": gen, "price_source": "td"},
            "markers": list(markers), "decisions": [], "dashboard": dash or {},
            "chart": {"t": t, "o": c, "h": c, "l": c, "c": c}}


def test_a1_replay_of_the_3_november_cluster_gives_one_plan_not_eight(tmp_path, monkeypatch):
    # this replay delivers a 2-hour cluster in ONE run to test the REPEAT folding; the stale-signal gate (which would
    # rightly call the oldest of them NOT ACTIONABLE) is tested on its own in tests/test_stale_signals.py
    monkeypatch.setattr(N, "FRESH_SEC", 10**9)
    sent = []
    monkeypatch.setattr(N, "send", lambda lines: sent.append(list(lines)) or ["test"])
    store = str(tmp_path)
    sig = lambda t, px: {"t": t, "type": "SIGNAL", "dir": -1, "px": px, "tq": 70, "sl": px + 10, "tp1": px - 10, "tp2": px, "tp3": px}
    N.run(store, {"5m": _pay("5m", NOV3_0800 - 300), "15m": _pay("15m", NOV3_0800 - 900)}, ["5m", "15m"], sent_t=NOV3_0800)
    m5 = [sig(NOV3_0800, 3906.34), sig(NOV3_0800 + 300, 3906.99), sig(NOV3_0800 + 3900, 3901.56),
          sig(NOV3_0800 + 4200, 3902.04), sig(NOV3_0800 + 4800, 3904.24)]
    m15 = [sig(NOV3_0800 + 3600, 3902.04), sig(NOV3_0800 + 6300, 3909.39), sig(NOV3_0800 + 7200, 3906.72)]
    rep = N.run(store, {"5m": _pay("5m", NOV3_0800 + 4800, m5), "15m": _pay("15m", NOV3_0800 + 7200, m15)}, ["5m", "15m"],
                sent_t=NOV3_0800 + 8400)
    plans = rep["plans"]["open"]
    assert len(plans) == 1 and plans[0]["entry"] == 3906.34 and plans[0]["id"] == 1                # 1 trade, not 8
    assert len(rep["plans"]["repeats"]) == 7 and {r["of_id"] for r in rep["plans"]["repeats"]} == {1}
    flat = [x for b in sent for x in b]
    assert sum(x.startswith("YOUR PLAN") for x in flat) == 1 and sum(x.startswith("REPEAT of #1") for x in flat) == 7


def test_a3_context_line_reads_the_layers_above_the_chart_and_flags_a_break_against_it():
    dash = {"mtf": {"scores": {"5": 50, "15": 50, "60": 20.0, "240": 0.0, "D": 70.0}, "align_long": 1, "align_short": 2},
            "regime": {"label": "STRONG TR"}, "session": {"label": "LON-KZ"}}
    p = _pay("15m", NOV3_0800, dash=dash)
    s = N.context_line(p, -1, [])
    assert s == "CONTEXT (now): higher timeframes 1h ▼ 4h ▼ 1D ▲ (2 agree, 1 against) | regime STRONG TR | session LON-KZ"
    brk = [{"kind": "BREAK", "tf": "15m", "t": NOV3_0800 - 900, "name": "PDH", "px": 3969.2}]
    assert s + " | ⚠ against today's PDH 3969.20 break (15m, 08:00 UTC)" == N.context_line(p, -1, brk)
    assert "⚠" not in N.context_line(p, 1, brk)                                     # a BUY agrees with an upside break
    assert N.context_line(_pay("4h", NOV3_0800, dash=dash), -1, []).startswith("CONTEXT (now): higher timeframes 1D ▲")
    assert N.context_line(_pay("15m", NOV3_0800), -1, []) is None                    # no dashboard: no line


def test_a2_trend_change_warning_once_per_direction_per_day():
    NOV4_0600 = NOV3_0800 + 86400 - 2 * 3600
    brk = [{"kind": "BREAK", "tf": "15m", "t": NOV4_0600 - 1800, "name": "PDH", "px": 3969.2},
           {"kind": "BREAK", "tf": "30m", "t": NOV4_0600 - 1800, "name": "PDH", "px": 3969.2}]
    pays = {"15m": _pay("15m", NOV4_0600, dash={"mtf": {"align_short": 3, "align_long": 0}})}
    state: dict = {}
    out = N.turn_lines(state, pays, ["15m", "30m"], brk, [], NOV4_0600 + 60)
    assert len(out) == 1 and out[0].startswith("XAUUSD TREND-CHANGE WARNING: price closed above PDH 3969.20 on 15m, 30m today")
    assert "higher-timeframe gate still blocks BUY signals (3 higher timeframes read down; it lags)" in out[0]
    assert "Don't SELL into it" in out[0] and out[0].endswith("info, not a trade signal")
    assert N.turn_lines(state, pays, ["15m", "30m"], brk, [], NOV4_0600 + 960) == []            # once a day
    assert N.turn_lines({}, pays, ["15m"], brk[:1], [], NOV4_0600 + 60) == []                    # one timeframe only
    free = {"15m": _pay("15m", NOV4_0600, dash={"mtf": {"align_short": 0}})}
    assert N.turn_lines({}, free, ["15m"], brk, [], NOV4_0600 + 60) == []                       # nothing against it
    sells = [{"dir": -1, "t_dec": NOV4_0600 - 7200, "tf": "15m", "t": NOV4_0600 - 8100}]
    w = N.turn_lines({}, free, ["15m"], brk, sells, NOV4_0600 + 60)
    assert len(w) == 1 and "today's 1 alerted signal(s) were SELL" in w[0]


def test_part_a_reaches_the_site():
    with open("site/app.js") as f:
        js = f.read()
    assert "REPEAT of #" in js and "Trend-change warnings" in js
    assert (N.REPEAT_SEC, N.REPEAT_USD, N.TURN_MIN_TFS) == (4 * 3600, 15.0, 2)
