"""Per-version CLI parity for `d2w fhir` - each tree's cli.py dispatches to its own service."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_core.fhir_core import GenerateReport
from typer.testing import CliRunner

_runner = CliRunner()

_FHIR_TOML = """
[ig]
id = "dhis2.fhir.parity"
canonical = "http://example.org/fhir"
name = "Dhis2FhirParity"
title = "Parity IG"
publisher = "Parity Org"
"""


def test_fhir_init_cli_parity(
    core_version: str,
    core_profile: None,  # noqa: ARG001
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`d2w fhir init` scaffolds through every version tree's cli module."""
    monkeypatch.setenv("DHIS2_VERSION", core_version)
    result = _runner.invoke(build_app(), ["fhir", "init", str(tmp_path / "project")])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "project" / "fhir.toml").exists()


def test_fhir_generate_cli_parity(
    core_version: str,
    core_profile: None,  # noqa: ARG001
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`d2w fhir generate option-sets` calls the version tree's own service function."""
    (tmp_path / "fhir.toml").write_text(_FHIR_TOML, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DHIS2_VERSION", core_version)
    report = GenerateReport(project_root=tmp_path, target_directory="terminology", option_set_count=1)
    mock = AsyncMock(return_value=report)
    with patch(f"dhis2w_core.{core_version}.plugins.fhir.service.generate_option_sets", new=mock):
        result = _runner.invoke(build_app(), ["-p", "probe", "fhir", "generate", "option-sets"])
    assert result.exit_code == 0, result.output
    mock.assert_awaited_once()
