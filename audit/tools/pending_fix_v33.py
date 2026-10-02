"""PENDING (needs operator approval: it changes signals, so it restarts the forward test).
F-A38 (constrained calibration fit) + F-A39 (Cornish-Fisher domain) for every engine copy.
Usage: python3 audit/tools/pending_fix_v33.py artefacts/<engine files>; then regenerate Diagnostics."""
import sys, re
BULL_OLD = """                if _pfVr > 1e-6
                    float _pfK = (_pfSxy / _pfSw - _pfMx * _pfMy) / _pfVr
                    if _pfK > 0
                        array.set(gCalFit, 0, math.min(math.max(_pfK, 0.02), 0.25))
                        array.set(gCalFit, 1, math.min(math.max(_pfMy - _pfK * _pfMx, -1.0), 1.0))
"""
BULL_NEW = """                // v33 F-A38: constrained WLS. The slope is projected onto [0, 0.25] (0 = the bins show no
                // resolution, so the fit is the weighted base rate) instead of (a) rejecting K <= 0 and
                // keeping a stale earlier fit, and (b) flooring K at 0.02, which manufactured resolution
                // the bins did not show. The intercept is re-solved for the slope USED, so the line still
                // passes through the weighted centroid. +-5 on the intercept is a numerical guard only.
                float _pfK = _pfVr > 1e-6 ? math.min(math.max((_pfSxy / _pfSw - _pfMx * _pfMy) / _pfVr, 0.0), 0.25) : 0.0
                array.set(gCalFit, 0, _pfK)
                array.set(gCalFit, 1, math.min(math.max(_pfMy - _pfK * _pfMx, -5.0), 5.0))
"""
BEAR_OLD = """                if _bfVr > 1e-6
                    float _bfK = (_bfSxy / _bfSw - _bfMx * _bfMy) / _bfVr
                    if _bfK < 0
                        array.set(gCalFitBear, 0, math.min(math.max(_bfK, -0.25), -0.02))
                        array.set(gCalFitBear, 1, math.min(math.max(_bfMy - _bfK * _bfMx, -1.0), 1.0))
"""
BEAR_NEW = """                // v33 F-A38: the same constrained fit, slope projected onto [-0.25, 0].
                float _bfK = _bfVr > 1e-6 ? math.min(math.max((_bfSxy / _bfSw - _bfMx * _bfMy) / _bfVr, -0.25), 0.0) : 0.0
                array.set(gCalFitBear, 0, _bfK)
                array.set(gCalFitBear, 1, math.min(math.max(_bfMy - _bfK * _bfMx, -5.0), 5.0))
"""
CF_OLD = "if _cfValid and math.abs(retSkew) < 1.5 and math.abs(retKurt) < 7.0 and not na(retZScoreRaw)\n"
CF_NEW = """// v33 F-A39: q(w) is monotone -- so the inverse exists -- only if a2 = K/8 - S^2/6 > 0 and
// (S/3)^2 - 4 a2 (1 - K/8 + 5 S^2/36) < 0 (Maillard 2012). Outside that domain the 6-step Newton
// had no solution to converge to and the 0.1 step floor made it diverge (to 1e43 in a test).
// There the observed z is used as is, exactly as when the moments are out of range.
float _cfA2 = _cfK / 8.0 - retSkewC * retSkewC / 6.0
bool _cfMono = _cfA2 > 0 and (retSkewC / 3.0) * (retSkewC / 3.0) - 4.0 * _cfA2 * (1.0 - _cfK / 8.0 + 5.0 * retSkewC * retSkewC / 36.0) < 0
if _cfValid and _cfMono and math.abs(retSkew) < 1.5 and math.abs(retKurt) < 7.0 and not na(retZScoreRaw)
"""
for p in sys.argv[1:]:
    s = open(p, encoding="utf-8").read()
    for o, n in ((BULL_OLD, BULL_NEW), (BEAR_OLD, BEAR_NEW), (CF_OLD, CF_NEW)):
        assert s.count(o) == 1, (p, o[:50])
        s = s.replace(o, n)
    open(p, "w", encoding="utf-8").write(s)
    print("patched", p)
