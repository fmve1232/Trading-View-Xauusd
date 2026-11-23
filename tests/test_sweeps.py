"""W7 amendment A3 (research/registrations/B31b-W7.json): every 15m sweep, its +$10 / +$15 / +$20 follow-up, the
breakout additions (ladder line, MOVE), the phone stream, the website card and the workflow switches. Hand-worked bars."""
import json
import os

import numpy as np
import pandas as pd
import pytest

from quantum import breakouts as B
from quantum import holdout
from quantum import notify as N
from quantum import sweeps as W

ROOT = os.path.join(os.path.dirname(__file__), "..")
T0 = 1795392000                        # 2026-11-23 00:00 UTC (Mon)
KEYS = ("ALERT_BREAKOUTS", "BREAKOUT_TFS", "ALERT_SWEEPS", "ALERT_STRUCTURE", "ALERT_MODE", "ALERT_ZONES", "CONFIRM_MIN_USD",
        "PLAN", "MT5_PRICE_OFFSET", "ENTRY_INTEL")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def only_swings(monkeypatch):
    """Flat bars make every session high / low and 12-bar range a level; these tests isolate the swing levels."""
    monkeypatch.setattr(B, "RANGE_ATR", 0.0)
    monkeypatch.setattr(B, "STATIC", {1: (), -1: ()})


def flat(n, px=4000.0, w=0.5):
    return [(px, px + w, px - w, px)] * n


def bars(rows, sec=900, t0=T0):
    t = np.array([t0 + sec * k for k in range(len(rows))], np.int64)
    o, h, l, c = (np.array(x, float) for x in zip(*rows))
    return {"t": t, "o": o, "h": h, "l": l, "c": c}


def payload(rows, tf, sec, t0=T0):
    b = bars(rows, sec, t0)
    return {"meta": {"tf": tf, "tf_sec": sec, "synthetic": False},
            "chart": {k: b[k].tolist() for k in ("t", "o", "h", "l", "c")}}


def swing15():
    """Flat 4000 +/- 0.5 with a 15m swing high 4003.0 at bar 40 (known at the close of bar 43)."""
    return flat(40) + [(4000.0, 4003.0, 3999.5, 4000.0)] + flat(30)


# ---------------- detection ----------------
def test_a_wick_through_a_level_that_closes_back_is_a_sweep_and_a_close_through_it_is_not(only_swings):
    rows = swing15()
    rows[55] = (4000.0, 4003.8, 3999.9, 4002.0)                    # wick 4003.8 over the 4003.0 swing, close back below
    ev = W.detect(bars(rows), {})
    assert [(e["i"], e["side"], e["dir"], e["ref"], e["ref_kind"], e["ref_tf"], e["wick"], e["close"]) for e in ev] == \
        [(55, 1, -1, 4003.0, "SWH", "15m", 4003.8, 4002.0)]
    rows[55] = (4000.0, 4003.8, 3999.9, 4003.2)                    # the same wick closing above: a breakout
    assert W.detect(bars(rows), {}) == []


def test_a_bar_that_came_from_beyond_the_level_is_not_a_sweep(only_swings):
    rows = swing15()
    rows[54] = (4000.0, 4003.5, 3999.9, 4003.3)                    # closes above 4003.0 (a breakout) ...
    rows[55] = (4003.3, 4003.9, 4001.0, 4002.0)                    # ... then wicks above and closes back below
    assert W.detect(bars(rows), {}) == []


def test_each_level_is_alerted_once(only_swings):
    rows = swing15()
    rows[55] = (4000.0, 4003.8, 3999.9, 4002.0)
    rows[60] = (4000.0, 4003.9, 3999.9, 4002.5)                    # the same swing again: not a second alert
    got = W.detect(bars(rows), {})
    assert [e["i"] for e in got if e["ref_kind"] == "SWH" and e["ref"] == 4003.0] == [55]


def test_an_h1_swing_is_watched_on_15m_bars_from_the_next_h1_bar_and_never_before(only_swings):
    h1 = flat(40) + [(4000.0, 4010.0, 3999.5, 4000.0)] + flat(30)  # H1 swing high 4010.0 at H1 bar 40, known at bar 43's close
    rows = flat(4 * 50)                                            # 15m bars over the same hours, no level of their own at 4010
    k_in, k_early = 4 * 44 + 1, 4 * 43 + 1                          # inside H1 bar 44 / inside H1 bar 43 (before its close)
    rows[k_in] = (4000.0, 4010.6, 3999.9, 4002.0)
    ev = W.detect(bars(rows), {"1h": bars(h1[:50], 3600)})
    assert [(e["i"], e["ref"], e["ref_kind"], e["ref_tf"], e["levels"]) for e in ev] == \
        [(k_in, 4010.0, "SWH", "1h", [{"tf": "1h", "kind": "SWH", "price": 4010.0}])]
    # the same sweep seen while H1 bar 44 is still forming (the H1 payload ends at bar 43): the same event
    ev2 = W.detect(bars(rows[:k_in + 1]), {"1h": bars(h1[:44], 3600)})
    assert [(e["i"], e["ref"], e["ref_tf"]) for e in ev2] == [(k_in, 4010.0, "1h")]
    # a wick inside H1 bar 43, before the close that makes the swing known: no sweep (no look-ahead)
    rows[k_in] = flat(1)[0]
    rows[k_early] = (4000.0, 4010.6, 3999.9, 4002.0)
    assert [e for e in W.detect(bars(rows), {"1h": bars(h1[:50], 3600)}) if e["ref_tf"] == "1h"] == []


def test_day_week_and_session_levels_come_from_m15_only(only_swings, monkeypatch):
    monkeypatch.setattr(B, "STATIC", {1: ("PDH",), -1: ("PDL",)})
    h1 = flat(60)
    rows = flat(4 * 60)
    live: dict = {}
    B.detect(*(bars(h1, 3600)[k] for k in ("t", "o", "h", "l", "c")), 3600, live)
    on15 = W._live_on_15m(bars(rows)["t"], bars(h1, 3600), 3600)
    assert all(kind in W.STRUCT for x in on15 if x for s in (1, -1) for kind, _, _ in x.get(s, []))
    # and the 15m detector keeps its own previous-day levels
    assert any(kind == "PDH" for x in live.values() for kind, _, _ in x.get(1, []))


def test_no_look_ahead_every_sweep_is_the_same_from_the_bars_closed_by_it():
    rng = np.random.default_rng(11)
    c = 4000 + np.cumsum(rng.normal(0, 1.4, 1200))
    o = np.concatenate([[4000.0], c[:-1]])
    rows = list(zip(o, np.maximum(o, c) + rng.uniform(0, 1.2, 1200), np.minimum(o, c) - rng.uniform(0, 1.2, 1200), c))
    h1 = [(rows[k][0], max(r[1] for r in rows[k:k + 4]), min(r[2] for r in rows[k:k + 4]), rows[k + 3][3])
          for k in range(0, 1200, 4)]
    full = W.detect(bars(rows), {"1h": bars(h1, 3600)})
    assert len(full) > 20 and {e["ref_tf"] for e in full} >= {"15m", "1h"}
    by = {e["id"]: e for e in full}
    for cut in range(400, 1200, 151):
        part = W.detect(bars(rows[:cut + 1]), {"1h": bars(h1[:(cut + 1) // 4], 3600)})
        assert {e["id"] for e in part} == {k for k, e in by.items() if e["i"] <= cut}
        assert all(e == by[e["id"]] for e in part)


# ---------------- follow-up ----------------
def _ev(close=4002.0, wick=4003.8, side=1):
    return {"t_close": T0 + 56 * 900, "close": close, "wick": wick, "dir": -side, "side": side}


def test_move_targets_before_the_wick_failed_when_the_wick_comes_first_and_an_ambiguous_bar_is_failed():
    rows = flat(56, 4002.0, 0.3) + [(4001.0, 4002.0, 3991.9, 3992.5),     # +$10 (3992.0) reached
                                    (3992.5, 3993.0, 3986.5, 3987.5),     # +$15 (3987.0)
                                    (3987.5, 4004.0, 3987.0, 4003.0)]     # the wick 4003.8 retaken before +$20
    res, over = W.follow(_ev(), bars(rows))
    assert res == {"10": ["TP", T0 + 57 * 900], "15": ["TP", T0 + 58 * 900], "20": ["SL", T0 + 59 * 900]} and not over
    assert W.stages(res, T0 + 56 * 900) == [("SWEEP", T0 + 56 * 900), ("MOVE10", T0 + 57 * 900), ("MOVE15", T0 + 58 * 900),
                                            ("FAILED", T0 + 59 * 900)]
    amb = flat(56, 4002.0, 0.3) + [(4001.0, 4004.0, 3991.0, 3995.0)]         # target and wick in one bar
    res, _ = W.follow(_ev(), bars(amb))
    assert res["10"][0] == "AMBIGUOUS" and [s for s, _ in W.stages(res, 0)] == ["SWEEP", "FAILED"]
    gap = flat(56, 4002.0, 0.3) + [(4005.0, 4006.0, 3990.0, 3991.0)]         # opens beyond the wick: failed
    assert W.follow(_ev(), bars(gap))[0]["10"][0] == "SL"


def test_the_watch_ends_after_96_bars():
    rows = flat(56 + 96 + 3, 4002.0, 0.3)
    rows[56 + 96] = (4002.0, 4002.0, 3980.0, 3985.0)                       # the 97th bar after the sweep: too late
    res, over = W.follow(_ev(), bars(rows))
    assert over and res == {"10": None, "15": None, "20": None}
    rows[56 + 95] = (4002.0, 4002.0, 3991.0, 3995.0)                       # the 96th: inside the watch
    assert W.follow(_ev(), bars(rows))[0]["10"][0] == "TP"


# ---------------- the live run and the phone ----------------
def test_scan_starts_now_sends_a_fresh_sweep_once_then_the_move_and_records_late_ones(only_swings):
    rows = swing15()[:50] + flat(20)
    rows[55] = (4000.0, 4003.8, 3999.9, 4002.0)
    st = {}
    W.scan(st, {"15m": payload(rows[:50], "15m", 900)}, T0 + 50 * 900 + 120)        # first run: since = now
    due = W.scan(st, {"15m": payload(rows[:56], "15m", 900)}, T0 + 56 * 900 + 120)
    eid = f"SWP:{T0 + 55 * 900}:HI"
    assert [(d["id"], d["stage"]) for d in due] == [(eid, "SWEEP")]
    assert W.scan(st, {"15m": payload(rows[:56], "15m", 900)}, T0 + 56 * 900 + 400) == []   # no repeat
    rows[57] = (4001.0, 4002.0, 3991.5, 3992.5)                                     # +$10 = 3992.0 on bar 57
    due = W.scan(st, {"15m": payload(rows[:58], "15m", 900)}, T0 + 58 * 900 + 1300)  # 21 min after: LATE
    rec = st["brk"]["sw"][eid]
    assert due == [] and rec["phone"] == {"SWEEP": "DUE", "MOVE10": "LATE"} and st["brk"]["since_sw"] == T0 + 50 * 900 + 120


def test_sweeps_before_the_first_run_are_never_recorded(only_swings):
    rows = swing15()
    rows[55] = (4000.0, 4003.8, 3999.9, 4002.0)
    st = {}
    W.scan(st, {"15m": payload(rows[:60], "15m", 900)}, T0 + 60 * 900 + 120)
    assert st["brk"]["sw"] == {}


def test_the_short_messages_with_the_mt5_offset():
    ev = {"side": 1, "dir": -1, "ref": 4003.0, "ref_kind": "SWH", "ref_tf": "1h", "wick": 4003.8, "close": 4002.0,
          "levels": [{"tf": "1h", "kind": "SWH", "price": 4003.0}, {"tf": "15m", "kind": "SWH", "price": 4003.1}],
          "stages": {"SWEEP": {}, "MOVE10": {}}}
    fmt = lambda x: f"{x + 1.5:.2f}"                                   # noqa: E731 - an MT5 offset of +1.50
    clock = lambda t: "05:00 MT5 / 08:00 PKT"                          # noqa: E731
    assert W.message(ev, "SWEEP", 0, fmt, clock) == [
        "🔴 GOLD SWEEP · buy-side liquidity", "Swept: 4004.50 H1 swing high (+1 more)",
        "Wick: 4005.30 · Close: 4003.50 (back below)", "Reversal side: SELL", "+$10 / +$15 / +$20 at: 3993.50 / 3988.50 / 3983.50",
        "Invalid if price trades above 4005.30", "Entry: Not validated", "Time: 05:00 MT5 / 08:00 PKT"]
    assert W.message(ev, "MOVE10", 0, fmt, clock) == [
        "🔴 GOLD SWEEP +$10 REACHED", "Swept: 4004.50 H1 swing high (+1 more)", "SELL move from 4003.50 to 3993.50",
        "Invalid if price trades above 4005.30", "Entry: Not validated", "Time: 05:00 MT5 / 08:00 PKT"]
    assert "Invalid" not in " ".join(W.message(ev, "MOVE20", 0, fmt, clock))
    assert W.message(ev, "FAILED", 0, fmt, clock) == [
        "⚠️ GOLD SWEEP FAILED", "Swept: 4004.50 H1 swing high (+1 more)", "Price traded above the wick 4005.30",
        "Reached first: +$10", "Time: 05:00 MT5 / 08:00 PKT"]
    low = {**ev, "side": -1, "dir": 1, "ref_kind": "PDL", "ref_tf": "15m", "levels": ev["levels"][:1], "wick": 3990.0, "close": 3992.0}
    m = W.message(low, "SWEEP", 0, fmt, clock)
    assert m[0] == "🟢 GOLD SWEEP · sell-side liquidity" and m[2] == "Wick: 3991.50 · Close: 3993.50 (back above)" and \
        m[4] == "+$10 / +$15 / +$20 at: 4003.50 / 4008.50 / 4013.50" and m[5] == "Invalid if price trades below 3991.50"
    allt = " ".join(" ".join(W.message(ev, s, 0, fmt, clock)) for s in ("SWEEP", "MOVE10", "MOVE20", "FAILED"))
    assert "%" not in allt and "probab" not in allt.lower() and "lot" not in allt.lower()


def test_the_switch(monkeypatch):
    for v, want in ((None, "phone"), ("site", "site"), ("0", "off"), ("off", "off"), ("1", "phone")):
        if v is None:
            monkeypatch.delenv("ALERT_SWEEPS", raising=False)
        else:
            monkeypatch.setenv("ALERT_SWEEPS", v)
        assert W.mode() == want


def _run_case(monkeypatch, value, only_swings_fixture=None):
    rows = swing15()[:50] + flat(20)
    rows[55] = (4000.0, 4003.8, 3999.9, 4002.0)
    if value is not None:
        monkeypatch.setenv("ALERT_SWEEPS", value)
    calls = []
    monkeypatch.setattr(N, "_say", lambda stream, lines, events=None, desc=None, **k: calls.append((stream, events, lines)) or ["ntfy"])
    st = {}
    N.sweeps_run(st, {"15m": payload(rows[:50], "15m", 900)}, T0 + 50 * 900 + 120, 0.0)
    rep, sent = N.sweeps_run(st, {"15m": payload(rows[:56], "15m", 900)}, T0 + 56 * 900 + 120, 0.0)
    return st, rep, sent, calls


def test_the_phone_gets_each_sweep_once_through_the_delivery_log(monkeypatch, only_swings):
    st, rep, sent, calls = _run_case(monkeypatch, None)
    eid = f"SWP:{T0 + 55 * 900}:HI"
    assert [(c[0], c[1]) for c in calls] == [("sweeps", [f"{eid}:SWEEP"])] and calls[0][2][0] == "🔴 GOLD SWEEP · buy-side liquidity"
    assert st["brk"]["sw"][eid]["phone"] == {"SWEEP": "SENT"} and rep["ok"] and rep["events"][0]["id"] == eid
    assert rep["record"]["15m"]["sweeps"] == 1 and rep["record"]["ALL"]["10"]["decided"] == 0


def test_site_mode_sends_nothing_and_off_does_nothing(monkeypatch, only_swings):
    st, rep, sent, calls = _run_case(monkeypatch, "site")
    assert calls == [] and sent == [] and list(st["brk"]["sw"].values())[0]["phone"] == {"SWEEP": "SITE"}
    st, rep, sent, calls = _run_case(monkeypatch, "0")
    assert calls == [] and rep == {"id": W.ID, "on": False} and "sw" not in st.get("brk", {})


def test_the_record_counts_target_first_per_level_timeframe_with_wilson_from_30():
    recs = {f"x{k}": {"ref_tf": "1h", "res": {"10": ["TP" if k < 20 else "SL", 0], "15": None, "20": None}} for k in range(30)}
    r = W.record(recs)
    assert r["1h"]["sweeps"] == 30 and r["1h"]["10"]["decided"] == 30 and r["1h"]["10"]["target_first"] == 20
    assert r["1h"]["10"]["wilson95"] == W.wilson(20, 30) and r["15m"]["sweeps"] == 0 and r["ALL"]["15"]["decided"] == 0
    assert W.record({k: v for k, v in list(recs.items())[:29]})["1h"]["10"]["wilson95"] is None


# ---------------- breakout additions ----------------
def test_the_confirmed_message_carries_the_ladder_and_a_move_message_reports_the_target():
    ev = {"dir": 1, "ref": 4010.0, "ref_kind": "PDH"}
    fmt = lambda x: f"{x + 1.5:.2f}"                                   # noqa: E731
    clock = lambda t: "T"                                              # noqa: E731
    m = B.message(ev, "15m", "CONFIRMED", {"c": 4012.0, "t_close": 0, "how": "ACCEPTED"}, fmt, clock)
    assert m[-2:] == ["+$10 / +$15 / +$20 at: 4023.50 / 4028.50 / 4033.50", "Time: T"]
    assert "+$10" not in " ".join(B.message(ev, "15m", "RETEST", {"c": 4012.0, "t_close": 0}, fmt, clock))
    assert B.message(ev, "1h", "MOVE15", {"c": 4012.0, "t_close": 0}, fmt, clock) == [
        "🟢 GOLD H1 +$15 REACHED", "Direction: BUY", "Level: 4011.50 (prev day high)",
        "From the confirmation close 4013.50 to 4028.50", "Entry: Not validated", "Time: T"]


def test_a_breakout_move_is_sent_when_the_e1_race_reaches_a_target_on_the_newest_bar(only_swings):
    rows = flat(40) + [(4000.0, 4003.0, 3999.5, 4000.0)] + flat(30)
    rows[54] = (4000.0, 4002.8, 3999.9, 4002.6)
    rows[55] = (4002.6, 4003.6, 4002.4, 4003.2)                   # breakout of the 4003.0 swing
    rows[56] = (4003.2, 4004.0, 4003.1, 4003.8)
    rows[57] = (4003.8, 4004.5, 4003.5, 4004.2)                   # accepted: E1 at 4004.2
    st = {}
    B.scan(st, {"15m": payload(rows[:50], "15m", 900)}, T0 + 50 * 900 + 300, 650.0)
    for k in (56, 58):
        B.scan(st, {"15m": payload(rows[:k], "15m", 900)}, T0 + k * 900 + 300, 650.0)
    rows[58] = (4004.2, 4014.4, 4004.0, 4014.0)                   # +$10 = 4014.2 on bar 58
    due = B.scan(st, {"15m": payload(rows[:59], "15m", 900)}, T0 + 59 * 900 + 300, 650.0)
    eid = f"BRK:M15:{T0 + 55 * 900}:UP"
    assert [(d["id"], d["stage"]) for d in due] == [(eid, "MOVE10")] and due[0]["bar"]["c"] == 4004.2
    assert st["brk"]["events"][eid]["stages"]["MOVE10"] == {"t": T0 + 59 * 900}


# ---------------- wiring ----------------
def test_the_module_is_not_an_engine_source_and_sends_nothing_itself():
    assert "sweeps.py" not in holdout.ENGINE_SOURCES
    src = open(W.__file__).read()
    imports = sorted(x.strip() for x in src.splitlines() if x.startswith(("import ", "from ")))
    assert imports == ["from . import breakouts as B", "from __future__ import annotations", "import math", "import numpy as np",
                       "import os"]
    assert "send(" not in src and "requests" not in src


def test_the_website_card_and_the_workflow_switches_are_wired():
    js = open(os.path.join(ROOT, "site", "app.js")).read()
    assert js.count("function sweepsCard(SW)") == 1 and "${breakoutsCard(A.breakouts)}${sweepsCard(A.sweeps)}" in js
    card = js[js.index("function sweepsCard(SW)"):]
    card = card[:card.index("\nfunction ", 10)]
    assert "not an entry" in card and "chance" not in card and "probab" not in card.lower()
    wf = open(os.path.join(ROOT, ".github", "workflows", "quantum-site.yml")).read()
    for v in ("ALERT_SWEEPS", "BREAKOUT_TFS", "ALERT_BREAKOUTS"):
        assert f"{v}: ${{{{ vars.{v} }}}}" in wf, v


def test_the_registration_fixes_what_the_code_runs():
    reg = json.load(open(os.path.join(ROOT, "research", "registrations", "B31b-W7.json")))
    a3 = [a for a in reg["amendments"] if a["id"] == "A3"][0]
    assert "96 15m bars (24 h)" in a3["sweeps"]["follow_up"] and W.HOLD == 96 and B.TARGETS == (10.0, 15.0, 20.0)
    assert "ALERT_SWEEPS" in a3["sweeps"]["switch"] and W.STRUCT == ("SWH", "SWL", "EQH", "EQL", "RGH", "RGL")
    assert set(W.LEVEL_TFS) == set(B.TFS) and W.BAR == 900


def test_sweeps_with_breakouts_off_leave_the_breakout_start_untouched(monkeypatch, only_swings):
    st, _, _, _ = _run_case(monkeypatch, None)
    assert set(st["brk"]) == {"since_sw", "sw"}                        # no breakout book was created
    B.scan(st, {}, T0 + 99 * 900, 650.0)
    assert st["brk"]["since"] == T0 + 99 * 900 and st["brk"]["since_sw"] == T0 + 50 * 900 + 120
