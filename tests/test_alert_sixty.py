"""ALERTS WITH MORE THAN 60% SUCCESSFUL TRADES ONLY (operator, 2026-11-06): ALERT_MODE "sixty", the default, sends the
phone only the engine's 15m signals (the one stream above 60% on history) with their plan follow-ups. The other
timeframes' signals still open plans, so the registered B15 test records them exactly as before."""
import pytest

from quantum import notify as N

T = 1793692800                    # 2026-11-03 08:00 UTC (Tue)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("PLAN", "PLAN_LOT", "PLAN_SL_USD", "PLAN_TP_USD", "MT5_PRICE_OFFSET", "ALERT_LIQUIDITY", "PLAN_LATE_FRAC", "ALERT_MODE"):
        monkeypatch.delenv(k, raising=False)                     # ALERT_MODE unset: the default
    monkeypatch.setenv("ALERT_STRUCTURE", "0")


def _pay(tf, t_last, markers=()):
    sec = N.TF_SEC[tf]
    t = [t_last - i * sec for i in range(11, -1, -1)]
    c = [3905.0] * len(t)
    return {"meta": {"tf": tf, "synthetic": False, "generated_utc": "2026-11-03T09:20:00+00:00", "price_source": "td"},
            "markers": list(markers), "decisions": [], "dashboard": {}, "chart": {"t": t, "o": c, "h": c, "l": c, "c": c}}


def _sig(t, px, d):
    return {"t": t, "type": "SIGNAL", "dir": d, "px": px, "tq": 70, "sl": px - 10 * d, "tp1": px + 10 * d, "tp2": px, "tp3": px}


def test_the_default_is_sixty_and_keeps_quality_filters(monkeypatch):
    assert N.alert_mode() == "sixty" and N.sixty() and N.quality()
    monkeypatch.setenv("ALERT_MODE", "")                         # the workflow passes an unset variable as empty
    assert N.alert_mode() == "sixty"
    monkeypatch.setenv("ALERT_MODE", "quality")
    assert N.quality() and not N.sixty()
    monkeypatch.setenv("ALERT_MODE", "all")
    assert not N.quality() and not N.sixty()


def test_only_15m_signals_reach_the_phone_and_every_plan_is_still_recorded(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(N, "send", lambda lines: sent.append(list(lines)) or ["test"] if lines else [])
    store = str(tmp_path)
    N.run(store, {"15m": _pay("15m", T - 900), "1h": _pay("1h", T - 3600)}, ["15m", "1h"], sent_t=T)   # position only
    pay = {"15m": _pay("15m", T, [_sig(T, 3906.34, -1)]), "1h": _pay("1h", T, [_sig(T, 3950.0, 1)])}
    rep = N.run(store, pay, ["15m", "1h"], sent_t=T + 3600 + 300)
    flat = [x for b in sent for x in b]
    assert any(x.startswith("XAUUSD 15m SELL (confirmed close) | entry 3906.34") for x in flat)
    assert N.SIGNAL_RECORD["15m"] in flat and N.SIGNAL_RECORD["15m"].startswith("RECORD of 15m engine signals")
    assert not any(x.startswith("XAUUSD 1h") for x in flat) and rep["1h"]["sent"] == []
    assert any(x.startswith("XAUUSD 1h BUY (confirmed close)") for x in rep["1h"]["lines"])          # still on the website
    assert sorted(p["tf"] for p in rep["plans"]["open"]) == ["15m", "1h"]                          # B15 sees both plans
    assert rep["plans"]["mode"] == "sixty" and rep["plans"]["phone_tfs"] == ["15m"]


def test_quality_mode_still_sends_every_alerted_timeframe(tmp_path, monkeypatch):
    monkeypatch.setenv("ALERT_MODE", "quality")
    sent = []
    monkeypatch.setattr(N, "send", lambda lines: sent.append(list(lines)) or ["test"] if lines else [])
    store = str(tmp_path)
    N.run(store, {"15m": _pay("15m", T - 900), "1h": _pay("1h", T - 3600)}, ["15m", "1h"], sent_t=T)
    pay = {"15m": _pay("15m", T, [_sig(T, 3906.34, -1)]), "1h": _pay("1h", T, [_sig(T, 3950.0, 1)])}
    N.run(store, pay, ["15m", "1h"], sent_t=T + 3600 + 300)
    flat = [x for b in sent for x in b]
    assert any(x.startswith("XAUUSD 1h BUY (confirmed close)") for x in flat)
    assert N.SIGNAL_RECORD["15m"] not in flat                                                       # sixty-mode line only
