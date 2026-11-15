"""IA-07 (audit 2026-11-14): a trading alert must not say "NO TRADE" on top and give an unconditional order below it.
Every line that maps the plan to an MT5 order ("at market") is phrased as a condition, and the disclaimer stays first."""
import pytest

from quantum import notify as N
from tests.test_alert_sixty import T, _pay, _sig

COND = "ON MT5, ONLY IF YOU TAKE IT ANYWAY (not a validated signal): "


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("PLAN", "PLAN_LOT", "PLAN_SL_USD", "PLAN_TP_USD", "PLAN_COST_PER_LOT", "PLAN_TP2_USD"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ALERT_MODE", "all")


@pytest.mark.parametrize("tp2", ["", "0"])
@pytest.mark.parametrize("d", [1, -1])
def test_the_order_mapping_is_conditional(monkeypatch, tp2, d):
    monkeypatch.setenv("PLAN_TP2_USD", tp2)
    line = N.mt5_line(d, N.plan_cfg())
    assert line.startswith(COND + ("BUY" if d == 1 else "SELL")) and "at market" in line


def test_no_unconditional_market_order_on_the_phone(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(N, "send", lambda lines: sent.append(list(lines)) or ["test"] if lines else [])
    store = str(tmp_path)
    N.run(store, {"15m": _pay("15m", T - 900)}, ["15m"], sent_t=T)
    N.run(store, {"15m": _pay("15m", T + 2700, [_sig(T + 2700, 3906.34, -1)])}, ["15m"], sent_t=T + 3600 + 300)
    msgs = [m for m in sent if any("at market" in x for x in m)]
    assert msgs, "the signal alert was not sent"
    for m in msgs:
        assert tuple(m[:len(N.TRADE_DISCLAIMER)]) == N.TRADE_DISCLAIMER          # NO TRADE stays on top
        for x in m:
            if "at market" in x:
                assert x.startswith(COND) or (" | " + COND) in x, x


def test_the_grab_test_trade_line_is_conditional_too():
    tr = {"tf": "15m", "t": T, "dir": 1, "pools": ["PDL"], "levels": [3990.0], "entry": 4000.0, "tp": 4013.0, "sl": 3987.0, "id": 1}
    out = N.grab_lines_new(tr, None)
    assert any((" | " + COND + "BUY at market") in x for x in out)
