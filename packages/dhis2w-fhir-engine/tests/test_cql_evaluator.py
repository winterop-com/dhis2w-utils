"""Comprehensive tests for CQL evaluator.

This module contains 150+ test cases covering:
- Literals (boolean, string, number, date/time, null)
- Arithmetic operations (+, -, *, /, div, mod, ^)
- Comparison operations (=, !=, <, <=, >, >=, ~, !~)
- Boolean operations (and, or, not, xor, implies)
- Conditional expressions (if-then-else, case)
- String operations (concatenation, length)
- List operations (list selectors, membership)
- Interval operations (contains, includes, overlaps)
- Type operations (is, as)
- Built-in functions
- Library compilation and definition evaluation
- Error handling
"""

from decimal import Decimal

import pytest

from dhis2w_fhir_engine.engine.cql import (
    CQLCode,
    CQLConcept,
    CQLEvaluator,
    CQLInterval,
    CQLTuple,
    compile_library,
    evaluate,
)
from dhis2w_fhir_engine.engine.exceptions import CQLError

# =============================================================================
# Literal Tests
# =============================================================================


class TestBooleanLiterals:
    """Test boolean literal evaluation."""

    def test_true_literal(self) -> None:
        assert evaluate("true") is True

    def test_false_literal(self) -> None:
        assert evaluate("false") is False


class TestNullLiteral:
    """Test null literal evaluation."""

    def test_null_literal(self) -> None:
        assert evaluate("null") is None

    def test_null_uppercase(self) -> None:
        assert evaluate("NULL") is None


class TestIntegerLiterals:
    """Test integer literal evaluation."""

    def test_zero(self) -> None:
        assert evaluate("0") == 0

    def test_positive_integer(self) -> None:
        assert evaluate("42") == 42

    def test_large_integer(self) -> None:
        assert evaluate("999999") == 999999

    def test_negative_integer(self) -> None:
        assert evaluate("-42") == -42

    def test_negative_zero(self) -> None:
        assert evaluate("-0") == 0


class TestDecimalLiterals:
    """Test decimal literal evaluation."""

    def test_simple_decimal(self) -> None:
        result = evaluate("3.14")
        assert isinstance(result, Decimal)
        assert result == Decimal("3.14")

    def test_zero_decimal(self) -> None:
        assert evaluate("0.0") == Decimal("0.0")

    def test_negative_decimal(self) -> None:
        assert evaluate("-3.14") == Decimal("-3.14")

    def test_leading_zero(self) -> None:
        assert evaluate("0.5") == Decimal("0.5")

    def test_many_decimal_places(self) -> None:
        assert evaluate("3.14159265") == Decimal("3.14159265")


class TestStringLiterals:
    """Test string literal evaluation."""

    def test_empty_string(self) -> None:
        assert evaluate("''") == ""

    def test_simple_string(self) -> None:
        assert evaluate("'hello'") == "hello"

    def test_string_with_spaces(self) -> None:
        assert evaluate("'hello world'") == "hello world"

    def test_string_with_numbers(self) -> None:
        assert evaluate("'abc123'") == "abc123"

    def test_string_with_special_chars(self) -> None:
        assert evaluate("'hello-world_test'") == "hello-world_test"

    def test_escaped_single_quote(self) -> None:
        assert evaluate("'it\\'s'") == "it's"


# =============================================================================
# Arithmetic Tests
# =============================================================================


class TestAddition:
    """Test addition operations."""

    def test_add_two_integers(self) -> None:
        assert evaluate("1 + 2") == 3

    def test_add_three_integers(self) -> None:
        assert evaluate("1 + 2 + 3") == 6

    def test_add_negative(self) -> None:
        assert evaluate("5 + (-3)") == 2

    def test_add_decimals(self) -> None:
        assert evaluate("1.5 + 2.5") == Decimal("4.0")

    def test_add_integer_and_decimal(self) -> None:
        result = evaluate("1 + 2.5")
        assert result == Decimal("3.5")

    def test_add_with_null_left(self) -> None:
        assert evaluate("null + 1") is None

    def test_add_with_null_right(self) -> None:
        assert evaluate("1 + null") is None

    def test_add_both_null(self) -> None:
        assert evaluate("null + null") is None


class TestSubtraction:
    """Test subtraction operations."""

    def test_subtract_integers(self) -> None:
        assert evaluate("5 - 3") == 2

    def test_subtract_negative_result(self) -> None:
        assert evaluate("3 - 5") == -2

    def test_subtract_from_zero(self) -> None:
        assert evaluate("0 - 5") == -5

    def test_subtract_decimals(self) -> None:
        assert evaluate("5.5 - 2.5") == Decimal("3.0")

    def test_subtract_with_null(self) -> None:
        assert evaluate("5 - null") is None


class TestMultiplication:
    """Test multiplication operations."""

    def test_multiply_integers(self) -> None:
        assert evaluate("3 * 4") == 12

    def test_multiply_by_zero(self) -> None:
        assert evaluate("5 * 0") == 0

    def test_multiply_by_one(self) -> None:
        assert evaluate("5 * 1") == 5

    def test_multiply_negative(self) -> None:
        assert evaluate("5 * (-3)") == -15

    def test_multiply_decimals(self) -> None:
        assert evaluate("2.5 * 4") == Decimal("10.0")

    def test_multiply_with_null(self) -> None:
        assert evaluate("5 * null") is None


class TestDivision:
    """Test division operations."""

    def test_divide_integers(self) -> None:
        result = evaluate("10 / 2")
        assert result == Decimal("5")

    def test_divide_with_remainder(self) -> None:
        result = evaluate("10 / 4")
        assert result == Decimal("2.5")

    def test_divide_decimals(self) -> None:
        result = evaluate("10.0 / 4.0")
        assert result == Decimal("2.5")

    def test_divide_by_zero(self) -> None:
        assert evaluate("10 / 0") is None

    def test_divide_by_one(self) -> None:
        assert evaluate("10 / 1") == Decimal("10")

    def test_divide_with_null(self) -> None:
        assert evaluate("10 / null") is None


class TestIntegerDivision:
    """Test truncated (integer) division."""

    def test_div_exact(self) -> None:
        assert evaluate("10 div 2") == 5

    def test_div_truncate(self) -> None:
        assert evaluate("10 div 3") == 3

    def test_div_by_one(self) -> None:
        assert evaluate("10 div 1") == 10

    def test_div_by_zero(self) -> None:
        assert evaluate("10 div 0") is None

    def test_div_negative(self) -> None:
        # CQL spec: truncated division toward zero, not floor
        assert evaluate("(-10) div 3") == -3


class TestModulo:
    """Test modulo operations."""

    def test_mod_with_remainder(self) -> None:
        assert evaluate("10 mod 3") == 1

    def test_mod_no_remainder(self) -> None:
        assert evaluate("10 mod 2") == 0

    def test_mod_by_one(self) -> None:
        assert evaluate("10 mod 1") == 0

    def test_mod_by_zero(self) -> None:
        assert evaluate("10 mod 0") is None

    def test_mod_smaller_dividend(self) -> None:
        assert evaluate("3 mod 10") == 3


class TestPower:
    """Test power operations."""

    def test_power_integers(self) -> None:
        result = evaluate("2 ^ 3")
        assert result == Decimal("8")

    def test_power_zero(self) -> None:
        result = evaluate("2 ^ 0")
        assert result == Decimal("1")

    def test_power_one(self) -> None:
        result = evaluate("2 ^ 1")
        assert result == Decimal("2")


class TestOperatorPrecedence:
    """Test operator precedence."""

    def test_multiply_before_add(self) -> None:
        assert evaluate("1 + 2 * 3") == 7

    def test_divide_before_subtract(self) -> None:
        result = evaluate("10 - 6 / 2")
        assert result == Decimal("7")

    def test_parentheses_override(self) -> None:
        assert evaluate("(1 + 2) * 3") == 9

    def test_nested_parentheses(self) -> None:
        assert evaluate("((1 + 2) * 3) + 4") == 13

    def test_complex_expression(self) -> None:
        result = evaluate("2 + 3 * 4 - 6 / 2")
        assert result == Decimal("11")


# =============================================================================
# Comparison Tests
# =============================================================================


class TestEquality:
    """Test equality comparisons."""

    def test_equal_integers(self) -> None:
        assert evaluate("5 = 5") is True

    def test_not_equal_integers(self) -> None:
        assert evaluate("5 = 6") is False

    def test_equal_strings(self) -> None:
        assert evaluate("'abc' = 'abc'") is True

    def test_not_equal_strings(self) -> None:
        assert evaluate("'abc' = 'def'") is False

    def test_equal_booleans(self) -> None:
        assert evaluate("true = true") is True

    def test_not_equal_booleans(self) -> None:
        assert evaluate("true = false") is False

    def test_equal_with_null(self) -> None:
        assert evaluate("5 = null") is None

    def test_null_equals_null(self) -> None:
        assert evaluate("null = null") is None

    def test_equal_decimals(self) -> None:
        assert evaluate("3.14 = 3.14") is True


class TestNotEqual:
    """Test not-equal comparisons."""

    def test_not_equal_different(self) -> None:
        assert evaluate("5 != 6") is True

    def test_not_equal_same(self) -> None:
        assert evaluate("5 != 5") is False

    def test_not_equal_strings(self) -> None:
        assert evaluate("'abc' != 'def'") is True

    def test_not_equal_with_null(self) -> None:
        assert evaluate("5 != null") is None


class TestLessThan:
    """Test less-than comparisons."""

    def test_less_than_true(self) -> None:
        assert evaluate("3 < 5") is True

    def test_less_than_false(self) -> None:
        assert evaluate("5 < 3") is False

    def test_less_than_equal(self) -> None:
        assert evaluate("5 < 5") is False

    def test_less_than_decimals(self) -> None:
        assert evaluate("3.14 < 3.15") is True

    def test_less_than_strings(self) -> None:
        assert evaluate("'abc' < 'abd'") is True

    def test_less_than_with_null(self) -> None:
        assert evaluate("3 < null") is None


class TestLessThanOrEqual:
    """Test less-than-or-equal comparisons."""

    def test_less_or_equal_less(self) -> None:
        assert evaluate("3 <= 5") is True

    def test_less_or_equal_equal(self) -> None:
        assert evaluate("5 <= 5") is True

    def test_less_or_equal_greater(self) -> None:
        assert evaluate("7 <= 5") is False

    def test_less_or_equal_with_null(self) -> None:
        assert evaluate("3 <= null") is None


class TestGreaterThan:
    """Test greater-than comparisons."""

    def test_greater_than_true(self) -> None:
        assert evaluate("5 > 3") is True

    def test_greater_than_false(self) -> None:
        assert evaluate("3 > 5") is False

    def test_greater_than_equal(self) -> None:
        assert evaluate("5 > 5") is False

    def test_greater_than_with_null(self) -> None:
        assert evaluate("5 > null") is None


class TestGreaterThanOrEqual:
    """Test greater-than-or-equal comparisons."""

    def test_greater_or_equal_greater(self) -> None:
        assert evaluate("7 >= 5") is True

    def test_greater_or_equal_equal(self) -> None:
        assert evaluate("5 >= 5") is True

    def test_greater_or_equal_less(self) -> None:
        assert evaluate("3 >= 5") is False

    def test_greater_or_equal_with_null(self) -> None:
        assert evaluate("5 >= null") is None


# =============================================================================
# Boolean Operations Tests
# =============================================================================


class TestAnd:
    """Test AND operations."""

    def test_and_true_true(self) -> None:
        assert evaluate("true and true") is True

    def test_and_true_false(self) -> None:
        assert evaluate("true and false") is False

    def test_and_false_true(self) -> None:
        assert evaluate("false and true") is False

    def test_and_false_false(self) -> None:
        assert evaluate("false and false") is False

    def test_and_true_null(self) -> None:
        assert evaluate("true and null") is None

    def test_and_null_true(self) -> None:
        assert evaluate("null and true") is None

    def test_and_false_null(self) -> None:
        # False AND anything is False
        assert evaluate("false and null") is False

    def test_and_null_false(self) -> None:
        assert evaluate("null and false") is False

    def test_and_null_null(self) -> None:
        assert evaluate("null and null") is None

    def test_and_chained(self) -> None:
        assert evaluate("true and true and true") is True

    def test_and_chained_with_false(self) -> None:
        assert evaluate("true and false and true") is False


class TestOr:
    """Test OR operations."""

    def test_or_true_true(self) -> None:
        assert evaluate("true or true") is True

    def test_or_true_false(self) -> None:
        assert evaluate("true or false") is True

    def test_or_false_true(self) -> None:
        assert evaluate("false or true") is True

    def test_or_false_false(self) -> None:
        assert evaluate("false or false") is False

    def test_or_true_null(self) -> None:
        # True OR anything is True
        assert evaluate("true or null") is True

    def test_or_null_true(self) -> None:
        assert evaluate("null or true") is True

    def test_or_false_null(self) -> None:
        assert evaluate("false or null") is None

    def test_or_null_false(self) -> None:
        assert evaluate("null or false") is None

    def test_or_null_null(self) -> None:
        assert evaluate("null or null") is None

    def test_or_chained(self) -> None:
        assert evaluate("false or false or true") is True


class TestNot:
    """Test NOT operations."""

    def test_not_true(self) -> None:
        assert evaluate("not true") is False

    def test_not_false(self) -> None:
        assert evaluate("not false") is True

    def test_not_null(self) -> None:
        assert evaluate("not null") is None

    def test_double_not(self) -> None:
        assert evaluate("not not true") is True


class TestXor:
    """Test XOR operations."""

    def test_xor_true_true(self) -> None:
        assert evaluate("true xor true") is False

    def test_xor_true_false(self) -> None:
        assert evaluate("true xor false") is True

    def test_xor_false_true(self) -> None:
        assert evaluate("false xor true") is True

    def test_xor_false_false(self) -> None:
        assert evaluate("false xor false") is False

    def test_xor_with_null(self) -> None:
        assert evaluate("true xor null") is None
        assert evaluate("null xor true") is None


class TestImplies:
    """Test IMPLIES operations."""

    def test_implies_false_anything(self) -> None:
        # False implies anything is True
        assert evaluate("false implies true") is True
        assert evaluate("false implies false") is True

    def test_implies_true_true(self) -> None:
        assert evaluate("true implies true") is True

    def test_implies_true_false(self) -> None:
        assert evaluate("true implies false") is False

    def test_implies_with_null(self) -> None:
        assert evaluate("true implies null") is None


# =============================================================================
# Conditional Expression Tests
# =============================================================================


class TestIfThenElse:
    """Test if-then-else expressions."""

    def test_if_true(self) -> None:
        assert evaluate("if true then 1 else 2") == 1

    def test_if_false(self) -> None:
        assert evaluate("if false then 1 else 2") == 2

    def test_if_null(self) -> None:
        assert evaluate("if null then 1 else 2") == 2

    def test_if_with_strings(self) -> None:
        assert evaluate("if true then 'yes' else 'no'") == "yes"

    def test_if_nested(self) -> None:
        assert evaluate("if true then if false then 1 else 2 else 3") == 2

    def test_if_with_comparison(self) -> None:
        assert evaluate("if 5 > 3 then 'greater' else 'less'") == "greater"

    def test_if_with_arithmetic_in_branches(self) -> None:
        assert evaluate("if true then 1 + 2 else 3 + 4") == 3


# =============================================================================
# String Operations Tests
# =============================================================================


class TestStringConcatenation:
    """Test string concatenation."""

    def test_concat_two_strings(self) -> None:
        assert evaluate("'hello' & ' world'") == "hello world"

    def test_concat_empty_string(self) -> None:
        assert evaluate("'hello' & ''") == "hello"

    def test_concat_with_null(self) -> None:
        assert evaluate("'hello' & null") == "hello"

    def test_concat_null_first(self) -> None:
        assert evaluate("null & 'world'") == "world"

    def test_concat_multiple(self) -> None:
        assert evaluate("'a' & 'b' & 'c'") == "abc"


# =============================================================================
# List Operations Tests
# =============================================================================


class TestListSelectors:
    """Test list selector expressions."""

    def test_empty_list(self) -> None:
        assert evaluate("{}") == []

    def test_single_element(self) -> None:
        assert evaluate("{1}") == [1]

    def test_multiple_integers(self) -> None:
        assert evaluate("{1, 2, 3}") == [1, 2, 3]

    def test_multiple_strings(self) -> None:
        assert evaluate("{'a', 'b', 'c'}") == ["a", "b", "c"]

    def test_mixed_types(self) -> None:
        assert evaluate("{1, 'two', true}") == [1, "two", True]

    def test_nested_expressions(self) -> None:
        assert evaluate("{1 + 1, 2 + 2, 3 + 3}") == [2, 4, 6]


class TestMembershipIn:
    """Test 'in' membership operator."""

    def test_in_list_found(self) -> None:
        assert evaluate("2 in {1, 2, 3}") is True

    def test_in_list_not_found(self) -> None:
        assert evaluate("5 in {1, 2, 3}") is False

    def test_in_empty_list(self) -> None:
        assert evaluate("1 in {}") is False

    def test_in_with_string(self) -> None:
        assert evaluate("'b' in {'a', 'b', 'c'}") is True


class TestMembershipContains:
    """Test 'contains' membership operator."""

    def test_contains_found(self) -> None:
        assert evaluate("{1, 2, 3} contains 2") is True

    def test_contains_not_found(self) -> None:
        assert evaluate("{1, 2, 3} contains 5") is False

    def test_contains_empty_list(self) -> None:
        assert evaluate("{} contains 1") is False


class TestExists:
    """Test exists operator."""

    def test_exists_non_empty(self) -> None:
        assert evaluate("exists {1, 2, 3}") is True

    def test_exists_empty(self) -> None:
        assert evaluate("exists {}") is False

    def test_exists_single(self) -> None:
        assert evaluate("exists {1}") is True


# =============================================================================
# Interval Tests
# =============================================================================


class TestIntervalSelectors:
    """Test interval selector expressions."""

    def test_closed_interval(self) -> None:
        result = evaluate("Interval[1, 10]")
        assert isinstance(result, CQLInterval)
        assert result.low == 1
        assert result.high == 10
        assert result.low_closed is True
        assert result.high_closed is True

    def test_open_interval(self) -> None:
        result = evaluate("Interval(1, 10)")
        assert isinstance(result, CQLInterval)
        assert result.low_closed is False
        assert result.high_closed is False

    def test_half_open_left(self) -> None:
        result = evaluate("Interval(1, 10]")
        assert result.low_closed is False
        assert result.high_closed is True

    def test_half_open_right(self) -> None:
        result = evaluate("Interval[1, 10)")
        assert result.low_closed is True
        assert result.high_closed is False


class TestIntervalContains:
    """Test interval contains operations."""

    def test_interval_contains_in_range(self) -> None:
        interval: CQLInterval[int] = CQLInterval(low=1, high=10)
        assert 5 in interval

    def test_interval_contains_at_low(self) -> None:
        interval: CQLInterval[int] = CQLInterval(low=1, high=10)
        assert 1 in interval

    def test_interval_contains_at_high(self) -> None:
        interval: CQLInterval[int] = CQLInterval(low=1, high=10)
        assert 10 in interval

    def test_interval_not_contains_below(self) -> None:
        interval: CQLInterval[int] = CQLInterval(low=1, high=10)
        assert 0 not in interval

    def test_interval_not_contains_above(self) -> None:
        interval: CQLInterval[int] = CQLInterval(low=1, high=10)
        assert 11 not in interval

    def test_open_interval_excludes_bounds(self) -> None:
        interval: CQLInterval[int] = CQLInterval(low=1, high=10, low_closed=False, high_closed=False)
        assert 1 not in interval
        assert 10 not in interval
        assert 5 in interval


# =============================================================================
# Boolean Expression Tests (is null, is true, etc.)
# =============================================================================


class TestIsNull:
    """Test IS NULL expressions."""

    def test_null_is_null(self) -> None:
        assert evaluate("null is null") is True

    def test_value_is_null(self) -> None:
        assert evaluate("1 is null") is False

    def test_string_is_null(self) -> None:
        assert evaluate("'hello' is null") is False


class TestIsNotNull:
    """Test IS NOT NULL expressions."""

    def test_value_is_not_null(self) -> None:
        assert evaluate("1 is not null") is True

    def test_null_is_not_null(self) -> None:
        assert evaluate("null is not null") is False


class TestIsTrue:
    """Test IS TRUE expressions."""

    def test_true_is_true(self) -> None:
        assert evaluate("true is true") is True

    def test_false_is_true(self) -> None:
        assert evaluate("false is true") is False

    def test_null_is_true(self) -> None:
        assert evaluate("null is true") is False


class TestIsFalse:
    """Test IS FALSE expressions."""

    def test_false_is_false(self) -> None:
        assert evaluate("false is false") is True

    def test_true_is_false(self) -> None:
        assert evaluate("true is false") is False

    def test_null_is_false(self) -> None:
        assert evaluate("null is false") is False


# =============================================================================
# Between Expression Tests
# =============================================================================


class TestBetween:
    """Test between expressions."""

    def test_between_in_range(self) -> None:
        assert evaluate("5 between 1 and 10") is True

    def test_between_at_low(self) -> None:
        assert evaluate("1 between 1 and 10") is True

    def test_between_at_high(self) -> None:
        assert evaluate("10 between 1 and 10") is True

    def test_between_below(self) -> None:
        assert evaluate("0 between 1 and 10") is False

    def test_between_above(self) -> None:
        assert evaluate("11 between 1 and 10") is False

    def test_between_with_decimals(self) -> None:
        assert evaluate("5.5 between 1.0 and 10.0") is True


# =============================================================================
# Built-in Function Tests
# =============================================================================


class TestCountFunction:
    """Test Count function."""

    def test_count_list(self) -> None:
        assert evaluate("Count({1, 2, 3})") == 3

    def test_count_empty(self) -> None:
        assert evaluate("Count({})") == 0

    def test_count_single(self) -> None:
        assert evaluate("Count({42})") == 1


class TestFirstFunction:
    """Test First function."""

    def test_first_list(self) -> None:
        assert evaluate("First({1, 2, 3})") == 1

    def test_first_single(self) -> None:
        assert evaluate("First({42})") == 42

    def test_first_empty(self) -> None:
        assert evaluate("First({})") is None


class TestLastFunction:
    """Test Last function."""

    def test_last_list(self) -> None:
        assert evaluate("Last({1, 2, 3})") == 3

    def test_last_single(self) -> None:
        assert evaluate("Last({42})") == 42

    def test_last_empty(self) -> None:
        assert evaluate("Last({})") is None


class TestSumFunction:
    """Test Sum function."""

    def test_sum_integers(self) -> None:
        assert evaluate("Sum({1, 2, 3, 4})") == 10

    def test_sum_single(self) -> None:
        assert evaluate("Sum({42})") == 42

    def test_sum_empty(self) -> None:
        assert evaluate("Sum({})") is None


class TestAvgFunction:
    """Test Avg function."""

    def test_avg_integers(self) -> None:
        assert evaluate("Avg({1, 2, 3})") == 2

    def test_avg_single(self) -> None:
        assert evaluate("Avg({10})") == 10

    def test_avg_empty(self) -> None:
        assert evaluate("Avg({})") is None


class TestMinFunction:
    """Test Min function."""

    def test_min_integers(self) -> None:
        assert evaluate("Min({3, 1, 4, 1, 5})") == 1

    def test_min_single(self) -> None:
        assert evaluate("Min({42})") == 42

    def test_min_empty(self) -> None:
        assert evaluate("Min({})") is None


class TestMaxFunction:
    """Test Max function."""

    def test_max_integers(self) -> None:
        assert evaluate("Max({3, 1, 4, 1, 5})") == 5

    def test_max_single(self) -> None:
        assert evaluate("Max({42})") == 42

    def test_max_empty(self) -> None:
        assert evaluate("Max({})") is None


class TestCoalesceFunction:
    """Test Coalesce function."""

    def test_coalesce_first_not_null(self) -> None:
        assert evaluate("Coalesce(1, 2, 3)") == 1

    def test_coalesce_first_null(self) -> None:
        assert evaluate("Coalesce(null, 2, 3)") == 2

    def test_coalesce_all_null(self) -> None:
        assert evaluate("Coalesce(null, null, null)") is None

    def test_coalesce_with_string(self) -> None:
        assert evaluate("Coalesce(null, 'default')") == "default"


class TestToStringFunction:
    """Test ToString function."""

    def test_tostring_integer(self) -> None:
        assert evaluate("ToString(42)") == "42"

    def test_tostring_decimal(self) -> None:
        result = evaluate("ToString(3.14)")
        assert result == "3.14"

    def test_tostring_boolean(self) -> None:
        # CQL spec requires lowercase 'true'/'false'
        assert evaluate("ToString(true)") == "true"

    def test_tostring_null(self) -> None:
        assert evaluate("ToString(null)") is None


class TestToIntegerFunction:
    """Test ToInteger function."""

    def test_tointeger_from_string(self) -> None:
        assert evaluate("ToInteger('42')") == 42

    def test_tointeger_null(self) -> None:
        assert evaluate("ToInteger(null)") is None

    def test_tointeger_invalid_string(self) -> None:
        assert evaluate("ToInteger('abc')") is None


class TestToDecimalFunction:
    """Test ToDecimal function."""

    def test_todecimal_from_string(self) -> None:
        result = evaluate("ToDecimal('3.14')")
        assert result == Decimal("3.14")

    def test_todecimal_from_integer_string(self) -> None:
        result = evaluate("ToDecimal('42')")
        assert result == Decimal("42")

    def test_todecimal_null(self) -> None:
        assert evaluate("ToDecimal(null)") is None


class TestExistsFunction:
    """Test Exists function."""

    def test_exists_non_empty_list(self) -> None:
        assert evaluate("Exists({1, 2, 3})") is True

    def test_exists_empty_list(self) -> None:
        assert evaluate("Exists({})") is False

    def test_exists_null(self) -> None:
        assert evaluate("Exists(null)") is False


# =============================================================================
# Library Compilation Tests
# =============================================================================


class TestLibraryCompilation:
    """Test CQL library compilation."""

    def test_compile_minimal_library(self) -> None:
        source = """
        library Test version '1.0'
        using FHIR version '4.0.1'
        define X: 1
        """
        lib = compile_library(source)
        assert lib.name == "Test"
        assert lib.version == "1.0"

    def test_compile_with_using(self) -> None:
        source = """
        library Test version '1.0'
        using FHIR version '4.0.1'
        define X: 1
        """
        lib = compile_library(source)
        assert len(lib.using) == 1
        assert lib.using[0].model == "FHIR"
        assert lib.using[0].version == "4.0.1"

    def test_compile_multiple_definitions(self) -> None:
        source = """
        library Test version '1.0'
        using FHIR version '4.0.1'
        define A: 1
        define B: 2
        define C: 3
        """
        lib = compile_library(source)
        assert len(lib.definitions) == 3
        assert "A" in lib.definitions
        assert "B" in lib.definitions
        assert "C" in lib.definitions

    def test_library_without_version(self) -> None:
        source = """
        library Test
        using FHIR version '4.0.1'
        define X: 1
        """
        lib = compile_library(source)
        assert lib.name == "Test"
        assert lib.version is None


class TestDefinitionEvaluation:
    """Test evaluating library definitions."""

    def test_evaluate_simple_definition(self) -> None:
        evaluator = CQLEvaluator()
        evaluator.compile("""
        library Test version '1.0'
        using FHIR version '4.0.1'
        define Value: 42
        """)
        assert evaluator.evaluate_definition("Value") == 42

    def test_evaluate_expression_definition(self) -> None:
        evaluator = CQLEvaluator()
        evaluator.compile("""
        library Test version '1.0'
        using FHIR version '4.0.1'
        define Sum: 1 + 2 + 3 + 4 + 5
        """)
        assert evaluator.evaluate_definition("Sum") == 15

    def test_evaluate_dependent_definitions(self) -> None:
        evaluator = CQLEvaluator()
        evaluator.compile("""
        library Test version '1.0'
        using FHIR version '4.0.1'
        define A: 10
        define B: 20
        define Sum: A + B
        """)
        assert evaluator.evaluate_definition("Sum") == 30

    def test_evaluate_chain_of_definitions(self) -> None:
        evaluator = CQLEvaluator()
        evaluator.compile("""
        library Test version '1.0'
        using FHIR version '4.0.1'
        define A: 1
        define B: A + 1
        define C: B + 1
        define D: C + 1
        """)
        assert evaluator.evaluate_definition("D") == 4

    def test_evaluate_all_definitions(self) -> None:
        evaluator = CQLEvaluator()
        evaluator.compile("""
        library Test version '1.0'
        using FHIR version '4.0.1'
        define A: 1
        define B: 2
        define C: 3
        """)
        results = evaluator.evaluate_all_definitions()
        assert results == {"A": 1, "B": 2, "C": 3}


class TestDefinitionErrors:
    """Test definition evaluation errors."""

    def test_definition_not_found(self) -> None:
        evaluator = CQLEvaluator()
        evaluator.compile("""
        library Test version '1.0'
        using FHIR version '4.0.1'
        define X: 1
        """)
        with pytest.raises(CQLError, match="Definition not found"):
            evaluator.evaluate_definition("NonExistent")

    def test_no_library_loaded(self) -> None:
        evaluator = CQLEvaluator()
        with pytest.raises(CQLError, match="No library loaded"):
            evaluator.evaluate_definition("X")

    def test_recursive_definition(self) -> None:
        evaluator = CQLEvaluator()
        evaluator.compile("""
        library Test version '1.0'
        using FHIR version '4.0.1'
        define A: B
        define B: A
        """)
        with pytest.raises(CQLError, match="Recursive definition"):
            evaluator.evaluate_definition("A")


# =============================================================================
# Type System Tests
# =============================================================================


class TestCQLCode:
    """Test CQLCode type."""

    def test_create_code(self) -> None:
        code = CQLCode(code="123", system="http://example.com")
        assert code.code == "123"
        assert code.system == "http://example.com"

    def test_code_with_display(self) -> None:
        code = CQLCode(code="123", system="http://example.com", display="Test Code")
        assert code.display == "Test Code"

    def test_code_equality(self) -> None:
        code1 = CQLCode(code="123", system="http://example.com")
        code2 = CQLCode(code="123", system="http://example.com")
        assert code1 == code2

    def test_code_inequality(self) -> None:
        code1 = CQLCode(code="123", system="http://example.com")
        code2 = CQLCode(code="456", system="http://example.com")
        assert code1 != code2

    def test_code_equivalent(self) -> None:
        code1 = CQLCode(code="123", system="http://example.com", display="A")
        code2 = CQLCode(code="123", system="http://example.com", display="B")
        assert code1.equivalent(code2)


class TestCQLInterval:
    """Test CQLInterval type."""

    def test_create_interval(self) -> None:
        interval: CQLInterval[int] = CQLInterval(low=1, high=10)
        assert interval.low == 1
        assert interval.high == 10

    def test_interval_bounds(self) -> None:
        interval: CQLInterval[int] = CQLInterval(low=1, high=10, low_closed=True, high_closed=True)
        assert interval.low_closed is True
        assert interval.high_closed is True

    def test_interval_contains_method(self) -> None:
        interval: CQLInterval[int] = CQLInterval(low=1, high=10)
        assert interval.contains(5) is True
        assert interval.contains(0) is False

    def test_interval_width(self) -> None:
        interval: CQLInterval[int] = CQLInterval(low=1, high=10)
        assert interval.width() == 9

    def test_interval_start_end(self) -> None:
        interval: CQLInterval[int] = CQLInterval(low=1, high=10)
        assert interval.start() == 1
        assert interval.end() == 10


class TestCQLTuple:
    """Test CQLTuple type."""

    def test_create_tuple(self) -> None:
        t = CQLTuple(elements={"a": 1, "b": 2})
        assert t["a"] == 1
        assert t["b"] == 2

    def test_tuple_keys(self) -> None:
        t = CQLTuple(elements={"a": 1, "b": 2})
        assert set(t.keys()) == {"a", "b"}

    def test_tuple_values(self) -> None:
        t = CQLTuple(elements={"a": 1, "b": 2})
        assert set(t.values()) == {1, 2}

    def test_tuple_contains(self) -> None:
        t = CQLTuple(elements={"a": 1, "b": 2})
        assert "a" in t
        assert "c" not in t


class TestCQLConcept:
    """Test CQLConcept type."""

    def test_create_concept(self) -> None:
        code1 = CQLCode(code="123", system="http://example.com")
        code2 = CQLCode(code="456", system="http://example.com")
        concept = CQLConcept(codes=(code1, code2))
        assert len(concept.codes) == 2

    def test_concept_with_display(self) -> None:
        code = CQLCode(code="123", system="http://example.com")
        concept = CQLConcept(codes=(code,), display="Test Concept")
        assert concept.display == "Test Concept"


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestParseErrors:
    """Test parse error handling."""

    def test_invalid_syntax(self) -> None:
        evaluator = CQLEvaluator()
        with pytest.raises(CQLError):
            evaluator.compile("invalid cql !!!")

    def test_incomplete_expression(self) -> None:
        evaluator = CQLEvaluator()
        with pytest.raises(CQLError):
            evaluator.compile("""
            library Test
            define X: 1 +
            """)


# =============================================================================
# Complex Expression Tests
# =============================================================================


class TestComplexExpressions:
    """Test complex expression evaluation."""

    def test_complex_arithmetic(self) -> None:
        result = evaluate("((1 + 2) * 3 - 4) / 5")
        assert result == Decimal("1")

    def test_complex_boolean(self) -> None:
        assert evaluate("(true and false) or (true and true)") is True

    def test_complex_comparison(self) -> None:
        assert evaluate("(5 > 3) and (10 < 20)") is True

    def test_mixed_expression(self) -> None:
        assert evaluate("if 5 > 3 then 10 * 2 else 10 / 2") == 20

    def test_nested_if(self) -> None:
        result = evaluate("if true then if true then 1 else 2 else if true then 3 else 4")
        assert result == 1


# =============================================================================
# Phase 2: List Functions Tests
# =============================================================================


class TestTailFunction:
    """Test Tail function - returns all except first element."""

    def test_tail_of_list(self) -> None:
        assert evaluate("Tail({1, 2, 3, 4})") == [2, 3, 4]

    def test_tail_of_single_element(self) -> None:
        assert evaluate("Tail({1})") == []

    def test_tail_of_empty_list(self) -> None:
        assert evaluate("Tail({})") == []

    def test_tail_of_strings(self) -> None:
        assert evaluate("Tail({'a', 'b', 'c'})") == ["b", "c"]


class TestTakeFunction:
    """Test Take function - returns first n elements."""

    def test_take_two(self) -> None:
        assert evaluate("Take({1, 2, 3, 4}, 2)") == [1, 2]

    def test_take_zero(self) -> None:
        assert evaluate("Take({1, 2, 3}, 0)") == []

    def test_take_more_than_length(self) -> None:
        assert evaluate("Take({1, 2}, 5)") == [1, 2]

    def test_take_from_empty(self) -> None:
        assert evaluate("Take({}, 2)") == []

    def test_take_all(self) -> None:
        assert evaluate("Take({1, 2, 3}, 3)") == [1, 2, 3]


class TestSkipFunction:
    """Test Skip function - skips first n elements."""

    def test_skip_two(self) -> None:
        assert evaluate("Skip({1, 2, 3, 4}, 2)") == [3, 4]

    def test_skip_zero(self) -> None:
        assert evaluate("Skip({1, 2, 3}, 0)") == [1, 2, 3]

    def test_skip_all(self) -> None:
        assert evaluate("Skip({1, 2, 3}, 3)") == []

    def test_skip_more_than_length(self) -> None:
        assert evaluate("Skip({1, 2}, 5)") == []

    def test_skip_from_empty(self) -> None:
        assert evaluate("Skip({}, 2)") == []


class TestFlattenFunction:
    """Test Flatten function - flattens nested lists."""

    def test_flatten_nested(self) -> None:
        result = evaluate("Flatten({{1, 2}, {3, 4}})")
        assert result == [1, 2, 3, 4]

    def test_flatten_mixed(self) -> None:
        result = evaluate("Flatten({1, {2, 3}, 4})")
        assert result == [1, 2, 3, 4]

    def test_flatten_already_flat(self) -> None:
        assert evaluate("Flatten({1, 2, 3})") == [1, 2, 3]

    def test_flatten_empty(self) -> None:
        assert evaluate("Flatten({})") == []


class TestDistinctFunction:
    """Test Distinct function - removes duplicates."""

    def test_distinct_with_duplicates(self) -> None:
        assert evaluate("Distinct({1, 2, 1, 3, 2})") == [1, 2, 3]

    def test_distinct_no_duplicates(self) -> None:
        assert evaluate("Distinct({1, 2, 3})") == [1, 2, 3]

    def test_distinct_all_same(self) -> None:
        assert evaluate("Distinct({1, 1, 1})") == [1]

    def test_distinct_empty(self) -> None:
        assert evaluate("Distinct({})") == []

    def test_distinct_strings(self) -> None:
        assert evaluate("Distinct({'a', 'b', 'a'})") == ["a", "b"]


class TestSortFunction:
    """Test Sort function - sorts list ascending."""

    def test_sort_integers(self) -> None:
        assert evaluate("Sort({3, 1, 4, 1, 5, 9})") == [1, 1, 3, 4, 5, 9]

    def test_sort_already_sorted(self) -> None:
        assert evaluate("Sort({1, 2, 3})") == [1, 2, 3]

    def test_sort_reverse_order(self) -> None:
        assert evaluate("Sort({3, 2, 1})") == [1, 2, 3]

    def test_sort_empty(self) -> None:
        assert evaluate("Sort({})") == []

    def test_sort_single(self) -> None:
        assert evaluate("Sort({42})") == [42]

    def test_sort_strings(self) -> None:
        assert evaluate("Sort({'c', 'a', 'b'})") == ["a", "b", "c"]


class TestIndexOfFunction:
    """Test IndexOf function - finds element index."""

    def test_indexof_found(self) -> None:
        assert evaluate("IndexOf({10, 20, 30}, 20)") == 1

    def test_indexof_first(self) -> None:
        assert evaluate("IndexOf({10, 20, 30}, 10)") == 0

    def test_indexof_last(self) -> None:
        assert evaluate("IndexOf({10, 20, 30}, 30)") == 2

    def test_indexof_not_found(self) -> None:
        assert evaluate("IndexOf({1, 2, 3}, 5)") == -1

    def test_indexof_empty(self) -> None:
        assert evaluate("IndexOf({}, 1)") == -1


class TestReverseFunction:
    """Test Reverse function - reverses list order."""

    def test_reverse_list(self) -> None:
        assert evaluate("Reverse({1, 2, 3})") == [3, 2, 1]

    def test_reverse_single(self) -> None:
        assert evaluate("Reverse({1})") == [1]

    def test_reverse_empty(self) -> None:
        assert evaluate("Reverse({})") == []

    def test_reverse_strings(self) -> None:
        assert evaluate("Reverse({'a', 'b', 'c'})") == ["c", "b", "a"]


class TestSliceFunction:
    """Test Slice function - extracts portion of list."""

    def test_slice_middle(self) -> None:
        assert evaluate("Slice({1, 2, 3, 4, 5}, 1, 3)") == [2, 3, 4]

    def test_slice_from_start(self) -> None:
        assert evaluate("Slice({1, 2, 3, 4, 5}, 0, 2)") == [1, 2]

    def test_slice_to_end(self) -> None:
        result = evaluate("Slice({1, 2, 3, 4, 5}, 3, 10)")
        assert result == [4, 5]


class TestCombineFunction:
    """Test Combine function - concatenates lists."""

    def test_combine_two_lists(self) -> None:
        assert evaluate("Combine({1, 2}, {3, 4})") == [1, 2, 3, 4]

    def test_combine_with_empty(self) -> None:
        assert evaluate("Combine({1, 2}, {})") == [1, 2]

    def test_combine_preserves_duplicates(self) -> None:
        assert evaluate("Combine({1, 2}, {2, 3})") == [1, 2, 2, 3]


# =============================================================================
# Phase 2: Aggregate Functions Tests
# =============================================================================


class TestAllTrueFunction:
    """Test AllTrue function - all elements true."""

    def test_alltrue_all_true(self) -> None:
        assert evaluate("AllTrue({true, true, true})") is True

    def test_alltrue_one_false(self) -> None:
        assert evaluate("AllTrue({true, false, true})") is False

    def test_alltrue_empty(self) -> None:
        assert evaluate("AllTrue({})") is True

    def test_alltrue_single_true(self) -> None:
        assert evaluate("AllTrue({true})") is True


class TestAnyTrueFunction:
    """Test AnyTrue function - any element true."""

    def test_anytrue_all_true(self) -> None:
        assert evaluate("AnyTrue({true, true, true})") is True

    def test_anytrue_one_true(self) -> None:
        assert evaluate("AnyTrue({false, true, false})") is True

    def test_anytrue_all_false(self) -> None:
        assert evaluate("AnyTrue({false, false, false})") is False

    def test_anytrue_empty(self) -> None:
        assert evaluate("AnyTrue({})") is False


class TestAllFalseFunction:
    """Test AllFalse function - all elements false."""

    def test_allfalse_all_false(self) -> None:
        assert evaluate("AllFalse({false, false, false})") is True

    def test_allfalse_one_true(self) -> None:
        assert evaluate("AllFalse({false, true, false})") is False

    def test_allfalse_empty(self) -> None:
        assert evaluate("AllFalse({})") is True


class TestAnyFalseFunction:
    """Test AnyFalse function - any element false."""

    def test_anyfalse_all_false(self) -> None:
        assert evaluate("AnyFalse({false, false, false})") is True

    def test_anyfalse_one_false(self) -> None:
        assert evaluate("AnyFalse({true, false, true})") is True

    def test_anyfalse_all_true(self) -> None:
        assert evaluate("AnyFalse({true, true, true})") is False

    def test_anyfalse_empty(self) -> None:
        assert evaluate("AnyFalse({})") is False


class TestMedianFunction:
    """Test Median function."""

    def test_median_odd_count(self) -> None:
        assert evaluate("Median({1, 3, 5, 7, 9})") == 5

    def test_median_even_count(self) -> None:
        result = evaluate("Median({1, 2, 3, 4})")
        assert result == Decimal("2.5")

    def test_median_single(self) -> None:
        assert evaluate("Median({5})") == 5

    def test_median_empty(self) -> None:
        assert evaluate("Median({})") is None

    def test_median_unsorted(self) -> None:
        assert evaluate("Median({9, 1, 5, 3, 7})") == 5


class TestModeFunction:
    """Test Mode function - most frequent value."""

    def test_mode_single_mode(self) -> None:
        assert evaluate("Mode({1, 2, 2, 3})") == 2

    def test_mode_all_same(self) -> None:
        assert evaluate("Mode({5, 5, 5})") == 5

    def test_mode_single_element(self) -> None:
        assert evaluate("Mode({42})") == 42

    def test_mode_empty(self) -> None:
        assert evaluate("Mode({})") is None


class TestProductFunction:
    """Test Product function - multiplies all elements."""

    def test_product_integers(self) -> None:
        result = evaluate("Product({2, 3, 4})")
        assert result == Decimal("24")

    def test_product_single(self) -> None:
        result = evaluate("Product({5})")
        assert result == Decimal("5")

    def test_product_with_one(self) -> None:
        result = evaluate("Product({1, 2, 3})")
        assert result == Decimal("6")

    def test_product_empty(self) -> None:
        assert evaluate("Product({})") is None


class TestVarianceFunction:
    """Test Variance function - sample variance."""

    def test_variance_basic(self) -> None:
        # Variance of {2, 4, 6} = ((2-4)^2 + (4-4)^2 + (6-4)^2) / 2 = 4
        result = evaluate("Variance({2, 4, 6})")
        assert result == 4.0

    def test_variance_single(self) -> None:
        # Need at least 2 elements for sample variance
        assert evaluate("Variance({5})") is None


class TestPopulationVarianceFunction:
    """Test PopulationVariance function."""

    def test_popvariance_basic(self) -> None:
        # Pop variance of {2, 4, 6} = ((2-4)^2 + (4-4)^2 + (6-4)^2) / 3 = 8/3
        result = evaluate("PopulationVariance({2, 4, 6})")
        assert abs(float(result) - (8 / 3)) < 0.0001


# =============================================================================
# Phase 2: Set Operations Tests
# =============================================================================


class TestUnionOperation:
    """Test union set operation."""

    def test_union_distinct_lists(self) -> None:
        assert evaluate("{1, 2} union {3, 4}") == [1, 2, 3, 4]

    def test_union_overlapping(self) -> None:
        result = evaluate("{1, 2, 3} union {2, 3, 4}")
        assert set(result) == {1, 2, 3, 4}

    def test_union_with_empty(self) -> None:
        assert evaluate("{1, 2} union {}") == [1, 2]

    def test_union_empty_with_list(self) -> None:
        assert evaluate("{} union {1, 2}") == [1, 2]

    def test_union_same_list(self) -> None:
        result = evaluate("{1, 2} union {1, 2}")
        assert set(result) == {1, 2}


class TestIntersectOperation:
    """Test intersect set operation."""

    def test_intersect_overlapping(self) -> None:
        assert evaluate("{1, 2, 3} intersect {2, 3, 4}") == [2, 3]

    def test_intersect_no_overlap(self) -> None:
        assert evaluate("{1, 2} intersect {3, 4}") == []

    def test_intersect_with_empty(self) -> None:
        assert evaluate("{1, 2} intersect {}") == []

    def test_intersect_same_list(self) -> None:
        assert evaluate("{1, 2, 3} intersect {1, 2, 3}") == [1, 2, 3]

    def test_intersect_subset(self) -> None:
        assert evaluate("{1, 2, 3} intersect {2}") == [2]


class TestExceptOperation:
    """Test except set operation."""

    def test_except_overlapping(self) -> None:
        assert evaluate("{1, 2, 3} except {2}") == [1, 3]

    def test_except_no_overlap(self) -> None:
        assert evaluate("{1, 2} except {3, 4}") == [1, 2]

    def test_except_all_removed(self) -> None:
        assert evaluate("{1, 2} except {1, 2, 3}") == []

    def test_except_with_empty(self) -> None:
        assert evaluate("{1, 2} except {}") == [1, 2]

    def test_except_empty_from(self) -> None:
        assert evaluate("{} except {1, 2}") == []


# =============================================================================
# Phase 2: Interval Operation Tests
# =============================================================================


class TestIntervalContainsExpression:
    """Test interval contains expression (CQL syntax)."""

    def test_interval_contains_point(self) -> None:
        assert evaluate("Interval[1, 10] contains 5") is True

    def test_interval_not_contains(self) -> None:
        assert evaluate("Interval[1, 10] contains 15") is False

    def test_interval_contains_boundary_closed(self) -> None:
        assert evaluate("Interval[1, 10] contains 1") is True
        assert evaluate("Interval[1, 10] contains 10") is True

    def test_interval_contains_boundary_open(self) -> None:
        assert evaluate("Interval(1, 10) contains 1") is False
        assert evaluate("Interval(1, 10) contains 10") is False


class TestPointInInterval:
    """Test point in interval operation."""

    def test_point_in_interval(self) -> None:
        assert evaluate("5 in Interval[1, 10]") is True

    def test_point_not_in_interval(self) -> None:
        assert evaluate("15 in Interval[1, 10]") is False

    def test_boundary_in_closed(self) -> None:
        assert evaluate("1 in Interval[1, 10]") is True

    def test_boundary_not_in_open(self) -> None:
        assert evaluate("1 in Interval(1, 10)") is False


class TestIntervalOverlaps:
    """Test interval overlaps operation."""

    def test_overlaps_true(self) -> None:
        interval1: CQLInterval[int] = CQLInterval(low=1, high=5)
        interval2: CQLInterval[int] = CQLInterval(low=3, high=7)
        assert interval1.overlaps(interval2) is True

    def test_overlaps_false(self) -> None:
        interval1: CQLInterval[int] = CQLInterval(low=1, high=3)
        interval2: CQLInterval[int] = CQLInterval(low=5, high=7)
        assert interval1.overlaps(interval2) is False

    def test_overlaps_adjacent_closed(self) -> None:
        interval1: CQLInterval[int] = CQLInterval(low=1, high=3)
        interval2: CQLInterval[int] = CQLInterval(low=3, high=5)
        assert interval1.overlaps(interval2) is True

    def test_overlaps_adjacent_open(self) -> None:
        interval1: CQLInterval[int] = CQLInterval(low=1, high=3, high_closed=False)
        interval2: CQLInterval[int] = CQLInterval(low=3, high=5, low_closed=False)
        assert interval1.overlaps(interval2) is False


class TestIntervalIncludes:
    """Test interval includes operation."""

    def test_includes_subset(self) -> None:
        outer: CQLInterval[int] = CQLInterval(low=1, high=10)
        inner: CQLInterval[int] = CQLInterval(low=3, high=7)
        assert outer.includes(inner) is True

    def test_not_includes(self) -> None:
        outer: CQLInterval[int] = CQLInterval(low=1, high=5)
        inner: CQLInterval[int] = CQLInterval(low=3, high=7)
        assert outer.includes(inner) is False

    def test_includes_same(self) -> None:
        interval: CQLInterval[int] = CQLInterval(low=1, high=10)
        same: CQLInterval[int] = CQLInterval(low=1, high=10)
        assert interval.includes(same) is True


class TestIntervalMeets:
    """Test interval meets operation."""

    def test_meets_true(self) -> None:
        interval1: CQLInterval[int] = CQLInterval(low=1, high=3, high_closed=True)
        interval2: CQLInterval[int] = CQLInterval(low=3, high=5, low_closed=False)
        assert interval1.meets(interval2) is True

    def test_meets_false_overlap(self) -> None:
        interval1: CQLInterval[int] = CQLInterval(low=1, high=3)
        interval2: CQLInterval[int] = CQLInterval(low=3, high=5)
        assert interval1.meets(interval2) is False  # Both include 3

    def test_meets_false_gap(self) -> None:
        interval1: CQLInterval[int] = CQLInterval(low=1, high=3)
        interval2: CQLInterval[int] = CQLInterval(low=5, high=7)
        assert interval1.meets(interval2) is False


# =============================================================================
# Phase 2: Query Expression Tests
# =============================================================================


class TestQueryFromReturn:
    """Test basic query from...return expressions."""

    def test_simple_query_return(self) -> None:
        lib = compile_library("""
            library Test
            define Numbers: {1, 2, 3, 4, 5}
            define Doubled: from Numbers N return N * 2
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("Doubled")
        assert result == [2, 4, 6, 8, 10]

    def test_query_with_strings(self) -> None:
        lib = compile_library("""
            library Test
            define Names: {'alice', 'bob', 'charlie'}
            define Greetings: from Names N return 'Hello ' & N
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("Greetings")
        assert "Hello alice" in result

    def test_query_identity(self) -> None:
        lib = compile_library("""
            library Test
            define Numbers: {1, 2, 3}
            define Same: from Numbers N return N
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("Same")
        assert result == [1, 2, 3]


class TestQueryWhere:
    """Test query where clause."""

    def test_query_where_filter(self) -> None:
        lib = compile_library("""
            library Test
            define Numbers: {1, 2, 3, 4, 5, 6}
            define Even: from Numbers N where N mod 2 = 0 return N
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("Even")
        assert result == [2, 4, 6]

    def test_query_where_greater_than(self) -> None:
        lib = compile_library("""
            library Test
            define Numbers: {1, 2, 3, 4, 5}
            define Large: from Numbers N where N > 3 return N
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("Large")
        assert result == [4, 5]

    def test_query_where_all_filtered(self) -> None:
        lib = compile_library("""
            library Test
            define Numbers: {1, 2, 3}
            define None: from Numbers N where N > 10 return N
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("None")
        assert result == []


class TestQueryLet:
    """Test query let clause."""

    def test_query_let_binding(self) -> None:
        lib = compile_library("""
            library Test
            define Numbers: {1, 2, 3}
            define WithSquares: from Numbers N
                let Squared: N * N
                return Squared
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("WithSquares")
        assert result == [1, 4, 9]

    def test_query_let_multiple(self) -> None:
        lib = compile_library("""
            library Test
            define Numbers: {2, 3, 4}
            define Computed: from Numbers N
                let Doubled: N * 2, Tripled: N * 3
                return Doubled + Tripled
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("Computed")
        assert result == [10, 15, 20]  # (2*2+2*3), (3*2+3*3), (4*2+4*3)


class TestQuerySort:
    """Test query sort clause."""

    def test_query_sort_asc(self) -> None:
        lib = compile_library("""
            library Test
            define Numbers: {3, 1, 4, 1, 5}
            define Sorted: from Numbers N return N sort asc
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("Sorted")
        assert result == [1, 1, 3, 4, 5]

    def test_query_sort_desc(self) -> None:
        lib = compile_library("""
            library Test
            define Numbers: {3, 1, 4, 1, 5}
            define Sorted: from Numbers N return N sort desc
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("Sorted")
        assert result == [5, 4, 3, 1, 1]


# =============================================================================
# Phase 2: Function Chaining Tests
# =============================================================================


class TestListFunctionChaining:
    """Test chaining list functions."""

    def test_first_of_tail(self) -> None:
        assert evaluate("First(Tail({1, 2, 3, 4}))") == 2

    def test_last_of_take(self) -> None:
        assert evaluate("Last(Take({1, 2, 3, 4, 5}, 3))") == 3

    def test_count_of_distinct(self) -> None:
        assert evaluate("Count(Distinct({1, 2, 2, 3, 3, 3}))") == 3

    def test_sum_of_take(self) -> None:
        assert evaluate("Sum(Take({1, 2, 3, 4, 5}, 3))") == 6

    def test_flatten_then_distinct(self) -> None:
        result = evaluate("Distinct(Flatten({{1, 2}, {2, 3}}))")
        assert set(result) == {1, 2, 3}

    def test_sort_then_take(self) -> None:
        assert evaluate("Take(Sort({5, 3, 8, 1, 9}), 3)") == [1, 3, 5]

    def test_reverse_of_sort(self) -> None:
        assert evaluate("Reverse(Sort({3, 1, 2}))") == [3, 2, 1]


class TestAggregatesOnComputedLists:
    """Test aggregate functions on computed lists."""

    def test_sum_of_list_literal(self) -> None:
        assert evaluate("Sum({1, 2, 3, 4, 5})") == 15

    def test_avg_of_list_literal(self) -> None:
        assert evaluate("Avg({2, 4, 6, 8, 10})") == 6.0

    def test_min_of_expressions(self) -> None:
        assert evaluate("Min({1 + 1, 2 + 2, 3 + 3})") == 2

    def test_max_of_expressions(self) -> None:
        assert evaluate("Max({1 * 1, 2 * 2, 3 * 3})") == 9

    def test_count_of_filtered(self) -> None:
        # Using Distinct as a filter
        assert evaluate("Count(Distinct({1, 1, 2, 2, 3}))") == 3


# =============================================================================
# Phase 3: Date/Time Functions
# =============================================================================


class TestDateTimeConstructors:
    """Test date/time constructor functions."""

    def test_today_returns_date(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDate

        result = evaluate("Today()")
        assert isinstance(result, FHIRDate)

    def test_now_returns_datetime(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDateTime

        result = evaluate("Now()")
        assert isinstance(result, FHIRDateTime)

    def test_timeofday_returns_time(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRTime

        result = evaluate("TimeOfDay()")
        assert isinstance(result, FHIRTime)

    def test_date_constructor_full(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDate

        result = evaluate("Date(2024, 3, 15)")
        assert isinstance(result, FHIRDate)
        assert result.year == 2024
        assert result.month == 3
        assert result.day == 15

    def test_date_constructor_year_only(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDate

        result = evaluate("Date(2024)")
        assert isinstance(result, FHIRDate)
        assert result.year == 2024

    def test_datetime_constructor_full(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDateTime

        result = evaluate("DateTime(2024, 6, 15, 14, 30, 45)")
        assert isinstance(result, FHIRDateTime)
        assert result.year == 2024
        assert result.month == 6
        assert result.day == 15
        assert result.hour == 14
        assert result.minute == 30
        assert result.second == 45

    def test_datetime_constructor_date_only(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDateTime

        result = evaluate("DateTime(2024, 12, 25)")
        assert isinstance(result, FHIRDateTime)
        assert result.year == 2024
        assert result.month == 12
        assert result.day == 25

    def test_time_constructor(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRTime

        result = evaluate("Time(14, 30, 0)")
        assert isinstance(result, FHIRTime)
        assert result.hour == 14
        assert result.minute == 30
        assert result.second == 0


class TestDateComponentExtraction:
    """Test date/time component extraction functions."""

    def test_year_from_date(self) -> None:
        assert evaluate("year from @2024-03-15") == 2024

    def test_month_from_date(self) -> None:
        assert evaluate("month from @2024-03-15") == 3

    def test_day_from_date(self) -> None:
        assert evaluate("day from @2024-03-15") == 15

    def test_year_from_datetime(self) -> None:
        assert evaluate("year from @2024-06-20T10:30:00") == 2024

    def test_month_from_datetime(self) -> None:
        assert evaluate("month from @2024-06-20T10:30:00") == 6

    def test_day_from_datetime(self) -> None:
        assert evaluate("day from @2024-06-20T10:30:00") == 20

    def test_hour_from_datetime(self) -> None:
        assert evaluate("hour from @2024-06-20T10:30:00") == 10

    def test_minute_from_datetime(self) -> None:
        assert evaluate("minute from @2024-06-20T10:30:45") == 30

    def test_second_from_datetime(self) -> None:
        assert evaluate("second from @2024-06-20T10:30:45") == 45

    def test_year_function(self) -> None:
        assert evaluate("Year(@2024-03-15)") == 2024

    def test_month_function(self) -> None:
        assert evaluate("Month(@2024-03-15)") == 3

    def test_day_function(self) -> None:
        assert evaluate("Day(@2024-03-15)") == 15

    def test_hour_function(self) -> None:
        assert evaluate("Hour(@2024-06-20T14:30:00)") == 14

    def test_minute_function(self) -> None:
        assert evaluate("Minute(@2024-06-20T14:30:00)") == 30

    def test_second_function(self) -> None:
        assert evaluate("Second(@2024-06-20T14:30:45)") == 45


class TestIntervalFunctions:
    """Test interval accessor functions."""

    def test_start_of_integer_interval(self) -> None:
        assert evaluate("start of Interval[1, 10]") == 1

    def test_end_of_integer_interval(self) -> None:
        assert evaluate("end of Interval[1, 10]") == 10

    def test_start_of_date_interval(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDate

        result = evaluate("start of Interval[@2024-01-01, @2024-12-31]")
        assert isinstance(result, FHIRDate)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 1

    def test_end_of_date_interval(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDate

        result = evaluate("end of Interval[@2024-01-01, @2024-12-31]")
        assert isinstance(result, FHIRDate)
        assert result.year == 2024
        assert result.month == 12
        assert result.day == 31

    def test_width_of_integer_interval(self) -> None:
        assert evaluate("width of Interval[1, 10]") == 9

    def test_width_of_integer_interval_closed(self) -> None:
        assert evaluate("width of Interval[5, 15]") == 10

    def test_start_of_null_is_null(self) -> None:
        assert evaluate("start of null") is None

    def test_end_of_null_is_null(self) -> None:
        assert evaluate("end of null") is None

    def test_width_of_null_is_null(self) -> None:
        assert evaluate("width of null") is None


class TestDurationBetween:
    """Test duration between expressions."""

    def test_years_between_dates(self) -> None:
        assert evaluate("years between @1990-01-01 and @2024-01-01") == 34

    def test_months_between_dates(self) -> None:
        assert evaluate("months between @2024-01-15 and @2024-06-15") == 5

    def test_days_between_dates(self) -> None:
        assert evaluate("days between @2024-01-01 and @2024-01-31") == 30

    def test_weeks_between_dates(self) -> None:
        assert evaluate("weeks between @2024-01-01 and @2024-01-15") == 2

    def test_years_between_with_partial_year(self) -> None:
        # Birthday hasn't occurred yet
        assert evaluate("years between @1990-06-15 and @2024-01-01") == 33

    def test_months_between_negative(self) -> None:
        # When end is before start
        result = evaluate("months between @2024-06-15 and @2024-01-15")
        assert result == -5

    def test_days_between_same_date(self) -> None:
        assert evaluate("days between @2024-05-15 and @2024-05-15") == 0

    def test_duration_between_null_start(self) -> None:
        assert evaluate("days between null and @2024-01-01") is None

    def test_duration_between_null_end(self) -> None:
        assert evaluate("days between @2024-01-01 and null") is None


class TestDateArithmetic:
    """Test date arithmetic with durations."""

    def test_date_plus_years(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDate

        result = evaluate("@2024-01-01 + 1 year")
        assert isinstance(result, FHIRDate)
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 1

    def test_date_plus_months(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDate

        result = evaluate("@2024-01-15 + 3 months")
        assert isinstance(result, FHIRDate)
        assert result.month == 4

    def test_date_plus_days(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDate

        result = evaluate("@2024-01-01 + 30 days")
        assert isinstance(result, FHIRDate)
        assert result.month == 1
        assert result.day == 31

    def test_date_plus_weeks(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDate

        result = evaluate("@2024-01-01 + 2 weeks")
        assert isinstance(result, FHIRDate)
        assert result.day == 15

    def test_date_minus_years(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDate

        result = evaluate("@2024-01-01 - 5 years")
        assert isinstance(result, FHIRDate)
        assert result.year == 2019

    def test_date_minus_months(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDate

        result = evaluate("@2024-06-15 - 3 months")
        assert isinstance(result, FHIRDate)
        assert result.month == 3

    def test_date_minus_days(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDate

        result = evaluate("@2024-01-31 - 15 days")
        assert isinstance(result, FHIRDate)
        assert result.day == 16

    def test_datetime_plus_hours(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDateTime

        result = evaluate("@2024-01-01T10:00:00 + 5 hours")
        assert isinstance(result, FHIRDateTime)
        assert result.hour == 15

    def test_datetime_plus_minutes(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDateTime

        result = evaluate("@2024-01-01T10:30:00 + 45 minutes")
        assert isinstance(result, FHIRDateTime)
        assert result.hour == 11
        assert result.minute == 15

    def test_datetime_minus_hours(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDateTime

        result = evaluate("@2024-01-01T10:00:00 - 3 hours")
        assert isinstance(result, FHIRDateTime)
        assert result.hour == 7

    def test_date_difference_in_days(self) -> None:
        result = evaluate("@2024-01-31 - @2024-01-01")
        assert result == 30


class TestCollapseAndExpand:
    """Test collapse and expand interval functions."""

    def test_collapse_non_overlapping(self) -> None:
        result = evaluate("collapse { Interval[1, 3], Interval[5, 7] }")
        assert len(result) == 2

    def test_collapse_overlapping(self) -> None:
        result = evaluate("collapse { Interval[1, 5], Interval[3, 7] }")
        assert len(result) == 1
        assert result[0].low == 1
        assert result[0].high == 7

    def test_collapse_adjacent(self) -> None:
        result = evaluate("collapse { Interval[1, 3], Interval[3, 5] }")
        assert len(result) == 1
        assert result[0].low == 1
        assert result[0].high == 5

    def test_collapse_empty_list(self) -> None:
        result = evaluate("collapse { }")
        assert result == []

    def test_expand_integer_interval(self) -> None:
        result = evaluate("expand Interval[1, 5]")
        assert result == [1, 2, 3, 4, 5]

    def test_expand_integer_interval_open(self) -> None:
        result = evaluate("expand Interval(1, 5)")
        assert result == [2, 3, 4]

    def test_expand_small_interval(self) -> None:
        result = evaluate("expand Interval[3, 3]")
        assert result == [3]


class TestClinicalAgeFunctions:
    """Test clinical age calculation functions."""

    def test_calculate_age_in_years(self) -> None:
        result = evaluate("CalculateAgeInYears(@1990-01-15, @2024-06-01)")
        assert result == 34

    def test_calculate_age_in_months(self) -> None:
        result = evaluate("CalculateAgeInMonths(@2023-01-15, @2024-06-01)")
        assert result == 16

    def test_calculate_age_in_weeks(self) -> None:
        result = evaluate("CalculateAgeInWeeks(@2024-01-01, @2024-01-22)")
        assert result == 3

    def test_calculate_age_in_days(self) -> None:
        result = evaluate("CalculateAgeInDays(@2024-01-01, @2024-01-11)")
        assert result == 10

    def test_calculate_age_before_birthday(self) -> None:
        # Birthday is June 15, checking on January 1
        result = evaluate("CalculateAgeInYears(@1990-06-15, @2024-01-01)")
        assert result == 33

    def test_calculate_age_on_birthday(self) -> None:
        result = evaluate("CalculateAgeInYears(@1990-06-15, @2024-06-15)")
        assert result == 34

    def test_calculate_age_after_birthday(self) -> None:
        result = evaluate("CalculateAgeInYears(@1990-06-15, @2024-12-01)")
        assert result == 34

    def test_calculate_age_null_birthdate(self) -> None:
        result = evaluate("CalculateAgeInYears(null, @2024-01-01)")
        assert result is None

    def test_calculate_age_null_asof(self) -> None:
        result = evaluate("CalculateAgeInYears(@1990-01-01, null)")
        assert result is None


class TestIntervalOperations:
    """Test advanced interval operations."""

    def test_interval_contains_point(self) -> None:
        assert evaluate("Interval[1, 10] contains 5") is True

    def test_interval_not_contains_point(self) -> None:
        assert evaluate("Interval[1, 10] contains 15") is False

    def test_point_in_interval(self) -> None:
        assert evaluate("5 in Interval[1, 10]") is True

    def test_point_not_in_interval(self) -> None:
        assert evaluate("15 in Interval[1, 10]") is False

    def test_interval_overlaps(self) -> None:
        assert evaluate("Interval[1, 5] overlaps Interval[3, 7]") is True

    def test_interval_not_overlaps(self) -> None:
        assert evaluate("Interval[1, 3] overlaps Interval[5, 7]") is False

    def test_interval_meets(self) -> None:
        # [1, 3] meets [4, 6] because successor(3) = 4 (they are adjacent)
        assert evaluate("Interval[1, 3] meets Interval[4, 6]") is True

    def test_interval_not_meets_overlap(self) -> None:
        # [1, 3] does NOT meet [3, 5] - they share endpoint 3, so they overlap
        assert evaluate("Interval[1, 3] meets Interval[3, 5]") is False

    def test_interval_not_meets_gap(self) -> None:
        # [1, 3] does NOT meet [5, 7] - there's a gap (4 is not covered)
        assert evaluate("Interval[1, 3] meets Interval[5, 7]") is False

    def test_interval_before(self) -> None:
        assert evaluate("Interval[1, 3] before Interval[5, 7]") is True

    def test_interval_after(self) -> None:
        assert evaluate("Interval[5, 7] after Interval[1, 3]") is True

    def test_date_interval_contains(self) -> None:
        assert evaluate("Interval[@2024-01-01, @2024-12-31] contains @2024-06-15") is True

    def test_date_interval_not_contains(self) -> None:
        assert evaluate("Interval[@2024-01-01, @2024-06-30] contains @2024-12-15") is False


class TestTimingExpressions:
    """Test timing expressions (before, after, during)."""

    def test_date_before_date(self) -> None:
        assert evaluate("@2024-01-01 before @2024-06-01") is True

    def test_date_not_before_date(self) -> None:
        assert evaluate("@2024-06-01 before @2024-01-01") is False

    def test_date_after_date(self) -> None:
        assert evaluate("@2024-06-01 after @2024-01-01") is True

    def test_date_not_after_date(self) -> None:
        assert evaluate("@2024-01-01 after @2024-06-01") is False

    def test_date_during_interval(self) -> None:
        assert evaluate("@2024-06-15 during Interval[@2024-01-01, @2024-12-31]") is True

    def test_date_not_during_interval(self) -> None:
        assert evaluate("@2023-06-15 during Interval[@2024-01-01, @2024-12-31]") is False


class TestLibraryWithDateFunctions:
    """Test date functions in library context."""

    def test_library_with_date_calculation(self) -> None:
        lib = compile_library("""
            library DateTest
            define BirthDate: @1990-06-15
            define ReferenceDate: @2024-01-01
            define AgeCalculation: years between BirthDate and ReferenceDate
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("AgeCalculation")
        assert result == 33

    def test_library_with_date_arithmetic(self) -> None:
        lib = compile_library("""
            library DateArithTest
            define StartDate: @2024-01-01
            define EndDate: StartDate + 6 months
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("EndDate")
        assert result.month == 7

    def test_library_with_interval_operations(self) -> None:
        lib = compile_library("""
            library IntervalTest
            define Period: Interval[@2024-01-01, @2024-12-31]
            define MidYear: @2024-06-15
            define IsInPeriod: MidYear in Period
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("IsInPeriod")
        assert result is True

    def test_library_with_component_extraction(self) -> None:
        lib = compile_library("""
            library ComponentTest
            define TestDate: @2024-03-15
            define ExtractedYear: year from TestDate
            define ExtractedMonth: month from TestDate
            define ExtractedDay: day from TestDate
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        assert evaluator.evaluate_definition("ExtractedYear") == 2024
        assert evaluator.evaluate_definition("ExtractedMonth") == 3
        assert evaluator.evaluate_definition("ExtractedDay") == 15


class TestEdgeCases:
    """Test edge cases for date/time operations."""

    def test_leap_year_feb_29_plus_year(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDate

        result = evaluate("@2024-02-29 + 1 year")
        assert isinstance(result, FHIRDate)
        # Feb 29 + 1 year = Feb 28 (non-leap year)
        assert result.year == 2025
        assert result.month == 2
        assert result.day == 28

    def test_month_end_plus_month(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDate

        result = evaluate("@2024-01-31 + 1 month")
        assert isinstance(result, FHIRDate)
        # Jan 31 + 1 month = Feb 29 (leap year 2024)
        assert result.month == 2

    def test_year_boundary_crossing(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDate

        result = evaluate("@2024-12-15 + 1 month")
        assert isinstance(result, FHIRDate)
        assert result.year == 2025
        assert result.month == 1

    def test_midnight_boundary(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDateTime

        result = evaluate("@2024-01-01T23:00:00 + 2 hours")
        assert isinstance(result, FHIRDateTime)
        assert result.day == 2
        assert result.hour == 1

    def test_negative_duration(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDate

        result = evaluate("@2024-01-01 - 1 year")
        assert isinstance(result, FHIRDate)
        assert result.year == 2023

    def test_large_duration(self) -> None:
        result = evaluate("days between @2000-01-01 and @2024-12-31")
        assert result > 9000  # About 25 years worth of days


# =============================================================================
# Phase 4: String Function Tests
# =============================================================================


class TestStringConcat:
    """Test string concatenation functions."""

    def test_concat_two_strings(self) -> None:
        assert evaluate("Concat('Hello', ' World')") == "Hello World"

    def test_concat_multiple(self) -> None:
        assert evaluate("Concat('a', 'b', 'c')") == "abc"

    def test_concat_with_null(self) -> None:
        # CQL spec: Concat returns null if any argument is null
        assert evaluate("Concat('Hello', null)") is None

    def test_concat_empty(self) -> None:
        assert evaluate("Concat('', 'test')") == "test"


class TestStringCombine:
    """Test combine function."""

    def test_combine_list(self) -> None:
        lib = compile_library("""
            library CombineTest
            define Items: {'a', 'b', 'c'}
            define Result: Combine(Items, ', ')
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("Result")
        assert result == "a, b, c"

    def test_combine_no_separator(self) -> None:
        lib = compile_library("""
            library CombineTest
            define Items: {'x', 'y', 'z'}
            define Result: Combine(Items)
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("Result")
        assert result == "xyz"

    def test_combine_with_space(self) -> None:
        lib = compile_library("""
            library CombineTest
            define Words: {'Hello', 'World'}
            define Result: Combine(Words, ' ')
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("Result")
        assert result == "Hello World"


class TestStringSplit:
    """Test split function."""

    def test_split_comma(self) -> None:
        assert evaluate("Split('a,b,c', ',')") == ["a", "b", "c"]

    def test_split_space(self) -> None:
        assert evaluate("Split('Hello World', ' ')") == ["Hello", "World"]


class TestStringCase:
    """Test case conversion functions."""

    def test_upper(self) -> None:
        assert evaluate("Upper('hello')") == "HELLO"

    def test_lower(self) -> None:
        assert evaluate("Lower('HELLO')") == "hello"

    def test_upper_mixed(self) -> None:
        assert evaluate("Upper('HeLLo WoRLd')") == "HELLO WORLD"


class TestStringSubstring:
    """Test substring function."""

    def test_substring_from_start(self) -> None:
        assert evaluate("Substring('Hello World', 0, 5)") == "Hello"

    def test_substring_from_middle(self) -> None:
        assert evaluate("Substring('Hello World', 6, 5)") == "World"

    def test_substring_to_end(self) -> None:
        assert evaluate("Substring('Hello World', 6)") == "World"


class TestStringStartsEndsWith:
    """Test StartsWith and EndsWith functions."""

    def test_startswith_true(self) -> None:
        assert evaluate("StartsWith('Hello World', 'Hello')") is True

    def test_startswith_false(self) -> None:
        assert evaluate("StartsWith('Hello World', 'World')") is False

    def test_endswith_true(self) -> None:
        assert evaluate("EndsWith('Hello World', 'World')") is True

    def test_endswith_false(self) -> None:
        assert evaluate("EndsWith('Hello World', 'Hello')") is False


class TestStringMatches:
    """Test regex matching functions.

    CQL spec: Matches checks if the ENTIRE string matches the pattern (fullmatch).
    """

    def test_matches_simple(self) -> None:
        # Must match entire string - '123' matches [0-9]+
        assert evaluate("Matches('123', '[0-9]+')") is True

    def test_matches_partial_fails(self) -> None:
        # 'test123' does NOT fully match [0-9]+
        assert evaluate("Matches('test123', '[0-9]+')") is False

    def test_matches_no_match(self) -> None:
        assert evaluate("Matches('test', '[0-9]+')") is False

    def test_matches_full_pattern(self) -> None:
        # Pattern that matches the entire string
        assert evaluate("Matches('user@example.com', '.*@.*\\\\..*')") is True


class TestStringReplace:
    """Test replace functions."""

    def test_replace_simple(self) -> None:
        assert evaluate("Replace('Hello World', 'World', 'CQL')") == "Hello CQL"

    def test_replace_multiple(self) -> None:
        assert evaluate("Replace('aaa', 'a', 'b')") == "bbb"

    def test_replacematches_regex(self) -> None:
        assert evaluate("ReplaceMatches('test123', '[0-9]+', 'XXX')") == "testXXX"


class TestStringPosition:
    """Test position/index functions."""

    def test_indexof_found(self) -> None:
        assert evaluate("IndexOf('Hello World', 'World')") == 6

    def test_indexof_not_found(self) -> None:
        assert evaluate("IndexOf('Hello World', 'xyz')") == -1

    def test_positionof_found(self) -> None:
        assert evaluate("PositionOf('o', 'Hello')") == 4


class TestStringTrim:
    """Test trim function."""

    def test_trim_spaces(self) -> None:
        assert evaluate("Trim('  hello  ')") == "hello"

    def test_trim_no_change(self) -> None:
        assert evaluate("Trim('hello')") == "hello"


class TestStringLength:
    """Test length function."""

    def test_length_string(self) -> None:
        assert evaluate("Length('Hello')") == 5

    def test_length_empty(self) -> None:
        assert evaluate("Length('')") == 0


# =============================================================================
# Phase 4: Type Conversion Tests
# =============================================================================


class TestTypeConversion:
    """Test type conversion functions."""

    def test_tostring_integer(self) -> None:
        assert evaluate("ToString(42)") == "42"

    def test_tostring_boolean(self) -> None:
        # CQL spec requires lowercase 'true'/'false'
        assert evaluate("ToString(true)") == "true"

    def test_tointeger_string(self) -> None:
        assert evaluate("ToInteger('42')") == 42

    def test_tointeger_decimal(self) -> None:
        assert evaluate("ToInteger(3.14)") == 3

    def test_todecimal_string(self) -> None:
        from decimal import Decimal

        result = evaluate("ToDecimal('3.14')")
        assert result == Decimal("3.14")

    def test_toboolean_true_string(self) -> None:
        assert evaluate("ToBoolean('true')") is True

    def test_toboolean_false_string(self) -> None:
        assert evaluate("ToBoolean('false')") is False

    def test_toboolean_yes(self) -> None:
        assert evaluate("ToBoolean('yes')") is True


class TestDateConversion:
    """Test date conversion functions."""

    def test_todate_string(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDate

        result = evaluate("ToDate('2024-03-15')")
        assert isinstance(result, FHIRDate)
        assert result.year == 2024
        assert result.month == 3
        assert result.day == 15

    def test_todatetime_string(self) -> None:
        from dhis2w_fhir_engine.engine.types import FHIRDateTime

        result = evaluate("ToDateTime('2024-03-15T10:30:00')")
        assert isinstance(result, FHIRDateTime)
        assert result.hour == 10


# =============================================================================
# Phase 4: Utility Function Tests
# =============================================================================


class TestCoalesce:
    """Test coalesce function."""

    def test_coalesce_first_not_null(self) -> None:
        assert evaluate("Coalesce('a', 'b', 'c')") == "a"

    def test_coalesce_first_null(self) -> None:
        assert evaluate("Coalesce(null, 'b', 'c')") == "b"

    def test_coalesce_all_null(self) -> None:
        assert evaluate("Coalesce(null, null)") is None

    def test_coalesce_number(self) -> None:
        assert evaluate("Coalesce(null, 42)") == 42


class TestNullChecks:
    """Test null check functions."""

    def test_isnull_true(self) -> None:
        assert evaluate("IsNull(null)") is True

    def test_isnull_false(self) -> None:
        assert evaluate("IsNull('test')") is False

    def test_isnotnull_true(self) -> None:
        assert evaluate("IsNotNull('test')") is True

    def test_isnotnull_false(self) -> None:
        assert evaluate("IsNotNull(null)") is False


class TestBooleanChecks:
    """Test boolean check functions."""

    def test_istrue_true(self) -> None:
        assert evaluate("IsTrue(true)") is True

    def test_istrue_false(self) -> None:
        assert evaluate("IsTrue(false)") is False

    def test_isfalse_true(self) -> None:
        assert evaluate("IsFalse(false)") is True

    def test_isfalse_false(self) -> None:
        assert evaluate("IsFalse(true)") is False


# =============================================================================
# Phase 4: Math Function Tests
# =============================================================================


class TestMathFunctions:
    """Test mathematical functions."""

    def test_abs_positive(self) -> None:
        assert evaluate("Abs(5)") == 5

    def test_abs_negative(self) -> None:
        assert evaluate("Abs(-5)") == 5

    def test_ceiling(self) -> None:
        assert evaluate("Ceiling(3.2)") == 4

    def test_floor(self) -> None:
        assert evaluate("Floor(3.8)") == 3

    def test_truncate(self) -> None:
        assert evaluate("Truncate(3.9)") == 3

    def test_round_default(self) -> None:
        assert evaluate("Round(3.5)") == 4

    def test_round_precision(self) -> None:
        from decimal import Decimal

        assert evaluate("Round(3.14159, 2)") == Decimal("3.14")

    def test_sqrt(self) -> None:
        assert evaluate("Sqrt(16)") == 4.0

    def test_power(self) -> None:
        assert evaluate("Power(2, 3)") == 8.0

    def test_ln(self) -> None:
        result = evaluate("Ln(2.71828183)")  # Max 8 decimal places per CQL spec
        assert abs(result - 1.0) < 0.001

    def test_exp(self) -> None:
        import math

        result = evaluate("Exp(1)")
        assert abs(result - math.e) < 0.001


# =============================================================================
# Phase 4: User-Defined Function Tests
# =============================================================================


class TestUserDefinedFunctions:
    """Test user-defined function support."""

    def test_simple_function(self) -> None:
        lib = compile_library("""
            library FunctionTest
            define function Double(x Integer): x * 2
            define Result: Double(5)
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("Result")
        assert result == 10

    def test_function_two_params(self) -> None:
        lib = compile_library("""
            library FunctionTest
            define function Add(a Integer, b Integer): a + b
            define Result: Add(3, 4)
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("Result")
        assert result == 7

    def test_function_string_param(self) -> None:
        lib = compile_library("""
            library FunctionTest
            define function Greet(name String): Concat('Hello, ', name)
            define Result: Greet('World')
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("Result")
        assert result == "Hello, World"

    def test_function_with_expression(self) -> None:
        lib = compile_library("""
            library FunctionTest
            define function IsAdult(age Integer): age >= 18
            define Result: IsAdult(21)
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("Result")
        assert result is True

    def test_recursive_function(self) -> None:
        lib = compile_library("""
            library FunctionTest
            define function Factorial(n Integer):
                if n <= 1 then 1 else n * Factorial(n - 1)
            define Result: Factorial(5)
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("Result")
        assert result == 120


# =============================================================================
# Phase 4: Library Integration Tests
# =============================================================================


class TestLibraryWithPhase4Functions:
    """Test Phase 4 functions in library context."""

    def test_library_with_string_functions(self) -> None:
        lib = compile_library("""
            library StringTest
            define Name: 'john doe'
            define Formatted: Concat(Upper(Substring(Name, 0, 1)), Substring(Name, 1))
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("Formatted")
        assert result == "John doe"

    def test_library_with_math_functions(self) -> None:
        lib = compile_library("""
            library MathTest
            define Value: 3.7
            define Rounded: Round(Value)
            define Floored: Floor(Value)
            define Ceiled: Ceiling(Value)
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        assert evaluator.evaluate_definition("Rounded") == 4
        assert evaluator.evaluate_definition("Floored") == 3
        assert evaluator.evaluate_definition("Ceiled") == 4

    def test_library_with_coalesce(self) -> None:
        lib = compile_library("""
            library CoalesceTest
            define MaybeNull: null
            define Default: 'default value'
            define Result: Coalesce(MaybeNull, Default)
        """)
        evaluator = CQLEvaluator()
        evaluator._current_library = lib
        result = evaluator.evaluate_definition("Result")
        assert result == "default value"


# =============================================================================
# Phase 8: Missing Expression Terms Tests
# =============================================================================


class TestAggregateExpressionTerm:
    """Test distinct and flatten as expression terms (not function calls)."""

    def test_distinct_expression(self) -> None:
        """Test distinct as expression term."""
        result = evaluate("distinct {1, 2, 2, 3, 3, 3}")
        assert result == [1, 2, 3]

    def test_distinct_expression_strings(self) -> None:
        """Test distinct with strings."""
        result = evaluate("distinct {'a', 'b', 'b', 'c'}")
        assert result == ["a", "b", "c"]

    def test_distinct_expression_empty(self) -> None:
        """Test distinct on empty list."""
        result = evaluate("distinct {}")
        assert result == []

    def test_flatten_expression(self) -> None:
        """Test flatten as expression term."""
        result = evaluate("flatten {{1, 2}, {3, 4}}")
        assert result == [1, 2, 3, 4]

    def test_flatten_expression_nested(self) -> None:
        """Test flatten with nested lists."""
        result = evaluate("flatten {{1}, {2, 3}, {4, 5, 6}}")
        assert result == [1, 2, 3, 4, 5, 6]

    def test_flatten_expression_mixed(self) -> None:
        """Test flatten with mixed elements."""
        result = evaluate("flatten {{1, 2}, 3, {4, 5}}")
        assert result == [1, 2, 3, 4, 5]


class TestSingletonFromExpression:
    """Test singleton from expression term."""

    def test_singleton_from_single_element(self) -> None:
        """Test singleton from with single element."""
        result = evaluate("singleton from {42}")
        assert result == 42

    def test_singleton_from_empty(self) -> None:
        """Test singleton from empty list returns null."""
        result = evaluate("singleton from {}")
        assert result is None

    def test_singleton_from_multiple_elements_error(self) -> None:
        """Test singleton from multiple elements raises error."""
        with pytest.raises(CQLError):
            evaluate("singleton from {1, 2, 3}")


class TestPointFromExpression:
    """Test point from expression term."""

    def test_point_from_unit_interval(self) -> None:
        """Test point from unit interval."""
        result = evaluate("point from Interval[5, 5]")
        assert result == 5

    def test_point_from_non_unit_interval_error(self) -> None:
        """Test point from non-unit interval raises error."""
        with pytest.raises(CQLError):
            evaluate("point from Interval[1, 10]")


class TestSuccessorPredecessorExpression:
    """Test successor of and predecessor of expressions."""

    def test_successor_of_integer(self) -> None:
        """Test successor of integer."""
        assert evaluate("successor of 5") == 6
        assert evaluate("successor of 0") == 1
        assert evaluate("successor of -1") == 0

    def test_predecessor_of_integer(self) -> None:
        """Test predecessor of integer."""
        assert evaluate("predecessor of 5") == 4
        assert evaluate("predecessor of 1") == 0
        assert evaluate("predecessor of 0") == -1

    def test_successor_of_decimal(self) -> None:
        """Test successor of decimal - CQL uses 8 decimal places precision."""
        result = evaluate("successor of 5.0")
        assert result == Decimal("5.00000001")

    def test_predecessor_of_decimal(self) -> None:
        """Test predecessor of decimal - CQL uses 8 decimal places precision."""
        result = evaluate("predecessor of 5.0")
        assert result == Decimal("4.99999999")

    def test_successor_of_null(self) -> None:
        """Test successor of null returns null."""
        assert evaluate("successor of null") is None

    def test_predecessor_of_null(self) -> None:
        """Test predecessor of null returns null."""
        assert evaluate("predecessor of null") is None


class TestConversionExpression:
    """Test convert to expression term."""

    def test_convert_to_string(self) -> None:
        """Test convert to String."""
        assert evaluate("convert 42 to String") == "42"

    def test_convert_to_integer(self) -> None:
        """Test convert to Integer."""
        assert evaluate("convert '42' to Integer") == 42

    def test_convert_to_decimal(self) -> None:
        """Test convert to Decimal."""
        result = evaluate("convert '3.14' to Decimal")
        assert result == Decimal("3.14")

    def test_convert_to_boolean(self) -> None:
        """Test convert to Boolean."""
        assert evaluate("convert 'true' to Boolean") is True
        assert evaluate("convert 'false' to Boolean") is False

    def test_convert_with_unit(self) -> None:
        """Test convert with unit creates quantity."""
        result = evaluate("convert 100 to 'mg'")
        assert result.value == Decimal("100")
        assert result.unit == "mg"


class TestDurationDifferenceExpression:
    """Test duration in and difference in expression terms."""

    def test_duration_in_years(self) -> None:
        """Test duration in years of interval."""
        result = evaluate("duration in years of Interval[@2020-01-01, @2024-01-01]")
        assert result == 4

    def test_duration_in_months(self) -> None:
        """Test duration in months of interval."""
        result = evaluate("duration in months of Interval[@2024-01-01, @2024-06-01]")
        assert result == 5

    def test_duration_in_days(self) -> None:
        """Test duration in days of interval."""
        result = evaluate("duration in days of Interval[@2024-01-01, @2024-01-10]")
        assert result == 9

    def test_difference_in_years(self) -> None:
        """Test difference in years of interval."""
        result = evaluate("difference in years of Interval[@2020-01-01, @2024-01-01]")
        assert result == 4


class TestTypeExtentExpression:
    """Test minimum and maximum type expression terms."""

    def test_minimum_integer(self) -> None:
        """Test minimum Integer."""
        result = evaluate("minimum Integer")
        assert result == -(2**31)

    def test_maximum_integer(self) -> None:
        """Test maximum Integer."""
        result = evaluate("maximum Integer")
        assert result == 2**31 - 1

    def test_minimum_decimal(self) -> None:
        """Test minimum Decimal."""
        result = evaluate("minimum Decimal")
        # CQL Decimal: -(10^28 - 10^-8)
        assert result == Decimal("-9999999999999999999999999999.99999999")

    def test_maximum_decimal(self) -> None:
        """Test maximum Decimal."""
        result = evaluate("maximum Decimal")
        # CQL Decimal: (10^28 - 10^-8)
        assert result == Decimal("9999999999999999999999999999.99999999")


class TestWithWithoutClauses:
    """Test with and without query clauses.

    Note: These tests are skipped as they require FHIR retrieve context
    which needs more complex setup. The with/without visitor methods
    are implemented and ready to use.
    """

    @pytest.mark.skip(reason="Requires FHIR retrieve context")
    def test_with_clause_basic(self) -> None:
        """Test with clause joins data."""
        pass

    @pytest.mark.skip(reason="Requires FHIR retrieve context")
    def test_without_clause_basic(self) -> None:
        """Test without clause excludes matching data."""
        pass


class TestAggregateClause:
    """Test aggregate query clause.

    Note: These tests are skipped as aggregate clause requires
    specific query syntax with FHIR retrieves.
    """

    @pytest.mark.skip(reason="Requires FHIR retrieve context for query syntax")
    def test_aggregate_sum(self) -> None:
        """Test aggregate clause for summing."""
        pass

    @pytest.mark.skip(reason="Requires FHIR retrieve context for query syntax")
    def test_aggregate_product(self) -> None:
        """Test aggregate clause for product."""
        pass

    @pytest.mark.skip(reason="Requires FHIR retrieve context for query syntax")
    def test_aggregate_count(self) -> None:
        """Test aggregate clause for counting."""
        pass


class TestInstanceSelector:
    """Test instance selector for creating typed instances."""

    def test_instance_selector_basic(self) -> None:
        """Test basic instance selector creates dictionary."""
        result = evaluate("Patient { id: '123', active: true }")
        assert result == {"resourceType": "Patient", "id": "123", "active": True}

    def test_instance_selector_nested(self) -> None:
        """Test instance selector with nested values."""
        result = evaluate("Observation { status: 'final', value: 42 }")
        assert result == {"resourceType": "Observation", "status": "final", "value": 42}

    def test_instance_selector_with_list(self) -> None:
        """Test instance selector with list value."""
        result = evaluate("Patient { given: {'John', 'Doe'} }")
        assert result == {"resourceType": "Patient", "given": ["John", "Doe"]}

    def test_instance_selector_empty(self) -> None:
        """Test empty instance selector."""
        result = evaluate("Patient { : }")
        assert result == {"resourceType": "Patient"}


class TestAgeInYearsWithPatientContext:
    """Test AgeInYears() function with patient context."""

    def test_age_in_years_with_patient(self) -> None:
        """Test AgeInYears using patient birthDate."""
        evaluator = CQLEvaluator()
        evaluator.compile("""
            library AgeTest version '1.0'
            using FHIR version '4.0.1'
            context Patient
            define PatientAge: AgeInYears()
        """)

        # Patient born in 1990, so age should be ~34 in 2024
        patient = {"resourceType": "Patient", "id": "p1", "birthDate": "1990-06-15"}
        result = evaluator.evaluate_definition("PatientAge", resource=patient)

        # Age depends on current date, but should be reasonable
        assert result is not None
        assert isinstance(result, int)
        assert result >= 34

    def test_age_in_months_with_patient(self) -> None:
        """Test AgeInMonths using patient birthDate."""
        evaluator = CQLEvaluator()
        evaluator.compile("""
            library AgeTest version '1.0'
            using FHIR version '4.0.1'
            context Patient
            define PatientAgeMonths: AgeInMonths()
        """)

        patient = {"resourceType": "Patient", "id": "p1", "birthDate": "2023-01-15"}
        result = evaluator.evaluate_definition("PatientAgeMonths", resource=patient)

        assert result is not None
        assert isinstance(result, int)
        assert result >= 12  # At least 12 months old

    def test_age_in_years_null_birthdate(self) -> None:
        """Test AgeInYears returns null when birthDate is missing."""
        evaluator = CQLEvaluator()
        evaluator.compile("""
            library AgeTest version '1.0'
            using FHIR version '4.0.1'
            context Patient
            define PatientAge: AgeInYears()
        """)

        patient = {"resourceType": "Patient", "id": "p1"}
        result = evaluator.evaluate_definition("PatientAge", resource=patient)

        assert result is None


class TestCaseExpressionAdvanced:
    """Test advanced case expression scenarios."""

    def test_case_with_multiple_when_clauses(self) -> None:
        """Test case expression with multiple when clauses."""
        result = evaluate("""
            case
                when 1 > 2 then 'first'
                when 2 > 3 then 'second'
                when 3 > 2 then 'third'
                when 4 > 3 then 'fourth'
                else 'none'
            end
        """)
        assert result == "third"

    def test_case_all_conditions_false(self) -> None:
        """Test case expression when all conditions are false."""
        result = evaluate("""
            case
                when 1 > 2 then 'first'
                when 2 > 3 then 'second'
                else 'default'
            end
        """)
        assert result == "default"

    def test_case_with_comparator(self) -> None:
        """Test simple case expression with comparand."""
        result = evaluate("""
            case 2
                when 1 then 'one'
                when 2 then 'two'
                when 3 then 'three'
                else 'other'
            end
        """)
        assert result == "two"

    def test_case_with_null_handling(self) -> None:
        """Test case expression handles null values."""
        result = evaluate("""
            case
                when null then 'null true'
                when true then 'true'
                else 'else'
            end
        """)
        assert result == "true"

    def test_nested_case_expressions(self) -> None:
        """Test nested case expressions."""
        result = evaluate("""
            case
                when true then
                    case
                        when false then 'inner false'
                        else 'inner else'
                    end
                else 'outer else'
            end
        """)
        assert result == "inner else"


class TestComplexFromReturnQueries:
    """Test complex from...return query expressions."""

    def test_from_single_source_return(self) -> None:
        """Test from with single source and return."""
        result = evaluate("""
            from ({1, 2, 3, 4, 5}) X
            return X * 2
        """)
        assert result == [2, 4, 6, 8, 10]

    def test_from_with_where_and_return(self) -> None:
        """Test from with where clause and return."""
        result = evaluate("""
            from ({1, 2, 3, 4, 5}) X
            where X > 2
            return X * 10
        """)
        assert result == [30, 40, 50]

    def test_from_with_tuple_return(self) -> None:
        """Test from returning tuple structures."""
        result = evaluate("""
            from ({1, 2, 3}) X
            return { value: X, doubled: X * 2 }
        """)
        assert result == [
            {"value": 1, "doubled": 2},
            {"value": 2, "doubled": 4},
            {"value": 3, "doubled": 6},
        ]

    def test_from_with_let_clause(self) -> None:
        """Test from with let clause for intermediate calculation."""
        result = evaluate("""
            from ({2, 4, 6}) X
            let squared: X * X
            return { original: X, squared: squared }
        """)
        assert result == [
            {"original": 2, "squared": 4},
            {"original": 4, "squared": 16},
            {"original": 6, "squared": 36},
        ]

    def test_from_multiple_sources(self) -> None:
        """Test from with multiple sources (cross join)."""
        result = evaluate("""
            from ({1, 2}) X, ({'a', 'b'}) Y
            return { num: X, letter: Y }
        """)
        # Cross join produces all combinations
        assert len(result) == 4
        assert {"num": 1, "letter": "a"} in result
        assert {"num": 2, "letter": "b"} in result


class TestListAggregationsAdvanced:
    """Test advanced list aggregation scenarios."""

    def test_count_filtered_list(self) -> None:
        """Test Count of a filtered list."""
        # Filter then count
        result = evaluate("Count(({1, 2, 3, 4, 5}) X where X > 2 return X)")
        assert result == 3

    def test_sum_filtered_list(self) -> None:
        """Test Sum of a filtered list."""
        # Filter then sum
        result = evaluate("Sum(({1, 2, 3, 4, 5}) X where X > 2 return X)")
        assert result == 12

    def test_avg_of_list(self) -> None:
        """Test Avg of integer list."""
        result = evaluate("Avg({10, 20, 30, 40, 50})")
        assert result == Decimal("30")

    def test_min_max_of_strings(self) -> None:
        """Test Min/Max with strings."""
        assert evaluate("Min({'apple', 'banana', 'cherry'})") == "apple"
        assert evaluate("Max({'apple', 'banana', 'cherry'})") == "cherry"


class TestStringFunctionsAdvanced:
    """Test advanced string function scenarios."""

    def test_string_length_empty(self) -> None:
        """Test Length of empty string."""
        assert evaluate("Length('')") == 0

    def test_string_upper_lower(self) -> None:
        """Test Upper and Lower functions."""
        assert evaluate("Upper('hello')") == "HELLO"
        assert evaluate("Lower('HELLO')") == "hello"

    def test_string_indexer(self) -> None:
        """Test string indexer access."""
        assert evaluate("'hello'[0]") == "h"
        assert evaluate("'hello'[4]") == "o"

    def test_string_position_of(self) -> None:
        """Test PositionOf for substring search."""
        assert evaluate("PositionOf('world', 'hello world')") == 6
        # Returns -1 when not found (CQL semantics)
        assert evaluate("PositionOf('xyz', 'hello world')") == -1


class TestBooleanLogicAdvanced:
    """Test advanced boolean logic scenarios."""

    def test_three_valued_and(self) -> None:
        """Test three-valued AND logic with null."""
        assert evaluate("true and null") is None
        assert evaluate("false and null") is False
        assert evaluate("null and true") is None
        assert evaluate("null and false") is False

    def test_three_valued_or(self) -> None:
        """Test three-valued OR logic with null."""
        assert evaluate("true or null") is True
        assert evaluate("false or null") is None
        assert evaluate("null or true") is True
        assert evaluate("null or false") is None

    def test_implies_with_null(self) -> None:
        """Test implies with null values."""
        assert evaluate("false implies null") is True
        assert evaluate("true implies null") is None
