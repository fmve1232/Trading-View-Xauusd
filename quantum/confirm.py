"""High-confidence confirmation panel: data-quality checks and the nine-layer trade approval (display only).

Operator brief "XAUUSD QUANTUM - HIGH-CONFIDENCE TRADE CONFIRMATION ENGINE", Step A (approved 2026-11-01).
Not in holdout.ENGINE_SOURCES and not in any arm's code hash: it reads the frozen engine's last bar, the stored
bars and the "Your trade" measurements, and changes no signal, plan or ledger. site/costs.js mirrors `approve`
(QCosts.hcApprove) for the viewer's custom profile; tests/test_confirm.py checks that both give the same result.

THE RULES (fixed a priori; none was fitted to outcomes):
  L1 Data quality       rejects: synthetic data, a futures fallback (a different instrument), duplicate or
                        out-of-order bars, zero / invalid prices, a bar that has not closed yet, missing bars among
                        the last 20, data more than 2 bars old while the market is open, the market shut
  L2 Market regime      warns only: no regime showed an edge (B1 volatility terciles, B3 trend filter)
  L3 Directional        WAIT when the engine has no BUY / SELL on the last closed bar; a 4H + 1H conflict
                        warns only (B3: trend alignment did not raise TP-first rates)
  L4 Entry quality      rejects a late entry: the measured rates assume entry at the signal bar's close
  L5 Target feasibility warns when the nearest opposing level lies before the TP (its value is unmeasured;
                        Step B tests it as a model feature)
  L6 Probability        requires a TP-first model validated out of sample; none exists yet -> MODEL NOT
                        VALIDATED. Once one exists: INSUFFICIENT EVIDENCE below 184 comparable cases (the
                        precision of a 90% claim with an 85% lower bound, research/09 section 4); otherwise the
                        Wilson 95% lower bound must clear both the break-even and the operator's 90% target
  L7 Execution          rejects inside a high-impact news window (official NFP / CPI / FOMC list, plus the weekly
                        feed on the site) and when costs exceed 25% of 1 ATR (the Pine Visuals red threshold)
  L8 Risk               rejects under the engine's risk lock, or when the risk state is unavailable
  L9 Final              CONFIRMED BUY / SELL only when every layer passes; otherwise WAIT FOR CONFIRMATION,
                        NO TRADE, DATA UNAVAILABLE, MODEL NOT VALIDATED or INSUFFICIENT EVIDENCE
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import contract, news_calendar, ta
from .data import sources

TARGET = 0.90
MIN_EVIDENCE_N = 184
COST_RED_PCT = 25.0
STALE_BARS = 2
RECENT_BARS = 20
SCAN_BARS = 300
PROFILES = {"A": {"tp": 10.0, "sl": 10.0}, "B": {"tp": 15.0, "sl": 10.0}, "C": {"tp": 20.0, "sl": 10.0}}
MODEL = {"validated": False, "name": None,
         "note": "No TP-first model has passed out-of-sample validation yet (Step B builds it on development data; "
                 "Step C validates it once on sealed data). Until then no trade can be CONFIRMED."}


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n <= 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(max(p * (1 - p) / n + z * z / (4 * n * n), 0.0)) / d
    return (max(0.0, c - h), min(1.0, c + h))


# ---------------- L1: data quality ----------------
def data_quality(market, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    checks = []

    def add(cid, ok, severity, detail):
        checks.append({"id": cid, "ok": bool(ok), "severity": severity, "detail": detail})

    base, tf = market.base, int(market.tf_sec)
    src = market.price_source or ""
    add("synthetic", not market.synthetic, "block", "synthetic test data" if market.synthetic else "real market data")
    if "GC=F" in src:
        add("source", False, "block", f"fallback to {src}: gold FUTURES, a different instrument from spot XAUUSD")
    elif src.startswith("twelvedata"):
        add("source", True, "degrade", f"primary source {src}")
    else:
        add("source", False, "degrade", f"fallback source {src or 'unknown'} (primary unavailable)")
    sym = src.split(":", 1)[-1]
    failed = [k for k, st in (market.status or {}).items() if str(k).startswith(sym + "_") and "failed" in str(getattr(st, "source", ""))]
    add("live_fetch", not failed, "degrade", ("live fetch failed, stored bars used: " + ", ".join(failed)) if failed else "live fetch succeeded")
    if base is None or len(base) == 0:
        add("bars", False, "block", "no bars")
        return _dq_result(checks, now, None, tf, market_open=False)
    tail = base.iloc[-SCAN_BARS:]
    idx = tail.index
    add("duplicates", not idx.duplicated().any(), "block", "duplicate bar timestamps" if idx.duplicated().any() else "no duplicate bars")
    add("order", bool(idx.is_monotonic_increasing), "block", "bars out of time order" if not idx.is_monotonic_increasing else "bars in time order")
    ep = ta.epoch_s(idx)
    if tf <= 3600:
        off = int(np.sum(ep % tf != 0))
        add("grid", off == 0, "block", f"{off} bar(s) off the {tf // 60}-minute grid" if off else "timestamps on the bar grid")
    last_close = pd.Timestamp(idx[-1]) + pd.Timedelta(seconds=tf)
    add("closed", last_close <= pd.Timestamp(now), "block", "the last bar has not closed yet" if last_close > pd.Timestamp(now) else "last bar closed")
    rec = tail.iloc[-RECENT_BARS:]
    o, h, l, c = (rec[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    bad = ~np.isfinite(o) | ~np.isfinite(h) | ~np.isfinite(l) | ~np.isfinite(c) | (o <= 0) | (h <= 0) | (l <= 0) | (c <= 0) \
        | (h < l - 1e-9) | (c > h + 1e-6) | (c < l - 1e-6) | (o > h + 1e-6) | (o < l - 1e-6)
    add("prices", not bad.any(), "block", f"{int(bad.sum())} invalid price bar(s) among the last {RECENT_BARS}" if bad.any() else "prices valid")
    if bool(idx.is_monotonic_increasing) and tf <= 3600:
        miss_recent = miss_old = 0
        cut = idx[max(len(idx) - RECENT_BARS, 0)]
        gaps = np.flatnonzero(np.diff(ep) > tf)
        for g in gaps:
            between = pd.date_range(idx[g] + pd.Timedelta(seconds=tf), idx[g + 1] - pd.Timedelta(seconds=tf), freq=f"{tf}s")
            k = int((~sources.gold_shut(between)).sum()) if len(between) else 0
            if idx[g + 1] > cut:
                miss_recent += k
            else:
                miss_old += k
        add("missing_recent", miss_recent == 0, "block", f"{miss_recent} missing bar(s) among the last {RECENT_BARS}" if miss_recent else "no missing bars recently")
        add("missing_older", miss_old == 0, "degrade", f"{miss_old} missing bar(s) earlier in the last {SCAN_BARS}" if miss_old else f"no missing bars in the last {SCAN_BARS}")
    open_now = not bool(sources.gold_shut(pd.DatetimeIndex([pd.Timestamp(now)]))[0])
    age = (pd.Timestamp(now) - last_close).total_seconds()
    if open_now:
        stale = age > STALE_BARS * tf + 300          # + 5 minutes for the build and deploy
        add("fresh", not stale, "block", f"data {age / 60:.0f} min old ({age / tf:.1f} bars)" if stale else f"data {age / 60:.0f} min old")
    add("spread", True, "info", "spread is MODELLED by session (no bid/ask feed); not observed")
    return _dq_result(checks, now, last_close, tf, market_open=open_now)


def _dq_result(checks, now, last_close, tf, market_open) -> dict:
    block = [c for c in checks if c["severity"] == "block" and not c["ok"]]
    degr = [c for c in checks if c["severity"] == "degrade" and not c["ok"]]
    return {"status": "UNAVAILABLE" if block else "DEGRADED" if degr else "OK", "market_open": market_open,
            "reasons": [c["detail"] for c in block + degr], "checks": checks,
            "last_bar_close": last_close.isoformat() if last_close is not None else None,
            "age_sec": (pd.Timestamp(now) - last_close).total_seconds() if last_close is not None else None, "tf_sec": tf}


# ---------------- L2-L9: approval ----------------
def approve(x: dict) -> dict:
    """x: data {status, reasons}, market_open, regime, signal {dir, bars_since}, htf {name: +1/-1/0/None},
    profile {tp, sl} (price), level_ahead {name, dist} | None, cost_px, atr, news {in_window}, risk_lock (bool | None),
    race {n, win, random} | None, model {validated}, target."""
    layers = []

    def L(i, name, state, detail):
        layers.append({"id": i, "name": name, "state": state, "detail": detail})

    dq, d = x["data"], int(x["signal"]["dir"])
    tp, sl, cost = float(x["profile"]["tp"]), float(x["profile"]["sl"]), float(x["cost_px"])
    if dq["status"] == "UNAVAILABLE":
        L(1, "Data quality", "fail", "; ".join(dq.get("reasons") or ["data unavailable"]))
    elif not x["market_open"]:
        L(1, "Data quality", "fail", "market closed")
    else:
        L(1, "Data quality", "pass" if dq["status"] == "OK" else "warn", "; ".join(dq.get("reasons") or []) or "current and consistent")
    if x["regime"] == "ABNORMAL":
        L(2, "Market regime", "warn", "ABNORMAL volatility (the engine halves size here); suitability by regime not measured")
    else:
        L(2, "Market regime", "info", f"{x['regime']}; suitability by regime not measured (no regime showed an edge)")
    if d == 0:
        L(3, "Directional evidence", "wait", "no engine BUY / SELL on the last closed bar")
    else:
        avail = {k: v for k, v in (x.get("htf") or {}).items() if v is not None}
        against = [k for k, v in avail.items() if v == -d]
        if len(avail) >= 2 and len(against) == len(avail):
            L(3, "Directional evidence", "warn", f"engine {'BUY' if d > 0 else 'SELL'}; {' and '.join(against)} trend against it")
        else:
            L(3, "Directional evidence", "pass", f"engine {'BUY' if d > 0 else 'SELL'}" + (f"; {', '.join(against)} against" if against else ""))
        bs = int(x["signal"]["bars_since"])
        L(4, "Entry quality", "fail" if bs > 0 else "pass", f"late: the signal bar closed {bs} bar(s) ago" if bs > 0 else "entry at the signal bar's close")
        la = x.get("level_ahead")
        if la and la["dist"] < tp:
            L(5, "Target feasibility", "warn", f"{la['name']} is {la['dist']:.2f} away, before the TP ({tp:.2f})")
        else:
            L(5, "Target feasibility", "pass", f"no engine level before the TP ({tp:.2f})" if not la else f"nearest opposing level {la['name']} {la['dist']:.2f} away")
    be = (sl + cost) / (tp + sl) if tp + sl > 0 else math.nan
    r = x.get("race")
    prob = None
    if r and r.get("n", 0) > 0:
        lo, hi = wilson(int(r["win"]), int(r["n"]))
        prob = {"p": r["win"] / r["n"], "lo": lo, "hi": hi, "n": int(r["n"]), "random": r.get("random"), "sample": r.get("sample", "in-sample")}
    meas = f"measured {prob['p'] * 100:.1f}% [{prob['lo'] * 100:.0f}-{prob['hi'] * 100:.0f}] n {prob['n']} ({prob['sample']})" if prob else "no measurement"
    if not x["model"]["validated"]:
        L(6, "Probability validation", "not_validated", f"no validated TP-first model; {meas}")
    elif not prob or prob["n"] < MIN_EVIDENCE_N:
        L(6, "Probability validation", "insufficient", f"{prob['n'] if prob else 0} comparable cases; {MIN_EVIDENCE_N} needed")
    elif prob["lo"] < max(be, x["target"]):
        L(6, "Probability validation", "fail", f"{meas}: lower bound below {max(be, x['target']) * 100:.0f}%")
    else:
        L(6, "Probability validation", "pass", meas)
    cost_pct = cost / x["atr"] * 100.0 if x.get("atr") and x["atr"] > 0 else math.nan
    why = []
    if x["news"].get("in_window"):
        why.append("inside a high-impact news window")
    if math.isfinite(cost_pct) and cost_pct > COST_RED_PCT:
        why.append(f"costs {cost_pct:.0f}% of 1 ATR (limit {COST_RED_PCT:.0f}%)")
    L(7, "Execution", "fail" if why else "pass", "; ".join(why) or (f"costs {cost_pct:.0f}% of 1 ATR; spread modelled" if math.isfinite(cost_pct) else "spread modelled"))
    rl = x.get("risk_lock")
    L(8, "Risk", "fail" if rl is None or rl else "pass",
      "risk state unavailable" if rl is None else "engine risk lock (daily loss or drawdown limit)" if rl else "within the engine's daily loss and drawdown limits")
    st = {lay["id"]: lay["state"] for lay in layers}
    if st[1] == "fail":
        status = "DATA UNAVAILABLE" if dq["status"] == "UNAVAILABLE" else "NO TRADE"
    elif d == 0:
        status = "WAIT FOR CONFIRMATION"
    elif any(st.get(k) == "fail" for k in (4, 7, 8)):
        status = "NO TRADE"
    elif st[6] == "not_validated":
        status = "MODEL NOT VALIDATED"
    elif st[6] == "insufficient":
        status = "INSUFFICIENT EVIDENCE"
    elif st[6] == "fail":
        status = "NO TRADE"
    else:
        status = "CONFIRMED BUY" if d > 0 else "CONFIRMED SELL"
    L(9, "Final", "pass" if status.startswith("CONFIRMED") else "fail", status)
    return {"status": status, "direction": d, "layers": layers, "break_even": be, "target": x["target"], "probability": prob,
            "reasons": [f"L{lay['id']} {lay['name']}: {lay['detail']}" for lay in layers[:-1] if lay["state"] in ("fail", "not_validated", "insufficient", "wait", "warn")]}


# ---------------- payload ----------------
def _bias(score: float) -> int:
    return 1 if score >= 60 else -1 if score <= 40 else 0


def levels(R: dict, sr: dict, i: int, price: float) -> dict:
    """The engine's own levels above and below the price at bar i (nearest first)."""
    names = {"pdh": "PDH", "pdl": "PDL", "pwh": "PWH", "pwl": "PWL", "vah": "VAH", "val": "VAL", "vpoc": "VPOC"}
    lv = [(nm, float(R[k][i])) for k, nm in names.items() if k in R and math.isfinite(float(R[k][i]))]
    lv += [("S/R", float(x["price"])) for x in (sr or {}).get("res", []) + (sr or {}).get("sup", [])]   # a broken level can sit on either side
    up = sorted([(nm, px - price) for nm, px in lv if px - price > 1e-9], key=lambda t: t[1])[:4]
    dn = sorted([(nm, price - px) for nm, px in lv if price - px > 1e-9], key=lambda t: t[1])[:4]
    return {"above": [{"name": nm, "dist": round(dd, 3)} for nm, dd in up], "below": [{"name": nm, "dist": round(dd, 3)} for nm, dd in dn]}


def level_ahead(lv: dict, d: int) -> dict | None:
    side = lv["above"] if d > 0 else lv["below"] if d < 0 else []
    return side[0] if side else None


def race_cell(race: dict | None, tp: float, sl: float, key: str = "engine", d: int = 0) -> dict | None:
    if not race or race.get("error"):
        return None
    try:
        i, j = race["tp_grid"].index(tp), race["sl_grid"].index(sl)
    except ValueError:
        return None
    src = next((s for s in race["sources"] if s.get("key") == key and not s.get("error")), None)
    if not src or not src.get("n"):
        return None
    rl, rs = race["random"]["long"], race["random"]["short"]
    rate = lambda x: x["win"][i][j] / x["n"] if x["n"] else math.nan
    rnd = rate(rl) if d > 0 else rate(rs) if d < 0 else ((src["long"] * rate(rl) + src["short"] * rate(rs)) / src["n"])
    return {"n": src["n"], "win": src["win"][i][j], "random": rnd, "sample": src.get("sample", "in-sample")}


def build(market, res, race: dict | None, checks: dict, sr: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    F, R = res.F, res.rows
    n = len(F["c"])
    i = n - 1
    dq = data_quality(market, now)
    eb, es = np.asarray(R["exec_buy"], float), np.asarray(R["exec_sell"], float)
    sig = np.flatnonzero((eb == 1) | (es == 1))
    d = 1 if eb[i] == 1 else -1 if es[i] == 1 else 0
    last = int(sig[-1]) if len(sig) else None
    tf = int(market.tf_sec)
    htf = {}
    for name, key, sec in (("4H", "240", 14400), ("1H", "60", 3600)):
        if tf < sec:
            htf[name] = _bias(float(F["htf_scores"][key][i]))
        elif tf == sec:
            bl = str(R["bias_label"][i])
            htf[name] = 1 if bl == "BULL" else -1 if bl == "BEAR" else 0
        else:
            htf[name] = None
    price = float(F["c"][i])
    lv = levels(R, sr, i, price)
    ns = news_calendar.state(int(now.timestamp()))
    base_x = {"data": {"status": dq["status"], "reasons": dq["reasons"]}, "market_open": dq["market_open"],
              "regime": str(F["mkt_regime"][i]), "signal": {"dir": d, "bars_since": 0}, "htf": htf,
              "cost_px": float(checks["cost_pts"]), "atr": float(checks["atr"]), "news": {"in_window": ns["in_window"] is not None},
              "risk_lock": bool(R["risk_lock"][i]) if "risk_lock" in R else None, "model": {"validated": MODEL["validated"]}, "target": TARGET}
    profiles = {}
    for k, p in PROFILES.items():
        x = {**base_x, "profile": dict(p), "level_ahead": level_ahead(lv, d), "race": race_cell(race, p["tp"], p["sl"], "engine", d)}
        out = approve(x)
        out["prices"] = ({"entry": price, "sl": price - d * p["sl"], "tp": price + d * p["tp"]} if d else None)
        profiles[k] = {**p, **out}
    return {"model": MODEL, "target": TARGET, "min_evidence_n": MIN_EVIDENCE_N, "cost_red_pct": COST_RED_PCT, "data": dq,
            "signal": {"dir": d, "entry": price if d else None, "last_signal_bars_ago": (i - last) if last is not None else None},
            "price": price, "htf": htf, "regime": str(F["mkt_regime"][i]), "bias": str(R["bias_label"][i]), "levels": lv,
            "inputs": base_x, "profiles": profiles, "contract": contract.export(),
            "news": {"in_window": ns["in_window"], "next": ns["next"]}, "generated_utc": now.isoformat()}
