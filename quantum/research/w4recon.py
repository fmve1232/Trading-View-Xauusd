"""B31b-W4 deliverable 1 (research only; production never imports this): point-in-time reconstruction of 18 Nov 2026,
the day of the operator's M15 / M30 screenshots (~20:57 UTC = 22:57 MT5). At each decision time the zones are rebuilt
by quantum/keyzones.py from the bars CLOSED by then (nothing later is visible) and set against the operator's visual
zones; the M15 bars that mattered are listed with the reason. Descriptive only: no outcome is tested here.

    python -m quantum.research.w4recon <market-data store> <out.json>
"""
import json
import sys

import numpy as np
import pandas as pd

from .. import keyzones as K
from .. import ta
from ..data import sources, store

SER = {"15m": ("XAU_USD_15m", 900, 1500), "30m": ("XAU_USD_30m", 1800, 1500), "1h": ("XAU_USD_60m", 3600, 1500), "4h": (None, 14400, 1100)}
OP = [(3720, 3725), (3728, 3734), (3741, 3749), (3756, 3765), (3772, 3780), (3787, 3794)]   # the operator's visual zones
DECISIONS = ["2026-11-18 08:00", "2026-11-18 13:00", "2026-11-18 16:00", "2026-11-18 19:00", "2026-11-18 19:45",
             "2026-11-18 20:45", "2026-11-18 21:30"]


def ts(t):
    return pd.Timestamp(t, unit="s", tz="UTC")


def load(st_dir):
    raw = {tf: sources.trading_week_only(sources.drop_offgrid(store.load(st_dir, nm))) for tf, (nm, _, _) in SER.items() if nm}
    raw["4h"] = sources.resample_ny_session(raw["1h"], 4)
    return raw


def pay(raw, tf, now):
    """A payload of the bars CLOSED by `now` (the forming bar is never in it)."""
    nm, sec, keep = SER[tf]
    df = raw[tf]
    t = ta.epoch_s(df.index).astype(np.int64)
    df = df[t + sec <= now].tail(keep)
    return {"meta": {"tf": tf, "tf_sec": sec, "synthetic": False}, "markers": [],
            "chart": {"t": [int(x) for x in ta.epoch_s(df.index)], "o": df.open.tolist(), "h": df.high.tolist(),
                      "l": df.low.tolist(), "c": df.close.tolist()}}


def zones_at(raw, now):
    """Every zone within $80 of the price, from the bars closed by `now`, with its state and sources."""
    P = {tf: pay(raw, tf, now) for tf in SER}
    zb = K.build(P, now)
    b15 = K.bars(P["15m"])
    a15 = K.atr14(b15)
    srcs = []
    for tf, (_, sec, _) in SER.items():
        srcs += K.swing_sources(K.bars(P[tf]), tf, sec, a15)
    srcs += K.level_sources(b15, a15)
    zs = K.merge(srcs, a15)
    px = zb["price"]["px"]
    rows = []
    for z in zs:
        z.update(K.visits(z, b15))
        if abs(z["mid"] - px) > 80:
            continue
        rows.append({"lo": round(z["lo"], 2), "hi": round(z["hi"], 2), "mid": round(z["mid"], 2), "width": round(z["hi"] - z["lo"], 2),
                     "width_atr": round((z["hi"] - z["lo"]) / zb["atr15"], 2), "state": z["state"], "touches": z["touches"],
                     "rej": z["rejections"], "acc": z["acceptances"], "inside_now": z["inside"], "t_known": int(z["t_known"]),
                     "known": str(ts(z["t_known"]))[:16],
                     "sources": sorted({f"{s['tf']} {s['kind']} {s['price']:.2f} ({str(ts(s['t_known']))[5:16]})" for s in z["sources"]}),
                     "where": "above" if z["lo"] > px else "below" if z["hi"] < px else "at",
                     "dist": round(0 if z["lo"] <= px <= z["hi"] else (z["lo"] - px if z["lo"] > px else px - z["hi"]), 2)})
    rows.sort(key=lambda r: -r["mid"])
    return zb, b15, rows


def m15_events(raw, day="2026-11-18", until="2026-11-18 21:30"):
    """The day's M15 bars that mattered: range >= 1.5 x ATR14, a close through the last confirmed swing, or a swing
    confirmed (pivot 3 / 3, known at the close of the 3rd bar after it)."""
    df = raw["15m"].loc[str(pd.Timestamp(day) - pd.Timedelta(days=3))[:10]:until]
    t, o, h, l, c = (ta.epoch_s(df.index).astype(np.int64), df.open.to_numpy(), df.high.to_numpy(), df.low.to_numpy(), df.close.to_numpy())
    atr = ta.atr(h, l, c, 14)
    ph, pl = ta.pivothigh(h, 3, 3), ta.pivotlow(l, 3, 3)
    last_hi = last_lo = None
    out = []
    t_day = pd.Timestamp(day, tz="UTC").timestamp()
    for k in range(1, len(c)):
        prev_hi, prev_lo = last_hi, last_lo                      # the swings known before this bar
        if k >= 3 and np.isfinite(ph[k]):
            last_hi = (float(ph[k]), int(t[k - 3]))
        if k >= 3 and np.isfinite(pl[k]):
            last_lo = (float(pl[k]), int(t[k - 3]))
        if t[k] < t_day:
            continue
        why = []
        rng = h[k] - l[k]
        if np.isfinite(atr[k - 1]) and rng >= 1.5 * atr[k - 1]:
            why.append(f"range {rng:.2f} = {rng / atr[k - 1]:.1f} ATR")
        if prev_lo and c[k] < prev_lo[0] <= c[k - 1]:
            why.append(f"closed below swing low {prev_lo[0]:.2f} ({str(ts(prev_lo[1]))[11:16]})")
        if prev_hi and c[k] > prev_hi[0] >= c[k - 1]:
            why.append(f"closed above swing high {prev_hi[0]:.2f} ({str(ts(prev_hi[1]))[11:16]})")
        if np.isfinite(pl[k]):
            why.append(f"swing low {pl[k]:.2f} confirmed (pivot bar {str(ts(t[k - 3]))[11:16]})")
        if np.isfinite(ph[k]):
            why.append(f"swing high {ph[k]:.2f} confirmed (pivot bar {str(ts(t[k - 3]))[11:16]})")
        if why:
            out.append({"bar_utc": str(ts(t[k]))[:16], "bar_mt5": str(ts(t[k] + 7200))[:16], "o": round(o[k], 2), "h": round(h[k], 2),
                        "l": round(l[k], 2), "c": round(c[k], 2), "atr": round(float(atr[k - 1]), 2), "why": why})
    return out


def main(argv=None) -> int:
    st_dir, out = (argv or sys.argv[1:])[:2]
    raw = load(st_dir)
    res = {"note": "point in time: each decision uses only bars closed by it; MT5 server time = UTC + 2 in November",
           "operator_zones": [f"{a}-{b}" for a, b in OP], "decisions": []}
    for d in DECISIONS:
        now = int(pd.Timestamp(d, tz="UTC").timestamp()) + 60
        zb, b15, rows = zones_at(raw, now)
        match = []
        for lo, hi in OP:
            ov = [r for r in rows if r["lo"] <= hi and r["hi"] >= lo]
            near = min(rows, key=lambda r: abs(r["mid"] - (lo + hi) / 2)) if rows else None
            match.append({"operator": f"{lo}-{hi}", "overlapping": [f"{r['lo']}-{r['hi']} {r['state']}" for r in ov],
                          "nearest": near and {"zone": f"{near['lo']}-{near['hi']}", "mid_diff": round(near["mid"] - (lo + hi) / 2, 2),
                                               "state": near["state"], "known": near["known"], "sources": near["sources"]}})
        res["decisions"].append({"t_utc": d, "last_closed_15m": str(ts(int(b15["t"][-1]) + 900))[:16], "price": round(zb["price"]["px"], 2),
                                 "atr15": zb["atr15"], "room_up": zb["room_up"], "room_down": zb["room_down"],
                                 "structure": {tf: (s and {k: s.get(k) for k in ("pattern", "stack", "bias")}) for tf, s in zb["structure"].items()},
                                 "zones": rows, "operator_match": match})
    res["m15_events"] = m15_events(raw)
    with open(out, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print("decisions", len(res["decisions"]), "events", len(res["m15_events"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
