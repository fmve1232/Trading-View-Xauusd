"""B31 (research/registrations/B31.json): pools, sweep classification, the A / B sequence, the checks, the fill-bar rule,
overlap, the matched control, the score's statistics and a prefix-invariance (look-ahead) check, worked by hand.
Prices near $4,000, so the scale s = price / 4000 is close to 1; ATR 5, cost $0.80 / oz unless stated."""
import numpy as np
import pandas as pd
import pytest

from quantum import engine, sessions
from quantum.config import DEFAULT
from quantum.data import sources
from quantum.data.market import load_synthetic
from quantum.features import compute as compute_features
from quantum.research import b10, b31

T0 = 1678093200                        # 2023-03-06 09:00 UTC (Mon, London)
NAMES = b31.SELL_SIDE + b31.BUY_SIDE + ("CDH", "CDL")


def _ctx(n, edits, pools=None, up_shift=(), dn_any=(), htf_up=False, cost=0.8):
    o = np.full(n, 3995.0)
    h, l, c = o + 0.5, o - 0.5, o.copy()
    for j, (oo, hh, ll, cc) in edits.items():
        o[j], h[j], l[j], c[j] = oo, hh, ll, cc
    P = {k: np.full(n, np.nan) for k in NAMES}
    for k, v in (pools or {}).items():
        P[k][:] = v
    ups = np.zeros(n, bool)
    ups[list(up_shift)] = True
    dna = np.zeros(n, bool)
    dna[list(dn_any)] = True
    f = np.zeros(n, bool)
    return b31.Ctx(t=T0 + 900 * np.arange(n), o=o, h=h, l=l, c=c, atr=np.full(n, 5.0), aatr=np.full(n, 5.0),
                   cost=np.full(n, cost), date=np.array([np.datetime64("2023-03-06")] * n), sess=np.array(["LONDON"] * n, object),
                   pools=P, asia_date=np.array([None] * n, object), up_any=ups.copy(), dn_any=dna, up_shift=ups, dn_shift=f.copy(),
                   ob_bull_hi=np.full(n, np.nan), ob_bear_lo=np.full(n, np.nan), ranging=f.copy(), vwap=np.full(n, np.nan),
                   lo2=np.full(n, np.nan), up2=np.full(n, np.nan), htf_up=np.full(n, htf_up), htf_dn=f.copy(), e15_up=f.copy(),
                   e1_up=np.full(n, htf_up), e4_up=np.full(n, htf_up), atr_ok=np.ones(n, bool))


# a sell-side pool (PDL 3990) swept to 3988.50 and closed back above on the same bar (bar 10); a bullish MSS on bar 11;
# a bullish FVG on bar 12 (low 3995 > bar 10's high 3993 by 2.0 > 0.3 x ATR 1.5): limit 3995, stop 3988.50 - 1.0 = 3987.50
BASE = {10: (3992, 3993, 3988.5, 3991), 11: (3991, 3996, 3990.5, 3995.5), 12: (3996, 4000, 3995, 3999.5),
        13: (3999, 3999.5, 3994.5, 3997)}
WIN = {14: (3997, 4005.5, 3996, 4005)}


def _a(edits, **kw):
    X = _ctx(40, edits, pools={"PDL": 3990.0}, up_shift=(11,), **kw)
    evs = b31.crossings(X, b31.SELL_SIDE + b31.BUY_SIDE)
    return X, evs


def test_pools_cover_every_bar_of_the_previous_day_and_week_and_sessions_only_once_ended():
    idx = pd.date_range("2023-03-05 22:00", periods=6 * 96, freq="15min", tz="UTC")       # Sun 17:00 NY onwards
    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}, index=idx)
    cal = sessions.calendar(idx)
    first_of_tue = int(np.flatnonzero(cal["trading_date"].to_numpy() == np.datetime64("2023-03-07"))[0])
    df.iloc[first_of_tue, df.columns.get_loc("high")] = 9.0                                 # Tuesday's opening bar
    pools, _ = b31.build_pools(df, cal, np.full(len(df), np.nan), np.full(len(df), np.nan))
    wed = np.flatnonzero(cal["trading_date"].to_numpy() == np.datetime64("2023-03-08"))
    assert (pools["PDH"][wed] == 9.0).all()                                                  # the day-opening bar counts
    asia = cal["in_asian"].to_numpy(bool)
    end = int(np.flatnonzero(asia)[np.flatnonzero(np.diff(np.flatnonzero(asia)) > 1)[0]])    # the first Asian run's last bar
    assert np.isnan(pools["ASH"][end]) and np.isfinite(pools["ASH"][end + 1])                # a pool only after it ends


def test_a_sweep_is_rejected_or_accepted_never_both():
    X, evs = _a(BASE)
    ev = [e for e in evs if e["kind"] == "PDL"][0]
    assert ev["status"] == "REJECTED" and ev["j"] == 10 and ev["k"] == 10 and ev["dir"] == 1
    assert ev["ext"] == 3988.5 and ev["pen"] == pytest.approx(1.5) and ev["bars"] == 1
    X2, evs2 = _a({10: (3992, 3993, 3988, 3989), 11: (3989, 3990, 3987, 3988), 12: (3988, 3989, 3986, 3987)})
    br = [e for e in evs2 if e["kind"] == "PDL"][0]
    assert br["status"] == "ACCEPTED" and br["dir"] == -1 and br["k"] == 12 and br["ext"] == 3993   # the leg's highest high (SELL stop side)


def test_module_a_sequence_stop_checks_and_a_tp1_win():
    X, evs = _a({**BASE, **WIN})
    sets = b31.setups(X, "A", evs)
    assert len(sets) == 1 and sets[0]["limit"] == 3995 and sets[0]["stop"] == pytest.approx(3987.5) and sets[0]["entry_type"] == "FVG"
    assert sets[0]["order_bar"] == 12
    R = b31.run_module(X, sets, 0)
    tr = R["trades"][0]
    sc = 3995 / 4000
    assert tr["entry"] == 3995 and tr["D"] == pytest.approx(7.5 / sc) and tr["out"] == "TP"
    assert tr["net"] == pytest.approx(10 - 0.8) and tr["r"] == pytest.approx(9.2 / (7.5 / sc + 0.8))
    assert b31.setups(X, "B", evs) == []                                     # HTF not aligned: A, not B
    Xb, evb = _a({**BASE, **WIN}, htf_up=True)
    assert b31.setups(Xb, "A", evb) == [] and len(b31.setups(Xb, "B", evb)) == 1


@pytest.mark.parametrize("edits, pools, why", [
    ({**BASE, **WIN}, {"PDL": 3990.0, "PDH": 4000.0}, "room"),                # buy-side liquidity $5 above the entry
    ({**BASE, 10: (3992, 3993, 3986, 3991), **WIN}, {"PDL": 3990.0}, "reward"),   # stop 3985: D 10, (10-.8)/(10+.8) < 1
])
def test_checks_reject(edits, pools, why):
    X = _ctx(40, edits, pools=pools, up_shift=(11,))
    R = b31.run_module(X, b31.setups(X, "A", b31.crossings(X, b31.SELL_SIDE + b31.BUY_SIDE)), 0)
    assert R["stat"]["rejected"] == {why: 1} and not R["trades"]


def test_a_stop_tighter_than_five_dollars_is_rejected():
    edits = {10: (3991, 3990.4, 3989.0, 3990.2), 11: (3990.2, 3993, 3990, 3992.5), 12: (3992.5, 3995, 3992, 3994.5)}
    X = _ctx(40, edits, pools={"PDL": 3990.0}, up_shift=(11,))
    R = b31.run_module(X, b31.setups(X, "A", b31.crossings(X, b31.SELL_SIDE + b31.BUY_SIDE)), 0)
    assert R["stat"]["rejected"] == {"stop": 1}                               # limit 3992, stop 3988: D 4


def test_the_fill_bar_can_only_stop_and_a_two_level_bar_is_ambiguous():
    X, evs = _a({**BASE, 13: (3999, 4006, 3987, 4000)})                       # the fill bar touches TP1 and the stop
    tr = b31.run_module(X, b31.setups(X, "A", evs), 0)["trades"][0]
    assert tr["out"] == "SL" and tr["r"] == pytest.approx(-1.0, abs=0.02)
    X, evs = _a({**BASE, 14: (3997, 4006, 3987, 4000)})
    tr = b31.run_module(X, b31.setups(X, "A", evs), 0)["trades"][0]
    assert tr["out"] == "AMBIGUOUS" and tr["net"] < 0


def test_price_beyond_the_sweep_extreme_before_the_fill_invalidates():
    """A falling price fills the limit (3995) before it reaches the extreme (3988.50), so before a fill only a bar that
    OPENS beyond the extreme can invalidate the setup."""
    X, evs = _a({**BASE, 13: (3999, 3999.5, 3996, 3997), 14: (3988.0, 3989, 3987.9, 3988.5)})
    R = b31.run_module(X, b31.setups(X, "A", evs), 0)
    assert R["stat"]["invalidated"] == 1 and not R["trades"]
    X, evs = _a({**BASE, 13: (3999, 3999.5, 3996, 3997), 14: (3997, 3997.5, 3988.0, 3989)})   # trades down through 3995
    assert b31.run_module(X, b31.setups(X, "A", evs), 0)["stat"]["executed"] == 1


def test_one_position_at_a_time_and_repeats():
    X = _ctx(60, {**BASE, **WIN})
    s1 = {"order_bar": 12, "limit": 3995.0, "stop": 3987.5, "inval": None, "entry_type": "FVG", "dir": 1, "ev": {"kind": "PDL", "bars": 1}}
    s2 = dict(s1, order_bar=13, limit=3999.0, stop=3991.5)                    # $4 away, 15 min later: a REPEAT
    s3 = dict(s1, order_bar=13, limit=3975.0, stop=3967.5)                    # $20 away: a new idea, never filled here
    R = b31.run_module(X, [s1, s2, s3], 0)
    assert R["stat"]["repeat"] == 1 and R["stat"]["missed"] == 1 and R["stat"]["executed"] == 1
    X2 = _ctx(60, {**BASE, 14: (3997, 3998, 3996, 3997), 15: (3997, 3998, 3994.6, 3997)})
    s4 = dict(s1, order_bar=14, limit=3994.8, stop=3987.3, ev={"kind": "ASL", "bars": 1})
    s4["dir"] = 1
    R2 = b31.run_module(X2, [s1, dict(s4, limit=3994.8 - 16, stop=3987.3 - 16)], 0)
    assert R2["stat"]["repeat"] == 0


def test_matched_random_uses_the_same_session_direction_and_stop():
    X = _ctx(400, {})
    tr = [{"sess": "LONDON", "dir": 1, "D": 7.0}]
    a = b31.matched_random(X, tr, 0)
    b = b31.matched_random(X, tr, 0)
    assert a == b and a["n"] == b31.RND_K and a["tp1_rate"] == 0.0           # flat prices: never +$10, a timeout each


def test_isotonic_and_auc():
    x = np.array([1, 2, 3, 4, 5, 6], float)
    y = np.array([0, 1, 0, 1, 1, 1], float)
    kn, va = b31.isotonic_fit(x, y)
    assert (np.diff(va) >= 0).all() and va[-1] == 1.0
    assert b31.auc(np.array([1, 2, 3, 4.0]), np.array([0, 0, 1, 1])) == 1.0
    assert b31.auc(np.array([1, 2, 3, 4.0]), np.array([1, 1, 0, 0])) == 0.0


def _real_ctx(base):
    h1 = sources.resample_ohlc(base, "60min")
    m = b10.make_market(base, h1, "15m", 900)
    F = compute_features(m, DEFAULT)
    return b31.make_ctx(base, h1, engine.run(m, DEFAULT, "treatment", F), F)


def test_no_setup_changes_when_later_bars_arrive():
    """Strict prefix invariance: every setup ordered before a cut is identical with or without the bars after it (the
    engine's own rows are prefix-invariant: tests/test_no_lookahead.py)."""
    base = load_synthetic("15m", bars=1600, seed=5).base
    full = _real_ctx(base)
    key = lambda s: (s["order_bar"], s["dir"], round(s.get("limit") or s.get("market"), 4), round(s["stop"], 4), s["entry_type"])
    every = {mod: [key(s) for s in b31.setups(full, mod, b31.crossings(full, b31.SELL_SIDE + b31.BUY_SIDE))] for mod in b31.MODULES}
    seen = 0
    for cut in (1150, 1300, 1451):
        part = _real_ctx(base.iloc[:cut])
        for mod in b31.MODULES:
            a = [k for k in every[mod] if k[0] < cut]
            b = [key(s) for s in b31.setups(part, mod, b31.crossings(part, b31.SELL_SIDE + b31.BUY_SIDE)) if s["order_bar"] < cut]
            assert a == b, (mod, cut)
            seen += len(a)
    assert seen > 0, "no setup at all: the comparison would be empty"


def test_without_an_fvg_the_order_block_order_waits_two_bars_and_a_small_gap_is_not_an_fvg():
    """Bar 12's low 3994 is only $1.00 above bar 10's high (3993): below 0.3 x ATR = $1.50, so not an FVG. With the
    engine's order block active at the shift (high 3994.80) the limit sits there, placed when 'no FVG by 2 bars after the
    shift' is known (bar 13), never at the shift bar."""
    edits = {**BASE, 12: (3996, 4000, 3994, 3999.5)}
    X = _ctx(40, edits, pools={"PDL": 3990.0}, up_shift=(11,))
    evs = b31.crossings(X, b31.SELL_SIDE + b31.BUY_SIDE)
    assert b31.fvg_at(X, 12, 1) is None and b31.setups(X, "A", evs) == []                 # no FVG and no order block
    X.ob_bull_hi[11] = 3994.8
    s = b31.setups(X, "A", evs)
    assert len(s) == 1 and s[0]["entry_type"] == "OB" and s[0]["limit"] == 3994.8 and s[0]["order_bar"] == 13
