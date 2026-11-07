"""The two-stage confirmation panel: trigger -> $15 / $20 confirmation -> plan, with an acceptance verdict (display only).

Beside the high-confidence panel (quantum/confirm.py, the nine-layer approval of the engine's last bar), this panel
follows EVERY live trigger type through the stages the operator asked to see separately: a possible direction (the
trigger), confirmation pending, a confirmed entry, and the validated (here: measured) move after it.

Operator master instruction 2026-11-07, sections 3, 5 and 7; research/QUANTUM5_REEVALUATION.md section 7. The rule is
B19's (research/registrations/B19.json: confirmation F0, entry E1, stop S13) run live on the site's bars, so the panel
shows exactly what was measured:

  A  TRIGGER: an engine SIGNAL on 15m / 30m / 1h / 4h (ENG, as B19), a 15m liquidity GRAB or BREAK (as B21 / B10), a
     15m SWEEP or BREAKOUT setup (as B21 / B16), or a 4h candle breakout with all four confirmations (as B18). One per
     idea per type: the same direction within 4 hours and $15 of an earlier kept trigger of that type is folded into it
     (the live REPEAT rule).
  B  CONFIRMATION on the 15m bars that open after the trigger's close: the first CLOSE at least $15 beyond the trigger
     price in its own direction (X15; X20 = $20 is tracked beside it), before price trades $13 against the trigger price
     (bar high / low) or a 15m BOS / MSS / CHoCH prints the other way. A touch never confirms; a bar that does both is
     INVALIDATED; no such close within 96 bars is EXPIRED. The direction is never reversed.
  PLAN after an X15 confirmation: entry at the confirming close; SL -$13, TP1 +$15, TP2 +$20 from that entry, each
     target resolved on the 15m bars after it as in B19 (a gap fills at the open; a bar touching both levels is
     AMBIGUOUS and counts as a loss; time stop after 192 bars).

ACCEPTANCE: a confirmed trigger is ACCEPTED only when its type has a registered out-of-sample PASS (EVIDENCE[kind]
["validated"]), the same standard as the high-confidence panel's layer L6. No type has one (B19 ENG: too few; B21: all FAIL; B18: FAIL; B23: FAIL), so the verdict is
NO TRADE - INSUFFICIENT CONFIRMATION, and the probabilities shown are the measured rates with 95% intervals. The
confidence score is a count of checks, never a probability. Every trigger keeps the run that first saw it: one that
appears on a bar an earlier run already had is flagged (repainting), and one that later disappears stays as it was seen.

Display only: nothing here reaches the phone, the plans, the B9 / B15 tests or the engine; not an ENGINE_SOURCES file.
"""
from __future__ import annotations

import math
import os
from bisect import bisect_left

import numpy as np

from . import notify, ta

TF_SEC = {"15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}
ENG_TFS = ("15m", "30m", "1h", "4h")
STRUCT = ("BOS", "MSS", "CHoCH")
WIN, HOLD = 96, 192                    # confirmation window and holding window, 15m bars (B19)
INV_USD, SL_USD = 13.0, 13.0           # invalidation before confirmation; stop after it ($, B19 S13)
X_USD = {"X15": 15.0, "X20": 20.0}     # confirmation closes
TP_USD = {"T15": 15.0, "T20": 20.0}    # targets from the entry
REPEAT_SEC, REPEAT_USD = 4 * 3600, 15.0
EPS = 1e-9
SHOW_SEC = 3 * 86400                   # finished rows stay on the panel this long
LOG_MAX, SEEN_SEC = 500, 10 * 86400
OP_COST = 0.26                         # the operator's measured round trip, $ per oz (PLAN_COST_PER_LOT 26 per 100 oz)
MODEL_COST = (0.77, 0.97)              # the research cost model, $ per oz (spread + 2 x slippage + commission)
RSI_BUY, RSI_SELL, RANGE_ATR, GAP_ATR = 55.0, 45.0, 2.5, 0.5     # B19 F1's momentum and calm checks (score only)
SESSIONS_LIQUID = ("London", "London+NY", "New York")
NO_TRADE = "NO TRADE — INSUFFICIENT CONFIRMATION"

# Measured rates (k reached the target first, n trades), copied from the committed results and checked against them by
# tests/test_confirm_panel.py. Development = 2020-01-24 -> 2023-01-24 (scored from 2020-04-01); validation = 2023-01-24 ->
# 2024-07-01. "at_trigger" = the same plan entered at the trigger price without waiting (no confirmation).
_DEV, _VAL = "2020-22", "2023-24"
EVIDENCE = {
    "ENG": {"label": "engine signal", "study": "B19", "results": "research/results/b19_development_2026-11-07.json",
            "verdict": "INSUFFICIENT: too few confirmed signals (20 in 2020-22, 7 in 2023-24)", "validated": False,
            "triggers": 64, "confirmed": {"X15": 20, "X20": 19},
            "rates": {"X15 T15": [[12, 20, _DEV]], "X15 T20": [[10, 20, _DEV], [5, 7, _VAL]],
                      "X20 T15": [[9, 19, _DEV]], "X20 T20": [[8, 19, _DEV], [3, 5, _VAL]]},
            "at_trigger": {"T15": [25, 64, _DEV], "T20": [23, 64, _DEV]}, "hold_min": {"T15": 124, "T20": 181}, "any_time": None},
    "GRAB": {"label": "15m liquidity grab", "study": "B21", "results": "research/results/b21_development_2026-11-07.json",
             "verdict": "FAIL (B21 H1 / H2)", "validated": False, "triggers": 855, "confirmed": {"X15": 302, "X20": 238},
             "rates": {"X15 T15": [[131, 302, _DEV]], "X15 T20": [[106, 302, _DEV]],
                       "X20 T15": [[118, 238, _DEV]], "X20 T20": [[94, 238, _DEV]]},
             "at_trigger": {"T15": [404, 855, _DEV], "T20": [339, 855, _DEV]}, "hold_min": {"T15": 271, "T20": 348},
             "any_time": {"T15": 0.699, "T20": 0.553}},
    "BREAK": {"label": "15m liquidity break", "study": "B21", "results": "research/results/b21_development_2026-11-07.json",
              "verdict": "FAIL (B21 H3 / H4)", "validated": False, "triggers": 781, "confirmed": {"X15": 277, "X20": 210},
              "rates": {"X15 T15": [[121, 277, _DEV]], "X15 T20": [[108, 277, _DEV]],
                        "X20 T15": [[101, 210, _DEV]], "X20 T20": [[90, 210, _DEV]]},
              "at_trigger": {"T15": [363, 781, _DEV], "T20": [313, 781, _DEV]}, "hold_min": {"T15": 217, "T20": 279},
              "any_time": {"T15": 0.668, "T20": 0.585}},
    "SWEEP": {"label": "15m sweep setup", "study": "B21", "results": "research/results/b21_development_2026-11-07.json",
              "verdict": "FAIL (B21 H5 / H6)", "validated": False, "triggers": 2928, "confirmed": {"X15": 949, "X20": 757},
              "rates": {"X15 T15": [[437, 949, _DEV]], "X15 T20": [[363, 949, _DEV]],
                        "X20 T15": [[351, 757, _DEV]], "X20 T20": [[289, 757, _DEV]]},
              "at_trigger": {"T15": [1358, 2928, _DEV], "T20": [1172, 2928, _DEV]}, "hold_min": {"T15": 249, "T20": 332},
              "any_time": {"T15": 0.670, "T20": 0.550}},
    "BREAKOUT": {"label": "15m breakout setup", "study": "B21", "results": "research/results/b21_development_2026-11-07.json",
                 "verdict": "FAIL (B21 H7 / H8)", "validated": False, "triggers": 2882, "confirmed": {"X15": 958, "X20": 763},
                 "rates": {"X15 T15": [[464, 958, _DEV]], "X15 T20": [[389, 958, _DEV]],
                           "X20 T15": [[364, 763, _DEV]], "X20 T20": [[306, 763, _DEV]]},
                 "at_trigger": {"T15": [1333, 2882, _DEV], "T20": [1139, 2882, _DEV]}, "hold_min": {"T15": 221, "T20": 305},
                 "any_time": {"T15": 0.690, "T20": 0.590}},
    "4H": {"label": "4h candle breakout (all four)", "study": "B18", "results": "research/results/b18_development_2026-11-06.json",
           "verdict": "FAIL at the trigger (B18); after a $15 confirmation: not measured", "validated": False, "triggers": 319,
           "confirmed": None, "rates": {}, "at_trigger": {"T15": [146, 319, _DEV]}, "hold_min": None, "any_time": None},
}
RANDOM = {"label": "random triggers, same pipeline (B21 N2)", "confirmed_share": 5263 / 16384,
          "rates": {"X15 T15": [2386, 5263], "X15 T20": [2012, 5263], "X20 T15": [1876, 4102], "X20 T20": [1584, 4102]},
          "at_trigger": {"T15": [7581, 16384], "T20": [6428, 16384]}}


def on() -> bool:
    return os.environ.get("CONFIRM_PANEL", "1").strip() != "0"


def _ok(p: dict | None) -> dict | None:
    return p if p and not (p.get("meta") or {}).get("synthetic") and (p.get("chart") or {}).get("t") else None


def _f(a: list | None, n: int) -> np.ndarray:
    a = list(a or [])[:n]
    return np.array([math.nan if x is None else float(x) for x in a] + [math.nan] * (n - len(a)), float)


def _r(x, nd: int = 2):
    """A finite number rounded, else None (index.json must not carry NaN: the browser's JSON.parse rejects it)."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, nd) if math.isfinite(x) else None


def rate(k: int, n: int) -> dict:
    lo, hi = notify._wilson(k, n) if n else (math.nan, math.nan)
    return {"k": int(k), "n": int(n), "p": k / n if n else None, "lo": lo if n else None, "hi": hi if n else None}


def break_even(T: float, cost: float = OP_COST) -> float:
    return (SL_USD + cost) / (SL_USD + T)


# ---------------- the 15m path ----------------
def path(p15: dict) -> dict:
    ch = p15["chart"]
    t = [int(x) for x in ch["t"]]
    n = len(t)
    o, h, lo_, c = (_f(ch.get(k), n) for k in ("o", "h", "l", "c"))
    up, dn = np.zeros(n, bool), np.zeros(n, bool)
    at = {tt: k for k, tt in enumerate(t)}
    for m in p15.get("markers") or []:
        k = at.get(m.get("t"))
        if k is not None and m.get("type") in STRUCT and m.get("dir") in (1, -1):
            (up if m["dir"] == 1 else dn)[k] = True
    rsi = _f(ch.get("rsi"), n) if ch.get("rsi") else np.asarray(ta.rsi(c, 14), float)
    ema20 = _f(ch.get("ema20"), n) if ch.get("ema20") else np.asarray(ta.ema(c, 20), float)
    sweep_dir = {at[m["t"]]: int(m["dir"]) for m in p15.get("markers") or []
                 if m.get("type") == "SWEEP" and m.get("t") in at and m.get("dir") in (1, -1)}
    return {"t": t, "o": o, "h": h, "l": lo_, "c": c, "up": up, "dn": dn, "atr": np.asarray(ta.atr(h, lo_, c, 14), float),
            "rsi": rsi, "ema20": ema20, "sweep_dir": sweep_dir}


def confirm_one(P: dict, j0: int, p0: float, d: int, X: float, s: float = 1.0) -> dict:
    """Stage B on the 15m bars j0 .. j0 + 95: CONFIRMED at bar k (the first close >= X beyond p0), INVALIDATED (price:
    $13 against on a bar's high / low; structure: an opposite BOS / MSS / CHoCH at a bar's close), EXPIRED, or PENDING
    while the window is still open. s scales the $ distances (p0 / 4000 in the research test, 1 live)."""
    n = len(P["t"])
    for b in range(j0, min(j0 + WIN, n)):
        adv = (p0 - P["l"][b]) if d > 0 else (P["h"][b] - p0)
        inv_p = adv >= INV_USD * s - EPS
        inv_s = bool(P["dn"][b] if d > 0 else P["up"][b])
        if inv_p or inv_s:
            return {"status": "INVALIDATED", "k": -1, "at": b, "why": "price" if inv_p else "structure"}
        if (P["c"][b] - p0) * d >= X * s - EPS:
            return {"status": "CONFIRMED", "k": b, "at": b, "why": ""}
    if j0 + WIN <= n:
        return {"status": "EXPIRED", "k": -1, "at": j0 + WIN - 1, "why": "no close beyond within 96 bars"}
    return {"status": "PENDING", "k": -1, "at": n - 1, "why": ""}


def exit_one(P: dict, k: int, d: int, T: float, s: float = 1.0, entry: float | None = None) -> dict:
    """The trade entered at bar k's close (or at `entry`): TP / SL / AMBIGUOUS / TIMEOUT as B19's exit, OPEN while bars are missing.
    mfe / mae: the largest move for / against the entry ($) on the trade's bars, the exit bar included but capped at the
    level that closed the trade (a bar touching both levels counts the target and the stop); the last bar while OPEN."""
    n = len(P["t"])
    e = float(P["c"][k]) if entry is None else float(entry)      # entry: a price other than bar k's close (research only)
    tp, sl = e + d * T * s, e - d * SL_USD * s
    mfe = mae = 0.0
    for b in range(k + 1, min(k + 1 + HOLD, n)):
        o, h, lo_ = P["o"][b], P["h"][b], P["l"][b]
        o_sl, o_tp = (o - sl) * d <= 0, (o - tp) * d >= 0
        hit_sl = (lo_ <= sl) if d > 0 else (h >= sl)
        hit_tp = (h >= tp) if d > 0 else (lo_ <= tp)
        fav, adv = ((h - e) if d > 0 else (e - lo_)), ((e - lo_) if d > 0 else (h - e))
        if o_sl or o_tp or hit_sl or hit_tp:
            out = "SL" if o_sl else "TP" if o_tp else "AMBIGUOUS" if (hit_sl and hit_tp) else "TP" if hit_tp else "SL"
            px = o if (o_sl or o_tp) else (tp if out == "TP" else sl)
            if out == "TP":                     # the exit bar counts up to the level that closed the trade
                mfe, mae = max(mfe, abs(px - e)), max(mae, min(adv, SL_USD * s))
            elif out == "SL":
                mfe, mae = max(mfe, min(fav, T * s)), max(mae, abs(px - e))
            else:
                mfe, mae = max(mfe, T * s), max(mae, SL_USD * s)
            return {"out": out, "bar": b, "px": float(px), "usd": float((px - e) * d), "mfe": float(mfe), "mae": float(mae)}
        mfe, mae = max(mfe, fav), max(mae, adv)          # max(x, nan) keeps x: a missing bar adds nothing
    if k + 1 + HOLD <= n:
        b = k + HOLD
        px = float(P["c"][b])                           # unrounded, as B19 (the display rounds); None if the bar is missing
        ok = math.isfinite(px)
        return {"out": "TIMEOUT", "bar": b, "px": px if ok else None, "usd": (px - e) * d if ok else None, "mfe": float(mfe), "mae": float(mae)}
    return {"out": "OPEN", "bar": n - 1, "px": None, "usd": None, "mfe": float(mfe), "mae": float(mae)}


# ---------------- stage A ----------------
def _trig(kind: str, tf: str, t: int, t_close: int, d: int, p0: float, what: str) -> dict:
    return {"key": f"{kind}|{tf}|{t}|{d}", "kind": kind, "tf": tf, "t": int(t), "t_close": int(t_close), "dir": int(d),
            "p0": round(float(p0), 2), "what": what}


def scan(payloads: dict) -> list[dict]:
    """Every trigger in the site's charts (the alerts' own functions, with a fresh 'seen' so nothing is marked)."""
    out = []
    for tf in ENG_TFS:
        p = _ok(payloads.get(tf))
        if p is None:
            continue
        for m in p.get("markers") or []:
            if m.get("type") == "SIGNAL" and m.get("dir") in (1, -1) and m.get("px") is not None:
                tq = m.get("tq")
                out.append(_trig("ENG", tf, m["t"], int(m["t"]) + TF_SEC[tf], m["dir"], m["px"],
                                 f"engine {tf} signal" + (f", TQ {tq:.0f}" if isinstance(tq, (int, float)) else "")))
    p = _ok(payloads.get("15m"))
    if p is not None:
        for e in notify.liquidity_events(p, None, {}):
            if e.get("close") is None:
                continue
            low = e["name"] not in notify._HIGHS
            d = (1 if low else -1) if e["kind"] == "GRAB" else (-1 if low else 1)
            verb = "swept and rejected" if e["kind"] == "GRAB" else "broken"
            out.append(_trig(e["kind"], "15m", e["t"], e["t"] + 900, d, e["close"], f"{e['name']} {e['px']:.2f} {verb}"))
        for e in notify.setup_scan(payloads, None, {}):
            nm = ", ".join(f"{a} {b:.2f}" for a, b in e["levels"])
            out.append(_trig(e["kind"], "15m", e["t"], e["t"] + 900, e["dir"], e["close"], f"{e['kind'].lower()} at {nm}"))
    for e in notify.h4_scan(payloads, None):
        if e.get("confirmed"):                                       # B18 measured the breakouts with all four only
            out.append(_trig("4H", "4h", e["t"], e["t_close"], e["dir"], e["close"],
                             f"4h close {'above' if e['dir'] > 0 else 'below'} the previous 4h "
                             f"{'high' if e['dir'] > 0 else 'low'} {(e['prev_high'] if e['dir'] > 0 else e['prev_low']):.2f}"))
    return sorted(out, key=lambda x: (x["t_close"], -TF_SEC[x["tf"]]))


def repeat_of(x: dict, kept: list[dict], s: float = 1.0) -> dict | None:
    for k in kept[::-1]:
        if k["kind"] == x["kind"] and k["dir"] == x["dir"] and 0 <= x["t_close"] - k["t_close"] <= REPEAT_SEC \
                and abs(x["p0"] - k["p0"]) <= REPEAT_USD * s:
            return k
    return None


# ---------------- the checks (a score, not a probability) ----------------
def checks(P: dict, row: dict, j0: int, k: int, votes: list) -> dict:
    d = row["dir"]
    v = votes[k] if 0 <= k < len(votes) else None
    rsi, ema, atr = P["rsi"][k], P["ema20"][k], P["atr"][k]
    c, o, h, lo_ = P["c"][k], P["o"][k], P["h"][k], P["l"][k]
    cp = P["c"][k - 1] if k >= 1 else math.nan
    same = P["up"] if d > 0 else P["dn"]
    i_trig = j0 - 1
    liq = row["kind"] in ("GRAB", "BREAK", "SWEEP", "BREAKOUT", "4H") or any(
        P["sweep_dir"].get(b) == d for b in range(max(0, i_trig - 15), i_trig + 1))
    return {"trend": v is not None and v == 3 * d,
            "structure": bool(same[j0:k + 1].any()) if k >= j0 else False,
            "momentum": bool(np.isfinite(rsi) and (rsi >= RSI_BUY if d > 0 else rsi <= RSI_SELL)),
            "ema20": bool(np.isfinite(ema) and (c - ema) * d > 0),
            "calm": bool(np.isfinite(atr) and (h - lo_) <= RANGE_ATR * atr and np.isfinite(cp) and abs(o - cp) <= GAP_ATR * atr),
            "liquidity": bool(liq),
            "session": notify.session_of(int(P["t"][k]) + 900) in SESSIONS_LIQUID}


CHECK_TEXT = {"trend": "1h, 4h and daily trend all agree", "structure": "a 15m structure break in the trade's direction",
              "momentum": "RSI14 >= 55 (BUY) / <= 45 (SELL)", "ema20": "close beyond the 15m EMA20",
              "calm": "bar range <= 2.5 ATR and no gap > 0.5 ATR", "liquidity": "began at a liquidity / level event",
              "session": "London or New York (lower spread)"}


# ---------------- one row ----------------
def evaluate(P: dict, row: dict, votes: list, s: float = 1.0) -> dict:
    """Recompute a tracked trigger's state from the 15m bars (closed bars only: the result can only move forward)."""
    t = P["t"]
    j0 = bisect_left(t, row["t_close"])
    d, p0 = row["dir"], row["p0"]
    out = {"confirm_at": round(p0 + d * X_USD["X15"] * s, 2), "invalid_at": round(p0 - d * INV_USD * s, 2),
           "confirm20_at": round(p0 + d * X_USD["X20"] * s, 2)}
    if j0 >= len(t):
        return {**out, "status": "PENDING", "bars": 0}
    c15, c20 = confirm_one(P, j0, p0, d, X_USD["X15"], s), confirm_one(P, j0, p0, d, X_USD["X20"], s)
    out["status"], out["bars"] = c15["status"], min(len(t), j0 + WIN) - j0
    if c15["status"] == "INVALIDATED":
        out["why"] = ("price traded $13 against first" if c15["why"] == "price" else "an opposite 15m structure break came first")
        out["t_done"] = t[c15["at"]] + 900
    elif c15["status"] == "EXPIRED":
        out["why"], out["t_done"] = "no 15m close $15 beyond within 96 bars", t[c15["at"]] + 900
    out["x20"] = {"status": c20["status"], **({"t": t[c20["k"]] + 900, "px": round(float(P["c"][c20["k"]]), 2)}
                                            if c20["status"] == "CONFIRMED" else {})}
    k = c15["k"]
    if c15["status"] != "CONFIRMED":
        out["checks"] = checks(P, row, j0, min(len(t) - 1, max(j0, c15["at"])), votes) if c15["status"] == "PENDING" else None
        return out
    e = float(P["c"][k])
    out.update(t_conf=t[k] + 900, entry=round(e, 2), sl=round(e - d * SL_USD * s, 2),
               tp1=round(e + d * TP_USD["T15"] * s, 2), tp2=round(e + d * TP_USD["T20"] * s, 2),
               rr1=TP_USD["T15"] / SL_USD, rr2=TP_USD["T20"] / SL_USD, checks=checks(P, row, j0, k, votes))
    res = {}
    for nm, T in TP_USD.items():
        x = exit_one(P, k, d, T, s)
        res[nm] = {"out": x["out"], "usd": _r(x["usd"]), "mfe": _r(x["mfe"]), "mae": _r(x["mae"]),
                   "t": t[x["bar"]] + 900 if x["out"] != "OPEN" else None}
    out["result"] = res
    if all(r["out"] != "OPEN" for r in res.values()):
        out["t_done"] = max(r["t"] for r in res.values())
    return out


def verdict(row: dict) -> tuple[str, str]:
    st, ev = row.get("status"), EVIDENCE.get(row["kind"], {})
    if st == "PENDING":
        return "WAIT", f"not confirmed: needs a 15m close at {row['confirm_at']:.2f} before {row['invalid_at']:.2f}"
    if st in ("INVALIDATED", "EXPIRED"):
        return "NO TRADE", row.get("why", st.lower())
    if ev.get("validated"):
        return "TRADE", "confirmed; this type has a validated out-of-sample success rate above break-even"
    r = ev.get("rates", {}).get("X15 T15")
    if r:
        m = rate(*r[-1][:2])
        why = (f"confirmed, but this type is not validated: +$15 first {m['p']:.0%} of {m['n']} ({r[-1][2]}, 95% "
               f"{m['lo']:.0%}-{m['hi']:.0%}) against a break-even of {break_even(15.0):.1%}; {ev['verdict']}")
    else:
        why = f"confirmed, but this type's rate after confirmation was never measured; {ev.get('verdict', '')}"
    return NO_TRADE, why


# ---------------- the run ----------------
def _key_t(key: str) -> tuple[str, int]:
    _, tf, t, _ = key.split("|")
    return tf, int(t)


def panel(payloads: dict, state: dict, t_now: int, s: float = 1.0) -> dict:
    """Update state["confirm"] (rows being tracked, the log of finished ones) and return the site block."""
    p15 = _ok(payloads.get("15m"))
    x15 = [rate(*v["rates"]["X15 T15"][-1][:2])["p"] for v in EVIDENCE.values() if v["rates"].get("X15 T15")]
    rnd = RANDOM["rates"]["X15 T15"]
    base = {"on": True, "rule": "research/registrations/B19.json (F0, E1, S13), run live by quantum/confirm_panel.py",
            "evidence": EVIDENCE, "random": RANDOM, "break_even": {"T15": break_even(15.0), "T20": break_even(20.0)},
            "op_cost": OP_COST, "model_cost": list(MODEL_COST), "check_text": CHECK_TEXT, "no_trade": NO_TRADE,
            "x_usd": X_USD, "tp_usd": TP_USD, "sl_usd": SL_USD, "inv_usd": INV_USD, "win_bars": WIN, "hold_bars": HOLD}
    sub = (f"No signal type has a validated success rate above break-even ({break_even(15.0):.1%} for +$15 before -$13 at "
           f"your ${OP_COST:.2f} cost). Measured after a $15 confirmation: +$15 first {min(x15):.0%}-{max(x15):.0%} for the "
           f"alert types, {rnd[0] / rnd[1]:.0%} for random triggers.")
    if p15 is None:
        return {**base, "headline": NO_TRADE, "sub": sub + " No 15m bars this run.", "rows": [], "record": {}}
    P = path(p15)
    t0 = P["t"][0]
    st = state.setdefault("confirm", {})
    backfill = "started" not in st
    st.setdefault("started", t_now)
    rows, log, seen = list(st.get("rows", [])), list(st.get("log", [])), dict(st.get("seen", {}))
    last_bar = dict(st.get("last_bar", {}))
    starts = {tf: int(p["chart"]["t"][0]) for tf in ENG_TFS for p in [_ok(payloads.get(tf))] if p is not None}
    found = scan(payloads)
    present = {x["key"] for x in found}
    for x in found:
        if x["key"] in seen:
            continue
        seen[x["key"]] = t_now
        if x["t_close"] < t0 or (backfill and x["t_close"] < t_now - SHOW_SEC):
            continue                                                 # older than the 15m bars (or the first run's window)
        rp = repeat_of(x, rows + log[-60:], s)
        if rp is not None:
            rp["repeats"] = int(rp.get("repeats", 0)) + 1
            continue
        st["seq"] = int(st.get("seq", 0)) + 1
        lb = last_bar.get(x["tf"])
        rows.append({**x, "id": st["seq"], "seen": t_now, "backfill": backfill,
                     "late": (not backfill) and lb is not None and x["t"] <= lb, "repeats": 0})
    votes = notify.trend_votes(P["t"], (_ok(payloads.get("1h")) or {}).get("chart"), (_ok(payloads.get("4h")) or {}).get("chart"))
    keep, done = [], []
    for r in rows:
        if r["t"] >= starts.get(r["tf"], t0) and r["key"] not in present:
            r["vanished"] = True                                     # was seen, no longer in the chart: kept as seen
        if r["t_close"] >= t0:
            r.update(evaluate(P, r, votes, s))
        elif r.get("t_done") is None:
            r.update(status="STALE", why="its 15m bars left the chart before it finished", t_done=t_now)
        r["verdict"], r["reason"] = verdict(r)
        (done if r.get("t_done") is not None else keep).append(r)
    log = (log + done)[-LOG_MAX:]
    st["rows"], st["log"] = keep[-200:], log
    st["seen"] = {k: v for k, v in seen.items() if _key_t(k)[1] >= starts.get(_key_t(k)[0], t0)}
    for tf, p in ((tf, _ok(payloads.get(tf))) for tf in ENG_TFS):
        if p is not None:
            last_bar[tf] = int(p["chart"]["t"][-1])
    st["last_bar"] = last_bar
    shown = sorted(keep + [r for r in log if r.get("t_done", 0) >= t_now - SHOW_SEC], key=lambda r: r["t_close"], reverse=True)
    accepted = [r for r in keep if r["verdict"] == "TRADE"]
    pend = sum(r["status"] == "PENDING" for r in keep)
    running = sum(r["status"] == "CONFIRMED" for r in keep)
    head = f"TRADE \u2014 {'BUY' if accepted[-1]['dir'] > 0 else 'SELL'} #{accepted[-1]['id']}" if accepted else NO_TRADE
    pn = notify.price_now(payloads, "15m")
    return {**base, "headline": head, "sub": sub, "pending": pend, "running": running, "rows": shown[:20],
            "record": record(log, st["started"]), "started_utc": st["started"], "price_now": pn["px"] if pn else None,
            "t": t_now}


def record(log: list[dict], started: int) -> dict:
    """The live record since the panel started (descriptive; no verdict is drawn from it). Backfilled rows excluded."""
    out: dict = {}
    for r in log:
        if r.get("backfill") or r["t_close"] < started:
            continue
        g = out.setdefault(r["kind"], {"triggers": 0, "confirmed": 0, "invalidated": 0, "expired": 0,
                                         "T15": [0, 0], "T20": [0, 0]})
        g["triggers"] += 1
        st = r.get("status")
        if st == "CONFIRMED":
            g["confirmed"] += 1
            for nm in ("T15", "T20"):
                o = ((r.get("result") or {}).get(nm) or {}).get("out")
                if o in ("TP", "SL", "AMBIGUOUS", "TIMEOUT"):
                    g[nm][1] += 1
                    g[nm][0] += o == "TP"
        elif st == "INVALIDATED":
            g["invalidated"] += 1
        elif st == "EXPIRED":
            g["expired"] += 1
    return out
