"""Collapse the ablation's changed signals into distinct ideas with the alerts' own REPEAT rule (read-only).

  python3 -I audit/tools/v2_ablation_ideas.py <v2_ablation_signals.csv> <out.json>

A signal repeats an earlier one in the same group (timeframe, change) when it has the same side, its bar opens within
4 hours of the idea's first signal and its entry is within $15 of that signal's entry (quantum/notify.py REPEAT_SEC /
REPEAT_USD; applied here within each group, not across all open plans, so it is an approximation). One outcome per idea:
the first signal's hypothetical +/-$13 result."""
import csv
import json
import sys
from collections import Counter

import pandas as pd

rows = list(csv.DictReader(open(sys.argv[1])))
out = {}
for tf in ("15m", "30m", "1h", "4h"):
    for grp in ("needs the feeds (removed when dropped)", "suppressed by the feeds (added when dropped)", ""):
        rs = sorted((r for r in rows if r["timeframe"] == tf and r["change"] == grp and (grp or r["in_baseline"] == "True")),
                    key=lambda r: r["bar_open"])
        ideas = []
        for r in rs:
            t = pd.Timestamp(r["bar_open"])
            if ideas and any(i["side"] == r["side"] and t - pd.Timestamp(i["bar_open"]) <= pd.Timedelta(hours=4)
                             and abs(float(r["entry"]) - float(i["entry"])) <= 15 for i in ideas[-6:]):
                continue
            ideas.append(r)
        key = f"{tf} | {grp or 'baseline'}"
        out[key] = {"signals": len(rs), "ideas": len(ideas), "signal_outcomes": dict(Counter(r["hypothetical_13"] for r in rs)),
                    "idea_outcomes": dict(Counter(r["hypothetical_13"] for r in ideas))}
        print(f"{key:58s} signals {len(rs):3d} -> ideas {len(ideas):3d} | idea outcomes {out[key]['idea_outcomes']}")
json.dump(out, open(sys.argv[2], "w"), indent=1)
