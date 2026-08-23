"""Branch coverage for the `cql` sub-app: result rendering, error exits, and the interactive session."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dhis2w_fhir_engine.cli.cql import app

runner = CliRunner()

DATA_DIRECTORY = Path(__file__).parent / "data" / "cql"
HELLO_WORLD = DATA_DIRECTORY / "hello_world.cql"
SIMPLE_MEASURE = DATA_DIRECTORY / "simple_measure.cql"

INVALID_LIBRARY = "this is not valid cql @@@@"

UNCOMPILABLE_LIBRARY = "library Broken version '1.0'\n\nparameter Threshold Integer default 99999999999999\n"

FAILING_DEFINITION_LIBRARY = (
    "library Partial version '1.0'\n\ndefine Good: 1 + 1\n\ndefine Bad: singleton from {1, 2}\n"
)

QUANTITY_LIBRARY = "library Dosage version '1.0'\n\ndefine Weight: 5 'mg'\n"

RICH_LIBRARY = (
    "library Rich version '2.0'\n\n"
    "using FHIR version '4.0.1'\n\n"
    "codesystem \"LOINC\": 'http://loinc.org'\n\n"
    "valueset \"FemaleGender\": 'http://example.org/ValueSet/female'\n\n"
    "parameter Threshold Integer default 5\n\n"
    "define function Double(value Integer) returns Integer: value * 2\n\n"
    "define Answer: Double(21)\n"
)

CONTEXT_ONLY_LIBRARY = "library Bare version '1.0'\n\ncontext Patient\n"

UNSERIALIZABLE_LIBRARY = (
    "library Untyped version '1.0'\n\nusing FHIR version '4.0.1'\n\ndefine Verdict: [Observation: 'a-literal-code']\n"
)

STRATIFIED_MEASURE = (
    "library Stratified version '1.0'\n\n"
    "using FHIR version '4.0.1'\n\n"
    "context Patient\n\n"
    'define "Initial Population": true\n\n'
    'define "Denominator": true\n\n'
    "define \"Numerator\": Patient.gender = 'female'\n\n"
    'define "Stratifier Gender": Patient.gender\n'
)

FEMALE_PATIENT = {"resourceType": "Patient", "id": "p1", "gender": "female"}


def write_source(directory: Path, name: str, source: str) -> Path:
    """Write a CQL source file into a directory and return its path."""
    file = directory / name
    file.write_text(source)
    return file


def write_json(directory: Path, name: str, document: object) -> Path:
    """Write a JSON document into a directory and return its path."""
    file = directory / name
    file.write_text(json.dumps(document))
    return file


@pytest.fixture
def uncompilable_library(tmp_path: Path) -> Path:
    """A library that parses cleanly but fails to compile."""
    return write_source(tmp_path, "uncompilable.cql", UNCOMPILABLE_LIBRARY)


@pytest.fixture
def failing_definition_library(tmp_path: Path) -> Path:
    """A library whose second definition raises while it is evaluated."""
    return write_source(tmp_path, "partial.cql", FAILING_DEFINITION_LIBRARY)


@pytest.fixture
def rich_library(tmp_path: Path) -> Path:
    """A library declaring a function, a value set, a code system, and a parameter."""
    return write_source(tmp_path, "rich.cql", RICH_LIBRARY)


class TestResultRendering:
    """The shapes `format_result` has to render, reached through `cql eval`."""

    def test_renders_a_null_result(self) -> None:
        result = runner.invoke(app, ["eval", "null"])

        assert result.exit_code == 0
        assert "null" in result.output

    def test_renders_an_empty_list(self) -> None:
        result = runner.invoke(app, ["eval", "{}"])

        assert result.exit_code == 0
        assert "{}" in result.output

    def test_renders_a_populated_list(self) -> None:
        result = runner.invoke(app, ["eval", "{1, 2, 3}"])

        assert result.exit_code == 0
        assert "{ 1, 2, 3 }" in result.output

    def test_renders_a_resource_as_a_mapping(self, tmp_path: Path) -> None:
        data = write_json(tmp_path, "patient.json", {"resourceType": "Patient", "gender": "female"})

        result = runner.invoke(app, ["eval", "Patient", "--library", str(SIMPLE_MEASURE), "--data", str(data)])

        assert result.exit_code == 0
        assert "resourceType" in result.output
        assert "Patient" in result.output

    def test_renders_a_list_of_mappings(self, tmp_path: Path) -> None:
        data = write_json(
            tmp_path,
            "patient.json",
            {"resourceType": "Patient", "gender": "female", "name": [{"family": "Lovelace"}]},
        )

        result = runner.invoke(app, ["eval", "Patient.name", "--library", str(SIMPLE_MEASURE), "--data", str(data)])

        assert result.exit_code == 0
        assert "family" in result.output
        assert "Lovelace" in result.output

    def test_renders_a_date_through_its_string_form(self) -> None:
        result = runner.invoke(app, ["eval", "@2020-01-01"])

        assert result.exit_code == 0
        assert "2020-01-01" in result.output


class TestEvalErrorExits:
    """`cql eval` failure paths."""

    def test_reports_a_missing_data_file(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["eval", "1 + 1", "--data", str(tmp_path / "absent.json")])

        assert result.exit_code == 1
        assert "Data file not found" in result.output

    def test_reports_a_library_that_does_not_compile(self, uncompilable_library: Path) -> None:
        result = runner.invoke(app, ["eval", "Threshold", "--library", str(uncompilable_library)])

        assert result.exit_code == 1
        assert "Error compiling library" in result.output
        assert "out of range" in result.output

    def test_reports_an_expression_that_fails_to_evaluate(self) -> None:
        result = runner.invoke(app, ["eval", "singleton from {1, 2}"])

        assert result.exit_code == 1
        assert "Evaluation error" in result.output
        assert "at most one element" in result.output


class TestRunBranches:
    """`cql run` reporting, error exits, and JSON output."""

    def test_reports_a_library_that_does_not_compile(self, uncompilable_library: Path) -> None:
        result = runner.invoke(app, ["run", str(uncompilable_library)])

        assert result.exit_code == 1
        assert "Error compiling library" in result.output

    def test_shows_a_failing_definition_as_an_error_row(self, failing_definition_library: Path) -> None:
        result = runner.invoke(app, ["run", str(failing_definition_library)])

        assert result.exit_code == 0
        assert "Good" in result.output
        assert "Error" in result.output

    def test_reports_a_named_definition_that_fails(self, failing_definition_library: Path) -> None:
        result = runner.invoke(app, ["run", str(failing_definition_library), "--definition", "Bad"])

        assert result.exit_code == 1
        assert "Evaluation error" in result.output

    def test_writes_a_failing_definition_as_an_error_entry(
        self, failing_definition_library: Path, tmp_path: Path
    ) -> None:
        output = tmp_path / "results.json"

        result = runner.invoke(app, ["run", str(failing_definition_library), "--output", str(output)])

        assert result.exit_code == 0
        written = json.loads(output.read_text())
        assert written["Good"] == 2
        assert "at most one element" in written["Bad"]["error"]

    def test_writes_a_model_result_as_a_mapping(self, tmp_path: Path) -> None:
        library = write_source(tmp_path, "dosage.cql", QUANTITY_LIBRARY)
        output = tmp_path / "results.json"

        result = runner.invoke(app, ["run", str(library), "--output", str(output)])

        assert result.exit_code == 0
        written = json.loads(output.read_text())
        assert written["Weight"]["unit"] == "mg"


class TestCheckBranches:
    """`cql check` compilation failures and the verbose listing."""

    def test_reports_a_library_that_does_not_compile(self, uncompilable_library: Path) -> None:
        result = runner.invoke(app, ["check", str(uncompilable_library)])

        assert result.exit_code == 1
        assert "Syntax valid" in result.output
        assert "Compilation error" in result.output

    def test_verbose_lists_functions_value_sets_and_code_systems(self, rich_library: Path) -> None:
        result = runner.invoke(app, ["check", str(rich_library), "--verbose"])

        assert result.exit_code == 0
        assert "Double(value: Integer)" in result.output
        assert "FemaleGender" in result.output
        assert "LOINC" in result.output


class TestMeasureBranches:
    """`cql measure` population sourcing and reporting."""

    def test_reports_a_missing_measure_file(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["measure", str(tmp_path / "absent.cql")])

        assert result.exit_code == 1
        assert "File not found" in result.output

    def test_reports_a_missing_patients_directory(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["measure", str(SIMPLE_MEASURE), "--patients", str(tmp_path / "absent")])

        assert result.exit_code == 1
        assert "Patients directory not found" in result.output

    def test_skips_an_unreadable_patient_file(self, tmp_path: Path) -> None:
        patients = tmp_path / "patients"
        patients.mkdir()
        (patients / "broken.json").write_text("{not json")
        write_json(patients, "p1.json", FEMALE_PATIENT)

        result = runner.invoke(app, ["measure", str(SIMPLE_MEASURE), "--patients", str(patients)])

        assert result.exit_code == 0
        assert "Skipping invalid JSON" in result.output
        assert "Evaluating 1 patient(s)" in result.output

    def test_warns_when_no_patients_were_provided(self) -> None:
        result = runner.invoke(app, ["measure", str(SIMPLE_MEASURE)])

        assert result.exit_code == 0
        assert "No patients provided" in result.output

    def test_reports_a_measure_that_does_not_compile(self, uncompilable_library: Path) -> None:
        result = runner.invoke(app, ["measure", str(uncompilable_library)])

        assert result.exit_code == 1
        assert "out of range" in result.output

    def test_verbose_shows_stratifier_results(self, tmp_path: Path) -> None:
        measure_file = write_source(tmp_path, "stratified.cql", STRATIFIED_MEASURE)
        data = write_json(tmp_path, "patient.json", FEMALE_PATIENT)

        result = runner.invoke(app, ["measure", str(measure_file), "--data", str(data), "--verbose"])

        assert result.exit_code == 0
        assert "Stratifiers:" in result.output
        assert "Stratifier Gender" in result.output


class TestExportBranches:
    """`cql export` rendering and failure paths."""

    def test_renders_elm_json_with_highlighting(self) -> None:
        result = runner.invoke(app, ["export", str(HELLO_WORLD)])

        assert result.exit_code == 0
        assert "HelloWorld" in result.output
        assert "identifier" in result.output

    def test_reports_a_source_that_cannot_be_exported(self, tmp_path: Path) -> None:
        file = write_source(tmp_path, "untyped.cql", UNSERIALIZABLE_LIBRARY)

        result = runner.invoke(app, ["export", str(file)])

        assert result.exit_code == 1
        assert "Error exporting to ELM" in result.output

    def test_quiet_sends_the_export_failure_to_standard_error(self, tmp_path: Path) -> None:
        file = write_source(tmp_path, "untyped.cql", UNSERIALIZABLE_LIBRARY)

        result = runner.invoke(app, ["export", str(file), "--quiet"])

        assert result.exit_code == 1
        assert result.stdout.strip() == ""
        assert "Error:" in result.stderr


class TestReplStartup:
    """What the interactive session reports while it starts."""

    def test_warns_about_a_library_that_does_not_compile(self, uncompilable_library: Path) -> None:
        result = runner.invoke(app, ["repl", "--library", str(uncompilable_library)], input="quit\n")

        assert result.exit_code == 0
        assert "Could not load library" in result.output

    def test_reports_the_resource_type_of_the_loaded_data(self, tmp_path: Path) -> None:
        data = write_json(tmp_path, "patient.json", FEMALE_PATIENT)

        result = runner.invoke(app, ["repl", "--data", str(data)], input="quit\n")

        assert result.exit_code == 0
        assert "Loaded data" in result.output
        assert "Resource type: Patient" in result.output

    def test_warns_about_data_that_is_not_json(self, tmp_path: Path) -> None:
        data = tmp_path / "broken.json"
        data.write_text("{not json")

        result = runner.invoke(app, ["repl", "--data", str(data)], input="quit\n")

        assert result.exit_code == 0
        assert "Could not load data" in result.output


class TestReplSession:
    """The commands the interactive session accepts."""

    def test_end_of_input_closes_the_session(self) -> None:
        result = runner.invoke(app, ["repl"], input="1 + 1\n")

        assert result.exit_code == 0
        assert "2" in result.output
        assert "Goodbye!" in result.output

    def test_blank_lines_are_ignored(self) -> None:
        result = runner.invoke(app, ["repl"], input="\n   \n7 * 6\nquit\n")

        assert result.exit_code == 0
        assert "42" in result.output

    def test_load_reports_a_missing_file(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["repl"], input=f"load {tmp_path / 'absent.cql'}\nquit\n")

        assert result.exit_code == 0
        assert "File not found" in result.output

    def test_load_reads_a_library(self) -> None:
        result = runner.invoke(app, ["repl"], input=f"load {HELLO_WORLD}\ndefs\nquit\n")

        assert result.exit_code == 0
        assert "Loaded: HelloWorld" in result.output
        assert "IsAdult" in result.output

    def test_load_reports_a_library_that_does_not_compile(self, uncompilable_library: Path) -> None:
        result = runner.invoke(app, ["repl"], input=f"load {uncompilable_library}\nquit\n")

        assert result.exit_code == 0
        assert "out of range" in result.output

    def test_data_reports_a_missing_file(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["repl"], input=f"data {tmp_path / 'absent.json'}\nquit\n")

        assert result.exit_code == 0
        assert "File not found" in result.output

    def test_data_reads_a_resource_and_evaluates_against_it(self, tmp_path: Path) -> None:
        data = write_json(tmp_path, "patient.json", FEMALE_PATIENT)

        result = runner.invoke(
            app,
            ["repl", "--library", str(SIMPLE_MEASURE)],
            input=f"data {data}\neval Numerator\nquit\n",
        )

        assert result.exit_code == 0
        assert "Resource type: Patient" in result.output
        assert "True" in result.output

    def test_data_reports_a_file_that_is_not_json(self, tmp_path: Path) -> None:
        broken = tmp_path / "broken.json"
        broken.write_text("{not json")

        result = runner.invoke(app, ["repl"], input=f"data {broken}\nquit\n")

        assert result.exit_code == 0
        assert "Error:" in result.output

    def test_defs_reports_that_no_library_is_loaded(self) -> None:
        result = runner.invoke(app, ["repl"], input="defs\nquit\n")

        assert result.exit_code == 0
        assert "No library loaded" in result.output

    def test_defs_lists_functions(self, rich_library: Path) -> None:
        result = runner.invoke(app, ["repl", "--library", str(rich_library)], input="defs\nquit\n")

        assert result.exit_code == 0
        assert "Functions:" in result.output
        assert "Double" in result.output

    def test_defs_reports_a_library_declaring_nothing(self, tmp_path: Path) -> None:
        library = write_source(tmp_path, "bare.cql", CONTEXT_ONLY_LIBRARY)

        result = runner.invoke(app, ["repl", "--library", str(library)], input="defs\nquit\n")

        assert result.exit_code == 0
        assert "No definitions" in result.output

    def test_clear_drops_the_loaded_library(self) -> None:
        result = runner.invoke(app, ["repl", "--library", str(HELLO_WORLD)], input="clear\ndefs\nquit\n")

        assert result.exit_code == 0
        assert "Cleared" in result.output
        assert "No library loaded" in result.output

    def test_eval_reports_an_unknown_definition(self) -> None:
        result = runner.invoke(app, ["repl", "--library", str(HELLO_WORLD)], input="eval Missing\nquit\n")

        assert result.exit_code == 0
        assert "Definition not found: Missing" in result.output

    def test_ast_renders_the_tree_of_an_expression(self) -> None:
        result = runner.invoke(app, ["repl"], input="ast 1 + 2\nquit\n")

        assert result.exit_code == 0
        assert "expression" in result.output
        assert "literal" in result.output

    def test_ast_of_an_unparseable_expression_renders_an_empty_tree(self) -> None:
        result = runner.invoke(app, ["repl"], input="ast @@@\nquit\n")

        assert result.exit_code == 0
        assert "expression" in result.output

    def test_an_expression_that_fails_reports_the_error(self) -> None:
        result = runner.invoke(app, ["repl"], input="singleton from {1, 2}\nquit\n")

        assert result.exit_code == 0
        assert "at most one element" in result.output
