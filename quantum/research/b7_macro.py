"""Phase B7: MACRO direction (US dollar, yields, real yields, VIX, oil, breakevens, COT positioning) for the
operator's $650 / $650 trade. DEVELOPMENT data only. Approved by the operator 2026-11-03 ("merge, approve B7 and B8");
declared and committed before any macro data was fetched.

Runs on GitHub Actions (.github/workflows/research-macro.yml): every source is free and needs no key, but this
session's network cannot reach them. Only aggregate results are written.

    python -m quantum.research.b7_macro --rd <research-data checkout> --out <results.json> --trials <trials.jsonl>

QUESTION. The literature finds gold moving against the dollar and real yields and with risk aversion (VIX), oil and
inflation expectations, mostly at the same time. Does yesterday's macro move tell which way gold goes first today:
+$13 before -$13 (the operator's $650 / $650 at 0.5 lot) or +$10 before -$10, distances scaled to $4,000?
DATA (free; the site's own fetchers in quantum/data/sources.py)
    Yahoo daily closes  dxy = DX-Y.NYB (US dollar index), tnx = ^TNX (10-year yield), vix = ^VIX, oil = CL=F (WTI)
    FRED daily          real = DFII10 (10-year TIPS real yield), be = T10YIE (10-year breakeven inflation)
    CFTC COT            COMEX gold, non-commercial net position / open interest, keyed by its Friday 15:30 NY release
NO LOOK-AHEAD. Entry at the close of the 07:45 UTC spot bar (08:00 UTC, the London open) on day D.
    Yahoo: the last close dated before D.  FRED: the last observation dated at least 2 business days before D (FRED
    publishes the next business day).  COT: the last report released before 08:00 UTC on D.
RULES (gold's direction on day D; dK = change over K observations)
    USD1  -sign(dxy d1)     USD5  -sign(dxy d5)     NOM1  -sign(tnx d1)
    REAL1 -sign(real d1)    REAL5 -sign(real d5)    VIX1  +sign(vix d1)
    OIL5  +sign(oil d5)     BE5   +sign(be d5)
    A rule fires only when |dK| >= the median |dK| of the previous 252 observations (small moves are noise).
    COMBO       USD1 and REAL1 both fire and agree
    COT_CONTRA  net position z-score over the previous 156 reports > +1 -> SELL, < -1 -> BUY (crowded positions)
    COT_FLOW    sign of the latest weekly change of the net position (follow the speculators)
  11 rules x 2 targets = 22 trials, under B2's five-part rule.
BASELINE: every day's 08:00 UTC entry, long and short, matched to each trial's long / short mix.
Paths, fills, costs and one-position: B2's. Also reported (descriptive): the mean signed move from 08:00 to 20:00 UTC.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

import numpy as np
import pandas as pd

from .. import ta
from ..data import sources
from . import b2, history
from . import harness as H

TARGETS = {"T13": (13.0, 13.0), "T10": (10.0, 10.0)}
YAHOO = {"dxy": "DX-Y.NYB", "tnx": "^TNX", "vix": "^VIX", "oil": "CL=F"}
FRED = {"real": "DFII10", "be": "T10YIE"}
RULES = (("USD1", "dxy", 1, -1), ("USD5", "dxy", 5, -1), ("NOM1", "tnx", 1, -1), ("REAL1", "real", 1, -1),
         ("REAL5", "real", 5, -1), ("VIX1", "vix", 1, 1), ("OIL5", "oil", 5, 1), ("BE5", "be", 5, 1))
MED_OBS, FRED_LAG_BD, COT_Z_N, COT_Z = 252, 2, 156, 1.0
ENTRY_OPEN_UTC = "07:45"          # the 15-minute bar that closes at 08:00 UTC
DRIFT_OPEN_UTC = "19:45"          # ... and the one that closes at 20:00 UTC
FETCH_ERRORS = (sources.FetchError, OSError, ValueError, KeyError, IndexError)


# ---------------- directions, known before the entry ----------------
def _usable_pos(idx: pd.DatetimeIndex, cut: pd.Timestamp, strict: bool) -> int:
    return int(idx.searchsorted(cut, side="left" if strict else "right")) - 1


def series_direction(s: pd.Series, days: pd.DatetimeIndex, k: int, sign: int, fred_lag: bool) -> np.ndarray:
    """+1 / -1 / 0 per entry day from a daily series: sign * sign(change over k observations), only when the change is
    at least the median absolute change of the previous MED_OBS observations. Uses observations known before entry."""
    s = s.dropna().sort_index()
    dk = s.diff(k)
    thr = dk.abs().shift(1).rolling(MED_OBS, min_periods=MED_OBS // 2).median()
    out = np.zeros(len(days))
    for n, d in enumerate(days):
        cut = d - pd.offsets.BDay(FRED_LAG_BD) if fred_lag else d
        pos = _usable_pos(s.index, cut, strict=not fred_lag)
        if pos < k or not np.isfinite(dk.iloc[pos]) or not np.isfinite(thr.iloc[pos]):
            continue
        if abs(dk.iloc[pos]) >= thr.iloc[pos] and dk.iloc[pos] != 0:
            out[n] = sign * np.sign(dk.iloc[pos])
    return out


def cot_directions(cot: pd.DataFrame, t_entry: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    """(COT_CONTRA, COT_FLOW) per entry instant, from reports released strictly before it."""
    c = cot.sort_index()
    net = (c["nc_long"] - c["nc_short"]) / c["open_interest"]
    mu = net.shift(1).rolling(COT_Z_N, min_periods=COT_Z_N // 2).mean()
    sd = net.shift(1).rolling(COT_Z_N, min_periods=COT_Z_N // 2).std()
    z = (net - mu) / sd
    flow = np.sign(net.diff())
    contra, fl = np.zeros(len(t_entry)), np.zeros(len(t_entry))
    for n, t in enumerate(t_entry):
        pos = _usable_pos(c.index, t, strict=True)
        if pos < 1:
            continue
        zz = z.iloc[pos]
        if np.isfinite(zz) and abs(zz) > COT_Z:
            contra[n] = -np.sign(zz)
        if np.isfinite(flow.iloc[pos]):
            fl[n] = flow.iloc[pos]
    return contra, fl


def directions(yahoo: dict, fred: dict, cot: pd.DataFrame | None, days: pd.DatetimeIndex, t_entry: pd.DatetimeIndex) -> pd.DataFrame:
    out = {}
    for name, key, k, sign in RULES:
        s = yahoo.get(key) if key in YAHOO else fred.get(key)
        out[name] = series_direction(s, days, k, sign, fred_lag=key in FRED) if s is not None and len(s) else np.zeros(len(days))
    out["COMBO"] = np.where((out["USD1"] != 0) & (out["USD1"] == out["REAL1"]), out["USD1"], 0.0)
    if cot is not None and len(cot):
        out["COT_CONTRA"], out["COT_FLOW"] = cot_directions(cot, t_entry)
    else:
        out["COT_CONTRA"] = out["COT_FLOW"] = np.zeros(len(days))
    return pd.DataFrame(out, index=days)


# ---------------- the study ----------------
def study(m15: pd.DataFrame, yahoo: dict, fred: dict, cot: pd.DataFrame | None) -> dict:
    P = b2.Paths(m15)
    idx = m15.index
    t_close = ta.epoch_s(idx) + 900
    c = m15["close"].to_numpy(float)
    cost_bar = H.cost_pts(idx)
    hhmm = idx.strftime("%H:%M")
    ent = np.flatnonzero(hhmm == ENTRY_OPEN_UTC)
    days = idx[ent].normalize()
    t_entry = idx[ent] + pd.Timedelta(minutes=15)
    dirs = directions(yahoo, fred, cot, days, t_entry)
    drift_pos = pd.Series(np.flatnonzero(hhmm == DRIFT_OPEN_UTC), index=idx[hhmm == DRIFT_OPEN_UTC].normalize())
    j_all, ok_all = P.locate(t_close[ent])
    res = {"set": "B7", "partition": "development", "from": str(H.DEV[0]), "to": str(H.DEV[1]), "data_hash": H.data_hash(m15),
           "entry_days": len(ent), "coverage": {k: int((dirs[k] != 0).sum()) for k in dirs}, "baseline": {}, "trials": []}
    sc_all = c[ent] / b2.REF_PRICE
    for dname, dv in (("long", 1.0), ("short", -1.0)):
        ev = P.evaluate(j_all[ok_all], c[ent][ok_all], np.full(int(ok_all.sum()), dv), [(a * sc_all[ok_all], b * sc_all[ok_all]) for a, b in TARGETS.values()])
        for tn, e in zip(TARGETS, ev):
            res["baseline"][f"{tn} {dname}"] = float(np.mean(e["out"] == 1))
    names, pv, daily = [], [], {}
    for rule in dirs.columns:
        d_all = dirs[rule].to_numpy()
        sel = (d_all != 0) & ok_all
        i, d, j = ent[sel], d_all[sel], j_all[sel]
        sc = c[i] / b2.REF_PRICE
        drift = [((c[drift_pos[dy]] - c[ii]) * dd / s_) if dy in drift_pos.index else np.nan
                 for ii, dd, s_, dy in zip(i, d, sc, idx[i].normalize())]
        evs = P.evaluate(j, c[i], d, [(a * sc, b * sc) for a, b in TARGETS.values()]) if len(i) else []
        for q, (tn, (a, b)) in enumerate(TARGETS.items()):
            tid = f"daily {rule} 08UTC {tn}"
            rec = {"id": tid, "rule": rule, "target": tn, "signal_days": len(i),
                   "drift_08_20_usd_at_4000": float(np.nanmean(drift)) if len(i) else None}
            if len(i):
                e = evs[q]
                keep = b2.one_position(t_close[i], P.t[np.minimum(e["exit"], len(P.t) - 1)] + b2.PATH_SEC)
                st = b2._stats(e["out"][keep], e["pnl"][keep], cost_bar[i][keep] * sc[keep], a * sc[keep], b * sc[keep], d[keep])
                rnd = (st["long"] * res["baseline"][f"{tn} long"] + st["short"] * res["baseline"][f"{tn} short"]) / st["n"]
                z = (st["win_rate"] - rnd) / math.sqrt(max(rnd * (1 - rnd), 1e-12) / st["n"])
                rec.update({k_: st.get(k_) for k_ in ("n", "long", "short", "wins", "losses", "open", "win_rate", "wilson", "break_even", "net_r", "t")})
                rec.update({"random_same_mix": rnd, "z_vs_random": z, "usd_per_trade_0p5lot": st["net_r"] * b * 50,
                            "pass": {"1_wilson_lb_above_break_even": bool(st["wilson"][0] > st["break_even"]),
                                     "2_t_above_3": bool((st["t"] if st["t"] is not None and math.isfinite(st["t"]) else 0) > 3 and st["net_r"] > 0),
                                     "3_beats_random_by_2se": bool(z > 2)}})
                net_r = (e["pnl"][keep] - cost_bar[i][keep] * sc[keep]) / (b * sc[keep])
                daily[tid] = pd.Series(net_r, index=pd.to_datetime(t_close[i][keep], unit="s", utc=True).normalize()).groupby(level=0).sum()
                names.append(tid)
                pv.append(H.t_pvalue(st["t"], st["n"]) if st["t"] is not None and math.isfinite(st["t"]) else 1.0)
            else:
                rec["n"] = 0
            res["trials"].append(rec)
    bh = H.benjamini_hochberg(pv, 0.10) if names else []
    Dd = pd.DataFrame({k: daily[k] for k in names}).fillna(0.0).sort_index() if names else pd.DataFrame()
    rc = H.reality_check(Dd[names].to_numpy(), B=1000, mean_block=10.0) if len(Dd) > 20 else {"p_value": 1.0, "best": 0}
    tmap = {t["id"]: t for t in res["trials"]}
    for x, okb in zip(names, bh):
        tmap[x]["pass"]["4_bh_fdr10"] = bool(okb)
        tmap[x]["pass"]["5_reality_check_p_below_0p05"] = bool(rc["p_value"] < 0.05)
        tmap[x]["passes_all"] = all(tmap[x]["pass"].values())
    res["family"] = {"trials": len(names), "reality_check_p": rc["p_value"], "best_id": names[rc["best"]] if names else None,
                     "bh_fdr10_passed": [x for x, okb in zip(names, bh) if okb],
                     "passes_all": [x for x in names if tmap[x].get("passes_all")]}
    return res


def fetch() -> tuple[dict, dict, pd.DataFrame | None, dict]:
    """Free sources, fetched on GitHub Actions. Failures are recorded, never invented."""
    y, f, status = {}, {}, {}
    for k, sym in YAHOO.items():
        try:
            y[k] = sources.yahoo(sym, "1d", "10y")["close"]
            status[k] = f"yahoo {sym}: {len(y[k])} days {y[k].index[0]:%Y-%m-%d} -> {y[k].index[-1]:%Y-%m-%d}"
        except FETCH_ERRORS as exc:  # recorded in the results; the rule then has no signals
            status[k] = f"yahoo {sym}: FAILED {type(exc).__name__}: {exc}"
    for k, sid in FRED.items():
        try:
            f[k] = sources.fred(sid)
            status[k] = f"fred {sid}: {len(f[k])} obs {f[k].index[0]:%Y-%m-%d} -> {f[k].index[-1]:%Y-%m-%d}"
        except FETCH_ERRORS as exc:  # recorded in the results; the rule then has no signals
            status[k] = f"fred {sid}: FAILED {type(exc).__name__}: {exc}"
    cot = None
    try:
        cot = sources.cftc_gold_cot()
        status["cot"] = f"cftc gold: {len(cot)} reports {cot.index[0]:%Y-%m-%d} -> {cot.index[-1]:%Y-%m-%d}"
    except FETCH_ERRORS as exc:  # recorded in the results; the COT rules then have no signals
        status["cot"] = f"cftc: FAILED {type(exc).__name__}: {exc}"
    return y, f, cot, status


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True, help="research-data checkout (spot XAU/USD 15min)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials", required=True)
    a = ap.parse_args(argv)
    if os.path.exists(a.trials):
        with open(a.trials) as fh:
            if any('"phase": "B7"' in line for line in fh):
                raise SystemExit(f"B7 already has records in {a.trials}; it is run once")
    m15 = H.partition(history.load(a.rd, "XAU/USD", "15min"), "development")
    y, f, cot, status = fetch()
    for v in status.values():
        print(v, flush=True)
    res = study(m15, y, f, cot)
    res["sources"] = status
    for t in res["trials"]:
        H.log_trial(a.trials, {"phase": "B7", "partition": "development", "data_hash": res["data_hash"], **t})
    with open(a.out, "w") as fh:
        json.dump(res, fh, indent=1, default=float)
    for t in res["trials"]:
        if t.get("n"):
            print(f"{t['id']:26s} n {t['n']:4d}  TP first {t['win_rate']:.1%} [{t['wilson'][0]:.0%}, {t['wilson'][1]:.0%}]  "
                  f"random {t['random_same_mix']:.1%}  z {t['z_vs_random']:+.2f}  net {t['net_r']:+.3f}R  drift {t['drift_08_20_usd_at_4000']:+.2f}")
        else:
            print(f"{t['id']:26s} n    0")
    print("family:", json.dumps(res["family"], default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
