"""Option-set schemas: the emitter projections plus the `[generate.option_sets]` selection."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.i18n import TranslationIn


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
    translations: list[TranslationIn] = Field(default_factory=list)


class OptionSetIn(BaseModel):
    """The option-set projection consumed by the emitter, options included."""

    model_config = ConfigDict(frozen=True)

    uid: str
    code: str | None = None
    name: str
    description: str | None = None
    options: list[OptionIn] = Field(default_factory=list)
    translations: list[TranslationIn] = Field(default_factory=list)


class OptionSetIdentity(BaseModel):
    """One option set's emitted slug plus the FSH name and artifact ids derived from it.

    The narrative pages link an option set to its compiled `CodeSystem-<id>.html`, so the
    slug assignment - truncation, collision suffixes, and the id stem the naming tokens
    build - is computed once here and read by both the emitter and the pages.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    slug: str
    fsh_name: str
    code_system_id: str
    value_set_id: str


class OptionSetIdentityPlan(BaseModel):
    """Every option set's identity in emission order, with the notes the slug assignment raised."""

    identities: list[OptionSetIdentity] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
