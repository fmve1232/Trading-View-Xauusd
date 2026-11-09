"""Phase C audit of the "top q" model selections after the fix (b27.SELECT_ON = "raw"). Descriptive; selects nothing.

For B27 S3 (5 models, +-$15) and B29 C (LightGBM per bracket), it recomputes the quarterly purged walk-forward and the
final (2026) models and reports, per model / bracket, direction and requested q:
  - eligible rows (walk-forward test rows of that direction; 2026 rows of that direction),
  - rows selected by the rule  raw score >= the training window's (1 - q) quantile of its own calibration rows' raw scores,
  - the realised share selected, the rows tied exactly at the threshold, and the number of distinct raw scores,
  - a cross-check: the count equals len(b27.wf_selections(...)) (the code path the studies use), and the summaries' n_raw.

Tie handling is deterministic: the threshold is np.quantile (linear interpolation) of the calibration rows' raw scores,
and every row at or above it is selected (ties at the threshold are all included, none dropped at random). The realised
test share differs from q because the threshold is fixed out of sample on the training window, as registered; choosing
exactly q of the test rows would need the test rows' own scores (look-ahead).

Raw vs calibrated: the raw score is used ONLY to rank and select; every probability, AUC, Brier and reliability figure
in the studies uses the isotonic-calibrated probability. Both AUCs are reported here (they differ only by isotonic ties).

  python research/tools/phasec_topq_audit.py --rd RD --store5 S5 --store60 S60 --out OUT.json
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from quantum.research import b27, b28, b29


def series_of(L: pd.DataFrame, rows: np.ndarray, rates: dict, weeks: float) -> dict:
    """The selection's independent trade series: decided TP-first with Wilson 95%, matched random, net expectancy per oz
    (ENG) with a t 95% interval, and the number of trades."""
    st = b27.series_stats(L, rows, rates, weeks)
    net = np.asarray((st.get("_seq") or {}).get("net", []), float)
    n = len(net)
    se = float(net.std(ddof=1) / np.sqrt(n)) if n > 1 else float("nan")
    return {"trades": n, "decided": st.get("n_decided"), "r": st.get("r"), "ci95": st.get("ci95"), "matched_random": st.get("matched_random"),
            "p_vs_random": st.get("p_vs_random"), "exp_oz": float(net.mean()) if n else None,
            "exp_ci95": [float(net.mean() - 1.96 * se), float(net.mean() + 1.96 * se)] if n > 1 else [None, None]}


def wf_counts(L: pd.DataFrame, wf: dict, model: str, rates: dict | None = None, weeks: float | None = None) -> dict:
    t_fill, d = L["fill_utc"].to_numpy(), L["d"].to_numpy()
    raw = wf["res"][model]["raw"]
    sel_code = b27.wf_selections(L, wf, model)
    out = {}
    for (dd, q), lst in wf["res"][model]["thr"].items():
        el = se = ti = 0
        for j, (s0, v) in enumerate(lst):
            s1 = lst[j + 1][0] if j + 1 < len(lst) else 10 ** 12
            m = (t_fill >= s0) & (t_fill < s1) & (d == dd) & ~np.isnan(raw)
            el += int(m.sum())
            se += int((raw[m] >= v).sum())
            ti += int((raw[m] == v).sum())
        assert se == len(sel_code[(dd, q)]), (model, dd, q, se, len(sel_code[(dd, q)]))
        out[f"{b27.DIRS[dd]} {q * 100:g}%"] = {"q": q, "dir": b27.DIRS[dd], "eligible": el, "selected": se, "share": se / el if el else None,
                                               "ties_at_threshold": ti, "quarters": len(lst),
                                               "series": series_of(L, sel_code[(dd, q)], rates, weeks) if rates is not None else None}
    return out


def final_counts(FM: dict, scores: dict, Ly: pd.DataFrame, model: str) -> dict:
    d = Ly["d"].to_numpy()
    out = {}
    for (dd, q), v in FM["thr"][model].items():
        m = d == dd
        s = scores[model][m]
        out[f"{b27.DIRS[dd]} {q * 100:g}%"] = {"q": q, "dir": b27.DIRS[dd], "eligible": int(m.sum()), "selected": int((s >= v).sum()),
                                               "share": float((s >= v).mean()) if m.any() else None, "ties_at_threshold": int((s == v).sum())}
    return out


def save(out: dict, path: str) -> None:
    with open(path + ".part", "w") as fh:
        json.dump(b27._clean(out), fh, indent=1)
    os.replace(path + ".part", path)


def by_dir(L: pd.DataFrame) -> dict:
    d = L["d"].to_numpy()
    return {b27.DIRS[dd]: int((d == dd).sum()) for dd in (1, -1)}


def block(label: str, F, L, h1, FY, Ly, h1y, models, rates: dict, weeks: float, with_2026: bool = True) -> dict:
    wf = b27.walk_forward(F, L, h1, models, log=lambda *_: None)
    if with_2026:
        FM = b27.final_models(F, L, h1, models)
        sc = b27.apply_final(FM, FY, Ly, h1y, scores=True)
        cal = b27.apply_final(FM, FY, Ly, h1y)
    y = (L["outcome"] == "TP").to_numpy(int)
    res = {}
    for m in models:
        raw, p = wf["res"][m]["raw"], wf["res"][m]["p"]
        te = ~np.isnan(raw)
        res[m] = {"walk_forward": wf_counts(L, wf, m, rates, weeks), "y2026": final_counts(FM, sc, Ly, m) if with_2026 else {},
                  "distinct_raw_test": len(np.unique(raw[te])), "distinct_calibrated_test": len(np.unique(p[te])),
                  "test_rows": int(te.sum()), "auc_calibrated": b27.auc(y, p), "auc_raw": b27.auc(y, raw),
                  "brier_calibrated": float(np.mean((p[te] - y[te]) ** 2)),
                  "y2026_distinct_raw": len(np.unique(sc[m])) if with_2026 else None,
                  "y2026_distinct_calibrated": len(np.unique(cal[m])) if with_2026 else None}
        print(label, m, json.dumps({k: res[m][k] for k in ("test_rows", "distinct_raw_test", "distinct_calibrated_test", "auc_calibrated",
                                                           "auc_raw")}), flush=True)
    return res


def _pct(x):
    return "—" if x is None else f"{100 * x:.2f}%"


def _f(x, d=2, sign=False):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    return f"{x:+.{d}f}" if sign else f"{x:.{d}f}"


def markdown(out: dict, s27: dict | None = None, s29: dict | None = None, asrun27: dict | None = None, asrun29: dict | None = None) -> str:
    """Tables: requested q, eligible, selected, realised share, ties; the studies' own counts (n_raw) beside."""
    def y26(s, cid):
        if s is None:
            return None
        for c in s.get("frozen", []):
            if c["id"] == cid:
                return (c.get("y2026") or {}).get("n_raw")
        return None

    def nraw(s, cid):
        if s is None:
            return None
        for k in ("S3", "C"):
            for c in s.get(k, []):
                if c["id"] == cid:
                    return c["dev"].get("n_raw")
        return None
    L = []
    mismatches = 0
    for label, blk, idf, s_new, s_old, el26 in (
            ("B27 S3 (+-$15)", out["B27_S3"], lambda m, k: f"S3 {m} top{k.split()[1]} {k.split()[0]}", s27, asrun27,
             lambda m: out.get("B27_2026_eligible", {})),
            ("B29 C (per bracket, LightGBM)", out["B29_C"], lambda g, k: f"C LGBM {g} top{k.split()[1]} {k.split()[0]}", s29, asrun29,
             lambda g: out.get("B29_2026_eligible", {}).get(g, {}))):
        L.append(f"\n### {label}: walk-forward 2021-01 .. 2023-01 and 2026\n")
        L.append("| Model / bracket | Dir | Requested q | WF eligible | WF selected | WF share | Ties at threshold | Study n_raw (corrected) | "
                 "As-run n_raw (calibrated threshold) | As-run share | 2026 eligible | 2026 selected | 2026 share |")
        L.append("|" + "---|" * 13)
        perf = []
        for m, v in blk.items():
            for k, w in v["walk_forward"].items():
                y = v["y2026"].get(k, {})
                cid = idf(m, k)
                nr, no = nraw(s_new, cid), nraw(s_old, cid)
                if nr is not None and nr != w["selected"]:
                    mismatches += 1
                if not y:                                              # walk-forward-only audit: 2026 from the frozen candidates
                    sel26, e26 = y26(s_new, cid), el26(m).get(w["dir"])
                    y = {"eligible": e26 if sel26 is not None else None, "selected": sel26,
                         "share": sel26 / e26 if sel26 is not None and e26 else None}
                L.append(f"| {m} | {w['dir']} | {100 * w['q']:g}% | {w['eligible']} | {w['selected']} | {_pct(w['share'])} | {w['ties_at_threshold']} | "
                         f"{'—' if nr is None else nr} | {'—' if no is None else no} | {_pct(no / w['eligible'] if no is not None and w['eligible'] else None)} | "
                         f"{y.get('eligible') if y.get('eligible') is not None else '—'} | {y.get('selected') if y.get('selected') is not None else '—'} | "
                         f"{_pct(y.get('share'))} |")
                sr = w.get("series") or {}
                if sr:
                    perf.append(f"| {m} | {w['dir']} | {100 * w['q']:g}% | {sr['trades']} | {sr['decided']} | {_pct(sr['r'])} "
                                f"({_pct((sr['ci95'] or [None])[0])}–{_pct((sr['ci95'] or [None, None])[1])}) | {_pct(sr['matched_random'])} | "
                                f"{_f(sr['p_vs_random'], 4)} | {_f(sr['exp_oz'], 2, True)} ({_f(sr['exp_ci95'][0], 2, True)} to {_f(sr['exp_ci95'][1], 2, True)}) |")
        if perf:
            L.append(f"\n#### {label}: predictive performance and net profitability of every corrected selection (walk-forward, independent series)\n")
            L.append("| Model / bracket | Dir | Requested q | Trades | Decided | TP-first (Wilson 95%) | Matched random | p vs random | Net exp / oz (t 95%) |")
            L.append("|---|---|---|---|---|---|---|---|---|")
            L.extend(perf)
        L.append("\n| Model / bracket | WF test rows | Distinct raw scores | Distinct calibrated values | AUC calibrated | AUC raw | Brier calibrated |")
        L.append("|---|---|---|---|---|---|---|")
        for m, v in blk.items():
            L.append(f"| {m} | {v['test_rows']} | {v['distinct_raw_test']} | {v['distinct_calibrated_test']} | {v['auc_calibrated']:.4f} | "
                     f"{v['auc_raw']:.4f} | {v['brier_calibrated']:.4f} |")
    L.append(f"\nCounts that differ from the corrected studies' own n_raw: {mismatches}. Rows whose study n_raw is '—' are not "
             "registered configurations (B29 C registered q of 50 / 20 / 10 / 5 / 2 / 1%; the audit also computed 0.5%); they are "
             "descriptive only. The 2026 columns are filled for frozen candidates (the only ones the registrations check on 2026).")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd")
    ap.add_argument("--store5")
    ap.add_argument("--store60")
    ap.add_argument("--out", required=True)
    ap.add_argument("--part", choices=("B27", "B29", "all"), default="all", help="compute one study only (merged into --out)")
    ap.add_argument("--no-2026", action="store_true", help="walk-forward only (the 2026 check concerns frozen candidates only)")
    ap.add_argument("--markdown", nargs=4, metavar=("B27_FIX", "B29_FIX", "B27_ASRUN", "B29_ASRUN"),
                    help="render OUT (an existing audit JSON) against the four summaries instead of computing")
    a = ap.parse_args(argv)
    if a.markdown:
        with open(a.out) as fh:
            out = json.load(fh)
        ss = []
        for p in a.markdown:
            with open(p) as fh:
                ss.append(json.load(fh))
        print(markdown(out, ss[0], ss[1], ss[2], ss[3]))
        return 0
    assert b27.SELECT_ON == "raw"
    pops = b27.load_pops(a.rd, a.store5, a.store60)
    D, Y = pops["DEV"], pops["Y2026"]
    for P_ in (D, Y):
        b27.prepare(P_, print)
    out = {"select_on": b27.SELECT_ON, "qs": list(b27.QS)}
    if os.path.exists(a.out):
        with open(a.out) as fh:
            out.update(json.load(fh))
    if a.part in ("B27", "all"):
        out["B27_2026_eligible"] = by_dir(Y["Lp"])
        out["B27_S3"] = block("B27", D["F"], D["Lp"], D["h1"], Y["F"], Y["Lp"], Y["h1"], b27.MODELS,   # B27's features (no B28 events)
                              D["rates"], D["weeks"], with_2026=not a.no_2026)
        save(out, a.out)
    if a.part == "B27":
        return 0
    for P_ in (D, Y):
        P_["F"] = pd.concat([P_["F"], b28.new_events(P_["m15"], P_["F"])], axis=1)
    TD = b29.tables(D, "ENG", fixed=b29.MODEL_BRACKETS)
    TY = b29.tables(Y, "ENG", fixed=b29.MODEL_BRACKETS)
    out.setdefault("B29_C", {})
    out["B29_2026_eligible"] = {b29.gname(g): by_dir(TY[g]) for g in b29.MODEL_BRACKETS}
    wD = b27.weeks_of(TD[b29.MODEL_BRACKETS[0]])
    for g in b29.MODEL_BRACKETS:
        if b29.gname(g) in out["B29_C"]:
            continue                                                  # resume: a bracket already saved is not recomputed
        out["B29_C"][b29.gname(g)] = block(f"B29 {b29.gname(g)}", D["F"], TD[g], D["h1"], Y["F"], TY[g], Y["h1"], ("LGBM",),
                                           b27.base_rates(TD[g]), wD, with_2026=not a.no_2026)["LGBM"]
        save(out, a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
