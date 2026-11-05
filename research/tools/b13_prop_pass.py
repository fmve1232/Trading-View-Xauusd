"""B13 secondary (research/registrations/B13.json): prop-firm pass probabilities of the operator's geometries.

Arithmetic, no market data: a two-step challenge (8% then 5%; daily loss 5% of the start-of-day balance; static 10%
maximum loss) on $25,000, at most two trades a day, a trade skipped when its loss would breach the daily limit,
independent trades with win probability p = S / (T + S) (no edge) and p + 3 points, $0.26 per oz round trip.
Check each firm's exact rules; the comparison between geometries is the point.

  python research/tools/b13_prop_pass.py OUT.json
"""
import json
import math
import sys

import numpy as np

OP_COST = 0.26


def prop_table(seed: int = 7, n: int = 40000) -> dict:
    """Two-step challenge (8% then 5%, daily 5% of the start-of-day balance, static 10% maximum loss) on $25,000.
    At most two trades a day; a trade is skipped when its loss would breach the daily limit. p = the driftless
    S / (T + S) and p + 3 points. Cost = $0.26 per oz round trip."""
    geoms = [("0.50 lot, SL $13, TP $15", 0.50, 13, 15), ("0.50 lot, SL $13, TP $10", 0.50, 13, 10),
             ("0.50 lot, SL $13, TP $20", 0.50, 13, 20), ("0.50 lot, SL $13, TP $13", 0.50, 13, 13),
             ("0.43 lot, SL $15, TP $15", 0.43, 15, 15), ("0.25 lot, SL $26, TP $15", 0.25, 26, 15),
             ("0.22 lot, SL $30, TP $15", 0.22, 30, 15), ("0.25 lot, SL $13, TP $15", 0.25, 13, 15)]
    acct, out = 25000.0, {}
    for name, lot, S, T in geoms:
        oz = 100 * lot
        w, ls = T * oz - OP_COST * oz, -S * oz - OP_COST * oz
        for edge in (0.0, 0.03):
            p = S / (T + S) + edge
            res = []
            for ph, tgt in ((1, 0.08), (2, 0.05)):
                g = np.random.default_rng(seed + ph)
                bal = np.zeros(n)
                alive, done = np.ones(n, bool), np.zeros(n, bool)
                days = np.zeros(n)
                for _ in range(1500):
                    act = alive & ~done
                    if not act.any():
                        break
                    days += act
                    start = bal.copy()
                    for _k in range(2):
                        can = act & ~done & alive & ((start - (bal + ls)) <= 0.05 * acct + 1e-9)
                        if not can.any():
                            break
                        win = g.random(n) < p
                        bal = np.where(can, bal + np.where(win, w, ls), bal)
                        alive &= ~(can & (bal <= -0.10 * acct + 1e-9))
                        done |= can & alive & (bal >= tgt * acct - 1e-9)
                res.append((float(done.mean()), float(np.median(days[done])) if done.any() else math.nan))
            out[f"{name} | p={p:.3f}"] = {"lot": lot, "S": S, "T": T, "p": p, "win_usd": w, "loss_usd": ls,
                                          "pass_phase1": res[0][0], "pass_both": res[0][0] * res[1][0],
                                          "median_days_phase1": res[0][1], "median_days_phase2": res[1][1],
                                          "ev_per_trade_usd": p * w + (1 - p) * ls}
    return out



if __name__ == "__main__":
    res = prop_table()
    with open(sys.argv[1], "w") as fh:
        json.dump(res, fh, indent=1)
    for k, v in res.items():
        print(f"{k:42s} EV/trade {v['ev_per_trade_usd']:+7.1f}  pass P1 {100*v['pass_phase1']:5.1f}%  both {100*v['pass_both']:5.1f}%  "
              f"days P1 {v['median_days_phase1']}")
