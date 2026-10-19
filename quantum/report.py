"""Turn engine results into the JSON the website renders. Pure presentation: no decision is
made here that the engine did not already make."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone

import numpy as np

import pandas as pd

from . import arm_h2, arm_h3, arm_h4, backtest, holdout, ta
from .config import ENGINE_VERSION, SCHEMA_BUILD

CHART_BARS = 1500


def _f(x, nd=2):
    if x is None:
        return None
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return x
    if math.isnan(xf) or math.isinf(xf):
        return None
    return round(xf, nd)


def _arr(a, nd=2, start=0):
    return [_f(x, nd) for x in np.asarray(a, dtype=float)[start:]]


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return _f(o, 4)
    return o


def kelly(last: dict, cfg, N: int, reg_mult: float = 1.0) -> dict:
    """Dashboard Kelly sizing (v16 form: binary Kelly on P conditional on resolution, Wilson
    95% lower bound at effective N, half-Kelly, tail and drawdown haircuts), then the regime size
    haircut `regSizeMult` (0.5 abnormal, 0.75 at ATR percentile >= 80; Pine v32 L5500 on the risk %,
    and since the Pine line's v46 F-A52 on the $ and lots too). The website had left it out."""
    a = last["analog"]
    k = cfg.risk_percent
    detail = "risk % (no ROLL history yet)"
    if cfg.show_stats_engine and last["oos_neff"] >= 10 and a.get("oos_wr") is not None and a.get("avg_l", 0) > 0:
        br = (last["oos_bear_wr"] if not _isnan(last["oos_bear_wr"]) else 100.0 - a["oos_wr"]) / 100.0
        p_win = a["oos_wr"] / 100.0 if last["plan"]["long"] else br
        p_res = a["oos_wr"] / 100.0 + br
        n_eff = max(a["oos_n"] * p_res / N, 1.0)
        p_hat = p_win / p_res if p_res > 0 else 0.5
        z = 1.96
        den = 1.0 + z * z / n_eff
        ctr = (p_hat + z * z / (2 * n_eff)) / den
        hw = z * math.sqrt(p_hat * (1 - p_hat) / n_eff + z * z / (4 * n_eff * n_eff)) / den
        p = max(ctr - hw, 0.01)
        aw = a["avg_w_oos"] if a["avg_w_oos"] > 0 else a["avg_w"]
        al = a["avg_l_oos"] if a["avg_l_oos"] > 0 else a["avg_l"]
        b = aw / max(abs(al), 0.01)
        raw = (p * b - (1 - p)) / b * 100.0
        k = min(cfg.risk_percent, max(0.0, raw * 0.5))
        detail = f"p_lb={p:.2f} b={b:.2f} raw={raw:.2f}%"
        sk, ku = last.get("ret_skew"), last.get("ret_kurt")
        if sk is not None and sk < -0.5:
            k *= 0.85
        if ku is not None and ku > 1.0:
            k *= 0.75
        md = a.get("max_dd") or 0.0
        if md >= 30:
            k = 0.0
        elif md >= 20:
            k *= 0.5
        elif md >= 10:
            k *= 0.75
    if not _isnan(reg_mult) and reg_mult != 1.0:
        k *= reg_mult
        detail += f" × regime {reg_mult:g}"
    risk_usd = cfg.account_size * max(k, 0.0) / 100.0
    dist = last["plan"]["dist"]
    raw_lots = risk_usd / (dist * cfg.point_value) if dist > 0 and cfg.point_value > 0 else 0.0
    floored = math.floor(raw_lots / 0.01) * 0.01
    return {"kelly_pct": k, "detail": detail, "reg_size_mult": reg_mult, "risk_usd": risk_usd, "lots": min(max(floored, 0.0), 100.0),
            "below_min": raw_lots > 0 and floored < 0.01, "raw_lots": raw_lots}


GATE_ORDER = ("Trend", "HTF", "Recent", "Sess", "News", "DD", "Trig")


def gate_sides(L: dict, F: dict, i: int) -> dict | None:
    """Both sides' entry gates on the last bar (display only), rebuilt from what the engine published.
    The engine logs one side, chosen by its bias step, while its WAIT reason follows the final scores, so the
    two can describe different sides. Returned only when the rebuild equals the engine's own log for the
    side it wrote; otherwise None and the site shows the log alone."""
    m = re.match(r"^([\u25b2\u25bc])\d/7(?: \[\u2717([^\]]*)\])?", str(L.get("decision_log") or ""))
    if not m:
        return None
    logged = sorted({"HTF" if x.startswith("HTF") else x for x in (m.group(2) or "").split()}, key=GATE_ORDER.index)
    common = [k for k in ("Recent", "News", "DD") if k in logged]            # the same for both sides
    s, sq = L.get("struct") or {}, float(F["session_quality"][i])
    sides = {}
    for side, trend, opp_htf, trig in (("long", F["bull_trend"][i], F["htf_bear_gate"][i], s.get("bull_act") or s.get("disp_up")),
                                       ("short", F["bear_trend"][i], F["htf_bull_gate"][i], s.get("bear_act") or s.get("disp_dn"))):
        fails = [k for k, ok in (("Trend", bool(trend)), ("HTF", not bool(opp_htf)), ("Sess", sq >= 30), ("Trig", bool(trig))) if not ok]
        sides[side] = sorted(fails + common, key=GATE_ORDER.index)
    side = "long" if m.group(1) == "\u25b2" else "short"
    return {**sides, "logged": side} if sides[side] == logged else None


HTF_SEC = {"5": 300, "15": 900, "60": 3600, "240": 14400, "D": 86400}


def gold_arrows(L: dict, F: dict, i: int, tf_sec: int) -> list[dict]:
    """The Pine v53-v73 GOLD ARROWS grid (Brief `f_brGrid`), display only: each indicator's state as what it means FOR
    GOLD. d > 0 supports gold up (2 = strong), d < 0 down, 0 neutral, None no data. Macro cells are the impact on gold,
    scaled by |avg corr| (> 0.5 strong, > 0.25 moderate, else neutral), as the Master's arrows (F-A54)."""
    def s(up, dn):
        return 1 if up else -1 if dn else 0

    def mag(valid, up, dn, r):
        if not valid:
            return None
        r = abs(float(r)) if r is not None and math.isfinite(float(r)) else 0.0
        return s(up, dn) * (2 if r > 0.5 else 1 if r > 0.25 else 0)

    def mv(valid, rise, fall):
        return "no data" if not valid else "rising" if rise else "falling" if fall else "flat"

    ev, st, fl, mt = L.get("evidence") or {}, L.get("struct") or {}, L.get("flow") or {}, L.get("mtf") or {}
    c = float(F["c"][i]); b, br = float(L["bull_score"]), float(L["bear_score"])
    e200, vw = float(F["ema200"][i]), float(F["vwap"][i])
    vah, val = fl.get("vah"), fl.get("val")
    g = lambda k: bool(F[k][i])                                                       # noqa: E731
    ac = lambda k: F["avg_corr"][k][i]                                                 # noqa: E731
    STRUCT = {"BOS": "break of structure", "CHoCH": "change of character", "MSS": "structure shift"}
    stype = st.get("bull_type") if st.get("bull_act") else st.get("bear_type") if st.get("bear_act") else None
    lb, ls_ = ev.get("liq_bull", 0), ev.get("liq_bear", 0)
    cells = [
        ("TREND", s(ev.get("bull_trend"), ev.get("bear_trend")),
         "uptrend" if ev.get("bull_trend") else "downtrend" if ev.get("bear_trend") else "no clear trend"),
        ("STRUCT", s(st.get("bull_act"), st.get("bear_act")),
         f"{'bullish' if st.get('bull_act') else 'bearish'} {STRUCT.get(stype, stype)} ({stype})" if stype else "no active break"),
        ("BIAS", 0 if abs(b - br) < 5 else s(b > br, br > b), f"long {b:.0f} vs short {br:.0f}"),
        ("LIQ", s(lb > ls_ + 3, ls_ > lb + 3), "pull toward the highs" if lb > ls_ + 3 else "pull toward the lows" if ls_ > lb + 3 else "balanced"),
        ("EMA200", s(c > e200, c < e200), "price above it" if c > e200 else "price below it"),
        ("VWAP", s(c > vw, c < vw), "price above it" if c > vw else "price below it"),
        ("VALUE", s(vah is not None and c > vah, val is not None and c < val),
         "above the value area" if vah is not None and c > vah else "below the value area" if val is not None and c < val else "inside the value area"),
        ("MTF", s(mt.get("conf_score", 0) > 20, mt.get("conf_score", 0) < -20), f"agreement {mt.get('conf_score', 0):+d}"),
    ]
    for k, nm in (("5", "5M"), ("15", "15M"), ("60", "1H"), ("240", "4H"), ("D", "1D")):
        live = tf_sec < HTF_SEC[k]                                                      # F-A63: a layer votes only above the chart
        sc_ = F["htf_scores"][k][i]
        cells.append((nm, s(bool(F["htf_bull"][k][i]), bool(F["htf_bear"][k][i])) if live else None,
                      (f"{'uptrend' if sc_ >= 60 else 'downtrend' if sc_ <= 40 else 'mixed'} ({sc_:.0f}/100)") if live else "no data on this TF"))
    cells += [
        ("CVD", s(fl.get("cvd_bull"), ev.get("cvd_bear")),
         "buyers stronger" if fl.get("cvd_bull") else "sellers stronger" if ev.get("cvd_bear") else "balanced"),
        ("DISPL", s(st.get("disp_up"), st.get("disp_dn")),
         "strong up candle" if st.get("disp_up") else "strong down candle" if st.get("disp_dn") else "none"),
        # the engine sets both flags True when its RSI-divergence filter is off (the default): that is no divergence
        ("RSI DIV", s(ev.get("rsi_div_bull"), ev.get("rsi_div_bear")) if ev.get("rsi_div_filter") else None,
         "divergence" if ev.get("rsi_div_filter") else "filter off (engine default)"),
        ("DXY", mag(g("dxy_valid"), g("dxy_bear"), g("dxy_bull"), ac("DXY")), "dollar " + mv(g("dxy_valid"), g("dxy_bull"), g("dxy_bear"))),
        ("10Y", mag(g("yld_valid"), g("yld_falling"), g("yld_rising"), ac("Yld")), "yields " + mv(g("yld_valid"), g("yld_rising"), g("yld_falling"))),
        ("TIPS", mag(g("tips_valid"), g("tips_falling"), g("tips_rising"), ac("TIPS")),
         ("real yield " + mv(g("tips_valid"), g("tips_rising"), g("tips_falling"))) if F.get("tips_on", True) else "off: same feed as 10Y"),
        ("EUR", mag(g("eur_valid"), g("eur_bull"), g("eur_bear"), ac("EUR")),
         "EURUSD " + mv(g("eur_valid"), g("eur_bull"), g("eur_bear")) + (" · confirms DXY" if g("dxy_valid") else " · USD vote")),
        ("XAG", mag(g("slv_valid"), g("slv_bull"), g("slv_bear"), ac("Slv")), "silver " + mv(g("slv_valid"), g("slv_bull"), g("slv_bear"))),
        ("SPX", s(g("spx_bull"), g("spx_bear")) if g("spx_valid") else None, "stocks " + mv(g("spx_valid"), g("spx_bull"), g("spx_bear"))),
        ("MACRO", s(F["macro_strength"][i] >= 15, F["macro_strength"][i] <= -15), f"score {F['macro_strength'][i]:+.0f} (±15 = a side)"),
    ]
    out = [{"name": n_, "d": d, "text": t} for n_, d, t in cells]
    cu, cd = bool(fl.get("climax_up")), bool(fl.get("climax_dn"))   # exhaustion either way: amber, not a side
    out.append({"name": "CLIMAX", "d": None, "amber": cu or cd, "glyph": "▲" if cu else "▼" if cd else "·",
                "text": ("buying" if cu else "selling") + " climax" if cu or cd else "none"})
    return out


def _isnan(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


def sr_scanner(F, scan_len=100, max_sr=6):
    """Visuals `scanSRLevels`: fractal highs/lows clustered within max(0.4 ATR, 0.03%)."""
    h, l, atr = F["h"], F["l"], F["atr"]
    n = len(h)
    if n < scan_len + 3:
        return {"res": [], "sup": []}
    a = atr[-1]
    res, sup = [], []
    for side, src in (("res", h), ("sup", l)):
        levels, strength = [], []
        for k in range(1, scan_len + 1):
            j = n - 1 - k
            if j - 1 < 0:
                break
            x, xn, xp = src[j], src[j - 1], src[j + 1]
            is_f = (x > xn and x >= xp) if side == "res" else (x < xn and x <= xp)
            if not is_f:
                continue
            thr = max(a * 0.4, x * 0.0003) / max(x, 1.0)
            hit = False
            for q, lev in enumerate(levels):
                if abs(lev - x) / lev < thr:
                    strength[q] += 1
                    hit = True
                    break
            if not hit and len(levels) < max_sr:
                levels.append(float(x))
                strength.append(1)
        (res if side == "res" else sup).extend({"price": _f(p), "touches": s} for p, s in zip(levels, strength))
    return {"res": res, "sup": sup}


H2_RULES = [   # [key, long wording, short wording] -- display text for the rules in arm_h2.py
    ["trend", "Trend: close above EMA200 and EMA20 above EMA100", "Trend: close below EMA200 and EMA20 below EMA100"],
    ["sweep", "Liquidity sweep in the last 3 bars: wick below PDL/PWL/PML or the swing low, close back above it",
              "Liquidity sweep in the last 3 bars: wick above PDH/PWH/PMH or the swing high, close back below it"],
    ["value", "The sweep reached the value-area low (VAL) or lower", "The sweep reached the value-area high (VAH) or higher"],
    ["confirmation", "Confirmation: close above the previous bar's high", "Confirmation: close below the previous bar's low"],
    ["session", "Active session (London / New York)", "Active session (London / New York)"],
]


H3_RULES = [   # [key, long wording, short wording] -- display text for the rules in arm_h3.py (Amendment 7)
    ["trend", "Trend: at least 2 of 1H / 4H / 1D up (score >= 60 on the last completed bar)",
              "Trend: at least 2 of 1H / 4H / 1D down (score <= 40 on the last completed bar)"],
    ["swing", "An untouched 5-bar swing low is waiting below", "An untouched 5-bar swing high is waiting above"],
    ["sweep", "This bar wicked below that swing low and closed back above it", "This bar wicked above that swing high and closed back below it"],
    ["value", "Close at or below the volume POC (discount)", "Close at or above the volume POC (premium)"],
    ["risk", "Stop 0.15 ATR beyond the wick is 0.5 to 5 ATR away", "Stop 0.15 ATR beyond the wick is 0.5 to 5 ATR away"],
]


def _arm_record(arm, key, market, trades, cfg, now, store_dir):
    """Freeze manifest + append-only ledger for a separately registered arm; returns (manifest, pre, post)."""
    if market.synthetic:
        man2 = {"arm": arm, "freeze_key": key, "freeze_utc": now.isoformat(), "status": "SYNTHETIC"}
        post = holdout.split(trades, man2["freeze_utc"])[1]
    else:
        man2 = holdout.load_or_freeze_arm(store_dir, arm, key, now)
        post = holdout.update_ledger(store_dir, market.tf, arm, trades, man2["freeze_utc"], key, market.price_source)
    pre, _ = holdout.split(trades, man2["freeze_utc"])
    return man2, pre, post


STALE_BARS = 24   # Pine v76 "Mark the last H2 signal stale after (bars)" default; display only


def signal_status(F: dict, i0: int, plan: dict, trend_ok: bool, stale_bars: int = STALE_BARS) -> dict:
    """The last signal's age, outcome and LIVE / STALE (Pine v76, display only; the arm's rule is untouched).
    Each confirmed bar after the signal is checked against the signal's own stop, TP1 and TP2; a bar that touches the
    stop and a target counts the stop first (the order inside a bar is unknown, so this is the conservative reading).
    STALE = the trade is over (stopped, TP2, or TP1 then stop), older than `stale_bars`, or the arm's trend vote no
    longer agrees with the signal's direction."""
    n = len(F["c"])
    long_ = plan["dir"] == "LONG"
    sl, t1, t2 = plan.get("sl"), plan.get("tp1"), plan.get("tp2")
    out, tp1_hit = "open", False
    if None not in (sl, t1, t2):
        for j in range(i0 + 1, n):
            hi, lo = float(F["h"][j]), float(F["l"][j])
            stop = lo <= sl if long_ else hi >= sl
            r1 = hi >= t1 if long_ else lo <= t1
            r2 = hi >= t2 if long_ else lo <= t2
            if stop:
                out = "TP1 hit, then stop" if tp1_hit else "stopped"
                break
            if r2:
                out = "TP2 hit"
                break
            if r1 and not tp1_hit:
                tp1_hit, out = True, "TP1 hit"
    closed = out in ("stopped", "TP2 hit", "TP1 hit, then stop")
    bars = n - 1 - i0
    why = [x for x, on in (("trade over", closed), (f"older than {stale_bars} bars", bars > stale_bars),
                          ("trend no longer agrees", not trend_ok)) if on]
    return {"bars": bars, "outcome": out, "closed": closed, "trend_ok": bool(trend_ok), "stale": bool(why), "why": why,
            "stale_bars": stale_bars}


def _with_status(F, i0, p, checklist):
    side = "long" if p["dir"] == "LONG" else "short"
    return {**p, "status": signal_status(F, i0, p, bool((checklist.get(side) or {}).get("trend")))}


def h3_section(market, res, cfg, man, now, store_dir, idx) -> dict:
    trades, ev = arm_h3.simulate(res, market, cfg)
    key = arm_h3.freeze_key(man.get("freeze_key") or holdout.freeze_key(cfg))
    man3, pre, post = _arm_record("h3", key, market, trades, cfg, now, store_dir)
    n = len(idx)
    sig = [i for i in range(n) if ev["exec_buy"][i] or ev["exec_sell"][i]]

    def plan(i):
        return {"t": int(pd.Timestamp(idx[i]).timestamp()), "iso": idx[i].isoformat(), "dir": "LONG" if ev["exec_buy"][i] else "SHORT",
                "entry": _f(res.F["c"][i]), "sl": _f(ev["plan_sl"][i]), "tp1": _f(ev["plan_tp1"][i]), "tp2": _f(ev["plan_tp2"][i]),
                "swept": _f(ev["swept"][i])}
    return {"rules": H3_RULES, "freeze": man3, "checklist": ev["checklist"],
            "signal_now": plan(n - 1) if sig and sig[-1] == n - 1 else None,
            "last_signal": _with_status(res.F, sig[-1], plan(sig[-1]), ev["checklist"]) if sig else None, "signals": [plan(i) for i in sig[-200:]],
            "open": [t for t in trades if t.get("open")],
            "next_move_in_sample": arm_h2.next_move_stats(pre),
            "in_sample": backtest.metrics(pre, cfg.risk_percent), "forward": backtest.metrics(post, cfg.risk_percent),
            "forward_trades": post[-100:], "signals_per_bar": len(sig) / n if n else None}


def h4_section(market, res, cfg, man, now, store_dir, idx) -> dict:
    """Arm H4 "Playbook" (Amendment 8): the site's playbook for the next bar, and its measured record."""
    trades, ev = arm_h4.simulate(res, cfg)
    key = arm_h4.freeze_key(man.get("freeze_key") or holdout.freeze_key(cfg))
    man4, pre, post = _arm_record("h4", key, market, trades, cfg, now, store_dir)
    n = len(idx)
    sig = [i for i in range(n) if ev["exec_buy"][i] or ev["exec_sell"][i]]

    def plan(i):
        return {"t": int(pd.Timestamp(idx[i]).timestamp()), "dir": "LONG" if ev["exec_buy"][i] else "SHORT", "entry": _f(res.F["c"][i]),
                "sl": _f(ev["plan_sl"][i]), "tp1": _f(ev["plan_tp1"][i]), "tp2": _f(ev["plan_tp2"][i]),
                "trigger": _f(ev["trigger"][i]), "tname": ev["tname"][i]}
    return {"playbook": arm_h4.playbook(res, n - 1), "freeze": man4,
            "signal_now": plan(n - 1) if sig and sig[-1] == n - 1 else None, "last_signal": plan(sig[-1]) if sig else None,
            "signals": [plan(i) for i in sig[-200:]], "open": [t for t in trades if t.get("open")],
            "in_sample": backtest.metrics(pre, cfg.risk_percent), "forward": backtest.metrics(post, cfg.risk_percent),
            "forward_trades": post[-100:], "signals_per_bar": len(sig) / n if n else None}


def h2_section(market, res, cfg, man, now, store_dir, idx) -> dict:
    trades, ev = arm_h2.simulate(res, cfg)
    key = arm_h2.freeze_key(man.get("freeze_key") or holdout.freeze_key(cfg))
    if market.synthetic:
        man2 = {"arm": "h2", "freeze_key": key, "freeze_utc": now.isoformat(), "status": "SYNTHETIC"}
        post = holdout.split(trades, man2["freeze_utc"])[1]
    else:
        man2 = holdout.load_or_freeze_arm(store_dir, "h2", key, now)
        post = holdout.update_ledger(store_dir, market.tf, "h2", trades, man2["freeze_utc"], key, market.price_source)
    pre, _ = holdout.split(trades, man2["freeze_utc"])
    n = len(idx)
    sig = [i for i in range(n) if ev["exec_buy"][i] or ev["exec_sell"][i]]
    def plan(i):
        return {"t": int(pd.Timestamp(idx[i]).timestamp()), "iso": idx[i].isoformat(), "dir": "LONG" if ev["exec_buy"][i] else "SHORT",
                "entry": _f(res.F["c"][i]), "sl": _f(ev["plan_sl"][i]), "tp1": _f(ev["plan_tp1"][i]), "tp2": _f(ev["plan_tp2"][i]),
                "sweep_t": int(pd.Timestamp(idx[ev["sweep_bar"][i]]).timestamp())}
    return {"rules": H2_RULES, "freeze": man2, "checklist": ev["checklist"],
            "signal_now": plan(n - 1) if sig and sig[-1] == n - 1 else None,
            "last_signal": _with_status(res.F, sig[-1], plan(sig[-1]), ev["checklist"]) if sig else None, "signals": [plan(i) for i in sig[-200:]],
            "open": [t for t in trades if t.get("open")],
            "next_move_in_sample": arm_h2.next_move_stats(pre),
            "in_sample": backtest.metrics(pre, cfg.risk_percent), "forward": backtest.metrics(post, cfg.risk_percent),
            "forward_trades": post[-100:], "signals_per_bar": len(sig) / n if n else None}


def build(market, res, res_ctrl, cfg, man: dict, now: datetime | None = None, store_dir: str | None = None,
          res_chal=None) -> dict:
    now = now or datetime.now(timezone.utc)
    F, R, L = res.F, res.rows, res.last
    n = F["n"]
    idx = F["index"]
    s = max(0, n - CHART_BARS)
    ep = ta.epoch_s(idx)
    t = ep[s:].tolist()
    N = res.outcome_n
    L["ret_skew"] = float(F["ret_skew"][-1])
    L["ret_kurt"] = float(F["ret_kurt"][-1])
    ks = kelly(L, cfg, N, float(F["reg_size_mult"][-1]))
    i = n - 1

    chart = {
        "t": t, "o": _arr(F["o"], 2, s), "h": _arr(F["h"], 2, s), "l": _arr(F["l"], 2, s), "c": _arr(F["c"], 2, s),
        "v": _arr(F["v"], 0, s), "ema20": _arr(F["ema20"], 2, s), "ema100": _arr(F["ema100"], 2, s),
        "ema200": _arr(F["ema200"], 2, s), "vwap": _arr(F["vwap"], 2, s), "wvwap": _arr(F["wvwap"], 2, s),
        "mvwap": _arr(F["mvwap"], 2, s), "bb_up": _arr(F["bb_basis"] + F["bb_dev"], 2, s),
        "bb_lo": _arr(F["bb_basis"] - F["bb_dev"], 2, s), "bb_mid": _arr(F["bb_basis"], 2, s),
        "bull": _arr(R["bull"], 1, s), "bear": _arr(R["bear"], 1, s), "range": _arr(R["range"], 1, s),
        "tq": _arr(R["tq"], 0, s), "conf": _arr(R["conf"], 0, s), "pdh": _arr(R["pdh"], 2, s), "pdl": _arr(R["pdl"], 2, s),
        "pwh": _arr(R["pwh"], 2, s), "pwl": _arr(R["pwl"], 2, s), "vpoc": _arr(R["vpoc"], 2, s),
        "vah": _arr(R["vah"], 2, s), "val": _arr(R["val"], 2, s), "adx": _arr(F["adx"], 1, s), "rsi": _arr(F["rsi"], 1, s),
        "session": [str(x) for x in F["session_label"][s:]],
    }
    cal = F["cal"]
    brk = {"vwap": cal["crossed_day"].to_numpy(), "wvwap": cal["crossed_week"].to_numpy(), "mvwap": cal["crossed_month"].to_numpy()}
    chart["anchor"] = {k: [int(j - s) for j in np.flatnonzero(v) if j >= s] for k, v in brk.items()}
    chart["anchor"].update({k: chart["anchor"]["vwap"] for k in ("pdh", "pdl")})
    chart["anchor"].update({k: chart["anchor"]["wvwap"] for k in ("pwh", "pwl")})
    ev_types = {"BOS", "CHoCH", "MSS", "SWEEP", "SIGNAL", "VETO", "TRACK_EXIT", "RISK_LOCK"}
    markers = []
    for e in res.events:
        if e["i"] < s or e["type"] not in ev_types:
            continue
        m = {"t": int(ep[e["i"]]), "type": e["type"], "dir": e.get("dir", 0), "px": _f(e.get("px"))}
        if e["type"] == "SIGNAL":
            m.update(tq=e["tq"], sl=_f(e["sl"]), tp1=_f(e["tp1"]), tp2=_f(e["tp2"]), tp3=_f(e["tp3"]))
        if e["type"] == "VETO":
            m["why"] = e["why"]
        if e["type"] == "TRACK_EXIT":
            m["r"] = _f(e["r"])
        markers.append(m)
    zones = []
    open_z = {}
    for e in res.events:
        if e["type"] in ("OB", "FVG"):
            key = (e["type"], e["dir"])
            z = {"type": e["type"], "dir": e["dir"], "hi": _f(e["hi"]), "lo": _f(e["lo"]),
                 "t0": int(ep[max(e["start"], 0)]), "t1": None, "failed": e.get("failed", False)}
            if key in open_z:
                open_z[key]["t1"] = z["t0"]
            open_z[key] = z
            zones.append(z)
        elif e["type"] in ("OB_END", "FVG_END"):
            key = (e["type"][:-4], e["dir"])
            if key in open_z and open_z[key]["t1"] is None:
                open_z[key]["t1"] = int(ep[e["i"]])
                del open_z[key]
    zones = [z for z in zones if (z["t1"] is None or z["t1"] >= t[0])][-60:]
    decisions = [{"t": int(ep[e["i"]]), "from": e["from"], "to": e["to"]}
                 for e in res.events if e["type"] == "DECISION"][-40:]

    def macro_row(key, fk, arrow_up, arrow_dn):
        valid = bool(F[f"{fk}_valid"][i]) if f"{fk}_valid" in F else False
        cs = F["corr"][key]
        return {"valid": valid, "value": _f(F[f"{fk}_c1"][i], 4), "ema10": _f(F[f"{fk}_e10"][i], 4), "ema20": _f(F[f"{fk}_e20"][i], 4),
                "gold_bullish": bool(arrow_up[i]), "gold_bearish": bool(arrow_dn[i]),
                "corr": [_f(cs[0][i], 3), _f(cs[1][i], 3), _f(cs[2][i], 3)], "avg_corr": _f(F["avg_corr"][key][i], 3),
                "health": _f(F["corr_health"][key][i], 1)}
    macro = {
        "DXY": macro_row("DXY", "dxy", F["dxy_bear"], F["dxy_bull"]),
        "US10Y": macro_row("Yld", "yld", F["yld_falling"], F["yld_rising"]),
        "XAG": macro_row("Slv", "slv", F["slv_bull"], F["slv_bear"]),
        "SPX": macro_row("SPX", "spx", F["spx_bull"], F["spx_bear"]),
        "EURUSD": macro_row("EUR", "eur", F["eur_bull"], F["eur_bear"]),
        "TIPS": macro_row("TIPS", "tips", F["tips_falling"], F["tips_rising"]),
        "tips_source": cfg.tips_source, "tips_on": bool(F.get("tips_on", True)),
        "dxy_rsi": _f(F["dxy_rsi"][i], 1),
        "curve_2s10s": _f(F["curve_2s10s"][i], 3), "curve_steepening": bool(F["curve_steep"][i]),
        "vix": _f(F["vix"][i], 2),
        "cot": {"valid": bool(F["cot_valid"][i]), "pct": _f(F["cot_pct"][i], 1), "crowded_long": bool(F["cot_crowd_long"][i]),
                "crowded_short": bool(F["cot_crowd_short"][i]), "gating": cfg.cot_enable, "regime": int(F["cot_regime"][i])},
        "oi": {"valid": bool(F["oi_valid"][i]), "chg_pct": _f(F["oi_chg_pct"][i], 2), "state": str(F["oi_state"][i]),
               "conviction": int(F["oi_conviction"][i]), "note": "weekly CFTC open interest (TradingView uses daily)"},
        "gc": {"enabled": bool(F["gc_enabled"]), "valid": bool(F["gc_valid"][i]), "fail": str(F["gc_fail"][i]),
               "confirms_bull": bool(F["gc_confirms_bull"][i]), "confirms_bear": bool(F["gc_confirms_bear"][i]),
               "diverges": bool(F["gc_diverges"][i]), "strong_bull": bool(F["gc_strong_bull"][i]), "strong_bear": bool(F["gc_strong_bear"][i]),
               "value": _f(F["gc_c1"][i], 2)},
        "status_line": " ".join(f"{k}:{'OK' if F[f'{k}_STATUS'][i] == 0 else 'NA'}" for k in ("GC", "OI", "US2Y", "COT")),
        "corr_sig": {str(k): _f(v, 3) for k, v in F["corr_sig"].items()},
        "avg_corr_health": _f(F["avg_corr_health"][i], 1), "avg_stability": _f(F["avg_stability"][i], 3),
    }

    # analog diagnostics (Diagnostics §3, §5)
    A = L["analog"]
    ow = A.get("oos_wr")
    o_neff = L["oos_neff"]
    wr_dir = (A["bear"] if L["bear_bias"] > L["bull_bias"] else A["wr"]) / 100.0
    diag_wr_ci = 1.96 * math.sqrt(max(wr_dir * (1 - wr_dir), 0.0) / max(A["match"] / max(N, 1), 1.0)) * 100.0 if A["match"] >= 30 else None
    diag_oos_ci = 1.96 * math.sqrt(max(ow / 100.0 * (1 - ow / 100.0), 0.0025) / max(A["oos_n"] / N, 1.0)) * 100.0 if o_neff >= 10 else None
    rel = []
    cr = L["cal_rel"]
    for k in range(5):
        rel.append({"bin": k, "n": cr[k * 3], "pred": _f(cr[k * 3 + 1], 1), "obs": _f(cr[k * 3 + 2], 1)})

    band = max(F["aatr"][i], F["atr"][i]) * 2.0
    eff_fb = max(4, int(math.floor(cfg.forecast_bars * float(F["reg_horizon_mult"][i]) + 0.5)))
    c_prev = F["c"][i - 1] if i > 0 else F["c"][i]
    cone = {"band": _f(band), "bars": eff_fb, "z": 2.0,
            "breach_up": bool(F["c"][i] > c_prev + band), "breach_dn": bool(F["c"][i] < c_prev - band),
            "upper": [_f(F["c"][i] + band * math.sqrt(k)) for k in range(1, eff_fb + 1)],
            "lower": [_f(F["c"][i] - band * math.sqrt(k)) for k in range(1, eff_fb + 1)],
            "note": "volatility envelope (Z x ATR x sqrt(bars)); it does not forecast direction"}

    # backtests
    bt = {}
    for name, rr in (("treatment", res), ("control", res_ctrl), ("challenger", res_chal)):
        if rr is None:
            continue
        trades = backtest.simulate(rr, cfg)
        pre, _ = holdout.split(trades, man["freeze_utc"])
        post = holdout.update_ledger(store_dir, market.tf, name, trades, man["freeze_utc"], man.get("freeze_key") or holdout.freeze_key(cfg), market.price_source) \
            if not market.synthetic else holdout.split(trades, man["freeze_utc"])[1]
        m_all = backtest.metrics(trades, cfg.risk_percent)
        eq = []
        acc = 0.0
        for tr in trades:
            if tr.get("open"):
                continue
            acc += tr["r"]
            eq.append({"t": tr["exit_time"], "r": round(acc, 3)})
        bt[name] = {
            "metrics": m_all, "holdout": backtest.metrics(post, cfg.risk_percent), "in_sample": backtest.metrics(pre, cfg.risk_percent),
            "walk_forward": backtest.walk_forward(trades, idx), "monte_carlo": backtest.monte_carlo(trades, risk_pct=cfg.risk_percent),
            "calibration": backtest.calibration_test(trades), "by_session": backtest.breakdown(trades, "session"),
            "by_regime": backtest.breakdown(trades, "regime"), "by_dir": backtest.breakdown(trades, "dir"),
            "equity": eq[-800:], "trades": trades[-300:], "open": [tr for tr in trades if tr.get("open")],
            "holdout_trades": post[-300:],
            "funnel": rr.last["funnel"],
        }

    # arm H2 "Sweep and Value" (pre-registered, Amendment 5): its own freeze key and ledger
    try:
        h2 = h2_section(market, res, cfg, man, now, store_dir, idx)
    except Exception as e:  # noqa: BLE001 - H2 must never break the page
        h2 = {"error": f"{type(e).__name__}: {e}"[:200]}
    # arm H4 "Playbook" (Amendment 8): the displayed playbook and its own freeze key and ledger
    try:
        h4 = h4_section(market, res, cfg, man, now, store_dir, idx)
    except Exception as e:  # noqa: BLE001 - H4 must never break the page
        h4 = {"error": f"{type(e).__name__}: {e}"[:200]}
    # arm H3 "Sweep-to-Value" (the Pine line's H2 rule, Amendment 7): its own freeze key and ledger
    try:
        h3 = h3_section(market, res, cfg, man, now, store_dir, idx)
    except Exception as e:  # noqa: BLE001 - H3 must never break the page
        h3 = {"error": f"{type(e).__name__}: {e}"[:200]}

    forming = None
    if market.forming is not None:
        fb = market.forming
        forming = {"t": int(pd.Timestamp(fb.name).timestamp()), "o": _f(fb["open"]), "h": _f(fb["high"]), "l": _f(fb["low"]), "c": _f(fb["close"])}
    last_open = idx[-1]
    last_close = last_open + np.timedelta64(market.tf_sec, "s")
    plan = L["plan"]
    payload = {
        "meta": {
            "tf": market.tf, "tf_sec": market.tf_sec, "generated_utc": now.isoformat(), "engine_version": ENGINE_VERSION,
            "schema_build": SCHEMA_BUILD, "config_hash": cfg.hash(), "price_source": market.price_source,
            "volume_source": market.volume_source, "synthetic": market.synthetic, "bars": n,
            "first_bar": idx[0].isoformat(), "last_bar_open": last_open.isoformat(), "last_bar_close": last_close.isoformat(),
            "outcome_n": N, "hist_max": res.hist_max, "vol_imputed_bars": F["vol_imputed"],
            "forming": forming, "config": cfg.to_dict(),
        },
        "data_status": [st.to_dict() for st in market.status.values()],
        "holdout": {k: man.get(k) for k in ("freeze_key", "config_hash", "engine_code_hash", "engine_version", "freeze_utc", "status", "history")},
        "chart": chart, "markers": markers, "zones": zones, "sr": sr_scanner(F), "decisions": decisions, "cone": cone,
        "dashboard": {**{k: v for k, v in L.items() if k not in ("analog", "plan")}, "plan": plan, "kelly": ks,
                      "gate_sides": gate_sides(L, F, n - 1), "gold_arrows": gold_arrows(L, F, n - 1, market.tf_sec)},
        "analog": {**A, "scan": L["analog_scan"], "hit_prob": L["hit_prob"], "hit_n": L["hit_n"],
                   "race_prob": L["race_prob"], "race_n": L["race_n"], "reliability": rel, "base_rate": _f(cr[15], 1),
                   "wr_ci": _f(diag_wr_ci, 1), "oos_ci": _f(diag_oos_ci, 1), "cal_q": L["cal_q"]},
        "macro": macro,
        "backtest": bt,
        "h2": h2,
        "h3": h3,
        "h4": h4,
    }
    return _clean(payload)
