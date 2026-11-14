"""Stale-signal protection (operator, 2026-11-11): a signal recovered after an outage is never presented as a fresh
trade; a delayed plan is issued only after a fresh market-price check; records stay exactly as before.

The outage replica is the real case: after the 2026-11-10 deploy-gate outage the 15m SELL of 16:15 UTC (entry 4024.98)
reached the phone at 21:35, 306 minutes after its bar closed, as a normal plan; it then hit its stop (-$650)."""
import json
from datetime import UTC, datetime

import pytest

from quantum import notify as N

C = 1794328200                    # 2026-11-10 16:30 UTC: the close of the 16:15 15m bar
ENTRY = 4024.98
PLAN_KEYS = {"id", "tf", "t", "dir", "entry", "sl", "tp", "tp2", "tp2_usd", "sl_usd", "tp_usd", "lot", "t_dec", "session", "dow",
             "tq", "t_alert", "px_alert", "move_alert", "late"}      # the plan record as written before 2026-11-11


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("PLAN", "PLAN_LOT", "PLAN_SL_USD", "PLAN_TP_USD", "PLAN_TP2_USD", "MT5_PRICE_OFFSET", "ALERT_LIQUIDITY",
              "PLAN_LATE_FRAC", "ALERT_MODE", "ALERT_SETUPS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ALERT_STRUCTURE", "0")
    monkeypatch.setenv("ALERT_LIQUIDITY", "0")
    monkeypatch.setenv("ALERT_SETUPS", "0")
    monkeypatch.setenv("CONFIRM_PANEL", "0")


def _iso(t):
    return datetime.fromtimestamp(t, UTC).isoformat()


def _pay(t_last, markers=(), forming=None, gen=None, hi=None, lo=None, n=24):
    """A 15m payload whose bars end at t_last; forming = the live price of this download (generated at gen)."""
    t = [t_last - i * 900 for i in range(n - 1, -1, -1)]
    c = [4025.0] * n
    h = [hi.get(x, 4025.0) if hi else 4025.0 for x in t]
    lo_ = [lo.get(x, 4025.0) if lo else 4025.0 for x in t]
    meta = {"tf": "15m", "synthetic": False, "generated_utc": _iso(gen or t_last + 960), "price_source": "td",
            "forming": {"t": t_last + 900, "c": forming} if forming is not None else None}
    return {"meta": meta, "markers": list(markers), "decisions": [], "dashboard": {},
            "chart": {"t": t, "o": c, "h": h, "l": lo_, "c": c}}


def _sig(t=C - 900, px=ENTRY, d=-1):
    return {"t": t, "type": "SIGNAL", "dir": d, "px": px, "tq": 74, "sl": px + 30.32, "tp1": px - 24.98, "tp2": px - 150, "tp3": px - 160}


def _run(tmp_path, payload, sent_t, sent, first=True):
    store = str(tmp_path)
    if first:                                                      # the run before: position only, nothing replayed
        N.run(store, {"15m": _pay(C - 1800)}, ["15m"], sent_t=C - 1500)
    return N.run(store, {"15m": payload}, ["15m"], sent_t=sent_t)


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(N, "send", lambda lines: out.append(N.without_disclaimer(lines)) or (["test"] if lines else []))
    return out


def _flat(sent):
    return [x for b in sent for x in b]


# ---- the decision itself ----------------------------------------------------------------------------------------

def _now(t, px=None, t_px=None, live=True):
    return {"t": t, **({"px": px, "t_px": t_px, "live": live} if px is not None else {})}


@pytest.mark.parametrize(("age", "state"), [(0, "FRESH"), (900, "FRESH"), (901, "DELAYED"), (3600, "DELAYED"),
                                            (3601, "NOT ACTIONABLE")])
def test_the_limits_are_one_scheduler_cycle_and_one_hour(age, state):
    fz = N.freshness(C, -1, ENTRY, 13.0, 13.0, _now(C + age, 4025.5, C + age - 60), [])
    assert fz["state"] == state and N.FRESH_SEC == 900 and N.RECOVERY_SEC == 3600 and N.PRICE_FRESH_SEC == 300


def test_a_delayed_plan_needs_a_live_recent_price():
    assert "no live price" in N.freshness(C, -1, ENTRY, 13, 13, _now(C + 1200), [])["why"]
    assert "no live price" in N.freshness(C, -1, ENTRY, 13, 13, _now(C + 1200, 4025.5, C + 1200 - 301), [])["why"]
    assert "no live price" in N.freshness(C, -1, ENTRY, 13, 13, _now(C + 1200, 4025.5, C + 1140, live=False), [])["why"]
    assert N.freshness(C, -1, ENTRY, 13, 13, _now(C + 1200, 4025.5, C + 1200 - 300), [])["state"] == "DELAYED"


def test_a_delayed_plan_fails_when_price_moved_past_the_late_limit_or_a_level_traded():
    moved = N.freshness(C, -1, ENTRY, 13, 13, _now(C + 1200, ENTRY + 3.90, C + 1140), [])   # 30% of 13 = 3.90, against
    assert moved["state"] == "NOT ACTIONABLE" and "moved $3.90" in moved["why"]
    ok = N.freshness(C, -1, ENTRY, 13, 13, _now(C + 1200, ENTRY + 3.89, C + 1140), [])
    assert ok["state"] == "DELAYED"
    stop = N.freshness(C, -1, ENTRY, 13, 13, _now(C + 1200, ENTRY, C + 1140), [_pay(C, hi={C: ENTRY + 13.0})])
    assert stop["state"] == "NOT ACTIONABLE" and "stop" in stop["why"]
    tgt = N.freshness(C, -1, ENTRY, 13, 13, _now(C + 1200, ENTRY, C + 1140), [_pay(C, lo={C: ENTRY - 13.0})])
    assert tgt["state"] == "NOT ACTIONABLE" and "first target" in tgt["why"]
    before = N.freshness(C, -1, ENTRY, 13, 13, _now(C + 1200, ENTRY, C + 1140), [_pay(C, hi={C - 900: ENTRY + 20})])
    assert before["state"] == "DELAYED"                            # the signal bar itself (before the close) never counts


# ---- end to end through the alerts ----------------------------------------------------------------------------------

def test_the_outage_replica_is_not_actionable_and_its_record_is_unchanged(tmp_path, sent):
    t_send = C + 306 * 60                                          # 21:36 UTC, as on 2026-11-10
    pay = _pay(C + 17100, [_sig()], forming=4027.84, gen=t_send - 60)
    rep = _run(tmp_path, pay, t_send, sent)
    flat = _flat(sent)
    assert not any(x.startswith("XAUUSD 15m SELL (confirmed close)") for x in flat)
    assert not any(x.startswith(("YOUR PLAN", "ON MT5", "LADDER", "TIMING")) for x in flat)
    na = [x for x in flat if x.startswith("XAUUSD NOT ACTIONABLE: 1 engine signal recovered late")]
    assert len(na) == 1 and "SELL at 4024.98" in na[0] and "306 min after the close (limit 60)" in na[0]
    plan = rep["plans"]["open"][0]                                 # the registered tests still see the signal
    assert set(plan) == PLAN_KEYS and plan["entry"] == ENTRY and plan["sl"] == 4037.98 and plan["tp"] == 4011.98
    st = json.loads((tmp_path / N.STATE).read_text())
    assert st["fresh_gate"]["plan:1"]["state"] == "NOT ACTIONABLE"
    assert rep["fresh_gate"]["recent"][0]["key"] == "plan:1"


def test_a_not_actionable_plans_results_stay_off_the_phone(tmp_path, sent):
    t_send = C + 306 * 60
    _run(tmp_path, _pay(C + 17100, [_sig()], forming=4027.84, gen=t_send - 60), t_send, sent)
    n0 = len(sent)
    hit = _pay(C + 18000, [_sig()], hi={C + 18000: 4040.0})        # the stop trades
    rep = N.run(str(tmp_path), {"15m": hit}, ["15m"], sent_t=C + 18000 + 300)
    assert not any("SL 4037.98 HIT" in x for x in _flat(sent[n0:]))
    web = [x for x in rep["15m"]["lines"] if "SL 4037.98 HIT" in x]
    assert len(web) == 1 and web[0].startswith(N.RECORD_ONLY + "XAUUSD 15m YOUR PLAN SELL from 4024.98")
    st = json.loads((tmp_path / N.STATE).read_text())
    assert st["plan_log"][-1]["result"] == "SL" and st["plan_tally"] == {"SL": 1}   # recorded and scored as before


def test_a_delayed_plan_with_a_valid_price_check_is_issued_and_labelled(tmp_path, sent):
    t_send = C + 20 * 60
    _run(tmp_path, _pay(C + 900, [_sig()], forming=4026.0, gen=t_send - 60), t_send, sent)
    msg = next(b for b in sent if b and b[0].startswith("XAUUSD 15m SELL (confirmed close)"))
    assert msg[1].startswith("DELAYED ALERT: sent 20 min after the bar closed") and "re-checked" in msg[1].lower()
    assert any(x.startswith("YOUR PLAN") for x in msg) and any(x.startswith("ON MT5") for x in msg)


def test_a_delayed_plan_without_a_live_price_is_not_actionable(tmp_path, sent):
    t_send = C + 20 * 60
    _run(tmp_path, _pay(C + 900, [_sig()]), t_send, sent)
    flat = _flat(sent)
    assert not any(x.startswith(("XAUUSD 15m SELL", "YOUR PLAN")) for x in flat)
    assert any("no live price to re-check it" in x for x in flat)


def test_a_fresh_alert_is_byte_identical_to_before(tmp_path, sent):
    t_send = C + 5 * 60
    pay = _pay(C, [_sig()], forming=4025.5, gen=t_send - 60)
    rep = _run(tmp_path, pay, t_send, sent)
    now = {"t": t_send, "px": 4025.5, "t_px": t_send - 60, "live": True}
    ctx_old = {"repeats": {}, "breaks": [], "h_records": N.h_records(str(tmp_path), "15m")}        # no "fresh": the old path
    assert rep["15m"]["lines"] == N.messages(pay, C - 1800, now, ctx_old)
    msg = next(b for b in sent if b and b[0].startswith("XAUUSD 15m SELL (confirmed close)"))
    assert msg == N.messages(pay, C - 1800, now, ctx_old, signals_only=True)
    assert not any(x.startswith(("DELAYED", "XAUUSD NOT ACTIONABLE", N.RECORD_ONLY)) for x in _flat(sent))
    assert "fresh_gate" not in json.loads((tmp_path / N.STATE).read_text())


def test_the_phone_never_gets_a_record_only_line():
    assert N.phone_only(["a", N.RECORD_ONLY + "b", "c"]) == ["a", "c"]


# ---- setups and the grab test: same rule, records untouched -------------------------------------------------------

def test_a_recovered_setup_is_not_actionable_and_its_record_keeps_its_fields(tmp_path, sent, monkeypatch):
    monkeypatch.setenv("ALERT_SETUPS", "1")
    monkeypatch.setenv("ALERT_MODE", "all")
    ev = {"t": C - 900, "dir": -1, "close": ENTRY, "kind": "BREAKOUT", "levels": [("PDL", 4030.0)], "zones": ["PDL"],
          "checks": {"major": True, "trend": True, "bias": True, "session": True}, "confirmed": True}
    monkeypatch.setattr(N, "setup_scan", lambda payloads, since, seen: [ev])
    t_send = C + 306 * 60
    rep = _run(tmp_path, _pay(C + 17100, forming=4027.84, gen=t_send - 60), t_send, sent)
    flat = _flat(sent)
    assert not any(x.startswith("XAUUSD 15m SETUP") for x in flat)
    assert any(x.startswith("XAUUSD NOT ACTIONABLE: 1 setup alert recovered late") for x in flat)
    assert all(x.startswith(N.RECORD_ONLY) for x in rep["setup_alerts"][-1]["lines"]) and rep["setup_alerts"][-1]["sent"] == []
    st = json.loads((tmp_path / N.STATE).read_text())
    s = st["setups"][-1]
    assert s["phone"] is True and s["entry"] == ENTRY and "fresh" not in s and st["fresh_gate"][f"setup:{s['id']}"]["state"] == "NOT ACTIONABLE"


def test_a_recovered_grab_test_trade_is_not_actionable_and_the_b9_record_is_unchanged(tmp_path, sent, monkeypatch):
    monkeypatch.setenv("ALERT_MODE", "all")
    t_send = C + 306 * 60
    tr = {"t": C - 900, "tf": "15m", "dir": -1, "entry": ENTRY, "tp": ENTRY - 13, "sl": ENTRY + 13, "pools": ["PDH"],
          "levels": [4030.0], "status": "OPEN"}
    calls = {"n": 0}

    def fake_new(p, since, started, seen):
        calls["n"] += 1
        return [dict(tr)] if calls["n"] == 1 else []
    monkeypatch.setattr(N, "grab_new", fake_new)
    rep = _run(tmp_path, _pay(C + 17100, forming=4027.84, gen=t_send - 60), t_send, sent)
    flat = _flat(sent)
    assert not any(x.startswith("XAUUSD 15m GRAB FORWARD TEST") for x in flat)
    assert any(x.startswith("XAUUSD NOT ACTIONABLE: 1 grab test trade recovered late") for x in flat)
    assert any(x.startswith(N.RECORD_ONLY + "XAUUSD 15m GRAB FORWARD TEST #1") for x in rep["grab_test_alert"]["lines"])
    book = json.loads((tmp_path / "research_forward" / "B9-GRAB-FWD.json").read_text())
    assert set(book["trades"][0]) == set(tr) | {"id", "alert"}     # the registered record: no new field


# ---- delivery: a channel counts as sent only on HTTP 2xx, and every attempt is logged without secrets -------------

class _R:
    def __init__(self, code, body=None):
        self.status_code, self._b = code, body

    def json(self):
        return self._b


def test_send_counts_only_http_2xx_and_logs_every_attempt(tmp_path, monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "secret-topic-xyz")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    N._DELIVERIES.clear()
    monkeypatch.setattr(N.requests, "post", lambda *a, **k: _R(200, {"id": "abc123", "time": 1}))
    assert N.send(["XAUUSD 15m SELL test", "line 2"]) == ["ntfy"]
    monkeypatch.setattr(N.requests, "post", lambda *a, **k: _R(500))
    assert N.send(["XAUUSD second"]) == []

    def boom(*a, **k):
        raise OSError("down")
    monkeypatch.setattr(N.requests, "post", boom)
    assert N.send(["XAUUSD third"]) == []
    got = N.save_deliveries(str(tmp_path))
    assert [(g["http"], g["ok"], g["id"]) for g in got] == [(200, True, "abc123"), (500, False, None), (None, False, None)]
    assert got[2]["error"] == "OSError" and got[0]["first"] == "XAUUSD 15m SELL test" and got[0]["lines"] == 2
    text = (tmp_path / N.DELIVERY).read_text()
    assert "secret-topic-xyz" not in text and len(json.loads(text)) == 3 and N._DELIVERIES == []


def test_a_delayed_repeat_of_a_not_actionable_plan_is_not_actionable_either(tmp_path, sent):
    """The 3 November replay: plan #1 recovered 110 min late (NOT ACTIONABLE); a later signal of the same idea, 50 min
    late with a valid price, must not be shown as a valid delayed alert: it only repeats the idea that was not actionable."""
    t_send = C + 110 * 60
    s1, s2 = _sig(t=C - 900, px=ENTRY), _sig(t=C + 3600 - 900, px=ENTRY + 1.0)          # second one closes 50 min before
    rep = _run(tmp_path, _pay(C + 5400, [s1, s2], forming=ENTRY + 0.5, gen=t_send - 60), t_send, sent)
    flat = _flat(sent)
    assert not any(x.startswith(("XAUUSD 15m SELL", "DELAYED ALERT", "YOUR PLAN")) for x in flat)
    na = next(x for x in flat if x.startswith("XAUUSD NOT ACTIONABLE: 2 engine signals"))
    assert "repeat of plan #1, which was not actionable" in na and len(rep["plans"]["open"]) == 1


# ---- hardening after the 2026-11-12 audit of the gate (display only; records unchanged) ----

def test_an_unpriced_signal_is_never_shown_late(tmp_path, sent):
    """A SIGNAL marker without a price got no freshness decision and its headline was shown however late it was."""
    t_send = C + 306 * 60
    _run(tmp_path, _pay(C + 17100, [{**_sig(), "px": None}], forming=4027.84, gen=t_send - 60), t_send, sent)
    flat = _flat(sent)
    assert not any(x.startswith("XAUUSD 15m SELL (confirmed close)") for x in flat)
    na = [x for x in flat if x.startswith("XAUUSD NOT ACTIONABLE: 1 engine signal recovered late")]
    assert len(na) == 1 and "SELL at —" in na[0] and "306 min after the close" in na[0]
    late = N.freshness(C, -1, None, 13, 13, _now(C + 1200, 4025.5, C + 1140), [])      # 20 min, live price: still no
    assert late["state"] == "NOT ACTIONABLE" and late["why"] == "no signal price to re-check it"
    assert N.freshness(C, -1, None, 13, 13, _now(C + 300), [])["state"] == "FRESH"     # in time: shown as before


def test_pruning_never_releases_a_still_tracked_not_actionable_plan(tmp_path, sent):
    """GATE_KEEP pruned the oldest decisions first; after 300 later ones a NOT ACTIONABLE plan still open lost its flag
    and its result reached the phone. Now DELAYED decisions go first, NOT ACTIONABLE ones only after GATE_HOLD_SEC."""
    t_send = C + 306 * 60
    _run(tmp_path, _pay(C + 17100, [_sig()], forming=4027.84, gen=t_send - 60), t_send, sent)
    st = json.loads((tmp_path / N.STATE).read_text())
    for i in range(N.GATE_KEEP + 50):                              # a long outage: many later decisions
        N.gate_note(st, f"setup:{1000 + i}", {"state": "DELAYED" if i % 3 == 0 else "NOT ACTIONABLE", "age_min": 30.0,
                                              "t_close": C, "t_alert": t_send})
    g = st["fresh_gate"]
    assert g["plan:1"]["state"] == "NOT ACTIONABLE" and all(v["state"] == "NOT ACTIONABLE" for v in list(g.values())[:2])
    assert sum(v["state"] == "NOT ACTIONABLE" for v in g.values()) == 1 + sum(1 for i in range(N.GATE_KEEP + 50) if i % 3)
    (tmp_path / N.STATE).write_text(json.dumps(st))
    n = len(sent)
    rep = N.run(str(tmp_path), {"15m": _pay(C + 18000, [_sig()], hi={C + 18000: 4040.0})}, ["15m"], sent_t=C + 18300)
    assert not any("SL 4037.98 HIT" in x for x in _flat(sent[n:]))                     # still website only
    assert any(x.startswith(N.RECORD_ONLY) and "SL 4037.98 HIT" in x for x in rep["15m"]["lines"])
    only = {}                                                      # all NOT ACTIONABLE and recent: nothing is dropped
    for i in range(N.GATE_KEEP + 5):
        N.gate_note(only, f"plan:{i}", {"state": "NOT ACTIONABLE", "age_min": 99.0, "t_close": C, "t_alert": C + i})
    assert len(only["fresh_gate"]) == N.GATE_KEEP + 5 and "plan:0" in only["fresh_gate"]
    edge = C + N.GATE_HOLD_SEC + 3                                 # only the ones past the hold may go (here 3 of them)
    N.gate_note(only, "plan:9998", {"state": "NOT ACTIONABLE", "age_min": 99.0, "t_close": edge, "t_alert": edge})
    assert len(only["fresh_gate"]) == N.GATE_KEEP + 3 and "plan:3" in only["fresh_gate"] and "plan:2" not in only["fresh_gate"]
    later = C + N.GATE_HOLD_SEC + 10**4                            # later still: back to the cap, oldest first
    N.gate_note(only, "plan:9999", {"state": "NOT ACTIONABLE", "age_min": 99.0, "t_close": later, "t_alert": later})
    g2 = only["fresh_gate"]
    assert len(g2) == N.GATE_KEEP and {"plan:9998", "plan:9999"} <= set(g2) and "plan:6" not in g2 and "plan:7" in g2
    assert N.GATE_HOLD_SEC > max(N.PLAN_TRACK_SEC, N.SETUP_STALE_SEC, N.GRAB_STALE)


def test_a_fresh_repeat_of_a_not_actionable_plan_does_not_imply_a_position(tmp_path, sent):
    """The REPEAT line said "still open ... don't add a trade" about a plan the operator was told not to trade."""
    _run(tmp_path, _pay(C, [_sig()], forming=4025.5, gen=C + 1200 - 400), C + 1200, sent)   # 20 min, stale price
    assert any(x.startswith("XAUUSD NOT ACTIONABLE") and "no live price" in x for x in _flat(sent))
    n = len(sent)
    t3 = C + 3600 + 300                                            # a repeat 5 min after its close: FRESH
    rep = N.run(str(tmp_path), {"15m": _pay(C + 2700, [_sig(), _sig(t=C + 2700, px=ENTRY - 3)], forming=ENTRY - 3,
                                            gen=t3 - 60)}, ["15m"], sent_t=t3)
    flat = _flat(sent[n:])
    rp = [x for x in flat if x.startswith("REPEAT of #1")]
    assert len(rp) == 1 and "which was NOT ACTIONABLE (sent late, no plan)" in rp[0] and "still open" not in rp[0]
    assert not any(x.startswith(("YOUR PLAN", "ON MT5", "LADDER")) for x in flat) and len(rep["plans"]["open"]) == 1
    plain = N.repeat_line(_sig(), "15m", {"id": 7, "tf": "15m", "entry": ENTRY, "t": C - 900, "t_dec": C})
    assert "still open" in plain and "don't add a trade" in plain                       # an actionable plan: as before
