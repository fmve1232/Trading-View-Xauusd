"""Phase B8: US NEWS REACTIONS (CPI, payrolls, FOMC) on the operator's $650 / $650 trade. DEVELOPMENT data only.
Approved by the operator 2026-11-03 ("merge, approve B7 and B8"); declared and committed before the first run.

    python -m quantum.research.b8_news <research-data checkout> <out.json> [--registry research/trials.jsonl]

QUESTION. After a scheduled US release, does trading in the direction of the first reaction (or against it) reach
+$13 before -$13 more often than a random entry at the same clock time? (+$13 / -$13 = the operator's $650 / $650 at
0.5 lot; +$10 / -$10 also reported. Distances scaled to $4,000 as in B2-B5.)
EVENTS. Scheduled releases inside the development partition (2020-01-24 -> 2023-01-24), from the official schedules:
    CPI   BLS Consumer Price Index, 08:30 New York          (36 releases)
    NFP   BLS Employment Situation, 08:30 New York          (36 releases)
    FOMC  Federal Reserve statement, 14:00 New York         (23 scheduled meetings; the emergency moves of 3 and 15 March
                                                             2020 were unscheduled and are not included)
  Integrity check, reported and never used to select: the range of each release's first 15-minute bar against the
  median range of the same clock-time bar on non-event weekdays. A ratio below 1.5 is flagged as a possible wrong date.
RULES. The reaction bar is the 15-minute bar that opens at the release time.
    W15  enter at the reaction bar's close, direction = sign(close - open) of that bar
    W30  enter one bar later, direction = sign(close of the 2nd bar - open of the reaction bar)
    CONT trades that direction; FADE trades against it.
  3 events + ALL x 2 waits x 2 rules x 2 targets = 32 trials (ALL pools the three).
BASELINE. Entries at the same New York clock time on weekdays without one of these releases, long and short, matched to
each trial's long / short mix (per event type: 08:45 / 09:00 or 14:15 / 14:30 New York).
Paths, fills, costs and one-position: B2's (spot 15-minute bars, 3 trading days). Reported: n, success, Wilson 95%
interval, z against the matched random rate, net R and $ per trade at 0.5 lot, B2's five-part pass flags.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .. import ta
from . import b2, history
from . import harness as H

NY = ZoneInfo("America/New_York")
TARGETS = {"T13": (13.0, 13.0), "T10": (10.0, 10.0)}
RATIO_MIN = 1.5
RELEASE_TIME = {"CPI": time(8, 30), "NFP": time(8, 30), "FOMC": time(14, 0)}
DATES = {
    "CPI": ["2020-02-13", "2020-03-11", "2020-04-10", "2020-05-12", "2020-06-10", "2020-07-14", "2020-08-12", "2020-09-11",
            "2020-10-13", "2020-11-12", "2020-12-10", "2021-01-13", "2021-02-10", "2021-03-10", "2021-04-13", "2021-05-12",
            "2021-06-10", "2021-07-13", "2021-08-11", "2021-09-14", "2021-10-13", "2021-11-10", "2021-12-10", "2022-01-12",
            "2022-02-10", "2022-03-10", "2022-04-12", "2022-05-11", "2022-06-10", "2022-07-13", "2022-08-10", "2022-09-13",
            "2022-10-13", "2022-11-10", "2022-12-13", "2023-01-12"],
    "NFP": ["2020-02-07", "2020-03-06", "2020-04-03", "2020-05-08", "2020-06-05", "2020-07-02", "2020-08-07", "2020-09-04",
            "2020-10-02", "2020-11-06", "2020-12-04", "2021-01-08", "2021-02-05", "2021-03-05", "2021-04-02", "2021-05-07",
            "2021-06-04", "2021-07-02", "2021-08-06", "2021-09-03", "2021-10-08", "2021-11-05", "2021-12-03", "2022-01-07",
            "2022-02-04", "2022-03-04", "2022-04-01", "2022-05-06", "2022-06-03", "2022-07-08", "2022-08-05", "2022-09-02",
            "2022-10-07", "2022-11-04", "2022-12-02", "2023-01-06"],
    "FOMC": ["2020-01-29", "2020-04-29", "2020-06-10", "2020-07-29", "2020-09-16", "2020-11-05", "2020-12-16", "2021-01-27",
             "2021-03-17", "2021-04-28", "2021-06-16", "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15", "2022-01-26",
             "2022-03-16", "2022-05-04", "2022-06-15", "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14"],
}


def release_utc(kind: str, day: str) -> pd.Timestamp:
    """The release instant in UTC (New York local time, daylight saving handled)."""
    d = date.fromisoformat(day)
    return pd.Timestamp(datetime.combine(d, RELEASE_TIME[kind], tzinfo=NY)).tz_convert("UTC")


def _bar_at(idx: pd.DatetimeIndex, t: pd.Timestamp) -> int | None:
    k = idx.searchsorted(t)
    return int(k) if k < len(idx) and idx[k] == t else None


def event_bars(m15: pd.DataFrame, kind: str) -> list[dict]:
    """Reaction bars of one event type: index, both directions, and the integrity ratio."""
    idx = m15.index
    o, h, l, c = (m15[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    ny = idx.tz_convert(NY)
    event_days = {d for k in DATES for d in DATES[k]}
    out = []
    for day in DATES[kind]:
        t = release_utc(kind, day)
        k = _bar_at(idx, t)
        if k is None or k + 1 >= len(idx) or idx[k + 1] != t + pd.Timedelta(minutes=15):
            out.append({"kind": kind, "day": day, "k": None})
            continue
        same = (ny.time == t.tz_convert(NY).time()) & (ny.dayofweek < 5) & ~pd.Index(ny.strftime("%Y-%m-%d")).isin(event_days)
        ref = np.median((h - l)[same]) if same.any() else np.nan
        out.append({"kind": kind, "day": day, "k": k, "ratio": float((h[k] - l[k]) / ref) if ref > 0 else math.nan,
                    "d15": float(np.sign(c[k] - o[k])), "d30": float(np.sign(c[k + 1] - o[k]))})
    return out


def baseline(P: b2.Paths, m15: pd.DataFrame, kind: str, wait: int) -> dict:
    """Random-entry TP-first rates at the same New York clock time on non-event weekdays."""
    ny = m15.index.tz_convert(NY)
    rel = RELEASE_TIME[kind]
    t_entry = (datetime.combine(date(2021, 1, 4), rel) + timedelta(minutes=15 * wait)).time()   # bar that closes at entry
    open_t = (datetime.combine(date(2021, 1, 4), t_entry) - timedelta(minutes=15)).time()
    event_days = {d for k in DATES for d in DATES[k]}
    m = (ny.time == open_t) & (ny.dayofweek < 5) & ~pd.Index(ny.strftime("%Y-%m-%d")).isin(event_days)
    i = np.flatnonzero(m)
    t_close = ta.epoch_s(m15.index) + 900
    j, ok = P.locate(t_close[i])
    i, j = i[ok], j[ok]
    c = m15["close"].to_numpy(float)
    sc = c[i] / b2.REF_PRICE
    out = {}
    for dname, dv in (("long", 1.0), ("short", -1.0)):
        ev = P.evaluate(j, c[i], np.full(len(i), dv), [(a * sc, b * sc) for a, b in TARGETS.values()])
        for tn, e in zip(TARGETS, ev):
            out[f"{tn} {dname}"] = float(np.mean(e["out"] == 1))
    out["n_days"] = len(i)
    return out


def run(rd: str, outp: str, registry: str | None) -> dict:
    m15 = H.partition(history.load(rd, "XAU/USD", "15min"), "development")
    P = b2.Paths(m15)
    t_close = ta.epoch_s(m15.index) + 900
    c = m15["close"].to_numpy(float)
    cost_bar = H.cost_pts(m15.index)
    res = {"set": "B8", "partition": "development", "from": str(H.DEV[0]), "to": str(H.DEV[1]), "data_hash": H.data_hash(m15),
           "events": {}, "baseline": {}, "trials": []}
    ev_all = {}
    for kind in DATES:
        bars = event_bars(m15, kind)
        ev_all[kind] = bars
        found = [b for b in bars if b["k"] is not None]
        res["events"][kind] = {"listed": len(bars), "with_bars": len(found),
                               "flagged_low_ratio": [b["day"] for b in found if not (b["ratio"] >= RATIO_MIN)],
                               "median_ratio": float(np.nanmedian([b["ratio"] for b in found])) if found else math.nan}
        for w in (1, 2):
            res["baseline"][f"{kind} W{15 * w}"] = baseline(P, m15, kind, w)
    names, pv, daily = [], [], {}
    for kind in ("CPI", "NFP", "FOMC", "ALL"):
        kinds = list(DATES) if kind == "ALL" else [kind]
        for w in (1, 2):
            rows = [(b["k"] + (w - 1), b[f"d{15 * w}"], kd) for kd in kinds for b in ev_all[kd] if b["k"] is not None and b[f"d{15 * w}"] != 0]
            if not rows:
                continue
            i = np.array([r[0] for r in rows], np.int64)
            dsign = np.array([r[1] for r in rows])
            kds = [r[2] for r in rows]
            for rule, sgn in (("CONT", 1.0), ("FADE", -1.0)):
                d = dsign * sgn
                j, ok = P.locate(t_close[i])
                ii, jj, dd, kk = i[ok], j[ok], d[ok], [k_ for k_, o_ in zip(kds, ok) if o_]
                sc = c[ii] / b2.REF_PRICE
                evs = P.evaluate(jj, c[ii], dd, [(a * sc, b * sc) for a, b in TARGETS.values()])
                for q, (tn, (a, b)) in enumerate(TARGETS.items()):
                    e = evs[q]
                    keep = b2.one_position(t_close[ii], P.t[np.minimum(e["exit"], len(P.t) - 1)] + b2.PATH_SEC)
                    st = b2._stats(e["out"][keep], e["pnl"][keep], cost_bar[ii][keep] * sc[keep], a * sc[keep], b * sc[keep], dd[keep])
                    tid = f"15min {kind} W{15 * w} {rule} {tn}"
                    rec = {"id": tid, "event": kind, "wait_min": 15 * w, "rule": rule, "target": tn}
                    if st["n"]:
                        kk_keep = [kk[x] for x in keep]
                        rnd = sum(res["baseline"][f"{k_} W{15 * w}"][f"{tn} {'long' if dd[keep][x] > 0 else 'short'}"]
                                  for x, k_ in enumerate(kk_keep)) / st["n"]
                        z = (st["win_rate"] - rnd) / math.sqrt(max(rnd * (1 - rnd), 1e-12) / st["n"])
                        rec.update({k_: st.get(k_) for k_ in ("n", "long", "short", "wins", "losses", "open", "win_rate", "wilson", "break_even", "net_r", "t")})
                        rec.update({"random_same_mix": rnd, "z_vs_random": z, "usd_per_trade_0p5lot": st["net_r"] * b * 50,
                                    "pass": {"1_wilson_lb_above_break_even": bool(st["wilson"][0] > st["break_even"]),
                                             "2_t_above_3": bool((st["t"] if st["t"] is not None and math.isfinite(st["t"]) else 0) > 3 and st["net_r"] > 0),
                                             "3_beats_random_by_2se": bool(z > 2)}})
                        net_r = (e["pnl"][keep] - cost_bar[ii][keep] * sc[keep]) / (b * sc[keep])
                        daily[tid] = pd.Series(net_r, index=pd.to_datetime(t_close[ii][keep], unit="s", utc=True).normalize()).groupby(level=0).sum()
                        names.append(tid)
                        pv.append(H.t_pvalue(st["t"], st["n"]) if st["t"] is not None and math.isfinite(st["t"]) else 1.0)
                    else:
                        rec["n"] = 0
                    res["trials"].append(rec)
    bh = H.benjamini_hochberg(pv, 0.10) if names else []
    Dd = pd.DataFrame({k: daily[k] for k in names}).fillna(0.0).sort_index() if names else pd.DataFrame()
    rc = H.reality_check(Dd[names].to_numpy(), B=1000, mean_block=5.0) if len(Dd) > 20 else {"p_value": 1.0, "best": 0}
    tmap = {t["id"]: t for t in res["trials"]}
    for x, okb in zip(names, bh):
        tmap[x]["pass"]["4_bh_fdr10"] = bool(okb)
        tmap[x]["pass"]["5_reality_check_p_below_0p05"] = bool(rc["p_value"] < 0.05)
        tmap[x]["passes_all"] = all(tmap[x]["pass"].values())
    res["family"] = {"trials": len(names), "reality_check_p": rc["p_value"], "best_id": names[rc["best"]] if names else None,
                     "bh_fdr10_passed": [x for x, okb in zip(names, bh) if okb],
                     "passes_all": [x for x in names if tmap[x].get("passes_all")]}
    if registry:
        for t in res["trials"]:
            H.log_trial(registry, {"phase": "B8", "partition": "development", "data_hash": res["data_hash"], **t})
    with open(outp, "w") as f:
        json.dump(res, f, indent=1, default=float)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rd")
    ap.add_argument("out")
    ap.add_argument("--registry", default="research/trials.jsonl")
    a = ap.parse_args(argv)
    r = run(a.rd, a.out, a.registry)
    for k, v in r["events"].items():
        print(f"{k}: {v['with_bars']}/{v['listed']} releases with bars, median reaction-bar ratio {v['median_ratio']:.1f}, flagged {v['flagged_low_ratio']}")
    for t in r["trials"]:
        if t.get("n"):
            print(f"{t['id']:28s} n {t['n']:3d}  TP first {t['win_rate']:.1%} [{t['wilson'][0]:.0%}, {t['wilson'][1]:.0%}]  "
                  f"random {t['random_same_mix']:.1%}  z {t['z_vs_random']:+.2f}  net {t['net_r']:+.3f}R  ${t['usd_per_trade_0p5lot']:+.0f}")
    print("family:", json.dumps(r["family"], default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
