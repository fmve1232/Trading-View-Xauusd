"""Feature-to-decision dependency inventory of the frozen engine, by perturbation (read-only).

  PYTHONPATH=<deployed checkout> python3 -I audit/tools/v2_features.py <store COPY> <snapshot UTC ISO> <py_trace.json> <out dir> [tf ...]

For each key of the feature dict F that quantum/features.compute returns, the treatment arm is re-run with that one key
perturbed and everything else unchanged: booleans negated, numeric and text arrays reversed in time (a constant array is
shifted by +1 / replaced), dict-valued keys perturbed element-wise, scalars negated or doubled. Compared with the
unperturbed run: the SIGNAL events from 2026-01-01 (the decision), every other event (VETO / DECISION / chart events)
and the final dashboard state. A key whose perturbation changes no signal on this sample is not shown to drive a
decision HERE; it may still matter under other conditions (e.g. COT gating is off in DEFAULT). Price inputs (o, h, l,
c, v, open, n) are not perturbed: they drive everything by construction. The static class from py_trace.py is shown
beside each key. Outputs v2_features_<tf>.csv and v2_features.json."""
from __future__ import annotations

import copy
import csv
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime

import numpy as np
import pandas as pd

STORE, SNAP, TRACE, OUT = sys.argv[1], datetime.fromisoformat(sys.argv[2].replace("Z", "+00:00")), sys.argv[3], sys.argv[4]
TFS = tuple(sys.argv[5:]) or ("15m", "1h")
FROM = pd.Timestamp("2026-01-01", tz="UTC")
SKIP = {"o", "h", "l", "c", "v", "open", "n"}
_W = {}


def perturb(x):
    if isinstance(x, dict):
        return {k: perturb(v) for k, v in x.items()}, "dict, element-wise"
    if isinstance(x, (bool, np.bool_)):
        return (not x), "scalar negated"
    if isinstance(x, (int, float, np.integer, np.floating)):
        return x * 2 if x else 1, "scalar doubled"
    if isinstance(x, np.ndarray):
        if x.dtype == bool:
            return ~x, "negated"
        r = x[::-1].copy()
        if x.dtype.kind in "fiu":
            same = np.array_equal(np.nan_to_num(r.astype(float), nan=-9e9), np.nan_to_num(x.astype(float), nan=-9e9))
            return (x.astype(float) + 1.0 if same else r), ("constant +1" if same else "reversed")
        same = bool(np.all(r == x))
        return (np.full(x.shape, "PERTURBED", dtype=object) if same else r), ("constant replaced" if same else "reversed")
    if isinstance(x, list):
        return x[::-1], "list reversed"
    return None, "not perturbable"


def init(tf):
    os.environ["TWELVEDATA_API_KEY"] = "offline-placeholder-not-a-key"
    from quantum.data import sources

    def _off(*a, **k):
        raise sources.FetchError("offline audit run")
    sources._get = _off
    from quantum import engine
    from quantum.config import DEFAULT
    from quantum.data import market as mk
    from quantum.features import compute
    from quantum.pipeline import MAX_BARS
    dl = mk.download_all(STORE, ("5m", "15m", "30m", "60m"))
    m = mk.build_market(tf, dl, SNAP)
    assert m.price_source.startswith("twelvedata"), m.price_source
    if len(m.base) > MAX_BARS:
        m.base = m.base.iloc[-MAX_BARS:]
    F = compute(m, DEFAULT)
    first = int(m.base.index.searchsorted(FROM))
    _W.update(tf=tf, m=m, F=F, first=first, engine=engine, cfg=DEFAULT)
    _W["base"] = outputs(engine.run(m, DEFAULT, "treatment", copy.deepcopy(F)), first)


def outputs(res, first):
    sig = sorted((e["i"], e["dir"]) for e in res.events if e["type"] == "SIGNAL" and e["i"] >= first)
    other = sorted((e["type"], e.get("i"), e.get("dir"), str(e.get("to", ""))) for e in res.events if e["type"] != "SIGNAL" and (e.get("i") or 0) >= first)
    last = json.dumps(res.last, sort_keys=True, default=str)
    return sig, other, last


def one(key):
    F2 = copy.deepcopy(_W["F"])
    v, how = perturb(F2[key])
    if v is None:
        return key, {"how": how}
    F2[key] = v
    try:
        sig, other, last = outputs(_W["engine"].run(_W["m"], _W["cfg"], "treatment", F2), _W["first"])
    except Exception as e:  # noqa: BLE001 - a crash means the engine reads the key; recorded, not hidden
        return key, {"how": how, "error": f"{type(e).__name__}: {str(e)[:80]}"}
    b = _W["base"]
    return key, {"how": how, "signals_changed": len(set(sig) ^ set(b[0])), "other_events_changed": len(set(other) ^ set(b[1])),
                 "dashboard_state_changed": last != b[2]}


def run_tf(tf):
    init(tf)
    keys = [k for k in _W["F"] if k not in SKIP]
    return tf, keys, len(_W["base"][0])


def main():
    os.makedirs(OUT, exist_ok=True)
    stat = json.load(open(TRACE))["feature_reach"]
    klass = {k: c for c, ks in stat.items() for k in ks}
    out = {}
    for tf in TFS:
        with ProcessPoolExecutor(max_workers=4, initializer=init, initargs=(tf,)) as ex:
            tf_, keys, nbase = run_tf(tf)
            res = dict(ex.map(one, keys))
        rows = []
        for k in sorted(res):
            r = res[k]
            if "error" in r:
                verdict = "read by the engine (perturbation crashed it)"
            elif "signals_changed" not in r:
                verdict = "not perturbable"
            elif r["signals_changed"]:
                verdict = "DRIVES SIGNALS on this sample"
            elif r["other_events_changed"] or r["dashboard_state_changed"]:
                verdict = "changes engine state / display, not signals, on this sample"
            else:
                verdict = "no effect on this sample"
            rows.append({"key": k, "static_class": klass.get(k, "-"), "perturbation": r.get("how"), "signals_changed": r.get("signals_changed"),
                         "other_events_changed": r.get("other_events_changed"), "dashboard_state_changed": r.get("dashboard_state_changed"),
                         "error": r.get("error", ""), "verdict": verdict})
        with open(os.path.join(OUT, f"v2_features_{tf}.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        cnt = {}
        for r in rows:
            cnt.setdefault(r["verdict"], 0)
            cnt[r["verdict"]] += 1
        cross = {}
        for r in rows:
            cross.setdefault(r["static_class"], {}).setdefault(r["verdict"], 0)
            cross[r["static_class"]][r["verdict"]] += 1
        out[tf] = {"baseline_signals": nbase, "keys_tested": len(rows), "verdicts": cnt, "static_vs_perturbation": cross}
        print(tf, json.dumps(out[tf], indent=1))
    json.dump(out, open(os.path.join(OUT, "v2_features.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
