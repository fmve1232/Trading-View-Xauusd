#!/usr/bin/env python3
"""Input ORDER gate (v103 follow-up, F-A93): TradingView keeps a chart's saved input values BY POSITION, so a build that
inserts, removes or reorders inputs hands the operator's saved values to different inputs.

Found on the operator's v103 screenshot (2026-11-14): v103 inserted two LAYOUT switches before 159 existing Visuals
inputs; 123 of them changed position, and the chart showed the detail panel that v103's defaults switch off.

Rule: for every artefact, each input of the PREVIOUS build (the newest earlier commit whose file content differs from
the current file) keeps its position, name and type; new inputs are only appended after the last one. A build that
breaks the rule on purpose is listed in ACCEPTED with what the operator was told (a one-time "Reset settings").
Positive control: a new input inserted at the top is detected.
Usage: python3 audit/tools/input_order_check.py"""
import glob
import re
import subprocess
import sys

# file name -> commit whose reorder was accepted (the operator was asked to reset that indicator's settings once)
ACCEPTED = {"XAUUSD_Quantum_5_5_Visuals.pine": ("2801317ff", "v103 inserted the LAYOUT switches at the top; the operator "
                                                             "resets Visuals' settings once (Settings -> Defaults -> Reset settings)")}
fails = 0


def report(ok, msg):
    global fails
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {msg}")


def inputs(src):
    out = []
    for l in src.split("\n"):
        if l.lstrip().startswith("//"):
            continue
        m = re.match(r'^\s*(?:\w+\s+)?(\w+)\s*=\s*input(?:\.(\w+))?\(', l)
        if m:
            out.append((m.group(1), m.group(2) or "input"))
    return out


def git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True).stdout


def previous(path, cur):
    for h in git("log", "--format=%h", "--", path).split():
        old = git("show", f"{h}:{path}")
        if old and old != cur:
            return h, old
    return None, None


def compare(old, new):
    a, b = inputs(old), inputs(new)
    moved = [(k, a[k], b[k] if k < len(b) else None) for k in range(len(a)) if k >= len(b) or a[k] != b[k]]
    return a, b, moved


if __name__ == "__main__":
    for path in sorted(glob.glob("artefacts/*.pine")):
        name = path.split("/")[-1]
        cur = open(path, encoding="utf-8").read()
        h, old = previous(path, cur)
        if old is None:
            report(True, f"{name}: no earlier build to compare")
            continue
        a, b, moved = compare(old, cur)
        acc = ACCEPTED.get(name)
        head = git("log", "-1", "--format=%h", "--", path).strip()
        if moved and acc and head.startswith(acc[0][:7]) and cur == git("show", f"{acc[0]}:{path}"):
            print(f"  NOTE  {name}: {len(moved)} of {len(a)} inputs moved vs {h} -- ACCEPTED: {acc[1]}")
            continue
        report(not moved, f"{name}: {len(a)} inputs of the previous build ({h}) keep their positions; {len(b) - len(a)} "
               "appended" + ("" if not moved else f"; MOVED {len(moved)}, first {moved[:3]}"))
    V = open("artefacts/XAUUSD_Quantum_5_5_Visuals.pine", encoding="utf-8").read()
    i = V.index("grpTm = ")
    mut = V[:i] + 'ctlX = input.bool(true, "control")\n' + V[i:]
    report(bool(compare(V, mut)[2]), "control: an input inserted before existing ones is detected")
    print(f"RESULT: {'PASS' if not fails else 'FAIL'} -- input positions read from the Pine text; how TradingView maps saved "
          "values is the platform's (keyed by position)")
    sys.exit(1 if fails else 0)
