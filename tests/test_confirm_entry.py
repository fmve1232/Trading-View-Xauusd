"""C1 (operator directive 2026-11-15): a SETUP is not an entry; a $10 confirming 15m close, fresh data, the plan recalculated
from the entry, room to TP1 and a size within the $650 budget make it ENTRY ELIGIBLE. Values are worked by hand at the N1
defaults: lot 0.46 (46 oz), sizing cost $0.97/oz -> cost $44.62, loss at the stop 46 x 13.97 = $642.62, reward with both
targets 46 x 16.50 - 44.62 = $714.38, with TP1 then the entry 46 x 6.50 - 44.62 = $254.38, net R:R 714.38 / 642.62 = 1.11."""
import json
import os

import pytest

from quantum import confirm_entry as C1
from quantum import notify as N

T0 = 1794405600                         # 2026-11-10 14:00 UTC (Tue), the signal bar's open
KEYS = ("CONFIRM_MIN_USD", "CONFIRM_CAP_USD", "PLAN", "PLAN_LOT", "PLAN_SL_USD", "PLAN_TP_USD", "PLAN_TP2_USD", "PLAN_COST_PER_LOT",
        "PLAN_RISK_PCT", "ACCOUNT_USD", "PLAN_SIZING", "PLAN_LOT_MAX", "MT5_PRICE_OFFSET")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)            # C1 as deployed: $10


def _chart(n, edits=None, base=4000.0):
    t = [T0 + 900 * k for k in range(n)]
    o, h, l, c = [base] * n, [base + 0.5] * n, [base - 0.5] * n, [base] * n
    for j, (oo, hh, ll, cc) in (edits or {}).items():
        o[j], h[j], l[j], c[j] = oo, hh, ll, cc
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "pdh": [None] * n, "pdl": [None] * n, "pwh": [None] * n, "pwl": [None] * n}


SIG = {"t": T0, "type": "SIGNAL", "dir": 1, "px": 4000.0, "tq": 70, "sl": 3990.0, "tp1": 4010.0, "tp2": 4020.0, "tp3": 4030.0}


def _run(ch, markers=(), t_now=None, state=None):
    st = state if state is not None else {}
    C1.open_from(st, {"meta": {"tf": "15m"}, "markers": [SIG]}, None)
    p15 = {"meta": {"tf": "15m"}, "chart": ch, "markers": [SIG, *markers]}
    t_now = t_now if t_now is not None else ch["t"][-1] + 900 + 60
    lines = C1.advance_all(st, p15, t_now, N.plan_cfg())
    s = (C1.book(st)["open"] + C1.book(st)["log"])[0]
    return lines, s, st


def test_the_setup_alert_says_it_is_not_an_entry():
    assert C1.on() and C1.min_usd() == 10.0
    assert C1.setup_head(SIG, "15m") == "XAUUSD 15m BUY SETUP DETECTED (signal bar closed) | NOT AN ENTRY | reference 4000.00"
    L = C1.setup_lines(SIG)
    assert L[0].startswith("WAIT FOR CONFIRMATION: a 15m close at or above 4010.00 (+$10 minimum) | +$15 4015.00 preferred | "
                           "+$20 4020.00 ideal")
    assert "CANCELLED if price trades 3987.00 (-$13)" in L[1]
    assert L[2].startswith("NO TRADE until an ENTRY ELIGIBLE alert arrives") and "not a proven edge" in L[2]


def test_a_touch_is_not_a_confirmation_and_the_close_recalculates_the_plan_and_risk():
    lines, s, _ = _run(_chart(3, {1: (4000, 4012, 4001, 4008), 2: (4008, 4013, 4007, 4012.40)}))
    names = [e[0] for e in s["events"]]
    assert names[:2] == ["SETUP_DETECTED", "REFERENCE_SET"]
    assert names.index("MOVE_10_TOUCHED") < names.index("CONFIRMED")          # touched on bar 1, confirmed on bar 2
    assert s["events"][names.index("MOVE_10_TOUCHED")][1] == T0 + 2 * 900       # the touch bar's close time
    assert s["status"] == "ACTIVE" and s["conf"]["tier"] == "MINIMUM" and s["conf"]["move"] == pytest.approx(12.40)
    p = s["plan"]
    assert (p["entry"], p["sl"], p["tp1"], p["tp2"], p["lot"]) == (4012.40, 3999.40, 4025.40, 4032.40, 0.46)
    assert p["cost_usd"] == pytest.approx(44.62) and p["risk_usd"] == pytest.approx(642.62)
    assert p["reward_both_usd"] == pytest.approx(714.38) and p["reward_tp1_usd"] == pytest.approx(254.38)
    assert p["rr_net"] == pytest.approx(714.38 / 642.62)
    assert lines[0].startswith("XAUUSD 15m BUY ENTRY ELIGIBLE: confirmed +$12.40 (MINIMUM) at the 15m close 4012.40")
    assert lines[1] == ("PLAN (recalculated from this entry): entry 4012.40 | SL 3999.40 | TP1 4025.40 (close half) | "
                        "TP2 4032.40 (the rest; stop to the entry after TP1)")
    assert lines[2] == ("RISK: account $25,000 | 2.6% = max $650 | lot 0.46 | est. cost $45 ($0.97/oz) | "
                        "loss at the stop incl. cost $643")
    assert lines[3] == ("NET: reward $714 if every target is reached, $254 if TP1 then back to the entry | net R:R 1.11 | "
                        "a $643 loss is possible on this trade")


@pytest.mark.parametrize("close, name", [(4014.99, "MINIMUM"), (4015.0, "PREFERRED"), (4019.99, "PREFERRED"), (4020.0, "IDEAL"),
                                         (4031.0, "IDEAL")])
def test_the_tier_is_read_from_the_confirming_close(close, name):
    _, s, _ = _run(_chart(2, {1: (4000, close + 0.5, 3999, close)}))
    assert s["conf"]["tier"] == name


@pytest.mark.parametrize("edit, marker, why", [
    ((4000, 4012, 3986.9, 4011), None, "price traded $13 against"),           # also closes +$11: invalidation is checked first
    ((4000, 4012, 3999, 4011), {"type": "BOS", "dir": -1}, "structure break the other way"),
    ((4000, 4012, 3999, 4011), {"type": "SIGNAL", "dir": -1, "px": 4011.0}, "opposite engine signal"),
])
def test_invalidation_comes_first(edit, marker, why):
    mk = [dict(marker, t=T0 + 900)] if marker else []
    lines, s, st = _run(_chart(2, {1: edit}), mk)
    assert s["status"] == "INVALIDATED" and why in s["why"]
    assert lines == [f"XAUUSD 15m BUY SETUP CANCELLED (reference 4000.00): {s['why']} | NO TRADE"]
    assert not C1.book(st)["open"] and C1.book(st)["log"][0]["id"] == s["id"]


def test_no_confirming_close_in_24_hours_expires():
    _, s, _ = _run(_chart(98))
    assert s["status"] == "EXPIRED" and "24 h" in s["why"]
    _, s, _ = _run(_chart(96))
    assert s["status"] == "PENDING"                                           # 95 bars seen: still waiting


def test_a_late_confirmation_is_rejected_as_stale():
    ch = _chart(4, {1: (4000, 4013, 3999, 4012.40)})                          # confirmed on bar 1, the run sees bars 2-3 too
    lines, s, _ = _run(ch)
    assert s["status"] == "REJECTED" and "stale" in s["why"]
    assert lines[0].startswith("XAUUSD 15m BUY confirmed +$12.40 (MINIMUM) at 4012.40 but NOT ELIGIBLE: stale")
    _, s, _ = _run(_chart(2, {1: (4000, 4013, 3999, 4012.40)}), t_now=T0 + 2 * 900 + 1201)
    assert s["status"] == "REJECTED" and "stale" in s["why"]                  # the last bar, but 20 min 1 s old


def test_a_level_inside_tp1_leaves_too_little_room():
    ch = _chart(2, {1: (4000, 4013, 3999, 4012.40)})
    ch["pdh"][1] = 4020.0                                                     # between 4012.40 and TP1 4025.40
    _, s, _ = _run(ch)
    assert s["status"] == "REJECTED" and "PDH 4020.00 lies between the entry and TP1, $7.60 away" in s["why"]
    ch["pdh"][1] = 4030.0                                                     # beyond TP1: fine
    _, s, _ = _run(ch)
    assert s["status"] == "ACTIVE"


def test_a_budget_the_minimum_lot_exceeds_is_no_trade(monkeypatch):
    monkeypatch.setenv("ACCOUNT_USD", "500")
    _, s, _ = _run(_chart(2, {1: (4000, 4013, 3999, 4012.40)}))
    assert s["status"] == "REJECTED" and "minimum lot loses more than the $13 budget" in s["why"]


def test_a_single_symmetric_target_cannot_pass_the_net_reward_check(monkeypatch):
    monkeypatch.setenv("PLAN_TP2_USD", "0")                                   # 46 x 13 - 44.62 = 553.38 / 642.62 = 0.86
    _, s, _ = _run(_chart(2, {1: (4000, 4013, 3999, 4012.40)}))
    assert s["status"] == "REJECTED" and "net reward / risk 0.86 after costs is below 1" in s["why"]


@pytest.mark.parametrize("bars, status, last", [
    ({2: (4012.4, 4025.5, 4013, 4025), 3: (4025, 4032.5, 4026, 4032)}, "TP2", "TP2 4032.40 reached"),
    ({2: (4012.4, 4025.5, 4013, 4025), 3: (4025, 4026, 4012.0, 4013)}, "BE", "back to the entry 4012.40 after TP1"),
    ({2: (4012.4, 4013, 3999.0, 4000)}, "SL", "stopped at 3999.40"),
    ({2: (4012.4, 4025.5, 3999.0, 4010)}, "AMBIGUOUS", "counted as the stop"),
    ({2: (4012.4, 4025.5, 4012.0, 4020)}, "BE", "TP1 bar also traded back to the entry"),
])
def test_the_plan_is_followed_after_the_entry(bars, status, last):
    st = {}
    ch = _chart(2, {1: (4000, 4013, 3999, 4012.40)})
    _run(ch, state=st)
    full = _chart(2 + len(bars), {1: (4000, 4013, 3999, 4012.40), **bars})
    lines = C1.advance_all(st, {"meta": {"tf": "15m"}, "chart": full, "markers": [SIG]}, full["t"][-1] + 960, N.plan_cfg())
    s = C1.book(st)["log"][0]
    assert s["status"] == status and last in lines[-1]
    if status in ("TP2", "BE") and len(bars) == 2:
        assert "TP1 4025.40 reached: close half, move the stop to the entry 4012.40" in lines[0]


def test_one_idea_one_setup_and_the_switch_restores_the_old_alerts(monkeypatch):
    st = {}
    C1.open_from(st, {"meta": {"tf": "15m"}, "markers": [SIG, dict(SIG, t=T0 + 1800, px=4008.0)]}, None)
    assert len(C1.book(st)["open"]) == 1                                      # same side, 30 min and $8 later: a repeat
    monkeypatch.setenv("CONFIRM_MIN_USD", "0")
    assert not C1.on()


def _payload(n, edits, markers):
    ch = _chart(n, edits)
    return {"meta": {"tf": "15m", "synthetic": False, "generated_utc": "2026-11-10T14:00:00+00:00", "price_source": "td"},
            "markers": markers, "decisions": [], "dashboard": {}, "chart": ch}


def _scenario(tmp_path, monkeypatch, c1_on):
    if not c1_on:
        monkeypatch.setenv("CONFIRM_MIN_USD", "0")
    monkeypatch.setenv("ALERT_STRUCTURE", "0")
    monkeypatch.delenv("ALERT_MODE", raising=False)                           # sixty, as in production
    sent = []
    monkeypatch.setattr(N, "send", lambda lines: sent.append(N.without_disclaimer(lines)) or ["test"] if lines else [])
    store = str(tmp_path)
    sig = dict(SIG, t=T0 + 900, px=4000.0)                                    # the signal bar is bar 1
    edits = {2: (4000, 4013, 3999, 4012.40)}                                  # bar 2 closes +$12.40
    N.run(store, {"15m": _payload(1, {}, [])}, ["15m"], sent_t=T0 + 900)
    N.run(store, {"15m": _payload(2, {}, [sig])}, ["15m"], sent_t=T0 + 1800 + 300)
    rep = N.run(store, {"15m": _payload(3, edits, [sig])}, ["15m"], sent_t=T0 + 2700 + 300)
    state = json.load(open(os.path.join(store, N.STATE)))
    return sent, rep, state


def test_on_the_phone_the_signal_is_a_setup_and_b15_records_the_same_plan(tmp_path, monkeypatch):
    sent, rep, state = _scenario(tmp_path / "on", monkeypatch, True)
    flat = [x for b in sent for x in b]
    head = next(x for x in flat if "SETUP DETECTED" in x)
    assert head.startswith("XAUUSD 15m BUY SETUP DETECTED") and "NOT AN ENTRY" in head
    assert not any(x.startswith(("YOUR PLAN", "ON MT5", "SIZE:", "LADDER")) for x in flat)   # no entry before confirmation
    assert any(x.startswith("XAUUSD 15m BUY ENTRY ELIGIBLE: confirmed +$12.40") for x in rep["confirm_entry"]["lines"])
    b15 = [x for x in flat if "TP1 4013.00 HIT" in x]                      # B15's own follow-up (its plan from 4000.00)
    assert len(b15) == 1 and b15[0].startswith(C1.B15_PREFIX) and "ENGINE PLAN BUY from 4000.00" in b15[0]
    assert not any("YOUR PLAN" in x for x in flat)                           # no line names a trade that was not taken
    monkeypatch.undo()
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    sent0, rep0, state0 = _scenario(tmp_path / "off", monkeypatch, False)
    assert state["plans"] == state0["plans"]                                  # B15's plan record: identical
    assert state.get("plan_log") == state0.get("plan_log") and "c1" not in state0
    assert any(x.startswith("YOUR PLAN") for b in sent0 for x in b)           # C1 off: the previous alert


def test_a_repeat_is_not_an_entry_either():
    h = C1.repeat_head(dict(SIG, px=3857.16, dir=-1), "15m")
    assert h == "XAUUSD 15m SELL signal again (signal bar closed) at 3857.16 | NOT AN ENTRY" and "entry 3857" not in h


def test_only_signals_the_phone_announced_open_a_setup(tmp_path, monkeypatch):
    """In sixty mode the phone gets 15m signals only: a 4h signal opens no setup, so no CANCELLED / ELIGIBLE alert can
    arrive for a setup the operator never saw. A skipped bar time (a REPEAT or a NOT ACTIONABLE signal) opens none."""
    monkeypatch.setenv("ALERT_STRUCTURE", "0")
    monkeypatch.delenv("ALERT_MODE", raising=False)
    monkeypatch.setattr(N, "send", lambda lines: ["test"] if lines else [])
    store = str(tmp_path)
    p4 = lambda n, mk: dict(_payload(n, {}, mk), meta={"tf": "4h", "synthetic": False, "price_source": "td",
                                                         "generated_utc": "2026-11-10T14:00:00+00:00"})
    sig4 = dict(SIG, t=T0 + 900)
    N.run(store, {"15m": _payload(1, {}, []), "4h": p4(1, [])}, ["15m", "4h"], sent_t=T0 + 900)
    N.run(store, {"15m": _payload(2, {}, []), "4h": p4(2, [sig4])}, ["15m", "4h"], sent_t=T0 + 1800 + 300)
    state = json.load(open(os.path.join(store, N.STATE)))
    assert not (state.get("c1") or {}).get("open")
    st = {}
    assert C1.open_from(st, {"meta": {"tf": "15m"}, "markers": [SIG]}, None, skip={SIG["t"]}) == []


def test_a_repeat_on_the_phone_never_says_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("ALERT_STRUCTURE", "0")
    monkeypatch.delenv("ALERT_MODE", raising=False)
    sent = []
    monkeypatch.setattr(N, "send", lambda lines: sent.append(N.without_disclaimer(lines)) or ["test"] if lines else [])
    store = str(tmp_path)
    s1, s2 = dict(SIG, t=T0 + 900, px=4000.0), dict(SIG, t=T0 + 1800, px=4005.0)     # same side, $5 and 15 min later
    N.run(store, {"15m": _payload(1, {}, [])}, ["15m"], sent_t=T0 + 900)
    N.run(store, {"15m": _payload(2, {}, [s1])}, ["15m"], sent_t=T0 + 1800 + 300)
    N.run(store, {"15m": _payload(3, {2: (4000, 4006, 3999, 4005)}, [s1, s2])}, ["15m"], sent_t=T0 + 2700 + 300)
    flat = [x for b in sent for x in b]
    assert any(x.startswith("XAUUSD 15m BUY signal again (signal bar closed) at 4005.00 | NOT AN ENTRY") for x in flat)
    assert not any("| entry " in x for x in flat)                                     # no headline offers an entry
    state = json.load(open(os.path.join(store, N.STATE)))
    assert len(state["c1"]["open"]) == 1                                               # the repeat opened no second setup
