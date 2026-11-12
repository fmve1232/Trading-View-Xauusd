"""R14 A/B: effect of Yahoo auxiliary-series revisions on the engine (offline, read-only; research measurement).

Usage (from a checkout; nothing is written outside <work>):
  python audit/tools/aux_revision_ab.py <base store snapshot> <donor store snapshot> <now UTC epoch> <work dir> [ctrl]
The two snapshots are copies of the market-data store from two production runs (e.g. `git archive` of two
market-data commits); keep them out of the repository (vendor data). Writes <work>/result.json and <work>/raw.pkl.

For a pair (BASE store snapshot, DONOR store snapshot) from two consecutive production runs:
  arm "base"  = the BASE snapshot as production stored it;
  arm "ctrl"  = BASE with every auxiliary series re-saved through store.load/store.save (harness null check);
  arm "swap"  = BASE with every auxiliary series (everything except XAU_USD_*) replaced by the DONOR's version,
                truncated to BASE's last bar of that series. XAU/USD spot data stays byte-identical.
Every arm runs the production code path offline: download_all (fetches disabled -> store), build_market,
features, engine treatment / control / challenger, report.build. Nothing is written outside this scratch dir.
"""
import json
import math
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

os.environ["TWELVEDATA_API_KEY"] = "offline-dummy"     # select the twelvedata candidate -> its store series

from quantum.data import sources as s                  # noqa: E402


def _off(*a, **k):
    raise s.FetchError("offline A/B run")


s._get = _off

import numpy as np                                      # noqa: E402
import pandas as pd                                     # noqa: E402

from quantum import engine, holdout, report             # noqa: E402
from quantum.config import DEFAULT, TIMEFRAMES          # noqa: E402
from quantum.data import market as mk, store            # noqa: E402
from quantum.features import compute as compute_features  # noqa: E402
from quantum.pipeline import MAX_BARS                   # noqa: E402

TFS = ["15m", "30m", "1h", "4h", "5m"]


def series_dirs(d):
    return sorted(x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x))
                  and any(f.endswith(".csv") for f in os.listdir(os.path.join(d, x))))


def is_aux(name):
    return not name.startswith("XAU_USD")


def make_arm(base, donor, out, mode):
    if os.path.exists(out):
        shutil.rmtree(out)
    shutil.copytree(base, out)
    pert = {}
    for nm in series_dirs(base):
        if not is_aux(nm):
            continue
        b = store.load(base, nm)
        src = b if mode == "ctrl" else store.load(donor, nm)
        if src is None:
            continue
        src = src[src.index <= b.index.max()]
        if mode == "swap":
            common = b.index.intersection(src.index)
            cols = [c for c in b.columns if c in src.columns]
            bb, ss = b.loc[common, cols].astype(float), src.loc[common, cols].astype(float)
            diff = ~np.isclose(bb.to_numpy(), ss.to_numpy(), rtol=0, atol=1e-9, equal_nan=True)
            per_col = {c: int(diff[:, j].sum()) for j, c in enumerate(cols)}
            rel = (ss["close"] - bb["close"]).abs() / bb["close"].abs()
            pert[nm] = {"rows": len(b), "rows_donor": len(src), "only_base": len(b.index.difference(src.index)),
                        "only_donor": len(src.index.difference(b.index)), "changed_by_col": per_col,
                        "max_rel_close": float(rel.max()) if len(rel) else 0.0,
                        "last_changed_bar": str(common[diff.any(axis=1)].max()) if diff.any() else None}
        shutil.rmtree(os.path.join(out, nm))
        store.save(out, nm, src)
    return pert


def run_tf(store_dir, tf, now_iso):
    now = datetime.fromisoformat(now_iso)
    cfg = DEFAULT
    need = sorted({("60m" if TIMEFRAMES[t].get("resample_from") else TIMEFRAMES[t]["yahoo"]) for t in TFS} | {"60m"})
    dl = mk.download_all(store_dir, tuple(need))
    m = mk.build_market(tf, dl, now)
    if len(m.base) > MAX_BARS:
        m.base = m.base.iloc[-MAX_BARS:]
    man = holdout.load_or_freeze(store_dir, cfg, now)
    F = compute_features(m, cfg)
    res = engine.run(m, cfg, "treatment", F)
    ctrl = engine.run(m, cfg, "control", F)
    chal = engine.run(m, cfg, "challenger", F)
    payload = report.build(m, res, ctrl, cfg, man, now, store_dir, res_chal=chal)
    out = {"t": [int(x) for x in (m.base.index.astype("int64") // 10**9)], "payload": payload, "psrc": dl.price_source}
    for arm, r in (("treatment", res), ("control", ctrl), ("challenger", chal)):
        out[arm] = {"rows": {k: (np.asarray(v).tolist() if not isinstance(v, (str, int, float)) else v) for k, v in r.rows.items()},
                    "events": r.events, "last": r.last}
    return out


def flat(x, p=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from flat(v, f"{p}.{k}" if p else str(k))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from flat(v, f"{p}[{i}]")
    else:
        yield p, x


def same(a, b):
    if isinstance(a, float) and isinstance(b, float):
        if math.isnan(a) and math.isnan(b):
            return True
        return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
    return a == b


def compare(A, B):
    rep = {"bars": len(A["t"]), "same_bars": A["t"] == B["t"]}
    for arm in ("treatment", "control", "challenger"):
        ra, rb = A[arm]["rows"], B[arm]["rows"]
        diffs = {}
        for k in ra:
            va, vb = ra[k], rb.get(k)
            if not isinstance(va, list) or not isinstance(vb, list) or len(va) != len(vb):
                if not same(va, vb):
                    diffs[k] = "shape/scalar differs"
                continue
            idx = [i for i, (x, y) in enumerate(zip(va, vb)) if not same(x, y)]
            if idx:
                diffs[k] = {"n": len(idx), "first_t": A["t"][idx[0]] if idx[0] < len(A["t"]) else None,
                            "last_t": A["t"][idx[-1]] if idx[-1] < len(A["t"]) else None}
        ea = {json.dumps(e, sort_keys=True, default=str) for e in A[arm]["events"]}
        eb = {json.dumps(e, sort_keys=True, default=str) for e in B[arm]["events"]}
        last_diff = [k for k, _ in flat(A[arm]["last"]) if not same(dict(flat(A[arm]["last"]))[k], dict(flat(B[arm]["last"])).get(k))]
        rep[arm] = {"row_keys_differing": diffs, "events_only_base": sorted(ea - eb), "events_only_swap": sorted(eb - ea),
                    "n_events": len(ea), "last_bar_fields_differing": last_diff}
    fa, fb = dict(flat(A["payload"])), dict(flat(B["payload"]))
    pdiff = {k: (fa.get(k), fb.get(k)) for k in sorted(set(fa) | set(fb)) if not same(fa.get(k), fb.get(k))}
    rep["payload_leaves"] = len(fa)
    rep["payload_differing"] = pdiff
    return rep


def main(base, donor, now_epoch, work, with_ctrl):
    os.makedirs(work, exist_ok=True)
    arms = {"base": None, "swap": "swap"} | ({"ctrl": "ctrl"} if with_ctrl else {})
    pert = {}
    dirs = {}
    for a, mode in arms.items():
        d = os.path.join(work, a)
        if mode is None:
            if os.path.exists(d):
                shutil.rmtree(d)
            shutil.copytree(base, d)
        else:
            p = make_arm(base, donor, d, mode)
            if mode == "swap":
                pert = p
        dirs[a] = d
    now = datetime.fromtimestamp(int(now_epoch), timezone.utc).isoformat()   # identical for every arm
    jobs = {}
    with ProcessPoolExecutor(max_workers=4) as ex:
        for a, d in dirs.items():
            for tf in TFS:
                jobs[(a, tf)] = ex.submit(run_tf, d, tf, now)
        out = {k: f.result() for k, f in jobs.items()}
    result = {"base": base, "donor": donor, "now": now, "perturbation": pert, "tfs": {}}
    for tf in TFS:
        r = {"swap_vs_base": compare(out[("base", tf)], out[("swap", tf)]), "psrc": out[("base", tf)]["psrc"]}
        if with_ctrl:
            r["ctrl_vs_base"] = compare(out[("base", tf)], out[("ctrl", tf)])
        result["tfs"][tf] = r
    import pickle
    with open(os.path.join(work, "raw.pkl"), "wb") as f:
        pickle.dump({f"{a}|{tf}": v for (a, tf), v in out.items()}, f)
    with open(os.path.join(work, "result.json"), "w") as f:
        json.dump(result, f, indent=1, default=str)
    print("done", work)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], len(sys.argv) > 5 and sys.argv[5] == "ctrl")
