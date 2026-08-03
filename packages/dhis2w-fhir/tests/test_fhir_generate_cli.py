"""CliRunner tests for `d2w fhir generate` (service mocked)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_fhir import FhirValidationReport, GenerateAllReport, GenerateReport
from dhis2w_fhir.validation.schemas import ValidationFinding
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
    """A working directory holding a fhir.toml and a default PAT profile."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    (config_dir / "profiles.toml").write_text(
        """
default = "probe"

[profiles.probe]
base_url = "https://dhis2.example"
auth = "pat"
token = "d2p_test"
"""
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
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


def test_generate_option_sets_renders_report(fhir_project: Path) -> None:  # noqa: ARG001
    """`d2w fhir generate option-sets` renders counts and notes from the service report."""
    mock = AsyncMock(return_value=_report("terminology", option_set_count=3, notes=["a note"]))
    with patch("dhis2w_fhir.service.generate_option_sets", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate", "option-sets"])
    assert result.exit_code == 0, result.output
    assert "option sets" in result.output
    assert "a note" in result.output
    mock.assert_awaited_once()


def test_generate_organisation_units_json(fhir_project: Path) -> None:  # noqa: ARG001
    """`--json` emits the GenerateReport as JSON."""
    mock = AsyncMock(return_value=_report("organization", organisation_unit_count=7, position_count=2))
    with patch("dhis2w_fhir.service.generate_organisation_units", new=mock):
        result = _runner.invoke(build_app(), ["--json", "fhir", "generate", "org-units"])
    assert result.exit_code == 0, result.output
    assert '"organisation_unit_count": 7' in result.output


def test_generate_all_renders_every_report(fhir_project: Path) -> None:  # noqa: ARG001
    """`d2w fhir generate all` renders every target's report, with the narrative pages rendered last."""
    report = GenerateAllReport(
        foundation=_report("foundation"),
        option_sets=_report("terminology"),
        questionnaires=_report("questionnaires"),
        examples=_report("examples", example_count=2),
        organisation_units=_report("organization"),
        pages=_report("pagecontent", target_base="ig/input", page_count=5, intro_count=3),
    )
    mock = AsyncMock(return_value=report)
    with patch("dhis2w_fhir.service.generate_all", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate", "all"])
    assert result.exit_code == 0, result.output
    titles = ["foundation", "option-sets", "questionnaires", "examples", "org-units", "pages"]
    positions = [result.output.index(f"fhir generate {title}") for title in titles]
    assert positions == sorted(positions)
    assert "ig/input/pagecontent" in result.output


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


def test_generate_without_project_fails_with_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a fhir.toml anywhere up the tree, generate fails and points at `d2w fhir init`."""
    monkeypatch.chdir(tmp_path)
    result = _runner.invoke(build_app(), ["fhir", "generate", "option-sets"])
    assert result.exit_code == 1
    output = result.output + str(result.exception or "")
    assert "d2w fhir init" in output


def test_generate_uses_fhir_toml_profile(fhir_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A `profile` entry in fhir.toml is used when no explicit profile is given."""
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    (fhir_project / "fhir.toml").write_text(_FHIR_TOML + 'profile = "probe"\n', encoding="utf-8")
    mock = AsyncMock(return_value=_report("terminology"))
    with patch("dhis2w_fhir.service.generate_option_sets", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate", "option-sets"])
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    profile = mock.await_args.args[0]
    assert profile.base_url == "https://dhis2.example"


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


def test_validate_renders_findings_and_exit_code(fhir_project: Path) -> None:
    """`d2w fhir validate` renders error rows, rolls infos up, writes all three reports, exits 1."""
    mock = AsyncMock(return_value=_error_report())
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "validate"])
    assert result.exit_code == 1, result.output
    assert "invalid-code" in result.output
    assert "spaced-code x1" in result.output
    assert "two words" not in result.output
    markdown = fhir_project / "reports" / "fhir-validate-report.md"
    assert "## options" in markdown.read_text(encoding="utf-8")
    csv_report = fhir_project / "reports" / "fhir-validate-report.csv"
    lines = csv_report.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "severity,category,resource_type,uid,name,code,message"
    assert len(lines) == 3
    assert "error,invalid-code,options,Op1aaaaaaaa," in lines[1]
    pdf_report = fhir_project / "reports" / "fhir-validate-report.pdf"
    assert pdf_report.read_bytes().startswith(b"%PDF")
    for suffix in ("md", "csv", "pdf"):
        assert f"fhir-validate-report.{suffix}" in result.output
    mock.assert_awaited_once()


def test_validate_report_stem_and_format_selection(fhir_project: Path) -> None:
    """`--report` takes a path stem and `--format` narrows which files are written."""
    mock = AsyncMock(return_value=_error_report())
    stem = fhir_project / "out" / "codes"
    stem.parent.mkdir()
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        result = _runner.invoke(
            build_app(), ["fhir", "validate", "--no-fail", "--report", str(stem), "--format", "csv,pdf"]
        )
    assert result.exit_code == 0, result.output
    assert (stem.parent / "codes.csv").exists()
    assert (stem.parent / "codes.pdf").exists()
    assert not (stem.parent / "codes.md").exists()


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


def test_validate_no_fail_and_all(fhir_project: Path) -> None:  # noqa: ARG001
    """`--no-fail` exits 0 despite errors; `--all` lists info rows individually."""
    mock = AsyncMock(return_value=_error_report())
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "validate", "--no-fail", "--all"])
    assert result.exit_code == 0, result.output
    assert "two words" in result.output


def test_validate_clean_exits_zero(fhir_project: Path) -> None:  # noqa: ARG001
    """A clean validation run exits 0."""
    mock = AsyncMock(return_value=FhirValidationReport(option_set_count=2, option_count=9))
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "validate"])
    assert result.exit_code == 0, result.output
