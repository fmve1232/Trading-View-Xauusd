"""Forward-record diagnosis of the arms, H4 first (operator decision 2026-11-26, next phase items 3-7). READ ONLY.

  PYTHONPATH=. python3 audit/tools/h4_forward_diagnosis.py --ledger <forward-ledger copy> --bars <market-data copy>
      [--arms h4] [--random 2000] [--horizon-days 7] [--pool-days 0] [--seed 20261126] [--json out.json]

Nothing here changes, tunes or proposes a rule. Every counterfactual below is a DIAGNOSIS of the recorded trades: it
explains the record; it is not a candidate, and none may be adopted from this window (CLAUDE.md "Do not tune";
the operator: "Do not modify the frozen H4 strategy merely to improve these numbers").

For every closed trade of the current freeze key (holdout/<tf>_<arm>.json):
  * replica      the exit model of quantum/backtest.simulate (entry at the signal bar's close; gaps at the open; stop
                 first on a tie; half at TP1, stop to entry from the next bar; the rest at TP2), re-implemented here
                 and run WITHOUT the flip on the arm's own bars. On every non-FLIP trade it must reproduce the
                 recorded exit; the agreement rate is reported, so the counterfactual is only as good as it shows.
  * no_flip      the same model from the entry with no flip: what the flipped trades would have done had they been
                 held (to the exit, or marked at the close after the horizon).
  * races        on 5-minute bars from the entry's close: TP1, TP2, +$10, +$15 and +$20 each against the ORIGINAL
                 stop (stop first on a tie; undecided within the horizon = excluded), the time to the target, the
                 favourable excursion before the stop (MFE) and the adverse excursion while the trade was open (MAE).
  * cost         gross versus net R, the cost in R, trades whose cost turned a gross gain into a net loss.
  * random       each trade's twins: every other bar close of the arm's timeframe in the forward window (or the last
                 --pool-days days), in the same UTC hour (+-1 h), with the same direction, stop / TP1 / TP2 distances,
                 cost and follow-up time, raced and managed the same way. --random pseudo-ledgers each draw one twin
                 per trade; p_two_sided is the share at least as far from the null mean as the recorded entries,
                 p_normal the normal tail of the same null (finer than 1 / (K + 1)); a degenerate null gives none.
  * multiplicity Holm and Benjamini-Hochberg over every (arm, timeframe, measure) p-value computed.

Bars: the market-data store's XAU/USD series with the market-shut quotes removed (sources.trading_week_only); 4h
bars are the 1h store resampled to the New York session grid, as the engine does. Twelve Data mid prices; no bid /
ask. A trade whose entry bar is not in the store is counted and skipped.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import forward_report as FR

from quantum.data import sources

TF_SEC = FR.TF_SEC
USD = (10.0, 15.0, 20.0)
MEASURES = ("tp1_first", "tp2_first", "usd10_first", "usd15_first", "usd20_first", "no_flip_r")
MIN_TWINS = 20          # a ledger whose median trade has fewer distinct twins than this is not tested (no real null)


# ---------------- bars ----------------
def bars(d: str, tf: str) -> pd.DataFrame:
    if tf == "4h":
        b = sources.trading_week_only(FR.load_bars(d, FR.SERIES["1h"])).assign(volume=0.0)   # the grid needs the column
        return sources.resample_ny_session(b, 4)[["open", "high", "low", "close"]]
    return sources.trading_week_only(FR.load_bars(d, FR.SERIES[tf]))


def arrays(df: pd.DataFrame) -> dict:
    return {"t": FR.secs(df.index), "o": df["open"].to_numpy(float), "h": df["high"].to_numpy(float),
            "l": df["low"].to_numpy(float), "c": df["close"].to_numpy(float)}


# ---------------- the exit model of backtest.simulate, without the flip ----------------
def manage(B: dict, i0: int, i_end: int, long: bool, entry: float, sl: float, tp1: float, tp2: float, cost: float) -> dict:
    """Manage one position from bar i0 (the bar after the entry) to i_end (exclusive), as backtest.simulate does,
    with no flip. Quiet bars are skipped with a vectorised search; each eventful bar runs the simulate rules."""
    o, h, l, c = B["o"], B["h"], B["l"], B["c"]
    pos = {"sl": sl, "tp1_done": False, "qty": 1.0, "legs": []}
    sgn = 1.0 if long else -1.0
    risk = abs(entry - sl)

    def close(px, i, why):
        legs = pos["legs"] + [(pos["qty"], px)]
        gross = sum(q * (p - entry) * sgn for q, p in legs)
        return {"reason": why, "exit_i": i, "exit": px, "gross": gross, "net": gross - cost,
                "r": (gross - cost) / risk if risk > 0 else 0.0, "tp1_done": pos["tp1_done"]}

    i = i0
    while i < i_end:
        s = slice(i, i_end)
        if long:
            ev = (l[s] <= pos["sl"]) | (o[s] <= pos["sl"]) | (h[s] >= tp2) | (o[s] >= tp2)
            if not pos["tp1_done"]:
                ev |= (h[s] >= tp1) | (o[s] >= tp1)
        else:
            ev = (h[s] >= pos["sl"]) | (o[s] >= pos["sl"]) | (l[s] <= tp2) | (o[s] <= tp2)
            if not pos["tp1_done"]:
                ev |= (l[s] <= tp1) | (o[s] <= tp1)
        if not ev.any():
            break
        k = i + int(np.argmax(ev))
        oi = o[k]
        gap_ok = not math.isnan(oi)

        def beyond(v, oi=oi):
            return oi >= v if long else oi <= v

        def through(v, oi=oi):
            return oi <= v if long else oi >= v

        stop_lbl = "BE" if pos["sl"] == entry and pos["tp1_done"] else "SL"
        if gap_ok and beyond(tp2):                                     # A) targets the bar opened beyond
            if not pos["tp1_done"]:
                pos["legs"].append((0.5, oi))
                pos["qty"] -= 0.5
                pos["tp1_done"] = True
            return close(oi, k, "TP2")
        if gap_ok and not pos["tp1_done"] and beyond(tp1):
            pos["legs"].append((0.5, oi))
            pos["qty"] -= 0.5
            pos["tp1_done"] = True
        if gap_ok and through(pos["sl"]):                              # B) the stop
            return close(oi, k, stop_lbl + "_GAP")
        if (l[k] <= pos["sl"]) if long else (h[k] >= pos["sl"]):
            return close(pos["sl"], k, stop_lbl)
        if not pos["tp1_done"] and ((h[k] >= tp1) if long else (l[k] <= tp1)):
            pos["legs"].append((0.5, tp1))
            pos["qty"] -= 0.5
            pos["tp1_done"] = True
        if (h[k] >= tp2) if long else (l[k] <= tp2):
            return close(tp2, k, "TP2")
        if pos["tp1_done"]:
            pos["sl"] = entry                                         # breakeven, live from the next bar
        i = k + 1
    last = min(i_end, len(c)) - 1
    out = close(c[last], last, "OPEN_AT_HORIZON")
    return out


# ---------------- races on 5-minute bars ----------------
def first(mask: np.ndarray) -> int | None:
    return int(np.argmax(mask)) if mask.any() else None


def races(B5: dict, j0: int, j_end: int, long: bool, entry: float, sl: float, targets: dict) -> dict:
    """Each target against the original stop from 5m bar j0: 'TP' / 'SL' / None, the hours to the target, and the
    favourable excursion before the stop (the stop bar itself excluded: its path inside the bar is unknown)."""
    o, h, l, t = B5["o"][j0:j_end], B5["h"][j0:j_end], B5["l"][j0:j_end], B5["t"][j0:j_end]
    if not len(o):
        return {}
    s_hit = (l <= sl) | (o <= sl) if long else (h >= sl) | (o >= sl)
    ks = first(s_hit)
    out = {}
    t0 = int(B5["t"][j0])
    for name, tp in targets.items():
        t_hit = (h >= tp) | (o >= tp) if long else (l <= tp) | (o <= tp)
        kt = first(t_hit)
        if ks is None and kt is None:
            out[name] = (None, None)
        elif kt is None or (ks is not None and ks <= kt):
            out[name] = ("SL", None)
        else:
            out[name] = ("TP", (int(t[kt]) + 300 - t0) / 3600.0)
    upto = ks if ks is not None else len(o)
    if upto > 0:
        mfe = (np.max(h[:upto]) - entry) if long else (entry - np.min(l[:upto]))
    else:
        mfe = 0.0
    out["mfe_usd"] = float(max(mfe, 0.0))
    out["stopped"] = ks is not None
    return out


# ---------------- statistics ----------------
def perm_p(actual: np.ndarray, rnd: np.ndarray) -> dict:
    """actual: (n,) values (NaN = undecided); rnd: (n, K). Null = pseudo-ledgers, one random entry per trade."""
    ok = ~np.isnan(actual)
    if ok.sum() < 5 or rnd.shape[1] == 0:
        return {"n": int(ok.sum()), "actual": None, "null_mean": None, "p_two_sided": None}
    a = float(np.nanmean(actual))
    with np.errstate(all="ignore"):
        null = np.nanmean(rnd[ok], axis=0)
    null = null[~np.isnan(null)]
    if not len(null):
        return {"n": int(ok.sum()), "actual": round(a, 4), "null_mean": None, "p_two_sided": None}
    mu, sd = float(null.mean()), float(null.std(ddof=1)) if len(null) > 1 else 0.0
    p = (1 + int(np.sum(np.abs(null - mu) >= abs(a - mu) - 1e-12))) / (len(null) + 1)
    # the pseudo-ledger mean is a mean of n draws: close to normal, so its tail gives p-values finer than 1 / (K + 1),
    # which the multiplicity corrections need (the empirical p is kept beside it)
    if sd <= 0:                                               # a degenerate null (too few distinct twins): no test
        return {"n": int(ok.sum()), "actual": round(a, 4), "null_mean": round(mu, 4), "null_sd": 0.0,
                "p_two_sided": None, "p_normal": None, "note": "degenerate null"}
    pn = math.erfc(abs(a - mu) / sd / math.sqrt(2.0))
    return {"n": int(ok.sum()), "actual": round(a, 4), "null_mean": round(mu, 4), "null_sd": round(sd, 4),
            "null_95": [round(float(np.percentile(null, 2.5)), 4), round(float(np.percentile(null, 97.5)), 4)],
            "p_two_sided": round(p, 4), "p_normal": float(f"{pn:.4g}")}


def holm(ps: list[float]) -> list[float]:
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i])
    adj, run = [0.0] * m, 0.0
    for r, i in enumerate(order):
        run = max(run, min(1.0, (m - r) * ps[i]))
        adj[i] = run
    return adj


def bh(ps: list[float]) -> list[float]:
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i], reverse=True)
    adj, run = [0.0] * m, 1.0
    for r, i in enumerate(order):
        run = min(run, ps[i] * m / (m - r))
        adj[i] = run
    return adj


# ---------------- one ledger ----------------
def diagnose(trades: list, tf: str, Btf: dict, B5: dict, pool_lo: int, horizon: int, k_rand: int, rng) -> dict:
    """pool_lo: the earliest bar close a random twin may use (the freeze time by default)."""
    sec = TF_SEC[tf]
    t_tf = Btf["t"]
    pos_of = {int(x): i for i, x in enumerate(t_tf)}
    closes = t_tf + sec
    t_last = int(B5["t"][-1]) + 300
    hours = ((closes // 3600) % 24).astype(int)
    rows, missing = [], 0
    for t in trades:
        i_e = pos_of.get(FR.ts(t["entry_time"]))
        if i_e is None:
            missing += 1
            continue
        long = t["dir"] == "LONG"
        e, sl, tp1, tp2, cost = t["entry"], t["sl"], t["tp1"], t["tp2"], t["cost_pts"]
        d_sl, d1, d2, sgn = abs(e - sl), abs(tp1 - e), abs(tp2 - e), (1 if long else -1)
        t_close = int(t_tf[i_e]) + sec
        i_end = int(np.searchsorted(t_tf, t_close + horizon, side="right"))
        rep = manage(Btf, i_e + 1, i_end, long, e, sl, tp1, tp2, cost)
        j0 = int(np.searchsorted(B5["t"], t_close, side="left"))
        j_end = int(np.searchsorted(B5["t"], t_close + horizon, side="right"))
        tg = {"tp1": tp1, "tp2": tp2, **{f"usd{int(u)}": e + sgn * u for u in USD}}
        rc = races(B5, j0, j_end, long, e, sl, tg)
        exit_t = FR.ts(t["exit_time"])
        jx = int(np.searchsorted(B5["t"], exit_t + sec, side="left"))
        seg_l, seg_h = B5["l"][j0:max(jx, j0 + 1)], B5["h"][j0:max(jx, j0 + 1)]
        mae = (e - float(np.min(seg_l))) if long else (float(np.max(seg_h)) - e)
        row = {"exit_reason": t["exit_reason"], "r": t["r"], "gross_r": t["gross_pts"] / d_sl if d_sl else 0.0,
               "cost_r": cost / d_sl if d_sl else 0.0, "d_sl": d_sl, "day": t["entry_time"][:10],
               "replica": rep, "agrees": None, "races": rc, "mae_r": max(mae, 0.0) / d_sl if d_sl else 0.0}
        if t["exit_reason"] not in ("FLIP", "OPEN"):
            same_t = int(t_tf[rep["exit_i"]]) == exit_t if rep["reason"] != "OPEN_AT_HORIZON" else False
            row["agrees"] = rep["reason"] == t["exit_reason"] and same_t and abs(rep["gross"] - t["gross_pts"]) <= 0.011
        # matched random twins: the arm's own timeframe, the same UTC hour +-1, direction, stop / TP1 / TP2 distances
        # and cost, and the same follow-up time as the trade had (the horizon, or less near the end of the data)
        fu = min(horizon, t_last - t_close)
        hr = (t_close // 3600) % 24
        ok = (closes >= pool_lo) & (closes <= t_last - fu) & (np.minimum((hours - hr) % 24, (hr - hours) % 24) <= 1)
        cand = np.flatnonzero(ok & (np.abs(closes - t_close) > sec))
        row["twins"] = len(cand)
        rnd = {m: [] for m in MEASURES}
        for ii in cand:                                       # every candidate once; the null resamples them below
            ii = int(ii)
            er = float(Btf["c"][ii])
            sl_r, tp1_r, tp2_r = er - sgn * d_sl, er + sgn * d1, er + sgn * d2
            tc = int(t_tf[ii]) + sec
            ie = int(np.searchsorted(t_tf, tc + fu, side="right"))
            m = manage(Btf, ii + 1, ie, long, er, sl_r, tp1_r, tp2_r, cost)
            a0 = int(np.searchsorted(B5["t"], tc, side="left"))
            a1 = int(np.searchsorted(B5["t"], tc + fu, side="right"))
            rr = races(B5, a0, a1, long, er, sl_r, {"tp1": tp1_r, "tp2": tp2_r, **{f"usd{int(u)}": er + sgn * u for u in USD}})
            for nm in ("tp1", "tp2", "usd10", "usd15", "usd20"):
                v = rr.get(nm, (None, None))[0]
                rnd[f"{nm}_first"].append(np.nan if v is None else float(v == "TP"))
            rnd["no_flip_r"].append(m["r"] if m["reason"] != "OPEN_AT_HORIZON" else np.nan)
        u = len(cand)
        pick = rng.integers(0, u, size=k_rand) if u else None          # K pseudo-ledger draws, with replacement
        row["random"] = {m: (np.asarray(v, dtype=float)[pick] if u else np.full(k_rand, np.nan)) for m, v in rnd.items()}
        rows.append(row)
    return summarise(rows, missing, k_rand)


def summarise(rows: list, missing: int, k_rand: int) -> dict:
    n = len(rows)
    out = {"trades": n, "entry_bar_missing": missing}
    if not n:
        return out
    r = np.array([x["r"] for x in rows])
    g = np.array([x["gross_r"] for x in rows])
    cr = np.array([x["cost_r"] for x in rows])
    out["exits"] = dict(Counter(x["exit_reason"] for x in rows))
    out["mean_r_by_exit"] = {k: round(float(np.mean([x["r"] for x in rows if x["exit_reason"] == k])), 4) for k in out["exits"]}
    out["cost"] = {"mean_net_r": round(float(r.mean()), 4), "mean_gross_r": round(float(g.mean()), 4),
                   "mean_cost_r": round(float(cr.mean()), 4), "median_cost_r": round(float(np.median(cr)), 4),
                   "gross_gain_net_loss": int(np.sum((g > 0) & (r <= 0))), "median_stop_usd": round(float(np.median([x["d_sl"] for x in rows])), 2)}
    ag = [x["agrees"] for x in rows if x["agrees"] is not None]
    out["replica_agreement"] = {"checked": len(ag), "agree": int(sum(ag)), "rate": round(sum(ag) / len(ag), 4) if ag else None}
    fl = [x for x in rows if x["exit_reason"] == "FLIP"]
    if fl:
        nf = [x["replica"] for x in fl]
        decided = [m for m in nf if m["reason"] != "OPEN_AT_HORIZON"]
        out["flip_counterfactual"] = {
            "flips": len(fl), "held_outcome": dict(Counter(m["reason"] for m in nf)),
            "mean_realised_r": round(float(np.mean([x["r"] for x in fl])), 4),
            "mean_held_r_decided": round(float(np.mean([m["r"] for m in decided])), 4) if decided else None,
            "mean_held_r_all_marked": round(float(np.mean([m["r"] for m in nf])), 4),
            "held_better": int(sum(m["r"] > x["r"] for m, x in zip(nf, fl))),
            "held_worse": int(sum(m["r"] < x["r"] for m, x in zip(nf, fl))),
            "tp1_done_before_flip_in_replica": int(sum(1 for m in nf if m["tp1_done"]))}
    allr = [x["replica"] for x in rows]
    out["no_flip_all"] = {"mean_r_decided": round(float(np.mean([m["r"] for m in allr if m["reason"] != "OPEN_AT_HORIZON"])), 4)
                          if any(m["reason"] != "OPEN_AT_HORIZON" for m in allr) else None,
                          "outcomes": dict(Counter(m["reason"] for m in allr))}
    tgt = {}
    for nm in ("tp1", "tp2", "usd10", "usd15", "usd20"):
        res = [x["races"].get(nm, (None, None)) for x in rows]
        dec = [v for v in res if v[0] is not None]
        k = sum(1 for v in dec if v[0] == "TP")
        tt = [v[1] for v in dec if v[0] == "TP"]
        tgt[nm] = {"decided": len(dec), "target_first": k, "rate": round(k / len(dec), 4) if dec else None,
                   "wilson95": FR.wilson(k, len(dec)) if dec else None, "undecided": len(res) - len(dec),
                   "median_hours_to_target": round(float(np.median(tt)), 2) if tt else None}
    out["targets_before_stop"] = tgt
    mfe = np.array([x["races"].get("mfe_usd", 0.0) for x in rows])
    d = np.array([x["d_sl"] for x in rows])
    out["excursions"] = {"mfe_before_stop_usd_median": round(float(np.median(mfe)), 2),
                         "mfe_before_stop_r_median": round(float(np.median(mfe / d)), 3),
                         "share_mfe_ge_10usd": round(float(np.mean(mfe >= 10)), 4),
                         "share_mfe_ge_15usd": round(float(np.mean(mfe >= 15)), 4),
                         "share_mfe_ge_20usd": round(float(np.mean(mfe >= 20)), 4),
                         "mae_in_trade_r_median": round(float(np.median([x["mae_r"] for x in rows])), 3)}
    # matched random comparison
    cmp_ = {}
    tw = [x["twins"] for x in rows]
    too_few = float(np.median(tw)) < MIN_TWINS
    for m in MEASURES:
        if m == "no_flip_r":
            act = np.array([x["replica"]["r"] if x["replica"]["reason"] != "OPEN_AT_HORIZON" else np.nan for x in rows])
        else:
            v = [x["races"].get(m[:-6], (None, None))[0] for x in rows]
            act = np.array([np.nan if a is None else float(a == "TP") for a in v])
        K = min((len(x["random"][m]) for x in rows), default=0)
        rnd = np.array([x["random"][m][:K] for x in rows], dtype=float) if K else np.zeros((n, 0))
        cmp_[m] = perm_p(act, rnd)
        if too_few:
            cmp_[m].update(p_two_sided=None, p_normal=None, note=f"too few distinct twins (median {float(np.median(tw)):g} < {MIN_TWINS})")
    out["vs_matched_random"] = cmp_
    out["random_twins_per_trade"] = {"min": int(min(tw)), "median": float(np.median(tw)), "max": int(max(tw))}
    out["pseudo_ledgers"] = k_rand
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--bars", required=True)
    ap.add_argument("--arms", default="h4")
    ap.add_argument("--random", type=int, default=200)
    ap.add_argument("--horizon-days", type=float, default=7.0)
    ap.add_argument("--seed", type=int, default=20261126)
    ap.add_argument("--pool-days", type=float, default=0.0,
                    help="0 = twins from the forward window only (default); N = twins from the last N days of bars")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    with open(os.path.join(a.ledger, "holdout_manifest.json")) as f:
        man = json.load(f)
    key = man["freeze_key"]
    t_lo = FR.ts(man["freeze_utc"][:19] + "+00:00")
    rng = np.random.default_rng(a.seed)
    horizon = int(a.horizon_days * 86400)
    B5 = arrays(bars(a.bars, "5m"))
    pool_lo = t_lo if a.pool_days <= 0 else int(B5["t"][-1] - a.pool_days * 86400)
    cache = {}
    out = {"key": key, "freeze_utc": man["freeze_utc"], "seed": a.seed, "pseudo_ledgers": a.random,
           "twin_pool": "forward window" if a.pool_days <= 0 else f"last {a.pool_days:g} days of bars",
           "horizon_days": a.horizon_days, "bars_5m_last_utc": int(B5["t"][-1]), "ledgers": {}}
    arms = [x.strip() for x in a.arms.split(",") if x.strip()]
    for tf in ("5m", "15m", "30m", "1h", "4h"):
        for arm in arms:
            f = os.path.join(a.ledger, "holdout", f"{tf}_{arm}.json")
            if not os.path.exists(f):
                continue
            with open(f) as fh:
                tr = [t for t in json.load(fh) if ":".join(t.get("freeze_key", "").split(":")[:2]) == key and not t.get("open")]
            if not tr:
                continue
            if tf not in cache:
                cache[tf] = arrays(bars(a.bars, tf))
            out["ledgers"][f"{tf}_{arm}"] = diagnose(tr, tf, cache[tf], B5, pool_lo, horizon, a.random, rng)
    fam = [(lk, m, v["p_normal"]) for lk, L in out["ledgers"].items() for m, v in L.get("vs_matched_random", {}).items()
           if v.get("p_normal") is not None]
    if fam:
        ps = [p for *_, p in fam]
        for (lk, m, _), ph, pb in zip(fam, holm(ps), bh(ps)):
            out["ledgers"][lk]["vs_matched_random"][m]["p_holm"] = round(ph, 4)
            out["ledgers"][lk]["vs_matched_random"][m]["p_bh"] = round(pb, 4)
    out["multiplicity"] = {"family": len(fam), "method": "Holm (FWER) and Benjamini-Hochberg (FDR) over every p_normal listed "
                                                         "(the normal tail of the matched null; p_two_sided is the empirical one)"}
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(out, fh, indent=1, default=float)
    for lk, L in out["ledgers"].items():
        if not L.get("trades"):
            continue
        c, tg, vm = L["cost"], L["targets_before_stop"], L["vs_matched_random"]
        print(f"{lk:16s} n {L['trades']:4d} net {c['mean_net_r']:+.3f}R gross {c['mean_gross_r']:+.3f}R cost {c['mean_cost_r']:.3f}R "
              f"| replica {L['replica_agreement']['agree']}/{L['replica_agreement']['checked']} "
              f"| exits {L['exits']}")
        if "flip_counterfactual" in L:
            fc = L["flip_counterfactual"]
            print(f"{'':16s} FLIP {fc['flips']}: realised {fc['mean_realised_r']:+.3f}R, held {fc['mean_held_r_decided']}R (decided), "
                  f"held outcomes {fc['held_outcome']}, held better {fc['held_better']} / worse {fc['held_worse']}")
        print(f"{'':16s} before stop: " + " · ".join(f"{k} {v['rate']} ({v['target_first']}/{v['decided']})" for k, v in tg.items()))
        print(f"{'':16s} vs random: " + " · ".join(f"{k} {v.get('actual')} vs {v.get('null_mean')} p {v.get('p_two_sided')}"
                                                     f"/{v.get('p_normal')} holm {v.get('p_holm')}" for k, v in vm.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
