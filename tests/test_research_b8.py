"""Phase B8 (quantum/research/b8_news.py): release instants follow New York time through daylight saving, the event
lists are complete for the development window, and the reaction direction uses only bars up to the entry."""
import numpy as np
import pandas as pd

from quantum.research import b8_news as B


def test_release_times_follow_new_york_daylight_saving():
    assert str(B.release_utc("CPI", "2022-07-13")) == "2022-07-13 12:30:00+00:00"      # EDT
    assert str(B.release_utc("NFP", "2022-12-02")) == "2022-12-02 13:30:00+00:00"      # EST
    assert str(B.release_utc("FOMC", "2021-03-17")) == "2021-03-17 18:00:00+00:00"


def test_event_lists_cover_the_development_window():
    assert (len(B.DATES["CPI"]), len(B.DATES["NFP"]), len(B.DATES["FOMC"])) == (36, 36, 23)
    for k, ds in B.DATES.items():
        assert ds == sorted(ds) and len(set(ds)) == len(ds)
        assert all("2020-01-24" <= d <= "2023-01-24" for d in ds), k
        assert all(pd.Timestamp(d).dayofweek < 5 for d in ds), k
    assert "2020-03-15" not in B.DATES["FOMC"] and "2020-03-03" not in B.DATES["FOMC"]     # unscheduled moves excluded


def test_reaction_direction_uses_only_bars_up_to_the_entry():
    idx = pd.date_range("2022-07-13 11:00", periods=12, freq="15min", tz="UTC")
    c = np.array([1800, 1800, 1800, 1800, 1800, 1800, 1790, 1795, 1780, 1700, 1600, 1500], float)  # 12:30 bar is index 6
    o = np.r_[1800, c[:-1]]
    m15 = pd.DataFrame({"open": o, "high": np.maximum(o, c) + 1, "low": np.minimum(o, c) - 1, "close": c}, index=idx)
    old = B.DATES["CPI"]
    try:
        B.DATES["CPI"] = ["2022-07-13"]
        ev = B.event_bars(m15, "CPI")[0]
    finally:
        B.DATES["CPI"] = old
    assert ev["k"] == 6 and ev["d15"] == -1.0 and ev["d30"] == -1.0      # 1800 -> 1790 (W15), 1800 -> 1795 (W30)
    m15.iloc[9:, :] = m15.iloc[9:, :] + 500                                 # later bars cannot change the direction
    B.DATES["CPI"] = ["2022-07-13"]
    try:
        assert B.event_bars(m15, "CPI")[0]["d15"] == -1.0
    finally:
        B.DATES["CPI"] = old
