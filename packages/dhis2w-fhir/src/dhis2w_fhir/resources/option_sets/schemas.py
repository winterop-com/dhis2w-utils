"""Option-set schemas: the emitter projections plus the `[generate.option_sets]` selection."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OptionSetSelection(BaseModel):
    """Which DHIS2 option sets to generate - the `[generate.option_sets]` table of `fhir.toml`.

    UIDs only: names are not unique in DHIS2. An empty (or absent) list means all option sets.
    """

    include_ids: list[str] = Field(default_factory=list)


class OptionIn(BaseModel):
    """The option projection consumed by the emitter."""

    model_config = ConfigDict(frozen=True)

    uid: str
    code: str | None = None
    name: str
    sort_order: int | None = None


class OptionSetIn(BaseModel):
    """The option-set projection consumed by the emitter, options included."""

    model_config = ConfigDict(frozen=True)

    uid: str
    code: str | None = None
    name: str
    options: list[OptionIn] = Field(default_factory=list)
