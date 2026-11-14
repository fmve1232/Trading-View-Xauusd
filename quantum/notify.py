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
TWO TARGETS (operator, 2026-11-06: "TP1 +$13, TP2 +$20"): PLAN_TP2_USD ($1,000 = $20 at 0.5 lot; 0 = one TP). The
trade is two half positions with the same SL: one closes at TP1 (PLAN_TP_USD), then the other's SL moves to the fill
(break-even) and it runs to TP2. Results: SL (both halves), TP1 then BE, or TP1 then TP2. With no edge its expected
value equals one TP at TP1 (the rest reaches TP2 before the fill TP1 / TP2 of the time), so break-even is unchanged.
After TP1 a 5m bar touching TP2 and the fill counts as break-even unless it opened beyond TP2.
Plans are resolved on the 5-minute path when the same feed's 5m bars cover the signal's close (the trade_race and
B9 rules: a 5m bar touching both levels is a loss unless it opened beyond the TP); otherwise on the signal's own
timeframe. On 1h / 4h a whole bar can span both levels, and its close came up to 4 h after the touch (audit
2026-11-05). LADDER: the driftless odds of +$10 / +$13 / +$15 / +$20 before the plan's stop (B13-0: within 0.5 points
of S / (T + S) on 2020-2022 and on the live window), and whether two stops in one day fit a daily loss limit
(ACCOUNT_USD 25,000, DAILY_LIMIT_PCT 5).

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
STALE-SIGNAL PROTECTION (operator, 2026-11-11, after the 2026-11-10 outage): every new trade alert is FRESH (<= 15 min
after the close: unchanged), DELAYED (15-60 min: only after a fresh live-price check, labelled) or NOT ACTIONABLE
(> 60 min or the check failed: no plan, one summary line, results website-only). See freshness(); records unchanged.
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

import hashlib
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
TF_SEC = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}
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
def json_safe(x):
    """A copy with every NaN / infinite float replaced by None. index.json carries this report, and the browser's JSON.parse
    rejects NaN: the validation block's empty "today" / "this week" (rate = NaN when nothing was decided) made the whole
    alerts block unreadable on most days (found 2026-11-07). The state file keeps its own values."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: json_safe(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [json_safe(v) for v in x]
    return x


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


# ---------------- stale-signal protection (operator, 2026-11-11: "Historical signals recovered after an outage must never be
# presented as fresh actionable trading opportunities"; "Require fresh market-price validation before issuing any
# recovered or delayed trading plan") ----------------
# Every new trade alert (engine signal plan, SETUP, 4h breakout, grab test trade) is classified by its delay after the
# bar close, BEFORE it is presented; records are written exactly as before (the registered tests count signals from
# their close, not from the alert), only the phone presentation changes:
#   FRESH           delay <= FRESH_SEC: unchanged (normal in-session alerts measured 2.2-7.8 min after the close, 41 of
#                   41, 2026-11-03..11; a run every 15 min)
#   DELAYED         FRESH_SEC < delay <= RECOVERY_SEC: issued only after a fresh market-price check (a live quote read
#                   at most PRICE_FRESH_SEC before the alert; the move since the signal inside the LATE limit; the stop
#                   and the first target not yet traded), and labelled DELAYED
#   NOT ACTIONABLE  delay > RECOVERY_SEC, or the price check fails: no plan, no MT5 line; one summary line says so, and
#                   its later results stay off the phone (website only, prefixed RECORD_ONLY)
FRESH_SEC = 900           # one scheduler cycle
RECOVERY_SEC = 3600       # beyond an hour after the close the signal is history (e.g. recovered after an outage)
PRICE_FRESH_SEC = 300     # the re-check price must come from this run's download (the 5m forming bar)
RECORD_ONLY = "RECORD ONLY (its alert was not actionable) "
GATE_KEEP = 300
GATE_HOLD_SEC = 14 * 86400  # a NOT ACTIONABLE decision is kept this long: longer than any plan (3 days), setup (7) or
                            # grab test trade (5) is tracked, so pruning never lets a still-tracked result reach the phone


def _traded(bars: list, t_close: int, d: int, entry: float, sl_px: float, tp_px: float) -> str | None:
    """'SL' / 'TP' if a bar that opened at or after the signal's close traded the stop / the first target (a forming
    bar's high / low counts when the payload has them), else None."""
    for p in bars:
        if not p:
            continue
        ch, fb = p.get("chart") or {}, (p.get("meta") or {}).get("forming") or {}
        rows = list(zip(ch.get("t") or [], ch.get("h") or [], ch.get("l") or [], strict=False))
        if fb.get("t") is not None and fb.get("h") is not None and fb.get("l") is not None:
            rows.append((fb["t"], fb["h"], fb["l"]))
        for t, h, lo in rows:
            if t is None or h is None or lo is None or int(t) < t_close:
                continue
            stop = lo <= entry - sl_px if d == 1 else h >= entry + sl_px
            tgt = h >= entry + tp_px if d == 1 else lo <= entry - tp_px
            if stop or tgt:
                return "SL" if stop else "TP"
    return None


def freshness(t_close: int, d: int, entry: float, sl_px: float, tp_px: float, now: dict | None, bars: list) -> dict:
    """FRESH / DELAYED / NOT ACTIONABLE for a trade alert about to be presented (see the block comment above)."""
    t_now = int((now or {}).get("t") or 0)
    age = t_now - int(t_close)
    out = {"t_close": int(t_close), "t_alert": t_now, "age_min": round(age / 60, 1)}
    if age <= FRESH_SEC:
        return {**out, "state": "FRESH"}
    if age > RECOVERY_SEC:
        return {**out, "state": "NOT ACTIONABLE", "why": f"{age // 60} min after the close (limit {RECOVERY_SEC // 60})"}
    if entry is None:                                      # a signal without a price cannot be re-checked
        return {**out, "state": "NOT ACTIONABLE", "why": "no signal price to re-check it"}
    px, t_px = (now or {}).get("px"), (now or {}).get("t_px")
    if px is None or not now.get("live") or t_px is None or t_now - int(t_px) > PRICE_FRESH_SEC:
        return {**out, "state": "NOT ACTIONABLE", "why": "no live price to re-check it"}
    mv = (float(px) - entry) * d
    lim = _env_float("PLAN_LATE_FRAC", LATE_FRAC) * sl_px
    out.update(px_now=float(px), t_px=int(t_px), move=round(mv, 2), limit=round(lim, 2))
    if abs(mv) >= lim:
        return {**out, "state": "NOT ACTIONABLE", "why": f"price moved ${abs(mv):.2f} since the signal (limit ${lim:.2f})"}
    hit = _traded(bars, int(t_close), d, entry, sl_px, tp_px)
    if hit:
        return {**out, "state": "NOT ACTIONABLE", "why": f"its {'stop' if hit == 'SL' else 'first target'} was already traded"}
    return {**out, "state": "DELAYED"}


def delayed_line(fz: dict, off: float = 0.0) -> str:
    at = datetime.fromtimestamp(fz["t_px"], timezone.utc).strftime("%H:%M UTC")
    where = "toward TP" if fz["move"] > 0 else "toward SL" if fz["move"] < 0 else "unchanged"
    return (f"DELAYED ALERT: sent {fz['age_min']:.0f} min after the bar closed (normal: under {FRESH_SEC // 60}). Re-checked at the "
            f"live price {_fmt(fz['px_now'], off)} ({at}): ${abs(fz['move']):.2f} {where} since the signal, inside the "
            f"${fz['limit']:.2f} limit; stop and first target not yet traded. Valid only at the re-checked price")


def stale_line(what: str, items: list[str]) -> str:
    """One line for every alert of a kind that was not actionable in this run (no plan, no MT5 line)."""
    shown = "; ".join(items[:6]) + (f"; +{len(items) - 6} more" if len(items) > 6 else "")
    return (f"XAUUSD NOT ACTIONABLE: {len(items)} {what} recovered late -- no plan, do not trade "
            f"{'it' if len(items) == 1 else 'them'} (recorded for the tests only): {shown}")


def stale_item(side: str, label: str, t_close: int, px: float, fz: dict, off: float = 0.0) -> str:
    return (f"{label} {side} at {_fmt(px, off)}, bar closed {datetime.fromtimestamp(t_close, timezone.utc).strftime('%d %b %H:%M UTC')} "
            f"({fz.get('why')})")


def gate_note(state: dict, key: str, fz: dict) -> None:
    """Remember a non-FRESH decision (website + follow-up filter); bounded."""
    g = state.setdefault("fresh_gate", {})
    g[key] = {k: fz[k] for k in ("state", "age_min", "t_close", "t_alert", "why", "px_now", "move") if k in fz}
    if len(g) > GATE_KEEP:                                 # oldest first: DELAYED ones (they never quiet anything), then
        t_new = int(fz.get("t_alert") or 0)                # NOT ACTIONABLE ones past GATE_HOLD_SEC; never a newer one
        drop = [k for k, v in g.items() if v.get("state") != "NOT ACTIONABLE"] + \
               [k for k, v in g.items() if v.get("state") == "NOT ACTIONABLE" and t_new - int(v.get("t_alert") or 0) > GATE_HOLD_SEC]
        for k in drop:
            if len(g) <= GATE_KEEP:
                break
            if k != key:
                g.pop(k, None)


def gate_quiet(state: dict, kind: str) -> set:
    return {int(k.split(":", 1)[1]) for k, v in (state.get("fresh_gate") or {}).items()
            if k.startswith(kind + ":") and v.get("state") == "NOT ACTIONABLE"}


def phone_only(lines: list[str]) -> list[str]:
    """What may reach the phone: never a RECORD_ONLY line."""
    return [x for x in lines if not x.startswith(RECORD_ONLY)]


# Operator, 2026-11-13 (approved wording): every phone trading alert and follow-up opens with this disclaimer. Wording
# only: it is added to the phone text after every gate and filter, never to the website's alert lines, the plans, the
# plan validation or any research record, so no scoring and no historical record changes.
TRADE_DISCLAIMER = ("RECORD \u2014 NOT A VALIDATED SIGNAL \u2014 NO TRADE",
                    "This is a research-engine alert, not a trading recommendation. The strategy has not yet demonstrated "
                    "a validated live trading edge.")


def trade_msg(lines: list[str]) -> list[str]:
    """A phone trading alert or follow-up with the disclaimer on top; nothing at all when there is nothing to send
    (a disclaimer is never sent on its own)."""
    return [*TRADE_DISCLAIMER, *lines] if lines else []


def without_disclaimer(lines: list[str]) -> list[str]:
    """The alert's own lines, without the disclaimer (the delivery log names the alert by its first own line)."""
    return [x for x in lines if x not in TRADE_DISCLAIMER]


def mt5_line(d: int, pl: dict) -> str:
    s, side = ("+", "-") if d == -1 else ("-", "+")
    if pl.get("tp2_px"):
        half = round(pl["lot"] / 2, 2)
        return (f"ON MT5: {'BUY' if d == 1 else 'SELL'} 2 x {half:g} lot at market; SL on both = your fill {s} {pl['sl_px']:.2f}; "
                f"TP = your fill {side} {pl['tp_px']:.2f} on one and {side} {pl['tp2_px']:.2f} on the other; when the first "
                f"closes at TP, move the other's SL to your fill (= -${pl['sl_usd']:,.0f} total / +${pl['tp_usd'] / 2:,.0f} "
                f"then +${pl['tp2_usd'] / 2:,.0f}, at any broker price)")
    return (f"ON MT5: {'BUY' if d == 1 else 'SELL'} at market, then SL = your fill {s} {pl['sl_px']:.2f}, "
            f"TP = your fill {side} {pl['tp_px']:.2f} (= -${pl['sl_usd']:,.0f} / +${pl['tp_usd']:,.0f} at {pl['lot']:g} lot, "
            "at any broker price)")


LADDER_USD = (10.0, 13.0, 15.0, 20.0)       # the operator's range of moves (2026-11-05: "$10 to $20, $15 ideal")


def ladder_line(pl: dict) -> str:
    """The driftless chance of each move before the plan's stop, its value at the plan's lot, and the daily-limit check."""
    oz, sl = pl["lot"] * 100.0, pl["sl_px"]
    steps = " | ".join(f"+${a:g} {sl / (a + sl):.0%} (${a * oz:,.0f})" for a in LADDER_USD)
    acct, lim = _env_float("ACCOUNT_USD", 25000.0), _env_float("DAILY_LIMIT_PCT", 5.0)
    two = 2 * (pl["sl_usd"] + pl["cost_usd"])
    fits = two <= acct * lim / 100.0
    day = (f"2 stops in a day = -${two:,.0f} ({100 * two / acct:.1f}% of ${acct:,.0f}): "
           + ("inside" if fits else "OVER") + f" a {lim:g}% daily limit"
           + ("" if fits else f" -- only one loss a day fits at {pl['lot']:g} lot"))
    return f"LADDER before -${sl:.2f} (no signal beats these odds): {steps} | {day}"


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


# ---------------- part A of the 2026-11-05 signal audit (operator: "approve A without daily loss guard") ----------------
REPEAT_SEC = 4 * 3600      # A1: a same-direction signal within 4 hours ...
REPEAT_USD = 15.0          # ... and $15 of an OPEN plan (any timeframe) is the same idea: no new plan (declared 2026-11-05)
TURN_MIN_TFS = 2           # A2: same-direction BREAKs on 2+ timeframes in one trading day ...
TURN_KEEP = 20
_HTF_LAYERS = (("15", "15m", 900), ("60", "1h", 3600), ("240", "4h", 14400), ("D", "1D", 86400))
_TF_ORDER = ("5m", "15m", "30m", "1h", "4h")


def repeat_of(m: dict, tf: str, plans: list[dict]) -> dict | None:
    """A1: the open plan this SIGNAL repeats (same direction, decision within REPEAT_SEC, entry within REPEAT_USD)."""
    t_dec = int(m["t"]) + TF_SEC.get(tf, 0)
    hits = [p for p in plans if p.get("dir") == m.get("dir") and abs(t_dec - _decision_t(p)) <= REPEAT_SEC
            and m.get("px") is not None and abs(float(m["px"]) - float(p["entry"])) <= REPEAT_USD]
    return min(hits, key=_decision_t) if hits else None


def repeat_line(m: dict, tf: str, rp: dict, off: float = 0.0, quiet: bool = False) -> str:
    side = "BUY" if m["dir"] == 1 else "SELL"
    when = datetime.fromtimestamp(_decision_t(rp), timezone.utc).strftime("%H:%M UTC")
    if quiet:                                              # its plan was never offered: say so, do not imply a position
        return (f"REPEAT of #{rp.get('id', '?')} ({rp['tf']} {side} from {_fmt(rp['entry'], off)} at {when}), which was NOT "
                f"ACTIONABLE (sent late, no plan): the same idea -- no plan from this repeat either")
    return (f"REPEAT of #{rp.get('id', '?')} ({rp['tf']} {side} from {_fmt(rp['entry'], off)} at {when}, still open): "
            f"the same idea -- don't add a trade (no new plan)")


def _breaks_today(liq_log: list[dict], day: str) -> list[dict]:
    return [r for r in liq_log if r.get("kind") == "BREAK" and r.get("tf") in TF_SEC
            and trading_day(int(r["t"]) + TF_SEC[r["tf"]]) == day]


def context_line(payload: dict, d: int, breaks: list[dict]) -> str | None:
    """A3: the higher timeframes, regime and session at this run, and a warning when the signal goes against today's
    latest previous day / week high or low break."""
    db = payload.get("dashboard") or {}
    sc = (db.get("mtf") or {}).get("scores") or {}
    tf_sec = TF_SEC.get(payload["meta"]["tf"], 0)
    parts, agree, against = [], 0, 0
    for k, lbl, sec in _HTF_LAYERS:
        v = sc.get(k)
        if sec <= tf_sec or v is None:
            continue
        a = 1 if v >= 60 else -1 if v <= 40 else 0
        parts.append(f"{lbl} {'▲' if a == 1 else '▼' if a == -1 else '='}")
        agree += a == d
        against += a == -d
    if not parts and not db:
        return None
    reg, sess = (db.get("regime") or {}).get("label"), (db.get("session") or {}).get("label")
    s = (f"CONTEXT (now): higher timeframes {' '.join(parts) or 'n/a'} ({agree} agree, {against} against) | "
         f"regime {reg or '—'} | session {sess or '—'}")
    if breaks:
        last = max(breaks, key=lambda r: int(r["t"]) + TF_SEC[r["tf"]])
        bd = 1 if last["name"] in _HIGHS else -1
        if bd == -d:
            hhmm = datetime.fromtimestamp(int(last["t"]) + TF_SEC[last["tf"]], timezone.utc).strftime("%H:%M UTC")
            s += f" | ⚠ against today's {last['name']} {last['px']:.2f} break ({last['tf']}, {hhmm})"
    return s


def turn_lines(state: dict, payloads: dict, tfs: list[str], liq_log: list[dict], plans_today: list[dict], t_send: int,
               off: float = 0.0) -> list[str]:
    """A2: same-direction BREAKs of PDH / PWH (or PDL / PWL) on TURN_MIN_TFS+ timeframes today, while the engine's
    higher-timeframe gate blocks that side (align >= 2 of the layers above the chart) or today's alerted signals were
    the other way: one warning per direction per trading day. Information, not a signal."""
    day = trading_day(t_send)
    brk = _breaks_today(liq_log, day)
    sent = state.setdefault("turn_sent", {})
    ref = next((payloads[x] for x in ["15m", *tfs] if payloads.get(x) and not payloads[x]["meta"].get("synthetic")), None)
    mtf = ((ref or {}).get("dashboard") or {}).get("mtf") or {}
    out = []
    for direction in (1, -1):
        mine = [r for r in brk if (1 if r["name"] in _HIGHS else -1) == direction]
        tfs_dir = sorted({r["tf"] for r in mine}, key=_TF_ORDER.index)
        key = f"{day}|{direction}"
        if len(tfs_dir) < TURN_MIN_TFS or key in sent:
            continue
        n_block = int(mtf.get("align_short" if direction == 1 else "align_long") or 0)
        opp = [p for p in plans_today if p.get("dir") == -direction]
        if n_block < 2 and not opp:
            continue
        up = direction == 1
        pools = ", ".join(sorted({f"{r['name']} {_fmt(r['px'], off)}" for r in mine}))
        why = []
        if n_block >= 2:
            why.append(f"the engine's higher-timeframe gate still blocks {'BUY' if up else 'SELL'} signals "
                       f"({n_block} higher timeframes read {'down' if up else 'up'}; it lags)")
        if opp:
            why.append(f"today's {len(opp)} alerted signal(s) were {'SELL' if up else 'BUY'}")
        out.append(f"XAUUSD TREND-CHANGE WARNING: price closed {'above' if up else 'below'} {pools} on {', '.join(tfs_dir)} today "
                   f"({'buy' if up else 'sell'}-side liquidity taken, holding beyond) -- {'; '.join(why)}. "
                   f"Don't {'SELL' if up else 'BUY'} into it; the engine may stay silent on this move | info, not a trade signal")
        sent[key] = t_send
        state["turn_log"] = (state.get("turn_log", []) + [{"t": t_send, "dir": direction, "tfs": tfs_dir, "pools": pools,
                                                           "blocked": n_block, "opposite_signals": len(opp)}])[-TURN_KEEP:]
    keep_from = trading_day(t_send - 3 * 86400)
    state["turn_sent"] = {k: v for k, v in sent.items() if k.split("|")[0] >= keep_from}
    return out


def messages(payload: dict, since_t: int | None, now: dict | None = None, ctx: dict | None = None,
             signals_only: bool = False) -> list[str]:
    """Alert lines for bars closed after since_t. `now` ({'t' send time, 'px', 't_px', 'live'}) adds the MT5 and
    timing lines to each SIGNAL; `ctx` ({'repeats': {bar t: plan}, 'breaks': today's BREAKs}) the REPEAT and CONTEXT
    lines (part A, 2026-11-05). signals_only: the SIGNAL alerts alone (the phone in sixty mode)."""
    tf = payload["meta"]["tf"]
    off = float(os.environ.get("MT5_PRICE_OFFSET", "0") or 0)
    out, stale, stale_at = [], [], None
    for m in payload["markers"]:
        if since_t is not None and m["t"] <= since_t:
            continue
        if m["type"] == "SIGNAL":
            d = "BUY" if m["dir"] == 1 else "SELL"
            fz = ((ctx or {}).get("fresh") or {}).get(m["t"])      # stale-signal protection (None = FRESH, as before)
            if fz and fz["state"] == "NOT ACTIONABLE":
                stale_at = len(out) if stale_at is None else stale_at
                stale.append(stale_item(d, f"{tf} signal", int(m["t"]) + TF_SEC.get(tf, 0), m["px"], fz, off))
                continue
            out.append(f"XAUUSD {tf} {d} (confirmed close) | entry {_fmt(m['px'], off)} SL {_fmt(m['sl'], off)} "
                       f"TP1 {_fmt(m['tp1'], off)} TP2 {_fmt(m['tp2'], off)} TP3 {_fmt(m['tp3'], off)} | TQ {m['tq']}")
            if fz and fz["state"] == "DELAYED":
                out.append(delayed_line(fz, off))                  # second line: visible in the phone's preview
            rp = ((ctx or {}).get("repeats") or {}).get(m["t"])
            if rp is not None:
                out.append(repeat_line(m, tf, rp, off, quiet=rp.get("id") in ((ctx or {}).get("quiet") or ())))
                continue
            pl = plan_cfg()
            late, timing = timing_lines(alert_timing(m, tf, now, pl), off)
            if late:
                out.append(late)                           # second line: visible in the phone's preview
            if pl and m.get("px") is not None:
                out.append(plan_line(m["px"], m["dir"], pl, off))
                out.append(mt5_line(m["dir"], pl))
                out.append(ladder_line(pl))
            if timing:
                out.append(timing)
            cl = context_line(payload, m["dir"], (ctx or {}).get("breaks") or []) if ctx is not None else None
            if cl:
                out.append(cl)
            if sixty() and tf in SIGNAL_RECORD:
                out.append(SIGNAL_RECORD[tf])
        elif signals_only:
            continue
        elif m["type"] == "TRACK_EXIT":
            out.append(f"XAUUSD {tf} tracked plan {'STOPPED' if (m.get('r') or 0) < 0 else 'reached TP1'} at {_fmt(m['px'], off)} = {m.get('r')}R")
        elif m["type"] == "RISK_LOCK":
            out.append(f"XAUUSD {tf} RISK LOCK engaged -- new entries blocked")
    if stale:
        out.insert(stale_at, stale_line("engine signal" + ("s" if len(stale) > 1 else ""), stale))
    if signals_only:
        return out
    if os.environ.get("ALERT_STRUCTURE", "1").strip() != "0" and not quality():
        out += structure_lines(payload, since_t, off, sweeps=not liq_on(), rec=(ctx or {}).get("h_records"))
    for d in payload["decisions"]:
        if since_t is not None and d["t"] <= since_t:
            continue
        if d["to"] in ("BUY", "SELL"):
            continue  # already covered by the SIGNAL message
        out.append(f"XAUUSD {tf} DECISION {d['from']} -> {d['to']}")
    return out


_TAG = {("BOS", 1): "BOS▲", ("BOS", -1): "BOS▼", ("CHoCH", 1): "CHoCH▲", ("CHoCH", -1): "CHoCH▼",
        ("MSS", 1): "MSS▲", ("MSS", -1): "MSS▼", ("SWEEP", 1): "SWEEP-LOW", ("SWEEP", -1): "SWEEP-HIGH"}


def structure_lines(payload: dict, since_t: int | None, off: float = 0.0, sweeps: bool = True,
                    rec: dict | None = None) -> list[str]:
    """One line per newly closed bar: its structure / sweep events and any H2 / H3 setup on it. sweeps=False leaves
    the sweeps to the LIQUIDITY alerts (one per pool per day instead of one per bar). rec: each setup's forward record
    on this timeframe (h_records), shown on its line so an unproven setup is not read as a trade call."""
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
                r = (rec or {}).get(arm)
                tail = (f" [forward record: {r['n']} trades, {r['won']} won, {r['pts']:+.1f} pts]" if r and r["n"] else "")
                by_t.setdefault(g["t"], []).append(f"{arm.upper()} {'BUY' if g['dir'] == 'LONG' else 'SELL'} entry {_fmt(g['entry'], off)} "
                                                   f"SL {_fmt(g['sl'], off)} TP1 {_fmt(g['tp1'], off)} TP2 {_fmt(g['tp2'], off)}{tail}")
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


LIQ_HIST = {"GRAB": (0.494, 913), "BREAK": (0.503, 895)}   # B10 development 2020-22, 15m, +13 / -13, all regimes


def _liq_hist(kind: str) -> str:
    rate, n = LIQ_HIST[kind]
    return f"2020-22: +$13 before -$13 after a {kind} {rate:.0%} of {n:,} (random 50%)"


def liq_text(r: dict, off: float = 0.0) -> str:
    nm, lv, side = r["name"], _fmt(r["px"], off), _liq_side(r["name"])
    also = "".join(f" + {a} {_fmt(x, off)}" for a, x in r.get("also") or [])
    if r["kind"] == "NEAR":
        where = "below" if r["name"] in _HIGHS else "above"
        return (f"XAUUSD LIQUIDITY NEAR: price {_fmt(r['price'], off)} is ${r['dist']:.2f} {where} {nm} {lv} ({side}) | "
                f"{clocks(r['t'])} | watch for a grab (wick through, close back) or a break | info, not a trade signal")
    bar, side = f"{r['tf']} bar {clocks(r['t'])}", side.rsplit(" ", 1)[0]       # "buy-side liquidity"
    if r["kind"] == "GRAB":
        lows = r["name"] not in _HIGHS
        return (f"XAUUSD {r['tf']} LIQUIDITY GRAB: {nm} {lv}{also} swept -- {'low' if lows else 'high'} {_fmt(r.get('wick'), off)}, "
                f"closed back {'above' if lows else 'below'} at {_fmt(r.get('close'), off)} ({side} taken, then rejected) | "
                f"{bar} | {_liq_hist('GRAB')} | info, not a trade signal")
    hi = r["name"] in _HIGHS
    return (f"XAUUSD {r['tf']} LIQUIDITY BREAK: {nm} {lv}{also} broken -- closed {'above' if hi else 'below'} at "
            f"{_fmt(r.get('close'), off)} ({side} taken, price holding beyond) | {bar} | {_liq_hist('BREAK')} | info, not a trade signal")


def liq_lines(ev: list[dict], seen: dict, off: float = 0.0) -> list[str]:
    """Phone lines for GRAB / BREAK events: one per pool per trading day ACROSS timeframes (the first timeframe that
    shows it; the others stay in the log for the site and the A2 warning), and pools taken on the same bar in the same
    direction in one line (audit 2026-11-06: 27 alerts for 6 market events). Marks each event sent / not sent."""
    groups: dict = {}
    for r in ev:
        r["sent"] = _first_today(seen, ("SENT", r["kind"], r["name"], f"{r['px']:.2f}"), r["t"])
        if r["sent"]:
            groups.setdefault((r["t"], r["kind"], r["name"] in _HIGHS), []).append(r)
    return [liq_text({**rs[0], "also": [(x["name"], x["px"]) for x in rs[1:]]}, off) for _, rs in sorted(groups.items())]


# ---------------- B9-GRAB-FWD: the registered live test of the liquidity GRAB (research/registrations/B9-GRAB-FWD.json) ----
GRAB_ID = "B9-GRAB-FWD"
GRAB_DIR, GRAB_FILE = "research_forward", "B9-GRAB-FWD.json"   # in the store; copied to forward-ledger (git history)
GRAB_TFS = ("15m", "30m", "1h", "4h")    # registered timeframes, in this order within a run
GRAB_TP = GRAB_SL = 13.0                 # price $: +$650 / -$650 at 0.5 lot
GRAB_H = 288                             # five-minute bars: one trading day
GRAB_WAIT = 3 * 86400                    # the first path bar more than 3 days after the close is a data hole (GAP)
GRAB_STALE = 5 * 86400                   # an open test trade not resolvable for 5 days (missing path) is GAP
GRAB_BE = (13.0 + 0.26) / 26.0           # break-even 51.0%
GRAB_LOOKS = tuple(range(30, 101, 10))   # the verdict is checked only at these numbers of decided results
GRAB_DEADLINE = "2027-03-31"


def grab_new(payload: dict, since_t: int | None, started: int, seen: dict) -> list[dict]:
    """New test trades on this timeframe's bars closed after since_t: one per pool per trading day (the first
    timeframe that shows it wins: `seen` is shared by the four timeframes); one trade per bar."""
    tf, ch = payload["meta"]["tf"], payload.get("chart") or {}
    t, c = ch.get("t") or [], ch.get("c") or []
    at = {tt: k for k, tt in enumerate(t)}
    out = []
    for m in payload["markers"]:
        if m["type"] != "SWEEP" or m.get("dir") not in (1, -1) or (since_t is not None and m["t"] <= since_t):
            continue
        t_close = int(m["t"]) + TF_SEC.get(tf, 0)
        k = at.get(m["t"])
        if t_close <= started or k is None or k >= len(c) or c[k] is None:
            continue
        pools = [x for x in m.get("lvl") or [] if x.get("px") is not None]
        fresh = [x for x in pools if _first_today(seen, ("GRAB", x["name"], f"{x['px']:.2f}"), t_close)]
        if not fresh:
            continue
        d, e = int(m["dir"]), float(c[k])
        out.append({"tf": tf, "t": int(m["t"]), "t_close": t_close, "dir": d, "pools": [x["name"] for x in fresh],
                    "levels": [x["px"] for x in fresh], "wick": m.get("px"), "entry": e,
                    "tp": round(e + d * GRAB_TP, 2), "sl": round(e - d * GRAB_SL, 2),
                    "src": payload["meta"].get("price_source"), "status": "OPEN", "mfe": 0.0, "mae": 0.0})
    return out


def grab_resolve(tr: dict, p5: dict | None, now_t: int) -> dict:
    """The test trade's status on the 5-minute path (quantum/trade_race.py rules): TP / SL / NONE / GAP, or OPEN."""
    if p5 is None or p5["meta"].get("synthetic") or p5["meta"].get("price_source") != tr.get("src"):
        return {**tr, "status": "GAP", "t_res": now_t} if now_t - tr["t_close"] > GRAB_STALE else tr
    ch = p5.get("chart") or {}
    t, o, h, l = ch.get("t") or [], ch.get("o") or [], ch.get("h") or [], ch.get("l") or []
    j = next((i for i, x in enumerate(t) if x >= tr["t_close"]), None)
    if j is None:
        return {**tr, "status": "GAP", "t_res": now_t} if now_t - tr["t_close"] > GRAB_STALE else tr
    if (j == 0 and t[0] > tr["t_close"]) or t[j] - tr["t_close"] > GRAB_WAIT:
        return {**tr, "status": "GAP", "t_res": now_t}      # the path's start is not in the data
    d, e, mfe, mae = tr["dir"], tr["entry"], 0.0, 0.0
    end = min(j + GRAB_H, len(t))
    for k in range(j, end):
        if h[k] is None or l[k] is None:
            continue
        fav, adv = ((h[k] - e), (e - l[k])) if d == 1 else ((e - l[k]), (h[k] - e))
        mfe, mae = max(mfe, fav), max(mae, adv)
        hit_tp, hit_sl = fav >= GRAB_TP - 1e-9, adv >= GRAB_SL - 1e-9
        if hit_tp or hit_sl:
            win = hit_tp and (not hit_sl or (o[k] is not None and (o[k] - e) * d >= GRAB_TP - 1e-9))
            return {**tr, "status": "TP" if win else "SL", "t_res": int(t[k]), "bars": k - j + 1,
                    "mfe": round(mfe, 2), "mae": round(mae, 2)}
    if j + GRAB_H <= len(t):
        return {**tr, "status": "NONE", "t_res": int(t[j + GRAB_H - 1]), "bars": GRAB_H, "mfe": round(mfe, 2), "mae": round(mae, 2)}
    return {**tr, "mfe": round(mfe, 2), "mae": round(mae, 2)}


def grab_verdict(trades: list[dict], book: dict, now_t: int) -> dict:
    """Checks only at 30, 40 ... 100 decided results, in the order they were decided; PROVEN when the Wilson 95%
    lower bound is above break-even at a check; NOT PROVEN at 100 or after the deadline. A verdict is final."""
    dec = sorted((x for x in trades if x["status"] in ("TP", "SL")), key=lambda x: (x["t_res"], x["id"]))
    checks = list(book.get("checks") or [])
    verdict = book.get("verdict")
    if verdict is None:
        for look in GRAB_LOOKS:
            if len(dec) < look or any(ch["n"] == look for ch in checks):
                continue
            k = sum(x["status"] == "TP" for x in dec[:look])
            lo, hi = _wilson(k, look)
            checks.append({"n": look, "tp": k, "wilson": [lo, hi], "utc": now_t, "proven": lo > GRAB_BE})
            if lo > GRAB_BE:
                verdict = {"verdict": "PROVEN", "at_n": look, "utc": now_t}
                break
        if verdict is None and (len(dec) >= GRAB_LOOKS[-1] or
                                datetime.fromtimestamp(now_t, timezone.utc).date() > date.fromisoformat(GRAB_DEADLINE)):
            verdict = {"verdict": "NOT PROVEN", "at_n": len(dec), "utc": now_t}
    n, k = len(dec), sum(x["status"] == "TP" for x in dec)
    lo, hi = _wilson(k, n)
    nxt = next((x for x in GRAB_LOOKS if x > n), None)
    status = (f"{verdict['verdict']} at {verdict['at_n']} results" if verdict else
              f"COLLECTING: {n} results, {k / n:.0%} TP first; first check at {GRAB_LOOKS[0]}" if n and n < GRAB_LOOKS[0] else
              f"COLLECTING: {n} results, {k / n:.0%} TP first; next check at {nxt}" if n else
              f"COLLECTING: no result yet; first check at {GRAB_LOOKS[0]}")
    return {"checks": checks, "verdict": verdict, "n": n, "tp": k, "sl": n - k, "rate": k / n if n else None,
            "wilson": [lo, hi] if n else None, "next_check": None if verdict else nxt, "status": status}


# ---------------- SETUP: the operator's level rules (research/registrations/B16.json; operator, 2026-11-06) ----------------
SETUP_TOL_USD = 3.0                              # zone tolerance, $ of price (scaled by price / 4000 in the research test)
SETUP_HI = ("PDH", "PWH", "PMH", "TDH", "4HH", "1HH")
SETUP_LO = ("PDL", "PWL", "PML", "TDL", "4HL", "1HL")
SETUP_NAMES = {"PDH": "previous day high", "PWH": "previous week high", "PMH": "previous month high", "TDH": "today's high",
               "4HH": "last 4h high", "1HH": "last 1h high", "PDL": "previous day low", "PWL": "previous week low",
               "PML": "previous month low", "TDL": "today's low", "4HL": "last 4h low", "1HL": "last 1h low"}


def _prev_month(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def setup_levels(t: list, h: list, lo_: list, h1: dict, h4: dict) -> dict:
    """Per trigger bar (bar open times t): today's high / low from the bars BEFORE it in the same New York trading day,
    the high / low of the last 1h and 4h bars that closed at or before its open, and the previous trading month's
    high / low (from the 1h bars). None where unknown."""
    n = len(t)
    out = {k: [None] * n for k in ("TDH", "TDL", "1HH", "1HL", "4HH", "4HL", "PMH", "PML")}
    day, dh, dl = None, None, None
    for i in range(n):
        d = trading_day(int(t[i]))
        if d != day:
            day, dh, dl = d, None, None
        out["TDH"][i], out["TDL"][i] = dh, dl
        if h[i] is not None:
            dh = h[i] if dh is None else max(dh, h[i])
        if lo_[i] is not None:
            dl = lo_[i] if dl is None else min(dl, lo_[i])
    for key, ch, sec in (("1H", h1, 3600), ("4H", h4, 14400)):
        ct, chh, cll = (ch or {}).get("t") or [], (ch or {}).get("h") or [], (ch or {}).get("l") or []
        j = -1
        for i in range(n):
            while j + 1 < len(ct) and ct[j + 1] + sec <= t[i]:
                j += 1
            if j >= 0:
                out[key + "H"][i], out[key + "L"][i] = chh[j], cll[j]
    ct, chh, cll = (h1 or {}).get("t") or [], (h1 or {}).get("h") or [], (h1 or {}).get("l") or []
    mon: dict = {}
    for k in range(len(ct)):
        if chh[k] is None or cll[k] is None:
            continue
        ym = trading_day(int(ct[k]))[:7]
        a = mon.setdefault(ym, [chh[k], cll[k]])
        a[0], a[1] = max(a[0], chh[k]), min(a[1], cll[k])
    first = min(mon) if mon else None
    for i in range(n):
        pm = _prev_month(trading_day(int(t[i]))[:7])
        if pm in mon and pm != first:                 # the first month in the data may be partial
            out["PMH"][i], out["PML"][i] = mon[pm]
    return out


def _setup_zone(L: float, side: int, zb: tuple, tol: float) -> str | None:
    """The zone a swept level sits in: the active order block on the trade's side, the value-area edge, or the POC."""
    bl, bh, sl_, sh, vah, val, poc = zb
    if side > 0 and bl is not None and bh is not None and bl - tol <= L <= bh + tol:
        return f"bull order block {bl:.2f}-{bh:.2f}"
    if side < 0 and sl_ is not None and sh is not None and sl_ - tol <= L <= sh + tol:
        return f"bear order block {sl_:.2f}-{sh:.2f}"
    va = val if side > 0 else vah
    if va is not None and abs(L - va) <= tol:
        return f"value-area {'low' if side > 0 else 'high'} {va:.2f}"
    if poc is not None and abs(L - poc) <= tol:
        return f"POC {poc:.2f}"
    return None


def setup_events(t: list, h: list, lo_: list, c: list, lv: dict, z: dict, rows, seen: dict, scale: bool = False) -> list[dict]:
    """The registered rules on each bar in rows. lv: level name -> per-bar values (SETUP_HI / SETUP_LO); z: per-bar
    ob_bull_lo / ob_bull_hi / ob_bear_lo / ob_bear_hi / vah / val / vpoc. One event per setup and direction per bar; a
    level counts once per setup, direction and trading day (seen)."""
    def g(k, i):
        a = z.get(k)
        x = a[i] if a is not None and i < len(a) else None
        return None if x is None or (isinstance(x, float) and math.isnan(x)) else x

    out = []
    for i in rows:
        if i < 1 or c[i] is None or c[i - 1] is None or h[i] is None or lo_[i] is None:
            continue
        tol = SETUP_TOL_USD * (c[i] / 4000.0 if scale else 1.0)
        bl, bh, sl_, sh = g("ob_bull_lo", i), g("ob_bull_hi", i), g("ob_bear_lo", i), g("ob_bear_hi", i)
        vah, val, poc = g("vah", i), g("val", i), g("vpoc", i)
        zb = (bl, bh, sl_, sh, vah, val, poc)
        cand = []
        for name in SETUP_LO:                                      # SWEEP BUY: low through a low-side level, close back above
            L = (lv.get(name) or [None] * (i + 1))[i]
            if L is not None and lo_[i] < L < c[i]:
                zn = _setup_zone(L, 1, zb, tol)
                if zn:
                    cand.append(("SWEEP", 1, name, L, zn))
        for name in SETUP_HI:                                      # SWEEP SELL: the mirror
            L = (lv.get(name) or [None] * (i + 1))[i]
            if L is not None and c[i] < L < h[i]:
                zn = _setup_zone(L, -1, zb, tol)
                if zn:
                    cand.append(("SWEEP", -1, name, L, zn))
        in_bear = sl_ is not None and sh is not None and sl_ <= c[i] <= sh
        in_bull = bl is not None and bh is not None and bl <= c[i] <= bh
        for name in SETUP_HI:                                      # BREAKOUT BUY: close above a high-side level, above value
            L = (lv.get(name) or [None] * (i + 1))[i]
            if L is not None and c[i] > L >= c[i - 1] and vah is not None and c[i] > vah and not in_bear:
                cand.append(("BREAKOUT", 1, name, L, f"above value-area high {vah:.2f}"))
        for name in SETUP_LO:                                      # BREAKOUT SELL: the mirror
            L = (lv.get(name) or [None] * (i + 1))[i]
            if L is not None and c[i] < L <= c[i - 1] and val is not None and c[i] < val and not in_bull:
                cand.append(("BREAKOUT", -1, name, L, f"below value-area low {val:.2f}"))
        groups: dict = {}
        for kind, d, name, L, zn in cand:
            if _first_today(seen, ("SETUP", kind, d, name, f"{L:.2f}"), int(t[i])):
                groups.setdefault((i, kind, d), []).append((name, L, zn))
        for (ii, kind, d), lst in groups.items():
            out.append({"i": ii, "t": int(t[ii]), "kind": kind, "dir": d, "close": c[ii], "levels": [(a, b) for a, b, _ in lst],
                        "zones": sorted({x for _, _, x in lst}), "low": lo_[ii], "high": h[ii]})
    return out


SETUP_ZKEYS = ("ob_bull_lo", "ob_bull_hi", "ob_bear_lo", "ob_bear_hi", "vah", "val", "vpoc")
SETUP_TP_PX, SETUP_SL_PX = 15.0, 13.0           # the registered outcome: +$15 before -$13 (B16)
SETUP_TRACK_SEC = 86400                          # one trading day OF BARS, as in the test (B16-B18: 96 15m bars)
SETUP_STALE_SEC = 7 * 86400                      # clock limit if the feed stops (a weekend is not trading time)
SETUP_FILE = "SETUP-LIVE.json"                   # <store>/research_forward/: every alerted setup and its result
SETUP_HIST = {"SWEEP": (0.466, 5918, 0.462, "not an edge"),        # B16 development 2020-22 (research/B16_RESULTS.md):
              "BREAKOUT": (0.461, 6729, 0.463, "not an edge")}     # +$15 before -$13, rate, n, random same mix, verdict
SETUP_MAJOR = ("PDH", "PDL", "PWH", "PWL", "PMH", "PML")         # SETUP_LEVELS=major: day / week / month levels only
SETUP_HIST_CONFIRMED: tuple | None = (0.516, 184, 0.463, "not proven (p 0.07)")   # B17 development result, all 4


def _ema(xs: list, n: int) -> list:
    out, e, a = [], None, 2.0 / (n + 1)
    for x in xs:
        if x is not None:
            e = x if e is None else e + a * (x - e)
        out.append(e)
    return out


def trend_votes(t: list, h1: dict | None, h4: dict | None) -> list:
    """Per bar (open times t), the sum of the three B12 trend votes, each +1 (up) or -1 (down): the last completed
    trading day's close against its 20-day average (days from the 1h bars), and the last completed 4h and 1h bars'
    EMA20 against EMA50. None until all three are known."""
    def ema_side(ch):
        ct, cc = (ch or {}).get("t") or [], (ch or {}).get("c") or []
        e20, e50 = _ema(cc, 20), _ema(cc, 50)
        return ct, [None if a is None or b is None else (1 if a > b else -1) for a, b in zip(e20, e50)]
    t1, v1 = ema_side(h1)
    t4, v4 = ema_side(h4)
    days: list = []                                       # (trading day, last close)
    for tt, cc in zip((h1 or {}).get("t") or [], (h1 or {}).get("c") or []):
        if cc is None:
            continue
        d = trading_day(int(tt))
        if days and days[-1][0] == d:
            days[-1] = (d, cc)
        else:
            days.append((d, cc))
    vd = {}
    for k in range(19, len(days)):
        sma = sum(x for _, x in days[k - 19:k + 1]) / 20.0
        vd[days[k][0]] = 1 if days[k][1] > sma else -1
    order = [d for d, _ in days]
    out, j1, j4, kd = [], -1, -1, -1
    for x in t:
        while j1 + 1 < len(t1) and t1[j1 + 1] + 3600 <= x:
            j1 += 1
        while j4 + 1 < len(t4) and t4[j4 + 1] + 14400 <= x:
            j4 += 1
        today = trading_day(int(x))
        while kd + 1 < len(order) and order[kd + 1] < today:   # t is in time order: the last day before today
            kd += 1
        prev = order[kd] if kd >= 0 else None
        a = v1[j1] if j1 >= 0 else None
        b = v4[j4] if j4 >= 0 else None
        c_ = vd.get(prev) if prev else None
        out.append(None if a is None or b is None or c_ is None else a + b + c_)
    return out


SETUP_SESSIONS = ("London", "London+NY", "New York")


def setup_checks(e: dict, votes: list, bull: list, bear: list) -> dict:
    """B17's four confirmations of a B16 setup (research/registrations/B17.json)."""
    i, d = e["i"], e["dir"]
    v = votes[i] if i < len(votes) else None
    bu = bull[i] if i < len(bull) else None
    be = bear[i] if i < len(bear) else None
    return {"major": any(nm in SETUP_MAJOR for nm, _ in e["levels"]),
            "trend": v is not None and v == 3 * d,
            "bias": bu is not None and be is not None and ((bu >= be) if d > 0 else (be >= bu)),
            "session": session_of(e["t"] + 900) in SETUP_SESSIONS}


def h4_events(t4: list, h4: list, l4: list, c4: list, bull4: list, bear4: list, lv4: dict, votes4: list, rows) -> list[dict]:
    """B18 (research/registrations/B18.json) on closed 4h candles (open times t4): a close above the previous 4h high
    (BUY) or below its low (SELL), with the four confirmations: beyond a previous day / week / month level in that
    direction, all three trend votes at the close (votes4), the engine's own bias on the candle, a London / New York
    close. One event per breakout candle."""
    out = []
    for i in rows:
        if i < 1 or c4[i] is None or h4[i - 1] is None or l4[i - 1] is None:
            continue
        d = 1 if c4[i] > h4[i - 1] else -1 if c4[i] < l4[i - 1] else 0
        if d == 0:
            continue
        names = ("PDH", "PWH", "PMH") if d > 0 else ("PDL", "PWL", "PML")
        beyond = []
        for nm in names:
            x = (lv4.get(nm) or [None] * (i + 1))[i]
            if x is not None and (c4[i] - x) * d > 0:
                beyond.append((nm, x))
        bu, be = bull4[i] if i < len(bull4) else None, bear4[i] if i < len(bear4) else None
        v = votes4[i] if i < len(votes4) else None
        checks = {"major": bool(beyond), "trend": v is not None and v == 3 * d,
                  "bias": bu is not None and be is not None and ((bu >= be) if d > 0 else (be >= bu)),
                  "session": session_of(int(t4[i]) + 14400) in SETUP_SESSIONS}
        out.append({"i": i, "t": int(t4[i]), "t_close": int(t4[i]) + 14400, "dir": d, "close": c4[i], "kind": "4H BREAKOUT",
                    "prev_high": h4[i - 1], "prev_low": l4[i - 1], "beyond": beyond, "checks": checks,
                    "confirmed": all(checks.values())})
    return out


PHONE_TFS_SIXTY = ("15m",)
# Operator, 2026-11-06: "ALERTS WITH MORE THAN 60% SUCCESSFUL TRADES ONLY". The one alert stream whose measured record is
# above 60% (stop -$13): the engine's 15m signals, 64.3% of 70 at +$13 (B10, 2020-22) and 61.4% of 44 (B13-1, 2023-24,
# not passed after Holm). 1h signals 40.0% of 25 (B10); 30m / 4h signals never measured; setups 51.6% (B17) / 45.8% (B18);
# liquidity grabs 49.4% of 913 (B10). Live Sep-Nov 2026 the 15m signals did 31.8% of 22 (B9-explore): not proven.
SIGNAL_RECORD = {"15m": "RECORD of 15m engine signals (stop -$13): 64% of 70 (2020-22), 61% of 44 (2023-24); live Sep-Nov 2026 "
                        "32% of 22 | live test B15 running | the only alert above 60% on history, not proven"}


def alert_mode() -> str:
    """ALERT_MODE: sixty (default since 2026-11-06), quality or all; unset or empty = sixty."""
    return (os.environ.get("ALERT_MODE") or "").strip().lower() or "sixty"


def sixty() -> bool:
    """sixty (operator, 2026-11-06, "ALERTS WITH MORE THAN 60% SUCCESSFUL TRADES ONLY"): quality mode, and the phone
    gets only the engine's 15m signals with their plan follow-ups (PHONE_TFS_SIXTY), the registered engine test's checks,
    the daily report and news. Every other stream (30m / 1h / 4h signals, setups, 4h breakouts, the grab test's trades,
    the trend-change warning, DECISION / RISK LOCK lines) stays on the website. Plans still open and are scored on every
    alerted timeframe, so B15-ENGINE-FWD and B9-GRAB-FWD record exactly as before."""
    return alert_mode() not in ("all", "quality")


def quality() -> bool:
    """ALERT_MODE (operator, 2026-11-06: "quality rather than the quantity"): quality (default) sends only engine
    signals with their follow-ups, setups with all four B17 confirmations, the trend-change warning, the registered
    tests' checks and the reports; liquidity, structure and H-setup lines and unconfirmed setups stay on the website.
    Since B18 (operator, 2026-11-06: "confirm movement of market at every 4 h candle") the 4h candle breakouts with all
    four confirmations reach the phone too; the operator then asked (2026-11-06, "Yes please") for the 15m setups with all
    four confirmations back on the phone beside them. Unconfirmed setups stay on the website and in the records.
    all = every alert as before. sixty (the default) narrows quality further: see sixty()."""
    return alert_mode() != "all"


def setups_on() -> bool:
    return os.environ.get("ALERT_SETUPS", "1").strip() != "0"


def setups_major() -> bool:
    """SETUP_LEVELS=major keeps only the previous day / week / month levels (about 1-2 alerts a day instead of ~18)."""
    return os.environ.get("SETUP_LEVELS", "all").strip().lower() == "major"


def setup_scan(payloads: dict, since: int | None, seen: dict) -> list[dict]:
    """The registered rules on the site's 15m bars closed after since; levels and zones from the 15m, 1h and 4h
    payloads (the engine's order blocks and volume profile on GC futures volume)."""
    p = payloads.get("15m")
    if not p or (p.get("meta") or {}).get("synthetic"):
        return []
    ch = p.get("chart") or {}
    t, h, lo_, c = ch.get("t") or [], ch.get("h") or [], ch.get("l") or [], ch.get("c") or []
    n = min(len(t), len(h), len(lo_), len(c))
    if n < 2:
        return []
    t, h, lo_, c = t[:n], h[:n], lo_[:n], c[:n]
    lv = setup_levels(t, h, lo_, (payloads.get("1h") or {}).get("chart"), (payloads.get("4h") or {}).get("chart"))
    for k in ("pdh", "pdl", "pwh", "pwl"):
        lv[k.upper()] = (ch.get(k) or [None] * n)[:n]
    if setups_major():
        lv = {k: (v if k in SETUP_MAJOR else [None] * n) for k, v in lv.items()}
    z = {k: (ch.get(k) or [None] * n)[:n] for k in SETUP_ZKEYS}
    rows = [i for i in range(n) if since is None or t[i] > since]
    ev = setup_events(t, h, lo_, c, lv, z, rows, seen)
    if ev:
        votes = trend_votes(t, (payloads.get("1h") or {}).get("chart"), (payloads.get("4h") or {}).get("chart"))
        bull, bear = (ch.get("bull") or [None] * n)[:n], (ch.get("bear") or [None] * n)[:n]
        for e in ev:
            e["checks"] = setup_checks(e, votes, bull, bear)
            e["confirmed"] = all(e["checks"].values())
    return ev


H4_HIST = (0.458, 319, 0.462, "not an edge")   # B18 development 2020-22: +$15 before -$13, n, random, verdict


def h4_scan(payloads: dict, since: int | None) -> list[dict]:
    """B18 on the site's 4h candles closed after since (levels from the 4h payload, PMH / PML and trend from the 1h)."""
    p = payloads.get("4h")
    if not p or (p.get("meta") or {}).get("synthetic"):
        return []
    ch = p.get("chart") or {}
    t, h, lo_, c = ch.get("t") or [], ch.get("h") or [], ch.get("l") or [], ch.get("c") or []
    n = min(len(t), len(h), len(lo_), len(c))
    if n < 2:
        return []
    t, h, lo_, c = t[:n], h[:n], lo_[:n], c[:n]
    h1 = (payloads.get("1h") or {}).get("chart")
    lv = setup_levels(t, h, lo_, h1, {"t": t, "h": h, "l": lo_})
    for k in ("pdh", "pdl", "pwh", "pwl"):
        lv[k.upper()] = (ch.get(k) or [None] * n)[:n]
    votes = trend_votes([x + 14400 for x in t], h1, {"t": t, "c": c})
    rows = [i for i in range(n) if since is None or t[i] > since]
    return h4_events(t, h, lo_, c, (ch.get("bull") or [None] * n)[:n], (ch.get("bear") or [None] * n)[:n], lv, votes, rows)


def h4_lines(e: dict, sid: int, pl: dict | None, now: dict | None, off: float, live: dict) -> list[str]:
    d, side = e["dir"], "BUY" if e["dir"] == 1 else "SELL"
    x = e["close"]
    lot = pl["lot"] if pl else 0.5
    oz = lot * 100.0
    prev = e["prev_high"] if d == 1 else e["prev_low"]
    beyond = " + ".join(f"{SETUP_NAMES[nm]} {_fmt(v, off)}" for nm, v in e["beyond"]) or "no day / week / month level"
    head = (f"XAUUSD 4h CANDLE BREAKOUT #{sid} {side} (your rule) -- the 4h candle closed {'above' if d == 1 else 'below'} the "
            f"previous 4h {'high' if d == 1 else 'low'} {_fmt(prev, off)} at {_fmt(x, off)} | beyond {beyond} | "
            f"candle closed {clocks(e['t_close'])}")
    out = [head]
    tm = alert_timing({"t": e["t"], "px": x, "dir": d, "sl": x - d * SETUP_SL_PX}, "4h", now, {"sl_px": SETUP_SL_PX})
    late, timing = timing_lines(tm, off)
    if late:
        out.append(late)
    ck = e["checks"]
    out.append("CONFIRMATIONS: " + " | ".join(f"{nm} {'YES' if ck.get(k) else 'no'}" for k, nm in (
        ("major", "beyond a day/week/month level"), ("trend", "trend 3 of 3"), ("bias", "engine bias"), ("session", "London/NY")))
        + (" -> ALL 4" if e["confirmed"] else ""))
    out.append(f"ENTRY {_fmt(x, off)} | SL {_fmt(x - d * SETUP_SL_PX, off)} (-${SETUP_SL_PX * oz:,.0f}) | TP1 {_fmt(x + d * 13, off)} "
               f"(close half, SL to entry) | +$15 at {_fmt(x + d * SETUP_TP_PX, off)} | TP2 {_fmt(x + d * 20, off)} | at {lot:g} lot")
    if pl:
        out.append(mt5_line(d, pl))
    g = live.get("4H CONFIRMED") or [0, 0]
    out.append(f"3-year record of this rule with all 4 (B18), 2020-22: +$15 before -$13 {H4_HIST[0]:.0%} of {H4_HIST[1]:,} "
               f"(random {H4_HIST[2]:.0%}): {H4_HIST[3]}" + (f" | live so far {g[1]}/{g[0]}" if g[0] else "")
               + " | information, not a confirmed signal")
    if timing:
        out.append(timing)
    return out


def setup_lines(e: dict, sid: int, pl: dict | None, now: dict | None, off: float, live: dict) -> list[str]:
    d, side = e["dir"], "BUY" if e["dir"] == 1 else "SELL"
    lv = " + ".join(f"{SETUP_NAMES[nm]} {_fmt(x, off)}" for nm, x in e["levels"])
    t_close = e["t"] + 900
    if e["kind"] == "SWEEP":
        what = (f"liquidity sweep: {lv} swept ({'low' if d == 1 else 'high'} {_fmt(e['low'] if d == 1 else e['high'], off)}), "
                f"closed back {'above' if d == 1 else 'below'} at {_fmt(e['close'], off)}")
    else:
        what = f"breakout: closed {'above' if d == 1 else 'below'} {lv} at {_fmt(e['close'], off)}"
    x = e["close"]
    lot = pl["lot"] if pl else 0.5
    oz = lot * 100.0
    out = [f"XAUUSD 15m SETUP #{sid} {side} (your rules) -- {what} | at {', '.join(e['zones'])} | bar closed {clocks(t_close)}"]
    tm = alert_timing({"t": e["t"], "px": x, "dir": d, "sl": x - d * SETUP_SL_PX}, "15m", now, {"sl_px": SETUP_SL_PX})
    late, timing = timing_lines(tm, off)
    if late:
        out.append(late)
    out.append(f"ENTRY {_fmt(x, off)} | SL {_fmt(x - d * SETUP_SL_PX, off)} (-${SETUP_SL_PX * oz:,.0f}) | TP1 {_fmt(x + d * 13, off)} "
               f"(close half, SL to entry) | +$15 at {_fmt(x + d * SETUP_TP_PX, off)} | TP2 {_fmt(x + d * 20, off)} | at {lot:g} lot")
    if pl:
        out.append(mt5_line(d, pl))
    ck = e.get("checks") or {}
    if ck:
        out.append("CONFIRMATIONS: " + " | ".join(f"{nm} {'YES' if ck.get(k) else 'no'}" for k, nm in (
            ("major", "day/week/month level"), ("trend", "trend 3 of 3"), ("bias", "engine bias"), ("session", "London/NY")))
            + (" -> ALL 4" if e.get("confirmed") else ""))
    hist = SETUP_HIST_CONFIRMED if e.get("confirmed") and SETUP_HIST_CONFIRMED else SETUP_HIST.get(e["kind"])
    which = "with all 4 confirmations (B17)" if e.get("confirmed") and SETUP_HIST_CONFIRMED else "(B16)"
    rec = (f"3-year record of this rule {which}, 2020-22: +$15 before -$13 {hist[0]:.0%} of {hist[1]:,} (random {hist[2]:.0%}): "
           f"{hist[3]}" if hist else "3-year record: being measured")
    lv_ = live.get(e["kind"]) or [0, 0]
    out.append(rec + (f" | live so far {lv_[1]}/{lv_[0]} reached +$15 first" if lv_[0] else "") +
               " | information, not a confirmed signal")
    if timing:
        out.append(timing)
    return out


def setup_track(setups: list[dict], chart: dict, p5: dict | None, now_t: int, off: float) -> tuple[list[str], list[dict], list[dict]]:
    """Each open setup's result: +$15 before -$13 on the same feed's 5m path (else the 15m bars); one line when it is
    decided; no result within a trading day = EXPIRED (not counted)."""
    lines, keep, closed = [], [], []
    for s in setups:
        p5path = plan_path5(s, p5)
        path = p5path or plan_path(s, chart)
        side = "BUY" if s["dir"] == 1 else "SELL"
        what = "4h CANDLE BREAKOUT" if s.get("kind") == "4H BREAKOUT" else "15m SETUP"   # the alert's own label
        head = f"XAUUSD {what} #{s['id']} {side} from {_fmt(s['entry'], off)}"
        if path["result"] is None:
            traded = path["bars"] * (300 if p5path else 900)      # trading time covered by bars, so a weekend does not count
            if traded >= SETUP_TRACK_SEC or now_t - s["t_dec"] > SETUP_STALE_SEC:
                closed.append({**s, **path, "result": "EXPIRED", "t_res": now_t})
                lines.append(f"{head}: neither +$15 nor -$13 within a trading day (not counted)")
            else:
                keep.append(s)
            continue
        closed.append({**s, **path})
        lines.append(f"{head}: " + {"TP": f"+$15 reached first ({_fmt(s['tp'], off)})", "SL": f"SL -$13 first ({_fmt(s['sl'], off)})",
                                     "BOTH": "+$15 and -$13 inside one bar (counted as SL)"}[path["result"]])
    return lines, keep, closed


def setup_record(store_dir: str | None, log: list[dict], now_t: int) -> dict:
    """The live record of every alerted setup (descriptive; the registered test is B16 on history). Saved to
    <store>/research_forward/ so the workflow copies it to forward-ledger."""
    path = os.path.join(store_dir, GRAB_DIR, SETUP_FILE) if store_dir else None
    started = now_t
    if path and os.path.exists(path):
        with open(path) as f:
            started = int(json.load(f).get("started_utc") or now_t)
    live: dict = {}
    for r in log:
        if r.get("result") in ("TP", "SL", "BOTH"):
            ck = "4H CONFIRMED" if r["kind"] == "4H BREAKOUT" else "CONFIRMED"
            for key in (r["kind"], ck) if r.get("confirmed") else (r["kind"],):
                g = live.setdefault(key, [0, 0])
                g[0] += 1
                g[1] += r["result"] == "TP"
    rec = {"rules": "research/registrations/B16.json", "started_utc": started, "setups": log, "live": live}
    if path:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(rec, f, indent=1)
    return rec


# ---------------- B15-ENGINE-FWD: the registered live test of the engine's own signal alerts ----------------
ENG_ID, ENG_FILE = "B15-ENGINE-FWD", "B15-ENGINE-FWD.json"   # in <store>/research_forward/, copied to forward-ledger
ENG_LOOKS = (30, 40, 50, 60, 70, 80, 90, 100)
ENG_PX = 13.0                            # TP1 and SL in price $ (registered)
ENG_BE = (13.0 + 0.26) / 26.0            # 51.0%
ENG_DEADLINE = "2027-06-30"


def eng_trades(vlog: list[dict], started: int) -> tuple[list[dict], int]:
    """The test's trades: closed alert plans whose signal closed at / after the start, with TP1 and SL $13 of price.
    TP1 first = TP; SL or both-in-one-bar = SL; no result in 3 days = EXPIRED (not counted). Returns (trades, excluded)."""
    out, excluded = [], 0
    for r in vlog:
        if _decision_t(r) < started or r.get("result") not in ("TP", "SL", "BOTH", "EXPIRED"):
            continue
        if abs(abs(r["tp"] - r["entry"]) - ENG_PX) > 0.011 or abs(abs(r["entry"] - r["sl"]) - ENG_PX) > 0.011:
            excluded += 1
            continue
        out.append({"id": r.get("id"), "tf": r["tf"], "dir": r["dir"], "entry": r["entry"], "t_dec": _decision_t(r),
                    "status": "TP" if r["result"] == "TP" else "EXPIRED" if r["result"] == "EXPIRED" else "SL",
                    "result": r["result"], "t_res": int(r.get("t_res") or 0), "tp2_result": r.get("tp2_result"),
                    "path": r.get("path"), "late": r.get("late"), "move_alert": r.get("move_alert"),
                    "session": r.get("session") or session_of(_decision_t(r))})
    return out, excluded


def eng_verdict(trades: list[dict], book: dict, now_t: int) -> dict:
    """The registered rule (that of B9-GRAB-FWD): checks only at 30, 40 ... 100 decided results in the order they
    resolved; PROVEN when the Wilson 95% lower bound is above 51.0% at a check; NOT PROVEN at 100 or after the
    deadline. A verdict is final."""
    dec = sorted((x for x in trades if x["status"] in ("TP", "SL")), key=lambda x: (x["t_res"], x["t_dec"]))
    checks = list(book.get("checks") or [])
    verdict = book.get("verdict")
    if verdict is None:
        for look in ENG_LOOKS:
            if len(dec) < look or any(ch["n"] == look for ch in checks):
                continue
            k = sum(x["status"] == "TP" for x in dec[:look])
            lo, hi = _wilson(k, look)
            checks.append({"n": look, "tp": k, "wilson": [lo, hi], "utc": now_t, "proven": lo > ENG_BE})
            if lo > ENG_BE:
                verdict = {"verdict": "PROVEN", "at_n": look, "utc": now_t}
                break
        if verdict is None and (len(dec) >= ENG_LOOKS[-1] or
                                datetime.fromtimestamp(now_t, timezone.utc).date() > date.fromisoformat(ENG_DEADLINE)):
            verdict = {"verdict": "NOT PROVEN", "at_n": len(dec), "utc": now_t}
    n, k = len(dec), sum(x["status"] == "TP" for x in dec)
    lo, hi = _wilson(k, n)
    nxt = next((x for x in ENG_LOOKS if x > n), None)
    status = (f"{verdict['verdict']} at {verdict['at_n']} results" if verdict else
              f"COLLECTING: {n} results, {k / n:.0%} TP1 first; {'first' if n < ENG_LOOKS[0] else 'next'} check at {nxt}" if n else
              f"COLLECTING: no result yet; first check at {ENG_LOOKS[0]}")
    return {"checks": checks, "verdict": verdict, "n": n, "tp": k, "sl": n - k, "rate": k / n if n else None,
            "wilson": [lo, hi] if n else None, "next_check": None if verdict else nxt, "status": status}


def eng_run(store_dir: str | None, vlog: list[dict], plans: list[dict], now_t: int) -> tuple[list[str], dict]:
    """Every run: rebuild the test's trades from the plan log, apply the rule, save the record (every trade and every
    check) to <store>/research_forward/, and return a phone line for each new check and for the verdict."""
    path = os.path.join(store_dir, GRAB_DIR, ENG_FILE) if store_dir else None
    book: dict = {}
    if path and os.path.exists(path):
        with open(path) as f:
            book = json.load(f)
    started = int(book.get("started_utc") or now_t)
    trades, excluded = eng_trades(vlog, started)
    v = eng_verdict(trades, book, now_t)
    old = {c["n"] for c in book.get("checks") or []}
    lines = []
    for c in v["checks"]:
        if c["n"] not in old:
            lines.append(f"ENGINE TEST ({ENG_ID}) CHECK at {c['n']} results: TP1 first {c['tp']}/{c['n']} = {c['tp'] / c['n']:.0%} "
                         f"(95% {c['wilson'][0]:.0%}-{c['wilson'][1]:.0%}; break-even {ENG_BE:.0%}) -> "
                         + ("PROVEN" if c["proven"] else "not proven yet"))
    if v["verdict"] and not book.get("verdict"):
        lines.append(f"ENGINE TEST ({ENG_ID}): {v['verdict']['verdict']} at {v['verdict']['at_n']} results. "
                     + ("The engine's signal alerts beat break-even on new data; an average, not a guarantee for one trade."
                        if v["verdict"]["verdict"] == "PROVEN" else "Not confirmed: treat the engine's alerts as unproven."))
    rec = {"id": ENG_ID, "registration": "research/registrations/B15-ENGINE-FWD.json", "started_utc": started,
           "trades": trades, "excluded": excluded, "checks": v["checks"], "verdict": v["verdict"]}
    if path:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(rec, f, indent=1)
    by_tf: dict = {}
    for x in trades:
        if x["status"] in ("TP", "SL"):
            g = by_tf.setdefault(x["tf"], [0, 0])
            g[0] += 1
            g[1] += x["status"] == "TP"
    tp1 = [x for x in trades if x["status"] == "TP" and x.get("tp2_result")]
    block = {"id": ENG_ID, "started_utc": started, "break_even": ENG_BE, "looks": list(ENG_LOOKS), "deadline": ENG_DEADLINE,
             **{k: v[k] for k in ("n", "tp", "sl", "rate", "wilson", "status", "next_check", "verdict", "checks")},
             "open": sum(1 for p in plans if _decision_t(p) >= started), "excluded": excluded,
             "expired": sum(1 for x in trades if x["status"] == "EXPIRED"),
             "by_tf": {k: {"n": a, "tp": b} for k, (a, b) in sorted(by_tf.items())},
             "tp2": {"of_tp1": len(tp1), "hit": sum(1 for x in tp1 if x["tp2_result"] == "TP2")},
             "recent": trades[::-1][:10]}
    return lines, block


def grab_lines_new(tr: dict, now: dict | None, off: float = 0.0) -> list[str]:
    side, d = ("BUY", 1) if tr["dir"] == 1 else ("SELL", -1)
    back = "above" if d == 1 else "below"
    pools = " + ".join(f"{nm} {_fmt(px, off)}" for nm, px in zip(tr["pools"], tr["levels"]))
    s1, s2 = ("-", "+") if d == 1 else ("+", "-")
    late, timing = timing_lines(alert_timing({"t": tr["t"], "px": tr["entry"], "dir": d, "sl": tr["sl"]}, tr["tf"], now,
                                             {"sl_px": GRAB_SL}), off)
    out = [f"XAUUSD {tr['tf']} GRAB FORWARD TEST #{tr['id']}: {side} after {pools} swept, closed back {back} at {_fmt(tr['entry'], off)}"]
    if late:
        out.append(late)
    out.append(f"TEST TRADE: entry {_fmt(tr['entry'], off)} TP {_fmt(tr['tp'], off)} (+$650) SL {_fmt(tr['sl'], off)} (-$650) | "
               f"ON MT5: {side} at market, then SL = your fill {s1} {GRAB_SL:.2f}, TP = your fill {s2} {GRAB_TP:.2f}")
    if timing:
        out.append(timing)
    return out


def grab_line_done(tr: dict, status: str, off: float = 0.0) -> str:
    side = "BUY" if tr["dir"] == 1 else "SELL"
    head = f"XAUUSD GRAB TEST #{tr['id']} {side} from {_fmt(tr['entry'], off)}"
    when = datetime.fromtimestamp(tr["t_res"], timezone.utc).strftime("%d %b %H:%M UTC") + f" = {mt5_clock(tr['t_res']):%H:%M} MT5"
    what = {"TP": f"TP {_fmt(tr['tp'], off)} HIT +$650 ({when} 5m bar)", "SL": f"SL {_fmt(tr['sl'], off)} HIT -$650 ({when} 5m bar)",
            "NONE": "no TP or SL within one trading day (not counted)", "GAP": "price data missing for its path (not counted)"}
    return f"{head}: {what[tr['status']]} | test {status}"


def grab_run(store_dir: str | None, state: dict, payloads: dict, t_send: int, off: float = 0.0) -> tuple[list[str], dict]:
    """One run of B9-GRAB-FWD: resolve open test trades, open new ones, check the verdict. Returns the alert lines and
    the website block. The record (every trade and every check) is kept in <store>/research_forward/."""
    g = state.setdefault("grab", {})
    path = os.path.join(store_dir, GRAB_DIR, GRAB_FILE) if store_dir else None
    book = {"id": GRAB_ID, "trades": [], "checks": [], "verdict": None}
    if path and os.path.exists(path):
        with open(path) as f:
            book = json.load(f)
    if g.get("started_utc") is None:                        # the first run with this code: start, replay nothing
        g["started_utc"] = book.get("started_utc") or t_send
    book["started_utc"] = g["started_utc"]
    pos, seen, trades = g.setdefault("pos", {}), g.setdefault("seen", {}), book["trades"]
    p5 = payloads.get("5m")
    lines, done = [], []
    for i, tr in enumerate(trades):                         # results first
        if tr["status"] == "OPEN":
            trades[i] = grab_resolve(tr, p5, t_send)
            if trades[i]["status"] != "OPEN":
                done.append(trades[i])
    new, fzs = [], {}
    for tf in GRAB_TFS:                                     # then new test trades, 15m before 30m before 1h before 4h
        p = payloads.get(tf)
        if not p or p["meta"].get("synthetic") or not (p.get("chart") or {}).get("t"):
            continue
        last_t = p["chart"]["t"][-1]
        same5 = p5 if p5 is not None and (p5.get("meta") or {}).get("price_source") == p["meta"].get("price_source") else None
        if tf in pos:
            for tr in grab_new(p, pos[tf], g["started_utc"], seen):
                tr["id"] = len(trades) + 1
                pn = price_now(payloads, tf)
                tr["alert"] = {"t": t_send, **({"px": pn["px"], "t_px": pn["t"], "live": pn["live"]} if pn else {})}
                trades.append(tr)
                new.append(tr)
                fzs[tr["id"]] = freshness(int(tr["t"]) + TF_SEC.get(tf, 0), tr["dir"], tr["entry"], GRAB_SL, GRAB_TP,
                                          tr["alert"], [p, same5])   # stale-signal protection; the record is untouched
                if fzs[tr["id"]]["state"] != "FRESH":
                    gate_note(state, f"grab:{tr['id']}", fzs[tr["id"]])
        pos[tf] = last_t
    sm = grab_verdict(trades, book, t_send)
    book["checks"], book["verdict"] = sm["checks"], sm["verdict"]
    quiet = gate_quiet(state, "grab")
    for tr in done:
        ln = grab_line_done(tr, sm["status"], off)
        lines.append(RECORD_ONLY + ln if tr.get("id") in quiet else ln)
    stale_g = []
    for tr in new:
        fz = fzs.get(tr["id"]) or {"state": "FRESH"}
        nl = grab_lines_new(tr, tr["alert"], off)
        if fz["state"] == "NOT ACTIONABLE":
            stale_g.append(stale_item("BUY" if tr["dir"] == 1 else "SELL", f"{tr['tf']} GRAB TEST #{tr['id']}",
                                      int(tr["t"]) + TF_SEC.get(tr["tf"], 0), tr["entry"], fz, off))
            lines += [RECORD_ONLY + x for x in nl]
            continue
        lines += nl[:1] + ([delayed_line(fz, off)] if fz["state"] == "DELAYED" else []) + nl[1:]
    if stale_g:
        lines.append(stale_line("grab test trade" + ("s" if len(stale_g) > 1 else ""), stale_g))
    if new:
        lines.append(f"Registered test {GRAB_ID}, not a proven signal: {sm['status']} (break-even {GRAB_BE:.0%})")
    keep_from = trading_day(t_send - 3 * 86400)
    g["seen"] = {k: v for k, v in seen.items() if v >= keep_from}
    if path:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(book, f, indent=1)
    by = {}
    for dim, fn in (("timeframe", lambda x: x["tf"]), ("side", lambda x: "BUY" if x["dir"] == 1 else "SELL"),
                    ("pool", lambda x: {"D": "day", "W": "week", "M": "month"}.get(x["pools"][0][1:2], "?") if x["pools"] else "?")):
        grp: dict = {}
        for x in trades:
            if x["status"] in ("TP", "SL"):
                a = grp.setdefault(fn(x), [0, 0])
                a[0] += 1
                a[1] += x["status"] == "TP"
        by[dim] = {k: {"n": v[0], "tp": v[1], "rate": v[1] / v[0]} for k, v in sorted(grp.items())}
    counts = {s: sum(x["status"] == s for x in trades) for s in ("OPEN", "TP", "SL", "NONE", "GAP")}
    block = {"id": GRAB_ID, "started_utc": g["started_utc"], "tp_px": GRAB_TP, "sl_px": GRAB_SL, "break_even": GRAB_BE,
             "looks": list(GRAB_LOOKS), "deadline": GRAB_DEADLINE, "counts": counts, **sm, "by": by,
             "open": [x for x in trades if x["status"] == "OPEN"][-20:],
             "recent": [x for x in trades if x["status"] != "OPEN"][::-1][:15]}
    return lines, block


PLAN_TP2_DEFAULT_PX = 20.0            # TP2 in price $ (the operator's choice, 2026-11-06): $1,000 at 0.5 lot


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
    raw = os.environ.get("PLAN_TP2_USD", "").strip()
    try:
        tp2 = float(raw) if raw else PLAN_TP2_DEFAULT_PX * oz
    except ValueError:
        tp2 = PLAN_TP2_DEFAULT_PX * oz
    tp2 = tp2 if tp2 > tp else 0.0                      # 0 (or not beyond TP1): one TP
    return {"lot": lot, "sl_usd": sl, "tp_usd": tp, "cost_usd": cpl * lot, "sl_px": sl / oz, "tp_px": tp / oz,
            "tp2_usd": tp2, "tp2_px": tp2 / oz if tp2 else None}


def plan_levels(entry: float, d: int, pl: dict) -> tuple[float, float]:
    """(SL, TP) prices of the plan for a signal at `entry` in direction d (+1 BUY, -1 SELL)."""
    return entry - d * pl["sl_px"], entry + d * pl["tp_px"]


def plan_line(entry: float, d: int, pl: dict, off: float = 0.0) -> str:
    sl, tp = plan_levels(entry, d, pl)
    first = pl["sl_px"] / (pl["sl_px"] + pl["tp_px"])
    be = (pl["sl_usd"] + pl["cost_usd"]) / (pl["sl_usd"] + pl["tp_usd"])
    if pl.get("tp2_px"):
        tp2, p2 = entry + d * pl["tp2_px"], pl["tp_px"] / pl["tp2_px"]
        return (f"YOUR PLAN {pl['lot']:g} lot: SL {_fmt(sl, off)} (-${pl['sl_usd']:,.0f}) | TP1 {_fmt(tp, off)}: close half "
                f"(+${pl['tp_usd'] / 2:,.0f}), move SL to entry | TP2 {_fmt(tp2, off)}: the rest (+${pl['tp2_usd'] / 2:,.0f}) | "
                f"odds with no edge: SL {1 - first:.0%} · TP1 then entry {first * (1 - p2):.0%} · TP2 {first * p2:.0%} "
                f"(no signal beats these) | break-even {be:.0%} TP1 first")
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


def plan_path5(plan: dict, p5: dict | None) -> dict | None:
    """The plan's path on the 5-minute bars opening at / after its signal's close, with the trade_race tie rule (a bar
    touching both levels is a loss, 'BOTH', unless it opened beyond the TP). None when the 5m bars do not cover that
    close (the caller then uses the signal's own timeframe)."""
    if not p5 or (p5.get("meta") or {}).get("synthetic"):
        return None
    ch = p5.get("chart") or {}
    t, o, h, lo_ = ch.get("t") or [], ch.get("o") or [], ch.get("h") or [], ch.get("l") or []
    t_dec = _decision_t(plan)
    if not t or t[0] > t_dec:
        return None
    d, sl, tp, e = plan["dir"], plan["sl"], plan["tp"], plan["entry"]
    mfe = mae = 0.0
    bars = 0
    for k in range(len(t)):
        if t[k] < t_dec or h[k] is None or lo_[k] is None:
            continue
        bars += 1
        mfe = max(mfe, (h[k] - e) if d == 1 else (e - lo_[k]))
        mae = max(mae, (e - lo_[k]) if d == 1 else (h[k] - e))
        hit_tp = h[k] >= tp if d == 1 else lo_[k] <= tp
        hit_sl = lo_[k] <= sl if d == 1 else h[k] >= sl
        if hit_tp and hit_sl:
            beyond = o[k] is not None and (o[k] - tp) * d >= 0
            what = "TP" if beyond else "BOTH"
        else:
            what = "TP" if hit_tp else "SL" if hit_sl else None
        if what:
            return {"result": what, "t_res": t[k], "mfe": mfe, "mae": mae, "bars": bars, "path": "5m"}
    return {"result": None, "t_res": None, "mfe": mfe, "mae": mae, "bars": bars, "path": "5m"}


def plan_stage2(plan: dict, chart: dict, t_from: int) -> dict:
    """After TP1 (on the bar opening at t_from): the rest's TP2 against the SL moved to the entry, on the bars opening
    after that bar. A bar touching both counts as break-even (BE) unless it opened beyond TP2."""
    t, h, lo_ = chart.get("t") or [], chart.get("h") or [], chart.get("l") or []
    o = chart.get("o") or [None] * len(t)
    d, e, tp2 = plan["dir"], plan["entry"], plan["tp2"]
    for k in range(len(t)):
        if t[k] <= t_from or h[k] is None or lo_[k] is None:
            continue
        hit2 = h[k] >= tp2 if d == 1 else lo_[k] <= tp2
        hit_be = lo_[k] <= e if d == 1 else h[k] >= e
        if hit2 and hit_be:
            return {"result": "TP2" if (o[k] is not None and (o[k] - tp2) * d >= 0) else "BE", "t_res": t[k]}
        if hit2 or hit_be:
            return {"result": "TP2" if hit2 else "BE", "t_res": t[k]}
    return {"result": None, "t_res": None}


def plan_result(plan: dict, chart: dict) -> tuple[str, int] | None:
    """('TP' | 'SL' | 'BOTH', bar open t) for the first bar AFTER the signal bar that touches the plan's TP or SL."""
    r = plan_path(plan, chart)
    return (r["result"], r["t_res"]) if r["result"] else None


def plan_updates(plans: list[dict], tf: str, chart: dict, now_t: int, off: float = 0.0,
                 p5: dict | None = None, quiet: set | None = None) -> tuple[list[str], list[dict], list[dict]]:
    """Follow-up alerts for this timeframe's open plans, the plans still open afterwards, and the ones that closed.
    p5: the same feed's 5m payload; plans are resolved on it when it covers their signal's close. quiet: ids of plans
    whose alert was NOT ACTIONABLE (stale-signal protection): their lines start with RECORD_ONLY (website only)."""
    lines, keep, closed = [], [], []
    for pl in plans:
        if pl["tf"] != tf:
            keep.append(pl)
            continue
        side = "BUY" if pl["dir"] == 1 else "SELL"
        head = f"XAUUSD {tf} YOUR PLAN {side} from {_fmt(pl['entry'], off)}"
        if quiet and pl.get("id") in quiet:
            head = RECORD_ONLY + head
        path = plan_path5(pl, p5) or plan_path(pl, chart)
        if path["result"] is None:
            if now_t - pl["t"] > PLAN_TRACK_SEC:
                lines.append(f"{head}: no TP or SL after 3 days on the site's prices -- check the trade in MT5 (tracking stopped)")
                closed.append({**pl, **path, "result": "EXPIRED", "t_res": now_t})
            else:
                keep.append(pl)
            continue
        what, bt = path["result"], path["t_res"]

        def clock(x, path=path):
            return (datetime.fromtimestamp(x, timezone.utc).strftime("%d %b %H:%M UTC") + f" = {mt5_clock(x):%H:%M} MT5"
                    + (" 5m" if path.get("path") == "5m" else ""))
        hhmm = clock(bt)
        to_tp, to_sl = abs(pl["tp"] - pl["entry"]), abs(pl["entry"] - pl["sl"])
        two = what == "TP" and pl.get("tp2") is not None
        if two:                                            # TP1 hit: half closed, the rest runs to TP2 or the entry
            if not pl.get("tp1_sent"):
                s = (f"{head}: TP1 {_fmt(pl['tp'], off)} HIT +${pl['tp_usd'] / 2:,.0f} on half -- close half, move the other "
                     f"half's SL to your fill (break-even); it runs to TP2 {_fmt(pl['tp2'], off)} (+${pl['tp2_usd'] / 2:,.0f}) "
                     f"({hhmm} bar)")
                if path["mfe"] - to_tp < FEED_MARGIN:
                    s += f" | only ${path['mfe'] - to_tp:.2f} past TP1 on the site's prices: confirm in MT5 (broker prices differ)"
                lines.append(s)
                pl = {**pl, "tp1_sent": True, "t_tp1": bt}
            ch2 = (p5 or {}).get("chart") if path.get("path") == "5m" else chart
            s2 = plan_stage2(pl, ch2 or {}, bt)
            banked = pl["tp_usd"] / 2
            if s2["result"] is None:
                if now_t - pl["t"] > PLAN_TRACK_SEC:
                    lines.append(f"{head}: no TP2 or break-even after 3 days on the site's prices -- check MT5 (tracking "
                                 f"stopped); +${banked:,.0f} banked at TP1")
                    closed.append({**pl, **path, "tp2_result": "EXPIRED", "t_tp2": now_t})
                else:
                    keep.append(pl)
                continue
            if s2["result"] == "TP2":
                lines.append(f"{head}: TP2 {_fmt(pl['tp2'], off)} HIT -- trade closed: +${banked + pl['tp2_usd'] / 2:,.0f} "
                             f"total ({clock(s2['t_res'])} bar)")
            else:
                lines.append(f"{head}: back at entry {_fmt(pl['entry'], off)} after TP1 -- the rest closed at break-even: "
                             f"+${banked:,.0f} total ({clock(s2['t_res'])} bar)")
            closed.append({**pl, **path, "tp2_result": s2["result"], "t_tp2": s2["t_res"]})
            continue
        closed.append({**pl, **path})
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
    def won(r):                                          # two targets: half at TP1, the rest at TP2 or the entry
        if r.get("tp2_result") and r.get("tp2_usd"):
            return r["tp_usd"] / 2 + (r["tp2_usd"] / 2 if r["tp2_result"] == "TP2" else 0.0)
        return r["tp_usd"]
    net = sum((won(r) if r["result"] == "TP" else -r["sl_usd"]) - cost(r) for r in dec)
    oz = [float(r.get("lot") or 0.5) * 100.0 for r in dec]
    stops = [r for r in dec if r["result"] != "TP"]
    wins = [r for r in dec if r["result"] == "TP"]
    near = sum(1 for r in stops if r.get("mfe", 0) >= 0.8 * abs(r["tp"] - r["entry"]))
    close_call = sum(1 for r in wins if r.get("mae", 0) >= 0.8 * abs(r["entry"] - r["sl"]))
    lo, hi = _wilson(tp, n)
    out = {"n": n, "tp": tp, "sl": n - tp, "expired": sum(r.get("result") == "EXPIRED" for r in recs),
           "tp2": sum(1 for r in dec if r.get("tp2_result") == "TP2"), "be_after_tp1": sum(1 for r in dec if r.get("tp2_result") == "BE"),
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


DELIVERY = "alerts_delivery.json"     # every send attempt (no secret, no full text): proof of delivery after ntfy's cache
DELIVERY_MAX = 1000
_DELIVERIES: list[dict] = []


def _post(name: str, text: str, fn) -> tuple[bool, dict]:
    """One channel: a channel counts as sent only on HTTP 2xx (before 2026-11-11 any answer counted)."""
    rec = {"channel": name, "http": None, "id": None}
    try:
        r = fn()
        rec["http"] = getattr(r, "status_code", None)
        if name == "ntfy" and rec["http"] is not None and 200 <= rec["http"] < 300:
            try:
                rec["id"] = (r.json() or {}).get("id")
            except Exception:  # noqa: BLE001  (an id is a nicety; the status decides)
                rec["id"] = None
    except Exception as e:  # noqa: BLE001  (a channel failure must never stop the alerts)
        rec["error"] = type(e).__name__
    return rec["http"] is not None and 200 <= rec["http"] < 300, rec


def send(lines: list[str]) -> list[str]:
    sent = []
    if not lines or requests is None:
        return sent
    text = "\n".join(lines)
    meta = {"t": int(datetime.now(timezone.utc).timestamp()), "sha16": hashlib.sha256(text.encode()).hexdigest()[:16],
            "lines": len(lines), "first": (without_disclaimer(lines) or lines)[0][:80]}
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    chans = []
    if topic:
        chans.append(("ntfy", lambda: requests.post(f"https://ntfy.sh/{topic}", data=text.encode(), timeout=15,
                                                    headers={"Title": "XAUUSD Quantum"})))
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if tok and chat:
        chans.append(("telegram", lambda: requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                                                        json={"chat_id": chat, "text": text}, timeout=15)))
    hook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if hook:
        chans.append(("discord", lambda: requests.post(hook, json={"content": text[:1900]}, timeout=15)))
    for name, fn in chans:
        ok, rec = _post(name, text, fn)
        if ok:
            sent.append(name)
        _DELIVERIES.append({**meta, **rec, "ok": ok})
    return sent


def save_deliveries(store_dir: str | None) -> list[dict]:
    """Append this run's send attempts to <store>/alerts_delivery.json (bounded) and clear the buffer."""
    got = list(_DELIVERIES)
    _DELIVERIES.clear()
    if not store_dir or not got:
        return got
    path = os.path.join(store_dir, DELIVERY)
    old = []
    if os.path.exists(path):
        try:
            with open(path) as f:
                old = json.load(f)
        except (OSError, ValueError):
            old = []
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump((old + got)[-DELIVERY_MAX:], f, indent=0)
    os.replace(tmp, path)
    return got


GATE_NAMES = {"Trend": "trend", "HTF": "higher-timeframe gate", "Sess": "session", "Trig": "no trigger", "Recent": "old bar",
              "News": "news", "DD": "drawdown", "all passed": "all gates passed (vetoed or already in a trade)",
              "?": "reason unclear"}   # '?': the engine's log for that bar could not be split into BUY / SELL reasons


def h_records(store_dir: str | None, tf: str) -> dict:
    """Each H-setup's forward record on this timeframe (store/holdout/<tf>_<arm>.json): trades, winners, net points."""
    out = {}
    for arm in ("h2", "h3", "h4", "h5", "h6"):
        path = os.path.join(store_dir, "holdout", f"{tf}_{arm}.json") if store_dir else None
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                tr = json.load(f)
        except (OSError, ValueError):
            continue
        pts = [float(x.get("pts") or 0.0) for x in tr if isinstance(x, dict)]
        out[arm] = {"n": len(pts), "won": sum(1 for x in pts if x > 0), "pts": round(sum(pts), 1)}
    return out


def gate_tally(state: dict, payload: dict, tf: str) -> None:
    """Count, once per closed bar, the first entry gate that blocked each side (the dashboard's gate_sides, rebuilt
    from the engine's own log), per trading day and timeframe; kept for six days."""
    lb = (payload.get("meta") or {}).get("last_bar_open")
    if not lb:
        return
    seen = state.setdefault("gates_seen", {})
    if seen.get(tf) == lb:
        return
    seen[tf] = lb
    t = int(datetime.fromisoformat(lb).timestamp())
    gs = (payload.get("dashboard") or {}).get("gate_sides")
    g = state.setdefault("gates", {}).setdefault(trading_day(t), {}).setdefault(tf, {"bars": 0, "signals": 0, "long": {}, "short": {}})
    g["bars"] += 1
    for side in ("long", "short"):
        f = (gs or {}).get(side)
        key = "?" if not gs else (f[0] if f else "all passed")
        g[side][key] = g[side].get(key, 0) + 1
    keep = trading_day(t - 6 * 86400)
    state["gates"] = {d: v for d, v in state["gates"].items() if d >= keep}


def engine_line(state: dict, day: str, tfs: list[str], last: dict | None) -> str | None:
    """The day's engine status for the daily report: signals per timeframe and what blocked each side most often."""
    g = (state.get("gates") or {}).get(day) or {}
    parts = []
    for tf in tfs:
        x = g.get(tf)
        if not x or not x["bars"]:
            continue

        def top(side, x=x):
            items = sorted(x[side].items(), key=lambda kv: -kv[1])[:2]
            return ", ".join(f"{GATE_NAMES.get(k, k)} {100 * v / x['bars']:.0f}%" for k, v in items)
        parts.append(f"{tf} {x['signals']} signal{'' if x['signals'] == 1 else 's'} in {x['bars']} bars "
                     f"(BUY blocked by {top('long')}; SELL by {top('short')})")
    if not parts:
        return None
    ls = (f"last signal {last['tf']} {'BUY' if last['dir'] == 1 else 'SELL'} "
          f"{datetime.fromtimestamp(int(last['t_dec']), timezone.utc):%a %d %b %H:%M} UTC" if last else "no signal recorded yet")
    return (f"XAUUSD ENGINE {date.fromisoformat(day):%a %d %b}: " + " | ".join(parts) + f" | {ls} | "
            "no signal = no trade by the engine's rules (by design, not a fault)")


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
        gate_tally(state, p, tf)
        pn = price_now(payloads, tf)
        now = {"t": t_send, **({"px": pn["px"], "t_px": pn["t"], "live": pn["live"]} if pn else {})}
        ev = liquidity_events(p, since, seen) if liq_on() else []   # liquidity grabs / breaks on this timeframe's new bars
        liq_log += ev
        upd, repeats = [], {}
        p5g = payloads.get("5m")
        p5g = p5g if p5g is not None and (p5g.get("meta") or {}).get("price_source") == p["meta"].get("price_source") else None
        fresh = {}                                         # stale-signal protection: each new signal, before it is shown
        for m in p["markers"]:                             # priced or not: an unpriced one is never DELAYED
            if m["type"] == "SIGNAL" and m["t"] > since:
                px_m = m.get("px")
                slp = (pl_cfg["sl_px"] if pl_cfg else abs(px_m - m["sl"]) if px_m is not None and m.get("sl") is not None
                       else ENG_PX)
                tpp = (pl_cfg["tp_px"] if pl_cfg else abs(m["tp1"] - px_m) if px_m is not None and m.get("tp1") is not None
                       else ENG_PX)
                fresh[m["t"]] = freshness(int(m["t"]) + TF_SEC.get(tf, 0), m["dir"], px_m, slp, tpp, now, [p, p5g])
        if pl_cfg:                                         # the operator's plan: results of earlier signals, then new ones
            p5 = payloads.get("5m")
            same = p5 is not None and (p5.get("meta") or {}).get("price_source") == p["meta"].get("price_source")
            upd, plans, done = plan_updates(plans, tf, p["chart"], last_t, off, p5 if same else None,
                                            quiet=gate_quiet(state, "plan"))
            for c in done:
                tally[c["result"]] = tally.get(c["result"], 0) + 1
            log = (log + done)[-PLAN_LOG:]
            vlog = (vlog + done)[-VALIDATION_MAX:]
            sigs = sorted((m for m in p["markers"] if m["type"] == "SIGNAL" and m["t"] > since and m.get("px") is not None),
                          key=lambda m: m["t"])
            for m in sigs:
                td_m = int(m["t"]) + TF_SEC.get(tf, 0)
                gday = state.setdefault("gates", {}).setdefault(trading_day(td_m), {}).setdefault(
                    tf, {"bars": 0, "signals": 0, "long": {}, "short": {}})
                gday["signals"] += 1
                state["last_signal"] = {"tf": tf, "dir": m["dir"], "t_dec": td_m, "px": m["px"]}
                rp = repeat_of(m, tf, plans)               # A1: one idea, one plan
                if rp is not None:
                    repeats[m["t"]] = rp
                    fz_rp = fresh.get(m["t"])
                    if fz_rp and fz_rp["state"] != "FRESH" and rp.get("id") in gate_quiet(state, "plan"):
                        fresh[m["t"]] = {**fz_rp, "state": "NOT ACTIONABLE",   # the idea it repeats was not actionable
                                         "why": f"repeat of plan #{rp.get('id')}, which was not actionable"}
                    state["plan_repeats"] = (state.get("plan_repeats", []) + [
                        {"tf": tf, "t": m["t"], "t_dec": int(m["t"]) + TF_SEC.get(tf, 0), "dir": m["dir"], "entry": m["px"],
                         "of_id": rp.get("id"), "of_tf": rp["tf"], "of_entry": rp["entry"], "t_alert": t_send}])[-PLAN_LOG:]
                    continue
                sl, tp = plan_levels(m["px"], m["dir"], pl_cfg)
                t_dec = int(m["t"]) + TF_SEC.get(tf, 0)
                tm = alert_timing(m, tf, now, pl_cfg) or {}
                state["plan_seq"] = int(state.get("plan_seq", 0)) + 1
                tp2 = round(m["px"] + m["dir"] * pl_cfg["tp2_px"], 2) if pl_cfg.get("tp2_px") else None
                plans.append({"id": state["plan_seq"], "tf": tf, "t": m["t"], "dir": m["dir"], "entry": m["px"], "sl": sl, "tp": tp,
                              "tp2": tp2, "tp2_usd": pl_cfg["tp2_usd"] if tp2 is not None else None,
                              "sl_usd": pl_cfg["sl_usd"], "tp_usd": pl_cfg["tp_usd"], "lot": pl_cfg["lot"], "t_dec": t_dec,
                              "session": session_of(t_dec), "dow": date.fromisoformat(trading_day(t_dec)).strftime("%a"),
                              "tq": m.get("tq"), "t_alert": tm.get("t_alert"), "px_alert": tm.get("px_now"),
                              "move_alert": tm.get("move"), "late": tm.get("late")})
                if fresh.get(m["t"], {}).get("state", "FRESH") != "FRESH":
                    gate_note(state, f"plan:{state['plan_seq']}", fresh[m["t"]])
        ctx = {"repeats": repeats, "breaks": _breaks_today(liq_log, trading_day(t_send)), "h_records": h_records(store_dir, tf),
               "fresh": fresh, "quiet": gate_quiet(state, "plan")}
        ll = liq_lines(ev, seen, off)                     # always marks the pools seen; sent unless quality mode
        lines = upd + messages(p, since, now, ctx) + ([] if quality() else ll)
        if sixty():                                        # the phone: 15m signals and their plan follow-ups only
            phone_lines = upd + messages(p, since, now, ctx, signals_only=True) if tf in PHONE_TFS_SIXTY else []
        else:
            phone_lines = lines
        report[tf] = {"lines": lines, "sent": send(trade_msg(phone_only(phone_lines)))}
        if tf == "15m" and setups_on():                    # SETUP alerts: the operator's level rules (B16)
            p5s = payloads.get("5m")
            p5s = p5s if p5s is not None and (p5s.get("meta") or {}).get("price_source") == p["meta"].get("price_source") else None
            s_upd, s_open, s_done = setup_track(state.get("setups", []), p["chart"], p5s, t_send, off)
            s_log = (list(state.get("setup_log", [])) + s_done)[-500:]
            sseen = dict(state.get("setup_seen", {}))
            live = setup_record(None, s_log, t_send)["live"]
            stale_s = []
            for e in setup_scan(payloads, since, sseen):
                state["setup_seq"] = int(state.get("setup_seq", 0)) + 1
                sid, d, x = state["setup_seq"], e["dir"], e["close"]
                conf = bool(e.get("confirmed"))
                s_open.append({"id": sid, "tf": "15m", "t": e["t"], "t_dec": e["t"] + 900, "dir": d, "entry": x, "kind": e["kind"],
                               "levels": e["levels"], "zones": e["zones"], "sl": round(x - d * SETUP_SL_PX, 2),
                               "tp": round(x + d * SETUP_TP_PX, 2), "checks": e.get("checks"), "confirmed": conf,
                               "phone": (conf and not sixty()) or not quality(), "t_alert": t_send})
                fz = freshness(e["t"] + 900, d, x, SETUP_SL_PX, ENG_PX, now, [p, p5s])   # TP1 +$13 is the first target
                sl_ = setup_lines(e, sid, pl_cfg, now, off, live)
                if fz["state"] != "FRESH":
                    gate_note(state, f"setup:{sid}", fz)
                if fz["state"] == "NOT ACTIONABLE":
                    if s_open[-1]["phone"]:
                        stale_s.append(stale_item("BUY" if d == 1 else "SELL", f"15m SETUP #{sid}", e["t"] + 900, x, fz, off))
                    report.setdefault("setup_alerts", []).append({"lines": [RECORD_ONLY + x_ for x_ in sl_], "sent": []})
                    continue
                if fz["state"] == "DELAYED":
                    sl_ = sl_[:1] + [delayed_line(fz, off)] + sl_[1:]
                report.setdefault("setup_alerts", []).append({"lines": sl_, "sent": send(trade_msg(sl_)) if s_open[-1]["phone"] else []})
            if stale_s:
                ls_ = [stale_line("setup alert" + ("s" if len(stale_s) > 1 else ""), stale_s)]
                report["setup_stale"] = {"lines": ls_, "sent": send(trade_msg(ls_))}
            if s_upd:                                      # results only for setups that reached the phone
                shown = {c_["id"] for c_ in s_done if c_.get("phone", True)} - gate_quiet(state, "setup")
                s_upd = [x for x in s_upd if any(f" #{k} " in x for k in shown)]
                if s_upd:
                    report["setup_updates"] = {"lines": s_upd, "sent": send(trade_msg(s_upd))}
            state["setups"], state["setup_log"] = s_open[-60:], s_log
            keep_s = trading_day(t_send - 3 * 86400)
            state["setup_seen"] = {k: v for k, v in sseen.items() if v >= keep_s}
        if tf == "4h" and setups_on():                     # B18: the operator's 4h candle breakout with all four confirmations
            live = setup_record(None, state.get("setup_log", []), t_send)["live"]
            s_open = list(state.get("setups", []))
            stale_h = []
            p15h = payloads.get("15m")
            p5h = payloads.get("5m")
            p5h = p5h if p5h is not None and p15h is not None and (p5h.get("meta") or {}).get("price_source") == \
                (p15h.get("meta") or {}).get("price_source") else None
            for e in h4_scan(payloads, since):
                state["setup_seq"] = int(state.get("setup_seq", 0)) + 1
                sid, d, x = state["setup_seq"], e["dir"], e["close"]
                phone = (e["confirmed"] and not sixty()) or not quality()
                s_open.append({"id": sid, "tf": "15m", "t": e["t_close"] - 900, "t_dec": e["t_close"], "dir": d, "entry": x,
                               "kind": "4H BREAKOUT", "levels": e["beyond"], "zones": [], "sl": round(x - d * SETUP_SL_PX, 2),
                               "tp": round(x + d * SETUP_TP_PX, 2), "checks": e["checks"], "confirmed": e["confirmed"],
                               "phone": phone, "t_alert": t_send})
                fz = freshness(e["t_close"], d, x, SETUP_SL_PX, ENG_PX, now, [p, p15h, p5h])
                hl = h4_lines(e, sid, pl_cfg, now, off, live)
                if fz["state"] != "FRESH":
                    gate_note(state, f"setup:{sid}", fz)
                if fz["state"] == "NOT ACTIONABLE":
                    if phone:
                        stale_h.append(stale_item("BUY" if d == 1 else "SELL", f"4h CANDLE BREAKOUT #{sid}", e["t_close"], x, fz, off))
                    report.setdefault("h4_alerts", []).append({"lines": [RECORD_ONLY + x_ for x_ in hl], "sent": []})
                    continue
                if fz["state"] == "DELAYED":
                    hl = hl[:1] + [delayed_line(fz, off)] + hl[1:]
                report.setdefault("h4_alerts", []).append({"lines": hl, "sent": send(trade_msg(hl)) if phone else []})
            if stale_h:
                lh_ = [stale_line("4h breakout alert" + ("s" if len(stale_h) > 1 else ""), stale_h)]
                report["h4_stale"] = {"lines": lh_, "sent": send(trade_msg(lh_))}
            state["setups"] = s_open[-60:]
        state[tf] = last_t
    if pl_cfg:
        state["plans"], state["plan_log"], state["plan_tally"] = plans[-PLAN_MAX_OPEN:], log, tally
        # for the website's "Your plan alerts" card (index.json -> alerts.plans): the plan, open trades, results, channels
        report["plans"] = {"cfg": {k: pl_cfg[k] for k in ("lot", "sl_usd", "tp_usd", "cost_usd", "tp2_usd")},
                           "tp_first": pl_cfg["sl_px"] / (pl_cfg["sl_px"] + pl_cfg["tp_px"]),
                           "break_even": (pl_cfg["sl_usd"] + pl_cfg["cost_usd"]) / (pl_cfg["sl_usd"] + pl_cfg["tp_usd"]),
                           "open": state["plans"], "recent": log[::-1], "tally": tally, "tfs": list(tfs),
                           "late_frac": _env_float("PLAN_LATE_FRAC", LATE_FRAC),
                           "repeats": state.get("plan_repeats", [])[::-1][:10], "repeat_rule": {"sec": REPEAT_SEC, "usd": REPEAT_USD},
                           "mode": alert_mode(), "phone_tfs": [x for x in tfs if x in PHONE_TFS_SIXTY] if sixty() else list(tfs)}
    if liq_on() and alerted:                               # A2: trend-change warning, once per direction per trading day
        today = trading_day(t_send)
        tl = turn_lines(state, payloads, tfs, liq_log, [x for x in plans + log if trading_day(_decision_t(x)) == today],
                        t_send, off)
        if tl:
            report["turn_warning"] = {"lines": tl, "sent": [] if sixty() else send(tl)}
    report["turn_log"] = state.get("turn_log", [])[::-1][:10]
    glines, report["grab_test"] = grab_run(store_dir, state, payloads, t_send, off)   # B9-GRAB-FWD, every run
    if glines:
        report["grab_test_alert"] = {"lines": glines, "sent": [] if sixty() else send(trade_msg(phone_only(glines)))}   # trades and results
    if setups_on():                                        # the live SETUP record (descriptive) and the site block
        srec = setup_record(store_dir, state.get("setup_log", []), t_send)
        report["setups"] = {"on": True, "quality": quality(), "sixty": sixty(), "hist_confirmed": list(SETUP_HIST_CONFIRMED) if SETUP_HIST_CONFIRMED else None,
                            "hist_4h": list(H4_HIST),
                            "started_utc": srec["started_utc"], "live": srec["live"], "open": state.get("setups", []),
                            "recent": state.get("setup_log", [])[::-1][:12], "hist": {k: list(v) for k, v in SETUP_HIST.items()},
                            "rule": "research/registrations/B16.json", "tp_px": SETUP_TP_PX, "sl_px": SETUP_SL_PX}
    if pl_cfg:                                             # B15-ENGINE-FWD, every run (reads the plans' results)
        elines, report["engine_test"] = eng_run(store_dir, vlog, plans, t_send)
        if elines:
            report["engine_test_alert"] = {"lines": elines, "sent": send(elines)}
    if liq_on() and alerted:                               # price near a pool: once per run, not per timeframe
        ev = liquidity_near(payloads, tfs, seen, t_send)
        if ev:
            lines = [liq_text(r, off) for r in ev]
            report["liquidity_near"] = {"lines": lines, "sent": [] if quality() else send(lines)}
            liq_log += ev
    keep_from = trading_day(t_send - 3 * 86400)
    state["liq_seen"] = {k: v for k, v in seen.items() if v >= keep_from}
    state["liq_log"] = liq_log[-_LIQ_LOG:]
    report["liquidity"] = {"on": liq_on(), "near_usd": _env_float("LIQ_NEAR_USD", LIQ_NEAR_USD), "recent": state["liq_log"][::-1]}
    report["engine_status"] = {"gates": state.get("gates", {}), "last_signal": state.get("last_signal")}
    report["channels"] = channels()
    report["fresh_gate"] = {"fresh_sec": FRESH_SEC, "recovery_sec": RECOVERY_SEC, "price_fresh_sec": PRICE_FRESH_SEC,
                            "recent": [{"key": k, **v} for k, v in list((state.get("fresh_gate") or {}).items())[::-1][:20]]}
    from . import confirm_panel  # the confirmation panel: website only, never sent
    if confirm_panel.on():
        try:
            report["confirm"] = confirm_panel.panel(payloads, state, t_send, store_dir=store_dir)
        except Exception as e:  # noqa: BLE001  (a panel failure must never stop the alerts)
            report["confirm"] = {"on": True, "error": f"{type(e).__name__}: {e}"}
    from . import fwd_b24  # B24-CONFIRM-FWD: records only, never sent
    try:                                                 # A2: a start the operator declared void is moved aside, once
        v = fwd_b24.void_premature(state, store_dir, t_send)
        if v:
            report["b24_void"] = v
    except Exception as e:  # noqa: BLE001  (a recorder failure must never stop the alerts)
        report["b24_void"] = {"error": f"{type(e).__name__}: {e}"}
    if fwd_b24.on():
        try:
            report["b24"] = fwd_b24.run(payloads, state, t_send, store_dir)
        except Exception as e:  # noqa: BLE001  (a recorder failure must never stop the alerts)
            report["b24"] = {"id": fwd_b24.ID, "error": f"{type(e).__name__}: {e}"}
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
            last = state.get("last_signal") or next(({"tf": r["tf"], "dir": r["dir"], "t_dec": _decision_t(r)} for r in vlog[::-1]), None)
            el = engine_line(state, prev, tfs, last)       # also on a silent weekday: why there was no signal
            if el:
                lines.append(el)
        if state.get("report_week") and state["report_week"] != week:
            prev = state["report_week"]
            recs = [r for r in vlog if trading_week(_decision_t(r)) == prev]
            n_open = sum(1 for p in plans if trading_week(_decision_t(p)) == prev)
            if recs or n_open:
                lines += report_lines("WEEKLY", prev, summarize(recs, cpl), n_open)
        gt = report["grab_test"]
        g_prev = [x for x in gt["recent"] + gt["open"]
                  if state.get("report_day") and state["report_day"] != day and trading_day(x["t_close"]) == state["report_day"]]
        if lines or g_prev:                                # the registered GRAB test's state rides with the daily report
            lines.append(f"GRAB TEST ({GRAB_ID}): {gt['status']} | break-even {GRAB_BE:.0%}")
        su = report.get("setups")
        if lines and su and state.get("report_day") and state["report_day"] != day:
            prev_d = state["report_day"]
            dd_ = [r for r in state.get("setup_log", []) if trading_day(_decision_t(r)) == prev_d and r.get("result") in ("TP", "SL", "BOTH")]
            tot = sum(v[0] for v in su["live"].values())
            won = sum(v[1] for v in su["live"].values())
            lines.append(f"SETUPS (your rules) {date.fromisoformat(prev_d):%a %d %b}: {len(dd_)} decided, "
                         f"{sum(r['result'] == 'TP' for r in dd_)} reached +$15 first | since start {won}/{tot}")
        et = report.get("engine_test")
        if lines and et:                                   # and the engine test's (B15-ENGINE-FWD)
            lines.append(f"ENGINE TEST ({ENG_ID}): {et['status']} | open {et['open']} | break-even {ENG_BE:.0%}")
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
    dl = save_deliveries(store_dir)                        # proof of delivery (status codes, ntfy ids), no secrets
    if dl:
        report["delivery"] = dl
    if vpath and pl_cfg:
        with open(vpath, "w") as f:
            json.dump(vlog, f)
    return json_safe(report)
