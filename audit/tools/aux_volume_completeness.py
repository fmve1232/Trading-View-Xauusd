"""Decision-time volume completeness: would the engine's historical signals still fire with the volume the live run
actually sees on the decision bar? (offline, read-only; research measurement)

Usage: python audit/tools/aux_volume_completeness.py <store snapshot> <now UTC epoch> <tf> <c1,c2,...> <out.json> [max_bars]

The spot bars' volume is COMEX GC futures volume (PLATFORM.md D-07). Yahoo's latest GC bar is still incomplete when
the pipeline reads it a few minutes after the close (measured 46-77% of the final 15m volume on 12 Nov). The engine is
causal, so a signal at bar i depends only on bars <= i. For every SIGNAL bar i of the treatment arm (and, as a control,
an equal number of non-signal bars) the engine is re-run on the history cut at i, once with bar i's final volume
(must reproduce the original decision) and once per completeness c with bar i's volume x c. Earlier bars keep their
final volume (they are complete by then). Engine, features and data layer are used unchanged."""
import json
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

os.environ["TWELVEDATA_API_KEY"] = "offline-dummy"
from quantum.data import sources as s                  # noqa: E402


def _off(*a, **k):
    raise s.FetchError("offline")


s._get = _off
from quantum import engine                             # noqa: E402
from quantum.config import DEFAULT, TIMEFRAMES         # noqa: E402
from quantum.data import market as mk                  # noqa: E402
from quantum.features import compute as compute_features  # noqa: E402
from quantum.pipeline import MAX_BARS                  # noqa: E402

TFS = ["15m", "30m", "1h", "4h", "5m"]
_M = None


def _market(store_dir, tf, now_iso):
    need = sorted({("60m" if TIMEFRAMES[t].get("resample_from") else TIMEFRAMES[t]["yahoo"]) for t in TFS} | {"60m"})
    m = mk.build_market(tf, mk.download_all(store_dir, tuple(need)), datetime.fromisoformat(now_iso))
    if len(m.base) > MAX_BARS:
        m.base = m.base.iloc[-MAX_BARS:]
    return m


def _signals(res):
    return {e["i"]: e for e in res.events if e.get("type") == "SIGNAL"}


def _fields(sig):
    return None if sig is None else {"dir": sig["dir"], "px": sig["px"], "sl": sig.get("sl"), "tp1": sig.get("tp1"),
                                     "tq": sig.get("tq")}


def _init(store_dir, tf, now_iso):
    global _M
    _M = _market(store_dir, tf, now_iso)


def _run_cut(i, c):
    import copy
    m = copy.copy(_M)
    b = _M.base.iloc[: i + 1].copy()
    if c != 1.0:
        b.iloc[-1, b.columns.get_loc("volume")] = float(b["volume"].iloc[-1]) * c
    m.base = b
    res = engine.run(m, DEFAULT, "treatment", compute_features(m, DEFAULT))
    return {"i": i, "c": c, "signal": _fields(_signals(res).get(i)), "decision": res.last.get("decision")}


def main():
    store_dir, now_epoch, tf, cs, out = sys.argv[1:6]
    max_bars = int(sys.argv[6]) if len(sys.argv) > 6 else 3000
    now_iso = datetime.fromtimestamp(int(now_epoch), timezone.utc).isoformat()
    cs = [float(x) for x in cs.split(",")]
    m = _market(store_dir, tf, now_iso)
    full = engine.run(m, DEFAULT, "treatment", compute_features(m, DEFAULT))
    n = len(m.base)
    full_sig = _signals(full)
    sig_bars = sorted(i for i in full_sig if i >= n - max_bars)
    random.seed(7)
    pool = [i for i in range(n - max_bars, n) if i not in _signals(full)]
    ctrl_bars = sorted(random.sample(pool, min(len(sig_bars), len(pool))))
    jobs = [(i, c) for i in sig_bars + ctrl_bars for c in [1.0] + cs]
    with ProcessPoolExecutor(max_workers=4, initializer=_init, initargs=(store_dir, tf, now_iso)) as ex:
        rows = list(ex.map(_run_cut, *zip(*jobs), chunksize=1))
    t = (m.base.index - __import__("pandas").Timestamp(0, tz="UTC")) // __import__("pandas").Timedelta(seconds=1)
    by = {}
    for r in rows:
        by.setdefault(r["i"], {})[r["c"]] = r
    summary = {"tf": tf, "bars": n, "window": max_bars, "signal_bars": len(sig_bars), "control_bars": len(ctrl_bars),
               "reproduced_with_final_volume": sum(1 for i in sig_bars if by[i][1.0]["signal"] is not None),
               # validity check: with final volume every cut run must equal the full run at its bar, field for field,
               # and every control bar must stay without a signal
               "exact_with_final_volume": sum(1 for i in sig_bars if by[i][1.0]["signal"] == _fields(full_sig[i])),
               "control_clean_with_final_volume": sum(1 for i in ctrl_bars if by[i][1.0]["signal"] is None),
               "per_completeness": {}}
    for c in cs:
        kept = [i for i in sig_bars if by[i][c]["signal"] is not None]
        lost = [i for i in sig_bars if by[i][c]["signal"] is None]
        new = [i for i in ctrl_bars if by[i][c]["signal"] is not None]
        lvl = [i for i in kept if by[i][c]["signal"] != by[i][1.0]["signal"]]
        summary["per_completeness"][str(c)] = {"signals_kept": len(kept), "signals_lost": len(lost),
                                               "signals_with_changed_levels": len(lvl), "new_signals_on_control_bars": len(new),
                                               "lost_bars_utc": [datetime.fromtimestamp(int(t[i]), timezone.utc).isoformat() for i in lost]}
    json.dump({"summary": summary, "rows": rows}, open(out, "w"), indent=1, default=str)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
