"""Prefix invariance: outputs for bars closed by T must be identical whether the engine saw data up to T or up to now."""
import json, sys, math
from datetime import datetime
full_dir, cut_dir, T = sys.argv[1], sys.argv[2], int(datetime.fromisoformat(sys.argv[3].replace("Z", "+00:00")).timestamp())
SEC = {"15m": 900, "1h": 3600, "4h": 14400}
for tf in sys.argv[4:]:
    F, C = (json.load(open(f"{d}/{tf}.json")) for d in (full_dir, cut_dir))
    sec = SEC[tf]
    tF, tC = F["chart"]["t"], C["chart"]["t"]
    lo = max(tF[0], tC[0])
    iF, iC = {t: k for k, t in enumerate(tF)}, {t: k for k, t in enumerate(tC)}
    common = [t for t in tC if t >= lo and t + sec <= T and t in iF]
    diffs = {}
    for key, arrC in C["chart"].items():
        arrF = F["chart"].get(key)
        if not isinstance(arrC, list) or arrF is None or len(arrC) != len(tC) or len(arrF) != len(tF): continue
        n = 0; worst = None
        for t in common:
            a, b = arrF[iF[t]], arrC[iC[t]]
            same = (a == b) or (isinstance(a, float) and isinstance(b, float) and (math.isnan(a) and math.isnan(b) or abs(a - b) <= 1e-9 * max(1, abs(a))))
            if not same:
                n += 1; worst = worst or (t, a, b)
        if n: diffs[key] = (n, worst)
    def ev(p):
        return {(m["t"], m["type"], m.get("dir")) for m in p["markers"] if lo <= m["t"] and m["t"] + sec <= T}
    mF, mC = ev(F), ev(C)
    lim = min(min((m["t"] for m in F["markers"]), default=0), min((m["t"] for m in C["markers"]), default=0))
    mF = {x for x in mF if x[0] >= max(lim, min(m["t"] for m in C["markers"]))}
    mC = {x for x in mC if x[0] >= max(lim, min(m["t"] for m in F["markers"]))}
    dF = {(d["t"], d.get("decision") or d.get("to") or json.dumps(d, sort_keys=True)[:60]) for d in F["decisions"] if lo <= d["t"] and d["t"] + sec <= T}
    dC = {(d["t"], d.get("decision") or d.get("to") or json.dumps(d, sort_keys=True)[:60]) for d in C["decisions"] if lo <= d["t"] and d["t"] + sec <= T}
    print(f"{tf} cut {sys.argv[3]}: {len(common)} common closed bars; chart series compared {sum(1 for k,v in C['chart'].items() if isinstance(v, list))}; "
          f"series with differences {len(diffs)}; markers only-full {len(mF - mC)} only-cut {len(mC - mF)} (of {len(mC)}); "
          f"decisions only-full {len(dF - dC)} only-cut {len(dC - dF)} (of {len(dC)})")
    for k, (n, w) in list(diffs.items())[:6]:
        print("   series", k, n, "bars differ; first", w)
    for x in sorted(mF ^ mC)[:6]:
        print("   marker diff", x, "in full" if x in mF else "in cut")
