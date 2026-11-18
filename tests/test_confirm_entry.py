"""C1 (operator directive 2026-11-15): a SETUP is not an entry; a $10 confirming 15m close, fresh data, the plan recalculated
from the entry, room to TP1 and a size within the $650 budget make it ENTRY ELIGIBLE. Values are worked by hand at the N1
defaults: lot 0.46 (46 oz), sizing cost $0.97/oz -> cost $44.62, loss at the stop 46 x 13.97 = $642.62, reward with both
targets 46 x 16.50 - 44.62 = $714.38, with TP1 then the entry 46 x 6.50 - 44.62 = $254.38, net R:R 714.38 / 642.62 = 1.11."""
import json
import os

import pytest

from quantum import confirm_entry as C1
from quantum import notify as N

T0 = 1794405600                         # 2026-11-11 14:00 UTC (Wed), the signal bar's open
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


SRC = "twelvedata:XAU/USD"


def _run(ch, markers=(), t_now=None, state=None, now=None):
    st = state if state is not None else {}
    C1.open_from(st, {"meta": {"tf": "15m", "price_source": SRC}, "markers": [SIG]}, None)
    p15 = {"meta": {"tf": "15m"}, "chart": ch, "markers": [SIG, *markers]}
    t_now = t_now if t_now is not None else ch["t"][-1] + 900 + 60
    lines = C1.advance_all(st, p15, t_now, N.plan_cfg(), 0.0, now)
    s = (C1.book(st)["open"] + C1.book(st)["log"])[0]
    return lines, s, st


def test_the_setup_alert_says_it_is_not_an_entry():
    assert C1.on() and C1.min_usd() == 10.0
    assert C1.setup_head(SIG, "15m") == ("XAUUSD 15m BUY SETUP DETECTED (signal bar closed 11 Nov 14:15 UTC) | WAIT, NOT AN ENTRY | "
                                         "trigger 4000.00")
    L = C1.setup_lines(SIG)
    assert L[0].startswith("WAIT FOR CONFIRMATION: a 15m close at or above 4010.00 (+$10 minimum) | +$15 4015.00 preferred | "
                           "+$20 4020.00 ideal")
    assert "CANCELLED if price trades 3987.00 (-$13)" in L[1] and L[1].endswith("first; expires after 24 h")
    assert L[2].startswith("NO TRADE until an ENTRY ELIGIBLE alert arrives") and "not a proven edge" in L[2] and len(L) == 3


def test_the_setup_alert_names_its_id_its_time_its_expiry_and_its_data_source():
    st = {}
    (s,) = C1.open_from(st, {"meta": {"tf": "15m", "price_source": SRC}, "markers": [SIG]}, None)
    assert (s["id"], s["src"], s["t_close"]) == (1, SRC, T0 + 900)
    assert C1.setup_head(SIG, "15m", 0.0, s["id"]) == ("XAUUSD 15m BUY SETUP DETECTED #1 (signal bar closed 11 Nov 14:15 UTC) | "
                                                       "WAIT, NOT AN ENTRY | trigger 4000.00")
    L = C1.setup_lines(SIG, 0.0, s)
    assert L[1] == ("CANCELLED if price trades 3987.00 (-$13) or the 15m structure breaks the other way first; expires after "
                    "96 15m bars without a confirming close (24 market hours: not before 12 Nov 14:15 UTC)")
    assert L[2] == "DATA: twelvedata:XAU/USD, 15m bars; the trigger is the signal bar's close"
    assert L[3].startswith("NO TRADE until an ENTRY ELIGIBLE alert arrives") and len(L) == 4
    assert T0 + 900 + C1.WIN * 900 == T0 + 900 + 86400                        # the printed expiry is the rule's 96 bars
    assert C1.setup_head(dict(SIG, t=T0), "1h", 0.0, 7).startswith("XAUUSD 1h BUY SETUP DETECTED #7 (signal bar closed 11 Nov 15:00 UTC)")
    st2 = {}
    (s2,) = C1.open_from(st2, {"meta": {"tf": "15m"}, "markers": [SIG]}, None)   # a payload without a source: no DATA line
    assert "src" not in s2 and len(C1.setup_lines(SIG, 0.0, s2)) == 3


def test_a_touch_is_not_a_confirmation_and_the_close_recalculates_the_plan_and_risk():
    ch = _chart(3, {1: (4000, 4012, 4001, 4008), 2: (4008, 4013, 4007, 4012.40)})
    t_now = ch["t"][-1] + 960                                                  # 16 min after the confirming bar's open
    lines, s, _ = _run(ch, t_now=t_now, now={"t": t_now, "px": 4013.10, "t_px": ch["t"][-1] + 900 + 240, "live": True})
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
    assert lines[0] == ("XAUUSD 15m BUY ENTRY ELIGIBLE, SETUP #1: entry 4012.40 = the 15m close at 11 Nov 14:45 UTC, +$12.40 "
                        "(MINIMUM) beyond the trigger 4000.00 (11 Nov 14:15 UTC)")
    assert lines[1] == ("PLAN (recalculated from this entry): entry 4012.40 | SL 3999.40 | TP1 4025.40 (close half) | "
                        "TP2 4032.40 (the rest; stop to the entry after TP1)")
    assert lines[2] == ("RISK: account $25,000 | 2.6% = max $650 | lot 0.46 | est. cost $45 ($0.97/oz) | "
                        "loss at the stop incl. cost $643")
    assert lines[3] == ("NET: reward $714 if every target is reached, $254 if TP1 then back to the entry | net R:R 1.11 | "
                        "a $643 loss is possible on this trade")
    # touched +$10 on bar 1 (high 4012), closed beyond it on bar 2; +$15 (4015) was never touched (high 4013)
    assert lines[4] == "CONFIRMATION STATUS: +$10 4010.00 CLOSED BEYOND | +$15 4015.00 not reached | +$20 4020.00 not reached"
    # latest 4013.10: 0.70 above the entry; TP1 4025.40 - 4013.10 = 12.30; TP2 4032.40 - 4013.10 = 19.30; stop 4013.10 - 3999.40 = 13.70
    assert lines[5] == ("DATA: twelvedata:XAU/USD, 15m bars | confirming close 4012.40 at 11 Nov 14:45 UTC | latest price 4013.10 "
                        "(live quote read 14:49 UTC): $0.70 toward TP from the entry | left from it: TP1 $12.30, TP2 $19.30, "
                        "the stop $13.70")
    # 46 oz x 0.97 = 44.62; at the stated $0.26/oz: 46 x 0.26 = 11.96
    assert lines[6] == ("COSTS per oz, round trip (research model; not broker-verified; the feed has no bid / ask): spread $0.50 + "
                        "slippage $0.40 + commission $0.07 = $0.97 = $45 at 0.46 lot | at your stated $0.26/oz: $12")
    assert lines[7] == ("VALID until 11 Nov 15:05 UTC (20 min after the confirming close; later the price has moved on: NO TRADE on "
                        "this alert) | the record follows the plan for 192 15m bars (48 market hours), then closes it")
    assert lines[8] == ("PROBABILITY: none shown, NOT CALIBRATED | validation B30, engine signals out of sample 2023-25, the engine "
                        "before Amendment F: a $10 confirming close reached TP1 first in 27 of 48 = 56% (95% 42%-69%; break-even "
                        "about 53%), net +0.00 R (-0.28 to +0.27), p 0.81: NOT SUPPORTED | live record of these entries: none "
                        "decided yet")
    assert lines[9].startswith("CHECKS passed: fresh close") and "not a proven edge" in lines[9] and len(lines) == 10
    assert s["conf"]["t"] + C1.FRESH_SEC == T0 + 2700 + 1200 and s["conf"]["t_alert"] == t_now   # 14:45 + 20 min = 15:05
    assert s["conf"]["now"] == {"px": 4013.10, "t_px": T0 + 2700 + 240, "live": True} and s["conf"]["rec"] == [0, 0]


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
    assert lines == [f"XAUUSD 15m BUY SETUP #1 CANCELLED (trigger 4000.00, 11 Nov 14:15 UTC): {s['why']} | NO TRADE"]
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
    assert lines[0].startswith("XAUUSD 15m BUY SETUP #1 confirmed +$12.40 (MINIMUM) at 4012.40 but NOT ELIGIBLE: stale")
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
    assert head.startswith("XAUUSD 15m BUY SETUP DETECTED #1 (signal bar closed 11 Nov 14:30 UTC)") and head.endswith("trigger 4000.00")
    assert "DATA: td, 15m bars; the trigger is the signal bar's close" in flat
    assert rep["confirm_entry"]["lines"][0].startswith("XAUUSD 15m BUY ENTRY ELIGIBLE, SETUP #1: entry 4012.40 = the 15m close")
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


# ---------------- priority 6 (operator directive 2026-11-15): every field on the alert, the same decision on the site ----------------
def test_the_validation_reference_is_the_b30_results_file():
    with open("research/results/b30_all_partitions_2026-11-15.json") as f:
        d = json.load(f)
    with open("research/registrations/B30.json") as f:
        reg = json.dumps(json.load(f))
    assert set(C1.VALIDATION) == {10.0, 15.0, 20.0} and d["decision"]["recommended"] is None
    for x, v in C1.VALIDATION.items():
        row = d["decision"]["rows"][v["model"]]
        oos = [d["parts"][p]["results"][f"ENG|G1|model|{v['model']}"] for p in ("validation", "holdout")]
        assert v["n"] == row["n_oos"] == sum(r["executed"] for r in oos)
        assert v["tp1"] == sum(r["tp1_first"]["k"] for r in oos)
        assert v["net_r"] == round(row["mean_r_oos"], 2) and v["boot95"] == tuple(round(b, 2) for b in row["boot95_oos"])
        assert v["holm_p"] == round(row["holm_p"], 2) and row["supported"] is False
        assert f"Model {v['model']}" in open("research/B30_RESULTS.md").read() and f"${x:g}" in reg
    md = open("research/B30_RESULTS.md").read()
    assert "| Model A | $10 | 48 |" in md and "| Model B | $15 | 42 |" in md and "| Model C | $20 | 34 |" in md   # threshold -> model
    assert "about 52.7%" in md and C1.VALIDATION_BE == 0.527
    lo, hi = C1.wilson(27, 48)
    assert (round(lo, 2), round(hi, 2)) == (0.42, 0.69) and C1.wilson(0, 0) is None      # the report's 42-69
    assert C1.probability_line(15.0).startswith("PROBABILITY: none shown, NOT CALIBRATED | validation B30")
    assert "a $15 confirming close reached TP1 first in 23 of 42 = 55%" in C1.probability_line(15.0)
    assert "net +0.17 R (-0.17 to +0.46), p 0.52: NOT SUPPORTED" in C1.probability_line(20.0)
    assert C1.probability_line(12.0) == ("PROBABILITY: none shown, NOT CALIBRATED | validation: none at a $12 confirming close (B30 "
                                         "tested $10 / $15 / $20; none was supported) | live record of these entries: none decided yet")


def test_the_cost_split_is_the_research_models_upper_bound(monkeypatch):
    import pandas as pd

    from quantum import config
    from quantum.research import harness as H
    P, cfg = N.COST_MODEL_PARTS, config.Config()
    assert sum(P.values()) == pytest.approx(N.COST_MODEL_OZ[1]) and set(P) == {"spread", "slippage", "commission"}
    assert P["slippage"] == pytest.approx(2 * cfg.slippage_pts) and P["commission"] == pytest.approx(cfg.commission_l / 100)
    day = H.cost_pts(pd.date_range("2026-11-11", periods=96, freq="15min", tz="UTC"))      # the frozen model over one day
    assert day.max() == pytest.approx(N.COST_MODEL_OZ[1]) and day.min() == pytest.approx(N.COST_MODEL_OZ[0])
    assert day.max() - P["slippage"] - P["commission"] == pytest.approx(P["spread"])       # the off-session spread
    assert N.cost_parts(0.97) == P and N.cost_parts(0.97) is not P and N.cost_parts(1.20) is None and N.cost_parts(0.77) is None
    assert N.plan_cfg()["cost_parts"] == P
    monkeypatch.setenv("PLAN_COST_PER_LOT", "120")                             # your cost $1.20/oz is the higher: one figure
    pl = N.plan_cfg()
    assert pl["size_cost_oz"] == pytest.approx(1.20) and pl["cost_parts"] is None and pl["lot"] == 0.44   # 650 / 1420 = 0.457 -> 0.44
    line = C1.cost_line(C1.plan_at(4012.40, 1, pl))
    assert line == ("COSTS per oz, round trip (the higher of your cost and the research model; not broker-verified; the feed has no "
                    "bid / ask): $1.20 = $53 at 0.44 lot")                      # 44 oz x 1.20 = 52.80


def _entry(i, status, tp1, entered=True):
    return {"id": i, "status": status, "events": [["TP1", 0, 0.0]] if tp1 else [], **({"entry_bar": 1} if entered else {})}


def test_the_live_record_counts_tp1_first_against_the_stop_and_the_next_alert_prints_it():
    log = [_entry(1, "TP2", True), _entry(2, "BE", True), _entry(3, "SL", False), _entry(4, "AMBIGUOUS", False),
           _entry(5, "TIMEOUT", False), _entry(6, "TIMEOUT", False), _entry(9, "REJECTED", False, False), _entry(10, "TIMEOUT", True),
           _entry(11, "EXPIRED", False, False)]
    st = {"c1": {"seq": 11, "open": [], "log": log}}
    # entered: 1 2 3 4 5 6 10 = 7; TP1 first: 1 2 10 = 3; the stop first: 3 4 = 2; a time stop before either: 5 6 (not 10)
    assert C1.record(st) == {"entries": 7, "tp1": 3, "sl": 2, "decided": 5, "timeout": 2, "open": 0, "wilson": C1.wilson(3, 5)}
    assert C1.record_text([3, 5]) == "live record of these entries: TP1 first 3 of 5 decided (95% 23%-88%); descriptive, no verdict"
    assert C1.record_text([0, 0]) == C1.record_text(None) == "live record of these entries: none decided yet"
    lines, s, _ = _run(_chart(2, {1: (4000, 4013, 3999, 4012.40)}), state=st)
    assert s["id"] == 12 and s["conf"]["rec"] == [3, 5]                        # the record before this entry, kept on it
    assert lines[8].endswith("| live record of these entries: TP1 first 3 of 5 decided (95% 23%-88%); descriptive, no verdict")
    r = C1.record(st)
    assert (r["entries"], r["open"], r["decided"]) == (8, 1, 5)                # the new entry is open, not decided
    st["c1"]["open"][0]["status"] = "TP1"
    st["c1"]["open"][0]["events"].append(["TP1", 0, 0.0])
    assert (C1.record(st)["tp1"], C1.record(st)["decided"], C1.record(st)["open"]) == (4, 6, 0)   # TP1 reached: decided at once


def test_a_touch_without_a_close_and_a_last_closed_bar_price_are_named():
    ch = _chart(3, {1: (4000, 4016, 4001, 4008), 2: (4008, 4013, 4007, 4012.40)})         # bar 1 touched +$15, closed +$8
    t_now = ch["t"][-1] + 960
    lines, s, _ = _run(ch, t_now=t_now, now={"t": t_now, "px": 4012.40, "t_px": ch["t"][-1] + 900, "live": False})
    assert lines[4] == ("CONFIRMATION STATUS: +$10 4010.00 CLOSED BEYOND | +$15 4015.00 touched 14:30 UTC, no close beyond | "
                        "+$20 4020.00 not reached")
    assert "latest price 4012.40 (last closed bar read 14:45 UTC): $0.00 unchanged from the entry" in lines[5]
    sell = {"id": 3, "tf": "15m", "dir": -1, "p0": 4000.0, "t_close": T0 + 900, "x": 10.0, "touch": {}, "src": SRC,
            "conf": {"t": T0 + 1800, "px": 3980.0, "move": 20.0, "tier": "IDEAL", "now": {"px": 3981.0, "t_px": T0 + 1900, "live": True}},
            "plan": C1.plan_at(3980.0, -1, N.plan_cfg())}
    assert C1.ladder_status(sell) == "CONFIRMATION STATUS: +$10 3990.00 CLOSED BEYOND | +$15 3985.00 CLOSED BEYOND | +$20 3980.00 CLOSED BEYOND"
    # a SELL from 3980.00: SL 3993.00, TP1 3967.00, TP2 3960.00; the latest 3981.00 is $1 toward the stop
    assert C1.data_line(sell).endswith("latest price 3981.00 (live quote read 14:31 UTC): $1.00 toward the stop from the entry | "
                                       "left from it: TP1 $14.00, TP2 $21.00, the stop $12.00")


def test_a_setup_recorded_before_this_build_still_prints():
    lines, s, st = _run(_chart(2, {1: (4000, 4013, 3999, 4012.40)}))
    for k in ("now", "rec", "t_alert"):
        s["conf"].pop(k, None)
    s.pop("src")
    s["plan"].pop("cost_parts")
    s["plan"].pop("own_cost_oz")
    L = C1.eligible_lines(s)
    assert L[5] == ("DATA: price source not recorded, 15m bars | confirming close 4012.40 at 11 Nov 14:30 UTC | latest price: not "
                    "available in this run, check your platform")
    assert L[6] == ("COSTS per oz, round trip (the higher of your cost and the research model; not broker-verified; the feed has no "
                    "bid / ask): $0.97 = $45 at 0.46 lot")
    assert L[8].endswith("live record of these entries: none decided yet") and len(L) == 10
    assert C1.snapshot(st, T0 + 1800 + 60)["open"][0]["phone"] == L


def test_the_website_copy_carries_the_same_decision_and_the_same_text_as_the_phone():
    st = {}
    assert C1.snapshot(st, T0)["decision"] == {"word": "NO TRADE", "id": None, "why": "no setup is open: no qualifying opportunity"}
    (s,) = C1.open_from(st, {"meta": {"tf": "15m", "price_source": SRC}, "markers": [SIG]}, None)
    snap = C1.snapshot(st, T0 + 960)
    assert snap["decision"] == {"word": "WAIT", "id": 1, "why": "waiting for a confirming 15m close: setup #1 BUY. Not an entry"}
    assert snap["open"][0]["phone"] == [C1.setup_head(SIG, "15m", 0.0, 1), *C1.setup_lines(SIG, 0.0, s)]
    assert snap["open"][0]["expires_not_before"] == T0 + 900 + 86400 and snap["open"][0]["status"] == "PENDING"
    assert (snap["on"], snap["min_usd"], snap["inv_usd"], snap["fresh_sec"], snap["t"]) == (True, 10.0, 13.0, 1200, T0 + 960)
    ch = _chart(3, {1: (4000, 4012, 4001, 4008), 2: (4008, 4013, 4007, 4012.40)})
    t_now = ch["t"][-1] + 960
    lines = C1.advance_all(st, {"meta": {"tf": "15m"}, "chart": ch, "markers": [SIG]}, t_now, N.plan_cfg(), 0.0,
                           {"t": t_now, "px": 4013.10, "t_px": t_now - 60, "live": True})
    snap = C1.snapshot(st, t_now)
    assert snap["decision"] == {"word": "BUY", "id": 1, "until": T0 + 2700 + 1200,
                                "why": "ENTRY ELIGIBLE, setup #1: every check passed at the confirming close"}
    assert snap["open"][0]["phone"] == lines and len(lines) == 10              # the alert the phone received, line for line
    assert snap["open"][0]["ladder"] == lines[4] and snap["record"]["open"] == 1
    assert C1.snapshot(st, T0 + 2700 + 1200)["decision"]["word"] == "BUY"      # valid up to 20 min after the close
    late = C1.snapshot(st, T0 + 2700 + 1201)["decision"]
    assert late == {"word": "NO TRADE", "id": None, "why": "no new entry: the entry window of setup #1 has passed"}
    full = _chart(4, {1: (4000, 4012, 4001, 4008), 2: (4008, 4013, 4007, 4012.40), 3: (4012.4, 4013, 3999.0, 4000)})
    res = C1.advance_all(st, {"meta": {"tf": "15m"}, "chart": full, "markers": [SIG]}, full["t"][-1] + 960, N.plan_cfg())
    assert res == ["XAUUSD 15m BUY confirmed setup #1 SL: stopped at 3999.40"]
    snap = C1.snapshot(st, full["t"][-1] + 960)
    assert snap["open"] == [] and snap["decision"]["word"] == "NO TRADE" and "no setup is open" in snap["decision"]["why"]
    assert (snap["recent"][0]["status"], snap["recent"][0]["phone"]) == ("SL", lines)
    assert (snap["record"]["decided"], snap["record"]["tp1"], snap["record"]["sl"]) == (1, 0, 1)
    assert snap["validation"]["rows"]["10"]["n"] == 48 and snap["validation"]["break_even"] == 0.527
    json.dumps(snap)                                                           # index.json carries it


def test_two_open_setups_the_newest_valid_entry_is_the_decision_and_wait_names_every_pending_one():
    st = {}
    C1.open_from(st, {"meta": {"tf": "15m"}, "markers": [SIG, dict(SIG, t=T0 + 900, dir=-1, px=4015.0)]}, None)
    d = C1.decision(st, T0 + 2000)
    assert d["word"] == "WAIT" and d["id"] == 2 and "#1 BUY, #2 SELL" in d["why"]
    ch = _chart(3, {2: (4000, 4013, 3999, 4012.40)})                           # +$12.40 for the BUY; the SELL from 4015 is +$2.60
    C1.advance_all(st, {"meta": {"tf": "15m"}, "chart": ch, "markers": []}, ch["t"][-1] + 960, N.plan_cfg())
    assert [x["status"] for x in C1.book(st)["open"]] == ["ACTIVE", "PENDING"]
    assert C1.decision(st, ch["t"][-1] + 960)["word"] == "BUY"                  # an entry in its window outranks a waiting setup
    assert C1.decision(st, ch["t"][-1] + 900 + 1201)["word"] == "WAIT"          # the window passed: the other setup still waits
    snap = C1.snapshot(st, ch["t"][-1] + 960)
    assert [x["id"] for x in snap["open"]] == [2, 1]                            # the newest setup first
    ch2 = _chart(4, {2: (4000, 4013, 3999, 4012.40), 3: (4012.4, 4013, 4004.0, 4004.5)})   # the next bar: the SELL from 4015 closes +$10.50
    C1.advance_all(st, {"meta": {"tf": "15m"}, "chart": ch2, "markers": []}, ch2["t"][-1] + 960, N.plan_cfg())
    assert [x["status"] for x in C1.book(st)["open"]] == ["ACTIVE", "ACTIVE"]
    d = C1.decision(st, ch2["t"][-1] + 960)                                     # both entries are in their windows (16 and 1 min old)
    assert (d["word"], d["id"], d["until"]) == ("SELL", 2, ch2["t"][-1] + 900 + 1200)   # the newest confirmation is the decision


def test_the_website_copy_lists_the_newest_finished_setups_first_and_at_most_twelve():
    log = [dict(_entry(i, "SL", False), tf="15m", dir=1, p0=4000.0 + i, t=T0, t_close=T0 + 900 * i, x=10.0, touch={},
                conf={"t": T0 + 900 * i + 900, "px": 4010.0 + i, "move": 10.0, "tier": "MINIMUM"},
                plan=C1.plan_at(4010.0 + i, 1, N.plan_cfg())) for i in range(1, 15)]
    snap = C1.snapshot({"c1": {"seq": 14, "open": [], "log": log}}, T0 + 86400)
    assert [x["id"] for x in snap["recent"]] == list(range(14, 2, -1)) and C1.SNAP_RECENT == 12
    assert snap["record"]["decided"] == 14 and snap["record"]["sl"] == 14       # the record still counts every entry


def test_a_signal_that_joins_a_waiting_setup_shows_that_setups_level():
    st = {}
    (s,) = C1.open_from(st, {"meta": {"tf": "15m"}, "markers": [SIG]}, None)
    m2 = dict(SIG, t=T0 + 1800, px=4003.0)
    assert C1.same_idea(st, m2, "15m") is s and C1.open_setup(st, m2, "15m") is None
    assert C1.same_idea(st, dict(m2, dir=-1), "15m") is None and C1.same_idea(st, dict(m2, px=4015.01), "15m") is None
    assert C1.same_idea(st, dict(m2, t=T0 + 4 * 3600 + 900), "15m") is None and C1.same_idea(st, dict(m2, t=T0 + 4 * 3600), "15m") is s
    assert C1.joined_lines(m2, "15m", s) == [
        "XAUUSD 15m BUY signal again (signal bar closed 11 Nov 14:45 UTC) at 4003.00 | SAME IDEA AS SETUP #1: no new setup | NOT AN ENTRY",
        "SETUP #1 is still waiting for a 15m close at or above 4010.00 (+$10 beyond its trigger 4000.00). NO TRADE on this signal."]


def test_on_the_phone_a_signal_joining_an_entered_setup_names_it_and_the_site_shows_the_phones_decision(tmp_path, monkeypatch):
    """B15's plan from 4000.00 ends at TP2 4020.00 on bar 3 while the confirmed setup #1 (entry 4012.40, TP1 4025.40) is
    still running. A new BUY signal on bar 3 at 4012.00 is a new B15 plan (no open plan to repeat) but the same idea as
    setup #1 (30 min and $12 from its trigger): the phone names setup #1 and shows no new confirmation levels."""
    monkeypatch.setenv("ALERT_STRUCTURE", "0")
    monkeypatch.delenv("ALERT_MODE", raising=False)
    sent = []
    monkeypatch.setattr(N, "send", lambda lines: sent.append(N.without_disclaimer(lines)) or ["test"] if lines else [])
    store = str(tmp_path)
    s1, s2 = dict(SIG, t=T0 + 900, px=4000.0), dict(SIG, t=T0 + 2700, px=4012.0)
    e = {2: (4000, 4013, 4000.5, 4012.40), 3: (4012.4, 4021, 4011, 4012.0)}
    N.run(store, {"15m": _payload(1, {}, [])}, ["15m"], sent_t=T0 + 900)
    r2 = N.run(store, {"15m": _payload(2, {}, [s1])}, ["15m"], sent_t=T0 + 1800 + 300)
    assert r2["c1"]["decision"]["word"] == "WAIT" and r2["c1"]["open"][0]["id"] == 1
    assert r2["c1"]["open"][0]["phone"][0] in sent[-1] and r2["c1"]["open"][0]["phone"][-1] in sent[-1]   # the same text
    r3 = N.run(store, {"15m": _payload(3, {2: e[2]}, [s1])}, ["15m"], sent_t=T0 + 2700 + 300)
    assert r3["c1"]["decision"]["word"] == "BUY" and r3["c1"]["open"][0]["phone"] == r3["confirm_entry"]["lines"]
    assert r3["confirm_entry"]["lines"] == sent[-1]
    # the run's own price reaches the alert: no forming bar in this payload, so the last closed bar (14:45, 4012.40)
    assert "DATA: td, 15m bars | confirming close 4012.40 at 11 Nov 14:45 UTC | latest price 4012.40 (last closed bar read 14:45 UTC)" in sent[-1][5]
    n0 = len(sent)
    r4 = N.run(store, {"15m": _payload(4, e, [s1, s2])}, ["15m"], sent_t=T0 + 3600 + 301)   # 20 min 1 s after the 14:45 close
    flat = [x for b in sent[n0:] for x in b]
    assert ("XAUUSD 15m BUY signal again (signal bar closed 11 Nov 15:00 UTC) at 4012.00 | SAME IDEA AS SETUP #1: no new setup | "
            "NOT AN ENTRY") in flat
    assert "SETUP #1 is already confirmed at 4012.40, 11 Nov 14:45 UTC: its entry alert was sent then. NO TRADE on this signal." in flat
    assert not any("4022.00" in x or "WAIT FOR CONFIRMATION" in x or "SETUP DETECTED" in x for x in flat)   # no levels from 4012.00
    state = json.load(open(os.path.join(store, N.STATE)))
    assert len(state["c1"]["open"]) == 1 and state["c1"]["seq"] == 1           # no second setup
    assert [p["entry"] for p in state["plans"]] == [4012.0]                    # B15 opened its own plan, as before
    assert r4["c1"]["decision"] == {"word": "NO TRADE", "id": None, "why": "no new entry: the entry window of setup #1 has passed"}
    monkeypatch.setenv("CONFIRM_MIN_USD", "0")                                 # C1 off: no website copy
    r5 = N.run(store, {"15m": _payload(4, e, [s1, s2])}, ["15m"], sent_t=T0 + 3600 + 400)
    assert "c1" not in r5


# The operator's list (directive 2026-11-15, section "final alert must provide"): the field, the text that carries it on
# the phone, and the label that carries it on the website card (site/app.js c1Card).
OPERATOR_FIELDS = [
    ("BUY / SELL / WAIT / NO TRADE", "BUY ENTRY ELIGIBLE", "<div>Decision</div>"),
    ("WAIT", "WAIT, NOT AN ENTRY", "WAIT, not an entry"),
    ("NO TRADE", "NO TRADE until an ENTRY ELIGIBLE alert arrives", "No setup is open: no qualifying opportunity"),
    ("signal ID", "SETUP #1", "<div>Setup</div>"),
    ("timestamp", "the 15m close at 11 Nov 14:45 UTC", "signal bar closed ${tfmt(x.t_close)}"),
    ("actual data source", "DATA: twelvedata:XAU/USD, 15m bars", "<div>Data source</div>"),
    ("live price", "latest price 4013.10 (live quote read 14:49 UTC)", "<div>Latest price at the alert</div>"),
    ("trigger price", "beyond the trigger 4000.00", "<div>Trigger price</div>"),
    ("confirmation price", "confirming close 4012.40 at 11 Nov 14:45 UTC", "<div>Confirmation price</div>"),
    ("executable entry", "entry 4012.40 | SL", "<div>Entry</div>"),
    ("$10 / $15 / $20 confirmation status", "CONFIRMATION STATUS: +$10 4010.00 CLOSED BEYOND", "<div>+$10 / +$15 / +$20</div>"),
    ("stop-loss and invalidation", "SL 3999.40", "<div>Stop-loss / invalidation</div>"),
    ("invalidation before the entry", "CANCELLED if price trades 3987.00 (-$13)", "cancelled at ${px(x.p0 - x.dir * C.inv_usd)}"),
    ("targets", "TP1 4025.40 (close half) | TP2 4032.40", "<div>Targets</div>"),
    ("remaining reward after entry", "left from it: TP1 $12.30, TP2 $19.30", "left from it: TP1 $"),
    ("net reward", "NET: reward $714 if every target is reached", "<div>Net reward · R:R</div>"),
    ("R:R", "net R:R 1.11", "net R:R ${f(p.rr_net, 2)}"),
    ("lot size", "lot 0.46", "${f(p.lot, 2)} lot"),
    ("maximum monetary risk", "a $643 loss is possible on this trade", "<div>Lot · largest loss</div>"),
    ("spread", "spread $0.50", "spread $${f(parts.spread, 2)}"),
    ("slippage", "slippage $0.40", "slippage $${f(parts.slippage, 2)}"),
    ("commission", "commission $0.07", "commission $${f(parts.commission, 2)}"),
    ("probability and calibration status", "PROBABILITY: none shown, NOT CALIBRATED", "none shown: <b>not calibrated</b>"),
    ("sample size", "27 of 48", "${v.tp1} of ${v.n}"),
    ("validation reference", "validation B30, engine signals out of sample 2023-25", "<div>Validation reference</div>"),
    ("entry expiry", "VALID until 11 Nov 15:05 UTC", "<div>Valid until</div>"),
    ("setup expiry", "expires after 96 15m bars without a confirming close", "<div>Expires</div>"),
]


def test_every_field_of_the_operators_list_is_on_the_phone_alert_and_on_the_website_card():
    st = {}
    (s,) = C1.open_from(st, {"meta": {"tf": "15m", "price_source": SRC}, "markers": [SIG]}, None)
    setup = [C1.setup_head(SIG, "15m", 0.0, s["id"]), *C1.setup_lines(SIG, 0.0, s)]
    ch = _chart(3, {1: (4000, 4012, 4001, 4008), 2: (4008, 4013, 4007, 4012.40)})
    t_now = ch["t"][-1] + 960
    entry = C1.advance_all(st, {"meta": {"tf": "15m"}, "chart": ch, "markers": [SIG]}, t_now, N.plan_cfg(), 0.0,
                           {"t": t_now, "px": 4013.10, "t_px": ch["t"][-1] + 900 + 240, "live": True})
    phone = "\n".join(setup + entry)
    with open("site/app.js") as f:
        js = f.read()
    assert "${c1Card(A.c1)}" in js and js.count("function c1Card(C)") == 1     # the card is in "Your plan alerts"
    for field, on_phone, on_site in OPERATOR_FIELDS:
        assert on_phone in phone, f"the phone alert lacks: {field}"
        assert on_site in js, f"the website card lacks: {field}"
    assert "probability" not in phone.lower().replace("probability: none shown, not calibrated", "")   # no number is called one
    assert '"until"' not in js and "D.until" in js and "nowS > D.until" in js  # a page left open drops an expired entry



def test_a_new_entry_leads_the_message_when_another_setup_reports_in_the_same_run():
    """Found live 18 Nov 00:36: setup #1's TP1 line came first and setup #2's ENTRY ELIGIBLE alert second, so the phone
    preview showed the old trade's news, not the new entry. The entry now leads; each setup's lines stay together."""
    st = {}
    C1.open_from(st, {"meta": {"tf": "15m"}, "markers": [SIG]}, None)                       # setup #1, trigger 4000
    ch1 = _chart(2, {1: (4000, 4013, 3999, 4012.40)})
    C1.advance_all(st, {"meta": {"tf": "15m"}, "chart": ch1, "markers": [SIG]}, ch1["t"][-1] + 960, N.plan_cfg())
    assert C1.book(st)["open"][0]["status"] == "ACTIVE"                                   # entered at 4012.40, TP1 4025.40
    sig2 = dict(SIG, t=T0 + 1800, px=4016.0)                                               # $16 away: a new idea, setup #2
    C1.open_from(st, {"meta": {"tf": "15m"}, "markers": [SIG, sig2]}, T0)
    assert [x["id"] for x in C1.book(st)["open"]] == [1, 2]
    full = _chart(4, {1: (4000, 4013, 3999, 4012.40), 2: (4012.4, 4016.5, 4011, 4016.0), 3: (4016, 4027, 4015, 4026.5)})
    lines = C1.advance_all(st, {"meta": {"tf": "15m"}, "chart": full, "markers": [SIG, sig2]}, full["t"][-1] + 960, N.plan_cfg())
    tp1 = "XAUUSD 15m BUY confirmed setup #1: TP1 4025.40 reached: close half, move the stop to the entry 4012.40"
    assert lines[0].startswith("XAUUSD 15m BUY ENTRY ELIGIBLE, SETUP #2: entry 4026.50") and tp1 in lines
    assert lines.index(tp1) == len(lines) - 1 == 10                                        # #2's ten lines, then #1's news
    assert all("SETUP #2" in x or not x.startswith("XAUUSD") for x in lines[:10])
    # with no entry in the run the order is the setups' own
    st2 = {}
    C1.open_from(st2, {"meta": {"tf": "15m"}, "markers": [SIG, dict(SIG, t=T0 + 900, px=4040.0)]}, None)
    out = C1.advance_all(st2, {"meta": {"tf": "15m"}, "chart": _chart(3, {2: (4030, 4031, 3986.0, 3990)}), "markers": []},
                         T0 + 3 * 900 + 60, N.plan_cfg())
    assert [x.split(" (")[0] for x in out] == ["XAUUSD 15m BUY SETUP #1 CANCELLED", "XAUUSD 15m BUY SETUP #2 CANCELLED"]
