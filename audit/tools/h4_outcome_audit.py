"""Decomposition of the H4 Playbook record ("won 35% of 986") — read-only, offline, nothing is changed or tuned.

Usage (repo root):
    TWELVEDATA_API_KEY=offline PYTHONPATH=. python audit/tools/h4_outcome_audit.py <market-data store copy> 15m out.json

It reproduces the site's in-sample record with the deployed engine (web.7), then measures every quantity the operator's
research brief asks for (Part 1): triggers versus trades, overlap, the exit mix, realised versus advertised
reward / risk, gross and net expectancy, cost in R, MFE / MAE, bars where the stop and TP1 were both touched, rollover,
sessions, regimes and direction. It also runs DIAGNOSTIC counterfactuals (no flips; a full exit at TP1; zero cost; the
fixed-horizon direction of every trigger). Those explain the record; they are not candidate rules, and none may be
adopted from this in-sample window (CLAUDE.md "Do not tune").
"""
import json
import math
import os
import sys
from collections import defaultdict
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from quantum.data import market as mk, sources as _src  # noqa: E402


def _off(*a, **k):
    raise _src.FetchError("offline audit run")


_src._get = _off
from quantum import arm_h4, backtest, engine  # noqa: E402
from quantum.config import DEFAULT  # noqa: E402
import gapsim  # noqa: E402


def wilson(k, n, z=1.959964):
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def summ(T, rng=None):
    T = [t for t in T if not t.get("open")]
    n = len(T)
    if n == 0:
        return {"n": 0}
    r = np.array([t["r"] for t in T])
    g = np.array([t["gross_pts"] / abs(t["entry"] - t["sl"]) for t in T])
    pts = np.array([t["pts"] for t in T])
    w = r > 0
    gl = -pts[pts < 0].sum()
    cum = np.cumsum(r)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max())
    sd = r.std(ddof=1) if n > 1 else math.nan
    out = {"n": n, "win_pct": round(100 * w.mean(), 1), "wilson": [round(100 * x, 1) for x in wilson(int(w.sum()), n)],
           "avg_win_r": round(float(r[w].mean()), 3) if w.any() else None, "avg_loss_r": round(float(r[~w].mean()), 3) if (~w).any() else None,
           "median_win_r": round(float(np.median(r[w])), 3) if w.any() else None,
           "median_loss_r": round(float(np.median(r[~w])), 3) if (~w).any() else None,
           "gross_exp_r": round(float(g.mean()), 4), "net_exp_r": round(float(r.mean()), 4),
           "cost_r": round(float((g - r).mean()), 4), "pf": round(float(pts[pts > 0].sum() / gl), 3) if gl > 0 else None,
           "t": round(float(r.mean() / (sd / math.sqrt(n))), 2) if n > 1 and sd > 0 else None, "sum_r": round(float(r.sum()), 2),
           "max_dd_r": round(dd, 2), "avg_bars": round(float(np.mean([t["bars"] for t in T])), 1),
           "median_bars": float(np.median([t["bars"] for t in T]))}
    if rng is not None and n >= 10:
        b = r[rng.integers(0, n, size=(5000, n))].mean(axis=1)
        out["net_exp_ci"] = [round(float(np.percentile(b, 2.5)), 4), round(float(np.percentile(b, 97.5)), 4)]
    return out


def main(store, tf, outp):
    rng = np.random.default_rng(7)
    dl = mk.download_all(store, ("5m", "15m", "60m"))
    m = mk.build_market(tf, dl)
    res = engine.run(m, DEFAULT, "treatment")
    F = res.F
    n = len(F["c"])
    o, h, l, c = (np.asarray(F[k], float) for k in ("o", "h", "l", "c"))
    idx = F["index"]
    trades, ev = arm_h4.simulate(res, DEFAULT)
    closed = [t for t in trades if not t.get("open")]
    rows = {"exec_buy": ev["exec_buy"], "exec_sell": ev["exec_sell"], "plan_sl": ev["plan_sl"], "plan_tp1": ev["plan_tp1"],
            "plan_tp2": ev["plan_tp2"], "tq": res.rows["tq"], "cal_p_long": res.rows["cal_p_long"],
            "cal_p_short": res.rows["cal_p_short"], "plan_ev": res.rows["plan_ev"]}
    r_ns = SimpleNamespace(F=F, rows=rows)
    out = {"source": m.price_source, "tf": tf, "bars": n, "from": str(idx[0]), "to": str(idx[-1]),
           "engine_version": __import__("quantum.config", fromlist=["ENGINE_VERSION"]).ENGINE_VERSION}

    # 1. triggers versus trades
    trig = [i for i in range(n) if ev["exec_buy"][i] or ev["exec_sell"][i]]
    entries = {t["entry_i"] for t in trades}


    out["triggers"] = {"trigger_bars": len(trig), "trades_opened": len(trades), "closed": len(closed),
                       "triggers_not_opened": len(trig) - len(entries & set(trig)),
                       "per_100_bars": round(100 * len(trig) / n, 1),
                       "note": "a trigger opens a trade only when flat or opposite (flip); a same-direction trigger while in a trade is ignored; a trigger without valid levels is skipped"}
    gaps = [closed[k + 1]["entry_i"] - closed[k]["exit_i"] for k in range(len(closed) - 1)]
    out["independence"] = {"overlapping_positions": 0, "note": "one position at a time by construction",
                           "next_entry_same_bar_as_exit": sum(1 for g in gaps if g == 0),
                           "next_entry_within_4_bars": sum(1 for g in gaps if g <= 4),
                           "lag1_autocorr_r": round(float(np.corrcoef([t["r"] for t in closed][:-1], [t["r"] for t in closed][1:])[0, 1]), 3)}

    # 2. the record, and its exit mix
    out["record"] = summ(closed, rng)
    by_exit = defaultdict(list)
    for t in closed:
        by_exit[t["exit_reason"]].append(t)
    out["by_exit"] = {k: {"n": len(v), "share_pct": round(100 * len(v) / len(closed), 1), "win_pct": round(100 * np.mean([t["r"] > 0 for t in v]), 1),
                          "mean_r": round(float(np.mean([t["r"] for t in v])), 3), "tp1_hit_pct": round(100 * np.mean([t["tp1_hit"] for t in v]), 1)}
                      for k, v in sorted(by_exit.items(), key=lambda x: -len(x[1]))}
    adv = np.array([abs(t["tp1"] - t["entry"]) / abs(t["entry"] - t["sl"]) for t in closed])
    out["advertised_vs_realised"] = {"median_advertised_tp1_rr": round(float(np.median(adv)), 2), "mean_advertised_tp1_rr": round(float(adv.mean()), 2),
                                     "realised_avg_win_over_avg_loss": round(abs(out["record"]["avg_win_r"] / out["record"]["avg_loss_r"]), 2),
                                     "breakeven_win_pct_at_realised_payoff": round(100 / (1 + abs(out["record"]["avg_win_r"] / out["record"]["avg_loss_r"])), 1),
                                     "tp1_reached_pct": round(100 * np.mean([t["tp1_hit"] for t in closed]), 1),
                                     "stop_hit_before_tp1_pct": round(100 * np.mean([t["exit_reason"] in ("SL", "SL_GAP") for t in closed]), 1)}

    # 3. MFE / MAE, two-way bars, rollover (per closed trade, bars after entry up to the exit bar)
    mfe, mae, amb, roll = [], [], 0, 0
    ny = idx.tz_convert("America/New_York")
    for t in closed:
        a, b = t["entry_i"] + 1, t["exit_i"]
        if b < a:
            continue
        risk = abs(t["entry"] - t["sl"])
        lg = t["dir"] == "LONG"
        hh, ll = h[a:b + 1].max(), l[a:b + 1].min()
        mfe.append(((hh - t["entry"]) if lg else (t["entry"] - ll)) / risk)
        mae.append(((t["entry"] - ll) if lg else (hh - t["entry"])) / risk)
        for j in range(a, b + 1):
            if (l[j] <= t["sl"] and h[j] >= t["tp1"]) if lg else (h[j] >= t["sl"] and l[j] <= t["tp1"]):
                amb += 1
                break
        if any((ny[j].hour == 17 and ny[j].minute == 0) or (ny[j].hour >= 17 > ny[j - 1].hour) for j in range(a, b + 1)):
            roll += 1
    mfe, mae = np.array(mfe), np.array(mae)
    out["excursions"] = {"mfe_r_median": round(float(np.median(mfe)), 3), "mfe_r_p75": round(float(np.percentile(mfe, 75)), 3),
                         "mae_r_median": round(float(np.median(mae)), 3), "reached_1r_mfe_pct": round(100 * float((mfe >= 1).mean()), 1),
                         "reached_2r_mfe_pct": round(100 * float((mfe >= 2).mean()), 1),
                         "trades_with_a_bar_touching_both_stop_and_tp1": amb, "trades_crossing_17h_new_york": roll,
                         "note": "MFE / MAE from bar highs and lows after entry up to the exit bar; no tick data, so the order inside a bar is unknown"}

    # 4. splits (descriptive; many groups: exploratory, multiple testing)
    for key in ("dir", "session", "regime"):
        g = defaultdict(list)
        for t in closed:
            g[t[key]].append(t)
        out[f"by_{key}"] = {k: summ(v) for k, v in sorted(g.items(), key=lambda x: -len(x[1]))}

    # 5. DIAGNOSTIC counterfactuals (same signals, same costs; explanation only)
    noflip = gapsim.simulate(r_ns, DEFAULT, "both", flip=False)
    rows_tp1 = dict(rows, plan_tp2=rows["plan_tp1"])
    tp1full = backtest.simulate(SimpleNamespace(F=F, rows=rows_tp1), DEFAULT)
    F0 = dict(F, sess_spread=np.zeros(n))
    import dataclasses
    zero = backtest.simulate(SimpleNamespace(F=F0, rows=rows), dataclasses.replace(DEFAULT, slippage_pts=0.0, commission_l=0.0))
    out["diagnostic"] = {"as_deployed": out["record"], "no_flip_exits": summ(noflip, rng), "full_exit_at_tp1": summ(tp1full, rng),
                         "zero_cost": summ(zero, rng)}
    # direction of every trigger at fixed horizons (gross points; ignores stops / targets): is the call better than a coin?
    hz = {}
    for H in (1, 4, 16, 48):
        ok, tot, ret = 0, 0, []
        for i in trig:
            if i + H >= n:
                continue
            d = 1 if ev["exec_buy"][i] else -1
            mv = (c[i + H] - c[i]) * d
            ret.append(mv / max(abs(c[i] - ev["plan_sl"][i]), 1e-9) if not math.isnan(ev["plan_sl"][i]) else np.nan)
            tot += 1
            ok += mv > 0
        lo, hi = wilson(ok, tot)
        hz[f"{H}_bars"] = {"n": tot, "correct_pct": round(100 * ok / tot, 1), "wilson": [round(100 * lo, 1), round(100 * hi, 1)],
                           "mean_move_r": round(float(np.nanmean(ret)), 4)}
    out["direction_at_horizon"] = hz
    json.dump(out, open(outp, "w"), indent=1, default=str)
    print(json.dumps(out, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
