"""An expression is the whole of the text it was given, in FHIRPath as in CQL.

Both front ends anchor their `expression` rule at the end of the token stream and hand every lexer
and parser recognition error to a throwing listener, so a mistyped formula raises instead of
evaluating a prefix of itself while a diagnostic goes to stderr.
"""

import pytest

from dhis2w_fhir_engine.engine.cql import CQLEvaluator
from dhis2w_fhir_engine.engine.exceptions import CQLError, FHIRPathError
from dhis2w_fhir_engine.engine.fhirpath import FHIRPathEvaluator


@pytest.fixture
def fhirpath_evaluator() -> FHIRPathEvaluator:
    """Create a FHIRPath evaluator."""
    return FHIRPathEvaluator()


@pytest.fixture
def cql_evaluator() -> CQLEvaluator:
    """Create a CQL evaluator."""
    return CQLEvaluator()


class TestFHIRPathTrailingText:
    """FHIRPath refuses text the parser stopped short of."""

    @pytest.mark.parametrize("expression", ["1 2", "true false", "1 + 2 garbage", "'a' 'b'"])
    def test_trailing_tokens_are_refused(self, fhirpath_evaluator: FHIRPathEvaluator, expression: str) -> None:
        with pytest.raises(FHIRPathError, match="Syntax error"):
            fhirpath_evaluator.evaluate(expression)

    def test_the_refusal_names_the_position_and_the_offending_text(self, fhirpath_evaluator: FHIRPathEvaluator) -> None:
        with pytest.raises(FHIRPathError) as raised:
            fhirpath_evaluator.evaluate("1 2")
        assert str(raised.value) == "Syntax error at line 1:2: extraneous input '2' expecting end of expression"

    def test_a_whole_expression_still_evaluates(self, fhirpath_evaluator: FHIRPathEvaluator) -> None:
        assert fhirpath_evaluator.evaluate("1 + 2") == [3]

    def test_surrounding_whitespace_is_not_trailing_text(self, fhirpath_evaluator: FHIRPathEvaluator) -> None:
        assert fhirpath_evaluator.evaluate("  1 + 2\n") == [3]

    def test_a_navigation_expression_still_evaluates(self, fhirpath_evaluator: FHIRPathEvaluator) -> None:
        patient = {"resourceType": "Patient", "name": [{"given": ["Ada", "Marie"]}]}
        assert fhirpath_evaluator.evaluate("Patient.name.given", patient) == ["Ada", "Marie"]


class TestUnrecognisedCharacters:
    """A character no lexer rule matches raises rather than being skipped with a stderr diagnostic."""

    @pytest.mark.parametrize("expression", ["$ 1 + 2", "1 $ + 2", "1 + 2 $"])
    def test_fhirpath_refuses_an_unrecognised_character(
        self, fhirpath_evaluator: FHIRPathEvaluator, expression: str
    ) -> None:
        with pytest.raises(FHIRPathError):
            fhirpath_evaluator.evaluate(expression)

    @pytest.mark.parametrize("expression", ["$ 1 + 2", "1 $ + 2", "1 + 2 $"])
    def test_cql_refuses_an_unrecognised_character(self, cql_evaluator: CQLEvaluator, expression: str) -> None:
        with pytest.raises(CQLError):
            cql_evaluator.evaluate_expression(expression)

    def test_cql_refuses_a_library_carrying_an_unrecognised_character(self, cql_evaluator: CQLEvaluator) -> None:
        source = "library Broken version '1.0'\n\ndefine Total: 1 + 2 $\n"
        with pytest.raises(CQLError):
            cql_evaluator.compile(source)

    def test_cql_compiles_the_same_library_without_the_stray_character(self, cql_evaluator: CQLEvaluator) -> None:
        source = "library Whole version '1.0'\n\ndefine Total: 1 + 2\n"
        cql_evaluator.compile(source)
        assert cql_evaluator.evaluate_expression("Total") == 3


class TestNothingIsWrittenToStandardError:
    """A successful evaluation writes nothing to stderr, and neither does a refused one."""

    def test_fhirpath_success_is_silent(
        self, fhirpath_evaluator: FHIRPathEvaluator, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert fhirpath_evaluator.evaluate("1 + 2") == [3]
        assert capsys.readouterr().err == ""

    def test_cql_success_is_silent(self, cql_evaluator: CQLEvaluator, capsys: pytest.CaptureFixture[str]) -> None:
        assert cql_evaluator.evaluate_expression("1 + 2") == 3
        assert capsys.readouterr().err == ""

    def test_fhirpath_refusal_is_silent(
        self, fhirpath_evaluator: FHIRPathEvaluator, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(FHIRPathError):
            fhirpath_evaluator.evaluate("1 + 2 $")
        assert capsys.readouterr().err == ""

    def test_cql_refusal_is_silent(self, cql_evaluator: CQLEvaluator, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(CQLError):
            cql_evaluator.evaluate_expression("1 + 2 $")
        assert capsys.readouterr().err == ""
