"""The gold-arrows grid (Pine v53-v73 GOLD ARROWS, report.gold_arrows): display only, every cell from engine values."""
from quantum import engine, report
from quantum.config import DEFAULT
from quantum.data.market import load_synthetic

NAMES = ["TREND", "STRUCT", "BIAS", "LIQ", "EMA200", "VWAP", "VALUE", "MTF", "5M", "15M", "1H", "4H", "1D",
         "CVD", "DISPL", "RSI DIV", "DXY", "10Y", "TIPS", "EUR", "XAG", "SPX", "MACRO", "CLIMAX"]


def test_grid_cells_and_rules():
    m = load_synthetic("1h", bars=1500, seed=4)
    res = engine.run(m, DEFAULT)
    i = res.F["n"] - 1
    g = report.gold_arrows(res.last, res.F, i, m.tf_sec)
    assert [c["name"] for c in g] == NAMES
    by = {c["name"]: c for c in g}
    for nm in ("5M", "15M", "1H"):                                # at or below the 1h chart: no vote, no data
        assert by[nm]["d"] is None and by[nm]["text"] == "no data on this TF"
    assert by["4H"]["d"] in (-1, 0, 1) and by["1D"]["d"] in (-1, 0, 1)
    assert by["RSI DIV"]["d"] is None and "filter off" in by["RSI DIV"]["text"]   # engine default: no divergence filter
    assert by["TIPS"]["d"] is None and by["TIPS"]["text"] == "off: same feed as 10Y"
    for nm in ("DXY", "10Y", "EUR", "XAG"):
        assert by[nm]["d"] is None or by[nm]["d"] in (-2, -1, 0, 1, 2)
    b, s = res.last["bull_score"], res.last["bear_score"]
    assert by["BIAS"]["d"] == (0 if abs(b - s) < 5 else 1 if b > s else -1)
    assert by["CLIMAX"]["d"] is None and "amber" in by["CLIMAX"]
