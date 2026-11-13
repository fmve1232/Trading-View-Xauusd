"""Stage-2 verification of the cross-asset forecasting comparisons (read-only).

  python3 -I audit/tools/v2_xasset.py <research-data dir> <market-data store dir> <forward-ledger dir> <out dir>

Re-runs the 12 predictive comparisons of audit/tools/xasset_corr.py with a STRICT cut: no bar, base price or regime
threshold from before 2026-01-01 (the stage-1 run used the 31 Dec 2025 close as the base of each series' first return,
and a VIX median over 2016-2025 for the VIX regime split; both are removed here). For every feed and horizon it prints
the exact out-of-sample window, the rows per month, both baselines, the Diebold-Mariano computation in full, and three
sensitivities:
  * delay 15 min (as stage 1) vs 60 min between the feed's bar close and the start of gold's forecast window;
  * FINAL data (the store as of 13 Nov) vs FIRST-SEEN data for the feeds, on 3 Oct .. 13 Nov, the only span the
    forward ledger's revision log covers (revisions/<series>: each revised bar's earlier value; the earliest one is the
    value first stored after the bar closed); gold uses its own revision log the same way;
  * the walk-forward start: 3 training months (stage 1) vs 5.
Gold's price is Twelve Data spot only. Nothing here reads the sealed spans."""
from __future__ import annotations

import csv
import json
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xasset_corr as X  # noqa: E402

RD, STORE, LED, OUT = sys.argv[1:5]
CUT = pd.Timestamp("2026-01-01", tz="UTC")
FS0 = pd.Timestamp("2026-10-03", tz="UTC")           # the revision log starts with the manifest (first run 2026-10-03)


def first_seen(series_folder: str) -> dict:
    """{bar_open: earliest recorded old close} from the forward ledger's revision log (closed-bar revisions only)."""
    d = os.path.join(LED, "revisions", series_folder)
    out = {}
    if not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d)):
        for r in csv.reader(open(os.path.join(d, f))):
            if len(r) != 11 or r[0] == "bar_open" or r[10] != "changed":
                continue
            try:
                t, run, old = pd.Timestamp(r[0]), r[1], float(r[5])
            except ValueError:
                continue
            if t not in out or run < out[t][0]:
                out[t] = (run, old)
    return {t: v for t, (_, v) in out.items()}


def dm(e_own, e_full, lags):
    d = e_own - e_full
    dm_ = d - d.mean()
    lr = float(np.sum(dm_ ** 2)) + 2 * sum((1 - l / (lags + 1)) * float(np.sum(dm_[l:] * dm_[:-l])) for l in range(1, lags + 1))
    se = math.sqrt(lr) / len(d)
    t = float(d.mean() / se)
    return {"mean_loss_diff_own_minus_full": float(d.mean()), "long_run_var_sum": lr, "se": se, "t": t,
            "p_one_sided_full_better": float(1 - X.stats.norm.cdf(t)), "nw_lags": lags}


def study(px, store, delay_min=15, min_months=3, window=(CUT, None), fs=None):
    out = {}
    for name, folder in X.SERIES.items():
        df = X.load(os.path.join(store, folder))
        if fs is not None and fs.get(folder):
            df = df.copy()
            rep = {t: v for t, v in fs[folder].items() if t in df.index}
            if rep:
                df.loc[list(rep), "close"] = list(rep.values())
        df = df[df.index >= CUT]                                  # strict: no base bar before the cut
        sp = X.spans(df)
        sp = sp[sp["start"] >= window[0]]
        if window[1] is not None:
            sp = sp[sp["start"] < window[1]]
        sp = sp.reset_index(drop=True)
        assert X.sealed_free(pd.DatetimeIndex(sp["start"])) and (sp["start"] >= CUT).all()
        g0, g1 = X.p_at(px, pd.DatetimeIndex(sp["start"])), X.p_at(px, pd.DatetimeIndex(sp["end"]))
        sp["g"] = np.log(g1 / g0)
        f0 = X.ceil15(pd.DatetimeIndex(sp["end"]) + pd.Timedelta(minutes=delay_min))
        sp["p_fwd0"] = X.p_at(px, f0)
        sp["g_f1"] = np.log(X.p_at(px, f0 + X.H) / sp["p_fwd0"])
        sp["g_f4"] = np.log(X.p_at(px, f0 + 4 * X.H) / sp["p_fwd0"])
        sp["g_lag"] = np.log(sp["p_fwd0"] / X.p_at(px, f0 - X.H))
        sp = sp.dropna(subset=["r", "g"]).reset_index(drop=True)
        res = {"spans": len(sp), "first_span": str(sp["start"].iloc[0])[:16], "last_span": str(sp["start"].iloc[-1])[:16],
               "pearson_1h": X.pear(sp["r"].to_numpy(), sp["g"].to_numpy())}
        for hz, col, lags in (("1h", "g_f1", 1), ("4h", "g_f4", 5)):
            dfp = sp.dropna(subset=[col, "g_lag", "p_fwd0"]).reset_index(drop=True)
            mods = {k: X.walk_forward(dfp, col, xs, min_months=min_months) for k, xs in (("drift", []), ("own", ["g_lag"]), ("full", ["g_lag", "r"]))}
            ok = mods["drift"]["ok"] & mods["own"]["ok"] & mods["full"]["ok"]
            y = dfp[col].to_numpy()[ok]
            pr = {k: m["pred"][ok] for k, m in mods.items()}
            mon = dfp["start"][ok].dt.tz_convert(None).dt.to_period("M").astype(str).value_counts().sort_index()
            nz = y != 0
            slope, tt, pp = X.nw_slope(dfp["r"].to_numpy(), dfp[col].to_numpy(), lags)
            res[hz] = {"rows": len(dfp), "oos_rows": int(ok.sum()),
                       "oos_first": str(dfp["start"][ok].iloc[0])[:16] if ok.any() else None,
                       "oos_last": str(dfp["start"][ok].iloc[-1])[:16] if ok.any() else None,
                       "oos_rows_by_month": mon.to_dict(), "train_months_before_first_oos": min_months,
                       "mse": {k: float(np.mean((y - v) ** 2)) for k, v in pr.items()},
                       "mse_zero_forecast": float(np.mean(y ** 2)),
                       "oos_r2_full_vs_own": 1 - float(np.sum((y - pr["full"]) ** 2)) / float(np.sum((y - pr["own"]) ** 2)),
                       "oos_r2_full_vs_zero": 1 - float(np.sum((y - pr["full"]) ** 2)) / float(np.sum(y ** 2)),
                       "hit": {k: float(np.mean(np.sign(v[nz]) == np.sign(y[nz]))) for k, v in pr.items()},
                       "up_share": float(np.mean(y[nz] > 0)),
                       "dm": dm((y - pr["own"]) ** 2, (y - pr["full"]) ** 2, lags),
                       "in_sample_slope": {"slope": slope, "nw_t": tt, "p": pp}}
        out[name] = res
    ps = [(n, h, out[n][h]["in_sample_slope"]["p"]) for n in out for h in ("1h", "4h")] + \
         [(n, h + "_dm", out[n][h]["dm"]["p_one_sided_full_better"]) for n in out for h in ("1h", "4h")]
    adj = X.holm([p for *_, p in ps])
    for (n, h, _), a in zip(ps, adj):
        if h.endswith("_dm"):
            out[n][h[:-3]]["dm"]["p_holm"] = float(a)
        else:
            out[n][h]["in_sample_slope"]["p_holm"] = float(a)
    return out


def xau_px(first_seen_xau=None):
    x15 = X.load(os.path.join(RD, "TD_XAU_USD_15min"))
    s15 = X.load(os.path.join(STORE, "XAU_USD_15m"))
    x = pd.concat([x15, s15[s15.index > x15.index[-1]]]).sort_index()
    if first_seen_xau:
        rep = {t: v for t, v in first_seen_xau.items() if t in x.index}
        if rep:
            x = x.copy()
            x.loc[list(rep), "close"] = list(rep.values())
    x = x[x.index >= CUT - pd.Timedelta(minutes=15)]          # the bar ENDING at 00:00 on 1 Jan carries the 00:00 price
    return X.xau_price(x), x15, s15


def line(tag, r):
    out = []
    for n, v in r.items():
        for h in ("1h", "4h"):
            q = v[h]
            out.append(f"{tag:22s} {n:13s} {h} OOS {q['oos_first']}..{q['oos_last']} n {q['oos_rows']:5d} | R2 full/own {q['oos_r2_full_vs_own']:+.4f}"
                       f" full/zero {q['oos_r2_full_vs_zero']:+.4f} | DM t {q['dm']['t']:+.2f} p {q['dm']['p_one_sided_full_better']:.3f} holm {q['dm']['p_holm']:.2f}"
                       f" | hit d/o/f {q['hit']['drift']:.3f}/{q['hit']['own']:.3f}/{q['hit']['full']:.3f}")
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    px, x15, s15 = xau_px()
    res = {"inputs": {"research_xau_15m_last": str(x15.index[-1]), "store_xau_15m": [str(s15.index[0]), str(s15.index[-1])],
                      "gold_price_first_used": str(px.index[0]), "cut": str(CUT)}}
    res["strict_delay15_train3"] = study(px, STORE)
    res["strict_delay60_train3"] = study(px, STORE, delay_min=60)
    res["strict_delay15_train5"] = study(px, STORE, min_months=5)
    fs = {f: first_seen(f) for f in X.SERIES.values()}
    fs_x = first_seen("XAU_USD_15m")
    res["first_seen_counts"] = {k: len(v) for k, v in fs.items()} | {"XAU_USD_15m": len(fs_x)}
    # Oct 3 .. Nov 13 only: final vs first-seen, same window, same models (trained on Jan..Sep, refit monthly)
    pxf, _, _ = xau_px(fs_x)
    res["final_from_oct3"] = study(px, STORE, window=(CUT, None))
    res["first_seen_from_oct3"] = study(pxf, STORE, window=(CUT, None), fs=fs)
    # report the Oct-Nov OOS subset of both runs on equal footing: correlations over spans starting on/after FS0
    sub = {}
    for tag, p_, f_ in (("final", px, None), ("first_seen", pxf, fs)):
        sub[tag] = {}
        for name, folder in X.SERIES.items():
            df = X.load(os.path.join(STORE, folder))
            if f_ is not None and f_.get(folder):
                rep = {t: v for t, v in f_[folder].items() if t in df.index}
                df = df.copy()
                if rep:
                    df.loc[list(rep), "close"] = list(rep.values())
            sp = X.spans(df[df.index >= FS0 - pd.Timedelta(hours=2)])
            sp = sp[sp["start"] >= FS0]
            g = np.log(X.p_at(p_, pd.DatetimeIndex(sp["end"])) / X.p_at(p_, pd.DatetimeIndex(sp["start"])))
            ok = ~np.isnan(g) & ~np.isnan(sp["r"].to_numpy())
            sub[tag][name] = {"n": int(ok.sum()), "pearson_1h": X.pear(sp["r"].to_numpy()[ok], g[ok])}
    res["oct3_contemporaneous_final_vs_first_seen"] = sub
    json.dump(res, open(os.path.join(OUT, "v2_xasset.json"), "w"), indent=1, default=float)
    print(json.dumps(res["inputs"], indent=0))
    for tag in ("strict_delay15_train3", "strict_delay60_train3", "strict_delay15_train5"):
        print("\n".join(line(tag, res[tag])))
    print("first-seen values available (closed-bar revisions logged since 2026-10-03):", res["first_seen_counts"])
    for n in X.SERIES:
        a, b = sub["final"][n], sub["first_seen"][n]
        print(f"Oct3+ contemporaneous {n:13s} n {a['n']} r final {a['pearson_1h']:+.4f} first-seen {b['pearson_1h']:+.4f} (diff {b['pearson_1h'] - a['pearson_1h']:+.4f})")
    d = res["strict_delay15_train3"]["DXY"]["1h"]
    print("DM detail DXY 1h:", d["dm"], "| mse", d["mse"], "| OOS rows by month", d["oos_rows_by_month"])


if __name__ == "__main__":
    main()
