"""Pydantic models for FHIR IG generation: fhir.toml config, inputs, FSH artifacts, and reports."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _strip_trailing_slash(value: str) -> str:
    """Drop trailing slashes - SUSHI and the IG publisher append path segments to the canonical."""
    return value.rstrip("/")


class IgConfig(BaseModel):
    """SUSHI IG identity - the `[ig]` table of `fhir.toml`."""

    id: str
    canonical: str
    name: str
    title: str
    publisher: str

    _normalize_canonical = field_validator("canonical")(_strip_trailing_slash)


class OptionSetSelection(BaseModel):
    """Which DHIS2 option sets to generate - the `[generate.option_sets]` table of `fhir.toml`."""

    include_names: list[str] = Field(default_factory=list)
    include_ids: list[str] = Field(default_factory=list)


class OrgUnitSelection(BaseModel):
    """Which DHIS2 organisation units to generate - the `[generate.org_units]` table of `fhir.toml`."""

    root: str | None = None
    max_level: int | None = None
    terminology: bool = False

    @field_validator("root", mode="before")
    @classmethod
    def _empty_root_is_none(cls, value: object) -> object:
        """Treat the scaffolded `root = ""` placeholder as unset."""
        return None if value == "" else value

    @field_validator("max_level", mode="before")
    @classmethod
    def _zero_level_is_none(cls, value: object) -> object:
        """Treat the scaffolded `max_level = 0` placeholder as unset."""
        return None if value == 0 else value


class GenerateConfig(BaseModel):
    """Generation behaviour - the `[generate]` table of `fhir.toml`."""

    identifier_system_base: str = "http://dhis2.org/fhir"
    concept_code_source: Literal["uid", "code"] = "uid"
    option_sets: OptionSetSelection = Field(default_factory=OptionSetSelection)
    org_units: OrgUnitSelection = Field(default_factory=OrgUnitSelection)

    _normalize_identifier_base = field_validator("identifier_system_base")(_strip_trailing_slash)


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


class InitOptions(BaseModel):
    """Parameters for `d2w fhir init` scaffolding."""

    ig_id: str
    canonical: str
    name: str
    title: str
    publisher: str

    _normalize_canonical = field_validator("canonical")(_strip_trailing_slash)


class ScaffoldFile(BaseModel):
    """One file emitted by `d2w fhir init`: path relative to the project root plus its content."""

    model_config = ConfigDict(frozen=True)

    relative_path: str
    content: str


class ScaffoldReport(BaseModel):
    """Outcome of `d2w fhir init`."""

    directory: Path
    created_files: list[str] = Field(default_factory=list)
    skipped_files: list[str] = Field(default_factory=list)


class OptionInput(BaseModel):
    """A DHIS2 option, reduced to the fields terminology emission needs."""

    model_config = ConfigDict(frozen=True)

    uid: str
    code: str | None = None
    name: str
    sort_order: int | None = None


class OptionSetInput(BaseModel):
    """A DHIS2 option set with its options, reduced to the fields terminology emission needs."""

    model_config = ConfigDict(frozen=True)

    uid: str
    code: str | None = None
    name: str
    options: list[OptionInput] = Field(default_factory=list)


class OrgUnitInput(BaseModel):
    """A DHIS2 organisation unit, reduced to the fields instance emission needs.

    `latitude`/`longitude` are set only when the source geometry is a GeoJSON Point;
    GeoJSON stores coordinates as `[longitude, latitude]`, so the mapper must swap.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    short_name: str | None = None
    code: str | None = None
    level: int
    path: str
    parent_uid: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    contact_person: str | None = None
    email: str | None = None
    phone_number: str | None = None


class FshArtifact(BaseModel):
    """One generated FSH file, path relative to `ig/input/fsh/`."""

    model_config = ConfigDict(frozen=True)

    relative_path: str
    kind: Literal["terminology-pair", "profile", "instances"]
    fsh_name: str
    content: str


class FshBuild(BaseModel):
    """Result of a pure FSH build step: artifacts plus human-facing notes (skips, fallbacks)."""

    artifacts: list[FshArtifact] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class GenerateReport(BaseModel):
    """Outcome of one `d2w fhir generate` target."""

    project_root: Path
    target_directory: str
    deleted_files: list[str] = Field(default_factory=list)
    written_files: list[str] = Field(default_factory=list)
    option_set_count: int = 0
    org_unit_count: int = 0
    location_count: int = 0
    notes: list[str] = Field(default_factory=list)


class GenerateAllReport(BaseModel):
    """Outcome of `d2w fhir generate all`."""

    option_sets: GenerateReport
    org_units: GenerateReport
