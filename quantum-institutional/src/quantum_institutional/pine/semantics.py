"""Pine Script v6 language semantics, reproduced exactly in Python.

WHY THIS MODULE EXISTS
----------------------
Quantum 5.0 is the reference system. Parity means the Python engine reproduces
what *Pine* computed -- including the places where Pine and Python disagree at
the language level. Those disagreements are silent: both languages return a
number, the numbers differ, and nothing raises.

Every function here is justified by an assertion in the Quantum 5.0 edge-case
harness (``reference/quantum_5_0/XAUUSD_Quantum_5_0_EdgeCases.pine``). The case
IDs in the docstrings are that harness's own IDs. See
``docs/PARITY_PLAN.md`` for what those assertions do and do not establish.

THE FOUR TRAPS THIS MODULE CLOSES
---------------------------------
1. ``round``     Pine rounds half AWAY FROM ZERO. Python's builtin ``round``
                 uses banker's rounding. ``round(2.5)`` is 2 in Python and 3 in
                 Pine (harness A10). ``round(0.03125, 4)`` is 0.0312 in Python
                 and 0.0313 in Pine (harness D2).
2. ``math.max``  Pine propagates ``na``. Python's ``max`` is order-dependent
                 with NaN: ``max(nan, 5) -> nan`` but ``max(5, nan) -> 5``
                 (harness I4). One argument order silently launders a missing
                 value into a real number.
3. ``math.exp``  Pine saturates to infinity and keeps going. Python's
                 ``math.exp`` raises ``OverflowError`` at roughly x > 709, so a
                 sigmoid that Pine evaluates to 0.0 is a crash in Python
                 (harness G6).
4. ``/``         Pine ``int / int`` is integer division. Python ``/`` is always
                 true division, so Python cannot accidentally reproduce a Pine
                 integer-division truncation -- it must be requested explicitly
                 via :func:`pine_int_div` (harness D5).

NOT A REWRITE. Nothing here "improves" Pine. Where Pine's behaviour is a known
defect, this module reproduces the defect and the divergence register records
it. See ``docs/DIVERGENCE_REGISTER.md``.
"""

from __future__ import annotations

import math
from typing import Final

__all__ = [
    "NA",
    "clamp",
    "is_na",
    "pine_abs",
    "pine_exp",
    "pine_int",
    "pine_int_div",
    "pine_max",
    "pine_min",
    "pine_nz",
    "pine_round",
    "pine_sigmoid",
    "pine_tostring",
]

#: Pine's ``na`` for float-typed values. Pine has a typed ``na`` per type; only
#: the float case appears in the Quantum 5.0 arithmetic this module covers.
NA: Final[float] = float("nan")

#: Largest exponent ``math.exp`` accepts before raising ``OverflowError``.
#: Pine has no such limit -- it saturates to +inf. See :func:`pine_exp`.
_EXP_MAX: Final[float] = 709.782712893384


def is_na(value: float | None) -> bool:
    """Pine ``na(x)``.

    ``None`` is treated as ``na`` so that a missing database column and a Pine
    ``na`` behave identically rather than raising on arithmetic.
    """
    if value is None:
        return True
    return math.isnan(value)


def pine_round(value: float, precision: int = 0) -> float:
    """Pine ``math.round``: half away from zero (harness A8, A9, A10).

    Python's builtin ``round`` is banker's rounding and disagrees on every
    exact ``.5``:

        >>> round(2.5), pine_round(2.5)
        (2, 3.0)
        >>> round(0.03125, 4), pine_round(0.03125, 4)
        (0.0312, 0.0313)

    ``precision`` mirrors Pine's second argument and is applied by scaling,
    which is what Pine does; it is therefore subject to the same binary
    floating-point representation error as Pine.
    """
    if is_na(value):
        return NA
    if math.isinf(value):
        return value
    scale = 10.0**precision
    scaled = value * scale
    # ``math.floor(|x| + 0.5)`` is half-away-from-zero once the sign is
    # reapplied. ``math.copysign`` keeps -0.0 distinct, as Pine does.
    rounded = math.floor(abs(scaled) + 0.5)
    return math.copysign(rounded, value) / scale


def pine_int(value: float) -> int | float:
    """Pine ``int()``: truncation TOWARD ZERO (harness A11, A12).

    ``int(69.99) -> 69`` and ``int(-0.5) -> 0``. Python's builtin ``int()``
    truncates toward zero as well, so this wrapper exists for two reasons: it
    makes the truncation intentional at every call site rather than incidental,
    and it propagates ``na`` instead of raising ``ValueError``.

    Returns ``NA`` (a float) when the input is ``na``, matching Pine, where an
    ``na`` int is still ``na``.
    """
    if is_na(value):
        return NA
    return int(value)


def pine_nz(value: float | None, replacement: float = 0.0) -> float:
    """Pine ``nz(x, y)``: substitute ``replacement`` when ``x`` is ``na`` (I5)."""
    return replacement if is_na(value) else float(value)  # type: ignore[arg-type]


def pine_max(a: float, b: float) -> float:
    """Pine ``math.max``: ``na`` PROPAGATES (harness I4).

    This is the trap that matters most, because Python's ``max`` gives the
    right answer for one argument order and the wrong answer for the other:

        >>> max(float("nan"), 5.0)
        nan
        >>> max(5.0, float("nan"))
        5.0

    The second form turns a missing value into a real number with no error, no
    warning and no NaN downstream to notice later.
    """
    if is_na(a) or is_na(b):
        return NA
    return a if a > b else b


def pine_min(a: float, b: float) -> float:
    """Pine ``math.min``: ``na`` propagates. Counterpart to :func:`pine_max`."""
    if is_na(a) or is_na(b):
        return NA
    return a if a < b else b


def pine_abs(value: float) -> float:
    """Pine ``math.abs`` with ``na`` propagation."""
    return NA if is_na(value) else abs(value)


def pine_int_div(numerator: int, denominator: int) -> int | float:
    """Pine ``int / int`` -- INTEGER division, truncating toward zero.

    Python's ``/`` is always true division, so a Pine integer-division
    truncation can never be reproduced by transcription alone; it has to be
    asked for. Call this only where the Pine expression genuinely has two int
    operands and no float in the surrounding ternary.

    The harness's ``bayesRate`` (group D) is the worked example of when NOT to
    use it: ``_t > 0 ? (_w + 1) / (_t + 2) : 0.5`` has a float branch, which
    makes the whole Pine ternary float, so the division is true division and
    ``bayesRate(0, 30)`` is 0.0313 rather than 0 (harness D5).

    Returns ``NA`` on a zero denominator rather than raising, matching Pine,
    where division by zero yields ``na`` for ints.
    """
    if denominator == 0:
        return NA
    quotient = abs(numerator) // abs(denominator)
    return -quotient if (numerator < 0) != (denominator < 0) else quotient


def pine_exp(value: float) -> float:
    """Pine ``math.exp``: saturates to ``inf`` instead of raising (harness G6).

    Python raises ``OverflowError`` above roughly 709.78. Pine returns ``inf``,
    which then flows into ``1 / (1 + inf) -> 0`` without incident. A direct
    transcription of the Quantum 5.0 sigmoid therefore crashes in Python on
    inputs Pine handles silently.
    """
    if is_na(value):
        return NA
    if value > _EXP_MAX:
        return math.inf
    if value < -_EXP_MAX:
        return 0.0
    return math.exp(value)


def pine_sigmoid(score: float, slope: float, intercept: float) -> float:
    """The Quantum 5.0 calibration sigmoid, overflow-safe.

    Pine source (``Master.pine``, sigmoid at the Platt application site)::

        1.0 / (1.0 + math.exp(-((_score - 50.0) * _k + _b)))

    Evaluated in the numerically stable branch form so that extreme scores
    return the same 0.0 / 1.0 Pine returns rather than raising or losing
    precision (harness G1, G5, G6).

    The ``- 50.0`` centring is Quantum 5.0's, not a convention of this module:
    a raw score of 50 is the neutral point, so ``pine_sigmoid(50, k, 0)`` is
    exactly 0.5 for every ``k`` (harness G1).
    """
    if is_na(score) or is_na(slope) or is_na(intercept):
        return NA
    z = (score - 50.0) * slope + intercept
    if z >= 0.0:
        return 1.0 / (1.0 + pine_exp(-z))
    exp_z = pine_exp(z)
    return exp_z / (1.0 + exp_z)


def clamp(value: float, lower: float, upper: float) -> float:
    """Pine ``math.min(math.max(v, lo), hi)`` with ``na`` propagation.

    Saturation destroys information on purpose: two distinct inputs above
    ``upper`` become one output (harness F11, G4, H3). That is the engine's
    intent, but it must be visible at the call site, which is why the clamp is
    named rather than inlined.
    """
    return pine_min(pine_max(value, lower), upper)


def pine_tostring(value: float, precision: int = 4) -> str:
    """Pine ``str.tostring(v, "#.####")`` -- the harness's display format.

    Reproduced because the edge-case harness compares FORMATTED strings, so a
    Python port that compares floats is testing something slightly different.
    Trailing zeros are stripped, as the ``#`` placeholder does, and rounding is
    half away from zero rather than banker's.
    """
    if is_na(value):
        return "na"
    rounded = pine_round(value, precision)
    text = f"{rounded:.{precision}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text if text not in ("", "-") else "0"
