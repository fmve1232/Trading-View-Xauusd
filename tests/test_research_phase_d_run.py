"""Phase D's registered command (quantum/research/d_run.py) end to end on SYNTHETIC data: a synthetic Dukascopy cache
written by the real extractor, synthetic spot paths for development and 2026, then the data gates, features, labels,
study, questions and one-minute measurements. Checks the wiring, the gates, that trade files carry no prices and that
every trial reaches the hash-chained log. Small folds are passed in for speed; the registered values are unchanged."""
import functools
import json
import lzma
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import pytest

from quantum.research import b5c_dukascopy as C
from quantum.research import d_dukascopy as D
from quantum.research import d_log as LOG
from quantum.research import d_run as R
from quantum.research import d_study as S
from quantum.research import harness as H


def _prefix():
    """The committed log's registration / amendment prefix (later records belong to real runs)."""
    out = []
    with open(os.path.join(os.path.dirname(__file__), "..", "research", "phase_d_trials.jsonl"), "rb") as fh:
        for ln in fh:
            if json.loads(ln)["kind"] not in ("registration", "amendment"):
                break
            out.append(ln)
    return out


def _seed(path):
    with open(path, "wb") as fh:
        fh.write(b"".join(_prefix()))


def _m15(start, end, seed):
    g = H.seeded_rng(seed)
    idx = pd.date_range(start, end, freq="15min", tz="UTC", inclusive="left")
    idx = idx[(idx.day_of_week < 5) | ((idx.day_of_week == 6) & (idx.hour >= 23))]
    idx = idx[~((idx.day_of_week == 4) & (idx.hour >= 21))]
    c = 1800 + np.cumsum(g.normal(0, 3.0, len(idx)))
    o = np.r_[c[0], c[:-1]]
    w = g.uniform(0.2, 2.0, (2, len(idx)))
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + w[0], "low": np.minimum(o, c) - w[1], "close": c, "volume": 0.0}, index=idx)


def _h1(m15):
    return m15.resample("1h", label="left", closed="left").agg({"open": "first", "high": "max", "low": "min", "close": "last",
                                                                "volume": "sum"}).dropna()


def _ticks_for(m15, seed):
    """A fake Dukascopy hour: ticks through each bar's open -> close (units of 1/1000 $), a 0.30 spread."""
    g = H.seeded_rng(seed)
    o, c = m15["open"], m15["close"]

    def fetch(t):
        rows = []
        for q in range(4):
            bar = t + pd.Timedelta(minutes=15 * q)
            if bar not in o.index:
                continue
            for j in range(8):
                mid = (o[bar] + (c[bar] - o[bar]) * j / 7) * 1000
                rows.append((q * 900_000 + j * 110_000 + 5, int(mid + 150), int(mid - 150), float(g.uniform(1, 5)), float(g.uniform(1, 5))))
        return lzma.compress(b"".join(C.REC.pack(*r) for r in rows), format=lzma.FORMAT_ALONE) if rows else b""
    return fetch


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("phase_d")
    dev, y26 = _m15("2021-01-04", "2021-04-17", 1), _m15("2026-01-05", "2026-03-14", 2)
    cache = str(tmp / "cache")
    with ThreadPoolExecutor(4) as pool:
        for m15, seed in ((dev, 3), (y26, 4)):
            f = _ticks_for(m15, seed)
            for day in pd.date_range(m15.index[0].normalize(), m15.index[-1].normalize(), freq="D"):
                fr, _ = D.load_day(day, cache, pool, f)
                assert fr is not None
    pops = {"DEV": {"m15": dev, "h1": _h1(dev), "score_from": pd.Timestamp("2021-01-11", tz="UTC"), "scale": True},
            "Y2026": {"m15": y26, "h1": _h1(y26), "score_from": pd.Timestamp("2026-01-19", tz="UTC"), "scale": False}}
    mp = pytest.MonkeyPatch()
    mp.setattr(R, "populations", lambda *a, **k: {k_: dict(v) for k_, v in pops.items()})
    mp.setattr(R, "GRID", ((5, 5), (10, 10)))
    mp.setattr(R, "STOP_X", (5,))
    mp.setattr(R, "DYNAMIC", ((1.0, 1.0),))
    mp.setattr(R, "DYN_ALGOS", ("LR",))
    fast = {"wf_start": "2021-03-01", "min_train": 2500, "months": 1, "log": lambda *a: None}
    mp.setattr(S, "run", functools.partial(S.run, sets=("BASELINE", "B", "C"), **fast))
    q = S.questions
    mp.setattr(S, "questions", lambda *a, **k: q(*a, **{**k, **fast, "sets": ("BASELINE", "B"), "algos": ("LR",)}))
    out, log = tmp / "out", str(tmp / "phase_d_trials.jsonl")
    _seed(log)                                                                 # the committed chain continues
    code = R.main(["--rd", "unused", "--store", "none", "--cache", cache, "--out", str(out), "--log", log, "--algos", "LR"])
    mp.undo()
    return out, log, code


def test_the_command_runs_end_to_end(run_dir):
    out, _, code = run_dir
    assert code == 0
    rep = json.loads((out / "data_report.json").read_text())
    assert rep["DEV"]["status"] == "PASS" and rep["Y2026"]["status"] == "PASS" and rep["DEV"]["of_coverage_scored"] == 1.0
    assert rep["DEV"]["price_units_per_usd"] == 1000.0 and rep["intermarket"] == "none supplied"
    st = json.loads((out / "study.json").read_text())
    assert st["not_run"] == {"C": "no intermarket data"} and st["verdict"] in ("NO QUALIFIED STRATEGY", "QUALIFIES FOR FURTHER VALIDATION")
    assert len(st["strategies"]) == 2 * 1 * 4 and "incremental" in st and "B/LR" in st["incremental"]
    m1 = json.loads((out / "m1.json").read_text())
    assert {"DEV/dukascopy", "Y2026/dukascopy"} <= set(m1) and "5/5" in m1["DEV/dukascopy"]["BUY"]["grid"]
    dyn = json.loads((out / "dynamic.json").read_text())
    assert set(dyn) == {"ATR1.0/1.0"} and all(len(v["strategies"]) == 3 * 1 * 4 for v in dyn.values())
    q = json.loads((out / "questions.json").read_text())
    assert {"FAV5", "FAV20", "ADV_FIRST5"} <= set(q["labels"]) and q["labels"]["ADV_FIRST5"]["info"]["resolution"].startswith("one minute")


def test_every_trial_is_logged_on_an_intact_chain(run_dir):
    _, log, _ = run_dir
    ok, why = LOG.verify(log)
    assert ok, why
    with open(log) as fh:
        recs = [json.loads(x) for x in fh]
    kinds = [r["kind"] for r in recs]
    seed = len(_prefix())                                                      # the committed registration / amendment records
    assert kinds[0] == "registration" and set(kinds[:seed]) <= {"registration", "amendment"}
    assert kinds[seed] == "data_report" and kinds.count("trial") == 8 and kinds[-1] == "descriptive"
    assert kinds.count("trial-dynamic") == 1 * 3 * 1 * 4


def test_a_failed_gate_stops_the_run_as_insufficient_data(tmp_path, monkeypatch):
    dev = _m15("2021-01-04", "2021-02-06", 1)
    pops = {"DEV": {"m15": dev, "h1": _h1(dev), "score_from": pd.Timestamp("2021-01-11", tz="UTC"), "scale": True}}
    monkeypatch.setattr(R, "populations", lambda *a, **k: pops)
    log = str(tmp_path / "log.jsonl")
    assert R.main(["--rd", "x", "--store", "none", "--cache", str(tmp_path / "empty"), "--out", str(tmp_path / "o"), "--log", log]) == 3
    with open(log) as fh:
        rec = json.loads(fh.readline())
    assert rec["status"] == {"DEV": "NO DATA"}
    assert not os.path.exists(tmp_path / "o" / "study.json")


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "research", "tools"))
import phase_d_audit as AUD


def test_trade_files_are_written_for_every_strategy_without_prices(run_dir):
    out, _, _ = run_dir
    files = sorted((out / "trades" / "benchmark").glob("*__dev.csv"))
    assert len(files) == 8
    import pandas as pd
    for f in files:
        cols = set(pd.read_csv(f, nrows=1).columns)
        assert cols <= set(R.TRADE_COLS) and not cols & {"fill_px", "exit_px", "tp_px", "sl_px", "decision_px", "fill_mid"}
    assert (out / "trades" / "dynamic" / "ATR1.0_1.0").is_dir()
    rep = json.loads((out / "data_report.json").read_text())
    assert rep["DEV"]["clock_a1"]["failures"] == [] and rep["DEV"]["clock_a1"]["weekly"]["weeks_checked"] >= 10


def test_the_d4_audit_reproduces_every_figure_and_catches_tampering(run_dir, tmp_path):
    out, log, _ = run_dir
    res = AUD.audit(str(out), log)
    assert res["pass"], {k: v for k, v in res["checks"].items() if isinstance(v, dict) and not v["pass"]}
    work = tmp_path / "copy"
    shutil.copytree(out, work)
    f = min((work / "trades" / "benchmark").glob("*__dev.csv"))
    lines = f.read_text().splitlines()
    if len(lines) > 2:
        f.write_text("\n".join(lines[:-1]) + "\n")                          # a losing (or any) trade removed
        assert not AUD.audit(str(work), log)["checks"]["files"]["pass"]
    st = json.loads((work / "study.json").read_text())
    st["strategies"][-1]["dev"]["exp_oz"] = 99.0                              # a figure edited (another strategy than the file)
    st["strategies"][-1]["bh_q010"] = not st["strategies"][-1]["bh_q010"]
    (work / "study.json").write_text(json.dumps(st))
    bad = AUD.audit(str(work), log)["checks"]
    assert not bad["figures"]["pass"] and not bad["bh"]["pass"]


import phase_d_reports as REP


def test_the_appendix_is_generated_only_from_an_audited_run(run_dir, tmp_path):
    out, log, _ = run_dir
    md = tmp_path / "APPENDIX.md"
    assert REP.main([str(out), "--log", log, "--md", str(md)]) == 0
    txt = md.read_text()
    assert "study.json`: " in txt and "B/LR/EV0" in txt and "Incremental value" in txt and "One-minute measurements" in txt
    work = tmp_path / "bad"
    import shutil as _sh
    _sh.copytree(out, work)
    st = json.loads((work / "study.json").read_text())
    st["strategies"][-1]["dev"]["exp_oz"] = 5.0
    (work / "study.json").write_text(json.dumps(st))
    assert REP.main([str(work), "--log", log, "--md", str(tmp_path / "x.md")]) == 1 and not (tmp_path / "x.md").exists()


def test_the_price_only_family_runs_and_audits(tmp_path, monkeypatch):
    """Amendment A2's price-only command on synthetic populations: sets BASELINE and A only, its own family, audited."""
    from quantum.research import d_price as DP
    dev, y26 = _m15("2021-01-04", "2021-04-17", 1), _m15("2026-01-05", "2026-03-14", 2)
    pops = {"DEV": {"m15": dev, "h1": _h1(dev), "score_from": pd.Timestamp("2021-01-11", tz="UTC"), "scale": True},
            "Y2026": {"m15": y26, "h1": _h1(y26), "score_from": pd.Timestamp("2026-01-19", tz="UTC"), "scale": False}}
    monkeypatch.setattr(R, "populations", lambda *a, **k: pops)
    fast = {"wf_start": "2021-03-01", "min_train": 2500, "months": 1, "algos": ("LR",)}
    monkeypatch.setattr(S, "run", functools.partial(S.run, **fast))
    log = str(tmp_path / "log.jsonl")
    _seed(log)
    out = tmp_path / "out"
    assert DP.main(["--rd", "x", "--out", str(out), "--log", log, "--skip-questions"]) == 0
    st = json.loads((out / "study.json").read_text())
    assert {s["set"] for s in st["strategies"]} == {"BASELINE", "A"} and st["family_id"] == "D3-P" and "D3-P" in st["verdict"]
    assert AUD.audit(str(out), log)["pass"]


def test_the_appendix_reports_not_run_sections():
    assert REP.m1_section({"not_run": "no one-minute data"}) == ["## 5. One-minute measurements (all-bar base rates, not selected strategies)\n",
                                                                 "NOT RUN: no one-minute data\n"]
