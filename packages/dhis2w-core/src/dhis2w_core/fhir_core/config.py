"""Discovery, load, and save of the `fhir.toml` project configuration.

A FHIR IG project is any directory holding a `fhir.toml` (scaffolded by
`d2w fhir init`). Discovery walks up from the working directory, mirroring
how `.dhis2/profiles.toml` is found.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import tomli_w

from dhis2w_core.fhir_core.models import FhirProject, FhirProjectConfig

FHIR_CONFIG_FILENAME = "fhir.toml"


class NoFhirProjectError(LookupError):
    """Raised when no `fhir.toml` is found walking up from the working directory."""


def find_project_fhir_config(start: Path | None = None) -> Path | None:
    """Walk up from `start` (defaulting to `$PWD`) looking for `fhir.toml`."""
    cwd = start or Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / FHIR_CONFIG_FILENAME
        if candidate.exists():
            return candidate
    return None


def load_fhir_config(path: Path) -> FhirProjectConfig:
    """Parse and validate a `fhir.toml` file."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    return FhirProjectConfig.model_validate(raw)


def write_fhir_config(path: Path, config: FhirProjectConfig) -> None:
    """Write a `fhir.toml` with default permissions - it is committed project config, not a credential store."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomli_w.dumps(config.model_dump(exclude_none=True)), encoding="utf-8")


def load_project(start: Path | None = None) -> FhirProject:
    """Discover and load the nearest FHIR project, raising `NoFhirProjectError` when there is none."""
    path = find_project_fhir_config(start)
    if path is None:
        raise NoFhirProjectError(
            "no fhir.toml found in this directory or any parent. "
            "Run `d2w fhir init [DIRECTORY]` to scaffold a FHIR IG project first."
        )
    return FhirProject(config=load_fhir_config(path), config_path=path.resolve())
