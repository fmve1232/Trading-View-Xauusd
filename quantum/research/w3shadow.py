"""B31b-W3 shadow module (research/registrations/B31b-W3.json, 'shadow_module'). RESEARCH ONLY.

Runs the W3 detector (imported from w3liq, never copied) on the market-data store's CLOSED bars at a given instant and
appends what it sees to an append-only, hash-chained JSONL ledger:

  EVENT     every liquidity event (sweep / break of a live level) the first time a step sees it
  ENTRY     every order a registered method places for it: entry reference, structural stop, TP1-3, costs, lots,
            eligibility and rejection reason, data freshness; STALE (seen more than 20 minutes after its decision close)
            never qualifies; QUALIFIES only under a frozen W3 candidate (research/registrations/B31b-W3-FREEZE.json)
  RESOLVE   once the outcome is in the past: TP / SL sequence per target, minutes to target, MFE / MAE, and a matched
            control entry (same direction and stop distance, 1-16 bars later, chosen by the entry's id hash)
  CLASS     the event's class A-G once its 24 h window has closed

Ids are unique and a second append of an id is refused, so re-running a step changes nothing. Every value is computed
from bars that closed at or before `now`. No alert, no notification, no network call, no production file: wiring it
into the site's workflow needs the operator's explicit authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os

import numpy as np
import pandas as pd

from ..data import sources, store
from . import w3liq as W

LOOKBACK_DAYS = 60          # warm-up bars loaded each step
SCORE_DAYS = 3              # decisions re-examined each step
STALE_SEC = 1200            # the site's FRESH_SEC: a decision first seen later than this is STALE
SERIES = {"M15": ("XAU_USD_15m", 900), "M5": ("XAU_USD_5m", 300), "H1": ("XAU_USD_60m", 3600)}


def closed_bars(store_dir: str, name: str, step: int, now: int) -> pd.DataFrame | None:
    df = store.load(store_dir, name)
    if df is None or not len(df):
        return None
    df = sources.trading_week_only(sources.drop_offgrid(df))
    t = W.ta.epoch_s(df.index).astype(np.int64)
    keep = (t + step <= now) & (t >= now - LOOKBACK_DAYS * 86400)
    return df[keep][["open", "high", "low", "close"]].assign(volume=np.nan)


def read_ledger(path: str) -> tuple[list[dict], str]:
    if not os.path.exists(path):
        return [], "0" * 64
    rows = [json.loads(x) for x in open(path) if x.strip()]
    return rows, (rows[-1]["hash"] if rows else "0" * 64)


def append(path: str, recs: list[dict], prev: str, ids: set) -> int:
    n = 0
    with open(path, "a") as f:
        for r in recs:
            if r["id"] in ids:
                continue
            body = json.dumps(W.jsonable(r), sort_keys=True, allow_nan=False)
            h = hashlib.sha256((prev + body).encode()).hexdigest()
            f.write(json.dumps({**json.loads(body), "prev": prev, "hash": h}, sort_keys=True) + "\n")
            prev = h
            ids.add(r["id"])
            n += 1
    return n


def verify_chain(path: str) -> bool:
    prev = "0" * 64
    seen = set()
    for line in open(path):
        r = json.loads(line)
        h, p = r.pop("hash"), r.pop("prev")
        if p != prev or r["id"] in seen:
            return False
        if hashlib.sha256((prev + json.dumps(r, sort_keys=True, allow_nan=False)).encode()).hexdigest() != h:
            return False
        prev = h
        seen.add(r["id"])
    return True


def control_offset(oid: str) -> int:
    return 1 + int(hashlib.sha256(oid.encode()).hexdigest()[:8], 16) % 16


def frozen() -> dict | None:
    return json.load(open(W.FREEZE_PATH)) if os.path.exists(W.FREEZE_PATH) else None


def qualifies(row: dict, fz: dict | None) -> bool:
    if fz is None or not row.get("eligible"):
        return False
    for c in fz.get("candidates", {}).values():
        if c["m"] == row["m"] and c["tf"] == row["tf"]:
            return bool(W.apply_frozen([dict(row)], c))
    return False


def step(store_dir: str, ledger: str, now: int, fz: dict | None = None) -> dict:
    """One shadow step at instant `now` (epoch s): new EVENT / ENTRY records, then RESOLVE / CLASS for what is now past."""
    m15 = closed_bars(store_dir, SERIES["M15"][0], 900, now)
    if m15 is None or len(m15) < 500:
        return {"now": now, "skipped": "not enough closed 15m bars"}
    h1 = closed_bars(store_dir, SERIES["H1"][0], 3600, now)
    m5 = closed_bars(store_dir, SERIES["M5"][0], 300, now)
    P, F15, F30, _ = W.frames(m15, h1, m5)
    piv = W.m5_pivots(P)
    rows, prev = read_ledger(ledger)
    ids = {r["id"] for r in rows}
    seen_at = {r["id"]: r.get("seen") for r in rows}
    new = []
    sf = now - SCORE_DAYS * 86400
    for F in (F15, F30):
        evs, trades, _ = W.build(P, F, sf, piv, log=lambda *_: None)
        by_ev = {}
        for r in trades:
            by_ev.setdefault(r["ev_id"], []).append(r)
        for ev in evs:
            if ev["id"] not in ids:
                new.append({"kind": "EVENT", "id": ev["id"], "seen": now, "t": ev["t"], "tf": ev["tf"], "side": ev["side"],
                            "disp": ev["disp"], "level": ev["L"], "level_outer": ev["L_out"], "kinds": ev["names"],
                            "sweep_or_break_price": ev["ext"], "types": ev["types"], "sess": ev["sess"],
                            "freshness_s": now - ev["t"], "stale": now - ev["t"] > STALE_SEC})
            if ev["t"] + W.HOLD_SEC <= now - 900 and ev["id"] + "|C" not in ids and ev["cls_sub"] != "data end":
                new.append({"kind": "CLASS", "id": ev["id"] + "|C", "seen": now, "cls": ev["cls"], "sub": ev["cls_sub"],
                            "mfe240": ev["mfe240"], "mae240": ev["mae240"], "de240": ev["de240"]})
            for r in by_ev.get(ev["id"], []):
                if r["t_dec"] > now:
                    continue
                oid = f"{ev['id']}|{r['m']}"
                first = seen_at.get(oid, now)
                if oid not in ids:
                    stale = (now - r["t_dec"]) > STALE_SEC
                    rec = {"kind": "ENTRY", "id": oid, "ev": ev["id"], "seen": now, "engine": r["m"][0], "m": r["m"], "tf": r["tf"],
                           "t_dec": r["t_dec"], "status": r["status"], "why": r.get("why"), "freshness_s": now - r["t_dec"], "stale": stale}
                    if r["status"] == "FILLED":
                        s = r["s"]
                        rec.update(entry=r["e"], stop=r["stop"], D=r["D"], cost=r["cost"], lots=r["lots"], eligible=r["eligible"],
                                   tp1=r["e"] + r["d"] * 10 * s, tp2=r["e"] + r["d"] * 15 * s, tp3=r["e"] + r["d"] * 20 * s,
                                   t_fill=r["t_fill"], qualifies=(not stale) and qualifies(r, fz))
                    new.append(rec)
                if r["status"] != "FILLED" or oid + "|R" in ids:
                    continue
                if all(r.get(f"tp{t}") in ("TP", "SL", "AMBIGUOUS", "TIMEOUT") for t in (10, 15, 20)):
                    ctl = control(P, r, oid)
                    if ctl is None:
                        continue
                    new.append({"kind": "RESOLVE", "id": oid + "|R", "seen": now, "first_seen": first,
                                **{f"tp{t}": r[f"tp{t}"] for t in (10, 15, 20)},
                                **{f"tp{t}_min": r[f"tp{t}_min"] for t in (10, 15, 20)},
                                **{f"tp{t}_r": r[f"tp{t}_r"] for t in (10, 15, 20)},
                                "mfe": r["mfe"], "mae": r["mae"], "loss_usd": r.get("loss_usd"), "control": ctl})
    n = append(ledger, new, prev, ids)
    return {"now": now, "appended": n, "records": len(ids)}


def control(P: W.Path, r: dict, oid: str) -> dict | None:
    """The matched control: same direction and scaled stop distance, entered at the close of the bar `control_offset`
    bars after the decision bar; None until its outcome is in the past."""
    kd = W.k_at(P, r["t_dec"]) - 1 if r["t_dec"] % 900 == 0 else W.k_at(P, r["t_dec"] - r["t_dec"] % 900)
    b = kd + control_offset(oid)
    if b >= len(P.c) - 1:
        return None
    e = float(P.c[b])
    s = e / 4000.0
    stop = e - r["d"] * r["D"] * s
    out = {}
    for T in W.TP:
        o, _, px, _ = W.race_fast(P, b + 1, r["d"], e, stop, e + r["d"] * T * s)
        if o not in ("TP", "SL", "AMBIGUOUS", "TIMEOUT"):
            return None
        out[f"tp{int(T)}"] = o
        out[f"tp{int(T)}_r"] = (r["d"] * (px - e) / s - float(P.cost[b])) / (r["D"] + float(P.cost[b]))
    out["offset_bars"] = control_offset(oid)
    return out


def replay(store_dir: str, ledger: str, t0: int, t1: int, every: int) -> list[dict]:
    return [step(store_dir, ledger, t, frozen()) for t in range(t0, t1 + 1, every)]


def summary(ledger: str) -> dict:
    rows, _ = read_ledger(ledger)
    k = pd.Series([r["kind"] for r in rows]).value_counts().to_dict()
    ent = [r for r in rows if r["kind"] == "ENTRY"]
    res = {r["id"][:-2]: r for r in rows if r["kind"] == "RESOLVE"}
    out = {"records": len(rows), "kinds": {a: int(b) for a, b in k.items()}, "chain_ok": verify_chain(ledger),
           "stale_entries": sum(1 for r in ent if r.get("stale")),
           "freshness_median_s": float(np.median([r["freshness_s"] for r in ent])) if ent else math.nan,
           "by_method": {}}
    for m in W.A_METHODS + W.B_METHODS:
        for tf in W.TFS:
            e = [r for r in ent if r["m"] == m and r["tf"] == tf]
            if not e:
                continue
            el = [r for r in e if r.get("eligible")]
            rs = [res[r["id"]] for r in el if r["id"] in res]
            out["by_method"][f"{m}|{tf}"] = {"entries": len(e), "filled": sum(1 for r in e if r["status"] == "FILLED"),
                                             "eligible": len(el), "resolved": len(rs),
                                             "tp10_first": sum(1 for r in rs if r["tp10"] == "TP"),
                                             "control_tp10_first": sum(1 for r in rs if r["control"]["tp10"] == "TP")}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="B31b-W3 shadow module (research only; no alert)")
    ap.add_argument("cmd", choices=("step", "replay", "summary"))
    ap.add_argument("--store", required=False)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--now", default=None)
    ap.add_argument("--from", dest="t0", default=None)
    ap.add_argument("--to", dest="t1", default=None)
    ap.add_argument("--every-min", type=int, default=15)
    a = ap.parse_args(argv)
    ts = lambda x: int(pd.Timestamp(x, tz="UTC").timestamp())     # noqa: E731
    if a.cmd == "step":
        print(json.dumps(step(a.store, a.ledger, ts(a.now) if a.now else int(pd.Timestamp.now(tz="UTC").timestamp()), frozen())))
    elif a.cmd == "replay":
        r = replay(a.store, a.ledger, ts(a.t0), ts(a.t1), a.every_min * 60)
        print(json.dumps({"steps": len(r), "appended": sum(x.get("appended", 0) for x in r)}))
    print(json.dumps(W.jsonable(summary(a.ledger)), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
