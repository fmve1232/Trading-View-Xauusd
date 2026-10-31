"""v91 (independent v90 audit, operator-approved 2026-10-31: B-01, B-02). DISPLAY ONLY: the Master's position-size
advice. No value read by the DECISION changes (audit/tools/v90_slice.py: none of the edited names is in its slice).

B-01  The lots were risk$ / (stop distance x $ per point), so a stop-out also paid spread + 2 x slippage + commission
      on top: realised loss 8-24% above the stated ceiling (3-10 point stops). Now risk$ / ((stop + cost) x $ per
      point), cost = the round-trip cost the plan itself charges (_cR, L2812: the SESSION spread tier). _liveCostATR
      (display only: cost-to-target %) used the flat spreadCost; it now uses _sessSpread, so both displays charge what
      the plan charges.
B-02  The Master's account default was $10,000 while Visuals' risk box (v89, operator: "account default is 25k") is
      $25,000: two lot sizes for one trade. The Master's default is now 25,000.
Paid for (the Master has < 80 tokens of headroom, F-A72) by three identical-output removals in the same function,
each a guard the inputs' bounds make redundant (executed old vs new in v91_check.py): pointValue > 0 (input minval
1), math.max(_kellyPct, 0.0) (every write to it is >= 0), math.max(_lotsFloored, 0.0) (_rawLots >= 0)."""

PAIRS = [
    ('accountSize = input.float(10000, "Account Size (USD)", minval=100, group=grpRisk)',
     'accountSize = input.float(25000, "Account Size (USD)", minval=100, group=grpRisk)'),
    ("// R5-F15: spread is a round-trip cost paid once; only slippage occurs on both sides.\n"
     "float _liveCostATR = adaptiveATR > 0 ? ((spreadCost + 2.0 * slippagePts) + commissionL / math.max(pointValue, 1.0)) / adaptiveATR : 0.0",
     "// R5-F15: spread is a round-trip cost paid once; only slippage occurs on both sides.\n"
     "// v91 (B-01): the SESSION spread tier, as the plan's own cost (_cR); the lots below are sized on stop + this cost.\n"
     "float _liveCostATR = adaptiveATR > 0 ? ((_sessSpread + 2.0 * slippagePts) + commissionL / math.max(pointValue, 1.0)) / adaptiveATR : 0.0"),
    ("    float _riskUSD = accountSize * math.max(_kellyPct, 0.0) * regSizeMult / 100.0\n"
     "    float _rawLots = tpDist > 0 and pointValue > 0 ? _riskUSD / (tpDist * pointValue) : 0.0",
     "    float _riskUSD = accountSize * _kellyPct * regSizeMult / 100.0\n"
     "    // v91 (B-01): a stop-out costs the stop distance PLUS the round-trip cost, so the lots are sized on both and the\n"
     "    // loss at the stop stays within the stated risk (was 8-24% over it). tpDist is the STOP distance |entry - SL|.\n"
     "    float _rawLots = tpDist > 0 ? _riskUSD / ((tpDist + _liveCostATR * adaptiveATR) * pointValue) : 0.0"),
    ("    float _lots = math.min(math.max(_lotsFloored, 0.0), 100.0)",
     "    float _lots = math.min(_lotsFloored, 100.0)"),
]
STAMP_M = "// ║  BUILD STAMP — this file last CHANGED in v91   (lots include cost; 25k)"


def master(text):
    """the v91 Master from the v86 Master"""
    for old, new in PAIRS:
        assert text.count(old) == 1, f"not the v86 text: {old[:60]}"
        text = text.replace(old, new)
    L = text.split("\n")
    i = next(k for k, l in enumerate(L[:6]) if "BUILD STAMP" in l)
    L[i] = STAMP_M + " " * (len(L[i + 1]) - len(STAMP_M) - 1) + "║"
    return "\n".join(L)


if __name__ == "__main__":
    p = "artefacts/XAUUSD_Quantum_5_0_Master.pine"
    src = open(p, encoding="utf-8").read()
    open(p, "w", encoding="utf-8").write(master(src))
    print("fixed Master (v91)")
