"""report.daily_regime: the developed Pine line's DAILY REGIME tile (Visuals v86 rgTxt), display only. Hand-made daily
bars in the engine's layout (each session opens at New York 17:00 the evening before and lasts 24 h)."""
import numpy as np
import pandas as pd

from quantum import report


def _daily(closes, last_trade_day="2026-11-26"):
    """One bar per weekday trading date ending at last_trade_day, indexed like market.build_market's daily bars."""
    days = pd.bdate_range(end=last_trade_day, periods=len(closes))
    idx = pd.DatetimeIndex([(pd.Timestamp(d) - pd.Timedelta(days=1) + pd.Timedelta(hours=17)).tz_localize("America/New_York")
                            for d in days]).tz_convert("UTC")
    c = np.asarray(closes, float)
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": 0.0}, index=idx)


# 27 Nov 2026 11:30 UTC: the 26 Nov session closed at 17:00 New York (22:00 UTC) on the 26th
ASOF = pd.Timestamp("2026-11-27T11:30:00Z")


def test_long_when_the_year_is_up_and_price_is_above_its_200_day_average():
    r = report.daily_regime(_daily(np.linspace(2000, 4000, 400)), ASOF)
    assert r["label"] == "LONG" and r["ret12"] > 0 and r["close"] > r["sma200"]
    assert r["asof_day"] == "2026-11-26"


def test_short_when_both_are_down_and_flat_when_they_disagree():
    assert report.daily_regime(_daily(np.linspace(4000, 2000, 400)), ASOF)["label"] == "SHORT"
    # up over the year, but the last 60 days fell below the 200-day average
    c = np.r_[np.linspace(2000, 4000, 340), np.linspace(4000, 2500, 60)]
    r = report.daily_regime(_daily(c), ASOF)
    assert r["ret12"] > 0 and r["close"] < r["sma200"] and r["label"] == "FLAT"


def test_no_label_without_thirteen_completed_months_or_200_days():
    r = report.daily_regime(_daily(np.linspace(2000, 4000, 150)), ASOF)
    assert r["label"] is None and r["sma200"] is None and r["ret12"] is None
    assert report.daily_regime(None, ASOF)["label"] is None


def test_completed_bars_only_the_forming_session_and_month_are_ignored():
    """The 27 Nov session (open 26 Nov 17:00 New York) has not closed at ASOF: a crash in it changes nothing; the
    November month-end is not complete either, so the 12-month return runs October to October."""
    base = _daily(np.linspace(2000, 4000, 400))
    forming = _daily(np.r_[np.linspace(2000, 4000, 400), 10.0], last_trade_day="2026-11-27")
    a, b = report.daily_regime(base, ASOF), report.daily_regime(forming, ASOF)
    assert a == b and a["label"] == "LONG"
    m = pd.Series(base["close"].values, index=pd.bdate_range(end="2026-11-26", periods=400))
    oct26, oct25 = m[:"2026-10-31"].iloc[-1], m[:"2025-10-31"].iloc[-1]
    assert a["m1"] == round(oct26, 2) and a["m13"] == round(oct25, 2)
    assert a["sma200"] == round(m.iloc[-200:].mean(), 2)


def test_twenty_day_macro_context_from_the_real_yield_and_the_dollar():
    d1 = _daily(np.linspace(2000, 4000, 400))
    ry = pd.DataFrame({"close": np.linspace(2.0, 1.5, 60)}, index=pd.date_range("2026-09-01", periods=60, freq="D", tz="UTC"))
    hrs = pd.date_range("2026-10-01", "2026-11-27 10:00", freq="h", tz="UTC")
    dxy = pd.DataFrame({"close": np.linspace(106, 103, len(hrs))}, index=hrs)
    r = report.daily_regime(d1, ASOF, ry, dxy)
    assert r["ry20"] < 0 and r["dxy20"] < 0 and r["macro"] == 1          # both falling: supports gold
    r2 = report.daily_regime(d1, ASOF, ry.assign(close=ry["close"][::-1].values), dxy)
    assert r2["ry20"] > 0 and r2["macro"] == 0                            # mixed
