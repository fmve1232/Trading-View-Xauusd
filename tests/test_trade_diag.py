"""quantum/trade_diag.py (G4): per-trade diagnostics worked by hand on hand-made 5-minute bars in a throwaway store;
the no-look-ahead, finality and write-once rules; the news classification; the summary; and agreement with the
independent checker (audit/tools/trade_diag_check.py, built on h4_forward_diagnosis.races) on random synthetic paths."""
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

from quantum import trade_diag as TD
from quantum.data import store

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "audit", "tools"))
import trade_diag_check as CHK

T0 = pd.Timestamp("2026-11-17T10:15:00Z")          # a Tuesday in London hours: the 10:00 15m bar's close = the fill
E0 = int(T0.timestamp())
LATER = E0 + 86400                                 # a run time after every hand-made bar has closed


def _read(path, mode="r"):
    with open(path, mode) as f:
        return f.read()


def _bars(rows, start=T0):
    idx = pd.date_range(start, periods=len(rows), freq="5min", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx).assign(volume=0.0)


def _store(tmp_path, rows, trades, tf="15m", arm="h4"):
    d = str(tmp_path / "store")
    store.save(d, "XAU/USD_5m", _bars(rows))
    os.makedirs(os.path.join(d, "holdout"), exist_ok=True)
    with open(os.path.join(d, "holdout", f"{tf}_{arm}.json"), "w") as f:
        json.dump(trades, f)
    return d


def _trade(**kw):
    t = {"dir": "LONG", "entry_time": "2026-11-17T10:00:00+00:00", "exit_time": "2026-11-17T10:30:00+00:00",
         "entry": 4000.0, "sl": 3990.0, "tp1": 4013.0, "tp2": 4020.0, "exit": 4000.0, "exit_reason": "BE",
         "tp1_hit": True, "pts": -0.77, "gross_pts": 0.0, "cost_pts": 0.77, "r": -0.077, "bars": 2, "open": False,
         "session": "LONDON", "regime": "RANGE", "freeze_key": "k", "price_source": "twelvedata:XAU/USD"}
    t.update(kw)
    return t


LONG_PATH = [(4000, 4004, 3998, 4003),       # 10:15
             (4003, 4011, 4002, 4010),       # 10:20  +$10 (4010)
             (4010, 4016, 4009, 4015),       # 10:25  +$15 (4015) and TP1 (4013)
             (4015, 4015, 3989, 3990),       # 10:30  the stop (3990), and break-even (4000) inside the exit bar
             (3990, 3995, 3985, 3992), (3992, 3994, 3988, 3990)]

ALL_TARGETS_PATH = [(4000, 4006, 3999, 4005),    # 10:15
                    (4005, 4012, 4004, 4011),    # 10:20  +$10
                    (4011, 4016, 4010, 4015),    # 10:25  +$15, TP1
                    (4015, 4021, 4014, 4019),    # 10:30  +$20, TP2 (4020): every target before any stop
                    (4019, 4019.5, 4018, 4019), (4019, 4019.5, 4018, 4019), (4019, 4019.5, 4018, 4019)]
TP2_TRADE = {"exit_reason": "TP2", "exit": 4020.0, "gross_pts": 16.5, "r": 1.573}


def test_a_long_trade_by_hand(tmp_path):
    d = _store(tmp_path, LONG_PATH, [_trade()])
    rec = TD.diagnose("15m", "h4", _trade(), TD.bars5(d), evs=[])
    r = rec["race"]
    assert r["usd10"] == {"result": "TARGET", "hours": round(10 / 60, 3), "price": 4010.0}      # bar 10:20 closes 10:25
    assert r["usd15"]["result"] == "TARGET" and r["usd15"]["hours"] == 0.25 and r["tp1"]["hours"] == 0.25
    assert r["usd20"]["result"] == "STOP_FIRST" and r["tp2"]["result"] == "STOP_FIRST"
    assert rec["race_window"] == {"ends": "STOP", "bars": 4, "hours": round(20 / 60, 3), "mfe_usd": 16.0}  # stop bar's high not counted
    assert rec["stop"]["hit"] and rec["stop"]["hours"] == round(20 / 60, 3) and not rec["stop"]["before_usd10"]
    # break-even exit at 4000 in the 10:30 bar: the window ends there, and only that bar's low counts, capped at 4000
    it = rec["in_trade"]
    assert (it["mfe_usd"], it["mae_usd"], it["mfe_r"], it["mae_r"]) == (16.0, 2.0, 1.6, 0.2)
    assert it["ends"] == "exit price touched" and it["hours"] == round(20 / 60, 3)
    assert rec["exit"]["reason"] == "BE" and rec["exit"]["gross_r"] == 0.0 and rec["cost"]["model_r"] == 0.077
    assert rec["cost"]["measured_pts"] is None and rec["cost"]["status"].startswith("MODEL")
    # next-bar convention: the first bar opens at the fill price here, so the race is the same
    assert rec["next_open"]["entry"] == 4000.0 and rec["next_open"]["entry_shift_usd"] == 0.0
    assert rec["next_open"]["first_bar_gap_min"] == 0.0
    assert {k: v["result"] for k, v in rec["next_open"]["race"].items()} == {"usd10": "TARGET", "usd15": "TARGET", "usd20": "STOP_FIRST"}
    assert rec["bars"]["n"] == 4 and rec["fill_utc"] == "2026-11-17T10:15:00+00:00"


def test_next_bar_open_worse_than_the_fill(tmp_path):
    rows = [(4001.5,) + LONG_PATH[0][1:]] + LONG_PATH[1:]                       # the next bar opens $1.50 above the fill
    rec = TD.diagnose("15m", "h4", _trade(), TD.bars5(_store(tmp_path, rows, [])), evs=[])
    n = rec["next_open"]
    assert n["entry"] == 4001.5 and n["entry_shift_usd"] == 1.5                 # a worse price for a long
    assert n["race"]["usd10"] == {"result": "TARGET", "hours": 0.25, "price": 4011.5}   # 4011 at 10:20 is not enough
    assert n["race"]["usd15"]["result"] == "STOP_FIRST" and n["race_window"]["mfe_usd"] == 14.5
    assert rec["race"]["usd10"]["hours"] == round(10 / 60, 3)                   # the engine-fill race is unchanged


def test_a_signal_at_the_friday_close_fills_next_at_the_sunday_reopen(tmp_path):
    # the 15m bar 21:45-22:00 UTC on Fri 20 Nov closes the week; the next bar is Sunday 23:00 UTC (18:00 New York)
    fri = pd.Timestamp("2026-11-20T21:45:00Z")
    d = str(tmp_path / "store")
    pre = _bars([(3530, 3533, 3529, 3533)] * 3, start=fri)
    sun = _bars([(3533.05, 3577.4, 3533.05, 3576.1)] + [(3576, 3578, 3560, 3561)] * 30 + [(3561, 3562, 3519, 3520)],
                start=pd.Timestamp("2026-11-22T23:00:00Z"))
    store.save(d, "XAU/USD_5m", pd.concat([pre, sun]))
    t = _trade(entry_time="2026-11-20T21:45:00+00:00", exit_time="2026-11-22T23:15:00+00:00", entry=3533.0, sl=3520.0,
               tp1=3546.0, tp2=3553.0, exit_reason="FLIP", exit=3561.0, tp1_hit=True)
    rec = TD.diagnose("15m", "h4", t, TD.bars5(d), evs=[])
    n = rec["next_open"]
    assert n["first_bar_gap_min"] == 2940.0                   # 22:00 Fri to 23:00 Sun = 49 hours
    # the stale first print (3533.05, the Friday quote) is replaced by that bar's close, as the engine does
    assert n["entry"] == 3576.1 and n["entry_shift_usd"] == 43.1
    # from the Friday close every target is reached by the reopen bar; from the reopen, none is before the stop
    assert all(v["result"] == "TARGET" and v["hours"] == 49.083 for v in rec["race"].values())
    assert all(v["result"] == "STOP_FIRST" for v in n["race"].values()) and n["race_window"]["ends"] == "STOP"
    assert n["race_window"]["mfe_usd"] == 1.9                                  # 3578 - 3576.10: the gap is not counted
    assert TD.summary([rec])["h4|15m"]["next_open"]["filled_at_a_session_close"] == 1


def test_a_short_stopped_by_a_gap_and_the_shared_bar_rule(tmp_path):
    rows = [(4012, 4013, 4008, 4009)] + [(4009, 4010, 4005, 4006)] * 3
    t = _trade(dir="SHORT", sl=4010.0, tp1=3987.0, tp2=3980.0, exit=4012.0, exit_reason="SL_GAP",
               exit_time="2026-11-17T10:15:00+00:00", tp1_hit=False, gross_pts=-12.0, r=-1.277)
    rec = TD.diagnose("15m", "h4", t, TD.bars5(_store(tmp_path, rows, [t])), evs=[])
    assert all(v["result"] == "STOP_FIRST" for v in rec["race"].values())           # it opened beyond the stop
    assert rec["race_window"]["ends"] == "STOP" and rec["race_window"]["mfe_usd"] == 0.0
    assert rec["stop"]["before_usd10"] and rec["in_trade"]["mae_usd"] == 12.0 and rec["in_trade"]["mfe_usd"] == 0.0
    assert rec["next_open"]["entry_shift_usd"] == -12.0                             # a higher sell: better, but past the stop
    # one bar that reaches both +$10 and the stop is a stop
    rows2 = [(4000, 4011, 3989, 4005)] + [(4005, 4006, 4004, 4005)] * 3
    t2 = _trade(exit_reason="SL", exit=3990.0, exit_time="2026-11-17T10:15:00+00:00")
    rec2 = TD.diagnose("15m", "h4", t2, TD.bars5(_store(tmp_path / "b", rows2, [t2])), evs=[])
    assert rec2["race"]["usd10"]["result"] == "STOP_FIRST" and rec2["race_window"]["mfe_usd"] == 0.0


def test_every_target_first_the_record_is_final_and_a_later_stop_does_not_change_it(tmp_path):
    t = _trade(**TP2_TRADE)
    rec = TD.diagnose("15m", "h4", t, TD.bars5(_store(tmp_path / "a", ALL_TARGETS_PATH, [])), evs=[])
    assert all(v["result"] == "TARGET" for v in rec["race"].values()) and rec["race"]["tp2"]["hours"] == round(20 / 60, 3)
    assert rec["race_window"] == {"ends": "ALL_TARGETS", "bars": 4, "hours": round(20 / 60, 3), "mfe_usd": 21.0}
    assert rec["stop"] == {"hit": False, "hours": None, "before_usd10": False, "scope": "inside the race window"}
    # TP2 exit at 4020 in the 10:30 bar: that bar's high counts up to 4020, its low not at all
    assert (rec["in_trade"]["mfe_usd"], rec["in_trade"]["mae_usd"]) == (20.0, 1.0)
    crash = ALL_TARGETS_PATH + [(4019, 4019, 3980, 3985)] * 5                      # the stop, after every target
    rec2 = TD.diagnose("15m", "h4", t, TD.bars5(_store(tmp_path / "b", crash, [])), evs=[])
    for k in ("race", "race_window", "stop", "next_open", "in_trade", "exit", "bars"):
        assert rec[k] == rec2[k], k


def test_no_record_while_the_next_open_race_is_undecided(tmp_path):
    rows = [(4001.5,) + ALL_TARGETS_PATH[0][1:]] + ALL_TARGETS_PATH[1:]          # next open 4001.50: +$20 = 4021.50
    t = _trade(**TP2_TRADE)
    assert TD.diagnose("15m", "h4", t, TD.bars5(_store(tmp_path / "a", rows, [])), evs=[]) is None
    more = rows + [(4019, 4022, 4018, 4021)]                                       # 10:50 reaches 4021.50
    rec = TD.diagnose("15m", "h4", t, TD.bars5(_store(tmp_path / "b", more, [])), evs=[])
    assert rec["next_open"]["race"]["usd20"] == {"result": "TARGET", "hours": round(40 / 60, 3), "price": 4021.5}
    assert rec["next_open"]["race_window"]["ends"] == "ALL_TARGETS" and rec["race_window"]["bars"] == 4


def test_a_bar_that_opens_beyond_a_level_reaches_it_even_if_its_range_does_not(tmp_path):
    # a malformed vendor bar (open outside its high-low range): the open is a traded price and still counts
    up = [(4010.5, 4009.5, 4002, 4006)] + [(4006, 4007, 4005, 4006)] * 6 + [(4006, 4006, 3985, 3986)]   # then the stop
    rec = TD.diagnose("15m", "h4", _trade(), TD.bars5(_store(tmp_path / "a", up, [])), evs=[])
    assert rec["race"]["usd10"] == {"result": "TARGET", "hours": round(5 / 60, 3), "price": 4010.0}
    assert rec["race"]["usd15"]["result"] == "STOP_FIRST"
    down = [(3989.5, 3998, 3991, 3995)] + [(3995, 3996, 3994, 3995)] * 6
    rec = TD.diagnose("15m", "h4", _trade(), TD.bars5(_store(tmp_path / "b", down, [])), evs=[])
    assert rec["race_window"]["ends"] == "STOP" and rec["stop"]["hours"] == round(5 / 60, 3)


def test_no_record_before_the_race_is_decided_and_future_bars_do_not_change_it(tmp_path):
    drift = [(4000 + k * 0.1, 4000.5 + k * 0.1, 3999.5 + k * 0.1, 4000 + k * 0.1) for k in range(40)]
    t = _trade(exit_reason="FLIP", exit=4001.0, exit_time="2026-11-17T10:30:00+00:00", tp1_hit=False)
    assert TD.diagnose("15m", "h4", t, TD.bars5(_store(tmp_path, drift, [t])), evs=[]) is None     # undecided, horizon open
    rec = TD.diagnose("15m", "h4", _trade(), TD.bars5(_store(tmp_path / "a", LONG_PATH, [])), evs=[])
    later = LONG_PATH + [(3990, 4100, 3900, 4050)] * 20                                            # wild bars after the stop
    rec2 = TD.diagnose("15m", "h4", _trade(), TD.bars5(_store(tmp_path / "b", later, [])), evs=[])
    for k in ("race", "race_window", "stop", "next_open", "in_trade", "exit", "bars"):
        assert rec[k] == rec2[k], k


def test_the_still_forming_bar_is_not_read(tmp_path):
    d = _store(tmp_path, LONG_PATH, [_trade()])
    assert len(TD.bars5(d)["t"]) == 6
    assert len(TD.bars5(d, t_now=E0 + 29 * 60)["t"]) == 5             # 10:44: the 10:35 bar has closed, the 10:40 bar has not
    assert TD.bars5(d, t_now=E0 + 60) is None                         # nothing closed yet
    # the stop at 10:30 decides the race, but the 15m exit bar (10:30-10:45) is not all stored by 10:40: no record
    assert TD.diagnose("15m", "h4", _trade(), TD.bars5(d, t_now=E0 + 25 * 60), evs=[]) is None
    assert TD.diagnose("15m", "h4", _trade(), TD.bars5(d, t_now=E0 + 30 * 60), evs=[]) is not None
    # the stop bar (10:30) still forming at 10:33: nothing is written; once it has closed the record is
    assert TD.append(d, t_now=E0 + 18 * 60) == {"state": "ok", "appended": 0, "pending": 1, "closed_trades": 1}
    assert TD.append(d, t_now=LATER)["appended"] == 1


def test_written_once_never_rewritten_and_the_ledger_is_untouched(tmp_path):
    d = _store(tmp_path, LONG_PATH, [_trade()])
    led = os.path.join(d, "holdout", "15m_h4.json")
    before = _read(led, "rb")
    assert TD.append(d, t_now=LATER)["appended"] == 1
    assert TD.append(d, t_now=LATER + 300)["appended"] == 0
    store.save(d, "XAU/USD_5m", _bars([(4000, 4030, 3999, 4025)] * 6))                            # a later bar revision
    assert TD.append(d, t_now=LATER + 600)["appended"] == 0
    rows = TD.read_dir(os.path.join(d, TD.DIR))
    assert len(rows) == 1 and rows[0]["race"]["usd10"]["hours"] == round(10 / 60, 3)
    assert rows[0]["logged_utc"] == "2026-11-18T10:15:00Z" and set(rows[0]["versions"]) == {"trade_diag_sha", "github_sha"}
    assert _read(led, "rb") == before
    assert rows[0]["trade_sha256"] == TD.sha(_trade())
    assert os.listdir(os.path.join(d, TD.DIR)) == ["2026-11-18.jsonl"]
    dst = str(tmp_path / "ledger")
    assert TD.merge_ledger(os.path.join(d, TD.DIR), dst) == {"added": 1}
    assert TD.merge_ledger(os.path.join(d, TD.DIR), dst) == {"added": 0}
    assert TD.read_dir(dst) == rows


def test_open_trades_archives_and_manifests_are_skipped(tmp_path):
    d = _store(tmp_path, LONG_PATH, [_trade(), _trade(entry_time="2026-11-17T10:15:00+00:00", open=True)])
    for name in ("manifest.json", "15m_h4_old.json"):
        with open(os.path.join(d, "holdout", name), "w") as f:
            json.dump([_trade()], f)
    os.makedirs(os.path.join(d, "holdout", "archive"))
    with open(os.path.join(d, "holdout", "archive", "15m_h4.json"), "w") as f:
        json.dump([_trade()], f)
    assert [(tf, arm) for tf, arm, _ in TD.ledger_trades(d)] == [("15m", "h4")]


def test_a_malformed_trade_is_reported_and_never_blocks_the_others(tmp_path):
    bad = _trade(entry_time="2026-11-17T10:15:00+00:00")
    del bad["sl"]
    d = _store(tmp_path, LONG_PATH, [_trade(), bad])
    r = TD.append(d, t_now=LATER)
    assert r["state"] == "errors" and r["appended"] == 1 and r["n_errors"] == 1
    assert r["errors"][0]["key"] == "15m|h4|2026-11-17T10:15:00+00:00|LONG" and "KeyError" in r["errors"][0]["error"]
    assert TD.main(["--append", d, "--now", "2026-11-18T10:15:00Z"]) == 1                     # a warning on the run


def test_news_classification_by_hand():
    fill = E0
    evs = [{"t": fill - 86400 * 3, "name": "FOMC"}, {"t": fill + 20 * 60, "name": "CPI"}, {"t": fill + 86400 * 30, "name": "NFP"}]
    n = TD.news(fill, fill + 3600, evs)
    assert n["covered"] and n["news_day"] and n["events_that_day"] == ["CPI"] and n["event_in_trade"] == ["CPI"]
    assert n["fill_in_window"] == ["CPI"] and n["nearest_event_min"] == 20.0 and n["nearest_event"] == "CPI"
    assert "only" in n["scope"]
    quiet = TD.news(fill + 86400 * 10, fill + 86400 * 10 + 3600, evs)
    assert not quiet["news_day"] and quiet["nearest_event_min"] is None and quiet["covered"]
    assert not TD.news(fill - 86400 * 40, fill - 86400 * 40 + 60, evs)["covered"]                # before the calendar
    # the New York day, not the UTC day: 02:00 UTC on the 18th is still the 17th in New York
    late = int(pd.Timestamp("2026-11-18T02:00:00Z").timestamp())
    assert TD.news(late, late + 60, evs)["events_that_day"] == ["CPI"]


def test_wilson_and_summary(tmp_path):
    assert TD.wilson(0, 0) is None and TD.wilson(5, 10) == [0.2366, 0.7634]
    a = TD.diagnose("15m", "h4", _trade(), TD.bars5(_store(tmp_path / "a", LONG_PATH, [])), evs=[])
    b = TD.diagnose("15m", "h4", _trade(**TP2_TRADE), TD.bars5(_store(tmp_path / "b", ALL_TARGETS_PATH, [])), evs=[])
    s = TD.summary([a, b])["h4|15m"]
    assert s["n"] == 2 and s["usd10"]["target_first"] == 2 and s["usd10"]["rate"] == 1.0
    assert s["usd20"] == {"target_first": 1, "decided": 2, "undecided": 0, "rate": 0.5, "wilson95": TD.wilson(1, 2),
                          "median_hours": round(20 / 60, 3)}
    assert s["race_window_ends"] == {"ALL_TARGETS": 1, "STOP": 1} and s["exit_reasons"] == {"BE": 1, "TP2": 1}
    assert s["next_open"]["usd15"]["rate"] == 1.0 and s["cost_measured"] == 0 and s["news"]["covered"] == 0
    md = TD.markdown(TD.summary([a, b])).splitlines()
    assert len(md) == 3 and md[2].startswith("| h4 · 15m | 2 | 1.00 [") and md[2].count("|") == 11


def _random_case(rng, n=120):
    """A random 5-minute path inside one London / New York day (no session break) and a ledger trade on it: an SL exit
    at the original stop when the path reaches it, otherwise a FLIP at a 15-minute close."""
    c = 4000 + np.cumsum(rng.normal(0, 1.5, n))
    o = np.r_[c[0] + rng.normal(0, 0.3), c[:-1]]
    h, lo = np.maximum(o, c) + rng.exponential(1.0, n), np.minimum(o, c) - rng.exponential(1.0, n)
    long = bool(rng.integers(0, 2))
    s = 1 if long else -1
    e = float(np.round(c[0] - rng.normal(0, 0.3), 3))
    sl = float(np.round(e - s * rng.uniform(6, 20), 3))
    stop = (lo <= sl) | (o <= sl) if long else (h >= sl) | (o >= sl)
    k = int(np.flatnonzero(stop)[0]) if stop.any() else None
    if k is not None and k < n - 3:
        q = k // 3
        reason, xp = ("SL_GAP", float(o[k])) if (o[k] <= sl if long else o[k] >= sl) else ("SL", sl)
    else:
        q = int(rng.integers(1, n // 3 - 1))
        reason, xp = "FLIP", float(c[3 * q + 2])
    t = _trade(dir="LONG" if long else "SHORT", entry=e, sl=sl, tp1=float(e + s * 13), tp2=float(e + s * 20),
               exit_reason=reason, exit=round(xp, 3), tp1_hit=False,
               exit_time=(T0 + pd.Timedelta(minutes=15 * q)).isoformat())
    return list(zip(o, h, lo, c, strict=True)), t


@pytest.mark.parametrize("seed", range(40))
def test_agrees_with_the_independent_checker_on_random_paths(tmp_path, seed):
    rows, t = _random_case(np.random.default_rng(seed))
    d = _store(tmp_path, rows, [t])
    got = TD.append(d, t_now=LATER)
    out = CHK.check(d, os.path.join(d, TD.DIR))
    assert out["records"] == got["appended"]
    assert out["disagree"] == 0 and out["reopen_only"] == 0 and out["ledger_changed"] == 0, out["details"]
    assert out["agree"] == out["records"]


def test_the_checker_catches_a_wrong_record_and_a_changed_trade(tmp_path):
    d = _store(tmp_path, LONG_PATH, [_trade()])
    TD.append(d, t_now=LATER)
    f = os.path.join(d, TD.DIR, "2026-11-18.jsonl")
    good = json.loads(_read(f))
    for mutate, want in ((lambda r: r["race"]["usd15"].update(result="STOP_FIRST", hours=None), "disagree"),
                         (lambda r: r["race_window"].update(mfe_usd=19.0), "disagree"),
                         (lambda r: r["next_open"]["race"]["usd10"].update(hours=0.5), "disagree"),
                         (lambda r: r["in_trade"].update(mae_usd=5.0), "disagree"),
                         (lambda r: r["stop"].update(hit=False), "disagree"),
                         (lambda r: r.update(trade_sha256="0" * 64), "ledger_changed")):
        bad = json.loads(json.dumps(good))
        mutate(bad)
        with open(f, "w") as fh:
            fh.write(json.dumps(bad) + "\n")
        out = CHK.check(d, os.path.join(d, TD.DIR))
        assert out[want] == 1 and out["agree"] == 0, (want, out)
    assert CHK.main(["--store", d]) == 1


ROOT = os.path.join(os.path.dirname(__file__), "..")


def test_wired_after_the_pipeline_before_the_store_is_saved_and_merged_into_the_ledger():
    wf = _read(os.path.join(ROOT, ".github", "workflows", "quantum-site.yml"))
    a = wf.index("python -m quantum.trade_diag --append store")
    assert wf.index("python -m quantum.outcomes --append store") < a < wf.index("- name: Save the market-data store")
    m = wf.index("python -m quantum.trade_diag --merge-ledger store/trade_diag ledger/trade_diag")
    assert wf.index("- name: Save the forward ledger") < m < wf.index('git commit -q -m "forward ledger')
    assert "::warning title=trade diagnostics::append failed" in wf          # a failure never stops the saves


def test_outside_the_engine_and_read_by_nothing_in_production():
    from quantum import holdout
    assert "trade_diag.py" not in holdout.ENGINE_SOURCES
    for root, _, files in os.walk(os.path.join(ROOT, "quantum")):
        for fn in files:
            if fn.endswith(".py") and fn != "trade_diag.py" and "__pycache__" not in root:
                assert "trade_diag" not in _read(os.path.join(root, fn)), fn


def test_the_g4_document_is_what_the_evidence_gives():
    """docs/final_audit/G4_TRADE_DIAGNOSTICS.md: its results block is generated from the committed evidence files."""
    import g4_doc
    assert g4_doc.main(["--check"]) == 0
