"""Macro panel for the site: DXY, EUR/USD, JPY/USD, the US 10-year yield, WTI oil and Bitcoin beside gold.
DISPLAY ONLY: outside `holdout.ENGINE_SOURCES`; the engine never reads `site/data/macro_panel.json`.

For each instrument: the last price, the 24-hour change, a 15-minute sparkline (last 2 days), the
correlation of its 15-minute returns with gold's over the same bars, and what its move implies for gold:
  * the sign of the measured correlation when it is clear (|r| >= 0.2), otherwise
  * the textbook relation (DXY and yields up = gold down; EUR/USD, JPY/USD (a stronger yen) and oil up = gold up),
    labelled as such. Bitcoin has no established relation (textbook 0): only a clear measured r colours it.
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
SPARK_BARS = 192          # 2 days of 15-minute bars
CORR_BARS = 96            # 1 day of 15-minute returns
CORR_CLEAR = 0.2


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


def build(chart_path: str, fetch=sources.yahoo) -> dict:
    gold = _gold(chart_path)
    items = []
    for key, label, sym, tb, unit, dec in INSTRUMENTS:
        try:
            df = fetch(sym, "15m", "5d")
            items.append(item(key, label, sym, tb, unit, dec, df, gold))
        except Exception as e:  # noqa: BLE001 - reported per instrument
            items.append(item(key, label, sym, tb, unit, dec, None, gold, sources.redact(f"{type(e).__name__}: {e}")[:160]))
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
