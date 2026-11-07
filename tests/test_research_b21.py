"""B21 (research/registrations/B21.json): the alert conversion, the "at any time" measure and the validation gate."""
import numpy as np
import pandas as pd
import pytest

from quantum.research import b21


def _m15(closes, start="2026-03-02 00:00"):
    idx = pd.date_range(start, periods=len(closes), freq="15min", tz="UTC")
    c = np.asarray(closes, float)
    o = np.concatenate([[c[0]], c[:-1]])
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.5, "low": np.minimum(o, c) - 0.5, "close": c, "volume": 0.0}, index=idx)


def test_alerts_keep_their_own_direction_and_close():
    idx = pd.date_range("2026-03-02 00:00", periods=5, freq="15min", tz="UTC")
    c = np.array([4000.0, 4001.0, 4002.0, 4003.0, 4004.0])
    tr = b21.to_triggers([1, 3], [-1, 1], idx, c, "SWEEP")
    assert [(x["dir"], x["p0"], x["t_close"]) for x in tr] == [(-1, 4001.0, int(idx[1].timestamp()) + 900),
                                                                 (1, 4003.0, int(idx[3].timestamp()) + 900)]


def test_reached_at_any_time_ignores_the_stop_and_needs_a_full_day():
    closes = [4000.0] * 4 + [3980.0] * 10 + [4016.0] + [4000.0] * 120      # -20 first, then +16: reached, despite the dip
    m = _m15(closes)
    t0 = int(m.index[3].timestamp()) + 900
    r = b21.reached_any(m, np.array([t0, t0]), np.array([4000.0, 4000.0]), np.array([1, -1]), 15.0)
    assert r[0] == 1.0 and r[1] == 1.0                          # BUY: +16.5 high; SELL: the -20 dip is +20 for a SELL
    r = b21.reached_any(m, np.array([t0]), np.array([4000.0]), np.array([1]), 20.0)
    assert r[0] == 0.0                                           # +20 never reached in the day
    late = int(m.index[-5].timestamp()) + 900
    assert np.isnan(b21.reached_any(m, np.array([late]), np.array([4000.0]), np.array([1]), 15.0)[0])   # incomplete window


def test_validation_opens_only_for_hypotheses_that_passed(tmp_path):
    with pytest.raises(SystemExit, match="passed development"):
        b21.main(["--rd", str(tmp_path), "--part", "validation", "--out", str(tmp_path / "o.json")])


def test_the_any_time_rate_counts_entries_that_never_reach_the_target():
    closes = [4000.0] * 4 + [4016.0] + [4000.0] * 200
    m = _m15(closes)
    t = np.array([int(m.index[3].timestamp()) + 900, int(m.index[10].timestamp()) + 900])
    r = b21.reached_any(m, t, np.array([4000.0, 4000.0]), np.array([1, 1]), 15.0)
    assert r.tolist() == [1.0, 0.0] and np.nanmean(r) == 0.5          # not 1.0: the miss stays in the denominator
