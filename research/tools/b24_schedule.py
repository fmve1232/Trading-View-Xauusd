"""B24 schedule: expected time to 30 / 50 / 75 / 100 decided results from the MEASURED historical signal frequency.

B24's stream is the engine signals (15m / 30m / 1h / 4h, one per idea) confirmed under amendment A1 (first close $15-$20
beyond the trigger). Each confirmation becomes one decided primary result (+$15 before -$13 from the executable entry;
TIMEOUT counts as decided), so the decided-result rate is the capped confirmation rate. That rate is measured, never
assumed: research/results/cf_validation.json (B19's registered functions, the capped rule) per scored period. Nothing here
reads an outcome: only how often a confirmation happened. No frequency is raised, no category is pooled with another.

Frequency bases, kept apart (the operator asked for the 2026 and the historical assumptions separately):
  2026                 the current regime alone
  historical 2020-24   2020-22 and 2023-24 together (2026 excluded), and each of them alone
  all 2020-26          every period pooled, for reference only
Per basis:
  rate        confirmations per month, with an exact Poisson 95% interval
  point       N / rate months
  poisson     time to N if the rate were known exactly (Gamma(N, rate)): 10th / 50th / 90th percentiles
  predictive  with the rate's own sampling uncertainty (Jeffreys: rate ~ Gamma(k + 1/2, months)): 10th / 50th / 90th
  bootstrap   whole calendar months of the period resampled with replacement (keeps the clustering of real signals)
  horizon     decided results expected by the A2 horizon (predictive: Poisson(rate x horizon months)) and the chance of
              reaching each look by then
Every figure assumes the basis's rate holds for the whole test (stationarity); see the write-up for what that means.

  python research/tools/b24_schedule.py --cf research/results/cf_validation.json --out research/results/b24_schedule.json \
      --md research/B24_SCHEDULE.md
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from quantum.research import harness as H

LOOKS = (30, 50, 75, 100)
SEED, SIMS = 20261110, 100_000
PARTS = {"recent": "2026", "validation": "2023-24", "development": "2020-22"}
# the order matters only for the random stream: the 2026 basis is drawn first, as in the run that fixed the horizon
BASES = (("2026", ["recent"]), ("historical 2020-24", ["validation", "development"]), ("2023-24", ["validation"]),
         ("2020-22", ["development"]), ("all 2020-26 (reference)", ["recent", "validation", "development"]))


def months_of(part: dict) -> tuple[float, list[str]]:
    a, b = pd.Timestamp(part["scored_from"]), pd.Timestamp(part["window"][1])
    span = (b - a).days / 30.44
    cal = [str(p) for p in pd.period_range(a.tz_convert(None).to_period("M"), b.tz_convert(None).to_period("M"), freq="M")]
    return span, cal


def poisson_ci(k: int, t: float) -> list[float]:
    lo = stats.chi2.ppf(0.025, 2 * k) / 2 / t if k else 0.0
    hi = stats.chi2.ppf(0.975, 2 * k + 2) / 2 / t
    return [float(lo), float(hi)]


def q(x: np.ndarray) -> dict:
    return {"p10": float(np.quantile(x, 0.1)), "p50": float(np.quantile(x, 0.5)), "p90": float(np.quantile(x, 0.9))}


def basis(name: str, k: int, months: float, monthly: list[int], rng) -> dict:
    rate = k / months
    out = {"basis": name, "confirmations": k, "months": months, "rate_per_month": rate, "rate_ci95": poisson_ci(k, months),
           "looks": {}}
    lam = rng.gamma(k + 0.5, 1.0 / months, SIMS)                     # Jeffreys posterior for the monthly rate
    mc = np.asarray(monthly, float)
    for n in LOOKS:
        pois = stats.gamma.ppf([0.1, 0.5, 0.9], n, scale=1.0 / rate) if rate > 0 else [math.inf] * 3
        pred = rng.gamma(n, 1.0 / lam)
        # bootstrap: whole months drawn with replacement until n confirmations; months needed
        need = np.full(20_000, np.nan)
        if mc.sum() > 0:
            draws = rng.choice(mc, size=(20_000, int(np.ceil(n / max(mc.mean(), 1e-9) * 4)) + 24))
            cum = np.cumsum(draws, axis=1)
            hit = cum >= n
            need = np.where(hit.any(axis=1), hit.argmax(axis=1) + 1, np.nan).astype(float)
        out["looks"][n] = {"point_months": n / rate if rate > 0 else None,
                           "poisson_months": dict(zip(("p10", "p50", "p90"), (float(x) for x in pois), strict=True)),
                           "predictive_months": q(pred),
                           "bootstrap_months": q(need[np.isfinite(need)]) if np.isfinite(need).any() else None}
    out["_lam"] = lam
    return out


def at_horizon(b: dict, hm: float, rng) -> dict:
    """H-ALL: confirmations by the horizon under this basis (predictive, uncapped), and P(each look reached by then)."""
    cnt = rng.poisson(b["_lam"] * hm)
    return {"point": b["rate_per_month"] * hm, "predictive": q(cnt),
            "p_look_by_horizon": {n: float(np.mean(cnt >= n)) for n in LOOKS}}


def sides_in_sample(lb: np.ndarray, ls: np.ndarray, hm: float, rng) -> dict:
    """H-BUY / H-SELL are tested on their share of the test's sample: H-ALL's first 100 results, or fewer if the
    horizon comes first. Per draw: n = min(Poisson((lb + ls) x horizon), 100); BUY ~ Binomial(n, lb / (lb + ls))."""
    n = np.minimum(rng.poisson((lb + ls) * hm), LOOKS[-1])
    nb = rng.binomial(n, lb / (lb + ls))
    out = {}
    for side, c in (("BUY", nb), ("SELL", n - nb)):
        out[side] = {"in_sample": q(c), "p_look": {L: float(np.mean(c >= L)) for L in LOOKS}}
    return out


def build(cf: dict) -> dict:
    rng = H.seeded_rng(SEED)
    P = cf["parts"]
    per = {}
    for key, label in PARTS.items():
        span, cal = months_of(P[key])
        tr = P[key]["plans"]["T15"]["after_capped_confirmation"]["trades"]
        mon = [pd.Timestamp(t["t_entry"], unit="s").strftime("%Y-%m") for t in tr]
        per[key] = {"label": label, "span_months": span, "calendar_months": cal, "scale_s": P[key].get("scale_s"),
                    "all": [mon.count(m) for m in cal],
                    "BUY": [sum(1 for t, m in zip(tr, mon, strict=True) if m == c and t["dir"] > 0) for c in cal],
                    "SELL": [sum(1 for t, m in zip(tr, mon, strict=True) if m == c and t["dir"] < 0) for c in cal]}
    res = {"tool": "research/tools/b24_schedule.py", "source": "research/results/cf_validation.json (capped rule, amendment A1)",
           "seed": SEED, "sims": SIMS, "looks": list(LOOKS), "periods": {}, "bases": {}}
    for v in per.values():
        res["periods"][v["label"]] = {"months": v["span_months"], "confirmations": sum(v["all"]), "BUY": sum(v["BUY"]),
                                      "SELL": sum(v["SELL"]), "scale_s": v["scale_s"],
                                      "monthly_counts": dict(zip(v["calendar_months"], v["all"], strict=True))}
    for side in ("all", "BUY", "SELL"):
        res["bases"][side] = {}
        for nm, keys in BASES:
            k = sum(sum(per[x][side]) for x in keys)
            m = sum(per[x]["span_months"] for x in keys)
            monthly = [c for x in keys for c in per[x][side]]
            res["bases"][side][nm] = basis(nm, k, m, monthly, rng)
    # A2's maximum administrative horizon: the 90th percentile of the predictive months to 100 decided results at the
    # 2026 frequency, rounded up to whole years. It bounds the test's length; it does not promise 100 results.
    p90 = res["bases"]["all"]["2026"]["looks"][100]["predictive_months"]["p90"]
    horizon_years = math.ceil(p90 / 12.0)
    hm = horizon_years * 12
    res["a2_horizon"] = {"rule": "ceil(90th percentile of the predictive months to 100 decided results at the 2026 frequency / 12)",
                         "p90_months": p90, "years": horizon_years, "months": hm}
    for nm, _ in BASES:
        B = {side: res["bases"][side][nm] for side in ("all", "BUY", "SELL")}
        B["all"]["at_horizon"] = at_horizon(B["all"], hm, rng)
        sides = sides_in_sample(B["BUY"]["_lam"], B["SELL"]["_lam"], hm, rng)
        for side in ("BUY", "SELL"):
            B[side]["at_end_in_sample"] = sides[side]
        for b in B.values():
            b.pop("_lam")
    return res


def _y(m) -> str:
    return "—" if m is None or not np.isfinite(m) else f"{m / 12:.1f}"


def _pct(p: float) -> str:
    return "<1%" if 0 < p < 0.005 else (">99%" if 0.995 < p < 1 else f"{p:.0%}")


def _look_table(res: dict, names: list[str]) -> list[str]:
    L = ["| Hypothesis | Basis | Rate / month (95% CI) | Look | Point | Rate known (10-50-90%) | With the rate's uncertainty (10-50-90%) | Resampled months (10-50-90%) |",
         "|---|---|---|---|---|---|---|---|"]
    for side, hyp in (("all", "H-ALL"), ("BUY", "H-BUY"), ("SELL", "H-SELL")):
        for nm in names:
            b = res["bases"][side][nm]
            for n, lk in b["looks"].items():
                po, pr, bs = lk["poisson_months"], lk["predictive_months"], lk["bootstrap_months"]
                L.append(f"| {hyp} | {nm} | {b['rate_per_month']:.2f} ({b['rate_ci95'][0]:.2f}-{b['rate_ci95'][1]:.2f}) | {n} | "
                         f"{_y(lk['point_months'])} | {_y(po['p10'])} - {_y(po['p50'])} - {_y(po['p90'])} | "
                         f"{_y(pr['p10'])} - {_y(pr['p50'])} - {_y(pr['p90'])} | "
                         + (f"{_y(bs['p10'])} - {_y(bs['p50'])} - {_y(bs['p90'])} |" if bs else "— |"))
    return L


def _horizon_table(res: dict, names: list[str]) -> list[str]:
    y = res["a2_horizon"]["years"]
    L = [f"| Basis | H-ALL confirmations in {y} years, uncapped: point (predictive 10-50-90%) | Look 30 reached | 50 | 75 | 100 |",
         "|---|---|---|---|---|---|"]
    for nm in names:
        h = res["bases"]["all"][nm]["at_horizon"]
        pr, p = h["predictive"], h["p_look_by_horizon"]
        L.append(f"| {nm} | {h['point']:.0f} ({pr['p10']:.0f} - {pr['p50']:.0f} - {pr['p90']:.0f}) | "
                 + " | ".join(_pct(p[n]) for n in LOOKS) + " |")
    L += ["", "H-BUY and H-SELL are tested on their share of the test's sample (H-ALL's first 100 results, or fewer if the",
          "horizon comes first), so neither can reach its own 100 look unless every result is in its direction:", "",
          "| Basis | H-BUY results in the sample (10-50-90%) | its look 30 / 50 / 75 reached | H-SELL results in the sample (10-50-90%) | its look 30 / 50 / 75 reached |",
          "|---|---|---|---|---|"]
    for nm in names:
        row = [nm]
        for side in ("BUY", "SELL"):
            e = res["bases"][side][nm]["at_end_in_sample"]
            row += [f"{e['in_sample']['p10']:.0f} - {e['in_sample']['p50']:.0f} - {e['in_sample']['p90']:.0f}",
                    " / ".join(_pct(e["p_look"][n]) for n in LOOKS[:3])]
        L.append("| " + " | ".join(row) + " |")
    return L


def markdown(res: dict) -> str:
    h = res["a2_horizon"]
    per = res["periods"]
    a26 = res["bases"]["all"]["2026"]
    hist = res["bases"]["all"]["historical 2020-24"]
    p100_26 = a26["at_horizon"]["p_look_by_horizon"][100]
    p100_h = hist["at_horizon"]["p_look_by_horizon"][100]
    s = {lab: p["scale_s"] for lab, p in per.items()}
    L = ["# B24: expected time to 30 / 50 / 75 / 100 decided results, from the measured signal frequency", "",
         f"Generated by `{res['tool']}` from `{res['source']}` (seed {res['seed']}, {res['sims']:,} draws).",
         "B24's stream is the engine signals confirmed under amendment A1 (a 15m close $15-$20 beyond the trigger price);",
         "every confirmation becomes one decided result. Only how OFTEN a confirmation happened is used here, never an",
         "outcome. No frequency is raised, no criterion is weakened and no trigger category is pooled with another.", "",
         "**Every projection below assumes that the basis's rate holds, unchanged, for the whole test (stationarity).**",
         "Section 5 explains why that assumption is weak; the 2026 and the historical assumptions are shown separately.", "",
         "## 1. Measured frequency (capped rule, research data)", "",
         "| Period | Months scored | Confirmations | BUY / SELL | Per month (95% CI) | Distance scale s (mean, range) |",
         "|---|---|---|---|---|---|"]
    for lab, p in per.items():
        ci = poisson_ci(p["confirmations"], p["months"])
        sc = p["scale_s"] or {}
        L.append(f"| {lab} | {p['months']:.1f} | {p['confirmations']} | {p['BUY']} / {p['SELL']} | "
                 f"{p['confirmations'] / p['months']:.2f} ({ci[0]:.2f}-{ci[1]:.2f}) | "
                 f"{sc.get('mean', float('nan')):.2f} ({sc.get('min', float('nan')):.2f}-{sc.get('max', float('nan')):.2f}) |")
    L += ["", "Monthly counts: " + "; ".join(f"{lab}: " + ", ".join(f"{m} {c}" for m, c in p["monthly_counts"].items() if c)
                                            for lab, p in per.items()) + ".", "",
          "The research measured B19's distances, $15 / $13 / $20 at a $4,000 gold price, scaled by s = trigger price / 4000.",
          f"So the 2026 rate is for distances about {s['2026']['mean']:.2f} x the live ones (live: $15-$20 fixed), and the 2020-24",
          "rates are for the same *relative* move when gold was near $2,000. No period measured the live, fixed-dollar rule",
          "exactly; the live rate is only known once B24 records it.", "",
          "## 2. Assumption A: the live frequency stays at the 2026 rate", "",
          "H-BUY / H-SELL rows give the time their own count would take; the test stops at H-ALL's 100th result (section 4).", "",
          *_look_table(res, ["2026"]), "",
          "## 3. Assumption B: the live frequency returns to the historical (2020-24) rate", "",
          "2026 is excluded here. The two historical periods are shown together and alone.", "",
          *_look_table(res, ["historical 2020-24", "2023-24", "2020-22"]), "",
          "Reference only (every period pooled, weighted by months, so mostly history):", "",
          *_look_table(res, ["all 2020-26 (reference)"]), "",
          f"## 4. The maximum administrative horizon in amendment A2: {h['years']} years", "",
          f"**{h['years']} years after B24's start is the longest the test may run.** It is an administrative limit, so the test",
          "cannot stay open for ever. **It is not a forecast or a guarantee that 100, or even 30, results will be collected.**",
          "If it comes first, the test ends **INSUFFICIENT EVIDENCE**: never PROVEN, never NOT PROVEN, never a statement",
          "about accuracy. Only a registered look decides; the horizon adds no look and lowers no threshold.", "",
          (f"Rule: {h['rule']} = {h['p90_months']:.0f} months, rounded up to {h['years']} years. The rule uses frequencies"
           " only, never an outcome. It was written before the number was computed, but after the per-period frequencies in"
           " section 1 had been seen, so it is not blind to them."), "",
          "H-ALL confirmations expected by the horizon (uncapped: the test itself stops at the 100th result), and the chance",
          "that each look is reached by then, under each assumption:", "",
          *_horizon_table(res, ["2026", "historical 2020-24", "2023-24", "2020-22"]), "",
          "## 5. The 2026 figure and its stationarity assumption", "",
          (f"Under assumption A, the 100 look is reached within the horizon in **{_pct(p100_26)}** of the simulated futures; under"
           f" assumption B in **{_pct(p100_h)}**. The {_pct(p100_26)} is a model probability, not a confidence level and"
           " not a promise. It holds only if all of the following hold:"), "",
          (f"1. **Stationarity.** It treats the 2026 rate, {a26['rate_per_month']:.2f} a month from "
           f"{a26['confirmations']} confirmations in {a26['months']:.1f} months, as fixed for the next {h['years']} years."),
          f"   The rate of every earlier period was 3-4 times lower ({hist['rate_per_month']:.2f} a month in 2020-24).",
          f"   2026 is one regime (gold averaged about ${4000 * s['2026']['mean']:,.0f} in its scored months), not a law. If signals return to the",
          f"   2020-24 frequency, the 100 look is reached within the horizon in {_pct(p100_h)} of futures.",
          (f"2. **A small sample.** The {a26['confirmations']} events give an exact 95% interval of "
           f"{a26['rate_ci95'][0]:.2f}-{a26['rate_ci95'][1]:.2f} a month. The predictive figures include this sampling"),
          "   uncertainty, but not a change of regime, which is the larger risk.",
          "3. **Independent arrivals.** A Poisson process is assumed. Real signals cluster. The month bootstrap keeps that",
          "   clustering, but on 8-9 months of 2026 data it is crude.",
          "4. **Research rate = live rate.** The research scaled the distances (section 1) and used its own bar history. The",
          "   live site uses fixed $15-$20 on its own data feed, and site downtime turns rows into DATA GAP, which are never",
          "   decided. Each of these can move the live rate either way.",
          "5. **One result per confirmation.** TIMEOUT counts as decided; DATA GAP does not.", "",
          "So the honest reading is conditional. *If* the 2026 frequency persists, the test will most likely reach its final",
          "look within the horizon. *If* it reverts to the historical frequency, the test will most likely reach only the 30",
          "look, possibly the 50, and then end INSUFFICIENT EVIDENCE unless an early look proves it. H-BUY and H-SELL each get",
          "only their share of the sample: at the 2026 frequency (8 of 9 confirmations were SELL) H-SELL usually reaches its",
          "75 look and H-BUY rarely its 30; at the historical frequency H-BUY reaches its 30 look in about a third of futures",
          "and H-SELL in about one in eight. Each that is undecided at the",
          "end ends INSUFFICIENT EVIDENCE. The BUY / SELL split itself rests on 9 events in 2026 and is not stable across",
          "periods (2023-24: 5 BUY, 0 SELL).", "",
          "## 6. Monitoring the assumption without adapting the test", "",
          "Once a year from the start, the recorder appends a schedule report. It shows the live confirmation frequency with",
          "its exact 95% interval, the decided count per hypothesis, and the projected time to the next look from that live",
          "frequency. It reads no outcome and changes nothing: no look, threshold, horizon, stream or rule is adapted to it.", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cf", default=os.path.join("research", "results", "cf_validation.json"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--md")
    a = ap.parse_args(argv)
    with open(a.cf) as fh:
        res = build(json.load(fh))
    with open(a.out, "w") as fh:
        json.dump(res, fh, indent=1)
    if a.md:
        with open(a.md, "w") as fh:
            fh.write(markdown(res))
    print(f"horizon {res['a2_horizon']['years']} years ({res['a2_horizon']['p90_months']:.1f} months p90); written {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
