"""Tests for the `elm` sub-app of the engine command line interface."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dhis2w_fhir_engine.cli import app as root_app
from dhis2w_fhir_engine.cli.elm import app
from dhis2w_fhir_engine.engine.elm import ELMSerializer

runner = CliRunner()

DATA_DIRECTORY = Path(__file__).parent / "data" / "cql"
HELLO_WORLD = DATA_DIRECTORY / "hello_world.cql"


@pytest.fixture
def elm_library(tmp_path: Path) -> Path:
    file = tmp_path / "library.elm.json"
    file.write_text(ELMSerializer().serialize_library_json(HELLO_WORLD.read_text()))
    return file


class TestLoad:
    def test_summarises_a_library(self, elm_library: Path) -> None:
        result = runner.invoke(app, ["load", str(elm_library)])

        assert result.exit_code == 0
        assert "Successfully loaded" in result.output
        assert "HelloWorld" in result.output

    def test_verbose_lists_definition_names(self, elm_library: Path) -> None:
        result = runner.invoke(app, ["load", str(elm_library), "--verbose"])

        assert result.exit_code == 0
        assert "Greeting" in result.output
        assert "Sum" in result.output

    def test_reports_a_missing_file(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["load", str(tmp_path / "absent.elm.json")])

        assert result.exit_code == 1
        assert "File not found" in result.output

    def test_reports_a_document_that_is_not_elm(self, tmp_path: Path) -> None:
        file = tmp_path / "not-elm.json"
        file.write_text(json.dumps({"resourceType": "Patient"}))

        result = runner.invoke(app, ["load", str(file)])

        assert result.exit_code == 1
        assert "error" in result.output.lower()


class TestEval:
    def test_evaluates_a_definition(self, elm_library: Path) -> None:
        result = runner.invoke(app, ["eval", str(elm_library), "Sum"])

        assert result.exit_code == 0
        assert "6" in result.output

    def test_evaluates_a_string_definition(self, elm_library: Path) -> None:
        result = runner.invoke(app, ["eval", str(elm_library), "Greeting"])

        assert result.exit_code == 0
        assert "Hello, world!" in result.output

    def test_accepts_a_parameter(self, elm_library: Path) -> None:
        result = runner.invoke(app, ["eval", str(elm_library), "Sum", "--param", "Multiplier=10"])

        assert result.exit_code == 0
        assert "6" in result.output

    def test_rejects_a_malformed_parameter(self, elm_library: Path) -> None:
        result = runner.invoke(app, ["eval", str(elm_library), "Sum", "--param", "Multiplier"])

        assert result.exit_code == 1
        assert "Invalid parameter" in result.output

    def test_accepts_a_context_resource(self, elm_library: Path, tmp_path: Path) -> None:
        data = tmp_path / "patient.json"
        data.write_text(json.dumps({"resourceType": "Patient", "gender": "female"}))

        result = runner.invoke(app, ["eval", str(elm_library), "Sum", "--data", str(data)])

        assert result.exit_code == 0
        assert "6" in result.output

    def test_reports_a_missing_data_file(self, elm_library: Path, tmp_path: Path) -> None:
        result = runner.invoke(app, ["eval", str(elm_library), "Sum", "--data", str(tmp_path / "absent.json")])

        assert result.exit_code == 1
        assert "Data file not found" in result.output

    def test_reports_an_unknown_definition(self, elm_library: Path) -> None:
        result = runner.invoke(app, ["eval", str(elm_library), "Missing"])

        assert result.exit_code == 1
        assert "rror" in result.output

    def test_reports_a_missing_file(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["eval", str(tmp_path / "absent.elm.json"), "Sum"])

        assert result.exit_code == 1
        assert "File not found" in result.output


class TestRun:
    def test_evaluates_every_definition(self, elm_library: Path) -> None:
        result = runner.invoke(app, ["run", str(elm_library)])

        assert result.exit_code == 0
        assert "HelloWorld" in result.output
        assert "Results" in result.output

    def test_writes_results_to_a_file(self, elm_library: Path, tmp_path: Path) -> None:
        output = tmp_path / "results.json"

        result = runner.invoke(app, ["run", str(elm_library), "--output", str(output), "--private"])

        assert result.exit_code == 0
        assert json.loads(output.read_text())["Sum"] == 6

    def test_rejects_a_malformed_parameter(self, elm_library: Path) -> None:
        result = runner.invoke(app, ["run", str(elm_library), "--param", "Multiplier"])

        assert result.exit_code == 1
        assert "Invalid parameter" in result.output

    def test_reports_a_missing_file(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["run", str(tmp_path / "absent.elm.json")])

        assert result.exit_code == 1
        assert "File not found" in result.output


class TestShow:
    def test_displays_the_document(self, elm_library: Path) -> None:
        result = runner.invoke(app, ["show", str(elm_library)])

        assert result.exit_code == 0
        assert "HelloWorld" in result.output

    def test_reports_invalid_json(self, tmp_path: Path) -> None:
        file = tmp_path / "broken.elm.json"
        file.write_text("{not json")

        result = runner.invoke(app, ["show", str(file)])

        assert result.exit_code == 1
        assert "Invalid JSON" in result.output

    def test_reports_a_missing_file(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["show", str(tmp_path / "absent.elm.json")])

        assert result.exit_code == 1
        assert "File not found" in result.output


class TestValidate:
    def test_accepts_a_valid_library(self, elm_library: Path) -> None:
        result = runner.invoke(app, ["validate", str(elm_library)])

        assert result.exit_code == 0
        assert "1/1 passed" in result.output

    def test_rejects_a_document_that_is_not_elm(self, tmp_path: Path) -> None:
        file = tmp_path / "not-elm.json"
        file.write_text(json.dumps({"resourceType": "Patient"}))

        result = runner.invoke(app, ["validate", str(file)])

        assert result.exit_code == 1
        assert "0/1 passed" in result.output

    def test_counts_a_missing_file_as_a_failure(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["validate", str(tmp_path / "absent.elm.json")])

        assert result.exit_code == 1
        assert "File not found" in result.output


class TestConvert:
    def test_prints_elm_json(self) -> None:
        result = runner.invoke(app, ["convert", str(HELLO_WORLD), "--quiet"])

        assert result.exit_code == 0
        assert json.loads(result.output)["library"]["identifier"]["id"] == "HelloWorld"

    def test_writes_elm_json_to_a_file(self, tmp_path: Path) -> None:
        output = tmp_path / "library.elm.json"

        result = runner.invoke(app, ["convert", str(HELLO_WORLD), "--output", str(output), "--indent", "4"])

        assert result.exit_code == 0
        assert json.loads(output.read_text())["library"]["identifier"]["id"] == "HelloWorld"

    def test_renders_elm_json_with_highlighting(self) -> None:
        result = runner.invoke(app, ["convert", str(HELLO_WORLD)])

        assert result.exit_code == 0
        assert "HelloWorld" in result.output

    def test_reports_a_missing_file(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["convert", str(tmp_path / "absent.cql")])

        assert result.exit_code == 1
        assert "File not found" in result.output


class TestBundleBehindData:
    """The `--data` rule holds for ELM too: a Bundle is the data source retrieves read."""

    @pytest.fixture
    def retrieve_library(self, tmp_path: Path) -> Path:
        """An ELM library whose one definition is a retrieve count."""
        source = (
            "library Coverage version '1.0'\nusing FHIR version '4.0.1'\n\ndefine \"Child Count\": Count([Patient])\n"
        )
        file = tmp_path / "coverage.elm.json"
        file.write_text(ELMSerializer().serialize_library_json(source))
        return file

    @pytest.fixture
    def bundle(self, tmp_path: Path) -> Path:
        """Two children as a collection Bundle."""
        file = tmp_path / "clinic.json"
        file.write_text(
            json.dumps(
                {
                    "resourceType": "Bundle",
                    "type": "collection",
                    "entry": [
                        {"resource": {"resourceType": "Patient", "id": "child-1"}},
                        {"resource": {"resourceType": "Patient", "id": "child-2"}},
                    ],
                }
            )
        )
        return file

    def test_eval_reaches_the_bundle_entries(self, retrieve_library: Path, bundle: Path) -> None:
        result = runner.invoke(app, ["eval", str(retrieve_library), "Child Count", "--data", str(bundle)])

        assert result.exit_code == 0
        assert "2" in result.output

    def test_run_reaches_the_bundle_entries(self, retrieve_library: Path, bundle: Path) -> None:
        result = runner.invoke(app, ["run", str(retrieve_library), "--data", str(bundle)])

        assert result.exit_code == 0
        assert "Child Count" in result.output
        assert "2" in result.output


class TestThroughTheRootApp:
    def test_elm_convert_is_reachable_from_the_root_app(self) -> None:
        result = runner.invoke(root_app, ["elm", "convert", str(HELLO_WORLD), "--quiet"])

        assert result.exit_code == 0
        assert json.loads(result.output)["library"]["identifier"]["id"] == "HelloWorld"

    def test_root_help_lists_the_elm_sub_app(self) -> None:
        result = runner.invoke(root_app, ["--help"])

        assert result.exit_code == 0
        assert "elm" in result.output
