"""Timeframe alignment on the PRODUCTION filter (quantum.data.sources.trading_week_only): do 5m/15m/30m bars aggregate to the
stored 15m/30m/60m bars? Open-hours gaps after the filter. Read-only on a store copy."""
import glob, json, os, sys
import pandas as pd
prod, md = sys.argv[1], sys.argv[2]
sys.path.insert(0, prod)
from quantum.data import sources
def load(name):
    fs = sorted(glob.glob(os.path.join(md, name, "*.csv")))
    d = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
    tc = "datetime" if "datetime" in d else d.columns[0]
    d.index = pd.to_datetime(d.pop(tc), utc=True)
    d = d[~d.index.duplicated(keep="last")].sort_index()
    return sources.trading_week_only(sources.drop_offgrid(d), daily=name.endswith("_1d"))
out = {}
X = {iv: load(f"XAU_USD_{iv}") for iv in ("5m", "15m", "30m", "60m", "1d")}
SEC = {"5m": 300, "15m": 900, "30m": 1800, "60m": 3600}
for iv, s in SEC.items():
    d = X[iv]; g = d.index.to_series().diff().dt.total_seconds()
    holes = g[(g > s)]
    # a hole is inside open hours if none of the missing slots is a shut slot
    inside = 0; miss = 0
    for t, gap in holes.items():
        slots = pd.date_range(t - pd.Timedelta(seconds=gap) + pd.Timedelta(seconds=s), t - pd.Timedelta(seconds=s), freq=f"{s}s")
        open_slots = slots[~sources.gold_shut(slots)]
        if len(open_slots): inside += 1; miss += len(open_slots)
    out[f"{iv}_after_filter"] = {"rows": len(d), "first": str(d.index[0]), "open_hour_holes": inside, "missing_open_slots": miss}
def agg(src, rule):
    r = src.resample(rule, label="left", closed="left").agg({"open": "first", "high": "max", "low": "min", "close": "last", "n": "count"}) if "n" in src else None
    return r
for lo, hi, rule, need in (("5m", "15m", "15min", 3), ("15m", "30m", "30min", 2), ("30m", "60m", "60min", 2), ("15m", "60m", "60min", 4)):
    a = X[lo].copy(); a["n"] = 1
    r = a.resample(rule, label="left", closed="left").agg({"open": "first", "high": "max", "low": "min", "close": "last", "n": "sum"})
    r = r[r["n"] == need]
    b = X[hi]; j = r.join(b, how="inner", rsuffix="_hi")
    j = j[j.index >= max(X[lo].index[0], X[hi].index[0])]
    dif = {k: (j[k] - j[k + "_hi"]).abs() for k in ("open", "high", "low", "close")}
    out[f"{lo}->{hi}"] = {"bars_compared": int(len(j)), **{f"{k}_max_abs": round(float(v.max()), 4) for k, v in dif.items()},
                          **{f"{k}_gt_0.05": int((v > 0.05).sum()) for k, v in dif.items()},
                          "examples": [str(t) for t in j.index[(dif["high"] > 0.05) | (dif["low"] > 0.05)][:3]]}
# 4h: production resample_ny_session(1h, 4) -> boundaries in NY time
h4 = sources.resample_ny_session(X["60m"], 4)
out["4h_open_hours_NY"] = sorted({int(h) for h in h4.index.tz_convert("America/New_York").hour})
out["4h_open_hours_UTC"] = sorted({int(h) for h in h4.index.hour})
# DST weeks present in the window
out["dst_transitions_in_15m_window"] = [str(t) for t in pd.date_range(X["15m"].index[0], X["15m"].index[-1], freq="D", tz="UTC")
                                       if (t.tz_convert("America/New_York").utcoffset() != (t - pd.Timedelta(days=1)).tz_convert("America/New_York").utcoffset())]
# daily bars: weekday dates only after the filter; boundary hour
out["1d_after_filter"] = {"rows": len(X["1d"]), "weekend_rows": int((X["1d"].index.dayofweek >= 5).sum()), "open_hours_utc": sorted(set(X["1d"].index.hour))}
json.dump(out, open(sys.argv[3], "w"), indent=1, default=str)
for k, v in out.items(): print(k, v)
