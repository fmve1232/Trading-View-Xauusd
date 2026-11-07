"""Phase B23 (research/registrations/B23.json, approved 2026-11-07; written after the registration was committed).

B22's exploratory raw-tail lead, frozen: the uncalibrated ensemble (mean of B22's LR, RF, HGB, XGB, LGBM probabilities)
on B22's features, trained on development only (first 80% fit, last 20% set the top-0.5% threshold), applied once to
the validation partition; the holdout only after a validation pass, with the same models (retrained deterministically
on the same development rows with the same seeds) and the same threshold. Research code: never imported by production.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import b13, b22, history
from . import harness as H

REG = "B23"
FRACS = (0.005, 0.001, 0.01)                         # primary first
T_ALL = (15.0, 20.0)
ENS_MODELS = ("LR", "RF", "HGB", "XGB", "LGBM")


def load_continuous(rd: str, part: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    d15, d1 = b13.load(rd, "development")
    parts15, parts1 = [d15], [d1]
    names = ["validation"] if part == "validation" else ["validation", "holdout"]
    for nm in names:
        parts15.append(H.partition(history.load(rd, "XAU/USD", "15min"), nm, REG))
        parts1.append(H.partition(history.load(rd, "XAU/USD", "1h"), nm, REG))
    m15 = pd.concat(parts15).sort_index()
    h1 = pd.concat(parts1).sort_index()
    m15, h1 = m15[~m15.index.duplicated()], h1[~h1.index.duplicated()]
    start, end = (H.VAL if part == "validation" else H.HOLD)
    return m15, h1, start, end


def thresholds(p_cal: np.ndarray) -> dict:
    return {f: float(np.quantile(p_cal, 1 - f)) for f in FRACS}


def run(rd: str, part: str, log=print) -> dict:
    m15, h1, start, end = load_continuous(rd, part)
    df, aux = b22.base_features(m15, h1, log)
    cost = aux["cost"]
    idx = df.index
    t_close = df["t_close"].to_numpy(np.int64)
    first_val = int(np.searchsorted(idx, H.VAL[0]))
    tr_bars = np.flatnonzero((idx >= b13.SCORE_FROM) & (idx < H.VAL[0]))
    tr_bars = tr_bars[tr_bars + b22.NBARS < first_val]
    te_bars = np.flatnonzero((idx >= start) & (idx < end))
    hm = b22.hmm_features(h1, int(H.VAL[0].timestamp()), t_close)        # fitted on 1h bars closed before validation
    out = {"registration": REG, "part": part, "train": [str(idx[tr_bars[0]]), str(idx[tr_bars[-1]])],
           "test": [str(idx[te_bars[0]]), str(idx[te_bars[-1]])], "results": {}}
    for T in T_ALL:
        def lab(bars):
            rb = b13.race(m15, t_close[bars], df["close"].to_numpy(float)[bars], np.ones(len(bars), int), T, b22.S, nbars=b22.NBARS)
            rs = b13.race(m15, t_close[bars], df["close"].to_numpy(float)[bars], -np.ones(len(bars), int), T, b22.S, nbars=b22.NBARS)
            return np.concatenate([rb["win"], rs["win"]]).astype(int), np.concatenate([rb["win"] | rb["loss"], rs["win"] | rs["loss"]])
        ytr_all, ktr = lab(tr_bars)
        yte_all, kte = lab(te_bars)
        Xtr, _, _ = b22.rows_for(df, hm, tr_bars)
        Xte, Dte, _ = b22.rows_for(df, hm, te_bars)
        Xtr, ytr = np.nan_to_num(Xtr[ktr], nan=0.0, posinf=0.0, neginf=0.0), ytr_all[ktr]
        Xte, yte, Dte = np.nan_to_num(Xte[kte], nan=0.0, posinf=0.0, neginf=0.0), yte_all[kte], Dte[kte]
        half = int(ktr[: len(tr_bars)].sum())
        ib, is_ = np.arange(half), np.arange(half, len(ytr))
        fit_i = np.concatenate([ib[: int(len(ib) * 0.8)], is_[: int(len(is_) * 0.8)]])
        cal_i = np.concatenate([ib[int(len(ib) * 0.8):], is_[int(len(is_) * 0.8):]])
        p_cal, p_te = [], []
        for mn in ENS_MODELS:
            mdl = b22.make(mn).fit(Xtr[fit_i], ytr[fit_i])
            p_cal.append(mdl.predict_proba(Xtr[cal_i])[:, 1])
            p_te.append(mdl.predict_proba(Xte)[:, 1])
            log(f"[B23] T{T:g} {mn} fitted on {len(fit_i)} development rows")
        pc, pt = np.mean(p_cal, axis=0), np.mean(p_te, axis=0)
        thr = thresholds(pc)
        days = df["day"].to_numpy()[te_bars]
        day = np.concatenate([days, days])[kte]
        cc = cost[te_bars]
        cst = np.concatenate([cc, cc])[kte]
        net_all = np.where(yte == 1, T, -b22.S) - cst
        be = float(np.mean((b22.S + cst) / (b22.S + T)))
        res = {"test_rows": len(yte), "base_rate": float(yte.mean()), "break_even": be, "thresholds": thr, "tops": {}}
        for f in FRACS:
            sel = pt >= thr[f]
            m_, lo, hi = b22.clustered_ci(yte[sel].astype(float), day[sel])
            res["tops"][f"{f:g}"] = {"n": int(sel.sum()), "days": len(np.unique(day[sel])), "success": m_, "ci95": [lo, hi],
                                     "net_usd_per_oz": float(net_all[sel].mean()) if sel.any() else None,
                                     "buy_n": int((sel & (Dte > 0)).sum()), "buy_success": float(yte[sel & (Dte > 0)].mean()) if (sel & (Dte > 0)).any() else None,
                                     "sell_n": int((sel & (Dte < 0)).sum()), "sell_success": float(yte[sel & (Dte < 0)].mean()) if (sel & (Dte < 0)).any() else None}
        out["results"][f"T{T:g}"] = res
        log(f"[B23] T{T:g}: top 0.5% {res['tops']['0.005']}")
    p = out["results"]["T15"]["tops"]["0.005"]
    lo = p["ci95"][0]
    out["pass"] = bool(p["n"] >= 2 and lo is not None and math.isfinite(lo) and lo > out["results"]["T15"]["break_even"]
                       and (p["net_usd_per_oz"] or -1) > 0)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True)
    ap.add_argument("--part", required=True, choices=("validation", "holdout"))
    ap.add_argument("--val-results", help="holdout only: the committed validation results (must show pass)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials")
    a = ap.parse_args(argv)
    if a.part == "holdout":
        ok = False
        if a.val_results:
            with open(a.val_results) as f:
                ok = bool(json.load(f).get("pass"))
        if not ok:
            raise SystemExit("the holdout opens only after a validation pass (registration B23)")
    out = run(a.rd, a.part)
    out["utc"] = datetime.now(timezone.utc).isoformat()
    with open(a.out, "w") as f:
        json.dump(b13._clean(out), f, indent=1, allow_nan=False)
    if a.trials:
        for tk, res in out["results"].items():
            for f_, v in res["tops"].items():
                H.log_trial(a.trials, {"phase": REG, "partition": a.part, "id": f"B23 ENS raw top {f_} {tk}",
                                       **({"primary": "B23", "verdict": "PASS" if out["pass"] else "FAIL"} if (tk == "T15" and f_ == "0.005") else {}),
                                       **b13._clean(v)})
    print(json.dumps({"pass": out["pass"], "T15 top 0.5%": out["results"]["T15"]["tops"]["0.005"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
