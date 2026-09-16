"""All 72 Quantum 5.0 edge-case assertions, ported to Python.

Master prompt section 60: "Port all Quantum 5.0 Edge Case tests into Python."

Each case below mirrors one ``chk(...)`` call in
``reference/quantum_5_0/XAUUSD_Quantum_5_0_EdgeCases.pine``, keeping the
harness's own ID, its WANT value and its classification letter
(BUG / STAT / NUM / PRES / DESIGN).

The comparison is on FORMATTED STRINGS, not floats, because that is what the
harness compares. ``pine_tostring`` reproduces ``str.tostring(v, "#.####")``,
including the half-away-from-zero rounding that makes D2 read 0.0313 rather
than Python's 0.0312.

READ THIS BEFORE TRUSTING A GREEN RUN
-------------------------------------
The WANT values are the harness's, so a green suite establishes that the Python
port agrees with the Pine harness. It does NOT establish that either agrees
with the Master's live wiring -- the harness says so itself -- and it is not a
substitute for running the harness on TradingView. Phase 6 parity is measured
against bar data. See ``docs/PARITY_PLAN.md``.
"""

from __future__ import annotations

import pytest
from quantum_parity.edge_cases import (
    bayes_rate,
    bucket_qualifies,
    cal_bin_count,
    cal_bin_win,
    cost_charged,
    fit_accepted,
    intercept_clamp,
    macro_need,
    macro_regime,
    prob_clamp,
    regime_category,
    resolve_race,
    safe_div,
    slope_clamp,
)
from quantum_parity.edge_cases import (
    cost_charged as _cost,
)

from quantum_institutional.pine.semantics import (
    NA,
    is_na,
    pine_int,
    pine_max,
    pine_nz,
    pine_round,
    pine_sigmoid,
    pine_tostring,
)


def f(v: float) -> str:
    """Harness helper ``f()``: float rendered as ``#.####`` or ``na``."""
    return pine_tostring(v)


def i(v) -> str:
    """Harness helper ``i()``: int rendered, or ``na``."""
    return "na" if is_na(v) else str(int(v))


def b(v: bool) -> str:
    """Harness helper ``b()``: ``true`` / ``false``."""
    return "true" if v else "false"


_NAN = NA

# (case_id, got, want, classification)
CASES: list[tuple[str, str, str, str]] = [
    # -- GROUP A: rounding at regime boundaries (F-021 CLOSED) --------------
    ("A1  raw 39.49 -> category", i(regime_category(39.49)), "2", "STAT"),
    ("A2  raw 39.50 -> category (was 1, now 2)", i(regime_category(39.50)), "2", "STAT"),
    ("A3  raw 39.51 -> category", i(regime_category(39.51)), "1", "STAT"),  # STALE: F-A18
    ("A4  raw 69.49 -> category", i(regime_category(69.49)), "1", "STAT"),
    ("A5  raw 69.50 -> category (was 0, now 1)", i(regime_category(69.50)), "1", "STAT"),
    ("A6  raw 69.51 -> category", i(regime_category(69.51)), "0", "STAT"),  # STALE: F-A18
    (
        "A7  F-021 CLOSED: boundary is 70, not 69.5",
        b(regime_category(69.50) == 1 and regime_category(70.00) == 0),
        "true",
        "STAT",
    ),
    ("A8  math.round(0.5) half-away-from-zero", f(pine_round(0.5)), "1", "NUM"),
    ("A9  math.round(1.5)", f(pine_round(1.5)), "2", "NUM"),
    ("A10 math.round(2.5) (banker's would give 2)", f(pine_round(2.5)), "3", "NUM"),
    ("A11 int(69.99) truncates", i(pine_int(69.99)), "69", "NUM"),
    ("A12 int(-0.5) truncates toward zero", i(pine_int(-0.5)), "0", "NUM"),
    # -- GROUP B: SL/TP race ------------------------------------------------
    ("B1  TP only  -> win", i(resolve_race(2000.0, 2020.0, 2000.0, 10.0)), "1", "DESIGN"),
    ("B2  SL only  -> loss", i(resolve_race(1985.0, 2005.0, 2000.0, 10.0)), "-1", "DESIGN"),
    ("B3  BOTH in one candle -> LOSS", i(resolve_race(1985.0, 2020.0, 2000.0, 10.0)), "-1", "DESIGN"),
    ("B4  neither -> timeout 0", i(resolve_race(1995.0, 2005.0, 2000.0, 10.0)), "0", "DESIGN"),
    ("B5  EXACT touch of SL counts", i(resolve_race(1990.0, 2005.0, 2000.0, 10.0)), "-1", "DESIGN"),
    ("B6  EXACT touch of TP counts", i(resolve_race(1995.0, 2010.0, 2000.0, 10.0)), "1", "DESIGN"),
    ("B7  R=0 -> race never runs (guard)", b(not (0.0 > 0.0)), "true", "NUM"),
    # -- GROUP C: timeout accounting inconsistency --------------------------
    ("C1  timeout enters bin TOTAL", i(cal_bin_count(0)), "1", "STAT"),
    ("C2  timeout is NOT a bin WIN", i(cal_bin_win(0)), "0", "STAT"),
    ("C3  timeout charged ZERO cost", f(cost_charged(0, 0.77)), "0", "STAT"),
    ("C4  win charged full cost", f(cost_charged(1, 0.77)), "0.77", "STAT"),
    (
        "C5  timeout: failure in calib AND free in EV",
        b(cal_bin_win(0) == 0 and _cost(0, 0.77) == 0.0),
        "true",
        "STAT",
    ),
    # -- GROUP D: bayesRate Beta(1,1) shrink --------------------------------
    ("D1  t=0 -> neutral 0.5", f(bayes_rate(0, 0)), "0.5", "NUM"),
    ("D2  0 wins of 30 is NOT 0%", f(bayes_rate(0, 30)), "0.0313", "STAT"),
    ("D3  30 wins of 30 is NOT 100%", f(bayes_rate(30, 30)), "0.9688", "STAT"),
    ("D4  15 of 30 ~ 0.5", f(bayes_rate(15, 30)), "0.5", "STAT"),
    ("D5  no integer-division truncation", b(bayes_rate(0, 30) > 0.0), "true", "NUM"),
    ("D6  shrink weakens as N grows", b(bayes_rate(0, 1000) < bayes_rate(0, 30)), "true", "STAT"),
    # -- GROUP E: bucket minimum sample -------------------------------------
    ("E1  N=29 rejected", b(bucket_qualifies(29)), "false", "PRES"),
    ("E2  N=30 accepted", b(bucket_qualifies(30)), "true", "PRES"),
    ("E3  N=31 accepted", b(bucket_qualifies(31)), "true", "PRES"),
    ("E4  2 qualifying bins -> no fit", b(2 >= 3), "false", "STAT"),
    ("E5  3 qualifying bins -> fit ok", b(3 >= 3), "true", "STAT"),
    # -- GROUP F: Platt/WLS clamps and rejection ----------------------------
    ("F1  slope 0.001 -> clamped up 0.02", f(slope_clamp(0.001)), "0.02", "NUM"),
    ("F2  slope 0.90  -> clamped down 0.25", f(slope_clamp(0.90)), "0.25", "NUM"),
    ("F3  slope 0.10  -> untouched", f(slope_clamp(0.10)), "0.1", "NUM"),
    ("F4  intercept -5 -> clamped -1", f(intercept_clamp(-5.0)), "-1", "NUM"),
    ("F5  intercept  5 -> clamped  1", f(intercept_clamp(5.0)), "1", "NUM"),
    ("F6  NEGATIVE slope rejected", b(fit_accepted(-0.05, 1.0, 5)), "false", "STAT"),
    ("F7  ZERO slope rejected", b(fit_accepted(0.0, 1.0, 5)), "false", "STAT"),
    ("F8  near-zero variance rejected", b(fit_accepted(0.1, 1e-9, 5)), "false", "NUM"),
    ("F9  too few bins rejected", b(fit_accepted(0.1, 1.0, 2)), "false", "STAT"),
    ("F10 valid fit accepted", b(fit_accepted(0.1, 1.0, 3)), "true", "STAT"),
    (
        "F11 slopes 0.5 and 0.9 collapse to one value",
        b(slope_clamp(0.5) == slope_clamp(0.9)),
        "true",
        "NUM",
    ),
    # -- GROUP G: sigmoid output clamp --------------------------------------
    ("G1  score 50 -> 0.5 exactly", f(pine_sigmoid(50.0, 0.1, 0.0)), "0.5", "NUM"),
    ("G2  score 100 clamped to 0.95", f(prob_clamp(pine_sigmoid(100.0, 0.25, 0.0))), "0.95", "STAT"),
    ("G3  score 0   clamped to 0.05", f(prob_clamp(pine_sigmoid(0.0, 0.25, 0.0))), "0.05", "STAT"),
    (
        "G4  MAX and near-max both 0.95",
        b(prob_clamp(pine_sigmoid(100.0, 0.25, 0.0)) == prob_clamp(pine_sigmoid(95.0, 0.25, 0.0))),
        "true",
        "NUM",
    ),
    ("G5  no overflow at extreme input", b(not is_na(pine_sigmoid(1e6, 0.25, 0.0))), "true", "NUM"),
    ("G6  no overflow at extreme -input", b(not is_na(pine_sigmoid(-1e6, 0.25, 0.0))), "true", "NUM"),
    # -- GROUP H: macroRegime clamp saturation ------------------------------
    ("H1  base100 +10 saturates to 100", i(macro_regime(100, 1, True)), "100", "NUM"),
    ("H2  base100 no OI also 100", i(macro_regime(100, 0, True)), "100", "NUM"),
    (
        "H3  SATURATION: V2 == V1 at base100",
        b(macro_regime(100, 1, True) == macro_regime(100, 0, True)),
        "true",
        "NUM",
    ),
    ("H4  base60 +10 -> 70 (no clamp)", i(macro_regime(60, 1, True)), "70", "NUM"),
    ("H5  base30 +5  -> 35", i(macro_regime(30, 1, False)), "35", "NUM"),
    ("H6  oiConviction -1 ADDS not subtracts", i(macro_regime(60, -1, True)), "70", "NUM"),
    (
        "H7  +1 and -1 give identical result",
        b(macro_regime(60, 1, True) == macro_regime(60, -1, True)),
        "true",
        "DESIGN",
    ),
    # -- GROUP I: na propagation and zero denominators ----------------------
    ("I1  na + 1 stays na", f(_NAN + 1.0), "na", "NUM"),
    ("I2  na > 0 is FALSE not na", b(_NAN > 0.0), "false", "NUM"),
    ("I3  na comparison never throws", b(not (_NAN > 0.0)), "true", "NUM"),
    ("I4  math.max(na, 5) propagates na", f(pine_max(_NAN, 5.0)), "na", "NUM"),
    ("I5  nz() substitutes", f(pine_nz(_NAN, 7.0)), "7", "NUM"),
    ("I6  safeDiv by zero -> 0", f(safe_div(10.0, 0.0)), "0", "NUM"),
    ("I7  safeDiv near-zero NOT guarded", b(safe_div(10.0, 1e-12) > 1e9), "true", "NUM"),
    ("I8  0/0 guarded to 0", f(safe_div(0.0, 0.0)), "0", "NUM"),
    # -- GROUP J: score extremes and vote pool ------------------------------
    ("J1  GC off -> pool 6 need 3", i(macro_need(False)), "3", "STAT"),
    ("J2  GC on  -> pool 7 need 4", i(macro_need(True)), "4", "STAT"),
    ("J3  all 6 bull votes clears gate", b(6 >= macro_need(False)), "true", "STAT"),
    ("J4  zero votes fails gate", b(0 >= macro_need(False)), "false", "STAT"),
    (
        "J5  3 votes: passes V1, FAILS V2",
        b(3 >= macro_need(False) and not (3 >= macro_need(True))),
        "true",
        "STAT",
    ),
]


def test_case_count_matches_the_pine_harness() -> None:
    """The harness carries 72 assertions. A port that drops one is not a port.

    This guards the failure mode where a case is deleted to make the suite
    green. If the Pine harness gains or loses an assertion, this number and the
    table above move together, in the same commit.
    """
    assert len(CASES) == 72


def test_case_ids_are_unique() -> None:
    """A duplicated ID would let one case silently shadow another."""
    ids = [case[0].split()[0] for case in CASES]
    assert len(ids) == len(set(ids)), sorted({x for x in ids if ids.count(x) > 1})


# ---------------------------------------------------------------------------
# KNOWN-STALE HARNESS CASES -- finding F-A18
# ---------------------------------------------------------------------------
# A3 and A6 carry PRE-F-021 expected values. The harness's own ``regimeCat``
# thresholds the UNROUNDED composite, matching Master L1894-1896, so:
#
#     regimeCat(39.51) = 2   (39.51 < 40)   but A3 wants 1
#     regimeCat(69.51) = 1   (69.51 < 70)   but A6 wants 0
#
# Those WANT values are only correct under the pre-F-021 behaviour, where the
# composite was ROUNDED before the comparison (round(39.51) = 40 -> 1,
# round(69.51) = 70 -> 0). When F-021 was applied, A2, A5 and A7 were updated
# and A3 and A6 were not.
#
# CONSEQUENCE: the harness reports "2 FAIL / 72" on TradingView. Two permanent
# red rows in a diagnostic table is worse than a wrong value, because it trains
# the reader to skim past red.
#
# These are marked xfail(strict=True) rather than corrected, so that the port
# stays a faithful transcription of the harness. If the Pine harness is fixed,
# strict xfail turns the unexpected pass into a FAILURE here, which is the
# signal to update this block in the same commit.
STALE_CASES: dict[str, str] = {
    "A3": "F-A18: pre-F-021 WANT; regimeCat(39.51) is 2, harness wants 1",
    "A6": "F-A18: pre-F-021 WANT; regimeCat(69.51) is 1, harness wants 0",
}


def _param(case: tuple[str, str, str, str]):
    case_id = case[0].split()[0]
    if case_id in STALE_CASES:
        return pytest.param(*case, marks=pytest.mark.xfail(strict=True, reason=STALE_CASES[case_id]))
    return pytest.param(*case)


@pytest.mark.parametrize(
    ("name", "got", "want", "classification"),
    [_param(c) for c in CASES],
    ids=[case[0].split()[0] for case in CASES],
)
def test_edge_case(name: str, got: str, want: str, classification: str) -> None:
    assert got == want, f"{name} [{classification}]: got {got!r}, want {want!r}"


def test_stale_cases_are_declared_not_silently_dropped() -> None:
    """Guards the shortcut of deleting A3/A6 to get a green board."""
    ids = {case[0].split()[0] for case in CASES}
    assert set(STALE_CASES) <= ids


# ---------------------------------------------------------------------------
# POST-F-021 SEMANTICS, PINNED INDEPENDENTLY OF THE HARNESS
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (39.49, 2),
        (39.50, 2),
        (39.51, 2),  # harness A3 disagrees -- F-A18
        (39.99, 2),
        (40.00, 1),  # the real lower boundary
        (69.49, 1),
        (69.50, 1),
        (69.51, 1),  # harness A6 disagrees -- F-A18
        (69.99, 1),
        (70.00, 0),  # the real upper boundary
    ],
)
def test_regime_boundaries_are_40_and_70_after_f021(raw: float, expected: int) -> None:
    """The boundaries the Master actually implements at L1894-1896.

    Thresholds are half-open on the RAW composite: ``>= 70`` strong,
    ``>= 40 and < 70`` moderate, ``< 40`` weak. The cases at 39.99 and 69.99
    are the ones the harness never added; they are what distinguishes the
    post-F-021 boundary from the pre-F-021 one.
    """
    assert regime_category(raw) == expected


def test_f021_is_not_closed_everywhere_in_the_master() -> None:
    """Finding F-A17, pinned as an executable statement of the defect.

    F-021 moved the REGIME CLASSIFICATION onto the raw composite
    (Master L1894-1896). It did NOT move the liquidity-reach score bump at
    Master L2274 / Strategy L2218, which still thresholds ``regimeComposite``
    -- the ``int(math.round(...))`` value from L1892.

    So a raw composite of 69.50 is MODERATE for classification and STRONG for
    the score bump, in the same bar. The bump feeds ``liqReachScore``, which
    feeds ``fEvBase`` at 20% weight (Master L4441), so the discrepancy reaches
    expected value.

    This test asserts the DEFECT, not the fix. It fails the day someone changes
    L2274 to use the raw composite -- which is the point: that change must be
    a deliberate, A/B-measured edit to all three arms, not a silent one.
    """
    raw = 69.50
    classification_is_strong = regime_category(raw) == 0
    rounded = pine_round(raw)  # what L1892 stores, half away from zero -> 70
    bump_is_strong = rounded >= 70

    assert classification_is_strong is False, "L1894-1896 thresholds the raw composite"
    assert bump_is_strong is True, "L2274 thresholds the rounded composite"
    assert classification_is_strong != bump_is_strong, (
        "F-A17: if these ever agree, F-021 has been completed and the "
        "divergence register entry should be closed in the same commit"
    )
