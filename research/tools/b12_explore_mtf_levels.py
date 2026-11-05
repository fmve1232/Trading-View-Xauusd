"""B12-explore: the operator's multi-timeframe level criteria (2026-11-05), +$22 / -$22 ($1,100 / $1,100 at 0.5 lot).
Rules fixed in this file BEFORE it was run; read-only on a copy of the store; live window 2026-09-09 -> 2026-11-05.

LEVELS at a 15-minute decision close t (only data before t):
  today's high / low so far (New York day, 17:00 roll), previous day H / L, this week's H / L so far, previous week's,
  this month's H / L so far, previous month's, the last COMPLETED 4h, 1h and 30m bars' H / L, and the last three
  confirmed 1h swing highs / lows (5-bar fractal, confirmed 2 bars later).
TREND: +1 / -1 votes from (a) the last completed day's close vs the 20-day average of daily closes, (b) 4h EMA20 vs
  EMA50, (c) 1h EMA20 vs EMA50 (completed bars only). UP if >= 2 of 3 up; DOWN if >= 2 of 3 down.
ENTRY (UP; DOWN mirrored): the 15m bar trades into a support level (low <= L + 2 and low >= L - 6), closes back above it
  (close >= L + 1) in the upper half of its range -> BUY at that close.
VARIANTS: V0 every 15m close in the trend direction (trend only); V1 the level rejection with the trend; V2 V1 + a
  confluence of >= 2 levels within $3; V3 V2 + room: no MAJOR level (D / PD / W / PW / M / PM H-L) within $22 the
  other way; V4 V3 + volume: the rejection bar's COMEX GC volume >= 1.2 x the median of the previous 20 bars;
  C1 the V1 rejection AGAINST the trend (control).
ONE entry per level per New York day per variant. OUTCOME on the 5-minute path from the next bar, 288 bars (one
trading day): +22 before -22 (a bar touching both is a loss unless it opened beyond the target); also +10 and +20
before -22. Direction-matched random 15m closes as the baseline. Cost $13 a trade (0.26 per oz).
"""
import json
import math
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), "..", ".."))
from quantum.data import sources, store as ST  # noqa: E402

STORE, OUT = sys.argv[1], sys.argv[2]
NY = "America/New_York"
TP, SL, H = 22.0, 22.0, 288
COST = 0.26

x5 = sources.trading_week_only(sources.drop_offgrid(ST.load(STORE, "XAU/USD_5m")))
x5 = sources.repair_reopen(x5, 300)
gc5 = ST.load(STORE, "GC=F_5m")
print("5m", len(x5), x5.index[0], x5.index[-1], "| GC", None if gc5 is None else len(gc5))


def ohlc(df, rule):
    return df.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


m15 = ohlc(x5, "15min")
nyt = m15.index.tz_convert(NY) + pd.Timedelta(hours=7)              # the trading-day clock (17:00 New York roll)
day = pd.Index(nyt.date)
week = pd.Index([d - pd.Timedelta(days=d.weekday()) for d in pd.to_datetime(nyt.date)])
month = pd.Index(nyt.strftime("%Y-%m"))
gvol = None
if gc5 is not None and "volume" in gc5:
    gvol = gc5["volume"].resample("15min", label="left", closed="left").sum().reindex(m15.index)


def period_levels(key):
    """(high so far BEFORE this bar, low so far before this bar, previous period high, previous period low)."""
    hi, lo = m15["high"], m15["low"]
    g = pd.Series(key, index=m15.index)
    so_far_h = hi.groupby(g.values).cummax().groupby(g.values).shift(1)
    so_far_l = lo.groupby(g.values).cummin().groupby(g.values).shift(1)
    per = pd.DataFrame({"h": hi.groupby(g.values).max(), "l": lo.groupby(g.values).min()})
    prev = per.shift(1)
    return so_far_h.to_numpy(), so_far_l.to_numpy(), prev["h"].reindex(g.values).to_numpy(), prev["l"].reindex(g.values).to_numpy()


DH, DL, PDH, PDL = period_levels(day)
WH, WL, PWH, PWL = period_levels(week)
MH, ML, PMH, PML = period_levels(month)
t_close = m15.index + pd.Timedelta(minutes=15)


def last_completed(rule, offset=None):
    b = x5.resample(rule, label="left", closed="left", offset=offset).agg({"high": "max", "low": "min", "close": "last"}).dropna()
    done = b.index + pd.Timedelta(rule)
    pos = np.searchsorted(done.values, t_close.values, side="right") - 1    # last bar closed at or before t
    ok = pos >= 0
    hh = np.where(ok, b["high"].to_numpy()[np.maximum(pos, 0)], np.nan)
    ll = np.where(ok, b["low"].to_numpy()[np.maximum(pos, 0)], np.nan)
    return hh, ll, b, done, pos


H4H, H4L, b4, d4, p4 = last_completed("4h", "2h")        # 22:00 / 02:00 ... UTC grid, close to the NY 17:00 session in winter
H1H, H1L, b1, d1, p1 = last_completed("1h")
M30H, M30L, _, _, _ = last_completed("30min")


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def trend_votes():
    dcl = m15["close"].groupby(day.values).last()
    sma20 = dcl.rolling(20, min_periods=20).mean()
    dvote = np.sign(dcl - sma20).shift(1)                    # the last COMPLETED day
    v_d = dvote.reindex(day.values).to_numpy()
    e4 = np.sign(ema(b4["close"], 20) - ema(b4["close"], 50)).to_numpy()
    e1 = np.sign(ema(b1["close"], 20) - ema(b1["close"], 50)).to_numpy()
    v4 = np.where(p4 >= 0, e4[np.maximum(p4, 0)], np.nan)
    v1 = np.where(p1 >= 0, e1[np.maximum(p1, 0)], np.nan)
    s = np.nan_to_num(v_d) + np.nan_to_num(v4) + np.nan_to_num(v1)
    return np.where(s >= 1, 1, np.where(s <= -1, -1, 0)), s


trend, tscore = trend_votes()


def swings(b, done, n_keep=3):
    """Last n confirmed 1h fractal highs / lows known at each 15m close."""
    hh, ll = b["high"].to_numpy(), b["low"].to_numpy()
    ph = [(done[j + 2], hh[j]) for j in range(2, len(b) - 2) if hh[j] == max(hh[j - 2:j + 3])]
    pl = [(done[j + 2], ll[j]) for j in range(2, len(b) - 2) if ll[j] == min(ll[j - 2:j + 3])]
    out_h, out_l = [], []
    ih = il = 0
    kh, kl = [], []
    for t in t_close:
        while ih < len(ph) and ph[ih][0] <= t:
            kh.append(ph[ih][1]); ih += 1
        while il < len(pl) and pl[il][0] <= t:
            kl.append(pl[il][1]); il += 1
        out_h.append(kh[-n_keep:]); out_l.append(kl[-n_keep:])
    return out_h, out_l


SWH, SWL = swings(b1, d1)
O, Hh, Ll, C = (m15[k].to_numpy() for k in ("open", "high", "low", "close"))
n = len(m15)
MAJOR = ("DH", "DL", "PDH", "PDL", "WH", "WL", "PWH", "PWL", "MH", "ML", "PMH", "PML")


def levels_at(k):
    lv = {"DH": DH[k], "DL": DL[k], "PDH": PDH[k], "PDL": PDL[k], "WH": WH[k], "WL": WL[k], "PWH": PWH[k], "PWL": PWL[k],
          "MH": MH[k], "ML": ML[k], "PMH": PMH[k], "PML": PML[k], "4H": H4H[k], "4L": H4L[k], "1H": H1H[k], "1L": H1L[k],
          "30H": M30H[k], "30L": M30L[k]}
    for i, v in enumerate(SWH[k]):
        lv[f"SH{i}"] = v
    for i, v in enumerate(SWL[k]):
        lv[f"SL{i}"] = v
    return {a: float(b) for a, b in lv.items() if b is not None and np.isfinite(b)}


def entries():
    ev = {v: [] for v in ("V0", "V1", "V2", "V3", "V4", "C1")}
    seen = {v: set() for v in ev}
    med = gvol.rolling(20, min_periods=10).median().shift(1).to_numpy() if gvol is not None else None
    vol = gvol.to_numpy() if gvol is not None else None
    for k in range(60, n):
        d = trend[k]
        if d != 0:
            ev["V0"].append((k, d))
        lv = levels_at(k)
        rng = Hh[k] - Ll[k]
        if rng <= 0:
            continue
        for side in (1, -1):
            for name, L in lv.items():
                if side == 1:
                    touch = Ll[k] <= L + 2 and Ll[k] >= L - 6 and C[k] >= L + 1 and (C[k] - Ll[k]) >= 0.5 * rng and L < C[k]
                else:
                    touch = Hh[k] >= L - 2 and Hh[k] <= L + 6 and C[k] <= L - 1 and (Hh[k] - C[k]) >= 0.5 * rng and L > C[k]
                if not touch:
                    continue
                key = (day[k], round(L, 1), side)
                with_trend = side == d
                if not with_trend:
                    if d != 0 and key not in seen["C1"]:
                        seen["C1"].add(key); ev["C1"].append((k, side))
                    continue
                if key not in seen["V1"]:
                    seen["V1"].add(key); ev["V1"].append((k, side))
                conf = sum(1 for v in lv.values() if abs(v - L) <= 3.0)
                if conf < 2:
                    continue
                if key not in seen["V2"]:
                    seen["V2"].add(key); ev["V2"].append((k, side))
                opp = [v for a, v in lv.items() if a in MAJOR and ((v > C[k]) if side == 1 else (v < C[k]))]
                room = min((abs(v - C[k]) for v in opp), default=1e9)
                if room < TP:
                    continue
                if key not in seen["V3"]:
                    seen["V3"].add(key); ev["V3"].append((k, side))
                if vol is not None and np.isfinite(med[k]) and med[k] > 0 and vol[k] >= 1.2 * med[k] and key not in seen["V4"]:
                    seen["V4"].add(key); ev["V4"].append((k, side))
    for v in ev:                                     # one entry per bar per variant
        u, out = set(), []
        for k, s in ev[v]:
            if (k, s) not in u:
                u.add((k, s)); out.append((k, s))
        ev[v] = out
    return ev


t5 = (x5.index.tz_convert("UTC").as_unit("s").asi8).astype(np.int64)
o5, h5, l5 = (x5[k].to_numpy() for k in ("open", "high", "low"))
tc15 = (t_close.tz_convert("UTC").as_unit("s").asi8).astype(np.int64)


def race(k, d, a):
    j = int(np.searchsorted(t5, tc15[k]))
    if j + H > len(t5) or t5[j] - tc15[k] > 3 * 86400:
        return None
    e = C[k]
    hh, ll, oo = h5[j:j + H], l5[j:j + H], o5[j:j + H]
    fav = (hh - e) if d > 0 else (e - ll)
    adv = (e - ll) if d > 0 else (hh - e)
    ia = np.flatnonzero(fav >= a - 1e-9); ib = np.flatnonzero(adv >= SL - 1e-9)
    ia = ia[0] if len(ia) else H; ib = ib[0] if len(ib) else H
    if ia == H and ib == H:
        return None
    if ia < ib:
        return 1
    if ib < ia:
        return 0
    return int((oo[ia] - e) * d >= a - 1e-9)


def wilson(k, m, z=1.959964):
    if m == 0:
        return (math.nan, math.nan)
    p = k / m; dd = 1 + z * z / m; c = (p + z * z / (2 * m)) / dd
    h = z * math.sqrt(p * (1 - p) / m + z * z / (4 * m * m)) / dd
    return (c - h, c + h)


ev = entries()
rk = np.arange(60, n, 2)
rnd = {}
for a in (TP, 10.0, 20.0):
    for s in (1, -1):
        r = [race(k, s, a) for k in rk]
        r = [x for x in r if x is not None]
        rnd[(a, s)] = sum(r) / len(r)
res = {"window": [str(m15.index[0]), str(m15.index[-1])], "random": {f"{a}:{s}": v for (a, s), v in rnd.items()}, "variants": {}}
for v, lst in ev.items():
    row = {"entries": len(lst)}
    for a in (TP, 10.0, 20.0):
        out = [(race(k, s, a), s) for k, s in lst]
        out = [(r, s) for r, s in out if r is not None]
        m = len(out); w = sum(r for r, _ in out)
        nl = sum(1 for _, s in out if s > 0); ns = m - nl
        mix = (nl * rnd[(a, 1)] + ns * rnd[(a, -1)]) / m if m else math.nan
        z = (w / m - mix) / math.sqrt(mix * (1 - mix) / m) if m and 0 < mix < 1 else math.nan
        lo, hi = wilson(w, m)
        row[f"T{int(a)}"] = {"n": m, "long": nl, "short": ns, "rate": w / m if m else None, "wilson": [lo, hi],
                             "random_same_mix": mix, "z": z}
    if row["T22"]["n"]:
        r22 = row["T22"]["rate"]
        row["usd_per_trade_0p5lot"] = r22 * (1100 - 13) - (1 - r22) * (1100 + 13)
    res["variants"][v] = row
json.dump(res, open(OUT, "w"), indent=1, default=lambda x: None if x != x else float(x))
print(f"window {res['window']}; random +22 first: long {rnd[(TP, 1)]:.3f} short {rnd[(TP, -1)]:.3f}")
for v, row in res["variants"].items():
    t = row["T22"]
    print(f"{v}: entries {row['entries']:5d} decided {t['n']:5d} (L{t['long']} S{t['short']}) +22 first {100*(t['rate'] or 0):5.1f}% "
          f"[{100*t['wilson'][0]:4.1f}-{100*t['wilson'][1]:4.1f}] random {100*t['random_same_mix']:5.1f} z {t['z']:+5.2f} | "
          f"+10 first {100*(row['T10']['rate'] or 0):4.1f}% (rand {100*row['T10']['random_same_mix']:4.1f}) | "
          f"+20 first {100*(row['T20']['rate'] or 0):4.1f}% | $/trade {row.get('usd_per_trade_0p5lot', float('nan')):+7.0f}")
