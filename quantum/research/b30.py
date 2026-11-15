"""Phase B30 (research/registrations/B30.json, approved 2026-11-15; written after the registration was committed).

Does a favourable move of $10 / $15 / $20 beyond the trigger price, confirmed at a 15m close, improve the odds that the
operator's plan reaches its target before its stop, after costs, compared with entering at the trigger?

  Baseline  entry at P0 (the trigger close)          A / B / C  entry at the first 15m close $10 / $15 / $20 beyond P0
  G1 (primary)  stop 13, TP1 13 for half, TP2 20 for the other half, stop to entry after TP1, all from the ACTUAL entry
  G2 (ENG only) the engine's own stop / TP1 fixed at the trigger; executed only if the remaining net R:R >= 1 etc.

Triggers, the REPEAT rule, the path, the invalidation (-13 or an opposite structure break) and the 96-bar window are
B19's (imported, unchanged). Every condition is read at a bar's close from data up to that close. A bar touching the
stop and a target is AMBIGUOUS (scored as the stop, reported apart). Distances are $ at $4,000 scaled by P0 / 4000;
costs are $ per oz. Research code: never imported by production.
"""
from __future__ import annotations

import argparse
import json
import math

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from . import b13, b19, history
from . import harness as H

REG = "B30"
WIN, HOLD = b19.WIN, b19.HOLD                       # 96 bars to confirm, 192 bars to hold (15m)
INV = b19.INV                                       # $13 against P0 invalidates before confirmation
MODELS = {"Baseline": 0.0, "A": 10.0, "B": 15.0, "C": 20.0}
SL, TP1, TP2 = 13.0, 13.0, 20.0                     # the operator's plan (N1 sizes it to $650 incl. cost)
REV_MFE = 6.5                                       # reversal: stopped first after an MFE of half TP1
RISK_USD = 650.0
OP_COST = b13.OP_COST
BOOT, SEED = 2000, 30
EPS = 1e-9
SEALED = ("validation", "holdout")


# ---------------- confirmation (B19's rule with X as a parameter) ----------------
def _win(a: np.ndarray, j: np.ndarray, w: int) -> np.ndarray:
    return sliding_window_view(a, w)[j]


def confirm(P: b19.Path15, A: dict, X: float) -> dict:
    """Per trigger: status (TRIGGER for the Baseline; else CONFIRMED / INVALIDATED / EXPIRED), k = the confirming 15m bar
    (absolute), the invalidation kind, and the first TOUCH of +10 / +15 / +20 (a milestone, never an entry)."""
    j0, p0, d = A["j0"], A["p0"], A["d"]
    n = len(j0)
    s = p0 / 4000.0
    dd, pp, ss = d[:, None], p0[:, None], s[:, None]
    hh, ll, cc = _win(P.h, j0, WIN), _win(P.l, j0, WIN), _win(P.c, j0, WIN)
    fav = np.where(dd > 0, hh - pp, pp - ll)
    adv = np.where(dd > 0, pp - ll, hh - pp)
    out = {}
    for lv in (10, 15, 20):
        hit = fav >= lv * ss - EPS
        out[f"touch{lv}"] = np.where(hit.any(1), hit.argmax(1), -1)
    if X <= 0:
        out.update(status=np.array(["TRIGGER"] * n, object), k=j0 - 1, inv_kind=np.array([""] * n, object))
        return out
    inv_p = adv >= INV * ss - EPS
    inv_s = np.where(dd > 0, _win(P.dn_evt, j0, WIN), _win(P.up_evt, j0, WIN))
    inv = inv_p | inv_s
    first_inv = np.where(inv.any(1), inv.argmax(1), WIN)
    cand = (cc - pp) * dd >= X * ss - EPS
    first_conf = np.where(cand.any(1), cand.argmax(1), WIN)
    confirmed = (first_conf < first_inv) & (first_conf < WIN)
    invalid = ~confirmed & (first_inv < WIN)
    status = np.where(confirmed, "CONFIRMED", np.where(invalid, "INVALIDATED", "EXPIRED")).astype(object)
    row = np.arange(n)
    fi = np.minimum(first_inv, WIN - 1)
    kind = np.where(invalid, np.where(inv_p[row, fi], "price", "structure"), "").astype(object)
    out.update(status=status, k=np.where(confirmed, j0 + first_conf, -1), inv_kind=kind)
    return out


# ---------------- exits ----------------
def _first(mask: np.ndarray) -> np.ndarray:
    return np.where(mask.any(1), mask.argmax(1), mask.shape[1])


def two_target(P: b19.Path15, ent: np.ndarray, start: np.ndarray, d: np.ndarray, s: np.ndarray, cost: np.ndarray) -> dict:
    """G1 exit for trades entered at `ent` with the first bar `start`. Stage 1: stop (ent - 13) vs TP1 (ent + 13), a bar
    touching both = AMBIGUOUS (scored as the stop). Stage 2 after TP1 (half closed at TP1): TP2 (ent + 20) vs the moved
    stop (ent). On the TP1 bar itself the order inside the bar is unknown: if it also touches the moved stop the second
    half is scored at the moved stop (AMBIGUOUS-2); if it reaches TP2 without touching it, TP2 is filled on that bar.
    A bar opening beyond a level fills at the open. Time stop at HOLD bars: exit at that bar's close."""
    m = len(ent)
    res = {k: np.full(m, np.nan) for k in ("net", "r", "mfe", "mae", "mfe_pre", "exit_bar")}
    res["outcome"] = np.array([""] * m, object)
    if not m:
        return res
    oo, hh, ll, cc = (_win(a, start, HOLD) for a in (P.o, P.h, P.l, P.c))
    dd, e_, ss = d[:, None], ent[:, None], s[:, None]
    sl, t1, t2 = e_ - dd * SL * ss, e_ + dd * TP1 * ss, e_ + dd * TP2 * ss
    fav_b, adv_b = np.where(dd > 0, hh - e_, e_ - ll) / ss, np.where(dd > 0, e_ - ll, hh - e_) / ss
    o_sl, o_t1 = (oo - sl) * dd <= 0, (oo - t1) * dd >= 0
    h_sl, h_t1 = np.where(dd > 0, ll <= sl, hh >= sl), np.where(dd > 0, hh >= t1, ll <= t1)
    f1 = _first(o_sl | o_t1 | h_sl | h_t1)
    r = np.arange(m)
    f = np.minimum(f1, HOLD - 1)
    none1 = f1 >= HOLD
    first_out = np.where(none1, "TIMEOUT", np.where(o_sl[r, f], "SL", np.where(o_t1[r, f], "TP1",
                         np.where(h_sl[r, f] & h_t1[r, f], "AMBIGUOUS", np.where(h_t1[r, f], "TP1", "SL"))))).astype(object)
    px1 = np.where(none1, cc[:, HOLD - 1], np.where(o_sl[r, f] | o_t1[r, f], oo[r, f], np.where(first_out == "TP1", t1[:, 0], sl[:, 0])))
    leg1 = (px1 - ent) * d / s                                    # $ per oz at $4,000 for the whole position
    net = np.where(first_out == "TP1", np.nan, leg1)
    # SL / AMBIGUOUS: -13 (px1 = the stop), worse if the bar opened through it; TIMEOUT: the close; TP1: stage 2 below
    outcome = first_out.copy()
    exit_bar = np.where(none1, HOLD - 1, f).astype(float)
    tp = np.flatnonzero(first_out == "TP1")
    for x in tp:                                                  # stage 2 (TP1 trades only), from the TP1 bar
        b = int(f[x])
        half1 = (px1[x] - ent[x]) * d[x] / s[x]
        o2, h2, l2, c2 = oo[x, b:], hh[x, b:], ll[x, b:], cc[x, b:]
        be, tgt = ent[x], t2[x, 0]
        hit_be = (l2 <= be) if d[x] > 0 else (h2 >= be)
        hit_t2 = (h2 >= tgt) if d[x] > 0 else (l2 <= tgt)
        open_be = ((o2 - be) * d[x] <= 0)
        open_t2 = ((o2 - tgt) * d[x] >= 0)
        open_be[0] = open_t2[0] = False                           # the TP1 bar's open came before TP1
        ev = hit_be | hit_t2 | open_be | open_t2
        j = int(ev.argmax()) if ev.any() else len(ev)
        if j >= len(ev):
            px2, tag = c2[-1], "TP1+TIMEOUT"
            jj = len(ev) - 1
        elif open_be[j]:
            px2, tag, jj = o2[j], "TP1+BE", j
        elif open_t2[j]:
            px2, tag, jj = o2[j], "TP1+TP2", j
        elif hit_be[j] and hit_t2[j]:
            px2, tag, jj = be, "TP1+AMBIGUOUS-2", j
        elif hit_t2[j]:
            px2, tag, jj = tgt, "TP1+TP2", j
        else:
            px2, tag, jj = be, "TP1+BE", j
        half2 = (px2 - ent[x]) * d[x] / s[x]
        net[x] = 0.5 * half1 + 0.5 * half2
        outcome[x] = tag
        exit_bar[x] = b + jj
    net = net - cost
    eb = exit_bar.astype(int)
    upto = np.arange(HOLD)[None, :] <= eb[:, None]
    res["mfe"] = np.where(upto, fav_b, -np.inf).max(1)
    res["mae"] = np.where(upto, adv_b, -np.inf).max(1)
    pre = np.arange(HOLD)[None, :] < f[:, None]                   # bars before the stage-1 event
    res["mfe_pre"] = np.where(pre, fav_b, 0.0).max(1)
    res.update(net=net, r=net / (SL + cost), outcome=outcome, exit_bar=exit_bar)
    return res


def one_target(P: b19.Path15, ent, start, d, s, cost, D, T) -> dict:
    """G2 exit: stop D and target T (price units, from the entry); a bar touching both = AMBIGUOUS (the stop)."""
    m = len(ent)
    res = {"net": np.full(m, np.nan), "r": np.full(m, np.nan), "outcome": np.array([""] * m, object)}
    if not m:
        return res
    oo, hh, ll, cc = (_win(a, start, HOLD) for a in (P.o, P.h, P.l, P.c))
    dd, e_ = d[:, None], ent[:, None]
    sl, tp = e_ - dd * D[:, None], e_ + dd * T[:, None]
    o_sl, o_tp = (oo - sl) * dd <= 0, (oo - tp) * dd >= 0
    h_sl, h_tp = np.where(dd > 0, ll <= sl, hh >= sl), np.where(dd > 0, hh >= tp, ll <= tp)
    f1 = _first(o_sl | o_tp | h_sl | h_tp)
    r = np.arange(m)
    f = np.minimum(f1, HOLD - 1)
    none = f1 >= HOLD
    out = np.where(none, "TIMEOUT", np.where(o_sl[r, f], "SL", np.where(o_tp[r, f], "TP1", np.where(h_sl[r, f] & h_tp[r, f], "AMBIGUOUS",
                   np.where(h_tp[r, f], "TP1", "SL"))))).astype(object)
    px = np.where(none, cc[:, HOLD - 1], np.where(o_sl[r, f] | o_tp[r, f], oo[r, f], np.where(out == "TP1", tp[:, 0], sl[:, 0])))
    net = (px - ent) * d / s - cost
    res.update(net=net, r=net / (D / s + cost), outcome=out)
    return res


# ---------------- one model ----------------
def run_model(P: b19.Path15, A: dict, X: float, plan: str = "G1", cost_kind: str = "model") -> dict:
    C = confirm(P, A, X)
    d, p0, j0 = A["d"], A["p0"], A["j0"]
    s = p0 / 4000.0
    n = len(d)
    act = np.ones(n, bool) if X <= 0 else (C["status"] == "CONFIRMED")
    k = C["k"]
    ent = np.where(X <= 0, p0, np.where(act, P.c[np.maximum(k, 0)], np.nan))
    start = np.where(X <= 0, j0, k + 1)
    kk = np.where(X <= 0, j0 - 1, np.maximum(k, 0))
    cost_all = P.cost[kk] if cost_kind == "model" else np.full(n, OP_COST)
    rejected = np.zeros(n, bool)
    if plan == "G1":
        ex = act.copy()
    else:
        sl_e = np.array([np.nan if t.get("sl_eng") is None else float(t["sl_eng"]) for t in A["trig"]])
        tp_e = np.array([np.nan if t.get("tp1_eng") is None else float(t["tp1_eng"]) for t in A["trig"]])
        D, T = (ent - sl_e) * d, (tp_e - ent) * d
        ok = act & np.isfinite(D) & np.isfinite(T) & (D > 0)
        with np.errstate(invalid="ignore", divide="ignore"):
            rr_net = (T / s - cost_all) / (D / s + cost_all)
            ex = ok & (rr_net >= b19.RR_MIN - EPS) & (D / s >= b19.D_MIN - EPS) & (D / s <= b19.D_MAX + EPS) & (cost_all <= b19.COST_FRAC * D / s + EPS)
        rejected = act & ~ex
    ii = np.flatnonzero(ex)
    if plan == "G1":
        T_ = two_target(P, ent[ii], start[ii].astype(int), d[ii], s[ii], cost_all[ii])
    else:
        T_ = one_target(P, ent[ii], start[ii].astype(int), d[ii], s[ii], cost_all[ii], D[ii], T[ii])
    delay = np.where(X <= 0, 0.0, (P.t[np.maximum(k, 0)] + 900 - A["t_close"]) / 60.0)
    t_entry = np.where(X <= 0, A["t_close"], P.t[np.maximum(k, 0)] + 900)
    return {"C": C, "execute": ex, "rejected": rejected, "idx": ii, "T": T_, "delay": delay[ii], "t_entry": t_entry[ii],
            "cost": cost_all[ii], "n": n}


# ---------------- statistics ----------------
def _boot_ci(r: np.ndarray, day: np.ndarray, seed: int = SEED) -> tuple[float, float]:
    if len(r) < 3:
        return (math.nan, math.nan)
    days = np.unique(day)
    g = {dd: r[day == dd] for dd in days}
    rng = H.seeded_rng(seed)
    means = []
    for _ in range(BOOT):
        pick = rng.choice(days, size=len(days), replace=True)
        x = np.concatenate([g[p] for p in pick])
        means.append(x.mean())
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def stats(res: dict, base: dict | None = None) -> dict:
    T_ = res["T"]
    out = T_["outcome"]
    n = len(out)
    st = res["C"]["status"]
    trig = res["n"]
    o = {"triggers": int(trig), "confirmed": int((st == "CONFIRMED").sum()) if st[0:1].size and st[0] != "TRIGGER" else int(trig),
         "invalidated_price": int(((st == "INVALIDATED") & (res["C"]["inv_kind"] == "price")).sum()),
         "invalidated_structure": int(((st == "INVALIDATED") & (res["C"]["inv_kind"] == "structure")).sum()),
         "expired": int((st == "EXPIRED").sum()), "rejected": int(res["rejected"].sum()), "executed": n,
         "touched10": int((res["C"]["touch10"] >= 0).sum()), "touched15": int((res["C"]["touch15"] >= 0).sum()),
         "touched20": int((res["C"]["touch20"] >= 0).sum())}
    if not n:
        return o
    tp1 = np.isin(out, ["TP1", "TP1+TP2", "TP1+BE", "TP1+TIMEOUT", "TP1+AMBIGUOUS-2"])
    tp2 = out == "TP1+TP2"
    slf = out == "SL"
    amb = out == "AMBIGUOUS"
    tmo = out == "TIMEOUT"
    for name, msk in (("tp1_first", tp1), ("tp2_first", tp2), ("sl_first", slf), ("ambiguous", amb), ("timeout", tmo)):
        k = int(msk.sum())
        lo, hi = H.wilson(k, n)
        o[name] = {"k": k, "rate": k / n, "wilson95": [lo, hi]}
    r, net = T_["r"], T_["net"]
    order = np.argsort(res["t_entry"], kind="stable")
    day = (res["t_entry"] // 86400).astype(np.int64)
    sd = float(np.std(r, ddof=1)) if n > 2 else math.nan
    o["mean_r"] = float(r.mean())
    o["mean_r_t95"] = [float(r.mean() - 1.96 * sd / math.sqrt(n)), float(r.mean() + 1.96 * sd / math.sqrt(n))] if n > 2 else [math.nan, math.nan]
    o["mean_r_boot95"] = list(_boot_ci(r, day))
    o["usd_per_trade"] = o["mean_r"] * RISK_USD
    o["mean_net_usd_per_oz"] = float(net.mean())
    o["r_ambiguous_excluded"] = float(r[~amb].mean()) if (~amb).any() else math.nan
    o["per_trigger_r"] = float(r.sum() / trig) if trig else math.nan
    o["delay_min_mean"], o["delay_min_median"] = float(np.mean(res["delay"])), float(np.median(res["delay"]))
    if "mfe" in T_:
        o["mfe_mean"], o["mfe_median"] = float(np.mean(T_["mfe"])), float(np.median(T_["mfe"]))
        o["mae_mean"], o["mae_median"] = float(np.mean(T_["mae"])), float(np.median(T_["mae"]))
        o["reversal_rate"] = float(np.mean((slf | amb) & (T_["mfe_pre"] >= REV_MFE)))
    wins, losses = net[net > 0], net[net < 0]
    o["realised_rr"] = float(wins.mean() / -losses.mean()) if len(wins) and len(losses) else math.nan
    usd = r[order] * RISK_USD
    o["max_drawdown_usd"] = b19.max_drawdown(usd)
    streak = best = 0
    for v in r[order]:
        streak = streak + 1 if v < 0 else 0
        best = max(best, streak)
    o["longest_losing_streak"] = int(best)
    o["mean_cost_usd_per_oz"] = float(np.mean(res["cost"]))
    o["sd_r"] = sd
    if base is not None:
        brs = base["T"]["r"]
        o["welch_p_vs_baseline"] = b19.welch_p(r, brs)
        miss = np.setdiff1d(np.arange(trig), res["idx"])
        bout = np.array([""] * trig, object)
        bout[base["idx"]] = base["T"]["outcome"]
        o["missed"] = int(len(miss))
        o["missed_winners"] = int(np.isin(bout[miss], ["TP1", "TP1+TP2", "TP1+BE", "TP1+TIMEOUT", "TP1+AMBIGUOUS-2"]).sum())
    return o


# ---------------- data and runs ----------------
def load_part(rd: str, part: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    if part == "recent":
        m15, h1 = history.load(rd, "XAU/USD", "15min"), history.load(rd, "XAU/USD", "1h")
        lo = H.HOLD[1]
        m15, h1 = m15[m15.index >= lo], h1[h1.index >= lo]
        return m15, h1, lo + pd.Timedelta(days=59)
    m15 = H.partition(history.load(rd, "XAU/USD", "15min"), part, REG if part in SEALED else None)
    h1 = H.partition(history.load(rd, "XAU/USD", "1h"), part, REG if part in SEALED else None)
    start = b13.SCORE_FROM if part == "development" else m15.index[0] + pd.Timedelta(days=67)
    return m15, h1, start


def populations(rd: str, part: str, log=print) -> tuple[b19.Path15, dict, dict]:
    m15, h1, score_from = load_part(rd, part)
    runs = b19.engine_runs(m15, h1, log)
    res15, _ = runs["15m"]
    up, dn = b19.struct_arrays(res15, len(m15))
    P = b19.make_path(m15, up, dn)
    t_from = int(score_from.timestamp())
    pops = {}
    for kind in ("ENG", "STR"):
        trig = [x for tf, (res, F) in runs.items() for x in b19.triggers_from_run(res, F, tf, kind)]
        pops[kind] = b19.attach(b19.dedupe([x for x in trig if x["t_close"] >= t_from]), P)
    rows = np.flatnonzero(P.t >= t_from)[::8]
    rnd = [{"tf": "15m", "kind": "RND", "i": int(i), "t_close": int(P.t[i]) + 900, "dir": dd, "p0": float(P.c[i])}
           for i in rows for dd in (1, -1)]
    pops["RND"] = b19.attach(rnd, P)
    meta = {"part": part, "bars_15m": len(m15), "first": str(m15.index[0]), "last": str(m15.index[-1]),
            "scored_from": str(score_from), "data_hash_15m": H.data_hash(m15), "data_hash_1h": H.data_hash(h1),
            "triggers": {k: len(v["d"]) for k, v in pops.items()}}
    return P, pops, meta


def run(rd: str, part: str, log=print, trials: str | None = None) -> dict:
    P, pops, meta = populations(rd, part, log)
    out = {"meta": meta, "results": {}, "keep": {}}
    for pop, A in pops.items():
        plans = ("G1", "G2") if pop == "ENG" else ("G1",)
        for plan in plans:
            for cost_kind in ("model", "operator"):
                base = run_model(P, A, 0.0, plan, cost_kind)
                for name, X in MODELS.items():
                    res = base if X <= 0 else run_model(P, A, X, plan, cost_kind)
                    st = stats(res, None if X <= 0 else base)
                    key = f"{pop}|{plan}|{cost_kind}|{name}"
                    out["results"][key] = st
                    if cost_kind == "model":
                        out["keep"][key] = {"r": res["T"]["r"].tolist(), "t_entry": res["t_entry"].tolist(),
                                            "outcome": res["T"]["outcome"].tolist()}
                    if trials:
                        H.log_trial(trials, {"reg": REG, "part": part, "key": key, "n": st.get("executed", 0),
                                             "mean_r": st.get("mean_r", math.nan)})
        log(f"[B30] {part} {pop}: {len(A['d'])} triggers")
    return out


def decide(parts: dict) -> dict:
    """The registered primary rule on ENG | G1 | model: out of sample = validation + holdout pooled."""
    def pooled(name):
        r, t = [], []
        for p in SEALED:
            k = parts[p]["keep"][f"ENG|G1|model|{name}"]
            r += k["r"]
            t += k["t_entry"]
        return np.asarray(r, float), np.asarray(t, np.int64)
    rb, _ = pooled("Baseline")
    ps, rows = {}, {}
    for name in ("A", "B", "C"):
        r, t = pooled(name)
        lo, hi = _boot_ci(r, t // 86400) if len(r) >= 3 else (math.nan, math.nan)
        ps[name] = b19.welch_p(r, rb)
        dev_m = parts["development"]["results"][f"ENG|G1|model|{name}"].get("mean_r", math.nan)
        dev_b = parts["development"]["results"]["ENG|G1|model|Baseline"].get("mean_r", math.nan)
        rows[name] = {"n_oos": int(len(r)), "mean_r_oos": float(r.mean()) if len(r) else math.nan, "boot95_oos": [lo, hi],
                      "baseline_mean_r_oos": float(rb.mean()) if len(rb) else math.nan, "welch_p": ps[name],
                      "dev_diff": dev_m - dev_b, "dev_mean_r": dev_m}
    adj = b19.holm_adjusted({k: (1.0 if (v != v) else v) for k, v in ps.items()})
    for name, row in rows.items():
        row["holm_p"] = adj[name]
        oos_diff = row["mean_r_oos"] - row["baseline_mean_r_oos"]
        row["supported"] = bool(row["boot95_oos"][0] > 0 and row["holm_p"] < 0.05 and oos_diff > 0 and row["dev_diff"] > 0)
    sup = [k for k, v in rows.items() if v["supported"]]
    rec = max(sup, key=lambda k: rows[k]["dev_mean_r"]) if sup else None
    return {"rows": rows, "recommended": rec}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True)
    ap.add_argument("--parts", default="development,validation,holdout,recent")
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials")
    a = ap.parse_args(argv)
    parts = {p: run(a.rd, p, trials=a.trials) for p in a.parts.split(",")}
    rep = {"registration": REG, "parts": {p: {"meta": v["meta"], "results": v["results"]} for p, v in parts.items()}}
    if all(p in parts for p in ("development",) + SEALED):
        rep["decision"] = decide(parts)
    with open(a.out, "w") as f:
        json.dump(rep, f, indent=1, default=lambda v: None if (isinstance(v, float) and v != v) else float(v))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
