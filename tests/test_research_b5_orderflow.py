"""Phase B5 order-flow study (quantum/research/b5_orderflow.py) on SYNTHETIC trades and a MOCKED Databento client.
Nothing here touches the network or real exchange data. Checks: aggressor signs, windows, OFI, queue imbalance, rolls,
no look-ahead, the cost guard, the walk-forward purge, the model maths, and the end-to-end study shape."""
import json
import math
import sys
import types

import numpy as np
import pandas as pd
import pytest

from quantum.research import b2
from quantum.research import b5_orderflow as B


def _trades(rows):
    """rows: (utc time, side, size, bid, ask, bid size, ask size, instrument)."""
    t = pd.DatetimeIndex([r[0] for r in rows], tz="UTC")
    return pd.DataFrame({"side": [r[1] for r in rows], "size": [r[2] for r in rows], "bid_px_00": [r[3] for r in rows],
                         "ask_px_00": [r[4] for r in rows], "bid_sz_00": [r[5] for r in rows], "ask_sz_00": [r[6] for r in rows],
                         "instrument_id": [r[7] for r in rows]}, index=t)


def _synthetic_flow(start="2021-01-04 00:00", bars=3000, seed=3, inst_change_at=None):
    g = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=bars, freq="15min", tz="UTC")
    raw = pd.DataFrame({"buy": g.integers(50, 500, bars).astype(float), "sell": g.integers(50, 500, bars).astype(float)}, index=idx)
    raw["buy5"], raw["sell5"] = raw["buy"] / 3, raw["sell"] / 3
    raw["buy1"], raw["sell1"] = raw["buy"] / 15, raw["sell"] / 15
    raw["n"] = g.integers(20, 400, bars).astype(float)
    raw["ofi"] = g.normal(0, 30, bars)
    raw["depth"] = raw["n"] * g.uniform(5, 15, bars)
    raw["qimb"] = g.uniform(-1, 1, bars)
    raw["spread"] = 0.1
    raw["inst"] = 1.0
    if inst_change_at is not None:
        raw.iloc[inst_change_at:, raw.columns.get_loc("inst")] = 2.0
    return raw


def _spot(start="2021-01-04 00:00", bars=3600, seed=5):
    g = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=bars, freq="15min", tz="UTC")
    c = 1800 + np.cumsum(g.normal(0, 2.0, bars))
    o = np.r_[c[0], c[:-1]]
    hi = np.maximum(o, c) + g.uniform(0, 1.5, bars)
    lo = np.minimum(o, c) - g.uniform(0, 1.5, bars)
    return pd.DataFrame({"open": o, "high": hi, "low": lo, "close": c, "volume": 0.0}, index=idx)


def test_aggressor_signs_windows_and_last_book():
    rows = [("2021-03-01 10:00:30", "B", 5, 1700.0, 1700.1, 10, 20, 7),
            ("2021-03-01 10:06:00", "A", 2, 1700.0, 1700.1, 12, 20, 7),
            ("2021-03-01 10:11:00", "B", 3, 1700.0, 1700.1, 12, 18, 7),
            ("2021-03-01 10:14:30", "N", 9, 1700.0, 1700.2, 30, 10, 7),       # unknown side: no sign
            ("2021-03-01 10:15:00", "A", 4, 1700.1, 1700.2, 6, 6, 7)]         # the next bar
    f = B.bar_features(_trades(rows))
    r0 = f.loc[pd.Timestamp("2021-03-01 10:00", tz="UTC")]
    assert (r0["buy"], r0["sell"], r0["n"]) == (8.0, 2.0, 4.0)
    assert (r0["buy5"], r0["sell5"], r0["buy1"], r0["sell1"]) == (3.0, 0.0, 0.0, 0.0)
    assert r0["qimb"] == pytest.approx((30 - 10) / 40) and r0["spread"] == pytest.approx(0.2)
    r1 = f.loc[pd.Timestamp("2021-03-01 10:15", tz="UTC")]
    assert (r1["buy"], r1["sell"], r1["n"]) == (0.0, 4.0, 1.0)
    ff = B.finish_features(f)
    assert ff.loc[pd.Timestamp("2021-03-01 10:00", tz="UTC"), "imb15"] == pytest.approx(0.6)
    assert ff.loc[pd.Timestamp("2021-03-01 10:15", tz="UTC"), "imb15"] == pytest.approx(-1.0)


def test_trade_sampled_ofi_signs():
    up = [("2021-03-01 10:00:00", "B", 1, 1700.0, 1700.1, 10, 10, 1),
          ("2021-03-01 10:01:00", "B", 1, 1700.1, 1700.2, 10, 10, 1),       # bid and ask tick up: buying pressure
          ("2021-03-01 10:02:00", "B", 1, 1700.1, 1700.2, 25, 10, 1)]       # bid queue grows
    dn = [(t, s, z, 3400.2 - a, 3400.2 - b, as_, bs, i) for (t, s, z, b, a, bs, as_, i) in up]   # mirror image
    e_up = B.bar_features(_trades(up))["ofi"].iloc[0]
    e_dn = B.bar_features(_trades(dn))["ofi"].iloc[0]
    assert e_up > 0 and e_dn < 0 and e_up == pytest.approx(-e_dn)
    assert e_up == pytest.approx((10 + 10) + (25 - 10))                     # CKS 2014 terms, step by step


def test_no_look_ahead_in_features_and_rules():
    raw = _synthetic_flow(bars=4000)
    full = B.finish_features(raw)
    sig_full = {x: B.rule_signal(full[x]) for x in B.RULE_FEATURES}
    for k in (2600, 3500):
        part = B.finish_features(raw.iloc[:k])
        cols = list(B.MODEL_FEATURES)
        pd.testing.assert_frame_equal(part[cols], full[cols].iloc[:k])
        for x in B.RULE_FEATURES:
            pd.testing.assert_series_equal(B.rule_signal(part[x]), sig_full[x].iloc[:k])
    assert all((s != 0).sum() > 100 for s in sig_full.values())


def test_roll_days_are_blanked():
    raw = _synthetic_flow(bars=800, inst_change_at=300)
    f = B.finish_features(raw)
    day = raw.index[300].normalize()
    bad = f.index.normalize().isin([day, day + pd.Timedelta(days=1)])
    assert f.loc[bad, list(B.MODEL_FEATURES)].isna().all().all()
    assert f.loc[~bad, "imb15"].notna().all() and f["roll_day"].sum() == bad.sum()


def test_walk_forward_is_purged_and_forward_only():
    I = np.repeat(np.arange(6000), 2)
    folds = B.walk_forward(I, 288)
    assert len(folds) == B.BLOCKS - 1
    for train, test in folds:
        assert len(test) and len(train)
        assert (I[train] + 288 < I[test].min()).all()                         # no label window reaches the test block
    assert sum(len(t) for _, t in folds) < len(I)                            # block 1 is never predicted


def test_logistic_auc_and_calibration():
    g = np.random.default_rng(1)
    X = g.normal(size=(20000, 2))
    p = 1 / (1 + np.exp(-(0.3 + 1.2 * X[:, 0])))
    y = (g.uniform(size=len(p)) < p).astype(float)
    w = B.fit_logistic(X, y, l2=0.0)
    assert w[1] == pytest.approx(1.2, abs=0.08) and abs(w[2]) < 0.06 and w[0] == pytest.approx(0.3, abs=0.06)
    assert B.auc(np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.3, 0.4])) == 1.0
    assert B.auc(np.array([0, 1, 0, 1]), np.array([0.5, 0.5, 0.5, 0.5])) == 0.5
    cal = B.calibration(y, p)
    assert cal["ece"] < 0.02 and cal["slope"] == pytest.approx(1.0, abs=0.1) and abs(cal["intercept"]) < 0.1
    bad = B.calibration(y, np.clip(p * 0.5, 0, 1))
    assert bad["ece"] > 0.15


class _FakeStore:
    def __init__(self, df):
        self.df = df

    def to_df(self):
        return self.df


def _fake_databento(monkeypatch, cost, frames):
    calls = {"get_range": 0, "get_cost": 0}

    class Meta:
        def get_cost(self, **kw):
            calls["get_cost"] += 1
            assert kw["dataset"] == "GLBX.MDP3" and kw["schema"] in ("tbbo", "trades") and kw["symbols"] == ["GC.v.0"] and kw["stype_in"] == "continuous"
            return cost if kw["schema"] == B.SCHEMA else cost * 1.5          # the declared schema costs `cost`

    class TS:
        def get_range(self, **kw):
            calls["get_range"] += 1
            a, b = pd.Timestamp(kw["start"]), pd.Timestamp(kw["end"])
            df = frames[(frames.index >= a) & (frames.index < b)].copy()
            df["ts_event"] = df.index
            if kw["schema"] == "trades":                                     # a trades frame has no book columns
                df = df.drop(columns=list(B.BOOK))
            return _FakeStore(df.reset_index(drop=True))

    class Hist:
        def __init__(self, key):
            assert key == "test-key"
            self.metadata, self.timeseries = Meta(), TS()

    mod = types.SimpleNamespace(Historical=Hist, __version__="fake")
    monkeypatch.setitem(sys.modules, "databento", mod)
    return calls


def test_cost_guard_downloads_nothing_over_budget(monkeypatch):
    calls = _fake_databento(monkeypatch, 250.0, _trades([("2021-03-01 10:00:00", "B", 1, 1.0, 1.1, 1, 1, 1)]))
    with pytest.raises(RuntimeError, match="cost guard"):
        B.fetch("test-key", "2021-03-01", "2021-03-20", 100.0)
    assert calls == {"get_range": 0, "get_cost": 1}


def test_fetch_reduces_pieces_to_bars(monkeypatch):
    g = np.random.default_rng(2)
    t = pd.date_range("2021-03-01", "2021-03-20", freq="37s", tz="UTC")
    rows = [(str(x), "B" if g.uniform() < 0.5 else "A", int(g.integers(1, 5)), 1700.0, 1700.1, 10, 12, 4) for x in t]
    fr = _trades(rows)
    calls = _fake_databento(monkeypatch, 12.5, fr)
    raw, meta = B.fetch("test-key", "2021-03-01T00:00:00+00:00", "2021-03-20T00:00:00+00:00", 100.0)
    assert calls["get_range"] == math.ceil(19 / B.CHUNK_DAYS) and meta["cost_usd"] == 12.5 and meta["trades"] == len(fr)
    whole = B.bar_features(fr)
    pd.testing.assert_series_equal(raw["buy"], whole["buy"], check_freq=False)
    pd.testing.assert_series_equal(raw["n"], whole["n"], check_freq=False)
    assert raw.index.is_unique and raw["n"].sum() == len(fr)


def test_study_end_to_end_on_noise(monkeypatch):
    monkeypatch.setattr(b2, "HORIZON", 48)
    m15 = _spot(bars=3600)
    raw = _synthetic_flow(bars=3600)
    res = B.study(B.finish_features(raw), m15, models=(B.Logit,))
    rules = [t for t in res["trials"] if t["kind"] == "rule"]
    assert len(rules) == len(B.RULE_FEATURES) * 2 * len(B.TARGETS) == 12
    assert {t["id"] for t in res["trials"] if t["kind"] == "model"} == {f"15min LOGIT {tn}" for tn in B.TARGETS}
    for t in res["trials"]:
        if t["n"]:
            assert set(t["pass"]) >= {"1_wilson_lb_above_break_even", "2_t_above_3", "3_beats_random_by_2se", "4_bh_fdr10",
                                      "5_reality_check_p_below_0p05"}
    for tid, m in res["models"].items():
        assert 0.40 < m["auc"] < 0.60, tid                                   # features are noise
    assert res["family"]["trials"] == 15 and res["family"]["passes_all"] == []
    assert len(res["execution"]["by_imb15_decile"]) == 10


def test_study_finds_a_planted_edge(monkeypatch):
    """Power check: when the bar's flow carries the next hour's move, the rules and the model must see it. (The plant
    uses future prices on purpose; a real edge would be far weaker. This only proves the pipeline can say yes.)"""
    monkeypatch.setattr(b2, "HORIZON", 48)
    m15 = _spot(bars=3600)
    raw = _synthetic_flow(bars=3600)
    c = m15["close"].to_numpy()
    imb = np.tanh(np.r_[c[4:] - c[:-4], [0.0] * 4] / 3.0) * 0.8
    tot = raw["buy"] + raw["sell"]
    raw["buy"], raw["sell"] = tot * (1 + imb) / 2, tot * (1 - imb) / 2
    res = B.study(B.finish_features(raw), m15, models=(B.Logit,))
    tm = {t["id"]: t for t in res["trials"]}
    assert tm["15min imb15_CONT T10"]["z_vs_random"] > 3 and tm["15min imb15_REV T10"]["z_vs_random"] < -3
    assert all(m["auc"] > 0.7 for m in res["models"].values())
    assert tm["15min LOGIT T10"]["win_rate"] > tm["15min LOGIT T10"]["random_same_mix"] + 0.2


def test_trees_report_not_run_without_scikit_learn(monkeypatch):
    monkeypatch.setattr(b2, "HORIZON", 48)
    monkeypatch.setitem(sys.modules, "sklearn", None)
    monkeypatch.setitem(sys.modules, "sklearn.ensemble", None)
    res = B.study(B.finish_features(_synthetic_flow(bars=3000)), _spot(bars=3000), models=(B.Trees,))
    assert all(m["verdict"] == "NOT RUN" for m in res["models"].values())
    assert not any(t["kind"] == "model" for t in res["trials"])


def test_main_end_to_end_with_a_mocked_vendor(tmp_path, monkeypatch):
    monkeypatch.setattr(b2, "HORIZON", 48)
    m15 = _spot(bars=3000)
    monkeypatch.setattr(B.history, "load", lambda *a, **k: m15)
    g = np.random.default_rng(9)
    rows = []
    for t0, px in zip(m15.index, m15["close"].to_numpy()):
        for off in (60, 400, 870):
            rows.append((str(t0 + pd.Timedelta(seconds=off)), "B" if g.uniform() < 0.5 else "A", int(g.integers(1, 6)),
                         round(px - 0.05, 2), round(px + 0.05, 2), int(g.integers(1, 30)), int(g.integers(1, 30)), 5))
    fr = _trades(rows)
    calls = _fake_databento(monkeypatch, 42.0, fr)
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    out, trials = tmp_path / "r.json", tmp_path / "t.jsonl"
    assert B.main(["--spot", "unused", "--out", str(out), "--trials", str(trials)]) == 0
    r = json.loads(out.read_text())
    assert r["cost_usd"] == 42.0 and r["trades"] == len(fr) and r["partition"] == "development" and calls["get_cost"] == 1
    assert r["spot_bars_with_flow"] == 3000 and len([t for t in r["trials"] if t["kind"] == "rule"]) == 12
    lines = [json.loads(x) for x in trials.read_text().splitlines()]
    assert len(lines) == len(r["trials"]) and all(x["phase"] == "B5" and x["partition"] == "development" for x in lines)
    assert "passes all five" in B.summary(str(out))
    with pytest.raises(SystemExit, match="already"):
        B.main(["--spot", "unused", "--out", str(out), "--trials", str(trials)])
    # a FAILED run repeated from the flow cache pays nothing and reproduces the same numbers
    cache, t2, out2, out3 = tmp_path / "cache", tmp_path / "t2.jsonl", tmp_path / "r2.json", tmp_path / "r3.json"
    assert B.main(["--spot", "u", "--out", str(out2), "--trials", str(t2), "--flow-cache", str(cache)]) == 0
    n_calls = dict(calls)
    t2.unlink()
    assert B.main(["--spot", "u", "--out", str(out3), "--trials", str(t2), "--flow-cache", str(cache)]) == 0
    assert calls == n_calls                                                  # no quote, no download
    r2, r3 = json.loads(out2.read_text()), json.loads(out3.read_text())
    assert r3["from_cache"] is True and r3["cost_usd"] == 42.0
    same = [json.dumps(x["trials"], sort_keys=True) for x in (r, r2, r3)]   # NaN-safe comparison
    assert same[0] == same[1] == same[2]
    (cache / B.FLOW_META).write_text(json.dumps({"dataset": "OTHER"}))
    with pytest.raises(RuntimeError, match="different request"):
        B.load_flow_cache(str(cache))


def test_quote_only_downloads_nothing(tmp_path, monkeypatch):
    calls = _fake_databento(monkeypatch, 80.0, _trades([("2021-03-01 10:00:00", "B", 1, 1.0, 1.1, 1, 1, 1)]))
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    out = tmp_path / "q.json"
    assert B.main(["--spot", "unused", "--out", str(out), "--trials", str(tmp_path / "t.jsonl"), "--quote-only"]) == 0
    q = json.loads(out.read_text())
    assert q["quote_usd"] == 80.0 and q["schema"] == "trades" and q["alternatives_usd"] == {"tbbo": 120.0}
    assert calls == {"get_range": 0, "get_cost": 2} and not (tmp_path / "t.jsonl").exists()
    assert B.summary(str(out)).startswith("quote $80.00") and "tbbo $120.00" in B.summary(str(out))


def test_rerun_guard_and_missing_key(tmp_path, monkeypatch):
    p = tmp_path / "t.jsonl"
    assert not B._already_run(str(p))
    p.write_text('{"phase": "B5", "partition": "development", "id": "x"}\n')
    assert B._already_run(str(p))
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="DATABENTO_API_KEY"):
        B.main(["--spot", str(tmp_path), "--out", str(tmp_path / "o.json"), "--trials", str(p)])


def test_declared_constants():
    assert (B.DATASET, B.SCHEMA, B.SYMBOL, B.STYPE) == ("GLBX.MDP3", "trades", "GC.v.0", "continuous")   # amendment A1
    assert B.TARGETS == {"T10": (10.0, 10.0), "T15": (15.0, 10.0), "T20": (20.0, 10.0)}
    assert (B.PCT, B.PCT_BARS, B.BLOCKS, B.TOP_Q, B.AUC_MIN, B.Z_MIN, B.BH_Q, B.RC_P) == (0.90, 2000, 6, 0.90, 0.55, 2.0, 0.10, 0.05)
    assert B.MAX_COST_USD == 100.0 and B.RULE_FEATURES == ("imb15", "imb60") and B.MODEL_FEATURES == ("imb1", "imb5", "imb15", "imb60", "ntr_z")
    assert B.COLS == ("side", "size", "instrument_id") and B.DIRECTIONAL == ("imb1", "imb5", "imb15", "imb60")


def test_trades_frames_without_a_book_still_give_flow_features():
    rows = [("2021-03-01 10:00:30", "B", 5, 1700.0, 1700.1, 10, 20, 7), ("2021-03-01 10:11:00", "A", 3, 1700.0, 1700.1, 12, 18, 7)]
    f = B.bar_features(_trades(rows)[list(B.COLS)])
    r0 = f.iloc[0]
    assert (r0["buy"], r0["sell"], r0["buy5"], r0["sell5"], r0["n"]) == (5.0, 3.0, 0.0, 3.0, 2.0)
    assert np.isnan(r0["qimb"]) and np.isnan(r0["spread"]) and np.isnan(r0["ofi"]) and r0["inst"] == 7
    ff = B.finish_features(f)
    assert ff["imb15"].iloc[0] == pytest.approx(0.25) and np.isnan(ff["ofi15"].iloc[0])
