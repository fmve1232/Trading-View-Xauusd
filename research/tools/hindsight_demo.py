"""Hindsight demonstration (exploratory, development data only; operator request 2026-11-07: "modify alerts to achieve
100% successful trades with TP hit first" from last week's data).

The rule below was CHOSEN AFTER LOOKING at the 3-6 Nov 4h breakouts (research/results/b18_recalc_2026-11-03_06.json): the
one combination of the B18 checks that would have made every alerted trade a winner that week (4 of 4). It is run here,
unchanged, on the 2020-22 development data to show what a rule picked that way does on data it was not picked on.
Nothing here changes an alert. Research code: never imported by production.

  python research/tools/hindsight_demo.py --rd RD --out OUT.json [--trials research/trials.jsonl]
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from quantum import config, engine, notify, ta
from quantum.data import sources
from quantum.features import compute as compute_features
from quantum.research import b10, b13, b16, b17
from quantum.research import harness as H

RULES = {  # name: (predicate on a B18 event, where it came from)
    "hindsight: BUY + beyond a level + engine bias": (
        lambda e: e["dir"] > 0 and e["checks"]["major"] and e["checks"]["bias"], "4 of 4 TP first on 3-6 Nov"),
    "same rule, both directions": (
        lambda e: e["checks"]["major"] and e["checks"]["bias"], "4 of 5 on 3-6 Nov"),
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials")
    a = ap.parse_args(argv)
    m15, h1 = b13.load(a.rd, "development")
    h4 = sources.resample_ny_session(h1, 4)
    m = b10.make_market(h4, h1, "4h", 14400)
    F = compute_features(m, config.DEFAULT)
    F2 = dict(F)
    F2["v"] = np.ones(len(np.asarray(F["v"])))                      # as B16-B18 (no volume stored for these data)
    R = engine.run(m, config.DEFAULT, "treatment", F2).rows
    idx = pd.DatetimeIndex(F["index"])
    t4 = ta.epoch_s(idx).astype(np.int64).tolist()
    h, lo_, c = b16._none(F["h"]), b16._none(F["l"]), b16._none(F["c"])
    c1, c4 = b17._chart(h1), b17._chart(h4)
    lv = notify.setup_levels(t4, h, lo_, c1, c4)
    for k in ("pdh", "pdl", "pwh", "pwl"):
        lv[k.upper()] = b16._none(R[k])
    votes = notify.trend_votes([x + 14400 for x in t4], c1, c4)
    rows = np.flatnonzero(idx >= b13.SCORE_FROM).tolist()
    ev = notify.h4_events(t4, h, lo_, c, b16._none(R["bull"]), b16._none(R["bear"]), lv, votes, rows)
    i15, t15 = m15.index, ta.epoch_s(m15.index).astype(np.int64)
    cost15 = H.cost_pts(i15)
    s15 = np.flatnonzero(i15 >= b13.SCORE_FROM)
    rnd = b13.random_rates(m15, i15, m15["close"].to_numpy(float), s15[::3], 15.0, b13.S_STOP)
    res = {"utc": datetime.now(timezone.utc).isoformat(), "kind": "exploratory hindsight demonstration", "stage": "development",
           "breakouts": len(ev), "rules": {}}
    for name, (pred, src) in RULES.items():
        es = [e for e in ev if pred(e)]
        tc = np.asarray([e["t_close"] for e in es], np.int64)
        px = np.asarray([e["close"] for e in es], float)
        dd = np.asarray([e["dir"] for e in es], int)
        j = np.searchsorted(t15, tc)
        r = b13.race(m15, tc, px, dd, 15.0, b13.S_STOP)
        base = np.where(dd > 0, rnd["long"], rnd["short"])
        st = b13.stats(r, dd, cost15[np.minimum(j, len(cost15) - 1)], 15.0, b13.S_STOP, base)
        yrs = (idx[-1] - b13.SCORE_FROM).days / 365.25
        res["rules"][name] = {"picked_on": src, **{k: st[k] for k in ("n", "rate", "wilson", "random", "z", "p_one_sided",
                                                                         "mean_net_usd_per_oz_at_4000", "t")},
                              "per_year": round(st["n"] / yrs, 1)}
        print(f"{name}: picked on {src}; 2020-22: {st['rate']:.1%} of {st['n']} (random {st['random']:.1%}), "
              f"net {st['mean_net_usd_per_oz_at_4000']:+.2f} $/oz")
    with open(a.out, "w") as f:
        json.dump(b13._clean(res), f, indent=1, allow_nan=False)
    if a.trials:
        for name, s in res["rules"].items():
            H.log_trial(a.trials, {"phase": "B19-explore", "partition": "development", "id": f"hindsight {name} T15",
                                   "note": "rule chosen on 3-6 Nov live data; demonstration of selection bias", **b13._clean(s)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
