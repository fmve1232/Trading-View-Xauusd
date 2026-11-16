"""B31b-W1 (research/registrations/B31b-W1.json): A / B with the engine's structure rules made volume-neutral.
Synthetic data only; the sealed partitions are never opened here."""
import json
import math

import numpy as np
import pytest

from quantum import config, engine
from quantum.data.market import load_synthetic
from quantum.features import compute as compute_features
from quantum.research import b31, b31w1 as W


@pytest.fixture(scope="module")
def no_volume():
    """A synthetic 15m market stored without volume, as the 2020-25 research history is."""
    m = load_synthetic("15m", bars=2500, seed=5)
    m.base = m.base.assign(volume=0.0)
    F = compute_features(m, config.DEFAULT)
    return m, F


def _events(res, kinds=W.STRUCT):
    return [(e["i"], e["type"], e["dir"]) for e in res.events if e["type"] in kinds]


def test_registration_matches_the_code():
    with open("research/registrations/B31b-W1.json") as f:
        reg = json.load(f)
    assert reg["id"] == W.REG and reg["approved_by_operator"] is True and reg["partitions"] == ["development", "validation", "holdout"]
    assert W.LADDER == 15.0 and "(15 - cost) / (D + cost) >= 1.0" in reg["eligibility"]
    assert W.GATE == 30 and "at least 30 executed A + B trades" in reg["step_1_firing_rates_before_any_outcome"]["gate"]
    assert W.UNITS == ("A", "B", "AB") and W.MIN_OOS == 30 and "Holm over the 3 units" in reg["primary_test"]["rule"]
    assert "v = 1 and vol_sma20 = 0" in reg["detector"]["rule"]


def test_neutral_features_change_only_the_two_volume_fields_and_not_the_original(no_volume):
    _, F = no_volume
    v0, s0 = np.array(F["v"], float).copy(), np.array(F["vol_sma20"], float).copy()
    G = W.neutral_features(F)
    assert (np.asarray(G["v"]) == 1.0).all() and (np.asarray(G["vol_sma20"]) == 0.0).all()
    assert np.array_equal(np.asarray(F["v"], float), v0) and np.array_equal(np.asarray(F["vol_sma20"], float), s0, equal_nan=True)
    assert set(G) == set(F) and all(G[k] is F[k] for k in F if k not in ("v", "vol_sma20"))


def test_without_volume_the_engine_has_no_bos_and_the_neutral_run_has(no_volume):
    m, F = no_volume
    as_is = engine.run(m, config.DEFAULT, "treatment", F)
    neutral = engine.run(m, config.DEFAULT, "treatment", W.neutral_features(F))
    assert not _events(as_is, ("BOS",))                                   # the B31 finding, reproduced
    assert len(_events(neutral, ("BOS",))) > 0
    ra, rn = W.event_rates(as_is, len(m.base)), W.event_rates(neutral, len(m.base))
    assert ra["BOS"]["n"] == 0 and rn["events"] == len(_events(neutral)) and rn["per_1000"] == round(1000 * rn["events"] / 2500, 2)
    assert rn["events"] > ra["events"]


def test_the_neutral_detector_never_reads_a_later_bar(no_volume):
    m, _ = no_volume
    full = engine.run(m, config.DEFAULT, "treatment", W.neutral_features(compute_features(m, config.DEFAULT)))
    cut = 2000
    m2 = load_synthetic("15m", bars=2500, seed=5)
    m2.base = m2.base.assign(volume=0.0).iloc[:cut]
    part = engine.run(m2, config.DEFAULT, "treatment", W.neutral_features(compute_features(m2, config.DEFAULT)))
    assert _events(part) == [e for e in _events(full) if e[0] < cut] and len(_events(part)) > 5


def test_ladder_eligibility_and_b31s_default_is_unchanged():
    X = b31.Ctx.__new__(b31.Ctx)
    X.pools = {k: np.full(3, np.nan) for k in b31.SELL_SIDE + b31.BUY_SIDE + ("CDH", "CDL")}
    s = lambda D: {"dir": 1, "stop": 4000.0 - D}
    assert b31.check(X, s(13.0), 4000.0, 1, 0.77) == "reward"                       # B31: (10 - .77) / (13 + .77) < 1
    assert b31.check(X, s(13.0), 4000.0, 1, 0.77, W.LADDER) is None                 # ladder: (15 - .77) / (13.77) = 1.03
    assert b31.check(X, s(14.0), 4000.0, 1, 0.77, W.LADDER) == "reward"             # 14.23 / 14.77 < 1
    assert b31.check(X, s(8.0), 4000.0, 1, 0.77) is None and b31.check(X, s(4.9), 4000.0, 1, 0.77, W.LADDER) == "stop"


def _tr(i, mod, tp1, r3, bar=None, exit_bar=None):
    return {"t": 1700000000 + 86400 * i, "bar": 10 * i if bar is None else bar, "exit_bar": 10 * i + 3 if exit_bar is None else exit_bar,
            "dir": 1, "out": "TP" if tp1 else "SL", "tp2": "SL", "tp3": "SL", "r": 0.0, "r_thirds": r3, "mod": mod}


def test_pooling_a_and_b_is_one_position_at_a_time_and_an_identical_entry_once():
    a = [_tr(0, "A", True, 1.0, bar=10, exit_bar=20), _tr(1, "A", True, 1.0, bar=40, exit_bar=41)]
    b = [_tr(0, "B", False, -1.0, bar=10, exit_bar=12), _tr(1, "B", False, -1.0, bar=15, exit_bar=18), _tr(2, "B", True, 1.0, bar=21, exit_bar=30)]
    assert [(x["mod"], x["bar"]) for x in W.pool_ab(a, b)] == [("A", 10), ("B", 21), ("A", 40)]


def _parts(oos, dev_r, rnd_rate=0.40, rnd_n=2000):
    res = lambda u, n: {"rnd": {"n": rnd_n, "tp1_rate": rnd_rate}, "ladder_r": dev_r}
    P = {"development": {"results": {f"{u}|model": res(u, 0) for u in W.UNITS}, "trades": {}}}
    half = len(oos) // 2
    for p, tr in (("validation", oos[:half]), ("holdout", oos[half:])):
        P[p] = {"results": {f"{u}|model": res(u, len(tr)) for u in W.UNITS}, "trades": {u: tr for u in W.UNITS}}
    return P


def test_the_registered_rule():
    good = [_tr(i, "A", i % 10 < 7, 0.5 if i % 10 < 7 else -0.6) for i in range(60)]      # 70% TP1, ladder +0.17
    d = W.decide(_parts(good, dev_r=0.1))
    assert d["A"]["verdict"] == "SUPPORTED" and d["A"]["n_oos"] == 60 and d["A"]["tp1_rate_oos"] == pytest.approx(0.7)
    assert d["A"]["ladder_r"] == pytest.approx(0.7 * 0.5 - 0.3 * 0.6) and d["A"]["ladder_boot95"][0] > 0 and d["A"]["holm_p"] < 0.05
    assert W.decide(_parts(good, dev_r=-0.1))["A"]["verdict"] == "NOT SUPPORTED"           # development had the other sign
    assert W.decide(_parts(good, dev_r=0.1, rnd_rate=0.70))["A"]["verdict"] == "NOT SUPPORTED"   # no better than random
    losing = [_tr(i, "A", i % 10 < 7, 0.2 if i % 10 < 7 else -1.0) for i in range(60)]     # 70% TP1 but ladder -0.16
    assert W.decide(_parts(losing, dev_r=0.1))["A"]["verdict"] == "NOT SUPPORTED"          # a hit rate without money
    noisy = [_tr(i, "A", i % 10 < 7, 3.0 if i % 20 == 0 else -0.1) for i in range(60)]     # positive mean, interval through 0
    dn = W.decide(_parts(noisy, dev_r=0.1))["A"]
    assert dn["ladder_r"] > 0 and dn["ladder_boot95"][0] <= 0 and dn["verdict"] == "NOT SUPPORTED"
    few = W.decide(_parts(good[:29], dev_r=0.1))["A"]
    assert few["verdict"] == "INSUFFICIENT" and few["n_oos"] == 29
    assert W.decide(_parts([], dev_r=0.1))["B"]["verdict"] == "INSUFFICIENT" and math.isnan(W.decide(_parts([], 0.1))["B"]["holm_p"])


def test_step_2_refuses_to_run_when_the_gate_did_not_pass(tmp_path, capsys):
    f = tmp_path / "step1.json"
    f.write_text(json.dumps({"gate": {"needs": 30, "passed": False}}))
    assert W.main(["--rd", "nowhere", "--step", "2", "--step1", str(f), "--out", str(tmp_path / "o.json")]) == 2
    assert "step 2 is not run" in capsys.readouterr().out and not (tmp_path / "o.json").exists()


def test_run_module_passes_the_ladder_reward_through():
    from tests.test_research_b31 import BASE, WIN, _a
    wide = {**BASE, **WIN, 10: (3992, 3993, 3984.0, 3991)}          # the sweep reaches 3984: stop 3983, D = 12 from the 3995 limit
    X, evs = _a(wide)
    sets = b31.setups(X, "A", evs)
    r10 = b31.run_module(X, sets, 0)
    r15 = b31.run_module(X, sets, 0, "model", W.LADDER)
    assert r10["stat"]["rejected"] == {"reward": 1} and r10["stat"]["executed"] == 0       # B31: (10 - .8) / 12.8 < 1
    assert r15["stat"]["executed"] == 1 and r15["trades"][0]["D"] == pytest.approx(12.0, abs=0.05)


def test_step_1_returns_counts_only_and_step_2_runs_end_to_end(monkeypatch):
    import pandas as pd
    m15 = load_synthetic("15m", bars=3000, seed=5).base.assign(volume=0.0)
    h1 = load_synthetic("1h", bars=1500, seed=5).base
    start = m15.index[0] + pd.Timedelta(days=5)
    monkeypatch.setattr(W, "load_part", lambda rd, part: (m15, h1, start))
    quiet = lambda *_: None
    s1 = W.step1("unused", quiet)
    assert s1["structure_as_is"]["BOS"]["n"] == 0 and s1["structure_volume_neutral"]["events"] > s1["structure_as_is"]["events"]
    assert set(s1["modules"]) == {"A", "B", "E"} and all(isinstance(v["executed"], int) for v in s1["modules"].values())
    flat = json.dumps(s1)
    assert not any(k in flat for k in ('"trades"', '"out"', "r_thirds", "ladder_r", "tp1_first", "mean_r", "mfe"))   # no outcome leaves step 1
    assert s1["executed_A_plus_B"] == s1["modules"]["A"]["executed"] + s1["modules"]["B"]["executed"]
    assert s1["gate"] == {"needs": 30, "passed": s1["executed_A_plus_B"] >= 30}
    f = s1["funnel"]
    assert f["rejected_sweeps"] >= f["any_structure_within_8"] >= f["shift_within_8"] >= 0 and f["rejected_sweeps"] > 0
    _, X, t_from, _ = W.context(m15, h1, start)
    evs = b31.crossings(X, b31.SELL_SIDE + b31.BUY_SIDE)
    assert W.sweep_funnel(X, evs, 0)["rejected_sweeps"] > W.sweep_funnel(X, evs, t_from)["rejected_sweeps"] == f["rejected_sweeps"]
    part = W.run("unused", "development", None, quiet)
    assert set(part["trades"]) == {"A", "B", "E", "AB"}
    assert all(f"{u}|{c}" in part["results"] for u in ("A", "B", "E", "AB") for c in ("model", "operator"))
    assert part["results"]["A|model"]["stat"] == s1["modules"]["A"]                        # step 1 counted the same orders
    d = W.decide({"development": part, "validation": part, "holdout": part})
    assert set(d) == set(W.UNITS) and all(v["verdict"] in ("SUPPORTED", "NOT SUPPORTED", "INSUFFICIENT") for v in d.values())
