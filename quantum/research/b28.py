"""B28 (research/registrations/B28.json, committed ffc0b6857 before this code): Track A, fixed +$15 / -$15, the eight
hypotheses B1-B27 did not test, each with every entry mechanism (B27's machinery, confirmation at $3/5/8/10/15/20).

RESEARCH ONLY: never imported by production (tests/test_integrity.py).

  python -m quantum.research.b28 --rd <research-data> --store5 <XAU_USD_5m> --store60 <XAU_USD_60m> --out <dir> [--trials ...]
"""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .. import ta
from . import b26, b27
from . import harness as H

REG = "B28"
XS = (3, 5, 8, 10, 15, 20)
FAMILIES = ("LONDON_ORB", "NY_ORB", "ENGULF_LEVEL", "PINBAR_LEVEL", "CHOCH_RETEST", "OB_RETEST", "SWEEP_DISPLACEMENT", "SUPERTREND")
MAX_INFORMATIVE, TOP_BIG, TOP_SMALL = 20, 5, 5


# ---------------- the new events (all from bars closed at or before the row's bar) ----------------
def supertrend(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int = 10, mult: float = 3.0) -> tuple[np.ndarray, np.ndarray]:
    """Standard Supertrend on closes: (trend +1 / -1, line). The trend flips up when the close crosses above the previous
    final upper band, down when it crosses below the previous final lower band."""
    atr = ta.atr(h, l, c, n)
    hl2 = (h + l) / 2
    ub, lb = hl2 + mult * atr, hl2 - mult * atr
    m = len(c)
    fub, flb = np.full(m, np.nan), np.full(m, np.nan)
    trend = np.zeros(m)
    for i in range(m):
        if np.isnan(atr[i]):
            continue
        if i == 0 or np.isnan(fub[i - 1]):
            fub[i], flb[i], trend[i] = ub[i], lb[i], 1.0
            continue
        fub[i] = ub[i] if (ub[i] < fub[i - 1] or c[i - 1] > fub[i - 1]) else fub[i - 1]
        flb[i] = lb[i] if (lb[i] > flb[i - 1] or c[i - 1] < flb[i - 1]) else flb[i - 1]
        if trend[i - 1] < 0 and c[i] > fub[i - 1]:
            trend[i] = 1.0
        elif trend[i - 1] > 0 and c[i] < flb[i - 1]:
            trend[i] = -1.0
        else:
            trend[i] = trend[i - 1]
    return trend, np.where(trend > 0, flb, fub)


def _orb(idx: pd.DatetimeIndex, h, l, c, tz: str, start: tuple[int, int], end: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    """Opening range = the two 15m bars from `start` local time; the first 15m close beyond it from 30 minutes after
    `start` until `end` (local), once per local day; a day without both range bars has no event."""
    loc = idx.tz_convert(tz)
    mins = loc.hour.to_numpy() * 60 + loc.minute.to_numpy()
    day = loc.tz_localize(None).normalize()
    s0, e0 = start[0] * 60 + start[1], end[0] * 60 + end[1]
    in_rng = (mins >= s0) & (mins < s0 + 30)
    g = pd.DataFrame({"h": h[in_rng], "l": l[in_rng]}, index=day[in_rng]).groupby(level=0).agg(
        hi=("h", "max"), lo=("l", "min"), n=("h", "size"))
    ev, lv = np.zeros(len(c)), np.full(len(c), np.nan)
    done = set()
    for i in np.flatnonzero((mins >= s0 + 30) & (mins < e0)):
        key = day[i]
        if key in done or key not in g.index or g.at[key, "n"] != 2:
            continue
        hi, lo = g.at[key, "hi"], g.at[key, "lo"]
        if c[i] > hi:
            ev[i], lv[i] = 1.0, hi
            done.add(key)
        elif c[i] < lo:
            ev[i], lv[i] = -1.0, lo
            done.add(key)
    return ev, lv


def new_events(m15: pd.DataFrame, F: pd.DataFrame) -> pd.DataFrame:
    """The eight B28 trigger families: ev_<family> (signed) and lv_<family> (the limit level)."""
    o, h, l, c = (m15[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    n = len(c)
    idx = m15.index
    atr = ta.atr(h, l, c, 14)
    rng, body = h - l, np.abs(c - o)
    out = {}

    out["ev_LONDON_ORB"], out["lv_LONDON_ORB"] = _orb(idx, h, l, c, "Europe/London", (8, 0), (11, 0))
    out["ev_NY_ORB"], out["lv_NY_ORB"] = _orb(idx, h, l, c, "America/New_York", (9, 30), (12, 0))

    tday = (idx.tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7)).normalize()
    df = pd.DataFrame({"h": h, "l": l}, index=idx)
    dd = df.groupby(tday).agg(hi=("h", "max"), lo=("l", "min")).shift(1)
    pdh = pd.Series(tday, index=idx).map(dd["hi"]).to_numpy(float)
    pdl = pd.Series(tday, index=idx).map(dd["lo"]).to_numpy(float)
    hour, uday = idx.hour.to_numpy(), idx.normalize()
    asia = df[hour < 7].groupby(uday[hour < 7]).agg(hi=("h", "max"), lo=("l", "min"))
    a_hi = np.where(hour >= 7, pd.Series(uday, index=idx).map(asia["hi"]).to_numpy(float), np.nan)
    a_lo = np.where(hour >= 7, pd.Series(uday, index=idx).map(asia["lo"]).to_numpy(float), np.nan)
    hh20 = pd.Series(h).shift(1).rolling(20).max().to_numpy()
    ll20 = pd.Series(l).shift(1).rolling(20).min().to_numpy()

    def at_support(i: int) -> bool:
        for s in (pdl[i], a_lo[i], ll20[i]):
            if not np.isnan(s) and (abs(l[i] - s) <= 0.5 * atr[i] or l[i] < s <= c[i]):
                return True
        return False

    def at_resist(i: int) -> bool:
        for s in (pdh[i], a_hi[i], hh20[i]):
            if not np.isnan(s) and (abs(h[i] - s) <= 0.5 * atr[i] or c[i] <= s < h[i]):
                return True
        return False

    eng, lv_eng = np.zeros(n), np.full(n, np.nan)
    pin, lv_pin = np.zeros(n), np.full(n, np.nan)
    for i in range(1, n):
        a = atr[i]
        if np.isnan(a) or rng[i] <= 0:
            continue
        bull_e = c[i - 1] < o[i - 1] and c[i] > o[i] and body[i] >= body[i - 1] and o[i] <= c[i - 1] and c[i] >= o[i - 1] and body[i] >= 0.5 * a
        bear_e = c[i - 1] > o[i - 1] and c[i] < o[i] and body[i] >= body[i - 1] and o[i] >= c[i - 1] and c[i] <= o[i - 1] and body[i] >= 0.5 * a
        if bull_e and at_support(i):
            eng[i], lv_eng[i] = 1.0, o[i] + 0.5 * (c[i] - o[i])
        elif bear_e and at_resist(i):
            eng[i], lv_eng[i] = -1.0, o[i] + 0.5 * (c[i] - o[i])
        low_w, up_w = min(o[i], c[i]) - l[i], h[i] - max(o[i], c[i])
        if rng[i] >= a and body[i] <= rng[i] / 3:
            if low_w >= 2 * rng[i] / 3 and at_support(i):
                pin[i], lv_pin[i] = 1.0, 0.5 * (h[i] + l[i])
            elif up_w >= 2 * rng[i] / 3 and at_resist(i):
                pin[i], lv_pin[i] = -1.0, 0.5 * (h[i] + l[i])
    out["ev_ENGULF_LEVEL"], out["lv_ENGULF_LEVEL"] = eng, lv_eng
    out["ev_PINBAR_LEVEL"], out["lv_PINBAR_LEVEL"] = pin, lv_pin

    flip = F["sg_flip"].to_numpy(float)
    first = (flip != 0) & (np.r_[0.0, flip[:-1]] != flip)
    out["ev_CHOCH_RETEST"] = np.where(first, flip, 0.0)
    out["lv_CHOCH_RETEST"] = np.where(first, 0.5 * (h + l), np.nan)

    disp = F["ev_disp"].to_numpy(float)
    ob, lv_ob = np.zeros(n), np.full(n, np.nan)
    for i in np.flatnonzero(disp != 0):
        for k in range(i - 1, max(i - 6, -1), -1):
            if np.sign(c[k] - o[k]) == -disp[i]:
                ob[i], lv_ob[i] = disp[i], (h[k] if disp[i] > 0 else l[k])
                break
    out["ev_OB_RETEST"], out["lv_OB_RETEST"] = ob, lv_ob

    sweep = np.where(F["sg_sweep"].to_numpy(float) != 0, np.sign(F["sg_sweep"].to_numpy(float)),
                     np.where(F["ev_pdsweep"].to_numpy(float) != 0, F["ev_pdsweep"].to_numpy(float), F["ev_failbo"].to_numpy(float)))
    sd, lv_sd = np.zeros(n), np.full(n, np.nan)
    for i in np.flatnonzero(disp != 0):
        prior = sweep[max(i - 4, 0):i]
        if (prior == disp[i]).any():
            sd[i], lv_sd[i] = disp[i], o[i] + 0.5 * (c[i] - o[i])
    out["ev_SWEEP_DISPLACEMENT"], out["lv_SWEEP_DISPLACEMENT"] = sd, lv_sd

    tr, line = supertrend(h, l, c)
    flip_st = (tr != 0) & (np.r_[0.0, tr[:-1]] != 0) & (np.r_[0.0, tr[:-1]] != tr)
    out["ev_SUPERTREND"] = np.where(flip_st, tr, 0.0)
    out["lv_SUPERTREND"] = np.where(flip_st, line, np.nan)
    return pd.DataFrame(out, index=idx)


def triggers(F: pd.DataFrame, L: pd.DataFrame, fam: str, k_of: np.ndarray) -> list[tuple]:
    elig = np.unique(L["dec_i"].to_numpy())
    ev, lv = F[f"ev_{fam}"].to_numpy(float), F[f"lv_{fam}"].to_numpy(float)
    sel = elig[ev[elig] != 0]
    return [(int(i), int(np.sign(ev[i])), float(k_of[i]), float(lv[i])) for i in sel]


# ---------------- extra statistics ----------------
def neutral_rates(rates: dict) -> dict:
    """Direction-neutral random rate per (session, month): the mean of the BUY and SELL rates."""
    out = {}
    for (d, s, ym), v in rates.items():
        out.setdefault((s, ym), []).append(v)
    return {k: float(np.mean(v)) for k, v in out.items()}


def extra(seq: dict, nrates: dict, L: pd.DataFrame, P: b26.Path) -> dict:
    """Direction-neutral baseline, monthly results and results by volatility tercile / trend for a trade series."""
    if not seq or len(seq["fill_t"]) == 0:
        return {}
    ft = pd.to_datetime(np.asarray(seq["fill_t"]), unit="s", utc=True)
    ym = ft.strftime("%Y-%m").to_numpy()
    sess = np.asarray(seq["session"])
    neu = [nrates.get((s, m)) for s, m in zip(sess, ym, strict=True)]
    neu = float(np.mean([v for v in neu if v is not None])) if any(v is not None for v in neu) else math.nan
    out_, net = np.asarray(seq["outcome"]), np.asarray(seq["net"], float)
    k, n = b27.decided(out_)
    monthly = pd.Series(net * b26.LOT_OZ).groupby(ym).sum()
    t = np.asarray(P.t, dtype=np.int64)
    dec = np.searchsorted(t, np.asarray(seq["fill_t"], dtype=np.int64)) - 1
    ctx = L.drop_duplicates("dec_i").set_index("dec_i")
    by = {}
    for col in ("vol_tercile", "trend_state", "session"):
        lab = ctx[col].reindex(dec).to_numpy() if col != "session" else sess
        for g in pd.unique(lab):
            m = lab == g
            kk, nn = b27.decided(out_[m])
            by[f"{col}={g}"] = {"n": int(nn), "r": kk / nn if nn else None, "exp_oz": float(net[m].mean()) if m.any() else None}
    return {"direction_neutral_random": neu, "p_vs_neutral": b27.binom_p(k, n, neu) if n and not math.isnan(neu) else 1.0,
            "months": len(monthly), "share_months_positive": float((monthly > 0).mean()) if len(monthly) else None,
            "monthly_mean_050lot_ASSUMED": float(monthly.mean()) if len(monthly) else None,
            "monthly_worst_050lot_ASSUMED": float(monthly.min()) if len(monthly) else None, "by": by}


# ---------------- the run ----------------
def family_trades(P_: dict, fam: str, costs=None) -> tuple[list[tuple], dict]:
    trig = triggers(P_["F"], P_["Lp"], fam, P_["k"])
    return trig, b27.entry_trades(P_["path"], trig, costs if costs is not None else P_["costs"], xs=XS)


def stats(P_: dict, trig, trades, d: int, mode: str, mc: bool = False) -> dict:
    return b27.trade_stats([x for x in trades[mode] if x["d"] == d], sum(1 for x in trig if x[1] == d), P_["path"], P_["rates"],
                           P_["sess_of"], P_["weeks"], mc)


def frozen_set(cands: list[dict]) -> list[dict]:
    def lb(c_):
        return c_["stats"]["ci95"][0] if c_["stats"].get("n_decided") else -1.0

    groups = (("informative", sorted([c_ for c_ in cands if c_["informative"]], key=lb, reverse=True)[:MAX_INFORMATIVE]),
              ("top_n300", sorted([c_ for c_ in cands if c_["stats"].get("n_decided", 0) >= b27.MIN_N], key=lb, reverse=True)[:TOP_BIG]),
              ("low_frequency", sorted([c_ for c_ in cands if b27.LOW_N <= c_["stats"].get("n_decided", 0) < b27.MIN_N], key=lb,
                                       reverse=True)[:TOP_SMALL]))
    seen, out = set(), []
    for board, g in groups:
        for c_ in g:
            if c_["id"] not in seen:
                seen.add(c_["id"])
                c_["board"] = board
                out.append(c_)
    return out


def run(a, log=print) -> dict:
    pops = b27.load_pops(a.rd, a.store5, a.store60)
    D, Y = pops["DEV"], pops["Y2026"]
    for P_ in (D, Y):
        b27.prepare(P_, log)
        ev = new_events(P_["m15"], P_["F"])
        P_["F"] = pd.concat([P_["F"], ev], axis=1)
        P_["nrates"] = neutral_rates(P_["rates"])
    out = {"registration": REG, "utc": datetime.now(timezone.utc).isoformat(), "families": {}, "configs": []}
    cands, funnel = [], {}
    for fam in FAMILIES:
        trig, trades = family_trades(D, fam)
        out["families"][fam] = {"triggers": len(trig), "buy": sum(1 for x in trig if x[1] > 0), "sell": sum(1 for x in trig if x[1] < 0)}
        for d, dn in b27.DIRS.items():
            for mode in b27.entry_modes(XS):
                st = stats(D, trig, trades, d, mode)
                if st.get("n_filled"):
                    cands.append({"id": f"B28 {fam} {mode} {dn}", "family": fam, "mode": mode, "dir": dn, "stats": st})
            fl = [f_ for dd, f_ in trades["_funnel"] if dd == d and f_ is not None]
            for x in XS:
                funnel[f"{fam} {dn} X{x}"] = {s: sum(1 for f_ in fl if f_[x] == s) for s in ("CONFIRMED", "INVALIDATED", "EXPIRED")}
        log(f"[B28] {fam}: {len(trig)} triggers")
    b27.flag(cands)
    log(f"[B28] {len(cands)} configurations, {sum(c_['bh'] for c_ in cands)} BH, {sum(c_['informative'] for c_ in cands)} informative")
    frozen = frozen_set(cands)
    cache = {}
    for c_ in frozen:
        fam, d = c_["family"], 1 if c_["dir"] == "BUY" else -1
        if fam not in cache:
            cache[fam] = {"D": family_trades(D, fam), "Y": family_trades(Y, fam),
                          "D_OP": family_trades(D, fam, [(0.26, 0.0, 0.0, 0.0)] * len(D["costs"])),
                          "D_ADV": family_trades(D, fam, [(2 * s, 0.40, 0.40, 0.07) for s, *_ in D["costs"]])}
        tD, trD = cache[fam]["D"]
        tY, trY = cache[fam]["Y"]
        c_["stats"] = stats(D, tD, trD, d, c_["mode"], mc=True)
        c_["y2026"] = stats(Y, tY, trY, d, c_["mode"])
        c_["dev_extra"] = extra(c_["stats"].get("_seq"), D["nrates"], D["Lp"], D["path"])
        c_["y2026_extra"] = extra(c_["y2026"].get("_seq"), Y["nrates"], Y["Lp"], Y["path"])
        c_["cost_sensitivity"] = {sc: b27.summary_row(stats(D, *cache[fam][f"D_{sc}"], d, c_["mode"])) for sc in ("OP", "ADV")}
    for c_, ph in zip(frozen, b27.holm([c_["y2026"].get("p_vs_random", 1.0) for c_ in frozen]), strict=True):
        y_ = c_["y2026"]
        c_["y2026_holm_p"] = ph
        c_["holds_2026"] = bool(ph < 0.05 and y_.get("n_decided", 0) and y_["ci95"][0] > y_["matched_random"])
        c_["above_break_even_2026"] = bool(y_.get("n_decided", 0) and y_["ci95"][0] > y_["break_even"])
    out["counts"] = {"tested": len(cands), "bh": sum(c_["bh"] for c_ in cands), "informative": sum(c_["informative"] for c_ in cands),
                     "tradeable": sum(c_["tradeable"] for c_ in cands)}
    out["combinations"] = "none tested: no single hypothesis (B27 or B28) is INFORMATIVE" if not any(c_["informative"] for c_ in cands) else "see report"
    out["funnel"] = funnel
    out["configs"] = [{"id": c_["id"], "family": c_["family"], "mode": c_["mode"], "dir": c_["dir"], "bh": c_["bh"],
                       "informative": c_["informative"], "tradeable": c_["tradeable"], "dev": b27.summary_row(c_["stats"])} for c_ in cands]
    out["frozen"] = [{"id": c_["id"], "family": c_["family"], "mode": c_["mode"], "dir": c_["dir"], "board": c_["board"],
                      "informative": c_["informative"], "tradeable": c_["tradeable"], "dev": b27.summary_row(c_["stats"]),
                      "dev_extra": c_["dev_extra"], "y2026": b27.summary_row(c_["y2026"]), "y2026_extra": c_["y2026_extra"],
                      "cost_sensitivity": c_["cost_sensitivity"], "y2026_holm_p": c_["y2026_holm_p"], "holds_2026": c_["holds_2026"],
                      "above_break_even_2026": c_["above_break_even_2026"]} for c_ in frozen]
    out["_frozen"] = frozen
    return out


def write(out: dict, dir_: str, trials: str | None) -> None:
    os.makedirs(dir_, exist_ok=True)
    frozen = out.pop("_frozen")
    with open(os.path.join(dir_, "b28_summary.json"), "w") as fh:
        json.dump(b27._clean(out), fh, indent=1, allow_nan=False)
    rows = []
    for c_ in out["configs"]:
        dv = c_["dev"]
        rows.append({"id": c_["id"], "family": c_["family"], "mode": c_["mode"], "dir": c_["dir"],
                     **{k: dv.get(k) for k in b27.SUMMARY_KEYS if k != "ci95"}, "lo": dv["ci95"][0] if dv.get("ci95") else None,
                     "hi": dv["ci95"][1] if dv.get("ci95") else None, "bh": c_["bh"], "informative": c_["informative"], "tradeable": c_["tradeable"]})
    pd.DataFrame(rows).to_csv(os.path.join(dir_, "b28_configs.csv.gz"), index=False, float_format="%.4f", compression="gzip")
    frames = [f for c_ in frozen for f in (b27._seq_frame(c_["id"], "DEV", c_["stats"].get("_seq")),
                                            b27._seq_frame(c_["id"], "Y2026", c_["y2026"].get("_seq"))) if f is not None]
    if frames:
        pd.concat(frames).to_csv(os.path.join(dir_, "b28_frozen_trades.csv.gz"), index=False, float_format="%.4f", compression="gzip")
    if trials:
        log_trials(out, trials)


def log_trials(out: dict, trials: str) -> None:
    for c_ in out["configs"]:
        dv = c_["dev"]
        H.log_trial(trials, {"phase": REG, "partition": "development", "id": c_["id"], "n": dv["n_decided"], "success": dv["r"],
                             "ci95": dv["ci95"], "net_usd_per_oz": dv["exp_oz"],
                             "verdict": "TRADEABLE" if c_["tradeable"] else ("INFORMATIVE" if c_["informative"] else "NO")})
    for c_ in out["frozen"]:
        y_ = c_["y2026"]
        H.log_trial(trials, {"phase": REG, "partition": "unsealed 2026 (frozen check)", "id": c_["id"], "n": y_.get("n_decided"),
                             "success": y_.get("r"), "ci95": y_.get("ci95"), "net_usd_per_oz": y_.get("exp_oz"),
                             "holm_p": c_["y2026_holm_p"], "verdict": "HOLDS" if c_["holds_2026"] else "DOES NOT HOLD"})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True)
    ap.add_argument("--store5", required=True)
    ap.add_argument("--store60", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials")
    a = ap.parse_args(argv)
    out = run(a)
    write(out, a.out, a.trials)
    print(json.dumps(b27._clean({"counts": out["counts"], "families": out["families"]}), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
