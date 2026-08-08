"""Category schemas: the emitter projection plus the `[generate.categories]` selection."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.notes import GenerateNote
from dhis2w_fhir.resources.option_sets.schemas import ConceptSourceIn


class CategorySelection(BaseModel):
    """Which DHIS2 categories to generate - the `[generate.categories]` table of `fhir.toml`.

    UIDs only: names are not unique in DHIS2. An empty (or absent) list means all categories.
    """

    include_ids: list[str] = Field(default_factory=list)


class CategoryIn(ConceptSourceIn):
    """The category projection consumed by the emitter, its category options included.

    A category is one axis of a DHIS2 disaggregation and its category options are the values
    along that axis, so the options land as the concepts of the emitted CodeSystem exactly as
    an option set's options do. DHIS2 holds `categoryOptions` as an ordered list rather than a
    sorted set, so the order the instance answers with is the DHIS2 sort order: the fetch
    carries each option's index across as its `sort_order`.
    """

    source_label: ClassVar[str] = "category"
    member_label: ClassVar[str] = "category option"


class CategoryIdentity(BaseModel):
    """One category's emitted slug plus the FSH name and artifact ids derived from it.

    The slug assignment - truncation, collision suffixes, and the id stem the naming tokens
    build - is computed once by `category_identities`, so every artifact naming a category
    reads the same names. All three artifacts of one category - the CodeSystem, the ValueSet,
    and the ConceptMap taking their concept codes back to DHIS2 - ride the one slug.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    slug: str
    fsh_name: str
    code_system_id: str
    value_set_id: str
    concept_map_id: str

    @property
    def code_system_name(self) -> str:
        """FSH name of the emitted CodeSystem (e.g. `D2CAT_Sex_CS`)."""
        return f"{self.fsh_name}_CS"

    @property
    def value_set_name(self) -> str:
        """FSH name of the emitted ValueSet (e.g. `D2CAT_Sex_VS`)."""
        return f"{self.fsh_name}_VS"

    @property
    def concept_map_name(self) -> str:
        """FSH name of the emitted ConceptMap (e.g. `D2CAT_Sex_CM`)."""
        return f"{self.fsh_name}_CM"


class CategoryIdentityPlan(BaseModel):
    """Every category's identity in emission order, with the notes the slug assignment raised."""

    identities: list[CategoryIdentity] = Field(default_factory=list)
    notes: list[GenerateNote] = Field(default_factory=list)
