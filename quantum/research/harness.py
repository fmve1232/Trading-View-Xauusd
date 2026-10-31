"""Research harness (Phase B0, research/09). RESEARCH ONLY: never imported by the engine, the arms or the site, and
outside holdout.ENGINE_SOURCES.

What it provides:
  * partitions   Amendment 13's blind split. Development data is free to explore; validation and the sealed holdout
                 open only for a hypothesis whose registration file says the operator approved it.
  * costs        the frozen engine cost model per bar (session spread + 2 x slippage + commission / 100 oz).
  * simulate     one-position-at-a-time trades from signals, with a stop at 1 R, a target at k R and a time stop at
                 h bars. Entry at the signal bar's close; gap fills at the open (Amendment 14). A bar touching both
                 barriers is AMBIGUOUS and charged as a full loss (conservative; research/09 section 3).
  * stats        Wilson, t, the bootstrap, the Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014), PBO by CSCV
                 (Bailey et al. 2017), White's Reality Check with the stationary bootstrap (White 2000; Politis &
                 Romano 1994) and Benjamini-Hochberg.
  * registry     append-only trial log (research/trials.jsonl); its trial count feeds the DSR.

R is the ATR(14) (Wilder) at the signal bar. That is a research convention, stated here, not the engine's adaptive
stop.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from itertools import combinations

import numpy as np
import pandas as pd

from .. import sessions, ta

# ---------------- partitions (Amendment 13) ----------------
DEV = (pd.Timestamp("2020-01-24 02:00", tz="UTC"), pd.Timestamp("2023-01-24 02:00", tz="UTC"))
VAL = (pd.Timestamp("2023-01-24 02:00", tz="UTC"), pd.Timestamp("2024-07-01 00:00", tz="UTC"))
HOLD = (pd.Timestamp("2024-07-01 00:00", tz="UTC"), pd.Timestamp("2026-01-01 00:00", tz="UTC"))
REG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "research", "registrations")


class SealedPartition(PermissionError):
    pass


def partition(df: pd.DataFrame, name: str, registration_id: str | None = None) -> pd.DataFrame:
    """Development is open. Validation / holdout need an approved registration (research/registrations/<id>.json
    with "approved_by_operator": true and the partition listed); anything else raises SealedPartition."""
    if name == "development":
        lo, hi = DEV
    elif name in ("validation", "holdout"):
        path = os.path.join(REG_DIR, f"{registration_id}.json") if registration_id else None
        if not path or not os.path.exists(path):
            raise SealedPartition(f"{name} is sealed: no registration")
        reg = json.load(open(path))
        if not reg.get("approved_by_operator") or name not in reg.get("partitions", []):
            raise SealedPartition(f"{name} is sealed: registration {registration_id} not approved for it")
        lo, hi = VAL if name == "validation" else HOLD
    else:
        raise ValueError(name)
    return df[(df.index >= lo) & (df.index < hi)]


# ---------------- costs ----------------
def cost_pts(index: pd.DatetimeIndex, spread_cost=0.30, slippage=0.20, commission_lot=7.0, point_value=100.0) -> np.ndarray:
    """The frozen engine model per bar: kill zone / NY / London max(floor, 0.30), off session 0.50."""
    cal = sessions.calendar(index)
    kz, lon, ny = (cal[k].to_numpy(bool) for k in ("in_killzone", "in_london", "in_ny"))
    spread = np.where(kz, max(0.18, spread_cost), np.where(ny, max(0.22, spread_cost),
                      np.where(lon, max(0.30, spread_cost), max(0.50, spread_cost))))
    return spread + 2 * slippage + commission_lot / point_value


# ---------------- simulation ----------------
def simulate(df: pd.DataFrame, signal: np.ndarray, k: float, h: int, atr_len: int = 14, cost: np.ndarray | None = None,
             one_position: bool = True) -> pd.DataFrame:
    """signal[i] in {-1, 0, +1} at the close of bar i. Returns one row per trade: entry_i, exit_i, dir, outcome
    (WIN / LOSS / AMBIGUOUS / TIMEOUT), gross_r, cost_r, net_r. A time-stop exit is at that bar's close."""
    o, h_, l, c = (df[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    atr = ta.atr(h_, l, c, atr_len)
    cost = cost_pts(df.index) if cost is None else cost
    n = len(c)
    rows = []
    i = 0
    while i < n - 1:
        d = int(signal[i])
        R = atr[i]
        if d == 0 or not (R > 0):
            i += 1
            continue
        e = c[i]
        stop, tgt = e - d * R, e + d * k * R
        out, px, j = None, None, i
        for j in range(i + 1, min(i + h, n - 1) + 1):
            if d * (o[j] - stop) <= 0:                  # opened through the stop: fill at the open
                out, px = "LOSS", o[j]
                break
            if d * (o[j] - tgt) >= 0:                   # opened beyond the target: fill at the open
                out, px = "WIN", o[j]
                break
            hit_s = (l[j] <= stop) if d > 0 else (h_[j] >= stop)
            hit_t = (h_[j] >= tgt) if d > 0 else (l[j] <= tgt)
            if hit_s and hit_t:
                out, px = "AMBIGUOUS", stop             # charged as a full loss
                break
            if hit_s:
                out, px = "LOSS", stop
                break
            if hit_t:
                out, px = "WIN", tgt
                break
        if out is None:
            out, px = "TIMEOUT", c[j]
        g = d * (px - e) / R
        cr = cost[i] / R
        rows.append((i, j, d, out, g, cr, g - cr))
        i = j if one_position else i + 1
        if one_position and j == i:
            i += 1
    return pd.DataFrame(rows, columns=["entry_i", "exit_i", "dir", "outcome", "gross_r", "cost_r", "net_r"])


# ---------------- purged cross-validation (Lopez de Prado 2018, ch. 7) ----------------
def purged_folds(n: int, k: int, span: int, embargo: int) -> list[tuple[np.ndarray, np.ndarray]]:
    """k contiguous test folds over n samples whose labels look `span` bars ahead. A training sample i is dropped
    when [i, i+span] overlaps the test fold (purge) or when i falls within `embargo` bars after it."""
    out = []
    edges = np.linspace(0, n, k + 1).astype(int)
    idx = np.arange(n)
    for a, b in zip(edges[:-1], edges[1:]):
        test = idx[a:b]
        keep = ~(((idx + span) >= a) & (idx < b)) & ~((idx >= b) & (idx < b + embargo))
        out.append((idx[keep], test))
    return out


# ---------------- statistics ----------------
def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    hw = z * math.sqrt(max(p * (1 - p) / n + z * z / (4 * n * n), 0.0)) / d
    return (max(0.0, c - hw), min(1.0, c + hw))


def summary(tr: pd.DataFrame) -> dict:
    n = len(tr)
    if n == 0:
        return {"n": 0}
    r = tr["net_r"].to_numpy()
    g = tr["gross_r"].to_numpy()
    sd = r.std(ddof=1) if n > 1 else math.nan
    wins = int((tr["outcome"] == "WIN").sum())
    resolved = int(tr["outcome"].isin(["WIN", "LOSS", "AMBIGUOUS"]).sum())
    pos, neg = r[r > 0].sum(), -r[r < 0].sum()
    cum = np.cumsum(r)
    gsd = g.std(ddof=1) if n > 1 else math.nan
    return {"n": n, "gross_r": float(g.mean()), "gross_t": float(g.mean() / (gsd / math.sqrt(n))) if n > 1 and gsd > 0 else math.nan,
            "net_r": float(r.mean()), "sd_r": float(sd),
            "t": float(r.mean() / (sd / math.sqrt(n))) if n > 1 and sd > 0 else math.nan,
            "pf": float(pos / neg) if neg > 0 else math.inf, "win_rate_resolved": wins / resolved if resolved else math.nan,
            "wins": wins, "resolved": resolved, "ambiguous": int((tr["outcome"] == "AMBIGUOUS").sum()),
            "timeouts": int((tr["outcome"] == "TIMEOUT").sum()),
            "max_dd_r": float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max()),
            "sharpe": float(r.mean() / sd) if sd > 0 else math.nan,
            "skew": float(pd.Series(r).skew()) if n > 2 else 0.0, "kurt": float(pd.Series(r).kurt() + 3.0) if n > 3 else 3.0}


def _norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p):
    # Acklam's rational approximation (|error| < 1.2e-9), enough for DSR thresholds
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02, 1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02, 6.680131188771972e01, -1.328068155288572e01]
    cc = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00, -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00]
    pl = 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((cc[0] * q + cc[1]) * q + cc[2]) * q + cc[3]) * q + cc[4]) * q + cc[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - pl:
        return -_norm_ppf(1 - p)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def psr(sr: float, n: int, skew: float, kurt: float, sr0: float = 0.0) -> float:
    """Probabilistic Sharpe ratio: P(true per-trade Sharpe > sr0)."""
    if n < 3 or not math.isfinite(sr):
        return math.nan
    den = math.sqrt(max(1 - skew * sr + (kurt - 1) / 4 * sr * sr, 1e-12))
    return _norm_cdf((sr - sr0) * math.sqrt(n - 1) / den)


def deflated_sharpe(sr: float, n: int, skew: float, kurt: float, trial_srs: list[float]) -> dict:
    """DSR (Bailey & Lopez de Prado 2014): PSR against the expected maximum Sharpe of N independent trials."""
    N = max(len(trial_srs), 1)
    v = float(np.var(trial_srs, ddof=1)) if N > 1 else 0.0
    emc = 0.5772156649
    sr0 = math.sqrt(v) * ((1 - emc) * _norm_ppf(1 - 1 / N) + emc * _norm_ppf(1 - 1 / (N * math.e))) if N > 1 else 0.0
    return {"sr0": sr0, "dsr": psr(sr, n, skew, kurt, sr0), "trials": N}


def pbo_cscv(perf: np.ndarray, groups: int = 8) -> dict:
    """PBO by combinatorially symmetric cross-validation (Bailey et al. 2017). perf: T x N matrix (rows = time blocks
    in order, columns = configurations) of per-block mean net R. Returns PBO = P(the IS-best config ranks below the
    OOS median) and the logit distribution's mean."""
    T, N = perf.shape
    if N < 2 or T < groups:
        return {"pbo": math.nan, "splits": 0}
    blocks = np.array_split(np.arange(T), groups)
    lam, oos_best = [], []
    for is_g in combinations(range(groups), groups // 2):
        is_idx = np.concatenate([blocks[g] for g in is_g])
        oos_idx = np.concatenate([blocks[g] for g in range(groups) if g not in is_g])
        best = int(np.argmax(perf[is_idx].mean(axis=0)))
        oos = perf[oos_idx].mean(axis=0)
        oos_best.append(float(oos[best]))
        rank = (oos < oos[best]).sum() + 0.5 * ((oos == oos[best]).sum() - 1)
        w = (rank + 1) / (N + 1)
        lam.append(math.log(w / (1 - w)))
    lam = np.array(lam)
    ob = np.array(oos_best)
    # PBO is about RANK stability: it can be ~0 while every configuration loses. Report the selected config's OOS
    # result with it (Bailey et al. 2017 also report the probability of an OOS loss).
    return {"pbo": float((lam <= 0).mean()), "logit_mean": float(lam.mean()), "splits": len(lam),
            "oos_mean_of_is_best": float(ob.mean()), "p_oos_loss_of_is_best": float((ob < 0).mean())}


def stationary_bootstrap_idx(n: int, mean_block: float, rng: np.random.Generator) -> np.ndarray:
    idx = np.empty(n, dtype=int)
    p = 1.0 / mean_block
    idx[0] = rng.integers(n)
    for t in range(1, n):
        idx[t] = rng.integers(n) if rng.random() < p else (idx[t - 1] + 1) % n
    return idx


def reality_check(excess: np.ndarray, B: int = 1000, mean_block: float = 10.0, seed: int = 11) -> dict:
    """White (2000) Reality Check. excess: T x N per-period net R of each rule over the benchmark (0 = no trade).
    H0: no rule beats the benchmark. Returns the p-value of the best rule."""
    T, N = excess.shape
    rng = np.random.default_rng(seed)
    f = excess.mean(axis=0)
    v = math.sqrt(T) * f.max()
    cnt = 0
    for _ in range(B):
        idx = stationary_bootstrap_idx(T, mean_block, rng)
        fb = excess[idx].mean(axis=0)
        cnt += (math.sqrt(T) * (fb - f).max()) >= v
    return {"stat": float(v), "p_value": cnt / B, "best": int(np.argmax(f)), "B": B}


def benjamini_hochberg(p: list[float], q: float = 0.10) -> list[bool]:
    m = len(p)
    order = np.argsort(p)
    passed = np.zeros(m, dtype=bool)
    kmax = 0
    for rank, j in enumerate(order, start=1):
        if p[j] <= q * rank / m:
            kmax = rank
    passed[order[:kmax]] = True
    return passed.tolist()


def t_pvalue(t: float, n: int, one_sided: bool = True) -> float:
    """p-value of a t-statistic (normal approximation; n is large in every use here). One-sided by default: the
    research question is "mean > 0", so a significantly NEGATIVE result must not pass a screen."""
    if not math.isfinite(t):
        return math.nan
    return 1 - _norm_cdf(t) if one_sided else 2 * (1 - _norm_cdf(abs(t)))


# ---------------- registry ----------------
def log_trial(path: str, record: dict) -> None:
    rec = {"utc": datetime.now(timezone.utc).isoformat(), **record}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(rec, default=float) + "\n")


def data_hash(df: pd.DataFrame) -> str:
    return hashlib.sha256(pd.util.hash_pandas_object(df[["open", "high", "low", "close"]], index=True).values.tobytes()).hexdigest()[:16]
