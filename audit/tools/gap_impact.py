"""Amendment 14 impact study: run the engine on a market-data store copy (offline) and compare fill rules.
Usage (repo root):  TWELVEDATA_API_KEY=offline PYTHONPATH=. python audit/tools/gap_impact.py <store copy> 5m,15m,1h out.json
The key only selects the Twelve Data XAU/USD series in the store; no request is made (network calls are disabled)."""
import sys, os, math, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from types import SimpleNamespace
from quantum.data import market as mk, sources as _src
def _off(*a, **k): raise _src.FetchError("offline audit run")
_src._get = _off
from quantum import engine, backtest, arm_h4
from quantum.config import DEFAULT
import gapsim
store, tfs, outp = sys.argv[1], sys.argv[2].split(","), sys.argv[3]
FSTART = "2026-10-17T21:26:18"
dl = mk.download_all(store, ("5m", "15m", "60m"))
def st(tr):
    m = backtest.metrics(tr)
    if not m.get("n"): return {"n": 0}
    return {k: (round(m[k], 4) if isinstance(m.get(k), float) else m.get(k)) for k in ("n", "win_rate", "avg_r", "t_stat", "profit_factor", "max_dd_r", "max_dd_pct", "sum_r")}
out = {}
for tf in tfs:
    m = mk.build_market(tf, dl)
    res = engine.run(m, DEFAULT, "treatment")
    F = res.F; n = len(F["c"])
    ev4 = arm_h4.evaluate(res)
    h4 = SimpleNamespace(F=F, rows={**{k: res.rows[k] for k in ("tq", "cal_p_long", "cal_p_short", "plan_ev")},
                                    **{k: ev4[k] for k in ("exec_buy", "exec_sell", "plan_sl", "plan_tp1", "plan_tp2")}})
    for name, r in (("treatment", res), ("h4", h4)):
        prod = backtest.simulate(r, DEFAULT)
        cur = gapsim.simulate(r, DEFAULT, "current")
        same = [(t["entry_i"], t["exit_i"], t["pts"]) for t in prod] == [(t["entry_i"], t["exit_i"], t["pts"]) for t in cur]
        pine = gapsim.simulate(r, DEFAULT, "current", spread_override=np.full(n, 0.30))
        g1 = gapsim.simulate(r, DEFAULT, "stop"); g2 = gapsim.simulate(r, DEFAULT, "both")
        fw = lambda T: [t for t in T if t["entry_time"] >= FSTART]
        gaps = [t for t in g1 if t["exit_reason"].endswith("_GAP")]
        changed = sum(1 for a, b in zip(cur, g1) if (a["entry_i"], a["exit_i"], a["pts"]) != (b["entry_i"], b["exit_i"], b["pts"]))
        worst = sorted(((round(t["r"], 3), t["exit_time"][:16]) for t in gaps))[:3]
        row = dict(bars=n, start=str(F["index"][0]), end=str(F["index"][-1]), reproduces_production=same,
                   current=st(cur), pine_fixed_spread=st(pine), gap_stop=st(g1), gap_stop_and_limit=st(g2),
                   fwd_current=st(fw(cur)), fwd_gap_stop=st(fw(g1)), fwd_gap_both=st(fw(g2)),
                   gap_exits=len(gaps), trades_changed=changed, worst_gap_r=worst,
                   limit_gap_fills=sum(1 for a, b in zip(g1, g2) if a["pts"] != b["pts"]))
        out[f"{tf}/{name}"] = row
        print(tf, name, json.dumps(row), flush=True)
json.dump(out, open(outp, "w"), indent=1)
