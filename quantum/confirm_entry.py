"""C1 (operator directive 2026-11-15): a favourable move must be CONFIRMED before the phone offers an entry.

Lifecycle of each engine signal on the phone's 15m alerts (one per idea: a signal in the same direction within 4 hours
and $15 of an open setup opens none):

  SETUP_DETECTED      the signal bar closed (the SETUP alert says: NOT an entry)
  REFERENCE_SET       P0 = that close, fixed; never reset, the direction never reversed
  MOVE_10/15/20       price TOUCHED +$10 / +$15 / +$20 beyond P0 (milestones, recorded; never an entry, never a message)
  CONFIRMED           the first 15m CLOSE at least CONFIRM_MIN_USD (default $10) beyond P0; tier by that close:
                      MINIMUM $10-15, PREFERRED $15-20, IDEAL $20 or more
  ENTRY_ELIGIBLE      every check below passed: the ENTRY ELIGIBLE alert, with the plan recalculated from the entry
  REJECTED            a check failed: NO TRADE, with the reason
  ENTRY_ACTIVE        the record's entry = the confirming close (the operator places the order; nothing is executed)
  TP1 / TP2 / BE / SL / AMBIGUOUS / TIMEOUT   the plan's result on the 15m bars after the entry
  INVALIDATED         before confirmation: price traded $13 against P0, a 15m BOS / MSS / CHoCH the other way, or an
                      opposite engine signal (checked first, so a bar that does both is INVALIDATED)
  EXPIRED             no confirming close within 96 15m bars (24 h), or (only if CONFIRM_CAP_USD is set) beyond the cap

Checks before ENTRY_ELIGIBLE (operator section 5):
  fresh     the confirming close is the run's latest closed 15m bar and at most FRESH_SEC old (else stale: NO TRADE)
  plan      entry = the confirming close; SL / TP1 / TP2 recalculated from it with the operator's distances ($13 / $13 /
            $20 by default; N1 sizes the lot so the loss at the stop, costs included, stays within the $650 budget)
  reward    net reward with both targets / net risk >= 1.0 after costs (a single symmetric $13 / $13 target cannot pass)
  room      no previous-day / week high (BUY) or low (SELL) between the entry and TP1: the target is not behind a level
  size      the N1 lot is within the budget (below the minimum lot = NO TRADE)

Evidence (stated on every alert): B19 and B30 found no confirmation threshold that raises the chance of TP before SL out
of sample; the rule is the operator's risk preference, not a validated edge. No probability is shown.

Alerts and display only: not an ENGINE_SOURCES file. B15's plans, B9 and every record are unchanged (the B15 plan still
opens at the signal close; its follow-ups are labelled as the engine's record, not an entry). CONFIRM_MIN_USD=0 restores
the previous alerts.
"""
from __future__ import annotations

import os

INV_USD = 13.0
WIN = 96                               # 15m bars to confirm (24 h), as B19 / B30
HOLD = 192                             # 15m bars a confirmed plan is followed (48 h), as B30
TIERS = ((20.0, "IDEAL"), (15.0, "PREFERRED"), (10.0, "MINIMUM"))
RR_MIN = 1.0                           # net reward / net risk, both targets, after costs (B19 / B30's RR_MIN)
FRESH_SEC = 1200                       # one 15-minute cycle plus 5 minutes for the run itself
REPEAT_SEC, REPEAT_USD = 4 * 3600, 15.0
STRUCT = ("BOS", "MSS", "CHoCH")
LOG_MAX, OPEN_MAX = 500, 60
EPS = 1e-9
FINAL = ("INVALIDATED", "EXPIRED", "REJECTED", "TP2", "BE", "SL", "AMBIGUOUS", "TIMEOUT")
EVIDENCE = ("Confirmation is your rule, not a proven edge: B19 and B30 found no $10 / $15 / $20 threshold that raises the "
            "chance of TP before SL out of sample.")
B15_PREFIX = "ENGINE RECORD, NOT YOUR TRADE (the engine test B15b measures the signal from its close; act only on ENTRY ELIGIBLE alerts): "


def b15_line(x: str) -> str:
    """A B15 plan follow-up under C1: the same line, named as the engine's record (the operator enters only after an
    ENTRY ELIGIBLE alert, so 'YOUR PLAN' would name a trade that was never taken)."""
    return B15_PREFIX + x.replace("YOUR PLAN", "ENGINE PLAN")


def _num(key: str, default: float) -> float:
    try:
        v = float(os.environ.get(key, "") or default)
    except ValueError:
        return default
    return max(v, 0.0)


def min_usd() -> float:
    return _num("CONFIRM_MIN_USD", 10.0)


def cap_usd() -> float:
    return _num("CONFIRM_CAP_USD", 0.0)


def on() -> bool:
    return min_usd() > 0


def tier(move: float) -> str:
    for lv, name in TIERS:
        if move >= lv - EPS:
            return name
    return "BELOW $10"


def _side(d: int) -> str:
    return "BUY" if d == 1 else "SELL"


def _px(x: float, off: float = 0.0) -> str:
    return f"{x + off:.2f}"


def _hm(t: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(t, timezone.utc).strftime("%d %b %H:%M UTC")


# ---------------- the SETUP alert (replaces the entry lines of a SIGNAL alert) ----------------
def setup_head(m: dict, tf: str, off: float = 0.0) -> str:
    return f"XAUUSD {tf} {_side(m['dir'])} SETUP DETECTED (signal bar closed) | NOT AN ENTRY | reference {_px(m['px'], off)}"


def repeat_head(m: dict, tf: str, off: float = 0.0) -> str:
    """A signal that repeats an idea already announced (its REPEAT line follows): still not an entry."""
    return f"XAUUSD {tf} {_side(m['dir'])} signal again (signal bar closed) at {_px(m['px'], off)} | NOT AN ENTRY"


def setup_lines(m: dict, off: float = 0.0) -> list[str]:
    d, p0, X = m["dir"], m["px"], min_usd()
    word = "above" if d == 1 else "below"
    lv = lambda x: _px(p0 + d * x, off)
    tail = f" | +$15 {lv(15)} preferred | +$20 {lv(20)} ideal" if X < 15 else ""
    cap = f" | a first close more than ${cap_usd():g} beyond expires it" if cap_usd() else ""
    return [f"WAIT FOR CONFIRMATION: a 15m close at or {word} {lv(X)} (+${X:g} minimum){tail}{cap} | a touch is not a confirmation",
            f"CANCELLED if price trades {_px(p0 - d * INV_USD, off)} (-${INV_USD:g}) or the 15m structure breaks the other way "
            f"first; expires after 24 h",
            "NO TRADE until an ENTRY ELIGIBLE alert arrives. " + EVIDENCE]


# ---------------- state ----------------
def book(state: dict) -> dict:
    return state.setdefault("c1", {"seq": 0, "open": [], "log": []})


def open_setup(state: dict, m: dict, tf: str) -> dict | None:
    """A new setup from a SIGNAL marker, or None when it repeats an open setup (one idea, one setup)."""
    if m.get("px") is None or m.get("dir") not in (1, -1):
        return None
    bk = book(state)
    t_close = int(m["t"]) + 900 if tf == "15m" else int(m["t"]) + {"30m": 1800, "1h": 3600, "4h": 14400}.get(tf, 900)
    for s in bk["open"]:
        if s["dir"] == m["dir"] and t_close - s["t_close"] <= REPEAT_SEC and abs(m["px"] - s["p0"]) <= REPEAT_USD:
            return None
    bk["seq"] = int(bk.get("seq", 0)) + 1
    s = {"id": bk["seq"], "tf": tf, "t": int(m["t"]), "t_close": t_close, "dir": int(m["dir"]), "p0": float(m["px"]),
         "status": "PENDING", "scanned": t_close - 900, "touch": {}, "x": min_usd(),
         "events": [["SETUP_DETECTED", t_close, float(m["px"])], ["REFERENCE_SET", t_close, float(m["px"])]]}
    bk["open"].append(s)
    return s


# ---------------- checks and the recalculated plan ----------------
def plan_at(entry: float, d: int, pl: dict) -> dict:
    lot, oz = pl["lot"], pl["lot"] * 100.0
    cost = oz * pl["size_cost_oz"]
    tp2 = pl.get("tp2_px")
    reward_both = oz * (0.5 * pl["tp_px"] + 0.5 * tp2) - cost if tp2 else oz * pl["tp_px"] - cost
    reward_tp1 = oz * 0.5 * pl["tp_px"] - cost if tp2 else reward_both
    risk = oz * (pl["sl_px"] + pl["size_cost_oz"])
    return {"entry": round(entry, 2), "sl": round(entry - d * pl["sl_px"], 2), "tp1": round(entry + d * pl["tp_px"], 2),
            "tp2": round(entry + d * tp2, 2) if tp2 else None, "lot": lot, "cost_usd": cost, "risk_usd": risk,
            "reward_both_usd": reward_both, "reward_tp1_usd": reward_tp1, "rr_net": reward_both / risk if risk > 0 else 0.0,
            "account": pl["account"], "risk_pct": pl["risk_pct"], "budget": pl["budget"], "size_cost_oz": pl["size_cost_oz"],
            "over_budget": bool(pl.get("over_budget"))}


def checks(ch: dict, j: int, d: int, plan: dict, t_now: int, off: float = 0.0) -> list[str]:
    """Reasons to reject (empty = ENTRY ELIGIBLE)."""
    why = []
    t = ch["t"]
    age = t_now - (int(t[j]) + 900)
    if j != len(t) - 1 or age > FRESH_SEC:
        why.append(f"stale: the confirming close was {max(age, 0) // 60} min before this alert, so the price has moved on")
    if plan["rr_net"] < RR_MIN - EPS:
        why.append(f"net reward / risk {plan['rr_net']:.2f} after costs is below {RR_MIN:g}")
    e, tp1 = plan["entry"], plan["tp1"]
    for name in (("pdh", "pwh") if d == 1 else ("pdl", "pwl")):
        lv = (ch.get(name) or [None] * len(t))[j]
        if lv is not None and (lv - e) * d > EPS and (tp1 - lv) * d > EPS:
            why.append(f"{name.upper()} {_px(lv, off)} lies between the entry and TP1, ${abs(lv - e):.2f} away: too little room to the target")
    if plan["over_budget"]:
        why.append(f"the minimum lot loses more than the ${plan['budget']:,.0f} budget at the stop")
    return why


# ---------------- advancing one setup on the 15m bars ----------------
def _markers_at(markers: list, kinds: tuple, d: int) -> set:
    return {int(m["t"]) for m in markers if m["type"] in kinds and m.get("dir") == d}


def advance(s: dict, ch: dict, markers: list, t_now: int, pl: dict | None, off: float = 0.0) -> list[str]:
    """Moves `s` along its lifecycle on the closed 15m bars it has not seen; returns the phone lines for what changed."""
    t, o, h, l, c = (ch.get(k) or [] for k in ("t", "o", "h", "l", "c"))
    d, p0 = s["dir"], s["p0"]
    opp_struct = _markers_at(markers, STRUCT, -d)
    opp_sig = _markers_at(markers, ("SIGNAL",), -d)
    out = []
    n_ok = min(len(t), len(o), len(h), len(l), len(c))       # incomplete data: bars without every price are skipped
    js = [j for j in range(n_ok) if int(t[j]) > s["scanned"] and int(t[j]) >= s["t_close"] and int(t[j]) + 900 <= t_now
          and None not in (o[j], h[j], l[j], c[j])]
    for j in js:
        tj = int(t[j])
        s["scanned"] = tj
        if s["status"] == "PENDING":
            n_bars = sum(1 for k in range(len(t)) if s["t_close"] <= int(t[k]) <= tj)
            fav = (h[j] - p0) if d == 1 else (p0 - l[j])
            adv = (p0 - l[j]) if d == 1 else (h[j] - p0)
            move = (c[j] - p0) * d
            if adv >= INV_USD - EPS:
                out.append(_final(s, "INVALIDATED", tj + 900, c[j], f"price traded ${INV_USD:g} against the reference before confirmation", off))
                break
            if tj in opp_struct:
                out.append(_final(s, "INVALIDATED", tj + 900, c[j], "a 15m structure break the other way came first", off))
                break
            if tj in opp_sig:
                out.append(_final(s, "INVALIDATED", tj + 900, c[j], "an opposite engine signal (contradictory) came first", off))
                break
            for lv in (10, 15, 20):
                if str(lv) not in s["touch"] and fav >= lv - EPS:
                    s["touch"][str(lv)] = tj + 900
                    s["events"].append([f"MOVE_{lv}_TOUCHED", tj + 900, round(p0 + d * lv, 2)])
            if move >= s["x"] - EPS:
                if cap_usd() and move > cap_usd() + EPS:
                    out.append(_final(s, "EXPIRED", tj + 900, c[j], f"the first close was ${move:.2f} beyond, past the ${cap_usd():g} cap", off))
                    break
                s["conf"] = {"t": tj + 900, "px": float(c[j]), "move": round(move, 2), "tier": tier(move)}
                s["events"].append(["CONFIRMED", tj + 900, float(c[j])])
                if pl is None:
                    out.append(_final(s, "REJECTED", tj + 900, c[j], "no plan is configured (PLAN=0)", off))
                    break
                plan = plan_at(float(c[j]), d, pl)
                why = checks(ch, j, d, plan, t_now, off)
                s["plan"] = plan
                if why:
                    out.append(_final(s, "REJECTED", tj + 900, c[j], "; ".join(why), off))
                    break
                s["status"] = "ACTIVE"
                s["entry_bar"] = tj
                s["events"] += [["ENTRY_ELIGIBLE", tj + 900, float(c[j])], ["ENTRY_ACTIVE", tj + 900, float(c[j])]]
                out += eligible_lines(s, off)
                continue
            if n_bars >= WIN:
                out.append(_final(s, "EXPIRED", tj + 900, c[j], "no confirming close within 24 h", off))
                break
        elif s["status"] in ("ACTIVE", "TP1"):
            out += _follow(s, j, tj, o[j], h[j], l[j], c[j], ch, off)
            if s["status"] in FINAL:
                break
    return out


def _follow(s: dict, j: int, tj: int, o_, h_, l_, c_, ch: dict, off: float) -> list[str]:
    """The plan after the entry: stage 1 SL vs TP1 (a bar touching both = AMBIGUOUS, counted as the stop); after TP1 the
    stop sits at the entry and the rest runs to TP2 (on the TP1 bar a touch of the entry scores it at the entry). A bar
    opening beyond a level fills at its open. Time stop after HOLD bars."""
    d, p = s["dir"], s["plan"]
    e, sl, tp1, tp2 = p["entry"], p["sl"], p["tp1"], p["tp2"]
    n_after = sum(1 for k in range(len(ch["t"])) if s["entry_bar"] < int(ch["t"][k]) <= tj)
    hi = lambda x: (h_ >= x - EPS) if d == 1 else (l_ <= x + EPS)
    lo = lambda x: (l_ <= x + EPS) if d == 1 else (h_ >= x - EPS)
    beyond = lambda x, up: ((o_ - x) * d >= 0) if up else ((o_ - x) * d <= 0)
    if s["status"] == "ACTIVE":
        if beyond(sl, False):
            return [_final(s, "SL", tj + 900, o_, f"the bar opened through the stop at {_px(o_, off)}", off)]
        if lo(sl) and hi(tp1):
            return [_final(s, "AMBIGUOUS", tj + 900, sl, "the stop and TP1 in one 15m bar: order unknown, counted as the stop", off)]
        if lo(sl):
            return [_final(s, "SL", tj + 900, sl, f"stopped at {_px(sl, off)}", off)]
        if hi(tp1) or beyond(tp1, True):
            s["status"] = "TP1"
            s["events"].append(["TP1", tj + 900, tp1])
            line = f"XAUUSD {s['tf']} {_side(d)} confirmed setup #{s['id']}: TP1 {_px(tp1, off)} reached"
            if tp2 is None:
                return [_final(s, "TP2", tj + 900, tp1, "TP1 reached (single target)", off)]
            if lo(e):
                return [line, _final(s, "BE", tj + 900, e, "the TP1 bar also traded back to the entry: the rest counted at the entry", off)]
            if hi(tp2):
                return [line, _final(s, "TP2", tj + 900, tp2, f"TP2 {_px(tp2, off)} reached in the same bar", off)]
            return [line + f": close half, move the stop to the entry {_px(e, off)}"]
    elif s["status"] == "TP1":
        if beyond(e, False) or lo(e):
            return [_final(s, "BE", tj + 900, e, f"back to the entry {_px(e, off)} after TP1 (half banked)", off)]
        if hi(tp2) or beyond(tp2, True):
            return [_final(s, "TP2", tj + 900, tp2, f"TP2 {_px(tp2, off)} reached", off)]
    if n_after >= HOLD and s["status"] not in FINAL:
        return [_final(s, "TIMEOUT", tj + 900, c_, f"48 h without the stop or the target; closed at {_px(c_, off)}", off)]
    return []


def _final(s: dict, status: str, t: int, px: float, why: str, off: float) -> str:
    s["status"], s["why"], s["t_done"] = status, why, int(t)
    s["events"].append([status, int(t), float(px)])
    d = s["dir"]
    if status in ("INVALIDATED", "EXPIRED"):
        return (f"XAUUSD {s['tf']} {_side(d)} SETUP {'CANCELLED' if status == 'INVALIDATED' else 'EXPIRED'} (reference "
                f"{_px(s['p0'], off)}): {why} | NO TRADE")
    if status == "REJECTED":
        cf = s.get("conf") or {}
        return (f"XAUUSD {s['tf']} {_side(d)} confirmed +${cf.get('move', 0):.2f} ({cf.get('tier', '')}) at "
                f"{_px(cf.get('px', px), off)} but NOT ELIGIBLE: {why} | NO TRADE")
    return f"XAUUSD {s['tf']} {_side(d)} confirmed setup #{s['id']} {status}: {why}"


def eligible_lines(s: dict, off: float = 0.0) -> list[str]:
    d, p, cf = s["dir"], s["plan"], s["conf"]
    touched = ", ".join(f"+${k} {_hm(v)[-9:]}" for k, v in sorted(s["touch"].items(), key=lambda kv: int(kv[0])))
    tp2 = f" | TP2 {_px(p['tp2'], off)} (the rest; stop to the entry after TP1)" if p["tp2"] is not None else ""
    return [
        f"XAUUSD {s['tf']} {_side(d)} ENTRY ELIGIBLE: confirmed +${cf['move']:.2f} ({cf['tier']}) at the 15m close "
        f"{_px(cf['px'], off)}, {_hm(cf['t'])} | reference {_px(s['p0'], off)} | touched {touched or '-'}",
        f"PLAN (recalculated from this entry): entry {_px(p['entry'], off)} | SL {_px(p['sl'], off)} | TP1 {_px(p['tp1'], off)}"
        f"{' (close half)' if p['tp2'] is not None else ''}{tp2}",
        f"RISK: account ${p['account']:,.0f} | {p['risk_pct']:g}% = max ${p['budget']:,.0f} | lot {p['lot']:g} | est. cost "
        f"${p['cost_usd']:,.0f} (${p['size_cost_oz']:.2f}/oz) | loss at the stop incl. cost ${p['risk_usd']:,.0f}",
        f"NET: reward ${p['reward_both_usd']:,.0f} if every target is reached"
        + (f", ${p['reward_tp1_usd']:,.0f} if TP1 then back to the entry" if p["tp2"] is not None else "")
        + f" | net R:R {p['rr_net']:.2f} | a ${p['risk_usd']:,.0f} loss is possible on this trade",
        "CHECKS passed: fresh close, no opposite structure or signal since the setup, room to TP1, size within the budget. "
        + EVIDENCE]


# ---------------- one run ----------------
def open_from(state: dict, payload: dict, since: int | None, skip: set | None = None) -> list[dict]:
    """Setups from a payload's new SIGNAL markers (confirmation is always read on 15m bars). skip: the bar times of
    signals the phone did not announce as a SETUP (a REPEAT of an open plan, or a NOT ACTIONABLE one), so every later
    CONFIRMED / CANCELLED alert belongs to a SETUP the operator was shown."""
    tf = payload["meta"]["tf"]
    new = sorted((m for m in payload.get("markers") or [] if m["type"] == "SIGNAL" and (since is None or m["t"] > since)
                  and m["t"] not in (skip or ())), key=lambda m: m["t"])
    return [s for s in (open_setup(state, m, tf) for m in new) if s is not None]


def advance_all(state: dict, p15: dict, t_now: int, pl: dict | None, off: float = 0.0) -> list[str]:
    """Move every open setup along the 15m payload's closed bars; archive the finished ones."""
    bk = book(state)
    markers, ch = p15.get("markers") or [], p15.get("chart") or {}
    out = []
    for s in list(bk["open"]):
        out += advance(s, ch, markers, t_now, pl, off)
    done = [s for s in bk["open"] if s["status"] in FINAL]
    bk["open"] = [s for s in bk["open"] if s["status"] not in FINAL][-OPEN_MAX:]
    bk["log"] = (bk["log"] + done)[-LOG_MAX:]
    return out
