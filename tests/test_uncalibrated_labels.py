"""IA-02 (audit 2026-11-14): the engine's p is not calibrated (43 unique live trades: p 62.5% on average, 34.9% won,
exact p 0.00017; Brier worse than the no-edge geometry). The page must not present it, or numbers derived from it, as a
probability. Source-level checks on the templates that render them (the browser check in the PR shows the result)."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src():
    with open(os.path.join(ROOT, "site", "app.js"), encoding="utf-8") as f:
        return f.read()


def test_the_brief_tile_shows_reach_scores_not_percent_odds():
    s = _src()
    assert "More likely next" not in s
    tile = s[s.index("Where it is heading · "):s.index("// 3 last liquidity sweep")]
    assert "Reach scores (0–100, not probabilities)" in tile and "NOT CALIBRATED" in tile
    assert not re.search(r"\(\$\{f\(rs\.PD[LH], 0\)\}%\)", tile)          # no "(58%)" next to a level


def test_touch_rates_and_the_probability_card_say_not_calibrated():
    s = _src()
    touch = s[s.index("const touch = isNum(p.p_tp1)"):].split("\n", 1)[0]
    assert "NOT CALIBRATED" in touch
    pst = s[s.index('$("#p-state").textContent'):].split("\n", 1)[0]
    assert pst.startswith('$("#p-state").textContent = "NOT CALIBRATED · "')
    assert '$("#p-state").className = "pill warn uncal";' in s


def test_the_confirmation_panel_calls_its_figures_historical_rates():
    s = _src()
    assert "Target-before-stop probability" not in s and "the chance that decides profit" not in s
    assert "<b>Target-before-stop historical rate</b>" in s and "not a calibrated probability" in s
