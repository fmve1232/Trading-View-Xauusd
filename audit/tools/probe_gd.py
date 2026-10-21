#!/usr/bin/env python3
"""Measure the real compiled cost of the gold drivers in the Master (F-A68), with TradingView as the meter.

TradingView prints the exact token count only when a script is OVER the limit (CE10117). So every probe is the v69
Master (the file that compiled; = the v72 Master) plus the same filler function PAD1, which pushes it over; the
difference between two reported counts is the exact cost of what the two probes differ by.

  P1 = v69 + PAD1                                   -> a
  P2 = v69 + PAD1 + PAD2 (an identical second pad)  -> b      PAD = b - a,  v69 real = a - PAD,  headroom = 100,256 - v69
  P3 = P1 + GD block + driver display               -> c      drivers, as v70 / v71 placed them = c - a
  P4 = P3 without the two ta.correlation lines      -> d      the two correlations = c - d
  P5 = P1 + the v71 cell queues (no drivers)        -> e      queue effect = e - a   (the model said about -1,950)

The probes are measuring instruments, NOT chart scripts: the filler is meaningless. Each is written to audit/probes/
and checked here to be the v69 Master plus insertions only.
Usage: python3 audit/tools/probe_gd.py                  (write the probes)
       python3 audit/tools/probe_gd.py a b c d e        (solve from the five reported counts)"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fix_v68 as F68  # noqa: E402
import fix_v71 as F71  # noqa: E402
import fix_v83 as F83  # noqa: E402

LIMIT = 100256
M = "artefacts/XAUUSD_Quantum_5_0_Master.pine"
OUT = "audit/probes"
PAD_LINES = 600


def pad(n, lines=None):
    return ([f"// PROBE filler {n}: meaningless arithmetic so the compiler reports a count; identical in every probe",
             f"f_probePad{n}(float x) =>", "    float p = x"] + ["    p := p * 0.5 + 1.0"] * (lines or PAD_LINES) + ["    p"])


def build():
    v66 = subprocess.run(["git", "show", "a5fc12ce:" + M], capture_output=True, text=True, check=True).stdout
    v69 = F83.master(F68.transform(v66, inline_one_call=False))   # v85: the Master on the chart (= v69 + the F-A71 label text)
    assert v69 == open(M, encoding="utf-8").read(), "the Master is not the v83 file"
    V = open("artefacts/XAUUSD_Quantum_5_5_Visuals.pine", encoding="utf-8").read()
    fence = V[V.index("// GD-BEGIN"):V.index("// GD-END") + len("// GD-END")]

    def with_pads(text, pads, lines=None):
        L = text.split("\n")
        L[0:0] = []
        i = next(k for k, l in enumerate(L) if l.startswith("indicator("))
        L[i] = L[i].replace('indicator("XAUUSD Quantum 5.0"', 'indicator("PROBE - not for trading"')
        a = L.index("// H2-BEGIN")
        body = sum((pad(n, lines) for n in pads), [])
        use = ["plot(" + " + ".join(f"f_probePad{n}(close)" for n in pads) + ', "probe", display=display.none)']
        L[a:a] = body + use
        return "\n".join(L)

    def drivers(text, corr=True):
        L = text.split("\n")
        t = L.index(F71.TCB_DEF[0])
        L[t:t] = F71.NEW_DEF[2:]                      # f_gdG
        k = next(k for k, l in enumerate(L) if F71.MACRO_OLD in l)
        ind = L[k][:len(L[k]) - len(L[k].lstrip())]
        L[k] = L[k].replace(F71.MACRO_OLD, F71.MACRO_NEW)
        L[k + 1:k + 1] = [ind + "if not _dashMobile and not _dashStrip", ind + "    table.cell_set_tooltip(tblA, 6, 2, " + F71.TIP + ")"]
        fl = fence.split("\n")
        if not corr:
            fl = [("float brJr = na" if l.startswith("float brJr = ") else "float brOr = na" if l.startswith("float brOr = ") else l)
                  for l in fl]
            assert "float brJr = na" in fl and "float brOr = na" in fl
        a = L.index("// H2-BEGIN")
        L[a:a] = fl
        return "\n".join(L)

    def queues(text):
        mn, q0 = F71.MACRO_NEW, F71.Q["tcb"][2]
        F71.MACRO_NEW = F71.MACRO_OLD                    # the MACRO cell exactly as in v69
        F71.Q["tcb"] = (F71.Q["tcb"][0], F71.Q["tcb"][1], q0[:-2])   # no driver tooltip
        try:
            q = F71.transform(text, "")
        finally:
            F71.MACRO_NEW, F71.Q["tcb"] = mn, (F71.Q["tcb"][0], F71.Q["tcb"][1], q0)
        q = q.replace("\n".join(F71.NEW_DEF[2:]) + "\n", "")
        L = q.split("\n")
        i = next(k for k, l in enumerate(L[:6]) if "BUILD STAMP" in l)
        L[i] = text.split("\n")[i]
        a = L.index("// H2-BEGIN")
        assert L[a - 1] == "", L[a - 1]          # the empty fence F71 inserted
        del L[a - 1]
        out = "\n".join(L)
        assert "f_gdG" not in out and "brJ" not in out
        return out

    # v85: P1 / P2 showed that an IDENTICAL second filler costs ~0 (108,612 vs 108,623): TradingView keeps one copy of
    # an identical function body. So the Master's size is measured with ONE filler of 300 / 600 (P1) / 900 lines
    # instead: per-line cost = slope, linearity checked, Master = P1 - 600 x slope - the filler's fixed part.
    P = {"PB300": with_pads(v69, [1], 300), "PC900": with_pads(v69, [1], 900), "P1": with_pads(v69, [1]), "P2": with_pads(v69, [1, 2]), "P3": with_pads(drivers(v69), [1]),
         "P4": with_pads(drivers(v69, corr=False), [1]), "P5": with_pads(queues(v69), [1])}
    os.makedirs(OUT, exist_ok=True)
    for k, t in P.items():
        open(f"{OUT}/{k}.pine", "w", encoding="utf-8").write(t)
    return v69, P


def solve_lines(b300, a600, c900):
    s1, s2 = (a600 - b300) / 300.0, (c900 - a600) / 300.0
    print(f"per filler line: {s1:.3f} (300->600)  {s2:.3f} (600->900)  {'linear' if abs(s1 - s2) <= 0.5 else 'NOT linear: the per-line model does not hold'}")
    slope = (c900 - b300) / 600.0
    fixed = a600 - 600 * slope
    print(f"Master + filler's fixed part (call, plot, header) = {fixed:,.0f}; the fixed part is a few dozen tokens, so the Master is"
          f" about {fixed - 40:,.0f} .. {fixed:,.0f}; headroom under {LIMIT:,}: about {LIMIT - fixed:,.0f} .. {LIMIT - fixed + 40:,.0f}")


def solve(a, b, c, d, e):
    padc = b - a
    v69 = a - padc
    head = LIMIT - v69
    drv, corr, q = c - a, c - d, e - a
    print(f"PAD (one filler)            {padc:7,}")
    print(f"v69 Master, real            {v69:7,}   headroom under {LIMIT:,}: {head:,}")
    print(f"gold drivers (block+display) {drv:+7,}   of which the two correlations {corr:+,}, the rest {drv - corr:+,}")
    print(f"v71 cell queues             {q:+7,}")
    print(f"check: v70/v71 ~ v69 + drivers + queues = {v69 + drv + q:,} (v71 reported 104,510; v70 103,989 with DCell queues)")
    print(f"drivers fit in the Master if {drv:,} - savings <= {head:,}: need {max(0, drv - head):,} tokens of identical-output savings")


if __name__ == "__main__":
    if len(sys.argv) == 6:
        solve(*map(int, sys.argv[1:]))
        sys.exit(0)
    if len(sys.argv) == 5 and sys.argv[1] == "--lines":
        solve_lines(*map(int, sys.argv[2:]))
        sys.exit(0)
    v69, P = build()
    import difflib
    for k, t in P.items():
        old, new = v69.split("\n"), t.split("\n")
        removed = [l for l in difflib.ndiff(old, new) if l.startswith("- ")]
        print(f"{k}: {len(new)} lines, {len(t.encode()):,} bytes, removed/changed v69 lines: {len(removed)}")
