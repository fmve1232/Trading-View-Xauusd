"""Phase B21 (research/registrations/B21.json, approved 2026-11-07; written after the registration was committed).

The site's four liquidity / breakout alert types (GRAB and BREAK as B10, SWEEP and BREAKOUT as B16), one per idea and
with no session filter, measured three ways: at the alert (unconfirmed), and after B19's F0 confirmation (a 15m CLOSE
$15 / $20 beyond the alert in its own direction before -$13 or an opposite structure break). For each: +$15 / +$20
before -$13 from the entry (B19's exit rules), and the operator's literal measure, +$15 / +$20 reached at any time in
the next trading day ignoring the stop. Random entries (N1) and random triggers through the same pipeline (N2) are the
baselines. Research code: never imported by production.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .. import config, engine, notify, ta
from ..data import sources
from ..features import compute as compute_features
from . import b10, b13, b16, b19
from . import harness as H

REG = "B21"
KINDS = ("GRAB", "BREAK", "SWEEP", "BREAKOUT")
CONFS = ("none", "X15F0", "X20F0")
T_ALL = (15.0, 20.0)
NODAY = 1e9                                         # "at any time": a stop that is never reached


def to_triggers(ii, dd, idx: pd.DatetimeIndex, c: np.ndarray, kind: str) -> list[dict]:
    return [{"tf": "15m", "kind": kind, "i": int(i), "t_close": int(idx[i].timestamp()) + 900, "dir": int(d), "p0": float(c[i]),
             "regime": "", "bull": math.nan, "bear": math.nan, "sl_eng": None, "tp1_eng": None} for i, d in zip(ii, dd)]


def reached_any(m15: pd.DataFrame, t_close: np.ndarray, px: np.ndarray, d: np.ndarray, T: float) -> np.ndarray:
    """+T (scaled) reached in direction d at any time in the next 96 15m bars, ignoring any stop; NaN when the window
    is incomplete."""
    r = b13.race(m15, np.asarray(t_close, np.int64), np.asarray(px, float), np.asarray(d, int), T, NODAY, nbars=b13.PATH_BARS)
    return np.where(r["ok"], r["win"].astype(float), np.nan)


def alerts(m15: pd.DataFrame, h1: pd.DataFrame, score_from: pd.Timestamp, log=print) -> tuple[dict, b19.Path15]:
    cfg = config.DEFAULT
    m = b10.make_market(m15, h1, "15m", 900)
    F = compute_features(m, cfg)
    res = engine.run(m, cfg, "treatment", F)                        # as B10 (GRAB / BREAK) and B19 (structure)
    F2 = dict(F)
    F2["v"] = np.ones(len(np.asarray(F["v"])))                      # as B16 (time-at-price profile, no stored volume)
    R2 = engine.run(m, cfg, "treatment", F2).rows
    idx = pd.DatetimeIndex(F["index"])
    c = np.asarray(F["c"], float)
    scored = idx >= score_from
    out = {}
    for kind in ("GRAB", "BREAK"):
        ii, dd = b10.liquidity_events(res, F, kind, None)
        keep = scored[ii] if len(ii) else np.zeros(0, bool)
        out[kind] = to_triggers(ii[keep], dd[keep], idx, c, kind)
    t = ta.epoch_s(idx).astype(np.int64).tolist()
    h, lo_, cc = b16._none(F["h"]), b16._none(F["l"]), b16._none(F["c"])
    lv = notify.setup_levels(t, h, lo_, b16._chart(h1), b16._chart(sources.resample_ny_session(h1, 4)))
    for k in ("pdh", "pdl", "pwh", "pwl"):
        lv[k.upper()] = b16._none(R2[k])
    z = {k: b16._none(R2[k]) for k in b16.ZKEYS}
    ev = notify.setup_events(t, h, lo_, cc, lv, z, np.flatnonzero(scored).tolist(), {}, scale=True)
    for kind in ("SWEEP", "BREAKOUT"):
        es = [e for e in ev if e["kind"] == kind]
        out[kind] = to_triggers([e["i"] for e in es], [e["dir"] for e in es], idx, c, kind)
    up, dn = b19.struct_arrays(res, len(m15))
    P = b19.make_path(m15, up, dn)
    for kind in KINDS:
        n0 = len(out[kind])
        out[kind] = b19.dedupe(out[kind])
        log(f"[B21] {kind}: {n0} alerts, {len(out[kind])} after the REPEAT rule")
    return out, P


def measure(m15: pd.DataFrame, P: b19.Path15, A: dict, conf: str, T: float) -> dict:
    C = b19.confirm(P, A, conf)
    T_ = b19.plan_and_exit(P, A, C, conf, "E1", "S13", T)
    sm = b19.summarize(A, C, T_)
    ex = T_["execute"]
    k = np.where(C["k"] >= 0, C["k"], A["j0"] - 1)
    t_entry_close = P.t[k] + 900
    px = np.where(conf == "none", A["p0"], P.c[k])
    any_ = reached_any(m15, t_entry_close[ex], px[ex], A["d"][ex], T)
    sm["reached_any_time"] = float(np.nanmean(any_)) if np.isfinite(any_).any() else None
    sm["reached_any_time_n"] = int(np.isfinite(any_).sum())
    o = np.argsort(T_["t_entry"][ex], kind="stable")
    return {"summary": sm, "net": T_["net"][ex][o]}


def run(rd: str, part: str = "development", only: list[str] | None = None, log=print) -> dict:
    if part == "development":
        m15, h1 = b13.load(rd, part)
        score_from = b13.SCORE_FROM
    else:
        m15 = H.partition(b13.history.load(rd, "XAU/USD", "15min"), part, REG)
        h1 = H.partition(b13.history.load(rd, "XAU/USD", "1h"), part, REG)
        score_from = m15.index[0] + pd.Timedelta(days=67)
    trig, P = alerts(m15, h1, score_from, log)
    t_from = int(score_from.timestamp())
    rows = np.flatnonzero(P.t >= t_from)[::8]
    rows = rows[(rows >= b19.SSTR_LOOKBACK) & (rows + 1 + b19.WIN + b19.HOLD + b19.LIMIT_BARS < len(P.t))]
    n2 = [{"tf": "15m", "kind": "N2", "i": int(i), "t_close": int(P.t[i]) + 900, "dir": s, "p0": float(P.c[i]), "regime": "",
           "bull": math.nan, "bear": math.nan, "sl_eng": None, "tp1_eng": None} for i in rows for s in (1, -1)]
    fams = {k: b19.attach(v, P) for k, v in trig.items()}
    fams["N2"] = b19.attach(n2, P)
    srows = np.flatnonzero(m15.index >= score_from)[::3]
    c = m15["close"].to_numpy(float)
    out = {"registration": REG, "part": part, "window": [str(m15.index[0]), str(m15.index[-1])], "scored_from": str(score_from),
           "alerts": {k: len(v["d"]) for k, v in fams.items()}, "random": {}, "results": {}, "primary": {}}
    for T in T_ALL:
        first = b13.random_rates(m15, m15.index, c, srows, T, b13.S_STOP)
        tc = ta.epoch_s(m15.index).astype(np.int64)[srows] + 900          # "at any time": reached / all complete windows
        anyt = {nm: float(np.nanmean(reached_any(m15, tc, c[srows], np.full(len(srows), sg), T))) for nm, sg in (("long", 1), ("short", -1))}
        out["random"][f"T{T:g}"] = {"first_long": first["long"], "first_short": first["short"],
                                    "any_time_long": anyt["long"], "any_time_short": anyt["short"]}
    nets = {}
    for fam, A in fams.items():
        for conf in CONFS:
            for T in T_ALL:
                key = f"{fam} {conf} T{T:g}"
                if only is not None and fam != "N2" and key not in only:
                    continue
                r = measure(m15, P, A, conf, T)
                out["results"][key] = r["summary"]
                nets[key] = r["net"]
                log(f"[B21] {key}: trades {r['summary']['trades']} TP first {r['summary']['tp_first']} "
                    f"any time {r['summary']['reached_any_time']}")
    ps = {}
    for h, (kind, conf) in enumerate([(k, cf) for k in KINDS for cf in ("X15F0", "X20F0")], start=1):
        key = f"{kind} {conf} T15"
        if key not in out["results"]:
            continue
        sm = out["results"][key]
        p_t = H.t_pvalue(sm["t"], sm["trades"]) if sm["trades"] > 2 and sm["t"] is not None and math.isfinite(sm["t"]) else math.nan
        ps[f"H{h}"] = p_t if math.isfinite(p_t) else 1.0
        out["primary"][f"H{h}"] = {"alert": kind, "confirmation": conf, "trades": sm["trades"], "mean_net": sm["mean_net_usd_per_oz"],
                                   "t": sm["t"], "p_t": p_t, "profit_factor": sm["profit_factor"],
                                   "p_vs_n2": b19.welch_p(nets[key], nets[f"N2 {conf} T15"]),
                                   "n2_mean_net": float(np.mean(nets[f"N2 {conf} T15"])) if len(nets[f"N2 {conf} T15"]) else None}
    hol = b19.holm_adjusted(ps)
    for h, v in out["primary"].items():
        v["p_holm"] = hol.get(h)
        pw = v["p_vs_n2"]
        v["verdict"] = ("INSUFFICIENT" if v["trades"] < 50 else
                        "PASS" if (v["p_holm"] <= 0.05 and pw is not None and math.isfinite(pw) and pw <= 0.05
                                   and (v["profit_factor"] or 0) >= 1.1) else "FAIL")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True)
    ap.add_argument("--part", default="development", choices=("development", "validation"))
    ap.add_argument("--only", help="validation: comma-separated result keys of the hypotheses that passed development")
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials")
    a = ap.parse_args(argv)
    only = [x.strip() for x in a.only.split(",")] if a.only else None
    if a.part == "validation" and not only:
        raise SystemExit("validation opens only for hypotheses that passed development (--only)")
    out = run(a.rd, a.part, only)
    out["utc"] = datetime.now(timezone.utc).isoformat()
    with open(a.out, "w") as f:
        json.dump(b13._clean(out), f, indent=1, allow_nan=False)
    if a.trials:
        for k, sm in out["results"].items():
            if not k.startswith("N2"):
                H.log_trial(a.trials, {"phase": REG, "partition": a.part, "id": f"B21 {k}", **b13._clean(sm)})
        for h, v in out["primary"].items():
            H.log_trial(a.trials, {"phase": REG, "partition": a.part, "id": f"B21 {h} {v['alert']} {v['confirmation']} T15",
                                   "primary": h, **b13._clean(v)})
    print(json.dumps({h: (v["trades"], v["verdict"]) for h, v in out["primary"].items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
