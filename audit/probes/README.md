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

## v85 finding and the line probes

- P1 (Master + one 600-line filler) = **108,612**; P2 (+ an identical second filler) = **108,623**.
- The identical second function body cost only its call (~11 tokens): TradingView keeps ONE copy of an identical function
  body. So P2 − P1 is not the filler's cost, and the Master's size cannot be solved from P1 / P2.
- PB300 / PC900 put a single filler of 300 / 900 lines into the same Master. The slope gives the cost per line (and
  checks it is linear); the Master = P1 − 600 × slope − the filler's small fixed part:

      python3 audit/tools/probe_gd.py --lines <PB300> 108612 <PC900>
