"""Store inventory: per series coverage, bar-time grid, spacing, zero-volume share, age at snapshot (read-only)."""
import os, sys, collections
import pandas as pd
root, snap = sys.argv[1], pd.Timestamp(sys.argv[2])
rows = []
for d in sorted(os.listdir(root)):
    p = os.path.join(root, d)
    if not os.path.isdir(p) or d in ("holdout", "research_forward", "manifests", "revisions"):
        continue
    fs = sorted(f for f in os.listdir(p) if f.endswith(".csv"))
    if not fs:
        continue
    df = pd.concat([pd.read_csv(os.path.join(p, f), index_col=0) for f in fs])
    df.index = pd.to_datetime(df.index, utc=True)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    mins = collections.Counter(df.index.minute)
    top = ",".join(f":{m:02d}x{c}" for m, c in mins.most_common(4))
    gaps = df.index.to_series().diff().dropna()
    nominal = gaps.mode().iloc[0]
    offgrid = (gaps < nominal).sum()
    vol = df["volume"] if "volume" in df else pd.Series(dtype=float)
    vnan, vz = vol.isna().mean(), (vol == 0).mean()
    rows.append((d, str(df.index[0])[:16], str(df.index[-1])[:16], len(df), str(nominal)[7:12] if 'days' in str(nominal) else str(nominal),
                 int(offgrid), top, round(vnan, 2), round(vz, 2), round((snap - df.index[-1]).total_seconds() / 60, 1)))
cols = ["series", "first", "last_open", "rows", "nominal_step", "short_steps", "minute_grid(top4)", "vol_nan", "vol_zero", "age_min"]
print(pd.DataFrame(rows, columns=cols).to_string(index=False))
