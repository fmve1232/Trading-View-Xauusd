"""B19 Monte Carlo (research/registrations/B19.json, grid_secondary.monte_carlo). Research only; outside quantum/ because
it draws random numbers (tests/test_integrity.py keeps np.random out of quantum/).

For each primary strategy's recorded trade results (R per trade, in time order, from the B19 results file): 10,000
resamples of 100 trades with replacement; the median and 95th percentile maximum drawdown in R, the probability of a
10 R drawdown (a 10% maximum loss at 1% risk per trade) and of a 5 R drawdown, and the distribution of the 100-trade
total.

  python research/tools/b19_montecarlo.py RESULTS.json OUT.json
"""
import json
import sys

import numpy as np


def max_dd(eq: np.ndarray) -> np.ndarray:
    """Maximum drawdown of each row of cumulative R paths (a leading zero is implied)."""
    z = np.concatenate([np.zeros((eq.shape[0], 1)), eq], axis=1)
    return (np.maximum.accumulate(z, axis=1) - z).max(axis=1)


def main(src: str, dst: str, sims: int = 10000, n: int = 100, seed: int = 19) -> int:
    with open(src) as f:
        res = json.load(f)
    rng = np.random.default_rng(seed)
    out = {"source": src, "sims": sims, "trades_per_sim": n, "seed": seed, "strategies": {}}
    for key, v in sorted(res.get("per_trade", {}).items()):
        r = np.asarray(v["r"], float)
        if len(r) < 10:
            out["strategies"][key] = {"trades": len(r), "note": "too few trades to resample"}
            continue
        draw = r[rng.integers(0, len(r), size=(sims, n))]
        eq = np.cumsum(draw, axis=1)
        dd = max_dd(eq)
        tot = eq[:, -1]
        out["strategies"][key] = {"trades": len(r), "mean_r": float(r.mean()), "median_max_dd_r": float(np.median(dd)),
                                  "p95_max_dd_r": float(np.quantile(dd, 0.95)), "p_dd_ge_10r": float((dd >= 10).mean()),
                                  "p_dd_ge_5r": float((dd >= 5).mean()), "median_total_r": float(np.median(tot)),
                                  "p_total_below_0": float((tot < 0).mean())}
        s = out["strategies"][key]
        print(f"{key:40s} n {len(r):5d} mean {s['mean_r']:+.3f} R | 100 trades: median DD {s['median_max_dd_r']:.1f} R, "
              f"P(DD>=10R) {s['p_dd_ge_10r']:.0%}, P(total<0) {s['p_total_below_0']:.0%}")
    with open(dst, "w") as f:
        json.dump(out, f, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
