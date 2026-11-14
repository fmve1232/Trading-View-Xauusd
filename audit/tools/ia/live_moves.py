"""Live (forward) per-strategy movement statistics, labelled independently on raw 5m spot bars: +$X before -$Y with the
conservative same-bar rule, at horizons of 1 and 3 trading days; MFE / MAE; Wilson 95% intervals; non-overlapping counts;
a same-period, same-direction-mix random-entry baseline. Read-only."""
import glob, json, math, os, sys
from collections import Counter, defaultdict
import numpy as np, pandas as pd
md, fl, outp = sys.argv[1], sys.argv[2], sys.argv[3]
fs = sorted(glob.glob(os.path.join(md, "XAU_USD_5m", "*.csv")))
b = pd.concat([pd.read_csv(f) for f in fs]); b.index = pd.to_datetime(b.pop("datetime"), utc=True)
b = b[~b.index.duplicated(keep="last")].sort_index()
ny = b.index.tz_convert("America/New_York"); wd, hr = ny.day_of_week, ny.hour
b = b[~((wd == 5) | ((wd == 4) & (hr >= 17)) | ((wd == 6) & (hr < 18)) | ((wd <= 3) & (hr == 17)))]
T = b.index.as_unit("s").asi8.astype(np.int64); O, H, L, C = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
def race(e, d, t0, tp, sl, nbars):
    k0 = np.searchsorted(T, t0)
    for k in range(k0, min(k0 + nbars, len(T))):
        fav = (H[k] - e) if d > 0 else (e - L[k]); adv = (e - L[k]) if d > 0 else (H[k] - e)
        a, z = fav >= tp - 1e-9, adv >= sl - 1e-9
        if a or z:
            if a and not z: return "W", k
            if a and z: return ("W" if (O[k] - e) * d >= tp else "L"), k
            return "L", k
    return ("U" if k0 + nbars <= len(T) else "OPEN"), None
def excur(e, d, t0, nbars):
    k0 = np.searchsorted(T, t0); k1 = min(k0 + nbars, len(T))
    if k1 <= k0: return None, None
    return (float(np.max(H[k0:k1] - e)) if d > 0 else float(np.max(e - L[k0:k1])), float(np.max(e - L[k0:k1])) if d > 0 else float(np.max(H[k0:k1] - e)))
def wilson(k, n):
    if n == 0: return (None, None)
    p = k / n; z = 1.96; c = (p + z * z / (2 * n)) / (1 + z * z / n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (round(100 * (c - h), 1), round(100 * (c + h), 1))
def session(t):
    h = pd.Timestamp(t, unit="s", tz="UTC").tz_convert("America/New_York").hour
    return "Asia" if (h >= 18 or h < 3) else "London" if h < 8 else "NY overlap" if h < 12 else "NY pm"
G = json.load(open(os.path.join(fl, "research_forward", "SETUP-LIVE.json")))["setups"]
streams = {
    "A. BREAKOUT setups (15m, SETUP-LIVE)": [dict(e=s["entry"], d=s["dir"], t=s["t_dec"], tf=s["tf"]) for s in G if s["kind"] == "BREAKOUT"],
    "A. BREAKOUT setups, all 4 confirmations": [dict(e=s["entry"], d=s["dir"], t=s["t_dec"], tf=s["tf"]) for s in G if s["kind"] == "BREAKOUT" and s.get("confirmed")],
    "A. 4H BREAKOUT (B18 rule, SETUP-LIVE)": [dict(e=s["entry"], d=s["dir"], t=s["t_dec"], tf=s["tf"]) for s in G if s["kind"] == "4H BREAKOUT"],
    "B. SWEEP setups (15m, SETUP-LIVE)": [dict(e=s["entry"], d=s["dir"], t=s["t_dec"], tf=s["tf"]) for s in G if s["kind"] == "SWEEP"],
    "B. SWEEP setups, all 4 confirmations": [dict(e=s["entry"], d=s["dir"], t=s["t_dec"], tf=s["tf"]) for s in G if s["kind"] == "SWEEP" and s.get("confirmed")],
    "B. Liquidity grabs (engine SWEEP, B9-GRAB-FWD)": [dict(e=x["entry"], d=x["dir"], t=x["t_close"], tf=x["tf"]) for x in json.load(open(os.path.join(fl, "research_forward", "B9-GRAB-FWD.json")))["trades"]],
    "Engine signals (B15-ENGINE-FWD, phone stream)": [dict(e=x["entry"], d=x["dir"], t=x["t_dec"], tf=x["tf"]) for x in json.load(open(os.path.join(fl, "research_forward", "B15-ENGINE-FWD.json")))["trades"]],
}
other_kinds = Counter(s["kind"] for s in G)
GEOM = [(10, 13), (13, 13), (15, 13), (20, 13), (10, 10), (15, 15), (20, 20)]
res = {"kinds_in_setup_live": dict(other_kinds), "streams": {}}
t_lo = min(x["t"] for v in streams.values() for x in v); t_hi = T[-1] - 3 * 86400
rng = np.random.default_rng(20261114)
for name, xs in streams.items():
    row = {"n_raw": len(xs), "period": [str(pd.Timestamp(min(x["t"] for x in xs), unit="s"))[:16], str(pd.Timestamp(max(x["t"] for x in xs), unit="s"))[:16]] if xs else None,
           "dir": dict(Counter("BUY" if x["d"] > 0 else "SELL" for x in xs)), "tf": dict(Counter(x["tf"] for x in xs))}
    for hz, nb in (("1d", 288), ("3d", 864)):
        for tp, sl in GEOM:
            r = [race(x["e"], x["d"], x["t"], tp, sl, nb) for x in xs]
            w, l_, u, op = (sum(1 for a, _ in r if a == s) for s in ("W", "L", "U", "OPEN"))
            row[f"+{tp}/-{sl} {hz}"] = {"win": w, "loss": l_, "unresolved": u, "open": op, "rate": round(100 * w / (w + l_), 1) if w + l_ else None, "wilson95": wilson(w, w + l_)}
    # non-overlapping (+13/-13, 1d): skip a trade that starts before the previous counted trade resolved
    r = sorted(((x["t"], race(x["e"], x["d"], x["t"], 13, 13, 288), x) for x in xs), key=lambda z: z[0]); busy = -1; k = w = 0
    for t0, (a, kk), x in r:
        if t0 < busy or a not in ("W", "L"): continue
        k += 1; w += a == "W"; busy = T[kk] if kk is not None else busy
    row["+13/-13 1d non-overlapping"] = {"n": k, "win": w, "rate": round(100 * w / k, 1) if k else None, "wilson95": wilson(w, k)}
    ex = [excur(x["e"], x["d"], x["t"], 288) for x in xs]; ex = [e for e in ex if e[0] is not None]
    if ex:
        mf, ma = np.array([e[0] for e in ex]), np.array([e[1] for e in ex])
        row["MFE_1d_median"], row["MAE_1d_median"] = round(float(np.median(mf)), 2), round(float(np.median(ma)), 2)
        row["share_MFE_ge_10_with_MAE_lt_13"] = round(100 * float(np.mean((mf >= 10) & (ma < 13))), 1)
    by_s = defaultdict(lambda: [0, 0])
    for x in xs:
        a, _ = race(x["e"], x["d"], x["t"], 13, 13, 288)
        if a in ("W", "L"): by_s[session(x["t"])][0] += a == "W"; by_s[session(x["t"])][1] += 1
    row["+13/-13 1d by session"] = {s: f"{v[0]}/{v[1]}" for s, v in sorted(by_s.items())}
    # random baseline: entries at random 15m closes in the same window, same direction mix, same count x 40
    if xs:
        lo_, hi_ = min(x["t"] for x in xs), max(x["t"] for x in xs)
        cand = T[(T >= lo_) & (T <= max(hi_, lo_ + 86400)) & (T % 900 == 0)]
        dirs = [x["d"] for x in xs]; ww = ll = 0
        for _ in range(40):
            for d, t0 in zip(dirs, rng.choice(cand, len(dirs))):
                k0 = np.searchsorted(T, t0) - 1; e = C[k0]
                a, _ = race(e, d, int(t0), 13, 13, 288)
                ww += a == "W"; ll += a == "L"
        row["random same-mix +13/-13 1d"] = {"rate": round(100 * ww / (ww + ll), 1), "n": ww + ll, "window": "the stream's own first-to-last trigger period"}
        # exact one-sided binomial: P(X >= wins | p = random rate)
        r13 = row["+13/-13 1d"]; n_, k_ = r13["win"] + r13["loss"], r13["win"]; p0 = ww / (ww + ll)
        row["p_vs_random_one_sided"] = round(sum(math.comb(n_, i) * p0 ** i * (1 - p0) ** (n_ - i) for i in range(k_, n_ + 1)), 4) if n_ else None
    res["streams"][name] = row
json.dump(res, open(outp, "w"), indent=1, default=str)
print("SETUP-LIVE kinds:", dict(other_kinds))
hdr = ["n_raw", "+10/-13 1d", "+13/-13 1d", "+15/-13 1d", "+20/-13 1d", "+10/-10 1d", "+15/-15 1d", "+20/-20 1d"]
for name, row in res["streams"].items():
    def f(k):
        v = row[k]; return f"{v['win']}/{v['win']+v['loss']}={v['rate']}% {v['wilson95']}" + (f" U{v['unresolved']}" if v['unresolved'] else "") if isinstance(v, dict) else str(v)
    print(f"\n{name}  n={row['n_raw']} {row['period']} {row['dir']} {row['tf']}")
    for k in hdr[1:]: print(f"   {k:12s} {f(k)}")
    print(f"   +13/-13 3d  {f('+13/-13 3d')} | non-overlap {row['+13/-13 1d non-overlapping']} | random same-period same-mix {row.get('random same-mix +13/-13 1d', {}).get('rate')}% p={row.get('p_vs_random_one_sided')}")
    print(f"   MFE/MAE 1d median {row.get('MFE_1d_median')}/{row.get('MAE_1d_median')} | MFE>=10 with MAE<13: {row.get('share_MFE_ge_10_with_MAE_lt_13')}% | by session {row['+13/-13 1d by session']}")
