"""Tests for unwrapping FHIR primitives out of a FHIRPath result."""

from typing import Any

import pytest

from dhis2w_fhir_engine import FHIRPathEvaluator, unwrap_primitives

PATIENT: dict[str, Any] = {
    "resourceType": "Patient",
    "active": True,
    "name": [{"given": ["Ada", "Byron"], "family": "Lovelace"}],
    "birthDate": "1815-12-10",
    "_birthDate": {"extension": [{"url": "http://example.org/precision", "valueCode": "day"}]},
}


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("Patient.name.given", ["Ada", "Byron"]),
        ("Patient.name.family", ["Lovelace"]),
        ("Patient.birthDate", ["1815-12-10"]),
        ("Patient.active", [True]),
        ("Patient.name.given.first()", ["Ada"]),
    ],
)
def test_unwrap_primitives_yields_plain_python_values(expression: str, expected: list[Any]) -> None:
    result = FHIRPathEvaluator().evaluate(expression, PATIENT)
    assert unwrap_primitives(result) == expected
    assert all(type(value) in (str, bool, int, float) for value in unwrap_primitives(result))


def test_unwrap_primitives_leaves_complex_elements_alone() -> None:
    result = FHIRPathEvaluator().evaluate("Patient.name", PATIENT)
    assert unwrap_primitives(result) == [{"given": ["Ada", "Byron"], "family": "Lovelace"}]


def test_unwrap_primitives_reaches_inside_dicts_and_nested_lists() -> None:
    given = FHIRPathEvaluator().evaluate("Patient.name.given", PATIENT)
    assert unwrap_primitives({"names": given, "nested": [given]}) == {
        "names": ["Ada", "Byron"],
        "nested": [["Ada", "Byron"]],
    }


def test_unwrap_primitives_passes_through_unwrapped_values() -> None:
    assert unwrap_primitives(7) == 7
    assert unwrap_primitives(None) is None
    assert unwrap_primitives([]) == []


def test_extensions_stay_reachable_before_unwrapping() -> None:
    extensions = FHIRPathEvaluator().evaluate("Patient.birthDate.extension('http://example.org/precision')", PATIENT)
    assert unwrap_primitives(extensions) == [{"url": "http://example.org/precision", "valueCode": "day"}]
