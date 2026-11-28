"""quantum/manual_ledger.py (mandate 2026-11-28, Parts 9, 12-17, 21): append-only hash chain, the Part 13 states and the
one-trade-at-a-time rule, execution and closure only from the operator or a broker record, corrections as separate lines,
the Part 15 populations, the Part 21 phone text, the C1 import, export, snapshot and reconciliation. Fixtures are built by
hand (test fixtures, never production records); every expected number is worked out in the comments."""
import json
import os
import re

import pytest

from quantum import holdout
from quantum import manual_ledger as M

T0 = "2026-11-30T10:15:00Z"           # a Monday, 15:15 PKT


def plan(**over):
    p = {"t_gen": T0, "price_at_gen": 4000.0, "data_ts": T0, "direction": "BUY", "setup": "Engine signal + C1 15m confirmation",
         "tf": "15m", "entry": 4000.0, "sl": 3987.0, "tp1": 4013.0, "tp2": 4020.0, "tp3": None, "rr": 1.1, "spread": 0.5,
         "commission_est": 0.07, "slippage_est": 0.4, "max_entry_dev": 3.9, "confirmation": "15M close",
         "invalidation": "stop 3987.0", "expiry_utc": "2026-11-30T10:35:00Z", "reason": "hand-built test signal", "actionable": True}
    p.update(over)
    return p


def execd(**over):
    e = {"fill": 4000.5, "t_fill": "2026-11-30T10:17:00Z", "lot": 0.46, "sl_actual": 3987.0, "evidence": "MT5 screenshot 1", "ticket": "111"}
    e.update(over)
    return e


def closed(**over):
    c = {"exit_px": 4013.0, "t_exit": "2026-11-30T11:02:00Z", "outcome": "TP1", "pl_gross": 575.0, "commission": -6.44, "swap": 0.0,
         "evidence": "MT5 history row"}
    c.update(over)
    return c


def gen(path, **over):
    return M.append(path, "GENERATED", plan(**over), "user", t=over.get("t_gen", T0))


def text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def sig(path, sid):
    return M.replay(M.read(path))["signals"][sid]


@pytest.fixture
def L(tmp_path):
    return str(tmp_path / "manual" / "ledger.jsonl")


def test_ids_sequence_and_chain(L):
    a, b = gen(L), gen(L, direction="SELL", sl=4013.0, tp1=3987.0, tp2=3980.0, invalidation="stop 4013.0")
    assert (a["signal_id"], b["signal_id"]) == ("Q-0001", "Q-0002") and (a["seq"], b["seq"]) == (1, 2)
    assert a["prev"] == M.GENESIS and b["prev"] == a["hash"]
    assert M.verify(L) == {"ok": True, "lines": 2, "problems": []}
    assert sig(L, "Q-0001")["state"] == "AWAITING_USER_CONFIRMATION"


@pytest.mark.parametrize("damage", ["edit", "edit_rehash", "delete", "reorder", "insert"])
def test_tampering_is_detected_and_blocks_appends(L, damage):
    gen(L)
    gen(L)
    gen(L)
    with open(L) as f:
        lines = f.read().splitlines()
    if damage == "edit":
        r = json.loads(lines[0])
        r["data"]["entry"] = 3990.0
        lines[0] = json.dumps(r)
    elif damage == "edit_rehash":              # the edited line re-hashed to look consistent: only the next line's prev catches it
        r = json.loads(lines[0])
        r["data"]["entry"] = 3990.0
        r["hash"] = M._digest(r)
        lines[0] = json.dumps(r)
        assert M.chain_problems([json.loads(x) for x in lines]) == ["line 2: prev does not match line 1's hash: the chain is broken"]
    elif damage == "delete":
        del lines[1]
    elif damage == "reorder":
        lines[1], lines[2] = lines[2], lines[1]
    else:
        lines.insert(1, lines[1])
    with open(L, "w") as f:
        f.write("\n".join(lines) + "\n")
    v = M.verify(L)
    assert not v["ok"] and v["problems"]
    with pytest.raises(M.LedgerError, match="integrity"):
        gen(L)


def test_the_five_events_stay_apart_and_the_lifecycle_closes_the_slot(L):
    gen(L)
    M.append(L, "ACCEPTED", {}, "user", "Q-0001", t="2026-11-30T10:16:00Z")
    s = sig(L, "Q-0001")
    assert s["state"] == "AWAITING_USER_CONFIRMATION" and s["accepted"] and s["execution"] is None
    M.append(L, "EXECUTED", execd(), "user", "Q-0001", t="2026-11-30T10:17:30Z")
    st = M.replay(M.read(L))
    assert st["slot"] == "Q-0001" and st["signals"]["Q-0001"]["state"] == "TRADE_OPEN"
    M.append(L, "CLOSED", closed(), "user", "Q-0001", t="2026-11-30T11:03:00Z")
    st = M.replay(M.read(L))
    assert st["slot"] is None and st["signals"]["Q-0001"]["state"] == "TRADE_CLOSED"
    M.append(L, "VERIFIED", {"evidence": "statement 30 Nov", "pl_net": 568.56}, "mt5", "Q-0001", t="2026-12-01T09:00:00Z")
    v = M.view(sig(L, "Q-0001"))
    # net 575 - 6.44 = 568.56; slippage (4000.5 - 4000) x +1 = +0.5 (adverse); |fill - entry| 0.5 <= 3.9: not deviated
    # holding 10:17 -> 11:02 = 2700 s; R on price (4013 - 4000.5) / 13.5 = 0.926; R:R from the fill |4013 - 4000.5| / 13.5 = 0.93
    assert v["pl_net"] == 568.56 and v["slippage_adverse"] == 0.5 and not v["execution_deviated"] and v["holding_sec"] == 2700
    assert v["r_price"] == 0.926 and v["rr_actual"] == 0.93 and v["verified"] and not v["verified_mismatch"] and v["r_net"] is None
    assert M.verify(L)["ok"]


def test_one_trade_at_a_time_blocks_and_records_new_signals(L):
    gen(L)
    M.append(L, "EXECUTED", execd(), "user", "Q-0001")
    b = gen(L)                                         # a new actionable signal while Q-0001 is open
    assert b["data"]["blocked_by"] == "Q-0001"
    s2 = sig(L, "Q-0002")
    assert s2["state"] == "SIGNAL_CANCELLED" and s2["blocked"] and s2["cancel_reason"] == "BLOCKED_OPEN_TRADE"
    with pytest.raises(M.LedgerError, match="only a signal awaiting confirmation"):
        M.append(L, "EXECUTED", execd(ticket="222"), "user", "Q-0002")
    M.append(L, "CLOSED", closed(), "user", "Q-0001")
    q3 = gen(L)                                        # the slot is free again
    assert q3["signal_id"] == "Q-0003" and "blocked_by" not in q3["data"] and sig(L, "Q-0003")["state"] == "AWAITING_USER_CONFIRMATION"
    st = M.stats(L)
    assert st["blocked"] == 1 and st["populations"]["4_executed"]["n"] == 1 and st["populations"]["2_qualified"]["n"] == 3
    assert M.notification(sig(L, "Q-0002"), T0) == ["XAUUSD | NO TRADE", "Reason: blocked: one trade is already open"]


def test_a_second_open_trade_is_refused(L):
    gen(L)
    gen(L)
    M.append(L, "EXECUTED", execd(), "user", "Q-0001")
    with pytest.raises(M.LedgerError):
        M.append(L, "EXECUTED", execd(), "user", "Q-0002")


@pytest.mark.parametrize("src", ["c1:5", "bars:XAU_USD_5m", "ledger", "engine"])
def test_execution_and_closure_are_never_inferred(L, src):
    gen(L)
    with pytest.raises(M.LedgerError, match="never inferred"):
        M.append(L, "EXECUTED", execd(), src, "Q-0001")
    M.append(L, "EXECUTED", execd(), "user", "Q-0001")
    with pytest.raises(M.LedgerError, match="never inferred"):
        M.append(L, "CLOSED", closed(), src, "Q-0001")


def test_execution_needs_evidence_and_a_stop_on_the_right_side(L):
    gen(L)
    with pytest.raises(M.LedgerError, match="needs"):
        M.append(L, "EXECUTED", execd(evidence=""), "user", "Q-0001")
    with pytest.raises(M.LedgerError, match="wrong side"):
        M.append(L, "EXECUTED", execd(sl_actual=4005.0), "user", "Q-0001")
    with pytest.raises(M.LedgerError, match="only an open trade"):
        M.append(L, "CLOSED", closed(), "user", "Q-0001")


def test_a_theoretical_stop_does_not_close_anything(L):
    gen(L)
    M.append(L, "EXECUTED", execd(), "user", "Q-0001")
    M.append(L, "OUTCOME", {"sl_hit": True, "reached": {}, "targets": {}, "mfe": 1.0, "mae": 13.0, "t_sl": T0}, "bars:test", "Q-0001")
    assert sig(L, "Q-0001")["state"] == "TRADE_OPEN" and M.replay(M.read(L))["slot"] == "Q-0001"


def test_expiry(L):
    gen(L)
    with pytest.raises(M.LedgerError, match="not before"):
        M.append(L, "EXPIRED", {}, "ledger", "Q-0001", t="2026-11-30T10:30:00Z")
    assert [r["signal_id"] for r in M.expire_due(L, "2026-11-30T10:34:59Z")] == []
    assert [r["signal_id"] for r in M.expire_due(L, "2026-11-30T10:35:00Z")] == ["Q-0001"]
    assert sig(L, "Q-0001")["state"] == "SIGNAL_EXPIRED"
    with pytest.raises(M.LedgerError):
        M.append(L, "EXECUTED", execd(), "user", "Q-0001")


def test_a_late_execution_is_recorded_and_flagged(L):
    gen(L)
    M.append(L, "EXECUTED", execd(fill=4006.0, t_fill="2026-11-30T10:40:00Z"), "user", "Q-0001")
    v = M.view(sig(L, "Q-0001"))
    assert v["after_expiry"] and v["execution_deviated"] and v["slippage_adverse"] == 6.0   # 6.0 > 3.9 allowed


@pytest.mark.parametrize("over,msg", [({"tp2": None}, "missing: tp2"), ({"sl": 4001.0}, "out of order"),
                                      ({"max_entry_dev": 0.0}, "maximum entry deviation"), ({"expiry_utc": T0}, "expiry"),
                                      ({"spread": None}, "missing: spread")])
def test_an_incomplete_or_inconsistent_plan_cannot_be_actionable(L, over, msg):
    with pytest.raises(M.LedgerError, match=msg):
        gen(L, **over)
    assert M.read(L) == []


def test_a_non_actionable_signal_needs_its_reason(L):
    with pytest.raises(M.LedgerError, match="reason"):
        M.append(L, "GENERATED", {"direction": "BUY", "actionable": False}, "user")
    M.append(L, "GENERATED", {"direction": "BUY", "actionable": False, "t_gen": T0, "reason": "HTF conflict"}, "user")
    s = sig(L, "Q-0001")
    assert s["state"] == "SIGNAL_GENERATED"
    assert M.notification(s, T0) == ["XAUUSD | NO TRADE", "Reason: HTF conflict"]


def test_corrections_are_separate_lines(L):
    gen(L)
    ex = M.append(L, "EXECUTED", execd(), "user", "Q-0001")
    first = text(L).splitlines()
    with pytest.raises(M.LedgerError, match="evidence"):
        M.append(L, "CORRECTION", {"target_seq": ex["seq"], "field": "fill", "value": 4001.0, "reason": "typo"}, "user", "Q-0001")
    with pytest.raises(M.LedgerError, match="reason"):
        M.append(L, "CORRECTION", {"target_seq": ex["seq"], "field": "fill", "value": 4001.0, "evidence": "x"}, "user", "Q-0001")
    with pytest.raises(M.LedgerError, match="no correctable line"):
        M.append(L, "CORRECTION", {"target_seq": 99, "field": "fill", "value": 1, "reason": "r"}, "user", "Q-0001")
    with pytest.raises(M.LedgerError):
        M.append(L, "CORRECTION", {"target_seq": 1, "field": "blocked_by", "value": "Q-9", "reason": "r"}, "user", "Q-0001")
    M.append(L, "CORRECTION", {"target_seq": ex["seq"], "field": "fill", "value": 4001.0, "reason": "typed 4000.5, MT5 shows 4001.0",
                               "evidence": "MT5 trade tab"}, "user", "Q-0001")
    assert text(L).splitlines()[:2] == first          # the corrected line is untouched
    s = sig(L, "Q-0001")
    assert s["execution"]["fill"] == 4001.0 and s["corrections"][0]["old"] == 4000.5 and M.view(s)["slippage_adverse"] == 1.0
    assert M.verify(L)["ok"]


def test_outcome_from_bars_by_hand():
    p = plan()                                           # BUY 4000, stop 3987 (risk 13), TP1 4013, TP2 4020
    t = M.utc(T0).timestamp()
    rows = [(t - 300, 3990, 4100, 3900, 4000),           # before the signal: ignored
            (t, 4000, 4005, 3995, 4002),                 # fav 5, adv 5
            (t + 300, 4002, 4011, 3999, 4010),           # fav 11: +$10 at close t+600
            (t + 600, 4010, 4016, 4004, 4015),           # fav 16: +$15 and TP1 (13) at t+900
            (t + 900, 4015, 4021, 3986, 3990)]           # touches 4021 and the stop (adv 14): the stop
    o = M.outcome_from_bars(p, rows, 300)
    assert o["sl_hit"] and o["t_sl"] == M.iso(t + 1200) and o["bars"] == 4
    assert o["reached"] == {"10": M.iso(t + 600), "15": M.iso(t + 900), "20": None}
    assert o["targets"] == {"tp1": M.iso(t + 900), "tp2": None} and o["mfe"] == 16.0 and o["mae"] == 14.0
    assert M.outcome_from_bars(p, rows[:3], 300) is None             # undecided: neither the stop nor the window's end
    calm = [(t + 300 * i, 4000, 4004, 3996, 4000) for i in range(int(M.HOLD_SEC / 300))]
    o = M.outcome_from_bars(p, calm, 300)
    assert o is not None and not o["sl_hit"] and o["reached"]["10"] is None and o["mfe"] == 4.0 and o["bars"] == len(calm)


@pytest.mark.parametrize("first", ["datetime", ""])           # the XAU/USD store names its time column, the GC=F store does not
def test_bars_are_read_from_a_store_directory_whatever_the_time_column_is_called(tmp_path, first):
    d = tmp_path / "XAU_USD_5m"
    d.mkdir()
    (d / "2026-11.csv").write_text(f"{first},open,high,low,close,volume\n2026-11-30 10:20:00+00:00,4000,4005,3995,4002,0\n"
                                   "2026-11-30 10:15:00+00:00,3999,4001,3998,4000,0\n")
    rows, sec = M.read_bars(str(d))
    assert sec == 300 and rows[0] == (M.utc(T0).timestamp(), 3999.0, 4001.0, 3998.0, 4000.0) and len(rows) == 2


def test_the_five_populations_and_the_actual_statistics_by_hand(L):
    M.append(L, "GENERATED", {"direction": "SELL", "actionable": False, "t_gen": T0, "reason": "weak confirmation"}, "user")  # Q-0001
    gen(L)                                                                                   # Q-0002: accepted, never executed
    M.append(L, "ACCEPTED", {}, "user", "Q-0002")
    M.expire_due(L, "2026-11-30T10:40:00Z")
    for i, (pl, out) in enumerate(((-50.0, "SL"), (100.0, "TP1"), (-30.0, "SL")), 3):        # Q-0003..5: executed and closed
        gen(L)
        M.append(L, "ACCEPTED", {}, "user", f"Q-{i:04d}")
        M.append(L, "EXECUTED", execd(ticket=str(i)), "user", f"Q-{i:04d}")
        M.append(L, "CLOSED", closed(pl_gross=pl, commission=0.0, swap=0.0, outcome=out), "user", f"Q-{i:04d}")
    st = M.stats(L)
    P = st["populations"]
    assert [P[k]["n"] for k in ("1_generated", "2_qualified", "3_accepted", "4_executed", "5_closed_executed")] == [5, 4, 4, 3, 3]
    a = P["5_closed_executed"]["actual"]
    # nets -50, +100, -30: win 1/3, loss 2/3; PF 100 / 80 = 1.25; equity -50, 50, 20 from 0: drawdown 50 (0 -> -50), the
    # later 50 -> 20 is 30; the losses are not consecutive, so the longest losing streak is 1
    assert a["win"]["k"] == 1 and a["loss"]["k"] == 2 and a["profit_factor"] == 1.25 and a["max_drawdown"] == 50.0
    assert a["max_consecutive_losses"] == 1 and a["net_total"] == 20.0 and a["tp_first_vs_sl_first"] == {"tp": 1, "sl": 2, "tp_share": M._rate(1, 3)}
    assert a["status"] == "INSUFFICIENT EVIDENCE" and a["by_tf"]["15m"]["n"] == 3
    assert st["states"]["SIGNAL_EXPIRED"] == 1 and st["states"]["SIGNAL_GENERATED"] == 1
    assert M.wilson(1, 3) == [0.0615, 0.7923]


def test_phone_text_follows_part_21(L):
    gen(L)
    s = sig(L, "Q-0001")
    # 10:35 UTC = 15:35 PKT (UTC+5)
    assert M.notification(s, "2026-11-30T10:20:00Z") == [
        "XAUUSD BUY | Signal ID: Q-0001", "Entry: 4000.0", "SL: 3987.0 | TP1: 4013.0", "TP2: 4020.0 | RR: 1.1",
        "Confirm: 15M close", "Expiry: 15:35 PKT", "Status: WAITING FOR EXECUTION"]
    assert M.notification(s, "2026-11-30T10:35:00Z") == ["XAUUSD | NO TRADE", "Reason: signal expired"]
    M.append(L, "CANCELLED", {"reason": "ENTRY_MISSED"}, "user", "Q-0001")
    assert M.notification(sig(L, "Q-0001"), "2026-11-30T10:20:00Z") == ["XAUUSD BUY | Signal ID: Q-0001", "ENTRY MISSED — DO NOT CHASE"]


def _c1_index():
    t = int(M.utc("2026-11-20T16:15:00Z").timestamp())
    conf = {"t": t + 900, "px": 3541.53, "move": 14.82, "tier": "MINIMUM", "now": {"px": 3545.74, "t_px": t + 1300, "live": True}}
    pl = {"entry": 3541.53, "sl": 3554.53, "tp1": 3528.53, "tp2": 3521.53, "lot": 0.46, "rr_net": 1.1117, "budget": 650.0,
          "cost_parts": {"spread": 0.5, "slippage": 0.4, "commission": 0.07}}
    recent = [{"id": 6, "tf": "15m", "dir": -1, "p0": 3556.35, "t_close": t, "status": "TP2", "conf": conf, "plan": pl, "why": "TP2 reached", "t_done": t + 9000},
              {"id": 7, "tf": "15m", "dir": -1, "p0": 3608.09, "t_close": t + 86400, "status": "INVALIDATED", "conf": None, "plan": None,
               "why": "price traded $13 against the reference before confirmation", "t_done": t + 90000},
              {"id": 8, "tf": "15m", "dir": 1, "p0": 3600.0, "t_close": t + 90000, "status": "EXPIRED", "conf": None, "plan": None,
               "why": "no confirming close within 96 bars", "t_done": t + 176400},
              {"id": 9, "tf": "15m", "dir": 1, "p0": 3610.0, "t_close": t + 100000, "status": "ACTIVE", "conf": conf,
               "plan": {**pl, "cost_parts": {}}, "why": "ENTRY ELIGIBLE"}]
    return {"alerts": {"plans": {"late_frac": 0.3},
                       "c1": {"on": True, "min_usd": 10.0, "inv_usd": 13.0, "fresh_sec": 1200, "recent": recent,
                              "open": [{"id": 10, "tf": "15m", "dir": 1, "p0": 3620.0, "t_close": t + 200000, "status": "PENDING"}]}}}


def test_import_c1_records_each_setup_once_with_the_published_fields_only(L):
    recs = M.import_c1(L, _c1_index(), now="2026-11-30T12:00:00Z")
    assert [(r["kind"], r["signal_id"], r["source"]) for r in recs] == [
        ("GENERATED", "Q-0001", "c1:6"), ("GENERATED", "Q-0002", "c1:7"), ("CANCELLED", "Q-0002", "c1:7"),
        ("GENERATED", "Q-0003", "c1:8"), ("EXPIRED", "Q-0003", "c1:8"), ("GENERATED", "Q-0004", "c1:9"), ("CANCELLED", "Q-0004", "c1:9")]
    p = sig(L, "Q-0001")["plan"]
    # max entry deviation = late_frac 0.3 x stop |3541.53 - 3554.53| = 3.9; expiry = confirming close + fresh_sec 1200
    assert p["actionable"] and p["max_entry_dev"] == 3.9 and p["direction"] == "SELL" and p["rr"] == 1.1117
    assert p["expiry_utc"] == M.iso(M.utc(p["t_gen"]).timestamp() + 1200) and p["htf_alignment"].startswith("UNAVAILABLE")
    assert sig(L, "Q-0001")["state"] == "AWAITING_USER_CONFIRMATION"          # the alert record's TP2 is not a trade
    assert sig(L, "Q-0002")["cancel_reason"] == "INVALIDATED" and sig(L, "Q-0003")["state"] == "SIGNAL_EXPIRED"
    q4 = sig(L, "Q-0004")                       # confirmed, but its cost split is missing: never actionable
    assert not q4["plan"]["actionable"] and "missing: spread, commission_est, slippage_est" in q4["plan"]["reason"]
    assert M.import_c1(L, _c1_index(), now="2026-11-30T12:15:00Z") == []      # idempotent; the PENDING setup waits
    assert M.verify(L)["ok"]


def test_export_is_reproducible_and_carries_the_part_14_fields(L):
    gen(L)
    M.append(L, "EXECUTED", execd(), "user", "Q-0001")
    M.append(L, "CLOSED", closed(), "user", "Q-0001")
    a, b = M.export_csv(L), M.export_csv(L)
    assert a == b and a.splitlines()[0] == ",".join(M.EXPORT)
    row = M.export_rows(L)[0]
    assert row["t_gen_pkt"] == "2026-11-30 15:15 PKT" and row["fill"] == 4000.5 and row["pl_net"] == 568.56 and row["risk_price"] == 13.0
    for f in ("signal_id", "instrument", "direction", "setup", "tf", "entry", "fill", "sl", "sl_actual", "tp1", "spread", "spread_exec",
              "commission", "slippage_adverse", "risk_money", "state", "outcome", "pl_gross", "swap", "pl_net", "holding_sec",
              "evidence_exec", "evidence_close"):
        assert f in M.EXPORT, f


def test_the_site_snapshot_shows_no_fill_no_profit_no_balance(L):
    gen(L)
    M.append(L, "EXECUTED", execd(), "user", "Q-0001")
    s = M.snapshot(L)
    assert s["state"] == "TRADE_OPEN" and s["open"] == {"signal_id": "Q-0001", "side": "BUY"} and s["integrity_ok"]
    txt = json.dumps(s)
    assert not re.search(r"fill|pl_|profit|lot|balance|4000\.5", txt)


def _broker(tmp_path, rows):
    p = tmp_path / "history.csv"
    p.write_text("Time,Position,Symbol,Type,Volume,Price,Close Time,Close Price,Commission,Swap,Profit\n" + "\n".join(rows) + "\n")
    return str(p)


def test_reconcile_is_read_only_and_never_assumes_the_server_clock(L, tmp_path):
    gen(L)
    M.append(L, "EXECUTED", execd(ticket=None), "user", "Q-0001")
    M.append(L, "CLOSED", closed(), "user", "Q-0001")
    before = text(L)
    # server time = UTC + 2: 10:17 UTC fill is 12:17 on the server
    csv = _broker(tmp_path, ["2026.11.30 12:17:20,111,XAUUSD,buy,0.46,4000.5,2026.11.30 13:02:00,4013.0,-6.44,0,575",
                             "2026.11.30 14:00:00,112,XAUUSD,sell,0.46,4010.0,2026.11.30 14:30:00,4005.0,-6.44,0,230",
                             "2026.11.30 14:00:00,113,EURUSD,buy,1,1.09,2026.11.30 14:30:00,1.10,-7,0,100"])
    off = M.reconcile(L, csv)
    assert off["time_matching"].startswith("off") and off["ledger_only"] == ["Q-0001"] and not off["ok"]
    on = M.reconcile(L, csv, server_utc_offset_h=2)
    assert on["matched"] == [{"signal_id": "Q-0001", "ticket": "111", "differences": {}}] and on["broker_only"] == ["112"]
    assert not on["ok"] and text(L) == before


def test_command_line_record_and_verify(L, capsys):
    gen(L)
    assert M.main(["record", "--ledger", L, "--kind", "ACCEPTED", "--signal", "Q-0001", "--source", "user"]) == 0
    assert M.main(["record", "--ledger", L, "--kind", "EXECUTED", "--signal", "Q-0001", "--source", "c1:1", "--data", json.dumps(execd())]) == 2
    assert "REFUSED" in capsys.readouterr().err
    assert M.main(["verify", "--ledger", L]) == 0
    with open(L, "a") as f:
        f.write('{"seq": 9}\n')
    assert M.main(["verify", "--ledger", L]) == 1


def test_nothing_in_production_imports_the_ledger_and_it_is_not_an_engine_source():
    root = os.path.dirname(M.__file__)
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith(".py") and f != "manual_ledger.py":
                with open(os.path.join(dirpath, f), encoding="utf-8") as fh:
                    assert "manual_ledger" not in fh.read(), f
    assert "manual_ledger.py" not in holdout.ENGINE_SOURCES
