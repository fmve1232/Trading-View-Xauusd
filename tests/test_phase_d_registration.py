"""Phase D's registration and code agree, and the registration is on the hash-chained log: any change to
research/registrations/PHASE_D.json must be logged as an amendment (the latest registration / amendment record carries
the file's current SHA-256), and the registered constants are the ones the code uses."""
import hashlib
import json
import os

from quantum.research import d_dukascopy as DD
from quantum.research import d_features as DF
from quantum.research import d_log as LOG
from quantum.research import d_run as R
from quantum.research import d_study as S
from quantum.research import harness as H

ROOT = os.path.join(os.path.dirname(__file__), "..")
REG = os.path.join(ROOT, "research", "registrations", "PHASE_D.json")
LOGF = os.path.join(ROOT, "research", "phase_d_trials.jsonl")


def _reg():
    with open(REG) as fh:
        return json.load(fh)


def test_registration_is_logged_and_unchanged_since():
    ok, why = LOG.verify(LOGF)
    assert ok, why
    with open(LOGF) as fh:
        recs = [json.loads(x) for x in fh]
    assert recs[0]["kind"] == "registration" and recs[0]["id"] == "PHASE_D" and recs[0]["before_any_data"] is True
    latest = [r for r in recs if r["kind"] in ("registration", "amendment")][-1]
    with open(REG, "rb") as fh:
        assert latest["sha256"] == hashlib.sha256(fh.read()).hexdigest(), "PHASE_D.json changed without a logged amendment"


def test_partitions_and_seal():
    r = _reg()
    assert r["partitions"] == ["development", "unsealed 2026"] and r["approved_by_operator"] is False
    assert DD.SEALED == (H.VAL[0], H.HOLD[1]) and DD.PERIODS["development"] == H.DEV


def test_registered_constants_are_the_code_constants():
    r = _reg()
    fams = r["features"]["order_flow"]["families"]
    reg_cols = [c for k, v in fams.items() for c in v]
    assert reg_cols == list(DF.OF_COLUMNS) and len([k for k in fams if k[0].isdigit()]) == 10
    assert [n for n, _ in S.RULES] == ["EV0", "Q10", "Q05", "Q02"] and S.SETS == ("BASELINE", "A", "B", "C", "D")
    assert S.ALGOS == ("LR", "RF", "LGBM", "GB") and S.BH_Q == 0.10 and S.RC_P == 0.05 and S.HOLM_P == 0.05
    assert (S.C5_MIN, S.C5_PREFERRED, S.C6_DD_R, S.C6_TRADES, S.C6_P, S.C6_BLOCK) == (300, 500, 15.0, 250, 0.05, 10)
    assert S.WF_START == "2021-01-01" and S.MIN_STRATA == 30 and S.FAV_X == (5.0, 10.0, 15.0, 20.0) and S.FAV_BARS == 16
    assert R.DYNAMIC == ((1.0, 1.0), (1.5, 1.0), (1.0, 1.5)) and R.MIN_OF_COVERAGE == 0.90
    assert len(R.GRID) == 16 and R.STOP_X == (3, 5, 7, 10) and R.STOP_WINDOW_S == 3600
    assert (R.ENG_SI, R.ENG_SO, R.ENG_CM) == (0.20, 0.20, 0.07)
    assert set(r["acceptance"]) >= {"C1", "C2", "C3", "C4", "C5", "C6", "qualifies"}
