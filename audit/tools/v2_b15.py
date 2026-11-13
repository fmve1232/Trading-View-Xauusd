"""B15-ENGINE-FWD: the registered criterion recomputed from the registration and the raw records (read-only).

  python3 -I audit/tools/v2_b15.py <checkout with research/registrations> <forward-ledger dir> <market-data store dir>

Prints: the registration's hash and rule; the Wilson thresholds for each look recomputed independently; the record's
trades (raw), their decided order and tally; the cross-check against the store's plan_validation.json; and, for every
look, how many of the remaining decided results must be TP1 for the look to be passed."""
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timezone

REPO, LED, STORE = sys.argv[1:4]
REG = os.path.join(REPO, "research", "registrations", "B15-ENGINE-FWD.json")
REC = os.path.join(LED, "research_forward", "B15-ENGINE-FWD.json")
VAL = os.path.join(STORE, "plan_validation.json")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def wilson_lo(k, n, z=1.959963984540054):
    p = k / n
    d = 1 + z * z / n
    return (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d


reg = json.load(open(REG))
be = (13 + 0.26) / 26
print("registration", REG, "sha256", sha(REG))
print("  proven rule:", reg["primary_test"]["proven"])
print("  break-even (13 + 0.26) / 26 =", round(be, 6))
looks = [30, 40, 50, 60, 70, 80, 90, 100]
need = {}
for n in looks:
    k = next(k for k in range(n + 1) if wilson_lo(k, n) > be)
    need[n] = k
    print(f"  look {n}: minimum TP1 count {k} (Wilson lower bound {wilson_lo(k, n):.4f}; with {k - 1}: {wilson_lo(k - 1, n):.4f})")
rec = json.load(open(REC))
print("record", REC, "sha256", sha(REC))
tr = rec["trades"]
dec = sorted([t for t in tr if t.get("result") in ("TP", "SL")], key=lambda t: (t.get("t_res") or 0, t.get("id")))
print(f"  trades {len(tr)}, decided {len(dec)}, excluded {rec.get('excluded')}, checks {len(rec.get('checks', []))}, verdict {rec.get('verdict')}")
for t in dec:
    print("   ", t["id"], t["tf"], "BUY" if t["dir"] == 1 else "SELL", f"{t['entry']:.2f}",
          datetime.fromtimestamp(t["t_dec"], timezone.utc).strftime("%d %b %H:%M"), "->", t["result"],
          datetime.fromtimestamp(t["t_res"], timezone.utc).strftime("%d %b %H:%M"), t.get("path"), "late" if t.get("late") else "")
k = sum(t["result"] == "TP" for t in dec)
n = len(dec)
print(f"  tally {k} TP / {n - k} SL of {n} = {k / n:.3f}; Wilson 95% [{wilson_lo(k, n):.3f}, {1 - wilson_lo(n - k, n):.3f}]")
for L in looks:
    rem, req = L - n, need[L] - k
    print(f"  look {L}: needs {need[L]} TP1 of {L}; now {k} of {n}; {req} of the next {rem} must be TP1 ({req / rem:.0%})"
          + (" -- impossible" if req > rem else ""))
# cross-check with the plan validation log: same plans (by tf, decision time, side, entry) and the same result
val = json.load(open(VAL))
start = rec["started_utc"]
vv = {(v["tf"], int(v.get("t_dec") or v["t"]), v["dir"], round(v["entry"], 2)): v for v in val if int(v.get("t_dec") or v["t"]) >= start - 86400}
miss, mism = [], []
for t in tr:
    key = (t["tf"], int(t["t_dec"]), t["dir"], round(t["entry"], 2))
    v = vv.get(key)
    if v is None:
        miss.append(t["id"])
    elif v.get("result") != t.get("result"):
        mism.append((t["id"], v.get("result"), t.get("result")))
later = [v for k_, v in vv.items() if k_[1] >= start and v.get("result") in ("TP", "SL") and
         not any((t["tf"], int(t["t_dec"]), t["dir"], round(t["entry"], 2)) == k_ for t in tr)]
print("plan_validation", VAL, "sha256", sha(VAL))
print(f"  B15 trades found in plan_validation: {len(tr) - len(miss)} of {len(tr)}; result mismatches {mism}; missing {miss}")
print(f"  decided plans in plan_validation since B15 start not in B15: {len(later)}",
      [(v['tf'], datetime.fromtimestamp(int(v.get('t_dec') or v['t']), timezone.utc).strftime('%d %b %H:%M'), v['result'], v.get('sl_usd'), v.get('tp_usd')) for v in later][:12])
