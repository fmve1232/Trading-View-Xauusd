"""Hypothesis test: the engine's PWH/PWL omit the first bar of every trading day that is not the first day of the week."""
import json, sys
import numpy as np, pandas as pd
for path in sys.argv[1:]:
    p = json.load(open(path)); ch = p["chart"]
    t = pd.to_datetime(np.array(ch["t"]), unit="s", utc=True)
    h, l = np.array(ch["h"], float), np.array(ch["l"], float)
    ny = t.tz_convert("America/New_York"); td = (ny + pd.Timedelta(hours=7)).normalize().tz_localize(None)
    iso = pd.DatetimeIndex(td).isocalendar(); wk = (iso["year"] * 100 + iso["week"]).to_numpy(); dk = np.asarray(td.strftime("%Y%m%d").astype(int))
    first_of_day = np.r_[True, dk[1:] != dk[:-1]]; first_of_week = np.r_[True, wk[1:] != wk[:-1]]
    eng_h, eng_l = np.array([np.nan if x is None else x for x in ch["pwh"]]), np.array([np.nan if x is None else x for x in ch["pwl"]])
    for label, excl in (("all bars (correct definition)", np.zeros(len(h), bool)), ("first bar of non-week-start days excluded", first_of_day & ~first_of_week)):
        df = pd.DataFrame({"w": wk, "h": np.where(excl, np.nan, h), "l": np.where(excl, np.nan, l)})
        wh, wl = df.groupby("w")["h"].max(), df.groupby("w")["l"].min(); ws = list(wh.index); prev = {ws[k]: ws[k - 1] for k in range(1, len(ws))}
        mh = np.array([wh[prev[x]] if x in prev and prev[x] != ws[0] else np.nan for x in wk]); ml = np.array([wl[prev[x]] if x in prev and prev[x] != ws[0] else np.nan for x in wk])
        ok = ~np.isnan(mh) & ~np.isnan(eng_h)
        print(f"{p['meta']['tf']:4s} {label:45s} PWH bars differing {int((np.abs(mh[ok]-eng_h[ok]) > 0.006).sum()):4d} / {int(ok.sum())}   PWL {int((np.abs(ml[ok]-eng_l[ok]) > 0.006).sum()):4d}")
    # weeks affected under the correct definition
    df = pd.DataFrame({"w": wk, "h": h, "l": l, "excl": first_of_day & ~first_of_week})
    aff = 0; tot = 0; mx = 0.0
    for w, g in df.groupby("w"):
        tot += 1; full_h, part_h = g["h"].max(), g.loc[~g["excl"], "h"].max(); full_l, part_l = g["l"].min(), g.loc[~g["excl"], "l"].min()
        if full_h != part_h or full_l != part_l: aff += 1; mx = max(mx, full_h - part_h, part_l - full_l)
    print(f"     weeks whose true high or low is set by a day's first bar: {aff} of {tot} (largest understatement ${mx:.2f})")
