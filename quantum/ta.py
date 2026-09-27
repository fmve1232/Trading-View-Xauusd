"""Pine Script v6 technical-analysis primitives, re-implemented on numpy arrays.

Every function takes and returns float64 arrays aligned bar-for-bar with the input, with
NaN standing in for Pine's `na`. The definitions follow the Pine reference implementations
(the `pine_ema` / `pine_rma` / `pine_rsi` / `pine_dmi` forms published by TradingView), so a
value here can be compared one-to-one with the same call on a TradingView chart fed the
same bars.

Known, stated differences (see docs/PLATFORM.md, "Parity"):
  * pivothigh / pivotlow: TradingView does not document how it breaks ties between equal
    highs. Here a pivot must be STRICTLY above (below) every other bar in its window, which
    yields at most one pivot per plateau. Unverified against TradingView on exact ties.
"""
from __future__ import annotations

import math

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

NaN = float("nan")


def epoch_s(idx) -> np.ndarray:
    """Epoch seconds of a DatetimeIndex, whatever its resolution (pandas 3 defaults to us)."""
    return np.asarray(idx.tz_convert("UTC").as_unit("s").asi8 if idx.tz is not None else idx.as_unit("s").asi8, dtype=np.int64)


def arr(x) -> np.ndarray:
    return np.asarray(x, dtype=np.float64)


def pine_round(x: float) -> float:
    """Pine's math.round: ties round half AWAY FROM ZERO (EdgeCases A8-A10), unlike Python's
    banker's rounding."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return NaN
    return math.copysign(math.floor(abs(x) + 0.5), x) + 0.0


def nz(x, fallback=0.0):
    if x is None:
        return fallback
    if isinstance(x, float) and math.isnan(x):
        return fallback
    return x


def isna(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def shift(x: np.ndarray, n: int = 1) -> np.ndarray:
    x = arr(x)
    out = np.full_like(x, np.nan)
    if n == 0:
        return x.copy()
    if n > 0:
        out[n:] = x[:-n]
    else:
        out[:n] = x[-n:]
    return out


def sma(x: np.ndarray, n: int) -> np.ndarray:
    """ta.sma: NaN if any value in the window is NaN (Pine sums the window)."""
    x = arr(x)
    out = np.full_like(x, np.nan)
    if n <= 0 or len(x) < n:
        return out
    w = sliding_window_view(x, n)
    out[n - 1:] = w.mean(axis=1)
    return out


def rolling_sum(x: np.ndarray, n: int) -> np.ndarray:
    x = arr(x)
    out = np.full_like(x, np.nan)
    if len(x) < n:
        return out
    out[n - 1:] = sliding_window_view(x, n).sum(axis=1)
    return out


def _seeded_recursive(x: np.ndarray, n: int, alpha: float) -> np.ndarray:
    """Pine's EMA/RMA recursion: seeded by sma(x, n) whenever the previous value is na."""
    x = arr(x)
    seed = sma(x, n)
    out = np.full_like(x, np.nan)
    prev = np.nan
    for i in range(len(x)):
        if math.isnan(prev):
            v = seed[i]
        else:
            xi = x[i]
            v = alpha * xi + (1.0 - alpha) * prev  # NaN input propagates, as in Pine
        out[i] = v
        prev = v
    return out


def ema(x: np.ndarray, n: int) -> np.ndarray:
    return _seeded_recursive(x, n, 2.0 / (n + 1.0))


def rma(x: np.ndarray, n: int) -> np.ndarray:
    return _seeded_recursive(x, n, 1.0 / n)


def stdev(x: np.ndarray, n: int) -> np.ndarray:
    """ta.stdev with biased=true (population standard deviation), Pine's default."""
    x = arr(x)
    out = np.full_like(x, np.nan)
    if len(x) < n:
        return out
    w = sliding_window_view(x, n)
    out[n - 1:] = w.std(axis=1, ddof=0)
    return out


def variance(x: np.ndarray, n: int) -> np.ndarray:
    x = arr(x)
    out = np.full_like(x, np.nan)
    if len(x) < n:
        return out
    out[n - 1:] = sliding_window_view(x, n).var(axis=1, ddof=0)
    return out


def highest(x: np.ndarray, n: int) -> np.ndarray:
    x = arr(x)
    out = np.full_like(x, np.nan)
    if len(x) < n:
        return out
    out[n - 1:] = sliding_window_view(x, n).max(axis=1)
    return out


def lowest(x: np.ndarray, n: int) -> np.ndarray:
    x = arr(x)
    out = np.full_like(x, np.nan)
    if len(x) < n:
        return out
    out[n - 1:] = sliding_window_view(x, n).min(axis=1)
    return out


def tr(high, low, close, handle_na: bool = True) -> np.ndarray:
    high, low, close = arr(high), arr(low), arr(close)
    pc = shift(close, 1)
    hl = high - low
    out = np.fmax(hl, np.fmax(np.abs(high - pc), np.abs(low - pc)))
    # np.fmax ignores NaN, so where pc is NaN out == hl. Pine's tr(false) is na there.
    if not handle_na:
        out = np.where(np.isnan(pc), np.nan, out)
    return out


def atr(high, low, close, n: int) -> np.ndarray:
    return rma(tr(high, low, close, handle_na=True), n)


def rsi(x: np.ndarray, n: int) -> np.ndarray:
    x = arr(x)
    ch = x - shift(x, 1)
    up = rma(np.where(np.isnan(ch), np.nan, np.maximum(ch, 0.0)), n)
    dn = rma(np.where(np.isnan(ch), np.nan, np.maximum(-ch, 0.0)), n)
    out = np.full_like(x, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = 100.0 - 100.0 / (1.0 + up / dn)
    out = np.where(dn == 0, 100.0, np.where(up == 0, 0.0, rs))
    out = np.where(np.isnan(up) | np.isnan(dn), np.nan, out)
    return out


def fixnan(x: np.ndarray) -> np.ndarray:
    x = arr(x).copy()
    last = np.nan
    for i in range(len(x)):
        if math.isnan(x[i]):
            x[i] = last
        else:
            last = x[i]
    return x


def dmi(high, low, close, di_len: int, adx_len: int):
    """ta.dmi -> (plusDI, minusDI, adx), following Pine's published reference."""
    high, low, close = arr(high), arr(low), arr(close)
    up = high - shift(high, 1)
    down = shift(low, 1) - low
    plus_dm = np.where(np.isnan(up), np.nan, np.where((up > down) & (up > 0), up, 0.0))
    minus_dm = np.where(np.isnan(down), np.nan, np.where((down > up) & (down > 0), down, 0.0))
    trur = rma(tr(high, low, close, handle_na=False), di_len)
    with np.errstate(divide="ignore", invalid="ignore"):
        plus = fixnan(100.0 * rma(plus_dm, di_len) / trur)
        minus = fixnan(100.0 * rma(minus_dm, di_len) / trur)
        s = plus + minus
        adx = 100.0 * rma(np.abs(plus - minus) / np.where(s == 0, 1.0, s), adx_len)
    return plus, minus, adx


def percentrank(x: np.ndarray, n: int) -> np.ndarray:
    """ta.percentrank: % of the previous n values that are <= the current value."""
    x = arr(x)
    out = np.full_like(x, np.nan)
    if len(x) <= n:
        return out
    w = sliding_window_view(x, n + 1)  # window [t-n .. t]
    cur = w[:, -1:]
    prev = w[:, :-1]
    cnt = (prev <= cur).sum(axis=1)
    res = cnt / n * 100.0
    bad = np.isnan(w).any(axis=1)
    res = np.where(bad, np.nan, res)
    out[n:] = res
    return out


def correlation(a: np.ndarray, b: np.ndarray, n: int) -> np.ndarray:
    a, b = arr(a), arr(b)
    out = np.full_like(a, np.nan)
    if len(a) < n:
        return out
    wa = sliding_window_view(a, n)
    wb = sliding_window_view(b, n)
    ma = wa.mean(axis=1)
    mb = wb.mean(axis=1)
    cov = (wa * wb).mean(axis=1) - ma * mb
    va = (wa * wa).mean(axis=1) - ma * ma
    vb = (wb * wb).mean(axis=1) - mb * mb
    with np.errstate(divide="ignore", invalid="ignore"):
        r = cov / np.sqrt(va * vb)
    r = np.where((va <= 0) | (vb <= 0), np.nan, r)
    out[n - 1:] = r
    return out


def roc(x: np.ndarray, n: int) -> np.ndarray:
    x = arr(x)
    p = shift(x, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        return 100.0 * (x - p) / p


def pivothigh(src: np.ndarray, left: int, right: int) -> np.ndarray:
    """Value at the pivot bar, reported on the bar `right` bars later (as Pine does)."""
    src = arr(src)
    n = len(src)
    out = np.full(n, np.nan)
    width = left + right + 1
    if n < width:
        return out
    w = sliding_window_view(src, width)
    c = w[:, left]
    others = np.delete(w, left, axis=1)
    ok = (c[:, None] > others).all(axis=1) & ~np.isnan(w).any(axis=1)
    out[width - 1:] = np.where(ok, c, np.nan)
    return out


def pivotlow(src: np.ndarray, left: int, right: int) -> np.ndarray:
    src = arr(src)
    n = len(src)
    out = np.full(n, np.nan)
    width = left + right + 1
    if n < width:
        return out
    w = sliding_window_view(src, width)
    c = w[:, left]
    others = np.delete(w, left, axis=1)
    ok = (c[:, None] < others).all(axis=1) & ~np.isnan(w).any(axis=1)
    out[width - 1:] = np.where(ok, c, np.nan)
    return out


def anchored_vwap(src: np.ndarray, volume: np.ndarray, new_anchor: np.ndarray) -> np.ndarray:
    """ta.vwap(src, anchor): cumulative since the last bar where new_anchor is true."""
    src, volume = arr(src), arr(volume)
    out = np.full_like(src, np.nan)
    pv = vv = ps = 0.0
    k = 0
    for i in range(len(src)):
        if new_anchor[i] or i == 0:
            pv = vv = ps = 0.0
            k = 0
        v = volume[i]
        s = src[i]
        if not math.isnan(s):
            ps += s
            k += 1
            if not math.isnan(v):
                pv += s * v
                vv += v
        # D-07 addendum: while an anchor period has no volume yet (spot bars during the COMEX
        # daily break), use the equal-weighted mean price instead of na. A na VWAP made
        # mrComposite na, which disables the analog scan for the next 100 bars (every day on 1h).
        out[i] = pv / vv if vv > 0 else (ps / k if k > 0 else np.nan)
    return out
