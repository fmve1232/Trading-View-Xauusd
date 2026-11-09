"""Phase C deliverable 11: risk and position sizing, computed from the MEASURED B29 grid (development 2020-22, ENG costs,
every bar, independent series) for a set of brackets. Money at 0.50 lot is ASSUMED (100-oz contract, so $50 per $1).

For each bracket and direction:
  - the money won at the target and lost at the stop per trade (ENG costs: TP pays spread + entry slippage + commission;
    SL also pays exit slippage),
  - the measured TP-first rate, the in-session break-even of a decided trade (B29 theory p*), the expectancy per trade and per week at the measured trade rate,
  - the Kelly fraction f* = (p b - q) / b with b = win / loss (zero or below means "no position"),
  - the chance of at least L losses in a row within N trades (exact dynamic programme), and the number of stops that
    would breach example daily-loss limits.

  python research/tools/phasec_risk.py research/results/b29/b29_grid.csv
"""
import math
import sys

import pandas as pd

LOT_OZ = 50                      # 0.50 lot, ASSUMED 100-oz contract
COST_TP = 0.30 + 0.20 + 0.07     # in-session spread + entry slippage + commission ($/oz)
COST_SL = COST_TP + 0.20         # plus exit slippage
BRACKETS = ((3, 30), (5, 10), (5, 15), (8, 10), (10, 10), (15, 15), (20, 10), (20, 20), (25, 30), (30, 30))
LIMITS = (1000, 2500, 5000)      # example daily-loss limits in $ (not the operator's account rules)


def p_run(p_loss: float, run: int, n: int) -> float:
    """P(at least `run` consecutive losses somewhere in n independent trades)."""
    st = [1.0] + [0.0] * (run - 1)   # st[j] = P(current losing streak = j, no run of `run` yet)
    hit = 0.0
    for _ in range(n):
        nxt = [0.0] * run
        nxt[0] = sum(st) * (1 - p_loss)
        for j in range(run):
            if j + 1 == run:
                hit += st[j] * p_loss
            else:
                nxt[j + 1] += st[j] * p_loss
        st = nxt
    return hit


def main(path: str) -> None:
    g = pd.read_csv(path)
    g = g[g["scenario"] == "ENG"]
    print("| Bracket | Dir | Win / loss per trade (0.5 lot) | TP-first (measured) | Break-even (in session) | Exp / trade (0.5 lot) | Trades / wk | "
          "Exp / wk (0.5 lot) | Kelly f* | P(>= 5 losses in a row, 100 trades) | P(>= 10 in a row, 250 trades) | Stops to breach "
          + " / ".join(f"${x:,}" for x in LIMITS) + " |")
    print("|" + "---|" * 12)
    for tp, sl in BRACKETS:
        for dn in ("BUY", "SELL"):
            r = g[(g["tp"] == tp) & (g["sl"] == sl) & (g["dir"] == dn)]
            if r.empty:
                continue
            r = r.iloc[0]
            win, loss = (tp - COST_TP) * LOT_OZ, (sl + COST_SL) * LOT_OZ
            p = float(r["r"])
            b = win / loss
            kelly = (p * b - (1 - p)) / b
            exp_t = float(r["exp_oz"]) * LOT_OZ
            wk = float(r["per_week"])
            stops = " / ".join(str(math.ceil(x / loss)) for x in LIMITS)
            print(f"| +{tp} / −{sl} | {dn} | +${win:,.0f} / −${loss:,.0f} | {100 * p:.1f}% | {100 * float(r['theory_break_even']):.1f}% | "
                  f"{exp_t:+,.0f} | {wk:.1f} | {exp_t * wk:+,.0f} | {kelly:+.3f} | {p_run(1 - p, 5, 100):.0%} | "
                  f"{p_run(1 - p, 10, 250):.0%} | {stops} |")
    print("\nWin / loss use the in-session ENG costs; the measured expectancy also carries off-session spreads, gaps through the stop, "
          "timeouts and closures, so it is slightly worse than p x win - q x loss.")


if __name__ == "__main__":
    main(sys.argv[1])
