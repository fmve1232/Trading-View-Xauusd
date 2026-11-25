"""B31b-W13: hand-worked checks of the re-costing, drawdown, the registered rule and the W12 path statistics."""
import numpy as np
import pytest

from quantum.research import w13precision as P


def test_recost_keeps_the_gross_move():
    # D 10, old cost 0.97: a +$10 win was (10 - 0.97) / 10.97; at cost 0.77 it is (10 - 0.77) / 10.77
    r_old = (10 - 0.97) / 10.97
    assert P.recost(r_old, 10.0, 0.97, 0.77) == pytest.approx((10 - 0.77) / 10.77)
    assert P.recost(-1.0, 10.0, 0.97, 0.77) == pytest.approx(-1.0)          # a stop stays exactly 1 R
    assert np.isnan(P.recost(0.5, 0.0, 0.97, 0.77))


def test_max_drawdown_in_time_order():
    # in time order: +1, -1, -1, +1 R -> equity 650, 0, -650, 0: the drawdown from the 650 peak is 1,300
    assert P.max_dd(np.array([-1.0, 1.0, 1.0, -1.0]), np.array([3, 1, 4, 2])) == pytest.approx(1300.0)


def test_holm_and_the_registered_rule():
    hp = P.holm({"a": 0.001, "b": 0.02, "c": 0.4})
    assert hp["a"] == pytest.approx(0.003) and hp["b"] == pytest.approx(0.04) and hp["c"] == pytest.approx(0.4)
    good = {"trades": 150, "net_r": 0.1, "net_r_day95": [0.02, 0.2], "folds": [0.1, 0.2, 0.05, 0.1, -0.1, 0.3],
            "years": {"2020": {"net_r": 0.1}, "2021": {"net_r": 0.05}, "2022": {"net_r": 0.2}}}
    assert P.supported(good, 0.01) is True
    assert P.supported(good, 0.06) is False                                  # Holm
    assert P.supported({**good, "trades": 99}, 0.01) is False                # sample
    assert P.supported({**good, "net_r_day95": [-0.01, 0.2]}, 0.01) is False  # lower bound
    assert P.supported({**good, "folds": [0.1, -0.2, 0.05, 0.1, -0.1, 0.3]}, 0.01) is False   # 4 of 6 folds
    assert P.supported({**good, "years": {**good["years"], "2021": {"net_r": -0.01}}}, 0.01) is False


def test_path_stats_stop_then_target():
    # buy at 4000 (s = 1), stop 3995: bar 1 dips to 3994.5 (stop, 0.5 beyond the wick), bar 3 reaches 4010
    fp = {"t": np.array([0, 300, 600, 900]), "o": np.array([4000.0, 3999, 3998, 4004]),
          "h": np.array([4001.0, 3999.5, 4005, 4011]), "l": np.array([3998.0, 3994.5, 3997, 4003]), "c": np.array([3999.0, 3998, 4004, 4010])}
    r = {"entry": 4000.0, "stop": 3995.0, "d": 1, "t0": 0}
    s = P.path_stats(fp, r)
    assert s["min_to_stop"] == pytest.approx(10.0) and s["beyond_wick"] == pytest.approx(0.5)
    assert s["stopped_then_right"] is True and s["mfe24"] == pytest.approx(11.0) and s["mae24"] == pytest.approx(5.5)
    r2 = {"entry": 4000.0, "stop": 3990.0, "d": 1, "t0": 0}
    s2 = P.path_stats(fp, r2)
    assert s2["min_to_stop"] is None and s2["exit10"] == 1200 and s2["mae_to_exit"] == pytest.approx(5.5)   # lowest low 3994.5 before the exit


def test_one_at_a_time():
    rows = [{"t0": 0, "exit10": 100}, {"t0": 50, "exit10": 200}, {"t0": 100, "exit10": 150}, {"t0": 120, "exit10": 300}]
    assert [r["t0"] for r in P.one_at_a_time(rows)] == [0, 100]
