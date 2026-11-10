"""What a "90% success rate" for +$15 costs (descriptive; operator request 2026-11-07). Random entries at every 4th
15m close of the 2020-22 development data, both directions, distances scaled to $4,000 (as every B-study):

  A. +$15 before a stop of S dollars, for S from 13 to 150 (first touch on 15m bars, ties a loss, up to 2 weeks);
  B. +$15 touched at ANY time within 1 day / 1 week / 2 weeks with no stop, and how far price went against the
     position first (the worst adverse move before the touch) and where the misses ended.

  python research/tools/geometry_90.py RD OUT.json
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from quantum import ta
from quantum.research import b13
from quantum.research import harness as H

T = 15.0
STOPS = (13.0, 20.0, 30.0, 50.0, 75.0, 100.0, 135.0, 150.0)
HORIZONS = {"1 day": 96, "1 week": 480, "2 weeks": 960}


def main(rd: str, out_path: str) -> int:
    m15, _ = b13.load(rd, "development")
    rows = np.flatnonzero(m15.index >= b13.SCORE_FROM)[::4]
    t_close = ta.epoch_s(m15.index).astype(np.int64)[rows] + 900
    c = m15["close"].to_numpy(float)
    px = c[rows]
    cost = float(np.mean(H.cost_pts(m15.index)[rows]))
    res = {"entries_per_direction": len(rows), "mean_cost_usd_per_oz": cost, "stops": {}, "no_stop": {}}
    for S in STOPS:
        w = l_ = 0
        for d in (1, -1):
            r = b13.race(m15, t_close, px, np.full(len(rows), d), T, S, nbars=960)
            w += int(r["win"].sum())
            l_ += int(r["loss"].sum())
        p = w / (w + l_)
        res["stops"][f"{S:g}"] = {"tp_first": p, "geometry": S / (S + T), "decided": w + l_,
                                  "expectancy_usd_per_oz": p * T - (1 - p) * S - cost, "loss_to_win_ratio": S / T}
        print(f"SL ${S:>5g}: +$15 first {p:6.1%} (geometry {S / (S + T):5.1%}); each loss = {S / T:4.1f} wins; "
              f"expectancy {p * T - (1 - p) * S - cost:+.2f} $/oz")
    h, lo_ = m15["high"].to_numpy(float), m15["low"].to_numpy(float)
    j0 = np.searchsorted(ta.epoch_s(m15.index).astype(np.int64), t_close)
    s = px / 4000.0
    for name, nb in HORIZONS.items():
        ok = j0 + nb <= len(c)
        hit, mae_before, miss_end = [], [], []
        for d in (1, -1):
            for x in np.flatnonzero(ok):
                seg_h, seg_l = h[j0[x]: j0[x] + nb], lo_[j0[x]: j0[x] + nb]
                fav = (seg_h - px[x]) * d if d > 0 else (px[x] - seg_l)
                adv = (px[x] - seg_l) if d > 0 else (seg_h - px[x])
                k = np.flatnonzero(fav >= T * s[x])
                if len(k):
                    hit.append(1)
                    mae_before.append(float(adv[: k[0] + 1].max() / s[x]))
                else:
                    hit.append(0)
                    miss_end.append(float((c[j0[x] + nb - 1] - px[x]) * d / s[x]))
        hit = np.array(hit)
        mae_before, miss_end = np.array(mae_before), np.array(miss_end)
        res["no_stop"][name] = {"touched_15": float(hit.mean()), "n": len(hit),
                                "adverse_before_touch_median": float(np.median(mae_before)),
                                "adverse_before_touch_p90": float(np.quantile(mae_before, 0.9)),
                                "adverse_before_touch_max": float(mae_before.max()),
                                "misses_end_median": float(np.median(miss_end)) if len(miss_end) else None,
                                "misses_end_p10": float(np.quantile(miss_end, 0.1)) if len(miss_end) else None}
        v = res["no_stop"][name]
        print(f"no stop, {name:8s}: +$15 touched {v['touched_15']:5.1%}; before the touch price went against the entry by a median "
              f"${v['adverse_before_touch_median']:.0f}, 1 in 10 by ${v['adverse_before_touch_p90']:.0f} (worst ${v['adverse_before_touch_max']:.0f}); "
              f"misses ended at a median ${v['misses_end_median']:+.0f} (1 in 10 worse than ${v['misses_end_p10']:+.0f})")
    with open(out_path, "w") as f:
        json.dump(res, f, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
