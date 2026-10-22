"""v86 (Phase 1 audit, item 1): the Master's SIGNAL cell printed its forecast scores as "L 52% S 30% R 18%", which reads
as win probabilities. They are scores: Diagnostics' reliability table (Oct 2026) shows the top band predicting 52% and
delivering 26%. The cell now prints "score L 52 S 30 R 18". Display text only: no value, gate or input changes, and the
expression loses one concatenation and one literal (fewer compiled tokens than the v83 file, which compiled). Applied
to the Master only (the line is Master-only: the arms, Diagnostics and Brief have no _probDisp)."""
import fix_v83 as F83

OLD = ('string _probDisp = _confDirLabel + "\\nL " + _si(na(fBullScore) ? 50 : fBullScore) + "% S " + _si(na(fBearScore) ? 50 : '
       'fBearScore) + "% R " + _si(na(fRngScore) ? 0 : fRngScore) + "%"')
NEW = ('string _probDisp = _confDirLabel + "\\nscore L " + _si(na(fBullScore) ? 50 : fBullScore) + " S " + _si(na(fBearScore) ? 50 : '
       'fBearScore) + " R " + _si(na(fRngScore) ? 0 : fRngScore)')
STAMP_M = "// ║  BUILD STAMP — this file last CHANGED in v86   (SIGNAL cell: scores)"


def master(text):
    """the v86 Master from the v83 Master: the SIGNAL cell text, and the stamp line"""
    assert text.count(OLD) == 1, "SIGNAL cell is not the v83 line"
    L = text.replace(OLD, NEW).split("\n")
    i = next(k for k, l in enumerate(L[:6]) if "BUILD STAMP" in l)
    L[i] = STAMP_M + " " * (len(L[i + 1]) - len(STAMP_M) - 1) + "║"
    return "\n".join(L)


if __name__ == "__main__":
    p = "artefacts/XAUUSD_Quantum_5_0_Master.pine"
    src = open(p, encoding="utf-8").read()
    open(p, "w", encoding="utf-8").write(master(src))
    print("fixed Master")
