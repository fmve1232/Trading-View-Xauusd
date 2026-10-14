#!/usr/bin/env python3
"""EdgeCases citations are code anchors (F-A43, closed v54): every M`<text>` in EdgeCases.pine must match
exactly ONE line of the current Master (comments ignored). Fails otherwise, so a citation cannot drift
silently the way line numbers did twice. Usage: python3 audit/tools/edgecase_cites.py"""
import re
import sys

E = "artefacts/XAUUSD_Quantum_5_0_EdgeCases.pine"
M = "artefacts/XAUUSD_Quantum_5_0_Master.pine"
code = [l.split("//")[0] if '"' not in l.split("//")[0] else l for l in open(M, encoding="utf-8").read().split("\n")]
anchors = re.findall(r"M`([^`]+)`", open(E, encoding="utf-8").read())
anchors = [a for a in anchors if a != "<text>"]
bad = 0
for a in anchors:
    hits = [i + 1 for i, l in enumerate(code) if a in l]
    if len(hits) != 1:
        bad += 1
        print(f"FAIL  M`{a}` matches {len(hits)} Master lines {hits[:5]}")
lines_left = len(re.findall(r"\bL\d{3,4}\b", open(E, encoding="utf-8").read()))
if lines_left:
    bad += 1
    print(f"FAIL  {lines_left} bare line-number citation(s) left in EdgeCases")
if bad:
    sys.exit(1)
print(f"PASS  EdgeCases citations: {len(anchors)} code anchors, each matches exactly one Master line; no bare line numbers")
