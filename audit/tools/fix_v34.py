"""APPLIED in v34 (before the 2026-10-05 holdout start; PREREGISTRATION amendment A2).
F-A40: MTF confluence and MTF confidence normalised by the layers AVAILABLE on the chart's timeframe.
Usage: python3 audit/tools/fix_v34.py artefacts/<engine files>; then regenerate Diagnostics."""
import sys
CONF_OLD = "mtfConfluenceScore = int(math.round((mtfConfluenceBull - mtfConfluenceBear) / 10.0 * 100.0))\n"
CONF_NEW = """// v34 F-A40: a layer at or below the chart's timeframe is not a higher timeframe and scores a
// neutral 50, so it can never vote. The fixed /10 denominator therefore capped the score by
// timeframe: at most 9 of 10 votes on 5M, 8 on 15M, 7 on 1H. The same market scored lower on 15M
// than on 5M purely because of the chart. Normalised by the votes AVAILABLE on this timeframe
// (MTF layers above the chart + the 6 macro votes); identical to before wherever all 4 layers vote.
int mtfAvail = (htf5mAvailable ? 1 : 0) + (htf15mAvailable ? 1 : 0) + (htf1hAvailable ? 1 : 0) + (htf4hAvailable ? 1 : 0)
mtfConfluenceScore = int(math.round((mtfConfluenceBull - mtfConfluenceBear) / (mtfAvail + 6.0) * 100.0))
"""
MTF_OLD = "confMTF = int(math.round(math.max(htfFullLong, htfFullShort) * 100.0 / 5.0))\n"
MTF_NEW = """// v34 F-A40: same normalisation for the 5-layer agreement (layers above the chart only).
int htfFullAvail = math.max(mtfAvail + (htf1dAvailable ? 1 : 0), 1)
confMTF = int(math.round(math.max(htfFullLong, htfFullShort) * 100.0 / htfFullAvail))
"""
for p in sys.argv[1:]:
    s = open(p, encoding="utf-8").read()
    for o, n in ((CONF_OLD, CONF_NEW), (MTF_OLD, MTF_NEW)):
        assert s.count(o) == 1, (p, o[:50])
        s = s.replace(o, n)
    open(p, "w", encoding="utf-8").write(s)
    print("patched", p)
