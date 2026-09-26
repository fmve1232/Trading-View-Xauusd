"""Frozen forward holdout -- the audit's only real fix for in-sample contamination.

The price history before the freeze was used, directly or through human judgement, to shape
Quantum 5.x (audit/AUDIT_PROMPT.md §9, F-037). No re-slicing of that history can be out of
sample. Evidence starts at the FREEZE: the moment a given configuration hash is first
deployed. Every trade entered after it was decided by parameters that could not have seen
its outcome.

The manifest lives with the market-data store. If the configuration hash ever changes, the
holdout is RESET (new freeze = now) and the old one is kept in `history`, so a changed
parameter can never inherit the evidence gathered under the previous one.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from .config import ENGINE_VERSION, Config

FILE = "holdout_manifest.json"


def load_or_freeze(store_dir: str | None, cfg: Config, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    h = cfg.hash()
    path = os.path.join(store_dir, FILE) if store_dir else None
    man = None
    if path and os.path.exists(path):
        with open(path) as f:
            man = json.load(f)
    if man and man.get("config_hash") == h:
        man["status"] = "ACTIVE"
        return man
    hist = (man or {}).get("history", [])
    if man:
        hist.append({k: man.get(k) for k in ("config_hash", "engine_version", "freeze_utc")} | {"ended_utc": now.isoformat()})
    man = {"config_hash": h, "engine_version": ENGINE_VERSION, "freeze_utc": now.isoformat(),
           "status": "RESET" if hist else "STARTED", "history": hist}
    if path:
        os.makedirs(store_dir, exist_ok=True)
        with open(path, "w") as f:
            json.dump(man, f, indent=2)
    return man


def split(trades: list[dict], freeze_iso: str) -> tuple[list[dict], list[dict]]:
    pre = [t for t in trades if t["entry_time"] < freeze_iso]
    post = [t for t in trades if t["entry_time"] >= freeze_iso]
    return pre, post


def update_ledger(store_dir: str | None, tf: str, arm: str, trades: list[dict], freeze_iso: str,
                  config_hash: str) -> list[dict]:
    """Append-only record of CLOSED trades entered after the freeze.

    A trade is written once, the first time it is seen closed, and never rewritten -- even if
    a later run with a longer or shorter data window would simulate it slightly differently.
    That is what makes it a forward record rather than a re-computation of the past.
    """
    path = os.path.join(store_dir, "holdout", f"{tf}_{arm}.json") if store_dir else None
    led = []
    if path and os.path.exists(path):
        with open(path) as f:
            led = json.load(f)
    led = [t for t in led if t.get("config_hash") == config_hash]   # a reset starts a new ledger
    seen = {(t["entry_time"], t["dir"]) for t in led}
    now = datetime.now(timezone.utc).isoformat()
    for t in trades:
        if t.get("open") or t["entry_time"] < freeze_iso:
            continue
        key = (t["entry_time"], t["dir"])
        if key not in seen:
            led.append({**t, "recorded_utc": now, "config_hash": config_hash})
            seen.add(key)
    led.sort(key=lambda t: t["entry_time"])
    if path:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(led, f, indent=0)
    return led
