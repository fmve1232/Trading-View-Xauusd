"""Calendar, DST and trading-session state for every bar.

DELIBERATE DIFFERENCE FROM PINE (D-02). The Pine Master derives DST from the calendar by
hand. Its EU rule keeps a running max over the Sundays seen so far, so in a year whose last
March Sunday falls after the 25th it switches to summer time on the 25th, up to four days
early (and the same in October). US DST also switches at 00:00 UTC rather than 02:00 local.
Session windows feed sessionQuality, which gates entries, so the error is not cosmetic. Here
the IANA database (zoneinfo) decides, which is exact.

Trading day: the NY 17:00 rollover used by the Master's PDH/PDL (crossedNYDay). A bar
belongs to the trading date of (its open time in New York + 7 hours).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NY = "America/New_York"
LON = "Europe/London"


def calendar(index: pd.DatetimeIndex) -> pd.DataFrame:
    """Per-bar calendar and session flags. `index` = bar OPEN times, tz-aware UTC."""
    if index.tz is None:
        index = index.tz_localize("UTC")
    utc = index.tz_convert("UTC")
    ny = utc.tz_convert(NY)
    lon = utc.tz_convert(LON)

    trading_dt = (ny + pd.Timedelta(hours=7))
    trading_date = trading_dt.normalize().tz_localize(None)
    tdate = pd.Series(trading_date, index=index)

    us_dst = np.array([bool(t.dst()) for t in ny], dtype=bool)
    eu_dst = np.array([bool(t.dst()) for t in lon], dtype=bool)

    hour = utc.hour.to_numpy()
    minute = utc.minute.to_numpy()
    # Pine dayofweek: 1 = Sunday .. 7 = Saturday
    dow = ((utc.dayofweek.to_numpy() + 1) % 7) + 1
    dom = utc.day.to_numpy()

    london_open = 7
    london_close = np.where(eu_dst, 16, 17)
    ny_open = np.where(us_dst, 14, 15)
    ny_close = np.where(us_dst, 20, 21)
    in_asian = (hour >= 0) & (hour < london_open)
    in_london = (hour >= london_open) & (hour < london_close)
    in_ny = (hour >= ny_open) & (hour < ny_close)
    eff_london_open = np.where(eu_dst, 7, 8)
    in_london_kz = (hour >= eff_london_open + 1) & (hour < eff_london_open + 4)
    in_london_fix_kz = (hour >= eff_london_open + 3) & (hour < eff_london_open + 4)
    in_ny_kz = (hour >= ny_open) & (hour < ny_open + 3)
    in_london_close_kz = (hour >= london_close - 1) & (hour < london_close)
    in_killzone = in_london_kz | in_ny_kz | in_london_close_kz | in_london_fix_kz

    td = tdate.to_numpy()
    crossed_day = np.zeros(len(index), dtype=bool)
    crossed_day[1:] = td[1:] != td[:-1]
    iso = tdate.dt.isocalendar()
    wk = (iso["year"].astype(int) * 100 + iso["week"].astype(int)).to_numpy()
    crossed_week = np.zeros(len(index), dtype=bool)
    crossed_week[1:] = crossed_day[1:] & (wk[1:] != wk[:-1])
    mkey = (tdate.dt.year * 100 + tdate.dt.month).to_numpy()
    crossed_month = np.zeros(len(index), dtype=bool)
    crossed_month[1:] = mkey[1:] != mkey[:-1]

    # Q5.1-A news windows (NFP = first Friday, CPI = day 10-15 weekday), 12:15-14:00 UTC.
    tm = hour * 60 + minute
    news_nfp = (dow == 6) & (dom <= 7)
    news_cpi = (dom >= 10) & (dom <= 15) & (dow >= 2) & (dow <= 6)
    news_window = (news_nfp | news_cpi) & (tm >= 735) & (tm <= 840)

    return pd.DataFrame(
        {
            "hour": hour,
            "dow": dow,
            "dom": dom,
            "us_dst": us_dst,
            "eu_dst": eu_dst,
            "in_asian": in_asian,
            "in_london": in_london,
            "in_ny": in_ny,
            "in_london_kz": in_london_kz,
            "in_london_fix_kz": in_london_fix_kz,
            "in_ny_kz": in_ny_kz,
            "in_london_close_kz": in_london_close_kz,
            "in_killzone": in_killzone,
            "trading_date": trading_date,
            "crossed_day": crossed_day,
            "crossed_week": crossed_week,
            "crossed_month": crossed_month,
            "month_key": mkey,
            "news_window": news_window,
        },
        index=index,
    )
