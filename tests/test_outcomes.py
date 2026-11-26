"""GA-03: the durable, append-only outcome log (quantum/outcomes.py). Synthetic records shaped as the monitors write them."""
import copy
import hashlib
import json
import os
import shutil

from quantum import outcomes


def _sha_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _read_json_lines(p):
    with open(p) as f:
        return [json.loads(x) for x in f]


def _state():
    return {"brk": {
        "sw": {
            "SWP:1:HI": {"id": "SWP:1:HI", "t": 1, "t_close": 901, "ref_tf": "15m", "side": "HI", "dir": -1, "close": 100.0,
                         "wick": 101.0, "stages": {"SWEEP": {"t": 901}, "FAILED": {"t": 1801}}, "phone": {}, "res": {}, "done": True},
            "SWP:2:LO": {"id": "SWP:2:LO", "t": 2, "t_close": 1801, "ref_tf": "4h", "side": "LO", "dir": 1, "close": 90.0,
                         "wick": 89.0, "stages": {"SWEEP": {"t": 1801}}, "phone": {}, "res": {}},
        },
        "events": {
            "BRK:M15:1:UP": {"id": "BRK:M15:1:UP", "tf": "15m", "t": 1, "t_close": 901, "dir": 1,
                             "stages": {"DETECTED": {"t": 901}, "CONFIRMED": {"t": 1801}, "CLOSED": {"t": 9001}},
                             "phone": {}, "shadow": {"E1": {"done": True}}},
            "BRK:H1:2:DN": {"id": "BRK:H1:2:DN", "tf": "1h", "t": 2, "t_close": 3602, "dir": -1,
                            "stages": {"DETECTED": {"t": 3602}, "CONFIRMED": {"t": 7202}, "FAILED": {"t": 9002}},
                            "phone": {}, "shadow": {"E1": {"done": False}}},
        }}}


def _store(tmp_path, state):
    d = tmp_path / "store"
    d.mkdir(exist_ok=True)
    (d / "alerts_state.json").write_text(json.dumps(state))
    return str(d)


def _lines(d):
    return outcomes.read_dir(d)


def test_every_record_is_logged_once_with_its_finality(tmp_path):
    st = _store(tmp_path, _state())
    assert outcomes.append(st, 1_800_000_000)["appended"] == 4
    rows = {r["rid"]: r for r in _lines(os.path.join(st, "outcomes"))}
    assert rows["sweep|SWP:1:HI"]["final"] and rows["sweep|SWP:1:HI"]["reason"] == "FAILED"
    assert not rows["sweep|SWP:2:LO"]["final"]
    assert rows["breakout|BRK:M15:1:UP"]["final"] and rows["breakout|BRK:M15:1:UP"]["reason"] == "CLOSED"
    assert not rows["breakout|BRK:H1:2:DN"]["final"]          # a shadow race is still running: it can gain a MOVE stage
    assert rows["sweep|SWP:2:LO"]["tf"] == "4h" and rows["breakout|BRK:H1:2:DN"]["tf"] == "1h"
    for r in rows.values():
        assert r["sha256"] == outcomes.sha(r["record"])
        assert set(r["versions"]) == {"sweeps", "sweeps_py", "breakouts", "breakouts_py", "git"}
    assert outcomes.append(st, 1_800_000_900)["appended"] == 0      # nothing changed, nothing written


def test_a_changed_record_gets_a_new_line_and_the_old_one_stays(tmp_path):
    s = _state()
    st = _store(tmp_path, s)
    outcomes.append(st, 1_800_000_000)
    s["brk"]["sw"]["SWP:2:LO"]["stages"]["MOVE10"] = {"t": 2701}
    s["brk"]["sw"]["SWP:2:LO"]["done"] = True
    _store(tmp_path, s)
    assert outcomes.append(st, 1_800_000_900)["appended"] == 1
    v = [r for r in _lines(os.path.join(st, "outcomes")) if r["rid"] == "sweep|SWP:2:LO"]
    assert [r["final"] for r in v] == [False, True]
    assert v[1]["first_seen_utc"] == v[0]["first_seen_utc"]


def test_the_state_file_is_only_read(tmp_path):
    st = _store(tmp_path, _state())
    before = _sha_file(os.path.join(st, "alerts_state.json"))
    outcomes.append(st, 1_800_000_000)
    assert _sha_file(os.path.join(st, "alerts_state.json")) == before


def test_pruned_records_stay_in_the_ledger_and_a_lost_store_removes_nothing(tmp_path):
    s = _state()
    st = _store(tmp_path, s)
    led = str(tmp_path / "ledger" / "outcomes")
    outcomes.append(st, 1_800_000_000)
    outcomes.merge_ledger(os.path.join(st, "outcomes"), led)
    pruned = copy.deepcopy(s)
    del pruned["brk"]["sw"]["SWP:1:HI"], pruned["brk"]["events"]["BRK:M15:1:UP"]     # what KEEP does to old records
    _store(tmp_path, pruned)
    v = outcomes.verify(led, os.path.join(st, "alerts_state.json"))
    assert v["problems"] == [] and v["records"] == 4
    assert v["logged_not_in_state"] == ["breakout|BRK:M15:1:UP", "sweep|SWP:1:HI"]
    shutil.rmtree(os.path.join(st, "outcomes"))                       # the store went back
    outcomes.append(st, 1_800_000_900)
    assert outcomes.merge_ledger(os.path.join(st, "outcomes"), led)["added"] == 0
    assert outcomes.verify(led)["lines"] == 4


def test_verify_finds_tampering_duplicates_conflicts_and_unlogged_versions(tmp_path):
    s = _state()
    st = _store(tmp_path, s)
    outcomes.append(st, 1_800_000_000)
    d = os.path.join(st, "outcomes")
    f = os.path.join(d, os.listdir(d)[0])
    rows = _read_json_lines(f)
    rows[0]["record"]["close"] = 999.0                                # tampered
    rows.append(copy.deepcopy(rows[1]))                               # duplicated
    other = copy.deepcopy(rows[2])                                    # a second, different final version
    assert other["final"]
    other["record"]["stages"]["NOTE"] = {"t": 0}
    other["sha256"] = outcomes.sha(other["record"])
    rows.append(other)
    with open(f, "w") as fh:
        fh.write("".join(outcomes.canonical(r) + "\n" for r in rows))
    s["brk"]["sw"]["SWP:2:LO"]["stages"]["MOVE15"] = {"t": 3601}      # a version the log has not seen
    _store(tmp_path, s)
    p = outcomes.verify(d, os.path.join(st, "alerts_state.json"))["problems"]
    assert any("checksum mismatch" in x for x in p)
    assert any("duplicate of" in x for x in p)
    assert any("different final versions" in x for x in p)
    assert any("SWP:2:LO: current version not in the log" in x for x in p)
    assert outcomes.main(["--verify", d]) == 1


def test_a_missing_state_writes_nothing(tmp_path):
    d = tmp_path / "store"
    d.mkdir()
    assert outcomes.append(str(d)) == {"state": "missing", "appended": 0}
    assert not (d / "outcomes").exists()


def test_the_workflow_appends_before_the_store_save_and_merges_into_the_ledger():
    with open(os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "quantum-site.yml")) as f:
        wf = f.read()
    i_app = wf.index("python -m quantum.outcomes --append store")
    i_store = wf.index("- name: Save the market-data store")
    i_merge = wf.index("python -m quantum.outcomes --merge-ledger store/outcomes ledger/outcomes")
    i_ledger = wf.index("- name: Save the forward ledger")
    assert i_app < i_store < i_ledger < i_merge


def test_the_log_is_outside_the_engine_freeze_key():
    from quantum import holdout
    assert "outcomes.py" not in holdout.ENGINE_SOURCES
