"""G3-NEWS (research/registrations/G3-NEWS.json): major USD releases and the frozen engine's trades on the DEVELOPMENT
partition. RESEARCH ONLY: never imported by production; production news blocking stays OFF; the engine runs unchanged.

  python -m quantum.research.g3_news --rd <research-data checkout> --calendar research/g3_calendar/official.json
                                     --out research/G3_NEWS_RESULTS.json [--trials research/trials.jsonl]

Event timestamps: an event enters only when its date agrees in B8's committed dates (CPI, NFP, FOMC) and the independent
reading of the official calendars (--calendar); PCE, GDP and RETAIL need the official reading and B8's market-reaction
check (release-bar range at least 1.5 x the median of the same clock-time bar on non-event weekdays). Every
disagreement is listed. The engine's block of a trade is first-order here: removed trades are taken out of the
recorded sequence without re-simulating the one-position rule (stated in the results).
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .. import arm_h4, backtest, config, engine
from ..data import sources
from ..features import compute as compute_features
from . import b8_news, b10, history
from . import harness as H

REG = "G3-NEWS"
NY = ZoneInfo("America/New_York")
TFS = {"15m": 900, "30m": 1800, "1h": 3600}
TIMES = {"CPI": time(8, 30), "NFP": time(8, 30), "FOMC_STATEMENT": time(14, 0), "FOMC_PRESS": time(14, 30),
         "PCE": time(8, 30), "GDP": time(8, 30), "RETAIL": time(8, 30)}
WINDOWS = {"PRE": (-30, 0), "DURING": (0, 15), "POST": (15, 60), "LATE": (60, 120)}
BLOCKS = {"no entry -15..+15": (-15, 15), "no entry -30..+30": (-30, 30), "no entry -30..+60": (-30, 60), "no hold across": None}
MATCH_MIN, MATCH_DAYS, RATIO_MIN = 30, 20, b8_news.RATIO_MIN
TARGETS = (10.0, 15.0, 20.0)
HORIZON = 7 * 86400
SEED = 20261128
DEV = H.DEV


# ---------------- events and their verification ----------------
def utc(kind: str, day: str) -> int:
    d = date.fromisoformat(day)
    return int(datetime.combine(d, TIMES[kind], tzinfo=NY).timestamp())


def _in_dev(day: str) -> bool:
    t = pd.Timestamp(day, tz="UTC")
    return DEV[0] <= t < DEV[1]


def verify(official: dict) -> dict:
    """Source A (B8's committed dates) against source B (the official reading). Returns the agreed events and every
    disagreement. FOMC_PRESS takes the official press-conference dates; PCE / GDP / RETAIL take the official dates
    (their market check is applied later, with the bars)."""
    a = {"CPI": set(b8_news.DATES["CPI"]), "NFP": set(b8_news.DATES["NFP"]), "FOMC_STATEMENT": set(b8_news.DATES["FOMC"])}
    b = {"CPI": set(official.get("CPI", {}).get("dates", [])), "NFP": set(official.get("NFP", {}).get("dates", [])),
         "FOMC_STATEMENT": set(official.get("FOMC", {}).get("statement_dates", [])),
         "FOMC_PRESS": set(official.get("FOMC", {}).get("press_conference_dates", [])),
         "PCE": set(official.get("PCE", {}).get("dates", [])), "GDP": set(official.get("GDP", {}).get("dates", [])),
         "RETAIL": set(official.get("RETAIL", {}).get("dates", []))}
    out = {"agreed": [], "disagreements": [], "counts": {}}
    for kind in TIMES:
        bb = {d for d in b.get(kind, set()) if _in_dev(d)}
        if kind in a:
            aa = {d for d in a[kind] if _in_dev(d)}
            both = sorted(aa & bb)
            out["disagreements"] += [{"kind": kind, "date": d, "in": "B8 only"} for d in sorted(aa - bb)]
            out["disagreements"] += [{"kind": kind, "date": d, "in": "official only"} for d in sorted(bb - aa)]
            if not bb:
                out["disagreements"].append({"kind": kind, "date": None, "in": "official reading unavailable: kind excluded"})
                both = []
        else:
            both = sorted(bb)
            if not bb:
                out["disagreements"].append({"kind": kind, "date": None, "in": "official reading unavailable: kind excluded"})
        out["agreed"] += [{"kind": kind, "date": d, "t": utc(kind, d), "needs_market_check": kind in ("PCE", "GDP", "RETAIL")}
                          for d in both]
        out["counts"][kind] = len(both)
    return out


def market_ratio(m15: pd.DataFrame, t: int, event_days: set) -> float | None:
    """B8's check: the 15-minute bar opening at the release, its range over the median range of the same clock-time bar
    on the 40 nearest weekdays without a listed event."""
    idx = pd.DatetimeIndex(m15.index)
    tt = idx.as_unit("s").asi8
    k = int(np.searchsorted(tt, t))
    if k >= len(tt) or tt[k] != t:
        return None
    rng = (m15["high"] - m15["low"]).to_numpy(float)
    ny = idx.tz_convert(NY)
    hm = ny.hour * 60 + ny.minute
    tl = datetime.fromtimestamp(t, NY)
    same = np.flatnonzero((hm == tl.hour * 60 + tl.minute) & (ny.dayofweek < 5))
    same = [j for j in same if ny[j].date().isoformat() not in event_days and j != k]
    same = sorted(same, key=lambda j: abs(int(tt[j]) - t))[:40]
    if len(same) < 10:
        return None
    med = float(np.median(rng[same]))
    return float(rng[k] / med) if med > 0 else None


# ---------------- helpers ----------------
def _p5(m5: pd.DataFrame) -> dict:
    ix = pd.DatetimeIndex(m5.index)
    return {"t": ix.as_unit("s").asi8.astype(np.int64), "o": m5["open"].to_numpy(float), "h": m5["high"].to_numpy(float),
            "l": m5["low"].to_numpy(float), "c": m5["close"].to_numpy(float)}


def ny_day(t: int) -> str:
    return datetime.fromtimestamp(t, NY).date().isoformat()


def clock_min(t: int) -> int:
    d = datetime.fromtimestamp(t, NY)
    return d.hour * 60 + d.minute


def window_of(t: int, events: list[dict]) -> tuple[str, dict | None]:
    """The window an instant falls in, relative to the nearest listed event (NORMAL if none)."""
    best = None
    for e in events:
        dm = (t - e["t"]) / 60.0
        for w, (a, b) in WINDOWS.items():
            if a <= dm < b and (best is None or abs(dm) < abs(best[2])):
                best = (w, e, dm)
    return ("NORMAL", None) if best is None else (best[0], best[1])


def race(P5: dict, t0: int, long: bool, entry: float, stop: float, target: float) -> str:
    j0 = int(np.searchsorted(P5["t"], t0))
    j1 = int(np.searchsorted(P5["t"], t0 + HORIZON))
    o, h, l = P5["o"][j0:j1], P5["h"][j0:j1], P5["l"][j0:j1]
    if not len(o):
        return "NONE"
    s = (l <= stop) | (o <= stop) if long else (h >= stop) | (o >= stop)
    g = (h >= target) | (o >= target) if long else (l <= target) | (o <= target)
    ks = int(np.argmax(s)) if s.any() else None
    kg = int(np.argmax(g)) if g.any() else None
    if kg is not None and (ks is None or kg < ks):
        return "TARGET"
    return "STOP" if ks is not None else "UNDECIDED"


def boot_mean(vals: list[float], rng, sims: int = 4000) -> dict:
    v = np.asarray(vals, float)
    if len(v) < 2:
        return {"n": len(v), "mean": None if not len(v) else round(float(v.mean()), 4), "ci95": None, "p_two_sided": None}
    pick = rng.integers(0, len(v), size=(sims, len(v)))
    m = v[pick].mean(1)
    p = 2 * min(float(np.mean(m <= 0)), float(np.mean(m >= 0)))
    return {"n": len(v), "mean": round(float(v.mean()), 4), "ci95": [round(float(np.quantile(m, 0.025)), 4),
            round(float(np.quantile(m, 0.975)), 4)], "p_two_sided": round(min(1.0, p), 6)}


def controls(t: int, pool_t: np.ndarray, pool_ok: np.ndarray) -> np.ndarray:
    """Indices of pool items at the same New York clock time (+-MATCH_MIN) within +-MATCH_DAYS days, on non-event days."""
    cm = clock_min(t)
    near = np.flatnonzero(pool_ok & (np.abs(pool_t - t) <= MATCH_DAYS * 86400))
    return np.array([j for j in near if abs(clock_min(int(pool_t[j])) - cm) <= MATCH_MIN], int)


def holm(ps: list[float]) -> list[float]:
    m = len(ps)
    order = np.argsort(ps)
    adj, run = np.empty(m), 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (m - rank) * ps[i]))
        adj[i] = run
    return [round(float(x), 6) for x in adj]


def bh(ps: list[float]) -> list[float]:
    m = len(ps)
    order = np.argsort(ps)[::-1]
    adj, run = np.empty(m), 1.0
    for rank, i in zip(range(m, 0, -1), order, strict=True):
        run = min(run, ps[i] * m / rank)
        adj[i] = run
    return [round(float(x), 6) for x in adj]


# ---------------- measurements ----------------
def volatility(P5: dict, events: list[dict], event_days: set, rng) -> dict:
    t, h, l, o, c = P5["t"], P5["h"], P5["l"], P5["o"], P5["c"]
    ok_day = np.array([ny_day(int(x)) not in event_days and datetime.fromtimestamp(int(x), NY).weekday() < 5 for x in t])
    out = {}
    for kind in TIMES:
        evs = [e for e in events if e["kind"] == kind]
        for w, (a, b) in WINDOWS.items():
            ratios = []
            for e in evs:
                sel = (t >= e["t"] + a * 60) & (t < e["t"] + b * 60)
                if sel.sum() == 0:
                    continue
                ev_rng = float(np.mean(h[sel] - l[sel]))
                cm0, cm1 = clock_min(e["t"]) + a, clock_min(e["t"]) + b
                ctl = ok_day & (np.abs(t - e["t"]) <= MATCH_DAYS * 86400)
                cmins = np.array([clock_min(int(x)) for x in t[ctl]])
                idx = np.flatnonzero(ctl)[(cmins >= cm0) & (cmins < cm1)]
                if len(idx) < 3:
                    continue
                base = float(np.mean(h[idx] - l[idx]))
                if base > 0:
                    ratios.append(math.log(ev_rng / base))
            bm = boot_mean(ratios, rng)
            out[f"{kind}|{w}"] = {"events": bm["n"], "mean_range_ratio": None if bm["mean"] is None else round(math.exp(bm["mean"]), 3),
                                  "ratio_ci95": None if bm["ci95"] is None else [round(math.exp(x), 3) for x in bm["ci95"]],
                                  "p_two_sided": bm["p_two_sided"]}
            _ = (o, c)
    return out


def trades_for(res, cfg) -> dict:
    tr = {"treatment": [t for t in backtest.simulate(res, cfg) if not t.get("open")]}
    h4, _ = arm_h4.simulate(res, cfg)
    tr["h4"] = [t for t in h4 if not t.get("open")]
    return tr


def by_window(trades: list[dict], tf_sec: int, events: list[dict], event_days: set, P5: dict, rng) -> dict:
    """Mean net R and target-before-stop by entry window, each event-window trade against its matched controls."""
    fills = np.array([int(pd.Timestamp(t["entry_time"]).timestamp()) + tf_sec for t in trades], np.int64)
    wins = [window_of(int(f), events) for f in fills]
    normal = np.array([w[0] == "NORMAL" and ny_day(int(f)) not in event_days for w, f in zip(wins, fills, strict=True)])
    r = np.array([t["r"] for t in trades], float)
    d = np.array([1 if t["dir"] == "LONG" else -1 for t in trades])
    out = {}
    for w in WINDOWS:
        diffs, ev_r, tgt = {}, [], {x: [0, 0] for x in TARGETS}
        for i in np.flatnonzero([x[0] == w for x in wins]):
            ctl = controls(int(fills[i]), fills, normal & (d == d[i]))
            ev_r.append(r[i])
            if len(ctl):
                diffs.setdefault(wins[i][1]["kind"] + wins[i][1]["date"], []).append(r[i] - float(r[ctl].mean()))
            t = trades[i]
            lg = t["dir"] == "LONG"
            for x in TARGETS:
                px = t["entry"] + (x if lg else -x) * t["entry"] / 4000.0
                res = race(P5, int(fills[i]), lg, t["entry"], t["sl"], px)
                if res in ("TARGET", "STOP"):
                    tgt[x][0] += res == "TARGET"
                    tgt[x][1] += 1
        per_event = [float(np.mean(v)) for v in diffs.values()]
        bm = boot_mean(per_event, rng)
        out[w] = {"trades": len(ev_r), "events_with_controls": len(per_event),
                  "mean_net_r": round(float(np.mean(ev_r)), 4) if ev_r else None,
                  "diff_vs_matched_normal": bm,
                  "targets": {f"usd{int(x)}": {"target_first": a, "decided": b, "rate": round(a / b, 4) if b else None,
                                               "wilson95": [round(y, 4) for y in H.wilson(a, b)] if b else None}
                              for x, (a, b) in tgt.items()}}
    nn = np.flatnonzero(normal)
    tg = {}
    for x in TARGETS:
        a = b = 0
        for i in nn[::max(1, len(nn) // 2000)]:
            t = trades[i]
            lg = t["dir"] == "LONG"
            res = race(P5, int(fills[i]), lg, t["entry"], t["sl"], t["entry"] + (x if lg else -x) * t["entry"] / 4000.0)
            if res in ("TARGET", "STOP"):
                a += res == "TARGET"
                b += 1
        tg[f"usd{int(x)}"] = {"target_first": a, "decided": b, "rate": round(a / b, 4) if b else None}
    out["NORMAL"] = {"trades": int(normal.sum()), "mean_net_r": round(float(r[normal].mean()), 4) if normal.any() else None,
                     "targets_sampled": tg}
    return out


def stop_behaviour(trades: list[dict], tf_sec: int, events: list[dict]) -> dict:
    """Trades whose life [fill, exit bar close) contains a release (a fill at the release included) against the rest."""
    ev_t = np.array([e["t"] for e in events], np.int64)
    rows = {"with_release": [], "without": []}
    for t in trades:
        a = int(pd.Timestamp(t["entry_time"]).timestamp()) + tf_sec
        b = int(pd.Timestamp(t["exit_time"]).timestamp()) + tf_sec
        inside = bool(np.any((ev_t >= a) & (ev_t < b)))
        rows["with_release" if inside else "without"].append(t)
    out = {}
    for k, g in rows.items():
        n = len(g)
        stopped = [t for t in g if t["exit_reason"] in ("SL", "SL_GAP", "BE", "BE_GAP")]
        gaps = [t for t in g if t["exit_reason"] in ("SL_GAP", "BE_GAP")]
        past = [abs(t["exit"] - t["sl"]) for t in gaps if t["exit_reason"] == "SL_GAP"]
        out[k] = {"trades": n, "stopped": len(stopped), "stopped_share": round(len(stopped) / n, 4) if n else None,
                  "stopped_wilson95": [round(y, 4) for y in H.wilson(len(stopped), n)] if n else None,
                  "gap_exits": len(gaps), "gap_share": round(len(gaps) / n, 4) if n else None,
                  "mean_gap_beyond_stop_usd": round(float(np.mean(past)), 3) if past else None,
                  "mean_net_r": round(float(np.mean([t["r"] for t in g])), 4) if g else None}
    return out


def liquidity(res, F, events: list[dict], event_days: set, P5: dict, rng) -> dict:
    idx = pd.DatetimeIndex(F["index"])
    tt = idx.as_unit("s").asi8 + 900
    c = np.asarray(F["c"], float)
    out = {}
    for kind in ("BREAK", "GRAB"):
        ii, dd = b10.liquidity_events(res, F, kind, None)
        ok = []
        for i, d in zip(ii, dd, strict=True):
            t0 = int(tt[i])
            w = window_of(t0, events)[0]
            x = 10.0 * c[i] / 4000.0
            r = race(P5, t0, d == 1, c[i], c[i] - d * x, c[i] + d * x)
            ok.append((w, r, ny_day(t0) in event_days))
        cell = {}
        for w in [*WINDOWS, "NORMAL"]:
            g = [r for ww, r, evd in ok if ww == w and (w != "NORMAL" or not evd)]
            dec = [r for r in g if r in ("TARGET", "STOP")]
            k = sum(r == "TARGET" for r in dec)
            cell[w] = {"events": len(g), "decided": len(dec), "plus10_first": k, "rate": round(k / len(dec), 4) if dec else None,
                       "wilson95": [round(y, 4) for y in H.wilson(k, len(dec))] if dec else None}
        out[kind] = cell
    return out


def blocks(trades: list[dict], tf_sec: int, events: list[dict], P5: dict, rng) -> dict:
    ev_t = np.array([e["t"] for e in events], np.int64)
    fills = np.array([int(pd.Timestamp(t["entry_time"]).timestamp()) + tf_sec for t in trades], np.int64)
    exits = np.array([int(pd.Timestamp(t["exit_time"]).timestamp()) + tf_sec for t in trades], np.int64)
    r = np.array([t["r"] for t in trades], float)
    days = np.array([ny_day(int(x)) for x in exits])
    out = {}
    for name, win in BLOCKS.items():
        if win is None:                                  # positions opened BEFORE a release and still open at it
            rm = np.array([bool(np.any((ev_t > a) & (ev_t < b))) for a, b in zip(fills, exits, strict=True)])
        else:
            a, b = win
            rm = np.array([bool(np.any((f >= ev_t + a * 60) & (f < ev_t + b * 60))) for f in fills])
        kept = ~rm
        tp1 = 0
        for i in np.flatnonzero(rm):
            t = trades[i]
            tp1 += race(P5, int(fills[i]), t["dir"] == "LONG", t["entry"], t["sl"], t["tp1"]) == "TARGET"
        # paired day-block bootstrap of the change in mean net R (kept set minus all)
        u = sorted(set(days))
        pos = {d: k for k, d in enumerate(u)}
        s_all, n_all, s_k, n_k = np.zeros(len(u)), np.zeros(len(u)), np.zeros(len(u)), np.zeros(len(u))
        for x, dday, kk in zip(r, days, kept, strict=True):
            j = pos[dday]
            s_all[j] += x
            n_all[j] += 1
            if kk:
                s_k[j] += x
                n_k[j] += 1
        pick = rng.integers(0, len(u), size=(4000, len(u)))
        delta = s_k[pick].sum(1) / np.maximum(n_k[pick].sum(1), 1) - s_all[pick].sum(1) / np.maximum(n_all[pick].sum(1), 1)
        p = 2 * min(float(np.mean(delta <= 0)), float(np.mean(delta >= 0)))
        out[name] = {"removed": int(rm.sum()), "removed_mean_net_r": round(float(r[rm].mean()), 4) if rm.any() else None,
                     "removed_tp1_first": tp1, "false_exclusion_share": round(tp1 / rm.sum(), 4) if rm.any() else None,
                     "kept": int(kept.sum()), "kept_mean_net_r": round(float(r[kept].mean()), 4) if kept.any() else None,
                     "all_mean_net_r": round(float(r.mean()), 4) if len(r) else None,
                     "change_mean_net_r": round(float(r[kept].mean() - r.mean()), 4) if kept.any() and len(r) else None,
                     "change_ci95": [round(float(np.quantile(delta, 0.025)), 4), round(float(np.quantile(delta, 0.975)), 4)],
                     "p_two_sided": round(min(1.0, p), 6),
                     "note": "first-order: removed trades are taken out without re-simulating the one-position rule"}
    return out


# ---------------- the run ----------------
def run(rd: str, official: dict, trials: str | None = None, log=print) -> dict:
    rng = H.seeded_rng(SEED)
    m15 = H.partition(history.load(rd, "XAU/USD", "15min"), "development")
    h1 = H.partition(history.load(rd, "XAU/USD", "1h"), "development")
    m5 = H.partition(history.load(rd, "XAU/USD", "5min"), "development")
    P5 = _p5(m5)
    v = verify(official)
    days_all = {e["date"] for e in v["agreed"]}
    events, checked = [], []
    for e in v["agreed"]:
        ratio = market_ratio(m15, e["t"], days_all) if e["t"] % 900 == 0 else None
        e = {**e, "market_ratio": None if ratio is None else round(ratio, 3)}
        checked.append(e)
        if e["needs_market_check"] and (ratio is None or ratio < RATIO_MIN):
            continue
        events.append(e)
    event_days = {e["date"] for e in events}
    log(f"[G3] events kept {len(events)} of {len(v['agreed'])} agreed; disagreements {len(v['disagreements'])}")
    out = {"registration": REG, "partition": "development", "window": [str(m15.index[0]), str(m15.index[-1])],
           "data_hashes": {"15m": H.data_hash(m15), "1h": H.data_hash(h1), "5m": H.data_hash(m5)}, "seed": SEED,
           "utc": datetime.now(timezone.utc).isoformat(),
           "calendar": {"sources": {k: official.get(k, {}).get("source") for k in ("CPI", "NFP", "FOMC", "PCE", "GDP", "RETAIL")},
                        "agreed_counts": v["counts"], "disagreements": v["disagreements"],
                        "kept_counts": {k: sum(e["kind"] == k for e in events) for k in TIMES},
                        "market_ratio_below_min": [e for e in checked if e["market_ratio"] is not None and e["market_ratio"] < RATIO_MIN],
                        "events": checked},
           "volatility": volatility(P5, events, event_days, rng),
           "spread": "UNAVAILABLE: no bid / ask in the feed (mid prices only)",
           "liquidity_volume": "UNAVAILABLE: no volume stored for 2020-2022",
           "arms": {}}
    bases = {"15m": m15, "30m": sources.resample_ohlc(m15, "30min"), "1h": h1}
    for tf, base in bases.items():
        m = b10.make_market(base, h1, tf, TFS[tf])
        F = compute_features(m, config.DEFAULT)
        res = engine.run(m, config.DEFAULT, "treatment", F)
        tr = trades_for(res, config.DEFAULT)
        for arm, trades in tr.items():
            out["arms"][f"{arm}|{tf}"] = {"trades": len(trades),
                                          "by_entry_window": by_window(trades, TFS[tf], events, event_days, P5, rng),
                                          "stop_behaviour": stop_behaviour(trades, TFS[tf], events),
                                          "blocks": blocks(trades, TFS[tf], events, P5, rng)}
            log(f"[G3] {arm} {tf}: {len(trades)} trades")
        if tf == "15m":
            out["liquidity_events_15m"] = liquidity(res, F, events, event_days, P5, rng)
    # multiple testing: the three declared families, Holm within each, BH across all
    fam = {"volatility": [(k, x["p_two_sided"]) for k, x in out["volatility"].items()],
           "entry_window": [(f"{a}|{w}", x["by_entry_window"][w]["diff_vs_matched_normal"]["p_two_sided"])
                            for a, x in out["arms"].items() for w in WINDOWS],
           "blocks": [(f"{a}|{b}", x["blocks"][b]["p_two_sided"]) for a, x in out["arms"].items() for b in BLOCKS]}
    allp = []
    out["multiple_testing"] = {}
    for f, items in fam.items():
        ok = [(k, p) for k, p in items if p is not None]
        ho = holm([p for _, p in ok]) if ok else []
        out["multiple_testing"][f] = [{"test": k, "p": p, "p_holm": h} for (k, p), h in zip(ok, ho, strict=True)]
        allp += [(f, k, p) for k, p in ok]
    b_all = bh([p for _, _, p in allp]) if allp else []
    out["multiple_testing"]["bh_all"] = [{"family": f, "test": k, "p": p, "p_bh": q} for (f, k, p), q in zip(allp, b_all, strict=True)]
    if trials:
        for f, items in out["multiple_testing"].items():
            if f == "bh_all":
                continue
            for x in items:
                H.log_trial(trials, {"reg": REG, "part": "development", "family": f, "test": x["test"], "p": x["p"],
                                     "p_holm": x["p_holm"], "data_hash_15m": out["data_hashes"]["15m"]})
    out["decision"] = "NONE for production: news blocking stays OFF (registration 'decision')"
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rd", required=True)
    ap.add_argument("--calendar", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials")
    a = ap.parse_args(argv)
    with open(a.calendar) as f:
        official = json.load(f)
    out = run(a.rd, official, a.trials)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=1, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
