"""B26 (research/registrations/B26.json, committed 4a3978666 before this code): the Phase A baseline for the operator's
exact trade, +$15 before -$15 from the actual fill, at every eligible bar, BUY and SELL measured separately.

RESEARCH ONLY: never imported by the engine, the arms or the site (tests/test_integrity.py). No parameter is chosen
here; the outputs are the reference rates later models must beat.

Execution model (registered):
  * decision at the close of bar i; fill at the open of bar i+1 (BUY at the ask, SELL at the bid, plus entry slippage);
  * TP / SL are +-15k from the fill (k = price / 4000 in development, 1 elsewhere); a BUY's levels trigger on the bid,
    a SELL's on the ask; bars are mid prices and s is the scenario spread at the fill;
  * a bar opening beyond the stop fills there less the exit slippage; beyond the target, at the target (limit order);
  * a bar reaching both levels is the stop (AMBIGUOUS); 2 trading days at most (TIMEOUT); a trade open at the last bar
    before a closure of more than 2 hours exits at that bar's close (CLOSURE); the one-hour daily break is held through.

  python -m quantum.research.b26 --rd <research-data> --store5 <XAU_USD_5m dir> --store60 <XAU_USD_60m dir> --out <dir>
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .. import news_calendar, sessions, ta
from ..data import sources
from . import b8_news, b13, history
from . import harness as H

REG = "B26"
MOVE = 15.0                        # USD at the 4000 reference (literal where k = 1)
REF = 4000.0
BAR = {"5m": 300, "15m": 900}
HORIZON = {"5m": 576, "15m": 192}  # 2 trading days
CLOSURE_S = 7200                   # a gap longer than this is a market closure (the daily break is 1 hour)
NO_ENTRY_S = 3600                  # no entry if a closure starts within this many seconds of the decision
NEWS_BEFORE_S, NEWS_AFTER_S = 1800, 7200
LOT_OZ = 50.0                      # 0.50 lot x 100 oz: ASSUMED until the broker's XAUUSD specification is received
SEED = 26
N_BOOT = 2000
OUTCOMES = ("TP", "SL", "AMBIGUOUS", "TIMEOUT", "CLOSURE", "OPEN")
TP, SL, AMB, TIMEOUT, CLOSURE, OPEN = range(6)
SCENARIOS = ("GROSS", "OP", "ENG", "ADV")
PRIMARY = "ENG"
DIRS = {1: "BUY", -1: "SELL"}
DATED = ((pd.Timestamp("2020-01-24", tz="UTC"), pd.Timestamp("2023-01-25", tz="UTC")),
         (pd.Timestamp("2026-10-28", tz="UTC"), pd.Timestamp("2027-12-11", tz="UTC")))


# ---------------- data ----------------
def epoch(idx: pd.DatetimeIndex) -> np.ndarray:
    return np.asarray(ta.epoch_s(idx), dtype=np.int64)


def load_store(d: str, bar_sec: int) -> pd.DataFrame:
    """A live-store series (one CSV per month), cleaned as the site does: off-grid rows and market-shut prints dropped,
    the stale first print after each closure repaired."""
    parts = [pd.read_csv(f, index_col=0, parse_dates=True) for f in sorted(glob.glob(os.path.join(d, "*.csv")))]
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    idx = pd.DatetimeIndex(df.index)
    df.index = idx.tz_convert("UTC") if idx.tz is not None else idx.tz_localize("UTC")
    df = sources.trading_week_only(sources.drop_offgrid(df))
    return sources.repair_reopen(df, bar_sec)


def populations(rd: str, store5: str | None, store60: str | None, which=("P1", "P2", "P3")) -> dict:
    """The three registered populations: execution bars, 1h context bars, scoring start, scaling, timeframe.
    No validation or holdout bar is read: development through the harness seal, 2026 from 2026-01-01 (H.HOLD[1])."""
    out = {}
    if "P1" in which:
        m15 = sources.repair_reopen(H.partition(history.load(rd, "XAU/USD", "15min"), "development"), 900)
        h1 = sources.repair_reopen(H.partition(history.load(rd, "XAU/USD", "1h"), "development"), 3600)
        out["P1"] = {"bars": m15, "h1": h1, "score_from": b13.SCORE_FROM, "scale": True, "tf": "15m",
                     "label": "development 2020-04-01 .. 2023-01-24, 15m, 4000-equivalent USD"}
    lo = H.HOLD[1]
    h1r = None
    if "P2" in which or "P3" in which:
        h1r = history.load(rd, "XAU/USD", "1h")
        h1r = sources.repair_reopen(h1r[h1r.index >= lo], 3600)
        if store60:
            s60 = load_store(store60, 3600)
            h1r = pd.concat([h1r, s60[s60.index > h1r.index[-1]]]).sort_index()
    if "P2" in which:
        m15 = history.load(rd, "XAU/USD", "15min")
        m15 = sources.repair_reopen(m15[m15.index >= lo], 900)
        out["P2"] = {"bars": m15, "h1": h1r, "score_from": pd.Timestamp("2026-03-01", tz="UTC"), "scale": False, "tf": "15m",
                     "label": "2026-03-01 .. end of the research history, 15m, literal USD"}
    if "P3" in which and store5:
        df5 = load_store(store5, 300)
        out["P3"] = {"bars": df5, "h1": h1r, "score_from": df5.index[0] + pd.Timedelta(days=1), "scale": False, "tf": "5m",
                     "label": "live store 5m, literal USD (the execution timeframe; two months)"}
    return out


# ---------------- the race ----------------
@dataclass
class Path:
    t: list
    o: list
    h: list
    l: list
    c: list
    closure_end: list      # True at the last bar before a closure (and at the final bar)
    bar: int
    n: int


def make_path(df: pd.DataFrame, bar: int) -> Path:
    t = epoch(df.index)
    gap_after = np.r_[np.diff(t), np.iinfo(np.int64).max]
    return Path(t.tolist(), *(df[x].astype(float).tolist() for x in ("open", "high", "low", "close")),
                (gap_after > CLOSURE_S).tolist(), bar, len(t))


def race(P: Path, f: int, d: int, s: float, si: float, so: float, k: float, horizon: int) -> tuple:
    """One trade filled at the open of bar f. Returns (outcome, exit_bar, exit_px, exit_t, gap, fill, tp, sl, mfe, mae);
    prices are actual, mfe / mae in price units on the trigger side (capped at the levels except a gap stop)."""
    o, h, l, c = P.o, P.h, P.l, P.c
    dist = MOVE * k
    fill = o[f] + d * (s / 2.0 + si)
    tp, sl = fill + d * dist, fill - d * dist
    off = -d * s / 2.0                                    # trigger side: a BUY exits on the bid, a SELL on the ask
    mfe = mae = 0.0
    end = min(f + horizon, P.n)
    for j in range(f, end):
        oj, hj, lj = o[j] + off, h[j] + off, l[j] + off
        if d > 0:
            if oj <= sl:
                return SL, j, oj - so, P.t[j], True, fill, tp, sl, mfe, fill - oj
            if oj >= tp:
                return TP, j, tp, P.t[j], True, fill, tp, sl, dist, mae
            fav, adv, hit_t, hit_s = hj - fill, fill - lj, hj >= tp, lj <= sl
        else:
            if oj >= sl:
                return SL, j, oj + so, P.t[j], True, fill, tp, sl, mfe, oj - fill
            if oj <= tp:
                return TP, j, tp, P.t[j], True, fill, tp, sl, dist, mae
            fav, adv, hit_t, hit_s = fill - lj, hj - fill, lj <= tp, hj >= sl
        mfe, mae = max(mfe, min(fav, dist)), max(mae, min(adv, dist))
        if hit_s:
            return (AMB if hit_t else SL), j, sl - d * so, P.t[j] + P.bar, False, fill, tp, sl, mfe, dist
        if hit_t:
            return TP, j, tp, P.t[j] + P.bar, False, fill, tp, sl, dist, mae
        if j == P.n - 1:
            return OPEN, j, math.nan, P.t[j] + P.bar, False, fill, tp, sl, mfe, mae
        if P.closure_end[j]:
            return CLOSURE, j, c[j] + off - d * so, P.t[j] + P.bar, False, fill, tp, sl, mfe, mae
        if j == f + horizon - 1:
            return TIMEOUT, j, c[j] + off - d * so, P.t[j] + P.bar, False, fill, tp, sl, mfe, mae
    return OPEN, end - 1, math.nan, P.t[end - 1] + P.bar, False, fill, tp, sl, mfe, mae


def eligible(P: Path, score_from_s: int) -> np.ndarray:
    """Decision bars: the fill bar follows without a break, no closure starts within NO_ENTRY_S, inside the window."""
    t = np.asarray(P.t, dtype=np.int64)
    nxt_ok = np.r_[np.diff(t) == P.bar, False]
    ce = np.flatnonzero(np.asarray(P.closure_end))
    nxt = ce[np.searchsorted(ce, np.arange(P.n), "left")]
    return nxt_ok & ((t[nxt] - t) >= NO_ENTRY_S) & ((t + P.bar) >= score_from_s)


def scenario_costs(fill_idx: pd.DatetimeIndex, k: np.ndarray) -> dict:
    """(spread, entry slippage, exit slippage, commission) per entry and scenario, in price units (x k)."""
    eng_spread = H.cost_pts(fill_idx, slippage=0.0, commission_lot=0.0)       # 0.30 in session, 0.50 off session
    z = np.zeros(len(k))
    return {"GROSS": (z, z, z, z),
            "OP": (0.26 * k, z, z, z),
            "ENG": (eng_spread * k, 0.20 * k, 0.20 * k, 0.07 * k),
            "ADV": (2.0 * eng_spread * k, 0.40 * k, 0.40 * k, 0.07 * k)}


# ---------------- context, from completed bars only ----------------
def context(h1: pd.DataFrame, T: np.ndarray) -> dict:
    """Volatility tercile and the three trend votes at decision times T (epoch s), each from bars CLOSED by T."""
    t1 = epoch(h1.index)
    hh, ll, cc = (h1[x].to_numpy(float) for x in ("high", "low", "close"))
    v = pd.Series(ta.atr(hh, ll, cc, 14) / cc, index=h1.index)
    q1 = v.rolling("90D", min_periods=1000).quantile(1 / 3).to_numpy()
    q2 = v.rolling("90D", min_periods=1000).quantile(2 / 3).to_numpy()
    vv = v.to_numpy()
    terc = np.where(np.isnan(q1) | np.isnan(vv), "NA", np.where(vv <= q1, "LOW", np.where(vv >= q2, "HIGH", "MID")))
    vote1 = np.sign(ta.ema(cc, 20) - ta.ema(cc, 50))
    h4 = sources.resample_ny_session(h1, 4)
    c4 = h4["close"].to_numpy(float)
    vote4 = np.sign(ta.ema(c4, 20) - ta.ema(c4, 50))
    d1 = sources.daily_ny_session(h1)
    cd = d1["close"].to_numpy(float)
    voted = np.sign(cd - ta.ema(cd, 50))

    def last_closed(t_open: np.ndarray, span: int) -> np.ndarray:
        return np.searchsorted(t_open + span, T, "right") - 1

    j1, j4, jd = last_closed(t1, 3600), last_closed(epoch(h4.index), 4 * 3600), last_closed(epoch(d1.index), 86400)

    def at(x: np.ndarray, j: np.ndarray) -> np.ndarray:
        out = np.full(len(j), np.nan)
        ok = j >= 0
        out[ok] = x[j[ok]]
        return out

    a1, a4, ad = at(vote1, j1), at(vote4, j4), at(voted, jd)
    trend = np.where(np.isnan(a1) | np.isnan(a4) | np.isnan(ad), "NA",
                     np.where((a1 > 0) & (a4 > 0) & (ad > 0), "UP", np.where((a1 < 0) & (a4 < 0) & (ad < 0), "DOWN", "MIXED")))
    vol = np.where(j1 >= 0, terc[np.clip(j1, 0, None)], "NA")
    return {"vol": vol, "trend": trend, "v1h": a1, "v4h": a4, "v1d": ad}


def news_label(T: np.ndarray) -> np.ndarray:
    rel = [int(b8_news.release_utc(kind, day).timestamp()) for kind, days in b8_news.DATES.items() for day in days]
    rel += [e["t"] for e in news_calendar.events()]
    rel = np.unique(np.asarray(rel, dtype=np.int64))
    j = np.searchsorted(rel, T - NEWS_AFTER_S, "left")              # first release not more than 2 h before T
    near = (j < len(rel)) & (rel[np.clip(j, 0, len(rel) - 1)] <= T + NEWS_BEFORE_S)
    dated = np.zeros(len(T), dtype=bool)
    for lo, hi in DATED:
        dated |= (T >= int(lo.timestamp())) & (T < int(hi.timestamp()))
    return np.where(near & dated, "NEWS", np.where(dated, "NONE", "NOT DATED"))


def session_labels(idx: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Session (ASIA / LONDON / OVERLAP / NY / OFF), the New York trading day's weekday and date (17:00 roll)."""
    cal = sessions.calendar(idx)
    a, lo, ny = (cal[x].to_numpy(bool) for x in ("in_asian", "in_london", "in_ny"))
    sess = np.where(a, "ASIA", np.where(lo & ny, "OVERLAP", np.where(lo, "LONDON", np.where(ny, "NY", "OFF"))))
    td = pd.DatetimeIndex(cal["trading_date"])
    return sess, td.day_name().str[:3].to_numpy(), td.strftime("%Y-%m-%d").to_numpy()


def direction_after(P: Path, f: np.ndarray, d: int, secs: int) -> np.ndarray:
    """1 / 0 / nan: is the mid close at fill + secs beyond the fill bar's open in the trade's direction (not across a
    closure)?"""
    t = np.asarray(P.t, dtype=np.int64)
    c, o = np.asarray(P.c), np.asarray(P.o)
    tgt = t[f] + secs - P.bar
    j = np.searchsorted(t, tgt, "right") - 1
    ok = (j >= f) & ((tgt - t[np.clip(j, 0, None)]) <= 3600)
    mv = d * (c[np.clip(j, 0, None)] - o[f])
    return np.where(ok & (mv != 0), (mv > 0).astype(float), np.nan)


# ---------------- one population ----------------
def run_population(name: str, pop: dict, log=print) -> pd.DataFrame:
    tf, bars = pop["tf"], pop["bars"]
    P = make_path(bars, BAR[tf])
    el = np.flatnonzero(eligible(P, int(pop["score_from"].timestamp())))
    f = el + 1
    t = np.asarray(P.t, dtype=np.int64)
    c = np.asarray(P.c)
    k = c[el] / REF if pop["scale"] else np.ones(len(el))
    fill_idx = pd.to_datetime(t[f], unit="s", utc=True)
    costs = scenario_costs(fill_idx, k)
    T = t[f]                                                    # decision time = the fill bar's open
    ctx = context(pop["h1"], T)
    sess, wd, nyday = session_labels(fill_idx)
    news = news_label(T)
    frames = []
    for d, dn in DIRS.items():
        rec = {"pop": name, "tf": tf, "dir": dn, "dec_i": el, "decision_utc": t[el], "decision_px": c[el], "fill_utc": T,
               "fill_mid": np.asarray(P.o)[f], "k": k, "nyday": nyday, "session": sess, "weekday": wd, "vol_tercile": ctx["vol"],
               "trend_state": ctx["trend"], "news": news,
               "dir_1h_correct": direction_after(P, f, d, 3600), "dir_4h_correct": direction_after(P, f, d, 4 * 3600)}
        rec["trend_rel"] = np.where(ctx["trend"] == "NA", "NA", np.where(ctx["trend"] == "MIXED", "MIXED",
                                    np.where(ctx["trend"] == ("UP" if d > 0 else "DOWN"), "WITH", "AGAINST")))
        for sc in SCENARIOS:
            s_, si_, so_, cm_ = costs[sc]
            res = [race(P, int(fi), d, float(s_[x]), float(si_[x]), float(so_[x]), float(k[x]), HORIZON[tf])
                   for x, fi in enumerate(f)]
            arr = list(zip(*res)) if res else [[]] * 10
            out_c, xb, xpx, xt, gap, fill, tpp, slp, mfe, mae = (np.asarray(a) for a in arr)
            net = (d * (xpx - fill) - cm_) / k                    # USD per oz (4000-equivalent where scaled)
            paid_out = np.where(out_c == TP, 0.0, so_)
            cost = (s_ + si_ + paid_out + cm_) / k
            pre = sc if sc != PRIMARY else ""
            if sc == PRIMARY:
                rec.update({"fill_px": fill, "tp_px": tpp, "sl_px": slp, "outcome": [OUTCOMES[int(x)] for x in out_c],
                            "gap": gap.astype(bool), "exit_bar": xb, "exit_utc": xt, "exit_px": xpx,
                            "minutes": (xt - T) / 60.0, "mfe_usd": mfe / k, "mae_usd": mae / k,
                            "spread": s_ / k, "slip_in": si_ / k, "slip_out": paid_out / k, "commission": cm_ / k,
                            "gross_usd_oz": net + cost, "cost_usd_oz": cost, "net_usd_oz": net, "net_usd_050lot": net * LOT_OZ})
            else:
                rec.update({f"{pre}_outcome": [OUTCOMES[int(x)] for x in out_c], f"{pre}_exit_bar": xb,
                            f"{pre}_minutes": (xt - T) / 60.0, f"{pre}_net_usd_oz": net})
        frames.append(pd.DataFrame(rec))
        log(f"[B26] {name} {dn}: {len(el)} entries")
    df = pd.concat(frames, ignore_index=True)
    for sc in SCENARIOS:
        df[f"in_seq_{sc}"] = sequential_mask(df, sc)
    return df


def sequential_mask(df: pd.DataFrame, sc: str) -> np.ndarray:
    """The non-overlapping series per direction: the next decision is the bar on which the previous trade exited."""
    oc = "outcome" if sc == PRIMARY else f"{sc}_outcome"
    xb = "exit_bar" if sc == PRIMARY else f"{sc}_exit_bar"
    mask = np.zeros(len(df), dtype=bool)
    for dn in DIRS.values():
        sub = df.index[df["dir"] == dn]
        dec, ex, out = df.loc[sub, "dec_i"].to_numpy(), df.loc[sub, xb].to_numpy(), df.loc[sub, oc].to_numpy()
        order = np.argsort(dec, kind="stable")
        cur = -1
        for q in order:
            if out[q] == "OPEN":
                break
            if dec[q] >= cur:
                mask[sub[q]] = True
                cur = ex[q]
    return mask


# ---------------- statistics ----------------
def _day(df: pd.DataFrame) -> np.ndarray:
    return df["nyday"].to_numpy()


def cluster_ci(x: np.ndarray, day: np.ndarray, n_boot: int = N_BOOT, seed: int = SEED) -> list:
    """95% interval of the mean of x, resampling whole New York trading days (entries in a day overlap)."""
    if len(x) == 0:
        return [None, None]
    keys, inv = np.unique(day, return_inverse=True)
    s = np.bincount(inv, weights=x, minlength=len(keys))
    m = np.bincount(inv, minlength=len(keys)).astype(float)
    rng = H.seeded_rng(seed)
    pick = rng.integers(len(keys), size=(n_boot, len(keys)))
    est = s[pick].sum(axis=1) / m[pick].sum(axis=1)
    return [float(np.quantile(est, 0.025)), float(np.quantile(est, 0.975))]


def _q(x: np.ndarray) -> dict:
    x = x[~np.isnan(x)]
    if len(x) == 0:
        return {"mean": None, "median": None, "p90": None, "max": None}
    return {"mean": float(x.mean()), "median": float(np.median(x)), "p90": float(np.quantile(x, 0.9)), "max": float(x.max())}


def _cols(sc: str) -> tuple[str, str, str]:
    return ("outcome", "minutes", "net_usd_oz") if sc == PRIMARY else (f"{sc}_outcome", f"{sc}_minutes", f"{sc}_net_usd_oz")


def scorecards(g: pd.DataFrame, sc: str, seq: bool) -> dict:
    """The three registered scorecards for one group (one population, direction and scenario)."""
    oc, mc, nc = _cols(sc)
    g = g[g[oc] != "OPEN"]
    n = len(g)
    if n == 0:
        return {"n": 0}
    out = g[oc].to_numpy()
    tp = out == "TP"
    net = g[nc].to_numpy(float)
    day = _day(g)
    counts = {o: int((out == o).sum()) for o in OUTCOMES[:-1]}
    rate = tp.mean()
    ci = list(H.wilson(int(tp.sum()), n)) if seq else cluster_ci(tp.astype(float), day)
    w, lz = net[tp], net[~tp]
    be = float(-lz.mean() / (w.mean() - lz.mean())) if len(w) and len(lz) and (w.mean() - lz.mean()) != 0 else None
    k = g["k"].to_numpy(float)
    s_ = g["spread"].to_numpy(float) if sc == PRIMARY else None
    pred = {"dir_1h_accuracy": float(np.nanmean(g["dir_1h_correct"])), "dir_4h_accuracy": float(np.nanmean(g["dir_4h_correct"])),
            "brier_constant_forecast": float(rate * (1 - rate)), "n_1h": int(g["dir_1h_correct"].notna().sum()),
            "n_4h": int(g["dir_4h_correct"].notna().sum())}
    ex = {"tp_first": float(rate), "ci95": ci, "sl_first": float((counts["SL"] + counts["AMBIGUOUS"]) / n),
          "counts": counts, "gap_fills": int(g["gap"].sum()) if sc == PRIMARY else None,
          "minutes_to_outcome": _q(g[mc].to_numpy(float)), "minutes_tp": _q(g.loc[tp, mc].to_numpy(float)),
          "minutes_sl": _q(g.loc[out == "SL", mc].to_numpy(float))}
    if sc == PRIMARY:
        ex.update({"mae_all": _q(g["mae_usd"].to_numpy(float)), "mae_winners": _q(g.loc[tp, "mae_usd"].to_numpy(float)),
                   "mfe_all": _q(g["mfe_usd"].to_numpy(float)), "mfe_losers": _q(g.loc[~tp, "mfe_usd"].to_numpy(float)),
                   "entry_vs_decision_close": _q((np.where(g["dir"] == "BUY", 1, -1) * (g["fill_px"] - g["decision_px"]) / k).to_numpy(float))})
    wins, losses = net[net > 0].sum(), net[net < 0].sum()
    prof = {"expectancy_usd_oz": float(net.mean()),
            "expectancy_ci95": (cluster_ci(net, day) if not seq else _t_ci(net)),
            "expectancy_usd_050lot_ASSUMED": float(net.mean() * LOT_OZ),
            "profit_factor": float(wins / -losses) if losses < 0 else None,
            "break_even_tp_rate": be}
    if sc == PRIMARY:
        prof.update({"gross_usd_oz": float(g["gross_usd_oz"].mean()), "cost_usd_oz": float(g["cost_usd_oz"].mean()),
                     "driftless_reference_rate": float(np.mean((MOVE * k - (s_ * k) - g["slip_in"].to_numpy(float) * k) / (2 * MOVE * k)))})
    if seq:
        order = np.argsort(g["fill_utc"].to_numpy(), kind="stable")
        cum = np.cumsum(net[order] * LOT_OZ)
        dd = float(np.max(np.maximum.accumulate(np.r_[0.0, cum])[1:] - cum)) if len(cum) else 0.0
        runs, r = [], 0
        for v in net[order]:
            r = r + 1 if v < 0 else 0
            runs.append(r)
        days = len(np.unique(day))
        prof.update({"max_drawdown_usd_050lot_ASSUMED": dd, "max_drawdown_in_stops": dd / (MOVE * LOT_OZ),
                     "longest_losing_run": int(max(runs) if runs else 0), "net_total_usd_050lot_ASSUMED": float(cum[-1]),
                     "trades_per_trading_day": n / days if days else None, "trading_days": days})
    return {"n": n, "prediction": pred, "execution": ex, "profitability": prof}


def _t_ci(x: np.ndarray) -> list:
    if len(x) < 2:
        return [None, None]
    se = x.std(ddof=1) / math.sqrt(len(x))
    return [float(x.mean() - 1.96 * se), float(x.mean() + 1.96 * se)]


def breakdown(df: pd.DataFrame, sc: str, col: str) -> dict:
    oc, _, nc = _cols(sc)
    out = {}
    for dn in DIRS.values():
        for key, g in df[(df["dir"] == dn) & (df[oc] != "OPEN")].groupby(col):
            tp = (g[oc] == "TP").to_numpy(float)
            day = _day(g)
            out[f"{dn} {key}"] = {"n": len(g), "tp_first": float(tp.mean()), "ci95": cluster_ci(tp, day),
                                  "expectancy_usd_oz": float(g[nc].mean()), "days": len(np.unique(day))}
    return out


def summarize(df: pd.DataFrame) -> dict:
    res = {"entries_per_direction": int((df["dir"] == "BUY").sum()), "window": [
        str(pd.Timestamp(int(df["fill_utc"].min()), unit="s", tz="UTC")), str(pd.Timestamp(int(df["fill_utc"].max()), unit="s", tz="UTC"))],
        "open_at_end": int((df["outcome"] == "OPEN").sum()), "all_bar": {}, "sequential": {}, "by": {}}
    for sc in SCENARIOS:
        for dn in DIRS.values():
            g = df[df["dir"] == dn]
            res["all_bar"][f"{sc} {dn}"] = scorecards(g, sc, seq=False)
            res["sequential"][f"{sc} {dn}"] = scorecards(g[g[f"in_seq_{sc}"]], sc, seq=True)
    for col in ("session", "weekday", "vol_tercile", "trend_rel", "news"):
        res["by"][col] = {sc: breakdown(df, sc, col) for sc in ("GROSS", PRIMARY)}
    return res


def gross_symmetry(df: pd.DataFrame) -> dict:
    """Labeller check (not a test of the market): on mid prices, a BUY wins exactly when the SELL from the same bar
    loses, unless one bar reached both levels or the trade timed out / met a closure."""
    b = df[df["dir"] == "BUY"].set_index("dec_i")["GROSS_outcome"]
    s = df[df["dir"] == "SELL"].set_index("dec_i")["GROSS_outcome"]
    j = b.index.intersection(s.index)
    b, s = b.loc[j], s.loc[j]
    clean = (b.isin(["TP", "SL"])) & (s.isin(["TP", "SL"]))
    agree = ((b == "TP") == (s == "SL"))[clean]
    return {"pairs": len(j), "clean_pairs": int(clean.sum()), "mirror_share": float(agree.mean()) if clean.any() else None}


def resolution_check(pop3: dict) -> dict:
    """Registered check on the P3 window: decisions at 15m closes resolved on 15m bars vs on 5m bars."""
    df5 = pop3["bars"]
    m15 = sources.resample_ohlc(df5, "15min")
    P15, P5 = make_path(m15, 900), make_path(df5, 300)
    el = np.flatnonzero(eligible(P15, int(pop3["score_from"].timestamp())))
    t15, t5 = np.asarray(P15.t), np.asarray(P5.t)
    f15 = el + 1
    f5 = np.searchsorted(t5, t15[f15])
    ok = (f5 < len(t5)) & (t5[np.clip(f5, 0, len(t5) - 1)] == t15[f15])
    el, f15, f5 = el[ok], f15[ok], f5[ok]
    idx = pd.to_datetime(t15[f15], unit="s", utc=True)
    costs = scenario_costs(idx, np.ones(len(el)))
    out = {"decisions": len(el)}
    for sc in ("GROSS", PRIMARY):
        s_, si_, so_, _ = costs[sc]
        for d, dn in DIRS.items():
            a = np.array([race(P15, int(f15[x]), d, s_[x], si_[x], so_[x], 1.0, HORIZON["15m"])[0] for x in range(len(el))])
            b = np.array([race(P5, int(f5[x]), d, s_[x], si_[x], so_[x], 1.0, HORIZON["5m"])[0] for x in range(len(el))])
            m = (a != OPEN) & (b != OPEN)
            out[f"{sc} {dn}"] = {"n": int(m.sum()), "tp_first_15m": float((a[m] == TP).mean()), "tp_first_5m": float((b[m] == TP).mean()),
                                 "ambiguous_15m": float((a[m] == AMB).mean()), "ambiguous_5m": float((b[m] == AMB).mean()),
                                 "outcome_differs": float((a[m] != b[m]).mean())}
    return out


# ---------------- files ----------------
def _clean(x):
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not math.isfinite(float(x)) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


CSV_COLS = ["pop", "tf", "dir", "nyday", "decision_utc", "decision_px", "fill_utc", "fill_mid", "k", "fill_px", "tp_px", "sl_px", "outcome",
            "gap", "exit_utc", "exit_px", "minutes", "mfe_usd", "mae_usd", "spread", "slip_in", "slip_out", "commission",
            "gross_usd_oz", "cost_usd_oz", "net_usd_oz", "net_usd_050lot", "GROSS_outcome", "GROSS_net_usd_oz", "OP_outcome",
            "OP_net_usd_oz", "ADV_outcome", "ADV_net_usd_oz", "session", "weekday", "vol_tercile", "trend_state", "trend_rel",
            "news", "dir_1h_correct", "dir_4h_correct", "in_seq_GROSS", "in_seq_OP", "in_seq_ENG", "in_seq_ADV"]


def write_csv(df: pd.DataFrame, path: str) -> None:
    out = df[CSV_COLS].copy()
    for col in ("decision_utc", "fill_utc", "exit_utc"):
        out[col] = pd.to_datetime(out[col], unit="s", utc=True).dt.strftime("%Y-%m-%d %H:%M:%S")
    out.sort_values(["fill_utc", "dir"]).to_csv(path, index=False, float_format="%.4f",
                                                 compression="gzip" if path.endswith(".gz") else None)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True)
    ap.add_argument("--store5", required=True)
    ap.add_argument("--store60")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pops", default="P1,P2,P3")
    ap.add_argument("--trials")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    pops = populations(a.rd, a.store5, a.store60, tuple(a.pops.split(",")))
    out = {"registration": REG, "utc": datetime.now(timezone.utc).isoformat(), "populations": {}}
    for name, pop in pops.items():
        df = run_population(name, pop)
        write_csv(df, os.path.join(a.out, f"b26_trades_{name}.csv.gz"))
        res = summarize(df)
        res.update({"label": pop["label"], "data_hash": H.data_hash(pop["bars"]), "bars": len(pop["bars"]),
                    "gross_symmetry_check": gross_symmetry(df)})
        if name == "P3":
            res["resolution_check"] = resolution_check(pop)
        out["populations"][name] = res
        print(name, {k: (v["execution"]["tp_first"], v["n"]) for k, v in res["sequential"].items() if v.get("n")}, flush=True)
    with open(os.path.join(a.out, "b26_summary.json"), "w") as fh:
        json.dump(_clean(out), fh, indent=1, allow_nan=False)
    if a.trials:
        for name, res in out["populations"].items():
            for kind in ("all_bar", "sequential"):
                for key, v in res[kind].items():
                    if not v.get("n"):
                        continue
                    H.log_trial(a.trials, {"phase": REG, "partition": "development" if name == "P1" else f"unsealed {name}",
                                           "id": f"B26 {name} {kind} {key}", "n": v["n"], "success": v["execution"]["tp_first"],
                                           "ci95": v["execution"]["ci95"], "net_usd_per_oz": v["profitability"]["expectancy_usd_oz"],
                                           "note": "baseline (no rule, no selection)"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
