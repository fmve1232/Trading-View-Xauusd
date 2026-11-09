"""Fills the ⟪slots⟫ of PHASE_C_REPORT.md and the B27 erratum from the committed results (no figure typed by hand), then
fails if any slot is left anywhere in research/*.md.

  python research/tools/phasec_fill_reports.py
"""
import contextlib
import glob
import io
import json
import re
import sys

sys.path.insert(0, "research/tools")
import phasec_rerun_compare as RC

R = "research/results"


def load(p):
    with open(p) as fh:
        return json.load(fh)


def pct(x, d=1):
    return "—" if x is None else f"{100 * x:.{d}f}%"


def share_range(blk: dict, qs: tuple, key: str = "walk_forward") -> str:
    out = []
    for q in qs:
        sh = [w["share"] for v in blk.values() for k, w in v[key].items() if abs(w["q"] - q) < 1e-12 and w.get("share") is not None]
        if sh:
            out.append(f"q = {100 * q:g}%: {pct(min(sh), 2)}–{pct(max(sh), 2)}")
    return "; ".join(out)


def asrun_range(blk: dict, s_old: dict, study: str, idf, q: float) -> str:
    old = {c["id"]: c["dev"].get("n_raw") for c in s_old[study]}
    sh = []
    for m, v in blk.items():
        for k, w in v["walk_forward"].items():
            if abs(w["q"] - q) < 1e-12 and old.get(idf(m, k)) is not None and w["eligible"]:
                sh.append(old[idf(m, k)] / w["eligible"])
    return f"{pct(min(sh), 1)}–{pct(max(sh), 1)}" if sh else "—"


def net_line(blk: dict, registered_q: tuple | None = None) -> str:
    rows = [w["series"] for v in blk.values() for w in v["walk_forward"].values() if w.get("series") and w["series"].get("exp_oz") is not None
            and (registered_q is None or any(abs(w["q"] - q) < 1e-12 for q in registered_q))]
    lo_pos = [r for r in rows if r["exp_ci95"][0] is not None and r["exp_ci95"][0] > 0]
    pos = [r for r in rows if r["exp_oz"] > 0]
    best = max(rows, key=lambda r: r["exp_ci95"][0] if r["exp_ci95"][0] is not None else -9)
    return (f"{len(pos)} of {len(rows)} selections have positive mean net expectancy; {len(lo_pos)} have a 95% interval above zero. "
            f"The highest lower bound is {best['exp_ci95'][0]:+.2f} $ / oz ({best['trades']} trades, mean {best['exp_oz']:+.2f})")


C_QS = (0.50, 0.20, 0.10, 0.05, 0.02, 0.01)       # B29 C's registered q (b29.QS_C); the audit also computed 0.5%


def unregistered(blk: dict) -> str:
    """The audit's q = 0.5% rows for B29 C are outside the registered set: reported, never counted as findings."""
    rows = [(g, k, w["series"]) for g, v in blk.items() for k, w in v["walk_forward"].items() if abs(w["q"] - 0.005) < 1e-12]
    hit = [(g, k, r) for g, k, r in rows if r["exp_ci95"][0] is not None and r["exp_ci95"][0] > 0]
    if not hit:
        return f"The audit's {len(rows)} unregistered q = 0.5% rows: none has an expectancy interval above zero."
    g, k, r = hit[0]
    return (f"Outside the registered set (C registered q of 50 / 20 / 10 / 5 / 2 / 1%), the audit's q = 0.5% rows include {len(hit)} with an "
            f"expectancy interval above zero: {g} {k} ({r['decided']} decided trades, {pct(r['r'])} against {pct(r['matched_random'])}, "
            f"{r['exp_oz']:+.2f} $ / oz, 95% {r['exp_ci95'][0]:+.2f} to {r['exp_ci95'][1]:+.2f}, p {r['p_vs_random']:.3f} before any correction). "
            "It is not a finding: it was not registered, it has fewer than 300 trades, its p does not survive any correction over the audit's rows, "
            "and its registered 1% and 2% neighbours were frozen and lost money on 2026")


def topq_line(blk: dict, s_old: dict, study: str, idf, qs=(0.01, 0.05, 0.10)) -> str:
    ties = sum(w["ties_at_threshold"] for v in blk.values() for w in v["walk_forward"].values())
    dup = {m: v["test_rows"] - v["distinct_raw_test"] for m, v in blk.items() if v["distinct_raw_test"] < v["test_rows"]}
    dtxt = ("every raw score distinct on the test rows" if not dup else
            "raw scores distinct on the test rows except " + ", ".join(f"{m} ({n} repeated values of {blk[m]['test_rows']:,})" for m, n in dup.items()))
    return (f"realised walk-forward shares {share_range(blk, qs)} (as run, q = 1% took {asrun_range(blk, s_old, study, idf, 0.01)}); "
            f"rows tied exactly at a threshold: {ties}; {dtxt} (A2)")


def perf_line(s: dict, study: str) -> str:
    cs = s[study]
    best = min(cs, key=lambda c: c["dev"]["p_vs_random"] if c["dev"].get("p_vs_random") is not None else 1)
    d = best["dev"]
    m = len(cs)
    return (f"{sum(c['bh'] for c in cs)} of {m} BH-significant; the smallest p is {d['p_vs_random']:.4f} ({best['id']}: {pct(d['r'])} on "
            f"{d['n_decided']} decided against {pct(d['matched_random'])}; BH threshold about {0.05 / m:.4f})")


def main() -> int:
    s27o, s27 = load(f"{R}/b27/b27_summary.json"), load(f"{R}/b27_fix/b27_summary.json")
    s28 = load(f"{R}/b28/b28_summary.json")
    s29o = load(f"{R}/b29/b29_summary.json")
    aud = load(f"{R}/phasec/topq_audit.json")
    cand = load(f"{R}/phasec/candidates.json")
    id27 = lambda m, k: f"S3 {m} top{k.split()[1]} {k.split()[0]}"
    id29 = lambda g, k: f"C LGBM {g} top{k.split()[1]} {k.split()[0]}"
    keys = [k for k in cand[0]["criteria"] if k != "QUALIFIES"]
    crit = "| Criterion | Candidates passing |\n|---|---|\n" + "\n".join(
        f"| {k.replace('_', ' ')} | {sum(c['criteria'][k] for c in cand)} of {len(cand)} |" for k in keys) + \
        f"\n| **All six (QUALIFIES)** | **{sum(c['criteria']['QUALIFIES'] for c in cand)} of {len(cand)}** |"
    c27 = s27["counts"]
    fz27 = s27["frozen"]
    ta = ("| Study | Configurations | BH | INFORMATIVE | TRADEABLE |\n|---|---|---|---|---|\n"
          + "\n".join(f"| B27 {k} (corrected re-run) | {v['tested']} | {v['bh']} | {v['informative']} | {v['tradeable']} |" for k, v in c27.items())
          + f"\n| B28 (8 new families) | {s28['counts']['tested']} | {s28['counts']['bh']} | {s28['counts']['informative']} | {s28['counts']['tradeable']} |"
          + f"\n\nFrozen and checked on 2026: B27 {len(fz27)} (hold: {sum(c['holds_2026'] for c in fz27)}; smallest Holm p "
          f"{min(c['y2026_holm_p'] for c in fz27):.3f}), B28 {len(s28['frozen'])} (hold: {sum(c['holds_2026'] for c in s28['frozen'])}).")
    old_ids, new_ids = [c["id"] for c in s27o["frozen"]], [c["id"] for c in fz27]
    rc = [c for c in cand if c.get("risk")]
    risk = [c["risk"]["iid"]["10000"] for c in rc]
    low = [c for c in rc if c["risk"]["iid"]["10000"] <= 0.05]
    low_txt = "; ".join(f"{c['id']}: {c['dev']['decided']} decided development trades, 2026 expectancy "
                        f"{c['y2026'].get('exp_oz', float('nan')):+.2f} per oz, BH q {c['dev_bh_q']:.3f}, Holm p {c['y2026_holm_p']:.3f}" for c in low)
    risk_line = (f"**Across the {len(risk)} candidates with at least 30 development trades,** P(drawdown ≥ $10,000 within 250 trades at 0.50 lot) "
                 f"runs from {pct(min(risk), 1)} to {pct(max(risk), 0)} (median {pct(sorted(risk)[len(risk) // 2], 0)}). "
                 f"{len(low)} {'is' if len(low) == 1 else 'are'} at or below 5%" + (f" ({low_txt})" if low else "")
                 + ". A low drawdown figure alone is not evidence of an edge: it fails C1–C3 (A4).")
    with open("research/PHASE_C_APPENDIX.md") as fh:
        app = fh.read()
    m_ = re.search(r"## Named bests.*?(?=\n## |\Z)", app, re.DOTALL)
    tab = m_.group(0).replace("## Named bests", "**Named bests**", 1).strip() if m_ else ""
    with contextlib.redirect_stdout(io.StringIO()):
        bad = sum(RC.check(s27o[k], s27[k], k) for k in ("S1", "S2", "S5"))
    s4o, s4n = s27o["S4"], s27["S4"]
    s4bad = sum(not RC._eq(s4o[k][f], s4n[k].get(f)) for k in ("univariate_auc", "permutation_auc_drop") for f in s4o[k])
    s4bad += sum(not RC._eq(s4o["ablation"][f]["change"], s4n["ablation"][f]["change"]) for f in s4o["ablation"])
    aucs = all(RC._eq(s27o["S3_models"][m]["auc"], s27["S3_models"][m]["auc"]) and RC._eq(s27o["S3_models"][m]["brier"], s27["S3_models"][m]["brier"])
               for m in s27o["S3_models"])
    repro27 = (f"S1 {len(s27['S1'])}, S2 {len(s27['S2'])} and S5 {len(s27['S5'])} configurations: {'identical' if bad == 0 else f'{bad} DIFFER'}; "
               f"S3's five AUCs and Brier scores: {'identical' if aucs else 'DIFFERENT'}; the S4 ranking (univariate AUC, permutation, "
               f"ablation): {'identical' if s4bad == 0 else f'{s4bad} values DIFFER'} (A1)")
    fill = {
        "N_CAND": str(len(cand)), "CRIT_TABLE": crit, "TRACK_A_TABLE": ta,
        "B27_S3_LINE": perf_line(s27, "S3") + ". " + net_line(aud["B27_S3"]) + ".",
        "B27_REPRO": repro27,
        "B27_TOPQ": topq_line(aud["B27_S3"], s27o, "S3", id27), "B29_TOPQ": topq_line(aud["B29_C"], s29o, "C", id29),
        "B27_PERF": perf_line(s27, "S3"), "B27_NET": net_line(aud["B27_S3"]),
        "B29_NET": net_line(aud["B29_C"], C_QS) + ". " + unregistered(aud["B29_C"]),
        "NAMED_BESTS": tab, "RISK_LINE": risk_line, "B27_FROZEN_N": str(len(fz27)),
        "B27_ASRUN_SHARES": f"as run, a nominal top 1% took {asrun_range(aud['B27_S3'], s27o, 'S3', id27, 0.01)} of the walk-forward test rows",
        "B27_FIX_SHARES": share_range(aud["B27_S3"], (0.005, 0.01, 0.05, 0.10)),
        "B27_FIX_S3": perf_line(s27, "S3") + ". " + net_line(aud["B27_S3"]) + ".",
        "B27_FIX_FROZEN": (f"{len(fz27)} frozen in the corrected re-run ({len(old_ids)} as run); entering: "
                           f"{', '.join(x for x in new_ids if x not in old_ids) or 'none'}; leaving: {', '.join(x for x in old_ids if x not in new_ids) or 'none'}. "
                           f"None holds on 2026 (smallest Holm p {min(c['y2026_holm_p'] for c in fz27):.3f})."),
    }
    for path in ("research/PHASE_C_REPORT.md", "research/B27_RESULTS.md"):
        with open(path) as fh:
            txt = fh.read()
        for k, v in fill.items():
            txt = txt.replace(f"⟪{k}⟫", v)
        with open(path, "w") as fh:
            fh.write(txt)
    left = {}
    for p in glob.glob("research/*.md"):
        with open(p) as fh:
            left[p] = re.findall(r"⟪[A-Z0-9_]+⟫", fh.read())
    left = {p: v for p, v in left.items() if v}
    if left:
        print("UNFILLED SLOTS:", left)
        return 1
    print("all slots filled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
