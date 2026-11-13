"""Stage-2 verification of the cross-asset ablation, signal by signal (read-only).

  PYTHONPATH=<deployed checkout> python3 -I audit/tools/v2_ablation.py <store COPY> <snapshot UTC ISO> <out dir>

Three runs of the deployed engine (treatment arm, DEFAULT config) per timeframe, offline from store copies with Twelve
Data prices asserted:
  baseline     the store copy as it is;
  no_xasset    the same with DXY, US10Y, silver, EURUSD, S&P and GC-as-confirmation removed (GC volume kept);
  cut_2026     a second store copy from which every month file before 2026-01 is deleted (every series): if its
               signals equal the baseline's, no sealed-period bar influenced any counted signal.
Signals are counted from 2026-01-01. For each signal: bar open / close (UTC), side, entry (the bar close), the engine's
own SL and TP1, TQ, and two outcomes, never mixed:
  hypothetical  +/-$13 from the entry on the later bars of the same timeframe in the store (FINAL, revised data):
                TP / SL / BOTH (both on one bar) / OPEN;
  recorded      what production recorded for the same (timeframe, bar, side): the plan's result in plan_validation.json
                or alerts_state.json's plan_log, an open plan, or a REPEAT (no plan). Production keeps these only from
                2026-11-02.
Also the match between the offline baseline and production's recorded signals over that window.
Outputs: v2_ablation_signals.csv (every signal in baseline or no_xasset), v2_ablation.json."""
from __future__ import annotations

import copy
import csv
import json
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

import pandas as pd

STORE, SNAP, OUT = sys.argv[1], datetime.fromisoformat(sys.argv[2].replace("Z", "+00:00")), sys.argv[3]
CUT_STORE = STORE.rstrip("/") + "_cut2026"
TFS = ("15m", "30m", "1h", "4h")
FROM = pd.Timestamp("2026-01-01", tz="UTC")
XASSET = ("dxy", "us10y", "silver", "eurusd", "spx", "gc")


def offline():
    os.environ["TWELVEDATA_API_KEY"] = "offline-placeholder-not-a-key"
    from quantum.data import sources

    def _off(*a, **k):
        raise sources.FetchError("offline audit run")
    sources._get = _off


def race(m, i, d, px):
    hi, lo = m.base["high"].to_numpy(float)[i + 1:], m.base["low"].to_numpy(float)[i + 1:]
    for h_, l_ in zip(hi, lo):
        tp = h_ >= px + 13 if d == 1 else l_ <= px - 13
        sl = l_ <= px - 13 if d == 1 else h_ >= px + 13
        if tp and sl:
            return "BOTH"
        if tp or sl:
            return "TP" if tp else "SL"
    return "OPEN"


def run(store, tf, drop=()):
    offline()
    from quantum import engine
    from quantum.config import DEFAULT
    from quantum.data import market as mk
    from quantum.features import compute
    from quantum.pipeline import MAX_BARS
    dl = mk.download_all(store, ("5m", "15m", "30m", "60m"))
    m = mk.build_market(tf, dl, SNAP)
    assert m.price_source.startswith("twelvedata"), m.price_source
    if len(m.base) > MAX_BARS:
        m.base = m.base.iloc[-MAX_BARS:]
    if drop:
        m = copy.copy(m)
        m.ext_macro, m.ext_chart = dict(m.ext_macro), dict(m.ext_chart)
        for k in drop:
            (m.ext_macro if k in ("dxy", "us10y") else m.ext_chart)[k] = None
    res = engine.run(m, DEFAULT, "treatment", compute(m, DEFAULT))
    first = int(m.base.index.searchsorted(FROM))
    out = {}
    for e in res.events:
        if e["type"] == "SIGNAL" and e["i"] >= first:
            t = m.base.index[e["i"]]
            out[(str(t), e["dir"])] = {"bar_open": str(t)[:16], "bar_close": str(t + pd.Timedelta(seconds=m.tf_sec))[:16],
                                       "side": "BUY" if e["dir"] == 1 else "SELL", "entry": round(float(e["px"]), 2),
                                       "engine_sl": round(float(e["sl"]), 2), "engine_tp1": round(float(e["tp1"]), 2), "tq": e.get("tq"),
                                       "hypothetical_13": race(m, e["i"], e["dir"], float(e["px"]))}
    return out, str(m.base.index[0])[:16]


def job(tf):
    base, first_bar = run(STORE, tf)
    nox, _ = run(STORE, tf, XASSET)
    cut, cut_first = run(CUT_STORE, tf)
    return tf, {"baseline": base, "no_xasset": nox, "cut_2026": cut, "first_bar": first_bar, "cut_first_bar": cut_first}


def production(store):
    st = json.load(open(os.path.join(store, "alerts_state.json")))
    pv = json.load(open(os.path.join(store, "plan_validation.json")))
    rec = {}
    for v in pv:
        rec[(v["tf"], int(v["t"]), v["dir"])] = ("plan", v.get("result"), v.get("entry"))
    for v in st.get("plans", []):
        rec.setdefault((v["tf"], int(v["t"]), v["dir"]), ("plan", "OPEN", v.get("entry")))
    for v in st.get("plan_log", []):                       # closed plans kept for the website (from 2026-11-02)
        rec.setdefault((v["tf"], int(v["t"]), v["dir"]), ("plan", v.get("result"), v.get("entry")))
    for v in st.get("plan_repeats", []):
        rec.setdefault((v["tf"], int(v["t"]), v["dir"]), ("repeat", "REPEAT (no plan)", v.get("entry")))
    t0 = min(int(v["t"]) for v in list(pv) + st.get("plan_log", []))
    return rec, t0


def main():
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(CUT_STORE):
        shutil.rmtree(CUT_STORE)
    shutil.copytree(STORE, CUT_STORE)
    removed = 0
    for d in os.listdir(CUT_STORE):
        p = os.path.join(CUT_STORE, d)
        if os.path.isdir(p) and d not in ("holdout", "research_forward"):
            for f in os.listdir(p):
                if f.endswith(".csv") and f[:7] < "2026-01":
                    os.remove(os.path.join(p, f))
                    removed += 1
    rec, t0 = production(STORE)
    with ProcessPoolExecutor(max_workers=4) as ex:
        res = dict(ex.map(job, TFS))
    summary, rows = {"month_files_removed_for_cut_2026": removed, "production_records_from": datetime.fromtimestamp(t0, timezone.utc).isoformat()}, []
    for tf, r in res.items():
        b, n, c = r["baseline"], r["no_xasset"], r["cut_2026"]
        keys = sorted(set(b) | set(n))
        win_prod = [k for k in b if pd.Timestamp(k[0]).timestamp() >= t0]
        prod_keys = {k for k in rec if k[0] == tf and k[1] >= t0}
        matched = [k for k in win_prod if (tf, int(pd.Timestamp(k[0]).timestamp()), k[1]) in rec]
        off_only = [k for k in win_prod if (tf, int(pd.Timestamp(k[0]).timestamp()), k[1]) not in rec]
        base_keys_prod = {(tf, int(pd.Timestamp(k[0]).timestamp()), k[1]) for k in b}
        prod_only = sorted(k for k in prod_keys if k not in base_keys_prod and k[1] <= SNAP.timestamp())
        summary[tf] = {"first_bar": r["first_bar"], "baseline": len(b), "no_xasset": len(n), "cut_2026": len(c),
                       "cut_2026_identical_to_baseline": set(c) == set(b) and all(c[k] == b[k] for k in b),
                       "cut_first_bar": r["cut_first_bar"],
                       "removed_by_dropping": len(set(b) - set(n)), "added_by_dropping": len(set(n) - set(b)),
                       "production_window_offline_signals": len(win_prod), "matched_production": len(matched),
                       "offline_only": len(off_only), "production_only": len(prod_only),
                       "production_only_list": [(datetime.fromtimestamp(k[1], timezone.utc).strftime("%Y-%m-%d %H:%M"), "BUY" if k[2] == 1 else "SELL", rec[k][1]) for k in prod_only]}
        for k in keys:
            s = b.get(k) or n.get(k)
            pk = (tf, int(pd.Timestamp(k[0]).timestamp()), k[1])
            pr = rec.get(pk)
            rows.append({"timeframe": tf, **s, "in_baseline": k in b, "in_no_xasset": k in n,
                         "change": "" if (k in b and k in n) else ("needs the feeds (removed when dropped)" if k in b else "suppressed by the feeds (added when dropped)"),
                         "in_production_window": pd.Timestamp(k[0]).timestamp() >= t0,
                         "recorded_in_production": (pr[0] + ": " + str(pr[1])) if pr else ("" if pd.Timestamp(k[0]).timestamp() < t0 else "not recorded")})
    json.dump(summary, open(os.path.join(OUT, "v2_ablation.json"), "w"), indent=1, default=str)
    with open(os.path.join(OUT, "v2_ablation_signals.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(json.dumps(summary, indent=1, default=str))
    shutil.rmtree(CUT_STORE)


if __name__ == "__main__":
    main()
