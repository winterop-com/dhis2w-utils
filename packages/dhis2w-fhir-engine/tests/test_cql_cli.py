"""Tests for the `cql` sub-app of the engine command line interface."""

import json
from pathlib import Path

from typer.testing import CliRunner

from dhis2w_fhir_engine.cli import app as root_app
from dhis2w_fhir_engine.cli.cql import app

runner = CliRunner()

DATA_DIRECTORY = Path(__file__).parent / "data" / "cql"
HELLO_WORLD = DATA_DIRECTORY / "hello_world.cql"
SIMPLE_MEASURE = DATA_DIRECTORY / "simple_measure.cql"

VALID_LIBRARY = "library Test version '1.0'\n\ndefine Sum: 1 + 2 + 3\n"
INVALID_LIBRARY = "this is not valid cql @@@@"


def write_library(directory: Path, name: str, source: str) -> Path:
    file = directory / name
    file.write_text(source)
    return file


class TestParse:
    def test_parses_a_valid_library(self, tmp_path: Path) -> None:
        file = write_library(tmp_path, "test.cql", VALID_LIBRARY)

        result = runner.invoke(app, ["parse", str(file)])

        assert result.exit_code == 0
        assert "Successfully parsed" in result.output

    def test_quiet_prints_nothing_for_a_valid_library(self, tmp_path: Path) -> None:
        file = write_library(tmp_path, "test.cql", VALID_LIBRARY)

        result = runner.invoke(app, ["parse", str(file), "--quiet"])

        assert result.exit_code == 0
        assert result.output.strip() == ""

    def test_reports_syntax_errors(self, tmp_path: Path) -> None:
        file = write_library(tmp_path, "invalid.cql", INVALID_LIBRARY)

        result = runner.invoke(app, ["parse", str(file)])

        assert result.exit_code == 1
        assert "Parse errors" in result.output

    def test_reports_a_missing_file(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["parse", str(tmp_path / "absent.cql")])

        assert result.exit_code == 1
        assert "File not found" in result.output


class TestAst:
    def test_renders_the_tree(self) -> None:
        result = runner.invoke(app, ["ast", str(HELLO_WORLD)])

        assert result.exit_code == 0
        assert "library" in result.output

    def test_honours_the_depth_option(self) -> None:
        result = runner.invoke(app, ["ast", str(HELLO_WORLD), "--depth", "1"])

        assert result.exit_code == 0
        assert "..." in result.output

    def test_reports_syntax_errors(self, tmp_path: Path) -> None:
        file = write_library(tmp_path, "invalid.cql", INVALID_LIBRARY)

        result = runner.invoke(app, ["ast", str(file)])

        assert result.exit_code == 1
        assert "Parse errors" in result.output


class TestTokens:
    def test_lists_tokens(self) -> None:
        result = runner.invoke(app, ["tokens", str(HELLO_WORLD)])

        assert result.exit_code == 0
        assert "Total:" in result.output

    def test_limit_truncates_the_stream(self) -> None:
        result = runner.invoke(app, ["tokens", str(HELLO_WORLD), "--limit", "3"])

        assert result.exit_code == 0
        assert "limited to 3 tokens" in result.output

    def test_reports_a_missing_file(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["tokens", str(tmp_path / "absent.cql")])

        assert result.exit_code == 1
        assert "File not found" in result.output


class TestShow:
    def test_displays_the_source(self) -> None:
        result = runner.invoke(app, ["show", str(HELLO_WORLD)])

        assert result.exit_code == 0
        assert "HelloWorld" in result.output

    def test_reports_a_missing_file(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["show", str(tmp_path / "absent.cql")])

        assert result.exit_code == 1
        assert "File not found" in result.output


class TestValidate:
    def test_accepts_valid_files(self, tmp_path: Path) -> None:
        first = write_library(tmp_path, "a.cql", VALID_LIBRARY)
        second = write_library(tmp_path, "b.cql", VALID_LIBRARY)

        result = runner.invoke(app, ["validate", str(first), str(second)])

        assert result.exit_code == 0
        assert "2/2 passed" in result.output

    def test_rejects_an_invalid_file(self, tmp_path: Path) -> None:
        good = write_library(tmp_path, "a.cql", VALID_LIBRARY)
        bad = write_library(tmp_path, "b.cql", INVALID_LIBRARY)

        result = runner.invoke(app, ["validate", str(good), str(bad)])

        assert result.exit_code == 1
        assert "1/2 passed" in result.output

    def test_counts_a_missing_file_as_a_failure(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["validate", str(tmp_path / "absent.cql")])

        assert result.exit_code == 1
        assert "File not found" in result.output


class TestDefinitions:
    def test_lists_the_declared_entries(self) -> None:
        result = runner.invoke(app, ["definitions", str(HELLO_WORLD)])

        assert result.exit_code == 0
        assert "Library:" in result.output
        assert "Define:" in result.output

    def test_reports_syntax_errors(self, tmp_path: Path) -> None:
        file = write_library(tmp_path, "invalid.cql", INVALID_LIBRARY)

        result = runner.invoke(app, ["definitions", str(file)])

        assert result.exit_code == 1
        assert "Parse errors" in result.output


class TestEval:
    def test_evaluates_an_arithmetic_expression(self) -> None:
        result = runner.invoke(app, ["eval", "1 + 2 * 3"])

        assert result.exit_code == 0
        assert "7" in result.output

    def test_evaluates_a_string_function(self) -> None:
        result = runner.invoke(app, ["eval", "Upper('hello')"])

        assert result.exit_code == 0
        assert "HELLO" in result.output

    def test_evaluates_a_definition_from_a_library(self) -> None:
        result = runner.invoke(app, ["eval", "Sum", "--library", str(HELLO_WORLD)])

        assert result.exit_code == 0
        assert "6" in result.output

    def test_evaluates_against_a_data_file(self, tmp_path: Path) -> None:
        data = tmp_path / "patient.json"
        data.write_text(json.dumps({"resourceType": "Patient", "gender": "female"}))

        result = runner.invoke(app, ["eval", "Numerator", "--library", str(SIMPLE_MEASURE), "--data", str(data)])

        assert result.exit_code == 0
        assert "True" in result.output

    def test_reports_a_missing_library(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["eval", "Sum", "--library", str(tmp_path / "absent.cql")])

        assert result.exit_code == 1
        assert "File not found" in result.output

    def test_reports_invalid_data_json(self, tmp_path: Path) -> None:
        data = tmp_path / "broken.json"
        data.write_text("{not json")

        result = runner.invoke(app, ["eval", "1 + 1", "--data", str(data)])

        assert result.exit_code == 1
        assert "Error parsing JSON" in result.output


class TestRun:
    def test_evaluates_every_definition(self) -> None:
        result = runner.invoke(app, ["run", str(HELLO_WORLD)])

        assert result.exit_code == 0
        assert "HelloWorld" in result.output
        assert "Results" in result.output

    def test_evaluates_a_single_definition(self) -> None:
        result = runner.invoke(app, ["run", str(HELLO_WORLD), "--definition", "Sum"])

        assert result.exit_code == 0
        assert "6" in result.output

    def test_rejects_an_unknown_definition(self) -> None:
        result = runner.invoke(app, ["run", str(HELLO_WORLD), "--definition", "Missing"])

        assert result.exit_code == 1
        assert "Definition not found" in result.output

    def test_writes_results_to_a_file(self, tmp_path: Path) -> None:
        output = tmp_path / "results.json"

        result = runner.invoke(app, ["run", str(HELLO_WORLD), "--output", str(output)])

        assert result.exit_code == 0
        written = json.loads(output.read_text())
        assert written["Sum"] == 6


class TestCheck:
    def test_summarises_a_library(self) -> None:
        result = runner.invoke(app, ["check", str(HELLO_WORLD)])

        assert result.exit_code == 0
        assert "Syntax valid" in result.output
        assert "All checks passed" in result.output

    def test_verbose_lists_definition_names(self) -> None:
        result = runner.invoke(app, ["check", str(HELLO_WORLD), "--verbose"])

        assert result.exit_code == 0
        assert "Greeting" in result.output

    def test_reports_syntax_errors(self, tmp_path: Path) -> None:
        file = write_library(tmp_path, "invalid.cql", INVALID_LIBRARY)

        result = runner.invoke(app, ["check", str(file)])

        assert result.exit_code == 1
        assert "Syntax errors" in result.output


class TestMeasure:
    def test_evaluates_a_measure_for_one_patient(self, tmp_path: Path) -> None:
        data = tmp_path / "patient.json"
        data.write_text(json.dumps({"resourceType": "Patient", "id": "p1", "gender": "female"}))

        result = runner.invoke(app, ["measure", str(SIMPLE_MEASURE), "--data", str(data)])

        assert result.exit_code == 0
        assert "initial-population" in result.output
        assert "numerator" in result.output

    def test_evaluates_a_measure_from_a_bundle(self, tmp_path: Path) -> None:
        bundle = tmp_path / "bundle.json"
        bundle.write_text(
            json.dumps(
                {
                    "resourceType": "Bundle",
                    "entry": [
                        {"resource": {"resourceType": "Patient", "id": "p1", "gender": "female"}},
                        {"resource": {"resourceType": "Patient", "id": "p2", "gender": "male"}},
                    ],
                }
            )
        )

        result = runner.invoke(app, ["measure", str(SIMPLE_MEASURE), "--data", str(bundle)])

        assert result.exit_code == 0
        assert "Evaluating 2 patient(s)" in result.output

    def test_reads_a_patient_directory(self, tmp_path: Path) -> None:
        patients = tmp_path / "patients"
        patients.mkdir()
        (patients / "p1.json").write_text(json.dumps({"resourceType": "Patient", "id": "p1", "gender": "female"}))

        result = runner.invoke(app, ["measure", str(SIMPLE_MEASURE), "--patients", str(patients)])

        assert result.exit_code == 0
        assert "Evaluating 1 patient(s)" in result.output

    def test_rejects_data_that_is_not_a_patient_or_bundle(self, tmp_path: Path) -> None:
        data = tmp_path / "observation.json"
        data.write_text(json.dumps({"resourceType": "Observation"}))

        result = runner.invoke(app, ["measure", str(SIMPLE_MEASURE), "--data", str(data)])

        assert result.exit_code == 1
        assert "must be a Patient or a Bundle" in result.output

    def test_writes_a_measure_report(self, tmp_path: Path) -> None:
        data = tmp_path / "patient.json"
        data.write_text(json.dumps({"resourceType": "Patient", "id": "p1", "gender": "female"}))
        output = tmp_path / "report.json"

        result = runner.invoke(
            app, ["measure", str(SIMPLE_MEASURE), "--data", str(data), "--output", str(output), "--verbose"]
        )

        assert result.exit_code == 0
        assert json.loads(output.read_text())["resourceType"] == "MeasureReport"


class TestExport:
    def test_prints_elm_json(self) -> None:
        result = runner.invoke(app, ["export", str(HELLO_WORLD), "--quiet"])

        assert result.exit_code == 0
        assert json.loads(result.output)["library"]["identifier"]["id"] == "HelloWorld"

    def test_writes_elm_json_to_a_file(self, tmp_path: Path) -> None:
        output = tmp_path / "library.elm.json"

        result = runner.invoke(app, ["export", str(HELLO_WORLD), "--output", str(output)])

        assert result.exit_code == 0
        assert json.loads(output.read_text())["library"]["identifier"]["id"] == "HelloWorld"

    def test_reports_a_missing_file(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["export", str(tmp_path / "absent.cql")])

        assert result.exit_code == 1
        assert "File not found" in result.output


class TestRepl:
    def test_evaluates_an_expression_then_quits(self) -> None:
        result = runner.invoke(app, ["repl"], input="1 + 2\nquit\n")

        assert result.exit_code == 0
        assert "3" in result.output
        assert "Goodbye!" in result.output

    def test_lists_definitions_of_a_loaded_library(self) -> None:
        result = runner.invoke(app, ["repl", "--library", str(HELLO_WORLD)], input="defs\nquit\n")

        assert result.exit_code == 0
        assert "Sum" in result.output

    def test_help_lists_the_session_commands(self) -> None:
        result = runner.invoke(app, ["repl"], input="help\nquit\n")

        assert result.exit_code == 0
        assert "load <file>" in result.output


class TestThroughTheRootApp:
    def test_cql_eval_is_reachable_from_the_root_app(self) -> None:
        result = runner.invoke(root_app, ["cql", "eval", "1 + 1"])

        assert result.exit_code == 0
        assert "2" in result.output

    def test_root_help_lists_the_cql_sub_app(self) -> None:
        result = runner.invoke(root_app, ["--help"])

        assert result.exit_code == 0
        assert "cql" in result.output
