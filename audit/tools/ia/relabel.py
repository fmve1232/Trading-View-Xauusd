"""Independent re-labelling of recorded forward trades from raw 5m spot bars (no quantum import): TP-before-SL with the
conservative same-bar rule (both touched -> loss, unless the bar OPENED beyond the target), MFE/MAE, time to +$10/+$15/+$20,
and horizon sensitivity. Closed-market quotes dropped by an independent rule (Fri 17:00 - Sun 18:00 NY, daily 17:00-18:00 NY)."""
import glob, json, os, sys
import numpy as np, pandas as pd
md, rec_path, key = sys.argv[1], sys.argv[2], sys.argv[3]
fs = sorted(glob.glob(os.path.join(md, "XAU_USD_5m", "*.csv")))
b = pd.concat([pd.read_csv(f) for f in fs]); b.index = pd.to_datetime(b.pop("datetime"), utc=True)
b = b[~b.index.duplicated(keep="last")].sort_index()
ny = b.index.tz_convert("America/New_York"); wd, hr = ny.day_of_week, ny.hour
shut = (wd == 5) | ((wd == 4) & (hr >= 17)) | ((wd == 6) & (hr < 18)) | ((wd <= 3) & (hr == 17))
b = b[~shut]
T = (b.index.as_unit("s").asi8).astype(np.int64); O, H, L = (b[k].to_numpy(float) for k in ("open", "high", "low"))
rec = json.load(open(rec_path)); trades = rec[key] if key != "-" else rec
out = []
for tr in trades:
    d, e, t0 = int(tr["dir"]), float(tr["entry"]), int(tr["t_dec"])
    k0 = np.searchsorted(T, t0)            # first 5m bar opening at or after the decision
    res, tres, mfe, mae, hit = None, None, 0.0, 0.0, {}
    for k in range(k0, min(k0 + 864, len(T))):          # 3 days of 5m bars at most
        fav = (H[k] - e) if d > 0 else (e - L[k]); adv = (e - L[k]) if d > 0 else (H[k] - e)
        ofav = (O[k] - e) * d
        for x in (10, 15, 20):
            if x not in hit and fav >= x: hit[x] = (T[k] - t0) / 60
        tp, sl = fav >= 13 - 1e-9, adv >= 13 - 1e-9
        if res is None and (tp or sl):
            res = "TP" if (tp and not sl) or (tp and sl and ofav >= 13) else "SL"; tres = int(T[k])
        if res is None:
            mfe, mae = max(mfe, fav), max(mae, adv)
        if res is not None and len(hit) == 3: break
    out.append({"id": tr.get("id"), "tf": tr.get("tf"), "dir": d, "rec": tr.get("result"), "mine": res, "t_res_rec": tr.get("t_res"), "t_res_mine": tres,
                "mfe_before_res": round(mfe, 2), "mae_before_res": round(mae, 2), "min_to": {x: round(v) for x, v in hit.items()}})
agree = sum(1 for r in out if r["rec"] == r["mine"]); tagree = sum(1 for r in out if r["t_res_rec"] == r["t_res_mine"])
print(f"{key}: {len(out)} trades; result agrees {agree}/{len(out)}; resolution time agrees {tagree}/{len(out)}")
for r in out:
    if r["rec"] != r["mine"] or r["t_res_rec"] != r["t_res_mine"]: print("  DIFF", r)
dec = [r for r in out if r["mine"] in ("TP", "SL")]
for x in (10, 15, 20):
    m = [r["min_to"].get(x) for r in dec]
    reached = [v for v in m if v is not None]
    print(f"  +${x}: reached at any time within 3 days {len(reached)}/{len(dec)}; median minutes {np.median(reached) if reached else None}")
json.dump(out, open(sys.argv[4], "w"), indent=1)
