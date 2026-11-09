"""Phase D extraction (research/registrations/PHASE_D.json, Workstream A): Dukascopy XAUUSD ticks -> per-15-minute
order-flow sums, per-minute bid / ask bars, and (optionally) intermarket mid bars. Runs on the operator's computer;
nothing it writes is committed (Dukascopy's terms restrict redistribution). Declared before any Dukascopy data.

    py -m quantum.research.d_dukascopy --period development        (then --period y2026; --stage intermarket optional)

Per hour file (B5c's decoder and downloader, unchanged):
  days/<day>.csv   B5c's own 15-minute sums (quantum/research/b5c_dukascopy.hour_bars), byte-for-byte what B5c writes,
                   so the registered B5c run (same --cache) reuses them without downloading again;
  dext/<day>.csv   the Phase D sums for the ten registered feature families (PD_COLS, below);
  m1/<day>.csv     one-minute bars of the best BID and the best ASK (open / high / low / close each) and the tick count:
                   the executable path for the bid / ask race (quantum/research/d_m1.py);
  inter/<SYM>/<day>.csv  (stage intermarket) 15-minute mid first / last / high / low and tick count per instrument.

PARTITIONS. development (2020-01-24 02:00 -> 2023-01-24 02:00 UTC) and y2026 (2026-01-01 00:00 UTC -> the last complete
UTC day, or --end). Any span touching the sealed validation / holdout period (2023-01-24 02:00 -> 2026-01-01 00:00 UTC)
is refused BEFORE any request is made (SealedPeriod); hours inside it are never fetched.

WHAT THE SOURCE IS. SWFX (Dukascopy's ECN) best bid and best offer, with the volume displayed at each, at every change.
It is top of book only: no depth beyond the best level, no traded volume, no trade sign. Feature names say "quote",
never "trade" or "order book depth".
"""
from __future__ import annotations

import argparse
import json
import lzma
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

from . import b5c_dukascopy as C
from . import harness as H

PERIODS = {"development": H.DEV, "y2026": (H.HOLD[1], None)}
SEALED = (H.VAL[0], H.HOLD[1])                    # validation + holdout: never fetched by Phase D
MIN_MS, HALF_MS, L5_MS = 60_000, 450_000, 600_000   # a minute; half a bar; the last five minutes start at 10:00
PD_COLS = ["spread_min", "spread_max", "spread_first", "spread_last", "spread_sq", "bid_up", "bid_dn", "ask_up", "ask_dn",
           "bv_sum", "av_sum", "path_abs", "rv", "mid_hi", "mid_lo", "flips", "run_max", "n_h1", "n_l5", "ofi_l5",
           "sw_up", "sw_dn", "sec_active", "ms_backwards"]          # ms_backwards: Phase D amendment A1 (d_clock)
M1_COLS = ["bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c", "n"]
MID_COLS = ["mid_first", "mid_last", "mid_hi", "mid_lo", "n"]
INTERMARKET = {"EURUSD": "EURUSD", "XAGUSD": "XAGUSD", "USDX": "DOLLARIDXUSD", "USTBOND": "USTBONDTRUSD"}
PROBE_HOUR = pd.Timestamp("2021-03-02 14:00", tz="UTC")     # a Tuesday afternoon: every listed instrument trades


class SealedPeriod(RuntimeError):
    """A requested span touches the sealed validation / holdout period."""


def check_span(start: pd.Timestamp, end: pd.Timestamp) -> None:
    if start < SEALED[1] and end > SEALED[0]:
        raise SealedPeriod(f"{start} -> {end} touches the sealed period {SEALED[0]} -> {SEALED[1]}; refused before any request")


def span(period: str, end: str | None = None, now: pd.Timestamp | None = None) -> tuple[pd.Timestamp, pd.Timestamp]:
    lo, hi = PERIODS[period]
    if hi is None:
        last_day = (now or pd.Timestamp.now(tz="UTC")).normalize()           # the last COMPLETE UTC day ends here
        hi = min(pd.Timestamp(end, tz="UTC"), last_day) if end else last_day
    check_span(lo, hi)
    return lo, hi


# ---------------- per-hour reducers ----------------
def _clean(ticks: np.ndarray) -> tuple[np.ndarray, ...]:
    ms = ticks[:, 0]
    keep = ms < C.HOUR_MS                                        # as B5c amendment A2: out-of-hour ticks are dropped
    t = ticks[keep]
    o = np.argsort(t[:, 0], kind="stable")
    t = t[o]
    return t[:, 0], t[:, 1], t[:, 2], np.nan_to_num(t[:, 3]), np.nan_to_num(t[:, 4])


def pd_sums(ticks: np.ndarray, hour_start: pd.Timestamp) -> pd.DataFrame:
    """The Phase D sums per 15-minute bar (prices in Dukascopy units; the scale is applied at the feature stage).
    Every figure uses ticks inside its bar, or the previous tick of the same hour file for a change: known at the close."""
    if len(ticks) == 0:
        return pd.DataFrame(columns=PD_COLS, dtype=float)
    ms, ap, bp, av, bv = _clean(ticks)
    if len(ms) == 0:
        return pd.DataFrame(columns=PD_COLS, dtype=float)
    k = (ms // C.BAR_MS).astype(int)
    sp = ap - bp
    mid = (ap + bp) / 2.0
    dm = np.r_[0.0, np.diff(mid)]
    dbp, dap, dsp = np.r_[0.0, np.diff(bp)], np.r_[0.0, np.diff(ap)], np.r_[0.0, np.diff(sp)]
    pbp, pap, pbv, pav = np.r_[np.nan, bp[:-1]], np.r_[np.nan, ap[:-1]], np.r_[0.0, bv[:-1]], np.r_[0.0, av[:-1]]
    e = (np.where(bp >= pbp, bv, 0.0) - np.where(bp <= pbp, pbv, 0.0) - np.where(ap <= pap, av, 0.0) + np.where(ap >= pap, pav, 0.0))
    e[0] = 0.0                                                   # as B5c: the first tick of an hour file counts 0
    in_bar = ms - k * C.BAR_MS
    l5 = in_bar >= L5_MS
    g = pd.DataFrame({"k": k, "spread_sq": sp * sp, "bid_up": (dbp > 0) * 1.0, "bid_dn": (dbp < 0) * 1.0, "ask_up": (dap > 0) * 1.0,
                      "ask_dn": (dap < 0) * 1.0, "bv_sum": bv, "av_sum": av, "path_abs": np.abs(dm), "rv": dm * dm,
                      "n_h1": (in_bar < HALF_MS) * 1.0, "n_l5": l5 * 1.0, "ofi_l5": np.where(l5, e, 0.0),
                      "sw_up": (dsp > 0) * 1.0, "sw_dn": (dsp < 0) * 1.0})
    s = g.groupby("k").sum()
    gk = pd.DataFrame({"k": k, "sp": sp, "mid": mid}).groupby("k")
    s["spread_min"], s["spread_max"] = gk["sp"].min(), gk["sp"].max()
    s["spread_first"], s["spread_last"] = gk["sp"].first(), gk["sp"].last()
    s["mid_hi"], s["mid_lo"] = gk["mid"].max(), gk["mid"].min()
    s["sec_active"] = pd.DataFrame({"k": k, "sec": ms // 1000}).groupby("k")["sec"].nunique().astype(float)
    ms0 = ticks[ticks[:, 0] < C.HOUR_MS, 0]                       # file order, before the sort: stamps that run backwards
    back = pd.Series(np.r_[0.0, (np.diff(ms0) < 0).astype(float)]).groupby((ms0 // C.BAR_MS).astype(int)).sum()
    s["ms_backwards"] = back.reindex(s.index).fillna(0.0)
    nz = dm != 0                                                 # direction runs: consecutive non-zero mid changes
    sgn, kk = np.sign(dm[nz]), k[nz]
    if len(sgn):
        new_run = np.r_[True, (sgn[1:] != sgn[:-1]) | (kk[1:] != kk[:-1])]
        rid = np.cumsum(new_run)
        runs = pd.DataFrame({"k": kk, "rid": rid}).groupby(["k", "rid"]).size()
        s["run_max"] = runs.groupby(level="k").max().astype(float)
        s["flips"] = (runs.groupby(level="k").size() - 1).astype(float)
    s["run_max"] = s.get("run_max", pd.Series(dtype=float)).reindex(s.index).fillna(0.0)
    s["flips"] = s.get("flips", pd.Series(dtype=float)).reindex(s.index).fillna(0.0)
    s.index = [hour_start + pd.Timedelta(minutes=15 * int(x)) for x in s.index]
    return s[PD_COLS].astype(float)


def m1_bars(ticks: np.ndarray, hour_start: pd.Timestamp) -> pd.DataFrame:
    """One-minute best-bid and best-ask OHLC and the tick count; minutes without ticks have no row (never filled)."""
    if len(ticks) == 0:
        return pd.DataFrame(columns=M1_COLS, dtype=float)
    ms, ap, bp, _, _ = _clean(ticks)
    if len(ms) == 0:
        return pd.DataFrame(columns=M1_COLS, dtype=float)
    k = (ms // MIN_MS).astype(int)
    g = pd.DataFrame({"k": k, "b": bp, "a": ap}).groupby("k")
    out = pd.DataFrame({"bid_o": g["b"].first(), "bid_h": g["b"].max(), "bid_l": g["b"].min(), "bid_c": g["b"].last(),
                        "ask_o": g["a"].first(), "ask_h": g["a"].max(), "ask_l": g["a"].min(), "ask_c": g["a"].last(),
                        "n": g["b"].size().astype(float)})
    out.index = [hour_start + pd.Timedelta(minutes=int(x)) for x in out.index]
    return out[M1_COLS].astype(float)


def mid_bars(ticks: np.ndarray, hour_start: pd.Timestamp) -> pd.DataFrame:
    """15-minute mid first / last / high / low and tick count (intermarket instruments)."""
    if len(ticks) == 0:
        return pd.DataFrame(columns=MID_COLS, dtype=float)
    ms, ap, bp, _, _ = _clean(ticks)
    if len(ms) == 0:
        return pd.DataFrame(columns=MID_COLS, dtype=float)
    g = pd.DataFrame({"k": (ms // C.BAR_MS).astype(int), "m": (ap + bp) / 2.0}).groupby("k")["m"]
    out = pd.DataFrame({"mid_first": g.first(), "mid_last": g.last(), "mid_hi": g.max(), "mid_lo": g.min(), "n": g.size().astype(float)})
    out.index = [hour_start + pd.Timedelta(minutes=15 * int(x)) for x in out.index]
    return out[MID_COLS].astype(float)


# ---------------- days ----------------
def _write(df: pd.DataFrame, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    df.to_csv(tmp, index_label="bar")
    os.replace(tmp, path)                                        # a day file is either complete or absent


def _read(path: str, cols: list[str]) -> pd.DataFrame | None:
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, index_col=0)
    if not set(cols) <= set(df.columns):
        return None
    df.index = pd.DatetimeIndex(pd.to_datetime(df.index, utc=True)).rename(None)
    return df.astype(float)


def sealed_hour(t: pd.Timestamp) -> bool:
    return SEALED[0] <= t < SEALED[1] or SEALED[0] < t + pd.Timedelta(hours=1) <= SEALED[1]


def hours_of(day: pd.Timestamp, start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    """The day's hour files inside [start, end) and wholly outside the sealed period (the boundary day 2023-01-24 keeps
    00:00 and 01:00 only). Saturdays have none (B5c)."""
    return [t for t in C.day_hours(day) if start <= t and t + pd.Timedelta(hours=1) <= end and not sealed_hour(t)]


def load_day(day: pd.Timestamp, cache: str, pool: ThreadPoolExecutor, fetch=None, start: pd.Timestamp | None = None,
             end: pd.Timestamp | None = None) -> tuple[dict | None, dict]:
    """One UTC day: {"days", "dext", "m1"} frames from the cache, or downloaded (only hours in [start, end) outside the
    sealed period). None when any hour failed."""
    start = start if start is not None else day
    end = end if end is not None else day + pd.Timedelta(days=1)
    hours = hours_of(day, start, end)
    paths = {k: os.path.join(cache, k, f"{day:%Y-%m-%d}.csv") for k in ("days", "dext", "m1")}
    cols = {"days": C.SUM_COLS, "dext": PD_COLS, "m1": M1_COLS}
    have = {k: _read(p, cols[k]) for k, p in paths.items()}
    if all(v is not None for v in have.values()):
        return have, {"cached": 1}
    fetch = fetch or C.fetch_hour
    futs = {pool.submit(fetch, t): t for t in hours}
    parts, failed, empty = {"days": [], "dext": [], "m1": []}, 0, 0
    for fu in as_completed(futs):
        raw = fu.result()
        if raw is None:
            failed += 1
        elif not raw:
            empty += 1
        else:
            try:
                tk = C.parse_bi5(raw)
            except (lzma.LZMAError, ValueError):
                failed += 1
                continue
            t = futs[fu]
            parts["days"].append(C.hour_bars(tk, t))
            parts["dext"].append(pd_sums(tk, t))
            parts["m1"].append(m1_bars(tk, t))
    if failed:
        return None, {"failed_hours": failed}
    out = {k: (pd.concat(v).sort_index() if v else pd.DataFrame(columns=cols[k], dtype=float)) for k, v in parts.items()}
    for k in ("dext", "m1", "days"):                             # B5c's file last: it marks the day complete for B5c too
        _write(out[k], paths[k])
    return out, {"hours": len(hours), "empty_hours": empty}


def collect(start: pd.Timestamp, end: pd.Timestamp, cache: str, workers: int = C.WORKERS, fetch=None, log=print) -> tuple[dict, dict]:
    check_span(start, end)
    days = pd.date_range(start.normalize(), (end - pd.Timedelta(seconds=1)).normalize(), freq="D", tz="UTC")
    acc, meta = {"days": [], "dext": [], "m1": []}, {"days": len(days), "cached_days": 0, "hours": 0, "empty_hours": 0, "failed_days": 0}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, d in enumerate(days, 1):
            fr, m = load_day(d, cache, pool, fetch, start, end)
            meta["cached_days"] += m.get("cached", 0)
            meta["hours"] += m.get("hours", 0)
            meta["empty_hours"] += m.get("empty_hours", 0)
            if fr is None:
                meta["failed_days"] += 1
            else:
                for k, lst in acc.items():
                    if len(fr[k]):
                        lst.append(fr[k])
            if i % 30 == 0 or i == len(days):
                log(f"  {d:%Y-%m-%d}: {i}/{len(days)} days ({meta['failed_days']} to retry)")
    out = {}
    for k, v in acc.items():
        df = pd.concat(v).sort_index() if v else pd.DataFrame(dtype=float)
        df = df[~df.index.duplicated(keep="first")]
        out[k] = df[(df.index >= start) & (df.index < end)] if len(df) else df
    return out, meta


def probe_intermarket(get=None) -> dict:
    """Which intermarket instruments Dukascopy serves: one hour each. Unavailable ones are reported, never substituted."""
    out = {}
    for name, sym in INTERMARKET.items():
        raw = fetch_sym(sym, PROBE_HOUR, get)
        ok = False
        if raw:
            try:
                ok = len(C.parse_bi5(raw)) > 0
            except (lzma.LZMAError, ValueError):
                ok = False
        out[name] = {"symbol": sym, "available": bool(ok)}
    return out


def fetch_sym(sym: str, t: pd.Timestamp, get=None) -> bytes | None:
    """B5c's fetch_hour for another instrument (same retries; b"" for no ticks; None after RETRIES failures)."""
    if sealed_hour(t):
        raise SealedPeriod(f"{t} is in the sealed period")
    url = C.URL.format(sym=sym, y=t.year, m0=t.month - 1, d=t.day, h=t.hour)
    for attempt in range(C.RETRIES):
        try:
            r = (get or C._session().get)(url, timeout=C.TIMEOUT)
        except OSError:
            r = None
        if r is not None and r.status_code == 404:
            return b""
        if r is not None and r.status_code == 200:
            return r.content
        C.time.sleep(min(2 ** attempt, 20))
    return None


def collect_intermarket(sym: str, start: pd.Timestamp, end: pd.Timestamp, cache: str, get=None, log=print) -> dict:
    """One instrument, one hour at a time (light files); resumable per day."""
    check_span(start, end)
    days = pd.date_range(start.normalize(), (end - pd.Timedelta(seconds=1)).normalize(), freq="D", tz="UTC")
    meta = {"days": len(days), "failed_days": 0, "cached_days": 0}
    for i, d in enumerate(days, 1):
        p = os.path.join(cache, "inter", sym, f"{d:%Y-%m-%d}.csv")
        if _read(p, MID_COLS) is not None:
            meta["cached_days"] += 1
            continue
        parts, failed = [], 0
        for t in hours_of(d, start, end):
            raw = fetch_sym(sym, t, get)
            if raw is None:
                failed += 1
            elif raw:
                try:
                    parts.append(mid_bars(C.parse_bi5(raw), t))
                except (lzma.LZMAError, ValueError):
                    failed += 1
        if failed:
            meta["failed_days"] += 1
            continue
        _write(pd.concat(parts).sort_index() if parts else pd.DataFrame(columns=MID_COLS, dtype=float), p)
        if i % 30 == 0:
            log(f"  {sym} {d:%Y-%m-%d}: {i}/{len(days)}")
    return meta


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Phase D: Dukascopy extraction (stays on this computer)")
    ap.add_argument("--period", choices=sorted(PERIODS), required=True)
    ap.add_argument("--end", help="y2026 only: last day (exclusive), default the last complete UTC day")
    ap.add_argument("--cache", default=os.path.join(os.path.expanduser("~"), "b5c_cache"),
                    help="local cache shared with B5c (not committed, not shared)")
    ap.add_argument("--stage", choices=("gold", "intermarket"), default="gold")
    ap.add_argument("--workers", type=int, default=C.WORKERS)
    a = ap.parse_args(argv)
    start, end = span(a.period, a.end)
    os.makedirs(a.cache, exist_ok=True)
    print(f"Phase D extraction: {a.stage}, {a.period} {start} -> {end}. Cache (stays here): {a.cache}", flush=True)
    if a.stage == "intermarket":
        pr = probe_intermarket()
        print(json.dumps(pr), flush=True)
        meta = {n: (collect_intermarket(v["symbol"], start, end, a.cache) if v["available"] else {"available": False}) for n, v in pr.items()}
        failed = sum(m.get("failed_days", 0) for m in meta.values())
    else:
        out, meta = collect(start, end, a.cache, a.workers)
        failed = meta["failed_days"]
        meta.update({"bars_15m": len(out["days"]), "minutes": len(out["m1"])})
    with open(os.path.join(a.cache, f"phase_d_extract_{a.stage}_{a.period}.json"), "w") as fh:
        json.dump({"period": a.period, "start": str(start), "end": str(end), **meta}, fh, indent=1, default=float)
    if failed:
        print(f"{failed} days are incomplete. Run the same command again to resume.")
        return 2
    print("Extraction complete. Nothing here is uploaded or committed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
