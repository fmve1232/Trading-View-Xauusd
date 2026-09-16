"""Quantum 5.0 Master expressions, transcribed for parity testing.

PROVENANCE
----------
Every function here is a transcription of an expression in
``reference/quantum_5_0/XAUUSD_Quantum_5_0_Master.pine``, taken via the
edge-case harness ``XAUUSD_Quantum_5_0_EdgeCases.pine``, which carries the same
expressions with its own line citations into the Master.

WHAT A PASSING TEST PROVES, AND WHAT IT DOES NOT
------------------------------------------------
The harness states its own limits, and they carry over verbatim to this port:

    PROVES:       how the expression evaluates, in Pine's semantics.
    DOES NOT PROVE: that the Master is WIRED to these expressions. Every case is
                  transcribed from the Master; transcription is verified by eye,
                  not by the compiler.

This port adds one more limit of its own, which is the important one:

    The expected values in ``tests/test_edge_case_parity.py`` are the harness's
    own WANT column. They were written by the same process that wrote the
    expressions. A green suite therefore proves PYTHON AGREES WITH THE HARNESS
    -- it does not independently prove either is right about the Master, and it
    is not a substitute for running the harness on TradingView and reading the
    table. Phase 6 parity is established against BAR DATA, not against this file.

DEFECTS ARE REPRODUCED, NOT FIXED
---------------------------------
Master prompt section 13: do not improve the formulas initially. Three of the
expressions below encode behaviour the audit classified as defective or
lossy. They are reproduced exactly and cross-referenced to
``docs/DIVERGENCE_REGISTER.md``. Do not "fix" them here -- a fix here breaks
parity and hides the defect instead of measuring it.
"""

from __future__ import annotations

from quantum_institutional.pine.semantics import (
    NA,
    clamp,
    is_na,
    pine_int,
    pine_max,
    pine_min,
)

__all__ = [
    "bayes_rate",
    "bucket_qualifies",
    "cal_bin_count",
    "cal_bin_win",
    "cost_charged",
    "fit_accepted",
    "intercept_clamp",
    "macro_need",
    "macro_regime",
    "prob_clamp",
    "regime_category",
    "resolve_race",
    "safe_div",
    "slope_clamp",
]

# --------------------------------------------------------------------------
# GROUP A -- regime boundaries (harness A1-A7; finding F-021, CLOSED)
# --------------------------------------------------------------------------

STRONG, MODERATE, WEAK = 0, 1, 2


def regime_category(raw_composite: float) -> int | float:
    """Master regime bucket, thresholded on the UNROUNDED composite.

    Before F-021 the engine rounded the composite and then compared, which made
    the documented 40 / 70 boundaries behave as 39.5 / 69.5. F-021 moved the
    threshold onto ``regimeCompositeRaw``, so the boundaries are now literally
    40 and 70 (harness A7 asserts the 69.5 artefact is gone).

    Takes the RAW composite. Passing an already-rounded value reintroduces the
    defect silently, which is why the parameter is named ``raw_composite``.
    """
    if is_na(raw_composite):
        return NA
    if raw_composite >= 70:
        return STRONG
    if raw_composite >= 40:
        return MODERATE
    return WEAK


# --------------------------------------------------------------------------
# GROUP B -- SL/TP race (harness B1-B7)
# --------------------------------------------------------------------------


def resolve_race(low: float, high: float, entry: float, r_distance: float) -> int:
    """Outcome of one bar against a symmetric SL/TP bracket.

    Returns -1 loss, +1 win, 0 unresolved.

    SL IS TESTED FIRST, so a bar that touches both resolves to LOSS. The
    harness classifies this DESIGN, not BUG: Pine cannot order intrabar events
    without lower-timeframe data, and the conservative branch is the defensible
    one. Any Python replacement that resolves the race with tick data will
    produce DIFFERENT outcome labels and therefore a different calibration set
    -- that is a deliberate divergence to be measured in Phase 6, not a bug fix
    to apply quietly. See DIVERGENCE_REGISTER D-02.

    Exact touches count as hits on both sides (harness B5, B6). ``r_distance``
    of 0 is guarded by the caller (``if _oR > 0``), which disables the race
    entirely on a flat or zero-ATR bar (harness B7).
    """
    if low <= entry - r_distance:
        return -1
    if high >= entry + r_distance:
        return 1
    return 0


# --------------------------------------------------------------------------
# GROUP C -- timeout accounting (harness C1-C5; finding F-A10 context)
# --------------------------------------------------------------------------


def cal_bin_count(outcome_code: int) -> int:
    """Calibration bin TOTAL. A timeout increments it. Always 1."""
    return 1


def cal_bin_win(outcome_code: int) -> int:
    """Calibration bin WIN. Only ``+1`` counts, so a timeout scores as failure."""
    return 1 if outcome_code == 1 else 0


def cost_charged(outcome_code: int, cost: float) -> float:
    """Cost EFFECTIVELY borne by an observation, by outcome code.

    This models the OUTCOME, not the arithmetic. Since F-A10 the Master
    subtracts cost for every analog including timeouts, but on the timeout
    branch the result is discarded (``_pnlPct`` is 0.0 and ``absFrAdj`` is read
    only in the +/-1 branches), so a timeout is still effectively free.

    The asymmetry the harness pins with C5: the SAME observation is counted as
    a FAILURE in calibration and as FREE in expectancy. Pessimistic in one
    statistic, optimistic in the other. DIVERGENCE_REGISTER D-03.
    """
    return cost if outcome_code in (1, -1) else 0.0


# --------------------------------------------------------------------------
# GROUP D -- Beta(1,1) shrink (harness D1-D6)
# --------------------------------------------------------------------------


def bayes_rate(wins: int, total: int) -> float:
    """Master ``bayesRate(w, t) = t > 0 ? (w + 1) / (t + 2) : 0.5``.

    Laplace / Beta(1,1) shrink: no bucket can ever claim 0% or 100%, which is
    what keeps a 30-sample bucket from reporting certainty (harness D2, D3).

    TRUE division, deliberately. In Pine the ``: 0.5`` branch makes the whole
    ternary float, so ``(w + 1) / (t + 2)`` is NOT integer division despite both
    operands being ints (harness D5). Python's ``/`` reproduces this by default;
    ``pine_int_div`` is what would be needed if the float branch were ever
    removed from the Pine source.
    """
    if total > 0:
        return (wins + 1) / (total + 2)
    return 0.5


# --------------------------------------------------------------------------
# GROUP E -- minimum sample gates (harness E1-E5)
# --------------------------------------------------------------------------

MIN_BUCKET_N = 30
MIN_PLATT_BINS = 3


def bucket_qualifies(n: int) -> bool:
    """``N >= 30`` gate on a calibration bucket."""
    return n >= MIN_BUCKET_N


# --------------------------------------------------------------------------
# GROUP F -- Platt / WLS clamps and rejection (harness F1-F11)
# --------------------------------------------------------------------------

SLOPE_MIN, SLOPE_MAX = 0.02, 0.25
INTERCEPT_MIN, INTERCEPT_MAX = -1.0, 1.0
VARIANCE_FLOOR = 1e-6


def slope_clamp(slope: float) -> float:
    """Clamp the fitted Platt slope to [0.02, 0.25].

    Saturating: two genuinely different fits collapse to one value above the
    ceiling, and the information that distinguished them is gone (harness F11
    asserts 0.5 and 0.9 become identical). Intentional, but it means a clamped
    slope carries no evidence about how far outside the range the fit was.
    """
    return clamp(slope, SLOPE_MIN, SLOPE_MAX)


def intercept_clamp(intercept: float) -> float:
    """Clamp the fitted Platt intercept to [-1, 1]. Saturating, as above."""
    return clamp(intercept, INTERCEPT_MIN, INTERCEPT_MAX)


def fit_accepted(slope: float, variance: float, qualifying_bins: int) -> bool:
    """Whether a Platt fit is accepted at all.

    Three independent rejections: too few qualifying bins, a degenerate design
    (``variance <= 1e-6``, i.e. the scores barely vary so the slope is not
    identified), and a non-positive slope -- which would mean the model learned
    that a HIGHER score implies a LOWER win rate, and is rejected rather than
    used (harness F6, F7).

    Note the slope test is on the RAW fit, before ``slope_clamp``. Clamping
    first would lift a negative slope to +0.02 and turn a rejection into an
    acceptance.
    """
    return qualifying_bins >= MIN_PLATT_BINS and variance > VARIANCE_FLOOR and slope > 0


# --------------------------------------------------------------------------
# GROUP G -- probability output clamp (harness G1-G6)
# --------------------------------------------------------------------------

PROB_MIN, PROB_MAX = 0.05, 0.95


def prob_clamp(p: float) -> float:
    """Clamp a calibrated probability to [0.05, 0.95].

    A calibrated probability can never be REPORTED below 5% or above 95%. The
    clamp bounds the downstream risk sizing, but it also means reported
    probabilities are not the model's probabilities at the extremes, which
    matters when scoring calibration: a Brier score computed on clamped values
    is not the model's Brier score. DIVERGENCE_REGISTER D-04.
    """
    return clamp(p, PROB_MIN, PROB_MAX)


# --------------------------------------------------------------------------
# GROUP H -- macro regime clamp saturation (harness H1-H7)
# --------------------------------------------------------------------------


def macro_regime(base: int, oi_conviction: int, macro_directional: bool) -> int | float:
    """Master macro regime with the open-interest nudge, clamped to [0, 100].

    The nudge is MAGNITUDE-based: ``oi_conviction`` of -1 adds exactly what +1
    adds, because the test is ``!= 0`` (harness H6, H7). Whether that is
    intended is a design question the audit left open; it is reproduced as-is.

    At base 100 the nudge is entirely absorbed by the clamp, so a variant that
    "subtracts the nudge" to recover a pre-nudge value would fabricate a
    divergence that does not exist (harness H3).
    """
    if oi_conviction != 0 and macro_directional:
        nudge = 10
    elif oi_conviction != 0:
        nudge = 5
    else:
        nudge = 0
    return pine_int(pine_max(0.0, pine_min(100.0, float(base + nudge))))


# --------------------------------------------------------------------------
# GROUP I -- division guard (harness I1-I8)
# --------------------------------------------------------------------------


def safe_div(numerator: float, denominator: float) -> float:
    """Master division guard: ``_b == 0 ? 0.0 : _a / _b``.

    REPRODUCES A KNOWN DEFECT. The guard tests exact equality with zero, so a
    denominator of 1e-12 passes the guard and the result explodes to 1e13
    (harness I7). A magnitude guard (``abs(b) < eps``) would be the fix; it is
    NOT applied here because applying it breaks parity with the live engine.
    DIVERGENCE_REGISTER D-01 tracks it, and Phase 6 measures how often a
    near-zero denominator actually occurs on XAUUSD bars before anything is
    changed in the Pine source.
    """
    if denominator == 0:
        return 0.0
    return numerator / denominator


# --------------------------------------------------------------------------
# GROUP J -- macro vote pool (harness J1-J5)
# --------------------------------------------------------------------------


def macro_need(gold_futures_valid: bool) -> int | float:
    """Votes required from the macro pool: ``ceil(pool / 2)``.

    The pool is 6, or 7 when gold futures are a valid contributor. Because the
    requirement is a ceiling over a pool that grows by one, enabling gold
    futures TIGHTENS the gate: 3 votes clear a 6-pool but fail a 7-pool
    (harness J5). A feed coming online therefore reduces the number of signals,
    which looks like a regression and is not.
    """
    pool = 6 + (1 if gold_futures_valid else 0)
    import math as _math

    return pine_int(_math.ceil(pool / 2.0))
