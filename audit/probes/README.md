# Probes: the real compiled cost of the gold drivers in the Master (F-A68)

These are **measuring instruments, not chart scripts**. Each one is the v69 / v72 Master with a meaningless filler
function added, which pushes it over TradingView's 100,256-token limit on purpose. Over the limit, TradingView prints the
exact count (`Compiled code contains too many tokens: N`). Every probe carries the same filler, so the difference
between two counts is the exact cost of what the two probes differ by.

| Probe | Content | Gives |
|---|---|---|
| P1 | v69 + filler | baseline `a` |
| P2 | v69 + filler × 2 | the filler's cost (`b − a`), then the v69 Master's real count and its headroom |
| P3 | P1 + the five gold drivers, as v70 / v71 placed them (block, MACRO arrows, tooltip) | drivers' cost `c − a` |
| P4 | P3 without the two `ta.correlation` lines | the correlations' cost `c − d` |
| P5 | P1 + the v71 cell queues, no drivers | whether the queues saved or cost tokens (`e − a`) |

Paste each one into a **new, separate indicator** in the Pine Editor, never into the Master. Read the token number
from the error, then delete the probe script. Solve with:

    python3 audit/tools/probe_gd.py a b c d e

`probe_gd.py` rebuilds the probes from the v66 commit through `fix_v68` (= the v69 Master). It checks that each probe
is that file plus insertions only: the indicator title, and for P3 / P4 the MACRO cell line.
