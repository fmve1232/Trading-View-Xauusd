"""B31b-W2 (research/registrations/B31b-W2.json): every C / D / E setup, its fate and the reason; no outcome.
Synthetic data only; the sealed partitions are never opened here."""
import csv
import json

import numpy as np
import pandas as pd
import pytest

from quantum.data.market import load_synthetic
from quantum.research import b31, b31w2 as W
from quantum.research import harness as H

OUTCOME_KEYS = ('"out"', '"r"', "r_thirds", "mfe", "mae", '"net"', '"tp2"', '"tp3"', "min_to_tp1", '"score"', "exit_bar", "mean_r", "tp1_rate")


@pytest.fixture(scope="module")
def synth():
    m15 = load_synthetic("15m", bars=6000, seed=5).base
    h1 = load_synthetic("1h", bars=3000, seed=5).base
    start = m15.index[0] + pd.Timedelta(days=5)
    X, t_from = W.context(m15, h1, start)
    evs = b31.crossings(X, b31.SELL_SIDE + b31.BUY_SIDE)
    return m15, h1, start, X, t_from, evs


def test_registration_matches_the_code():
    with open("research/registrations/B31b-W2.json") as f:
        reg = json.load(f)
    assert reg["id"] == W.REG and reg["approved_by_operator"] is True and reg["partitions"] == ["development", "validation", "holdout"]
    assert W.MODS == ("C", "D", "E") and W.RULES == {"tp1_10": 10.0, "ladder_15": 15.0}
    two = reg["what_is_counted"]["two_eligibility_rules_side_by_side"]
    assert "(10 - cost) / (D + cost) >= 1" in two and "(15 - cost) / (D + cost) >= 1" in two
    assert "No trade outcome" in reg["no_outcomes"] and "Report every rejected setup and rejection reason" in reg["approval"]
    df = pd.DataFrame({"x": [1.0]}, index=pd.DatetimeIndex([H.VAL[0] + pd.Timedelta(days=1)]))
    assert len(H.partition(df, "validation", W.REG)) == 1                      # this registration opens the sealed partitions
    with pytest.raises(H.SealedPartition):
        H.partition(df, "validation", None)


def test_recording_the_reasons_changes_nothing_in_the_run(synth):
    *_, X, t_from, evs = synth
    seen = 0
    for mod in W.MODS:
        sets = b31.setups(X, mod, evs)
        for reward in W.RULES.values():
            plain = b31.run_module(X, sets, t_from, "model", reward)
            tr: list = []
            traced = b31.run_module(X, sets, t_from, "model", reward, tr)
            assert traced == plain                                             # the same counts and the same trades
            st = plain["stat"]
            assert len(tr) == st["setups"]                                     # one row per counted setup, never more
            fates = [r["fate"] for r in tr]
            assert fates.count("repeat") == st["repeat"] and fates.count("executed") == st["executed"]
            assert fates.count("missed") == st["missed"] and fates.count("overlap") == st["overlap"]
            assert fates.count("invalidated") == st["invalidated"] and fates.count("false_breakout") == st["false_breakout"]
            why = {}
            for r in tr:
                if r["fate"] == "rejected":
                    why[r["why"]] = why.get(r["why"], 0) + 1
            assert why == st["rejected"]
            assert all(set(r) & {"out", "r", "net", "mfe", "mae", "r_thirds", "exit_bar", "score"} == set() for r in tr)
            seen += st["setups"]
    assert seen > 50                                                           # the synthetic market does produce setups


def test_each_reason_agrees_with_the_distance_that_was_measured(synth):
    *_, X, t_from, evs = synth
    n = 0
    for mod in W.MODS:
        _, rows, _raw = W.order_life(X, b31.setups(X, mod, evs), t_from)
        for r in rows:
            for rule, reward in W.RULES.items():
                fate, why = r[f"fate_{rule}"], r[f"why_{rule}"]
                if fate == "repeat":
                    assert r["D"] is None and r[f"rr_{rule}"] is None          # a repeat is not measured
                    continue
                n += 1
                rr = (reward - r["cost"]) / (r["D"] + r["cost"])         # from the rounded D and cost: close, not equal
                assert r[f"rr_{rule}"] == pytest.approx(rr, rel=0.01, abs=0.006)
                rr = r[f"rr_{rule}"]                                     # computed from the unrounded values, then rounded
                if fate != "rejected":
                    assert r["D"] >= 5 - 0.006 and rr >= 1 - 0.006 and r["cost"] <= 0.15 * r["D"] + 0.006   # it passed every check
                    assert (r["room"] is None or r["room"] >= 10 - 0.006) and (r["vwap_room"] is None or r["vwap_room"] >= 10 - 0.006)
                elif why == "stop":
                    assert 0 < r["D"] < 5 + 0.006
                elif why == "reward":
                    assert r["D"] >= 5 - 0.006 and rr < 1 + 0.006
                elif why == "cost":
                    assert rr >= 1 - 0.006 and r["cost"] > 0.15 * r["D"] - 0.006
                elif why == "room":
                    assert (r["room"] is not None and r["room"] < 10 + 0.006) or (r["vwap_room"] is not None and r["vwap_room"] < 10 + 0.006)
                else:
                    assert why == "stop on the wrong side" and r["D"] <= 0
    assert n > 50


def test_the_ladder_rule_moves_only_the_reward_check(synth):
    *_, X, t_from, evs = synth
    for mod in W.MODS:
        stats, rows, _raw = W.order_life(X, b31.setups(X, mod, evs), t_from)
        a, b = stats["tp1_10"], stats["ladder_15"]
        assert a["setups"] == b["setups"] == len(rows) and a["repeat"] == b["repeat"]
        assert a["rejected"].get("stop", 0) == b["rejected"].get("stop", 0)    # checked before the reward
        assert b["rejected"].get("reward", 0) <= a["rejected"].get("reward", 0)
        for r in rows:
            if r["fate_tp1_10"] == "rejected" and r["why_tp1_10"] != "reward":
                assert (r["fate_ladder_15"], r["why_ladder_15"]) == ("rejected", r["why_tp1_10"])
            if r["fate_ladder_15"] == "rejected" and r["why_ladder_15"] == "reward":
                assert (r["fate_tp1_10"], r["why_tp1_10"]) == ("rejected", "reward")   # too wide at +15 is too wide at +10


def test_the_upstream_funnels_follow_the_modules_own_selection(synth):
    *_, X, t_from, evs = synth
    c = W.upstream_c(X, evs, t_from)
    assert c["first_crossings_of_a_pool"] == c["rejected_within_3_bars"] + c["accepted_3_closes_beyond"]
    assert c["accepted_with_an_fvg_in_the_breakout_leg"] <= c["accepted_3_closes_beyond"]
    c_sets = [s for s in b31.setups(X, "C", evs) if X.t[s["order_bar"]] + 900 >= t_from]
    assert c["accepted_with_an_fvg_in_the_breakout_leg"] == len(c_sets)        # a C order is placed on the 3rd close: the same bar
    d = W.upstream_d(X, t_from)
    assert d["all_setups"] == len(b31.setups(X, "D", evs)) > 0                 # the copied loop finds exactly b31's setups
    assert d["ranging_bars"] >= d["first_bars_of_a_2_sigma_deviation"] >= d["closed_back_inside_within_3_bars"]
    assert d["closed_back_inside_within_3_bars"] == d["vetoed_by_a_strong_displacement_body"] + d["setups"]
    assert W.upstream_d(X, 0)["setups"] == d["all_setups"] and d["setups"] < d["all_setups"]   # scored bars only
    e = W.upstream_e(X, evs, t_from)
    assert e["days_with_a_first_asia_range_crossing_in_london_or_ny"] == e["of_which_a_sweep_rejected"] + e["of_which_a_break_accepted"]
    assert e["days_with_a_first_asia_range_crossing_in_london_or_ny"] <= e["trading_days"]
    made = e["sweeps_with_a_structure_shift_and_an_entry_zone"] + e["breaks_with_an_fvg_in_the_breakout_leg"]
    e_all = W.upstream_e(X, evs, 0)
    assert e_all["sweeps_with_a_structure_shift_and_an_entry_zone"] + e_all["breaks_with_an_fvg_in_the_breakout_leg"] == len(b31.setups(X, "E", evs))
    assert made <= len(b31.setups(X, "E", evs))


def test_the_stop_distance_table_adds_up():
    rows = [{"D": d, "cost": 0.8} for d in (3.0, 4.9, 5.0, 8.4, 8.5, 13.4, 13.5, 20.0)] + [{"D": None, "cost": None}, {"D": -1.0, "cost": 0.8}]
    t = W.distances(rows)
    assert (t["n"], t["tp1_rule_limit_usd"], t["ladder_rule_limit_usd"], t["median_cost"]) == (8, 8.4, 13.4, 0.8)   # 10 - 1.6, 15 - 1.6
    assert (t["below_5"], t["from_5_to_the_tp1_rule_limit"], t["from_there_to_the_ladder_rule_limit"], t["above_the_ladder_rule_limit"]) == (2, 2, 2, 2)
    assert t["percentiles_usd"]["50"] == pytest.approx(np.percentile([3.0, 4.9, 5.0, 8.4, 8.5, 13.4, 13.5, 20.0], 50), abs=0.01)
    assert W.distances([{"D": None, "cost": None}]) == {"n": 0}


def test_the_run_writes_counts_and_distances_and_no_outcome(synth, monkeypatch, tmp_path):
    m15, h1, start, *_ = synth
    monkeypatch.setattr(W, "load_part", lambda rd, part: (m15, h1, start))
    out, cs, tr = tmp_path / "w2.json", tmp_path / "w2.csv", tmp_path / "trials.jsonl"
    assert W.main(["--rd", "unused", "--parts", "development", "--out", str(out), "--csv", str(cs), "--trials", str(tr)]) == 0
    text = out.read_text()
    res = json.loads(text)
    assert res["registration"] == "B31b-W2" and set(res["parts"]) == {"development"} and "rows" not in res["parts"]["development"]
    assert not any(k in text for k in OUTCOME_KEYS)                            # nothing about how a trade ended
    P = res["parts"]["development"]
    assert set(P["modules"]) == set(P["upstream"]) == {"C", "D", "E"} and "all_setups" not in P["upstream"]["D"]
    with open(cs) as f:
        rows = list(csv.DictReader(f))
    assert tuple(rows[0]) == W.ROW_KEYS and not any(k in ("entry", "stop", "limit", "price", "p_ref", "open", "high", "low", "close") for k in rows[0])
    for m in W.MODS:
        st = P["modules"][m]["rules"]
        mine = [r for r in rows if r["mod"] == m]
        assert len(mine) == st["tp1_10"]["setups"] == st["ladder_15"]["setups"]
        assert sum(r["fate_ladder_15"] == "executed" for r in mine) == st["ladder_15"]["executed"]
        assert sum(r["fate_tp1_10"] == "rejected" for r in mine) == sum(st["tp1_10"]["rejected"].values())
    assert all(r["part"] == "development" for r in rows) and len(rows) > 50
    *_, X, t_from, evs = synth
    for m in W.MODS:                                                           # the tables come from the unrounded distances
        _, _, raw = W.order_life(X, b31.setups(X, m, evs), t_from)
        assert P["modules"][m]["stop_distance"] == W.distances(raw) and P["modules"][m]["checks"] == W.failures(raw)
    (line,) = [json.loads(x) for x in tr.read_text().splitlines()]
    assert line["reg"] == "B31b-W2" and line["outcomes_inspected"] is False and set(line["setups"]) == {"C", "D", "E"}
    assert not any(k in json.dumps(line) for k in OUTCOME_KEYS)


# ---------------- hand-worked cases (tests/test_research_b31.py's market; prices near $4,000, cost $0.80) ----------------
def test_measure_reports_the_distances_check_compares():
    from tests.test_research_b31 import _ctx
    X = _ctx(40, {}, pools={"PDH": 4003.0})
    s = {"dir": 1, "stop": 3988.0}
    m = b31.measure(X, s, 3995.0, 5, 0.8)                                    # sc = 3995 / 4000
    assert m["D"] == pytest.approx(7.0 / 0.99875) and m["room"] == pytest.approx(8.0 / 0.99875)
    assert m["cost_frac"] == pytest.approx(0.8 / (7.0 / 0.99875)) and m["vwap_room"] is None and m["cost"] == 0.8
    assert b31.check(X, s, 3995.0, 5, 0.8) == "room"                         # the pool 8 above is inside +$10
    assert b31.measure(_ctx(40, {}), s, 3995.0, 5, 0.8)["room"] is None       # no opposing pool: no limit
    sv = dict(s, vwap=4001.0)
    assert b31.measure(_ctx(40, {}), sv, 3995.0, 5, 0.8)["vwap_room"] == pytest.approx(6.0 / 0.99875)


def test_an_invalidated_limit_and_an_overlapping_position_are_named_in_the_listing():
    from tests.test_research_b31 import BASE, WIN, _a, _ctx
    X, evs = _a({**BASE, 13: (3999, 3999.5, 3996, 3997), 14: (3988.0, 3989, 3987.9, 3988.5)})   # opens below the extreme
    tr: list = []
    R = b31.run_module(X, b31.setups(X, "A", evs), 0, trace=tr)
    assert R["stat"]["invalidated"] == 1 and [(x["fate"], x["why"]) for x in tr] == [("invalidated", "opened beyond the sweep extreme")]
    assert tr[0]["D"] == pytest.approx(7.5 / (3995 / 4000), abs=0.01)        # limit 3995, stop 3987.50
    X, evs = _a({**BASE, 13: (3999, 3999.5, 3996, 3997)}, dn_any=(13,))      # a bearish structure event before any fill
    tr = []
    R = b31.run_module(X, b31.setups(X, "A", evs), 0, trace=tr)
    assert R["stat"]["invalidated"] == 1 and [(x["fate"], x["why"]) for x in tr] == [("invalidated", "structure broke the other way")]
    # a limit below the sweep extreme passes the $5 stop check only when 0.2 x ATR exceeds about $5 (ATR above 25): a bar
    # can then trade beyond the extreme without reaching the limit
    s6 = {"order_bar": 12, "limit": 3990.0, "stop": 3984.0, "inval": 3992.0, "entry_type": "OB", "dir": 1, "ev": {"kind": "PDL", "bars": 1}}
    tr = []
    R = b31.run_module(_ctx(40, {13: (3995, 3995.5, 3991.0, 3994)}), [s6], 0, trace=tr)
    assert R["stat"]["invalidated"] == 1 and [(x["fate"], x["why"]) for x in tr] == [("invalidated", "traded beyond the sweep extreme")]
    X = _ctx(60, {**BASE, **WIN})
    s1 = {"order_bar": 12, "limit": 3995.0, "stop": 3987.5, "inval": None, "entry_type": "FVG", "dir": 1, "ev": {"kind": "PDL", "bars": 1}}
    s5 = dict(s1, limit=3999.0, stop=4006.5, dir=-1, ev={"kind": "PDH", "bars": 1})   # a SELL filled on bar 13 while s1 is open
    tr = []
    R = b31.run_module(X, [s1, s5], 0, trace=tr)
    assert (R["stat"]["executed"], R["stat"]["overlap"]) == (1, 1)
    assert [(x["kind"], x["fate"], x["why"]) for x in tr] == [("PDL", "executed", None), ("PDH", "overlap", "a position was still open")]
    tr = []
    R = b31.run_module(X, [dict(s1, limit=3975.0, stop=3967.5)], 0, trace=tr)          # never reached in 8 bars
    assert R["stat"]["missed"] == 1 and [(x["fate"], x["why"]) for x in tr] == [("missed", "limit not reached in 8 bars")]


def test_the_sealed_partitions_are_opened_by_this_registration_and_development_by_none(monkeypatch):
    idx = pd.date_range("2020-01-01", "2026-06-01", freq="1D", tz="UTC")
    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}, index=idx)
    monkeypatch.setattr(W.history, "load", lambda rd, sym, tf: df)
    seen = []
    real = H.partition
    monkeypatch.setattr(W.H, "partition", lambda d, name, reg=None: seen.append((name, reg)) or real(d, name, reg))
    for part in ("development", "validation", "holdout"):
        W.load_part("unused", part)
    assert seen == [("development", None)] * 2 + [("validation", "B31b-W2")] * 2 + [("holdout", "B31b-W2")] * 2
    m15, _, start = W.load_part("unused", "recent")
    assert m15.index[0] >= H.HOLD[1] and start == H.HOLD[1] + pd.Timedelta(days=59) and len(seen) == 6   # recent is not sealed


def test_the_d_funnel_counts_each_stage_on_a_hand_worked_market():
    """Ranging bars with a 2-sigma band at 3990 / 4000. Bar 5 dips to 3989 and closes back inside on the same bar (a setup);
    bar 15 dips to 3986.50 with a 13-dollar bearish body (above 2.5 x ATR 5) and closes back on bar 16 (vetoed); bar 25
    dips and stays below for 3 bars (no setup); bar 26 is the second bar of that deviation (not counted again)."""
    from tests.test_research_b31 import _ctx
    edits = {5: (3995, 3995.5, 3989.0, 3992), 6: (3992, 3993, 3991, 3992.5),
             15: (3999.9, 3999.95, 3986.5, 3986.9), 16: (3986.9, 3992, 3986.5, 3991.5),
             25: (3995, 3995.5, 3989.5, 3989.6), 26: (3989.6, 3989.8, 3989.0, 3989.5), 27: (3989.5, 3989.9, 3989.2, 3989.7)}
    X = _ctx(40, edits)
    X.ranging[:] = True
    X.lo2[:], X.up2[:], X.vwap[:] = 3990.0, 4000.0, 3995.0
    d = W.upstream_d(X, 0)
    assert d == {"ranging_bars": 39, "first_bars_of_a_2_sigma_deviation": 3, "closed_back_inside_within_3_bars": 2,
                 "vetoed_by_a_strong_displacement_body": 1, "setups": 1, "all_setups": 1}
    (s,) = b31.setups(X, "D", [])
    assert s["ev"]["j"] == s["order_bar"] == 5                                # it closed back inside on the same bar


def test_the_tables_use_unrounded_distances_and_agree_with_the_check_order(synth):
    *_, X, t_from, evs = synth
    for mod in W.MODS:
        stats, rows, raw = W.order_life(X, b31.setups(X, mod, evs), t_from)
        a = stats["tp1_10"]
        assert len(raw) == a["setups"] - a["repeat"] == sum(r["D"] is not None for r in rows)
        sd = W.distances(raw)
        assert sd["below_5"] == a["rejected"].get("stop", 0) == stats["ladder_15"]["rejected"].get("stop", 0)   # exactly
        f = W.failures(raw)
        for rule in W.RULES:
            st = stats[rule]
            assert f[rule]["measured"] == len(raw)
            assert f[rule]["pass_every_check"] == len(raw) - sum(st["rejected"].values())       # passed check() = reached the order
            assert f[rule]["fail"]["stop"] == st["rejected"].get("stop", 0)
            for c in W.CHECKS:
                assert f[rule]["fail_only"][c] <= f[rule]["fail"][c] >= st["rejected"].get(c, 0)
            for m in raw:
                x = W.fails(m, rule)
                if m[f"fate_{rule}"] == "rejected":
                    assert x                                                  # the first failed check is the reason recorded
                else:
                    assert not x
        r = [m for m in raw if m["fate_tp1_10"] == "rejected"]
        tr: list = []
        b31.run_module(X, b31.setups(X, mod, evs), t_from, "model", W.RULES["tp1_10"], tr)
        why = [z["why"] for z in tr if z["fate"] == "rejected"]
        assert [W.fails(m, "tp1_10")[0] for m in r] == why                    # in the order b31.check tests them


def test_fails_lists_every_failed_check():
    m = {"D": 4.0, "cost": 0.8, "room": 6.0, "vwap_room": None, "rr_tp1_10": (10 - 0.8) / 4.8, "rr_ladder_15": (15 - 0.8) / 4.8}
    assert W.fails(m, "tp1_10") == ["stop", "cost", "room"] and W.fails(m, "ladder_15") == ["stop", "cost", "room"]   # 0.8 > 0.6
    m = {"D": 12.0, "cost": 0.8, "room": None, "vwap_room": 25.0, "rr_tp1_10": 9.2 / 12.8, "rr_ladder_15": 14.2 / 12.8}
    assert W.fails(m, "tp1_10") == ["reward"] and W.fails(m, "ladder_15") == []
    assert W.fails(dict(m, D=-1.0), "tp1_10") == ["stop on the wrong side"]
    assert W.fails(dict(m, vwap_room=9.9), "ladder_15") == ["room"]
    assert W.fails(dict(m, D=5.0, cost=0.5, rr_ladder_15=14.5 / 5.5), "ladder_15") == []      # exactly $5 is allowed
    assert W.fails(dict(m, D=4.99, cost=0.5, rr_ladder_15=14.5 / 5.49), "ladder_15") == ["stop"]
    raw = [{"D": 4.0, "cost": 0.8, "room": 6.0, "vwap_room": None, "rr_tp1_10": 1.9, "rr_ladder_15": 2.9},      # stop, cost, room
           {"D": 12.0, "cost": 0.8, "room": None, "vwap_room": None, "rr_tp1_10": 0.72, "rr_ladder_15": 1.11},   # reward at +10 only
           {"D": 7.0, "cost": 0.8, "room": 8.0, "vwap_room": None, "rr_tp1_10": 1.18, "rr_ladder_15": 1.82},     # room only
           {"D": 7.0, "cost": 0.8, "room": 30.0, "vwap_room": None, "rr_tp1_10": 1.18, "rr_ladder_15": 1.82}]    # passes
    f = W.failures(raw)
    assert f["tp1_10"] == {"measured": 4, "pass_every_check": 1, "fail": {"stop": 1, "reward": 1, "cost": 1, "room": 2, "stop on the wrong side": 0},
                           "fail_only": {"stop": 0, "reward": 1, "cost": 0, "room": 1}}
    assert f["ladder_15"]["pass_every_check"] == 2 and f["ladder_15"]["fail"]["reward"] == 0
