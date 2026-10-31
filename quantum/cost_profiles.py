"""Per-account trading-cost profiles for POSITION SIZING on the site (display only).

Outside the freeze key (not in holdout.ENGINE_SOURCES). The engine, the arms and every forward-test ledger keep the
frozen cost model in config.py: session spread + 2 x 0.20 slippage + $7 per lot round turn. A profile here changes
only the lot size and "loss at stop" the Risk & sizing card shows for the account the operator picks.

No rate is VERIFIED until the operator's own MT5 evidence (symbol specification + a closed trade's IN and OUT deals)
confirms it. Until then each profile carries the firm's published figure, status UNVERIFIED, and, where the firm does
not say whether the fee is per side or round turn, sizing uses the HIGHER reading (per side, charged twice).
Sources are the firms' help-centre pages as found on 2026-11-01 (audit/COST_PROFILES.md).
"""
from __future__ import annotations

import math

CONTRACT_OZ = 100.0          # XAUUSD: 1 lot = 100 oz on both firms (their published contract specification)
BASES = ("per_side", "round_turn", "open_only", "unconfirmed")

# commission: type "fixed" = USD per lot; type "pct" = percent of notional (lots x 100 oz x price)
PROFILES = [
    dict(id="engine", firm="Engine (frozen)", account="Forward-test cost model",
         commission=dict(type="fixed", rate=7.0, basis="round_turn"), spread=dict(mode="engine", value=None), slippage=0.20,
         status="FROZEN", source="quantum/config.py (commission_l 7.0, slippage_pts 0.20, spread_cost 0.30)",
         note="What every arm and ledger is charged. Changing it needs a pre-registration amendment."),
    dict(id="fp_standard", firm="FundingPips", account="Standard (1-Step / 2-Step / Flex)",
         commission=dict(type="fixed", rate=5.0, basis="unconfirmed"), spread=dict(mode="engine", value=None), slippage=0.20,
         status="UNVERIFIED", source="https://help.fundingpips.com/hc/en-us/articles/44390730743825-Get-Started",
         note="Published $5 per lot; per side or round turn not stated."),
    dict(id="fp_zero", firm="FundingPips", account="Zero",
         commission=dict(type="fixed", rate=7.0, basis="unconfirmed"), spread=dict(mode="engine", value=None), slippage=0.20,
         status="UNVERIFIED", source="https://help.fundingpips.com/hc/en-us/articles/34502157694865-FundingPips-Zero",
         note="Published $7 per lot; per side or round turn not stated."),
    dict(id="fp_swapfree", firm="FundingPips", account="Swap-free (MT5)",
         commission=dict(type="fixed", rate=10.0, basis="unconfirmed"), spread=dict(mode="engine", value=None), slippage=0.20,
         status="UNVERIFIED", source="https://help.fundingpips.com/hc/en-us/articles/44390730743825-Get-Started",
         note="Published $10 per lot on swap-free MT5; basis not stated."),
    dict(id="fp_prime", firm="FundingPips", account="Prime",
         commission=dict(type="fixed", rate=10.0, basis="unconfirmed"), spread=dict(mode="engine", value=None), slippage=0.20,
         status="UNVERIFIED", source="https://help.fundingpips.com/hc/en-us/articles/34447308895889-Prime-Account",
         note="Published flat $10 per lot (all instruments except crypto); basis not stated."),
    dict(id="fn_stellar_1step", firm="FundedNext", account="Stellar 1-Step",
         commission=dict(type="pct", rate=0.0016, basis="per_side"), spread=dict(mode="engine", value=None), slippage=0.20,
         status="UNVERIFIED", source="https://fundednext.com/general-rules/cfds/symbols-and-conditions",
         note="0.0016% of notional, 'charged per side' (symbols page). A help article says open-only for Instant; "
              "a new schedule is announced from 12/01/2026."),
    dict(id="fn_stellar_2step", firm="FundedNext", account="Stellar 2-Step",
         commission=dict(type="pct", rate=0.0016, basis="per_side"), spread=dict(mode="engine", value=None), slippage=0.20,
         status="UNVERIFIED", source="https://fundednext.com/general-rules/cfds/symbols-and-conditions",
         note="As Stellar 1-Step."),
    dict(id="fn_stellar_instant", firm="FundedNext", account="Stellar Instant",
         commission=dict(type="pct", rate=0.0016, basis="open_only"), spread=dict(mode="engine", value=None), slippage=0.20,
         status="UNVERIFIED",
         source="https://help.fundednext.com/en/articles/11641300-what-are-the-commission-charges-for-the-stellar-instant-account",
         note="Help article: 0.0016% on the opening price, nothing at close. Conflicts with the symbols page's per-side wording."),
    dict(id="fn_stellar_lite", firm="FundedNext", account="Stellar Lite",
         commission=dict(type="pct", rate=0.0018, basis="per_side"), spread=dict(mode="engine", value=None), slippage=0.20,
         status="UNVERIFIED", source="https://fundednext.com/general-rules/cfds/symbols-and-conditions",
         note="0.0018% of notional per side (symbols page)."),
    dict(id="custom", firm="Custom", account="Other account",
         commission=dict(type="fixed", rate=7.0, basis="round_turn"), spread=dict(mode="engine", value=None), slippage=0.20,
         status="USER", source="entered by the viewer", note="Edit the fields; stored in this browser only."),
]


def _sides(basis: str, conservative: bool = True) -> float:
    """How many times the quoted fee is paid on one round trip."""
    if basis == "per_side":
        return 2.0
    if basis in ("round_turn", "open_only"):
        return 1.0
    return 2.0 if conservative else 1.0          # unconfirmed: the higher reading for sizing


def commission_per_lot(profile: dict, price: float, conservative: bool = True) -> float:
    """Round-trip commission in USD for one lot at this price."""
    c = profile["commission"]
    rate = float(c["rate"])
    if not (rate >= 0 and math.isfinite(rate)):
        return math.nan
    if c["type"] == "pct":
        if not (price > 0 and math.isfinite(price)):
            return math.nan
        per = CONTRACT_OZ * price * rate / 100.0     # percent of notional; the close leg is priced at entry (stated)
    else:
        per = rate
    return per * _sides(c["basis"], conservative)


def round_trip_cost_per_oz(profile: dict, price: float, engine_spread: float, conservative: bool = True) -> float:
    """Spread + 2 x slippage + commission / 100 oz: the engine's own formula, with this profile's inputs.
    Spread and slippage are counted once each (spread is a round-trip quantity; slippage is per side)."""
    s = profile["spread"]
    spread = engine_spread if s["mode"] == "engine" else float(s["value"])
    return spread + 2.0 * float(profile["slippage"]) + commission_per_lot(profile, price, conservative) / CONTRACT_OZ


def export() -> list[dict]:
    """The profiles as the site reads them (payload['cost_profiles'])."""
    return [dict(p, commission=dict(p["commission"]), spread=dict(p["spread"])) for p in PROFILES]
