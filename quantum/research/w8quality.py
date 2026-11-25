"""B31b-W8 (research only; production never imports this module): quality-selected M15 / M30 breakout entries at the
operator's measured execution cost. research/registrations/B31b-W8.json fixes every rule before this code; this file
implements it.

  events     the production breakout detector (quantum/breakouts.py) through B31b-W7's study code (w7breakout.events)
  quality    a logistic model of "the breakout does not close back inside its level within the 16-bar watch" on the W7
             baseline (stop distance at the breakout close, cost, ATR, session) plus the W7 candle group, walk-forward
             (6 folds by time, purged). Every event in folds 2..6 gets an out-of-fold score; it is SELECTED when that
             score is at or above the 80th percentile of the in-sample scores of the fold's TRAINING events (computed
             from training rows only). One model is fitted for both timeframes, as W7's outcome-A model was.
  entries    E0 (market at the breakout close) and E1 (market at the confirmation close), W7's stops, targets, sizing and
             ENTRY READY checks, unchanged; B31b-W3's execution (M5-refined races, 24 h time stop).
  cost       the operator's measured round-trip cost per oz by session, from a committed cost amendment (cost file);
             the W3 cost model only as the registered fallback after 2026-12-03, labelled; sensitivity on the same
             trades: the W3 model, x1.5, x2.
  tests      4 candidates {E0, E1} x {M15, M30}: the paired +$10-first rate vs R1 (20 random entries in the same watch),
             Holm over 4; mean net R > 0 with its day-clustered lower bound > 0; >= 100 decided trades; and the selected
             trades beat the same entry on the NON-selected breakouts (R3), one-sided bootstrap p < 0.05.

Development partition only: main() refuses any other. Validation is opened only by a later amendment, for a
candidate, with the operator's explicit approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .. import breakouts as B
from . import harness as H
from . import w3liq as W
from . import w7breakout as X

REG = "B31b-W8"
CANDIDATES = (("E0", "M15"), ("E0", "M30"), ("E1", "M15"), ("E1", "M30"))
QUANTILE = 80.0
FOLDS = 6
MIN_DECIDED = 100
FALLBACK_FROM = "2026-12-03"
QCOLS = X.BASE + X.GROUPS["candle"]
SESSIONS = ("ASIA", "LDN_OPEN", "LDN_CONT", "NY_OPEN", "OVERLAP", "NY_CONT", "OFF")


# ---------------- the quality score and the selection ----------------
def quality(Xm: np.ndarray, y: np.ndarray, t: np.ndarray, t_end: np.ndarray, t_lo: int, t_hi: int,
            folds: int = FOLDS, q: float = QUANTILE) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Out-of-fold score, the fold's threshold (the q-th percentile of the TRAINING events' in-sample scores) and the
    selected flag, per event. Fold 1 and any fold without enough training rows: NaN score, not selected."""
    n = len(y)
    score, thr = np.full(n, np.nan), np.full(n, np.nan)
    edges = np.linspace(t_lo, t_hi, folds + 1)
    for f in range(1, folds):
        te = (t >= edges[f]) & (t < edges[f + 1])
        tr = t_end < edges[f]
        if te.sum() == 0 or tr.sum() < 30 or len(np.unique(y[tr])) < 2:
            continue
        Xtr, Xte, _, _ = W.standardize(Xm[tr], Xm[te])
        w = W.logit_fit(Xtr, y[tr])
        score[te] = W.logit_pred(w, Xte)
        thr[te] = float(np.percentile(W.logit_pred(w, Xtr), q))
    sel = np.isfinite(score) & (score >= thr)
    return score, thr, sel


def frozen(Xm: np.ndarray, y: np.ndarray, q: float = QUANTILE) -> dict:
    """The one model for validation: fitted on all development events; threshold = q-th percentile of its in-sample
    scores. Written to the freeze record only if there is a candidate."""
    Xs, _, mu, sd = W.standardize(Xm, Xm[:1])
    w = W.logit_fit(Xs, y)
    return {"cols": list(QCOLS), "w": [float(v) for v in w], "mu": [float(v) for v in mu], "sd": [float(v) for v in sd],
            "threshold": float(np.percentile(W.logit_pred(w, Xs), q))}


def reliability(p: np.ndarray, y: np.ndarray, bins: int = 10) -> list[dict]:
    """Calibration table of the out-of-fold score (deciles): mean predicted vs observed rate."""
    ok = np.isfinite(p)
    p, y = p[ok], y[ok]
    if len(p) < bins:
        return []
    edges = np.percentile(p, np.linspace(0, 100, bins + 1))
    out = []
    for b in range(bins):
        m = (p >= edges[b]) & ((p <= edges[b + 1]) if b == bins - 1 else (p < edges[b + 1]))
        if m.any():
            out.append({"bin": b + 1, "n": int(m.sum()), "mean_score": float(p[m].mean()), "observed": float(y[m].mean())})
    return out


# ---------------- cost ----------------
def load_cost(path: str | None, today: str) -> dict:
    """The decision cost: the committed cost file, or the registered fallback (the W3 model) from 2026-12-03 only."""
    if path:
        c = json.load(open(path))
        assert c.get("registration") == REG and c.get("source"), "cost file must name B31b-W8 and its source"
        assert set(c["per_session_usd_oz"]) >= set(SESSIONS), "a round-trip cost for every session is required"
        assert all(float(v) > 0 for v in c["per_session_usd_oz"].values())
        return c
    if today < FALLBACK_FROM:
        raise SystemExit(f"{REG}: no measured cost yet; the W3 cost model is the registered fallback only from {FALLBACK_FROM}")
    return {"registration": REG, "source": "FALLBACK: the B31b-W3 cost model (no measured broker cost by 2026-12-03)",
            "per_session_usd_oz": None}


def apply_cost(P, cost: dict) -> np.ndarray:
    """Replace the path's per-bar cost by the decision cost (by session); returns the W3 model cost it replaced."""
    model = np.asarray(P.cost, float).copy()
    if cost.get("per_session_usd_oz"):
        P.cost = np.array([float(cost["per_session_usd_oz"][str(s)]) for s in P.sess], float)
    return model


def recost(r: dict, c_new: float, key: str = "tp10_r") -> float:
    """The same trade's net R at another round-trip cost: the gross move is g = R x (D + c) + c."""
    g = r[key] * (r["D"] + r["cost"]) + r["cost"]
    return (g - c_new) / (r["D"] + c_new)


# ---------------- statistics ----------------
def boot_two(x1: np.ndarray, d1: np.ndarray, x0: np.ndarray, d0: np.ndarray, B_: int = W.BOOT) -> tuple[float, list[float]]:
    """One-sided p of mean(x1) - mean(x0) <= 0, each group resampled by its own days (day-clustered), and the 95% CI."""
    if len(x1) < 3 or len(x0) < 3:
        return math.nan, [math.nan, math.nan]
    g = H.seeded_rng(X.SEED + 8)

    def draws(x, d):
        u, inv = np.unique(d, return_inverse=True)
        s, n = np.bincount(inv, weights=x), np.bincount(inv)
        pick = g.integers(0, len(u), size=(B_, len(u)))
        return s[pick].sum(axis=1) / n[pick].sum(axis=1)
    diff = draws(x1, d1) - draws(x0, d0)
    return float((diff <= 0).mean()), [float(np.percentile(diff, 2.5)), float(np.percentile(diff, 97.5))]


def candidate(s: dict, holm_p, r3_p) -> bool:
    lb = (s.get("tp10_mean_net_r_boot95_day") or [math.nan])[0]
    mr = (s.get("tp10") or {}).get("mean_net_r", math.nan)
    return bool(holm_p is not None and holm_p < 0.05 and np.isfinite(mr) and mr > 0 and np.isfinite(lb) and lb > 0
                and s.get("n", 0) >= MIN_DECIDED and r3_p is not None and np.isfinite(r3_p) and r3_p < 0.05)


# ---------------- a run ----------------
def build(m15: pd.DataFrame, h1: pd.DataFrame, m5: pd.DataFrame | None, score_from: int, cost: dict) -> dict:
    P, F15, F30, incomplete = W.frames(m15, h1, m5)
    model_cost = apply_cost(P, cost)
    Fs = {"M15": F15, "M30": F30}
    evs = {tf: X.events(F, score_from) for tf, F in Fs.items()}
    allev = evs["M15"] + evs["M30"]
    feat = {}
    for tf, F in Fs.items():
        other = evs["M30" if tf == "M15" else "M15"]
        for e in evs[tf]:
            feat[e["id"]] = X.features(P, F, e, other)
    A = sorted([e for e in allev if e["st"]["failed"] is not None or e["st"]["closed"] is not None], key=lambda e: e["t_close"])
    y = np.array([float(e["st"]["failed"] is None) for e in A])
    t = np.array([e["t_close"] for e in A], np.int64)
    t_end = np.array([e["t_close"] + B.WATCH * Fs[e["tf"]].sec for e in A], np.int64)
    Xm = W.matrix([feat[e["id"]] for e in A], QCOLS)
    t_hi = int(P.t[-1]) + 900
    score, thr, sel = quality(Xm, y, t, t_end, score_from, t_hi)
    qual = {e["id"]: {"score": float(score[k]) if np.isfinite(score[k]) else None, "selected": bool(sel[k]),
                      "scored": bool(np.isfinite(score[k]))} for k, e in enumerate(A)}
    rows = []
    for tf, F in Fs.items():
        for ev in evs[tf]:
            qv = qual.get(ev["id"])
            if not qv or not qv["scored"]:
                continue                                    # fold 1 / an unfinished watch: no out-of-fold score
            for od in X.orders_for(P, F, ev):
                if od["m"] not in ("E0", "E1"):
                    continue
                r = W.execute(P, F, od)
                r.update(tf=tf, ev_id=ev["id"], sess=ev["sess"], ref_kind=ev["ref_kind"], selected=qv["selected"])
                if r["status"] == "FILLED":
                    r["checks"] = X.checks(r, ev)
                    r["ready"] = bool(r.get("eligible")) and not r["checks"]
                    kd = min(max(W.k_at(P, int(r["t_dec"])) - 1, 0), len(P.c) - 1)
                    r["model_cost"] = float(model_cost[kd])
                rows.append(r)
    return {"P": P, "F": Fs, "events": evs, "rows": rows, "score": score, "y": y, "sel": sel, "frozen": frozen(Xm, y),
            "score_from": score_from, "t_end": t_hi, "incomplete_m30": incomplete, "cost": cost}


def analyse(res: dict) -> dict:
    P, Fs, rows = res["P"], res["F"], res["rows"]
    by_id = {e["id"]: e for tf in Fs for e in res["events"][tf]}
    sel_rows = [r for r in rows if r.get("selected")]
    non_rows = [r for r in rows if not r.get("selected")]
    us = {(m, tf): X.counted(sel_rows, m, tf) for m, tf in CANDIDATES}
    r3 = {(m, tf): X.counted(non_rows, m, tf) for m, tf in CANDIDATES}
    ctl = X.controls(P, Fs, [r for u in us.values() for r in u if W.decided(r)], by_id)
    sc, y = res["score"], res["y"]
    ok = np.isfinite(sc)
    out = {"quality": {"events_scored": int(ok.sum()), "selected": int(res["sel"].sum()), "base_rate_oof": float(y[ok].mean()),
                       "auc_oof": W.auc(sc[ok], y[ok]), "reliability_oof": reliability(sc, y),
                       "note": "the out-of-fold score of 'the breakout holds'; NOT a validated probability"},
           "candidates": {}, "funnel": {}}
    ps = {}
    for (m, tf), u in us.items():
        key = f"{m}:{tf}"
        out["funnel"][key] = {"selected": X.funnel(sel_rows, m, tf), "not_selected": X.funnel(non_rows, m, tf)}
        s = X.variant_summary(u, ctl)
        dec = [r for r in u if W.decided(r)]
        d0 = [r for r in r3[(m, tf)] if W.decided(r)]
        x1 = np.array([float(r["tp10"] == "TP") for r in dec])
        x0 = np.array([float(r["tp10"] == "TP") for r in d0])
        p3, ci3 = boot_two(x1, np.array([r["t_fill"] // 86400 for r in dec]), x0, np.array([r["t_fill"] // 86400 for r in d0]))
        s["vs_R3_not_selected"] = {"n_not_selected": len(d0), "rate_not_selected": float(x0.mean()) if len(x0) else math.nan,
                                   "rate_selected": float(x1.mean()) if len(x1) else math.nan, "diff_boot95": ci3, "p_one_sided": p3}
        sens = {}
        for name, f in (("w3_model", lambda r: r["model_cost"]), ("x1.5", lambda r: 1.5 * r["cost"]), ("x2", lambda r: 2.0 * r["cost"])):
            v = [recost(r, f(r)) for r in dec if np.isfinite(r.get("tp10_r", math.nan))]
            sens[name] = float(np.mean(v)) if v else math.nan
        s["cost_sensitivity_mean_net_r_tp10"] = sens
        for T in W.TP:
            k = f"tp{int(T)}"
            if dec:
                s[k]["break_even_rate"] = float(np.mean([(r["D"] + r["cost"]) / (T + r["D"]) for r in dec]))
        out["candidates"][key] = s
        ps[key] = (s.get("vs_R1_tp10_rate") or {}).get("p_one_sided")
    hp = holm(ps)
    out["verdict"] = {k: {"n": s.get("n", 0), "holm_p": hp.get(k), "mean_net_r": (s.get("tp10") or {}).get("mean_net_r"),
                          "mean_net_r_lb95": (s.get("tp10_mean_net_r_boot95_day") or [None])[0],
                          "r3_p": s["vs_R3_not_selected"]["p_one_sided"],
                          "candidate": candidate(s, hp.get(k), s["vs_R3_not_selected"]["p_one_sided"])}
                      for k, s in out["candidates"].items()}
    out["overall"] = ("CANDIDATE(S): " + ", ".join(k for k, v in out["verdict"].items() if v["candidate"])
                      if any(v["candidate"] for v in out["verdict"].values()) else "NO CANDIDATE")
    out["cost"] = {k: v for k, v in res["cost"].items()}
    out["events_total"] = {tf: len(v) for tf, v in res["events"].items()}
    out["incomplete_m30_bars"] = res["incomplete_m30"]
    if out["overall"] != "NO CANDIDATE":
        out["frozen_model"] = res["frozen"]
    return out


def holm(ps: dict) -> dict:
    items = sorted((p, k) for k, p in ps.items() if p is not None and np.isfinite(p))
    m, out, run = len(items), {}, 0.0
    for r, (p, k) in enumerate(items):
        run = max(run, min(1.0, (m - r) * p))
        out[k] = run
    return out


def code_sha() -> str:
    return hashlib.sha256(open(__file__, "rb").read()).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", default="development")
    ap.add_argument("--rd", required=True, help="research-data clone (development)")
    ap.add_argument("--cost", help="the committed cost file (research/registrations/B31b-W8-cost.json)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--csv")
    ap.add_argument("--today", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    a = ap.parse_args(argv)
    if a.part != "development":
        raise H.SealedPartition(f"{REG}: only the development partition is registered; validation needs an amendment and "
                                "the operator's explicit approval")
    cost = load_cost(a.cost, a.today)
    m15, h1, m5, score_from = W.load(a.rd, "development", None)
    res = build(m15, h1, m5, score_from, cost)
    out = analyse(res)
    out.update(registration=REG, part=a.part, code_sha256=code_sha(), data_hash=H.data_hash(m15),
               breakouts_sha256=hashlib.sha256(open(B.__file__, "rb").read()).hexdigest())
    with open(a.out, "w") as fh:
        json.dump(X._clean(out), fh, indent=1)
    if a.csv:
        cols = X.TRADE_COLS + ("selected", "model_cost")
        pd.DataFrame([{k: (",".join(r[k]) if isinstance(r.get(k), list) else r.get(k)) for k in cols} for r in res["rows"]]).to_csv(
            a.csv, index=False)
    print(json.dumps({"overall": out["overall"], "events": out["events_total"], "cost_source": cost["source"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
