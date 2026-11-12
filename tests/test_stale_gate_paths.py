"""Stale-signal gate, end to end on every alert path (audit of 2026-11-12; operator: "Verify that no alert can bypass
the 15-minute, 15-60-minute and over-60-minute rules ... ensure that repeated NOT ACTIONABLE signals cannot become
actionable").

The rules (quantum/notify.py, unchanged by the audit): at most 15 minutes after the bar close FRESH; 15-60 minutes
DELAYED only after a live price check; over 60 minutes, or a failed check, NOT ACTIONABLE (no plan, no MT5 line, one
summary line; later results website-only). Each rule is exercised at its boundary on the engine plan path (the one the
phone gets in production), the 4h breakout path, and the setup / grab paths, plus repeats and the three edge cases
the audit found (an unpriced signal, pruning of the decision log, the wording of a FRESH repeat of a quiet plan)."""
import json

import pytest

from test_stale_signals import C, ENTRY, _flat, _now, _pay, _sig

from quantum import notify as N


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("PLAN", "PLAN_LOT", "PLAN_SL_USD", "PLAN_TP_USD", "PLAN_TP2_USD", "MT5_PRICE_OFFSET", "PLAN_LATE_FRAC",
              "ALERT_MODE"):
        monkeypatch.delenv(k, raising=False)                       # ALERT_MODE unset = sixty, as in production
    monkeypatch.setenv("ALERT_STRUCTURE", "0")
    monkeypatch.setenv("ALERT_LIQUIDITY", "0")
    monkeypatch.setenv("ALERT_SETUPS", "0")
    monkeypatch.setenv("CONFIRM_PANEL", "0")


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(N, "send", lambda lines: out.append(list(lines)) or (["test"] if lines else []))
    return out


def _start(store):
    N.run(store, {"15m": _pay(C - 1800)}, ["15m"], sent_t=C - 1500)


TRADE = ("XAUUSD 15m SELL (confirmed close)", "YOUR PLAN", "ON MT5", "LADDER")


def _trade_lines(lines):
    return [x for x in lines if x.startswith(TRADE)]


# ---- the rule boundaries on the phone, engine plan path (production default mode) --------------------------------

@pytest.mark.parametrize(("age_min", "live_ok", "want"), [
    (14, True, "FRESH"), (15, True, "FRESH"), (16, True, "DELAYED"), (16, False, "NOT ACTIONABLE"),
    (59, True, "DELAYED"), (60, True, "DELAYED"), (61, True, "NOT ACTIONABLE"), (306, True, "NOT ACTIONABLE")])
def test_rule_boundaries_on_the_phone(tmp_path, sent, age_min, live_ok, want):
    store = str(tmp_path)
    _start(store)
    t_send = C + age_min * 60
    gen = t_send - 60 if live_ok else t_send - 400                 # 400 s old = not a fresh price
    N.run(store, {"15m": _pay(C, [_sig()], forming=4025.5, gen=gen)}, ["15m"], sent_t=t_send)
    flat = _flat(sent)
    if want == "NOT ACTIONABLE":
        assert not _trade_lines(flat)
        assert sum(x.startswith("XAUUSD NOT ACTIONABLE") for x in flat) == 1
    else:
        assert any(x.startswith("YOUR PLAN") for x in flat) and any(x.startswith("ON MT5") for x in flat)
        assert any(x.startswith("DELAYED ALERT") for x in flat) == (want == "DELAYED")


# ---- the decision's own boundaries (price age, LATE limit, levels already traded) --------------------------------

@pytest.mark.parametrize(("px_age", "state"), [(0, "DELAYED"), (300, "DELAYED"), (301, "NOT ACTIONABLE")])
def test_the_re_check_price_must_be_at_most_five_minutes_old(px_age, state):
    t = C + 1200
    assert N.freshness(C, -1, ENTRY, 13.0, 13.0, _now(t, ENTRY - 1.0, t - px_age), []).get("state") == state


def test_a_quote_not_marked_live_never_validates():
    t = C + 1200
    assert N.freshness(C, -1, ENTRY, 13.0, 13.0, _now(t, ENTRY - 1.0, t - 10, live=False), [])["state"] == "NOT ACTIONABLE"


@pytest.mark.parametrize(("move", "state"), [(2.75, "DELAYED"), (-2.75, "DELAYED"), (3.0, "NOT ACTIONABLE"),
                                             (-3.0, "NOT ACTIONABLE")])
def test_a_move_of_exactly_the_late_limit_is_too_late_in_both_directions(move, state):
    t = C + 1200                                                   # exact binary values: limit = 0.30 x $10 = $3.00
    fz = N.freshness(C, -1, 4000.0, 10.0, 10.0, _now(t, 4000.0 - move, t - 10), [])
    assert fz["state"] == state and fz["limit"] == 3.0 and abs(fz["move"]) == abs(move)


@pytest.mark.parametrize(("hi", "lo", "why"), [(ENTRY + 13.0, None, "stop"), (None, ENTRY - 13.0, "first target")])
def test_a_level_traded_since_the_close_blocks_a_delayed_plan(hi, lo, why):
    t = C + 1200
    bars = [_pay(C + 900, hi={C: hi} if hi else None, lo={C: lo} if lo else None)]
    fz = N.freshness(C, -1, ENTRY, 13.0, 13.0, _now(t, ENTRY - 1.0, t - 10), bars)
    assert fz["state"] == "NOT ACTIONABLE" and why in fz["why"]


def test_a_level_traded_before_the_close_does_not_count():
    t = C + 1200
    bars = [_pay(C + 900, hi={C - 900: ENTRY + 20.0})]             # the signal bar itself, before the close
    assert N.freshness(C, -1, ENTRY, 13.0, 13.0, _now(t, ENTRY - 1.0, t - 10), bars)["state"] == "DELAYED"


# ---- repeated NOT ACTIONABLE signals ------------------------------------------------------------------------------

def test_repeats_of_a_not_actionable_plan_never_get_a_plan_or_mt5_line(tmp_path, sent):
    store = str(tmp_path)
    _start(store)
    t1 = C + 20 * 60                                               # plan #1: 20 min late, price 400 s old -> NOT ACTIONABLE
    N.run(store, {"15m": _pay(C, [_sig()], forming=4025.5, gen=t1 - 400)}, ["15m"], sent_t=t1)
    assert any(x.startswith("XAUUSD NOT ACTIONABLE") and "no live price" in x for x in _flat(sent))
    n1 = len(sent)
    t2 = C + 1800 + 1800                                           # a repeat that would be DELAYED on its own
    N.run(store, {"15m": _pay(C + 900, [_sig(), _sig(t=C + 900, px=ENTRY - 2)], forming=ENTRY - 2.5, gen=t2 - 60)},
          ["15m"], sent_t=t2)
    flat2 = _flat(sent[n1:])
    assert not _trade_lines(flat2)
    assert any("repeat of plan #1, which was not actionable" in x for x in flat2)
    n2 = len(sent)
    t3 = C + 4500 + 300                                            # a FRESH repeat (5 min after its close)
    rep = N.run(store, {"15m": _pay(C + 3600, [_sig(), _sig(t=C + 900, px=ENTRY - 2), _sig(t=C + 3600, px=ENTRY - 3)],
                                    forming=ENTRY - 3, gen=t3 - 60)}, ["15m"], sent_t=t3)
    flat3 = _flat(sent[n2:])
    assert not any(x.startswith(("YOUR PLAN", "ON MT5", "LADDER")) for x in flat3)
    rp = [x for x in flat3 if x.startswith("REPEAT of #1")]
    assert rp and "which was NOT ACTIONABLE" in rp[0] and "still open" not in rp[0]
    st = json.loads((tmp_path / N.STATE).read_text())
    assert [p["id"] for p in st["plans"]] == [1] and st["fresh_gate"]["plan:1"]["state"] == "NOT ACTIONABLE"
    assert rep["plans"]["open"][0]["id"] == 1                      # the record still tracks it (website)


def test_follow_ups_of_a_quiet_plan_stay_off_the_phone_every_time(tmp_path, sent):
    store = str(tmp_path)
    _start(store)
    t1 = C + 306 * 60
    N.run(store, {"15m": _pay(C + 17100, [_sig()], forming=4025.5, gen=t1 - 60)}, ["15m"], sent_t=t1)
    n = len(sent)
    N.run(store, {"15m": _pay(C + 18000, [_sig()], lo={C + 18000: ENTRY - 13.5})}, ["15m"], sent_t=C + 18300)
    assert not any("TP1" in x and "HIT" in x for x in _flat(sent[n:]))


# ---- the three edge cases, now closed ------------------------------------------------------------------------------

def test_an_unpriced_signal_306_min_late_is_not_shown_as_a_signal(tmp_path, sent):
    store = str(tmp_path)
    _start(store)
    t1 = C + 306 * 60
    N.run(store, {"15m": _pay(C + 17100, [{**_sig(), "px": None}], forming=4025.5, gen=t1 - 60)}, ["15m"], sent_t=t1)
    flat = _flat(sent)
    assert not any(x.startswith("XAUUSD 15m SELL (confirmed close)") for x in flat)
    assert sum(x.startswith("XAUUSD NOT ACTIONABLE") for x in flat) == 1


def test_an_unpriced_signal_inside_the_hour_is_never_delayed():
    fz = N.freshness(C, -1, None, 13.0, 13.0, _now(C + 1200, ENTRY, C + 1190), [])
    assert fz["state"] == "NOT ACTIONABLE" and fz["why"] == "no signal price to re-check it"
    assert N.freshness(C, -1, None, 13.0, 13.0, _now(C + 600), [])["state"] == "FRESH"     # on time: unchanged


def test_three_hundred_later_decisions_do_not_release_a_quiet_open_plan(tmp_path, sent):
    store = str(tmp_path)
    _start(store)
    t1 = C + 306 * 60
    N.run(store, {"15m": _pay(C + 17100, [_sig()], forming=4025.5, gen=t1 - 60)}, ["15m"], sent_t=t1)
    st = json.loads((tmp_path / N.STATE).read_text())
    for i in range(N.GATE_KEEP + 50):                              # a very long outage's worth of later decisions
        N.gate_note(st, f"setup:{1000 + i}", {"state": "NOT ACTIONABLE", "age_min": 99, "t_close": C, "t_alert": t1})
    (tmp_path / N.STATE).write_text(json.dumps(st))
    assert st["fresh_gate"]["plan:1"]["state"] == "NOT ACTIONABLE"
    n = len(sent)
    N.run(store, {"15m": _pay(C + 18000, [_sig()], hi={C + 18000: 4040.0})}, ["15m"], sent_t=C + 18300)
    assert not any("SL 4037.98 HIT" in x for x in _flat(sent[n:]))


def test_pruning_drops_delayed_decisions_first_then_only_not_actionable_ones_past_the_hold():
    st = {}
    N.gate_note(st, "plan:1", {"state": "NOT ACTIONABLE", "t_alert": C})
    for i in range(N.GATE_KEEP):
        N.gate_note(st, f"plan:{100 + i}", {"state": "DELAYED", "t_alert": C + i})
    g = st["fresh_gate"]
    assert len(g) == N.GATE_KEEP and "plan:1" in g and "plan:100" not in g     # a DELAYED one went first
    late = C + N.GATE_HOLD_SEC + 1
    for i in range(N.GATE_KEEP):
        N.gate_note(st, f"setup:{i}", {"state": "NOT ACTIONABLE", "t_alert": late})
    assert "plan:1" not in st["fresh_gate"] and len(st["fresh_gate"]) == N.GATE_KEEP
    assert N.GATE_HOLD_SEC == 14 * 86400 and N.GATE_KEEP == 300


def test_the_newest_decision_is_never_the_one_pruned():
    st = {}
    for i in range(N.GATE_KEEP):
        N.gate_note(st, f"plan:{i}", {"state": "NOT ACTIONABLE", "t_alert": C})
    N.gate_note(st, "plan:new", {"state": "DELAYED", "t_alert": C})
    assert "plan:new" in st["fresh_gate"]


# ---- the other paths ------------------------------------------------------------------------------------------------

def _h4_event(t_close):
    return {"i": 5, "t": t_close - 14400, "t_close": t_close, "dir": -1, "close": ENTRY, "kind": "4H BREAKOUT",
            "prev_high": ENTRY + 20, "prev_low": ENTRY + 1, "beyond": [("PDL", 4030.0)],
            "checks": {"major": True, "trend": True, "bias": True, "session": True}, "confirmed": True}


@pytest.mark.parametrize(("age_min", "gen_age", "want"), [(5, 60, "FRESH"), (15, 60, "FRESH"), (16, 60, "DELAYED"),
                                                          (20, 400, "NOT ACTIONABLE"), (60, 60, "DELAYED"),
                                                          (61, 60, "NOT ACTIONABLE"), (306, 60, "NOT ACTIONABLE")])
def test_4h_breakout_path_obeys_the_three_rules(tmp_path, sent, monkeypatch, age_min, gen_age, want):
    monkeypatch.setenv("ALERT_SETUPS", "1")
    monkeypatch.setenv("ALERT_MODE", "all")                       # the only mode in which these reach the phone
    monkeypatch.setattr(N, "setup_scan", lambda payloads, since, seen: [])
    store = str(tmp_path)
    N.run(store, {"15m": _pay(C - 1800), "4h": _pay(C - 1800)}, ["15m", "4h"], sent_t=C - 1500)
    monkeypatch.setattr(N, "h4_scan", lambda payloads, since: [_h4_event(C)])
    t_send = C + age_min * 60
    p = _pay(C, forming=4025.5, gen=t_send - gen_age)
    rep = N.run(store, {"15m": p, "4h": p}, ["15m", "4h"], sent_t=t_send)
    flat = _flat(sent)
    shown = [x for x in flat if x.startswith("XAUUSD 4h CANDLE BREAKOUT")]
    if want == "NOT ACTIONABLE":
        assert not shown and not any(x.startswith(("ENTRY ", "ON MT5")) for x in flat)
        assert any(x.startswith("XAUUSD NOT ACTIONABLE: 1 4h breakout alert recovered late") for x in flat)
        assert all(x.startswith(N.RECORD_ONLY) for x in rep["h4_alerts"][-1]["lines"])
    else:
        assert shown
        assert any(x.startswith("DELAYED ALERT") for x in flat) == (want == "DELAYED")


def test_sixty_mode_sends_no_setup_or_4h_or_grab_line_at_all(tmp_path, sent, monkeypatch):
    monkeypatch.setenv("ALERT_SETUPS", "1")                       # production: ALERT_MODE unset = sixty
    ev = {"t": C - 900, "dir": -1, "close": ENTRY, "kind": "BREAKOUT", "levels": [("PDL", 4030.0)], "zones": ["PDL"],
          "checks": {"major": True, "trend": True, "bias": True, "session": True}, "confirmed": True}
    store = str(tmp_path)
    N.run(store, {"15m": _pay(C - 1800), "4h": _pay(C - 1800)}, ["15m", "4h"], sent_t=C - 1500)
    monkeypatch.setattr(N, "setup_scan", lambda payloads, since, seen: [ev])
    monkeypatch.setattr(N, "h4_scan", lambda payloads, since: [_h4_event(C)])
    t_send = C + 5 * 60
    p = _pay(C, forming=4025.5, gen=t_send - 60)
    N.run(store, {"15m": p, "4h": p}, ["15m", "4h"], sent_t=t_send)
    flat = _flat(sent)
    assert not any("SETUP" in x or "CANDLE BREAKOUT" in x or "GRAB TEST" in x for x in flat)


def test_sixty_mode_keeps_h_setup_lines_off_the_phone(tmp_path, sent, monkeypatch):
    monkeypatch.setenv("ALERT_STRUCTURE", "1")
    store = str(tmp_path)
    _start(store)
    t1 = C + 306 * 60
    pay = _pay(C + 17100, [], forming=4025.5, gen=t1 - 60)
    pay["h2"] = {"signals": [{"t": C - 900, "dir": "SHORT", "entry": ENTRY, "sl": ENTRY + 10, "tp1": ENTRY - 10, "tp2": ENTRY - 20}]}
    N.run(store, {"15m": pay}, ["15m"], sent_t=t1)
    assert not any("H2 SELL" in x for x in _flat(sent))
