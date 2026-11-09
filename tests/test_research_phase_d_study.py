"""Phase D study pipeline (quantum/research/d_study.py) on SYNTHETIC data only: never a result. A planted order-flow
edge must be found by the incremental-value test and the null must not be; probabilities sum to one; nothing reads a
test row while fitting; the acceptance logic needs all six criteria; the trial log is append-only and tamper-evident;
the broker specification is refused when incomplete. No real Dukascopy, MT5 or broker data exist yet."""
import json

import numpy as np
import pandas as pd
import pytest

from quantum.research import b27
from quantum.research import d_broker as BR
from quantum.research import d_log as LOG
from quantum.research import d_study as S
from quantum.research import harness as H


def _synthetic(beta: float, seed: int = 5, start="2021-01-04", end="2021-06-26"):
    """15-minute mid bars on the trading week; an AR(1) 'order-flow' signal s that drives the NEXT bars' drift by beta."""
    g = H.seeded_rng(seed)
    idx = pd.date_range(start, end, freq="15min", tz="UTC", inclusive="left")
    idx = idx[(idx.day_of_week < 5) | ((idx.day_of_week == 6) & (idx.hour >= 23))]
    idx = idx[~((idx.day_of_week == 4) & (idx.hour >= 21))]
    n = len(idx)
    s = np.zeros(n)
    for i in range(1, n):
        s[i] = 0.9 * s[i - 1] + g.normal(0, 0.45)
    inc = g.normal(0, 3.0, n) + beta * np.r_[0.0, s[:-1]]
    c = 1800 + np.cumsum(inc)
    o = np.r_[c[0], c[:-1]]
    wig = g.uniform(0.2, 2.5, (2, n))
    m15 = pd.DataFrame({"open": o, "high": np.maximum(o, c) + wig[0], "low": np.minimum(o, c) - wig[1], "close": c, "volume": 0.0}, index=idx)
    h1 = m15.resample("1h", label="left", closed="left").agg({"open": "first", "high": "max", "low": "min", "close": "last",
                                                              "volume": "sum"}).dropna()
    F = pd.DataFrame(index=idx)
    F["nd_hour"] = idx.hour / 24.0
    F["nd_weekday"] = idx.day_of_week / 6.0
    F["sg_ret1"] = pd.Series(c, index=idx).diff().to_numpy()
    F["sg_ret4"] = pd.Series(c, index=idx).diff(4).to_numpy()
    F["nd_atr"] = (m15["high"] - m15["low"]).rolling(14).mean().to_numpy()
    F["sg_of_ofi15"] = s
    F["nd_of_spread"] = g.uniform(0.2, 0.4, n)
    F["nd_of_missing"] = 0.0
    L = b27.labels("SYN", m15, h1, pd.Timestamp(start, tz="UTC") + pd.Timedelta(days=2), scale=False)
    return m15, F, L


@pytest.fixture(scope="module")
def planted():
    m15, F, L = _synthetic(beta=1.0)
    res = S.run(F, L, ["sg_of_ofi15", "nd_of_spread", "nd_of_missing"], [], sets=("BASELINE", "B", "C"), algos=("LR", "LGBM"),
                wf_start="2021-03-01", min_train=3000, months=1, log=lambda *a: None)
    return m15, F, L, res


@pytest.fixture(scope="module")
def null():
    _, F, L = _synthetic(beta=0.0, seed=6)
    res = S.run(F, L, ["sg_of_ofi15", "nd_of_spread", "nd_of_missing"], [], sets=("BASELINE", "B"), algos=("LR",),
                wf_start="2021-03-01", min_train=3000, months=1, log=lambda *a: None)
    return res


def test_planted_order_flow_edge_is_found(planted):
    _, _, _, res = planted
    inc = res["incremental"]["B/LR"]
    assert inc["delta_logloss"] > 0 and inc["p"] < 0.01 and inc["ci95"][0] > 0
    assert inc["p_holm_over_algorithms"] >= inc["p"] and res["incremental"]["B/LGBM"]["p_holm_over_algorithms"] < 0.05
    assert res["not_run"] == {"C": "no intermarket data"}                   # never substituted
    ev = next(s for s in res["strategies"] if s["id"] == "B/LR/EV0")["dev"]
    assert ev["exp_oz"] > 0 and ev["ci95"][0] > ev["matched_random"]
    assert res["family"]["strategies"] == 2 * 2 * 4 and res["family"]["reality_check"]["p_value"] < 0.05
    assert res["verdict"] == "NO QUALIFIED STRATEGY"                         # no out-of-sample period and one year: C1 / C4 fail


def test_the_null_finds_nothing(null):
    inc = null["incremental"]["B/LR"]
    assert inc["p"] is None or inc["p"] > 0.05
    assert null["qualified"] == [] and not any(s["criteria"]["QUALIFIES"] for s in null["strategies"])


def test_probabilities_are_multinomial_and_calibrated_only_on_training_rows(planted):
    _, F, L, res = planted
    m = res["sets"]["B"]["LR"]["metrics"]
    assert m["max_abs_sum_minus_1"] < 1e-9 and set(m["mean_p"]) == {"TP", "SL", "NEITHER"}
    cols = res["sets"]["B"]["columns"]
    wf = S.walk_forward(F, L, cols, "LR", "2021-03-01", 3000, 1, log=lambda *a: None)
    t_fill = L["fill_utc"].to_numpy()
    first = pd.Timestamp(wf["folds"][0]["start"], tz="UTC").timestamp()
    assert np.isnan(wf["P"][t_fill < first]).all() and not np.isnan(wf["P"][t_fill >= first + 86400 * 7]).all()
    # changing every outcome AFTER a fold's start cannot change that fold's model: refit with the future scrambled
    L2 = L.copy()
    late = L2["fill_utc"] >= pd.Timestamp("2021-04-01", tz="UTC").timestamp()
    L2.loc[late, "outcome"] = L2.loc[late, "outcome"].sample(frac=1.0, random_state=1).to_numpy()
    wf2 = S.walk_forward(F, L2, cols, "LR", "2021-03-01", 3000, 1, log=lambda *a: None)
    march = (t_fill >= pd.Timestamp("2021-03-01", tz="UTC").timestamp()) & (t_fill < pd.Timestamp("2021-04-01", tz="UTC").timestamp())
    np.testing.assert_allclose(wf["P"][march], wf2["P"][march])


def test_every_algorithm_gives_three_probabilities():
    g = H.seeded_rng(1)
    X = g.normal(size=(1500, 4))
    y = g.integers(0, 3, 1500)
    for a in S.ALGOS:
        m = S.fit(a, X, y)
        p = S.proba(a, m, X[:50])
        assert p.shape == (50, 3) and np.allclose(p.sum(axis=1), 1.0)
    T = S.temperature(p, y[:50])
    assert 0.05 <= T <= 20 and np.allclose(S.apply_temperature(p, T).sum(axis=1), 1.0)


def test_acceptance_needs_all_six_criteria():
    good = {"exp_oz": 1.0, "ci95": [0.6, 0.7], "matched_random": 0.5, "n_trades": 600, "p_dd_ge_15R_in_250": 0.01,
            "by_year": {"2021": {"n": 200, "exp_oz": 1.0}, "2022": {"n": 200, "exp_oz": 0.5}},
            "by_vol_tercile": {"LOW": {"n": 100, "exp_oz": 1}, "MID": {"n": 100, "exp_oz": 1}, "HIGH": {"n": 100, "exp_oz": -1}},
            "by_trend": {"UP": {"n": 100, "exp_oz": 1}, "DOWN": {"n": 100, "exp_oz": 1}, "MIXED": {"n": 100, "exp_oz": 1}}}
    y26 = {"exp_oz": 0.8, "ci95": [0.55, 0.7], "matched_random": 0.5}
    assert S.criteria(good, y26, True, 0.01, 0.01)["QUALIFIES"]
    for broken in ({"bh": False}, {"rc": 0.2}, {"holm": 0.2}, {"y26": None}, {"dev": {"n_trades": 299}},
                   {"dev": {"p_dd_ge_15R_in_250": 0.2}}, {"dev": {"by_year": {"2021": {"n": 200, "exp_oz": -0.1}}}},
                   {"y26": {"exp_oz": -0.1, "ci95": [0.55, 0.7], "matched_random": 0.5}},
                   {"y26": {"exp_oz": 0.8, "ci95": [0.45, 0.7], "matched_random": 0.5}}):
        dev = {**good, **broken.get("dev", {})}
        c = S.criteria(dev, broken.get("y26", y26) if "y26" in broken else y26, broken.get("bh", True), broken.get("rc", 0.01),
                       broken.get("holm", 0.01))
        assert not c["QUALIFIES"], broken


def test_descriptive_questions_run_and_label_resolution(planted):
    m15, F, L, _ = planted
    fav = S.favourable(L, m15, 10.0)
    assert set(np.unique(fav)) <= {-1, 0, 1} and 0.2 < np.mean(fav[fav >= 0] == 0) < 0.95
    _, info = S.adverse_first(L.iloc[:400], m15, 5.0)
    assert info["resolution"].startswith("15 minutes") and "inconclusive_at_15m" in info
    d = S.delay_effect(L, F)
    assert any(k.endswith("flow_with") for k in d)


def test_phase_d_log_is_append_only_and_tamper_evident(tmp_path):
    p = str(tmp_path / "log.jsonl")
    LOG.append(p, {"phase": "D", "kind": "registration", "id": "PHASE_D", "x": float("nan") if False else 1.0})
    LOG.append(p, {"phase": "D", "kind": "trial", "id": "B/LR/EV0", "result": LOG.sanitize({"exp": float("nan")})})
    assert LOG.verify(p) == (True, "2 records, chain intact")
    with pytest.raises(ValueError):
        LOG.append(p, {"phase": "D", "kind": "trial"})
    with open(p, "rb") as fh:
        lines = fh.read().split(b"\n")
    rec = json.loads(lines[0])
    rec["x"] = 2.0
    lines[0] = json.dumps(rec).encode()
    with open(p, "wb") as fh:
        fh.write(b"\n".join(lines))
    ok, why = LOG.verify(p)
    assert not ok and "record 2" in why
    with pytest.raises(ValueError, match="chain broken"):
        LOG.append(p, {"phase": "D", "kind": "trial", "id": "late"})


def _spec(**kw):
    s = {"broker_name": "Example", "server": "Example-Live", "symbol": "XAUUSD", "account_currency": "USD", "account_type": "raw",
         "contract_size_oz": 100, "min_lot": 0.01, "lot_step": 0.01, "max_lot": 50, "tick_size": 0.01, "tick_value_account_ccy": 1.0,
         "digits": 2, "commission_per_lot_round_trip_account_ccy": 7.0, "typical_spread_points": 20, "spread_source": "spec page",
         "slippage_assumption_points": 10, "slippage_source": "operator fills", "margin_percent": 1.0, "leverage": 100,
         "stop_out_level_percent": 50, "swap_long_per_lot_account_ccy": -30, "swap_short_per_lot_account_ccy": 5,
         "server_time_zone": "NY+7", "trading_hours_utc": "Sun 23:00 - Fri 22:00", "spec_source": "MT5 specification", "spec_date": "2026-11-09"}
    s.update(kw)
    return s


def test_broker_spec_refuses_missing_or_assumed_values_and_separates_account_pnl():
    with open("research/broker/BROKER_SPEC_TEMPLATE.json") as fh:
        tmpl = json.load(fh)
    with pytest.raises(BR.SpecError) as e:
        BR.validate(tmpl)
    assert len(str(e.value).split("; ")) == len(BR.REQUIRED)
    for bad in ({"contract_size_oz": "ASSUMED"}, {"tick_value_account_ccy": 2.0}, {"min_lot": 0.015}, {"leverage": 0}):
        with pytest.raises(BR.SpecError):
            BR.validate(_spec(**bad))
    m = BR.money_terms(_spec(), 0.5)
    assert m["ounces"] == 50 and m["per_usd_move_account_ccy"] == pytest.approx(50.0)
    assert m["round_trip_cost_usd_per_oz"] == pytest.approx(0.20 + 2 * 0.10 + 0.07)
    with pytest.raises(BR.SpecError):
        BR.money_terms(_spec(), 0.005)
    assert BR.account_pnl([1.0, -2.0], _spec(), 0.5)["total_account_ccy"] == pytest.approx(-50.0)
    assert BR.margin(_spec(), 0.5, 4000.0) == pytest.approx(2000.0)
