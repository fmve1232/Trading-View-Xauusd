"""Durable, append-only log of every live sweep and breakout record (audit gap GA-03; RECORDS ONLY).

Why: the sweep and breakout monitors keep their records in <store>/alerts_state.json, capped at 300 each
(sweeps.KEEP, breakouts.KEEP_EVENTS), and the store is saved as ONE orphan commit replaced every run. The registered
checks (B31b-W7: "descriptive until ... 100 decided") need every record, for months. This module never changes a
record, a detection, an alert or the engine: it reads the state after a run and appends what is new.

What is written: one JSON line per VERSION of a record. A record's version is the SHA-256 of its canonical JSON, so a
record that gains a stage (CONFIRMED, MOVE10, FAILED ...) gets a new line and every earlier line stays. Each line:
  {"rid": "<kind>|<record id>", "kind": "sweep" | "breakout", "tf": level timeframe, "id", "t", "t_close",
   "final": the record can no longer change, "reason": why it is final (FAILED / MOVE20 / CLOSED / watch over),
   "first_seen_utc" / "logged_utc", "versions": {module ids, code SHA-256 of sweeps.py / breakouts.py, GITHUB_SHA},
   "record": the record exactly as the monitor holds it, "sha256": SHA-256 of the canonical record}
Files: <store>/outcomes/<YYYY-MM-DD>.jsonl (the run's UTC day), merged into <ledger>/outcomes/ by a union over
(rid, sha256): a store that goes back or loses files never removes a line from the ledger (normal commits, never
force-pushed).

  python -m quantum.outcomes --append <store>                       after the pipeline, every run
  python -m quantum.outcomes --merge-ledger <store>/outcomes <ledger>/outcomes
  python -m quantum.outcomes --verify <outcomes dir> [--state <alerts_state.json>]
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys
import time

from . import breakouts, sweeps

DIR = "outcomes"
STATE = "alerts_state.json"
_HERE = os.path.dirname(os.path.abspath(__file__))


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(obj) -> str:
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def _file_sha(name: str) -> str:
    with open(os.path.join(_HERE, name), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def versions() -> dict:
    return {"sweeps": sweeps.ID, "sweeps_py": _file_sha("sweeps.py"), "breakouts": breakouts.ID,
            "breakouts_py": _file_sha("breakouts.py"), "git": os.environ.get("GITHUB_SHA", "")}


def final_reason(kind: str, rec: dict) -> str | None:
    """None while the record can still change; else why it is final."""
    st = rec.get("stages") or {}
    if kind == "sweep":
        if not rec.get("done"):
            return None
        for s in ("FAILED", "MOVE20", "CLOSED"):
            if s in st:
                return s
        return "DONE"
    end = next((s for s in ("FAILED", "CLOSED") if s in st), None)
    if end is None:
        return None
    if any(not x.get("done") for x in (rec.get("shadow") or {}).values()):
        return None                               # the shadow entries' races can still add MOVE stages
    return end


def records(state: dict) -> list[tuple[str, str, dict]]:
    bk = state.get("brk") or {}
    out = [("sweep", r.get("ref_tf", ""), r) for r in (bk.get("sw") or {}).values()]
    out += [("breakout", r.get("tf", ""), r) for r in (bk.get("events") or {}).values()]
    return out


def read_dir(d: str) -> list[dict]:
    rows = []
    for f in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
        with open(f) as fh:
            for n, line in enumerate(fh, 1):
                line = line.strip()
                if line:
                    row = json.loads(line)
                    row["_at"] = f"{os.path.basename(f)}:{n}"
                    rows.append(row)
    return rows


def append(store_dir: str, t_now: float | None = None) -> dict:
    """Append every record version not yet logged. Returns counts; never raises on a missing state."""
    path = os.path.join(store_dir, STATE)
    if not os.path.exists(path):
        return {"state": "missing", "appended": 0}
    with open(path) as f:
        state = json.load(f)
    d = os.path.join(store_dir, DIR)
    os.makedirs(d, exist_ok=True)
    logged = read_dir(d)
    seen = {(r["rid"], r["sha256"]) for r in logged}
    first = {}
    for r in logged:
        first.setdefault(r["rid"], r.get("first_seen_utc"))
    now = time.time() if t_now is None else t_now
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    ver = versions()
    new = []
    for kind, tf, rec in records(state):
        rid, h = f"{kind}|{rec['id']}", sha(rec)
        if (rid, h) in seen:
            continue
        reason = final_reason(kind, rec)
        new.append({"rid": rid, "kind": kind, "tf": tf, "id": rec["id"], "t": rec.get("t"), "t_close": rec.get("t_close"),
                    "final": reason is not None, "reason": reason, "first_seen_utc": first.get(rid) or stamp,
                    "logged_utc": stamp, "versions": ver, "record": rec, "sha256": h})
        seen.add((rid, h))
    if new:
        with open(os.path.join(d, f"{day}.jsonl"), "a") as f:
            f.writelines(canonical(row) + "\n" for row in new)
    return {"state": "ok", "appended": len(new), "records_in_state": len(records(state))}


def merge_ledger(src: str, dst: str) -> dict:
    """Union by (rid, sha256), per day file: lines already in the ledger stay, new ones are added, nothing is removed."""
    os.makedirs(dst, exist_ok=True)
    added = 0
    for f in sorted(glob.glob(os.path.join(src, "*.jsonl"))):
        out = os.path.join(dst, os.path.basename(f))
        have = set()
        if os.path.exists(out):
            with open(out) as fh:
                have = {(r["rid"], r["sha256"]) for r in map(json.loads, filter(None, map(str.strip, fh)))}
        with open(f) as fh:
            rows = [json.loads(x) for x in map(str.strip, fh) if x]
        fresh = [r for r in rows if (r["rid"], r["sha256"]) not in have]
        if fresh:
            with open(out, "a") as fh:
                fh.writelines(canonical(r) + "\n" for r in fresh)
            have.update((r["rid"], r["sha256"]) for r in fresh)
            added += len(fresh)
    return {"added": added}


def verify(d: str, state_path: str | None = None) -> dict:
    """Integrity of the log (and, given the current state, its completeness). Problems are listed, never repaired."""
    rows = read_dir(d)
    problems, by_rid, pairs = [], {}, {}
    for r in rows:
        if sha(r["record"]) != r["sha256"]:
            problems.append(f"{r['_at']}: checksum mismatch for {r['rid']}")
        if r["rid"] != f"{r['kind']}|{r['record'].get('id')}":
            problems.append(f"{r['_at']}: rid does not match the record id")
        key = (r["rid"], r["sha256"])
        if key in pairs:
            problems.append(f"{r['_at']}: duplicate of {pairs[key]} ({r['rid']})")
        pairs.setdefault(key, r["_at"])
        by_rid.setdefault(r["rid"], []).append(r)
    finals = {rid: [x for x in v if x["final"]] for rid, v in by_rid.items()}
    for rid, f in finals.items():
        if len({x["sha256"] for x in f}) > 1:
            problems.append(f"{rid}: {len(f)} different final versions")
    per_tf = {}
    for rid, v in by_rid.items():
        last = v[-1]
        k = (last["kind"], last["tf"])
        c = per_tf.setdefault(k, {"records": 0, "final": 0})
        c["records"] += 1
        c["final"] += bool(finals[rid])
    out = {"lines": len(rows), "records": len(by_rid), "problems": problems,
           "per_kind_tf": {f"{k}|{tf}": v for (k, tf), v in sorted(per_tf.items())}}
    if state_path:
        with open(state_path) as f:
            state = json.load(f)
        in_state = {f"{k}|{r['id']}": sha(r) for k, _, r in records(state)}
        missing = [rid for rid, h in in_state.items() if (rid, h) not in pairs]
        out["state_records"] = len(in_state)
        out["state_versions_not_logged"] = missing
        out["logged_not_in_state"] = sorted(set(by_rid) - set(in_state))
        problems += [f"{rid}: current version not in the log" for rid in missing]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--append", metavar="STORE")
    g.add_argument("--merge-ledger", nargs=2, metavar=("SRC", "DST"))
    g.add_argument("--verify", metavar="DIR")
    ap.add_argument("--state", help="alerts_state.json to check completeness against (with --verify)")
    a = ap.parse_args(argv)
    if a.append:
        res = append(a.append)
    elif a.merge_ledger:
        res = merge_ledger(*a.merge_ledger)
    else:
        res = verify(a.verify, a.state)
    print(json.dumps(res, indent=1))
    return 1 if res.get("problems") else 0


if __name__ == "__main__":
    sys.exit(main())
