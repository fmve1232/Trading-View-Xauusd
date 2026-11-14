"""Every phone trading alert and follow-up opens with the operator's disclaimer (approved 2026-11-13), and nothing else
changes: not the alert's own lines, not the website's lines, not the plans, the plan validation or any research record.

The scenario is the daily-validation one of test_notify_plan.py: a 15m BUY, its TP1 follow-up, then the daily and weekly
reports after the New York close. Every test runs in sixty mode (the production default: ALERT_MODE unset) and in
quality mode (the mode tests/conftest.py gives every other test)."""
import json
import os
from datetime import datetime, timezone

import pytest

from quantum import notify

APPROVED = ("RECORD — NOT A VALIDATED SIGNAL — NO TRADE",
            "This is a research-engine alert, not a trading recommendation. The strategy has not yet demonstrated a "
            "validated live trading edge.")


def _set_env(monkeypatch, mode):
    for k in ("PLAN", "PLAN_LOT", "PLAN_SL_USD", "PLAN_TP_USD", "PLAN_COST_PER_LOT", "MT5_PRICE_OFFSET", "ALERT_STRUCTURE",
              "PLAN_LATE_FRAC", "MT5_SERVER_UTC_OFFSET", "ALERT_LOCAL_TZ", "ALERT_LIQUIDITY", "LIQ_NEAR_USD",
              "ACCOUNT_USD", "DAILY_LIMIT_PCT", "PLAN_TP2_USD", "ALERT_MODE", "NTFY_TOPIC", "TELEGRAM_BOT_TOKEN",
              "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ALERT_STRUCTURE", "0")
    monkeypatch.setenv("PLAN_TP2_USD", "0")
    if mode == "sixty":
        monkeypatch.delenv("ALERT_MODE", raising=False)    # unset: sixty, as in production
    else:
        monkeypatch.setenv("ALERT_MODE", mode)
    assert notify.alert_mode() == mode


@pytest.fixture(autouse=True, params=["sixty", "quality"])
def mode(request, monkeypatch):
    _set_env(monkeypatch, request.param)
    return request.param


def _ts(s):
    return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp())


def _payload(t_last, markers, bars, now):
    return {"meta": {"tf": "15m", "synthetic": False, "generated_utc": now}, "markers": markers, "decisions": [],
            "news": None, "chart": {"t": [b[0] for b in bars] + [t_last], "h": [b[1] for b in bars] + [None],
                                    "l": [b[2] for b in bars] + [None]}}


T0 = _ts("2026-11-06 14:00")                       # Friday, London + New York
SIG = {"t": T0 + 900, "type": "SIGNAL", "dir": 1, "px": 4000.0, "tq": 70, "sl": 3990.0, "tp1": 4010.0, "tp2": 4020.0,
       "tp3": 4030.0}
RUNS = [  # (t_last, now, markers, bars); each run is sent at its `now`, 5 minutes after its newest bar as in production
    (T0, "2026-11-06T14:05:00+00:00", [], []),
    (T0 + 1800, "2026-11-06T14:35:00+00:00", [SIG], [(T0 + 900, 4001, 3999)]),                       # the alert: FRESH
    (T0 + 2700, "2026-11-06T14:50:00+00:00", [SIG], [(T0 + 900, 4001, 3999), (T0 + 1800, 4013.5, 3998)]),   # TP1 hit
    (T0 + 2700, "2026-11-06T22:10:00+00:00", [], []),                                               # daily + weekly
]


def _scenario(tmp_path, monkeypatch, disclaimer=True):
    """Run the four runs; return (raw messages handed to send, reports, the store's files)."""
    if not disclaimer:                                     # the code before 2026-11-13 sent exactly the alert's lines
        monkeypatch.setattr(notify, "trade_msg", lambda lines: list(lines))
    raw = []
    monkeypatch.setattr(notify, "send", lambda lines: raw.append(list(lines)) or (["test"] if lines else []))
    store = str(tmp_path)
    reps = [notify.run(store, {"15m": _payload(t, list(m), list(b), now)}, ["15m"], sent_t=_ts(now[:16].replace("T", " ")))
            for t, now, m, b in RUNS]
    files = {}
    for root, _, fs in os.walk(store):
        for f in fs:
            p = os.path.join(root, f)
            files[os.path.relpath(p, store)] = open(p, "rb").read()
    return raw, reps, files


def test_the_wording_is_exactly_the_approved_text():
    assert notify.TRADE_DISCLAIMER == APPROVED


def test_never_a_lone_disclaimer():
    assert notify.trade_msg([]) == []
    assert notify.trade_msg(["XAUUSD 15m SELL"]) == [*APPROVED, "XAUUSD 15m SELL"]
    assert notify.without_disclaimer([*APPROVED, "a", "b"]) == ["a", "b"]


def test_it_survives_the_phone_filter():
    """phone_only drops RECORD ONLY lines; the disclaimer starts with 'RECORD —', a different prefix."""
    assert not APPROVED[0].startswith(notify.RECORD_ONLY)
    assert notify.phone_only(notify.trade_msg(["x"])) == [*APPROVED, "x"]


def test_the_signal_alert_and_its_follow_up_open_with_it(tmp_path, monkeypatch):
    raw, _, _ = _scenario(tmp_path, monkeypatch)
    alert = next(m for m in raw if any(x.startswith("XAUUSD 15m BUY") for x in m))
    follow = next(m for m in raw if any("TP" in x and "HIT" in x for x in m))
    for m in (alert, follow):
        assert tuple(m[:2]) == APPROVED
        assert sum(x in APPROVED for x in m) == 2               # once per message, never repeated inside it
    assert alert[2].startswith("XAUUSD 15m BUY")              # the alert's own first line comes right after


def test_reports_are_not_trading_alerts_and_carry_no_disclaimer(tmp_path, monkeypatch):
    raw, _, _ = _scenario(tmp_path, monkeypatch)
    reports = [m for m in raw if any("VALIDATION" in x for x in m)]
    assert reports and all(m[0].startswith("XAUUSD DAILY VALIDATION") for m in reports)
    assert not any(x in APPROVED for m in reports for x in m)


def test_only_the_disclaimer_is_added_and_no_record_changes(tmp_path, monkeypatch, mode):
    """With and without the disclaimer: the same messages minus the two lines, the same website lines, the same store
    files byte for byte (alert state, plan log, plan validation, research records)."""
    new_raw, new_reps, new_files = _scenario(tmp_path / "new", monkeypatch, disclaimer=True)
    monkeypatch.undo()
    _set_env(monkeypatch, mode)
    old_raw, old_reps, old_files = _scenario(tmp_path / "old", monkeypatch, disclaimer=False)
    assert [notify.without_disclaimer(m) for m in new_raw] == old_raw
    assert sum(1 for m in new_raw if tuple(m[:2]) == APPROVED) == 2      # the alert and its follow-up
    assert [r.get("15m", {}).get("lines") for r in new_reps] == [r.get("15m", {}).get("lines") for r in old_reps]
    assert [r.get("plans") for r in new_reps] == [r.get("plans") for r in old_reps]
    assert new_files.keys() == old_files.keys() and new_files == old_files
    assert notify.VALIDATION in new_files and notify.STATE in new_files


def test_the_delivery_log_still_names_the_alert(monkeypatch):
    """alerts_delivery.json keeps the alert's first own line, not the disclaimer."""

    class R:
        status_code = 200

        @staticmethod
        def json():
            return {"id": "abc"}
    monkeypatch.setenv("NTFY_TOPIC", "test-topic-not-real")
    monkeypatch.setattr(notify.requests, "post", lambda *a, **k: R())
    notify._DELIVERIES.clear()
    assert notify.send(notify.trade_msg(["XAUUSD 15m SELL (confirmed close) | entry 3871.20", "YOUR PLAN 0.5 lot"])) == ["ntfy"]
    rec = notify._DELIVERIES.pop()
    assert rec["first"].startswith("XAUUSD 15m SELL") and rec["lines"] == 4 and rec["http"] == 200
    notify._DELIVERIES.clear()


def test_every_trading_send_site_wraps_and_no_report_site_does():
    """The policy, pinned at the source: trading alerts and their follow-ups (engine plans, setups, 4h breakouts, their
    late notices, the grab test's trades) go through trade_msg; reports, news, the registered test's checks, the
    trend-change warning and liquidity lines do not. A new send site has to be classified here."""
    import inspect
    import re
    src = inspect.getsource(notify.run)
    sites = {}
    for m in re.finditer(r'report(?:\[(\w+|"[a-z_0-9]+")\]|\.setdefault\("([a-z_0-9]+)")[^\n]*?send\(([^\n]*)', src):
        key = (m.group(1) or m.group(2)).strip('"')
        sites.setdefault(key, []).append(m.group(3).startswith("trade_msg("))
    trading = {"tf", "setup_alerts", "setup_stale", "setup_updates", "h4_alerts", "h4_stale", "grab_test_alert"}
    other = {"turn_warning", "engine_test_alert", "liquidity_near", "validation_report", "news"}
    assert set(sites) == trading | other, set(sites) ^ (trading | other)
    for k in trading:
        assert all(sites[k]), f"{k} must open with the disclaimer"
    for k in other:
        assert not any(sites[k]), f"{k} is not a trading alert"
