"""Per-operator tests for the ELM expression visitor, driven by hand-written ELM JSON nodes."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from dhis2w_fhir_engine.engine.cql.context import CQLContext
from dhis2w_fhir_engine.engine.cql.types import CQLCode, CQLConcept, CQLInterval, CQLTuple
from dhis2w_fhir_engine.engine.elm.exceptions import ELMExecutionError
from dhis2w_fhir_engine.engine.elm.loader import ELMLoader
from dhis2w_fhir_engine.engine.elm.visitor import ELMExpressionVisitor
from dhis2w_fhir_engine.engine.types import FHIRDate, FHIRDateTime, FHIRTime, Quantity

ELM_TYPE = "{urn:hl7-org:elm-types:r1}"

NULL: dict[str, Any] = {"type": "Null"}


def integer(value: int) -> dict[str, Any]:
    """Build an ELM Integer literal node."""
    return {"type": "Literal", "valueType": f"{ELM_TYPE}Integer", "value": str(value)}


def decimal(value: str) -> dict[str, Any]:
    """Build an ELM Decimal literal node."""
    return {"type": "Literal", "valueType": f"{ELM_TYPE}Decimal", "value": value}


def string(value: str) -> dict[str, Any]:
    """Build an ELM String literal node."""
    return {"type": "Literal", "valueType": f"{ELM_TYPE}String", "value": value}


def boolean(value: bool) -> dict[str, Any]:
    """Build an ELM Boolean literal node."""
    return {"type": "Literal", "valueType": f"{ELM_TYPE}Boolean", "value": "true" if value else "false"}


def date_literal(value: str) -> dict[str, Any]:
    """Build an ELM Date literal node."""
    return {"type": "Literal", "valueType": f"{ELM_TYPE}Date", "value": value}


def datetime_literal(value: str) -> dict[str, Any]:
    """Build an ELM DateTime literal node."""
    return {"type": "Literal", "valueType": f"{ELM_TYPE}DateTime", "value": value}


def elm_list(*elements: dict[str, Any]) -> dict[str, Any]:
    """Build an ELM List node."""
    return {"type": "List", "element": list(elements)}


def interval(
    low: dict[str, Any] | None,
    high: dict[str, Any] | None,
    low_closed: bool = True,
    high_closed: bool = True,
) -> dict[str, Any]:
    """Build an ELM Interval node, omitting bounds that are None."""
    node: dict[str, Any] = {"type": "Interval", "lowClosed": low_closed, "highClosed": high_closed}
    if low is not None:
        node["low"] = low
    if high is not None:
        node["high"] = high
    return node


def named_type(type_name: str) -> dict[str, Any]:
    """Build a NamedTypeSpecifier for a System type."""
    return {"type": "NamedTypeSpecifier", "name": f"{ELM_TYPE}{type_name}"}


@pytest.fixture
def visitor() -> ELMExpressionVisitor:
    """A visitor with an empty context and no library bound."""
    return ELMExpressionVisitor(CQLContext())


class TestLiteralNodes:
    """Literal and selector nodes."""

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            (date_literal("2024-03-05"), FHIRDate(year=2024, month=3, day=5)),
            (
                datetime_literal("2024-03-05T10:00:00"),
                FHIRDateTime(year=2024, month=3, day=5, hour=10, minute=0, second=0),
            ),
            ({"type": "Literal", "valueType": f"{ELM_TYPE}Time", "value": "10:30:00"}, "10:30:00"),
            ({"type": "Literal", "valueType": f"{ELM_TYPE}Long", "value": "9"}, 9),
            ({"type": "Literal", "valueType": f"{ELM_TYPE}Integer"}, None),
            ({"type": "Literal", "valueType": f"{ELM_TYPE}Unmapped", "value": "raw"}, "raw"),
            ({"type": "Literal", "valueType": f"{ELM_TYPE}Boolean", "value": True}, True),
        ],
    )
    def test_literal_parses_by_value_type(
        self, visitor: ELMExpressionVisitor, node: dict[str, Any], expected: Any
    ) -> None:
        assert visitor.evaluate(node) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("5 mg", Quantity(value=Decimal("5"), unit="mg")), ("5", Quantity(value=Decimal("5"), unit="1"))],
    )
    def test_quantity_literal_splits_value_and_unit(
        self, visitor: ELMExpressionVisitor, value: str, expected: Quantity
    ) -> None:
        node = {"type": "Literal", "valueType": f"{ELM_TYPE}Quantity", "value": value}
        assert visitor.evaluate(node) == expected

    def test_interval_reads_dynamic_closed_expressions(self, visitor: ELMExpressionVisitor) -> None:
        node = {
            "type": "Interval",
            "low": integer(1),
            "high": integer(5),
            "lowClosedExpression": boolean(False),
            "highClosedExpression": boolean(True),
        }
        result = visitor.evaluate(node)
        assert result == CQLInterval(low=1, high=5, low_closed=False, high_closed=True)

    def test_tuple_builds_named_elements(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "Tuple", "element": [{"name": "a", "value": integer(1)}, {"name": "b", "value": string("x")}]}
        assert visitor.evaluate(node) == CQLTuple(elements={"a": 1, "b": "x"})

    @pytest.mark.parametrize("class_type", ["{http://hl7.org/fhir}Patient", "Patient"])
    def test_instance_uses_local_name_as_resource_type(self, visitor: ELMExpressionVisitor, class_type: str) -> None:
        node = {"type": "Instance", "classType": class_type, "element": [{"name": "id", "value": string("p1")}]}
        assert visitor.evaluate(node) == {"resourceType": "Patient", "id": "p1"}

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            ({"type": "Quantity", "value": "12.5", "unit": "mg"}, Quantity(value=Decimal("12.5"), unit="mg")),
            ({"type": "Quantity", "value": "3"}, Quantity(value=Decimal("3"), unit="1")),
            ({"type": "Quantity"}, None),
        ],
    )
    def test_quantity_node(self, visitor: ELMExpressionVisitor, node: dict[str, Any], expected: Any) -> None:
        assert visitor.evaluate(node) == expected

    def test_ratio_evaluates_both_sides(self, visitor: ELMExpressionVisitor) -> None:
        node = {
            "type": "Ratio",
            "numerator": {"type": "Quantity", "value": "1", "unit": "mg"},
            "denominator": {"type": "Quantity", "value": "2", "unit": "mg"},
        }
        assert visitor.evaluate(node) == {
            "numerator": Quantity(value=Decimal("1"), unit="mg"),
            "denominator": Quantity(value=Decimal("2"), unit="mg"),
        }

    def test_code_node_evaluates_system_expression(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "Code", "code": "1234", "system": string("http://loinc.org"), "display": "Test"}
        assert visitor.evaluate(node) == CQLCode(code="1234", system="http://loinc.org", display="Test")

    def test_code_node_without_system_uses_empty_string(self, visitor: ELMExpressionVisitor) -> None:
        result = visitor.evaluate({"type": "Code", "code": "1234"})
        assert result == CQLCode(code="1234", system="")

    def test_concept_node_collects_codes(self, visitor: ELMExpressionVisitor) -> None:
        node = {
            "type": "Concept",
            "code": [{"type": "Code", "code": "a", "system": string("s")}],
            "display": "C",
        }
        expected = CQLConcept(codes=(CQLCode(code="a", system="s"),), display="C")
        assert visitor.evaluate(node) == expected


class TestArithmetic:
    """Arithmetic operators, including their null branches."""

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            ({"type": "Ln", "operand": decimal("2.718281828459045")}, Decimal("1.0")),
            ({"type": "Ln", "operand": integer(0)}, None),
            ({"type": "Ln", "operand": NULL}, None),
            ({"type": "Log", "operand": [integer(8), integer(2)]}, Decimal("3.0")),
            ({"type": "Log", "operand": [integer(0), integer(2)]}, None),
            ({"type": "Log", "operand": [NULL, integer(2)]}, None),
            ({"type": "Exp", "operand": integer(0)}, Decimal("1.0")),
            ({"type": "Exp", "operand": NULL}, None),
            ({"type": "Round", "operand": decimal("3.14159"), "precision": integer(2)}, Decimal("3.14")),
        ],
    )
    def test_transcendental_operators(self, visitor: ELMExpressionVisitor, node: dict[str, Any], expected: Any) -> None:
        assert visitor.evaluate(node) == expected

    @pytest.mark.parametrize(
        "node_type",
        ["Add", "Subtract", "Multiply", "Divide", "TruncatedDivide", "Modulo", "Power", "Log"],
    )
    def test_binary_arithmetic_propagates_null(self, visitor: ELMExpressionVisitor, node_type: str) -> None:
        assert visitor.evaluate({"type": node_type, "operand": [integer(1), NULL]}) is None

    @pytest.mark.parametrize("node_type", ["Negate", "Abs", "Ceiling", "Floor", "Truncate", "Round"])
    def test_unary_arithmetic_propagates_null(self, visitor: ELMExpressionVisitor, node_type: str) -> None:
        assert visitor.evaluate({"type": node_type, "operand": NULL}) is None

    @pytest.mark.parametrize("node_type", ["TruncatedDivide", "Modulo"])
    def test_integer_division_by_zero_is_null(self, visitor: ELMExpressionVisitor, node_type: str) -> None:
        assert visitor.evaluate({"type": node_type, "operand": [integer(10), integer(0)]}) is None

    def test_binary_operator_rejects_wrong_operand_count(self, visitor: ELMExpressionVisitor) -> None:
        with pytest.raises(ELMExecutionError, match="requires 2 operands"):
            visitor.evaluate({"type": "Add", "operand": [integer(1)]})

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            ({"type": "Successor", "operand": integer(5)}, 6),
            ({"type": "Successor", "operand": decimal("1.5")}, Decimal("1.50000001")),
            ({"type": "Successor", "operand": date_literal("2024-01-31")}, FHIRDate(year=2024, month=2, day=1)),
            ({"type": "Successor", "operand": date_literal("2024-12")}, FHIRDate(year=2025, month=1)),
            ({"type": "Successor", "operand": date_literal("2024-06")}, FHIRDate(year=2024, month=7)),
            ({"type": "Successor", "operand": date_literal("2024")}, FHIRDate(year=2025)),
            ({"type": "Successor", "operand": string("abc")}, "abc"),
            ({"type": "Successor", "operand": NULL}, None),
            ({"type": "Predecessor", "operand": integer(5)}, 4),
            ({"type": "Predecessor", "operand": decimal("1.5")}, Decimal("1.49999999")),
            ({"type": "Predecessor", "operand": date_literal("2024-01-01")}, FHIRDate(year=2023, month=12, day=31)),
            ({"type": "Predecessor", "operand": date_literal("2024-01")}, FHIRDate(year=2023, month=12)),
            ({"type": "Predecessor", "operand": date_literal("2024-06")}, FHIRDate(year=2024, month=5)),
            ({"type": "Predecessor", "operand": date_literal("2024")}, FHIRDate(year=2023)),
            ({"type": "Predecessor", "operand": string("abc")}, "abc"),
            ({"type": "Predecessor", "operand": NULL}, None),
        ],
    )
    def test_successor_and_predecessor(
        self, visitor: ELMExpressionVisitor, node: dict[str, Any], expected: Any
    ) -> None:
        assert visitor.evaluate(node) == expected

    def test_successor_of_datetime_advances_one_millisecond(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "Successor", "operand": datetime_literal("2024-01-01T00:00:00.000")}
        assert visitor.evaluate(node) == FHIRDateTime(
            year=2024, month=1, day=1, hour=0, minute=0, second=0, millisecond=1
        )

    def test_predecessor_of_datetime_steps_back_one_millisecond(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "Predecessor", "operand": datetime_literal("2024-01-01T00:00:00.005")}
        assert visitor.evaluate(node) == FHIRDateTime(
            year=2024, month=1, day=1, hour=0, minute=0, second=0, millisecond=4
        )

    @pytest.mark.parametrize(
        ("node_type", "value", "expected"),
        [
            ("Successor", "2024-01T", FHIRDateTime(year=2024, month=1, day=2)),
            ("Predecessor", "2024-01T", FHIRDateTime(year=2024, month=1, day=28)),
            ("Successor", "2024T", FHIRDateTime(year=2024, month=2)),
            ("Predecessor", "2024T", FHIRDateTime(year=2024, month=12)),
        ],
    )
    def test_partial_datetime_steps_at_its_coarsest_precision(
        self, visitor: ELMExpressionVisitor, node_type: str, value: str, expected: FHIRDateTime
    ) -> None:
        assert visitor.evaluate({"type": node_type, "operand": datetime_literal(value)}) == expected

    @pytest.mark.parametrize(
        ("node_type", "value_type", "expected"),
        [
            ("MinValue", "Integer", -(2**31)),
            ("MinValue", "Decimal", Decimal("-99999999999999999999.99999999")),
            ("MinValue", "String", None),
            ("MaxValue", "Integer", 2**31 - 1),
            ("MaxValue", "Decimal", Decimal("99999999999999999999.99999999")),
            ("MaxValue", "String", None),
        ],
    )
    def test_type_bounds(self, visitor: ELMExpressionVisitor, node_type: str, value_type: str, expected: Any) -> None:
        assert visitor.evaluate({"type": node_type, "valueType": f"{ELM_TYPE}{value_type}"}) == expected


def time_value(value: str) -> dict[str, Any]:
    """Build a node that evaluates to a FHIRTime by casting a string."""
    return {"type": "As", "operand": string(value), "asTypeSpecifier": named_type("Time")}


class TestSuccessorOnTemporalValues:
    """Successor and Predecessor on FHIRTime and Quantity operands."""

    @pytest.mark.parametrize(
        ("node_type", "operand", "expected"),
        [
            ("Successor", "10:00:00.000", FHIRTime(hour=10, minute=0, second=0, millisecond=1)),
            ("Predecessor", "10:00:00.005", FHIRTime(hour=10, minute=0, second=0, millisecond=4)),
            ("Successor", "23:59:59.999", FHIRTime(hour=23, minute=59, second=59, millisecond=999)),
            ("Predecessor", "00:00:00.000", FHIRTime(hour=0, minute=0, second=0, millisecond=0)),
        ],
    )
    def test_time_steps_by_one_millisecond(
        self, visitor: ELMExpressionVisitor, node_type: str, operand: str, expected: FHIRTime
    ) -> None:
        assert visitor.evaluate({"type": node_type, "operand": time_value(operand)}) == expected

    @pytest.mark.parametrize(
        ("node_type", "expected_value"),
        [("Successor", Decimal("5.00000001")), ("Predecessor", Decimal("4.99999999"))],
    )
    def test_quantity_steps_by_smallest_decimal_increment(
        self, visitor: ELMExpressionVisitor, node_type: str, expected_value: Decimal
    ) -> None:
        operand = {"type": "Quantity", "value": "5", "unit": "mg"}
        result = visitor.evaluate({"type": node_type, "operand": operand})
        assert result == Quantity(value=expected_value, unit="mg")


class TestComparisonAndLogic:
    """Comparison, equivalence and three-valued logic."""

    @pytest.mark.parametrize("node_type", ["Equal", "NotEqual", "Less", "LessOrEqual", "Greater", "GreaterOrEqual"])
    def test_comparison_propagates_null(self, visitor: ELMExpressionVisitor, node_type: str) -> None:
        assert visitor.evaluate({"type": node_type, "operand": [integer(1), NULL]}) is None

    @pytest.mark.parametrize(
        ("operands", "expected"),
        [
            ([NULL, NULL], True),
            ([integer(1), NULL], False),
            ([NULL, integer(1)], False),
            ([integer(1), integer(1)], True),
        ],
    )
    def test_equivalent_is_null_safe(
        self, visitor: ELMExpressionVisitor, operands: list[dict[str, Any]], expected: bool
    ) -> None:
        assert visitor.evaluate({"type": "Equivalent", "operand": operands}) is expected

    @pytest.mark.parametrize(
        ("operands", "expected"),
        [
            ([boolean(True), boolean(False)], True),
            ([boolean(True), boolean(True)], False),
            ([boolean(False), boolean(False)], False),
            ([boolean(True), NULL], None),
        ],
    )
    def test_xor(self, visitor: ELMExpressionVisitor, operands: list[dict[str, Any]], expected: bool | None) -> None:
        assert visitor.evaluate({"type": "Xor", "operand": operands}) is expected

    @pytest.mark.parametrize(
        ("operands", "expected"),
        [
            ([boolean(False), boolean(False)], True),
            ([boolean(True), boolean(True)], True),
            ([boolean(True), boolean(False)], False),
            ([NULL, boolean(True)], True),
            ([NULL, boolean(False)], None),
        ],
    )
    def test_implies(
        self, visitor: ELMExpressionVisitor, operands: list[dict[str, Any]], expected: bool | None
    ) -> None:
        assert visitor.evaluate({"type": "Implies", "operand": operands}) is expected

    @pytest.mark.parametrize(
        ("node_type", "operand", "expected"),
        [
            ("IsTrue", boolean(True), True),
            ("IsTrue", boolean(False), False),
            ("IsTrue", NULL, False),
            ("IsFalse", boolean(False), True),
            ("IsFalse", boolean(True), False),
            ("IsFalse", NULL, False),
        ],
    )
    def test_is_true_and_is_false(
        self, visitor: ELMExpressionVisitor, node_type: str, operand: dict[str, Any], expected: bool
    ) -> None:
        assert visitor.evaluate({"type": node_type, "operand": operand}) is expected

    def test_and_of_two_nulls_is_null(self, visitor: ELMExpressionVisitor) -> None:
        assert visitor.evaluate({"type": "And", "operand": [NULL, NULL]}) is None

    def test_or_of_two_nulls_is_null(self, visitor: ELMExpressionVisitor) -> None:
        assert visitor.evaluate({"type": "Or", "operand": [NULL, NULL]}) is None


class TestConditional:
    """If, Case and Coalesce."""

    def test_if_without_else_is_null(self, visitor: ELMExpressionVisitor) -> None:
        assert visitor.evaluate({"type": "If", "condition": boolean(False), "then": integer(1)}) is None

    def test_case_with_comparand_matches_by_value(self, visitor: ELMExpressionVisitor) -> None:
        node = {
            "type": "Case",
            "comparand": integer(2),
            "caseItem": [{"when": integer(1), "then": string("one")}, {"when": integer(2), "then": string("two")}],
            "else": string("other"),
        }
        assert visitor.evaluate(node) == "two"

    def test_case_with_comparand_falls_through_to_else(self, visitor: ELMExpressionVisitor) -> None:
        node = {
            "type": "Case",
            "comparand": integer(9),
            "caseItem": [{"when": integer(1), "then": string("one")}],
            "else": string("other"),
        }
        assert visitor.evaluate(node) == "other"

    def test_case_without_else_is_null(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "Case", "caseItem": [{"when": boolean(False), "then": string("x")}]}
        assert visitor.evaluate(node) is None

    def test_coalesce_skips_empty_lists(self, visitor: ELMExpressionVisitor) -> None:
        assert visitor.evaluate({"type": "Coalesce", "operand": [elm_list(), integer(7)]}) == 7

    def test_coalesce_returns_non_empty_list(self, visitor: ELMExpressionVisitor) -> None:
        assert visitor.evaluate({"type": "Coalesce", "operand": [elm_list(integer(1)), integer(7)]}) == [1]


class TestStringOperators:
    """String handling operators."""

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            ({"type": "Concatenate", "operand": [string("a"), NULL]}, None),
            ({"type": "Combine", "source": elm_list(string("a"), string("b")), "separator": string("-")}, "a-b"),
            ({"type": "Combine", "source": elm_list(string("a"), string("b"))}, "ab"),
            ({"type": "Combine", "source": string("a")}, "a"),
            ({"type": "Combine", "source": NULL}, None),
            ({"type": "Split", "stringToSplit": string("a,b,c"), "separator": string(",")}, ["a", "b", "c"]),
            ({"type": "Split", "stringToSplit": string("abc")}, ["abc"]),
            ({"type": "Split", "stringToSplit": NULL, "separator": string(",")}, None),
            ({"type": "Length", "operand": elm_list(integer(1), integer(2))}, 2),
            ({"type": "Length", "operand": NULL}, None),
            ({"type": "Upper", "operand": NULL}, None),
            ({"type": "Lower", "operand": NULL}, None),
        ],
    )
    def test_string_operator(self, visitor: ELMExpressionVisitor, node: dict[str, Any], expected: Any) -> None:
        assert visitor.evaluate(node) == expected

    def test_combine_drops_null_entries(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "Combine", "source": elm_list(string("a"), NULL, string("b")), "separator": string(",")}
        assert visitor.evaluate(node) == "a,b"

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            (
                {"type": "Substring", "stringToSub": string("hello"), "startIndex": integer(1), "length": integer(3)},
                "ell",
            ),
            ({"type": "Substring", "stringToSub": string("hello"), "startIndex": integer(2)}, "llo"),
            ({"type": "Substring", "stringToSub": NULL, "startIndex": integer(0)}, None),
            ({"type": "Substring", "stringToSub": string("hello")}, None),
        ],
    )
    def test_substring_named_form(
        self, visitor: ELMExpressionVisitor, node: dict[str, Any], expected: str | None
    ) -> None:
        assert visitor.evaluate(node) == expected

    def test_substring_operand_form_without_length(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "Substring", "operand": [string("hello"), integer(2)]}
        assert visitor.evaluate(node) == "llo"

    @pytest.mark.parametrize("node_type", ["StartsWith", "EndsWith", "Matches", "PositionOf", "LastPositionOf"])
    def test_string_binary_propagates_null(self, visitor: ELMExpressionVisitor, node_type: str) -> None:
        assert visitor.evaluate({"type": node_type, "operand": [NULL, string("x")]}) is None

    def test_matches_finds_pattern(self, visitor: ELMExpressionVisitor) -> None:
        assert visitor.evaluate({"type": "Matches", "operand": [string("hello123"), string(r"\d+")]}) is True

    def test_replace_matches_substitutes_every_hit(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "ReplaceMatches", "operand": [string("a1b2"), string(r"\d"), string("#")]}
        assert visitor.evaluate(node) == "a#b#"

    @pytest.mark.parametrize(
        "operands",
        [[string("a"), string("b")], [NULL, string(r"\d"), string("#")]],
    )
    def test_replace_matches_returns_null(self, visitor: ELMExpressionVisitor, operands: list[dict[str, Any]]) -> None:
        assert visitor.evaluate({"type": "ReplaceMatches", "operand": operands}) is None

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            ({"type": "Indexer", "operand": [string("hello"), integer(1)]}, "e"),
            ({"type": "Indexer", "operand": [elm_list(integer(1), integer(2)), integer(0)]}, 1),
            ({"type": "Indexer", "operand": [elm_list(integer(1)), integer(9)]}, None),
            ({"type": "Indexer", "operand": [NULL, integer(0)]}, None),
            ({"type": "PositionOf", "operand": [string("lo"), string("hello")]}, 3),
            ({"type": "PositionOf", "operand": [string("z"), string("hello")]}, None),
            ({"type": "LastPositionOf", "operand": [string("l"), string("hello")]}, 3),
            ({"type": "LastPositionOf", "operand": [string("z"), string("hello")]}, None),
        ],
    )
    def test_indexing_and_position(self, visitor: ELMExpressionVisitor, node: dict[str, Any], expected: Any) -> None:
        assert visitor.evaluate(node) == expected


class TestCollectionOperators:
    """List membership, inclusion and shaping operators."""

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            ({"type": "First", "source": elm_list()}, None),
            ({"type": "First", "source": NULL}, None),
            ({"type": "First", "source": integer(1)}, None),
            ({"type": "Last", "source": elm_list()}, None),
            ({"type": "Last", "source": NULL}, None),
            ({"type": "IndexOf", "source": elm_list(integer(1), integer(2)), "element": integer(2)}, 1),
            ({"type": "IndexOf", "source": elm_list(integer(1)), "element": integer(9)}, -1),
            ({"type": "IndexOf", "source": NULL, "element": integer(1)}, None),
            ({"type": "IndexOf", "source": elm_list(integer(1)), "element": NULL}, None),
        ],
    )
    def test_positional_access(self, visitor: ELMExpressionVisitor, node: dict[str, Any], expected: Any) -> None:
        assert visitor.evaluate(node) == expected

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            ({"type": "Contains", "operand": [elm_list(integer(1), integer(2)), integer(2)]}, True),
            ({"type": "Contains", "operand": [elm_list(integer(1)), integer(2)]}, False),
            ({"type": "Contains", "operand": [interval(integer(1), integer(9)), integer(5)]}, True),
            ({"type": "Contains", "operand": [integer(1), integer(2)]}, None),
            ({"type": "Contains", "operand": [NULL, integer(2)]}, None),
            ({"type": "In", "operand": [integer(2), elm_list(integer(1), integer(2))]}, True),
            ({"type": "In", "operand": [integer(9), elm_list(integer(1))]}, False),
            ({"type": "In", "operand": [integer(5), interval(integer(1), integer(9))]}, True),
            ({"type": "In", "operand": [integer(2), NULL]}, None),
            ({"type": "In", "operand": [integer(2), integer(2)]}, None),
        ],
    )
    def test_membership(self, visitor: ELMExpressionVisitor, node: dict[str, Any], expected: Any) -> None:
        assert visitor.evaluate(node) == expected

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            ({"type": "Includes", "operand": [elm_list(integer(1), integer(2)), elm_list(integer(1))]}, True),
            ({"type": "Includes", "operand": [elm_list(integer(1)), elm_list(integer(2))]}, False),
            ({"type": "Includes", "operand": [integer(1), integer(2)]}, None),
            ({"type": "Includes", "operand": [NULL, elm_list(integer(1))]}, None),
            ({"type": "IncludedIn", "operand": [elm_list(integer(1)), elm_list(integer(1), integer(2))]}, True),
            ({"type": "IncludedIn", "operand": [elm_list(integer(9)), elm_list(integer(1))]}, False),
            ({"type": "IncludedIn", "operand": [integer(1), integer(2)]}, None),
            ({"type": "IncludedIn", "operand": [NULL, elm_list(integer(1))]}, None),
        ],
    )
    def test_inclusion(self, visitor: ELMExpressionVisitor, node: dict[str, Any], expected: Any) -> None:
        assert visitor.evaluate(node) == expected

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            ({"type": "ProperIncludes", "operand": [elm_list(integer(1), integer(2)), elm_list(integer(1))]}, True),
            ({"type": "ProperIncludes", "operand": [elm_list(integer(1)), elm_list(integer(1))]}, False),
            ({"type": "ProperIncludes", "operand": [elm_list(integer(1)), elm_list(integer(2))]}, False),
            ({"type": "ProperIncludes", "operand": [NULL, elm_list(integer(1))]}, None),
            ({"type": "ProperIncludedIn", "operand": [elm_list(integer(1)), elm_list(integer(1), integer(2))]}, True),
            ({"type": "ProperIncludedIn", "operand": [elm_list(integer(1)), elm_list(integer(1))]}, False),
            ({"type": "ProperIncludedIn", "operand": [elm_list(integer(9)), elm_list(integer(1))]}, False),
            ({"type": "ProperIncludedIn", "operand": [NULL, elm_list(integer(1))]}, None),
        ],
    )
    def test_proper_inclusion(self, visitor: ELMExpressionVisitor, node: dict[str, Any], expected: Any) -> None:
        assert visitor.evaluate(node) == expected

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            ({"type": "Distinct", "operand": elm_list(integer(1), integer(2), integer(1))}, [1, 2]),
            ({"type": "Distinct", "operand": integer(1)}, [1]),
            ({"type": "Distinct", "operand": NULL}, None),
            (
                {"type": "Flatten", "operand": elm_list(elm_list(integer(1), integer(2)), elm_list(integer(3)))},
                [1, 2, 3],
            ),
            ({"type": "Flatten", "operand": integer(1)}, [1]),
            ({"type": "Flatten", "operand": NULL}, None),
            ({"type": "ToList", "operand": integer(1)}, [1]),
            ({"type": "ToList", "operand": NULL}, []),
            ({"type": "ToList", "operand": elm_list(integer(1))}, [1]),
        ],
    )
    def test_list_shaping(self, visitor: ELMExpressionVisitor, node: dict[str, Any], expected: Any) -> None:
        assert visitor.evaluate(node) == expected

    def test_distinct_keeps_first_occurrence_of_unhashable_items(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "Distinct", "operand": elm_list(elm_list(integer(1)), elm_list(integer(1)))}
        assert visitor.evaluate(node) == [[1], [1]]

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            ({"type": "Exists", "operand": integer(1)}, True),
            ({"type": "Exists", "operand": NULL}, False),
            ({"type": "SingletonFrom", "operand": elm_list(integer(1))}, 1),
            ({"type": "SingletonFrom", "operand": elm_list()}, None),
            ({"type": "SingletonFrom", "operand": integer(4)}, 4),
            ({"type": "SingletonFrom", "operand": NULL}, None),
        ],
    )
    def test_existence(self, visitor: ELMExpressionVisitor, node: dict[str, Any], expected: Any) -> None:
        assert visitor.evaluate(node) == expected

    def test_singleton_from_multiple_elements_is_an_error(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "SingletonFrom", "operand": elm_list(integer(1), integer(2))}
        with pytest.raises(ELMExecutionError, match="Expected single element"):
            visitor.evaluate(node)


class TestAggregates:
    """Aggregate operators over a source list."""

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            ({"type": "Count", "source": elm_list(integer(1), NULL, integer(2))}, 2),
            ({"type": "Count", "source": NULL}, 0),
            ({"type": "Count", "source": integer(1)}, 1),
            ({"type": "Sum", "source": elm_list()}, None),
            ({"type": "Avg", "source": elm_list()}, None),
            ({"type": "Min", "source": elm_list()}, None),
            ({"type": "Max", "source": elm_list()}, None),
            ({"type": "Median", "source": elm_list(integer(1), integer(3), integer(2))}, 2),
            ({"type": "Median", "source": elm_list()}, None),
            ({"type": "Mode", "source": elm_list(integer(1), integer(1), integer(2))}, 1),
            ({"type": "Mode", "source": elm_list()}, None),
            ({"type": "Variance", "source": elm_list(integer(1), integer(2), integer(3))}, Decimal("1.0")),
            ({"type": "Variance", "source": elm_list(integer(1))}, None),
            ({"type": "PopulationVariance", "source": elm_list(integer(2), integer(4))}, Decimal("1.0")),
            ({"type": "PopulationVariance", "source": elm_list()}, None),
            ({"type": "StdDev", "source": elm_list(integer(2), integer(4))}, Decimal(str(2**0.5))),
            ({"type": "StdDev", "source": elm_list(integer(1))}, None),
            ({"type": "PopulationStdDev", "source": elm_list(integer(2), integer(4))}, Decimal("1.0")),
            ({"type": "PopulationStdDev", "source": elm_list()}, None),
            ({"type": "AllTrue", "source": elm_list(boolean(True), boolean(True))}, True),
            ({"type": "AllTrue", "source": elm_list(boolean(True), boolean(False))}, False),
            ({"type": "AnyTrue", "source": elm_list(boolean(False), boolean(True))}, True),
            ({"type": "AnyTrue", "source": elm_list(boolean(False))}, False),
            ({"type": "Product", "source": elm_list(integer(2), integer(3), integer(4))}, 24),
            ({"type": "Product", "source": elm_list()}, None),
            ({"type": "GeometricMean", "source": elm_list(integer(1), integer(4))}, Decimal("2.0")),
            ({"type": "GeometricMean", "source": elm_list()}, None),
        ],
    )
    def test_aggregate(self, visitor: ELMExpressionVisitor, node: dict[str, Any], expected: Any) -> None:
        assert visitor.evaluate(node) == expected

    def test_mode_without_a_unique_winner_returns_the_first_value(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "Mode", "source": elm_list(string("b"), string("a"))}
        assert visitor.evaluate(node) == "b"

    def test_geometric_mean_ignores_non_positive_values(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "GeometricMean", "source": elm_list(integer(0), integer(1), integer(4))}
        assert visitor.evaluate(node) == Decimal("2.0")


class TestSetOperations:
    """Union, Intersect and Except."""

    def test_union_concatenates_without_deduplicating(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "Union", "operand": [elm_list(integer(1), integer(2)), elm_list(integer(2), integer(3))]}
        assert visitor.evaluate(node) == [1, 2, 2, 3]

    @pytest.mark.parametrize(
        ("operands", "expected"),
        [([integer(1), elm_list(integer(2))], [1, 2]), ([NULL, elm_list(integer(2))], [2])],
    )
    def test_union_promotes_scalars_and_skips_nulls(
        self, visitor: ELMExpressionVisitor, operands: list[dict[str, Any]], expected: list[int]
    ) -> None:
        assert visitor.evaluate({"type": "Union", "operand": operands}) == expected

    def test_intersect_keeps_shared_members(self, visitor: ELMExpressionVisitor) -> None:
        node = {
            "type": "Intersect",
            "operand": [elm_list(integer(1), integer(2), integer(3)), elm_list(integer(2), integer(3), integer(4))],
        }
        assert sorted(visitor.evaluate(node)) == [2, 3]

    @pytest.mark.parametrize(
        ("operands", "expected"),
        [
            ([elm_list(integer(1))], []),
            ([NULL, elm_list(integer(1))], []),
            ([elm_list(integer(1)), NULL], []),
            ([integer(1), integer(1)], [1]),
        ],
    )
    def test_intersect_edge_cases(
        self, visitor: ELMExpressionVisitor, operands: list[dict[str, Any]], expected: list[int]
    ) -> None:
        assert visitor.evaluate({"type": "Intersect", "operand": operands}) == expected

    @pytest.mark.parametrize(
        ("operands", "expected"),
        [
            ([elm_list(integer(1), integer(2), integer(3)), elm_list(integer(2))], [1, 3]),
            ([elm_list(integer(1))], []),
            ([NULL, elm_list(integer(1))], []),
            ([integer(1), integer(2)], [1]),
            ([elm_list(integer(1)), NULL], [1]),
        ],
    )
    def test_except(self, visitor: ELMExpressionVisitor, operands: list[dict[str, Any]], expected: list[int]) -> None:
        assert visitor.evaluate({"type": "Except", "operand": operands}) == expected


class TestTypeOperators:
    """As, Is and the To*/ConvertsTo* families."""

    @pytest.mark.parametrize(
        ("operand", "target", "expected"),
        [
            (decimal("3.7"), "Integer", 3),
            (string("42"), "Integer", 42),
            (string("xx"), "Integer", None),
            (integer(3), "Decimal", Decimal("3")),
            (string("2.5"), "Decimal", Decimal("2.5")),
            (boolean(True), "String", "true"),
            (boolean(False), "String", "false"),
            (integer(3), "String", "3"),
            (date_literal("2024-01-02"), "String", "2024-01-02"),
            (string("yes"), "Boolean", True),
            (string("no"), "Boolean", False),
            (integer(0), "Boolean", False),
            (integer(1), "Boolean", True),
            (string("maybe"), "Boolean", None),
            (boolean(True), "Boolean", True),
            (datetime_literal("2024-05-06T01:02:03"), "Date", FHIRDate(year=2024, month=5, day=6)),
            (string("2024-05-06"), "Date", FHIRDate(year=2024, month=5, day=6)),
            (integer(1), "Date", None),
            (date_literal("2024-05-06"), "DateTime", FHIRDateTime(year=2024, month=5, day=6)),
            (integer(1), "DateTime", None),
            (string("10:30:00"), "Time", FHIRTime(hour=10, minute=30, second=0)),
            (integer(1), "Time", None),
            (integer(3), "Quantity", None),
            (integer(1), "Concept", None),
            (NULL, "Integer", None),
        ],
    )
    def test_as_casts(self, visitor: ELMExpressionVisitor, operand: dict[str, Any], target: str, expected: Any) -> None:
        node = {"type": "As", "operand": operand, "asTypeSpecifier": named_type(target)}
        assert visitor.evaluate(node) == expected

    def test_as_keeps_a_quantity_unchanged(self, visitor: ELMExpressionVisitor) -> None:
        node = {
            "type": "As",
            "operand": {"type": "Quantity", "value": "3", "unit": "mg"},
            "asTypeSpecifier": named_type("Quantity"),
        }
        assert visitor.evaluate(node) == Quantity(value=Decimal("3"), unit="mg")

    def test_as_builds_a_code_from_a_mapping(self, visitor: ELMExpressionVisitor) -> None:
        source = {
            "type": "Instance",
            "classType": "Coding",
            "element": [{"name": "code", "value": string("c1")}, {"name": "system", "value": string("s1")}],
        }
        node = {"type": "As", "operand": source, "asTypeSpecifier": named_type("Code")}
        assert visitor.evaluate(node) == CQLCode(code="c1", system="s1")

    def test_as_wraps_a_code_into_a_concept(self, visitor: ELMExpressionVisitor) -> None:
        source = {"type": "Code", "code": "c", "system": string("s"), "display": "d"}
        node = {"type": "As", "operand": source, "asTypeSpecifier": named_type("Concept")}
        assert visitor.evaluate(node) == CQLConcept(codes=(CQLCode(code="c", system="s", display="d"),), display="d")

    def test_as_list_promotes_a_singleton(self, visitor: ELMExpressionVisitor) -> None:
        assert visitor.evaluate({"type": "As", "operand": integer(1), "asType": f"{ELM_TYPE}List"}) == [1]

    def test_as_strict_raises_when_the_cast_fails(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "As", "operand": string("xx"), "asTypeSpecifier": named_type("Integer"), "strict": True}
        with pytest.raises(ELMExecutionError, match="Cannot cast"):
            visitor.evaluate(node)

    @pytest.mark.parametrize("target", ["{http://hl7.org/fhir}Patient", "{http://hl7.org/fhir}Resource"])
    def test_as_accepts_matching_and_generic_resource_targets(self, visitor: ELMExpressionVisitor, target: str) -> None:
        source = {"type": "Instance", "classType": "{http://hl7.org/fhir}Patient", "element": []}
        assert visitor.evaluate({"type": "As", "operand": source, "asType": target}) == {"resourceType": "Patient"}

    @pytest.mark.parametrize(
        ("operand", "is_type", "expected"),
        [
            (integer(1), "Integer", True),
            (boolean(True), "Integer", False),
            (decimal("1.5"), "Decimal", True),
            (integer(1), "Decimal", False),
            (string("s"), "String", True),
            (integer(1), "String", False),
            (boolean(True), "Boolean", True),
            (integer(1), "Boolean", False),
            (date_literal("2024-01-01"), "Date", True),
            (integer(1), "Date", False),
            (datetime_literal("2024-01-01T00:00:00"), "DateTime", True),
            (integer(1), "DateTime", False),
            (NULL, "Integer", False),
        ],
    )
    def test_is_type_check(
        self, visitor: ELMExpressionVisitor, operand: dict[str, Any], is_type: str, expected: bool
    ) -> None:
        node = {"type": "Is", "operand": operand, "isType": f"{ELM_TYPE}{is_type}"}
        assert visitor.evaluate(node) is expected

    def test_is_defaults_to_true_for_unrecognised_types(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "Is", "operand": integer(1), "isType": "{http://hl7.org/fhir}Patient"}
        assert visitor.evaluate(node) is True

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            ({"type": "ToBoolean", "operand": string("Y")}, True),
            ({"type": "ToBoolean", "operand": string("N")}, False),
            ({"type": "ToBoolean", "operand": string("maybe")}, None),
            ({"type": "ToBoolean", "operand": integer(2)}, True),
            ({"type": "ToBoolean", "operand": boolean(False)}, False),
            ({"type": "ToBoolean", "operand": elm_list(integer(1))}, None),
            ({"type": "ToBoolean", "operand": NULL}, None),
            ({"type": "ToInteger", "operand": string("42")}, 42),
            ({"type": "ToInteger", "operand": string("x")}, None),
            ({"type": "ToInteger", "operand": NULL}, None),
            ({"type": "ToLong", "operand": string("42")}, 42),
            ({"type": "ToDecimal", "operand": string("2.5")}, Decimal("2.5")),
            ({"type": "ToDecimal", "operand": NULL}, None),
            ({"type": "ToString", "operand": integer(5)}, "5"),
            ({"type": "ToString", "operand": NULL}, None),
            ({"type": "ToDateTime", "operand": integer(1)}, None),
            ({"type": "ToDateTime", "operand": NULL}, None),
            ({"type": "ToDate", "operand": integer(1)}, None),
            ({"type": "ToDate", "operand": NULL}, None),
            ({"type": "ToTime", "operand": string("10:30:00")}, "10:30:00"),
            ({"type": "ToTime", "operand": NULL}, None),
            ({"type": "ToQuantity", "operand": string("x")}, None),
            ({"type": "ToQuantity", "operand": NULL}, None),
            ({"type": "ToConcept", "operand": integer(1)}, None),
            ({"type": "ToConcept", "operand": NULL}, None),
        ],
    )
    def test_conversion(self, visitor: ELMExpressionVisitor, node: dict[str, Any], expected: Any) -> None:
        assert visitor.evaluate(node) == expected

    def test_to_datetime_parses_a_string(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "ToDateTime", "operand": string("2024-01-02T03:04:05")}
        assert visitor.evaluate(node) == FHIRDateTime(year=2024, month=1, day=2, hour=3, minute=4, second=5)

    def test_to_date_narrows_a_datetime(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "ToDate", "operand": datetime_literal("2024-01-02T03:04:05")}
        assert visitor.evaluate(node) == FHIRDate(year=2024, month=1, day=2)

    def test_to_quantity_gives_a_dimensionless_unit(self, visitor: ELMExpressionVisitor) -> None:
        assert visitor.evaluate({"type": "ToQuantity", "operand": integer(5)}) == Quantity(value=Decimal("5"), unit="1")

    def test_to_concept_wraps_a_code(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "ToConcept", "operand": {"type": "Code", "code": "c", "system": string("s")}}
        assert visitor.evaluate(node) == CQLConcept(codes=(CQLCode(code="c", system="s"),))

    @pytest.mark.parametrize(
        ("node_type", "operand", "expected"),
        [
            ("ConvertsToBoolean", string("true"), True),
            ("ConvertsToBoolean", string("zzz"), False),
            ("ConvertsToInteger", string("4"), True),
            ("ConvertsToInteger", string("x"), False),
            ("ConvertsToDecimal", integer(4), True),
            ("ConvertsToDecimal", NULL, False),
            ("ConvertsToString", integer(4), True),
            ("ConvertsToString", NULL, False),
            ("ConvertsToDateTime", string("2024-01-02T00:00:00"), True),
            ("ConvertsToDateTime", integer(1), False),
            ("ConvertsToDate", string("2024-01-02"), True),
            ("ConvertsToDate", integer(1), False),
            ("ConvertsToTime", string("10:00:00"), True),
            ("ConvertsToTime", NULL, False),
            ("ConvertsToQuantity", integer(3), True),
            ("ConvertsToQuantity", string("x"), False),
        ],
    )
    def test_converts_to(
        self, visitor: ELMExpressionVisitor, node_type: str, operand: dict[str, Any], expected: bool
    ) -> None:
        assert visitor.evaluate({"type": node_type, "operand": operand}) is expected


class TestDateTimeOperators:
    """Date and time construction, extraction and duration."""

    def test_today_returns_the_current_date(self, visitor: ELMExpressionVisitor) -> None:
        today = date.today()
        assert visitor.evaluate({"type": "Today"}) == FHIRDate(year=today.year, month=today.month, day=today.day)

    def test_now_carries_the_current_date(self, visitor: ELMExpressionVisitor) -> None:
        result = visitor.evaluate({"type": "Now"})
        today = date.today()
        assert isinstance(result, FHIRDateTime)
        assert (result.year, result.month, result.day) == (today.year, today.month, today.day)

    def test_time_of_day_is_a_clock_string(self, visitor: ELMExpressionVisitor) -> None:
        result = visitor.evaluate({"type": "TimeOfDay"})
        hours, minutes, seconds = result.split(":")
        assert 0 <= int(hours) <= 23
        assert 0 <= int(minutes) <= 59
        assert 0 <= int(seconds) <= 59

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            (
                {"type": "Date", "year": integer(2024), "month": integer(3), "day": integer(4)},
                FHIRDate(year=2024, month=3, day=4),
            ),
            ({"type": "Date", "year": integer(2024)}, FHIRDate(year=2024)),
            ({"type": "Date"}, None),
        ],
    )
    def test_date_constructor(
        self, visitor: ELMExpressionVisitor, node: dict[str, Any], expected: FHIRDate | None
    ) -> None:
        assert visitor.evaluate(node) == expected

    def test_datetime_constructor(self, visitor: ELMExpressionVisitor) -> None:
        node = {
            "type": "DateTime",
            "year": integer(2024),
            "month": integer(3),
            "day": integer(4),
            "hour": integer(5),
            "minute": integer(6),
            "second": integer(7),
        }
        assert visitor.evaluate(node) == FHIRDateTime(year=2024, month=3, day=4, hour=5, minute=6, second=7)

    def test_datetime_constructor_without_year_is_null(self, visitor: ELMExpressionVisitor) -> None:
        assert visitor.evaluate({"type": "DateTime"}) is None

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            ({"type": "Time", "hour": integer(10), "minute": integer(30), "second": integer(15)}, "10:30:15"),
            ({"type": "Time", "hour": integer(10), "minute": integer(30)}, "10:30"),
            ({"type": "Time", "hour": integer(10)}, "10"),
            ({"type": "Time"}, None),
        ],
    )
    def test_time_constructor(self, visitor: ELMExpressionVisitor, node: dict[str, Any], expected: str | None) -> None:
        assert visitor.evaluate(node) == expected

    @pytest.mark.parametrize(
        ("precision", "left", "right", "expected"),
        [
            ("Year", date_literal("2000-01-01"), date_literal("2000-12-31"), 0),
            ("Year", date_literal("2000-01-01"), date_literal("2001-01-01"), 1),
            ("Month", date_literal("2000-01-15"), date_literal("2000-03-14"), 1),
            ("Week", date_literal("2024-01-01"), date_literal("2024-01-15"), 2),
            ("Day", date_literal("2024-01-01"), date_literal("2024-01-15"), 14),
            ("Hour", datetime_literal("2024-01-01T00:00:00"), datetime_literal("2024-01-01T05:30:00"), 5),
            ("Minute", datetime_literal("2024-01-01T00:00:00"), datetime_literal("2024-01-01T05:30:00"), 330),
            ("Second", datetime_literal("2024-01-01T00:00:00"), datetime_literal("2024-01-01T00:01:00"), 60),
            ("Millisecond", datetime_literal("2024-01-01T00:00:00"), datetime_literal("2024-01-01T00:00:01"), 1000),
            ("Fortnight", date_literal("2024-01-01"), date_literal("2024-01-02"), None),
            ("Day", NULL, date_literal("2024-01-01"), None),
            ("Day", integer(1), integer(2), None),
            ("Day", date_literal("2024"), date_literal("2024-01-11"), 10),
        ],
    )
    def test_duration_between(
        self,
        visitor: ELMExpressionVisitor,
        precision: str,
        left: dict[str, Any],
        right: dict[str, Any],
        expected: int | None,
    ) -> None:
        node = {"type": "DurationBetween", "precision": precision, "operand": [left, right]}
        assert visitor.evaluate(node) == expected

    def test_difference_between_uses_the_same_calculation(self, visitor: ELMExpressionVisitor) -> None:
        node = {
            "type": "DifferenceBetween",
            "precision": "Day",
            "operand": [date_literal("2024-01-01"), date_literal("2024-01-15")],
        }
        assert visitor.evaluate(node) == 14

    def test_duration_between_python_dates(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "DurationBetween", "precision": "Day", "operand": [date(2024, 1, 1), date(2024, 1, 8)]}
        assert visitor.evaluate(node) == 7

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            (
                {"type": "DateFrom", "operand": datetime_literal("2024-01-02T03:04:05")},
                FHIRDate(year=2024, month=1, day=2),
            ),
            ({"type": "DateFrom", "operand": date_literal("2024-01-02")}, FHIRDate(year=2024, month=1, day=2)),
            ({"type": "DateFrom", "operand": integer(1)}, None),
            ({"type": "DateFrom", "operand": NULL}, None),
            ({"type": "TimeFrom", "operand": datetime_literal("2024-01-02T03:04:05")}, "03:04:05"),
            ({"type": "TimeFrom", "operand": datetime_literal("2024-01-02")}, None),
            ({"type": "TimeFrom", "operand": integer(1)}, None),
            ({"type": "TimeFrom", "operand": NULL}, None),
            ({"type": "TimezoneOffsetFrom", "operand": datetime_literal("2024-01-02T03:04:05")}, None),
            ({"type": "TimezoneOffsetFrom", "operand": NULL}, None),
        ],
    )
    def test_extraction(self, visitor: ELMExpressionVisitor, node: dict[str, Any], expected: Any) -> None:
        assert visitor.evaluate(node) == expected

    @pytest.mark.parametrize(
        ("precision", "expected"),
        [("Year", 2024), ("Month", 3), ("Day", 4), ("Hour", 5), ("Minute", 6), ("Second", 7), ("Era", None)],
    )
    def test_datetime_component_from(self, visitor: ELMExpressionVisitor, precision: str, expected: int | None) -> None:
        node = {
            "type": "DateTimeComponentFrom",
            "precision": precision,
            "operand": datetime_literal("2024-03-04T05:06:07"),
        }
        assert visitor.evaluate(node) == expected

    def test_datetime_component_from_null_operand(self, visitor: ELMExpressionVisitor) -> None:
        assert visitor.evaluate({"type": "DateTimeComponentFrom", "precision": "Year", "operand": NULL}) is None

    @pytest.mark.parametrize(
        ("node_type", "left", "right", "expected"),
        [
            ("SameAs", date_literal("2024-01-01"), date_literal("2024-01-01"), True),
            ("SameAs", date_literal("2024-01-01"), date_literal("2024-01-02"), False),
            ("SameOrBefore", date_literal("2024-01-01"), date_literal("2024-01-02"), True),
            ("SameOrAfter", date_literal("2024-01-03"), date_literal("2024-01-02"), True),
        ],
    )
    def test_concurrent_comparisons(
        self,
        visitor: ELMExpressionVisitor,
        node_type: str,
        left: dict[str, Any],
        right: dict[str, Any],
        expected: bool,
    ) -> None:
        assert visitor.evaluate({"type": node_type, "operand": [left, right]}) is expected


class TestIntervalOperators:
    """Interval bounds, relations and reshaping."""

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            ({"type": "Start", "operand": NULL}, None),
            ({"type": "Start", "operand": integer(1)}, None),
            ({"type": "End", "operand": NULL}, None),
            ({"type": "End", "operand": integer(1)}, None),
            ({"type": "Width", "operand": interval(integer(1), integer(10))}, 9),
            ({"type": "Width", "operand": interval(None, integer(10))}, None),
            ({"type": "Width", "operand": integer(1)}, None),
            ({"type": "Width", "operand": NULL}, None),
            ({"type": "Size", "operand": interval(integer(1), integer(10))}, 9),
            ({"type": "PointFrom", "operand": interval(integer(5), integer(5))}, 5),
            ({"type": "PointFrom", "operand": interval(integer(1), integer(5))}, None),
            ({"type": "PointFrom", "operand": integer(1)}, None),
            ({"type": "PointFrom", "operand": NULL}, None),
        ],
    )
    def test_bounds(self, visitor: ELMExpressionVisitor, node: dict[str, Any], expected: Any) -> None:
        assert visitor.evaluate(node) == expected

    @pytest.mark.parametrize(
        ("node_type", "left", "right", "expected"),
        [
            ("Overlaps", interval(integer(1), integer(5)), interval(integer(3), integer(8)), True),
            ("Overlaps", interval(integer(1), integer(2)), interval(integer(5), integer(8)), False),
            ("OverlapsBefore", interval(integer(1), integer(5)), interval(integer(3), integer(8)), True),
            ("OverlapsAfter", interval(integer(3), integer(8)), interval(integer(1), integer(5)), True),
            ("Meets", interval(integer(1), integer(5)), interval(integer(5), integer(9), low_closed=False), True),
            ("MeetsBefore", interval(integer(1), integer(5)), interval(integer(5), integer(9), low_closed=False), True),
            ("MeetsAfter", interval(integer(5), integer(9), low_closed=False), interval(integer(1), integer(5)), True),
            ("Starts", interval(integer(1), integer(3)), interval(integer(1), integer(9)), True),
            ("Ends", interval(integer(5), integer(9)), interval(integer(1), integer(9)), True),
        ],
    )
    def test_interval_relations(
        self,
        visitor: ELMExpressionVisitor,
        node_type: str,
        left: dict[str, Any],
        right: dict[str, Any],
        expected: bool,
    ) -> None:
        assert visitor.evaluate({"type": node_type, "operand": [left, right]}) is expected

    @pytest.mark.parametrize(
        "node_type",
        ["Overlaps", "OverlapsBefore", "OverlapsAfter", "Meets", "MeetsBefore", "MeetsAfter", "Starts", "Ends"],
    )
    def test_interval_relations_reject_points(self, visitor: ELMExpressionVisitor, node_type: str) -> None:
        assert visitor.evaluate({"type": node_type, "operand": [integer(1), integer(2)]}) is None

    @pytest.mark.parametrize(
        "node_type",
        ["Overlaps", "OverlapsBefore", "OverlapsAfter", "Meets", "MeetsBefore", "MeetsAfter", "Starts", "Ends"],
    )
    def test_interval_relations_propagate_null(self, visitor: ELMExpressionVisitor, node_type: str) -> None:
        node = {"type": node_type, "operand": [NULL, interval(integer(1), integer(2))]}
        assert visitor.evaluate(node) is None

    @pytest.mark.parametrize(
        ("left", "right", "expected"),
        [
            (interval(integer(1), integer(2)), interval(integer(5), integer(9)), True),
            (interval(integer(5), integer(9)), interval(integer(1), integer(2)), False),
            (interval(integer(1), integer(2)), integer(5), True),
            (integer(0), interval(integer(1), integer(2)), True),
            (integer(0), integer(2), True),
            (integer(5), integer(2), False),
            (interval(integer(1), None), interval(integer(5), integer(9)), None),
            (interval(integer(1), None), integer(5), None),
            (integer(0), interval(None, integer(9)), None),
            (NULL, integer(1), None),
        ],
    )
    def test_before(
        self, visitor: ELMExpressionVisitor, left: dict[str, Any], right: dict[str, Any], expected: bool | None
    ) -> None:
        assert visitor.evaluate({"type": "Before", "operand": [left, right]}) is expected

    @pytest.mark.parametrize(
        ("left", "right", "expected"),
        [
            (interval(integer(5), integer(9)), interval(integer(1), integer(2)), True),
            (interval(integer(1), integer(2)), interval(integer(5), integer(9)), False),
            (interval(integer(5), integer(9)), integer(1), True),
            (integer(10), interval(integer(1), integer(2)), True),
            (integer(10), integer(2), True),
            (integer(1), integer(2), False),
            (interval(None, integer(9)), interval(integer(1), integer(2)), None),
            (interval(None, integer(9)), integer(1), None),
            (integer(10), interval(integer(1), None), None),
            (NULL, integer(1), None),
        ],
    )
    def test_after(
        self, visitor: ELMExpressionVisitor, left: dict[str, Any], right: dict[str, Any], expected: bool | None
    ) -> None:
        assert visitor.evaluate({"type": "After", "operand": [left, right]}) is expected

    def test_collapse_merges_overlapping_intervals(self, visitor: ELMExpressionVisitor) -> None:
        node = {
            "type": "Collapse",
            "operand": elm_list(
                interval(integer(1), integer(5)),
                interval(integer(3), integer(8)),
                interval(integer(20), integer(25)),
            ),
        }
        assert visitor.evaluate(node) == [
            CQLInterval(low=1, high=8, low_closed=True, high_closed=True),
            CQLInterval(low=20, high=25, low_closed=True, high_closed=True),
        ]

    def test_collapse_accepts_a_single_interval(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "Collapse", "operand": interval(integer(1), integer(5))}
        assert visitor.evaluate(node) == [CQLInterval(low=1, high=5, low_closed=True, high_closed=True)]

    @pytest.mark.parametrize("operand", [NULL, integer(1), elm_list(), elm_list(integer(1))])
    def test_collapse_without_intervals_is_empty(self, visitor: ELMExpressionVisitor, operand: dict[str, Any]) -> None:
        assert visitor.evaluate({"type": "Collapse", "operand": operand}) == []

    def test_expand_splits_an_integer_interval_by_step(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "Expand", "operand": interval(integer(1), integer(6)), "per": integer(2)}
        assert visitor.evaluate(node) == [
            CQLInterval(low=1, high=2),
            CQLInterval(low=3, high=4),
            CQLInterval(low=5, high=6),
        ]

    def test_expand_defaults_to_unit_steps(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "Expand", "operand": interval(integer(1), integer(3))}
        assert visitor.evaluate(node) == [
            CQLInterval(low=1, high=1),
            CQLInterval(low=2, high=2),
            CQLInterval(low=3, high=3),
        ]

    def test_expand_honours_open_bounds(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "Expand", "operand": interval(integer(1), integer(4), low_closed=False, high_closed=False)}
        assert visitor.evaluate(node) == [CQLInterval(low=2, high=2), CQLInterval(low=3, high=3)]

    def test_expand_reads_a_quantity_step(self, visitor: ELMExpressionVisitor) -> None:
        node = {
            "type": "Expand",
            "operand": interval(integer(1), integer(4)),
            "per": {"type": "Quantity", "value": "2", "unit": "1"},
        }
        assert visitor.evaluate(node) == [CQLInterval(low=1, high=2), CQLInterval(low=3, high=4)]

    def test_expand_walks_a_date_interval(self, visitor: ELMExpressionVisitor) -> None:
        node = {
            "type": "Expand",
            "operand": interval(date_literal("2024-01-01"), date_literal("2024-01-04")),
            "per": integer(2),
        }
        assert visitor.evaluate(node) == [
            CQLInterval(low=FHIRDate(year=2024, month=1, day=1), high=FHIRDate(year=2024, month=1, day=2)),
            CQLInterval(low=FHIRDate(year=2024, month=1, day=3), high=FHIRDate(year=2024, month=1, day=4)),
        ]

    def test_expand_walks_a_decimal_interval(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "Expand", "operand": interval(decimal("1.0"), decimal("3.0"))}
        assert visitor.evaluate(node) == [
            CQLInterval(low=Decimal("1.0"), high=Decimal("1.0")),
            CQLInterval(low=Decimal("2.0"), high=Decimal("2.0")),
            CQLInterval(low=Decimal("3.0"), high=Decimal("3.0")),
        ]

    def test_expand_over_a_list_of_intervals(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "Expand", "operand": elm_list(interval(integer(1), integer(2)))}
        assert visitor.evaluate(node) == [CQLInterval(low=1, high=1), CQLInterval(low=2, high=2)]

    @pytest.mark.parametrize("operand", [NULL, integer(1)])
    def test_expand_without_an_interval_is_empty(self, visitor: ELMExpressionVisitor, operand: dict[str, Any]) -> None:
        assert visitor.evaluate({"type": "Expand", "operand": operand}) == []

    @pytest.mark.parametrize(
        "operand",
        [interval(integer(1), None), interval(string("a"), string("z"))],
    )
    def test_expand_returns_intervals_it_cannot_walk_unchanged(
        self, visitor: ELMExpressionVisitor, operand: dict[str, Any]
    ) -> None:
        result = visitor.evaluate({"type": "Expand", "operand": operand})
        assert result == [visitor.evaluate(operand)]


class TestIterationOperators:
    """ForEach, Repeat, Filter and Times."""

    def test_for_each_evaluates_the_element_expression_per_item(self, visitor: ELMExpressionVisitor) -> None:
        node = {
            "type": "ForEach",
            "source": elm_list(integer(1), integer(2)),
            "element": {"type": "Multiply", "operand": [{"type": "AliasRef", "name": "$this"}, integer(10)]},
        }
        assert visitor.evaluate(node) == [10, 20]

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            ({"type": "ForEach", "source": elm_list(integer(1), integer(2))}, [1, 2]),
            ({"type": "ForEach", "source": NULL}, []),
            ({"type": "ForEach", "source": integer(3)}, [3]),
            ({"type": "Repeat", "source": elm_list(integer(1))}, [1]),
        ],
    )
    def test_for_each_edge_cases(
        self, visitor: ELMExpressionVisitor, node: dict[str, Any], expected: list[int]
    ) -> None:
        assert visitor.evaluate(node) == expected

    def test_filter_keeps_items_whose_condition_is_true(self, visitor: ELMExpressionVisitor) -> None:
        node = {
            "type": "Filter",
            "source": elm_list(integer(1), integer(2), integer(3)),
            "condition": {"type": "Greater", "operand": [{"type": "AliasRef", "name": "$this"}, integer(1)]},
        }
        assert visitor.evaluate(node) == [2, 3]

    @pytest.mark.parametrize(
        ("source", "expected"),
        [(NULL, []), (integer(3), [3])],
    )
    def test_filter_edge_cases(
        self, visitor: ELMExpressionVisitor, source: dict[str, Any], expected: list[int]
    ) -> None:
        node = {"type": "Filter", "source": source, "condition": boolean(True)}
        assert visitor.evaluate(node) == expected

    @pytest.mark.parametrize(
        ("operands", "expected"),
        [
            ([elm_list(integer(1), integer(2)), elm_list(string("a"))], [[1, "a"], [2, "a"]]),
            ([], []),
            ([NULL, elm_list(integer(1))], []),
            ([integer(1), elm_list(string("a"))], [[1, "a"]]),
        ],
    )
    def test_times_builds_the_cartesian_product(
        self, visitor: ELMExpressionVisitor, operands: list[dict[str, Any]], expected: list[list[Any]]
    ) -> None:
        assert visitor.evaluate({"type": "Times", "operand": operands}) == expected


class TestMessage:
    """The Message expression logs and passes the source through."""

    @pytest.mark.parametrize("severity", ["Trace", "Message", "Warning", "Error"])
    def test_message_returns_its_source_at_every_severity(self, visitor: ELMExpressionVisitor, severity: str) -> None:
        node = {
            "type": "Message",
            "source": integer(5),
            "condition": boolean(True),
            "code": string("c1"),
            "severity": string(severity),
            "message": string("careful"),
        }
        assert visitor.evaluate(node) == 5

    def test_message_logs_the_code_and_text(
        self, visitor: ELMExpressionVisitor, caplog: pytest.LogCaptureFixture
    ) -> None:
        node = {
            "type": "Message",
            "source": integer(5),
            "condition": boolean(True),
            "code": string("c1"),
            "severity": string("Warning"),
            "message": string("careful"),
        }
        with caplog.at_level("DEBUG", logger="dhis2w_fhir_engine.cql.message"):
            visitor.evaluate(node)
        assert "[c1] careful" in caplog.text

    def test_message_stays_silent_when_the_condition_is_false(
        self, visitor: ELMExpressionVisitor, caplog: pytest.LogCaptureFixture
    ) -> None:
        node = {"type": "Message", "source": integer(5), "condition": boolean(False), "message": string("hidden")}
        with caplog.at_level("DEBUG", logger="dhis2w_fhir_engine.cql.message"):
            assert visitor.evaluate(node) == 5
        assert "hidden" not in caplog.text


class TestClinicalOperators:
    """Terminology references and age calculation."""

    @pytest.fixture
    def clinical_visitor(self) -> ELMExpressionVisitor:
        library = ELMLoader.parse(
            {
                "library": {
                    "identifier": {"id": "Clinical"},
                    "codeSystems": [{"name": "LOINC", "id": "http://loinc.org"}],
                    "valueSets": [{"name": "Diabetes", "id": "http://example.org/vs/diabetes"}],
                    "codes": [
                        {
                            "name": "BP",
                            "id": "55284-4",
                            "display": "Blood pressure",
                            "codeSystem": {"name": "LOINC"},
                        }
                    ],
                    "concepts": [{"name": "BPConcept", "display": "BP concept", "code": [{"name": "BP"}]}],
                }
            }
        )
        visitor = ELMExpressionVisitor(CQLContext())
        visitor.set_library(library)
        return visitor

    def test_code_ref_resolves_the_code_system_url(self, clinical_visitor: ELMExpressionVisitor) -> None:
        result = clinical_visitor.evaluate({"type": "CodeRef", "name": "BP"})
        assert result == CQLCode(code="55284-4", system="http://loinc.org", display="Blood pressure")

    def test_concept_ref_resolves_its_member_codes(self, clinical_visitor: ELMExpressionVisitor) -> None:
        result = clinical_visitor.evaluate({"type": "ConceptRef", "name": "BPConcept"})
        expected_code = CQLCode(code="55284-4", system="http://loinc.org", display="Blood pressure")
        assert result == CQLConcept(codes=(expected_code,), display="BP concept")

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            ({"type": "CodeSystemRef", "name": "LOINC"}, "http://loinc.org"),
            ({"type": "CodeSystemRef", "name": "Ghost"}, None),
            ({"type": "CodeSystemRef"}, None),
            ({"type": "ValueSetRef", "name": "Diabetes"}, "http://example.org/vs/diabetes"),
            ({"type": "ValueSetRef", "name": "Ghost"}, None),
            ({"type": "ValueSetRef"}, None),
            ({"type": "CodeRef", "name": "Ghost"}, None),
            ({"type": "CodeRef"}, None),
            ({"type": "ConceptRef", "name": "Ghost"}, None),
            ({"type": "ConceptRef"}, None),
        ],
    )
    def test_terminology_reference_lookups(
        self, clinical_visitor: ELMExpressionVisitor, node: dict[str, Any], expected: Any
    ) -> None:
        assert clinical_visitor.evaluate(node) == expected

    @pytest.mark.parametrize(
        "node_type",
        ["CodeRef", "CodeSystemRef", "ValueSetRef", "ConceptRef"],
    )
    def test_terminology_reference_without_a_library_is_null(
        self, visitor: ELMExpressionVisitor, node_type: str
    ) -> None:
        assert visitor.evaluate({"type": node_type, "name": "Anything"}) is None

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            (
                {
                    "type": "InCodeSystem",
                    "code": {"type": "CodeRef", "name": "BP"},
                    "codesystemRef": {"name": "LOINC"},
                },
                True,
            ),
            (
                {
                    "type": "InCodeSystem",
                    "code": {"type": "CodeRef", "name": "BP"},
                    "codesystem": {"type": "Literal", "valueType": f"{ELM_TYPE}String", "value": "http://other"},
                },
                False,
            ),
            ({"type": "InCodeSystem", "code": NULL, "codesystemRef": {"name": "LOINC"}}, None),
            ({"type": "InCodeSystem", "code": {"type": "CodeRef", "name": "BP"}}, None),
            (
                {
                    "type": "InCodeSystem",
                    "code": {"type": "Literal", "valueType": f"{ELM_TYPE}Integer", "value": "1"},
                    "codesystem": {"type": "Literal", "valueType": f"{ELM_TYPE}String", "value": "http://loinc.org"},
                },
                None,
            ),
        ],
    )
    def test_in_code_system(
        self, clinical_visitor: ELMExpressionVisitor, node: dict[str, Any], expected: bool | None
    ) -> None:
        assert clinical_visitor.evaluate(node) is expected

    @pytest.mark.parametrize(
        "node",
        [
            {"type": "InValueSet", "code": {"type": "CodeRef", "name": "BP"}, "valuesetRef": {"name": "Diabetes"}},
            {"type": "InValueSet", "code": NULL, "valuesetRef": {"name": "Diabetes"}},
            {"type": "InValueSet", "code": {"type": "CodeRef", "name": "BP"}},
            {
                "type": "InValueSet",
                "code": {"type": "CodeRef", "name": "BP"},
                "valueset": {"type": "Literal", "valueType": f"{ELM_TYPE}String", "value": "http://x"},
            },
        ],
    )
    def test_in_value_set_without_a_data_source_is_null(
        self, clinical_visitor: ELMExpressionVisitor, node: dict[str, Any]
    ) -> None:
        assert clinical_visitor.evaluate(node) is None

    @pytest.mark.parametrize(
        ("operand", "birth"),
        [(date_literal("2000-06-15"), (2000, 6, 15)), (string("2000-06-15"), (2000, 6, 15))],
    )
    def test_calculate_age_in_years(
        self, visitor: ELMExpressionVisitor, operand: dict[str, Any], birth: tuple[int, int, int]
    ) -> None:
        today = date.today()
        expected = today.year - birth[0] - ((today.month, today.day) < (birth[1], birth[2]))
        assert visitor.evaluate({"type": "CalculateAge", "operand": operand, "precision": "Year"}) == expected

    @pytest.mark.parametrize(
        "node",
        [
            {"type": "CalculateAge", "operand": {"type": "Literal", "valueType": f"{ELM_TYPE}String", "value": "nope"}},
            {"type": "CalculateAge", "operand": {"type": "Literal", "valueType": f"{ELM_TYPE}Integer", "value": "1"}},
            {"type": "CalculateAge", "operand": NULL},
            {
                "type": "CalculateAge",
                "operand": {"type": "Literal", "valueType": f"{ELM_TYPE}Date", "value": "2000-06-15"},
                "precision": "Month",
            },
        ],
    )
    def test_calculate_age_returns_null(self, visitor: ELMExpressionVisitor, node: dict[str, Any]) -> None:
        assert visitor.evaluate(node) is None

    @pytest.mark.parametrize(
        ("left", "right", "precision", "expected"),
        [
            (date_literal("2000-06-15"), date_literal("2024-06-14"), "Year", 23),
            (date_literal("2000-06-15"), date_literal("2024-06-15"), "Year", 24),
            (date_literal("2000-01-20"), date_literal("2000-03-10"), "Month", 1),
            (date_literal("2024-01-01"), date_literal("2024-01-31"), "Day", 30),
            (string("2000-06-15"), string("2024-06-16"), "Year", 24),
            (string("nope"), date_literal("2024-01-01"), "Year", None),
            (date_literal("2000-01-01"), string("nope"), "Year", None),
            (integer(1), date_literal("2024-01-01"), "Year", None),
            (date_literal("2000-01-01"), integer(1), "Year", None),
            (date_literal("2000-01-01"), date_literal("2024-01-01"), "Hour", None),
            (NULL, date_literal("2024-01-01"), "Year", None),
        ],
    )
    def test_calculate_age_at(
        self,
        visitor: ELMExpressionVisitor,
        left: dict[str, Any],
        right: dict[str, Any],
        precision: str,
        expected: int | None,
    ) -> None:
        node = {"type": "CalculateAgeAt", "operand": [left, right], "precision": precision}
        assert visitor.evaluate(node) == expected

    def test_calculate_age_at_accepts_a_python_date_as_the_as_of_value(self, visitor: ELMExpressionVisitor) -> None:
        node = {
            "type": "CalculateAgeAt",
            "operand": [date_literal("2000-01-01"), date(2024, 1, 1)],
            "precision": "Year",
        }
        assert visitor.evaluate(node) == 24


class TestPropertyNavigation:
    """Property access against the context resource, a scope alias, or an explicit source."""

    @pytest.fixture
    def patient_visitor(self) -> ELMExpressionVisitor:
        resource = {
            "resourceType": "Patient",
            "name": [{"family": "Smith"}, {"family": "Jones"}],
            "birthDate": "2000-01-01",
        }
        return ELMExpressionVisitor(CQLContext(resource=resource))

    def test_property_reads_the_context_resource(self, patient_visitor: ELMExpressionVisitor) -> None:
        assert patient_visitor.evaluate({"type": "Property", "path": "birthDate"}) == "2000-01-01"

    def test_property_maps_over_a_list(self, patient_visitor: ELMExpressionVisitor) -> None:
        assert patient_visitor.evaluate({"type": "Property", "path": "name.family"}) == ["Smith", "Jones"]

    @pytest.mark.parametrize(
        "node",
        [
            {"type": "Property", "path": "gender"},
            {"type": "Property"},
            {"type": "Property", "path": "anything", "scope": "unbound"},
        ],
    )
    def test_property_missing_paths_are_null(self, patient_visitor: ELMExpressionVisitor, node: dict[str, Any]) -> None:
        assert patient_visitor.evaluate(node) is None

    def test_property_reads_an_explicit_source(self, visitor: ELMExpressionVisitor) -> None:
        source = {"type": "Instance", "classType": "X", "element": [{"name": "family", "value": string("Doe")}]}
        assert visitor.evaluate({"type": "Property", "path": "family", "source": source}) == "Doe"

    def test_property_reads_a_model_attribute(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "Property", "path": "year", "source": date_literal("2024-05-06")}
        assert visitor.evaluate(node) == 2024

    def test_property_on_a_missing_attribute_is_null(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "Property", "path": "absent", "source": date_literal("2024-05-06")}
        assert visitor.evaluate(node) is None

    def test_property_reads_a_scope_alias(self, visitor: ELMExpressionVisitor) -> None:
        visitor.context.set_alias("N", {"code": "abc"})
        assert visitor.evaluate({"type": "Property", "path": "code", "scope": "N"}) == "abc"

    def test_property_over_a_list_without_matches_is_null(self, patient_visitor: ELMExpressionVisitor) -> None:
        assert patient_visitor.evaluate({"type": "Property", "path": "name.given"}) is None


class TestDispatch:
    """The evaluate() entry point itself."""

    def test_none_node_is_null(self, visitor: ELMExpressionVisitor) -> None:
        assert visitor.evaluate(None) is None

    @pytest.mark.parametrize("value", [7, "plain", [1, 2]])
    def test_primitive_nodes_pass_through(self, visitor: ELMExpressionVisitor, value: Any) -> None:
        assert visitor.evaluate(value) == value

    def test_missing_type_is_an_error(self, visitor: ELMExpressionVisitor) -> None:
        with pytest.raises(ELMExecutionError, match="Missing 'type' field"):
            visitor.evaluate({"value": "1"})

    def test_unsupported_type_is_an_error(self, visitor: ELMExpressionVisitor) -> None:
        with pytest.raises(ELMExecutionError, match="Unsupported expression type: Nope"):
            visitor.evaluate({"type": "Nope"})

    def test_handler_failure_is_wrapped_with_the_locator(self, visitor: ELMExpressionVisitor) -> None:
        node = {"type": "Add", "operand": [integer(1), string("x")], "locator": "12:3-12:9"}
        with pytest.raises(ELMExecutionError, match="Error evaluating Add.*at 12:3-12:9"):
            visitor.evaluate(node)

    def test_pydantic_nodes_are_dumped_before_dispatch(self, visitor: ELMExpressionVisitor) -> None:
        library = ELMLoader.parse(
            {
                "library": {
                    "identifier": {"id": "Model"},
                    "statements": {"def": [{"name": "One", "expression": integer(1)}]},
                }
            }
        )
        definition = library.get_definition("One")
        assert definition is not None
        assert visitor.evaluate(definition.expression) == 1
