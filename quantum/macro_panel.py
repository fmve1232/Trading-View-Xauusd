"""Macro panel for the site: DXY, EUR/USD, JPY/USD, the US 10-year yield, WTI oil and Bitcoin beside gold, plus the
daily real 10Y yield, 10Y breakeven and US 2Y yield (FRED).
DISPLAY ONLY: outside `holdout.ENGINE_SOURCES`; the engine never reads `site/data/macro_panel.json`.

For each instrument: the last price, the 24-hour change, a 15-minute sparkline (last 2 days), the
correlation of its 15-minute returns with gold's over the same bars, and what its move implies for gold:
  * the sign of the measured correlation when it is clear (|r| >= 0.2), otherwise
  * the textbook relation (DXY and yields up = gold down; EUR/USD, JPY/USD (a stronger yen) and oil up = gold up),
    labelled as such. Bitcoin has no established relation (textbook 0): only a clear measured r colours it.
Live US 10Y yield: no free feed streams the yield, only the 10-year T-note price (the relay's OANDA:USB10Y_USD).
`bridge` measures the yield's change per point of T-note price (Yahoo ZN=F futures vs ^TNX, 15-minute changes,
last 5 days); the site shows yield = ^TNX at the last completed bar + beta x the T-note's move since then.
Gold is the engine's own 15-minute series (`site/data/15m.json`), so both sides share a clock.
A failed source is reported per instrument and never fails the run.
"""
from __future__ import annotations

import argparse
import json
import math
import time

import numpy as np
import pandas as pd

from .data import sources

INSTRUMENTS = [   # key, label, Yahoo symbol, textbook sign of its move for gold, unit, decimals
    ("DXY", "US Dollar Index", "DX-Y.NYB", -1, "", 2),
    ("EURUSD", "EUR / USD", "EURUSD=X", +1, "", 5),   # a stronger euro = a weaker dollar (57.6% of the DXY)
    ("JPYUSD", "JPY / USD", "JPYUSD=X", +1, "", 6),   # the yen in dollars (1 / USDJPY): a stronger yen
    ("US10Y", "US 10Y yield", "^TNX", -1, "%", 3),
    ("WTI", "WTI crude oil", "CL=F", +1, "$", 2),
    ("BTC", "Bitcoin", "BTC-USD", 0, "$", 0),         # no established relation with gold: measured r only
]
# Pine v65 "five gold drivers" (Amendment 9 section 3): the three DAILY ones, from FRED (no key). Direction as Pine reads
# them: the last observation vs its EMA10 / EMA20 ("rising" = last > EMA10 > EMA20); no intraday correlation.
DAILY = [   # key, label, FRED id, textbook sign of a RISE for gold, unit, decimals
    ("REALYLD", "Real 10Y yield", "DFII10", -1, "%", 2),
    ("BREAKEVEN", "10Y breakeven", "T10YIE", +1, "%", 2),
    ("US2Y", "US 2Y yield", "DGS2", -1, "%", 2),
]
DAILY_SPARK = 60          # observations (about 3 months)
SPARK_BARS = 192          # 2 days of 15-minute bars
CORR_BARS = 96            # 1 day of 15-minute returns
CORR_CLEAR = 0.2
LIVE_PROXY = {"US10Y": "ZN=F"}   # 10-year T-note futures: the price the live yield estimate moves with
BRIDGE_BARS = 480                # 5 days of 15-minute changes
BRIDGE_ROLL = 1.0                # a T-note move above 1 point in 15 minutes is a contract roll, not a trade
BRIDGE_BETA = (-0.30, -0.03)     # plausible yield-% per T-note point (duration about 6-8); outside it, no estimate
BRIDGE_R2 = 0.5


def _gold(chart_path: str) -> pd.Series | None:
    try:
        with open(chart_path) as f:
            ch = json.load(f)["chart"]
        return pd.Series(ch["c"], index=pd.to_datetime(ch["t"], unit="s", utc=True), dtype=float).dropna()
    except Exception:  # noqa: BLE001
        return None


def correlation(a: pd.Series, b: pd.Series, n: int = CORR_BARS) -> tuple[float | None, int]:
    """Pearson correlation of simple returns on the bars both series have (inner join), last n."""
    j = pd.concat([a, b], axis=1, join="inner").dropna()
    r = j.pct_change().dropna().tail(n)
    if len(r) < 20 or r.iloc[:, 0].std() == 0 or r.iloc[:, 1].std() == 0:
        return None, len(r)
    return float(np.corrcoef(r.iloc[:, 0], r.iloc[:, 1])[0, 1]), len(r)


def bridge(yld: pd.Series, price: pd.Series) -> dict:
    """OLS slope of the yield's 15-minute changes on the T-note price's, on shared bars; rolls dropped."""
    j = pd.concat([yld, price], axis=1, join="inner").dropna()
    d = j.diff().dropna()
    d = d[d.iloc[:, 1].abs() <= BRIDGE_ROLL].tail(BRIDGE_BARS)
    if len(d) < 40 or d.iloc[:, 1].var() == 0 or d.iloc[:, 0].var() == 0:
        return {"ok": False, "n": int(len(d)), "why": "too few shared bars"}
    dy, dp = d.iloc[:, 0].to_numpy(), d.iloc[:, 1].to_numpy()
    beta = float(np.cov(dy, dp)[0, 1] / np.var(dp, ddof=1))
    r2 = float(np.corrcoef(dy, dp)[0, 1] ** 2)
    out = {"ok": BRIDGE_BETA[0] <= beta <= BRIDGE_BETA[1] and r2 >= BRIDGE_R2, "beta": round(beta, 5), "r2": round(r2, 3),
           "n": int(len(d)), "proxy_last": round(float(price.dropna().iloc[-1]), 4)}
    if not out["ok"]:
        out["why"] = "fit outside its plausible range"
    return out


def implication(change: float | None, corr: float | None, textbook: int) -> dict:
    """+1 = the move supports gold up (green), -1 = supports gold down (red), 0 = flat / unknown."""
    if change is None or not math.isfinite(change) or change == 0:
        return {"gold": 0, "basis": "flat"}
    if corr is not None and abs(corr) >= CORR_CLEAR:
        return {"gold": int(np.sign(change) * np.sign(corr)), "basis": f"measured r {corr:+.2f}"}
    if not textbook:
        return {"gold": 0, "basis": "no established relation (measured r weak)"}
    return {"gold": int(np.sign(change) * textbook), "basis": "textbook relation (measured r weak)"}


def item(key, label, sym, textbook, unit, dec, df: pd.DataFrame | None, gold: pd.Series | None, err: str = "") -> dict:
    out = {"key": key, "label": label, "symbol": sym, "unit": unit, "dec": dec, "textbook": textbook, "ok": False, "note": err}
    if df is None or df.empty:
        return out
    c = df["close"].astype(float).dropna()
    last_t = c.index[-1]
    prev = c[c.index <= last_t - pd.Timedelta(hours=24)]
    ref = float(prev.iloc[-1]) if len(prev) else float(c.iloc[0])
    chg = float(c.iloc[-1]) - ref
    corr, nret = correlation(c, gold) if gold is not None else (None, 0)
    sp = c.tail(SPARK_BARS)
    dg = max(4, dec + 2)          # keep the instrument's precision (JPY/USD is about 0.0065)
    gs = gold.reindex(sp.index, method="ffill") if gold is not None else None
    out.update(ok=True, last=round(float(c.iloc[-1]), dg), t=int(last_t.timestamp()), ref=round(ref, dg), change=round(chg, dg),
               change_pct=round(chg / ref * 100, 3) if ref else None, corr=None if corr is None else round(corr, 3), corr_n=nret,
               spark={"t": [int(x.timestamp()) for x in sp.index], "v": [round(float(v), dg) for v in sp.values],
                      "gold": None if gs is None else [None if not math.isfinite(v) else round(float(v), 2) for v in gs.values]},
               **implication(chg, corr, textbook))
    return out


def live_bridge(df: pd.DataFrame, proxy: str, fetch) -> dict:
    """The live estimate's inputs: the measured slope and the anchor (the last COMPLETED 15-minute bar)."""
    try:
        c = df["close"].astype(float).dropna()
        out = bridge(c, fetch(proxy, "15m", "5d")["close"].astype(float))
        if len(c) >= 2:   # Yahoo's last bar may still be forming; its predecessor closed at its start + 15 minutes
            out.update(anchor_t=int(c.index[-2].timestamp()) + 900, anchor_v=round(float(c.iloc[-2]), 5))
        else:
            out["ok"] = False
        return out
    except Exception as e:  # noqa: BLE001 - the box falls back to the direction only
        return {"ok": False, "why": sources.redact(f"{type(e).__name__}: {e}")[:120]}


def ema(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(span=n, adjust=False).mean()


def daily_item(key, label, sid, textbook, unit, dec, s: pd.Series | None, err: str = "") -> dict:
    out = {"key": key, "label": label, "symbol": "FRED:" + sid, "unit": unit, "dec": dec, "textbook": textbook, "ok": False,
           "daily": True, "note": err}
    if s is None or len(s.dropna()) < 25:
        out["note"] = out["note"] or "not enough observations"
        return out
    s = s.dropna().astype(float)
    e10, e20 = ema(s, 10), ema(s, 20)
    last, f10, f20 = float(s.iloc[-1]), float(e10.iloc[-1]), float(e20.iloc[-1])
    trend = 1 if last > f10 > f20 else -1 if last < f10 < f20 else 0
    ref = float(s.iloc[-2])
    sp = s.tail(DAILY_SPARK)
    out.update(ok=True, last=round(last, 4), t=int(s.index[-1].timestamp()), ref=round(ref, 4), change=round(last - ref, 4),
               change_pct=round((last - ref) / ref * 100, 3) if ref else None, corr=None, corr_n=0, trend=trend,
               ema10=round(f10, 4), ema20=round(f20, 4),
               spark={"t": [int(x.timestamp()) for x in sp.index], "v": [round(float(v), 4) for v in sp.values], "gold": None},
               gold=int(trend * textbook), basis="daily trend (last vs EMA10 / EMA20), textbook relation")
    return out


def build(chart_path: str, fetch=sources.yahoo, fetch_daily=sources.fred) -> dict:
    gold = _gold(chart_path)
    items = []
    for key, label, sym, tb, unit, dec in INSTRUMENTS:
        try:
            df = fetch(sym, "15m", "5d")
            it = item(key, label, sym, tb, unit, dec, df, gold)
            if key in LIVE_PROXY and it["ok"]:
                it["live"] = live_bridge(df, LIVE_PROXY[key], fetch)
            items.append(it)
        except Exception as e:  # noqa: BLE001 - reported per instrument
            items.append(item(key, label, sym, tb, unit, dec, None, gold, sources.redact(f"{type(e).__name__}: {e}")[:160]))
    for key, label, sid, tb, unit, dec in DAILY:
        try:
            items.append(daily_item(key, label, sid, tb, unit, dec, fetch_daily(sid)))
        except Exception as e:  # noqa: BLE001 - reported per instrument
            items.append(daily_item(key, label, sid, tb, unit, dec, None, sources.redact(f"{type(e).__name__}: {e}")[:160]))
    return {"generated_ts": int(time.time()), "gold_bars": 0 if gold is None else int(len(gold)), "items": items,
            "note": "Display only. 15-minute bars from Yahoo; correlations of 15-minute returns with the engine's gold series over the last day."}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--chart", default="site/data/15m.json")
    a = ap.parse_args()
    out = build(a.chart)
    with open(a.out, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    for it in out["items"]:
        print(f"{it['key']}: {'ok' if it['ok'] else 'FAIL ' + it['note']} last={it.get('last')} r={it.get('corr')} gold={it.get('gold')}")


if __name__ == "__main__":
    main()
