#!/usr/bin/env python3
"""v100 (F-A90, edge case E7): the Master's BUY / SELL alert() fires on the FIRST bar of a signal run, not on every bar.

Measured (the website's engine, the verified port of the Master's, read-only on the live 15m store 2026-08-05 ->
11-03): the executed BUY signal (shouldBuy and not tqVeto, the alert's condition) was true on 36 bars in 7 runs (up
to 9 bars long), so 29 of 36 BUY alerts repeated a signal already sent; SELL 10 of 21. Each repeat carried a fresh
"BUY | MT5 entry ..." plan at a later price, up to two hours after the signal on 15m.

Fix: `and _confDirLabel[1] != "BUY"` (resp. "SELL") on the two alert() lines. _confDirLabel == "BUY" exactly when
shouldBuy and not tqVeto (decision_check precedence; tqVeto includes the risk lock), and both are confirmed-bar values,
so the alert fires when the previous closed bar was not already an alerted BUY. Unchanged: the DECISION cell, the plan,
the DECISION-change alert, the alertcondition() entries (ALERTS_SETUP: not the recommended setup; no token room for
four edits). Usage: python3 audit/tools/fix_v100.py (from the repo root)"""
M = "artefacts/XAUUSD_Quantum_5_0_Master.pine"
EDITS = [("if shouldBuy and not tqVeto and barstate.isconfirmed and not perfMode\n",
          "if shouldBuy and not tqVeto and barstate.isconfirmed and not perfMode and _confDirLabel[1] != \"BUY\"\n"),
         ("if shouldSell and not tqVeto and barstate.isconfirmed and not perfMode\n",
          "if shouldSell and not tqVeto and barstate.isconfirmed and not perfMode and _confDirLabel[1] != \"SELL\"\n")]
COMMENT = ("// v100 (F-A90, E7): the BUY / SELL alert() fires on the first bar of a signal run (the website engine on 15m: 29 of\n"
           "// 36 BUY alerts repeated a signal already sent, up to 9 bars in a row); the DECISION-change alert is unchanged.\n")
STAMP_OLD = "// ║  BUILD STAMP — this file last CHANGED in v99   (day rollover = website key)   ║"
STAMP_NEW = "// ║  BUILD STAMP — this file last CHANGED in v100  (one BUY / SELL alert per run) ║"


def master(src):
    assert len(STAMP_OLD) == len(STAMP_NEW) and src.count(STAMP_OLD) == 1
    out = src.replace(STAMP_OLD, STAMP_NEW)
    for i, (o, n) in enumerate(EDITS):
        assert out.count(o) == 1, o
        out = out.replace(o, (COMMENT if i == 0 else "") + n)
    return out


if __name__ == "__main__":
    out = master(open(M, encoding="utf-8").read())
    open(M, "w", encoding="utf-8").write(out)
    print("wrote", M)
