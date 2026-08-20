"""Tests for FHIRPath parser."""


# Add generated directory to path

from antlr4 import CommonTokenStream, InputStream  # type: ignore[import-untyped]

from dhis2w_fhir_engine.generated.fhirpath.fhirpathLexer import fhirpathLexer
from dhis2w_fhir_engine.generated.fhirpath.fhirpathParser import fhirpathParser


def parse_fhirpath(expression: str) -> fhirpathParser.ExpressionContext:
    """Parse a FHIRPath expression and return the parse tree."""
    input_stream = InputStream(expression)
    lexer = fhirpathLexer(input_stream)
    token_stream = CommonTokenStream(lexer)
    parser = fhirpathParser(token_stream)
    expression_context: fhirpathParser.ExpressionContext = parser.expression()
    return expression_context


class TestFHIRPathParser:
    def test_simple_path(self) -> None:
        tree = parse_fhirpath("Patient.name")
        assert tree is not None

    def test_function_call(self) -> None:
        tree = parse_fhirpath("Patient.name.given.first()")
        assert tree is not None

    def test_where_clause(self) -> None:
        tree = parse_fhirpath("Patient.name.where(use = 'official')")
        assert tree is not None

    def test_boolean_expression(self) -> None:
        tree = parse_fhirpath("Patient.active = true")
        assert tree is not None

    def test_arithmetic(self) -> None:
        tree = parse_fhirpath("1 + 2 * 3")
        assert tree is not None

    def test_date_literal(self) -> None:
        tree = parse_fhirpath("@2024-01-01")
        assert tree is not None

    def test_datetime_literal(self) -> None:
        tree = parse_fhirpath("@2024-01-01T10:30:00Z")
        assert tree is not None

    def test_exists(self) -> None:
        tree = parse_fhirpath("Patient.name.exists()")
        assert tree is not None

    def test_union(self) -> None:
        tree = parse_fhirpath("Patient.name | Patient.address")
        assert tree is not None

    def test_membership(self) -> None:
        tree = parse_fhirpath("'A' in Patient.name.given")
        assert tree is not None
