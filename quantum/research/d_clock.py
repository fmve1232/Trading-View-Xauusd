"""Phase D amendment A1 (2026-11-09, before any data): timestamp verification beyond B5c's lag-0 gate. Research only.

B5c's A1 / A2 gates (lag of 15-minute changes at -2..+2 bars, overall / by session / by year; weekly edges; basis) can
pass a clock that is wrong by a few minutes, or wrong for a few weeks only. These checks close both gaps. None of them
shifts a timestamp: data that fail are quarantined (set missing) or stop the run.

  weekly_lags       the 15-minute lag check per ISO week (>= WEEK_MIN_BARS bars); a week whose best lag is not 0 is
                    misaligned. Misaligned weeks are quarantined; more than MAX_MISALIGNED_WEEKS of them stops the run.
  minute_offsets    Dukascopy's one-minute mid, read at the spot bar's close shifted by o minutes (o in -5..+5), against
                    the spot close changes: 0 must be among the tied best offsets (within TIE_EPS of the maximum
                    correlation), and the tied set must lie within +-MAX_TIE_SPAN minutes. It presumes quotes at least
                    every minute or two on average (Dukascopy gold quotes many times a minute): much sparser quoting
                    makes the forward-filled read stale and mimics a late clock, so the check is pooled over a period.
  mt5_cross         (when an MT5 export is supplied) one-minute bid close changes, Dukascopy vs the broker, at lags of
                    -5..+5 minutes, overall and per week: the peak must be at 0 and misaligned weeks <= the same share.
  backwards_share   ticks whose millisecond stamp runs backwards inside an hour file (d_dukascopy "ms_backwards"):
                    at most MAX_BACKWARDS of all ticks.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

LAGS_BARS = (-2, -1, 0, 1, 2)
WEEK_MIN_BARS = 200
MAX_MISALIGNED_WEEKS = 0.02
MINUTE_OFFSETS = tuple(range(-5, 6))
MT5_LAGS_MIN = tuple(range(-5, 6))
MT5_WEEK_MIN = 1000
MAX_BACKWARDS = 0.001
TIE_EPS = 0.001          # offsets whose correlation is within this of the maximum are indistinguishable (sparse quotes)
MAX_TIE_SPAN = 3         # minutes: a tied set wider than +-3 cannot pin the clock down, and fails


def _corr(a: pd.Series, b: pd.Series, min_n: int) -> float:
    j = pd.concat([a, b], axis=1).dropna()
    return float(j.iloc[:, 0].corr(j.iloc[:, 1])) if len(j) > min_n else math.nan


def _ties(c: dict) -> list[int]:
    """Every lag / offset within TIE_EPS of the best correlation (ties arise where quotes are sparse)."""
    ok = {k: v for k, v in c.items() if not math.isnan(v)}
    if not ok:
        return []
    top = max(ok.values())
    return sorted(k for k, v in ok.items() if v >= top - TIE_EPS)


def _best(c: dict) -> int | None:
    """The tied best closest to 0 (reporting only: a check passes when 0 itself is among the tied best)."""
    t = _ties(c)
    return min(t, key=lambda k: (abs(k), k)) if t else None


def _week(idx: pd.DatetimeIndex) -> np.ndarray:
    iso = idx.isocalendar()
    return (iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)).to_numpy()


def weekly_lags(raw: pd.DataFrame, m15: pd.DataFrame, scale: float) -> dict:
    mid = (raw["mid_last"] / scale).reindex(m15.index)
    dm, ds = mid.diff(), m15["close"].diff()
    wk = _week(m15.index)
    weeks, bad = {}, []
    for w in sorted(set(wk)):
        m = wk == w
        if int((m & dm.notna().to_numpy() & ds.notna().to_numpy()).sum()) < WEEK_MIN_BARS:
            continue
        c = {k: _corr(dm.shift(k)[m], ds[m], 50) for k in LAGS_BARS}
        weeks[w] = {"best_lag_bars": _best(c), "tied_best": _ties(c), "r0": c[0]}
        if 0 not in weeks[w]["tied_best"]:
            bad.append(w)
    share = len(bad) / len(weeks) if weeks else 0.0
    return {"weeks_checked": len(weeks), "misaligned_weeks": bad, "misaligned_share": share,
            "pass": bool(weeks) and share <= MAX_MISALIGNED_WEEKS, "by_week": weeks}


def minute_offsets(m1: pd.DataFrame, m15: pd.DataFrame, scale: float) -> dict:
    """The spot bar opening at t closes at t + 15 min; Dukascopy's minute closing at t + 15 + o min opens at t + 14 + o."""
    mid = ((m1["bid_c"] + m1["ask_c"]) / 2.0 / scale).sort_index()
    mid = mid[~mid.index.duplicated()]
    ds = m15["close"].diff()
    corr = {}
    for o in MINUTE_OFFSETS:
        target = m15.index + pd.Timedelta(minutes=14 + o)
        s = mid.reindex(target, method="ffill", tolerance=pd.Timedelta(minutes=5))
        s.index = m15.index
        corr[o] = _corr(s.diff(), ds, 100)
    t = _ties(corr)
    return {"corr_by_offset_min": corr, "best_offset_min": _best(corr), "tied_best": t,
            "pass": 0 in t and all(abs(k) <= MAX_TIE_SPAN for k in t)}


def mt5_cross(m1: pd.DataFrame, mt5: pd.DataFrame, scale: float) -> dict:
    """Dukascopy bid vs the broker's bid (MT5 bars are bid), one-minute close changes, at -5..+5 minutes."""
    dk = (m1["bid_c"] / scale).sort_index()
    dk = dk[~dk.index.duplicated()]
    mt = mt5["close"].sort_index()
    mt = mt[~mt.index.duplicated()]
    idx = dk.index.intersection(mt.index)
    if len(idx) < MT5_WEEK_MIN:
        return {"pass": False, "reason": f"only {len(idx)} common minutes"}
    grid = dk.index.union(mt.index)
    d1, d2 = dk.reindex(grid).diff(), mt.reindex(grid).diff()
    corr = {k: _corr(d1.shift(k), d2, 100) for k in MT5_LAGS_MIN}
    wk = _week(grid)
    weeks, bad = {}, []
    for w in sorted(set(wk)):
        m = wk == w
        if int((m & d1.notna().to_numpy() & d2.notna().to_numpy()).sum()) < MT5_WEEK_MIN:
            continue
        c = {k: _corr(d1.shift(k)[m], d2[m], 100) for k in MT5_LAGS_MIN}
        weeks[w] = _ties(c)
        if 0 not in weeks[w]:
            bad.append(w)
    share = len(bad) / len(weeks) if weeks else 0.0
    t = _ties(corr)
    return {"corr_by_lag_min": corr, "best_lag_min": _best(corr), "tied_best": t, "weeks_checked": len(weeks),
            "misaligned_weeks": bad, "pass": 0 in t and all(abs(k) <= MAX_TIE_SPAN for k in t) and share <= MAX_MISALIGNED_WEEKS}


def backwards_share(raw: pd.DataFrame, dext: pd.DataFrame) -> dict:
    n = float(raw["n"].sum())
    back = float(dext["ms_backwards"].sum()) if "ms_backwards" in dext else math.nan
    share = back / n if n else math.nan
    return {"ticks": n, "ms_backwards": back, "share": share, "pass": bool(n) and share <= MAX_BACKWARDS}


def quarantine_weeks(df: pd.DataFrame, weeks: list[str]) -> pd.DataFrame:
    """Bars of the listed ISO weeks become missing; nothing is shifted."""
    if not weeks or not len(df):
        return df
    q = df.copy()
    q.loc[np.isin(_week(pd.DatetimeIndex(q.index)), weeks), :] = np.nan
    return q


def audit(raw: pd.DataFrame, dext: pd.DataFrame, m1: pd.DataFrame, m15: pd.DataFrame, scale: float,
          mt5: pd.DataFrame | None = None) -> dict:
    rep = {"weekly": weekly_lags(raw, m15, scale), "ticks_order": backwards_share(raw, dext)}
    rep["minute"] = minute_offsets(m1, m15, scale) if len(m1) else {"pass": False, "reason": "no one-minute bars"}
    if mt5 is not None:
        rep["mt5"] = mt5_cross(m1, mt5, scale)
    f = []
    if not rep["weekly"]["pass"]:
        f.append(f"{rep['weekly']['misaligned_share']:.1%} of weeks misaligned (> {MAX_MISALIGNED_WEEKS:.0%})")
    if not rep["minute"]["pass"]:
        f.append(f"minute offsets tied best {rep['minute'].get('tied_best')} (0 required, within +-{MAX_TIE_SPAN}) {rep['minute'].get('reason', '')}".strip())
    if not rep["ticks_order"]["pass"]:
        f.append(f"ticks out of order: {rep['ticks_order']['share']}")
    if mt5 is not None and not rep["mt5"]["pass"]:
        f.append(f"MT5 cross-check: best lag {rep['mt5'].get('best_lag_min')} min, {rep['mt5'].get('reason', '')}".strip())
    rep["failures"] = f
    rep["quarantine_weeks"] = rep["weekly"]["misaligned_weeks"] if rep["weekly"]["pass"] else []
    return rep
