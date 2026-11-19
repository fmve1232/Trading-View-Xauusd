"""B31b-W4 (research/registrations/B31b-W4.json): pullback continuation, reversal, breakout-retest and entry timing.

A hand-worked bearish episode, the M30 context, a truncation (no look-ahead) check including the M5 method, the
taxonomy, Holm, and the registration's order (registered before the code, development only)."""
import json
import os

import numpy as np
import pandas as pd
import pytest

from quantum.research import w3liq as W
from quantum.research import w4pull as X

FLAT = (4000.0, 4000.5, 3999.5, 4000.0)


def frame_of(rows, start="2026-03-02 00:00", freq="15min"):
    idx = pd.date_range(start, periods=len(rows), freq=freq, tz="UTC")
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"]).assign(volume=np.nan)


def agg(df, rule):
    return df.resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(
        subset=["open"])


def bearish_episode_rows():
    """Flat 4000; a swing low at bar 150 (low 3995, body bottom 3999); a BREAK at bar 161 (close 3991); a pullback whose
    bar 163 trades to 3995.5 and closes 3994 (back below the zone); then a slide to 3970."""
    rows = [FLAT] * 150 + [(4000.0, 4000.5, 3995.0, 3999.0)] + [FLAT] * 10
    rows += [(4000.0, 4000.2, 3990.0, 3991.0)]                      # 161: the BREAK
    rows += [(3991.0, 3992.0, 3990.5, 3991.5)]                      # 162
    rows += [(3991.5, 3995.5, 3991.0, 3994.0)]                      # 163: into the zone, closes back below 3995
    rows += [(3994.0, 3994.2, 3991.5, 3992.0)]                      # 164: the next close is lower (T4)
    px = 3992.0
    for _ in range(40):
        rows.append((px, px + 0.3, px - 1.0, px - 0.8))
        px -= 0.8
    rows += [(px, px + 0.3, px - 0.3, px)] * 120
    return rows


def frames_of(m15, m5=None):
    h1 = agg(m15, "1h")
    P, F15, F30, _ = W.frames(m15, h1, m5)
    return P, F15, F30, h1


def test_hand_worked_bearish_episode_a1_t4_a4_t1():
    m15 = frame_of(bearish_episode_rows())
    P, F, F30, h1 = frames_of(m15)
    ctx = np.full(len(F.c), -1)                                      # the M30 context forced bearish
    eps = X.a_episodes(F, ctx, int(F.t[0]))
    ep = [e for e in eps if e["i"] == 161]
    assert len(ep) == 1
    ep = ep[0]
    atr = F.atr[161]
    w = min(max(3999.0 - 3995.0, 0.15 * atr), 0.75 * atr)
    assert ep["d"] == -1 and ep["L"] == 3995.0 and ep["zn"] == 3995.0 and ep["zf"] == pytest.approx(3995.0 + w)
    od = {o["m"]: o for o in X.a_orders(P, F, ep, np.asarray(X.ta.ema(F.c, 50), float), None, None)}
    buf = 0.2 * atr
    assert od["A1"]["j"] == 163 and od["A1"]["px"] == 3994.0 and od["A1"]["stop"] == pytest.approx(3995.5 + buf)
    assert od["T4"]["j"] == 164 and od["T4"]["px"] == 3992.0
    assert od["A4"]["kind"] == "LIM" and od["A4"]["px"] == 3995.0 and od["A4"]["valid"] == 161 + 8
    assert od["A4"]["stop"] == pytest.approx(3995.0 + w + buf)
    assert od["T1"]["px"] == pytest.approx(3995.0 - 0.25 * atr) and od["T1"]["t"] == int(F.t[161]) + 900
    a4 = W.execute(P, F, od["A4"])
    assert a4["status"] == "FILLED" and a4["e"] == 3995.0 and a4["t_fill"] == int(F.t[163])
    a1 = W.execute(P, F, od["A1"])
    assert a1["status"] == "FILLED" and a1["d"] == -1 and a1["tp10"] == "TP"


def test_a6_failed_reclaim_and_a1_needs_a_close_back_below():
    rows = bearish_episode_rows()
    rows[163] = (3991.5, 3996.0, 3991.0, 3995.6)                    # closes back ABOVE 3995: a reclaim, not a rejection
    rows[164] = (3995.6, 3995.8, 3992.0, 3992.5)                    # then closes below again: A6
    m15 = frame_of(rows)
    P, F, _, _ = frames_of(m15)
    ep = [e for e in X.a_episodes(F, np.full(len(F.c), -1), int(F.t[0])) if e["i"] == 161][0]
    od = {o["m"]: o for o in X.a_orders(P, F, ep, np.asarray(X.ta.ema(F.c, 50), float), None, None)}
    assert od["A6"]["j"] == 164 and od["A6"]["stop"] == pytest.approx(3996.0 + 0.2 * F.atr[161])
    assert "A1" not in od or od["A1"]["j"] != 163


def test_without_a_reclaim_there_is_no_a6_and_without_a_lower_close_no_t4():
    rows = bearish_episode_rows()
    m15 = frame_of(rows)
    P, F, _, _ = frames_of(m15)
    ep = [e for e in X.a_episodes(F, np.full(len(F.c), -1), int(F.t[0])) if e["i"] == 161][0]
    od = {o["m"] for o in X.a_orders(P, F, ep, np.asarray(X.ta.ema(F.c, 50), float), None, None)}
    assert "A6" not in od and "T4" in od
    rows[164] = (3994.0, 3994.6, 3993.8, 3994.3)                    # the bar after A1 closes HIGHER: no T4
    P, F, _, _ = frames_of(frame_of(rows))
    ep = [e for e in X.a_episodes(F, np.full(len(F.c), -1), int(F.t[0])) if e["i"] == 161][0]
    od = {o["m"] for o in X.a_orders(P, F, ep, np.asarray(X.ta.ema(F.c, 50), float), None, None)}
    assert "A1" in od and "T4" not in od


def split5(o, h, l, c):
    """Three M5 bars whose aggregate is the 15m bar (path o-l-h-c when bullish, o-h-l-c when bearish)."""
    if c >= o:
        return [(o, o, l, l), (l, h, l, h), (h, h, c, c)]
    return [(o, h, o, h), (h, h, l, l), (l, c, l, c)]


def test_a3_m5_mss_uses_a_swing_formed_after_the_approach():
    rows = bearish_episode_rows()
    rows[164] = (3994.0, 3994.8, 3993.6, 3993.9)
    rows[165] = (3993.9, 3994.0, 3992.0, 3992.2)
    m5rows = [b for r in rows for b in split5(*r)]
    m5rows[163 * 3:166 * 3] = [(3991.5, 3994.0, 3991.0, 3993.9), (3993.9, 3995.5, 3993.8, 3995.2), (3995.2, 3995.3, 3993.95, 3994.0),
                               (3994.0, 3994.6, 3993.6, 3994.4), (3994.4, 3994.8, 3994.1, 3994.5), (3994.5, 3994.6, 3993.8, 3993.9),
                               (3993.9, 3994.0, 3993.0, 3993.1), (3993.1, 3993.2, 3992.0, 3992.1), (3992.1, 3992.3, 3992.0, 3992.2)]
    m15, m5 = frame_of(rows), frame_of(m5rows, freq="5min")
    P, F, _, _ = frames_of(m15, m5)
    ep = [e for e in X.a_episodes(F, np.full(len(F.c), -1), int(F.t[0])) if e["i"] == 161][0]
    pl5, ph5 = X.ta.pivotlow(P.l5, 2, 2), X.ta.pivothigh(P.h5, 2, 2)
    a3 = [o for o in X.a_orders(P, F, ep, np.asarray(X.ta.ema(F.c, 50), float), pl5, ph5) if o["m"] == "A3"]
    assert len(a3) == 1
    assert a3[0]["t"] == int(F.t[165]) + 300 and a3[0]["px"] == 3993.1          # the first M5 close below 3993.6
    assert a3[0]["stop"] == pytest.approx(3995.5 + 0.2 * F.atr[161])


def test_c1_waits_for_a_retest_after_the_acceptance_bar():
    rows = [FLAT] * 40 + [(4000.0, 4000.5, 3995.0, 4000.0)] + [FLAT] * (128 - 41)     # Monday's low 3995 = Tuesday's PDL
    rows += [(4000.0, 4000.2, 3992.5, 3993.0)]                                         # Tue 08:00: the break
    rows += [(3993.0, 3994.95, 3992.0, 3992.5)]                                        # acceptance, also near the level
    rows += [(3992.5, 3995.0, 3992.4, 3993.0)]                                         # the retest that closes below
    rows += [(3993.0, 3993.2, 3992.8, 3993.0)] * 60
    m15 = frame_of(rows)
    P, F, F30, h1 = frames_of(m15)
    t_break = int(pd.Timestamp("2026-03-03 08:00", tz="UTC").timestamp())
    i = int(np.searchsorted(F.t, t_break))
    assert F.pools["PDL"][i] == 3995.0
    tclose = F.t + F.sec
    m30df = pd.DataFrame({"high": F30.h, "low": F30.l}, index=pd.to_datetime(F30.t, unit="s", utc=True))
    hts = [X.htf_swings(h1, 3600, tclose), X.htf_swings(m30df, 1800, tclose)]
    c1 = [o for o in X.c_orders(F, np.zeros(len(F.c), int), hts, int(F.t[0])) if o["m"] == "C1" and o["d"] == -1]
    assert [o["j"] for o in c1] == [i + 2]


def test_m30_context_reads_a_staircase_down_as_bearish_and_up_as_bullish():
    hs, ls, cs = [], [], []
    px = 4100.0
    for _ in range(14):
        for k in range(6):
            px -= 10 / 6
            hs.append(px + 1.0), ls.append(px - 1.0), cs.append(px)
        for k in range(6):
            px += 4 / 6
            hs.append(px + 1.0), ls.append(px - 1.0), cs.append(px)
    t = np.arange(len(cs)) * 1800
    cx = X.m30_context(t, np.array(hs), np.array(ls), np.array(cs))
    assert cx[-1] == -1
    cx2 = X.m30_context(t, -np.array(ls) + 8200, -np.array(hs) + 8200, -np.array(cs) + 8200)
    assert cx2[-1] == 1


def walk(n5=7200, seed=7):
    """A seeded M5 random walk with trending regimes, aggregated to M15 (so M5 and M15 agree)."""
    rng = np.random.default_rng(seed)
    drift = np.repeat(rng.choice([-0.35, 0.0, 0.35], size=n5 // 600 + 1), 600)[:n5]
    c = 4000 + np.cumsum(drift + rng.normal(0, 1.1, n5))
    o = np.concatenate([[4000.0], c[:-1]])
    h = np.maximum(o, c) + rng.uniform(0, 0.8, n5)
    l = np.minimum(o, c) - rng.uniform(0, 0.8, n5)
    m5 = frame_of(list(zip(o, h, l, c)), start="2026-03-02 00:00", freq="5min")
    return agg(m5, "15min"), m5


def key(o):
    return (o["m"], o["d"], int(o["t"]), round(float(o["px"]), 6), round(float(o["stop"]), 6))


@pytest.mark.parametrize("seed", [7, 11])
def test_no_lookahead_every_order_is_rebuilt_identically_from_data_ending_at_its_decision(seed):
    m15, m5 = walk(seed=seed)
    P, F15, F30, h1 = frames_of(m15, m5)
    sf = int(F15.t[0]) + 86400 * 3
    full, _, _ = X.orders_of(P, F15, F30, h1, sf)
    assert {o["m"] for o in full} >= {"A1", "A3", "A4", "A6", "T1", "T4", "B1", "B3", "C1"}
    by_t = {}
    for o in full:
        by_t.setdefault(int(o["t"]), []).append(o)
    for t, os_ in by_t.items():                              # every order, rebuilt from the bars closed by its decision
        cut_at = pd.Timestamp(t, unit="s", tz="UTC")
        m15c = m15[m15.index + pd.Timedelta(minutes=15) <= cut_at]
        m5c = m5[m5.index + pd.Timedelta(minutes=5) <= cut_at]
        P2, F2, F302, h12 = frames_of(m15c, m5c)
        cut = {key(x) for x in X.orders_of(P2, F2, F302, h12, sf)[0]}
        for o in os_:
            assert key(o) in cut, o


def test_taxonomy_continuation_and_short_covering_bounce():
    rows = [FLAT] * 120 + [(4000.0, 4000.5, 3994.0, 3999.8)]        # 120: a sweep below, reclaimed (d = +1)
    cont = rows + [(3999.8, 3999.9, 3993.0, 3993.5)] + [FLAT] * 120
    bounce = rows + [(3999.8, 4003.5, 3999.6, 4003.0), (4003.0, 4003.1, 3992.0, 3992.5)] + [FLAT] * 120
    tie = rows + [(3999.8, 4002.0, 3993.0, 3993.5)] + [FLAT] * 120   # +1 ATR and a close below the sweep low in one bar
    for rr, want in ((cont, "CONTINUATION"), (bounce, "SHORT-COVERING BOUNCE"), (tie, "CONTINUATION")):
        m15 = frame_of(rr)
        P, F, F30, _ = frames_of(m15)
        ev = {"i": 120, "c": -1, "d": 1, "L": 3999.5, "kind": "SW", "atr": 2.0}
        assert X.b_taxonomy(F, F30, ev, X.m30_swings(F30)) == want


def test_holm_matches_the_step_down_definition():
    h = X.holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": None})
    assert h["a"] == pytest.approx(0.03) and h["c"] == pytest.approx(0.06) and h["b"] == pytest.approx(0.06)
    assert "d" not in h


def test_only_development_and_the_case_study_can_run():
    with pytest.raises(SystemExit):
        X.main(["--part", "validation", "--rd", "x", "--out", "y"])
    with pytest.raises(SystemExit):
        X.main(["--part", "holdout", "--rd", "x", "--out", "y"])


def test_registration_precedes_the_code_and_names_the_family():
    p = os.path.join(os.path.dirname(X.__file__), "..", "..", "research", "registrations", "B31b-W4.json")
    r = json.load(open(p))
    assert r["id"] == "B31b-W4" and "development only" in r["partitions"]["used"]
    assert "amendment_A1_before_any_run" in r
    assert r["statistics"]["family"].startswith(f"{len(X.METHODS)} methods") and len(X.METHODS) == 15
    defined = " ".join(list(r["module_A_pullback_continuation"]) + list(r["timing_study"]) + list(r["module_B_reversal"])
                       + list(r["module_C_breakout_retest"]))
    for m in X.METHODS:
        assert f"{m}_" in defined, m
    assert "NO CANDIDATE" in r["statistics"]["candidate"]


def test_reconstruction_zones_are_point_in_time():
    """w4recon.zones_at sees only bars closed by its time: appending later bars changes nothing, no zone is known later."""
    from quantum.research import w4recon as R
    m15, _ = walk(n5=4800, seed=3)
    raw = {"15m": m15, "30m": agg(m15, "30min"), "1h": agg(m15, "1h"), "4h": agg(m15, "4h")}
    now = int(m15.index[900].timestamp()) + 60
    cut = {k: v[v.index < pd.Timestamp(now - 60, unit="s", tz="UTC")] for k, v in raw.items()}
    _, _, full = R.zones_at(raw, now)
    _, _, past = R.zones_at(cut, now)
    assert full == past and full
    assert all(z["t_known"] <= now for z in full)


def test_the_break_uses_only_swings_confirmed_before_its_bar():
    """A wick to 3988 two bars before the break becomes a swing low only one bar AFTER the break (pivot 3 / 3): the break
    of the older 3995 swing at bar 161 must stand, judged with what was known then."""
    rows = [FLAT] * 150 + [(4000.0, 4000.5, 3995.0, 3999.0)] + [FLAT] * 8
    rows += [(4000.0, 4000.3, 3988.0, 3996.0)]                      # 159: wick to 3988, close back above 3995
    rows += [(3996.0, 3996.5, 3994.0, 3996.0)]                      # 160
    rows += [(3996.0, 3996.2, 3990.0, 3991.0)]                      # 161: closes below 3995 (the known swing)
    rows += [(3991.0, 3992.0, 3989.0, 3990.0)]                      # 162: 159 becomes a pivot low only now
    rows += [(3990.0, 3990.5, 3989.5, 3990.0)] * 60
    P, F, _, _ = frames_of(frame_of(rows))
    eps = [e for e in X.a_episodes(F, np.full(len(F.c), -1), int(F.t[0])) if e["i"] == 161]
    assert len(eps) == 1 and eps[0]["L"] == 3995.0
