"""Registration B4-RN-V1: the file and the runner agree, the runner refuses a changed rule, and the sealed data stays
sealed until the operator approves. No test here reads validation or holdout data."""
import json

import pandas as pd
import pytest

from quantum.research import harness as H
from quantum.research import validate_rn as V

_DF = pd.DataFrame({"close": [1.0, 2.0]}, index=pd.DatetimeIndex(["2023-06-01", "2025-01-02"], tz="UTC"))


def test_registration_matches_the_coded_rule():
    reg = V.registration()
    assert reg["partitions"] == ["validation"] and reg["one_time"] is True
    assert reg["rule"]["take_profit_usd_at_4000"] == V.PRIMARY["tp"] == 15.0 and reg["rule"]["stop_loss_usd_at_4000"] == 10.0
    assert set(reg["primary_test"]) == {"P1", "P2", "pass"} and V.Z_CRIT == 1.645


def test_runner_refuses_a_changed_registration(tmp_path, monkeypatch):
    reg = V.registration()
    reg["rule"]["take_profit_usd_at_4000"] = 20.0
    (tmp_path / f"{V.REG_ID}.json").write_text(json.dumps(reg))
    monkeypatch.setattr(H, "REG_DIR", str(tmp_path))
    with pytest.raises(RuntimeError):
        V.registration()


def test_validation_stays_sealed_until_the_operator_approves():
    reg = V.registration()
    if not reg["approved_by_operator"]:
        with pytest.raises(H.SealedPartition):
            H.partition(_DF, "validation", V.REG_ID)
    with pytest.raises(H.SealedPartition):              # never the holdout under this registration
        H.partition(_DF, "holdout", V.REG_ID)


def test_the_registration_has_been_run_once_and_cannot_run_again(tmp_path):
    assert V.already_run("research/trials.jsonl")            # 2026-11-01: run once, verdict FAIL
    with pytest.raises(RuntimeError):
        V.run(str(tmp_path), str(tmp_path / "out.json"), "research/trials.jsonl")
    assert not V.already_run(str(tmp_path / "none.jsonl"))
