"""Which pre-2026 data changes the frozen engine's 2026 signals? (read-only diagnostic)

  PYTHONPATH=<deployed checkout> python3 -I audit/tools/v2_cut_diagnostic.py <store> <snapshot UTC ISO> <out.json>

For each group, a store copy with that group's month files before 2026-01 deleted; treatment-arm signals counted from
2026-01-01 are compared with the full store's. Groups: XAU daily; GC and VIX daily; the hourly and intraday cross-asset
series (DXY, US10Y, S&P, EURUSD, SI, GC intraday); everything."""
import json
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
STORE, SNAP_S, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
sys.argv = [sys.argv[0], STORE, SNAP_S, os.path.dirname(OUT)]
import v2_ablation as A  # noqa: E402

GROUPS = {"none": lambda d: False, "XAU daily": lambda d: d == "XAU_USD_1d", "GC and VIX daily": lambda d: d in ("GC_F_1d", "_VIX_1d"),
          "cross-asset intraday": lambda d: not d.startswith("XAU_USD") and not d.endswith("_1d"), "everything": lambda d: True}


def make(name, pick):
    dst = STORE.rstrip("/") + "_diag_" + name.replace(" ", "_")
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(STORE, dst)
    for d in os.listdir(dst):
        p = os.path.join(dst, d)
        if os.path.isdir(p) and d not in ("holdout", "research_forward") and pick(d):
            for f in os.listdir(p):
                if f.endswith(".csv") and f[:7] < "2026-01":
                    os.remove(os.path.join(p, f))
    return dst


def job(args):
    tf, name, path = args
    sig, _ = A.run(path, tf)
    return tf, name, sig


def main():
    paths = {n: (STORE if n == "none" else make(n, f)) for n, f in GROUPS.items()}
    jobs = [(tf, n, p) for tf in A.TFS for n, p in paths.items()]
    with ProcessPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(job, jobs))
    base = {tf: s for tf, n, s in res if n == "none"}
    out = {}
    for tf, n, s in res:
        b = base[tf]
        diff = sorted((set(b) - set(s)) | (set(s) - set(b)))
        out.setdefault(tf, {})[n] = {"signals": len(s), "differ_from_full_store": len(diff),
                                     "first_differing_bar": diff[0][0][:16] if diff else None, "last_differing_bar": diff[-1][0][:16] if diff else None}
    for n, p in paths.items():
        if n != "none":
            shutil.rmtree(p)
    json.dump(out, open(OUT, "w"), indent=1)
    for tf, v in out.items():
        print(tf, {n: (x["signals"], x["differ_from_full_store"], x["first_differing_bar"], x["last_differing_bar"]) for n, x in v.items()})


if __name__ == "__main__":
    main()
