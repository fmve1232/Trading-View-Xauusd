"""PR #90 final audit (operator request 2026-11-07, sections 2-3): reproduce the reported 2020-22 figures independently,
then report sample sizes, intervals, trade definitions, expectancy after costs, BUY / SELL, regimes, sessions, years,
drawdown, losing streaks, entry-latency sensitivity and the out-of-sample record.

Independence: the outcomes are recomputed by a fresh loop written from the rule text (no b19 / confirm_panel code),
and every trade is compared with b19.plan_and_exit; every trigger price is checked against the raw close of its bar.
Data: development (2020-01-24 -> 2023-01-24, scored from 2020-04-01, open) and "recent" (2026-01-01 -> the end of the
research history, scored from 2026-03-01; not a sealed partition, after the holdout, never used to choose any rule).
The sealed validation / holdout partitions are NOT read; the 2023-24 figure quoted comes from the committed B19 file.
Research tool: never imported by production. Descriptive: no registration is passed or failed here.

Trade definition (all rows): BUY / SELL at the trigger's direction; entry at the trigger close ("at the trigger") or at
the first 15m close $15 beyond the trigger price ("after a $15 close"; invalid if price first trades $13 against the
trigger price or a 15m structure break prints the other way; expired after 96 bars); stop -$13 and target +$15 / +$20
from the entry; a bar opening beyond a level fills at the open; a bar touching both levels counts as the stop; time
stop after 192 bars at the close; distances scaled by price / 4000; net = $ per oz at $4,000 after the model cost
(session spread + 2 x 0.20 slippage + $7 / lot commission, $0.77-0.97); "operator cost" uses $0.26 instead.
Latency variants: the same confirmed trades entered at the next bar's open, or one full bar (15 minutes) later.

  python research/tools/pr90_audit.py --rd <research-data dir> --out research/results/pr90_audit_2026-11-07.json [--trials research/trials.jsonl]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from quantum import notify
from quantum.data import sources
from quantum.research import b10, b13, b19, b21
from quantum.research import harness as H

HEADLINE = {"random entries (N2, at the trigger)": ("N2", "none"), "engine signals after a $15 close": ("ENG", "X15F0"),
            "liquidity grabs after a $15 close": ("GRAB", "X15F0"), "breakouts after a $15 close": ("BREAKOUT", "X15F0")}
TF_SEC = {"15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}


def wilson(k: int, n: int) -> list:
    if not n:
        return [None, None]
    z, p = 1.959964, k / n
    den = 1 + z * z / n
    mid, half = (p + z * z / (2 * n)) / den, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [mid - half, mid + half]


def binom_tail(k: int, n: int, p: float) -> float:
    """P(X >= k), X ~ Binomial(n, p), exact."""
    return float(sum(math.comb(n, j) * p ** j * (1 - p) ** (n - j) for j in range(k, n + 1)))


# ---------------- an independent implementation, from the rule text ----------------
def confirm_indep(P, j0: int, p0: float, d: int, X: float | None, s: float) -> int | None:
    """The bar whose close confirms, or None (invalidated / expired). X None = no confirmation (entry at the trigger)."""
    if X is None:
        return j0 - 1
    for b in range(j0, j0 + 96):
        against = (p0 - P.l[b]) if d > 0 else (P.h[b] - p0)
        if against >= 13.0 * s - 1e-9 or (P.dn_evt[b] if d > 0 else P.up_evt[b]):
            return None
        if (P.c[b] - p0) * d >= X * s - 1e-9:
            return b
    return None


def exit_from(P, start: int, entry: float, d: int, T: float, s: float, open_counts_on_first: bool) -> tuple[str, float]:
    tp, sl = entry + d * T * s, entry - d * 13.0 * s
    for b in range(start, start + 192):
        if open_counts_on_first or b > start:
            if (P.o[b] - sl) * d <= 0:
                return "SL", P.o[b]
            if (P.o[b] - tp) * d >= 0:
                return "TP", P.o[b]
        hit_tp = (P.h[b] >= tp) if d > 0 else (P.l[b] <= tp)
        hit_sl = (P.l[b] <= sl) if d > 0 else (P.h[b] >= sl)
        if hit_tp and hit_sl:
            return "AMBIGUOUS", sl
        if hit_tp:
            return "TP", tp
        if hit_sl:
            return "SL", sl
    return "TIMEOUT", P.c[start + 191]


def streak(outs: list[str]) -> int:
    best = cur = 0
    for x in outs:
        cur = cur + 1 if x != "TP" else 0
        best = max(best, cur)
    return best


def group(rows: list[dict], key) -> dict:
    out: dict = {}
    for r in rows:
        for g in key(r):
            out.setdefault(g, []).append(r)
    res = {}
    for g, v in sorted(out.items()):
        k = sum(x["out"] == "TP" for x in v)
        res[g] = {"n": len(v), "tp_first": k / len(v), "ci95": wilson(k, len(v)), "mean_net": float(np.mean([x["net"] for x in v]))}
    return res


# ---------------- data ----------------
def build(rd: str, part: str, log=print) -> dict:
    m15, h1, score_from = b19.load_part(rd, part)
    runs = b19.engine_runs(m15, h1, log)
    res15 = runs["15m"][0]
    up, dn = b19.struct_arrays(res15, len(m15))
    P = b19.make_path(m15, up, dn)
    t_from = int(score_from.timestamp())
    eng = b19.dedupe([x for tf, (res, F) in runs.items() for x in b19.triggers_from_run(res, F, tf, "ENG") if x["t_close"] >= t_from])
    trig, P21 = b21.alerts(m15, h1, score_from, log)
    assert np.array_equal(P21.c, P.c) and np.array_equal(P21.up_evt, P.up_evt)
    rows = np.flatnonzero(P.t >= t_from)[::8]
    rows = rows[(rows >= b19.SSTR_LOOKBACK) & (rows + 1 + b19.WIN + b19.HOLD + b19.LIMIT_BARS < len(P.t))]
    n2 = [{"tf": "15m", "kind": "N2", "i": int(i), "t_close": int(P.t[i]) + 900, "dir": sg, "p0": float(P.c[i]), "regime": ""}
          for i in rows for sg in (1, -1)]
    fams = {"ENG": b19.attach(eng, P), "N2": b19.attach(n2, P), **{k: b19.attach(v, P) for k, v in trig.items()}}
    closes = {"15m": m15["close"], "30m": sources.resample_ohlc(m15, "30min")["close"], "1h": h1["close"],
              "4h": sources.resample_ny_session(h1, 4)["close"]}
    vol = P.atr / P.c
    return {"m15": m15, "P": P, "fams": fams, "reg15": np.asarray(res15.rows["regime_label"], object), "closes": closes,
            "vol_q80": float(np.nanquantile(vol, 0.8)), "vol": vol, "score_from": str(score_from)}


def check_trigger_prices(D: dict) -> dict:
    """Every trigger price must be the raw close of its own bar on its own timeframe."""
    bad = n = 0
    for A in D["fams"].values():
        for tr in A["trig"]:
            ser = D["closes"][tr["tf"]]
            ts = pd.Timestamp(tr["t_close"] - TF_SEC[tr["tf"]], unit="s", tz="UTC")
            n += 1
            if ts not in ser.index or abs(float(ser.loc[ts]) - tr["p0"]) > 1e-6:
                bad += 1
    return {"checked": n, "mismatched": bad}


def measure(D: dict, fam: str, conf: str, T: float, variant: str, nw: list) -> dict:
    P, A = D["P"], D["fams"][fam]
    C = b19.confirm(P, A, conf)
    R = b19.plan_and_exit(P, A, C, conf, "E1", "S13", T)
    ex = set(np.flatnonzero(R["execute"]).tolist())
    X = {"none": None, "X15F0": 15.0}[conf]
    rows, mism, conf_mism = [], 0, 0
    for x in range(len(A["d"])):
        d, p0, j0 = int(A["d"][x]), float(A["p0"][x]), int(A["j0"][x])
        s = p0 / 4000.0
        k = confirm_indep(P, j0, p0, d, X, s)
        if (k is not None) != (x in ex) or (k is not None and conf != "none" and k != int(C["k"][x])):
            conf_mism += 1
        if k is None:
            continue
        cost = float(P.cost[k])
        if variant == "E1":
            entry = p0 if conf == "none" else float(P.c[k])
            out, px = exit_from(P, k + 1 if conf != "none" else j0, entry, d, T, s, True)
        elif variant == "next_open":
            entry = float(P.o[k + 1])
            out, px = exit_from(P, k + 1, entry, d, T, s, False)
        else:                                                         # one full bar later, at its close
            entry = float(P.c[k + 1])
            out, px = exit_from(P, k + 2, entry, d, T, s, True)
        net = (px - entry) * d / s - cost
        if variant == "E1" and (out != R["outcome"][x] or abs(net - R["net"][x]) > 1e-6):
            mism += 1
        tr = A["trig"][x]
        reg = str(tr.get("regime") or D["reg15"][j0 - 1])
        labels = ["trending" if reg in ("STRONG TR", "EXPANSION") else "ranging" if reg in b10.RANGE_REGIMES else "other"]
        if D["vol"][j0 - 1] >= D["vol_q80"]:
            labels.append("volatile (ATR/price in the top 20%)")
        if any(a <= tr["t_close"] <= b for a, b in nw):
            labels.append("news (within 2 h after CPI / NFP / FOMC)")
        rows.append({"t_trigger": int(tr["t_close"]), "t_entry": int(P.t[k]) + 900 if conf != "none" else int(tr["t_close"]),
                     "tf": tr["tf"], "dir": d, "p0": round(p0, 2), "entry": round(entry, 2), "out": out, "net": float(net),
                     "op_net": float(net + cost - b13.OP_COST), "r": float(net / 13.0), "session": notify.session_of(int(tr["t_close"])),
                     "year": datetime.fromtimestamp(int(tr["t_close"]), timezone.utc).year, "labels": labels})
    rows.sort(key=lambda z: z["t_entry"])
    n = len(rows)
    k = sum(r["out"] == "TP" for r in rows)
    nets = np.array([r["net"] for r in rows])
    eq = np.concatenate([[0.0], np.cumsum([r["r"] for r in rows])])
    wins, losses = nets[nets > 0], nets[nets < 0]
    return {"trades": n, "k": k, "tp_first": k / n if n else None, "ci95": wilson(k, n), "triggers": len(A["d"]),
            "independent_mismatch": {"outcome_or_net": mism, "confirmation": conf_mism} if variant == "E1" else None,
            "stop_first": sum(r["out"] in ("SL", "AMBIGUOUS") for r in rows) / n if n else None,
            "neither_192_bars": sum(r["out"] == "TIMEOUT" for r in rows) / n if n else None,
            "expectancy_usd_per_oz_model_cost": float(nets.mean()) if n else None,
            "expectancy_usd_per_oz_operator_cost": float(np.mean([r["op_net"] for r in rows])) if n else None,
            "profit_factor": float(wins.sum() / -losses.sum()) if len(losses) else None,
            "max_drawdown_r": float((np.maximum.accumulate(eq) - eq).max()) if n else 0.0,
            "longest_losing_streak": streak([r["out"] for r in rows]),
            "buy": group([r for r in rows if r["dir"] > 0], lambda r: ["BUY"]).get("BUY"),
            "sell": group([r for r in rows if r["dir"] < 0], lambda r: ["SELL"]).get("SELL"),
            "by_regime": group(rows, lambda r: r["labels"]), "by_session": group(rows, lambda r: [r["session"]]),
            "by_year": group(rows, lambda r: [str(r["year"])]), "trades_list": rows if n <= 60 else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials")
    a = ap.parse_args(argv)
    out = {"what": "PR #90 final audit: independent reproduction and statistics (descriptive)", "parts": {}}
    for part in ("development", "recent"):
        D = build(a.rd, part)
        nw = b19.news_windows() if part == "development" else []
        res = {"window": [str(D["m15"].index[0]), str(D["m15"].index[-1])], "scored_from": D["score_from"],
               "trigger_prices": check_trigger_prices(D), "rows": {}}
        print(part, "trigger prices", res["trigger_prices"], flush=True)
        for name, (fam, conf) in HEADLINE.items():
            for T in (15.0, 20.0):
                for variant in (("E1",) if conf == "none" else ("E1", "next_open", "one_bar_later")):
                    key = f"{name} | +${T:g} | {variant}"
                    m = measure(D, fam, conf, T, variant, nw)
                    res["rows"][key] = m
                    print(part, key, m["trades"], round(m["tp_first"] or 0, 4), m["independent_mismatch"], flush=True)
        out["parts"][part] = res
    dev = out["parts"]["development"]["rows"]
    eng, rnd = dev["engine signals after a $15 close | +$15 | E1"], dev["random entries (N2, at the trigger) | +$15 | E1"]
    with open("research/results/b21_development_2026-11-07.json") as fh:
        n2c = json.load(fh)["results"]["N2 X15F0 T15"]["tp_first"]
    with open("research/results/b19_development_2026-11-07.json") as fh:
        n_cfg = sum(1 for key in json.load(fh)["configs"] if key.startswith("ENG "))
    k, n = eng["k"], eng["trades"]
    rec = out["parts"]["recent"]["rows"]
    out["engine_60_noise"] = {
        "k": k, "n": n, "rate": k / n, "ci95": wilson(k, n),
        "p_one_sided_vs_random_at_trigger": binom_tail(k, n, rnd["tp_first"]),
        "p_one_sided_vs_random_triggers_after_a_15_close": binom_tail(k, n, n2c),
        "p_one_sided_vs_break_even_model_cost": binom_tail(k, n, (13.0 + 0.83) / 28.0),
        "engine_configurations_measured_in_B19_development": n_cfg,
        "chance_one_of_that_many_independent_20_trade_samples_reaches_12": 1 - (1 - binom_tail(12, 20, n2c)) ** n_cfg,
        "out_of_sample": {"2023-24 validation, +$20 only (committed B19 file)": "5 of 7",
                          "2026 recent, this audit": {kk: {"k": v["k"], "n": v["trades"], "ci95": v["ci95"],
                                                           "expectancy_usd_per_oz_model_cost": v["expectancy_usd_per_oz_model_cost"]}
                                                      for kk, v in rec.items() if kk.startswith("engine") and kk.endswith("E1")}}}
    out["utc"] = datetime.now(timezone.utc).isoformat()
    with open(a.out, "w") as fh:
        json.dump(b13._clean(out), fh, indent=1, allow_nan=False)
    if a.trials:
        for kk, v in rec.items():
            if kk.endswith("E1"):
                H.log_trial(a.trials, {"phase": "PR90-audit", "partition": "recent (2026-03-01 on, unsealed)", "id": kk, "n": v["trades"],
                                       "success": v["tp_first"], "ci95": v["ci95"],
                                       "net_usd_per_oz": v["expectancy_usd_per_oz_model_cost"], "verdict": "DESCRIPTIVE"})
    print(json.dumps(b13._clean(out["engine_60_noise"]), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
