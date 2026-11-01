"""v96 (operator, 2026-11-01: "Go ahead with order-block retention alignment"): Visuals' order blocks ARE the engine's.
Visuals only; display only.

The SX block is re-sliced with the Master's order-block lifecycle as targets (one active block per side, invalidated on
a close 0.3 adaptive ATR beyond it, 50% mitigation, reversal blocks from failed displacement, the 5-deep history queue
per side with its mitigation flags, expiry after obMaxBars) and the engine's displacement detector they read (dispMult,
the 2.5x-enter / 1.5x-hold latch, the onset edge): 97 -> 206 Master lines, verbatim. One more stated exception: the
engine switch `showOB` (default ON) is not copied; Visuals' draw switch (default OFF) stands in, as for showFVG.
Drawing: on the last bar the boxes are rebuilt from the engine's queue (newest first, up to `obKeep`, default 5 = the
engine's queue size): from the OB candle to its expiry (detection bar + obMaxBars), faded and marked "½" once 50%
mitigated, bold while it is the engine's ACTIVE block of its side. The ticker's CHECKS tile shows 'LINK the Master' while the link is not connected (TradingView cannot connect a
source input by default: its default can only be a built-in series). Merged duplicates: Visuals' own displacement copy
(the V lines and "OB displacement (xATR)", now the engine's dispMult) and its "last N boxes" retention."""
import sys
import fix_v95 as F95

F95.TARGETS += ["obBullActive", "obBearActive", "obBullHigh", "obBullLow", "obBearHigh", "obBearLow", "obBullMitigated",
                "obBearMitigated", "obBullMitPct", "obBearMitPct", "obBullHighA", "obBullLowA", "obBullBarA", "obBullMitA",
                "obBearHighA", "obBearLowA", "obBearBarA", "obBearMitA"]
F95.SKIP |= {'showOB = input.bool(true, "Order Blocks (engine)"'}

OB_NEW = '''// v96: the boxes ARE the engine's order blocks (SX block): rebuilt on the last bar from its queue, newest first, up to
// obKeep per side; faded + "½" once 50% mitigated; bold while it is the engine's ACTIVE block of its side.
var box[] obBoxes = array.new<box>()
var label[] obZoneLbls = array.new<label>()
f_obDraw(float[] hA, float[] lA, int[] bA, bool[] mA, bool bull, bool act, float actHi) =>
    int _n = math.min(array.size(hA), obKeep)
    if _n > 0
        for _k = 0 to _n - 1
            float _h = array.get(hA, _k)
            float _l = array.get(lA, _k)
            int _b = array.get(bA, _k)
            bool _mit = array.get(mA, _k)
            bool _on = act and _k == 0 and _h == actHi
            color _oc = zoneFlatCol ? cOB : bull ? cBull : cBear
            array.push(obBoxes, box.new(_b - 1, _h, _b + obMaxBars, _l, border_color = color.new(_oc, _mit ? 88 : 60), border_width = _on ? 2 : 1, bgcolor = color.new(_oc, _mit ? math.min(boxFade + 4, 100) : boxFade)))
            if obShowLabel
                array.push(obZoneLbls, label.new(_b - 1, bull ? _h : _l, (bull ? "OB▲" : "OB▼") + (_mit ? " ½" : ""), xloc.bar_index, yloc.price, color.new(color.black, 100), bull ? label.style_label_down : label.style_label_up, _oc, size.tiny))
    true
if showOB and barstate.islast
    while array.size(obBoxes) > 0
        box.delete(array.pop(obBoxes))
    while array.size(obZoneLbls) > 0
        label.delete(array.pop(obZoneLbls))
    f_obDraw(obBullHighA, obBullLowA, obBullBarA, obBullMitA, true, obBullActive, obBullHigh)
    f_obDraw(obBearHighA, obBearLowA, obBearBarA, obBearMitA, false, obBearActive, obBearHigh)
// the FVG zone labels' cap (it lived in the old OB block)
while array.size(obLbls) > obKeep * 3
    label.delete(array.shift(obLbls))
'''


def visuals(vtext, mtext):
    M = mtext.split("\n")
    sx = F95.sx_lines(M)
    t = vtext
    a = t.index("// SX-BEGIN")
    b = t.index("// SX-END")
    head = [l for l in t[a:b].split("\n") if l.startswith("//")][:3]
    head[1] = head[1].replace("the backward slice of bosLabel* / chochLabel* / mssLabel* /", "the backward slice of bosLabel* / chochLabel* / mssLabel* / the OB lifecycle (v96) /")
    head[2] = head[2].replace("One exception: the engine switch showFVG is Visuals' draw switch.", "Exceptions: the engine switches showFVG / showOB are Visuals' draw switches.")
    t = t[:a] + "\n".join(head) + "\n" + "\n".join(sx) + "\n" + t[b:]
    # Visuals' own displacement copy -> the engine's (in SX now)
    s0 = t.index("float _bodySzV  = math.abs(close - open)\n")
    s1 = t.index("bool dispOnsetDownV = displacementDownV and not displacementDownV[1]\n")
    t = t[:s0] + "// v96: displacement is the engine's (dispMult, SX block); the V copy and its input are merged into it.\n" + t[s1 + len("bool dispOnsetDownV = displacementDownV and not displacementDownV[1]\n"):]
    d0 = t.index("obDispATR    = input.float(2.5,")
    t = t[:d0] + t[t.index("\n", d0) + 1:]
    old = 'obKeep       = input.int(4,      "Order Blocks kept", minval = 1, maxval = 10, group = grpZ)'
    assert t.count(old) == 1
    t = t.replace(old, 'obKeep       = input.int(5,      "Order Blocks shown per side (the engine keeps 5)", minval = 1, maxval = 5, group = grpZ)')
    o0 = t.index("var box[] obBoxes = array.new<box>()\n")
    o1 = t.index("        label.delete(array.shift(obLbls))\n", o0) + len("        label.delete(array.shift(obLbls))\n")
    t = t[:o0] + OB_NEW + t[o1:]
    # the link cannot be connected by default (a source input defaults only to a built-in series): say so on the ticker
    ck = '+ (ckChurn ? "CHURN · " : "")'
    assert t.count(ck) == 1
    t = t.replace(ck, ck + ' + (lkOn ? "" : "LINK the Master · ")')
    L = t.split("\n")
    i = next(k for k, l in enumerate(L[:6]) if "BUILD STAMP" in l)
    st = "// ║  BUILD STAMP — this file last CHANGED in v96   (engine order blocks)"
    L[i] = st + " " * (len(L[i + 1]) - len(st) - 1) + "║"
    return "\n".join(L)


if __name__ == "__main__":
    p = "artefacts/XAUUSD_Quantum_5_5_Visuals.pine"
    out = visuals(open(p, encoding="utf-8").read(), open(F95.M_FILE, encoding="utf-8").read())
    open(p, "w", encoding="utf-8").write(out)
    print("fixed Visuals (v96)")
