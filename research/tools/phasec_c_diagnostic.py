"""Phase C diagnostic of B29 study C (a description of measured results, not a new hypothesis; nothing is selected here).

Two questions raised by auditing the B29 tables:
  1. The C model's AUC rises with bracket size (0.504 at TP5/SL10 -> 0.534 at TP30/SL20). Does that come from direction,
     or from predicting which trades end without TP or SL (2-day limit, weekend / holiday closures), which grows with
     bracket size? Measured: the outcome shares by entry weekday, the AUC on decided trades only (TP vs SL), the AUC
     without Friday entries, and the AUC of a calendar-only forecast (training-window TP rate per UTC weekday x hour)
     under the same quarterly walk-forward.
  2. "Top q" is chosen by a quantile threshold of isotonic-calibrated probabilities, and isotonic output is a step
     function, so ties at a plateau can make the realised share much larger than q. Measured: the share of test rows
     selected for each (direction, q), in the walk-forward and in 2026 (final model), and the number of distinct values.

  python research/tools/phasec_c_diagnostic.py --rd RD --store5 S5 --store60 S60 --out OUT.json [--select-on raw]

The committed research/results/phasec/phasec_c_diag.json was produced before the fix (b27.SELECT_ON did not exist and the
selection was on calibrated probabilities), which --select-on calibrated reproduces.
"""
import argparse
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from quantum.research import b22, b27, b28, b29


def calendar_wf(L: pd.DataFrame, start: str = "2021-01-01") -> np.ndarray:
    """Calendar-only forecast: TP rate of the training window's usable rows by (UTC weekday, hour), same quarters and
    purge as b27.walk_forward; unseen cells take the training mean."""
    t_fill, t_exit = L["fill_utc"].to_numpy(), L["exit_utc"].to_numpy()
    y = (L["outcome"] == "TP").to_numpy(int)
    ts = pd.to_datetime(t_fill, unit="s", utc=True)
    cell = (ts.weekday * 24 + ts.hour).to_numpy()
    p = np.full(len(L), np.nan)
    end = pd.Timestamp(int(t_fill.max()), unit="s", tz="UTC") + pd.Timedelta(seconds=1)
    for qs, qe in b22.quarters(start, end):
        s0, s1 = int(qs.timestamp()), int(qe.timestamp())
        te = (t_fill >= s0) & (t_fill < s1)
        usable = (t_exit < s0 - 86400) & (L["outcome"] != "OPEN").to_numpy()
        if te.sum() == 0 or usable.sum() < 5000:
            continue
        s = pd.Series(y[usable]).groupby(cell[usable]).mean()
        p[te] = pd.Series(cell[te]).map(s).fillna(y[usable].mean()).to_numpy()
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rd", required=True)
    ap.add_argument("--store5", required=True)
    ap.add_argument("--store60", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--select-on", default="calibrated", choices=("calibrated", "raw"),
                    help="calibrated = the selection as the registered runs did it (the default; what this diagnostic measured)")
    a = ap.parse_args(argv)
    b27.SELECT_ON = a.select_on
    pops = b27.load_pops(a.rd, a.store5, a.store60)
    D, Y = pops["DEV"], pops["Y2026"]
    for P_ in (D, Y):
        b27.prepare(P_, print)
        P_["F"] = pd.concat([P_["F"], b28.new_events(P_["m15"], P_["F"])], axis=1)
    TD = b29.tables(D, "ENG", fixed=b29.MODEL_BRACKETS)
    TY = b29.tables(Y, "ENG", fixed=b29.MODEL_BRACKETS)
    out = {}
    for g in b29.MODEL_BRACKETS:
        L, Ly = TD[g], TY[g]
        oc = L["outcome"].astype(str).to_numpy()
        y = (oc == "TP").astype(int)
        wd = pd.to_datetime(L["fill_utc"].to_numpy(), unit="s", utc=True).day_of_week.to_numpy()
        wf = b27.walk_forward(D["F"], L, D["h1"], ("LGBM",), log=lambda *_: None)
        p = wf["res"]["LGBM"]["p"]
        te = ~np.isnan(p)
        dec = te & np.isin(oc, ["TP", "SL"])
        nofri = te & (wd != 4)
        pc = calendar_wf(L)
        shares = {}
        for (dd, q), rows in b27.wf_selections(L, wf, "LGBM").items():
            base = int((te & (L["d"].to_numpy() == dd)).sum())
            shares[f"{b27.DIRS[dd]} top{q * 100:g}%"] = len(rows) / base if base else None
        FM = b27.final_models(D["F"], L, D["h1"], ("LGBM",))
        py = b27.apply_final(FM, Y["F"], Ly, Y["h1"], scores=True)["LGBM"]
        sh26 = {}
        for (dd, q), thr in FM["thr"]["LGBM"].items():
            m = (Ly["d"].to_numpy() == dd) & (Ly["outcome"].astype(str).to_numpy() != "OPEN")
            sh26[f"{b27.DIRS[dd]} top{q * 100:g}%"] = float((py[m] >= thr).mean()) if m.any() else None
        by_wd = {}
        for k, nm in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
            mk = te & (wd == k) & (oc != "OPEN")
            if mk.any():
                by_wd[nm] = {"n": int(mk.sum()), "tp": float((oc[mk] == "TP").mean()),
                             "neither": float(np.isin(oc[mk], ["TIMEOUT", "CLOSURE"]).mean())}
        out[b29.gname(g)] = {
            "auc_all": b27.auc(y[te], p[te]), "auc_decided_only": b27.auc(y[dec], p[dec]),
            "auc_without_friday": b27.auc(y[nofri], p[nofri]), "auc_calendar_only": b27.auc(y[te], pc[te]),
            "auc_calendar_only_decided": b27.auc(y[dec], pc[dec]),
            "neither_share_test": float(np.isin(oc[te], ["TIMEOUT", "CLOSURE"]).mean()),
            "by_weekday_test": by_wd, "distinct_p_test": len(np.unique(p[te])),
            "selected_share_wf": shares, "selected_share_2026": sh26,
            "distinct_p_2026": len(np.unique(py)),
        }
        print(b29.gname(g), json.dumps({k: v for k, v in out[b29.gname(g)].items() if k.startswith(("auc", "neither"))}))
    with open(a.out, "w") as fh:
        json.dump(b27._clean(out), fh, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
