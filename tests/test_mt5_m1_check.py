"""research/tools/mt5_m1_check.py on a synthetic MT5 export: parsing, server time -> UTC, integrity, and the clock check."""
import io
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "research", "tools"))
import mt5_m1_check as M


def _export(utc_idx, close, server_offset_h=2):
    st = utc_idx.tz_convert(None) + pd.Timedelta(hours=server_offset_h)
    o = np.r_[close[0], close[:-1]]
    df = pd.DataFrame({"<DATE>": st.strftime("%Y.%m.%d"), "<TIME>": st.strftime("%H:%M:%S"), "<OPEN>": o,
                       "<HIGH>": np.maximum(o, close) + 0.1, "<LOW>": np.minimum(o, close) - 0.1, "<CLOSE>": close,
                       "<TICKVOL>": 10, "<VOL>": 0, "<SPREAD>": 25})
    return io.StringIO(df.to_csv(sep="\t", index=False))


def test_parse_convert_integrity_and_clock():
    idx = pd.date_range("2024-01-08", "2024-01-20", freq="1min", tz="UTC", inclusive="left")
    idx = idx[idx.day_of_week < 5]
    g = np.random.default_rng(4)
    close = 2000 + np.cumsum(g.normal(0, 0.3, len(idx)))
    raw = M.read_export(_export(idx, close))
    rep = M.integrity(raw)
    assert rep["rows"] == len(idx) and rep["duplicates"] == 0 and rep["bad_ohlc"] == 0 and rep["gaps_weekend_or_holiday"] == 1
    ref = pd.Series(close, index=idx).resample("15min", label="left", closed="left").last().dropna()
    good = M.to_utc(raw, offset_hours=2)
    assert good.index[0] == idx[0]
    ck = M.clock_check(good, ref)
    assert ck["aligned"] and ck["best_shift_hours"] == 0 and ck["median_abs_close_gap"] < 1e-9
    wrong = M.to_utc(raw, offset_hours=0)                    # the server offset forgotten
    ck2 = M.clock_check(wrong, ref)
    assert not ck2["aligned"] and ck2["best_shift_hours"] == -2


def test_rejects_a_non_export_and_bad_bars():
    try:
        M.read_export(io.StringIO("a\tb\n1\t2\n"))
        raise AssertionError("must refuse")
    except ValueError:
        pass
    idx = pd.date_range("2024-01-08", periods=500, freq="1min", tz="UTC")
    close = np.full(500, 2000.0)
    buf = _export(idx, close)
    raw = M.read_export(buf)
    raw.iloc[10, raw.columns.get_loc("low")] = 2100.0         # low above the close
    assert M.integrity(raw)["bad_ohlc"] == 1
