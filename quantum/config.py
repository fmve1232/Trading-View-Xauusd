"""Engine parameters. Every default is the Pine Master's input default at build v21.

DO NOT TUNE these against results measured on the price history this system was developed
on (audit/AUDIT_PROMPT.md §9). The configuration is hashed; the frozen forward holdout in
`holdout.py` restarts whenever the hash changes, so a tweak can never quietly borrow the
credibility of evidence collected under different parameters.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass

ENGINE_VERSION = "Q7.2-web.3"   # Pine QVERSION this engine ports, plus the web build
SCHEMA_BUILD = 6                 # same schema build as Pine v32 (F-A38 Cornish-Fisher guard)


@dataclass(frozen=True)
class Config:
    # ---- MODULES (Pine grpModules) ----
    show_fvg: bool = True            # engine input since v21 (F-A30)
    show_ob: bool = True
    show_smt: bool = True
    show_climax: bool = True
    show_adaptive_atr: bool = False
    show_displacement: bool = True
    show_stats_engine: bool = True
    forecast_bars: int = 10

    # ---- RISK MANAGEMENT ----
    risk_percent: float = 1.0
    account_size: float = 10000.0
    point_value: float = 100.0
    use_dd_breaker: bool = False
    max_dd_pct: float = 12.0
    use_cal_gate: bool = True
    cal_gate_min_p: float = 0.50
    spread_cost: float = 0.3
    slippage_pts: float = 0.2
    commission_l: float = 7.0
    holdout_ratio: float = 0.20
    use_news_suppress: bool = False

    # ---- CORE ----
    ema20_len: int = 20
    ema100_len: int = 100
    ema200_len: int = 200
    atr_len: int = 14
    adx_len: int = 14
    adx_threshold: int = 25
    rsi_len: int = 14
    internal_pivot_len: int = 2
    swing_pivot_len: int = 5
    struct_window: int = 8
    trend_threshold: int = 60
    vol_climax_perc: int = 95
    eq_atr_mult: float = 0.25
    vol_lookback: int = 50
    fvg_max_bars: int = 30
    ob_max_bars: int = 20
    liq_prox_mult: float = 1.5
    rn_grid: float = 50.0
    min_match_q: int = 0
    tq_min_score: int = 55

    # ---- RISK LIMITS ----
    use_risk_limits: bool = True
    max_daily_loss_r: float = 3.0
    max_trades_day: int = 4
    max_consec_loss: int = 3
    lockout_bars: int = 0

    # ---- V11 / V17 ----
    disp_mult: float = 2.5
    dxy_roc_len: int = 10
    use_rsi_div_filter: bool = False
    zn_roc_len: int = 10
    invert_yield: bool = False
    gc_min_tf_sec: int = 900
    gc_vol_mult: float = 1.2
    cot_enable: bool = False          # Pine default OFF; COT is always DISPLAYED, gated only if on
    cot_len: int = 52
    cot_extreme: int = 85

    # ---- V19 correlation ----
    corr_short_len: int = 30
    corr_med_len: int = 60
    corr_long_len: int = 120

    # ---- HISTORICAL ANALOG ----
    hist_w_adx: int = 30
    hist_w_atr: int = 25
    hist_w_htf: int = 25
    hist_w_str: int = 5
    hist_w_liq: int = 5
    hist_w_mr: int = 5
    hist_w_cor: int = 5
    hist_w_sess: int = 5
    hist_w_reg: int = 5

    # ---- Strategy twin (backtest) ----
    backtest_all_bars: bool = True    # F-A29: the arms trade every bar, not the last 120
    recent_bars_len: int = 120
    commission_per_oz: float = 0.385  # Pine strategy(): cash_per_contract 0.385, qty 1 oz

    # ---- Data-source switches (opt-in; each changes signals, so each needs a new freeze) ----
    tips_source: str = "us10y"        # Pine default TVC:US10Y. "fred_dfii10" = real 10y yield.

    def hash(self) -> str:
        blob = json.dumps(dataclasses.asdict(self), sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:16]

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


DEFAULT = Config()

# Timeframes the pipeline builds. seconds, Yahoo interval, history window Yahoo serves.
TIMEFRAMES = {
    "5m": {"sec": 300, "yahoo": "5m", "range": "60d"},
    "15m": {"sec": 900, "yahoo": "15m", "range": "60d"},
    "1h": {"sec": 3600, "yahoo": "60m", "range": "730d"},
    "4h": {"sec": 14400, "yahoo": "60m", "range": "730d", "resample_from": "1h"},
}
