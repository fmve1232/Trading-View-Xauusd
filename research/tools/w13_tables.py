"""Markdown tables from the B31b-W13 result JSON (every number printed comes from the file).

  python research/tools/w13_tables.py research/results/b31b_w13_development_2026-11-25.json > tables.md
"""
import json
import sys


def pct(x):
    return "—" if x is None else f"{100 * x:.1f}%"


def row(name, m):
    if not m or not m.get("trades"):
        return f"| {name} | 0 | | | | | | | | | | | |"
    ci = m["net_r_day95"]
    folds = sum(1 for f in m["folds"] if f is not None and f > 0)
    yrs = " / ".join(f"{m['years'][y]['net_r']:+.2f}" for y in ("2020", "2021", "2022") if y in m["years"])
    mfe = f"{m['mfe_mean']:.1f} / {m['mae_mean']:.1f}" if m.get("mfe_mean") is not None else "—"
    return (f"| {name} | {m['trades']} | {m['per_week']:.1f} | {pct(m['tp10_first']['rate'])} | {pct(m['tp15_first']['rate'])} | "
            f"{pct(m['tp20_first']['rate'])} | {pct(m['stop_first']['rate'])} | {mfe} | {m['net_r']:+.3f} ({ci[0]:+.3f} to {ci[1]:+.3f}) | "
            f"{m['usd_per_trade']:+.0f} | {m['profit_factor']:.2f} | {m['max_drawdown_usd']:,.0f} | {folds}/6 · {yrs} |")


HEAD = ("| Mechanism | Trades | /week | +$10 first | +$15 first | +$20 first | Stop first | MFE / MAE ($) | Net R / trade (95%) | "
        "$ / trade | PF | Max DD $ | Folds + · years |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|")


def main(path):
    with open(path) as f:
        d = json.load(f)
    print(f"**Verdict: {d['verdict']}** (development {d['weeks']:.0f} weeks; cost: the W8 broker decision cost)\n")
    for fam, ms in d["families"].items():
        print(f"### Family {fam}\n\n{HEAD}")
        for name, m in ms.items():
            print(row(name + (" ✔" if m.get("supported") else ""), m))
        print()
    print(f"### Baselines (not candidates)\n\n{HEAD}")
    for name, m in d["baselines"].items():
        print(row(name, m))
    print("\n### Strongest by the lower 95% bound of net R (at least 100 trades)\n\n| Mechanism | Lower bound | Net R | Trades |\n|---|---|---|---|")
    for n, lb, nr, t in d["strongest_by_lower_bound"]:
        print(f"| {n} | {lb:+.3f} | {nr:+.3f} | {t} |")


if __name__ == "__main__":
    main(sys.argv[1])
