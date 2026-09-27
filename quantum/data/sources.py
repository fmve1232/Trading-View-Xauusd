"""Free market-data fetchers. No paid feed, no account required (Twelve Data is optional).

Every fetcher returns a DataFrame indexed by bar OPEN time (tz-aware UTC) with float
columns open/high/low/close/volume, or raises FetchError with a reason that ends up in the
site's data-status panel. Nothing here is silently substituted: the caller records which
source actually served each series.

Sources
  Yahoo Finance chart API   intraday OHLCV (5m/15m: last 60 days, 60m: last 730 days, 1d: all)
  Twelve Data (optional)    XAU/USD spot intraday; needs a free API key in TWELVEDATA_API_KEY
  FRED (fredgraph.csv)      daily US 2Y (DGS2) and 10Y real yield (DFII10), no key
  CFTC Public Reporting     weekly Commitments of Traders, gold (088691), no key
"""
from __future__ import annotations

import io
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

try:
    import requests
except ImportError:  # pragma: no cover - requests is in requirements.txt
    requests = None

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) quantum-xauusd/1.0 (+github pages research site)"}
COLS = ["open", "high", "low", "close", "volume"]


class FetchError(RuntimeError):
    pass


def _get(url: str, params: dict | None = None, timeout: int = 30, tries: int = 4) -> "requests.Response":
    if requests is None:
        raise FetchError("python 'requests' is not installed")
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
            if r.status_code in (400, 401, 403, 404):
                break
        except Exception as e:  # network error: retry with backoff
            last = f"{type(e).__name__}: {e}"
        time.sleep(2 ** i)
    raise FetchError(f"{url} -> {last}")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=COLS, index=pd.DatetimeIndex([], tz="UTC"), dtype=float)


def yahoo(symbol: str, interval: str, rng: str) -> pd.DataFrame:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": interval, "range": rng, "includePrePost": "true", "events": "div,splits"}
    r = _get(url, params)
    j = r.json()
    res = (j.get("chart") or {}).get("result")
    if not res:
        err = (j.get("chart") or {}).get("error")
        raise FetchError(f"yahoo {symbol} {interval}: {err}")
    res = res[0]
    ts = res.get("timestamp") or []
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    if not ts:
        raise FetchError(f"yahoo {symbol} {interval}: no bars")
    df = pd.DataFrame({c: q.get(c) for c in COLS}, index=pd.to_datetime(ts, unit="s", utc=True))
    df = df.astype(float)
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    if interval in ("1d", "1wk", "1mo"):
        df.index = df.index.normalize()
    return df


def twelvedata(symbol: str, interval: str, apikey: str, outputsize: int = 5000) -> pd.DataFrame:
    url = "https://api.twelvedata.com/time_series"
    params = {"symbol": symbol, "interval": interval, "outputsize": outputsize,
              "timezone": "UTC", "apikey": apikey, "order": "ASC"}
    j = _get(url, params).json()
    if j.get("status") != "ok":
        raise FetchError(f"twelvedata {symbol} {interval}: {j.get('message', j.get('status'))}")
    vals = j.get("values") or []
    if not vals:
        raise FetchError(f"twelvedata {symbol}: no bars")
    df = pd.DataFrame(vals)
    df.index = pd.to_datetime(df.pop("datetime"), utc=True)
    for c in COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce") if c in df else np.nan
    return df[COLS].sort_index()


def fred(series_id: str) -> pd.Series:
    """Daily FRED series, indexed by observation date (UTC midnight)."""
    r = _get("https://fred.stlouisfed.org/graph/fredgraph.csv", {"id": series_id})
    df = pd.read_csv(io.StringIO(r.text))
    date_col = df.columns[0]
    s = pd.to_numeric(df[series_id], errors="coerce")
    s.index = pd.to_datetime(df[date_col], utc=True)
    return s.dropna()


def cftc_gold_cot() -> pd.DataFrame:
    """Legacy futures-only COT for COMEX gold (088691).

    Indexed by the time the report became PUBLIC (Friday 15:30 New York), not by its
    Tuesday as-of date. TradingView's COT feed is keyed on the as-of date, which lets a
    backtest see positions three days before anyone could; aligning on release time
    removes that look-ahead.
    """
    url = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
    params = {"cftc_contract_market_code": "088691", "$order": "report_date_as_yyyy_mm_dd",
              "$limit": 5000}
    rows = _get(url, params).json()
    if not rows:
        raise FetchError("cftc: no rows")
    df = pd.DataFrame(rows)
    asof = pd.to_datetime(df["report_date_as_yyyy_mm_dd"]).dt.tz_localize(None)
    release_local = (asof + pd.Timedelta(days=3) + pd.Timedelta(hours=15, minutes=30))
    release = release_local.dt.tz_localize("America/New_York").dt.tz_convert("UTC")
    out = pd.DataFrame({
        "nc_long": pd.to_numeric(df["noncomm_positions_long_all"], errors="coerce"),
        "nc_short": pd.to_numeric(df["noncomm_positions_short_all"], errors="coerce"),
        "open_interest": pd.to_numeric(df["open_interest_all"], errors="coerce"),
        "asof": asof,
    })
    out.index = pd.DatetimeIndex(release)
    return out.sort_index()


def resample_ohlc(df: pd.DataFrame, rule: str, offset: str | None = None) -> pd.DataFrame:
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    kw = {"label": "left", "closed": "left"}
    if offset:
        kw["offset"] = offset
    out = df.resample(rule, **kw).agg(agg)
    return out.dropna(subset=["open", "high", "low", "close"])


def resample_ny_session(df: pd.DataFrame, hours: int) -> pd.DataFrame:
    """N-hour bars aligned to the 17:00 New York session start, as TradingView aligns FX.

    Buckets are taken on New York WALL-CLOCK time, so the grid stays on 17:00 / 21:00 / 01:00 ...
    through every DST change. (A fixed-frequency resample drifts by an hour across DST, and two
    series that start in different seasons land on different grids.)
    """
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    if len(df) == 0:
        return df
    wall = (df.index.tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7))
    bucket = wall.floor(f"{hours}h")
    out = df.groupby(bucket.values).agg(agg)
    out = out.dropna(subset=["open", "high", "low", "close"])
    lab = pd.DatetimeIndex(out.index) - pd.Timedelta(hours=7)
    lab = lab.tz_localize("America/New_York", ambiguous=np.zeros(len(lab), dtype=bool), nonexistent="shift_forward")
    out.index = lab.tz_convert("UTC")
    return out[~out.index.duplicated(keep="last")].sort_index()


def daily_ny_session(df: pd.DataFrame) -> pd.DataFrame:
    """Daily bars on the NY 17:00 trading day, indexed by the session OPEN time (UTC)."""
    ny = df.tz_convert("America/New_York")
    key = (ny.index + pd.Timedelta(hours=7)).normalize()
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    g = df.groupby(key.tz_localize(None).values).agg(agg)
    start = [ts.tz_localize("America/New_York") - pd.Timedelta(hours=7) for ts in pd.to_datetime(g.index)]
    g.index = pd.DatetimeIndex(start).tz_convert("UTC")
    return g.dropna(subset=["open", "high", "low", "close"])


def trading_week_only(df: pd.DataFrame | None, daily: bool = False) -> pd.DataFrame | None:
    """Drop bars printed while the market is shut (Friday 17:00 -> Sunday 17:00 New York).

    Twelve Data's free XAU/USD feed prints flat quotes 24/7. On a live week those weekend
    bars were ~30% of a 15-minute chart: they shrank the ATR, created fake Saturday/Sunday
    "days" for PDH/PDL, carried no volume (blank VWAP) and drove the return volatility to
    near zero. TradingView's OANDA feed has no weekend bars, so they also broke parity.
    Daily bars dated Saturday or Sunday are dropped for the same reason.
    """
    if df is None or len(df) == 0:
        return df
    if daily:
        return df[df.index.dayofweek < 5]
    ny = df.index.tz_convert("America/New_York")
    wd, hr = ny.dayofweek, ny.hour
    shut = (wd == 5) | ((wd == 4) & (hr >= 17)) | ((wd == 6) & (hr < 17))
    return df[~shut]


def drop_incomplete(df: pd.DataFrame, bar_sec: int, now: datetime | None = None) -> tuple[pd.DataFrame, pd.Series | None]:
    """Split off a still-forming last bar. The engine only reads CONFIRMED bars."""
    if df.empty:
        return df, None
    now = now or datetime.now(timezone.utc)
    last_open = df.index[-1].to_pydatetime()
    if last_open + timedelta(seconds=bar_sec) > now:
        return df.iloc[:-1], df.iloc[-1]
    return df, None
