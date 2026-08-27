"""Tests for the FHIRPath aggregate functions - sum, min, max, avg.

The worked examples in `TestSpecExamples` are the ones printed in FHIRPath section 7, so a
regression there is a regression against the specification text rather than against our reading
of it.
"""

from decimal import Decimal
from typing import Any

import pytest

from dhis2w_fhir_engine.engine.context import EvaluationContext
from dhis2w_fhir_engine.engine.exceptions import FHIRPathError
from dhis2w_fhir_engine.engine.fhirpath.evaluator import FHIRPathEvaluator
from dhis2w_fhir_engine.engine.fhirpath.functions.aggregates import fn_avg, fn_max, fn_min, fn_sum
from dhis2w_fhir_engine.engine.fhirpath.visitor import _PrimitiveWithExtension
from dhis2w_fhir_engine.engine.types import FHIRDate, Quantity


@pytest.fixture
def context() -> EvaluationContext:
    """Build an evaluation context with no resource bound."""
    return EvaluationContext()


@pytest.fixture
def evaluator() -> FHIRPathEvaluator:
    """Build an evaluator for the expression-level cases."""
    return FHIRPathEvaluator()


class TestEmptyCollection:
    """Section 7: if the input collection is empty, the result is empty."""

    @pytest.mark.parametrize("function", [fn_sum, fn_min, fn_max, fn_avg])
    def test_empty_input_answers_empty(self, context: EvaluationContext, function: Any) -> None:
        """No aggregate invents a zero for a collection that holds nothing."""
        assert function(context, []) == []

    @pytest.mark.parametrize("expression", ["sum()", "min()", "max()", "avg()"])
    def test_absent_element_answers_empty(self, evaluator: FHIRPathEvaluator, expression: str) -> None:
        """A path that matches nothing carries the empty collection into the aggregate."""
        patient = {"resourceType": "Patient", "id": "child-1"}
        assert evaluator.evaluate(f"Patient.multipleBirthInteger.{expression}", patient) == []


class TestSpecExamples:
    """The examples printed in FHIRPath section 7, evaluated as written."""

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("(1.0 | 2.0 | 3.0 | 4.0 | 5.0).sum()", [Decimal("15.0")]),
            ("(2 | 4 | 8 | 6).min()", [2]),
            ("(2 | 4 | 8 | 6).max()", [8]),
            ("(5.5 | 4.7 | 4.8).avg()", [Decimal("5.0")]),
        ],
    )
    def test_numeric_example(self, evaluator: FHIRPathEvaluator, expression: str, expected: list[Any]) -> None:
        """The numeric examples answer exactly what the specification prints beside them."""
        assert evaluator.evaluate(expression, {"resourceType": "Patient"}) == expected

    def test_quantity_sum_example(self, evaluator: FHIRPathEvaluator) -> None:
        """`( 1.0 'mg' | ... | 5.0 'mg' ).sum()` answers `15.0 'mg'`."""
        expression = "(1.0 'mg' | 2.0 'mg' | 3.0 'mg' | 4.0 'mg' | 5.0 'mg').sum()"
        assert evaluator.evaluate(expression, {"resourceType": "Patient"}) == [
            Quantity(value=Decimal("15.0"), unit="mg")
        ]

    def test_quantity_avg_example(self, evaluator: FHIRPathEvaluator) -> None:
        """`( 5.5 'cm' | 4.7 'cm' | 4.8 'cm' ).avg()` answers `5.0 'cm'`."""
        expression = "(5.5 'cm' | 4.7 'cm' | 4.8 'cm').avg()"
        assert evaluator.evaluate(expression, {"resourceType": "Patient"}) == [
            Quantity(value=Decimal("5.0"), unit="cm")
        ]

    def test_date_min_example(self, evaluator: FHIRPathEvaluator) -> None:
        """`( @2012-12-31 | @2013-01-01 | @2012-01-01 ).min()` answers `@2012-01-01`."""
        expression = "(@2012-12-31 | @2013-01-01 | @2012-01-01).min()"
        assert evaluator.evaluate(expression, {"resourceType": "Patient"}) == [FHIRDate(year=2012, month=1, day=1)]

    def test_date_max_example(self, evaluator: FHIRPathEvaluator) -> None:
        """`( @2012-12-31 | @2013-01-01 | @2012-01-01 ).max()` answers `@2013-01-01`."""
        expression = "(@2012-12-31 | @2013-01-01 | @2012-01-01).max()"
        assert evaluator.evaluate(expression, {"resourceType": "Patient"}) == [FHIRDate(year=2013, month=1, day=1)]


class TestOverADocument:
    """The aggregates read a navigated collection, not only a literal one."""

    @pytest.fixture
    def response(self) -> dict[str, Any]:
        """A QuestionnaireResponse whose answers are the numbers being aggregated."""
        return {
            "resourceType": "QuestionnaireResponse",
            "status": "completed",
            "item": [
                {"linkId": "bcg", "answer": [{"valueInteger": 3}]},
                {"linkId": "measles", "item": [{"linkId": "dose-1", "answer": [{"valueInteger": 4}]}]},
                {"linkId": "penta", "answer": [{"valueInteger": 11}]},
            ],
        }

    def test_sum_over_descendants(self, evaluator: FHIRPathEvaluator, response: dict[str, Any]) -> None:
        """The whole nested form totals in one expression."""
        expression = "QuestionnaireResponse.descendants().answer.valueInteger.sum()"
        assert evaluator.evaluate(expression, response) == [18]

    @pytest.mark.parametrize(
        ("function", "expected"),
        [("min", [3]), ("max", [11]), ("avg", [Decimal("6")])],
    )
    def test_other_aggregates_over_descendants(
        self, evaluator: FHIRPathEvaluator, response: dict[str, Any], function: str, expected: list[Any]
    ) -> None:
        """min, max and avg read the same navigated collection sum does."""
        expression = f"QuestionnaireResponse.descendants().answer.valueInteger.{function}()"
        assert evaluator.evaluate(expression, response) == expected

    def test_primitive_extension_wrapper_is_unwrapped(self, context: EvaluationContext) -> None:
        """A FHIR primitive carrying its own extensions aggregates as the number it wraps."""
        collection = [_PrimitiveWithExtension(3, {}), _PrimitiveWithExtension(4, {})]
        assert fn_sum(context, collection) == [7]


class TestTypeRules:
    """Section 7: all items SHALL be the same type, otherwise an exception is thrown."""

    @pytest.mark.parametrize("function", [fn_sum, fn_min, fn_max, fn_avg])
    def test_mixed_types_are_refused(self, context: EvaluationContext, function: Any) -> None:
        """A number beside a string is not a collection any aggregate has a rule for."""
        with pytest.raises(FHIRPathError, match="one type across the collection"):
            function(context, [1, "two"])

    @pytest.mark.parametrize("function", [fn_sum, fn_avg])
    def test_booleans_are_refused(self, context: EvaluationContext, function: Any) -> None:
        """Booleans are not the numbers Python's `bool` subclassing would otherwise make them."""
        with pytest.raises(FHIRPathError, match="no rule for Boolean"):
            function(context, [True, False])

    @pytest.mark.parametrize("function", [fn_sum, fn_avg])
    def test_strings_are_refused_by_the_additive_aggregates(self, context: EvaluationContext, function: Any) -> None:
        """sum and avg take the numeric family and Quantity, and nothing else."""
        with pytest.raises(FHIRPathError, match="no rule for String"):
            function(context, ["a", "b"])

    @pytest.mark.parametrize(("function", "expected"), [(fn_min, ["a"]), (fn_max, ["c"])])
    def test_strings_order_for_min_and_max(
        self, context: EvaluationContext, function: Any, expected: list[str]
    ) -> None:
        """min and max take every type section 7 lists comparison semantics for, strings included."""
        assert function(context, ["b", "a", "c"]) == expected

    def test_integers_and_decimals_are_one_numeric_family(self, context: EvaluationContext) -> None:
        """FHIRPath converts Integer to Decimal implicitly, so a mixed numeric collection totals."""
        assert fn_sum(context, [1, Decimal("2.5")]) == [Decimal("3.5")]

    def test_integer_sum_stays_an_integer(self, context: EvaluationContext) -> None:
        """An all-Integer collection answers in Integer, per the section's `(in the same type)`."""
        total = fn_sum(context, [1, 2, 3])
        assert total == [6]
        assert isinstance(total[0], int)

    def test_avg_answers_in_decimal(self, context: EvaluationContext) -> None:
        """avg converts Integer and Long to Decimal on the way in, so its answer is Decimal."""
        average = fn_avg(context, [1, 2])
        assert average == [Decimal("1.5")]
        assert isinstance(average[0], Decimal)


class TestQuantities:
    """Quantity is one of the types section 7 accepts, on the engine's own unit rules."""

    def test_sum_refuses_two_units(self, context: EvaluationContext) -> None:
        """Adding quantities is the `+` operator's rule - one unit - applied down a collection."""
        collection = [Quantity(value=Decimal(1), unit="mg"), Quantity(value=Decimal(1), unit="cm")]
        with pytest.raises(FHIRPathError, match="adds quantities in one unit"):
            fn_sum(context, collection)

    def test_avg_refuses_two_units(self, context: EvaluationContext) -> None:
        """avg divides a sum, so it refuses exactly what sum refuses."""
        collection = [Quantity(value=Decimal(1), unit="mg"), Quantity(value=Decimal(1), unit="cm")]
        with pytest.raises(FHIRPathError, match="adds quantities in one unit"):
            fn_avg(context, collection)

    def test_min_converts_comparable_units(self, context: EvaluationContext) -> None:
        """min compares rather than adds, and quantity comparison converts between comparable units."""
        collection = [Quantity(value=Decimal(1), unit="g"), Quantity(value=Decimal(1), unit="mg")]
        assert fn_min(context, collection) == [Quantity(value=Decimal(1), unit="mg")]

    def test_min_refuses_incomparable_units(self, context: EvaluationContext) -> None:
        """Milligrams and centimetres have no ordering between them, and the refusal says so."""
        collection = [Quantity(value=Decimal(1), unit="mg"), Quantity(value=Decimal(1), unit="cm")]
        with pytest.raises(FHIRPathError, match="cannot order this collection"):
            fn_min(context, collection)
