"""IA-04 (audit 2026-11-14): the website showed the engine's levels (structure / ATR stop, liquidity targets) as "Stop" and
"Target", while the phone sends a fixed-dollar plan. The engine's levels are now named "engine" and the phone's plan is
shown beside them. myPlanPx is executed in Node with stubs (behaviour, worked by hand); the rest are template checks."""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src():
    with open(os.path.join(ROOT, "site", "app.js"), encoding="utf-8") as f:
        return f.read()


def _my_plan(cfg, d, entry):
    s = _src()
    fn = s[s.index("function myPlanPx("):s.index("function myPlanHtml(")]
    js = (f"const S = {{ index: {{ alerts: {{ plans: {{ cfg: {json.dumps(cfg)} }} }} }} }}; const isNum = Number.isFinite;\n{fn}\n"
          f"console.log(JSON.stringify(myPlanPx({d}, {entry})));")
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_phone_plan_beside_the_engine_levels_by_hand():
    cfg = {"lot": 0.5, "sl_usd": 650, "tp_usd": 650, "cost_usd": 13, "tp2_usd": 1000}
    buy = _my_plan(cfg, 1, 3879.78)                     # $650 / 50 oz = $13; $1,000 / 50 oz = $20
    assert buy["sl"] == pytest.approx(3866.78) and buy["tp1"] == pytest.approx(3892.78) and buy["tp2"] == pytest.approx(3899.78)
    sell = _my_plan(cfg, -1, 3873.46)
    assert sell["sl"] == pytest.approx(3886.46) and sell["tp1"] == pytest.approx(3860.46) and sell["tp2"] == pytest.approx(3853.46)
    one = _my_plan({**cfg, "tp2_usd": 0}, 1, 4000.0)
    assert one["tp2"] is None and one["tp1"] == pytest.approx(4013.0)
    assert _my_plan({**cfg, "lot": 0}, 1, 4000.0) is None


def test_engine_levels_are_named_and_the_phone_plan_is_shown_with_them():
    s = _src()
    pb = s[s.index("function pbLine("):s.index("function renderBrief(")]
    assert "<i>Engine stop</i>" in pb and "<i>Engine target 1 · " in pb and "<i>Engine target 2 · " in pb
    assert "<i>Stop</i>" not in pb and 'myPlanHtml(x.dir, x.trigger, "Your plan if it fires (what the phone sends):")' in pb
    assert '<div class="k">Engine stop · ${esc(p.sl_basis)}</div>' in s and '<div class="k">Engine TP1 · ' in s
    assert 'myPlanHtml(p.long ? 1 : -1, p.entry, "Your plan (what the phone sends):")' in s
    assert "the engine's EV check is computed on the engine levels, not on your plan" in s
