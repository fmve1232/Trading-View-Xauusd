"""index.json must be strict JSON (found 2026-11-07): the validation block's empty "today" / "this week" carried NaN, which
the browser's JSON.parse rejects, so the site lost the whole alerts block on days with nothing decided. notify.run now
returns its report through notify.json_safe (NaN / Infinity -> null); the state file keeps its own values."""
import json
import math

from quantum import notify

T0 = 1793973600                                   # 2026-11-06 14:00 UTC (Friday)


def _p15(bars):
    n = len(bars)
    x = bars[-1][3]
    ch = {"t": [b[0] for b in bars], "o": [b[3] for b in bars], "h": [b[1] for b in bars], "l": [b[2] for b in bars],
          "c": [b[3] for b in bars], "pdh": [4147.6] * n, "pdl": [4058.44] * n, "pwh": [4081.97] * n, "pwl": [3871.19] * n,
          "vpoc": [4059.0] * n, "vah": [4075.0] * n, "val": [4040.0] * n,
          "ob_bull_lo": [None] * n, "ob_bull_hi": [None] * n, "ob_bear_lo": [None] * n, "ob_bear_hi": [None] * n}
    mk = [{"t": bars[-1][0], "type": "SIGNAL", "dir": 1, "px": x, "tq": 60, "sl": x - 13, "tp1": x + 13, "tp2": x + 20, "tp3": x + 30}]
    return {"meta": {"tf": "15m", "synthetic": False, "generated_utc": "2026-11-06T14:40:00+00:00", "price_source": "td"},
            "markers": mk, "decisions": [], "news": None, "chart": ch}


def test_json_safe_replaces_nan_and_infinity_only():
    x = {"a": float("nan"), "b": [1.0, float("inf"), -float("inf")], "c": (2.5, "x", None, 0), "d": {"e": 3}}
    assert notify.json_safe(x) == {"a": None, "b": [1.0, None, None], "c": [2.5, "x", None, 0], "d": {"e": 3}}
    assert math.isnan(x["a"])                                       # the input is not modified


def test_the_alerts_block_is_strict_json_on_a_day_with_nothing_decided(tmp_path, monkeypatch):
    monkeypatch.setattr(notify, "send", lambda lines: ["test"])
    b = [(T0, 4066.0, 4061.0, 4062.0)]
    notify.run(str(tmp_path), {"15m": _p15(b)}, ["15m"], sent_t=T0 + 1000)
    rep = notify.run(str(tmp_path), {"15m": _p15(b + [(T0 + 900, 4063.0, 4055.22, 4060.10)])}, ["15m"], sent_t=T0 + 1900)
    today = rep["plans"]["validation"]["today"]
    assert today["n"] == 0 and today["rate"] is None and today["wilson"] == [None, None]
    json.dumps(rep, allow_nan=False)                                # what pipeline.py writes into index.json must parse
