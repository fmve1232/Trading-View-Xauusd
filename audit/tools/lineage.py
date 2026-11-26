"""Research lineage across every branch (read-only; audit GA-01 / GA-02, mandate §4).

  python3 audit/tools/lineage.py --repo <clone with the branches fetched> --out research/lineage

Reads, on each branch named below (or --branches), research/trials.jsonl and research/registrations/*.json through
`git show`; it checks nothing out and changes no branch. Writes:
  trials_union.jsonl     every distinct trial record once (by SHA-1 of its line), with the branches it was found on;
                         the original lines are untouched on their branches
  partition_access.json  per study and partition: trial lines, first and last record time, branches
  registrations.json     per registration file: the branches holding it, the commit that added it on each, and its
                         committer date (author-set, so evidence of order only together with GitHub's own push times)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections import defaultdict

P = "origin/claude/session-01fdjaothuvhxscxtl7ysa-y3n4w4-"
BRANCHES = (["origin/claude/audit-prompt-real-artefacts-nekqv6"]
            + [P + b for b in ("w3-liquidity", "w4-research", "w5-entry", "w7-study", "w8-quality", "w11-scoreboard",
                               "w12-session-sweeps", "w13-entry-precision", "b30-confirmation", "b31-opportunity",
                               "b31b-w1", "b31b-w2", "remediation")]
            + ["origin/claude/research-phase-c", "origin/claude/research-phase-d", "origin/claude/research-sym15"])
SEALED = ("validation", "holdout")


def git(repo: str, *a: str) -> str:
    r = subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, check=False)
    return r.stdout if r.returncode == 0 else ""


def short(b: str) -> str:
    return b.replace("origin/", "").replace("claude/session-01fdjaothuvhxscxtl7ysa-y3n4w4-", "")


def study(d: dict) -> str:
    return str(d.get("study") or d.get("phase") or d.get("registration") or d.get("reg") or (d.get("id") or "?").split("-")[0])


def part(d: dict) -> str:
    return str(d.get("part") or d.get("partition") or "-")


def build(repo: str, branches: list[str]) -> dict:
    recs, regs = {}, defaultdict(dict)
    for b in branches:
        if not git(repo, "rev-parse", "--verify", "-q", b):
            continue
        for line in git(repo, "show", f"{b}:research/trials.jsonl").splitlines():
            line = line.strip()
            if line:
                h = hashlib.sha1(line.encode()).hexdigest()
                recs.setdefault(h, {"sha1": h, "branches": [], "record": json.loads(line)})["branches"].append(short(b))
        for path in git(repo, "ls-tree", "--name-only", f"{b}:research/registrations").split():
            if not path.endswith(".json"):
                continue
            full = f"research/registrations/{path}"
            added = git(repo, "log", "--diff-filter=A", "--format=%h %cI", b, "--", full).split()
            regs[path][short(b)] = {"added_commit": added[-2] if len(added) >= 2 else None,
                                    "added_committer_date": added[-1] if added else None}
    access = defaultdict(lambda: {"lines": 0, "first_utc": None, "last_utc": None, "branches": set()})
    for r in recs.values():
        d = r["record"]
        a = access[(study(d), part(d))]
        u = str(d.get("utc") or "")
        a["lines"] += 1
        a["first_utc"] = min(a["first_utc"] or u, u) if u else a["first_utc"]
        a["last_utc"] = max(a["last_utc"] or u, u) if u else a["last_utc"]
        a["branches"].update(r["branches"])
    return {"records": sorted(recs.values(), key=lambda r: str(r["record"].get("utc") or "")),
            "access": {f"{s}|{p}": {**v, "branches": sorted(v["branches"])} for (s, p), v in sorted(access.items())},
            "registrations": dict(sorted(regs.items()))}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--out", required=True)
    ap.add_argument("--branches", nargs="*", default=BRANCHES)
    a = ap.parse_args(argv)
    r = build(a.repo, a.branches)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "trials_union.jsonl"), "w") as f:
        f.writelines(json.dumps(x, sort_keys=True) + "\n" for x in r["records"])
    with open(os.path.join(a.out, "partition_access.json"), "w") as f:
        json.dump(r["access"], f, indent=1)
    with open(os.path.join(a.out, "registrations.json"), "w") as f:
        json.dump(r["registrations"], f, indent=1)
    sealed = {k: v for k, v in r["access"].items() if k.rsplit("|", 1)[1] in SEALED}
    print(f"{len(r['records'])} distinct trial records; {len(r['registrations'])} registration files; "
          f"studies that read validation or holdout: {sorted({k.split('|')[0] for k in sealed})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
