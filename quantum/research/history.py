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
             sleep_s: float = 8.0, max_calls: int = 300, now: datetime | None = None, log=print) -> dict:
    name, step, floor = series_name(symbol, interval), STEP[interval], pd.Timestamp(start, tz="UTC")
    have = store.load(store_dir, name)
    calls, added, stop = 0, 0, "max calls"
    end = (have.index.min() - step) if have is not None and len(have) else pd.Timestamp(now or datetime.now(timezone.utc))
    while calls < max_calls:                                       # backwards to the floor or the feed's first bar
        if end < floor:
            stop = "reached the start date"
            break
        df = fetch(symbol, interval, apikey, end=end)
        calls += 1
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
        time.sleep(sleep_s)                                        # the free plan allows 8 requests a minute
    if have is not None and len(have) and calls < max_calls:     # forwards to now
        df = fetch(symbol, interval, apikey, start=have.index.max() + step)
        calls += 1
        if df is not None and len(df):
            have = store.merge(have, df)
            added += len(df)
            store.save(store_dir, name, have)
    rec = {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "series": name, "calls": calls, "added": added,
           "rows": 0 if have is None else int(len(have)), "first": None if have is None or not len(have) else have.index.min().isoformat(),
           "last": None if have is None or not len(have) else have.index.max().isoformat(), "stop": stop}
    os.makedirs(store_dir, exist_ok=True)
    with open(os.path.join(store_dir, "_history_log.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")
    log(json.dumps(rec))
    return rec


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
