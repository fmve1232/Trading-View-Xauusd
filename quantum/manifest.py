"""Data-versioning manifest for every pipeline run -- BOOKKEEPING ONLY.

The market-data store is pushed as one orphan commit per run (to keep the branch small), so
earlier versions of a bar are not kept there. This module records, on the never-force-pushed
`forward-ledger` branch, what the store held at each run:

  manifests/state.json       full map {file: [sha256, rows]} for the store as of this run; the
                             branch's git history keeps every earlier version of this file
  manifests/runs-YYYY-MM.jsonl  one line per run: time, GitHub run id, commit, freeze key,
                             tree hash (one SHA-256 over the whole store) and the files changed
  revisions/<series>/YYYY-MM.csv  the OLD values of every bar that a later download changed
                             after that bar had closed (a forming bar finishing is not a revision)

So a counted trade can be traced to the exact bars the engine saw (the run's tree hash), and a
silently revised bar leaves a record instead of disappearing. Nothing here reads or changes
market data the engine uses: it is outside `holdout.ENGINE_SOURCES`, the pipeline does not import
it, and the workflow runs it as a separate, non-fatal step.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
from datetime import datetime, timezone

import numpy as np
import pandas as pd

BAR_SEC = {"5m": 300, "15m": 900, "60m": 3600, "1h": 3600, "1d": 86400}
PRICE_COLS = ("open", "high", "low", "close")
MAX_REVISIONS_PER_FILE = 500      # beyond this, only the count is recorded (a re-based series)


def file_digest(path: str) -> tuple[str, int]:
    h = hashlib.sha256()
    rows = 0
    with open(path, "rb") as f:
        for line in f:
            h.update(line)
            rows += 1
    return h.hexdigest(), max(rows - 1, 0)          # CSV: minus the header


def scan(store_dir: str) -> dict:
    out = {}
    for root, dirs, files in os.walk(store_dir):
        dirs[:] = sorted(d for d in dirs if d != ".git")
        for fn in sorted(files):
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, store_dir).replace(os.sep, "/")
            sha, rows = file_digest(p)
            out[rel] = [sha, rows]
    return out


def tree_hash(state: dict) -> str:
    h = hashlib.sha256()
    for rel in sorted(state):
        h.update(f"{rel}\0{state[rel][0]}\n".encode())
    return h.hexdigest()


def _git(store_dir: str, *args: str) -> str | None:
    if not os.path.isdir(os.path.join(store_dir, ".git")):
        return None
    r = subprocess.run(["git", "-C", store_dir, *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def _bar_sec(rel: str) -> int | None:
    series = rel.split("/", 1)[0]
    return BAR_SEC.get(series.rsplit("_", 1)[-1]) if "_" in series else None


def revisions(old_csv: str, new_csv: str, bar_sec: int, prev_commit_utc: pd.Timestamp) -> tuple[pd.DataFrame, int]:
    """Bars that had CLOSED by the previous snapshot and whose prices differ now (or vanished).
    Returns (old rows with the new values beside them, number of forming-bar updates skipped)."""
    old = pd.read_csv(io.StringIO(old_csv), index_col=0)
    new = pd.read_csv(io.StringIO(new_csv), index_col=0)
    cols = [c for c in PRICE_COLS if c in old.columns]
    if not cols:
        return pd.DataFrame(), 0
    closed = pd.to_datetime(old.index, utc=True) + pd.Timedelta(seconds=bar_sec) <= prev_commit_utc
    common = old.index.intersection(new.index)
    o, n = old.loc[common, cols].astype(float), new.loc[common, cols].astype(float)
    diff = ~np.isclose(o.to_numpy(), n.to_numpy(), rtol=0.0, atol=1e-6, equal_nan=True)
    changed = pd.Series(diff.any(axis=1), index=common)
    gone = old.index.difference(new.index)
    is_closed = pd.Series(closed, index=old.index)
    rev_idx = [i for i in common[changed.to_numpy()] if is_closed[i]] + [i for i in gone if is_closed[i]]
    forming = int(changed.sum()) + len(gone) - len(rev_idx)
    if not rev_idx:
        return pd.DataFrame(), forming
    rows = old.loc[rev_idx, cols].add_prefix("old_")
    nv = new.reindex(rev_idx)[cols].add_prefix("new_")
    out = pd.concat([rows, nv], axis=1)
    out["kind"] = ["removed" if i in gone else "changed" for i in rev_idx]
    return out, forming


def record(store_dir: str, ledger_dir: str, run_id: str = "", sha: str = "", freeze_key: str = "",
           now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    state = scan(store_dir)
    mdir = os.path.join(ledger_dir, "manifests")
    os.makedirs(mdir, exist_ok=True)
    spath = os.path.join(mdir, "state.json")
    prev = {}
    if os.path.exists(spath):
        with open(spath) as f:
            prev = json.load(f).get("files", {})
    changed = sorted(k for k in state if prev.get(k, [None])[0] != state[k][0])
    removed = sorted(k for k in prev if k not in state)

    # revisions: compare each changed CSV with its version in the previous store snapshot
    n_rev, n_forming, rev_files = 0, 0, []
    ct = _git(store_dir, "log", "-1", "--format=%ct")
    prev_commit = pd.Timestamp(int(ct.strip()), unit="s", tz="UTC") if ct and ct.strip() else None
    if prev_commit is not None:
        for rel in changed:
            bs = _bar_sec(rel)
            if not rel.endswith(".csv") or bs is None:
                continue
            old_csv = _git(store_dir, "show", f"HEAD:{rel}")
            if not old_csv:
                continue                                    # a new month file: nothing to revise
            with open(os.path.join(store_dir, rel)) as f:
                new_csv = f.read()
            try:
                rev, forming = revisions(old_csv, new_csv, bs, prev_commit)
            except Exception:                               # noqa: BLE001 - bookkeeping never fails the run
                continue
            n_forming += forming
            if rev.empty:
                continue
            n_rev += len(rev)
            rev_files.append(rel)
            rdir = os.path.join(ledger_dir, "revisions", os.path.dirname(rel))
            os.makedirs(rdir, exist_ok=True)
            rpath = os.path.join(ledger_dir, "revisions", rel)
            if len(rev) > MAX_REVISIONS_PER_FILE:
                rev = pd.DataFrame({"kind": [f"{len(rev)} closed bars revised (series re-based); not listed"]},
                                   index=[rev.index[-1]])
            rev.insert(0, "run_utc", stamp)
            rev.index.name = "bar_open"
            rev.to_csv(rpath, mode="a", header=not os.path.exists(rpath), float_format="%.6f")

    tree = tree_hash(state)
    with open(spath, "w") as f:
        json.dump({"run_utc": stamp, "tree_sha256": tree, "files": state}, f, indent=0, sort_keys=True)
    line = {"run_utc": stamp, "run_id": run_id, "commit": sha, "freeze_key": freeze_key, "tree_sha256": tree,
            "n_files": len(state), "changed": changed, "removed": removed,
            "revised_closed_bars": n_rev, "revised_files": rev_files, "forming_bar_updates": n_forming}
    with open(os.path.join(mdir, f"runs-{now:%Y-%m}.jsonl"), "a") as f:
        f.write(json.dumps(line, sort_keys=True) + "\n")
    return line


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--store", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    ap.add_argument("--sha", default=os.environ.get("GITHUB_SHA", ""))
    a = ap.parse_args()
    key = ""
    mp = os.path.join(a.store, "holdout_manifest.json")
    if os.path.exists(mp):
        with open(mp) as f:
            key = json.load(f).get("freeze_key", "")
    line = record(a.store, a.ledger, a.run_id, a.sha, key)
    print(f"manifest: tree {line['tree_sha256'][:16]} · {line['n_files']} files · {len(line['changed'])} changed · "
          f"{line['revised_closed_bars']} revised closed bars · {line['forming_bar_updates']} forming-bar updates")


if __name__ == "__main__":
    main()
