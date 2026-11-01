"""v97 (operator, 2026-11-01: "-$10 stop with +$10, +$15 and +$20 profit with success rate more than 90%" -> "Both"):
Visuals' BRACKET tracker scores ONE stop against THREE targets, with the confirmation entry the website tested (B3).
Visuals only; display only; nothing is fitted (the defaults are the operator's bracket and the website's declared rule).

Targets: TP1 / TP2 / TP3 (default $500 / $750 / $1,000 at 0.5 lot = +$10 / +$15 / +$20 of price) on the SL ($500 = -$10).
Each target is scored on its own: a WIN when it is touched before the stop, a LOSS when the stop comes first (a bar
touching both counts as the stop); a race ends when the stop is hit or all three targets have been. Each target shows
its success rate, Wilson 95% range, break-even (cost included) and net $ at the lot.
Confirmation (the website's Phase B3 rule, research/B3_DEVELOPMENT_RESULTS.md section 2): after the signal, wait up
to trkCfMin minutes (120 = B3's 2 hours) for a CLOSE at least trkCf dollars (3 = B3, scaled to a $4,000 gold price as
B3 scales it) beyond the signal close in the trade's direction, before any close that far against; enter at that
confirming close and measure the stop and targets from it; otherwise no trade. 0 = enter at the signal's close, as v93.
On the chart the confirming closes are the chart's own bars (B3 used 15-minute closes).
The website found no edge in this family (B3: 210 trials, best within noise of random; Reality Check p = 1.000); the
tracker lets the operator watch the same rule on his own signals, it does not certify one."""

NEW = r'''trkTP1 = input.float(500.0, "Bracket TP1 (in the unit above)", minval = 0.01, maxval = 10000000.0, group = grpCk, tooltip = "v97: three targets on one stop, each scored on its own (touched before the stop = success). Defaults at 0.5 lot: SL $500 = -$10, TP1 $500 = +$10, TP2 $750 = +$15, TP3 $1,000 = +$20.")
trkTP2 = input.float(750.0, "Bracket TP2 (in the unit above)", minval = 0.01, maxval = 10000000.0, group = grpCk)
trkTP = input.float(1000.0, "Bracket TP3 (in the unit above)", minval = 0.01, maxval = 10000000.0, group = grpCk)
trkLot = input.float(0.5, "Bracket lot size", minval = 0.01, maxval = 100.0, step = 0.01, group = grpCk)
trkPt = input.float(0.01, "MT5 point size (price per point; 0.01 for a 2-digit XAUUSD quote)", minval = 0.0001, maxval = 1.0, step = 0.0001, group = grpCk)
trkCf = input.float(3.0, "Confirmation: a close this far my way first ($ at $4,000 gold; 0 = enter at the signal)", minval = 0.0, maxval = 50.0, step = 0.5, group = grpCk, tooltip = "v97: the website's Phase B3 confirmation entry. After the signal, wait for a close this far beyond the signal close in the trade's direction, before a close this far against, within the window below; enter at that close. B3 used $3 (scaled with the gold price) within 2 hours. The website found no edge in this family (B3, 210 trials): this measures it on your own signals.")
trkCfMin = input.int(120, "Confirmation window (minutes)", minval = 1, maxval = 1440, group = grpCk)
float trkSLd = trkUnit == "MT5 points" ? trkSL * trkPt : trkSL / (trkLot * pointValue)
float trkTP1d = trkUnit == "MT5 points" ? trkTP1 * trkPt : trkTP1 / (trkLot * pointValue)
float trkTP2d = trkUnit == "MT5 points" ? trkTP2 * trkPt : trkTP2 / (trkLot * pointValue)
float trkTPd = trkUnit == "MT5 points" ? trkTP * trkPt : trkTP / (trkLot * pointValue)
float trkCfD = trkCf * close / 4000.0
int trkCfN = math.max(1, int(math.ceil(trkCfMin * 60.0 / timeframe.in_seconds())))
var float[] trkE = array.new_float()
var int[] trkDir = array.new_int()
var bool[] trkH1 = array.new_bool()
var bool[] trkH2 = array.new_bool()
var bool[] trkH3 = array.new_bool()
var float[] trkQe = array.new_float()
var int[] trkQd = array.new_int()
var int[] trkQb = array.new_int()
var int trkW1 = 0
var int trkL1 = 0
var float trkNet1 = 0.0
var int trkW2 = 0
var int trkL2 = 0
var float trkNet2 = 0.0
var int trkW = 0
var int trkL = 0
var float trkNet = 0.0
if trkShow and barstate.isconfirmed
    // 1 open races (entered on an earlier bar): the stop first on a bar that touches both
    int _tn = array.size(trkE)
    if _tn > 0
        for _ti = _tn - 1 to 0
            float _te = array.get(trkE, _ti)
            int _td = array.get(trkDir, _ti)
            bool _h1 = array.get(trkH1, _ti)
            bool _h2 = array.get(trkH2, _ti)
            bool _h3 = array.get(trkH3, _ti)
            float _lossUsd = (trkSLd + ckCost) * trkLot * pointValue
            if _td > 0 ? low <= _te - trkSLd : high >= _te + trkSLd
                if not _h1
                    trkL1 += 1
                    trkNet1 -= _lossUsd
                if not _h2
                    trkL2 += 1
                    trkNet2 -= _lossUsd
                if not _h3
                    trkL += 1
                    trkNet -= _lossUsd
                array.remove(trkE, _ti)
                array.remove(trkDir, _ti)
                array.remove(trkH1, _ti)
                array.remove(trkH2, _ti)
                array.remove(trkH3, _ti)
            else
                if not _h1 and (_td > 0 ? high >= _te + trkTP1d : low <= _te - trkTP1d)
                    _h1 := true
                    trkW1 += 1
                    trkNet1 += (trkTP1d - ckCost) * trkLot * pointValue
                if not _h2 and (_td > 0 ? high >= _te + trkTP2d : low <= _te - trkTP2d)
                    _h2 := true
                    trkW2 += 1
                    trkNet2 += (trkTP2d - ckCost) * trkLot * pointValue
                if not _h3 and (_td > 0 ? high >= _te + trkTPd : low <= _te - trkTPd)
                    _h3 := true
                    trkW += 1
                    trkNet += (trkTPd - ckCost) * trkLot * pointValue
                if _h1 and _h2 and _h3
                    array.remove(trkE, _ti)
                    array.remove(trkDir, _ti)
                    array.remove(trkH1, _ti)
                    array.remove(trkH2, _ti)
                    array.remove(trkH3, _ti)
                else
                    array.set(trkH1, _ti, _h1)
                    array.set(trkH2, _ti, _h2)
                    array.set(trkH3, _ti, _h3)
    // 2 signals waiting for confirmation: a close trkCfD my way enters (at that close), one against or the window cancels
    int _qn = array.size(trkQe)
    if _qn > 0
        for _qi = _qn - 1 to 0
            float _qe = array.get(trkQe, _qi)
            int _qd = array.get(trkQd, _qi)
            bool _qgo = _qd > 0 ? close >= _qe + trkCfD : close <= _qe - trkCfD
            bool _qno = (_qd > 0 ? close <= _qe - trkCfD : close >= _qe + trkCfD) or bar_index - array.get(trkQb, _qi) >= trkCfN
            if _qgo and array.size(trkE) < 200
                array.push(trkE, close)
                array.push(trkDir, _qd)
                array.push(trkH1, false)
                array.push(trkH2, false)
                array.push(trkH3, false)
            if _qgo or _qno
                array.remove(trkQe, _qi)
                array.remove(trkQd, _qi)
                array.remove(trkQb, _qi)
    // 3 a new signal: straight in (no confirmation) or queued
    if (trkLongSig or trkShortSig) and array.size(trkE) < 200 and array.size(trkQe) < 200
        if trkCf <= 0
            array.push(trkE, close)
            array.push(trkDir, trkLongSig ? 1 : -1)
            array.push(trkH1, false)
            array.push(trkH2, false)
            array.push(trkH3, false)
        else
            array.push(trkQe, close)
            array.push(trkQd, trkLongSig ? 1 : -1)
            array.push(trkQb, bar_index)
int trkN1 = trkW1 + trkL1
int trkN2 = trkW2 + trkL2
int trkN = trkW + trkL
float trkBE1 = (trkSLd + ckCost) / (trkSLd + trkTP1d)
float trkBE2 = (trkSLd + ckCost) / (trkSLd + trkTP2d)
float trkBE = (trkSLd + ckCost) / (trkSLd + trkTPd)
[trkLo1, trkHi1] = f_wil(trkW1, trkN1)
[trkLo2, trkHi2] = f_wil(trkW2, trkN2)
[trkLo, trkHi] = f_wil(trkW, trkN)
float trkEqPct = trkSLd * trkLot * pointValue / rkEquity * 100.0
int trkLv1 = trkN1 < 1 ? 0 : trkLo1 > trkBE1 ? 1 : trkHi1 < trkBE1 ? -1 : 0
int trkLv2 = trkN2 < 1 ? 0 : trkLo2 > trkBE2 ? 1 : trkHi2 < trkBE2 ? -1 : 0
int trkLv = trkN < 1 ? 0 : trkLo > trkBE ? 1 : trkHi < trkBE ? -1 : 0
int trkLvAll = trkLv1 == 1 or trkLv2 == 1 or trkLv == 1 ? 1 : trkLv1 == -1 and trkLv2 == -1 and trkLv == -1 ? -1 : 0
f_trkCell(string nm, float tpd, int w, int n, float lo, float hi, float be, float net) =>
    nm + " +$" + str.tostring(tpd, "#.#") + ": " + (n < 1 ? "—" : str.tostring(w) + "/" + str.tostring(n) + " = " + str.tostring(w * 100.0 / n, "#") + "% (" + str.tostring(lo * 100.0, "#") + "–" + str.tostring(hi * 100.0, "#") + ")") + " · BE " + str.tostring(be * 100.0, "#") + "% · net $" + str.tostring(net, "#")
string trkTxt = (lkOn ? "Master BUY / SELL" : "H2 signals (link the Master to score its BUY / SELL)") + " · stop −$" + str.tostring(trkSLd, "#.##") + " at " + str.tostring(trkLot, "#.##") + " lot = $" + str.tostring(trkSLd * trkLot * pointValue, "#") + " (" + str.tostring(trkEqPct, "#.#") + "% of equity) · " + (trkCf > 0 ? "confirm: a close $" + str.tostring(trkCfD, "#.##") + " my way within " + str.tostring(trkCfMin) + " min (website B3)" : "enter at the signal") + "\n" + f_trkCell("TP1", trkTP1d, trkW1, trkN1, trkLo1, trkHi1, trkBE1, trkNet1) + "\n" + f_trkCell("TP2", trkTP2d, trkW2, trkN2, trkLo2, trkHi2, trkBE2, trkNet2) + "\n" + f_trkCell("TP3", trkTPd, trkW, trkN, trkLo, trkHi, trkBE, trkNet) + "\nopen " + str.tostring(array.size(trkE)) + " · waiting " + str.tostring(array.size(trkQe)) + " · chance " + str.tostring(trkSLd / (trkSLd + trkTP1d) * 100.0, "#") + " / " + str.tostring(trkSLd / (trkSLd + trkTP2d) * 100.0, "#") + " / " + str.tostring(trkSLd / (trkSLd + trkTPd) * 100.0, "#") + "% · this chart's history only" + (lkOn ? "" : ", not the Master's BUY / SELL")'''


def visuals(t):
    a = t.index('trkTP = input.float(1000.0, "Bracket TP (in the unit above)"')
    b0 = t.index("\nstring trkTxt = ", a)
    b = t.index("\n", b0 + 1)
    t = t[:a] + NEW + t[b:]
    old = '_tmRow(r, "BRACKET", trkTxt, trkLv == 1 ? _tmUp : trkLv == -1 ? _tmDn : _amb)'
    assert t.count(old) == 1
    t = t.replace(old, '_tmRow(r, "BRACKET", trkTxt, trkLvAll == 1 ? _tmUp : trkLvAll == -1 ? _tmDn : _amb)')
    L = t.split("\n")
    i = next(k for k, l in enumerate(L[:6]) if "BUILD STAMP" in l)
    st = "// ║  BUILD STAMP — this file last CHANGED in v97   (3 targets + confirm)"
    L[i] = st + " " * (len(L[i + 1]) - len(st) - 1) + "║"
    return "\n".join(L)


if __name__ == "__main__":
    p = "artefacts/XAUUSD_Quantum_5_5_Visuals.pine"
    out = visuals(open(p, encoding="utf-8").read())
    open(p, "w", encoding="utf-8").write(out)
    print("fixed Visuals (v97)")
