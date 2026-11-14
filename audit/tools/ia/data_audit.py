"""Read-only data-quality audit of the market-data store copy: per series counts, duplicates, order, gaps, weekend bars,
OHLC sanity, and closed-market bars. Prints a compact summary; writes JSON."""
import glob, json, os, sys
import numpy as np, pandas as pd
md, out = sys.argv[1], sys.argv[2]
SEC = {"5m": 300, "15m": 900, "30m": 1800, "60m": 3600, "1d": 86400}
res = {}
def load(name):
    fs = sorted(glob.glob(os.path.join(md, name, "*.csv")))
    if not fs: return None
    d = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
    tc = "datetime" if "datetime" in d else d.columns[0]
    d["t"] = pd.to_datetime(d[tc], utc=True)
    return d
def closed_market(t):
    # Spot gold is closed from Friday 17:00 New York to Sunday 17:00 New York (CME / interbank convention, DST-aware).
    ny = t.dt.tz_convert("America/New_York")
    dow, hm = ny.dt.day_of_week, ny.dt.hour + ny.dt.minute / 60
    return ((dow == 4) & (hm >= 17)) | (dow == 5) | ((dow == 6) & (hm < 17))
for name in sorted(os.listdir(md)):
    if not os.path.isdir(os.path.join(md, name)) or "_" not in name: continue
    iv = name.rsplit("_", 1)[1]
    if iv not in SEC: continue
    d = load(name)
    if d is None: continue
    raw_n = len(d)
    dup = int(d.duplicated("t").sum())
    order_bad = int((d["t"].diff().dt.total_seconds().fillna(1) <= 0).sum())
    d = d.drop_duplicates("t", keep="last").sort_values("t")
    o, h, l, c = (d[k].astype(float) for k in ("open", "high", "low", "close"))
    bad = int(((h < np.maximum(o, c) - 1e-9) | (l > np.minimum(o, c) + 1e-9) | (h < l)).sum())
    nan = int(d[["open", "high", "low", "close"]].isna().any(axis=1).sum())
    r = {"rows": raw_n, "first": str(d["t"].iloc[0]), "last": str(d["t"].iloc[-1]), "dup": dup, "out_of_order": order_bad,
         "ohlc_inconsistent": bad, "nan_ohlc": nan, "zero_range": int(((h - l) == 0).sum())}
    if iv != "1d":
        cm = closed_market(d["t"])
        r["closed_market_bars"] = int(cm.sum())
        r["closed_market_bars_2026"] = int((cm & (d["t"].dt.year == 2026)).sum())
        gaps = d["t"].diff().dt.total_seconds() / SEC[iv]
        nxt = d["t"]
        # missing bars inside open-market hours: gaps > 1 bar whose span lies wholly in open hours (ignore weekend / daily break)
        g = d[(gaps > 1)].copy(); g["gap_bars"] = gaps[gaps > 1] - 1
        prev_t = d["t"].shift(1)[gaps > 1]
        span_h = (g["t"] - prev_t).dt.total_seconds() / 3600
        g["span_h"] = span_h
        r["gaps_total"] = int(len(g))
        r["gaps_le_2h"] = int((span_h <= 2).sum())       # intraday holes (daily break is 1 h for gold)
        r["gaps_2h_to_40h"] = int(((span_h > 2) & (span_h < 40)).sum())
        r["missing_bars_in_le_2h_gaps"] = float(g.loc[span_h <= 2, "gap_bars"].sum())
        y26 = d[d["t"].dt.year == 2026]
        r["rows_2026"] = int(len(y26))
    res[name] = r
json.dump(res, open(out, "w"), indent=1)
cols = ["rows", "first", "dup", "out_of_order", "ohlc_inconsistent", "nan_ohlc", "zero_range", "closed_market_bars", "closed_market_bars_2026", "gaps_le_2h", "gaps_2h_to_40h"]
df = pd.DataFrame(res).T
df["first"] = df["first"].str[:10]
print(df[[c for c in cols if c in df]].to_string())
