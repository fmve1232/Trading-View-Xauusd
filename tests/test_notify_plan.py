"""The operator's plan in every SIGNAL alert (quantum/notify.py): levels from the fixed money stop / target at a fixed
lot, one follow-up alert when TP or SL is hit, nothing repeated, and the engine untouched (notify.py is outside the
freeze key)."""
import json

import pytest

from quantum import holdout, notify


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("PLAN", "PLAN_LOT", "PLAN_SL_USD", "PLAN_TP_USD", "PLAN_COST_PER_LOT", "MT5_PRICE_OFFSET", "ALERT_STRUCTURE"):
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
    assert pl["open"][0]["tp"] == 4013.0 and pl["recent"] == [] and pl["tfs"] == ["15m"]
    assert rep["channels"] == ["ntfy"] and "secret-topic-name" not in json.dumps(rep)


def test_notify_stays_outside_the_frozen_engine():
    assert "notify.py" not in holdout.ENGINE_SOURCES
