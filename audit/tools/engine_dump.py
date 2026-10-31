#!/usr/bin/env python3
"""Run the engine READ-ONLY on a COPY of the market-data store and dump what engine_calibration.py needs (Amendment 12).

Nothing is fetched (network calls are disabled, so every series comes from the store copy, marked "store (live fetch
failed)" by data/market.py) and nothing is written anywhere but that copy and the output file. Make the copy with
`git archive origin/market-data | tar -x -C <dir>`; never point it at the pipeline's own store.
Usage: PYTHONPATH=. python3 audit/tools/engine_dump.py <15m|1h|5m> <store copy> <out.pkl>"""
import os, sys, time, pickle
from datetime import datetime, timezone
os.environ["TWELVEDATA_API_KEY"] = "offline-audit"   # forces the Twelve Data store name; the live call fails, the stored bars are used
import requests
_orig = requests.Session.request
def _offline(self, *a, **k):
    raise requests.ConnectionError("offline audit: network disabled")
requests.Session.request = _offline
requests.get = lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("offline audit"))
from quantum import engine, config
from quantum.data import market as mk
from quantum.features import compute
tf = sys.argv[1]; store = sys.argv[2]
cfg = config.DEFAULT
need = ("5m", "15m", "60m") if tf == "5m" else ("15m", "60m") if tf == "15m" else ("60m",)
t0 = time.time()
dl = mk.download_all(store, need)
print("price source", dl.price_source, {k: (v.ok, v.rows, v.source) for k, v in dl.status.items() if "XAU" in k}, flush=True)
m = mk.build_market(tf, dl, datetime(2026, 10, 31, 1, 0, tzinfo=timezone.utc))
print("bars", len(m.base), m.base.index[0], m.base.index[-1], flush=True)
F = compute(m, cfg)
res = engine.run(m, cfg, "treatment", F)
print("engine run", round(time.time() - t0), "s; outcome_n", res.outcome_n, flush=True)
rows = res.rows
keep = {k: rows[k] for k in ("cal_p_long", "cal_p_short", "plan_ev", "should_buy", "should_sell", "exec_buy", "exec_sell", "tq") if k in rows}
pickle.dump(dict(index=m.base.index, o=m.base["open"].values, h=m.base["high"].values, l=m.base["low"].values, c=m.base["close"].values,
                 F_keys=list(F.keys()), rows=keep, row_keys=list(rows.keys()), N=res.outcome_n,
                 aatr=F.get("aatr"), regsl=F.get("reg_sl_mult")), open(sys.argv[3], "wb"))
