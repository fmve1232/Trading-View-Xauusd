"""G5 risk analytics of RECORDED forward trades (operator mandate 27 Nov 2026; read-only, descriptive).

Usage: python audit/tools/risk_analytics.py <dir holding holdout/*.json> [--json out] [--sims 10000] [--seed 20261127]
       python audit/tools/risk_analytics.py --doc <evidence.json> <document.md> [--check]
         (rewrites the document's generated block from the evidence file; --check: exit 1 if it differs)

Per arm and timeframe (and per freeze key, since H6 carries the previous one), from the ledger trades as recorded:

  expectancy   mean R BEFORE cost (gross_pts / stop), AFTER the modelled cost of record (the ledger's net r), and the
               modelled cost itself; measured broker cost: NOT AVAILABLE (no fills yet, G2). Intervals: day-block
               bootstrap (whole trading days resampled), seeded.
  tail         VaR 5% = the k-th worst outcome, CVaR 5% (expected shortfall) = the mean of the k worst, k = ceil(0.05 n),
               per trade (net R) and per trading day (the day's summed net R). With n < 20, k = 1: CVaR is the single
               worst outcome; the record says so.
  drawdown     the observed maximum drawdown of cumulative net R in exit order, and a Monte Carlo distribution of it:
               a stationary bootstrap (Politis & Romano 1994) over TRADING DAYS with mean block length L, so trades of
               one day stay together and in order (intraday dependence) and runs of consecutive days stay together
               (daily dependence). Each path has as many days as the record; reported: the 50th / 95th / 99th
               percentiles in R, the 95th also in $ at $650 per R (the operator's planned maximum loss per trade, an
               ASSUMPTION of the plan, not a measured fill), for L = 1, 2 and 5 days.

A trading day is the New York session day (it starts at 17:00 New York), dated by the trade's exit.

Limitations, also written into the output: the forward record covers few weeks; resampling cannot produce a regime
the record does not contain, so the Monte Carlo drawdown is a lower bound on what a longer record could show; trades
of different arms are treated separately (combined exposure is G6); costs are modelled, not measured.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import os
import re
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

NY = ZoneInfo("America/New_York")
LEDGER_RE = re.compile(r"^(5m|15m|30m|1h|4h)_([a-z0-9]+)\.json$")
USD_PER_R = 650.0                      # the operator's planned maximum loss per trade including costs (an assumption)
BLOCKS = (1, 2, 5)
ALPHA = 0.05


def session_day(iso: str) -> str:
    """The New York session day of a timestamp: the day starts at 17:00 New York."""
    t = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(NY)
    return (t + timedelta(hours=7)).date().isoformat()


def load(store: str) -> dict:
    groups: dict = {}
    for f in sorted(glob.glob(os.path.join(store, "holdout", "*.json"))):
        m = LEDGER_RE.match(os.path.basename(f))
        if not m:
            continue
        with open(f) as fh:
            rows = json.load(fh)
        for t in rows if isinstance(rows, list) else []:
            if t.get("open"):
                continue
            key = (m.group(2), m.group(1), t.get("freeze_key") or t.get("config_hash") or "")
            groups.setdefault(key, []).append(t)
    for v in groups.values():
        v.sort(key=lambda t: (t["exit_time"], t["entry_time"]))
    return groups


def tail(x: np.ndarray, alpha: float = ALPHA) -> dict:
    """VaR and CVaR (expected shortfall) at level alpha: k = ceil(alpha n) worst outcomes."""
    n = len(x)
    if n == 0:
        return {"n": 0, "k": 0, "var": None, "cvar": None, "note": "no data"}
    k = max(1, math.ceil(alpha * n))
    w = np.sort(x)[:k]
    return {"n": n, "k": k, "var": round(float(w[-1]), 4), "cvar": round(float(w.mean()), 4),
            "note": "k = 1: the single worst outcome" if k == 1 else ""}


def max_drawdown(r: np.ndarray) -> float:
    """Largest fall of cumulative R from a running peak (the start counts as a peak at 0)."""
    if not len(r):
        return 0.0
    eq = np.concatenate([[0.0], np.cumsum(r)])
    return float(np.max(np.maximum.accumulate(eq) - eq))


def stationary_days(n_days: int, mean_block: float, rng: np.random.Generator) -> np.ndarray:
    """Day indices of one stationary-bootstrap path of n_days: a block starts at a uniform day and continues to the
    next day (wrapping) with probability 1 - 1/mean_block."""
    out = np.empty(n_days, dtype=np.int64)
    p_new = 1.0 / mean_block
    cur = int(rng.integers(n_days))
    for i in range(n_days):
        if i == 0 or rng.random() < p_new:
            cur = int(rng.integers(n_days))
        else:
            cur = (cur + 1) % n_days
        out[i] = cur
    return out


def mc_drawdown(days: list[np.ndarray], mean_block: float, sims: int, rng: np.random.Generator) -> np.ndarray:
    """Maximum drawdown (R) of `sims` stationary-bootstrap paths over whole trading days (each day's trades in order)."""
    n = len(days)
    out = np.empty(sims)
    for s in range(sims):
        idx = stationary_days(n, mean_block, rng)
        out[s] = max_drawdown(np.concatenate([days[i] for i in idx]))
    return out


def day_boot_mean(days: list[np.ndarray], sims: int, rng: np.random.Generator) -> list[float] | None:
    """95% interval of the per-trade mean by resampling whole days with replacement."""
    n = len(days)
    if n < 2:
        return None
    sums = np.array([d.sum() for d in days])
    cnt = np.array([len(d) for d in days])
    pick = rng.integers(0, n, size=(sims, n))
    m = sums[pick].sum(1) / np.maximum(cnt[pick].sum(1), 1)
    return [round(float(np.quantile(m, 0.025)), 4), round(float(np.quantile(m, 0.975)), 4)]


def analyse(trades: list[dict], sims: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    d_sl = np.array([abs(t["entry"] - t["sl"]) for t in trades], float)
    ok = d_sl > 0
    net = np.array([t["r"] for t in trades], float)[ok]
    gross = (np.array([t["gross_pts"] for t in trades], float)[ok] / d_sl[ok])
    cost = (np.array([t["cost_pts"] for t in trades], float)[ok] / d_sl[ok])
    tr = [t for t, k in zip(trades, ok, strict=True) if k]
    day_of = [session_day(t["exit_time"]) for t in tr]
    order = sorted(set(day_of))
    pos = {d: i for i, d in enumerate(order)}
    by_day_net: list[list[float]] = [[] for _ in order]
    by_day_gross: list[list[float]] = [[] for _ in order]
    for i, d in enumerate(day_of):
        by_day_net[pos[d]].append(net[i])
        by_day_gross[pos[d]].append(gross[i])
    dn = [np.array(x) for x in by_day_net]
    dg = [np.array(x) for x in by_day_gross]
    n = len(net)
    out = {
        "n": n, "days": len(order), "first_exit_day": order[0] if order else None, "last_exit_day": order[-1] if order else None,
        "excluded_zero_stop": int((~ok).sum()),
        "expectancy_r": {
            "before_cost": round(float(gross.mean()), 4) if n else None,
            "before_cost_day_boot95": day_boot_mean(dg, sims, rng),
            "after_modelled_cost": round(float(net.mean()), 4) if n else None,
            "after_modelled_cost_day_boot95": day_boot_mean(dn, sims, rng),
            "modelled_cost": round(float(cost.mean()), 4) if n else None,
            "after_measured_cost": None,
            "measured_cost_status": "NOT AVAILABLE: no broker fills yet (G2)",
            "usd_at_650_per_r_after_modelled_cost": round(float(net.mean()) * USD_PER_R, 2) if n else None,
        },
        "tail_per_trade_net_r": tail(net),
        "tail_per_day_net_r": {**tail(np.array([x.sum() for x in dn])), "days": "days with at least one exit"},
        "observed_max_drawdown_r": round(max_drawdown(net), 4),
        "monte_carlo_drawdown": {},
    }
    if len(order) >= 2:
        for L in BLOCKS:
            dd = mc_drawdown(dn, L, sims, rng)
            q = {p: round(float(np.quantile(dd, p / 100)), 4) for p in (50, 95, 99)}
            out["monte_carlo_drawdown"][f"L={L}d"] = {"p50_r": q[50], "p95_r": q[95], "p99_r": q[99],
                                                     "p95_usd_at_650_per_r": round(q[95] * USD_PER_R, 0)}
    else:
        out["monte_carlo_drawdown"]["note"] = "fewer than 2 trading days: not computed"
    return out


def group_seed(seed: int, key: str) -> int:
    """A group's own seed: the run seed plus a stable hash of its key, so adding a group never changes another's."""
    return seed + int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


def run(store: str, sims: int = 10000, seed: int = 20261127) -> dict:
    groups = load(store)
    res = {}
    for (arm, tf, key), trades in sorted(groups.items()):
        gk = f"{arm}|{tf}|{key}"
        res[gk] = {"arm": arm, "tf": tf, "freeze_key": key, "seed": group_seed(seed, gk), **analyse(trades, sims, group_seed(seed, gk))}
    return {"method": {"sims": sims, "seed": seed, "alpha": ALPHA, "mean_block_days": list(BLOCKS),
                       "usd_per_r": USD_PER_R, "usd_per_r_status": "ASSUMPTION: the plan's maximum loss per trade",
                       "day": "New York session day (starts 17:00 New York), by exit time",
                       "limitations": [
                           "the forward record covers few weeks: tails and drawdowns are estimated from few days",
                           ("resampling cannot produce a regime the record does not contain: the Monte Carlo drawdown "
                            "is a lower bound on what a longer record could show"),
                           "each arm and timeframe alone; combined exposure across arms is G6",
                           "costs are the engine's model of record, not broker-measured (G2)",
                           "descriptive: nothing here selects a parameter"]},
            "groups": res}


BEGIN = "<!-- G5:BEGIN (generated by audit/tools/risk_analytics.py --doc; do not edit) -->"
END = "<!-- G5:END -->"


def _ci(x) -> str:
    return "—" if x is None else f"[{x[0]}, {x[1]}]"


def markdown(out: dict) -> str:
    m = out["method"]
    intro = (f"Simulations {m['sims']} per block length; seed {m['seed']} (each group adds a stable hash of its key); "
             f"tail level {m['alpha']}; block lengths {m['mean_block_days']} days; $ per R = {m['usd_per_r']} "
             f"({m['usd_per_r_status']}). Day: {m['day']}.")
    head = ("| Arm · TF · freeze key | n | days | E[R] before cost [day-boot 95%] | E[R] after modelled cost [day-boot 95%] "
            "| modelled cost R | E[R] after measured cost | CVaR 5% per trade (k) | CVaR 5% per day (k) | max DD observed R "
            "| MC max DD p95 R, L = 1 / 2 / 5 d | MC p95 $ at L = 2 d |")
    rows = [intro, "", head, "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for g in out["groups"].values():
        e, mc = g["expectancy_r"], g["monte_carlo_drawdown"]
        has = f"L={BLOCKS[0]}d" in mc
        p95 = " / ".join(str(mc[f"L={L}d"]["p95_r"]) for L in BLOCKS) if has else "— (under 2 days)"
        usd = f"{mc['L=2d']['p95_usd_at_650_per_r']:,.0f}" if has else "—"
        tt, td = g["tail_per_trade_net_r"], g["tail_per_day_net_r"]
        rows.append(f"| {g['arm']} · {g['tf']} · `{g['freeze_key'][:16]}` | {g['n']} | {g['days']} | {e['before_cost']} "
                    f"{_ci(e['before_cost_day_boot95'])} | {e['after_modelled_cost']} {_ci(e['after_modelled_cost_day_boot95'])} "
                    f"| {e['modelled_cost']} | not available (G2) | {tt['cvar']} ({tt['k']}) | {td['cvar']} ({td['k']}) "
                    f"| {g['observed_max_drawdown_r']} | {p95} | {usd} |")
    rows += ["", "Limitations written into the evidence file:", ""] + [f"- {x}" for x in m["limitations"]]
    return "\n".join(rows)


def write_doc(evidence: str, doc: str, check: bool = False) -> int:
    with open(evidence) as f:
        out = json.load(f)
    with open(doc) as f:
        text = f.read()
    i, j = text.index(BEGIN), text.index(END) + len(END)
    new = text[:i] + BEGIN + "\n\n" + markdown(out) + "\n\n" + END + text[j:]
    if check:
        return 0 if new == text else 1
    with open(doc, "w") as f:
        f.write(new)
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--doc":
        rc = write_doc(argv[1], argv[2], "--check" in argv)
        print("G5 document matches the evidence" if rc == 0 else "G5 document differs from the evidence")
        return rc
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("store")
    ap.add_argument("--json")
    ap.add_argument("--sims", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=20261127)
    a = ap.parse_args(argv)
    out = run(a.store, a.sims, a.seed)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(out, f, indent=1)
    print(markdown(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
