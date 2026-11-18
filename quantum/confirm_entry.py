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

Fields on every alert (operator directive 2026-11-15, priority 6): the decision (WAIT / BUY or SELL ENTRY ELIGIBLE / NO
TRADE), the setup's id and times, the data source and the latest price with its age, the trigger price (P0), the
confirmation price, the entry, the +$10 / +$15 / +$20 status, the stop, the targets, what is left to each from the latest
price, net R:R, the lot, the largest loss, the cost split (spread / slippage / commission), the probability status (none:
not calibrated) with the validation reference and its sample size, the live record of these entries, and the expiry.
snapshot() gives the website the same setups and the same phone text, so both show one decision.

Alerts and display only: not an ENGINE_SOURCES file. B15's plans, B9 and every record are unchanged (the B15 plan still
opens at the signal close; its follow-ups are labelled as the engine's record, not an entry). CONFIRM_MIN_USD=0 restores
the previous alerts.
"""
from __future__ import annotations

import math
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
# The validation reference printed with the probability status: B30's models A / B / C (a $10 / $15 / $20 confirming
# close, the plan recalculated from the entry), engine signals, validation + holdout pooled, model cost. Copied from
# research/B30_RESULTS.md section 2; tests/test_confirm_entry.py checks every number against the results file
# research/results/b30_all_partitions_2026-11-15.json. None was supported.
VALIDATION = {10.0: {"model": "A", "n": 48, "tp1": 27, "net_r": 0.00, "boot95": (-0.28, 0.27), "holm_p": 0.81},
              15.0: {"model": "B", "n": 42, "tp1": 23, "net_r": 0.03, "boot95": (-0.26, 0.30), "holm_p": 0.81},
              20.0: {"model": "C", "n": 34, "tp1": 21, "net_r": 0.17, "boot95": (-0.17, 0.46), "holm_p": 0.52}}
VALIDATION_REF = "B30, engine signals out of sample 2023-25, the engine before Amendment F"
VALIDATION_BE = 0.527                  # B30's break-even TP1-first rate for this plan at the model cost
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


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float] | None:
    """The Wilson 95% interval of k successes in n; None without a sample."""
    if n <= 0:
        return None
    p, den = k / n, 1 + z * z / n
    mid, half = (p + z * z / (2 * n)) / den, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, mid - half), min(1.0, mid + half)


TF_SEC = {"15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}


# ---------------- the SETUP alert (replaces the entry lines of a SIGNAL alert) ----------------
def setup_head(m: dict, tf: str, off: float = 0.0, sid: int | None = None) -> str:
    """sid: the C1 setup this signal opened (None on a line that opens none, e.g. a website-only timeframe)."""
    num = f" #{sid}" if sid is not None else ""
    return (f"XAUUSD {tf} {_side(m['dir'])} SETUP DETECTED{num} (signal bar closed {_hm(int(m['t']) + TF_SEC.get(tf, 900))}) | "
            f"WAIT, NOT AN ENTRY | trigger {_px(m['px'], off)}")


def repeat_head(m: dict, tf: str, off: float = 0.0) -> str:
    """A signal that repeats an idea already announced (its REPEAT line follows): still not an entry."""
    return f"XAUUSD {tf} {_side(m['dir'])} signal again (signal bar closed) at {_px(m['px'], off)} | NOT AN ENTRY"


def joined_lines(m: dict, tf: str, s: dict, off: float = 0.0) -> list[str]:
    """A new signal that is the same idea as an open C1 setup (same side, within 4 h and $15): it opens no second
    setup, so the phone names the setup that is being followed and shows that setup's levels, not new ones."""
    d = s["dir"]
    if s["status"] == "PENDING":
        word = "above" if d == 1 else "below"
        now = (f"still waiting for a 15m close at or {word} {_px(s['p0'] + d * s['x'], off)} (+${s['x']:g} beyond its trigger "
               f"{_px(s['p0'], off)})")
    else:
        now = f"already confirmed at {_px(s['conf']['px'], off)}, {_hm(s['conf']['t'])}: its entry alert was sent then"
    return [f"XAUUSD {tf} {_side(d)} signal again (signal bar closed {_hm(int(m['t']) + TF_SEC.get(tf, 900))}) at "
            f"{_px(m['px'], off)} | SAME IDEA AS SETUP #{s['id']}: no new setup | NOT AN ENTRY",
            f"SETUP #{s['id']} is {now}. NO TRADE on this signal."]


def setup_lines(m: dict, off: float = 0.0, s: dict | None = None) -> list[str]:
    """s: the C1 setup the signal opened; with it the lines carry the expiry time and the data source."""
    d, p0, X = m["dir"], m["px"], min_usd()
    word = "above" if d == 1 else "below"
    lv = lambda x: _px(p0 + d * x, off)
    tail = f" | +$15 {lv(15)} preferred | +$20 {lv(20)} ideal" if X < 15 else ""
    cap = f" | a first close more than ${cap_usd():g} beyond expires it" if cap_usd() else ""
    exp = (f"expires after {WIN} 15m bars without a confirming close (24 market hours: not before {_hm(s['t_close'] + WIN * 900)})"
           if s else "expires after 24 h")
    out = [f"WAIT FOR CONFIRMATION: a 15m close at or {word} {lv(X)} (+${X:g} minimum){tail}{cap} | a touch is not a confirmation",
           f"CANCELLED if price trades {_px(p0 - d * INV_USD, off)} (-${INV_USD:g}) or the 15m structure breaks the other way "
           f"first; {exp}"]
    if s and s.get("src"):
        out.append(f"DATA: {s['src']}, {s['tf']} bars; the trigger is the signal bar's close")
    return out + ["NO TRADE until an ENTRY ELIGIBLE alert arrives. " + EVIDENCE]


# ---------------- state ----------------
def book(state: dict) -> dict:
    return state.setdefault("c1", {"seq": 0, "open": [], "log": []})


def same_idea(state: dict, m: dict, tf: str) -> dict | None:
    """The open setup this SIGNAL marker belongs to: the one it opened, or the earlier one it repeats (same side,
    within REPEAT_SEC and REPEAT_USD). None when there is none."""
    if m.get("px") is None or m.get("dir") not in (1, -1):
        return None
    t_close = int(m["t"]) + TF_SEC.get(tf, 900)
    for s in book(state)["open"]:
        if s["dir"] == m["dir"] and t_close - s["t_close"] <= REPEAT_SEC and abs(m["px"] - s["p0"]) <= REPEAT_USD:
            return s
    return None


def open_setup(state: dict, m: dict, tf: str, src: str | None = None) -> dict | None:
    """A new setup from a SIGNAL marker, or None when it repeats an open setup (one idea, one setup). src: the
    payload's price source, kept on the setup so every later alert names where its prices came from."""
    if m.get("px") is None or m.get("dir") not in (1, -1) or same_idea(state, m, tf) is not None:
        return None
    bk = book(state)
    t_close = int(m["t"]) + TF_SEC.get(tf, 900)
    bk["seq"] = int(bk.get("seq", 0)) + 1
    s = {"id": bk["seq"], "tf": tf, "t": int(m["t"]), "t_close": t_close, "dir": int(m["dir"]), "p0": float(m["px"]),
         "status": "PENDING", "scanned": t_close - 900, "touch": {}, "x": min_usd(),
         "events": [["SETUP_DETECTED", t_close, float(m["px"])], ["REFERENCE_SET", t_close, float(m["px"])]]}
    if src:
        s["src"] = str(src)
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
            "over_budget": bool(pl.get("over_budget")), "cost_parts": pl.get("cost_parts"),
            "own_cost_oz": pl["cost_usd"] / oz if oz > 0 and pl.get("cost_usd") is not None else None}


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


def advance(s: dict, ch: dict, markers: list, t_now: int, pl: dict | None, off: float = 0.0, now: dict | None = None,
            rec: dict | None = None) -> list[str]:
    """Moves `s` along its lifecycle on the closed 15m bars it has not seen; returns the phone lines for what changed.
    now: this run's latest price {'px', 't_px', 'live'} (notify.price_now); rec: the live record of earlier entries
    (record()). Both are kept on the confirmation, so the alert and the website print the same figures."""
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
                s["conf"] = {"t": tj + 900, "px": float(c[j]), "move": round(move, 2), "tier": tier(move), "t_alert": int(t_now)}
                if now and now.get("px") is not None and now.get("t_px") is not None:
                    s["conf"]["now"] = {"px": float(now["px"]), "t_px": int(now["t_px"]), "live": bool(now.get("live"))}
                if rec:
                    s["conf"]["rec"] = [int(rec["tp1"]), int(rec["decided"])]
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
        return (f"XAUUSD {s['tf']} {_side(d)} SETUP #{s['id']} {'CANCELLED' if status == 'INVALIDATED' else 'EXPIRED'} (trigger "
                f"{_px(s['p0'], off)}, {_hm(s['t_close'])}): {why} | NO TRADE")
    if status == "REJECTED":
        cf = s.get("conf") or {}
        return (f"XAUUSD {s['tf']} {_side(d)} SETUP #{s['id']} confirmed +${cf.get('move', 0):.2f} ({cf.get('tier', '')}) at "
                f"{_px(cf.get('px', px), off)} but NOT ELIGIBLE: {why} | NO TRADE")
    return f"XAUUSD {s['tf']} {_side(d)} confirmed setup #{s['id']} {status}: {why}"


def ladder_status(s: dict, off: float = 0.0) -> str:
    """The +$10 / +$15 / +$20 status of a setup: closed beyond (the confirming close), touched only, or not reached."""
    d, p0, cf = s["dir"], s["p0"], s.get("conf") or {}
    out = []
    for lv in (10, 15, 20):
        if cf and cf["move"] >= lv - EPS:
            st = "CLOSED BEYOND"
        elif str(lv) in s["touch"]:
            st = f"touched {_hm(s['touch'][str(lv)])[-9:]}, no close beyond"
        else:
            st = "not reached"
        out.append(f"+${lv} {_px(p0 + d * lv, off)} {st}")
    return "CONFIRMATION STATUS: " + " | ".join(out)


def data_line(s: dict, off: float = 0.0) -> str:
    """Where the prices came from, the latest price of the alert's run with its age, and what is left from it to each
    target and to the stop (the plan itself is measured from the entry = the confirming close)."""
    d, p, cf = s["dir"], s["plan"], s["conf"]
    base = f"DATA: {s.get('src') or 'price source not recorded'}, 15m bars | confirming close {_px(cf['px'], off)} at {_hm(cf['t'])}"
    nw = cf.get("now")
    if not nw:
        return base + " | latest price: not available in this run, check your platform"
    mv = (nw["px"] - p["entry"]) * d
    where = "toward TP" if mv > 0 else "toward the stop" if mv < 0 else "unchanged"
    left = [f"TP1 ${(p['tp1'] - nw['px']) * d:.2f}"] + ([f"TP2 ${(p['tp2'] - nw['px']) * d:.2f}"] if p["tp2"] is not None else [])
    return (f"{base} | latest price {_px(nw['px'], off)} ({'live quote' if nw['live'] else 'last closed bar'} read "
            f"{_hm(nw['t_px'])[-9:]}): ${abs(mv):.2f} {where} from the entry | left from it: {', '.join(left)}, "
            f"the stop ${(nw['px'] - p['sl']) * d:.2f}")


def cost_line(p: dict) -> str:
    """The round-trip cost the lot was sized with (the higher of the operator's cost and the research model), split into
    spread, slippage and commission when it is the research model (the feed has no bid / ask, so no live spread exists),
    beside the operator's stated cost. A plan recorded without the split prints the one figure."""
    oz, c = p["lot"] * 100.0, p["size_cost_oz"]
    parts = p.get("cost_parts")
    split = (f"spread ${parts['spread']:.2f} + slippage ${parts['slippage']:.2f} + commission ${parts['commission']:.2f} = "
             if parts else "")
    own = (f" | at your stated ${p['own_cost_oz']:.2f}/oz: ${p['own_cost_oz'] * oz:,.0f}"
           if p.get("own_cost_oz") is not None and abs(p["own_cost_oz"] - c) > EPS else "")
    return (f"COSTS per oz, round trip ({'research model' if parts else 'the higher of your cost and the research model'}; not "
            f"broker-verified; the feed has no bid / ask): {split}${c:.2f} = ${p['cost_usd']:,.0f} at {p['lot']:g} lot{own}")


def valid_line(s: dict) -> str:
    cf = s["conf"]
    return (f"VALID until {_hm(cf['t'] + FRESH_SEC)} ({FRESH_SEC // 60} min after the confirming close; later the price has moved "
            f"on: NO TRADE on this alert) | the record follows the plan for {HOLD} 15m bars (48 market hours), then closes it")


def record(state: dict) -> dict:
    """The live record of ENTRY ELIGIBLE alerts, from the book: an entry is decided when TP1 or the stop came first
    (AMBIGUOUS counts as the stop); a time stop before either is neither. Descriptive: no registered verdict."""
    bk = book(state)
    ent = [x for x in bk["log"] + bk["open"] if x.get("entry_bar") is not None]
    tp1 = sum(1 for x in ent if any(e[0] == "TP1" for e in x["events"]))
    sl = sum(1 for x in ent if x["status"] in ("SL", "AMBIGUOUS"))
    return {"entries": len(ent), "tp1": tp1, "sl": sl, "decided": tp1 + sl,
            "timeout": sum(1 for x in ent if x["status"] == "TIMEOUT" and not any(e[0] == "TP1" for e in x["events"])),
            "open": sum(1 for x in ent if x["status"] == "ACTIVE"), "wilson": wilson(tp1, tp1 + sl)}


def record_text(rec: list | None) -> str:
    """rec: [TP1 first, decided] of the earlier entries, as kept on the confirmation when its alert was written."""
    if not rec or not rec[1]:
        return "live record of these entries: none decided yet"
    lo, hi = wilson(rec[0], rec[1])
    return (f"live record of these entries: TP1 first {rec[0]} of {rec[1]} decided (95% {lo:.0%}-{hi:.0%}); "
            f"descriptive, no verdict")


def probability_line(x: float, rec: list | None = None) -> str:
    """No probability is shown: none is calibrated. The line names that status, the validation reference for this
    confirmation threshold with its sample size, and the live record of these entries."""
    v = VALIDATION.get(float(x))
    if v:
        lo, hi = wilson(v["tp1"], v["n"])
        hist = (f"validation {VALIDATION_REF}: a ${x:g} confirming close reached TP1 first in {v['tp1']} of {v['n']} = "
                f"{v['tp1'] / v['n']:.0%} (95% {lo:.0%}-{hi:.0%}; break-even about {VALIDATION_BE:.0%}), net {v['net_r']:+.2f} R "
                f"({v['boot95'][0]:+.2f} to {v['boot95'][1]:+.2f}), p {v['holm_p']:.2f}: NOT SUPPORTED")
    else:
        hist = f"validation: none at a ${x:g} confirming close (B30 tested $10 / $15 / $20; none was supported)"
    return f"PROBABILITY: none shown, NOT CALIBRATED | {hist} | {record_text(rec)}"


ENTRY_HEAD = " ENTRY ELIGIBLE, SETUP #"                    # the head of an entry alert (eligible_lines)


def eligible_lines(s: dict, off: float = 0.0) -> list[str]:
    """The ENTRY ELIGIBLE alert, from the setup alone (so the website prints the same text from the same record)."""
    d, p, cf = s["dir"], s["plan"], s["conf"]
    tp2 = f" | TP2 {_px(p['tp2'], off)} (the rest; stop to the entry after TP1)" if p["tp2"] is not None else ""
    return [
        f"XAUUSD {s['tf']} {_side(d)}{ENTRY_HEAD}{s['id']}: entry {_px(p['entry'], off)} = the 15m close at "
        f"{_hm(cf['t'])}, +${cf['move']:.2f} ({cf['tier']}) beyond the trigger {_px(s['p0'], off)} ({_hm(s['t_close'])})",
        f"PLAN (recalculated from this entry): entry {_px(p['entry'], off)} | SL {_px(p['sl'], off)} | TP1 {_px(p['tp1'], off)}"
        f"{' (close half)' if p['tp2'] is not None else ''}{tp2}",
        f"RISK: account ${p['account']:,.0f} | {p['risk_pct']:g}% = max ${p['budget']:,.0f} | lot {p['lot']:g} | est. cost "
        f"${p['cost_usd']:,.0f} (${p['size_cost_oz']:.2f}/oz) | loss at the stop incl. cost ${p['risk_usd']:,.0f}",
        f"NET: reward ${p['reward_both_usd']:,.0f} if every target is reached"
        + (f", ${p['reward_tp1_usd']:,.0f} if TP1 then back to the entry" if p["tp2"] is not None else "")
        + f" | net R:R {p['rr_net']:.2f} | a ${p['risk_usd']:,.0f} loss is possible on this trade",
        ladder_status(s, off),
        data_line(s, off),
        cost_line(p),
        valid_line(s),
        probability_line(s["x"], cf.get("rec")),
        "CHECKS passed: fresh close, no opposite structure or signal since the setup, room to TP1, size within the budget. "
        + EVIDENCE]


# ---------------- one run ----------------
def open_from(state: dict, payload: dict, since: int | None, skip: set | None = None) -> list[dict]:
    """Setups from a payload's new SIGNAL markers (confirmation is always read on 15m bars). skip: the bar times of
    signals the phone did not announce as a SETUP (a REPEAT of an open plan, or a NOT ACTIONABLE one), so every later
    CONFIRMED / CANCELLED alert belongs to a SETUP the operator was shown."""
    tf, src = payload["meta"]["tf"], payload["meta"].get("price_source")
    new = sorted((m for m in payload.get("markers") or [] if m["type"] == "SIGNAL" and (since is None or m["t"] > since)
                  and m["t"] not in (skip or ())), key=lambda m: m["t"])
    return [s for s in (open_setup(state, m, tf, src) for m in new) if s is not None]


def advance_all(state: dict, p15: dict, t_now: int, pl: dict | None, off: float = 0.0, now: dict | None = None) -> list[str]:
    """Move every open setup along the 15m payload's closed bars; archive the finished ones. now: this run's latest
    price (see advance). A setup that became ENTRY ELIGIBLE in this run leads the message, so the entry is the first
    line the phone shows (found live 18 Nov 00:36: setup #2's entry came after setup #1's TP1 line); every setup's
    lines stay together and otherwise keep their order."""
    bk = book(state)
    markers, ch = p15.get("markers") or [], p15.get("chart") or {}
    rec = record(state)                                    # the record before this run's changes: what the alert prints
    groups = [advance(s, ch, markers, t_now, pl, off, now, rec) for s in list(bk["open"])]
    entry = [g for g in groups if any(ENTRY_HEAD in x for x in g)]
    out = [x for g in entry + [g for g in groups if not any(ENTRY_HEAD in x for x in g)] for x in g]
    done = [s for s in bk["open"] if s["status"] in FINAL]
    bk["open"] = [s for s in bk["open"] if s["status"] not in FINAL][-OPEN_MAX:]
    bk["log"] = (bk["log"] + done)[-LOG_MAX:]
    return out


# ---------------- the website's copy: the same setups, the same decision, the same phone text ----------------
SNAP_RECENT = 12


def decision(state: dict, t_now: int) -> dict:
    """The one decision the phone and the website show now. An entry is offered only while its ENTRY ELIGIBLE alert is
    valid (FRESH_SEC after the confirming close); a setup waiting for its close is WAIT; anything else is NO TRADE."""
    op = book(state)["open"]
    live = [x for x in op if x["status"] == "ACTIVE" and t_now - x["conf"]["t"] <= FRESH_SEC]
    if live:
        x = max(live, key=lambda x: x["conf"]["t"])
        return {"word": _side(x["dir"]), "id": x["id"], "until": x["conf"]["t"] + FRESH_SEC,
                "why": f"ENTRY ELIGIBLE, setup #{x['id']}: every check passed at the confirming close"}
    wait = [x for x in op if x["status"] == "PENDING"]
    if wait:
        ids = ", ".join(f"#{x['id']} {_side(x['dir'])}" for x in wait)
        return {"word": "WAIT", "id": wait[-1]["id"], "why": f"waiting for a confirming 15m close: setup {ids}. Not an entry"}
    run = [x for x in op if x["status"] in ("ACTIVE", "TP1")]
    if run:
        return {"word": "NO TRADE", "id": None,
                "why": "no new entry: the entry window of setup " + ", ".join(f"#{x['id']}" for x in run) + " has passed"}
    return {"word": "NO TRADE", "id": None, "why": "no setup is open: no qualifying opportunity"}


def _row(x: dict, off: float) -> dict:
    out = {k: x.get(k) for k in ("id", "tf", "dir", "p0", "t_close", "status", "x", "touch", "conf", "plan", "why", "t_done", "src")}
    out["expires_not_before"] = x["t_close"] + WIN * 900   # WIN bars are counted, so a market break moves the expiry later
    out["ladder"] = ladder_status(x, off)
    if x["status"] == "PENDING":
        m = {"dir": x["dir"], "px": x["p0"], "t": x["t"]}
        out["phone"] = [setup_head(m, x["tf"], off, x["id"]), *setup_lines(m, off, x)]
    elif x.get("entry_bar") is not None:
        out["phone"] = eligible_lines(x, off)
    return out


def snapshot(state: dict, t_now: int, off: float = 0.0) -> dict:
    """index.json -> alerts.c1: the open setups, the last finished ones, the live record and the decision."""
    bk = book(state)
    return {"on": on(), "min_usd": min_usd(), "inv_usd": INV_USD, "fresh_sec": FRESH_SEC, "t": int(t_now),
            "decision": decision(state, t_now), "open": [_row(x, off) for x in bk["open"]][::-1],
            "recent": [_row(x, off) for x in bk["log"][::-1][:SNAP_RECENT]], "record": record(state),
            "validation": {"ref": VALIDATION_REF, "break_even": VALIDATION_BE, "rows": {f"{k:g}": v for k, v in VALIDATION.items()}},
            "evidence": EVIDENCE}
