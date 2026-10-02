"""Independent reference prices for XAU/USD -- DISPLAY AND VALIDATION ONLY.

The engine prices every bar from Twelve Data. This module asks other providers for the same
instrument, so the dashboard can show whether the primary feed agrees with them. It never
changes a price the engine uses: it is outside `holdout.ENGINE_SOURCES`, the pipeline does not
import it, and the workflow runs it as a separate, non-fatal step.

Providers (each one fails on its own and says why; nothing is ever filled in):
  * OANDA v20, practice account (free). Needs the secret OANDA_API_TOKEN; OANDA_ENV=live
    switches to a live account. Gives bid/ask candles (`price=BA`) and a pricing snapshot.
  * gold-api.com (free, no key). A mid price only.

Every observation carries four timestamps as integer epoch nanoseconds -- source (as the
provider stated it), received (this runner's clock when the response arrived), processed and
published -- plus `timestamp_precision`, which is what the SOURCE gave (second, millisecond,
...). Digits are never padded to claim more precision. The runner's clock offset is estimated
from the HTTP `Date` header (one-second resolution) and reported beside the latency.

Divergence thresholds (fixed a priori for display, not fitted to any data; the engine never
reads them): |difference| < 0.03% CONSISTENT, < 0.10% MINOR, < 1% SIGNIFICANT, otherwise
CRITICAL. Spot feeds normally differ by cents to about a dollar (0.00-0.03% near $4,300); a
CRITICAL reading means one feed is wrong (the "2707 vs 4373" class of error) and both raw values
are shown -- neither is replaced.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime
from email.utils import parsedate_to_datetime

import numpy as np
import requests

INSTRUMENT = "XAU_USD"
OANDA_HOST = {"practice": "https://api-fxpractice.oanda.com", "live": "https://api-fxtrade.oanda.com"}
GOLDAPI_URL = "https://api.gold-api.com/price/XAU"
TIMEOUT = 20
DIVERGENCE_BANDS = ((0.03, "CONSISTENT"), (0.10, "MINOR_DIVERGENCE"), (1.0, "SIGNIFICANT_DIVERGENCE"))
PRECISION = {0: "SECOND", 3: "MILLISECOND", 6: "MICROSECOND", 9: "NANOSECOND"}
_RFC3339 = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})$")


def parse_ts_ns(s: str) -> tuple[int | None, str]:
    """RFC 3339 time -> (exact epoch ns, precision the source string carries). No float rounding."""
    m = _RFC3339.match(str(s or "").strip())
    if not m:
        return None, "UNKNOWN"
    base, frac, tz = m.groups()
    sec = int(datetime.fromisoformat(base + ("+00:00" if tz == "Z" else tz)).timestamp())
    frac = frac or ""
    ns = sec * 1_000_000_000 + (int(frac.ljust(9, "0")) if frac else 0)
    # zeros a provider pads on (OANDA candles: ".000000000") are not precision: count the
    # significant digits, so a padded time is reported at the precision it actually carries
    digits = len(frac.rstrip("0"))
    prec = PRECISION.get(digits) or PRECISION[min((k for k in PRECISION if k >= digits), default=9)]
    return ns, prec


def classify(pct: float | None) -> str:
    if pct is None or not np.isfinite(pct):
        return "UNAVAILABLE"
    for lim, name in DIVERGENCE_BANDS:
        if abs(pct) < lim:
            return name
    return "CRITICAL_DIVERGENCE"


def _scrub(msg: str, secret: str) -> str:
    return msg.replace(secret, "***") if secret else msg


def _get(url: str, headers: dict | None = None, params: dict | None = None):
    r = requests.get(url, headers=headers or {}, params=params, timeout=TIMEOUT)
    recv = time.time_ns()
    r.raise_for_status()
    clock = None
    if r.headers.get("Date"):
        try:
            clock = recv - int(parsedate_to_datetime(r.headers["Date"]).timestamp()) * 1_000_000_000
        except (TypeError, ValueError):
            clock = None
    return r.json(), recv, clock


def _obs(provider: str, market_type: str, **kw) -> dict:
    o = dict(provider_id=provider, instrument_id="XAUUSD", symbol=INSTRUMENT, market_type=market_type,
             currency="USD", unit="troy ounce", bid=None, ask=None, mid=None, spread=None, tradeable=None,
             source_ts_ns=None, received_ts_ns=None, processed_ts_ns=None, timestamp_precision="UNKNOWN",
             latency_ms=None, clock_offset_ms=None, status="UNAVAILABLE", quality="UNAVAILABLE", note="")
    o.update(kw)
    return o


def _finish(o: dict, clock_ns: int | None) -> dict:
    o["processed_ts_ns"] = time.time_ns()
    if o["source_ts_ns"] is not None and o["received_ts_ns"] is not None:
        o["latency_ms"] = round((o["received_ts_ns"] - o["source_ts_ns"]) / 1e6, 1)
    if clock_ns is not None:
        o["clock_offset_ms"] = round(clock_ns / 1e6)   # Date header has 1 s resolution: +-1000 ms
    q = "VALID"
    if o["bid"] is not None and o["ask"] is not None and o["ask"] < o["bid"]:
        q = "CROSSED"
    if o["mid"] is not None and o["mid"] <= 0:
        q = "INVALID"
    o["quality"] = q
    return o


# ----------------------------------------------------------------------------- OANDA
def oanda(token: str, env: str = "practice", account: str = "", candles: int = 300) -> tuple[dict, dict]:
    """Pricing snapshot + H1 bid/ask candles. Returns (observation, {bar_open_s: (bid_c, ask_c)})."""
    host = OANDA_HOST.get(env, OANDA_HOST["practice"])
    pid = f"oanda-{env}"
    if not token:
        return _obs(pid, "BROKER_REFERENCE", note="OANDA_API_TOKEN not set (free practice account)"), {}
    hd = {"Authorization": f"Bearer {token}", "Accept-Datetime-Format": "RFC3339"}
    bars: dict = {}
    try:
        j, _, _ = _get(f"{host}/v3/instruments/{INSTRUMENT}/candles", hd,
                       {"price": "BA", "granularity": "H1", "count": candles})
        for k in j.get("candles", []):
            if not k.get("complete"):
                continue
            ns, _ = parse_ts_ns(k.get("time"))
            if ns is not None and "bid" in k and "ask" in k:
                bars[ns // 1_000_000_000] = (float(k["bid"]["c"]), float(k["ask"]["c"]))
        if not account:
            acc, _, _ = _get(f"{host}/v3/accounts", hd)
            account = (acc.get("accounts") or [{}])[0].get("id", "")
        if not account:
            return _obs(pid, "BROKER_REFERENCE", status="ERROR", note="no account on this token"), bars
        j, recv, clock = _get(f"{host}/v3/accounts/{account}/pricing", hd, {"instruments": INSTRUMENT})
        p = (j.get("prices") or [{}])[0]
        bid = float(p["bids"][0]["price"]) if p.get("bids") else None
        ask = float(p["asks"][0]["price"]) if p.get("asks") else None
        ns, prec = parse_ts_ns(p.get("time"))
        o = _obs(pid, "BROKER_REFERENCE", bid=bid, ask=ask,
                 mid=(bid + ask) / 2 if bid is not None and ask is not None else None,
                 spread=round(ask - bid, 5) if bid is not None and ask is not None else None,
                 tradeable=bool(p.get("tradeable")), source_ts_ns=ns, received_ts_ns=recv,
                 timestamp_precision=prec, status="LIVE" if p.get("tradeable") else "MARKET_CLOSED")
        return _finish(o, clock), bars
    except Exception as e:  # noqa: BLE001 - reported, never swallowed
        return _obs(pid, "BROKER_REFERENCE", status="ERROR", note=_scrub(str(e), token)[:200]), bars


# ----------------------------------------------------------------------------- gold-api
def goldapi() -> dict:
    try:
        j, recv, clock = _get(GOLDAPI_URL)
        px = float(j.get("price"))
        ns, prec = parse_ts_ns(j.get("updatedAt"))
        o = _obs("gold-api", "AGGREGATED_REFERENCE", symbol="XAU", mid=px, source_ts_ns=ns, received_ts_ns=recv,
                 timestamp_precision=prec, status="LIVE", note="mid only; no bid/ask")
        return _finish(o, clock)
    except Exception as e:  # noqa: BLE001
        return _obs("gold-api", "AGGREGATED_REFERENCE", symbol="XAU", status="ERROR", note=str(e)[:200])


# ----------------------------------------------------------------------------- comparison
def compare_bars(primary: dict, ref_bars: dict) -> dict:
    """Same-bar comparison of the engine's 1h closes with a reference's 1h mid closes.
    Robust statistics (median, MAD) so one bad bar cannot hide or fake a divergence."""
    t, c = primary.get("t") or [], primary.get("c") or []
    pairs = [(ts, cl, ref_bars[ts]) for ts, cl in zip(t, c) if ts in ref_bars and cl is not None]
    if not pairs:
        return {"n": 0, "status": "UNAVAILABLE"}
    d = np.array([cl - (b + a) / 2 for _, cl, (b, a) in pairs])
    spread = np.array([a - b for _, _, (b, a) in pairs])
    med = float(np.median(d))
    mad = float(np.median(np.abs(d - med))) * 1.4826
    last_ts, last_c, (lb, la) = pairs[-1]
    last_mid = (lb + la) / 2
    pct = (last_c - last_mid) / last_mid * 100
    return {"n": len(pairs), "last_bar_open_s": int(last_ts), "primary_close": last_c, "reference_mid_close": round(last_mid, 3),
            "diff": round(last_c - last_mid, 3), "diff_pct": round(pct, 4), "status": classify(pct),
            "robust_z": round((d[-1] - med) / mad, 2) if mad > 0 else None,
            "median_diff": round(med, 3), "mad_diff": round(mad, 3), "p95_abs_diff": round(float(np.percentile(np.abs(d), 95)), 3),
            "max_abs_diff": round(float(np.max(np.abs(d))), 3),
            "spread_median": round(float(np.median(spread)), 3), "spread_p90": round(float(np.percentile(spread, 90)), 3),
            "inside_spread_pct": round(float(np.mean(np.abs(d) <= spread / 2) * 100), 1)}


def build(primary_chart: dict | None, token: str = "", env: str = "practice", account: str = "",
          price_source: str = "") -> dict:
    gen = time.time_ns()
    obs_oanda, bars = oanda(token, env, account)
    obs = [obs_oanda, goldapi()]
    live = [o for o in obs if o["mid"] is not None and o["quality"] == "VALID"]
    snap = None
    if len(live) >= 2:
        a, b = live[0], live[1]
        pct = (b["mid"] - a["mid"]) / a["mid"] * 100
        snap = {"a": a["provider_id"], "b": b["provider_id"], "diff": round(b["mid"] - a["mid"], 3), "diff_pct": round(pct, 4),
                "status": classify(pct),
                "source_time_gap_ms": round((b["source_ts_ns"] - a["source_ts_ns"]) / 1e6) if a["source_ts_ns"] and b["source_ts_ns"] else None}
    bar_cmp = compare_bars(primary_chart or {}, bars) if bars else {"n": 0, "status": "UNAVAILABLE",
                                                                     "note": obs_oanda["note"] or "no reference bars"}
    pub = time.time_ns()
    return {"generated_ts_ns": gen, "published_ts_ns": pub, "primary": price_source or "unknown",
            "observations": obs, "live_divergence": snap, "bar_divergence_1h": bar_cmp,
            "thresholds_pct": {name: lim for lim, name in DIVERGENCE_BANDS},
            "note": "Display and validation only. The engine never reads this file."}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--chart", default="", help="the pipeline's 1h payload (site/data/1h.json)")
    a = ap.parse_args()
    chart, psrc = None, ""
    if a.chart and os.path.exists(a.chart):
        with open(a.chart) as f:
            p = json.load(f)
        ch = p.get("chart", {})
        chart = {"t": ch.get("t"), "c": ch.get("c")}
        psrc = p.get("meta", {}).get("price_source", "")
    out = build(chart, os.environ.get("OANDA_API_TOKEN", "").strip(), os.environ.get("OANDA_ENV", "practice").strip() or "practice",
                os.environ.get("OANDA_ACCOUNT_ID", "").strip(), psrc)
    with open(a.out, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    for o in out["observations"]:
        print(f"{o['provider_id']}: {o['status']} mid={o['mid']} spread={o['spread']} precision={o['timestamp_precision']} {o['note']}")
    print("1h bars:", {k: out["bar_divergence_1h"].get(k) for k in ("n", "status", "diff", "diff_pct", "spread_median")})


if __name__ == "__main__":
    main()
