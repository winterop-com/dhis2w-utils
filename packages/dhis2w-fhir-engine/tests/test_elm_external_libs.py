"""Tests for ELM external library references."""

import pytest

from dhis2w_fhir_engine.engine.cql.context import CQLContext
from dhis2w_fhir_engine.engine.elm.models.library import (
    ELMDefinition,
    ELMFunctionDef,
    ELMIdentifier,
    ELMInclude,
    ELMLibrary,
    ELMOperandDef,
    ELMStatements,
)
from dhis2w_fhir_engine.engine.elm.visitor import ELMExpressionVisitor


class TestExternalLibraryReferences:
    """Test external library reference support."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.context = CQLContext()
        self.visitor = ELMExpressionVisitor(self.context)

    def create_helper_library(self) -> ELMLibrary:
        """Create a helper library with definitions and functions."""
        return ELMLibrary(
            identifier=ELMIdentifier(id="Helpers", version="1.0"),
            statements=ELMStatements.model_validate(
                {
                    "def": [
                        ELMDefinition(
                            name="Pi",
                            expression={"type": "Literal", "valueType": "Decimal", "value": "3.14159"},
                        ),
                        ELMDefinition(
                            name="Ten",
                            expression={"type": "Literal", "valueType": "Integer", "value": "10"},
                        ),
                        ELMFunctionDef(
                            name="Double",
                            operand=[ELMOperandDef(name="x")],
                            expression={
                                "type": "Multiply",
                                "operand": [
                                    {"type": "OperandRef", "name": "x"},
                                    {"type": "Literal", "valueType": "Integer", "value": "2"},
                                ],
                            },
                        ),
                        ELMFunctionDef(
                            name="Add",
                            operand=[ELMOperandDef(name="a"), ELMOperandDef(name="b")],
                            expression={
                                "type": "Add",
                                "operand": [
                                    {"type": "OperandRef", "name": "a"},
                                    {"type": "OperandRef", "name": "b"},
                                ],
                            },
                        ),
                    ]
                }
            ),
        )

    def create_main_library(self) -> ELMLibrary:
        """Create a main library that includes Helpers."""
        return ELMLibrary(
            identifier=ELMIdentifier(id="Main", version="1.0"),
            includes=[ELMInclude(localIdentifier="Helpers", path="Helpers", version="1.0")],
            statements=ELMStatements.model_validate(
                {
                    "def": [
                        ELMDefinition(
                            name="LocalValue",
                            expression={"type": "Literal", "valueType": "Integer", "value": "42"},
                        ),
                    ]
                }
            ),
        )

    def test_add_and_get_included_library(self) -> None:
        """Test adding and retrieving included libraries."""
        helper = self.create_helper_library()

        self.visitor.add_included_library("Helpers", helper)

        retrieved = self.visitor.get_included_library("Helpers")
        assert retrieved is not None
        assert retrieved is helper
        assert retrieved.identifier.id == "Helpers"

    def test_get_nonexistent_included_library(self) -> None:
        """Test getting non-existent included library returns None."""
        result = self.visitor.get_included_library("DoesNotExist")
        assert result is None

    def test_clear_included_libraries(self) -> None:
        """Test clearing included libraries."""
        helper = self.create_helper_library()
        self.visitor.add_included_library("Helpers", helper)

        self.visitor.clear_included_libraries()

        assert self.visitor.get_included_library("Helpers") is None

    def test_expression_ref_to_external_library(self) -> None:
        """Test ExpressionRef with libraryName to external library."""
        main = self.create_main_library()
        helper = self.create_helper_library()

        self.visitor.set_library(main)
        self.visitor.add_included_library("Helpers", helper)

        # Reference Pi definition from Helpers library
        node = {
            "type": "ExpressionRef",
            "name": "Pi",
            "libraryName": "Helpers",
        }
        result = self.visitor.evaluate(node)
        assert abs(float(result) - 3.14159) < 0.0001

    def test_expression_ref_to_local_definition(self) -> None:
        """Test ExpressionRef without libraryName uses current library."""
        main = self.create_main_library()
        helper = self.create_helper_library()

        self.visitor.set_library(main)
        self.visitor.add_included_library("Helpers", helper)

        # Reference local definition
        node = {
            "type": "ExpressionRef",
            "name": "LocalValue",
        }
        result = self.visitor.evaluate(node)
        assert result == 42

    def test_function_ref_to_external_library(self) -> None:
        """Test FunctionRef with libraryName to external library."""
        main = self.create_main_library()
        helper = self.create_helper_library()

        self.visitor.set_library(main)
        self.visitor.add_included_library("Helpers", helper)

        # Call Double function from Helpers library
        node = {
            "type": "FunctionRef",
            "name": "Double",
            "libraryName": "Helpers",
            "operand": [{"type": "Literal", "valueType": "Integer", "value": "21"}],
        }
        result = self.visitor.evaluate(node)
        assert result == 42

    def test_function_ref_with_multiple_args(self) -> None:
        """Test FunctionRef to external function with multiple arguments."""
        main = self.create_main_library()
        helper = self.create_helper_library()

        self.visitor.set_library(main)
        self.visitor.add_included_library("Helpers", helper)

        # Call Add function from Helpers library
        node = {
            "type": "FunctionRef",
            "name": "Add",
            "libraryName": "Helpers",
            "operand": [
                {"type": "Literal", "valueType": "Integer", "value": "30"},
                {"type": "Literal", "valueType": "Integer", "value": "12"},
            ],
        }
        result = self.visitor.evaluate(node)
        assert result == 42

    def test_external_ref_caching(self) -> None:
        """Test that external definition results are cached."""
        main = self.create_main_library()
        helper = self.create_helper_library()

        self.visitor.set_library(main)
        self.visitor.add_included_library("Helpers", helper)

        node = {
            "type": "ExpressionRef",
            "name": "Ten",
            "libraryName": "Helpers",
        }

        # First evaluation
        result1 = self.visitor.evaluate(node)
        assert result1 == 10

        # Second evaluation should use cache
        result2 = self.visitor.evaluate(node)
        assert result2 == 10

        # Verify cache key includes library name
        cache_key = "Helpers.Ten"
        found, cached = self.context.get_cached_definition(cache_key)
        assert found
        assert cached == 10

    def test_external_ref_missing_library_error(self) -> None:
        """Test ExpressionRef to non-existent library raises error."""
        main = self.create_main_library()
        self.visitor.set_library(main)

        node = {
            "type": "ExpressionRef",
            "name": "SomeValue",
            "libraryName": "NonExistent",
        }

        from dhis2w_fhir_engine.engine.elm.exceptions import ELMExecutionError, ELMReferenceError

        # Error may be wrapped in ELMExecutionError
        with pytest.raises((ELMReferenceError, ELMExecutionError)):
            self.visitor.evaluate(node)

    def test_external_function_missing_library_error(self) -> None:
        """Test FunctionRef to non-existent library raises error."""
        main = self.create_main_library()
        self.visitor.set_library(main)

        node = {
            "type": "FunctionRef",
            "name": "SomeFunc",
            "libraryName": "NonExistent",
            "operand": [],
        }

        from dhis2w_fhir_engine.engine.elm.exceptions import ELMExecutionError, ELMReferenceError

        # Error may be wrapped in ELMExecutionError
        with pytest.raises((ELMReferenceError, ELMExecutionError)):
            self.visitor.evaluate(node)

    def test_multiple_included_libraries(self) -> None:
        """Test with multiple included libraries."""
        main = self.create_main_library()
        helper1 = self.create_helper_library()

        # Create second helper library
        helper2 = ELMLibrary(
            identifier=ELMIdentifier(id="Utils", version="1.0"),
            statements=ELMStatements.model_validate(
                {
                    "def": [
                        ELMDefinition(
                            name="Constant",
                            expression={"type": "Literal", "valueType": "Integer", "value": "100"},
                        ),
                    ]
                }
            ),
        )

        self.visitor.set_library(main)
        self.visitor.add_included_library("Helpers", helper1)
        self.visitor.add_included_library("Utils", helper2)

        # Reference from first library
        result1 = self.visitor.evaluate({"type": "ExpressionRef", "name": "Ten", "libraryName": "Helpers"})
        assert result1 == 10

        # Reference from second library
        result2 = self.visitor.evaluate({"type": "ExpressionRef", "name": "Constant", "libraryName": "Utils"})
        assert result2 == 100
