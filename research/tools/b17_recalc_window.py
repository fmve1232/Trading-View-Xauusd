"""B17 recalculation on a recent window of the site's own data (descriptive; research/registrations/B17.json).

The live engine (treatment, GC volume) runs offline on a copy of the store; every B16 setup in the window is listed
with its four B17 confirmations and its outcome on the 5-minute path (+$13 / +$15 / +$20 before -$13, a bar touching
both = a loss unless it opened beyond the target; neither within a day = OPEN).

  python research/tools/b17_recalc_window.py STORE "2026-11-03 12:00" "2026-11-06 22:00" OUT.json
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
m = mk.build_market("15m", dl, t1.to_pydatetime())
F = compute_features(m, config.DEFAULT)
R = engine.run(m, config.DEFAULT, "treatment", F).rows
idx = pd.DatetimeIndex(F["index"])
t = ta.epoch_s(idx).astype(np.int64).tolist()
h, lo_, c = b16._none(F["h"]), b16._none(F["l"]), b16._none(F["c"])
h1 = sources.trading_week_only(sources.drop_offgrid(ST.load(store, "XAU/USD_60m")))
c1 = {"t": ta.epoch_s(h1.index).astype(np.int64).tolist(), "h": h1["high"].tolist(), "l": h1["low"].tolist(), "c": h1["close"].tolist()}
h4 = sources.resample_ny_session(h1, 4)
c4 = {"t": ta.epoch_s(h4.index).astype(np.int64).tolist(), "h": h4["high"].tolist(), "l": h4["low"].tolist(), "c": h4["close"].tolist()}
lv = notify.setup_levels(t, h, lo_, c1, c4)
for k in ("pdh", "pdl", "pwh", "pwl"):
    lv[k.upper()] = b16._none(R[k])
z = {k: b16._none(R[k]) for k in b16.ZKEYS}
rows = [i for i, x in enumerate(idx) if t0 <= x < t1]
ev = notify.setup_events(t, h, lo_, c, lv, z, rows, {})
votes = notify.trend_votes(t, c1, c4)
bull, bear = b16._none(R["bull"]), b16._none(R["bear"])
x5 = sources.trading_week_only(sources.drop_offgrid(ST.load(store, "XAU/USD_5m")))[["open", "high", "low", "close"]]
pad = pd.DataFrame({k: np.nan for k in x5.columns}, index=pd.date_range(x5.index[-1] + pd.Timedelta(minutes=5), periods=288, freq="5min"))
x5 = pd.concat([x5, pad])
res = []
for e in ev:
    ck = notify.setup_checks(e, votes, bull, bear)
    tc, px, d = np.array([e["t"] + 900]), np.array([e["close"]]), np.array([e["dir"]])
    oc = {}
    for T in (13.0, 15.0, 20.0):
        r = b13.race(x5, tc, px, d, T, 13.0, nbars=288, scale=False)
        oc[f"+{T:g}"] = "TP" if r["win"][0] else "SL" if r["loss"][0] else "OPEN"
    r = b13.race(x5, tc, px, d, 15.0, 1e9, nbars=288, scale=False)
    oc["moved +15 in the day"] = bool(r["win"][0])
    res.append({"utc": datetime.fromtimestamp(e["t"] + 900, timezone.utc).strftime("%a %d %b %H:%M"), "kind": e["kind"],
                "side": "BUY" if e["dir"] > 0 else "SELL", "entry": round(e["close"], 2),
                "levels": [f"{a} {b:.2f}" for a, b in e["levels"]], "zones": e["zones"], "checks": ck,
                "confirmed": all(ck.values()), "outcome": oc})
with open(out_path, "w") as f:
    json.dump({"window": [str(t0), str(t1)], "setups": res}, f, indent=1)
n = len(res)
conf = [x for x in res if x["confirmed"]]
dec = [x for x in res if x["outcome"]["+15"] != "OPEN"]
print(f"{n} setups; +15 before -13: {sum(x['outcome']['+15'] == 'TP' for x in dec)}/{len(dec)}; confirmed {len(conf)}")
for x in res:
    print(f"{x['utc']} {x['kind']:8s} {x['side']:4s} {x['entry']:8.2f} {'+'.join(x['levels']):34s} "
          f"{''.join('Y' if v else '.' for v in x['checks'].values())} {'CONFIRMED' if x['confirmed'] else '':9s} {x['outcome']}")
