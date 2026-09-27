"""Frozen forward holdout -- the audit's only real fix for in-sample contamination.

The price history before the freeze was used, directly or through human judgement, to shape
Quantum 5.x (audit/AUDIT_PROMPT.md §9, F-037). No re-slicing of that history can be out of
sample. Evidence starts at the FREEZE: the moment a given configuration hash is first
deployed. Every trade entered after it was decided by parameters that could not have seen
its outcome.

The manifest lives with the market-data store (and, with its git history, on the
`forward-ledger` branch). The holdout is keyed on the FREEZE KEY = configuration hash + a hash
of the signal-producing source code (`engine_code_hash`). If either changes, the holdout is
RESET (new freeze = now), the old one is kept in `history`, and its ledger entries are moved
to `holdout/archive/`, never deleted -- so neither a changed parameter nor a changed engine can
inherit the evidence gathered under the previous one.

The first freeze is pinned to the pre-registered start (HOLDOUT_START, audit/PREREGISTRATION.md
§7): a deployment before it waits for it; nothing entered earlier counts.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

from .config import ENGINE_VERSION, Config

FILE = "holdout_manifest.json"
HOLDOUT_START = datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc)   # pre-registered; do not move

_PKG = os.path.dirname(os.path.abspath(__file__))
# Source that can change a signal or a recorded trade. Display, alerting and this bookkeeping
# module are excluded, so a display fix does not restart the holdout; anything listed here does.
ENGINE_SOURCES = ("ta.py", "sessions.py", "features.py", "analog.py", "engine.py", "backtest.py",
                  "config.py", "pipeline.py", "data/sources.py", "data/market.py", "data/store.py")


def engine_code_hash() -> str:
    h = hashlib.sha256()
    for rel in ENGINE_SOURCES:
        with open(os.path.join(_PKG, rel), "rb") as f:
            h.update(rel.encode() + b"\0" + f.read().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()[:16]


def freeze_key(cfg: Config) -> str:
    return f"{cfg.hash()}:{engine_code_hash()}"


def load_or_freeze(store_dir: str | None, cfg: Config, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    key = freeze_key(cfg)
    path = os.path.join(store_dir, FILE) if store_dir else None
    man = None
    if path and os.path.exists(path):
        with open(path) as f:
            man = json.load(f)
    if man and man.get("freeze_key") == key:
        man["status"] = "ACTIVE" if now >= datetime.fromisoformat(man["freeze_utc"]) else "PENDING"
        return man
    hist = (man or {}).get("history", [])
    if man:
        hist.append({k: man.get(k) for k in ("freeze_key", "config_hash", "engine_code_hash", "engine_version", "freeze_utc")}
                    | {"ended_utc": now.isoformat()})
    start = max(now, HOLDOUT_START)
    cfg_h, code_h = key.split(":")
    man = {"freeze_key": key, "config_hash": cfg_h, "engine_code_hash": code_h, "engine_version": ENGINE_VERSION,
           "freeze_utc": start.isoformat(), "status": "PENDING" if start > now else ("RESET" if hist else "STARTED"),
           "history": hist}
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
                  key: str, price_source: str = "") -> list[dict]:
    """Append-only record of CLOSED trades entered after the freeze.

    A trade is written once, the first time it is seen closed, and never rewritten -- even if
    a later run with a longer or shorter data window would simulate it slightly differently.
    That is what makes it a forward record rather than a re-computation of the past. Entries
    made under a previous freeze key are moved to holdout/archive/, never dropped.
    """
    path = os.path.join(store_dir, "holdout", f"{tf}_{arm}.json") if store_dir else None
    led = []
    if path and os.path.exists(path):
        with open(path) as f:
            led = json.load(f)
    old = [t for t in led if t.get("freeze_key", t.get("config_hash")) != key]
    led = [t for t in led if t.get("freeze_key", t.get("config_hash")) == key]
    if old and path:
        apath = os.path.join(store_dir, "holdout", "archive", f"{tf}_{arm}.json")
        os.makedirs(os.path.dirname(apath), exist_ok=True)
        arch = []
        if os.path.exists(apath):
            with open(apath) as f:
                arch = json.load(f)
        with open(apath, "w") as f:
            json.dump(arch + old, f, indent=0)
    seen = {(t["entry_time"], t["dir"]) for t in led}
    now = datetime.now(timezone.utc).isoformat()
    for t in trades:
        if t.get("open") or t["entry_time"] < freeze_iso:
            continue
        k = (t["entry_time"], t["dir"])
        if k not in seen:
            led.append({**t, "recorded_utc": now, "freeze_key": key, "price_source": price_source})
            seen.add(k)
    led.sort(key=lambda t: t["entry_time"])
    if path:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(led, f, indent=0)
    return led
