#!/usr/bin/env python3
"""Build artefacts/XAUUSD_Quantum_5_0_Brief.pine from the Treatment twin's engine (v52).

The website's Market Brief (the system of record, A7) on the TradingView chart. The Master and
Diagnostics have no token room, so the brief lives in its own companion. Everything outside
`// DIAG-BEGIN` / `// DIAG-END` fences is the Strategy engine verbatim (apart from the declaration
line and comments); audit/tools/diag_parity.py enforces it, as for Diagnostics.

The playbook is the website's arm H4 rule (quantum/arm_h4.py on the default branch), ported
constant for constant; audit/tools/brief_trace.py executes the Pine below against a Python copy
of that rule. Display only: no gate, no order, and the Master's DECISION is the rule.
"""
SRC = "artefacts/XAUUSD_Quantum_5_0_Strategy.pine"
DST = "artefacts/XAUUSD_Quantum_5_0_Brief.pine"

L = open(SRC, encoding="utf-8").read().split("\n")
cut = next(i for i, l in enumerate(L) if l.startswith("bool _costModelValid"))
L = L[:cut]
while L and (L[-1].strip() == "" or L[-1].lstrip().startswith("//")):
    L.pop()


def at(prefix):
    hits = [i for i, l in enumerate(L) if l.startswith(prefix)]
    assert len(hits) == 1, (prefix, len(hits))
    return hits[0]


ref = L[3]
body = "// ║  BUILD STAMP — this file last CHANGED in v83   (news window: NY time)"
assert len(body) < len(ref), "stamp too long"
L[2] = body + " " * (len(ref) - len(body) - 1) + "║"
i = at('strategy("XAUUSD Quantum 5.0 — Treatment"')
L[i] = ('indicator("XAUUSD Quantum 5.0 — Brief", overlay=true, max_lines_count=500, '
        'max_labels_count=500, max_boxes_count=500, max_bars_back=5000)')
i = at("// FILE ROLE: A/B TREATMENT ARM")
L[i] = ("// FILE ROLE: MARKET BRIEF COMPANION — display only, trades nothing. The engine below is the "
        "Treatment twin's, verbatim (audit/tools/diag_parity.py); the brief panel is appended.")

PANEL = open(__file__.replace("build_brief.py", "brief_panel.pine"), encoding="utf-8").read()
out = "\n".join(L) + "\n" + PANEL
open(DST, "w", encoding="utf-8").write(out)
print(f"wrote {DST}: {out.count(chr(10))} lines")
