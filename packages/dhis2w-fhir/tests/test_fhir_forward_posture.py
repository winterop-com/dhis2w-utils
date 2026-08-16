"""The posture dials: where `import` and `register_completeness` come from when nobody states them.

Three sources, in one order - the flag a run passed, then `[forward]` in fhir.toml, then the default
the key carries. The resolution lives in `service.forward_responses` so the CLI and the MCP tool
cannot resolve it differently, and these tests read it where it is resolved rather than at either edge.

Every run here drains an empty spool, which is what makes the whole matrix cheap: a drain with
nothing to translate answers before a client is opened, and the report it answers with states both
dials. Nothing in this file reaches a network.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from dhis2w_core.profile import resolve
from dhis2w_fhir import load_project, service
from dhis2w_fhir.config import FHIR_CONFIG_FILENAME, ForwardConfig, UnknownFhirConfigKeyError, load_fhir_config

_BASE_URL = "https://dhis2.example"

_IG_TABLE = """
[ig]
id = "dhis2.fhir.posture"
canonical = "http://example.org/fhir"
name = "Posture"
title = "Posture"
publisher = "Winterop"
"""


def _write_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point profile resolution at a profile nothing in this file ever connects with."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    (config_dir / "profiles.toml").write_text(
        f'default = "probe"\n\n[profiles.probe]\nbase_url = "{_BASE_URL}"\nauth = "pat"\ntoken = "d2p_test"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)


@pytest.fixture
def posture_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project with an empty spool, whose `[forward]` table each test writes for itself."""
    _write_profile(tmp_path, monkeypatch)
    root = tmp_path / "project"
    root.mkdir()
    (root / FHIR_CONFIG_FILENAME).write_text(_IG_TABLE, encoding="utf-8")
    return root


def _state_forward_table(root: Path, table: str) -> None:
    """Put one `[forward]` table into the project's config, replacing whatever was there."""
    (root / FHIR_CONFIG_FILENAME).write_text(f"{_IG_TABLE}\n[forward]\n{table}\n", encoding="utf-8")


async def _drain(
    root: Path, *, import_responses: bool | None = None, register_completeness: bool | None = None
) -> service.ForwardReport:
    """One drain of the project's empty spool, stating what the caller stated and nothing else."""
    return await service.forward_responses(
        resolve(None).profile,
        load_project(root),
        import_responses=import_responses,
        register_completeness=register_completeness,
    )


async def test_a_project_that_states_nothing_forwards_as_a_dry_run_that_registers(posture_project: Path) -> None:
    """The defaults are what the keys carry, so a project with no `[forward]` table behaves as it always did."""
    report = await _drain(posture_project)

    assert report.dry_run is True
    assert report.register_completeness is True


async def test_the_table_decides_when_no_flag_states_a_posture(posture_project: Path) -> None:
    """A project whose drains are routine states it once, and the bare command honours both keys."""
    _state_forward_table(posture_project, "import = true\nregister_completeness = false")
    report = await _drain(posture_project)

    assert report.dry_run is False
    assert report.register_completeness is False


async def test_a_stated_flag_outranks_the_table_in_either_direction(posture_project: Path) -> None:
    """A flag is one run's decision and the table is the project's, and the run's wins - both ways round."""
    _state_forward_table(posture_project, "import = true\nregister_completeness = false")
    held_back = await _drain(posture_project, import_responses=False, register_completeness=True)

    assert held_back.dry_run is True
    assert held_back.register_completeness is True

    _state_forward_table(posture_project, "import = false\nregister_completeness = true")
    committed = await _drain(posture_project, import_responses=True, register_completeness=False)

    assert committed.dry_run is False
    assert committed.register_completeness is False


async def test_a_stated_false_is_a_statement_rather_than_silence(posture_project: Path) -> None:
    """The whole reason the parameters are three-valued: `--dry-run` against `import = true` has to hold."""
    _state_forward_table(posture_project, "import = true")
    report = await _drain(posture_project, import_responses=False)

    assert report.dry_run is True


def test_the_key_in_the_file_is_import_and_the_field_is_the_python_name() -> None:
    """`import` is a Python keyword, so the field is aliased - and the file accepts the key it declares."""
    assert ForwardConfig.model_validate({"import": True}).import_responses is True
    assert ForwardConfig().import_responses is False


def test_the_python_field_name_is_not_a_second_spelling_in_the_file(posture_project: Path) -> None:
    """One name per setting: a file naming the Python field is a file naming a key nothing declares."""
    _state_forward_table(posture_project, "import_responses = true")

    with pytest.raises(UnknownFhirConfigKeyError) as refusal:
        load_fhir_config(posture_project / FHIR_CONFIG_FILENAME)

    assert "unknown key 'import_responses' in [forward]" in str(refusal.value)


def test_a_misspelled_key_is_answered_with_the_name_the_file_takes(posture_project: Path) -> None:
    """The suggestion is drawn from the names the file declares, so an aliased key suggests the alias."""
    _state_forward_table(posture_project, "improt = true")

    with pytest.raises(UnknownFhirConfigKeyError) as refusal:
        load_fhir_config(posture_project / FHIR_CONFIG_FILENAME)

    assert "did you mean 'import'?" in str(refusal.value)
