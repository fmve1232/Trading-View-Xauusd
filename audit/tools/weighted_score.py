"""Weighted engineering-verification score (mandate §13), computed from the requirement list below.

  python3 audit/tools/weighted_score.py [--json out.json]

Each requirement is scored 1 only when its status is VERIFIED with evidence; everything else (OPEN, FAIL,
UNVERIFIED, NOT RUN, BLOCKED) scores 0. A category's score is the share of its requirements verified; the total is
the weighted sum. Two columns: "production" (what is deployed at 505f05ecc) and "branch" (production plus the
remediation branch, which is NOT deployed and needs approval). A P0 requirement that fails blocks the 90% designation
whatever the total. Trading performance is NOT part of this score; it is reported separately.
"""
from __future__ import annotations

import argparse
import json

WEIGHTS = {"data": 0.20, "stats": 0.20, "cost": 0.15, "alerts": 0.15, "research": 0.10, "tests": 0.10,
           "ops": 0.05, "docs": 0.05}
V, X = "VERIFIED", None
# (id, category, P0?, requirement, production status, branch status, evidence)
REQ = [
    ("D1", "data", False, "Engine input excludes market-shut quotes; cited PDH/PDL/PWL reproduced independently", V, V, "levels_check_2026-11-26.txt; sources.trading_week_only"),
    ("D2", "data", True, "Forward ledgers append-only, never force-pushed", V, V, "forward-ledger 312 commits; workflow step"),
    ("D3", "data", True, "Ledger records internally consistent (attribution, arithmetic, windows)", V, V, "ledger_check_2026-11-26.txt: 0 problems"),
    ("D4", "data", True, "Audit tooling reports the records correctly (no false problems)", "FAIL", V, "GA-21"),
    ("D5", "data", True, "Live sweep / breakout outcome records durable (no cap, no overwrite)", "FAIL", V, "GA-03; GA-03_outcome_log_replay.txt"),
    ("D6", "data", False, "Per-run payload archive checked against its manifest SHA-256", "NOT RUN", "NOT RUN", "artifact download unavailable here"),
    ("D7", "data", False, "Research input data retained immutably by hash", "OPEN", "OPEN", "GA-15"),
    ("D8", "data", False, "Vendor data licensing checked", "BLOCKED", "BLOCKED", "GA-16"),
    ("S1", "stats", False, "Forward metrics per arm and timeframe with Wilson and bootstrap intervals", V, V, "forward_stats.py; forward_report.py"),
    ("S2", "stats", False, "Dependence-aware (day-clustered) intervals", "FAIL", V, "GA-09"),
    ("S3", "stats", False, "Matched random-entry baseline on forward data", "FAIL", V, "forward_report baseline"),
    ("S4", "stats", False, "Cost sensitivity of forward results at measured spreads", "FAIL", V, "mean_r_at_spread"),
    ("S5", "stats", False, "Loss tail reported (worst, share below -1 R)", "FAIL", V, "GA-10"),
    ("S6", "stats", True, "No look-ahead: engine and monitors tested on prefixes", V, V, "test_no_lookahead and five prefix tests"),
    ("S7", "stats", False, "Registered looks honoured; INSUFFICIENT EVIDENCE between looks", V, V, "test_engine_forward, test_grab_forward"),
    ("S8", "stats", False, "Program-level multiple-testing correction over all trials", "OPEN", "OPEN", "GA-02"),
    ("S9", "stats", False, "Untouched out-of-sample data of sufficient size", "FAIL", "FAIL", "GA-01, GA-08"),
    ("E1", "cost", False, "One cost of record applied to every simulated trade", V, V, "cost_pts_used [0.77]"),
    ("E2", "cost", False, "Spread verified by session at the broker", "UNVERIFIED", "UNVERIFIED", "Asia only; 1 NY reading"),
    ("E3", "cost", False, "Commission, contract size, tick value from the MT5 specification", "UNVERIFIED", "UNVERIFIED", "GA-04"),
    ("E4", "cost", False, "Swap", "UNVERIFIED", "UNVERIFIED", "GA-04"),
    ("E5", "cost", False, "Slippage and stop / target fills against account statements", "UNVERIFIED", "UNVERIFIED", "GA-28"),
    ("E6", "cost", True, "Position sizing keeps the planned loss within $650 including the round-trip cost", V, V, "test_notify_plan, test_risk_sizing"),
    ("E7", "cost", True, "Gap fills modelled; gap risk disclosed in plan alerts", V, V, "test_backtest_gaps; confirm_entry.gap_line"),
    ("E8", "cost", False, "Expectancy recomputed at measured spreads", "FAIL", V, "BROKER_COST_VALIDATION.md"),
    ("A1", "alerts", True, "Every SENT stage has a server-accepted delivery record", V, V, "377 of 377"),
    ("A2", "alerts", True, "No duplicate sends", V, V, "0 keys accepted twice"),
    ("A3", "alerts", True, "No stale alert sent (freshness gate)", V, V, "0 over 20 min; stale-gate tests"),
    ("A4", "alerts", False, "Retry with cache check; mutation-tested", V, V, "42 of 42 mutants killed"),
    ("A5", "alerts", True, "Resilient to rate limits (no lost alert)", "FAIL", "UNVERIFIED", "GA-07: 1 lost; fix untested live"),
    ("A6", "alerts", False, "Device delivery confirmed", "UNVERIFIED", "UNVERIFIED", "not observable via ntfy"),
    ("A7", "alerts", False, "Disclaimer and planned-vs-guaranteed loss wording", V, V, "test_alert_disclaimer; GAP RISK line"),
    ("A8", "alerts", False, "Outage notice when alerts may be missing", V, V, "test_outage_notice (53)"),
    ("R1", "research", False, "Registration provably precedes code (server-side times)", "UNVERIFIED", "UNVERIFIED", "GA-06"),
    ("R2", "research", False, "Complete partition-use ledger", "FAIL", V, "partition_access.json"),
    ("R3", "research", False, "Complete trial log in one place", "FAIL", V, "trials_union.jsonl"),
    ("R4", "research", True, "Partition boundaries leak-free", V, V, "harness.partition; W4 boundary check"),
    ("R5", "research", False, "Sealed holdout untouched", "FAIL", "FAIL", "read by B30, B31, B31b-W2"),
    ("R6", "research", True, "No tuning on forward data; freeze key unchanged", V, V, "freeze key recomputed"),
    ("T1", "tests", False, "Full Python suite passes on the pinned versions", V, V, "production gate (40/40 runs); branch: pinned run + GitHub pr-checks"),
    ("T2", "tests", False, "JavaScript tests pass", V, V, "node --test 20 of 20"),
    ("T3", "tests", False, "Pine checkers and frozen-file manifest", V, V, "7 of 7 OK; checkers clean"),
    ("T4", "tests", True, "Freeze key reproducible", V, V, "1f88aad357497da4:4440d52587f5cc6b"),
    ("T5", "tests", False, "Mutation tests of critical rules", V, V, "mutation_notify_delivery 42/42"),
    ("T6", "tests", False, "Library versions recorded per run", V, V, "manifest env; requirements.lock"),
    ("T7", "tests", False, "Every research result reproducible from committed code and data", "UNVERIFIED", "UNVERIFIED", "W3/W7/W8/W12 reproduced in W13; not all studies; GA-15"),
    ("T8", "tests", False, "Live alert replay committed as a tested tool", "OPEN", "OPEN", "GA-23"),
    ("O1", "ops", False, "Scheduler cadence: production runs succeed", V, V, "40 of 40 latest runs"),
    ("O2", "ops", False, "Site smoke test on every deploy", V, V, "smoke.py in every run"),
    ("O3", "ops", False, "Partial-failure warnings", V, V, "test_run_hygiene"),
    ("O4", "ops", False, "No false-failure workflows", "FAIL", "FAIL", "GA-22"),
    ("O5", "ops", False, "Independent price cross-check result inspected", "NOT RUN", "NOT RUN", "xcheck-dukascopy"),
    ("C1", "docs", False, "Feature register with code, tests and evidence", V, V, "docs/AUDIT_PACK.md"),
    ("C2", "docs", False, "Inventory appendix current and enforced by a test", "FAIL", V, "GA-17"),
    ("C3", "docs", False, "Changelog and approval register", "FAIL", V, "CHANGELOG_AND_APPROVAL_REGISTER.md"),
    ("C4", "docs", False, "Gap register with status and evidence", "FAIL", V, "GAP_REMEDIATION_REGISTER.md"),
    ("C5", "docs", False, "Errata for misleading research wording (B31 registration, W-series)", "FAIL", "FAIL", "B31 done; W-series OPEN"),
]


def score(col: int) -> dict:
    cats = {}
    for c in WEIGHTS:
        rows = [r for r in REQ if r[1] == c]
        ok = sum(1 for r in rows if r[col] == V)
        cats[c] = {"verified": ok, "total": len(rows), "share": round(ok / len(rows), 4)}
    total = sum(WEIGHTS[c] * cats[c]["share"] for c in WEIGHTS)
    p0 = [r[0] for r in REQ if r[2] and r[col] != V]
    return {"categories": cats, "weighted_percent": round(100 * total, 1), "p0_not_verified": p0,
            "designation": "90% NOT ACHIEVED" if p0 or total < 0.90 else "90% ACHIEVED"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    out = {"weights": WEIGHTS, "production": score(4), "branch": score(5),
           "requirements": [dict(zip(("id", "category", "p0", "requirement", "production", "branch", "evidence"), r)) for r in REQ]}
    if a.json:
        with open(a.json, "w") as f:
            json.dump(out, f, indent=1)
    for k in ("production", "branch"):
        s = out[k]
        print(k, s["weighted_percent"], "%", s["designation"], "| P0 not verified:", s["p0_not_verified"],
              "|", {c: f"{v['verified']}/{v['total']}" for c, v in s["categories"].items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
