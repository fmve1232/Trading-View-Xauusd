"""End-to-end run: download -> engine (treatment + control arm) -> JSON for the site -> alerts.

  python -m quantum.pipeline --out site/data --store store          # live, free sources
  python -m quantum.pipeline --out site/data --synthetic            # offline, labelled SYNTHETIC
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

from . import engine, holdout, notify, report
from .config import DEFAULT, ENGINE_VERSION, TIMEFRAMES
from .data import market as mk
from .features import compute as compute_features


MAX_BARS = 16000   # rolling engine window; the holdout ledger keeps anything that scrolls out


def run_tf(m, cfg, man, now, store_dir=None):
    t0 = time.time()
    if len(m.base) > MAX_BARS:
        m.base = m.base.iloc[-MAX_BARS:]
    F = compute_features(m, cfg)
    res = engine.run(m, cfg, "treatment", F)
    ctrl = engine.run(m, cfg, "control", F)
    payload = report.build(m, res, ctrl, cfg, man, now, store_dir)
    payload["meta"]["runtime_sec"] = round(time.time() - t0, 1)
    return payload


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site/data")
    ap.add_argument("--store", default=None, help="market-data store dir (history accumulates here)")
    ap.add_argument("--tfs", default="15m,1h,4h,5m")
    ap.add_argument("--alert-tfs", default=os.environ.get("ALERT_TFS", "15m,1h"))
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--bars", type=int, default=6000, help="synthetic bars")
    args = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    cfg = DEFAULT
    os.makedirs(args.out, exist_ok=True)
    tfs = [x.strip() for x in args.tfs.split(",") if x.strip()]
    man = holdout.load_or_freeze(args.store, cfg, now)
    index = {"generated_utc": now.isoformat(), "engine_version": ENGINE_VERSION, "config_hash": cfg.hash(),
             "holdout": {k: man.get(k) for k in ("freeze_utc", "status", "config_hash")}, "timeframes": {}, "errors": {}}
    payloads = {}
    dl = None
    if not args.synthetic:
        try:
            need = sorted({("60m" if TIMEFRAMES[tf].get("resample_from") else TIMEFRAMES[tf]["yahoo"]) for tf in tfs} | {"60m"})
            dl = mk.download_all(args.store, tuple(need))
        except Exception as e:  # noqa: BLE001
            index["errors"]["download"] = mk.sources.redact(f"{type(e).__name__}: {e}")
            traceback.print_exc()
    jobs = {}
    for tf in tfs:
        try:
            if args.synthetic:
                jobs[tf] = mk.load_synthetic(tf, bars=args.bars)
            elif dl is not None:
                jobs[tf] = mk.build_market(tf, dl, now)
        except Exception as e:  # noqa: BLE001
            index["errors"][tf] = mk.sources.redact(f"{type(e).__name__}: {e}")
            traceback.print_exc()
    store_dir = None if args.synthetic else args.store
    workers = max(1, min(len(jobs), os.cpu_count() or 1, 4))
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {tf: ex.submit(run_tf, m, cfg, man, now, store_dir) for tf, m in jobs.items()}
        for tf, fut in futs.items():
            try:
                p = fut.result()
            except Exception as e:  # noqa: BLE001
                index["errors"][tf] = mk.sources.redact(f"{type(e).__name__}: {e}")
                traceback.print_exc()
                continue
            payloads[tf] = p
            with open(os.path.join(args.out, f"{tf}.json"), "w") as f:
                json.dump(p, f, separators=(",", ":"), allow_nan=False)
            d = p["dashboard"]
            index["timeframes"][tf] = {
                "decision": d["decision"], "bias": d["bias_label"], "bull": d["bull_score"], "bear": d["bear_score"],
                "range": d["range_score"], "tq": d["trade_quality"], "close": d["close"],
                "last_bar_close": p["meta"]["last_bar_close"], "synthetic": p["meta"]["synthetic"],
                "price_source": p["meta"]["price_source"], "runtime_sec": p["meta"]["runtime_sec"],
            }
            print(f"[{tf}] {d['decision']} bias={d['bias_label']} tq={d['trade_quality']} bars={p['meta']['bars']} "
                  f"({p['meta']['runtime_sec']}s)")
    if payloads:
        alert_tfs = [x.strip() for x in args.alert_tfs.split(",") if x.strip()]
        index["alerts"] = notify.run(args.store, payloads, alert_tfs)
    with open(os.path.join(args.out, "index.json"), "w") as f:
        json.dump(index, f, indent=1, default=str)
    return 0 if payloads else 1


if __name__ == "__main__":
    sys.exit(main())
