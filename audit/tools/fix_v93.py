"""v93 (operator, 2026-10-31: "MT5 points, build the Visuals tracker. I mean $500 / $1000 in money"). DISPLAY ONLY, Visuals.

BRACKET TRACKER: the operator trades a fixed bracket (SL $500 / TP $1000 at 0.5 lot = $10 / $20 of price; the inputs
also take MT5 points). For every H2 signal on the loaded chart (Visuals' own signal, the website's arm H3 rule; Visuals
cannot read the Master's BUY / SELL, a Master -> Visuals link was declined 2026-10-21) the tracker starts a race at the
signal bar's close and, from the NEXT bar, records which of the operator's TP or SL is touched first (a bar touching
both counts as the SL: conservative, as the website). It shows the TP-first rate with its Wilson 95% range, the
break-even rate including the round-trip cost (spread + 2 x slippage + commission, the COST row's cost at the bar the
race resolved, news multiplier included), the chance level SL / (SL + TP), and the net $ at the lot size.
Nothing here feeds a signal; nothing was fitted. The numbers are the chart's loaded history only, not the website's
record (the system of record, A7)."""

V_PAIRS = [
    ("bool rkLocked = rkToday <= rkCap\n",
     "bool rkLocked = rkToday <= rkCap\n"
     "\n"
     "// ---- v93 BRACKET TRACKER (operator, 2026-10-31): the operator's fixed SL / TP scored on every H2 signal (= the\n"
     "// website's arm H3 rule) from the signal bar's close; from the next bar, TP or SL first (both on one bar = SL).\n"
     'trkShow = input.bool(true, "Bracket tracker: score H2 signals with my SL / TP", group = grpCk, tooltip = "v93: for '
     "every H2 signal on the loaded chart, did your TP or your SL come first, from the signal bar's close? Shows the "
     "TP-first rate with its 95% range, the break-even rate (cost included) and the net $ at your lot size. H2 is "
     "Visuals' own signal (the website's arm H3); Visuals cannot read the Master's BUY / SELL. Display only.\")\n"
     'trkUnit = input.string("Money ($)", "Bracket unit", options = ["Money ($)", "MT5 points"], group = grpCk)\n'
     'trkSL = input.float(500.0, "Bracket SL (in the unit above)", minval = 0.01, maxval = 10000000.0, group = grpCk)\n'
     'trkTP = input.float(1000.0, "Bracket TP (in the unit above)", minval = 0.01, maxval = 10000000.0, group = grpCk)\n'
     'trkLot = input.float(0.5, "Bracket lot size", minval = 0.01, maxval = 100.0, step = 0.01, group = grpCk)\n'
     'trkPt = input.float(0.01, "MT5 point size (price per point; 0.01 for a 2-digit XAUUSD quote)", minval = 0.0001, '
     "maxval = 1.0, step = 0.0001, group = grpCk)\n"
     "float trkSLd = trkUnit == \"MT5 points\" ? trkSL * trkPt : trkSL / (trkLot * pointValue)\n"
     "float trkTPd = trkUnit == \"MT5 points\" ? trkTP * trkPt : trkTP / (trkLot * pointValue)\n"
     "var float[] trkE = array.new_float()\n"
     "var int[] trkDir = array.new_int()\n"
     "var int trkW = 0\n"
     "var int trkL = 0\n"
     "var float trkNet = 0.0\n"
     "if trkShow and barstate.isconfirmed\n"
     "    int _tn = array.size(trkE)\n"
     "    if _tn > 0\n"
     "        for _ti = _tn - 1 to 0\n"
     "            float _te = array.get(trkE, _ti)\n"
     "            int _td = array.get(trkDir, _ti)\n"
     "            bool _tsl = _td > 0 ? low <= _te - trkSLd : high >= _te + trkSLd\n"
     "            bool _ttp = _td > 0 ? high >= _te + trkTPd : low <= _te - trkTPd\n"
     "            if _tsl or _ttp\n"
     "                if _tsl\n"
     "                    trkL += 1\n"
     "                    trkNet -= (trkSLd + ckCost) * trkLot * pointValue\n"
     "                else\n"
     "                    trkW += 1\n"
     "                    trkNet += (trkTPd - ckCost) * trkLot * pointValue\n"
     "                array.remove(trkE, _ti)\n"
     "                array.remove(trkDir, _ti)\n"
     "    if (h2Long or h2Short) and array.size(trkE) < 200\n"
     "        array.push(trkE, close)\n"
     "        array.push(trkDir, h2Long ? 1 : -1)\n"
     "int trkN = trkW + trkL\n"
     "float trkBE = (trkSLd + ckCost) / (trkSLd + trkTPd)\n"
     "[trkLo, trkHi] = f_wil(trkW, trkN)\n"
     "float trkEqPct = trkSLd * trkLot * pointValue / rkEquity * 100.0\n"
     "int trkLv = trkN < 1 ? 0 : trkLo > trkBE ? 1 : trkHi < trkBE ? -1 : 0\n"
     "string trkTxt = \"H2 signals · SL \" + (trkUnit == \"MT5 points\" ? str.tostring(trkSL, \"#\") + \" pts\" : \"$\" + str.tostring(trkSL, \"#\")) "
     "+ \" / TP \" + (trkUnit == \"MT5 points\" ? str.tostring(trkTP, \"#\") + \" pts\" : \"$\" + str.tostring(trkTP, \"#\")) + \" at \" "
     "+ str.tostring(trkLot, \"#.##\") + \" lot = $\" + str.tostring(trkSLd, \"#.##\") + \" / $\" + str.tostring(trkTPd, \"#.##\") "
     "+ \" price · risk \" + str.tostring(trkEqPct, \"#.#\") + \"% of equity\\n\" + (trkN < 1 ? \"no closed H2 signal on this chart yet\" "
     ": \"TP first \" + str.tostring(trkW) + \"/\" + str.tostring(trkN) + \" = \" + str.tostring(trkW * 100.0 / trkN, \"#\") + \"% (95% \" "
     "+ str.tostring(trkLo * 100.0, \"#\") + \"–\" + str.tostring(trkHi * 100.0, \"#\") + \") · break-even \" + str.tostring(trkBE * 100.0, \"#\") "
     "+ \"% · chance \" + str.tostring(trkSLd / (trkSLd + trkTPd) * 100.0, \"#\") + \"%\") + \"\\nnet $\" + str.tostring(trkNet, \"#\") "
     "+ \" · open \" + str.tostring(array.size(trkE)) + \" · this chart's history only, not the Master's BUY / SELL\"\n"),
    ("        r += 1\n        _tmRow(r, \"TODAY\", rkLocked ?",
     "        if trkShow\n"
     "            r += 1\n"
     "            _tmRow(r, \"BRACKET\", trkTxt, trkLv == 1 ? _tmUp : trkLv == -1 ? _tmDn : _amb)\n"
     "        r += 1\n        _tmRow(r, \"TODAY\", rkLocked ?"),
]
STAMP_V = "// ║  BUILD STAMP — this file last CHANGED in v93   (bracket tracker)"


def visuals(text):
    """the v93 Visuals from the v92 Visuals"""
    for old, new in V_PAIRS:
        assert text.count(old) == 1, f"not the v92 text: {old[:70]}"
        text = text.replace(old, new)
    L = text.split("\n")
    i = next(k for k, l in enumerate(L[:6]) if "BUILD STAMP" in l)
    L[i] = STAMP_V + " " * (len(L[i + 1]) - len(STAMP_V) - 1) + "║"
    return "\n".join(L)


if __name__ == "__main__":
    p = "artefacts/XAUUSD_Quantum_5_5_Visuals.pine"
    src = open(p, encoding="utf-8").read()
    open(p, "w", encoding="utf-8").write(visuals(src))
    print("fixed Visuals (v93)")
