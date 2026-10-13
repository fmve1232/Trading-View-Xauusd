"""The decision card's two-sided gates (report.gate_sides, display only) equal the engine's own log for the side it logged."""
import copy

from quantum import engine, report
from quantum.config import DEFAULT
from quantum.data.market import load_synthetic


def test_rebuilt_gates_match_the_engine_log():
    m = load_synthetic("15m", bars=1400, seed=2)
    checked = 0
    for cut in (950, 1100, 1250, 1400):
        mc = copy.copy(m)
        mc.base = m.base.iloc[:cut]
        res = engine.run(mc, DEFAULT)
        L, F = res.last, res.F
        g = report.gate_sides(L, F, F["n"] - 1)
        if str(L["decision_log"]).startswith("RANGE"):
            assert g is None
            continue
        assert g is not None, L["decision_log"]                      # rebuilt side == logged side
        assert set(g) == {"long", "short", "logged"} and g["logged"] in ("long", "short")
        checked += 1
    assert checked >= 1


def test_unverifiable_log_gives_none():
    assert report.gate_sides({"decision_log": "RANGE 80/130 [no dir. edge]"}, {}, 0) is None
