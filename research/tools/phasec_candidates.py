"""Phase C: every shortlisted (frozen) candidate's full statistics and the operator's six acceptance criteria.

Reads the final runs' summaries and frozen-trade CSVs (B27 corrected re-run, B28, B29 corrected re-run) and, per candidate
and period (development 2020-22; 2026 check):
  - trades, decided trades, TP-first (decided, Wilson 95%), SL-first, neither (timeout / closure) and closure shares,
  - net expectancy per oz (ENG costs) with a t 95% interval, per 0.50 lot (ASSUMED 100 oz), profit factor,
  - matched random rate, raw p, the BH-adjusted q of its development study, the Holm p of the 2026 check,
  - drawdown (0.50 lot) and its Monte Carlo 95th percentile, trades per week,
  - per-year results (2020, 2021, 2022 incl. Jan 2023; 2026) and results by session and volatility tercile
    (the decision bar's B26 context),
  - risk of ruin: P(drawdown >= $10,000 within 250 trades at 0.50 lot), by bootstrap of the development trades
    (ASSUMED context: a $100,000 account with a 10% maximum-loss rule).

Acceptance criteria (operator, 2026-11-09), all required:
  C1 positive net expectancy after costs: development AND 2026 expectancy > 0
  C2 better than matched random: Wilson lower bound > matched random, development AND 2026
  C3 multiple-testing evidence: BH-significant in its development study (q < 0.05) AND Holm p < 0.05 on 2026
  C4 stability: expectancy > 0 in every development year and in 2026, and in at least 2 of 3 volatility terciles
  C5 adequate independent sample: >= 300 decided development trades
  C6 drawdown / ruin: P(drawdown >= $10,000 within 250 trades) <= 5%

  python research/tools/phasec_candidates.py [--out-dir research/results/phasec]
"""
import argparse
import json
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from quantum.research import harness as H

RUNS = (("B27", "research/results/b27_fix"), ("B28", "research/results/b28"), ("B29", "research/results/b29_fix"))
LOT_OZ = 50
RUIN_USD, RUIN_N, RUIN_PATHS = 10_000.0, 250, 2000
# Risk audit assumptions (every money figure depends on them; NONE is a verified broker outcome)
ACCOUNT_USD = 100_000.0           # ASSUMED starting balance, account currency USD
CONTRACT_OZ = 100                 # ASSUMED contract size of 1.00 lot (broker specification not supplied)
LOT = 0.50                        # the operator's size: 0.50 lot = 50 oz = $50 per $1 move (ASSUMED contract)
THRESHOLDS = (2_500.0, 5_000.0, 10_000.0)   # 2.5% / 5% / 10% of the ASSUMED balance
BLOCK = 10                        # block bootstrap: circular blocks of 10 consecutive trades
OUTER, INNER = 200, 200           # nested bootstrap for the 95% interval of each breach probability
ADV_EXTRA = {"spread_in": 0.30, "spread_off": 0.50, "slip_in": 0.20, "slip_out": 0.20}   # ADV minus ENG, $ per oz


def bh_q(ps: list[float]) -> list[float]:
    m = len(ps)
    order = np.argsort(ps)
    q = np.empty(m)
    prev = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        prev = min(prev, ps[i] * m / rank)
        q[i] = prev
    return q.tolist()


def study_q(s: dict, run: str) -> dict:
    """Configuration id -> BH-adjusted q within its registered development study."""
    out = {}
    if run == "B27":
        groups = [s[k] for k in ("S1", "S2", "S3", "S5")]
    elif run == "B28":
        groups = [s["configs"]]
    else:
        groups = [s[k] for k in ("M", "C", "E")]
        v = s["V"]                                           # V: the pooled test per bracket (registration amendment 3)
        br = sorted({tuple(c["bracket"]) for c in v})
        pb = {b: next(c["p_pooled_eng"] for c in v if tuple(c["bracket"]) == b) for b in br}
        qb = dict(zip(br, bh_q([pb[b] for b in br]), strict=True))
        out.update({c["id"]: qb[tuple(c["bracket"])] for c in v})
    for g in groups:
        ps = [c["dev"].get("p_vs_random") if c["dev"].get("p_vs_random") is not None else 1.0 for c in g]
        out.update(dict(zip([c["id"] for c in g], bh_q(ps), strict=True)))
    return out


def context_map() -> dict:
    m = {}
    for P in ("P1", "P2"):
        b = pd.read_csv(f"research/results/b26/b26_trades_{P}.csv.gz", usecols=["fill_utc", "vol_tercile"]).drop_duplicates("fill_utc")
        m.update(dict(zip(b["fill_utc"], b["vol_tercile"].fillna("NA"), strict=True)))
    return m


def period_stats(x: pd.DataFrame, ctx: dict, rng) -> dict:
    out_, net = x["outcome"].to_numpy(), x["net"].to_numpy(float)
    n = len(x)
    k = int((out_ == "TP").sum())
    nsl = int(np.isin(out_, ["SL", "AMBIGUOUS"]).sum())
    nd = k + nsl
    lo, hi = H.wilson(k, nd) if nd else (math.nan, math.nan)
    mu = float(net.mean()) if n else math.nan
    se = float(net.std(ddof=1) / math.sqrt(n)) if n > 1 else math.nan
    wins, losses = net[net > 0].sum(), net[net < 0].sum()
    yr = pd.to_datetime(x["fill_t"]).dt.year.clip(upper=2022).where(pd.to_datetime(x["fill_t"]).dt.year < 2026, 2026)
    by_year = {int(y): {"n": int((yr == y).sum()), "r": _r(out_[yr == y]), "exp_oz": float(net[yr == y].mean())} for y in sorted(yr.unique())}
    sess = x["session"].to_numpy()
    by_sess = {s: {"n": int((sess == s).sum()), "r": _r(out_[sess == s]), "exp_oz": float(net[sess == s].mean())} for s in pd.unique(sess)}
    vt = np.asarray([ctx.get(t, "NA") for t in x["fill_t"]])
    by_vol = {v: {"n": int((vt == v).sum()), "r": _r(out_[vt == v]), "exp_oz": float(net[vt == v].mean())} for v in ("LOW", "MID", "HIGH")
              if (vt == v).any()}
    ruin = None
    if n >= 30:
        draws = rng.choice(net * LOT_OZ, size=(RUIN_PATHS, RUIN_N), replace=True).cumsum(axis=1)
        dd = (np.maximum.accumulate(np.maximum(draws, 0.0), axis=1) - draws).max(axis=1)
        ruin = float((dd >= RUIN_USD).mean())
    return {"trades": n, "decided": nd, "tp_first": k / nd if nd else None, "ci95": [lo, hi], "sl_first_share": nsl / n if n else None,
            "neither_share": float(np.isin(out_, ["TIMEOUT", "CLOSURE"]).mean()) if n else None,
            "closure_share": float((out_ == "CLOSURE").mean()) if n else None, "exp_oz": mu,
            "exp_ci95": [mu - 1.96 * se, mu + 1.96 * se] if n > 1 else [None, None], "exp_050lot": mu * LOT_OZ,
            "pf": float(wins / -losses) if losses < 0 else None, "by_year": by_year, "by_session": by_sess, "by_vol_tercile": by_vol,
            "p_dd_10k_in_250": ruin, "vol_context_matched": float((vt != "NA").mean()) if n else None}


def _max_dd(paths: np.ndarray) -> np.ndarray:
    """Peak-to-trough drawdown of cumulative P&L paths (rows), the start (0) counting as a peak."""
    cum = paths.cumsum(axis=1)
    return (np.maximum.accumulate(np.maximum(cum, 0.0), axis=1) - cum).max(axis=1)


def _breach(pool: np.ndarray, rng, n_paths: int = RUIN_PATHS, block: int | None = None) -> np.ndarray:
    """Max drawdowns of n_paths sequences of RUIN_N trades drawn from pool (iid, or circular blocks)."""
    if block:
        starts = rng.integers(0, len(pool), size=(n_paths, math.ceil(RUIN_N / block)))
        ix = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n_paths, -1)[:, :RUIN_N] % len(pool)
        return _max_dd(pool[ix])
    return _max_dd(rng.choice(pool, size=(n_paths, RUIN_N), replace=True))


def risk_audit(x_dev: pd.DataFrame, x_y: pd.DataFrame, ctx: dict, rng) -> dict:
    """Drawdown risk at 0.50 lot (ASSUMED 100 oz): breach probabilities of 2.5k / 5k / 10k within 250 trades under
    seven scenarios. The 95% interval of the iid figure comes from a nested bootstrap (outer resample of the trade pool)."""
    usd = LOT * CONTRACT_OZ
    dev = x_dev.sort_values("fill_t")
    net = dev["net"].to_numpy(float) * usd
    if len(net) < 30:
        return {}
    out = {"trades_dev": len(net), "expected_pnl_250": float(net.mean() * RUIN_N)}
    dd = _breach(net, rng)
    out["iid"] = {f"{int(t)}": float((dd >= t).mean()) for t in THRESHOLDS}
    ci = {f"{int(t)}": [] for t in THRESHOLDS}
    for _ in range(OUTER):
        pool = rng.choice(net, size=len(net), replace=True)
        d_ = _breach(pool, rng, INNER)
        for t in THRESHOLDS:
            ci[f"{int(t)}"].append((d_ >= t).mean())
    out["iid_ci95"] = {k: [float(np.quantile(v, 0.025)), float(np.quantile(v, 0.975))] for k, v in ci.items()}
    out["block"] = float((_breach(net, rng, block=BLOCK) >= RUIN_USD).mean())
    out["chronological_maxdd_first250"] = float(_max_dd(net[None, :RUIN_N])[0])
    out["chronological_maxdd_all"] = float(_max_dd(net[None, :])[0])
    vt = np.asarray([ctx.get(t, "NA") for t in dev["fill_t"]])
    for v in ("HIGH", "LOW"):
        pool = net[vt == v]
        out[f"vol_{v}"] = float((_breach(pool, rng) >= RUIN_USD).mean()) if len(pool) >= 30 else None
    sp = np.where(dev["session"].to_numpy() == "OFF", ADV_EXTRA["spread_off"], ADV_EXTRA["spread_in"])
    extra = (sp + ADV_EXTRA["slip_in"] + np.where(dev["outcome"].to_numpy() == "TP", 0.0, ADV_EXTRA["slip_out"])) * usd
    out["cost_stress"] = float((_breach(net - extra, rng) >= RUIN_USD).mean())
    ny = x_y["net"].to_numpy(float) * usd if len(x_y) else np.zeros(0)
    out["y2026"] = float((_breach(ny, rng) >= RUIN_USD).mean()) if len(ny) >= 30 else None
    return out


def markdown_risk(rows: list[dict]) -> str:
    L = ["### Risk audit: assumptions (identical for every candidate; NOT verified broker outcomes)\n",
         "| Item | Value |", "|---|---|",
         f"| Starting balance / currency | ${ACCOUNT_USD:,.0f} USD (ASSUMED) |",
         f"| Contract size | {CONTRACT_OZ} oz per 1.00 lot (ASSUMED; broker specification not supplied) |",
         f"| Position | fixed {LOT:.2f} lot = {LOT * CONTRACT_OZ:.0f} oz = ${LOT * CONTRACT_OZ:.0f} per $1 move (ASSUMED contract) |",
         "| Spread (ENG) | $0.30 per oz in session, $0.50 off session (modelled, not measured) |",
         "| Slippage (ENG) | $0.20 per oz on entry; $0.20 per oz on every exit except a filled target |",
         "| Commission (ENG) | $0.07 per oz ($7 per 1.00 lot, ASSUMED) |",
         "| Cost stress | ADV − ENG added per trade: + one more spread, + $0.20 entry and + $0.20 exit slippage |",
         "| Concurrency | one position at a time (the independent series); no pyramiding, no compounding, no other exposure |",
         f"| Drawdown | peak-to-trough of cumulative P&L from the start; over {RUIN_N} trades |",
         (f"| Simulation | {RUIN_PATHS:,} bootstrap paths per scenario; 95% interval of the iid figure from a nested bootstrap "
          f"({OUTER} outer resamples of the trade pool x {INNER} paths); block bootstrap = circular blocks of {BLOCK} trades |"),
         "| Thresholds | $2,500 / $5,000 / $10,000 = 2.5% / 5% / 10% of the ASSUMED balance (the 10% figure is the ruin line) |",
         "\n### Risk audit: probability of a drawdown within 250 trades at 0.50 lot (ASSUMED 100 oz)\n",
         ("| Run | Candidate | Dev trades | Expected P&L / 250 trades | P(DD >= $2.5k) (95%) | P(DD >= $5k) (95%) | P(DD >= $10k) (95%) | "
          "Block bootstrap $10k | Actual max DD, first 250 / all | HIGH vol only $10k | LOW vol only $10k | Cost stress $10k | 2026 trades $10k |"),
         "|" + "---|" * 13]
    for r in rows:
        a = r.get("risk") or {}
        if not a:
            L.append(f"| {r['run']} | {r['id']} | < 30 | — | — | — | — | — | — | — | — | — | — |")
            continue
        def pc(k, a=a):
            return f"{_p(a['iid'][k], 0)} ({_p(a['iid_ci95'][k][0], 0)}–{_p(a['iid_ci95'][k][1], 0)})"
        L.append(f"| {r['run']} | {r['id']} | {a['trades_dev']} | {_n(a['expected_pnl_250'], 0)} | {pc('2500')} | {pc('5000')} | {pc('10000')} | "
                 f"{_p(a['block'], 0)} | {_n(a['chronological_maxdd_first250'], 0, False)} / {_n(a['chronological_maxdd_all'], 0, False)} | "
                 f"{_p(a.get('vol_HIGH'), 0)} | {_p(a.get('vol_LOW'), 0)} | {_p(a['cost_stress'], 0)} | {_p(a.get('y2026'), 0)} |")
    return "\n".join(L)


def _r(o):
    k = int((o == "TP").sum())
    n = k + int(np.isin(o, ["SL", "AMBIGUOUS"]).sum())
    return k / n if n else None


def criteria(c: dict) -> dict:
    d, y = c["dev"], c["y2026"]
    yrs = [v["exp_oz"] for v in d["by_year"].values() if v["n"] >= 30]
    vol = [v["exp_oz"] for v in d["by_vol_tercile"].values() if v["n"] >= 30]
    q, ph = c.get("dev_bh_q"), c.get("y2026_holm_p")
    crit = {
        "C1_positive_expectancy": bool(d["exp_oz"] > 0 and (y.get("exp_oz") or -1) > 0),
        "C2_beats_matched_random": bool(d["ci95"][0] > (c["dev_random"] or 1) and (y.get("ci95") or [0])[0] > (c["y2026_random"] or 1)),
        "C3_multiple_testing": bool(q is not None and q < 0.05 and ph is not None and ph < 0.05),
        "C4_stable": bool(yrs and all(e > 0 for e in yrs) and (y.get("exp_oz") or -1) > 0 and sum(e > 0 for e in vol) >= 2),
        "C5_sample": bool(d["decided"] >= 300),
        "C6_drawdown_ruin": bool(d["p_dd_10k_in_250"] is not None and d["p_dd_10k_in_250"] <= 0.05),
    }
    crit["QUALIFIES"] = all(crit.values())
    return crit


def _p(x, d=1):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:.{d}f}%"


def _n(x, d=2, sign=True):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x:+.{d}f}" if sign else f"{x:.{d}f}"


def markdown(rows: list[dict]) -> str:
    L = ["### Every shortlisted candidate: outcomes, expectancy, baselines, significance, risk\n",
         ("| Run | Candidate | Dev decided (trades) | Dev TP-first (95%) | SL-first | Neither | Dev exp / oz (95%) | Dev random | Dev BH q | "
          "2026 decided | 2026 TP-first (95%) | 2026 random | 2026 exp / oz | 2026 Holm p | Max DD 0.5 lot (MC95) | Trades / wk | P(DD >= $10k in 250) |"),
         "|" + "---|" * 17]
    for r in rows:
        d, y = r["dev"], r["y2026"]
        L.append(f"| {r['run']} | {r['id']} | {d['decided']} ({d['trades']}) | {_p(d.get('tp_first'))} ({_p(d['ci95'][0])}–{_p(d['ci95'][1])}) | "
                 f"{_p(d.get('sl_first_share'))} | {_p(d.get('neither_share'))} | {_n(d.get('exp_oz'))} ({_n((d.get('exp_ci95') or [None])[0])} to "
                 f"{_n((d.get('exp_ci95') or [None, None])[1])}) | {_p(r['dev_random'])} | {_n(r['dev_bh_q'], 3, False)} | {y.get('decided')} | "
                 f"{_p(y.get('tp_first'))} ({_p(y['ci95'][0])}–{_p(y['ci95'][1])}) | {_p(r['y2026_random'])} | {_n(y.get('exp_oz'))} | "
                 f"{_n(r['y2026_holm_p'], 3, False)} | {_n(r['max_dd_050lot'], 0, False)} ({_n(r['mc_dd95_050lot'], 0, False)}) | "
                 f"{_n(r['per_week'], 1, False)} | {_p(d.get('p_dd_10k_in_250'), 0)} |")
    L += ["\n### Stability and the six acceptance criteria (C1–C6; QUALIFIES needs all six)\n",
          ("| Run | Candidate | Exp 2020 | Exp 2021 | Exp 2022 | Exp 2026 | Exp LOW / MID / HIGH vol | Sessions with exp > 0 (n >= 30) | "
           "C1 exp > 0 | C2 > random | C3 BH + Holm | C4 stable | C5 n >= 300 | C6 ruin <= 5% | QUALIFIES |"), "|" + "---|" * 15]
    for r in rows:
        d, y, c = r["dev"], r["y2026"], r["criteria"]
        yr = {**d["by_year"], **y["by_year"]}
        vol = " / ".join(_n((d["by_vol_tercile"].get(v) or {}).get("exp_oz")) for v in ("LOW", "MID", "HIGH"))
        ss = [v for v in d["by_session"].values() if v["n"] >= 30]
        L.append(f"| {r['run']} | {r['id']} | " + " | ".join(_n((yr.get(k) or yr.get(str(k)) or {}).get("exp_oz")) for k in (2020, 2021, 2022, 2026))
                 + f" | {vol} | {sum(v['exp_oz'] > 0 for v in ss)} of {len(ss)} | "
                 + " | ".join("yes" if c[k] else "no" for k in ("C1_positive_expectancy", "C2_beats_matched_random", "C3_multiple_testing",
                                                             "C4_stable", "C5_sample", "C6_drawdown_ruin", "QUALIFIES")) + " |")
    n_q = sum(r["criteria"]["QUALIFIES"] for r in rows)
    keys = [k for k in rows[0]["criteria"] if k != "QUALIFIES"]
    L.append(f"\nCandidates: {len(rows)}. Passing each criterion: " + "; ".join(f"{k.split('_')[0]} {sum(r['criteria'][k] for r in rows)}" for k in keys)
             + f". **Qualifying (all six): {n_q}.**")
    L.append("\nExpectancy in $ per oz after ENG costs (development in 4,000-equivalent dollars). Neither = timeout or closure. "
             "Risk of ruin: bootstrap of the development trades, 2,000 paths of 250 trades at 0.50 lot (ASSUMED 100 oz).")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="research/results/phasec")
    ap.add_argument("--b27", default=RUNS[0][1])
    ap.add_argument("--b29", default=RUNS[2][1])
    a = ap.parse_args(argv)
    runs = (("B27", a.b27), RUNS[1], ("B29", a.b29))
    ctx = context_map()
    rng = H.seeded_rng(29)
    rows = []
    for run, d in runs:
        with open(os.path.join(d, f"{run.lower()}_summary.json")) as fh:
            s = json.load(fh)
        t = pd.read_csv(os.path.join(d, f"{run.lower()}_frozen_trades.csv.gz"))
        q = study_q(s, run)
        for c in s["frozen"]:
            rec = {"run": run, "id": c["id"], "study": c.get("study", "B28"), "dir": c.get("dir"), "board": c.get("board"),
                   "dev_random": c["dev"].get("matched_random"), "dev_p": c["dev"].get("p_vs_random"), "dev_bh_q": q.get(c["id"]),
                   "y2026_random": (c.get("y2026") or {}).get("matched_random"), "y2026_p": (c.get("y2026") or {}).get("p_vs_random"),
                   "y2026_holm_p": c.get("y2026_holm_p"), "max_dd_050lot": c["dev"].get("max_dd_050lot_ASSUMED"),
                   "mc_dd95_050lot": c["dev"].get("mc_dd95_050lot_ASSUMED"), "per_week": c["dev"].get("per_week")}
            for per, key in (("DEV", "dev"), ("Y2026", "y2026")):
                x = t[(t["candidate"] == c["id"]) & (t["period"] == per)]
                rec[key] = period_stats(x, ctx, rng) if len(x) else {"trades": 0, "decided": 0, "ci95": [None, None], "by_year": {},
                                                                     "by_session": {}, "by_vol_tercile": {}, "p_dd_10k_in_250": None}
                ref = c.get("dev" if per == "DEV" else "y2026") or {}
                if ref.get("n_decided") is not None and len(x):
                    assert rec[key]["decided"] == ref["n_decided"], (run, c["id"], per, rec[key]["decided"], ref["n_decided"])
            rec["risk"] = risk_audit(t[(t["candidate"] == c["id"]) & (t["period"] == "DEV")],
                                     t[(t["candidate"] == c["id"]) & (t["period"] == "Y2026")], ctx, rng)
            rec["criteria"] = criteria(rec)
            rows.append(rec)
    os.makedirs(a.out_dir, exist_ok=True)
    with open(os.path.join(a.out_dir, "candidates.json"), "w") as fh:
        json.dump(rows, fh, indent=1, default=float)
    flat = [{"run": r["run"], "id": r["id"], **{f"dev_{k}": r["dev"].get(k) for k in ("trades", "decided", "tp_first", "sl_first_share",
            "neither_share", "exp_oz", "exp_050lot", "pf", "p_dd_10k_in_250")}, "dev_lo": r["dev"]["ci95"][0], "dev_hi": r["dev"]["ci95"][1],
            "dev_exp_lo": (r["dev"].get("exp_ci95") or [None])[0], "dev_exp_hi": (r["dev"].get("exp_ci95") or [None, None])[1],
            "dev_random": r["dev_random"], "dev_p": r["dev_p"], "dev_bh_q": r["dev_bh_q"],
            **{f"y2026_{k}": r["y2026"].get(k) for k in ("trades", "decided", "tp_first", "sl_first_share", "neither_share", "exp_oz")},
            "y2026_lo": r["y2026"]["ci95"][0], "y2026_random": r["y2026_random"], "y2026_holm_p": r["y2026_holm_p"],
            "max_dd_050lot": r["max_dd_050lot"], "mc_dd95_050lot": r["mc_dd95_050lot"], "per_week": r["per_week"],
            **{f"exp_{y}": (r["dev"]["by_year"].get(y) or r["y2026"]["by_year"].get(y) or {}).get("exp_oz") for y in (2020, 2021, 2022, 2026)},
            **r["criteria"]} for r in rows]
    pd.DataFrame(flat).to_csv(os.path.join(a.out_dir, "candidates.csv"), index=False, float_format="%.4f")
    with open(os.path.join(a.out_dir, "candidates.md"), "w") as fh:
        fh.write(markdown(rows) + "\n\n" + markdown_risk(rows) + "\n")
    n_q = sum(r["criteria"]["QUALIFIES"] for r in rows)
    print(json.dumps({"candidates": len(rows), "qualifying": n_q,
                      "criteria_passed": {k: sum(r["criteria"][k] for r in rows) for k in rows[0]["criteria"]}}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
