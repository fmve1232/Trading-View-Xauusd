"""Generate research/G6_EXPOSURE_RESULTS.md from the G6-EXPOSURE result files and their independent checks. Every number
in the document is read from those files; nothing is typed in by hand.

  python audit/tools/g6_doc.py [--root <repo>] [--check]
Reads the files in FILES (both families' results, forward evidence, checks, mutation, provenance) and writes OUT.
--check exits 1 if the document on disk differs from what the files give.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, ROOT)
# the registered arm / timeframe sets (tested against the registration)
from quantum.research.g6_exposure import FAMILIES

NAMES = {"P0_none": "P0 every trade", "P1_one_open": "P1 one open (the operator's manual rule)",
         "P2_one_open_three_per_day": "P2 one open + 3 a day (B11 hypothesis)", "P3_three_open": "P3 three open",
         "P4_one_open_per_direction": "P4 one per direction"}


def f(x, nd=4):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return f"{x:+.{nd}f}" if nd else f"{x:,.0f}"
    return f"{x:,}" if isinstance(x, int) else str(x)


def pct(x):
    return "n/a" if x is None else f"{100 * x:.1f}%"


def exposure(lines, r, label):
    c, cor, b = r["concurrency"], r["correlated"], r["book"]
    op = c["open_positions"]
    lines += [f"| Measure ({label}) | Value |", "|---|---|",
              f"| positions (closed trades) | {f(r['positions'])} |",
              f"| 5-minute samples | {f(op['samples'])} |",
              f"| share of time with any position open | {pct(c['share_of_time_any_open'])} |",
              f"| mean open positions | {op['mean']:.3f} |",
              f"| share of time with 2+ / 3+ open | {pct(op['share_2_plus'])} / {pct(op['share_3_plus'])} |",
              f"| maximum open at once (exact) | {c['exact']['max_open']} (first at {c['exact']['first_at_utc']}) |",
              f"| largest simultaneous sum of stop distances | ${c['exact']['max_sum_stop_usd_per_oz']:,.2f} per ounce |",
              f"| maximum open long / short | {c['long_open']['max']} / {c['short_open']['max']} |",
              (f"| net long minus short: mean, min, max | {c['net_long_minus_short']['mean']:+.3f}, "
              f"{c['net_long_minus_short']['min']}, {c['net_long_minus_short']['max']} |"),
              f"| share of time 2+ open in the same direction | {pct(c['share_of_time_two_plus_same_direction'])} |",
              f"| share of time long and short open together | {pct(c['share_of_time_long_and_short_together'])} |",
              (f"| combined stop at the worst instant | {c['combined_stop_r']['max_r_at_risk']} R; MODELLED "
              f"${c['combined_stop_r']['max_usd_if_every_position_risked_650']:,.0f} if every position were taken at $650 |"),
              (f"| entries with a same-direction entry on another timeframe within 60 min | "
              f"{pct(cor['share_with_same_direction_entry_on_another_tf_within_60m'])} |"),
              (f"| entries with a same-direction entry on the other arm, same timeframe, within 60 min | "
              f"{pct(cor['share_with_same_direction_entry_on_other_arm_same_tf_within_60m'])} |"),
              (f"| same-direction pairs open together | {f(cor['same_direction_pairs_open_together'])}; both lost "
              f"{pct(cor.get('both_lost_share'))} vs {pct(cor.get('independence_expectation'))} if independent "
              f"(phi {cor.get('phi_loss_loss')}) |"),
              f"| net R, mean net R per trade, win rate | {b['net_r']:+,.2f}, {b['mean_net_r']:+.4f}, {pct(b['win_rate'])} |",
              f"| maximum drawdown (exit order) | {b['max_dd_r']:,.2f} R |",
              f"| longest losing streak | {b['longest_losing_streak']} trades |",
              (f"| potential daily loss (entries x 1 R): mean, p95, max | {b['potential_daily_loss_r']['mean']:.2f}, "
              f"{b['potential_daily_loss_r']['p95']:.0f}, {b['potential_daily_loss_r']['max']} R on "
              f"{b['potential_daily_loss_r']['max_day']} (MODELLED ${b['potential_daily_loss_r']['max_usd_if_every_position_risked_650']:,.0f} at $650 each) |"),
              (f"| realised daily R: mean, 5th percentile, worst | {b['realised_daily_r']['mean']:+.3f}, "
              f"{b['realised_daily_r']['p05']:+.3f}, {b['realised_daily_r']['worst']:+.3f} on {b['realised_daily_r']['worst_day']} |"),
              f"| worst single trade, gap exits | {b['worst_trade_r']:+.4f} R, {b['gap_exits']} |", ""]
    lines += ["By timeframe and arm: " + ", ".join(f"{k} {v:,}" for k, v in r["by_tf_arm"].items()) + ".", ""]
    lines += ["| Session (at entry) | Entries | Net R | Mean net R | Mean already open at entry |", "|---|---|---|---|---|"]
    lines += [f"| {s} | {v['entries']:,} | {v['net_r']:+,.2f} | {v['mean_net_r']:+.4f} | {v['mean_already_open_at_entry']:.2f} |"
              for s, v in r["sessions"].items()]
    lines.append("")


SIMS = 4000          # quantum/research/g6_exposure.compare: bootstrap resamples per test
MEASURES = (("mean_net_r_per_trade", "mean net R per trade"), ("net_r_per_day", "net R per day"))
EV = "docs/final_audit/evidence"
FILES = {"dev": "research/G6_EXPOSURE_RESULTS.json", "dev_a1": "research/G6_EXPOSURE_RESULTS_A1.json",
         "fwd": f"{EV}/g6_forward_exposure_2026-11-28.json", "fwd_a1": f"{EV}/g6_forward_exposure_a1_2026-11-28.json",
         "dchk": f"{EV}/g6_dev_check_2026-11-28.json", "dchk_a1": f"{EV}/g6_dev_check_a1_2026-11-28.json",
         "fchk": f"{EV}/g6_forward_check_2026-11-28.json", "fchk_a1": f"{EV}/g6_forward_check_a1_2026-11-28.json",
         "mut": f"{EV}/g6_mutation_2026-11-28.json", "prov": f"{EV}/g6_forward_provenance_2026-11-28.json"}
OUT = "research/G6_EXPOSURE_RESULTS.md"


def pfmt(p):
    return f"< {1 / SIMS:.5f}" if p == 0 else f"{p:.4f}"


def bh(ps: list[float]) -> list[float]:
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i], reverse=True)
    adj, run = [0.0] * m, 1.0
    for k, i in enumerate(order):
        run = min(run, ps[i] * m / (m - k))
        adj[i] = min(run, 1.0)
    return adj


def family(L, dev, fwd, dchk, fchk, title):
    # result files written before A1 (the primary run, commit ec45a1f8f) carry no family / arm keys: the sets are the
    # module's registered ones
    tfs, arms = FAMILIES[dev.get("family", "primary")]
    L += [f"## {title}", "", f"Arms: {', '.join(dev.get('arms') or arms)}. Timeframes: {', '.join(dev.get('timeframes') or tfs)}.", "",
          f"### Development partition ({dev['window_utc'][0]} to {dev['window_utc'][1]})", "",
          (f"Data hashes {dev['data_hashes']}; seed {dev['seed']}. {dev['common_window_note']}. Skipped: "
           f"{dev['skipped']['before_common_start']:,} fills before the common start and "
           f"{dev['skipped']['open_at_end']} still open at the end. Engine seconds per timeframe: {dev['engine_seconds']}."), ""]
    zero = [f"{tf}_{arm}" for tf in (dev.get("timeframes") or tfs) for arm in (dev.get("arms") or arms)
            if f"{tf}_{arm}" not in dev["by_tf_arm"]]
    if zero:
        L += [f"No development trades: {', '.join(zero)}."]
        tf_all = dev.get("timeframes") or tfs
        blind = [a for a in ("control", "h5") if all(f"{tf}_{a}" in zero for tf in tf_all)]
        if blind:
            L += [(f"{' and '.join(blind)}: NOT EVALUABLE on the development partition. Control's entry gate needs "
                   "`macro_bull` / `macro_bear` (`quantum/engine.py`, the control branch of the entry gates) and H5's "
                   "checklist needs the same macro check; both are votes on external series (COMEX gold futures, DXY or "
                   "EUR/USD, yields, S&P 500, silver, TIPS; `quantum/features.py`) that the research market does not "
                   "carry (`quantum/research/b10.py` `make_market`), so they can never pass there. Their forward "
                   "ledgers are measured below (register GA-32).")]
        L.append("")
    exposure(L, dev, "development, P0 = every trade")
    L += ["#### The five policies (development)", "",
          ("| Policy | Kept | Blocked | Mean net R | Net R | Max DD R | Longest losing streak | Max entries in a day | "
           "Worst realised day R | Max open | Blocked: mean net R | Blocked: TP1 first |"),
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in dev["policies"].items():
        b, bl = v["book"], v["blocked"]
        L.append(f"| {NAMES[k]} | {b['trades']:,} | {bl.get('count', 0):,} | {b['mean_net_r']:+.4f} | {b['net_r']:+,.2f} | "
                 f"{b['max_dd_r']:,.2f} | {b['longest_losing_streak']} | {b['potential_daily_loss_r']['max']} | "
                 f"{b['realised_daily_r']['worst']:+.3f} | {v['concurrency']['max']} | "
                 f"{f(bl.get('mean_net_r'))} | {pct(bl.get('tp1_first_share'))} |")
    L += ["", "#### Registered comparisons (paired day-block bootstrap, 10 tests, Holm and BH within the family)", "",
          "| A vs B | Measure | A - B | 95% interval | p | Holm | BH |", "|---|---|---|---|---|---|---|"]
    for c in dev["comparisons"]:
        for m, lab in MEASURES:
            x = c[m]
            L.append(f"| {c['a'].split('_')[0]} vs {c['b'].split('_')[0]} | {lab} | {x['diff']:+.4f} | "
                     f"[{x['ci95'][0]:+.4f}, {x['ci95'][1]:+.4f}] | {pfmt(x['p_two_sided'])} | {pfmt(x['p_holm'])} | "
                     f"{pfmt(x['p_bh'])} |")
    n_sig = sum(1 for c in dev["comparisons"] for m, _ in MEASURES if c[m]["p_holm"] < 0.05)
    neg = [NAMES[k] for k, v in dev["policies"].items() if v["book"]["mean_net_r"] < 0]
    L += ["", (f"{n_sig} of 10 tests have Holm-adjusted p < 0.05 (a p shown as < {1 / SIMS:.5f} means no one of the "
               f"{SIMS:,} resamples crossed zero). Policies with a negative mean net R per trade: {len(neg)} of 5"
               + (f" ({', '.join(neg)})" if neg else "") + ". A policy only chooses which of the engine's own trades are "
               "kept. When every policy's mean is below zero, a difference between policies is a difference in how much "
               "of a negative-expectancy stream is taken. It is not an edge, and it validates no policy."), "",
          "### Forward ledgers (descriptive only; no policy replayed or compared)", "",
          (f"Ledgers: `holdout/<tf>_<arm>.json`, records under freeze key `{fwd['freeze_key']}`; window "
           f"{fwd['window_utc'][0]} to {fwd['window_utc'][1]}. Records per ledger: "
           + ", ".join(f"{k} {v['current_freeze']}" for k, v in fwd["ledgers"].items() if v["current_freeze"])
           + (". No ledger file: " + ", ".join(k for k, v in fwd["ledgers"].items() if v.get("records") is None)
              if any(v.get("records") is None for v in fwd["ledgers"].values()) else "") + "."), ""]
    exposure(L, fwd, "forward, every recorded trade")
    L += [(f"Independent checks: forward **{fchk['verdict']}** ({sum(r['pass'] for r in fchk['rows'])} of "
           f"{len(fchk['rows'])} figures equal), development invariants **{dchk['verdict']}** "
           f"({sum(r['pass'] for r in dchk['rows'])} of {len(dchk['rows'])})."), ""]


def build(d: dict) -> str:
    dev, dev1, fwd, fwd1, mut, prov = d["dev"], d["dev_a1"], d["fwd"], d["fwd_a1"], d["mut"], d["prov"]
    L = ["# G6-EXPOSURE: aggregate exposure and five exposure policies (shadow research)", "",
         ("Generated by `audit/tools/g6_doc.py` from the result, evidence and check files listed at the end; "
          "`--check` confirms this file matches them. Registration: `research/registrations/G6-EXPOSURE.json` (committed "
          "before any code or run) and its amendment A1 (committed before any A1 code or run, and before any primary "
          "result was read). Code: `quantum/research/g6_exposure.py`. Tests: `tests/test_research_g6_exposure.py`."), "",
         ("**Decision: NONE.** Research in shadow mode. No limit is enforced anywhere, and nothing is proposed for production "
          "or the alerts. The operator's own rule (one MT5 trade open at a time) belongs to the operator, not to this study. "
          "The 1-open / 3-max proposal remains a hypothesis whatever these figures show."), "",
         "## What the numbers are", "",
         ("- **Positions.** Closed trades of the frozen engine's arms. A position is open from its fill (the signal bar's "
          "close) to the close of its exit bar: exact for a FLIP, the latest possible instant for an intrabar stop or "
          "target. Concurrency is therefore never understated."),
         ("- **R.** Each position carries 1 R, its own stop distance. Net R is after the engine's cost of record, which is "
          "MODELLED: G2 broker costs are unverified."),
         ("- **The $650 figures** are MODELLED. They assume every position were taken at the operator's $650 planned loss. "
          "The operator takes one trade at a time, so they show what the alert stream would put at risk, not what anyone "
          "risked."),
         ("- **Policies** are replayed first-order. A blocked trade never opens and the arms are not re-simulated. Ties go "
          "to the higher timeframe, then to the registered arm order."), "",
         ("- **Two families.** PRIMARY is the registration as written (treatment and H4, 5m-1h). A1 is the amendment "
          "(every live arm, 5m-4h). Each family has its own 10 tests."), ""]
    family(L, dev, fwd, d["dchk"], d["fchk"], "PRIMARY family (as registered)")
    family(L, dev1, fwd1, d["dchk_a1"], d["fchk_a1"], "A1 family (all live forward-test arms, 5m-4h)")
    oos = fwd1.get("out_of_scope") or {}
    L += ["### Not modelled as positions (A1 'out_of_scope_listed')", "", f"{oos.get('reason', 'n/a')}.", "",
          "| Notification stream | Send attempts |", "|---|---|"]
    L += [f"| {k} | {v:,} |" for k, v in (oos.get("notification_attempts_by_stream") or {}).items()]
    L += ["", "| Research-forward file | Records |", "|---|---|"]
    L += [f"| {k} | {v if isinstance(v, int) else ', '.join(f'{a} {b:,}' for a, b in v.items())} |"
          for k, v in (oos.get("research_forward_records") or {}).items()]
    ps = [c[m]["p_two_sided"] for r in (dev, dev1) for c in r["comparisons"] for m, _ in MEASURES]
    adj = bh(ps)
    L += ["", "## BH across both families (20 tests; registered in A1)", "",
          (f"{sum(1 for x in adj if x < 0.05)} of {len(adj)} tests have a BH-adjusted p < 0.05 across both families; "
           f"the largest adjusted p is {pfmt(round(max(adj), 4))}."), "",
          "## Independent checks and tests", "",
          ("- Forward (`audit/tools/g6_check.py forward`): brute-force recomputation from the raw ledger JSON and the raw "
           "store CSV timestamps, with its own JSON / CSV parsing and its own market-hours rule."),
          ("- Development (`audit/tools/g6_check.py dev`): every policy limit holds, kept + blocked = all, the corrections "
           "are no smaller than the raw p, and the trials log matches the results."),
          (f"- Tests: hand-worked cases, a seeded random equivalence against brute force for the replay, the concurrency count "
           f"and the exact maximum. Mutation test (`{FILES['mut']}`): {sum(m['killed'] for m in mut['mutants'])} of "
           f"{len(mut['mutants'])} hand mutations of the rules killed."), "",
          "## Provenance", "",
          (f"- Forward ledgers: forward-ledger branch at `{prov['forward_ledger_branch']['commit']}` "
           f"({prov['forward_ledger_branch']['commit_utc']}); 5-minute bars: market-data branch at "
           f"`{prov['market_data_branch']['commit']}` ({prov['market_data_branch']['commit_utc']}); file hashes in "
           f"`{FILES['prov']}`. Both were read with `git show` / `git archive`; nothing was written to either."),
          "- Files read by this generator: " + ", ".join(f"`{v}`" for v in FILES.values()) + ".", "",
          "## Limits", "",
          ("- The replay is first-order. In reality, an arm whose trade was blocked could have taken a different later "
           "trade; that is not simulated."),
          "- Ending each position at its exit-bar close overstates overlap by up to one bar on intrabar exits.",
          ("- Prices are Twelve Data spot mid. There is no bid / ask, so spreads, costs and slippage are the engine's "
           "MODELLED cost of record."),
          ("- Development engine runs have no external series (no futures, dollar, yields, equities, silver, COT, "
           "volume): the engine's macro terms are inactive there, so the development trades are the frozen engine "
           "without its macro inputs, not a replay of what production would have done."),
          (f"- The forward window has entries on {fwd1['book']['days_with_entries']} New York trading days. Its figures "
           "describe that window only.")]
    return "\n".join(L) + "\n"


def _load(path: str) -> dict:
    with open(path) as fh:
        return json.load(fh)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    doc = build({k: _load(os.path.join(a.root, v)) for k, v in FILES.items()})
    out = os.path.join(a.root, OUT)
    if a.check:
        with open(out) as fh:
            same = fh.read() == doc
        print("document matches the files" if same else "document DIFFERS from the files")
        return 0 if same else 1
    with open(out, "w") as fh:
        fh.write(doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
