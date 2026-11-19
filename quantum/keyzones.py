"""Key zones and market structure (Workstream 4, operator 2026-11-18): NON-DIRECTIONAL MONITORING ONLY.

Every run rebuilds, from the payloads' CLOSED bars (the forming bar is never in `chart`), the price zones a trader would
mark on M15 / M30 / H1 / H4 and the structure of each timeframe, with reproducible rules:

  * swing zones: a pivot high / low (3 bars each side) on 15m, 30m, 1h or 4h; the zone is the pivot candle's wick beyond
    its body (high .. top of body, or bottom of body .. low), widened to at least 0.15 x ATR14(15m) and cut to at most
    0.75 x ATR14(15m) from the extreme; known from the close of the 3rd bar after the pivot;
  * level zones: the previous day / week high and low and the last completed Asia / London / New York high and low,
    +/- 0.10 x ATR14(15m);
  * sources whose extremes lie within 0.5 x ATR14(15m) of the first one in price order form one zone (lowest low ..
    highest high of the members), which keeps every source; two zones that still overlap are split at the overlap's
    middle, or made one zone when a split would leave a side narrower than 0.15 x ATR14(15m);
  * state from the 15m bars after the zone became known: each visit (a bar trading into the zone after being outside)
    ends with the first close outside it: back on the side it came from = a REJECTION, on the far side = an ACCEPTANCE.
    FRESH (no completed visit), TESTED (1 rejection), WEAKENED (2+ rejections), BROKEN (accepted once: its role flips,
    support <-> resistance), INVALIDATED (accepted twice); `inside` marks a visit still in progress (it is counted);
  * KEY zones (the only ones the zone watch may message): a previous day / week level, or two or more sources of which
    one is a day / week / session level or a 30m+ swing; AT ZONE only while FRESH, TESTED or BROKEN (a retest of a
    flipped zone), and BROKEN on the bar whose close accepts it; after either message, that price band gets no
    further AT ZONE until a closed bar is 1.5 x ATR14(15m) away from it (by price band, not zone id, since a cluster's
    id can change as levels roll);
  * structure per timeframe: the last swing highs / lows (lower highs and lower lows = bearish, higher highs and higher
    lows = bullish, else mixed), the EMA20 / 50 / 100 / 200 stack, and the last BOS / CHoCH / MSS marker of the engine.

Nothing here is a signal, a direction call or a probability. It reads payloads only, writes nothing, is not imported by
the engine and is outside holdout.ENGINE_SOURCES: the engine, its configuration and the freeze key are untouched.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import sessions, shadow, ta

ZONE_TFS = {"15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}
PIVOT = 3
LOOKBACK_BARS = 480                 # swings kept per timeframe: 5 days of 15m, 10 of 30m, 20 of 1h, 80 of 4h
MIN_W, MAX_W = 0.15, 0.75           # swing-zone width, x ATR14(15m)
LEVEL_W = 0.10                      # half-width of a day / week / session level, x ATR14(15m)
CLUSTER = 0.5                       # sources within this x ATR14(15m) of a cluster's first extreme join it
SHOW_EACH_SIDE = 5
STALE_SEC = 1200                    # the newest closed 15m bar older than this at the run: STALE
SIGNIFICANT_TFS = ("30m", "1h", "4h")
LEVEL_KINDS = ("PDH", "PDL", "PWH", "PWL", "ASH", "ASL", "LOH", "LOL", "NYH", "NYL")
NAMES = {"PDH": "previous day high", "PDL": "previous day low", "PWH": "previous week high", "PWL": "previous week low",
         "ASH": "Asia high", "ASL": "Asia low", "LOH": "London high", "LOL": "London low", "NYH": "New York high",
         "NYL": "New York low", "SWH": "swing high", "SWL": "swing low"}


def _num(a) -> np.ndarray:
    return np.array([np.nan if x is None else float(x) for x in (a or [])], float)


def bars(p: dict | None) -> dict | None:
    """Closed OHLC arrays of a payload (the chart holds closed bars only), or None."""
    if not p or p.get("meta", {}).get("synthetic") or not (p.get("chart") or {}).get("t"):
        return None
    ch = p["chart"]
    if any(not ch.get(k) or len(ch[k]) != len(ch["t"]) for k in ("o", "h", "l", "c")):
        return None
    t = np.asarray(ch["t"], np.int64)
    o, h, l, c = (_num(ch[k]) for k in ("o", "h", "l", "c"))
    ok = np.isfinite(o) & np.isfinite(h) & np.isfinite(l) & np.isfinite(c)
    return {"t": t[ok], "o": o[ok], "h": h[ok], "l": l[ok], "c": c[ok], "sec": int(p["meta"].get("tf_sec") or 0)}


def atr14(b: dict) -> float:
    a = ta.atr(b["h"], b["l"], b["c"], 14)
    return float(a[-1]) if len(a) and np.isfinite(a[-1]) else float("nan")


def swing_sources(b: dict, tf: str, sec: int, a: float) -> list[dict]:
    """Pivot highs / lows of the last LOOKBACK_BARS bars as zone sources; a = ATR14(15m)."""
    n = len(b["c"])
    if n < 2 * PIVOT + 15 or not (a > 0):
        return []
    ph, pl = ta.pivothigh(b["h"], PIVOT, PIVOT), ta.pivotlow(b["l"], PIVOT, PIVOT)
    out = []
    for q in range(max(0, n - LOOKBACK_BARS), n):
        for side, v in ((1, ph[q]), (-1, pl[q])):
            if not np.isfinite(v):
                continue
            p = q - PIVOT
            body = max(b["o"][p], b["c"][p]) if side == 1 else min(b["o"][p], b["c"][p])
            if side == 1:
                hi, lo = float(v), float(body)
                lo = min(lo, hi - MIN_W * a)
                lo = max(lo, hi - MAX_W * a)
            else:
                lo, hi = float(v), float(body)
                hi = max(hi, lo + MIN_W * a)
                hi = min(hi, lo + MAX_W * a)
            out.append({"kind": "SWH" if side == 1 else "SWL", "tf": tf, "price": float(v), "lo": lo, "hi": hi,
                        "t_known": int(b["t"][q]) + sec, "t_pivot": int(b["t"][p])})
    return out


def level_sources(b15: dict, a15: float) -> list[dict]:
    """The current previous-day / week and last completed session highs and lows, from the 15m bars."""
    # one virtual bar after the last close (h = l = its close): the levels a bar opening now would see, so a day or
    # session that just completed is included
    t = np.concatenate([b15["t"], [b15["t"][-1] + 900]])
    h = np.concatenate([b15["h"], [b15["c"][-1]]])
    lo_ = np.concatenate([b15["l"], [b15["c"][-1]]])
    cal = sessions.calendar(pd.DatetimeIndex(pd.to_datetime(t, unit="s", utc=True)))
    n = len(t)
    pools, _ = shadow.build_pools(h, lo_, cal, np.full(n, np.nan), np.full(n, np.nan))
    out = []
    w = LEVEL_W * a15
    for k in LEVEL_KINDS:
        arr = pools[k]
        v = arr[-1]                                     # the virtual next bar: the level that applies after the last close
        if not np.isfinite(v):
            continue
        j = n - 1
        while j > 0 and arr[j - 1] == v:
            j -= 1
        out.append({"kind": k, "tf": "15m", "price": float(v), "lo": float(v) - w, "hi": float(v) + w,
                    "t_known": int(t[j]), "t_pivot": None})
    return out


def merge(srcs: list[dict], a15: float) -> list[dict]:
    zs = []
    for s in sorted(srcs, key=lambda x: (x["price"], x["kind"], x["tf"], x["t_known"])):
        if zs and s["price"] - zs[-1]["p0"] <= CLUSTER * a15:
            z = zs[-1]
            z["lo"], z["hi"] = min(z["lo"], s["lo"]), max(z["hi"], s["hi"])
            z["sources"].append(s)
            continue
        zs.append({"p0": s["price"], "lo": s["lo"], "hi": s["hi"], "sources": [s]})
    zs = _resolve(zs, a15)
    for z in zs:
        z.pop("p0")
        z["t_known"] = min(s["t_known"] for s in z["sources"])
        z["mid"] = (z["lo"] + z["hi"]) / 2.0
        key = sorted(z["sources"], key=lambda s: (-_rank(s), s["t_known"], s["kind"]))[0]
        z["id"] = f"{key['kind']}-{key['tf']}-{key['t_pivot'] or key['t_known']}"
    return zs


def _resolve(zs: list[dict], a15: float) -> list[dict]:
    """Clusters that still overlap: split at the middle of the overlap, or made one zone when a split would leave a side
    narrower than MIN_W x ATR (a cluster nested in another would otherwise become a sliver). Repeated until no two zones
    overlap; if that has not settled after 50 passes, whatever still overlaps is merged."""
    for _ in range(50):
        zs = sorted(zs, key=lambda z: (z["lo"], z["hi"]))
        changed, out = False, []
        for z in zs:
            a = out[-1] if out else None
            if a is not None and z["lo"] < a["hi"]:
                changed = True
                m = (z["lo"] + a["hi"]) / 2.0
                if m - a["lo"] < MIN_W * a15 or z["hi"] - m < MIN_W * a15:
                    a["lo"], a["hi"] = min(a["lo"], z["lo"]), max(a["hi"], z["hi"])
                    a["sources"] += z["sources"]
                    continue
                a["hi"], z["lo"] = m, m
            out.append(z)
        zs = out
        if not changed:
            return zs
    out = []
    for z in sorted(zs, key=lambda z: z["lo"]):
        if out and z["lo"] < out[-1]["hi"]:
            out[-1]["hi"] = max(out[-1]["hi"], z["hi"])
            out[-1]["sources"] += z["sources"]
            continue
        out.append(z)
    return out


def _rank(s: dict) -> int:
    if s["kind"] in ("PWH", "PWL"):
        return 6
    if s["kind"] in ("PDH", "PDL"):
        return 5
    if s["kind"] in LEVEL_KINDS:
        return 4
    return {"4h": 3, "1h": 2, "30m": 1}.get(s["tf"], 0)


def visits(z: dict, b15: dict) -> dict:
    """Visits of the 15m bars after the zone became known, their outcomes and the zone's state."""
    t, h, l, c = b15["t"], b15["h"], b15["l"], b15["c"]
    k0 = int(np.searchsorted(t, z["t_known"], side="left"))
    if k0 >= len(c):
        return {"state": "FRESH", "touches": 0, "rejections": 0, "acceptances": 0, "last_visit_t": None, "last_acc_t": None,
                "flips": 0, "inside": False}
    first_c = c[k0 - 1] if k0 > 0 else c[k0]
    side = 1 if first_c > z["hi"] else (-1 if first_c < z["lo"] else 0)     # +1 = price above the zone (zone is support)
    if side == 0:
        side = 1 if c[k0] >= z["mid"] else -1
    touches = rej = acc = 0
    inside, last_t, acc_t = False, None, None
    for k in range(k0, len(c)):
        hit = l[k] <= z["hi"] and h[k] >= z["lo"]
        if not inside and hit:
            inside, touches, last_t = True, touches + 1, int(t[k])
        if inside:
            if c[k] > z["hi"] or c[k] < z["lo"]:
                now = 1 if c[k] > z["hi"] else -1
                if now == side:
                    rej += 1
                else:
                    acc += 1
                    side, acc_t = now, int(t[k])
                inside = False
    state = ("INVALIDATED" if acc >= 2 else "BROKEN" if acc == 1 else "WEAKENED" if rej >= 2 else "TESTED" if rej == 1
             else "FRESH")
    return {"state": state, "touches": touches, "rejections": rej, "acceptances": acc, "last_visit_t": last_t,
            "last_acc_t": acc_t, "flips": acc, "inside": inside, "side_now": side}


def structure(p: dict | None, tf: str) -> dict | None:
    b = bars(p)
    if b is None or len(b["c"]) < 60:
        return None
    ph, pl = ta.pivothigh(b["h"], PIVOT, PIVOT), ta.pivotlow(b["l"], PIVOT, PIVOT)
    hs = [float(x) for x in ph[np.isfinite(ph)][-3:]]
    ls_ = [float(x) for x in pl[np.isfinite(pl)][-3:]]
    pattern = "mixed"
    if len(hs) >= 2 and len(ls_) >= 2:
        if hs[-1] < hs[-2] and ls_[-1] < ls_[-2]:
            pattern = "LH/LL"
        elif hs[-1] > hs[-2] and ls_[-1] > ls_[-2]:
            pattern = "HH/HL"
    ch = p["chart"]
    e = {n: (lambda a: float(a[-1]) if len(a) and np.isfinite(a[-1]) else None)(_num(ch.get(f"ema{n}")) if ch.get(f"ema{n}")
         else np.asarray(ta.ema(b["c"], n), float)) for n in (20, 50, 100, 200)}
    stack = None
    if all(e[n] is not None for n in (20, 50, 100)):
        stack = "bear" if e[20] < e[50] < e[100] else ("bull" if e[20] > e[50] > e[100] else "mixed")
    mk = [m for m in (p.get("markers") or []) if m.get("type") in ("BOS", "CHoCH", "MSS")]
    last = mk[-1] if mk else None
    a = atr14(b)
    close = float(b["c"][-1])
    bias = ("bearish" if pattern == "LH/LL" and stack == "bear" else "bullish" if pattern == "HH/HL" and stack == "bull"
            else "mixed")
    return {"tf": tf, "swing_highs": hs, "swing_lows": ls_, "pattern": pattern, "ema": e, "stack": stack, "bias": bias,
            "last_structure": {"type": last["type"], "dir": last["dir"], "t": last["t"], "px": last.get("px")} if last else None,
            "close": close, "atr": a, "close_vs_ema20_atr": (close - e[20]) / a if e[20] is not None and a > 0 else None}


def build(payloads: dict, t_now: int | None = None, price: dict | None = None) -> dict:
    """The key zones nearest the price, each side, with their state and room, and the structure of each timeframe.
    price: {'px', 't', 'source'}; default the last closed 15m close (labelled as such)."""
    t_now = int(t_now if t_now is not None else datetime.now(timezone.utc).timestamp())
    b15 = bars(payloads.get("15m"))
    if b15 is None or len(b15["c"]) < 100:
        return {"ok": False, "why": "no 15m bars"}
    a15 = atr14(b15)
    last_close_t = int(b15["t"][-1]) + 900
    if price is None or price.get("px") is None:
        price = {"px": float(b15["c"][-1]), "t": last_close_t, "source": "last closed 15m bar (feed mid, not executable)"}
    srcs = []
    for tf, sec in ZONE_TFS.items():
        b = bars(payloads.get(tf))
        if b is not None:
            srcs += swing_sources(b, tf, sec, a15)
    srcs += level_sources(b15, a15)
    zs = merge(srcs, a15)
    px = float(price["px"])
    for z in zs:
        z.update(visits(z, b15))
        z["width"] = z["hi"] - z["lo"]
        z["width_atr"] = z["width"] / a15 if a15 > 0 else None
        z["where"] = "above" if z["lo"] > px else ("below" if z["hi"] < px else "at")
        z["role"] = "resistance" if z["where"] == "above" else ("support" if z["where"] == "below" else "price inside")
        z["distance"] = 0.0 if z["where"] == "at" else (z["lo"] - px if z["where"] == "above" else px - z["hi"])
        z["distance_atr"] = z["distance"] / a15 if a15 > 0 else None
        z["significant"] = (len(z["sources"]) >= 2 or any(s["tf"] in SIGNIFICANT_TFS or s["kind"] in LEVEL_KINDS
                                                           for s in z["sources"]))
        kinds = {(s["kind"], s["tf"]) for s in z["sources"]}
        z["key"] = (any(s["kind"] in ("PDH", "PDL", "PWH", "PWL") for s in z["sources"])
                    or (len(kinds) >= 2 and any(s["tf"] in SIGNIFICANT_TFS or s["kind"] in LEVEL_KINDS for s in z["sources"])))
        z["label"] = " + ".join(dict.fromkeys(f"{s['tf']} {NAMES.get(s['kind'], s['kind'])}" for s in
                                              sorted(z["sources"], key=lambda s: -_rank(s))))
    live = [z for z in zs if z["state"] != "INVALIDATED"]
    above = sorted([z for z in live if z["where"] == "above"], key=lambda z: z["lo"])
    below = sorted([z for z in live if z["where"] == "below"], key=lambda z: -z["hi"])
    at = [z for z in live if z["where"] == "at"]
    for seq, d in ((above, 1), (below, -1)):            # room beyond each zone: to the next zone further away that does
        for i, z in enumerate(seq):                     # not touch it (a split cluster's neighbour is not room)
            gaps = [(n["lo"] - z["hi"]) if d == 1 else (z["lo"] - n["hi"]) for n in seq[i + 1:]]
            gaps = [g for g in gaps if g > 0.1 * a15]
            z["room_beyond"] = min(gaps) if gaps else None
    near_up = above[0]["lo"] - px if above else None
    near_dn = px - below[0]["hi"] if below else None
    st = {tf: structure(payloads.get(tf), tf) for tf in ZONE_TFS}
    bear = [tf for tf, s in st.items() if s and s["bias"] == "bearish"]
    bull = [tf for tf, s in st.items() if s and s["bias"] == "bullish"]
    keep = lambda z: {k: (round(v, 2) if isinstance(v, float) else v) for k, v in z.items() if k != "sources"} | {
        "sources": [{"kind": s["kind"], "tf": s["tf"], "price": round(s["price"], 2), "t_known": s["t_known"]} for s in z["sources"]]}
    return {"ok": True, "generated_t": t_now, "last_bar_close_t": last_close_t, "stale": t_now - last_close_t > STALE_SEC,
            "price": price, "atr15": round(a15, 2), "rules": __doc__.split("\n\n")[1].strip(),
            "above": [keep(z) for z in above[:SHOW_EACH_SIDE]], "below": [keep(z) for z in below[:SHOW_EACH_SIDE]],
            "at": [keep(z) for z in at], "room_up": round(near_up, 2) if near_up is not None else None,
            "room_down": round(near_dn, 2) if near_dn is not None else None,
            "structure": st, "context": {"bearish": bear, "bullish": bull},
            "counts": {"zones": len(zs), "invalidated": len(zs) - len(live)},
            "directional": "no entry method has a validated edge (B31b-W3); zones are for monitoring, not entries"}


# ---------------- zone watch: non-directional monitoring messages ----------------
WATCH_NEAR_ATR = 0.25          # a closed 15m bar inside a zone or closing within this x ATR14(15m) of its edge = AT ZONE
WATCH_REARM_ATR = 1.5          # an alerted zone re-arms once a closed bar is this far from it
WATCH_DAY_CAP = 4              # phone messages per UTC day
WATCH_LOG = 30


def _dist(z: dict, px: float) -> float:
    return 0.0 if z["lo"] <= px <= z["hi"] else (z["lo"] - px if px < z["lo"] else px - z["hi"])


def watch(st: dict, zb: dict, b15: dict | None, t_send: int) -> list[dict]:
    """Events for the newest closed 15m bar (once per bar): BROKEN (a key zone accepted by this bar's close) and AT ZONE
    (this bar inside a FRESH / TESTED / BROKEN key zone, or closing within WATCH_NEAR_ATR x ATR of it). A messaged price
    band stays silent until a closed bar is WATCH_REARM_ATR x ATR away from it and does not trade into it; bands, not
    zone ids, because a cluster's id can change when a new level joins it. st: the persistent watch state, updated in
    place. Each event: {'kind', 'zone', 'bar_t', 'fresh'}."""
    if not zb.get("ok") or b15 is None or not len(b15["c"]):
        return []
    bar_t = int(b15["t"][-1])
    if st.get("last_bar") is not None and bar_t <= st["last_bar"]:
        return []
    st["last_bar"] = bar_t
    a = zb["atr15"]
    h, l, c = float(b15["h"][-1]), float(b15["l"][-1]), float(b15["c"][-1])
    hits = lambda lo, hi: l <= hi and h >= lo
    bands = [bd for bd in st.get("bands", [])                       # re-arm: a closed bar far from the band, not in it
             if not (min(abs(bd[0] - c), abs(c - bd[1])) >= WATCH_REARM_ATR * a and not hits(bd[0], bd[1]))]
    quiet = lambda z: any(z["lo"] <= bd[1] and z["hi"] >= bd[0] for bd in bands)
    zones = [z for z in zb["above"] + zb["below"] + zb["at"] if z.get("key")]
    out = []
    for z in zones:
        if z.get("last_acc_t") == bar_t:
            kind = "BROKEN"
        elif (hits(z["lo"], z["hi"]) or _dist(z, c) <= WATCH_NEAR_ATR * a) and z["state"] in ("FRESH", "TESTED", "BROKEN"):
            kind = "AT ZONE"
        else:
            continue
        if kind == "AT ZONE" and quiet(z):              # a BROKEN is never silenced: it can only fire on its own bar
            continue
        out.append({"kind": kind, "zone": z, "bar_t": bar_t})
        if not quiet(z):
            bands.append([z["lo"], z["hi"]])
    st["bands"] = bands
    fresh = t_send - (bar_t + 900) <= STALE_SEC
    day = datetime.fromtimestamp(t_send, timezone.utc).strftime("%Y-%m-%d")
    if st.get("day") != day:
        st["day"], st["n"] = day, 0
    for e in out:
        e["fresh"] = fresh
    log = st.setdefault("log", [])
    log += [{"kind": e["kind"], "zone": e["zone"]["id"], "lo": e["zone"]["lo"], "hi": e["zone"]["hi"], "bar_t": bar_t,
             "fresh": fresh} for e in out]
    st["log"] = log[-WATCH_LOG:]
    return out


def watch_lines(evs: list[dict], zb: dict, fmt, clock) -> list[str]:
    """The phone text of one run's zone events (at most two zones). fmt(px) prints a price with the MT5 offset; clock(t)
    prints a time. Non-directional: no side, no entry, no probability."""
    if not evs:
        return []
    bar_t = evs[0]["bar_t"]
    head = (f"XAUUSD KEY ZONE WATCH | 15m bar closed {clock(bar_t + 900)} | MONITORING ONLY, NOT AN ENTRY")
    lines = [head]
    px = zb["price"]["px"]
    for e in evs[:2]:
        z = e["zone"]
        what = ("BROKEN (closed through: its role flips)" if e["kind"] == "BROKEN" else
                "PRICE INSIDE ZONE" if z["role"] == "price inside" else f"PRICE AT {z['role'].upper()}")
        room = (f"; the next separate zone is ${z['room_beyond']:.2f} beyond it" if z.get("room_beyond") is not None
                else "; no separate zone beyond it in the data")
        seen = (f"visit {z['touches']} in progress" if z.get("inside") else f"visited {z['touches']}x")
        lines.append(f"{what}: {fmt(z['lo'])}-{fmt(z['hi'])} ({z['label']}; {z['state'].lower()}, {seen}; "
                     f"width {z['width_atr']:.2f} ATR){room}")
    up = f"${zb['room_up']:.2f} to the nearest resistance" if zb.get("room_up") is not None else "no resistance zone above"
    dn = f"${zb['room_down']:.2f} to the nearest support" if zb.get("room_down") is not None else "no support zone below"
    lines.append(f"PRICE {fmt(px)} ({zb['price']['source']}): {up}, {dn}")
    ctx = zb["context"]
    lines.append(f"STRUCTURE: bearish on {', '.join(ctx['bearish']) or 'none'} | bullish on {', '.join(ctx['bullish']) or 'none'}"
                 " (swing pattern and EMA stack agree)")
    lines.append("Directional entries are DISABLED until one is validated (B31b-W3 found no edge). NO TRADE from this alert.")
    return lines
