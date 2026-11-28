"""Forward ledgers against a properly matched random-entry baseline, after costs (read-only; operator mandate
2026-11-28, Part 6 items 7-12 and Part 7). Method fixed here, committed before the first run:

  python audit/tools/forward_matched.py --ledger <forward-ledger export> --bars <market-data export> --json out.json
                                        [--k 50] [--seed 20261128]

Inputs: <ledger>/holdout/<tf>_<arm>.json, trades under the current engine key (<ledger>/holdout_manifest.json) only,
every live arm and timeframe; <bars>/XAU_USD_5m/*.csv, with off-grid rows and bars printed while gold is shut
dropped (own rule: Friday 17:00 to Sunday 18:00 New York and the 17:00-18:00 daily break).

Per recorded trade (fill = signal close = entry_time + one bar; holding period H = exit-bar close - fill):
- recorded net R (the ledger's own r, after the engine's MODELLED cost), gross R = gross_pts / stop distance;
- the trade's ENTRY replayed on 5-minute bars under the arms' fixed exit rules (half at TP1, stop to break-even after
  TP1 from the next bar, TP2 closes, a bar touching the stop counts as the stop, a bar opening beyond a level fills at
  that open), with a time exit at the close after H, the same cost: "entry replay R";
- K matched random entries: 5-minute closes on ANOTHER New York trading day inside the forward window, within 60
  minutes of the fill's New York clock time (entry timing and session), on the trade's timeframe grid (UTC multiples
  of its bar length; 4h: of one hour), same direction, same stop / TP1 / TP2 distances, same cost, same holding
  period H, managed by the same fixed rules: "random R". Candidates whose horizon runs past the data are not used.
- races from the fill: +$10, +$15 and +$20 before the original stop (5-minute bars, 7 days, a bar touching both is the
  stop), for the trade and for its random matches; MFE and MAE in USD over the trade's own life; minutes to each
  target when it is reached first.

Per ledger (arm x timeframe), per arm and overall: means with a day-block bootstrap 95% interval (New York trading
days resampled whole); the matched difference d_i = R_i - mean(random R of trade i) with a day-block bootstrap and a
one-sided p (share of resampled means <= 0); the same for the entry replay and for each race (hit minus the random hit
rate). Holm and BH across the ledgers tested. A ledger is tested only with MIN_N = 30 trades or more; smaller ones are
reported as INSUFFICIENT SAMPLE. Verdict: EDGE only if the recorded net mean R has a day-block interval above zero AND
the recorded-vs-random difference has Holm p < 0.05; otherwise "NO EDGE — INSUFFICIENT EVIDENCE". Measured-cost
expectancy is UNAVAILABLE until the broker's costs are verified (G2); it is never filled with a modelled number.

Sensitivity: the same means without the trades whose life contains a weekly reopen bar (the first bar after the
weekend closure), because the feed's reopen bars are known to carry suspect extremes (docs/final_audit/
REOPEN_VERIFICATION.md, R2b).
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

NY = ZoneInfo("America/New_York")
TF_SEC = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}
GRID = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 3600}
TARGETS = (10.0, 15.0, 20.0)
HORIZON = 7 * 86400
CLOCK_WIN = 3600
MIN_N = 30
B = 4000


# ---------------- data ----------------
def shut(t: int) -> bool:
    ny = datetime.fromtimestamp(t, NY)
    wd, hr = ny.weekday(), ny.hour
    return wd == 5 or (wd == 4 and hr >= 17) or (wd == 6 and hr < 18) or (wd <= 3 and hr == 17)


def nyday(t: int) -> str:
    return (datetime.fromtimestamp(t, NY) + timedelta(hours=7)).date().isoformat()


def ny_minute(t: int) -> int:
    ny = datetime.fromtimestamp(t, NY)
    return ny.hour * 60 + ny.minute


def ts(s: str) -> int:
    return int(pd.Timestamp(s).timestamp())


def load_bars(d: str) -> dict:
    frames = []
    for f in sorted(glob.glob(os.path.join(d, "XAU_USD_5m", "*.csv"))):
        x = pd.read_csv(f, index_col=0)
        x.index = pd.to_datetime(x.index, utc=True)
        frames.append(x[["open", "high", "low", "close"]].astype(float))
    df = pd.concat(frames)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    t = ((df.index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)).to_numpy().astype(np.int64)
    keep = np.array([x % 300 == 0 and not shut(int(x)) for x in t], bool)
    t = t[keep]
    a = df.to_numpy()[keep]
    gap = np.diff(t, prepend=t[0]) > 6 * 3600                   # the first bar after the weekend closure
    return {"t": t, "o": a[:, 0], "h": a[:, 1], "l": a[:, 2], "c": a[:, 3], "reopen": gap}


def load_ledgers(d: str) -> tuple[str, dict]:
    with open(os.path.join(d, "holdout_manifest.json")) as f:
        key = json.load(f)["freeze_key"]
    out = {}
    for path in sorted(glob.glob(os.path.join(d, "holdout", "*_*.json"))):
        name = os.path.basename(path)[:-5]
        tf, _, arm = name.partition("_")
        if tf not in TF_SEC or name.startswith("manifest"):
            continue
        with open(path) as f:
            rows = json.load(f)
        if not isinstance(rows, list):
            continue
        tr = [t for t in rows if not t.get("open") and str(t.get("freeze_key", "")).startswith(key)]
        if tr:
            out[(tf, arm)] = tr
    return key, out


# ---------------- simulation ----------------
def manage(P: dict, j0: int, t_end: int, side: int, e: float, sl: float, tp1: float, tp2: float, cost: float) -> float | None:
    """Net R of one position from 5-minute bar j0 under the arms' fixed rules, with a time exit at t_end (the close of
    the last bar ending by then). None if the data end before t_end."""
    t, o, h, l, c = P["t"], P["o"], P["h"], P["l"], P["c"]
    risk = abs(e - sl)
    if risk <= 0:
        return None
    legs, qty, tp1_done, stop, px = [], 1.0, False, sl, None
    j = j0
    while j < len(t) and t[j] + 300 <= t_end:
        oj = o[j]
        if (oj >= tp2) if side == 1 else (oj <= tp2):
            if not tp1_done:
                legs.append((0.5, oj))
                qty -= 0.5
            px = oj
            break
        if not tp1_done and ((oj >= tp1) if side == 1 else (oj <= tp1)):
            legs.append((0.5, oj))
            qty -= 0.5
            tp1_done = True
        if (oj <= stop) if side == 1 else (oj >= stop):
            px = oj
            break
        if (l[j] <= stop) if side == 1 else (h[j] >= stop):
            px = stop
            break
        if not tp1_done and ((h[j] >= tp1) if side == 1 else (l[j] <= tp1)):
            legs.append((0.5, tp1))
            qty -= 0.5
            tp1_done = True
        if (h[j] >= tp2) if side == 1 else (l[j] <= tp2):
            px = tp2
            break
        if tp1_done:
            stop = e
        j += 1
    if px is None:
        if j == len(t) and t[-1] + 300 < t_end:
            return None                       # the data end before the time exit
        if j == j0:
            return None                       # no complete 5-minute bar inside the holding period
        px = c[j - 1]                         # time exit at the close of the last bar ending by t_end
    gross = sum(q * (p - e) * side for q, p in [*legs, (qty, px)])
    return (gross - cost) / risk


def races(P: dict, j0: int, side: int, e: float, sl: float) -> dict:
    """+$10 / +$15 / +$20 before the original stop from bar j0 (7 days; a bar touching both is the stop): 1, 0 or None
    (undecided), and the minutes to each target when reached first."""
    t, o, h, l = P["t"], P["o"], P["h"], P["l"]
    j1 = int(np.searchsorted(t, t[j0] + HORIZON)) if j0 < len(t) else j0
    oo, hh, ll = o[j0:j1], h[j0:j1], l[j0:j1]
    stop = (ll <= sl) | (oo <= sl) if side == 1 else (hh >= sl) | (oo >= sl)
    ks = int(np.argmax(stop)) if stop.any() else None
    out = {}
    for x in TARGETS:
        px = e + side * x
        hit = (hh >= px) | (oo >= px) if side == 1 else (ll <= px) | (oo <= px)
        kt = int(np.argmax(hit)) if hit.any() else None
        if kt is not None and (ks is None or kt < ks):
            out[int(x)] = (1, (int(t[j0 + kt]) + 300 - int(t[j0])) / 60)
        elif ks is not None:
            out[int(x)] = (0, None)
        else:
            out[int(x)] = (None, None)
    return out


def excursions(P: dict, j0: int, t_end: int, side: int, e: float) -> tuple[float, float]:
    t, h, l = P["t"], P["h"], P["l"]
    j1 = int(np.searchsorted(t, t_end - 300, "right"))
    if j1 <= j0:
        return 0.0, 0.0
    hh, ll = h[j0:j1], l[j0:j1]
    fav = (hh.max() - e) if side == 1 else (e - ll.min())
    adv = (e - ll.min()) if side == 1 else (hh.max() - e)
    return round(max(float(fav), 0.0), 3), round(max(float(adv), 0.0), 3)


# ---------------- statistics ----------------
def day_boot(x: np.ndarray, days: list, rng) -> dict:
    if len(x) == 0:
        return {"n": 0}
    groups = defaultdict(list)
    for v, d in zip(x, days, strict=True):
        groups[d].append(v)
    g = list(groups.values())
    out = {"n": len(x), "days": len(g), "mean": round(float(np.mean(x)), 4)}
    if len(g) < 5:
        out |= {"ci95_days": None, "p_le_0": None}
        return out
    sums, cnts = np.array([sum(v) for v in g]), np.array([len(v) for v in g])
    idx = rng.integers(0, len(g), size=(B, len(g)))
    m = sums[idx].sum(1) / cnts[idx].sum(1)
    out |= {"ci95_days": [round(float(np.quantile(m, 0.025)), 4), round(float(np.quantile(m, 0.975)), 4)],
            "p_le_0": round(float(np.mean(m <= 0)), 4)}
    return out


def wilson(k: int, n: int, z: float = 1.959964):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    hw = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - hw, 4), round(c + hw, 4)]


def holm(ps: list[float]) -> list[float]:
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i])
    adj, run = [0.0] * m, 0.0
    for k, i in enumerate(order):
        run = max(run, min(1.0, (m - k) * ps[i]))
        adj[i] = round(run, 4)
    return adj


def bh(ps: list[float]) -> list[float]:
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i], reverse=True)
    adj, run = [0.0] * m, 1.0
    for k, i in enumerate(order):
        run = min(run, ps[i] * m / (m - k))
        adj[i] = round(min(run, 1.0), 4)
    return adj


# ---------------- per trade ----------------
def candidates(P: dict, tf: str) -> dict:
    """Candidate random entry instants (5-minute closes on the timeframe's grid), with their New York minute and day."""
    close = P["t"] + 300
    ok = close % GRID[tf] == 0
    return {"close": close[ok], "j": np.nonzero(ok)[0] + 1, "minute": np.array([ny_minute(int(x)) for x in close[ok]]),
            "day": np.array([nyday(int(x)) for x in close[ok]])}


def one(t: dict, tf: str, P: dict, cand: dict, k: int, rng) -> dict | None:
    sec = TF_SEC[tf]
    side = 1 if t["dir"] == "LONG" else -1
    fill = ts(t["entry_time"]) + sec
    end = ts(t["exit_time"]) + sec
    H = end - fill
    j0 = int(np.searchsorted(P["t"], fill))
    if j0 >= len(P["t"]) or P["t"][0] > fill:
        return None
    e, sl, tp1, tp2 = float(t["entry"]), float(t["sl"]), float(t["tp1"]), float(t["tp2"])
    risk = abs(e - sl)
    cost = float(t["cost_pts"])
    d1, d2 = abs(tp1 - e), abs(tp2 - e)
    rec = {"r": float(t["r"]), "gross_r": float(t["gross_pts"]) / risk if risk > 0 else 0.0, "day": nyday(fill),
           "replay_r": manage(P, j0, end, side, e, sl, tp1, tp2, cost),
           "races": races(P, j0, side, e, sl), "mfe_mae": excursions(P, j0, end, side, e),
           "reopen_inside": bool(P["reopen"][j0:int(np.searchsorted(P["t"], end - 300, "right"))].any())}
    mins = ny_minute(fill)
    dm = np.abs(cand["minute"] - mins)
    dm = np.minimum(dm, 1440 - dm)
    pool = np.nonzero((dm <= CLOCK_WIN // 60) & (cand["day"] != rec["day"]) & (cand["close"] + H <= P["t"][-1] + 300))[0]
    rr, rh = [], {int(x): [] for x in TARGETS}
    if len(pool):
        for q in rng.choice(pool, size=min(k, len(pool)), replace=False):
            j = int(cand["j"][q])
            if j >= len(P["t"]):
                continue
            ep = float(P["c"][j - 1])
            r = manage(P, j, int(cand["close"][q]) + H, side, ep, ep - side * risk, ep + side * d1, ep + side * d2, cost)
            if r is not None:
                rr.append(r)
            for x, (hit, _) in races(P, j, side, ep, ep - side * risk).items():
                if hit is not None:
                    rh[x].append(hit)
    rec["random_r"] = rr
    rec["random_hits"] = rh
    return rec


def summarise(recs: list[dict], rng) -> dict:
    days = [x["day"] for x in recs]
    r = np.array([x["r"] for x in recs])
    g = np.array([x["gross_r"] for x in recs])
    ok = [x for x in recs if x["random_r"]]
    d_rec = np.array([x["r"] - np.mean(x["random_r"]) for x in ok])
    rep = [x for x in ok if x["replay_r"] is not None]
    d_rep = np.array([x["replay_r"] - np.mean(x["random_r"]) for x in rep])
    out = {"trades": len(recs), "gross_r": day_boot(g, days, rng), "net_r_modelled_cost": day_boot(r, days, rng),
           "net_r_measured_cost": "UNAVAILABLE: broker costs not verified (G2)",
           "entry_replay_r": day_boot(np.array([x["replay_r"] for x in rep]), [x["day"] for x in rep], rng),
           "matched_random_r": {"trades_with_matches": len(ok),
                                "mean_of_trade_means": round(float(np.mean([np.mean(x["random_r"]) for x in ok])), 4) if ok else None,
                                "matches_per_trade_mean": round(float(np.mean([len(x["random_r"]) for x in ok])), 1) if ok else None},
           "recorded_minus_random": day_boot(d_rec, [x["day"] for x in ok], rng),
           "replay_minus_random": day_boot(d_rep, [x["day"] for x in rep], rng)}
    races_out = {}
    for x in (10, 15, 20):
        dec = [y for y in recs if y["races"][x][0] is not None]
        k = sum(y["races"][x][0] for y in dec)
        rnd = [h for y in recs for h in y["random_hits"][x]]
        pair = [y for y in dec if y["random_hits"][x]]
        diff = np.array([y["races"][x][0] - np.mean(y["random_hits"][x]) for y in pair])
        mins = [y["races"][x][1] for y in dec if y["races"][x][0] == 1]
        races_out[f"usd{x}"] = {"decided": len(dec), "target_first": k, "rate": round(k / len(dec), 4) if dec else None,
                                "wilson95": wilson(k, len(dec)), "random_decided": len(rnd),
                                "random_rate": round(float(np.mean(rnd)), 4) if rnd else None,
                                "matched_difference": day_boot(diff, [y["day"] for y in pair], rng),
                                "minutes_to_target_median": round(float(np.median(mins)), 1) if mins else None,
                                "minutes_to_target_p75": round(float(np.quantile(mins, 0.75)), 1) if mins else None}
    out["target_before_stop"] = races_out
    mfe = np.array([x["mfe_mae"][0] for x in recs])
    mae = np.array([x["mfe_mae"][1] for x in recs])
    out["mfe_mae_usd"] = {"mfe_median": round(float(np.median(mfe)), 2) if len(mfe) else None,
                          "mfe_p75": round(float(np.quantile(mfe, 0.75)), 2) if len(mfe) else None,
                          "mae_median": round(float(np.median(mae)), 2) if len(mae) else None,
                          "mae_p75": round(float(np.quantile(mae, 0.75)), 2) if len(mae) else None,
                          "share_mfe_ge": {str(x): round(float(np.mean(mfe >= x)), 4) if len(mfe) else None for x in (10, 15, 20)}}
    clean = [x for x in recs if not x["reopen_inside"]]
    out["sensitivity_without_reopen_trades"] = {"trades": len(clean), "excluded": len(recs) - len(clean),
                                                "net_r_mean": round(float(np.mean([x["r"] for x in clean])), 4) if clean else None}
    return out


def verdicts(per: dict) -> list[str]:
    """The docstring's rule: ledgers with MIN_N trades or more are tested (Holm / BH across them); EDGE only if the
    recorded net mean R has a day-block interval above zero AND recorded-minus-random has Holm p < 0.05."""
    tested = [n for n, v in per.items() if v["trades"] >= MIN_N and v["recorded_minus_random"].get("p_le_0") is not None]
    ps = [per[n]["recorded_minus_random"]["p_le_0"] for n in tested]
    ho, bhv = (holm(ps), bh(ps)) if ps else ([], [])
    for n, v in per.items():
        if n in tested:
            i = tested.index(n)
            v["recorded_minus_random"]["p_holm"], v["recorded_minus_random"]["p_bh"] = ho[i], bhv[i]
            ci = v["net_r_modelled_cost"].get("ci95_days")
            v["verdict"] = ("EDGE (forward evidence)" if ci and ci[0] > 0 and ho[i] < 0.05
                            else "NO EDGE — INSUFFICIENT EVIDENCE")
        else:
            v["verdict"] = "INSUFFICIENT SAMPLE"
    return tested


def run(ledger: str, bars: str, k: int = 50, seed: int = 20261128, log=print) -> dict:
    key, books = load_ledgers(ledger)
    P = load_bars(bars)
    rng = np.random.default_rng(seed)
    per, by_arm, allr, skipped = {}, defaultdict(list), [], {}
    for (tf, arm), trades in sorted(books.items()):
        cand = candidates(P, tf)
        recs = [x for x in (one(t, tf, P, cand, k, rng) for t in trades) if x is not None]
        skipped[f"{tf}_{arm}"] = len(trades) - len(recs)
        per[f"{tf}_{arm}"] = summarise(recs, rng)
        by_arm[arm] += recs
        allr += recs
        log(f"[matched] {tf}_{arm}: {len(recs)} trades")
    tested = verdicts(per)
    return {"tool": "audit/tools/forward_matched.py", "freeze_key": key, "seed": seed, "k": k, "min_n": MIN_N,
            "bootstrap": B, "bars": {"first": int(P["t"][0]), "last": int(P["t"][-1]), "count": len(P["t"])},
            "skipped_no_bars": skipped, "ledgers": per,
            "arms": {a: summarise(v, rng) for a, v in sorted(by_arm.items())}, "all": summarise(allr, rng),
            "tested_ledgers": tested, "utc": datetime.now().astimezone().isoformat()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--bars", required=True)
    ap.add_argument("--json", required=True)
    ap.add_argument("--k", type=int, default=50)
    ap.add_argument("--seed", type=int, default=20261128)
    a = ap.parse_args(argv)
    out = run(a.ledger, a.bars, a.k, a.seed)
    with open(a.json, "w") as f:
        json.dump(out, f, indent=1, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
