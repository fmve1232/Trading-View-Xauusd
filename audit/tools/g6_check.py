"""Independent check of the G6-EXPOSURE results (research/registrations/G6-EXPOSURE.json). Read-only.

forward: recomputes the forward exposure figures by brute force from the raw ledger files and the raw store CSV
         timestamps (own JSON / CSV parsing, own market-hours rule, own loops; nothing imported from the study module)
         and compares them with the study's output.
dev:     checks the invariants of the development results (policy limits respected, kept + blocked = all, corrections
         no smaller than the raw p, the trials log matching the results).

  python audit/tools/g6_check.py forward --ledger <dir with holdout/> --store <store> --results <forward json>
  python audit/tools/g6_check.py dev --results research/G6_EXPOSURE_RESULTS.json [--trials research/trials.jsonl]
Exit 0 when every check passes, 1 otherwise.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
SEC = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}
FAMILY = {"primary": (("5m", "15m", "30m", "1h"), ("treatment", "h4")),
          "a1": (("5m", "15m", "30m", "1h", "4h"), ("treatment", "control", "challenger", "h2", "h3", "h4", "h5"))}
FREEZE = "1f88aad357497da4:4440d52587f5cc6b"


def epoch(s: str) -> int:
    return int(datetime.fromisoformat(s).timestamp())


def shut(t: int) -> bool:
    ny = datetime.fromtimestamp(t, NY)
    wd, hr = ny.weekday(), ny.hour
    return wd == 5 or (wd == 4 and hr >= 17) or (wd == 6 and hr < 18) or (wd <= 3 and hr == 17)


def nyday(t: int) -> str:
    return (datetime.fromtimestamp(t, NY) + timedelta(hours=7)).date().isoformat()


def load_positions(ledger: str, family: str) -> list[tuple]:
    out = []
    tfs, arms = FAMILY[family]
    for tf in tfs:
        sec = SEC[tf]
        for arm in arms:
            path = os.path.join(ledger, "holdout", f"{tf}_{arm}.json")
            if not os.path.exists(path):
                continue
            with open(path) as f:
                for t in json.load(f):
                    if t.get("open") or not str(t.get("freeze_key", "")).startswith(FREEZE):
                        continue
                    out.append((epoch(t["entry_time"]) + sec, epoch(t["exit_time"]) + sec, 1 if t["dir"] == "LONG" else -1,
                                tf, arm, float(t["r"])))
    return out


def load_grid(store: str, lo: int, hi: int) -> list[int]:
    ts = set()
    for path in sorted(glob.glob(os.path.join(store, "XAU_USD_5m", "*.csv"))):
        with open(path) as f:
            for row in csv.DictReader(f):
                t = epoch(row["datetime"])
                if t % 300 == 0 and not shut(t):
                    ts.add(t)
    return [t + 300 for t in sorted(ts) if lo <= t + 300 <= hi]


def forward(a) -> list[tuple]:
    with open(a.results) as f:
        res = json.load(f)
    P = load_positions(a.ledger, a.family)
    lo, hi = min(p[0] for p in P), max(p[1] for p in P)
    G = load_grid(a.store, lo, hi)
    n_all = [sum(1 for p in P if p[0] <= g < p[1]) for g in G]
    n_l = [sum(1 for p in P if p[2] == 1 and p[0] <= g < p[1]) for g in G]
    n_s = [x - y for x, y in zip(n_all, n_l, strict=True)]
    peak = max(sum(1 for q in P if q[0] <= p[0] < q[1]) for p in P)            # the maximum is reached at some fill
    cross = sum(1 for p in P if any(q is not p and q[2] == p[2] and q[3] != p[3] and abs(q[0] - p[0]) <= 3600 for q in P))
    order = sorted(range(len(P)), key=lambda i: (P[i][1], P[i][0]))
    eq = peak_eq = dd = 0.0
    run = streak = 0
    for i in order:
        eq += P[i][5]
        peak_eq = max(peak_eq, eq)
        dd = max(dd, peak_eq - eq)
        run = run + 1 if P[i][5] < 0 else 0
        streak = max(streak, run)
    per_day, realised = {}, {}
    for p in P:
        per_day[nyday(p[0])] = per_day.get(nyday(p[0]), 0) + 1
        realised[nyday(p[1])] = realised.get(nyday(p[1]), 0.0) + p[5]
    c, b = res["concurrency"], res["book"]
    return [("positions", len(P), res["positions"]), ("samples", len(G), c["open_positions"]["samples"]),
            ("mean open", round(sum(n_all) / len(G), 4), c["open_positions"]["mean"]),
            ("max open on grid", max(n_all), c["open_positions"]["max"]),
            ("share 2+ open", round(sum(x >= 2 for x in n_all) / len(G), 4), c["open_positions"]["share_2_plus"]),
            ("share 2+ same direction", round(sum(x >= 2 or y >= 2 for x, y in zip(n_l, n_s, strict=True)) / len(G), 4),
             c["share_of_time_two_plus_same_direction"]),
            ("share long and short together", round(sum(x >= 1 and y >= 1 for x, y in zip(n_l, n_s, strict=True)) / len(G), 4),
             c["share_of_time_long_and_short_together"]),
            ("exact max open", peak, c["exact"]["max_open"]),
            ("share same-direction other-tf entry within 60m", round(cross / len(P), 4),
             res["correlated"]["share_with_same_direction_entry_on_another_tf_within_60m"]),
            ("net R", round(sum(p[5] for p in P), 2), b["net_r"]), ("max drawdown R", round(dd, 4), b["max_dd_r"]),
            ("longest losing streak", streak, b["longest_losing_streak"]),
            ("max entries in a day", max(per_day.values()), b["potential_daily_loss_r"]["max"]),
            ("worst realised day R", round(min(realised.values()), 4), b["realised_daily_r"]["worst"])]


def dev(a) -> list[tuple]:
    with open(a.results) as f:
        res = json.load(f)
    pol = res["policies"]
    n = res["positions"]
    rows = [("P0 keeps every position", n, pol["P0_none"]["book"]["trades"])]
    for k, v in pol.items():
        rows.append((f"{k}: kept + blocked = all", n, v["book"]["trades"] + v["blocked"].get("count", 0)))
    rows += [("P1 never more than one open", True, pol["P1_one_open"]["concurrency"]["max"] <= 1),
             ("P2 never more than one open", True, pol["P2_one_open_three_per_day"]["concurrency"]["max"] <= 1),
             ("P2 never more than three entries a day", True, pol["P2_one_open_three_per_day"]["book"]["potential_daily_loss_r"]["max"] <= 3),
             ("P3 never more than three open", True, pol["P3_three_open"]["concurrency"]["max"] <= 3),
             ("P4 never more than two open", True, pol["P4_one_open_per_direction"]["concurrency"]["max"] <= 2),
             ("ten tests", 10, sum(1 for c in res["comparisons"] for m in ("mean_net_r_per_trade", "net_r_per_day") if m in c))]
    ok_adj = all(c[m]["p_holm"] >= c[m]["p_two_sided"] - 1e-9 and c[m]["p_bh"] >= c[m]["p_two_sided"] - 1e-9
                 for c in res["comparisons"] for m in ("mean_net_r_per_trade", "net_r_per_day"))
    rows.append(("Holm and BH no smaller than raw p", True, ok_adj))
    if a.trials:
        with open(a.trials) as f:
            lines = [x for x in (json.loads(y) for y in f if '"G6-EXPOSURE"' in y)
                     if x.get("family", "primary") == res.get("family", "primary")]
        last = lines[-len(res["comparisons"]):]
        same = all(x["a"] == c["a"] and x["b"] == c["b"] and x["mean_net_r_per_trade_diff"] == c["mean_net_r_per_trade"]["diff"]
                   and x["net_r_per_day_diff"] == c["net_r_per_day"]["diff"] for x, c in zip(last, res["comparisons"], strict=True))
        rows += [("trials lines for G6", len(res["comparisons"]), len(lines)), ("trials match results", True, same)]
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("forward")
    f.add_argument("--ledger", required=True)
    f.add_argument("--store", required=True)
    f.add_argument("--results", required=True)
    f.add_argument("--family", choices=list(FAMILY), default="primary")
    d = sub.add_parser("dev")
    d.add_argument("--results", required=True)
    d.add_argument("--trials")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    rows = forward(a) if a.cmd == "forward" else dev(a)
    bad = 0
    for name, want, got in rows:
        ok = want == got
        bad += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}: independent {want} / study {got}")
    print(f"{len(rows) - bad} of {len(rows)} PASS")
    if a.json:
        with open(a.json, "w") as fh:
            json.dump({"check": a.cmd, "rows": [{"name": n, "independent": w, "study": g, "pass": w == g} for n, w, g in rows],
                       "verdict": "PASS" if not bad else "FAIL"}, fh, indent=1)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
