"""quantum/research/g6_exposure.py (G6-EXPOSURE): positions, the five policies, concurrency, correlated exposure, the
daily book and the paired comparisons, worked by hand. No research data and no network needed."""
import json
import os

import numpy as np
import pandas as pd

from quantum.research import g6_exposure as G
from quantum.research import harness as H

REG = os.path.join(os.path.dirname(__file__), "..", "research", "registrations", "G6-EXPOSURE.json")
T0 = int(pd.Timestamp("2021-06-01T12:00:00Z").timestamp())          # a Tuesday, 08:00 New York


def iso(t):
    return pd.Timestamp(t, unit="s", tz="UTC").isoformat()


def tr(entry, exit_, r, d="LONG", **kw):
    """A trade whose signal bar opens at `entry` and whose exit bar opens at `exit_` (epoch seconds)."""
    t = {"dir": d, "entry_time": iso(entry), "exit_time": iso(exit_), "entry": 2000.0, "sl": 1990.0 if d == "LONG" else 2010.0,
         "r": r, "tp1_hit": r > 0, "session": "NY", "exit_reason": "SL" if r < 0 else "TP2", "open": False}
    t.update(kw)
    return t


def pos(*rows):
    """Positions straight from (tf, arm, d, fill, end, r) rows, already in order."""
    out = []
    for i, (tf, arm, d, fill, end, r) in enumerate(rows):
        out.append({"tf": tf, "arm": arm, "k": i, "i": i, "d": d, "fill": fill, "end": end, "r": r, "tp1": r > 0,
                    "stop_usd": 10.0, "session": "NY", "reason": "SL" if r < 0 else "TP2",
                    "day": G.session_day(fill), "exit_day": G.session_day(end)})
    return out


def test_the_policies_and_tie_break_are_the_registered_ones():
    with open(REG) as f:
        reg = json.load(f)
    assert list(reg["policies"]) == list(G.POLICIES)
    assert len(G.COMPARISONS) * len(G.MEASURES) == 10 and "5 comparisons x 2 measures = 10 tests" in reg["multiple_testing"]
    assert G.TF_RANK["1h"] < G.TF_RANK["30m"] < G.TF_RANK["15m"] < G.TF_RANK["5m"] and G.ARM_RANK["treatment"] < G.ARM_RANK["h4"]
    assert set(G.TFS) == {"5m", "15m", "30m", "1h"} and G.ARMS == ("treatment", "h4")


def test_positions_fill_at_the_signal_close_and_end_at_the_exit_close():
    trades = {("15m", "h4"): [tr(T0, T0 + 3600, 1.0), tr(T0, T0 + 900, 0.2, open=True)],
              ("1h", "treatment"): [tr(T0 - 2700, T0 + 7200, -1.0)],       # fills at T0 + 900 too: 1h first
              ("15m", "treatment"): [tr(T0, T0 + 1800, 0.5, d="SHORT")]}
    p, skipped = G.positions(trades)
    assert skipped == {"open_at_end": 1, "before_common_start": 0}
    assert [(x["tf"], x["arm"]) for x in p] == [("1h", "treatment"), ("15m", "treatment"), ("15m", "h4")]
    assert p[0]["fill"] == T0 + 900 and p[0]["end"] == T0 + 7200 + 3600
    assert p[2]["fill"] == T0 + 900 and p[2]["end"] == T0 + 3600 + 900 and p[1]["d"] == -1
    assert p[0]["stop_usd"] == 10.0 and p[0]["day"] == "2021-06-01"
    _, sk = G.positions(trades, start=T0 + 901)
    assert sk["before_common_start"] == 3


def test_replay_by_hand():
    h = 3600
    p = pos(("1h", "treatment", 1, T0, T0 + 2 * h, -1.0),            # 0: open 12:00-14:00
            ("15m", "h4", 1, T0 + h, T0 + 3 * h, 1.0),               # 1: inside 0
            ("15m", "treatment", -1, T0 + h, T0 + 4 * h, 0.5),       # 2: inside 0, the other direction
            ("5m", "h4", 1, T0 + 2 * h, T0 + 5 * h, -0.5),           # 3: starts when 0 closes
            ("5m", "treatment", -1, T0 + 6 * h, T0 + 7 * h, 2.0),    # 4: nothing open
            ("5m", "h4", 1, T0 + 8 * h, T0 + 9 * h, 1.0))            # 5: nothing open; the day's 4th P2 entry
    assert G.replay(p, "P0_none") == [True] * 6
    assert G.replay(p, "P1_one_open") == [True, False, False, True, True, True]     # 0 closing at 3's fill frees it
    assert G.replay(p, "P2_one_open_three_per_day") == [True, False, False, True, True, False]
    assert G.replay(p, "P3_three_open") == [True, True, True, True, True, True]
    assert G.replay(p, "P4_one_open_per_direction") == [True, False, True, True, True, True]
    four = pos(*[("5m", "h4", 1, T0 + i, T0 + 100, 0.0) for i in range(4)])
    assert G.replay(four, "P3_three_open") == [True, True, True, False]


def test_concurrency_by_hand():
    h = 3600
    p = pos(("1h", "treatment", 1, T0, T0 + 2 * h, -1.0), ("15m", "h4", 1, T0 + h, T0 + 3 * h, 1.0),
            ("15m", "treatment", -1, T0 + h, T0 + 4 * h, 0.5))
    grid = np.array([T0 - 1, T0, T0 + h, T0 + 2 * h, T0 + 3 * h, T0 + 4 * h], np.int64)
    c = G.counts_at(p, grid)
    assert c["all"].tolist() == [0, 1, 3, 2, 1, 0]
    assert c["long"].tolist() == [0, 1, 2, 1, 0, 0] and c["short"].tolist() == [0, 0, 1, 1, 1, 0]
    m = G.concurrency(p, grid)
    assert m["open_positions"]["max"] == 3 and m["open_positions"]["share_2_plus"] == round(2 / 6, 4)
    assert m["share_of_time_two_plus_same_direction"] == round(1 / 6, 4)
    assert m["share_of_time_long_and_short_together"] == round(2 / 6, 4)
    assert m["combined_stop_r"]["max_r_at_risk"] == 3 and m["combined_stop_r"]["max_usd_if_every_position_risked_650"] == 1950.0
    assert m["exact"]["max_open"] == 3 and m["exact"]["max_sum_stop_usd_per_oz"] == 30.0
    assert m["exact"]["first_at_utc"] == iso(T0 + h)
    # a close and a fill at the same instant do not overlap
    assert G.exact_max(pos(("5m", "h4", 1, T0, T0 + 300, 0.0), ("5m", "h4", 1, T0 + 300, T0 + 600, 0.0)))["max_open"] == 1


def test_correlated_by_hand():
    p = pos(("1h", "treatment", 1, T0, T0 + 7200, -1.0),
            ("15m", "h4", 1, T0 + 1800, T0 + 7200, -0.5),            # same direction, other tf, 30 min later
            ("15m", "treatment", 1, T0 + 1800, T0 + 3600, 1.0),      # same tf as the H4 one: the other arm
            ("5m", "h4", -1, T0 + 2400, T0 + 2700, 0.3))             # other direction
    c = G.correlated(p)
    assert c["share_with_same_direction_entry_on_another_tf_within_60m"] == 0.75
    assert c["share_with_same_direction_entry_on_other_arm_same_tf_within_60m"] == 0.5
    # pairs open together in the same direction: (0,1) both lost, (0,2), (1,2)
    assert c["same_direction_pairs_open_together"] == 3 and c["both_lost_share"] == round(1 / 3, 4)


def test_book_by_hand():
    d = 86400
    p = pos(("1h", "treatment", 1, T0, T0 + 3600, -1.0), ("15m", "h4", 1, T0 + 600, T0 + 4000, -1.0),
            ("15m", "h4", 1, T0 + 9000, T0 + 9900, 2.5), ("5m", "h4", -1, T0 + d, T0 + d + 600, -0.5))
    b = G.book(p)
    assert b["trades"] == 4 and b["net_r"] == 0.0 and b["max_dd_r"] == 2.0 and b["longest_losing_streak"] == 2
    assert b["potential_daily_loss_r"]["max"] == 3 and b["potential_daily_loss_r"]["max_day"] == "2021-06-01"
    assert b["potential_daily_loss_r"]["max_usd_if_every_position_risked_650"] == 1950.0
    assert b["realised_daily_r"]["worst"] == -0.5 and b["realised_daily_r"]["worst_day"] == "2021-06-02"
    assert G.streak([-1, 1, -1, -1, -1, 0.5]) == 3 and G.max_dd([]) == 0.0


def test_paired_comparison_and_corrections_by_hand():
    d = 86400
    p = pos(*[("1h", "treatment", 1, T0 + k * d, T0 + k * d + 7200, 1.0) for k in range(5)],
            *[("15m", "h4", 1, T0 + k * d + 900, T0 + k * d + 1800, -1.0) for k in range(5)])
    p.sort(key=lambda x: x["fill"])
    keeps = {k: G.replay(p, k) for k in G.POLICIES}
    assert keeps["P1_one_open"].count(True) == 5                      # every H4 trade starts inside a treatment one
    rows = {(r["a"], r["b"]): r for r in G.compare(p, keeps, H.seeded_rng(0), sims=500)}
    r = rows[("P1_one_open", "P0_none")]
    assert r["mean_net_r_per_trade"]["diff"] == 1.0 and r["mean_net_r_per_trade"]["ci95"] == [1.0, 1.0]
    assert r["net_r_per_day"]["diff"] == 1.0 and r["net_r_per_day"]["p_two_sided"] == 0.0
    same = rows[("P1_one_open", "P2_one_open_three_per_day")]          # identical kept sets here
    assert same["mean_net_r_per_trade"]["diff"] == 0.0 and same["mean_net_r_per_trade"]["p_two_sided"] == 1.0
    assert G.holm([0.01, 0.04, 0.03]) == [0.03, 0.06, 0.06] and G.bh([0.01, 0.04, 0.03]) == [0.03, 0.04, 0.04]
    b = G.blocked(p, keeps["P1_one_open"])
    assert b["count"] == 5 and b["mean_net_r"] == -1.0 and b["tp1_first_share"] == 0.0 and b["by_tf_arm"] == {"15m_h4": 5}


def test_study_without_policies_has_no_comparison():
    p = pos(("1h", "treatment", 1, T0, T0 + 3600, 1.0))
    out = G.study(p, np.array([T0 + 300], np.int64), None, with_policies=False)
    assert "policies" not in out and "comparisons" not in out and out["positions"] == 1


def test_edges_the_first_tests_left_open():
    # a flat trade is not a loss; realised P/L belongs to the exit day; another arm on the SAME timeframe is not another tf
    assert G.streak([-1, 0, -1]) == 1
    d = 86400
    overnight = pos(("1h", "treatment", 1, T0, T0 + d, -2.0), ("15m", "h4", 1, T0 + 2 * d, T0 + 2 * d + 900, 1.0))
    assert G.book(overnight)["realised_daily_r"]["worst_day"] == "2021-06-02"
    twins = pos(("15m", "treatment", 1, T0, T0 + 900, 1.0), ("15m", "h4", 1, T0 + 600, T0 + 1800, 1.0))
    c = G.correlated(twins)
    assert c["share_with_same_direction_entry_on_another_tf_within_60m"] == 0.0
    assert c["share_with_same_direction_entry_on_other_arm_same_tf_within_60m"] == 1.0
    # net R per day divides by the number of days, not by the number of trades kept
    p = pos(("1h", "treatment", 1, T0, T0 + 7200, 1.0), ("15m", "h4", 1, T0 + 900, T0 + 1800, -1.0),
            ("15m", "h4", 1, T0 + d, T0 + d + 900, -1.0), ("15m", "h4", 1, T0 + d + 3600, T0 + d + 4500, -1.0))
    keeps = {k: G.replay(p, k) for k in G.POLICIES}
    rows = {(x["a"], x["b"]): x for x in G.compare(p, keeps, H.seeded_rng(0), sims=200)}
    r = rows[("P1_one_open", "P0_none")]
    assert r["net_r_per_day"]["diff"] == 0.5 and r["mean_net_r_per_trade"]["diff"] == round(-1 / 3 + 0.5, 4)
    # the two days differ, so only a PAIRED bootstrap gives an identical pair of policies a zero-width interval
    assert keeps["P1_one_open"] == keeps["P2_one_open_three_per_day"]
    same = rows[("P1_one_open", "P2_one_open_three_per_day")]
    assert same["mean_net_r_per_trade"]["ci95"] == [0.0, 0.0] and same["net_r_per_day"]["ci95"] == [0.0, 0.0]


def _brute_replay(p, policy):
    kept = []
    for x in p:
        live = [q for q in kept if q["fill"] <= x["fill"] < q["end"]]
        day = sum(1 for q in kept if q["day"] == x["day"])
        ok = {"P0_none": True, "P1_one_open": not live, "P2_one_open_three_per_day": not live and day < 3,
              "P3_three_open": len(live) < 3, "P4_one_open_per_direction": all(q["d"] != x["d"] for q in live)}[policy]
        if ok:
            kept.append(x)
    return [any(q is x for q in kept) for x in p]


def test_replay_and_counts_equal_brute_force_on_random_positions():
    rng = H.seeded_rng(7)
    rows = []
    for _ in range(400):
        f = T0 + int(rng.integers(0, 20)) * 3600 + int(rng.integers(0, 12)) * 300     # many ties and touching ends
        rows.append((str(rng.choice(["5m", "15m", "30m", "1h"])), str(rng.choice(["treatment", "h4"])),
                     int(rng.choice([1, -1])), f, f + int(rng.integers(1, 30)) * 300, float(rng.normal())))
    p = pos(*rows)
    p.sort(key=lambda x: (x["fill"], G.TF_RANK[x["tf"]], G.ARM_RANK[x["arm"]], x["k"]))
    for k in G.POLICIES:
        assert G.replay(p, k) == _brute_replay(p, k), k
    grid = np.arange(T0, T0 + 30 * 3600, 300, dtype=np.int64)
    c = G.counts_at(p, grid)
    assert c["all"].tolist() == [sum(1 for x in p if x["fill"] <= g < x["end"]) for g in grid]
    assert G.exact_max(p)["max_open"] == max(sum(1 for q in p if q["fill"] <= x["fill"] < q["end"]) for x in p)


def test_a1_family_is_the_registered_one_and_keeps_the_primary_order():
    with open(REG) as f:
        a1 = json.load(f)["amendments"][0]
    assert a1["id"] == "A1" and "h6" not in G.ARMS_A1
    assert all(arm in a1["arms"] for arm in G.ARMS_A1) and list(G.TFS_A1) == ["5m", "15m", "30m", "1h", "4h"]
    assert G.FAMILIES["primary"] == (G.TFS, G.ARMS) and G.TFS_A1["4h"] == 14400
    assert sorted(G.TFS_A1, key=G.TF_RANK.get) == ["4h", "1h", "30m", "15m", "5m"]
    assert sorted(G.ARMS_A1, key=G.ARM_RANK.get) == list(G.ARMS_A1)
    assert G.ARM_RANK["treatment"] < G.ARM_RANK["h4"]                     # the primary tie-break is unchanged
    trades = {("4h", "h5"): [tr(T0 - 14400 + 900, T0 + 3600, 1.0)], ("1h", "control"): [tr(T0 - 2700, T0 + 3600, 1.0)],
              ("1h", "treatment"): [tr(T0 - 2700, T0 + 3600, 1.0)]}           # all three fill at T0 + 900
    p, _ = G.positions(trades)
    assert [(x["tf"], x["arm"]) for x in p] == [("4h", "h5"), ("1h", "treatment"), ("1h", "control")]


def test_out_of_scope_records_are_counted_not_modelled(tmp_path):
    (tmp_path / "notifications").mkdir()
    (tmp_path / "notifications" / "2026-11-27.jsonl").write_text('{"stream": "breakouts"}\n{"stream": "15m"}\nnot json\n')
    (tmp_path / "research_forward").mkdir()
    (tmp_path / "research_forward" / "B9-GRAB-FWD.json").write_text('{"id": "B9", "trades": [{}, {}]}')
    (tmp_path / "research_forward" / "CONFIRM-EVENTS.jsonl").write_text("{}\n{}\n{}\n")
    o = G.out_of_scope(str(tmp_path))
    assert o["notification_attempts_by_stream"] == {"15m": 1, "breakouts": 1, "unreadable line": 1}
    assert o["research_forward_records"] == {"B9-GRAB-FWD.json": {"trades": 2}, "CONFIRM-EVENTS.jsonl": 3}


def test_the_forward_grid_keeps_only_trading_bars(tmp_path):
    d = tmp_path / "XAU_USD_5m"
    d.mkdir()
    rows = ["datetime,open,high,low,close,volume",
            "2026-11-20 14:00:00+00:00,1,1,1,1,",          # Friday 09:00 New York: trading
            "2026-11-20 14:02:31+00:00,1,1,1,1,",          # off the grid (a quote stamped with its own time)
            "2026-11-21 14:00:00+00:00,1,1,1,1,",          # Saturday: gold is shut
            "2026-11-23 14:05:00+00:00,1,1,1,1,"]          # Monday: trading
    (d / "2026-11.csv").write_text("\n".join(rows) + "\n")
    got = G.grid5(str(tmp_path)).tolist()
    assert got == [int(pd.Timestamp(x).timestamp()) for x in ("2026-11-20T14:00:00Z", "2026-11-23T14:05:00Z")]


def test_the_results_document_is_what_the_evidence_gives():
    """research/G6_EXPOSURE_RESULTS.md is generated from the committed result, check and evidence files."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "audit", "tools"))
    import g6_doc
    assert g6_doc.main(["--check"]) == 0
