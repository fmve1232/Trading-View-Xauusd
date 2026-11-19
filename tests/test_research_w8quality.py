"""B31b-W8 (research/registrations/B31b-W8.json): quality-selected breakout entries at the operator's measured cost.

The selection uses training rows only (the scored fold's outcomes cannot move its threshold), fold 1 is never traded,
the decision cost replaces the model by session and the W3 model is only the dated fallback, re-costing is exact, the
R3 bootstrap and the candidate rule need every registered condition, Holm, the partition gate, the registration's
constants, and an end-to-end run on synthetic bars that trades only E0 / E1 on scored events."""
import json
import os

import numpy as np
import pandas as pd
import pytest

from quantum.research import harness as H
from quantum.research import w3liq as W
from quantum.research import w7breakout as X
from quantum.research import w8quality as Q

REG = json.load(open(os.path.join(os.path.dirname(__file__), "..", "research", "registrations", "B31b-W8.json")))


def synthetic(n=1200, seed=4):
    g = H.seeded_rng(seed)
    Xm = g.normal(size=(n, len(Q.QCOLS)))
    y = (g.uniform(size=n) < 1 / (1 + np.exp(-(0.8 * Xm[:, 3] - 0.5 * Xm[:, 4])))).astype(float)
    t = np.arange(n, dtype=np.int64) * 3600 + 1_600_000_000
    return Xm, y, t, t + 4 * 3600


# ---------------- selection ----------------
def test_the_threshold_is_the_80th_percentile_of_the_training_scores_and_fold_1_is_not_scored():
    Xm, y, t, te = synthetic()
    lo, hi = int(t[0]), int(t[-1]) + 1
    score, thr, sel = Q.quality(Xm, y, t, te, lo, hi)
    edges = np.linspace(lo, hi, 7)
    f1 = t < edges[1]
    assert np.isnan(score[f1]).all() and not sel[f1].any()
    f = 3
    fold = (t >= edges[f]) & (t < edges[f + 1])
    tr = te < edges[f]
    Xtr, Xfold, _, _ = W.standardize(Xm[tr], Xm[fold])
    w = W.logit_fit(Xtr, y[tr])
    assert np.allclose(score[fold], W.logit_pred(w, Xfold))
    assert np.allclose(thr[fold], np.percentile(W.logit_pred(w, Xtr), 80))
    assert (sel[fold] == (score[fold] >= thr[fold])).all() and 0.05 < sel[fold].mean() < 0.4


def test_the_scored_folds_own_outcomes_cannot_move_its_scores_or_threshold():
    Xm, y, t, te = synthetic()
    lo, hi = int(t[0]), int(t[-1]) + 1
    a = Q.quality(Xm, y, t, te, lo, hi)
    edges = np.linspace(lo, hi, 7)
    last = t >= edges[5]
    y2 = y.copy()
    y2[last] = 1 - y2[last]                                         # flip every outcome of the last fold
    b = Q.quality(Xm, y2, t, te, lo, hi)
    assert np.allclose(a[0][last], b[0][last]) and np.allclose(a[1][last], b[1][last])


def test_reliability_bins_cover_every_scored_event():
    Xm, y, t, te = synthetic()
    score, _, _ = Q.quality(Xm, y, t, te, int(t[0]), int(t[-1]) + 1)
    rel = Q.reliability(score, y)
    assert len(rel) == 10 and sum(b["n"] for b in rel) == int(np.isfinite(score).sum())


# ---------------- cost ----------------
def cost_file(tmp_path, **kw):
    c = {"registration": "B31b-W8", "source": "operator MT5 specification + statement", "per_session_usd_oz":
         {s: 0.40 for s in Q.SESSIONS}}
    c.update(kw)
    p = tmp_path / "cost.json"
    p.write_text(json.dumps(c))
    return str(p)


def test_the_measured_cost_is_required_until_the_registered_fallback_date(tmp_path):
    with pytest.raises(SystemExit):
        Q.load_cost(None, "2026-12-02")
    fb = Q.load_cost(None, "2026-12-03")
    assert fb["per_session_usd_oz"] is None and "FALLBACK" in fb["source"]
    assert Q.load_cost(cost_file(tmp_path), "2026-11-20")["per_session_usd_oz"]["ASIA"] == 0.40
    with pytest.raises(AssertionError):
        Q.load_cost(cost_file(tmp_path, per_session_usd_oz={"ASIA": 0.4}), "2026-11-20")       # a session missing
    assert Q.FALLBACK_FROM in json.dumps(REG["cost"])


def test_apply_cost_maps_every_bar_by_session_and_returns_the_model():
    class P:
        cost = np.array([0.9, 0.8, 0.7])
        sess = np.array(["ASIA", "NY_OPEN", "OFF"], object)
    c = {"per_session_usd_oz": {s: float(k + 1) for k, s in enumerate(Q.SESSIONS)}}
    model = Q.apply_cost(P, c)
    assert list(model) == [0.9, 0.8, 0.7] and list(P.cost) == [1.0, 4.0, 7.0]
    P.cost = model.copy()
    assert list(Q.apply_cost(P, {"per_session_usd_oz": None})) == [0.9, 0.8, 0.7] and list(P.cost) == [0.9, 0.8, 0.7]


def test_recost_is_exact():
    D, c, g = 9.0, 0.8, 10.0                                        # a +$10 winner, stop $9, cost $0.80
    r = {"D": D, "cost": c, "tp10_r": (g - c) / (D + c)}
    assert Q.recost(r, 0.4) == pytest.approx((g - 0.4) / (D + 0.4)) and Q.recost(r, c) == pytest.approx(r["tp10_r"])


# ---------------- statistics and the decision ----------------
def test_boot_two_is_one_sided_and_day_clustered():
    g = H.seeded_rng(1)
    d = np.repeat(np.arange(60), 5)
    hi, lo = (g.uniform(size=300) < 0.6).astype(float), (g.uniform(size=300) < 0.4).astype(float)
    p, ci = Q.boot_two(hi, d, lo, d)
    assert p < 0.01 and ci[0] > 0
    p2, _ = Q.boot_two(lo, d, hi, d)
    assert p2 > 0.99


def summary(n=150, mr=0.05, lb=0.01):
    return {"n": n, "tp10": {"mean_net_r": mr}, "tp10_mean_net_r_boot95_day": [lb, 0.1]}


@pytest.mark.parametrize("s, holm_p, r3_p, ok", [
    (summary(), 0.01, 0.01, True),
    (summary(), 0.06, 0.01, False),                                 # Holm
    (summary(mr=-0.01, lb=-0.05), 0.01, 0.01, False),               # expectancy
    (summary(lb=-0.001), 0.01, 0.01, False),                        # lower bound
    (summary(n=99), 0.01, 0.01, False),                             # fewer than 100 decided trades
    (summary(), 0.01, 0.2, False),                                  # selection adds nothing over R3
    (summary(), None, 0.01, False)])
def test_the_candidate_rule_needs_every_registered_condition(s, holm_p, r3_p, ok):
    assert Q.candidate(s, holm_p, r3_p) is ok


def test_holm():
    assert Q.holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": None}) == {"a": 0.03, "c": 0.06, "b": 0.06}


def test_only_the_development_partition_runs():
    for part in ("validation", "holdout"):
        with pytest.raises(H.SealedPartition):
            Q.main(["--part", part, "--rd", "nowhere", "--out", "nowhere.json"])


def test_the_registration_fixes_what_the_code_runs():
    assert (Q.QUANTILE, Q.FOLDS, Q.MIN_DECIDED, len(Q.CANDIDATES)) == (80.0, 6, 100, 4)
    assert "80th percentile" in REG["quality_selection"]["selected"] and "6 folds" in REG["quality_selection"]["fitting"]
    assert "4: {E0, E1} x {M15, M30}" in REG["tests"]["candidates"] and "at least 100 decided trades" in REG["tests"]["decision"]
    assert Q.QCOLS == X.BASE + X.GROUPS["candle"] and set(Q.SESSIONS) == set(W.SESS)


# ---------------- end to end on synthetic bars ----------------
def level_rich(n=2600, seed=9):
    g = H.seeded_rng(seed)
    rows, px = [], 4000.0
    for k in range(n):
        quiet = (k // 40) % 2 == 0
        step = g.normal(0, 0.08) if quiet else g.normal(0.25 * (1 if (k // 80) % 2 else -1), 1.0)
        o, c = px, px + step
        w = 0.15 if quiet else 0.8
        rows.append((o, max(o, c) + abs(g.normal(0, w)), min(o, c) - abs(g.normal(0, w)), c))
        px = c
    idx = pd.date_range("2026-03-01 22:00", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"]).assign(volume=np.nan)


def test_end_to_end_trades_only_e0_e1_on_scored_events_at_the_decision_cost(tmp_path):
    m15 = level_rich()
    h1 = m15.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["open"])
    cost = Q.load_cost(cost_file(tmp_path), "2026-11-20")
    res = Q.build(m15, h1, None, int(m15.index[0].timestamp()), cost)
    rows = res["rows"]
    assert rows and {r["m"] for r in rows} <= {"E0", "E1"} and any(r["selected"] for r in rows)
    filled = [r for r in rows if r["status"] == "FILLED"]
    assert filled and all(r["cost"] == 0.40 for r in filled) and all(r["model_cost"] != 0.40 for r in filled)
    first_fold_end = np.linspace(int(m15.index[0].timestamp()), res["t_end"], 7)[1]
    assert all(r["t_dec"] >= first_fold_end for r in rows)
    out = Q.analyse(res)
    assert set(out["candidates"]) == {"E0:M15", "E0:M30", "E1:M15", "E1:M30"} and out["overall"] in ("NO CANDIDATE",) or \
        out["overall"].startswith("CANDIDATE")
