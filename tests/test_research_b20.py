"""B20 (research/registrations/B20.json): the run-continuation features and statistics on hand-built bars."""
import math

import numpy as np
import pandas as pd
import pytest

from quantum.research import b20


def _m15(closes, start="2026-03-03 13:00"):
    idx = pd.date_range(start, periods=len(closes), freq="15min", tz="UTC")
    c = np.asarray(closes, float)
    o = np.concatenate([[c[0]], c[:-1]])
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.5, "low": np.minimum(o, c) - 0.5, "close": c, "volume": 0.0}, index=idx)


def _h1(closes, start="2026-02-20 00:00"):
    idx = pd.date_range(start, periods=len(closes), freq="1h", tz="UTC")
    c = np.asarray(closes, float)
    return pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 0.0}, index=idx)


def test_run_length_and_run_size_count_consecutive_closes_from_the_close_before_the_run():
    m = _m15([4000, 4001, 4005, 4012, 4020, 4018, 4010, 4011])
    F = b20.features(m, _h1(np.linspace(3900, 4000, 400)))
    assert F["d"].tolist() == [0, 1, 1, 1, 1, -1, -1, 1]
    assert F["run_length"].tolist() == [0, 1, 2, 3, 4, 1, 2, 1]
    s = 4020 / 4000
    assert F["run_size"].iloc[4] == pytest.approx((4020 - 4000) / s)             # from the close before the first up candle
    assert F["run_size"].iloc[6] == pytest.approx((4020 - 4010) / (4010 / 4000))  # a down run of two, measured downward


def test_the_1h_trend_uses_only_closed_bars():
    h1 = _h1(np.concatenate([np.linspace(4200, 3900, 300), np.linspace(3900, 4300, 100)]), start="2026-02-17 13:00")
    m = _m15([4000, 4001], start="2026-03-03 13:00")              # 13:15 close: the 12:00 1h bar is the last CLOSED one
    F = b20.features(m, h1)
    ema20, ema100 = (pd.Series(h1["close"]).ewm(span=n, adjust=False).mean() for n in (20, 100))
    j = h1.index.get_loc(pd.Timestamp("2026-03-03 12:00", tz="UTC"))
    assert bool(F["trend_1h_agrees"].iloc[1]) == bool(ema20.iloc[j] > ema100.iloc[j])
    h1b = h1.copy()
    h1b.loc[h1b.index > pd.Timestamp("2026-03-03 12:00", tz="UTC"), "close"] = 1.0          # later 1h bars cannot change it
    assert b20.features(m, h1b)["trend_1h_agrees"].tolist() == F["trend_1h_agrees"].tolist()


def test_body_session_and_day_move():
    m = _m15([4000, 4004, 4010], start="2026-03-03 15:00")       # London + New York overlap (the engine: 15:00-17:00 UTC in winter)
    F = b20.features(m, _h1(np.linspace(3900, 4000, 400)))
    assert set(F["session"]) == {"London + New York"}
    atr = F["last_candle_body"].iloc[2]
    assert atr > 0
    first_open = m["open"].iloc[0]                                 # same New York trading day
    assert F["day_move"].iloc[2] == pytest.approx((4010 - first_open) / (4010 / 4000))


def test_bins():
    assert b20.bin_of(np.array([1, 2, 6, 9]), "run_length").tolist() == ["1", "2", "6+", "6+"]
    assert b20.bin_of(np.array([4.9, 5.0, 15.0, 19.99, 30.0, np.nan]), "run_size").tolist() == ["<5", "5-10", "15-20", "15-20", ">=30", ""]
    assert b20.bin_of(np.array([-3.0, 0.0, 40.0]), "day_move").tolist() == ["<0", "0-10", ">=40"]


def test_day_clustered_statistics_and_holm():
    w = np.array([1, 1, 1, 0, 0, 1, 0, 1], bool)
    base = np.full(8, 0.5)
    day = np.array([1, 1, 2, 2, 3, 3, 4, 4])
    m, se, p = b20.clustered(w, base, day)
    x = w - 0.5
    g = pd.Series(x - x.mean()).groupby(day).sum().to_numpy()
    assert m == pytest.approx(x.mean()) and se == pytest.approx(math.sqrt((g ** 2).sum()) / 8) and 0 < p < 1
    adj = b20.holm_adjusted({"a": 0.01, "b": 0.04, "c": 0.03, "d": math.nan})
    assert adj["a"] == pytest.approx(0.04) and adj["c"] == pytest.approx(0.09) and adj["b"] == pytest.approx(0.09) and adj["d"] == 1.0


def test_table_reports_rate_base_and_net_after_cost():
    m = _m15([4000, 4001, 4002, 4003])
    F = b20.features(m, _h1(np.linspace(3900, 4000, 400)))
    r = {"win": np.array([False, True, False, True]), "loss": np.array([False, False, True, False])}
    t = b20.table(F, r, 0.46, 0.46, np.full(4, 0.77), 15.0, np.ones(4, bool))
    assert t["n"] == 3 and t["rate"] == pytest.approx(2 / 3) and t["base"] == pytest.approx(0.46)
    assert t["mean_net_usd_per_oz"] == pytest.approx((15 + 15 - 13) / 3 - 0.77)
    assert t["break_even"] == pytest.approx((13 + 0.77) / 28)
