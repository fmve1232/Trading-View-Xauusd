"""Validation of the two-stage rule the confirmation panel shows (quantum/confirm_panel.py = B19 ENG X15F0 E1 S13).

Uses B19's registered functions only (quantum/research/b19.py: engine runs, triggers, REPEAT, confirmation, exits); no
parameter is chosen here. Periods: development 2020-04-01 -> 2023-01-24 (in sample: B19 was designed on it),
validation 2023 -> 2024-07 (out of sample; opened for B19 under its approved registration), and 2026 (out of sample,
not sealed). The holdout is not read.

Per period, for the engine-signal trigger (15m / 30m / 1h / 4h, REPEAT-pooled):
  funnel      setups (triggers), $15 confirmations, % confirmed, invalidated by price / by structure, expired;
  plan        entry at the confirming 15m close, SL -$13, TP1 +$15 / TP2 +$20 (each its own trade, as the panel), on 15m
              bars: TP / SL / AMBIGUOUS (= SL) / TIMEOUT (192 bars) counts with Wilson 95% intervals;
  money       net $ per oz under the research cost model (spread by session + 2 x $0.20 slippage + $0.07 commission),
              the operator's measured $0.26, and a stress case (twice the model cost); expectancy with a t interval,
              profit factor, average win / loss, maximum drawdown (R) and the longest losing streak;
  splits      BUY / SELL, timeframe, calendar year, news window (dated releases only; coverage reported), and the same
              plan entered AT THE TRIGGER with no confirmation (what the confirmation adds, and how many setups it gives
              up). Not reported: the at-trigger result split by whether the confirmation later passed. That split is
              decided by the future (a +$15 confirmation close implies the at-trigger +$15 target was hit), so it
              measures nothing.
  timing      the confirmed plan entered one 15m bar later (the next close; start the bar after): the site shows a
              confirmation 3-66 min after the close, so the confirming close itself is not a fill a person can get.
  capped      amendment B24-CONFIRM-FWD-A1 (operator, 2026-11-10): the same confirmations, but one whose confirming
              close is more than $20 beyond the trigger price is EXPIRED (overshoot) instead. Reported beside the
              original rule, never instead of it; the cap was the operator's decision before these figures existed.
  trades      price-free per-trade rows (entry time, direction, timeframe, outcome, net / gross / cost in the units
              below) so every figure can be recomputed, and the two out-of-sample periods pooled.
Distances are $ at $4,000 scaled by s = P0 / 4000 in every period, as B19 registered them. B19 subtracts the cost
UNSCALED from that scaled move (its docstring: "costs are $ per oz, unscaled"), which under-weights the cost by 1 / s when
gold traded far below $4,000 (2020-24). The figures here put the cost in the same units as the move (cost / s); B19's own
figure is kept as net_b19 so the run still reproduces it.

  python research/tools/cf_validation.py --rd <research-data checkout> --out research/results/cf_validation.json \
      --md research/CF_VALIDATION.md --log research/trials.jsonl
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from quantum.research import b19 as B
from quantum.research import harness as H

PARTS = ("development", "validation", "recent")
LABEL = {"development": "development 2020-22 (in sample)", "validation": "validation 2023-24 (out of sample)",
         "recent": "2026 (out of sample)"}
OP_COST = B.OP_COST
CAP = 20.0                                # amendment A1: the confirming close at most $20 beyond (at $4,000 scale)


def _ci_mean(x: np.ndarray) -> list:
    if len(x) < 2:
        return [None, None]
    m, se = float(np.mean(x)), float(np.std(x, ddof=1) / math.sqrt(len(x)))
    return [m - 1.96 * se, m + 1.96 * se]


def _streak(x: np.ndarray) -> int:
    best = cur = 0
    for v in x:
        cur = cur + 1 if v < 0 else 0
        best = max(best, cur)
    return best


STOP = 13.0                                   # S13: the stop in $ at $4,000, so R = net / 13 in the same units


def stats(out: np.ndarray, net_b19: np.ndarray, cost: np.ndarray, s: np.ndarray, t: np.ndarray) -> dict:
    """net_b19 = B19's net (scaled move - unscaled cost); everything else uses the cost in the move's units (cost / s)."""
    o = np.argsort(t, kind="stable")
    out, net_b19, cost, s = out[o], net_b19[o], cost[o], s[o]
    gross = net_b19 + cost
    net = gross - cost / s
    r = net / STOP
    n = len(out)
    tp, sl, amb, to = (int((out == k).sum()) for k in ("TP", "SL", "AMBIGUOUS", "TIMEOUT"))
    dec = tp + sl + amb
    op = gross - OP_COST / s
    stress = gross - 2 * cost / s
    win, loss = net[net > 0], net[net < 0]

    def wil(k, m):
        return list(H.wilson(k, m)) if m else [None, None]
    return {"trades": n, "tp": tp, "sl": sl, "ambiguous": amb, "timeout": to,
            "tp_rate": tp / n if n else None, "tp_rate_ci95": wil(tp, n),
            "sl_rate": (sl + amb) / n if n else None, "sl_rate_ci95": wil(sl + amb, n),
            "tp_first_decided": tp / dec if dec else None, "tp_first_decided_ci95": wil(tp, dec),
            "net_model": float(net.mean()) if n else None, "net_model_ci95": _ci_mean(net),
            "net_model_total": float(net.sum()) if n else 0.0, "net_b19": float(net_b19.mean()) if n else None,
            "net_operator_cost": float(op.mean()) if n else None, "net_stress_2x_cost": float(stress.mean()) if n else None,
            "gross": float(gross.mean()) if n else None, "cost_model_mean": float((cost / s).mean()) if n else None,
            "cost_model_mean_unscaled": float(cost.mean()) if n else None,
            "profit_factor": float(win.sum() / -loss.sum()) if len(loss) and loss.sum() < 0 else None,
            "avg_win": float(win.mean()) if len(win) else None, "avg_loss": float(loss.mean()) if len(loss) else None,
            "max_drawdown_r": B.max_drawdown(r) if n else 0.0, "longest_losing_streak": _streak(net)}


def trade_rows(out: np.ndarray, net_b19: np.ndarray, cost: np.ndarray, s: np.ndarray, t: np.ndarray, d: np.ndarray,
               tf: np.ndarray) -> list[dict]:
    o = np.argsort(t, kind="stable")
    return [{"t_entry": int(t[i]), "dir": int(d[i]), "tf": str(tf[i]), "outcome": str(out[i]),
             "net": float(net_b19[i] + cost[i] - cost[i] / s[i]), "gross": float(net_b19[i] + cost[i]),
             "cost": float(cost[i] / s[i]), "net_operator_cost": float(net_b19[i] + cost[i] - OP_COST / s[i])} for i in o]


def pooled(rows: list[dict]) -> dict:
    """Statistics over price-free trade rows (the out-of-sample periods pooled)."""
    out = np.asarray([r["outcome"] for r in rows], object)
    net = np.asarray([r["net"] for r in rows], float)
    gross = np.asarray([r["gross"] for r in rows], float)
    cost = np.asarray([r["cost"] for r in rows], float)
    n = len(rows)
    tp = int((out == "TP").sum())
    win, loss = net[net > 0], net[net < 0]
    return {"trades": n, "tp": tp, "tp_rate": tp / n if n else None, "tp_rate_ci95": list(H.wilson(tp, n)) if n else [None, None],
            "net_model": float(net.mean()) if n else None, "net_model_ci95": _ci_mean(net),
            "net_operator_cost": float(np.mean([r["net_operator_cost"] for r in rows])) if n else None,
            "net_stress_2x_cost": float((gross - 2 * cost).mean()) if n else None,
            "profit_factor": float(win.sum() / -loss.sum()) if len(loss) else None,
            "max_drawdown_r": B.max_drawdown(net / STOP) if n else 0.0, "longest_losing_streak": _streak(net)}


def news_windows() -> list[tuple[int, int]]:
    from quantum import news_calendar
    w = list(B.news_windows())
    w += [(int(e["t"]), int(e["t"]) + 7200) for e in news_calendar.events()]
    return w


def run_part(rd: str, part: str, log=print) -> dict:
    m15, h1, score_from = B.load_part(rd, part)
    runs = B.engine_runs(m15, h1, log)
    res15, _ = runs["15m"]
    up, dn = B.struct_arrays(res15, len(m15))
    P = B.make_path(m15, up, dn)
    t_from = int(score_from.timestamp())
    trig = [x for tf, (res, F) in runs.items() for x in B.triggers_from_run(res, F, tf, "ENG")]
    trig = B.dedupe([x for x in trig if x["t_close"] >= t_from])
    A = B.attach(trig, P)
    d = A["d"]
    tf = np.asarray([x["tf"] for x in A["trig"]], object)
    nw = news_windows()
    near = np.asarray([any(a - 1800 <= x["t_close"] <= b for a, b in nw) for x in A["trig"]], bool)
    lo_t, hi_t = int(m15.index[0].timestamp()), int(m15.index[-1].timestamp())
    news_cov = sum(1 for a, _ in nw if max(lo_t, t_from) <= a <= hi_t)
    s_all = A["p0"] / 4000.0
    yr = np.asarray([str(np.datetime64(int(x["t_close"]), "s"))[:4] for x in A["trig"]], object)
    C = B.confirm(P, A, "X15F0")
    C0 = B.confirm(P, A, "none")
    st = C["status"]
    inv = C.get("inv_kind", np.array([""] * len(d), object))
    cf = np.flatnonzero(st == "CONFIRMED")
    move = (P.c[C["k"][cf]] - A["p0"][cf]) * d[cf] / (A["p0"][cf] / 4000.0) if len(cf) else np.zeros(0)
    C1 = dict(C)                                         # the same confirmations, entered one 15m bar later
    C1["k"] = np.where(st == "CONFIRMED", C["k"] + 1, C["k"])
    mv_all = np.full(len(d), np.nan)
    mv_all[cf] = move
    over = (st == "CONFIRMED") & (mv_all > CAP + 1e-9)    # amendment A1: an overshoot of the cap is EXPIRED
    Cc = dict(C)
    Cc["status"] = np.where(over, "EXPIRED", st).astype(object)
    Cc1 = dict(Cc)
    Cc1["k"] = np.where(Cc["status"] == "CONFIRMED", C["k"] + 1, C["k"])
    stc = Cc["status"]
    funnel = {"setups": len(d), "confirmed": int((st == "CONFIRMED").sum()),
              "confirmed_share": float((st == "CONFIRMED").mean()) if len(d) else None,
              "confirmed_share_ci95": list(H.wilson(int((st == "CONFIRMED").sum()), len(d))) if len(d) else [None, None],
              "invalidated_price": int(((st == "INVALIDATED") & (inv == "price")).sum()),
              "invalidated_structure": int(((st == "INVALIDATED") & (inv == "structure")).sum()),
              "expired": int((st == "EXPIRED").sum()),
              "confirmation_move_mean": float(move.mean()) if len(move) else None,
              "confirmation_move_max": float(move.max()) if len(move) else None,
              "bars_to_confirmation_median": float(np.median(C["k"][cf] - A["j0"][cf] + 1)) if len(cf) else None,
              "by_direction": {nm: {"setups": int((d == dd).sum()), "confirmed": int(((d == dd) & (st == "CONFIRMED")).sum())}
                               for dd, nm in ((1, "BUY"), (-1, "SELL"))},
              "by_timeframe": {k: {"setups": int((tf == k).sum()), "confirmed": int(((tf == k) & (st == "CONFIRMED")).sum())}
                               for k in B.TFS},
              "capped": {"confirmed": int((stc == "CONFIRMED").sum()), "expired_overshoot": int(over.sum()),
                         "confirmed_share": float((stc == "CONFIRMED").mean()) if len(d) else None,
                         "confirmed_share_ci95": list(H.wilson(int((stc == "CONFIRMED").sum()), len(d))) if len(d) else [None, None],
                         "overshoot_moves": sorted(round(float(x), 2) for x in mv_all[over]),
                         "by_direction": {nm: int(((d == dd) & (stc == "CONFIRMED")).sum()) for dd, nm in ((1, "BUY"), (-1, "SELL"))}}}
    out = {"part": part, "label": LABEL[part], "window": [str(m15.index[0]), str(m15.index[-1])], "scored_from": str(score_from),
           "data_hash_15m": H.data_hash(m15), "funnel": funnel, "plans": {},
           "scale_s": {"min": float(s_all.min()), "max": float(s_all.max()), "mean": float(s_all.mean())} if len(d) else None,
           "news_releases_in_period": news_cov,
           "news_split": "measured" if news_cov else "NOT MEASURABLE: no dated release in this period's calendar"}
    for T in (15.0, 20.0):
        key = f"T{T:g}"
        for nm, CC, conf in (("after_confirmation", C, "X15F0"), ("at_trigger_no_confirmation", C0, "none"),
                             ("after_confirmation_one_bar_later", C1, "X15F0"), ("after_capped_confirmation", Cc, "X15F0"),
                             ("after_capped_confirmation_one_bar_later", Cc1, "X15F0")):
            T_ = B.plan_and_exit(P, A, CC, conf, "E1", "S13", T)
            ex = T_["execute"]

            def sub(m, T_=T_, ex=ex):
                s_ = ex & m
                return stats(T_["outcome"][s_].astype(object), T_["net"][s_], T_["cost"][s_], s_all[s_], T_["t_entry"][s_])
            blk = {"all": sub(np.ones(len(d), bool)), "BUY": sub(d == 1), "SELL": sub(d == -1),
                   "by_timeframe": {k: sub(tf == k) for k in B.TFS},
                   "by_year": {y: sub(yr == y) for y in sorted(set(yr))},
                   "news_window": sub(near), "outside_news": sub(~near), "rejected_by_rules": int(T_["rejected"].sum())}
            blk["trades"] = trade_rows(T_["outcome"][ex].astype(object), T_["net"][ex], T_["cost"][ex], s_all[ex],
                                       T_["t_entry"][ex], d[ex], tf[ex])
            out["plans"].setdefault(key, {})[nm] = blk
    log(f"[cf] {part}: {funnel['setups']} setups, {funnel['confirmed']} confirmed")
    return out


# ---------------- the write-up, generated from the JSON (no figure is typed by hand) ----------------
def _p(x, nd=0):
    return "—" if x is None else f"{100 * x:.{nd}f}%"


def _u(x, nd=2):
    return "—" if x is None else f"{x:+.{nd}f}"


def _ci(c, pct=False):
    if not c or c[0] is None:
        return "—"
    return f"{_p(c[0])}–{_p(c[1])}" if pct else f"{c[0]:+.2f} to {c[1]:+.2f}"


def _pf(x) -> str:
    return "—" if x is None else f"{x:.2f}"


def _be(T: float, c: float) -> float:
    """Break-even target-first rate for +T before -13 at a round-trip cost c ($ per oz): p (T - c) = (1 - p) (13 + c)."""
    return (STOP + c) / (T + STOP)


def _row(nm: str, a: dict) -> str:
    return (f"| {nm} | {a['trades']} | {a['tp']} / {a['sl'] + a.get('ambiguous', 0)} / {a.get('timeout', 0)} | {_p(a['tp_rate'])} "
            f"({_ci(a['tp_rate_ci95'], True)}) | {_u(a['net_model'])} ({_ci(a['net_model_ci95'])}) | {_u(a['net_operator_cost'])} | "
            f"{_u(a['net_stress_2x_cost'])} | {_pf(a['profit_factor'])} | "
            f"{_u(a['avg_win'])} / {_u(a['avg_loss'])} | {a['max_drawdown_r']:.1f} | {a['longest_losing_streak']} |")


PLAN_NAME = {"after_capped_confirmation": "CAPPED (live rule, A1): confirming close $15-$20 beyond, entry at it",
             "after_capped_confirmation_one_bar_later": "CAPPED, entered one 15m bar later",
             "after_confirmation": "original (no cap): first close $15+ beyond, entry at it",
             "after_confirmation_one_bar_later": "original, entered one 15m bar later",
             "at_trigger_no_confirmation": "at the trigger, no confirmation"}
HDR = ("| Plan | Trades | TP / SL (incl. ambiguous) / timeout | Target first (95% CI) | Net $/oz, model cost (95% CI) | "
       "Net at your $0.26 | Net at 2x model cost | PF | Avg win / loss | Max DD (R) | Longest losing run |\n"
       "|---|---|---|---|---|---|---|---|---|---|---|")


def markdown(res: dict) -> str:
    P = res["parts"]
    L = ["# Two-stage alert: setup, $15 confirmation, plan — historical validation",
         "",
         f"Generated by `{res['tool']}` from `research/results/cf_validation.json`. Rule: {res['rule']}. Units: {res['units']}.",
         "Historical research only: the frozen engine replayed on stored history; the live forward test is separate and untouched.",
         "Every figure below is computed by that tool from B19's registered functions; nothing here was tuned: the distances,",
         "windows and filters are B19's, fixed before any of these periods was scored.",
         "",
         "## Verdict",
         ""]
    po = res["pooled_out_of_sample"]["T15"]["after_confirmation"]
    po1 = res["pooled_out_of_sample"]["T15"]["after_confirmation_one_bar_later"]
    pc = res["pooled_out_of_sample"]["T15"]["after_capped_confirmation"]
    pc1 = res["pooled_out_of_sample"]["T15"]["after_capped_confirmation_one_bar_later"]
    pt = res["pooled_out_of_sample"]["T15"]["at_trigger_no_confirmation"]
    c26 = P["recent"]["plans"]["T15"]["after_confirmation"]["all"]["cost_model_mean"] or 0.0
    be_op, be_mod = _be(15.0, OP_COST), _be(15.0, c26)
    a15 = {k: P[k]["plans"]["T15"] for k in PARTS}
    at_means = ", ".join(f"{_u(a15[k]['at_trigger_no_confirmation']['all']['net_model'])}" for k in PARTS)
    cf_means = ", ".join(f"{_u(a15[k]['after_confirmation']['all']['net_model'])}" for k in PARTS)
    n_oos = po["trades"]
    d1 = a15["development"]["after_confirmation_one_bar_later"]["all"]
    ns = [a15[k]["after_confirmation"]["all"]["trades"] for k in PARTS]
    cap = {k: sum(t["cost"] > 0.15 * STOP + 1e-9 for t in a15[k]["after_confirmation"]["trades"]) for k in PARTS}
    capf = {k: P[k]["funnel"]["capped"] for k in PARTS}
    import pandas as pd
    months = (pd.Timestamp(P["recent"]["window"][1]) - pd.Timestamp(P["recent"]["scored_from"])).days / 30.44
    pace = capf["recent"]["confirmed"] / months if months > 0 else float("nan")
    L += ["**NOT STATISTICALLY VALIDATED under either rule. No accuracy claim is made.**", "",
          ("**Live rule since amendment B24-CONFIRM-FWD-A1 (2026-11-10): the confirming close must be $15-$20 beyond the "
           "trigger price; beyond $20 the setup is EXPIRED.** The cap was the operator's decision, made before any figure "
           "below was computed; neither rule is chosen by these figures, and both are reported."), "",
          (f"Capped, out of sample pooled: {pc['tp']} of {pc['trades']} trades reached +$15 before -$13 ({_p(pc['tp_rate'])}, 95% "
           f"{_ci(pc['tp_rate_ci95'], True)}); net {_u(pc['net_model'])} $/oz at the model cost (95% {_ci(pc['net_model_ci95'])}); "
           f"entered one 15m bar later {pc1['tp']} of {pc1['trades']}, {_u(pc1['net_model'])} $/oz. The cap removed "
           + ", ".join(f"{capf[k]['expired_overshoot']} of {P[k]['funnel']['confirmed']}" for k in PARTS)
           + " confirmations (2020-22, 2023-24, 2026) as overshoots."), "",
          (f"Pace (B24's stream is these engine signals): 2026 gave {capf['recent']['confirmed']} capped confirmations in "
           f"{months:.1f} scored months (about {pace:.1f} a month; {P['recent']['funnel']['confirmed']} under the original rule). "
           f"At that pace B24's first look (30 decided results) comes about {30 / pace / 12:.1f} years after it starts and the "
           f"last (100) about {100 / pace / 12:.1f} years after, so the registered 2029-12-31 deadline (unchanged by the "
           "amendment) is likely to end the test before the last look. A slow test, not a weaker standard: fewer alerts "
           "is the operator's stated priority."), "",
          "Original rule (no cap), out of sample (2023-24 validation and 2026 pooled), the",
          (f"confirmed plan reached +$15 before -$13 in {po['tp']} of {po['trades']} trades ({_p(po['tp_rate'])}, 95% "
          f"{_ci(po['tp_rate_ci95'], True)}); break-even is {_p(be_op, 1)} at your $0.26 cost and about {_p(be_mod, 1)} at the"),
          (f"model cost. The interval includes break-even. Net {_u(po['net_model'])} $/oz per trade at the model cost (95% "
          f"{_ci(po['net_model_ci95'])}): the interval includes zero."),
          (f"Entered one 15m bar later (what the site can actually deliver), the same trades gave {po1['tp']} of {po1['trades']} "
          f"({_p(po1['tp_rate'])}) and {_u(po1['net_model'])} $/oz (95% {_ci(po1['net_model_ci95'])})."),
          (f"Entered at the trigger with no confirmation: {pt['tp']} of {pt['trades']} ({_p(pt['tp_rate'])}), {_u(pt['net_model'])} "
          f"$/oz (95% {_ci(pt['net_model_ci95'])})."),
          "",
          (f"Entering at the trigger without a confirmation had a negative mean after costs in every period ({at_means}); the "
           f"confirmed plan had a positive mean in every period ({cf_means}), but no interval excludes zero, only {n_oos} "
           "trades are out of sample, and in 2020-22 the result did not survive a one-bar entry delay "
           f"({d1['tp']} of {d1['trades']} targets, {_u(d1['net_model'])} $/oz). The site therefore keeps the headline"),
          "\"NO TRADE — INSUFFICIENT CONFIRMATION\", and the registered B24 forward test decides it on new data.",
          ""]
    L += ["## Funnel (setups, confirmations, failed confirmations)", "",
          ("| Period | Window scored | Setups | Confirmed, original rule (95% CI) | Confirmed, capped / overshoot EXPIRED | Invalidated: price -$13 / opposite structure | Expired (window) | "
          "BUY confirmed / setups | SELL confirmed / setups | Mean move from the trigger at the confirming close ($) | Median 15m bars to confirm |"),
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for k in PARTS:
        f = P[k]["funnel"]
        b, se = f["by_direction"]["BUY"], f["by_direction"]["SELL"]
        L.append(f"| {P[k]['label']} | {P[k]['scored_from'][:10]} → {P[k]['window'][1][:10]} | {f['setups']} | {f['confirmed']} "
                 f"({_p(f['confirmed_share'])}, {_ci(f['confirmed_share_ci95'], True)}) | {f['capped']['confirmed']} / "
                 f"{f['capped']['expired_overshoot']} | {f['invalidated_price']} / "
                 f"{f['invalidated_structure']} | {f['expired']} | {b['confirmed']} / {b['setups']} | {se['confirmed']} / {se['setups']} | "
                 f"{_u(f.get('confirmation_move_mean'))} | {f.get('bars_to_confirmation_median') or '—'} |")
    L += ["", "A failed confirmation is NO TRADE: nothing is entered, nothing is lost. The at-trigger rows below show what those",
          "setups would have cost if they had been traded without the confirmation.", ""]
    for T in ("T15", "T20"):
        L += [f"## Plan results: +${T[1:]} before -$13", ""]
        for k in PARTS:
            L += [f"**{P[k]['label']}**", "", HDR]
            for nm, label in PLAN_NAME.items():
                L.append(_row(label, P[k]["plans"][T][nm]["all"]))
            L.append("")
        L += ["**Out of sample pooled (2023-24 validation + 2026)**", "",
              "| Plan | Trades | TP | Target first (95% CI) | Net $/oz (95% CI) | Net at $0.26 | Net at 2x cost | PF | Max DD (R) | Longest losing run |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for nm, a in res["pooled_out_of_sample"][T].items():
            L.append(f"| {PLAN_NAME[nm]} | {a['trades']} | {a['tp']} | {_p(a['tp_rate'])} ({_ci(a['tp_rate_ci95'], True)}) | "
                     f"{_u(a['net_model'])} ({_ci(a['net_model_ci95'])}) | {_u(a['net_operator_cost'])} | {_u(a['net_stress_2x_cost'])} | "
                     f"{_pf(a['profit_factor'])} | {a['max_drawdown_r']:.1f} | "
                     f"{a['longest_losing_streak']} |")
        L += ["", (f"Break-even target-first rate for +${T[1:]} before -$13: {_p(_be(float(T[1:]), OP_COST), 1)} at $0.26; "
              f"{_p(_be(float(T[1:]), c26), 1)} at ${c26:.2f} (the 2026 model cost)."), ""]
    L += ["## Splits (after the confirmation, +$15 before -$13; descriptive: no split was registered as a test)", "",
          "| Period | Split | Trades | TP | Target first | Net $/oz |", "|---|---|---|---|---|---|"]
    for k in PARTS:
        blk = P[k]["plans"]["T15"]["after_confirmation"]
        items = [("BUY", blk["BUY"]), ("SELL", blk["SELL"])] + [(f"timeframe {t}", v) for t, v in blk["by_timeframe"].items()] \
            + [(f"year {y}", v) for y, v in blk["by_year"].items()] + [("near a dated US release", blk["news_window"]),
                                                                    ("away from releases", blk["outside_news"])]
        for nm, a in items:
            if a["trades"]:
                L.append(f"| {P[k]['label']} | {nm} | {a['trades']} | {a['tp']} | {_p(a['tp_rate'])} | {_u(a['net_model'])} |")
    L += ["", "News coverage: " + "; ".join(f"{P[k]['label']}: {P[k]['news_releases_in_period']} dated release(s) "
                                           f"({P[k]['news_split']})" for k in PARTS) + ". Dated releases exist for 2020-22",
          "(B8: CPI, NFP, FOMC) and from 2026-10-28 (the live calendar); 2023-24 and most of 2026 cannot be split by news.", ""]
    L += ["## Costs and units", "",
          "Distances are B19's: $15 / $13 / $20 at a $4,000 gold price, scaled by s = trigger price / 4000 in every period",
          (f"(s averaged {P['development']['scale_s']['mean']:.2f} in 2020-22, {P['validation']['scale_s']['mean']:.2f} in 2023-24 and "
          f"{P['recent']['scale_s']['mean']:.2f} in 2026). The model cost (spread by session + 2 x $0.20 slippage + $0.07 commission) is put in"),
          "the same units (cost / s). B19's own figure subtracted the cost unscaled, which under-weights it when gold was far below",
          "$4,000; its figure is kept as `net_b19` in the JSON for reproduction. Correcting it lowers the 2020-22 expectancy by",
          (f"about ${P['development']['plans']['T15']['after_confirmation']['all']['net_b19'] - P['development']['plans']['T15']['after_confirmation']['all']['net_model']:.2f} per oz "
          f"and 2023-24 by about ${P['validation']['plans']['T15']['after_confirmation']['all']['net_b19'] - P['validation']['plans']['T15']['after_confirmation']['all']['net_model']:.2f}; "
          "2026 (s near 1) is unchanged in substance."),
          (f"B19's EXECUTE cost cap (cost <= 0.15 x D / s) has the same mix: in consistent units it would be cost / s <= "
           f"{0.15 * STOP:.2f}, which {cap['development']} of {ns[0]} confirmed 2020-22 trades and {cap['validation']} of {ns[1]} "
           f"2023-24 trades would fail ({cap['recent']} of {ns[2]} in 2026). They are kept: re-scoring with a cap corrected after "
           "seeing the results would be a new configuration chosen on these data."),
          "Prices are the research history's mid quotes; no broker bid / ask is in the data. A BUY fills at the ask and exits",
          "at the bid: the spread is inside the model cost, and the 2x stress column doubles it.", ""]
    L += ["## Limitations", "",
          (f"- Small samples: {ns[0]}, {ns[1]} and {ns[2]} confirmed trades. Intervals are wide; one trade moves a rate by "
           f"{100 / max(ns):.0f}-{100 / min(ns):.0f} points."),
          "- The 2020-22 period is in sample: B19 was designed on it. Only 2023-24 and 2026 are out of sample.",
          "- Fixed rule, no re-fit: a walk-forward re-optimisation does not apply (nothing is optimised). The periods are scored",
          "  in time order with the same rule, and the per-year rows show the sequence.",
          "- The entry is the confirming 15m close; the site shows a confirmation 3-66 minutes after that close (B25). The",
          "  one-bar-later row is the closer estimate of what a person can fill.",
          (f"- The live panel uses $15 / $13 / $20 unscaled (s = 1). In 2026 the research scaled them by s = "
           f"{P['recent']['scale_s']['mean']:.2f} on average ({P['recent']['scale_s']['min']:.2f}-{P['recent']['scale_s']['max']:.2f}), "
           "so the tested distances were that much wider than the ones the panel shows."),
          "- No broker prices: the operator's MT5 feed is not connected. Spread and slippage are modelled, not measured.",
          "- The engine signals come from the frozen engine replayed on history (B19); live signals can differ when the feed",
          "  revises a bar (the panel flags it).",
          "",
          "## Reproduce", "",
          "```sh", ("python research/tools/cf_validation.py --rd <research-data checkout> --out research/results/cf_validation.json "
          "--md research/CF_VALIDATION.md"), "```", "",
          "15m data hashes: " + "; ".join(f"{k} `{P[k]['data_hash_15m']}`" for k in PARTS) + ".", ""]
    return "\n".join(L)


def log_trials(res: dict, path: str, only: str | None = None) -> int:
    """One record per period x plan x target in the append-only trial log (research/trials.jsonl), as B19 logged its runs."""
    n = 0
    for part, v in res["parts"].items():
        for T, blk in v["plans"].items():
            for nm, b in blk.items():
                if only and only not in nm:
                    continue
                a = b["all"]
                H.log_trial(path, {"phase": "CF-VALIDATION", "partition": part, "id": f"CF ENG X15F0 E1 S13 {T} {nm}",
                                   "note": ("re-analysis of B19's rule with the cost in the move's units; the one-bar-later "
                                            "entry is a sensitivity, not a candidate rule; nothing selected"),
                                   "trades": a["trades"], "tp_first": a["tp_rate"], "net_usd_per_oz": a["net_model"],
                                   "net_b19": a["net_b19"], "profit_factor": a["profit_factor"],
                                   "data_hash_15m": v["data_hash_15m"]})
                n += 1
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd")
    ap.add_argument("--out", default=os.path.join("research", "results", "cf_validation.json"))
    ap.add_argument("--md", help="also write the Markdown write-up here")
    ap.add_argument("--from-json", action="store_true", help="only regenerate --md from an existing --out")
    ap.add_argument("--log", help="append one record per period / plan / target to this trial log (research/trials.jsonl)")
    ap.add_argument("--log-only", help="log only the plans whose name contains this (e.g. capped: the others are logged)")
    a = ap.parse_args(argv)
    if not a.from_json and not a.rd:
        ap.error("--rd is required unless --from-json")
    if a.from_json:
        with open(a.out) as fh:
            res = json.load(fh)
        if a.md:
            with open(a.md, "w") as fh:
                fh.write(markdown(res))
            print(f"written {a.md}")
        if a.log:
            print(f"logged {log_trials(res, a.log, a.log_only)} trial records to {a.log}")
        return 0
    res = {"rule": "quantum/confirm_panel.py = research/registrations/B19.json ENG X15F0 E1 S13 (T15 / T20)",
           "tool": "research/tools/cf_validation.py",
           "units": "$ per oz at a $4,000 price (distances and costs both scaled by s = P0 / 4000); net_b19 = B19's own figure "
                    "(cost unscaled); r = net / 13", "parts": {}}
    for part in PARTS:
        res["parts"][part] = run_part(a.rd, part)
    res["pooled_out_of_sample"] = {T: {nm: pooled(res["parts"]["validation"]["plans"][T][nm]["trades"]
                                                  + res["parts"]["recent"]["plans"][T][nm]["trades"])
                                       for nm in res["parts"]["recent"]["plans"][T]}
                                   for T in res["parts"]["recent"]["plans"]}
    with open(a.out, "w") as fh:
        json.dump(res, fh, indent=1, default=lambda x: None if isinstance(x, float) and math.isnan(x) else str(x), allow_nan=True)
    print(f"written {a.out}")
    if a.md:
        with open(a.md, "w") as fh:
            fh.write(markdown(res))
        print(f"written {a.md}")
    if a.log:
        print(f"logged {log_trials(res, a.log, a.log_only)} trial records to {a.log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
