"""Tests for the CQL-to-ELM serializer: round-trip evaluation plus the ELM shapes it emits."""

import json
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir_engine.engine.cql.context import CQLContext
from dhis2w_fhir_engine.engine.cql.evaluator import CQLEvaluator
from dhis2w_fhir_engine.engine.cql.types import CQLInterval, CQLTuple
from dhis2w_fhir_engine.engine.elm.evaluator import ELMEvaluator
from dhis2w_fhir_engine.engine.elm.serializer import (
    ELMSerializer,
    serialize_to_elm,
    serialize_to_elm_json,
    serialize_to_elm_model,
)
from dhis2w_fhir_engine.engine.elm.visitor import ELMExpressionVisitor
from dhis2w_fhir_engine.engine.types import FHIRDate, FHIRDateTime, FHIRTime, Quantity

ELM_TYPE = "{urn:hl7-org:elm-types:r1}"


class IdentifierContext(BaseModel):
    """A stand-in parse-tree context that yields a fixed piece of text."""

    model_config = ConfigDict(frozen=True)

    text: str

    def getText(self) -> str:  # noqa: N802 - matches the ANTLR context API
        """Return the text this context stands for."""
        return self.text


@pytest.fixture
def serializer() -> ELMSerializer:
    """A fresh serializer."""
    return ELMSerializer()


@pytest.fixture
def visitor() -> ELMExpressionVisitor:
    """A visitor for evaluating serialized expressions."""
    return ELMExpressionVisitor(CQLContext())


def _alias(name: str) -> dict[str, str]:
    """The ELM node a query alias reference serializes to."""
    return {"type": "AliasRef", "name": name}


def integer_literal(value: int) -> dict[str, str]:
    """The ELM Integer literal node one date or time component serializes to."""
    return {"type": "Literal", "valueType": f"{ELM_TYPE}Integer", "value": str(value)}


def statement(elm: dict[str, Any], name: str) -> dict[str, Any]:
    """Pick one named statement out of a serialized library."""
    definitions: list[dict[str, Any]] = elm["library"]["statements"]["def"]
    for definition in definitions:
        if definition["name"] == name:
            return definition
    raise AssertionError(f"no statement named {name}")


class TestExpressionRoundTrip:
    """CQL expressions serialized to ELM and then evaluated."""

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("1 + 2", 3),
            ("10.5 - 0.5", Decimal("10.0")),
            ("2 ^ 10", 1024),
            ("-3 + 5", 2),
            ("+7", 7),
            ("'a' & 'b'", "ab"),
            ("10 div 3", 3),
            ("10 mod 3", 1),
            ("(1 + 2) * 3", 9),
            ("6 / 3", Decimal("2")),
        ],
    )
    def test_arithmetic(
        self, serializer: ELMSerializer, visitor: ELMExpressionVisitor, expression: str, expected: Any
    ) -> None:
        assert visitor.evaluate(serializer.serialize_expression(expression)) == expected

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("5 = 5", True),
            ("5 != 4", True),
            ("5 ~ 5", True),
            ("5 !~ 4", True),
            ("3 < 4", True),
            ("3 <= 3", True),
            ("4 > 3", True),
            ("4 >= 4", True),
            ("5 = 4", False),
        ],
    )
    def test_comparison(
        self, serializer: ELMSerializer, visitor: ELMExpressionVisitor, expression: str, expected: bool
    ) -> None:
        assert visitor.evaluate(serializer.serialize_expression(expression)) is expected

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("true and false", False),
            ("true or false", True),
            ("true xor true", False),
            ("not false", True),
            ("true implies false", False),
            ("5 is null", False),
            ("5 is not null", True),
            ("true is true", True),
            ("true is not true", False),
            ("false is false", True),
            ("false is not false", False),
        ],
    )
    def test_boolean(
        self, serializer: ELMSerializer, visitor: ELMExpressionVisitor, expression: str, expected: bool
    ) -> None:
        assert visitor.evaluate(serializer.serialize_expression(expression)) is expected

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("if 1 < 2 then 'a' else 'b'", "a"),
            ("if 1 > 2 then 'a' else 'b'", "b"),
        ],
    )
    def test_conditional(
        self, serializer: ELMSerializer, visitor: ELMExpressionVisitor, expression: str, expected: str
    ) -> None:
        assert visitor.evaluate(serializer.serialize_expression(expression)) == expected

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("{1, 2, 3}", [1, 2, 3]),
            ("{}", []),
            ("5 in {1, 5, 9}", True),
            ("{1, 5, 9} contains 5", True),
            ("{1, 2} union {2, 3}", [1, 2, 2, 3]),
            ("{1, 2, 3} except {2}", [1, 3]),
            ("{1, 2} | {3}", [1, 2, 3]),
            ("exists {1}", True),
            ("exists {}", False),
            ("distinct {1, 1, 2}", [1, 2]),
            ("{1, 2, 3}[1]", 2),
            ("'hello'[1]", "e"),
        ],
    )
    def test_collections(
        self, serializer: ELMSerializer, visitor: ELMExpressionVisitor, expression: str, expected: Any
    ) -> None:
        assert visitor.evaluate(serializer.serialize_expression(expression)) == expected

    def test_intersect_keeps_shared_members(self, serializer: ELMSerializer, visitor: ELMExpressionVisitor) -> None:
        result = visitor.evaluate(serializer.serialize_expression("{1, 2, 3} intersect {2, 3, 4}"))
        assert sorted(result) == [2, 3]

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("Interval[1, 10]", CQLInterval(low=1, high=10, low_closed=True, high_closed=True)),
            ("Interval(1, 10)", CQLInterval(low=1, high=10, low_closed=False, high_closed=False)),
            ("Interval[1, 10)", CQLInterval(low=1, high=10, low_closed=True, high_closed=False)),
        ],
    )
    def test_interval_selectors(
        self, serializer: ELMSerializer, visitor: ELMExpressionVisitor, expression: str, expected: CQLInterval[Any]
    ) -> None:
        assert visitor.evaluate(serializer.serialize_expression(expression)) == expected

    def test_tuple_selector(self, serializer: ELMSerializer, visitor: ELMExpressionVisitor) -> None:
        result = visitor.evaluate(serializer.serialize_expression("Tuple { a: 1, b: 'x' }"))
        assert result == CQLTuple(elements={"a": 1, "b": "x"})

    def test_quantity_literal(self, serializer: ELMSerializer, visitor: ELMExpressionVisitor) -> None:
        result = visitor.evaluate(serializer.serialize_expression("10 'mg'"))
        assert result == Quantity(value=Decimal("10"), unit="mg")

    def test_ratio_literal(self, serializer: ELMSerializer, visitor: ELMExpressionVisitor) -> None:
        result = visitor.evaluate(serializer.serialize_expression("1 'mg' : 2 'mg'"))
        assert result == {
            "numerator": Quantity(value=Decimal("1"), unit="mg"),
            "denominator": Quantity(value=Decimal("2"), unit="mg"),
        }

    def test_long_literal(self, serializer: ELMSerializer, visitor: ELMExpressionVisitor) -> None:
        elm = serializer.serialize_expression("100L")
        assert elm["valueType"] == f"{ELM_TYPE}Long"
        assert visitor.evaluate(elm) == 100

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("5 between 1 and 10", True),
            ("15 between 1 and 10", False),
            ("5 properly between 1 and 10", True),
            ("1 properly between 1 and 10", False),
        ],
    )
    def test_between(
        self, serializer: ELMSerializer, visitor: ELMExpressionVisitor, expression: str, expected: bool
    ) -> None:
        assert visitor.evaluate(serializer.serialize_expression(expression)) is expected

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("Abs(-5)", 5),
            ("Ceiling(1.2)", 2),
            ("Floor(1.8)", 1),
            ("Truncate(1.9)", 1),
            ("Round(1.5)", 2),
            ("Ln(1)", Decimal("0.0")),
            ("Exp(0)", Decimal("1.0")),
            ("Log(8, 2)", Decimal("3.0")),
            ("Length('hello')", 5),
            ("Upper('ab')", "AB"),
            ("Lower('AB')", "ab"),
            ("Distinct({1, 1, 2})", [1, 2]),
            ("Flatten({{1}, {2}})", [1, 2]),
            ("SingletonFrom({1})", 1),
            ("ToBoolean('true')", True),
            ("ToInteger('4')", 4),
            ("ToDecimal('4.5')", Decimal("4.5")),
            ("ToString(4)", "4"),
            ("ToDate('2024-01-02')", FHIRDate(year=2024, month=1, day=2)),
            ("ToQuantity(4)", Quantity(value=Decimal("4"), unit="1")),
            ("ToList(4)", [4]),
            ("Start(Interval[1, 10])", 1),
            ("End(Interval[1, 10])", 10),
            ("Width(Interval[1, 10])", 9),
            ("PointFrom(Interval[5, 5])", 5),
            ("Not(true)", False),
            ("IsNull(null)", True),
            ("IsTrue(true)", True),
            ("IsFalse(false)", True),
            ("Successor(1)", 2),
            ("Predecessor(1)", 0),
        ],
    )
    def test_unary_function_calls(
        self, serializer: ELMSerializer, visitor: ELMExpressionVisitor, expression: str, expected: Any
    ) -> None:
        assert visitor.evaluate(serializer.serialize_expression(expression)) == expected

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("Add(1, 2)", 3),
            ("Subtract(3, 1)", 2),
            ("Multiply(2, 3)", 6),
            ("Divide(6, 3)", Decimal("2")),
            ("Power(2, 3)", 8),
            ("Modulo(7, 3)", 1),
            ("And(true, false)", False),
            ("Or(true, false)", True),
            ("Xor(true, false)", True),
            ("Implies(true, true)", True),
            ("Equal(1, 1)", True),
            ("NotEqual(1, 2)", True),
            ("Less(1, 2)", True),
            ("LessOrEqual(1, 1)", True),
            ("Greater(2, 1)", True),
            ("GreaterOrEqual(2, 2)", True),
            ("Equivalent(1, 1)", True),
            ("Concatenate('a', 'b')", "ab"),
            ("StartsWith('hello', 'he')", True),
            ("EndsWith('hello', 'lo')", True),
            ("Matches('a1', '[0-9]')", True),
            ("Contains({1, 2}, 2)", True),
            ("In(2, {1, 2})", True),
            ("Includes({1, 2}, {1})", True),
            ("IncludedIn({1}, {1, 2})", True),
            ("ProperIncludes({1, 2}, {1})", True),
            ("ProperIncludedIn({1}, {1, 2})", True),
            ("Before(1, 2)", True),
            ("After(2, 1)", True),
            ("Union({1}, {2})", [1, 2]),
            ("Except({1, 2}, {2})", [1]),
        ],
    )
    def test_binary_function_calls(
        self, serializer: ELMSerializer, visitor: ELMExpressionVisitor, expression: str, expected: Any
    ) -> None:
        assert visitor.evaluate(serializer.serialize_expression(expression)) == expected

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("Meets(Interval[1, 5], Interval(5, 9])", True),
            ("MeetsBefore(Interval[1, 5], Interval(5, 9])", True),
            ("MeetsAfter(Interval(5, 9], Interval[1, 5])", True),
            ("Overlaps(Interval[1, 5], Interval[3, 8])", True),
            ("OverlapsBefore(Interval[1, 5], Interval[3, 8])", True),
            ("OverlapsAfter(Interval[3, 8], Interval[1, 5])", True),
            ("Interval[1, 2] before Interval[5, 9]", True),
            ("Interval[5, 9] after Interval[1, 2]", True),
            ("Interval[1, 2] starts Interval[1, 9]", True),
            ("Interval[5, 9] ends Interval[1, 9]", True),
            ("Interval[1, 5] overlaps Interval[3, 8]", True),
            ("Interval[1, 5] meets Interval(5, 9]", True),
        ],
    )
    def test_interval_relations(
        self, serializer: ELMSerializer, visitor: ELMExpressionVisitor, expression: str, expected: bool
    ) -> None:
        assert visitor.evaluate(serializer.serialize_expression(expression)) is expected

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("Coalesce(null, 3)", 3),
            ("Substring('hello', 1, 3)", "ell"),
            ("Substring('hello', 2)", "llo"),
            ("Split('a,b', ',')", ["a", "b"]),
        ],
    )
    def test_variadic_function_calls(
        self, serializer: ELMSerializer, visitor: ELMExpressionVisitor, expression: str, expected: Any
    ) -> None:
        assert visitor.evaluate(serializer.serialize_expression(expression)) == expected

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("1 as Integer", 1),
            ("cast 1 as Integer", 1),
            ("'2024-01-02' as Date", FHIRDate(year=2024, month=1, day=2)),
            ("1 is Integer", True),
        ],
    )
    def test_type_expressions(
        self, serializer: ELMSerializer, visitor: ELMExpressionVisitor, expression: str, expected: Any
    ) -> None:
        assert visitor.evaluate(serializer.serialize_expression(expression)) == expected

    def test_today_evaluates_to_the_current_date(
        self, serializer: ELMSerializer, visitor: ELMExpressionVisitor
    ) -> None:
        today = date.today()
        result = visitor.evaluate(serializer.serialize_expression("Today()"))
        assert result == FHIRDate(year=today.year, month=today.month, day=today.day)

    def test_age_in_years_of_todays_birthdate_is_zero(
        self, serializer: ELMSerializer, visitor: ELMExpressionVisitor
    ) -> None:
        assert visitor.evaluate(serializer.serialize_expression("AgeInYears()")) == 0


class TestExpressionShapes:
    """The ELM node shapes the serializer emits for individual expressions."""

    @pytest.mark.parametrize(
        ("expression", "node_type", "components"),
        [
            ("@2024-01-15", "Date", {"year": 2024, "month": 1, "day": 15}),
            ("@2024", "Date", {"year": 2024}),
            (
                "@2024-01-15T10:30:00",
                "DateTime",
                {"year": 2024, "month": 1, "day": 15, "hour": 10, "minute": 30, "second": 0},
            ),
            ("@T10:30:00", "Time", {"hour": 10, "minute": 30, "second": 0}),
            ("@T00:00", "Time", {"hour": 0, "minute": 0}),
        ],
    )
    def test_temporal_literals(
        self, serializer: ELMSerializer, expression: str, node_type: str, components: dict[str, int]
    ) -> None:
        elm = serializer.serialize_expression(expression)
        assert elm["type"] == node_type
        # ELM carries a date, time, or datetime as one node per component, each an Integer literal,
        # so the precision the source wrote is the set of components the node names.
        assert {name: value for name, value in elm.items() if name != "type"} == {
            name: integer_literal(value) for name, value in components.items()
        }

    def test_a_datetime_literal_carries_its_timezone_as_an_offset_in_hours(self, serializer: ELMSerializer) -> None:
        elm = serializer.serialize_expression("@2024-01-15T10:30:00+05:30")
        assert elm["timezoneOffset"] == {
            "type": "Literal",
            "valueType": "{urn:hl7-org:elm-types:r1}Decimal",
            "value": "5.5",
        }

    @pytest.mark.parametrize(
        ("expression", "node_type"),
        [
            ("First({1, 2})", "First"),
            ("Last({1, 2})", "Last"),
            ("Count({1, 2})", "Count"),
            ("Sum({1, 2})", "Sum"),
            ("Avg({1, 2})", "Avg"),
            ("Min({1, 2})", "Min"),
            ("Max({1, 2})", "Max"),
            ("Exists({1})", "Exists"),
            ("ToDateTime('2024-01-02T00:00:00')", "ToDateTime"),
            ("ToTime('10:00:00')", "ToTime"),
            ("ToConcept(1)", "ToConcept"),
            ("Now()", "Now"),
            ("TimeOfDay()", "TimeOfDay"),
        ],
    )
    def test_unary_function_names_map_to_elm_types(
        self, serializer: ELMSerializer, expression: str, node_type: str
    ) -> None:
        assert serializer.serialize_expression(expression)["type"] == node_type

    @pytest.mark.parametrize("name", ["Count", "Sum", "Avg", "Min", "Max"])
    def test_an_aggregate_names_its_list_source(self, serializer: ELMSerializer, name: str) -> None:
        elm = serializer.serialize_expression(f"{name}({{1, 2}})")
        assert elm["source"]["type"] == "List"
        assert "operand" not in elm

    @pytest.mark.parametrize(("expression", "node_type"), [("start of", "Start"), ("end of", "End")])
    def test_an_interval_boundary_is_its_own_node(
        self, serializer: ELMSerializer, expression: str, node_type: str
    ) -> None:
        elm = serializer.serialize_expression(f"{expression} Interval[1, 10]")
        assert elm["type"] == node_type
        assert elm["operand"]["type"] == "Interval"

    @pytest.mark.parametrize(
        ("expression", "node_type"),
        [("IndexOf({1}, 1)", "IndexOf"), ("Intersect({1}, {1})", "Intersect")],
    )
    def test_binary_function_names_map_to_elm_types(
        self, serializer: ELMSerializer, expression: str, node_type: str
    ) -> None:
        assert serializer.serialize_expression(expression)["type"] == node_type

    def test_combine_names_its_two_parts(self, serializer: ELMSerializer) -> None:
        elm = serializer.serialize_expression("Combine({'a'}, '-')")
        assert elm["type"] == "Combine"
        assert elm["source"]["type"] == "List"
        assert elm["separator"]["value"] == "-"

    def test_replace_matches_names_its_three_parts(self, serializer: ELMSerializer) -> None:
        elm = serializer.serialize_expression("ReplaceMatches('a1', '[0-9]', 'x')")
        assert elm["type"] == "ReplaceMatches"
        assert elm["argument"]["value"] == "a1"
        assert elm["pattern"]["value"] == "[0-9]"
        assert elm["substitution"]["value"] == "x"

    def test_split_names_its_parts(self, serializer: ELMSerializer) -> None:
        elm = serializer.serialize_expression("Split('a,b', ',')")
        assert elm["stringToSplit"]["value"] == "a,b"
        assert elm["separator"]["value"] == ","

    def test_substring_names_its_parts(self, serializer: ELMSerializer) -> None:
        elm = serializer.serialize_expression("Substring('hello', 1, 3)")
        assert elm["stringToSub"]["value"] == "hello"
        assert elm["startIndex"]["value"] == "1"
        assert elm["length"]["value"] == "3"

    @pytest.mark.parametrize(
        ("expression", "precision"),
        [
            ("AgeInYears()", "Year"),
            ("AgeInMonths()", "Month"),
            ("AgeInDays()", "Day"),
        ],
    )
    def test_age_functions_without_arguments_default_to_today(
        self, serializer: ELMSerializer, expression: str, precision: str
    ) -> None:
        elm = serializer.serialize_expression(expression)
        assert elm["type"] == "CalculateAge"
        assert elm["precision"] == precision
        assert elm["operand"] == {"type": "Today"}

    @pytest.mark.parametrize(
        ("expression", "precision"),
        [
            ("AgeInYears(@2000-01-01)", "Year"),
            ("AgeInMonths(@2000-01-01)", "Month"),
            ("AgeInDays(@2000-01-01)", "Day"),
        ],
    )
    def test_age_functions_with_an_argument(self, serializer: ELMSerializer, expression: str, precision: str) -> None:
        elm = serializer.serialize_expression(expression)
        assert elm["type"] == "CalculateAge"
        assert elm["precision"] == precision
        assert elm["operand"]["type"] == "Date"

    @pytest.mark.parametrize(
        ("expression", "precision"),
        [
            ("CalculateAgeInYearsAt(@2000-01-01, @2024-01-01)", "Year"),
            ("CalculateAgeInMonthsAt(@2000-01-01, @2024-01-01)", "Month"),
            ("CalculateAgeInDaysAt(@2000-01-01, @2024-01-01)", "Day"),
        ],
    )
    def test_calculate_age_at_functions(self, serializer: ELMSerializer, expression: str, precision: str) -> None:
        elm = serializer.serialize_expression(expression)
        assert elm["type"] == "CalculateAgeAt"
        assert elm["precision"] == precision
        assert len(elm["operand"]) == 2

    @pytest.mark.parametrize(
        ("expression", "precision"),
        [
            ("years between @2000-01-01 and @2024-01-01", "Year"),
            ("months between @2000-01-01 and @2000-04-01", "Month"),
            ("weeks between @2024-01-01 and @2024-01-31", "Week"),
            ("days between @2024-01-01 and @2024-01-31", "Day"),
            ("hours between @2024-01-01 and @2024-01-31", "Hour"),
            ("minutes between @2024-01-01 and @2024-01-31", "Minute"),
            ("seconds between @2024-01-01 and @2024-01-31", "Second"),
        ],
    )
    def test_duration_between(self, serializer: ELMSerializer, expression: str, precision: str) -> None:
        elm = serializer.serialize_expression(expression)
        assert elm["type"] == "DurationBetween"
        assert elm["precision"] == precision

    @pytest.mark.parametrize(
        ("expression", "precision"),
        [
            ("difference in years between @2000-01-01 and @2024-01-01", "Year"),
            ("difference in days between @2024-01-01 and @2024-01-31", "Day"),
        ],
    )
    def test_difference_between(self, serializer: ELMSerializer, expression: str, precision: str) -> None:
        elm = serializer.serialize_expression(expression)
        assert elm["type"] == "DifferenceBetween"
        assert elm["precision"] == precision

    def test_duration_in_of_an_interval_spans_start_to_end(self, serializer: ELMSerializer) -> None:
        elm = serializer.serialize_expression("duration in days of Interval[@2024-01-01, @2024-01-31]")
        assert elm["type"] == "DurationBetween"
        assert elm["precision"] == "Day"
        assert [operand["type"] for operand in elm["operand"]] == ["Start", "End"]

    @pytest.mark.parametrize(
        ("expression", "node_type"),
        [
            ("Interval[1, 2] during Interval[1, 9]", "IncludedIn"),
            ("Interval[1, 9] includes Interval[1, 2]", "Includes"),
        ],
    )
    def test_timing_phrases(self, serializer: ELMSerializer, expression: str, node_type: str) -> None:
        assert serializer.serialize_expression(expression)["type"] == node_type

    def test_same_as_is_a_concurrent_comparison(self, serializer: ELMSerializer) -> None:
        elm = serializer.serialize_expression("@2024-01-01 same as @2024-01-01")
        assert elm["type"] == "SameAs"
        assert [operand["type"] for operand in elm["operand"]] == ["Date", "Date"]

    @pytest.mark.parametrize(
        ("expression", "name"),
        [("$this", "$this"), ("$index", "$index"), ("$total", "$total")],
    )
    def test_special_invocations(self, serializer: ELMSerializer, expression: str, name: str) -> None:
        assert serializer.serialize_expression(expression) == {"type": "AliasRef", "name": name}

    def test_external_constant_becomes_a_parameter_reference(self, serializer: ELMSerializer) -> None:
        assert serializer.serialize_expression("%MyParam") == {"type": "ParameterRef", "name": "MyParam"}

    def test_unknown_function_becomes_a_function_reference(self, serializer: ELMSerializer) -> None:
        elm = serializer.serialize_expression("Nope(1, 2)")
        assert elm["type"] == "FunctionRef"
        assert elm["name"] == "Nope"
        assert len(elm["operand"]) == 2

    def test_unknown_function_without_arguments_omits_operands(self, serializer: ELMSerializer) -> None:
        assert serializer.serialize_expression("Nope()") == {"type": "FunctionRef", "name": "Nope"}

    def test_method_call_puts_the_target_first(self, serializer: ELMSerializer) -> None:
        elm = serializer.serialize_expression("'ab'.upper()")
        assert elm["type"] == "FunctionRef"
        assert elm["name"] == "upper"
        assert elm["operand"][0]["value"] == "ab"

    def test_member_invocation_on_a_term_becomes_a_property(self, serializer: ELMSerializer) -> None:
        elm = serializer.serialize_expression("Numbers.value")
        assert elm["type"] == "Property"
        assert elm["path"] == "value"
        assert elm["source"] == {"type": "ExpressionRef", "name": "Numbers"}

    def test_code_selector_names_its_code_system(self, serializer: ELMSerializer) -> None:
        elm = serializer.serialize_expression("Code 'x' from Sys display 'D'")
        assert elm["type"] == "Code"
        assert elm["code"] == "x"
        assert elm["system"] == {"name": "Sys"}
        assert elm["display"] == "D"

    def test_concept_selector_collects_its_codes(self, serializer: ELMSerializer) -> None:
        elm = serializer.serialize_expression("Concept { Code 'x' from Sys } display 'D'")
        assert elm["type"] == "Concept"
        assert [code["code"] for code in elm["code"]] == ["x"]
        assert elm["display"] == "D"

    def test_a_searched_case_carries_its_whens_and_its_else(self, serializer: ELMSerializer) -> None:
        elm = serializer.serialize_expression("case when false then 1 when true then 2 else 3 end")
        assert elm["type"] == "Case"
        assert "comparand" not in elm
        assert [item["when"]["value"] for item in elm["caseItem"]] == ["false", "true"]
        assert [item["then"]["value"] for item in elm["caseItem"]] == ["1", "2"]
        assert elm["else"]["value"] == "3"

    def test_a_case_with_a_comparand_carries_the_comparand(self, serializer: ELMSerializer) -> None:
        elm = serializer.serialize_expression("case 2 when 1 then 'one' when 2 then 'two' else 'other' end")
        assert elm["type"] == "Case"
        assert elm["comparand"]["value"] == "2"
        assert [item["when"]["value"] for item in elm["caseItem"]] == ["1", "2"]
        assert elm["else"]["value"] == "other"


class TestLibraryStructure:
    """Library-level declarations."""

    def test_library_without_a_version(self) -> None:
        elm = serialize_to_elm("library Test")
        assert elm["library"]["identifier"] == {"id": "Test"}

    def test_empty_sections_are_dropped(self) -> None:
        library = serialize_to_elm("library Test\ndefine One: 1")["library"]
        for section in ["usings", "includes", "parameters", "codeSystems", "valueSets", "codes", "concepts"]:
            assert section not in library

    def test_schema_identifier_is_always_present(self) -> None:
        elm = serialize_to_elm("library Test")
        assert elm["library"]["schemaIdentifier"] == {"id": "urn:hl7-org:elm", "version": "r1"}

    @pytest.mark.parametrize(
        ("model", "uri"),
        [("FHIR", "http://hl7.org/fhir"), ("System", "urn:hl7-org:elm-types:r1")],
    )
    def test_using_maps_known_models_to_a_uri(self, model: str, uri: str) -> None:
        usings = serialize_to_elm(f"library Test\nusing {model}")["library"]["usings"]["def"]
        assert usings == [{"localIdentifier": model, "uri": uri}]

    def test_include_without_an_alias_uses_the_library_name(self) -> None:
        includes = serialize_to_elm("library Test\ninclude Helpers version '1.0'")["library"]["includes"]["def"]
        assert includes == [{"localIdentifier": "Helpers", "path": "Helpers", "version": "1.0"}]

    def test_context_definition_sets_the_statement_context(self) -> None:
        source = "library Test\ncontext Unfiltered\ndefine One: 1"
        elm = serialize_to_elm(source)
        assert elm["library"]["contexts"]["def"] == [{"name": "Unfiltered"}]
        assert statement(elm, "One")["context"] == "Unfiltered"

    def test_quoted_definition_names_lose_their_quotes(self) -> None:
        elm = serialize_to_elm('library Test\ndefine "My Def": 1')
        assert statement(elm, "My Def")["accessLevel"] == "Public"

    def test_private_definitions_are_marked(self) -> None:
        elm = serialize_to_elm("library Test\ndefine private Secret: 1")
        assert statement(elm, "Secret")["accessLevel"] == "Private"


class TestParameterAndTypeSpecifiers:
    """Parameter declarations and the type specifiers they carry."""

    def parameter(self, source: str) -> dict[str, Any]:
        """Serialize one parameter declaration."""
        parameters: list[dict[str, Any]] = serialize_to_elm(source)["library"]["parameters"]["def"]
        return parameters[0]

    def test_default_value(self) -> None:
        parameter = self.parameter("library Test\nparameter Threshold Integer default 5")
        assert parameter["name"] == "Threshold"
        assert parameter["default"] == {"type": "Literal", "valueType": f"{ELM_TYPE}Integer", "value": "5"}

    @pytest.mark.parametrize(
        ("declared", "expected"),
        [
            ("Integer", f"{ELM_TYPE}Integer"),
            ("Decimal", f"{ELM_TYPE}Decimal"),
            ("String", f"{ELM_TYPE}String"),
            ("Boolean", f"{ELM_TYPE}Boolean"),
            ("Date", f"{ELM_TYPE}Date"),
            ("DateTime", f"{ELM_TYPE}DateTime"),
            ("Time", f"{ELM_TYPE}Time"),
            ("Quantity", f"{ELM_TYPE}Quantity"),
            ("Ratio", f"{ELM_TYPE}Ratio"),
            ("Any", f"{ELM_TYPE}Any"),
            ("Code", f"{ELM_TYPE}Code"),
            ("Concept", f"{ELM_TYPE}Concept"),
            ("Patient", "{http://hl7.org/fhir}Patient"),
        ],
    )
    def test_named_type_specifier(self, declared: str, expected: str) -> None:
        parameter = self.parameter(f"library Test\nparameter P {declared}")
        assert parameter["parameterTypeSpecifier"] == {"type": "NamedTypeSpecifier", "name": expected}

    def test_qualified_type_name_lands_in_the_fhir_namespace(self) -> None:
        parameter = self.parameter("library Test\nparameter P FHIR.Patient")
        assert parameter["parameterTypeSpecifier"]["name"] == "{http://hl7.org/fhir}FHIR.Patient"

    def test_list_type_specifier(self) -> None:
        parameter = self.parameter("library Test\nparameter Names List<String>")
        assert parameter["parameterTypeSpecifier"] == {
            "type": "ListTypeSpecifier",
            "elementType": {"type": "NamedTypeSpecifier", "name": f"{ELM_TYPE}String"},
        }

    def test_interval_type_specifier(self) -> None:
        parameter = self.parameter("library Test\nparameter Period Interval<DateTime>")
        assert parameter["parameterTypeSpecifier"] == {
            "type": "IntervalTypeSpecifier",
            "pointType": {"type": "NamedTypeSpecifier", "name": f"{ELM_TYPE}DateTime"},
        }

    def test_choice_type_specifier(self) -> None:
        parameter = self.parameter("library Test\nparameter Mixed Choice<Integer, String>")
        assert parameter["parameterTypeSpecifier"] == {
            "type": "ChoiceTypeSpecifier",
            "choice": [
                {"type": "NamedTypeSpecifier", "name": f"{ELM_TYPE}Integer"},
                {"type": "NamedTypeSpecifier", "name": f"{ELM_TYPE}String"},
            ],
        }


class TestTerminologyDeclarations:
    """Code system, value set, code and concept declarations."""

    def test_codesystem_with_a_version(self) -> None:
        source = "library Test\ncodesystem LOINC: 'http://loinc.org' version '2.7'"
        code_systems = serialize_to_elm(source)["library"]["codeSystems"]["def"]
        assert code_systems == [{"name": "LOINC", "id": "http://loinc.org", "accessLevel": "Public", "version": "2.7"}]

    def test_valueset_with_a_version_and_code_systems(self) -> None:
        source = (
            "library Test\n"
            "codesystem LOINC: 'http://loinc.org'\n"
            "valueset VS: 'http://example.org/vs' version '1.0' codesystems { LOINC }"
        )
        value_sets = serialize_to_elm(source)["library"]["valueSets"]["def"]
        assert value_sets == [
            {
                "name": "VS",
                "id": "http://example.org/vs",
                "accessLevel": "Public",
                "version": "1.0",
                "codeSystem": [{"name": "LOINC"}],
            }
        ]

    def test_code_with_a_display(self) -> None:
        source = (
            "library Test\ncodesystem LOINC: 'http://loinc.org'\ncode BP: '55284-4' from LOINC display 'Blood pressure'"
        )
        codes = serialize_to_elm(source)["library"]["codes"]["def"]
        assert codes == [
            {
                "name": "BP",
                "id": "55284-4",
                "accessLevel": "Public",
                "codeSystem": {"name": "LOINC"},
                "display": "Blood pressure",
            }
        ]

    def test_concept_lists_its_member_codes(self) -> None:
        source = (
            "library Test\n"
            "codesystem LOINC: 'http://loinc.org'\n"
            "code BP: '55284-4' from LOINC\n"
            "concept BPC: { BP } display 'BP concept'"
        )
        concepts = serialize_to_elm(source)["library"]["concepts"]["def"]
        assert concepts == [{"name": "BPC", "accessLevel": "Public", "code": [{"name": "BP"}], "display": "BP concept"}]

    @pytest.mark.parametrize(
        ("method_name", "node_type"),
        [
            ("visitCodeSystemRef", "CodeSystemRef"),
            ("visitValueSetRef", "ValueSetRef"),
            ("visitCodeRef", "CodeRef"),
            ("visitConceptRef", "ConceptRef"),
        ],
    )
    def test_terminology_reference_visitors(self, serializer: ELMSerializer, method_name: str, node_type: str) -> None:
        visit = getattr(serializer, method_name)
        assert visit(IdentifierContext(text='"LOINC"')) == {"type": node_type, "name": "LOINC"}

    def test_terminology_visitor_passes_through_a_missing_context(self, serializer: ELMSerializer) -> None:
        assert serializer.visitTerminology(None) is None


class TestFunctionDefinitions:
    """Function declarations."""

    def test_operands_and_return_type(self) -> None:
        source = "library Test\ndefine function Add(a Integer, b Integer) returns Integer: a + b"
        function = statement(serialize_to_elm(source), "Add")
        assert function["type"] == "FunctionDef"
        assert [operand["name"] for operand in function["operand"]] == ["a", "b"]
        assert function["resultTypeSpecifier"] == {"type": "NamedTypeSpecifier", "name": f"{ELM_TYPE}Integer"}
        assert function["expression"]["type"] == "Add"

    def test_external_function_has_no_body(self) -> None:
        source = "library Test\ndefine function Ext(a Integer) returns Integer: external"
        function = statement(serialize_to_elm(source), "Ext")
        assert function["external"] is True
        assert "expression" not in function

    def test_fluent_function_is_marked(self) -> None:
        source = "library Test\ndefine fluent function Doubled(a Integer): a * 2"
        assert statement(serialize_to_elm(source), "Doubled")["fluent"] is True

    def test_untyped_operand_falls_back_to_the_fhir_namespace(self) -> None:
        source = "library Test\ndefine function Ident(a): a"
        operand = statement(serialize_to_elm(source), "Ident")["operand"][0]
        assert operand["operandTypeSpecifier"]["name"].startswith("{http://hl7.org/fhir}")

    def test_function_without_operands_omits_the_operand_list(self) -> None:
        source = "library Test\ndefine function Constant(): 1"
        assert "operand" not in statement(serialize_to_elm(source), "Constant")


class TestQuerySerialization:
    """Query clauses in a serialized library."""

    def query(self, clause: str) -> dict[str, Any]:
        """Serialize a query written over a fixed list source."""
        source = f"library Test\ndefine Numbers: {{ 1, 2, 3 }}\ndefine Q: from Numbers N {clause}"
        expression: dict[str, Any] = statement(serialize_to_elm(source), "Q")["expression"]
        return expression

    def test_source_alias(self) -> None:
        query = self.query("return N")
        assert query["type"] == "Query"
        assert [entry["alias"] for entry in query["source"]] == ["N"]

    def test_where_clause(self) -> None:
        assert self.query("where N > 1")["where"]["type"] == "Greater"

    def test_return_clause(self) -> None:
        assert self.query("return N * 2")["return"]["expression"]["type"] == "Multiply"

    def test_return_distinct_is_flagged(self) -> None:
        assert self.query("return distinct N")["return"]["distinct"] is True

    def test_let_clause(self) -> None:
        let_clauses = self.query("let d: N * 2 return d")["let"]
        assert [clause["identifier"] for clause in let_clauses] == ["d"]
        assert let_clauses[0]["expression"]["type"] == "Multiply"

    def test_aggregate_clause(self) -> None:
        aggregate = self.query("aggregate T starting 0: T + N")["aggregate"]
        assert aggregate["identifier"] == "T"
        assert aggregate["expression"]["type"] == "Add"
        assert aggregate["starting"] == {"type": "Literal", "valueType": f"{ELM_TYPE}Integer", "value": "0"}

    def test_aggregate_clause_without_a_starting_value(self) -> None:
        aggregate = self.query("aggregate T: T + N")["aggregate"]
        assert aggregate["identifier"] == "T"
        assert "starting" not in aggregate

    def test_sort_clause_is_present(self) -> None:
        assert "sort" in self.query("return N sort desc")

    def test_sort_by_a_named_column(self) -> None:
        sort_items = self.query("return N sort by N desc")["sort"]["by"]
        assert sort_items == [{"expression": {"type": "ExpressionRef", "name": "N"}, "direction": "desc"}]

    def test_sort_by_a_named_column_ascending(self) -> None:
        sort_items = self.query("return N sort by N asc")["sort"]["by"]
        assert sort_items[0]["direction"] == "asc"

    def test_a_source_alias_is_referenced_as_an_alias(self) -> None:
        assert self.query("where N > 1")["where"]["operand"][0] == {"type": "AliasRef", "name": "N"}

    def test_a_return_clause_references_the_alias(self) -> None:
        assert self.query("return N * 2")["return"]["expression"]["operand"][0] == {"type": "AliasRef", "name": "N"}

    def test_a_property_reads_through_the_alias(self) -> None:
        source = "library Test\nusing FHIR version '4.0.1'\ndefine Q: from [Patient] P where P.gender = 'female'"
        query = statement(serialize_to_elm(source), "Q")["expression"]
        assert query["where"]["operand"][0] == {"type": "Property", "path": "gender", "source": _alias("P")}

    def test_a_let_binding_is_referenced_as_a_query_let(self) -> None:
        query = self.query("let d: N * 2 where d > 2 return d")
        assert query["let"][0]["expression"]["operand"][0] == _alias("N")
        assert query["where"]["operand"][0] == {"type": "QueryLetRef", "name": "d"}
        assert query["return"]["expression"] == {"type": "QueryLetRef", "name": "d"}

    def test_an_aggregate_reads_the_accumulator_and_the_alias(self) -> None:
        aggregate = self.query("aggregate T starting 0: T + N")["aggregate"]
        assert aggregate["expression"]["operand"] == [_alias("T"), _alias("N")]

    def test_a_definition_outside_a_query_stays_an_expression_reference(self) -> None:
        source = "library Test\ndefine N: 1\ndefine Q: from { 1, 2 } N return N\ndefine After: N"
        elm = serialize_to_elm(source)
        assert statement(elm, "After")["expression"] == {"type": "ExpressionRef", "name": "N"}

    def test_a_relationship_alias_is_in_scope_only_in_its_such_that(self) -> None:
        source = (
            "library Test\ndefine A: { 1, 2 }\ndefine B: { 2 }\ndefine Q: from A x with B y such that x = y return x"
        )
        query = statement(serialize_to_elm(source), "Q")["expression"]
        relationship = query["relationship"][0]
        assert relationship["expression"] == {"type": "ExpressionRef", "name": "B"}
        assert relationship["suchThat"]["operand"] == [_alias("x"), _alias("y")]
        assert query["return"]["expression"] == _alias("x")

    def test_a_nested_query_sees_both_aliases(self) -> None:
        source = (
            "library Test\ndefine Outer: { 1, 2 }\ndefine Inner: { 3 }\n"
            "define Q: from Outer N return (from Inner M return M + N)"
        )
        inner = statement(serialize_to_elm(source), "Q")["expression"]["return"]["expression"]
        assert inner["return"]["expression"]["operand"] == [_alias("M"), _alias("N")]

    def test_relationship_clauses_are_recorded(self) -> None:
        source = (
            "library Test\ndefine A: { 1, 2 }\ndefine B: { 2 }\ndefine Q: from A x with B y such that x = y return x"
        )
        query = statement(serialize_to_elm(source), "Q")["expression"]
        assert len(query["relationship"]) == 1

    def test_query_without_optional_clauses(self) -> None:
        query = self.query("return N")
        for clause in ["where", "let", "relationship", "aggregate", "sort"]:
            assert clause not in query


class TestRetrieveSerialization:
    """Retrieve expressions."""

    def test_plain_retrieve_carries_a_qualified_data_type(self) -> None:
        source = "library Test\nusing FHIR version '4.0.1'\ndefine Patients: [Patient]"
        expression = statement(serialize_to_elm(source), "Patients")["expression"]
        assert expression == {"type": "Retrieve", "dataType": "{http://hl7.org/fhir}Patient"}

    def test_instance_selector_carries_a_class_type(self) -> None:
        source = "library Test\nusing FHIR version '4.0.1'\ndefine P: FHIR.Patient { id: 'p1' }"
        expression = statement(serialize_to_elm(source), "P")["expression"]
        assert expression["type"] == "Instance"
        assert expression["classType"] == "{http://hl7.org/fhir}FHIR.Patient"
        assert expression["element"] == [
            {"name": "id", "value": {"type": "Literal", "valueType": f"{ELM_TYPE}String", "value": "p1"}}
        ]


class TestCollectionAndFunctionShapes:
    """The ELM shapes the schema names for list selectors, `flatten`, and a user-defined function."""

    @pytest.mark.parametrize("selector", ["First", "Last"])
    def test_a_list_selector_names_its_list_source(self, selector: str) -> None:
        source = f"library Test\ndefine Numbers: {{ 1, 2, 3 }}\ndefine Picked: {selector}(Numbers)"
        expression = statement(serialize_to_elm(source), "Picked")["expression"]
        assert expression == {"type": selector, "source": {"type": "ExpressionRef", "name": "Numbers"}}

    def test_the_flatten_keyword_emits_a_flatten_node(self) -> None:
        source = "library Test\ndefine Nested: { { 1 }, { 2 } }\ndefine Flat: flatten Nested"
        expression = statement(serialize_to_elm(source), "Flat")["expression"]
        assert expression == {"type": "Flatten", "operand": {"type": "ExpressionRef", "name": "Nested"}}

    def test_the_distinct_keyword_still_emits_a_distinct_node(self) -> None:
        source = "library Test\ndefine Numbers: { 1, 1, 2 }\ndefine Unique: distinct Numbers"
        expression = statement(serialize_to_elm(source), "Unique")["expression"]
        assert expression == {"type": "Distinct", "operand": {"type": "ExpressionRef", "name": "Numbers"}}

    @pytest.mark.parametrize(
        "aggregate",
        [
            "Count",
            "Sum",
            "Avg",
            "Min",
            "Max",
            "Median",
            "Mode",
            "Variance",
            "PopulationVariance",
            "StdDev",
            "PopulationStdDev",
            "AllTrue",
            "AnyTrue",
            "Product",
            "GeometricMean",
        ],
    )
    def test_every_aggregate_names_its_list_source(self, aggregate: str) -> None:
        source = f"library Test\ndefine Numbers: {{ 1, 2, 3 }}\ndefine Folded: {aggregate}(Numbers)"
        expression = statement(serialize_to_elm(source), "Folded")["expression"]
        assert expression == {"type": aggregate, "source": {"type": "ExpressionRef", "name": "Numbers"}}

    def test_index_of_names_its_list_source_and_its_needle_element(self) -> None:
        source = "library Test\ndefine Numbers: { 1, 2 }\ndefine Where: IndexOf(Numbers, 2)"
        expression = statement(serialize_to_elm(source), "Where")["expression"]
        assert expression == {
            "type": "IndexOf",
            "source": {"type": "ExpressionRef", "name": "Numbers"},
            "element": {"type": "Literal", "valueType": f"{ELM_TYPE}Integer", "value": "2"},
        }

    def test_combine_without_a_separator_states_only_its_source(self) -> None:
        source = "library Test\ndefine Parts: { 'a', 'b' }\ndefine Joined: Combine(Parts)"
        expression = statement(serialize_to_elm(source), "Joined")["expression"]
        assert expression == {"type": "Combine", "source": {"type": "ExpressionRef", "name": "Parts"}}

    def test_a_function_body_refers_to_its_parameter_as_an_operand(self) -> None:
        source = 'library Test\ndefine function "Doubled"(value Integer): value * 2'
        expression = statement(serialize_to_elm(source), "Doubled")["expression"]
        assert expression["operand"][0] == {"type": "OperandRef", "name": "value"}

    def test_a_name_outside_the_function_stays_an_expression_reference(self) -> None:
        source = 'library Test\ndefine Base: 2\ndefine function "Scaled"(value Integer): value * Base'
        expression = statement(serialize_to_elm(source), "Scaled")["expression"]
        assert expression["operand"] == [
            {"type": "OperandRef", "name": "value"},
            {"type": "ExpressionRef", "name": "Base"},
        ]

    def test_a_query_alias_inside_a_function_body_shadows_nothing_it_should_not(self) -> None:
        source = (
            "library Test\ndefine Numbers: { 1, 2 }\n"
            'define function "Scaled"(factor Integer): Numbers N return N * factor'
        )
        expression = statement(serialize_to_elm(source), "Scaled")["expression"]
        assert expression["return"]["expression"]["operand"] == [
            {"type": "AliasRef", "name": "N"},
            {"type": "OperandRef", "name": "factor"},
        ]


class TestJSONOutput:
    """JSON rendering and the module-level convenience functions."""

    def test_json_is_parseable_and_indented(self) -> None:
        rendered = serialize_to_elm_json("library Test\ndefine Sum: 1 + 2", indent=4)
        assert "    " in rendered
        assert json.loads(rendered)["library"]["identifier"]["id"] == "Test"

    def test_quantities_survive_the_json_round_trip(self) -> None:
        rendered = serialize_to_elm_json("library Test\ndefine Q: 1 'mg'")
        expression = json.loads(rendered)["library"]["statements"]["def"][0]["expression"]
        assert expression == {"type": "Quantity", "value": "1", "unit": "mg"}

    def test_serialize_to_model_returns_a_library(self) -> None:
        model = serialize_to_elm_model("library Test version '2.0'\ndefine One: 1")
        assert model.identifier.id == "Test"
        assert model.identifier.version == "2.0"
        assert model.get_definition("One") is not None

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(Decimal("1.5"), "1.5"), (date(2024, 1, 2), "2024-01-02")],
    )
    def test_json_default_renders_special_types(self, serializer: ELMSerializer, value: Any, expected: str) -> None:
        assert serializer._json_default(value) == expected

    def test_json_default_rejects_anything_else(self, serializer: ELMSerializer) -> None:
        with pytest.raises(TypeError, match="not JSON serializable"):
            serializer._json_default(object())


class TestLibraryRoundTrip:
    """Whole libraries serialized, loaded and evaluated."""

    def test_definitions_reference_each_other(self) -> None:
        source = """
            library RoundTrip version '1.0'
            define Base: 10
            define Derived: Base + 5
            define Nested: Derived * 2
        """
        evaluator = ELMEvaluator()
        evaluator.load(serialize_to_elm_json(source))
        assert evaluator.evaluate_definition("Nested") == 30

    def test_all_definitions_evaluate_together(self) -> None:
        source = """
            library RoundTrip
            define Numbers: { 1, 2, 3 }
            define Flag: true and false
            define Chosen: if 1 < 2 then 'a' else 'b'
        """
        evaluator = ELMEvaluator()
        evaluator.load(serialize_to_elm_json(source))
        assert evaluator.evaluate_all_definitions() == {
            "Numbers": [1, 2, 3],
            "Flag": False,
            "Chosen": "a",
        }

    @pytest.mark.parametrize(
        ("clause", "expected"),
        [
            ("where N > 2", [3, 4]),
            ("return N * 2", [2, 4, 6, 8]),
            ("where N > 1 return N + 10", [12, 13, 14]),
            ("let d: N * 10 where d > 25 return d", [30, 40]),
            ("aggregate T starting 0: T + N", 10),
        ],
    )
    def test_a_query_answers_the_same_from_cql_and_from_elm(self, clause: str, expected: Any) -> None:
        source = f"library RoundTrip\ndefine Numbers: {{ 1, 2, 3, 4 }}\ndefine Q: from Numbers N {clause}"

        from_cql = CQLEvaluator()
        from_cql.compile(source)
        from_elm = ELMEvaluator()
        from_elm.load(serialize_to_elm_json(source))

        assert from_elm.evaluate_definition("Q") == expected
        assert from_elm.evaluate_definition("Q") == from_cql.evaluate_definition("Q")

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("Count({ 1, 2, 3 })", 3),
            ("Sum({ 1, 2, 3 })", 6),
            ("Max({ 1, 5, 3 })", 5),
            ("start of Interval[1, 10]", 1),
            ("end of Interval[1, 10]", 10),
            ("case when false then 'a' when true then 'b' else 'c' end", "b"),
            ("case when false then 'a' when false then 'b' else 'c' end", "c"),
            ("case 2 when 1 then 'one' when 2 then 'two' else 'other' end", "two"),
            ("case 9 when 1 then 'one' when 2 then 'two' else 'other' end", "other"),
            ("case 'x' when 'x' then case when true then 'nested' else 'no' end else 'no' end", "nested"),
            ("@2024-01-15", FHIRDate(year=2024, month=1, day=15)),
            ("@2024-01", FHIRDate(year=2024, month=1)),
            ("@2024", FHIRDate(year=2024)),
            ("@2024-01-15T10:30:00", FHIRDateTime(year=2024, month=1, day=15, hour=10, minute=30, second=0)),
            (
                "@2024-01-15T00:00:00.250Z",
                FHIRDateTime(year=2024, month=1, day=15, hour=0, minute=0, second=0, millisecond=250, tz_offset="Z"),
            ),
            (
                "@2024-01-15T10:30:00+05:30",
                FHIRDateTime(year=2024, month=1, day=15, hour=10, minute=30, second=0, tz_offset="+05:30"),
            ),
            ("@T12:00", FHIRTime(hour=12, minute=0)),
            ("@T00:00:00", FHIRTime(hour=0, minute=0, second=0)),
            (
                "Interval[@2024-01-01, @2024-01-31]",
                CQLInterval(
                    low=FHIRDate(year=2024, month=1, day=1),
                    high=FHIRDate(year=2024, month=1, day=31),
                    low_closed=True,
                    high_closed=True,
                ),
            ),
            ("@2024-01-15 in Interval[@2024-01-01, @2024-01-31]", True),
            ("start of Interval[@2024-01-01, @2024-01-31]", FHIRDate(year=2024, month=1, day=1)),
            ("case when @2024-01-15 in Interval[@2024-01-01, @2024-01-31] then 'inside' else 'outside' end", "inside"),
        ],
    )
    def test_an_expression_answers_the_same_from_cql_and_from_elm(self, expression: str, expected: Any) -> None:
        source = f"library RoundTrip\ndefine Answer: {expression}"

        from_cql = CQLEvaluator()
        from_cql.compile(source)
        from_elm = ELMEvaluator()
        from_elm.load(serialize_to_elm_json(source))

        assert from_elm.evaluate_definition("Answer") == expected
        assert from_elm.evaluate_definition("Answer") == from_cql.evaluate_definition("Answer")

    def test_a_relationship_query_answers_the_same_from_cql_and_from_elm(self) -> None:
        source = """
            library RoundTrip
            define Left: { 1, 2, 3 }
            define Right: { 2, 3 }
            define Q: from Left x with Right y such that x = y return x
        """

        from_cql = CQLEvaluator()
        from_cql.compile(source)
        from_elm = ELMEvaluator()
        from_elm.load(serialize_to_elm_json(source))

        assert from_elm.evaluate_definition("Q") == [2, 3]
        assert from_elm.evaluate_definition("Q") == from_cql.evaluate_definition("Q")

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("First({ 1, 2, 3 })", 1),
            ("Last({ 1, 2, 3 })", 3),
            ("First({})", None),
            ("Last({})", None),
            ("flatten { { 1, 2 }, { 3, 4 } }", [1, 2, 3, 4]),
            ("distinct { 1, 1, 2 }", [1, 2]),
            ("First(flatten { { 5, 6 }, { 7 } })", 5),
            ("Last(distinct { 1, 2, 2 })", 2),
            ("IndexOf({ 10, 20, 30 }, 20)", 1),
            ("IndexOf({ 10, 20 }, 99)", -1),
            ("IndexOf('Hello World', 'World')", 6),
            ("Combine({ 'a', 'b' }, '-')", "a-b"),
            ("Combine({ 'a', 'b' })", "ab"),
            ("Median({ 1, 2, 3 })", 2),
            ("Mode({ 1, 1, 2 })", 1),
            ("AllTrue({ true, true })", True),
            ("AnyTrue({ false, true })", True),
            ("Product({ 2, 3, 4 })", 24),
        ],
    )
    def test_a_collection_expression_answers_the_same_from_cql_and_from_elm(
        self, expression: str, expected: Any
    ) -> None:
        source = f"library RoundTrip\ndefine Answer: {expression}"

        from_cql = CQLEvaluator()
        from_cql.compile(source)
        from_elm = ELMEvaluator()
        from_elm.load(serialize_to_elm_json(source))

        assert from_elm.evaluate_definition("Answer") == expected
        assert from_elm.evaluate_definition("Answer") == from_cql.evaluate_definition("Answer")

    def test_a_defined_function_answers_the_same_from_cql_and_from_elm(self) -> None:
        source = """
            library RoundTrip
            define function "Doubled"(value Integer): value * 2
            define "Doubled Three": "Doubled"(3)
        """

        from_cql = CQLEvaluator()
        from_cql.compile(source)
        from_elm = ELMEvaluator()
        from_elm.load(serialize_to_elm_json(source))

        assert from_elm.evaluate_definition("Doubled Three") == 6
        assert from_elm.evaluate_definition("Doubled Three") == from_cql.evaluate_definition("Doubled Three")

    def test_list_selectors_flatten_and_a_defined_function_agree_across_the_round_trip(self) -> None:
        source = """
            library RoundTrip version '1.0'
            define "Dose Numbers": { 1, 2, 3 }
            define "First Dose": First("Dose Numbers")
            define "Last Dose": Last("Dose Numbers")
            define "Nested Doses": { { 1, 2 }, { 3, 4 } }
            define "Flat Doses": flatten "Nested Doses"
            define function "Doubled"(value Integer): value * 2
            define "Doubled First": "Doubled"(First("Dose Numbers"))
            define "Doubled Flat": "Dose Numbers" N return "Doubled"(N)
        """
        compared = ("First Dose", "Last Dose", "Flat Doses", "Doubled First", "Doubled Flat")

        from_cql = CQLEvaluator()
        from_cql.compile(source)
        from_elm = ELMEvaluator()
        from_elm.load(serialize_to_elm_json(source))

        from_elm_answers = {name: from_elm.evaluate_definition(name) for name in compared}
        assert from_elm_answers == {
            "First Dose": 1,
            "Last Dose": 3,
            "Flat Doses": [1, 2, 3, 4],
            "Doubled First": 2,
            "Doubled Flat": [2, 4, 6],
        }
        assert from_elm_answers == {name: from_cql.evaluate_definition(name) for name in compared}

    def test_private_definitions_are_skipped_after_a_round_trip(self) -> None:
        source = """
            library RoundTrip
            define private Hidden: 1
            define Shown: 2
        """
        evaluator = ELMEvaluator()
        evaluator.load(serialize_to_elm_json(source))
        assert evaluator.get_definition_names() == ["Shown"]
        assert evaluator.get_definition_names(include_private=True) == ["Hidden", "Shown"]
