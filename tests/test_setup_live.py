"""Live SETUP alerts (quantum/notify.py, the operator's level rules, research/registrations/B16.json): detected on the
site's 15m bars, sent as their own notification with the plan, then scored +$15 before -$13 in their own record."""
import json

import pytest

from quantum import notify

T0 = 1793973600                                   # 2026-11-06 14:00 UTC (Friday)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("PLAN", "PLAN_LOT", "PLAN_SL_USD", "PLAN_TP_USD", "PLAN_TP2_USD", "ALERT_SETUPS", "ALERT_STRUCTURE", "ALERT_LIQUIDITY",
              "MT5_PRICE_OFFSET"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ALERT_STRUCTURE", "0")


def _p15(bars, gen="2026-11-06T14:40:00+00:00"):
    """bars: (t, h, l, c)."""
    n = len(bars)
    ch = {"t": [b[0] for b in bars], "h": [b[1] for b in bars], "l": [b[2] for b in bars], "c": [b[3] for b in bars],
          "pdh": [4147.6] * n, "pdl": [4058.44] * n, "pwh": [4081.97] * n, "pwl": [3871.19] * n,
          "vpoc": [4059.0] * n, "vah": [4075.0] * n, "val": [4040.0] * n,
          "ob_bull_lo": [None] * n, "ob_bull_hi": [None] * n, "ob_bear_lo": [None] * n, "ob_bear_hi": [None] * n}
    return {"meta": {"tf": "15m", "synthetic": False, "generated_utc": gen, "price_source": "td"}, "markers": [], "decisions": [],
            "news": None, "chart": ch}


def _p5(bars):
    return {"meta": {"tf": "5m", "synthetic": False, "price_source": "td"}, "markers": [], "decisions": [], "news": None,
            "chart": {"t": [b[0] for b in bars], "o": [b[1] for b in bars], "h": [b[2] for b in bars], "l": [b[3] for b in bars],
                      "c": [b[4] for b in bars]}}


def test_setup_alert_is_sent_alone_then_scored_once(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send", lambda lines: sent.append(list(lines)) or ["test"])
    store = str(tmp_path)
    base = [(T0, 4066.0, 4061.0, 4062.0)]
    notify.run(store, {"15m": _p15(base)}, ["15m"], sent_t=T0 + 1000)                   # first run: position only
    sweep = base + [(T0 + 900, 4063.0, 4055.22, 4060.10)]                               # PDL 4058.44 swept at the POC
    notify.run(store, {"15m": _p15(sweep)}, ["15m"], sent_t=T0 + 1800 + 380)
    alert = [b for b in sent if b and b[0].startswith("XAUUSD 15m SETUP #1 BUY (your rules)")]
    assert len(alert) == 1
    a = alert[0]
    assert "liquidity sweep: previous day low 4058.44 swept (low 4055.22), closed back above at 4060.10 | at POC 4059.00" in a[0]
    assert any(x.startswith("ENTRY 4060.10 | SL 4047.10 (-$650) | TP1 4073.10 (close half, SL to entry) | +$15 at 4075.10 | TP2 4080.10")
               for x in a)
    assert any("information, not a confirmed signal" in x for x in a)
    st = json.loads((tmp_path / notify.STATE).read_text())
    assert len(st["setups"]) == 1 and st["setups"][0]["tp"] == 4075.10 and st["setups"][0]["sl"] == 4047.10
    notify.run(store, {"15m": _p15(sweep)}, ["15m"], sent_t=T0 + 2400)                  # nothing new: nothing repeated
    assert sum(1 for b in sent if b and b[0].startswith("XAUUSD 15m SETUP #")) == 1
    p5 = _p5([(T0 + 1800, 4060.0, 4070.0, 4058.0, 4069.0), (T0 + 2100, 4069.0, 4075.5, 4066.0, 4075.0)])
    later = sweep + [(T0 + 1800, 4076.0, 4058.0, 4075.0)]
    notify.run(store, {"15m": _p15(later), "5m": p5}, ["15m"], sent_t=T0 + 2700 + 300)
    upd = [x for b in sent for x in b if x.startswith("XAUUSD 15m SETUP #1 BUY from 4060.10:")]
    assert upd == ["XAUUSD 15m SETUP #1 BUY from 4060.10: +$15 reached first (4075.10)"]
    rec = json.loads((tmp_path / "research_forward" / notify.SETUP_FILE).read_text())
    assert rec["live"] == {"SWEEP": [1, 1]} and rec["setups"][0]["result"] == "TP" and rec["setups"][0]["path"] == "5m"


def test_setups_can_be_turned_off(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send", lambda lines: sent.append(list(lines)) or ["test"])
    monkeypatch.setenv("ALERT_SETUPS", "0")
    store = str(tmp_path)
    base = [(T0, 4066.0, 4061.0, 4062.0)]
    notify.run(store, {"15m": _p15(base)}, ["15m"], sent_t=T0 + 1000)
    rep = notify.run(store, {"15m": _p15(base + [(T0 + 900, 4063.0, 4055.22, 4060.10)])}, ["15m"], sent_t=T0 + 2000)
    assert not any(b and b[0].startswith("XAUUSD 15m SETUP") for b in sent) and "setups" not in rep


def test_record_line_and_major_levels_switch(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send", lambda lines: sent.append(list(lines)) or ["test"])
    store = str(tmp_path)
    base = [(T0, 4066.0, 4061.0, 4062.0)]
    notify.run(store, {"15m": _p15(base)}, ["15m"], sent_t=T0 + 1000)
    notify.run(store, {"15m": _p15(base + [(T0 + 900, 4063.0, 4055.22, 4060.10)])}, ["15m"], sent_t=T0 + 2000)
    a = next(b for b in sent if b and b[0].startswith("XAUUSD 15m SETUP #1"))
    assert any(x.startswith("3-year record of this rule (2020-22, B16): +$15 before -$13 47% of 5,918 (random 46%): not an edge")
               for x in a)
    monkeypatch.setenv("SETUP_LEVELS", "major")                 # the same bar sweeping only a 1h low: no alert
    p = _p15(base + [(T0 + 900, 4063.0, 4055.22, 4060.10)])
    p["chart"]["pdl"] = [4000.0] * 2
    h1 = {"meta": {"tf": "1h", "synthetic": False, "price_source": "td"},
          "chart": {"t": [T0 - 3600], "h": [4070.0], "l": [4058.5], "c": [4062.0]}}
    assert notify.setup_scan({"15m": p, "1h": h1}, T0, {}) == []
    monkeypatch.setenv("SETUP_LEVELS", "all")
    assert [e["levels"] for e in notify.setup_scan({"15m": p, "1h": h1}, T0, {})] == [[("1HL", 4058.5)]]
