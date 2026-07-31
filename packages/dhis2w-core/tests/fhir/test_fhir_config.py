"""Unit tests for fhir.toml discovery, load, and save."""

from pathlib import Path

import pytest
from dhis2w_core.fhir_core.config import (
    NoFhirProjectError,
    find_project_fhir_config,
    load_fhir_config,
    load_project,
    write_fhir_config,
)
from dhis2w_core.fhir_core.models import FhirProjectConfig, IgConfig

_MINIMAL_TOML = """
[ig]
id = "dhis2.fhir.example"
canonical = "http://example.org/fhir/"
name = "Dhis2FhirExample"
title = "DHIS2 FHIR Example IG"
publisher = "Example Organisation"

[generate.org_units]
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
    assert config.generate.org_units.root is None
    assert config.generate.org_units.max_level is None
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
