"""W7 (research/registrations/B31b-W7.json): M15 / M30 / H1 / H4 breakout monitoring. NON-DIRECTIONAL MONITORING ONLY.

Every run reads the 15m, 30m, 1h and 4h payloads' CLOSED bars (amendment A2 added 1h / 4h; BREAKOUT_TFS selects) (the forming bar is never in `chart`) and, on each timeframe on its
own, finds every breakout: a bar that CLOSES beyond a live level after the previous bar closed at or inside it (a wick
through a level is not a breakout). Levels, from that timeframe's bars only:

  * previous trading day / week high and low; high and low of the last completed Asia / London / New York session
    (the same pools as quantum/shadow.py);
  * swing highs / lows (pivot 3 bars each side), known at the close of the 3rd bar after the pivot, live 5 trading days;
  * equal highs / lows: two live swings of a side within max($0.50, 0.10 x ATR14) and at least 4 bars apart (the outer
    one is the level), live while both swings are;
  * a range: at bar i, the box of bars i-12 .. i-1 when its height is at most 1.5 x ATR14 and it holds no bar that
    broke an earlier range (amendment A1).

Each level breaks once. One event per bar and side lists every level its close crossed; the REFERENCE level is the one
crossed first (nearest the previous close). Stages, from the bars after it (watch: 16 bars):

  DETECTED     the breakout close;
  CONFIRMED    a displacement close (body >= 1.0 x ATR14 of the bar before, confirmed at once) or acceptance (the next
               two closes stay beyond the level);
  RETEST HELD  after confirmation, a bar reaching back to the level that still closes beyond it;
  FAILED       the first close back inside the level, before or after confirmation;
  CLOSED       the watch ended without a failure (no message).

Each stage goes to the phone once, in the operator's short format, only while its bar is the newest closed bar and the
run is within FRESH_SEC of that close (else it is recorded LATE). ENTRY READY is SHADOW: the registered entry (market at
the confirmation close, E1; and a retest limit at the level, E2) with its stop, targets, size and checks is computed,
recorded and raced to +$10 / +$15 / +$20 on the 15m bars, and shown on the website, never sent: no breakout entry has
been validated (B31b-W3 found none better than matched random entries). Nothing here is a probability. Not an
ENGINE_SOURCES file: the engine, its configuration and the freeze key are untouched; it reads payloads and writes only
its own records (state['brk']).
"""
from __future__ import annotations

import math
import os

import numpy as np
import pandas as pd

from . import sessions, shadow, ta

ID = "B31b-W7"
TFS = {"15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}
TF_LABEL = {"15m": "M15", "30m": "M30", "1h": "H1", "4h": "H4"}
W7_TFS = ("15m", "30m")                        # monitored since the W7 start; A2 timeframes start at their first run
PIVOT, SWING_DAYS = 3, 5
EQ_USD, EQ_ATR, EQ_GAP = 0.50, 0.10, 4
RANGE_BARS, RANGE_ATR = 12, 1.5
DISP_ATR, ACCEPT_BARS, WATCH = 1.0, 2, 16
FRESH_SEC = 1200
SL_BUF, EXT_ATR, ROOM_USD, COST_FRAC = 0.2, 1.0, 10.0, 0.15
RETEST_VALID = 8
TARGETS = (10.0, 15.0, 20.0)
OZ = 100.0
KEEP_EVENTS, BUNDLE_AT = 300, 5
BEYOND_KEEP = 10                               # unbroken same-side levels kept per event for the room check
EPS = 1e-9
STATIC = {1: ("PWH", "PDH", "ASH", "LOH", "NYH"), -1: ("PWL", "PDL", "ASL", "LOL", "NYL")}
RANK = {"PW": 7, "PD": 6, "AS": 5, "LO": 5, "NY": 5, "EQ": 4, "RG": 3, "SW": 2}
NAMES = {"PWH": "prev week high", "PWL": "prev week low", "PDH": "prev day high", "PDL": "prev day low",
         "ASH": "Asia high", "ASL": "Asia low", "LOH": "London high", "LOL": "London low", "NYH": "New York high",
         "NYL": "New York low", "EQH": "equal highs", "EQL": "equal lows", "RGH": "range high", "RGL": "range low",
         "SWH": "swing high", "SWL": "swing low"}
SESSION = {"ASIAN": "Asia", "LONDON": "London", "LONDON+NY": "London+NY", "NEW YORK": "New York", "OFF": "other"}


def mode() -> str:
    """ALERT_BREAKOUTS: unset = phone; 'site' = website only; '0' / 'off' = no breakout monitoring at all."""
    v = (os.environ.get("ALERT_BREAKOUTS") or "").strip().lower()
    return "off" if v in ("0", "off", "no", "false") else ("site" if v == "site" else "phone")


def tfs() -> list[str]:
    """BREAKOUT_TFS (amendment A2): a comma list from 15m, 30m, 1h, 4h; unset = all four; unknown entries are ignored and
    an empty result means all four."""
    want = [x.strip().lower() for x in (os.environ.get("BREAKOUT_TFS") or "").split(",")]
    got = [tf for tf in TFS if tf in want]
    return got or list(TFS)


def _rank(kind: str) -> int:
    return RANK[kind[:2]]


# ---------------- detection: a pure function of closed bars ----------------
def detect(t, o, h, l, c, sec: int) -> tuple[list[dict], dict]:
    """Every breakout on these closed bars, each from the bars closed by its own close. Returns (events, context) where
    context holds the arrays the stages and shadow entries need (atr, session label, cost model)."""
    t = np.asarray(t, np.int64)
    o, h, l, c = (np.asarray(x, float) for x in (o, h, l, c))
    n = len(c)
    ctx = {"n": n}
    if n < RANGE_BARS + 2 * PIVOT + 2:
        return [], ctx
    cal = sessions.calendar(pd.DatetimeIndex(pd.to_datetime(t, unit="s", utc=True)))
    pools, _ = shadow.build_pools(h, l, cal, np.full(n, np.nan), np.full(n, np.nan))
    atr = np.asarray(ta.atr(h, l, c, 14), float)
    dord = pd.factorize(cal["trading_date"])[0]
    sess = shadow.session_label(cal)
    ctx.update(atr=atr, sess=sess, cost=shadow.cost_model(cal))
    ph, pl = ta.pivothigh(h, PIVOT, PIVOT), ta.pivotlow(l, PIVOT, PIVOT)
    start = {k: 0 for s in STATIC for k in STATIC[s]}
    swings = {1: [], -1: []}                       # live swings: {"v", "p", "d", "key"}
    eqs = {1: [], -1: []}                          # live equal highs / lows: {"v", "keys", "key"}
    used: set = set()
    last_rg = -10 ** 9                             # bar of the last range breakout (amendment A1)
    events = []
    for i in range(1, n):
        q = i - 1                                  # a swing reported at bar q's close is usable from bar i
        for s, arr in ((1, ph), (-1, pl)):
            v = arr[q]
            if not np.isfinite(v):
                continue
            p = q - PIVOT
            sw = {"v": float(v), "p": p, "d": int(dord[q]), "key": ("SW", s, p)}
            tol = max(EQ_USD, EQ_ATR * atr[q]) if np.isfinite(atr[q]) else EQ_USD
            for x in swings[s]:
                if p - x["p"] >= EQ_GAP and abs(sw["v"] - x["v"]) <= tol:
                    outer = max(sw["v"], x["v"]) if s == 1 else min(sw["v"], x["v"])
                    eqs[s].append({"v": outer, "keys": (x["key"], sw["key"]), "key": ("EQ", s, x["p"], p)})
            swings[s].append(sw)
        for s in (1, -1):                          # expiry: 5 trading days after the swing became known
            swings[s] = [x for x in swings[s] if x["key"] not in used and dord[i] - x["d"] < SWING_DAYS]
            live = {x["key"] for x in swings[s]}
            eqs[s] = [x for x in eqs[s] if x["key"] not in used and all(k in live for k in x["keys"])]
        for s in STATIC:
            for k in STATIC[s]:
                if not (pools[k][i] == pools[k][i - 1]):
                    start[k] = i
        rg = None
        if i - RANGE_BARS >= 0 and last_rg < i - RANGE_BARS and np.isfinite(atr[i - 1]):
            hb, lb = float(h[i - RANGE_BARS:i].max()), float(l[i - RANGE_BARS:i].min())
            if hb - lb <= RANGE_ATR * atr[i - 1]:
                rg = {1: hb, -1: lb}
        if not (np.isfinite(c[i]) and np.isfinite(c[i - 1])):
            continue
        for s in (1, -1):
            cand = []
            for k in STATIC[s]:
                v = pools[k][i]
                if np.isfinite(v):
                    cand.append((k, float(v), (k, start[k])))
            cand += [(("SWH" if s == 1 else "SWL"), x["v"], x["key"]) for x in swings[s]]
            cand += [(("EQH" if s == 1 else "EQL"), x["v"], x["key"]) for x in eqs[s]]
            if rg is not None:
                cand.append((("RGH" if s == 1 else "RGL"), rg[s], ("RG", s, i)))
            crossed = [x for x in cand if x[2] not in used and s * (c[i] - x[1]) > EPS and s * (c[i - 1] - x[1]) <= EPS]
            if not crossed:
                continue
            for x in crossed:
                used.add(x[2])
                if x[0] in ("RGH", "RGL"):
                    last_rg = i
            ref = min(crossed, key=lambda x: (s * (x[1] - c[i - 1]), -_rank(x[0])))
            prim = max(crossed, key=lambda x: (_rank(x[0]), -s * x[1]))
            a_prev = float(atr[i - 1]) if np.isfinite(atr[i - 1]) else float("nan")
            body = s * (c[i] - o[i])
            beyond = sorted({round(x[1], 2) for x in cand if x[2] not in used and s * (x[1] - c[i]) > EPS},
                            key=lambda v: s * v)
            events.append({"i": i, "t": int(t[i]), "t_close": int(t[i]) + sec, "dir": s, "ref": round(ref[1], 2),
                           "ref_kind": ref[0], "primary": prim[0],
                           "levels": sorted(({"kind": x[0], "price": round(x[1], 2)} for x in crossed),
                                            key=lambda z: (-_rank(z["kind"]), z["price"])),
                           "open": float(o[i]), "high": float(h[i]), "low": float(l[i]), "close": float(c[i]),
                           "atr": a_prev, "body_atr": body / a_prev if a_prev > 0 else float("nan"),
                           "disp": bool(a_prev > 0 and body >= DISP_ATR * a_prev - EPS),
                           "gap": bool(s * (o[i] - ref[1]) > EPS), "sess": str(sess[i]),
                           "beyond": beyond[:BEYOND_KEEP]})
    return events, ctx


def follow(ev: dict, o, h, l, c, n: int | None = None) -> dict:
    """The stages of one event from the bars after it (bars 0 .. n-1 are closed). Indexes, None when not reached."""
    i, s, L = ev["i"], ev["dir"], ev["ref"]
    n = len(c) if n is None else n
    st = {"confirmed": i if ev["disp"] else None, "how": "DISPLACEMENT" if ev["disp"] else None, "retest": None,
          "failed": None, "closed": None}
    for j in range(i + 1, min(i + WATCH, n - 1) + 1):
        if s * (c[j] - L) <= EPS:
            st["failed"] = j
            return st
        if st["confirmed"] is None and j == i + ACCEPT_BARS:
            st["confirmed"], st["how"] = j, "ACCEPTED"
        elif st["confirmed"] is not None and st["retest"] is None and \
                ((l[j] <= L + EPS) if s == 1 else (h[j] >= L - EPS)):   # never the confirmation bar: the branch above
            st["retest"] = j
    if i + WATCH <= n - 1:
        st["closed"] = i + WATCH
    return st


def stage_list(ev: dict, st: dict) -> list[tuple[str, int]]:
    """The phone stages of an event in order: (stage, bar index). A displacement breakout opens with CONFIRMED."""
    out = [] if ev["disp"] else [("DETECTED", ev["i"])]
    if st["confirmed"] is not None:
        out.append(("CONFIRMED", st["confirmed"]))
    if st["retest"] is not None:
        out.append(("RETEST", st["retest"]))
    if st["failed"] is not None:
        out.append(("FAILED", st["failed"]))
    return out


# ---------------- shadow ENTRY READY (never sent) ----------------
def shadow_entries(ev: dict, st: dict, o, h, l, c, ctx: dict, budget: float) -> dict:
    """E1 (market at the confirmation close) and E2 (retest limit at the level, placed at the confirmation close) with the
    registered stop, targets, size and checks; {} before confirmation."""
    k = st["confirmed"]
    if k is None:
        return {}
    i, s, L = ev["i"], ev["dir"], ev["ref"]
    a = ev["atr"] if ev["atr"] > 0 else float(ctx["atr"][k])
    opp = float(l[i:k + 1].min()) if s == 1 else float(h[i:k + 1].max())
    stop = opp - s * SL_BUF * a
    cost = float(ctx["cost"][k])
    out = {}
    for name, e in (("E1", float(c[k])), ("E2", float(L))):
        D = s * (e - stop)
        x = {"entry": round(e, 2), "stop": round(stop, 2), "D": round(D, 2), "cost": round(cost, 2),
             "tp": [round(e + s * T, 2) for T in TARGETS], "placed": int(k)}
        why = []
        if D <= 0:
            why.append("stop on the wrong side")
            lots = 0.0
        else:
            lots = math.floor(budget / ((D + cost) * OZ) / 0.01 + 1e-9) * 0.01
            x["loss_planned"] = round(lots * OZ * (D + cost), 2)
            if lots < 0.01 - EPS:
                why.append(f"stop ${D:.2f} too wide for the ${budget:,.0f} budget")
            if cost > COST_FRAC * D + EPS:
                why.append(f"costs ${cost:.2f} are over 15% of the ${D:.2f} stop")
        x["lots"] = round(lots, 2)
        ext = s * (e - L)
        if ext > EXT_ATR * a + EPS:
            why.append(f"price already ${ext:.2f} beyond the level (over 1 ATR = ${a:.2f})")
        room = [s * (v - e) for v in ev["beyond"] if s * (v - e) > EPS]
        if room and min(room) < ROOM_USD - EPS:
            why.append(f"next level only ${min(room):.2f} away (under $10)")
        x["ready"], x["why"] = not why, why
        out[name] = x
    return out


def race(x: dict, s: int, b15: dict, t_from: int, limit: bool = False, valid_until: int | None = None) -> dict:
    """The shadow entry's fill (a limit: the first 15m bar reaching it after placement; a limit AT the level always
    fills before a close back inside, since that close trades through it) and +$10 / +$15 / +$20 raced separately
    against the stop on the 15m bars after it (a bar touching both = AMBIGUOUS, counted as the stop; a bar opening
    through the stop counts as the stop; a fill bar that also reaches the stop counts as the stop)."""
    t, o, h, l = (b15[k] for k in ("t", "o", "h", "l"))
    j0 = int(np.searchsorted(t, t_from, side="left"))
    e, stop = x["entry"], x["stop"]
    res = {"fill": None, "res": {f"{T:g}": None for T in TARGETS}}
    j = j0
    if limit:
        while j < len(t) and (valid_until is None or t[j] < valid_until):
            if (l[j] <= e + EPS) if s == 1 else (h[j] >= e - EPS):
                e = float(o[j]) if ((o[j] <= e) if s == 1 else (o[j] >= e)) else e
                res["fill"] = {"t": int(t[j]), "px": round(e, 2)}
                if (l[j] <= stop + EPS) if s == 1 else (h[j] >= stop - EPS):
                    res["res"] = {f"{T:g}": ["SL", int(t[j]) + 900] for T in TARGETS}
                    return res
                j += 1
                break
            j += 1
        if res["fill"] is None:
            if j < len(t) or (valid_until is not None and t[-1] + 900 >= valid_until):
                res["fill"] = "MISSED"
            return res
    else:
        res["fill"] = {"t": int(t_from), "px": round(e, 2)}
    for k in range(j, len(t)):
        gap = s * (o[k] - stop) <= 0
        hit_s = gap or ((l[k] <= stop + EPS) if s == 1 else (h[k] >= stop - EPS))
        for T in TARGETS:
            key = f"{T:g}"
            if res["res"][key] is not None:
                continue
            tgt = e + s * T
            hit_t = (h[k] >= tgt - EPS) if s == 1 else (l[k] <= tgt + EPS)
            if hit_s and hit_t and not gap:
                res["res"][key] = ["AMBIGUOUS", int(t[k]) + 900]
            elif hit_s:
                res["res"][key] = ["SL", int(t[k]) + 900]
            elif hit_t:
                res["res"][key] = ["TP", int(t[k]) + 900]
        if all(v is not None for v in res["res"].values()):
            break
    return res


# ---------------- phone text (the operator's short format) ----------------
def _head(ev: dict, tf: str, word: str) -> str:
    dot = "🟢" if ev["dir"] == 1 else "🔴"
    return f"{'⚠️' if word == 'FAILED' else dot} GOLD {TF_LABEL[tf]} {word}"


def message(ev: dict, tf: str, stage: str, bar: dict, fmt, clock) -> list[str]:
    """One stage's phone message. bar: {'c', 't_close'} of the stage's bar. fmt prints a price (MT5 offset applied);
    clock prints a time. No probability, no entry instruction."""
    side = "BUY" if ev["dir"] == 1 else "SELL"
    lv = f"{fmt(ev['ref'])} ({NAMES[ev['ref_kind']]})"
    t = f"Time: {clock(bar['t_close'])}"
    if stage == "DETECTED":
        return [_head(ev, tf, "BREAKOUT"), f"Direction: {side}", f"Level: {lv}", f"Price: {fmt(bar['c'])}",
                "Status: Monitoring", "Entry: Not confirmed", t]
    if stage in ("CONFIRMED", "RETEST"):
        status = ("Retest held" if stage == "RETEST" else
                  "Displacement, retest pending" if bar.get("how") == "DISPLACEMENT" else "Accepted, retest pending")
        return [_head(ev, tf, "CONFIRMED"), f"Direction: {side}", f"Level: {lv}", f"Price: {fmt(bar['c'])}",
                f"Status: {status}", "Action: Wait", "Entry: Not validated", t]
    back = "below" if ev["dir"] == 1 else "above"
    return [_head(ev, tf, "FAILED"), f"Direction: {side}", f"Level: {lv}",
            f"Reason: Price closed back {back} the level", "Action: Cancel setup", t]


def bundle(msgs: list[list[str]]) -> list[list[str]]:
    """More than BUNDLE_AT messages in one run (a fast market or a data burst): one message carrying them all."""
    if len(msgs) <= BUNDLE_AT:
        return msgs
    lines = [f"GOLD: {len(msgs)} breakout updates in this run"]
    for m in msgs:
        lines += ["", *m]
    return [lines]


# ---------------- the live run ----------------
def book(state: dict, t_now: int) -> dict:
    return state.setdefault("brk", {"since": int(t_now), "events": {}})


def since_tf(bk: dict, tf: str, t_now: int) -> int:
    """The first close a timeframe records: the W7 start for M15 / M30, the first monitored run for an A2 timeframe."""
    s = bk.setdefault("since_tf", {})
    if tf not in s:
        s[tf] = int(bk["since"]) if tf in W7_TFS else int(t_now)
    return s[tf]


def _bars(p: dict | None) -> dict | None:
    if not p or (p.get("meta") or {}).get("synthetic"):
        return None
    ch = p.get("chart") or {}
    t = ch.get("t") or []
    if not t or any(len(ch.get(k) or []) != len(t) for k in ("o", "h", "l", "c")):
        return None
    arr = {k: np.array([np.nan if x is None else float(x) for x in ch[k]], float) for k in ("o", "h", "l", "c")}
    ok = np.isfinite(arr["o"]) & np.isfinite(arr["h"]) & np.isfinite(arr["l"]) & np.isfinite(arr["c"])
    return {"t": np.asarray(t, np.int64)[ok], **{k: v[ok] for k, v in arr.items()}}


def scan(state: dict, payloads: dict, t_now: int, budget: float) -> list[dict]:
    """Update the records from this run's closed bars; returns the stages due on the phone now (fresh only)."""
    bk = book(state, t_now)
    due = []
    b15 = _bars(payloads.get("15m"))
    for tf in tfs():
        sec = TFS[tf]
        b = _bars(payloads.get(tf))
        if b is None:
            continue
        since = since_tf(bk, tf, t_now)
        evs, ctx = detect(b["t"], b["o"], b["h"], b["l"], b["c"], sec)
        n = len(b["c"])
        newest = n - 1
        for ev in evs:
            if ev["t_close"] < since:
                continue
            eid = f"BRK:{TF_LABEL[tf]}:{ev['t']}:{'UP' if ev['dir'] == 1 else 'DN'}"
            st = follow(ev, b["o"], b["h"], b["l"], b["c"], n)
            conf_fresh = False
            rec = bk["events"].get(eid)
            if rec is None:
                rec = {"id": eid, "tf": tf, "dir": ev["dir"], "t": ev["t"], "t_close": ev["t_close"], "ref": ev["ref"],
                       "ref_kind": ev["ref_kind"], "primary": ev["primary"], "levels": ev["levels"],
                       "close": round(ev["close"], 2), "sess": ev["sess"], "disp": ev["disp"],
                       "body_atr": None if not math.isfinite(ev["body_atr"]) else round(ev["body_atr"], 2),
                       "stages": {}, "phone": {}}
                bk["events"][eid] = rec
            for stage, j in stage_list(ev, st):
                if stage in rec["stages"]:
                    continue
                tj = int(b["t"][j]) + sec
                rec["stages"][stage] = {"t": tj, "c": round(float(b["c"][j]), 2)}
                if stage == "CONFIRMED":
                    rec["stages"][stage]["how"] = st["how"]
                fresh = j == newest and 0 <= t_now - tj <= FRESH_SEC
                rec["phone"][stage] = "DUE" if fresh else "LATE"
                if stage == "CONFIRMED":
                    conf_fresh = fresh
                if fresh:
                    due.append({"id": eid, "tf": tf, "stage": stage, "ev": ev,
                                "bar": {"c": float(b["c"][j]), "t_close": tj, "how": st["how"]}})
            if st["closed"] is not None and "CLOSED" not in rec["stages"] and "FAILED" not in rec["stages"]:
                rec["stages"]["CLOSED"] = {"t": int(b["t"][st["closed"]]) + sec}
            if st["confirmed"] is not None and "shadow" not in rec:
                rec["shadow"] = shadow_entries(ev, st, b["o"], b["h"], b["l"], b["c"], ctx, budget)
                if not conf_fresh:                 # the registered "fresh data" check: seen too late to act on
                    age = (t_now - rec["stages"]["CONFIRMED"]["t"]) // 60
                    for x in rec["shadow"].values():
                        x["why"].append(f"seen {age} min after the confirmation close (fresh = within {FRESH_SEC // 60} min, newest bar)")
                        x["ready"] = False
            if rec.get("shadow") and b15 is not None:
                k_t = rec["stages"]["CONFIRMED"]["t"]
                for name, x in rec["shadow"].items():
                    if x.get("done"):
                        continue
                    if x["D"] <= 0:                # no valid stop: nothing to race
                        x["done"] = True
                        continue
                    lim = name == "E2"
                    if k_t < int(b15["t"][0]):
                        continue                   # the confirmation is older than this run's 15m bars: kept as it was
                    r = race(x, ev["dir"], b15, k_t, limit=lim, valid_until=k_t + RETEST_VALID * sec if lim else None)
                    x["fill"], x["res"] = r["fill"], r["res"]
                    x["done"] = r["fill"] == "MISSED" or all(v is not None for v in r["res"].values())
    if len(bk["events"]) > KEEP_EVENTS:
        for k in sorted(bk["events"], key=lambda k: bk["events"][k]["t_close"])[:len(bk["events"]) - KEEP_EVENTS]:
            del bk["events"][k]
    return due


def counts(bk: dict, t_now: int, days: int = 7) -> dict:
    """Events and phone results of the last `days` days, by timeframe, direction and session."""
    lo = t_now - days * 86400
    evs = [e for e in bk["events"].values() if e["t_close"] >= lo]
    by = lambda f: {k: sum(1 for e in evs if f(e) == k) for k in sorted({f(e) for e in evs})}  # noqa: E731
    ph = [v for e in evs for v in e["phone"].values()]
    return {"days": days, "events": len(evs), "by_tf": by(lambda e: TF_LABEL[e["tf"]]),
            "by_dir": by(lambda e: "BUY" if e["dir"] == 1 else "SELL"), "by_session": by(lambda e: SESSION.get(e["sess"], e["sess"])),
            "confirmed": sum(1 for e in evs if "CONFIRMED" in e["stages"]),
            "failed_before": sum(1 for e in evs if "FAILED" in e["stages"] and "CONFIRMED" not in e["stages"]),
            "failed_after": sum(1 for e in evs if "FAILED" in e["stages"] and "CONFIRMED" in e["stages"]),
            "retest_held": sum(1 for e in evs if "RETEST" in e["stages"]),
            "phone": {k: ph.count(k) for k in sorted(set(ph))}}


def snapshot(state: dict, t_now: int) -> dict:
    """index.json -> alerts.breakouts: the newest events with their stages, phone results and shadow entries."""
    bk = book(state, t_now)
    recent = sorted(bk["events"].values(), key=lambda e: (e["t_close"], e["tf"]), reverse=True)[:40]
    return {"id": ID, "on": True, "mode": mode(), "t": int(t_now), "since": bk["since"], "since_tf": bk.get("since_tf", {}),
            "tfs": [TF_LABEL[tf] for tf in tfs()], "events": recent,
            "counts": counts(bk, t_now), "watch_bars": WATCH, "fresh_sec": FRESH_SEC,
            "rules": ("A breakout is an M15 / M30 / H1 / H4 bar that CLOSES beyond a level (swing, previous day / week, Asia / London / "
                      "New York session, equal highs / lows, range) after the bar before closed inside it; a wick is not "
                      "enough. CONFIRMED: a displacement close (body at least 1 ATR) or two more closes beyond. FAILED: a "
                      "close back inside within 16 bars of that timeframe. Every session, both directions, each timeframe on its own."),
            "shadow": ("ENTRY READY is computed in SHADOW only (market at the confirmation close, or a limit at the level) "
                       "and never sent: no breakout entry has been validated. B31b-W3 (2020-23) found no breakout entry "
                       "better than matched random entries; B31b-W7 found none with positive expectancy after costs on "
                       "M15 / M30, and no study covers H1 / H4 entries.")}
