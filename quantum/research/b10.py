"""Phase B10 (research/registrations/B10.json, approved 2026-11-05; written after the registration was committed).

Development partition only. The frozen web.8 engine (treatment arm, config.DEFAULT) runs on Markets built from the
research-data Twelve Data XAU/USD 15min and 1h series; inputs not stored for 2020-2023 (GC volume, silver, EUR/USD,
S&P 500, DXY, US 10y, VIX, FRED, COT) are absent, so their layers are neutral.

  B10-1a  release the HTF bear (bull) gate from a close above the previous week's high (below its low) until a close
          beyond the opposite weekly level or 5 trading days; measured on the signals the variant ADDS
  B10-1b  (secondary) the same with the previous day's high / low, for the rest of that trading day and the next
  B10-2a  GRAB (the engine's SWEEP) in RANGE / COMPRESS, in the sweep's direction, once per pool per trading day
  B10-2b  BREAK (a close beyond PDH / PDL / PWH / PWL) in STRONG TR / EXPANSION, in the break's direction, ditto

Outcome: +13 before -13 at $4,000, scaled by entry / 4000, on 15-minute bars for 96 bars; a bar reaching both levels is
a loss unless it opened beyond the target. Costs harness.cost_pts, scaled. Holm over the three primaries (P1: z vs
direction-matched random; P2: mean net > 0, t >= 1.645); fewer than 30 decided trades: INSUFFICIENT.
Research code: never imported by production (tests/test_integrity.py).
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .. import config, engine, report, ta
from ..data import sources
from ..data.market import Market
from ..features import compute as compute_features
from ..notify import trading_day
from . import harness as H
from . import history

REG = "B10"
TP = SL = 13.0                        # at $4,000; scaled by entry / 4000
PATH_BARS = 96                        # 15-minute bars: one trading day
SCORE_FROM = pd.Timestamp("2020-04-01", tz="UTC")
RELEASE_BARS = {"15m": 480, "1h": 120}   # 5 trading days
RANGE_REGIMES = ("RANGE", "COMPRESS")
TREND_REGIMES = ("STRONG TR", "EXPANSION")
MIN_N = 30
HIGHS = ("PDH", "PWH", "PMH")


def make_market(base: pd.DataFrame, h1: pd.DataFrame, tf: str, tf_sec: int) -> Market:
    htf = {"60": h1, "240": sources.resample_ny_session(h1, 4), "D": sources.daily_ny_session(h1)}
    return Market(tf=tf, tf_sec=tf_sec, base=base, forming=None, htf=htf,
                  ext_chart={"silver": None, "eurusd": None, "spx": None, "gc": None}, ext_macro={}, ext_daily={}, cot=None,
                  status={}, price_source="twelvedata:XAU/USD", volume_source="NONE (not stored for 2020-2023)")


def release_mask(c: np.ndarray, up_level: np.ndarray, dn_level: np.ndarray, max_bars: int | None, day: np.ndarray | None = None) -> np.ndarray:
    """True on bars where a gate is released: from the first close above up_level (the previous close at or below it)
    until a close below dn_level, or max_bars later (weekly rule), or the end of the next trading day (daily rule, day
    given). After it ends, a new release needs a new close from below."""
    n = len(c)
    out = np.zeros(n, bool)
    start, start_day = -1, None
    nxt = {}
    if day is not None:                                   # each trading day -> the next one in the series
        u_days = list(dict.fromkeys(day.tolist()))
        nxt = dict(itertools.pairwise(u_days))
    for i in range(n):
        u, d = up_level[i], dn_level[i]
        if start >= 0:
            expired = (i - start > max_bars) if max_bars is not None else (day[i] not in (start_day, nxt.get(start_day)))
            if expired or (np.isfinite(d) and c[i] < d):
                start = -1
        fresh = i > 0 and np.isfinite(up_level[i - 1]) and c[i - 1] <= up_level[i - 1]   # a close from below: a new break
        if start < 0 and np.isfinite(u) and c[i] > u and fresh:
            start, start_day = i, (day[i] if day is not None else None)
        out[i] = start >= 0
    return out


def signals(res) -> set:
    return {(e["i"], int(e["dir"])) for e in res.events if e["type"] == "SIGNAL" and e.get("dir") in (1, -1)}


def outcomes(path: pd.DataFrame, t_close: np.ndarray, price: np.ndarray, d: np.ndarray, cost: np.ndarray) -> dict:
    """+13 / -13 (scaled) first passage on the 15-minute path from each decision bar's close."""
    t = ta.epoch_s(path.index)
    o, h, l = (path[k].to_numpy(float) for k in ("open", "high", "low"))
    j = np.searchsorted(t, t_close)                      # first bar opening at / after the decision close
    ok = (j + PATH_BARS <= len(t)) & np.isfinite(price) & (d != 0)
    win = np.zeros(len(t_close), bool)
    loss = np.zeros(len(t_close), bool)
    for x in np.flatnonzero(ok):
        s = price[x] / 4000.0
        a = TP * s
        rows = slice(j[x], j[x] + PATH_BARS)
        hh, ll, oo = h[rows], l[rows], o[rows]
        fav = (hh - price[x]) if d[x] > 0 else (price[x] - ll)
        adv = (price[x] - ll) if d[x] > 0 else (hh - price[x])
        it = np.flatnonzero(fav >= a - 1e-9)
        ib = np.flatnonzero(adv >= SL * s - 1e-9)
        ia, ib_ = (it[0] if len(it) else PATH_BARS), (ib[0] if len(ib) else PATH_BARS)
        if ia < ib_:
            win[x] = True
        elif ib_ < ia:
            loss[x] = True
        elif ia < PATH_BARS:                             # both in one bar: a loss unless it opened beyond the target
            if (oo[ia] - price[x]) * d[x] >= a - 1e-9:
                win[x] = True
            else:
                loss[x] = True
    scale = price / 4000.0
    net = np.where(win, TP * scale - cost * scale, np.where(loss, -SL * scale - cost * scale, np.nan))
    be = (13.0 + cost) / 26.0
    return {"ok": ok, "win": win, "loss": loss, "net": net, "be": be}


def stats(o: dict, d: np.ndarray, rnd: dict) -> dict:
    dec = o["win"] | o["loss"]
    n, k = int(dec.sum()), int(o["win"].sum())
    long_, short_ = int(((d > 0) & dec).sum()), int(((d < 0) & dec).sum())
    mix = (long_ * rnd["long"] + short_ * rnd["short"]) / n if n else math.nan
    rate = k / n if n else math.nan
    z = (rate - mix) / math.sqrt(mix * (1 - mix) / n) if n and 0 < mix < 1 else math.nan
    net = o["net"][dec]
    mean = float(np.mean(net)) if n else math.nan
    t = float(mean / (np.std(net, ddof=1) / math.sqrt(n))) if n > 2 and np.std(net, ddof=1) > 0 else math.nan
    lo, hi = H.wilson(k, n)
    return {"n": n, "wins": k, "losses": n - k, "long": long_, "short": short_, "win_rate": rate, "wilson": [lo, hi],
            "random_same_mix": mix, "z_vs_random": z, "p_one_sided": 1 - H._norm_cdf(z) if math.isfinite(z) else math.nan,
            "break_even": float(np.mean(o["be"][dec])) if n else math.nan, "mean_net_usd_at_4000_per_oz": mean,
            "t": t, "usd_per_trade_0p5lot_at_4000": mean * 50 if n else math.nan}


def liquidity_events(res, F, kind: str, regimes: tuple | None) -> tuple[np.ndarray, np.ndarray]:
    R = res.rows
    idx = pd.DatetimeIndex(F["index"])
    day = np.array([trading_day(int(x.timestamp())) for x in idx])
    reg = np.asarray(R["regime_label"], object)
    seen, ii, dd = set(), [], []
    if kind == "GRAB":
        for e in res.events:
            if e["type"] != "SWEEP" or e.get("dir") not in (1, -1):
                continue
            i = e["i"]
            if regimes and reg[i] not in regimes:
                continue
            pools = report.swept_levels(R, F, i, e["dir"])
            fresh = [p for p in pools if ("G", p["name"], round(float(p["px"]), 2), day[i]) not in seen]
            for p in pools:
                seen.add(("G", p["name"], round(float(p["px"]), 2), day[i]))
            if fresh:
                ii.append(i)
                dd.append(int(e["dir"]))
    else:
        c = np.asarray(F["c"], float)
        for name, key in (("PDH", "pdh"), ("PWH", "pwh"), ("PDL", "pdl"), ("PWL", "pwl")):
            lv = np.asarray(R[key], float)
            hi = name in HIGHS
            for k in range(1, len(c)):
                if not np.isfinite(lv[k]) or (regimes and reg[k] not in regimes):
                    continue
                if (c[k] > lv[k] >= c[k - 1]) if hi else (c[k] < lv[k] <= c[k - 1]):
                    key2 = ("B", name, round(float(lv[k]), 2), day[k])
                    if key2 not in seen:
                        seen.add(key2)
                        ii.append(k)
                        dd.append(1 if hi else -1)
    order = np.argsort(ii, kind="stable")
    return np.asarray(ii, int)[order], np.asarray(dd, int)[order]


def _clean(x):
    """NaN -> None, numpy scalars -> Python, for strict JSON."""
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if math.isnan(float(x)) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def holm(ps: dict, alpha: float = 0.05) -> dict:
    items = sorted((p, k) for k, p in ps.items() if math.isfinite(p))
    out, m, still = {}, len(items), True
    for r, (p, k) in enumerate(items):
        still = still and p <= alpha / (m - r)
        out[k] = still
    for k, p in ps.items():
        out.setdefault(k, False)
    return out


def run_tf(rd: str, tf: str, cfg=config.DEFAULT, log=print) -> dict:
    m15 = H.partition(history.load(rd, "XAU/USD", "15min"), "development")
    h1 = H.partition(history.load(rd, "XAU/USD", "1h"), "development")
    base, tf_sec = (m15, 900) if tf == "15m" else (h1, 3600)
    m = make_market(base, h1, tf, tf_sec)
    F = compute_features(m, cfg)
    idx = pd.DatetimeIndex(F["index"])
    t_close = ta.epoch_s(idx) + tf_sec
    c = np.asarray(F["c"], float)
    cost = H.cost_pts(idx)
    scored = idx >= SCORE_FROM
    log(f"[{tf}] {len(idx)} bars {idx[0]} -> {idx[-1]}: baseline engine run")
    res0 = engine.run(m, cfg, "treatment", F)
    R = res0.rows
    day = np.array([trading_day(int(x)) for x in t_close - tf_sec])
    variants = {}
    for name, (up, dn, mb) in {"B10-1a": ("pwh", "pwl", RELEASE_BARS[tf]), "B10-1b": ("pdh", "pdl", None)}.items():
        upl, dnl = np.asarray(R[up], float), np.asarray(R[dn], float)
        rel_bear = release_mask(c, upl, dnl, mb, None if mb else day)          # BUYs allowed after an upside break
        rel_bull = release_mask(-c, -dnl, -upl, mb, None if mb else day)       # SELLs allowed after a downside break
        F2 = dict(F)
        F2["htf_bear_gate"] = np.asarray(F["htf_bear_gate"], bool) & ~rel_bear
        F2["htf_bull_gate"] = np.asarray(F["htf_bull_gate"], bool) & ~rel_bull
        log(f"[{tf}] {name}: gate released on {int(rel_bear.sum())} / {int(rel_bull.sum())} bars; variant engine run")
        variants[name] = (engine.run(m, cfg, "treatment", F2), int(rel_bear.sum()), int(rel_bull.sum()))
    path = m15
    k = np.arange(0, int(np.sum(scored)), 3)
    ri = np.flatnonzero(scored)[k]
    rnd = {}
    for nm, s in (("long", 1), ("short", -1)):
        o = outcomes(path, t_close[ri], c[ri], np.full(len(ri), s), cost[ri])
        dec = o["win"] | o["loss"]
        rnd[nm] = float(o["win"][dec].mean())
    log(f"[{tf}] random: long {rnd['long']:.3f} short {rnd['short']:.3f}")

    def measure(ii, dd):
        ii, dd = np.asarray(ii, int), np.asarray(dd, int)
        keep = scored[ii] if len(ii) else np.zeros(0, bool)
        ii, dd = ii[keep], dd[keep]
        o = outcomes(path, t_close[ii], c[ii], dd, cost[ii])
        return stats(o, dd, rnd)

    out = {"tf": tf, "bars": len(idx), "window": [str(idx[0]), str(idx[-1])], "random": rnd, "trials": {}}
    s0 = sorted(signals(res0))
    out["trials"]["baseline signals"] = measure([x[0] for x in s0], [x[1] for x in s0])
    for name, (res1, nb, ns) in variants.items():
        s1 = signals(res1)
        added = sorted(s1 - set(s0))
        removed = sorted(set(s0) - s1)
        out["trials"][f"{name} added signals"] = {**measure([x[0] for x in added], [x[1] for x in added]),
                                                   "released_bars_bear_gate": nb, "released_bars_bull_gate": ns,
                                                   "removed_signals": len(removed)}
        out["trials"][f"{name} all signals"] = measure([x[0] for x in sorted(s1)], [x[1] for x in sorted(s1)])
    for kind, regs, nm in (("GRAB", RANGE_REGIMES, "B10-2a GRAB in range"), ("GRAB", None, "GRAB all regimes"),
                           ("BREAK", TREND_REGIMES, "B10-2b BREAK in trend"), ("BREAK", None, "BREAK all regimes")):
        out["trials"][nm] = measure(*liquidity_events(res0, F, kind, regs))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True, help="research-data checkout")
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials", required=True)
    a = ap.parse_args(argv)
    res = {"registration": REG, "utc": datetime.now(timezone.utc).isoformat(), "tfs": {}}
    for tf in ("15m", "1h"):
        res["tfs"][tf] = run_tf(a.rd, tf)
    prim = {"B10-1a": res["tfs"]["15m"]["trials"]["B10-1a added signals"],
            "B10-2a": res["tfs"]["15m"]["trials"]["B10-2a GRAB in range"],
            "B10-2b": res["tfs"]["15m"]["trials"]["B10-2b BREAK in trend"]}
    p1 = holm({k: v["p_one_sided"] for k, v in prim.items()})
    verdict = {}
    for k, v in prim.items():
        if v["n"] < MIN_N:
            verdict[k] = "INSUFFICIENT"
        else:
            verdict[k] = "PASS" if (p1[k] and math.isfinite(v["t"]) and v["t"] >= 1.645) else "FAIL"
    res["primary"] = {"holm_p1": p1, "verdict": verdict}
    with open(a.out, "w") as f:
        json.dump(_clean(res), f, indent=1, allow_nan=False)
    primary_name = {"B10-1a added signals": "B10-1a", "B10-2a GRAB in range": "B10-2a", "B10-2b BREAK in trend": "B10-2b"}
    for tf, T in res["tfs"].items():
        for nm, s in T["trials"].items():
            rec = {"phase": "B10", "partition": "development", "id": f"{tf} {nm} T13", "tf": tf,
                   **_clean(s)}
            if tf == "15m" and nm in primary_name:
                rec["primary"], rec["verdict"] = primary_name[nm], verdict[primary_name[nm]]
            H.log_trial(a.trials, rec)
    print(json.dumps(res["primary"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
