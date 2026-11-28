"""The 15-item final audit (operator mandate 2026-11-28, Part 6), generated from evidence files only.

  python audit/tools/final_audit_doc.py [--root <repo>] [--check]

Reads the files named in FILES under docs/final_audit/evidence/ (and the gap register), writes OUT. Every number in the
document is read from those files; a file that does not exist yet makes its item PENDING, never a typed-in number.
--check exits 1 if the document on disk differs from what the files give.

Status words used for each item, as the mandate asks:
  VERIFIED            executed, with an independent check or a test named
  MODELLED            computed with a model input that is not verified (the engine's cost of record; $650 per R)
  ASSUMPTION          an input taken as given, named
  UNVERIFIED          not checked, or not observable by the system
  INSUFFICIENT SAMPLE fewer trades than the stated minimum
  PENDING             waits for an event or a computation still running
  BLOCKED             needs something from outside this session (operator data, network hosts)
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, ROOT)
from quantum import config  # the engine's cost of record, read rather than retyped

EV = "docs/final_audit/evidence"
DAY = "2026-11-28"
FILES = {
    "score": f"{EV}/weighted_score_{DAY}.json", "inventory": f"{EV}/change_inventory_{DAY}.json",
    "fwd": f"{EV}/forward_report_{DAY}.json", "matched": f"{EV}/forward_matched_{DAY}.json",
    "matched_mut": f"{EV}/forward_matched_mutation_{DAY}.json", "risk": f"{EV}/g5_risk_analytics_{DAY}.json",
    "delivery": f"{EV}/delivery_status_{DAY}.json", "trace": f"{EV}/delivery_429_trace_{DAY}.json",
    "protected": f"{EV}/protected_check_{DAY}_final.json", "g6_dev": f"{EV}/g6_dev_primary_{DAY}.json",
    "g6_dev_a1": f"{EV}/g6_dev_a1_{DAY}.json", "g6_fwd_a1": f"{EV}/g6_forward_a1_{DAY}.json",
    "g5sens": f"{EV}/g5_sens_results_{DAY}.json", "reopen": f"{EV}/reopen_dryrun_2026-11-22.json",
}
TEXT = {"ledger_check": f"{EV}/ledger_check_{DAY}.txt", "register": "docs/final_audit/GAP_REMEDIATION_REGISTER.md"}
SUITES = f"{EV}/suite_*_{DAY}.txt"
OUT = f"docs/final_audit/FINAL_AUDIT_{DAY}.md"
MIN_N = 30


def read(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return fh.read()


def load(root: str) -> dict:
    d = {}
    for k, v in FILES.items():
        t = read(os.path.join(root, v))
        d[k] = json.loads(t) if t is not None else None
    for k, v in TEXT.items():
        d[k] = read(os.path.join(root, v))
    d["suites"] = {os.path.basename(p): read(p) for p in sorted(glob.glob(os.path.join(root, SUITES)))}
    return d


def pct(x):
    return "n/a" if x is None else f"{100 * x:.1f}%"


def ci(x):
    return "n/a" if not x or x[0] is None or x[1] is None else f"[{x[0]:+.4f}, {x[1]:+.4f}]"


def num(x, nd=4):
    return "n/a" if x is None else f"{x:+.{nd}f}"


def src(*keys):
    return "Source: " + ", ".join(f"`{FILES.get(k) or TEXT.get(k) or k}`" for k in keys) + "."


def pending(L, what):
    L += [f"**Status: PENDING.** {what}", ""]


# ---------------- A. Engineering ----------------
def item1_2(L, d):
    s = d["score"]
    for n, col, title in ((1, "production", "Current production completeness"), (2, "branch", "Current remediation completeness")):
        L.append(f"### {n}. {title}")
        L.append("")
        if not s:
            pending(L, "weighted score not yet computed")
            continue
        x = s[col]
        L += [(f"**{x['weighted_percent']}%** weighted engineering verification; designation **{x['designation']}**. "
               f"P0 requirements not verified: {', '.join(x['p0_not_verified']) or 'none'}. Status: VERIFIED (computed "
               f"from the requirement list and its evidence; the list is unchanged since 26 Nov so scores compare)."), "",
              "| Category | Weight | Verified |", "|---|---|---|"]
        L += [f"| {c} | {s['weights'][c]:.2f} | {v['verified']} of {v['total']} |" for c, v in x["categories"].items()]
        if n == 1:
            L += ["", "Earlier: " + "; ".join(f"{p['date']} at `{p['production_commit']}`: production {p['production']}%, "
                                               f"branch {p['branch']}%" for p in s["previous"]) + "."]
        L += ["", src("score"), ""]


def register_rows(text: str) -> tuple[dict, list[dict]]:
    """Gap IDs with their priority and status from the register's P0 / P1 / P2 tables, then the 28 Nov update rows."""
    gaps, upd, pri = {}, [], None
    section = None
    for line in text.splitlines():
        if line.startswith("## Priority "):
            pri, section = "P" + line.split()[-1], "base"
        elif line.startswith("## Update, 28 Nov"):
            section = "update"
        elif line.startswith("## "):
            section = None
        m = re.match(r"\| (GA-\d+(?: / GA-\d+)?)(?: \*\(new\)\*)? \|", line)
        if not m or section is None:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if section == "base":
            gaps[m.group(1)] = {"priority": pri, "status": cells[-1], "gap": cells[1]}
        else:
            upd.append({"id": m.group(1), "priority": cells[1], "change": cells[2], "evidence": cells[3], "status": cells[4]})
    return gaps, upd


def item3(L, d):
    L += ["### 3. Remaining P0, P1 and P2 gaps", ""]
    if not d["register"]:
        pending(L, "gap register missing")
        return
    gaps, upd = register_rows(d["register"])
    for u in upd:
        gaps[u["id"]] = {"priority": u["priority"], "status": u["status"], "gap": u["change"]}
    open_ = {k: v for k, v in gaps.items() if not v["status"].startswith("VERIFIED")}
    L += [(f"{len(gaps)} gaps in the register, {len(open_)} not verified. Status: VERIFIED as a register (each row names "
           "its evidence); the statuses themselves are those in the register."), "",
          "| Priority | Gap | Status |", "|---|---|---|"]
    for p in ("P0", "P1", "P2"):
        L += [f"| {p} | {k} | {v['status']} |" for k, v in sorted(open_.items()) if v["priority"] == p]
    L += ["", "Changes recorded on 28 Nov:", ""]
    L += [f"- **{u['id']}** ({u['priority']}): {u['change']} *{u['status']}*" for u in upd]
    L += ["", src("register"), ""]


def item4_5(L, d):
    inv = d["inventory"]
    L += ["### 4. Exact files and functions changed", ""]
    if not inv:
        pending(L, "change inventory not yet collected")
        L += ["### 5. Commit hashes and pull requests", ""]
        pending(L, "change inventory not yet collected")
        return
    L += [(f"From git alone (`audit/tools/change_inventory.py`): production head `{inv['base_head']}`. Functions are "
           "compared by their source text. Status: VERIFIED (generated from git)."), ""]
    groups = [(f"PR #{m['pr']} (merged {m['merged_utc'][:10]}, `{m['merge']}`)", m) for m in inv["merged"]] + \
             [(f"Open branch {o['name']} (`{o['head']}`, not merged)", o) for o in inv["open"]]
    for title, g in groups:
        L += [f"**{title}**: {g['shortstat']}", ""]
        for f in g["files"]:
            fx = []
            for k, lab in (("functions_added", "added"), ("functions_changed", "changed"), ("functions_removed", "removed")):
                if f.get(k):
                    fx.append(f"{lab}: {', '.join(f[k])}")
            L.append(f"- `{f['status']}` `{f['path']}`" + (f" ({'; '.join(fx)})" if fx else ""))
        L.append("")
    L += [src("inventory"), "", "### 5. Commit hashes and pull requests", ""]
    L += ["| Change | Commits |", "|---|---|"]
    for title, g in groups:
        L.append(f"| {title} | " + "<br>".join(f"`{c}`" for c in g["commits"]) + " |")
    L += ["", src("inventory"), ""]


def item6(L, d):
    L += ["### 6. Test results and skipped-test explanations", ""]
    if not d["suites"]:
        pending(L, "suite logs not yet collected")
        return
    L += ["| Branch run | Result | Skipped (reason) |", "|---|---|---|"]
    for name, txt in d["suites"].items():
        tail = [x for x in txt.splitlines() if re.search(r"\d+ (passed|failed)", x)]
        skips = re.findall(r"SKIPPED \[\d+\] ([^\n]+)", txt)
        L.append(f"| `{name}` | {tail[-1].strip('= ') if tail else 'n/a'} | {'; '.join(skips) or 'none'} |")
    L += ["", "Status: VERIFIED (each line is the suite's own summary; logs in the evidence folder).", ""]


# ---------------- B. Trading performance ----------------
def item7(L, d):
    L += ["### 7. Strategy-wise and timeframe-wise forward performance", ""]
    f, m = d["fwd"], d["matched"]
    if not f:
        pending(L, "forward report not yet produced")
        return
    L += [(f"Every live ledger under the current engine key `{f['key']}` (forward window from {f['freeze_utc'][:10]}). "
           f"Net R is after the engine's MODELLED cost. Ledgers under {MIN_N} trades are INSUFFICIENT SAMPLE: their "
           "figures are shown, but nothing is concluded from them."), "",
          "| Ledger | n | Win rate | Mean net R | 95% (trades) | 95% (days) | Sum R | Max DD R | PF | Status |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in sorted(f["ledgers"].items(), key=lambda kv: -kv[1]["trades"]):
        st = "INSUFFICIENT SAMPLE" if v["trades"] < MIN_N else "MODELLED cost"
        L.append(f"| {k} | {v['trades']} | {pct(v['win_rate'])} | {num(v['mean_r'])} | {ci(v['mean_r_boot95_trades'])} | "
                 f"{ci(v['mean_r_boot95_days'])} | {v['sum_r']:+.2f} | {v['max_drawdown_r']:.2f} | "
                 f"{v['profit_factor'] if v['profit_factor'] is not None else 'n/a'} | {st} |")
    if m:
        a = m["all"]["replay_agrees_with_record"]
        L += ["", (f"Independent check: re-deriving every recorded trade from the raw 5-minute bars under the fixed exit "
                   f"rules reproduces **{a['agree']} of {a['replayed']}** recorded net R values (GA-31 lists the rest). "
                   "The records are VERIFIED to that extent.")]
    L += ["", src("fwd", "matched"), ""]


def item8(L, d):
    L += ["### 8. Properly matched random-entry comparisons", ""]
    m = d["matched"]
    if not m:
        pending(L, "matched comparison not yet produced")
        return
    L += [(f"Each recorded trade against {m['k']} random entries matched on timeframe grid, New York clock time (60 "
           "minutes either side, another day), direction, stop / TP1 / TP2 distances, cost and holding period, all "
           "managed by the same fixed exit rules (`audit/tools/forward_matched.py`, method fixed before its first run; "
           f"seed {m['seed']}). Tested: ledgers with {m['min_n']}+ trades. Status: VERIFIED method (replay equals the "
           "production exit model on 200+ random paths in the tests; "
           f"{sum(x['killed'] for x in d['matched_mut']['mutants']) if d['matched_mut'] else 'n/a'} of "
           f"{len(d['matched_mut']['mutants']) if d['matched_mut'] else 'n/a'} mutants killed); costs MODELLED."), "",
          "| Ledger | n | Recorded mean R | Matched random mean R | Recorded - random [95% days] | p (one-sided) | Holm | BH | Verdict |",
          "|---|---|---|---|---|---|---|---|---|"]
    for k in m["tested_ledgers"]:
        v = m["ledgers"][k]
        r = v["recorded_minus_random"]
        L.append(f"| {k} | {v['trades']} | {num(v['net_r_modelled_cost']['mean'])} | "
                 f"{num(v['matched_random_r']['mean_of_trade_means'])} | {num(r['mean'])} {ci(r.get('ci95_days'))} | "
                 f"{r.get('p_le_0')} | {r.get('p_holm')} | {r.get('p_bh')} | **{v['verdict']}**"
                 + (" (recorded BELOW matched random: interval under zero)" if r.get("ci95_days") and r["ci95_days"][1] < 0 else "")
                 + " |")
    a = m["all"]
    L += ["", (f"All {a['trades']} forward trades: recorded {num(a['net_r_modelled_cost']['mean'])} R, matched random "
               f"{num(a['matched_random_r']['mean_of_trade_means'])} R, difference {num(a['recorded_minus_random']['mean'])} "
               f"{ci(a['recorded_minus_random'].get('ci95_days'))}. Untested ledgers ({len(m['ledgers']) - len(m['tested_ledgers'])}): "
               "INSUFFICIENT SAMPLE.")]
    edges = [k for k in m["tested_ledgers"] if m["ledgers"][k]["verdict"].startswith("EDGE")]
    L += ["", f"**Overall: {'EDGE on ' + ', '.join(edges) if edges else 'NO EDGE — INSUFFICIENT EVIDENCE'}.**", "", src("matched"), ""]


def item9(L, d):
    L += ["### 9. Before-cost and after-cost expectancy", ""]
    m, f = d["matched"], d["fwd"]
    if not m:
        pending(L, "matched comparison not yet produced")
        return
    L += ["| Ledger | n | Gross R [95% days] | Net R, modelled cost [95% days] | Net R, measured cost | Net R at $0.50 / $0.80 spread |",
          "|---|---|---|---|---|---|"]
    for k in m["tested_ledgers"]:
        v = m["ledgers"][k]
        s = (f["ledgers"].get(k) or {}).get("mean_r_at_spread", {}) if f else {}
        L.append(f"| {k} | {v['trades']} | {num(v['gross_r']['mean'])} {ci(v['gross_r'].get('ci95_days'))} | "
                 f"{num(v['net_r_modelled_cost']['mean'])} {ci(v['net_r_modelled_cost'].get('ci95_days'))} | UNAVAILABLE (G2) | "
                 f"{num(s.get('spread_0.50'))} / {num(s.get('spread_0.80'))} |")
    a = m["all"]
    L += ["", (f"All trades: gross {num(a['gross_r']['mean'])} {ci(a['gross_r'].get('ci95_days'))}, net "
               f"{num(a['net_r_modelled_cost']['mean'])} {ci(a['net_r_modelled_cost'].get('ci95_days'))}. Gross and net are "
               f"VERIFIED arithmetic on the records; the cost is MODELLED (quantum/config.py: spread_cost "
               f"{config.DEFAULT.spread_cost}, slippage_pts {config.DEFAULT.slippage_pts} per side, commission_l "
               f"{config.DEFAULT.commission_l} per lot, with the session spread floor); measured-cost expectancy is "
               "BLOCKED on the broker data (item 15)."), "", src("matched", "fwd"), ""]


def item10(L, d):
    L += ["### 10. Confidence intervals and multiple-testing corrections", ""]
    m = d["matched"]
    lines = []
    if m:
        lines.append(f"- Forward matched comparison: {len(m['tested_ledgers'])} tests, Holm and BH across them (item 8); "
                     "intervals resample whole New York trading days, because trades on one day share the day's move.")
    g6 = d["g6_dev"]
    if g6:
        n = sum(1 for c in g6["comparisons"] for k in ("mean_net_r_per_trade", "net_r_per_day") if c[k]["p_holm"] < 0.05)
        lines.append(f"- G6 exposure policies (development, primary family): 10 tests, {n} with Holm p < 0.05; paired "
                     "day-block bootstrap (research/G6_EXPOSURE_RESULTS.md on the G6 branch).")
    gs = d["g5sens"]
    lines.append("- G5-SENS parameter sensitivity: " + (f"{gs.get('cells_run')} cells, Holm and BH across them."
                                                         if gs else "PENDING (the run is still computing)."))
    L += lines + ["", ("Status: VERIFIED for the corrections listed; a program-level correction over every trial ever run "
                      "remains OPEN (GA-02)."), ""]


def item11(L, d):
    L += ["### 11. Target-before-stop probabilities for +$10, +$15 and +$20", ""]
    m = d["matched"]
    if not m:
        pending(L, "matched comparison not yet produced")
        return
    L += [("From the fill, on 5-minute bars, before the trade's ORIGINAL stop, within 7 days; a bar touching both counts "
           "as the stop. Random = the matched entries of item 8. Wilson 95% for the rates; the matched difference is "
           "per trade (hit minus its matches' rate) with a day-block interval."), "",
          "| Ledger | Target | Decided | Rate [Wilson 95%] | Matched random rate | Difference [95% days] |", "|---|---|---|---|---|---|"]
    for k in [*m["tested_ledgers"], "all"]:
        v = m["all"] if k == "all" else m["ledgers"][k]
        for x in ("usd10", "usd15", "usd20"):
            r = v["target_before_stop"][x]
            L.append(f"| {k} | +${x[3:]} | {r['decided']} | {pct(r['rate'])} {r['wilson95']} | {pct(r['random_rate'])} | "
                     f"{num(r['matched_difference'].get('mean'))} {ci(r['matched_difference'].get('ci95_days'))} |")
    L += ["", ("A target-hit percentage alone is not an edge (Part 7): the rate is set mostly by the distance to the stop, "
               "which the random entries share. Status: VERIFIED arithmetic; the comparison is the evidence."), "",
          src("matched"), ""]


def item12(L, d):
    L += ["### 12. MAE, MFE and time-to-target", ""]
    m = d["matched"]
    if not m:
        pending(L, "matched comparison not yet produced")
        return
    L += ["| Ledger | n | MFE median / p75 ($) | MAE median / p75 ($) | MFE >= $10 / $15 / $20 | Minutes to +$10 / +$15 / +$20 (median) |",
          "|---|---|---|---|---|---|"]
    for k in [*m["tested_ledgers"], "all"]:
        v = m["all"] if k == "all" else m["ledgers"][k]
        x = v["mfe_mae_usd"]
        t = v["target_before_stop"]
        L.append(f"| {k} | {v['trades']} | {x['mfe_median']} / {x['mfe_p75']} | {x['mae_median']} / {x['mae_p75']} | "
                 f"{pct(x['share_mfe_ge']['10'])} / {pct(x['share_mfe_ge']['15'])} / {pct(x['share_mfe_ge']['20'])} | "
                 f"{t['usd10']['minutes_to_target_median']} / {t['usd15']['minutes_to_target_median']} / "
                 f"{t['usd20']['minutes_to_target_median']} |")
    L += ["", ("MFE / MAE over the trade's own life, from 5-minute highs and lows (USD per ounce). Minutes are counted "
               "for trades that reached the target first. Status: VERIFIED arithmetic (tests by hand)."), "", src("matched"), ""]


# ---------------- C. Risk and execution ----------------
def item13(L, d):
    L += ["### 13. CVaR, Monte Carlo drawdown and aggregate exposure", ""]
    r = d["risk"]
    if r:
        L += [("Per ledger with 30+ trades (G5, `audit/tools/risk_analytics.py`): CVaR 5% = mean of the worst 5%; Monte "
               "Carlo = stationary day-block bootstrap. The $ column is MODELLED at the ASSUMPTION of $650 per R."), "",
              "| Arm · TF | n | CVaR 5% per trade R | CVaR 5% per day R | Max DD observed R | MC max DD p95 R (L = 2 d) | MC p95 $ at $650/R |",
              "|---|---|---|---|---|---|---|"]
        for g in sorted(r["groups"].values(), key=lambda g: -g["n"]):
            if g["n"] >= MIN_N:
                mc = g["monte_carlo_drawdown"].get("L=2d") or {}
                L.append(f"| {g['arm']} · {g['tf']} | {g['n']} | {g['tail_per_trade_net_r']['cvar']} | "
                         f"{g['tail_per_day_net_r']['cvar']} | {g['observed_max_drawdown_r']} | {mc.get('p95_r')} | "
                         f"{mc.get('p95_usd_at_650_per_r')} |")
        L += ["", src("risk"), ""]
    f = d["g6_fwd_a1"]
    if f:
        c, b = f["concurrency"], f["book"]
        L += [(f"Aggregate exposure (G6, amendment A1, all live arms 5m-4h, forward, descriptive): {f['positions']} "
               f"positions; mean open {c['open_positions']['mean']:.2f}; at most {c['exact']['max_open']} open at once "
               f"(MODELLED ${c['combined_stop_r']['max_usd_if_every_position_risked_650']:,.0f} if every one were taken at "
               f"$650); 2+ open in one direction {pct(c['share_of_time_two_plus_same_direction'])} of the time; up to "
               f"{b['potential_daily_loss_r']['max']} entries in one day; longest losing streak "
               f"{b['longest_losing_streak']}; combined drawdown {b['max_dd_r']:.2f} R. The operator takes one trade at a "
               "time, so these figures describe the alert stream, not an account.")]
    g = d["g6_dev"]
    if g:
        p = g["policies"]
        L += ["", "Development (G6 primary family), the five exposure policies: " + "; ".join(
            f"{k.split('_')[0]} mean {v['book']['mean_net_r']:+.4f} R over {v['book']['trades']:,} trades"
            for k, v in p.items()) + ". Every mean is negative: a policy chooses how much of a losing stream is taken; "
            "none is an edge, and none is proposed."]
    if not (r or f or g):
        pending(L, "risk and exposure evidence not yet collected")
    L += ["", src("g6_fwd_a1", "g6_dev"), ""]


def item14(L, d):
    L += ["### 14. Alert reliability, delivery failures and recovery statistics", ""]
    e = d["delivery"]
    if not e:
        pending(L, "delivery report not yet produced")
        return
    s = e["status_distribution"]
    L += [(f"{e['messages']} messages ({e['attempt_records']} send attempts) in the forward-ledger delivery log. "
           f"SENT_TO_NTFY: {s['SENT_TO_NTFY']}. SEND_FAILED: {s['SEND_FAILED']}. RETRY_ATTEMPTED: {s['RETRY_ATTEMPTED']}. "
           f"PHONE_DELIVERY and PHONE_DISPLAY: NOT_VERIFIABLE on every message (ntfy confirms its server only). Stored vs "
           f"recomputed status disagreements: {e['stored_vs_recomputed_disagreements']}."), "",
          "| Stream | Messages | Accepted by ntfy | Send failed | Retried |", "|---|---|---|---|---|"]
    for k, v in e["by_stream"].items():
        L.append(f"| {k} | {v['messages']} | {v.get('SENT_TO_NTFY=YES', 0)} | {v.get('SEND_FAILED=YES', 0)} | "
                 f"{v.get('RETRY_ATTEMPTED=YES', 0)} |")
    t = d["trace"]
    if t:
        L += ["", "Rate-limit (HTTP 429) attempts and the messages that carried the pending warnings:", "",
              "| Run (UTC) | Stream | Attempt | HTTP | State | Note | Warnings carried |", "|---|---|---|---|---|---|---|"]
        L += [f"| {x['t_run_utc'][:19]} | {x['stream']} | {x['attempt']} | {x['http']} | {x['state']} | "
              f"{x.get('no_retry') or ''} | {x.get('warnings_carried')} |" for x in t["records"]]
        L += ["", ("Recovery: a lost message is not re-sent; its loss is disclosed as a warning in the next delivered "
                   "message. Status: P0 requirement A5 (no lost alert) FAILED live after the fix (GA-07); device delivery "
                   "UNVERIFIED by design.")]
    L += ["", src("delivery", "trace"), ""]


def item15(L, d):
    L += ["### 15. Broker-cost validation, data integrity and outstanding requirements", ""]
    L += [("**Broker costs (G2, FundingPips MT5): BLOCKED.** Every cost in this audit is MODELLED. Needed from the "
          "operator: the MT5 XAUUSD symbol specification (contract size, tick size and value, volume minimum, maximum "
          "and step), an account statement with fills, spread samples in the Asian, London and New York sessions, the "
          "commission basis (USD per lot, per side or round turn), swap, slippage, and what the stated \"02 pips\" "
          "measures."), ""]
    lc = d["ledger_check"]
    if lc:
        prob = re.findall(r"problems: (\d+)", lc)
        L.append(f"- Ledger consistency (`ledger_check.py`): problems **{prob[-1] if prob else 'n/a'}**. VERIFIED.")
    m = d["matched"]
    if m:
        a = m["all"]["replay_agrees_with_record"]
        L.append(f"- Raw-bar re-derivation of the forward record: {a['agree']} of {a['replayed']} trades equal. VERIFIED (GA-31 open for the rest).")
    p = d["protected"]
    if p:
        L.append(f"- Protected state (`protected_check.py`): **{p.get('verdict')}**; freeze key "
                 f"`{p['checks']['freeze_key']['found']}`. VERIFIED.")
    rp = d["reopen"]
    L.append("- Sunday reopening (Part 2): dry run on 22 Nov " + (f"verdict **{rp.get('verdict')}**" if rp else "n/a") +
             "; the 29 Nov reopening is **PENDING** (records exist only after 2026-11-29 23:00 UTC).")
    L.append("- G3 news timestamps: **BLOCKED** (GA-30). G5-SENS: " + ("done" if d["g5sens"] else "**PENDING** (computing)") + ".")
    L += ["", src("ledger_check", "matched", "protected", "reopen"), ""]


def build(d: dict) -> str:
    L = [f"# Final audit, 15 items ({DAY})", "",
         ("Generated by `audit/tools/final_audit_doc.py` from the evidence files named under each item; `--check` "
          "confirms this file matches them. Operator mandate 2026-11-28, Part 6. Engineering and trading results are kept "
          "apart and never combined."), "",
         ("Status words: **VERIFIED** (executed and independently checked), **MODELLED** (uses an unverified model input: "
          "the engine's cost of record, $650 per R), **ASSUMPTION** (an input taken as given), **UNVERIFIED** (not checked "
          "or not observable), **INSUFFICIENT SAMPLE** (fewer than 30 trades), **PENDING** (waits for an event or a "
          "computation), **BLOCKED** (needs operator data or network access)."), "",
         "## A. Engineering", ""]
    item1_2(L, d)
    item3(L, d)
    item4_5(L, d)
    item6(L, d)
    L += ["## B. Trading performance", ""]
    for f in (item7, item8, item9, item10, item11, item12):
        f(L, d)
    L += ["## C. Risk and execution", ""]
    for f in (item13, item14, item15):
        f(L, d)
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    doc = build(load(a.root))
    out = os.path.join(a.root, OUT)
    if a.check:
        same = read(out) == doc
        print("document matches the evidence" if same else "document DIFFERS from the evidence")
        return 0 if same else 1
    with open(out, "w") as fh:
        fh.write(doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
