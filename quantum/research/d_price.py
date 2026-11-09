"""Phase D amendment A2 (registered 2026-11-09, before this run): the PRICE-ONLY part of the registered study, on real
data, while Dukascopy's order flow is unobtainable from every environment this project can reach. Research only.

What runs (exactly the registered machinery, d_study.run / d_study.questions, nothing re-tuned):
  * the +-$15 benchmark labels (B26 via b27.labels) on Phase C's populations: development 2020-04-01 -> 2023-01-24
    (walk-forward) and 2026 from 2026-03-01 (frozen models applied once);
  * sets BASELINE and A only (B / D need order flow; C needs intraday intermarket history the development period lacks),
    the four algorithms, the four rules: family "D3-P", 2 x 4 x 4 = 32 strategies, its own BH and Reality Check;
  * the descriptive questions for BASELINE and A (LR, LGBM), at 15-minute resolution (ADV_FIRST flagged INCONCLUSIVE
    when AMBIGUOUS > 2%).
What does not run: order flow, intermarket, the one-minute measurements and the dynamic track (they need data that
are not available here); they stay registered for the full run, which will be its own family.

    python -m quantum.research.d_price --rd <research-data checkout> --store <market-data checkout> --out <dir>
"""
from __future__ import annotations

import argparse
import os
import sys

from . import b27
from . import d_log as LOG
from . import d_run as R
from . import d_study as S
from . import harness as H

FAMILY = "D3-P"
SETS = ("BASELINE", "A")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Phase D amendment A2: the price-only family on real data")
    ap.add_argument("--rd", required=True)
    ap.add_argument("--store", help="a market-data checkout (2026 extended by the live store, as Phase C)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--log", default=os.path.join("research", "phase_d_trials.jsonl"))
    ap.add_argument("--skip-questions", action="store_true")
    a = ap.parse_args(argv)
    if os.path.exists(os.path.join(a.out, "study.json")):
        raise SystemExit(f"{a.out} already holds a run")
    os.makedirs(os.path.join(a.out, "trades"), exist_ok=True)
    st5, st60 = (os.path.join(a.store, "XAU_USD_5m"), os.path.join(a.store, "XAU_USD_60m")) if a.store else (None, None)
    P = R.populations(a.rd, st5, st60)
    rep = {"mode": f"price-only (amendment A2, family {FAMILY}): no Dukascopy gate applies; the spot paths are Phase C's"}
    for k, p in P.items():
        m = p["m15"]
        rep[k] = {"status": "PASS (price data present)", "bars_15m": len(m), "first": str(m.index[0]), "last": str(m.index[-1]),
                  "score_from": str(p["score_from"]), "data_hash_15m": H.data_hash(m), "bars_1h": len(p["h1"])}
    h = R.write_json(rep, os.path.join(a.out, "data_report.json"))
    LOG.append(a.log, {"phase": "D", "kind": "data_report", "id": f"{FAMILY}-data", "sha256": h, "family": FAMILY,
                       "status": {k: v["status"] for k, v in rep.items() if isinstance(v, dict)}})
    print("features and labels...", flush=True)
    Fd = b27.build_features(P["DEV"]["m15"], P["DEV"]["h1"], log=lambda *x: None)
    Ld = b27.labels("PHASE_D", P["DEV"]["m15"], P["DEV"]["h1"], P["DEV"]["score_from"], True)
    Ld = Ld[Ld["outcome"] != "OPEN"].reset_index(drop=True)
    Fy = b27.build_features(P["Y2026"]["m15"], P["Y2026"]["h1"], log=lambda *x: None)
    Ly = b27.labels("PHASE_D", P["Y2026"]["m15"], P["Y2026"]["h1"], P["Y2026"]["score_from"], False)
    Ly = Ly[Ly["outcome"] != "OPEN"].reset_index(drop=True)
    print(f"rows: development {len(Ld)}, 2026 {len(Ly)}", flush=True)
    res = S.run(Fd, Ld, [], [], Fy, Ly, sets=SETS, log=lambda *x: print(*x, flush=True))
    res["family_id"] = FAMILY
    res["verdict"] = f"{res['verdict']} (family {FAMILY}: price-only sets; order flow not yet tested)"
    tf = R.trade_files(res, Ld, Ly, os.path.join(a.out, "trades", "benchmark"))
    h = R.write_json(res, os.path.join(a.out, "study.json"))
    for s in res["strategies"]:
        LOG.append(a.log, LOG.sanitize({"phase": "D", "kind": "trial", "family": FAMILY, "id": s["id"],
                                        "partition": "development (walk-forward)",
                                        "trades": {k: {"n": v["n"], "sha256": v["sha256"]} for k, v in tf[s["id"]].items()},
                                        "n": s["dev"].get("n_trades"), "r": s["dev"].get("r"), "ci95": s["dev"].get("ci95"),
                                        "matched_random": s["dev"].get("matched_random"), "exp_oz": s["dev"].get("exp_oz"),
                                        "p_vs_random": s["dev"].get("p_vs_random"), "bh_q010": s["bh_q010"],
                                        "y2026": {k: s.get("y2026", {}).get(k) for k in ("n_trades", "r", "exp_oz", "p_vs_random")} if "y2026" in s else None,
                                        "criteria": s["criteria"], "study_sha256": h}))
    print(f"study done: {res['verdict']}", flush=True)
    if not a.skip_questions:
        q = S.questions(Fd, Ld, P["DEV"]["m15"], [], [], sets=SETS, log=lambda *x: print(*x, flush=True))
        LOG.append(a.log, {"phase": "D", "kind": "descriptive", "family": FAMILY, "id": f"{FAMILY}-questions",
                           "sha256": R.write_json(q, os.path.join(a.out, "questions.json"))})
    R.write_json({"not_run": "the one-minute measurements need Dukascopy or MT5 one-minute data (amendment A2)"}, os.path.join(a.out, "m1.json"))
    R.write_json({"not_run": "the dynamic track needs Dukascopy one-minute bid / ask (amendment A2)"}, os.path.join(a.out, "dynamic.json"))
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
