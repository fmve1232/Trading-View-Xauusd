"""Independent re-computation of sampled B26 trades from the bars (a second code path, not quantum.research.b26.race).

For each sampled CSV row (primary ENG scenario) it rebuilds the fill, the levels, the first level reached, the exit
price and the net result from the cleaned bars with pandas, and reports every mismatch.

  python research/tools/b26_spotcheck.py --csv <b26_trades_P3.csv.gz> --pop P3 --rd <research-data> --store5 <dir> [--n 20]
"""
import argparse
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from quantum.research import b26
from quantum.research import harness as H


def recompute(bars: pd.DataFrame, row: pd.Series, horizon: int, bar_sec: int) -> dict:
    d = 1 if row["dir"] == "BUY" else -1
    k, s, si, so_full, cm = row["k"], row["spread"] * row["k"], row["slip_in"] * row["k"], 0.20 * row["k"], row["commission"] * row["k"]
    fill_t = pd.Timestamp(row["fill_utc"], tz="UTC")
    path = bars[bars.index >= fill_t].iloc[:horizon]
    fill = path["open"].iloc[0] + d * (s / 2 + si)
    tp, sl = fill + d * 15 * k, fill - d * 15 * k
    trig = path[["open", "high", "low", "close"]] - d * s / 2
    nxt_gap = path.index.to_series().diff().shift(-1).dt.total_seconds().fillna(np.inf)
    for i, (ts, b) in enumerate(trig.iterrows()):
        up_hit, dn_hit = b["high"] >= (tp if d > 0 else sl), b["low"] <= (sl if d > 0 else tp)
        if (d > 0 and b["open"] <= sl) or (d < 0 and b["open"] >= sl):
            return {"outcome": "SL", "exit_px": b["open"] - d * so_full, "net": (d * (b["open"] - d * so_full - fill) - cm) / k}
        if (d > 0 and b["open"] >= tp) or (d < 0 and b["open"] <= tp):
            return {"outcome": "TP", "exit_px": tp, "net": (15 * k - cm) / k}
        hit_t = up_hit if d > 0 else dn_hit
        hit_s = dn_hit if d > 0 else up_hit
        if hit_s:
            return {"outcome": "AMBIGUOUS" if hit_t else "SL", "exit_px": sl - d * so_full, "net": (-15 * k - so_full - cm) / k}
        if hit_t:
            return {"outcome": "TP", "exit_px": tp, "net": (15 * k - cm) / k}
        if nxt_gap.iloc[i] > b26.CLOSURE_S:
            px = b["close"] - d * so_full
            return {"outcome": "CLOSURE", "exit_px": px, "net": (d * (px - fill) - cm) / k}
    px = trig["close"].iloc[-1] - d * so_full
    return {"outcome": "TIMEOUT", "exit_px": px, "net": (d * (px - fill) - cm) / k}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--pop", required=True, choices=("P1", "P2", "P3"))
    ap.add_argument("--rd", required=True)
    ap.add_argument("--store5")
    ap.add_argument("--store60")
    ap.add_argument("--n", type=int, default=20)
    a = ap.parse_args(argv)
    df = pd.read_csv(a.csv)
    df = df[df["outcome"] != "OPEN"]
    pick = H.seeded_rng(260).choice(len(df), size=min(a.n, len(df)), replace=False)
    pop = b26.populations(a.rd, a.store5, a.store60, (a.pop,))[a.pop]
    bars, tf = pop["bars"], pop["tf"]
    bad = 0
    for q in sorted(pick):
        row = df.iloc[q]
        r = recompute(bars, row, b26.HORIZON[tf], b26.BAR[tf])
        ok = (r["outcome"] == row["outcome"] and abs(r["exit_px"] - row["exit_px"]) < 1e-3 and abs(r["net"] - row["net_usd_oz"]) < 1e-3)
        bad += not ok
        print(f"{'OK ' if ok else 'BAD'} {row['dir']:4s} {row['fill_utc']} {row['outcome']:9s}/{r['outcome']:9s} "
              f"exit {row['exit_px']:.3f}/{r['exit_px']:.3f} net {row['net_usd_oz']:+.3f}/{r['net']:+.3f}")
    print(f"{len(pick) - bad} of {len(pick)} match")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
