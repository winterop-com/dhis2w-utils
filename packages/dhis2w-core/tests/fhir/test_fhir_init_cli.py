"""CliRunner tests for `d2w fhir init`."""

from __future__ import annotations

from pathlib import Path

import pytest
from dhis2w_cli.main import build_app
from typer.testing import CliRunner

_runner = CliRunner()


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run in an empty temporary working directory."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_init_scaffolds_project(workdir: Path) -> None:
    """`d2w fhir init DIR` writes the full scaffold."""
    result = _runner.invoke(build_app(), ["fhir", "init", "project", "--id", "dhis2.fhir.test"])
    assert result.exit_code == 0, result.output
    project = workdir / "project"
    for relative_path in ["fhir.toml", "ig/sushi-config.yaml", "ig/ig.ini", "ig/input/fsh/aliases.fsh", "Makefile"]:
        assert (project / relative_path).exists(), relative_path
    assert "id: dhis2.fhir.test" in (project / "ig" / "sushi-config.yaml").read_text(encoding="utf-8")


def test_init_skips_existing_without_force(workdir: Path) -> None:
    """A second init leaves existing files alone and reports them as skipped."""
    assert _runner.invoke(build_app(), ["fhir", "init", "project"]).exit_code == 0
    marker = workdir / "project" / "fhir.toml"
    marker.write_text("# customized\n", encoding="utf-8")
    result = _runner.invoke(build_app(), ["fhir", "init", "project"])
    assert result.exit_code == 0, result.output
    assert marker.read_text(encoding="utf-8") == "# customized\n"
    assert "skipped" in result.output


def test_init_force_overwrites(workdir: Path) -> None:
    """`--force` rewrites scaffold files that already exist."""
    assert _runner.invoke(build_app(), ["fhir", "init", "project"]).exit_code == 0
    marker = workdir / "project" / "fhir.toml"
    marker.write_text("# customized\n", encoding="utf-8")
    result = _runner.invoke(build_app(), ["fhir", "init", "project", "--force"])
    assert result.exit_code == 0, result.output
    assert "[ig]" in marker.read_text(encoding="utf-8")


def test_init_json_output(workdir: Path) -> None:  # noqa: ARG001
    """`--json` emits the ScaffoldReport as JSON."""
    result = _runner.invoke(build_app(), ["--json", "fhir", "init", "project"])
    assert result.exit_code == 0, result.output
    assert '"created_files"' in result.output
