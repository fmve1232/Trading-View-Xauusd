"""Phase B6-explore (quantum/research/b6_mtf_live.py): the higher-timeframe context uses only signals decided at or before
each signal, within the declared ages; groups select what they say."""
import pandas as pd

from quantum.research import b6_mtf_live as B


def _sig(rows):
    return pd.DataFrame(rows, columns=["tf", "t", "dir", "entry"])


def test_context_uses_only_earlier_decisions_within_age():
    s = _sig([("1h", 1000, -1, 1.0), ("4h", 500, -1, 1.0), ("15m", 1500, 1, 1.0),
              ("5m", 1200, -1, 1.0),                       # 1h SHORT decided at 1000: known; 15m at 1500: not yet
              ("1h", 2000, 1, 1.0), ("5m", 2000, 1, 1.0),   # same-second 1h decision counts (decided at or before)
              ("5m", 1000 + 25 * 3600, -1, 1.0)])           # 1h signal now older than 24 h
    c = B.context(s).set_index(["tf", "t"])
    assert c.loc[("5m", 1200), "h1"] == -1 and c.loc[("5m", 1200), "h4"] == -1 and c.loc[("5m", 1200), "m15"] == 0
    assert c.loc[("5m", 2000), "h1"] == 1 and c.loc[("5m", 2000), "m15"] == 1
    assert c.loc[("5m", 1000 + 25 * 3600), "h1"] == 0


def test_groups():
    df = pd.DataFrame({"tf": ["5m", "5m", "15m", "5m"], "dir": [1, -1, 1, 1], "h1": [1, 1, 0, 1], "h4": [1, 0, 1, -1], "m15": [1, -1, 0, 0]})
    assert B.group_mask(df, "H1_AGREE").tolist() == [True, False, False, True]
    assert B.group_mask(df, "H1_AGAINST").tolist() == [False, True, False, False]
    assert B.group_mask(df, "H1_H4_AGREE").tolist() == [True, False, False, False]
    assert B.group_mask(df, "M15_AGREE").tolist() == [True, True, False, False]
    assert B.TARGETS == {"T13": (13.0, 13.0), "T10": (10.0, 10.0)}
