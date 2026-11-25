"""B31b-W12 study code: hand-worked checks of the session clock, the run, the POC, the race, net R and the controls."""
import math
from datetime import datetime, timezone

import numpy as np
import pytest

from quantum.research import harness as H
from quantum.research import w12session as Z


def ts(s):
    return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp())


@pytest.mark.parametrize("when,name,mins", [
    ("2026-11-25T07:50", "LONDON_OPEN", -10.0),     # winter: 08:00 London = 08:00 UTC
    ("2026-07-15T07:10", "LONDON_OPEN", 10.0),      # summer: 08:00 London = 07:00 UTC
    ("2026-11-25T13:00", "NY_OPEN", -30.0),         # winter: 08:30 New York = 13:30 UTC
    ("2026-07-15T12:45", "NY_OPEN", 15.0),          # summer: 08:30 New York = 12:30 UTC
    ("2026-11-25T16:15", "LONDON_CLOSE", -15.0),    # 16:30 London = 16:30 UTC in winter
    ("2026-11-25T21:45", "NY_CLOSE", -15.0),        # 17:00 New York = 22:00 UTC in winter
    ("2026-11-26T00:20", "ASIA_OPEN", 20.0),
])
def test_nearest_boundary(when, name, mins):
    assert Z.nearest_boundary(ts(when)) == (name, mins)


def test_pre_run_in_atr():
    c = np.array([100.0, 101, 102, 103, 104, 103])
    h = c + 1
    l = c - 1
    atr = np.full(6, 2.0)
    # sweep bar 5 on the buy side: its high 104 minus the close 4 bars earlier (101) = 3 -> 1.5 ATR
    assert Z.pre_run(h, l, c, atr, 5, 1) == pytest.approx(1.5)
    # sell side: (low 102 - 101) x -1 = -0.5 ATR (the run went the other way)
    assert Z.pre_run(h, l, c, atr, 5, -1) == pytest.approx(-0.5)
    assert math.isnan(Z.pre_run(h, l, c, atr, 3, 1))


def test_tpo_poc_time_at_price():
    # three bars: 10-12, 11-12, 11-11.9 with $1 bins -> bin 11 holds 0.5 + 0.5 + 1.0 = 2.0, the fullest
    assert Z.tpo_poc(np.array([10.0, 11.0, 11.0]), np.array([12.0, 12.0, 11.9]), 1.0) == pytest.approx(11.5)


def test_trend_uses_only_closed_h1_bars():
    th = np.arange(60, dtype=np.int64) * 3600
    e20 = np.r_[np.zeros(59), 2.0]                  # the last bar (still forming at t_close) flips the trend up
    e50 = np.ones(60)
    t_close = int(th[59]) + 1800                    # inside bar 59: only bar 58 has closed
    assert Z.trend_agrees(th, e20, e50, t_close, 1) is False
    assert Z.trend_agrees(th, e20, e50, t_close, -1) is True
    assert Z.trend_agrees(th, e20, e50, int(th[59]) + 3600, 1) is True    # once bar 59 has closed


def path(rows):
    t, o, h, l, c = (np.array(x) for x in zip(*rows))
    return {"t": t.astype(np.int64), "o": o, "h": h, "l": l, "c": c}


def test_race_target_first_stop_first_both_and_gap():
    fp = path([(300, 4000, 4011, 3999, 4010), (600, 4010, 4016, 4005, 4015), (900, 4015, 4021, 4014, 4020)])
    # buy at 4000, stop 3990: +10 on bar 1, +15 on bar 2, +20 on bar 3
    res = Z.race(fp, 300, 4000, 3990, 1, (4010, 4015, 4020))
    assert [r[0] for r in res] == ["TP", "TP", "TP"] and [r[1] for r in res] == [300, 600, 900]
    # a bar touching both the target and the stop is the stop
    fp2 = path([(300, 4000, 4012, 3989, 4001)])
    assert Z.race(fp2, 300, 4000, 3990, 1, (4010,))[0][0] == "SL"
    # a gap through the stop fills at the open
    fp3 = path([(300, 3980, 3985, 3975, 3982)])
    assert Z.race(fp3, 300, 4000, 3990, 1, (4010,))[0] == ("SL", 300, 3980.0)
    # nothing hit in 24 h: time stop at the last close
    fp4 = path([(300, 4000, 4005, 3995, 4002)])
    assert Z.race(fp4, 300, 4000, 3990, 1, (4010,))[0] == ("TO", 300, 4002.0)
    assert Z.race(fp4, 10 ** 9, 4000, 3990, 1, (4010,))[0] == ("NONE",)


def test_net_r_at_4000():
    # entry 4000 (s = 1), stop 10 away, cost 0.77
    assert Z.net_r(("TP", 0), 10, 4000, 10, 0.77, 1) == pytest.approx((10 - 0.77) / 10.77)
    assert Z.net_r(("SL", 0, 3990.0), 10, 4000, 10, 0.77, 1) == pytest.approx(-1.0)
    assert Z.net_r(("SL", 0, 3980.0), 10, 4000, 10, 0.77, 1) == pytest.approx(-(20 + 0.77) / 10.77)    # gap loss
    assert Z.net_r(("TO", 0, 4005.0), 10, 4000, 10, 0.77, 1) == pytest.approx((5 - 0.77) / 10.77)
    # at entry 2000 the $ at $4,000 scale halves the bar distances: a 5-dollar real stop is D = 10
    assert Z.net_r(("SL", 0, 1995.0), 10, 2000, 10, 0.77, 1) == pytest.approx(-1.0)


def test_holm_and_select():
    hp = Z.holm({"a": 0.01, "b": 0.04, "c": 0.5})
    assert hp == {"a": pytest.approx(0.03), "b": pytest.approx(0.08), "c": pytest.approx(0.5)}
    rows = [{"id": "1", "H1": True, "c1": True, "c2": False, "c3": None},
            {"id": "2", "H1": True, "c1": True, "c2": True, "c3": True},
            {"id": "3", "H1": False, "c1": True, "c2": True, "c3": True}]
    assert [r["id"] for r in Z.select(rows, "H1")] == ["1", "2"]
    assert [r["id"] for r in Z.select(rows, "H1+C3")] == ["2"]            # an unknown dollar move is not a yes
    assert [r["id"] for r in Z.select(rows, "H1+ALL")] == ["2"]


def test_boot_mean_day_clustered():
    m, ci, p = Z.boot_mean(np.array([1.0, 1.0, -1.0, 1.0]), np.array([1, 1, 2, 3]))
    assert m == pytest.approx(0.5) and ci[0] <= m <= ci[1] and 0.0 <= p <= 1.0


def test_only_development():
    with pytest.raises(H.SealedPartition):
        Z.main(["--part", "validation", "--rd", ".", "--cost", "x", "--out", "y"])
