"""Amendment 14 (approved 2026-11-01): a stop or target that a bar OPENS beyond fills at the open.

Tests 1-22 of the amendment's section 7, written before the engine change. Hand-worked bars; cost per trade is
spread 0.30 + 2 x 0.20 slippage + $7 / 100 oz = 0.77 points, charged once.
"""
import gzip
import json
import math
import os
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from quantum import backtest, engine, holdout
from quantum.config import DEFAULT
from quantum.data import sources
from quantum.data.market import load_synthetic

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "audit", "tools"))
import gapsim  # noqa: E402  (the reviewed reference implementation: "current" = web.6, "both" = Amendment 14)

COST = 0.30 + 0.40 + 0.07


def _res(bars, buy=(), sell=(), sl=95.0, tp1=105.0, tp2=110.0, start="2026-10-05 10:00"):
    """bars: list of (o, h, l, c). Signals at the listed bar indices; plan levels constant."""
    n = len(bars)
    o, h, l, c = (np.array(x, float) for x in zip(*bars))
    idx = pd.date_range(start, periods=n, freq="15min", tz="UTC")
    eb, es = np.zeros(n), np.zeros(n)
    eb[list(buy)] = 1
    es[list(sell)] = 1
    F = {"o": o, "h": h, "l": l, "c": c, "index": idx, "sess_spread": np.full(n, 0.30),
         "session_label": np.array(["NY"] * n), "mkt_regime": np.array(["RANGE"] * n)}
    R = {"exec_buy": eb, "exec_sell": es, "plan_sl": np.full(n, sl), "plan_tp1": np.full(n, tp1), "plan_tp2": np.full(n, tp2),
         "tq": np.full(n, 60), "cal_p_long": np.full(n, 0.6), "cal_p_short": np.full(n, 0.4), "plan_ev": np.full(n, 0.1)}
    return SimpleNamespace(F=F, rows=R)


def _one(bars, **kw):
    t = backtest.simulate(_res(bars, **kw), DEFAULT)
    assert len(t) >= 1
    return t[0]


E = (100, 100, 100, 100)          # entry bar: close 100


# ---------------- unit tests (1-10) ----------------
def test_01_long_gap_through_stop_fills_at_open():
    t = _one([E, (93, 94, 92, 93)], buy=[0])
    assert t["exit_reason"] == "SL_GAP" and t["exit"] == 93.0 and t["exit_i"] == 1
    assert t["r"] == pytest.approx((93 - 100 - COST) / 5.0, abs=1e-4)
    assert t["r"] < -1 and t["r"] - (-1 - COST / 5) == pytest.approx(-(95 - 93) / 5.0, abs=1e-4)


def test_02_short_gap_through_stop_fills_at_open():
    t = _one([E, (107, 108, 106, 107)], sell=[0], sl=105, tp1=95, tp2=90)
    assert t["exit_reason"] == "SL_GAP" and t["exit"] == 107.0
    assert t["r"] == pytest.approx((100 - 107 - COST) / 5.0, abs=1e-4)


def test_03_open_inside_then_through_stop_is_unchanged():
    t = _one([E, (97, 98, 94, 96)], buy=[0])
    assert t["exit_reason"] == "SL" and t["exit"] == 95.0


def test_04_long_open_beyond_tp2_fills_everything_at_open():
    t = _one([E, (111, 112, 110.5, 111)], buy=[0])
    assert t["exit_reason"] == "TP2" and t["tp1_hit"] and t["exit"] == 111.0
    assert t["gross_pts"] == pytest.approx(11.0)


def test_05_open_between_tp1_and_tp2_takes_half_then_bar_continues():
    t = _one([E, (106, 111, 104, 109)], buy=[0])                       # half at 106, rest at TP2 110 in the same bar
    assert t["exit_reason"] == "TP2" and t["gross_pts"] == pytest.approx(0.5 * 6 + 0.5 * 10)
    t = _one([E, (106, 106.5, 94, 95)], buy=[0])                       # half at 106, then the original stop in the same bar
    assert t["exit_reason"] == "SL" and t["exit"] == 95.0 and t["tp1_hit"]
    assert t["gross_pts"] == pytest.approx(0.5 * 6 + 0.5 * -5)
    t = _one([E, (106, 106.5, 104, 105), (101, 102, 99, 100)], buy=[0])  # breakeven live from the next bar
    assert t["exit_reason"] == "BE" and t["exit"] == 100.0 and t["gross_pts"] == pytest.approx(3.0)


def test_06_breakeven_stop_gapped_through_fills_at_open():
    t = _one([E, (104, 106, 103, 105), (98, 99, 97, 98)], buy=[0])     # TP1 intrabar on bar 1; BE stop 100 from bar 2
    assert t["exit_reason"] == "BE_GAP" and t["exit"] == 98.0
    assert t["gross_pts"] == pytest.approx(0.5 * 5 + 0.5 * -2)


def test_07_short_mirrors_of_4_to_6():
    kw = dict(sell=[0], sl=105, tp1=95, tp2=90)
    t = _one([E, (89, 89.5, 88, 89)], **kw)
    assert t["exit_reason"] == "TP2" and t["gross_pts"] == pytest.approx(11.0)
    t = _one([E, (94, 96, 89, 91)], **kw)
    assert t["exit_reason"] == "TP2" and t["gross_pts"] == pytest.approx(0.5 * 6 + 0.5 * 10)
    t = _one([E, (96, 97, 94, 95), (102, 103, 101, 102)], **kw)
    assert t["exit_reason"] == "BE_GAP" and t["gross_pts"] == pytest.approx(0.5 * 5 + 0.5 * -2)


def test_08_open_exactly_at_the_stop_counts_as_a_gap_at_the_same_price():
    t = _one([E, (95, 96, 94, 95.5)], buy=[0])
    assert t["exit_reason"] == "SL_GAP" and t["exit"] == 95.0


def test_08b_short_open_exactly_at_the_stop_counts_as_a_gap():
    """Added by the 2026-11-01 verification: mutation M08 (short boundary '>' instead of '>=') survived without it."""
    t = _one([E, (105, 106, 104, 105.5)], sell=[0], sl=105, tp1=95, tp2=90)
    assert t["exit_reason"] == "SL_GAP" and t["exit"] == 105.0


def test_09_nan_open_falls_back_to_the_existing_rule():
    t = _one([E, (math.nan, 96, 94, 95.5)], buy=[0])
    assert t["exit_reason"] == "SL" and t["exit"] == 95.0


def test_10_cost_is_charged_once_and_is_unchanged_by_a_gap():
    a = _one([E, (93, 94, 92, 93)], buy=[0])
    b = _one([E, (97, 98, 94, 96)], buy=[0])
    assert a["cost_pts"] == b["cost_pts"] == pytest.approx(COST)
    assert a["pts"] == pytest.approx(a["gross_pts"] - COST)


# ---------------- integration (11-13) ----------------
@pytest.fixture(scope="module")
def eng():
    """Synthetic engine run, traded with the H4 Playbook rows (many trades; the engine's own BUY / SELL fires rarely)."""
    from quantum import arm_h4
    m = load_synthetic("15m", bars=1500, seed=4)
    res = engine.run(m, DEFAULT)
    ev = arm_h4.evaluate(res)
    rows = {**{k: res.rows[k] for k in ("tq", "cal_p_long", "cal_p_short", "plan_ev")},
            **{k: ev[k] for k in ("exec_buy", "exec_sell", "plan_sl", "plan_tp1", "plan_tp2")}}
    r = SimpleNamespace(F=res.F, rows=rows)
    assert len(backtest.simulate(r, DEFAULT)) > 20
    return r


def _gapped(res, every=37, size=3.0):
    """The synthetic feed opens at the previous close; force gaps so the rule is exercised."""
    F = dict(res.F)
    o, h, l = F["o"].copy(), F["h"].copy(), F["l"].copy()
    for i in range(every, len(o), every):
        o[i] += size if (i // every) % 2 else -size
        h[i], l[i] = max(h[i], o[i]), min(l[i], o[i])
    F["o"], F["h"], F["l"] = o, h, l
    return SimpleNamespace(F=F, rows=res.rows)


def test_11_gap_exits_are_at_the_open_and_every_exit_is_inside_its_bar(eng):
    r = _gapped(eng)
    tr = backtest.simulate(r, DEFAULT)
    F = r.F
    assert any(t["exit_reason"].endswith("_GAP") for t in tr)
    for t in tr:
        i = t["exit_i"]
        if t["exit_reason"].endswith("_GAP"):
            assert t["exit"] == pytest.approx(round(F["o"][i], 3))
        assert F["l"][i] - 1e-6 <= t["exit"] <= F["h"][i] + 1e-6


def test_12_arms_simulate_through_the_same_function():
    from quantum import arm_h2, arm_h3, arm_h4, arm_h5, arm_h6
    for m in (arm_h2, arm_h3, arm_h4, arm_h5, arm_h6):
        src = open(m.__file__).read()
        assert "backtest.simulate(" in src, m.__name__


def test_13_no_lookahead_trades_closed_before_a_cut_are_identical(eng):
    r = _gapped(eng)
    full = backtest.simulate(r, DEFAULT)
    n = len(r.F["c"])
    for k in (600, 1100):
        cut = SimpleNamespace(F={kk: (v[:k] if hasattr(v, "__len__") and not isinstance(v, (str, dict)) and len(v) == n else v)
                                 for kk, v in r.F.items()}, rows={kk: v[:k] for kk, v in r.rows.items()})
        part = backtest.simulate(cut, DEFAULT)
        a = [(t["entry_i"], t["exit_i"], t["pts"], t["exit_reason"]) for t in full if t["exit_i"] < k - 1]
        b = [(t["entry_i"], t["exit_i"], t["pts"], t["exit_reason"]) for t in part if t["exit_i"] < k - 1]
        assert a == b


# ---------------- regression (14-16) ----------------
def _key(tr):
    return [(t["entry_i"], t["exit_i"], t["pts"]) for t in tr]


def test_14_without_gaps_the_trades_equal_web6(eng):
    """On a feed with no price gaps (each bar opens at the previous close) web.7 equals web.6, except one case the
    approved rule covers: after TP1 the bar CLOSED beyond entry, so the breakeven stop is already crossed when it goes
    live and fills at the next open (BE_GAP), as a broker would close at market. Every difference must be that case."""
    F = eng.F
    assert np.nanmax(np.abs(F["o"][1:] - F["c"][:-1])) == 0.0
    new = backtest.simulate(eng, DEFAULT)
    assert _key(new) == _key(gapsim.simulate(eng, DEFAULT, "both"))         # the reviewed rule, exactly
    old = {t["entry_i"]: t for t in gapsim.simulate(eng, DEFAULT, "current")}
    diff = [t for t in new if (t["entry_i"], t["exit_i"], t["pts"]) != (old[t["entry_i"]]["entry_i"], old[t["entry_i"]]["exit_i"], old[t["entry_i"]]["pts"])]
    assert len(diff) < len(new) / 10
    for t in diff:
        i = t["exit_i"]
        assert t["exit_reason"] == "BE_GAP" and t["tp1_hit"] and t["exit"] == pytest.approx(round(F["o"][i], 3))
        assert (F["c"][i - 1] < t["entry"]) if t["dir"] == "LONG" else (F["c"][i - 1] > t["entry"])
    r = _gapped(eng)                                       # and with gaps they equal the reviewed rule ("both")
    assert _key(backtest.simulate(r, DEFAULT)) == _key(gapsim.simulate(r, DEFAULT, "both"))
    assert _key(backtest.simulate(r, DEFAULT)) != _key(gapsim.simulate(r, DEFAULT, "current"))


def test_15_golden_numbers_on_the_stored_1h_window():
    """Frozen fixture: XAU/USD 1h, 2026-03-02..2026-10-30, H4 Playbook rows (market-data @ 0bb2c8a96).
    Amendment 14 section 6.2: n 729, 13 gap exits, sum R -28.5189 (web.6) and -29.5761 (proposed)."""
    with gzip.open(os.path.join(HERE, "fixtures", "h4_1h_2026-10-30.json.gz"), "rt") as f:
        d = json.load(f)
    n = len(d["c"])
    F = {k: np.array(d[k], float) for k in ("o", "h", "l", "c", "sess_spread")}
    F.update(index=pd.DatetimeIndex(pd.to_datetime(d["t"], unit="s", utc=True)), session_label=np.array(d["session"]),
             mkt_regime=np.array(d["regime"]))
    R = {k: np.array([math.nan if x is None else x for x in d[k]], float) for k in ("exec_buy", "exec_sell", "plan_sl", "plan_tp1", "plan_tp2")}
    R.update(tq=np.zeros(n), cal_p_long=np.full(n, math.nan), cal_p_short=np.full(n, math.nan), plan_ev=np.full(n, math.nan))
    r = SimpleNamespace(F=F, rows=R)
    new = [t for t in backtest.simulate(r, DEFAULT) if not t.get("open")]
    old = [t for t in gapsim.simulate(r, DEFAULT, "current") if not t.get("open")]
    assert len(new) == len(old) == 729
    assert sum(t["exit_reason"].endswith("_GAP") for t in new) == 13
    assert sum(t["r"] for t in old) == pytest.approx(-28.5189, abs=1e-3)
    assert sum(t["r"] for t in new) == pytest.approx(-29.5761, abs=1e-3)


def test_16_new_engine_hash_restarts_and_archives_never_deletes(tmp_path):
    from datetime import datetime, timezone
    key = holdout.freeze_key(DEFAULT)
    old = "5e4630924d663fc5:6f3964ad97813cc9"                   # web.6
    assert key != old
    t0 = datetime(2026, 10, 17, 21, 26, 18, tzinfo=timezone.utc)
    man = {"freeze_key": old, "config_hash": old.split(":")[0], "engine_code_hash": old.split(":")[1],
           "engine_version": "Q7.2-web.6", "freeze_utc": t0.isoformat(), "status": "ACTIVE", "history": []}
    (tmp_path / holdout.FILE).write_text(json.dumps(man))
    now = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    m = holdout.load_or_freeze(str(tmp_path), DEFAULT, now)
    assert m["status"] == "RESET" and m["freeze_key"] == key and m["history"][-1]["freeze_key"] == old
    assert m["history"][-1]["ended_utc"] == now.isoformat() and m["engine_version"] != "Q7.2-web.6"
    old_trade = dict(entry_time="2026-10-20T10:00:00+00:00", dir="LONG", r=-1.0, freeze_key=old)
    (tmp_path / "holdout").mkdir()
    (tmp_path / "holdout" / "1h_treatment.json").write_text(json.dumps([old_trade]))
    led = holdout.update_ledger(str(tmp_path), "1h", "treatment", [], m["freeze_utc"], key)
    assert led == []
    arch = json.loads((tmp_path / "holdout" / "archive" / "1h_treatment.json").read_text())
    assert arch == [old_trade]


# ---------------- edge cases (17-22) ----------------
def test_17_gap_later_in_the_trade():
    t = _one([E, (100, 101, 99, 100), (100, 101, 99, 100), (92, 93, 91, 92)], buy=[0])
    assert t["exit_reason"] == "SL_GAP" and t["exit_i"] == 3 and t["exit"] == 92.0


def test_18_gap_on_a_flip_bar_exits_at_the_open_then_the_new_signal_enters_at_the_close():
    tr = backtest.simulate(_res([E, (93, 94, 92, 93), (93, 94, 92, 93)], buy=[0], sell=[1], sl=95, tp1=105, tp2=110), DEFAULT)
    assert tr[0]["exit_reason"] == "SL_GAP" and tr[0]["exit"] == 93.0
    assert tr[1]["dir"] == "SHORT" and tr[1]["entry"] == 93.0 and tr[1]["entry_i"] == 1


def test_19_gap_on_the_last_bar_closes_the_trade():
    tr = backtest.simulate(_res([E, (100, 101, 99, 100), (93, 94, 92, 93)], buy=[0]), DEFAULT)
    assert len(tr) == 1 and tr[0]["exit_reason"] == "SL_GAP" and not tr[0]["open"]


def test_20_sunday_reopen_uses_the_repaired_open_not_the_stale_print():
    # Sunday 2026-10-04 22:00 UTC = 18:00 New York: the reopen bar. Stale print 99 (above the 95 stop), real close 93.
    idx = pd.DatetimeIndex(["2026-10-02 20:45", "2026-10-04 22:00", "2026-10-04 22:15"], tz="UTC")
    df = pd.DataFrame({"open": [100, 99.0, 93], "high": [100, 99.0, 94], "low": [100, 92.5, 92], "close": [100, 93.0, 93]}, index=idx)
    rep = sources.repair_reopen(df, 900)
    assert rep["open"].iloc[1] == 93.0                                   # stale open replaced by the close
    bars = list(zip(rep["open"], rep["high"], rep["low"], rep["close"]))
    r = _res(bars, buy=[0])
    r.F["index"] = idx
    t = backtest.simulate(r, DEFAULT)[0]
    assert t["exit_reason"] == "SL_GAP" and t["exit"] == 93.0 and t["exit_i"] == 1


def test_21_tp1_equal_tp2():
    t = _one([E, (107, 108, 106, 107)], buy=[0], tp1=106, tp2=106)
    assert t["exit_reason"] == "TP2" and t["gross_pts"] == pytest.approx(7.0)
    t = _one([E, (101, 107, 100.5, 106)], buy=[0], tp1=106, tp2=106)
    assert t["exit_reason"] == "TP2" and t["gross_pts"] == pytest.approx(6.0)


def test_22_short_open_exactly_at_the_target():
    t = _one([E, (90, 91, 89, 90)], sell=[0], sl=105, tp1=95, tp2=90)
    assert t["exit_reason"] == "TP2" and t["exit"] == 90.0 and t["gross_pts"] == pytest.approx(10.0)
    t = _one([E, (95, 96, 94, 95)], sell=[0], sl=105, tp1=95, tp2=90)
    assert t["tp1_hit"] and t.get("exit_reason") != "SL_GAP"
