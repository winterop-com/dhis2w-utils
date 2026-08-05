"""FHIR R4 schemas for the resources this package emits: Organization and Location, plus their elements.

The models mirror the JSON SUSHI produces for the generated implementation guide, so every
model round-trips: `Model.model_validate(payload).model_dump_json(exclude_none=True, by_alias=True)`
reproduces the input document key for key. The primitive-extension key `_name` is not a legal
Pydantic field name, so it is carried by `name_element`: validation accepts `_name` or the field
name, and serialisation under `by_alias=True` writes `_name` back.
"""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

#: The standard R4 extension carrying the GeoJSON boundary of a Location.
BOUNDARY_EXTENSION_URL = "http://hl7.org/fhir/StructureDefinition/location-boundary-geojson"


class FhirElement(BaseModel):
    """Base for every FHIR element and resource here: frozen, alias-aware, and closed to unknown keys."""

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="forbid")


class Meta(FhirElement):
    """`Resource.meta` - the profiles a generated instance claims conformance to."""

    profile: list[str] | None = None


class Identifier(FhirElement):
    """A business identifier: the DHIS2 UID or code under its identifier system."""

    system: str | None = None
    value: str | None = None


class Coding(FhirElement):
    """One code drawn from a code system, with the display the system gives it."""

    system: str | None = None
    code: str | None = None
    display: str | None = None


class CodeableConcept(FhirElement):
    """A concept expressed as one or more codings, optionally with free text."""

    coding: list[Coding] | None = None
    text: str | None = None


class Reference(FhirElement):
    """A literal reference to another resource, such as `Organization/mOsABqg3Cqw`."""

    reference: str | None = None
    display: str | None = None


class ContactPoint(FhirElement):
    """A telecom contact point - the phone number or email address of an organisation unit."""

    system: Literal["phone", "fax", "email", "pager", "url", "sms", "other"] | None = None
    value: str | None = None


class HumanName(FhirElement):
    """A person's name; the generated contacts carry the DHIS2 free text in `text`."""

    text: str | None = None


class Attachment(FhirElement):
    """Attached content - the base64 GeoJSON boundary a Location extension carries."""

    contentType: str | None = None
    data: str | None = None
    title: str | None = None
    size: int | None = None


class Extension(FhirElement):
    """One extension: either a nested set of extensions or a single `value[x]` choice."""

    url: str
    extension: list[Extension] | None = None
    valueCode: str | None = None
    valueString: str | None = None
    valueAttachment: Attachment | None = None


class NameElement(FhirElement):
    """The `_name` sibling of a `name` primitive, carrying the translation extensions DHIS2 supplies."""

    extension: list[Extension] | None = None


class OrganizationContact(FhirElement):
    """`Organization.contact` - a contact party for the organisation unit."""

    name: HumanName | None = None
    telecom: list[ContactPoint] | None = None


class LocationPosition(FhirElement):
    """`Location.position` - the WGS84 point of an organisation unit."""

    longitude: float | None = None
    latitude: float | None = None


class Organization(FhirElement):
    """A FHIR R4 Organization as generated from one DHIS2 organisation unit."""

    resourceType: Literal["Organization"] = "Organization"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    name: str | None = None
    name_element: NameElement | None = Field(
        default=None, validation_alias=AliasChoices("_name", "name_element"), serialization_alias="_name"
    )
    alias: list[str] | None = None
    type: list[CodeableConcept] | None = None
    partOf: Reference | None = None
    telecom: list[ContactPoint] | None = None
    contact: list[OrganizationContact] | None = None
    active: bool | None = None


class Location(FhirElement):
    """A FHIR R4 Location as generated from the physical place of one DHIS2 organisation unit."""

    resourceType: Literal["Location"] = "Location"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    name: str | None = None
    name_element: NameElement | None = Field(
        default=None, validation_alias=AliasChoices("_name", "name_element"), serialization_alias="_name"
    )
    description: str | None = None
    status: Literal["active", "suspended", "inactive"] | None = None
    position: LocationPosition | None = None
    extension: list[Extension] | None = None
    managingOrganization: Reference | None = None
    partOf: Reference | None = None
