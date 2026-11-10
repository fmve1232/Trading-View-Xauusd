"""Phase B25 (research/registrations/B25.json, approved 2026-11-07; written after the registration was committed).

Execution timing after a $15 confirmation. For every trigger of the B19 / B21 populations, entry models:
  A    the confirming 15m close (the reference)              B0   the next 15m bar's open
  B15 / B30 / B60   the 15m close 15 / 30 / 60 minutes later C    a limit back at the confirmation level, 8 bars
  E    a stop order at the trigger price + $15 placed at the trigger close (filled when traded, before invalidation)
and on the live store's 5m bars (P3): A5 (the 15m close, exits on 5m), B5 / B10 / B25 (the 5m close 5 / 10 / 25
minutes after the confirming close), D (the first 5m close $15 beyond) and E5 (the stop order on 5m bars).
Each model exits on its own entry: stop -$13, targets +$15 / +$20, a bar opening beyond a level fills at the open, a
bar touching both counts as the stop, in a fill bar of C / E only the stop can be hit, 48-hour time stop. Every rule
reads bars up to the decision only. Research code: never imported by production.
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

from .. import notify, ta
from ..data import sources
from . import b13, b19, b21
from . import harness as H

REG = "B25"
TYPES = ("GRAB", "BREAK", "SWEEP", "BREAKOUT")
FAMS = ("ENG", *TYPES, "N2")
WIN15, HOLD15, HOLD5 = 96, 192, 576
X, INV, SL = 15.0, 13.0, 13.0
TS = (15.0, 20.0)
M15 = ("A", "B0", "B15", "B30", "B60", "C", "E")
M5 = ("A5", "B5", "B10", "B25", "D", "E5")
PRIMARY = ("B0", "B15", "C", "E")
LIMIT_BARS = 8
EPS = 1e-9


@dataclass
class Bars:
    t: np.ndarray       # bar open, epoch s
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    up: np.ndarray      # an up structure event is published at this bar's close (15m events, mapped)
    dn: np.ndarray
    cost: np.ndarray    # model cost $ / oz at the bar
    sec: int


def from_path(P: b19.Path15) -> Bars:
    return Bars(P.t, P.o, P.h, P.l, P.c, P.up_evt, P.dn_evt, P.cost, 900)


def bars5(df5: pd.DataFrame, P: b19.Path15) -> Bars:
    """5m bars with the 15m structure events placed on the 5m bar that closes when the 15m event is published, and the
    15m model cost at the time."""
    t = np.asarray(ta.epoch_s(df5.index), np.int64)                # robust to the index's time unit
    n = len(t)
    up, dn = np.zeros(n, bool), np.zeros(n, bool)
    close5 = t + 300
    for arr, ev in ((up, P.up_evt), (dn, P.dn_evt)):
        k = np.searchsorted(close5, P.t[ev] + 900)
        ok = (k < n) & (close5[np.minimum(k, n - 1)] == P.t[ev] + 900)
        arr[k[ok]] = True
    j = np.clip(np.searchsorted(P.t, t, side="right") - 1, 0, len(P.t) - 1)
    return Bars(t, *(np.array(df5[x].to_numpy(float)) for x in ("open", "high", "low", "close")), up, dn, P.cost[j], 300)


# ---------------- the rules ----------------
def confirm(B: Bars, j0: int, p0: float, d: int, s: float, win: int) -> tuple[str, int]:
    """The first close X beyond p0 before INV against (high / low) or an opposite structure event; (status, bar)."""
    for b in range(j0, min(j0 + win, len(B.t))):
        if ((p0 - B.l[b]) if d > 0 else (B.h[b] - p0)) >= INV * s - EPS or (B.dn[b] if d > 0 else B.up[b]):
            return "INVALIDATED", b
        if (B.c[b] - p0) * d >= X * s - EPS:
            return "CONFIRMED", b
    return ("EXPIRED", -1) if j0 + win <= len(B.t) else ("OPEN", -1)


def exit_from(B: Bars, b0: int, entry: float, d: int, T: float, s: float, hold: int, mode: str) -> tuple[str, float, float, float]:
    """mode 'close': entered at the close of bar b0 - 1, scan from b0 with every rule. 'open': entered at bar b0's open
    (its open is the entry: only its range counts). 'fill': entered inside bar b0 (only the stop can be hit in it).
    Returns (outcome, exit price, MFE, MAE)."""
    tp, sl = entry + d * T * s, entry - d * SL * s
    mfe = mae = 0.0
    for b in range(b0, min(b0 + hold, len(B.t))):
        o, h, lo_ = B.o[b], B.h[b], B.l[b]
        fav, adv = ((h - entry) if d > 0 else (entry - lo_)), ((entry - lo_) if d > 0 else (h - entry))
        hit_sl = (lo_ <= sl) if d > 0 else (h >= sl)
        hit_tp = (h >= tp) if d > 0 else (lo_ <= tp)
        first = b == b0
        if not (first and mode in ("open", "fill")):
            if (o - sl) * d <= 0:
                return "SL", o, max(mfe, fav), max(mae, abs(o - entry))
            if (o - tp) * d >= 0:
                return "TP", o, max(mfe, abs(o - entry)), mae
        if first and mode == "fill":
            if hit_sl:
                return "SL", sl, mfe, SL * s
            mae = max(mae, adv)
            continue
        if hit_sl and hit_tp:
            return "AMBIGUOUS", sl, max(mfe, T * s), SL * s
        if hit_tp:
            return "TP", tp, max(mfe, T * s), max(mae, min(adv, SL * s))
        if hit_sl:
            return "SL", sl, max(mfe, min(fav, T * s)), SL * s
        mfe, mae = max(mfe, fav), max(mae, adv)
    b = b0 + hold - 1
    if b < len(B.t):
        return "TIMEOUT", B.c[b], mfe, mae
    return "OPEN", math.nan, mfe, mae


def stop_order(B: Bars, j0: int, p0: float, d: int, s: float, win: int) -> tuple[str, int, float, str]:
    """E: a stop at p0 + X in the direction, live from the trigger close. Returns (status, fill bar, fill price, how)."""
    L = p0 + d * X * s
    for b in range(j0, min(j0 + win, len(B.t))):
        inv_px = p0 - d * INV * s
        if (B.o[b] - inv_px) * d <= 0:                                # opens beyond the invalidation: never filled
            return "INVALIDATED", b, math.nan, ""
        if (B.o[b] - L) * d >= 0:                                     # opens beyond the level: filled at the open
            return "FILLED", b, float(B.o[b]), "gap"
        touched = (B.h[b] >= L) if d > 0 else (B.l[b] <= L)
        inv = (B.l[b] <= inv_px) if d > 0 else (B.h[b] >= inv_px)
        if touched:                                                   # a bar that also touches the invalidation: filled
            return "FILLED", b, float(L), "touch+invalid" if inv else "touch"          # (and stopped: see exit_from 'fill')
        if inv or (B.dn[b] if d > 0 else B.up[b]):
            return "INVALIDATED", b, math.nan, ""
    return ("EXPIRED", -1, math.nan, "") if j0 + win <= len(B.t) else ("OPEN", -1, math.nan, "")


def first_at(t: np.ndarray, ts: int) -> int:
    return int(np.searchsorted(t, ts))


# ---------------- one population ----------------
def run_models(B15: Bars, A: dict, s_scale: bool, B5: Bars | None = None, t_from5: int | None = None) -> list[dict]:
    """Every trigger through every model; one row per trigger."""
    rows = []
    for x in range(len(A["d"])):
        d, p0, j0 = int(A["d"][x]), float(A["p0"][x]), int(A["j0"][x])
        s = p0 / 4000.0 if s_scale else 1.0
        tr = A["trig"][x]
        row = {"t_trigger": int(tr["t_close"]), "dir": d, "p0": p0, "tf": tr["tf"], "regime": str(tr.get("regime") or ""),
               "session": notify.session_of(int(tr["t_close"])), "day": notify.trading_day(int(tr["t_close"])), "m": {}}
        st, k = confirm(B15, j0, p0, d, s, WIN15)
        row["A_status"] = st

        def add(name, entry, b0, mode, t_entry, bars=B15, hold=HOLD15, extra=None, d=d, s=s, row=row):
            m = {"entry": float(entry), "t_entry": int(t_entry), **(extra or {})}
            cost = float(bars.cost[min(b0, len(bars.t) - 1)])
            for T in TS:
                out, px, mfe, mae = exit_from(bars, b0, entry, d, T, s, hold, mode)
                m[f"T{T:g}"] = {"out": out, "net": (px - entry) * d / s - cost if np.isfinite(px) else math.nan,
                                "mfe": mfe / s, "mae": mae / s}
            m["cost"] = cost
            row["m"][name] = m

        if st == "CONFIRMED" and k + 5 + HOLD15 < len(B15.t):
            tA = int(B15.t[k]) + 900
            add("A", B15.c[k], k + 1, "close", tA)
            add("B0", B15.o[k + 1], k + 1, "open", int(B15.t[k + 1]))
            for name, mbar in (("B15", 1), ("B30", 2), ("B60", 4)):
                add(name, B15.c[k + mbar], k + mbar + 1, "close", int(B15.t[k + mbar]) + 900)
            L = p0 + d * X * s
            filled = False
            for b in range(k + 1, k + 1 + LIMIT_BARS):
                if (B15.l[b] <= L) if d > 0 else (B15.h[b] >= L):
                    fill = min(B15.o[b], L) if d > 0 else max(B15.o[b], L)
                    gap = (B15.o[b] - L) * d <= 0                     # opened through the level: filled at the open
                    add("C", fill, b, "fill", int(B15.t[b]) + (0 if gap else 450))   # inside a bar: its middle
                    filled = True
                    break
            if not filled:
                row["C_missed"] = True
        est, eb, epx, how = stop_order(B15, j0, p0, d, s, WIN15)
        if est == "FILLED" and eb + HOLD15 < len(B15.t):
            add("E", epx, eb, "fill", int(B15.t[eb]) + (0 if how == "gap" else 450), extra={"how": how})
        if B5 is not None and t_from5 is not None and int(tr["t_close"]) >= t_from5:
            j5 = first_at(B5.t, int(tr["t_close"]))
            if j5 < len(B5.t) and B5.t[j5] == int(tr["t_close"]) and j5 + 3 * WIN15 + HOLD5 < len(B5.t):
                row["in_p3"] = True
                if st == "CONFIRMED":
                    tA = int(B15.t[k]) + 900
                    a5 = first_at(B5.t, tA)
                    if a5 + 6 + HOLD5 < len(B5.t) and B5.t[a5] == tA:
                        add("A5", B15.c[k], a5, "close", tA, B5, HOLD5)
                        for name, m in (("B5", 0), ("B10", 1), ("B25", 4)):
                            add(name, B5.c[a5 + m], a5 + m + 1, "close", int(B5.t[a5 + m]) + 300, B5, HOLD5)
                dst, db = confirm(B5, j5, p0, d, s, 3 * WIN15)
                row["D_status"] = dst
                if dst == "CONFIRMED":
                    add("D", B5.c[db], db + 1, "close", int(B5.t[db]) + 300, B5, HOLD5)
                est5, eb5, epx5, how5 = stop_order(B5, j5, p0, d, s, 3 * WIN15)
                if est5 == "FILLED":
                    add("E5", epx5, eb5, "fill", int(B5.t[eb5]) + (0 if how5 == "gap" else 150), B5, HOLD5, {"how": how5})
        rows.append(row)
    return rows


# ---------------- statistics ----------------
def wilson(k: int, n: int) -> list:
    if not n:
        return [None, None]
    z, p = 1.959964, k / n
    den = 1 + z * z / n
    mid, half = (p + z * z / (2 * n)) / den, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [mid - half, mid + half]


def summarize(rows: list[dict], name: str, op_cost: float = b13.OP_COST) -> dict:
    ent = [r for r in rows if name in r["m"]]
    n = len(ent)
    out: dict = {"entered": n}
    if name == "C":
        conf = sum(1 for r in rows if "A" in r["m"])
        out.update(fill_rate=n / conf if conf else None, missed=sum(1 for r in rows if r.get("C_missed")),
                   missed_opportunities=sum(1 for r in rows if r.get("C_missed") and r["m"]["A"]["T15"]["out"] == "TP"))
    if name in ("D", "E", "E5"):
        out["false_confirmations"] = sum(1 for r in ent if r["A_status"] != "CONFIRMED")
    ref = "A5" if name in ("B5", "B10", "B25", "D", "E5") else "A"
    pairs = [r for r in ent if ref in r["m"] and name != ref]
    if pairs:
        out["vs_" + ref] = {"pairs": len(pairs),
                            "latency_min_mean": float(np.mean([(r["m"][name]["t_entry"] - r["m"][ref]["t_entry"]) / 60 for r in pairs])),
                            "latency_min_median": float(np.median([(r["m"][name]["t_entry"] - r["m"][ref]["t_entry"]) / 60 for r in pairs])),
                            "deterioration_usd_mean": float(np.mean([(r["m"][name]["entry"] - r["m"][ref]["entry"]) * r["dir"]
                                                                       / (r["p0"] / 4000.0 if r.get("_scaled") else 1.0) for r in pairs]))}
    for T in TS:
        key = f"T{T:g}"
        outs = [r["m"][name][key]["out"] for r in ent]
        dec = [o for o in outs if o != "OPEN"]
        k = sum(o == "TP" for o in dec)
        nets = np.array([r["m"][name][key]["net"] for r in ent if r["m"][name][key]["out"] != "OPEN"], float)
        costs = np.array([r["m"][name]["cost"] for r in ent if r["m"][name][key]["out"] != "OPEN"], float)
        wins, losses = nets[nets > 0], nets[nets < 0]
        out[key] = {"n": len(dec), "tp_first": k / len(dec) if dec else None, "ci95": wilson(k, len(dec)),
                    "stop_first": sum(o in ("SL", "AMBIGUOUS") for o in dec) / len(dec) if dec else None,
                    "timeout": sum(o == "TIMEOUT" for o in dec) / len(dec) if dec else None,
                    "expectancy_model_cost": float(nets.mean()) if len(nets) else None,
                    "expectancy_operator_cost": float((nets + costs - op_cost).mean()) if len(nets) else None,
                    "profit_factor": float(wins.sum() / -losses.sum()) if len(losses) else None,
                    "mfe_mean": float(np.mean([r["m"][name][key]["mfe"] for r in ent])) if ent else None,
                    "mae_mean": float(np.mean([r["m"][name][key]["mae"] for r in ent])) if ent else None,
                    "buy": _rate([r for r in ent if r["dir"] > 0], name, key), "sell": _rate([r for r in ent if r["dir"] < 0], name, key)}
    out["by_session"] = {g: _rate([r for r in ent if r["session"] == g], name, "T15") for g in sorted({r["session"] for r in ent})}
    return out


def _rate(rs: list[dict], name: str, key: str) -> dict | None:
    dec = [r for r in rs if r["m"][name][key]["out"] != "OPEN"]
    if not dec:
        return None
    k = sum(r["m"][name][key]["out"] == "TP" for r in dec)
    return {"n": len(dec), "tp_first": k / len(dec), "ci95": wilson(k, len(dec))}


def paired(rows: list[dict], name: str, ref: str = "A", key: str = "T15", n_boot: int = 2000, seed: int = 25) -> dict:
    """Mean net difference (model - ref) on the triggers both entered, day-clustered bootstrap, one-sided p in the
    direction of the observed difference."""
    pr = [r for r in rows if name in r["m"] and ref in r["m"] and np.isfinite(r["m"][name][key]["net"]) and np.isfinite(r["m"][ref][key]["net"])]
    if len(pr) < 2:
        return {"pairs": len(pr), "diff": None, "p": None}
    days = sorted({r["day"] for r in pr})
    by = {dd: [] for dd in days}
    for r in pr:
        by[r["day"]].append(r["m"][name][key]["net"] - r["m"][ref][key]["net"])
    sums = np.array([sum(by[dd]) for dd in days])
    cnts = np.array([len(by[dd]) for dd in days])
    diff = float(sums.sum() / cnts.sum())
    rng = H.seeded_rng(seed)
    idx = rng.integers(0, len(days), size=(n_boot, len(days)))
    boot = sums[idx].sum(1) / cnts[idx].sum(1)
    p = float(np.mean(boot <= 0)) if diff > 0 else float(np.mean(boot >= 0))
    win_m = np.mean([r["m"][name][key]["out"] == "TP" for r in pr])
    win_r = np.mean([r["m"][ref][key]["out"] == "TP" for r in pr])
    return {"pairs": len(pr), "days": len(days), "diff": diff, "p": p, "tp_first_model": float(win_m), "tp_first_ref": float(win_r)}


def holm(ps: dict) -> dict:
    items = sorted((p, k) for k, p in ps.items() if p is not None)
    m, out, run = len(items), {}, 0.0
    for i, (p, k) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        out[k] = run
    return out


# ---------------- data ----------------
def build(rd: str, part: str, log=print) -> dict:
    m15, h1, score_from = b19.load_part(rd, part)
    runs = b19.engine_runs(m15, h1, log)
    res15 = runs["15m"][0]
    up, dn = b19.struct_arrays(res15, len(m15))
    P = b19.make_path(m15, up, dn)
    t_from = int(score_from.timestamp())
    eng = b19.dedupe([x for tf, (res, F) in runs.items() for x in b19.triggers_from_run(res, F, tf, "ENG") if x["t_close"] >= t_from])
    trig, _ = b21.alerts(m15, h1, score_from, log)
    rows = np.flatnonzero(P.t >= t_from)[::8]
    rows = rows[(rows >= b19.SSTR_LOOKBACK) & (rows + 1 + b19.WIN + b19.HOLD + b19.LIMIT_BARS < len(P.t))]
    n2 = [{"tf": "15m", "kind": "N2", "i": int(i), "t_close": int(P.t[i]) + 900, "dir": sg, "p0": float(P.c[i]), "regime": ""}
          for i in rows for sg in (1, -1)]
    fams = {"ENG": b19.attach(eng, P), "N2": b19.attach(n2, P), **{k: b19.attach(v, P) for k, v in trig.items()}}
    return {"m15": m15, "P": P, "fams": fams, "score_from": str(score_from)}


def load_store5(d: str) -> pd.DataFrame:
    """The live store's XAU/USD 5m CSVs, cleaned as the site does (closed-market quotes dropped, reopen bars repaired)."""
    parts = [pd.read_csv(f, index_col=0, parse_dates=True) for f in sorted(glob.glob(os.path.join(d, "*.csv")))]
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df.index = pd.DatetimeIndex(df.index).tz_convert("UTC") if df.index.tz is not None else pd.DatetimeIndex(df.index).tz_localize("UTC")
    df = sources.trading_week_only(df)
    return sources.repair_reopen(df, 300)


def check_5m_vs_15m(df5: pd.DataFrame, m15: pd.DataFrame) -> dict:
    r = sources.resample_ohlc(df5, "15min")
    j = r.index.intersection(m15.index)
    diff = (r.loc[j, "close"] - m15.loc[j, "close"]).abs()
    return {"overlap_15m_bars": len(j), "close_diff_median": float(diff.median()) if len(j) else None,
            "share_above_0.10": float((diff > 0.10).mean()) if len(j) else None, "max": float(diff.max()) if len(j) else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True)
    ap.add_argument("--store5", required=True, help="a folder with the live store's XAU_USD_5m/*.csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials")
    a = ap.parse_args(argv)
    out = {"registration": REG, "parts": {}}
    for part, scale in (("development", True), ("recent", False)):
        D = build(a.rd, part)
        B15 = from_path(D["P"])
        B5 = t5 = None
        res = {"window": [str(D["m15"].index[0]), str(D["m15"].index[-1])], "scored_from": D["score_from"], "populations": {}}
        if part == "recent":
            df5 = load_store5(a.store5)
            df5 = df5[df5.index <= D["m15"].index[-1] + pd.Timedelta(minutes=10)]
            res["p3_5m"] = {"window": [str(df5.index[0]), str(df5.index[-1])], "bars": len(df5), "check_vs_15m": check_5m_vs_15m(df5, D["m15"])}
            B5, t5 = bars5(df5, D["P"]), int(df5.index[0].timestamp()) + 86400
        all_rows = []
        for fam in FAMS:
            rows = run_models(B15, D["fams"][fam], scale, B5, t5)
            for r in rows:
                r["_scaled"] = scale
            if fam in TYPES:
                all_rows += rows
            res["populations"][fam] = _pop(rows, part)
            print(part, fam, {m: res["populations"][fam]["models"].get(m, {}).get("T15", {}).get("tp_first") for m in M15}, flush=True)
        res["populations"]["ALL"] = _pop(all_rows, part)
        tests = {m: paired(all_rows, m) for m in PRIMARY}
        res["primary"] = {"tests": tests, "holm": holm({m: v["p"] for m, v in tests.items()})}
        out["parts"][part] = res
    dev, rec = out["parts"]["development"]["primary"], out["parts"]["recent"]["primary"]
    out["verdicts"] = {m: ("DIFFERS" if (dev["holm"].get(m, 1) < 0.05 and dev["tests"][m]["diff"] is not None and rec["tests"][m]["diff"] is not None
                                         and np.sign(dev["tests"][m]["diff"]) == np.sign(rec["tests"][m]["diff"])) else "NO DIFFERENCE SHOWN")
                       for m in PRIMARY}
    out["utc"] = datetime.now(timezone.utc).isoformat()
    with open(a.out, "w") as fh:
        json.dump(b13._clean(out), fh, indent=1, allow_nan=False)
    if a.trials:
        for part, res in out["parts"].items():
            for fam, pop in res["populations"].items():
                for m, v in pop["models"].items():
                    t = v.get("T15") or {}
                    H.log_trial(a.trials, {"phase": REG, "partition": part, "id": f"B25 {fam} {m} T15", "n": t.get("n"),
                                           "success": t.get("tp_first"), "ci95": t.get("ci95"),
                                           "net_usd_per_oz": t.get("expectancy_model_cost"),
                                           **({"primary": "B25", "verdict": out["verdicts"][m]} if (fam == "ALL" and part == "development" and m in PRIMARY) else {})})
    print(json.dumps({"verdicts": out["verdicts"], "dev": dev, "recent": rec}, indent=1, default=str))
    return 0


def _pop(rows: list[dict], part: str) -> dict:
    models = {m: summarize(rows, m) for m in (*M15, *M5) if any(m in r["m"] for r in rows)}
    return {"triggers": len(rows), "A_status": {s: sum(r["A_status"] == s for r in rows) for s in ("CONFIRMED", "INVALIDATED", "EXPIRED", "OPEN")},
            "in_p3": sum(1 for r in rows if r.get("in_p3")), "models": models,
            "paired_vs_A": {m: paired(rows, m) for m in M15 if m != "A"},
            "paired_vs_A5": {m: paired(rows, m, "A5") for m in ("B5", "B10", "B25", "D", "E5")}}


if __name__ == "__main__":
    raise SystemExit(main())
