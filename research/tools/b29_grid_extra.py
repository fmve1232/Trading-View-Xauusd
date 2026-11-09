"""B29 study G, completed: monthly results and results by volatility tercile / trend / session for EVERY grid pair
(development 2020-22, ENG costs, every eligible bar, independent series). The B29 run computed these breakdowns only for
the frozen candidates; the registration lists them among the statistics, so this fills the gap. Descriptive only (G
has no pass / fail); 2026 is not read.

  python research/tools/b29_grid_extra.py --rd RD --store5 S5 --store60 S60 --out research/results/b29/b29_grid_extra.csv.gz
"""
import argparse
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from quantum.research import b27, b28, b29


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True)
    ap.add_argument("--store5", required=True)
    ap.add_argument("--store60", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    D = b27.load_pops(a.rd, a.store5, a.store60)["DEV"]
    b27.prepare(D, print)
    T = b29.tables(D, "ENG")
    wD = b27.weeks_of(T[b29.GRID[0]])
    rows = []
    for g in b29.GRID:
        L = T[g]
        rates = b27.base_rates(L)
        for d, dn in b27.DIRS.items():
            st = b29.seq_stats(L, np.flatnonzero((L["d"] == d).to_numpy()), rates, wD, g[1])
            ex = b28.extra(st.get("_seq"), b28.neutral_rates(rates), D["Lp"], D["path"])
            r = {"bracket": b29.gname(g), "tp": g[0], "sl": g[1], "dir": dn, "n_decided": st.get("n_decided"), "r": st.get("r"),
                 "exp_oz": st.get("exp_oz"), "months": ex.get("months"), "share_months_positive": ex.get("share_months_positive"),
                 "monthly_mean_050lot_ASSUMED": ex.get("monthly_mean_050lot_ASSUMED"),
                 "monthly_worst_050lot_ASSUMED": ex.get("monthly_worst_050lot_ASSUMED"),
                 "direction_neutral_random": ex.get("direction_neutral_random")}
            by = ex.get("by", {})
            for k, v in sorted(by.items()):
                r[f"{k} n"], r[f"{k} r"], r[f"{k} exp_oz"] = v["n"], v["r"], v["exp_oz"]
            vt = [v["r"] for k, v in by.items() if k.startswith("vol_tercile=") and v["r"] is not None and v["n"] >= 100]
            r["vol_tercile_r_spread"] = (max(vt) - min(vt)) if len(vt) >= 2 else None
            ve = [v["exp_oz"] for k, v in by.items() if k.startswith(("vol_tercile=", "trend_state=", "session=")) and v["n"] >= 100]
            r["regimes_with_positive_exp"] = int(sum(e > 0 for e in ve if e is not None))
            r["regimes_tested"] = len(ve)
            rows.append(r)
        print(b29.gname(g), flush=True)
    pd.DataFrame(rows).to_csv(a.out, index=False, float_format="%.4f", compression="gzip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
