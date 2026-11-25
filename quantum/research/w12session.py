"""B31b-W12 (research only; production never imports this module): session-boundary liquidity sweeps.

research/registrations/B31b-W12.json fixes every rule before this code; this file implements it.

  events     the production sweep detector (quantum/sweeps.detect) on the M15 bars, M30 levels from pairs of 15m bars,
             H1 / H4 levels from the 1h bars (H4 on the 17:00 New York grid, as production builds it)
  pattern    H1 = the sweep bar closes within 60 min of a session boundary (Asia open 00:00 UTC, London open 08:00
             London, New York open 08:30 New York, London close 16:30 London, New York close 17:00 New York) AND the
             run into it, (sweep-bar extreme - close 4 bars earlier) x side, is at least 1.0 x ATR14 of the bar before
  entry      market at the sweep close in the reversal direction, stop at the wick, +$10 / +$15 / +$20 ($ at $4,000),
             raced on M5 (M15 where the M5 bar is missing), both-in-one-bar = stop, gap fills at the open, 24 h time stop
  confirm    C1 H1 EMA20 vs EMA50 agrees; C2 the previous trading day's time-at-price POC is on the reversal side;
             C3 EUR/USD over the same 4 bars moved the reversal's way (dollar did not confirm the run)
  tests      5 candidates (H1, H1+C1, H1+C2, H1+C3, H1+ALL) vs R1 (20 random M15 closes in the 16 bars after), Holm

Development partition only: main() refuses any other.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .. import sessions, sweeps, ta
from ..data import sources
from . import harness as H
from . import history
from . import w3liq as W

REG = "B31b-W12"
WINDOW = 3600
RUN_BARS, RUN_ATR = 4, 1.0
EMA_F, EMA_S = 20, 50
POC_BIN = 0.50                       # $ at $4,000
TP = (10.0, 15.0, 20.0)
HOLD_SEC = 96 * 900
R1_N, R1_BARS = 20, 16
BOOT = 2000
MIN_DECIDED = 100
EU_COVERAGE = 0.95
LON, NY = ZoneInfo("Europe/London"), ZoneInfo("America/New_York")
BOUNDS = (("ASIA_OPEN", timezone.utc, 0, 0), ("LONDON_OPEN", LON, 8, 0), ("NY_OPEN", NY, 8, 30),
          ("LONDON_CLOSE", LON, 16, 30), ("NY_CLOSE", NY, 17, 0))
CANDIDATES = ("H1", "H1+C1", "H1+C2", "H1+C3", "H1+ALL")


# ---------------- the pattern ----------------
def nearest_boundary(t: int) -> tuple[str, float]:
    """The session boundary nearest to epoch second t (any of the 5, on the day before, of or after t's UTC date):
    (name, minutes from the boundary to t, negative = before the boundary)."""
    d0 = datetime.fromtimestamp(t, timezone.utc).date()
    best = (None, math.inf)
    for dd in (-1, 0, 1):
        d = d0 + pd.Timedelta(days=dd)
        for name, tz, hh, mm in BOUNDS:
            b = datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz).timestamp()
            if abs(t - b) < abs(best[1]):
                best = (name, t - b)
    return best[0], best[1] / 60.0


def pre_run(h, l, c, atr, k: int, side: int) -> float:
    """The run into the sweep bar k in ATR: (its extreme - the close RUN_BARS bars earlier) x side / ATR[k-1]."""
    if k - RUN_BARS < 0 or not np.isfinite(atr[k - 1]) or atr[k - 1] <= 0:
        return math.nan
    ext = h[k] if side == 1 else l[k]
    return float((ext - c[k - RUN_BARS]) * side / atr[k - 1])


def trend_agrees(th: np.ndarray, e20: np.ndarray, e50: np.ndarray, t_close: int, d: int) -> bool:
    """C1: on the last H1 bar CLOSED by t_close (open + 3600 <= t_close), EMA20 vs EMA50 points the reversal's way."""
    j = int(np.searchsorted(th + 3600, t_close, side="right")) - 1
    return bool(j >= EMA_S and np.isfinite(e20[j]) and np.isfinite(e50[j]) and np.sign(e20[j] - e50[j]) == d)


def tpo_poc(lo: np.ndarray, hi: np.ndarray, bin_usd: float) -> float:
    """Time-at-price POC: each bar's range spread equally over the bins it covers; the mid of the fullest bin (the
    lowest such bin on a tie)."""
    if not len(lo):
        return math.nan
    base = math.floor(float(np.min(lo)) / bin_usd)
    top = math.floor(float(np.max(hi)) / bin_usd)
    acc = np.zeros(top - base + 1)
    for a, b in zip(lo, hi):
        i0, i1 = math.floor(a / bin_usd) - base, math.floor(b / bin_usd) - base
        acc[i0:i1 + 1] += 1.0 / (i1 - i0 + 1)
    return (base + int(np.argmax(acc)) + 0.5) * bin_usd


def daily_pocs(m15: pd.DataFrame) -> tuple[np.ndarray, dict]:
    """Each M15 bar's trading date, and {trading date: POC} from that date's bars ($0.50-at-$4,000 bins)."""
    cal = sessions.calendar(m15.index)
    td = cal["trading_date"].to_numpy()
    out = {}
    lo, hi, c = (m15[k].to_numpy(float) for k in ("low", "high", "close"))
    for d in pd.unique(td):
        m = td == d
        out[d] = tpo_poc(lo[m], hi[m], POC_BIN * float(np.mean(c[m])) / 4000.0)
    return td, out


# ---------------- the race ----------------
def fine_path(m15: pd.DataFrame, m5: pd.DataFrame | None) -> dict:
    """M5 bars where all three of a 15m bar's M5 bars exist, else the M15 bar: open time, o, h, l, c (time-sorted)."""
    t15 = ta.epoch_s(m15.index).astype(np.int64)
    parts = []
    full = set()
    if m5 is not None and len(m5):
        t5 = ta.epoch_s(m5.index).astype(np.int64)
        key = t5 - t5 % 900
        u, cnt = np.unique(key, return_counts=True)
        full = set(u[cnt == 3].tolist())
        keep = np.isin(key, list(full))
        parts.append(pd.DataFrame({"t": t5[keep], **{k: m5[col].to_numpy(float)[keep] for k, col in
                                                      (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close"))}}))
    miss = ~np.isin(t15, list(full))
    parts.append(pd.DataFrame({"t": t15[miss], **{k: m15[col].to_numpy(float)[miss] for k, col in
                                                   (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close"))}}))
    df = pd.concat(parts).sort_values("t", kind="stable")
    return {k: df[k].to_numpy() for k in ("t", "o", "h", "l", "c")}


def race(fp: dict, t0: int, entry: float, stop: float, d: int, targets: tuple) -> list[tuple]:
    """Each target raced against the stop on the fine path from t0 (the entry bar's close) for 24 h. Returns per target
    ("TP", t) / ("SL", t, fill) / ("TO", t, exit close) / ("NONE",) when no bar follows."""
    i0 = int(np.searchsorted(fp["t"], t0, side="left"))
    i1 = int(np.searchsorted(fp["t"], t0 + HOLD_SEC, side="left"))
    if i1 <= i0:
        return [("NONE",)] * len(targets)
    o, h, l, c, t = (fp[k][i0:i1] for k in ("o", "h", "l", "c", "t"))
    hit_s = (l <= stop) if d == 1 else (h >= stop)
    ks = int(np.argmax(hit_s)) if hit_s.any() else None
    out = []
    for tg in targets:
        hit_t = (h >= tg) if d == 1 else (l <= tg)
        kt = int(np.argmax(hit_t)) if hit_t.any() else None
        if ks is not None and (kt is None or ks <= kt):
            gap = (o[ks] < stop) if d == 1 else (o[ks] > stop)
            out.append(("SL", int(t[ks]), float(o[ks] if gap else stop)))
        elif kt is not None:
            out.append(("TP", int(t[kt])))
        else:
            out.append(("TO", int(t[-1]), float(c[-1])))
    return out


def net_r(res: tuple, T: float, entry: float, D: float, cost: float, d: int) -> float:
    """Net R with D and T in $ at $4,000 and the cost in today's $ per oz (the B31b-W3 convention)."""
    s = entry / 4000.0
    if res[0] == "TP":
        return (T - cost) / (D + cost)
    if res[0] == "SL":
        return -(abs(entry - res[2]) / s + cost) / (D + cost)
    if res[0] == "TO":
        return ((res[2] - entry) * d / s - cost) / (D + cost)
    return math.nan


def trade(fp: dict, t0: int, entry: float, D: float, d: int, cost: float) -> dict:
    """A market entry at `entry` (bar close t0), stop D ($ at $4,000) away, all three targets."""
    s = entry / 4000.0
    stop = entry - d * D * s
    res = race(fp, t0, entry, stop, d, tuple(entry + d * T * s for T in TP))
    r = {"t0": t0, "entry": entry, "stop": stop, "D": D, "cost": cost}
    for T, x in zip(TP, res):
        k = f"tp{int(T)}"
        r[k] = x[0]
        r[k + "_r"] = net_r(x, T, entry, D, cost, d)
    return r


# ---------------- statistics ----------------
def boot_mean(x: np.ndarray, days: np.ndarray, seed: int = 12) -> tuple[float, list[float], float]:
    """Mean, its day-clustered bootstrap 95% interval and the one-sided p of mean <= 0."""
    x, days = np.asarray(x, float), np.asarray(days)
    ok = np.isfinite(x)
    x, days = x[ok], days[ok]
    if not len(x):
        return math.nan, [math.nan, math.nan], math.nan
    u, inv = np.unique(days, return_inverse=True)
    sums, cnts = np.bincount(inv, weights=x), np.bincount(inv)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(u), size=(BOOT, len(u)))
    bm = sums[pick].sum(1) / cnts[pick].sum(1)
    return float(x.mean()), [float(np.percentile(bm, 2.5)), float(np.percentile(bm, 97.5))], float((bm <= 0).mean())


def boot_two(x1, d1, x0, d0, seed: int = 13) -> tuple[float, list[float], float]:
    """Difference of means (group 1 - group 0), day-clustered within each group: mean, 95% interval, one-sided p."""
    x1, x0 = np.asarray(x1, float), np.asarray(x0, float)
    if not len(x1) or not len(x0):
        return math.nan, [math.nan, math.nan], math.nan
    rng = np.random.default_rng(seed)

    def draws(x, d):
        u, inv = np.unique(d, return_inverse=True)
        s, n = np.bincount(inv, weights=x), np.bincount(inv)
        p = rng.integers(0, len(u), size=(BOOT, len(u)))
        return s[p].sum(1) / n[p].sum(1)
    bm = draws(x1, np.asarray(d1)) - draws(x0, np.asarray(d0))
    return float(x1.mean() - x0.mean()), [float(np.percentile(bm, 2.5)), float(np.percentile(bm, 97.5))], float((bm <= 0).mean())


def holm(ps: dict) -> dict:
    items = sorted((p, k) for k, p in ps.items() if p is not None and np.isfinite(p))
    m, out, run = len(items), {}, 0.0
    for r, (p, k) in enumerate(items):
        run = max(run, min(1.0, (m - r) * p))
        out[k] = run
    return out


def summary(rows: list[dict]) -> dict:
    out = {"n": len(rows)}
    if not rows:
        return out
    days = np.array([r["t0"] // 86400 for r in rows])
    for T in TP:
        k = f"tp{int(T)}"
        dec = [r for r in rows if r[k] in ("TP", "SL")]
        kk = sum(r[k] == "TP" for r in dec)
        mr, ci, _ = boot_mean(np.array([r[k + "_r"] for r in rows]), days)
        out[k] = {"decided": len(dec), "timeouts": sum(r[k] == "TO" for r in rows), "tp_first": kk / len(dec) if dec else math.nan,
                  "wilson95": list(H.wilson(kk, len(dec))), "break_even": float(np.mean([(r["D"] + r["cost"]) / (T + r["D"]) for r in rows])),
                  "mean_net_r": mr, "mean_net_r_day95": ci, "usd_per_trade": mr * 650.0}
    out["gap_losses_over_650"] = sum(r["tp10"] == "SL" and r["tp10_r"] < -1.0 - 1e-9 for r in rows)
    out["worst_loss_usd"] = float(-650.0 * np.nanmin([r["tp10_r"] for r in rows]))
    return out


# ---------------- a run ----------------
def load_cost(path: str) -> dict:
    with open(path) as f:
        c = json.load(f)
    assert c.get("registration") == "B31b-W8" and c.get("per_session_usd_oz"), "the B31b-W8 decision-cost file"
    return c["per_session_usd_oz"]


def bars(df: pd.DataFrame) -> dict:
    return {"t": ta.epoch_s(df.index).astype(np.int64), **{k: df[c].to_numpy(float) for k, c in
                                                          (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close"))}}


def build(m15: pd.DataFrame, h1: pd.DataFrame, m5: pd.DataFrame | None, eu: pd.DataFrame | None, score_from: int,
          cost_map: dict, seed: int = 12) -> dict:
    b15 = bars(m15)
    m30, _ = W.make_m30(m15)
    h4 = sources.resample_ny_session(h1, 4)
    higher = {"30m": bars(m30), "1h": bars(h1), "4h": bars(h4)}
    evs = [e for e in sweeps.detect(b15, higher) if e["t"] >= score_from]
    t, h, l, c = b15["t"], b15["h"], b15["l"], b15["c"]
    atr = np.asarray(ta.atr(h, l, c, 14), float)
    th = ta.epoch_s(h1.index).astype(np.int64)
    e20, e50 = np.asarray(ta.ema(h1["close"].to_numpy(float), EMA_F)), np.asarray(ta.ema(h1["close"].to_numpy(float), EMA_S))
    td, pocs = daily_pocs(m15)
    dates = sorted(pocs)
    prev_date = {d: (dates[i - 1] if i else None) for i, d in enumerate(dates)}
    eu_c = None
    cover = 0.0
    if eu is not None and len(eu):
        eu_c = pd.Series(eu["close"].to_numpy(float), index=ta.epoch_s(eu.index).astype(np.int64))
        eu_c = eu_c[~eu_c.index.duplicated(keep="last")]
        dev = t[t >= score_from]
        cover = float(np.isin(dev, eu_c.index.to_numpy()).mean()) if len(dev) else 0.0
    sess_of = W.sess_bucket(sessions.calendar(pd.DatetimeIndex(pd.to_datetime(t + 900, unit="s", utc=True))))
    fp = fine_path(m15, m5)
    rows = []
    for e in evs:
        k, side, d = e["i"], e["side"], e["dir"]
        bname, mins = nearest_boundary(int(e["t_close"]))
        run = pre_run(h, l, c, atr, k, side)
        c1 = trend_agrees(th, e20, e50, int(e["t_close"]), d)
        pd_ = prev_date.get(td[k])
        poc = pocs.get(pd_) if pd_ is not None else math.nan
        c2 = bool(np.isfinite(poc) and (poc - c[k]) * d > 0)
        c3 = None
        if eu_c is not None and k >= RUN_BARS and t[k] in eu_c.index and t[k - RUN_BARS] in eu_c.index:
            ch = float(eu_c[t[k]] - eu_c[t[k - RUN_BARS]])
            c3 = bool(ch != 0 and np.sign(ch) == d)
        entry = float(c[k])
        ext = float(h[k] if side == 1 else l[k])                  # the wick's extreme (unrounded)
        D = abs(entry - ext) / (entry / 4000.0)
        if D <= 0:
            continue
        cost = float(cost_map[str(sess_of[k])])
        r = trade(fp, int(e["t_close"]), entry, D, d, cost)
        r.update(id=e["id"], k=k, side=side, d=d, ref=e["ref"], ref_kind=e["ref_kind"], ref_tf=e["ref_tf"], sess=str(sess_of[k]),
                 boundary=bname, min_to_boundary=round(mins, 1), in_window=bool(abs(mins) * 60 <= WINDOW), run_atr=run,
                 run_ok=bool(np.isfinite(run) and run >= RUN_ATR), c1=c1, c2=c2, c3=c3, poc_prev=poc)
        r["H1"] = r["in_window"] and r["run_ok"]
        rng = np.random.default_rng(int(hashlib.sha256(e["id"].encode()).hexdigest()[:8], 16) ^ seed)
        js = k + rng.integers(1, R1_BARS + 1, size=R1_N)
        rr = [trade(fp, int(t[q]) + 900, float(c[q]), D, d, cost) for q in js if q < len(c)]
        dec = [x for x in rr if x["tp10"] in ("TP", "SL")]
        r["r1_rate10"] = float(np.mean([x["tp10"] == "TP" for x in dec])) if dec else math.nan
        r["r1_net10"] = float(np.nanmean([x["tp10_r"] for x in rr])) if rr else math.nan
        rows.append(r)
    return {"rows": rows, "events": len(evs), "eu_coverage": cover, "score_from": score_from, "t_end": int(t[-1]) + 900}


def select(rows: list[dict], cand: str) -> list[dict]:
    base = [r for r in rows if r["H1"]]
    if cand == "H1":
        return base
    if cand == "H1+C1":
        return [r for r in base if r["c1"]]
    if cand == "H1+C2":
        return [r for r in base if r["c2"]]
    if cand == "H1+C3":
        return [r for r in base if r["c3"] is True]
    return [r for r in base if r["c1"] and r["c2"] and r["c3"] is True]


def analyse(res: dict) -> dict:
    rows = res["rows"]
    c3_run = res["eu_coverage"] >= EU_COVERAGE
    cands = [c for c in CANDIDATES if c3_run or c not in ("H1+C3", "H1+ALL")]
    out = {"events": res["events"], "trades": len(rows), "eu_coverage": res["eu_coverage"],
           "not_run": [c for c in CANDIDATES if c not in cands], "candidates": {}}
    base = select(rows, "H1")
    outside = [r for r in rows if not r["in_window"]]
    ps = {}
    for cand in cands:
        u = select(rows, cand)
        s = summary(u)
        dec = [r for r in u if r["tp10"] in ("TP", "SL") and np.isfinite(r["r1_rate10"])]
        diff = np.array([float(r["tp10"] == "TP") - r["r1_rate10"] for r in dec])
        md, ci, p = boot_mean(diff, np.array([r["t0"] // 86400 for r in dec]))
        s["vs_R1"] = {"n": len(dec), "rate": float(np.mean([r["tp10"] == "TP" for r in dec])) if dec else math.nan,
                      "r1_rate": float(np.mean([r["r1_rate10"] for r in dec])) if dec else math.nan, "mean_diff": md, "boot95": ci, "p_one_sided": p}
        if cand != "H1":
            ids = {r["id"] for r in u}
            rest = [r for r in base if r["id"] not in ids]
            x1 = [float(r["tp10"] == "TP") for r in u if r["tp10"] in ("TP", "SL")]
            x0 = [float(r["tp10"] == "TP") for r in rest if r["tp10"] in ("TP", "SL")]
            d1 = [r["t0"] // 86400 for r in u if r["tp10"] in ("TP", "SL")]
            d0 = [r["t0"] // 86400 for r in rest if r["tp10"] in ("TP", "SL")]
            s["vs_R3_without_confirmation"] = dict(zip(("diff", "boot95", "p_one_sided"), boot_two(x1, d1, x0, d0)), n_without=len(x0))
        ps[cand] = p
        out["candidates"][cand] = s
    hp = holm(ps)
    for cand, s in out["candidates"].items():
        lb = (s.get("tp10") or {}).get("mean_net_r_day95", [math.nan])[0]
        mr = (s.get("tp10") or {}).get("mean_net_r", math.nan)
        s["holm_p"] = hp.get(cand)
        s["candidate"] = bool(hp.get(cand) is not None and hp[cand] < 0.05 and np.isfinite(mr) and mr > 0 and np.isfinite(lb) and lb > 0
                              and (s.get("tp10") or {}).get("decided", 0) >= MIN_DECIDED)
    out["overall"] = ("CANDIDATE(S): " + ", ".join(k for k, v in out["candidates"].items() if v["candidate"])
                      if any(v["candidate"] for v in out["candidates"].values()) else "NO CANDIDATE")
    x1 = [float(r["tp10"] == "TP") for r in base if r["tp10"] in ("TP", "SL")]
    x0 = [float(r["tp10"] == "TP") for r in outside if r["tp10"] in ("TP", "SL")]
    out["R2_outside_windows"] = {**summary(outside), "H1_minus_outside": dict(zip(("diff", "boot95", "p_one_sided"), boot_two(
        x1, [r["t0"] // 86400 for r in base if r["tp10"] in ("TP", "SL")], x0, [r["t0"] // 86400 for r in outside if r["tp10"] in ("TP", "SL")])))}
    out["window_without_run"] = summary([r for r in rows if r["in_window"] and not r["run_ok"]])
    out["by_boundary_H1"] = {b: summary([r for r in base if r["boundary"] == b]) for b, *_ in BOUNDS}
    out["by_boundary_all_in_window"] = {b: summary([r for r in rows if r["in_window"] and r["boundary"] == b]) for b, *_ in BOUNDS}
    out["by_ref_tf_H1"] = {tf: summary([r for r in base if r["ref_tf"] == tf]) for tf in sweeps.LEVEL_TFS}
    return out


def file_sha(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", default="development")
    ap.add_argument("--rd", required=True, help="research-data clone (XAU/USD 15min, 1h, 5min; EUR/USD 15min)")
    ap.add_argument("--cost", required=True, help="research/registrations/B31b-W8-cost.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--csv")
    a = ap.parse_args(argv)
    if a.part != "development":
        raise H.SealedPartition(f"{REG}: only the development partition is registered")
    m15, h1, m5, score_from = W.load(a.rd, "development", None)
    eu = history.load(a.rd, "EUR/USD", "15min")
    eu = H.partition(eu, "development") if eu is not None else None
    res = build(m15, h1, m5, eu, score_from, load_cost(a.cost))
    out = analyse(res)
    out.update(registration=REG, part=a.part, code_sha256=file_sha(__file__), data_hash=H.data_hash(m15),
               sweeps_sha256=file_sha(sweeps.__file__),
               created_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    with open(a.out, "w") as fh:
        json.dump(_clean(out), fh, indent=1)
    if a.csv:
        cols = ("id", "t0", "boundary", "min_to_boundary", "in_window", "run_atr", "run_ok", "H1", "c1", "c2", "c3", "d", "ref",
                "ref_kind", "ref_tf", "sess", "entry", "stop", "D", "cost", "tp10", "tp10_r", "tp15", "tp15_r", "tp20", "tp20_r",
                "r1_rate10", "r1_net10", "poc_prev")
        pd.DataFrame([{k: r.get(k) for k in cols} for r in res["rows"]]).to_csv(a.csv, index=False)
    print(json.dumps({"overall": out["overall"], "events": out["events"], "eu_coverage": round(res["eu_coverage"], 4)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
