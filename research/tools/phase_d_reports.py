"""Phase D: the appendix generated from a registered run's outputs only (no hand-typed figure). Research only.

  python research/tools/phase_d_reports.py <phase_d_out> [--out research/PHASE_D_APPENDIX.md]

Every number below the header comes from data_report.json / study.json / dynamic.json / questions.json / m1.json, each
named with its SHA-256 so the appendix can be traced to the exact files (and, through phase_d_trials.jsonl, to the run).
Run research/tools/phase_d_audit.py first: an appendix is only written for a run whose audit passes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import phase_d_audit as AUD


def _p(x, d=1):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:.{d}f}%"


def _n(x, d=2, sign=True):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x:+.{d}f}" if sign else f"{x:.{d}f}"


def _ci(c):
    return "—" if not c or c[0] is None else f"{100 * c[0]:.1f}–{100 * c[1]:.1f}%"


def _load(out, name):
    p = os.path.join(out, name)
    if not os.path.exists(p):
        return None, None
    with open(p, "rb") as fh:
        b = fh.read()
    return json.loads(b), hashlib.sha256(b).hexdigest()


def data_section(rep: dict) -> list[str]:
    L = ["## 1. Data gates (per period)\n", ("| Period | Status | Units / $ | Median basis | Order-flow coverage | Quarantined days | "
                                             "Weeks checked / misaligned | Minute tied best | Failures |"), "|---|---|---|---|---|---|---|---|---|"]
    for k in ("DEV", "Y2026"):
        v = rep.get(k, {})
        c = v.get("clock_a1", {})
        w = c.get("weekly", {})
        L.append(f"| {k} | {v.get('status')} | {v.get('price_units_per_usd', '—')} | {_p(v.get('median_gap_rel'), 3)} | "
                 f"{_p(v.get('of_coverage_scored'))} | {len(v.get('integrity', {}).get('quarantined_days', []))} | "
                 f"{w.get('weeks_checked', '—')} / {len(w.get('misaligned_weeks', []))} | {c.get('minute', {}).get('tied_best', '—')} | "
                 f"{'; '.join(v.get('failures', [])) or 'none'} |")
    L.append(f"\nIntermarket: {rep.get('intermarket')}.\n")
    return L


def incremental_section(st: dict) -> list[str]:
    L = ["## 2. Incremental value over Baseline (out-of-sample log-loss per New York day)\n",
         "| Set / algorithm | Rows | Days | Δ log-loss | 95% interval | p | p (Holm over algorithms) | AUC TP Baseline | AUC TP set |",
         "|---|---|---|---|---|---|---|---|---|"]
    for k, v in sorted(st.get("incremental", {}).items()):
        ci = v.get("ci95") or [None, None]
        L.append(f"| {k} | {v.get('rows')} | {v.get('days', '—')} | {_n(v.get('delta_logloss'), 4)} | "
                 f"{_n(ci[0], 4)} … {_n(ci[1], 4)} | {_n(v.get('p'), 3, False)} | {_n(v.get('p_holm_over_algorithms'), 3, False)} | "
                 f"{_n(v.get('auc_tp_base'), 3, False)} | {_n(v.get('auc_tp_set'), 3, False)} |")
    nr = st.get("not_run") or {}
    L.append("\nNot run: " + (", ".join(f"{k} ({v})" for k, v in nr.items()) if nr else "none") + ".\n")
    return L


def strategy_section(st: dict, title: str) -> list[str]:
    L = [f"## {title}\n", ("| Strategy | Trades | Decided | TP-first (95%) | Random | Exp $/oz | PF | p | BH q=0.10 | "
                           "2026 trades | 2026 TP-first | 2026 exp | Holm p | C1 | C2 | C3 | C4 | C5 | C6 | QUALIFIES |"),
         "|---|" + "---|" * 19]
    for s in st.get("strategies", []):
        d, y, c = s["dev"], s.get("y2026") or {}, s["criteria"]
        tick = ["✓" if c.get(k) else "✗" for k in ("C1_positive_expectancy_dev_and_oos", "C2_beats_matched_random",
                                                    "C3_bh_and_reality_check", "C4_stable", "C5_independent_trades",
                                                    "C6_drawdown_ruin")]
        L.append(f"| {s['id']} | {d.get('n_trades')} | {d.get('n_decided')} | {_p(d.get('r'))} ({_ci(d.get('ci95'))}) | "
                 f"{_p(d.get('matched_random'))} | {_n(d.get('exp_oz'))} | {_n(d.get('pf'), 2, False)} | {_n(d.get('p_vs_random'), 4, False)} | "
                 f"{'yes' if s.get('bh_q010') else 'no'} | {y.get('n_trades', '—')} | {_p(y.get('r'))} | {_n(y.get('exp_oz'))} | "
                 f"{_n(s.get('y2026_holm_p'), 3, False)} | " + " | ".join(tick) + f" | {'**YES**' if c.get('QUALIFIES') else 'no'} |")
    fam = st.get("family", {})
    L.append(f"\nFamily: {fam.get('strategies')} strategies; BH passed {fam.get('bh_passed')}; Reality Check p = "
             f"{_n((fam.get('reality_check') or {}).get('p_value'), 3, False)}; frozen for 2026: {st.get('frozen') or 'none'}; "
             f"verdict: **{st.get('verdict')}**.\n")
    return L


def m1_section(m1: dict) -> list[str]:
    L = ["## 5. One-minute measurements (all-bar base rates, not selected strategies)\n"]
    for src, v in m1.items():
        L.append(f"### {src} ({v.get('source')}, {v.get('minutes')} minutes)\n")
        L.append("| Direction | B26 15m TP-first | 1m TP-first | B26 AMBIGUOUS resolved TP at 1m | Exp $/oz 15m model spread | Exp $/oz 1m real spread |")
        L.append("|---|---|---|---|---|---|")
        for dn in ("BUY", "SELL"):
            x = v.get(dn, {})
            L.append(f"| {dn} | {_p(x.get('benchmark_15m_b26', {}).get('r'))} | {_p(x.get('benchmark_1m', {}).get('r'))} | "
                     f"{_p(x.get('b26_ambiguous_resolved', {}).get('tp_share_at_1m'))} of {x.get('b26_ambiguous_resolved', {}).get('n')} | "
                     f"{_n(x.get('exp_oz_15m_model_spread'))} | {_n(x.get('exp_oz_1m_real_spread'))} |")
        L.append("\n| Direction | TP / SL | TP-first worst (95%) | best | Neither | Exp worst | Exp best |")
        L.append("|---|---|---|---|---|---|---|")
        for dn in ("BUY", "SELL"):
            for g, x in v.get(dn, {}).get("grid", {}).items():
                L.append(f"| {dn} | {g} | {_p(x.get('r'))} ({_ci(x.get('ci95'))}) | {_p(x.get('r_best'))} | {_p(x.get('neither_share'))} | "
                         f"{_n(x.get('exp_oz_worst'))} | {_n(x.get('exp_oz_best'))} |")
        L.append("")
    return L


def questions_section(q: dict) -> list[str]:
    L = ["## 6. Descriptive questions\n", "| Label | Resolution | Base rate (class 0) | Set / algorithm | AUC class 0 | Log-loss | Δ log-loss vs Baseline (p) |",
         "|---|---|---|---|---|---|---|"]
    for lab, v in q.get("labels", {}).items():
        for st_, algos in v.get("sets", {}).items():
            for a, m in (algos.items() if isinstance(algos, dict) and "not_run" not in algos else []):
                inc = (v.get("incremental") or {}).get(f"{st_}/{a}", {})
                L.append(f"| {lab} | {v['info'].get('resolution')} | {_p(v.get('base_rate_class0'))} | {st_}/{a} | "
                         f"{_n(m.get('auc_tp_vs_rest'), 3, False)} | {_n(m.get('logloss'), 4, False)} | "
                         f"{_n(inc.get('delta_logloss'), 4)} ({_n(inc.get('p'), 3, False)}) |")
    L.append(f"\nDelay one bar (paired net change, $/oz): {json.dumps(q.get('delay'))}\n")
    return L


def render(out: str) -> str:
    rep, h_rep = _load(out, "data_report.json")
    st, h_st = _load(out, "study.json")
    dyn, h_dyn = _load(out, "dynamic.json")
    q, h_q = _load(out, "questions.json")
    m1, h_m1 = _load(out, "m1.json")
    L = ["# Phase D appendix (generated)\n", "Generated by `research/tools/phase_d_reports.py` from the registered run's outputs only. Sources:\n"]
    for nm, h in (("data_report.json", h_rep), ("study.json", h_st), ("dynamic.json", h_dyn), ("questions.json", h_q), ("m1.json", h_m1)):
        L.append(f"- `{nm}`: {h or 'not produced'}")
    L.append("")
    L += data_section(rep)
    if st is None:
        L.append("**INSUFFICIENT DATA — RESEARCH INCOMPLETE**: a development data gate failed; no study was run.\n")
        return "\n".join(L)
    L += incremental_section(st)
    L += strategy_section(st, "3. The order-flow-informed ±$15 family (benchmark labels)")
    for k, v in (dyn or {}).items():
        if isinstance(v, dict) and "strategies" in v:
            L += strategy_section(v, f"4. Dynamic TP / SL family {k} (its own family)")
        elif k == "not_run":
            L.append(f"## 4. Dynamic TP / SL family\n\nNOT RUN: {v}\n")
    L += m1_section(m1 or {})
    L += questions_section(q or {})
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--log", default=os.path.join("research", "phase_d_trials.jsonl"))
    ap.add_argument("--md", default=os.path.join("research", "PHASE_D_APPENDIX.md"))
    a = ap.parse_args(argv)
    au = AUD.audit(a.out, a.log)
    if not au["pass"]:
        print("the D4 audit failed; no appendix written:", json.dumps({k: v["pass"] for k, v in au["checks"].items() if isinstance(v, dict)}))
        return 1
    with open(a.md, "w") as fh:
        fh.write(render(a.out))
    print(f"written {a.md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
