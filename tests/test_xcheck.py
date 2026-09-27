"""audit/tools/xcheck_dukascopy.py against Dukascopy-format files built from known bars."""
import importlib.util
import lzma
import os
import re
import struct
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from quantum.data import store

_spec = importlib.util.spec_from_file_location(
    "xcheck", os.path.join(os.path.dirname(__file__), "..", "audit", "tools", "xcheck_dukascopy.py"))
xc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(xc)

TODAY = date(2026, 9, 26)                       # a Saturday: the last complete trading day is Friday the 25th
REC = struct.Struct(">iiiiif")


def _td_bars():
    rng = np.random.default_rng(11)
    idx = pd.date_range("2026-09-14 00:00", "2026-09-25 20:45", freq="15min", tz="UTC")
    c = 4300 + np.cumsum(rng.normal(0, 1.5, len(idx)))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + rng.uniform(0.2, 1.5, len(idx))
    l = np.minimum(o, c) - rng.uniform(0.2, 1.5, len(idx))
    m15 = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 0.0}, index=idx)
    g = m15.resample("1h", label="left", closed="left")
    h1 = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last(),
                       "volume": 0.0}).dropna()
    return m15, h1


def _minutes(m15, offset, shift_min=0):
    """Dukascopy-like MID minutes whose 15m aggregation equals m15 + offset (optionally time-shifted)."""
    rows = []
    for t, b in m15.iterrows():
        path = np.linspace(b.open, b.close, 16)
        for k in range(15):
            o, c = path[k], path[k + 1]
            hi, lo = max(o, c), min(o, c)
            if k == 5:
                hi = b.high
            if k == 10:
                lo = b.low
            rows.append((t + timedelta(minutes=k + shift_min), o + offset, hi + offset, lo + offset, c + offset))
    return rows


def _getter(rows, divisor=1000.0, half_spread=0.15, corrupt=False):
    by_day = {}
    for t, o, h, l, c in rows:
        by_day.setdefault(t.date(), []).append((t, o, h, l, c))

    def get(url):
        m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/(BID|ASK)_candles_min_1\.bi5$", url)
        y, m0, d, side = int(m[1]), int(m[2]), int(m[3]), m[4]
        day = date(y, m0 + 1, d)                                    # the URL month is zero-based
        sgn = -1 if side == "BID" else 1
        buf = b""
        for t, o, h, l, c in by_day.get(day, []):
            px = [round((v + sgn * half_spread) * divisor) for v in (o, c, l, h)]
            if corrupt:
                px[2], px[3] = px[3], px[2]                         # low above high
            sec = int((t - datetime(day.year, day.month, day.day, tzinfo=timezone.utc)).total_seconds())
            buf += REC.pack(sec, *px, 1.0)
        return lzma.compress(buf, format=lzma.FORMAT_ALONE) if buf else b""
    return get


@pytest.fixture()
def st(tmp_path):
    m15, h1 = _td_bars()
    store.save(str(tmp_path), "XAU_USD_15m", m15)
    store.save(str(tmp_path), "XAU_USD_60m", h1)
    return str(tmp_path), m15


def test_decoder_reads_zero_based_month_and_big_endian_records():
    raw = lzma.compress(REC.pack(60, 4300123, 4301456, 4299000, 4302000, 2.5), format=lzma.FORMAT_ALONE)
    df = xc.decode_candles(raw, date(2026, 1, 5))
    assert df.index[0] == pd.Timestamp("2026-01-05 00:01", tz="UTC")
    assert list(df.iloc[0][["open", "close", "low", "high"]]) == [4300123, 4301456, 4299000, 4302000]
    assert xc.URL.format(sym="XAUUSD", y=2026, m0=0, d=5, side="BID").endswith("/2026/00/05/BID_candles_min_1.bi5")
    assert xc.decode_candles(b"", date(2026, 1, 5)).empty                  # weekends are empty files


def test_consistent_feeds_report_the_known_bias(st):
    path, m15 = st
    doc = xc.run(path, 12, get=_getter(_minutes(m15, offset=-0.20)), today=TODAY)
    assert "error" not in doc and doc["divisor"] == 1000.0 and doc["sanity_share"] == 1.0
    r = doc["timeframes"]["15m"]
    assert r["matched"] > 500 and r["best_lag_bars"] == 0
    assert abs(r["close_diff_mean"] - 0.20) < 0.005                      # TD prints 0.20 above Dukascopy mid
    assert r["return_corr"] > 0.99 and r["verdict"].startswith("CONSISTENT")
    assert abs(r["ref_spread_median"] - 0.30) < 0.005
    assert doc["timeframes"]["1h"]["verdict"].startswith("CONSISTENT")


def test_time_offset_is_flagged(st):
    path, m15 = st
    doc = xc.run(path, 12, get=_getter(_minutes(m15, 0.0, shift_min=60)), today=TODAY)
    r = doc["timeframes"]["1h"]
    assert r["best_lag_bars"] != 0 and r["verdict"].startswith("CHECK")


def test_scale_is_detected_and_bad_decodes_are_refused(st):
    path, m15 = st
    assert xc.run(path, 12, get=_getter(_minutes(m15, 0.0), divisor=100.0), today=TODAY)["divisor"] == 100.0
    doc = xc.run(path, 12, get=_getter(_minutes(m15, 0.0), corrupt=True), today=TODAY)
    assert "OHLC sanity" in doc["error"] and "timeframes" in doc and not doc["timeframes"]
    assert "NOT RUN" in xc.report_md(doc)


def test_unreachable_feed_fails_fast_and_is_not_run(st):
    path, _ = st
    calls = []
    def get(url):
        calls.append(url)
        raise OSError("blocked")
    doc = xc.run(path, 20, get=get, today=TODAY, log=lambda *a, **k: None)
    assert "unreachable" in doc["error"] and "NOT RUN" in xc.report_md(doc)
    assert len(calls) == xc.FAIL_FAST_DAYS                          # one BID attempt per day, then stop


# ---------------- Yahoo reference ----------------
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def _yahoo_fetch(m15, offset=0.0, scale=1.0, forming=True):
    def fetch(sym, interval, rng):
        assert sym == "XAUUSD=X" and rng == "60d"
        df = m15 if interval == "15m" else m15.resample("1h", label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
        out = (df[["open", "high", "low", "close"]] + offset) * scale
        if forming:                                   # Yahoo also returns the still-forming bar: must be dropped
            out.loc[pd.Timestamp("2026-09-26 11:45", tz="UTC")] = [9999.0, 9999.0, 9999.0, 9999.0]
        return out.assign(volume=0.0)
    return fetch


def test_yahoo_consistent_feed(st):
    path, m15 = st
    doc = xc.run_yahoo(path, 20, fetch=_yahoo_fetch(m15, offset=0.35), now=NOW)
    assert "error" not in doc and doc["reference"] == "Yahoo XAUUSD=X"
    r = doc["timeframes"]["1h"]
    assert abs(r["close_diff_mean"] + 0.35) < 0.005 and r["best_lag_bars"] == 0      # TD 0.35 below Yahoo
    assert r["ref_spread_median"] is None and r["verdict"].startswith("CONSISTENT")
    assert doc["timeframes"]["15m"]["matched"] > 500
    assert all(x["ref_close"] < 9000 for x in r["largest_close_diffs"])              # the forming bar was excluded
    md = xc.report_md(doc)
    assert "Twelve Data vs Yahoo XAUUSD=X" in md and "| Yahoo XAUUSD=X |" in md


def test_yahoo_wrong_instrument_and_outage_are_not_run(st):
    path, m15 = st
    doc = xc.run_yahoo(path, 20, fetch=_yahoo_fetch(m15, scale=1.5), now=NOW)
    assert "different instrument" in doc["error"] and "NOT RUN" in xc.report_md(doc)
    doc = xc.run_yahoo(path, 20, fetch=lambda *a: (_ for _ in ()).throw(OSError("HTTP 429")), now=NOW)
    assert "unavailable" in doc["error"] and "429" in doc["error"]
    later = datetime(2027, 3, 1, tzinfo=timezone.utc)                                # store has nothing that recent
    doc = xc.run_yahoo(path, 20, fetch=lambda *a: pd.DataFrame(
        {"open": [4300.0], "high": [4301.0], "low": [4299.0], "close": [4300.5], "volume": [0.0]},
        index=pd.DatetimeIndex(["2027-02-26 10:00"], tz="UTC")), now=later)
    assert "error" in doc                                                            # NaN level must not pass


# ---------------- COMEX futures reference (from the store) ----------------
def _gc_store(tmp_path, m15, premium_fn, spike_at=None):
    days = pd.Series(xc.trading_day(m15.index), index=m15.index)
    prem = days.map(premium_fn).astype(float)
    gc15 = m15[["open", "high", "low", "close"]].add(prem, axis=0)
    if spike_at is not None:
        gc15.loc[spike_at, ["close", "high"]] += 25.0
    gc15 = gc15.assign(volume=100.0)
    brk = gc15.index.tz_convert("America/New_York")
    gc15 = gc15[~((brk.hour == 17))]                                  # COMEX daily break: no futures bars
    g = gc15.resample("1h", label="left", closed="left")
    gc60 = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last(),
                         "volume": g["volume"].sum()}).dropna()
    store.save(str(tmp_path), "GC=F_15m", gc15)
    store.save(str(tmp_path), "GC=F_60m", gc60)


def test_gc_premium_removed_per_trading_day_and_rolls_flagged(st, tmp_path):
    path, m15 = st
    roll = date(2026, 9, 21)
    _gc_store(tmp_path, m15, lambda d: 40.0 if d < roll else 28.0,
              spike_at=pd.Timestamp("2026-09-22 08:00", tz="UTC"))            # 04:00 New York: no event window
    doc = xc.run_gc(path, 20, now=datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc))
    assert "error" not in doc
    r15, r1 = doc["timeframes"]["15m"], doc["timeframes"]["1h"]
    assert abs(r1["close_diff_mean"]) < 0.1 and r1["best_lag_bars"] == 0
    assert "2026-09-21" in r1["probable_rolls"]                               # the 40 -> 28 premium drop
    assert r15["td_only"] > 0                                                 # the COMEX break: spot-only bars
    assert any(x["bar_open_utc"].startswith("2026-09-22T08:00") for x in r15["unexplained_outliers"])
    assert "review" in r15["verdict"]
    assert xc.event_window(pd.Timestamp("2026-09-04 12:45", tz="UTC")).startswith("08:30")
    assert xc.event_window(pd.Timestamp("2026-09-16 19:00", tz="UTC")).startswith("14:00-16:00")
    assert xc.event_window(pd.Timestamp("2026-09-11 20:45", tz="UTC")) == "Friday close"
    assert "**unexplained**" in xc.report_md(doc)


def test_gc_trading_day_starts_at_1700_new_york():
    idx = pd.DatetimeIndex(["2026-09-21 20:59", "2026-09-21 21:00"], tz="UTC")     # 16:59 / 17:00 New York (EDT)
    assert list(xc.trading_day(idx)) == [date(2026, 9, 21), date(2026, 9, 22)]


def test_gc_wrong_underlying_and_missing_series(st, tmp_path):
    path, m15 = st
    doc = xc.run_gc(path, 20, now=datetime(2026, 9, 26, 12, tzinfo=timezone.utc))
    assert "no GC=F_15m" in doc["error"]
    _gc_store(tmp_path, m15, lambda d: 900.0)                                  # ~20% "premium": not gold futures
    doc = xc.run_gc(path, 20, now=datetime(2026, 9, 26, 12, tzinfo=timezone.utc))
    assert "not the same underlying" in doc["error"]
