"""Files, Python functions and commits changed by each pull request or branch, from git alone (read-only; mandate
2026-11-28, Part 6 items 4 and 5). Nothing is typed in: every entry comes from `git diff`, `git log` and the files'
own syntax trees.

  python audit/tools/change_inventory.py --repo . --json out.json \
      --merged <first merge>..<last merge> [--open name=<ref> ...] [--base <production ref>]

--merged: every first-parent merge commit in the range is one merged pull request (its diff = merge^1..merge).
--open:   each branch's diff against its merge-base with --base (default: the production branch).
A function counts as changed when its source text differs between the two versions, or it exists in one only.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess


def git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True).stdout


def show(repo: str, rev: str, path: str) -> str | None:
    r = subprocess.run(["git", "-C", repo, "show", f"{rev}:{path}"], check=False, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def functions(src: str | None) -> dict[str, str]:
    """Qualified name -> source text of every function and method in a Python file (empty if absent or unparsable)."""
    if not src:
        return {}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {}
    out = {}

    def walk(node, prefix=""):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out[prefix + ch.name] = ast.get_source_segment(src, ch) or ""
                walk(ch, prefix + ch.name + ".")
            elif isinstance(ch, ast.ClassDef):
                walk(ch, prefix + ch.name + ".")
    walk(tree)
    return out


def diff(repo: str, a: str, b: str) -> dict:
    files = []
    for line in git(repo, "diff", "--name-status", "--no-renames", a, b).splitlines():
        st, path = line.split("\t", 1)
        entry = {"status": st, "path": path}
        if path.endswith(".py"):
            fa, fb = functions(show(repo, a, path)), functions(show(repo, b, path))
            entry["functions_added"] = sorted(set(fb) - set(fa))
            entry["functions_removed"] = sorted(set(fa) - set(fb))
            entry["functions_changed"] = sorted(n for n in set(fa) & set(fb) if fa[n] != fb[n])
        files.append(entry)
    stat = git(repo, "diff", "--shortstat", a, b).strip()
    return {"files": files, "shortstat": stat}


def merged(repo: str, rng: str) -> list[dict]:
    out = []
    lo, hi = rng.split("..")
    for line in git(repo, "log", "--first-parent", "--merges", "--format=%H%x09%cI%x09%s", f"{lo}^..{hi}").splitlines():
        h, when, subj = line.split("\t")
        m = re.search(r"#(\d+)", subj)
        d = diff(repo, f"{h}^1", h)
        out.append({"pr": int(m.group(1)) if m else None, "merge": h[:9], "merged_utc": when, "subject": subj, **d,
                    "commits": [c for c in git(repo, "log", "--format=%h %cI %s", f"{h}^1..{h}^2").splitlines()]})
    return out


def opened(repo: str, name: str, ref: str, base: str) -> dict:
    mb = git(repo, "merge-base", base, ref).strip()
    return {"name": name, "ref": ref, "head": git(repo, "rev-parse", "--short=9", ref).strip(), "merge_base": mb[:9],
            **diff(repo, mb, ref), "commits": git(repo, "log", "--format=%h %cI %s", f"{mb}..{ref}").splitlines()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--json", required=True)
    ap.add_argument("--merged", required=True)
    ap.add_argument("--open", action="append", default=[])
    ap.add_argument("--base", default="origin/claude/audit-prompt-real-artefacts-nekqv6")
    a = ap.parse_args(argv)
    out = {"base": a.base, "base_head": git(a.repo, "rev-parse", "--short=9", a.base).strip(),
           "merged": merged(a.repo, a.merged),
           "open": [opened(a.repo, *x.split("=", 1), a.base) for x in a.open]}
    with open(a.json, "w") as f:
        json.dump(out, f, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
