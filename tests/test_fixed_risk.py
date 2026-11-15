"""IA-13 (audit 2026-11-14): the dashboard sized positions with half-Kelly on the engine's own rolling win rate, which is
not validated (43 live trades: p 62.5% on average, 34.9% won). Size is now a fixed risk % of the account (the viewer's
choice, default the config's risk_percent, at most 5%); Kelly is shown for reference only. The sizing functions run in
Node with stubs (behaviour, worked by hand); the rest are template checks."""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src():
    with open(os.path.join(ROOT, "site", "app.js"), encoding="utf-8") as f:
        return f.read()


def _run(state, expr):
    s = _src()
    fns = s[s.index("const RISK_MAX = 5;"):s.index("function renderBrief(")]
    js = f"const S = {json.dumps(state)}; const isNum = Number.isFinite;\n{fns}\nconsole.log(JSON.stringify({expr}));"
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_fixed_risk_sizing_by_hand():
    cfg = {"data": {"meta": {"config": {"risk_percent": 1.0}}}}
    per_lot = (13 + 0.97) * 100                                   # stop $13 + cost $0.97 per oz, 100 oz = $1,397 per lot
    assert _run({**cfg, "riskPct": None}, "riskPctFixed()") == 1.0
    assert _run({**cfg, "riskPct": None}, f"fixedLots(25000, {per_lot})") == pytest.approx(0.17)   # 250 / 1397 = 0.179
    assert _run({**cfg, "riskPct": 0.5}, f"fixedLots(25000, {per_lot})") == pytest.approx(0.08)    # 125 / 1397 = 0.089
    assert _run({**cfg, "riskPct": 7}, "riskPctFixed()") == 1.0        # above the 5% cap: back to the default
    assert _run({**cfg, "riskPct": 0}, "riskPctFixed()") == 1.0
    assert _run({"riskPct": None}, "riskPctFixed()") == 1.0             # no payload yet
    assert _run({**cfg, "riskPct": None}, "fixedLots(25000, 0)") == 0


def test_kelly_never_sizes_a_trade():
    s = _src()
    lots = s[s.index("  const lots = sig && p.dist > 0 ? "):].split("\n", 1)[0]
    assert "fixedLots(acct, perLot)" in lots and "kelly" not in lots
    assert s.count("kelly_pct") == 1                                     # only the reference row reads it
    row = s[s.index('["Kelly (half, Wilson LB)"'):].split("\n", 1)[0]
    assert "not used for sizing: the win rate it needs is not validated" in row
    assert '["Risk per trade (fixed)", `<input id="riskpct"' in s and 'store.set("risk_pct", S.riskPct)' in s
    assert "risk ${f(riskPctFixed(), 2)}% of the account (fixed)" in s and "risk ${f(riskPctFixed(), 2)}% fixed" in s
