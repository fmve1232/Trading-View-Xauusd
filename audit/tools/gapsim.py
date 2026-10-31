"""AUDIT TOOL ONLY (not the engine): backtest.simulate with an optional gap-fill rule, for Amendment 14's impact study.
mode "current": identical to quantum.backtest.simulate (checked trade-for-trade).
mode "stop":    a stop (SL or breakeven) that the bar OPENS beyond fills at the open.
mode "both":    "stop", and a TP limit that the bar OPENS beyond fills at the open (better), before any stop test."""
import math
from quantum.backtest import _close

def simulate(res, cfg, mode="current", spread_override=None):
    F, R = res.F, res.rows
    o, h, l, c = F["o"], F["h"], F["l"], F["c"]
    idx = F["index"]; spread = F["sess_spread"] if spread_override is None else spread_override
    eb, es = R["exec_buy"], R["exec_sell"]
    trades, pos, n = [], None, len(c)
    for i in range(n):
        if pos is not None and i > pos["entry_i"]:
            lg = pos["long"]
            done = False
            if mode == "both":
                # limit orders at the open: TP2 first (whole rest), else TP1
                if (o[i] >= pos["tp2"]) if lg else (o[i] <= pos["tp2"]):
                    if not pos["tp1_done"]:
                        pos["legs"].append((0.5, o[i])); pos["qty"] -= 0.5; pos["tp1_done"] = True
                    _close(pos, o[i], i, idx, "TP2", trades); pos = None; done = True
                elif not pos["tp1_done"] and ((o[i] >= pos["tp1"]) if lg else (o[i] <= pos["tp1"])):
                    pos["legs"].append((0.5, o[i])); pos["qty"] -= 0.5; pos["tp1_done"] = True
            if not done:
                gap = mode in ("stop", "both") and ((o[i] <= pos["sl"]) if lg else (o[i] >= pos["sl"]))
                if gap or ((l[i] <= pos["sl"]) if lg else (h[i] >= pos["sl"])):
                    _close(pos, o[i] if gap else pos["sl"], i, idx, ("BE" if pos["tp1_done"] else "SL") + ("_GAP" if gap else ""), trades)
                    pos = None
                else:
                    if not pos["tp1_done"] and ((h[i] >= pos["tp1"]) if lg else (l[i] <= pos["tp1"])):
                        pos["legs"].append((0.5, pos["tp1"])); pos["qty"] -= 0.5; pos["tp1_done"] = True
                    if (h[i] >= pos["tp2"]) if lg else (l[i] <= pos["tp2"]):
                        _close(pos, pos["tp2"], i, idx, "TP2", trades); pos = None
                    elif pos["tp1_done"]:
                        pos["sl"] = pos["entry"]
        sig = 1 if eb[i] == 1 else -1 if es[i] == 1 else 0
        if sig != 0:
            if pos is not None and ((sig == 1) != pos["long"]):
                _close(pos, c[i], i, idx, "FLIP", trades); pos = None
            if pos is None:
                sl, tp1, tp2 = R["plan_sl"][i], R["plan_tp1"][i], R["plan_tp2"][i]
                if not (math.isnan(sl) or math.isnan(tp1) or math.isnan(tp2)):
                    cost = spread[i] + 2.0 * cfg.slippage_pts + cfg.commission_l / max(cfg.point_value, 1.0)
                    pos = dict(long=sig == 1, entry=c[i], entry_i=i, sl=sl, sl0=sl, tp1=tp1, tp2=tp2, qty=1.0, legs=[], tp1_done=False,
                               cost=cost, tq=int(R["tq"][i]), p=float(R["cal_p_long"][i] if sig == 1 else R["cal_p_short"][i]),
                               ev=float(R["plan_ev"][i]), session=str(F["session_label"][i]), regime=str(F["mkt_regime"][i]),
                               entry_time=idx[i].isoformat())
    if pos is not None:
        pos["open"] = True; _close(pos, c[n - 1], n - 1, idx, "OPEN", trades)
    return trades
