"""Tests for CQL external functions.

External functions are declared in CQL without a body and must be
implemented via the plugin registry.

Tests cover:
- Basic external function declaration and calling
- External function with multiple parameters
- Error when external function has no implementation
- Mixing external and regular functions
"""

import pytest

from dhis2w_fhir_engine.engine.cql import CQLEvaluator
from dhis2w_fhir_engine.engine.cql.plugins import CQLPluginRegistry
from dhis2w_fhir_engine.engine.exceptions import CQLError


class TestExternalFunctions:
    """Test CQL external function support."""

    def test_external_function_basic(self) -> None:
        """Test basic external function declaration and execution."""
        registry = CQLPluginRegistry()
        registry.register("Double", lambda x: x * 2)

        evaluator = CQLEvaluator(plugin_registry=registry)

        cql = """
        library Test version '1.0.0'

        define function Double(x Integer) returns Integer: external

        define Result: Double(21)
        """
        evaluator.compile(cql)
        result = evaluator.evaluate_definition("Result", {})
        assert result == 42

    def test_external_function_multiple_params(self) -> None:
        """Test external function with multiple parameters."""
        registry = CQLPluginRegistry()
        registry.register("Add", lambda a, b, c: a + b + c)

        evaluator = CQLEvaluator(plugin_registry=registry)

        cql = """
        library Test version '1.0.0'

        define function Add(a Integer, b Integer, c Integer) returns Integer: external

        define Result: Add(10, 20, 12)
        """
        evaluator.compile(cql)
        result = evaluator.evaluate_definition("Result", {})
        assert result == 42

    def test_external_function_no_implementation_error(self) -> None:
        """Test that calling unimplemented external function raises error."""
        evaluator = CQLEvaluator()

        cql = """
        library Test version '1.0.0'

        define function NotImplemented(x Integer) returns Integer: external

        define Result: NotImplemented(42)
        """
        evaluator.compile(cql)

        with pytest.raises(CQLError) as exc_info:
            evaluator.evaluate_definition("Result", {})

        assert "External function 'NotImplemented' declared but no implementation found" in str(exc_info.value)

    def test_external_function_string_return(self) -> None:
        """Test external function returning a string."""
        registry = CQLPluginRegistry()
        registry.register("FormatName", lambda first, last: f"{last}, {first}")

        evaluator = CQLEvaluator(plugin_registry=registry)

        cql = """
        library Test version '1.0.0'

        define function FormatName(first String, last String) returns String: external

        define Result: FormatName('John', 'Doe')
        """
        evaluator.compile(cql)
        result = evaluator.evaluate_definition("Result", {})
        assert result == "Doe, John"

    def test_external_function_with_null_handling(self) -> None:
        """Test external function that handles null values."""
        registry = CQLPluginRegistry()
        registry.register("SafeDouble", lambda x: x * 2 if x is not None else None)

        evaluator = CQLEvaluator(plugin_registry=registry)

        cql = """
        library Test version '1.0.0'

        define function SafeDouble(x Integer) returns Integer: external

        define ResultValid: SafeDouble(21)
        define ResultNull: SafeDouble(null)
        """
        evaluator.compile(cql)

        assert evaluator.evaluate_definition("ResultValid", {}) == 42
        assert evaluator.evaluate_definition("ResultNull", {}) is None

    def test_mixed_external_and_regular_functions(self) -> None:
        """Test mixing external and regular CQL functions."""
        registry = CQLPluginRegistry()
        registry.register("ExternalSquare", lambda x: x * x)

        evaluator = CQLEvaluator(plugin_registry=registry)

        cql = """
        library Test version '1.0.0'

        define function ExternalSquare(x Integer) returns Integer: external

        define function LocalDouble(x Integer) returns Integer:
            x * 2

        define Result: LocalDouble(ExternalSquare(3))
        """
        evaluator.compile(cql)
        result = evaluator.evaluate_definition("Result", {})
        # ExternalSquare(3) = 9, LocalDouble(9) = 18
        assert result == 18

    def test_external_function_in_query(self) -> None:
        """Test using external function in a query expression."""
        registry = CQLPluginRegistry()
        registry.register("IsEven", lambda x: x % 2 == 0)

        evaluator = CQLEvaluator(plugin_registry=registry)

        cql = """
        library Test version '1.0.0'

        define function IsEven(x Integer) returns Boolean: external

        define Numbers: { 1, 2, 3, 4, 5, 6 }

        define EvenNumbers:
            from Numbers N
            where IsEven(N)
            return N
        """
        evaluator.compile(cql)
        result = evaluator.evaluate_definition("EvenNumbers", {})
        assert result == [2, 4, 6]

    def test_external_function_decimal_math(self) -> None:
        """Test external function with decimal math operations."""
        import math

        registry = CQLPluginRegistry()
        registry.register("Sqrt", lambda x: math.sqrt(float(x)) if x is not None and x >= 0 else None)

        evaluator = CQLEvaluator(plugin_registry=registry)

        cql = """
        library Test version '1.0.0'

        define function Sqrt(x Decimal) returns Decimal: external

        define Result: Sqrt(16.0)
        """
        evaluator.compile(cql)
        result = evaluator.evaluate_definition("Result", {})
        assert result == pytest.approx(4.0)

    def test_external_function_list_parameter(self) -> None:
        """Test external function that accepts a list."""
        registry = CQLPluginRegistry()
        registry.register("CustomSum", lambda lst: sum(lst) if lst else 0)

        evaluator = CQLEvaluator(plugin_registry=registry)

        cql = """
        library Test version '1.0.0'

        define function CustomSum(values List<Integer>) returns Integer: external

        define Numbers: { 1, 2, 3, 4, 5 }
        define Result: CustomSum(Numbers)
        """
        evaluator.compile(cql)
        result = evaluator.evaluate_definition("Result", {})
        assert result == 15

    def test_external_function_fluent(self) -> None:
        """Test fluent external function."""
        registry = CQLPluginRegistry()
        registry.register("squared", lambda x: x * x)

        evaluator = CQLEvaluator(plugin_registry=registry)

        cql = """
        library Test version '1.0.0'

        define fluent function squared(x Integer) returns Integer: external

        define Result: 5.squared()
        """
        evaluator.compile(cql)
        result = evaluator.evaluate_definition("Result", {})
        assert result == 25


class TestExternalFunctionEdgeCases:
    """Test edge cases for external functions."""

    def test_external_function_same_name_different_arity(self) -> None:
        """Test external functions with same name but different arity."""
        registry = CQLPluginRegistry()
        # Note: Plugin registry doesn't distinguish by arity, so this tests
        # that the correct plugin is found regardless
        registry.register("Combine", lambda *args: sum(args))

        evaluator = CQLEvaluator(plugin_registry=registry)

        cql = """
        library Test version '1.0.0'

        define function Combine(a Integer, b Integer) returns Integer: external

        define Result: Combine(10, 32)
        """
        evaluator.compile(cql)
        result = evaluator.evaluate_definition("Result", {})
        assert result == 42

    def test_external_function_no_return_type(self) -> None:
        """Test external function without explicit return type."""
        registry = CQLPluginRegistry()
        registry.register("GetValue", lambda: 42)

        evaluator = CQLEvaluator(plugin_registry=registry)

        cql = """
        library Test version '1.0.0'

        define function GetValue(): external

        define Result: GetValue()
        """
        evaluator.compile(cql)
        result = evaluator.evaluate_definition("Result", {})
        assert result == 42
