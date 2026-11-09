"""Phase D, D4: independent audit of a registered run's outputs (research/registrations/PHASE_D.json). Research only.

Re-derives every strategy figure from its trade file instead of trusting study.json, and checks the bookkeeping:
  log        the hash chain is intact and the latest registration / amendment record matches PHASE_D.json;
  trials     every strategy in study.json / dynamic.json has exactly one trial record, and no record is orphaned;
  files      each trade file's SHA-256 equals the one in its trial record; only the price-free columns are present;
  figures    n, decided, TP-first rate, Wilson interval, expectancy and PF recomputed from the trades equal study.json;
  bh         Benjamini-Hochberg at q = 0.10 recomputed over each family's p-values gives the same flags;
  partitions no trade fills inside the sealed span; development trades in development, 2026 trades from 2026-01-01;
  gates      a run whose development data failed a gate produced no study; the verdict matches the criteria.

  python research/tools/phase_d_audit.py <phase_d_out> [--log research/phase_d_trials.jsonl] [--out audit.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from quantum.research import d_log as LOG
from quantum.research import d_run as R
from quantum.research import harness as H

REG = os.path.join(os.path.dirname(__file__), "..", "registrations", "PHASE_D.json")
TOL = 1e-9


def _sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _eq(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, float) and math.isnan(a):
        return isinstance(b, float) and math.isnan(b)
    return abs(float(a) - float(b)) <= TOL * max(1.0, abs(float(a)))


def recompute(path: str) -> dict:
    t = pd.read_csv(path)
    o = t["outcome"].to_numpy() if len(t) else []
    tp = int((o == "TP").sum()) if len(t) else 0
    dec = tp + (int(pd.Series(o).isin(["SL", "AMBIGUOUS"]).sum()) if len(t) else 0)
    net = t["net_usd_oz"].astype(float) if len(t) else pd.Series(dtype=float)
    lo, hi = H.wilson(tp, dec) if dec else (None, None)
    win, loss = float(net[net > 0].sum()), float(net[net < 0].sum())
    return {"n_trades": len(t), "n_decided": dec, "r": tp / dec if dec else None, "ci95": [lo, hi],
            "exp_oz": float(net.mean()) if len(t) else None, "pf": win / -loss if loss < 0 else None,
            "columns": list(t.columns), "fill_min": int(t["fill_utc"].min()) if len(t) else None,
            "fill_max": int(t["fill_utc"].max()) if len(t) else None}


def _compare(rec: dict, st: dict) -> list[str]:
    bad = []
    for k in ("n_trades", "n_decided", "r", "exp_oz", "pf"):
        a, b = rec[k], st.get(k)
        b = None if isinstance(b, float) and math.isnan(b) else b
        if not _eq(a, b):
            bad.append(f"{k}: trades {a} vs study {b}")
    for j in (0, 1):
        a, b = rec["ci95"][j], (st.get("ci95") or [None, None])[j]
        if not _eq(a, b):
            bad.append(f"ci95[{j}]: trades {a} vs study {b}")
    return bad


def audit(out: str, log: str) -> dict:
    checks = {}
    ok, why = LOG.verify(log)
    with open(log) as fh:
        recs = [json.loads(x) for x in fh if x.strip()]
    regs = [r for r in recs if r["kind"] in ("registration", "amendment")]
    checks["log"] = {"pass": ok and bool(regs) and regs[-1]["sha256"] == _sha(REG), "chain": why,
                     "registration_matches": bool(regs) and regs[-1]["sha256"] == _sha(REG)}
    with open(os.path.join(out, "data_report.json")) as fh:
        rep = json.load(fh)
    have_study = os.path.exists(os.path.join(out, "study.json"))
    dev_ok = str(rep.get("DEV", {}).get("status", "")).startswith("PASS")
    checks["gates"] = {"pass": dev_ok == have_study, "dev_status": rep.get("DEV", {}).get("status"), "study_written": have_study}
    if not have_study:
        checks["verdict"] = "INSUFFICIENT DATA — RESEARCH INCOMPLETE (data gate)"
        return {"checks": checks, "pass": all(c["pass"] for c in checks.values() if isinstance(c, dict))}
    with open(os.path.join(out, "study.json")) as fh:
        study = json.load(fh)
    families = {"benchmark": (study, os.path.join(out, "trades", "benchmark"), "trial", "")}
    dpath = os.path.join(out, "dynamic.json")
    if os.path.exists(dpath):
        with open(dpath) as fh:
            dyn = json.load(fh)
        for k, v in dyn.items():
            if isinstance(v, dict) and "strategies" in v:
                families[k] = (v, os.path.join(out, "trades", "dynamic", k.replace("/", "_")), "trial-dynamic", f"{k} ")
    family = study.get("family_id")                     # None = the full registered run; "D3-P" = amendment A2's family
    checks["family"] = family or "full run"
    trial_ids = {}
    for r in recs:
        if r["kind"] in ("trial", "trial-dynamic") and r.get("family") == family:
            trial_ids.setdefault((r["kind"], r["id"]), []).append(r)
    fig_bad, file_bad, part_bad, bh_bad, missing, dup, cols_bad = [], [], [], [], [], [], []
    expected = set()
    for res, tdir, kind, pre in families.values():
        ps = [s["dev"].get("p_vs_random") if s["dev"].get("p_vs_random") is not None else 1.0 for s in res["strategies"]]
        flags = H.benjamini_hochberg(ps, 0.10)
        for s, f in zip(res["strategies"], flags, strict=True):
            tid = pre + s["id"]
            expected.add((kind, tid))
            lst = trial_ids.get((kind, tid), [])
            if not lst:
                missing.append(tid)
                continue
            if len(lst) > 1:
                dup.append(tid)
            tr = lst[-1].get("trades", {})
            if bool(f) != bool(s["bh_q010"]):
                bh_bad.append(tid)
            for per, key, lo, hi in (("dev", "dev", H.DEV[0], H.DEV[1]), ("y2026", "y2026", H.HOLD[1], None)):
                if per not in tr:
                    continue
                path = os.path.join(tdir, s["id"].replace("/", "_") + ("__dev.csv" if per == "dev" else "__2026.csv"))
                if not os.path.exists(path) or _sha(path) != tr[per]["sha256"]:
                    file_bad.append(f"{tid} {per}")
                    continue
                rc = recompute(path)
                if not set(rc["columns"]) <= set(R.TRADE_COLS):
                    cols_bad.append(f"{tid} {per}: {sorted(set(rc['columns']) - set(R.TRADE_COLS))}")
                fig_bad += [f"{tid} {per} {b}" for b in _compare(rc, s.get(key) or {})]
                if rc["fill_min"] is not None:
                    sealed_lo, sealed_hi = int(H.VAL[0].timestamp()), int(H.HOLD[1].timestamp())
                    inside = rc["fill_min"] < int(lo.timestamp()) or (hi is not None and rc["fill_max"] >= int(hi.timestamp()))
                    sealed = not (rc["fill_max"] < sealed_lo or rc["fill_min"] >= sealed_hi)
                    if inside or sealed:
                        part_bad.append(f"{tid} {per}")
    orphans = [k[1] for k in trial_ids if k not in expected]
    checks["trials"] = {"pass": not missing and not dup and not orphans, "missing": missing, "duplicated": dup, "orphaned": orphans}
    checks["files"] = {"pass": not file_bad and not cols_bad, "hash_mismatch_or_missing": file_bad, "price_columns": cols_bad}
    checks["figures"] = {"pass": not fig_bad, "mismatches": fig_bad[:50], "count": len(fig_bad)}
    checks["bh"] = {"pass": not bh_bad, "mismatches": bh_bad}
    checks["partitions"] = {"pass": not part_bad, "violations": part_bad}
    q = [s["id"] for s in study["strategies"] if s["criteria"]["QUALIFIES"]]
    vtxt = study.get("verdict", "")
    checks["verdict"] = {"pass": (bool(q) == vtxt.startswith("QUALIFIES")) and (not vtxt.startswith("QUALIFIES") or bool(q)),
                         "verdict": vtxt, "qualified": q}
    return {"checks": checks, "pass": all(c["pass"] for c in checks.values() if isinstance(c, dict))}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--log", default=os.path.join("research", "phase_d_trials.jsonl"))
    ap.add_argument("--report")
    a = ap.parse_args(argv)
    res = audit(a.out, a.log)
    txt = json.dumps(res, indent=1, default=str)
    if a.report:
        with open(a.report, "w") as fh:
            fh.write(txt)
    print(json.dumps({k: v["pass"] if isinstance(v, dict) else v for k, v in res["checks"].items()} | {"PASS": res["pass"]}))
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
