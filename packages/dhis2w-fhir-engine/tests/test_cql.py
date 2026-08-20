"""Tests for CQL parser."""


# Add generated directory to path

from antlr4 import CommonTokenStream, InputStream  # type: ignore[import-untyped]

from dhis2w_fhir_engine.generated.cql.cqlLexer import cqlLexer
from dhis2w_fhir_engine.generated.cql.cqlParser import cqlParser


def parse_cql(cql_text: str) -> cqlParser.LibraryContext:
    """Parse CQL text and return the parse tree."""
    input_stream = InputStream(cql_text)
    lexer = cqlLexer(input_stream)
    token_stream = CommonTokenStream(lexer)
    parser = cqlParser(token_stream)
    library_context: cqlParser.LibraryContext = parser.library()
    return library_context


class TestCQLParser:
    def test_simple_library(self) -> None:
        cql = """
        library Test version '1.0.0'
        """
        tree = parse_cql(cql)
        assert tree is not None

    def test_library_with_using(self) -> None:
        cql = """
        library Test version '1.0.0'
        using FHIR version '4.0.1'
        """
        tree = parse_cql(cql)
        assert tree is not None

    def test_define_expression(self) -> None:
        cql = """
        library Test version '1.0.0'
        using FHIR version '4.0.1'

        define TestExpression: 1 + 2
        """
        tree = parse_cql(cql)
        assert tree is not None

    def test_retrieve(self) -> None:
        cql = """
        library Test version '1.0.0'
        using FHIR version '4.0.1'

        define Patients: [Patient]
        """
        tree = parse_cql(cql)
        assert tree is not None

    def test_query_with_where(self) -> None:
        cql = """
        library Test version '1.0.0'
        using FHIR version '4.0.1'

        define ActivePatients:
            [Patient] P
            where P.active = true
        """
        tree = parse_cql(cql)
        assert tree is not None

    def test_valueset_definition(self) -> None:
        cql = """
        library Test version '1.0.0'

        valueset "Diabetes": 'http://example.org/fhir/ValueSet/diabetes'
        """
        tree = parse_cql(cql)
        assert tree is not None

    def test_codesystem_definition(self) -> None:
        cql = """
        library Test version '1.0.0'

        codesystem "LOINC": 'http://loinc.org'
        """
        tree = parse_cql(cql)
        assert tree is not None

    def test_function_definition(self) -> None:
        cql = """
        library Test version '1.0.0'

        define function Add(a Integer, b Integer) returns Integer:
            a + b
        """
        tree = parse_cql(cql)
        assert tree is not None

    def test_interval_expression(self) -> None:
        cql = """
        library Test version '1.0.0'

        define TestInterval: Interval[1, 10]
        """
        tree = parse_cql(cql)
        assert tree is not None

    def test_datetime_expression(self) -> None:
        cql = """
        library Test version '1.0.0'

        define TestDate: @2024-01-01T10:30:00
        """
        tree = parse_cql(cql)
        assert tree is not None
