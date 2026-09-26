"""The historical-analog statistics engine (Pine `runStatsEngines`), vectorised.

DELIBERATE DIFFERENCES FROM PINE (D-03, D-04). Pine cannot scan its 3,000-4,500-record
buffer in one bar, so it scans in chunks over several bars and keeps its calibration counts
across scan cycles with a 0.7 decay. Every cycle re-adds the same analogs, so a steady-state
bin count is ~3.3x the number of distinct observations, and the `N >= 30` bin gates are met
by counting the same trades repeatedly. The regime win counters do the same with a halving
every 100 matches. Here the whole buffer is scanned on every confirmed bar and every count is
a count of DISTINCT analogs. Thresholds are unchanged; they now mean what they say.

Everything else -- features, weights, similarity, gates, outcome labels, the rolling IS/ROLL
split (which is NOT a holdout, F-037) -- follows the Master line for line.
"""
from __future__ import annotations

import math

import numpy as np

from .ta import pine_round


def bayes_rate(w: float, t: float) -> float:
    return (w + 1.0) / (t + 2.0) if t > 0 else 0.5


def default_outputs() -> dict:
    return dict(bull=50.0, bear=50.0, range=0.0, match=0, pdh1st=None, pdl1st=None, ev=0.0, ev_label=None,
                wr=50.0, avg_w=0.5, avg_l=1.0, cal_grade_pct=0, cal_grade="N/A", cal_brier=None, cal_detail="",
                bos_cont=50.0, bos_fail=50.0, reg_per=50.0, feat_str=None, feat_htf=None, feat_liq=None,
                feat_mr=None, feat_cor=None, profit_factor=None, max_adverse_atr=None, max_dd=0.0,
                oos_wr=50.0, oos_n=0, is_wr=50.0, is_n=0, avg_w_oos=0.5, avg_l_oos=1.0)


class AnalogState:
    """Persistent state the Pine engine keeps in `var` arrays between bars."""

    def __init__(self):
        self.out = default_outputs()
        self.cal_fit = [math.nan, math.nan]
        self.cal_fit_bear = [math.nan, math.nan]
        self.hit_prob = [math.nan] * 8
        self.hit_n = math.nan
        self.race_prob = [math.nan] * 18
        self.race_n = math.nan
        self.oos_bear_wr = math.nan
        self.cal_rel = [math.nan] * 16
        self.reg_tot = [0, 0, 0]
        self.reg_win = [0, 0, 0]
        self.last_scan = {}


def scan(i: int, st: AnalogState, H: dict, S: dict, cur: dict, P: dict) -> None:
    """One full scan at bar i.

    H: per-bar record arrays (h_* ...), S: per-bar series needed at analog bars,
    cur: current-bar scalars, P: parameters (OUTCOME_N, HIST_MAX, weights ...).
    """
    N = P["N"]
    first = H["first_rec"]
    if first is None or i < first:
        return
    lo = max(first, i - P["HIST_MAX"] + 1)
    hN = i - lo + 1
    if not P["show_stats"] or hN <= N * 2:
        st.out = default_outputs()
        return
    hi = i - N
    if hi < lo:
        return
    R = np.arange(lo, hi + 1)

    # ---- similarity weights (1/sigma, capped by the user maxima, zone fixed at 8%) ----
    std = cur["std"]  # dict feature -> stdev over the last 100 bars
    iv = {k: (1.0 / max(s, 0.05)) if not math.isnan(s) else math.nan for k, s in std.items()}
    if any(math.isnan(x) for x in iv.values()):
        return  # Pine: a na stdev makes every weight na, so nothing matches
    ivs = sum(iv.values())
    caps = P["caps"]
    w = {k: min(iv[k] / ivs * 100.0, caps[k]) for k in iv}
    wn = sum(w.values())
    if wn > 0:
        w = {k: x / (wn / 100.0) for k, x in w.items()}
    w = {k: x * 0.92 for k, x in w.items()}
    w_zone = 8.0

    data_adj = 5 if hN > 300 else (0 if hN > 150 else -5)
    vol_adj = 5 if cur["vol_regime"] > 70 else 0
    sim_thresh = min(65, max(35, 45 + data_adj + vol_adj))

    sb_min, sb_max = lo, i
    sb_rng = max(1, sb_max - sb_min)
    oos_pct = 1.0 - P["holdout_ratio"]

    h_ret = H["ret"][R]
    keep = np.abs(h_ret) <= 3.0
    ema200 = S["ema200"][R]
    ss = S["struct"][R]
    mr = S["mr"][R]
    ch = S["corrh"][R]
    cl = S["close"][R]
    keep &= ~(np.isnan(ema200) | np.isnan(ss) | np.isnan(mr) | np.isnan(ch) | np.isnan(cl))
    R = R[keep]
    if len(R) == 0:
        _publish(i, st, P, cur, {}, empty=True)
        return

    adx_r = S["adx"][R]
    adx_norm = np.where(np.isnan(adx_r), H["adx_cat"][R] / 2.0,
                        np.where(adx_r > P["adx_threshold"], 1.0, np.where(adx_r > 15, 0.5, 0.0)))
    zone = H["zone"][R]
    ap = S["atr_pct"][R]
    cat = H["atr_cat"][R]
    atr_norm = np.where(np.isnan(ap), np.where(cat == 2, 0.85, np.where(cat == 1, 0.50, 0.15)), ap / 100.0)
    ema_r = S["ema200"][R]
    cl = S["close"][R]
    htf_norm = np.where(cl > ema_r, 1.0, np.where(cl < ema_r, 0.0, 0.5))
    struct_i = S["struct"][R] / 100.0
    pdh = S["pdh"][R]
    pdl = S["pdl"][R]
    ok_pd = ~np.isnan(pdh) & ~np.isnan(pdl) & (pdh != pdl)
    with np.errstate(divide="ignore", invalid="ignore"):
        liq_pos = np.where(ok_pd, (cl - pdl) / np.where(ok_pd, pdh - pdl, 1.0), 0.5)
    mr_norm = np.clip((S["mr"][R] + 100.0) / 200.0, 0.0, 1.0)
    corr_norm = np.clip(S["corrh"][R] / 100.0, 0.0, 1.0)
    sess = H["sess"][R]
    rg = H["regime"][R]
    reg_norm = np.where(rg == 0, 1.0, np.where(rg == 1, 0.5, 0.0))
    c = cur
    wad = (w["adx"] * np.abs(c["adx_norm"] - adx_norm) + w["atr"] * np.abs(c["atr_norm"] - atr_norm)
           + w["htf"] * np.abs(c["htf_norm"] - htf_norm) + w["str"] * np.abs(c["struct"] - struct_i)
           + w["liq"] * np.abs(c["liq_pos"] - liq_pos) + w["mr"] * np.abs(c["mr_norm"] - mr_norm)
           + w["cor"] * np.abs(c["corr_norm"] - corr_norm) + w["sess"] * np.abs(c["sess_norm"] - sess)
           + w["reg"] * np.abs(c["reg_norm"] - reg_norm) + w_zone * np.abs(c["zone"] - zone)) / 100.0
    bar_dist = np.maximum(1, i - R)
    time_w = np.power(0.997, bar_dist)
    sim_state = 1.0 - np.clip(wad, 0.0, 1.0)
    match = ~np.isnan(sim_state) & (sim_state * 100.0 >= max(sim_thresh, P["min_match_q"])) & (time_w >= 0.05)
    R = R[match]
    sim = (sim_state * time_w)[match]
    if len(R) == 0:
        _publish(i, st, P, cur, {}, empty=True)
        return

    oc = H["out"][R]
    is_oos = ((R - sb_min) / sb_rng >= oos_pct) & ((R - sb_min) - oos_pct * sb_rng >= N)

    A = {}
    A["mb"] = int((oc == 1).sum())
    A["mbr"] = int((oc == -1).sum())
    A["mr_"] = int((oc == 0).sum())
    A["mt"] = len(R)
    A["wb"] = float(sim[oc == 1].sum())
    A["wbr"] = float(sim[oc == -1].sum())
    A["wr_"] = float(sim[oc == 0].sum())
    A["wt"] = float(sim.sum())
    f1 = H["first"][R]
    A["p1"] = int((f1 == 1).sum())
    A["p2"] = int((f1 == 2).sum())
    A["pT"] = A["p1"] + A["p2"]
    A["wp1"] = float(sim[f1 == 1].sum())
    A["wpT"] = float(sim[(f1 == 1) | (f1 == 2)].sum())

    fr = H["ret"][R]
    cost_pts = (cur["sess_spread"] + 2.0 * P["slippage"]) + P["commission"] / max(P["point_value"], 1.0)
    ru = H["runit"][R]
    cost_r = np.where(ru > 0, cost_pts / np.where(ru > 0, ru, 1.0), 0.0)
    fr_adj = fr - cost_r
    afr = np.abs(fr_adj)
    win = oc == 1
    loss = oc == -1
    tmo = ~win & ~loss
    A["wc"] = int(win.sum())
    A["lc"] = int(loss.sum())
    A["sw"] = float(afr[win].sum())
    A["sl"] = float(afr[loss].sum())
    A["st"] = float(fr_adj[tmo].sum())
    aatr_now = cur["aatr"]
    fwd = R + N
    lo_out = S["low_out"][fwd]
    hi_out = S["high_out"][fwd]
    ent = S["close"][R]
    worst_dn = np.maximum(ent - lo_out, 0.0)
    worst_up = np.maximum(hi_out - ent, 0.0)
    mae = np.where(win, worst_dn, np.where(loss, worst_up, 0.0))
    A["mae_sum"] = float((mae[win | loss] / aatr_now).sum()) if aatr_now > 0 else 0.0
    A["mae_cnt"] = int((win | loss).sum())

    rp = P["risk_percent"]
    pnl = np.where(win, rp * afr / 1.5, np.where(loss, -rp * afr / 1.5, rp * fr_adj / 1.5))
    eq = 100.0 + np.cumsum(pnl)
    peak = np.maximum.accumulate(np.maximum(eq, 100.0))
    dd = np.where(peak > 0, (peak - eq) / peak * 100.0, 0.0)
    A["max_dd"] = float(max(dd.max(), 0.0)) if len(dd) else 0.0
    A["eq_peak"] = float(peak[-1]) if len(peak) else 100.0

    # hit histogram (OOS-early population), R unit = 1.5 x clamped historical ATR
    a_hist = S["aatr"][R]
    a_hist = np.where(np.isnan(a_hist), aatr_now, a_hist)
    r_u = 1.5 * np.clip(a_hist, aatr_now * 0.2, aatr_now * 5.0)
    hm = is_oos & (r_u > 0) & ~np.isnan(hi_out) & ~np.isnan(lo_out) & ~np.isnan(ent)
    mfe = (hi_out - ent) / np.where(r_u > 0, r_u, 1.0)
    maeL = (ent - lo_out) / np.where(r_u > 0, r_u, 1.0)
    ghit = [0.0] * 9
    ghit[8] = float(hm.sum())
    ghit[0] = float((hm & (mfe >= 1)).sum())
    ghit[1] = float((hm & (mfe >= 2)).sum())
    ghit[2] = float((hm & (mfe >= 3)).sum())
    ghit[3] = float((hm & (maeL >= 1)).sum())
    ghit[4] = float((hm & (maeL >= 1)).sum())
    ghit[5] = float((hm & (maeL >= 2)).sum())
    ghit[6] = float((hm & (maeL >= 3)).sum())
    ghit[7] = float((hm & (mfe >= 1)).sum())
    A["ghit"] = ghit

    rc = H["race"][R]
    rm = (rc >= 0) & is_oos
    grace = [0.0] * 19
    grace[12] = float(rm.sum())
    term = H["term"][R]
    rem = rc.copy()
    for j in range(6):
        ro = rem % 3
        rem = rem // 3
        base = (0 if j < 3 else 6) + j % 3
        grace[base] += float((rm & (ro == 1)).sum())
        grace[base + 3] += float((rm & (ro == 2)).sum())
        tsum = term[rm & (ro == 0)].sum()
        grace[13 + j] += float(tsum if j < 3 else -tsum)
    A["grace"] = grace

    A["oos_mt"] = int(is_oos.sum())
    A["oos_mb"] = int((is_oos & win).sum())
    A["oos_mbr"] = int((is_oos & loss).sum())
    A["wc_oos"] = A["oos_mb"]
    A["lc_oos"] = A["oos_mbr"]
    A["sw_oos"] = float(afr[is_oos & win].sum())
    A["sl_oos"] = float(afr[is_oos & loss].sum())
    A["is_mt"] = int((~is_oos).sum())
    A["is_mb"] = int((~is_oos & win).sum())

    be = H["bev"][R]
    bc = H["bcont"][R]
    A["boT"] = int((be > 0).sum())
    A["bov"] = int(((be > 0) & (bc > 0.5)).sum())

    pp = H["pred"][R]
    cb = H["calbin"][R]
    cal = []
    for k in range(5):
        mk = is_oos & (cb == k)
        cal.append((int(mk.sum()), float(pp[mk].sum()), int((mk & win).sum()), int((mk & loss).sum())))
    A["cal"] = cal

    rg = H["regime"][R]
    st.reg_tot = [int((rg == k).sum()) for k in range(3)]
    st.reg_win = [int(((rg == k) & win).sum()) for k in range(3)]

    def feat(code):
        up, dn = code == 2, code == 0
        tot = int((up | dn).sum())
        corr = int((up & win).sum() + (dn & loss).sum())
        return tot, corr
    A["fS"] = feat(H["str"][R])
    A["fH"] = feat(H["htf"][R])
    A["fL"] = feat(H["liq"][R])
    A["fM"] = feat(H["mr"][R])
    A["fC"] = feat(H["cor"][R])
    st.last_scan = {"hN": hN, "candidates": int(len(keep)), "matched": len(R), "sim_thresh": sim_thresh,
                    "weights": {k: round(x, 2) for k, x in w.items()}, "w_zone": w_zone}
    _publish(i, st, P, cur, A)


def _publish(i: int, st: AnalogState, P: dict, cur: dict, A: dict, empty: bool = False) -> None:
    """Pine's `else` branch: turn the accumulators into published statistics. Values that
    fail their own sample gate keep their previous published value, as the Pine vars do."""
    if empty:
        return
    o = st.out
    N = P["N"]
    mt, wt = A["mt"], A["wt"]
    if mt >= 3:
        b = pine_round((A["wb"] / wt if wt > 0 else A["mb"] / mt) * 100.0)
        be = pine_round((A["wbr"] / wt if wt > 0 else A["mbr"] / mt) * 100.0)
        r = 100.0 - b - be
        if r < 0:
            r = 0.0
            ratio = A["wb"] / wt if wt > 0 else (A["mb"] / mt if mt > 0 else 0.5)
            b = max(b - abs(r) * ratio, 5.0)
            be = 100.0 - b
        o["bull"], o["bear"], o["range"], o["match"] = b, be, r, mt
    if A["pT"] >= 3:
        p = int(pine_round((A["wp1"] / A["wpT"] if A["wpT"] > 0 else A["p1"] / A["pT"]) * 100.0))
        o["pdh1st"], o["pdl1st"] = p, 100 - p
    if mt / max(N, 1) >= 10:
        wr = A["wb"] / wt if wt > 0 else A["mb"] / mt
        lr = A["wbr"] / wt if wt > 0 else A["mbr"] / mt
        avg_w = A["sw"] / A["wc"] if A["wc"] > 0 else 0.5
        avg_l = A["sl"] / A["lc"] if A["lc"] > 0 else 1.0
        tr = A["wr_"] / wt if wt > 0 else (A["mr_"] / mt if mt > 0 else 0.0)
        avg_t = A["st"] / A["mr_"] if A["mr_"] > 0 else 0.0
        ev = wr * avg_w - lr * avg_l + tr * avg_t
        o["ev"] = ev
        o["ev_label"] = 1 if ev > 0.3 else (-1 if ev < -0.3 else 0)
        o["wr"] = wr * 100.0
        o["avg_w"], o["avg_l"] = avg_w, avg_l

    cal = A["cal"]
    cal_err, cal_bins, cal_brier, cal_n = 0.0, 0, 0.0, 0.0
    for (t, s, bw, _br) in cal:
        if t >= 30:
            a = bayes_rate(bw, t)
            p = s / t / 100.0
            cal_err += abs(a * 100.0 - p * 100.0)
            cal_bins += 1
            cal_brier += (a - p) ** 2 * t
            cal_n += t
    for k, (t, s, bw, _br) in enumerate(cal):
        st.cal_rel[k * 3] = t
        st.cal_rel[k * 3 + 1] = s / t if t >= 30 else math.nan
        st.cal_rel[k * 3 + 2] = bw * 100.0 / t if t >= 30 else math.nan
    if cal_bins > 0:
        ae = cal_err / cal_bins
        o["cal_grade_pct"] = int(max(0, 100.0 - ae * 2.0))
        g = o["cal_grade_pct"]
        o["cal_grade"] = "Excellent" if g >= 90 else "Good" if g >= 75 else "Fair" if g >= 50 else "Poor"
        # Platt-style WLS (Berkson weights) -- bull fit
        sw = sx = sy = sxx = sxy = 0.0
        nb = 0
        for (t, s, bw, _br) in cal:
            if t >= 30:
                xm = s / t - 50.0
                ar = min(max(bayes_rate(bw, t), 0.05), 0.95)
                ym = math.log(ar / (1.0 - ar))
                wf = t * ar * (1.0 - ar)
                sw += wf; sx += wf * xm; sy += wf * ym; sxx += wf * xm * xm; sxy += wf * xm * ym
                nb += 1
        if nb >= 3 and sw > 0:
            mx, my = sx / sw, sy / sw
            vr = sxx / sw - mx * mx
            if vr > 1e-6:
                k_ = (sxy / sw - mx * my) / vr
                if k_ > 0:
                    st.cal_fit = [min(max(k_, 0.02), 0.25), min(max(my - k_ * mx, -1.0), 1.0)]
        # bear fit (F-A16)
        sw = sx = sy = sxx = sxy = 0.0
        nb = 0
        for (t, s, _bw, br) in cal:
            if t >= 30:
                xm = s / t - 50.0
                ar = min(max(bayes_rate(br, t), 0.05), 0.95)
                ym = math.log(ar / (1.0 - ar))
                wf = t * ar * (1.0 - ar)
                sw += wf; sx += wf * xm; sy += wf * ym; sxx += wf * xm * xm; sxy += wf * xm * ym
                nb += 1
        if nb >= 3 and sw > 0:
            mx, my = sx / sw, sy / sw
            vr = sxx / sw - mx * mx
            if vr > 1e-6:
                k_ = (sxy / sw - mx * my) / vr
                if k_ < 0:
                    st.cal_fit_bear = [min(max(k_, -0.25), -0.02), min(max(my - k_ * mx, -1.0), 1.0)]
        tot = sum(t for (t, _, _, _) in cal)
        tb = sum(bw for (_, _, bw, _) in cal)
        base = tb / tot if tot > 0 else 0.5
        rel = res = 0.0
        for (t, s, bw, _br) in cal:
            if t > 0:
                p_ = s / t / 100.0
                o_ = bw / t
                rel += t * (p_ - o_) ** 2
                res += t * (o_ - base) ** 2
        if tot > 0:
            rel /= tot
            res /= tot
            o["cal_brier"] = pine_round((base * (1 - base) + rel - res) * 1000.0) / 1000.0
        st.cal_rel[15] = base * 100.0
        detail = ""
        for k in (3, 2, 4, 1, 0):
            t, s, bw, _ = cal[k]
            if t >= 30:
                detail = f"P{int(s / t)}>{int(pine_round(bayes_rate(bw, t) * 100.0))}%"
                break
        o["cal_detail"] = detail + (f" rmsCE{math.sqrt(cal_brier / cal_n) * 100.0:.0f}%" if cal_n > 0 else "")
    if A["boT"] >= 3:
        o["bos_cont"] = pine_round(A["bov"] * 100.0 / A["boT"])
        o["bos_fail"] = 100 - o["bos_cont"]
    rc = cur["r_curr"]
    tc = cur["reg_trans"]
    if rc == 0 and tc["T"] > 0:
        o["reg_per"] = pine_round((tc["T"] - tc["TR"] - tc["TD"]) * 100.0 / tc["T"])
    elif rc == 1 and tc["R"] > 0:
        o["reg_per"] = pine_round((tc["R"] - tc["RT"] - tc["RD"]) * 100.0 / tc["R"])
    elif rc == 2 and tc["D"] > 0:
        o["reg_per"] = pine_round((tc["D"] - tc["DT"] - tc["DR"]) * 100.0 / tc["D"])
    for key, name in (("fS", "feat_str"), ("fH", "feat_htf"), ("fL", "feat_liq"), ("fM", "feat_mr"), ("fC", "feat_cor")):
        tot, corr = A[key]
        if tot > 0:
            o[name] = (corr / tot - 0.5) * 100.0
    if mt >= 5 and A["sl"] > 0 and A["lc"] > 0 and A["wc"] > 0:
        o["profit_factor"] = (A["wc"] * (A["sw"] / A["wc"])) / (A["lc"] * (A["sl"] / A["lc"]))
    if A["mae_cnt"] > 0:
        o["max_adverse_atr"] = A["mae_sum"] / A["mae_cnt"]
    hn = A["ghit"][8]
    if hn >= 20:
        st.hit_prob = [A["ghit"][k] / hn * 100.0 for k in range(8)]
        st.hit_n = hn
    rn = A["grace"][12]
    if rn >= 20:
        st.race_prob = [A["grace"][k] / rn * 100.0 for k in range(12)] + [A["grace"][13 + k] / rn for k in range(6)]
        st.race_n = rn
    if A["eq_peak"] > 0:
        o["max_dd"] = pine_round(A["max_dd"] * 10.0) / 10.0
    if A["oos_mt"] > 0:
        st.oos_bear_wr = A["oos_mbr"] * 100.0 / A["oos_mt"]
        o["oos_wr"] = pine_round(A["oos_mb"] * 100.0 / A["oos_mt"])
        o["oos_n"] = A["oos_mt"]
        o["avg_w_oos"] = A["sw_oos"] / A["wc_oos"] if A["wc_oos"] > 0 else 0.5
        o["avg_l_oos"] = A["sl_oos"] / A["lc_oos"] if A["lc_oos"] > 0 else 1.0
    if A["is_mt"] > 0:
        o["is_wr"] = pine_round(A["is_mb"] * 100.0 / A["is_mt"])
        o["is_n"] = A["is_mt"]
