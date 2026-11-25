"""Every entry plan already measured on the development partition (2020-01-24 .. 2023-01-24), on the operator's one
yardstick: the target (+$10 minimum, +$15 / +$20 preferred, from the fill) reached BEFORE the plan's own stop, costs
included, $650 planned loss at the stop.

It only READS the committed result files (B2 / B3 and B31b-W3 / W4 / W5 / W7). Nothing is re-run, re-tuned or
re-selected, no partition is opened, and no trial is added to research/trials.jsonl: each row is reported as its own
study recorded it, with that study's stop, cost model and controls.

  python research/tools/entry_scoreboard.py [--results research/results] [--out-json ...] [--out-md ...]
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
import pandas as pd

W_FILES = (("W3 sweep reversal", "b31b_w3_development_2026-11-18.json"),
           ("W4 pullback / reversal / retest", "b31b_w4_development_2026-11-19.json"),
           ("W5 entry price", "b31b_w5_development_2026-11-19.json"),
           ("W7 breakout", "b31b_w7_development_2026-11-19.json"))
B_FILES = (("B2 SMC setup", "b2_development_2026-11-01.json"), ("B3 trend + confirmation + SMC", "b3_development_2026-11-01.json"))
W7_TRADES = "b31b_w7_trades_development_2026-11-19.csv.gz"
TARGETS = (10, 15, 20)


def _load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def structural_rows(res_dir: str) -> list[dict]:
    """W3 / W4 / W5 / W7: market or limit entries, each against its study's own structural stop (B31b-W3 execution)."""
    rows = []
    for study, fname in W_FILES:
        d = _load(os.path.join(res_dir, fname))
        if "variants" in d and fname.startswith("b31b_w3"):
            src = {k: {"name": k, **v["summary"], "realised_loss_usd": v["summary"].get("realised_loss_usd")}
                   for k, v in d["variants"].items()}
        else:
            src = d["methods"] if "methods" in d else d["variants"]
        for key, m in src.items():
            for T in TARGETS:
                r = m[f"tp{T}"]
                tp = r["tp_first"]
                rnd = (r.get("random") or {}).get("tp_first", {}).get("rate")
                if rnd is None and T == 10:
                    rnd = (m.get("vs_R1_tp10_rate") or {}).get("r1_rate")
                worst = (m.get("realised_loss_usd") or {}).get("max")
                rows.append({"family": "structural stop", "study": study, "plan": key, "name": m.get("name", key), "T": T,
                             "n": int(tp["n"]), "tp_first": tp["rate"], "tp_wilson95": tp["wilson95"],
                             "break_even": r["break_even"], "gap": tp["rate"] - r["break_even"],
                             "net_r": r["mean_net_r"], "net_r_boot95": r.get("mean_net_r_boot95"),
                             "usd_per_trade_at_650": r["mean_net_r"] * 650.0, "random_tp_first": rnd,
                             "median_stop": m.get("median_D"), "worst_loss_usd": worst})
    return rows


def fixed_stop_rows(res_dir: str) -> list[dict]:
    """B2 / B3: setups against a fixed -$10 stop; only targets of at least the operator's $10 minimum."""
    rows = []
    for study, fname in B_FILES:
        d = _load(os.path.join(res_dir, fname))
        for t in d["trials"]:
            T = int(d["targets"][t["target"]][0])
            if T < 10 or t.get("win_rate") is None:
                continue
            rows.append({"family": "fixed -$10 stop", "study": study, "plan": t["id"], "name": t["id"], "T": T, "n": int(t["n"]),
                         "tp_first": t["win_rate"], "tp_wilson95": t["wilson"], "break_even": t["break_even"],
                         "gap": t["win_rate"] - t["break_even"], "net_r": t["net_r"], "net_r_boot95": None,
                         "usd_per_trade_at_650": t["net_r"] * 650.0,
                         "random_tp_first": t.get("random_same_mix", t.get("random_same_treatment")),
                         "median_stop": 10.0, "worst_loss_usd": None})
    return rows


def tally(rows: list[dict]) -> dict:
    out = {}
    for T in TARGETS:
        x = [r for r in rows if r["T"] == T]
        out[str(T)] = {"plans": len(x), "tp_first_above_break_even": sum(r["gap"] > 0 for r in x),
                       "net_r_positive": sum(r["net_r"] > 0 for r in x),
                       "net_r_lower95_positive": sum(bool(r["net_r_boot95"]) and r["net_r_boot95"][0] > 0 for r in x),
                       "beats_random": sum(r["random_tp_first"] is not None and r["tp_first"] > r["random_tp_first"] for r in x)}
    return out


def _mean_r(tp: np.ndarray, D: np.ndarray, T: float, c: float) -> float:
    """Mean net R at round-trip cost c: a target first wins (T - c) / (D + c), a stop first loses 1 R."""
    return float(np.where(tp, (T - c) / (D + c), -1.0).mean())


def break_even_cost(res_dir: str) -> dict:
    """Sensitivity, never decisive: the round-trip cost ($/oz at the $4,000 scale of the W3-W7 execution) at which the
    W7 market entries E0 / E1 on M15 (ENTRY READY, filled, decided) would have a mean net R of exactly 0. Outcomes are
    held as recorded; only the cost in the R arithmetic changes (the loss at the stop stays 1 R)."""
    p = os.path.join(res_dir, W7_TRADES)
    if not os.path.exists(p):
        return {}
    df = pd.read_csv(p)
    out = {}
    for m in ("E0", "E1"):
        y = df[(df.m == m) & (df.tf == "M15") & (df.status == "FILLED") & df.ready.astype(bool)]
        for T in TARGETS:
            dec = y[y[f"tp{T}"].isin(["TP", "SL"])]
            tp, D = (dec[f"tp{T}"] == "TP").to_numpy(), dec["D"].to_numpy(float)
            grid = np.round(np.arange(0.0, 1.5001, 0.01), 2)
            ok = [c for c in grid if _mean_r(tp, D, T, c) >= 0]
            out[f"{m}:M15:+{T}"] = {"decided": len(dec), "tp_first": float(tp.mean()),
                                    "mean_r_at_model_cost": float(dec[f"tp{T}_r"].mean()), "model_cost_mean": float(dec["cost"].mean()),
                                    "mean_r_at_zero_cost": _mean_r(tp, D, T, 0.0), "break_even_cost": max(ok) if ok else None}
    return out


def _label(r):
    return r["plan"] if r["name"] == r["plan"] else f"{r['plan']}: {r['name']}"


def _pct(x):
    return "—" if x is None else f"{100 * x:.1f}%"


def markdown(rows: list[dict], fixed: list[dict], bec: dict, tall: dict) -> str:
    L = []
    for fam, rs in (("Structural stops (W3 / W4 / W5 / W7)", rows), ("Fixed −$10 stop (B2 / B3)", fixed)):
        t = tall[fam.split(" (")[0]]
        L.append(f"### {fam}\n")
        L.append("| Target | Plans | TP first above break-even | Net R > 0 | Net R 95% lower bound > 0 | TP first above random |")
        L.append("|---|---|---|---|---|---|")
        for T in TARGETS:
            v = t[str(T)]
            L.append(f"| +${T} | {v['plans']} | {v['tp_first_above_break_even']} | {v['net_r_positive']} | "
                     f"{v['net_r_lower95_positive'] if fam.startswith('Structural') else 'not computed'} | {v['beats_random']} |")
        L.append("")
    L.append("### Every structural-stop plan at +$10, ranked by TP-first rate minus break-even\n")
    L.append("| # | Study | Plan | n | TP first | Break-even | Gap | Net R (95%) | $ / trade at $650 | Random | Worst loss |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(sorted([r for r in rows if r["T"] == 10], key=lambda r: -r["gap"]), 1):
        ci = r["net_r_boot95"]
        L.append(f"| {i} | {r['study']} | {_label(r)} | {r['n']} | {_pct(r['tp_first'])} | {_pct(r['break_even'])} | "
                 f"{100 * r['gap']:+.1f} | {r['net_r']:+.3f}" + (f" ({ci[0]:+.3f} to {ci[1]:+.3f})" if ci else "") +
                 f" | {r['usd_per_trade_at_650']:+.0f} | {_pct(r['random_tp_first'])} | "
                 + ("—" if r["worst_loss_usd"] is None else f"${r['worst_loss_usd']:,.0f}") + " |")
    L.append("")
    for T in (15, 20):
        L.append(f"### Top 10 structural-stop plans at +${T}\n")
        L.append("| # | Study | Plan | n | TP first | Break-even | Gap | Net R (95%) | $ / trade at $650 |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for i, r in enumerate(sorted([r for r in rows if r["T"] == T], key=lambda r: -r["gap"])[:10], 1):
            ci = r["net_r_boot95"]
            L.append(f"| {i} | {r['study']} | {_label(r)} | {r['n']} | {_pct(r['tp_first'])} | {_pct(r['break_even'])} | "
                     f"{100 * r['gap']:+.1f} | {r['net_r']:+.3f}" + (f" ({ci[0]:+.3f} to {ci[1]:+.3f})" if ci else "") +
                     f" | {r['usd_per_trade_at_650']:+.0f} |")
        L.append("")
    L.append("### Top 10 fixed −$10 stop plans per target (B2 / B3; no confidence interval was recorded)\n")
    L.append("| Target | Plan | n | TP first | Break-even | Gap | Net R | Random |")
    L.append("|---|---|---|---|---|---|---|---|")
    for T in TARGETS:
        for r in sorted([r for r in fixed if r["T"] == T], key=lambda r: -r["gap"])[:10]:
            L.append(f"| +${T} | {r['study']}: {r['plan']} | {r['n']} | {_pct(r['tp_first'])} | {_pct(r['break_even'])} | "
                     f"{100 * r['gap']:+.1f} | {r['net_r']:+.3f} | {_pct(r['random_tp_first'])} |")
    L.append("")
    if bec:
        L.append("### Sensitivity: the round-trip cost at which the W7 M15 market entries would break even\n")
        L.append("| Entry and target | Decided | TP first | Net R at the modelled cost | Modelled cost | Net R at zero cost | Break-even cost |")
        L.append("|---|---|---|---|---|---|---|")
        for k, v in bec.items():
            L.append(f"| {k} | {v['decided']} | {_pct(v['tp_first'])} | {v['mean_r_at_model_cost']:+.3f} | ${v['model_cost_mean']:.2f} | "
                     f"{v['mean_r_at_zero_cost']:+.3f} | " + ("none (negative at zero cost)" if v["break_even_cost"] is None
                                                            else f"${v['break_even_cost']:.2f} / oz") + " |")
        L.append("")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.path.join(os.path.dirname(__file__), "..", "results"))
    ap.add_argument("--out-json", default=None)
    ap.add_argument("--out-md", default=None)
    a = ap.parse_args()
    rows, fixed = structural_rows(a.results), fixed_stop_rows(a.results)
    tall = {"Structural stops": tally(rows), "Fixed −$10 stop": tally(fixed)}
    bec = break_even_cost(a.results)
    if a.out_json:
        with open(a.out_json, "w") as f:
            json.dump({"tally": tall, "structural": rows, "fixed_10_stop": fixed, "break_even_cost": bec}, f, indent=1)
    md = markdown(rows, fixed, bec, tall)
    if a.out_md:
        with open(a.out_md, "w") as f:
            f.write(md + "\n")
    print(json.dumps(tall, indent=1))


if __name__ == "__main__":
    main()
