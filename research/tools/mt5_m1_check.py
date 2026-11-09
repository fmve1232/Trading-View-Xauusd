"""Validate an MT5 M1 bar export before any research uses it (research only; the file stays on the operator's computer).

MT5 terminal: View -> Symbols (Ctrl+U) -> Bars -> XAUUSD, M1, date range -> Request -> Export Bars. The export has the
header <DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <VOL> <SPREAD>, dates YYYY.MM.DD, times HH:MM[:SS], in the
broker's SERVER time, prices from the BID side, spread in points (research/PHASE_D_DATA_REQUIREMENTS.md section 3).

Phase D version (2026-11-09, before any MT5 data; the Phase C version's defects are listed in research/PHASE_D_PLAN.md
section 2.3):
  * reads UTF-16 (MT5's usual "Unicode" export, with or without a BOM), UTF-8 and UTF-8 with a BOM; tab, comma or
    semicolon separated; header names with or without <>; explicit date formats (no guessing); every unparsed row counted;
  * server time -> UTC by an IANA zone (--server-tz Europe/Athens), the common "New York + 7" convention
    (--server-tz NY+7: GMT+2 / GMT+3 switching on the US dates, so that 17:00 New York = 00:00 server), or a fixed
    --offset-hours. Rows that do not exist or are ambiguous in that zone are dropped and counted, never guessed;
  * PARTITION GUARD: only development (2020-01-24 02:00 -> 2023-01-24 02:00 UTC) and 2026 (from 2026-01-01 00:00 UTC)
    are kept. Rows in the sealed validation / holdout span are dropped immediately after the UTC conversion and only
    counted; no other figure is computed on them;
  * integrity: duplicates, order, OHLC consistency, non-positive prices, Saturday bars, bars inside New York's
    17:00-18:00 daily break, gap classes, price discontinuities (consecutive minutes), range spikes, a price-scale
    (digits) change between months, and coverage by month and year against the trading schedule;
  * broker identification (--broker, --symbol, --point, --contract-oz are recorded; nothing is assumed when absent),
    with the point inferred from the prices' decimals and the spread in $ only when the point is known;
  * the clock (with --reference or --reference-rd): the correlation of 15-minute close changes peaks at a shift of 0
    hours overall AND in every ISO week with enough bars (a daylight-saving convention mismatch shows as misaligned
    weeks in March / October-November); the per-month median close basis against the reference;
  * --suggest-zone prints how many weeks each common convention misaligns. It is information for the operator to
    confirm with the broker; it is never applied automatically and the timestamps are never shifted.
Writes a JSON report; with --write-utc (only when USABLE), a normalised UTC CSV of the kept rows and a sidecar JSON.

  python research/tools/mt5_m1_check.py --file XAUUSD_M1.csv --server-tz NY+7 --broker "<name>" --symbol XAUUSD \
      [--point 0.01] [--reference-rd <research-data checkout>] [--report m1_report.json] [--write-utc m1_utc.csv]
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import sys

import numpy as np
import pandas as pd

COLS = ["<DATE>", "<TIME>", "<OPEN>", "<HIGH>", "<LOW>", "<CLOSE>", "<TICKVOL>", "<VOL>", "<SPREAD>"]
NEED = ("DATE", "TIME", "OPEN", "HIGH", "LOW", "CLOSE", "TICKVOL", "SPREAD")
DATE_FORMATS = ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M")
LAGS_H = tuple(range(-4, 5))
NY_PLUS_7 = ("NY+7", "NY7", "NEWYORK+7")
DEV = (pd.Timestamp("2020-01-24 02:00", tz="UTC"), pd.Timestamp("2023-01-24 02:00", tz="UTC"))
SEALED = (pd.Timestamp("2023-01-24 02:00", tz="UTC"), pd.Timestamp("2026-01-01 00:00", tz="UTC"))   # validation + holdout
Y2026 = pd.Timestamp("2026-01-01 00:00", tz="UTC")
JUMP_REL = 0.001          # |open - previous close| > 0.1% of the price between consecutive minutes: a discontinuity
SPIKE_REL = 0.01          # a one-minute range above 1% of the price: a spike
MAX_JUMP_SHARE = 0.001    # USABLE only if discontinuities are at most 0.1% of consecutive pairs
WEEK_MIN_BARS = 200       # a week enters the clock check with at least this many overlapping 15-minute bars
COVERAGE_FLAG = 0.90
SCALE_JUMP = 0.20         # a month whose median close differs from the previous month's by > 20%: a digits change
ZONES = ("NY+7", "Europe/Athens", "Europe/London", "Europe/Berlin", "Etc/GMT-2", "Etc/GMT-3", "UTC")


# ---------------- reading ----------------
def _decode(raw: bytes) -> tuple[str, str]:
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16"), "utf-16 (BOM)"
    if raw[:3] == b"\xef\xbb\xbf":
        return raw[3:].decode("utf-8"), "utf-8 (BOM)"
    head = raw[:4000]
    if head and head[1::2].count(0) > 0.4 * len(head[1::2]):
        return raw.decode("utf-16-le"), "utf-16-le (no BOM)"
    if head and head[0::2].count(0) > 0.4 * len(head[0::2]):
        return raw.decode("utf-16-be"), "utf-16-be (no BOM)"
    return raw.decode("utf-8"), "utf-8"


def _sep(header: str) -> str:
    counts = {s: header.count(s) for s in ("\t", ",", ";")}
    best = max(counts, key=counts.get)
    if counts[best] < 5:
        raise ValueError(f"not an MT5 bar export: cannot find a separator in the header {header[:80]!r}")
    return best


def read_export(path_or_buf, meta: dict | None = None) -> pd.DataFrame:
    """The export as bars indexed by SERVER time (naive). meta, if given, receives the encoding, separator, date format
    and the number of rows that could not be parsed."""
    if isinstance(path_or_buf, (str, os.PathLike)):
        with open(path_or_buf, "rb") as fh:
            raw = fh.read()
    else:
        raw = path_or_buf.read()
        raw = raw.encode("utf-8") if isinstance(raw, str) else raw
    text, enc = _decode(raw)
    text = text.lstrip("﻿")
    first = text.split("\n", 1)[0]
    sep = _sep(first)
    df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, skipinitialspace=True)
    df.columns = [str(c).strip().strip("<>").upper() for c in df.columns]
    missing = [c for c in NEED if c not in df.columns]
    if missing:
        raise ValueError(f"not an MT5 bar export: missing columns {missing}")
    stamp = (df["DATE"].str.strip() + " " + df["TIME"].str.strip())
    best_fmt, best_t, best_bad = None, None, None
    for fmt in DATE_FORMATS:
        t = pd.to_datetime(stamp, format=fmt, errors="coerce")
        bad = int(t.isna().sum())
        if best_bad is None or bad < best_bad:
            best_fmt, best_t, best_bad = fmt, t, bad
        if bad == 0:
            break
    num = {c: pd.to_numeric(df[c].str.strip(), errors="coerce") for c in ("OPEN", "HIGH", "LOW", "CLOSE", "TICKVOL", "SPREAD")}
    bad_num = int(pd.concat(num, axis=1).isna().any(axis=1).sum())
    keep = best_t.notna().to_numpy() & ~pd.concat(num, axis=1).isna().any(axis=1).to_numpy()
    out = pd.DataFrame({"open": num["OPEN"], "high": num["HIGH"], "low": num["LOW"], "close": num["CLOSE"],
                        "tickvol": num["TICKVOL"], "spread_points": num["SPREAD"]})[keep]
    out.index = pd.DatetimeIndex(best_t[keep], name="server_time")
    decimals = df["CLOSE"].str.strip().str.partition(".")[2].str.len()
    if meta is not None:
        meta.update({"encoding": enc, "separator": {"\t": "tab", ",": "comma", ";": "semicolon"}[sep], "date_format": best_fmt,
                     "rows_in_file": len(df), "unparsed_time": best_bad, "unparsed_number": bad_num,
                     "price_decimals_max": int(decimals.max()) if len(decimals) else None})
    return out.astype(float)


# ---------------- time ----------------
def to_utc(m1: pd.DataFrame, server_tz: str | None = None, offset_hours: float | None = None) -> pd.DataFrame:
    """Server time -> UTC. A zone is DST-aware; NY+7 is New York time plus 7 hours. Rows that do not exist or are
    ambiguous in the zone become NaT and are dropped (counted by the caller)."""
    if (server_tz is None) == (offset_hours is None):
        raise ValueError("give exactly one of server_tz or offset_hours")
    x = m1.copy()
    if server_tz and server_tz.upper() in NY_PLUS_7:
        ny = (x.index - pd.Timedelta(hours=7)).tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
        x.index = ny.tz_convert("UTC")
    elif server_tz:
        x.index = x.index.tz_localize(server_tz, ambiguous="NaT", nonexistent="NaT").tz_convert("UTC")
    else:
        x.index = (x.index - pd.Timedelta(hours=offset_hours)).tz_localize("UTC")
    x = x[~x.index.isna()]
    x.index.name = "utc"
    return x


def partition_guard(m1_utc: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Keep development and 2026 rows only. Sealed rows are dropped before any figure is computed and only counted."""
    t = m1_utc.index
    dev = (t >= DEV[0]) & (t < DEV[1])
    y26 = t >= Y2026
    sealed = (t >= SEALED[0]) & (t < SEALED[1])
    kept = m1_utc[dev | y26]
    return kept, {"kept_development": int(dev.sum()), "kept_2026": int(y26.sum()), "dropped_sealed": int(sealed.sum()),
                  "dropped_before_development": int((t < DEV[0]).sum())}


def trading_minutes(start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    """Minutes of the gold trading week in UTC: Sunday 18:00 -> Friday 17:00 New York, without the 17:00-18:00 break."""
    m = pd.date_range(start.floor("min"), end.ceil("min"), freq="1min", tz="UTC", inclusive="left")
    ny = m.tz_convert("America/New_York")
    wd, h = ny.day_of_week, ny.hour
    ok = ((wd <= 3) & (h != 17)) | ((wd == 6) & (h >= 18)) | ((wd == 4) & (h < 17))
    return m[ok]


# ---------------- integrity ----------------
def integrity(m1: pd.DataFrame, point: float | None = None) -> dict:
    idx = m1.index
    dup = int(idx.duplicated().sum())
    ordered = bool(idx.is_monotonic_increasing)
    bad_ohlc = int(((m1["low"] > m1[["open", "close"]].min(axis=1)) | (m1["high"] < m1[["open", "close"]].max(axis=1))
                    | (m1["low"] > m1["high"])).sum())
    nonpos = int((m1[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())
    s = m1[~idx.duplicated()].sort_index()
    gaps = s.index.to_series().diff().dropna()
    gmin = gaps.dt.total_seconds() / 60
    weekend = int((gmin >= 24 * 60).sum())
    daily = int(((gmin >= 30) & (gmin < 24 * 60)).sum())
    holes = int(((gmin > 1) & (gmin < 30)).sum())
    consec = np.r_[False, (gmin == 1).to_numpy()]
    prev_c = s["close"].shift(1).to_numpy()
    jump_abs = np.abs(s["open"].to_numpy() - prev_c)
    jump = consec & (jump_abs > JUMP_REL * s["close"].to_numpy())
    spike = (s["high"] - s["low"]).to_numpy() > SPIKE_REL * s["close"].to_numpy()
    top = np.argsort(-np.where(consec, jump_abs, 0.0))[:20]
    rep = {"rows": len(m1), "first": str(idx.min()) if len(idx) else None, "last": str(idx.max()) if len(idx) else None,
           "duplicates": dup, "ordered": ordered, "bad_ohlc": bad_ohlc, "non_positive": nonpos,
           "gaps_weekend_or_holiday": weekend, "gaps_30min_to_1day": daily, "gaps_2_to_29min": holes,
           "discontinuities": {"consecutive_pairs": int(consec.sum()), "jumps": int(jump.sum()),
                               "jump_share": float(jump.sum() / consec.sum()) if consec.sum() else 0.0,
                               "rule": f"|open - previous close| > {JUMP_REL:.1%} of the price, consecutive minutes",
                               "largest": [{"t": str(s.index[j]), "usd": float(jump_abs[j])} for j in top if consec[j] and jump_abs[j] > 0][:20],
                               "spikes": int(spike.sum()), "spike_rule": f"one-minute range > {SPIKE_REL:.0%} of the price"},
           "spread_points": {"median": float(m1["spread_points"].median()) if len(m1) else None,
                             "p95": float(m1["spread_points"].quantile(0.95)) if len(m1) else None,
                             "zero_share": float((m1["spread_points"] == 0).mean()) if len(m1) else None}}
    if point:
        sp = m1["spread_points"] * point
        rep["spread_usd"] = {"median": float(sp.median()), "p95": float(sp.quantile(0.95)), "point": point}
    else:
        rep["spread_usd"] = "not computed: the broker's point size was not supplied (--point)"
    if getattr(idx, "tz", None) is not None and len(s):
        u = s.index
        rep["saturday_bars"] = int((u.day_of_week == 5).sum())
        ny = u.tz_convert("America/New_York")
        rep["bars_in_ny_17h_break"] = int((ny.hour == 17).sum())
        med = s["close"].groupby(u.strftime("%Y-%m")).median()
        rel = (med / med.shift(1) - 1).abs()
        rep["scale_changes"] = [{"month": m, "median_close": float(med[m]), "change": float(rel[m])} for m in rel.index[rel > SCALE_JUMP]]
        rep["coverage"] = coverage(s)
    return rep


def coverage(m1_utc: pd.DataFrame) -> dict:
    """Bars per month and year against the minutes of the trading schedule (holidays and quiet minutes lower it)."""
    if not len(m1_utc):
        return {}
    exp = trading_minutes(m1_utc.index.min().floor("D"), m1_utc.index.max().ceil("D") + pd.Timedelta(days=1))
    have = pd.Series(1, index=m1_utc.index).groupby(m1_utc.index.strftime("%Y-%m")).sum()
    want = pd.Series(1, index=exp).groupby(exp.strftime("%Y-%m")).sum()
    months = sorted(set(have.index))
    by_m = {m: {"bars": int(have.get(m, 0)), "schedule_minutes": int(want.get(m, 0)),
                "coverage": float(have.get(m, 0) / want[m]) if want.get(m, 0) else None} for m in months}
    years = sorted({m[:4] for m in months})
    by_y = {y: {"bars": int(sum(by_m[m]["bars"] for m in months if m.startswith(y))),
                "schedule_minutes": int(sum(by_m[m]["schedule_minutes"] for m in months if m.startswith(y)))} for y in years}
    for v in by_y.values():
        v["coverage"] = v["bars"] / v["schedule_minutes"] if v["schedule_minutes"] else None
    low = [m for m in months if (by_m[m]["coverage"] or 0) < COVERAGE_FLAG]
    return {"by_month": by_m, "by_year": by_y, "months_below_90pct": low}


# ---------------- clock ----------------
def _c15(m1_utc: pd.DataFrame) -> pd.Series:
    return m1_utc["close"].resample("15min", label="left", closed="left").last().dropna()


def _corr(a: pd.Series, b: pd.Series, k: int, min_n: int) -> float:
    s = a.copy()
    s.index = s.index + pd.Timedelta(hours=k)
    j = pd.concat([s.diff(), b.diff()], axis=1, join="inner").dropna()
    return float(j.iloc[:, 0].corr(j.iloc[:, 1])) if len(j) > min_n else math.nan


def clock_check(m1_utc: pd.DataFrame, ref15: pd.Series) -> dict:
    """Correlation of 15m close changes (M1 resampled, UTC) with the reference's, shifting M1 by k hours, overall and
    per ISO week. Aligned = a peak at 0 overall (r >= 0.8) and in every week with enough bars."""
    c15 = _c15(m1_utc)
    r = ref15.dropna()
    corr = {k: _corr(c15, r, k, 100) for k in LAGS_H}
    ok = {k: v for k, v in corr.items() if not math.isnan(v)}
    best = max(ok, key=ok.get) if ok else None
    j0 = pd.concat([c15, r], axis=1, join="inner").dropna()
    weeks, bad = {}, []
    if len(j0):
        iso = c15.index.isocalendar()
        wk = (iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)).to_numpy()
        for w in sorted(set(wk)):
            cw = c15[wk == w]
            lo, hi = cw.index.min() - pd.Timedelta(hours=5), cw.index.max() + pd.Timedelta(hours=5)
            rw = r[(r.index >= lo) & (r.index <= hi)]
            n0 = len(pd.concat([cw, rw], axis=1, join="inner").dropna())
            if n0 < WEEK_MIN_BARS:
                continue
            cc = {k: _corr(cw, rw, k, 50) for k in LAGS_H}
            okw = {k: v for k, v in cc.items() if not math.isnan(v)}
            bw = max(okw, key=okw.get) if okw else None
            weeks[w] = {"best_shift_hours": bw, "r0": cc.get(0), "bars": n0}
            if bw != 0:
                bad.append(w)
    basis = (j0.iloc[:, 0] - j0.iloc[:, 1]) if len(j0) else pd.Series(dtype=float)
    by_month = {m: float(v) for m, v in basis.groupby(basis.index.strftime("%Y-%m")).median().items()} if len(basis) else {}
    return {"corr_by_shift_hours": corr, "best_shift_hours": best,
            "median_abs_close_gap": float(basis.abs().median()) if len(basis) else None,
            "median_close_basis_by_month": by_month, "weeks_checked": len(weeks), "misaligned_weeks": bad,
            "by_week": weeks, "aligned": bool(best == 0 and ok.get(0, 0) >= 0.8 and not bad)}


def suggest_zone(raw: pd.DataFrame, ref15: pd.Series) -> dict:
    """Misaligned weeks under each common convention. Information only: never applied."""
    out = {}
    for z in ZONES:
        try:
            ck = clock_check(partition_guard(to_utc(raw, server_tz=z))[0], ref15)
        except (ValueError, TypeError, KeyError) as e:   # a zone that cannot convert this file is reported, not fatal
            out[z] = {"error": str(e)}
            continue
        out[z] = {"misaligned_weeks": len(ck["misaligned_weeks"]), "weeks_checked": ck["weeks_checked"],
                  "best_shift_hours": ck["best_shift_hours"]}
    return out


def load_reference(path: str | None, rd: str | None) -> pd.Series | None:
    if path:
        ref = pd.read_csv(path)
        return pd.Series(ref["close"].astype(float).to_numpy(), index=pd.to_datetime(ref["time"], utc=True))
    if rd:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from quantum.research import history
        m15 = history.load(rd, "XAU/USD", "15min")
        return m15["close"].astype(float)
    return None


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def verdict(rep: dict) -> tuple[bool, list[str]]:
    u, why = rep["utc"], []
    if rep["read"]["unparsed_time"] or rep["read"]["unparsed_number"]:
        why.append(f"{rep['read']['unparsed_time']} rows with an unreadable time, {rep['read']['unparsed_number']} with an unreadable price")
    if u["duplicates"]:
        why.append(f"{u['duplicates']} duplicate UTC timestamps")
    if not u["ordered"]:
        why.append("rows out of time order")
    if u["bad_ohlc"] or u["non_positive"]:
        why.append(f"{u['bad_ohlc']} inconsistent OHLC rows, {u['non_positive']} non-positive prices")
    if u.get("saturday_bars"):
        why.append(f"{u['saturday_bars']} bars on a UTC Saturday (time zone?)")
    if u["discontinuities"]["jump_share"] > MAX_JUMP_SHARE:
        why.append(f"discontinuities in {u['discontinuities']['jump_share']:.3%} of consecutive minutes")
    if u.get("scale_changes"):
        why.append(f"price scale changes in {[x['month'] for x in u['scale_changes']]}")
    ck = rep.get("clock")
    if ck is not None and not ck["aligned"]:
        why.append(f"clock: best shift {ck['best_shift_hours']} h, misaligned weeks {ck['misaligned_weeks'][:8]}")
    if not rep["partitions"]["kept_development"] + rep["partitions"]["kept_2026"]:
        why.append("no development or 2026 rows")
    return not why, why


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--server-tz", help="IANA zone (e.g. Europe/Athens) or NY+7")
    g.add_argument("--offset-hours", type=float)
    ap.add_argument("--broker")
    ap.add_argument("--symbol")
    ap.add_argument("--point", type=float, help="the broker's point size in $ (the <SPREAD> unit)")
    ap.add_argument("--contract-oz", type=float, help="ounces in 1.00 lot, from the broker's specification")
    ap.add_argument("--reference", help="UTC 15m CSV with columns time, close")
    ap.add_argument("--reference-rd", help="a research-data checkout (Twelve Data 15m spot paths)")
    ap.add_argument("--suggest-zone", action="store_true")
    ap.add_argument("--report", default="m1_report.json")
    ap.add_argument("--write-utc")
    a = ap.parse_args(argv)
    meta = {}
    raw = read_export(a.file, meta)
    utc_all = to_utc(raw, a.server_tz, a.offset_hours)
    m1, parts = partition_guard(utc_all)
    infer = 10.0 ** -meta["price_decimals_max"] if meta.get("price_decimals_max") else None
    rep = {"source": {"file": os.path.basename(a.file), "sha256": _sha256(a.file), "broker": a.broker or "NOT SUPPLIED",
                      "symbol": a.symbol or "NOT SUPPLIED", "point": a.point or "NOT SUPPLIED", "point_inferred_from_decimals": infer,
                      "point_matches_decimals": None if not (a.point and infer) else bool(abs(a.point - infer) < 1e-12),
                      "contract_oz": a.contract_oz or "NOT SUPPLIED", "price_side": "BID (MT5 bars); ask = bid + spread x point"},
           "read": meta,
           "conversion": {"server_tz": a.server_tz, "offset_hours": a.offset_hours,
                          "dropped_nonexistent_or_ambiguous": len(raw) - len(utc_all)},
           "partitions": parts,
           "utc": integrity(m1, a.point)}
    ref = load_reference(a.reference, a.reference_rd)
    if ref is not None:
        rep["clock"] = clock_check(m1, ref)
        if a.suggest_zone:
            rep["zone_suggestion"] = {"note": "information only: confirm the zone with the broker; never applied", **suggest_zone(raw, ref)}
    ok, why = verdict(rep)
    rep["verdict"] = "USABLE" if ok else "NOT USABLE"
    rep["reasons"] = why
    if ref is None:
        rep["reasons"].append("clock NOT CHECKED (no --reference / --reference-rd): not usable for research until checked")
        rep["verdict"] = "NOT USABLE"
        ok = False
    with open(a.report, "w") as fh:
        json.dump(rep, fh, indent=1, default=float)
    if a.write_utc and ok:
        m1[~m1.index.duplicated()].to_csv(a.write_utc, float_format="%.5f")
        with open(a.write_utc + ".json", "w") as fh:
            json.dump({"source": rep["source"], "conversion": rep["conversion"], "partitions": parts}, fh, indent=1, default=float)
    print(json.dumps({"verdict": rep["verdict"], "rows_kept": len(m1), "sealed_dropped": parts["dropped_sealed"],
                      "clock": rep.get("clock", {}).get("best_shift_hours"), "reasons": why[:5]}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
