"""Alerts for newly CONFIRMED events (all optional, all free):
  NTFY_TOPIC            ntfy.sh topic -> phone push via the free ntfy app, no account
  TELEGRAM_BOT_TOKEN +  TELEGRAM_CHAT_ID
  DISCORD_WEBHOOK_URL

Only events on bars that closed since the previous run are sent (state kept in the data
store), so a re-run never repeats an alert. Prices are shown with the MT5 offset from the
MT5_PRICE_OFFSET variable (display only, like the Pine input).

Structure / sweep alerts (Pine line v49): one line per closed bar on which the engine's BOS, CHoCH, MSS
or a PDH/PDL/PWH/PWL/PMH/PML sweep first appears, plus the separately registered H2 / H3 / H4 setups. They are
information, not entries; the DECISION is unchanged. ALERT_STRUCTURE=0 turns them off.
"""
from __future__ import annotations

import json
import os

from .data.sources import requests

STATE = "alerts_state.json"


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
        report[tf] = {"lines": lines, "sent": send(lines)}
        state[tf] = last_t
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
