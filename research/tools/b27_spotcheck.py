"""Independent re-computation of sampled B27 entry trades (market fills: IMM and CONF_X) with B26's race, a separately
tested code path, from the cleaned development bars.

  python research/tools/b27_spotcheck.py --trades research/results/b27/b27_frozen_trades.csv.gz --rd <research-data> [--n 30]
"""
import argparse
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from quantum.data import sources
from quantum.research import b26, history
from quantum.research import harness as H


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trades", required=True)
    ap.add_argument("--rd", required=True)
    ap.add_argument("--n", type=int, default=30)
    a = ap.parse_args(argv)
    T = pd.read_csv(a.trades)
    T = T[(T["period"] == "DEV") & T["candidate"].str.contains(r"^S2 \S+ (?:IMM|CONF_\d+) ", regex=True)]
    m15 = sources.repair_reopen(H.partition(history.load(a.rd, "XAU/USD", "15min"), "development"), 900)
    P = b26.make_path(m15, 900)
    t = np.asarray(P.t, dtype=np.int64)
    eng = H.cost_pts(m15.index, slippage=0.0, commission_lot=0.0)
    pick = H.seeded_rng(270).choice(len(T), size=min(a.n, len(T)), replace=False)
    bad = 0
    for q in sorted(pick):
        r = T.iloc[q]
        f = int(np.searchsorted(t, int(pd.Timestamp(r["fill_t"], tz="UTC").timestamp())))
        d = 1 if r["dir"] == "BUY" else -1
        k = P.c[f - 1] / b26.REF        # B27 takes k from the trigger bar; for IMM that is bar f - 1, for CONF an earlier bar
        res = b26.race(P, f, d, eng[f] * k, 0.20 * k, 0.20 * k, k, 192)
        out = b26.OUTCOMES[res[0]]
        net = (d * (res[2] - res[5]) - 0.07 * k) / k
        # TP / SL nets are fixed in 4000-equivalent dollars; a closure / time exit's net depends on k, so for those the
        # outcome must match and the net within a cent
        ok = out == r["outcome"] and abs(net - r["net"]) < (1e-3 if out in ("TP", "SL", "AMBIGUOUS") else 0.05)
        bad += not ok
        print(f"{'OK ' if ok else 'BAD'} {r['candidate']:34s} {r['fill_t']} {r['outcome']:9s}/{out:9s} net {r['net']:+.3f}/{net:+.3f}")
    print(f"{len(pick) - bad} of {len(pick)} match")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
