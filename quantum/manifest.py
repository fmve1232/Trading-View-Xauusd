"""Data-versioning manifest for every pipeline run -- BOOKKEEPING ONLY.

The market-data store is pushed as one orphan commit per run (to keep the branch small), so
earlier versions of a bar are not kept there. This module records, on the never-force-pushed
`forward-ledger` branch, what the store held at each run:

  manifests/state.json       full map {file: [sha256, rows]} for the store as of this run; the
                             branch's git history keeps every earlier version of this file
  manifests/runs-YYYY-MM.jsonl  one line per run: time, GitHub run id, commit, freeze key,
                             tree hash (one SHA-256 over the whole store), the files changed, and
                             `env`: the Python / NumPy / pandas versions the run used (operator
                             approval 2026-11-13, audit F-03: the freeze key hashes source files
                             only, so a library upgrade would otherwise leave no trace)
  revisions/<series>/<bar month>/<run day>.csv  the OLD values of every bar that a later download
                             changed after that bar had closed (a forming bar finishing is not a
                             revision), beside its new values. One file per run day (2026-11-20): the
                             month files written before then (revisions/<series>/YYYY-MM.csv) are kept
                             as they are, but grew on every run to 62 MB, and GitHub refuses a file
                             over 100 MB, which would stop the ledger push. A run whose revision set is
                             byte-identical to an earlier run's set in the same day file is written as
                             one `repeat` line naming that run (Yahoo's GC=F / SI=F bars alternate
                             between two versions on most runs); read_revisions() expands it, so
                             nothing is lost. A set larger than MAX_REVISIONS_PER_FILE is one
                             `rebased` line with its count.
  `payloads` / `payload_artifact` in the run line (audit IA-12, 2026-11-14): SHA-256 and size of every
                             site payload this run published (site/data/*.json) and the name of the
                             Actions artifact that keeps their bytes (quantum-site.yml, 90 days by
                             default), so a past decision can be replayed from the exact payload and
                             the copy checked against this line (audit/tools/payload_archive_check.py)

So a counted trade can be traced to the exact bars the engine saw (the run's tree hash), and a
silently revised bar leaves a record instead of disappearing. Nothing here reads or changes
market data the engine uses: it is outside `holdout.ENGINE_SOURCES`, the pipeline does not import
it, and the workflow runs it as a separate, non-fatal step.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import platform
import subprocess
from datetime import datetime, timezone

import numpy as np
import pandas as pd

BAR_SEC = {"5m": 300, "15m": 900, "30m": 1800, "60m": 3600, "1h": 3600, "1d": 86400}
PRICE_COLS = ("open", "high", "low", "close")
MAX_REVISIONS_PER_FILE = 500      # beyond this, only the count is recorded (a re-based series)
REV_VALUES = [f"old_{c}" for c in PRICE_COLS] + [f"new_{c}" for c in PRICE_COLS]
REV_HEADER = ["bar_open", "run_utc"] + REV_VALUES + ["kind", "ref_run", "n_bars"]
FULL_KINDS = ("changed", "removed")


def env_versions() -> dict:
    """The interpreter and numeric libraries this process runs on. quantum-site.yml runs this module in the build job,
    on the same interpreter and installed packages as the pipeline step a few steps earlier, so these are the versions
    the engine used in this run. Bookkeeping only: not part of the freeze key (holdout.ENGINE_SOURCES is unchanged)."""
    return {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__}


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


def payload_digests(payload_dir: str) -> dict:
    """{file name: [sha256 of the bytes, size in bytes]} for every *.json the run published in payload_dir."""
    out = {}
    for name in sorted(os.listdir(payload_dir)):
        p = os.path.join(payload_dir, name)
        if not name.endswith(".json") or not os.path.isfile(p):
            continue
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        out[name] = [h.hexdigest(), os.path.getsize(p)]
    return out


def revision_path(ledger_dir: str, rel: str, stamp: str) -> str:
    """revisions/<series>/<bar month>/<run day>.csv for the store file `rel` (<series>/<YYYY-MM>.csv)."""
    return os.path.join(ledger_dir, "revisions", os.path.splitext(rel)[0], stamp[:10] + ".csv")


def _cell(v) -> str:
    if v is None or (isinstance(v, (float, np.floating)) and np.isnan(v)):
        return ""
    return f"{float(v):.6f}" if isinstance(v, (float, np.floating, int, np.integer)) else str(v)


def revision_rows(rev: pd.DataFrame) -> list[list[str]]:
    """A run's revision set as text rows in REV_HEADER order, without the run time (bar_open first)."""
    rows = []
    for bar, r in rev.iterrows():
        rows.append([str(bar)] + [_cell(r.get(c, np.nan)) for c in REV_VALUES] + [str(r["kind"]), "", ""])
    return rows


def write_revisions(path: str, rev: pd.DataFrame, stamp: str) -> str:
    """Append one run's revision set to its day file; returns how it was written (full / repeat / rebased)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    blank = [""] * len(REV_VALUES)
    sets: dict[str, list] = {}
    if os.path.exists(path):
        with open(path, newline="") as f:
            rd = csv.reader(f)
            assert next(rd) == REV_HEADER, path            # this writer's own files only
            for row in rd:
                if row[-3] in FULL_KINDS:
                    sets.setdefault(row[1], []).append(row[:1] + row[2:])
    if len(rev) > MAX_REVISIONS_PER_FILE:
        how, out = "rebased", [[str(rev.index[-1]), stamp] + blank + ["rebased", "", str(len(rev))]]
    else:
        body = revision_rows(rev)
        ref = next((run for run, rows in sets.items() if rows == body), None)
        if ref is not None:
            how, out = "repeat", [["", stamp] + blank + ["repeat", ref, str(len(body))]]
        else:
            how, out = "full", [r[:1] + [stamp] + r[1:] for r in body]
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        if new:
            w.writerow(REV_HEADER)
        w.writerows(out)
    return how


def read_revisions(path: str) -> pd.DataFrame:
    """Every revised bar of every run in one revision file, one row each, `repeat` lines expanded from the
    run they name. Reads both layouts: the day files (REV_HEADER) and the month files written before
    2026-11-20, whose header is whichever row came first (11 columns, or 3 when the file began with a
    re-based count), so a row's own width says which it is."""
    out = []
    with open(path, newline="") as f:
        rd = csv.reader(f)
        hdr = next(rd)
        if hdr == REV_HEADER:
            by_run: dict[str, list] = {}
            for row in rd:
                rec = dict(zip(REV_HEADER, row))
                if rec["kind"] == "repeat":
                    for r in by_run[rec["ref_run"]]:
                        out.append({**r, "run_utc": rec["run_utc"], "ref_run": rec["ref_run"]})
                    continue
                if rec["kind"] in FULL_KINDS:
                    by_run.setdefault(rec["run_utc"], []).append(rec)
                out.append(rec)
        else:
            for row in rd:
                if len(row) == 11:
                    out.append(dict(zip(REV_HEADER[:11], row)))
                elif len(row) == 3:
                    out.append({"bar_open": row[0], "run_utc": row[1], "kind": row[2]})
                else:
                    raise ValueError(f"{path}: a row of {len(row)} fields")
    df = pd.DataFrame(out).reindex(columns=REV_HEADER)
    for c in REV_VALUES:
        df[c] = pd.to_numeric(df[c].replace("", np.nan))
    for c in ("ref_run", "n_bars"):
        df[c] = df[c].astype(object).where(df[c].notna(), "")
    return df


def record(store_dir: str, ledger_dir: str, run_id: str = "", sha: str = "", freeze_key: str = "",
           now: datetime | None = None, payload_dir: str | None = None, artifact: str = "") -> dict:
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
    n_rev, n_forming, rev_files, rev_repeats = 0, 0, [], []
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
            if write_revisions(revision_path(ledger_dir, rel, stamp), rev, stamp) == "repeat":
                rev_repeats.append(rel)

    tree = tree_hash(state)
    with open(spath, "w") as f:
        json.dump({"run_utc": stamp, "tree_sha256": tree, "files": state}, f, indent=0, sort_keys=True)
    line = {"run_utc": stamp, "run_id": run_id, "commit": sha, "freeze_key": freeze_key, "tree_sha256": tree,
            "n_files": len(state), "changed": changed, "removed": removed,
            "revised_closed_bars": n_rev, "revised_files": rev_files, "revised_files_repeating": rev_repeats,
            "forming_bar_updates": n_forming,
            "env": env_versions()}
    if payload_dir and os.path.isdir(payload_dir):
        line["payloads"] = payload_digests(payload_dir)
        line["payload_artifact"] = artifact
    with open(os.path.join(mdir, f"runs-{now:%Y-%m}.jsonl"), "a") as f:
        f.write(json.dumps(line, sort_keys=True) + "\n")
    return line


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--store", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    ap.add_argument("--sha", default=os.environ.get("GITHUB_SHA", ""))
    ap.add_argument("--payloads", default=None, help="directory of the payloads this run published (site/data)")
    ap.add_argument("--artifact", default="", help="name of the Actions artifact that archives them")
    a = ap.parse_args()
    key = ""
    mp = os.path.join(a.store, "holdout_manifest.json")
    if os.path.exists(mp):
        with open(mp) as f:
            key = json.load(f).get("freeze_key", "")
    line = record(a.store, a.ledger, a.run_id, a.sha, key, payload_dir=a.payloads, artifact=a.artifact)
    print(f"manifest: tree {line['tree_sha256'][:16]} · {line['n_files']} files · {len(line['changed'])} changed · "
          f"{line['revised_closed_bars']} revised closed bars · {line['forming_bar_updates']} forming-bar updates · "
          + " ".join(f"{k} {v}" for k, v in line["env"].items())
          + (f" · {len(line['payloads'])} payloads -> {line['payload_artifact'] or 'no artifact'}" if "payloads" in line else ""))


if __name__ == "__main__":
    main()
