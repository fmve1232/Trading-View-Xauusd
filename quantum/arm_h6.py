"""Arm H6 "No score veto" -- pre-registered in audit/PREREGISTRATION.md, Amendment 12.

The treatment engine's own BUY / SELL with ONE of its vetoes removed: the calibration veto (`cal_veto`: the long / short
score below `cal_gate_min_p` once the calibration is live). Everything else is the engine's, read from what it publishes
per bar: the seven entry gates (`should_buy` / `should_sell`), the TQ-floor veto, the negative-EV veto and the risk lock
(when `use_risk_limits` is on). The engine computes, for bar i,

    exec_buy[i] = should_buy[i] and not (tq_floor_veto[i] or ev_veto[i] or cal_veto[i] or (use_risk_limits and risk_lock[i]))

and H6 is the same line without `cal_veto[i]`. The risk lock is the engine's, tracked on the treatment's own signals.

Why: the score behind the veto did not rank outcomes when it was measured against the event it is defined on (AUC ~0.5,
Brier worse than a constant base rate, 15m and 1h, before and after the forward start; Amendment 12). If the veto removes
trades at random, H6 differs from the treatment arm only in the number of trades; if it removes worse ones, H6 does worse.
H6 reads only published values and adds no threshold. Do not change a rule here without a new amendment: H6's freeze
key includes the SHA-256 of this file.
"""
from __future__ import annotations

import hashlib
import math
import os
from types import SimpleNamespace

from . import backtest

ARM = "h6"


def code_hash() -> str:
    with open(os.path.abspath(__file__), "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()[:16]


def freeze_key(engine_key: str) -> str:
    return f"{engine_key}:{code_hash()}"


def _f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return math.nan


def _b(R, k, i) -> bool:
    v = R[k][i]
    return bool(v) and not (isinstance(v, float) and math.isnan(v))


def evaluate(res, cfg) -> dict:
    R = res.rows
    n = len(res.F["c"])
    nan = [math.nan] * n
    out = {"exec_buy": [0] * n, "exec_sell": [0] * n, "plan_sl": list(nan), "plan_tp1": list(nan), "plan_tp2": list(nan),
           "score_vetoed": [0] * n}
    for i in range(n):
        blocked = _b(R, "tq_floor_veto", i) or _b(R, "ev_veto", i) or (cfg.use_risk_limits and _b(R, "risk_lock", i))
        if blocked:
            continue
        buy, sell = _b(R, "should_buy", i), _b(R, "should_sell", i)
        if not (buy or sell):
            continue
        out["exec_buy" if buy else "exec_sell"][i] = 1
        out["score_vetoed"][i] = int(_b(R, "cal_veto", i))     # a trade the treatment arm did not take
        for k in ("plan_sl", "plan_tp1", "plan_tp2"):
            out[k][i] = _f(R[k][i])
    return out


def simulate(res, cfg) -> tuple[list[dict], dict]:
    """H6's trades under the SAME execution model and costs as the other arms."""
    ev = evaluate(res, cfg)
    n = len(res.F["c"])
    rows = {"exec_buy": ev["exec_buy"], "exec_sell": ev["exec_sell"], "plan_sl": ev["plan_sl"], "plan_tp1": ev["plan_tp1"],
            "plan_tp2": ev["plan_tp2"], "tq": res.rows.get("tq", [0] * n), "cal_p_long": res.rows.get("cal_p_long", [math.nan] * n),
            "cal_p_short": res.rows.get("cal_p_short", [math.nan] * n), "plan_ev": res.rows.get("plan_ev", [math.nan] * n)}
    return backtest.simulate(SimpleNamespace(F=res.F, rows=rows), cfg), ev
