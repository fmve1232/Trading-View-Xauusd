"""Arm H5 "High confidence" -- pre-registered in audit/PREREGISTRATION.md, Amendment 10.

The treatment engine's own BUY / SELL (after all its gates and vetoes), taken only when every other layer agrees: the
bias label at full conviction (BULL / BEAR), the live 4H / 1D trend layers, the macro vote and an active session.
The rule was written into the pre-registration BEFORE this module was run on any price history. Do not change a rule
or a tie-break here without a new amendment: H5's freeze key includes the SHA-256 of this file.

H5 reads only what the frozen engine already published per bar and adds no threshold of its own (60 / 40 are the
engine's HTF thresholds, BULL / BEAR its >= 62 labels, 30 its session gate). It decides on bar i from bar i's own
published values, which the engine computes at bar i's close (a test enforces no look-ahead).
"""
from __future__ import annotations

import hashlib
import math
import os
from types import SimpleNamespace

from . import backtest

ARM = "h5"
HTF = {"240": 14400, "D": 86400}   # the 4H and 1D layers; live only above the chart's timeframe
UP, DOWN, SESSION = 60.0, 40.0, 30


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


def checks(res, i: int, tf_sec: int) -> dict:
    """The five conditions for each side at bar i (also shown on the site as a checklist)."""
    F, R = res.F, res.rows
    live = [k for k, s in HTF.items() if tf_sec < s]
    sc = {k: _f(F["htf_scores"][k][i]) for k in live}
    sq = _f(F["session_quality"][i])
    out = {}
    for side, ex, lab, htf_ok, mac in (("long", "exec_buy", "BULL", lambda v: v >= UP, "macro_bull"),
                                        ("short", "exec_sell", "BEAR", lambda v: v <= DOWN, "macro_bear")):
        out[side] = {
            "engine": bool(R[ex][i]),
            "conviction": R["bias_label"][i] == lab,
            "htf": bool(live) and all(htf_ok(v) for v in sc.values()),
            "macro": bool(F[mac][i]),
            "session": math.isfinite(sq) and sq >= SESSION,
        }
    out["htf_live"] = live
    out["htf_scores"] = sc
    return out


def evaluate(res, tf_sec: int) -> dict:
    n = len(res.F["c"])
    nan = [math.nan] * n
    out = {"exec_buy": [0] * n, "exec_sell": [0] * n, "plan_sl": list(nan), "plan_tp1": list(nan), "plan_tp2": list(nan)}
    for i in range(n):
        ck = checks(res, i, tf_sec)
        side = "long" if all(ck["long"].values()) else "short" if all(ck["short"].values()) else None
        if side is None:
            continue
        out["exec_buy" if side == "long" else "exec_sell"][i] = 1
        for k in ("plan_sl", "plan_tp1", "plan_tp2"):
            out[k][i] = _f(res.rows[k][i])
    out["checklist"] = checks(res, n - 1, tf_sec) if n else None
    return out


def simulate(res, cfg, tf_sec: int) -> tuple[list[dict], dict]:
    """H5's trades under the SAME execution model and costs as the other arms."""
    ev = evaluate(res, tf_sec)
    n = len(res.F["c"])
    rows = {"exec_buy": ev["exec_buy"], "exec_sell": ev["exec_sell"], "plan_sl": ev["plan_sl"], "plan_tp1": ev["plan_tp1"],
            "plan_tp2": ev["plan_tp2"], "tq": res.rows.get("tq", [0] * n), "cal_p_long": res.rows.get("cal_p_long", [math.nan] * n),
            "cal_p_short": res.rows.get("cal_p_short", [math.nan] * n), "plan_ev": res.rows.get("plan_ev", [math.nan] * n)}
    return backtest.simulate(SimpleNamespace(F=res.F, rows=rows), cfg), ev
