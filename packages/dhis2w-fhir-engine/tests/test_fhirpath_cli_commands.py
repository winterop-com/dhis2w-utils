"""Branch coverage for the `fhirpath` sub-app: evaluation failures, output trimming, and the session."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dhis2w_fhir_engine.cli.fhirpath import app

runner = CliRunner()

UNKNOWN_FUNCTION_EXPRESSION = "Patient.name.bogusFunction()"

PATIENT_WITH_MANY_NAMES = {
    "resourceType": "Patient",
    "id": "example",
    "gender": "female",
    "name": [{"given": ["Augusta", "Ada", "Gwendolyn", "Millicent", "Rosalind"], "family": "Lovelace"}],
}


@pytest.fixture
def patient_file(tmp_path: Path) -> Path:
    """A Patient resource whose given names are long enough to be trimmed on one line."""
    file = tmp_path / "patient.json"
    file.write_text(json.dumps(PATIENT_WITH_MANY_NAMES))
    return file


class TestEvalFailures:
    """`fhirpath eval` reports an expression the evaluator refuses."""

    def test_reports_an_unknown_function(self, patient_file: Path) -> None:
        result = runner.invoke(app, ["eval", UNKNOWN_FUNCTION_EXPRESSION, "--resource", str(patient_file)])

        assert result.exit_code == 1
        assert "FHIRPath error" in result.output
        assert "Unknown function" in result.output


class TestEvalFileBranches:
    """`fhirpath eval-file` per-line reporting."""

    def test_reports_a_line_the_evaluator_refuses(self, tmp_path: Path, patient_file: Path) -> None:
        expressions = tmp_path / "expressions.txt"
        expressions.write_text(f"Patient.gender\n{UNKNOWN_FUNCTION_EXPRESSION}\n")

        result = runner.invoke(app, ["eval-file", str(expressions), "--resource", str(patient_file)])

        assert result.exit_code == 1
        assert "FAIL" in result.output
        assert "Unknown function" in result.output
        assert "1/2 passed" in result.output

    def test_trims_a_long_result_to_one_line(self, tmp_path: Path, patient_file: Path) -> None:
        expressions = tmp_path / "expressions.txt"
        expressions.write_text("Patient.name.given\n")

        result = runner.invoke(app, ["eval-file", str(expressions), "--resource", str(patient_file)])

        assert result.exit_code == 0
        assert "'Augusta'" in result.output
        assert "..." in result.output
        assert "Rosalind" not in result.output


class TestReplSession:
    """The commands the interactive session accepts."""

    def test_end_of_input_closes_the_session(self) -> None:
        result = runner.invoke(app, ["repl"], input="Patient.gender\n")

        assert result.exit_code == 0
        assert "Valid" in result.output
        assert "Goodbye!" in result.output

    def test_blank_lines_are_ignored(self) -> None:
        result = runner.invoke(app, ["repl"], input="\n   \nPatient.active\nquit\n")

        assert result.exit_code == 0
        assert "Valid" in result.output

    def test_ast_reports_syntax_errors(self) -> None:
        result = runner.invoke(app, ["repl"], input="ast Patient..name\nquit\n")

        assert result.exit_code == 0
        assert "extraneous input" in result.output
        assert "└──" not in result.output
