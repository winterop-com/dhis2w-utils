"""Scaffold schemas: the `d2w fhir init` inputs and the files it writes."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dhis2w_fhir.names import strip_trailing_slash


class InitOptions(BaseModel):
    """Parameters for `d2w fhir init` scaffolding."""

    ig_id: str
    canonical: str
    name: str
    title: str
    publisher: str
    publisher_url: str | None = None

    _normalize_canonical = field_validator("canonical")(strip_trailing_slash)


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
