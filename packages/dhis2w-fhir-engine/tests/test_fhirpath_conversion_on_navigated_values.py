"""Tests for the FHIRPath conversion and math functions reading values that navigation wrapped."""

from decimal import Decimal
from typing import Any

import pytest

from dhis2w_fhir_engine import FHIRPathEvaluator
from dhis2w_fhir_engine.engine.context import EvaluationContext
from dhis2w_fhir_engine.engine.fhirpath.functions.boolean import (
    fn_converts_to_boolean,
    fn_converts_to_date,
    fn_converts_to_datetime,
    fn_converts_to_decimal,
    fn_converts_to_integer,
    fn_converts_to_quantity,
    fn_converts_to_string,
    fn_converts_to_time,
    fn_to_boolean,
    fn_to_date,
    fn_to_datetime,
    fn_to_decimal,
    fn_to_integer,
    fn_to_quantity,
    fn_to_string,
    fn_to_time,
)
from dhis2w_fhir_engine.engine.fhirpath.functions.math import (
    fn_abs,
    fn_ceiling,
    fn_exp,
    fn_floor,
    fn_high_boundary,
    fn_ln,
    fn_log,
    fn_low_boundary,
    fn_power,
    fn_precision,
    fn_round,
    fn_sqrt,
    fn_truncate,
)
from dhis2w_fhir_engine.engine.fhirpath.visitor import _PrimitiveWithExtension
from dhis2w_fhir_engine.engine.types import Quantity

PATIENT: dict[str, Any] = {
    "resourceType": "Patient",
    "active": True,
    "deceasedBoolean": False,
    "birthDate": "1974-12-25",
    "_birthDate": {"extension": [{"url": "http://example.org/precision", "valueCode": "day"}]},
    "multipleBirthInteger": 3,
}

OBSERVATION: dict[str, Any] = {
    "resourceType": "Observation",
    "status": "final",
    "effectiveDateTime": "2024-03-15T10:30:00Z",
    "valueQuantity": {"value": -2.5, "unit": "kg", "system": "http://unitsofmeasure.org", "code": "kg"},
}


@pytest.fixture
def context() -> EvaluationContext:
    return EvaluationContext(resource=PATIENT)


def wrapped(value: Any, element_name: str = "element") -> _PrimitiveWithExtension:
    """Wrap a value the way navigation wraps a FHIR primitive that carries extensions."""
    return _PrimitiveWithExtension(value, {"extension": []}, element_name, "Patient")


class TestConversionOnWrappedPrimitives:
    """Each conversion reads the value a wrapper holds, per the FHIRPath 2.0.0 conversion table."""

    def test_to_boolean_reads_a_wrapped_boolean(self, context: EvaluationContext) -> None:
        assert fn_to_boolean(context, [wrapped(True, "active")]) == [True]
        assert fn_to_boolean(context, [wrapped(False, "active")]) == [False]

    def test_to_boolean_reads_a_wrapped_string(self, context: EvaluationContext) -> None:
        assert fn_to_boolean(context, [wrapped("yes", "code")]) == [True]
        assert fn_to_boolean(context, [wrapped("n", "code")]) == [False]
        assert fn_to_boolean(context, [wrapped("maybe", "code")]) == []

    def test_to_boolean_reads_a_wrapped_number(self, context: EvaluationContext) -> None:
        assert fn_to_boolean(context, [wrapped(1, "multipleBirthInteger")]) == [True]
        assert fn_to_boolean(context, [wrapped(0, "multipleBirthInteger")]) == [False]
        assert fn_to_boolean(context, [wrapped(7, "multipleBirthInteger")]) == []

    def test_to_integer_reads_a_wrapped_integer(self, context: EvaluationContext) -> None:
        assert fn_to_integer(context, [wrapped(3, "multipleBirthInteger")]) == [3]

    def test_to_integer_reads_a_wrapped_boolean(self, context: EvaluationContext) -> None:
        """The conversion table maps true to 1 and false to 0."""
        assert fn_to_integer(context, [wrapped(True, "active")]) == [1]
        assert fn_to_integer(context, [wrapped(False, "active")]) == [0]

    def test_to_integer_rejects_a_wrapped_string_holding_a_decimal_point(self, context: EvaluationContext) -> None:
        assert fn_to_integer(context, [wrapped("42", "code")]) == [42]
        assert fn_to_integer(context, [wrapped("42.0", "code")]) == []

    def test_to_decimal_reads_a_wrapped_number(self, context: EvaluationContext) -> None:
        assert fn_to_decimal(context, [wrapped(3, "multipleBirthInteger")]) == [Decimal(3)]
        assert fn_to_decimal(context, [wrapped("2.50", "code")]) == [Decimal("2.50")]

    def test_to_decimal_reads_a_wrapped_boolean(self, context: EvaluationContext) -> None:
        assert fn_to_decimal(context, [wrapped(True, "active")]) == [Decimal(1)]

    def test_to_string_reads_a_wrapped_value(self, context: EvaluationContext) -> None:
        assert fn_to_string(context, [wrapped("1974-12-25", "birthDate")]) == ["1974-12-25"]
        assert fn_to_string(context, [wrapped(3, "multipleBirthInteger")]) == ["3"]

    def test_to_string_spells_a_wrapped_boolean_in_lower_case(self, context: EvaluationContext) -> None:
        """The conversion table spells Boolean as 'true' and 'false'."""
        assert fn_to_string(context, [wrapped(True, "active")]) == ["true"]
        assert fn_to_string(context, [wrapped(False, "deceasedBoolean")]) == ["false"]

    def test_to_date_reads_a_wrapped_date(self, context: EvaluationContext) -> None:
        assert fn_to_date(context, [wrapped("1974-12-25", "birthDate")]) == ["1974-12-25"]
        assert fn_to_date(context, [wrapped("1974-12", "birthDate")]) == ["1974-12"]

    def test_to_date_takes_the_date_part_of_a_wrapped_datetime(self, context: EvaluationContext) -> None:
        """The conversion table takes the Date portion of a DateTime."""
        assert fn_to_date(context, [wrapped("2024-03-15T10:30:00Z", "effectiveDateTime")]) == ["2024-03-15"]

    def test_to_datetime_reads_a_wrapped_datetime(self, context: EvaluationContext) -> None:
        assert fn_to_datetime(context, [wrapped("2024-03-15T10:30:00Z", "effectiveDateTime")]) == [
            "2024-03-15T10:30:00Z"
        ]
        assert fn_to_datetime(context, [wrapped("1974-12-25", "birthDate")]) == ["1974-12-25"]

    def test_to_time_reads_a_wrapped_time(self, context: EvaluationContext) -> None:
        assert fn_to_time(context, [wrapped("10:30:00", "time")]) == ["10:30:00"]
        assert fn_to_time(context, [wrapped("not a time", "time")]) == []

    def test_to_quantity_reads_a_wrapped_number(self, context: EvaluationContext) -> None:
        assert fn_to_quantity(context, [wrapped(3, "multipleBirthInteger")]) == [Quantity(value=Decimal(3), unit="1")]

    def test_to_quantity_reads_a_wrapped_string_carrying_a_unit(self, context: EvaluationContext) -> None:
        assert fn_to_quantity(context, [wrapped("4 'kg'", "code")]) == [Quantity(value=Decimal(4), unit="kg")]


class TestConvertsToPredicatesOnWrappedPrimitives:
    """Each convertsTo predicate answers for the value a wrapper holds, not for the wrapper."""

    def test_converts_to_boolean(self, context: EvaluationContext) -> None:
        assert fn_converts_to_boolean(context, [wrapped(True, "active")]) == [True]
        assert fn_converts_to_boolean(context, [wrapped("maybe", "code")]) == [False]

    def test_converts_to_integer(self, context: EvaluationContext) -> None:
        assert fn_converts_to_integer(context, [wrapped(3, "multipleBirthInteger")]) == [True]
        assert fn_converts_to_integer(context, [wrapped("three", "code")]) == [False]

    def test_converts_to_decimal(self, context: EvaluationContext) -> None:
        assert fn_converts_to_decimal(context, [wrapped("2.5", "code")]) == [True]
        assert fn_converts_to_decimal(context, [wrapped("two point five", "code")]) == [False]

    def test_converts_to_string(self, context: EvaluationContext) -> None:
        assert fn_converts_to_string(context, [wrapped("1974-12-25", "birthDate")]) == [True]

    def test_converts_to_date(self, context: EvaluationContext) -> None:
        assert fn_converts_to_date(context, [wrapped("1974-12-25", "birthDate")]) == [True]
        assert fn_converts_to_date(context, [wrapped("Christmas", "birthDate")]) == [False]

    def test_converts_to_datetime(self, context: EvaluationContext) -> None:
        assert fn_converts_to_datetime(context, [wrapped("2024-03-15T10:30:00Z", "effectiveDateTime")]) == [True]

    def test_converts_to_time(self, context: EvaluationContext) -> None:
        assert fn_converts_to_time(context, [wrapped("10:30:00", "time")]) == [True]
        assert fn_converts_to_time(context, [wrapped("half past ten", "time")]) == [False]

    def test_converts_to_quantity(self, context: EvaluationContext) -> None:
        assert fn_converts_to_quantity(context, [wrapped(3, "multipleBirthInteger")]) == [True]
        assert fn_converts_to_quantity(context, [wrapped("a few", "code")]) == [False]


class TestConversionOnRawLiterals:
    """Raw literals keep converting the way they always have."""

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("true.toBoolean()", [True]),
            ("'yes'.toBoolean()", [True]),
            ("'1'.toInteger()", [1]),
            ("true.toInteger()", [1]),
            ("1.toDecimal()", [Decimal(1)]),
            ("true.toString()", ["true"]),
            ("'2024-03-15'.toDate()", ["2024-03-15"]),
            ("'2024-03-15T10:30:00Z'.toDateTime()", ["2024-03-15T10:30:00Z"]),
            ("'10:30:00'.toTime()", ["10:30:00"]),
            ("'2024-03-15'.convertsToDate()", [True]),
            ("'apple'.convertsToInteger()", [False]),
            ("{}.toString()", []),
            ("{}.convertsToBoolean()", [False]),
        ],
    )
    def test_literal_conversions(self, expression: str, expected: list[Any]) -> None:
        assert FHIRPathEvaluator().evaluate(expression, PATIENT) == expected


class TestConversionThroughNavigation:
    """A conversion applied to a navigated element reads the element's value."""

    @pytest.mark.parametrize(
        ("expression", "resource", "expected"),
        [
            ("Patient.active.toBoolean()", PATIENT, [True]),
            ("Patient.deceasedBoolean.toBoolean()", PATIENT, [False]),
            ("Patient.active.toInteger()", PATIENT, [1]),
            ("Patient.active.toString()", PATIENT, ["true"]),
            ("Patient.birthDate.toString()", PATIENT, ["1974-12-25"]),
            ("Patient.birthDate.toDate()", PATIENT, ["1974-12-25"]),
            ("Patient.birthDate.toDateTime()", PATIENT, ["1974-12-25"]),
            ("Patient.multipleBirthInteger.toInteger()", PATIENT, [3]),
            ("Patient.multipleBirthInteger.toDecimal()", PATIENT, [Decimal(3)]),
            ("Patient.multipleBirthInteger.toString()", PATIENT, ["3"]),
            ("Patient.active.convertsToBoolean()", PATIENT, [True]),
            ("Patient.birthDate.convertsToDate()", PATIENT, [True]),
            ("Patient.multipleBirthInteger.convertsToInteger()", PATIENT, [True]),
            ("Observation.effectiveDateTime.toDateTime()", OBSERVATION, ["2024-03-15T10:30:00Z"]),
            ("Observation.status.toString()", OBSERVATION, ["final"]),
        ],
    )
    def test_navigated_conversions(self, expression: str, resource: dict[str, Any], expected: list[Any]) -> None:
        assert FHIRPathEvaluator().evaluate(expression, resource) == expected

    def test_a_conversion_result_feeds_the_next_function(self) -> None:
        assert FHIRPathEvaluator().evaluate("Patient.birthDate.toString().length()", PATIENT) == [10]


class TestMathOnWrappedPrimitives:
    """Each math function reads the number a wrapper holds."""

    def test_abs(self, context: EvaluationContext) -> None:
        assert fn_abs(context, [wrapped(-2.5, "value")]) == [2.5]

    def test_ceiling(self, context: EvaluationContext) -> None:
        assert fn_ceiling(context, [wrapped(-2.5, "value")]) == [-2]

    def test_floor(self, context: EvaluationContext) -> None:
        assert fn_floor(context, [wrapped(-2.5, "value")]) == [-3]

    def test_round(self, context: EvaluationContext) -> None:
        assert fn_round(context, [wrapped(2.567, "value")], 2) == [2.57]

    def test_truncate(self, context: EvaluationContext) -> None:
        assert fn_truncate(context, [wrapped(2.9, "value")]) == [2]

    def test_sqrt(self, context: EvaluationContext) -> None:
        assert fn_sqrt(context, [wrapped(9, "value")]) == [3.0]

    def test_ln(self, context: EvaluationContext) -> None:
        assert fn_ln(context, [wrapped(1, "value")]) == [0.0]

    def test_log(self, context: EvaluationContext) -> None:
        assert fn_log(context, [wrapped(100, "value")], 10) == [2.0]

    def test_power(self, context: EvaluationContext) -> None:
        assert fn_power(context, [wrapped(3, "value")], 2) == [9.0]

    def test_exp(self, context: EvaluationContext) -> None:
        assert fn_exp(context, [wrapped(0, "value")]) == [1.0]

    def test_precision(self, context: EvaluationContext) -> None:
        assert fn_precision(context, [wrapped(Decimal("1.587"), "value")]) == [3]

    def test_boundaries_still_read_a_wrapped_value(self, context: EvaluationContext) -> None:
        assert fn_low_boundary(context, [wrapped(Decimal("1.587"), "value")], 6) == [Decimal("1.586500")]
        assert fn_high_boundary(context, [wrapped(Decimal("1.587"), "value")], 6) == [Decimal("1.587500")]


class TestMathThroughNavigation:
    """A math function applied to a navigated element reads the element's number."""

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("Observation.valueQuantity.value.abs()", [2.5]),
            ("Observation.valueQuantity.value.ceiling()", [-2]),
            ("Observation.valueQuantity.value.floor()", [-3]),
            ("Observation.valueQuantity.value.truncate()", [-2]),
            ("Observation.valueQuantity.value.precision()", [1]),
        ],
    )
    def test_navigated_math(self, expression: str, expected: list[Any]) -> None:
        assert FHIRPathEvaluator().evaluate(expression, OBSERVATION) == expected

    def test_navigated_math_on_an_integer_element(self) -> None:
        assert FHIRPathEvaluator().evaluate("Patient.multipleBirthInteger.power(2)", PATIENT) == [9.0]


class TestMathOnRawLiterals:
    """Raw literals keep computing the way they always have."""

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("(-3).abs()", [3]),
            ("2.5.ceiling()", [3]),
            ("2.5.floor()", [2]),
            ("9.sqrt()", [3.0]),
            ("100.log(10)", [2.0]),
            ("{}.abs()", []),
            ("'text'.abs()", []),
        ],
    )
    def test_literal_math(self, expression: str, expected: list[Any]) -> None:
        assert FHIRPathEvaluator().evaluate(expression, PATIENT) == expected
