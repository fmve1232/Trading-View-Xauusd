"""The chart terminal's dashboard (site/app.js renderDash / renderPlanStrip, operator 27 Nov 2026): the RECORD verdict
and the ROOM lookup run in Node with stubs and are checked against hand-worked numbers; the rest are template checks
that the honesty labels survived the redesign (IA-02 NOT CALIBRATED, IA-13 fixed risk, IA-04 / IA-07 reference plan)."""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _src():
    with open(os.path.join(ROOT, "site", "app.js"), encoding="utf-8") as f:
        return f.read()


def _run(expr, start="const t975 = ", end="const ROOM_USD = "):
    s = _src()
    js = f"const isNum = Number.isFinite;\n{s[s.index(start):s.index(end)]}\nconsole.log(JSON.stringify({expr}));"
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


@node
def test_the_record_verdict_follows_the_visuals_rule_by_hand():
    # 15m H4 forward record of 26 Nov: 158 trades, mean -0.0854 R, t -1.3567, PF 0.86
    # se = 0.0854 / 1.3567 = 0.06295; t(0.975, 157) = 1.9752; interval -0.2097 .. +0.0389: spans 0
    v = _run('recordVerdict({n: 158, avg_r: -0.0854, t_stat: -1.3567, profit_factor: 0.8605})')
    assert v["txt"] == "NO EDGE SHOWN · interval spans 0" and v["lv"] == 0
    assert v["lo"] == pytest.approx(-0.2097, abs=5e-4) and v["hi"] == pytest.approx(0.0389, abs=5e-4)
    # n 60, mean +0.30, t 3.0: se 0.1, t(0.975, 59) = 2.0010, lo = +0.0999 > 0
    assert _run('recordVerdict({n: 60, avg_r: 0.3, t_stat: 3.0, profit_factor: 1.5})')["txt"] == "EDGE SHOWN"
    assert _run('recordVerdict({n: 60, avg_r: 0.3, t_stat: 3.0, profit_factor: 1.1})')["txt"] == "NO EDGE SHOWN · PF < 1.2"
    assert _run('recordVerdict({n: 60, avg_r: -0.3, t_stat: -3.0, profit_factor: 0.6})')["txt"] == "NO EDGE · interval below 0"
    assert _run('recordVerdict({n: 49, avg_r: 0.5, t_stat: 5, profit_factor: 3})')["txt"] == "UNDECIDED · N < 50"
    assert _run('recordVerdict(null)')["txt"] == "no closed trades yet"
    assert _run("t975(59)") == pytest.approx(2.000995, abs=2e-5) and _run("t975(157)") == pytest.approx(1.975180, abs=2e-5)


@node
def test_room_uses_the_nearest_tagged_level_on_each_side():
    D = {"dashboard": {"liquidity": {"pools": {"PDH": 3606.46, "PDL": 3546.21, "PWH": 3901.18, "PWL": 3503.98, "PMH": 4225.62,
                                               "PML": 3871.19, "EQH": 3679.0}, "cdh": 3684.87, "cdl": 3556.04}}}
    g = _run(f"glNear({json.dumps(D)}, 3678.60)", start="function glNear(")
    # above: today's high; below: yesterday's HIGH, which price has already cleared (either side counts, as in Pine);
    # EQH 3679 is nearer above but is not one of the tagged levels (Visuals f_glNear)
    assert g["up"] == ["CDH", 3684.87] and g["dn"] == ["PDH", 3606.46]


def test_the_dashboard_keeps_the_honesty_labels():
    s = _src()
    dash = s[s.index("function renderDash("):s.index("function updDashPrice(")]
    assert "NOT CALIBRATED" in dash and "score L " in dash and "% S " not in dash       # scores, never "L 52% S 28%"
    assert "kelly_pct" not in dash and "fixedLots(acct, perLotD)" in dash             # IA-13: fixed risk only
    assert "UNTESTED hypothesis (context, never a signal)" in dash
    strip = s[s.index("function renderPlanStrip("):s.index("const DASH_WIDE")]
    assert "reference only · decision ${esc(dec)} · not a signal" in strip and "NOT CALIBRATED" in strip
    assert "analog frequency" in strip


def test_the_terminal_comes_first_on_the_page():
    with open(os.path.join(ROOT, "site", "index.html"), encoding="utf-8") as f:
        html = f.read()
    main = html[html.index("<main>"):]
    assert main.index('id="terminal"') < main.index('id="brief"') < main.index('class="layout"') < main.index('id="tabs"')
    for el in ('id="tvdash"', 'id="chart"', 'id="tvplan"', 'id="subchart"', 'id="toolbar"', 'id="legend"'):
        assert main.index('id="terminal"') < main.index(el) < main.index('id="brief"'), el
