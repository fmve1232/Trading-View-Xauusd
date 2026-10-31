"""Execution-assumption sensitivity (HYPOTHETICAL simulation; read-only; never writes a ledger).

Usage (repo root):
    TWELVEDATA_API_KEY=offline PYTHONPATH=. python audit/tools/exec_sensitivity.py <market-data store copy> 5m,15m,1h out.json

The engine runs on a copy of the store. Network calls are disabled; the key only selects the Twelve Data XAU/USD
series. Every arm's own code produces its signals. The script captures the input each arm hands to
`backtest.simulate`, then replays that input under these execution assumptions:

  web6         stops fill at the stop price even when the bar opened beyond it (the old rule; audit/tools/gapsim.py)
  web7         the approved Amendment 14 rule: the deployed quantum.backtest.simulate, unchanged
  gap+x        web7, plus x points of extra adverse slippage on every gap exit (SL_GAP / BE_GAP)
  stop+x       web7, plus x points of extra adverse slippage on every stop exit (SL, BE, SL_GAP, BE_GAP)
  5m-path      15m / 1h trades re-walked on 5-minute bars with the web7 rule (finer intrabar order; BE live
               from the next 5-minute bar). Only trades whose whole holding period lies inside the 5-minute store
               are used. Trades are re-evaluated one at a time: a different exit is not allowed to change later
               entries. Flip exits keep their original time and price.

Slippage is applied to the exit price of the quantity still open (1.0, or 0.5 after TP1). It does not move the exit
time, so the trade path is unchanged and the adjustment is exact. These are simulated prices, not fills.
Tick-level execution is NOT RUN: no tick data source is available to this project.
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from quantum.data import market as mk, sources as _src  # noqa: E402


def _off(*a, **k):
    raise _src.FetchError("offline audit run")


_src._get = _off
from quantum import arm_h2, arm_h3, arm_h4, arm_h5, arm_h6, backtest, engine  # noqa: E402
from quantum.config import DEFAULT  # noqa: E402
import gapsim  # noqa: E402

TFSEC = {"5m": 300, "15m": 900, "1h": 3600}
REAL_SIM = backtest.simulate


def stats(tr):
    tr = [t for t in tr if not t.get("open")]
    if not tr:
        return {"n": 0}
    r = np.array([t["r"] for t in tr])
    pts = np.array([t["pts"] for t in tr])
    gl = -pts[pts < 0].sum()
    cum = np.cumsum(r)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max())
    sd = r.std(ddof=1) if len(r) > 1 else float("nan")
    return {"n": len(r), "win": round(float((r > 0).mean() * 100), 1), "mean_r": round(float(r.mean()), 4),
            "t": round(float(r.mean() / (sd / math.sqrt(len(r)))), 2) if len(r) > 1 and sd > 0 else None,
            "pf": round(float(pts[pts > 0].sum() / gl), 3) if gl > 0 else None, "sum_r": round(float(r.sum()), 3),
            "max_dd_r": round(dd, 3)}


def slip(trades, x, gaps_only):
    out = []
    for t in trades:
        t = dict(t)
        why = t["exit_reason"]
        hit = why in ("SL_GAP", "BE_GAP") if gaps_only else why in ("SL", "BE", "SL_GAP", "BE_GAP")
        if hit and not t.get("open"):
            q = 0.5 if t["tp1_hit"] else 1.0
            t["pts"] = t["pts"] - x * q
            risk = abs(t["entry"] - t["sl"])
            t["r"] = t["pts"] / risk if risk > 0 else 0.0
        out.append(t)
    return out


def walk_5m(t, m5, tf_sec):
    """Re-walk one trade on 5-minute bars (web7 rule). Returns the new trade, or None when it is not covered."""
    o5, h5, l5, c5, ts = m5
    t_entry = np.datetime64(t["entry_time"][:19]) + np.timedelta64(tf_sec, "s")      # the signal bar's close
    t_exit_open = np.datetime64(t["exit_time"][:19])
    if t_entry < ts[0] or t.get("open"):
        return None
    lg = t["dir"] == "LONG"
    sl, tp1, tp2, entry = t["sl"], t["tp1"], t["tp2"], t["entry"]
    flip_end = t_exit_open + np.timedelta64(tf_sec, "s") if t["exit_reason"] == "FLIP" else None
    legs, qty, tp1_done, be = [], 1.0, False, False
    j = int(np.searchsorted(ts, t_entry))
    while j < len(ts):
        if flip_end is not None and ts[j] >= flip_end:
            break
        oi = o5[j]
        beyond = (lambda v: oi >= v) if lg else (lambda v: oi <= v)
        through = (lambda v: oi <= v) if lg else (lambda v: oi >= v)
        lab = "BE" if be else "SL"
        if beyond(tp2):
            if not tp1_done:
                legs.append((0.5, oi)); qty -= 0.5; tp1_done = True
            return _fin(t, legs, qty, oi, "TP2")
        if not tp1_done and beyond(tp1):
            legs.append((0.5, oi)); qty -= 0.5; tp1_done = True
        if through(sl):
            return _fin(t, legs, qty, oi, lab + "_GAP")
        if (l5[j] <= sl) if lg else (h5[j] >= sl):
            return _fin(t, legs, qty, sl, lab)
        if not tp1_done and ((h5[j] >= tp1) if lg else (l5[j] <= tp1)):
            legs.append((0.5, tp1)); qty -= 0.5; tp1_done = True
        if (h5[j] >= tp2) if lg else (l5[j] <= tp2):
            return _fin(t, legs, qty, tp2, "TP2")
        if tp1_done and not be:
            sl, be = entry, True
        j += 1
    if flip_end is not None:
        return _fin(t, legs, qty, t["exit"], "FLIP")
    return None                                                     # ran off the store: not covered


def _fin(t, legs, qty, px, why):
    sgn = 1.0 if t["dir"] == "LONG" else -1.0
    gross = sum(q * (p - t["entry"]) * sgn for q, p in legs + [(qty, px)])
    pts = gross - t["cost_pts"]
    risk = abs(t["entry"] - t["sl"])
    return dict(t, exit=px, exit_reason=why, gross_pts=gross, pts=pts, r=pts / risk if risk > 0 else 0.0,
                tp1_hit=len(legs) > 0 or why == "TP2")


def main(store, tfs, outp):
    dl = mk.download_all(store, ("5m", "15m", "60m"))
    m5m = mk.build_market("5m", dl)
    b5 = m5m.base
    m5 = (b5["open"].to_numpy(float), b5["high"].to_numpy(float), b5["low"].to_numpy(float), b5["close"].to_numpy(float),
          b5.index.tz_convert("UTC").tz_localize(None).to_numpy().astype("datetime64[s]"))
    out = {"note": "HYPOTHETICAL simulation on stored data; not fills; not the forward record.", "price_source": m5m.price_source,
           "five_minute_from": str(b5.index[0]), "rows": {}}
    for tf in tfs:
        m = mk.build_market(tf, dl)
        F = None
        res = {}
        for arm in ("treatment", "control", "challenger"):
            res[arm] = engine.run(m, DEFAULT, arm, F)
            F = res[arm].F
        captured = {}

        def cap(name):
            def f(r, cfg, start=0):
                captured[name] = r
                return REAL_SIM(r, cfg, start)
            return f
        runs = {"treatment": lambda: cap("treatment")(res["treatment"], DEFAULT),
                "control": lambda: cap("control")(res["control"], DEFAULT),
                "challenger": lambda: cap("challenger")(res["challenger"], DEFAULT)}
        for name, call in (("h2", lambda: arm_h2.simulate(res["treatment"], DEFAULT)), ("h3", lambda: arm_h3.simulate(res["treatment"], m, DEFAULT)),
                           ("h4", lambda: arm_h4.simulate(res["treatment"], DEFAULT)), ("h5", lambda: arm_h5.simulate(res["treatment"], DEFAULT, m.tf_sec)),
                           ("h6", lambda: arm_h6.simulate(res["treatment"], DEFAULT))):
            runs[name] = call
        for name, call in runs.items():
            backtest.simulate = cap(name)
            try:
                call()
            finally:
                backtest.simulate = REAL_SIM
            r = captured[name]
            w7 = REAL_SIM(r, DEFAULT)
            w6 = gapsim.simulate(r, DEFAULT, "current")
            row = {"bars": len(r.F["c"]), "from": str(r.F["index"][0]), "to": str(r.F["index"][-1]),
                   "gap_exits": sum(1 for t in w7 if t["exit_reason"].endswith("_GAP")),
                   "stop_exits": sum(1 for t in w7 if t["exit_reason"] in ("SL", "BE", "SL_GAP", "BE_GAP")),
                   "web6": stats(w6), "web7": stats(w7)}
            for x in (0.5, 1.0, 2.0):
                row[f"gap+{x}"] = stats(slip(w7, x, True))
            for x in (0.2, 0.5):
                row[f"stop+{x}"] = stats(slip(w7, x, False))
            if tf != "5m":
                pairs = [(t, walk_5m(t, m5, TFSEC[tf])) for t in w7 if not t.get("open")]
                pairs = [(a, b) for a, b in pairs if b is not None]
                row["5m_path"] = {"covered": len(pairs), "chart_bars": stats([a for a, _ in pairs]), "five_min": stats([b for _, b in pairs]),
                                  "pnl_changed": sum(1 for a, b in pairs if abs(a["pts"] - b["pts"]) > 0.005),   # production rounds pts to 3 dp
                                  "label_only_changed": sum(1 for a, b in pairs if a["exit_reason"] != b["exit_reason"] and abs(a["pts"] - b["pts"]) <= 0.005)}
            out["rows"][f"{tf}/{name}"] = row
            print(tf, name, json.dumps({k: row[k] for k in ("gap_exits", "web6", "web7")}), flush=True)
    json.dump(out, open(outp, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2].split(","), sys.argv[3])
