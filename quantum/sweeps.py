"""W7 amendment A3 (research/registrations/B31b-W7.json): every liquidity SWEEP on the 15m timeline. MONITORING ONLY.

On every closed 15m bar, a live level L on side s (s = +1: a level above, buy-side liquidity; s = -1: below, sell-side)
is SWEPT when the bar trades beyond it, CLOSES back at or inside it, and the bar before closed at or inside it. A close
beyond the level is a breakout (quantum/breakouts.py), not a sweep. Levels:

  * M15: every live level exactly as the breakout monitor builds it on 15m bars (previous day / week, last Asia /
    London / New York session, swings, equal highs / lows, 12-bar range);
  * M30, H1, H4: their swing, equal-high / low and range levels, built on that timeframe's own bars by the same code,
    as they stand at the OPEN of the higher-timeframe bar holding the 15m bar (no look-ahead). Day, week and session
    levels come from M15 only: they are the same prices on every timeframe.

Each level instance is alerted once; one event per 15m bar and side lists every level swept. From the sweep close, in
the reversal direction: MOVE +$10 / +$15 / +$20 when a later closed 15m bar reaches it before any bar trades at or
beyond the wick extreme; FAILED when the extreme is traded first (a bar touching both, or opening beyond the extreme,
counts as FAILED); the watch ends after 96 15m bars (24 h). The prices are where a move of that size would be
confirmed, not forecasts, and a MOVE reports what already happened. Nothing here is a probability, a size or an order:
B31b-W3 found sweep reversals no better than matched random entries. Not an ENGINE_SOURCES file; writes only
state['brk']['sw'].
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import breakouts as B
from . import sessions, ta
from .data import store as _store

ID = "B31b-W7-A3"
LEVEL_TFS = {"15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}
TF_RANK = {"15m": 0, "30m": 1, "1h": 2, "4h": 3}
STRUCT = ("SWH", "SWL", "EQH", "EQL", "RGH", "RGL")
HOLD = 96                                      # 15m bars watched after the sweep (24 h)
BAR = 900
KEEP = 300
WILSON_MIN = 30                                # intervals shown once this many are decided
EPS = B.EPS
# W7 amendment A4 (display only): the session / trend / value / dollar / yield context of each sweep (B31b-W12 part B)
_LON, _NY = ZoneInfo("Europe/London"), ZoneInfo("America/New_York")
BOUNDS = (("Asia open", timezone.utc, 0, 0), ("London open", _LON, 8, 0), ("New York open", _NY, 8, 30),
          ("London close", _LON, 16, 30), ("New York close", _NY, 17, 0))
WINDOW_MIN, RUN_BARS = 60, 4
POC_BIN = 0.50                                 # $ at $4,000
MACRO_STALE = 3 * 3600                         # a series whose last completed hour ended longer ago shows "closed"
MACRO = (("dxy", "DX-Y.NYB_60m"), ("us10y", "^TNX_60m"))
PATTERN_LINE = "Session sweep after a run (2020-23): +$10 first 26%, needs 33%: no edge"


def mode() -> str:
    """ALERT_SWEEPS: unset = phone; 'site' = website only; '0' / 'off' = no sweep monitoring at all."""
    v = (os.environ.get("ALERT_SWEEPS") or "").strip().lower()
    return "off" if v in ("0", "off", "no", "false") else ("site" if v == "site" else "phone")


def _live_on_15m(t15: np.ndarray, b: dict, sec: int) -> list:
    """For each 15m bar: the swing / equal / range levels of a higher timeframe live at the open of its bar holding the
    15m bar (the still-forming one after its last close), as {side: [(kind, price, key)]}, or None."""
    live: dict = {}
    B.detect(b["t"], b["o"], b["h"], b["l"], b["c"], sec, live)
    live = {i: {s: [x for x in v.get(s, []) if x[0] in STRUCT] for s in (1, -1)} for i, v in live.items()}
    tt, n = b["t"], len(b["t"])
    out = []
    for t0 in t15:
        j = int(np.searchsorted(tt, t0, side="right")) - 1
        if j < 0:
            out.append(None)
        elif t0 < tt[j] + sec:
            out.append(live.get(j))
        elif j == n - 1:
            out.append(live.get(n))
        else:
            out.append(None)                     # a 15m bar in a gap of the higher timeframe's bars
    return out


def detect(b15: dict, higher: dict) -> list[dict]:
    """Every sweep on these closed 15m bars, each from the bars closed by its own close. higher: {tf: bars} for 30m / 1h
    / 4h (any may be missing)."""
    t, o, h, l, c = (b15[k] for k in ("t", "o", "h", "l", "c"))
    n = len(c)
    live15: dict = {}
    _, ctx = B.detect(t, o, h, l, c, BAR, live15)
    if n < 2 or "sess" not in ctx:
        return []
    src = {"15m": [live15.get(k) for k in range(n)]}
    for tf, b in higher.items():
        if b is not None and tf in LEVEL_TFS and tf != "15m":
            src[tf] = _live_on_15m(t, b, LEVEL_TFS[tf])
    swept: set = set()
    events = []
    for k in range(1, n):
        if not (np.isfinite(c[k]) and np.isfinite(c[k - 1])):
            continue
        for s in (1, -1):
            ext = float(h[k] if s == 1 else l[k])
            hits = []
            for tf in LEVEL_TFS:
                lv = (src.get(tf) or [None] * n)[k]
                for kind, v, key in (lv or {}).get(s, []):
                    if (tf, key) in swept:
                        continue
                    if s * (ext - v) > EPS and s * (c[k] - v) <= EPS and s * (c[k - 1] - v) <= EPS:
                        hits.append((tf, kind, float(v), (tf, key)))
            if not hits:
                continue
            swept.update(x[3] for x in hits)
            ref = max(hits, key=lambda x: (B._rank(x[1]), TF_RANK[x[0]], s * x[2]))
            a = ctx["atr"][k - 1]
            events.append({"id": f"SWP:{int(t[k])}:{'HI' if s == 1 else 'LO'}", "i": k, "t": int(t[k]),
                           "t_close": int(t[k]) + BAR, "side": s, "dir": -s, "ref": round(ref[2], 2), "ref_kind": ref[1],
                           "ref_tf": ref[0], "wick": round(ext, 2), "close": round(float(c[k]), 2),
                           "levels": sorted(({"tf": x[0], "kind": x[1], "price": round(x[2], 2)} for x in hits),
                                            key=lambda z: (-B._rank(z["kind"]), -TF_RANK[z["tf"]], z["price"])),
                           "atr": None if not np.isfinite(a) else round(float(a), 2), "sess": str(ctx["sess"][k])})
    return events


def follow(ev: dict, b15: dict) -> tuple[dict, bool]:
    """+$10 / +$15 / +$20 from the sweep close in the reversal direction, each against the wick extreme, on the 15m
    bars of the watch (B.race: a bar touching both or opening beyond the extreme counts as the extreme). Returns
    ({'10': None | [result, bar close], ...}, watch over)."""
    cut = ev["t_close"] + HOLD * BAR
    j = int(np.searchsorted(b15["t"], cut, side="left"))
    sub = {k: b15[k][:j] for k in ("t", "o", "h", "l")}
    r = B.race({"entry": ev["close"], "stop": ev["wick"]}, ev["dir"], sub, ev["t_close"])
    return r["res"], int(b15["t"][-1]) + BAR >= cut


def stages(res: dict, t_close: int) -> list[tuple[str, int]]:
    """SWEEP, MOVE10 / MOVE15 / MOVE20 (target first) and FAILED (the extreme first, before +$20), in time order."""
    out = [("SWEEP", t_close)]
    for T, v in res.items():
        if v and v[0] == "TP":
            out.append((f"MOVE{T}", int(v[1])))
    fails = [int(v[1]) for v in res.values() if v and v[0] in ("SL", "AMBIGUOUS")]
    if fails:
        out.append(("FAILED", min(fails)))
    return sorted(out, key=lambda x: (x[1], x[0] == "FAILED"))


# ---------------- context (W7 amendment A4: display only, never changes a sweep or its outcome) ----------------
def nearest_boundary(t: int) -> tuple[str, float]:
    """The session boundary nearest to epoch second t: (name, minutes from it to t; negative = before it)."""
    d0 = datetime.fromtimestamp(t, timezone.utc).date()
    best = ("", math.inf)
    for dd in (-1, 0, 1):
        d = d0 + pd.Timedelta(days=dd)
        for name, tz, hh, mm in BOUNDS:
            b = datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz).timestamp()
            if abs(t - b) < abs(best[1]):
                best = (name, t - b)
    return best[0], best[1] / 60.0


def tpo_poc(lo: np.ndarray, hi: np.ndarray, bin_usd: float) -> float | None:
    """Time-at-price POC: each bar's range spread equally over the bins it covers; the mid of the fullest bin."""
    if not len(lo) or bin_usd <= 0:
        return None
    base = math.floor(float(np.min(lo)) / bin_usd)
    acc = np.zeros(math.floor(float(np.max(hi)) / bin_usd) - base + 1)
    for a, b in zip(lo, hi):
        i0, i1 = math.floor(a / bin_usd) - base, math.floor(b / bin_usd) - base
        acc[i0:i1 + 1] += 1.0 / (i1 - i0 + 1)
    return (base + int(np.argmax(acc)) + 0.5) * bin_usd


def macro_from_store(store_dir: str | None) -> dict:
    """The store's Yahoo 60m DXY and US 10Y series (display only), or {} when absent."""
    out = {}
    for key, name in MACRO:
        try:
            df = _store.load(store_dir, name)
        except Exception:  # noqa: BLE001 - context is optional
            df = None
        if df is not None and len(df) and "close" in df:
            out[key] = df
    return out


def hour_change(df: pd.DataFrame | None, t_close: int, pct: bool) -> float | None:
    """The last completed hour's change at t_close (% for DXY, bp for the yield); None when absent or stale."""
    if df is None or len(df) < 2:
        return None
    t = ta.epoch_s(df.index).astype(np.int64)
    j = int(np.searchsorted(t + 3600, t_close, side="right")) - 1
    if j < 1 or t_close - (t[j] + 3600) > MACRO_STALE:
        return None
    c0, c1 = float(df["close"].iloc[j - 1]), float(df["close"].iloc[j])
    return round((c1 / c0 - 1.0) * 100.0, 3) if pct else round((c1 - c0) * 100.0, 1)


def context(ev: dict, b15: dict, h1: dict | None, macro: dict) -> dict:
    """The context of one sweep, from bars closed by its close only."""
    k, side = ev["i"], ev["side"]
    name, mins = nearest_boundary(int(ev["t_close"]))
    out = {"boundary": name if abs(mins) <= WINDOW_MIN else None, "min_to_boundary": round(mins)}
    a = ev.get("atr")
    if k >= RUN_BARS and a:
        ext = b15["h"][k] if side == 1 else b15["l"][k]
        out["run_atr"] = round(float((ext - b15["c"][k - RUN_BARS]) * side / a), 2)
    if h1 is not None and len(h1["t"]) > 50:
        j = int(np.searchsorted(h1["t"] + 3600, ev["t_close"], side="right")) - 1
        e20, e50 = ta.ema(h1["c"][:j + 1], 20), ta.ema(h1["c"][:j + 1], 50)
        if j >= 50 and np.isfinite(e20[-1]) and np.isfinite(e50[-1]) and e20[-1] != e50[-1]:
            out["trend_h1"] = "up" if e20[-1] > e50[-1] else "down"
    td = sessions.calendar(pd.DatetimeIndex(pd.to_datetime(b15["t"][:k + 1], unit="s", utc=True)))["trading_date"].to_numpy()
    prev = [x for x in pd.unique(td) if x < td[k]]
    if prev:
        m = td == prev[-1]
        poc = tpo_poc(b15["l"][:k + 1][m], b15["h"][:k + 1][m], POC_BIN * float(np.mean(b15["c"][:k + 1][m])) / 4000.0)
        if poc is not None:
            out["poc_prev"] = round(poc, 2)
            out["poc_side"] = "above" if poc > ev["close"] else "below"
    out["dxy_1h_pct"] = hour_change(macro.get("dxy"), int(ev["t_close"]), True)
    out["us10y_1h_bp"] = hour_change(macro.get("us10y"), int(ev["t_close"]), False)
    return out


def scan(state: dict, payloads: dict, t_now: int, macro: dict | None = None) -> list[dict]:
    """Update the sweep records from this run's closed bars; returns the stages due on the phone now (fresh only)."""
    bk = state.setdefault("brk", {})            # its own keys only: the breakout monitor's start is not touched
    since = bk.setdefault("since_sw", int(t_now))
    recs = bk.setdefault("sw", {})
    b15 = B._bars(payloads.get("15m"))
    if b15 is None:
        return []
    evs = detect(b15, {tf: B._bars(payloads.get(tf)) for tf in ("30m", "1h", "4h")})
    newest = int(b15["t"][-1]) + BAR
    due = []
    for ev in evs:
        if ev["t_close"] < since:
            continue
        rec = recs.get(ev["id"])
        if rec is None:
            rec = {k: ev[k] for k in ("id", "t", "t_close", "side", "dir", "ref", "ref_kind", "ref_tf", "wick", "close",
                                      "levels", "atr", "sess")}
            rec.update(stages={}, phone={}, res={})
            try:   # A4: display only; a failure here never stops the sweep or its stages
                rec["ctx"] = context(ev, b15, B._bars(payloads.get("1h")), macro or {})
            except Exception as e:  # noqa: BLE001
                rec["ctx"] = {"error": type(e).__name__}
            recs[ev["id"]] = rec
        if rec.get("done"):
            continue
        res, over = follow(ev, b15)
        rec["res"] = res
        for stage, tc in stages(res, ev["t_close"]):
            if stage in rec["stages"]:
                continue
            rec["stages"][stage] = {"t": tc}
            fresh = tc == newest and 0 <= t_now - tc <= B.FRESH_SEC
            rec["phone"][stage] = "DUE" if fresh else "LATE"
            if fresh:
                due.append({"id": ev["id"], "stage": stage, "ev": rec, "t_close": tc})
        if "FAILED" in rec["stages"] or "MOVE20" in rec["stages"]:
            rec["done"] = True
        elif over:
            rec["stages"]["CLOSED"] = {"t": ev["t_close"] + HOLD * BAR}
            rec["done"] = True
    if len(recs) > KEEP:
        for k in sorted(recs, key=lambda k: recs[k]["t_close"])[:len(recs) - KEEP]:
            del recs[k]
    return due


# ---------------- phone text (the operator's short format) ----------------
def context_lines(ctx: dict | None, fmt) -> list[str]:
    """A4: the session line and the context line of a SWEEP message ([] for a record without context)."""
    if not ctx or "error" in ctx:
        return []
    m = ctx.get("min_to_boundary")
    if ctx.get("boundary"):
        when = f"{ctx['boundary']} in {-m} min" if m < 0 else f"{ctx['boundary']} +{m} min"
    else:
        when = "no session open / close within 60 min"
    run = f" · run {ctx['run_atr']:.1f} ATR" if ctx.get("run_atr") is not None else ""
    parts = [f"H1 trend {ctx['trend_h1']}" if ctx.get("trend_h1") else "H1 trend n/a"]
    parts.append(f"POC {fmt(ctx['poc_prev'])} {ctx['poc_side']}" if ctx.get("poc_prev") is not None else "POC n/a")
    dx, ty = ctx.get("dxy_1h_pct"), ctx.get("us10y_1h_bp")
    parts.append(f"DXY 1h {dx:+.2f}%" if dx is not None else "DXY closed")
    parts.append(f"US10Y 1h {ty:+.1f} bp" if ty is not None else "US10Y closed")
    return [f"Session: {when}{run}", "Context: " + " · ".join(parts)]


def _level(ev: dict, fmt) -> str:
    more = len(ev["levels"]) - 1
    return (f"{fmt(ev['ref'])} {B.TF_LABEL[ev['ref_tf']]} {B.NAMES[ev['ref_kind']]}"
            + (f" (+{more} more)" if more > 0 else ""))


def message(ev: dict, stage: str, t_close: int, fmt, clock) -> list[str]:
    """One stage's phone message; fmt prints a price (MT5 offset applied), clock a time. No probability, no order."""
    side = "BUY" if ev["dir"] == 1 else "SELL"
    dot = "🟢" if ev["dir"] == 1 else "🔴"
    beyond = "above" if ev["side"] == 1 else "below"
    lv, t = f"Swept: {_level(ev, fmt)}", f"Time: {clock(t_close)}"
    inval = f"Invalid if price trades {beyond} {fmt(ev['wick'])}"
    if stage == "SWEEP":
        liq = "buy-side liquidity" if ev["side"] == 1 else "sell-side liquidity"
        ladder = " / ".join(fmt(ev["close"] + ev["dir"] * T) for T in B.TARGETS)
        return [f"{dot} GOLD SWEEP · {liq}", lv,
                f"Wick: {fmt(ev['wick'])} · Close: {fmt(ev['close'])} (back {'below' if ev['side'] == 1 else 'above'})",
                f"Reversal side: {side}", *context_lines(ev.get("ctx"), fmt), f"+$10 / +$15 / +$20 at: {ladder}", inval,
                *([PATTERN_LINE] if (ev.get("ctx") or {}).get("boundary") else []), "Entry: Not validated", t]
    if stage.startswith("MOVE"):
        T = float(stage[4:])
        return [f"{dot} GOLD SWEEP +${T:g} REACHED", lv,
                f"{side} move from {fmt(ev['close'])} to {fmt(ev['close'] + ev['dir'] * T)}",
                *([inval] if T < max(B.TARGETS) else []), "Entry: Not validated", t]
    got = [f"+${float(k[4:]):g}" for k in ("MOVE10", "MOVE15", "MOVE20") if k in ev["stages"]]
    return ["⚠️ GOLD SWEEP FAILED", lv, f"Price traded {beyond} the wick {fmt(ev['wick'])}",
            f"Reached first: {', '.join(got) if got else 'none'}", t]


# ---------------- the website ----------------
def wilson(k: int, n: int) -> list[float] | None:
    if n <= 0:
        return None
    z, p = 1.959964, k / n
    d = 1 + z * z / n
    m = (p + z * z / (2 * n)) / d
    w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(m - w, 3), round(m + w, 3)]


def record(recs: dict) -> dict:
    """Live outcomes per level timeframe and target: decided = target or extreme reached; rate = target first."""
    out = {}
    for tf in [*LEVEL_TFS, "ALL"]:
        rows = [r for r in recs.values() if tf == "ALL" or r["ref_tf"] == tf]
        row = {"sweeps": len(rows)}
        for T in ("10", "15", "20"):
            dec = [r["res"].get(T) for r in rows if (r.get("res") or {}).get(T)]
            k, n = sum(1 for v in dec if v[0] == "TP"), len(dec)
            row[T] = {"decided": n, "target_first": k, "rate": round(k / n, 3) if n else None,
                      "wilson95": wilson(k, n) if n >= WILSON_MIN else None}
        out[tf] = row
    return out


def snapshot(state: dict, t_now: int) -> dict:
    """index.json -> alerts.sweeps: the newest sweeps with their stages, phone results and outcomes."""
    bk = state.get("brk", {})
    recs = bk.get("sw", {})
    recent = sorted(recs.values(), key=lambda e: e["t_close"], reverse=True)[:40]
    return {"id": ID, "on": True, "mode": mode(), "t": int(t_now), "since": bk.get("since_sw"), "events": recent,
            "record": record(recs), "hold_bars": HOLD, "fresh_sec": B.FRESH_SEC, "wilson_min": WILSON_MIN,
            "rules": ("A sweep is a 15m bar that trades beyond a live level and CLOSES back inside it after the bar "
                      "before closed inside. Levels: M15's previous day / week, Asia / London / New York session, swing, "
                      "equal highs / lows and range levels, and the swing, equal and range levels of M30, H1 and H4 as "
                      "known at the open of their bar. Each level is alerted once. +$10 / +$15 / +$20 are counted from the "
                      "sweep close in the reversal direction, each before price trades back beyond the wick, within 24 h."),
            "evidence": ("Not a validated entry: B31b-W3 (2020-23 development data) found sweep reversals no better than "
                         "matched random entries. The live record below is descriptive until each level timeframe has "
                         "100 decided sweeps.")}
