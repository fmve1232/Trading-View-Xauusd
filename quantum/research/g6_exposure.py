"""G6-EXPOSURE (research/registrations/G6-EXPOSURE.json): aggregate exposure across the frozen engine's treatment arm and
arm H4 on 5m / 15m / 30m / 1h, and five exposure policies compared on the DEVELOPMENT partition, in SHADOW mode.
RESEARCH ONLY: never imported by production, nothing here is enforced anywhere, and no policy is adopted. The forward
ledgers are measured descriptively (no policy is replayed or compared on them).

A position is open from its fill (the close of its signal bar: entry_time + one bar) until the close of its exit bar
(exit_time + one bar): exact for a FLIP (filled at that close) and the latest possible instant for an intrabar stop or
target, so concurrency is never understated. Each open position carries one R of initial risk (its own stop distance).

  python -m quantum.research.g6_exposure dev     --rd <research-data checkout> --out research/G6_EXPOSURE_RESULTS.json
                                                 [--trials research/trials.jsonl]
  python -m quantum.research.g6_exposure forward --ledger <dir holding holdout/<tf>_<arm>.json> --store <store dir>
                                                 --out docs/final_audit/evidence/g6_forward_exposure_<day>.json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .. import arm_h2, arm_h3, arm_h4, arm_h5, backtest, config, engine
from ..data import sources, store
from ..features import compute as compute_features
from . import b10, history
from . import harness as H

REG = "G6-EXPOSURE"
SEED = 20261128
NY = ZoneInfo("America/New_York")
TFS = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600}
ARMS = ("treatment", "h4")
# amendment A1: every live forward-test arm (h6 is closed, Amendment F) on 5m-4h, as a second family
TFS_A1 = {**TFS, "4h": 14400}
ARMS_A1 = ("treatment", "control", "challenger", "h2", "h3", "h4", "h5")
FAMILIES = {"primary": (TFS, ARMS), "a1": (TFS_A1, ARMS_A1)}
SEC = TFS_A1
# tie-break at the same fill time: higher timeframe first, then the arm order (registration "tie_break", A1 "tie_break");
# the A1 additions keep the primary order (1h before 30m before 15m before 5m; treatment before h4)
TF_RANK = {"4h": -1, "1h": 0, "30m": 1, "15m": 2, "5m": 3}
ARM_RANK = {a: i for i, a in enumerate(ARMS_A1)}
OVERLAP_SEC = 3600                                         # "entries in the same direction within 60 minutes"
PER_DAY = 3
MAX_OPEN = 3
PLAN_LOSS_USD = 650.0                                      # the operator's maximum planned loss per trade (CLAUDE.md)
POLICIES = ("P0_none", "P1_one_open", "P2_one_open_three_per_day", "P3_three_open", "P4_one_open_per_direction")
COMPARISONS = (("P1_one_open", "P0_none"), ("P2_one_open_three_per_day", "P0_none"), ("P3_three_open", "P0_none"),
               ("P4_one_open_per_direction", "P0_none"), ("P1_one_open", "P2_one_open_three_per_day"))
MEASURES = ("mean_net_r_per_trade", "net_r_per_day")
CURRENT_FREEZE = "1f88aad357497da4:4440d52587f5cc6b"


def ts(iso: str) -> int:
    return int(pd.Timestamp(iso).timestamp())


def session_day(t: int) -> str:
    """The New York trading day (17:00 New York to 17:00 New York), as the rest of the research code uses it."""
    return (datetime.fromtimestamp(t, NY) + timedelta(hours=7)).date().isoformat()


# ---------------- positions ----------------
def positions(trades_by_key: dict, start: int | None = None) -> tuple[list[dict], dict]:
    """Closed trades of every (timeframe, arm) as positions, in the registered order (fill time, then timeframe, then
    arm). Trades still open at the end of the data and fills before `start` are left out and counted."""
    out, skipped = [], {"open_at_end": 0, "before_common_start": 0}
    for (tf, arm), trades in trades_by_key.items():
        sec = SEC[tf]
        for k, t in enumerate(trades):
            if t.get("open"):
                skipped["open_at_end"] += 1
                continue
            fill = ts(t["entry_time"]) + sec
            if start is not None and fill < start:
                skipped["before_common_start"] += 1
                continue
            end = ts(t["exit_time"]) + sec
            out.append({"tf": tf, "arm": arm, "k": k, "d": 1 if t["dir"] == "LONG" else -1, "fill": fill, "end": end,
                        "r": float(t["r"]), "tp1": bool(t.get("tp1_hit")), "stop_usd": abs(float(t["entry"]) - float(t["sl"])),
                        "session": str(t.get("session") or "NA"), "reason": str(t.get("exit_reason") or ""),
                        "day": session_day(fill), "exit_day": session_day(end)})
    out.sort(key=lambda p: (p["fill"], TF_RANK[p["tf"]], ARM_RANK[p["arm"]], p["k"]))
    for i, p in enumerate(out):
        p["i"] = i
    return out, skipped


def replay(pos: list[dict], policy: str) -> list[bool]:
    """First-order replay: each recorded position is kept or blocked by the policy, in the registered order; a blocked
    position never opens and never frees a slot; the arms' own sequences are not re-simulated."""
    keep, open_, per_day = [], [], Counter()
    for p in pos:
        open_ = [q for q in open_ if q["end"] > p["fill"]]                 # a position closing at this instant is free
        if policy == "P0_none":
            ok = True
        elif policy == "P1_one_open":
            ok = not open_
        elif policy == "P2_one_open_three_per_day":
            ok = not open_ and per_day[p["day"]] < PER_DAY
        elif policy == "P3_three_open":
            ok = len(open_) < MAX_OPEN
        elif policy == "P4_one_open_per_direction":
            ok = not any(q["d"] == p["d"] for q in open_)
        else:
            raise ValueError(policy)
        keep.append(ok)
        if ok:
            open_.append(p)
            per_day[p["day"]] += 1
    return keep


# ---------------- exposure measurements ----------------
def counts_at(pos: list[dict], grid: np.ndarray) -> dict:
    """Open positions at each sample instant g (fill <= g < end): all, long, short."""
    out = {}
    for name, sel in (("all", pos), ("long", [p for p in pos if p["d"] == 1]), ("short", [p for p in pos if p["d"] == -1])):
        f = np.sort(np.array([p["fill"] for p in sel], np.int64))
        e = np.sort(np.array([p["end"] for p in sel], np.int64))
        out[name] = np.searchsorted(f, grid, "right") - np.searchsorted(e, grid, "right")
    return out


def exact_max(pos: list[dict]) -> dict:
    """The exact maximum number open at once (event sweep; a close at the same instant as a fill comes first), its
    first instant, and the largest simultaneous sum of stop distances (USD per ounce)."""
    ev = sorted([(p["fill"], 1, p["stop_usd"]) for p in pos] + [(p["end"], -1, p["stop_usd"]) for p in pos],
                key=lambda x: (x[0], x[1]))
    n = best = 0
    usd = best_usd = 0.0
    at = None
    for t, s, u in ev:
        n += s
        usd += s * u
        if n > best:
            best, at = n, t
        best_usd = max(best_usd, usd)
    return {"max_open": best, "first_at_utc": None if at is None else datetime.fromtimestamp(at, timezone.utc).isoformat(),
            "max_sum_stop_usd_per_oz": round(best_usd, 2)}


def _dist(x: np.ndarray) -> dict:
    if not len(x):
        return {"samples": 0}
    vals, cnt = np.unique(x, return_counts=True)
    return {"samples": len(x), "mean": round(float(np.mean(x)), 4), "max": int(np.max(x)),
            "share": {str(int(v)): round(float(c) / len(x), 4) for v, c in zip(vals, cnt, strict=True)},
            "share_2_plus": round(float(np.mean(x >= 2)), 4), "share_3_plus": round(float(np.mean(x >= 3)), 4)}


def concurrency(pos: list[dict], grid: np.ndarray) -> dict:
    """Registered measurements 'concurrency', 'direction', 'combined_stop' and the time part of 'correlated', sampled at
    every 5-minute bar close in the window (market hours only: bars exist only while the market trades)."""
    c = counts_at(pos, grid)
    a, lg, sh = c["all"], c["long"], c["short"]
    held = a > 0
    hours = np.array([datetime.fromtimestamp(int(g), NY).hour for g in grid]) if len(grid) else np.array([], int)
    return {"open_positions": _dist(a), "long_open": _dist(lg), "short_open": _dist(sh),
            "net_long_minus_short": {"mean": round(float(np.mean(lg - sh)), 4) if len(grid) else None,
                                     "min": int(np.min(lg - sh)) if len(grid) else None,
                                     "max": int(np.max(lg - sh)) if len(grid) else None},
            "share_of_time_any_open": round(float(np.mean(held)), 4) if len(grid) else None,
            "share_of_time_two_plus_same_direction": round(float(np.mean((lg >= 2) | (sh >= 2))), 4) if len(grid) else None,
            "share_of_time_long_and_short_together": round(float(np.mean((lg >= 1) & (sh >= 1))), 4) if len(grid) else None,
            "mean_open_by_new_york_hour": {str(h): round(float(np.mean(a[hours == h])), 4) for h in range(24) if (hours == h).any()},
            "exact": exact_max(pos),
            "combined_stop_r": {"max_r_at_risk": int(np.max(a)) if len(grid) else 0,
                                "max_usd_if_every_position_risked_650": int(np.max(a)) * PLAN_LOSS_USD if len(grid) else 0.0,
                                "note": "1 R per open position (its own stop); the USD figure is MODELLED: it assumes every "
                                        "position were taken at the operator's $650 planned loss, which the operator does not do"}}


def correlated(pos: list[dict]) -> dict:
    """Registered measurement 'correlated': same-direction entries within 60 minutes on another timeframe (and on the other
    arm of the same timeframe), and the outcomes of positions open together in the same direction."""
    fills = np.array([p["fill"] for p in pos], np.int64)
    cross_tf = cross_arm = 0
    for i, p in enumerate(pos):
        lo, hi = np.searchsorted(fills, p["fill"] - OVERLAP_SEC, "left"), np.searchsorted(fills, p["fill"] + OVERLAP_SEC, "right")
        nb = [pos[j] for j in range(lo, hi) if j != i and pos[j]["d"] == p["d"]]
        cross_tf += any(q["tf"] != p["tf"] for q in nb)
        cross_arm += any(q["tf"] == p["tf"] and q["arm"] != p["arm"] for q in nb)
    pairs, open_ = [], []
    for p in pos:
        open_ = [q for q in open_ if q["end"] > p["fill"]]
        pairs += [(q["r"] < 0, p["r"] < 0) for q in open_ if q["d"] == p["d"] and (q["tf"], q["arm"]) != (p["tf"], p["arm"])]
        open_.append(p)
    out = {"entries": len(pos),
           "share_with_same_direction_entry_on_another_tf_within_60m": round(cross_tf / len(pos), 4) if pos else None,
           "share_with_same_direction_entry_on_other_arm_same_tf_within_60m": round(cross_arm / len(pos), 4) if pos else None,
           "same_direction_pairs_open_together": len(pairs)}
    if pairs:
        x = np.array(pairs, float)
        a, b = x[:, 0], x[:, 1]
        both = float(np.mean(a * b))
        sa, sb = float(np.std(a)), float(np.std(b))
        out |= {"both_lost_share": round(both, 4), "independence_expectation": round(float(np.mean(a)) * float(np.mean(b)), 4),
                "phi_loss_loss": round((both - float(np.mean(a)) * float(np.mean(b))) / (sa * sb), 4) if sa > 0 and sb > 0 else None}
    return out


def sessions(pos: list[dict]) -> dict:
    """Registered measurement 'session': entries, initial R and net R by the engine's session label at the entry, and how
    many positions were already open when each entry filled."""
    by = defaultdict(list)
    open_ = []
    for p in pos:
        open_ = [q for q in open_ if q["end"] > p["fill"]]
        by[p["session"]].append((p["r"], len(open_)))
        open_.append(p)
    return {s: {"entries": len(v), "initial_r": len(v), "net_r": round(sum(x for x, _ in v), 2),
                "mean_net_r": round(float(np.mean([x for x, _ in v])), 4),
                "mean_already_open_at_entry": round(float(np.mean([y for _, y in v])), 4)} for s, v in sorted(by.items())}


def max_dd(r: list[float]) -> float:
    if not r:
        return 0.0
    eq = np.concatenate([[0.0], np.cumsum(r)])
    return round(float(np.max(np.maximum.accumulate(eq) - eq)), 4)


def streak(r: list[float]) -> int:
    best = cur = 0
    for x in r:
        cur = cur + 1 if x < 0 else 0
        best = max(best, cur)
    return best


def book(pos: list[dict]) -> dict:
    """Registered measurements 'daily', 'streaks' and 'drawdown' for one set of positions (exit order for P/L)."""
    if not pos:
        return {"trades": 0}
    ex = sorted(pos, key=lambda p: (p["end"], p["fill"], p["i"]))
    r = [p["r"] for p in ex]
    entries = Counter(p["day"] for p in pos)
    realised = defaultdict(float)
    for p in pos:
        realised[p["exit_day"]] += p["r"]
    e = np.array(list(entries.values()), float)
    rv = np.array(list(realised.values()), float)
    worst_day = min(realised, key=realised.get)
    return {"trades": len(pos), "days_with_entries": len(entries), "net_r": round(sum(r), 2),
            "mean_net_r": round(float(np.mean(r)), 4), "win_rate": round(float(np.mean([x > 0 for x in r])), 4),
            "tp1_first_share": round(float(np.mean([p["tp1"] for p in pos])), 4),
            "worst_trade_r": round(min(r), 4), "gap_exits": sum(p["reason"].endswith("_GAP") for p in pos),
            "max_dd_r": max_dd(r), "longest_losing_streak": streak(r),
            "potential_daily_loss_r": {"note": "entries per New York day x 1 R each (the stop); costs and gaps can exceed it",
                                       "mean": round(float(np.mean(e)), 3), "p95": float(np.quantile(e, 0.95)),
                                       "max": int(np.max(e)), "max_day": max(entries, key=entries.get),
                                       "max_usd_if_every_position_risked_650": int(np.max(e)) * PLAN_LOSS_USD},
            "realised_daily_r": {"mean": round(float(np.mean(rv)), 4), "p05": round(float(np.quantile(rv, 0.05)), 4),
                                 "worst": round(float(realised[worst_day]), 4), "worst_day": worst_day}}


# ---------------- comparisons ----------------
def day_sums(pos: list[dict], keep: list[bool], days: list[str]) -> tuple[np.ndarray, np.ndarray]:
    ix = {d: i for i, d in enumerate(days)}
    s, n = np.zeros(len(days)), np.zeros(len(days))
    for p, k in zip(pos, keep, strict=True):
        if k:
            s[ix[p["day"]]] += p["r"]
            n[ix[p["day"]]] += 1
    return s, n


def compare(pos: list[dict], keeps: dict, rng, sims: int = 4000) -> list[dict]:
    """Each registered comparison on both measures, with a PAIRED day-block bootstrap (the same resampled days for both
    policies) 95% interval and a two-sided bootstrap p for the difference A - B."""
    days = sorted({p["day"] for p in pos})
    pick = rng.integers(0, len(days), size=(sims, len(days)))
    sums = {k: day_sums(pos, v, days) for k, v in keeps.items()}
    out = []
    for a, b in COMPARISONS:
        (sa, na), (sb, nb) = sums[a], sums[b]
        row = {"a": a, "b": b}
        for m in MEASURES:
            if m == "mean_net_r_per_trade":
                obs = sa.sum() / max(na.sum(), 1) - sb.sum() / max(nb.sum(), 1)
                bs = sa[pick].sum(1) / np.maximum(na[pick].sum(1), 1) - sb[pick].sum(1) / np.maximum(nb[pick].sum(1), 1)
            else:
                obs = (sa.sum() - sb.sum()) / len(days)
                bs = (sa[pick].sum(1) - sb[pick].sum(1)) / len(days)
            p = min(1.0, 2.0 * min(float(np.mean(bs <= 0)), float(np.mean(bs >= 0))))
            row[m] = {"diff": round(float(obs), 4), "ci95": [round(float(np.quantile(bs, 0.025)), 4),
                                                              round(float(np.quantile(bs, 0.975)), 4)], "p_two_sided": round(p, 4)}
        out.append(row)
    ps = [r[m]["p_two_sided"] for r in out for m in MEASURES]
    ho, bhv = holm(ps), bh(ps)
    for j, (r, m) in enumerate((r, m) for r in out for m in MEASURES):
        r[m]["p_holm"], r[m]["p_bh"] = ho[j], bhv[j]
    return out


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


def blocked(pos: list[dict], keep: list[bool]) -> dict:
    b = [p for p, k in zip(pos, keep, strict=True) if not k]
    if not b:
        return {"count": 0}
    return {"count": len(b), "share_of_all": round(len(b) / len(pos), 4), "mean_net_r": round(float(np.mean([p["r"] for p in b])), 4),
            "net_r": round(sum(p["r"] for p in b), 2), "tp1_first_share": round(float(np.mean([p["tp1"] for p in b])), 4),
            "by_tf_arm": dict(sorted(Counter(f"{p['tf']}_{p['arm']}" for p in b).items()))}


def study(pos: list[dict], grid: np.ndarray, rng, with_policies: bool) -> dict:
    out = {"positions": len(pos), "by_tf_arm": dict(sorted(Counter(f"{p['tf']}_{p['arm']}" for p in pos).items())),
           "concurrency": concurrency(pos, grid), "correlated": correlated(pos), "sessions": sessions(pos), "book": book(pos)}
    if with_policies:
        keeps = {k: replay(pos, k) for k in POLICIES}
        out["policies"] = {k: {"book": book([p for p, x in zip(pos, v, strict=True) if x]), "blocked": blocked(pos, v),
                               "concurrency": _dist(counts_at([p for p, x in zip(pos, v, strict=True) if x], grid)["all"])}
                           for k, v in keeps.items()}
        out["comparisons"] = compare(pos, keeps, rng)
    return out


# ---------------- runs ----------------
def dev_trades(bases: dict, h1, tfs: dict, arms: tuple, log=print) -> tuple[dict, dict]:
    """The frozen engine's trades for each (timeframe, arm), produced as production produces them: one feature
    computation per timeframe, engine.run per engine mode (quantum/pipeline.py), backtest.simulate for the engine arms
    and the H-arms' own simulate on the treatment run (quantum/report.py)."""
    cfg = config.DEFAULT
    trades, timing = {}, {}
    for tf, sec in tfs.items():
        t0 = time.time()
        m = b10.make_market(bases[tf], h1, tf, sec)
        F = compute_features(m, cfg)
        runs = {mode: engine.run(m, cfg, mode, F) for mode in ("treatment", "control", "challenger") if mode in arms}
        res = runs.get("treatment") or engine.run(m, cfg, "treatment", F)
        for arm in arms:
            if arm in ("treatment", "control", "challenger"):
                trades[(tf, arm)] = backtest.simulate(runs[arm], cfg)
            elif arm == "h2":
                trades[(tf, arm)], _ = arm_h2.simulate(res, cfg)
            elif arm == "h3":
                trades[(tf, arm)], _ = arm_h3.simulate(res, m, cfg)
            elif arm == "h4":
                trades[(tf, arm)], _ = arm_h4.simulate(res, cfg)
            elif arm == "h5":
                trades[(tf, arm)], _ = arm_h5.simulate(res, cfg, sec)
            else:
                raise ValueError(arm)
        timing[tf] = round(time.time() - t0, 1)
        log(f"[G6] {tf}: " + ", ".join(f"{a} {len(trades[(tf, a)])}" for a in arms) + f" trades, {timing[tf]} s")
        del runs, res, F, m
    return trades, timing


def run_dev(rd: str, trials: str | None = None, log=print, family: str = "primary") -> dict:
    m15 = H.partition(history.load(rd, "XAU/USD", "15min"), "development")
    h1 = H.partition(history.load(rd, "XAU/USD", "1h"), "development")
    m5 = H.partition(history.load(rd, "XAU/USD", "5min"), "development")
    bases = {"5m": m5, "15m": m15, "30m": sources.resample_ohlc(m15, "30min"), "1h": h1,
             "4h": sources.resample_ny_session(h1, 4)}
    tfs, arms = FAMILIES[family]
    trades, timing = dev_trades(bases, h1, tfs, arms, log)
    ix5 = pd.DatetimeIndex(m5.index).tz_convert("UTC").as_unit("s").asi8.astype(np.int64)
    start = int(ix5[0])                                       # the common window: the 5-minute coverage
    grid = ix5 + 300                                          # every 5-minute bar close
    pos, skipped = positions(trades, start)
    rng = H.seeded_rng(SEED)
    res = study(pos, grid, rng, with_policies=True)
    hashes = {"5m": H.data_hash(m5), "15m": H.data_hash(m15), "1h": H.data_hash(h1)}
    if trials:
        for c in res["comparisons"]:
            H.log_trial(trials, {"reg": REG, **({"family": family} if family != "primary" else {}), "part": "development",
                                 "a": c["a"], "b": c["b"], "data_hash_5m": hashes["5m"],
                                 "data_hash_15m": hashes["15m"], "data_hash_1h": hashes["1h"],
                                 **{f"{m}_diff": c[m]["diff"] for m in MEASURES}, **{f"{m}_p": c[m]["p_two_sided"] for m in MEASURES},
                                 **{f"{m}_p_holm": c[m]["p_holm"] for m in MEASURES}})
    return {"registration": REG, "family": family, "arms": list(arms), "timeframes": list(tfs),
            "partition": "development", "data_hashes": hashes, "seed": SEED,
            "window_utc": [datetime.fromtimestamp(start, timezone.utc).isoformat(), str(m5.index[-1])],
            "common_window_note": "every timeframe is measured from the first development 5-minute bar (2020-03-16) so that all "
                                  "four timeframes and the 5-minute sampling grid cover the same span; earlier 15m / 1h fills "
                                  "are counted under 'skipped'",
            "skipped": skipped, "engine_seconds": timing, "utc": datetime.now(timezone.utc).isoformat(), **res,
            "decision": "NONE: shadow research only (registration 'decision'); no limit is enforced or proposed for production"}


def out_of_scope(ledger: str) -> dict:
    """Amendment A1 'out_of_scope_listed': what the ledger holds that is not a position with a fill, an exit and a net
    R, counted and listed (not modelled)."""
    streams = Counter()
    for path in sorted(glob.glob(os.path.join(ledger, "notifications", "*.jsonl"))):
        with open(path) as f:
            for line in f:
                try:
                    streams[str(json.loads(line).get("stream") or "unknown")] += 1
                except ValueError:
                    streams["unreadable line"] += 1
    research = {}
    for path in sorted(glob.glob(os.path.join(ledger, "research_forward", "*.json*"))):
        name = os.path.basename(path)
        with open(path) as f:
            if name.endswith(".jsonl"):
                research[name] = sum(1 for _ in f)
                continue
            d = json.load(f)
        lists = {k: len(v) for k, v in d.items() if isinstance(v, list)} if isinstance(d, dict) else {"rows": len(d)}
        research[name] = lists
    return {"reason": "not positions with a fill, an exit and a net R: information messages, or shadow research records "
                      "whose outcome is a race label; counted here, not modelled as positions",
            "notification_attempts_by_stream": dict(sorted(streams.items())), "research_forward_records": research}


def grid5(store_dir: str) -> np.ndarray:
    """Bar-open times (epoch s) of the stored XAU/USD 5-minute bars as the engine keeps them: off-grid rows and
    bars printed while gold is shut dropped (sources.drop_offgrid, sources.trading_week_only). Only the times are
    used here; the reopen repair changes prices, not which bars exist."""
    df = store.load(store_dir, "XAU/USD_5m")
    if df is None or not len(df):
        return np.array([], np.int64)
    ix = pd.DatetimeIndex(sources.trading_week_only(sources.drop_offgrid(df)).index)
    ix = ix.tz_localize("UTC") if ix.tz is None else ix.tz_convert("UTC")
    return ix.as_unit("s").asi8.astype(np.int64)


def run_forward(ledger: str, store_dir: str, log=print, family: str = "primary") -> dict:
    trades, src = {}, {}
    tfs, arms = FAMILIES[family]
    for tf in tfs:
        for arm in arms:
            path = os.path.join(ledger, "holdout", f"{tf}_{arm}.json")
            if not os.path.exists(path):
                src[f"{tf}_{arm}"] = {"records": None, "current_freeze": 0, "note": "no ledger file"}
                continue
            with open(path) as f:
                rows = json.load(f)
            keep = [t for t in rows if str(t.get("freeze_key", "")).startswith(CURRENT_FREEZE)]
            trades[(tf, arm)] = keep
            src[f"{tf}_{arm}"] = {"records": len(rows), "current_freeze": len(keep)}
    pos, skipped = positions(trades)
    t5 = grid5(store_dir)
    lo, hi = (min(p["fill"] for p in pos), max(p["end"] for p in pos)) if pos else (0, 0)
    grid = t5[(t5 + 300 >= lo) & (t5 + 300 <= hi)] + 300
    log(f"[G6] forward: {len(pos)} positions, {len(grid)} 5-minute samples")
    res = study(pos, grid, None, with_policies=False)
    extra = {"out_of_scope": out_of_scope(ledger)} if family == "a1" else {}
    return {"registration": REG, "family": family, "arms": list(arms), "timeframes": list(tfs),
            "part": "forward (descriptive only; no policy replayed or compared)", "freeze_key": CURRENT_FREEZE, **extra,
            "ledgers": src, "skipped": skipped, "utc": datetime.now(timezone.utc).isoformat(),
            "window_utc": [datetime.fromtimestamp(lo, timezone.utc).isoformat(), datetime.fromtimestamp(hi, timezone.utc).isoformat()]
            if pos else None, **res}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dev")
    d.add_argument("--rd", required=True)
    d.add_argument("--out", required=True)
    d.add_argument("--trials")
    d.add_argument("--family", choices=list(FAMILIES), default="primary")
    f = sub.add_parser("forward")
    f.add_argument("--ledger", required=True)
    f.add_argument("--store", required=True)
    f.add_argument("--out", required=True)
    f.add_argument("--family", choices=list(FAMILIES), default="primary")
    a = ap.parse_args(argv)
    out = run_dev(a.rd, a.trials, family=a.family) if a.cmd == "dev" else run_forward(a.ledger, a.store, family=a.family)
    with open(a.out, "w") as fh:
        json.dump(out, fh, indent=1, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
