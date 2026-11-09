"""Phase D amendment A1 (quantum/research/d_clock.py) on SYNTHETIC data: the checks that go beyond B5c's lag-0 gate must
catch what that gate cannot (a clock wrong for a few weeks; a few minutes; against the broker; ticks out of order),
and pass aligned data. Nothing is ever shifted: failing weeks are quarantined or the run stops."""
import lzma

import numpy as np
import pandas as pd

from quantum.research import b5c_dukascopy as C
from quantum.research import d_clock as K
from quantum.research import d_dukascopy as D
from quantum.research import harness as H


def _minutes(weeks=20, seed=3):
    """One-minute mid path on weekdays, the spot 15-minute bars built from it (close = the bar's last minute close)."""
    g = H.seeded_rng(seed)
    idx = pd.date_range("2021-01-04", periods=weeks * 7 * 1440, freq="1min", tz="UTC")
    idx = idx[idx.day_of_week < 5]
    mid = 1800 + np.cumsum(g.normal(0, 0.25, len(idx)))
    m1 = pd.DataFrame({"bid_c": (mid - 0.15) * 1000, "ask_c": (mid + 0.15) * 1000}, index=idx)
    s = pd.Series(mid, index=idx)
    m15 = pd.DataFrame({"open": s.resample("15min").first(), "close": s.resample("15min").last()}).dropna()
    raw = pd.DataFrame({"mid_last": m15["close"] * 1000, "n": 30.0}, index=m15.index)
    return m1, m15, raw


def test_aligned_data_pass_every_check():
    m1, m15, raw = _minutes()
    dext = pd.DataFrame({"ms_backwards": 0.0}, index=raw.index)
    rep = K.audit(raw, dext, m1, m15, 1000.0)
    assert rep["failures"] == [] and rep["weekly"]["misaligned_weeks"] == [] and 0 in rep["minute"]["tied_best"]
    assert rep["weekly"]["weeks_checked"] >= 19 and rep["ticks_order"]["pass"]


def test_a_clock_wrong_for_a_few_weeks_is_caught_by_the_weekly_check():
    _, m15, raw = _minutes(weeks=60)
    bad = raw.copy()
    wk = K._week(pd.DatetimeIndex(bad.index))
    sel = np.isin(wk, ["2021-W10", "2021-W11", "2021-W30"])
    bad.loc[sel, "mid_last"] = bad["mid_last"].shift(2)[sel]                  # two bars late in three weeks
    w = K.weekly_lags(bad, m15, 1000.0)
    assert set(w["misaligned_weeks"]) == {"2021-W10", "2021-W11", "2021-W30"} and not w["pass"]   # 3 / 60 > 2%
    one = raw.copy()
    one.loc[wk == "2021-W30", "mid_last"] = one["mid_last"].shift(2)[wk == "2021-W30"]
    w1 = K.weekly_lags(one, m15, 1000.0)
    assert w1["pass"] and w1["misaligned_weeks"] == ["2021-W30"]               # quarantined, not shifted
    q = K.quarantine_weeks(one, w1["misaligned_weeks"])
    assert q.loc[wk == "2021-W30"].isna().all().all() and (q.loc[wk != "2021-W30", "mid_last"] == one.loc[wk != "2021-W30", "mid_last"]).all()


def test_a_few_minutes_of_clock_error_is_caught_by_the_minute_check():
    m1, m15, _ = _minutes()
    ok = K.minute_offsets(m1, m15, 1000.0)
    late = m1.copy()
    late.index = late.index + pd.Timedelta(minutes=3)                         # Dukascopy three minutes late
    r = K.minute_offsets(late, m15, 1000.0)
    assert ok["pass"] and not r["pass"] and r["best_offset_min"] == 3 and 0 not in r["tied_best"]
    sp = K.minute_offsets(m1.iloc[::2], m15, 1000.0)                          # a quote every 2 minutes: 0 still among the best
    assert sp["pass"] and 0 in sp["tied_best"]
    # the 15-minute lag gate (B5c A1) cannot see it: bar-level changes still peak at lag 0
    late_raw = pd.DataFrame({"mid_last": ((late["bid_c"] + late["ask_c"]) / 2).resample("15min").last()}).dropna()
    assert C.lag_check(late_raw, m15, 1000.0)["best_lag_bars"] == 0


def test_the_mt5_cross_check_catches_a_broker_clock_offset():
    m1, _, _ = _minutes(weeks=4)
    g = H.seeded_rng(9)
    mt5 = pd.DataFrame({"close": m1["bid_c"] / 1000 + g.normal(0, 0.02, len(m1))}, index=m1.index)
    assert K.mt5_cross(m1, mt5, 1000.0)["pass"]
    off = mt5.copy()
    off.index = off.index - pd.Timedelta(minutes=2)
    r = K.mt5_cross(m1, off, 1000.0)
    assert not r["pass"] and r["best_lag_min"] != 0


def test_ticks_running_backwards_are_counted_and_gated():
    rows = [(1_000, 1010, 1000, 1, 1), (5_000, 1011, 1001, 1, 1), (3_000, 1012, 1002, 1, 1), (950_000, 1012, 1002, 1, 1)]
    raw = lzma.compress(b"".join(C.REC.pack(*r) for r in rows), format=lzma.FORMAT_ALONE)
    s = D.pd_sums(C.parse_bi5(raw), pd.Timestamp("2021-03-01 10:00", tz="UTC"))
    assert s["ms_backwards"].tolist() == [1.0, 0.0]
    b = K.backwards_share(pd.DataFrame({"n": [3.0, 1.0]}), s)
    assert b["share"] == 0.25 and not b["pass"]
