"""Broker contract specification for XAUUSD and the price <-> money <-> pip <-> point arithmetic (display only).

Not in holdout.ENGINE_SOURCES: the engine and every forward ledger keep the frozen model (1 lot = 100 oz,
config.point_value). This module serves the viewer's numbers: the high-confidence panel, "Your trade" and sizing.
site/costs.js mirrors every function here; tests/test_contract.py and tests/costs.test.mjs check that the two agree.

The defaults are a STANDARD contract and are labelled UNVERIFIED until the operator enters the MT5 symbol
specification (Market Watch -> XAUUSD -> Specification): contract size, tick size, tick value, digits, account
currency, volume step / minimum. MT5 quotes the tick value in the ACCOUNT currency, so the money per 1.00 of price
per lot is tick_value / tick_size whatever the account currency; for a USD account it must equal contract_size x
tick_size / tick_size = contract_size (checked).

Vocabulary (they are NOT interchangeable without the spec):
    price move   dollars of quoted XAUUSD price, e.g. 4000.00 -> 4010.00 is a 10.00 move
    point        one tick_size (0.01 on a 2-digit quote)
    pip          the broker's pip convention (commonly 0.10 for gold; some use 0.01); configurable
    money        profit or loss in the account currency = price move x lots x tick_value / tick_size
"""
from __future__ import annotations

import math

DEFAULT_SPEC = {
    "symbol": "XAUUSD", "contract_size": 100.0, "tick_size": 0.01, "tick_value": 1.0, "digits": 2,
    "account_currency": "USD", "pip_size": 0.10, "volume_min": 0.01, "volume_step": 0.01,
    "status": "UNVERIFIED",
    "note": "Standard contract (100 oz per lot, tick 0.01 = $1 per lot). Enter your MT5 symbol specification to verify.",
}


def validate(spec: dict) -> dict:
    """{'ok': bool, 'errors': [...], 'warnings': [...]}. Errors make every money figure unusable."""
    err, warn = [], []
    for k in ("contract_size", "tick_size", "tick_value", "pip_size", "volume_min", "volume_step"):
        v = spec.get(k)
        if not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            err.append(f"{k} must be a positive number")
    cur = str(spec.get("account_currency") or "").upper()
    if len(cur) != 3 or not cur.isalpha():
        err.append("account_currency must be a 3-letter code")
    if not err:
        implied = spec["contract_size"] * spec["tick_size"]           # USD per tick per lot on a USD account
        if cur == "USD" and abs(spec["tick_value"] - implied) > 0.01 * implied:
            err.append(f"tick_value {spec['tick_value']:g} does not match contract_size x tick_size = {implied:g} for a USD account")
        if cur != "USD":
            warn.append(f"{cur} account: the tick value moves with the {cur}/USD rate; re-read it from MT5 when it changes")
        if spec["pip_size"] < spec["tick_size"]:
            err.append("pip_size cannot be smaller than tick_size")
        if spec["volume_step"] > spec["volume_min"] + 1e-12 and abs(round(spec["volume_min"] / spec["volume_step"]) * spec["volume_step"] - spec["volume_min"]) > 1e-9:
            warn.append("volume_min is not a multiple of volume_step")
    return {"ok": not err, "errors": err, "warnings": warn}


def money_per_price(spec: dict, lots: float) -> float:
    """Account-currency profit or loss for a 1.00 move in the quoted price, at `lots`."""
    return lots * spec["tick_value"] / spec["tick_size"]


def price_to_money(spec: dict, price_move: float, lots: float) -> float:
    return price_move * money_per_price(spec, lots)


def money_to_price(spec: dict, money: float, lots: float) -> float:
    m = money_per_price(spec, lots)
    return money / m if m > 0 else math.nan


def to_pips(spec: dict, price_move: float) -> float:
    return price_move / spec["pip_size"]


def to_points(spec: dict, price_move: float) -> float:
    return price_move / spec["tick_size"]


def round_price(spec: dict, px: float) -> float:
    return round(px, int(spec.get("digits", 2)))


def lots_for_risk(spec: dict, risk_money: float, stop_move: float, cost_per_price_unit: float = 0.0) -> float:
    """Largest lot (a multiple of volume_step) whose loss at the stop, plus the round-trip cost, is within
    risk_money. Returns 0 when even the minimum lot is too large."""
    per_lot = (stop_move + cost_per_price_unit) * money_per_price(spec, 1.0)
    if not (per_lot > 0) or not (risk_money > 0):
        return 0.0
    step = spec["volume_step"]
    lots = math.floor(risk_money / per_lot / step + 1e-9) * step
    return round(lots, 8) if lots >= spec["volume_min"] - 1e-12 else 0.0


def trade_money(spec: dict, lots: float, tp_move: float, sl_move: float, cost_per_price_unit: float) -> dict:
    """Gross and net money at TP and at SL, the break-even win rate, and the price distances in pips / points."""
    m = money_per_price(spec, lots)
    cost = cost_per_price_unit * m
    out = {"money_per_price": m, "gross_tp": tp_move * m, "gross_sl": -sl_move * m, "cost": cost,
           "net_tp": tp_move * m - cost, "net_sl": -sl_move * m - cost,
           "tp_pips": to_pips(spec, tp_move), "sl_pips": to_pips(spec, sl_move),
           "tp_points": to_points(spec, tp_move), "sl_points": to_points(spec, sl_move)}
    out["break_even"] = (sl_move + cost_per_price_unit) / (tp_move + sl_move) if tp_move + sl_move > 0 else math.nan
    return out


def export() -> dict:
    return {"default": dict(DEFAULT_SPEC), "validation": validate(DEFAULT_SPEC)}
