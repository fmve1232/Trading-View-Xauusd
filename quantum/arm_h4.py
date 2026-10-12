"""Arm H4 "Playbook" -- pre-registered in audit/PREREGISTRATION.md, Amendment 8.

The site's conditional playbook ("sell below X / buy above Y on a close"), as a measured arm. The rule was
written into the pre-registration BEFORE this module was run on any price history. Do not change a rule, a
constant or a tie-break here without a new amendment: H4's freeze key includes the SHA-256 of this file.

H4 reads only what the frozen engine already published per bar (the liquidity levels, the internal pivots, the
volume profile, the adaptive ATR and the regime stop multiple) and changes none of them. The playbook for bar i
is built at the close of bar i-1, so bar i's signal uses nothing from bar i but its own close (a test enforces
this). The site displays `playbook(res, n - 1)`: the triggers for the next bar, from the same code.
"""
from __future__ import annotations

import hashlib
import math
import os
from types import SimpleNamespace

import numpy as np

from . import backtest

GAP_ATR = 0.1           # a trigger is at least 0.1 ATR beyond price
MERGE_ATR = 0.05        # levels closer than this are one level
MIN_TP_R = 1.0          # a target is at least one stop distance beyond the trigger
FALLBACK_R = 2.0        # with no level that far: 2 stop distances
ARM = "h4"
LEVELS = [   # (name, where it lives, key)
    ("PDH", "rows", "pdh"), ("PDL", "rows", "pdl"), ("PWH", "rows", "pwh"), ("PWL", "rows", "pwl"),
    ("PMH", "F", "pm_high"), ("PML", "F", "pm_low"), ("EQH", "rows", "eqh"), ("EQL", "rows", "eql"),
    ("Day high", "rows", "cdh"), ("Day low", "rows", "cdl"), ("Internal high", "rows", "active_res"),
    ("Internal low", "rows", "active_sup"), ("VAH", "rows", "vah"), ("VAL", "rows", "val"), ("POC", "rows", "vpoc"),
]


def code_hash() -> str:
    with open(os.path.abspath(__file__), "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()[:16]


def freeze_key(engine_key: str) -> str:
    return f"{engine_key}:{code_hash()}"


def _f(x) -> float:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return math.nan
    return x


def _levels(res, i: int) -> list[tuple[str, float]]:
    out = []
    for name, where, key in LEVELS:
        src = res.rows if where == "rows" else res.F
        arr = src.get(key) if hasattr(src, "get") else None
        if arr is None or i >= len(arr):
            continue
        v = _f(arr[i])
        if math.isfinite(v):
            out.append((name, v))
    return out


def playbook(res, i: int) -> dict | None:
    """The playbook at the close of bar i (it applies to bar i + 1)."""
    F = res.F
    p, a, m = _f(F["c"][i]), _f(F["aatr"][i]), _f(F["reg_sl_mult"][i])
    if not (math.isfinite(p) and math.isfinite(a) and a > 0 and math.isfinite(m)):
        return None
    d = m * a
    lv = []
    for name, v in sorted(_levels(res, i), key=lambda x: x[1]):
        if not any(abs(v - w) < MERGE_ATR * a for _, w in lv):
            lv.append((name, v))
    below = sorted([x for x in lv if x[1] < p - GAP_ATR * a], key=lambda x: -x[1])
    above = sorted([x for x in lv if x[1] > p + GAP_ATR * a], key=lambda x: x[1])

    def side(direction, lst):
        if not lst:
            return None
        tn, tv = lst[0]
        far = [x for x in lst[1:] if direction * (x[1] - tv) >= MIN_TP_R * d]
        tp1 = far[0] if far else (f"{FALLBACK_R:g}R", tv + direction * FALLBACK_R * d)
        tp2 = far[1] if len(far) > 1 else tp1
        return {"dir": direction, "trigger": tv, "tname": tn, "stop": tv - direction * d, "tp1": tp1[1], "tp1n": tp1[0],
                "tp2": tp2[1], "tp2n": tp2[0], "rr": abs(tp1[1] - tv) / d}
    return {"price": p, "atr": a, "stop_dist": d, "sell": side(-1, below), "buy": side(1, above)}


def evaluate(res) -> dict:
    n = len(res.F["c"])
    c = res.F["c"]
    nan = [math.nan] * n
    out = {"exec_buy": [0] * n, "exec_sell": [0] * n, "plan_sl": list(nan), "plan_tp1": list(nan), "plan_tp2": list(nan),
           "trigger": list(nan), "tname": [None] * n}
    for i in range(1, n):
        pb = playbook(res, i - 1)
        if pb is None or not math.isfinite(_f(c[i])):
            continue
        s, b = pb["sell"], pb["buy"]
        if s and c[i] < s["trigger"] and c[i] > s["tp1"]:
            out["exec_sell"][i] = 1
            x = s
        elif b and c[i] > b["trigger"] and c[i] < b["tp1"]:
            out["exec_buy"][i] = 1
            x = b
        else:
            continue
        out["plan_sl"][i], out["plan_tp1"][i], out["plan_tp2"][i] = x["stop"], x["tp1"], x["tp2"]
        out["trigger"][i], out["tname"][i] = x["trigger"], x["tname"]
    return out


def simulate(res, cfg) -> tuple[list[dict], dict]:
    """H4's trades under the SAME execution model and costs as the other arms."""
    ev = evaluate(res)
    n = len(res.F["c"])
    rows = {"exec_buy": ev["exec_buy"], "exec_sell": ev["exec_sell"], "plan_sl": ev["plan_sl"], "plan_tp1": ev["plan_tp1"],
            "plan_tp2": ev["plan_tp2"], "tq": [0] * n, "cal_p_long": [math.nan] * n, "cal_p_short": [math.nan] * n,
            "plan_ev": [math.nan] * n}
    return backtest.simulate(SimpleNamespace(F=res.F, rows=rows), cfg), ev
