"""Weekend-reopening verification of the production data and the G4 records (operator mandate 28 Nov 2026, Part 2).
Read-only: it reads a market-data snapshot and the G4 record files and writes nothing but its report.

  python audit/tools/reopen_check.py --store <market-data snapshot> [--diag <trade_diag dir>] [--diag2 <second copy>]
                                     [--reopen <ISO UTC>] [--json out]

  --diag    the G4 records to examine (default <store>/trade_diag); --diag2 a second copy (e.g. forward-ledger/trade_diag)
            compared line by line with the first
  --reopen  the reopening bar's open time; default: the last session start after a break of 24 h or more

Checks (PASS / FAIL, or PENDING when the snapshot has no post-reopening records yet, or UNAVAILABLE for a reference
the store does not hold):
  R1  first valid bar        the first bar of the engine-cleaned 5-minute series after the weekend opens at 18:00 New York
  R2  stale quote excluded   the feed's raw first print, the carried Friday quote, is replaced as the engine does
                             (sources.repair_reopen: the open becomes the bar's close); reported with Friday's last close
  R2b reopen-bar extreme     SUSPECT when the engine's first bar reaches beyond Friday's close by more than
                             STALE_TOL_USD on the side opposite to the gap (a print below Friday's close on a gap up):
                             the repair replaces the stale open but keeps the bar's high and low. Not verifiable without
                             a tick source; the ledger exits and G4 records it decides are listed
  R3  shut window excluded   raw feed bars printed while gold was shut are dropped (sources.trading_week_only)
  R4  ordering               engine-cleaned bars strictly increasing, on the 5-minute grid, no duplicate times
  R5  reference price        COMEX GC=F 5-minute bars (Yahoo, a different vendor), premium removed by the median
                             futures-minus-spot close over the first two hours: the median absolute difference of
                             closes over the first hour must not exceed the 95th percentile of the same difference over
                             the last complete session before the break (its own premium). Rule fixed on 28 Nov 2026,
                             after a dry run on the 22 Nov reopening showed a fixed $3 was not a defensible bound, and
                             before any 29 Nov data existed. Futures, not spot: a consistency check, not a verified price
  R6  forming bars           no record read a bar that had not closed when it was written: every window ends at or
                             before logged_utc
  R7  conventions            fill = signal bar open + its timeframe; next_open.entry = the engine-cleaned open of the
                             first bar at or after the fill; first_bar_gap_min consistent
  R8  independent recompute  audit/tools/trade_diag_check.py agrees on every record (targets, stop first, MAE / MFE)
  R9  duplicates / missing / modified   no key twice, no conflicting copies, every trade final by the last run
                             logged, no ledger trade changed since its record was written
Verdicts: PASS, FAIL, SUSPECT (a data anomaly that cannot be verified here), PENDING, UNAVAILABLE. Overall: FAIL if
any FAIL, else SUSPECT if any SUSPECT, else PENDING when there is no post-reopening record, else PASS.
Exit 0 on PASS, 1 on FAIL, 3 on SUSPECT, 2 on PENDING.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trade_diag_check as CHK

from quantum import trade_diag as TD
from quantum.data import sources, store

NY = ZoneInfo("America/New_York")
STALE_TOL_USD = 1.0
TF_SEC = TD.TF_SEC


def _utc(t: int) -> str:
    return datetime.fromtimestamp(int(t), timezone.utc).isoformat()


def _epochs(df: pd.DataFrame) -> np.ndarray:
    ix = pd.DatetimeIndex(df.index)
    ix = ix.tz_localize("UTC") if ix.tz is None else ix.tz_convert("UTC")
    return ix.as_unit("s").asi8.astype(np.int64)


def _verdict(ok: bool | None) -> str:
    return "PENDING" if ok is None else ("PASS" if ok else "FAIL")


def bars(store_dir: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = sources.drop_offgrid(store.load(store_dir, "XAU/USD_5m"))
    clean = sources.repair_reopen(sources.trading_week_only(raw), 300)
    return raw, clean


def find_reopen(t: np.ndarray) -> int | None:
    gaps = np.flatnonzero(np.diff(t) >= 24 * 3600)
    return int(t[gaps[-1] + 1]) if len(gaps) else None


def price_checks(store_dir: str, reopen: int | None) -> dict:
    raw, clean = bars(store_dir)
    tr, tc = _epochs(raw), _epochs(clean)
    out: dict = {}
    reopen = find_reopen(tc) if reopen is None else reopen
    if reopen is None or reopen not in set(tc.tolist()):
        return {"reopen": None, "R1": {"verdict": "PENDING", "note": "no post-weekend bar in this snapshot"}}
    k = int(np.searchsorted(tc, reopen))
    ny = datetime.fromtimestamp(reopen, NY)
    out["reopen"] = _utc(reopen)
    out["R1"] = {"verdict": _verdict(ny.weekday() == 6 and (ny.hour, ny.minute) == (18, 0)),
                 "first_bar_open_utc": _utc(reopen), "new_york": ny.isoformat(),
                 "bars_after_reopen": int(len(tc) - k)}
    fri_t, fri_c = int(tc[k - 1]), float(clean["close"].iloc[k - 1])
    j = int(np.searchsorted(tr, reopen))
    raw_o = float(raw["open"].iloc[j]) if j < len(tr) and tr[j] == reopen else None
    shut = (tr > fri_t) & (tr < reopen)
    carried = float(raw["close"][shut].iloc[-1]) if shut.any() else None
    c_o, c_c = float(clean["open"].iloc[k]), float(clean["close"].iloc[k])
    stale = raw_o is not None and abs(raw_o - (carried if carried is not None else fri_c)) <= STALE_TOL_USD
    out["R2"] = {"verdict": _verdict(c_o == c_c and (raw_o is None or not stale or c_o != raw_o)),
                 "friday_last_bar_utc": _utc(fri_t), "friday_last_close": round(fri_c, 3),
                 "last_shut_window_print": None if carried is None else round(carried, 3),
                 "raw_first_print_open": None if raw_o is None else round(raw_o, 3),
                 "raw_first_print_is_the_carried_quote": stale,
                 "engine_first_bar": {"open": round(c_o, 3), "high": round(float(clean["high"].iloc[k]), 3),
                                      "low": round(float(clean["low"].iloc[k]), 3), "close": round(c_c, 3)},
                 "first_valid_price": round(c_c, 3),
                 "first_valid_price_definition": "the first bar's close (its open is the carried quote; sources.repair_reopen)",
                 "gap_from_friday_close": round(c_c - fri_c, 3)}
    hi, lo = float(clean["high"].iloc[k]), float(clean["low"].iloc[k])
    up = c_c >= fri_c
    extreme = lo if up else hi
    suspect = (lo < fri_c - STALE_TOL_USD) if up else (hi > fri_c + STALE_TOL_USD)
    nxt = float(clean["open"].iloc[k + 1]) if k + 1 < len(tc) else c_o
    out["R2b"] = {"verdict": "SUSPECT" if suspect else "PASS", "gap": "up" if up else "down",
                  "extreme_opposite_to_the_gap": round(extreme, 3), "friday_last_close": round(fri_c, 3),
                  "note": ("the first bar's " + ("low" if up else "high") + " lies beyond Friday's close against the gap: "
                           "probably not a trade; unverifiable without a tick source") if suspect else "",
                  "_k": k, "_replacement": min(c_o, nxt) if up else max(c_o, nxt), "_side": "l" if up else "h"}
    out["R3"] = {"verdict": _verdict(bool(not sources.gold_shut(clean.index).any())),
                 "raw_bars_in_shut_window": int(shut.sum()), "engine_bars_in_shut_window": int(sources.gold_shut(clean.index).sum())}
    out["R4"] = {"verdict": _verdict(bool(np.all(np.diff(tc) > 0) and np.all(tc % 300 == 0))),
                 "bars": len(tc), "duplicates": int(len(tc) - len(np.unique(tc))), "off_grid": int(np.sum(tc % 300 != 0))}
    gc = store.load(store_dir, "GC=F_5m")
    if gc is None or not len(gc):
        out["R5"] = {"verdict": "UNAVAILABLE", "note": "no GC=F 5-minute bars in the store"}
    else:
        gc = sources.drop_offgrid(gc)
        tg = _epochs(gc)
        both = np.intersect1d(tg[(tg >= reopen) & (tg < reopen + 7200)], tc)
        if not len(both):
            out["R5"] = {"verdict": "UNAVAILABLE", "note": "no GC=F bar in the first two hours"}
        else:
            gi = pd.Series(gc["close"].to_numpy(float), index=tg)
            xi = pd.Series(clean["close"].to_numpy(float), index=tc)
            go = pd.Series(gc["open"].to_numpy(float), index=tg)
            xo = pd.Series(clean["open"].to_numpy(float), index=tc)
            prem = float(np.median(gi[both] - xi[both]))
            hour = both[both < reopen + 3600]
            dev = np.abs((gi[hour] - prem) - xi[hour]) if len(hour) else np.array([])
            first = int(both[0])
            sess = np.intersect1d(tg[(tg > fri_t - 23 * 3600) & (tg <= fri_t)], tc)      # the last session before the break
            tol = None
            if len(sess) >= 20:
                d0 = gi[sess] - xi[sess]
                tol = float(np.quantile(np.abs(d0 - np.median(d0)), 0.95))
            ok = None if (not len(dev) or tol is None) else float(np.median(dev)) <= tol
            out["R5"] = {"verdict": "UNAVAILABLE" if ok is None else ("PASS" if ok else "FAIL"),
                         "reference": "COMEX GC=F futures (Yahoo), premium removed; not a spot price",
                         "first_common_bar_utc": _utc(first), "premium_usd": round(prem, 3),
                         "first_common_open_spot_vs_futures_minus_premium": [round(float(xo[first]), 3), round(float(go[first] - prem), 3)],
                         "first_hour_bars": len(hour),
                         "first_hour_median_abs_close_diff_usd": None if not len(dev) else round(float(np.median(dev)), 3),
                         "first_hour_max_abs_close_diff_usd": None if not len(dev) else round(float(np.max(dev)), 3),
                         "tolerance_usd": None if tol is None else round(tol, 3),
                         "tolerance_rule": "p95 of |futures - premium - spot| over the last session before the break",
                         "baseline_bars": len(sess)}
    out["_clean_t"], out["_clean_o"] = tc, clean["open"].to_numpy(float)
    # ledger exits at the first bar (non-gap exits at a price beyond Friday's close against the gap)
    if out["R2b"]["verdict"] == "SUSPECT":
        hits = []
        for tf, arm, t in TD.ledger_trades(store_dir):
            sec = TF_SEC[tf]
            tx = TD.ts(t["exit_time"])
            if tx <= reopen < tx + sec and t["exit_reason"] in ("SL", "BE", "TP2") and t.get("exit") is not None:
                px = float(t["exit"])
                if (px < fri_c - STALE_TOL_USD) if up else (px > fri_c + STALE_TOL_USD):
                    hits.append({"ledger": f"{tf}_{arm}", "dir": t["dir"], "entry_time": t["entry_time"], "exit": px,
                                 "exit_reason": t["exit_reason"], "r": t["r"]})
        out["R2b"]["ledger_exits_decided_inside_the_suspect_range"] = hits
    return out


def record_checks(store_dir: str, diag: str, diag2: str | None, reopen: int | None, t_open: np.ndarray, o_open: np.ndarray) -> dict:
    rows = TD.read_dir(diag)
    keys = [r["key"] for r in rows]
    dup = sorted({k for k in keys if keys.count(k) > 1})
    post = [r for r in rows if reopen is not None and TD.ts(r["logged_utc"].replace("Z", "+00:00")) >= reopen]
    out: dict = {"records": len(rows), "post_reopen_records": len(post),
                 "runs_logged": sorted({r["logged_utc"] for r in rows})[-6:]}
    # R6 forming bars
    late = []
    for r in rows:
        fill = TD.ts(r["fill_utc"])
        end = fill + 3600 * max(r["race_window"]["hours"], r["next_open"]["race_window"]["hours"], r["in_trade"]["hours"])
        if end > TD.ts(r["logged_utc"].replace("Z", "+00:00")) + 1:
            late.append({"key": r["key"], "window_end": _utc(end), "logged_utc": r["logged_utc"]})
    out["R6"] = {"verdict": _verdict(not late) if rows else "PENDING", "records_reading_unclosed_bars": len(late), "examples": late[:5]}
    # R7 conventions
    bad = []
    for r in rows:
        fill = TD.ts(r["entry_time"]) + TF_SEC[r["tf"]]
        j0 = int(np.searchsorted(t_open, fill))
        exp_o = float(o_open[j0]) if j0 < len(t_open) else None
        gap = (int(t_open[j0]) - fill) / 60.0 if j0 < len(t_open) else None
        if TD.ts(r["fill_utc"]) != fill or exp_o is None or abs(exp_o - r["next_open"]["entry"]) > 1.5e-3 \
                or abs(gap - r["next_open"]["first_bar_gap_min"]) > 0.05:
            bad.append({"key": r["key"], "fill_utc": r["fill_utc"], "expected_fill_utc": _utc(fill),
                        "next_open": r["next_open"]["entry"], "expected_next_open": None if exp_o is None else round(exp_o, 3)})
    out["R7"] = {"verdict": _verdict(not bad) if rows else "PENDING", "discrepancies": len(bad), "examples": bad[:5],
                 "post_reopen_fills_at_a_session_close": sum(1 for r in post if r["next_open"]["first_bar_gap_min"] > 0)}
    # R8 independent recomputation, all records and the post-reopen ones
    full = CHK.check(store_dir, diag)
    sub = {"records": 0, "agree": 0, "disagree": 0, "ledger_changed": 0}
    if post:
        tmp = tempfile.mkdtemp()
        try:
            with open(os.path.join(tmp, "post.jsonl"), "w") as f:
                f.writelines(TD.canonical(r) + "\n" for r in post)
            sub = CHK.check(store_dir, tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    out["R8"] = {"verdict": _verdict(full["disagree"] == 0 and full["ledger_changed"] == 0) if rows else "PENDING",
                 "all": {k: full[k] for k in ("records", "agree", "disagree", "ledger_changed", "trade_not_in_ledger")},
                 "post_reopen": {k: sub.get(k) for k in ("records", "agree", "disagree", "ledger_changed")},
                 "details": full["details"][:10]}
    # R9 duplicates, conflicting copies, missing, modified
    conflicts = []
    if diag2:
        other = {r["key"]: TD.canonical(r) for r in TD.read_dir(diag2)}
        conflicts = [r["key"] for r in rows if r["key"] in other and other[r["key"]] != TD.canonical(r)]
    last_run = max((TD.ts(r["logged_utc"].replace("Z", "+00:00")) for r in rows), default=None)
    expected, missing = 0, []
    if last_run is not None:
        B = TD.bars5(store_dir, last_run)
        have = set(keys)
        for tf, arm, t in TD.ledger_trades(store_dir):
            rec_t = t.get("recorded_utc")
            if rec_t and TD.ts(rec_t) > last_run:
                continue                                    # recorded after the last logging run: not due yet
            if TD.diagnose(tf, arm, t, B, []) is not None:
                expected += 1
                k = f"{tf}|{arm}|{t['entry_time']}|{t['dir']}"
                if k not in have:
                    missing.append(k)
    out["R9"] = {"verdict": _verdict(not dup and not conflicts and not missing and full["ledger_changed"] == 0) if rows else "PENDING",
                 "expected_records_by_last_run": expected, "actual_records": len(set(keys)), "duplicates": len(dup),
                 "conflicting_copies": len(conflicts), "missing": len(missing), "missing_examples": missing[:10],
                 "modified_ledger_trades": full["ledger_changed"], "second_copy": diag2}
    return out


def suspect_impact(store_dir: str, diag: str, reopen: int, replacement: float, side: str) -> dict:
    """The G4 records whose result changes when the first bar's suspect extreme is replaced by the nearer of its open
    and the next bar's open (a sensitivity, not a correction: the records stay as written)."""
    rows = {r["key"]: r for r in TD.read_dir(diag)}
    if not rows:
        return {"records_spanning_the_bar": 0, "changed": []}
    last = max(TD.ts(r["logged_utc"].replace("Z", "+00:00")) for r in rows.values())
    B = TD.bars5(store_dir, last)
    k = int(np.searchsorted(B["t"], reopen))
    B2 = {kk: v.copy() for kk, v in B.items()}
    B2[side][k] = replacement
    span, changed = 0, []
    for tf, arm, t in TD.ledger_trades(store_dir):
        key = f"{tf}|{arm}|{t['entry_time']}|{t['dir']}"
        if key not in rows:
            continue
        a = TD.diagnose(tf, arm, t, B, [])
        if a is None:
            continue
        fill = TD.ts(a["fill_utc"])
        end = fill + 3600 * max(a["race_window"]["hours"], a["next_open"]["race_window"]["hours"], a["in_trade"]["hours"])
        if not fill <= reopen < end:
            continue
        span += 1
        b = TD.diagnose(tf, arm, t, B2, [])
        diff = [f for f in ("race", "stop", "race_window", "next_open", "in_trade") if b is None or a[f] != b[f]]
        if diff:
            changed.append({"key": key, "fields": diff})
    return {"records_spanning_the_bar": span, "changed": changed}


def run(store_dir: str, diag: str | None = None, diag2: str | None = None, reopen: str | None = None) -> dict:
    t_re = None if reopen is None else TD.ts(reopen)
    p = price_checks(store_dir, t_re)
    t_open, o_open = p.pop("_clean_t", np.array([], np.int64)), p.pop("_clean_o", np.array([]))
    t_re = TD.ts(p["reopen"]) if p.get("reopen") else None
    r = record_checks(store_dir, diag or os.path.join(store_dir, TD.DIR), diag2, t_re, t_open, o_open)
    if p.get("R2b", {}).get("verdict") == "SUSPECT":
        p["R2b"]["g4_records_changed_without_the_extreme"] = suspect_impact(store_dir, diag or os.path.join(store_dir, TD.DIR),
                                                                             t_re, p["R2b"]["_replacement"], p["R2b"]["_side"])
    for kk in ("_k", "_replacement", "_side"):
        p.get("R2b", {}).pop(kk, None)
    checks = {k: v for k, v in {**p, **r}.items() if k.startswith("R")}
    states = [v["verdict"] for v in checks.values()]
    if "FAIL" in states:
        verdict = "FAIL"
    elif "SUSPECT" in states:
        verdict = "SUSPECT"
    elif r["post_reopen_records"] == 0 or "PENDING" in states:
        verdict = "PENDING"
    else:
        verdict = "PASS"
    return {"verdict": verdict, "reopen": p.get("reopen"), "records": r["records"],
            "post_reopen_records": r["post_reopen_records"], "runs_logged": r["runs_logged"], "checks": checks,
            "pending_rule": "PENDING until the snapshot holds G4 records written after the reopening bar"}


BEGIN, END = "<!-- REOPEN:BEGIN (generated by audit/tools/reopen_check.py --doc; do not edit) -->", "<!-- REOPEN:END -->"


def markdown(out: dict, title: str) -> str:
    c = out["checks"]
    head = (f"Reopening bar {out['reopen']}; G4 records {out['records']}, written after it "
            f"{out['post_reopen_records']}. **Overall: {out['verdict']}**")
    rows = [f"#### {title}", "", head, "", "| Check | Verdict | Measured |", "|---|---|---|"]
    r2, r2b, r5, r8, r9 = c.get("R2", {}), c.get("R2b", {}), c.get("R5", {}), c.get("R8", {}), c.get("R9", {})
    meas = {
        "R1": f"first bar {c.get('R1', {}).get('first_bar_open_utc')} ({c.get('R1', {}).get('new_york')})",
        "R2": (f"Friday close {r2.get('friday_last_close')}; raw first print {r2.get('raw_first_print_open')} "
               f"(carried quote: {r2.get('raw_first_print_is_the_carried_quote')}); engine first bar open = close = "
               f"{r2.get('first_valid_price')}; gap {r2.get('gap_from_friday_close')}"),
        "R2b": (f"{r2b.get('gap')} gap; extreme against it {r2b.get('extreme_opposite_to_the_gap')}; ledger exits inside the "
                f"suspect range: {len(r2b.get('ledger_exits_decided_inside_the_suspect_range', []))}; G4 records changed "
                f"without it: {len(r2b.get('g4_records_changed_without_the_extreme', {}).get('changed', []))} of "
                f"{r2b.get('g4_records_changed_without_the_extreme', {}).get('records_spanning_the_bar', 0)}"),
        "R3": f"raw bars while shut {c.get('R3', {}).get('raw_bars_in_shut_window')}, after cleaning {c.get('R3', {}).get('engine_bars_in_shut_window')}",
        "R4": f"duplicates {c.get('R4', {}).get('duplicates')}, off grid {c.get('R4', {}).get('off_grid')}",
        "R5": (f"first-hour median abs(futures - premium - spot) {r5.get('first_hour_median_abs_close_diff_usd')} vs tolerance "
               f"{r5.get('tolerance_usd')} (premium {r5.get('premium_usd')}; first common bar {r5.get('first_common_bar_utc')})"),
        "R6": f"records reading an unclosed bar {c.get('R6', {}).get('records_reading_unclosed_bars')}",
        "R7": f"convention discrepancies {c.get('R7', {}).get('discrepancies')}; fills at a session close {c.get('R7', {}).get('post_reopen_fills_at_a_session_close')}",
        "R8": (f"agree {r8.get('all', {}).get('agree')} of {r8.get('all', {}).get('records')}, disagree "
               f"{r8.get('all', {}).get('disagree')}, ledger changed {r8.get('all', {}).get('ledger_changed')}"),
        "R9": (f"expected {r9.get('expected_records_by_last_run')}, actual {r9.get('actual_records')}, duplicates "
               f"{r9.get('duplicates')}, missing {r9.get('missing')}, conflicting copies {r9.get('conflicting_copies')}"),
    }
    for k, v in c.items():
        rows.append(f"| {k} | {v['verdict']} | {meas.get(k, '')} |")
    for e in r2b.get("ledger_exits_decided_inside_the_suspect_range", []):
        rows.append("")
        rows.append(f"Ledger exit inside the suspect range: `{e['ledger']}` {e['dir']} entered {e['entry_time']}, "
                    f"{e['exit_reason']} at {e['exit']} (r {e['r']}).")
    return "\n".join(rows)


def write_doc(evidence: list[tuple[str, str]], doc: str, check: bool = False) -> int:
    parts = []
    for path, title in evidence:
        with open(path) as f:
            parts.append(markdown(json.load(f), title))
    with open(doc) as f:
        text = f.read()
    i, j = text.index(BEGIN), text.index(END) + len(END)
    new = text[:i] + BEGIN + "\n\n" + "\n\n".join(parts) + "\n\n" + END + text[j:]
    if check:
        return 0 if new == text else 1
    with open(doc, "w") as f:
        f.write(new)
    return 0


DOC_EVIDENCE = [("docs/final_audit/evidence/reopen_dryrun_2026-11-22.json",
                 "DRY RUN: 22 Nov 2026 reopening (records from the 27 Nov evidence run, not production)")]


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--doc":
        rc = write_doc([(os.path.join(ROOT, p), t) for p, t in DOC_EVIDENCE],
                       os.path.join(ROOT, "docs", "final_audit", "REOPEN_VERIFICATION.md"), "--check" in argv)
        print(("reopening document matches the evidence" if rc == 0 else "reopening document differs from the evidence")
              if "--check" in argv else "reopening document written from the evidence")
        return rc
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--store", required=True)
    ap.add_argument("--diag")
    ap.add_argument("--diag2")
    ap.add_argument("--reopen")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    out = run(a.store, a.diag, a.diag2, a.reopen)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(out, f, indent=1, default=str)
    print(f"reopen {out['reopen']}  records {out['records']}  post-reopen {out['post_reopen_records']}")
    for k, v in out["checks"].items():
        print(f"{v['verdict']:<11} {k}")
    print(out["verdict"])
    return {"PASS": 0, "FAIL": 1, "SUSPECT": 3}.get(out["verdict"], 2)


if __name__ == "__main__":
    sys.exit(main())
