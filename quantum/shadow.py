"""B31b-SHADOW-FWD (research/registrations/B31b-SHADOW-FWD.json): a forward shadow test of B31's five entry modules.

Live data only; nothing is sent. Every site run rebuilds the 15m context from that run's own payloads (the engine's rows
and structure markers, the 1h / 4h EMA trend), detects B31's setups, records each new one ONCE, follows it through fill /
invalidation / outcome on later closed 15m bars, freezes the outcome when it is decided, and publishes the scoreboard.

- The detectors are B31's (quantum/research/b31.py), ported here because research code is never imported by production.
  Changes, all registered: eligibility on the +10 / +15 / +20 ladder, literal dollars, no score, and a same-moment
  coin-flip control (the trade and its mirror).
- A setup first recorded more than 30 minutes after its order bar closed is LATE: kept, but outside the primary.
- Records are immutable. A setup is appended once and never removed. Its outcome is written once, then frozen.
- The payload holds closed bars only; the forming bar is excluded (sources.drop_incomplete).
- Not an ENGINE_SOURCES file: the engine, its configuration and the freeze key are untouched.
"""
from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from . import sessions

ID, FILE, DIR = "B31b-SHADOW-FWD", "B31b-SHADOW-FWD.json", "research_forward"
REG = "research/registrations/B31b-SHADOW-FWD.json"
TP = (10.0, 15.0, 20.0)
LADDER = sum(TP) / 3.0                       # the mean target of the thirds plan: the eligibility reward
REJECT_BARS, SHIFT_BARS, LIMIT_BARS, HOLD = 3, 8, 8, 96
SL_BUF, D_MIN, RR_MIN, COST_FRAC = 0.2, 5.0, 1.0, 0.15
FVG_ATR, DISP_BODY = 0.3, 2.5
REPEAT_SEC, REPEAT_USD = 4 * 3600, 15.0
OP_COST, RISK_USD, OZ = 0.26, 650.0, 100.0
TIMELY_SEC, LOOK, DEADLINE, ALPHA = 1800, 100, "2027-06-30", 0.05
BAR = 900
EPS = 1e-9
MODULES = ("A", "B", "C", "D", "E")
UNITS = MODULES + ("ALL",)
SELL_SIDE = ("PDL", "PWL", "ASL", "LOL", "NYL", "EQL")      # swept -> BUY
BUY_SIDE = ("PDH", "PWH", "ASH", "LOH", "NYH", "EQH")       # swept -> SELL
RANGE_REGIMES = ("RANGE", "COMPRESS")


# ---------------- context from the site run's payloads ----------------
class Ctx:
    pass


def _num(a) -> np.ndarray:
    return np.array([np.nan if x is None else float(x) for x in a], float)


def cost_model(cal: pd.DataFrame) -> np.ndarray:
    """The engine's session cost model in $ per oz (as research/harness.cost_pts with its defaults): spread 0.30 in a
    kill zone, London or New York, else 0.50, plus 2 x 0.20 slippage and $7 commission per 100-oz lot."""
    on = cal["in_killzone"].to_numpy(bool) | cal["in_london"].to_numpy(bool) | cal["in_ny"].to_numpy(bool)
    return np.where(on, 0.30, 0.50) + 2 * 0.20 + 7.0 / OZ


def session_label(cal: pd.DataFrame) -> np.ndarray:
    a, lo, ny = (cal[k].to_numpy(bool) for k in ("in_asian", "in_london", "in_ny"))
    return np.where(lo & ny, "LONDON+NY", np.where(lo, "LONDON", np.where(ny, "NEW YORK", np.where(a, "ASIAN", "OFF")))).astype(object)


def prev_group(key: np.ndarray, x: np.ndarray, fn) -> np.ndarray:
    """For each bar: fn (max / min) of x over ALL bars of the previous group (consecutive key runs, in order)."""
    out = np.full(len(x), np.nan)
    order = list(dict.fromkeys(key.tolist()))
    s = pd.Series(x).groupby(key, sort=False).agg(fn)
    prev = {order[i]: order[i - 1] for i in range(1, len(order))}
    for i, k in enumerate(key):
        if k in prev:
            out[i] = s[prev[k]]
    return out


def last_completed_session(flag: np.ndarray, h: np.ndarray, l: np.ndarray, date_: np.ndarray):
    """High / low of the most recently COMPLETED run of `flag` before each bar (a run's levels exist from the bar after
    its last bar), and the trading date that run belonged to."""
    n = len(flag)
    hi, lo, dt = np.full(n, np.nan), np.full(n, np.nan), np.array([None] * n, object)
    runs, i = [], 0
    while i < n:
        if flag[i]:
            j = i
            while j + 1 < n and flag[j + 1]:
                j += 1
            runs.append((i, j))
            i = j + 1
        else:
            i += 1
    for r, (a, b) in enumerate(runs):
        end = runs[r + 1][1] + 1 if r + 1 < len(runs) else n
        hi[b + 1:end], lo[b + 1:end] = h[a:b + 1].max(), l[a:b + 1].min()
        dt[b + 1:end] = date_[a]
    return hi, lo, dt


def build_pools(h: np.ndarray, l: np.ndarray, cal: pd.DataFrame, eqh: np.ndarray, eql: np.ndarray):
    date_ = np.asarray(cal["trading_date"].to_numpy())
    iso = pd.DatetimeIndex(cal["trading_date"]).isocalendar()
    wk = (iso["year"].astype(int) * 100 + iso["week"].astype(int)).to_numpy()
    pools = {"PDH": prev_group(date_, h, "max"), "PDL": prev_group(date_, l, "min"),
             "PWH": prev_group(wk, h, "max"), "PWL": prev_group(wk, l, "min")}
    asia_date = None
    for nm, col in (("AS", "in_asian"), ("LO", "in_london"), ("NY", "in_ny")):
        hi, lo, dt = last_completed_session(cal[col].to_numpy(bool), h, l, date_)
        pools[nm + "H"], pools[nm + "L"] = hi, lo
        if nm == "AS":
            asia_date = dt
    prev_e = lambda a: np.concatenate([[np.nan], np.asarray(a, float)[:-1]])       # the engine's level at the bar before
    pools["EQH"], pools["EQL"] = prev_e(eqh), prev_e(eql)
    g = pd.Series(date_)
    pools["CDH"] = pd.Series(h).groupby(g).cummax().groupby(g).shift(1).to_numpy(float)
    pools["CDL"] = pd.Series(l).groupby(g).cummin().groupby(g).shift(1).to_numpy(float)
    return pools, asia_date


def htf_trend(t_close15: np.ndarray, p: dict | None, sec: int) -> tuple[np.ndarray, np.ndarray]:
    """EMA20 above / below EMA100 on the last bar of that payload COMPLETED by each 15m close (False when unknown)."""
    n = len(t_close15)
    if not p or not p.get("chart") or not p["chart"].get("t"):
        return np.zeros(n, bool), np.zeros(n, bool)
    ch = p["chart"]
    done = np.asarray(ch["t"], np.int64) + sec
    e20, e100 = _num(ch["ema20"]), _num(ch["ema100"])
    k = np.searchsorted(done, t_close15, side="right") - 1
    kk = np.maximum(k, 0)
    ok = (k >= 0) & np.isfinite(e20[kk]) & np.isfinite(e100[kk])
    return ok & (e20[kk] > e100[kk]), ok & (e20[kk] < e100[kk])


def context(p15: dict, p1h: dict | None, p4h: dict | None) -> Ctx:
    ch = p15["chart"]
    X = Ctx()
    X.t = np.asarray(ch["t"], np.int64)
    n = len(X.t)
    X.o, X.h, X.l, X.c = (_num(ch[k]) for k in ("o", "h", "l", "c"))
    X.atr, X.aatr = _num(ch["atr"]), _num(ch["aatr"])
    X.vwap, X.lo2, X.up2 = _num(ch["vwap"]), _num(ch["vwap_lo2"]), _num(ch["vwap_up2"])
    X.ob_bull_hi, X.ob_bear_lo = _num(ch["ob_bull_hi"]), _num(ch["ob_bear_lo"])
    X.v = _num(ch["v"])
    X.ranging = np.isin(np.asarray(ch["regime"], object), RANGE_REGIMES)
    cal = sessions.calendar(pd.to_datetime(X.t, unit="s", utc=True))
    X.date = np.array([pd.Timestamp(x).date().isoformat() for x in cal["trading_date"]], object)
    X.sess = session_label(cal)
    X.cost = cost_model(cal)
    X.pools, X.asia_date = build_pools(X.h, X.l, cal, _num(ch["eqh"]), _num(ch["eql"]))
    X.up_any, X.dn_any, X.up_shift, X.dn_shift = (np.zeros(n, bool) for _ in range(4))
    pos = {int(t): i for i, t in enumerate(X.t)}
    for m in p15.get("markers") or []:
        i = pos.get(int(m.get("t", -1)))
        if i is None or m.get("type") not in ("BOS", "MSS", "CHoCH"):
            continue
        shift = m["type"] in ("MSS", "CHoCH")
        if m.get("dir") == 1:
            X.up_any[i] = True
            X.up_shift[i] |= shift
        elif m.get("dir") == -1:
            X.dn_any[i] = True
            X.dn_shift[i] |= shift
    t_close = X.t + BAR
    e1u, e1d = htf_trend(t_close, p1h, 3600)
    e4u, e4d = htf_trend(t_close, p4h, 14400)
    X.htf_up, X.htf_dn = e1u & e4u, e1d & e4d
    return X


# ---------------- detectors (B31, unchanged; distances in literal dollars) ----------------
def fvg_at(X: Ctx, i: int, d: int):
    """The engine's FVG rule at bar i in direction d: (zone low, zone high) or None."""
    if i < 2 or not np.isfinite(X.aatr[i]):
        return None
    if d == 1 and X.l[i] > X.h[i - 2] and X.l[i] - X.h[i - 2] > FVG_ATR * X.aatr[i]:
        return (X.h[i - 2], X.l[i])
    if d == -1 and X.h[i] < X.l[i - 2] and X.l[i - 2] - X.h[i] > FVG_ATR * X.aatr[i]:
        return (X.h[i], X.l[i - 2])
    return None


def crossings(X: Ctx, kinds: tuple) -> list[dict]:
    """Every first crossing of a pool level per trading day, REJECTED (a close back inside within 3 bars) or ACCEPTED
    (the 3 closes from the crossing all beyond); undecided at the end of the data until enough bars exist."""
    n, out, seen = len(X.c), [], set()
    for kind in kinds:
        P = X.pools[kind]
        side = -1 if kind in SELL_SIDE else 1
        for j in range(1, n):
            lv = P[j]
            if not np.isfinite(lv):
                continue
            if not (X.l[j] < lv - EPS if side == -1 else X.h[j] > lv + EPS):
                continue
            key = (kind, round(float(lv), 2), X.date[j])
            if key in seen:
                continue
            seen.add(key)
            back = [k for k in range(j, min(j + REJECT_BARS, n)) if (X.c[k] > lv if side == -1 else X.c[k] < lv)]
            if not back and j + REJECT_BARS > n:
                seen.discard(key)
                continue
            if back:
                k = back[0]
                ext = X.l[j:k + 1].min() if side == -1 else X.h[j:k + 1].max()
                out.append({"kind": kind, "j": j, "k": k, "lv": float(lv), "ext": float(ext), "status": "REJECTED",
                            "bars": k - j + 1, "dir": -side})
            else:
                a = j + REJECT_BARS - 1
                ext = X.l[j:a + 1].min() if side == 1 else X.h[j:a + 1].max()
                out.append({"kind": kind, "j": j, "k": a, "lv": float(lv), "ext": float(ext), "status": "ACCEPTED",
                            "bars": REJECT_BARS, "dir": side})
    return sorted(out, key=lambda e: (e["j"], e["kind"]))


def aligned(X: Ctx, i: int, d: int) -> bool:
    return bool(X.htf_up[i]) if d == 1 else bool(X.htf_dn[i])


def opposing_room(X: Ctx, i: int, d: int, e: float) -> float:
    names = ("PDH", "PWH", "ASH", "LOH", "NYH", "EQH", "CDH") if d == 1 else ("PDL", "PWL", "ASL", "LOL", "NYL", "EQL", "CDL")
    best = math.inf
    for nm in names:
        lv = X.pools[nm][i]
        if np.isfinite(lv) and (lv - e) * d > EPS:
            best = min(best, abs(lv - e))
    return best


def seq_sweep(X: Ctx, ev: dict, need: str) -> dict | None:
    d, j = ev["dir"], ev["j"]
    end = min(j + SHIFT_BARS, len(X.c) - 1)
    for m in range(ev["k"], end + 1):
        hit = (X.up_shift[m] if need == "A" else X.up_any[m]) if d == 1 else (X.dn_shift[m] if need == "A" else X.dn_any[m])
        if not hit:
            continue
        if aligned(X, m, d) != (need == "B"):
            return None
        zone, f_bar, etype = None, m, "OB"
        for f in range(j, min(m + 2, len(X.c) - 1) + 1):
            z = fvg_at(X, f, d)
            if z is not None:
                zone, f_bar, etype = z, f, "FVG"
                break
        if zone is not None:
            lim = zone[1] if d == 1 else zone[0]
        else:
            if m + 2 > len(X.c) - 1:
                return None
            lim = X.ob_bull_hi[m] if d == 1 else X.ob_bear_lo[m]
            if not np.isfinite(lim):
                return None
            f_bar = m + 2
        return {"order_bar": max(m, f_bar), "limit": float(lim), "stop": float(ev["ext"] - d * SL_BUF * X.atr[m]),
                "inval": ev["ext"], "entry_type": etype, "dir": d, "ev": ev, "struct_bar": m}
    return None


def seq_break(X: Ctx, ev: dict) -> dict | None:
    d, j, a = ev["dir"], ev["j"], ev["k"]
    if not any(fvg_at(X, f, d) is not None for f in range(j, a + 1)):
        return None
    leg = min(ev["ext"], ev["lv"]) if d == 1 else max(ev["ext"], ev["lv"])
    return {"order_bar": a, "limit": ev["lv"], "stop": float(leg - d * SL_BUF * X.atr[a]), "inval": None,
            "entry_type": "RETEST", "dir": d, "ev": ev, "false_break_level": ev["lv"], "struct_bar": j}


def setups(X: Ctx, mod: str, evs: list[dict]) -> list[dict]:
    out = []
    if mod in ("A", "B"):
        out = [s for s in (seq_sweep(X, ev, mod) for ev in evs if ev["status"] == "REJECTED") if s]
    elif mod == "C":
        out = [s for s in (seq_break(X, ev) for ev in evs if ev["status"] == "ACCEPTED") if s]
    elif mod == "E":
        first = {}
        for ev in evs:
            if ev["kind"] in ("ASH", "ASL") and X.sess[ev["j"]] in ("LONDON", "NEW YORK", "LONDON+NY") \
                    and X.asia_date[ev["j"]] == X.date[ev["j"]] and X.date[ev["j"]] not in first:
                first[X.date[ev["j"]]] = ev
        for ev in first.values():
            s = ((seq_sweep(X, ev, "A") or seq_sweep(X, ev, "B")) if ev["status"] == "REJECTED" else seq_break(X, ev))
            if s:
                out.append(s)
    elif mod == "D":
        n = len(X.c)
        for j in range(1, n):
            if not X.ranging[j]:
                continue
            for d in (1, -1):
                dev = X.l[j] <= X.lo2[j] if d == 1 else X.h[j] >= X.up2[j]
                if not dev or (X.l[j - 1] <= X.lo2[j - 1] if d == 1 else X.h[j - 1] >= X.up2[j - 1]):
                    continue
                ks = [k for k in range(j, min(j + REJECT_BARS, n)) if (X.c[k] > X.lo2[k] if d == 1 else X.c[k] < X.up2[k])]
                if not ks:
                    continue
                k = ks[0]
                if ((X.o[j:k + 1] - X.c[j:k + 1]) * d >= DISP_BODY * X.atr[j:k + 1]).any():
                    continue
                ext = X.l[j:k + 1].min() if d == 1 else X.h[j:k + 1].max()
                out.append({"order_bar": k, "limit": None, "market": float(X.c[k]), "stop": float(ext - d * SL_BUF * X.atr[k]),
                            "inval": None, "entry_type": "MARKET", "dir": d, "struct_bar": j,
                            "ev": {"kind": "VWAP", "j": j, "k": k, "bars": k - j + 1, "lv": float(X.lo2[j] if d == 1 else X.up2[j])},
                            "vwap": float(X.vwap[k])})
    return sorted(out, key=lambda s: s["order_bar"])


def check(X: Ctx, s: dict, e: float, i: int, cost: float) -> str | None:
    """B31's checks with the operator's option (a): net R:R on the ladder (mean target $15), not on TP1 alone."""
    d = s["dir"]
    D = (e - s["stop"]) * d
    if not np.isfinite(D) or D <= 0:
        return "stop on the wrong side"
    if D < D_MIN - EPS:
        return "stop"
    if (LADDER - cost) / (D + cost) < RR_MIN - EPS:
        return "reward"
    if cost > COST_FRAC * D + EPS:
        return "cost"
    if opposing_room(X, i, d, e) < TP[0] - EPS:
        return "room"
    if s.get("vwap") is not None and (s["vwap"] - e) * d < TP[0] - EPS:
        return "room"
    return None


# ---------------- outcomes (B31's race; OPEN while the data has not decided) ----------------
def race(X: Ctx, b0: int, d: int, stop: float, tgt: float) -> tuple[str, int | None, float | None]:
    n = len(X.c)
    for b in range(b0, min(b0 + HOLD, n)):
        o, h, l = X.o[b], X.h[b], X.l[b]
        if (o - stop) * d <= 0:
            return "SL", b, o
        if (o - tgt) * d >= 0:
            return "TP", b, o
        hs = (l <= stop) if d == 1 else (h >= stop)
        ht = (h >= tgt) if d == 1 else (l <= tgt)
        if hs and ht:
            return "AMBIGUOUS", b, stop
        if hs:
            return "SL", b, stop
        if ht:
            return "TP", b, tgt
    if b0 + HOLD > n:
        return "OPEN", None, None
    return "TIMEOUT", b0 + HOLD - 1, X.c[b0 + HOLD - 1]


def thirds(X: Ctx, b0: int, d: int, e: float, stop: float) -> float | None:
    """Thirds at +10 / +15 / +20, the stop moved to the entry after TP1: $ per oz before cost (None while OPEN)."""
    st, got, b = stop, [], b0
    for t in (e + d * x for x in TP):
        r, b, px = race(X, b, d, st, t)
        if r == "OPEN":
            return None
        if r == "TP":
            got.append((t - e) * d)
            st, b = e, b + 1
        else:
            got += [(px - e) * d] * (3 - len(got))
            break
    return float(np.mean(got))


def side(X: Ctx, fill_bar: int, first: int, d: int, e: float, D: float, limit: bool) -> dict | None:
    """One direction's outcome from the fill: TP1 / TP2 / TP3 races, the thirds plan, MFE / MAE (None while OPEN)."""
    stop = e - d * D
    if limit and ((X.l[fill_bar] <= stop) if d == 1 else (X.h[fill_bar] >= stop)):   # the fill bar can only stop
        return {"out": ["SL"] * 3, "exit": fill_bar, "px1": stop, "th": -D, "mfe": 0.0, "mae": D, "bars1": 0}
    res = [race(X, first, d, stop, e + d * x) for x in TP]
    if any(r[0] == "OPEN" for r in res):
        return None
    th = thirds(X, first, d, e, stop)
    if th is None:
        return None
    exit_ = res[0][1]
    seg = slice(first, exit_ + 1)
    mfe = max(float(((X.h[seg] - e) if d == 1 else (e - X.l[seg])).max()), 0.0) if exit_ >= first else 0.0
    mae = max(float(((e - X.l[seg]) if d == 1 else (X.h[seg] - e)).max()), 0.0) if exit_ >= first else D
    return {"out": [r[0] for r in res], "exit": exit_, "px1": res[0][2], "th": th, "mfe": mfe, "mae": mae,
            "bars1": exit_ - fill_bar}


# ---------------- the forward record ----------------
def load(store_dir: str | None) -> dict:
    path = os.path.join(store_dir, DIR, FILE) if store_dir else None
    if path and os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"id": ID, "registration": REG, "started_utc": None, "setups": [], "days": [], "verdicts": {}}


def save(store_dir: str | None, book: dict) -> None:
    if not store_dir:
        return
    path = os.path.join(store_dir, DIR, FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump(book, f, indent=0)
    os.replace(tmp, path)


def _vol_ratio(X: Ctx, i: int) -> float | None:
    prev = X.v[max(0, i - 20):i]
    prev = prev[np.isfinite(prev)]
    if len(prev) < 20 or prev.mean() <= 0 or not np.isfinite(X.v[i]):
        return None
    return round(float(X.v[i] / prev.mean()), 3)


def record_new(X: Ctx, book: dict, now_t: int) -> None:
    """Append every setup decided since the start that is not yet recorded; REPEAT and the checks are applied at once."""
    started = book["started_utc"]
    evs = crossings(X, SELL_SIDE + BUY_SIDE)
    found = sorted(((mod, s) for mod in MODULES for s in setups(X, mod, evs)), key=lambda x: (x[1]["order_bar"], x[0]))
    recs = book["setups"]
    keys = {r["key"] for r in recs}
    for mod, s in found:
        ob = s["order_bar"]
        t_o = int(X.t[ob])
        if t_o + BAR < started:
            continue
        p_ref = s["limit"] if s.get("limit") is not None else s["market"]
        ev = s["ev"]
        key = f"{mod}|{t_o}|{s['dir']}|{ev['kind']}|{round(float(ev.get('lv', p_ref)), 2)}"
        if key in keys:
            continue
        rec = {"key": key, "module": mod, "dir": s["dir"], "kind": ev["kind"], "lv": round(float(ev.get("lv", p_ref)), 2),
               "order_t": t_o, "order_close": t_o + BAR, "recorded_utc": now_t,
               "timely": now_t - (t_o + BAR) <= TIMELY_SEC, "entry_type": s["entry_type"],
               "limit": s.get("limit"), "market": s.get("market"), "p_ref": float(p_ref), "stop": float(s["stop"]),
               "inval": s.get("inval"), "false_break": s.get("false_break_level") is not None, "vwap": s.get("vwap"),
               "session": str(X.sess[ob]), "ranging": bool(X.ranging[ob]), "vol_ratio": _vol_ratio(X, s["struct_bar"]),
               "cost": float(X.cost[ob]), "status": "PENDING"}
        kept = [r for r in recs if r["module"] == mod and r["status"] != "REPEAT"]
        if any(r["dir"] == rec["dir"] and rec["order_t"] - r["order_t"] <= REPEAT_SEC and abs(rec["p_ref"] - r["p_ref"]) <= REPEAT_USD
               for r in kept[-50:]):
            rec["status"] = "REPEAT"
        else:
            why = check(X, s, rec["p_ref"], ob, rec["cost"])
            if why:
                rec["status"], rec["why"] = "REJECTED", why
        recs.append(rec)
        keys.add(key)


def follow(X: Ctx, rec: dict, busy: list[tuple[int, int | None]]) -> None:
    """Advance one PENDING / OPEN record on the current data; final states are written once and never revisited."""
    pos = np.searchsorted(X.t, rec["order_t"])
    if pos >= len(X.t) or X.t[pos] != rec["order_t"]:
        rec["status"] = "LOST"                    # the order bar left the window (or was revised away) before a decision
        return
    i0, d, n = int(pos), rec["dir"], len(X.t)
    limit = rec["limit"] is not None
    if not limit:
        fill_bar, e, first = i0, float(rec["market"]), i0 + 1
    else:
        fill_bar = e = None
        for b in range(i0 + 1, i0 + 1 + LIMIT_BARS):
            if b >= n:
                return                             # still waiting for the bars that decide the order
            o = X.o[b]
            if rec["inval"] is not None and (o - rec["inval"]) * d < 0:
                rec["status"] = "INVALIDATED"
                return
            if rec["false_break"] and (o - rec["limit"]) * d < 0:
                rec["status"] = "FALSE_BREAKOUT"
                return
            if (X.l[b] <= rec["limit"]) if d == 1 else (X.h[b] >= rec["limit"]):
                fill_bar, e = b, (min(o, rec["limit"]) if d == 1 else max(o, rec["limit"]))
                break
            if rec["inval"] is not None and ((X.l[b] < rec["inval"]) if d == 1 else (X.h[b] > rec["inval"])):
                rec["status"] = "INVALIDATED"
                return
            if rec["inval"] is not None and (X.dn_any[b] if d == 1 else X.up_any[b]):
                rec["status"] = "INVALIDATED"
                return
        else:
            rec["status"] = "MISSED"
            return
        first = fill_bar + 1
    fill_t = int(X.t[fill_bar]) + (0 if limit else BAR)
    fill_bar_t = int(X.t[fill_bar])
    if any(f <= fill_bar_t and (x is None or x >= fill_bar_t) for f, x in busy):     # B31: fill_bar <= the busy exit bar
        rec["status"] = "OVERLAP"                  # the module's previous trade was still open: one position at a time
        return
    D = (e - rec["stop"]) * d
    own = side(X, fill_bar, first, d, e, D, limit)
    mir = side(X, fill_bar, first, -d, e, D, limit)
    rec.update({"status": "OPEN", "fill_t": fill_t, "fill_bar_t": fill_bar_t, "day": str(X.date[fill_bar]),
                "entry": round(e, 2), "D": round(D, 2),
                "lots": round(RISK_USD / (OZ * (D + rec["cost"])), 3)})
    if own is None or mir is None:
        return
    c = rec["cost"]
    r = lambda th, cost: (th - cost) / (D + cost)
    rec.update({"status": "DONE", "out": own["out"], "exit_t": int(X.t[own["exit"]]) + BAR, "exit_bar_t": int(X.t[own["exit"]]),
                "r1": round(((own["px1"] - e) * d - c) / (D + c), 4), "ladder_r": round(r(own["th"], c), 4),
                "ladder_usd": round(r(own["th"], c) * RISK_USD, 2), "ladder_r_op": round(r(own["th"], OP_COST), 4),
                "mfe": round(own["mfe"], 2), "mae": round(own["mae"], 2),
                "min_to_tp1": own["bars1"] * 15 if own["out"][0] == "TP" else None,
                "mirror": {"out": mir["out"], "ladder_r": round(r(mir["th"], c), 4)}})


def update(book: dict, X: Ctx, now_t: int) -> None:
    if book.get("started_utc") is None:
        book["started_utc"] = int(now_t)          # the first run with this code: nothing before it is ever scored
    record_new(X, book, now_t)
    for mod in MODULES:
        busy, blocked = [], False
        for rec in sorted((r for r in book["setups"] if r["module"] == mod), key=lambda r: r["order_t"]):
            if rec["status"] in ("PENDING", "OPEN") and not blocked:
                follow(X, rec, busy)
            blocked = blocked or rec["status"] == "PENDING"   # an earlier undecided order has priority (B31's order)
            if rec.get("fill_bar_t") is not None and rec["status"] in ("OPEN", "DONE"):
                busy.append((rec["fill_bar_t"], rec.get("exit_bar_t")))
    seen = set(book.get("days") or [])
    seen.update(str(x) for x in X.date[X.t + BAR >= book["started_utc"]])
    book["days"] = sorted(seen)


# ---------------- statistics (no random numbers) ----------------
def wilson(k: int, n: int) -> list[float] | None:
    if n == 0:
        return None
    z, p = 1.96, k / n
    den = 1 + z * z / n
    mid, half = (p + z * z / (2 * n)) / den, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(max(0.0, mid - half), 4), round(min(1.0, mid + half), 4)]


_T975 = (12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145, 2.131, 2.120,
         2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042)


def t975(df: int) -> float:
    return _T975[df - 1] if df <= 30 else 1.96 + 2.372 / df      # Cornish-Fisher beyond the table (2.042 at 30)


def day_ci(trades: list[dict]) -> list[float] | None:
    """95% t-interval of the mean ladder R over trading-day means (trades on one day are not independent)."""
    by: dict = {}
    for x in trades:
        by.setdefault(x["day"], []).append(x["ladder_r"])
    m = np.array([np.mean(v) for v in by.values()], float)
    if len(m) < 2:
        return None
    half = t975(len(m) - 1) * m.std(ddof=1) / math.sqrt(len(m))
    return [round(float(m.mean() - half), 4), round(float(m.mean() + half), 4)]


def sign_p(wins: int, losses: int) -> float:
    """One-sided exact sign test: P(X >= wins) with X ~ Binomial(wins + losses, 1/2)."""
    n = wins + losses
    if n == 0:
        return 1.0
    return float(sum(math.comb(n, k) for k in range(wins, n + 1)) / 2 ** n)


def unit_trades(book: dict, unit: str) -> list[dict]:
    """Timely DONE trades of a unit in the order they were decided; ALL = A-E pooled, a (time, direction) entry once."""
    tr = [r for r in book["setups"] if r["status"] == "DONE" and r["timely"] and (unit == "ALL" or r["module"] == unit)]
    tr.sort(key=lambda r: (r["exit_t"], r["fill_t"], r["module"]))
    if unit == "ALL":
        seen, out = set(), []
        for r in tr:
            if (r["fill_t"], r["dir"]) not in seen:
                seen.add((r["fill_t"], r["dir"]))
                out.append(r)
        tr = out
    return tr


def stats(tr: list[dict]) -> dict:
    n = len(tr)
    hit = [sum(r["out"][k] == "TP" for r in tr) for k in range(3)]
    mir = sum(r["mirror"]["out"][0] == "TP" for r in tr)
    wins = sum(r["out"][0] == "TP" and r["mirror"]["out"][0] != "TP" for r in tr)
    losses = sum(r["mirror"]["out"][0] == "TP" and r["out"][0] != "TP" for r in tr)
    lr = [r["ladder_r"] for r in tr]
    return {"n": n, "tp": hit, "tp_rate": [h / n if n else None for h in hit], "tp1_wilson": wilson(hit[0], n),
            "control_tp1_rate": (hit[0] + mir) / (2 * n) if n else None, "discordant": [wins, losses],
            "sign_p": sign_p(wins, losses), "ladder_r": float(np.mean(lr)) if n else None,
            "ladder_usd": float(np.mean(lr)) * RISK_USD if n else None,
            "ladder_r_op": float(np.mean([r["ladder_r_op"] for r in tr])) if n else None,
            "day_ci": day_ci(tr) if n else None, "ambiguous": sum(r["out"][0] == "AMBIGUOUS" for r in tr),
            "mfe": float(np.median([r["mfe"] for r in tr])) if n else None,
            "mae": float(np.median([r["mae"] for r in tr])) if n else None}


def verdicts(book: dict, now_t: int) -> dict:
    """The registered look: once, at a unit's first 100 decided timely trades. SUPPORTED needs the day-mean ladder R
    interval above 0 and the sign test below the Holm threshold over the 6 units; while Holm depends on units that have
    not looked yet, the unit reads HOLM PENDING (p between 0.05 / 6 and 0.05). After the deadline, units without 100
    trades are INSUFFICIENT and count as p = 1."""
    V = book.setdefault("verdicts", {})
    for u in UNITS:
        if u in V:
            continue
        tr = unit_trades(book, u)
        if len(tr) >= LOOK:
            s = stats(tr[:LOOK])
            V[u] = {"at_n": LOOK, "utc": int(now_t), "p": s["sign_p"], "ci": s["day_ci"],
                    "ci_ok": bool(s["day_ci"] and s["day_ci"][0] > 0)}
    past = datetime.fromtimestamp(now_t, timezone.utc).date() > date.fromisoformat(DEADLINE)
    ps = {u: (V[u]["p"] if u in V else (1.0 if past else None)) for u in UNITS}
    known = sorted((p, u) for u, p in ps.items() if p is not None)
    out = {}
    holm_ok, stopped = {}, False
    if len(known) == len(UNITS):
        for rank, (p, u) in enumerate(known):
            stopped = stopped or p >= ALPHA / (len(UNITS) - rank)
            holm_ok[u] = not stopped
    for u in UNITS:
        if u not in V:
            out[u] = "INSUFFICIENT" if past else "COLLECTING"
        elif not V[u]["ci_ok"] or V[u]["p"] >= ALPHA:
            out[u] = "NOT SUPPORTED"
        elif u in holm_ok:
            out[u] = "SUPPORTED" if holm_ok[u] else "NOT SUPPORTED"
        else:
            out[u] = "SUPPORTED" if V[u]["p"] < ALPHA / len(UNITS) else "HOLM PENDING"
    return out


def summary(book: dict, now_t: int) -> dict:
    v = verdicts(book, now_t)
    days = max(len(book.get("days") or []), 1)
    units = {}
    for u in UNITS:
        rs = [r for r in book["setups"] if u == "ALL" or r["module"] == u]
        by: dict = {}
        for r in rs:
            by[r["status"]] = by.get(r["status"], 0) + 1
        why: dict = {}
        for r in rs:
            if r["status"] == "REJECTED":
                why[r["why"]] = why.get(r["why"], 0) + 1
        units[u] = {"verdict": v[u], "setups": len(rs), "per_day": round(len(rs) / days, 2), "by_status": by, "rejected": why,
                    "late": sum(1 for r in rs if not r["timely"]), **stats(unit_trades(book, u))}
    recent = [{k: r.get(k) for k in ("module", "dir", "kind", "order_t", "status", "why", "entry", "D", "out", "ladder_usd",
                                       "timely")} for r in sorted(book["setups"], key=lambda r: r["order_t"])[-12:]][::-1]
    return {"id": ID, "registration": REG, "started_utc": book["started_utc"], "trading_days": len(book.get("days") or []),
            "look": LOOK, "deadline": DEADLINE, "units": units, "recent": recent, "verdicts": book.get("verdicts", {})}


def run(store_dir: str | None, payloads: dict, now_t: int) -> dict:
    """One site run: rebuild the context from this run's payloads, record and follow setups, save, summarise."""
    p15 = payloads.get("15m")
    if not p15 or (p15.get("meta") or {}).get("synthetic") or "regime" not in (p15.get("chart") or {}):
        return {"id": ID, "registration": REG, "status": "no live 15m payload with the engine rows this test reads"}
    X = context(p15, payloads.get("1h"), payloads.get("4h"))
    book = load(store_dir)
    update(book, X, int(now_t))
    verdicts(book, int(now_t))                     # the registered look is frozen in the record before it is saved
    save(store_dir, book)
    return summary(book, int(now_t))
