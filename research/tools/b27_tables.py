"""Markdown tables for research/B27_RESULTS.md, read straight from research/results/b27/b27_summary.json (no number is
typed by hand).

  python research/tools/b27_tables.py research/results/b27/b27_summary.json
"""
import json
import sys


def pct(x, d=1):
    return "—" if x is None else f"{100 * x:.{d}f}%"


def num(x, d=2, sign=False):
    if x is None:
        return "—"
    return f"{x:+.{d}f}" if sign else f"{x:.{d}f}"


def ci(c):
    return "—" if not c or c[0] is None else f"{100 * c[0]:.1f}–{100 * c[1]:.1f}"


def row(cells):
    return "| " + " | ".join(str(c) for c in cells) + " |"


def main(path: str) -> None:
    with open(path) as fh:
        s = json.load(fh)
    print("## Baseline (independent trades, ENG)\n")
    print(row(["Population", "BUY r (95%)", "SELL r (95%)", "BUY n", "SELL n", "BUY exp/oz", "SELL exp/oz"]))
    print(row(["---"] * 7))
    for p in ("DEV", "Y2026", "Y2026_5m"):
        b, s_ = s["baseline"][f"{p} BUY"], s["baseline"][f"{p} SELL"]
        print(row([p, f"{pct(b['r'])} ({ci(b['ci95'])})", f"{pct(s_['r'])} ({ci(s_['ci95'])})", b["n_decided"], s_["n_decided"],
                   num(b["exp_oz"], sign=True), num(s_["exp_oz"], sign=True)]))
    print("\n## Counts\n")
    print(row(["Study", "Tested", "BH-significant", "INFORMATIVE", "TRADEABLE"]))
    print(row(["---"] * 5))
    for k, v in s["counts"].items():
        print(row([k, v["tested"], v["bh"], v["informative"], v["tradeable"]]))

    print("\n## Leaderboard (frozen on development; 2026 is the check)\n")
    print(row(["Candidate", "Board", "Dev r (95%)", "Dev n", "Dev random", "Dev exp/oz", "PF", "Trades/wk", "DD 0.5 lot (MC95)",
               "Min", "2026 r (95%)", "2026 n", "2026 random", "2026 exp/oz", "Holm p", "Holds", "2026 5m r (n)"]))
    print(row(["---"] * 17))
    for c in s["frozen"]:
        d, y, y5 = c["dev"], c.get("y2026") or {}, c.get("y2026_5m") or {}
        print(row([c["id"], c["board"], f"{pct(d['r'])} ({ci(d['ci95'])})", d["n_decided"], pct(d["matched_random"]), num(d["exp_oz"], sign=True),
                   num(d["pf"]), num(d["per_week"], 1), f"{num(d['max_dd_050lot_ASSUMED'], 0)} ({num(d.get('mc_dd95_050lot_ASSUMED'), 0)})",
                   num(d["minutes_median"], 0), f"{pct(y.get('r'))} ({ci(y.get('ci95'))})", y.get("n_decided"), pct(y.get("matched_random")),
                   num(y.get("exp_oz"), sign=True), num(c.get("y2026_holm_p"), 3), "yes" if c.get("holds_2026") else "no",
                   f"{pct(y5.get('r'))} ({y5.get('n_decided', '—')})"]))

    print("\n## S2 confirmation distance, every hour (development)\n")
    print(row(["Mode", "BUY r", "BUY n", "BUY fill", "BUY exp/trigger", "SELL r", "SELL n", "SELL exp/trigger", "MAE", "min to TP"]))
    print(row(["---"] * 10))
    s2 = {c["id"]: c["dev"] for c in s["S2"]}
    modes = ["IMM"] + [f"{m}_{x}" for m in ("CONF", "RETEST", "STOP") for x in (3, 5, 7, 10, 12, 15, 20)]
    for m in modes:
        b, s_ = s2.get(f"S2 EVERY_HOUR {m} BUY"), s2.get(f"S2 EVERY_HOUR {m} SELL")
        if not b or not s_:
            continue
        print(row([m, pct(b["r"]), b["n_decided"], pct(b["fill_rate"], 0), num(b["exp_per_trigger_oz"], sign=True), pct(s_["r"]),
                   s_["n_decided"], num(s_["exp_per_trigger_oz"], sign=True), num(b["mae_mean"]), num(b["minutes_tp_median"], 0)]))

    print("\n## S2 best mode per trigger family (development, by Wilson lower bound, n >= 300)\n")
    print(row(["Family", "Dir", "Best mode", "r (95%)", "n", "random", "exp/oz", "IMM r", "triggers"]))
    print(row(["---"] * 9))
    fams = sorted({c["family"] for c in s["S2"]})
    for f in fams:
        for dn in ("BUY", "SELL"):
            cs = [c for c in s["S2"] if c["family"] == f and c["dir"] == dn and (c["dev"]["n_decided"] or 0) >= 300]
            if not cs:
                continue
            best = max(cs, key=lambda c: c["dev"]["ci95"][0])
            imm = s2.get(f"S2 {f} IMM {dn}", {})
            print(row([f, dn, best["mode"], f"{pct(best['dev']['r'])} ({ci(best['dev']['ci95'])})", best["dev"]["n_decided"],
                       pct(best["dev"]["matched_random"]), num(best["dev"]["exp_oz"], sign=True), pct(imm.get("r")), best["dev"]["n_triggers"]]))

    print("\n## S3 models (walk-forward 2021-01 .. 2023-01)\n")
    print(row(["Model", "AUC", "AUC BUY", "AUC SELL", "Brier", "Brier const", "top 1% BUY r (n)", "top 1% SELL r (n)", "top 10% BUY r",
               "top 10% SELL r"]))
    print(row(["---"] * 10))
    s3 = {c["id"]: c["dev"] for c in s["S3"]}
    for m, v in s["S3_models"].items():
        def g(q, dn, m=m):
            return s3.get(f"S3 {m} top{q}% {dn}", {})

        print(row([m, num(v["auc"], 4), num(v["auc_buy"], 4), num(v["auc_sell"], 4), num(v["brier"], 4), num(v["brier_constant"], 4),
                   f"{pct(g(1, 'BUY').get('r'))} ({g(1, 'BUY').get('n_decided')})", f"{pct(g(1, 'SELL').get('r'))} ({g(1, 'SELL').get('n_decided')})",
                   pct(g(10, "BUY").get("r")), pct(g(10, "SELL").get("r"))]))
    print("\nReliability (ENS, walk-forward): " + "; ".join(f"{pct(b['p_mean'])}→{pct(b['observed'])}" for b in s["S3_models"]["ENS"]["reliability"]))

    print("\n## S4 ranking\n")
    print(row(["Family dropped", "AUC without", "Change"]))
    print(row(["---"] * 3))
    for f, v in s["S4"]["ablation"].items():
        print(row([f, num(v["auc_without"], 4), num(v["change"], 4, sign=True)]))
    perm = sorted(s["S4"]["permutation_auc_drop"].items(), key=lambda kv: -kv[1])[:12]
    print("\nPermutation AUC drop (top 12): " + "; ".join(f"{k} {v:+.4f}" for k, v in perm))
    uni = sorted(s["S4"]["univariate_auc"].items(), key=lambda kv: -abs((kv[1] or 0.5) - 0.5))[:12]
    print("\nUnivariate AUC furthest from 0.5 (top 12): " + "; ".join(f"{k} {v:.4f}" for k, v in uni))

    print("\n## S5 regimes (development)\n")
    print(row(["Regime", "BUY r (95%)", "BUY n", "BUY random", "SELL r (95%)", "SELL n", "SELL random"]))
    print(row(["---"] * 7))
    s5 = {c["id"]: c["dev"] for c in s["S5"]}
    for reg in sorted({c["regime"] for c in s["S5"]}):
        b, s_ = s5.get(f"S5 {reg} BUY", {}), s5.get(f"S5 {reg} SELL", {})
        print(row([reg, f"{pct(b.get('r'))} ({ci(b.get('ci95'))})", b.get("n_decided"), pct(b.get("matched_random")),
                   f"{pct(s_.get('r'))} ({ci(s_.get('ci95'))})", s_.get("n_decided"), pct(s_.get("matched_random"))]))

    print("\n## S6 intermarket, 2026 (descriptive)\n")
    print(row(["Series / quintile", "r", "n", "random", "BH"]))
    print(row(["---"] * 5))
    for k, v in s["S6_intermarket_2026_descriptive"].items():
        print(row([k, pct(v["r"]), v["n_decided"], pct(v["matched_random"]), "yes" if v.get("bh") else "no"]))


if __name__ == "__main__":
    main(sys.argv[1])
