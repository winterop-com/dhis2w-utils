"""Tests for CQL library include resolution.

Tests cover:
- Expression references to included libraries
- Function calls to included libraries
- Library aliases with 'called' keyword
- Multiple included libraries
- Chained library dependencies
"""

import pytest

from dhis2w_fhir_engine.engine.cql import CQLEvaluator
from dhis2w_fhir_engine.engine.cql.library_resolver import InMemoryLibraryResolver


class TestCQLLibraryIncludes:
    """Test CQL include statement resolution."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.resolver = InMemoryLibraryResolver()
        self.evaluator = CQLEvaluator(library_resolver=self.resolver)

    def test_expression_ref_without_alias(self) -> None:
        """Test referencing a definition from included library without alias."""
        # Helper library
        helper = """
        library Helper version '1.0.0'
        define Value: 42
        """
        self.resolver.add_library("Helper", "1.0.0", helper)
        self.evaluator.compile(helper)

        # Main library
        main = """
        library Main version '1.0.0'
        include Helper version '1.0.0'
        define Test: Helper.Value
        """
        self.evaluator.compile(main)

        result = self.evaluator.evaluate_definition("Test", {})
        assert result == 42

    def test_expression_ref_with_alias(self) -> None:
        """Test referencing a definition from included library with alias."""
        # Helper library
        helper = """
        library MathUtils version '2.0.0'
        define Pi: 3.14159
        """
        self.resolver.add_library("MathUtils", "2.0.0", helper)
        self.evaluator.compile(helper)

        # Main library
        main = """
        library Main version '1.0.0'
        include MathUtils version '2.0.0' called Math
        define Test: Math.Pi
        """
        self.evaluator.compile(main)

        result = self.evaluator.evaluate_definition("Test", {})
        assert float(result) == pytest.approx(3.14159)

    def test_function_call_without_alias(self) -> None:
        """Test calling a function from included library without alias."""
        # Helper library with function
        helper = """
        library Helper version '1.0.0'
        define function Double(x Integer) returns Integer:
            x * 2
        """
        self.resolver.add_library("Helper", "1.0.0", helper)
        self.evaluator.compile(helper)

        # Main library
        main = """
        library Main version '1.0.0'
        include Helper version '1.0.0'
        define Test: Helper.Double(21)
        """
        self.evaluator.compile(main)

        result = self.evaluator.evaluate_definition("Test", {})
        assert result == 42

    def test_function_call_with_alias(self) -> None:
        """Test calling a function from included library with alias."""
        # Helper library with function
        helper = """
        library StringUtils version '1.0.0'
        define function Greet(name String) returns String:
            'Hello, ' + name
        """
        self.resolver.add_library("StringUtils", "1.0.0", helper)
        self.evaluator.compile(helper)

        # Main library
        main = """
        library Main version '1.0.0'
        include StringUtils version '1.0.0' called Str
        define Test: Str.Greet('World')
        """
        self.evaluator.compile(main)

        result = self.evaluator.evaluate_definition("Test", {})
        assert result == "Hello, World"

    def test_multiple_libraries(self) -> None:
        """Test including multiple libraries."""
        # Math library
        math = """
        library MathLib version '1.0.0'
        define Pi: 3.14159
        define function Square(x Decimal) returns Decimal:
            x * x
        """
        self.resolver.add_library("MathLib", "1.0.0", math)
        self.evaluator.compile(math)

        # String library
        strings = """
        library StringLib version '1.0.0'
        define Separator: '-'
        define function Upper(s String) returns String:
            s
        """
        self.resolver.add_library("StringLib", "1.0.0", strings)
        self.evaluator.compile(strings)

        # Main library including both
        main = """
        library Main version '1.0.0'
        include MathLib version '1.0.0' called Math
        include StringLib version '1.0.0' called Str

        define TestMath: Math.Square(4.0)
        define TestStr: Str.Separator
        """
        self.evaluator.compile(main)

        result1 = self.evaluator.evaluate_definition("TestMath", {})
        result2 = self.evaluator.evaluate_definition("TestStr", {})

        assert float(result1) == pytest.approx(16.0)
        assert result2 == "-"

    def test_function_with_multiple_args(self) -> None:
        """Test calling external function with multiple arguments."""
        helper = """
        library Helper version '1.0.0'
        define function Add(a Integer, b Integer) returns Integer:
            a + b
        """
        self.resolver.add_library("Helper", "1.0.0", helper)
        self.evaluator.compile(helper)

        main = """
        library Main version '1.0.0'
        include Helper version '1.0.0'
        define Test: Helper.Add(10, 32)
        """
        self.evaluator.compile(main)

        result = self.evaluator.evaluate_definition("Test", {})
        assert result == 42

    def test_external_definition_uses_local_definition(self) -> None:
        """Test external definition that references its own local definitions."""
        helper = """
        library Helper version '1.0.0'
        define Base: 10
        define Calculated: Base * 2
        """
        self.resolver.add_library("Helper", "1.0.0", helper)
        self.evaluator.compile(helper)

        main = """
        library Main version '1.0.0'
        include Helper version '1.0.0'
        define Test: Helper.Calculated
        """
        self.evaluator.compile(main)

        result = self.evaluator.evaluate_definition("Test", {})
        assert result == 20

    def test_local_and_external_definitions(self) -> None:
        """Test mixing local and external definitions."""
        helper = """
        library Helper version '1.0.0'
        define ExternalValue: 100
        """
        self.resolver.add_library("Helper", "1.0.0", helper)
        self.evaluator.compile(helper)

        main = """
        library Main version '1.0.0'
        include Helper version '1.0.0'

        define LocalValue: 50
        define Combined: LocalValue + Helper.ExternalValue
        """
        self.evaluator.compile(main)

        result = self.evaluator.evaluate_definition("Combined", {})
        assert result == 150

    def test_chained_library_dependencies(self) -> None:
        """Test library A includes library B which includes library C."""
        # Base library
        base = """
        library Base version '1.0.0'
        define BaseValue: 10
        """
        self.resolver.add_library("Base", "1.0.0", base)
        self.evaluator.compile(base)

        # Middle library that includes Base
        middle = """
        library Middle version '1.0.0'
        include Base version '1.0.0'
        define MiddleValue: Base.BaseValue * 2
        """
        self.resolver.add_library("Middle", "1.0.0", middle)
        self.evaluator.compile(middle)

        # Top library that includes Middle
        top = """
        library Top version '1.0.0'
        include Middle version '1.0.0'
        define TopValue: Middle.MiddleValue + 5
        """
        self.evaluator.compile(top)

        result = self.evaluator.evaluate_definition("TopValue", {})
        assert result == 25  # (10 * 2) + 5

    def test_definition_caching(self) -> None:
        """Test that external definitions are cached."""
        helper = """
        library Helper version '1.0.0'
        define Value: 42
        """
        self.resolver.add_library("Helper", "1.0.0", helper)
        self.evaluator.compile(helper)

        main = """
        library Main version '1.0.0'
        include Helper version '1.0.0'
        define Test1: Helper.Value
        define Test2: Helper.Value + 1
        """
        self.evaluator.compile(main)

        # Both should work and use cached value for Helper.Value
        result1 = self.evaluator.evaluate_definition("Test1", {})
        result2 = self.evaluator.evaluate_definition("Test2", {})

        assert result1 == 42
        assert result2 == 43

    def test_external_function_calling_local_function(self) -> None:
        """Test external function that calls its own local function."""
        helper = """
        library Helper version '1.0.0'

        define function Square(x Integer) returns Integer:
            x * x

        define function SumOfSquares(a Integer, b Integer) returns Integer:
            Square(a) + Square(b)
        """
        self.resolver.add_library("Helper", "1.0.0", helper)
        self.evaluator.compile(helper)

        main = """
        library Main version '1.0.0'
        include Helper version '1.0.0'
        define Test: Helper.SumOfSquares(3, 4)
        """
        self.evaluator.compile(main)

        result = self.evaluator.evaluate_definition("Test", {})
        assert result == 25  # 3^2 + 4^2 = 9 + 16 = 25

    def test_builtin_function_from_external_context(self) -> None:
        """Test that builtin functions work in external library context."""
        helper = """
        library Helper version '1.0.0'
        define Numbers: {1, 2, 3, 4, 5}
        define Total: Sum(Numbers)
        """
        self.resolver.add_library("Helper", "1.0.0", helper)
        self.evaluator.compile(helper)

        main = """
        library Main version '1.0.0'
        include Helper version '1.0.0'
        define Test: Helper.Total
        """
        self.evaluator.compile(main)

        result = self.evaluator.evaluate_definition("Test", {})
        assert result == 15
