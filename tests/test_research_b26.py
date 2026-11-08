"""B26 labeller (quantum/research/b26.py) against its registration (research/registrations/B26.json)."""
import numpy as np
import pandas as pd
import pytest

from quantum.research import b26
from quantum.research import harness as H

T0 = pd.Timestamp("2026-11-02 08:00", tz="UTC")          # a Monday, London session
WALK0 = pd.Timestamp("2026-03-02 00:00", tz="UTC")
KEYS = ("out", "xb", "xpx", "xt", "gap", "fill", "tp", "sl", "mfe", "mae")


def _bars(rows, start=T0, step=900, gaps=None):
    """rows = [(o, h, l, c)]; gaps = {row index: extra seconds inserted before that row}."""
    t, cur = [], start
    for i in range(len(rows)):
        cur = cur + pd.Timedelta(seconds=(gaps or {}).get(i, 0))
        t.append(cur)
        cur = cur + pd.Timedelta(seconds=step)
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=pd.DatetimeIndex(t))


def _flat(n, px=4000.0):
    return [(px, px + 0.5, px - 0.5, px)] * n


def _race(df, f=1, d=1, s=0.0, si=0.0, so=0.0, k=1.0, horizon=192):
    P = b26.make_path(df, 900)
    return dict(zip(KEYS, b26.race(P, f, d, s, si, so, k, horizon), strict=True))


def test_buy_fills_at_the_ask_and_its_target_triggers_on_the_bid():
    rows = _flat(2) + [(4000.0, 4015.40, 3999.0, 4010.0), (4010.0, 4015.60, 4009.0, 4015.0)] + _flat(3, 4015.0)
    r = _race(_bars(rows), s=0.30, si=0.20)
    assert r["fill"] == pytest.approx(4000.35) and r["tp"] == pytest.approx(4015.35) and r["sl"] == pytest.approx(3985.35)
    assert r["out"] == b26.TP and r["xb"] == 3 and r["xpx"] == pytest.approx(4015.35) and not r["gap"]   # 4015.40 - 0.15 < TP
    assert r["mfe"] == pytest.approx(15.0)


def test_the_spread_alone_can_turn_a_target_touch_into_no_touch():
    rows = _flat(2) + [(4000.0, 4015.0, 3999.0, 4010.0)] + _flat(200, 4010.0)
    assert _race(_bars(rows))["out"] == b26.TP                                         # mid touches +15 exactly
    assert _race(_bars(rows), s=0.30)["out"] != b26.TP                                 # the bid does not


def test_a_bar_reaching_both_levels_is_the_stop_with_exit_slippage():
    rows = _flat(2) + [(4000.0, 4030.0, 3970.0, 4000.0)] + _flat(3)
    r = _race(_bars(rows), s=0.30, si=0.20, so=0.20)
    assert r["out"] == b26.AMB and r["xpx"] == pytest.approx(3985.35 - 0.20)


def test_a_gap_through_the_stop_fills_at_the_open_and_through_the_target_at_the_target():
    rows = _flat(2) + [(3980.0, 3981.0, 3979.0, 3980.0)] + _flat(3, 3980.0)
    r = _race(_bars(rows), s=0.30, si=0.20, so=0.20)
    assert r["out"] == b26.SL and r["gap"] and r["xpx"] == pytest.approx(3980.0 - 0.15 - 0.20) and r["mae"] > 15.0
    rows = _flat(2) + [(4030.0, 4031.0, 4029.0, 4030.0)] + _flat(3, 4030.0)
    r = _race(_bars(rows), s=0.30, si=0.20, so=0.20)
    assert r["out"] == b26.TP and r["gap"] and r["xpx"] == pytest.approx(4015.35)      # a limit: no credit for the better open


def test_sell_fills_at_the_bid_and_triggers_on_the_ask():
    rows = _flat(2) + [(4000.0, 4001.0, 3984.60, 3990.0)] + _flat(3, 3990.0)
    r = _race(_bars(rows), d=-1, s=0.30, si=0.20)
    assert r["fill"] == pytest.approx(3999.65) and r["tp"] == pytest.approx(3984.65) and r["sl"] == pytest.approx(4014.65)
    assert r["out"] != b26.TP                                                          # ask low 3984.75 is above the TP
    rows = _flat(2) + [(4000.0, 4001.0, 3984.40, 3990.0)] + _flat(3, 3990.0)
    assert _race(_bars(rows), d=-1, s=0.30, si=0.20)["out"] == b26.TP                  # ask low 3984.55 <= TP


def test_the_daily_break_is_held_and_a_closure_exits_at_the_last_bar():
    rows = _flat(6)
    df = _bars(rows, gaps={4: 3600})                                                   # a one-hour break before row 4
    r = _race(df, horizon=192)
    assert r["out"] == b26.OPEN and r["xb"] == 5                                       # held through, then the data ends
    df = _bars(rows, gaps={4: 3 * 86400})                                              # a weekend before row 4
    r = _race(df, s=0.30, so=0.20)
    assert r["out"] == b26.CLOSURE and r["xb"] == 3 and r["xpx"] == pytest.approx(4000.0 - 0.15 - 0.20)


def test_time_limit():
    r = _race(_bars(_flat(300)), horizon=192)
    assert r["out"] == b26.TIMEOUT and r["xb"] == 1 + 191


def test_no_entry_across_a_break_or_within_an_hour_of_a_closure():
    df = _bars(_flat(20), gaps={10: 3600, 16: 3 * 86400})
    P = b26.make_path(df, 900)
    el = b26.eligible(P, int(T0.timestamp()))
    assert not el[9]                                                                   # the fill would be after the break
    assert el[10] and el[11]                                                           # 1.5 h / 1.25 h before the closure
    assert not el[12] and not el[15]                                                   # 1 h or less before it
    assert not el[19]                                                                  # no fill bar


def _walk(n=3000, seed=3, step=900, start=WALK0):
    rng = H.seeded_rng(seed)
    c = 4000.0 + np.cumsum(rng.normal(0.0, 4.0, n))
    o = np.r_[4000.0, c[:-1]]
    hi = np.maximum(o, c) + np.abs(rng.normal(0, 1.5, n))
    lo = np.minimum(o, c) - np.abs(rng.normal(0, 1.5, n))
    idx = pd.date_range(start, periods=n, freq=f"{step}s", tz="UTC")
    return pd.DataFrame({"open": o, "high": hi, "low": lo, "close": c, "volume": np.nan}, index=idx)   # the feed has no volume


def test_context_reads_only_closed_bars():
    h1 = _walk(2400, step=3600, start=pd.Timestamp("2026-01-05", tz="UTC"))
    T = np.array([int(pd.Timestamp("2026-03-20 10:00", tz="UTC").timestamp())])
    a = b26.context(h1, T)
    h2 = h1.copy()
    later = h2.index >= pd.Timestamp("2026-03-20 10:00", tz="UTC")                     # the bar opening at T is not closed
    h2.loc[later, ["open", "high", "low", "close"]] *= 1.5
    b = b26.context(h2, T)
    assert all(a[x][0] == b[x][0] for x in ("vol", "trend")) and all(
        (np.isnan(a[x][0]) and np.isnan(b[x][0])) or a[x][0] == b[x][0] for x in ("v1h", "v4h", "v1d"))


def _pop(scale=False):
    m15 = _walk()
    return {"bars": m15, "h1": m15.resample("1h", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["close"]),
        "score_from": m15.index[0] + pd.Timedelta(days=1), "scale": scale, "tf": "15m", "label": "test"}


def test_population_series_symmetry_and_sequence():
    df = b26.run_population("T", _pop(), log=lambda *_: None)
    assert set(df["dir"]) == {"BUY", "SELL"} and (df["dir"] == "BUY").sum() == (df["dir"] == "SELL").sum()
    sym = b26.gross_symmetry(df)
    assert sym["clean_pairs"] > 1000 and sym["mirror_share"] == 1.0                    # on mid prices BUY wins iff SELL loses
    for dn in ("BUY", "SELL"):
        s = df[(df["dir"] == dn) & df["in_seq_ENG"]].sort_values("dec_i")
        assert (s["dec_i"].to_numpy()[1:] >= s["exit_bar"].to_numpy()[:-1]).all()      # never overlapping
    eng = df[df["outcome"] == "TP"]
    assert np.allclose(eng["net_usd_oz"], 15.0 - eng["commission"])                    # target: no exit slippage
    sl = df[df["outcome"] == "SL"]
    assert (sl["net_usd_oz"] <= -15.0 - sl["slip_out"] - sl["commission"] + 1e-9).all()
    done = df[df["outcome"] != "OPEN"]                                                 # OPEN = the data ended first
    assert np.allclose(done["gross_usd_oz"] - done["cost_usd_oz"], done["net_usd_oz"])
    res = b26.summarize(df)
    a = res["all_bar"]["GROSS BUY"]["execution"]["tp_first"] + res["all_bar"]["GROSS SELL"]["execution"]["tp_first"]
    assert a <= 1.0 + 1e-9
    assert res["sequential"]["ENG BUY"]["profitability"]["longest_losing_run"] >= 1


def test_development_scaling_reports_4000_equivalent_dollars():
    pop = _pop(scale=True)
    pop["bars"] = pop["bars"] / 2.0                                                    # gold at ~2000: k ~ 0.5
    pop["h1"] = pop["h1"] / 2.0
    df = b26.run_population("T", pop, log=lambda *_: None)
    r = df[df["outcome"] == "TP"].iloc[0]
    assert r["k"] == pytest.approx(r["decision_px"] / 4000.0)
    assert abs(r["tp_px"] - r["fill_px"]) == pytest.approx(15.0 * r["k"])
    assert r["net_usd_oz"] == pytest.approx(15.0 - 0.07)                                # 4000-equivalent


def test_cluster_interval_is_seeded():
    x = np.r_[np.ones(60), np.zeros(40)]
    day = np.repeat(np.arange(20), 5)
    assert b26.cluster_ci(x, day) == b26.cluster_ci(x, day)
