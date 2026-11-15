"""Partial-failure check after the pipeline step -- WARNINGS ONLY, never fails the run (audit IA-19, 2026-11-14).

quantum.pipeline exits 0 whenever at least one timeframe produced a payload, so a timeframe that failed (or a download
error) shows only inside site/data/index.json -> errors. This step turns each problem into a GitHub Actions ::warning
annotation and a line in the run summary, so a partial failure is visible on the run page. It reads index.json only:
outside holdout.ENGINE_SOURCES, imported by nothing, and the workflow runs it as a separate, non-fatal step.

  python -m quantum.run_check --index site/data/index.json --tfs 15m,30m,1h,4h,5m
"""
from __future__ import annotations

import argparse
import json
import os


def problems(index: dict | None, tfs: list[str]) -> list[str]:
    """Every reason the run is incomplete: the pipeline's own errors, timeframes without a payload, alerts not run."""
    if index is None:
        return ["index.json missing or unreadable: the pipeline published nothing"]
    errors = index.get("errors") or {}
    out = [f"{k}: {v}" for k, v in sorted(errors.items())]
    got = set(index.get("timeframes") or {})
    out += [f"{tf}: no payload this run" for tf in tfs if tf not in got and tf not in errors]
    if got and "alerts" not in index:
        out.append("alerts: the notifier did not run")
    return out


def _annotation(text: str) -> str:
    """One line, at most 300 characters, with the characters GitHub's workflow commands reserve escaped."""
    t = text.replace("\r", " ").replace("\n", " ")[:300]
    return t.replace("%", "%25").replace("::", ": :")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--index", default="site/data/index.json")
    ap.add_argument("--tfs", default="15m,30m,1h,4h,5m")
    a = ap.parse_args(argv)
    tfs = [x.strip() for x in a.tfs.split(",") if x.strip()]
    try:
        with open(a.index) as f:
            index = json.load(f)
    except (OSError, ValueError):
        index = None
    found = problems(index, tfs)
    for p in found:
        print(f"::warning title=pipeline partial failure::{_annotation(p)}", flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write("### Pipeline completeness\n\n" + ("\n".join(f"- {_annotation(p)}" for p in found) if found
                                                       else "- every timeframe published; no pipeline error") + "\n")
    print(f"run check: {len(found)} problem(s)" + ("" if found else " -- complete"))
    return 0                                                   # warnings only, never fails the run


if __name__ == "__main__":
    raise SystemExit(main())
