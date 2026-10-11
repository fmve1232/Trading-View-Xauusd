"""Arm H3 "Sweep-to-Value" -- the TradingView line's H2 rule, pre-registered in
audit/PREREGISTRATION.md, Amendment 7 section 3.

Transcribed from reference/pine-v50/XAUUSD_Quantum_5_0_Strategy_H2.pine (H2-TREND and H2-BEGIN ... H2-END)
and written into the pre-registration BEFORE this module was run on any price history. Do not change a
rule, a constant or a tie-break here without a new amendment: H3's freeze key includes the SHA-256 of this
file, so any edit restarts its forward test (the other arms are unaffected).

H3 reads the frozen engine's outputs for the treatment arm's bars (ATR14 and the per-bar volume profile, whose
construction is the Pine block's: 100 bars, 40 bins, typical price, POC and a 70% value area) and the 1H / 4H /
1D series the engine already aligns (D-01). It changes none of them. At bar i it uses data up to and
including bar i only (a test enforces this).

LONG at the close of bar i (SHORT is the exact mirror):
  trend   at least 2 of the 1H / 4H / 1D scores >= 60 (score = 40 [c1 > EMA200] + 40 [EMA20 > EMA100]
          + 20 [c1 > EMA20], on the last completed bar of that timeframe; missing -> 50)
  sweep   low[i] < swing low and close[i] > swing low; the swing low is the last 5-bar pivot low not yet
          traded through, as it stood before bar i
  value   close[i] <= POC[i]
  risk    R = close - (low - 0.15 ATR), 0.5 ATR <= R <= 5 ATR
Plan: entry close; stop entry - R; TP1 = max(POC, entry + R); TP2 = max(VAH, entry + 2R).
"""
from __future__ import annotations

import hashlib
import math
import os
from types import SimpleNamespace

import numpy as np

from . import backtest, ta
from .data.market import align, htf_expr

PIVOT = 5               # ta.pivothigh / ta.pivotlow (high/low, 5, 5)
STOP_ATR = 0.15         # the engine's buffer beyond the sweep wick
R_MIN_ATR, R_MAX_ATR = 0.5, 5.0
HTF_KEYS = ("60", "240", "D")
ARM = "h3"


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


def htf_scores(market, n: int) -> dict:
    """The 40/40/20 trend score on the last completed 1H / 4H / 1D bar, for every chart bar."""
    out = {}
    for key in HTF_KEYS:
        df = market.htf.get(key)
        if df is None or len(df) == 0:
            out[key] = np.full(n, 50.0)
            continue
        al = align(market.close_times, htf_expr(df), ["c1", "e20", "e100", "e200"])
        hc, e20, e100, e200 = al["c1"], al["e20"], al["e100"], al["e200"]
        sc = (((~np.isnan(e200)) & (hc > e200)) * 40 + ((~np.isnan(e20)) & (~np.isnan(e100)) & (e20 > e100)) * 40
              + ((~np.isnan(e20)) & (hc > e20)) * 20)
        out[key] = np.where(np.isnan(hc), 50.0, sc.astype(float))
    return out


def evaluate(res, market) -> dict:
    """Signals and plans for every bar, plus the rule checklist for the last bar."""
    F, R = res.F, res.rows
    n = len(F["c"])
    h, l, c, atr = F["h"], F["l"], F["c"], F["atr"]
    poc = np.array([_f(x) for x in R["vpoc"]])
    vah = np.array([_f(x) for x in R["vah"]])
    val = np.array([_f(x) for x in R["val"]])
    sc = htf_scores(market, n)
    up_n = sum((sc[k] >= 60).astype(int) for k in HTF_KEYS)
    dn_n = sum((sc[k] <= 40).astype(int) for k in HTF_KEYS)
    ph, pl = ta.pivothigh(h, PIVOT, PIVOT), ta.pivotlow(l, PIVOT, PIVOT)
    nan = [math.nan] * n
    out = {"exec_buy": [0] * n, "exec_sell": [0] * n, "plan_sl": list(nan), "plan_tp1": list(nan), "plan_tp2": list(nan),
           "swept": list(nan)}
    sw_h = sw_l = math.nan
    checklist = None
    for i in range(n):
        a = _f(atr[i])
        # sweep against the swing as it stood before this bar (Pine: evaluated before the updates below)
        sweep_l = not math.isnan(sw_l) and l[i] < sw_l and c[i] > sw_l
        sweep_h = not math.isnan(sw_h) and h[i] > sw_h and c[i] < sw_h
        lvl_l, lvl_h = sw_l, sw_h
        if not math.isnan(sw_l) and l[i] < sw_l:
            sw_l = math.nan                                  # traded through: consumed
        if not math.isnan(sw_h) and h[i] > sw_h:
            sw_h = math.nan
        if not math.isnan(pl[i]):
            sw_l = float(pl[i])                              # a newly confirmed pivot replaces it
        if not math.isnan(ph[i]):
            sw_h = float(ph[i])
        trend_up, trend_dn = up_n[i] >= 2, dn_n[i] >= 2
        rl = c[i] - (l[i] - STOP_ATR * a) if sweep_l else math.nan
        rs = (h[i] + STOP_ATR * a) - c[i] if sweep_h else math.nan
        ok_poc = not math.isnan(poc[i])
        risk_l = not math.isnan(rl) and R_MIN_ATR * a <= rl <= R_MAX_ATR * a
        risk_s = not math.isnan(rs) and R_MIN_ATR * a <= rs <= R_MAX_ATR * a
        long_ = sweep_l and trend_up and ok_poc and c[i] <= poc[i] and risk_l
        short_ = sweep_h and trend_dn and ok_poc and c[i] >= poc[i] and risk_s
        if i == n - 1:
            checklist = {
                "long": {"trend": bool(trend_up), "swing": not math.isnan(lvl_l), "sweep": bool(sweep_l),
                         "value": bool(ok_poc and c[i] <= poc[i]), "risk": bool(risk_l)},
                "short": {"trend": bool(trend_dn), "swing": not math.isnan(lvl_h), "sweep": bool(sweep_h),
                          "value": bool(ok_poc and c[i] >= poc[i]), "risk": bool(risk_s)},
                "scores": {k: float(sc[k][i]) for k in HTF_KEYS}, "swing_low": None if math.isnan(sw_l) else sw_l,
                "swing_high": None if math.isnan(sw_h) else sw_h}
        if long_:
            r = rl
            out["exec_buy"][i] = 1
            out["plan_sl"][i], out["plan_tp1"][i] = c[i] - r, max(poc[i], c[i] + r)
            out["plan_tp2"][i] = max(vah[i], c[i] + 2.0 * r) if not math.isnan(vah[i]) else c[i] + 2.0 * r
            out["swept"][i] = lvl_l
        elif short_:
            r = rs
            out["exec_sell"][i] = 1
            out["plan_sl"][i], out["plan_tp1"][i] = c[i] + r, min(poc[i], c[i] - r)
            out["plan_tp2"][i] = min(val[i], c[i] - 2.0 * r) if not math.isnan(val[i]) else c[i] - 2.0 * r
            out["swept"][i] = lvl_h
    out["checklist"] = checklist
    return out


def simulate(res, market, cfg) -> tuple[list[dict], dict]:
    """H3's trades under the SAME execution model and costs as the other arms."""
    ev = evaluate(res, market)
    n = len(res.F["c"])
    rows = {"exec_buy": ev["exec_buy"], "exec_sell": ev["exec_sell"], "plan_sl": ev["plan_sl"], "plan_tp1": ev["plan_tp1"],
            "plan_tp2": ev["plan_tp2"], "tq": [0] * n, "cal_p_long": [math.nan] * n, "cal_p_short": [math.nan] * n,
            "plan_ev": [math.nan] * n}
    trades = backtest.simulate(SimpleNamespace(F=res.F, rows=rows), cfg)
    return trades, ev
