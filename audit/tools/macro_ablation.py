"""How much do the engine's cross-asset feeds change its signals? A read-only ablation of the FROZEN engine.

  PYTHONPATH=<deployed checkout> python3 -I audit/tools/macro_ablation.py <store COPY> <snapshot UTC ISO> <out.json>

Runs the deployed engine (treatment arm, the phone's arm, DEFAULT config: no setting changes) offline on a copy of the
production store: every network fetch fails, so each series comes from the store exactly as the pipeline's
"store (live fetch failed)" path reads it (FRED and COT are then absent; in DEFAULT neither can change a signal: COT
gating is off and the real yield is unused, tips_source = us10y). Then it removes one cross-asset feed at a time, and all
of them together, and compares the SIGNAL events bar by bar. GC=F volume on the spot bars (the volume gate) is a separate
path and is kept in every variant; only GC as a confirming market is removed.

What it measures: the demonstrated connection of each feed to the final output (how many signals exist only because of
it, or are removed by it), not whether that connection is profitable. Outcomes of the changed signals are reported with
the plan's own +/-$13 race on the following bars of the same timeframe, descriptively (samples are small)."""
from __future__ import annotations

import copy
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime


STORE, SNAP, OUT = sys.argv[1], datetime.fromisoformat(sys.argv[2].replace("Z", "+00:00")), sys.argv[3]
TFS = ("15m", "30m", "1h", "4h")
VARIANTS = {"baseline": (), "no DXY": ("dxy",), "no US10Y": ("us10y",), "no silver": ("silver",), "no EURUSD": ("eurusd",),
            "no SPX": ("spx",), "no GC confirm": ("gc",), "no cross-asset at all": ("dxy", "us10y", "silver", "eurusd", "spx", "gc")}
TP = SL = 13.0
FROM = "2026-01-01"           # after the sealed holdout (Amendment 13): signals before this are never counted


def offline():
    """Every fetch fails, so each series is read from the store copy. A placeholder key makes the pipeline take its
    Twelve Data branch (production's price source) and read the stored Twelve Data bars; no request is ever sent."""
    os.environ["TWELVEDATA_API_KEY"] = "offline-placeholder-not-a-key"
    from quantum.data import sources

    def _off(*a, **k):
        raise sources.FetchError("offline audit run")
    sources._get = _off


def race(m, i, d):
    """+/-$13 from the signal bar's close on the following bars: TP, SL, BOTH (same bar) or None (open)."""
    c = float(m.base["close"].iloc[i])
    hi, lo = m.base["high"].to_numpy(float)[i + 1:], m.base["low"].to_numpy(float)[i + 1:]
    for h_, l_ in zip(hi, lo):
        tp = h_ >= c + TP if d == 1 else l_ <= c - TP
        sl = l_ <= c - SL if d == 1 else h_ >= c + SL
        if tp and sl:
            return "BOTH"
        if tp or sl:
            return "TP" if tp else "SL"
    return None


def job(tf):
    offline()
    from quantum import engine
    from quantum.config import DEFAULT
    from quantum.data import market as mk
    from quantum.features import compute
    from quantum.pipeline import MAX_BARS
    dl = mk.download_all(STORE, ("5m", "15m", "30m", "60m"))
    base = mk.build_market(tf, dl, SNAP)
    assert base.price_source.startswith("twelvedata"), base.price_source
    if len(base.base) > MAX_BARS:
        base.base = base.base.iloc[-MAX_BARS:]
    out = {}
    sigs = {}
    for name, drop in VARIANTS.items():
        m = copy.copy(base)
        m.ext_macro, m.ext_chart = dict(base.ext_macro), dict(base.ext_chart)
        for k in drop:
            if k in ("dxy", "us10y"):
                m.ext_macro[k] = None
            else:
                m.ext_chart[k] = None
        res = engine.run(m, DEFAULT, "treatment", compute(m, DEFAULT))
        first = int(base.base.index.searchsorted(__import__("pandas").Timestamp(FROM, tz="UTC")))
        sigs[name] = {(e["i"], e["dir"]) for e in res.events if e["type"] == "SIGNAL" and e["i"] >= first}
    b = sigs["baseline"]
    t0 = str(base.base.index[0])[:16]
    for name, s in sigs.items():
        only_base, only_var = sorted(b - s), sorted(s - b)
        out[name] = {"signals": len(s), "removed_by_dropping": len(only_base), "added_by_dropping": len(only_var),
                     "outcomes_of_signals_that_need_the_feed": _tally([race(base, i, d) for i, d in only_base]),
                     "outcomes_of_signals_the_feed_suppresses": _tally([race(base, i, d) for i, d in only_var])}
    return tf, {"bars": len(base.base), "first_bar": t0, "signals_counted_from": FROM, "last_bar": str(base.base.index[-1])[:16],
                "price_source": base.price_source, "series_status": {k: v.source for k, v in base.status.items()}, "variants": out,
                "baseline_outcomes": _tally([race(base, i, d) for i, d in sorted(b)])}


def _tally(xs):
    return {k: sum(1 for x in xs if x == k) for k in ("TP", "SL", "BOTH", None) if any(x == k for x in xs)} if xs else {}


def main():
    with ProcessPoolExecutor(max_workers=4) as ex:
        res = dict(ex.map(job, TFS))
    with open(OUT, "w") as f:
        json.dump(res, f, indent=1, default=str)
    for tf, r in res.items():
        print(tf, r["bars"], r["first_bar"], "->", r["last_bar"], r["price_source"])
        for name, v in r["variants"].items():
            print(f"   {name:24s} signals {v['signals']:4d}  removed {v['removed_by_dropping']:3d}  added {v['added_by_dropping']:3d}"
                  f"  | needed-feed outcomes {v['outcomes_of_signals_that_need_the_feed']}  suppressed outcomes {v['outcomes_of_signals_the_feed_suppresses']}")
        print("   baseline outcomes", r["baseline_outcomes"])


if __name__ == "__main__":
    main()
