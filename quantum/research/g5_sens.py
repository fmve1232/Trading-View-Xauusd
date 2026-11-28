"""G5-SENS (research/registrations/G5-SENS.json + amendment A1): one-at-a-time parameter sensitivity of the frozen
engine's treatment arm and arm H4 on the DEVELOPMENT partition only. RESEARCH ONLY: never imported by production; it
calls the production engine, backtest.simulate and arm_h4.simulate unchanged, on a copy of the configuration
(dataclasses.replace) and, for H4, with module constants patched inside this process only and restored after.

A diagnostic of fragility, not a search: no cell is selected, recommended or adopted.

  python -m quantum.research.g5_sens --rd <research-data checkout> --out research/G5_SENS_RESULTS.json
                                     [--trials research/trials.jsonl] [--feasibility]
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .. import arm_h4, backtest, config, engine
from ..data import sources
from ..features import compute as compute_features
from . import b10, history
from . import harness as H

REG = "G5-SENS"
TFS = {"15m": 900, "30m": 1800, "1h": 3600}
ENGINE = {"atr_len": [10, 14, 20], "swing_pivot_len": [3, 5, 8], "internal_pivot_len": [1, 2, 3],
          "struct_window": [5, 8, 12], "tq_min_score": [45, 55, 65], "cal_gate_min_p": [0.45, 0.50, 0.55],
          "eq_atr_mult": [0.15, 0.25, 0.35], "liq_prox_mult": [1.0, 1.5, 2.0]}
H4 = {"GAP_ATR": [0.05, 0.1, 0.2], "MERGE_ATR": [0.025, 0.05, 0.1], "MIN_TP_R": [0.75, 1.0, 1.5], "FALLBACK_R": [1.5, 2.0, 3.0]}
COST = [0.5, 1.0, 1.5, 2.0]
TARGETS = (10.0, 15.0, 20.0)
HORIZON = 7 * 86400
SEED = 20261128
NY = ZoneInfo("America/New_York")


# ---------------- the cell plan, exactly as registered ----------------
def plan() -> list[dict]:
    """Every cell: (tf, arm, group, parameter, value). The frozen cell is listed once per arm and timeframe."""
    cells = []
    for tf in TFS:
        for arm in ("treatment", "h4"):
            cells.append({"tf": tf, "arm": arm, "group": "frozen", "param": None, "value": None})
            for p, vals in ENGINE.items():
                cells += [{"tf": tf, "arm": arm, "group": "engine", "param": p, "value": v} for v in vals if v != vals[1]]
            if arm == "h4":
                for p, vals in H4.items():
                    cells += [{"tf": tf, "arm": arm, "group": "h4", "param": p, "value": v} for v in vals if v != vals[1]]
            cells += [{"tf": tf, "arm": arm, "group": "cost", "param": "cost_mult", "value": m} for m in COST if m != 1.0]
    return cells


def cfg_for(cell: dict):
    if cell["group"] == "engine":
        return dataclasses.replace(config.DEFAULT, **{cell["param"]: cell["value"]})
    if cell["group"] == "cost":
        m = cell["value"]
        d = config.DEFAULT
        return dataclasses.replace(d, spread_cost=d.spread_cost * m, slippage_pts=d.slippage_pts * m, commission_l=d.commission_l * m)
    return config.DEFAULT


@contextmanager
def h4_constants(patch: dict):
    old = {k: getattr(arm_h4, k) for k in patch}
    try:
        for k, v in patch.items():
            setattr(arm_h4, k, v)
        yield
    finally:
        for k, v in old.items():
            setattr(arm_h4, k, v)


# ---------------- measurement ----------------
def session_day(t: int) -> str:
    return (datetime.fromtimestamp(t, NY) + timedelta(hours=7)).date().isoformat()


def ts(iso: str) -> int:
    return int(pd.Timestamp(iso).timestamp())


def races(trades: list[dict], tf_sec: int, P5: dict) -> dict:
    """+$10 / +$15 / +$20 (scaled by P0 / 4000) before the original stop, from the fill, on 5-minute bars; a bar touching
    both is the stop; 7-day horizon. Fills before the 5-minute coverage are excluded and counted."""
    t5, o5, h5, l5 = P5["t"], P5["o"], P5["h"], P5["l"]
    out = {f"usd{int(x)}": {"target": 0, "stop": 0, "undecided": 0} for x in TARGETS}
    excluded = 0
    for t in trades:
        fill = ts(t["entry_time"]) + tf_sec
        if not len(t5) or fill < t5[0]:
            excluded += 1
            continue
        j0 = int(np.searchsorted(t5, fill))
        j1 = int(np.searchsorted(t5, fill + HORIZON))
        lg = t["dir"] == "LONG"
        e, sl = float(t["entry"]), float(t["sl"])
        o, h, l = o5[j0:j1], h5[j0:j1], l5[j0:j1]
        stop = (l <= sl) | (o <= sl) if lg else (h >= sl) | (o >= sl)
        ks = int(np.argmax(stop)) if stop.any() else None
        for x in TARGETS:
            px = e + (x if lg else -x) * e / 4000.0
            hit = (h >= px) | (o >= px) if lg else (l <= px) | (o <= px)
            kt = int(np.argmax(hit)) if hit.any() else None
            key = f"usd{int(x)}"
            if kt is not None and (ks is None or kt < ks):
                out[key]["target"] += 1
            elif ks is not None:
                out[key]["stop"] += 1
            else:
                out[key]["undecided"] += 1
    for v in out.values():
        n = v["target"] + v["stop"]
        v["rate"] = round(v["target"] / n, 4) if n else None
        v["wilson95"] = [round(x, 4) for x in H.wilson(v["target"], n)] if n else None
    out["excluded_before_5m_coverage"] = excluded
    return out


def max_dd(r: np.ndarray) -> float:
    if not len(r):
        return 0.0
    eq = np.concatenate([[0.0], np.cumsum(r)])
    return float(np.max(np.maximum.accumulate(eq) - eq))


def day_boot(r: np.ndarray, days: list[str], rng, sims: int = 2000) -> list[float] | None:
    u = sorted(set(days))
    if len(u) < 2:
        return None
    pos = {d: i for i, d in enumerate(u)}
    sums, cnt = np.zeros(len(u)), np.zeros(len(u))
    for x, d in zip(r, days, strict=True):
        sums[pos[d]] += x
        cnt[pos[d]] += 1
    pick = rng.integers(0, len(u), size=(sims, len(u)))
    m = sums[pick].sum(1) / np.maximum(cnt[pick].sum(1), 1)
    return [round(float(np.quantile(m, 0.025)), 4), round(float(np.quantile(m, 0.975)), 4)]


def metrics(trades: list[dict], tf_sec: int, P5: dict, rng) -> dict:
    trades = sorted([t for t in trades if not t.get("open")], key=lambda t: (t["exit_time"], t["entry_time"]))
    n = len(trades)
    if n == 0:
        return {"n": 0}
    risk = np.array([abs(t["entry"] - t["sl"]) for t in trades], float)
    ok = risk > 0
    tr = [t for t, k in zip(trades, ok, strict=True) if k]
    r = np.array([t["r"] for t in tr], float)
    gross = np.array([t["gross_pts"] for t in tr], float) / risk[ok]
    pts = np.array([t["pts"] for t in tr], float)
    days = [session_day(ts(t["exit_time"])) for t in tr]
    k = int((r > 0).sum())
    sd = float(r.std(ddof=1)) if len(r) > 1 else float("nan")
    tstat = float(r.mean() / (sd / math.sqrt(len(r)))) if len(r) > 1 and sd > 0 else float("nan")
    gl = -pts[pts < 0].sum()
    by = {}
    for field in ("regime", "session"):
        g: dict = {}
        for t, x in zip(tr, r, strict=True):
            g.setdefault(str(t.get(field)), []).append(x)
        by[field] = {kk: {"n": len(v), "mean_net_r": round(float(np.mean(v)), 4)} for kk, v in sorted(g.items())}
    return {
        "n": len(r), "excluded_zero_stop": int((~ok).sum()), "days": len(set(days)),
        "mean_net_r": round(float(r.mean()), 4), "mean_net_r_day_boot95": day_boot(r, days, rng),
        "mean_gross_r": round(float(gross.mean()), 4), "pf": round(float(pts[pts > 0].sum() / gl), 4) if gl > 0 else None,
        "win_rate": round(k / len(r), 4), "win_wilson95": [round(x, 4) for x in H.wilson(k, len(r))],
        "max_dd_r": round(max_dd(r), 4), "t": None if math.isnan(tstat) else round(tstat, 3),
        "p_one_sided": None if math.isnan(tstat) else float(H.t_pvalue(tstat, len(r), one_sided=True)),
        "quartiles_r": [round(float(q), 4) for q in np.quantile(r, [0.25, 0.5, 0.75])],
        "share_at_or_below_minus_1r": round(float(np.mean(r <= -1.0)), 4),
        "avg_win_r": round(float(r[r > 0].mean()), 4) if (r > 0).any() else None,
        "avg_loss_r": round(float(r[r <= 0].mean()), 4) if (r <= 0).any() else None,
        "by": by, "targets": races(tr, tf_sec, P5),
    }


def repriced(trades: list[dict], mult: float) -> dict:
    """Supplementary (A1): the same trades with each modelled cost multiplied (fixed signals)."""
    tr = [t for t in trades if not t.get("open") and abs(t["entry"] - t["sl"]) > 0]
    r = np.array([(t["gross_pts"] - mult * t["cost_pts"]) / abs(t["entry"] - t["sl"]) for t in tr], float)
    return {"mult": mult, "n": len(r), "mean_net_r": round(float(r.mean()), 4) if len(r) else None}


def holm(ps: list[float]) -> list[float]:
    m = len(ps)
    order = np.argsort(ps)
    adj, run = np.empty(m), 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (m - rank) * ps[i]))
        adj[i] = run
    return [round(float(x), 6) for x in adj]


def bh(ps: list[float]) -> list[float]:
    m = len(ps)
    order = np.argsort(ps)[::-1]
    adj, run = np.empty(m), 1.0
    for rank, i in zip(range(m, 0, -1), order, strict=True):
        run = min(run, ps[i] * m / rank)
        adj[i] = run
    return [round(float(x), 6) for x in adj]


# ---------------- fragility summary (stated in the registration) ----------------
def fragility(cells: list[dict]) -> list[dict]:
    """Per arm, timeframe and parameter: sign stability, the frozen value's rank, PEAK / PLATEAU / SLOPE, the largest
    change against the frozen cell and interval overlap. PEAK: the frozen value has the best mean net R and both
    neighbours lie below the frozen cell's 95% interval; PLATEAU: every value's mean lies inside that interval; SLOPE:
    otherwise."""
    out = []
    frozen = {(c["tf"], c["arm"]): c["m"] for c in cells if c["group"] == "frozen"}
    groups: dict = {}
    for c in cells:
        if c["group"] != "frozen":
            groups.setdefault((c["tf"], c["arm"], c["param"]), []).append(c)
    for (tf, arm, p), cs in sorted(groups.items()):
        f = frozen.get((tf, arm), {})
        if not f.get("n"):
            out.append({"tf": tf, "arm": arm, "param": p, "note": "frozen cell has no trades"})
            continue
        vals = sorted([(c["value"], c["m"]) for c in cs] + [(1.0 if p == "cost_mult" else _frozen_value(p), f)], key=lambda x: x[0])
        means = [m.get("mean_net_r") for _, m in vals]
        ci = f.get("mean_net_r_day_boot95")
        fr_i = next(i for i, (_, m) in enumerate(vals) if m is f)
        fm = f["mean_net_r"]
        valid = [x for x in means if x is not None]
        rank = 1 + sum(1 for x in valid if x > fm)
        if ci is None or len(valid) < len(means):
            shape = "INSUFFICIENT"
        elif all(ci[0] <= x <= ci[1] for x in valid):
            shape = "PLATEAU"
        elif rank == 1 and 0 < fr_i < len(vals) - 1 and means[fr_i - 1] < ci[0] and means[fr_i + 1] < ci[0]:
            shape = "PEAK"
        else:
            shape = "SLOPE"
        sign = None if not valid else all((x > 0) == (fm > 0) for x in valid)
        overlap = None if ci is None else all(m.get("mean_net_r_day_boot95") is not None and m["mean_net_r_day_boot95"][1] >= ci[0]
                                             and m["mean_net_r_day_boot95"][0] <= ci[1] for _, m in vals)
        out.append({"tf": tf, "arm": arm, "param": p, "values": [v for v, _ in vals], "mean_net_r": means,
                    "n": [m.get("n") for _, m in vals], "frozen_rank": rank, "shape": shape, "sign_stable": sign,
                    "max_abs_change_mean_net_r": round(max(abs(x - fm) for x in valid), 4) if valid else None,
                    "max_rel_change_n": round(max(abs((m.get("n") or 0) - f["n"]) / f["n"] for _, m in vals), 4),
                    "intervals_overlap_frozen": overlap})
    return out


def _frozen_value(p: str):
    return ENGINE[p][1] if p in ENGINE else H4[p][1]


# ---------------- the run ----------------
def load(rd: str) -> tuple[dict, dict, dict]:
    m15 = H.partition(history.load(rd, "XAU/USD", "15min"), "development")
    h1 = H.partition(history.load(rd, "XAU/USD", "1h"), "development")
    m5 = H.partition(history.load(rd, "XAU/USD", "5min"), "development")
    bases = {"15m": m15, "30m": sources.resample_ohlc(m15, "30min"), "1h": h1}
    ix = pd.DatetimeIndex(m5.index).tz_convert("UTC")
    P5 = {"t": ix.as_unit("s").asi8.astype(np.int64), "o": m5["open"].to_numpy(float), "h": m5["high"].to_numpy(float),
          "l": m5["low"].to_numpy(float)}
    hashes = {"15m": H.data_hash(m15), "1h": H.data_hash(h1), "5m": H.data_hash(m5)}
    return bases, P5, {"h1": h1, "hashes": hashes, "first": str(m15.index[0]), "last": str(m15.index[-1])}


def engine_key(c: dict) -> tuple:
    """Cells that share one engine run: the frozen configuration (frozen and H4-constant cells) or one config change."""
    if c["group"] in ("engine", "cost"):
        return (c["tf"], c["group"], c["param"], c["value"])
    return (c["tf"], "frozen", None, None)


def run(rd: str, trials: str | None = None, feasibility: bool = False, log=print) -> dict:
    bases, P5, meta = load(rd)
    planned = plan()
    cells = [c for c in planned if not feasibility or c["group"] == "frozen"]
    rng = H.seeded_rng(SEED)                       # the harness seed helper (research only)
    timing, results = {}, {}
    keys = list(dict.fromkeys(engine_key(c) for c in cells))            # in plan order, each engine run once
    for key in keys:
        tf = key[0]
        cfg = cfg_for(next(c for c in cells if engine_key(c) == key))
        t0 = time.time()
        m = b10.make_market(bases[tf], meta["h1"], tf, TFS[tf])
        res = engine.run(m, cfg, "treatment", compute_features(m, cfg))
        timing[" ".join(str(x) for x in key)] = round(time.time() - t0, 1)
        log(f"[G5-SENS] engine {key}: {timing[' '.join(str(x) for x in key)]} s")
        for i, c in enumerate(cells):
            if engine_key(c) != key:
                continue
            if c["arm"] == "treatment":
                trades = backtest.simulate(res, cfg)
            else:
                patch = {c["param"]: c["value"]} if c["group"] == "h4" else {}
                with h4_constants(patch):
                    trades, _ = arm_h4.simulate(res, cfg)
            r = {**c, "m": metrics(trades, TFS[tf], P5, rng)}
            if c["group"] == "frozen":
                r["supplementary_cost_repriced"] = [repriced(trades, x) for x in (0.5, 1.5, 2.0)]
            results[i] = r
            if trials:
                H.log_trial(trials, {"reg": REG, "part": "development", "tf": tf, "arm": c["arm"], "group": c["group"],
                                     "param": c["param"], "value": c["value"], "data_hash_15m": meta["hashes"]["15m"],
                                     "data_hash_1h": meta["hashes"]["1h"], "data_hash_5m": meta["hashes"]["5m"],
                                     "n": r["m"].get("n"), "mean_net_r": r["m"].get("mean_net_r"),
                                     "mean_gross_r": r["m"].get("mean_gross_r"), "p_one_sided": r["m"].get("p_one_sided")})
            log(f"[G5-SENS] {tf} {c['arm']} {c['group']} {c['param']}={c['value']}: n {r['m'].get('n')} "
                f"net {r['m'].get('mean_net_r')}")
        del res
    done = [results[i] for i in range(len(cells))]
    ps = [c["m"].get("p_one_sided") for c in done]
    idx = [i for i, p in enumerate(ps) if p is not None]
    ho, bhv = holm([ps[i] for i in idx]), bh([ps[i] for i in idx])
    for j, i in enumerate(idx):
        done[i]["m"]["p_holm"], done[i]["m"]["p_bh"] = ho[j], bhv[j]
    return {"registration": REG, "amendment": "A1", "partition": "development", "window": [meta["first"], meta["last"]],
            "data_hashes": meta["hashes"], "seed": SEED, "cells_planned": len(plan()), "cells_run": len(done),
            "feasibility_only": feasibility, "engine_seconds": timing,
            "utc": datetime.now(timezone.utc).isoformat(), "cells": done,
            "fragility": [] if feasibility else fragility(done),
            "decision": "NONE: diagnostic only (registration 'decision')"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rd", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials")
    ap.add_argument("--feasibility", action="store_true")
    a = ap.parse_args(argv)
    out = run(a.rd, a.trials, a.feasibility)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=1, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
