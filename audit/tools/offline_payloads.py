"""Rebuild the site payloads a tree's pipeline would have produced at a past moment, offline (read-only on the tree).

  python3 -I audit/tools/offline_payloads.py <tree> <store COPY> <snapshot UTC ISO> <out dir> [tf ...]

Every network fetch raises (quantum.data.sources._get is replaced), so the market data come from the store copy only;
Twelve Data prices are asserted (a payload built on another price source is refused). Writes <out dir>/<tf>.json for
15m, 30m, 1h, 4h, 5m (default), as quantum.pipeline.run_tf builds them. The store copy may be written (holdout ledgers):
never pass the live store. Used for the 13 Nov 2026 plan #12 replay (P-0), whose production payloads had expired; check
the result against the production delivery log before relying on it. Payloads are vendor-derived market data: keep them
out of the repository."""
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime

TREE, STORE, OUT = sys.argv[1], sys.argv[2], sys.argv[4]
SNAP = datetime.fromisoformat(sys.argv[3].replace("Z", "+00:00"))
PIPELINE_TFS = ("15m", "30m", "1h", "4h", "5m")   # the workflow's --tfs: the series loaded for EVERY payload, as in
TFS = tuple(sys.argv[5:]) or PIPELINE_TFS         # production (a payload built with fewer loaded series differs)
sys.path.insert(0, TREE)


def job(tf):
    os.environ["TWELVEDATA_API_KEY"] = "offline-placeholder-not-a-key"   # selects the store's Twelve Data series
    from quantum.data import sources

    def _off(*a, **k):
        raise sources.FetchError("offline rebuild")
    sources._get = _off
    from quantum import holdout, pipeline
    from quantum.config import DEFAULT, TIMEFRAMES
    from quantum.data import market as mk
    need = sorted({("60m" if TIMEFRAMES[t].get("resample_from") else TIMEFRAMES[t]["yahoo"]) for t in PIPELINE_TFS} | {"60m"})
    m = mk.build_market(tf, mk.download_all(STORE, tuple(need)), SNAP)
    assert m.price_source.startswith("twelvedata"), m.price_source
    p = pipeline.run_tf(m, DEFAULT, holdout.load_or_freeze(STORE, DEFAULT, SNAP), SNAP, None)
    with open(os.path.join(OUT, f"{tf}.json"), "w") as f:
        json.dump(p, f, separators=(",", ":"), allow_nan=False)
    return tf, p["meta"]["price_source"], p["meta"]["last_bar_close"], len(p["markers"])


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    with ProcessPoolExecutor(max_workers=min(5, len(TFS))) as ex:
        for r in ex.map(job, TFS):
            print(*r, flush=True)
