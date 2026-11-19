"""B31b-W7 (research/registrations/B31b-W7.json + amendment A1): the development study of the breakout monitor.

The independent reference detector reproduces quantum/breakouts.py exactly (random walks and level-rich bars, both
timeframes) and catches a planted defect; the registered shadow entries E0-E4 worked by hand (E3 on M5 bars); the
extension and room checks; orders rebuilt from the bars closed by their placement (no look-ahead); the controls'
window and determinism; the partition gate; the registration's constants."""
import json
import os

import numpy as np
import pandas as pd
import pytest

from quantum import breakouts as B
from quantum.research import harness as H
from quantum.research import w3liq as W
from quantum.research import w7breakout as X

FLAT = (4000.0, 4000.5, 3999.5, 4000.0)
START = "2026-03-01 22:00"                       # a Sunday 22:00 UTC: bar 0 opens a trading day


def frame_of(rows, start=START, freq="15min"):
    idx = pd.date_range(start, periods=len(rows), freq=freq, tz="UTC")
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"]).assign(volume=np.nan)


def agg(df, rule):
    return df.resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(
        subset=["open"])


def frames(rows, m5=None):
    m15 = frame_of(rows)
    P, F15, F30, _ = W.frames(m15, agg(m15, "1h"), m5)
    return P, F15, F30, int(m15.index[0].timestamp())


def walk(seed, n, vol=1.0):
    g = H.seeded_rng(seed)
    c = 4000 + np.cumsum(g.normal(0, 1.2 * vol, n))
    o = np.concatenate([[4000.0], c[:-1]])
    h = np.maximum(o, c) + g.uniform(0, 1.0 * vol, n)
    l = np.minimum(o, c) - g.uniform(0, 1.0 * vol, n)
    return list(zip(o, h, l, c))


def level_rich(n=1400, seed=9):
    """Quiet 40-bar boxes (ranges, equal highs / lows) alternating with 40-bar drifts (swings, session and day breaks)."""
    g = H.seeded_rng(seed)
    rows, px = [], 4000.0
    for k in range(n):
        quiet = (k // 40) % 2 == 0
        step = g.normal(0, 0.08) if quiet else g.normal(0.25 * (1 if (k // 80) % 2 else -1), 1.0)
        o, c = px, px + step
        w = 0.15 if quiet else 0.8
        rows.append((o, max(o, c) + abs(g.normal(0, w)), min(o, c) - abs(g.normal(0, w)), c))
        px = c
    return rows


# ---------------- (a) the reference detector ----------------
@pytest.mark.parametrize("rows", [walk(21, 2500), walk(22, 2500), walk(23, 2500, vol=6.0), level_rich()],
                         ids=["walk21", "walk22", "walk23_atr_over_5", "level_rich"])
def test_the_reference_detector_reproduces_production_exactly(rows):
    P, F15, F30, _ = frames(rows)
    for F in (F15, F30):
        r = X.detection_check(F)
        assert r["identical"], r
        assert r["events_production"] == r["events_reference"] > 20


def test_equal_levels_wider_than_fifty_cents_appear_when_atr_is_over_five_dollars():
    P, F15, _, _ = frames(walk(23, 2500, vol=6.0))
    evs, ctx = B.detect(F15.t, F15.o, F15.h, F15.l, F15.c, 900)
    eq = [e for e in evs if any(x["kind"][:2] == "EQ" for x in e["levels"])]
    assert eq and np.nanmedian(ctx["atr"]) > 5.0                     # the 0.10 x ATR tolerance is the binding one here


def test_both_detectors_ignore_a_level_born_with_price_already_beyond_it(monkeypatch):
    rows = [FLAT] * 300
    rows[200] = (4000.0, 4000.2, 3998.0, 3998.5)                    # back under the 3999.0 level ...
    rows[201] = (3998.5, 4000.2, 3998.4, 4000.0)                    # ... and above it again: the only PDH breakout
    def pools(h, l, cal, eqh, eql):
        n = len(h)
        out = {k: np.full(n, np.nan) for s in B.STATIC for k in B.STATIC[s]}
        out["PDH"] = np.full(n, 3999.0)
        return out, None
    monkeypatch.setattr(X.shadow, "build_pools", pools)
    P, F15, _, _ = frames(rows)
    assert [e["i"] for e in X.ref_detect(F15.t, F15.o, F15.h, F15.l, F15.c, 900) if e["ref_kind"] == "PDH"] == [201]
    assert X.detection_check(F15)["identical"]


def test_the_level_rich_bars_exercise_every_kind_of_level():
    P, F15, F30, _ = frames(level_rich())
    kinds = {x["kind"][:2] for F in (F15, F30) for e in B.detect(F.t, F.o, F.h, F.l, F.c, F.sec)[0] for x in e["levels"]}
    assert {"RG", "SW", "EQ", "AS", "PD"} <= kinds
    st = [B.follow(e, F15.o, F15.h, F15.l, F15.c) for e in B.detect(F15.t, F15.o, F15.h, F15.l, F15.c, 900)[0]]
    assert any(s["how"] == "ACCEPTED" for s in st) and any(s["retest"] is not None for s in st)
    assert any(s["failed"] is not None for s in st) and any(s["closed"] is not None for s in st)


@pytest.mark.parametrize("attr, value", [("RANGE_ATR", 1.0), ("DISP_ATR", 0.8), ("WATCH", 12), ("SWING_DAYS", 4)])
def test_the_check_catches_a_planted_defect(monkeypatch, attr, value):
    P, F15, _, _ = frames(level_rich())
    monkeypatch.setattr(B, attr, value)
    assert not X.detection_check(F15)["identical"]


# ---------------- the registered shadow entries ----------------
def breakout_rows(disp=False):
    """Flat 4000 +/- 0.5 with a swing high 4003.0 at bar 140; bar 154 closes 4002.6; bar 155 closes above 4003.0 (a
    0.6 body, or a displacement bar), 156 and 157 stay above (ACCEPTED at 157); then flat above."""
    rows = [FLAT] * 140 + [(4000.0, 4003.0, 3999.5, 4000.0)] + [FLAT] * 13
    rows += [(4000.0, 4002.8, 3999.9, 4002.6)]
    rows += [(3999.6, 4006.0, 3999.5, 4005.8)] if disp else [(4002.6, 4003.6, 4002.4, 4003.2)]
    rows += [(4003.2, 4004.0, 4003.1, 4003.8), (4003.8, 4004.5, 4003.5, 4004.2)]
    rows += [(4004.2, 4004.6, 4003.9, 4004.3)] * 60
    return rows


def the_event(F, sf, i=155):
    evs = [e for e in X.events(F, sf) if e["i"] == i and e["dir"] == 1 and e["ref"] == 4003.0]
    assert len(evs) == 1
    return evs[0]


def test_entries_worked_by_hand():
    P, F, _, sf = frames(breakout_rows())
    ev = the_event(F, sf)
    assert ev["st"]["confirmed"] == 157 and not ev["disp"]
    buf = 0.2 * ev["atr"]
    od = {o["m"]: o for o in X.orders_for(P, F, ev)}
    assert set(od) == {"E0", "E1", "E2"}                                       # no M5 bars: no E3; no displacement: no E4
    assert od["E0"]["px"] == 4003.2 and od["E0"]["stop"] == pytest.approx(4002.4 - buf) and od["E0"]["t"] == int(F.t[155]) + 900
    assert od["E1"]["px"] == 4004.2 and od["E1"]["stop"] == pytest.approx(4002.4 - buf) and od["E1"]["t"] == int(F.t[157]) + 900
    assert od["E2"]["kind"] == "LIM" and od["E2"]["px"] == 4003.0 and od["E2"]["valid"] == 157 + 8
    assert od["E2"]["stop"] == od["E1"]["stop"] and "cancel_back" not in od["E2"]                 # A1: no cancel clause


def test_a_displacement_breakout_adds_e4_at_the_middle_of_its_body():
    P, F, _, sf = frames(breakout_rows(disp=True))
    ev = the_event(F, sf)
    assert ev["disp"] and ev["st"]["confirmed"] == 155
    od = {o["m"]: o for o in X.orders_for(P, F, ev)}
    assert od["E4"]["px"] == pytest.approx((3999.6 + 4005.8) / 2) and od["E4"]["valid"] == 155 + 4
    assert od["E4"]["stop"] == pytest.approx(3999.5 - 0.2 * ev["atr"]) and od["E1"]["t"] == od["E0"]["t"]


def m5_of(rows15, override):
    """Three flat M5 bars per 15m bar (the 15m bar's close), with `override` {m5 index: (o, h, l, c)}."""
    out = []
    for o, h, l, c in rows15:
        out += [(c, c + 0.05, c - 0.05, c)] * 3
    for k, v in override.items():
        out[k] = v
    return frame_of(out, freq="5min")


def test_e3_is_the_first_m5_close_beyond_a_pullback_bar_after_the_confirmation():
    rows = breakout_rows()
    a = 158 * 3                                                       # the first M5 bar after the confirmation close
    m5 = m5_of(rows, {a: (4004.2, 4004.9, 4004.1, 4004.6), a + 1: (4004.6, 4004.7, 4002.0, 4003.9),   # a+1: lower high
                      a + 2: (4003.9, 4005.2, 4003.8, 4005.0)})                                         # closes > 4004.7
    P, F, _, sf = frames(rows, m5)
    ev = the_event(F, sf)
    od = {o["m"]: o for o in X.orders_for(P, F, ev)}
    e3 = od["E3"]
    assert e3["px"] == 4005.0 and e3["t"] == int(m5.index[a + 2].timestamp()) + 300 and e3["kind"] == "MKT"
    assert e3["stop"] == pytest.approx(4002.0 - 0.2 * ev["atr"])     # the M5 low 4002.0 is below bars 155-157's 4002.4


def test_no_e3_without_a_pullback_or_a_close_beyond_the_pullback_bar():
    rows = breakout_rows()
    P, F, _, sf = frames(rows, m5_of(rows, {}))                       # flat M5: no lower high, no close beyond
    assert "E3" not in {o["m"] for o in X.orders_for(P, F, the_event(F, sf))}
    a = 158 * 3
    m5 = m5_of(rows, {a: (4004.2, 4004.9, 4004.1, 4004.6), a + 1: (4004.6, 4004.7, 4003.7, 4003.9),
                      a + 2: (4003.9, 4004.6, 4003.8, 4004.5)})       # a lower high, then a close under its high
    P, F, _, sf = frames(rows, m5)
    assert "E3" not in {o["m"] for o in X.orders_for(P, F, the_event(F, sf))}


def test_extension_and_room_checks():
    ev = {"dir": 1, "ref": 4003.0, "atr": 1.0, "beyond": [4008.0, 4030.0]}
    assert X.checks({"e": 4004.5, "s": 1.0}, ev) == ["extension", "room"]          # 1.5 beyond; 4008 is $3.50 ahead
    assert X.checks({"e": 4003.5, "s": 1.0}, {**ev, "beyond": [4014.0]}) == []
    assert X.checks({"e": 3995.0, "s": 1.0}, {**ev, "dir": -1, "ref": 3996.0, "beyond": [3990.0]}) == ["room"]


def test_orders_are_rebuilt_from_the_bars_closed_by_their_placement():
    rows = breakout_rows()
    P, F, _, sf = frames(rows)
    full = {o["m"]: o for o in X.orders_for(P, F, the_event(F, sf))}
    for m, cut in (("E0", 155), ("E1", 157), ("E2", 157)):
        P2, F2, _, _ = frames(rows[:cut + 1])
        part = {o["m"]: o for o in X.orders_for(P2, F2, the_event(F2, sf))}
        assert {k: v for k, v in part[m].items() if k != "valid"} == {k: v for k, v in full[m].items() if k != "valid"}


def test_only_entry_ready_fills_are_counted_one_position_at_a_time():
    base = {"m": "E1", "tf": "M15", "status": "FILLED", "eligible": True, "ready": True, "why": None, "checks": []}
    rows = [dict(base, ev_id="a", t_fill=1000, tp10_exit=5000.0), dict(base, ev_id="b", t_fill=2000, tp10_exit=3000.0),
            dict(base, ev_id="c", t_fill=6000, tp10_exit=7000.0, ready=False, checks=["room"]),
            dict(base, ev_id="d", t_fill=8000, tp10_exit=9000.0, eligible=False, ready=False, why="cost"),
            dict(base, ev_id="e", status="MISSED", why="limit not filled in time", t_fill=None),
            dict(base, ev_id="f", t_fill=9500, tp10_exit=9900.0, tf="M30")]
    assert [r["ev_id"] for r in X.counted(rows, "E1", "M15")] == ["a"]          # b overlaps a; c, d not ready; f is M30
    assert X.funnel(rows, "E1", "M15") == {"orders": 5, "MISSED:limit not filled in time": 1, "NOT_READY:cost": 1,
                                           "NOT_READY:room": 1, "READY": 2}


# ---------------- controls, gate, registration ----------------
def test_controls_are_deterministic_and_inside_the_watch_window():
    rows = breakout_rows() + [FLAT] * 120
    P, F, F30, sf = frames(rows)
    ev = the_event(F, sf)
    r = W.execute(P, F, [o for o in X.orders_for(P, F, ev) if o["m"] == "E1"][0])
    r.update(m="E1", tf="M15", ev_id=ev["id"])
    a = X.controls(P, {"M15": F, "M30": F30}, [r], {ev["id"]: ev})
    b = X.controls(P, {"M15": F, "M30": F30}, [r], {ev["id"]: ev})
    assert a[id(r)]["r1"] == b[id(r)]["r1"] and sum(a[id(r)]["r1"]["tp10"]) > 0
    assert a[id(r)]["r2"]["tp10"] in ("TP", "SL", "AMBIGUOUS", "TIMEOUT", "OPEN", "NODATA")


def test_only_the_development_partition_runs():
    for part in ("validation", "holdout", "recent"):
        with pytest.raises(H.SealedPartition):
            X.main(["--part", part, "--rd", "nowhere", "--out", "nowhere.json"])


def test_the_registration_fixes_what_the_study_runs():
    reg = json.load(open(os.path.join(os.path.dirname(__file__), "..", "research", "registrations", "B31b-W7.json")))
    v = reg["shadow_entry_ready"]["variants"]
    assert set(v) == set(X.VARIANTS) and "valid 8 bars" in v["E2"] and "within 4 bars" in v["E3"] and "valid 4 bars" in v["E4"]
    assert (X.E3_BARS, X.E4_BARS, B.RETEST_VALID, X.K_RAND) == (4, 4, 8, 20)
    assert "20 market entries" in reg["study"]["controls"] and "Holm" in reg["study"]["test"]
    assert [a["id"] for a in reg["amendments"]] == ["A1"] and "e2_cancel_clause" in reg["amendments"][0]["changes"]
