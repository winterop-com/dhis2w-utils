"""CliRunner tests for `d2w fhir generate` (service mocked)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_core.fhir_core import GenerateAllReport, GenerateReport
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
    with patch("dhis2w_core.v42.plugins.fhir.service.generate_option_sets", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate", "option-sets"])
    assert result.exit_code == 0, result.output
    assert "option sets" in result.output
    assert "a note" in result.output
    mock.assert_awaited_once()


def test_generate_org_units_json(fhir_project: Path) -> None:  # noqa: ARG001
    """`--json` emits the GenerateReport as JSON."""
    mock = AsyncMock(return_value=_report("organization", org_unit_count=7, location_count=2))
    with patch("dhis2w_core.v42.plugins.fhir.service.generate_org_units", new=mock):
        result = _runner.invoke(build_app(), ["--json", "fhir", "generate", "org-units"])
    assert result.exit_code == 0, result.output
    assert '"org_unit_count": 7' in result.output


def test_generate_all_renders_both_reports(fhir_project: Path) -> None:  # noqa: ARG001
    """`d2w fhir generate all` renders both sub-reports."""
    report = GenerateAllReport(option_sets=_report("terminology"), org_units=_report("organization"))
    mock = AsyncMock(return_value=report)
    with patch("dhis2w_core.v42.plugins.fhir.service.generate_all", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate", "all"])
    assert result.exit_code == 0, result.output
    assert "option-sets" in result.output
    assert "org-units" in result.output


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
    with patch("dhis2w_core.v42.plugins.fhir.service.generate_option_sets", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "generate", "option-sets"])
    assert result.exit_code == 0, result.output
    assert mock.await_args is not None
    profile = mock.await_args.args[0]
    assert profile.base_url == "https://dhis2.example"
