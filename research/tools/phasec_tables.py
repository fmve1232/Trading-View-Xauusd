"""Markdown tables for research/PHASE_C_REPORT.md, read straight from the B27 / B28 / B29 summaries and the Phase C
diagnostics in research/results/phasec (no number typed by hand).

  python research/tools/phasec_tables.py research/results/b27/b27_summary.json research/results/b28/b28_summary.json \
      research/results/b29/b29_summary.json research/results/phasec
"""
import collections
import gzip
import json
import math
import os
import sys

import pandas as pd


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


def epr_of(c):
    """Development ENG expectancy per $ of risk (Track A: exp / $15)."""
    d = c["dev"]
    v = d.get("exp_per_risk")
    if v is None and d.get("exp_oz") is not None and c.get("_risk"):
        v = d["exp_oz"] / c["_risk"]
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else v


def board(cands, title):
    print(f"\n### {title}\n")
    print(row(["Candidate", "Board", "Dev r (95%)", "Dev n", "Dev random", "Dev exp/oz", "Exp / risk", "PF", "Trades/wk", "Max DD 0.5 lot (MC95)",
               "Months +", "2026 r (95%)", "2026 n", "2026 random", "2026 exp/oz", "Holm p", "Holds 2026"]))
    print(row(["---"] * 17))
    for c in cands:
        d, y = c["dev"], c.get("y2026") or {}
        ex = c.get("dev_extra") or {}
        print(row([c["id"], c.get("board", ""), f"{pct(d.get('r'))} ({ci(d.get('ci95'))})", d.get("n_decided"), pct(d.get("matched_random")),
                   num(d.get("exp_oz"), sign=True), num(epr_of(c), 3, sign=True), num(d.get("pf")), num(d.get("per_week"), 1),
                   f"{num(d.get('max_dd_050lot_ASSUMED'), 0)} ({num(d.get('mc_dd95_050lot_ASSUMED'), 0)})",
                   pct(ex.get("share_months_positive"), 0), f"{pct(y.get('r'))} ({ci(y.get('ci95'))})", y.get("n_decided"),
                   pct(y.get("matched_random")), num(y.get("exp_oz"), sign=True), num(c.get("y2026_holm_p"), 3),
                   "yes" if c.get("holds_2026") else "no"]))


def main(p27, p28, p29, pc=None):
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
    A = []
    for c in s27["frozen"] + s28["frozen"]:
        c = dict(c)
        c["_risk"] = 15.0
        c["_track"] = "A"
        A.append(c)
    board(A, "A. Fixed ±$15 (B27 and B28 frozen candidates)")
    board(s29["frozen"], "B. Dynamic TP / SL (B29 frozen candidates)")
    allc = list(A)
    for c in s29["frozen"]:
        c = dict(c)
        c["_track"] = "B"
        allc.append(c)

    def epr(c):
        v = epr_of(c)
        return -9.0 if v is None else v

    allc.sort(key=lambda c: (epr(c), (c["dev"].get("ci95") or [0])[0] or 0), reverse=True)
    board(allc[:15], "C. Best risk-adjusted across both tracks (development expectancy per $ of risk; top 15)")
    board([c for c in allc if c.get("dir") == "BUY"][:10], "BUY leaderboard (both tracks, development expectancy per $ of risk; top 10)")
    board([c for c in allc if c.get("dir") == "SELL"][:10], "SELL leaderboard (both tracks, development expectancy per $ of risk; top 10)")

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
    pos = [c for c in big if (c["dev"].get("exp_oz") or -9) > 0]
    show("Highest TP-first (n >= 300)", max(big, key=lambda c: c["dev"]["r"] or 0) if big else None)
    show("Highest TP-first with positive dev expectancy (n >= 300)", max(pos, key=lambda c: c["dev"]["r"] or 0) if pos else None)
    show("Best net profit per trade (n >= 300)", max(big, key=lambda c: c["dev"]["exp_oz"] if c["dev"]["exp_oz"] is not None else -9) if big else None)
    show("Best risk-adjusted (n >= 300)", max(big, key=epr) if big else None)
    show("Lowest drawdown (n >= 300, dev expectancy > 0; lowest Monte Carlo 95th-percentile drawdown per 100 trades)",
         min(pos, key=lambda c: (c["dev"].get("mc_dd95_050lot_ASSUMED") or 9e9) / c["dev"]["n_decided"]) if pos else None)
    buys = [c for c in big if c.get("dir") == "BUY"]
    sells = [c for c in big if c.get("dir") == "SELL"]
    show("Best BUY (risk-adjusted)", max(buys, key=epr) if buys else None)
    show("Best SELL (risk-adjusted)", max(sells, key=epr) if sells else None)
    no5m = ("none qualifies: no 5m history for development (the store's Sep–Nov 2026 5m bars "
            "only check the 15m resolution; see the resolution table)")
    print(row(["Best 5m-execution setup", no5m, "", "", "", ""]))
    tradeable = [c for c in allc if c.get("tradeable")]
    holds = [c for c in allc if c.get("holds_2026")]
    print(f"\nTRADEABLE on development: {len(tradeable)}. Holding on 2026: {len(holds)}. Validated strategies: 0.")
    if pc:
        diagnostics(s28, s29, p29, pc)


def modes_b28(s28):
    agg = collections.defaultdict(lambda: collections.Counter())
    for c in s28["configs"]:
        d = c["dev"]
        n = d.get("n_decided") or 0
        if not n:
            continue
        a = agg[c["mode"]]
        a["n"] += n
        a["k"] += d["r"] * n
        a["rnd"] += d["matched_random"] * n
        a["nt"] += d["n_trades"]
        a["net"] += d["exp_oz"] * d["n_trades"]
        a["trig"] += d["n_triggers"]
        a["filled"] += d["n_filled"]
        a["netT"] += d["exp_per_trigger_oz"] * d["n_triggers"]
    print("\n## B28: pooled by entry mode (8 families, both directions, 2020–22; descriptive)\n")
    print(row(["Mode", "Trades", "TP-first", "Matched random", "Lift (pts)", "Exp/oz per trade", "Fill rate", "Exp/oz per trigger"]))
    print(row(["---"] * 8))
    order = ["IMM"] + [f"{m}_{x}" for m in ("CONF", "RETEST", "STOP") for x in (3, 5, 8, 10, 15, 20)] + ["LIMIT"]
    for m in order:
        a = agg.get(m)
        if a:
            r, rr = a["k"] / a["n"], a["rnd"] / a["n"]
            print(row([m, a["n"], pct(r), pct(rr), f"{100 * (r - rr):+.1f}", num(a["net"] / a["nt"], sign=True), pct(a["filled"] / a["trig"], 0),
                       num(a["netT"] / a["trig"], sign=True)]))


def _null_line(lst):
    big = [c for c in lst if (c["dev"].get("n_decided") or 0) >= 300]
    ps = [c["dev"]["p_vs_random"] for c in lst if c["dev"].get("p_vs_random") is not None]
    if not big:
        return [len(lst), 0, "—", "—", num(min(ps), 4) if ps else "—", "—"]
    lift = max(c["dev"]["r"] - c["dev"]["matched_random"] for c in big)
    return [len(lst), len(big), pct(max(c["dev"]["r"] for c in big)), f"{100 * lift:+.1f}", num(min(ps), 4),
            sum((c["dev"]["exp_oz"] or -9) > 0 for c in big)]


def diagnostics(s28, s29, p29, pc):
    modes_b28(s28)
    fb = os.path.join(pc, "phasec_fillbar.json")
    if os.path.exists(fb):
        P = load(fb)["pooled"]
        print("\n## Order-entry resolution: the fill bar, worst vs best case (21 families, 2020–22)\n")
        print(row(["Mode", "Trades (worst)", "Stopped on the fill bar", "TP-first worst", "TP-first best", "Gap (pts)", "Random", "Inconclusive (> 2 pts)"]))
        print(row(["---"] * 8))

        def key(k):
            kind, _, x = k.partition("_")
            return (kind.split()[0], 0 if not x else (int(x) if x.isdigit() else 0), k)
        for k in sorted(P, key=key):
            v = P[k]
            print(row([k, v["n_worst"], pct(v["fill_bar_stop_share"]), pct(v["r_worst"]), pct(v["r_best"]),
                       f"{100 * (v['r_best'] - v['r_worst']):+.1f}", pct(v["random_worst_series"]), "yes" if v["inconclusive"] else "no"]))
    cd = os.path.join(pc, "phasec_c_diag.json")
    if os.path.exists(cd):
        C = load(cd)
        print("\n## C diagnostic: where the model's AUC comes from (walk-forward 2021-01 .. 2023-01)\n")
        print(row(["Bracket", "Neither share", "AUC (all)", "AUC (decided only)", "AUC (no Friday entries)", "Calendar-only AUC",
                   "Calendar-only AUC (decided)", "Distinct p", "Top 1% SELL realised share", "Top 10% SELL realised share",
                   "Top 1% SELL share in 2026"]))
        print(row(["---"] * 11))
        for g, v in C.items():
            sh, s6 = v["selected_share_wf"], v["selected_share_2026"]
            print(row([g, pct(v["neither_share_test"]), num(v["auc_all"], 4), num(v["auc_decided_only"], 4), num(v["auc_without_friday"], 4),
                       num(v["auc_calendar_only"], 4), num(v["auc_calendar_only_decided"], 4), v["distinct_p_test"],
                       pct(sh.get("SELL top1%")), pct(sh.get("SELL top10%")), pct(s6.get("SELL top1%"))]))
        print("\nNeither share and AUCs on the walk-forward test rows; 'Calendar-only' = the training window's TP rate per UTC weekday x hour.")
        print("\n### P(TP first), P(SL first) and P(neither) by entry weekday (walk-forward test rows, worst case)\n")
        print(row(["Bracket", "Entry day", "n", "P(TP first)", "P(SL first)", "P(neither: closure / 2-day limit)", "P(TP | decided)"]))
        print(row(["---"] * 7))
        for g, v in C.items():
            for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sun"):
                w = v["by_weekday_test"].get(day)
                if w:
                    sl = 1 - w["tp"] - w["neither"]
                    print(row([g, day, w["n"], pct(w["tp"]), pct(sl), pct(w["neither"]), pct(w["tp"] / (w["tp"] + sl))]))
        fri = {g: v["by_weekday_test"].get("Fri", {}) for g, v in C.items()}
        print("\n| Bracket | Friday entries ending without TP or SL | Monday–Thursday (mean) |\n| --- | --- | --- |")
        for g, v in C.items():
            mt = [v["by_weekday_test"][d]["neither"] for d in ("Mon", "Tue", "Wed", "Thu") if d in v["by_weekday_test"]]
            print(row([g, pct(fri[g].get("neither")), pct(sum(mt) / len(mt) if mt else None)]))
    ge = next((x for x in (os.path.join(os.path.dirname(p29), "b29_grid_extra.csv.gz"),
                           os.path.join(os.path.dirname(os.path.dirname(p29)), "b29", "b29_grid_extra.csv.gz")) if os.path.exists(x)), None)
    if ge:
        x = pd.read_csv(ge)
        print("\n## Grid stability per pair (2020–22, ENG; `b29_grid_extra.csv.gz` has every pair)\n")
        print(f"- Months per pair: {int(x['months'].median())}. Share of profitable months: median {pct(x['share_months_positive'].median())}, "
              f"best {pct(x['share_months_positive'].max())} ({x.loc[x['share_months_positive'].idxmax(), 'bracket']} "
              f"{x.loc[x['share_months_positive'].idxmax(), 'dir']}); pairs with at least half the months profitable: "
              f"{int((x['share_months_positive'] >= 0.5).sum())} of {len(x)}.")
        print(f"- Spread of the TP-first rate across volatility terciles: median {100 * x['vol_tercile_r_spread'].median():.1f} points, "
              f"largest {100 * x['vol_tercile_r_spread'].max():.1f}.")
        tot, posn = int(x["regimes_tested"].sum()), int(x["regimes_with_positive_exp"].sum())
        print(f"- Regime cells (volatility tercile, trend, session; >= 100 trades) with positive expectancy: {posn} of {tot} "
              f"({pct(posn / tot if tot else None)}).")
        print("\n| Pair | Dir | Months + | Mean month (0.5 lot) | Worst month (0.5 lot) | LOW vol r | MID vol r | HIGH vol r | Regime cells + |")
        print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for _, r in x.sort_values("share_months_positive", ascending=False).head(10).iterrows():
            print(row([r["bracket"], r["dir"], pct(r["share_months_positive"], 0), num(r["monthly_mean_050lot_ASSUMED"], 0),
                       num(r["monthly_worst_050lot_ASSUMED"], 0), pct(r.get("vol_tercile=LOW r")), pct(r.get("vol_tercile=MID r")),
                       pct(r.get("vol_tercile=HIGH r")), f"{int(r['regimes_with_positive_exp'])} of {int(r['regimes_tested'])}"]))
    n28, n29 = os.path.join(pc, "null_b28_summary.json.gz"), os.path.join(pc, "null_b29_summary.json.gz")
    if os.path.exists(n28) and os.path.exists(n29):
        with gzip.open(n28, "rt") as fh:
            z28 = json.load(fh)
        with gzip.open(n29, "rt") as fh:
            z29 = json.load(fh)
        print("\n## Real data against the same framework on a path-consistent random walk (development)\n")
        print(row(["Study", "Data", "Configurations", "With >= 300 trades", "Best TP-first (>= 300)", "Largest lift (pts)", "Smallest p",
                   "Positive expectancy (>= 300)"]))
        print(row(["---"] * 8))
        for nm, a, b in (("B28", s28["configs"], z28["configs"]), *((f"B29 {k}", s29[k], z29[k]) for k in "VMCE")):
            print(row([nm, "real 2020–22", *_null_line(a)]))
            print(row([nm, "random walk", *_null_line(b)]))
        print("\n| Bracket | C model AUC, real | C model AUC, random walk |\n| --- | --- | --- |")
        for g in s29["C_models"]:
            print(row([g, num(s29["C_models"][g]["auc"], 4), num(z29["C_models"].get(g, {}).get("auc"), 4)]))
        print("\nThe synthetic development history is shorter (26,964 15m bars against 70,173), so fewer configurations reach 300 trades.")


if __name__ == "__main__":
    main(*sys.argv[1:5])
