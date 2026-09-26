"""Strategy-twin backtest: the A/B arms of the Pine Strategy files, simulated bar by bar.

EXECUTION MODEL (stated, conservative, the same for both arms):
  * Entry at the CLOSE of the confirmed signal bar (Pine: process_orders_on_close = true).
  * Stop and targets are live from the NEXT bar. Both TP1 and SL inside one bar = STOP FIRST
    (the engine's own labelling convention; TradingView instead guesses the intrabar path).
  * 50% off at TP1, the rest at TP2; after TP1 the stop moves to entry from the next bar.
  * An opposite executed signal closes the position at that close and reverses (Pine: flip).
  * Round-trip cost per ounce = session spread + 2 x slippage + commission/lot / 100 oz,
    the engine's own cost model (the same one planExpectancy charges).
P&L is reported in price points (= USD per ounce) and in R (multiples of the initial stop).

Nothing here chooses a parameter. Walk-forward folds MEASURE stability over time; they do
not re-fit anything, because the configuration is frozen (see holdout.py).
"""
from __future__ import annotations

import math

import numpy as np


def simulate(res, cfg, start: int = 0) -> list[dict]:
    F, R = res.F, res.rows
    h, l, c = F["h"], F["l"], F["c"]
    idx = F["index"]
    spread = F["sess_spread"]
    eb, es = R["exec_buy"], R["exec_sell"]
    trades = []
    pos = None
    n = len(c)
    for i in range(start, n):
        # 1) manage an open position on this bar's range (its orders were placed at an earlier close)
        if pos is not None and i > pos["entry_i"]:
            lg = pos["long"]
            if (l[i] <= pos["sl"]) if lg else (h[i] >= pos["sl"]):          # stop first on any tie
                _close(pos, pos["sl"], i, idx, "BE" if pos["tp1_done"] else "SL", trades)
                pos = None
            else:
                if not pos["tp1_done"] and ((h[i] >= pos["tp1"]) if lg else (l[i] <= pos["tp1"])):
                    pos["legs"].append((0.5, pos["tp1"]))
                    pos["qty"] -= 0.5
                    pos["tp1_done"] = True
                if (h[i] >= pos["tp2"]) if lg else (l[i] <= pos["tp2"]):
                    _close(pos, pos["tp2"], i, idx, "TP2", trades)
                    pos = None
                elif pos["tp1_done"]:
                    pos["sl"] = pos["entry"]      # breakeven, live from the next bar
        # 2) signals at this bar's close
        sig = 1 if eb[i] == 1 else -1 if es[i] == 1 else 0
        if sig != 0:
            if pos is not None and ((sig == 1) != pos["long"]):
                _close(pos, c[i], i, idx, "FLIP", trades)
                pos = None
            if pos is None:
                sl = R["plan_sl"][i]
                tp1 = R["plan_tp1"][i]
                tp2 = R["plan_tp2"][i]
                if not (math.isnan(sl) or math.isnan(tp1) or math.isnan(tp2)):
                    cost = spread[i] + 2.0 * cfg.slippage_pts + cfg.commission_l / max(cfg.point_value, 1.0)
                    pos = dict(long=sig == 1, entry=c[i], entry_i=i, sl=sl, sl0=sl, tp1=tp1, tp2=tp2, qty=1.0,
                               legs=[], tp1_done=False, cost=cost, tq=int(R["tq"][i]),
                               p=float(R["cal_p_long"][i] if sig == 1 else R["cal_p_short"][i]),
                               ev=float(R["plan_ev"][i]), session=str(F["session_label"][i]),
                               regime=str(F["mkt_regime"][i]), entry_time=idx[i].isoformat())
    if pos is not None:
        pos["open"] = True
        _close(pos, c[n - 1], n - 1, idx, "OPEN", trades)
    return trades


def _close(pos, px, i, idx, why, trades):
    legs = pos["legs"] + [(pos["qty"], px)]
    sgn = 1.0 if pos["long"] else -1.0
    gross = sum(q * (p - pos["entry"]) * sgn for q, p in legs)
    net = gross - pos["cost"]
    risk = abs(pos["entry"] - pos["sl0"])
    trades.append(dict(
        dir="LONG" if pos["long"] else "SHORT", entry_time=pos["entry_time"], exit_time=idx[i].isoformat(),
        entry_i=pos["entry_i"], exit_i=i, entry=round(pos["entry"], 3), sl=round(pos["sl0"], 3),
        tp1=round(pos["tp1"], 3), tp2=round(pos["tp2"], 3), exit=round(px, 3), exit_reason=why,
        tp1_hit=pos["tp1_done"], pts=round(net, 3), gross_pts=round(gross, 3), cost_pts=round(pos["cost"], 3),
        r=round(net / risk, 4) if risk > 0 else 0.0, bars=i - pos["entry_i"], tq=pos["tq"],
        p=None if math.isnan(pos["p"]) else round(pos["p"], 4), ev=None if math.isnan(pos["ev"]) else round(pos["ev"], 4),
        session=pos["session"], regime=pos["regime"], open=pos.get("open", False)))


def metrics(trades: list[dict], risk_pct: float = 1.0) -> dict:
    closed = [t for t in trades if not t.get("open")]
    n = len(closed)
    if n == 0:
        return {"n": 0}
    r = np.array([t["r"] for t in closed])
    pts = np.array([t["pts"] for t in closed])
    wins = r > 0
    gp = pts[pts > 0].sum()
    gl = -pts[pts < 0].sum()
    eq = np.cumprod(1.0 + risk_pct / 100.0 * r)  # fixed-fractional: risk_pct of equity per trade
    peak = np.maximum.accumulate(np.concatenate([[1.0], eq]))[1:]
    dd = (peak - eq) / peak
    cum_r = np.cumsum(r)
    rpeak = np.maximum.accumulate(np.concatenate([[0.0], cum_r]))[1:]
    streak = best = 0
    for x in r:
        streak = streak + 1 if x <= 0 else 0
        best = max(best, streak)
    sd = r.std(ddof=1) if n > 1 else float("nan")
    dsd = math.sqrt(float(np.mean(np.minimum(r, 0.0) ** 2)))   # downside deviation over ALL trades
    return {
        "n": n, "win_rate": float(wins.mean() * 100), "avg_r": float(r.mean()), "median_r": float(np.median(r)),
        "expectancy_r": float(r.mean()), "sum_r": float(r.sum()), "net_pts": float(pts.sum()),
        "profit_factor": float(gp / gl) if gl > 0 else None, "avg_win_r": float(r[wins].mean()) if wins.any() else None,
        "avg_loss_r": float(r[~wins].mean()) if (~wins).any() else None,
        "max_dd_pct": float(dd.max() * 100), "max_dd_r": float((rpeak - cum_r).max()),
        "final_equity_pct": float((eq[-1] - 1) * 100), "sharpe_per_trade": float(r.mean() / sd) if sd and sd > 0 else None,
        "sortino_per_trade": float(r.mean() / dsd) if dsd and dsd > 0 else None, "longest_losing_streak": int(best),
        "tp1_rate": float(np.mean([t["tp1_hit"] for t in closed]) * 100), "avg_bars": float(np.mean([t["bars"] for t in closed])),
        "longs": sum(1 for t in closed if t["dir"] == "LONG"), "shorts": sum(1 for t in closed if t["dir"] == "SHORT"),
        "t_stat": float(r.mean() / (sd / math.sqrt(n))) if sd and sd > 0 and n > 1 else None,
    }


def breakdown(trades: list[dict], key: str) -> dict:
    out = {}
    for t in trades:
        if t.get("open"):
            continue
        out.setdefault(t[key], []).append(t)
    return {k: metrics(v) for k, v in out.items()}


def walk_forward(trades: list[dict], index, folds: int = 5) -> list[dict]:
    """Split the SAMPLE PERIOD into equal time folds and report each. No re-fitting."""
    if len(index) == 0:
        return []
    t0, t1 = index[0], index[-1]
    edges = [t0 + (t1 - t0) * k / folds for k in range(folds + 1)]
    out = []
    for k in range(folds):
        a, b = edges[k], edges[k + 1]
        tr = [t for t in trades if not t.get("open") and a.isoformat() <= t["entry_time"] < b.isoformat()]
        m = metrics(tr)
        m.update({"from": a.isoformat(), "to": b.isoformat()})
        out.append(m)
    return out


def monte_carlo(trades: list[dict], runs: int = 2000, risk_pct: float = 1.0, seed: int = 11) -> dict:
    r = np.array([t["r"] for t in trades if not t.get("open")])
    if len(r) < 5:
        return {"runs": 0}
    rng = np.random.default_rng(seed)
    sims = rng.choice(r, size=(runs, len(r)), replace=True)
    eq = np.cumprod(1.0 + risk_pct / 100.0 * sims, axis=1)
    peak = np.maximum.accumulate(np.concatenate([np.ones((runs, 1)), eq], axis=1), axis=1)[:, 1:]
    mdd = ((peak - eq) / peak).max(axis=1) * 100
    fin = (eq[:, -1] - 1) * 100
    pct = lambda x: {"p5": float(np.percentile(x, 5)), "p50": float(np.percentile(x, 50)), "p95": float(np.percentile(x, 95))}
    return {"runs": runs, "trades": int(len(r)), "final_equity_pct": pct(fin), "max_dd_pct": pct(mdd),
            "prob_loss": float((fin < 0).mean() * 100),
            "note": "i.i.d. bootstrap of trade R. Ignores serial dependence, so it understates tail risk when losses cluster."}


def calibration_test(trades: list[dict]) -> dict:
    """F-A12: does the calibrated P at entry predict the realised outcome? (TP1 hit before SL)"""
    pts = [(t["p"], 1.0 if t["tp1_hit"] else 0.0) for t in trades if not t.get("open") and t["p"] is not None]
    if len(pts) < 10:
        return {"n": len(pts)}
    p = np.array([x[0] for x in pts])
    y = np.array([x[1] for x in pts])
    bins = []
    for lo in (0.0, 0.5, 0.6, 0.7, 0.8):
        hi = {0.0: 0.5, 0.5: 0.6, 0.6: 0.7, 0.7: 0.8, 0.8: 1.01}[lo]
        m = (p >= lo) & (p < hi)
        if m.any():
            bins.append({"lo": lo, "hi": min(hi, 1.0), "n": int(m.sum()), "pred": float(p[m].mean() * 100), "obs": float(y[m].mean() * 100)})
    return {"n": len(pts), "brier": float(np.mean((p - y) ** 2)), "base_rate": float(y.mean() * 100), "bins": bins}
