"""W5 Entry Price Intelligence (operator directive 2026-11-19, Critical Workstream 5, sections 12 and 13).

For the phone's entry alerts (C1, quantum/confirm_entry.py) this module works out what entering at the latest price
means for the alert's own plan, and records how each setup's price path went. It is NON-DIRECTIONAL: it never opens,
closes, changes or re-times a setup, a plan, an alert or any record; it sends nothing to the phone; it only adds
index.json -> alerts.entry_intel for the website and its own records under state["epi"]. Not an ENGINE_SOURCES file.

1. Entry check (ENTRY ELIGIBLE setups inside C1's validity window). The alert's stop, targets and lot are fixed at the
   confirming close. Entering at another price x changes the distance to that stop, so:
     loss at the stop (alert's lot)  = lot x 100 oz x (d(x - stop) + cost per oz)
     lot that keeps the budget       = the same rule as notify.plan_cfg (largest volume step within the budget)
     cost share                      = cost per oz / (d(x - stop) + cost per oz): the part of that loss that is costs
                                       (shown, not a rule: near the stop the lot grows and costs dominate)
     net R:R with the alert's targets = (half to TP1 + half to TP2 - cost) / (d(x - stop) + cost), as C1's plan_at
   The ENTRY BAND is the range of prices where the alert's rules still hold: the far side is the nearest of
     (a) the price where the alert's lot would lose more than the budget at the stop,
     (b) the price where net R:R falls below C1's minimum (RR_MIN),
     (c) TP1 itself (nothing left to the first target);
   the near side is the stop. Inside the band at the alert's lot: WITHIN PLAN. Beyond (a) only: RESIZE to the lot
   shown. Beyond (b) or (c), or at / beyond the stop: OUTSIDE PLAN, NO TRADE at that price. A price older than
   C1.FRESH_SEC: NOT CHECKED. The band is arithmetic of the operator's own plan. It is NOT a better chance of reaching
   the target: B31b-W5 found no entry price that beats a random entry with the same stop distance (EVIDENCE).
   This check can only make C1's decision stricter, never looser: setups C1 did not make ENTRY ELIGIBLE, or whose window
   has passed, are not assessed.

2. Path record (every C1 setup that appears after this module started). Two hypothetical entries, both with the
   plan's stop distance: at the signal close P0 (the earliest plausible price) and, when C1 confirmed one, at the
   confirming close (the actual alert entry). For each, +$10 / +$15 / +$20 are raced against the stop SEPARATELY on the
   15m bars after it, with C1's own conventions: a bar opening through the stop fills at its open (a gap: the loss
   can exceed the plan); a bar touching both the stop and the target is AMBIGUOUS and counted as the stop. MFE / MAE run
   until the stop, +$20 or the 48 h horizon. Also recorded: how much of P0's best move was used before the confirmed entry,
   and the confirmed entry vs P0 in net R at +$10 (did waiting pay for the worse price?). Descriptive only: no verdict,
   no probability, never an alert.

The prices are the feed's mid (Twelve Data); the cost model stands in for the spread, slippage and commission. No
broker bid / ask is connected, so no spread is measured and none of this is a broker-executable price.
"""
from __future__ import annotations

import math
import os

from . import confirm_entry as C1

ID = "W5-EPI"
TARGETS = (10.0, 15.0, 20.0)
HOLD = C1.HOLD                         # 15m bars a path is followed (48 market hours), as C1
LOG_MAX, PATH_MAX, SNAP_PATHS = 300, 200, 12
EPS = 1e-9
EVIDENCE = ("B31b-W5 (development 2020-23: 4,223 impulses, 20 entry methods incl. Fibonacci levels, structure, TWAP / EMA, "
            "M5 timing and adaptive limits, each against random entries with the same stop): no entry price reached +$10 "
            "before the stop more often than a random walk with that stop distance, and every method lost after costs. "
            "NO CANDIDATE. The band is arithmetic of your plan, not a better chance.")
RULES = ("Entry band: the prices where the alert's own rules still hold with its stop and targets: the loss at the stop "
         "with the alert's lot within the budget (else RESIZE), net R:R at least the minimum, and something left to TP1. "
         "Path record: +$10 / +$15 / +$20 raced separately against the plan's stop from the signal close and from the "
         "confirmed entry, on 15m bars (a bar touching both counts as the stop; a bar opening through the stop fills at "
         "its open). Feed mid prices and a cost model: no broker bid / ask is connected.")


def on() -> bool:
    return (os.environ.get("ENTRY_INTEL") or "1").strip() not in ("0", "off", "no", "false")


# ---------------- 1. the entry check ----------------
def lot_for(dist: float, cost_oz: float, budget: float, step: float, lot_max: float) -> float:
    """notify.plan_cfg's sizing rule at a stop distance `dist`: the largest multiple of `step` whose loss at the stop,
    cost included, stays within `budget`; never below `step` (then over budget) and never above `lot_max`."""
    k = math.floor(budget / ((dist + cost_oz) * 100.0) / step + 1e-9) if dist + cost_oz > 0 else 0
    return min(max(round(k * step, 2), step), lot_max)


def rr_at(u: float, p: dict, d: int) -> float:
    """Net reward / net risk per oz at the signed price u = d * x, with the plan's stop and targets (C1.plan_at)."""
    c = p["size_cost_oz"]
    t1 = d * p["tp1"] - u
    reward = (0.5 * t1 + 0.5 * (d * p["tp2"] - u) - c) if p.get("tp2") is not None else t1 - c
    risk = u - d * p["sl"] + c
    return reward / risk if risk > 0 else 0.0


def band(p: dict, d: int, rr_min: float = C1.RR_MIN) -> dict:
    """The prices bounding the alert's rules (see the module text), each as a price and the $ from the alert entry
    (+ = worse for the trader)."""
    c, lot, s = p["size_cost_oz"], p["lot"], p["sl"]
    oz = lot * 100.0
    ds = d * s
    u_budget = ds + p["budget"] / oz - c if oz > 0 else ds
    if p.get("tp2") is not None:
        u_rr = (0.5 * (d * p["tp1"] + d * p["tp2"]) - c + rr_min * (ds - c)) / (1.0 + rr_min)
    else:
        u_rr = (d * p["tp1"] - c + rr_min * (ds - c)) / (1.0 + rr_min)
    u_tp1 = d * p["tp1"]
    u_far = min(u_rr, u_tp1)
    u0 = d * p["entry"]
    return {"stop": s, "budget_px": round(d * u_budget, 2), "rr_px": round(d * u_rr, 2), "tp1": p["tp1"],
            "far_px": round(d * min(u_budget, u_far), 2), "far_resized_px": round(d * u_far, 2),
            "budget_worse_usd": round(u_budget - u0, 2), "rr_worse_usd": round(u_rr - u0, 2),
            "far_by": "budget" if u_budget <= u_far else ("rr" if u_rr <= u_tp1 else "tp1")}


def assess(s: dict, now: dict | None, t_now: int, sizing: dict) -> dict | None:
    """The entry check of one C1 setup at this run's latest price, or None when C1 has not made it ENTRY ELIGIBLE or
    its window has passed (the check never re-opens what C1 closed). sizing: {'step', 'lot_max'} of notify.plan_cfg."""
    cf, p = s.get("conf") or {}, s.get("plan")
    if s.get("status") != "ACTIVE" or not p or not cf or t_now - cf["t"] > C1.FRESH_SEC:
        return None
    d = s["dir"]
    out = {"id": s["id"], "dir": d, "tf": s["tf"], "entry": p["entry"], "until": cf["t"] + C1.FRESH_SEC,
           "band": band(p, d), "lot_alert": p["lot"], "budget": p["budget"], "cost_oz": p["size_cost_oz"]}
    if not now or now.get("px") is None or now.get("t") is None:
        return {**out, "word": "NOT CHECKED", "why": ["no latest price in this run"]}
    age = int(t_now - now["t"])
    x = float(now["px"])
    out.update({"px": x, "t_px": int(now["t"]), "age_sec": age, "live": bool(now.get("live"))})
    if age > C1.FRESH_SEC:
        return {**out, "word": "NOT CHECKED", "why": [f"the latest price is {age // 60} min old"]}
    u, c = d * x, p["size_cost_oz"]
    dist = u - d * p["sl"]
    oz = p["lot"] * 100.0
    out.update({"dev_usd": round(d * p["entry"] - u, 2), "dist_usd": round(dist, 2), "left_tp1_usd": round(d * p["tp1"] - u, 2)})
    if dist <= EPS:
        return {**out, "word": "OUTSIDE PLAN", "why": ["price is at or beyond the alert's stop"]}
    lot_b = lot_for(dist, c, p["budget"], sizing["step"], sizing["lot_max"])
    out.update({"loss_alert_lot": round(oz * (dist + c), 2), "lot_budget": lot_b, "loss_lot_budget": round(lot_b * 100.0 * (dist + c), 2),
                "rr_now": round(rr_at(u, p, d), 3), "cost_share": round(c / (dist + c), 3)})   # costs / loss at the stop
    why = []
    if d * p["tp1"] - u <= EPS:
        why.append("TP1 is already reached at this price: nothing is left to the first target")
    elif out["rr_now"] < C1.RR_MIN - EPS:
        why.append(f"net R:R {out['rr_now']:.2f} with the alert's targets is below {C1.RR_MIN:g} "
                   f"(${-out['dev_usd']:.2f} worse than the alert's entry)")
    if lot_b * 100.0 * (dist + c) > p["budget"] + 1e-6:
        why.append(f"even the minimum lot loses more than the ${p['budget']:,.0f} budget at the stop")
    if why:
        return {**out, "word": "OUTSIDE PLAN", "why": why}
    if out["loss_alert_lot"] > p["budget"] + 1e-6:
        return {**out, "word": "RESIZE", "why": [f"at the alert's {p['lot']:g} lot the loss at the stop would be "
                                                 f"${out['loss_alert_lot']:,.0f}, over the ${p['budget']:,.0f} budget: "
                                                 f"{lot_b:g} lot keeps it at ${out['loss_lot_budget']:,.0f}"]}
    return {**out, "word": "WITHIN PLAN", "why": []}


# ---------------- 2. the path record ----------------
def _race_new(e: float, stop_dist: float, t_from: int) -> dict:
    return {"e": round(e, 2), "D": stop_dist, "from": int(t_from), "scanned": int(t_from) - 900, "n": 0, "mfe": 0.0,
            "mae": 0.0, "res": {f"{t:g}": None for t in TARGETS}, "mark": None}


def _race_step(r: dict, d: int, tj: int, o_, h_, l_, c_, cost: float) -> None:
    """One closed 15m bar of one hypothetical entry: each target's race against the stop, then MFE / MAE (the race ends
    once all three are decided, so MFE / MAE run until the stop, +$20 or the horizon, the deciding bar included)."""
    e, D = r["e"], r["D"]
    stop = e - d * D
    R = lambda pnl: (pnl - cost) / (D + cost)                       # noqa: E731 - net R per oz, cost included
    gap = (o_ - stop) * d <= 0
    hit_s = gap or ((l_ <= stop + EPS) if d == 1 else (h_ >= stop - EPS))
    for t in TARGETS:
        k = f"{t:g}"
        if r["res"][k] is not None:
            continue
        tgt = e + d * t
        hit_t = (h_ >= tgt - EPS) if d == 1 else (l_ <= tgt + EPS)
        if gap:
            r["res"][k] = ["SL", tj + 900, round(o_, 2), round(R(d * (o_ - e)), 3)]
        elif hit_s and hit_t:
            r["res"][k] = ["AMBIGUOUS", tj + 900, round(stop, 2), round(R(-D), 3)]
        elif hit_s:
            r["res"][k] = ["SL", tj + 900, round(stop, 2), round(R(-D), 3)]
        elif hit_t:
            r["res"][k] = ["TP", tj + 900, round(tgt, 2), round(R(t), 3)]
    r["mfe"] = round(max(r["mfe"], d * ((h_ if d == 1 else l_) - e)), 2)
    r["mae"] = round(max(r["mae"], d * (e - (l_ if d == 1 else h_))), 2)
    r["n"] += 1
    r["scanned"] = tj
    r["mark"] = [tj + 900, round(c_, 2), round(R(d * (c_ - e)), 3)]


def _race_done(r: dict) -> bool:
    return all(v is not None for v in r["res"].values()) or r["n"] >= HOLD


def _advance(r: dict, d: int, ch: dict, t_now: int, cost: float) -> None:
    t, o, h, l, c = (ch.get(k) or [] for k in ("t", "o", "h", "l", "c"))
    n = min(len(t), len(o), len(h), len(l), len(c))
    for j in range(n):
        tj = int(t[j])
        if _race_done(r):
            return
        if tj <= r["scanned"] or tj < r["from"] or tj + 900 > t_now or None in (o[j], h[j], l[j], c[j]):
            continue
        _race_step(r, d, tj, float(o[j]), float(h[j]), float(l[j]), float(c[j]), cost)


def book(state: dict, t_now: int) -> dict:
    return state.setdefault("epi", {"since": int(t_now), "paths": [], "log": [], "last": {}})


def track(state: dict, ch: dict, t_now: int, pl: dict) -> None:
    """Start a path for every C1 setup that appeared since this module started; move every unfinished one on."""
    bk, c1 = book(state, t_now), C1.book(state)
    have = {x["id"]: x for x in bk["paths"]}
    for s in c1["log"] + c1["open"]:
        x = have.get(s["id"])
        if x is None:
            if s["t_close"] < bk["since"]:
                continue                                  # before this module started: not recorded
            x = {"id": s["id"], "tf": s["tf"], "dir": s["dir"], "p0": s["p0"], "t_close": s["t_close"],
                 "p0_race": _race_new(s["p0"], pl["sl_px"], s["t_close"])}
            bk["paths"].append(x)
            have[s["id"]] = x
        x["c1"] = s["status"]
        cf, p = s.get("conf"), s.get("plan")
        if s.get("entry_bar") is not None and p and cf and "entry_race" not in x:
            x["entry_race"] = _race_new(p["entry"], d_abs(p), cf["t"])
            x["conf_move"] = cf["move"]
    cost = pl["size_cost_oz"]
    for x in bk["paths"]:
        for k in ("p0_race", "entry_race"):
            if k in x and not _race_done(x[k]):
                _advance(x[k], x["dir"], ch, t_now, cost)
        r0, re_ = x["p0_race"], x.get("entry_race")
        if re_ is not None and r0["mfe"] > EPS:
            x["used_share"] = round(min(1.0, max(0.0, x["conf_move"] / r0["mfe"])), 3)
        x["done"] = _race_done(r0) and (re_ is None or _race_done(re_)) and x["c1"] in C1.FINAL
    bk["paths"] = bk["paths"][-PATH_MAX:]


def d_abs(p: dict) -> float:
    """The plan's stop distance, from its own levels."""
    return round(abs(p["entry"] - p["sl"]), 2)


def summary(paths: list[dict]) -> dict:
    """Counts per target for the two hypothetical entries; only decided races count (AMBIGUOUS as the stop)."""
    out = {}
    for k in ("p0_race", "entry_race"):
        rows = [x[k] for x in paths if k in x]
        per = {}
        for t in TARGETS:
            res = [r["res"][f"{t:g}"] for r in rows if r["res"][f"{t:g}"] is not None]
            tp = sum(1 for v in res if v[0] == "TP")
            n = len(res)
            per[f"{t:g}"] = {"tp": tp, "n": n, "wilson": C1.wilson(tp, n), "mean_r": round(sum(v[3] for v in res) / n, 3) if n else None}
        out[k] = {"paths": len(rows), "per": per}
    pair = [(x["entry_race"]["res"]["10"], x["p0_race"]["res"]["10"]) for x in paths if "entry_race" in x]
    pair = [(a[3], b[3]) for a, b in pair if a is not None and b is not None]
    out["waiting_10"] = {"n": len(pair), "mean_diff_r": round(sum(a - b for a, b in pair) / len(pair), 3) if pair else None}
    return out


# ---------------- the run ----------------
def run(state: dict, p15: dict | None, pl: dict | None, now: dict | None, t_now: int) -> dict:
    """index.json -> alerts.entry_intel. Reads C1's book (never writes it), records under state['epi']."""
    if not on():
        return {"id": ID, "on": False}
    if not p15 or (p15.get("meta") or {}).get("synthetic") or pl is None:
        return {"id": ID, "on": True, "ok": False, "why": "no plan or no 15m data in this run"}
    sizing = {"step": pl["lot_step"], "lot_max": pl["lot_max"]}
    track(state, p15.get("chart") or {}, t_now, pl)
    bk = book(state, t_now)
    live = [a for a in (assess(s, now, t_now, sizing) for s in C1.book(state)["open"]) if a is not None]
    for a in live:                                        # the decision record: each change of word per setup
        key = str(a["id"])
        if bk["last"].get(key) != a["word"]:
            bk["last"][key] = a["word"]
            bk["log"].append({"t": int(t_now), "id": a["id"], "word": a["word"], "px": a.get("px"), "dev_usd": a.get("dev_usd"),
                              "dist_usd": a.get("dist_usd"), "why": a["why"]})
    bk["log"] = bk["log"][-LOG_MAX:]
    keep = {str(s["id"]) for s in C1.book(state)["open"]}
    bk["last"] = {k: v for k, v in bk["last"].items() if k in keep}
    return {"id": ID, "on": True, "ok": True, "t": int(t_now), "since": bk["since"],
            "price": ({"px": now["px"], "t": now["t"], "live": bool(now.get("live")),
                       "source": "feed mid (Twelve Data); not a broker bid / ask"} if now and now.get("px") is not None else None),
            "fresh_sec": C1.FRESH_SEC, "rr_min": C1.RR_MIN, "sizing": sizing, "live": live,
            "paths": bk["paths"][::-1][:SNAP_PATHS], "summary": summary(bk["paths"]), "log": bk["log"][::-1][:10],
            "evidence": EVIDENCE, "rules": RULES}
