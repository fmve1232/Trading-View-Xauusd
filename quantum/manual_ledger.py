"""Manual MT5 trade ledger (mandate 2026-11-28, Parts 9 and 12-17, 21): an append-only, hash-chained record of every
Quantum signal and of what the operator did with it on MT5, kept apart from the forward-test records.

Quantum cannot see the MT5 account. A signal is never counted as a trade: execution and closure enter only as the
operator's confirmation or a broker record, with evidence, and are never inferred from price (price reaching a stop or
target changes nothing here). Nothing in this module sends an order, sizes a lot, sends a notification or changes an
alert; it is not an engine source and nothing in production imports it.

Storage: one JSON object per line. Each line carries its sequence number and the SHA-256 of the previous line, so an
edit, a deletion, an insertion or a reordering breaks the chain (`verify`). Lines are only ever appended; a mistake is
fixed by a CORRECTION line naming the line it corrects and why. Five events are kept apart (Part 9): GENERATED, ACCEPTED,
EXECUTED, CLOSED and VERIFIED (the broker-checked result). Signal and slot states are the Part 13 words.

  python -m quantum.manual_ledger verify   --ledger L.jsonl
  python -m quantum.manual_ledger record   --ledger L.jsonl --kind EXECUTED --signal Q-0001 --source user --data '{...}'
  python -m quantum.manual_ledger import-c1 --ledger L.jsonl --index index.json [--now ISO]
  python -m quantum.manual_ledger expire   --ledger L.jsonl [--now ISO]
  python -m quantum.manual_ledger outcomes --ledger L.jsonl --bars <store>/XAU_USD_5m
  python -m quantum.manual_ledger export   --ledger L.jsonl --csv out.csv
  python -m quantum.manual_ledger stats    --ledger L.jsonl [--json out.json]
  python -m quantum.manual_ledger snapshot --ledger L.jsonl [--json out.json]
  python -m quantum.manual_ledger notify   --ledger L.jsonl --signal Q-0001 [--now ISO]
  python -m quantum.manual_ledger reconcile --ledger L.jsonl --mt5 history.csv
Standard library only, so the same file runs on the operator's own computer.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import io
import itertools
import json
import math
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

try:                                     # an exclusive lock while appending; Windows has no fcntl (one writer there)
    import fcntl
except ImportError:                      # pragma: no cover
    fcntl = None

PKT = ZoneInfo("Asia/Karachi")
GENESIS = "0" * 64
KINDS = ("GENERATED", "ACCEPTED", "EXECUTED", "CLOSED", "EXPIRED", "CANCELLED", "VERIFIED", "OUTCOME", "CORRECTION")
STATES = ("NO_OPEN_TRADE", "SIGNAL_GENERATED", "AWAITING_USER_CONFIRMATION", "TRADE_OPEN", "TRADE_CLOSED",
          "SIGNAL_EXPIRED", "SIGNAL_CANCELLED")
CANCEL_REASONS = ("USER_DECLINED", "INVALIDATED", "ENTRY_MISSED", "BLOCKED_OPEN_TRADE", "REJECTED", "OTHER")
OUTCOMES = ("TP1", "TP2", "TP3", "SL", "BE", "MANUAL", "OTHER")
CONFIRMERS = ("user", "mt5")             # the only sources that may confirm an execution or a closure
PLAN_REQUIRED = ("t_gen", "price_at_gen", "data_ts", "direction", "setup", "tf", "entry", "sl", "tp1", "tp2", "rr",
                 "spread", "commission_est", "slippage_est", "max_entry_dev", "confirmation", "invalidation",
                 "expiry_utc", "reason")
EXEC_REQUIRED = ("fill", "t_fill", "lot", "sl_actual", "evidence")
CLOSE_REQUIRED = ("exit_px", "t_exit", "outcome", "pl_gross", "commission", "swap", "evidence")
MIN_N = 30                               # below this a population is INSUFFICIENT EVIDENCE (as tools/forward_matched.py)
MOVES = (10.0, 15.0, 20.0)               # the operator's favourable moves, $ of price (Part 15)
HOLD_SEC = 48 * 3600                     # theoretical outcome window, as C1 follows a plan (confirm_entry.HOLD, 192 x 15m)
MATCH_SEC, MATCH_PX = 120, 0.5           # reconciliation: a broker deal within 2 min and $0.50 of a confirmed fill


class LedgerError(ValueError):
    """An append that would break a rule; nothing is written."""


def utc(t) -> datetime:
    """An ISO time or epoch seconds as an aware UTC datetime."""
    if isinstance(t, (int, float)):
        return datetime.fromtimestamp(float(t), timezone.utc)
    d = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def iso(t) -> str:
    return utc(t).strftime("%Y-%m-%dT%H:%M:%SZ")


def pkt(t) -> str:
    return utc(t).astimezone(PKT).strftime("%Y-%m-%d %H:%M PKT")


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(rec: dict) -> str:
    return hashlib.sha256(_canon({k: v for k, v in rec.items() if k != "hash"}).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- storage

def read(path: str) -> list[dict]:
    """Every line as written (no checks; see verify)."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def chain_problems(recs: list[dict]) -> list[str]:
    """Sequence, chain and hash of every line: an edit, deletion, insertion or reordering is reported here."""
    out, prev = [], GENESIS
    for i, r in enumerate(recs, 1):
        if r.get("seq") != i:
            out.append(f"line {i}: seq {r.get('seq')} (expected {i}): a line was removed, inserted or reordered")
        if r.get("prev") != prev:
            out.append(f"line {i}: prev does not match line {i - 1}'s hash: the chain is broken")
        if r.get("hash") != _digest(r):
            out.append(f"line {i}: hash does not match its content: the line was edited")
        if r.get("kind") not in KINDS:
            out.append(f"line {i}: unknown kind {r.get('kind')!r}")
        prev = r.get("hash")
    return out


# ---------------------------------------------------------------- the state machine

def _side(plan: dict) -> int:
    return 1 if plan.get("direction") == "BUY" else -1


def plan_gaps(p: dict) -> list[str]:
    """Why a plan cannot be actionable (Parts 12 and 21): missing fields, levels on the wrong side, a bad expiry."""
    miss = [k for k in PLAN_REQUIRED if p.get(k) in (None, "")]
    if miss:
        return ["missing: " + ", ".join(miss)]
    bad = []
    if p["direction"] not in ("BUY", "SELL"):
        bad.append("direction must be BUY or SELL")
    nums = ("price_at_gen", "entry", "sl", "tp1", "tp2", "rr", "spread", "commission_est", "slippage_est", "max_entry_dev")
    bad += [f"{k} is not a number" for k in nums if not _num(p[k])]
    if bad:
        return bad
    d = _side(p)
    levels = [p["sl"], p["entry"], p["tp1"], p["tp2"]] + ([p["tp3"]] if _num(p.get("tp3")) else [])
    if not all((b - a) * d > 0 for a, b in itertools.pairwise(levels[:4])) or (len(levels) == 5 and (levels[4] - levels[3]) * d < 0):
        bad.append("levels out of order for the direction (stop, entry, TP1, TP2[, TP3])")
    if min(p["spread"], p["commission_est"], p["slippage_est"]) < 0 or p["max_entry_dev"] <= 0:
        bad.append("costs must be >= 0 and the maximum entry deviation > 0")
    if utc(p["expiry_utc"]) <= utc(p["t_gen"]):
        bad.append("expiry must be after generation")
    return bad


def replay(recs: list[dict], strict: bool = False) -> dict:
    """Fold the lines into signals and the trading slot. strict=True raises on the first illegal line (append uses it
    for the line it is about to write); otherwise problems are collected (verify)."""
    sig, slot, problems, by_seq, sources = {}, None, [], {}, {}

    def bad(r, msg):
        if strict:
            raise LedgerError(msg)
        problems.append(f"seq {r.get('seq')}: {msg}")

    for r in recs:
        by_seq[r.get("seq")] = r
        k, sid, data, src = r.get("kind"), r.get("signal_id"), dict(r.get("data") or {}), r.get("source") or ""
        s = sig.get(sid)
        if k == "GENERATED":
            if sid in sig:
                bad(r, f"{sid} generated twice")
                continue
            if src and src not in CONFIRMERS and src in sources:
                bad(r, f"source {src} already recorded as {sources[src]} (duplicate import)")
                continue
            if data.get("actionable") and plan_gaps(data):
                bad(r, f"{sid} marked actionable with an incomplete plan: {'; '.join(plan_gaps(data))}")
                continue
            if not data.get("actionable") and not data.get("reason"):
                bad(r, f"{sid}: a non-actionable signal needs its reason (NO TRADE: Reason ...)")
                continue
            blocked = bool(data.get("actionable")) and slot is not None
            if blocked and data.get("blocked_by") != slot:
                bad(r, f"{sid} generated while {slot} is open but not marked blocked_by {slot}")
            if not blocked and data.get("blocked_by"):
                bad(r, f"{sid} marked blocked_by {data['blocked_by']} while no trade was open")
            sources[src] = sid
            sig[sid] = {"signal_id": sid, "plan": data, "seq": r["seq"], "t_rec": r.get("t"), "source": src,
                        "state": "SIGNAL_CANCELLED" if blocked else "AWAITING_USER_CONFIRMATION" if data.get("actionable") else "SIGNAL_GENERATED",
                        "blocked": blocked, "cancel_reason": "BLOCKED_OPEN_TRADE" if blocked else None, "accepted": False,
                        "execution": None, "closure": None, "verified": None, "outcome": None, "expired_at": None,
                        "events": [r["seq"]], "corrections": []}
            continue
        if k == "CORRECTION":
            tgt = by_seq.get(data.get("target_seq"))
            if not tgt or tgt is r or tgt.get("kind") not in ("GENERATED", "EXECUTED", "CLOSED", "VERIFIED", "OUTCOME"):
                bad(r, f"correction of seq {data.get('target_seq')}: no correctable line (GENERATED, EXECUTED, CLOSED, VERIFIED, OUTCOME)")
                continue
            if src != "user" or not data.get("reason") or "field" not in data or data["field"] in ("blocked_by", "actionable"):
                bad(r, "a correction needs source user, a reason, and a correctable field")
                continue
            if tgt["kind"] in ("EXECUTED", "CLOSED", "VERIFIED") and not data.get("evidence"):
                bad(r, "correcting an execution, closure or verification needs evidence")
                continue
            ts = sig.get(tgt.get("signal_id"))
            part = {"GENERATED": "plan", "EXECUTED": "execution", "CLOSED": "closure", "VERIFIED": "verified", "OUTCOME": "outcome"}[tgt["kind"]]
            if ts is None or ts.get(part) is None:
                bad(r, f"correction of seq {tgt['seq']}: that line was itself refused, so there is nothing to correct")
                continue
            old = ts[part].get(data["field"])
            ts[part] = {**ts[part], data["field"]: data.get("value")}
            ts["corrections"].append({"seq": r["seq"], "target_seq": tgt["seq"], "field": data["field"], "old": old,
                                      "new": data.get("value"), "reason": data["reason"]})
            ts["events"].append(r["seq"])
            continue
        if s is None:
            bad(r, f"{k} for unknown signal {sid}")
            continue
        st = s["state"]
        if k == "ACCEPTED":
            if src != "user" or st != "AWAITING_USER_CONFIRMATION" or s["accepted"]:
                bad(r, f"ACCEPTED needs source user and a signal awaiting confirmation ({sid} is {st})")
                continue
            s["accepted"] = True
        elif k == "EXECUTED":
            if src not in CONFIRMERS:
                bad(r, f"an execution is confirmed only by {CONFIRMERS}, not {src!r}: never inferred")
                continue
            if st != "AWAITING_USER_CONFIRMATION":
                bad(r, f"{sid} is {st}: only a signal awaiting confirmation can be executed")
                continue
            if slot is not None:
                bad(r, f"{slot} is still open: one trade at a time")
                continue
            miss = [f for f in EXEC_REQUIRED if data.get(f) in (None, "")]
            if miss or not all(_num(data[f]) for f in ("fill", "lot", "sl_actual")) or data["lot"] <= 0:
                bad(r, f"an execution needs {EXEC_REQUIRED} (missing or invalid: {miss or 'fill / lot / sl_actual'})")
                continue
            if (data["fill"] - data["sl_actual"]) * _side(s["plan"]) <= 0:
                bad(r, "the actual stop is on the wrong side of the fill")
                continue
            s["execution"], s["state"], s["accepted"], slot = data, "TRADE_OPEN", True, sid
        elif k == "CLOSED":
            if src not in CONFIRMERS:
                bad(r, f"a closure is confirmed only by {CONFIRMERS}, not {src!r}: never inferred from price")
                continue
            if st != "TRADE_OPEN":
                bad(r, f"{sid} is {st}: only an open trade can be closed")
                continue
            miss = [f for f in CLOSE_REQUIRED if data.get(f) in (None, "")]
            if miss or data["outcome"] not in OUTCOMES or not all(_num(data[f]) for f in ("exit_px", "pl_gross", "commission", "swap")):
                bad(r, f"a closure needs {CLOSE_REQUIRED} with outcome in {OUTCOMES} (missing or invalid: {miss or 'values'})")
                continue
            if utc(data["t_exit"]) < utc(s["execution"]["t_fill"]):
                bad(r, "the exit is before the fill")
                continue
            s["closure"], s["state"], slot = data, "TRADE_CLOSED", None
        elif k == "EXPIRED":
            if st == "AWAITING_USER_CONFIRMATION":
                if utc(r["t"]) < utc(s["plan"]["expiry_utc"]):
                    bad(r, f"{sid} expires at {s['plan']['expiry_utc']}, not before")
                    continue
            elif st != "SIGNAL_GENERATED":
                bad(r, f"{sid} is {st}: only an unexecuted signal can expire")
                continue
            s["state"], s["expired_at"] = "SIGNAL_EXPIRED", r["t"]
        elif k == "CANCELLED":
            if st not in ("SIGNAL_GENERATED", "AWAITING_USER_CONFIRMATION") or data.get("reason") not in CANCEL_REASONS:
                bad(r, f"CANCELLED needs an unexecuted signal ({sid} is {st}) and a reason in {CANCEL_REASONS}")
                continue
            s["state"], s["cancel_reason"] = "SIGNAL_CANCELLED", data["reason"]
        elif k == "VERIFIED":
            if src not in CONFIRMERS or st != "TRADE_CLOSED" or s["verified"] is not None or not data.get("evidence") or not _num(data.get("pl_net")):
                bad(r, f"VERIFIED needs a closed, unverified trade ({sid} is {st}), evidence and the statement's pl_net")
                continue
            s["verified"] = data
        elif k == "OUTCOME":
            if s["outcome"] is not None:
                bad(r, f"{sid} already has its theoretical outcome")
                continue
            s["outcome"] = data
        else:
            bad(r, f"unknown kind {k!r}")
            continue
        s["events"].append(r["seq"])
    return {"signals": sig, "slot": slot, "problems": problems}


def verify(path: str) -> dict:
    """The whole file: chain, hashes, sequence, and every line replayed against the rules."""
    try:
        recs = read(path)
    except json.JSONDecodeError as e:
        return {"ok": False, "lines": None, "problems": [f"not JSON: {e}"]}
    p = chain_problems(recs) + replay(recs)["problems"]
    return {"ok": not p, "lines": len(recs), "problems": p}


@contextlib.contextmanager
def _locked(path: str):
    with open(path, "a+", encoding="utf-8") as fh:
        if fcntl:
            fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield fh
        finally:
            if fcntl:
                fcntl.flock(fh, fcntl.LOCK_UN)


def append(path: str, kind: str, data: dict, source: str, signal_id: str | None = None, t=None) -> dict:
    """Check the ledger, check the new line against the rules, then append it (flushed and fsynced). GENERATED takes the
    next Q-XXXX id and, while a trade is open, is recorded as blocked (Part 13: watch-only, never counted as a trade)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with _locked(path) as fh:
        fh.seek(0)
        try:
            recs = [json.loads(line) for line in fh.read().splitlines() if line.strip()]
        except json.JSONDecodeError as e:
            raise LedgerError(f"the ledger has a line that is not JSON ({e}); nothing appended") from e
        broken = chain_problems(recs)
        if broken:
            raise LedgerError("the ledger fails its integrity check; nothing appended: " + "; ".join(broken[:3]))
        state = replay(recs)
        data = dict(data or {})
        if kind == "GENERATED":
            signal_id = f"Q-{sum(1 for r in recs if r['kind'] == 'GENERATED') + 1:04d}"
            data.pop("blocked_by", None)
            if data.get("actionable") and state["slot"] is not None:
                data["blocked_by"] = state["slot"]
        rec = {"seq": len(recs) + 1, "t": iso(t if t is not None else datetime.now(timezone.utc)), "kind": kind,
               "signal_id": signal_id, "source": source, "data": data, "prev": recs[-1]["hash"] if recs else GENESIS}
        rec["hash"] = _digest(rec)
        _check_new(recs, rec)
        fh.seek(0, os.SEEK_END)
        fh.write(_canon(rec) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return rec


def _check_new(recs: list[dict], rec: dict) -> None:
    """Refuse the new line if replaying it adds a problem (earlier lines are judged by verify, not here)."""
    before = len(replay(recs)["problems"])
    after = replay([*recs, rec])["problems"]
    if len(after) > before:
        raise LedgerError(after[-1].split(": ", 1)[-1])


# ---------------------------------------------------------------- derived views

def view(s: dict) -> dict:
    """One signal with the Part 14.1 / 16 figures derived from its lines (nothing stored twice)."""
    p, e, c, v = s["plan"], s["execution"], s["closure"], s["verified"]
    d = _side(p)
    out = {"signal_id": s["signal_id"], "state": s["state"], "t_gen_utc": iso(p["t_gen"]) if p.get("t_gen") else None,
           "t_gen_pkt": pkt(p["t_gen"]) if p.get("t_gen") else None, "instrument": "XAUUSD", "direction": p.get("direction"),
           "setup": p.get("setup"), "tf": p.get("tf"), "actionable": bool(p.get("actionable")), "blocked": s["blocked"],
           "cancel_reason": s["cancel_reason"], "accepted": s["accepted"], "executed": e is not None, "closed": c is not None,
           "verified": v is not None, "corrections": len(s["corrections"])}
    if e:
        stop = abs(e["fill"] - e["sl_actual"])
        out.update(fill=e["fill"], t_fill=e["t_fill"], lot=e["lot"], sl_actual=e["sl_actual"],
                   slippage_adverse=round((e["fill"] - p["entry"]) * d, 2) if _num(p.get("entry")) else None,
                   execution_deviated=bool(_num(p.get("entry")) and _num(p.get("max_entry_dev")) and abs(e["fill"] - p["entry"]) > p["max_entry_dev"]),
                   after_expiry=bool(p.get("expiry_utc")) and utc(e["t_fill"]) > utc(p["expiry_utc"]),
                   sl_moved=_num(p.get("sl")) and abs(e["sl_actual"] - p["sl"]) > 1e-9,
                   rr_actual=round(abs(p["tp1"] - e["fill"]) / stop, 2) if _num(p.get("tp1")) and stop > 0 else None)
    if c:
        net = c["pl_gross"] + c["commission"] + c["swap"]
        stop = abs(e["fill"] - e["sl_actual"])
        out.update(exit_px=c["exit_px"], t_exit=c["t_exit"], outcome=c["outcome"], pl_gross=c["pl_gross"], commission=c["commission"],
                   swap=c["swap"], pl_net=round(net, 2), holding_sec=int((utc(c["t_exit"]) - utc(e["t_fill"])).total_seconds()),
                   r_price=round((c["exit_px"] - e["fill"]) * d / stop, 3) if stop > 0 else None,
                   r_net=round(net / e["risk_money"], 3) if _num(e.get("risk_money")) and e["risk_money"] > 0 else None)
    if v:
        out.update(verified_pl_net=v["pl_net"], verified_mismatch=c is not None and abs(v["pl_net"] - out["pl_net"]) > 0.01)
    return out


def outcome_from_bars(plan: dict, rows: list[tuple], bar_sec: int, hold_sec: int = HOLD_SEC) -> dict | None:
    """Part 15, at signal level (theoretical; never a trade result): from the planned entry, on the bars that open at or
    after the signal time, until the stop or hold_sec. Each +$10 / +$15 / +$20 and each target counts only if reached
    before the stop; a bar that reaches both a target and the stop counts as the stop (as the engine's simulator). MFE /
    MAE are measured up to the stop or the window's end. None while the window is still open and nothing has decided it."""
    e, d, t0 = plan["entry"], _side(plan), utc(plan["t_gen"]).timestamp()
    risk = abs(e - plan["sl"])
    tps = {k: abs(plan[k] - e) for k in ("tp1", "tp2", "tp3") if _num(plan.get(k))}
    hit, t_sl, mfe, mae, n, last_close = {}, None, 0.0, 0.0, 0, None
    for t, _o, h, lo, _c in rows:
        if t < t0:
            continue
        if t >= t0 + hold_sec:
            break
        fav, adv = ((h - e), (e - lo)) if d > 0 else ((e - lo), (h - e))
        n, last_close = n + 1, t + bar_sec
        if adv >= risk:
            t_sl, mae = t + bar_sec, max(mae, adv)
            break
        mfe, mae = max(mfe, fav), max(mae, adv)
        for k, x in [*((f"{m:g}", m) for m in MOVES), *tps.items()]:
            if k not in hit and fav >= x:
                hit[k] = t + bar_sec
    done = t_sl is not None or (last_close is not None and last_close >= t0 + hold_sec)
    if not done:
        return None
    return {"basis": "planned entry; bars opening at or after the signal; a bar touching target and stop counts as the stop",
            "bar_sec": bar_sec, "hold_sec": hold_sec, "bars": n, "sl_hit": t_sl is not None, "t_sl": iso(t_sl) if t_sl else None,
            "reached": {f"{m:g}": iso(hit[f"{m:g}"]) if f"{m:g}" in hit else None for m in MOVES},
            "targets": {k: iso(hit[k]) if k in hit else None for k in ("tp1", "tp2", "tp3") if k in tps},
            "mfe": round(mfe, 2), "mae": round(mae, 2)}


def read_bars(where: str) -> tuple[list[tuple], int]:
    """(epoch open, open, high, low, close) rows from a market-data store directory of monthly CSVs or a site payload."""
    rows = []
    if os.path.isdir(where):
        for f in sorted(os.listdir(where)):
            if f.endswith(".csv"):
                with open(os.path.join(where, f), encoding="utf-8") as fh:
                    rd = csv.reader(fh)
                    head = [h.strip().lower() for h in next(rd, [])]
                    if not head:
                        continue
                    col = [head.index(k) for k in ("open", "high", "low", "close")]   # the time is the first column, named or not
                    for rec in rd:
                        if rec:
                            rows.append((utc(rec[0]).timestamp(), *(float(rec[i]) for i in col)))
    else:
        with open(where, encoding="utf-8") as fh:
            ch = json.load(fh)["chart"]
        rows = [(float(t), o, h, lo, c) for t, o, h, lo, c in zip(ch["t"], ch["o"], ch["h"], ch["l"], ch["c"], strict=True)]
    rows.sort()
    gaps = sorted({round(b[0] - a[0]) for a, b in itertools.pairwise(rows) if b[0] > a[0]})
    return rows, int(gaps[0]) if gaps else 0


# ---------------------------------------------------------------- statistics (Part 15)

def wilson(k: int, n: int) -> list:
    if n <= 0:
        return [None, None]
    z, p = 1.959964, k / n
    den, c = 1 + z * z / n, p + z * z / (2 * n)
    h = z * math.sqrt(max(p * (1 - p) / n + z * z / (4 * n * n), 0))
    return [round(max(0.0, (c - h) / den), 4), round(min(1.0, (c + h) / den), 4)]


def _rate(k: int, n: int) -> dict:
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "wilson95": wilson(k, n)}


def _theory(sigs: list[dict]) -> dict:
    o = [s["outcome"] for s in sigs if s["outcome"]]
    out = {"n_signals": len(sigs), "n_with_outcome": len(o)}
    for m in MOVES:
        out[f"reached_{m:g}_before_stop"] = _rate(sum(1 for x in o if x["reached"].get(f"{m:g}")), len(o))
    for k in ("tp1", "tp2", "tp3"):
        has = [x for x in o if k in x["targets"]]
        out[f"{k}_before_stop"] = _rate(sum(1 for x in has if x["targets"][k]), len(has))
    out["mean_mfe"] = round(sum(x["mfe"] for x in o) / len(o), 2) if o else None
    out["mean_mae"] = round(sum(x["mae"] for x in o) / len(o), 2) if o else None
    out["status"] = "INSUFFICIENT EVIDENCE" if len(o) < MIN_N else "MEASURED"
    return out


def _actual(views: list[dict]) -> dict:
    closed = [v for v in views if v["closed"]]
    nets = [v["pl_net"] for v in closed]
    wins, losses = [x for x in nets if x > 0.005], [x for x in nets if x < -0.005]
    eq, peak, dd, run, worst = 0.0, 0.0, 0.0, 0, 0
    for x in nets:
        eq += x
        peak, dd = max(peak, eq), max(dd, peak - eq)
        run = run + 1 if x < -0.005 else 0
        worst = max(worst, run)
    rs = [v["r_net"] for v in closed if v.get("r_net") is not None]
    tp = sum(1 for v in closed if v["outcome"] in ("TP1", "TP2", "TP3"))
    sl = sum(1 for v in closed if v["outcome"] == "SL")

    def group(key):
        g = {}
        for v in closed:
            x = g.setdefault(str(v.get(key) or "unknown"), {"n": 0, "net": 0.0, "wins": 0})
            x["n"], x["net"], x["wins"] = x["n"] + 1, round(x["net"] + v["pl_net"], 2), x["wins"] + (v["pl_net"] > 0.005)
        return g

    ex = [v for v in views if v["executed"]]
    return {"n_executed": len(ex), "n_closed": len(closed),
            "execution_deviated": sum(1 for v in ex if v["execution_deviated"]), "after_expiry": sum(1 for v in ex if v["after_expiry"]),
            "mean_adverse_slippage": round(sum(v["slippage_adverse"] for v in ex) / len(ex), 3) if ex else None,
            "win": _rate(len(wins), len(closed)), "loss": _rate(len(losses), len(closed)),
            "break_even": _rate(len(closed) - len(wins) - len(losses), len(closed)),
            "net_total": round(sum(nets), 2), "net_mean": round(sum(nets) / len(nets), 2) if nets else None,
            "net_r_mean": round(sum(rs) / len(rs), 3) if rs else None, "net_r_n": len(rs),
            "avg_win": round(sum(wins) / len(wins), 2) if wins else None, "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
            "profit_factor": round(sum(wins) / -sum(losses), 3) if losses else None, "max_drawdown": round(dd, 2),
            "max_consecutive_losses": worst,
            "mean_commission": round(sum(v["commission"] for v in closed) / len(closed), 2) if closed else None,
            "mean_swap": round(sum(v["swap"] for v in closed) / len(closed), 2) if closed else None,
            "tp_first_vs_sl_first": {"tp": tp, "sl": sl, "tp_share": _rate(tp, tp + sl)},
            "by_setup": group("setup"), "by_tf": group("tf"), "by_session": group("session"),
            "verified": sum(1 for v in closed if v["verified"]), "verified_mismatch": sum(1 for v in closed if v.get("verified_mismatch")),
            "status": "INSUFFICIENT EVIDENCE" if len(closed) < MIN_N else "MEASURED"}


def stats(path: str) -> dict:
    """Part 15: the five populations kept apart, theoretical (signal-level) and actual (MT5) results never mixed. Every
    line counts: expired, cancelled, blocked and losing records are reported, none dropped."""
    st = replay(read(path))
    sigs = list(st["signals"].values())
    views = {s["signal_id"]: {**view(s), "session": s["plan"].get("session")} for s in sigs}
    pops = {"1_generated": sigs, "2_qualified": [s for s in sigs if s["plan"].get("actionable")],
            "3_accepted": [s for s in sigs if s["accepted"]], "4_executed": [s for s in sigs if s["execution"]],
            "5_closed_executed": [s for s in sigs if s["closure"]]}
    out = {"populations": {k: {"n": len(v), "theoretical": _theory(v)} for k, v in pops.items()},
           "states": {x: sum(1 for s in sigs if s["state"] == x) for x in STATES if x != "NO_OPEN_TRADE"},
           "blocked": sum(1 for s in sigs if s["blocked"]),
           "cancel_reasons": {r: sum(1 for s in sigs if s["cancel_reason"] == r) for r in CANCEL_REASONS},
           "slot": st["slot"] or "NO_OPEN_TRADE", "problems": st["problems"]}
    for k in ("4_executed", "5_closed_executed"):
        out["populations"][k]["actual"] = _actual([views[s["signal_id"]] for s in pops[k]])
    out["note"] = ("theoretical = from the planned entry on market bars (signal level, not a trade); actual = the operator's "
                   "confirmed MT5 executions and closures only")
    return out


# ---------------------------------------------------------------- outputs

EXPORT = ("signal_id", "t_gen_utc", "t_gen_pkt", "instrument", "direction", "setup", "tf", "price_at_gen", "entry", "max_entry_dev",
          "fill", "t_fill", "slippage_adverse", "execution_deviated", "after_expiry", "sl", "sl_actual", "sl_moved", "tp1", "tp2",
          "tp3", "rr", "rr_actual", "spread", "spread_exec", "commission_est", "commission", "slippage_est", "swap", "risk_price",
          "risk_money", "lot", "state", "actionable", "blocked", "cancel_reason", "accepted", "executed", "closed", "outcome",
          "exit_px", "t_exit", "pl_gross", "pl_net", "r_price", "r_net", "holding_sec", "evidence_exec", "evidence_close",
          "verified", "verified_pl_net", "verified_mismatch", "corrections", "theory_10", "theory_15", "theory_20",
          "theory_tp1", "theory_tp2", "theory_sl", "theory_mfe", "theory_mae", "source")


def export_rows(path: str) -> list[dict]:
    out = []
    for s in replay(read(path))["signals"].values():
        v, p, e, c, o = view(s), s["plan"], s["execution"] or {}, s["closure"] or {}, s["outcome"]
        row = {**{k: p.get(k) for k in ("price_at_gen", "entry", "max_entry_dev", "sl", "tp1", "tp2", "tp3", "rr", "spread",
                                         "commission_est", "slippage_est")}, **v,
               "spread_exec": e.get("spread_exec"), "risk_money": e.get("risk_money"), "evidence_exec": e.get("evidence"),
               "evidence_close": c.get("evidence"), "source": s["source"],
               "risk_price": round(abs(p["entry"] - p["sl"]), 2) if _num(p.get("entry")) and _num(p.get("sl")) else None}
        if o:
            row.update(theory_10=o["reached"].get("10"), theory_15=o["reached"].get("15"), theory_20=o["reached"].get("20"),
                       theory_tp1=o["targets"].get("tp1"), theory_tp2=o["targets"].get("tp2"), theory_sl=o["t_sl"],
                       theory_mfe=o["mfe"], theory_mae=o["mae"])
        out.append({k: row.get(k) for k in EXPORT})
    return out


def export_csv(path: str) -> str:
    """The reproducible export: one row per signal, fixed columns, the same bytes for the same ledger."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=EXPORT, lineterminator="\n")
    w.writeheader()
    for row in export_rows(path):
        w.writerow({k: "" if v is None else v for k, v in row.items()})
    return buf.getvalue()


def snapshot(path: str) -> dict:
    """What the website's trading-status section may show: the slot and the latest signal's id and state. No fill,
    no P/L, no balance (the operator's results stay private)."""
    vr = verify(path)
    st = replay(read(path))
    sigs = list(st["signals"].values())
    last = sigs[-1] if sigs else None
    open_ = st["signals"].get(st["slot"]) if st["slot"] else None
    return {"integrity_ok": vr["ok"], "state": "TRADE_OPEN" if open_ else "NO_OPEN_TRADE",
            "open": {"signal_id": open_["signal_id"], "side": open_["plan"]["direction"]} if open_ else None,
            "last_signal": {"signal_id": last["signal_id"], "direction": last["plan"].get("direction"), "state": last["state"],
                            "t_gen_utc": iso(last["plan"]["t_gen"]) if last["plan"].get("t_gen") else None} if last else None,
            "counts": {x: sum(1 for s in sigs if s["state"] == x) for x in STATES if x != "NO_OPEN_TRADE"}}


def notification(s: dict, now) -> list[str]:
    """Part 21's phone text for one signal. Actionable only while it awaits confirmation, before its expiry, with a
    complete plan; anything else says NO TRADE with the reason, or ENTRY MISSED — DO NOT CHASE."""
    p = s["plan"]
    if s["state"] == "SIGNAL_CANCELLED" and s["cancel_reason"] == "ENTRY_MISSED":
        return [f"XAUUSD {p.get('direction', '')} | Signal ID: {s['signal_id']}", "ENTRY MISSED — DO NOT CHASE"]
    why = (p.get("reason") if not p.get("actionable") else "blocked: one trade is already open" if s["blocked"]
           else None)
    gaps = plan_gaps(p) if p.get("actionable") else []
    if why is None and gaps:
        why = "incomplete trade plan (" + "; ".join(gaps) + ")"
    if why is None and s["state"] != "AWAITING_USER_CONFIRMATION":
        why = f"signal {s['state'].replace('_', ' ').lower()}"
    if why is None and utc(now) >= utc(p["expiry_utc"]):
        why = "signal expired"
    if why is not None:
        return ["XAUUSD | NO TRADE", f"Reason: {why}"]
    return [f"XAUUSD {p['direction']} | Signal ID: {s['signal_id']}", f"Entry: {p['entry']:.1f}",
            f"SL: {p['sl']:.1f} | TP1: {p['tp1']:.1f}", f"TP2: {p['tp2']:.1f} | RR: {p['rr']:.1f}",
            f"Confirm: {p['confirmation']}", f"Expiry: {utc(p['expiry_utc']).astimezone(PKT):%H:%M} PKT",
            "Status: WAITING FOR EXECUTION"]


# ---------------------------------------------------------------- inputs from the published records

def c1_plan(x: dict, c1: dict, late_frac: float) -> dict:
    """The Part 12 fields of one C1 setup (index.json alerts.c1), as published; nothing filled in. The maximum entry
    deviation is the existing LATE rule (alerts.plans.late_frac x the stop distance, declared 2026-11-03). The C1 record
    carries no higher-timeframe alignment, so that field says so."""
    side = "BUY" if x["dir"] > 0 else "SELL"
    base = {"direction": side, "setup": "Engine signal + C1 15m confirmation", "tf": x.get("tf"), "source_record": f"alerts.c1 #{x['id']}",
            "htf_alignment": "UNAVAILABLE (not published by C1)", "t_signal_bar": iso(x["t_close"]), "trigger_p0": x.get("p0")}
    cf, pl = x.get("conf"), x.get("plan")
    if not (cf and pl):
        return {**base, "actionable": False, "t_gen": iso(x.get("t_done") or x["t_close"]),
                "reason": f"C1 setup #{x['id']} {x.get('status')}: {x.get('why') or 'not confirmed'}"}
    cp = pl.get("cost_parts") or {}
    stop = abs(pl["entry"] - pl["sl"])
    return {**base, "actionable": True, "t_gen": iso(cf["t"]), "data_ts": iso(cf["t"]), "price_at_gen": cf.get("px"),
            "px_at_alert": (cf.get("now") or {}).get("px"), "entry": pl["entry"], "entry_zone": None, "sl": pl["sl"],
            "tp1": pl["tp1"], "tp2": pl["tp2"], "tp3": None, "rr": pl.get("rr_net"), "spread": cp.get("spread"),
            "commission_est": cp.get("commission"), "slippage_est": cp.get("slippage"), "cost_units": "$ of price per oz (C1 cost split)",
            "max_entry_dev": round(late_frac * stop, 2) if _num(late_frac) else None,
            "max_entry_dev_rule": f"alerts.plans.late_frac {late_frac} x stop distance (the LATE rule)",
            "confirmation": "15M close", "invalidation": f"stop {pl['sl']}",
            "expiry_utc": iso(cf["t"] + int(c1.get("fresh_sec") or 0)) if c1.get("fresh_sec") else None,
            "reason": f"C1 setup #{x['id']}: engine signal {iso(x['t_close'])}, confirmed by a 15m close {cf.get('move')} beyond the trigger ({cf.get('tier')})"}


def import_c1(path: str, index: dict, now=None) -> list[dict]:
    """Record every finished or confirmed C1 setup once (keyed c1:<id>): a confirmed one as an actionable signal, one that
    ended unconfirmed as a non-actionable signal followed by its cancellation or expiry. A setup still waiting for its
    close is not a signal yet and is left for a later run."""
    al = index.get("alerts") or {}
    c1, late = al.get("c1") or {}, (al.get("plans") or {}).get("late_frac")
    have = {r.get("source") for r in read(path)}
    done = []
    for x in sorted([*(c1.get("recent") or []), *(c1.get("open") or [])], key=lambda s: (s["t_close"], s["id"])):
        key = f"c1:{x['id']}"
        if key in have or x.get("status") == "PENDING":
            continue
        have.add(key)
        plan = c1_plan(x, c1, late)
        if plan.get("actionable") and plan_gaps(plan):
            plan = {**plan, "actionable": False, "reason": "incomplete trade plan in the C1 record: " + "; ".join(plan_gaps(plan))}
        rec = append(path, "GENERATED", plan, key, t=now)
        done.append(rec)
        if not plan["actionable"]:
            st = x.get("status") if not (x.get("conf") and x.get("plan")) else None   # None: confirmed, but its plan was incomplete
            if st == "EXPIRED":
                done.append(append(path, "EXPIRED", {"note": x.get("why")}, key, rec["signal_id"], t=now))
            else:
                done.append(append(path, "CANCELLED", {"reason": "INVALIDATED" if st == "INVALIDATED" else "REJECTED" if st == "REJECTED" else "OTHER",
                                                       "note": x.get("why") if st else plan["reason"]}, key, rec["signal_id"], t=now))
    return done


def expire_due(path: str, now) -> list[dict]:
    """Mark every signal still awaiting confirmation past its expiry as SIGNAL_EXPIRED (never as a trade)."""
    out = []
    for s in replay(read(path))["signals"].values():
        if s["state"] == "AWAITING_USER_CONFIRMATION" and utc(now) >= utc(s["plan"]["expiry_utc"]):
            out.append(append(path, "EXPIRED", {"note": "no execution confirmed before the expiry"}, "ledger", s["signal_id"], t=now))
    return out


def record_outcomes(path: str, bars: str) -> list[dict]:
    """Append the theoretical outcome of every actionable signal whose window is decided on the given bars."""
    rows, sec = read_bars(bars)
    out = []
    for s in replay(read(path))["signals"].values():
        if s["outcome"] is None and s["plan"].get("actionable") and not plan_gaps(s["plan"]):
            o = outcome_from_bars(s["plan"], rows, sec)
            if o is not None:
                out.append(append(path, "OUTCOME", o, "bars:" + os.path.basename(os.path.normpath(bars)), s["signal_id"]))
    return out


ALIASES = {"ticket": ("ticket", "position", "deal", "order"), "type": ("type", "direction", "side"),
           "open_time": ("open_time", "time", "open time"), "open_price": ("open_price", "price", "open price"),
           "close_time": ("close_time", "close time"), "close_price": ("close_price", "close price"),
           "commission": ("commission",), "swap": ("swap",), "profit": ("profit",), "symbol": ("symbol",)}


def reconcile(path: str, broker_csv: str, server_utc_offset_h: float | None = None) -> dict:
    """Read-only comparison of the confirmed trades with a broker history export (CSV with a header row; the usual MT5
    column names are recognised). Matches by ticket when both have one; otherwise by side, fill time (2 min) and price
    ($0.50), but only when the broker server's UTC offset is given, because MT5 history is in server time, not UTC, and
    the offset is never assumed. Reports differences, ledger trades the broker file lacks, and XAUUSD broker trades the
    ledger lacks (a missing record). It writes nothing: a VERIFIED line is added by the operator with the statement as
    evidence."""
    with open(broker_csv, encoding="utf-8-sig") as fh:
        raw = list(csv.DictReader(fh))
    deals = []
    for r in raw:
        low = {k.strip().lower(): v for k, v in r.items() if k}
        g = {f: next((low[a] for a in al if a in low and low[a] not in (None, "")), None) for f, al in ALIASES.items()}
        if g["symbol"] and "XAU" not in g["symbol"].upper():
            continue
        try:
            t_srv = datetime.fromisoformat(g["open_time"].replace(".", "-", 2)).replace(tzinfo=timezone.utc).timestamp()
            deals.append({"ticket": g["ticket"], "side": "BUY" if str(g["type"]).lower().startswith("buy") else "SELL",
                          "t_open": t_srv - server_utc_offset_h * 3600 if server_utc_offset_h is not None else None,
                          "open_price": float(g["open_price"]),
                          "close_price": float(g["close_price"]) if g["close_price"] else None,
                          "net": sum(float(g[k]) for k in ("profit", "commission", "swap") if g[k] not in (None, ""))})
        except (TypeError, ValueError, AttributeError):
            continue
    used, out = set(), {"matched": [], "ledger_only": [], "broker_only": []}
    for s in replay(read(path))["signals"].values():
        if not s["execution"]:
            continue
        v, e = view(s), s["execution"]
        cand = [i for i, d in enumerate(deals) if i not in used and (
            (e.get("ticket") and d["ticket"] and str(e["ticket"]) == str(d["ticket"])) or
            (d["t_open"] is not None and d["side"] == v["direction"] and abs(d["t_open"] - utc(e["t_fill"]).timestamp()) <= MATCH_SEC
             and abs(d["open_price"] - e["fill"]) <= MATCH_PX))]
        if not cand:
            out["ledger_only"].append(v["signal_id"])
            continue
        used.add(cand[0])
        d = deals[cand[0]]
        diff = {k: [a, b] for k, a, b in (("fill", e["fill"], d["open_price"]), ("exit", v.get("exit_px"), d["close_price"]),
                                          ("pl_net", v.get("pl_net"), round(d["net"], 2)))
                if a is not None and b is not None and abs(a - b) > (0.01 if k == "pl_net" else 1e-6)}
        out["matched"].append({"signal_id": v["signal_id"], "ticket": d["ticket"], "differences": diff})
    out["broker_only"] = [deals[i]["ticket"] for i in range(len(deals)) if i not in used]
    out["time_matching"] = "on" if server_utc_offset_h is not None else "off: no server UTC offset given, tickets only"
    out["ok"] = not out["ledger_only"] and not out["broker_only"] and not any(m["differences"] for m in out["matched"])
    return out


# ---------------------------------------------------------------- command line

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("verify", "record", "import-c1", "expire", "outcomes", "export", "stats", "snapshot", "notify", "reconcile"):
        p = sub.add_parser(name)
        p.add_argument("--ledger", required=True)
        p.add_argument("--now", default=None)
        if name == "record":
            p.add_argument("--kind", required=True, choices=KINDS)
            p.add_argument("--signal", default=None)
            p.add_argument("--source", required=True)
            p.add_argument("--data", default="{}")
        if name == "import-c1":
            p.add_argument("--index", required=True)
        if name == "outcomes":
            p.add_argument("--bars", required=True)
        if name in ("export",):
            p.add_argument("--csv", required=True)
        if name in ("stats", "snapshot"):
            p.add_argument("--json", default=None)
        if name == "notify":
            p.add_argument("--signal", required=True)
        if name == "reconcile":
            p.add_argument("--mt5", required=True)
            p.add_argument("--server-utc-offset", type=float, default=None, help="the MT5 server's UTC offset in hours (never assumed)")
    a = ap.parse_args(argv)
    now = a.now or iso(datetime.now(timezone.utc))
    try:
        if a.cmd == "verify":
            res = verify(a.ledger)
        elif a.cmd == "record":
            res = append(a.ledger, a.kind, json.loads(a.data), a.source, a.signal, t=a.now)
        elif a.cmd == "import-c1":
            with open(a.index, encoding="utf-8") as fh:
                res = [r["signal_id"] for r in import_c1(a.ledger, json.load(fh), now)]
        elif a.cmd == "expire":
            res = [r["signal_id"] for r in expire_due(a.ledger, now)]
        elif a.cmd == "outcomes":
            res = [r["signal_id"] for r in record_outcomes(a.ledger, a.bars)]
        elif a.cmd == "export":
            with open(a.csv, "w", encoding="utf-8", newline="") as fh:
                fh.write(export_csv(a.ledger))
            res = {"rows": len(export_rows(a.ledger)), "csv": a.csv}
        elif a.cmd == "stats":
            res = stats(a.ledger)
        elif a.cmd == "snapshot":
            res = snapshot(a.ledger)
        elif a.cmd == "notify":
            s = replay(read(a.ledger))["signals"].get(a.signal)
            if s is None:
                raise LedgerError(f"no signal {a.signal}")
            res = notification(s, now)
        else:
            res = reconcile(a.ledger, a.mt5, a.server_utc_offset)
    except LedgerError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    text = json.dumps(res, indent=1, ensure_ascii=False)
    if getattr(a, "json", None):
        with open(a.json, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 1 if a.cmd == "verify" and not res["ok"] else 0


if __name__ == "__main__":
    sys.exit(main())
