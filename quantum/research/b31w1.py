"""Phase B31b-W1 (research/registrations/B31b-W1.json, approved 2026-11-15; written after the registration was committed).

Modules A (sweep reversal) and B (continuation after a liquidity grab) of B31 on the 2020-25 history, with the engine's
structure rules made volume-neutral. The frozen engine runs unchanged on a copy of its features in which v = 1 and
vol_sma20 = 0 on every bar, so its three volume conditions (quantum/engine.py strong_vol, vol_ok, vol_ok13) are always met
and every other structural clause is its own. Eligibility is on the +10 / +15 / +20 ladder (net R:R >= 1 on the mean target).

Step 1 counts how often the detector and the A / B sequence fire on development: counts only, no outcome is returned.
Step 2 measures outcomes on every partition and runs only if development has at least 30 executed A + B trades.
Research code: never imported by production.
"""
from __future__ import annotations

import argparse
import json
import math

import numpy as np
import pandas as pd

from .. import config, engine
from ..features import compute as compute_features
from . import b10, b13, b19, b31, history
from . import harness as H

REG = "B31b-W1"
LADDER = sum(b31.TP) / 3.0                 # 15: the mean target of the thirds plan (the eligibility reward)
UNITS = ("A", "B", "AB")
SECONDARY = ("E",)
GATE = 30                                  # executed A + B trades on development before step 2 may run
MIN_OOS = 30
SEALED = ("validation", "holdout")
STRUCT = ("BOS", "MSS", "CHoCH")


# ---------------- the volume-neutral detector ----------------
def neutral_features(F: dict) -> dict:
    """A copy of the engine's features in which every volume condition is met (v = 1, vol_sma20 = 0). Nothing else
    changes, and the original dict is not modified."""
    G = dict(F)
    G["v"] = np.ones_like(np.asarray(F["v"], float))
    G["vol_sma20"] = np.zeros_like(np.asarray(F["vol_sma20"], float))
    return G


def engine_15m(m15: pd.DataFrame, h1: pd.DataFrame, neutral: bool = True):
    """(engine result, features) on 15m bars; the result is volume-neutral when `neutral`, the features are the engine's."""
    m = b10.make_market(m15, h1, "15m", 900)
    F = compute_features(m, config.DEFAULT)
    return engine.run(m, config.DEFAULT, "treatment", neutral_features(F) if neutral else F), F


def event_rates(res, n: int) -> dict:
    """Structure events per 1,000 bars, by type and in total."""
    cnt = {k: 0 for k in STRUCT}
    for e in res.events:
        if e["type"] in cnt:
            cnt[e["type"]] += 1
    tot = sum(cnt.values())
    return {"bars": n, "events": tot, "per_1000": round(1000.0 * tot / n, 2) if n else math.nan,
            **{k: {"n": v, "per_1000": round(1000.0 * v / n, 2) if n else math.nan} for k, v in cnt.items()}}


def load_part(rd: str, part: str):
    """B31's partition loader under this registration's seal."""
    if part == "recent":
        m15, h1 = history.load(rd, "XAU/USD", "15min"), history.load(rd, "XAU/USD", "1h")
        lo = H.HOLD[1]
        m15, h1 = m15[m15.index >= lo], h1[h1.index >= lo]
        return m15, h1, lo + pd.Timedelta(days=59)
    m15 = H.partition(history.load(rd, "XAU/USD", "15min"), part, REG if part in SEALED else None)
    h1 = H.partition(history.load(rd, "XAU/USD", "1h"), part, REG if part in SEALED else None)
    start = b13.SCORE_FROM if part == "development" else m15.index[0] + pd.Timedelta(days=67)
    return m15, h1, start


def context(m15: pd.DataFrame, h1: pd.DataFrame, score_from):
    res, F = engine_15m(m15, h1, True)
    X = b31.make_ctx(m15, h1, res, F)
    t_from = int(score_from.timestamp())
    return res, X, t_from, int(np.searchsorted(X.t, t_from))


# ---------------- step 1: firing rates, counts only ----------------
def sweep_funnel(X, evs: list[dict], t_from: int) -> dict:
    """Rejected sweeps scored from t_from, and how many are followed within 8 bars by a structure event in the trade's
    direction (any; MSS / CHoCH only)."""
    n = len(X.c)
    f = {"rejected_sweeps": 0, "any_structure_within_8": 0, "shift_within_8": 0}
    for ev in evs:
        if ev["status"] != "REJECTED" or X.t[ev["j"]] + 900 < t_from:
            continue
        d, end = ev["dir"], min(ev["j"] + b31.SHIFT_BARS, n - 1)
        rng = range(ev["k"], end + 1)
        f["rejected_sweeps"] += 1
        f["any_structure_within_8"] += any((X.up_any[m] if d == 1 else X.dn_any[m]) for m in rng)
        f["shift_within_8"] += any((X.up_shift[m] if d == 1 else X.dn_shift[m]) for m in rng)
    return f


def step1(rd: str, log=print) -> dict:
    """Development only. Returns counts: the modules' `stat` dictionaries, never their trades or outcomes."""
    m15, h1, score_from = load_part(rd, "development")
    as_is, _ = engine_15m(m15, h1, False)
    res, X, t_from, _ = context(m15, h1, score_from)
    evs = b31.crossings(X, b31.SELL_SIDE + b31.BUY_SIDE)
    out = {"registration": REG, "step": 1, "partition": "development", "bars_15m": len(m15), "scored_from": str(score_from),
           "data_hash_15m": H.data_hash(m15), "structure_as_is": event_rates(as_is, len(m15)),
           "structure_volume_neutral": event_rates(res, len(m15)), "funnel": sweep_funnel(X, evs, t_from), "modules": {}}
    for mod in UNITS[:2] + SECONDARY:
        out["modules"][mod] = b31.run_module(X, b31.setups(X, mod, evs), t_from, "model", LADDER)["stat"]
    out["executed_A_plus_B"] = out["modules"]["A"]["executed"] + out["modules"]["B"]["executed"]
    out["gate"] = {"needs": GATE, "passed": out["executed_A_plus_B"] >= GATE}
    log(f"[B31b-W1] step 1: structure {out['structure_as_is']['per_1000']} -> {out['structure_volume_neutral']['per_1000']} per 1,000 bars; "
        f"executed A {out['modules']['A']['executed']} + B {out['modules']['B']['executed']}; gate {'PASSED' if out['gate']['passed'] else 'NOT PASSED'}")
    return out


# ---------------- step 2: outcomes ----------------
def pool_ab(a: list[dict], b: list[dict]) -> list[dict]:
    """A and B in time order, one position at a time, an identical (bar, direction) once (B31's COMBINED rule)."""
    out, busy, seen = [], -1, set()
    for x in sorted([dict(t, mod="A") for t in a] + [dict(t, mod="B") for t in b], key=lambda y: (y["bar"], y["mod"])):
        if (x["bar"], x["dir"]) in seen or x["bar"] <= busy:
            continue
        seen.add((x["bar"], x["dir"]))
        out.append(x)
        busy = x["exit_bar"]
    return out


def ladder(tr: list[dict]) -> dict:
    """The primary money measure: the mean ladder net R (thirds plan) with its day-clustered bootstrap interval."""
    if not tr:
        return {"n": 0}
    r = np.array([x["r_thirds"] for x in tr])
    return {"n": len(tr), "ladder_r": float(r.mean()), "ladder_boot95": b31.boot_ci(r, np.array([x["t"] // 86400 for x in tr])),
            "ladder_usd": float(r.mean() * 650.0)}


def run(rd: str, part: str, trials: str | None = None, log=print) -> dict:
    m15, h1, score_from = load_part(rd, part)
    res, X, t_from, lo_bar = context(m15, h1, score_from)
    evs = b31.crossings(X, b31.SELL_SIDE + b31.BUY_SIDE)
    out = {"meta": {"part": part, "bars_15m": len(m15), "first": str(m15.index[0]), "last": str(m15.index[-1]),
                    "scored_from": str(score_from), "data_hash_15m": H.data_hash(m15), "data_hash_1h": H.data_hash(h1),
                    "structure_volume_neutral": event_rates(res, len(m15)), "funnel": sweep_funnel(X, evs, t_from)},
           "results": {}, "trades": {}}
    for cost_kind in ("model", "operator"):
        tr = {}
        for mod in UNITS[:2] + SECONDARY:
            R = b31.run_module(X, b31.setups(X, mod, evs), t_from, cost_kind, LADDER)
            tr[mod] = R["trades"]
            rnd = b31.matched_random(X, R["trades"], lo_bar, cost_kind) if cost_kind == "model" else None
            out["results"][f"{mod}|{cost_kind}"] = {**b31.summarize(R["trades"], R["stat"], rnd), **ladder(R["trades"])}
        ab = pool_ab(tr["A"], tr["B"])
        tr["AB"] = ab
        rnd = b31.matched_random(X, ab, lo_bar, cost_kind) if cost_kind == "model" else None
        out["results"][f"AB|{cost_kind}"] = {**b31.summarize(ab, {"setups": len(ab)}, rnd), **ladder(ab)}
        if cost_kind == "model":
            out["trades"] = tr
        if trials:
            for u in UNITS + SECONDARY:
                H.log_trial(trials, {"reg": REG, "part": part, "key": f"{u}|{cost_kind}", "n": len(tr[u]),
                                     "ladder_r": out["results"][f"{u}|{cost_kind}"].get("ladder_r", math.nan)})
    log(f"[B31b-W1] {part}: " + ", ".join(f"{u} {out['results'][u + '|model']['n']}" for u in UNITS + SECONDARY))
    return out


def decide(parts: dict) -> dict:
    """The registered rule per unit (validation + holdout pooled; Holm over the 3 units)."""
    rows, ps = {}, {}
    for u in UNITS:
        tr = [x for p in SEALED for x in parts[p]["trades"].get(u, [])]
        n = len(tr)
        rnd = [parts[p]["results"][f"{u}|model"].get("rnd") or {} for p in SEALED]
        n0 = sum(x.get("n", 0) for x in rnd)
        p0 = sum(x.get("tp1_rate", 0) * x.get("n", 0) for x in rnd if x.get("n")) / n0 if n0 else math.nan
        row = {"n_oos": n, "dev_ladder_r": parts["development"]["results"].get(f"{u}|model", {}).get("ladder_r", math.nan),
               "rnd_tp1_rate_oos": p0}
        if n:
            hit = np.array([x["out"] == "TP" for x in tr])
            row.update(ladder(tr), tp1_rate_oos=float(hit.mean()), wilson95_oos=list(H.wilson(int(hit.sum()), n)),
                       tp2_rate_oos=float(np.mean([x["tp2"] == "TP" for x in tr])),
                       tp3_rate_oos=float(np.mean([x["tp3"] == "TP" for x in tr])))
            pp = (hit.sum() + p0 * n0) / (n + n0) if n0 else math.nan
            if n0 and 0 < pp < 1:
                ps[u] = float(1 - H._norm_cdf((hit.mean() - p0) / math.sqrt(pp * (1 - pp) * (1 / n + 1 / n0))))
        rows[u] = row
    adj = b19.holm_adjusted(dict(ps)) if ps else {}
    for u, row in rows.items():
        row["holm_p"] = adj.get(u, math.nan)
        if row["n_oos"] < MIN_OOS:
            row["verdict"] = "INSUFFICIENT"
        else:
            ok = row["ladder_r"] > 0 and row["ladder_boot95"][0] > 0 and row["holm_p"] < 0.05 and row["dev_ladder_r"] > 0
            row["verdict"] = "SUPPORTED" if ok else "NOT SUPPORTED"
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True)
    ap.add_argument("--step", type=int, choices=(1, 2), required=True)
    ap.add_argument("--step1", help="step 2: the committed step-1 JSON (its gate must have passed)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials")
    a = ap.parse_args(argv)
    if a.step == 1:
        res = step1(a.rd)
    else:
        with open(a.step1) as f:
            if not json.load(f)["gate"]["passed"]:
                print("[B31b-W1] step 1's gate did not pass: step 2 is not run (DETECTOR INSUFFICIENT)")
                return 2
        parts = {p: run(a.rd, p, a.trials) for p in ("development", "validation", "holdout", "recent")}
        res = {"registration": REG, "step": 2, "parts": parts, "decision": decide(parts)}
    with open(a.out, "w") as f:
        json.dump(res, f, indent=1, default=lambda v: None if isinstance(v, float) and v != v else str(v))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
