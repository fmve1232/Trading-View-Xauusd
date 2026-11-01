"""Phase B5: REAL ORDER FLOW from COMEX gold futures (CME Globex, via Databento) against the operator's -$10 stop
with +$10 / +$15 / +$20 targets. DEVELOPMENT data only (Amendment 13). The operator approved the study on 2026-11-01
("approve B5 order flow study"; design in research/ORDER_FLOW_RESEARCH.md section 5). This module was declared and
committed BEFORE any order-flow data was obtained, and must not be changed after results are seen.

It runs on GitHub Actions (.github/workflows/research-orderflow.yml), where the network is open and the API key is the
repository secret DATABENTO_API_KEY. Only AGGREGATE results are written. Raw exchange data and per-bar features are
never stored or committed (CME licensing). The one exception is the workflow's repeat-after-failure cache: the
15-minute sums, AES-encrypted with the secret, in the repository's private Actions cache.

    python -m quantum.research.b5_orderflow --spot <research-data checkout> --out <results.json> \
           --trials <trials.jsonl> [--max-cost-usd 100] [--quote-only] [--allow-rerun] [--flow-cache <dir>]

DATA
  Databento GLBX.MDP3, schema "tbbo": every trade with its aggressor side and the best bid / offer just before it.
  Symbol GC.v.0, the most-traded gold futures contract (Databento continuous symbology, rolled by volume).
  Window: the development partition, 2020-01-24 02:00 -> 2023-01-24 02:00 UTC, fetched in 7-day pieces.
  Each piece is reduced to 15-minute sums at once, and the trades are discarded.
COST GUARD
  metadata.get_cost for the whole request runs first. Nothing is downloaded when the quote exceeds --max-cost-usd
  (default $100, inside Databento's $125 new-account credit). --quote-only prints the quote and stops.
DEVIATIONS FROM THE SECTION 5 DESIGN, stated before any data
  - Schema tbbo instead of trades + mbp-1. tbbo is the same trades, with the book at each trade, at a fraction of
    mbp-1's size. Cont's OFI is therefore TRADE-SAMPLED: computed between consecutive pre-trade book states rather
    than over every book update. Multi-level OFI (mbp-10) is not run.
  - Decisions are every 15-minute bar. Paths are SPOT XAU/USD 15-minute bars (research-data branch; the operator's
    instrument), with B2's horizon, fills, costs and one-position rule, so the results compare with B1-B4.
    GC paths are not used.
FEATURES per 15-minute bar (UTC open time; built only from trades inside the bar or earlier, so known at its close)
    imb1, imb5, imb15   (buyer-initiated - seller-initiated volume) / (their sum), over the bar's last 1 / 5 minutes and
                        the whole bar. Databento side "B" = buyer-initiated (lifted the offer), "A" = seller-initiated.
    imb60               the same over the last 4 traded bars
    ofi15, ofi60        trade-sampled Cont-Kukanov-Stoikov OFI summed over the bar / the last 4 traded bars, divided by
                        the mean top-of-book depth (bid size + ask size) / 2 over the same trades
    qimb                queue imbalance before the bar's last trade: (bid size - ask size) / (bid size + ask size)
    ntr_z               log trade count, z-scored over the previous 2,000 traded bars
    spread              ask - bid before the bar's last trade
  ROLLS: on the UTC day the front contract changes, and the day after, every feature is set missing.
Q1 DIRECTION (decides)
  Rules: x in imb15, imb60, ofi15, ofi60 and qimb. A rule fires where |x| is at or above its trailing 90th percentile
    (the previous 2,000 traded bars, the current one excluded).
    CONT trades sign(x) (the literature's direction). REV trades -sign(x).
    5 features x 2 x 3 targets = 30 trials.
  Models: logistic regression (L2 = 1, standardized) and gradient-boosted trees (scikit-learn
    HistGradientBoostingClassifier with the GBT settings below).
    Inputs: the 9 features, with the directional ones multiplied by the trade direction. Long and short decisions are
    stacked at every bar. Label: target before stop.
    Validation: walk-forward over 6 contiguous blocks. Blocks 2-6 are each predicted by a model trained on every
    earlier row whose 288-bar label window ends before the block starts (purged).
    A model "trades" its top decile: predictions at or above the 90th percentile of its own training-row predictions.
    Only one position is open at a time.
    2 models x 3 targets = 6 trials.
  Out-of-fold report (research/09 section 5): AUC, Brier against the base rate, log loss, ECE and maximum calibration
    error (10 equal-width bins), and the calibration slope and intercept.
  Family verdict: all 36 trials together face B2's five-part rule:
    (1) the Wilson lower bound is above break-even;
    (2) t > 3 with net > 0;
    (3) z > 2 against a random entry with the same long / short mix;
    (4) Benjamini-Hochberg at q = 0.10;
    (5) White's Reality Check p < 0.05.
  A model trial also needs an out-of-fold AUC of at least 0.55.
Q2 EXECUTION (descriptive, not a trial)
  The mean spot move over the next 15 and 60 minutes, scaled to $4,000, by imb15 decile and in the flow's direction.
The operator's 90% target is reported beside every result.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from itertools import pairwise

import numpy as np
import pandas as pd

from .. import ta
from . import b2, history
from . import harness as H

DATASET, SCHEMA, SYMBOL, STYPE = "GLBX.MDP3", "tbbo", "GC.v.0", "continuous"
COLS = ("side", "size", "bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00", "instrument_id")
TARGETS = {"T10": (10.0, 10.0), "T15": (15.0, 10.0), "T20": (20.0, 10.0)}
BAR, BAR_SEC = "15min", 900
PCT, PCT_BARS, Z_BARS = 0.90, 2000, 2000
RULE_FEATURES = ("imb15", "imb60", "ofi15", "ofi60", "qimb")
MODEL_FEATURES = ("imb1", "imb5", "imb15", "imb60", "ofi15", "ofi60", "qimb", "ntr_z", "spread")
DIRECTIONAL = ("imb1", "imb5", "imb15", "imb60", "ofi15", "ofi60", "qimb")
BLOCKS, TOP_Q = 6, 0.90
L2 = 1.0
GBT = {"max_iter": 200, "learning_rate": 0.05, "max_leaf_nodes": 15, "min_samples_leaf": 200, "l2_regularization": 1.0,
       "early_stopping": False, "random_state": 7}
AUC_MIN, Z_MIN, BH_Q, RC_P = 0.55, 2.0, 0.10, 0.05
MAX_COST_USD, CHUNK_DAYS, RETRIES = 100.0, 7, 3
QUOTE_ALTERNATIVES = ("trades",)


# ---------------- features ----------------
def bar_features(tr: pd.DataFrame) -> pd.DataFrame:
    """tr: one row per trade, UTC DatetimeIndex (exchange event time), columns COLS. One row per 15-minute bar
    (open time) that has trades: volume sums by aggressor, trade count, trade-sampled OFI and depth sums, and the
    book before the bar's last trade."""
    cols = ["buy", "sell", "buy5", "sell5", "buy1", "sell1", "n", "ofi", "depth", "qimb", "spread", "inst"]
    if tr is None or tr.empty:
        return pd.DataFrame(columns=cols, dtype=float)
    t = tr.sort_index(kind="stable")
    key = t.index.floor(BAR)
    off = (t.index - key).total_seconds().to_numpy()
    sz = t["size"].to_numpy(float)
    side = t["side"].astype(str).to_numpy()
    b_ = np.where(side == "B", sz, 0.0)
    s_ = np.where(side == "A", sz, 0.0)
    bp, ap = t["bid_px_00"].to_numpy(float), t["ask_px_00"].to_numpy(float)
    bs, as_ = np.nan_to_num(t["bid_sz_00"].to_numpy(float)), np.nan_to_num(t["ask_sz_00"].to_numpy(float))
    # Cont, Kukanov & Stoikov (2014) OFI between consecutive pre-trade book states (first trade of a piece: 0)
    pbp, pap, pbs, pas = np.r_[np.nan, bp[:-1]], np.r_[np.nan, ap[:-1]], np.r_[0.0, bs[:-1]], np.r_[0.0, as_[:-1]]
    e = (np.where(bp >= pbp, bs, 0.0) - np.where(bp <= pbp, pbs, 0.0)
         - np.where(ap <= pap, as_, 0.0) + np.where(ap >= pap, pas, 0.0))
    e[0] = 0.0
    g = pd.DataFrame({"buy": b_, "sell": s_, "buy5": np.where(off >= 600, b_, 0.0), "sell5": np.where(off >= 600, s_, 0.0),
                      "buy1": np.where(off >= 840, b_, 0.0), "sell1": np.where(off >= 840, s_, 0.0), "n": 1.0, "ofi": e,
                      "depth": (bs + as_) / 2.0}, index=key).groupby(level=0).sum()
    last = pd.DataFrame({"bs": bs, "as": as_, "bp": bp, "ap": ap, "inst": t["instrument_id"].to_numpy(float)}, index=key)
    last = last[~last.index.duplicated(keep="last")]
    tot = last["bs"] + last["as"]
    g["qimb"] = ((last["bs"] - last["as"]) / tot.where(tot > 0)).reindex(g.index)
    spr = last["ap"] - last["bp"]
    g["spread"] = spr.where(spr >= 0).reindex(g.index)
    g["inst"] = last["inst"].reindex(g.index)
    g.index.name = None
    return g[cols]


def _ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    return (num / den.where(den > 0)).astype(float)


def finish_features(raw: pd.DataFrame) -> pd.DataFrame:
    """Rolling features from the per-bar sums. Row i uses rows <= i only. Roll days are blanked."""
    f = raw.sort_index().copy()
    f["imb15"] = _ratio(f["buy"] - f["sell"], f["buy"] + f["sell"])
    f["imb5"] = _ratio(f["buy5"] - f["sell5"], f["buy5"] + f["sell5"])
    f["imb1"] = _ratio(f["buy1"] - f["sell1"], f["buy1"] + f["sell1"])
    b4, s4 = f["buy"].rolling(4, min_periods=4).sum(), f["sell"].rolling(4, min_periods=4).sum()
    f["imb60"] = _ratio(b4 - s4, b4 + s4)
    f["ofi15"] = _ratio(f["ofi"], f["depth"] / f["n"])
    n4, d4, o4 = (f[k].rolling(4, min_periods=4).sum() for k in ("n", "depth", "ofi"))
    f["ofi60"] = _ratio(o4, d4 / n4)
    ln = np.log(f["n"].clip(lower=1.0))
    mu = ln.shift(1).rolling(Z_BARS, min_periods=200).mean()
    sd = ln.shift(1).rolling(Z_BARS, min_periods=200).std()
    f["ntr_z"] = _ratio(ln - mu, sd)
    chg = f["inst"].ne(f["inst"].shift(1)) & f["inst"].shift(1).notna()
    days = pd.DatetimeIndex(f.index[chg.to_numpy()]).normalize()
    bad = set(days) | set(days + pd.Timedelta(days=1))
    roll = np.asarray(pd.DatetimeIndex(f.index).normalize().isin(list(bad)), bool) if bad else np.zeros(len(f), bool)
    f.loc[roll, list(MODEL_FEATURES)] = np.nan
    f["roll_day"] = roll
    return f


def rule_signal(x: pd.Series) -> pd.Series:
    """+1 / -1 where |x| reaches its trailing 90th percentile (previous PCT_BARS non-missing bars, current excluded)."""
    v = x.dropna()
    a = v.abs()
    thr = a.shift(1).rolling(PCT_BARS, min_periods=PCT_BARS).quantile(PCT)
    on = thr.notna() & (a >= thr) & (v != 0)
    return pd.Series(np.where(on, np.sign(v), 0.0), index=v.index).reindex(x.index).fillna(0.0)


# ---------------- models (logistic in numpy; trees from scikit-learn, installed by the workflow only) -------------
def fit_logistic(X: np.ndarray, y: np.ndarray, l2: float = L2, iters: int = 60) -> np.ndarray:
    """Newton-Raphson with an L2 penalty (intercept unpenalized)."""
    Xb = np.c_[np.ones(len(X)), X]
    w = np.zeros(Xb.shape[1])
    reg = np.eye(Xb.shape[1]) * l2
    reg[0, 0] = 0.0
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(Xb @ w, -30, 30)))
        grad = Xb.T @ (p - y) + reg @ w
        hess = (Xb * (p * (1 - p))[:, None]).T @ Xb + reg + 1e-9 * np.eye(len(w))
        step = np.linalg.solve(hess, grad)
        w -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    return w


def predict_logistic(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(np.c_[np.ones(len(X)), X] @ w, -30, 30)))


class Logit:
    name = "LOGIT"

    def fit(self, X, y):
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-12
        self.w = fit_logistic((X - self.mu) / self.sd, y)
        return self

    def predict(self, X):
        return predict_logistic(self.w, (X - self.mu) / self.sd)


class Trees:
    name = "GBT"

    def fit(self, X, y):
        from sklearn.ensemble import HistGradientBoostingClassifier
        self.m = HistGradientBoostingClassifier(**GBT).fit(X, y.astype(int))
        return self

    def predict(self, X):
        return self.m.predict_proba(X)[:, 1]


def auc(y: np.ndarray, p: np.ndarray) -> float:
    """Mann-Whitney AUC, ties averaged."""
    y = np.asarray(y, int)
    n1, n0 = int(y.sum()), int(len(y) - y.sum())
    if n1 == 0 or n0 == 0:
        return math.nan
    r = pd.Series(p).rank(method="average").to_numpy()
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def calibration(y: np.ndarray, p: np.ndarray, bins: int = 10) -> dict:
    y, p = np.asarray(y, float), np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    k = np.minimum((p * bins).astype(int), bins - 1)
    ece = mce = 0.0
    for b in range(bins):
        m = k == b
        if m.any():
            gap = abs(p[m].mean() - y[m].mean())
            ece += m.mean() * gap
            mce = max(mce, gap)
    w = fit_logistic(np.log(p / (1 - p))[:, None], y, l2=0.0)
    return {"brier": float(np.mean((p - y) ** 2)), "log_loss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))),
            "ece": float(ece), "mce": float(mce), "slope": float(w[1]), "intercept": float(w[0])}


def walk_forward(I: np.ndarray, span: int, blocks: int = BLOCKS) -> list[tuple[np.ndarray, np.ndarray]]:
    """Rows sorted by bar index I. Blocks 2..k are tested; each trains on rows whose label window [I, I + span]
    ends before the block's first bar (purged)."""
    edges = np.linspace(I.min(), I.max() + 1, blocks + 1).astype(np.int64)
    out = []
    for a, b in pairwise(edges[1:]):
        out.append((np.flatnonzero(I + span < a), np.flatnonzero((I >= a) & (I < b))))
    return out


# ---------------- data access (GitHub Actions only) ----------------
def _client(key: str):
    import databento as db  # installed by the workflow only; never a production dependency
    return db, db.Historical(key)


def quote(key: str, start: str, end: str, schema: str = SCHEMA) -> float:
    _, client = _client(key)
    return float(client.metadata.get_cost(dataset=DATASET, symbols=[SYMBOL], stype_in=STYPE, schema=schema, start=start, end=end))


def fetch(key: str, start: str, end: str, max_cost: float) -> tuple[pd.DataFrame, dict]:
    """Cost-guarded download in CHUNK_DAYS pieces, each reduced to per-bar sums at once (raw trades discarded)."""
    db, client = _client(key)
    cost = float(client.metadata.get_cost(dataset=DATASET, symbols=[SYMBOL], stype_in=STYPE, schema=SCHEMA, start=start, end=end))
    if not math.isfinite(cost) or cost > max_cost:
        raise RuntimeError(f"cost guard: the request is quoted at ${cost:.2f}, above the ${max_cost:.2f} budget; nothing downloaded")
    t0, t1 = pd.Timestamp(start), pd.Timestamp(end)
    parts, trades, pieces = [], 0, 0
    a = t0
    while a < t1:
        b = min(a + pd.Timedelta(days=CHUNK_DAYS), t1)
        for attempt in range(RETRIES):
            try:
                df = client.timeseries.get_range(dataset=DATASET, symbols=[SYMBOL], stype_in=STYPE, schema=SCHEMA,
                                                 start=a.isoformat(), end=b.isoformat()).to_df()
                break
            except Exception as exc:  # network errors of any kind; re-raised after the last attempt
                if attempt == RETRIES - 1:
                    raise
                print(f"{a:%Y-%m-%d}: retry after {type(exc).__name__}", flush=True)
                time.sleep(5 * 2 ** attempt)
        if len(df):
            if "ts_event" in df.columns:
                idx = pd.to_datetime(df["ts_event"], utc=True)
            elif df.index.name == "ts_event":
                idx = pd.to_datetime(df.index, utc=True)
            else:
                raise RuntimeError("tbbo frame has no ts_event")
            tr = df[list(COLS)].set_axis(pd.DatetimeIndex(idx), axis=0)
            parts.append(bar_features(tr[(tr.index >= a) & (tr.index < b)]))
            trades += len(df)
        pieces += 1
        print(f"{a:%Y-%m-%d} -> {b:%Y-%m-%d}: {len(df)} trades", flush=True)
        del df
        a = b
    raw = pd.concat(parts) if parts else bar_features(None)
    raw = raw[~raw.index.duplicated(keep="first")].sort_index()
    return raw, {"cost_usd": cost, "trades": trades, "pieces": pieces, "flow_bars": len(raw),
                 "databento_version": getattr(db, "__version__", "?")}


# ---------------- the study ----------------
def _outcomes(P: b2.Paths, t_close: np.ndarray, c: np.ndarray) -> dict:
    """Every spot bar, long and short, every target: outcome (1 / 0 / -1 open; -2 = no full path), result, exit."""
    j, ok = P.locate(t_close)
    sc = c[ok] / b2.REF_PRICE
    out = {}
    for dname, dv in (("long", 1.0), ("short", -1.0)):
        ev = P.evaluate(j[ok], c[ok], np.full(int(ok.sum()), dv), [(a * sc, b * sc) for a, b in TARGETS.values()])
        for tn, e in zip(TARGETS, ev):
            o = np.full(len(c), -2, np.int8)
            pnl, ex = np.zeros(len(c)), np.zeros(len(c), np.int64)
            o[ok], pnl[ok], ex[ok] = e["out"], e["pnl"], e["exit"]
            out[(tn, dname)] = (o, pnl, ex)
    return out


def _trial(P, t_close, c, cost_bar, outc, base, i, d, tn) -> tuple[dict, pd.Series]:
    """One-position stats of decisions (bar i, direction d) at target tn, against the direction-matched random rate."""
    a, b = TARGETS[tn]
    order = np.argsort(t_close[i], kind="stable")
    i, d = i[order], d[order]
    o = np.where(d > 0, outc[(tn, "long")][0][i], outc[(tn, "short")][0][i])
    keep_ok = o != -2
    i, d = i[keep_ok], d[keep_ok]
    if not len(i):
        return {"n": 0, "pass": {"1_wilson_lb_above_break_even": False, "2_t_above_3": False, "3_beats_random_by_2se": False}}, pd.Series(dtype=float)
    o, pnl, ex = (np.where(d > 0, outc[(tn, "long")][k][i], outc[(tn, "short")][k][i]) for k in range(3))
    keep = b2.one_position(t_close[i], P.t[np.minimum(ex, len(P.t) - 1)] + b2.PATH_SEC)
    sc = c[i][keep] / b2.REF_PRICE
    st = b2._stats(o[keep], pnl[keep], cost_bar[i][keep] * sc, a * sc, b * sc, d[keep])
    rnd = (st["long"] * base[f"{tn} long"] + st["short"] * base[f"{tn} short"]) / st["n"]
    z = (st["win_rate"] - rnd) / math.sqrt(max(rnd * (1 - rnd), 1e-12) / st["n"])
    rec = {**{k: st.get(k) for k in ("n", "long", "short", "wins", "losses", "open", "win_rate", "wilson", "break_even", "net_r", "gross_r", "t")},
           "decisions": len(i), "random_same_mix": rnd, "z_vs_random": z, "usd_per_trade_0p5lot": st["net_r"] * b * 50,
           "operator_target_90": {"wilson_lower_at_least_0p90": bool(st["wilson"][0] >= 0.90)},
           "pass": {"1_wilson_lb_above_break_even": bool(st["wilson"][0] > st["break_even"]),
                    "2_t_above_3": bool((st["t"] if st["t"] is not None and math.isfinite(st["t"]) else 0) > 3 and st["net_r"] > 0),
                    "3_beats_random_by_2se": bool(z > Z_MIN)}}
    net_r = (pnl[keep] - cost_bar[i][keep] * sc) / (b * sc)
    daily = pd.Series(net_r, index=pd.to_datetime(t_close[i][keep], unit="s", utc=True).normalize()).groupby(level=0).sum()
    return rec, daily


def study(feat: pd.DataFrame, m15: pd.DataFrame, models: tuple = (Logit, Trees), rules: tuple = RULE_FEATURES,
          inputs: tuple = MODEL_FEATURES, directional: tuple = DIRECTIONAL, q2: str = "imb15") -> dict:
    """feat: per-bar flow features (B5: finish_features of futures bars). m15: spot 15-minute bars of the development
    partition. rules / inputs / directional / q2 default to B5's declaration; B5c (b5c_dukascopy.py) passes its own."""
    span = b2.HORIZON
    P = b2.Paths(m15)
    t_close = ta.epoch_s(m15.index) + BAR_SEC
    c = m15["close"].to_numpy(float)
    cost_bar = H.cost_pts(m15.index)
    f = feat.reindex(m15.index)
    outc = _outcomes(P, t_close, c)
    base = {f"{tn} {dn}": float(np.mean(outc[(tn, dn)][0][outc[(tn, dn)][0] != -2] == 1)) for tn in TARGETS for dn in ("long", "short")}
    res = {"spot_bars": len(m15), "spot_data_hash": H.data_hash(m15), "flow_bars": len(feat),
           "spot_bars_with_flow": int(f[q2].notna().sum()), "roll_day_bars": int(feat.get("roll_day", pd.Series(dtype=bool)).sum()),
           "baseline": base, "trials": [], "models": {}, "execution": {}}
    daily = {}

    for x in rules:                                                           # Q1 rules
        sig = rule_signal(feat[x]).reindex(m15.index).fillna(0.0).to_numpy()
        for rule, sgn in (("CONT", 1.0), ("REV", -1.0)):
            i = np.flatnonzero(sig != 0)
            for tn in TARGETS:
                rec, dser = _trial(P, t_close, c, cost_bar, outc, base, i, sig[i] * sgn, tn)
                tid = f"15min {x}_{rule} {tn}"
                res["trials"].append({"id": tid, "kind": "rule", "feature": x, "rule": rule, "target": tn, **rec})
                daily[tid] = dser

    X0 = f[list(inputs)].to_numpy(float)                                      # Q1 models
    valid = np.isfinite(X0).all(axis=1)
    for tn in TARGETS:
        rows, ys, dirs, idx = [], [], [], []
        for dname, dv in (("long", 1.0), ("short", -1.0)):
            o = outc[(tn, dname)][0]
            m = valid & (o != -2)
            Xd = X0[m].copy()
            for k, nm in enumerate(inputs):
                if nm in directional:
                    Xd[:, k] *= dv
            rows.append(Xd)
            ys.append((o[m] == 1).astype(float))
            dirs.append(np.full(int(m.sum()), dv))
            idx.append(np.flatnonzero(m))
        X, Y, D, I = np.vstack(rows), np.concatenate(ys), np.concatenate(dirs), np.concatenate(idx)
        srt = np.argsort(I, kind="stable")
        X, Y, D, I = X[srt], Y[srt], D[srt], I[srt]
        for M in models:
            tid = f"15min {M.name} {tn}"
            if len(I) < 1000:
                res["models"][tid] = {"verdict": "NOT RUN", "reason": f"{len(I)} rows"}
                continue
            try:
                oof, top = np.full(len(Y), np.nan), np.zeros(len(Y), bool)
                for train, test in walk_forward(I, span):
                    if len(test) == 0 or len(train) < 500:
                        continue
                    mdl = M().fit(X[train], Y[train])
                    thr = float(np.quantile(mdl.predict(X[train]), TOP_Q))
                    oof[test] = mdl.predict(X[test])
                    top[test] = oof[test] >= thr
            except ImportError as exc:
                res["models"][tid] = {"verdict": "NOT RUN", "reason": f"{type(exc).__name__}: {exc}"}
                continue
            ok = np.isfinite(oof)
            if not ok.any():
                res["models"][tid] = {"verdict": "NOT RUN", "reason": "no test block had enough training rows"}
                continue
            br = float(Y[ok].mean())
            rec, dser = _trial(P, t_close, c, cost_bar, outc, base, I[top], D[top], tn)
            A = auc(Y[ok], oof[ok])
            rec["pass"]["0_auc_at_least_0p55"] = bool(A >= AUC_MIN)
            res["models"][tid] = {"rows_oof": int(ok.sum()), "base_rate_oof": br, "brier_base": br * (1 - br), "auc": A,
                                  **calibration(Y[ok], oof[ok]), "top_rows": int(top.sum())}
            res["trials"].append({"id": tid, "kind": "model", "model": M.name, "target": tn, **rec})
            daily[tid] = dser

    names = [t["id"] for t in res["trials"]]                                  # family: BH and the Reality Check
    tmap = {t["id"]: t for t in res["trials"]}
    pv = [H.t_pvalue(tmap[x]["t"], tmap[x]["n"]) if tmap[x]["n"] and tmap[x].get("t") is not None and math.isfinite(tmap[x]["t"]) else 1.0 for x in names]
    bh = H.benjamini_hochberg(pv, BH_Q) if names else []
    Dd = pd.DataFrame({k: daily[k] for k in names}).fillna(0.0).sort_index() if names else pd.DataFrame()
    rc = H.reality_check(Dd[names].to_numpy(), B=1000, mean_block=10.0) if len(Dd) > 20 else {"p_value": 1.0, "best": 0, "note": "too few days"}
    for x, okb in zip(names, bh):
        tmap[x]["pass"]["4_bh_fdr10"] = bool(okb)
        tmap[x]["pass"]["5_reality_check_p_below_0p05"] = bool(rc["p_value"] < RC_P)
        tmap[x]["passes_all"] = all(tmap[x]["pass"].values())
    res["family"] = {"trials": len(names), "days": len(Dd), "reality_check": {**rc, "best_id": names[rc["best"]] if names else None},
                     "bh_fdr10_passed": [x for x, okb in zip(names, bh) if okb],
                     "passes_all": [x for x in names if tmap[x].get("passes_all")]}

    x = f[q2].to_numpy(float)                                                 # Q2 execution (descriptive)
    tt = P.t
    n_ = len(c)
    nxt1 = np.full(n_, np.nan)
    nxt4 = np.full(n_, np.nan)
    if n_ > 4:
        c1 = (tt[1:] - tt[:-1]) == BAR_SEC
        nxt1[:-1] = np.where(c1, c[1:] - c[:-1], np.nan)
        c4 = (tt[4:] - tt[:-4]) == 4 * BAR_SEC
        nxt4[:-4] = np.where(c4, c[4:] - c[:-4], np.nan)
    sc = b2.REF_PRICE / c
    ok = np.isfinite(x) & np.isfinite(nxt1) & np.isfinite(nxt4)
    if ok.sum() >= 100:
        dec = pd.qcut(pd.Series(x[ok]).rank(method="first"), 10, labels=False).to_numpy()
        m1, m4 = (nxt1 * sc)[ok], (nxt4 * sc)[ok]
        res["execution"] = {f"by_{q2}_decile": {str(k): {"n": int((dec == k).sum()), f"{q2}_mean": float(x[ok][dec == k].mean()),
                                                           "next_15m_usd": float(m1[dec == k].mean()), "next_60m_usd": float(m4[dec == k].mean())}
                                                 for k in range(10)},
                            "with_the_flow_usd": {"next_15m": float(np.mean(np.sign(x[ok]) * m1)), "next_60m": float(np.mean(np.sign(x[ok]) * m4)),
                                                  "top_decile_abs_next_15m": float(np.mean((np.sign(x[ok]) * m1)[np.abs(x[ok]) >= np.quantile(np.abs(x[ok]), 0.9)]))},
                            "mean_cost_usd_at_4000": float(np.mean(cost_bar * sc))}
    return res


def summary(path: str) -> str:
    """Plain-text digest of a quote or results JSON (aggregate figures only) for the workflow's job summary."""
    with open(path) as f:
        r = json.load(f)
    if "quote_usd" in r:
        alt = "".join(f"; {k} ${v:.2f}" for k, v in r.get("alternatives_usd", {}).items())
        return f"quote ${r['quote_usd']:.2f} for {r['dataset']} {r['schema']} {r['symbol']} {r['from']} -> {r['to']} (budget ${r['budget_usd']:.2f}){alt}"
    nan = float("nan")
    out = [f"cost ${r.get('cost_usd', nan):.2f}  trades {r.get('trades')}  flow bars {r.get('flow_bars')}  spot bars with flow {r.get('spot_bars_with_flow')}",
           (f"passes all five: {r['family']['passes_all'] or 'none'}   BH: {r['family']['bh_fdr10_passed'] or 'none'}   "
            f"Reality Check p {r['family']['reality_check']['p_value']:.3f}")]
    for t in r["trials"]:
        if t["n"]:
            out.append(f"{t['id']:26s} n {t['n']:5d}  win {t['win_rate']:.3f}  random {t['random_same_mix']:.3f}  z {t['z_vs_random']:+.2f}  "
                       f"break-even {t['break_even']:.3f}  net {t['net_r']:+.3f}R  t {t['t']:+.2f}")
        else:
            out.append(f"{t['id']:26s} n     0")
    for k, m in r["models"].items():
        out.append(f"{k:26s} " + ("  ".join(f"{x} {m[x]:.3f}" for x in ("auc", "ece", "slope") if x in m) or f"{m.get('verdict')}: {m.get('reason')}"))
    return "\n".join(out)


FLOW_CSV, FLOW_META = "flow_bars.csv", "flow_meta.json"


def save_flow_cache(d: str, raw: pd.DataFrame, meta: dict) -> None:
    """Per-bar sums (never trades) for a repeat of a FAILED run. Plain CSV and JSON, so reading it executes nothing."""
    os.makedirs(d, exist_ok=True)
    raw.to_csv(os.path.join(d, FLOW_CSV), index_label="bar")
    with open(os.path.join(d, FLOW_META), "w") as f:
        json.dump({**meta, "dataset": DATASET, "schema": SCHEMA, "symbol": SYMBOL, "from": H.DEV[0].isoformat(), "to": H.DEV[1].isoformat()}, f)


def load_flow_cache(d: str) -> tuple[pd.DataFrame | None, dict | None]:
    pc, pm = os.path.join(d, FLOW_CSV), os.path.join(d, FLOW_META)
    if not (os.path.exists(pc) and os.path.exists(pm)):
        return None, None
    with open(pm) as f:
        meta = json.load(f)
    if (meta.get("dataset"), meta.get("schema"), meta.get("symbol"), meta.get("from"), meta.get("to")) != \
            (DATASET, SCHEMA, SYMBOL, H.DEV[0].isoformat(), H.DEV[1].isoformat()):
        raise RuntimeError("flow cache is for a different request; delete it")
    raw = pd.read_csv(pc, index_col="bar")
    raw.index = pd.to_datetime(raw.index, utc=True)
    raw.index.name = None
    print(f"flow cache: {len(raw)} bars reused (no new download)", flush=True)
    return raw.astype(float), {**meta, "from_cache": True}


def _already_run(trials_path: str) -> bool:
    if not os.path.exists(trials_path):
        return False
    with open(trials_path) as f:
        return any('"phase": "B5"' in line and '"partition": "development"' in line for line in f)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spot", required=True, help="research-data checkout (spot XAU/USD 15min)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials", required=True, help="append-only trial records are written here")
    ap.add_argument("--max-cost-usd", type=float, default=MAX_COST_USD)
    ap.add_argument("--quote-only", action="store_true")
    ap.add_argument("--allow-rerun", action="store_true")
    ap.add_argument("--flow-cache", help="directory for the per-bar sums, so a failed run can be repeated without paying "
                                         "again; the workflow keeps it only in an encrypted, repository-private cache")
    a = ap.parse_args(argv)
    key = os.environ.get("DATABENTO_API_KEY", "").strip()
    if not key:
        raise SystemExit("DATABENTO_API_KEY is not set (add it as a repository secret)")
    start, end = H.DEV[0].isoformat(), H.DEV[1].isoformat()
    if a.quote_only:
        q = {"set": "B5", "quote_usd": quote(key, start, end), "dataset": DATASET, "schema": SCHEMA, "symbol": SYMBOL, "from": start, "to": end,
             "budget_usd": a.max_cost_usd,
             # information only: the same window in the trades schema (aggressor side, no book), for the operator's choice
             "alternatives_usd": {s: quote(key, start, end, s) for s in QUOTE_ALTERNATIVES}}
        with open(a.out, "w") as f:
            json.dump(q, f, indent=1)
        print(json.dumps(q, indent=1))
        return 0
    if _already_run(a.trials) and not a.allow_rerun:
        raise SystemExit(f"B5 already has development records in {a.trials}; re-running needs --allow-rerun")
    m15 = H.partition(history.load(a.spot, "XAU/USD", "15min"), "development")
    raw, meta = load_flow_cache(a.flow_cache) if a.flow_cache else (None, None)
    if raw is None:
        raw, meta = fetch(key, start, end, a.max_cost_usd)
        if a.flow_cache:
            save_flow_cache(a.flow_cache, raw, meta)
    res = study(finish_features(raw), m15)
    res.update({"set": "B5", "partition": "development", "dataset": DATASET, "schema": SCHEMA, "symbol": SYMBOL, "from": start, "to": end, **meta})
    for t in res["trials"]:
        H.log_trial(a.trials, {"phase": "B5", "partition": "development", "data_hash": res["spot_data_hash"], "flow": f"{DATASET}/{SCHEMA}/{SYMBOL}",
                               **t, **({"model_report": res["models"][t["id"]]} if t["kind"] == "model" else {})})
    with open(a.out, "w") as f:
        json.dump(res, f, indent=1, default=float)
    print(json.dumps({"family": res["family"], "models": res["models"], "cost_usd": meta["cost_usd"]}, indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
