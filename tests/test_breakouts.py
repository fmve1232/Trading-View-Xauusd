"""W7 (research/registrations/B31b-W7.json): M15 / M30 breakout monitoring. Hand-worked bars for every level kind and
stage, the close-not-wick rule, one break per level, the range rule of amendment A1, no look-ahead (truncation), the
live bookkeeping (since, freshness, LATE, one message per stage), the operator's short format, the shadow entry, and
that the module changes no other alert or record."""
import json
import os

import numpy as np
import pandas as pd
import pytest

from quantum import breakouts as B
from quantum import holdout
from quantum import notify as N

T0 = 1795392000                        # 2026-11-23 00:00 UTC (Mon); a trading day rolls at 22:00 UTC (17:00 New York)
KEYS = ("ALERT_BREAKOUTS", "BREAKOUT_TFS", "ALERT_SWEEPS", "ALERT_STRUCTURE", "ALERT_MODE", "ALERT_ZONES", "CONFIRM_MIN_USD", "PLAN", "MT5_PRICE_OFFSET",
        "ENTRY_INTEL")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def no_range(monkeypatch):
    """Identical flat bars always form a 12-bar range; tests of the other levels switch the range rule off."""
    monkeypatch.setattr(B, "RANGE_ATR", 0.0)


@pytest.fixture
def only_swings(monkeypatch):
    """Flat bars also make every completed session's high / low a level just above / below them; the swing, stage and
    shadow tests isolate the swing levels (the day / session test keeps them)."""
    monkeypatch.setattr(B, "RANGE_ATR", 0.0)
    monkeypatch.setattr(B, "STATIC", {1: (), -1: ()})


def flat(n, px=4000.0, w=0.5):
    return [(px, px + w, px - w, px)] * n


def arrays(rows, sec=900, t0=T0):
    t = np.array([t0 + sec * k for k in range(len(rows))], np.int64)
    o, h, l, c = (np.array(x, float) for x in zip(*rows))
    return t, o, h, l, c


def run(rows, sec=900, t0=T0):
    t, o, h, l, c = arrays(rows, sec, t0)
    evs, ctx = B.detect(t, o, h, l, c, sec)
    return evs, (t, o, h, l, c)


def brk(rows):
    """A plain (non-displacement) breakout of the 4003.0 swing: bar 54 closes 4002.6 below it, bar 55 closes 4003.2
    above it with a 0.6 body (under 1 ATR)."""
    rows[54] = (4000.0, 4002.8, 3999.9, 4002.6)
    rows[55] = (4002.6, 4003.6, 4002.4, 4003.2)
    return rows


def swing_rows():
    """Flat 4000 +/- 0.5 with a swing high 4003.0 at bar 40 (known at the close of bar 43)."""
    rows = flat(40) + [(4000.0, 4003.0, 3999.5, 4000.0)] + flat(30)
    return rows


# ---------------- detection ----------------
def test_a_close_beyond_a_swing_high_is_a_breakout_and_a_wick_is_not(only_swings):
    rows = swing_rows()
    rows[50] = (4000.0, 4003.8, 3999.6, 4002.5)                     # wick through 4003.0, close below: no breakout
    brk(rows)                                                       # closes above 4003.0 after 4002.6: breakout
    evs, _ = run(rows)
    up = [e for e in evs if e["dir"] == 1]
    assert [e["i"] for e in up] == [55]
    e = up[0]
    assert e["ref"] == 4003.0 and e["ref_kind"] == "SWH" and [x["kind"] for x in e["levels"]] == ["SWH"]
    assert e["t_close"] == T0 + 56 * 900 and not e["disp"] and e["body_atr"] == pytest.approx(0.6 / e["atr"])


def test_a_swing_is_not_a_level_before_its_third_bar_closes(only_swings):
    rows = swing_rows()
    rows[42] = (4000.0, 4003.5, 3999.8, 4003.3)                     # bar 42 closes above 4003.0, but the pivot is not known
    rows[40] = (4000.0, 4003.0, 3999.5, 4000.0)
    evs, _ = run(rows)
    assert not [e for e in evs if e["dir"] == 1 and e["i"] == 42 and e["ref_kind"] == "SWH"]


def test_each_level_breaks_once(only_swings):
    rows = swing_rows()
    brk(rows)
    rows[56] = (4003.2, 4003.3, 4001.0, 4001.5)                     # back below
    rows[57] = (4001.5, 4003.9, 4001.4, 4003.6)                     # above again: the same swing is consumed
    evs, _ = run(rows)
    assert [e["i"] for e in evs if e["dir"] == 1 and e["ref"] == 4003.0] == [55]


def test_stages_detected_confirmed_retest_failed(only_swings):
    rows = swing_rows()
    brk(rows)                                                       # breakout close 4003.2
    rows[56] = (4003.2, 4004.0, 4003.1, 4003.8)
    rows[57] = (4003.8, 4004.5, 4003.5, 4004.2)                     # second close beyond: ACCEPTED at 57
    rows[58] = (4004.2, 4004.4, 4002.9, 4003.4)                     # reaches 4003.0, closes above: RETEST at 58
    rows[60] = (4003.4, 4003.5, 4001.8, 4002.0)                     # closes back below 4003.0: FAILED at 60
    for k in (59,):
        rows[k] = (4003.4, 4003.9, 4003.2, 4003.4)
    evs, (t, o, h, l, c) = run(rows)
    e = [e for e in evs if e["i"] == 55][0]
    st = B.follow(e, o, h, l, c)
    assert (st["confirmed"], st["how"], st["retest"], st["failed"]) == (57, "ACCEPTED", 58, 60)
    assert B.stage_list(e, st) == [("DETECTED", 55), ("CONFIRMED", 57), ("RETEST", 58), ("FAILED", 60)]


def test_an_early_close_back_inside_is_a_false_breakout(only_swings):
    rows = swing_rows()
    brk(rows)
    rows[56] = (4003.2, 4003.3, 4002.0, 4002.6)
    evs, (t, o, h, l, c) = run(rows)
    st = B.follow([e for e in evs if e["i"] == 55][0], o, h, l, c)
    assert st["failed"] == 56 and st["confirmed"] is None


def test_a_displacement_close_is_confirmed_at_once_and_skips_detected(only_swings):
    rows = swing_rows()
    rows[55] = (3999.6, 4006.0, 3999.5, 4005.8)                     # body 6.2 >= 1 x ATR (about 1.1)
    evs, (t, o, h, l, c) = run(rows)
    e = [e for e in evs if e["i"] == 55][0]
    st = B.follow(e, o, h, l, c)
    assert e["disp"] and st["confirmed"] == 55 and st["how"] == "DISPLACEMENT"
    assert B.stage_list(e, st)[0] == ("CONFIRMED", 55)


def test_the_watch_closes_after_sixteen_bars(only_swings):
    rows = swing_rows()
    brk(rows)
    for k in range(56, 71):
        rows[k] = (4004.0, 4004.5, 4003.5, 4004.0)
    rows.append((4004.0, 4004.5, 4003.5, 4004.0))
    evs, (t, o, h, l, c) = run(rows)
    st = B.follow([e for e in evs if e["i"] == 55][0], o, h, l, c)
    assert st["closed"] == 55 + 16 and st["failed"] is None
    rows[70] = (4004.0, 4004.1, 4001.0, 4001.5)                     # bar 70 = the 15th after the breakout: inside the watch
    evs, (t, o, h, l, c) = run(rows)
    assert B.follow([e for e in evs if e["i"] == 55][0], o, h, l, c)["failed"] == 70


def test_a_dip_to_the_level_before_confirmation_is_not_a_retest(only_swings):
    rows = swing_rows()
    brk(rows)
    rows[56] = (4003.2, 4003.6, 4002.9, 4003.4)                     # reaches 4003.0 and closes above, not yet confirmed
    rows[57] = (4003.4, 4004.5, 4003.3, 4004.2)                     # ACCEPTED at 57; bar 58 (flat 4000) fails
    evs, (t, o, h, l, c) = run(rows)
    st = B.follow([e for e in evs if e["i"] == 55][0], o, h, l, c)
    assert (st["confirmed"], st["retest"], st["failed"]) == (57, None, 58)


def test_a_level_that_appears_with_price_already_beyond_it_is_not_a_breakout(no_range, monkeypatch):
    rows = flat(60)
    rows[30] = (4000.0, 4000.2, 3998.0, 3998.5)                     # closes back under the 3999.0 level ...
    rows[31] = (3998.5, 4000.2, 3998.4, 4000.0)                     # ... and above it again: the only breakout
    def pools(h, l, cal, eqh, eql):
        n = len(h)
        out = {k: np.full(n, np.nan) for s in B.STATIC for k in B.STATIC[s]}
        out["PDH"] = np.full(n, 3999.0)                              # live from bar 0 with every close above it
        return out, None
    monkeypatch.setattr(B.shadow, "build_pools", pools)
    evs, _ = run(rows)
    assert [e["i"] for e in evs if any(x["kind"] == "PDH" for x in e["levels"])] == [31]


def test_equal_highs_are_a_level(only_swings):
    rows = flat(40) + [(4000.0, 4003.0, 3999.5, 4000.0)] + flat(5) + [(4000.0, 4003.3, 3999.5, 4000.0)] + flat(30)
    rows[60] = (4000.0, 4003.6, 3999.8, 4003.5)                     # closes above both swings (4003.0 and 4003.3)
    evs, _ = run(rows)
    e = [e for e in evs if e["dir"] == 1 and e["i"] == 60][0]
    assert {x["kind"] for x in e["levels"]} == {"EQH", "SWH"} and e["primary"] == "EQH"
    assert e["ref"] == 4003.0 and max(x["price"] for x in e["levels"] if x["kind"] == "EQH") == 4003.3


def test_a_range_breaks_once_and_a_box_holding_that_bar_is_not_a_new_range():
    rows = flat(60, w=0.2)                                           # 12-bar boxes 0.4 high, ATR about 0.4
    rows[45] = (4000.0, 4000.7, 3999.9, 4000.6)                     # closes above the box high 4000.2
    rows[46] = (4000.6, 4001.0, 4000.5, 4000.9)                     # above bar 45's high: no second range breakout
    evs, _ = run(rows)
    rg = [e for e in evs if any(x["kind"] == "RGH" for x in e["levels"])]
    assert [e["i"] for e in rg] == [45] and rg[0]["ref"] == pytest.approx(4000.2)
    rows = flat(60, w=0.2)                                           # a small breakout: the box holding it is still a range
    rows[45] = (4000.0, 4000.35, 3999.9, 4000.3)                    # box 33..44 = 0.4 high; closes above 4000.2
    rows[46] = (4000.3, 4000.45, 4000.25, 4000.4)                   # above 4000.35 (box 34..45 is 0.55 <= 1.5 ATR)
    evs, _ = run(rows)
    assert [e["i"] for e in evs if any(x["kind"] == "RGH" for x in e["levels"])] == [45]   # A1: no second range breakout


def test_previous_day_high_and_asia_high_on_real_calendar_days(no_range):
    day = 96                                                         # bars 0-95 = trading day 1, 96-191 = day 2, 192+ = day 3
    rows = flat(3 * day + 10)
    rows[30] = (4000.0, 4006.0, 3999.5, 4000.0)                     # day 1 high 4006.0
    k1, k2 = day + 60, 2 * day + 60                                  # 13:00 UTC on days 2 and 3 (after Asia and London open)
    rows[k1] = (4000.0, 4006.6, 3999.8, 4006.3)                     # day 2: closes above 4006.0; day 2 high = 4006.6
    rows[k2] = (4000.0, 4007.2, 3999.8, 4007.0)                     # day 3: closes above 4006.6
    evs, _ = run(rows, t0=T0 - 2 * 3600)                             # start at 22:00 UTC: bar 0 opens a trading day
    lv = {e["i"]: {x["kind"]: x["price"] for x in e["levels"]} for e in evs if e["dir"] == 1}
    assert lv[k1]["PDH"] == 4006.0 and lv[k1]["ASH"] == 4000.5 and lv[k2]["PDH"] == 4006.6   # each day's PDH breaks once
    e1 = [e for e in evs if e["dir"] == 1 and e["i"] == k1][0]
    assert e1["primary"] == "PDH" and e1["ref_kind"] in ("ASH", "LOH") and e1["ref"] == 4000.5   # nearest = first crossed


def walk(n=1400, seed=3, sec=900):
    rng = np.random.default_rng(seed)
    c = 4000 + np.cumsum(rng.normal(0, 1.4, n))
    o = np.concatenate([[4000.0], c[:-1]])
    h = np.maximum(o, c) + rng.uniform(0, 1.0, n)
    l = np.minimum(o, c) - rng.uniform(0, 1.0, n)
    return list(zip(o, h, l, c))


@pytest.mark.parametrize("seed, sec", [(3, 900), (5, 1800)])
def test_no_look_ahead_every_event_is_the_same_from_the_bars_closed_by_it(seed, sec):
    rows = walk(seed=seed, sec=sec)
    full, (t, o, h, l, c) = run(rows, sec=sec)
    assert len(full) > 30 and {e["dir"] for e in full} == {1, -1}
    by_i = {(e["i"], e["dir"]): e for e in full}
    for cut in range(200, len(rows), 97):
        part, _ = run(rows[:cut + 1], sec=sec)
        for e in part:
            f = by_i[(e["i"], e["dir"])]
            assert e == f
        assert {(e["i"], e["dir"]) for e in part} == {k for k in by_i if k[0] <= cut}
        for e in part:                                                # stages seen so far are those of the full data
            st, sf = B.follow(e, o, h, l, c, cut + 1), B.follow(by_i[(e["i"], e["dir"])], o, h, l, c)
            assert [x for x in B.stage_list(e, st)] == [x for x in B.stage_list(e, sf) if x[1] <= cut]


# ---------------- shadow ENTRY READY ----------------
def test_shadow_entry_worked_by_hand(only_swings):
    rows = swing_rows()
    brk(rows)
    rows[56] = (4003.2, 4004.0, 4003.1, 4003.8)
    rows[57] = (4003.8, 4004.5, 4003.5, 4004.2)
    evs, (t, o, h, l, c) = run(rows)
    e = [e for e in evs if e["i"] == 55][0]
    st = B.follow(e, o, h, l, c)
    ctx = {"atr": np.full(len(c), e["atr"]), "cost": np.full(len(c), 0.97)}
    x = B.shadow_entries(e, st, o, h, l, c, ctx, 650.0)
    stop = 4002.4 - 0.2 * e["atr"]                                   # the lowest low of bars 55 .. 57, less 0.2 ATR
    assert x["E1"]["entry"] == 4004.2 and x["E1"]["stop"] == pytest.approx(round(stop, 2))
    assert x["E1"]["tp"] == [4014.2, 4019.2, 4024.2] and x["E2"]["entry"] == 4003.0
    D = 4004.2 - stop
    assert x["E1"]["lots"] == pytest.approx(np.floor(650 / ((D + 0.97) * 100) / 0.01 + 1e-9) * 0.01)
    assert x["E1"]["ready"] is False and any("over 15%" in w for w in x["E1"]["why"])   # $0.97 cost on a ~$2 stop


def test_shadow_race_counts_an_ambiguous_bar_and_a_gap_as_the_stop():
    b15 = {"t": np.array([T0 + 900 * k for k in range(4)], np.int64), "o": np.array([4000.0, 4000.0, 3980.0, 3980.0]),
           "h": np.array([4011.0, 4005.0, 3982.0, 3982.0]), "l": np.array([3994.0, 3999.0, 3975.0, 3975.0]),
           "c": np.array([4000.0, 4000.0, 3980.0, 3980.0])}
    x = {"entry": 4000.0, "stop": 3995.0}
    r = B.race(x, 1, b15, T0)
    assert r["res"]["10"][0] == "AMBIGUOUS" and r["res"]["15"][0] == "SL"
    r2 = B.race({"entry": 4000.0, "stop": 3990.0}, 1, b15, T0 + 900)
    assert r2["res"]["10"][0] == "SL" and r2["res"]["10"][1] == T0 + 3 * 900          # opened through the stop


# ---------------- live bookkeeping and the phone text ----------------
def payload(rows, tf, sec, t0=T0, gen=None):
    t, o, h, l, c = arrays(rows, sec, t0)
    return {"meta": {"tf": tf, "tf_sec": sec, "synthetic": False, "price_source": "td",
                     "generated_utc": pd.Timestamp(int(t[-1]) + sec + 120, unit="s", tz="UTC").isoformat()},
            "markers": [], "decisions": [], "dashboard": {},
            "chart": {"t": t.tolist(), "o": o.tolist(), "h": h.tolist(), "l": l.tolist(), "c": c.tolist(),
                      "pdh": [None] * len(t), "pdl": [None] * len(t), "pwh": [None] * len(t), "pwl": [None] * len(t)}}


def test_scan_starts_now_sends_fresh_stages_once_and_records_late_ones(only_swings):
    rows = swing_rows()
    brk(rows)
    rows[56] = (4003.2, 4004.0, 4003.1, 4003.8)
    rows[57] = (4003.8, 4004.5, 4003.5, 4004.2)
    st = {}
    B.scan(st, {"15m": payload(rows[:50], "15m", 900)}, T0 + 50 * 900 + 300, 650.0)       # first run: since = now
    due = B.scan(st, {"15m": payload(rows[:56], "15m", 900)}, T0 + 56 * 900 + 300, 650.0)
    assert [(d["stage"], d["id"]) for d in due] == [("DETECTED", f"BRK:M15:{T0 + 55 * 900}:UP")]
    assert B.scan(st, {"15m": payload(rows[:56], "15m", 900)}, T0 + 56 * 900 + 400, 650.0) == []   # same bar: no repeat
    due = B.scan(st, {"15m": payload(rows[:58], "15m", 900)}, T0 + 58 * 900 + 1300, 650.0)    # 21 min after: LATE
    rec = st["brk"]["events"][f"BRK:M15:{T0 + 55 * 900}:UP"]
    assert due == [] and rec["phone"]["CONFIRMED"] == "LATE" and rec["stages"]["CONFIRMED"]["how"] == "ACCEPTED"
    assert rec["shadow"]["E1"]["entry"] == 4004.2
    for x in rec["shadow"].values():                               # the registered fresh-data check
        assert x["ready"] is False and any(w.startswith("seen 21 min after the confirmation close") for w in x["why"])


def test_a_shadow_entry_without_a_valid_stop_is_not_raced(only_swings, monkeypatch):
    rows = swing_rows()
    brk(rows)
    rows[56] = (4003.2, 4004.0, 4003.1, 4003.8)
    rows[57] = (4003.8, 4004.5, 4003.5, 4004.2)
    real = B.shadow_entries
    def wrong(*a, **k):                                              # force a stop on the wrong side of E2
        out = real(*a, **k)
        out["E2"].update(D=-0.5, lots=0.0, ready=False)
        return out
    monkeypatch.setattr(B, "shadow_entries", wrong)
    st = {}
    B.scan(st, {"15m": payload(rows[:50], "15m", 900)}, T0 + 50 * 900 + 300, 650.0)
    B.scan(st, {"15m": payload(rows[:58], "15m", 900)}, T0 + 58 * 900 + 300, 650.0)
    x = st["brk"]["events"][f"BRK:M15:{T0 + 55 * 900}:UP"]["shadow"]
    assert x["E2"]["done"] is True and "fill" not in x["E2"] and "fill" in x["E1"]
    assert x["E1"]["ready"] is False and not any(w.startswith("seen ") for w in x["E1"]["why"])   # fresh: no late reason


def test_a_stage_whose_bar_is_not_the_newest_is_late_even_within_twenty_minutes(only_swings):
    rows = swing_rows()
    brk(rows)
    rows[56] = (4003.2, 4004.0, 4003.1, 4003.8)
    st = {}
    B.scan(st, {"15m": payload(rows[:50], "15m", 900)}, T0 + 50 * 900 + 300, 650.0)
    due = B.scan(st, {"15m": payload(rows[:57], "15m", 900)}, T0 + 57 * 900 + 300, 650.0)   # bar 55 closed 20 min ago
    assert due == [] and st["brk"]["events"][f"BRK:M15:{T0 + 55 * 900}:UP"]["phone"] == {"DETECTED": "LATE"}


def test_shadow_room_and_extension_reasons(only_swings):
    rows = swing_rows()
    brk(rows)
    rows[56] = (4003.2, 4004.0, 4003.1, 4003.8)
    rows[57] = (4003.8, 4004.5, 4003.5, 4004.2)
    evs, (t, o, h, l, c) = run(rows)
    e = [e for e in evs if e["i"] == 55][0]
    st = B.follow(e, o, h, l, c)
    ctx = {"atr": np.full(len(c), 1.0), "cost": np.full(len(c), 0.0)}
    x = B.shadow_entries({**e, "atr": 1.0, "beyond": [4008.0]}, st, o, h, l, c, ctx, 650.0)
    assert "price already $1.20 beyond the level (over 1 ATR = $1.00)" in x["E1"]["why"]     # E1 4004.2, level 4003.0
    assert "next level only $3.80 away (under $10)" in x["E1"]["why"] and "next level only $5.00 away (under $10)" in x["E2"]["why"]
    assert not any(w.startswith("price already") for w in x["E2"]["why"])                  # E2 fills at the level
    y = B.shadow_entries({**e, "atr": 2.0, "beyond": [4016.0]}, st, o, h, l, c, ctx, 650.0)
    assert y["E1"]["why"] == [] and y["E1"]["ready"] is True and y["E1"]["loss_planned"] <= 650.0


def _b15(rows):
    o, h, l, c = (np.array(x, float) for x in zip(*rows))
    return {"t": np.array([T0 + 900 * k for k in range(len(rows))], np.int64), "o": o, "h": h, "l": l, "c": c}


def test_shadow_race_of_a_limit_fill_miss_and_stop_on_the_fill_bar():
    b15 = _b15([(4005.0, 4006.0, 4004.0, 4005.0),          # limit 4003.0 not reached
                (4002.5, 4004.0, 4002.0, 4003.5),          # opens below the limit: fills at the open 4002.5
                (4004.0, 4013.0, 4003.5, 4012.0)])         # +$10 from 4002.5 = 4012.5: TP
    r = B.race({"entry": 4003.0, "stop": 4001.0}, 1, b15, T0, limit=True)
    assert r["fill"] == {"t": T0 + 900, "px": 4002.5} and r["res"]["10"] == ["TP", T0 + 3 * 900]
    assert r["res"]["15"] is None and r["res"]["20"] is None
    assert B.race({"entry": 4003.0, "stop": 4001.0}, 1, b15, T0, limit=True, valid_until=T0 + 900)["fill"] == "MISSED"
    s = B.race({"entry": 4003.0, "stop": 4002.2}, 1, b15, T0, limit=True)          # the fill bar reaches the stop
    assert s["res"] == {"10": ["SL", T0 + 2 * 900], "15": ["SL", T0 + 2 * 900], "20": ["SL", T0 + 2 * 900]}
    p = B.race({"entry": 3990.0, "stop": 3985.0}, 1, b15, T0, limit=True)          # never reached, no expiry yet
    assert p["fill"] is None and all(v is None for v in p["res"].values())
    d = B.race({"entry": 4006.0, "stop": 4008.0}, -1, b15, T0, limit=True)         # a sell limit, filled on bar 0
    assert d["fill"] == {"t": T0, "px": 4006.0}


def test_a_bar_opening_through_the_stop_is_the_stop_even_when_it_reaches_the_target():
    b15 = _b15([(3990.0, 4012.0, 3989.0, 4011.0)])
    r = B.race({"entry": 4000.0, "stop": 3995.0}, 1, b15, T0)
    assert r["res"]["10"] == ["SL", T0 + 900]


def test_a_failed_send_is_recorded_send_failed(monkeypatch, only_swings):
    rows = swing_rows()
    brk(rows)
    st = {}
    calls = []
    monkeypatch.setattr(N, "_say", lambda stream, lines, events=None, **k: calls.append((stream, events)) or [])
    N.breakouts_run(st, {"15m": payload(rows[:50], "15m", 900)}, T0 + 50 * 900 + 300, 0.0, None)
    blk, sent = N.breakouts_run(st, {"15m": payload(rows[:56], "15m", 900)}, T0 + 56 * 900 + 300, 0.0, None)
    eid = f"BRK:M15:{T0 + 55 * 900}:UP"
    assert calls == [("breakouts", [f"{eid}:DETECTED"])] and sent[0]["sent"] == []
    assert st["brk"]["events"][eid]["phone"] == {"DETECTED": "SEND_FAILED"} and blk["counts"]["phone"] == {"SEND_FAILED": 1}


def test_counts_by_timeframe_direction_session_and_fate():
    now = T0 + 10 * 86400
    ev = lambda i, tf, d, sess, stages, phone, age: {"tf": tf, "dir": d, "sess": sess, "stages": stages,   # noqa: E731
                                                      "phone": phone, "t_close": now - age}
    bk = {"events": {
        "a": ev(0, "15m", 1, "ASIAN", {"DETECTED": {}, "FAILED": {}}, {"DETECTED": "SENT", "FAILED": "SENT"}, 3600),
        "b": ev(1, "30m", -1, "LONDON", {"CONFIRMED": {}, "RETEST": {}, "FAILED": {}}, {"CONFIRMED": "LATE"}, 7200),
        "c": ev(2, "15m", -1, "NEW YORK", {"DETECTED": {}, "CONFIRMED": {}}, {"DETECTED": "SITE"}, 86400),
        "d": ev(3, "15m", 1, "OFF", {"DETECTED": {}}, {"DETECTED": "SENT"}, 8 * 86400)}}            # outside 7 days
    k = B.counts(bk, now)
    assert k["events"] == 3 and k["by_tf"] == {"M15": 2, "M30": 1} and k["by_dir"] == {"BUY": 1, "SELL": 2}
    assert k["by_session"] == {"Asia": 1, "London": 1, "New York": 1}
    assert (k["confirmed"], k["failed_before"], k["failed_after"], k["retest_held"]) == (2, 1, 1, 1)
    assert k["phone"] == {"LATE": 1, "SENT": 2, "SITE": 1}


def test_events_before_the_first_run_are_never_recorded(only_swings):
    rows = swing_rows()
    brk(rows)
    st = {}
    B.scan(st, {"15m": payload(rows[:60], "15m", 900)}, T0 + 60 * 900 + 300, 650.0)
    assert st["brk"]["events"] == {}


def test_the_short_messages():
    ev = {"dir": -1, "ref": 3738.71, "ref_kind": "SWL"}
    fmt = lambda x: f"{x + 1.5:.2f}"                                   # noqa: E731 - an MT5 offset of +1.50
    clock = lambda t: "05:00 MT5 / 08:00 PKT"                          # noqa: E731
    bar = {"c": 3735.31, "t_close": 0, "how": "ACCEPTED"}
    assert B.message(ev, "15m", "DETECTED", bar, fmt, clock) == [
        "🔴 GOLD M15 BREAKOUT", "Direction: SELL", "Level: 3740.21 (swing low)", "Price: 3736.81", "Status: Monitoring",
        "Entry: Not confirmed", "Time: 05:00 MT5 / 08:00 PKT"]
    assert B.message(ev, "30m", "CONFIRMED", bar, fmt, clock)[:6] == [
        "🔴 GOLD M30 CONFIRMED", "Direction: SELL", "Level: 3740.21 (swing low)", "Price: 3736.81",
        "Status: Accepted, retest pending", "Action: Wait"]
    assert B.message(ev, "15m", "RETEST", bar, fmt, clock)[4] == "Status: Retest held"
    assert B.message({**ev, "dir": 1}, "15m", "DETECTED", bar, fmt, clock)[0] == "🟢 GOLD M15 BREAKOUT"
    assert B.message(ev, "15m", "FAILED", bar, fmt, clock) == [
        "⚠️ GOLD M15 FAILED", "Direction: SELL", "Level: 3740.21 (swing low)", "Reason: Price closed back above the level",
        "Action: Cancel setup", "Time: 05:00 MT5 / 08:00 PKT"]
    allt = " ".join(" ".join(B.message(ev, "15m", s, bar, fmt, clock)) for s in ("DETECTED", "CONFIRMED", "RETEST", "FAILED"))
    assert "%" not in allt and "probab" not in allt.lower() and "ENTRY READY" not in allt


# ---------------- amendment A2: H1 / H4 ----------------
def test_the_monitored_timeframes_and_their_switch(monkeypatch):
    assert B.TFS == {"15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}
    assert B.TF_LABEL == {"15m": "M15", "30m": "M30", "1h": "H1", "4h": "H4"} and B.W7_TFS == ("15m", "30m")
    assert B.tfs() == ["15m", "30m", "1h", "4h"]                     # unset = all four
    for v, want in (("15m,30m", ["15m", "30m"]), (" 4H, 1h ", ["1h", "4h"]), ("1d,2h", ["15m", "30m", "1h", "4h"]),
                    ("", ["15m", "30m", "1h", "4h"])):
        monkeypatch.setenv("BREAKOUT_TFS", v)
        assert B.tfs() == want, v


def test_h1_and_h4_messages_name_their_timeframe():
    ev = {"dir": 1, "ref": 4010.0, "ref_kind": "PDH"}
    bar = {"c": 4012.0, "t_close": 0, "how": "DISPLACEMENT"}
    assert B.message(ev, "1h", "DETECTED", bar, str, str)[0] == "🟢 GOLD H1 BREAKOUT"
    assert B.message(ev, "4h", "CONFIRMED", bar, str, str)[:5] == [
        "🟢 GOLD H4 CONFIRMED", "Direction: BUY", "Level: 4010.0 (prev day high)", "Price: 4012.0",
        "Status: Displacement, retest pending"]


def _h1_case():
    rows = swing_rows()
    brk(rows)
    rows[56] = (4003.2, 4004.0, 4003.1, 4003.8)
    rows[57] = (4003.8, 4004.5, 4003.5, 4004.2)
    return rows


def test_an_h1_breakout_is_sent_fresh_within_twenty_minutes_of_its_close_and_starts_at_its_first_run(only_swings):
    rows = _h1_case()
    st = {"brk": {"since": T0 - 10 * 86400, "events": {}}}            # the W7 start, long before
    B.scan(st, {"1h": payload(rows[:50], "1h", 3600)}, T0 + 50 * 3600 + 300, 650.0)      # first H1 run: since = now
    assert st["brk"]["since_tf"] == {"1h": T0 + 50 * 3600 + 300} and st["brk"]["since"] == T0 - 10 * 86400
    due = B.scan(st, {"1h": payload(rows[:56], "1h", 3600)}, T0 + 56 * 3600 + 1100, 650.0)  # 18 min after the close
    assert [(d["stage"], d["id"]) for d in due] == [("DETECTED", f"BRK:H1:{T0 + 55 * 3600}:UP")]
    due = B.scan(st, {"1h": payload(rows[:58], "1h", 3600)}, T0 + 58 * 3600 + 1300, 650.0)  # 21 min after: LATE
    rec = st["brk"]["events"][f"BRK:H1:{T0 + 55 * 3600}:UP"]
    assert due == [] and rec["phone"]["CONFIRMED"] == "LATE" and rec["tf"] == "1h"


def test_an_h4_breakout_before_its_first_run_is_never_recorded_while_m15_keeps_the_w7_start(only_swings):
    rows = _h1_case()
    st = {"brk": {"since": T0, "events": {}}}
    B.scan(st, {"15m": payload(rows[:60], "15m", 900), "4h": payload(rows[:60], "4h", 14400)}, T0 + 60 * 14400 + 300, 650.0)
    assert st["brk"]["since_tf"] == {"15m": T0, "4h": T0 + 60 * 14400 + 300}
    assert sorted(st["brk"]["events"]) == [f"BRK:M15:{T0 + 55 * 900}:UP"]       # the same bars on H4: before its start


def test_adding_h1_and_h4_leaves_every_m15_and_m30_record_and_message_identical(monkeypatch):
    rows = walk(n=1400, seed=7)
    t_end = T0 + 1400 * 900
    def runs(value):
        if value is None:
            monkeypatch.delenv("BREAKOUT_TFS", raising=False)
        else:
            monkeypatch.setenv("BREAKOUT_TFS", value)
        st, due = {}, []
        for cut in range(1000, 1400, 4):
            t_now = T0 + cut * 900 + 115
            pay = {"15m": payload(rows[:cut], "15m", 900), "30m": payload(rows[:cut // 2], "30m", 1800, t0=T0),
                   "1h": payload(rows[:cut // 4], "1h", 3600), "4h": payload(rows[:cut // 16], "4h", 14400)}
            due += [(d["id"], d["stage"]) for d in B.scan(st, pay, t_now, 650.0)]
        return st, due
    base, d0 = runs("15m,30m")
    full, d1 = runs(None)
    w7 = lambda ev: {k: v for k, v in ev.items() if k.startswith(("BRK:M15:", "BRK:M30:"))}   # noqa: E731
    assert w7(full["brk"]["events"]) == base["brk"]["events"] and len(base["brk"]["events"]) > 10
    assert [x for x in d1 if x[0].startswith(("BRK:M15:", "BRK:M30:"))] == d0
    h = [k for k in full["brk"]["events"] if k.startswith(("BRK:H1:", "BRK:H4:"))]
    tf_of = {"H1": "1h", "H4": "4h"}
    assert h and all(full["brk"]["events"][k]["t_close"] >= full["brk"]["since_tf"][tf_of[k.split(":")[1]]]
                     for k in h)                                     # H1 / H4 recorded, none before their own start
    assert full["brk"]["since_tf"]["15m"] == full["brk"]["since"] == base["brk"]["since"] and t_end > 0


def test_more_than_five_messages_in_one_run_go_as_one():
    msgs = [[f"m{k}", "x"] for k in range(6)]
    out = B.bundle(msgs)
    assert len(out) == 1 and out[0][0] == "GOLD: 6 breakout updates in this run" and "m5" in out[0]
    assert B.bundle(msgs[:5]) == msgs[:5]


# ---------------- through notify: every other alert and record unchanged ----------------
def _scenario(store, monkeypatch, value):
    monkeypatch.setenv("ALERT_STRUCTURE", "0")
    monkeypatch.setenv("ALERT_SWEEPS", "0")                          # this test isolates the breakout stream
    if value is not None:
        monkeypatch.setenv("ALERT_BREAKOUTS", value)
    sent = []
    monkeypatch.setattr(N, "send", lambda lines: sent.append(list(lines)) or ["test"] if lines else [])
    rows = swing_rows()
    brk(rows)
    rows[56] = (4003.2, 4003.3, 4002.0, 4002.6)                     # fails at once
    reps = []
    for k in (50, 51, 56, 57):
        p15 = payload(rows[:k], "15m", 900)
        reps.append(N.run(store, {"15m": p15}, ["15m"], sent_t=T0 + k * 900 + 300))
    return sent, reps, json.load(open(os.path.join(store, N.STATE)))


def test_the_phone_gets_the_breakout_messages_and_nothing_else_changes(tmp_path, monkeypatch, only_swings):
    sent1, reps1, st1 = _scenario(str(tmp_path / "on"), monkeypatch, None)
    monkeypatch.undo()
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    sent0, reps0, st0 = _scenario(str(tmp_path / "off"), monkeypatch, "0")
    brk = [m for m in sent1 if m and m[0].startswith(("🟢 GOLD", "🔴 GOLD", "⚠️ GOLD"))]
    assert [m[0] for m in brk] == ["🟢 GOLD M15 BREAKOUT", "⚠️ GOLD M15 FAILED"]
    assert [m for m in sent1 if m not in brk] == sent0
    assert {k: v for k, v in st1.items() if k != "brk"} == {k: v for k, v in st0.items() if k != "brk"} and "brk" not in st0
    for r1, r0 in zip(reps1, reps0):
        assert {k: v for k, v in r1.items() if k not in ("breakouts", "breakout_alerts")} == \
               {k: v for k, v in r0.items() if k not in ("breakouts", "breakout_alerts")}
    ev = st1["brk"]["events"][f"BRK:M15:{T0 + 55 * 900}:UP"]
    assert ev["phone"] == {"DETECTED": "SENT", "FAILED": "SENT"} and reps1[-1]["breakouts"]["counts"]["failed_before"] == 1


def test_site_mode_sends_nothing_and_records_site(tmp_path, monkeypatch, only_swings):
    sent, reps, st = _scenario(str(tmp_path / "site"), monkeypatch, "site")
    assert not [m for m in sent if m and "GOLD M15" in m[0]]
    ev = st["brk"]["events"][f"BRK:M15:{T0 + 55 * 900}:UP"]
    assert ev["phone"] == {"DETECTED": "SITE", "FAILED": "SITE"}


def test_the_module_is_not_an_engine_source_and_sends_nothing_itself():
    assert "breakouts.py" not in holdout.ENGINE_SOURCES
    src = open(B.__file__).read()
    imports = sorted(x.strip() for x in src.splitlines() if x.startswith(("import ", "from ")))
    assert imports == ["from . import sessions, shadow, ta", "from __future__ import annotations", "import math",
                       "import numpy as np", "import os", "import pandas as pd"]
    assert "send(" not in src and "requests" not in src


def test_the_website_card_is_wired():
    js = open(os.path.join(os.path.dirname(__file__), "..", "site", "app.js")).read()
    assert js.count("function breakoutsCard(BK)") == 1 and "${breakoutsCard(A.breakouts)}" in js
    card = js[js.index("function breakoutsCard(BK)"):]
    card = card[:card.index("\nfunction ", 10)]
    assert "SHADOW" in card and "not validated" in card and "chance" not in card
