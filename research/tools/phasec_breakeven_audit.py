"""Phase C audit of the break-even comparator (2026-11-09). The registered runs (B27 at acca0426f, B28 / B29 at 9a86c684c)
compared the decided TP-first rate's lower bound with `break_even`, the break-even of the TP share of ALL trades (stops,
timeouts and closures together). That comparator is too low when timeouts / closures are common. This tool recomputes,
for every frozen candidate, the consistent `break_even_decided` (b27.break_even_decided) from the committed trade CSVs,
and the "lower bound above break-even" flags in development and 2026 under both definitions. No verdict depends on it
(TRADEABLE also needs INFORMATIVE and positive expectancy; nothing was INFORMATIVE).

  python research/tools/phasec_breakeven_audit.py
"""
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from quantum.research import b27

RUNS = (("B27", "research/results/b27/b27_summary.json", "research/results/b27/b27_frozen_trades.csv.gz"),
        ("B28", "research/results/b28/b28_summary.json", "research/results/b28/b28_frozen_trades.csv.gz"),
        ("B29", "research/results/b29/b29_summary.json", "research/results/b29/b29_frozen_trades.csv.gz"))


def main() -> None:
    print("| Study | Candidate | Period | n | r | Lower bound | Neither | break_even (registered) | break_even_decided | Gap (pts) | "
          "LB > old | LB > new | Exp/oz |")
    print("|" + "---|" * 13)
    tot = {"rows": 0, "old": 0, "new": 0, "gap_max": 0.0}
    for study, sp, tp in RUNS:
        with open(sp) as fh:
            s = json.load(fh)
        t = pd.read_csv(tp)
        for c in s["frozen"]:
            for per, key in (("DEV", "dev"), ("Y2026", "y2026")):
                st = c.get(key) or {}
                x = t[(t["candidate"] == c["id"]) & (t["period"] == per)]
                if x.empty or not st.get("n_decided"):
                    continue
                out, net = x["outcome"].to_numpy(), x["net"].to_numpy(float)
                k, n = b27.decided(out)
                assert n == st["n_decided"], (c["id"], per, n, st["n_decided"])
                be_new = b27.break_even_decided(out, net)
                lo = st["ci95"][0]
                old_ok, new_ok = bool(lo > st["break_even"]), bool(lo > be_new)
                gap = 100 * (be_new - st["break_even"])
                tot["rows"] += 1
                tot["old"] += old_ok
                tot["new"] += new_ok
                tot["gap_max"] = max(tot["gap_max"], gap)
                print(f"| {study} | {c['id']} | {per} | {n} | {100 * k / n:.1f}% | {100 * lo:.1f}% | "
                      f"{100 * np.isin(out, ['TIMEOUT', 'CLOSURE']).mean():.1f}% | {100 * st['break_even']:.1f}% | {100 * be_new:.1f}% | "
                      f"{gap:+.1f} | {'yes' if old_ok else 'no'} | {'yes' if new_ok else 'no'} | {net.mean():+.2f} |")
    print(f"\nRows: {tot['rows']}. Lower bound above the registered break-even: {tot['old']}; above break_even_decided: {tot['new']}. "
          f"Largest understatement of the break-even: {tot['gap_max']:.1f} points.")


if __name__ == "__main__":
    main()
