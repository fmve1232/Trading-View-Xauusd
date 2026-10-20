"""v83 (F-A71): the news window's label said UTC, but time(timeframe.period, newsSession) has no time-zone argument, so
it is evaluated in the EXCHANGE time zone (America/New_York for OANDA:XAUUSD, the engine's documented assumption, F-033).
The tooltip's own example (1300-1500 for FOMC Wednesdays; FOMC = 14:00 New York) is New York time. The label and
tooltip are corrected; the logic, the default ("" = off) and the token count are unchanged. Applied identically to the
Master, the three arms, and (rebuilt) Diagnostics and Brief."""
OLD = 'newsSession = input.session("", "News Event Window (UTC)", group=grpRisk, tooltip="Session during which signals are suppressed, e.g. 1300-1500:4 for FOMC Wednesdays. Leave empty to disable.")'
NEW = ('newsSession = input.session("", "News Event Window (New York time)", group=grpRisk, tooltip="Session during which signals '
       'are suppressed, in the chart symbol\'s exchange time zone (New York for OANDA XAUUSD), NOT UTC: e.g. 1300-1500:4 = '
       '13:00-15:00 New York on Wednesdays, around the 14:00 FOMC statement. Leave empty to disable.")')


STAMP_M = "// ║  BUILD STAMP — this file last CHANGED in v83   (news window: NY time)"


def transform(text):
    assert text.count(OLD) == 1, "news input is not the v82 line"
    return text.replace(OLD, NEW)


def master(text):
    """the v83 Master from the v72 (= fix_v68.transform(v66)) Master: the label, and the stamp line"""
    L = transform(text).split("\n")
    i = next(k for k, l in enumerate(L[:6]) if "BUILD STAMP" in l)
    L[i] = STAMP_M + " " * (len(L[i + 1]) - len(STAMP_M) - 1) + "║"
    return "\n".join(L)


if __name__ == "__main__":
    for f in ("Master", "Strategy", "Strategy_OLDGATES", "Strategy_CHALLENGER"):
        p = f"artefacts/XAUUSD_Quantum_5_0_{f}.pine"
        src = open(p, encoding="utf-8").read()
        open(p, "w", encoding="utf-8").write(transform(src))
        print("fixed", f)
