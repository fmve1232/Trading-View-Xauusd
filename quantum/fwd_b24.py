"""B24-CONFIRM-FWD recorder (research/registrations/B24-CONFIRM-FWD.json; registered before this code was written).

The live forward test of: engine signal + a completed $15 confirmation close. Records only. Nothing here reaches the
phone, the plans, the engine or the other tests; it is not an ENGINE_SOURCES file. It starts with the first site run
that carries it: only engine signals whose bar closes after that run are recorded (no backfill).

Per signal (BUY and SELL alike), each decision is written once, when it is made, and never edited:
  trigger      the signal bar's close and time; folded into an earlier one of the same idea (REPEAT rule) if any
  stage B      confirm_panel's state machine on the 15m bars, each bar examined once: CONFIRMED / INVALIDATED / EXPIRED
  entries      A = the confirming 15m close; B = the first price the site could act on: the newest price of the first
               run that has the confirming bar (5m forming bar at that run's download), with its time and the latency
  costs        the engine's round-trip cost model at that run (dashboard.checks.cost_pts) and the operator's $0.26;
               slippage = (B - A) x direction ($, positive = worse)
  exits        for A and B, targets +$15 / +$20, stops S13 / S10 / SATR (3 x ATR14) / SSTR (the extreme since the
               trigger + 0.2 ATR; outside $5-40 = not applicable): on the site's 5m bars from the first bar after the
               entry (fallback: 15m bars, flagged); gap at the open; a bar touching both counts as the stop; 48 hours
  excursions   MFE / MAE to each exit, and over a fixed 24 hours from each entry
Finished rows are appended to <store>/research_forward/B24-CONFIRM-FWD.json (the workflow copies it to forward-ledger).
Checks of H-ALL / H-BUY / H-SELL happen only at 30, 50, 75, 100 decided results (Wilson z = 2.24 above 47.4% and a
positive mean net after $0.26); a weekly report is appended after each Friday New York close. Between looks every
figure is PRELIMINARY.
"""
from __future__ import annotations

import json
import math
import os
from bisect import bisect_left

import numpy as np

from . import confirm_panel as cp
from . import notify

ID, FILE = "B24-CONFIRM-FWD", "B24-CONFIRM-FWD.json"
OP_COST = 0.26
BREAK_EVEN = (13.0 + OP_COST) / 28.0                      # 47.36%
Z = 2.24
LOOKS = (30, 50, 75, 100)
DEADLINE = "2029-12-31"
TARGETS = {"T15": 15.0, "T20": 20.0}
STOPS = ("S13", "S10", "SATR", "SSTR")
HOLD5, FIX24_5 = 576, 288                                  # 48 h and 24 h of 5m bars
SATR_MULT, SSTR_BUF, STOP_MIN, STOP_MAX = 3.0, 0.2, 5.0, 40.0


def on() -> bool:
    return os.environ.get("FWD_B24", "1").strip() != "0"


def wilson_lo(k: int, n: int, z: float = Z) -> float:
    p = k / n
    den = 1 + z * z / n
    return (p + z * z / (2 * n)) / den - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den


def wins_needed() -> dict:
    return {n: next(k for k in range(n + 1) if wilson_lo(k, n) > BREAK_EVEN) for n in LOOKS}


def _path5(payloads: dict, p15: dict) -> tuple[dict | None, bool]:
    p5 = cp._ok(payloads.get("5m"))
    if p5 is not None and (p5.get("meta") or {}).get("price_source") == (p15.get("meta") or {}).get("price_source"):
        return cp.path(p5), True
    return None, False


def _stops(P15: dict, j0: int, k: int, d: int, entry: float) -> dict:
    atr = float(P15["atr"][k]) if np.isfinite(P15["atr"][k]) else math.nan
    out = {"S13": 13.0, "S10": 10.0, "SATR": SATR_MULT * atr if np.isfinite(atr) else math.nan}
    seg_l, seg_h = P15["l"][j0 - 1:k + 1], P15["h"][j0 - 1:k + 1]       # from the trigger bar to the confirmation
    lv = (np.nanmin(seg_l) - SSTR_BUF * atr) if d > 0 else (np.nanmax(seg_h) + SSTR_BUF * atr)
    out["SSTR"] = float((entry - lv) * d) if np.isfinite(lv) else math.nan
    return {k_: (v if np.isfinite(v) and STOP_MIN <= v <= STOP_MAX else None) for k_, v in out.items()}


def _fixed24(P: dict, start: int, entry: float, d: int) -> dict | None:
    if start + FIX24_5 > len(P["t"]):
        return None
    h, lo_ = P["h"][start:start + FIX24_5], P["l"][start:start + FIX24_5]
    return {"mfe": float(np.nanmax((h - entry) if d > 0 else (entry - lo_))),
            "mae": float(np.nanmax((entry - lo_) if d > 0 else (h - entry)))}


GAP_WHY = ("bars it still needed left the chart before any run examined them (the site did not run for days); no decision "
           "is made on bars never examined")


def _gap(next_open: int, t: np.ndarray, sec: int) -> bool:
    """True when the next bar this row must examine opens before the chart's first bar: the bars in between were never
    seen by any run, so scanning on from the chart's start would skip them."""
    return len(t) > 0 and -(-int(next_open) // sec) * sec < int(t[0])


def advance(row: dict, P15: dict, P5: dict | None, payloads: dict, t_now: int) -> None:
    """Move one row forward on bars no earlier run examined; decisions are frozen once written. A row whose next bar is
    no longer on the chart is closed as DATA GAP (not decided; never counted in a look)."""
    t = P15["t"]
    j0 = bisect_left(t, row["t_close"])
    d, p0 = row["dir"], row["p0"]
    if row["stage"] == "PENDING":
        if j0 >= len(t):
            return
        if _gap(row["t_close"] if row.get("scan_t") is None else row["scan_t"], t, 900):
            row.update(stage="DATA GAP", why=GAP_WHY, t_stage=t_now, t_stage_seen=t_now)
            return
        js = j0 if row.get("scan_t") is None else bisect_left(t, row["scan_t"])
        c = cp.confirm_one(P15, j0, p0, d, 15.0, start=js)
        row["scan_t"] = t[-1] + 900
        if c["status"] == "PENDING":
            return
        row["stage"] = c["status"]
        row["t_stage"] = t[c["at"]] + 900                                  # the close of the deciding bar
        row["t_stage_seen"] = t_now
        if c["status"] != "CONFIRMED":
            row["why"] = c["why"]
            return
        k = c["k"]
        pn = notify.price_now(payloads, "15m") or {}
        a_px, b_px = float(P15["c"][k]), pn.get("px")
        ck = ((payloads.get("15m") or {}).get("dashboard") or {}).get("checks") or {}
        row.update(k_conf_t=t[k], t_conf=t[k] + 900, A={"px": a_px, "t": t[k] + 900},
                   B={"px": None if b_px is None else float(b_px), "t": pn.get("t"), "live_quote": bool(pn.get("live"))},
                   latency_s=(pn.get("t") - (t[k] + 900)) if pn.get("t") is not None else None,
                   slippage=((b_px - a_px) * d) if b_px is not None else None, cost_model=ck.get("cost_pts"), op_cost=OP_COST,
                   atr15=float(P15["atr"][k]) if np.isfinite(P15["atr"][k]) else None,
                   stops={"A": _stops(P15, j0, k, d, a_px), "B": _stops(P15, j0, k, d, b_px) if b_px is not None else None},
                   path="5m" if P5 is not None else "15m", res={})
    if row["stage"] != "CONFIRMED":
        return
    P = P5 if (P5 is not None and row.get("path") == "5m") else P15
    hold = HOLD5 if P is P5 else cp.HOLD
    for ent in ("A", "B"):
        e = row.get(ent) or {}
        if e.get("px") is None:
            continue
        j = bisect_left(P["t"], int(e["t"]))                                # the first bar opening at or after the entry
        if j >= len(P["t"]):
            continue
        sec = 300 if P is P5 else 900
        for tk, T in TARGETS.items():
            for sk in STOPS:
                dist = ((row.get("stops") or {}).get(ent) or {}).get(sk)
                key = f"{ent} {tk} {sk}"
                cur = row["res"].get(key) or {}
                if dist is None or cur.get("out") not in (None, "OPEN"):
                    if dist is None:
                        row["res"][key] = {"out": "N/A"}
                    continue
                if _gap(cur["scan_t"] if cur.get("scan_t") else int(e["t"]), P["t"], sec):
                    row["res"][key] = {"out": "DATA GAP", "why": GAP_WHY}
                    continue
                st0 = bisect_left(P["t"], cur["scan_t"]) if cur.get("scan_t") else j
                x = cp.exit_one(P, j - 1, d, T, 1.0, entry=e["px"], start=st0, mfe0=cur.get("mfe", 0.0), mae0=cur.get("mae", 0.0),
                                stop=dist, hold=hold)
                net = None if x["usd"] is None else x["usd"] - OP_COST
                row["res"][key] = {"out": x["out"], "usd": x["usd"], "net_op": net, "mfe": x["mfe"], "mae": x["mae"],
                                   "t_exit": P["t"][x["bar"]] + (300 if P is P5 else 900) if x["out"] != "OPEN" else None,
                                   "scan_t": P["t"][-1] + (300 if P is P5 else 900) if x["out"] == "OPEN" else None}
        if P is P5 and e.get("fixed24") is None:
            e["fixed24"] = {"data_gap": True} if _gap(int(e["t"]), P["t"], sec) else _fixed24(P, j, e["px"], d)


def finished(row: dict) -> bool:
    if row["stage"] in ("INVALIDATED", "EXPIRED", "FOLDED", "DATA GAP"):
        return True
    if row["stage"] != "CONFIRMED":
        return False
    outs = [v.get("out") for v in row.get("res", {}).values()]
    fixed = all((row.get(e) or {}).get("fixed24") is not None or row.get("path") != "5m" or (row.get(e) or {}).get("px") is None
                for e in ("A", "B"))
    return bool(outs) and all(o not in (None, "OPEN") for o in outs) and fixed


def primary(row: dict) -> tuple[str, float] | None:
    x = (row.get("res") or {}).get("B T15 S13") or {}
    if x.get("out") in ("TP", "SL", "AMBIGUOUS", "TIMEOUT"):
        return x["out"], x.get("net_op")
    return None


def checks(rows: list[dict], checks_done: list[dict], t_now: int) -> list[dict]:
    """New looks for H-ALL / H-BUY / H-SELL, in the order the results resolved; a decided hypothesis stops."""
    out = []
    dec = sorted((r for r in rows if primary(r)), key=lambda r: r["res"]["B T15 S13"]["t_exit"])
    need = wins_needed()
    for h, sel in (("H-ALL", lambda r: True), ("H-BUY", lambda r: r["dir"] > 0), ("H-SELL", lambda r: r["dir"] < 0)):
        mine = [r for r in dec if sel(r)]
        done = {c["look"] for c in checks_done if c["hypothesis"] == h}
        if any(c["hypothesis"] == h and c["result"] in ("PROVEN", "NOT PROVEN") for c in checks_done):
            continue
        for L in LOOKS:
            if len(mine) < L or L in done:
                continue
            k = sum(primary(r)[0] == "TP" for r in mine[:L])
            mean_net = float(np.mean([primary(r)[1] for r in mine[:L]]))
            proven = k >= need[L] and mean_net > 0
            res = "PROVEN" if proven else ("NOT PROVEN" if L == LOOKS[-1] else "CONTINUE")
            out.append({"hypothesis": h, "look": L, "wins": k, "needed": need[L], "rate": k / L, "wilson_lo_z224": wilson_lo(k, L),
                        "mean_net_after_026": mean_net, "result": res, "t": t_now})
            if res != "CONTINUE":
                break
    if notify.trading_day(t_now) > DEADLINE and not any(c["hypothesis"] == "H-ALL" and c["result"] != "CONTINUE"
                                                        for c in checks_done + out):
        out.append({"hypothesis": "H-ALL", "look": "deadline", "result": "NOT PROVEN", "t": t_now})
    allc = checks_done + out
    ended = any(c["hypothesis"] == "H-ALL" and (c["look"] in (LOOKS[-1], "deadline")) for c in allc)
    if ended:                                                            # H-BUY / H-SELL end with H-ALL (registered)
        for h in ("H-BUY", "H-SELL"):
            if not any(c["hypothesis"] == h and c["result"] in ("PROVEN", "NOT PROVEN") for c in allc):
                out.append({"hypothesis": h, "look": "test ended", "result": "NOT PROVEN", "t": t_now})
    return out


def weekly(rows: list[dict], week: str, started: int, status: str) -> dict:
    """The registered weekly report over every row recorded since the start (cumulative) and in the week."""
    def block(rs: list[dict]) -> dict:
        conf = [r for r in rs if r["stage"] == "CONFIRMED"]
        out = {"triggers": len(rs), "buy": sum(r["dir"] > 0 for r in rs), "sell": sum(r["dir"] < 0 for r in rs),
               "confirmed": len(conf), "invalidated": sum(r["stage"] == "INVALIDATED" for r in rs),
               "expired": sum(r["stage"] == "EXPIRED" for r in rs), "folded": sum(r["stage"] == "FOLDED" for r in rs),
               "data_gap": sum(r["stage"] == "DATA GAP" for r in rs)}
        for key in ("B T15 S13", "B T20 S13", "A T15 S13"):
            dec = [r["res"][key] for r in conf if (r.get("res") or {}).get(key, {}).get("out") in ("TP", "SL", "AMBIGUOUS", "TIMEOUT")]
            n, k = len(dec), sum(x["out"] == "TP" for x in dec)
            nets = np.array([x["net_op"] for x in dec if x.get("net_op") is not None], float)
            eq = np.concatenate([[0.0], np.cumsum(nets / 13.0)]) if len(nets) else np.zeros(1)
            lo, hi = notify._wilson(k, n) if n else (None, None)
            out[key] = {"n": n, "tp_first": k / n if n else None, "ci95": [lo, hi], "stop_first": sum(x["out"] in ("SL", "AMBIGUOUS") for x in dec) / n if n else None,
                        "mfe_mean": float(np.mean([x["mfe"] for x in dec])) if n else None, "mae_mean": float(np.mean([x["mae"] for x in dec])) if n else None,
                        "expectancy_after_026": float(nets.mean()) if len(nets) else None,
                        "profit_factor": float(nets[nets > 0].sum() / -nets[nets < 0].sum()) if (nets < 0).any() else None,
                        "max_drawdown_r": float((np.maximum.accumulate(eq) - eq).max())}
        lat = [r["latency_s"] for r in conf if r.get("latency_s") is not None]
        sl = [r["slippage"] for r in conf if r.get("slippage") is not None]
        cm = [r["cost_model"] for r in conf if r.get("cost_model") is not None]
        out.update(latency_s_mean=float(np.mean(lat)) if lat else None, slippage_mean=float(np.mean(sl)) if sl else None,
                   cost_model_mean=float(np.mean(cm)) if cm else None)
        return out
    wk = [r for r in rows if notify.trading_week(r["t_close"]) == week]
    label = {"PROVEN": "STATISTICALLY VALIDATED: PROVEN at a registered look", "NOT PROVEN": "DECIDED: NOT PROVEN"}.get(status, "PRELIMINARY")
    return {"week": week, "label": label, "status": status,
            "this_week": block(wk), "since_start": block(rows), "started_utc": started}


def run(payloads: dict, state: dict, t_now: int, store_dir: str | None = None) -> dict:
    p15 = cp._ok(payloads.get("15m"))
    st = state.setdefault("b24", {})
    if p15 is None:
        return {"id": ID, "status": "NO DATA", "started_utc": st.get("started")}
    P15 = cp.path(p15)
    P5, _ = _path5(payloads, p15)
    first = "started" not in st
    st.setdefault("started", t_now)
    rows, seen, last_bar = list(st.get("rows", [])), dict(st.get("seen", {})), dict(st.get("last_bar", {}))
    starts = {tf: int(p["chart"]["t"][0]) for tf in cp.ENG_TFS for p in [cp._ok(payloads.get(tf))] if p is not None}
    path = os.path.join(store_dir, "research_forward", FILE) if store_dir else None
    rec = {"registration": "research/registrations/B24-CONFIRM-FWD.json", "started_utc": st["started"], "rows": [],
           "checks": [], "weekly": []}
    if path and os.path.exists(path):
        with open(path) as f:
            rec = json.load(f)
    for x in (y for y in cp.scan(payloads) if y["kind"] == "ENG"):
        if x["key"] in seen:
            continue
        seen[x["key"]] = t_now
        if first or x["t_close"] <= st["started"]:
            continue                                                     # new data only: nothing from before the start
        st["seq"] = int(st.get("seq", 0)) + 1
        lb = last_bar.get(x["tf"])
        row = {**x, "id": st["seq"], "seen": t_now, "stage": "PENDING", "late": lb is not None and x["t"] <= lb}
        rp = cp.repeat_of(x, rows + rec["rows"][-60:])
        if rp is not None:
            row.update(stage="FOLDED", of_id=rp["id"])
        rows.append(row)
    keep, done = [], []
    for r in rows:
        if r["stage"] in ("PENDING", "CONFIRMED"):
            advance(r, P15, P5, payloads, t_now)
        (done if finished(r) else keep).append(r)
    have = {r["key"] for r in rec["rows"]}
    rec["rows"] += [notify.json_safe(r) for r in done if r["key"] not in have]
    new_checks = checks(rec["rows"], rec["checks"], t_now)
    rec["checks"] += new_checks
    week = notify.trading_week(t_now)
    status = next((c["result"] for c in reversed(rec["checks"]) if c["hypothesis"] == "H-ALL" and c["result"] != "CONTINUE"), "COLLECTING")
    if st.get("week") and st["week"] != week:                           # a trading week has ended: its report, once
        rec["weekly"].append(notify.json_safe(weekly(rec["rows"], st["week"], st["started"], status)))
    st["week"] = week
    st["rows"] = keep[-200:]
    st["seen"] = {k: v for k, v in seen.items() if cp._key_t(k)[1] >= starts.get(cp._key_t(k)[0], P15["t"][0])}
    st["last_bar"] = {**last_bar, **{tf: int(p["chart"]["t"][-1]) for tf in cp.ENG_TFS for p in [cp._ok(payloads.get(tf))] if p is not None}}
    if path:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"                                              # replaced whole: a crash cannot truncate it
        with open(tmp, "w") as f:
            json.dump(rec, f, indent=1)
        os.replace(tmp, path)
    dec = [r for r in rec["rows"] if primary(r)]
    return notify.json_safe({"id": ID, "status": status, "started_utc": st["started"], "open": len(keep), "recorded": len(rec["rows"]),
                             "decided": len(dec), "wins": sum(primary(r)[0] == "TP" for r in dec), "looks": list(LOOKS),
                             "wins_needed": wins_needed(), "break_even": BREAK_EVEN, "label": "PRELIMINARY" if status == "COLLECTING" else status,
                             "last_week": rec["weekly"][-1] if rec["weekly"] else None})
