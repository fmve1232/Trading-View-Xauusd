"""B31b-W2 (research/registrations/B31b-W2.json): why modules C, D and E produce so few trades.

Operator, 2026-11-15: "Retain original strategy definitions. Investigate why the available sample sizes are low. Do not
loosen filters merely to generate more trades. Report every rejected setup and rejection reason."

Nothing is changed and nothing is measured about performance. For every C / D / E setup of B31 (quantum/research/b31.py,
unchanged definitions) this records its fate and the reason, with the distances the checks compared, under the two
reward rules that exist: B31's (net R:R at +$10) and the ladder rule the operator adopted (net R:R at the ladder's mean,
+$15), which the live B31b-SHADOW-FWD uses. It also counts the stages before a setup exists (the upstream funnel).

No outcome leaves this module: b31.run_module computes exits because the one-position rule needs them, and its trades
are discarded here. Research code: never imported by production."""
from __future__ import annotations

import argparse
import csv
import json

import numpy as np
import pandas as pd

from . import b13, b19, b31, history
from . import harness as H

REG = "B31b-W2"
MODS = ("C", "D", "E")
RULES = {"tp1_10": b31.TP[0], "ladder_15": float(np.mean(b31.TP))}      # the reward the net R:R check uses
PARTS = ("development", "validation", "holdout", "recent")
ROW_KEYS = ("part", "mod", "t", "dir", "kind", "entry_type", "D", "cost", "cost_frac", "room", "vwap_room", "rr_tp1_10",
            "rr_ladder_15", "fate_tp1_10", "why_tp1_10", "fate_ladder_15", "why_ladder_15")
Q = (10, 25, 50, 75, 90)


def load_part(rd: str, part: str):
    """b31.load_part with this registration opening the sealed partitions."""
    if part == "recent":
        m15, h1 = history.load(rd, "XAU/USD", "15min"), history.load(rd, "XAU/USD", "1h")
        lo = H.HOLD[1]
        m15, h1 = m15[m15.index >= lo], h1[h1.index >= lo]
        return m15, h1, lo + pd.Timedelta(days=59)
    reg = REG if part in b31.SEALED else None
    m15 = H.partition(history.load(rd, "XAU/USD", "15min"), part, reg)
    h1 = H.partition(history.load(rd, "XAU/USD", "1h"), part, reg)
    start = b13.SCORE_FROM if part == "development" else m15.index[0] + pd.Timedelta(days=67)
    return m15, h1, start


def context(m15: pd.DataFrame, h1: pd.DataFrame, start) -> tuple[b31.Ctx, int]:
    runs = b19.engine_runs(m15, h1, lambda *_: None)
    res15, F15 = runs["15m"]
    return b31.make_ctx(m15, h1, res15, F15), int(start.timestamp())


def _scored(X: b31.Ctx, bar: int, t_from: int) -> bool:
    return X.t[bar] + 900 >= t_from


# ---------------- the stages before a setup exists ----------------
def upstream_c(X: b31.Ctx, evs: list[dict], t_from: int) -> dict:
    ev = [e for e in evs if _scored(X, e["k"], t_from)]
    acc = [e for e in ev if e["status"] == "ACCEPTED"]
    return {"first_crossings_of_a_pool": len(ev), "rejected_within_3_bars": len(ev) - len(acc), "accepted_3_closes_beyond": len(acc),
            "accepted_with_an_fvg_in_the_breakout_leg": sum(b31.seq_break(X, e) is not None for e in acc)}


def upstream_d(X: b31.Ctx, t_from: int) -> dict:
    """The same loop as b31.setups(X, 'D'), with a count at each stage. `all_setups` is every setup the loop finds (scored
    or not): run() checks it against b31.setups so the two can never drift apart unnoticed."""
    n = len(X.c)
    out = {"ranging_bars": 0, "first_bars_of_a_2_sigma_deviation": 0, "closed_back_inside_within_3_bars": 0,
           "vetoed_by_a_strong_displacement_body": 0, "setups": 0, "all_setups": 0}
    for j in range(1, n):
        if not X.ranging[j]:
            continue
        sc = _scored(X, j, t_from)
        out["ranging_bars"] += sc
        for d in (1, -1):
            dev = X.l[j] <= X.lo2[j] if d == 1 else X.h[j] >= X.up2[j]
            if not dev or (X.l[j - 1] <= X.lo2[j - 1] if d == 1 else X.h[j - 1] >= X.up2[j - 1]):
                continue
            out["first_bars_of_a_2_sigma_deviation"] += sc
            ks = [k for k in range(j, min(j + b31.REJECT_BARS, n)) if (X.c[k] > X.lo2[k] if d == 1 else X.c[k] < X.up2[k])]
            if not ks:
                continue
            out["closed_back_inside_within_3_bars"] += sc
            k = ks[0]
            if ((X.o[j:k + 1] - X.c[j:k + 1]) * d >= b31.DISP_BODY * X.atr[j:k + 1]).any():
                out["vetoed_by_a_strong_displacement_body"] += sc
                continue
            out["setups"] += sc
            out["all_setups"] += 1
    return {k: int(v) for k, v in out.items()}


def upstream_e(X: b31.Ctx, evs: list[dict], t_from: int) -> dict:
    """The same selection as b31.setups(X, 'E'): the day's first Asia-range crossing in London / New York."""
    first = {}
    for ev in evs:
        if ev["kind"] in ("ASH", "ASL") and X.sess[ev["j"]] in ("LONDON", "NEW YORK", "LONDON+NY") \
                and X.asia_date[ev["j"]] == X.date[ev["j"]] and X.date[ev["j"]] not in first:
            first[X.date[ev["j"]]] = ev
    days = {X.date[i] for i in range(len(X.c)) if _scored(X, i, t_from)}
    sel = [e for e in first.values() if _scored(X, e["k"], t_from)]
    sw = [e for e in sel if e["status"] == "REJECTED"]
    br = [e for e in sel if e["status"] == "ACCEPTED"]
    return {"trading_days": len(days), "days_with_a_first_asia_range_crossing_in_london_or_ny": len(sel),
            "of_which_a_sweep_rejected": len(sw), "of_which_a_break_accepted": len(br),
            "sweeps_with_a_structure_shift_and_an_entry_zone": sum((b31.seq_sweep(X, e, "A") or b31.seq_sweep(X, e, "B")) is not None for e in sw),
            "breaks_with_an_fvg_in_the_breakout_leg": sum(b31.seq_break(X, e) is not None for e in br)}


# ---------------- every setup, its fate and the reason ----------------
def _rr(m: dict, reward: float) -> float | None:
    return float((reward - m["cost"]) / (m["D"] + m["cost"])) if m.get("D") is not None and m["D"] + m["cost"] > 0 else None


def order_life(X: b31.Ctx, sets: list[dict], t_from: int) -> tuple[dict, list[dict], list[dict]]:
    """({rule: stat}, one row per setup with its fate under each rule (distances rounded to the cent, for the CSV), the
    unrounded measurements of every setup that was not a repeat (for the tables)). The outcomes run_module computes are
    dropped."""
    stats, traces = {}, {}
    for rule, reward in RULES.items():
        tr: list = []
        stats[rule] = b31.run_module(X, sets, t_from, "model", reward, tr)["stat"]
        traces[rule] = tr
    a, b = traces["tp1_10"], traces["ladder_15"]
    assert len(a) == len(b) == stats["tp1_10"]["setups"] == stats["ladder_15"]["setups"]
    rows, raw = [], []
    for x, y in zip(a, b, strict=True):
        assert (x["t"], x["dir"], x["kind"]) == (y["t"], y["dir"], y["kind"])     # the same setups in the same order
        row = {"t": x["t"], "dir": x["dir"], "kind": x["kind"], "entry_type": x["entry_type"],
               **{k: (round(x[k], 2) if x.get(k) is not None else None) for k in ("D", "cost", "cost_frac", "room", "vwap_room")}}
        for rule, z in (("tp1_10", x), ("ladder_15", y)):                         # a repeat has no measured distances
            r = _rr(x, RULES[rule]) if x.get("D") is not None else None
            row.update({f"rr_{rule}": round(r, 2) if r is not None else None, f"fate_{rule}": z["fate"], f"why_{rule}": z["why"]})
        rows.append(row)
        if x.get("D") is not None:
            raw.append({**{k: x.get(k) for k in ("D", "cost", "cost_frac", "room", "vwap_room")},
                        **{f"rr_{rule}": _rr(x, rw) for rule, rw in RULES.items()},
                        **{f"fate_{rule}": z["fate"] for rule, z in (("tp1_10", x), ("ladder_15", y))}})
    return stats, rows, raw


CHECKS = ("stop", "reward", "cost", "room")                # b31.check's order (after "stop on the wrong side")


def fails(m: dict, rule: str) -> list[str]:
    """Every check this setup fails under `rule`, in b31.check's order (b31.check reports only the first)."""
    if m["D"] <= 0:
        return ["stop on the wrong side"]
    out = []
    if m["D"] < b31.D_MIN - b31.EPS:
        out.append("stop")
    if m[f"rr_{rule}"] < b31.RR_MIN - b31.EPS:
        out.append("reward")
    if m["cost"] > b31.COST_FRAC * m["D"] + b31.EPS:
        out.append("cost")
    if any(m.get(k) is not None and m[k] < b31.TP[0] - b31.EPS for k in ("room", "vwap_room")):
        out.append("room")
    return out


def failures(raw: list[dict]) -> dict:
    """Per rule, over the setups that were not repeats: how many fail each check on its own (a setup can fail several),
    how many fail that check and no other, and how many pass every check."""
    res = {}
    for rule in RULES:
        f = [fails(m, rule) for m in raw]
        res[rule] = {"measured": len(raw), "pass_every_check": sum(not x for x in f),
                     "fail": {c: sum(c in x for x in f) for c in CHECKS + ("stop on the wrong side",)},
                     "fail_only": {c: sum(x == [c] for x in f) for c in CHECKS}}
    return res


def distances(rows: list[dict]) -> dict:
    """Where the measured stop distances lie (setups that were not repeats; unrounded), beside the windows the rules
    allow."""
    D = np.array([r["D"] for r in rows if r["D"] is not None and r["D"] > 0], float)
    if not len(D):
        return {"n": 0}
    c = float(np.median([r["cost"] for r in rows if r["cost"] is not None]))
    return {"n": int(len(D)), "percentiles_usd": {str(q): round(float(np.percentile(D, q)), 2) for q in Q},
            "below_5": int((D < b31.D_MIN).sum()), "from_5_to_the_tp1_rule_limit": int(((D >= b31.D_MIN) & (D <= RULES["tp1_10"] - 2 * c)).sum()),
            "from_there_to_the_ladder_rule_limit": int(((D > RULES["tp1_10"] - 2 * c) & (D <= RULES["ladder_15"] - 2 * c)).sum()),
            "above_the_ladder_rule_limit": int((D > RULES["ladder_15"] - 2 * c).sum()), "median_cost": round(c, 2),
            "tp1_rule_limit_usd": round(RULES["tp1_10"] - 2 * c, 2), "ladder_rule_limit_usd": round(RULES["ladder_15"] - 2 * c, 2)}


def run(rd: str, part: str, log=print) -> dict:
    m15, h1, start = load_part(rd, part)
    X, t_from = context(m15, h1, start)
    evs = b31.crossings(X, b31.SELL_SIDE + b31.BUY_SIDE)
    sets = {m: b31.setups(X, m, evs) for m in MODS}
    up = {"C": upstream_c(X, evs, t_from), "D": upstream_d(X, t_from), "E": upstream_e(X, evs, t_from)}
    assert up["D"].pop("all_setups") == len(sets["D"]), "the D funnel no longer matches b31.setups"
    out = {"meta": {"part": part, "bars_15m": len(m15), "scored_from": str(start), "data_hash_15m": H.data_hash(m15),
                    "years_scored": round((X.t[-1] + 900 - t_from) / (365.25 * 86400), 2)},
           "upstream": up, "modules": {}, "rows": []}
    for m in MODS:
        stats, rows, raw = order_life(X, sets[m], t_from)
        out["modules"][m] = {"rules": stats, "stop_distance": distances(raw), "checks": failures(raw)}
        out["rows"] += [dict(r, part=part, mod=m) for r in rows]
        log(f"[B31b-W2] {part} {m}: setups {stats['tp1_10']['setups']}, executed {stats['tp1_10']['executed']} (TP1 rule) / "
            f"{stats['ladder_15']['executed']} (ladder rule)")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True, help="the research history directory")
    ap.add_argument("--parts", default=",".join(PARTS))
    ap.add_argument("--out", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--trials")
    a = ap.parse_args(argv)
    res = {"registration": REG, "rules": RULES, "parts": {}}
    rows = []
    for part in a.parts.split(","):
        r = run(a.rd, part)
        rows += r.pop("rows")
        res["parts"][part] = r
        if a.trials:
            H.log_trial(a.trials, {"reg": REG, "part": part, "key": "C+D+E|counts", "data_hash_15m": r["meta"]["data_hash_15m"],
                                   "setups": {m: r["modules"][m]["rules"]["ladder_15"]["setups"] for m in MODS},
                                   "executed_tp1_rule": {m: r["modules"][m]["rules"]["tp1_10"]["executed"] for m in MODS},
                                   "executed_ladder_rule": {m: r["modules"][m]["rules"]["ladder_15"]["executed"] for m in MODS},
                                   "outcomes_inspected": False})
    with open(a.out, "w") as f:
        json.dump(res, f, indent=1)
    with open(a.csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ROW_KEYS)
        w.writeheader()
        w.writerows(rows)
    print(f"[B31b-W2] {len(rows)} setups written to {a.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
