"""Amendment 9: macro correlations over the same period (F-A64) and each macro factor counted once (F-A65)."""
import dataclasses

import numpy as np

from quantum import features
from quantum.config import DEFAULT
from quantum.data.market import load_synthetic


def _F(m, cfg=DEFAULT):
    return features.compute(m, cfg)


def test_an_asset_that_is_gold_correlates_near_one():
    """Silver = gold's own chart bars, DXY = 1 / gold's own 1H bars: the same-period pairing must see r ~ +1 / -1.
    Before the fix (gold this bar vs the asset one bar earlier) both read near 0."""
    m = load_synthetic("15m", bars=3000, seed=11)
    g1h = m.htf["60"]
    m2 = dataclasses.replace(m, ext_chart={**m.ext_chart, "silver": m.base.copy()},
                             ext_macro={**m.ext_macro, "dxy": g1h.assign(**{c: 1.0 / g1h[c] for c in ("open", "high", "low", "close")})})
    F = _F(m2)
    tail = slice(-500, None)
    assert np.nanmedian(F["avg_corr"]["Slv"][tail]) > 0.9
    assert np.nanmedian(F["avg_corr"]["DXY"][tail]) < -0.9


def test_macro_tf_windows_are_counted_in_1h_bars():
    m = load_synthetic("5m", bars=3000, seed=3)        # k = 12: the 120-bar window is 1,440 chart bars
    F = _F(m)
    assert np.isnan(F["corr"]["DXY"][2][:1400]).all() and not np.isnan(F["corr"]["DXY"][2][-50:]).all()


def test_each_macro_factor_counts_once():
    m = load_synthetic("15m", bars=2000, seed=5)
    F = _F(m)
    assert DEFAULT.tips_source == "us10y" and not F["tips_valid"].any()        # TIPS = the 10Y: off
    gcv = F["gc_valid"].astype(int)
    need = np.ceil((4 + gcv) / 2.0)
    assert np.array_equal(F["macro_bull"], F["macro_bull_votes"] >= need)
    dv = F["dxy_valid"]
    usd_b = np.where(dv, F["dxy_bear"], F["eur_bull"]).astype(int)
    exp = F["gc_confirms_bull"].astype(int) + usd_b + F["yld_falling"] + F["spx_bull"] + F["slv_bull"] + F["tips_falling"]
    assert np.array_equal(F["macro_bull_votes"], exp)                          # EUR does not vote beside DXY
    no_dxy = dataclasses.replace(m, ext_macro={k: v for k, v in m.ext_macro.items() if k != "dxy"})
    F2 = _F(no_dxy)
    assert not F2["dxy_valid"].any() and (F2["macro_bull_votes"] >= F2["eur_bull"].astype(int)).all()  # EUR stands in
