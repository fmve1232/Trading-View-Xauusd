"""Historical XAU/USD bars for research (audit/PREREGISTRATION.md Amendment 11).

Pages Twelve Data's `time_series` backwards from the oldest stored bar (or now) to 2010-01-01 or the earliest bar the
feed serves, and forwards from the newest stored bar to now. Bars go to `<store>/TD_XAU_USD_<interval>/<YYYY-MM>.csv`
(the store format) on the `research-data` branch, which the engine and the site never read. Every run appends a line to
`<store>/_history_log.jsonl` (calls, rows, first and last bar). The API key is never written or logged.

  python -m quantum.research.history --store rd --intervals 1h,15min [--start 2010-01-01]
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone

import pandas as pd

from ..data import sources, store

STEP = {"1h": pd.Timedelta(hours=1), "15min": pd.Timedelta(minutes=15), "5min": pd.Timedelta(minutes=5), "1day": pd.Timedelta(days=1)}
PAGE = 5000            # Twelve Data's maximum outputsize
NO_DATA = ("no data", "not found", "no values")


class MinuteLimit(Exception):
    """The plan's per-minute credits are spent (the site's pipeline shares the key): wait and retry."""


class DayLimit(Exception):
    """The plan's daily credits are spent: stop; the next run resumes from the oldest stored bar."""


def series_name(symbol: str, interval: str) -> str:
    return "TD_" + symbol.replace("/", "_") + "_" + interval


def page(symbol: str, interval: str, apikey: str, end: pd.Timestamp | None = None, start: pd.Timestamp | None = None) -> pd.DataFrame | None:
    """One request: up to 5000 bars ending at `end` (or starting at `start`), oldest first; None when the feed has none."""
    params = {"symbol": symbol, "interval": interval, "outputsize": PAGE, "timezone": "UTC", "order": "ASC", "apikey": apikey}
    if end is not None:
        params["end_date"] = end.strftime("%Y-%m-%d %H:%M:%S")
    if start is not None:
        params["start_date"] = start.strftime("%Y-%m-%d %H:%M:%S")
    j = sources._get("https://api.twelvedata.com/time_series", params).json()
    if j.get("status") != "ok":
        msg = str(j.get("message", j.get("status", ""))).lower()
        if any(k in msg for k in NO_DATA):
            return None
        if "credits" in msg and "minute" in msg:
            raise MinuteLimit(msg[:120])
        if "credits" in msg and ("day" in msg or "daily" in msg):
            raise DayLimit(msg[:120])
        raise sources.FetchError(sources.redact(f"twelvedata {symbol} {interval}: {j.get('message', j.get('status'))}"))
    vals = j.get("values") or []
    if not vals:
        return None
    df = pd.DataFrame(vals)
    df.index = pd.to_datetime(df.pop("datetime"), utc=True)
    for c in sources.COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce") if c in df else float("nan")
    df = df[sources.COLS].sort_index()
    return df[~df.index.duplicated(keep="last")]


def backfill(store_dir: str, symbol: str, interval: str, apikey: str, start: str = "2010-01-01", fetch=page,
             sleep_s: float = 10.0, max_calls: int = 300, now: datetime | None = None, log=print) -> dict:
    name, step, floor = series_name(symbol, interval), STEP[interval], pd.Timestamp(start, tz="UTC")
    have = store.load(store_dir, name)
    calls, added, stop = 0, 0, "max calls"
    end = (have.index.min() - step) if have is not None and len(have) else pd.Timestamp(now or datetime.now(timezone.utc))
    err, waits = None, 0
    while calls < max_calls:                                       # backwards to the floor or the feed's first bar
        if end < floor:
            stop = "reached the start date"
            break
        try:
            df = fetch(symbol, interval, apikey, end=end)
        except MinuteLimit:
            calls += 1
            waits += 1
            if waits > 6:
                err, stop = "per-minute credit limit persisted", "error"
                break
            time.sleep(65 if sleep_s else 0)
            continue
        except DayLimit:
            calls += 1
            stop = "daily credit limit (resumes next run)"
            break
        except Exception as e:  # noqa: BLE001 - recorded in the log (key redacted), then the run stops
            calls += 1
            if "HTTP 404" in str(e) and have is not None and len(have):
                stop = "the feed has no older bars"                # Twelve Data answers 404 before its first bar
                break
            err, stop = sources.redact(f"{type(e).__name__}: {e}")[:300], "error"
            break
        calls += 1
        waits = 0
        if df is None or df.empty:
            stop = "the feed has no older bars"
            break
        df = df[df.index >= floor]
        have = store.merge(have, df)
        added += len(df)
        store.save(store_dir, name, have)
        new_end = df.index.min() - step if len(df) else end - step * PAGE
        if new_end >= end:
            stop = "no progress"
            break
        end = new_end
        log(f"{name}: {len(have)} bars, oldest {have.index.min()}")
        time.sleep(sleep_s)                                        # free plan: 8 a minute, shared with the site's pipeline
    if err is None and have is not None and len(have) and calls < max_calls:     # forwards to now
        try:
            df = fetch(symbol, interval, apikey, start=have.index.max() + step)
        except (MinuteLimit, DayLimit):
            df = None                                              # the next run adds the newest bars
        except Exception as e:  # noqa: BLE001
            df, err = None, sources.redact(f"{type(e).__name__}: {e}")[:300]
        calls += 1
        if df is not None and len(df):
            have = store.merge(have, df)
            added += len(df)
            store.save(store_dir, name, have)
    rec = {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "series": name, "calls": calls, "added": added,
           "rows": 0 if have is None else int(len(have)), "first": None if have is None or not len(have) else have.index.min().isoformat(),
           "last": None if have is None or not len(have) else have.index.max().isoformat(), "stop": stop, "error": err,
           "end_requested": end.isoformat() if stop == "error" else None}
    os.makedirs(store_dir, exist_ok=True)
    with open(os.path.join(store_dir, "_history_log.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")
    log(json.dumps(rec))
    if err:
        raise sources.FetchError(err)
    return rec



def load(store_dir: str, symbol: str = "XAU/USD", interval: str = "1h") -> pd.DataFrame | None:
    """Research series as the engine would see it: market-shut bars removed (audit 2026-10-31, D-R1).

    The stored history is raw. From 2025 Twelve Data prints its XAU/USD quote 24/7, so the raw 1h series holds
    ~3,100 bars inside the weekend / daily closure (893 in 2025, 2,200 in 2026; none in 2021-2024). Every
    research run must read through here, or the sealed 2024-07..2025-12 holdout would mix two feed formats.
    """
    df = store.load(store_dir, series_name(symbol, interval))
    if df is None or len(df) == 0:
        return df
    return sources.trading_week_only(sources.drop_offgrid(df), daily=interval in ("1day", "1d"))

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--store", required=True)
    ap.add_argument("--symbol", default="XAU/USD")
    ap.add_argument("--intervals", default="1h,15min")
    ap.add_argument("--start", default="2010-01-01")
    ap.add_argument("--max-calls", type=int, default=300)
    a = ap.parse_args(argv)
    key = os.environ.get("TWELVEDATA_API_KEY", "")
    if not key:
        print("TWELVEDATA_API_KEY is not set")
        return 1
    ok = True
    for iv in [x.strip() for x in a.intervals.split(",") if x.strip()]:
        try:
            backfill(a.store, a.symbol, iv, key, a.start, max_calls=a.max_calls)
        except Exception as e:  # noqa: BLE001 - report and continue with the next interval
            print("::warning::" + sources.redact(f"{iv}: {type(e).__name__}: {e}"))
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
