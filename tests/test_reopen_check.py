"""audit/tools/reopen_check.py and protected_check.py (mandate 28 Nov 2026, Parts 1.2 and 2), on a hand-made weekend:
Friday bars to the 17:00 New York close, carried quotes while gold is shut, a Sunday 18:00 reopening bar whose first
print is the carried quote, a gap up, COMEX futures with a premium, a forward trade across the weekend and G4 records."""
import json
import os
import shutil
import sys

import numpy as np
import pandas as pd

from quantum import trade_diag as TD
from quantum.data import store

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "audit", "tools"))
import protected_check as PC
import reopen_check as RC

ROOT = os.path.join(os.path.dirname(__file__), "..")
FRI = pd.Timestamp("2026-12-04T20:00:00Z")          # Friday 15:00 New York (EST)
SUN = pd.Timestamp("2026-12-06T23:00:00Z")          # Sunday 18:00 New York: the reopening bar
PREM = 4.0


def _rows(start, n, p0, step, wick=1.0):
    t = pd.date_range(start, periods=n, freq="5min", tz="UTC")
    c = p0 + step * np.arange(1, n + 1)
    o = np.r_[p0, c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + wick, "low": np.minimum(o, c) - wick, "close": c,
                         "volume": 0.0}, index=t)


def _weekend(tmp_path, suspect_low=False, trades=None):
    d = str(tmp_path / "store")
    fri = _rows(FRI, 24, 4000.0, 0.1)                                   # 20:00 -> 21:55 UTC, last close 4002.4
    carry = pd.DataFrame({"open": 4002.4, "high": 4002.5, "low": 4002.3, "close": 4002.4, "volume": 0.0},
                         index=pd.date_range("2026-12-04T22:00Z", SUN - pd.Timedelta(minutes=5), freq="5min", tz="UTC"))
    first = pd.DataFrame({"open": [4002.4], "high": [4046.0], "low": [3990.0 if suspect_low else 4002.4], "close": [4045.0],
                          "volume": [0.0]}, index=[SUN])                # stale open, gap up to 4045
    sun = _rows(SUN + pd.Timedelta(minutes=5), 36, 4045.0, 0.6)         # +$21.6 by 02:00: both races decided
    xau = pd.concat([fri, carry, first, sun])
    store.save(d, "XAU/USD_5m", xau)
    gc = pd.concat([fri, first.assign(open=4045.0), sun]) + 0
    gc[["open", "high", "low", "close"]] += PREM
    store.save(d, "GC=F_5m", gc)
    os.makedirs(os.path.join(d, "holdout"), exist_ok=True)
    with open(os.path.join(d, "holdout", "15m_h4.json"), "w") as f:
        json.dump(trades if trades is not None else [_trade()], f)
    with open(os.path.join(d, "holdout_manifest.json"), "w") as f:
        json.dump({"freeze_key": PC.EXPECTED}, f)
    return d


def _trade(**kw):
    # a long filled at Friday's 21:45 15m close (22:00 UTC = 17:00 New York, the weekly close), exit at the reopening
    t = {"dir": "LONG", "entry_time": "2026-12-04T21:45:00+00:00", "exit_time": "2026-12-06T23:15:00+00:00",
         "entry": 4002.4, "sl": 3992.0, "tp1": 4015.0, "tp2": 4022.0, "exit": 4048.0, "exit_reason": "FLIP",
         "tp1_hit": True, "pts": 30.0, "gross_pts": 30.8, "cost_pts": 0.8, "r": 2.9, "bars": 6, "open": False,
         "freeze_key": PC.EXPECTED, "price_source": "twelvedata:XAU/USD", "recorded_utc": "2026-12-06T23:31:00+00:00"}
    t.update(kw)
    return t


RUN = int(pd.Timestamp("2026-12-07T02:00:00Z").timestamp())


def test_a_clean_reopening_passes(tmp_path):
    d = _weekend(tmp_path)
    assert TD.append(d, t_now=RUN)["appended"] == 1
    out = RC.run(d)
    c = out["checks"]
    assert out["reopen"] == "2026-12-06T23:00:00+00:00" and c["R1"]["verdict"] == "PASS"
    assert c["R2"]["raw_first_print_is_the_carried_quote"] and c["R2"]["engine_first_bar"]["open"] == 4045.0
    assert c["R2"]["first_valid_price"] == 4045.0 and c["R2"]["gap_from_friday_close"] == 42.6
    assert c["R2b"]["verdict"] == "PASS"
    assert c["R3"]["raw_bars_in_shut_window"] > 500 and c["R3"]["engine_bars_in_shut_window"] == 0
    assert c["R5"]["verdict"] == "PASS" and c["R5"]["premium_usd"] == PREM
    assert c["R7"]["post_reopen_fills_at_a_session_close"] == 1
    assert c["R8"]["all"]["agree"] == 1 and c["R9"]["missing"] == 0
    assert out["verdict"] == "PASS"


def test_no_record_after_the_reopening_is_pending(tmp_path):
    d = _weekend(tmp_path)
    assert RC.run(d)["verdict"] == "PENDING"
    assert RC.main(["--store", d]) == 2


def test_a_suspect_low_on_the_reopening_bar_is_flagged_with_its_effect(tmp_path):
    d = _weekend(tmp_path, suspect_low=True)
    TD.append(d, t_now=RUN)
    out = RC.run(d)
    b = out["checks"]["R2b"]
    assert b["verdict"] == "SUSPECT" and b["extreme_opposite_to_the_gap"] == 3990.0
    assert b["g4_records_changed_without_the_extreme"]["records_spanning_the_bar"] == 1
    assert b["g4_records_changed_without_the_extreme"]["changed"][0]["fields"][0] == "race"   # the stop decided it
    assert out["verdict"] == "SUSPECT" and RC.main(["--store", d]) == 3


def test_a_record_that_read_an_unclosed_bar_fails(tmp_path):
    d = _weekend(tmp_path)
    TD.append(d, t_now=RUN)
    f = os.path.join(d, TD.DIR, os.listdir(os.path.join(d, TD.DIR))[0])
    with open(f) as fh:
        r = json.loads(fh.read())
    r["logged_utc"] = "2026-12-06T23:10:00Z"                                   # before its window closed
    with open(f, "w") as fh:
        fh.write(json.dumps(r) + "\n")
    out = RC.run(d)
    assert out["checks"]["R6"]["verdict"] == "FAIL" and out["verdict"] == "FAIL"


def test_duplicates_missing_and_conflicting_copies_fail(tmp_path):
    d = _weekend(tmp_path, trades=[_trade(), _trade(entry_time="2026-12-04T21:30:00+00:00", entry=4002.0)])
    TD.append(d, t_now=RUN)
    f = os.path.join(d, TD.DIR, os.listdir(os.path.join(d, TD.DIR))[0])
    with open(f) as fh:
        lines = fh.read().splitlines()
    with open(f, "w") as fh:                                                   # drop one record, duplicate the other
        fh.write(lines[0] + "\n" + lines[0] + "\n")
    copy = str(tmp_path / "ledger")
    os.makedirs(copy)
    bad = json.loads(lines[0])
    bad["race"]["usd10"]["hours"] = 9.9
    with open(os.path.join(copy, "x.jsonl"), "w") as fh:
        fh.write(json.dumps(bad) + "\n")
    r9 = RC.run(d, diag2=copy)["checks"]["R9"]
    assert r9["verdict"] == "FAIL" and r9["duplicates"] == 1 and r9["missing"] == 1 and r9["conflicting_copies"] == 2


def test_protected_state_passes_here_and_fails_on_a_changed_pine_file(tmp_path):
    out = PC.check()
    assert out["verdict"] == "PASS", out
    assert out["checks"]["freeze_key"]["found"] == "1f88aad357497da4:4440d52587f5cc6b"
    assert len(out["checks"]["pine_manifest"]["sha256"]) == 7 and len(out["checks"]["pine_prereg"]["files"]) == 4
    root = tmp_path / "repo"
    for sub in ("artefacts", "audit"):
        shutil.copytree(os.path.join(ROOT, sub), root / sub, ignore=shutil.ignore_patterns("__pycache__", "tools"))
    with open(root / "artefacts" / "XAUUSD_Quantum_5_0_Master.pine", "a") as f:
        f.write("// changed\n")
    bad = PC.check(str(root))
    assert bad["verdict"] == "FAIL" and bad["checks"]["pine_manifest"]["mismatch"] == ["XAUUSD_Quantum_5_0_Master.pine"]
    assert not bad["checks"]["pine_prereg"]["ok"]


def test_the_reopening_document_is_what_the_evidence_gives():
    assert RC.main(["--doc", "--check"]) == 0
