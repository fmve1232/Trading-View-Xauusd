"""B23 (research/registrations/B23.json): the frozen threshold and the holdout gate."""
import json

import numpy as np
import pytest

from quantum.research import b23


def test_thresholds_are_quantiles_of_the_development_slice_only():
    p_cal = np.linspace(0, 1, 1001)
    thr = b23.thresholds(p_cal)
    assert thr[0.005] == pytest.approx(0.995) and thr[0.001] == pytest.approx(0.999) and thr[0.01] == pytest.approx(0.99)


def test_the_holdout_needs_a_recorded_validation_pass(tmp_path):
    with pytest.raises(SystemExit, match="validation pass"):
        b23.main(["--rd", str(tmp_path), "--part", "holdout", "--out", str(tmp_path / "o.json")])
    vr = tmp_path / "val.json"
    vr.write_text(json.dumps({"pass": False}))
    with pytest.raises(SystemExit, match="validation pass"):
        b23.main(["--rd", str(tmp_path), "--part", "holdout", "--out", str(tmp_path / "o.json"), "--val-results", str(vr)])
