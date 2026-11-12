"""Summary tables of an aux_revision_ab.py run (read-only): per timeframe, the live decision, signal existence and
level changes, and the size of the changes in calibrated probability, scores and trade quality (treatment arm).

Usage: python audit/tools/aux_revision_summary.py <work dir of aux_revision_ab.py>"""
import json
import math
import os
import pickle
import sys
from datetime import datetime, timezone

import numpy as np

TFS = ["15m", "30m", "1h", "4h", "5m"]


def u(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M")


def size(a, b):
    a, b = np.array(a, dtype=float), np.array(b, dtype=float)
    d = np.abs(a - b)
    m = ~np.isnan(d)
    ch = d[m][d[m] > 1e-9]
    last = [None if math.isnan(x) else float(x) for x in (a[-1], b[-1])]
    return {"changed": int(len(ch)), "of": int(m.sum()), "median": float(np.median(ch)) if len(ch) else 0.0,
            "p95": float(np.percentile(ch, 95)) if len(ch) else 0.0, "max": float(ch.max()) if len(ch) else 0.0, "last": last}


def main():
    raw = pickle.load(open(os.path.join(sys.argv[1], "raw.pkl"), "rb"))
    out = {}
    for tf in TFS:
        A, B = raw[f"base|{tf}"], raw[f"swap|{tf}"]
        ra, rb = A["treatment"]["rows"], B["treatment"]["rows"]
        sig = lambda P: {(m["t"], m.get("dir")): m for m in P["payload"]["markers"] if m["type"] == "SIGNAL"}   # noqa: E731
        sa, sb = sig(A), sig(B)
        sl = [abs((sa[k].get("sl") or 0) - (sb[k].get("sl") or 0)) for k in set(sa) & set(sb) if sa[k].get("sl") != sb[k].get("sl")]
        ev = lambda R: [e for e in R["treatment"]["events"] if e.get("type") == "SIGNAL"]                  # noqa: E731
        out[tf] = {
            "live_decision": [A["treatment"]["last"].get("decision"), B["treatment"]["last"].get("decision")],
            "engine_signals": [len(ev(A)), len(ev(B))],
            "site_signals_only_base": [(u(t), d) for t, d in sorted(set(sa) - set(sb))],
            "site_signals_only_swap": [(u(t), d) for t, d in sorted(set(sb) - set(sa))],
            "site_signals_sl_changed": [len(sl), len(sa), max(sl) if sl else 0.0],
            **{k: size(ra[k], rb[k]) for k in ("cal_p_long", "bull", "bear", "tq") if k in ra},
            "bias_label_changed": int(sum(x != y for x, y in zip(ra["bias_label"], rb["bias_label"], strict=True))),
        }
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
