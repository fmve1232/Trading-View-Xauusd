"""The Quantum 5.0 Master engine, bar by bar. Port of artefacts/XAUUSD_Quantum_5_0_Master.pine
(build v21), in the Master's own order, so each block can be read against its Pine source.

`arm` selects the entry gate:
  "treatment"  the Master / Strategy gate (live system)
  "control"    the OLDGATES A/B arm (pre-Q5.5 gates) -- backtest comparison only

Differences from Pine are deliberate, few, and listed in docs/PLATFORM.md ("Parity"):
  D-01 HTF values use real-time semantics on every bar (no historical/real-time asymmetry).
  D-02 DST from the IANA database, not the hand-rolled calendar rule.
  D-03/04 the analog engine scans the whole buffer each bar and counts distinct analogs.
  D-05 COT percentile over weeks, aligned on report RELEASE time.
  D-06 volume profile computed on every bar (Pine: last bar only, F-A07), so a backtested
       plan can use value-area levels exactly as the live plan does; the "°" markers go.
  D-07 missing futures volume on a spot bar counts as 0 (reported in the data census).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import analog, ta
from .config import SCHEMA_BUILD, Config
from .features import compute as compute_features

NaN = float("nan")


def isn(x) -> bool:
    return x is None or (isinstance(x, float) and x != x)


def nz(x, f=0.0):
    return f if isn(x) else x


def ne(a, b) -> bool:
    """Pine `a != b`: false when either side is na."""
    return (not isn(a)) and (not isn(b)) and a != b


def pround(x):
    """Pine math.round: half away from zero."""
    return math.copysign(math.floor(abs(x) + 0.5), x) + 0.0


def clamp(x, lo, hi):
    return min(max(x, lo), hi)


def f_grid_interp(rr, p0, p1, p2, p3, decay):
    if rr <= 0.0:
        return p0
    if rr <= 1.0:
        return p0 + (p1 - p0) * rr
    if rr <= 2.0:
        return p1 + (p2 - p1) * (rr - 1.0)
    if rr <= 3.0:
        return p2 + (p3 - p2) * (rr - 2.0)
    return p3 * math.pow(0.7, rr - 3.0) if decay else p3


@dataclass
class Result:
    cfg: Config
    arm: str
    F: dict
    rows: dict                      # per-bar arrays
    events: list                    # chart events (BOS, CHoCH, zones, signals ...)
    last: dict                      # full dashboard state at the last confirmed bar
    analog: analog.AnalogState
    outcome_n: int
    hist_max: int
    params: dict = field(default_factory=dict)


def outcome_n_for(tf_sec: int) -> int:
    return max(3, int(3600.0 / tf_sec))


def hist_max_for(tf_sec: int) -> int:
    return 1200 if tf_sec <= 60 else 2000 if tf_sec <= 300 else 3000 if tf_sec <= 900 else 4500


def run(market, cfg: Config, arm: str = "treatment", F: dict | None = None) -> Result:
    F = F or compute_features(market, cfg)
    n = F["n"]
    tf_sec = market.tf_sec
    N = outcome_n_for(tf_sec)
    HIST_MAX = hist_max_for(tf_sec)
    cal = F["cal"]
    o, h, l, c, v = (F[k].tolist() for k in ("o", "h", "l", "c", "v"))
    aatr = F["aatr"].tolist()
    atr = F["atr"].tolist()
    adx = F["adx"].tolist()
    dip, dim = F["diplus"].tolist(), F["diminus"].tolist()
    atr_pct = F["atr_pct"].tolist()
    adx_gate = F["adx_gate"].tolist()
    vol_sma20 = F["vol_sma20"].tolist()
    body, rng, body_pct = F["body"].tolist(), F["range"].tolist(), F["body_pct"].tolist()
    piv_hi, piv_lo = F["piv_hi"].tolist(), F["piv_lo"].tolist()
    spiv_hi, spiv_lo = F["swing_piv_hi"].tolist(), F["swing_piv_lo"].tolist()
    rsi = F["rsi"].tolist()
    slv_rsi = F["slv_rsi"].tolist()
    slv_valid = F["slv_valid"].tolist()
    reg_bos_mult = F["reg_bos_mult"].tolist()
    reg_sl_mult = F["reg_sl_mult"].tolist()
    reg_liq_mult = F["reg_liq_mult"].tolist()
    hour = cal["hour"].tolist()
    dow = cal["dow"].tolist()
    in_asian, in_london, in_ny = cal["in_asian"].tolist(), cal["in_london"].tolist(), cal["in_ny"].tolist()
    in_kz = cal["in_killzone"].tolist()
    crossed_day, crossed_week = cal["crossed_day"].tolist(), cal["crossed_week"].tolist()
    pr_raw_vol = F["pr_raw_vol"].tolist()
    ema20, ema100 = F["ema20"].tolist(), F["ema100"].tolist()
    vwap, wvwap, mvwap = F["vwap"].tolist(), F["wvwap"].tolist(), F["mvwap"].tolist()
    vwap_up2 = F["vwap_up2"].tolist()
    bull_ts, bear_ts = F["bull_trend_score"].tolist(), F["bear_trend_score"].tolist()
    bull_trend, bear_trend = F["bull_trend"].tolist(), F["bear_trend"].tolist()
    htf_bull_gate, htf_bear_gate = F["htf_bull_gate"].tolist(), F["htf_bear_gate"].tolist()
    htf_al_l, htf_al_s = F["htf_align_long"].tolist(), F["htf_align_short"].tolist()
    htf_full_l, htf_full_s = F["htf_full_long"].tolist(), F["htf_full_short"].tolist()
    hb, hs = {k: a.tolist() for k, a in F["htf_bull"].items()}, {k: a.tolist() for k, a in F["htf_bear"].items()}
    sess_q = F["session_quality"].tolist()
    regime_strength = F["regime_strength"].tolist()
    mr = F["mr_composite"].tolist()
    corrh = F["avg_corr_health"].tolist()
    macro_bull, macro_bear = F["macro_bull"].tolist(), F["macro_bear"].tolist()
    mbv, mbr = F["macro_bull_votes"].tolist(), F["macro_bear_votes"].tolist()
    macro_strength = F["macro_strength"].tolist()
    macro_conf = F["macro_strength_conf"].tolist()
    oi_conv = F["oi_conviction"].tolist()
    reg_abn, reg_cmp, reg_exp = F["reg_abnormal"].tolist(), F["reg_compression"].tolist(), F["reg_expansion"].tolist()
    reg_str, reg_wk = F["reg_strong"].tolist(), F["reg_weak"].tolist()
    reg_conf_cap = F["reg_conf_cap"].tolist()
    sess_conf_mult = F["session_conf_mult"].tolist()
    sess_spread = F["sess_spread"].tolist()
    var_s, var_l = F["var_short"].tolist(), F["var_long"].tolist()
    regime_trending, regime_ranging, regime_dead = F["regime_trending"].tolist(), F["regime_ranging"].tolist(), F["regime_dead"].tolist()
    avg_stab = F["avg_stability"].tolist()
    num_valid = F["num_valid"].tolist()
    pm_high, pm_low = F["pm_high"].tolist(), F["pm_low"].tolist()
    vwap_reject_bull = F["vwap_reject_bull"].tolist()
    vol_delta50 = F["vol_delta50"].tolist()
    cot_regime = F["cot_regime"].tolist()
    atr_sma20 = F["atr_sma20"].tolist()
    macro_valid_any = (F["dxy_valid"] | F["yld_valid"] | F["spx_valid"] | F["eur_valid"] | F["slv_valid"]).tolist()
    gc_cb, gc_cr = F["gc_confirms_bull"].tolist(), F["gc_confirms_bear"].tolist()
    oi_valid = F["oi_valid"].tolist()

    high_out = ta.highest(F["h"], N)
    low_out = ta.lowest(F["l"], N)
    high_out_l, low_out_l = high_out.tolist(), low_out.tolist()
    vp_high = ta.highest(F["h"], 100).tolist()
    vp_low = ta.lowest(F["l"], 100).tolist()
    hlc3 = ((F["h"] + F["l"] + F["c"]) / 3.0)

    # ---- per-bar outputs ----
    keys = ["bull", "bear", "range", "bull_pre", "struct", "pdh", "pdl", "pwh", "pwl", "cdh", "cdl", "eqh", "eql",
            "should_buy", "should_sell", "tq_veto", "tq", "conf", "dir_label", "plan_long", "plan_entry",
            "plan_sl", "plan_tp1", "plan_tp2", "plan_tp3", "plan_rr1", "plan_ev", "cal_p_long", "cal_p_short",
            "exec_buy", "exec_sell", "ob_bull_lo", "ob_bull_hi", "ob_bear_lo", "ob_bear_hi", "fvg_hi", "fvg_lo",
            "fvg_bull", "vpoc", "vah", "val", "risk_lock", "cal_veto", "ev_veto", "tq_floor_veto",
            "curr_adx", "curr_atr", "curr_htf", "curr_struct", "curr_liq", "curr_mr", "curr_cor", "curr_sess", "curr_reg", "curr_zone",
            "bias_label", "regime_label", "sess_label", "active_res", "active_sup"]
    rows = {k: [None] * n for k in keys}
    events = []

    # ---- state (Pine var) ----
    ny_dh = ny_dl = prev_ny_dh = prev_ny_dl = NaN
    ny_wh = ny_wl = prev_ny_wh = prev_ny_wl = NaN
    # session intel
    cur_sess_id = -1
    ses_hi = ses_lo = ses_open = prev_ses_hi = prev_ses_lo = NaN
    ses_manip = False
    sess_rng_avg = [0.0, 0.0, 0.0]
    sess_cnt = [0, 0, 0]
    sess_manip_cnt = [0, 0, 0]
    sess_cont_cnt = [0, 0, 0]
    # BOS
    active_res = active_sup = last_broken_res = last_broken_sup = NaN
    s_active_res = s_active_sup = s_last_broken_res = s_last_broken_sup = NaN
    prev_bos_res_snap = prev_bos_sup_snap = prev_sbos_res_snap = prev_sbos_sup_snap = NaN
    prev_active_res = prev_active_sup = prev_s_active_res = prev_s_active_sup = NaN
    # sequences
    sh1 = sh2 = sh3 = sl1 = sl2 = sl3 = NaN
    seq_last_bar = -999
    choch_bull_sc = choch_bear_sc = mss_bull_sc = mss_bear_sc = 0.0
    prev_choch_lab_b = prev_choch_lab_s = prev_mss_lab_b = prev_mss_lab_s = False
    prev_mss_act_b = prev_mss_act_s = prev_choch_act_b = prev_choch_act_s = False
    # displacement
    disp_up_act = disp_dn_act = False
    prev_disp_up = prev_disp_dn = False
    # struct
    bull_struct_bar = bear_struct_bar = None
    bull_struct_inval = bear_struct_inval = NaN
    bull_struct_type = bear_struct_type = ""
    # rsi div pivots
    piv_rsi_hi = piv_px_hi = piv_rsi_lo = piv_px_lo = NaN
    prev_piv_rsi_hi = prev_piv_px_hi = prev_piv_rsi_lo = prev_piv_px_lo = NaN
    # eq
    swh1 = swh2 = swl1 = swl2 = NaN
    # vol by hour
    vol_by_hour = [0.0] * 24
    vol_hour_cnt = [0] * 24
    rel_vol_hist = []
    # fvg
    fvg_hu = fvg_ll = NaN
    fvg_bar = -1
    fvg_active = False
    fvg_bull = False
    # ob
    ob_bl = ob_bh = ob_sl = ob_sh = NaN
    ob_b_bar = ob_s_bar = -1
    ob_b_act = ob_s_act = False
    ob_b_mit = ob_s_mit = False
    ob_b_mitpct = ob_s_mitpct = 0.0
    # smt
    g_rsi_low = s_rsi_low = g_rsi_high = s_rsi_high = NaN
    prev_g_rsi_low = prev_g_rsi_high = NaN
    prev_piv_lo_val = prev_piv_hi_val = NaN
    # cdh/cdl
    cdh = cdl = NaN
    # struct persistence
    sp_entry_hi = sp_entry_lo = NaN
    sp_bull = False
    sp_bars = 0
    struct_score = 0.0
    sp_peak = sp_trough = NaN
    # regime transitions
    r_prev = -1
    rt = {"T": 0, "R": 0, "D": 0, "TR": 0, "TD": 0, "RT": 0, "RD": 0, "DT": 0, "DR": 0}
    regime_comp_hist = []
    # analog history (per-bar arrays; bar index == record index)
    H = {
        "first_rec": None,
        "zone": np.full(n, 0.5), "adx_cat": np.zeros(n), "atr_cat": np.zeros(n), "htf": np.ones(n, dtype=int),
        "str": np.ones(n, dtype=int), "liq": np.ones(n, dtype=int), "mr": np.ones(n, dtype=int), "cor": np.zeros(n, dtype=int),
        "out": np.zeros(n, dtype=int), "ret": np.zeros(n), "runit": np.zeros(n), "pred": np.full(n, 50.0),
        "race": np.full(n, -1, dtype=np.int64), "term": np.zeros(n), "first": np.zeros(n, dtype=int), "bev": np.zeros(n, dtype=int),
        "bcont": np.full(n, -1.0), "calbin": np.full(n, -1.0), "regime": np.zeros(n, dtype=int), "sess": np.full(n, 0.5),
        "datastatus": np.zeros(n, dtype=int), "schema": np.ones(n, dtype=int),
    }
    struct_arr = np.full(n, np.nan)
    pdh_arr = np.full(n, np.nan)
    pdl_arr = np.full(n, np.nan)
    S = {"ema200": F["ema200"], "struct": struct_arr, "mr": F["mr_composite"], "corrh": F["avg_corr_health"],
         "close": F["c"], "adx": F["adx"], "atr_pct": F["atr_pct"], "pdh": pdh_arr, "pdl": pdl_arr,
         "aatr": F["aatr"], "low_out": low_out, "high_out": high_out}
    AS = analog.AnalogState()
    cal_q = [20.0, 40.0, 60.0, 80.0]
    curr_feat = {k: np.full(n, np.nan) for k in ("adx", "atr", "htf", "str", "liq", "mr", "cor", "sess", "reg", "zone")}
    cal_drift_fast = cal_drift_slow = 50.0
    fadj_hist = [0.0, 0.0]
    dd_for_breaker = 0.0
    # auction
    prev_day_value = NaN
    bars_on_side = 0
    last_sweep_q = 0
    last_sweep_grade = ""
    prev_sess_id = None
    sess_age = 0
    disc_hist = []
    # risk tracker
    rk_entry = rk_sl = rk_tp = NaN
    rk_long = False
    rk_day_r = 0.0
    rk_day_n = 0
    rk_consec = 0
    risk_lock = False
    rk_lock_bar = 0
    conf_dir_label = "WAIT"
    dow_bull = [0.0] * 8
    dow_bear = [0.0] * 8
    # gate funnel (Diagnostics §7)
    fn = dict(bars=0, trend=0, htf=0, pre=0, sig=0, tq=0, ev=0, cal=0, risk=0, pass_=0)
    # V1/V2 shadow (Diagnostics §2)
    shd = dict(bars=0, dcomp=0, regchg=0, x40=0, x70=0, maxabs=0)
    last = {}
    rec_floor = N * 3 + 50
    prev_conf_label = "WAIT"
    prev_risk_lock = False
    prev_vwap = NaN

    for i in range(n):
        ci, hi_, li, oi_, vi = c[i], h[i], l[i], o[i], v[i]
        c1 = c[i - 1] if i > 0 else NaN
        a = aatr[i]
        # ================= NY daily / weekly high-low (PDH/PDL/PWH/PWL) =================
        if isn(ny_dh):
            ny_dh, ny_dl, ny_wh, ny_wl = hi_, li, hi_, li
        elif crossed_day[i]:
            prev_ny_dh, prev_ny_dl = ny_dh, ny_dl
            ny_dh, ny_dl = hi_, li
            if crossed_week[i]:
                prev_ny_wh, prev_ny_wl = ny_wh, ny_wl
                ny_wh, ny_wl = hi_, li
        else:
            ny_dh = max(nz(ny_dh, hi_), hi_)
            ny_dl = min(nz(ny_dl, li), li)
            ny_wh = max(nz(ny_wh, hi_), hi_)
            ny_wl = min(nz(ny_wl, li), li)

        # ================= session intelligence =================
        sess_id = 0 if in_asian[i] else 1 if in_london[i] else 2 if in_ny[i] else 3
        if sess_id != cur_sess_id:
            if 0 <= cur_sess_id <= 2 and not isn(ses_hi):
                rng_s = ses_hi - ses_lo
                cs = sess_cnt[cur_sess_id]
                sess_rng_avg[cur_sess_id] = rng_s if cs == 0 else sess_rng_avg[cur_sess_id] * 0.9 + rng_s * 0.1
                sess_cnt[cur_sess_id] = cs + 1
                if ses_manip:
                    sess_manip_cnt[cur_sess_id] += 1
                if rng_s > 0 and abs(c1 - ses_open) / rng_s > 0.5:
                    sess_cont_cnt[cur_sess_id] += 1
            prev_ses_hi, prev_ses_lo = ses_hi, ses_lo
            cur_sess_id = sess_id
            ses_hi, ses_lo, ses_open = hi_, li, oi_
            ses_manip = False
        else:
            ses_hi = max(nz(ses_hi, hi_), hi_)
            ses_lo = min(nz(ses_lo, li), li)
            if not isn(prev_ses_hi) and not isn(prev_ses_lo) and ((hi_ > prev_ses_hi and ci < prev_ses_hi) or (li < prev_ses_lo and ci > prev_ses_lo)):
                ses_manip = True
        sess_avg_rng = sess_rng_avg[cur_sess_id] if 0 <= cur_sess_id <= 2 else NaN
        sess_exp_pct = (ses_hi - ses_lo) / sess_avg_rng * 100.0 if (not isn(sess_avg_rng) and sess_avg_rng > 0 and not isn(ses_hi)) else NaN
        sess_n = sess_cnt[cur_sess_id] if 0 <= cur_sess_id <= 2 else 0
        sess_manip_prob = sess_manip_cnt[cur_sess_id] * 100.0 / sess_n if sess_n >= 5 else NaN
        sess_cont_prob = sess_cont_cnt[cur_sess_id] * 100.0 / sess_n if sess_n >= 5 else NaN

        # ================= pivots / BOS =================
        ph, pl = piv_hi[i], piv_lo[i]
        bos_res_snap, bos_sup_snap = active_res, active_sup
        if not isn(ph):
            if not isn(active_res):
                last_broken_res = active_res
            active_res = ph
        if not isn(pl):
            if not isn(active_sup):
                last_broken_sup = active_sup
            active_sup = pl
        sph, spl = spiv_hi[i], spiv_lo[i]
        sbos_res_snap, sbos_sup_snap = s_active_res, s_active_sup
        if not isn(sph):
            if not isn(s_active_res):
                s_last_broken_res = s_active_res
            s_active_res = sph
        if not isn(spl):
            if not isn(s_active_sup):
                s_last_broken_sup = s_active_sup
            s_active_sup = spl
        break_buf = a * 0.15
        strong_body = a * 0.30
        strong_vol = vi > vol_sma20[i] * 1.20 * reg_bos_mult[i]
        bd, bp = body[i], body_pct[i]
        common_b = adx_gate[i] and bd > strong_body and bp > 70 and strong_vol

        def bos_up(snap, prev_snap, lbr):
            return (not isn(snap)) and ci > snap and c1 <= prev_snap and ne(snap, lbr)

        def bos_dn(snap, prev_snap, lbs):
            return (not isn(snap)) and ci < snap and c1 >= prev_snap and ne(snap, lbs)
        int_lab_b = bos_up(bos_res_snap, prev_bos_res_snap, last_broken_res)
        int_lab_s = bos_dn(bos_sup_snap, prev_bos_sup_snap, last_broken_sup)
        int_bull_bos = int_lab_b and common_b and (ci - bos_res_snap) > break_buf
        int_bear_bos = int_lab_s and common_b and (bos_sup_snap - ci) > break_buf
        sw_lab_b = bos_up(sbos_res_snap, prev_sbos_res_snap, s_last_broken_res)
        sw_lab_s = bos_dn(sbos_sup_snap, prev_sbos_sup_snap, s_last_broken_sup)
        sw_bull_bos = sw_lab_b and common_b and (ci - sbos_res_snap) > break_buf
        sw_bear_bos = sw_lab_s and common_b and (sbos_sup_snap - ci) > break_buf
        bull_bos = int_bull_bos or sw_bull_bos
        bear_bos = int_bear_bos or sw_bear_bos
        bos_lab_b = int_lab_b or sw_lab_b
        bos_lab_s = int_lab_s or sw_lab_s
        prev_bos_res_snap, prev_bos_sup_snap = bos_res_snap, bos_sup_snap
        prev_sbos_res_snap, prev_sbos_sup_snap = sbos_res_snap, sbos_sup_snap
        vol_ok = vi > vol_sma20[i]
        if not isn(active_res) and ci > active_res and c1 <= prev_active_res and vol_ok:
            last_broken_res = active_res
            active_res = NaN
        if not isn(active_sup) and ci < active_sup and c1 >= prev_active_sup and vol_ok:
            last_broken_sup = active_sup
            active_sup = NaN
        if not isn(s_active_res) and ci > s_active_res and c1 <= prev_s_active_res and vol_ok:
            s_last_broken_res = s_active_res
            s_active_res = NaN
        if not isn(s_active_sup) and ci < s_active_sup and c1 >= prev_s_active_sup and vol_ok:
            s_last_broken_sup = s_active_sup
            s_active_sup = NaN
        prev_active_res, prev_active_sup = active_res, active_sup
        prev_s_active_res, prev_s_active_sup = s_active_res, s_active_sup
        if bull_bos:
            events.append({"i": i, "type": "BOS", "dir": 1, "px": bos_res_snap if int_bull_bos else sbos_res_snap})
        if bear_bos:
            events.append({"i": i, "type": "BOS", "dir": -1, "px": bos_sup_snap if int_bear_bos else sbos_sup_snap})

        # ================= CHoCH / MSS =================
        if not isn(ph) or not isn(pl):
            if not isn(ph):
                sh3, sh2, sh1 = sh2, sh1, ph
            if not isn(pl):
                sl3, sl2, sl1 = sl2, sl1, pl
            seq_last_bar = i
        seq_valid = not any(isn(x) for x in (sh1, sh2, sh3, sl1, sl2, sl3))
        hl_ = seq_valid and sl1 > sl2
        lh_ = seq_valid and sh1 < sh2
        bar_space = (i - seq_last_bar) >= 3
        pad = a * 0.5
        adok_b = hl_ and abs(sl1 - sl2) >= pad
        adok_s = lh_ and abs(sh1 - sh2) >= pad
        prior_bull = seq_valid and sh2 > sh3 and sl2 > sl3
        prior_bear = seq_valid and sh2 < sh3 and sl2 < sl3
        choch_lab_b = prior_bear and hl_ and bar_space and adok_b
        choch_lab_s = prior_bull and lh_ and bar_space and adok_s
        mss_lab_b = choch_lab_b and (seq_valid and sh1 > sh2) and bar_space and adok_b
        mss_lab_s = choch_lab_s and (seq_valid and sl1 < sl2) and bar_space and adok_s
        choch_ev_b = choch_lab_b and not prev_choch_lab_b
        choch_ev_s = choch_lab_s and not prev_choch_lab_s
        mss_ev_b = mss_lab_b and not prev_mss_lab_b
        mss_ev_s = mss_lab_s and not prev_mss_lab_s
        prev_choch_lab_b, prev_choch_lab_s, prev_mss_lab_b, prev_mss_lab_s = choch_lab_b, choch_lab_s, mss_lab_b, mss_lab_s
        choch_bull_sc = 15.0 if choch_ev_b else choch_bull_sc * 0.85
        choch_bear_sc = 15.0 if choch_ev_s else choch_bear_sc * 0.85
        mss_bull_sc = 15.0 if mss_ev_b else mss_bull_sc * 0.85
        mss_bear_sc = 15.0 if mss_ev_s else mss_bear_sc * 0.85
        choch_act_b, choch_act_s = choch_bull_sc > 7.5, choch_bear_sc > 7.5
        mss_act_b, mss_act_s = mss_bull_sc > 7.5, mss_bear_sc > 7.5
        if choch_ev_b:
            events.append({"i": i, "type": "MSS" if mss_ev_b else "CHoCH", "dir": 1, "px": sl1})
        if choch_ev_s:
            events.append({"i": i, "type": "MSS" if mss_ev_s else "CHoCH", "dir": -1, "px": sh1})

        # ================= displacement =================
        d_enter = a * cfg.disp_mult
        d_hold = a * (cfg.disp_mult * 0.6)
        vol_ok13 = vi > vol_sma20[i] * 1.30
        c_hi1 = h[i - 1] if i > 0 else NaN
        c_lo1 = l[i - 1] if i > 0 else NaN
        raw_up = cfg.show_displacement and bd > d_enter and ci > oi_ and ci > c_hi1 and rng[i] > 0 and bp > 70 and vol_ok13
        raw_dn = cfg.show_displacement and bd > d_enter and ci < oi_ and ci < c_lo1 and rng[i] > 0 and bp > 70 and vol_ok13
        if raw_up:
            disp_up_act = True
        elif bd <= d_hold:
            disp_up_act = False
        if raw_dn:
            disp_dn_act = True
        elif bd <= d_hold:
            disp_dn_act = False
        disp_up = raw_up or disp_up_act
        disp_dn = raw_dn or disp_dn_act

        # ================= structure latch =================
        bull_trig = bull_bos or (mss_act_b and not prev_mss_act_b) or (choch_act_b and not prev_choch_act_b)
        bear_trig = bear_bos or (mss_act_s and not prev_mss_act_s) or (choch_act_s and not prev_choch_act_s)
        if bull_trig:
            bull_struct_bar = i
            bull_struct_inval = li
            bull_struct_type = "BOS" if bull_bos else ("MSS" if (mss_act_b and not prev_mss_act_b) else "CHoCH")
        if bear_trig:
            bear_struct_bar = i
            bear_struct_inval = hi_
            bear_struct_type = "BOS" if bear_bos else ("MSS" if (mss_act_s and not prev_mss_act_s) else "CHoCH")
        prev_mss_act_b, prev_mss_act_s, prev_choch_act_b, prev_choch_act_s = mss_act_b, mss_act_s, choch_act_b, choch_act_s
        if not isn(bull_struct_inval) and ci < bull_struct_inval:
            bull_struct_bar = None
        if not isn(bear_struct_inval) and ci > bear_struct_inval:
            bear_struct_bar = None
        bull_struct_act = bull_struct_bar is not None and i - bull_struct_bar <= cfg.struct_window
        bear_struct_act = bear_struct_bar is not None and i - bear_struct_bar <= cfg.struct_window
        bull_struct_age = i - bull_struct_bar if bull_struct_act else -1
        bear_struct_age = i - bear_struct_bar if bear_struct_act else -1

        # ================= RSI divergence =================
        prev_piv_rsi_hi, prev_piv_px_hi, prev_piv_rsi_lo, prev_piv_px_lo = piv_rsi_hi, piv_px_hi, piv_rsi_lo, piv_px_lo
        if not isn(ph):
            piv_rsi_hi, piv_px_hi = rsi[i], ph
        if not isn(pl):
            piv_rsi_lo, piv_px_lo = rsi[i], pl
        if cfg.use_rsi_div_filter and not any(isn(x) for x in (piv_px_lo, piv_rsi_lo, prev_piv_rsi_lo, prev_piv_px_lo)):
            bull_rsi_div = piv_px_lo < prev_piv_px_lo and piv_rsi_lo > prev_piv_rsi_lo
        else:
            bull_rsi_div = True
        if cfg.use_rsi_div_filter and not any(isn(x) for x in (piv_px_hi, piv_rsi_hi, prev_piv_rsi_hi, prev_piv_px_hi)):
            bear_rsi_div = piv_px_hi > prev_piv_px_hi and piv_rsi_hi < prev_piv_rsi_hi
        else:
            bear_rsi_div = True

        # ================= equal highs / lows =================
        eq_tol = a * cfg.eq_atr_mult
        if not isn(ph):
            swh2, swh1 = swh1, ph
        if not isn(pl):
            swl2, swl1 = swl1, pl
        equal_highs = not isn(swh1) and not isn(swh2) and abs(swh1 - swh2) <= eq_tol
        equal_lows = not isn(swl1) and not isn(swl2) and abs(swl1 - swl2) <= eq_tol

        # ================= relative volume / climax =================
        hr = hour[i]
        pa, pcnt = vol_by_hour[hr], vol_hour_cnt[hr]
        alpha = 1.0 / (pcnt + 1) if pcnt < 20 else 0.05
        vol_by_hour[hr] = pa + alpha * (vi - pa)
        vol_hour_cnt[hr] = min(pcnt + 1, 100000)
        rel_vol = vi / max(vol_by_hour[hr], 1.0)
        rel_vol_hist.append(rel_vol)
        L = cfg.vol_lookback
        if len(rel_vol_hist) > L:
            win = rel_vol_hist[-(L + 1):-1]
            pr_rel = sum(1 for x in win if x <= rel_vol) / L * 100.0
        else:
            pr_rel = NaN
        vol_pct = pr_rel if vol_hour_cnt[hr] >= 20 else pr_raw_vol[i]
        climax_up = cfg.show_climax and vol_pct >= cfg.vol_climax_perc and ci > oi_
        climax_dn = cfg.show_climax and vol_pct >= cfg.vol_climax_perc and ci < oi_

        # ================= FVG =================
        if i >= 2:
            h2, l2 = h[i - 2], l[i - 2]
            fvg_det = cfg.show_fvg and ((h2 < li and li - h2 > a * 0.3) or (l2 > hi_ and l2 - hi_ > a * 0.3))
        else:
            fvg_det = False
        if fvg_det and not fvg_active:
            g_lo, g_hi = h[i - 2], li
            if l[i - 2] > hi_:
                g_lo, g_hi = hi_, l[i - 2]
            if g_lo < g_hi:
                fvg_hu, fvg_ll, fvg_bar = g_hi, g_lo, i
                fvg_active = True
                fvg_bull = li > h[i - 2]
                events.append({"i": i, "type": "FVG", "dir": 1 if fvg_bull else -1, "hi": g_hi, "lo": g_lo, "start": i - 2})
        fvg_active = fvg_active and i - fvg_bar <= cfg.fvg_max_bars
        fvg_mit = fvg_active and i > fvg_bar and ((fvg_bull and li < fvg_hu) or (not fvg_bull and hi_ > fvg_ll))
        if fvg_mit:
            fvg_active = False
            events.append({"i": i, "type": "FVG_END", "dir": 1 if fvg_bull else -1})

        # ================= order blocks =================
        onset_up = disp_up and not prev_disp_up
        onset_dn = disp_dn and not prev_disp_dn
        if cfg.show_ob and onset_dn and not ob_s_act and i > 0:
            ob_sh, ob_sl, ob_s_bar, ob_s_act, ob_s_mit, ob_s_mitpct = h[i - 1], l[i - 1], i, True, False, 0.0
            events.append({"i": i, "type": "OB", "dir": -1, "hi": ob_sh, "lo": ob_sl, "start": i - 1})
        if cfg.show_ob and onset_up and not ob_b_act and i > 0:
            ob_bh, ob_bl, ob_b_bar, ob_b_act, ob_b_mit, ob_b_mitpct = h[i - 1], l[i - 1], i, True, False, 0.0
            events.append({"i": i, "type": "OB", "dir": 1, "hi": ob_bh, "lo": ob_bl, "start": i - 1})
        failed_bull = cfg.show_ob and not ob_s_act and prev_disp_up and not disp_up and i > 0 and ci < o[i - 1] and ci < (h[i - 1] + l[i - 1]) / 2
        if failed_bull:
            ob_sh, ob_sl, ob_s_bar, ob_s_act, ob_s_mit, ob_s_mitpct = h[i - 1], l[i - 1], i, True, False, 0.0
            events.append({"i": i, "type": "OB", "dir": -1, "hi": ob_sh, "lo": ob_sl, "start": i - 1, "failed": True})
        failed_bear = cfg.show_ob and not ob_b_act and prev_disp_dn and not disp_dn and i > 0 and ci > o[i - 1] and ci > (h[i - 1] + l[i - 1]) / 2
        if failed_bear:
            ob_bh, ob_bl, ob_b_bar, ob_b_act, ob_b_mit, ob_b_mitpct = h[i - 1], l[i - 1], i, True, False, 0.0
            events.append({"i": i, "type": "OB", "dir": 1, "hi": ob_bh, "lo": ob_bl, "start": i - 1, "failed": True})
        was_b, was_s = ob_b_act, ob_s_act
        ob_b_act = ob_b_act and i - ob_b_bar <= cfg.ob_max_bars
        ob_s_act = ob_s_act and i - ob_s_bar <= cfg.ob_max_bars
        if ob_b_act and ci < ob_bl - a * 0.3:
            ob_b_act = False
        if ob_s_act and ci > ob_sh + a * 0.3:
            ob_s_act = False
        if ob_b_act and not ob_b_mit:
            r_ = ob_bh - ob_bl
            if r_ > 0 and ob_bl <= ci <= ob_bh:
                ob_b_mitpct = min(100.0, (ob_bh - ci) / r_ * 100.0)
                if ob_b_mitpct >= 50.0:
                    ob_b_mit = True
        if ob_s_act and not ob_s_mit:
            r_ = ob_sh - ob_sl
            if r_ > 0 and ob_sl <= ci <= ob_sh:
                ob_s_mitpct = min(100.0, (ci - ob_sl) / r_ * 100.0)
                if ob_s_mitpct >= 50.0:
                    ob_s_mit = True
        if was_b and not ob_b_act:
            events.append({"i": i, "type": "OB_END", "dir": 1})
        if was_s and not ob_s_act:
            events.append({"i": i, "type": "OB_END", "dir": -1})
        prev_disp_up_now, prev_disp_dn_now = disp_up, disp_dn

        # ================= SMT divergence =================
        g_rsi = rsi[i]
        smt_valid = cfg.show_smt and slv_valid[i] and not isn(g_rsi) and not isn(slv_rsi[i])
        prev_g_rsi_low, prev_g_rsi_high = g_rsi_low, g_rsi_high
        if not isn(pl):
            g_rsi_low, s_rsi_low = g_rsi, slv_rsi[i]
        if not isn(ph):
            g_rsi_high, s_rsi_high = g_rsi, slv_rsi[i]
        smt_bull_raw = smt_valid and not isn(pl) and not isn(prev_piv_lo_val) and pl < prev_piv_lo_val and g_rsi_low > prev_g_rsi_low and g_rsi_low > s_rsi_low
        smt_bear_raw = smt_valid and not isn(ph) and not isn(prev_piv_hi_val) and ph > prev_piv_hi_val and g_rsi_high < prev_g_rsi_high and g_rsi_high < s_rsi_high
        gdir1 = (1 if c[i - 1] > c[i - 2] else -1 if c[i - 1] < c[i - 2] else 0) if i > 1 else 0
        smt_bull = smt_bull_raw and (gdir1 < 0 or (i > 0 and rsi[i - 1] > slv_rsi[i - 1]))
        smt_bear = smt_bear_raw and (gdir1 > 0 or (i > 0 and rsi[i - 1] < slv_rsi[i - 1]))
        prev_piv_lo_val, prev_piv_hi_val = pl, ph

        # ================= regime composite =================
        ap = atr_pct[i]
        regime_score = int(min(pround((nz(adx[i]) / 100.0) * (1.2 if ap > 70 else 1.0) * 100.0), 100))
        vol_regime = 100 if ap > 70 else 60 if ap > 40 else 30
        structure_regime = 100 if (htf_al_l[i] >= 2 or htf_al_s[i] >= 2) else 60 if (htf_al_l[i] >= 1 or htf_al_s[i] >= 1) else 30
        mb_, mr_b = macro_bull[i], macro_bear[i]
        macro_regime_base = 100 if (mb_ or mr_b) else 60 if (mbv[i] >= 2 or mbr[i] >= 2) else 30
        macro_regime = max(0, min(100, macro_regime_base + (10 if (oi_conv[i] != 0 and (mb_ or mr_b)) else 5 if oi_conv[i] != 0 else 0)))
        sq = sess_q[i]
        session_regime = 100 if sq >= 60 else 60 if sq >= 30 else 30
        rc_raw = regime_score * 0.30 + vol_regime * 0.15 + structure_regime * 0.20 + macro_regime * 0.20 + session_regime * 0.15
        regime_comp = int(pround(rc_raw))
        strong_trend = rc_raw >= 70
        moderate_trend = 40 <= rc_raw < 70
        weak_trend = rc_raw < 40
        regime_comp_hist.append(rc_raw)

        # ================= volume profile (every bar, D-06) =================
        vpoc = vah = val = NaN
        va_ratio = 0.0
        va_pos = "—"
        if i >= 99:
            vh, vl = vp_high[i], vp_low[i]
            bsz = (vh - vl) / 40
            if bsz > 0:
                seg = slice(i - 99, i + 1)
                bp_ = hlc3[seg]
                bv = F["v"][seg]
                idx = np.clip(((bp_ - vl) / bsz).astype(int), 0, 39)
                vols = np.bincount(idx, weights=bv, minlength=40)
                prices = vl + bsz * (np.arange(40) + 0.5)
                vi_ = int(np.argmax(vols)) if vols.max() > 0 else 0
                maxv = float(vols[vi_]) if vols.max() > 0 else 0.0
                vpoc = float(prices[vi_])
                tot_v = float(vols.sum())
                tgt = tot_v * 0.70
                cum = maxv
                lo_i = hi_i = vi_
                while cum < tgt and (lo_i > 0 or hi_i < 39):
                    vb = vols[lo_i - 1] if lo_i > 0 else -1.0
                    va_ = vols[hi_i + 1] if hi_i < 39 else -1.0
                    if va_ >= vb and hi_i < 39:
                        hi_i += 1
                        cum += va_
                    elif lo_i > 0:
                        lo_i -= 1
                        cum += vb
                    else:
                        break
                vah, val = float(prices[hi_i]), float(prices[lo_i])
                vrng = vh - vl
                va_ratio = (vah - val) / vrng * 100.0 if tot_v > 0 and vrng > 0 else 0.0
                va_pos = "▲" if ci > vah else "▼" if ci < val else "●"

        # ================= liquidity pools =================
        pool_pdh = prev_ny_dh if tf_sec <= 86400 else NaN
        pool_pdl = prev_ny_dl if tf_sec <= 86400 else NaN
        pool_pwh = prev_ny_wh if tf_sec <= 604800 else NaN
        pool_pwl = prev_ny_wl if tf_sec <= 604800 else NaN
        pool_pmh, pool_pml = pm_high[i], pm_low[i]
        pool_eqh = max(swh1, swh2) if equal_highs else NaN
        pool_eql = min(swl1, swl2) if equal_lows else NaN
        pdh_arr[i], pdl_arr[i] = pool_pdh, pool_pdl
        ran = lambda p, up: (not isn(p)) and (ci > p if up else ci < p)
        ran_pdh, ran_pdl = ran(pool_pdh, True), ran(pool_pdl, False)
        ran_pwh, ran_pwl = ran(pool_pwh, True), ran(pool_pwl, False)
        ran_pmh, ran_pml = ran(pool_pmh, True), ran(pool_pml, False)
        ran_eqh, ran_eql = ran(pool_eqh, True), ran(pool_eql, False)
        liq_avail = sum(0 if isn(p) else 1 for p in (pool_pdh, pool_pdl, pool_pwh, pool_pwl, pool_pmh, pool_pml))
        liq_health = (80 if liq_avail >= 6 else 60 if liq_avail >= 4 else 35 if liq_avail >= 2 else 0) + (20 if (ran_pdh or ran_pdl or ran_pwh or ran_pwl or ran_pmh or ran_pml) else 0)

        if crossed_day[i]:
            cdh, cdl = hi_, li
        else:
            cdh = max(nz(cdh, hi_), hi_)
            cdl = min(nz(cdl, li), li)

        # ================= structure persistence -> structScore =================
        if bull_bos:
            sp_entry_hi, sp_entry_lo, sp_bull, sp_bars, sp_peak, sp_trough = ci, li, True, 1, hi_, li
        elif bear_bos:
            sp_entry_hi, sp_entry_lo, sp_bull, sp_bars, sp_peak, sp_trough = hi_, ci, False, 1, hi_, li
        else:
            if not isn(sp_entry_hi):
                if sp_bull:
                    if hi_ > sp_peak:
                        sp_peak = hi_
                    if li > sp_trough:
                        sp_trough = li
                    if li >= sp_entry_lo:
                        sp_bars += 1
                    else:
                        sp_entry_hi = NaN
                        sp_bars = 0
                else:
                    if hi_ < sp_peak:
                        sp_peak = hi_
                    if li < sp_trough:
                        sp_trough = li
                    if hi_ <= sp_entry_hi:
                        sp_bars += 1
                    else:
                        sp_entry_hi = NaN
                        sp_bars = 0
        if sp_bars > 0:
            if sp_bull and sp_entry_lo > 0:
                dr = (ci - sp_entry_lo) / a if abs(a) > 1e-10 else 0.0
            elif not sp_bull and not isn(sp_entry_hi) and sp_entry_hi > 0:
                dr = (sp_entry_hi - ci) / a if abs(a) > 1e-10 else 0.0
            else:
                dr = 0.0
            sp_dist = 35 if dr >= 2.0 else 25 if dr >= 1.0 else 15 if dr >= 0.5 else 0
            sp_adx = 20 if adx[i] > cfg.adx_threshold else 0
            struct_score = (45 if sp_bars >= 12 else 35 if sp_bars >= 8 else 25 if sp_bars >= 4 else 15) + sp_dist + sp_adx
        else:
            struct_score = struct_score * 0.5 if struct_score > 0 else 0.0
        struct_arr[i] = struct_score

        # ================= liquidity scoring =================
        eff_prox = cfg.liq_prox_mult * reg_liq_mult[i]

        def ldist(p):
            return abs(ci - p) if not isn(p) else 1e10

        def lds(d):
            if d < a * eff_prox and a > 0:
                return max(100.0 - (d / a) * (100.0 / eff_prox), 0.0)
            return 0.0
        hgb, hgs = htf_bull_gate[i], htf_bear_gate[i]
        al_l, al_s = htf_al_l[i], htf_al_s[i]

        def htf_match(bull):
            if bull and hgb:
                return 1.3
            if bull and al_l >= 1:
                return 1.15
            if bull and hgs:
                return 0.7
            if bull and al_s >= 1:
                return 0.85
            if not bull and hgs:
                return 1.3
            if not bull and al_s >= 1:
                return 1.15
            if not bull and hgb:
                return 0.7
            if not bull and al_l >= 1:
                return 0.85
            return 1.0
        liq_sess_w = 1.3 if in_kz[i] else 1.15 if (in_london[i] or in_ny[i]) else 0.8
        bt, brt = bull_trend[i], bear_trend[i]

        def trend_w(bull):
            if bull and bt:
                return 1.2
            if not bull and brt:
                return 1.2
            if bull and brt:
                return 0.7
            if not bull and bt:
                return 0.7
            return 1.0
        pools = [("PDH", pool_pdh, 1.50, True), ("PDL", pool_pdl, 1.50, False), ("PWH", pool_pwh, 1.25, True),
                 ("PWL", pool_pwl, 1.25, False), ("PMH", pool_pmh, 1.10, True), ("PML", pool_pml, 1.10, False),
                 ("EQH", pool_eqh, 1.00, True), ("EQL", pool_eql, 1.00, False)]
        liq_scores = {}
        liq_dists = {}
        for name, p, wgt, bull in pools:
            d = ldist(p)
            s = lds(d)
            liq_dists[name] = d
            liq_scores[name] = wgt * s * htf_match(bull) * liq_sess_w * trend_w(bull) if s > 0 else 0.0
        srt = sorted(liq_scores.values(), reverse=True)
        liq_max, liq_second = srt[0], srt[1]
        liq_dest, liq_dest_score, liq_dest_dist, liq_dest_sec = "—", 0, 1e10, 0
        order = ["PDH", "PDL", "PWH", "PWL", "PMH", "PML", "EQH", "EQL"]
        if liq_max >= 25:
            for nm in order:
                if liq_scores[nm] >= liq_max or nm == "EQL":
                    liq_dest, liq_dest_score, liq_dest_dist = nm, int(pround(liq_scores[nm])), liq_dists[nm]
                    break
            if liq_second >= liq_max * 0.5:
                for nm in order:
                    if liq_scores[nm] > 0 and liq_scores[nm] >= liq_second and liq_dest != nm:
                        liq_dest_sec = int(pround(liq_scores[nm]))
                        break
        diff = liq_dest_score - liq_dest_sec
        liq_dest_conf = ("HIGH" if diff >= 30 else "MEDIUM" if diff >= 15 else "LOW") if liq_dest_score > 0 else ""
        mss_ = macro_strength[i]
        liq_reach = 50.0
        if liq_max > 0:
            dest_bull = liq_dest in ("PDH", "PWH", "PMH", "EQH")
            base = 50.0
            base += 12.0 if ((dest_bull and bt) or (not dest_bull and brt)) else 0.0
            base += 10.0 if ((dest_bull and hgb) or (not dest_bull and hgs)) else 0.0
            base += 8.0 if ((mss_ > 0 and dest_bull) or (mss_ < 0 and not dest_bull)) else 0.0
            base += 8.0 if regime_comp >= 70 else 4.0 if regime_comp >= 40 else 0.0
            dp = min(liq_dest_dist / (a * 3.0) * 30.0, 30.0) if (a > 0 and liq_dest_dist < 1e10) else 15.0
            liq_reach = clamp(base - dp, 5.0, 95.0)
        sweep_bear = any((not isn(p)) and hi_ >= p and ci < p for p in (pool_pdh, pool_pwh, pool_pmh))
        sweep_bull = any((not isn(p)) and li <= p and ci > p for p in (pool_pdl, pool_pwl, pool_pml))
        if sweep_bull:
            events.append({"i": i, "type": "SWEEP", "dir": 1, "px": li})
        if sweep_bear:
            events.append({"i": i, "type": "SWEEP", "dir": -1, "px": hi_})

        # ================= MTF confluence / macro label =================
        mtf_b = int(hb["5"][i]) + int(hb["15"][i]) + int(hb["60"][i]) + int(hb["240"][i])
        mtf_s = int(hs["5"][i]) + int(hs["15"][i]) + int(hs["60"][i]) + int(hs["240"][i])
        mtf_conf_score = int(pround(((mtf_b + mbv[i]) - (mtf_s + mbr[i])) / 10.0 * 100.0))
        mtf_mag = abs(mtf_conf_score)
        mtf_hi, mtf_med, mtf_low = mtf_mag >= 60, 30 <= mtf_mag < 60, mtf_mag < 30
        macro_valid = macro_valid_any[i]
        macro_label = ("BULL" if mss_ >= 40 else "BEAR" if mss_ <= -40 else "BULL-ISH" if mss_ >= 15 else "BEAR-ISH" if mss_ <= -15 else "MIXED") if macro_valid else "N/A"

        # ================= bias scores =================
        b_struct_b = 30 if bt else choch_bull_sc
        b_struct_s = 30 if brt else choch_bear_sc
        b_liq_b = 20 if (bull_bos or disp_up) else choch_bull_sc * (10.0 / 15.0)
        b_liq_s = 20 if (bear_bos or disp_dn) else choch_bear_sc * (10.0 / 15.0)
        b_mac_b = 25 if mb_ else 0
        b_mac_s = 25 if mr_b else 0
        b_htf_b = 25 if hgb else (10 if al_l >= 1 else 0)
        b_htf_s = 25 if hgs else (10 if al_s >= 1 else 0)
        b_mom_b = 15 if bull_rsi_div else 0
        b_mom_s = 15 if bear_rsi_div else 0
        b_sess = 15 if sq >= 50 else 8 if sq >= 30 else 3
        bull_bias = b_struct_b + b_liq_b + b_mac_b + b_htf_b + b_mom_b + b_sess
        bear_bias = b_struct_s + b_liq_s + b_mac_s + b_htf_s + b_mom_s + b_sess
        range_bias = ((40 if regime_ranging[i] else 0) + (50 if regime_dead[i] else 0) + (30 if mtf_low else 0)
                      + (20 if (not mb_ and not mr_b and macro_valid) else 0) + (15 if sq < 30 else 0) + (15 if avg_stab[i] > 0.3 else 0))
        bias_call = "RANGE" if (range_bias >= bull_bias and range_bias >= bear_bias) else ("BULL" if bull_bias >= bear_bias else "BEAR")
        range_dominant = bias_call == "RANGE"

        # ================= confidence =================
        conf_struct = 100 if structure_regime >= 80 else 60 if structure_regime >= 50 else 30 if structure_regime >= 20 else 10
        conf_mtf = int(pround(max(htf_full_l[i], htf_full_s[i]) * 100.0 / 5.0))
        conf_liq = (25 if (bull_bos or bear_bos) else 0) + (25 if (fvg_active or ob_b_act or ob_s_act) else 0) \
            + (25 if (ran_pdh or ran_pdl or ran_pwh or ran_pwl or ran_eqh or ran_eql) else 0) + (25 if liq_dest_score >= 50 else 0)
        mic = macro_conf[i]
        conf_macro = 100 if mic >= 60 else 60 if mic >= 30 else 30 if mic >= 10 else 10
        conf_sess = 100 if session_regime >= 80 else 60 if session_regime >= 50 else 30 if session_regime >= 20 else 10
        prev5 = regime_comp_hist[-6:-1] if len(regime_comp_hist) >= 6 else []
        s_strong = sum(1 for x in prev5 if x >= 70)
        s_weak = sum(1 for x in prev5 if x < 40)
        use_s, use_w = s_strong >= 3, s_weak >= 3
        cw_struct = 25 if use_s else 15 if use_w else 20
        cw_mtf = 30 if use_s else 10 if use_w else 20
        cw_liq = 20.0
        cw_macro = 15 if use_s else 25 if use_w else 20
        cw_sess = 10 if use_s else 30 if use_w else 20
        cw_tot = cw_struct + cw_mtf + cw_liq + cw_macro + cw_sess
        conf = int(pround((conf_struct * cw_struct + conf_mtf * cw_mtf + conf_liq * cw_liq + conf_macro * cw_macro + conf_sess * cw_sess) / cw_tot))
        conf = int(min(pround(conf * sess_conf_mult[i]), 100))
        conf = int(min(conf, reg_conf_cap[i]))
        vwap_rej_bear = (hi_ >= vwap_up2[i]) and (ci < vwap[i])
        bull_sig_n = int(bull_bos) + int(disp_up) + int(mss_act_b) + int(choch_act_b) + int(smt_bull) + int(sweep_bull) + int(bool(vwap_reject_bull[i]))
        bear_sig_n = int(bear_bos) + int(disp_dn) + int(mss_act_s) + int(choch_act_s) + int(smt_bear) + int(sweep_bear) + int(bool(vwap_rej_bear))
        max_agree = max(bull_sig_n, bear_sig_n)
        pipeline_conflict = bull_sig_n > 0 and bear_sig_n > 0
        if max_agree < 2:
            conf = int(conf * 0.75)
        if not (not isn(var_l[i]) and var_l[i] > 0 and not isn(var_s[i]) and var_s[i] / var_l[i] < 3.0):
            conf = int(conf * 0.85)
        conf_label = "EXTREME" if conf >= 85 else "HIGH" if conf >= 65 else "MEDIUM" if conf >= 40 else "LOW"
        conf_thresh = 45.0 if max(bull_ts[i], bear_ts[i]) >= 70 else 60.0
        regime_conf_high = conf >= conf_thresh

        # ================= weighted evidence composite =================
        ev_tb, ev_ts = float(bull_ts[i]), float(bear_ts[i])
        ev_sb = max(struct_score, 55.0) if choch_bull_sc > 0 else struct_score
        ev_ss = max(100.0 - struct_score, 55.0) if choch_bear_sc > 0 else 100.0 - struct_score
        dpl, dmi_ = dip[i], dim[i]
        ev_fb = (dpl / (dpl + dmi_) * 100.0 if abs(dpl + dmi_) > 1e-10 else 0.0) if dpl > dmi_ else 30.0
        ev_fs = (dmi_ / (dpl + dmi_) * 100.0 if abs(dpl + dmi_) > 1e-10 else 0.0) if dmi_ > dpl else 30.0
        ev_mb = mss_ if mss_ > 0 else 0.0
        ev_ms = abs(mss_) if mss_ < 0 else 0.0
        up_pull = liq_scores["PDH"] + liq_scores["PWH"] + liq_scores["PMH"] + liq_scores["EQH"]
        dn_pull = liq_scores["PDL"] + liq_scores["PWL"] + liq_scores["PML"] + liq_scores["EQL"]
        pt = up_pull + dn_pull
        ev_lb = 30.0 + 30.0 * (up_pull / pt) if pt > 0 else 45.0
        ev_ls = 30.0 + 30.0 * (dn_pull / pt) if pt > 0 else 45.0
        ev_sess = sq * 0.65
        ach = corrh[i]
        ev_cor = ach if ach >= 40 else 30.0
        mri = mr[i]
        ev_mrb = min(abs(mri), 100) if mri <= -30 else 10.0
        ev_mrs = min(abs(mri), 100) if mri >= 30 else 10.0
        k_mod = (regime_strength[i] - 0.5) * 2.0
        w_trend = 0.20 + k_mod * 0.10
        w_struct = 0.18 - k_mod * 0.04
        w_flow, w_macro, w_liq = 0.15, 0.15, 0.12
        w_sess = 0.10 - k_mod * 0.03
        w_corr = 0.05 + k_mod * 0.02
        w_mr = 0.05 - k_mod * 0.05
        raw_bull = ev_tb * w_trend + ev_sb * w_struct + ev_fb * w_flow + ev_mb * w_macro + ev_lb * w_liq + ev_sess * w_sess + ev_cor * w_corr + ev_mrb * w_mr
        raw_bear = ev_ts * w_trend + ev_ss * w_struct + ev_fs * w_flow + ev_ms * w_macro + ev_ls * w_liq + ev_sess * w_sess + ev_cor * w_corr + ev_mrs * w_mr
        adxi = nz(adx[i], 0.0)
        range_ev = 40.0 if adxi < 20 else 25.0 if adxi < 25 else 0.0
        inside = i > 0 and hi_ <= h[i - 1] and li >= l[i - 1]
        range_ev += 20.0 if inside else 0.0
        asma = atr_sma20[i]
        atr_ratio = a / asma if (not isn(asma) and asma > 0.0) else 1.0
        range_ev += 20.0 if atr_ratio < 0.85 else 10.0 if atr_ratio < 1.0 else 0.0
        ema_spread = abs(ema20[i] - ema100[i]) / a if a > 0 and not isn(ema100[i]) else 0.0
        range_ev += 15.0 if ema_spread < 0.5 else 8.0 if ema_spread < 1.0 else 0.0
        range_ev += 10.0 if (num_valid[i] > 0 and ach < 40) else 0.0
        range_ev = min(range_ev, 100.0)
        reg_range_base = 10.0 if regime_trending[i] else 30.0 if regime_ranging[i] else 45.0
        tot_raw = raw_bull + raw_bear
        rb = raw_bull / tot_raw * 100.0 if tot_raw > 0 else 50.0
        rs_ = raw_bear / tot_raw * 100.0 if tot_raw > 0 else 50.0
        range_resid = 100.0 - rb - rs_
        range_blend = range_resid * 0.70 + range_ev * 0.20 + reg_range_base * 0.10
        r_tot = rb + rs_ + range_blend
        bull_score = bear_score = range_score = 0.0
        if r_tot > 0:
            bull_score = float(pround(rb / r_tot * 100.0))
            bear_score = float(pround(rs_ / r_tot * 100.0))
            range_score = 100.0 - bull_score - bear_score
        if range_score < 0:
            excess = abs(range_score)
            range_score = 0.0
            den = bull_score + bear_score
            ratio = bull_score / den if den > 0 else 0.5
            bull_score = max(bull_score - excess * ratio, 5.0)
            bear_score = 100.0 - bull_score
        if bull_score < 5.0 and bear_score < 5.0:
            bull_score, bear_score, range_score = 50.0, 50.0, 0.0
        if bull_score > 95.0:
            bull_score = 95.0
            bear_score = max(bear_score, 5.0)
            range_score = 100.0 - bull_score - bear_score
        if bear_score > 95.0:
            bear_score = 95.0
            bull_score = max(bull_score, 5.0)
            range_score = 100.0 - bull_score - bear_score
        bias_label = ("BULL" if bull_score >= 62 else "BEAR" if bear_score >= 62 else "RANGE" if range_score >= 62
                      else "BULL-ISH" if (bull_score > bear_score and bull_score > range_score)
                      else "BEAR-ISH" if (bear_score > bull_score and bear_score > range_score) else "NEUTRAL")
        tot_r = raw_bull + raw_bear
        pdh_reach = float(pround(raw_bull / tot_r * 100.0)) if tot_r > 0 else 50.0
        pdl_reach = 100.0 - pdh_reach
        if pdh_reach < 5.0:
            pdh_reach, pdl_reach = 5.0, 95.0
        if pdl_reach < 5.0:
            pdl_reach, pdh_reach = 5.0, 95.0

        # ================= entry gates =================
        recent = cfg.backtest_all_bars or i > n - 1 - cfg.recent_bars_len
        news_blk = cfg.use_news_suppress and False   # no news calendar input on the web build
        dd_breach = cfg.use_dd_breaker and dd_for_breaker >= cfg.max_dd_pct
        if arm == "control":
            buy_pre = bt and hgb and mb_ and regime_conf_high and bull_rsi_div and recent and sq >= 30 and not news_blk and not dd_breach
            sell_pre = brt and hgs and mr_b and regime_conf_high and bear_rsi_div and recent and sq >= 30 and not news_blk and not dd_breach
            trig_b = bull_bos or disp_up
            trig_s = bear_bos or disp_dn
        else:
            buy_pre = bt and not hgs and recent and sq >= 30 and not news_blk and not dd_breach
            sell_pre = brt and not hgb and recent and sq >= 30 and not news_blk and not dd_breach
            trig_b = bull_struct_act or disp_up
            trig_s = bear_struct_act or disp_dn
        should_buy = buy_pre and trig_b
        should_sell = sell_pre and trig_s
        blk_why = ""
        if not should_buy and not should_sell:
            bull_side = bull_score >= bear_score
            blk_why = ("DD" if dd_breach else "NEWS" if news_blk else "OLD-BAR" if not recent
                       else f"SESS {int(sq)}/30" if sq < 30
                       else (f"TREND {bull_ts[i] if bull_side else bear_ts[i]}/{cfg.trend_threshold}" if (not bt if bull_side else not brt)
                             else "HTF-OPP" if (hgs if bull_side else hgb) else "NO-TRIGGER"))
        buy_fail = [n_ for n_, ok in (("Trend", bt), ("HTF-Bear", not hgs), ("Recent", recent), ("Sess", sq >= 30),
                                     ("News", not news_blk), ("DD", not dd_breach), ("Trig", bull_struct_act or disp_up)) if not ok]
        sell_fail = [n_ for n_, ok in (("Trend", brt), ("HTF-Bull", not hgb), ("Recent", recent), ("Sess", sq >= 30),
                                      ("News", not news_blk), ("DD", not dd_breach), ("Trig", bear_struct_act or disp_dn)) if not ok]
        buy_log = f"▲{7 - len(buy_fail)}/7" + (f" [✗{' '.join(buy_fail)}]" if buy_fail else "")
        sell_log = f"▼{7 - len(sell_fail)}/7" + (f" [✗{' '.join(sell_fail)}]" if sell_fail else "")
        ctx_log = " ctx:" + ("Rg" if regime_conf_high else "rg") + ("M+" if mb_ else "M-" if mr_b else "M=") + ("R+" if bull_rsi_div else "R-" if bear_rsi_div else "R=")
        trig_log = "" if (bull_struct_act or disp_up or bear_struct_act or disp_dn) else " NO-TRIG"
        conflict_log = " CONFLICT" if pipeline_conflict else ""
        if range_dominant:
            decision_log = f"RANGE {int(range_bias)}/130 [no dir. edge]"
        elif bull_bias >= bear_bias:
            decision_log = buy_log + trig_log + conflict_log + ctx_log
        else:
            decision_log = sell_log + trig_log + conflict_log + ctx_log

        # ================= trade plan (uses the analog grids published up to the previous bar) =================
        plan = trade_plan(i, cfg, should_buy, should_sell, bull_bias, bear_bias, ci, a, reg_sl_mult[i],
                          active_sup, active_res, ob_b_act, ob_bl, ob_bh, ob_s_act, ob_sl, ob_sh, cdl, cdh,
                          pool_pdl, pool_pdh, pool_pwh, pool_pwl, pool_pmh, pool_pml, pool_eql, pool_eqh,
                          val, vah, vpoc, wvwap[i], mvwap[i], AS, sess_spread[i], N, F["mkt_regime"][i])

        # ================= regime transition counters =================
        r_curr = 0 if strong_trend else 1 if moderate_trend else 2
        if r_prev >= 0:
            if r_prev == 0:
                rt["T"] += 1
                if r_curr == 1:
                    rt["TR"] += 1
                elif r_curr == 2:
                    rt["TD"] += 1
            elif r_prev == 1:
                rt["R"] += 1
                if r_curr == 0:
                    rt["RT"] += 1
                elif r_curr == 2:
                    rt["RD"] += 1
            else:
                rt["D"] += 1
                if r_curr == 0:
                    rt["DT"] += 1
                elif r_curr == 1:
                    rt["DR"] += 1
        r_prev = r_curr

        # ================= analog record + outcome label =================
        schema_v = 2 if ((gc_cb[i] or gc_cr[i]) or (oi_valid[i] and oi_conv[i] != 0)) else 1
        data_status = (int(gc_cb[i] or gc_cr[i]) + (2 if (oi_valid[i] and oi_conv[i] != 0) else 0) + (4 if F["US2Y_STATUS"][i] == 0 else 0)
                       + (8 if F["COT_STATUS"][i] == 0 else 0) + (16 if F["GC_STATUS"][i] != 0 else 0) + (32 if F["OI_STATUS"][i] != 0 else 0))
        recorded = cfg.show_stats_engine and i > rec_floor
        if recorded:
            if H["first_rec"] is None:
                H["first_rec"] = i
            cA = 2 if nz(adx[i]) > 25 else 1 if nz(adx[i]) > 15 else 0
            cT = 2 if nz(ap) >= 70 else 1 if nz(ap) >= 30 else 0
            cH = 2 if hgb else 0 if hgs else 1
            cS = 2 if bt else 0 if brt else 1
            cL = 1
            if not isn(pool_pdh) and not isn(pool_pdl):
                cL = 2 if ci > pool_pdh else 0 if ci < pool_pdl else 1
            cM = 2 if mri <= -30 else 0 if mri >= 30 else 1
            cC = 2 if ach >= 60 else 1 if ach >= 40 else 0
            H["zone"][i] = 1.0 if (ob_b_act or (fvg_active and fvg_bull)) else 0.0 if (ob_s_act or (fvg_active and not fvg_bull)) else 0.5
            H["adx_cat"][i], H["atr_cat"][i], H["htf"][i], H["str"][i] = cA, cT, cH, cS
            H["liq"][i], H["mr"][i], H["cor"][i] = cL, cM, cC
            H["pred"][i] = bull_score
            H["race"][i] = -1
            H["calbin"][i] = 4.0 if bull_score >= cal_q[3] else 3.0 if bull_score >= cal_q[2] else 2.0 if bull_score >= cal_q[1] else 1.0 if bull_score >= cal_q[0] else 0.0
            H["bev"][i] = 1 if bull_bos else 2 if bear_bos else 0
            H["bcont"][i] = -1.0
            H["regime"][i] = r_curr
            H["schema"][i] = schema_v
            H["datastatus"][i] = data_status
            H["sess"][i] = 1.0 if in_ny[i] else 0.67 if in_london[i] else 0.33 if in_asian[i] else 0.0
            rr = i - N
            if H["first_rec"] is not None and rr >= H["first_rec"]:
                label_outcome(rr, i, N, H, c, h, l, aatr, reg_sl_mult, high_out_l, low_out_l, pdh_arr, pdl_arr)

        # current-state features for similarity (every bar, for the 100-bar stdevs)
        cur_adx_n = 1.0 if nz(adx[i]) > cfg.adx_threshold else 0.5 if nz(adx[i]) > 15 else 0.0
        cur_zone = 1.0 if (ob_b_act or (fvg_active and fvg_bull)) else 0.0 if (ob_s_act or (fvg_active and not fvg_bull)) else 0.5
        cur_atr_n = ap / 100.0 if not isn(ap) else NaN
        cur_htf_n = 1.0 if hgb else 0.0 if hgs else 0.5
        cur_struct = struct_score / 100.0
        cur_liq = (ci - pool_pdl) / (pool_pdh - pool_pdl) if (not isn(pool_pdh) and not isn(pool_pdl) and pool_pdh != pool_pdl) else 0.5
        cur_mr = clamp((mri + 100.0) / 200.0, 0.0, 1.0)
        cur_cor = clamp(ach / 100.0, 0.0, 1.0)
        cur_sess = 1.0 if in_ny[i] else 0.67 if in_london[i] else 0.33 if in_asian[i] else 0.0
        cur_reg = 1.0 if r_curr == 0 else 0.5 if r_curr == 1 else 0.0
        for k_, vv in (("adx", cur_adx_n), ("atr", cur_atr_n), ("htf", cur_htf_n), ("str", cur_struct), ("liq", cur_liq),
                       ("mr", cur_mr), ("cor", cur_cor), ("sess", cur_sess), ("reg", cur_reg), ("zone", cur_zone)):
            curr_feat[k_][i] = vv
        if i >= 99:
            std = {k_: float(np.std(curr_feat[k_][i - 99:i + 1])) for k_ in ("adx", "atr", "htf", "str", "liq", "mr", "cor", "sess", "reg")}
        else:
            std = {k_: NaN for k_ in ("adx", "atr", "htf", "str", "liq", "mr", "cor", "sess", "reg")}

        # ================= statistics engine =================
        if recorded:
            cur = {"std": std, "vol_regime": vol_regime, "adx_norm": cur_adx_n, "atr_norm": cur_atr_n, "htf_norm": cur_htf_n,
                   "struct": cur_struct, "liq_pos": cur_liq, "mr_norm": cur_mr, "corr_norm": cur_cor, "sess_norm": cur_sess,
                   "reg_norm": cur_reg, "zone": cur_zone, "sess_spread": sess_spread[i], "aatr": a, "r_curr": r_curr, "reg_trans": rt}
            P = {"N": N, "HIST_MAX": HIST_MAX, "show_stats": cfg.show_stats_engine, "holdout_ratio": cfg.holdout_ratio,
                 "adx_threshold": cfg.adx_threshold, "min_match_q": cfg.min_match_q, "slippage": cfg.slippage_pts,
                 "commission": cfg.commission_l, "point_value": cfg.point_value, "risk_percent": cfg.risk_percent,
                 "caps": {"adx": cfg.hist_w_adx, "atr": cfg.hist_w_atr, "htf": cfg.hist_w_htf, "str": cfg.hist_w_str,
                          "liq": cfg.hist_w_liq, "mr": cfg.hist_w_mr, "cor": cfg.hist_w_cor, "sess": cfg.hist_w_sess, "reg": cfg.hist_w_reg}}
            analog.scan(i, AS, H, S, cur, P)
            lo_b = max(H["first_rec"], i - HIST_MAX + 1)
            hN = i - lo_b + 1
            if hN >= 50:
                sp = np.sort(H["pred"][lo_b:i + 1])
                p20, p40, p60, p80 = sp[int(hN * 0.20)], sp[int(hN * 0.40)], sp[int(hN * 0.60)], sp[int(hN * 0.80)]
                if p20 < p40 - 1.0 and p40 < p60 - 1.0 and p60 < p80 - 1.0:
                    cal_q = [float(p20), float(p40), float(p60), float(p80)]
        else:
            hN = 0
        O = AS.out
        o_oos_neff = int(O["oos_n"] / max(N, 1))
        dd_for_breaker = nz(O["max_dd"], 0.0)
        if cfg.show_stats_engine and o_oos_neff >= 10:
            cal_drift_fast = 0.7 * cal_drift_fast + 0.3 * O["cal_grade_pct"]
            cal_drift_slow = 0.95 * cal_drift_slow + 0.05 * O["cal_grade_pct"]
        cal_drift = cfg.show_stats_engine and o_oos_neff >= 10 and cal_drift_fast < cal_drift_slow - 10
        use_raw = cal_drift
        bull_pre = bull_score

        # ================= history blend + forecast adjustment =================
        if cfg.show_stats_engine and o_oos_neff >= 10:
            bull_score = bull_score * 0.7 + O["bull"] * 0.3
            bear_score = bear_score * 0.7 + O["bear"] * 0.3
            range_score = O["range"] if not isn(O["range"]) else range_score
            f_bull, f_bear = bull_score, bear_score
            f_rng = max(100.0 - f_bull - f_bear, 0.0)
        else:
            f_bull, f_bear, f_rng = bull_score, bear_score, range_score
        mom_bars = 0
        if i > 6:
            mom_up, mom_dn = ci > c[i - 1], ci < c[i - 1]
            for k_ in range(1, 6):
                if mom_up and c[i - k_] > c[i - k_ - 1]:
                    mom_bars += 1
                elif mom_dn and c[i - k_] < c[i - k_ - 1]:
                    mom_bars -= 1
                else:
                    break
        mom_score = abs(mom_bars) * 10.0 + (15.0 if adxi > 25 else 8.0 if adxi > 20 else 0.0)
        f_mult = (min(O["match"] / 300.0, 1.0) * (0.20 + 0.10 * min(O["oos_n"] / N / 30.0, 1.0))) if cfg.show_stats_engine else 0.10
        f_sig = 1.0 if bt else -1.0 if brt else 0.0
        fe_base = fe_w = 0.0
        if cfg.show_stats_engine and o_oos_neff >= 10:
            fe_base += min(mom_score * 100.0 / 75.0, 100.0) * 0.25
            fe_w += 0.25
        if liq_max > 0:
            fe_base += nz(liq_reach, 50) * 0.20
            fe_w += 0.20
        if cfg.show_stats_engine and O["reg_per"] >= 30:
            fe_base += nz(O["reg_per"], 50) * 0.15
            fe_w += 0.15
        f_adj = (fe_base / fe_w - 50.0) * f_mult * f_sig if fe_w > 0 else 0.0
        if f_adj * fadj_hist[-1] < 0 or f_adj * fadj_hist[-2] < 0:
            f_adj *= 0.5
        fadj_hist = [fadj_hist[-1], f_adj]
        f_bull = clamp(f_bull + f_adj, 5.0, 95.0)
        f_bear = 100.0 - f_bull - f_rng
        if f_bear < 0:
            f_bear = 0.0
            f_rng = max(100.0 - f_bull - f_bear, 0.0)
            r_ = f_bull / (f_bull + f_bear + 1)
            f_bull = max(100.0 * r_, 5.0)
            f_bear = 100.0 - f_bull
        bull_score, bear_score, range_score = normalize_scores(f_bull, f_bear, f_rng, 1.0)
        if recorded:
            H["pred"][i] = bull_score
            H["calbin"][i] = 4.0 if bull_score >= cal_q[3] else 3.0 if bull_score >= cal_q[2] else 2.0 if bull_score >= cal_q[1] else 1.0 if bull_score >= cal_q[0] else 0.0

        # ================= calibrated probability =================
        cal_p_raw = bull_score / 100.0
        cal_prob = cal_p_raw
        cal_prob_bear = NaN
        cal_prob_str = ""
        if cfg.show_stats_engine and O["match"] >= 30:
            if use_raw:
                cal_prob = bull_score / 100.0
            else:
                cp = bull_score / 100.0
                fit = AS.cal_fit
                pf_ok = not isn(fit[0])
                if pf_ok:
                    cp = clamp(1.0 / (1.0 + math.exp(-((bull_score - 50.0) * fit[0] + fit[1]))), 0.05, 0.95)
                fb = AS.cal_fit_bear
                bf_ok = not isn(fb[0])
                cpb = NaN
                if bf_ok:
                    cpb = clamp(1.0 / (1.0 + math.exp(-((bull_score - 50.0) * fb[0] + fb[1]))), 0.05, 0.95)
                if range_score > bull_score and range_score > bear_score:
                    cal_prob = 0.5
                    cal_prob_bear = 0.5 if bf_ok else NaN
                else:
                    cal_prob = cp
                    cal_prob_bear = cpb
                rg_i = int(clamp(r_curr, 0, 2))
                reg_t, reg_w = AS.reg_tot[rg_i], AS.reg_win[rg_i]
                if reg_t >= 20:
                    reg_rate = reg_w / reg_t
                    overall = O["wr"] / 100.0
                    reg_adj = clamp(reg_rate / overall if overall > 0 else 1.0, 0.67, 1.5)
                    cal_prob = clamp(0.5 + (cal_prob - 0.5) * reg_adj, 0.05, 0.95)
            cal_prob_str = (f"mP={int(pround(cal_prob * 100))}" + ("" if isn(cal_prob_bear) else f"/S{int(pround(cal_prob_bear * 100))}") + "%") \
                if (not isn(AS.cal_fit[0]) or use_raw) else "mP unfit"
        cal_both = not isn(cal_prob) and not isn(cal_prob_bear) and cal_prob + cal_prob_bear > 0
        p_long = cal_prob / (cal_prob + cal_prob_bear) if cal_both else cal_prob
        p_short = cal_prob_bear / (cal_prob + cal_prob_bear) if cal_both else (NaN if isn(cal_prob) else 1.0 - cal_prob)

        # ================= trade quality =================
        tp_long = plan["long"]
        plan_ev = plan["ev"]
        tq_sum = tq_w = 0.0
        tq_trend = bull_ts[i] if tp_long else bear_ts[i]
        tw_trend = 0.22 if (reg_str[i] or reg_exp[i]) else 0.14 if not (reg_wk[i] or reg_str[i] or reg_exp[i]) else 0.18
        tq_sum += min(tq_trend, 100.0) * tw_trend; tq_w += tw_trend
        tq_sum += min(struct_score, 100.0) * 0.15; tq_w += 0.15
        tq_sum += min(liq_health, 100.0) * 0.10; tq_w += 0.10
        if tp_long and ob_b_act:
            zref = ob_bh
        elif (not tp_long) and ob_s_act:
            zref = ob_sl
        elif fvg_active:
            zref = (fvg_hu + fvg_ll) / 2.0
        else:
            zref = NaN
        zdist = abs(ci - zref) / a if (not isn(zref) and a > 0) else NaN
        zbase = 100.0 if ((tp_long and ob_b_act) or ((not tp_long) and ob_s_act)) else 60.0 if fvg_active else 0.0
        tq_zone = 20.0 if isn(zdist) else max(zbase * math.exp(-zdist / 2.0), 20.0)
        tq_sum += tq_zone * 0.10; tq_w += 0.10
        tq_macro = clamp(50.0 + (1.0 if tp_long else -1.0) * mtf_conf_score / 2.0, 0.0, 100.0)
        tq_sum += tq_macro * 0.15; tq_w += 0.15
        tw_sess = 0.12 if not (reg_wk[i] or reg_str[i] or reg_exp[i] or reg_abn[i]) else 0.08
        tq_sum += min(sq, 100) * tw_sess; tq_w += tw_sess
        tq_reg = 10.0 if reg_abn[i] else 35.0 if reg_cmp[i] else 85.0 if (reg_str[i] or reg_exp[i]) else 65.0 if reg_wk[i] else 45.0
        tq_sum += tq_reg * 0.09; tq_w += 0.09
        tq_has_hist = o_oos_neff >= 10
        if tq_has_hist:
            tq_hist = O["oos_wr"] if tp_long else nz(AS.oos_bear_wr, 100.0 - O["oos_wr"])
            tq_hw = 0.10 * min(o_oos_neff / 50.0, 1.0)
            tq_sum += tq_hist * tq_hw; tq_w += tq_hw
        tq_timing = 100.0 if in_kz[i] else 60.0 if (in_london[i] or in_ny[i]) else 25.0
        tq_sum += tq_timing * 0.05; tq_w += 0.05
        if not isn(plan_ev):
            tx = clamp(plan_ev / 0.75, -10.0, 10.0)
            e2 = math.exp(2.0 * tx)
            tq_sum += (50.0 + 50.0 * ((e2 - 1.0) / (e2 + 1.0))) * 0.10; tq_w += 0.10
        trade_quality = int(pround(clamp(tq_sum / tq_w, 0.0, 100.0))) if tq_w > 0 else 50
        tq_basis = ("" if tq_has_hist else "-H") + ("" if not isn(plan_ev) else "-F")

        # ================= auction intelligence =================
        if crossed_day[i]:
            prev_day_value = prev_vwap if not isn(prev_vwap) else vwap[i]
        val_mig = (vwap[i] - prev_day_value) / a if (not isn(prev_day_value) and a > 0) else NaN
        val_mig_str = "VAL n/a" if isn(val_mig) else "VAL⇈" if val_mig > 0.8 else "VAL↑" if val_mig > 0.3 else "VAL⇊" if val_mig < -0.8 else "VAL↓" if val_mig < -0.3 else "VAL="
        above_val = ci > vwap[i]
        prev_above = (c1 if not isn(c1) else ci) > (prev_vwap if not isn(prev_vwap) else vwap[i])
        bars_on_side = min(bars_on_side + 1, 40) if above_val == prev_above else 1
        close_loc = (ci - li) / (hi_ - li) if hi_ > li else 0.5
        c5 = c[i - 5] if i >= 5 else ci
        ft_atr = min(abs(ci - c5) / a, 2.0) if a > 0 else 0.0
        accept = int(min(min(bars_on_side, 40) * 1.0 + (20 if rel_vol > 1.0 else 10 if rel_vol > 0.7 else 0)
                         + (close_loc if above_val else 1.0 - close_loc) * 20 + ft_atr * 10, 100))
        accept_grade = "A+" if accept >= 85 else "A" if accept >= 70 else "B" if accept >= 55 else "C" if accept >= 40 else "D"
        if sweep_bull or sweep_bear:
            pen = min((abs(li - ci) if sweep_bull else abs(hi_ - ci)) / a, 1.5) if a > 0 else 0.0
            rev = ((ci - li) / (hi_ - li) if sweep_bull else (hi_ - ci) / (hi_ - li)) if hi_ > li else 0.5
            last_sweep_q = int(min(pen * 30 + nz(vol_pct) * 0.3 + rev * 30 + (10 if ((sweep_bull and disp_up) or (sweep_bear and disp_dn)) else 0), 100))
            last_sweep_grade = "INST" if last_sweep_q >= 80 else "STRONG" if last_sweep_q >= 65 else "MOD" if last_sweep_q >= 50 else "WEAK"
        val_dist = abs(ci - vwap[i]) / a if a > 0 else 0.0
        disc = min(val_dist * 25 + nz(ap) * 0.25 + min(adxi, 40) * 1.0 + accept * 0.25, 100)
        disc_hist.append(disc)
        disc_hi10 = max(disc_hist[-10:])
        disc_str = ("DISC:EXH" if (disc >= 70 and (reg_abn[i] or climax_up or climax_dn)) else "DISC:ACCPT" if (disc >= 70 and accept >= 60)
                    else "DISC:CONF" if disc >= 70 else "DISC:DEV" if disc >= 50 else "DISC:FAIL" if (disc < 30 and disc_hi10 >= 50)
                    else "DISC:WEAK" if disc >= 30 else "ROTATION")
        st_bal = (50.0 if (reg_cmp[i] or (not reg_str[i] and not reg_exp[i] and adxi < cfg.adx_threshold)) else 0.0) + (30.0 if val_dist < 0.8 else 0.0) + (20.0 if nz(ap) <= 40 else 0.0)
        st_trend = (45.0 if reg_str[i] else 20.0 if reg_wk[i] else 0.0) + accept * 0.3 + (25.0 if disc >= 50 else 0.0)
        st_rot = (45.0 if range_score > max(bull_score, bear_score) else 0.0) + (25.0 if val_dist < 1.0 else 0.0) + (20.0 if adxi < cfg.adx_threshold else 0.0)
        st_disc = (40.0 if reg_exp[i] else 0.0) + (30.0 if val_dist >= 1.0 else 0.0) + (20.0 if nz(ap) >= 60 else 0.0)
        st_acc = 40.0 + accept * 0.4 if (accept >= 60 and val_dist >= 0.8) else 0.0
        st_rej = (50.0 if (sweep_bull or sweep_bear) else 30.0 if ses_manip else 0.0) + (25.0 if (last_sweep_q >= 65 and (sweep_bull or sweep_bear)) else 0.0)
        st_exh = (40.0 if reg_abn[i] else 0.0) + (35.0 if (climax_up or climax_dn) else 0.0) + (15.0 if nz(ap) >= 90 else 0.0)
        vdkq = nz(vol_delta50[i]) / 1000.0
        st_ad = 35.0 + min(abs(vdkq) * 5.0, 25.0) if (st_bal > 30 and abs(vdkq) > 1.0) else 0.0
        st_sum = st_bal + st_trend + st_rot + st_disc + st_acc + st_rej + st_exh + st_ad
        st_max = max(st_bal, st_trend, st_rot, st_disc, st_acc, st_rej, st_exh, st_ad)
        if st_sum <= 0:
            auc_state = "BALANCE"
        elif st_max == st_rej:
            auc_state = "REJ-HI" if (sweep_bear or (ses_manip and not sweep_bull)) else "REJ-LO"
        elif st_max == st_exh:
            auc_state = "EXHAUST"
        elif st_max == st_trend:
            auc_state = "TREND-AUC"
        elif st_max == st_acc:
            auc_state = "ACC-HI" if above_val else "ACC-LO"
        elif st_max == st_disc:
            auc_state = "DISCOVERY"
        elif st_max == st_ad:
            auc_state = "ACCUM" if vdkq > 0 else "DISTRIB"
        elif st_max == st_rot:
            auc_state = "ROTATE"
        else:
            auc_state = "BALANCE"
        auc_prob = int(st_max / st_sum * 100.0) if st_sum > 0 else 0
        auc_cycle = ("①BAL" if auc_state in ("BALANCE", "ACCUM", "DISTRIB") else "②INIT" if auc_state == "ROTATE" else "③DISC" if auc_state == "DISCOVERY"
                     else "④TEST" if auc_state in ("REJ-HI", "REJ-LO") else "⑤ACPT" if auc_state in ("ACC-HI", "ACC-LO") else "⑥TRND" if auc_state == "TREND-AUC" else "⑦EXH")
        if prev_sess_id is not None and sess_id != prev_sess_id:
            sess_age = 0
        else:
            sess_age += 1
        prev_sess_id = sess_id
        open_type = ""
        if not isn(ses_open) and not isn(ses_hi) and 0 <= cur_sess_id <= 2:
            upx, dnx = ses_hi - ses_open, ses_open - ses_lo
            rngx = max(ses_hi - ses_lo, 0.01)
            one_side = max(upx, dnx) / rngx
            past_open = (ci - ses_open) * (1 if upx > dnx else -1) < 0
            gap_up = not isn(prev_ses_hi) and ses_open > prev_ses_hi
            gap_dn = not isn(prev_ses_lo) and ses_open < prev_ses_lo
            gap_filled = (gap_up and li <= prev_ses_hi) or (gap_dn and hi_ >= prev_ses_lo)
            if gap_up or gap_dn:
                open_type = "GAP-FILL" if gap_filled else "GAP-DRV" if one_side >= 0.7 else "O-AUC"
            elif rngx < a * 0.7:
                open_type = "O-NEU"
            elif rngx < a:
                open_type = "O-AUC"
            elif one_side >= 0.85:
                open_type = "DLY-DRV" if sess_age > 12 else "O-DRV"
            elif one_side >= 0.7 and past_open:
                open_type = "O-REJ"
            elif one_side >= 0.7:
                open_type = "O-TDR"
            else:
                open_type = "O-AUC"

        # ================= vetoes =================
        eff_tq_min = 0 if cfg.tq_min_score == 0 else int(clamp(cfg.tq_min_score + (15 if reg_abn[i] else 10 if reg_cmp[i] else -5 if (reg_str[i] or reg_exp[i]) else 0), 0, 90))
        cot_damp = 0 if cot_regime[i] == 0 else (5 if ((cot_regime[i] == -1 and should_buy) or (cot_regime[i] == 1 and should_sell)) else 0)
        cal_gate_ready = cfg.use_cal_gate and not isn(AS.cal_fit[0]) and o_oos_neff >= 10 and not isn(cal_prob)
        cal_veto = cal_gate_ready and ((should_buy and p_long < cfg.cal_gate_min_p) or (should_sell and p_short < cfg.cal_gate_min_p))
        eff_tq_min_cot = min(eff_tq_min + cot_damp, 95)
        tq_floor_veto = eff_tq_min_cot > 0 and trade_quality < eff_tq_min_cot
        ev_veto = (not isn(plan_ev)) and plan_ev < 0.0
        tq_veto = tq_floor_veto or ev_veto or cal_veto

        # ================= account-state risk limits (virtual-R tracker) =================
        if crossed_day[i]:
            rk_day_r = 0.0
            rk_day_n = 0
            if cfg.lockout_bars == 0:
                risk_lock = False
                rk_consec = 0
        if not isn(rk_entry):
            rk_r = max(abs(rk_entry - rk_sl), a * 0.2)
            hit_sl = li <= rk_sl if rk_long else hi_ >= rk_sl
            hit_tp = hi_ >= rk_tp if rk_long else li <= rk_tp
            if hit_sl or hit_tp:
                res_ = -1.0 if hit_sl else min(abs(rk_tp - rk_entry) / rk_r, 5.0)
                events.append({"i": i, "type": "TRACK_EXIT", "dir": 1 if rk_long else -1, "px": rk_sl if hit_sl else rk_tp, "r": res_, "sl": hit_sl})
                rk_day_r += res_
                rk_consec = rk_consec + 1 if res_ < 0 else 0
                rk_entry = NaN
        loss_hit = cfg.max_daily_loss_r > 0 and rk_day_r <= -cfg.max_daily_loss_r
        cap_hit = cfg.max_trades_day > 0 and rk_day_n >= cfg.max_trades_day
        streak_hit = cfg.max_consec_loss > 0 and rk_consec >= cfg.max_consec_loss
        if cfg.use_risk_limits and (loss_hit or cap_hit or streak_hit) and not risk_lock:
            risk_lock = True
            rk_lock_bar = i
        if risk_lock and cfg.lockout_bars > 0 and i - rk_lock_bar >= cfg.lockout_bars:
            risk_lock = False
            rk_consec = 0
        if (should_buy or should_sell) and not tq_veto and not risk_lock and isn(rk_entry) and not isn(plan["sl"]) and not isn(plan["tp1"]):
            rk_entry, rk_sl, rk_tp, rk_long = ci, plan["sl"], plan["tp1"], should_buy
            rk_day_n += 1
        risk_lock_str = "" if not cfg.use_risk_limits else (("LOCK:DAYLOSS" if loss_hit else "LOCK:MAXTRADES" if cap_hit else "LOCK:LOSSSTREAK") if risk_lock
                                                           else f"R{rk_day_r:.1f} N{rk_day_n}" + (f" L{rk_consec}" if rk_consec > 0 else ""))
        tq_veto = tq_veto or (cfg.use_risk_limits and risk_lock)
        stats_warm = (not cfg.show_stats_engine) or (hN > N * 2 and o_oos_neff >= 10)
        rk_blocked = (should_buy or should_sell) and cfg.use_risk_limits and risk_lock
        tq_blocked = (should_buy or should_sell) and tq_veto
        conf_dir_label = "RISK LOCK" if rk_blocked else "NO TRADE" if tq_blocked else "BUY" if should_buy else "SELL" if should_sell else "WARMUP" if not stats_warm else "WAIT"
        exec_buy = should_buy and not tq_veto
        exec_sell = should_sell and not tq_veto
        if conf_dir_label != prev_conf_label:
            events.append({"i": i, "type": "DECISION", "from": prev_conf_label, "to": conf_dir_label})
        if exec_buy or exec_sell:
            events.append({"i": i, "type": "SIGNAL", "dir": 1 if exec_buy else -1, "px": ci, "tq": trade_quality,
                           "sl": plan["sl"], "tp1": plan["tp1"], "tp2": plan["tp2"], "tp3": plan["tp3"]})
        elif should_buy or should_sell:
            events.append({"i": i, "type": "VETO", "dir": 1 if should_buy else -1, "px": ci,
                           "why": "RISK" if rk_blocked else "P" if cal_veto else "EV" if ev_veto else "TQ"})
        if cfg.use_risk_limits and risk_lock and not prev_risk_lock:
            events.append({"i": i, "type": "RISK_LOCK", "why": risk_lock_str})
        prev_conf_label = conf_dir_label
        prev_risk_lock = risk_lock

        # gate funnel
        fn["bars"] += 1
        fn["trend"] += int(bt or brt)
        fn["htf"] += int((bt and not hgs) or (brt and not hgb))
        fn["pre"] += int(buy_pre or sell_pre)
        if should_buy or should_sell:
            fn["sig"] += 1
            fn["tq"] += int(tq_floor_veto)
            fn["ev"] += int(ev_veto)
            fn["cal"] += int(cal_veto)
            fn["risk"] += int(cfg.use_risk_limits and risk_lock)
            fn["pass_"] += int(not tq_veto)
        # V1/V2 regime shadow
        mbv1 = mbv[i] - int(gc_cb[i])
        mbr1 = mbr[i] - int(gc_cr[i])
        mr1 = 100 if (mbv1 >= 3 or mbr1 >= 3) else 60 if (mbv1 >= 2 or mbr1 >= 2) else 30
        rcv1 = regime_score * 0.30 + vol_regime * 0.15 + structure_regime * 0.20 + mr1 * 0.20 + session_regime * 0.15
        rc1 = int(pround(rcv1))
        rcurr1 = 0 if rcv1 >= 70 else 1 if rcv1 >= 40 else 2
        shd["bars"] += 1
        if regime_comp != rc1:
            shd["dcomp"] += 1
            shd["maxabs"] = max(shd["maxabs"], abs(regime_comp - rc1))
        shd["regchg"] += int(r_curr != rcurr1)
        shd["x40"] += int((rc1 < 40) != (regime_comp < 40))
        shd["x70"] += int((rc1 < 70) != (regime_comp < 70))
        # day-of-week tracker
        dw = dow[i]
        if 2 <= dw <= 6:
            db, dr_ = bt and mb_, brt and mr_b
            dow_bull[dw] = dow_bull[dw] * 0.995 + (1.0 if db else 0.0)
            dow_bear[dw] = dow_bear[dw] * 0.995 + (1.0 if (dr_ and not db) else 0.0)

        # ================= per-bar rows =================
        R_ = rows
        R_["bull"][i], R_["bear"][i], R_["range"][i], R_["bull_pre"][i] = bull_score, bear_score, range_score, bull_pre
        R_["struct"][i] = struct_score
        R_["pdh"][i], R_["pdl"][i], R_["pwh"][i], R_["pwl"][i] = pool_pdh, pool_pdl, pool_pwh, pool_pwl
        R_["cdh"][i], R_["cdl"][i], R_["eqh"][i], R_["eql"][i] = cdh, cdl, pool_eqh, pool_eql
        R_["should_buy"][i], R_["should_sell"][i], R_["tq_veto"][i] = should_buy, should_sell, tq_veto
        R_["tq"][i], R_["conf"][i], R_["dir_label"][i] = trade_quality, conf, conf_dir_label
        R_["plan_long"][i], R_["plan_entry"][i], R_["plan_sl"][i] = plan["long"], plan["entry"], plan["sl"]
        R_["plan_tp1"][i], R_["plan_tp2"][i], R_["plan_tp3"][i] = plan["tp1"], plan["tp2"], plan["tp3"]
        R_["plan_rr1"][i], R_["plan_ev"][i] = plan["rr1"], plan["ev"]
        R_["cal_p_long"][i], R_["cal_p_short"][i] = p_long, p_short
        R_["exec_buy"][i], R_["exec_sell"][i] = exec_buy, exec_sell
        R_["ob_bull_lo"][i], R_["ob_bull_hi"][i] = (ob_bl, ob_bh) if ob_b_act else (NaN, NaN)
        R_["ob_bear_lo"][i], R_["ob_bear_hi"][i] = (ob_sl, ob_sh) if ob_s_act else (NaN, NaN)
        R_["fvg_hi"][i], R_["fvg_lo"][i], R_["fvg_bull"][i] = (fvg_hu, fvg_ll, fvg_bull) if fvg_active else (NaN, NaN, None)
        R_["vpoc"][i], R_["vah"][i], R_["val"][i] = vpoc, vah, val
        R_["risk_lock"][i], R_["cal_veto"][i], R_["ev_veto"][i], R_["tq_floor_veto"][i] = risk_lock, cal_veto, ev_veto, tq_floor_veto
        R_["bias_label"][i], R_["regime_label"][i], R_["sess_label"][i] = bias_label, F["mkt_regime"][i], F["session_label"][i]
        R_["active_res"][i], R_["active_sup"][i] = active_res, active_sup
        for k_ in ("adx", "atr", "htf", "str", "liq", "mr", "cor", "sess", "reg", "zone"):
            R_["curr_" + ("struct" if k_ == "str" else k_)][i] = curr_feat[k_][i]
        prev_disp_up, prev_disp_dn = prev_disp_up_now, prev_disp_dn_now
        prev_vwap = vwap[i]

        if i == n - 1:
            last = dict(
                i=i, close=ci, atr=atr[i], aatr=a, adx=adx[i], should_buy=should_buy, should_sell=should_sell,
                bull_score=bull_score, bear_score=bear_score, range_score=range_score, bull_pre=bull_pre,
                bias_label=bias_label, bias_call=bias_call, bull_bias=bull_bias, bear_bias=bear_bias, range_bias=range_bias,
                confidence=conf, conf_label=conf_label, trade_quality=trade_quality, tq_basis=tq_basis,
                tq_grade="A" if trade_quality >= 80 else "B" if trade_quality >= 65 else "C" if trade_quality >= 50 else "D",
                eff_tq_min=eff_tq_min_cot, tq_veto=tq_veto, tq_floor_veto=tq_floor_veto, ev_veto=ev_veto, cal_veto=cal_veto,
                cal_gate_ready=cal_gate_ready, decision=conf_dir_label, decision_log=decision_log, blk_why=blk_why,
                plan=plan, cal_prob=cal_prob, cal_prob_bear=cal_prob_bear, p_long=p_long, p_short=p_short, cal_prob_str=cal_prob_str,
                cal_drift=cal_drift, cal_fit=list(AS.cal_fit), cal_fit_bear=list(AS.cal_fit_bear),
                struct=dict(bull_act=bull_struct_act, bear_act=bear_struct_act, bull_type=bull_struct_type, bear_type=bear_struct_type,
                            bull_age=bull_struct_age, bear_age=bear_struct_age, struct_score=struct_score,
                            bos_label_bull=bos_lab_b, bos_label_bear=bos_lab_s, choch_bull=choch_lab_b, choch_bear=choch_lab_s,
                            mss_bull=mss_lab_b, mss_bear=mss_lab_s, disp_up=disp_up, disp_dn=disp_dn,
                            choch_bull_score=choch_bull_sc, choch_bear_score=choch_bear_sc,
                            active_res=active_res, active_sup=active_sup, swing_res=s_active_res, swing_sup=s_active_sup),
                zones=dict(ob_bull=[ob_bl, ob_bh] if ob_b_act else None, ob_bear=[ob_sl, ob_sh] if ob_s_act else None,
                           ob_bull_mit=ob_b_mitpct, ob_bear_mit=ob_s_mitpct,
                           fvg=[fvg_ll, fvg_hu, fvg_bull] if fvg_active else None, eqh=pool_eqh, eql=pool_eql),
                liquidity=dict(pools={nm: p for nm, p, _, _ in pools}, scores=liq_scores, dest=liq_dest, dest_score=liq_dest_score,
                               dest_secondary=liq_dest_sec, dest_conf=liq_dest_conf, reach=liq_reach, health=liq_health,
                               sweep_bull=sweep_bull, sweep_bear=sweep_bear, cdh=cdh, cdl=cdl,
                               reach_scores=dict(PDH=pdh_reach, PDL=pdl_reach)),
                regime=dict(label=F["mkt_regime"][i], vol_tag=F["vol_tag"][i], composite=regime_comp, r_curr=r_curr,
                            strong=strong_trend, moderate=moderate_trend, weak=weak_trend, sl_mult=reg_sl_mult[i],
                            conf_cap=int(reg_conf_cap[i]), atr_pct=ap, strength=regime_strength[i], vol_regime=vol_regime,
                            structure_regime=structure_regime, macro_regime=macro_regime, session_regime=session_regime,
                            transitions=dict(rt)),
                session=dict(label=F["session_label"][i], quality=sq, sess_id=sess_id, exp_pct=sess_exp_pct,
                             manip_prob=sess_manip_prob, cont_prob=sess_cont_prob, manip=ses_manip, conf_mult=sess_conf_mult[i],
                             spread=sess_spread[i], ses_hi=ses_hi, ses_lo=ses_lo, open_type=open_type),
                mtf=dict(conf_score=mtf_conf_score, tier="A:HI" if mtf_hi else "A:MED" if mtf_med else "A:LO",
                         scores={k: float(F["htf_scores"][k][i]) for k in F["htf_scores"]}, align_long=al_l, align_short=al_s),
                macro=dict(label=macro_label, strength=mss_, conf=mic, bull=mb_, bear=mr_b, bull_votes=int(mbv[i]), bear_votes=int(mbr[i])),
                auction=dict(state=auc_state, prob=auc_prob, cycle=auc_cycle, disc=disc_str, accept=accept, accept_grade=accept_grade,
                             value_mig=val_mig_str, open_type=open_type, sweep_q=last_sweep_q, sweep_grade=last_sweep_grade,
                             bias=("LONG-REV" if auc_state == "REJ-LO" else "LONG-CONT") if (should_buy and not tq_veto)
                             else ("SHORT-REV" if auc_state == "REJ-HI" else "SHORT-CONT") if (should_sell and not tq_veto)
                             else "NO-TRADE" if (should_buy or should_sell) else "WAIT"),
                flow=dict(cvd_bull=bool(F["cvd_bull"][i]), vd_k=vdkq, vpoc=vpoc, vah=vah, val=val, va_ratio=va_ratio, va_pos=va_pos,
                          rel_vol=rel_vol, vol_pct=vol_pct, climax_up=climax_up, climax_dn=climax_dn),
                signals=dict(bull=bull_sig_n, bear=bear_sig_n, conflict=pipeline_conflict, smt_bull=smt_bull, smt_bear=smt_bear),
                risk=dict(lock=risk_lock, lock_str=risk_lock_str, day_r=rk_day_r, day_n=rk_day_n, consec=rk_consec,
                          open_entry=rk_entry, open_sl=rk_sl, open_tp=rk_tp, open_long=rk_long),
                stats_warm=stats_warm, hN=hN, oos_neff=o_oos_neff, analog=dict(AS.out), analog_scan=dict(AS.last_scan),
                hit_prob=list(AS.hit_prob), hit_n=AS.hit_n, race_prob=list(AS.race_prob), race_n=AS.race_n,
                oos_bear_wr=AS.oos_bear_wr, cal_rel=list(AS.cal_rel), cal_q=list(cal_q), reg_tot=list(AS.reg_tot), reg_win=list(AS.reg_win),
                funnel=dict(fn), shadow=dict(shd), dow_bull=list(dow_bull), dow_bear=list(dow_bear),
                schema_v=schema_v, data_status=data_status, mom_score=mom_score, f_adj=f_adj,
                what_if=what_if(i, F, bt, brt, hgb, hgs, mss_, adxi, cfg, ev_lb, ev_ls, pool_pdh, pool_pdl),
                census=census(H, lo_b if recorded else None, i),
            )

    rows_np = {}
    for k_, vals in rows.items():
        try:
            rows_np[k_] = np.array([NaN if x is None else x for x in vals], dtype=float)
        except (TypeError, ValueError):
            rows_np[k_] = np.array(vals, dtype=object)
    return Result(cfg=cfg, arm=arm, F=F, rows=rows_np, events=events, last=last, analog=AS, outcome_n=N,
                  hist_max=HIST_MAX, params={"cal_q": cal_q, "H": H})


def label_outcome(r, i, N, H, c, h, l, aatr, reg_sl_mult, high_out, low_out, pdh_arr, pdl_arr):
    """Pine outcome block (Q7.0 race + F-A19 first-touch ladder) for the record at bar r."""
    fc = c[i] - c[r]
    fh, fl = high_out[i], low_out[i]
    if isn(fh) or isn(fl) or fh - fl <= 0:
        return
    ent = c[r]
    o_r = nz(aatr[r]) * nz(reg_sl_mult[r], 1.5)
    scan_end = min(i, r + 60)
    res = 0
    if o_r > 0:
        for k in range(r + 1, scan_end + 1):
            if res == 0:
                res = -1 if l[k] <= ent - o_r else (1 if h[k] >= ent + o_r else 0)
        H["out"][r] = res
        tU = [9999, 9999, 9999]
        tD = [9999, 9999, 9999]
        for ti, k in enumerate(range(r + 1, scan_end + 1)):
            for m_ in range(3):
                if tU[m_] == 9999 and h[k] >= ent + (m_ + 1) * o_r:
                    tU[m_] = ti
                if tD[m_] == 9999 and l[k] <= ent - (m_ + 1) * o_r:
                    tD[m_] = ti
        L_ = [2 if (tD[0] < 9999 and tD[0] <= tU[m_]) else 1 if tU[m_] < 9999 else 0 for m_ in range(3)]
        S_ = [2 if (tU[0] < 9999 and tU[0] <= tD[m_]) else 1 if tD[m_] < 9999 else 0 for m_ in range(3)]
        H["race"][r] = L_[0] + 3 * L_[1] + 9 * L_[2] + 27 * S_[0] + 81 * S_[1] + 243 * S_[2]
        H["term"][r] = fc / o_r
    else:
        H["out"][r] = 0
    H["ret"][r] = float(res) if res != 0 else (fc / o_r if o_r > 0 else 0.0)
    H["runit"][r] = o_r
    be = H["bev"][r]
    if be == 1:
        H["bcont"][r] = 1.0 if fc > 0 else 0.0
    elif be == 2:
        H["bcont"][r] = 1.0 if fc < 0 else 0.0
    pdu, pdl = pdh_arr[r], pdl_arr[r]
    if not isn(pdu) and not isn(pdl):
        f = 0
        for k in range(r + 1, i):
            if f == 0 and h[k] >= pdu:
                f = 1
            if f == 0 and l[k] <= pdl:
                f = 2
            if f != 0:
                break
        H["first"][r] = f


def normalize_scores(b, be, r, floor):
    nb, nbe, nr = min(b, 95.0), min(be, 95.0), max(r, 0.0)
    tot = nb + nbe + nr
    if tot > 100.0:
        rb, rbe = nb / tot, nbe / tot
        nb = clamp(pround(100.0 * rb), floor, 95.0)
        nbe = clamp(pround(100.0 * rbe), floor, 95.0)
        nr = max(100.0 - nb - nbe, 0.0)
    else:
        nb, nbe = max(nb, floor), max(nbe, floor)
        tot = nb + nbe + nr
        if tot > 100.0:
            ex = tot - 100.0
            if nr >= ex:
                nr -= ex
            else:
                ex -= nr
                nr = 0.0
                brat = nb / max(nb + nbe, 1.0)
                be_adj = min(pround(ex * (1.0 - brat)), nbe)
                nb = nb - min(pround(ex * brat), nb)
                nbe = nbe - be_adj
        else:
            nr = max(100.0 - nb - nbe, 0.0)
    if r > 0 and nr < floor:
        deficit = floor - nr
        bshare = pround(deficit * nb / max(nb + nbe, 1.0))
        nb -= bshare
        nbe -= (deficit - bshare)
        nr = floor
    if nr < 0:
        nr = 0.0
    return float(nb), float(nbe), float(nr)


def trade_plan(i, cfg, should_buy, should_sell, bull_bias, bear_bias, close, a, reg_sl, active_sup, active_res,
               ob_b_act, ob_bl, ob_bh, ob_s_act, ob_sl, ob_sh, cdl, cdh, pdl, pdh, pwh, pwl, pmh, pml, eql, eqh,
               val, vah, vpoc, wvwap, mvwap, AS, sess_spread, N, regime_label):
    """R6.0 dynamic trade plan (Pine f_tradePlan)."""
    long_ = True if should_buy else False if should_sell else bull_bias >= bear_bias
    entry = close
    sl_base = a * reg_sl
    sl_lo, sl_hi = a * 0.6, sl_base * 1.6
    basis = "ATR"
    sl = close - sl_base if long_ else close + sl_base
    if long_:
        cands = [(active_sup, "Swing"), (ob_bl if ob_b_act else NaN, "OB"), (cdl, "CDL"), (pdl, "PDL"), (eql, "EQL"),
                 (val, "VAL"), (wvwap if wvwap < close else NaN, "wVWAP")]
    else:
        cands = [(active_res, "Swing"), (ob_sh if ob_s_act else NaN, "OB"), (cdh, "CDH"), (pdh, "PDH"), (eqh, "EQH"),
                 (vah, "VAH"), (wvwap if wvwap > close else NaN, "wVWAP")]
    best = 1e10
    for lv, nm in cands:
        if not isn(lv) and ((long_ and lv < close) or (not long_ and lv > close)):
            d = abs(close - lv) + a * 0.15
            if sl_lo <= d <= sl_hi and d < best:
                best = d
                sl = lv - a * 0.15 if long_ else lv + a * 0.15
                basis = nm
    rn = pround(sl / cfg.rn_grid) * cfg.rn_grid
    if abs(sl - rn) < a * 0.05:
        sl = rn - a * 0.2 if long_ else rn + a * 0.2
    r_min, r_max = a * 0.5, a * 5.0
    r_raw = abs(entry - sl)
    if isn(r_raw) or r_raw < r_min or r_raw > r_max:
        fix = clamp(nz(r_raw, r_min), r_min, r_max)
        sl = entry - fix if long_ else entry + fix
        basis += "*"
    dist = abs(entry - sl)
    tp_min = max(dist * 0.8, a * 0.5)
    tp_max = dist * 12.0
    if long_:
        lv_ = [(pdh, "PDH"), (pwh, "PWH"), (pmh, "PMH"), (eqh, "EQH"), (ob_sl if ob_s_act else NaN, "OB"), (cdh, "CDH"),
               (vpoc, "POC"), (vah, "VAH"), (mvwap, "mVWAP"), (math.floor(close / cfg.rn_grid) * cfg.rn_grid + cfg.rn_grid, "RN")]
    else:
        lv_ = [(pdl, "PDL"), (pwl, "PWL"), (pml, "PML"), (eql, "EQL"), (ob_bh if ob_b_act else NaN, "OB"), (cdl, "CDL"),
               (vpoc, "POC"), (val, "VAL"), (mvwap, "mVWAP"), (math.ceil(close / cfg.rn_grid) * cfg.rn_grid - cfg.rn_grid, "RN")]
    cand = []
    for lv, nm in lv_:
        if not isn(lv):
            d = lv - close if long_ else close - lv
            if tp_min <= d <= tp_max:
                cand.append((d, lv, nm))
    cand.sort(key=lambda x: x[0])   # stable, as array.sort_indices
    tps, bases = [NaN, NaN, NaN], ["1R", "2R", "3R"]
    last_pick = NaN
    got = 0
    for d, lv, nm in cand:
        if got >= 3:
            break
        if isn(last_pick) or abs(lv - last_pick) > a * 0.3:
            tps[got] = lv
            bases[got] = nm
            last_pick = lv
            got += 1
    tp1, tp2, tp3 = tps
    fb1 = isn(tp1)
    tp1 = (entry + dist if long_ else entry - dist) if fb1 else tp1
    fb2 = isn(tp2) or (tp2 <= tp1 if long_ else tp2 >= tp1)
    tp2 = ((max(tp1, entry) + dist) if long_ else (min(tp1, entry) - dist)) if fb2 else tp2
    fb3 = isn(tp3) or (tp3 <= tp2 if long_ else tp3 >= tp2)
    tp3 = (tp2 + dist if long_ else tp2 - dist) if fb3 else tp3
    b1 = "1R" if fb1 else bases[0]
    b2 = ("2R" if fb1 else "+1R") if fb2 else bases[1]
    b3 = ("3R" if (fb2 and fb1) else "+1R") if fb3 else bases[2]
    rr1 = abs(tp1 - entry) / dist if dist > 0 else 0.0
    rr2 = abs(tp2 - entry) / dist if dist > 0 else 0.0
    rr3 = abs(tp3 - entry) / dist if dist > 0 else 0.0
    p1 = p2 = p3 = psl = NaN
    uH = 1.5 * a
    hp = AS.hit_prob
    if not isn(hp[0]) and uH > 0:
        hb, hba = (0, 4) if long_ else (4, 0)
        u1, u2, u3, us = abs(tp1 - entry) / uH, abs(tp2 - entry) / uH, abs(tp3 - entry) / uH, dist / uH
        p1 = f_grid_interp(u1, 100.0, hp[hb], hp[hb + 1], hp[hb + 2], True)
        p2 = f_grid_interp(u2, 100.0, hp[hb], hp[hb + 1], hp[hb + 2], True)
        p3 = f_grid_interp(u3, 100.0, hp[hb], hp[hb + 1], hp[hb + 2], True)
        psl = f_grid_interp(us, 100.0, hp[hba], hp[hba + 1], hp[hba + 2], True)
    ev = NaN
    rp = AS.race_prob
    pw = pl_ = pt = NaN
    if not isn(rp[0]) and dist > 0:
        rb0 = 0 if long_ else 6
        pw = f_grid_interp(rr1, 100.0, rp[rb0], rp[rb0 + 1], rp[rb0 + 2], True) / 100.0
        pl_ = f_grid_interp(rr1, 0.0, rp[rb0 + 3], rp[rb0 + 4], rp[rb0 + 5], False) / 100.0
        rt0 = 12 if long_ else 15
        pt = f_grid_interp(rr1, 0.0, rp[rt0], rp[rt0 + 1], rp[rt0 + 2], False)
        cr = ((sess_spread + 2.0 * cfg.slippage_pts) + cfg.commission_l / max(cfg.point_value, 1.0)) / dist
        ev = pw * rr1 - pl_ + pt - cr
    reason = f"SL:{basis} TP:{b1}/{b2}/{b3} [{regime_label}]"
    return dict(long=long_, entry=entry, sl=sl, dist=dist, tp1=tp1, tp2=tp2, tp3=tp3, rr1=rr1, rr2=rr2, rr3=rr3,
                sl_basis=basis, tp_basis=[b1, b2, b3], p_tp1=p1, p_tp2=p2, p_tp3=p3, p_sl=psl, ev=ev,
                race_p_win=pw, race_p_loss=pl_, race_timeout_r=pt, race_n=AS.race_n, hit_n=AS.hit_n, horizon_bars=N, reason=reason)


def what_if(i, F, bt, brt, hgb, hgs, mss, adx, cfg, ev_lb, ev_ls, pdh, pdl):
    """Scenario scores (heuristic 0-100, clamped [10, 90] as R5.1 specified), from the twins."""
    out = {"pdh_cont": None, "pdl_cont": None, "vwap_hold": None, "vwap_fail": None}
    at = adx > cfg.adx_threshold
    if not isn(pdh):
        f = 50.0 + (15.0 if bt else -10.0 if brt else 0.0) + (12.0 if hgb else -8.0 if hgs else 0.0) + (10.0 if mss > 0 else -10.0 if mss < 0 else 0.0) + (5.0 if at else 0.0)
        out["pdh_cont"] = clamp(f, 10.0, 90.0)
    if not isn(pdl):
        f = 50.0 + (15.0 if brt else -10.0 if bt else 0.0) + (12.0 if hgs else -8.0 if hgb else 0.0) + (10.0 if mss < 0 else -10.0 if mss > 0 else 0.0) + (5.0 if at else 0.0)
        out["pdl_cont"] = clamp(f, 10.0, 90.0)
    dv = F["dist_vwap_atr"][i]
    if abs(dv) < 1.0 and not isn(F["vwap"][i]):
        s, ac = F["vwap_slope"][i], F["vwap_accel"][i]
        hold = 50.0 + (12.0 if bt else -12.0 if brt else 0.0) + (10.0 if hgb else -10.0 if hgs else 0.0) + (8.0 if mss > 0 else -8.0 if mss < 0 else 0.0) \
            + (8.0 if ev_lb > ev_ls else -8.0) + (5.0 if at else 0.0) + (5.0 if s > 0 else -5.0 if s < 0 else 0.0) + (3.0 if ac > 0 else -3.0 if ac < 0 else 0.0)
        fail = 50.0 + (12.0 if brt else -12.0 if bt else 0.0) + (10.0 if hgs else -10.0 if hgb else 0.0) + (8.0 if mss < 0 else -8.0 if mss > 0 else 0.0) \
            + (8.0 if ev_ls > ev_lb else -8.0) + (5.0 if at else 0.0) + (5.0 if s < 0 else -5.0 if s > 0 else 0.0) + (3.0 if ac < 0 else -3.0 if ac > 0 else 0.0)
        out["vwap_hold"] = clamp(hold, 10.0, 90.0)
        out["vwap_fail"] = clamp(fail, 10.0, 90.0)
    return out


def census(H, lo, i):
    if lo is None:
        return {"n": 0}
    ds = H["datastatus"][lo:i + 1]
    sv = H["schema"][lo:i + 1]
    n = len(ds)
    return {"n": int(n), "gc_pct": float((ds % 2).sum() * 100.0 / max(n, 1)), "oi_pct": float(((ds // 2) % 2).sum() * 100.0 / max(n, 1)),
            "v2_pct": float((sv == 2).sum() * 100.0 / max(n, 1)), "schema_build": SCHEMA_BUILD}
