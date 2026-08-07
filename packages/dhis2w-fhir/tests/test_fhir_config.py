"""Unit tests for fhir.toml discovery, load, and save."""

from pathlib import Path

import pytest
from dhis2w_fhir.config import (
    FhirProjectConfig,
    GenerateConfig,
    IgConfig,
    NoFhirProjectError,
    find_project_fhir_config,
    load_fhir_config,
    load_project,
    write_fhir_config,
)
from pydantic import ValidationError

_MINIMAL_TOML = """
[ig]
id = "dhis2.fhir.example"
canonical = "http://example.org/fhir/"
name = "Dhis2FhirExample"
title = "DHIS2 FHIR Example IG"
publisher = "Example Organisation"

[generate.organisation_units]
root = ""
max_level = 0
"""


def _make_config() -> FhirProjectConfig:
    """Build a minimal valid config."""
    return FhirProjectConfig(
        ig=IgConfig(
            id="dhis2.fhir.example",
            canonical="http://example.org/fhir",
            name="Dhis2FhirExample",
            title="DHIS2 FHIR Example IG",
            publisher="Example Organisation",
        )
    )


def test_find_walks_up(tmp_path: Path) -> None:
    """Discovery finds fhir.toml in a parent of the start directory."""
    (tmp_path / "fhir.toml").write_text(_MINIMAL_TOML, encoding="utf-8")
    nested = tmp_path / "ig" / "input" / "fsh"
    nested.mkdir(parents=True)
    assert find_project_fhir_config(nested) == tmp_path / "fhir.toml"


def test_find_returns_none_when_absent(tmp_path: Path) -> None:
    """Discovery returns None when no fhir.toml exists anywhere up the tree."""
    assert find_project_fhir_config(tmp_path) is None


def test_load_normalizes_placeholders(tmp_path: Path) -> None:
    """The scaffolded `root = \"\"` and `max_level = 0` placeholders load as None."""
    path = tmp_path / "fhir.toml"
    path.write_text(_MINIMAL_TOML, encoding="utf-8")
    config = load_fhir_config(path)
    assert config.generate.organisation_units.root is None
    assert config.generate.organisation_units.max_level is None
    assert config.ig.canonical == "http://example.org/fhir"


def test_round_trip(tmp_path: Path) -> None:
    """write_fhir_config -> load_fhir_config preserves the config."""
    path = tmp_path / "fhir.toml"
    config = _make_config()
    write_fhir_config(path, config)
    assert load_fhir_config(path) == config


def test_load_project_raises_without_config(tmp_path: Path) -> None:
    """load_project points the user at `d2w fhir init` when nothing is found."""
    with pytest.raises(NoFhirProjectError, match="d2w fhir init"):
        load_project(tmp_path)


def test_load_project_derives_directories(tmp_path: Path) -> None:
    """FhirProject exposes the project root and the ig/input/fsh directory."""
    (tmp_path / "fhir.toml").write_text(_MINIMAL_TOML, encoding="utf-8")
    project = load_project(tmp_path)
    assert project.project_root == tmp_path.resolve()
    assert project.fsh_directory == tmp_path.resolve() / "ig" / "input" / "fsh"


def test_data_definition_tables_parse(tmp_path: Path) -> None:
    """The three data-definition tables load as UID include lists, one per questionnaire form kind."""
    path = tmp_path / "fhir.toml"
    path.write_text(
        _MINIMAL_TOML
        + '\n[generate.data_sets]\ninclude_ids = ["BfMAe6Itzgt"]\n'
        + '\n[generate.event_programs]\ninclude_ids = ["VBqh0ynB2wv"]\n'
        + '\n[generate.tracker_programs]\ninclude_ids = ["IpHINAT79UW"]\n',
        encoding="utf-8",
    )
    config = load_fhir_config(path)
    assert config.generate.data_sets.include_ids == ["BfMAe6Itzgt"]
    assert config.generate.event_programs.include_ids == ["VBqh0ynB2wv"]
    assert config.generate.tracker_programs.include_ids == ["IpHINAT79UW"]


def test_tracker_program_selection_defaults_to_everything() -> None:
    """An absent `[generate.tracker_programs]` means every tracker program on the instance."""
    assert GenerateConfig().tracker_programs.include_ids == []


def test_questionnaire_naming_tokens_default_to_the_registry() -> None:
    """The data-set, program, and program-stage tokens default to DS / PR / PS, and may all be dropped."""
    assert GenerateConfig().naming.data_set == "DS"
    assert GenerateConfig().naming.program == "PR"
    assert GenerateConfig().naming.program_stage == "PS"
    assert GenerateConfig.model_validate({"naming": {"data_set": "", "program": ""}}).naming.data_set == ""
    assert GenerateConfig.model_validate({"naming": {"program_stage": ""}}).naming.program_stage == ""


def test_the_program_stage_token_is_overridable_and_validated() -> None:
    """A custom program-stage token lands in FSH names, so it takes the same letter-leading rule as its peers."""
    assert GenerateConfig.model_validate({"naming": {"program_stage": "Stage"}}).naming.program_stage == "Stage"
    with pytest.raises(ValidationError, match="letter-leading alphanumeric"):
        GenerateConfig.model_validate({"naming": {"program_stage": "2Stage"}})


def test_locales_default_to_every_locale_found() -> None:
    """An absent `[generate] locales` means every translation locale on the instance is emitted."""
    assert GenerateConfig().locales == []


def test_locales_are_normalized_to_bcp47() -> None:
    """Java-style DHIS2 tags in fhir.toml are held in the BCP-47 form the emitters compare against."""
    assert GenerateConfig(locales=["pt_BR", "LO", "km"]).locales == ["pt-BR", "lo", "km"]
