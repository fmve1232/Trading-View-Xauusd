"""Registration chronology from GitHub's own push times (audit gap GA-06; operator next phase item 9). READ ONLY.

  python3 audit/tools/registration_chronology.py --repo <clone, every branch fetched> [--owner O --name R] [--json out]

A commit's author and committer dates are set by whoever makes it, so they prove nothing about order. GitHub records
when each push (and each pull-request merge) reached it: the repository activity API (`GET /repos/{o}/{r}/activity`),
which this tool reads for every ref, deleted branches included. A commit's first server time is the time of the
earliest recorded push that brought it to GitHub.

For each registration file (research/registrations/*.json on any branch named in lineage.BRANCHES):
  T_reg   the first server time of the commit that added it (the earliest over branches);
  T_code  the first server time of the first commit whose added lines DEFINE the study in code (quantum/,
          research/tools/, audit/tools/): `REG = "<id>"`, `<X>_ID = "<id>"`, or a trial record `"phase": "<id>"`;
  T_res   the first server time of the first result: the commit that added the study's first trial line
          (research/trials.jsonl), its first research/results/<id>_*.json, or research/<ID>_RESULTS.md;
  verdict, on the earlier of T_code and T_res (the first evidence that the work had started)
    BEFORE       the registration was on GitHub first
    SAME_PUSH    both reached GitHub in one push: only the commit order (parent links) separates them
    AFTER        code or a result was on GitHub before the registration
    NO_EVIDENCE  no code literal and no result found (a study not run, an amendment, or an id the code never quotes)
    NOT_FOUND    no recorded push contains the registration commit (or the first evidence commit): pushed before the
                 activity history begins, or its branch history was rewritten
The forward ledger itself began on 22 Nov 2026; forward records before that lived in the market-data store, which is
replaced every run and keeps no history, so forward tests are judged by their code, not by their records.
Nothing is changed, fetched into the repo or pushed; the only network calls are GET requests to the activity API.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lineage

ZERO = "0" * 40
SKIP_REFS = ("refs/heads/market-data",)              # one orphan commit replaced every run: nothing to resolve locally
# a registration whose study is logged under another name in research/trials.jsonl (evidence in the comment)
ALIAS = {"B4-RN-V1": ["B4-V"],                      # "Round-number crossing continuation (Osler 2003), one validation test"
         "B31b-W8-cost": ["B31b-W8"]}               # the W8 cost amendment, "committed_before_any_W8_run"
FORWARD = {"B9-GRAB-FWD", "B15-ENGINE-FWD", "B15b-ENGINE-FWD", "B24-CONFIRM-FWD", "B31b-SHADOW-FWD"}   # labels only


def git(repo: str, *a: str) -> str:
    r = subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, check=False)
    return r.stdout if r.returncode == 0 else ""


def activities(owner: str, name: str) -> list[dict]:
    import requests
    h = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    url, params, out = f"https://api.github.com/repos/{owner}/{name}/activity", {"per_page": 100, "direction": "asc"}, []
    while url:
        r = requests.get(url, params=params, headers=h, timeout=30)
        r.raise_for_status()
        out += r.json()
        url, params = r.links.get("next", {}).get("url"), None
    return out


def first_push(repo: str, acts: list[dict], needed: set[str]) -> tuple[dict, dict]:
    """commit -> (server time, ref, activity type) of the earliest recorded push that brought it to GitHub."""
    found, stats = {}, {"activities": len(acts), "skipped_refs": 0, "unresolved": 0}
    for a in sorted(acts, key=lambda x: x["timestamp"]):
        if a.get("ref") in SKIP_REFS:
            stats["skipped_refs"] += 1
            continue
        after, before = a.get("after"), a.get("before")
        if not after or after == ZERO or not (needed - found.keys()):
            continue
        rng = [after] if not before or before == ZERO else [after, f"^{before}"]
        intro = git(repo, "rev-list", *rng).split()
        if not intro:
            stats["unresolved"] += 1
            continue
        for c in needed.intersection(intro) - found.keys():
            found[c] = {"utc": a["timestamp"], "ref": a.get("ref"), "type": a.get("activity_type")}
    return found, stats


def registration_adds(repo: str, branches: list[str]) -> dict:
    out: dict = {}
    for b in branches:
        for path in git(repo, "ls-tree", "--name-only", f"{b}:research/registrations").split():
            if path.endswith(".json"):
                for c in git(repo, "log", "--full-history", "--diff-filter=A", "--format=%H", b, "--",
                             f"research/registrations/{path}").split():
                    out.setdefault(path, {}).setdefault(c, set()).add(lineage.short(b))
    return out


def _studies_at(repo: str, rev: str, cache: dict) -> set:
    if rev not in cache:
        st = set()
        for ln in git(repo, "show", f"{rev}:research/trials.jsonl").splitlines():
            try:
                st.add(lineage.study(json.loads(ln)))
            except ValueError:
                continue
        cache[rev] = st
    return cache[rev]


def study_firsts(repo: str, branches: list[str]) -> dict:
    """study -> {commit: ""} of every non-merge commit (full history, all branches) whose version of the trial log
    holds the study and whose parent's does not: the commits that wrote a study's first line. Path-limited history
    simplification is off, so a merge never stands in for the commit that did the work."""
    cache, out = {}, {}
    for c in git(repo, "log", "--full-history", "--no-merges", "--format=%H %P", *branches, "--", "research/trials.jsonl").splitlines():
        c, *par = c.split()
        new = _studies_at(repo, c, cache) - (_studies_at(repo, par[0], cache) if par else set())
        for s in new:
            out.setdefault(s, {})[c] = ""
    return out


CODE_PATHS = ("quantum", "research/tools", "audit/tools")


def defines(sid: str) -> re.Pattern:
    """An added line that makes the id the code's own study: `REG = "B30"`, `GRAB_ID = "B9-GRAB-FWD"`, or a trial record
    written as `"phase": "B30"`. A mere mention (a label in a tuple, a comment) does not count: B25's entry-delay arms
    are called "B10", "B30", ..., which are not the studies B10 and B30."""
    q = re.escape(sid)
    return re.compile(r'^\+.*(?:\b[A-Z0-9_]*(?:REG|STUDY|ID|REGISTRATION)[A-Z0-9_]*(?:\s*,\s*[A-Z0-9_]+)*\s*=\s*["\']'
                      + q + r'["\']'
                      r'|["\'](?:phase|study|registration|reg)["\']\s*:\s*["\']' + q + r'["\'])', re.MULTILINE)


def code_firsts(repo: str, branches: list[str], sid: str) -> dict:
    """{commit: ""} of every non-merge commit (full history, all branches) whose added lines define the study in code;
    the earliest push among them is the start of the code."""
    rx, out = defines(sid), {}
    for c in git(repo, "log", "--full-history", "--no-merges", "--format=%H", f'-S"{sid}"', *branches, "--", *CODE_PATHS).split():
        if rx.search(git(repo, "show", "--format=", c, "--", *CODE_PATHS)):
            out[c] = ""
    return out


def norm(x: str) -> str:
    return x.lower().replace("-", "_")


def result_files(repo: str, branches: list[str], names: list[str]) -> dict:
    """{commit: branches} of the commits that added a results file of the study (research/results/<id>_*.json or
    research/<ID>_RESULTS.md; never a plan, design or registration document)."""
    pre = [norm(n) + "_" for n in names]
    out = {}
    for b in branches:
        files = git(repo, "ls-tree", "-r", "--name-only", b, "research").split()
        for f in files:
            base = norm(os.path.basename(f))
            ok = (f.startswith("research/results/") and f.endswith(".json")) or base.endswith("_results.md")
            if ok and any(base.startswith(p) for p in pre):
                for c in git(repo, "log", "--full-history", "--no-merges", "--diff-filter=A", "--format=%H", b, "--", f).split():
                    out.setdefault(c, set()).add(lineage.short(b))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--owner", default="fmve1232")
    ap.add_argument("--name", default="Trading-View-Xauusd")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    branches = [b for b in lineage.BRANCHES if git(a.repo, "rev-parse", "--verify", "-q", b)]
    regs, studies = registration_adds(a.repo, branches), study_firsts(a.repo, branches)
    meta = {}
    for path in regs:
        body = {}
        for b in branches:
            txt = git(a.repo, "show", f"{b}:research/registrations/{path}")
            if txt:
                try:
                    body = json.loads(txt)
                except ValueError:
                    body = {}
                break
        rid = path[:-5]
        sid = str(body.get("id") or rid)
        names = ALIAS.get(rid, [sid])
        res = {c: v for s in names for c, v in studies.get(s, {}).items()}
        res.update(result_files(a.repo, branches, names))
        meta[path] = {"rid": rid, "sid": sid, "names": names, "body": body, "code": code_firsts(a.repo, branches, sid), "res": res}
    needed = ({c for v in regs.values() for c in v} | {c for m in meta.values() for c in m["code"]}
              | {c for m in meta.values() for c in m["res"]})
    acts = activities(a.owner, a.name)
    found, stats = first_push(a.repo, acts, needed)
    stats["history_from"] = min((x["timestamp"] for x in acts), default=None)
    stats["history_to"] = max((x["timestamp"] for x in acts), default=None)

    def earliest(commits) -> dict | None:
        ts = [dict(found[c], commit=c[:9]) for c in commits if c in found]
        return min(ts, key=lambda x: x["utc"]) if ts else None

    rows = []
    for path, adds in sorted(regs.items()):
        m = meta[path]
        reg, code, res = earliest(adds), earliest(m["code"]), earliest(m["res"])
        ev_commits = set(m["code"]) | set(m["res"])
        first = min([x for x in (code, res) if x], key=lambda x: x["utc"], default=None)
        if reg is None:
            v = "NOT_FOUND"
        elif not ev_commits:
            v = "NO_EVIDENCE"
        elif first is None:
            v = "NOT_FOUND"
        elif reg["utc"] < first["utc"]:
            v = "BEFORE"
        elif reg["utc"] == first["utc"]:
            v = "SAME_PUSH"
        else:
            v = "AFTER"
        dag = None
        if v == "SAME_PUSH":
            rc = [c for c in adds if c in found]
            xc = [c for c in ev_commits if c in found and found[c]["utc"] == first["utc"]]
            dag = any(subprocess.run(["git", "-C", a.repo, "merge-base", "--is-ancestor", r, x], check=False).returncode == 0
                      for r in rc for x in xc)
        rows.append({"registration": m["rid"], "id": m["sid"], "kind": "forward" if m["sid"] in FORWARD else "study",
                     "result_names": m["names"],
                     "created_utc_in_file": m["body"].get("created_utc") or m["body"].get("registered_utc"),
                     "registration_first_push": reg, "first_code_push": code, "first_result_push": res, "verdict": v,
                     "registration_commit_is_ancestor_of_first_evidence": dag,
                     "hours_registration_to_first_evidence": (round((_t(first["utc"]) - _t(reg["utc"])) / 3600, 2)
                                                              if reg and first else None)})
    out = {"activity": stats, "branches": [lineage.short(b) for b in branches], "registrations": rows,
           "counts": {k: sum(1 for r in rows if r["verdict"] == k) for k in ("BEFORE", "SAME_PUSH", "AFTER", "NO_EVIDENCE", "NOT_FOUND")}}
    if a.json:
        with open(a.json, "w") as f:
            json.dump(out, f, indent=1)
    print(f"activity {stats}")
    for r in rows:
        rp, cp, xp = r["registration_first_push"], r["first_code_push"], r["first_result_push"]
        print(f"{r['registration']:20s} {r['verdict']:11s} reg {rp['utc'] if rp else '-':20s} code {cp['utc'] if cp else '-':20s} "
              f"result {xp['utc'] if xp else '-':20s} gap {r['hours_registration_to_first_evidence']} h; file date "
              f"{r['created_utc_in_file']}" + (f"; reg commit ancestor of first evidence: "
                                               f"{r['registration_commit_is_ancestor_of_first_evidence']}" if r["verdict"] == "SAME_PUSH" else ""))
    print("counts", out["counts"])
    return 0


def _t(s: str) -> float:
    from datetime import datetime
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


if __name__ == "__main__":
    raise SystemExit(main())
