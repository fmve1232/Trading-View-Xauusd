"""B31b-W5 (research/registrations/B31b-W5.json): the executable entry-price study.

A hand-worked impulse (every mechanism's price), J's first completion, the controls (R1 same stop distance inside the
same window; R3 random prices inside the eligible zone), the EMA limit's causality, an exhaustive truncation check
(every order rebuilt from the bars closed by its decision, M5 included) and the registration."""
import json
import os

import numpy as np
import pandas as pd
import pytest

from quantum import ta
from quantum.research import w3liq as W
from quantum.research import w5entry as X

FLAT = (4000.0, 4000.5, 3999.5, 4000.0)


def frame_of(rows, start="2026-03-02 00:00", freq="15min"):
    idx = pd.date_range(start, periods=len(rows), freq=freq, tz="UTC")
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"]).assign(volume=np.nan)


def agg(df, rule):
    return df.resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(
        subset=["open"])


def impulse_rows(after=None):
    """Flat 4000 with a swing high 4001.0 at bar 190 and a dip to 3998.0 at bar 199; an up impulse closes 4000.4 at bar
    200 (t0), makes 4002.0 at 201, and 202 is the first pullback bar (t1); then `after` (default: a slow rise)."""
    rows = [FLAT] * 190 + [(4000.0, 4001.0, 3999.5, 4000.0)] + [FLAT] * 8
    rows += [(4000.0, 4000.2, 3998.0, 3999.0)]                       # 199: the impulse's origin L0 = 3998.0
    rows += [(3999.0, 4000.6, 3998.9, 4000.4)]                       # 200: t0
    rows += [(4000.4, 4002.0, 4000.3, 4001.9)]                       # 201: the extreme 4002.0
    rows += [(4001.9, 4001.9, 4000.9, 4001.0)]                       # 202: t1 (high 4001.9 <= 4002.0)
    if after is None:
        after = [(4001.0, 4001.2, 3999.9, 4000.1)]
        px = 4000.1
        for _ in range(40):
            after.append((px, px + 1.2, px - 0.1, px + 1.0))
            px += 1.0
    return rows + after + [(after[-1][3], after[-1][3] + 0.2, after[-1][3] - 0.2, after[-1][3])] * 40


def build(rows, m5=None, sf=None):
    m15 = frame_of(rows)
    P, F, F30, _ = W.frames(m15, agg(m15, "1h"), m5)
    sf = int(m15.index[0].timestamp()) if sf is None else sf
    return P, F, X.opportunities(F, sf)


def ema_of(F):
    return {"G20": F.e20, "G50": np.asarray(ta.ema(F.c, 50), float)}


def test_hand_worked_impulse_and_every_mechanism_price():
    P, F, ops = build(impulse_rows())
    op = [o for o in ops if o["t0"] == 200 and o["d"] == 1]
    assert len(op) == 1
    op = op[0]
    a0 = F.atr[200]
    assert op["p0"] == 199 and op["X0"] == 3998.0 and op["S"] == pytest.approx(3998.0 - 0.2 * a0)
    assert op["t1"] == 202 and op["Hx"] == 4002.0 and op["R"] == pytest.approx(4.0) and op["p_0"] == 4000.4
    od = {o["m"]: o for o in X.orders_for(P, F, op, ema_of(F))}
    assert od["A0"]["px"] == 4000.4 and od["A0"]["t"] == int(F.t[200]) + 900
    assert od["A1"]["px"] == 4001.0 and od["A1"]["t"] == int(F.t[202]) + 900
    for r in X.LEVELS:
        b = od[X.BNAME[r]]
        assert b["kind"] == "LIM" and b["px"] == pytest.approx(4002.0 - r * 4.0) and b["stop"] == op["S"]
        assert b["valid"] == op["end"] and b["cancel_back"] and b["L"] == op["S"]
    assert 0.2 <= od["B_rand"]["u"] <= 0.8 and od["B_rand"]["px"] == pytest.approx(4002.0 - od["B_rand"]["u"] * 4.0)
    assert od["C"]["px"] == 4000.4                                   # bar 201 has the largest up body (1.5)
    assert od["E"]["px"] == 4001.0                                   # the swing high of bar 190, broken at 201
    assert od["F"]["px"] == pytest.approx(np.mean([(F.h[k] + F.l[k] + F.c[k]) / 3 for k in range(199, 203)]))
    assert od["I"]["px"] == pytest.approx(4002.0 - F.atr[202])
    pk = op["S"] + max(F.atr[202], 8 * P.cost[202] * F.c[202] / 4000.0)
    if F.c[202] - pk <= 0:                                           # price already at / beyond the adaptive level
        assert od["K"]["kind"] == "MKT" and od["K"]["px"] == F.c[202]
    else:
        assert od["K"]["kind"] == "LIM" and od["K"]["px"] == pytest.approx(pk)
    b5 = W.execute(P, F, od["B0.5"])
    assert b5["status"] == "FILLED" and b5["e"] == 4000.0 and b5["t_fill"] == int(F.t[203])


def test_j_fires_on_the_first_completed_reclaim_not_only_the_first_dip():
    after = [(4001.0, 4001.2, 3999.9, 4000.1)] + [(4000.1, 4000.8, 4000.0, 4000.5)] * 4 + [(4000.5, 4001.8, 4000.4, 4001.5)]
    px = 4001.5
    for _ in range(30):
        after.append((px, px + 1.2, px - 0.1, px + 1.0))
        px += 1.0
    P, F, ops = build(impulse_rows(after))
    op = [o for o in ops if o["t0"] == 200 and o["d"] == 1][0]
    j = [o for o in X.orders_for(P, F, op, ema_of(F)) if o["m"] == "J"][0]
    assert j.get("status") != "MISSED" and j["j"] == 208 and j["px"] == 4001.5


def test_the_ema_limit_is_priced_from_closed_bars_only():
    P, F, ops = build(impulse_rows())
    op = [o for o in ops if o["t0"] == 200][0]
    for nm, n in (("G20", 20), ("G50", 50)):
        g = X.dynamic_limit(nm, op, F, ema_of(F)[nm])
        if g.get("virtual"):
            continue
        j = g["valid"]
        assert g["px"] == pytest.approx(np.asarray(ta.ema(F.c[:j], n), float)[-1])        # bars before the fill bar only


def walk(n5=9000, seed=7):
    rng = np.random.default_rng(seed)
    drift = np.repeat(rng.choice([-0.35, 0.0, 0.35], size=n5 // 600 + 1), 600)[:n5]
    c = 4000 + np.cumsum(drift + rng.normal(0, 1.1, n5))
    o = np.concatenate([[4000.0], c[:-1]])
    h = np.maximum(o, c) + rng.uniform(0, 0.8, n5)
    l = np.minimum(o, c) - rng.uniform(0, 0.8, n5)
    m5 = frame_of(list(zip(o, h, l, c)), freq="5min")
    return agg(m5, "15min"), m5


def key(o):
    return (o["m"], o["d"], int(o["t"]), round(float(o["px"]), 6), round(float(o["stop"]), 6))


def all_orders(m15, m5, sf):
    P, F, F30, _ = W.frames(m15, agg(m15, "1h"), m5)
    out = []
    for op in X.opportunities(F, sf):
        out += [o for o in X.orders_for(P, F, op, ema_of(F)) if not o.get("virtual")]
    return out


@pytest.mark.parametrize("seed", [7, 11])
def test_no_lookahead_every_order_is_rebuilt_identically_from_data_ending_at_its_decision(seed):
    m15, m5 = walk(seed=seed)
    sf = int(m15.index[0].timestamp()) + 86400 * 3
    full = [o for o in all_orders(m15, m5, sf) if o["m"] not in ("G20", "G50")]   # G: emitted at its fill bar (own test)
    assert {o["m"] for o in full} >= {"A0", "A1", "B0.5", "B_rand", "C", "E", "F", "H", "I", "J", "K"}
    by_t = {}
    for o in full:
        by_t.setdefault(int(o["t"]), []).append(o)
    for t, os_ in by_t.items():
        cut_at = pd.Timestamp(t, unit="s", tz="UTC")
        cut = {key(x) for x in all_orders(m15[m15.index + pd.Timedelta(minutes=15) <= cut_at],
                                          m5[m5.index + pd.Timedelta(minutes=5) <= cut_at], sf)}
        for o in os_:
            assert key(o) in cut, o


def test_r1_controls_stay_in_the_window_with_the_same_stop_distance(monkeypatch):
    m15, m5 = walk(seed=3)
    res = X.build(m15, agg(m15, "1h"), m5, int(m15.index[0].timestamp()) + 86400 * 3)
    ops = {o["id"]: o for o in res["ops"]}
    rows = [r for r in X.counted(res["rows"], "A1") + X.counted(res["rows"], "A0") if W.decided(r)][:40]
    calls = []
    monkeypatch.setattr(W, "race_fast", lambda P, k0, d, e, stop, tgt, *a: calls.append((k0, d, e, stop)) or ("SL", 0.0, stop, False))
    for r in rows:
        calls.clear()
        X.r1_control(res["P"], [r], ops)
        op = ops[r["op"]]
        lo = op["t0"] if r["m"] == "A0" else op["t1"]
        assert len(calls) == X.K_RAND * len(W.TP)
        for k0, d, e, stop in calls:
            assert lo <= k0 - 1 <= lo + X.WIN and d == r["d"]
            assert d * (e - stop) / (e / 4000.0) == pytest.approx(r["D"])


def test_r3_prices_are_inside_the_eligible_zone_with_the_structural_stop(monkeypatch):
    m15, m5 = walk(seed=5)
    res = X.build(m15, agg(m15, "1h"), m5, int(m15.index[0].timestamp()) + 86400 * 3)
    seen = []
    monkeypatch.setattr(W, "execute", lambda P, F, od: seen.append(od) or {"status": "MISSED"})
    ops = [o for o in res["ops"] if o["t1"] is not None][:20]
    X.r3_control(res["P"], res["F"], ops)
    assert len(seen) == X.K_RAND * len(ops)
    by = {o["id"]: o for o in ops}
    for od in seen:
        op = by[od["op"]]
        lo, hi = sorted((op["Hx"], op["Hx"] - op["d"] * X.ZONE_MAX * op["R"]))
        assert lo - 1e-9 <= od["px"] <= hi + 1e-9 and od["stop"] == op["S"] and od["valid"] == op["end"]


def test_only_development_and_the_case_can_run():
    for part in ("validation", "holdout"):
        with pytest.raises(SystemExit):
            X.main(["--part", part, "--rd", "x", "--out", "y"])


def test_registration_names_the_twenty_candidates_and_the_controls():
    p = os.path.join(os.path.dirname(X.__file__), "..", "..", "research", "registrations", "B31b-W5.json")
    with open(p) as fh:
        r = json.load(fh)
    assert r["id"] == "B31b-W5" and "development only" in r["partitions"]["used"]
    assert len(X.CANDIDATES) == 20 and r["statistics"]["family"].startswith("the 20 candidates")
    for m in ("A0", "A1", "C", "E", "F", "H", "I", "J", "K"):
        assert m in r["mechanisms"]
    assert "R1_same_D_random_timing" in r["benchmarks"] and "R3_random_price_in_zone" in r["benchmarks"]
    assert "NOT RUN until Dukascopy" in r["tick_validation"]
