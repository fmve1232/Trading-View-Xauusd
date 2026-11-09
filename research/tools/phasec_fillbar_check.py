"""Phase C resolution check for Track A's order entries (retest / stop / limit), development 2020-22, all 21 trigger
families (B27's 13 with X in b27.CONF_X, B28's 8 with X in b28.XS). Descriptive; nothing is selected here.

B27 / B28 fill a retest, stop or limit order INSIDE a 15m bar and count that bar only against the trade: if the bar's
adverse extreme reaches the stop it is a loss, and its favourable extreme never counts (b27.race_fill). On 15m bars the
order of the extremes is unknown, so that is the WORST case. A $15-$20 stop entry is usually filled by a large bar whose
other extreme is near the trigger, so the worst case books many losses that need the low to come after the fill.

This tool races every order entry a second time in the BEST case for the fill bar (its adverse extreme came before the
fill; its favourable extreme after: TP if it reaches the target, otherwise the race starts on the next bar) and reports,
per entry mode pooled over families and directions: trades, the share stopped on the fill bar (worst case), TP-first
worst and best, and the matched random of the worst-case series. The 2-point INCONCLUSIVE rule of B29 is applied.

  python research/tools/phasec_fillbar_check.py --rd RD --store5 S5 --store60 S60 --out OUT.json
"""
import argparse
import collections
import json
import math
import sys

import pandas as pd

sys.path.insert(0, ".")
from quantum.research import b26, b27, b28

_worst = b27.race_fill


def race_best(P: b26.Path, j0: int, fill: float, d: int, s: float, so: float, k: float, horizon: int, fill_bar=None):
    if fill_bar is None:
        return _worst(P, j0, fill, d, s, so, k, horizon)
    dist = b27.MOVE * k
    off = -d * s / 2.0
    fav = (P.h[fill_bar] + off - fill) if d > 0 else (fill - (P.l[fill_bar] + off))
    if fav >= dist:
        return "TP", P.t[fill_bar] + P.bar, fill + d * dist, dist, 0.0
    if fill_bar + 1 >= P.n:
        return "OPEN", P.t[fill_bar] + P.bar, math.nan, 0.0, 0.0
    return _worst(P, fill_bar + 1, fill, d, s, so, k, horizon)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True)
    ap.add_argument("--store5", required=True)
    ap.add_argument("--store60", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    D = b27.load_pops(a.rd, a.store5, a.store60)["DEV"]
    b27.prepare(D, print)
    D["F"] = pd.concat([D["F"], b28.new_events(D["m15"], D["F"])], axis=1)
    agg = collections.defaultdict(lambda: collections.Counter())
    per = {}
    for fams, xs, trig_of in ((b27.FAMILIES, b27.CONF_X, b27.triggers), (b28.FAMILIES, b28.XS, b28.triggers)):
        for fam in fams:
            trig = trig_of(D["F"], D["Lp"], fam, D["k"])
            b27.race_fill = _worst
            tw = b27.entry_trades(D["path"], trig, D["costs"], xs=xs)
            b27.race_fill = race_best
            tb = b27.entry_trades(D["path"], trig, D["costs"], xs=xs)
            b27.race_fill = _worst
            for mode in tw:
                if mode.startswith("_") or not mode.startswith(("RETEST", "STOP", "LIMIT")):
                    continue
                for d, dn in b27.DIRS.items():
                    w = [x for x in tw[mode] if x["d"] == d]
                    bb = [x for x in tb[mode] if x["d"] == d]
                    if not w:
                        continue
                    n_trig = sum(1 for x in trig if x[1] == d)
                    sw = b27.trade_stats(w, n_trig, D["path"], D["rates"], D["sess_of"], D["weeks"])
                    sb = b27.trade_stats(bb, n_trig, D["path"], D["rates"], D["sess_of"], D["weeks"])
                    fb = sum(1 for x in w if x["outcome"] == "SL" and x["minutes"] == 15.0) / len(w)
                    nw, nb = sw.get("n_decided") or 0, sb.get("n_decided") or 0
                    per[f"{fam} {mode} {dn}"] = {"n_worst": nw, "r_worst": sw.get("r"), "n_best": nb, "r_best": sb.get("r"),
                                                 "random": sw.get("matched_random"), "fill_bar_stop_share": fb}
                    kind, _, x = mode.partition("_")
                    coarse = kind if not x else f"{kind} X{'>=' if int(x) >= 15 else '<'}15"
                    for kk in {mode, coarse}:
                        c = agg[kk]
                        c["nw"] += nw
                        c["kw"] += (sw.get("r") or 0) * nw
                        c["rnd"] += (sw.get("matched_random") or 0) * nw
                        c["nb"] += nb
                        c["kb"] += (sb.get("r") or 0) * nb
                        c["fb"] += fb * len(w)
                        c["nall"] += len(w)
            print(fam, flush=True)
    pooled = {}
    for kk, c in sorted(agg.items()):
        rw, rb = c["kw"] / c["nw"] if c["nw"] else None, c["kb"] / c["nb"] if c["nb"] else None
        pooled[kk] = {"n_worst": c["nw"], "r_worst": rw, "n_best": c["nb"], "r_best": rb, "random_worst_series": c["rnd"] / c["nw"] if c["nw"] else None,
                      "fill_bar_stop_share": c["fb"] / c["nall"] if c["nall"] else None,
                      "inconclusive": bool(rw is not None and rb is not None and rb - rw > 0.02)}
        print(kk, json.dumps(pooled[kk]))
    with open(a.out, "w") as fh:
        json.dump(b27._clean({"pooled": pooled, "per_config": per}), fh, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
