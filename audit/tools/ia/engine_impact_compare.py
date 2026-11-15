"""Compare two f_impact.py dumps (A = before, B = after): signals kept / removed / added per timeframe, where the added
ones came from (the A engine's VETO reason on that bar), weekly-level and trade-quality differences, and ideas per day
after the live REPEAT rule on the alerted timeframes.  python audit/tools/ia/engine_impact_compare.py A.json B.json [label]"""
import json
import sys
from collections import Counter

A, B = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
label = sys.argv[3] if len(sys.argv) > 3 else ""
print(f"## {label}  A key {A['freeze_key']}  ->  B key {B['freeze_key']}")
print("| TF | bars | days | A signals | B signals | kept | removed | added | added: A vetoed for | PWH/PWL bars differing (max $) | TQ bars differing | TQ-floor flips |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")


def ideas(evs, sec):
    kept = []
    for e in sorted(evs, key=lambda z: z["t"]):
        if any(k["dir"] == e["dir"] and e["t"] - k["t"] <= 4 * 3600 and abs(e["px"] - k["px"]) <= 15.0 for k in kept[-50:]):
            continue
        kept.append(e)
    return kept


pooled = {"A": [], "B": []}
SEC = {"15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "5m": 300}
for tf in A["tf"]:
    a, b = A["tf"][tf], B["tf"][tf]
    assert a["t"] == b["t"], tf
    sa = {(e["t"], e["dir"]) for e in a["events"] if e["type"] == "SIGNAL"}
    sb = {(e["t"], e["dir"]) for e in b["events"] if e["type"] == "SIGNAL"}
    va = {(e["t"], e["dir"]): e["why"] for e in a["events"] if e["type"] == "VETO"}
    added = sb - sa
    why = Counter(va.get(k, "not a setup in A") for k in added)
    diffw = [k for k in range(len(a["t"])) if a["pwh"][k] != b["pwh"][k] or a["pwl"][k] != b["pwl"][k]]
    mx = max([abs((a["pwh"][k] or 0) - (b["pwh"][k] or 0)) for k in diffw] + [abs((a["pwl"][k] or 0) - (b["pwl"][k] or 0)) for k in diffw] + [0])
    dtq = sum(1 for x, y in zip(a["tq"], b["tq"]) if x != y)
    flips = sum(1 for x, y in zip(a["tq_floor"], b["tq_floor"]) if x != y)
    days = (a["last"] - a["first"]) / 86400
    w = ", ".join(f"{k} {v}" for k, v in why.most_common()) or "-"
    print(f"| {tf} | {len(a['t'])} | {days:.0f} | {len(sa)} | {len(sb)} | {len(sa & sb)} | {len(sa - sb)} | {len(added)} | {w} | {len(diffw)} ({mx:.2f}) | {dtq} | {flips} |")
    if tf in ("15m", "1h"):
        pooled["A"] += [dict(e, tf=tf) for e in a["events"] if e["type"] == "SIGNAL"]
        pooled["B"] += [dict(e, tf=tf) for e in b["events"] if e["type"] == "SIGNAL"]
t0 = max(A["tf"]["15m"]["first"], A["tf"]["1h"]["first"])
ia, ib = ideas([e for e in pooled["A"] if e["t"] >= t0], 0), ideas([e for e in pooled["B"] if e["t"] >= t0], 0)
span = (A["tf"]["15m"]["last"] - t0) / 86400
print(f"\nIdeas after the REPEAT rule, 15m + 1h pooled, common window {span:.0f} days: A {len(ia)} ({len(ia) / span:.2f}/day), B {len(ib)} ({len(ib) / span:.2f}/day)")
