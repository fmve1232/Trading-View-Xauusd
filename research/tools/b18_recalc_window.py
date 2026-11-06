"""B18 recalculation on a recent window of the site's own data (descriptive; research/registrations/B18.json).

The live engine runs offline on the store's 4h bars; every 4h breakout in the window is listed with its four
confirmations and its outcome from the 4h close on the 5-minute path (+$13 / +$15 / +$20 before -$13).

  python research/tools/b18_recalc_window.py STORE "2026-11-03 12:00" "2026-11-06 22:00" OUT.json
"""
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ["TWELVEDATA_API_KEY"] = "offline"
from quantum import config, engine, notify, ta
from quantum.data import market as mk
from quantum.data import sources
from quantum.data import store as ST
from quantum.features import compute as compute_features
from quantum.research import b13, b16


def boom(*a, **k):
    raise sources.FetchError("offline")


for nm in ("twelvedata", "yahoo", "fred", "cftc_gold_cot"):
    setattr(sources, nm, boom)

store, t0, t1, out_path = sys.argv[1], pd.Timestamp(sys.argv[2], tz="UTC"), pd.Timestamp(sys.argv[3], tz="UTC"), sys.argv[4]
dl = mk.download_all(store, ("5m", "15m", "30m", "60m"))
m = mk.build_market("4h", dl, t1.to_pydatetime())
F = compute_features(m, config.DEFAULT)
R = engine.run(m, config.DEFAULT, "treatment", F).rows
idx = pd.DatetimeIndex(F["index"])
t4 = ta.epoch_s(idx).astype(np.int64).tolist()
h, lo_, c = b16._none(F["h"]), b16._none(F["l"]), b16._none(F["c"])
h1 = sources.trading_week_only(sources.drop_offgrid(ST.load(store, "XAU/USD_60m")))
c1 = {"t": ta.epoch_s(h1.index).astype(np.int64).tolist(), "h": h1["high"].tolist(), "l": h1["low"].tolist(), "c": h1["close"].tolist()}
c4 = {"t": t4, "h": h, "l": lo_, "c": c}
lv = notify.setup_levels(t4, h, lo_, c1, c4)
for k in ("pdh", "pdl", "pwh", "pwl"):
    lv[k.upper()] = b16._none(R[k])
votes = notify.trend_votes([x + 14400 for x in t4], c1, c4)
rows = [i for i, x in enumerate(idx) if t0 <= x and x + pd.Timedelta(hours=4) <= t1]
ev = notify.h4_events(t4, h, lo_, c, b16._none(R["bull"]), b16._none(R["bear"]), lv, votes, rows)
x5 = sources.trading_week_only(sources.drop_offgrid(ST.load(store, "XAU/USD_5m")))[["open", "high", "low", "close"]]
pad = pd.DataFrame({k: np.nan for k in x5.columns}, index=pd.date_range(x5.index[-1] + pd.Timedelta(minutes=5), periods=288, freq="5min"))
x5 = pd.concat([x5, pad])
res = []
for e in ev:
    tc, px, d = np.array([e["t_close"]]), np.array([e["close"]]), np.array([e["dir"]])
    oc = {}
    for T in (13.0, 15.0, 20.0):
        r = b13.race(x5, tc, px, d, T, 13.0, nbars=288, scale=False)
        oc[f"+{T:g}"] = "TP" if r["win"][0] else "SL" if r["loss"][0] else "OPEN"
    res.append({"close_utc": datetime.fromtimestamp(e["t_close"], timezone.utc).strftime("%a %d %b %H:%M"),
                "side": "BUY" if e["dir"] > 0 else "SELL", "entry": round(e["close"], 2),
                "prev": round(e["prev_high"] if e["dir"] > 0 else e["prev_low"], 2),
                "beyond": [f"{a} {b:.2f}" for a, b in e["beyond"]], "checks": e["checks"], "confirmed": e["confirmed"], "outcome": oc})
with open(out_path, "w") as f:
    json.dump({"window": [str(t0), str(t1)], "breakouts": res}, f, indent=1)
print(f"{len(res)} 4h breakouts; confirmed {sum(x['confirmed'] for x in res)}")
for x in res:
    print(f"{x['close_utc']} {x['side']:4s} {x['entry']:8.2f} prev {x['prev']:8.2f} {'+'.join(x['beyond']):28s} "
          f"{''.join('Y' if v else '.' for v in x['checks'].values())} {'CONFIRMED' if x['confirmed'] else '':9s} {x['outcome']}")
