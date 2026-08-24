"""Organisation-unit schemas: the emitter projection, its geometry, and the selection table."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dhis2w_fhir.attributes import AttributeValueIn
from dhis2w_fhir.coded import CodedProjectionIn
from dhis2w_fhir.foundation.schemas import TerminologyPairProfile, TerminologyPropertyDeclaration
from dhis2w_fhir.i18n import TranslationIn

#: The prose the org-unit-level CodeSystem/ValueSet pair publishes under - the levels the selection reaches.
ORGANISATION_UNIT_LEVEL_TERMINOLOGY = TerminologyPairProfile(
    title="DHIS2 organisation unit levels",
    description="Hierarchy levels of the DHIS2 organisation unit tree.",
)

#: The prose the whole-selection CodeSystem/ValueSet pair publishes under. The ValueSet names the
#: selection it draws, where the CodeSystem names what a concept code means.
ORGANISATION_UNIT_TERMINOLOGY = TerminologyPairProfile(
    title="DHIS2 organisation units",
    description="DHIS2 organisation units. Concept codes are DHIS2 organisation unit UIDs.",
    value_set_description="All DHIS2 organisation units in the generated selection.",
)

#: The concept properties the whole-selection CodeSystem declares, in the order it declares them.
ORGANISATION_UNIT_CONCEPT_PROPERTIES: tuple[TerminologyPropertyDeclaration, ...] = (
    TerminologyPropertyDeclaration(
        code="level", description="DHIS2 organisation unit hierarchy level.", type="integer"
    ),
    TerminologyPropertyDeclaration(code="parent", description="Parent organisation unit UID.", type="code"),
    TerminologyPropertyDeclaration(code="dhis2-code", description="DHIS2 organisation unit code.", type="string"),
)


class OrganisationUnitSelection(BaseModel):
    """Which DHIS2 organisation units to generate - the `[generate.organisation_units]` table of `fhir.toml`."""

    model_config = ConfigDict(extra="forbid")

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


class GeoPoint(BaseModel):
    """A WGS84 position - the Point coordinates or polygon centroid that `Location.position` renders."""

    model_config = ConfigDict(frozen=True)

    longitude: float
    latitude: float


class OrganisationUnitIn(CodedProjectionIn):
    """The organisation-unit projection consumed by the emitter.

    `latitude`/`longitude` hold the Point coordinates, or the area-weighted centroid for
    Polygon/MultiPolygon geometry; GeoJSON stores `[longitude, latitude]`, so the mapper
    must swap. `boundary_geojson` carries the compact GeoJSON Feature wrapping the geometry
    of every unit whose geometry parses, Points and non-positional types included.
    `closed` is true for a unit whose DHIS2 `closedDate` has passed. `description` is the
    DHIS2 free text, which the narrative pages carry into the unit's intro page.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    short_name: str | None = None
    description: str | None = None
    level: int
    path: str
    parent_uid: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    boundary_geojson: str | None = None
    contact_person: str | None = None
    email: str | None = None
    phone_number: str | None = None
    closed: bool = False
    translations: list[TranslationIn] = Field(default_factory=list)
    attribute_values: list[AttributeValueIn] = Field(default_factory=list)


def ordered_organisation_units(organisation_units: list[OrganisationUnitIn]) -> list[OrganisationUnitIn]:
    """The selection in terminology emission order - down the DHIS2 hierarchy path, then by UID."""
    return sorted(organisation_units, key=lambda item: (item.path, item.uid))
