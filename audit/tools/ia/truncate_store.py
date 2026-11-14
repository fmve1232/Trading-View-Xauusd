"""Copy a market-data store keeping only bars CLOSED by T (open + interval <= T): what the pipeline could know at T."""
import glob, os, shutil, sys
import pandas as pd
src, dst, T = sys.argv[1], sys.argv[2], pd.Timestamp(sys.argv[3])
SEC = {"5m": 300, "15m": 900, "30m": 1800, "60m": 3600, "1d": 86400}
shutil.copytree(src, dst)
for d in glob.glob(os.path.join(dst, "*_*")):
    iv = d.rsplit("_", 1)[1]
    if not os.path.isdir(d) or iv not in SEC: continue
    for f in glob.glob(os.path.join(d, "*.csv")):
        x = pd.read_csv(f); tc = "datetime" if "datetime" in x else x.columns[0]
        t = pd.to_datetime(x[tc], utc=True)
        keep = (t + pd.Timedelta(seconds=SEC[iv])) <= T
        if keep.all(): continue
        if keep.any(): x[keep.values].to_csv(f, index=False)
        else: os.remove(f)
print("truncated at", T)
