"""The phone's daily / weekly validation separates the 15m timeframe the phone receives from the 30m / 1h / 4h records
that stay on the website (operator approval 2026-11-13, audit F-05). Wording only: the records, the plans, the website's
validation block and every other line are unchanged.

tests/conftest.py runs every test in "quality" mode; the production default, "sixty", is set here explicitly."""
import copy
import json
import os
from datetime import datetime, timezone

import pytest

from quantum import notify as N

SPLIT = " — 15m (your phone's timeframe)"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("PLAN", "PLAN_LOT", "PLAN_SL_USD", "PLAN_TP_USD", "PLAN_COST_PER_LOT", "MT5_PRICE_OFFSET", "ALERT_LIQUIDITY",
              "PLAN_LATE_FRAC", "ALERT_MODE", "NTFY_TOPIC", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK_URL"):
        monkeypatch.delenv(k, raising=False)                     # ALERT_MODE unset: sixty, the production default
    monkeypatch.setenv("ALERT_STRUCTURE", "0")
    monkeypatch.setenv("PLAN_TP2_USD", "0")


def _rec(tf, res, t=1794495600):                                 # 2026-11-12 12:00 UTC, a Thursday
    e = 4000.0
    return {"tf": tf, "t": t, "t_dec": t + N.TF_SEC[tf], "dir": 1, "entry": e, "sl": e - 13, "tp": e + 13, "sl_usd": 650.0,
            "tp_usd": 650.0, "lot": 0.5, "result": res, "session": "London", "dow": "Thu", "mfe": 0.0, "mae": 0.0}


def _open(tf, t=1794495600):
    return {"tf": tf, "t": t, "t_dec": t + N.TF_SEC[tf], "dir": -1, "entry": 4000.0}


def _old(kind, label, recs, open_plans, cpl):
    """The report before 2026-11-13: every timeframe in one headline."""
    return N.report_lines(kind, label, N.summarize(recs, cpl), len(open_plans))


def test_the_12_nov_shape_15m_first_and_website_records_on_their_own_line():
    """12 Nov (the replay of that day on the deployed code reproduces this): the phone's two 15m alerts went 1 TP / 1 SL;
    the 30m and 4h plans (both SL, and a 30m one still open) were never sent to the phone."""
    recs, op = [_rec("15m", "TP"), _rec("15m", "SL"), _rec("30m", "SL"), _rec("4h", "SL")], [_open("30m")]
    out = N.period_report_lines("DAILY", "Thu 12 Nov", recs, op, 26.0)
    assert out[0].startswith(f"XAUUSD DAILY VALIDATION Thu 12 Nov{SPLIT}: 2 signals closed, TP first 1/2 = 50%")
    assert "by timeframe 15m 1/2 |" in out[0] and "30m" not in out[0] and "4h" not in out[0] and "still open" not in out[0]
    assert out[1] == "WEBSITE ONLY (30m, 4h; not sent to your phone): 2 closed, TP first 0/2 = 0% | still open 1"
    assert out[-1] == "Details: website > Your plan alerts > Validation."
    old = _old("DAILY", "Thu 12 Nov", recs, op, 26.0)                                  # what the phone was sent
    assert old[0].startswith("XAUUSD DAILY VALIDATION Thu 12 Nov: 4 signals closed, TP first 1/4 = 25%")
    assert "by timeframe 15m 1/2 30m 0/1 4h 0/1" in old[0]
    out = N.period_report_lines("DAILY", "Thu 12 Nov", recs + [_rec("1h", "TP")], op + [_open("4h")], 26.0)
    assert out[1] == "WEBSITE ONLY (30m, 1h, 4h; not sent to your phone): 3 closed, TP first 1/3 = 33% | still open 2"


def test_15m_only_changes_nothing_but_the_label():
    recs, op = [_rec("15m", "TP"), _rec("15m", "SL")], [_open("15m")]
    out, old = N.period_report_lines("DAILY", "Thu 12 Nov", recs, op, 26.0), _old("DAILY", "Thu 12 Nov", recs, op, 26.0)
    assert not any(x.startswith("WEBSITE ONLY") for x in out)
    assert out[0] == old[0].replace("Thu 12 Nov:", f"Thu 12 Nov{SPLIT}:", 1) and out[1:] == old[1:]
    assert "still open 1" in out[0]


def test_website_only_day_says_the_phone_had_none():
    out = N.period_report_lines("WEEKLY", "2026-W46", [_rec("1h", "TP")], [_open("30m")], 26.0)
    assert out == [f"XAUUSD WEEKLY VALIDATION 2026-W46{SPLIT}: no alerted signal closed (and none open).",
                   "WEBSITE ONLY (30m, 1h; not sent to your phone): 1 closed, TP first 1/1 = 100% | still open 1"]
    out = N.period_report_lines("DAILY", "Thu 12 Nov", [], [_open("1h")], 26.0)
    assert out[1] == "WEBSITE ONLY (1h; not sent to your phone): none closed | still open 1"


def test_expired_only_is_not_counted_as_closed():
    out = N.period_report_lines("DAILY", "Thu 12 Nov", [_rec("15m", "TP"), _rec("1h", "EXPIRED")], [], 26.0)
    assert out[1] == "WEBSITE ONLY (1h; not sent to your phone): none closed"


def test_advice_on_the_phone_is_about_the_phone_timeframe_only():
    """A WEAK 1h verdict (30 results) must not tell the operator to stop taking signals the phone never sends."""
    recs = [_rec("1h", "SL")] * 30 + [_rec("15m", "TP")]
    old = " ".join(_old("DAILY", "Thu 12 Nov", recs, [], 26.0))
    assert "WEAK - timeframe 1h" in old
    out = N.period_report_lines("DAILY", "Thu 12 Nov", recs, [], 26.0)
    assert "WEAK" not in " ".join(out)
    assert out[1] == "WEBSITE ONLY (1h; not sent to your phone): 30 closed, TP first 0/30 = 0%"


@pytest.mark.parametrize("mode", ["quality", "all"])
def test_other_modes_send_every_timeframe_and_are_unchanged(monkeypatch, mode):
    monkeypatch.setenv("ALERT_MODE", mode)
    recs, op = [_rec("15m", "TP"), _rec("30m", "SL"), _rec("1h", "SL")], [_open("4h")]
    assert N.period_report_lines("DAILY", "Thu 12 Nov", recs, op, 26.0) == _old("DAILY", "Thu 12 Nov", recs, op, 26.0)


def test_the_inputs_are_not_modified():
    recs, op = [_rec("15m", "TP"), _rec("1h", "SL")], [_open("4h"), _open("15m")]
    r0, o0 = copy.deepcopy(recs), copy.deepcopy(op)
    N.period_report_lines("DAILY", "Thu 12 Nov", recs, op, 26.0)
    assert recs == r0 and op == o0


# ---- the whole run: 15m BUY (TP) + 1h SELL (SL), then the reports at the New York close ----------------------------
def _ts(s):
    return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp())


T0 = _ts("2026-11-06 14:00")                                     # Friday, London + New York


def _pay(tf, t_last, markers, bars, now):
    return {"meta": {"tf": tf, "synthetic": False, "generated_utc": now, "price_source": "td"}, "markers": markers,
            "decisions": [], "news": None, "chart": {"t": [b[0] for b in bars] + [t_last], "h": [b[1] for b in bars] + [None],
                                                     "l": [b[2] for b in bars] + [None]}}


S15 = {"t": T0 + 2700, "type": "SIGNAL", "dir": 1, "px": 4000.0, "tq": 70, "sl": 3990.0, "tp1": 4010.0, "tp2": 4020.0, "tp3": 4030.0}
S1H = {"t": T0, "type": "SIGNAL", "dir": -1, "px": 4000.0, "tq": 70, "sl": 4010.0, "tp1": 3990.0, "tp2": 3980.0, "tp3": 3970.0}
B15 = [(T0 + 2700, 4001, 3999), (T0 + 3600, 4013.5, 3998)]      # the bar after the signal reaches +$13: TP
B1H = [(T0, 4001, 3999), (T0 + 3600, 4013.5, 3998)]              # the same high stops the SELL: SL
RUNS = [  # (now, 15m (t_last, markers, bars), 1h (t_last, markers, bars))
    ("2026-11-06T14:05:00+00:00", (T0, [], []), (T0 - 3600, [], [])),
    ("2026-11-06T15:05:00+00:00", (T0 + 3600, [S15], B15[:1]), (T0 + 3600, [S1H], B1H[:1])),     # both alerts, FRESH
    ("2026-11-06T16:05:00+00:00", (T0 + 4500, [S15], B15), (T0 + 7200, [S1H], B1H)),             # both resolved
    ("2026-11-06T22:10:00+00:00", (T0 + 4500, [], []), (T0 + 7200, [], [])),                     # daily + weekly
]


def _scenario(tmp_path, monkeypatch, split=True):
    if not split:
        monkeypatch.setattr(N, "period_report_lines", _old)
    raw = []
    monkeypatch.setattr(N, "send", lambda lines: raw.append(list(lines)) or (["test"] if lines else []))
    store = str(tmp_path)
    reps = [N.run(store, {"15m": _pay("15m", *a, now), "1h": _pay("1h", *b, now)}, ["15m", "1h"],
                  sent_t=_ts(now[:16].replace("T", " "))) for now, a, b in RUNS]
    files = {}
    for root, _, fs in os.walk(store):
        for f in fs:
            p = os.path.join(root, f)
            files[os.path.relpath(p, store)] = open(p, "rb").read()
    return raw, reps, files


def test_whole_run_only_the_report_wording_changes(tmp_path, monkeypatch):
    new_raw, new_reps, new_files = _scenario(tmp_path / "new", monkeypatch, split=True)
    old_raw, old_reps, old_files = _scenario(tmp_path / "old", monkeypatch, split=False)
    assert N.sixty()
    # the scenario is what it claims: one 15m TP, one 1h SL, closed on the Friday
    v = new_reps[2]["plans"]["validation"]                  # the website's block, after both closed: every timeframe
    assert v["today"]["n"] == 2 and set(v["today"]["by"]["timeframe"]) == {"15m", "1h"} and v["all"]["n"] == 2
    assert [r["plans"]["validation"] for r in new_reps] == [r["plans"]["validation"] for r in old_reps]
    closed = sorted((r["tf"], r["result"]) for r in json.loads(new_files[N.VALIDATION]))
    assert closed == [("15m", "TP"), ("1h", "SL")]
    # every record, plan and website line is the same
    assert new_files == old_files
    assert [r.get("plans") for r in new_reps] == [r.get("plans") for r in old_reps]
    for tf in ("15m", "1h"):
        assert [r.get(tf) for r in new_reps] == [r.get(tf) for r in old_reps]
    # every message but the report is the same; the 1h alert never reached the phone in either
    rep_new = [m for m in new_raw if any("VALIDATION" in x for x in m)]
    rep_old = [m for m in old_raw if any("VALIDATION" in x for x in m)]
    assert [m for m in new_raw if m not in rep_new] == [m for m in old_raw if m not in rep_old]
    assert not any(x.startswith("XAUUSD 1h") for m in new_raw for x in m)
    assert len(rep_new) == len(rep_old) == 1
    new, old = rep_new[0], rep_old[0]
    assert any(x.startswith("XAUUSD DAILY VALIDATION Fri 06 Nov: 2 signals closed, TP first 1/2 = 50%") for x in old)
    assert any(x.startswith(f"XAUUSD DAILY VALIDATION Fri 06 Nov{SPLIT}: 1 signals closed, TP first 1/1 = 100%") for x in new)
    assert any(x.startswith(f"XAUUSD WEEKLY VALIDATION 2026-W45{SPLIT}: 1 signals closed") for x in new)
    assert new.count("WEBSITE ONLY (1h; not sent to your phone): 1 closed, TP first 0/1 = 0%") == 2   # daily + weekly

    def tail(m):                                         # the lines that ride with the report: engine, tests, setups
        return [x for x in m if not x.startswith(("XAUUSD DAILY VALIDATION", "XAUUSD WEEKLY VALIDATION", "WEBSITE ONLY",
                                                     "Only ", "Details:"))]
    assert tail(new) == tail(old) and tail(new)
    assert new_reps[-1]["validation_report"]["lines"] == new
