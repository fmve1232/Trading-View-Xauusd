"""Validate an MT5 M1 bar export before any research uses it (research only; the file stays on the operator's computer).

MT5 terminal: View -> Symbols (Ctrl+U) -> Bars -> XAUUSD, M1, date range -> Request -> Export Bars. The export is
tab-separated with the header <DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <VOL> <SPREAD>, dates YYYY.MM.DD,
times HH:MM[:SS], in the broker's SERVER time, prices from the BID side, spread in points (research/MT5_M1_IMPORT.md).

Checks: columns; parse; duplicates; order; OHLC consistency; non-positive prices; conversion of server time to UTC
(--server-tz IANA name, e.g. Europe/Athens for the common GMT+2 / GMT+3-with-DST convention, or --offset-hours);
gaps (weekend / daily break vs unexpected intraday holes); the spread column; and, with --reference (a UTC 15m OHLC
CSV with a time column and close), the clock: the correlation of 15m close changes peaks at lag 0 when the offset is
right. Writes a JSON report; with --write-utc, a normalised UTC CSV to a path of the operator's choosing.

  python research/tools/mt5_m1_check.py --file XAUUSD_M1.csv --server-tz Europe/Athens [--reference ref15.csv] \
      [--report m1_report.json] [--write-utc m1_utc.csv]
"""
import argparse
import json
import math
import sys

import pandas as pd

COLS = ["<DATE>", "<TIME>", "<OPEN>", "<HIGH>", "<LOW>", "<CLOSE>", "<TICKVOL>", "<VOL>", "<SPREAD>"]
LAGS_H = tuple(range(-4, 5))


def read_export(path_or_buf) -> pd.DataFrame:
    df = pd.read_csv(path_or_buf, sep="\t")
    missing = [c for c in COLS if c not in df.columns]
    if missing:
        raise ValueError(f"not an MT5 bar export: missing columns {missing}")
    t = pd.to_datetime(df["<DATE>"].astype(str) + " " + df["<TIME>"].astype(str), format="mixed")
    out = pd.DataFrame({"open": df["<OPEN>"].astype(float), "high": df["<HIGH>"].astype(float), "low": df["<LOW>"].astype(float),
                        "close": df["<CLOSE>"].astype(float), "tickvol": df["<TICKVOL>"].astype(float),
                        "spread_points": df["<SPREAD>"].astype(float)})
    out.index = pd.DatetimeIndex(t, name="server_time")
    return out


def to_utc(m1: pd.DataFrame, server_tz: str | None = None, offset_hours: float | None = None) -> pd.DataFrame:
    if (server_tz is None) == (offset_hours is None):
        raise ValueError("give exactly one of server_tz or offset_hours")
    x = m1.copy()
    if server_tz:
        x.index = x.index.tz_localize(server_tz, ambiguous="NaT", nonexistent="NaT").tz_convert("UTC")
        x = x[~x.index.isna()]
    else:
        x.index = (x.index - pd.Timedelta(hours=offset_hours)).tz_localize("UTC")
    x.index.name = "utc"
    return x


def integrity(m1: pd.DataFrame) -> dict:
    dup = int(m1.index.duplicated().sum())
    ordered = bool(m1.index.is_monotonic_increasing)
    bad_ohlc = int(((m1["low"] > m1[["open", "close"]].min(axis=1)) | (m1["high"] < m1[["open", "close"]].max(axis=1))
                    | (m1["low"] > m1["high"])).sum())
    nonpos = int((m1[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())
    gaps = m1.index.to_series().diff().dropna()
    gmin = gaps.dt.total_seconds() / 60
    weekend = int((gmin >= 24 * 60).sum())
    daily = int(((gmin >= 30) & (gmin < 24 * 60)).sum())
    holes = int(((gmin > 1) & (gmin < 30)).sum())
    return {"rows": len(m1), "first": str(m1.index.min()), "last": str(m1.index.max()), "duplicates": dup, "ordered": ordered,
            "bad_ohlc": bad_ohlc, "non_positive": nonpos, "gaps_weekend_or_holiday": weekend, "gaps_30min_to_1day": daily,
            "gaps_2_to_29min": holes, "spread_points": {"median": float(m1["spread_points"].median()),
                                                         "p95": float(m1["spread_points"].quantile(0.95)),
                                                         "zero_share": float((m1["spread_points"] == 0).mean())}}


def clock_check(m1_utc: pd.DataFrame, ref15: pd.Series) -> dict:
    """Correlation of 15m close changes (M1 resampled, UTC) with the reference's, shifting M1 by k hours; peaks at 0."""
    c15 = m1_utc["close"].resample("15min", label="left", closed="left").last().dropna()
    r = ref15.dropna()
    corr = {}
    for k in LAGS_H:
        s = c15.copy()
        s.index = s.index + pd.Timedelta(hours=k)
        j = pd.concat([s.diff(), r.diff()], axis=1, join="inner").dropna()
        corr[k] = float(j.iloc[:, 0].corr(j.iloc[:, 1])) if len(j) > 100 else math.nan
    ok = {k: v for k, v in corr.items() if not math.isnan(v)}
    best = max(ok, key=ok.get) if ok else None
    j0 = pd.concat([c15, r], axis=1, join="inner").dropna()
    return {"corr_by_shift_hours": corr, "best_shift_hours": best,
            "median_abs_close_gap": float((j0.iloc[:, 0] - j0.iloc[:, 1]).abs().median()) if len(j0) else None,
            "aligned": bool(best == 0 and ok.get(0, 0) >= 0.8)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--server-tz")
    g.add_argument("--offset-hours", type=float)
    ap.add_argument("--reference", help="UTC 15m OHLC CSV with columns time, close")
    ap.add_argument("--report", default="m1_report.json")
    ap.add_argument("--write-utc")
    a = ap.parse_args(argv)
    raw = read_export(a.file)
    rep = {"server": integrity(raw)}
    m1 = to_utc(raw, a.server_tz, a.offset_hours)
    rep["utc"] = integrity(m1)
    rep["conversion"] = {"server_tz": a.server_tz, "offset_hours": a.offset_hours, "dropped_ambiguous_or_missing": len(raw) - len(m1)}
    if a.reference:
        ref = pd.read_csv(a.reference)
        ref.index = pd.to_datetime(ref["time"], utc=True)
        rep["clock"] = clock_check(m1, ref["close"].astype(float))
    ok = rep["utc"]["duplicates"] == 0 and rep["utc"]["ordered"] and rep["utc"]["bad_ohlc"] == 0 and rep["utc"]["non_positive"] == 0
    ok = ok and (rep.get("clock", {}).get("aligned", True))
    rep["verdict"] = "USABLE" if ok else "NOT USABLE (see the checks)"
    with open(a.report, "w") as fh:
        json.dump(rep, fh, indent=1, default=float)
    if a.write_utc and ok:
        m1.to_csv(a.write_utc, float_format="%.5f")
    print(json.dumps({"verdict": rep["verdict"], "rows": rep["utc"]["rows"], "clock": rep.get("clock", {}).get("best_shift_hours")}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
