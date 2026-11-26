"""Forward-test performance per arm and timeframe, with a matched random-entry baseline (read-only; audit GA-09, mandate §7).

  python3 audit/tools/forward_report.py --ledger <forward-ledger checkout> --bars <market-data checkout> \
      [--key 1f88aad357497da4:4440d52587f5cc6b] [--json out.json] [--md out.md] [--seed 20261126]

What it reads: <ledger>/holdout/<tf>_<arm>.json (the live ledgers; trades under the current engine key only) and the
stored 5-minute XAU/USD bars <bars>/XAU_USD_5m/*.csv plus each timeframe's own series (for random entry times).
It writes nothing into either checkout.

Per ledger: trades; wins / losses (net points > 0 / < 0); win rate (Wilson 95%); average win and loss in R; profit
factor; mean R with a trade-level and a DAY-CLUSTERED bootstrap 95% interval (trades on the same UTC day are resampled
together, because they overlap and share the day's move); sum R; maximum drawdown in R; longest losing streak; R per
trade / its standard deviation (a per-trade ratio, not an annualised Sharpe); average holding time; TP1 reached,
TP2 exits, stop exits (SL and SL_GAP), break-even and FLIP exits; the loss tail (worst trade, share of trades below
-1 R, 1st percentile); the trades needed for 80% power to detect a mean of
+0.10 R; and the mean R recomputed at a $0.50 and $0.80 spread (the operator's MT5 readings) instead of the
model's $0.30 (r' = r - (cost' - cost) / |entry - stop|).

Baseline (the entry's own value, independent of the arm's exit management): every trade's entry is raced on the
5-minute bars from its entry close: does price reach TP1 before the stop (a bar touching both counts as the stop; a
bar opening beyond a level fills there), within 7 days? The same race is run from K random bar closes of the same
timeframe inside the forward window, with the trade's direction, stop distance and TP1 distance. Undecided races are
left out. The random rate is what an entry with no information achieves with that geometry.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd

SERIES = {"5m": "XAU_USD_5m", "15m": "XAU_USD_15m", "30m": "XAU_USD_30m", "1h": "XAU_USD_60m", "4h": "XAU_USD_60m"}
TF_SEC = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}
HORIZON = 7 * 86400
SPREAD_MODEL, SPREADS = 0.30, (0.50, 0.80)
B = 10_000


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 4), round(c + h, 4))


def load_bars(d: str, name: str) -> pd.DataFrame:
    frames = []
    for f in sorted(glob.glob(os.path.join(d, name, "*.csv"))):
        x = pd.read_csv(f, index_col=0)
        x.index = pd.to_datetime(x.index, utc=True)
        frames.append(x[["open", "high", "low", "close"]].astype(float))
    df = pd.concat(frames)
    return df[~df.index.duplicated(keep="last")].sort_index()


def race(t5: np.ndarray, o, h, l, start: int, side: int, entry: float, sl: float, tp: float) -> str | None:
    """First touch from bar index `start` on: 'TP' | 'SL' | None (undecided within the horizon / data)."""
    end = int(np.searchsorted(t5, t5[start] + HORIZON, side="right")) if start < len(t5) else start
    for j in range(start, min(end, len(t5))):
        if side == 1:
            if o[j] <= sl or l[j] <= sl:
                return "SL"
            if o[j] >= tp or h[j] >= tp:
                return "TP"
        else:
            if o[j] >= sl or h[j] >= sl:
                return "SL"
            if o[j] <= tp or l[j] <= tp:
                return "TP"
    return None


def secs(idx: pd.DatetimeIndex) -> np.ndarray:
    """UTC seconds whatever the index resolution (pandas 3 parses these files at microseconds, not nanoseconds)."""
    return ((idx - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)).to_numpy().astype(np.int64)


def ts(s: str) -> int:
    return int(datetime.fromisoformat(s).timestamp())


def boot_mean(x: np.ndarray, rng) -> tuple:
    if len(x) < 5:
        return (None, None)
    m = rng.choice(x, size=(B, len(x)), replace=True).mean(axis=1)
    return (round(float(np.percentile(m, 2.5)), 4), round(float(np.percentile(m, 97.5)), 4))


def boot_day(r: np.ndarray, days: list, rng) -> tuple:
    groups = defaultdict(list)
    for v, d in zip(r, days):
        groups[d].append(v)
    g = list(groups.values())
    if len(g) < 5:
        return (None, None)
    sums = np.array([sum(v) for v in g])
    cnts = np.array([len(v) for v in g])
    idx = rng.integers(0, len(g), size=(B, len(g)))
    m = sums[idx].sum(axis=1) / cnts[idx].sum(axis=1)
    return (round(float(np.percentile(m, 2.5)), 4), round(float(np.percentile(m, 97.5)), 4))


def metrics(trades: list, rng) -> dict:
    r = np.array([t["r"] for t in trades], dtype=float)
    pts = np.array([t["pts"] for t in trades], dtype=float)
    n = len(r)
    wins, losses = r[pts > 0], r[pts < 0]
    cum = np.cumsum(r)
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum)) if n else 0.0
    streak = best = 0
    for p in pts:
        streak = streak + 1 if p < 0 else 0
        best = max(best, streak)
    sd = float(np.std(r, ddof=1)) if n > 1 else float("nan")
    hold = [(ts(t["exit_time"]) - ts(t["entry_time"])) / 60 for t in trades]
    reasons = defaultdict(int)
    for t in trades:
        reasons[t["exit_reason"]] += 1
    days = [t["entry_time"][:10] for t in trades]
    risk = np.array([abs(t["entry"] - t["sl"]) for t in trades])
    cost = np.array([t["cost_pts"] for t in trades])
    sens = {}
    for s in SPREADS:
        r2 = r - (s - SPREAD_MODEL) / np.where(risk > 0, risk, np.nan)      # only the spread changes
        sens[f"spread_{s:.2f}"] = round(float(np.nanmean(r2)), 4) if n else None
    return {
        "trades": n, "wins": int((pts > 0).sum()), "losses": int((pts < 0).sum()), "flat": int((pts == 0).sum()),
        "win_rate": round(float((pts > 0).mean()), 4) if n else None, "win_rate_wilson95": wilson(int((pts > 0).sum()), n),
        "avg_win_r": round(float(wins.mean()), 4) if len(wins) else None,
        "avg_loss_r": round(float(losses.mean()), 4) if len(losses) else None,
        "profit_factor": round(float(r[r > 0].sum() / -r[r < 0].sum()), 3) if (r < 0).any() else None,
        "mean_r": round(float(r.mean()), 4) if n else None,
        "mean_r_boot95_trades": boot_mean(r, rng), "mean_r_boot95_days": boot_day(r, days, rng),
        "trading_days": len(set(days)), "sum_r": round(float(r.sum()), 3), "max_drawdown_r": round(dd, 3),
        "longest_losing_streak": best,
        "worst_r": round(float(r.min()), 4) if n else None,                       # GA-10: the tail, not only the mean
        "share_below_minus_1r": round(float((r < -1.0).mean()), 4) if n else None,
        "r_p01": round(float(np.percentile(r, 1)), 4) if n else None,
        "r_per_sd": round(float(r.mean() / sd), 4) if n > 1 and sd > 0 else None,
        "avg_hold_min": round(float(np.mean(hold)), 1) if n else None,
        "tp1_reached": int(sum(bool(t.get("tp1_hit")) for t in trades)),
        "exits": dict(sorted(reasons.items())),
        "stop_exits": reasons.get("SL", 0) + reasons.get("SL_GAP", 0),
        "n_for_80pct_power_at_0.10R": math.ceil(((1.96 + 0.8416) * sd / 0.10) ** 2) if n > 1 and sd > 0 else None,
        "mean_r_at_spread": sens, "cost_pts_used": sorted({round(float(c), 3) for c in cost}),
    }


def baseline(trades: list, tf: str, bars5: pd.DataFrame, tfbars: pd.DataFrame, t_lo: int, k: int, rng) -> dict:
    t5 = secs(bars5.index)
    o, h, l = (bars5[c].to_numpy() for c in ("open", "high", "low"))
    sec = TF_SEC[tf]
    closes = secs(tfbars.index) + (3600 if tf == "4h" else sec)
    pool = closes[(closes >= t_lo) & (closes <= t5[-1] - 86400)]
    act, rnd = [], []
    for t in trades:
        side = 1 if t["dir"] == "LONG" else -1
        d_sl, d_tp = abs(t["entry"] - t["sl"]), abs(t["tp1"] - t["entry"])
        start = int(np.searchsorted(t5, ts(t["entry_time"]) + sec, side="left"))
        a = race(t5, o, h, l, start, side, t["entry"], t["sl"], t["tp1"])
        if a:
            act.append(a == "TP")
        for tc in rng.choice(pool, size=min(k, len(pool)), replace=False) if len(pool) else []:
            j = int(np.searchsorted(t5, tc, side="left"))           # first 5m bar opening at or after the close
            if j < 1 or j >= len(t5):
                continue
            e = float(bars5["close"].iloc[j - 1])                    # the price at that close
            res = race(t5, o, h, l, j, side, e, e - side * d_sl, e + side * d_tp)
            if res:
                rnd.append(res == "TP")
    ka, na, kr, nr = sum(act), len(act), sum(rnd), len(rnd)
    out = {"entries_decided": na, "tp1_first": ka, "tp1_first_rate": round(ka / na, 4) if na else None,
           "wilson95": wilson(ka, na), "random_decided": nr, "random_tp1_first_rate": round(kr / nr, 4) if nr else None,
           "random_per_trade": k}
    if na and nr:
        p0 = kr / nr
        out["difference"] = round(ka / na - p0, 4)
        # how unusual the entries' count is if each had the random rate (binomial tails)
        from math import comb
        pmf = [comb(na, i) * p0 ** i * (1 - p0) ** (na - i) for i in range(na + 1)]
        out["p_at_least"] = round(sum(pmf[ka:]), 4)
        out["p_at_most"] = round(sum(pmf[:ka + 1]), 4)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--bars", required=True)
    ap.add_argument("--key", default=None, help="main engine key; default: the ledger's holdout_manifest.json")
    ap.add_argument("--random", type=int, default=50)
    ap.add_argument("--seed", type=int, default=20261126)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    with open(os.path.join(a.ledger, "holdout_manifest.json")) as f:
        man = json.load(f)
    key = a.key or man["freeze_key"]
    t_lo = ts(man["freeze_utc"][:19] + "+00:00")
    rng = np.random.default_rng(a.seed)
    bars5 = load_bars(a.bars, SERIES["5m"])
    cache = {}
    out = {"key": key, "freeze_utc": man["freeze_utc"], "bars_5m": [str(bars5.index[0]), str(bars5.index[-1]), len(bars5)],
           "seed": a.seed, "ledgers": {}}
    for f in sorted(glob.glob(os.path.join(a.ledger, "holdout", "*_*.json"))):
        name = os.path.basename(f)[:-5]
        if name.startswith("manifest"):
            continue
        tf = name.split("_", 1)[0]
        with open(f) as fh:
            tr = [t for t in json.load(fh) if ":".join(t.get("freeze_key", "").split(":")[:2]) == key and not t.get("open")]
        if not tr:
            continue
        if SERIES[tf] not in cache:
            cache[SERIES[tf]] = load_bars(a.bars, SERIES[tf])
        m = metrics(tr, rng)
        m["baseline"] = baseline(tr, tf, bars5, cache[SERIES[tf]], t_lo, a.random, rng)
        out["ledgers"][name] = m
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(out, fh, indent=1)
    for k, m in out["ledgers"].items():
        b = m["baseline"]
        print(f"{k:16s} n {m['trades']:4d} win {m['win_rate']} mean {m['mean_r']} trades95 {m['mean_r_boot95_trades']} "
              f"days95 {m['mean_r_boot95_days']} | TP1-first {b['tp1_first_rate']} vs random {b['random_tp1_first_rate']} "
              f"(n {b['entries_decided']}/{b['random_decided']}, p>= {b.get('p_at_least')}, p<= {b.get('p_at_most')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
