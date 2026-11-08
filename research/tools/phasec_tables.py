"""Markdown tables for research/PHASE_C_REPORT.md, read straight from the B27 / B28 / B29 summaries (no number typed
by hand).

  python research/tools/phasec_tables.py research/results/b27/b27_summary.json research/results/b28/b28_summary.json \
      research/results/b29/b29_summary.json
"""
import json
import math
import sys


def pct(x, d=1):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:.{d}f}%"


def num(x, d=2, sign=False):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x:+.{d}f}" if sign else f"{x:.{d}f}"


def ci(c):
    return "—" if not c or c[0] is None else f"{100 * c[0]:.1f}–{100 * c[1]:.1f}"


def row(cells):
    return "| " + " | ".join(str(c) for c in cells) + " |"


def load(p):
    with open(p) as fh:
        return json.load(fh)


def board(cands, title):
    print(f"\n### {title}\n")
    print(row(["Candidate", "Board", "Dev r (95%)", "Dev n", "Dev random", "Dev exp/oz", "Exp / risk", "PF", "Trades/wk", "Max DD 0.5 lot (MC95)",
               "Months +", "2026 r (95%)", "2026 n", "2026 random", "2026 exp/oz", "Holm p", "Holds 2026"]))
    print(row(["---"] * 17))
    for c in cands:
        d, y = c["dev"], c.get("y2026") or {}
        ex = c.get("dev_extra") or {}
        risk = c.get("_risk")
        epr = d.get("exp_per_risk", (d["exp_oz"] / risk) if risk and d.get("exp_oz") is not None else None)
        print(row([c["id"], c.get("board", ""), f"{pct(d.get('r'))} ({ci(d.get('ci95'))})", d.get("n_decided"), pct(d.get("matched_random")),
                   num(d.get("exp_oz"), sign=True), num(epr, 3, sign=True), num(d.get("pf")), num(d.get("per_week"), 1),
                   f"{num(d.get('max_dd_050lot_ASSUMED'), 0)} ({num(d.get('mc_dd95_050lot_ASSUMED'), 0)})",
                   pct(ex.get("share_months_positive"), 0), f"{pct(y.get('r'))} ({ci(y.get('ci95'))})", y.get("n_decided"),
                   pct(y.get("matched_random")), num(y.get("exp_oz"), sign=True), num(c.get("y2026_holm_p"), 3),
                   "yes" if c.get("holds_2026") else "no"]))


def main(p27, p28, p29):
    s27, s28, s29 = load(p27), load(p28), load(p29)
    print("## Counts\n")
    print(row(["Study", "Configurations", "BH-significant", "INFORMATIVE", "TRADEABLE"]))
    print(row(["---"] * 5))
    for k, v in s27["counts"].items():
        print(row([f"B27 {k} (±$15)", v["tested"], v["bh"], v["informative"], v["tradeable"]]))
    v = s28["counts"]
    print(row(["B28 new Track A families (±$15)", v["tested"], v["bh"], v["informative"], v["tradeable"]]))
    for k, v in s29["counts"].items():
        print(row([f"B29 {k} (dynamic)", v["tested"], v["bh"], v["informative"], v["tradeable"]]))
    print(row(["B29 G grid (descriptive)", len(s29["G"]), "—", "—", "—"]))

    print("\n## Track B grid: the no-information arithmetic, measured (2020–22, every bar, independent trades, ENG)\n")
    print(row(["Bracket", "Dir", "TP-first (worst)", "TP-first (best case)", "Theory p0 (in session)", "Break-even", "Exp/oz", "Exp / $ risk",
               "PF", "Neither", "Min to TP", "Min to SL", "Trades/wk", "Inconclusive (15m)"]))
    print(row(["---"] * 14))
    pick = {(3, 30), (5, 30), (5, 15), (5, 10), (8, 10), (10, 10), (10, 15), (12, 10), (15, 10), (15, 15), (20, 10), (20, 15), (20, 20),
            (25, 15), (30, 20), (30, 30), (3, 3), (30, 3)}
    for e in s29["G"]:
        if tuple(e["bracket"]) not in pick:
            continue
        v = e["ENG"]
        print(row([f"+{e['bracket'][0]} / −{e['bracket'][1]}", e["dir"], f"{pct(v['r'])} ({ci(v['ci95'])})", pct(v.get("r_best")),
                   pct(v["theory_p0_in_session"]), pct(v["theory_break_even"]), num(v["exp_oz"], sign=True), num(v["exp_per_risk"], 3, sign=True),
                   num(v["pf"]), pct(v.get("neither")), num(v.get("minutes_tp"), 0), num(v.get("minutes_sl"), 0), num(v["per_week"], 1),
                   "yes" if v.get("inconclusive") else "no"]))
    best = max(s29["G"], key=lambda e: e["ENG"]["exp_per_risk"] if e["ENG"]["exp_per_risk"] is not None else -9)
    hi = max(s29["G"], key=lambda e: e["ENG"]["r"] or 0)
    print(f"\nHighest TP-first rate on the grid: +{hi['bracket'][0]} / −{hi['bracket'][1]} {hi['dir']} at {pct(hi['ENG']['r'])} "
          f"(break-even {pct(hi['ENG']['theory_break_even'])}, expectancy {num(hi['ENG']['exp_oz'], sign=True)} per oz).")
    print(f"Least-bad expectancy per $ of risk: +{best['bracket'][0]} / −{best['bracket'][1]} {best['dir']} at "
          f"{num(best['ENG']['exp_per_risk'], 3, sign=True)} (expectancy {num(best['ENG']['exp_oz'], sign=True)} per oz).")
    pos = [e for e in s29["G"] if (e["ENG"]["exp_oz"] or -1) > 0]
    print(f"Pairs x directions with positive ENG expectancy: {len(pos)} of {len(s29['G'])}"
          + (": " + ", ".join(f"+{e['bracket'][0]}/−{e['bracket'][1]} {e['dir']} {num(e['ENG']['exp_oz'], sign=True)}" for e in pos) if pos else "."))

    print("\n## 15m resolution against 5m (Sep–Nov 2026, same decisions)\n")
    print(row(["Bracket / dir", "n", "15m worst", "15m best", "5m worst", "5m best"]))
    print(row(["---"] * 6))
    for k in ("TP3/SL3 BUY", "TP5/SL5 BUY", "TP5/SL10 BUY", "TP10/SL10 BUY", "TP15/SL15 BUY", "TP3/SL30 BUY", "TP30/SL30 BUY", "TP20/SL10 SELL"):
        v = s29["resolution_5m"].get(k)
        if v:
            print(row([k, v["n"], pct(v["r15_worst"]), pct(v["r15_best"]), pct(v["r5_worst"]), pct(v["r5_best"])]))

    print("\n## V: ATR-scaled brackets (2020–22)\n")
    print(row(["Bracket", "Dir", "Median TP / SL ($)", "r (95%)", "n", "Exp/oz", "Pooled ENG exp/oz", "p (pooled > 0)", "Nearest fixed", "Exp/risk vs fixed"]))
    print(row(["---"] * 10))
    for c in s29["V"]:
        vf = c.get("vs_fixed") or {}
        d = c["dev"]
        print(row([c["id"].split(" ")[1] + " " + c["id"].split(" ")[2], c["dir"], f"{num(vf.get('median_tp'), 1)} / {num(vf.get('median_sl'), 1)}",
                   f"{pct(d['r'])} ({ci(d['ci95'])})", d["n_decided"], num(d["exp_oz"], sign=True), num(c.get("eng_pooled_exp_oz"), sign=True),
                   num(c.get("p_pooled_eng"), 3), vf.get("fixed"), f"{num(vf.get('exp_per_risk'), 3, sign=True)} vs {num(vf.get('fixed_exp_per_risk'), 3, sign=True)}"]))

    print("\n## M: time-series momentum, large brackets (2020–22; direction-neutral baseline)\n")
    print(row(["Signal / bracket", "r (95%)", "n", "Neutral random", "Same-direction random", "BUY r", "SELL r", "Exp/oz", "p"]))
    print(row(["---"] * 9))
    for c in s29["M"]:
        d = c["dev"]
        print(row([c["id"][2:], f"{pct(d['r'])} ({ci(d['ci95'])})", d["n_decided"], pct(d["matched_random"]), pct(d.get("matched_same_direction")),
                   pct(d.get("r_BUY")), pct(d.get("r_SELL")), num(d["exp_oz"], sign=True), num(d["p_vs_random"], 3)]))

    print("\n## C: a calibrated model per bracket (walk-forward 2021-01 .. 2023-01)\n")
    print(row(["Bracket", "AUC", "Brier", "Brier const", "top 1% BUY r (n)", "top 1% SELL r (n)", "top 10% BUY r", "top 10% SELL r"]))
    print(row(["---"] * 8))
    cmap = {c["id"]: c["dev"] for c in s29["C"]}
    for g, v in s29["C_models"].items():
        def gg(q, dn, g=g):
            return cmap.get(f"C LGBM {g} top{q}% {dn}", {})
        print(row([g, num(v["auc"], 4), num(v["brier"], 4), num(v["brier_constant"], 4),
                   f"{pct(gg(1, 'BUY').get('r'))} ({gg(1, 'BUY').get('n_decided')})", f"{pct(gg(1, 'SELL').get('r'))} ({gg(1, 'SELL').get('n_decided')})",
                   pct(gg(10, "BUY").get("r")), pct(gg(10, "SELL").get("r"))]))

    print("\n## E: best trigger family per bracket (2020–22, by lower bound, n >= 300)\n")
    print(row(["Bracket", "Best family / dir", "r (95%)", "n", "Random", "Exp/oz", "BH"]))
    print(row(["---"] * 7))
    by = {}
    for c in s29["E"]:
        g = tuple(c["bracket"])
        if (c["dev"]["n_decided"] or 0) >= 300 and (g not in by or c["dev"]["ci95"][0] > by[g]["dev"]["ci95"][0]):
            by[g] = c
    for g, c in sorted(by.items()):
        d = c["dev"]
        print(row([f"+{g[0]} / −{g[1]}", f"{c['family']} {c['dir']}", f"{pct(d['r'])} ({ci(d['ci95'])})", d["n_decided"], pct(d["matched_random"]),
                   num(d["exp_oz"], sign=True), "yes" if c["bh"] else "no"]))

    print("\n## B28: best mode per new family (2020–22, by lower bound, n >= 300)\n")
    print(row(["Family", "Dir", "Best mode", "r (95%)", "n", "Random", "Exp/oz", "IMM r", "Triggers"]))
    print(row(["---"] * 9))
    cfg = {c["id"]: c for c in s28["configs"]}
    for fam in s28["families"]:
        for dn in ("BUY", "SELL"):
            cs = [c for c in s28["configs"] if c["family"] == fam and c["dir"] == dn and (c["dev"]["n_decided"] or 0) >= 300]
            imm = cfg.get(f"B28 {fam} IMM {dn}", {}).get("dev", {})
            if not cs:
                print(row([fam, dn, "— (no mode with 300 trades)", "—", imm.get("n_decided"), "—", "—", pct(imm.get("r")), s28["families"][fam][dn.lower()]]))
                continue
            b = max(cs, key=lambda c: c["dev"]["ci95"][0])
            d = b["dev"]
            print(row([fam, dn, b["mode"], f"{pct(d['r'])} ({ci(d['ci95'])})", d["n_decided"], pct(d["matched_random"]), num(d["exp_oz"], sign=True),
                       pct(imm.get("r")), s28["families"][fam][dn.lower()]]))

    print("\n## Leaderboards (frozen on development; 2026 is the check; none is a validated strategy)")
    board(s27["frozen"] + s28["frozen"], "A. Fixed ±$15 (B27 and B28 frozen candidates)")
    board(s29["frozen"], "B. Dynamic TP / SL (B29 frozen candidates)")
    allc = []
    for c in s27["frozen"] + s28["frozen"]:
        c = dict(c)
        c["_risk"] = 15.0
        c["_track"] = "A"
        allc.append(c)
    for c in s29["frozen"]:
        c = dict(c)
        c["_track"] = "B"
        allc.append(c)

    def epr(c):
        d = c["dev"]
        v = d.get("exp_per_risk")
        if v is None and d.get("exp_oz") is not None:
            v = d["exp_oz"] / c.get("_risk", 15.0)
        return -9.0 if v is None or (isinstance(v, float) and math.isnan(v)) else v

    allc.sort(key=lambda c: (epr(c), (c["dev"].get("ci95") or [0])[0] or 0), reverse=True)
    board(allc[:15], "C. Best risk-adjusted across both tracks (development expectancy per $ of risk; top 15)")

    print("\n## Named bests (development, frozen; each with its 2026 check)\n")

    def show(label, c):
        if c is None:
            print(row([label, "none qualifies", "", "", "", ""]))
            return
        d, y = c["dev"], c.get("y2026") or {}
        print(row([label, c["id"], f"{pct(d.get('r'))} (n {d.get('n_decided')})", num(d.get("exp_oz"), sign=True),
                   f"{pct(y.get('r'))} (n {y.get('n_decided')})", "yes" if c.get("holds_2026") else "no"]))

    print(row(["Category", "Candidate", "Dev r", "Dev exp/oz", "2026 r", "Holds 2026"]))
    print(row(["---"] * 6))
    big = [c for c in allc if (c["dev"].get("n_decided") or 0) >= 300]
    show("Highest TP-first (n >= 300)", max(big, key=lambda c: c["dev"]["r"] or 0) if big else None)
    show("Best net profit per trade (n >= 300)", max(big, key=lambda c: c["dev"]["exp_oz"] if c["dev"]["exp_oz"] is not None else -9) if big else None)
    show("Best risk-adjusted (n >= 300)", max(big, key=epr) if big else None)
    show("Lowest drawdown (n >= 300)", min(big, key=lambda c: c["dev"].get("max_dd_050lot_ASSUMED") or 9e9) if big else None)
    buys = [c for c in big if c.get("dir") == "BUY"]
    sells = [c for c in big if c.get("dir") == "SELL"]
    show("Best BUY (risk-adjusted)", max(buys, key=epr) if buys else None)
    show("Best SELL (risk-adjusted)", max(sells, key=epr) if sells else None)
    tradeable = [c for c in allc if c.get("tradeable")]
    holds = [c for c in allc if c.get("holds_2026")]
    print(f"\nTRADEABLE on development: {len(tradeable)}. Holding on 2026: {len(holds)}. Validated strategies: 0.")


if __name__ == "__main__":
    main(*sys.argv[1:4])
