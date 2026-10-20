"""v84 (operator: "notifications on each sweep, CHoCH and when a signal fires on a confirmed trade"): the Master's
single alert() channel already carried BUY / SELL (confirmed, with the MT5 plan), DECISION changes, BOS / CHoCH / MSS
and the pool sweeps (PDH/PDL, PWH/PWL, PMH/PML). It did not carry H2's swing-high / swing-low sweeps. They are added
to the same event line (one alert covers everything, which the free plan needs), with the swept level at the MT5 price.
h2SweptLvl is read, not h2SwL / h2SwH: the H2 block consumes the swing after a sweep (sequence.py), so only the copy
holds the level. Display / alert text only: the DECISION rule and the H2 block are unchanged."""
OLD = ' + _ev(liqSweepBull, " SWEEP-LOW") + _ev(liqSweepBear, " SWEEP-HIGH") + (h2Long or h2Short ? " | H2 SETUP " + h2Plan + " (MT5)" : "")'
NEW = (' + _ev(liqSweepBull, " SWEEP-LOW") + _ev(liqSweepBear, " SWEEP-HIGH") + (h2SweepL or h2SweepH ? (h2SweepL ? " H2-SWEEP-LOW " : '
       '" H2-SWEEP-HIGH ") + str.tostring(h2SweptLvl + mt5Offset, "#.##") + (h2SweepL and h2SweepH ? " (+HIGH)" : "") + " (MT5)" : "")'
       ' + (h2Long or h2Short ? " | H2 SETUP " + h2Plan + " (MT5)" : "")')
STAMP = "// ║  BUILD STAMP — this file last CHANGED in v84   (alerts: + H2 sweeps)"


def master(text):
    assert text.count(OLD) == 1, "the alert line is not the v83 one"
    L = text.replace(OLD, NEW).split("\n")
    i = next(k for k, l in enumerate(L[:6]) if "BUILD STAMP" in l)
    L[i] = STAMP + " " * (len(L[i + 1]) - len(STAMP) - 1) + "║"
    return "\n".join(L)


if __name__ == "__main__":
    p = "artefacts/XAUUSD_Quantum_5_0_Master.pine"
    src = open(p, encoding="utf-8").read()
    open(p, "w", encoding="utf-8").write(master(src))
    print("wrote the v84 Master")
