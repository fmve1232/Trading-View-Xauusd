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
  Timestamps (amendment A1, 2026-11-09, before any Dukascopy data): the run also stops unless the correlation of
  15-minute mid changes with the spot close changes peaks at lag 0 (of -2..+2 bars) and is at least 0.8.
  Registration: research/registrations/B5C.json.
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
LAGS = (-2, -1, 0, 1, 2)          # bars; amendment A1 (2026-11-09, before any Dukascopy data): timestamp alignment check
LAG_MIN_CORR = 0.8
WORKERS, RETRIES, TIMEOUT = 6, 5, 30
SUM_COLS = ["n", "ofi", "depth", "qsum", "qn", "qlast", "up", "down", "spread_sum", "mid_last",
            "mid_first", "dup_ms", "crossed", "max_gap_s", "out_of_hour"]          # the last five: amendment A2 (integrity)
HOUR_MS = 3_600_000
SESSIONS_UTC = (("ASIA", 0, 7), ("LONDON", 7, 12), ("NY", 12, 21), ("OFF", 21, 24))   # UTC hours, for the alignment report
STALE_S = 300.0                   # a bar whose ticks are more than 5 minutes apart somewhere is "stale"
DAY_MAX_BASIS = 0.005             # a day whose median |basis| exceeds 0.5% of the price is quarantined
DAY_MIN_CORR, DAY_MIN_BARS = 0.5, 20
MAX_QUARANTINE, MAX_CROSSED, MAX_OUT_OF_HOUR = 0.05, 0.01, 0.001
GROUP_MIN_BARS = 500
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
    out_hour = ms >= HOUR_MS                               # amendment A2: never clamped into the last bar; counted, dropped
    n_out = int(out_hour.sum())
    ms, ap, bp, av, bv = ms[~out_hour], ap[~out_hour], bp[~out_hour], av[~out_hour], bv[~out_hour]
    if len(ms) == 0:
        return pd.DataFrame(columns=SUM_COLS, dtype=float)
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
    k = (ms // BAR_MS).astype(int)
    dup = np.r_[0.0, (np.diff(ms) == 0).astype(float)]
    gap = np.r_[ms[0] - k[0] * BAR_MS, np.diff(ms)]                                # from the bar start for each bar's first tick
    first = np.r_[True, k[1:] != k[:-1]]
    gap = np.where(first, ms - k * BAR_MS, gap) / 1000.0
    g = pd.DataFrame({"k": k, "n": 1.0, "ofi": e, "depth": tot / 2.0, "qsum": np.nan_to_num(q), "qn": np.isfinite(q).astype(float),
                      "up": (dm > 0).astype(float), "down": (dm < 0).astype(float), "spread_sum": ap - bp,
                      "dup_ms": dup, "crossed": (ap <= bp).astype(float)})
    s = g.groupby("k").sum()
    last = pd.DataFrame({"k": k, "q": q, "mid": mid}).groupby("k").tail(1).set_index("k")   # the last tick, even if its q is NaN
    s["qlast"], s["mid_last"] = last["q"], last["mid"]
    s["mid_first"] = pd.DataFrame({"k": k, "mid": mid}).groupby("k").head(1).set_index("k")["mid"]
    tail = pd.DataFrame({"k": k, "ms": ms}).groupby("k")["ms"].max()
    s["max_gap_s"] = np.maximum(pd.DataFrame({"k": k, "gap": gap}).groupby("k")["gap"].max(),
                                ((tail.index.to_numpy() + 1) * BAR_MS - tail.to_numpy()) / 1000.0)
    s["out_of_hour"] = 0.0
    if n_out:
        s.loc[s.index.max(), "out_of_hour"] = float(n_out)                       # booked on the hour's last bar with ticks
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
    """The day's hour files, Saturdays excepted. Amendment A3: never an hour inside the sealed validation / holdout span
    (before A3 the boundary day 2023-01-24 fetched 22 sealed hours and discarded them unread; results are unchanged)."""
    if day.day_of_week == 5:
        return []
    hrs = [day + pd.Timedelta(hours=h) for h in range(24)]
    return [t for t in hrs if not (H.VAL[0] <= t < H.HOLD[1])]


def load_day(day: pd.Timestamp, cache: str, pool: ThreadPoolExecutor, get=None) -> tuple[pd.DataFrame | None, dict]:
    """One UTC day's 15-minute sums, from the cache or downloaded. None when any hour failed (retried on the next run)."""
    path = os.path.join(cache, "days", f"{day:%Y-%m-%d}.csv")
    if os.path.exists(path):
        df = pd.read_csv(path, index_col=0)
        if set(SUM_COLS) <= set(df.columns):                 # a cache written before amendment A2 is fetched again
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


def lag_check(raw: pd.DataFrame, m15: pd.DataFrame, scale: float) -> dict:
    """Timestamp alignment (amendment A1): the correlation of 15-minute changes of Dukascopy's last mid with the spot
    path's close changes, with Dukascopy shifted by k bars (k in LAGS). Aligned bars peak at k = 0."""
    mid = (raw["mid_last"] / scale).reindex(m15.index)
    dm, ds = mid.diff(), m15["close"].diff()
    corr = {}
    for k in LAGS:
        j = pd.concat([dm.shift(k), ds], axis=1).dropna()
        corr[k] = float(j.iloc[:, 0].corr(j.iloc[:, 1])) if len(j) > 100 else math.nan
    ok = {k: v for k, v in corr.items() if not math.isnan(v)}
    return {"corr_by_lag_bars": corr, "best_lag_bars": max(ok, key=ok.get) if ok else None}


class IntegrityError(RuntimeError):
    """The data failed a registered integrity gate (amendment A2); .report holds every figure."""

    def __init__(self, report: dict):
        super().__init__("; ".join(report["failures"]))
        self.report = report


def _session_of(idx: pd.DatetimeIndex) -> np.ndarray:
    """UTC session label per bar (amendment A2's alignment report). Named apart from _session(), the HTTP session:
    the two shared one name until amendment A3, which made every real download fail (TypeError)."""
    h = idx.hour
    return np.select([(h >= a) & (h < b) for _, a, b in SESSIONS_UTC], [nm for nm, _, _ in SESSIONS_UTC], "OFF")


def _lag_corr(dm: pd.Series, ds: pd.Series, mask: np.ndarray) -> dict:
    out = {}
    for k in LAGS:
        j = pd.concat([dm.shift(k), ds], axis=1)[mask].dropna()
        out[k] = float(j.iloc[:, 0].corr(j.iloc[:, 1])) if len(j) > 100 else math.nan
    ok = {k: v for k, v in out.items() if not math.isnan(v)}
    return {"corr_by_lag_bars": out, "best_lag_bars": max(ok, key=ok.get) if ok else None, "bars": int(mask.sum())}


def _q(x: pd.Series) -> dict:
    x = x.dropna()
    return {f"p{round(p * 100):02d}": float(x.quantile(p)) for p in (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)} if len(x) else {}


def _week_edges(idx: pd.DatetimeIndex) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """Weekly opens / closes: the first bar after, and the last bar before, a gap of more than 24 hours."""
    if len(idx) < 2:
        return idx[:0], idx[:0]
    gap = idx[1:] - idx[:-1] > pd.Timedelta(hours=24)
    return idx[1:][gap], idx[:-1][gap]


def integrity_report(raw: pd.DataFrame, m15: pd.DataFrame, scale: float) -> dict:
    """Amendment A2 (2026-11-09, before any Dukascopy data): the data's integrity and clock, measured and gated BEFORE any
    test. Days that fail are quarantined (their bars set to missing); timestamps are never shifted."""
    idx = m15.index
    j = raw.reindex(idx)
    mid_l, mid_f = j["mid_last"] / scale, j["mid_first"] / scale
    basis_c, basis_o = mid_l - m15["close"], mid_f - m15["open"]
    dm, ds = mid_l.diff(), m15["close"].diff()
    sess = _session_of(idx)
    allm = np.ones(len(idx), bool)
    lag = {"overall": _lag_corr(dm, ds, allm), "by_session": {nm: _lag_corr(dm, ds, sess == nm) for nm, _, _ in SESSIONS_UTC},
           "by_year": {int(y): _lag_corr(dm, ds, idx.year == y) for y in sorted(set(idx.year))}}
    best = lag["overall"]["best_lag_bars"]
    has = j["n"].fillna(0) > 0
    n_ticks = float(raw["n"].sum())
    stale = (raw["max_gap_s"] > STALE_S) & (raw["n"] > 0)
    d_open_s, d_close_s = _week_edges(idx)
    d_open_d, d_close_d = _week_edges(raw.index[raw["n"] > 0])

    def edge_diff(a, b):
        if len(a) == 0 or len(b) == 0:
            return {}
        an = np.asarray(a.tz_convert("UTC").tz_localize(None), dtype="datetime64[ns]").astype(np.int64)
        bn = np.asarray(b.tz_convert("UTC").tz_localize(None), dtype="datetime64[ns]").astype(np.int64)
        if len(bn) == 1:
            near = np.full(len(an), bn[0])
        else:
            pos = np.clip(np.searchsorted(bn, an), 1, len(bn) - 1)
            near = np.where(np.abs(bn[pos] - an) < np.abs(bn[pos - 1] - an), bn[pos], bn[pos - 1])
        dmin = (near - an) / 6e10
        return {"weeks": len(a), "median_min": float(np.median(dmin)), "max_abs_min": float(np.max(np.abs(dmin))),
                "share_within_15min": float(np.mean(np.abs(dmin) <= 15))}

    day = idx.normalize()
    dd = pd.DataFrame({"day": day, "rel": (basis_c / m15["close"]).abs(), "dm": dm, "ds": ds}).dropna()
    quarantine = []
    for d_, g in dd.groupby("day"):
        if len(g) >= DAY_MIN_BARS and (g["rel"].median() > DAY_MAX_BASIS or g["dm"].corr(g["ds"]) < DAY_MIN_CORR):
            quarantine.append(str(pd.Timestamp(d_).date()))
    days_with = dd["day"].nunique()
    rep = {
        "lags": lag, "best_lag_bars": best, "offset_minutes": None if best is None else 15 * best,
        "basis_close_usd": _q(basis_c), "basis_open_usd": _q(basis_o),
        "basis_close_by_session_usd": {nm: _q(basis_c[sess == nm]) for nm, _, _ in SESSIONS_UTC},
        "timestamps": {"dukascopy": "UTC hour files + ms; no conversion", "spot": "UTC, bar open time",
                       "weekly_open": edge_diff(d_open_s, d_open_d), "weekly_close": edge_diff(d_close_s, d_close_d)},
        "missing": {"spot_bars": len(idx), "spot_bars_without_ticks": int((~has).sum()),
                    "share": float((~has).mean()) if len(idx) else None,
                    "by_session": {nm: float((~has[sess == nm]).mean()) for nm, _, _ in SESSIONS_UTC if (sess == nm).any()},
                    "dukascopy_bars_outside_spot": int((~raw.index.isin(idx) & (raw["n"] > 0)).sum())},
        "ticks": {"total": n_ticks, "duplicate_ms_share": float(raw["dup_ms"].sum() / n_ticks) if n_ticks else None,
                  "crossed_share": float(raw["crossed"].sum() / n_ticks) if n_ticks else None,
                  "out_of_hour_share": float(raw["out_of_hour"].sum() / n_ticks) if n_ticks else None,
                  "stale_bar_share": float(stale.mean()) if len(raw) else None},
        "quarantined_days": quarantine, "quarantined_share": len(quarantine) / days_with if days_with else 0.0,
    }
    f = []
    r0 = lag["overall"]["corr_by_lag_bars"].get(0)
    if best != 0 or not (r0 is not None and r0 >= LAG_MIN_CORR):
        f.append(f"overall clock: best lag {best} bars, r(0) = {r0}")
    for grp in ("by_session", "by_year"):
        for k, v in lag[grp].items():
            if v["bars"] >= GROUP_MIN_BARS and v["best_lag_bars"] not in (0, None):
                f.append(f"clock {grp} {k}: best lag {v['best_lag_bars']} bars")
    if rep["quarantined_share"] > MAX_QUARANTINE:
        f.append(f"{rep['quarantined_share']:.1%} of days quarantined (> {MAX_QUARANTINE:.0%})")
    t = rep["ticks"]
    if (t["crossed_share"] or 0) > MAX_CROSSED:
        f.append(f"crossed quotes {t['crossed_share']:.2%}")
    if (t["out_of_hour_share"] or 0) > MAX_OUT_OF_HOUR:
        f.append(f"ticks outside their hour file {t['out_of_hour_share']:.3%}")
    wo = rep["timestamps"]["weekly_open"]
    if wo and abs(wo["median_min"]) > 15:
        f.append(f"weekly opens differ by a median {wo['median_min']:.0f} minutes (time zone)")
    rep["failures"] = f
    return rep


def quarantine(raw: pd.DataFrame, days: list[str]) -> pd.DataFrame:
    """Quarantined days' bars become missing (NaN); nothing is shifted or filled."""
    q = raw.copy()
    m = q.index.normalize().isin(pd.to_datetime(days).tz_localize("UTC")) if days else np.zeros(len(q), bool)
    q.loc[m, :] = np.nan
    return q


def run(spot_dir: str, raw: pd.DataFrame, meta: dict) -> dict:
    m15 = H.partition(history.load(spot_dir, "XAU/USD", "15min"), "development")
    scale, gap_usd, gap_rel = price_scale(raw, m15)
    if gap_rel > ALIGN_MAX:
        raise RuntimeError(f"Dukascopy and the spot paths disagree by a median {gap_rel:.2%} (${gap_usd:.2f}); stopping")
    integ = integrity_report(raw, m15, scale)
    if integ["failures"]:
        raise IntegrityError(integ)
    lag = lag_check(raw, m15, scale)
    raw = quarantine(raw, integ["quarantined_days"])
    res = B.study(finish_features(raw, scale), m15, models=MODELS, rules=RULE_FEATURES, inputs=MODEL_FEATURES,
                  directional=DIRECTIONAL, q2=Q2)
    res.update({"set": "B5c", "partition": "development", "source": f"Dukascopy {INSTRUMENT} ticks (top of book)",
                "from": H.DEV[0].isoformat(), "to": H.DEV[1].isoformat(), "cost_usd": 0.0, "trades": None,
                "price_units_per_usd": scale, "median_gap_usd": gap_usd, "median_gap_rel": gap_rel, "alignment": lag, "integrity": integ, **meta})
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
    print(f"Ticks reduced to {len(raw)} bars. Checking the data, then running the declared tests...", flush=True)
    integ_path = os.path.splitext(a.out)[0] + "_integrity.json"
    try:
        res = run(spot, raw, meta)
    except IntegrityError as e:
        with open(integ_path, "w") as f:
            json.dump(e.report, f, indent=1, default=float)
        print(f"\nSTOPPED: the data failed a registered integrity check ({e}). No test was run.")
        print(f"Please send {os.path.abspath(integ_path)} to Claude.")
        return 3
    with open(integ_path, "w") as f:
        json.dump(res["integrity"], f, indent=1, default=float)
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
