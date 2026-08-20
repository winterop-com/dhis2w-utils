"""Tests for ELM evaluator and expression visitor."""

import json
from decimal import Decimal
from typing import Any

import pytest

from dhis2w_fhir_engine.engine.cql.context import CQLContext
from dhis2w_fhir_engine.engine.cql.types import CQLInterval
from dhis2w_fhir_engine.engine.elm.evaluator import ELMEvaluator
from dhis2w_fhir_engine.engine.elm.exceptions import ELMExecutionError, ELMReferenceError
from dhis2w_fhir_engine.engine.elm.visitor import ELMExpressionVisitor


class TestELMExpressionVisitor:
    """Test the ELM expression visitor directly."""

    @pytest.fixture
    def visitor(self) -> Any:
        context = CQLContext()
        return ELMExpressionVisitor(context)

    def test_integer_literal(self, visitor: Any) -> None:
        node = {
            "type": "Literal",
            "valueType": "{urn:hl7-org:elm-types:r1}Integer",
            "value": "42",
        }
        result = visitor.evaluate(node)
        assert result == 42

    def test_decimal_literal(self, visitor: Any) -> None:
        node = {
            "type": "Literal",
            "valueType": "{urn:hl7-org:elm-types:r1}Decimal",
            "value": "3.14",
        }
        result = visitor.evaluate(node)
        assert result == Decimal("3.14")

    def test_string_literal(self, visitor: Any) -> None:
        node = {
            "type": "Literal",
            "valueType": "{urn:hl7-org:elm-types:r1}String",
            "value": "hello",
        }
        result = visitor.evaluate(node)
        assert result == "hello"

    def test_boolean_literal_true(self, visitor: Any) -> None:
        node = {
            "type": "Literal",
            "valueType": "{urn:hl7-org:elm-types:r1}Boolean",
            "value": "true",
        }
        result = visitor.evaluate(node)
        assert result is True

    def test_boolean_literal_false(self, visitor: Any) -> None:
        node = {
            "type": "Literal",
            "valueType": "{urn:hl7-org:elm-types:r1}Boolean",
            "value": "false",
        }
        result = visitor.evaluate(node)
        assert result is False

    def test_null(self, visitor: Any) -> None:
        node = {"type": "Null"}
        result = visitor.evaluate(node)
        assert result is None

    def test_add_integers(self, visitor: Any) -> None:
        node = {
            "type": "Add",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "2"},
            ],
        }
        result = visitor.evaluate(node)
        assert result == 3

    def test_subtract_integers(self, visitor: Any) -> None:
        node = {
            "type": "Subtract",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "5"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "3"},
            ],
        }
        result = visitor.evaluate(node)
        assert result == 2

    def test_multiply_integers(self, visitor: Any) -> None:
        node = {
            "type": "Multiply",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "4"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "3"},
            ],
        }
        result = visitor.evaluate(node)
        assert result == 12

    def test_divide_integers(self, visitor: Any) -> None:
        node = {
            "type": "Divide",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "10"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "4"},
            ],
        }
        result = visitor.evaluate(node)
        assert result == Decimal("2.5")

    def test_divide_by_zero(self, visitor: Any) -> None:
        node = {
            "type": "Divide",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "10"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "0"},
            ],
        }
        result = visitor.evaluate(node)
        assert result is None

    def test_truncated_divide(self, visitor: Any) -> None:
        node = {
            "type": "TruncatedDivide",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "10"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "3"},
            ],
        }
        result = visitor.evaluate(node)
        assert result == 3

    def test_modulo(self, visitor: Any) -> None:
        node = {
            "type": "Modulo",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "10"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "3"},
            ],
        }
        result = visitor.evaluate(node)
        assert result == 1

    def test_power(self, visitor: Any) -> None:
        node = {
            "type": "Power",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "2"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "3"},
            ],
        }
        result = visitor.evaluate(node)
        assert result == 8

    def test_negate(self, visitor: Any) -> None:
        node = {
            "type": "Negate",
            "operand": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "5"},
        }
        result = visitor.evaluate(node)
        assert result == -5

    def test_abs_positive(self, visitor: Any) -> None:
        node = {
            "type": "Abs",
            "operand": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "5"},
        }
        result = visitor.evaluate(node)
        assert result == 5

    def test_abs_negative(self, visitor: Any) -> None:
        node = {
            "type": "Abs",
            "operand": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "-5"},
        }
        result = visitor.evaluate(node)
        assert result == 5

    def test_ceiling(self, visitor: Any) -> None:
        node = {
            "type": "Ceiling",
            "operand": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Decimal", "value": "3.2"},
        }
        result = visitor.evaluate(node)
        assert result == 4

    def test_floor(self, visitor: Any) -> None:
        node = {
            "type": "Floor",
            "operand": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Decimal", "value": "3.8"},
        }
        result = visitor.evaluate(node)
        assert result == 3

    def test_truncate(self, visitor: Any) -> None:
        node = {
            "type": "Truncate",
            "operand": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Decimal", "value": "3.9"},
        }
        result = visitor.evaluate(node)
        assert result == 3

    def test_round(self, visitor: Any) -> None:
        node = {
            "type": "Round",
            "operand": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Decimal", "value": "3.5"},
        }
        result = visitor.evaluate(node)
        assert result == 4

    def test_equal_true(self, visitor: Any) -> None:
        node = {
            "type": "Equal",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "5"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "5"},
            ],
        }
        result = visitor.evaluate(node)
        assert result is True

    def test_equal_false(self, visitor: Any) -> None:
        node = {
            "type": "Equal",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "5"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "3"},
            ],
        }
        result = visitor.evaluate(node)
        assert result is False

    def test_not_equal_true(self, visitor: Any) -> None:
        node = {
            "type": "NotEqual",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "5"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "3"},
            ],
        }
        result = visitor.evaluate(node)
        assert result is True

    def test_less_true(self, visitor: Any) -> None:
        node = {
            "type": "Less",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "3"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "5"},
            ],
        }
        result = visitor.evaluate(node)
        assert result is True

    def test_less_false(self, visitor: Any) -> None:
        node = {
            "type": "Less",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "5"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "3"},
            ],
        }
        result = visitor.evaluate(node)
        assert result is False

    def test_greater_true(self, visitor: Any) -> None:
        node = {
            "type": "Greater",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "5"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "3"},
            ],
        }
        result = visitor.evaluate(node)
        assert result is True

    def test_less_or_equal_equal(self, visitor: Any) -> None:
        node = {
            "type": "LessOrEqual",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "5"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "5"},
            ],
        }
        result = visitor.evaluate(node)
        assert result is True

    def test_greater_or_equal_equal(self, visitor: Any) -> None:
        node = {
            "type": "GreaterOrEqual",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "5"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "5"},
            ],
        }
        result = visitor.evaluate(node)
        assert result is True

    def test_and_true_true(self, visitor: Any) -> None:
        node = {
            "type": "And",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Boolean", "value": "true"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Boolean", "value": "true"},
            ],
        }
        result = visitor.evaluate(node)
        assert result is True

    def test_and_true_false(self, visitor: Any) -> None:
        node = {
            "type": "And",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Boolean", "value": "true"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Boolean", "value": "false"},
            ],
        }
        result = visitor.evaluate(node)
        assert result is False

    def test_and_false_null(self, visitor: Any) -> None:
        node = {
            "type": "And",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Boolean", "value": "false"},
                {"type": "Null"},
            ],
        }
        result = visitor.evaluate(node)
        assert result is False

    def test_or_false_false(self, visitor: Any) -> None:
        node = {
            "type": "Or",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Boolean", "value": "false"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Boolean", "value": "false"},
            ],
        }
        result = visitor.evaluate(node)
        assert result is False

    def test_or_true_false(self, visitor: Any) -> None:
        node = {
            "type": "Or",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Boolean", "value": "true"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Boolean", "value": "false"},
            ],
        }
        result = visitor.evaluate(node)
        assert result is True

    def test_or_true_null(self, visitor: Any) -> None:
        node = {
            "type": "Or",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Boolean", "value": "true"},
                {"type": "Null"},
            ],
        }
        result = visitor.evaluate(node)
        assert result is True

    def test_not_true(self, visitor: Any) -> None:
        node = {
            "type": "Not",
            "operand": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Boolean", "value": "true"},
        }
        result = visitor.evaluate(node)
        assert result is False

    def test_not_false(self, visitor: Any) -> None:
        node = {
            "type": "Not",
            "operand": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Boolean", "value": "false"},
        }
        result = visitor.evaluate(node)
        assert result is True

    def test_not_null(self, visitor: Any) -> None:
        node = {
            "type": "Not",
            "operand": {"type": "Null"},
        }
        result = visitor.evaluate(node)
        assert result is None

    def test_is_null_true(self, visitor: Any) -> None:
        node = {
            "type": "IsNull",
            "operand": {"type": "Null"},
        }
        result = visitor.evaluate(node)
        assert result is True

    def test_is_null_false(self, visitor: Any) -> None:
        node = {
            "type": "IsNull",
            "operand": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "5"},
        }
        result = visitor.evaluate(node)
        assert result is False

    def test_if_true(self, visitor: Any) -> None:
        node = {
            "type": "If",
            "condition": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Boolean", "value": "true"},
            "then": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},
            "else": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "2"},
        }
        result = visitor.evaluate(node)
        assert result == 1

    def test_if_false(self, visitor: Any) -> None:
        node = {
            "type": "If",
            "condition": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Boolean", "value": "false"},
            "then": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},
            "else": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "2"},
        }
        result = visitor.evaluate(node)
        assert result == 2

    def test_if_null(self, visitor: Any) -> None:
        node = {
            "type": "If",
            "condition": {"type": "Null"},
            "then": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},
            "else": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "2"},
        }
        result = visitor.evaluate(node)
        assert result == 2

    def test_coalesce_first_not_null(self, visitor: Any) -> None:
        node = {
            "type": "Coalesce",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "2"},
            ],
        }
        result = visitor.evaluate(node)
        assert result == 1

    def test_coalesce_first_null(self, visitor: Any) -> None:
        node = {
            "type": "Coalesce",
            "operand": [
                {"type": "Null"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "2"},
            ],
        }
        result = visitor.evaluate(node)
        assert result == 2

    def test_coalesce_all_null(self, visitor: Any) -> None:
        node = {
            "type": "Coalesce",
            "operand": [
                {"type": "Null"},
                {"type": "Null"},
            ],
        }
        result = visitor.evaluate(node)
        assert result is None

    def test_concatenate(self, visitor: Any) -> None:
        node = {
            "type": "Concatenate",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}String", "value": "Hello"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}String", "value": " World"},
            ],
        }
        result = visitor.evaluate(node)
        assert result == "Hello World"

    def test_length(self, visitor: Any) -> None:
        node = {
            "type": "Length",
            "operand": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}String", "value": "hello"},
        }
        result = visitor.evaluate(node)
        assert result == 5

    def test_upper(self, visitor: Any) -> None:
        node = {
            "type": "Upper",
            "operand": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}String", "value": "hello"},
        }
        result = visitor.evaluate(node)
        assert result == "HELLO"

    def test_lower(self, visitor: Any) -> None:
        node = {
            "type": "Lower",
            "operand": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}String", "value": "HELLO"},
        }
        result = visitor.evaluate(node)
        assert result == "hello"

    def test_starts_with(self, visitor: Any) -> None:
        node = {
            "type": "StartsWith",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}String", "value": "hello world"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}String", "value": "hello"},
            ],
        }
        result = visitor.evaluate(node)
        assert result is True

    def test_ends_with(self, visitor: Any) -> None:
        node = {
            "type": "EndsWith",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}String", "value": "hello world"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}String", "value": "world"},
            ],
        }
        result = visitor.evaluate(node)
        assert result is True

    def test_substring(self, visitor: Any) -> None:
        node = {
            "type": "Substring",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}String", "value": "hello"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "0"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "3"},
            ],
        }
        result = visitor.evaluate(node)
        assert result == "hel"

    def test_list(self, visitor: Any) -> None:
        node = {
            "type": "List",
            "element": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "2"},
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "3"},
            ],
        }
        result = visitor.evaluate(node)
        assert result == [1, 2, 3]

    def test_list_empty(self, visitor: Any) -> None:
        node = {"type": "List", "element": []}
        result = visitor.evaluate(node)
        assert result == []

    def test_first(self, visitor: Any) -> None:
        node = {
            "type": "First",
            "source": {
                "type": "List",
                "element": [
                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},
                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "2"},
                ],
            },
        }
        result = visitor.evaluate(node)
        assert result == 1

    def test_last(self, visitor: Any) -> None:
        node = {
            "type": "Last",
            "source": {
                "type": "List",
                "element": [
                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},
                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "2"},
                ],
            },
        }
        result = visitor.evaluate(node)
        assert result == 2

    def test_exists_true(self, visitor: Any) -> None:
        node = {
            "type": "Exists",
            "operand": {
                "type": "List",
                "element": [
                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},
                ],
            },
        }
        result = visitor.evaluate(node)
        assert result is True

    def test_exists_false(self, visitor: Any) -> None:
        node = {
            "type": "Exists",
            "operand": {"type": "List", "element": []},
        }
        result = visitor.evaluate(node)
        assert result is False

    def test_count(self, visitor: Any) -> None:
        node = {
            "type": "Count",
            "source": {
                "type": "List",
                "element": [
                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},
                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "2"},
                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "3"},
                ],
            },
        }
        result = visitor.evaluate(node)
        assert result == 3

    def test_sum(self, visitor: Any) -> None:
        node = {
            "type": "Sum",
            "source": {
                "type": "List",
                "element": [
                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},
                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "2"},
                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "3"},
                ],
            },
        }
        result = visitor.evaluate(node)
        assert result == 6

    def test_avg(self, visitor: Any) -> None:
        node = {
            "type": "Avg",
            "source": {
                "type": "List",
                "element": [
                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},
                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "2"},
                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "3"},
                ],
            },
        }
        result = visitor.evaluate(node)
        assert result == Decimal("2")

    def test_min(self, visitor: Any) -> None:
        node = {
            "type": "Min",
            "source": {
                "type": "List",
                "element": [
                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "3"},
                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},
                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "2"},
                ],
            },
        }
        result = visitor.evaluate(node)
        assert result == 1

    def test_max(self, visitor: Any) -> None:
        node = {
            "type": "Max",
            "source": {
                "type": "List",
                "element": [
                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},
                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "3"},
                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "2"},
                ],
            },
        }
        result = visitor.evaluate(node)
        assert result == 3

    def test_interval(self, visitor: Any) -> None:
        node = {
            "type": "Interval",
            "low": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},
            "high": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "10"},
            "lowClosed": True,
            "highClosed": True,
        }
        result = visitor.evaluate(node)
        assert isinstance(result, CQLInterval)
        assert result.low == 1
        assert result.high == 10

    def test_start_of_interval(self, visitor: Any) -> None:
        node = {
            "type": "Start",
            "operand": {
                "type": "Interval",
                "low": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "5"},
                "high": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "10"},
            },
        }
        result = visitor.evaluate(node)
        assert result == 5

    def test_end_of_interval(self, visitor: Any) -> None:
        node = {
            "type": "End",
            "operand": {
                "type": "Interval",
                "low": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "5"},
                "high": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "10"},
            },
        }
        result = visitor.evaluate(node)
        assert result == 10

    def test_in_interval(self, visitor: Any) -> None:
        node = {
            "type": "In",
            "operand": [
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "5"},
                {
                    "type": "Interval",
                    "low": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},
                    "high": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "10"},
                    "lowClosed": True,
                    "highClosed": True,
                },
            ],
        }
        result = visitor.evaluate(node)
        assert result is True

    def test_contains_interval(self, visitor: Any) -> None:
        node = {
            "type": "Contains",
            "operand": [
                {
                    "type": "Interval",
                    "low": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},
                    "high": {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "10"},
                    "lowClosed": True,
                    "highClosed": True,
                },
                {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "5"},
            ],
        }
        result = visitor.evaluate(node)
        assert result is True

    def test_unknown_type_raises_error(self, visitor: Any) -> None:
        node = {"type": "UnknownExpression"}
        with pytest.raises(ELMExecutionError):
            visitor.evaluate(node)


class TestELMEvaluator:
    """Test the ELM evaluator."""

    @pytest.fixture
    def evaluator(self) -> Any:
        return ELMEvaluator()

    def test_load_from_dict(self, evaluator: Any) -> None:
        data = {
            "library": {
                "identifier": {"id": "TestLibrary", "version": "1.0.0"},
            }
        }
        library = evaluator.load(data)
        assert library.identifier.id == "TestLibrary"
        assert evaluator.current_library is library

    def test_load_from_json_string(self, evaluator: Any) -> None:
        json_str = json.dumps(
            {
                "library": {
                    "identifier": {"id": "TestLibrary", "version": "1.0.0"},
                }
            }
        )
        library = evaluator.load(json_str)
        assert library.identifier.id == "TestLibrary"

    def test_evaluate_simple_definition(self, evaluator: Any) -> None:
        data = {
            "library": {
                "identifier": {"id": "TestLibrary"},
                "statements": {
                    "def": [
                        {
                            "name": "Sum",
                            "expression": {
                                "type": "Add",
                                "operand": [
                                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},
                                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "2"},
                                ],
                            },
                        }
                    ]
                },
            }
        }
        evaluator.load(data)
        result = evaluator.evaluate_definition("Sum")
        assert result == 3

    def test_evaluate_definition_not_found(self, evaluator: Any) -> None:
        data = {
            "library": {
                "identifier": {"id": "TestLibrary"},
            }
        }
        evaluator.load(data)
        with pytest.raises(ELMReferenceError):
            evaluator.evaluate_definition("NonExistent")

    def test_evaluate_no_library_loaded(self, evaluator: Any) -> None:
        with pytest.raises(ELMExecutionError):
            evaluator.evaluate_definition("Sum")

    def test_evaluate_all_definitions(self, evaluator: Any) -> None:
        data = {
            "library": {
                "identifier": {"id": "TestLibrary"},
                "statements": {
                    "def": [
                        {
                            "name": "One",
                            "expression": {
                                "type": "Literal",
                                "valueType": "{urn:hl7-org:elm-types:r1}Integer",
                                "value": "1",
                            },
                        },
                        {
                            "name": "Two",
                            "expression": {
                                "type": "Literal",
                                "valueType": "{urn:hl7-org:elm-types:r1}Integer",
                                "value": "2",
                            },
                        },
                    ]
                },
            }
        }
        evaluator.load(data)
        results = evaluator.evaluate_all_definitions()
        assert results["One"] == 1
        assert results["Two"] == 2

    def test_get_definition_names(self, evaluator: Any) -> None:
        data = {
            "library": {
                "identifier": {"id": "TestLibrary"},
                "statements": {
                    "def": [
                        {"name": "One", "expression": {}},
                        {"name": "Two", "expression": {}},
                    ]
                },
            }
        }
        evaluator.load(data)
        names = evaluator.get_definition_names()
        assert "One" in names
        assert "Two" in names

    def test_get_library_info(self, evaluator: Any) -> None:
        data = {
            "library": {
                "identifier": {"id": "TestLibrary", "version": "1.0.0"},
                "usings": [{"localIdentifier": "FHIR", "uri": "http://hl7.org/fhir"}],
            }
        }
        evaluator.load(data)
        info = evaluator.get_library_info()
        assert info["id"] == "TestLibrary"
        assert info["version"] == "1.0.0"
        assert len(info["usings"]) == 1

    def test_validate_valid(self, evaluator: Any) -> None:
        data = {
            "library": {
                "identifier": {"id": "TestLibrary"},
            }
        }
        is_valid, errors = evaluator.validate(data)
        assert is_valid
        assert len(errors) == 0

    def test_validate_invalid(self, evaluator: Any) -> None:
        data: dict[str, Any] = {"library": {}}
        is_valid, errors = evaluator.validate(data)
        assert not is_valid
        assert len(errors) > 0

    def test_evaluate_with_parameters(self, evaluator: Any) -> None:
        data = {
            "library": {
                "identifier": {"id": "TestLibrary"},
                "parameters": [
                    {"name": "X", "parameterType": "{urn:hl7-org:elm-types:r1}Integer"},
                ],
                "statements": {
                    "def": [
                        {
                            "name": "DoubleX",
                            "expression": {
                                "type": "Multiply",
                                "operand": [
                                    {"type": "ParameterRef", "name": "X"},
                                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "2"},
                                ],
                            },
                        }
                    ]
                },
            }
        }
        evaluator.load(data)
        result = evaluator.evaluate_definition("DoubleX", parameters={"X": 5})
        assert result == 10

    def test_nested_expression(self, evaluator: Any) -> None:
        data = {
            "library": {
                "identifier": {"id": "TestLibrary"},
                "statements": {
                    "def": [
                        {
                            "name": "Complex",
                            "expression": {
                                "type": "Add",
                                "operand": [
                                    {
                                        "type": "Multiply",
                                        "operand": [
                                            {
                                                "type": "Literal",
                                                "valueType": "{urn:hl7-org:elm-types:r1}Integer",
                                                "value": "2",
                                            },
                                            {
                                                "type": "Literal",
                                                "valueType": "{urn:hl7-org:elm-types:r1}Integer",
                                                "value": "3",
                                            },
                                        ],
                                    },
                                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "4"},
                                ],
                            },
                        }
                    ]
                },
            }
        }
        evaluator.load(data)
        result = evaluator.evaluate_definition("Complex")
        assert result == 10  # (2 * 3) + 4

    def test_conditional_expression(self, evaluator: Any) -> None:
        data = {
            "library": {
                "identifier": {"id": "TestLibrary"},
                "statements": {
                    "def": [
                        {
                            "name": "IfTest",
                            "expression": {
                                "type": "If",
                                "condition": {
                                    "type": "Greater",
                                    "operand": [
                                        {
                                            "type": "Literal",
                                            "valueType": "{urn:hl7-org:elm-types:r1}Integer",
                                            "value": "5",
                                        },
                                        {
                                            "type": "Literal",
                                            "valueType": "{urn:hl7-org:elm-types:r1}Integer",
                                            "value": "3",
                                        },
                                    ],
                                },
                                "then": {
                                    "type": "Literal",
                                    "valueType": "{urn:hl7-org:elm-types:r1}String",
                                    "value": "yes",
                                },
                                "else": {
                                    "type": "Literal",
                                    "valueType": "{urn:hl7-org:elm-types:r1}String",
                                    "value": "no",
                                },
                            },
                        }
                    ]
                },
            }
        }
        evaluator.load(data)
        result = evaluator.evaluate_definition("IfTest")
        assert result == "yes"

    def test_list_operations(self, evaluator: Any) -> None:
        data = {
            "library": {
                "identifier": {"id": "TestLibrary"},
                "statements": {
                    "def": [
                        {
                            "name": "ListSum",
                            "expression": {
                                "type": "Sum",
                                "source": {
                                    "type": "List",
                                    "element": [
                                        {
                                            "type": "Literal",
                                            "valueType": "{urn:hl7-org:elm-types:r1}Integer",
                                            "value": "1",
                                        },
                                        {
                                            "type": "Literal",
                                            "valueType": "{urn:hl7-org:elm-types:r1}Integer",
                                            "value": "2",
                                        },
                                        {
                                            "type": "Literal",
                                            "valueType": "{urn:hl7-org:elm-types:r1}Integer",
                                            "value": "3",
                                        },
                                        {
                                            "type": "Literal",
                                            "valueType": "{urn:hl7-org:elm-types:r1}Integer",
                                            "value": "4",
                                        },
                                        {
                                            "type": "Literal",
                                            "valueType": "{urn:hl7-org:elm-types:r1}Integer",
                                            "value": "5",
                                        },
                                    ],
                                },
                            },
                        }
                    ]
                },
            }
        }
        evaluator.load(data)
        result = evaluator.evaluate_definition("ListSum")
        assert result == 15

    def test_expression_ref(self, evaluator: Any) -> None:
        data = {
            "library": {
                "identifier": {"id": "TestLibrary"},
                "statements": {
                    "def": [
                        {
                            "name": "Base",
                            "expression": {
                                "type": "Literal",
                                "valueType": "{urn:hl7-org:elm-types:r1}Integer",
                                "value": "10",
                            },
                        },
                        {
                            "name": "Derived",
                            "expression": {
                                "type": "Add",
                                "operand": [
                                    {"type": "ExpressionRef", "name": "Base"},
                                    {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "5"},
                                ],
                            },
                        },
                    ]
                },
            }
        }
        evaluator.load(data)
        result = evaluator.evaluate_definition("Derived")
        assert result == 15
