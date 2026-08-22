"""Tests for function edge cases to improve coverage."""

from decimal import Decimal

from dhis2w_fhir_engine.engine.context import EvaluationContext

# Boolean functions
from dhis2w_fhir_engine.engine.fhirpath.functions.boolean import (
    fn_converts_to_boolean,
    fn_converts_to_date,
    fn_converts_to_datetime,
    fn_converts_to_decimal,
    fn_converts_to_integer,
    fn_converts_to_quantity,
    fn_converts_to_string,
    fn_converts_to_time,
    fn_iif,
    fn_not,
    fn_to_boolean,
    fn_to_date,
    fn_to_datetime,
    fn_to_decimal,
    fn_to_integer,
    fn_to_quantity,
    fn_to_string,
    fn_to_time,
    fn_trace,
)

# Math functions
from dhis2w_fhir_engine.engine.fhirpath.functions.math import (
    fn_abs,
    fn_ceiling,
    fn_exp,
    fn_floor,
    fn_ln,
    fn_log,
    fn_power,
    fn_round,
    fn_sqrt,
    fn_truncate,
)

# String functions
from dhis2w_fhir_engine.engine.fhirpath.functions.strings import (
    fn_contains,
    fn_ends_with,
    fn_index_of,
    fn_join,
    fn_length,
    fn_lower,
    fn_matches,
    fn_replace,
    fn_split,
    fn_starts_with,
    fn_substring,
    fn_to_chars,
    fn_trim,
    fn_upper,
)
from dhis2w_fhir_engine.engine.types import Quantity


class TestStringFunctionsEdgeCases:
    """Edge cases for string functions."""

    def test_starts_with_non_string(self) -> None:
        """Test startsWith with non-string input."""
        ctx = EvaluationContext()
        assert fn_starts_with(ctx, [123], "pre") == []

    def test_ends_with_non_string(self) -> None:
        """Test endsWith with non-string input."""
        ctx = EvaluationContext()
        assert fn_ends_with(ctx, [123], "suf") == []

    def test_contains_non_string(self) -> None:
        """Test contains with non-string input."""
        ctx = EvaluationContext()
        assert fn_contains(ctx, [123], "sub") == []

    def test_matches_non_string(self) -> None:
        """Test matches with non-string input."""
        ctx = EvaluationContext()
        assert fn_matches(ctx, [123], ".*") == []

    def test_matches_invalid_regex(self) -> None:
        """Test matches with invalid regex returns False."""
        ctx = EvaluationContext()
        result = fn_matches(ctx, ["hello"], "[invalid")
        assert result == [False]

    def test_replace_non_string(self) -> None:
        """Test replace with non-string input."""
        ctx = EvaluationContext()
        assert fn_replace(ctx, [123], "a", "b") == []

    def test_replace_invalid_regex(self) -> None:
        """Test replace with invalid regex returns original."""
        ctx = EvaluationContext()
        result = fn_replace(ctx, ["hello"], "[invalid", "x")
        assert result == ["hello"]

    def test_length_non_string(self) -> None:
        """Test length with non-string input."""
        ctx = EvaluationContext()
        assert fn_length(ctx, [123]) == []

    def test_substring_non_string(self) -> None:
        """Test substring with non-string input."""
        ctx = EvaluationContext()
        assert fn_substring(ctx, [123], 0) == []

    def test_upper_non_string(self) -> None:
        """Test upper with non-string input."""
        ctx = EvaluationContext()
        assert fn_upper(ctx, [123]) == []

    def test_lower_non_string(self) -> None:
        """Test lower with non-string input."""
        ctx = EvaluationContext()
        assert fn_lower(ctx, [123]) == []

    def test_trim_non_string(self) -> None:
        """Test trim with non-string input."""
        ctx = EvaluationContext()
        assert fn_trim(ctx, [123]) == []

    def test_split_non_string(self) -> None:
        """Test split with non-string input."""
        ctx = EvaluationContext()
        assert fn_split(ctx, [123], ",") == []

    def test_index_of_non_string(self) -> None:
        """Test indexOf with non-string input."""
        ctx = EvaluationContext()
        assert fn_index_of(ctx, [123], "x") == []

    def test_to_chars_non_string(self) -> None:
        """Test toChars with non-string input."""
        ctx = EvaluationContext()
        assert fn_to_chars(ctx, [123]) == []

    def test_join_with_none_items(self) -> None:
        """Test join filters None items."""
        ctx = EvaluationContext()
        result = fn_join(ctx, ["a", None, "b"], "-")
        assert result == ["a-b"]


class TestMathFunctionsEdgeCases:
    """Edge cases for math functions."""

    def test_abs_non_numeric(self) -> None:
        """Test abs with non-numeric input."""
        ctx = EvaluationContext()
        assert fn_abs(ctx, ["string"]) == []

    def test_ceiling_non_numeric(self) -> None:
        """Test ceiling with non-numeric input."""
        ctx = EvaluationContext()
        assert fn_ceiling(ctx, ["string"]) == []

    def test_floor_non_numeric(self) -> None:
        """Test floor with non-numeric input."""
        ctx = EvaluationContext()
        assert fn_floor(ctx, ["string"]) == []

    def test_round_non_numeric(self) -> None:
        """Test round with non-numeric input."""
        ctx = EvaluationContext()
        assert fn_round(ctx, ["string"]) == []

    def test_truncate_non_numeric(self) -> None:
        """Test truncate with non-numeric input."""
        ctx = EvaluationContext()
        assert fn_truncate(ctx, ["string"]) == []

    def test_sqrt_non_numeric(self) -> None:
        """Test sqrt with non-numeric input."""
        ctx = EvaluationContext()
        assert fn_sqrt(ctx, ["string"]) == []

    def test_sqrt_negative(self) -> None:
        """Test sqrt with negative input returns empty."""
        ctx = EvaluationContext()
        assert fn_sqrt(ctx, [-1]) == []

    def test_ln_non_numeric(self) -> None:
        """Test ln with non-numeric input."""
        ctx = EvaluationContext()
        assert fn_ln(ctx, ["string"]) == []

    def test_ln_non_positive(self) -> None:
        """Test ln with non-positive input returns empty."""
        ctx = EvaluationContext()
        assert fn_ln(ctx, [0]) == []
        assert fn_ln(ctx, [-1]) == []

    def test_log_non_numeric(self) -> None:
        """Test log with non-numeric input."""
        ctx = EvaluationContext()
        assert fn_log(ctx, ["string"], 10) == []

    def test_log_non_positive(self) -> None:
        """Test log with non-positive input returns empty."""
        ctx = EvaluationContext()
        assert fn_log(ctx, [0], 10) == []

    def test_power_non_numeric(self) -> None:
        """Test power with non-numeric input."""
        ctx = EvaluationContext()
        assert fn_power(ctx, ["string"], 2) == []

    def test_exp_non_numeric(self) -> None:
        """Test exp with non-numeric input."""
        ctx = EvaluationContext()
        assert fn_exp(ctx, ["string"]) == []

    def test_math_with_decimal(self) -> None:
        """Test math functions work with Decimal."""
        ctx = EvaluationContext()
        d = Decimal("10.5")
        assert fn_abs(ctx, [d]) == [Decimal("10.5")]
        assert fn_ceiling(ctx, [d]) == [11]
        assert fn_floor(ctx, [d]) == [10]


class TestBooleanFunctionsEdgeCases:
    """Edge cases for boolean functions."""

    def test_not_non_boolean(self) -> None:
        """A single non-boolean item evaluates as true under the singleton rule, so not() reports false."""
        ctx = EvaluationContext()
        assert fn_not(ctx, ["string"]) == [False]

    def test_not_empty(self) -> None:
        """An empty collection evaluates as empty, so not() reports empty."""
        ctx = EvaluationContext()
        assert fn_not(ctx, []) == []

    def test_iif_with_list_results(self) -> None:
        """Test iif with list results."""
        ctx = EvaluationContext()
        result = fn_iif(ctx, [True], [1, 2], [3, 4])
        assert result == [1, 2]

        result = fn_iif(ctx, [False], [1, 2], [3, 4])
        assert result == [3, 4]

    def test_iif_empty_condition_with_otherwise(self) -> None:
        """Test iif with empty condition uses otherwise."""
        ctx = EvaluationContext()
        result = fn_iif(ctx, [], "true_val", "otherwise")
        assert result == ["otherwise"]

    def test_iif_empty_condition_no_otherwise(self) -> None:
        """Test iif with empty condition and no otherwise returns empty."""
        ctx = EvaluationContext()
        result = fn_iif(ctx, [], "true_val", None)
        assert result == []

    def test_trace_returns_unchanged(self) -> None:
        """Test trace returns collection unchanged."""
        ctx = EvaluationContext()
        result = fn_trace(ctx, [1, 2, 3], "debug")
        assert result == [1, 2, 3]

    def test_to_boolean_float(self) -> None:
        """Test toBoolean with float."""
        ctx = EvaluationContext()
        assert fn_to_boolean(ctx, [1.0]) == [True]
        assert fn_to_boolean(ctx, [0.0]) == [False]
        assert fn_to_boolean(ctx, [2.5]) == []

    def test_to_integer_float_not_whole(self) -> None:
        """Test toInteger with non-whole float."""
        ctx = EvaluationContext()
        assert fn_to_integer(ctx, [3.5]) == []

    def test_to_integer_string_with_decimal(self) -> None:
        """Test toInteger with string containing decimal.

        Per FHIRPath spec, strings with decimal points don't convert to integers.
        """
        ctx = EvaluationContext()
        assert fn_to_integer(ctx, ["5.0"]) == []  # Has decimal point, so no conversion
        assert fn_to_integer(ctx, ["5.5"]) == []

    def test_to_integer_invalid_string(self) -> None:
        """Test toInteger with invalid string."""
        ctx = EvaluationContext()
        assert fn_to_integer(ctx, ["abc"]) == []

    def test_to_decimal_invalid_string(self) -> None:
        """Test toDecimal with invalid string."""
        ctx = EvaluationContext()
        assert fn_to_decimal(ctx, ["abc"]) == []

    def test_to_decimal_non_convertible(self) -> None:
        """Test toDecimal with non-convertible type."""
        ctx = EvaluationContext()
        assert fn_to_decimal(ctx, [{"obj": "val"}]) == []

    def test_to_string_non_convertible(self) -> None:
        """Test toString with non-convertible type."""
        ctx = EvaluationContext()
        assert fn_to_string(ctx, [{"obj": "val"}]) == []

    def test_to_date_datetime_extraction(self) -> None:
        """Test toDate extracts date from datetime."""
        ctx = EvaluationContext()
        result = fn_to_date(ctx, ["2024-03-15T10:30:00Z"])
        assert result == ["2024-03-15"]

    def test_to_date_invalid(self) -> None:
        """Test toDate with invalid input."""
        ctx = EvaluationContext()
        assert fn_to_date(ctx, ["not-a-date"]) == []
        assert fn_to_date(ctx, [123]) == []

    def test_to_datetime_invalid(self) -> None:
        """Test toDateTime with invalid input."""
        ctx = EvaluationContext()
        assert fn_to_datetime(ctx, ["not-a-date"]) == []
        assert fn_to_datetime(ctx, [123]) == []

    def test_to_time_t_prefix(self) -> None:
        """Test toTime with T prefix."""
        ctx = EvaluationContext()
        result = fn_to_time(ctx, ["T10:30:45"])
        assert result == ["10:30:45"]

    def test_to_time_invalid(self) -> None:
        """Test toTime with invalid input."""
        ctx = EvaluationContext()
        assert fn_to_time(ctx, ["not-a-time"]) == []
        assert fn_to_time(ctx, [123]) == []

    def test_to_quantity_existing_quantity(self) -> None:
        """Test toQuantity with existing Quantity."""
        ctx = EvaluationContext()
        q = Quantity(value=Decimal("10"), unit="mg")
        result = fn_to_quantity(ctx, [q])
        assert result == [q]

    def test_to_quantity_int(self) -> None:
        """Test toQuantity with integer."""
        ctx = EvaluationContext()
        result = fn_to_quantity(ctx, [10])
        assert len(result) == 1
        assert result[0].value == Decimal(10)

    def test_to_quantity_string(self) -> None:
        """Test toQuantity with string. Per FHIRPath spec, UCUM units need quotes."""
        ctx = EvaluationContext()
        result = fn_to_quantity(ctx, ["10 'mg'"])
        assert len(result) == 1
        assert result[0].value == Decimal("10")
        assert result[0].unit == "mg"

    def test_to_quantity_invalid_string(self) -> None:
        """Test toQuantity with invalid string."""
        ctx = EvaluationContext()
        assert fn_to_quantity(ctx, ["not a quantity"]) == []

    def test_to_quantity_non_convertible(self) -> None:
        """Test toQuantity with non-convertible type."""
        ctx = EvaluationContext()
        assert fn_to_quantity(ctx, [{"obj": "val"}]) == []

    def test_converts_to_functions(self) -> None:
        """Test convertsTo functions return boolean."""
        ctx = EvaluationContext()
        assert fn_converts_to_boolean(ctx, ["true"]) == [True]
        assert fn_converts_to_boolean(ctx, ["invalid"]) == [False]

        assert fn_converts_to_integer(ctx, ["5"]) == [True]
        assert fn_converts_to_integer(ctx, ["abc"]) == [False]

        assert fn_converts_to_decimal(ctx, ["5.5"]) == [True]
        assert fn_converts_to_decimal(ctx, ["abc"]) == [False]

        assert fn_converts_to_string(ctx, [5]) == [True]

        assert fn_converts_to_date(ctx, ["2024-03-15"]) == [True]
        assert fn_converts_to_date(ctx, ["invalid"]) == [False]

        assert fn_converts_to_datetime(ctx, ["2024-03-15T10:30:00"]) == [True]
        assert fn_converts_to_datetime(ctx, ["invalid"]) == [False]

        assert fn_converts_to_time(ctx, ["10:30:00"]) == [True]
        assert fn_converts_to_time(ctx, ["invalid"]) == [False]

        assert fn_converts_to_quantity(ctx, ["10 'mg'"]) == [True]
        assert fn_converts_to_quantity(ctx, ["invalid"]) == [False]
