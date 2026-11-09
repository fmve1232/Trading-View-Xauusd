"""Phase D features (research/registrations/PHASE_D.json, Workstreams A, D and F). Research only.

ORDER FLOW: the ten registered families from Dukascopy top-of-book sums (quantum/research/d_dukascopy.py). Row i uses
ticks of bar i and earlier only, so it is known at bar i's close, the decision time. Prefix nd_of_ = direction-free,
sg_of_ = signed (multiplied by the trade direction in the design, as B27's sg_ features). Missing bars stay missing.

  family                         columns
  1 spread dynamics              nd_of_spread, nd_of_spread_z, nd_of_spread_sd
  2 quote intensity              nd_of_ntr_z, nd_of_sec_active
  3 mid direction changes        nd_of_flip_rate
  4 bid- vs ask-side pressure    sg_of_side_moves, sg_of_side_vol
  5 short-term imbalance         sg_of_ofi15, sg_of_ofi60, sg_of_qimb15, sg_of_qlast, sg_of_ofi_l5
  6 price move per quote         sg_of_move_per_quote, nd_of_efficiency
  7 quote acceleration           nd_of_accel_in_bar, nd_of_accel_60
  8 spread expansion/contraction nd_of_spread_chg, nd_of_spread_range, sg_of_spread_net (signed: widening as mid rises)
  9 directional persistence      sg_of_timb15, sg_of_timb60, sg_of_run_signed
  10 volatility-conditioned      nd_of_rv, nd_of_rv_ratio, sg_of_ofi15_vadj
  plus nd_of_missing (1 when the bar has no Dukascopy tick).

BASELINE / A / C sets are B27's audited price features (quantum/research/b27.py, research/FEATURE_AUDIT.md) selected by
family, plus intermarket returns where the data genuinely exist. Nothing here is fitted.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import b5_orderflow as B

Z_BARS, Z_MIN = 2000, 200
FAMILIES_OF = {1: ("nd_of_spread", "nd_of_spread_z", "nd_of_spread_sd"), 2: ("nd_of_ntr_z", "nd_of_sec_active"),
               3: ("nd_of_flip_rate",), 4: ("sg_of_side_moves", "sg_of_side_vol"),
               5: ("sg_of_ofi15", "sg_of_ofi60", "sg_of_qimb15", "sg_of_qlast", "sg_of_ofi_l5"),
               6: ("sg_of_move_per_quote", "nd_of_efficiency"), 7: ("nd_of_accel_in_bar", "nd_of_accel_60"),
               8: ("nd_of_spread_chg", "nd_of_spread_range", "sg_of_spread_net"), 9: ("sg_of_timb15", "sg_of_timb60", "sg_of_run_signed"),
               10: ("nd_of_rv", "nd_of_rv_ratio", "sg_of_ofi15_vadj")}
OF_COLUMNS = tuple(c for v in FAMILIES_OF.values() for c in v) + ("nd_of_missing",)

# B27 families (b27.FAMILY_OF) per registered model set; MARKOV (needs hmmlearn) and ENGINE are in no set.
BASELINE_FAMILIES = ("TIME_NEWS", "MOMENTUM")
A_FAMILIES = (*BASELINE_FAMILIES, "VOLATILITY", "TREND", "STRUCTURE_SMC", "LIQUIDITY")


def _r(a, b):
    return B._ratio(a, b)


def _z(x: pd.Series) -> pd.Series:
    mu = x.shift(1).rolling(Z_BARS, min_periods=Z_MIN).mean()
    sd = x.shift(1).rolling(Z_BARS, min_periods=Z_MIN).std()
    return _r(x - mu, sd)


def order_flow(raw: pd.DataFrame, dext: pd.DataFrame, scale: float, index: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """The registered order-flow columns. raw = B5c's sums, dext = Phase D's sums, both per 15-minute bar (Dukascopy
    units); scale = units per dollar (b5c_dukascopy.price_scale). index (the spot grid) reindexes the result."""
    f = raw.join(dext, how="outer").sort_index().astype(float)
    n = f["n"]
    has = n.fillna(0) > 0
    out = pd.DataFrame(index=f.index)
    sp = f["spread_sum"] / n / scale
    out["nd_of_spread"] = sp
    out["nd_of_spread_z"] = _z(sp)
    out["nd_of_spread_sd"] = np.sqrt(np.clip(f["spread_sq"] / n / scale ** 2 - sp ** 2, 0, None))
    out["nd_of_ntr_z"] = _z(np.log(n.clip(lower=1.0)))
    out["nd_of_sec_active"] = f["sec_active"] / 900.0
    out["nd_of_flip_rate"] = _r(f["flips"], (f["up"] + f["down"] - 1).clip(lower=1.0))
    moves_up, moves_dn = f["bid_up"] + f["ask_up"], f["bid_dn"] + f["ask_dn"]
    out["sg_of_side_moves"] = _r(moves_up - moves_dn, moves_up + moves_dn)
    out["sg_of_side_vol"] = _r(f["bv_sum"] - f["av_sum"], f["bv_sum"] + f["av_sum"])
    depth = f["depth"] / n
    out["sg_of_ofi15"] = _r(f["ofi"], depth)
    n4, d4, o4, u4, w4 = (f[k].rolling(4, min_periods=4).sum() for k in ("n", "depth", "ofi", "up", "down"))
    out["sg_of_ofi60"] = _r(o4, d4 / n4)
    out["sg_of_qimb15"] = _r(f["qsum"], f["qn"])
    out["sg_of_qlast"] = f["qlast"]
    out["sg_of_ofi_l5"] = _r(f["ofi_l5"], depth)
    net = (f["mid_last"] - f["mid_first"]) / scale
    out["sg_of_move_per_quote"] = _r(net, n)
    out["nd_of_efficiency"] = _r(net.abs(), f["path_abs"] / scale)
    h1 = f["n_h1"]
    out["nd_of_accel_in_bar"] = np.log(((n - h1).clip(lower=0) + 1.0) / (h1 + 1.0))
    prev3 = n.shift(1).rolling(3, min_periods=3).mean()
    out["nd_of_accel_60"] = np.log((n + 1.0) / (prev3 + 1.0))
    out["nd_of_spread_chg"] = (f["spread_last"] - f["spread_first"]) / scale
    out["nd_of_spread_range"] = (f["spread_max"] - f["spread_min"]) / scale
    out["sg_of_spread_net"] = _r(f["sw_up"] - f["sw_dn"], f["sw_up"] + f["sw_dn"]) * np.sign(net)
    out["sg_of_timb15"] = _r(f["up"] - f["down"], f["up"] + f["down"])
    out["sg_of_timb60"] = _r(u4 - w4, u4 + w4)
    out["sg_of_run_signed"] = _r(f["run_max"], (f["up"] + f["down"]).clip(lower=1.0)) * np.sign(net)
    rv = np.sqrt(f["rv"]) / scale
    out["nd_of_rv"] = rv
    med = rv.shift(1).rolling(Z_BARS, min_periods=Z_MIN).median()
    out["nd_of_rv_ratio"] = _r(rv, med)
    out["sg_of_ofi15_vadj"] = _r(out["sg_of_ofi15"], np.sqrt(out["nd_of_rv_ratio"].clip(lower=1e-6)))
    out.loc[~has, [c for c in OF_COLUMNS if c != "nd_of_missing"]] = np.nan
    out["nd_of_missing"] = (~has).astype(float)
    out = out[list(OF_COLUMNS)]
    if index is not None:
        out = out.reindex(index)
        out["nd_of_missing"] = out["nd_of_missing"].fillna(1.0)
    return out


def intermarket(mid: dict[str, pd.DataFrame], index: pd.DatetimeIndex) -> pd.DataFrame:
    """Signed 1-bar and 4-bar log returns of each available instrument's 15-minute mid, read at the same bar close
    (its ticks are inside the bar). Instruments not supplied are absent, never filled with another series."""
    out = pd.DataFrame(index=index)
    for name, df in mid.items():
        last = df["mid_last"].where(df["n"] > 0).reindex(index)
        lr = np.log(last)
        out[f"sg_im_{name.lower()}_r1"] = lr.diff(1)
        out[f"sg_im_{name.lower()}_r4"] = lr.diff(4)
    return out


def select(F: pd.DataFrame, families: tuple[str, ...], family_of) -> list[str]:
    """B27 feature columns whose family (b27.family) is in `families`."""
    return [c for c in F.columns if c.startswith(("nd_", "sg_")) and family_of(c) in families]
