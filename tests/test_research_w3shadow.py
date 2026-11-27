"""B31b-W3 shadow module: closed bars only, append-only and idempotent, hash chain, stale decisions, no alert path."""
import json
import os

import numpy as np
import pandas as pd

from quantum.data import store
from quantum.research import harness as H
from quantum.research import w3shadow as S


def make_store(tmp_path, n=1600, seed=21):
    rng = H.seeded_rng(seed)
    c = 4000 + np.cumsum(rng.normal(0, 1.6, n))
    o = np.concatenate([[4000.0], c[:-1]])
    hi = np.maximum(o, c) + np.abs(rng.normal(0, 0.9, n))
    lo = np.minimum(o, c) - np.abs(rng.normal(0, 0.9, n))
    idx = pd.date_range("2026-09-07 00:00", periods=n, freq="15min", tz="UTC")
    m15 = pd.DataFrame({"open": o, "high": hi, "low": lo, "close": c, "volume": np.nan}, index=idx)
    h1 = m15.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["open"])
    d = str(tmp_path / "store")
    store.save(d, "XAU_USD_15m", m15)
    store.save(d, "XAU_USD_60m", h1)
    return d, m15


def test_step_is_idempotent_uses_closed_bars_only_and_keeps_a_valid_chain(tmp_path):
    d, m15 = make_store(tmp_path)
    led = str(tmp_path / "led.jsonl")
    now = int(m15.index[1100].timestamp()) + 60
    r1 = S.step(d, led, now)
    assert r1["appended"] > 0
    r2 = S.step(d, led, now)
    assert r2["appended"] == 0
    rows = [json.loads(x) for x in open(led)]
    assert len({r["id"] for r in rows}) == len(rows)
    for r in rows:
        if r["kind"] == "EVENT":
            assert r["t"] <= r["seen"] == now
        if r["kind"] == "ENTRY":
            assert r["t_dec"] <= r["seen"]
            if r["status"] == "FILLED":
                assert r["t_fill"] <= now
    assert S.verify_chain(led)


def test_later_steps_add_resolutions_once_and_never_rewrite(tmp_path):
    d, m15 = make_store(tmp_path)
    led = str(tmp_path / "led.jsonl")
    t0 = int(m15.index[900].timestamp())
    for k in range(0, 40):
        S.step(d, led, t0 + k * 3 * 3600)
    rows = [json.loads(x) for x in open(led)]
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    res = [r for r in rows if r["kind"] == "RESOLVE"]
    assert res, "a resolution is expected once outcomes are in the past"
    ent = {r["id"]: r for r in rows if r["kind"] == "ENTRY"}
    for r in res:
        e = ent[r["id"][:-2]]
        assert r["seen"] >= e["seen"]
        assert r["control"]["offset_bars"] == S.control_offset(e["id"])
    first = open(led).read()
    S.step(d, led, t0 + 39 * 3 * 3600)
    assert open(led).read() == first                                 # nothing new at the same instant


def test_a_decision_first_seen_late_is_stale_and_never_qualifies(tmp_path):
    d, m15 = make_store(tmp_path)
    led = str(tmp_path / "led.jsonl")
    now = int(m15.index[1100].timestamp()) + 6 * 3600                  # six hours after the bars it scores
    S.step(d, led, now)
    ent = [json.loads(x) for x in open(led) if '"ENTRY"' in x]
    old = [r for r in ent if now - r["t_dec"] > S.STALE_SEC]
    assert old and all(r["stale"] for r in old)
    assert not any(r.get("qualifies") for r in old)


def test_tampering_breaks_the_chain(tmp_path):
    d, m15 = make_store(tmp_path)
    led = str(tmp_path / "led.jsonl")
    S.step(d, led, int(m15.index[1100].timestamp()))
    lines = open(led).read().splitlines()
    r = json.loads(lines[0])
    r["level"] = (r.get("level") or 0) + 1
    lines[0] = json.dumps(r, sort_keys=True)
    open(led, "w").write("\n".join(lines) + "\n")
    assert not S.verify_chain(led)


def test_the_shadow_module_has_no_alert_or_network_path():
    src = open(os.path.join(os.path.dirname(S.__file__), "w3shadow.py")).read()
    for word in ("ntfy", "requests", "urllib", "notify", "http://", "https://", "smtplib", "socket"):
        assert word not in src
