"""Point-in-time recoverability of the market data (read-only).

  python3 -I audit/tools/v2_pit.py <forward-ledger dir> <out dir>

Reads the forward ledger's revision log (revisions/<series>/<YYYY-MM>.csv, written by quantum/manifest.py since its
first run) and the run manifests (manifests/runs-*.jsonl). For each series: closed-bar revisions LISTED with their old
values (recoverable: the earliest old value of a bar is the value first stored after it closed), revisions recorded
only as a COUNT ("N closed bars revised (series re-based); not listed": old values lost), and removed bars. For XAU:
every revised 5-minute bar (delay from its close to the run that revised it, size), and the daily-close rewrite runs.
Outputs v2_pit.json and v2_pit_xau_5m.csv."""
from __future__ import annotations

import csv
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

LED, OUT = sys.argv[1], sys.argv[2]
BAR = {"5m": 300, "15m": 900, "30m": 1800, "60m": 3600, "1d": 86400}


def main():
    os.makedirs(OUT, exist_ok=True)
    runs = [json.loads(l) for f in sorted(glob.glob(os.path.join(LED, "manifests", "runs-*.jsonl"))) for l in open(f) if l.strip()]
    res = {"manifest_runs": len(runs), "manifest_first_run": runs[0]["run_utc"], "manifest_last_run": runs[-1]["run_utc"],
           "manifest_revised_closed_bars_total": sum(r.get("revised_closed_bars", 0) for r in runs),
           "manifest_fields": sorted(runs[-1].keys()), "series": {}}
    root = os.path.join(LED, "revisions")
    xau5 = []
    daily_runs = defaultdict(list)
    for d in sorted(os.listdir(root)):
        listed, removed, counted, count_rows = 0, 0, 0, 0
        bars = set()
        for f in sorted(os.listdir(os.path.join(root, d))):
            for r in csv.reader(open(os.path.join(root, d, f))):
                if not r or r[0] == "bar_open":
                    continue
                if len(r) == 11:
                    if r[10] == "removed":
                        removed += 1
                        continue
                    listed += 1
                    bars.add(r[0])
                    if d == "XAU_USD_5m":
                        t, run = pd.Timestamp(r[0]), pd.Timestamp(r[1])
                        o, n = float(r[5]), float(r[9])
                        xau5.append({"bar_open": r[0][:16], "run_utc": r[1], "minutes_after_close": round((run - t).total_seconds() / 60 - 5, 1),
                                     "change_usd": round(n - o, 2), "change_bp": round((n - o) / o * 1e4, 2)})   # no vendor prices written
                    if d == "XAU_USD_1d":
                        daily_runs[r[1][:16]].append((r[0][:10], float(r[5]), float(r[9])))
                elif len(r) == 3:
                    m = re.match(r"(\d+) closed bars revised", r[2])
                    if m:
                        counted += int(m.group(1))
                        count_rows += 1
        res["series"][d] = {"listed_revisions_old_value_recoverable": listed, "distinct_bars_listed": len(bars),
                            "revisions_count_only_old_value_lost": counted, "count_only_rows": count_rows, "removed_bars": removed,
                            "share_recoverable": listed / (listed + counted) if listed + counted else None}
    x = pd.DataFrame(xau5)
    if len(x):
        x.to_csv(os.path.join(OUT, "v2_pit_xau_5m.csv"), index=False)
        res["xau_5m"] = {"rows": len(x), "distinct_bars": int(x["bar_open"].nunique()),
                         "revisions_per_bar": dict(Counter(Counter(x["bar_open"]).values())),
                         "minutes_after_close_quantiles": {q: float(x["minutes_after_close"].quantile(q)) for q in (0.05, 0.25, 0.5, 0.75, 0.95, 1.0)},
                         "abs_change_usd_quantiles": {q: float(x["change_usd"].abs().quantile(q)) for q in (0.5, 0.9, 0.99, 1.0)},
                         "share_over_1_usd": float((x["change_usd"].abs() > 1).mean()),
                         "first": x["bar_open"].min(), "last": x["bar_open"].max()}
    dr = {}
    for run, rows in sorted(daily_runs.items()):
        ch = np.array([abs(n - o) / o * 1e4 for _, o, n in rows])
        dr[run] = {"bars": len(rows), "first_bar": min(b for b, _, _ in rows), "last_bar": max(b for b, _, _ in rows),
                   "median_bp": float(np.median(ch)), "max_bp": float(ch.max())}
    res["xau_1d_revision_runs"] = dr
    json.dump(res, open(os.path.join(OUT, "v2_pit.json"), "w"), indent=1)
    print({k: res[k] for k in ("manifest_runs", "manifest_first_run", "manifest_last_run", "manifest_revised_closed_bars_total")})
    tot_l = sum(v["listed_revisions_old_value_recoverable"] for v in res["series"].values())
    tot_c = sum(v["revisions_count_only_old_value_lost"] for v in res["series"].values())
    print(f"all series: listed (recoverable) {tot_l:,} | count-only (lost) {tot_c:,} | listed + count = {tot_l + tot_c:,}")
    for d, v in res["series"].items():
        print(f"  {d:14s} listed {v['listed_revisions_old_value_recoverable']:>9,} ({v['distinct_bars_listed']:,} bars) | count-only {v['revisions_count_only_old_value_lost']:>10,} | removed {v['removed_bars']:5d} | recoverable {v['share_recoverable'] if v['share_recoverable'] is None else round(v['share_recoverable'], 3)}")
    print("XAU 5m:", json.dumps(res.get("xau_5m"), indent=0))
    big = {k: v for k, v in dr.items() if v["bars"] >= 5 or v["max_bp"] >= 20}
    print("XAU 1d revision runs with >= 5 bars or >= 20 bp:", json.dumps(big, indent=0))
    print("XAU 1d revision runs total:", len(dr), "| rows", sum(v["bars"] for v in dr.values()))


if __name__ == "__main__":
    main()
