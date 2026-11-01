"""Phase B3 (research/14): trend alignment + confirmation entries + SMC sequences, combined, on the operator's
-$10 stop with +$10 / +$15 / +$20 targets. DEVELOPMENT data only.

Declared 2026-11-01, committed before the first run, and not changed after seeing results.

    python -m quantum.research.b3 <research-data checkout> <out.json> [--registry research/trials.jsonl]

THE REQUEST (operator, 2026-11-01): "-$10 stop with +$10, +$15 and +$20 profit with success rate more than 90% ...
by improving structure, sequence, trend / confirmation". At 0.5 lot: SL $500, TP $500 / $750 / $1,000.
    T10  +$10 before -$10    break-even ~54%, random ~50%
    T15  +$15 before -$10    break-even ~43%, random ~40%
    T20  +$20 before -$10    break-even ~36%, random ~33%
The success rate is reported against 90% as asked, against break-even, and against random entries treated
identically (same filter, same confirmation, same direction mix). The research brief's rules apply: no tuning on
these results, no cherry-picking, every trial logged.

EVERYTHING NOT LISTED BELOW IS B2's DECLARATION (quantum/research/b2.py): development partition, 15min / 1h decision
bars, 15-minute paths over 3 trading days, prices and costs scaled to $4,000 (unscaled logged as a sensitivity),
frozen costs, fills at the level or a gapping open, one position at a time.

SETUPS: B2's nine (SWEEP_PD, SWEEP_PW, SWEEP_EQ, BREAK_PD, BOS, CHOCH, FVG_RETEST, OB_RETEST, FAILED_BO) plus two SMC
sequences (the "full model" practitioners describe):
    SEQ_SWEEP_MSS      a liquidity sweep (prior day / prior week / equal highs-lows; B2's definitions) followed within
                       12 bars by a structure break in the sweep's trade direction -> trade at the break bar; each
                       sweep is used once
    SEQ_SWEEP_MSS_FVG  after a SEQ_SWEEP_MSS signal, the first FVG_RETEST in the same direction within 20 bars
FILTER (trend):
    none               as B2
    trend              trade only in the direction of the 1h trend: close > EMA50 > EMA200 (up) or close < EMA50 <
                       EMA200 (down), from the last COMPLETED 1h bar at the decision time; no trade when mixed
CONFIRMATION (entry):
    no                 enter at the decision bar's close (as B2)
    yes                wait up to 8 fifteen-minute bars (2 hours) for a 15-minute close at least $3 (scaled) beyond the
                       decision price in the trade direction, before any close $3 against; enter at that confirming
                       close (the stop and targets are measured from the new entry); otherwise no trade
GRID: B2's nine setups x {none+confirm, trend, trend+confirm} (none+no is B2, already run) and the two sequences x
all four combinations, on 15min and 1h, x 3 targets = (27 + 8) x 2 x 3 = 210 trials.
BASELINE: random decisions (every 2nd 15-minute close of the partition, long and short) passed through the SAME filter
and confirmation, weighted by each trial's long / short mix.
PASS RULE (B2's five parts, all required): (1) Wilson 95% lower bound > break-even; (2) mean net > 0 with one-sided
t > 3; (3) above the matched random rate by more than 2 standard errors; (4) one-sided Benjamini-Hochberg q = 0.10
over the family; (5) White's Reality Check p < 0.05. Reported beside it, not part of the rule: the operator's target,
success rate >= 90% (point estimate and 95% lower bound).
Nothing here opens validation or the holdout.
"""
from __future__ import annotations

import argparse
import json
import math
import sys

import numpy as np
import pandas as pd

from .. import ta
from . import b2, history
from . import harness as H

TARGETS = {"T10": (10.0, 10.0), "T15": (15.0, 10.0), "T20": (20.0, 10.0)}
OPERATOR_TARGET = 0.90
SEQ_MSS_WITHIN = 12
SEQ_FVG_WITHIN = 20
TREND_FAST, TREND_SLOW = 50, 200
CONF_USD, CONF_BARS = 3.0, 8
RANDOM_STEP = 2
SETUPS = b2.SETUPS + ("SEQ_SWEEP_MSS", "SEQ_SWEEP_MSS_FVG")


def combos(setup: str) -> list[tuple[str, bool]]:
    if setup.startswith("SEQ_"):
        return [("none", False), ("none", True), ("trend", False), ("trend", True)]
    return [("none", True), ("trend", False), ("trend", True)]


# ---------------- setups ----------------
def sequences(df: pd.DataFrame, base: dict) -> dict:
    h, l, c = (df[x].to_numpy(float) for x in ("high", "low", "close"))
    n = len(c)
    sw = np.zeros(n)
    for k in ("SWEEP_PD", "SWEEP_PW", "SWEEP_EQ"):
        s = base[k]
        sw = np.where((sw == 0) & (s != 0), s, np.where((sw != 0) & (s != 0) & (s != sw), 9.0, sw))   # 9 = conflict
    sw[sw == 9.0] = 0.0
    brk, _ = b2._structure(h, l, c)
    mss = np.zeros(n)
    pending = []                                     # (direction, bar of the sweep)
    for i in range(n):
        pending = [p for p in pending if i - p[1] <= SEQ_MSS_WITHIN]
        if brk[i] != 0:
            hit = next((p for p in pending if p[0] == brk[i] and p[1] < i), None)
            if hit:
                pending.remove(hit)
                mss[i] = brk[i]
        if sw[i] != 0:
            pending.append((sw[i], i))
    fvg = base["FVG_RETEST"]
    seq_fvg = np.zeros(n)
    live = []                                        # (direction, bar of the MSS)
    for i in range(n):
        live = [x for x in live if i - x[1] <= SEQ_FVG_WITHIN]
        if fvg[i] != 0:
            hit = next((x for x in live if x[0] == fvg[i] and x[1] < i), None)
            if hit:
                live.remove(hit)
                seq_fvg[i] = fvg[i]
        if mss[i] != 0:
            live.append((mss[i], i))
    return {"SEQ_SWEEP_MSS": mss, "SEQ_SWEEP_MSS_FVG": seq_fvg}


# ---------------- filter and confirmation ----------------
class Trend:
    """The 1h trend at any moment, from the last 1h bar that has CLOSED by then."""

    def __init__(self, h1: pd.DataFrame):
        c = h1["close"].to_numpy(float)
        fast, slow = ta.ema(c, TREND_FAST), ta.ema(c, TREND_SLOW)
        self.v = np.where((c > fast) & (fast > slow), 1, np.where((c < fast) & (fast < slow), -1, 0))
        self.v[: TREND_SLOW] = 0                    # EMA warm-up
        self.t_close = ta.epoch_s(h1.index) + 3600

    def at(self, t: np.ndarray) -> np.ndarray:
        k = np.searchsorted(self.t_close, t, side="right") - 1
        return np.where(k >= 0, self.v[np.maximum(k, 0)], 0)


def confirm(P: b2.Paths, t_dec: np.ndarray, p: np.ndarray, d: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """For each decision: (taken, path index of the confirming 15-minute bar, entry close time, entry price)."""
    n = len(t_dec)
    if n == 0:
        z = np.zeros(0, np.int64)
        return np.zeros(0, bool), z, z, np.zeros(0)
    j, ok = P.locate(t_dec)
    last = len(P.t) - 1
    idx = np.minimum(j[:, None] + np.arange(CONF_BARS)[None, :], last)
    dist = CONF_USD * p / b2.REF_PRICE
    mv = (P.c[idx] - p[:, None]) * d[:, None]
    up, dn = mv >= dist[:, None] - 1e-9, mv <= -dist[:, None] + 1e-9
    ku = np.where(up.any(1), up.argmax(1), CONF_BARS)
    kd = np.where(dn.any(1), dn.argmax(1), CONF_BARS)
    take = ok & (ku < kd) & (ku < CONF_BARS) & (j + ku <= last)
    jj = np.minimum(j + np.minimum(ku, CONF_BARS - 1), last)
    return take, jj, P.t[jj] + b2.PATH_SEC, P.c[jj]


def entries(P, trend, t_dec, p, d, cost_dec, cost15, filt: str, conf: bool):
    """Apply the filter, then the confirmation. Returns entry close time, price, direction, cost, decision time."""
    keep = np.ones(len(t_dec), bool) if filt == "none" else (trend.at(t_dec) == d)
    t_dec, p, d, cost_dec = t_dec[keep], p[keep], d[keep], cost_dec[keep]
    if not conf:
        return t_dec, p, d, cost_dec
    take, jj, t_e, p_e = confirm(P, t_dec, p, d)
    return t_e[take], p_e[take], d[take], cost15[jj[take]]


def evaluate(P, t_e, p_e, d, cost, targets: dict):
    """Scaled and unscaled outcomes for every target; drops entries without a full stored path."""
    j, ok = P.locate(t_e)
    t_e, p_e, d, cost, j = t_e[ok], p_e[ok], d[ok], cost[ok], j[ok]
    scale = p_e / b2.REF_PRICE
    ab = [(a * scale, b * scale) for a, b in targets.values()] + [(np.full(len(j), a), np.full(len(j), b)) for a, b in targets.values()]
    ev = P.evaluate(j, p_e, d, ab) if len(j) else [{"out": np.zeros(0, np.int8), "pnl": np.zeros(0), "exit": np.zeros(0, np.int64)} for _ in ab]
    return t_e, p_e, d, cost, scale, ev


# ---------------- run ----------------
def _daily(net_r: np.ndarray, days: pd.DatetimeIndex) -> pd.Series:
    """Net R summed per entry day; a trial without trades gives an empty series that still has a date index
    (fixed 2026-11-01 after the first run stopped here; the trials themselves are unaffected)."""
    if len(net_r) == 0:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
    return pd.Series(net_r, index=days).groupby(level=0).sum()


def run(rd: str, outp: str, registry: str) -> dict:
    m15 = H.partition(history.load(rd, "XAU/USD", "15min"), "development")
    h1 = H.partition(history.load(rd, "XAU/USD", "1h"), "development")
    P, trend = b2.Paths(m15), Trend(h1)
    cost15 = H.cost_pts(m15.index)
    res = {"partition": "development", "set": "B3", "from": str(H.DEV[0]), "to": str(H.DEV[1]),
           "targets": {k: list(v) for k, v in TARGETS.items()}, "operator_target": OPERATOR_TARGET, "baseline": {}, "trials": [], "family": {}}

    # random decisions through the same filter and confirmation
    k = np.arange(0, len(P.t), RANDOM_STEP)
    for filt in ("none", "trend"):
        for conf in (False, True):
            for dname, dv in (("long", 1.0), ("short", -1.0)):
                t_e, p_e, d, cost = entries(P, trend, P.t[k] + b2.PATH_SEC, P.c[k], np.full(len(k), dv), cost15[k], cost15, filt, conf)
                t_e, p_e, d, cost, scale, ev = evaluate(P, t_e, p_e, d, cost, TARGETS)
                for q, (tn, (a, b)) in enumerate(TARGETS.items()):
                    st = b2._stats(ev[q]["out"], ev[q]["pnl"], cost * scale, a * scale, b * scale, d)
                    res["baseline"][f"{filt}{'+conf' if conf else ''} {tn} {dname}"] = {x: st.get(x) for x in ("n", "win_rate", "net_r", "break_even")}
                print(f"baseline {filt}{'+conf' if conf else ''} {dname}: n {len(t_e)}", flush=True)

    daily, names = {}, []
    for tf, tf_sec in b2.TFS.items():
        df = m15 if tf == "15min" else h1
        dh = H.data_hash(df)
        cost_bar = H.cost_pts(df.index)
        t_close = ta.epoch_s(df.index) + tf_sec
        c = df["close"].to_numpy(float)
        base = b2.signals(df)
        sig = {**base, **sequences(df, base)}
        for sname in SETUPS:
            s = sig[sname]
            i = np.flatnonzero(s != 0)
            for filt, conf in combos(sname):
                t_e, p_e, d, cost = entries(P, trend, t_close[i], c[i], s[i], cost_bar[i], cost15, filt, conf)
                t_e, p_e, d, cost, scale, ev = evaluate(P, t_e, p_e, d, cost, TARGETS)
                for q, (tn, (a, b)) in enumerate(TARGETS.items()):
                    e, eu = ev[q], ev[q + len(TARGETS)]
                    keep = b2.one_position(t_e, P.t[np.minimum(e["exit"], len(P.t) - 1)] + b2.PATH_SEC) if len(t_e) else np.zeros(0, np.int64)
                    st = b2._stats(e["out"][keep], e["pnl"][keep], cost[keep] * scale[keep], a * scale[keep], b * scale[keep], d[keep])
                    keep_u = b2.one_position(t_e, P.t[np.minimum(eu["exit"], len(P.t) - 1)] + b2.PATH_SEC) if len(t_e) else np.zeros(0, np.int64)
                    st_u = b2._stats(eu["out"][keep_u], eu["pnl"][keep_u], cost[keep_u], np.full(len(keep_u), a), np.full(len(keep_u), b), d[keep_u])
                    tag = f"{filt}{'+conf' if conf else ''}"
                    bl, bs = res["baseline"][f"{tag} {tn} long"], res["baseline"][f"{tag} {tn} short"]
                    if st["n"]:
                        p_rand = ((st["long"] * bl["win_rate"] if st["long"] else 0) + (st["short"] * bs["win_rate"] if st["short"] else 0)) / st["n"]
                        z = (st["win_rate"] - p_rand) / math.sqrt(max(p_rand * (1 - p_rand), 1e-12) / st["n"])
                    else:
                        p_rand = z = math.nan
                    tid = f"{tf} {sname} {tag} {tn}"
                    rec = {"id": tid, "tf": tf, "setup": sname, "filter": filt, "confirm": conf, "target": tn,
                           "a_usd_at_4000": a, "b_usd_at_4000": b, "data_hash": dh, "decisions": len(i),
                           **{x: st.get(x) for x in ("n", "long", "short", "wins", "losses", "open", "win_rate", "wilson", "break_even", "net_r", "gross_r", "t")},
                           "random_same_treatment": p_rand, "z_vs_random": z,
                           "usd_per_trade_0p5lot": st["net_r"] * b * 50 if st["n"] else None,
                           "unscaled_sensitivity": {x: st_u.get(x) for x in ("n", "win_rate", "net_r", "t")},
                           "operator_target_90": {"point": bool(st["n"] and st["win_rate"] >= OPERATOR_TARGET),
                                                  "lower_95": bool(st["n"] and st["wilson"][0] >= OPERATOR_TARGET)}}
                    rec["pass"] = {"1_wilson_lb_above_break_even": bool(st["n"] and st["wilson"][0] > st["break_even"]),
                                   "2_t_above_3": bool(st["n"] and (st["t"] or 0) > 3 and st["net_r"] > 0),
                                   "3_beats_random_by_2se": bool(st["n"] and z > 2)}
                    res["trials"].append(rec)
                    H.log_trial(registry, {"phase": "B3", "partition": "development", **rec})
                    names.append(tid)
                    dts = pd.to_datetime(t_e[keep], unit="s", utc=True).normalize()
                    net_r = (e["pnl"][keep] - cost[keep] * scale[keep]) / (b * scale[keep]) if len(keep) else np.zeros(0)
                    daily[tid] = _daily(net_r, dts)
                    print(f"{tid:40s} n {st.get('n', 0):5d} win {st.get('win_rate', math.nan):.3f} [{(st.get('wilson') or [math.nan])[0]:.3f}] "
                          f"be {st.get('break_even', math.nan):.3f} rand {p_rand:.3f} z {z:+.2f} net {st.get('net_r', math.nan):+.3f}R", flush=True)

    D = pd.DataFrame(daily).fillna(0.0).sort_index()
    D.index = pd.DatetimeIndex(D.index)
    W = D.groupby(pd.Grouper(freq="W")).sum()
    rc = H.reality_check(D[names].to_numpy(), B=1000, mean_block=10.0)
    tr_map = {t["id"]: t for t in res["trials"]}
    pv = [H.t_pvalue(tr_map[x]["t"], tr_map[x]["n"]) if tr_map[x]["n"] and tr_map[x]["t"] is not None else 1.0 for x in names]
    pv = [1.0 if not math.isfinite(v) else v for v in pv]
    bh = H.benjamini_hochberg(pv, q=0.10)
    sr = (D[names].mean() / D[names].std(ddof=1)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    best = sr.idxmax()
    x = D[best].to_numpy()
    dsr = H.deflated_sharpe(float(sr[best]), len(x), float(pd.Series(x).skew()), float(pd.Series(x).kurt() + 3), list(sr.values))
    for t_, ok in zip(names, bh):
        tr_map[t_]["pass"]["4_bh_fdr10"] = bool(ok)
        tr_map[t_]["pass"]["5_reality_check_p_below_0p05"] = bool(rc["p_value"] < 0.05)
        tr_map[t_]["passes_all"] = all(tr_map[t_]["pass"].values())
    res["family"] = {"trials": len(names), "days": len(D), "weeks": len(W), "reality_check": {**rc, "best_id": names[rc["best"]]},
                     "pbo": H.pbo_cscv(W[names].to_numpy(), groups=8), "best_daily_sharpe": {"id": best, "sharpe_daily": float(sr[best]), **dsr},
                     "bh_fdr10_passed": [n_ for n_, ok in zip(names, bh) if ok],
                     "passes_all": [t_["id"] for t_ in res["trials"] if t_.get("passes_all")],
                     "operator_target_90_point": [t_["id"] for t_ in res["trials"] if t_["operator_target_90"]["point"]],
                     "operator_target_90_lower_95": [t_["id"] for t_ in res["trials"] if t_["operator_target_90"]["lower_95"]],
                     "note": "Screens one-sided (H1: mean net > 0). Flags 1-3 per trial; 4-5 family-wide. The 90% flags are reported, not part of the rule."}
    with open(outp, "w") as f:
        json.dump(res, f, indent=1, default=float)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rd")
    ap.add_argument("out")
    ap.add_argument("--registry", default="research/trials.jsonl")
    a = ap.parse_args(argv)
    r = run(a.rd, a.out, a.registry)
    print(json.dumps(r["family"], indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
