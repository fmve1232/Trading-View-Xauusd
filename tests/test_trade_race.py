""""Your trade" panel (quantum/trade_race.py, display only): first-passage counts checked by hand, against a
bar-by-bar reference on random walks, the window / data-hole exclusions, the forward-ledger reader, and the payload."""
import json
import os

import numpy as np
import pytest

from quantum import engine, holdout, report
from quantum import trade_race as tr
from quantum.config import DEFAULT
from quantum.data.market import load_synthetic

TP, SL = tr.TP_GRID, tr.SL_GRID
T0 = 1_760_000_100 - (1_760_000_100 % 300)


def _path(o, h, l, c, H=4, t=None):
    n = len(c)
    t = T0 + 300 * np.arange(n, dtype=np.int64) if t is None else np.asarray(t, np.int64)
    return {"t": t, "o": np.asarray(o, float), "h": np.asarray(h, float), "l": np.asarray(l, float), "c": np.asarray(c, float), "H": H}


def _cell(r, a, b):
    i, j = TP.index(a), SL.index(b)
    return r["win"][i][j], r["loss"][i][j], r["mark"][i][j]


def test_display_only_and_outside_every_key():
    assert "trade_race.py" not in holdout.ENGINE_SOURCES
    assert "report.py" not in holdout.ENGINE_SOURCES
    assert list(TP) == sorted(TP) and list(SL) == sorted(SL)
    for a, b in ((2.0, 10.0), (10.0, 10.0), (20.0, 10.0)):        # the operator's trades are measured exactly
        assert a in TP and b in SL


def test_hand_built_long_and_short_paths():
    # long at 100: best +2.5 on bar 0, then -5 on bar 1, -15 on bar 2; closes the day at 86
    P = _path(o=[100, 102, 96, 86], h=[102.5, 102, 96, 87], l=[99.5, 95, 85, 85], c=[102, 96, 86, 86])
    r = tr.race(P, [T0], [100.0], [1])
    assert r["n"] == 1 and r["long"] == 1 and r["short"] == 0
    assert _cell(r, 2.0, 10.0)[:2] == (1, 0)          # +2 reached on bar 0, -10 only on bar 2
    assert _cell(r, 3.0, 10.0)[:2] == (0, 1)          # +3 never reached
    assert _cell(r, 2.0, 2.0)[:2] == (1, 0)           # +2 on bar 0 before -2 on bar 1
    w, l_, m = _cell(r, 50.0, 100.0)
    assert (w, l_, m) == (0, 0, -14.0)                # OPEN: marked at the horizon close, 86 - 100
    s = tr.race(P, [T0], [100.0], [-1])               # the same path, short
    assert _cell(s, 5.0, 3.0)[:2] == (1, 0)           # -5 below on bar 1, never 3 above
    assert _cell(s, 2.0, 2.0)[:2] == (0, 1)           # 2.5 above on bar 0 first
    assert _cell(s, 50.0, 100.0)[2] == 14.0


@pytest.mark.parametrize("o, expect", [(100.0, (0, 1)), (103.0, (1, 0)), (88.0, (0, 1))])
def test_a_bar_touching_both_is_a_loss_unless_it_opened_beyond_the_target(o, expect):
    P = _path(o=[o, 95, 95, 95], h=[104, 96, 96, 96], l=[87, 94, 94, 94], c=[95, 95, 95, 95])
    assert _cell(tr.race(P, [T0], [100.0], [1]), 2.0, 10.0)[:2] == expect


def test_window_horizon_and_data_hole_exclusions():
    n = 10
    t = list(T0 + 300 * np.arange(5)) + list(T0 + 300 * 4 + 4 * 86400 + 300 * np.arange(1, 6))   # a 4-day hole
    P = _path(o=[100] * n, h=[101] * n, l=[99] * n, c=[100] * n, H=3, t=t)
    trig = [T0 - 300,          # before the window
            T0,                # counted
            T0 + 300 * 3,      # counted: its next bar is stored; the horizon is counted in stored bars
            T0 + 300 * 5,      # inside the hole: the next stored bar is 4 days away
            int(t[-1])]        # the horizon runs past the end
    r = tr.race(P, trig, [100.0] * 5, [1] * 5)
    assert r["n"] == 2
    assert tr.race(P, [], [], [])["n"] == 0


def _reference(P, tc, p, d, a, b):
    """Bar by bar: the first bar that reaches the target or the stop decides; both on one bar = loss unless it opened
    beyond the target."""
    t, H = P["t"], P["H"]
    j = int(np.searchsorted(t, tc))
    if tc < t[0] or j + H > len(t) or t[j] - tc > tr.MAX_WAIT_SEC:
        return None
    for k in range(j, j + H):
        fav = (P["h"][k] - p) if d > 0 else (p - P["l"][k])
        adv = (p - P["l"][k]) if d > 0 else (P["h"][k] - p)
        if fav >= a and adv >= b:
            return ("W", 0.0) if (P["o"][k] - p) * d >= a else ("L", 0.0)
        if fav >= a:
            return ("W", 0.0)
        if adv >= b:
            return ("L", 0.0)
    return ("O", (P["c"][j + H - 1] - p) * d)


def test_matches_a_bar_by_bar_reference_on_random_walks(monkeypatch):
    monkeypatch.setattr(tr, "CHUNK", 37)                         # exercise the block boundaries
    g = np.random.default_rng(11)
    n = 2500
    c = 2000 + np.cumsum(g.normal(0, 1.2, n))
    o = np.r_[2000.0, c[:-1]] + g.normal(0, 0.3, n) * (g.random(n) < 0.05) * 10    # occasional gaps
    h = np.maximum(o, c) + np.abs(g.normal(0, 0.8, n))
    l = np.minimum(o, c) - np.abs(g.normal(0, 0.8, n))
    P = _path(o, h, l, c, H=288)
    k = g.choice(n, 400, replace=False)
    tc, p, d = P["t"][k] + 300, c[k], np.where(g.random(400) < 0.5, 1, -1)
    r = tr.race(P, tc, p, d)
    refs = [[[_reference(P, tc[q], p[q], d[q], a, b) for q in range(400)] for b in SL] for a in TP]
    n_ok = sum(x is not None for x in refs[0][0])
    assert r["n"] == n_ok > 300
    for i, a in enumerate(TP):
        for j, b in enumerate(SL):
            rr = [x for x in refs[i][j] if x is not None]
            assert r["win"][i][j] == sum(x[0] == "W" for x in rr), (a, b)
            assert r["loss"][i][j] == sum(x[0] == "L" for x in rr), (a, b)
            assert abs(r["mark"][i][j] - sum(x[1] for x in rr if x[0] == "O")) < 0.02, (a, b)


def test_forward_triggers_reads_both_keys_once_per_decision(tmp_path):
    cur, prev, old = "cfg:web7", "cfg:web6", "cfg:web5"
    hd = tmp_path / "holdout"
    (hd / "archive").mkdir(parents=True)
    t1, t2, t3 = "2026-10-20T10:00:00+00:00", "2026-10-21T10:00:00+00:00", "2026-10-22T10:00:00+00:00"
    (hd / "15m_treatment.json").write_text(json.dumps([{"freeze_key": cur, "entry_time": t1, "dir": "LONG", "entry": 4000.0}]))
    (hd / "15m_h6.json").write_text(json.dumps([{"freeze_key": cur + ":armhash", "entry_time": t1, "dir": "LONG", "entry": 4000.0}]))
    (hd / "archive" / "15m_h4.json").write_text(json.dumps([
        {"freeze_key": prev + ":h4hash", "entry_time": t2, "dir": "SHORT", "entry": 4010.0},
        {"freeze_key": old, "entry_time": t3, "dir": "LONG", "entry": 4020.0}]))
    (hd / "5m_treatment.json").write_text(json.dumps([{"freeze_key": cur, "entry_time": t3, "dir": "LONG", "entry": 1.0}]))
    (hd / "manifest_h2.json").write_text(json.dumps({"freeze_key": cur}))
    ts, px, d, n = tr.forward_triggers(str(tmp_path), "15m", 900, [cur, prev])
    assert n == 2 and list(d) == [1, -1] and list(px) == [4000.0, 4010.0]
    assert ts[0] == int(np.datetime64("2026-10-20T10:15:00").astype("datetime64[s]").astype(np.int64))
    assert tr.forward_triggers(None, "15m", 900, [cur])[3] == 0


def test_payload_on_a_synthetic_market_falls_back_to_chart_bars_and_is_strict_json():
    m = load_synthetic("15m", bars=1500, seed=4)
    res = engine.run(m, DEFAULT)
    ctrl = engine.run(m, DEFAULT, "control", res.F)
    chal = engine.run(m, DEFAULT, "challenger", res.F)
    p = report.build(m, res, ctrl, DEFAULT, holdout.load_or_freeze(None, DEFAULT), res_chal=chal)
    R = p["trade_race"]
    assert "error" not in R, R
    assert R["tp_grid"] == list(TP) and R["sl_grid"] == list(SL)
    assert R["bar_sec"] == 900 and R["horizon_bars"] == 96 and "15m bars" in R["bars"]
    keys = [s["key"] for s in R["sources"]]
    assert keys == ["engine", "challenger", "h2", "h3", "h4", "h5", "h6", "forward"]
    assert R["random"]["long"]["n"] > 0 and R["random"]["short"]["n"] > 0
    for s in R["sources"] + list(R["random"].values()):
        for i in range(len(TP)):
            for j in range(len(SL)):
                assert 0 <= s["win"][i][j] + s["loss"][i][j] <= s["n"]
    json.dumps(p, allow_nan=False)
    assert os.path.basename(tr.__file__) == "trade_race.py"


def test_time_to_tp_and_to_either_barrier_are_counted_in_bars():
    # long at 100: +2 reached on bar 0 (1 bar to close), -10 on bar 2 (3 bars); +3 never; neither for +50 / -100
    P = _path(o=[100, 102, 96, 86], h=[102.5, 102, 96, 87], l=[99.5, 95, 85, 85], c=[102, 96, 86, 86])
    r = tr.race(P, [T0], [100.0], [1])
    i2, i3, j10 = TP.index(2.0), TP.index(3.0), SL.index(10.0)
    assert r["t_tp"][i2][j10] == 1 and r["t_res"][i2][j10] == 1             # TP on the first bar
    assert r["t_tp"][i3][j10] == 0 and r["t_res"][i3][j10] == 3             # the stop on the third bar
    assert r["t_res"][TP.index(50.0)][SL.index(100.0)] == 0                  # open paths add nothing
