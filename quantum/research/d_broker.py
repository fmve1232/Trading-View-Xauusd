"""Phase D broker calibration (research/broker/BROKER_SPEC_TEMPLATE.json). Research only.

The validator REFUSES a specification with any required field missing, empty, null, or marked ASSUMED / UNKNOWN / TBD:
no value is ever substituted. It converts a verified specification into per-lot money terms and keeps two things apart:
  * theoretical price movement: USD per ounce per $1 of gold (always 1), the strategy's unit everywhere in Phase D;
  * executable account P&L: per lot, from the broker's contract size, tick size / value, commission, typical spread and
    slippage, in the account currency.
The operator's balance is an INPUT of the risk report only (rule: never an optimisation variable); nothing selects on it.
"""
from __future__ import annotations

import json
import math
import sys

REQUIRED = {
    "broker_name": str, "server": str, "symbol": str, "account_currency": str, "account_type": str,
    "contract_size_oz": float, "min_lot": float, "lot_step": float, "max_lot": float,
    "tick_size": float, "tick_value_account_ccy": float, "digits": int,
    "commission_per_lot_round_trip_account_ccy": float, "typical_spread_points": float, "spread_source": str,
    "slippage_assumption_points": float, "slippage_source": str,
    "margin_percent": float, "leverage": float, "stop_out_level_percent": float,
    "swap_long_per_lot_account_ccy": float, "swap_short_per_lot_account_ccy": float,
    "server_time_zone": str, "trading_hours_utc": str, "spec_source": str, "spec_date": str,
}
POSITIVE = ("contract_size_oz", "min_lot", "lot_step", "max_lot", "tick_size", "tick_value_account_ccy", "leverage")
NON_NEGATIVE = ("commission_per_lot_round_trip_account_ccy", "typical_spread_points", "slippage_assumption_points",
                "margin_percent", "stop_out_level_percent")
REFUSED_TEXT = ("ASSUMED", "UNKNOWN", "TBD", "N/A", "NA", "?", "TODO", "")


class SpecError(ValueError):
    pass


def validate(spec: dict) -> dict:
    """Returns the cleaned specification or raises SpecError listing EVERY problem."""
    bad, out = [], {}
    for k, typ in REQUIRED.items():
        v = spec.get(k)
        if v is None or (isinstance(v, str) and v.strip().upper() in REFUSED_TEXT):
            bad.append(f"{k}: missing (never assumed)")
            continue
        try:
            out[k] = typ(v) if typ is not str else str(v).strip()
        except (TypeError, ValueError):
            bad.append(f"{k}: {v!r} is not a {typ.__name__}")
            continue
        if typ in (float, int) and not math.isfinite(float(out[k])):
            bad.append(f"{k}: not finite")
    for k in POSITIVE:
        if k in out and out[k] <= 0:
            bad.append(f"{k}: must be > 0")
    for k in NON_NEGATIVE:
        if k in out and out[k] < 0:
            bad.append(f"{k}: must be >= 0")
    if "min_lot" in out and "lot_step" in out and "max_lot" in out:
        if out["min_lot"] > out["max_lot"]:
            bad.append("min_lot > max_lot")
        steps = out["min_lot"] / out["lot_step"]
        if abs(steps - round(steps)) > 1e-6:
            bad.append("min_lot is not a whole number of lot_step")
    if "tick_size" in out and "digits" in out and out["tick_size"] < 10.0 ** -out["digits"] * (1 - 1e-9):
        bad.append("tick_size is finer than the quoted digits")
    if {"contract_size_oz", "tick_size", "tick_value_account_ccy", "account_currency"} <= set(out) and out["account_currency"] == "USD":
        implied = out["contract_size_oz"] * out["tick_size"]
        if abs(implied - out["tick_value_account_ccy"]) > 1e-6 * max(1.0, implied):
            bad.append(f"tick_value {out['tick_value_account_ccy']} != contract_size x tick_size = {implied} for a USD account")
    if bad:
        raise SpecError("; ".join(bad))
    return out


def money_terms(spec: dict, lots: float) -> dict:
    """Per-trade money terms at `lots` from a VALIDATED specification (account currency)."""
    s = validate(spec)
    steps = lots / s["lot_step"]
    if lots < s["min_lot"] or lots > s["max_lot"] or abs(steps - round(steps)) > 1e-6:
        raise SpecError(f"{lots} lots is not tradeable (min {s['min_lot']}, step {s['lot_step']}, max {s['max_lot']})")
    per_usd_move = s["tick_value_account_ccy"] / s["tick_size"] * lots         # account ccy per $1 of gold
    point = 10.0 ** -s["digits"]
    spread_usd = s["typical_spread_points"] * point
    slip_usd = s["slippage_assumption_points"] * point
    return {"lots": lots, "ounces": s["contract_size_oz"] * lots, "per_usd_move_account_ccy": per_usd_move,
            "round_trip_cost_account_ccy": spread_usd * per_usd_move + 2 * slip_usd * per_usd_move
            + s["commission_per_lot_round_trip_account_ccy"] * lots,
            "round_trip_cost_usd_per_oz": spread_usd + 2 * slip_usd + s["commission_per_lot_round_trip_account_ccy"] / s["contract_size_oz"],
            "spread_usd_per_oz": spread_usd, "slippage_usd_per_oz_each_side": slip_usd, "account_currency": s["account_currency"]}


def margin(spec: dict, lots: float, price: float) -> float:
    """Margin in USD at `price` (contract x lots x price x margin %); converting to a non-USD account needs a rate."""
    s = validate(spec)
    return price * s["contract_size_oz"] * lots * s["margin_percent"] / 100.0


def account_pnl(net_usd_per_oz: list[float], spec: dict, lots: float) -> dict:
    """Executable P&L in the account currency from a strategy's net USD per oz (which already includes the research
    cost model). Reported next to, never in place of, the theoretical $ per oz figures. Development figures are
    4000-equivalent (scaled by price / 4000), so their account P&L is illustrative, not literal; 2026 figures are literal."""
    m = money_terms(spec, lots)
    acct = [x * m["per_usd_move_account_ccy"] for x in net_usd_per_oz]
    return {"lots": lots, "trades": len(acct), "total_account_ccy": float(sum(acct)), "mean_account_ccy": float(sum(acct) / len(acct)) if acct else None,
            "account_currency": m["account_currency"]}


def main(argv=None) -> int:
    path = (argv or sys.argv[1:])[0]
    with open(path) as fh:
        spec = json.load(fh)
    try:
        s = validate(spec)
    except SpecError as e:
        print(json.dumps({"valid": False, "problems": str(e).split("; ")}, indent=1))
        return 1
    m = money_terms(s, s["min_lot"])
    print(json.dumps({"valid": True, "per_usd_move_at_min_lot": m["per_usd_move_account_ccy"],
                      "round_trip_cost_usd_per_oz": m["round_trip_cost_usd_per_oz"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
