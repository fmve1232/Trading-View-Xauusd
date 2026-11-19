"""Workstream 4 key zones (quantum/keyzones.py) and their wiring: reproducible zones, visit states, structure, the
non-directional zone watch (once per visit, re-armed, capped, fresh bars only, switchable), and the engine untouched."""
import os

import numpy as np
import pytest

from quantum import holdout, notify
from quantum import keyzones as K

T0 = 1794000000 - (1794000000 % 900)          # a 15m boundary (Nov 2026)


def payload(tf, rows, sec=900, t0=T0):
    t = [t0 + k * sec for k in range(len(rows))]
    o, h, l, c = (list(x) for x in zip(*rows))
    return {"meta": {"tf": tf, "tf_sec": sec, "synthetic": False, "generated_utc": "2026-11-18T21:00:00+00:00",
                     "price_source": "twelvedata:XAU/USD", "forming": None},
            "chart": {"t": t, "o": o, "h": h, "l": l, "c": c}, "markers": [], "news": None}


def flat(n, px=4000.0, r=1.0):
    return [(px, px + r / 2, px - r / 2, px)] * n


def with_swing_high(n_before=150, n_after=20, peak=4012.0):
    """Flat at 4000 (range $1) then one bar spiking to `peak` with its body top at 4003, then flat again."""
    return flat(n_before) + [(4000.0, peak, 3999.5, 4003.0)] + flat(n_after)


def test_a_swing_high_becomes_a_zone_from_its_wick_with_width_limits():
    rows = with_swing_high()
    b = K.bars(payload("15m", rows))
    a = K.atr14(b)
    src = [s for s in K.swing_sources(b, "15m", 900, a) if s["kind"] == "SWH" and s["price"] == 4012.0]
    assert len(src) == 1
    z = src[0]
    assert z["hi"] == 4012.0 and z["lo"] == pytest.approx(max(4003.0, 4012.0 - K.MAX_W * a))   # wick 4003..4012, capped
    assert z["t_known"] == T0 + (150 + K.PIVOT) * 900 + 900                                  # known at the 3rd bar's close


def test_a_pivot_is_not_a_zone_before_its_confirmation_bar_closes():
    rows = with_swing_high(n_after=2)                        # only two bars after the peak: not yet a pivot
    b = K.bars(payload("15m", rows))
    assert not [s for s in K.swing_sources(b, "15m", 900, K.atr14(b)) if s["price"] == 4012.0]


def test_visit_states_fresh_tested_weakened_broken_invalidated():
    z = {"lo": 4005.0, "hi": 4007.0, "mid": 4006.0, "t_known": T0}
    def st(closes):
        rows = [(c, max(c, 4000.0) + 0.5, min(c, 4000.0) - 0.5, c) for c in closes]
        rows = [(4000.0, 4000.5, 3999.5, 4000.0)] + rows
        return K.visits(z, K.bars(payload("15m", rows, t0=T0 - 900)))
    assert st([4000.0, 4001.0])["state"] == "FRESH"
    v = st([4000.0, 4006.0, 4003.0])                       # into the zone, back below: rejected once
    assert v["state"] == "TESTED" and v["touches"] == 1 and v["rejections"] == 1
    assert st([4006.0, 4003.0, 4006.5, 4002.0])["state"] == "WEAKENED"
    v = st([4006.0, 4009.0])                               # into it, then a close above: accepted, now support
    assert v["state"] == "BROKEN" and v["acceptances"] == 1 and v["side_now"] == 1
    assert st([4006.0, 4009.0, 4006.0, 4001.0])["state"] == "INVALIDATED"


def test_zones_are_sorted_non_overlapping_and_distances_and_room_are_consistent():
    rows = flat(100) + [(4000, 4012, 3999.5, 4003)] + flat(10) + [(4000, 4000.5, 3988, 3997)] + flat(40)
    p = {"15m": payload("15m", rows)}
    zb = K.build(p, T0 + len(rows) * 900 + 60)
    assert zb["ok"]
    up, dn = zb["above"], zb["below"]
    for seq in (up, dn):
        for a, b in zip(seq, seq[1:]):
            assert a["hi"] <= b["lo"] or b["hi"] <= a["lo"]           # no overlap
    px = zb["price"]["px"]
    for z in up:
        assert z["lo"] > px and z["distance"] == pytest.approx(z["lo"] - px, abs=0.01)
    for z in dn:
        assert z["hi"] < px and z["distance"] == pytest.approx(px - z["hi"], abs=0.01)
    assert zb["room_up"] == pytest.approx(up[0]["lo"] - px, abs=0.01) and zb["room_down"] == pytest.approx(px - dn[0]["hi"], abs=0.01)
    assert "no entry method has a validated edge" in zb["directional"]


def test_a_cluster_nested_in_another_is_merged_not_cut_to_a_sliver_and_no_zone_is_narrower_than_the_minimum():
    a = 10.0
    src = lambda k, p, lo, hi: {"kind": "SWH", "tf": "30m", "price": p, "lo": lo, "hi": hi, "t_known": T0 + k, "t_pivot": None}  # noqa: E731
    zs = K._resolve([{"lo": 4000.0, "hi": 4009.0, "sources": [src(0, 4009.0, 4000.0, 4009.0)]},
                     {"lo": 4007.0, "hi": 4008.0, "sources": [src(1, 4008.0, 4007.0, 4008.0)]}], a)
    assert len(zs) == 1 and (zs[0]["lo"], zs[0]["hi"]) == (4000.0, 4009.0) and len(zs[0]["sources"]) == 2
    zs = K._resolve([{"lo": 4000.0, "hi": 4006.0, "sources": [src(0, 4006.0, 4000.0, 4006.0)]},
                     {"lo": 4004.0, "hi": 4012.0, "sources": [src(1, 4012.0, 4004.0, 4012.0)]}], a)
    assert [(z["lo"], z["hi"]) for z in zs] == [(4000.0, 4005.0), (4005.0, 4012.0)]           # a clean split
    zs = K._resolve([{"lo": 0.0, "hi": 10.0, "sources": [src(0, 10.0, 0.0, 10.0)]},          # a merge in pass 1 makes a
                     {"lo": 5.0, "hi": 20.0, "sources": [src(1, 20.0, 5.0, 20.0)]},          # new overlap that pass 2
                     {"lo": 6.0, "hi": 7.0, "sources": [src(2, 7.0, 6.0, 7.0)]}], 1.0)        # splits cleanly
    assert [(z["lo"], z["hi"], len(z["sources"])) for z in zs] == [(0.0, 6.75, 1), (6.75, 20.0, 2)]
    rng = np.random.default_rng(11)
    for _ in range(200):                                     # random overlapping clusters: never overlapping, never slivers
        zz = []
        for k in range(12):
            lo = 4000 + rng.uniform(0, 60)
            hi = lo + rng.uniform(K.MIN_W * a, 3 * a)
            zz.append({"lo": lo, "hi": hi, "sources": [src(k, hi, lo, hi)]})
        out = K._resolve(zz, a)
        assert sum(len(z["sources"]) for z in out) == 12
        for x, y in zip(out, out[1:]):
            assert x["hi"] <= y["lo"] + 1e-9
        assert all(z["hi"] - z["lo"] >= K.MIN_W * a - 1e-9 for z in out)


def test_structure_reads_lower_highs_and_lower_lows_as_bearish_with_a_bear_ema_stack():
    rows = []
    px = 4100.0
    for k in range(12):                                     # a staircase down: rallies of $4, drops of $10
        for _ in range(6):
            px -= 10 / 6
            rows.append((px + 0.8, px + 1.0, px - 1.0, px))
        for _ in range(6):
            px += 4 / 6
            rows.append((px - 0.8, px + 1.0, px - 1.0, px))
    s = K.structure(payload("30m", rows, sec=1800), "30m")
    assert s["pattern"] == "LH/LL" and s["stack"] == "bear" and s["bias"] == "bearish"


def test_watch_once_per_visit_rearms_after_moving_away_and_marks_late_bars():
    rows = with_swing_high(n_after=10)
    p = {"15m": payload("15m", rows)}
    st = {}
    t_end = T0 + len(rows) * 900
    zb = K.build(p, t_end + 60)
    z = zb["above"][0]
    z["significant"] = z["key"] = True
    zb["above"], zb["below"], zb["at"] = [z], [], []             # this one zone only
    # a bar that trades into the zone
    rows2 = rows + [(4000.0, z["lo"] + 0.1, 3999.5, 4000.2)]
    b2 = K.bars(payload("15m", rows2))
    ev = K.watch(st, zb, b2, int(b2["t"][-1]) + 900 + 60)
    assert [e["kind"] for e in ev] == ["AT ZONE"] and ev[0]["fresh"]
    assert K.watch(st, zb, b2, int(b2["t"][-1]) + 900 + 60) == []                    # the same bar: nothing again
    rows3 = rows2 + [(4000.0, z["lo"] + 0.1, 3999.5, 4000.2)]
    assert K.watch(st, zb, K.bars(payload("15m", rows3)), int(rows3 and T0 + len(rows3) * 900 + 60)) == []   # not re-armed
    far = z["lo"] - (K.WATCH_REARM_ATR + 1) * zb["atr15"]
    rows4 = rows3 + [(far, far + 0.3, far - 0.3, far)]
    K.watch(st, zb, K.bars(payload("15m", rows4)), T0 + len(rows4) * 900 + 60)       # far away: re-armed
    rows5 = rows4 + [(4000.0, z["lo"] + 0.1, 3999.5, 4000.2)]
    late = K.watch(st, zb, K.bars(payload("15m", rows5)), T0 + len(rows5) * 900 + 2 * 3600)
    assert [e["kind"] for e in late] == ["AT ZONE"] and not late[0]["fresh"]          # 2 h late: recorded, not fresh


def _one_zone(z, a=1.0):
    return {"ok": True, "atr15": a, "above": [z], "below": [], "at": []}


def _b(rows):
    return K.bars(payload("15m", rows))


def test_watch_dedupes_by_price_band_so_a_zone_whose_id_changes_is_not_messaged_twice():
    z = {"id": "SWH-30m-1", "lo": 4005.0, "hi": 4007.0, "mid": 4006.0, "width": 2.0, "state": "FRESH", "key": True,
         "last_acc_t": None}
    st = {}
    rows = flat(20) + [(4000.0, 4005.5, 3999.5, 4003.0)]                 # trades into the zone
    assert [e["kind"] for e in K.watch(st, _one_zone(z), _b(rows), T0 + len(rows) * 900 + 60)] == ["AT ZONE"]
    z2 = dict(z, id="PDH-15m-2", lo=4004.8)                              # a new day's level joined the cluster: new id
    rows += [(4003.0, 4005.2, 4002.5, 4003.5)]
    assert K.watch(st, _one_zone(z2), _b(rows), T0 + len(rows) * 900 + 60) == []
    rows += [(3990.0, 3990.3, 3989.7, 3990.0)]                          # $14.8 away (> 1.5 ATR): the band re-arms
    assert K.watch(st, _one_zone(z2), _b(rows), T0 + len(rows) * 900 + 60) == []
    rows += [(4003.0, 4005.2, 4002.5, 4003.5)]
    assert [e["kind"] for e in K.watch(st, _one_zone(z2), _b(rows), T0 + len(rows) * 900 + 60)] == ["AT ZONE"]


def test_broken_fires_only_on_the_accepting_bar_and_is_not_silenced_by_the_approach_message():
    z = {"id": "SWH-30m-1", "lo": 4005.0, "hi": 4007.0, "mid": 4006.0, "width": 2.0, "state": "FRESH", "key": True,
         "last_acc_t": None}
    st = {}
    rows = flat(20) + [(4000.0, 4005.5, 3999.5, 4004.0)]
    assert [e["kind"] for e in K.watch(st, _one_zone(z), _b(rows), T0 + len(rows) * 900 + 60)] == ["AT ZONE"]
    rows += [(4004.0, 4009.5, 4003.8, 4009.0)]                          # this bar's close accepts it
    zb = dict(z, state="BROKEN", last_acc_t=T0 + (len(rows) - 1) * 900)
    assert [e["kind"] for e in K.watch(st, _one_zone(zb), _b(rows), T0 + len(rows) * 900 + 60)] == ["BROKEN"]
    rows += [(4009.0, 4009.5, 4006.5, 4008.0)]                          # the next bar retests it: the same band, quiet
    assert K.watch(st, _one_zone(zb), _b(rows), T0 + len(rows) * 900 + 60) == []
    # the real visit bookkeeping marks the accepting bar
    v = K.visits(dict(z, t_known=T0), _b(rows))
    assert v["state"] == "BROKEN" and v["last_acc_t"] == T0 + (len(rows) - 2) * 900


def test_a_visit_in_progress_is_said_as_such():
    zb = {"price": {"px": 4006.0, "source": "x"}, "room_up": None, "room_down": None, "context": {"bearish": [], "bullish": []}}
    z = {"lo": 4005.0, "hi": 4007.0, "label": "30m swing high", "state": "FRESH", "touches": 1, "inside": True,
         "width_atr": 0.5, "role": "price inside", "room_beyond": None}
    lines = K.watch_lines([{"kind": "AT ZONE", "zone": z, "bar_t": T0}], zb, lambda x: f"{x:.2f}", lambda t: "t")
    assert "fresh, visit 1 in progress" in lines[1] and "PRICE INSIDE ZONE" in lines[1]


def test_watch_lines_are_non_directional_and_say_no_trade():
    zb = {"price": {"px": 3729.54, "source": "Twelve Data mid"}, "room_up": 11.5, "room_down": 7.0,
          "context": {"bearish": ["30m", "1h"], "bullish": []}}
    z = {"lo": 3741.0, "hi": 3744.0, "label": "30m swing high", "state": "FRESH", "touches": 1, "width_atr": 0.5,
         "role": "resistance", "room_beyond": 12.0}
    lines = K.watch_lines([{"kind": "AT ZONE", "zone": z, "bar_t": T0}], zb, lambda x: f"{x:.2f}", lambda t: "21:00 UTC")
    text = " ".join(lines)
    assert lines[0].startswith("XAUUSD KEY ZONE WATCH") and "MONITORING ONLY, NOT AN ENTRY" in lines[0]
    assert "NO TRADE" in lines[-1] and "DISABLED" in lines[-1]
    for word in ("BUY", "SELL", "probability", "%"):
        assert word not in text


def _full(n=400):
    rng = np.random.default_rng(3)
    c = 4000 + np.cumsum(rng.normal(0, 1.2, n))
    o = np.concatenate([[4000.0], c[:-1]])
    rows = [(float(a), float(max(a, b) + 0.6), float(min(a, b) - 0.6), float(b)) for a, b in zip(o, c)]
    return rows


@pytest.mark.parametrize("mode,expect_sent", [("", True), ("site", False), ("0", False)])
def test_notify_sends_zone_watch_by_mode_with_a_daily_cap(tmp_path, monkeypatch, mode, expect_sent):
    monkeypatch.setenv("ALERT_ZONES", mode)
    rows = _full()
    p15 = payload("15m", rows)
    t_send = T0 + len(rows) * 900 + 120
    st = {}
    zb, lines, ids = notify.zones_run(st, {"15m": p15}, t_send, 0.0)
    assert zb["ok"] and zb["watch"]["mode"] == ("phone" if mode == "" else "site" if mode == "site" else "off")
    if not expect_sent:
        assert lines == [] and ids == []
    st["zone_watch"]["n"] = K.WATCH_DAY_CAP                 # the cap is reached: nothing more today
    st["zone_watch"]["last_bar"] = None
    _, lines2, _ = notify.zones_run(st, {"15m": p15}, t_send, 0.0)
    assert lines2 == []


def test_notify_run_reports_zones_and_never_fails_on_a_partial_payload(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send", lambda lines: sent.append(lines) or ["test"])
    part = {"meta": {"tf": "15m", "synthetic": False, "generated_utc": "2026-11-02T10:00:00+00:00"}, "markers": [],
            "decisions": [], "news": None, "chart": {"t": [1000], "h": [None], "l": [None]}}
    rep = notify.run(str(tmp_path), {"15m": part}, ["15m"])
    assert rep["zones"]["ok"] is False                      # no OHLC: reported, nothing sent, no exception


def test_the_engine_and_its_freeze_key_do_not_include_the_monitoring_code():
    for f in ("keyzones.py", "notify.py", "confirm_entry.py"):
        assert f not in holdout.ENGINE_SOURCES
    with open(os.path.join(os.path.dirname(K.__file__), "pipeline.py")) as fh:
        src = fh.read()
    assert "keyzones" not in src


def test_the_website_shows_zones_as_monitoring_and_the_gap_risk_row():
    with open(os.path.join(os.path.dirname(K.__file__), "..", "site", "app.js")) as fh:
        js = fh.read()
    assert "function zonesCard(Z)" in js and "Key zones · monitoring only, not an entry" in js
    assert "${zonesCard(A.zones)}" in js and "Directional entries" in js and "<div>Gap risk</div>" in js
    assert "only the broker's is executable" in js.lower() or "Only the broker's is executable" in js


def test_workflow_passes_the_zone_switch_to_the_pipeline():
    with open(os.path.join(os.path.dirname(K.__file__), "..", ".github", "workflows", "quantum-site.yml")) as fh:
        wf = fh.read()
    assert "ALERT_ZONES: ${{ vars.ALERT_ZONES }}" in wf
