"""Branch coverage for the `elm` sub-app: the verbose listing, parameter parsing, and error exits."""

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dhis2w_fhir_engine.cli.elm import app

runner = CliRunner()

DATA_DIRECTORY = Path(__file__).parent / "data" / "cql"
HELLO_WORLD = DATA_DIRECTORY / "hello_world.cql"

UNSERIALIZABLE_LIBRARY = (
    "library Untyped version '1.0'\n\nusing FHIR version '4.0.1'\n\ndefine Verdict: [Observation: 'a-literal-code']\n"
)


def integer_literal(value: int) -> dict[str, Any]:
    """Build the ELM literal node for an integer."""
    return {"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": str(value)}


DECLARING_LIBRARY: dict[str, Any] = {
    "library": {
        "identifier": {"id": "Declaring", "version": "3.0"},
        "schemaIdentifier": {"id": "urn:hl7-org:elm", "version": "r1"},
        "usings": [
            {"localIdentifier": "System", "uri": "urn:hl7-org:elm-types:r1"},
            {"localIdentifier": "FHIR", "uri": "http://hl7.org/fhir", "version": "4.0.1"},
        ],
        "includes": [
            {"localIdentifier": "Helpers", "path": "FHIRHelpers", "version": "4.0.1"},
            {"localIdentifier": "Common", "path": "CommonLogic"},
        ],
        "parameters": [{"name": "MeasurementPeriod"}],
        "codeSystems": [{"name": "LOINC", "id": "http://loinc.org"}],
        "valueSets": [{"name": "FemaleGender", "id": "http://example.org/ValueSet/female"}],
        "statements": {
            "def": [
                {"name": "Answer", "expression": integer_literal(42)},
                {"name": "Doubled", "type": "FunctionDef", "operand": [], "expression": integer_literal(84)},
            ]
        },
    }
}

FAILING_LIBRARY: dict[str, Any] = {
    "library": {
        "identifier": {"id": "Partial", "version": "1.0"},
        "statements": {
            "def": [
                {"name": "Good", "expression": integer_literal(1)},
                {"name": "Bad", "expression": {"type": "ExpressionRef", "name": "DoesNotExist"}},
            ]
        },
    }
}

PARAMETERISED_LIBRARY: dict[str, Any] = {
    "library": {
        "identifier": {"id": "Parameterised", "version": "1.0"},
        "parameters": [{"name": "Label"}],
        "statements": {"def": [{"name": "Echo", "expression": {"type": "ParameterRef", "name": "Label"}}]},
    }
}


def write_library(directory: Path, name: str, document: dict[str, Any]) -> Path:
    """Write an ELM JSON document into a directory and return its path."""
    file = directory / name
    file.write_text(json.dumps(document))
    return file


@pytest.fixture
def declaring_library(tmp_path: Path) -> Path:
    """A library declaring usings, includes, parameters, value sets, and a function."""
    return write_library(tmp_path, "declaring.elm.json", DECLARING_LIBRARY)


@pytest.fixture
def failing_library(tmp_path: Path) -> Path:
    """A library whose second definition references a name that is not defined."""
    return write_library(tmp_path, "partial.elm.json", FAILING_LIBRARY)


@pytest.fixture
def parameterised_library(tmp_path: Path) -> Path:
    """A library whose only definition returns the value of a parameter."""
    return write_library(tmp_path, "parameterised.elm.json", PARAMETERISED_LIBRARY)


@pytest.fixture
def document_that_is_not_elm(tmp_path: Path) -> Path:
    """A JSON document that the ELM loader rejects."""
    return write_library(tmp_path, "not-elm.json", {"library": {"usings": "nope"}})


class TestLoadVerboseListing:
    """`elm load --verbose` prints every declared section."""

    def test_lists_the_used_models(self, declaring_library: Path) -> None:
        result = runner.invoke(app, ["load", str(declaring_library), "--verbose"])

        assert result.exit_code == 0
        assert "Using:" in result.output
        assert "FHIR v4.0.1" in result.output
        assert "System" in result.output

    def test_lists_the_included_libraries(self, declaring_library: Path) -> None:
        result = runner.invoke(app, ["load", str(declaring_library), "--verbose"])

        assert result.exit_code == 0
        assert "Includes:" in result.output
        assert "Helpers" in result.output
        assert "(FHIRHelpers) v4.0.1" in result.output
        assert "(CommonLogic)" in result.output

    def test_lists_definitions_functions_parameters_and_value_sets(self, declaring_library: Path) -> None:
        result = runner.invoke(app, ["load", str(declaring_library), "--verbose"])

        assert result.exit_code == 0
        assert "Answer" in result.output
        assert "Doubled" in result.output
        assert "MeasurementPeriod" in result.output
        assert "FemaleGender" in result.output


class TestEvalErrorExits:
    """`elm eval` failure paths."""

    def test_reports_a_library_that_cannot_be_loaded(self, document_that_is_not_elm: Path) -> None:
        result = runner.invoke(app, ["eval", str(document_that_is_not_elm), "Answer"])

        assert result.exit_code == 1
        assert "Error loading ELM" in result.output

    def test_reports_a_data_file_that_is_not_json(self, declaring_library: Path, tmp_path: Path) -> None:
        data = tmp_path / "broken.json"
        data.write_text("{not json")

        result = runner.invoke(app, ["eval", str(declaring_library), "Answer", "--data", str(data)])

        assert result.exit_code == 1
        assert "Error parsing JSON" in result.output

    def test_reports_a_definition_that_fails_while_it_runs(self, failing_library: Path) -> None:
        result = runner.invoke(app, ["eval", str(failing_library), "Bad"])

        assert result.exit_code == 1
        assert "Execution error" in result.output
        assert "DoesNotExist" in result.output


class TestParameterParsing:
    """`--param name=value` accepts both JSON and bare text."""

    def test_a_value_that_is_not_json_is_kept_as_text(self, parameterised_library: Path) -> None:
        result = runner.invoke(app, ["eval", str(parameterised_library), "Echo", "--param", "Label=urgent"])

        assert result.exit_code == 0
        assert "urgent" in result.output

    def test_a_json_value_is_decoded(self, parameterised_library: Path) -> None:
        result = runner.invoke(app, ["eval", str(parameterised_library), "Echo", "--param", "Label=7"])

        assert result.exit_code == 0
        assert "7" in result.output


class TestRunBranches:
    """`elm run` reporting, error exits, and JSON output."""

    def test_reports_a_library_that_cannot_be_loaded(self, document_that_is_not_elm: Path) -> None:
        result = runner.invoke(app, ["run", str(document_that_is_not_elm)])

        assert result.exit_code == 1
        assert "Error loading ELM" in result.output

    def test_lists_the_definitions_that_failed(self, failing_library: Path) -> None:
        result = runner.invoke(app, ["run", str(failing_library)])

        assert result.exit_code == 0
        assert "Errors:" in result.output
        assert "DoesNotExist" in result.output

    def test_writes_the_failures_beside_the_results(self, failing_library: Path, tmp_path: Path) -> None:
        output = tmp_path / "results.json"

        result = runner.invoke(app, ["run", str(failing_library), "--output", str(output)])

        assert result.exit_code == 0
        written = json.loads(output.read_text())
        assert written["Good"] == 1
        assert "DoesNotExist" in written["_errors"]["Bad"]


class TestConvertFailures:
    """`elm convert` reports a CQL source it cannot serialise."""

    def test_reports_the_failure(self, tmp_path: Path) -> None:
        file = tmp_path / "untyped.cql"
        file.write_text(UNSERIALIZABLE_LIBRARY)

        result = runner.invoke(app, ["convert", str(file)])

        assert result.exit_code == 1
        assert "Error converting to ELM" in result.output

    def test_quiet_sends_the_failure_to_standard_error(self, tmp_path: Path) -> None:
        file = tmp_path / "untyped.cql"
        file.write_text(UNSERIALIZABLE_LIBRARY)

        result = runner.invoke(app, ["convert", str(file), "--quiet"])

        assert result.exit_code == 1
        assert result.stdout.strip() == ""
        assert "Error:" in result.stderr
