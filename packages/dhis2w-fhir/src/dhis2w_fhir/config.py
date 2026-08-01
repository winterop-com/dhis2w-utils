"""The `fhir.toml` document: its models plus discovery, load, and save.

A FHIR IG project is any directory holding a `fhir.toml` (scaffolded by
`d2w fhir init`). Discovery walks up from the working directory, mirroring
how `.dhis2/profiles.toml` is found.

The document composes the per-component selection tables, so this module
depends on the components and never the other way round - an emitter
receives its config as a parameter.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Literal

import tomli_w
from pydantic import BaseModel, ConfigDict, Field, field_validator

from dhis2w_fhir.i18n import normalize_locale
from dhis2w_fhir.names import strip_trailing_slash
from dhis2w_fhir.resources.option_sets.schemas import OptionSetSelection
from dhis2w_fhir.resources.organisation_units.schemas import OrganisationUnitSelection

FHIR_CONFIG_FILENAME = "fhir.toml"


class NoFhirProjectError(LookupError):
    """Raised when no `fhir.toml` is found walking up from the working directory."""


class IgConfig(BaseModel):
    """SUSHI IG identity - the `[ig]` table of `fhir.toml`."""

    id: str
    canonical: str
    name: str
    title: str
    publisher: str

    _normalize_canonical = field_validator("canonical")(strip_trailing_slash)


def _validate_fsh_token(value: str, *, allow_empty: bool) -> str:
    """Require a letter-leading alphanumeric token (it lands in FSH names), optionally empty."""
    if not value:
        if allow_empty:
            return value
        raise ValueError("token must not be empty")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", value):
        raise ValueError("token must be letter-leading alphanumeric (e.g. 'D2', 'Dhis2', 'OU')")
    return value


class NamingConfig(BaseModel):
    """Configurable FSH naming tokens - the `[generate.naming]` table of `fhir.toml`.

    Artifact names concatenate the pascal tokens (`D2` + `OS` + `BirthType` + `CS`);
    ids join the kebab of each non-empty token (`d2-os-birth-type-cs`). `prefix` and
    `option_set` may be empty to drop them; `organisation_unit` must stay non-empty or the
    org-unit artifact names would degenerate to bare `CS`/`LevelCS`. Future group /
    group-set artifacts follow the same scheme (`OUG`, `OUGS`).
    """

    source: Literal["uid", "name"] = "uid"
    prefix: str = "D2"
    option_set: str = "OS"
    organisation_unit: str = "OU"

    @field_validator("prefix", "option_set")
    @classmethod
    def _optional_token(cls, value: str) -> str:
        """Prefix and option_set may be empty or a FSH-name-safe token."""
        return _validate_fsh_token(value, allow_empty=True)

    @field_validator("organisation_unit")
    @classmethod
    def _required_token(cls, value: str) -> str:
        """organisation_unit must be a non-empty FSH-name-safe token."""
        return _validate_fsh_token(value, allow_empty=False)


class GenerateConfig(BaseModel):
    """Generation behaviour - the `[generate]` table of `fhir.toml`."""

    identifier_system_base: str = "http://dhis2.org/fhir"
    concept_code_source: Literal["uid", "code"] = "uid"
    locales: list[str] = Field(default_factory=list)
    naming: NamingConfig = Field(default_factory=NamingConfig)
    option_sets: OptionSetSelection = Field(default_factory=OptionSetSelection)
    organisation_units: OrganisationUnitSelection = Field(default_factory=OrganisationUnitSelection)

    _normalize_identifier_base = field_validator("identifier_system_base")(strip_trailing_slash)

    @field_validator("locales")
    @classmethod
    def _normalize_locales(cls, value: list[str]) -> list[str]:
        """Accept BCP-47 or DHIS2-style tags and hold them in the BCP-47 form the emitters compare against."""
        return [normalize_locale(locale) for locale in value]


class FhirProjectConfig(BaseModel):
    """The full parsed `fhir.toml` document."""

    profile: str | None = None
    ig: IgConfig
    generate: GenerateConfig = Field(default_factory=GenerateConfig)


class FhirProject(BaseModel):
    """A discovered FHIR IG project: parsed config plus where it lives on disk."""

    model_config = ConfigDict(frozen=True)

    config: FhirProjectConfig
    config_path: Path

    @property
    def project_root(self) -> Path:
        """Directory containing `fhir.toml`."""
        return self.config_path.parent

    @property
    def ig_directory(self) -> Path:
        """The SUSHI IG directory (`<project_root>/ig`)."""
        return self.project_root / "ig"

    @property
    def fsh_directory(self) -> Path:
        """The FSH source directory (`<project_root>/ig/input/fsh`)."""
        return self.ig_directory / "input" / "fsh"


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
