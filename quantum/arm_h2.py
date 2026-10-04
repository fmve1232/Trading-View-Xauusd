"""Arm H2 "Sweep and Value" -- pre-registered in audit/PREREGISTRATION.md, Amendment 5.

The rules below were approved by the operator and written into the pre-registration BEFORE this
module was run on any price history. Do not change a rule, a constant or a tie-break here without
a new amendment: H2's freeze key includes the SHA-256 of this file, so any edit restarts its
forward test (the other arms are unaffected).

H2 reads only what the frozen engine already produced for the treatment arm's bars: EMA20 /
EMA100 / EMA200, ATR, session quality, the rolling 100-bar volume profile (POC / VAH / VAL),
the pool SWEEP events and the active pivot swing levels. It changes none of them. At bar i it
uses data up to and including bar i only (a test enforces this).

LONG at the close of bar i (SHORT is the exact mirror):
  1 trend         close[i] > EMA200[i] and EMA20[i] > EMA100[i]
  2 sweep         some bar j, i-3 <= j <= i, swept sell-side liquidity: the engine's bullish SWEEP
                  event, or low[j] < active_sup[j-1] and close[j] > active_sup[j-1]
  3 value         low[j] <= VAL[j]
  4 confirmation  close[i] > high[i-1]
  5 session       session_quality[i] >= 30
  one signal per sweep bar; LONG and SHORT on the same bar -> no signal; missing input -> no signal
Plan: entry close[i]; stop min(low[j..i]) - 0.1 ATR[i]; TP1 = POC if >= 1R away else entry + 1R;
TP2 = nearer of VAH / active_res above TP1, else TP1 + 1R.
"""
from __future__ import annotations

import hashlib
import math
import os
from types import SimpleNamespace

import numpy as np

from . import backtest

LOOKBACK = 3            # sweep within the last 3 bars (i-3 .. i)
STOP_ATR = 0.1          # stop buffer below the sweep low, in ATR
SESSION_MIN = 30        # the engine's own session gate
ARM = "h2"


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


def _ok(*xs) -> bool:
    return all(not math.isnan(x) for x in xs)


def sweeps(res) -> tuple[np.ndarray, np.ndarray]:
    """Per bar: did it sweep sell-side (bull) / buy-side (bear) liquidity? Rule 2."""
    F, R = res.F, res.rows
    n = len(F["c"])
    l, h, c = F["l"], F["h"], F["c"]
    sb = np.zeros(n, bool)
    ss = np.zeros(n, bool)
    for e in res.events:
        if e.get("type") == "SWEEP" and 0 <= e.get("i", -1) < n:
            if e.get("dir", 0) > 0:
                sb[e["i"]] = True
            elif e.get("dir", 0) < 0:
                ss[e["i"]] = True
    sup = np.array([_f(x) for x in R["active_sup"]])
    rs = np.array([_f(x) for x in R["active_res"]])
    for j in range(1, n):
        if not math.isnan(sup[j - 1]) and l[j] < sup[j - 1] and c[j] > sup[j - 1]:
            sb[j] = True
        if not math.isnan(rs[j - 1]) and h[j] > rs[j - 1] and c[j] < rs[j - 1]:
            ss[j] = True
    return sb, ss


def evaluate(res) -> dict:
    """Signals and plans for every bar, plus the rule checklist for the last bar."""
    F, R = res.F, res.rows
    n = len(F["c"])
    o, h, l, c = F["o"], F["h"], F["l"], F["c"]
    e20, e100, e200, atr = F["ema20"], F["ema100"], F["ema200"], F["atr"]
    sq = F["session_quality"]
    poc = np.array([_f(x) for x in R["vpoc"]])
    vah = np.array([_f(x) for x in R["vah"]])
    val = np.array([_f(x) for x in R["val"]])
    sup = np.array([_f(x) for x in R["active_sup"]])
    rs = np.array([_f(x) for x in R["active_res"]])
    sb, ss = sweeps(res)
    nan = [math.nan] * n
    out = {"exec_buy": [0] * n, "exec_sell": [0] * n, "plan_sl": list(nan), "plan_tp1": list(nan), "plan_tp2": list(nan),
           "sweep_bar": [None] * n}
    used_b, used_s = set(), set()
    checklist = None
    for i in range(1, n):
        cands = {}
        for side, swept, used in ((1, sb, used_b), (-1, ss, used_s)):
            trend = _ok(c[i], e200[i], e20[i], e100[i]) and ((c[i] > e200[i] and e20[i] > e100[i]) if side > 0
                                                              else (c[i] < e200[i] and e20[i] < e100[i]))
            js = [j for j in range(max(0, i - LOOKBACK), i + 1) if swept[j] and j not in used]
            if side > 0:
                value_js = [j for j in js if _ok(val[j]) and l[j] <= val[j]]      # rule 3: swept at or below VAL
            else:
                value_js = [j for j in js if _ok(vah[j]) and h[j] >= vah[j]]      # mirror: at or above VAH
            confirm = (c[i] > h[i - 1]) if side > 0 else (c[i] < l[i - 1])
            sess = sq[i] >= SESSION_MIN
            if i == n - 1:
                checklist = checklist or {}
                checklist["long" if side > 0 else "short"] = {
                    "trend": bool(trend), "sweep": bool(js), "value": bool(value_js), "confirmation": bool(confirm), "session": bool(sess)}
            if trend and value_js and confirm and sess:
                cands[side] = value_js[0]                          # the earliest unused qualifying sweep
        if len(cands) != 1:
            continue                                           # none, or both sides: no signal
        side, j = next(iter(cands.items()))
        a = _f(atr[i])
        if math.isnan(a):
            continue
        entry = c[i]
        if side > 0:
            stop = float(np.min(l[j:i + 1])) - STOP_ATR * a
            r = entry - stop
            if r <= 0:
                continue
            tp1 = poc[i] if (_ok(poc[i]) and poc[i] - entry >= r) else entry + r
            above = [x for x in (vah[i], rs[i]) if _ok(x) and x > tp1]
            tp2 = min(above) if above else tp1 + r
            used_b.add(j)
            out["exec_buy"][i] = 1
        else:
            stop = float(np.max(h[j:i + 1])) + STOP_ATR * a
            r = stop - entry
            if r <= 0:
                continue
            tp1 = poc[i] if (_ok(poc[i]) and entry - poc[i] >= r) else entry - r
            below = [x for x in (val[i], sup[i]) if _ok(x) and x < tp1]
            tp2 = max(below) if below else tp1 - r
            used_s.add(j)
            out["exec_sell"][i] = 1
        out["plan_sl"][i], out["plan_tp1"][i], out["plan_tp2"][i], out["sweep_bar"][i] = stop, tp1, tp2, j
    out["checklist"] = checklist
    return out


def simulate(res, cfg) -> tuple[list[dict], dict]:
    """H2's trades under the SAME execution model and costs as the other arms."""
    ev = evaluate(res)
    n = len(res.F["c"])
    rows = {"exec_buy": ev["exec_buy"], "exec_sell": ev["exec_sell"], "plan_sl": ev["plan_sl"], "plan_tp1": ev["plan_tp1"],
            "plan_tp2": ev["plan_tp2"], "tq": [0] * n, "cal_p_long": [math.nan] * n, "cal_p_short": [math.nan] * n,
            "plan_ev": [math.nan] * n}
    trades = backtest.simulate(SimpleNamespace(F=res.F, rows=rows), cfg)
    return trades, ev


def next_move_stats(trades: list[dict]) -> dict:
    """What followed past H2 signals (closed trades): TP1 first, stop first, mean R."""
    closed = [t for t in trades if not t.get("open")]
    if not closed:
        return {"n": 0}
    r = np.array([t["r"] for t in closed])
    tp1 = np.array([bool(t["tp1_hit"]) for t in closed])
    stop_first = np.array([t["exit_reason"] == "SL" for t in closed])
    return {"n": len(closed), "tp1_first_pct": float(tp1.mean() * 100), "stop_first_pct": float(stop_first.mean() * 100),
            "mean_r": float(r.mean()), "median_r": float(np.median(r)), "avg_bars": float(np.mean([t["bars"] for t in closed]))}
