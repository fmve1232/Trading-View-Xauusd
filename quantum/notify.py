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
"""
from __future__ import annotations

import json
import os

from .data.sources import requests

STATE = "alerts_state.json"
PLAN_TRACK_SEC = 3 * 86400          # a plan with no TP / SL after 3 days gets one "still open" alert and is dropped
PLAN_MAX_OPEN = 60


def _fmt(x, off=0.0):
    return "—" if x is None else f"{x + off:.2f}"


def messages(payload: dict, since_t: int | None) -> list[str]:
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
            if pl and m.get("px") is not None:
                out.append(plan_line(m["px"], m["dir"], pl, off))
        elif m["type"] == "TRACK_EXIT":
            out.append(f"XAUUSD {tf} tracked plan {'STOPPED' if (m.get('r') or 0) < 0 else 'reached TP1'} at {_fmt(m['px'], off)} = {m.get('r')}R")
        elif m["type"] == "RISK_LOCK":
            out.append(f"XAUUSD {tf} RISK LOCK engaged -- new entries blocked")
    if os.environ.get("ALERT_STRUCTURE", "1").strip() != "0":
        out += structure_lines(payload, since_t, off)
    for d in payload["decisions"]:
        if since_t is not None and d["t"] <= since_t:
            continue
        if d["to"] in ("BUY", "SELL"):
            continue  # already covered by the SIGNAL message
        out.append(f"XAUUSD {tf} DECISION {d['from']} -> {d['to']}")
    return out


_TAG = {("BOS", 1): "BOS▲", ("BOS", -1): "BOS▼", ("CHoCH", 1): "CHoCH▲", ("CHoCH", -1): "CHoCH▼",
        ("MSS", 1): "MSS▲", ("MSS", -1): "MSS▼", ("SWEEP", 1): "SWEEP-LOW", ("SWEEP", -1): "SWEEP-HIGH"}


def structure_lines(payload: dict, since_t: int | None, off: float = 0.0) -> list[str]:
    """One line per newly closed bar: its structure / sweep events and any H2 / H3 setup on it."""
    tf = payload["meta"]["tf"]
    by_t: dict = {}
    for m in payload["markers"]:
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


def plan_result(plan: dict, chart: dict) -> tuple[str, int] | None:
    """('TP' | 'SL' | 'BOTH', bar open t) for the first bar AFTER the signal bar that touches the plan's TP or SL."""
    t, h, l = chart.get("t") or [], chart.get("h") or [], chart.get("l") or []
    d, sl, tp = plan["dir"], plan["sl"], plan["tp"]
    for k in range(len(t)):
        if t[k] <= plan["t"] or h[k] is None or l[k] is None:
            continue
        hit_tp = h[k] >= tp if d == 1 else l[k] <= tp
        hit_sl = l[k] <= sl if d == 1 else h[k] >= sl
        if hit_tp and hit_sl:
            return "BOTH", t[k]
        if hit_tp:
            return "TP", t[k]
        if hit_sl:
            return "SL", t[k]
    return None


def plan_updates(plans: list[dict], tf: str, chart: dict, now_t: int, off: float = 0.0) -> tuple[list[str], list[dict]]:
    """Follow-up alerts for this timeframe's open plans, and the plans still open afterwards."""
    from datetime import datetime, timezone
    lines, keep = [], []
    for pl in plans:
        if pl["tf"] != tf:
            keep.append(pl)
            continue
        side = "BUY" if pl["dir"] == 1 else "SELL"
        head = f"XAUUSD {tf} YOUR PLAN {side} from {_fmt(pl['entry'], off)}"
        r = plan_result(pl, chart)
        if r is None:
            if now_t - pl["t"] > PLAN_TRACK_SEC:
                lines.append(f"{head}: no TP or SL after 3 days on the site's prices -- check the trade in MT5 (tracking stopped)")
            else:
                keep.append(pl)
            continue
        what, bt = r
        hhmm = datetime.fromtimestamp(bt, timezone.utc).strftime("%d %b %H:%M UTC")
        if what == "TP":
            lines.append(f"{head}: TP {_fmt(pl['tp'], off)} HIT +${pl['tp_usd']:,.0f} -- trade closed in profit ({hhmm} bar)")
        elif what == "SL":
            lines.append(f"{head}: SL {_fmt(pl['sl'], off)} HIT -${pl['sl_usd']:,.0f} -- trade closed at the stop ({hhmm} bar)")
        else:
            lines.append(f"{head}: TP and SL both inside the {hhmm} bar -- order unknown, check MT5 (counted as SL)")
    return lines, keep


def news_lines(news: dict | None, now_t: int, last_alerted: int | None) -> tuple[list[str], int | None]:
    """One alert per dated NFP / CPI / FOMC window, sent on the first run inside it (Pine Visuals v86 alertOnNews).
    Display only: the engine neither blocks nor re-costs news. Returns the lines and the event time now alerted."""
    if not news or os.environ.get("ALERT_NEWS", "1").strip() == "0":
        return [], last_alerted
    b, a = news["before_min"] * 60, news["after_min"] * 60
    for e in news["events"]:
        if e["t"] - b <= now_t <= e["t"] + a and (last_alerted is None or e["t"] > last_alerted):
            from datetime import datetime, timezone
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


def run(store_dir: str | None, payloads: dict, tfs: list[str]) -> dict:
    path = os.path.join(store_dir, STATE) if store_dir else None
    state = {}
    if path and os.path.exists(path):
        with open(path) as f:
            state = json.load(f)
    report = {}
    off = float(os.environ.get("MT5_PRICE_OFFSET", "0") or 0)
    pl_cfg = plan_cfg()
    plans = state.get("plans", []) if pl_cfg else []
    for tf in tfs:
        p = payloads.get(tf)
        if not p or p["meta"]["synthetic"]:
            continue
        last_t = p["chart"]["t"][-1]
        since = state.get(tf)
        if since is None:
            state[tf] = last_t   # first run: remember the position, do not replay history
            continue
        lines = messages(p, since)
        if pl_cfg:                                         # the operator's plan: results of earlier signals, then new ones
            upd, plans = plan_updates(plans, tf, p["chart"], last_t, off)
            lines = upd + lines
            for m in p["markers"]:
                if m["type"] == "SIGNAL" and m["t"] > since and m.get("px") is not None:
                    sl, tp = plan_levels(m["px"], m["dir"], pl_cfg)
                    plans.append({"tf": tf, "t": m["t"], "dir": m["dir"], "entry": m["px"], "sl": sl, "tp": tp,
                                  "sl_usd": pl_cfg["sl_usd"], "tp_usd": pl_cfg["tp_usd"]})
        report[tf] = {"lines": lines, "sent": send(lines)}
        state[tf] = last_t
    if pl_cfg:
        state["plans"] = plans[-PLAN_MAX_OPEN:]
    first = next((payloads[tf] for tf in tfs if payloads.get(tf) and not payloads[tf]["meta"]["synthetic"]), None)
    if first is not None:                                  # news is per release, not per timeframe: once per event
        from datetime import datetime
        now_t = int(datetime.fromisoformat(first["meta"]["generated_utc"]).timestamp())
        lines, state["news"] = news_lines(first.get("news"), now_t, state.get("news"))
        if lines:
            report["news"] = {"lines": lines, "sent": send(lines)}
    if path:
        with open(path, "w") as f:
            json.dump(state, f)
    return report
