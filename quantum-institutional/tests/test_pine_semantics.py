"""Pine/Python divergences, asserted from both sides.

Each test states what PYTHON does as well as what PINE does. Asserting only the
Pine side would leave the reader unable to tell whether the wrapper is
necessary, and a future contributor would delete it.
"""

from __future__ import annotations

import math

import pytest

from quantum_institutional.pine.semantics import (
    NA,
    clamp,
    is_na,
    pine_exp,
    pine_int,
    pine_int_div,
    pine_max,
    pine_min,
    pine_nz,
    pine_round,
    pine_sigmoid,
    pine_tostring,
)


class TestRoundingDivergence:
    @pytest.mark.parametrize(
        ("value", "pine", "python"),
        [(0.5, 1.0, 0), (1.5, 2.0, 2), (2.5, 3.0, 2), (3.5, 4.0, 4)],
    )
    def test_half_away_from_zero_vs_bankers(self, value: float, pine: float, python: int) -> None:
        assert pine_round(value) == pine
        assert round(value) == python  # banker's -- differs on every odd .5

    def test_negative_values_round_away_from_zero(self) -> None:
        assert pine_round(-0.5) == -1.0
        assert pine_round(-2.5) == -3.0

    def test_precision_divergence_is_the_bayes_rate_case(self) -> None:
        """The exact value the edge-case harness pins at D2."""
        assert pine_tostring(1 / 32) == "0.0313"
        assert round(1 / 32, 4) == 0.0312

    def test_na_propagates(self) -> None:
        assert is_na(pine_round(NA))


class TestNaPropagation:
    def test_python_max_is_order_dependent_with_nan(self) -> None:
        """The trap: one argument order launders a missing value into a number."""
        assert math.isnan(max(NA, 5.0))
        assert max(5.0, NA) == 5.0  # silently wrong

    @pytest.mark.parametrize("args", [(NA, 5.0), (5.0, NA), (NA, NA)])
    def test_pine_max_and_min_always_propagate(self, args: tuple[float, float]) -> None:
        assert is_na(pine_max(*args))
        assert is_na(pine_min(*args))

    def test_none_is_treated_as_na(self) -> None:
        """A missing DB column and a Pine ``na`` must behave identically."""
        assert is_na(None)
        assert pine_nz(None, 7.0) == 7.0

    def test_clamp_propagates_na_rather_than_saturating_it(self) -> None:
        """A clamp must not turn a missing value into its lower bound."""
        assert is_na(clamp(NA, 0.05, 0.95))


class TestExpOverflow:
    def test_python_math_exp_raises_where_pine_saturates(self) -> None:
        with pytest.raises(OverflowError):
            math.exp(250_012.5)
        assert pine_exp(250_012.5) == math.inf

    def test_sigmoid_survives_both_extremes(self) -> None:
        """Harness G5 and G6. A naive transcription raises on G6."""
        assert pine_sigmoid(1e6, 0.25, 0.0) == 1.0
        assert pine_sigmoid(-1e6, 0.25, 0.0) == 0.0

    def test_sigmoid_is_exactly_one_half_at_the_neutral_score(self) -> None:
        """Harness G1, for every slope: the centring is at score 50."""
        for slope in (0.02, 0.1, 0.25):
            assert pine_sigmoid(50.0, slope, 0.0) == 0.5


class TestIntegerDivision:
    def test_python_slash_cannot_reproduce_pine_int_division(self) -> None:
        assert 7 / 2 == 3.5
        assert pine_int_div(7, 2) == 3

    def test_truncation_is_toward_zero_not_floor(self) -> None:
        """Distinguishes Pine from Python's ``//``, which floors."""
        assert pine_int_div(-7, 2) == -3
        assert -7 // 2 == -4

    def test_zero_denominator_is_na_not_an_exception(self) -> None:
        assert is_na(pine_int_div(1, 0))


class TestTruncation:
    @pytest.mark.parametrize(("value", "expected"), [(69.99, 69), (-0.5, 0), (-69.99, -69), (0.0, 0)])
    def test_int_truncates_toward_zero(self, value: float, expected: int) -> None:
        assert pine_int(value) == expected


class TestFormatting:
    @pytest.mark.parametrize(("value", "expected"), [(0.5, "0.5"), (1.0, "1"), (-1.0, "-1"), (0.77, "0.77")])
    def test_trailing_zeros_are_stripped(self, value: float, expected: str) -> None:
        assert pine_tostring(value) == expected

    def test_na_renders_as_na_not_as_zero(self) -> None:
        assert pine_tostring(NA) == "na"
