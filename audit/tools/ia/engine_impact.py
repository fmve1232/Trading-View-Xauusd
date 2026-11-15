"""Impact replay for the proposed Amendment F: run ONE source tree's treatment engine offline on a store COPY, exactly as
the pipeline builds each market (download_all on the store with every network call blocked, build_market, the 16,000-bar
window), and dump the engine's SIGNAL / VETO events and weekly levels. Run once on production and once on the branch,
then compare with engine_impact_compare.py. Nothing is sent; the store copy is never written back to the repository.

  python audit/tools/ia/engine_impact.py <tree> <store copy> <now ISO UTC> <out.json>
"""
import json
import os
import sys
import time
from datetime import datetime

tree, store, now_iso, out = sys.argv[1:5]
for k in ("NTFY_TOPIC", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK_URL", "GITHUB_STEP_SUMMARY"):
    os.environ.pop(k, None)
os.environ["TWELVEDATA_API_KEY"] = "offline-placeholder-not-a-key"
sys.path.insert(0, tree)
import requests  # noqa: E402

from quantum.data import sources  # noqa: E402


def _off(*a, **k):
    raise sources.FetchError("offline impact replay")


sources._get = _off
requests.post = requests.get = lambda *a, **k: (_ for _ in ()).throw(requests.exceptions.ConnectionError("offline"))
from quantum import engine, holdout  # noqa: E402
from quantum.config import DEFAULT  # noqa: E402
from quantum.data import market as mk  # noqa: E402
from quantum.data.market import TIMEFRAMES  # noqa: E402
from quantum.features import compute as compute_features  # noqa: E402
from quantum.pipeline import MAX_BARS  # noqa: E402

now = datetime.fromisoformat(now_iso)
tfs = ["15m", "30m", "1h", "4h", "5m"]
need = sorted({("60m" if TIMEFRAMES[tf].get("resample_from") else TIMEFRAMES[tf]["yahoo"]) for tf in tfs} | {"60m"})
dl = mk.download_all(store, tuple(need))
res_all = {"tree": tree, "freeze_key": holdout.freeze_key(DEFAULT), "now": now_iso, "tf": {}}
for tf in tfs:
    t0 = time.time()
    m = mk.build_market(tf, dl, now)
    if len(m.base) > MAX_BARS:
        m.base = m.base.iloc[-MAX_BARS:]
    F = compute_features(m, DEFAULT)
    r = engine.run(m, DEFAULT, "treatment", F)
    idx = F["index"]
    ts = [int(x.timestamp()) for x in idx]
    ev = []
    for e in r.events:
        if e["type"] in ("SIGNAL", "VETO", "SWEEP"):
            ev.append({"t": ts[e["i"]], "type": e["type"], "dir": e.get("dir"), "px": round(float(e.get("px", float("nan"))), 2),
                       "why": e.get("why", ""), "sl": e.get("sl"), "tp1": e.get("tp1")})
    R = r.rows
    rnd = lambda a: [None if (v is None or v != v) else round(float(v), 2) for v in a]
    res_all["tf"][tf] = {"bars": len(ts), "first": ts[0], "last": ts[-1], "events": ev, "t": ts,
                         "pwh": rnd(R["pwh"]), "pwl": rnd(R["pwl"]), "tq": [int(x) for x in R["tq"]],
                         "should": [int(bool(a) or bool(b)) for a, b in zip(R["should_buy"], R["should_sell"])],
                         "cal_veto": [int(bool(x)) for x in R["cal_veto"]], "ev_veto": [int(bool(x)) for x in R["ev_veto"]],
                         "tq_floor": [int(bool(x)) for x in R["tq_floor_veto"]], "sec": round(time.time() - t0, 1)}
    print(tf, len(ts), "bars", sum(1 for e in ev if e["type"] == "SIGNAL"), "signals", res_all["tf"][tf]["sec"], "s", flush=True)
with open(out, "w") as f:
    json.dump(res_all, f, default=lambda v: None if v != v else v)
