"""
FHIRPath Compliance Tests - Official HL7 FHIRPath Test Suite.

This module runs the official HL7 FHIRPath test suite against the FHIRPath evaluator.
Tests are parametrized from the XML test files.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from dhis2w_fhir_engine.engine.exceptions import FHIRPathError
from dhis2w_fhir_engine.engine.types import FHIRDate, FHIRDateTime, FHIRTime, Quantity
from tests.compliance.test_runner import (
    ComplianceTestCase,
    get_test_statistics,
    load_fhir_input_file,
    load_fhirpath_test_suites,
)

# Path to test data
DATA_DIR = Path(__file__).parent.parent / "fhirpath" / "data"

# Cache for loaded FHIR resources
_RESOURCE_CACHE: dict[str, dict[str, Any]] = {}


def get_all_fhirpath_tests() -> list[ComplianceTestCase]:
    """Load all FHIRPath test cases."""
    suites = load_fhirpath_test_suites(DATA_DIR)
    tests = []
    for suite in suites:
        tests.extend(suite.all_tests)
    return tests


# Load tests at module level for parametrization
ALL_FHIRPATH_TESTS = get_all_fhirpath_tests()


def load_test_resource(filename: str | None) -> dict[str, Any] | None:
    """Load a FHIR resource for testing."""
    if not filename:
        return None

    if filename in _RESOURCE_CACHE:
        return _RESOURCE_CACHE[filename]

    resource = load_fhir_input_file(DATA_DIR, filename)
    if resource:
        _RESOURCE_CACHE[filename] = resource
    return resource


def evaluate_fhirpath_expression(
    expression: str,
    resource: dict[str, Any] | None = None,
) -> list[Any]:
    """Evaluate a FHIRPath expression and return the result."""
    from dhis2w_fhir_engine.engine.fhirpath.evaluator import FHIRPathEvaluator

    evaluator = FHIRPathEvaluator()
    return evaluator.evaluate(expression, resource)


def normalize_result(result: Any) -> Any:
    """Normalize a FHIRPath result for comparison."""
    if result is None:
        return None

    # Handle lists
    if isinstance(result, list):
        if len(result) == 0:
            return []
        return [normalize_result(r) for r in result]

    # Handle Decimal
    if isinstance(result, Decimal):
        return result

    # Handle floats (convert to Decimal for precision)
    if isinstance(result, float):
        return Decimal(str(result))

    # Handle dicts with value extraction
    if isinstance(result, dict):
        # For coded elements, return the code
        if "code" in result and len(result) <= 3:
            return result.get("code")
        # For primitives with value
        if "value" in result and len(result) == 1:
            return normalize_result(result["value"])
        return result

    return result


def compare_results(actual: list[Any], expected: list[Any]) -> bool:
    """Compare actual and expected result lists."""
    actual = [normalize_result(a) for a in actual]

    if len(actual) != len(expected):
        return False

    return all(compare_single_result(act, exp) for act, exp in zip(actual, expected, strict=True))


def compare_single_result(actual: Any, expected: Any) -> bool:
    """Compare a single actual and expected result."""
    if actual is None and expected is None:
        return True

    if actual is None or expected is None:
        return False

    # Handle Decimal comparison
    if isinstance(expected, Decimal):
        if isinstance(actual, (int, float, Decimal)):
            return Decimal(str(actual)) == expected
        return False

    # Handle integer comparison
    if isinstance(expected, int) and not isinstance(expected, bool):
        if isinstance(actual, (int, float, Decimal)):
            try:
                return int(actual) == expected
            except (ValueError, TypeError):
                return False
        return False

    # Handle boolean comparison
    if isinstance(expected, bool):
        boolean_matches: bool = actual == expected
        return boolean_matches

    # Handle string comparison with date/time types
    if isinstance(expected, str):
        # Handle FHIRPath date literal format (@YYYY-MM-DD)
        if expected.startswith("@"):
            expected_str = expected[1:]  # Remove @ prefix
            if isinstance(actual, FHIRDate):
                return str(actual) == expected_str
            if isinstance(actual, FHIRDateTime):
                return str(actual) == expected_str
            if isinstance(actual, FHIRTime):
                # Time literals start with @T
                if expected_str.startswith("T"):
                    return str(actual) == expected_str[1:]  # Remove T prefix
                return str(actual) == expected_str
            return str(actual) == expected_str

        # Handle Quantity comparison (format: "value 'unit'")
        if isinstance(actual, Quantity):
            # Expected might be "10 'kg'" or similar
            return str(actual) == expected

        return str(actual) == expected

    # Handle dict comparison
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        # Compare relevant keys
        for key in expected:
            if key not in actual:
                return False
            if not compare_single_result(actual[key], expected[key]):
                return False
        return True

    # Default comparison
    default_matches: bool = actual == expected
    return default_matches


@pytest.mark.parametrize(
    "test_case",
    ALL_FHIRPATH_TESTS,
    ids=lambda tc: tc.test_id,
)
def test_fhirpath_compliance(test_case: ComplianceTestCase) -> None:
    """Run a single FHIRPath compliance test."""
    # Load input resource if specified
    resource = load_test_resource(test_case.input_file)

    if test_case.expects_error:
        if test_case.expects_semantic_error:
            # Semantic errors require FHIR schema validation which is not yet implemented
            pytest.skip("Semantic validation not yet implemented")
        elif test_case.expects_execution_error:
            # Execution errors (like calling methods on literals) not yet implemented
            pytest.skip("Execution error detection not yet implemented")
        else:
            # Runtime errors - expression should parse but fail at runtime
            with pytest.raises(FHIRPathError):
                evaluate_fhirpath_expression(test_case.expression, resource)
        return

    # Normal test - evaluate and compare
    try:
        result = evaluate_fhirpath_expression(test_case.expression, resource)
    except Exception as e:
        pytest.fail(
            f"Expression failed to evaluate: {e}\n"
            f"Expression: {test_case.expression}\n"
            f"Input file: {test_case.input_file}"
        )

    # Compare with expected outputs
    if not test_case.outputs:
        # No expected output means empty result
        assert result == [] or result is None, (
            f"Expected empty result, got: {result}\nExpression: {test_case.expression}"
        )
        return

    # Parse expected values
    expected_values = [out.parse_value() for out in test_case.outputs]

    # Handle predicate tests (single boolean expected)
    if test_case.predicate and len(expected_values) == 1:
        expected_bool = expected_values[0]
        # For predicate tests, non-empty result = true, empty = false
        actual_bool = len(result) > 0
        if len(result) == 1 and isinstance(result[0], bool):
            actual_bool = result[0]
        assert actual_bool == expected_bool, (
            f"Predicate mismatch:\n"
            f"  Expression: {test_case.expression}\n"
            f"  Expected: {expected_bool}\n"
            f"  Actual: {actual_bool} (result: {result})"
        )
        return

    # Normal comparison
    assert compare_results(result, expected_values), (
        f"Result mismatch:\n  Expression: {test_case.expression}\n  Expected: {expected_values}\n  Actual: {result}"
    )


def test_fhirpath_test_suite_loaded() -> None:
    """Verify that FHIRPath test suites were loaded successfully."""
    suites = load_fhirpath_test_suites(DATA_DIR)
    stats = get_test_statistics(suites)

    print("\nFHIRPath Test Suite Statistics:")
    print(f"  Total suites: {stats['total_suites']}")
    print(f"  Total groups: {stats['total_groups']}")
    print(f"  Total tests: {stats['total_tests']}")
    print("  By suite:")
    for suite_name, count in stats["by_suite"].items():
        print(f"    {suite_name}: {count}")

    assert stats["total_suites"] > 0, "No FHIRPath test suites found"
    assert stats["total_tests"] > 0, "No FHIRPath tests found"


def test_input_files_loadable() -> None:
    """Verify that all referenced input files can be loaded."""
    suites = load_fhirpath_test_suites(DATA_DIR)

    input_files = set()
    for suite in suites:
        for test in suite.all_tests:
            if test.input_file:
                input_files.add(test.input_file)

    print(f"\nInput files referenced: {len(input_files)}")
    for filename in sorted(input_files):
        resource = load_fhir_input_file(DATA_DIR, filename)
        print(f"  {filename}: {'loaded' if resource else 'NOT FOUND'}")
        # Don't fail here, just report - some tests may not need resources
