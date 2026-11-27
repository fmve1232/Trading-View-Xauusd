"""Per-trade forward diagnostics (operator G4, 27 Nov 2026; RECORDS ONLY).

For every CLOSED trade in the forward ledgers (<store>/holdout/<tf>_<arm>.json, every arm and timeframe), from the
stored XAU/USD 5-minute bars, in time order:

  race         against the ORIGINAL stop, from the fill for up to HORIZON_SEC: +$10, +$15, +$20, TP1 and TP2: which
               came first (TARGET / STOP_FIRST / UNDECIDED) and the hours from the fill to the target
  race_window  where the race ended: at the stop (STOP), at the bar that reached the last target (ALL_TARGETS), or at
               the horizon (HORIZON); the hours to that point, and the favourable excursion inside it (the stop bar's
               favourable side excluded). "stop" reports the stop inside this window only
  next_open    the same race for +$10 / +$15 / +$20 entered at the OPEN of the first 5-minute bar after the signal
               (next-bar convention), with the original stop, and how far that open was from the engine's fill
  in_trade     the maximum adverse / favourable excursion (MAE / MFE, $ and R) from the fill to the recorded exit
  exit         the ledger's exit reason, exit bar and hours held (copied; the ledger record is never changed)
  cost         the modelled cost of record (MODEL) and the measured cost (null: no broker fills yet, G2)
  news         NFP / CPI / FOMC from quantum/news_calendar.py (no other release is in that calendar): on the fill's
               New York day, inside the trade, within the +-30 min window of the fill; "covered": false outside the
               calendar's range

Conventions (the engine's, quantum/backtest.simulate): the ledger's entry_time is the signal bar's OPEN label and the
fill is that bar's CLOSE, so the path starts with the first 5-minute bar opening at the close (entry-bar convention).
A 5-minute bar that touches both the stop and a target counts as the stop (the path inside a bar is unknown); a bar
that opens beyond a level reached it at the open. For an exit at a price (SL, SL_GAP, BE, BE_GAP, TP2) the in-trade
window ends at the first 5-minute bar of the exit bar that reaches the exit price, and only that bar's exit side
counts, capped at the exit price; for an exit at a close (FLIP) the window ends at the exit bar's close.

No look-ahead, and final when written: only 5-minute bars that had CLOSED by the run time are read (the store also
keeps the still-forming bar); a record is written only when both races are decided or the horizon has passed, and the
bars through the exit are stored; every field depends only on bars up to the end of its race window or the exit, so
a later bar cannot change it. Written once and never rewritten: each record carries the SHA-256 of the bars it used
and of the ledger trade it describes, so audit/tools/trade_diag_check.py can recompute it independently.

Files: <store>/trade_diag/<YYYY-MM-DD>.jsonl (the run's UTC day), merged into <ledger>/trade_diag/ by a union over the
trade key (normal commits, never force-pushed). Outside holdout.ENGINE_SOURCES: nothing in the engine, the arms, the
alerts or the ledgers reads it.

  python -m quantum.trade_diag --append <store> [--now ISO]             after the pipeline, every run
  python -m quantum.trade_diag --merge-ledger <store>/trade_diag <ledger>/trade_diag
  python -m quantum.trade_diag --summary <trade_diag dir> [--json | --markdown]   per arm and timeframe
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import news_calendar
from .data import sources, store

DIR = "trade_diag"
HORIZON_SEC = 7 * 86400
USD = (10.0, 15.0, 20.0)
TF_SEC = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}
LEVEL_EXITS = ("SL", "SL_GAP", "BE", "BE_GAP", "TP2")          # exits at a price; FLIP exits at the bar close
ADVERSE_EXITS = ("SL", "SL_GAP", "BE", "BE_GAP")
LEDGER_RE = re.compile(r"^(5m|15m|30m|1h|4h)_([a-z0-9]+)\.json$")
NY = ZoneInfo("America/New_York")
_HERE = os.path.dirname(os.path.abspath(__file__))


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(obj) -> str:
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def _code_sha() -> str:
    with open(os.path.join(_HERE, "trade_diag.py"), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def ts(iso: str) -> int:
    return int(pd.Timestamp(iso).timestamp())


def bars5(store_dir: str, t_now: float | None = None) -> dict | None:
    """The stored XAU/USD 5-minute bars as the engine reads them (off-grid rows and shut-market bars dropped, the
    first print of each session repaired), as arrays: t = bar open (epoch s), o, h, l. With t_now, only the bars
    that had closed by then (the store also keeps the still-forming bar, whose high and low can still move)."""
    df = store.load(store_dir, "XAU/USD_5m")
    if df is None or not len(df):
        return None
    df = sources.repair_reopen(sources.trading_week_only(sources.drop_offgrid(df)), 300)
    ix = pd.DatetimeIndex(df.index)
    ix = ix.tz_localize("UTC") if ix.tz is None else ix.tz_convert("UTC")
    t = ix.as_unit("s").asi8.astype(np.int64)                                     # seconds, whatever the index unit
    keep = np.ones(len(t), bool) if t_now is None else (t + 300 <= t_now)
    if not keep.any():
        return None
    return {"t": t[keep], "o": df["open"].to_numpy(float)[keep], "h": df["high"].to_numpy(float)[keep],
            "l": df["low"].to_numpy(float)[keep]}


def ledger_trades(store_dir: str):
    """(tf, arm, trade) for every closed trade in <store>/holdout/<tf>_<arm>.json (archives and manifests skipped)."""
    for f in sorted(glob.glob(os.path.join(store_dir, "holdout", "*.json"))):
        m = LEDGER_RE.match(os.path.basename(f))
        if not m:
            continue
        with open(f) as fh:
            rows = json.load(fh)
        if not isinstance(rows, list):
            continue
        for t in rows:
            if not t.get("open"):
                yield m.group(1), m.group(2), t


def _first(mask: np.ndarray) -> int | None:
    k = np.flatnonzero(mask)
    return int(k[0]) if len(k) else None


def _r(x: float | None, d: float) -> float | None:
    return None if x is None or not d else round(x / d, 4)


def _race(o, h, l, tt, long: bool, entry: float, sl: float, targets: dict, t_fill: int, horizon_over: bool):
    """Each target against the stop over the 5-minute bars from the fill: TARGET / STOP_FIRST / UNDECIDED and the
    hours from the fill to the close of the bar that reached it; and the race window, which ends at the stop, at the
    bar that reached the last target, or at the last bar read. Once the race is decided nothing in it depends on a
    later bar."""
    stop = (l <= sl) | (o <= sl) if long else (h >= sl) | (o >= sl)
    ks = _first(stop)
    race, hit_k = {}, {}
    for name, px in targets.items():
        hit = (h >= px) | (o >= px) if long else (l <= px) | (o <= px)
        kt = _first(hit)
        hit_k[name] = kt
        if kt is not None and (ks is None or kt < ks):
            race[name] = {"result": "TARGET", "hours": round((int(tt[kt]) + 300 - t_fill) / 3600.0, 3), "price": round(px, 3)}
        elif ks is not None:
            race[name] = {"result": "STOP_FIRST", "hours": None, "price": round(px, 3)}
        else:
            race[name] = {"result": "UNDECIDED", "hours": None, "price": round(px, 3)}
    k_all = max(hit_k.values()) if all(k is not None for k in hit_k.values()) else None
    if ks is not None and (k_all is None or ks <= k_all):
        ends, k_end, upto = "STOP", ks, ks                     # the stop bar's favourable side is not counted
    elif k_all is not None:
        ends, k_end, upto = "ALL_TARGETS", k_all, k_all + 1    # a stop after this is outside the race
    else:
        ends, k_end, upto = ("HORIZON" if horizon_over else "UNDECIDED"), len(o) - 1, len(o)
    mfe = ((np.max(h[:upto]) - entry) if long else (entry - np.min(l[:upto]))) if upto > 0 else 0.0
    hrs = round((int(tt[k_end]) + 300 - t_fill) / 3600.0, 3)
    win = {"ends": ends, "bars": int(k_end + 1), "hours": hrs, "mfe_usd": round(float(max(mfe, 0.0)), 3)}
    return race, win


def news(t_fill: int, t_out: int, evs: list[dict] | None = None) -> dict:
    """NFP / CPI / FOMC around a trade (quantum/news_calendar.py, New York times)."""
    evs = news_calendar.events() if evs is None else evs
    covered = bool(evs) and t_fill >= evs[0]["t"] - 86400 and t_fill <= evs[-1]["t"] + 86400
    day = datetime.fromtimestamp(t_fill, NY).date()
    same_day = [e["name"] for e in evs if datetime.fromtimestamp(e["t"], NY).date() == day]
    inside = [e["name"] for e in evs if t_fill <= e["t"] <= t_out]
    near = min(((abs(e["t"] - t_fill) / 60.0, e) for e in evs), key=lambda x: x[0], default=(None, None))
    w_b, w_a = news_calendar.BEFORE_MIN, news_calendar.AFTER_MIN
    in_window = [e["name"] for e in evs if e["t"] - w_b * 60 <= t_fill <= e["t"] + w_a * 60]
    return {"covered": covered, "news_day": bool(same_day), "events_that_day": same_day, "event_in_trade": inside,
            "fill_in_window": in_window, "window_min": [w_b, w_a],
            "nearest_event_min": round(near[0], 1) if near[0] is not None and near[0] <= 24 * 60 else None,
            "nearest_event": near[1]["name"] if near[0] is not None and near[0] <= 24 * 60 else None,
            "calendar": news_calendar.SOURCE, "scope": "NFP, CPI and FOMC only: other USD releases are not in the calendar"}


def diagnose(tf: str, arm: str, t: dict, B: dict, evs: list[dict] | None = None) -> dict | None:
    """The diagnostic record of one closed ledger trade from 5-minute bars B (bars5), or None while it cannot be final
    (either race undecided and the horizon not over, or the bars do not yet reach the exit bar's close)."""
    sec = TF_SEC[tf]
    long = t["dir"] == "LONG"
    sgn = 1.0 if long else -1.0
    e, sl = float(t["entry"]), float(t["sl"])
    d_sl = abs(e - sl)
    t_fill = ts(t["entry_time"]) + sec
    t_exit_bar = ts(t["exit_time"])
    T = B["t"]
    if not len(T):
        return None
    t_last = int(T[-1]) + 300                                  # the close of the last stored bar
    if t_exit_bar + sec > t_last:
        return None
    j0 = int(np.searchsorted(T, t_fill, side="left"))
    j_end = int(np.searchsorted(T, t_fill + HORIZON_SEC, side="left"))
    o, h, l, tt = B["o"][j0:j_end], B["h"][j0:j_end], B["l"][j0:j_end], T[j0:j_end]
    if not len(o):
        return None
    # ---- race against the original stop: the engine's fill (entry bar) and the next bar's open
    horizon_over = t_fill + HORIZON_SEC <= t_last
    tg = {f"usd{int(u)}": e + sgn * u for u in USD}
    tg.update({"tp1": float(t["tp1"]), "tp2": float(t["tp2"])})
    race, win = _race(o, h, l, tt, long, e, sl, tg, t_fill, horizon_over)
    o0 = float(o[0])
    race_n, win_n = _race(o, h, l, tt, long, o0, sl, {f"usd{int(u)}": o0 + sgn * u for u in USD}, t_fill, horizon_over)
    if "UNDECIDED" in (win["ends"], win_n["ends"]):
        return None
    # ---- in-trade excursion, fill to recorded exit
    reason = t.get("exit_reason")
    xb0 = int(np.searchsorted(T, t_exit_bar, side="left"))
    xb1 = int(np.searchsorted(T, t_exit_bar + sec, side="left"))
    end, last_side, ends = xb1, None, "exit bar close"
    if reason in LEVEL_EXITS and t.get("exit") is not None:
        xp = float(t["exit"])
        adverse = reason in ADVERSE_EXITS and ((xp <= e) if long else (xp >= e))
        below = long == adverse                      # the exit price lies below the fill (long stop / short target)
        ends = "exit price not found in the stored bars"
        for k in range(max(xb0, j0), xb1):
            if (B["l"][k] <= xp <= B["h"][k]) or (B["o"][k] <= xp if below else B["o"][k] >= xp):
                end, last_side, ends = k + 1, below, "exit price touched"
                break
    seg = slice(j0, max(end, j0 + 1))
    hh, ll = B["h"][seg].copy(), B["l"][seg].copy()
    if last_side is not None and len(hh):
        # the bar that reached the exit price: only its exit side counts, and never beyond the fill
        xp = float(t["exit"])
        if last_side:                                # exit price below the fill: the bar's low, never below the exit
            ll[-1], hh[-1] = max(ll[-1], xp), e      # its high is of unknown order: not counted
        else:                                        # exit price above the fill: the bar's high, never above the exit
            hh[-1], ll[-1] = min(hh[-1], xp), e
    mfe = max(((np.max(hh) - e) if long else (e - np.min(ll))) if len(hh) else 0.0, 0.0)
    mae = max(((e - np.min(ll)) if long else (np.max(hh) - e)) if len(hh) else 0.0, 0.0)
    t_out = (int(T[end - 1]) + 300) if last_side is not None else t_exit_bar + sec
    used = slice(j0, max(j0 + max(win["bars"], win_n["bars"]), end))      # exactly the bars the record depends on
    bars_sha = hashlib.sha256(np.round(np.vstack([T[used].astype(float), B["o"][used], B["h"][used], B["l"][used]]), 5)
                              .tobytes()).hexdigest()
    cost = t.get("cost_pts")
    gross = t.get("gross_pts")
    return {
        "key": f"{tf}|{arm}|{t['entry_time']}|{t['dir']}", "tf": tf, "arm": arm, "dir": t["dir"],
        "entry_time": t["entry_time"], "fill_utc": datetime.fromtimestamp(t_fill, timezone.utc).isoformat(),
        "entry": e, "sl": sl, "stop_usd": round(d_sl, 3), "freeze_key": t.get("freeze_key"),
        "session": t.get("session"), "regime": t.get("regime"),
        "race": race, "horizon_hours": HORIZON_SEC / 3600, "race_window": win,
        "stop": {"hit": win["ends"] == "STOP", "hours": win["hours"] if win["ends"] == "STOP" else None,
                 "before_usd10": race["usd10"]["result"] == "STOP_FIRST", "scope": "inside the race window"},
        "next_open": {"entry": round(o0, 3), "entry_shift_usd": round(sgn * (o0 - e), 3),
                      "first_bar_gap_min": round((int(T[j0]) - t_fill) / 60.0, 1), "race": race_n, "race_window": win_n,
                      "note": "entered at the open of the first 5-minute bar after the signal; entry_shift_usd > 0 = a "
                      "worse price than the engine's fill. first_bar_gap_min > 0: the signal closed at a session close "
                      "(the market was shut at the engine's fill) and this open is the session's first bar, whose open "
                      "is the engine's repaired value (that bar's close; the feed's first print is a stale quote)"},
        "in_trade": {"mae_usd": round(float(mae), 3), "mfe_usd": round(float(mfe), 3), "mae_r": _r(float(mae), d_sl),
                     "mfe_r": _r(float(mfe), d_sl), "hours": round((t_out - t_fill) / 3600.0, 3),
                     "ends": ends},
        "exit": {"reason": reason, "exit_time": t.get("exit_time"), "exit": t.get("exit"), "bars": t.get("bars"),
                 "tp1_hit": t.get("tp1_hit"), "net_r": t.get("r"), "gross_r": _r(gross, d_sl)},
        "cost": {"model_pts": cost, "model_r": _r(cost, d_sl), "measured_pts": None,
                 "status": "MODEL: the engine's cost of record; broker costs not measured (G2)"},
        "news": news(t_fill, t_out, evs),
        "bars": {"first_open_utc": datetime.fromtimestamp(int(T[j0]), timezone.utc).isoformat(), "n": int(used.stop - used.start),
                 "sha256": bars_sha, "source": t.get("price_source")},
        "trade_sha256": sha(t),
    }


def read_dir(d: str) -> list[dict]:
    rows = []
    for f in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
        with open(f) as fh:
            rows.extend(json.loads(x) for x in map(str.strip, fh) if x)
    return rows


def append(store_dir: str, t_now: float | None = None) -> dict:
    """Write the record of every closed trade that is now final and not yet logged. Never rewrites a line."""
    now = time.time() if t_now is None else t_now
    B = bars5(store_dir, now)                                  # closed bars only
    if B is None:
        return {"state": "no 5m bars", "appended": 0}
    d = os.path.join(store_dir, DIR)
    os.makedirs(d, exist_ok=True)
    seen = {r["key"] for r in read_dir(d)}
    day, stamp = time.strftime("%Y-%m-%d", time.gmtime(now)), time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    ver = {"trade_diag_sha": _code_sha(), "github_sha": os.environ.get("GITHUB_SHA", "")}
    evs = news_calendar.events()
    new, pending, closed, errors = [], 0, 0, []
    for tf, arm, t in ledger_trades(store_dir):
        closed += 1
        key = f"{tf}|{arm}|{t.get('entry_time')}|{t.get('dir')}"
        if key in seen:
            continue
        try:
            rec = diagnose(tf, arm, t, B, evs)
        except (KeyError, TypeError, ValueError) as e:      # one malformed trade never blocks the others
            errors.append({"key": key, "error": f"{type(e).__name__}: {e}"[:200]})
            continue
        if rec is None:
            pending += 1
            continue
        rec.update({"logged_utc": stamp, "versions": ver})
        new.append(rec)
        seen.add(key)
    if new:
        with open(os.path.join(d, f"{day}.jsonl"), "a") as f:
            f.writelines(canonical(r) + "\n" for r in new)
    out = {"state": "ok", "appended": len(new), "pending": pending, "closed_trades": closed}
    if errors:
        out.update(state="errors", errors=errors[:20], n_errors=len(errors))
    return out


def merge_ledger(src: str, dst: str) -> dict:
    """Union by trade key, per day file: a key already in the ledger is never written again; nothing is removed."""
    os.makedirs(dst, exist_ok=True)
    have = {r["key"] for r in read_dir(dst)}
    added = 0
    for f in sorted(glob.glob(os.path.join(src, "*.jsonl"))):
        with open(f) as fh:
            rows = [json.loads(x) for x in map(str.strip, fh) if x]
        fresh = [r for r in rows if r["key"] not in have]
        if fresh:
            with open(os.path.join(dst, os.path.basename(f)), "a") as fh:
                fh.writelines(canonical(r) + "\n" for r in fresh)
            have.update(r["key"] for r in fresh)
            added += len(fresh)
    return {"added": added}


def wilson(k: int, n: int, z: float = 1.959964) -> list[float] | None:
    if n <= 0:
        return None
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(max(0.0, mid - half), 4), round(min(1.0, mid + half), 4)]


def _rates(g: list[dict], get) -> dict:
    res = [get(x)["result"] for x in g]
    k, n = res.count("TARGET"), res.count("TARGET") + res.count("STOP_FIRST")
    hrs = [get(x)["hours"] for x in g if get(x)["hours"] is not None]
    return {"target_first": k, "decided": n, "undecided": res.count("UNDECIDED"), "rate": round(k / n, 4) if n else None,
            "wilson95": wilson(k, n), "median_hours": round(float(np.median(hrs)), 3) if hrs else None}


def _med(v: list) -> float | None:
    v = [x for x in v if x is not None]
    return round(float(np.median(v)), 4) if v else None


def summary(rows: list[dict]) -> dict:
    """Per arm and timeframe: target-before-stop rates with Wilson 95% intervals (decided races only) and median hours
    to each target, for the engine's fill and the next bar's open; median MAE / MFE (R and $); how the race windows
    ended; exit reasons; cost status; news counts. Descriptive only: no baseline, no test (see G5 / the strategy
    report for those)."""
    out = {}
    groups: dict = {}
    for r in rows:
        groups.setdefault((r["arm"], r["tf"]), []).append(r)
    for (arm, tf), g in sorted(groups.items()):
        s = {"n": len(g)}
        for name in ("usd10", "usd15", "usd20", "tp1", "tp2"):
            s[name] = _rates(g, lambda x, nm=name: x["race"][nm])
        s["next_open"] = {name: _rates(g, lambda x, nm=name: x["next_open"]["race"][nm]) for name in ("usd10", "usd15", "usd20")}
        s["next_open"]["median_entry_shift_usd"] = _med([x["next_open"]["entry_shift_usd"] for x in g])
        s["next_open"]["filled_at_a_session_close"] = sum(1 for x in g if x["next_open"]["first_bar_gap_min"] > 0)
        for fld in ("mae_r", "mfe_r", "mae_usd", "mfe_usd"):
            s[f"median_{fld}"] = _med([x["in_trade"][fld] for x in g])
        s["race_window_ends"] = dict(sorted(_count(x["race_window"]["ends"] for x in g).items()))
        s["median_race_mfe_usd"] = _med([x["race_window"]["mfe_usd"] for x in g])
        s["stop_before_usd10"] = sum(1 for x in g if x["stop"]["before_usd10"])
        s["in_trade_ends"] = dict(sorted(_count(x["in_trade"]["ends"] for x in g).items()))
        s["exit_reasons"] = dict(sorted(_count(x["exit"]["reason"] for x in g).items()))
        s["cost_measured"] = sum(1 for x in g if x["cost"]["measured_pts"] is not None)
        s["news"] = {"covered": sum(1 for x in g if x["news"]["covered"]), "news_day": sum(1 for x in g if x["news"]["news_day"]),
                     "event_in_trade": sum(1 for x in g if x["news"]["event_in_trade"]),
                     "fill_in_window": sum(1 for x in g if x["news"]["fill_in_window"])}
        out[f"{arm}|{tf}"] = s
    return out


def _count(it) -> dict:
    c: dict = {}
    for v in it:
        c[v] = c.get(v, 0) + 1
    return c


def markdown(s: dict) -> str:
    """The summary as a markdown table: rates are target-before-stop among decided races, with Wilson 95% intervals."""
    def cell(x: dict) -> str:
        return "—" if x["rate"] is None else f"{x['rate']:.2f} [{x['wilson95'][0]:.2f}, {x['wilson95'][1]:.2f}]"
    head = ("| Arm · TF | n | +$10 first | +$15 first | +$20 first | +$15 first, next-bar open | median MAE R | "
            "median MFE R | stop before +$10 | filled at a session close |")
    rows = [head, "|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in s.items():
        rows.append(f"| {k.replace('|', ' · ')} | {v['n']} | {cell(v['usd10'])} | {cell(v['usd15'])} | {cell(v['usd20'])} | "
                    f"{cell(v['next_open']['usd15'])} | {v['median_mae_r']} | {v['median_mfe_r']} | {v['stop_before_usd10']} | "
                    f"{v['next_open']['filled_at_a_session_close']} |")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--append", metavar="STORE")
    g.add_argument("--merge-ledger", nargs=2, metavar=("SRC", "DST"))
    g.add_argument("--summary", metavar="DIR")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--markdown", action="store_true", help="with --summary: a markdown table (for the G4 document)")
    ap.add_argument("--now", help="with --append: the run time (ISO UTC) instead of the clock, to reproduce a past run")
    a = ap.parse_args(argv)
    if a.append:
        r = append(a.append, None if a.now is None else ts(a.now))
        print(json.dumps(r))
        return 1 if r["state"] == "errors" else 0                # the workflow turns this into a warning
    elif a.merge_ledger:
        print(json.dumps(merge_ledger(*a.merge_ledger)))
    else:
        s = summary(read_dir(a.summary))
        if a.markdown:
            print(markdown(s))
            return 0
        print(json.dumps(s, indent=1) if a.json else "\n".join(
            f"{k}: n {v['n']} · +$10 {v['usd10']['rate']} · +$15 {v['usd15']['rate']} · +$20 {v['usd20']['rate']} · "
            f"MAE {v['median_mae_r']} R · MFE {v['median_mfe_r']} R" for k, v in s.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
