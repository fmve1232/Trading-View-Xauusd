"""Alerts for newly CONFIRMED events (all optional, all free):
  NTFY_TOPIC            ntfy.sh topic -> phone push via the free ntfy app, no account
  TELEGRAM_BOT_TOKEN +  TELEGRAM_CHAT_ID
  DISCORD_WEBHOOK_URL

Only events on bars that closed since the previous run are sent (state kept in the data
store), so a re-run never repeats an alert. Prices are shown with the MT5 offset from the
MT5_PRICE_OFFSET variable (display only, like the Pine input).
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
    for d in payload["decisions"]:
        if since_t is not None and d["t"] <= since_t:
            continue
        if d["to"] in ("BUY", "SELL"):
            continue  # already covered by the SIGNAL message
        out.append(f"XAUUSD {tf} DECISION {d['from']} -> {d['to']}")
    return out


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
    if path:
        with open(path, "w") as f:
            json.dump(state, f)
    return report
