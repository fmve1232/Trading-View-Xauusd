"""Phase B5c: ORDER FLOW on Dukascopy's spot-gold top of book (free, no account), against the operator's -$10 stop with
+$10 / +$15 / +$20 targets. DEVELOPMENT data only (Amendment 13).

Why this exists. The operator approved the B5 order-flow study on 2026-11-01. They then asked for a free source:
Databento is paid, and OANDA does not accept residents of Pakistan. Dukascopy publishes its tick data free to everyone.
It refuses GitHub's servers, so this runs on the operator's own Windows laptop. Declared and committed BEFORE any
Dukascopy data was obtained; not to be changed after results are seen.

    py -m quantum.research.b5c_dukascopy            (from the repository folder; see research/ORDER_FLOW_RESEARCH.md)

DATA (stays on the laptop; Dukascopy's terms restrict redistribution)
  - Dukascopy datafeed: XAUUSD hourly tick files (.bi5, LZMA).
    Each tick = (ms in the hour, ask, bid, ask volume, bid volume): the best offer and bid on Dukascopy's SWFX
    marketplace, with the liquidity shown at each.
  - Every hour of the development partition except Saturdays is fetched, 2020-01-24 -> 2023-01-24.
  - Each hour is reduced at once to 15-minute sums. Only those sums are cached (one CSV per day, under --cache), so an
    interrupted run resumes without downloading again.
  - Spot paths: the research-data branch (Twelve Data XAU/USD 15-minute bars), downloaded from GitHub as a zip.
    These are the same paths as B2-B5.
FEATURES per 15-minute bar (UTC open time; built from ticks inside the bar or earlier, so known at its close)
    ofi15, ofi60   Cont-Kukanov-Stoikov order-flow imbalance on Dukascopy's best bid / offer, summed over the bar or the
                   last 4 bars, divided by the mean depth (bid volume + ask volume) / 2. Every tick is a book update
                   here, so this is the full top-of-book OFI for this venue. The first tick of each hour file counts 0.
    qimb15         mean queue imbalance (bid volume - ask volume) / (bid volume + ask volume) over the bar's ticks
    qlast          the same at the bar's last tick
    timb15, timb60 (up-ticks - down-ticks) / (up + down) of the mid, over the bar or the last 4 bars
    ntr_z          log tick count, z-scored over the previous 2,000 bars
    spread         mean ask - bid over the bar's ticks
  Units are checked against the spot paths before anything is tested: the price scale (a power of ten) is detected
  from the median ratio of Dukascopy's last mid to the spot close. The run stops if the median gap exceeds 0.5%.
Q1 DIRECTION (decides): B5's machinery (quantum/research/b5_orderflow.study), unchanged.
  - Rules: ofi15, ofi60, qimb15, qlast and timb15 at their trailing 90th percentile; follow (CONT) or fade (REV);
    +$10 / +$15 / +$20 against -$10. 5 x 2 x 3 = 30 trials.
  - Model: logistic regression only (numpy; nothing extra to install on the laptop). The 8 features, 6-block purged
    walk-forward, top decile, one position at a time. 3 trials.
  - All 33 trials face B2's five-part rule, plus an out-of-fold AUC of at least 0.55 for the model.
Q2 EXECUTION (descriptive): the next 15 / 60 minutes' spot move by ofi15 decile.
OUTPUT: b5c_results.json (aggregate figures only) and a printed summary for the operator to send back.
"""
from __future__ import annotations

import argparse
import io
import json
import lzma
import math
import os
import struct
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

from . import b5_orderflow as B
from . import harness as H
from . import history

INSTRUMENT = "XAUUSD"
URL = "https://datafeed.dukascopy.com/datafeed/{sym}/{y:04d}/{m0:02d}/{d:02d}/{h:02d}h_ticks.bi5"
RD_ZIP = "https://codeload.github.com/fmve1232/Trading-View-Xauusd/zip/refs/heads/research-data"
REC = struct.Struct(">3I2f")             # ms, ask, bid, ask volume, bid volume (big-endian)
BAR_MS = 900_000
RULE_FEATURES = ("ofi15", "ofi60", "qimb15", "qlast", "timb15")
MODEL_FEATURES = ("ofi15", "ofi60", "qimb15", "qlast", "timb15", "timb60", "ntr_z", "spread")
DIRECTIONAL = ("ofi15", "ofi60", "qimb15", "qlast", "timb15", "timb60")
Q2 = "ofi15"
MODELS = (B.Logit,)
ALIGN_MAX = 0.005
WORKERS, RETRIES, TIMEOUT = 6, 5, 30
SUM_COLS = ["n", "ofi", "depth", "qsum", "qn", "qlast", "up", "down", "spread_sum", "mid_last"]
UA = {"User-Agent": "Mozilla/5.0 (research; quantum b5c)"}


# ---------------- ticks ----------------
def parse_bi5(raw: bytes) -> np.ndarray:
    """Decoded ticks as a (n, 5) float array: ms, ask, bid, ask volume, bid volume (prices in Dukascopy's integer units)."""
    if not raw:
        return np.zeros((0, 5))
    data = lzma.decompress(raw)
    n = len(data) // REC.size
    if n == 0:
        return np.zeros((0, 5))
    a = np.frombuffer(data[: n * REC.size], dtype=np.dtype([("ms", ">u4"), ("ask", ">u4"), ("bid", ">u4"), ("av", ">f4"), ("bv", ">f4")]))
    return np.column_stack([a["ms"], a["ask"], a["bid"], a["av"], a["bv"]]).astype(float)


def hour_bars(ticks: np.ndarray, hour_start: pd.Timestamp) -> pd.DataFrame:
    """15-minute sums for one hour of ticks (up to 4 rows, indexed by bar open time)."""
    if len(ticks) == 0:
        return pd.DataFrame(columns=SUM_COLS, dtype=float)
    ms, ap, bp, av, bv = (ticks[:, k] for k in range(5))
    o = np.argsort(ms, kind="stable")
    ms, ap, bp, av, bv = ms[o], ap[o], bp[o], np.nan_to_num(av[o]), np.nan_to_num(bv[o])
    pbp, pap, pbv, pav = np.r_[np.nan, bp[:-1]], np.r_[np.nan, ap[:-1]], np.r_[0.0, bv[:-1]], np.r_[0.0, av[:-1]]
    e = (np.where(bp >= pbp, bv, 0.0) - np.where(bp <= pbp, pbv, 0.0)
         - np.where(ap <= pap, av, 0.0) + np.where(ap >= pap, pav, 0.0))
    e[0] = 0.0
    tot = av + bv
    q = np.where(tot > 0, (bv - av) / np.where(tot > 0, tot, 1.0), np.nan)
    mid = (ap + bp) / 2.0
    dm = np.r_[0.0, np.diff(mid)]
    k = np.minimum((ms // BAR_MS).astype(int), 3)
    g = pd.DataFrame({"k": k, "n": 1.0, "ofi": e, "depth": tot / 2.0, "qsum": np.nan_to_num(q), "qn": np.isfinite(q).astype(float),
                      "up": (dm > 0).astype(float), "down": (dm < 0).astype(float), "spread_sum": ap - bp})
    s = g.groupby("k").sum()
    last = pd.DataFrame({"k": k, "q": q, "mid": mid}).groupby("k").tail(1).set_index("k")   # the last tick, even if its q is NaN
    s["qlast"], s["mid_last"] = last["q"], last["mid"]
    s.index = [hour_start + pd.Timedelta(minutes=15 * int(x)) for x in s.index]
    return s[SUM_COLS]


# ---------------- download (the operator's laptop) ----------------
_local = threading.local()


def _session():
    import requests
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
        _local.s.headers.update(UA)
    return _local.s


def fetch_hour(t: pd.Timestamp, get=None) -> bytes | None:
    """Raw .bi5 bytes; b"" for an hour with no ticks (404 or empty file); None after RETRIES failures."""
    url = URL.format(sym=INSTRUMENT, y=t.year, m0=t.month - 1, d=t.day, h=t.hour)
    for attempt in range(RETRIES):
        try:
            r = (get or _session().get)(url, timeout=TIMEOUT)
        except OSError:                                    # requests' network errors are OSErrors: retried
            r = None
        if r is not None and r.status_code == 404:
            return b""
        if r is not None and r.status_code == 200:
            return r.content
        time.sleep(min(2 ** attempt, 20))
    return None


def day_hours(day: pd.Timestamp) -> list[pd.Timestamp]:
    return [] if day.dayofweek == 5 else [day + pd.Timedelta(hours=h) for h in range(24)]


def load_day(day: pd.Timestamp, cache: str, pool: ThreadPoolExecutor, get=None) -> tuple[pd.DataFrame | None, dict]:
    """One UTC day's 15-minute sums, from the cache or downloaded. None when any hour failed (retried on the next run)."""
    path = os.path.join(cache, "days", f"{day:%Y-%m-%d}.csv")
    if os.path.exists(path):
        df = pd.read_csv(path, index_col=0)
        df.index = pd.DatetimeIndex(pd.to_datetime(df.index, utc=True)).rename(None)
        return df.astype(float), {"cached": 1}
    hours = day_hours(day)
    futs = {pool.submit(fetch_hour, t, get): t for t in hours}
    parts, failed, empty = [], 0, 0
    for fu in as_completed(futs):
        raw = fu.result()
        if raw is None:
            failed += 1
        elif not raw:
            empty += 1
        else:
            try:
                parts.append(hour_bars(parse_bi5(raw), futs[fu]))
            except (lzma.LZMAError, ValueError):          # a truncated or non-LZMA reply: fetch again on the next run
                failed += 1
    if failed:
        return None, {"failed_hours": failed}
    df = pd.concat(parts).sort_index() if parts else pd.DataFrame(columns=SUM_COLS, dtype=float)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index_label="bar")
    return df, {"hours": len(hours), "empty_hours": empty}


def collect(start: pd.Timestamp, end: pd.Timestamp, cache: str, workers: int = WORKERS, get=None) -> tuple[pd.DataFrame, dict]:
    days = pd.date_range(start.normalize(), end.normalize(), freq="D", tz="UTC")
    parts, meta = [], {"days": len(days), "cached_days": 0, "hours": 0, "empty_hours": 0, "failed_days": 0}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, d in enumerate(days, 1):
            df, m = load_day(d, cache, pool, get)
            meta["cached_days"] += m.get("cached", 0)
            meta["hours"] += m.get("hours", 0)
            meta["empty_hours"] += m.get("empty_hours", 0)
            if df is None:
                meta["failed_days"] += 1
            elif len(df):
                parts.append(df)
            if i % 30 == 0 or i == len(days):
                print(f"  {d:%Y-%m-%d}: {i}/{len(days)} days ({meta['failed_days']} to retry)", flush=True)
    raw = pd.concat(parts).sort_index() if parts else pd.DataFrame(columns=SUM_COLS, dtype=float)
    raw = raw[~raw.index.duplicated(keep="first")]
    return raw[(raw.index >= start) & (raw.index < end)], meta


def research_data(cache: str, get=None) -> str:
    """The research-data branch (spot XAU/USD 15-minute bars), downloaded once from GitHub and unpacked under the cache."""
    root = os.path.join(cache, "research-data")
    if not os.path.isdir(root):
        r = (get or _session().get)(RD_ZIP, timeout=120)
        if r.status_code != 200:
            raise RuntimeError(f"could not download the research-data branch (HTTP {r.status_code})")
        tmp = root + ".part"
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            z.extractall(tmp)
        os.replace(tmp, root)                              # only a complete copy is ever used
    subs = [os.path.join(root, x) for x in os.listdir(root) if os.path.isdir(os.path.join(root, x))]
    return subs[0] if len(subs) == 1 else root


# ---------------- features ----------------
def finish_features(raw: pd.DataFrame, scale: float = 1.0) -> pd.DataFrame:
    """Rolling features from the 15-minute sums. Row i uses rows <= i only. scale = Dukascopy price units per dollar."""
    f = raw.sort_index().astype(float).copy()
    r = B._ratio
    f["ofi15"] = r(f["ofi"], f["depth"] / f["n"])
    n4, d4, o4, u4, w4 = (f[k].rolling(4, min_periods=4).sum() for k in ("n", "depth", "ofi", "up", "down"))
    f["ofi60"] = r(o4, d4 / n4)
    f["qimb15"] = r(f["qsum"], f["qn"])
    f["timb15"] = r(f["up"] - f["down"], f["up"] + f["down"])
    f["timb60"] = r(u4 - w4, u4 + w4)
    ln = np.log(f["n"].clip(lower=1.0))
    mu = ln.shift(1).rolling(B.Z_BARS, min_periods=200).mean()
    sd = ln.shift(1).rolling(B.Z_BARS, min_periods=200).std()
    f["ntr_z"] = r(ln - mu, sd)
    f["spread"] = f["spread_sum"] / f["n"] / scale
    f["mid"] = f["mid_last"] / scale
    return f


def price_scale(raw: pd.DataFrame, m15: pd.DataFrame) -> tuple[float, float, float]:
    """(units per dollar, median |gap| in $, median relative gap) from Dukascopy's last mid against the spot close."""
    j = pd.DataFrame({"mid": raw["mid_last"], "close": m15["close"]}).dropna()
    if len(j) < 100:
        raise RuntimeError(f"only {len(j)} bars overlap the spot paths; cannot check units")
    ratio = float(np.median(j["mid"] / j["close"]))
    scale = 10.0 ** round(math.log10(ratio))
    gap = (j["mid"] / scale - j["close"]).abs()
    return scale, float(gap.median()), float((gap / j["close"]).median())


def run(spot_dir: str, raw: pd.DataFrame, meta: dict) -> dict:
    m15 = H.partition(history.load(spot_dir, "XAU/USD", "15min"), "development")
    scale, gap_usd, gap_rel = price_scale(raw, m15)
    if gap_rel > ALIGN_MAX:
        raise RuntimeError(f"Dukascopy and the spot paths disagree by a median {gap_rel:.2%} (${gap_usd:.2f}); stopping")
    res = B.study(finish_features(raw, scale), m15, models=MODELS, rules=RULE_FEATURES, inputs=MODEL_FEATURES,
                  directional=DIRECTIONAL, q2=Q2)
    res.update({"set": "B5c", "partition": "development", "source": f"Dukascopy {INSTRUMENT} ticks (top of book)",
                "from": H.DEV[0].isoformat(), "to": H.DEV[1].isoformat(), "cost_usd": 0.0, "trades": None,
                "price_units_per_usd": scale, "median_gap_usd": gap_usd, "median_gap_rel": gap_rel, **meta})
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="B5c: order flow on Dukascopy's free spot-gold ticks (development data)")
    ap.add_argument("--cache", default=os.path.join(os.path.expanduser("~"), "b5c_cache"), help="local cache (not shared)")
    ap.add_argument("--out", default="b5c_results.json")
    ap.add_argument("--trials", default="b5c_trials.jsonl")
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--spot", help="an existing research-data checkout (default: download it from GitHub)")
    ap.add_argument("--allow-rerun", action="store_true")
    a = ap.parse_args(argv)
    if os.path.exists(a.trials) and not a.allow_rerun:
        raise SystemExit(f"{a.trials} already exists: B5c has been run here. Send {a.out} to Claude.")
    os.makedirs(a.cache, exist_ok=True)
    print("B5c: order flow on Dukascopy gold ticks, development data 2020-01-24 to 2023-01-24", flush=True)
    print(f"Cache (stays on this computer): {a.cache}", flush=True)
    spot = a.spot or research_data(a.cache)
    print("Downloading Dukascopy ticks (about 22,000 hourly files; the first run takes a while; it resumes if stopped)...", flush=True)
    raw, meta = collect(H.DEV[0], H.DEV[1], a.cache, a.workers)
    if meta["failed_days"]:
        print(f"\n{meta['failed_days']} days could not be downloaded completely. Run the same command again to resume.")
        return 2
    print(f"Ticks reduced to {len(raw)} bars. Running the declared tests...", flush=True)
    res = run(spot, raw, meta)
    for t in res["trials"]:
        H.log_trial(os.path.abspath(a.trials), {"phase": "B5c", "partition": "development", "data_hash": res["spot_data_hash"],
                                                "flow": f"Dukascopy/{INSTRUMENT}/top-of-book", **t,
                                                **({"model_report": res["models"][t["id"]]} if t["kind"] == "model" else {})})
    with open(a.out, "w") as f:
        json.dump(res, f, indent=1, default=float)
    print("\n" + B.summary(a.out))
    print(f"\nDone. Please send the file {os.path.abspath(a.out)} to Claude (it holds summary figures only).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
