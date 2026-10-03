"""The operator's own MT5 broker feed, read in the cloud through MetaApi -- DISPLAY AND VALIDATION ONLY.

No PC is involved: MetaApi (metaapi.cloud; billed per account-hour, about USD 9 a month as
quoted on 3 Oct 2026, so it is OPTIONAL and the site hides the panel unless connected) keeps the MT5
account connected on its servers, and this module reads it over REST on every pipeline run.
Connect the account with the MT5 INVESTOR (read-only) password, so nothing here can trade.

What it publishes (`site/data/mt5.json`) and stores (`<store>/MT5_<symbol>_<tf>/`):
  * the broker's latest tick: bid, ask, spread, time in epoch ns with the precision it carries;
  * the broker's 5m / 15m / 1h candles with TICK volume (the count of price changes; spot gold
    has no central exchange, so no source has its traded volume);
  * the same-bar difference between the broker's closes and the engine's (Twelve Data);
  * a footprint of the latest ticks per price level. If the broker sends deal side and volume
    (exchange instruments), it is a real buy/sell footprint; otherwise each tick is classed by
    the tick rule (up-tick = buy, down-tick = sell) and the result is labelled a PROXY.

It never changes a price the engine uses: it is outside `holdout.ENGINE_SOURCES`, the pipeline
does not import it, and the workflow runs it as a separate, non-fatal step. Secrets:
METAAPI_TOKEN and METAAPI_ACCOUNT_ID; variable MT5_SYMBOL (default XAUUSD). The token is sent
only in the `auth-token` header and is scrubbed from every message this module writes.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests

from .reference import classify, parse_ts_ns

PROVISIONING = "https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai"
TIMEFRAMES = {"5m": 300, "15m": 900, "1h": 3600}
TIMEOUT = 25
FOOTPRINT_TICKS = 1000          # one request (the API's maximum page)


class MetaApi:
    def __init__(self, token: str, account: str, get=requests.get):
        self.token, self.account, self._get = token, account, get
        self.calls = 0

    def _req(self, url: str, params: dict | None = None):
        self.calls += 1
        r = self._get(url, headers={"auth-token": self.token}, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()

    def scrub(self, msg: str) -> str:
        return msg.replace(self.token, "***") if self.token else msg

    def account_info(self) -> dict:
        return self._req(f"{PROVISIONING}/users/current/accounts/{self.account}")

    def domain(self) -> str:
        return self._req(f"{PROVISIONING}/users/current/servers/mt-client-api").get("domain", "agiliumtrade.ai")

    def market_host(self, region: str, domain: str) -> str:
        return f"https://mt-market-data-client-api-v1.{region}.{domain}"

    def candles(self, host: str, symbol: str, tf: str, limit: int = 1000) -> list:
        return self._req(f"{host}/users/current/accounts/{self.account}/historical-market-data/symbols/{quote(symbol)}"
                         f"/timeframes/{tf}/candles", {"limit": limit}) or []

    def ticks(self, host: str, symbol: str, limit: int = FOOTPRINT_TICKS) -> list:
        return self._req(f"{host}/users/current/accounts/{self.account}/historical-market-data/symbols/{quote(symbol)}"
                         f"/ticks", {"limit": limit}) or []


def candles_frame(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "spread"])
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["time"], utc=True)
    df.index.name = "datetime"
    out = df[["open", "high", "low", "close"]].astype(float)
    out["volume"] = pd.to_numeric(df.get("tickVolume"), errors="coerce")       # TICK volume, labelled as such
    out["spread"] = pd.to_numeric(df.get("spread"), errors="coerce")           # in points, as MT5 reports it
    return out[~out.index.duplicated(keep="last")].sort_index()


def footprint(ticks: list, step: float = 0.5) -> dict:
    """Ticks per price level. Real buy/sell when the feed carries deal side and volume,
    otherwise the tick rule on the mid (or last) price, labelled PROXY."""
    rows = []
    for t in ticks:
        px = t.get("last") or (((t.get("bid") or 0) + (t.get("ask") or 0)) / 2 if t.get("bid") and t.get("ask") else None)
        ns, _ = parse_ts_ns(t.get("time"))
        if px and ns:
            rows.append((ns, float(px), t.get("side"), float(t.get("volume") or 0.0)))
    if len(rows) < 2:
        return {"n": len(rows), "levels": [], "method": "UNAVAILABLE"}
    rows.sort(key=lambda r: r[0])
    real = sum(1 for r in rows if r[2] in ("buy", "sell") and r[3] > 0) >= 0.8 * len(rows)
    lv: dict = {}
    prev = rows[0][1]
    last_dir = 0
    for _, px, side, vol in rows[1:]:
        if real:
            d, w = (1 if side == "buy" else -1), vol
        else:
            d = 1 if px > prev else -1 if px < prev else last_dir     # zero tick keeps the last direction
            w = 1.0
        last_dir, prev = d, px
        if d == 0:
            continue
        k = round(math.floor(px / step) * step, 2)
        b = lv.setdefault(k, [0.0, 0.0])
        b[0 if d > 0 else 1] += w
    levels = [{"price": k, "buy": round(v[0], 2), "sell": round(v[1], 2), "delta": round(v[0] - v[1], 2)}
              for k, v in sorted(lv.items(), reverse=True)]
    tot_b, tot_s = sum(x["buy"] for x in levels), sum(x["sell"] for x in levels)
    return {"n": len(rows), "from_ns": rows[0][0], "to_ns": rows[-1][0], "step": step, "levels": levels,
            "buy": round(tot_b, 2), "sell": round(tot_s, 2), "delta": round(tot_b - tot_s, 2),
            "poc": max(levels, key=lambda x: x["buy"] + x["sell"])["price"] if levels else None,
            "method": "DEAL_SIDE_VOLUME" if real else "TICK_RULE_PROXY"}


def compare(primary: dict, mt5: pd.DataFrame, bar_sec: int) -> dict:
    """Same-bar closes: the engine's feed vs the broker's. Robust statistics, fixed bands."""
    if mt5 is None or mt5.empty or not primary.get("t"):
        return {"n": 0, "status": "UNAVAILABLE"}
    m = {int(ts.timestamp()): c for ts, c in mt5["close"].items()}
    pairs = [(t, c, m[t]) for t, c in zip(primary["t"], primary["c"]) if t in m and c is not None]
    if not pairs:
        return {"n": 0, "status": "UNAVAILABLE", "note": "no common bars (broker bars may be on a different grid)"}
    d = np.array([c - b for _, c, b in pairs])
    med = float(np.median(d))
    mad = float(np.median(np.abs(d - med))) * 1.4826
    t, c, b = pairs[-1]
    pct = (c - b) / b * 100
    return {"n": len(pairs), "bar_sec": bar_sec, "last_bar_open_s": int(t), "primary_close": c, "mt5_close": b,
            "diff": round(c - b, 3), "diff_pct": round(pct, 4), "status": classify(pct),
            "median_diff": round(med, 3), "mad_diff": round(mad, 3),
            "p95_abs_diff": round(float(np.percentile(np.abs(d), 95)), 3), "max_abs_diff": round(float(np.max(np.abs(d))), 3)}


def build(api: MetaApi | None, symbol: str, primary: dict | None = None, store_dir: str | None = None) -> dict:
    gen = time.time_ns()
    out = {"generated_ts_ns": gen, "symbol": symbol, "status": "UNAVAILABLE", "note": "", "broker": None,
           "tick": None, "candles": {}, "vs_primary": {}, "footprint": None,
           "volume_kind": "TICK_VOLUME (count of price changes; not traded volume)",
           "note_display": "Display and validation only. The engine never reads this file."}
    if api is None:
        out["note"] = "METAAPI_TOKEN / METAAPI_ACCOUNT_ID not set (optional, paid MetaApi service)"
        return out
    try:
        acc = api.account_info()
        out["broker"] = {k: acc.get(k) for k in ("name", "server", "platform", "region", "state", "connectionStatus", "type")}
        if acc.get("state") != "DEPLOYED" or acc.get("connectionStatus") != "CONNECTED":
            out["status"] = "DISCONNECTED"
            out["note"] = f"account state {acc.get('state')}, connection {acc.get('connectionStatus')} (deploy it in the MetaApi dashboard)"
            return out
        host = api.market_host(acc.get("region") or "new-york", api.domain())
        frames = {}
        for tf, sec in TIMEFRAMES.items():
            df = candles_frame(api.candles(host, symbol, tf))
            frames[tf] = df
            if not df.empty:
                last = df.iloc[-1]
                out["candles"][tf] = {"n": len(df), "last_open": df.index[-1].isoformat(), "o": last["open"], "h": last["high"],
                                      "l": last["low"], "c": last["close"], "tick_volume": None if pd.isna(last["volume"]) else float(last["volume"]),
                                      "tick_volume_median": None if df["volume"].isna().all() else float(df["volume"].tail(100).median())}
                if store_dir:
                    from .data import store                   # write only; the engine never loads MT5_* series
                    store.save(store_dir, f"MT5_{symbol}_{tf}", store.merge(store.load(store_dir, f"MT5_{symbol}_{tf}"), df))
        if primary:
            for tf, sec in TIMEFRAMES.items():
                if tf in primary:
                    out["vs_primary"][tf] = compare(primary[tf], frames.get(tf), sec)
        ticks = api.ticks(host, symbol)
        recv = time.time_ns()
        if ticks:
            lt = max(ticks, key=lambda t: parse_ts_ns(t.get("time"))[0] or 0)      # pages may come newest-first
            ns, prec = parse_ts_ns(lt.get("time"))
            bid, ask = lt.get("bid"), lt.get("ask")
            out["tick"] = {"bid": bid, "ask": ask, "spread": round(ask - bid, 5) if bid and ask else None,
                           "mid": (bid + ask) / 2 if bid and ask else lt.get("last"), "source_ts_ns": ns, "received_ts_ns": recv,
                           "timestamp_precision": prec, "broker_time": lt.get("brokerTime"),
                           "age_s": round((recv - ns) / 1e9, 1) if ns else None,
                           "quality": "CROSSED" if bid and ask and ask < bid else "VALID"}
            out["footprint"] = footprint(ticks)
        out["status"] = "OK"
    except Exception as e:  # noqa: BLE001 - reported, never swallowed
        out["status"] = "ERROR"
        out["note"] = api.scrub(str(e))[:240]
    out["api_calls"] = api.calls
    out["processed_ts_ns"] = time.time_ns()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--store", default="")
    ap.add_argument("--data", default="site/data", help="the pipeline's payloads, for the same-bar comparison")
    a = ap.parse_args()
    tok, acc = os.environ.get("METAAPI_TOKEN", "").strip(), os.environ.get("METAAPI_ACCOUNT_ID", "").strip()
    symbol = os.environ.get("MT5_SYMBOL", "").strip() or "XAUUSD"
    primary = {}
    for tf in TIMEFRAMES:
        p = os.path.join(a.data, f"{tf}.json")
        if os.path.exists(p):
            with open(p) as f:
                ch = json.load(f).get("chart", {})
            primary[tf] = {"t": ch.get("t"), "c": ch.get("c")}
    out = build(MetaApi(tok, acc) if tok and acc else None, symbol, primary, a.store or None)
    with open(a.out, "w") as f:
        json.dump(out, f, separators=(",", ":"), default=float)
    print(f"mt5 {symbol}: {out['status']} {out['note']} tick={out['tick'] and out['tick'].get('mid')} calls={out.get('api_calls')}")
    for tf, v in out["vs_primary"].items():
        print(f"  vs primary {tf}: n={v.get('n')} diff={v.get('diff')} {v.get('status')}")


if __name__ == "__main__":
    main()
