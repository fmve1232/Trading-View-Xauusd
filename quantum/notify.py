"""Alerts for newly CONFIRMED events (all optional, all free):
  NTFY_TOPIC            ntfy.sh topic -> phone push via the free ntfy app, no account
  TELEGRAM_BOT_TOKEN +  TELEGRAM_CHAT_ID
  DISCORD_WEBHOOK_URL

Only events on bars that closed since the previous run are sent (state kept in the data
store), so a re-run never repeats an alert. Prices are shown with the MT5 offset from the
MT5_PRICE_OFFSET variable (display only, like the Pine input).

YOUR PLAN (operator, 2026-11-01): under every SIGNAL alert, the operator's own trade on that signal. Fixed money
stop and target at a fixed lot, priced from the signal's entry; then ONE follow-up alert when that TP or SL is hit
(TP first = the trade closes in profit). Variables: PLAN_LOT (0.5), PLAN_SL_USD (650), PLAN_TP_USD (650),
PLAN_COST_PER_LOT ($26 round trip: commission ~$6.5 + ~$0.20 spread x 100 oz); PLAN=0 turns it off. Display only:
the engine, its plan and the forward test are unchanged. The TP-first figure is geometry, SL / (TP + SL), measured
within 0.3 points on 139,754 entries 2020-2022 (research/B5 and B6 found no signal that beats it).

Structure / sweep alerts (Pine line v49): one line per closed bar on which the engine's BOS, CHoCH, MSS
or a PDH/PDL/PWH/PWL/PMH/PML sweep first appears, plus the separately registered H2 / H3 / H4 setups. They are
information, not entries; the DECISION is unchanged. ALERT_STRUCTURE=0 turns them off.

MT5 vs the site (operator, 2026-11-03): the broker's prices differ from the site's feed by a variable amount, and an
alert arrives minutes after the bar closed (a run every 15 min; median 6-7 min, a 5m signal up to ~17 min). So every
SIGNAL alert also carries:
  ON MT5   SL and TP as distances from YOUR fill ($650 / $650 = $13.00 at 0.5 lot), right at any broker price;
  TIMING   the bar close in UTC, MT5 server time and local time, the alert's delay, and the price move since the
           signal (the 5m forming bar of the same download, else the last close);
  LATE     when that move is >= PLAN_LATE_FRAC (0.30) of the stop: the alert's levels are stale (a discipline rule,
           not a measured edge: no tested signal beats SL / (TP + SL), so neither does skipping).
MT5 server time = New York + 7 h (UTC+2 in the northern winter, UTC+3 in summer: most prop-firm brokers);
MT5_SERVER_UTC_OFFSET (hours) fixes another offset. Local time: ALERT_LOCAL_TZ (Asia/Karachi). A TP / SL follow-up
decided by less than FEED_MARGIN ($0.50) on the site's prices says to confirm it in MT5.

LIQUIDITY (operator, 2026-11-03), once per pool per trading day (ALERT_LIQUIDITY=0 turns them off):
  NEAR   the live price within LIQ_NEAR_USD ($5) of a pool on the side it has not reached and not traded through
         today: previous day / week / month high or low, equal highs / lows (the 15m dashboard's pools);
  GRAB   the engine's own SWEEP on a closed bar (wick through, close back), per timeframe;
  BREAK  a closed bar beyond a previous day / week high or low it had not closed beyond the bar before.
Information, not trade signals (sweeps and breaks did not beat break-even on 2020-2022 data, research B2 / B3). They
replace the per-bar SWEEP tags of the structure line, which fired on every bar near the same pool.
"""
from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .data.sources import requests

STATE = "alerts_state.json"
PLAN_TRACK_SEC = 3 * 86400          # a plan with no TP / SL after 3 days gets one "still open" alert and is dropped
PLAN_MAX_OPEN = 60
PLAN_LOG = 30                       # closed plans kept for the website
VALIDATION = "plan_validation.json"   # every closed plan, kept in the data store for the daily / weekly validation
VALIDATION_MAX = 5000
MIN_N = 30                            # a group is called WEAK / STRONG only with at least this many results ...
NY = ZoneInfo("America/New_York")     # ... and a 95% interval that excludes break-even
TF_SEC = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
SESSIONS = ((0, 7, "Asia"), (7, 12, "London"), (12, 16, "London+NY"), (16, 21, "New York"), (21, 24, "Rollover"))
LATE_FRAC = 0.30     # a move since the signal of 30% of the stop marks the alert LATE (declared 2026-11-03, before use)
FEED_MARGIN = 0.50   # $ of price: a TP / SL decided by less than this on the site's feed may differ on the broker's


def channels() -> list[str]:
    """Which phone / chat channels are configured (names only, never the values)."""
    out = []
    if os.environ.get("NTFY_TOPIC", "").strip():
        out.append("ntfy")
    if os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() and os.environ.get("TELEGRAM_CHAT_ID", "").strip():
        out.append("telegram")
    if os.environ.get("DISCORD_WEBHOOK_URL", "").strip():
        out.append("discord")
    return out


def _fmt(x, off=0.0):
    return "—" if x is None else f"{x + off:.2f}"


# ---------------- MT5 vs the site: clocks, the price now, and how late an alert is ----------------
def _env_float(k: str, d: float) -> float:
    try:
        v = float(os.environ.get(k, "") or d)
    except ValueError:
        return d
    return v if math.isfinite(v) else d


def mt5_clock(t: int) -> datetime:
    """Wall-clock time on the MT5 server: New York + 7 h unless MT5_SERVER_UTC_OFFSET (hours) is set."""
    v = os.environ.get("MT5_SERVER_UTC_OFFSET", "").strip()
    if v:
        try:
            h = float(v)
            if -14 <= h <= 14:
                return datetime.fromtimestamp(t, timezone(timedelta(hours=h)))
        except ValueError:
            pass
    return datetime.fromtimestamp(t, NY) + timedelta(hours=7)


def local_clock(t: int) -> datetime:
    try:
        tz = ZoneInfo(os.environ.get("ALERT_LOCAL_TZ", "").strip() or "Asia/Karachi")
    except (ValueError, KeyError, OSError):
        tz = ZoneInfo("Asia/Karachi")
    return datetime.fromtimestamp(t, tz)


def clocks(t: int) -> str:
    """'06:30 UTC = 08:30 MT5 = 11:30 PKT' for one instant."""
    loc = local_clock(t)
    return f"{datetime.fromtimestamp(t, timezone.utc):%H:%M} UTC = {mt5_clock(t):%H:%M} MT5 = {loc:%H:%M} {loc.tzname()}"


def price_now(payloads: dict, tf: str) -> dict | None:
    """The newest price of this run's download: the 5m forming bar (then this timeframe's), else the last closed bar.
    {'px', 't' (when it was read, or the bar's close), 'live' (forming bar or not)}. The 5m price is used only when
    it comes from the same source as the signal (futures trade $10-30 over spot: a mixed pair would fake a move)."""
    own, m5 = payloads.get(tf), payloads.get("5m")
    if not own or own["meta"].get("synthetic"):
        return None
    same = m5 and not m5["meta"].get("synthetic") and m5["meta"].get("price_source") == own["meta"].get("price_source")
    order = [m5, own] if same else [own]
    for p in order:
        fb = p["meta"].get("forming") or {}
        if fb.get("c") is not None and p["meta"].get("generated_utc"):
            return {"px": float(fb["c"]), "t": int(datetime.fromisoformat(p["meta"]["generated_utc"]).timestamp()), "live": True}
    for p in order:
        ch = p.get("chart") or {}
        c, t = ch.get("c") or [], ch.get("t") or []
        k = next((i for i in range(len(c) - 1, -1, -1) if c[i] is not None), None)
        if k is not None and k < len(t):
            return {"px": float(c[k]), "t": int(t[k]) + TF_SEC.get(p["meta"].get("tf"), 0), "live": False}
    return None


def alert_timing(m: dict, tf: str, now: dict | None, pl: dict | None) -> dict | None:
    """How late this SIGNAL alert is and how far price has moved since the signal close (+ = toward TP)."""
    if not now or now.get("t") is None or m.get("px") is None:
        return None
    t_close = int(m["t"]) + TF_SEC.get(tf, 0)
    stop = pl["sl_px"] if pl else abs(m["px"] - m["sl"]) if m.get("sl") is not None else None
    frac = _env_float("PLAN_LATE_FRAC", LATE_FRAC)
    out = {"t_close": t_close, "t_alert": int(now["t"]), "delay_min": max(0, round((now["t"] - t_close) / 60)),
           "px_now": None, "t_px": None, "live": None, "move": None, "limit": None, "late": False}
    if now.get("px") is not None:
        mv = (now["px"] - m["px"]) * m["dir"]
        out.update(px_now=now["px"], t_px=now.get("t_px"), live=now.get("live"), move=round(mv, 2))
        if stop:
            out["limit"] = round(frac * stop, 2)
            out["late"] = abs(mv) >= frac * stop
    return out


def mt5_line(d: int, pl: dict) -> str:
    s, side = ("+", "-") if d == -1 else ("-", "+")
    return (f"ON MT5: {'BUY' if d == 1 else 'SELL'} at market, then SL = your fill {s} {pl['sl_px']:.2f}, "
            f"TP = your fill {side} {pl['tp_px']:.2f} (= -${pl['sl_usd']:,.0f} / +${pl['tp_usd']:,.0f} at {pl['lot']:g} lot, "
            "at any broker price)")


def timing_lines(tm: dict | None, off: float = 0.0) -> tuple[str | None, str | None]:
    """(LATE warning or None, TIMING line or None)."""
    if not tm:
        return None, None
    s = f"TIMING: bar closed {clocks(tm['t_close'])} | alert {tm['delay_min']} min after the close"
    late = None
    if tm["move"] is not None:
        where = "toward TP" if tm["move"] > 0 else "toward SL" if tm["move"] < 0 else "unchanged"
        what = "price" if tm["live"] else "last close"
        at = datetime.fromtimestamp(tm["t_px"], timezone.utc).strftime("%H:%M UTC") if tm["t_px"] else "?"
        s += f" | {what} {_fmt(tm['px_now'], off)} at {at}: ${abs(tm['move']):.2f} {where} since the signal"
        if tm["late"]:
            late = (f"LATE: price already moved ${abs(tm['move']):.2f} {where} since the signal (limit ${tm['limit']:.2f} = "
                    f"{_env_float('PLAN_LATE_FRAC', LATE_FRAC):.0%} of the stop). The alert's levels are stale: skip it")
    return late, s


def messages(payload: dict, since_t: int | None, now: dict | None = None) -> list[str]:
    """Alert lines for bars closed after since_t. `now` ({'t' send time, 'px', 't_px', 'live'}) adds the MT5 and
    timing lines to each SIGNAL."""
    tf = payload["meta"]["tf"]
    off = float(os.environ.get("MT5_PRICE_OFFSET", "0") or 0)
    out = []
    for m in payload["markers"]:
        if since_t is not None and m["t"] <= since_t:
            continue
        if m["type"] == "SIGNAL":
            d = "BUY" if m["dir"] == 1 else "SELL"
            out.append(f"XAUUSD {tf} {d} (confirmed close) | entry {_fmt(m['px'], off)} SL {_fmt(m['sl'], off)} "
                       f"TP1 {_fmt(m['tp1'], off)} TP2 {_fmt(m['tp2'], off)} TP3 {_fmt(m['tp3'], off)} | TQ {m['tq']}")
            pl = plan_cfg()
            late, timing = timing_lines(alert_timing(m, tf, now, pl), off)
            if late:
                out.append(late)                           # second line: visible in the phone's preview
            if pl and m.get("px") is not None:
                out.append(plan_line(m["px"], m["dir"], pl, off))
                out.append(mt5_line(m["dir"], pl))
            if timing:
                out.append(timing)
        elif m["type"] == "TRACK_EXIT":
            out.append(f"XAUUSD {tf} tracked plan {'STOPPED' if (m.get('r') or 0) < 0 else 'reached TP1'} at {_fmt(m['px'], off)} = {m.get('r')}R")
        elif m["type"] == "RISK_LOCK":
            out.append(f"XAUUSD {tf} RISK LOCK engaged -- new entries blocked")
    if os.environ.get("ALERT_STRUCTURE", "1").strip() != "0":
        out += structure_lines(payload, since_t, off, sweeps=not liq_on())
    for d in payload["decisions"]:
        if since_t is not None and d["t"] <= since_t:
            continue
        if d["to"] in ("BUY", "SELL"):
            continue  # already covered by the SIGNAL message
        out.append(f"XAUUSD {tf} DECISION {d['from']} -> {d['to']}")
    return out


_TAG = {("BOS", 1): "BOS▲", ("BOS", -1): "BOS▼", ("CHoCH", 1): "CHoCH▲", ("CHoCH", -1): "CHoCH▼",
        ("MSS", 1): "MSS▲", ("MSS", -1): "MSS▼", ("SWEEP", 1): "SWEEP-LOW", ("SWEEP", -1): "SWEEP-HIGH"}


def structure_lines(payload: dict, since_t: int | None, off: float = 0.0, sweeps: bool = True) -> list[str]:
    """One line per newly closed bar: its structure / sweep events and any H2 / H3 setup on it. sweeps=False leaves
    the sweeps to the LIQUIDITY alerts (one per pool per day instead of one per bar)."""
    tf = payload["meta"]["tf"]
    by_t: dict = {}
    for m in payload["markers"]:
        if m["type"] == "SWEEP" and not sweeps:
            continue
        tag = _TAG.get((m["type"], m.get("dir")))
        if tag and m["type"] == "SWEEP" and m.get("lvl"):       # name the swept pool and its price (Pine v84)
            tag += " " + " ".join(f"{x['name']} {_fmt(x['px'], off)}" for x in m["lvl"])
        if tag and (since_t is None or m["t"] > since_t) and tag not in by_t.setdefault(m["t"], []):
            by_t[m["t"]].append(tag)
    for arm in ("h2", "h3", "h4", "h5", "h6"):
        for g in (payload.get(arm) or {}).get("signals") or []:
            if since_t is None or g["t"] > since_t:
                by_t.setdefault(g["t"], []).append(f"{arm.upper()} {'BUY' if g['dir'] == 'LONG' else 'SELL'} entry {_fmt(g['entry'], off)} "
                                                   f"SL {_fmt(g['sl'], off)} TP1 {_fmt(g['tp1'], off)} TP2 {_fmt(g['tp2'], off)}")
    return [f"XAUUSD {tf} {' '.join(v)} | info, not a DECISION" for _, v in sorted(by_t.items())]


# ---------------- liquidity alerts (operator, 2026-11-03): price near a pool, a pool grabbed, a pool broken ----------------
LIQ_NEAR_USD = 5.0     # NEAR = within $5 of a pool not yet traded through today (declared 2026-11-03, before use)
_HIGHS = ("PDH", "PWH", "PMH", "EQH")
_LIQ_LOG = 40


def liq_on() -> bool:
    return os.environ.get("ALERT_LIQUIDITY", "1").strip() != "0"


def _liq_side(name: str) -> str:
    return "buy-side liquidity above" if name in _HIGHS else "sell-side liquidity below"


def _first_today(seen: dict, key: tuple, t: int) -> bool:
    """True the first time `key` happens on this trading day (and remembers it)."""
    k, day = "|".join(str(x) for x in key), trading_day(t)
    if seen.get(k) == day:
        return False
    seen[k] = day
    return True


def liquidity_events(payload: dict, since_t: int | None, seen: dict) -> list[dict]:
    """GRAB: the engine's own SWEEP (wick through a previous day / week / month high or low, close back), once per
    pool per day per timeframe. BREAK: a bar closed beyond a previous day / week high or low it had not closed beyond
    on the bar before, once per pool per day per timeframe. Bars closed after since_t only."""
    tf, ch = payload["meta"]["tf"], payload.get("chart") or {}
    t, c = ch.get("t") or [], ch.get("c") or []
    at = {tt: k for k, tt in enumerate(t)}
    out = []
    for m in payload["markers"]:
        if m["type"] != "SWEEP" or (since_t is not None and m["t"] <= since_t):
            continue
        k = at.get(m["t"])
        close = c[k] if k is not None and k < len(c) else None
        for x in m.get("lvl") or []:
            if x.get("px") is not None and _first_today(seen, (tf, "GRAB", x["name"], f"{x['px']:.2f}"), m["t"]):
                out.append({"kind": "GRAB", "tf": tf, "t": int(m["t"]), "name": x["name"], "px": x["px"],
                            "wick": m.get("px"), "close": close})
    for k in range(1, min(len(t), len(c))):
        if (since_t is not None and t[k] <= since_t) or c[k] is None or c[k - 1] is None:
            continue
        for name, key in (("PDH", "pdh"), ("PWH", "pwh"), ("PDL", "pdl"), ("PWL", "pwl")):
            lv = (ch.get(key) or [None] * len(t))[k]
            if lv is None:
                continue
            hi = name in _HIGHS
            crossed = (c[k] > lv >= c[k - 1]) if hi else (c[k] < lv <= c[k - 1])
            if crossed and _first_today(seen, (tf, "BREAK", name, f"{lv:.2f}"), t[k]):
                out.append({"kind": "BREAK", "tf": tf, "t": int(t[k]), "name": name, "px": lv, "close": c[k]})
    return sorted(out, key=lambda r: r["t"])


def _taken_today(p: dict, lv: float, hi: bool) -> bool:
    """Has price already traded through this level on the current trading day (closed bars and the forming one)?"""
    ch, fb = p.get("chart") or {}, p["meta"].get("forming") or {}
    t, h, l = ch.get("t") or [], ch.get("h") or [], ch.get("l") or []
    if not t:
        return False
    day = trading_day(int(fb["t"]) if fb.get("t") else int(t[-1]))
    ext = [x for k, x in enumerate(h if hi else l) if k < len(t) and x is not None and trading_day(int(t[k])) == day]
    if fb.get("h" if hi else "l") is not None:
        ext.append(fb["h" if hi else "l"])
    return any(x >= lv for x in ext) if hi else any(x <= lv for x in ext)


def liquidity_near(payloads: dict, tfs: list[str], seen: dict, t_now: int) -> list[dict]:
    """NEAR: the price now within LIQ_NEAR_USD of a pool (the 15m dashboard's: previous day / week / month highs and
    lows, equal highs / lows) on the side it has not reached, and not traded through today; once per pool per day."""
    src = next((payloads[x] for x in ["15m", *tfs] if payloads.get(x) and not payloads[x]["meta"].get("synthetic")), None)
    if src is None:
        return []
    pn = price_now(payloads, src["meta"]["tf"])
    pools = ((src.get("dashboard") or {}).get("liquidity") or {}).get("pools") or {}
    if not pn or not pn.get("live"):                   # only on a live price: a stale close is not "near now"
        return []
    near = _env_float("LIQ_NEAR_USD", LIQ_NEAR_USD)
    out = []
    for name, lv in pools.items():
        if lv is None:
            continue
        hi = name in _HIGHS
        dist = (lv - pn["px"]) if hi else (pn["px"] - lv)
        if 0 < dist <= near and not _taken_today(src, lv, hi) and _first_today(seen, ("NEAR", name, f"{lv:.2f}"), t_now):
            out.append({"kind": "NEAR", "tf": "", "t": int(pn["t"]), "name": name, "px": round(float(lv), 2),
                        "price": pn["px"], "dist": round(dist, 2)})
    return out


def liq_text(r: dict, off: float = 0.0) -> str:
    nm, lv, side = r["name"], _fmt(r["px"], off), _liq_side(r["name"])
    if r["kind"] == "NEAR":
        where = "below" if r["name"] in _HIGHS else "above"
        return (f"XAUUSD LIQUIDITY NEAR: price {_fmt(r['price'], off)} is ${r['dist']:.2f} {where} {nm} {lv} ({side}) | "
                f"{clocks(r['t'])} | watch for a grab (wick through, close back) or a break | info, not a trade signal")
    bar, side = f"{r['tf']} bar {clocks(r['t'])}", side.rsplit(" ", 1)[0]       # "buy-side liquidity"
    if r["kind"] == "GRAB":
        lows = r["name"] not in _HIGHS
        return (f"XAUUSD {r['tf']} LIQUIDITY GRAB: {nm} {lv} swept -- {'low' if lows else 'high'} {_fmt(r.get('wick'), off)}, "
                f"closed back {'above' if lows else 'below'} at {_fmt(r.get('close'), off)} ({side} taken, then rejected) | "
                f"{bar} | info, not a trade signal")
    hi = r["name"] in _HIGHS
    return (f"XAUUSD {r['tf']} LIQUIDITY BREAK: {nm} {lv} broken -- closed {'above' if hi else 'below'} at "
            f"{_fmt(r.get('close'), off)} ({side} taken, price holding beyond) | {bar} | info, not a trade signal")


def plan_cfg() -> dict | None:
    """The operator's plan from the environment (defaults 0.5 lot, SL $650, TP $650); None when PLAN=0."""
    if os.environ.get("PLAN", "1").strip() == "0":
        return None

    def num(k: str, d: float) -> float:
        try:
            v = float(os.environ.get(k, "") or d)
        except ValueError:
            return d
        return v if v > 0 else d
    lot, sl, tp, cpl = num("PLAN_LOT", 0.5), num("PLAN_SL_USD", 650.0), num("PLAN_TP_USD", 650.0), num("PLAN_COST_PER_LOT", 26.0)
    oz = lot * 100.0
    return {"lot": lot, "sl_usd": sl, "tp_usd": tp, "cost_usd": cpl * lot, "sl_px": sl / oz, "tp_px": tp / oz}


def plan_levels(entry: float, d: int, pl: dict) -> tuple[float, float]:
    """(SL, TP) prices of the plan for a signal at `entry` in direction d (+1 BUY, -1 SELL)."""
    return entry - d * pl["sl_px"], entry + d * pl["tp_px"]


def plan_line(entry: float, d: int, pl: dict, off: float = 0.0) -> str:
    sl, tp = plan_levels(entry, d, pl)
    first = pl["sl_px"] / (pl["sl_px"] + pl["tp_px"])
    be = (pl["sl_usd"] + pl["cost_usd"]) / (pl["sl_usd"] + pl["tp_usd"])
    return (f"YOUR PLAN {pl['lot']:g} lot: SL {_fmt(sl, off)} (-${pl['sl_usd']:,.0f}) TP {_fmt(tp, off)} (+${pl['tp_usd']:,.0f}) | "
            f"TP first ~{first:.0%} (measured; no signal beats it) | break-even {be:.0%}")


def plan_path(plan: dict, chart: dict) -> dict:
    """The plan's path on the bars AFTER its signal bar: result ('TP' | 'SL' | 'BOTH' | None while open), the bar it
    happened on, how far price went for (mfe) and against (mae) the trade in $ of price, and the bars it took."""
    t, h, l = chart.get("t") or [], chart.get("h") or [], chart.get("l") or []
    d, sl, tp, e = plan["dir"], plan["sl"], plan["tp"], plan["entry"]
    mfe = mae = 0.0
    bars = 0
    for k in range(len(t)):
        if t[k] <= plan["t"] or h[k] is None or l[k] is None:
            continue
        bars += 1
        mfe = max(mfe, (h[k] - e) if d == 1 else (e - l[k]))
        mae = max(mae, (e - l[k]) if d == 1 else (h[k] - e))
        hit_tp = h[k] >= tp if d == 1 else l[k] <= tp
        hit_sl = l[k] <= sl if d == 1 else h[k] >= sl
        what = "BOTH" if hit_tp and hit_sl else "TP" if hit_tp else "SL" if hit_sl else None
        if what:
            return {"result": what, "t_res": t[k], "mfe": mfe, "mae": mae, "bars": bars}
    return {"result": None, "t_res": None, "mfe": mfe, "mae": mae, "bars": bars}


def plan_result(plan: dict, chart: dict) -> tuple[str, int] | None:
    """('TP' | 'SL' | 'BOTH', bar open t) for the first bar AFTER the signal bar that touches the plan's TP or SL."""
    r = plan_path(plan, chart)
    return (r["result"], r["t_res"]) if r["result"] else None


def plan_updates(plans: list[dict], tf: str, chart: dict, now_t: int, off: float = 0.0) -> tuple[list[str], list[dict], list[dict]]:
    """Follow-up alerts for this timeframe's open plans, the plans still open afterwards, and the ones that closed."""
    lines, keep, closed = [], [], []
    for pl in plans:
        if pl["tf"] != tf:
            keep.append(pl)
            continue
        side = "BUY" if pl["dir"] == 1 else "SELL"
        head = f"XAUUSD {tf} YOUR PLAN {side} from {_fmt(pl['entry'], off)}"
        path = plan_path(pl, chart)
        if path["result"] is None:
            if now_t - pl["t"] > PLAN_TRACK_SEC:
                lines.append(f"{head}: no TP or SL after 3 days on the site's prices -- check the trade in MT5 (tracking stopped)")
                closed.append({**pl, **path, "result": "EXPIRED", "t_res": now_t})
            else:
                keep.append(pl)
            continue
        what, bt = path["result"], path["t_res"]
        closed.append({**pl, **path})
        hhmm = datetime.fromtimestamp(bt, timezone.utc).strftime("%d %b %H:%M UTC")
        hhmm += f" = {mt5_clock(bt):%H:%M} MT5"
        to_tp, to_sl = abs(pl["tp"] - pl["entry"]), abs(pl["entry"] - pl["sl"])
        if what == "TP":
            s = f"{head}: TP {_fmt(pl['tp'], off)} HIT +${pl['tp_usd']:,.0f} -- trade closed in profit ({hhmm} bar)"
            past = path["mfe"] - to_tp
            if past < FEED_MARGIN:
                s += f" | only ${past:.2f} past TP on the site's prices: confirm in MT5 (broker prices differ)"
            lines.append(s)
        elif what == "SL":
            s = f"{head}: SL {_fmt(pl['sl'], off)} HIT -${pl['sl_usd']:,.0f} -- trade closed at the stop ({hhmm} bar)"
            past, short = path["mae"] - to_sl, to_tp - path["mfe"]
            if past < FEED_MARGIN:
                s += f" | only ${past:.2f} past SL on the site's prices: confirm in MT5 (broker prices differ)"
            if short < FEED_MARGIN:
                s += f" | price came within ${max(short, 0):.2f} of TP: check MT5, your TP may have filled"
            lines.append(s)
        else:
            lines.append(f"{head}: TP and SL both inside the {hhmm} bar -- order unknown, check MT5 (counted as SL)")
    return lines, keep, closed


# ---------------- validation: how the market answered every alerted signal ----------------
def session_of(t: int) -> str:
    h = (int(t) % 86400) // 3600
    return next(nm for a, b, nm in SESSIONS if a <= h < b)


def trading_day(t: int) -> str:
    """The New York trading day of an instant: a day runs from 17:00 to 17:00 New York (gold's daily close)."""
    return (datetime.fromtimestamp(int(t), NY) + timedelta(hours=7)).strftime("%Y-%m-%d")


def trading_week(t: int) -> str:
    """ISO week of the trading day; the weekend belongs to the coming week, so a week ends at Friday's close."""
    d = date.fromisoformat(trading_day(t))
    if d.weekday() >= 5:
        d += timedelta(days=7 - d.weekday())
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    hw = z * math.sqrt(max(p * (1 - p) / n + z * z / (4 * n * n), 0.0)) / d
    return (max(0.0, c - hw), min(1.0, c + hw))


def _decision_t(r: dict) -> int:
    return int(r.get("t_dec") or (r["t"] + TF_SEC.get(r["tf"], 0)))


def summarize(recs: list[dict], cost_per_lot: float) -> dict:
    """Validation of closed plans: TP-first rate against target, geometry and break-even, money, near misses, and
    the same per timeframe, session, side and weekday. Groups are flagged only when the evidence is clear."""
    dec = [r for r in recs if r.get("result") in ("TP", "SL", "BOTH")]
    n, tp = len(dec), sum(r["result"] == "TP" for r in dec)

    def cost(r):
        return cost_per_lot * float(r.get("lot") or 0.5)
    exp = sum(r["sl_usd"] / (r["sl_usd"] + r["tp_usd"]) for r in dec) / n if n else math.nan
    be = sum((r["sl_usd"] + cost(r)) / (r["sl_usd"] + r["tp_usd"]) for r in dec) / n if n else math.nan
    net = sum((r["tp_usd"] if r["result"] == "TP" else -r["sl_usd"]) - cost(r) for r in dec)
    oz = [float(r.get("lot") or 0.5) * 100.0 for r in dec]
    stops = [r for r in dec if r["result"] != "TP"]
    wins = [r for r in dec if r["result"] == "TP"]
    near = sum(1 for r in stops if r.get("mfe", 0) >= 0.8 * abs(r["tp"] - r["entry"]))
    close_call = sum(1 for r in wins if r.get("mae", 0) >= 0.8 * abs(r["entry"] - r["sl"]))
    lo, hi = _wilson(tp, n)
    out = {"n": n, "tp": tp, "sl": n - tp, "expired": sum(r.get("result") == "EXPIRED" for r in recs),
           "rate": tp / n if n else math.nan, "wilson": [lo, hi], "target": 0.90, "expected": exp, "break_even": be,
           "net_usd": net, "near_misses": near, "close_calls": close_call,
           "avg_mfe_usd": sum(r.get("mfe", 0) * o for r, o in zip(dec, oz)) / n if n else math.nan,
           "avg_mae_usd": sum(r.get("mae", 0) * o for r, o in zip(dec, oz)) / n if n else math.nan, "by": {}}
    keys = {"timeframe": lambda r: r["tf"], "session": lambda r: r.get("session") or session_of(_decision_t(r)),
            "side": lambda r: "BUY" if r["dir"] == 1 else "SELL",
            "weekday": lambda r: r.get("dow") or date.fromisoformat(trading_day(_decision_t(r))).strftime("%a")}
    for dim, fn in keys.items():
        grp: dict = {}
        for r in dec:
            g = grp.setdefault(fn(r), [0, 0])
            g[0] += 1
            g[1] += r["result"] == "TP"
        out["by"][dim] = {}
        for key, (gn, gk) in sorted(grp.items()):
            glo, ghi = _wilson(gk, gn)
            flag = ("WEAK" if ghi < be else "STRONG" if glo > be else "") if gn >= MIN_N and math.isfinite(be) else ""
            out["by"][dim][key] = {"n": gn, "tp": gk, "rate": gk / gn, "wilson": [glo, ghi], "flag": flag}
    out["advice"] = advice(out)
    return out


def advice(sm: dict) -> list[str]:
    """Plain-language findings from a summary. Only clear evidence becomes an instruction."""
    if not sm["n"]:
        return ["No validated signals yet: results appear as each alerted signal reaches its TP or SL."]
    a = [(f"TP hit first {sm['tp']} of {sm['n']} = {sm['rate']:.0%} against your 90% target "
          f"({100 * (sm['rate'] - 0.9):+.0f} points). Your SL / TP sizes predict {sm['expected']:.0%}; break-even is {sm['break_even']:.0%}.")]
    if sm["n"] < MIN_N:
        a.append(f"Only {sm['n']} results: too few to tell skill from luck. A group is judged after {MIN_N} results.")
    for dim, groups in sm["by"].items():
        for key, g in groups.items():
            if g["flag"] == "WEAK":
                a.append(f"WEAK - {dim} {key}: {g['tp']}/{g['n']} TP first (95% range {g['wilson'][0]:.0%}-{g['wilson'][1]:.0%}), "
                         f"below break-even. Stop taking these signals.")
            elif g["flag"] == "STRONG":
                a.append(f"STRONG - {dim} {key}: {g['tp']}/{g['n']} TP first (95% range {g['wilson'][0]:.0%}-{g['wilson'][1]:.0%}), "
                         f"above break-even. Keep them; confirm on more trades before sizing up.")
    if sm["sl"] >= 5 and sm["near_misses"] / sm["sl"] >= 0.25:
        a.append(f"{sm['near_misses']} of {sm['sl']} stopped trades first went 80%+ of the way to TP: price often turns just "
                 f"before TP. A closer TP would win more of these but pays less per win.")
    if sm["tp"] >= 5 and sm["close_calls"] / sm["tp"] >= 0.25:
        a.append(f"{sm['close_calls']} of {sm['tp']} winners first came within 20% of the SL: the stop barely survived.")
    return a


def report_lines(kind: str, label: str, sm: dict, open_n: int = 0) -> list[str]:
    """The daily / weekly phone summary."""
    if not sm["n"] and not open_n:
        return [f"XAUUSD {kind} VALIDATION {label}: no alerted signal closed (and none open)."]
    tfs = " ".join(f"{k} {g['tp']}/{g['n']}" for k, g in sm["by"].get("timeframe", {}).items())
    head = (f"XAUUSD {kind} VALIDATION {label}: {sm['n']} signals closed, TP first {sm['tp']}/{sm['n']}"
            + (f" = {sm['rate']:.0%}" if sm["n"] else "")
            + f" (target 90%, expected {sm['expected']:.0%}, break-even {sm['break_even']:.0%}) | net ${sm['net_usd']:+,.0f} at your plan"
            if sm["n"] else f"XAUUSD {kind} VALIDATION {label}: no signal closed yet")
    head += (f" | by timeframe {tfs}" if tfs else "") + (f" | near misses {sm['near_misses']}" if sm["n"] else "") + (f" | still open {open_n}" if open_n else "")
    return [head] + [x for x in sm["advice"][1:3]] + ["Details: website > Your plan alerts > Validation."]


def validation_block(log: list[dict], plans: list[dict], now_t: int, cost_per_lot: float) -> dict:
    """Today / this week / all time, for the website."""
    day, week = trading_day(now_t), trading_week(now_t)
    today = [r for r in log if trading_day(_decision_t(r)) == day]
    wk = [r for r in log if trading_week(_decision_t(r)) == week]
    return {"day": day, "week": week, "today": summarize(today, cost_per_lot), "this_week": summarize(wk, cost_per_lot),
            "all": summarize(log, cost_per_lot),
            "open_today": sum(1 for p in plans if trading_day(_decision_t(p)) == day),
            "open_week": sum(1 for p in plans if trading_week(_decision_t(p)) == week)}


def news_lines(news: dict | None, now_t: int, last_alerted: int | None) -> tuple[list[str], int | None]:
    """One alert per dated NFP / CPI / FOMC window, sent on the first run inside it (Pine Visuals v86 alertOnNews).
    Display only: the engine neither blocks nor re-costs news. Returns the lines and the event time now alerted."""
    if not news or os.environ.get("ALERT_NEWS", "1").strip() == "0":
        return [], last_alerted
    b, a = news["before_min"] * 60, news["after_min"] * 60
    for e in news["events"]:
        if e["t"] - b <= now_t <= e["t"] + a and (last_alerted is None or e["t"] > last_alerted):
            utc = datetime.fromtimestamp(e["t"], timezone.utc).strftime("%H:%M")
            return [f"XAUUSD NEWS WINDOW: {e['name']} {e['ny'][5:]} New York ({utc} UTC), window -{news['before_min']}/+{news['after_min']} min. "
                    f"Spreads widen and stops can be skipped. Display only: the DECISION is the engine's."], e["t"]
    return [], last_alerted


def send(lines: list[str]) -> list[str]:
    sent = []
    if not lines or requests is None:
        return sent
    text = "\n".join(lines)
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if topic:
        try:
            requests.post(f"https://ntfy.sh/{topic}", data=text.encode(), timeout=15, headers={"Title": "XAUUSD Quantum"})
            sent.append("ntfy")
        except Exception:
            pass
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if tok and chat:
        try:
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id": chat, "text": text}, timeout=15)
            sent.append("telegram")
        except Exception:
            pass
    hook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if hook:
        try:
            requests.post(hook, json={"content": text[:1900]}, timeout=15)
            sent.append("discord")
        except Exception:
            pass
    return sent


def run(store_dir: str | None, payloads: dict, tfs: list[str], sent_t: int | None = None) -> dict:
    """sent_t: the send time (tests); None = the clock when the alerts go out."""
    path = os.path.join(store_dir, STATE) if store_dir else None
    state = {}
    if path and os.path.exists(path):
        with open(path) as f:
            state = json.load(f)
    report = {}
    off = float(os.environ.get("MT5_PRICE_OFFSET", "0") or 0)
    pl_cfg = plan_cfg()
    plans = state.get("plans", []) if pl_cfg else []
    log, tally = state.get("plan_log", []), dict(state.get("plan_tally", {}))
    vpath = os.path.join(store_dir, VALIDATION) if store_dir else None
    vlog: list = []
    seen, liq_log, alerted = dict(state.get("liq_seen", {})), list(state.get("liq_log", [])), False
    t_send = int(sent_t if sent_t is not None else datetime.now(timezone.utc).timestamp())
    if vpath and os.path.exists(vpath):
        with open(vpath) as f:
            vlog = json.load(f)
    for tf in tfs:
        p = payloads.get(tf)
        if not p or p["meta"]["synthetic"]:
            continue
        last_t = p["chart"]["t"][-1]
        since = state.get(tf)
        if since is None:
            state[tf] = last_t   # first run: remember the position, do not replay history
            continue
        alerted = True
        pn = price_now(payloads, tf)
        now = {"t": t_send, **({"px": pn["px"], "t_px": pn["t"], "live": pn["live"]} if pn else {})}
        lines = messages(p, since, now)
        if liq_on():                                       # liquidity grabs / breaks on this timeframe's new bars
            ev = liquidity_events(p, since, seen)
            lines += [liq_text(r, off) for r in ev]
            liq_log += ev
        if pl_cfg:                                         # the operator's plan: results of earlier signals, then new ones
            upd, plans, done = plan_updates(plans, tf, p["chart"], last_t, off)
            lines = upd + lines
            for c in done:
                tally[c["result"]] = tally.get(c["result"], 0) + 1
            log = (log + done)[-PLAN_LOG:]
            vlog = (vlog + done)[-VALIDATION_MAX:]
            for m in p["markers"]:
                if m["type"] == "SIGNAL" and m["t"] > since and m.get("px") is not None:
                    sl, tp = plan_levels(m["px"], m["dir"], pl_cfg)
                    t_dec = int(m["t"]) + TF_SEC.get(tf, 0)
                    tm = alert_timing(m, tf, now, pl_cfg) or {}
                    plans.append({"tf": tf, "t": m["t"], "dir": m["dir"], "entry": m["px"], "sl": sl, "tp": tp,
                                  "sl_usd": pl_cfg["sl_usd"], "tp_usd": pl_cfg["tp_usd"], "lot": pl_cfg["lot"], "t_dec": t_dec,
                                  "session": session_of(t_dec), "dow": date.fromisoformat(trading_day(t_dec)).strftime("%a"),
                                  "tq": m.get("tq"), "t_alert": tm.get("t_alert"), "px_alert": tm.get("px_now"),
                                  "move_alert": tm.get("move"), "late": tm.get("late")})
        report[tf] = {"lines": lines, "sent": send(lines)}
        state[tf] = last_t
    if pl_cfg:
        state["plans"], state["plan_log"], state["plan_tally"] = plans[-PLAN_MAX_OPEN:], log, tally
        # for the website's "Your plan alerts" card (index.json -> alerts.plans): the plan, open trades, results, channels
        report["plans"] = {"cfg": {k: pl_cfg[k] for k in ("lot", "sl_usd", "tp_usd", "cost_usd")},
                           "tp_first": pl_cfg["sl_px"] / (pl_cfg["sl_px"] + pl_cfg["tp_px"]),
                           "break_even": (pl_cfg["sl_usd"] + pl_cfg["cost_usd"]) / (pl_cfg["sl_usd"] + pl_cfg["tp_usd"]),
                           "open": state["plans"], "recent": log[::-1], "tally": tally, "tfs": list(tfs),
                           "late_frac": _env_float("PLAN_LATE_FRAC", LATE_FRAC)}
    if liq_on() and alerted:                               # price near a pool: once per run, not per timeframe
        ev = liquidity_near(payloads, tfs, seen, t_send)
        if ev:
            lines = [liq_text(r, off) for r in ev]
            report["liquidity_near"] = {"lines": lines, "sent": send(lines)}
            liq_log += ev
    keep_from = trading_day(t_send - 3 * 86400)
    state["liq_seen"] = {k: v for k, v in seen.items() if v >= keep_from}
    state["liq_log"] = liq_log[-_LIQ_LOG:]
    report["liquidity"] = {"on": liq_on(), "near_usd": _env_float("LIQ_NEAR_USD", LIQ_NEAR_USD), "recent": state["liq_log"][::-1]}
    report["channels"] = channels()
    first = next((payloads[tf] for tf in tfs if payloads.get(tf) and not payloads[tf]["meta"]["synthetic"]), None)
    if first is not None and pl_cfg:                       # validation: daily at the New York close, weekly at Friday's
        now_t = int(datetime.fromisoformat(first["meta"]["generated_utc"]).timestamp())
        cpl = pl_cfg["cost_usd"] / pl_cfg["lot"]
        report["plans"]["validation"] = validation_block(vlog, plans, now_t, cpl)
        day, week = trading_day(now_t), trading_week(now_t)
        lines = []
        if state.get("report_day") and state["report_day"] != day:
            prev = state["report_day"]
            recs = [r for r in vlog if trading_day(_decision_t(r)) == prev]
            n_open = sum(1 for p in plans if trading_day(_decision_t(p)) == prev)
            if recs or n_open:                             # a day without alerted signals (weekends) sends nothing
                lines += report_lines("DAILY", date.fromisoformat(prev).strftime("%a %d %b"), summarize(recs, cpl), n_open)
        if state.get("report_week") and state["report_week"] != week:
            prev = state["report_week"]
            recs = [r for r in vlog if trading_week(_decision_t(r)) == prev]
            n_open = sum(1 for p in plans if trading_week(_decision_t(p)) == prev)
            if recs or n_open:
                lines += report_lines("WEEKLY", prev, summarize(recs, cpl), n_open)
        state["report_day"], state["report_week"] = day, week
        if lines:
            report["validation_report"] = {"lines": lines, "sent": send(lines)}
    if first is not None:                                  # news is per release, not per timeframe: once per event
        now_t = int(datetime.fromisoformat(first["meta"]["generated_utc"]).timestamp())
        lines, state["news"] = news_lines(first.get("news"), now_t, state.get("news"))
        if lines:
            report["news"] = {"lines": lines, "sent": send(lines)}
    if path:
        with open(path, "w") as f:
            json.dump(state, f)
    if vpath and pl_cfg:
        with open(vpath, "w") as f:
            json.dump(vlog, f)
    return report
