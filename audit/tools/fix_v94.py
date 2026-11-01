"""v94 (operator, 2026-10-31: "Master & Visuals should be 100% aligned & calibrated in all respects" -> "Allow the link").

THE LINK. Visuals cannot read another script except through input.source. The Master now publishes two series, shown
in the Data Window only (no line on the chart):
  "LINK decision x stop" = +plan SL on a bar whose confirmed DECISION is BUY, -plan SL on SELL, 0 otherwise
                           (_confDirLabel changes on confirmed bars only, so the series does not repaint; tpIsLong =
                           shouldBuy ? true : ..., so the sign and the stop's side always agree)
  "LINK lots"            = the lots the Master's MT5 plan shows (gDashF[6]: -1 = below the 0.01 minimum); set on the
                           last bar, where Visuals reads it
Visuals reads them through two source inputs (the operator picks them once per chart). An unlinked source defaults to
`close` (> 0 on every bar); a linked one is 0 on every WAIT bar, so the link is detected without a switch.
Linked: the BRACKET tracker scores each new Master BUY / SELL (the bar the DECISION changes to it, as the DECISION
alert) instead of the H2 signals; the RISK row shows the Master's plan lots and, while a DECISION is live, uses the
plan stop instead of 1 ATR. Unlinked: everything is as in v93.
The Master pays for the two plots with identical-output rewrites in Master-only dashboard code (its headroom is < 80
tokens, F-A72): one local `color _cn = color(na)` for the 15 `color(na)` arguments in f_dashRender, and
na(x) ? 50 : x == nz(x, 50) twice. No signal, gate, veto or engine value changes."""

M_PAIRS = [
    ("f_dashRender() =>\n    string _agreeTier = array.get(gDashS, 0)\n",
     "f_dashRender() =>\n    // v94: one transparent colour for the 15 cells below (the same na colour each used inline; identical value, fewer tokens)\n"
     "    color _cn = color(na)\n    string _agreeTier = array.get(gDashS, 0)\n"),
    ("    float _crVal = na(avgCorrHealth) ? 50 : avgCorrHealth", "    float _crVal = nz(avgCorrHealth, 50)"),
    ("na(liqReachScore) ? 50 : liqReachScore", "nz(liqReachScore, 50)"),
]
M_TAIL = ("\n// v94 LINK (operator, 2026-10-31: \"Allow the link\"): two series for Visuals' source inputs, Data Window only.\n"
          "// +plan SL on a confirmed-BUY bar, -plan SL on SELL, 0 otherwise; and the MT5 plan's lots (-1 = below 0.01).\n"
          'plot(_confDirLabel == "BUY" ? tpSL : _confDirLabel == "SELL" ? -tpSL : 0, "LINK decision x stop", display = display.data_window)\n'
          'plot(array.get(gDashF, 6), "LINK lots", display = display.data_window)\n')
STAMP_M = "// ║  BUILD STAMP — this file last CHANGED in v94   (LINK for Visuals)"

V_PAIRS = [
    ("float trkSLd = trkUnit == \"MT5 points\" ? trkSL * trkPt : trkSL / (trkLot * pointValue)\n",
     "// v94 LINK: the Master's two series (pick them once per chart). Unlinked, a source is `close` (> 0 on every bar); the\n"
     "// Master's decision series is 0 on every WAIT bar, so a 0 proves the link.\n"
     'lkDec = input.source(close, "Master link: LINK decision x stop", group = grpCk, tooltip = "v94: pick the Master\'s '
     "'LINK decision x stop' here (and 'LINK lots' below) so Visuals scores the Master's own BUY / SELL and shows its plan "
     "lots and stop. Left at 'close', Visuals works as before (the tracker scores H2 signals).\")\n"
     'lkLots = input.source(close, "Master link: LINK lots", group = grpCk)\n'
     "var bool lkOn = false\n"
     "if not lkOn and lkDec == 0\n"
     "    lkOn := true\n"
     "int lkD = lkOn and not na(lkDec) ? (lkDec > 0 ? 1 : lkDec < 0 ? -1 : 0) : 0\n"
     "float lkSLp = lkD != 0 ? math.abs(lkDec) : na\n"
     "bool lkTrig = barstate.isconfirmed and lkD != 0 and lkD != nz(lkD[1])\n"
     "bool lkLotsOn = lkOn and not na(lkLots) and lkLots != close\n"
     "bool trkLongSig = lkOn ? lkTrig and lkD > 0 : h2Long\n"
     "bool trkShortSig = lkOn ? lkTrig and lkD < 0 : h2Short\n"
     "float trkSLd = trkUnit == \"MT5 points\" ? trkSL * trkPt : trkSL / (trkLot * pointValue)\n"),
    ("    if (h2Long or h2Short) and array.size(trkE) < 200\n", "    if (trkLongSig or trkShortSig) and array.size(trkE) < 200\n"),
    ("        array.push(trkDir, h2Long ? 1 : -1)\n", "        array.push(trkDir, trkLongSig ? 1 : -1)\n"),
    ('string trkTxt = "H2 signals · SL "', 'string trkTxt = (lkOn ? "Master BUY / SELL" : "H2 signals (link the Master to score its BUY / SELL)") + " · SL "'),
    ('" · this chart\'s history only, not the Master\'s BUY / SELL"', '" · this chart\'s history only" + (lkOn ? "" : ", not the Master\'s BUY / SELL")'),
    ("float rkStopD = rkStop > 0 ? rkStop : atr14\n",
     "// v94: with the link and a live DECISION, the default stop is the Master's plan stop (it was 1 ATR)\n"
     "float rkStopD = rkStop > 0 ? rkStop : not na(lkSLp) ? math.abs(close - lkSLp) : atr14\n"),
    ('(rkStop > 0 ? "" : " (1 ATR, not the Master\'s plan SL: type it in)")',
     '(rkStop > 0 ? "" : not na(lkSLp) ? " (the Master\'s plan SL)" : " (1 ATR, not the Master\'s plan SL: type it in)")'),
    ('str.tostring(rkLots, "#.##") + " lot (MT5 step 0.01, " + str.tostring(pointValue, "#") + " oz)")',
     'str.tostring(rkLots, "#.##") + " lot (MT5 step 0.01, " + str.tostring(pointValue, "#") + " oz)") + (lkLotsOn ? "\\nthe Master\'s plan: " + '
     '(lkLots < 0 ? "below 0.01 lot" : str.tostring(lkLots, "#.##") + " lot (half-Kelly, capped at its Risk %)") : "")'),
]
STAMP_V = "// ║  BUILD STAMP — this file last CHANGED in v94   (LINK from the Master)"


def _stamp(text, stamp):
    L = text.split("\n")
    i = next(k for k, l in enumerate(L[:6]) if "BUILD STAMP" in l)
    L[i] = stamp + " " * (len(L[i + 1]) - len(stamp) - 1) + "║"
    return "\n".join(L)


def _apply(text, pairs):
    for old, new in pairs:
        assert text.count(old) == 1, f"not the v93 text: {old[:70]}"
        text = text.replace(old, new)
    return text


def master(text):
    """the v94 Master from the v93 Master (= v92)"""
    text = _apply(text, M_PAIRS)
    a = text.index("f_dashRender() =>")
    b = text.index("\n", text.index("\n", a) + 1)
    end = a
    L = text[a:].split("\n")
    n = 1
    while n < len(L) and (L[n].startswith(" ") or not L[n].strip()):
        n += 1
    body = "\n".join(L[:n])
    assert body.count("color(na)") == 16, body.count("color(na)")      # 15 arguments + the new local's own definition
    body = body.replace("color(na)", "_cn").replace("    color _cn = _cn", "    color _cn = color(na)", 1)
    text = text[:a] + body + "\n" + "\n".join(L[n:])
    text = text.rstrip("\n") + "\n" + M_TAIL
    return _stamp(text, STAMP_M)


def visuals(text):
    """the v94 Visuals from the v93 Visuals"""
    return _stamp(_apply(text, V_PAIRS), STAMP_V)


if __name__ == "__main__":
    for p, f in (("artefacts/XAUUSD_Quantum_5_0_Master.pine", master), ("artefacts/XAUUSD_Quantum_5_5_Visuals.pine", visuals)):
        out = f(open(p, encoding="utf-8").read())      # computed BEFORE the file is opened for writing
        open(p, "w", encoding="utf-8").write(out)
    print("fixed Master and Visuals (v94)")
