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
  B  CONFIRMATION on the 15m bars that open after the trigger's close (amendment B24-CONFIRM-FWD-A1, 2026-11-10): the
     first CLOSE at least $15 beyond the trigger price in its own direction decides: CONFIRMED if it is no more than $20
     beyond, EXPIRED (overshoot, final) if it is further. Before it, price trading $13 against the trigger price (bar
     high / low) or a 15m BOS / MSS / CHoCH the other way INVALIDATES (checked first, so a bar that does both is
     INVALIDATED). No such close within 96 bars is EXPIRED. A touch never confirms; an intrabar move beyond $20 alone
     neither confirms nor expires. The trigger price is never reset; the direction is never reversed. A later close $20
     beyond (X20) is tracked as a milestone after the confirmation, never as a confirmation.
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

import hashlib
import json
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
X_USD = {"X15": 15.0, "X20": 20.0}     # the confirmation close ($15); X20 = a later $20 close, tracked as a milestone
CAP_USD = 20.0                         # B24-A1: the confirming close at most $20 beyond the trigger price (inclusive)
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
INSUFFICIENT = "INSUFFICIENT DATA — NOT STATISTICALLY VALIDATED"
STATUS_TEXT = {"VALIDATED": "VALIDATED out of sample", "FAILED": "NOT VALIDATED: its registered test failed",
               "INSUFFICIENT": INSUFFICIENT}
LIVE_MIN_N = 30                        # a live record is shown as a rate only from 30 decided results (notify.MIN_N)
AUDIT_FILE = "CONFIRM-LIVE.json"       # <store>/research_forward/: every finished row, kept; copied to forward-ledger
EVENTS_FILE = "CONFIRM-EVENTS.jsonl"   # <store>/research_forward/: every stage event once, hash-chained (append-only)
GENESIS = "GENESIS"

# Measured rates (k reached the target first, n trades), copied from the committed results and checked against them by
# tests/test_confirm_panel.py. Development = 2020-01-24 -> 2023-01-24 (scored from 2020-04-01); validation = 2023-01-24 ->
# 2024-07-01. "at_trigger" = the same plan entered at the trigger price without waiting (no confirmation).
_DEV, _VAL = "2020-22", "2023-24"
EVIDENCE = {
    "ENG": {"label": "engine signal", "study": "B19", "results": "research/results/b19_development_2026-11-07.json",
            "verdict": "INSUFFICIENT: too few confirmed signals (20 in 2020-22, 7 in 2023-24)", "validated": False,
            "status": "INSUFFICIENT",
            "triggers": 64, "confirmed": {"X15": 20, "X20": 19},
            "rates": {"X15 T15": [[12, 20, _DEV]], "X15 T20": [[10, 20, _DEV], [5, 7, _VAL]],
                      "X20 T15": [[9, 19, _DEV]], "X20 T20": [[8, 19, _DEV], [3, 5, _VAL]]},
            "at_trigger": {"T15": [25, 64, _DEV], "T20": [23, 64, _DEV]}, "hold_min": {"T15": 124, "T20": 181},
            "any_time": {"T15": 0.75, "T20": 0.65}},          # research/results/excursions_development_2026-11-07.json
    "GRAB": {"label": "15m liquidity grab", "study": "B21", "results": "research/results/b21_development_2026-11-07.json",
             "verdict": "FAIL (B21 H1 / H2)", "validated": False, "status": "FAILED", "triggers": 855, "confirmed": {"X15": 302, "X20": 238},
             "rates": {"X15 T15": [[131, 302, _DEV]], "X15 T20": [[106, 302, _DEV]],
                       "X20 T15": [[118, 238, _DEV]], "X20 T20": [[94, 238, _DEV]]},
             "at_trigger": {"T15": [404, 855, _DEV], "T20": [339, 855, _DEV]}, "hold_min": {"T15": 271, "T20": 348},
             "any_time": {"T15": 0.699, "T20": 0.553}},
    "BREAK": {"label": "15m liquidity break", "study": "B21", "results": "research/results/b21_development_2026-11-07.json",
              "verdict": "FAIL (B21 H3 / H4)", "validated": False, "status": "FAILED", "triggers": 781, "confirmed": {"X15": 277, "X20": 210},
              "rates": {"X15 T15": [[121, 277, _DEV]], "X15 T20": [[108, 277, _DEV]],
                        "X20 T15": [[101, 210, _DEV]], "X20 T20": [[90, 210, _DEV]]},
              "at_trigger": {"T15": [363, 781, _DEV], "T20": [313, 781, _DEV]}, "hold_min": {"T15": 217, "T20": 279},
              "any_time": {"T15": 0.668, "T20": 0.585}},
    "SWEEP": {"label": "15m sweep setup", "study": "B21", "results": "research/results/b21_development_2026-11-07.json",
              "verdict": "FAIL (B21 H5 / H6)", "validated": False, "status": "FAILED", "triggers": 2928, "confirmed": {"X15": 949, "X20": 757},
              "rates": {"X15 T15": [[437, 949, _DEV]], "X15 T20": [[363, 949, _DEV]],
                        "X20 T15": [[351, 757, _DEV]], "X20 T20": [[289, 757, _DEV]]},
              "at_trigger": {"T15": [1358, 2928, _DEV], "T20": [1172, 2928, _DEV]}, "hold_min": {"T15": 249, "T20": 332},
              "any_time": {"T15": 0.670, "T20": 0.550}},
    "BREAKOUT": {"label": "15m breakout setup", "study": "B21", "results": "research/results/b21_development_2026-11-07.json",
                 "verdict": "FAIL (B21 H7 / H8)", "validated": False, "status": "FAILED", "triggers": 2882, "confirmed": {"X15": 958, "X20": 763},
                 "rates": {"X15 T15": [[464, 958, _DEV]], "X15 T20": [[389, 958, _DEV]],
                           "X20 T15": [[364, 763, _DEV]], "X20 T20": [[306, 763, _DEV]]},
                 "at_trigger": {"T15": [1333, 2882, _DEV], "T20": [1139, 2882, _DEV]}, "hold_min": {"T15": 221, "T20": 305},
                 "any_time": {"T15": 0.690, "T20": 0.590}},
    "4H": {"label": "4h candle breakout (all four)", "study": "B18", "results": "research/results/b18_development_2026-11-06.json",
           "verdict": "FAIL at the trigger (B18); after a $15 confirmation: not measured", "validated": False,
           "status": "INSUFFICIENT", "triggers": 319,
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


def confirm_one(P: dict, j0: int, p0: float, d: int, X: float, s: float = 1.0, start: int | None = None,
                cap: float | None = None) -> dict:
    """Stage B on the 15m bars j0 .. j0 + 95: CONFIRMED at bar k (the first close >= X beyond p0), INVALIDATED (price:
    $13 against on a bar's high / low; structure: an opposite BOS / MSS / CHoCH at a bar's close), EXPIRED, or PENDING
    while the window is still open. s scales the $ distances (p0 / 4000 in the research test, 1 live). start: the first
    bar to examine (live: the first bar not examined by an earlier run; the bars before it had no event).
    cap (B24-A1): when that first close is more than cap beyond p0 the setup is EXPIRED with why "overshoot" and the move
    in `move` ($): final, so a later close back inside the band never confirms. cap=None is B19's uncapped rule (the
    research parity tests use it)."""
    n = len(P["t"])
    for b in range(j0 if start is None else max(j0, start), min(j0 + WIN, n)):
        adv = (p0 - P["l"][b]) if d > 0 else (P["h"][b] - p0)
        inv_p = adv >= INV_USD * s - EPS
        inv_s = bool(P["dn"][b] if d > 0 else P["up"][b])
        if inv_p or inv_s:
            return {"status": "INVALIDATED", "k": -1, "at": b, "why": "price" if inv_p else "structure"}
        mv = (P["c"][b] - p0) * d
        if mv >= X * s - EPS:
            if cap is not None and mv > cap * s + EPS:
                return {"status": "EXPIRED", "k": -1, "at": b, "why": "overshoot", "move": float(mv / s)}
            return {"status": "CONFIRMED", "k": b, "at": b, "why": ""}
    if j0 + WIN <= n:
        return {"status": "EXPIRED", "k": -1, "at": j0 + WIN - 1, "why": "no close beyond within 96 bars"}
    return {"status": "PENDING", "k": -1, "at": n - 1, "why": ""}


def exit_one(P: dict, k: int, d: int, T: float, s: float = 1.0, entry: float | None = None, start: int | None = None,
             mfe0: float = 0.0, mae0: float = 0.0, stop: float | None = None, hold: int | None = None) -> dict:
    """The trade entered at bar k's close (or at `entry`): TP / SL / AMBIGUOUS / TIMEOUT as B19's exit, OPEN while bars are missing.
    mfe / mae: the largest move for / against the entry ($) on the trade's bars, the exit bar included but capped at the
    level that closed the trade (a bar touching both levels counts the target and the stop); the last bar while OPEN."""
    n = len(P["t"])
    e = float(P["c"][k]) if entry is None else float(entry)      # entry: a price other than bar k's close (research only)
    stop_px = SL_USD if stop is None else float(stop)               # B24 also tracks other stop distances
    hold = HOLD if hold is None else int(hold)                      # bars of the path given (5m paths: 576 = 48 h)
    tp, sl = e + d * T * s, e - d * stop_px * s
    mfe, mae = float(mfe0), float(mae0)                           # carried from the bars an earlier run examined
    for b in range(k + 1 if start is None else max(k + 1, start), min(k + 1 + hold, n)):
        o, h, lo_ = P["o"][b], P["h"][b], P["l"][b]
        o_sl, o_tp = (o - sl) * d <= 0, (o - tp) * d >= 0
        hit_sl = (lo_ <= sl) if d > 0 else (h >= sl)
        hit_tp = (h >= tp) if d > 0 else (lo_ <= tp)
        fav, adv = ((h - e) if d > 0 else (e - lo_)), ((e - lo_) if d > 0 else (h - e))
        if o_sl or o_tp or hit_sl or hit_tp:
            out = "SL" if o_sl else "TP" if o_tp else "AMBIGUOUS" if (hit_sl and hit_tp) else "TP" if hit_tp else "SL"
            px = o if (o_sl or o_tp) else (tp if out == "TP" else sl)
            if out == "TP":                     # the exit bar counts up to the level that closed the trade
                mfe, mae = max(mfe, abs(px - e)), max(mae, min(adv, stop_px * s))
            elif out == "SL":
                mfe, mae = max(mfe, min(fav, T * s)), max(mae, abs(px - e))
            else:
                mfe, mae = max(mfe, T * s), max(mae, stop_px * s)
            return {"out": out, "bar": b, "px": float(px), "usd": float((px - e) * d), "mfe": float(mfe), "mae": float(mae)}
        mfe, mae = max(mfe, fav), max(mae, adv)          # max(x, nan) keeps x: a missing bar adds nothing
    if k + 1 + hold <= n:
        b = k + hold
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
def _at(t: list, ts) -> int | None:
    """Index of the bar opening at ts, or None."""
    if ts is None:
        return None
    k = bisect_left(t, int(ts))
    return k if k < len(t) and t[k] == int(ts) else None


def evaluate(P: dict, row: dict, votes: list, s: float = 1.0) -> dict:
    """Advance a tracked trigger on the 15m bars that no earlier run examined (each closed bar is examined once, as a live
    state machine would). A decision already shown (confirmation, entry, invalidation, expiry, an exit) never changes.
    If the feed has revised a bar an earlier run examined, so that a full recomputation would decide differently, the
    row keeps what was shown and carries `revised` (the research parity holds whenever no bar is revised)."""
    t = P["t"]
    n = len(t)
    j0 = bisect_left(t, row["t_close"])
    d, p0 = row["dir"], row["p0"]
    out = {"confirm_at": round(p0 + d * X_USD["X15"] * s, 2), "invalid_at": round(p0 - d * INV_USD * s, 2),
           "cap_at": round(p0 + d * CAP_USD * s, 2), "confirm20_at": round(p0 + d * X_USD["X20"] * s, 2)}
    if j0 >= n:
        return {**out, "status": "PENDING", "bars": 0}
    nxt = t[-1] + 900                                             # the open of the first bar no run has examined yet
    if row.get("status") != "CONFIRMED":                          # stage B still open (final rows are in the log)
        js = j0 if row.get("scan_t") is None else bisect_left(t, row["scan_t"])
        c15 = confirm_one(P, j0, p0, d, X_USD["X15"], s, start=js, cap=CAP_USD)
        full = confirm_one(P, j0, p0, d, X_USD["X15"], s, cap=CAP_USD)
        if (full["status"], full["k"]) != (c15["status"], c15["k"]) and full["status"] != "PENDING":
            out["revised"] = (f"the feed revised a bar an earlier run examined: recomputed from the start it would read "
                              f"{full['status'].lower()}; the row keeps what was shown")
        out["status"], out["bars"] = c15["status"], min(n, j0 + WIN) - j0
        out["scan_t"] = nxt if c15["status"] == "PENDING" else None
        if c15["status"] == "INVALIDATED":
            out["why"] = ("price traded $13 against first" if c15["why"] == "price" else "an opposite 15m structure break came first")
            out["t_done"] = t[c15["at"]] + 900
        elif c15["status"] == "EXPIRED" and c15["why"] == "overshoot":
            out["overshoot_usd"] = round(c15["move"], 2)
            out["why"] = (f"the first 15m close $15 beyond was ${c15['move']:.2f} beyond the trigger price: over the "
                          f"${CAP_USD:.0f} cap, so no entry (no chasing)")
            out["t_done"] = t[c15["at"]] + 900
        elif c15["status"] == "EXPIRED":
            out["why"], out["t_done"] = "no 15m close $15 beyond within 96 bars", t[c15["at"]] + 900
        if c15["status"] != "CONFIRMED":
            out["checks"] = checks(P, row, j0, min(n - 1, max(j0, c15["at"])), votes) if c15["status"] == "PENDING" else None
            return out
        k = c15["k"]
        e = float(P["c"][k])
        out.update(t_conf=t[k] + 900, entry=round(e, 2), entry_px=e, move_usd=round((e - p0) * d, 2), sl=round(e - d * SL_USD * s, 2),
                   tp1=round(e + d * TP_USD["T15"] * s, 2), tp2=round(e + d * TP_USD["T20"] * s, 2),
                   rr1=TP_USD["T15"] / SL_USD, rr2=TP_USD["T20"] / SL_USD, checks=checks(P, row, j0, k, votes))
        prev_res: dict = {}
    else:                                                         # confirmed earlier: the entry stays as shown
        k = _at(t, row["t_conf"] - 900)
        if k is None:
            return {"revised": "the confirming bar is no longer in the feed; the row keeps what was shown"}
        e = float(row["entry_px"])
        if abs(float(P["c"][k]) - e) > 1e-9:
            out["revised"] = "the feed revised the confirming bar after the entry was shown; the entry stays as shown"
        prev_res = dict(row.get("result") or {})
    x20 = row.get("x20") or {}
    if x20.get("status") in (None, "PENDING"):                    # the $20 close, tracked beside it the same way
        c20 = confirm_one(P, j0, p0, d, X_USD["X20"], s, start=j0 if x20.get("scan_t") is None else bisect_left(t, x20["scan_t"]))
        x20 = {"status": c20["status"], "scan_t": nxt if c20["status"] == "PENDING" else None,
               **({"t": t[c20["k"]] + 900, "px": round(float(P["c"][c20["k"]]), 2)} if c20["status"] == "CONFIRMED" else {})}
    out["x20"] = x20
    res = {}
    for nm, T in TP_USD.items():
        pr = prev_res.get(nm) or {}
        if pr.get("out") not in (None, "OPEN"):
            res[nm] = pr                                           # an exit already shown never changes
            continue
        st0 = bisect_left(t, pr["scan_t"]) if pr.get("scan_t") is not None else None
        x = exit_one(P, k, d, T, s, entry=e, start=st0, mfe0=pr.get("mfe_px") or 0.0, mae0=pr.get("mae_px") or 0.0)
        res[nm] = {"out": x["out"], "usd": _r(x["usd"]), "mfe": _r(x["mfe"]), "mae": _r(x["mae"]), "mfe_px": x["mfe"],
                   "mae_px": x["mae"], "t": t[x["bar"]] + 900 if x["out"] != "OPEN" else None,
                   "scan_t": nxt if x["out"] == "OPEN" else None}
    out["status"] = "CONFIRMED"
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
    if st == "STALE":
        return "NO TRADE", (row.get("why", "stale") + ("; it was confirmed, but its exits were never reached on the chart"
                                                        if row.get("t_conf") is not None else "; never confirmed"))
    if ev.get("validated"):
        return "TRADE", "confirmed; this type has a validated out-of-sample success rate above break-even"
    label = STATUS_TEXT[ev.get("status", "INSUFFICIENT")]
    r = ev.get("rates", {}).get("X15 T15")
    if r:
        m = rate(*r[-1][:2])
        why = (f"confirmed, but {label}: +$15 before -$13 after a $15 confirmation was {m['p']:.0%} of {m['n']} trades "
               f"({r[-1][2]}, 95% {m['lo']:.0%}-{m['hi']:.0%}) against a break-even of {break_even(15.0):.1%}; {ev['verdict']}")
    else:
        why = f"confirmed, but {label}: this type's rate after a confirmation was never measured; {ev.get('verdict', '')}"
    return NO_TRADE, why


# ---------------- the run ----------------
def _key_t(key: str) -> tuple[str, int]:
    _, tf, t, _ = key.split("|")
    return tf, int(t)


def panel(payloads: dict, state: dict, t_now: int, s: float = 1.0, store_dir: str | None = None) -> dict:
    """Update state["confirm"] (rows being tracked, the log of finished ones) and return the site block. With store_dir,
    every row that finished in this run is appended to <store>/research_forward/CONFIRM-LIVE.json (never trimmed)."""
    p15 = _ok(payloads.get("15m"))
    x15 = [rate(*v["rates"]["X15 T15"][-1][:2])["p"] for v in EVIDENCE.values() if v["rates"].get("X15 T15")]
    rnd = RANDOM["rates"]["X15 T15"]
    base = {"on": True, "mode": "SHADOW",
            "rule": ("research/registrations/B19.json (F0, E1, S13) with the $15-$20 confirmation cap of "
                     "research/registrations/B24-CONFIRM-FWD-A1.json, run live by quantum/confirm_panel.py"),
            "cap_usd": CAP_USD,
            "evidence": EVIDENCE, "random": RANDOM, "break_even": {"T15": break_even(15.0), "T20": break_even(20.0)},
            "op_cost": OP_COST, "model_cost": list(MODEL_COST), "check_text": CHECK_TEXT, "no_trade": NO_TRADE,
            "x_usd": X_USD, "tp_usd": TP_USD, "sl_usd": SL_USD, "inv_usd": INV_USD, "win_bars": WIN, "hold_bars": HOLD,
            "status_text": STATUS_TEXT, "insufficient": INSUFFICIENT, "live_min_n": LIVE_MIN_N}
    top_k, top = max(((k, v["rates"]["X15 T15"][-1]) for k, v in EVIDENCE.items() if v["rates"].get("X15 T15")),
                     key=lambda kv: kv[1][0] / kv[1][1])
    tm = rate(*top[:2])
    sub = (f"No signal type has a validated success rate above break-even ({break_even(15.0):.1%} for +$15 before -$13 at "
           f"your ${OP_COST:.2f} cost). Measured with the original rule (no $20 cap) after a $15 confirmation: +$15 first "
           f"{min(x15):.0%}-{max(x15):.0%} for the "
           f"alert types (the top figure is {top[0]} of {top[1]} {EVIDENCE[top_k]['label']} trades, {top[2]}, 95% "
           f"{tm['lo']:.0%}-{tm['hi']:.0%}: {STATUS_TEXT[EVIDENCE[top_k]['status']]}, not a proven accuracy), "
           f"{rnd[0] / rnd[1]:.0%} for random triggers.")
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
    src = (p15.get("meta") or {}).get("price_source") or "unknown"
    for r in keep + done:
        r.setdefault("data_source", f"{src} 15m bars (closed bars only)")
    log = (log + done)[-LOG_MAX:]
    st["rows"], st["log"] = keep[-200:], log
    if store_dir and done:
        audit(store_dir, done, st["started"])
    if store_dir:
        log_events(store_dir, keep + done, st, t_now)
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
            "events": st.get("events_status"), "t": t_now}


def setup_id(r: dict) -> str:
    """A setup's id in the event log, from the trigger itself (type, timeframe, signal bar, direction), so it never depends
    on the panel's state: a lost or reset state file cannot reuse an id."""
    return f"CF-{r['kind']}-{r['tf']}-{int(r['t'])}-{'B' if r['dir'] > 0 else 'S'}"


EXIT_REASON = {"TP": "target", "SL": "stop", "AMBIGUOUS": "target and stop in one bar (counted as the stop)",
               "TIMEOUT": "time stop (192 bars)"}


def events_of(r: dict) -> list[dict]:
    """The stage events a row has reached, in order. Each carries the bar time at which it happened (never the run time):
    SETUP (stage A), CONFIRMED (stage B) and X20_CLOSE (a later close $20 beyond: a milestone, not a confirmation),
    INVALIDATED / EXPIRED (no trade; an overshoot of the $20 cap is EXPIRED with its move), EXIT_T15 / EXIT_T20 (each
    target's result, P&L in $ of price per oz before costs, and after the operator's measured cost), COMPLETED, or STALE
    (the bars left the chart first: NO TRADE before a confirmation, UNRESOLVED after one)."""
    base = {"setup_id": setup_id(r), "panel_no": r.get("id"), "kind": r["kind"], "tf": r["tf"],
            "direction": "BUY" if r["dir"] > 0 else "SELL", "trigger_price": r["p0"], "trigger_utc": r["t_close"],
            "data_source": r.get("data_source"),
            "flags": [f for f in ("backfill", "late", "vanished") if r.get(f)] + (["revised"] if r.get("revised") else [])}
    ev = [{"event": "SETUP", "event_utc": r["t_close"], "confirm_at": r.get("confirm_at"), "invalid_at": r.get("invalid_at"),
           "what": r.get("what")}]
    st, conf = r.get("status"), r.get("t_conf") is not None
    if conf:
        ev.append({"event": "CONFIRMED", "event_utc": r["t_conf"], "confirmation_price": r["entry"], "confirmation_utc": r["t_conf"],
                   "move_usd": r.get("move_usd"), "entry": r["entry"], "sl": r["sl"], "tp1": r["tp1"], "tp2": r["tp2"]})
        x20 = r.get("x20") or {}
        if x20.get("status") == "CONFIRMED":
            ev.append({"event": "X20_CLOSE", "event_utc": x20["t"], "close_price": x20["px"],
                       "note": "a later 15m close $20 beyond the trigger price: a milestone after the confirmation"})
        for nm in ("T15", "T20"):
            x = (r.get("result") or {}).get(nm) or {}
            if x.get("out") not in (None, "OPEN"):
                ev.append({"event": f"EXIT_{nm}", "event_utc": x.get("t"), "target": nm, "outcome": x["out"],
                           "exit_reason": EXIT_REASON.get(x["out"], x["out"]), "pnl_usd_per_oz": x.get("usd"),
                           "pnl_after_operator_cost": _r(x["usd"] - OP_COST) if x.get("usd") is not None else None})
    if st == "CONFIRMED" and r.get("t_done") is not None:
        ev.append({"event": "COMPLETED", "event_utc": r["t_done"]})
    elif st in ("INVALIDATED", "EXPIRED") or (st == "STALE" and not conf):
        ev.append({"event": st, "event_utc": r.get("t_done"), "outcome": "NO TRADE", "exit_reason": r.get("why"),
                   **({"overshoot_usd": r["overshoot_usd"]} if r.get("overshoot_usd") is not None else {})})
    elif st == "STALE":
        ev.append({"event": "STALE", "event_utc": r.get("t_done"), "outcome": "UNRESOLVED",
                   "exit_reason": "confirmed, but its 15m bars left the chart before every exit was reached"})
    return [{**base, **e, "event_id": f"{base['setup_id']}-{e['event']}"} for e in ev]


def _sha(line: bytes) -> str:
    return hashlib.sha256(line).hexdigest()


def _read_events(path: str, head: dict | None = None) -> tuple[bool, str, str, int, set]:
    """(intact, why, sha of the last line, count, event ids). Intact = every line parses, seq counts from 1 and each prev
    is the SHA-256 of the line before it (a torn, edited, inserted, removed or reordered line breaks it). A chain alone
    cannot show that lines were cut from its END, so head = the last line this panel wrote ({seq, sha}, kept in the
    state): the log must still hold that line unchanged, or it was truncated, deleted or replaced."""
    prev, n, ids, shas = GENESIS, 0, set(), []
    if os.path.exists(path):
        with open(path, "rb") as fh:
            for n, ln in enumerate((x.rstrip(b"\n") for x in fh if x.strip()), 1):
                try:
                    rec = json.loads(ln)
                except ValueError:
                    return False, f"event {n} breaks the chain (not valid JSON)", prev, n, ids
                if not isinstance(rec, dict) or rec.get("seq") != n or rec.get("prev") != prev:
                    return False, f"event {n} breaks the chain", prev, n, ids
                ids.add(rec.get("event_id"))
                prev = _sha(ln)
                shas.append(prev)
    if head and head.get("seq"):
        hs = int(head["seq"])
        if n < hs:
            return False, (f"the log holds {n} events but this panel last wrote event {hs}: truncated or deleted"), prev, n, ids
        if shas[hs - 1] != head.get("sha"):
            return False, f"event {hs} is not the line this panel wrote: replaced", prev, n, ids
    if not n:
        return True, "no events yet", prev, 0, ids
    return True, f"{n} events, chain intact", prev, n, ids


def verify_events(path: str, head: dict | None = None) -> tuple[bool, str]:
    ok, why, *_ = _read_events(path, head)
    return ok, why


def log_events(store_dir: str, rows: list[dict], st: dict, t_now: int) -> int:
    """Append each row's events that the log does not hold yet (by event id, read from the log itself, so a lost state
    file or a crashed run can neither duplicate nor skip one). Never rewrites or removes a line; refuses to append to a
    broken chain, and the panel then shows why (state["confirm"]["events_status"])."""
    path = os.path.join(store_dir, "research_forward", EVENTS_FILE)
    ok, why, prev, seq, have = _read_events(path, st.get("events_head"))
    if not ok:
        st["events_status"] = {"file": EVENTS_FILE, "ok": False, "why": why + "; nothing appended"}
        return 0
    new = []
    for r in rows:
        for e in events_of(r):
            if e["event_id"] in have:
                continue
            seq += 1
            line = json.dumps(notify.json_safe({"seq": seq, "prev": prev, "logged_utc": t_now, **e}), allow_nan=False).encode()
            new.append(line)
            prev = _sha(line)
            have.add(e["event_id"])
    if new:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "ab") as fh:
            fh.write(b"".join(x + b"\n" for x in new))
            fh.flush()
            os.fsync(fh.fileno())
    if seq:
        st["events_head"] = {"seq": seq, "sha": prev}                  # the anchor for the next run's check
    st["events_status"] = {"file": EVENTS_FILE, "ok": True, "why": f"{seq} events, chain intact", "appended": len(new)}
    return len(new)


def audit(store_dir: str, done: list[dict], started: int) -> None:
    """Append the rows that finished in this run to the durable audit file (accepted and rejected alike)."""
    path = os.path.join(store_dir, "research_forward", AUDIT_FILE)
    rec = {"rule": "research/registrations/B19.json (F0, E1, S13), run live by quantum/confirm_panel.py",
           "started_utc": started, "rows": []}
    if os.path.exists(path):
        with open(path) as f:
            rec = json.load(f)
    have = {r["key"] for r in rec["rows"]}
    rec["rows"] += [notify.json_safe({k: v for k, v in r.items() if k not in ("checks",)}) for r in done if r["key"] not in have]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rec, f, indent=1)
    os.replace(tmp, path)


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
        if st == "CONFIRMED" or r.get("t_conf") is not None:
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
