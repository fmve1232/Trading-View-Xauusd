#!/usr/bin/env python3
"""Independent price cross-check: the site's Twelve Data XAU/USD bars vs Dukascopy.

AUDIT TOOL -- not part of the engine or the website. It reads the market-data store (read-only),
downloads Dukascopy's public 1-minute BID and ASK candles for complete past days, builds MID bars
on the same UTC open-time grid, and reports how far the two feeds disagree. Dukascopy's terms
restrict redistribution, so its data is never written to the site or the store; the report holds
summary statistics and a short list of the largest disagreements only.

Dukascopy day file (LZMA "alone" format, .bi5), per side:
  https://datafeed.dukascopy.com/datafeed/XAUUSD/YYYY/MM/DD/{BID,ASK}_candles_min_1.bi5
  MM is ZERO-based (January = 00). Records are 24 bytes, big-endian:
  int32 seconds-from-midnight-UTC, int32 open, int32 close, int32 low, int32 high, float32 volume.
  Prices are integers in instrument points; the divisor is detected (not assumed) by matching the
  Twelve Data price level, and the decode is rejected if the candles fail OHLC sanity checks.

  python3 audit/tools/xcheck_dukascopy.py --store store --days 20 --out xcheck
"""
from __future__ import annotations

import argparse
import json
import lzma
import math
import os
import struct
import sys
import time
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from quantum.data import sources, store  # noqa: E402  (read-only use)

URL = "https://datafeed.dukascopy.com/datafeed/{sym}/{y:04d}/{m0:02d}/{d:02d}/{side}_candles_min_1.bi5"
REC = struct.Struct(">iiiiif")
DIVISORS = (1000.0, 100.0, 10.0, 100000.0)


def decode_candles(raw: bytes, day: date) -> pd.DataFrame:
    """One Dukascopy day file -> integer-point OHLC indexed by minute (UTC)."""
    if not raw:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    buf = lzma.decompress(raw, format=lzma.FORMAT_ALONE)
    if len(buf) % REC.size:
        raise ValueError(f"{day}: {len(buf)} bytes is not a multiple of {REC.size}")
    rows = [REC.unpack_from(buf, k) for k in range(0, len(buf), REC.size)]
    t0 = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    idx = pd.DatetimeIndex([t0 + timedelta(seconds=r[0]) for r in rows])
    return pd.DataFrame({"open": [r[1] for r in rows], "close": [r[2] for r in rows], "low": [r[3] for r in rows],
                         "high": [r[4] for r in rows], "volume": [r[5] for r in rows]}, index=idx, dtype=float)


def fetch_day(sym: str, day: date, side: str, get) -> pd.DataFrame:
    url = URL.format(sym=sym, y=day.year, m0=day.month - 1, d=day.day, side=side)
    return decode_candles(get(url), day)


def mid_minutes(bid: pd.DataFrame, ask: pd.DataFrame) -> pd.DataFrame:
    j = bid.join(ask, lsuffix="_b", rsuffix="_a", how="inner")
    out = pd.DataFrame({k: (j[f"{k}_b"] + j[f"{k}_a"]) / 2.0 for k in ("open", "high", "low", "close")})
    out["spread"] = j["close_a"] - j["close_b"]
    return out


def detect_divisor(points: pd.Series, ref_level: float) -> float:
    """The scale that brings Dukascopy's integer prices to the reference level (within 5%)."""
    med = float(points.median())
    best = min(DIVISORS, key=lambda d: abs(math.log(max(med / d, 1e-12) / ref_level)))
    if abs(med / best / ref_level - 1.0) > 0.05:
        raise ValueError(f"no divisor maps Dukascopy median {med:.0f} to the reference level {ref_level:.2f}")
    return best


def sane(m: pd.DataFrame) -> float:
    """Share of minutes with low <= open, close <= high and a non-negative spread."""
    ok = (m["low"] <= m[["open", "close"]].min(axis=1) + 1e-9) & (m["high"] >= m[["open", "close"]].max(axis=1) - 1e-9) \
        & (m["spread"] >= -1e-9)
    return float(ok.mean()) if len(m) else 0.0


def to_bars(m: pd.DataFrame, rule: str) -> pd.DataFrame:
    g = m.resample(rule, label="left", closed="left")
    return pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                         "close": g["close"].last(), "minutes": g["close"].count(),
                         "spread": g["spread"].median()}).dropna(subset=["close"])


def compare(td: pd.DataFrame, dk: pd.DataFrame, bar_min: int) -> dict:
    """Per-bar agreement of two OHLC frames on the same UTC open-time index."""
    full = dk[dk["minutes"] >= bar_min * 0.9]                      # only bars Dukascopy saw almost completely
    j = td.join(full, lsuffix="_td", rsuffix="_dk", how="inner")
    res = {"bars_td": int(len(td)), "bars_dukascopy_complete": int(len(full)), "matched": int(len(j)),
           "td_only": int(len(td.index.difference(full.index))), "dukascopy_only": int(len(full.index.difference(td.index)))}
    if len(j) < 10:
        res["note"] = "fewer than 10 matched bars; nothing to conclude"
        return res
    d = {k: (j[f"{k}_td"] - j[f"{k}_dk"]) for k in ("open", "high", "low", "close")}
    ad = d["close"].abs()
    rng = (j["high_dk"] - j["low_dk"]).replace(0, np.nan)
    r_td, r_dk = j["close_td"].pct_change(), j["close_dk"].pct_change()
    lag = {}
    for k in (-2, -1, 0, 1, 2):                                    # a grid-label offset shows up as a better lag
        c = r_td.corr(r_dk.shift(k))
        lag[str(k)] = None if pd.isna(c) else round(float(c), 4)
    worst = ad.sort_values(ascending=False).head(10)
    res.update({
        "close_diff_mean": round(float(d["close"].mean()), 3),     # bias: + means Twelve Data prints higher
        "close_absdiff_median": round(float(ad.median()), 3), "close_absdiff_p95": round(float(ad.quantile(0.95)), 3),
        "close_absdiff_max": round(float(ad.max()), 3),
        "close_absdiff_bps_median": round(float((ad / j["close_dk"]).median() * 1e4), 2),
        "high_absdiff_median": round(float(d["high"].abs().median()), 3), "low_absdiff_median": round(float(d["low"].abs().median()), 3),
        "close_diff_vs_bar_range_median": round(float((ad / rng).median()), 3),
        "return_corr": lag["0"], "return_sign_agreement": round(float((np.sign(r_td) == np.sign(r_dk))[r_td.notna() & r_dk.notna()].mean()), 4),
        "return_corr_by_lag_bars": lag, "best_lag_bars": int(max((k for k in lag if lag[k] is not None), key=lambda k: lag[k])),
        "dukascopy_spread_median": round(float(j["spread"].median()), 3),
        "largest_close_diffs": [{"bar_open_utc": t.isoformat(), "td_close": round(float(j.at[t, "close_td"]), 3),
                                 "dk_close": round(float(j.at[t, "close_dk"]), 3), "diff": round(float(d["close"][t]), 3)} for t in worst.index],
    })
    return res


def verdict(r: dict) -> str:
    if "close_absdiff_median" not in r:
        return "NOT RUN (too few matched bars)"
    if r["best_lag_bars"] != 0:
        return f"CHECK: returns line up best at a lag of {r['best_lag_bars']} bar(s) -- a bar-labelling offset between the feeds"
    if r["return_corr"] is not None and r["return_corr"] < 0.9:
        return "CHECK: bar-to-bar returns correlate below 0.9"
    if r["close_absdiff_bps_median"] > 5:
        return "CHECK: median close difference above 5 bps"
    return "CONSISTENT (median close difference {:.2f} bps, return correlation {:.3f})".format(r["close_absdiff_bps_median"], r["return_corr"])


def report_md(doc: dict) -> str:
    L = [f"# Twelve Data vs Dukascopy — XAU/USD cross-check", "",
         f"Run {doc['generated_utc']} · days {doc['from']} → {doc['to']} · Dukascopy MID = (BID+ASK)/2 · divisor {doc.get('divisor')}", ""]
    if doc.get("error"):
        return "\n".join(L + [f"**NOT RUN:** {doc['error']}"])
    L += [f"Dukascopy minutes decoded: {doc['dukascopy_minutes']} · OHLC sanity {doc['sanity_share']:.2%} · days fetched {doc['days_ok']}/{doc['days_tried']}", ""]
    for tf, r in doc["timeframes"].items():
        L += [f"## {tf}", "", f"**{r['verdict']}**", "", "| Metric | Value |", "|---|---|"]
        for k, v in r.items():
            if k in ("verdict", "largest_close_diffs"):
                continue
            L.append(f"| {k} | {json.dumps(v) if isinstance(v, dict) else v} |")
        if r.get("largest_close_diffs"):
            L += ["", "Largest close differences (bar open, UTC):", "", "| Bar | Twelve Data | Dukascopy | Diff |", "|---|---|---|---|"]
            L += [f"| {x['bar_open_utc']} | {x['td_close']} | {x['dk_close']} | {x['diff']:+} |" for x in r["largest_close_diffs"]]
        L.append("")
    L.append("Dukascopy data is used for this audit only and is not republished (its terms restrict redistribution).")
    return "\n".join(L)


FAIL_FAST_DAYS = 3        # stop when the first days attempted all fail: the feed is unreachable, not flaky


def _default_get(url: str) -> bytes:
    """One short attempt per file (20 s). The public feed either answers quickly or not at all."""
    import requests
    r = requests.get(url, headers=sources.UA, timeout=20)
    if r.status_code == 404:
        return b""                                                    # no file for that day
    if r.status_code != 200:
        raise sources.FetchError(f"{url} -> HTTP {r.status_code}")
    return r.content


def run(store_dir: str, days: int, sym: str = "XAUUSD", get=None, today: date | None = None, log=print) -> dict:
    get = get or _default_get
    today = today or datetime.now(timezone.utc).date()
    doc = {"generated_utc": datetime.now(timezone.utc).isoformat(), "symbol": sym, "timeframes": {}}
    td = {}
    for tf, name in (("15m", "XAU_USD_15m"), ("1h", "XAU_USD_60m")):
        df = store.load(store_dir, name)
        if df is None or not len(df):
            doc["error"] = f"no {name} in the store at {store_dir}"
            return doc
        df = sources.trading_week_only(df)
        td[tf] = df[["open", "high", "low", "close"]].astype(float)
    last_full = today - timedelta(days=1)                            # only complete UTC days
    span = [last_full - timedelta(days=k) for k in range(days)][::-1]
    doc["from"], doc["to"], doc["days_tried"] = span[0].isoformat(), span[-1].isoformat(), len(span)
    parts, ok, tried = [], 0, 0
    for day in span:
        if day.weekday() == 5:                                        # Saturday: no market
            continue
        tried += 1
        t0 = time.time()
        try:
            b, a = fetch_day(sym, day, "BID", get), fetch_day(sym, day, "ASK", get)
            ok += 1
            log(f"[xcheck] {day}: {len(b)} bid / {len(a)} ask minutes ({time.time() - t0:.1f}s)", flush=True)
        except Exception as e:  # noqa: BLE001
            msg = f"{day}: {type(e).__name__}: {sources.redact(str(e))[:140]}"
            doc.setdefault("fetch_errors", []).append(msg)
            log(f"[xcheck] FAILED {msg} ({time.time() - t0:.1f}s)", flush=True)
            if ok == 0 and tried >= FAIL_FAST_DAYS:
                doc["error"] = f"Dukascopy feed unreachable from this runner: the first {tried} days all failed ({msg})"
                return doc
            continue
        if len(b) and len(a):
            parts.append(mid_minutes(b, a))
        time.sleep(0.3)                                               # be polite to the public feed
    doc["days_ok"] = ok
    if not parts:
        doc["error"] = "no Dukascopy data could be read" + (f" ({doc['fetch_errors'][0]})" if doc.get("fetch_errors") else "")
        return doc
    m = pd.concat(parts).sort_index()
    ref = float(td["1h"]["close"].loc[str(span[0]):].median())
    div = detect_divisor(m["close"], ref)
    m[["open", "high", "low", "close", "spread"]] = m[["open", "high", "low", "close", "spread"]] / div
    doc["divisor"], doc["dukascopy_minutes"], doc["sanity_share"] = div, int(len(m)), round(sane(m), 4)
    if doc["sanity_share"] < 0.99:
        doc["error"] = f"decoded candles fail OHLC sanity on {1 - doc['sanity_share']:.1%} of minutes -- format assumption wrong"
        return doc
    lo, hi = m.index.min(), m.index.max()
    for tf, rule, mins in (("15m", "15min", 15), ("1h", "1h", 60)):
        dk = to_bars(m, rule)
        t = td[tf][(td[tf].index >= lo) & (td[tf].index < hi)]
        r = compare(t, dk, mins)
        r["verdict"] = verdict(r)
        doc["timeframes"][tf] = r
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", required=True)
    ap.add_argument("--days", type=int, default=20)
    ap.add_argument("--out", default="xcheck")
    a = ap.parse_args(argv)
    doc = run(a.store, a.days)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "xcheck.json"), "w") as f:
        json.dump(doc, f, indent=1, default=str)
    md = report_md(doc)
    with open(os.path.join(a.out, "xcheck.md"), "w") as f:
        f.write(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(md + "\n")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
