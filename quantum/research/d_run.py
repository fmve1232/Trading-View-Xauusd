"""Phase D, D3: the registered run (research/registrations/PHASE_D.json). Research only. Runs where the data are (the
operator's computer); writes summary JSON and trade-level CSVs WITHOUT prices, and appends every trial to the Phase D log.

    py -m quantum.research.d_run --cache <the d_dukascopy cache> --out phase_d_out [--mt5 m1_utc.csv --mt5-point 0.01]
        (--rd / --store default to auto: the research-data and market-data branches, downloaded once into the cache)

ORDER (each stage gates the next; nothing is tuned between them):
  1 data     Dukascopy integrity per period (B5c amendment A2's gates, unchanged), order-flow coverage of the spot bars
             (at least MIN_OF_COVERAGE), intermarket availability. A failure stops the run: INSUFFICIENT DATA.
  2 study    d_study.run on development (walk-forward), the frozen set applied once to 2026.
  3 questions d_study.questions (descriptive).
  4 m1       the one-minute bid / ask measurements (resolution of B26's AMBIGUOUS trades, real-spread benchmark, the
             $3-$10 grid and stop entries) on Dukascopy and, if supplied, MT5.
The benchmark labels are B26's on the Twelve Data paths, exactly Phase C's populations (b27.load_pops conventions).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys

import numpy as np
import pandas as pd

from .. import ta
from ..data import sources
from . import b5c_dukascopy as C
from . import b26, b27, history
from . import d_clock as CK
from . import d_dukascopy as DD
from . import d_features as DF
from . import d_log as LOG
from . import d_m1 as M
from . import d_study as S
from . import harness as H

MIN_OF_COVERAGE = 0.90          # share of spot 15-minute bars (scored span) with Dukascopy ticks, per period
GRID = tuple((t, s) for t in (3, 5, 7, 10) for s in (3, 5, 7, 10))
STOP_X, STOP_WINDOW_S = (3, 5, 7, 10), 3600
ENG_SI, ENG_SO, ENG_CM = 0.20, 0.20, 0.07
DYNAMIC = ((1.0, 1.0), (1.5, 1.0), (1.0, 1.5))     # TP / SL in multiples of the 15-minute ATR(14) at the decision
DYN_SETS, DYN_ALGOS = ("BASELINE", "B", "D"), ("LR", "LGBM")
TRADE_COLS = ("fill_utc", "exit_utc", "dir", "outcome", "net_usd_oz", "cost_usd_oz", "minutes", "session", "vol_tercile", "trend_state")


# ---------------- data ----------------
MD_ZIP = "https://codeload.github.com/fmve1232/Trading-View-Xauusd/zip/refs/heads/market-data"


def market_data(cache: str, get=None) -> str:
    """The market-data branch (the live store: XAU_USD_5m / _60m for late 2026), downloaded once like B5c's research-data."""
    import io
    import zipfile
    root = os.path.join(cache, "market-data")
    if not os.path.isdir(root):
        r = (get or C._session().get)(MD_ZIP, timeout=120)
        if r.status_code != 200:
            raise RuntimeError(f"could not download the market-data branch (HTTP {r.status_code})")
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            z.extractall(root + ".part")
        os.replace(root + ".part", root)
    subs = [os.path.join(root, x) for x in os.listdir(root) if os.path.isdir(os.path.join(root, x))]
    return subs[0] if len(subs) == 1 else root


def populations(rd: str, store5: str | None, store60: str | None) -> dict:
    """Phase C's populations: development (scaled) and 2026 (literal, extended by the live store when given)."""
    m15d = sources.repair_reopen(H.partition(history.load(rd, "XAU/USD", "15min"), "development"), 900)
    h1d = sources.repair_reopen(H.partition(history.load(rd, "XAU/USD", "1h"), "development"), 3600)
    lo = H.HOLD[1]
    m15r = history.load(rd, "XAU/USD", "15min")
    m15r = sources.repair_reopen(m15r[m15r.index >= lo], 900)
    h1r = history.load(rd, "XAU/USD", "1h")
    h1r = sources.repair_reopen(h1r[h1r.index >= lo], 3600)
    if store5:
        ext = sources.resample_ohlc(b26.load_store(store5, 300), "15min")
        m15r = pd.concat([m15r, ext[ext.index > m15r.index[-1]]]).sort_index()
    if store60:
        s60 = b26.load_store(store60, 3600)
        h1r = pd.concat([h1r, s60[s60.index > h1r.index[-1]]]).sort_index()
    return {"DEV": {"m15": m15d, "h1": h1d, "score_from": pd.Timestamp("2020-04-01", tz="UTC"), "scale": True},
            "Y2026": {"m15": m15r, "h1": h1r, "score_from": pd.Timestamp("2026-03-01", tz="UTC"), "scale": False}}


def read_cache(cache: str, kind: str, start: pd.Timestamp, end: pd.Timestamp, cols: list[str]) -> pd.DataFrame:
    d = os.path.join(cache, kind)
    parts = []
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".csv"):
                continue
            day = pd.Timestamp(fn[:-4], tz="UTC")
            if day + pd.Timedelta(days=1) <= start or day >= end:
                continue
            df = pd.read_csv(os.path.join(d, fn), index_col=0)
            if len(df) and set(cols) <= set(df.columns):
                df.index = pd.DatetimeIndex(pd.to_datetime(df.index, utc=True)).rename(None)
                parts.append(df[cols].astype(float))
    if not parts:
        return pd.DataFrame(columns=cols, dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
    out = pd.concat(parts).sort_index()
    out = out[~out.index.duplicated(keep="first")]
    return out[(out.index >= start) & (out.index < end)]


def data_stage(P: dict, cache: str, mt5: pd.DataFrame | None = None) -> dict:
    """Integrity, scale, coverage and the clock (B5c A1 / A2 and Phase D A1, d_clock) per period. Returns the report;
    P gains raw / dext / m1 / scale, with quarantined days and weeks set missing (never shifted)."""
    rep = {}
    for name, p in P.items():
        m15 = p["m15"]
        lo, hi = m15.index[0], m15.index[-1] + pd.Timedelta(minutes=15)
        if lo < H.HOLD[1] and hi > H.VAL[0]:
            raise DD.SealedPeriod(f"the {name} population touches the sealed period")
        raw = read_cache(cache, "days", lo, hi, C.SUM_COLS)
        dext = read_cache(cache, "dext", lo, hi, DD.PD_COLS)
        r = {"spot_bars": len(m15), "dukascopy_bars": len(raw)}
        if len(raw) < 100:
            r["status"] = "NO DATA"
            rep[name] = r
            continue
        scale, gap_usd, gap_rel = C.price_scale(raw, m15)
        integ = C.integrity_report(raw, m15, scale)
        scored = m15.index >= p["score_from"]
        has = raw["n"].reindex(m15.index).fillna(0) > 0
        cov = float(has[scored].mean()) if scored.any() else 0.0
        r.update({"price_units_per_usd": scale, "median_gap_usd": gap_usd, "median_gap_rel": gap_rel, "integrity": integ,
                  "of_coverage_scored": cov, "dext_bars": len(dext)})
        fails = list(integ["failures"])
        if gap_rel > C.ALIGN_MAX:
            fails.append(f"price basis {gap_rel:.2%} > {C.ALIGN_MAX:.1%}")
        if cov < MIN_OF_COVERAGE:
            fails.append(f"order-flow coverage {cov:.1%} < {MIN_OF_COVERAGE:.0%}")
        if len(dext) < 0.99 * len(raw):
            fails.append("Phase D sums missing for some bars (re-run d_dukascopy)")
        m1 = read_cache(cache, "m1", lo, hi, DD.M1_COLS)
        mt = mt5[(mt5.index >= lo) & (mt5.index < hi)] if mt5 is not None else None
        clock = CK.audit(raw, dext, m1, m15, scale, mt if mt is not None and len(mt) else None)
        r["clock_a1"] = clock
        fails += clock["failures"]
        r["failures"] = fails
        r["status"] = "PASS" if not fails else "FAIL"
        qw = clock["quarantine_weeks"]
        p.update({"raw": CK.quarantine_weeks(C.quarantine(raw, integ["quarantined_days"]), qw),
                  "dext": CK.quarantine_weeks(dext, qw), "scale": scale, "m1": CK.quarantine_weeks(m1, qw)})
        rep[name] = r
    inter = {}
    root = os.path.join(cache, "inter")
    for sym in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        inter[sym] = {nm: read_cache(os.path.join(cache, "inter"), sym, p["m15"].index[0], p["m15"].index[-1] + pd.Timedelta(minutes=15),
                                     DD.MID_COLS) for nm, p in P.items()}
    rep["intermarket"] = {s: {nm: len(v[nm]) for nm in v} for s, v in inter.items()} or "none supplied"
    rep["_inter"] = inter
    return rep


def features(p: dict, inter: dict, name: str, log=print) -> tuple[pd.DataFrame, list[str], list[str]]:
    F = b27.build_features(p["m15"], p["h1"], log)
    of = DF.order_flow(p["raw"], p["dext"], p["scale"], index=p["m15"].index) if "raw" in p else pd.DataFrame(index=p["m15"].index)
    mids = {s: v[name] for s, v in inter.items() if len(v.get(name, [])) > 100}
    im = DF.intermarket(mids, p["m15"].index) if mids else pd.DataFrame(index=p["m15"].index)
    F = pd.concat([F, of, im], axis=1)
    return F, list(of.columns), list(im.columns)


# ---------------- the one-minute measurements (Workstream B) ----------------
def _t_end(m15: pd.DataFrame, dec: np.ndarray) -> np.ndarray:
    t15 = np.asarray(b26.make_path(m15, 900).t, dtype=np.int64)
    j = dec + 1 + 191
    return np.where(j < len(t15), t15[np.clip(j, 0, len(t15) - 1)] + 900, 2 ** 62)


def _rate(o: np.ndarray) -> dict:
    tp, st = int((o == "TP").sum()), int(np.isin(o, ["SL", "AMBIGUOUS"]).sum())
    n = tp + st
    return {"decided": n, "r": tp / n if n else None, "ci95": list(H.wilson(tp, n)) if n else [None, None],
            "neither_share": float(np.isin(o, ["TIMEOUT", "CLOSURE"]).mean()) if len(o) else None,
            "ambiguous_share": float((o == "AMBIGUOUS").mean()) if len(o) else None}


def m1_study(path: M.M1Path, L: pd.DataFrame, m15: pd.DataFrame) -> dict:
    """All-bar measurements on one-minute bid / ask (descriptive base rates, no selection)."""
    out = {"source": path.source, "minutes": path.n}
    t_end = _t_end(m15, L["dec_i"].to_numpy())
    k = L["k"].to_numpy(float)
    for dd, dn in b26.DIRS.items():
        m = (L["d"] == dd).to_numpy()
        tdec, te, kk = L["fill_utc"].to_numpy()[m], t_end[m], k[m]
        bench = M.bracket(path, tdec, te, dd, 15.0, 15.0, kk, ENG_SI, ENG_SO, ENG_CM)
        o15 = L["outcome"].to_numpy()[m]
        filled = bench["outcome"].to_numpy() != "NO_FILL"
        amb = (o15 == "AMBIGUOUS") & filled
        paired = filled & (o15 != "OPEN") & (bench["outcome"].to_numpy() != "OPEN")
        out[dn] = {"benchmark_15m_b26": _rate(o15[filled]), "benchmark_1m": _rate(bench["outcome"].to_numpy()[filled]),
                   "b26_ambiguous_resolved": {"n": int(amb.sum()), "tp_share_at_1m": float((bench["outcome"].to_numpy()[amb] == "TP").mean()) if amb.any() else None},
                   "exp_oz_15m_model_spread": float(L["net_usd_oz"].to_numpy()[m][paired].mean()) if paired.any() else None,
                   "exp_oz_1m_real_spread": float(bench["net_worst"].to_numpy()[paired].mean()) if paired.any() else None,
                   "no_fill": int((~filled).sum())}
        grid = {}
        for tp, sl in GRID:
            b = M.bracket(path, tdec, te, dd, float(tp), float(sl), kk, ENG_SI, ENG_SO, ENG_CM)
            ok = ~np.isin(b["outcome"].to_numpy(), ["NO_FILL", "OPEN"])
            grid[f"{tp}/{sl}"] = {**_rate(b["outcome"].to_numpy()[ok]), "r_best": _rate(b["outcome_best"].to_numpy()[ok])["r"],
                                  "exp_oz_worst": float(b["net_worst"].to_numpy()[ok].mean()) if ok.any() else None,
                                  "exp_oz_best": float(b["net_best"].to_numpy()[ok].mean()) if ok.any() else None}
        out[dn]["grid"] = grid
        ref = L["decision_px"].to_numpy(float)[m]
        stops = {}
        for x in STOP_X:
            st = M.stop_entry(path, tdec, te, dd, float(x), STOP_WINDOW_S, 15.0, 15.0, ref, kk, ENG_SI, ENG_SO, ENG_CM)
            ok = ~np.isin(st["outcome"].to_numpy(), ["NO_FILL", "OPEN"])
            stops[f"stop{x}"] = {"triggered": int(ok.sum()), **_rate(st["outcome"].to_numpy()[ok]),
                                 "r_best": _rate(st["outcome_best"].to_numpy()[ok])["r"],
                                 "exp_oz_worst": float(st["net_worst"].to_numpy()[ok].mean()) if ok.any() else None,
                                 "exp_oz_best": float(st["net_best"].to_numpy()[ok].mean()) if ok.any() else None}
        out[dn]["stop_entries_pm15"] = stops
    return out


# ---------------- the dynamic TP / SL track (registered separately; its own family) ----------------
def dynamic_labels(L: pd.DataFrame, m15: pd.DataFrame, path: M.M1Path, m_tp: float, m_sl: float) -> pd.DataFrame:
    """The same decisions with TP / SL = m x ATR(14) of the 15-minute bars closed at the decision, resolved on the
    one-minute bid / ask path (B26's rules, ENG slippage and commission x k). Columns as B26's, so d_study runs unchanged."""
    atr = ta.atr(*(m15[x].to_numpy(float) for x in ("high", "low", "close")), 14)
    t15 = np.asarray(b26.make_path(m15, 900).t, dtype=np.int64)
    dec = L["dec_i"].to_numpy()
    t_end = _t_end(m15, dec)
    k, d = L["k"].to_numpy(float), L["d"].to_numpy()
    f_all = M.fill_index(path, L["fill_utc"].to_numpy())
    out, xt, net, cost, xb = [], [], [], [], []
    for r in range(len(L)):
        a = atr[dec[r]]
        if f_all[r] < 0 or not np.isfinite(a) or a <= 0:
            out.append("OPEN")
            xt.append(np.nan)
            net.append(np.nan)
            cost.append(np.nan)
            xb.append(-1)
            continue
        f = int(f_all[r])
        o_w, _, j, px, fill, _ = M.race(path, f, int(d[r]), m_tp * a, m_sl * a, ENG_SI * k[r], ENG_SO * k[r], int(t_end[r]))
        oc = M.NAMES[o_w]
        out.append(oc)
        t_exit = int(path.t[j]) + 60
        xt.append(t_exit)
        xb.append(int(np.searchsorted(t15, t_exit - 1, "right") - 1))
        net.append((d[r] * (px - fill) - ENG_CM * k[r]) / k[r] if oc != "OPEN" else np.nan)
        cost.append((path.ao[f] - path.bo[f]) / k[r] + ENG_SI + (0.0 if oc == "TP" else ENG_SO) + ENG_CM)
    D_ = L.copy()
    D_["outcome"], D_["exit_utc"], D_["net_usd_oz"], D_["cost_usd_oz"], D_["exit_bar"] = out, xt, net, cost, xb
    D_["minutes"] = (D_["exit_utc"] - D_["fill_utc"]) / 60.0
    return D_[D_["outcome"] != "OPEN"].reset_index(drop=True)


# ---------------- outputs ----------------
def _clean(x):
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items() if not str(k).startswith("_")}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return None if (math.isnan(float(x)) or math.isinf(float(x))) else float(x)
    if isinstance(x, np.ndarray):
        return _clean(x.tolist())
    return x


def write_json(obj, path: str) -> str:
    with open(path, "w") as fh:
        json.dump(_clean(obj), fh, indent=1)
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def write_trades(L: pd.DataFrame, rows: np.ndarray, path: str) -> dict:
    """The strategy's independent trades (S.series), price-free columns only. Returns {file, n, sha256}."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    t = S.series(L, rows)
    t[[c for c in TRADE_COLS if c in t.columns]].to_csv(path, index=False)
    with open(path, "rb") as fh:
        return {"file": path, "n": len(t), "sha256": hashlib.sha256(fh.read()).hexdigest()}


def trade_files(res: dict, L: pd.DataFrame, Ly: pd.DataFrame | None, root: str) -> dict:
    """Every strategy's trade lists (development; 2026 for the frozen ones), whatever its result."""
    out = {}
    for s in res["strategies"]:
        base = os.path.join(root, s["id"].replace("/", "_"))
        out[s["id"]] = {"dev": write_trades(L, s["_rows_dev"], base + "__dev.csv")}
        if Ly is not None and "_rows_y2026" in s:
            out[s["id"]]["y2026"] = write_trades(Ly, s["_rows_y2026"], base + "__2026.csv")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Phase D: the registered run (development + the frozen 2026 check)")
    ap.add_argument("--rd", default="auto", help="a research-data checkout, or auto (downloaded into the cache, as B5c)")
    ap.add_argument("--store", default="auto", help="a market-data checkout, auto, or none (2026 then ends with the research history)")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--log", default=os.path.join("research", "phase_d_trials.jsonl"),
                    help="the committed hash-chained log (run from the repository folder so the chain continues)")
    ap.add_argument("--mt5", help="a USABLE UTC M1 file written by research/tools/mt5_m1_check.py --write-utc")
    ap.add_argument("--mt5-point", type=float)
    ap.add_argument("--algos", default=",".join(S.ALGOS))
    a = ap.parse_args(argv)
    os.makedirs(os.path.join(a.out, "trades"), exist_ok=True)
    if os.path.exists(os.path.join(a.out, "study.json")):
        raise SystemExit(f"{a.out} already holds a run: the registered run is made once; use a new --out to re-run and log it")
    rd = C.research_data(a.cache) if a.rd == "auto" else a.rd
    md = None if a.store == "none" else (market_data(a.cache) if a.store == "auto" else a.store)
    st5, st60 = (os.path.join(md, "XAU_USD_5m"), os.path.join(md, "XAU_USD_60m")) if md else (None, None)
    P = populations(rd, st5, st60)
    mt = None
    if a.mt5:
        mt = pd.read_csv(a.mt5, index_col=0)
        mt.index = pd.DatetimeIndex(pd.to_datetime(mt.index, utc=True))
    rep = data_stage(P, a.cache, mt)
    inter = rep.pop("_inter")
    h = write_json(rep, os.path.join(a.out, "data_report.json"))
    LOG.append(a.log, {"phase": "D", "kind": "data_report", "id": "D3-data", "sha256": h,
                       "status": {k: v.get("status") for k, v in rep.items() if isinstance(v, dict) and "status" in v}})
    if rep["DEV"].get("status") != "PASS":
        print(f"INSUFFICIENT DATA — RESEARCH INCOMPLETE: development data {rep['DEV'].get('status')}: {rep['DEV'].get('failures')}")
        return 3
    Fd, of_cols, im_cols = features(P["DEV"], inter, "DEV")
    Ld = b27.labels("PHASE_D", P["DEV"]["m15"], P["DEV"]["h1"], P["DEV"]["score_from"], True)
    Ld = Ld[Ld["outcome"] != "OPEN"].reset_index(drop=True)
    Fy = Ly = None
    if rep.get("Y2026", {}).get("status") == "PASS":
        Fy, _of_y, im_y = features(P["Y2026"], inter, "Y2026")
        Ly = b27.labels("PHASE_D", P["Y2026"]["m15"], P["Y2026"]["h1"], P["Y2026"]["score_from"], False)
        Ly = Ly[Ly["outcome"] != "OPEN"].reset_index(drop=True)
        im_cols = [c for c in im_cols if c in im_y]
    res = S.run(Fd, Ld, of_cols, im_cols, Fy, Ly, algos=tuple(a.algos.split(",")))
    if Ly is None:
        res["verdict"] = "INSUFFICIENT DATA — RESEARCH INCOMPLETE (no usable 2026 order flow: C1 cannot be assessed)"
    tf = trade_files(res, Ld, Ly, os.path.join(a.out, "trades", "benchmark"))
    h = write_json(res, os.path.join(a.out, "study.json"))
    for s in res["strategies"]:
        LOG.append(a.log, LOG.sanitize({"phase": "D", "kind": "trial", "id": s["id"], "partition": "development (walk-forward)",
                                        "trades": {k: {"n": v["n"], "sha256": v["sha256"]} for k, v in tf[s["id"]].items()},
                                        "n": s["dev"].get("n_trades"), "r": s["dev"].get("r"), "ci95": s["dev"].get("ci95"),
                                        "matched_random": s["dev"].get("matched_random"), "exp_oz": s["dev"].get("exp_oz"),
                                        "p_vs_random": s["dev"].get("p_vs_random"), "bh_q010": s["bh_q010"],
                                        "y2026": {k: s.get("y2026", {}).get(k) for k in ("n_trades", "r", "exp_oz", "p_vs_random")} if "y2026" in s else None,
                                        "criteria": s["criteria"], "study_sha256": h}))
    q = S.questions(Fd, Ld, P["DEV"]["m15"], of_cols, im_cols,
                    path_m1=M.from_dukascopy(P["DEV"]["m1"], P["DEV"]["scale"]) if len(P["DEV"].get("m1", [])) else None)
    LOG.append(a.log, {"phase": "D", "kind": "descriptive", "id": "D3-questions", "sha256": write_json(q, os.path.join(a.out, "questions.json"))})
    m1 = {}
    for name, p in P.items():
        if len(p.get("m1", [])):
            L_ = Ld if name == "DEV" else Ly
            if L_ is not None:
                m1[f"{name}/dukascopy"] = m1_study(M.from_dukascopy(p["m1"], p["scale"]), L_, p["m15"])
    if mt is not None:
        path = M.from_mt5(mt, a.mt5_point)
        for name, L_ in (("DEV", Ld), ("Y2026", Ly)):
            if L_ is not None:
                m1[f"{name}/mt5"] = m1_study(path, L_, P[name]["m15"])
    LOG.append(a.log, {"phase": "D", "kind": "descriptive", "id": "D3-m1", "sha256": write_json(m1, os.path.join(a.out, "m1.json"))})
    dyn = {}
    if len(P["DEV"].get("m1", [])) and Ly is not None and len(P["Y2026"].get("m1", [])):
        pd_, py_ = M.from_dukascopy(P["DEV"]["m1"], P["DEV"]["scale"]), M.from_dukascopy(P["Y2026"]["m1"], P["Y2026"]["scale"])
        for mt, ms in DYNAMIC:
            Ld_ = dynamic_labels(Ld, P["DEV"]["m15"], pd_, mt, ms)
            Ly_ = dynamic_labels(Ly, P["Y2026"]["m15"], py_, mt, ms)
            r_ = S.run(Fd, Ld_, of_cols, im_cols, Fy, Ly_, sets=DYN_SETS, algos=DYN_ALGOS)
            dyn[f"ATR{mt}/{ms}"] = r_
            tfd = trade_files(r_, Ld_, Ly_, os.path.join(a.out, "trades", "dynamic", f"ATR{mt}_{ms}"))
            for s_ in r_["strategies"]:
                LOG.append(a.log, LOG.sanitize({"phase": "D", "kind": "trial-dynamic", "id": f"ATR{mt}/{ms} {s_['id']}",
                                                "trades": {k: {"n": v["n"], "sha256": v["sha256"]} for k, v in tfd[s_["id"]].items()},
                                                "n": s_["dev"].get("n_trades"), "exp_oz": s_["dev"].get("exp_oz"),
                                                "p_vs_random": s_["dev"].get("p_vs_random"), "criteria": s_["criteria"]}))
    else:
        dyn["not_run"] = "the dynamic track needs Dukascopy one-minute bid / ask for development and 2026"
    LOG.append(a.log, {"phase": "D", "kind": "descriptive", "id": "D3-dynamic", "sha256": write_json(dyn, os.path.join(a.out, "dynamic.json"))})
    dyn_q = [f"{k}: {v['qualified']}" for k, v in dyn.items() if isinstance(v, dict) and v.get("qualified")]
    print(f"Phase D run complete: benchmark track {res['verdict']}; dynamic track qualified {dyn_q or 'none'}. Send the folder {os.path.abspath(a.out)} (summaries and trade lists, no prices) and {os.path.abspath(a.log)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
