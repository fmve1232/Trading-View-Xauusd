"""Assemble every series the engine reads, aligned to the chart's bars without look-ahead.

ALIGNMENT RULE (one rule for every external series). The engine evaluates a chart bar at its
close, time T. For another series it reads the LAST bar of that series that opened before T,
and from that bar it reads an expression built only from `[1]` values (close[1], ema of
close[1] ...), exactly as the Pine `request.security(..., close[1], lookahead_off)` calls do.
Such an expression is fully known when that bar opens, so nothing from after T can leak in.

DELIBERATE DIFFERENCE FROM PINE (D-01). On HISTORICAL bars TradingView returns a higher-
timeframe value one HTF bar later than it does in real time (the well-known historical/real-
time asymmetry of lookahead_off). This engine applies the real-time behaviour on every bar,
so the backtest and the live signal are computed the same way.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from .. import ta
from ..config import TIMEFRAMES
from . import sources, store

# Yahoo symbols. Pine equivalents in comments.
SYM = {
    "xau_spot": "XAUUSD=X",   # OANDA:XAUUSD (if Yahoo still serves it)
    "gc": "GC=F",             # COMEX:GC1!
    "silver": "SI=F",         # OANDA:XAGUSD (futures proxy)
    "dxy": "DX-Y.NYB",        # TVC:DXY
    "us10y": "^TNX",          # TVC:US10Y
    "eurusd": "EURUSD=X",     # OANDA:EURUSD
    "spx": "^GSPC",           # SP:SPX
    "vix": "^VIX",            # TVC:VIX
}


@dataclass
class SeriesStatus:
    name: str
    source: str = ""
    ok: bool = False
    rows: int = 0
    last: str = ""
    note: str = ""

    def to_dict(self):
        return self.__dict__.copy()


@dataclass
class Market:
    tf: str
    tf_sec: int
    base: pd.DataFrame                       # confirmed chart bars (open time index, UTC)
    forming: pd.Series | None                # the still-forming bar, display only
    htf: dict = field(default_factory=dict)  # "5","15","60","240","D" -> primary OHLCV
    ext_chart: dict = field(default_factory=dict)   # silver/eurusd/spx/gc at chart TF
    ext_macro: dict = field(default_factory=dict)   # dxy/us10y/tips at 1h
    ext_daily: dict = field(default_factory=dict)   # vix/us2y/tips_real daily
    cot: pd.DataFrame | None = None
    status: dict = field(default_factory=dict)
    price_source: str = ""
    volume_source: str = ""
    synthetic: bool = False

    @property
    def close_times(self) -> pd.DatetimeIndex:
        return self.base.index + pd.Timedelta(seconds=self.tf_sec)


def align(chart_close: pd.DatetimeIndex, other: pd.DataFrame, cols: list[str]) -> dict:
    """For each chart bar, the row of `other` = last bar that opened strictly before the
    chart bar's close. Returns {col: np.ndarray} plus `_open` (that bar's open, epoch s)."""
    out = {}
    n = len(chart_close)
    if other is None or len(other) == 0:
        for c in cols:
            out[c] = np.full(n, np.nan)
        out["_open"] = np.full(n, np.nan)
        return out
    oidx = ta.epoch_s(other.index)
    cidx = ta.epoch_s(chart_close)
    k = np.searchsorted(oidx, cidx, side="left") - 1
    valid = k >= 0
    kk = np.where(valid, k, 0)
    for c in cols:
        v = other[c].to_numpy(dtype=float)[kk]
        out[c] = np.where(valid, v, np.nan)
    op = oidx[kk].astype(float)
    out["_open"] = np.where(valid, op, np.nan)
    return out


def htf_expr(df: pd.DataFrame) -> pd.DataFrame:
    """[close[1], ema(close[1],20), ema(close[1],100), ema(close[1],200)] on the HTF series."""
    c1 = ta.shift(df["close"].to_numpy(float), 1)
    return pd.DataFrame({
        "c1": c1,
        "e20": ta.ema(c1, 20),
        "e100": ta.ema(c1, 100),
        "e200": ta.ema(c1, 200),
    }, index=df.index)


# --------------------------------------------------------------------------------------
# Live assembly: ONE download pass per pipeline run, shared by every timeframe.
# --------------------------------------------------------------------------------------

def _fetch_merge(store_dir: str | None, name: str, fn, status: dict) -> pd.DataFrame | None:
    st = SeriesStatus(name=name)
    df = None
    try:
        df = fn()
        st.source = "live"
    except Exception as e:  # noqa: BLE001 - the reason is reported, never swallowed
        st.note = sources.redact(str(e))[:200]
    old = store.load(store_dir, name) if store_dir else None
    if df is not None and len(df):
        df = store.merge(old, df)
        if store_dir:
            store.save(store_dir, name, df)
    elif old is not None and len(old):
        df = old
        st.source = "store (live fetch failed)"
    if df is not None and len(df):
        n0 = len(df)
        df = sources.trading_week_only(df, daily=name.endswith("_1d"))
        st.ok = len(df) > 0
        st.rows = len(df)
        st.last = df.index[-1].isoformat() if len(df) else ""
        if len(df) < n0:
            st.note = (st.note + " " if st.note else "") + f"{n0 - len(df)} market-closed bars dropped"
    status[name] = st
    return df


@dataclass
class Downloads:
    prim: dict            # interval -> DataFrame, all from ONE instrument
    price_source: str
    gc: dict              # interval -> DataFrame
    chart_ext: dict       # (name, interval) -> DataFrame
    macro: dict
    daily: dict
    cot: pd.DataFrame | None
    status: dict


def download_all(store_dir: str | None = None, intervals=("5m", "15m", "60m")) -> Downloads:
    status: dict = {}
    td_key = os.environ.get("TWELVEDATA_API_KEY", "").strip()
    td_int = {"5m": "5min", "15m": "15min", "60m": "1h", "1d": "1day"}
    rng = {"5m": "60d", "15m": "60d", "60m": "730d", "1d": "10y"}

    # PRICE: one instrument for every interval, so PDH/PMH/HTF levels share a price scale.
    # Order: Twelve Data spot (if a key is set) -> Yahoo spot -> Yahoo COMEX futures.
    candidates = []
    if td_key:
        candidates.append(("twelvedata:XAU/USD", lambda i: sources.twelvedata("XAU/USD", td_int[i], td_key)))
    candidates.append((f"yahoo:{SYM['xau_spot']}", lambda i: sources.yahoo(SYM["xau_spot"], i, rng[i])))
    candidates.append((f"yahoo:{SYM['gc']}", lambda i: sources.yahoo(SYM["gc"], i, rng[i])))
    prim, psrc = {}, ""
    for src, fn in candidates:
        sym = src.split(":", 1)[1]
        got = {}
        for i in (*intervals, "1d"):
            d = _fetch_merge(store_dir, f"{sym}_{i}", lambda i=i: fn(i), status)
            if d is not None and len(d) > 50:
                got[i] = d
        if all(i in got for i in intervals):
            prim, psrc = got, src
            break
    if not prim:
        raise sources.FetchError("no XAUUSD price source reachable for every interval: "
                                 + "; ".join(f"{k}: {v.note}" for k, v in status.items() if not v.ok))

    gc = {}
    for i in (*intervals, "1d"):
        gc[i] = prim[i] if "GC=F" in psrc else _fetch_merge(
            store_dir, f"GC=F_{i}", lambda i=i: sources.yahoo(SYM["gc"], i, rng[i]), status)

    chart_ext = {}
    for nm in ("silver", "eurusd", "spx"):
        for i in intervals:
            chart_ext[(nm, i)] = _fetch_merge(store_dir, f"{SYM[nm]}_{i}",
                                              lambda s=SYM[nm], i=i: sources.yahoo(s, i, rng[i]), status)
    macro = {nm: _fetch_merge(store_dir, f"{SYM[nm]}_60m", lambda s=SYM[nm]: sources.yahoo(s, "60m", "730d"), status)
             for nm in ("dxy", "us10y")}
    daily = {"vix": _fetch_merge(store_dir, f"{SYM['vix']}_1d", lambda: sources.yahoo(SYM["vix"], "1d", "10y"), status)}
    for sid in ("DGS2", "DFII10"):
        try:
            s = sources.fred(sid)
            status[sid] = SeriesStatus(sid, "fred", True, len(s), s.index[-1].isoformat())
            # A FRED value is published after the observation day; usable from the next day.
            daily[sid] = pd.DataFrame({"close": s.values}, index=s.index + pd.Timedelta(days=1))
        except Exception as e:  # noqa: BLE001
            status[sid] = SeriesStatus(sid, note=sources.redact(str(e))[:200])
    cot = None
    try:
        cot = sources.cftc_gold_cot()
        status["COT"] = SeriesStatus("COT", "cftc", True, len(cot), cot.index[-1].isoformat())
    except Exception as e:  # noqa: BLE001
        status["COT"] = SeriesStatus("COT", note=sources.redact(str(e))[:200])
    return Downloads(prim, psrc, gc, chart_ext, macro, daily, cot, status)


def build_market(tf: str, dl: Downloads, now: datetime | None = None) -> Market:
    spec = TIMEFRAMES[tf]
    tf_sec = spec["sec"]
    four_h = spec.get("resample_from") == "1h"
    yint = "60m" if four_h else spec["yahoo"]
    psrc = dl.price_source

    def chart(df):
        if df is None:
            return None
        return sources.resample_ny_session(df, 4) if four_h else df

    raw = chart(dl.prim[yint]).copy()
    gc_chart = chart(dl.gc.get(yint))
    vol_src = psrc
    if "GC=F" not in psrc:
        # Spot FX has no traded volume. Use COMEX gold futures volume bar for bar -- the
        # real institutional volume (TradingView's OANDA feed carries tick counts instead).
        if gc_chart is not None:
            raw["volume"] = gc_chart["volume"].reindex(raw.index).to_numpy()
            vol_src = "yahoo:GC=F futures volume on spot bars"
        else:
            vol_src = "NONE (volume-gated signals cannot fire)"
    base, forming = sources.drop_incomplete(raw, tf_sec, now)

    h1 = dl.prim["60m"]
    d1 = dl.prim.get("1d")
    if d1 is not None and len(d1) and psrc.startswith("yahoo"):
        # Yahoo dates a futures daily bar by its trade date D, whose session opens at 17:00
        # New York on D-1; index it there so the alignment rule sees the session boundary
        # where TradingView does. (Twelve Data daily bars are UTC calendar days and already
        # carry their true 00:00 UTC open, so they are left as they are.)
        d1 = d1.copy()
        d1.index = pd.DatetimeIndex([
            (pd.Timestamp(ts.date()) - pd.Timedelta(days=1) + pd.Timedelta(hours=17)).tz_localize("America/New_York")
            for ts in d1.index]).tz_convert("UTC")
    elif d1 is None or not len(d1):
        d1 = sources.daily_ny_session(h1)
    htf = {"60": h1, "240": sources.resample_ny_session(h1, 4), "D": d1}
    if tf_sec < 900:
        htf["15"] = dl.prim.get("15m") if dl.prim.get("15m") is not None else sources.resample_ohlc(raw, "15min")
    if tf_sec < 300:
        htf["5"] = dl.prim.get("5m")

    ext_chart = {nm: chart(dl.chart_ext.get((nm, yint))) for nm in ("silver", "eurusd", "spx")}
    ext_chart["gc"] = None if "GC=F" in psrc else gc_chart
    status = {k: v for k, v in dl.status.items()}
    if "GC=F" in psrc:
        status["gc_confirm"] = SeriesStatus("gc_confirm", note="price IS gold futures, so the GC confirmation layer is off")
    return Market(tf=tf, tf_sec=tf_sec, base=base, forming=forming, htf=htf, ext_chart=ext_chart,
                  ext_macro=dict(dl.macro), ext_daily=dict(dl.daily), cot=dl.cot, status=status,
                  price_source=psrc, volume_source=vol_src)


# --------------------------------------------------------------------------------------
# Synthetic market, for offline development and the test-suite. Always labelled SYNTHETIC.
# --------------------------------------------------------------------------------------

def _gbm(index: pd.DatetimeIndex, start: float, vol_per_bar: float, rng: np.random.Generator,
         drift: float = 0.0, shocks: np.ndarray | None = None) -> pd.DataFrame:
    n = len(index)
    eps = rng.standard_normal(n)
    if shocks is not None:
        eps = 0.6 * eps + 0.8 * shocks
    # intraday volatility seasonality: London/NY busier than Asia
    h = index.hour.to_numpy()
    season = np.where((h >= 7) & (h < 17), 1.25, 0.75)
    r = drift + vol_per_bar * season * eps
    # occasional regime bursts so displacement / BOS logic gets exercised
    burst = rng.random(n) < 0.004
    r = r + np.where(burst, rng.choice([-1, 1], n) * vol_per_bar * 6, 0.0)
    c = start * np.exp(np.cumsum(r))
    o = np.concatenate([[start], c[:-1]])
    wig = np.abs(rng.standard_normal((n, 2))) * vol_per_bar * season[:, None] * c[:, None] * 0.6
    hi = np.maximum(o, c) + wig[:, 0]
    lo = np.minimum(o, c) - wig[:, 1]
    v = rng.gamma(2.0, 500.0, n) * season * (1 + 4 * burst)
    return pd.DataFrame({"open": o, "high": hi, "low": lo, "close": c, "volume": v}, index=index)


def _trading_index(start: str, periods: int, freq: str) -> pd.DatetimeIndex:
    idx = pd.date_range(start, periods=int(periods * 1.5), freq=freq, tz="UTC")
    ny = idx.tz_convert("America/New_York")
    wd = ny.dayofweek
    hr = ny.hour
    # FX week: Sunday 17:00 NY -> Friday 17:00 NY
    open_ = ~((wd == 5) | ((wd == 4) & (hr >= 17)) | ((wd == 6) & (hr < 17)))
    return idx[open_][:periods]


def load_synthetic(tf: str = "15m", bars: int = 6000, seed: int = 7) -> Market:
    spec = TIMEFRAMES[tf]
    tf_sec = spec["sec"]
    rng = np.random.default_rng(seed)
    freq = f"{tf_sec // 60}min"
    idx = _trading_index("2025-01-06 00:00", bars, freq)
    common = rng.standard_normal(len(idx))
    bar_vol = 0.0011 * math.sqrt(tf_sec / 900)
    gold = _gbm(idx, 2650.0, bar_vol, rng, shocks=common)
    silver = _gbm(idx, 30.0, bar_vol * 1.6, rng, shocks=common)
    gc = gold.copy()
    gc[["open", "high", "low", "close"]] *= 1.004
    gc["volume"] = gold["volume"] * 3
    eur = _gbm(idx, 1.08, bar_vol * 0.35, rng, shocks=common * 0.5)
    spx = _gbm(idx, 5900.0, bar_vol * 0.8, rng)
    base = gold
    h1_idx = _trading_index("2024-01-01 00:00", 12000, "60min")
    h1_idx = h1_idx[h1_idx <= idx[-1]]
    h1 = _gbm(h1_idx, 2050.0, 0.0022, np.random.default_rng(seed + 1), drift=0.00002)
    # stitch: rescale the long 1h history so it ends where the chart series begins
    h1 = h1.copy()
    pre = h1.index < idx[0]
    if pre.any():
        k = gold["close"].iloc[0] / h1.loc[pre, "close"].iloc[-1]
        h1.loc[pre, ["open", "high", "low", "close"]] *= k
    post = sources.resample_ohlc(gold, "60min")
    h1 = pd.concat([h1[pre], post])
    daily = sources.daily_ny_session(h1)
    macro_idx = h1.index
    dxy = _gbm(macro_idx, 104.0, 0.0012, np.random.default_rng(seed + 2))
    us10y = _gbm(macro_idx, 4.3, 0.004, np.random.default_rng(seed + 3))
    vix = _gbm(daily.index, 16.0, 0.05, np.random.default_rng(seed + 4))
    us2y = _gbm(daily.index, 4.0, 0.006, np.random.default_rng(seed + 5))[["close"]]
    weeks = pd.date_range(daily.index[0], daily.index[-1], freq="W-FRI", tz="UTC") + pd.Timedelta(hours=20, minutes=30)
    cot = pd.DataFrame({
        "nc_long": 250000 + np.cumsum(np.random.default_rng(seed + 6).normal(0, 8000, len(weeks))),
        "nc_short": 60000 + np.cumsum(np.random.default_rng(seed + 7).normal(0, 4000, len(weeks))),
        "open_interest": 480000 + np.cumsum(np.random.default_rng(seed + 8).normal(0, 9000, len(weeks))),
    }, index=weeks)
    htf = {"60": h1, "240": sources.resample_ny_session(h1, 4), "D": daily}
    if tf_sec < 900:
        htf["15"] = sources.resample_ohlc(gold, "15min")
    status = {k: SeriesStatus(k, "SYNTHETIC", True, 0, "", "synthetic test data") for k in
              ("price", "silver", "eurusd", "spx", "gc", "dxy", "us10y", "vix", "DGS2", "COT")}
    return Market(tf=tf, tf_sec=tf_sec, base=base, forming=None, htf=htf,
                  ext_chart={"silver": silver, "eurusd": eur, "spx": spx, "gc": gc},
                  ext_macro={"dxy": dxy, "us10y": us10y},
                  ext_daily={"vix": vix, "DGS2": us2y}, cot=cot, status=status,
                  price_source="SYNTHETIC", volume_source="SYNTHETIC", synthetic=True)
