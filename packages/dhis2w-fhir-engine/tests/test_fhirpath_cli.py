"""Tests for the `fhirpath` sub-app of the engine command line interface."""

import json
from pathlib import Path

from typer.testing import CliRunner

from dhis2w_fhir_engine.cli import app as root_app
from dhis2w_fhir_engine.cli.fhirpath import app

runner = CliRunner()

PATIENT = {
    "resourceType": "Patient",
    "id": "example",
    "active": True,
    "gender": "female",
    "name": [{"given": ["Ada", "Grace"], "family": "Lovelace"}],
}


def write_patient(directory: Path) -> Path:
    file = directory / "patient.json"
    file.write_text(json.dumps(PATIENT))
    return file


class TestParse:
    def test_parses_a_valid_expression(self) -> None:
        result = runner.invoke(app, ["parse", "Patient.name.given"])

        assert result.exit_code == 0
        assert "Valid FHIRPath expression" in result.output

    def test_quiet_prints_nothing_for_a_valid_expression(self) -> None:
        result = runner.invoke(app, ["parse", "Patient.name", "--quiet"])

        assert result.exit_code == 0
        assert result.output.strip() == ""

    def test_reports_syntax_errors(self) -> None:
        result = runner.invoke(app, ["parse", "Patient..name"])

        assert result.exit_code == 1
        assert "Parse errors" in result.output


class TestAst:
    def test_renders_the_tree(self) -> None:
        result = runner.invoke(app, ["ast", "Patient.name.given"])

        assert result.exit_code == 0
        assert "expression" in result.output

    def test_honours_the_depth_option(self) -> None:
        result = runner.invoke(app, ["ast", "Patient.name.given.first()", "--depth", "1"])

        assert result.exit_code == 0
        assert "..." in result.output

    def test_reports_syntax_errors(self) -> None:
        result = runner.invoke(app, ["ast", "Patient..name"])

        assert result.exit_code == 1
        assert "Parse errors" in result.output


class TestTokens:
    def test_lists_tokens(self) -> None:
        result = runner.invoke(app, ["tokens", "Patient.name"])

        assert result.exit_code == 0
        assert "Total:" in result.output
        assert "Patient" in result.output


class TestParseFile:
    def test_parses_every_expression(self, tmp_path: Path) -> None:
        file = tmp_path / "expressions.txt"
        file.write_text("# a comment\nPatient.name\n\nPatient.active\n")

        result = runner.invoke(app, ["parse-file", str(file)])

        assert result.exit_code == 0
        assert "2/2 passed" in result.output

    def test_quiet_hides_the_passing_lines(self, tmp_path: Path) -> None:
        file = tmp_path / "expressions.txt"
        file.write_text("Patient.name\n")

        result = runner.invoke(app, ["parse-file", str(file), "--quiet"])

        assert result.exit_code == 0
        assert "Line 1" not in result.output
        assert "1/1 passed" in result.output

    def test_reports_a_failing_expression(self, tmp_path: Path) -> None:
        file = tmp_path / "expressions.txt"
        file.write_text("Patient.name\nPatient..name\n")

        result = runner.invoke(app, ["parse-file", str(file)])

        assert result.exit_code == 1
        assert "1/2 passed" in result.output

    def test_reports_a_missing_file(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["parse-file", str(tmp_path / "absent.txt")])

        assert result.exit_code == 1
        assert "File not found" in result.output


class TestShow:
    def test_displays_the_file(self, tmp_path: Path) -> None:
        file = tmp_path / "expressions.fhirpath"
        file.write_text("Patient.name.given\n")

        result = runner.invoke(app, ["show", str(file)])

        assert result.exit_code == 0
        assert "Patient" in result.output

    def test_reports_a_missing_file(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["show", str(tmp_path / "absent.fhirpath")])

        assert result.exit_code == 1
        assert "File not found" in result.output


class TestEval:
    def test_evaluates_a_literal(self) -> None:
        result = runner.invoke(app, ["eval", "1 + 1"])

        assert result.exit_code == 0
        assert "2" in result.output

    def test_evaluates_against_an_inline_resource(self) -> None:
        result = runner.invoke(app, ["eval", "Patient.gender", "--json", json.dumps(PATIENT)])

        assert result.exit_code == 0
        assert "female" in result.output

    def test_evaluates_against_a_resource_file(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["eval", "Patient.name.family", "--resource", str(write_patient(tmp_path))])

        assert result.exit_code == 0
        assert "Lovelace" in result.output

    def test_renders_a_multi_item_result(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["eval", "Patient.name.given", "--resource", str(write_patient(tmp_path))])

        assert result.exit_code == 0
        assert "Ada" in result.output
        assert "Grace" in result.output

    def test_renders_an_empty_result(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["eval", "Patient.birthDate", "--resource", str(write_patient(tmp_path))])

        assert result.exit_code == 0
        assert "Empty result" in result.output

    def test_json_output(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app, ["eval", "Patient.name.given", "--resource", str(write_patient(tmp_path)), "--json-output"]
        )

        assert result.exit_code == 0
        assert json.loads(result.output) == ["Ada", "Grace"]

    def test_reports_a_missing_resource_file(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["eval", "Patient.name", "--resource", str(tmp_path / "absent.json")])

        assert result.exit_code == 1
        assert "Resource file not found" in result.output

    def test_reports_invalid_inline_json(self) -> None:
        result = runner.invoke(app, ["eval", "Patient.name", "--json", "{not json"])

        assert result.exit_code == 1
        assert "Invalid JSON" in result.output


class TestEvalFile:
    def test_evaluates_every_expression(self, tmp_path: Path) -> None:
        expressions = tmp_path / "expressions.txt"
        expressions.write_text("// comment\nPatient.gender\nPatient.name.family\n")

        result = runner.invoke(app, ["eval-file", str(expressions), "--resource", str(write_patient(tmp_path))])

        assert result.exit_code == 0
        assert "2/2 passed" in result.output

    def test_quiet_hides_the_passing_lines(self, tmp_path: Path) -> None:
        expressions = tmp_path / "expressions.txt"
        expressions.write_text("Patient.gender\n")

        result = runner.invoke(
            app, ["eval-file", str(expressions), "--resource", str(write_patient(tmp_path)), "--quiet"]
        )

        assert result.exit_code == 0
        assert "1/1 passed" in result.output
        assert "=>" not in result.output

    def test_reports_a_missing_file(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["eval-file", str(tmp_path / "absent.txt")])

        assert result.exit_code == 1
        assert "File not found" in result.output


class TestRepl:
    def test_parses_an_expression_then_quits(self) -> None:
        result = runner.invoke(app, ["repl"], input="Patient.name\nquit\n")

        assert result.exit_code == 0
        assert "Valid" in result.output
        assert "Goodbye!" in result.output

    def test_reports_syntax_errors(self) -> None:
        result = runner.invoke(app, ["repl"], input="Patient..name\nexit\n")

        assert result.exit_code == 0
        assert "Goodbye!" in result.output

    def test_ast_sub_command(self) -> None:
        result = runner.invoke(app, ["repl"], input="ast Patient.name\nquit\n")

        assert result.exit_code == 0
        assert "expression" in result.output

    def test_tokens_sub_command(self) -> None:
        result = runner.invoke(app, ["repl"], input="tokens Patient.name\nquit\n")

        assert result.exit_code == 0
        assert "Patient" in result.output

    def test_help_lists_the_session_commands(self) -> None:
        result = runner.invoke(app, ["repl"], input="help\nquit\n")

        assert result.exit_code == 0
        assert "tokens" in result.output


class TestThroughTheRootApp:
    def test_fhirpath_eval_is_reachable_from_the_root_app(self) -> None:
        result = runner.invoke(root_app, ["fhirpath", "eval", "1 + 1"])

        assert result.exit_code == 0
        assert "2" in result.output

    def test_root_help_lists_the_fhirpath_sub_app(self) -> None:
        result = runner.invoke(root_app, ["--help"])

        assert result.exit_code == 0
        assert "fhirpath" in result.output
