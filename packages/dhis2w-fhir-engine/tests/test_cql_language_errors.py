"""Tests for the CQL constructs that raise, and for the ones that quietly answer null.

Each case names the raise site it reaches: literal range and precision checks, interval boundary
validation, `singleton from` / `point from` arity, successor and predecessor overflow, `convert`
failures, external functions with no implementation, and recursive definitions.
"""

import pytest

from dhis2w_fhir_engine.engine.cql import CQLEvaluator
from dhis2w_fhir_engine.engine.exceptions import CQLError


@pytest.fixture
def evaluator() -> CQLEvaluator:
    """Create a CQL evaluator."""
    return CQLEvaluator()


class TestNumericLiteralRange:
    """Integer and decimal literals are range- and precision-checked while being visited."""

    def test_integer_above_the_maximum(self, evaluator: CQLEvaluator) -> None:
        with pytest.raises(CQLError, match="Integer value 2147483648 out of range"):
            evaluator.evaluate_expression("2147483648")

    def test_integer_below_the_minimum(self, evaluator: CQLEvaluator) -> None:
        with pytest.raises(CQLError, match="Integer value 2147483649 out of range"):
            evaluator.evaluate_expression("-2147483649")

    def test_the_maximum_integer_is_accepted(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("2147483647") == 2147483647

    def test_the_minimum_integer_is_accepted(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("-2147483648") == -2147483648

    def test_decimal_out_of_range(self, evaluator: CQLEvaluator) -> None:
        with pytest.raises(CQLError, match="out of range"):
            evaluator.evaluate_expression("10000000000000000000000000000.0")

    def test_decimal_beyond_eight_places(self, evaluator: CQLEvaluator) -> None:
        with pytest.raises(CQLError, match="exceeds maximum precision of 8 decimal places"):
            evaluator.evaluate_expression("1.123456789")

    def test_eight_decimal_places_are_accepted(self, evaluator: CQLEvaluator) -> None:
        assert str(evaluator.evaluate_expression("1.12345678")) == "1.12345678"


class TestIntervalBoundaryValidation:
    """An interval selector rejects a high bound below its low bound, and empty open intervals."""

    def test_high_below_low(self, evaluator: CQLEvaluator) -> None:
        with pytest.raises(CQLError, match="the ending boundary"):
            evaluator.evaluate_expression("Interval[10, 1]")

    @pytest.mark.parametrize("expression", ["Interval[5, 5)", "Interval(5, 5]", "Interval(5, 5)"])
    def test_empty_open_interval(self, evaluator: CQLEvaluator, expression: str) -> None:
        with pytest.raises(CQLError, match="the ending boundary must be greater than"):
            evaluator.evaluate_expression(expression)

    def test_incomparable_bounds_are_left_alone(self, evaluator: CQLEvaluator) -> None:
        result = evaluator.evaluate_expression("Interval['a', 1]")
        assert result is not None
        assert result.low == "a"
        assert result.high == 1


class TestExtractorArity:
    """`singleton from` and `point from` reject inputs they cannot reduce to one value."""

    def test_singleton_from_a_longer_list(self, evaluator: CQLEvaluator) -> None:
        with pytest.raises(CQLError, match="singleton from requires a list with at most one element"):
            evaluator.evaluate_expression("singleton from {1, 2}")

    def test_point_from_a_wide_interval(self, evaluator: CQLEvaluator) -> None:
        with pytest.raises(CQLError, match="point from requires a unit interval"):
            evaluator.evaluate_expression("point from Interval[1, 10]")

    def test_point_from_a_half_open_unit_interval(self, evaluator: CQLEvaluator) -> None:
        with pytest.raises(CQLError, match="point from requires a unit interval"):
            evaluator.evaluate_expression("point from Interval[1, 10)")

    def test_point_from_function_on_a_wide_interval(self, evaluator: CQLEvaluator) -> None:
        with pytest.raises(CQLError, match="pointFrom requires a unit interval"):
            evaluator.evaluate_expression("PointFrom(Interval[1, 10])")


class TestSuccessorAndPredecessorBounds:
    """Stepping past the end of the Time domain raises rather than wrapping."""

    def test_successor_of_the_last_time(self, evaluator: CQLEvaluator) -> None:
        with pytest.raises(CQLError, match="successor of maximum time value would overflow"):
            evaluator.evaluate_expression("successor of @T23:59:59.999")

    def test_predecessor_of_the_first_time(self, evaluator: CQLEvaluator) -> None:
        with pytest.raises(CQLError, match="predecessor of minimum time value would underflow"):
            evaluator.evaluate_expression("predecessor of @T00:00:00.000")


class TestDateArithmeticRange:
    """Date arithmetic that leaves the 1-9999 year range raises."""

    def test_adding_past_year_9999(self, evaluator: CQLEvaluator) -> None:
        with pytest.raises(CQLError, match="out of range"):
            evaluator.evaluate_expression("@9999-12-31 + 1 year")

    def test_subtracting_below_year_1(self, evaluator: CQLEvaluator) -> None:
        with pytest.raises(CQLError, match="out of range"):
            evaluator.evaluate_expression("@0001-01-01 - 1 year")

    def test_adding_months_past_year_9999(self, evaluator: CQLEvaluator) -> None:
        with pytest.raises(CQLError, match="out of range"):
            evaluator.evaluate_expression("@9999-12-01 + 1 month")

    def test_subtracting_months_below_year_1(self, evaluator: CQLEvaluator) -> None:
        with pytest.raises(CQLError, match="out of range"):
            evaluator.evaluate_expression("@0001-01-01 - 1 month")

    def test_datetime_adding_years_past_year_9999(self, evaluator: CQLEvaluator) -> None:
        with pytest.raises(CQLError, match="out of range"):
            evaluator.evaluate_expression("@9999-12-31T10:00:00 + 1 year")

    def test_datetime_adding_months_past_year_9999(self, evaluator: CQLEvaluator) -> None:
        with pytest.raises(CQLError, match="out of range"):
            evaluator.evaluate_expression("@9999-12-01T10:00:00 + 1 month")


CONVERT_FAILURES: list[tuple[str, str]] = [
    ("convert 'abc' to Integer", "Cannot convert 'abc' to Integer"),
    ("convert 'zz' to Decimal", "Cannot convert 'zz' to Decimal"),
    ("convert 'maybe' to Boolean", "Cannot convert 'maybe' to Boolean"),
    ("convert 5 to Boolean", "Cannot convert value to Boolean"),
    ("convert 'abc' to Quantity", "Cannot convert 'abc' to Quantity"),
]


class TestConvertFailures:
    """`convert` raises where the ToX functions would answer null."""

    @pytest.mark.parametrize(("expression", "message"), CONVERT_FAILURES)
    def test_convert_raises(self, evaluator: CQLEvaluator, expression: str, message: str) -> None:
        with pytest.raises(CQLError, match=message):
            evaluator.evaluate_expression(expression)

    def test_the_matching_to_function_answers_null_instead(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("ToInteger('abc')") is None


class TestExternalFunctions:
    """An `external` function without a registered implementation raises on call."""

    def test_missing_implementation(self, evaluator: CQLEvaluator) -> None:
        evaluator.compile("""
            library External version '1.0'
            define function Missing(a Integer) returns Integer: external
            define Uses: Missing(1)
        """)
        with pytest.raises(CQLError, match="External function 'Missing' declared but no implementation found"):
            evaluator.evaluate_definition("Uses")


class TestRecursiveDefinitions:
    """A definition cycle is detected instead of recursing until the stack runs out."""

    def test_two_definitions_referring_to_each_other(self, evaluator: CQLEvaluator) -> None:
        evaluator.compile("""
            library Recursion version '1.0'
            define A: B
            define B: A
        """)
        with pytest.raises(CQLError, match="Recursive definition detected: B"):
            evaluator.evaluate_definition("A")

    def test_a_definition_referring_to_itself(self, evaluator: CQLEvaluator) -> None:
        evaluator.compile("""
            library Recursion version '1.0'
            define Loop: Loop + 1
        """)
        with pytest.raises(CQLError, match="Recursive definition detected: Loop"):
            evaluator.evaluate_definition("Loop")


class TestSyntaxErrors:
    """Grammar failures surface as CQLError with the offending position."""

    @pytest.mark.parametrize(
        "expression",
        ["Interval[1", "Interval[1, 2", "'unterminated", "Tuple { a:"],
    )
    def test_malformed_expression(self, evaluator: CQLEvaluator, expression: str) -> None:
        with pytest.raises(CQLError, match="Syntax error"):
            evaluator.evaluate_expression(expression)

    def test_malformed_library(self, evaluator: CQLEvaluator) -> None:
        with pytest.raises(CQLError, match="Syntax error"):
            evaluator.compile("library Broken version '1.0'\ndefine X: 1 +")


class TestUnresolvedNames:
    """Unknown identifiers and functions evaluate to null rather than raising."""

    def test_unknown_identifier(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("UnknownIdentifier") is None

    def test_unknown_function(self, evaluator: CQLEvaluator) -> None:
        assert evaluator.evaluate_expression("UnknownFunction(1)") is None

    def test_unknown_definition_reference(self, evaluator: CQLEvaluator) -> None:
        evaluator.compile("""
            library Unresolved version '1.0'
            define Uses: Nope
        """)
        assert evaluator.evaluate_definition("Uses") is None

    def test_a_user_function_called_with_too_few_arguments(self, evaluator: CQLEvaluator) -> None:
        evaluator.compile("""
            library Arity version '1.0'
            define function Add(a Integer, b Integer): a + b
            define TooFew: Add(1)
        """)
        assert evaluator.evaluate_definition("TooFew") is None

    def test_a_user_function_called_with_extra_arguments_ignores_them(self, evaluator: CQLEvaluator) -> None:
        evaluator.compile("""
            library Arity version '1.0'
            define function Add(a Integer, b Integer): a + b
            define TooMany: Add(1, 2, 3)
        """)
        assert evaluator.evaluate_definition("TooMany") == 3

    def test_a_qualified_call_into_a_library_that_lacks_the_function(self, evaluator: CQLEvaluator) -> None:
        from dhis2w_fhir_engine.engine.cql import InMemoryLibraryResolver

        resolver = InMemoryLibraryResolver({"Helper": "library Helper version '1.0'\ndefine Answer: 42"})
        with_include = CQLEvaluator(library_resolver=resolver)
        with_include.compile("""
            library Main version '1.0'
            include Helper version '1.0' called H
            define Uses: H.Missing(1)
        """)
        assert with_include.evaluate_definition("Uses") is None


class TestDivisionByZero:
    """Division by zero answers null in every spelling."""

    @pytest.mark.parametrize("expression", ["10 / 0", "10 div 0", "10 mod 0", "10.0 / 0", "10 / 0.0"])
    def test_zero_divisor(self, evaluator: CQLEvaluator, expression: str) -> None:
        assert evaluator.evaluate_expression(expression) is None
