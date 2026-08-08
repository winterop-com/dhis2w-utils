"""CliRunner tests for `d2w fhir generate` and `d2w fhir validate` (service mocked)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_fhir import FhirValidationReport, GenerateFullReport, GenerateReport, LoadSetReport
from dhis2w_fhir.validation.schemas import CodeCoverage, SurfaceCodeCoverage, ValidationFinding
from typer.testing import CliRunner

_runner = CliRunner()

_FHIR_TOML = """
[ig]
id = "dhis2.fhir.test"
canonical = "http://example.org/fhir"
name = "Dhis2FhirTest"
title = "DHIS2 FHIR Test IG"
publisher = "Test Organisation"
"""


@pytest.fixture
def fhir_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working directory holding a fhir.toml, a default PAT profile, and a non-default sibling."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    # `secondary` exists purely so `test_generate_uses_fhir_toml_profile` has a profile the
    # default resolution chain would never pick. Asserting against `probe` there would pass
    # whether or not fhir.toml's `profile` key was honoured, since `probe` is also the default.
    (config_dir / "profiles.toml").write_text(
        """
default = "probe"

[profiles.probe]
base_url = "https://dhis2.example"
auth = "pat"
token = "d2p_test"

[profiles.secondary]
base_url = "https://secondary.example"
auth = "pat"
token = "d2p_secondary"
"""
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    # Rich reads COLUMNS when stderr is captured; a wide surface keeps a table cell on one
    # line, so a test can assert an object string without meeting the wrap of a narrow CI tty.
    monkeypatch.setenv("COLUMNS", "300")
    (tmp_path / "fhir.toml").write_text(_FHIR_TOML, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _report(target_directory: str, **overrides: object) -> GenerateReport:
    """Build a small GenerateReport for mocking."""
    defaults: dict[str, object] = {
        "project_root": Path("/project"),
        "target_directory": target_directory,
        "written_files": [f"{target_directory}/sample.fsh"],
    }
    defaults.update(overrides)
    return GenerateReport.model_validate(defaults)


def _full_report() -> GenerateFullReport:
    """Build the seven-target report a bare `d2w fhir generate` renders."""
    return GenerateFullReport(
        foundation=_report("foundation"),
        option_sets=_report("terminology"),
        categories=_report("categories"),
        questionnaires=_report("questionnaires"),
        examples=_report("examples"),
        organisation_units=_report("organization"),
        pages=_report("pagecontent", target_base="ig/input"),
    )


def test_generate_option_sets_renders_report(fhir_project: Path) -> None:  # noqa: ARG001
    """`d2w fhir generate option-sets` renders counts and notes from the service report."""
    mock = AsyncMock(return_value=_report("terminology", option_set_count=3, notes=["a note"]))
    with patch("dhis2w_fhir.service.generate_option_sets", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate", "option-sets"])
    assert result.exit_code == 0, result.output
    assert "option sets" in result.output
    assert "a note" in result.output
    mock.assert_awaited_once()


def test_generate_categories_renders_report(fhir_project: Path) -> None:  # noqa: ARG001
    """`d2w fhir generate categories` renders counts and notes from the service report."""
    mock = AsyncMock(return_value=_report("resources/categories", category_count=4, notes=["a note"]))
    with patch("dhis2w_fhir.service.generate_categories", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate", "categories"])
    assert result.exit_code == 0, result.output
    assert "categories" in result.output
    assert "a note" in result.output
    mock.assert_awaited_once()


def test_generate_renders_a_zero_count_row(fhir_project: Path) -> None:  # noqa: ARG001
    """A target's own count row renders at zero: the table's shape says what the target counts."""
    mock = AsyncMock(return_value=_report("terminology", option_set_count=0))
    with patch("dhis2w_fhir.service.generate_option_sets", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate", "option-sets"])
    assert result.exit_code == 0, result.output
    assert "option sets" in result.stderr


def test_generate_organisation_units_json(fhir_project: Path) -> None:  # noqa: ARG001
    """`--json` emits the GenerateReport as JSON."""
    mock = AsyncMock(return_value=_report("organization", organisation_unit_count=7, position_count=2))
    with patch("dhis2w_fhir.service.generate_organisation_units", new=mock):
        result = _runner.invoke(build_app(), ["--json", "fhir", "generate", "org-units"])
    assert result.exit_code == 0, result.output
    assert '"organisation_unit_count": 7' in result.output


def test_bare_generate_runs_the_full_pipeline(fhir_project: Path) -> None:  # noqa: ARG001
    """`d2w fhir generate` with no target runs every target off the one full-pipeline call."""
    mock = AsyncMock(return_value=_full_report())
    with patch("dhis2w_fhir.service.generate_full", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate"])
    assert result.exit_code == 0, result.output
    mock.assert_awaited_once()


def test_bare_generate_renders_one_consolidated_table(fhir_project: Path) -> None:  # noqa: ARG001
    """A full run reports one row per target, not one table per target."""
    report = GenerateFullReport(
        foundation=_report("foundation"),
        option_sets=_report("terminology"),
        categories=_report("categories"),
        questionnaires=_report("questionnaires"),
        examples=_report("examples", example_count=2),
        organisation_units=_report("organization"),
        pages=_report("pagecontent", target_base="ig/input", page_count=5, intro_count=3),
    )
    mock = AsyncMock(return_value=report)
    with patch("dhis2w_fhir.service.generate_full", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate"])
    assert result.exit_code == 0, result.output
    assert "fhir generate (7)" in result.stderr
    assert "fhir generate foundation" not in result.stderr
    targets = ["foundation", "option-sets", "categories", "questionnaires", "examples", "org-units", "pages"]
    positions = [result.stderr.index(target) for target in targets]
    assert positions == sorted(positions)


def _noted_report(project_root: Path) -> GenerateFullReport:
    """The seven-target report with one note on the examples target, rooted where a test can write."""
    report = _full_report()
    for outcome in (
        report.foundation,
        report.option_sets,
        report.categories,
        report.questionnaires,
        report.examples,
        report.organisation_units,
        report.pages,
    ):
        outcome.project_root = project_root
    report.examples.notes.append("no data values for the period")
    return report


def test_bare_generate_counts_its_notes_and_writes_them_to_a_file(fhir_project: Path) -> None:
    """Eight targets of aggregate notes bury the summary table, so the terminal counts and the file lists."""
    mock = AsyncMock(return_value=_noted_report(fhir_project))
    with patch("dhis2w_fhir.service.generate_full", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate"])
    assert result.exit_code == 0, result.output
    notes = fhir_project / "reports" / "fhir-generate-notes.md"
    assert "no data values for the period" not in result.stderr
    assert "1 note(s) across 1 target(s)" in result.stderr
    assert str(notes) in result.stderr
    body = notes.read_text(encoding="utf-8")
    assert "## examples" in body
    assert "- no data values for the period" in body
    assert "https://dhis2.example" in body


def test_bare_generate_details_prints_every_note_with_its_target(fhir_project: Path) -> None:
    """`--details` is the firehose, and one table for seven targets means a note names the target."""
    mock = AsyncMock(return_value=_noted_report(fhir_project))
    with patch("dhis2w_fhir.service.generate_full", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate", "--details"])
    assert result.exit_code == 0, result.output
    assert "note: examples: no data values for the period" in result.stderr
    assert not (fhir_project / "reports" / "fhir-generate-notes.md").exists()


def test_a_run_that_raised_no_note_writes_no_notes_file(fhir_project: Path) -> None:
    """Nothing to say means nothing said and nothing written - a clean run stays a clean run."""
    mock = AsyncMock(return_value=_full_report())
    with patch("dhis2w_fhir.service.generate_full", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate"])
    assert result.exit_code == 0, result.output
    assert "note(s) across" not in result.stderr
    assert not (fhir_project / "reports" / "fhir-generate-notes.md").exists()


def test_a_solo_target_still_prints_its_notes_inline(fhir_project: Path) -> None:
    """One target's notes are short and were asked for by name, so they stay on the terminal."""
    report = _report("terminology", notes=["1 option sets are absent from the selection"])
    report.project_root = fhir_project
    mock = AsyncMock(return_value=report)
    with patch("dhis2w_fhir.service.generate_option_sets", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate", "option-sets"])
    assert result.exit_code == 0, result.output
    assert "1 option sets are absent from the selection" in result.stderr
    assert not (fhir_project / "reports" / "fhir-generate-notes.md").exists()


def test_bare_generate_json_emits_the_full_report(fhir_project: Path) -> None:  # noqa: ARG001
    """`--json` dumps the whole GenerateFullReport on stdout and leaves stderr silent."""
    mock = AsyncMock(return_value=_full_report())
    with patch("dhis2w_fhir.service.generate_full", new=mock):
        result = _runner.invoke(build_app(), ["--json", "fhir", "generate"])
    assert result.exit_code == 0, result.output
    assert '"foundation"' in result.stdout
    assert '"pages"' in result.stdout
    assert result.stderr == ""


def test_bare_generate_writes_nothing_to_stdout_in_human_mode(fhir_project: Path) -> None:  # noqa: ARG001
    """Tables and notes are narration, so they land on stderr and stdout stays free for a pipe."""
    mock = AsyncMock(return_value=_full_report())
    with patch("dhis2w_fhir.service.generate_full", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate"])
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "fhir generate (7)" in result.stderr


def test_bare_generate_narrates_its_steps(fhir_project: Path) -> None:  # noqa: ARG001
    """The default builds a reporter, hands it to the service, and closes with the run summary."""
    mock = AsyncMock(return_value=_full_report())
    with patch("dhis2w_fhir.service.generate_full", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate"])
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.kwargs["reporter"] is not None
    assert "running 8 step(s)" in result.stderr
    assert "full pipeline: 7 file(s) written across 7 target(s)" in result.stderr


def test_bare_generate_no_progress_builds_no_reporter(fhir_project: Path) -> None:  # noqa: ARG001
    """`--no-progress` means no narration at all, so the service is handed nothing to announce to."""
    mock = AsyncMock(return_value=_full_report())
    with patch("dhis2w_fhir.service.generate_full", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate", "--no-progress"])
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.kwargs["reporter"] is None
    assert "running" not in result.stderr


def test_bare_generate_json_builds_no_reporter(fhir_project: Path) -> None:  # noqa: ARG001
    """`--json` keeps stderr quiet, so the progress lines are not built either."""
    mock = AsyncMock(return_value=_full_report())
    with patch("dhis2w_fhir.service.generate_full", new=mock):
        result = _runner.invoke(build_app(), ["--json", "fhir", "generate"])
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.kwargs["reporter"] is None


def test_generate_target_takes_its_own_progress_flag(fhir_project: Path) -> None:  # noqa: ARG001
    """A named target carries `--progress/--no-progress` after the target name, not before it."""
    mock = AsyncMock(return_value=_report("terminology"))
    with patch("dhis2w_fhir.service.generate_option_sets", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate", "option-sets", "--no-progress"])
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.kwargs["reporter"] is None

    with patch("dhis2w_fhir.service.generate_option_sets", new=mock):
        narrated = _runner.invoke(build_app(), ["fhir", "generate", "option-sets"])
    assert narrated.exit_code == 0, narrated.output
    assert mock.await_args.kwargs["reporter"] is not None
    assert "running 2 step(s)" in narrated.stderr


def test_generate_pages_renders_report(fhir_project: Path) -> None:  # noqa: ARG001
    """`d2w fhir generate pages` renders the page and intro counts against the pagecontent target."""
    mock = AsyncMock(
        return_value=_report("pagecontent", target_base="ig/input", page_count=5, intro_count=4, notes=["a note"])
    )
    with patch("dhis2w_fhir.service.generate_pages", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate", "pages"])
    assert result.exit_code == 0, result.output
    assert "pages" in result.output
    assert "intros" in result.output
    assert "ig/input/pagecontent" in result.output
    assert "a note" in result.output
    mock.assert_awaited_once()


def test_generate_pages_json(fhir_project: Path) -> None:  # noqa: ARG001
    """`--json` emits the pages GenerateReport as JSON."""
    mock = AsyncMock(return_value=_report("pagecontent", target_base="ig/input", page_count=5, intro_count=4))
    with patch("dhis2w_fhir.service.generate_pages", new=mock):
        result = _runner.invoke(build_app(), ["--json", "fhir", "generate", "pages"])
    assert result.exit_code == 0, result.output
    assert '"page_count": 5' in result.output
    assert '"intro_count": 4' in result.output


def test_generate_foundation_renders_report(fhir_project: Path) -> None:  # noqa: ARG001
    """`d2w fhir generate foundation` syncs the instance-independent artifacts."""
    mock = AsyncMock(return_value=_report("foundation"))
    with patch("dhis2w_fhir.service.generate_foundation", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate", "foundation"])
    assert result.exit_code == 0, result.output
    assert "foundation" in result.output
    mock.assert_awaited_once()
    assert mock.await_args is not None
    assert "running 1 step(s)" in result.stderr


def test_generate_load_set_renders_the_corpus_report(fhir_project: Path) -> None:  # noqa: ARG001
    """`d2w fhir generate load-set` renders the response and questionnaire counts the service reports."""
    report = LoadSetReport(
        project_root=Path("/project"),
        target_directory="load",
        written_files=["load/a1b2c3d4e5f.json"],
        response_count=50,
        questionnaire_count=2,
        notes=["a note"],
    )
    mock = AsyncMock(return_value=report)
    with patch("dhis2w_fhir.service.generate_load_set", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate", "load-set"])
    assert result.exit_code == 0, result.output
    assert "responses" in result.output
    assert "a note" in result.output
    mock.assert_awaited_once()


def test_generate_load_set_passes_per_target_and_output_dir(fhir_project: Path) -> None:
    """`--per-target` and `--output-dir` reach the service as the keyword arguments it takes."""
    mock = AsyncMock(return_value=LoadSetReport(project_root=Path("/project"), target_directory="load"))
    with patch("dhis2w_fhir.service.generate_load_set", new=mock):
        result = _runner.invoke(
            build_app(),
            ["fhir", "generate", "load-set", "--per-target", "5", "--output-dir", str(fhir_project / "scratch")],
        )
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.kwargs["per_target"] == 5
    assert mock.await_args.kwargs["output_directory"] == fhir_project / "scratch"


def test_generate_load_set_rejects_a_per_target_below_one(fhir_project: Path) -> None:  # noqa: ARG001
    """A load set of zero responses per target is a typo, not a request."""
    result = _runner.invoke(build_app(), ["fhir", "generate", "load-set", "--per-target", "0"])
    assert result.exit_code != 0


def test_bare_generate_leaves_the_load_set_alone(fhir_project: Path) -> None:  # noqa: ARG001
    """A load set is test data rather than IG source, so the full pipeline never writes one."""
    load_mock = AsyncMock(return_value=LoadSetReport(project_root=Path("/project"), target_directory="load"))
    full_mock = AsyncMock(return_value=_full_report())
    with (
        patch("dhis2w_fhir.service.generate_load_set", new=load_mock),
        patch("dhis2w_fhir.service.generate_full", new=full_mock),
    ):
        result = _runner.invoke(build_app(), ["fhir", "generate"])
    assert result.exit_code == 0, result.output
    load_mock.assert_not_awaited()


def test_generate_without_project_fails_with_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a fhir.toml anywhere up the tree, generate fails and points at `d2w fhir init`."""
    monkeypatch.chdir(tmp_path)
    result = _runner.invoke(build_app(), ["fhir", "generate", "option-sets"])
    assert result.exit_code == 1
    output = result.output + str(result.exception or "")
    assert "d2w fhir init" in output


def test_bare_generate_without_project_fails_with_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The bare run resolves the project the same way a named target does, and fails the same way."""
    monkeypatch.chdir(tmp_path)
    result = _runner.invoke(build_app(), ["fhir", "generate"])
    assert result.exit_code == 1
    output = result.output + str(result.exception or "")
    assert "d2w fhir init" in output


def test_generate_uses_fhir_toml_profile(fhir_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A `profile` entry in fhir.toml is used when no explicit profile is given."""
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    # `profile` is a top-level key of fhir.toml, so it has to precede the `[ig]` table - append it
    # after and TOML reads it as `ig.profile`, which FhirProjectConfig drops on the floor.
    (fhir_project / "fhir.toml").write_text('profile = "secondary"\n' + _FHIR_TOML, encoding="utf-8")
    mock = AsyncMock(return_value=_report("terminology"))
    with patch("dhis2w_fhir.service.generate_option_sets", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate", "option-sets"])
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    profile = mock.await_args.args[0]
    assert profile.base_url == "https://secondary.example"


def _error_report() -> FhirValidationReport:
    """One error plus one info finding for CLI rendering tests."""
    error = ValidationFinding(
        severity="error",
        category="invalid-code",
        resource_type="options",
        uid="Op1aaaaaaaa",
        name="Male [in Sex]",
        code=" M ",
        message="code is not a valid FHIR code",
    )
    info = ValidationFinding(
        severity="info",
        category="spaced-code",
        resource_type="options",
        uid="Op2aaaaaaaa",
        name="Spaced [in Sex]",
        code="two words",
        message="code contains spaces",
    )
    return FhirValidationReport(option_set_count=1, option_count=2, findings=[error, info])


def _warning_report() -> FhirValidationReport:
    """One warning finding alone - what a clean-but-noisy national instance reports."""
    return FhirValidationReport(
        object_count=1,
        findings=[
            ValidationFinding(
                severity="warning",
                category="template-hostile-name",
                resource_type="organisationUnits",
                uid="Ou1aaaaaaaa",
                name="Kids <5",
                code="OU_K5",
                message="name carries a character the publisher's template writes unescaped",
            )
        ],
    )


def _scoped_report() -> FhirValidationReport:
    """A scope-resolved report: one selection warning, one selection info, two instance infos, coverage."""
    return FhirValidationReport(
        object_count=4,
        code_coverage=CodeCoverage(surfaces=[SurfaceCodeCoverage(surface="dataSets", usable_count=1, object_count=2)]),
        findings=[
            ValidationFinding(
                severity="warning",
                scope="selection",
                category="invalid-code",
                resource_type="dataSets",
                uid="Ds1aaaaaaaa",
                name="Selected",
                code=" X ",
                message="code is not a valid FHIR code",
            ),
            ValidationFinding(
                severity="info",
                scope="selection",
                category="spaced-code",
                resource_type="options",
                uid="Op1aaaaaaaa",
                name="Spaced [in Sex]",
                code="two words",
                message="code contains spaces",
            ),
            ValidationFinding(
                severity="info",
                scope="instance",
                category="invalid-code",
                resource_type="dataElements",
                uid="De1aaaaaaaa",
                name="Outside",
                code=" Y ",
                message="code is not a valid FHIR code",
            ),
            ValidationFinding(
                severity="info",
                scope="instance",
                category="missing-code",
                resource_type="attributes",
                uid="At1aaaaaaaa",
                name="Uncoded",
                code=None,
                message="attribute has no code",
            ),
        ],
    )


def test_validate_renders_findings_and_exit_code(fhir_project: Path) -> None:
    """`d2w fhir validate` lists the errors, rolls every severity up by category, writes three reports, exits 1."""
    mock = AsyncMock(return_value=_error_report())
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "validate"])
    assert result.exit_code == 1, result.output
    assert "findings by category" in result.output
    assert "invalid-code" in result.output
    assert "spaced-code" in result.output
    assert "Op1aaaaaaaa" in result.output
    assert "two words" not in result.output
    assert "code contains spaces" not in result.output
    markdown = fhir_project / "reports" / "fhir-validate-report.md"
    assert "## options" in markdown.read_text(encoding="utf-8")
    csv_report = fhir_project / "reports" / "fhir-validate-report.csv"
    lines = csv_report.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "severity,scope,category,resource_type,uid,name,code,message"
    assert len(lines) == 3
    assert "error,instance,invalid-code,options,Op1aaaaaaaa," in lines[1]
    pdf_report = fhir_project / "reports" / "fhir-validate-report.pdf"
    assert pdf_report.read_bytes().startswith(b"%PDF")
    for suffix in ("md", "csv", "pdf"):
        assert f"fhir-validate-report.{suffix}" in result.output
    mock.assert_awaited_once()


def test_validate_writes_into_the_output_directory(fhir_project: Path) -> None:
    """`--output-dir` names a directory; the files inside it keep the fhir-validate-report basename."""
    mock = AsyncMock(return_value=_error_report())
    destination = fhir_project / "out"
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        result = _runner.invoke(
            build_app(), ["fhir", "validate", "--no-fail", "--output-dir", str(destination), "--format", "csv,pdf"]
        )
    assert result.exit_code == 0, result.output
    assert (destination / "fhir-validate-report.csv").exists()
    assert (destination / "fhir-validate-report.pdf").exists()
    assert not (destination / "fhir-validate-report.md").exists()
    # The directory reading as a stem would give `out/out.csv`, or `fhir-validate-report.md.md`
    # for the default; neither name exists, because the basename is the plugin's, not the path's.
    assert not (destination / "out.csv").exists()
    assert not list(destination.glob("*.md.md"))


def test_validate_creates_a_missing_output_directory(fhir_project: Path) -> None:
    """A directory that does not exist yet is created rather than failing the run after the sweep."""
    mock = AsyncMock(return_value=FhirValidationReport())
    destination = fhir_project / "deep" / "nested"
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "validate", "--output-dir", str(destination), "--format", "md"])
    assert result.exit_code == 0, result.output
    assert (destination / "fhir-validate-report.md").exists()


def test_validate_rejects_an_unknown_format(fhir_project: Path) -> None:  # noqa: ARG001
    """An unknown `--format` name fails before any DHIS2 call."""
    result = _runner.invoke(build_app(), ["fhir", "validate", "--format", "md,html"])
    assert result.exit_code != 0
    assert "html" in result.output


def test_validate_code_source_override_reaches_the_service(fhir_project: Path) -> None:  # noqa: ARG001
    """`--code-source code` is passed through to the service as the effective source."""
    mock = AsyncMock(return_value=FhirValidationReport())
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "validate", "--code-source", "code"])
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.args[2] == "code"
    assert "code source" in result.output


def test_validate_rejects_an_unknown_code_source(fhir_project: Path) -> None:  # noqa: ARG001
    """The choice is enumerated, so an unknown value is a usage error naming the flag."""
    result = _runner.invoke(build_app(), ["fhir", "validate", "--code-source", "uid"])
    assert result.exit_code != 0
    assert "--code-source" in result.output


def test_a_warning_is_counted_in_the_rollup_and_left_to_the_report(fhir_project: Path) -> None:
    """A national instance raises hundreds of warnings, so the terminal counts them and the file lists them."""
    mock = AsyncMock(return_value=_warning_report())
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "validate"])
    assert result.exit_code == 0, result.output
    assert "findings by category" in result.output
    assert "template-hostile-name" in result.output
    assert "organisationUnits" not in result.output
    assert "OU_K5" not in result.output
    assert "passed: 1 warning(s), 0 info(s)" in result.stderr
    assert str(fhir_project / "reports" / "fhir-validate-report.md") in result.stderr


def test_validate_rollup_splits_by_scope_selection_first(fhir_project: Path) -> None:  # noqa: ARG001
    """The rollup rows carry the scope, and within one severity the build path sorts before the hygiene."""
    mock = AsyncMock(return_value=_scoped_report())
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "validate"])
    assert result.exit_code == 0, result.output
    assert "findings by category (4)" in result.stderr
    assert "Scope" in result.stderr
    assert "selection" in result.stderr
    assert "instance" in result.stderr
    # Within the info severity the selection row (spaced-code) sorts before both instance rows;
    # category order alone would put missing-code first, so this is the scope key at work.
    assert result.stderr.index("spaced-code") < result.stderr.index("missing-code")


def test_validate_summary_carries_selection_and_coverage_rows(fhir_project: Path) -> None:  # noqa: ARG001
    """With a resolved scope the summary says the selection split and the code-coverage fraction."""
    mock = AsyncMock(return_value=_scoped_report())
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "validate"])
    assert result.exit_code == 0, result.output
    assert "selection findings" in result.stderr
    assert "0 errors, 1 warning, 1 info" in result.stderr
    assert "code coverage" in result.stderr
    assert "1/2 (selection objects with slug-safe codes)" in result.stderr
    assert "passed: 1 selection warning(s), 1 selection info(s), 2 instance finding(s)" in result.stderr


def test_validate_summary_omits_the_selection_rows_without_a_scope(fhir_project: Path) -> None:  # noqa: ARG001
    """A hand-built report without code coverage renders neither selection row nor coverage line."""
    mock = AsyncMock(return_value=_warning_report())
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "validate"])
    assert result.exit_code == 0, result.output
    assert "selection findings" not in result.stderr
    assert "code coverage" not in result.stderr
    assert "passed: 1 warning(s), 0 info(s)" in result.stderr


def test_validate_details_lists_every_finding(fhir_project: Path) -> None:  # noqa: ARG001
    """`--details` is the firehose: warnings and infos get their own rows alongside the rollup."""
    mock = AsyncMock(return_value=_warning_report())
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "validate", "--details"])
    assert result.exit_code == 0, result.output
    assert "findings by category" in result.output
    assert "organisationUnits" in result.output
    assert "OU_K5" in result.output


def test_validate_details_table_carries_the_scope(fhir_project: Path) -> None:  # noqa: ARG001
    """The per-finding table says whose problem each row is - build path or instance hygiene."""
    mock = AsyncMock(return_value=_scoped_report())
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "validate", "--details"])
    assert result.exit_code == 0, result.output
    assert "findings (4)" in result.stderr
    assert "Ds1aaaaaaaa" in result.stderr
    assert "De1aaaaaaaa" in result.stderr
    # The selection warning and the instance info both name their scope on the row.
    lines = result.stderr.splitlines()
    assert any("Ds1aaaaaaaa" in line and "selection" in line for line in lines)
    assert any("De1aaaaaaaa" in line and "instance" in line for line in lines)


def test_validate_no_fail_and_details(fhir_project: Path) -> None:  # noqa: ARG001
    """`--no-fail` exits 0 despite errors; `--details` lists info rows individually."""
    mock = AsyncMock(return_value=_error_report())
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "validate", "--no-fail", "--details"])
    assert result.exit_code == 0, result.output
    assert "two words" in result.output
    assert "error(s) found" not in result.output


def test_validate_fail_is_the_default(fhir_project: Path) -> None:  # noqa: ARG001
    """`--fail` is what the command already does, so passing it explicitly changes nothing."""
    mock = AsyncMock(return_value=_error_report())
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "validate", "--fail"])
    assert result.exit_code == 1, result.output
    assert "1 error(s) found" in result.stderr


def test_validate_narrates_its_steps(fhir_project: Path) -> None:  # noqa: ARG001
    """The sweep is the longest thing the plugin does, so it announces its five steps by default."""
    mock = AsyncMock(return_value=FhirValidationReport())
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "validate"])
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.kwargs["reporter"] is not None
    assert "running 5 step(s)" in result.stderr


def test_validate_no_progress_builds_no_reporter(fhir_project: Path) -> None:  # noqa: ARG001
    """`--no-progress` hands the service nothing to announce to."""
    mock = AsyncMock(return_value=FhirValidationReport())
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "validate", "--no-progress"])
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    assert mock.await_args.kwargs["reporter"] is None


def test_validate_renders_its_tables_on_stderr(fhir_project: Path) -> None:  # noqa: ARG001
    """The findings table is narration; only `--json` puts anything on stdout."""
    mock = AsyncMock(return_value=_error_report())
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "validate", "--no-fail"])
    assert result.exit_code == 0, result.output
    assert "fhir validate" in result.stderr
    assert "invalid-code" in result.stderr
    assert result.stdout == ""


def test_validate_clean_exits_zero(fhir_project: Path) -> None:  # noqa: ARG001
    """A clean validation run exits 0."""
    mock = AsyncMock(return_value=FhirValidationReport(option_set_count=2, option_count=9))
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "validate"])
    assert result.exit_code == 0, result.output
