"""B13 (research/registrations/B13.json): the generalised barrier race and the clock-rule decision times."""
import numpy as np
import pandas as pd

from quantum import ta
from quantum.research import b10, b13


def _bars(prices_hlo, start="2021-03-01 14:00"):
    idx = pd.date_range(start, periods=len(prices_hlo), freq="15min", tz="UTC")
    o, h, l = zip(*[(x[2], x[0], x[1]) for x in prices_hlo])
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": o, "volume": 0.0}, index=idx)


def test_race_win_loss_tie_and_scaling():
    # entry 4000 at the close of a bar before the path; T15 / S13 unscaled at $4,000
    path = _bars([(4005, 3995, 4000), (4016, 4000, 4005)] + [(4001, 3999, 4000)] * 100)
    t0 = int(ta.epoch_s(path.index)[0])
    r = b13.race(path, np.array([t0]), np.array([4000.0]), np.array([1]), 15, 13)
    assert r["win"][0] and not r["loss"][0] and r["k"][0] == 1
    r = b13.race(path, np.array([t0]), np.array([4000.0]), np.array([-1]), 15, 13)
    assert r["loss"][0] and r["k"][0] == 1                       # +16 above a short entry: stopped at +13
    # a bar reaching both is a loss unless it opened beyond the target
    both = _bars([(4020, 3980, 4000)] + [(4001, 3999, 4000)] * 100)
    t0 = int(ta.epoch_s(both.index)[0])
    r = b13.race(both, np.array([t0]), np.array([4000.0]), np.array([1]), 15, 13)
    assert r["loss"][0] and r["tie"][0]
    gap = _bars([(4020, 3980, 4016)] + [(4001, 3999, 4000)] * 100)
    r = b13.race(gap, np.array([t0]), np.array([4000.0]), np.array([1]), 15, 13)
    assert r["win"][0] and not r["tie"][0]
    # at $2,000 the distances halve: +7.5 / -6.5
    half = _bars([(2008, 1999, 2000)] + [(2001, 1999, 2000)] * 100)
    r = b13.race(half, np.array([t0]), np.array([2000.0]), np.array([1]), 15, 13)
    assert r["win"][0]
    # a window end before the move: OPEN
    r = b13.race(path, np.array([int(ta.epoch_s(path.index)[0])]), np.array([4000.0]), np.array([1]), 15, 13,
                 end_t=np.array([int(ta.epoch_s(path.index)[1])]))
    assert not r["win"][0] and not r["loss"][0] and r["ok"][0]


def test_race_matches_b10_at_13_13():
    g = np.random.default_rng(3)
    n = 3000
    c = 4000 + np.cumsum(g.normal(0, 2.0, n))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + g.exponential(1.0, n)
    l = np.minimum(o, c) - g.exponential(1.0, n)
    idx = pd.date_range("2021-03-01", periods=n, freq="15min", tz="UTC")
    path = pd.DataFrame({"open": o, "high": h, "low": l, "close": c}, index=idx)
    rows = np.arange(0, n - 100, 7)
    t_close = ta.epoch_s(idx)[rows] + 900
    d = np.where(g.random(len(rows)) < 0.5, 1, -1)
    a = b13.race(path, t_close, c[rows], d, 13, 13)
    b = b10.outcomes(path, t_close, c[rows], d, np.zeros(len(rows)))
    assert np.array_equal(a["win"], b["win"]) and np.array_equal(a["loss"], b["loss"])


def test_clock_rule_times_across_dst():
    idx = pd.date_range("2021-03-08 00:00", "2021-03-19 00:00", freq="15min", tz="UTC")    # US DST starts 14 Mar
    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": np.arange(len(idx), dtype=float)}, index=idx)
    out = b13.clock_rules(df, np.ones(len(idx), bool))
    ny = lambda i: (idx[i] + pd.Timedelta(minutes=15)).tz_convert("America/New_York").strftime("%H:%M")
    for key, hm in (("B13-2a", "13:30"), ("B13-2b", "08:30"), ("B13-3", "09:00")):
        rows, _d, end_t = out[key]
        assert len(rows) and {ny(i) for i in rows} == {hm}
        ends = {pd.Timestamp(int(e), unit="s", tz="UTC").tz_convert("America/New_York").strftime("%H:%M") for e in end_t}
        assert ends == ({"08:30"} if key == "B13-2a" else {"13:30"})
    assert set(out["B13-2a"][1]) == {1} and set(out["B13-2b"][1]) == {-1} and set(out["B13-3"][1]) == {1}


def test_b14_two_timeframe_break_against_the_gate():
    from quantum.research import b14
    idx15 = pd.date_range("2021-03-02 14:00", periods=8, freq="15min", tz="UTC")
    idx1 = pd.date_range("2021-03-02 14:00", periods=2, freq="1h", tz="UTC")
    c15 = np.array([99.0, 99.5, 101.0, 100.5, 102.0, 103.0, 104.0, 105.0])
    c1 = np.array([100.5, 105.0])                                   # 1h closes beyond 100 only at 16:00
    lv15 = {"pdh": np.full(8, 100.0), "pwh": np.full(8, np.nan), "pdl": np.full(8, 90.0), "pwl": np.full(8, np.nan)}
    lv1 = {"pdh": np.full(2, 100.0), "pwh": np.full(2, np.nan), "pdl": np.full(2, 90.0), "pwl": np.full(2, np.nan)}
    assert [(k, nm, d) for k, nm, _lv, d in b14.breaks(lv15, c15)] == [(2, "PDH", 1)]   # 100.5 after 101: not a new cross
    lv1x = {**lv1, "pdh": np.full(2, 100.5)}                        # a different level on 1h: no match
    F = {"htf_bear_gate": np.ones(8, bool), "htf_bull_gate": np.zeros(8, bool)}
    ev = b14.events(idx15, c15, lv15, F, idx1, np.array([99.0, 101.0]), lv1)
    assert [(e["k"], e["pool"], e["dir"], e["gate_on"]) for e in ev] == [(7, "PDH", 1, True)]   # the 16:00 close
    assert b14.events(idx15, c15, lv15, F, idx1, np.array([99.0, 101.0]), lv1x) == []
    assert b14.events(idx15, c15, lv15, {**F, "htf_bear_gate": np.zeros(8, bool)}, idx1, np.array([99.0, 101.0]), lv1)[0]["gate_on"] is False
    two = [{"day": 1, "dir": 1, "k": 3}, {"day": 1, "dir": 1, "k": 5}, {"day": 1, "dir": -1, "k": 6}, {"day": 2, "dir": 1, "k": 9}]
    assert [e["k"] for e in b14.once_per_day(two)] == [3, 6, 9]
    del c1
