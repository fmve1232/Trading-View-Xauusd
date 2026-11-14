"""Independent recomputation (numpy/pandas only; does NOT import quantum) of the engine's chart indicators from the payload
OHLCV, compared with the engine's own published values. Seeds differ from the engine's (the payload starts mid-history), so
recursive indicators are compared after a 1,200-bar warm-up."""
import json, sys
import numpy as np, pandas as pd
p = json.load(open(sys.argv[1])); ch = p["chart"]; tf = p["meta"]["tf"]
t = pd.to_datetime(np.array(ch["t"]), unit="s", utc=True)
o, h, l, c, v = (np.array([np.nan if x is None else x for x in ch[k]], float) for k in ("o", "h", "l", "c", "v"))
n = len(c)
def ema(x, k):
    a = 2 / (k + 1); out = np.full(len(x), np.nan); out[k - 1] = x[:k].mean()
    for i in range(k, len(x)): out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out
def rma(x, k):
    out = np.full(len(x), np.nan); s = np.nanmean(x[1:k + 1]); out[k] = s
    for i in range(k + 1, len(x)): out[i] = (out[i - 1] * (k - 1) + x[i]) / k
    return out
tr = np.maximum.reduce([h - l, np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))]); tr[0] = h[0] - l[0]
atr = rma(tr, 14)
d = np.diff(c, prepend=np.nan); g, ls = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
ag, al = rma(g, 14), rma(ls, 14); rsi = 100 - 100 / (1 + ag / al); rsi = np.where(al == 0, 100.0, rsi)
up, dn = h - np.roll(h, 1), np.roll(l, 1) - l
pdm, mdm = np.where((up > dn) & (up > 0), up, 0.0), np.where((dn > up) & (dn > 0), dn, 0.0); pdm[0] = mdm[0] = np.nan
str_ = rma(tr, 14); pdi, mdi = 100 * rma(pdm, 14) / str_, 100 * rma(mdm, 14) / str_
dx = 100 * np.abs(pdi - mdi) / np.where(pdi + mdi == 0, 1, pdi + mdi)
adx = rma(np.nan_to_num(dx, nan=0.0) if False else dx, 14)
s = pd.Series(c); bbm = s.rolling(20).mean().to_numpy(); bbd = 2 * s.rolling(20).std(ddof=0).to_numpy()
ny = t.tz_convert("America/New_York"); td = (ny + pd.Timedelta(hours=7)).normalize().tz_localize(None)
iso = pd.DatetimeIndex(td).isocalendar(); wk = (iso["year"] * 100 + iso["week"]).to_numpy(); mo = (td.year * 100 + td.month).to_numpy()
def avwap(key):
    out = np.full(n, np.nan); pv = vv = 0.0; first = True
    hlc3 = (h + l + c) / 3
    for i in range(n):
        if i > 0 and key[i] != key[i - 1]: pv = vv = 0.0; first = False
        pv += hlc3[i] * v[i]; vv += v[i]
        out[i] = np.nan if first else (pv / vv if vv > 0 else np.nan)
    return out
tdk = np.asarray(td.strftime("%Y%m%d").astype(int))
vw, wvw, mvw = avwap(tdk), avwap(wk), avwap(mo)
day = pd.DataFrame({"d": tdk, "h": h, "l": l})
dh, dl = day.groupby("d")["h"].max(), day.groupby("d")["l"].min(); days = list(dh.index)
prev = {days[k]: days[k - 1] for k in range(1, len(days))}
pdh = np.array([dh[prev[x]] if x in prev and prev[x] != days[0] else np.nan for x in tdk])
pdl = np.array([dl[prev[x]] if x in prev and prev[x] != days[0] else np.nan for x in tdk])
wkd = pd.DataFrame({"w": wk, "h": h, "l": l}); wh, wl = wkd.groupby("w")["h"].max(), wkd.groupby("w")["l"].min(); wks = list(wh.index)
pw = {wks[k]: wks[k - 1] for k in range(1, len(wks))}
pwh = np.array([wh[pw[x]] if x in pw and pw[x] != wks[0] else np.nan for x in wk])
pwl = np.array([wl[pw[x]] if x in pw and pw[x] != wks[0] else np.nan for x in wk])
W = slice(1200, n) if n > 1300 else slice(max(n - 300, 250), n)
rows = []
for name, mine, key, rnd, sl in (("EMA20", ema(c, 20), "ema20", 2, W), ("EMA100", ema(c, 100), "ema100", 2, W), ("EMA200", ema(c, 200), "ema200", 2, W),
                                 ("RSI14 (Wilder)", rsi, "rsi", 1, W), ("ADX14 (Wilder DMI)", adx, "adx", 1, W),
                                 ("BB basis SMA20", bbm, "bb_mid", 2, slice(20, n)), ("BB upper (+2 sd, population)", bbm + bbd, "bb_up", 2, slice(20, n)),
                                 ("BB lower", bbm - bbd, "bb_lo", 2, slice(20, n)), ("VWAP (NY day)", vw, "vwap", 2, slice(0, n)),
                                 ("Weekly VWAP", wvw, "wvwap", 2, slice(0, n)), ("Monthly VWAP", mvw, "mvwap", 2, slice(0, n)),
                                 ("PDH (NY 17:00 day)", pdh, "pdh", 2, slice(0, n)), ("PDL", pdl, "pdl", 2, slice(0, n)),
                                 ("PWH", pwh, "pwh", 2, slice(0, n)), ("PWL", pwl, "pwl", 2, slice(0, n))):
    eng = np.array([np.nan if x is None else x for x in ch[key]], float)
    a, b = np.round(mine[sl], rnd), eng[sl]
    ok = ~np.isnan(a) & ~np.isnan(b)
    diff = np.abs(a[ok] - b[ok])
    tol = 1.01 * 10 ** -rnd
    rows.append((name, int(ok.sum()), float(diff.max()) if ok.any() else None, int((diff > tol).sum()), "PASS" if ok.sum() > 50 and (diff <= tol).all() else "FAIL" if ok.any() else "UNKNOWN"))
print(f"--- {tf} ({n} bars) ---")
for r in rows: print(f"{r[0]:30s} compared {r[1]:5d}  max|diff| {r[2] if r[2] is None else round(r[2], 4)}  >tol {r[3]:4d}  {r[4]}")
