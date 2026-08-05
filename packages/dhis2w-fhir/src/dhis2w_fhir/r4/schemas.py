"""FHIR R4 schemas for the resources this package emits - Organization, Location, CodeSystem, ValueSet - plus elements.

The models mirror the JSON SUSHI produces for the generated implementation guide, so every
model round-trips: `Model.model_validate(payload).model_dump_json(exclude_none=True, by_alias=True)`
reproduces the input document key for key. The primitive-extension keys `_name` and `_title` are not
legal Pydantic field names, so they are carried by `name_element` and `title_element`: validation
accepts either the underscore key or the field name, and serialisation under `by_alias=True` writes
the underscore key back.
"""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

#: The standard R4 extension carrying the GeoJSON boundary of a Location.
BOUNDARY_EXTENSION_URL = "http://hl7.org/fhir/StructureDefinition/location-boundary-geojson"


class FhirBase(BaseModel):
    """Pydantic carrier for every schema here - frozen, alias-aware, closed to unknown keys. Not a FHIR type."""

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="forbid")


class Element(FhirBase):
    """`Element` - the R4 root for datatypes, and the `_x` sibling a primitive's extensions hang from."""

    extension: list[Extension] | None = None


class BackboneElement(Element):
    """`BackboneElement` - an element defined inside a resource rather than as a reusable datatype."""


class Resource(FhirBase):
    """`Resource` - the R4 root for resources, a sibling of `Element` rather than a subtype of it."""


class DomainResource(Resource):
    """`DomainResource` - a resource carrying narrative and extensions; every resource emitted here is one."""


class Meta(Element):
    """`Resource.meta` - the profiles a generated instance claims conformance to."""

    profile: list[str] | None = None


class Identifier(Element):
    """A business identifier: the DHIS2 UID or code under its identifier system."""

    system: str | None = None
    value: str | None = None


class Coding(Element):
    """One code drawn from a code system, with the display the system gives it."""

    system: str | None = None
    code: str | None = None
    display: str | None = None


class CodeableConcept(Element):
    """A concept expressed as one or more codings, optionally with free text."""

    coding: list[Coding] | None = None
    text: str | None = None


class Reference(Element):
    """A literal reference to another resource, such as `Organization/mOsABqg3Cqw`."""

    reference: str | None = None
    display: str | None = None


class ContactPoint(Element):
    """A telecom contact point - the phone number or email address of an organisation unit."""

    system: Literal["phone", "fax", "email", "pager", "url", "sms", "other"] | None = None
    value: str | None = None


class HumanName(Element):
    """A person's name; the generated contacts carry the DHIS2 free text in `text`."""

    text: str | None = None


class Attachment(Element):
    """Attached content - the base64 GeoJSON boundary a Location extension carries."""

    contentType: str | None = None
    data: str | None = None
    title: str | None = None
    size: int | None = None


class Extension(Element):
    """One extension: either a nested set of extensions or a single `value[x]` choice."""

    url: str
    extension: list[Extension] | None = None
    valueCode: str | None = None
    valueString: str | None = None
    valueAttachment: Attachment | None = None


class OrganizationContact(BackboneElement):
    """`Organization.contact` - a contact party for the organisation unit."""

    name: HumanName | None = None
    telecom: list[ContactPoint] | None = None


class LocationPosition(BackboneElement):
    """`Location.position` - the WGS84 point of an organisation unit."""

    longitude: float | None = None
    latitude: float | None = None


class CodeSystemProperty(BackboneElement):
    """`CodeSystem.property` - the declaration of a property the concepts in the code system may carry."""

    code: str | None = None
    uri: str | None = None
    description: str | None = None
    type: Literal["code", "Coding", "string", "integer", "boolean", "dateTime", "decimal"] | None = None


class CodeSystemConceptProperty(BackboneElement):
    """`CodeSystem.concept.property` - one declared property carried by a single concept."""

    code: str | None = None
    valueCode: str | None = None
    valueString: str | None = None


class CodeSystemConceptDesignation(BackboneElement):
    """`CodeSystem.concept.designation` - the translation of a concept display into one locale."""

    language: str | None = None
    value: str | None = None


class CodeSystemConcept(BackboneElement):
    """`CodeSystem.concept` - one DHIS2 option, keyed by its option UID."""

    code: str | None = None
    display: str | None = None
    property: list[CodeSystemConceptProperty] | None = None
    designation: list[CodeSystemConceptDesignation] | None = None


class ValueSetInclude(BackboneElement):
    """`ValueSet.compose.include` - one code system the value set draws its codes from."""

    system: str | None = None


class ValueSetCompose(BackboneElement):
    """`ValueSet.compose` - the content logic that builds the expansion of the value set."""

    include: list[ValueSetInclude] | None = None


class Organization(DomainResource):
    """A FHIR R4 Organization as generated from one DHIS2 organisation unit."""

    resourceType: Literal["Organization"] = "Organization"
    id: str | None = None
    meta: Meta | None = None
    extension: list[Extension] | None = None
    identifier: list[Identifier] | None = None
    name: str | None = None
    name_element: Element | None = Field(
        default=None, validation_alias=AliasChoices("_name", "name_element"), serialization_alias="_name"
    )
    alias: list[str] | None = None
    type: list[CodeableConcept] | None = None
    partOf: Reference | None = None
    telecom: list[ContactPoint] | None = None
    contact: list[OrganizationContact] | None = None
    active: bool | None = None


class Location(DomainResource):
    """A FHIR R4 Location as generated from the physical place of one DHIS2 organisation unit."""

    resourceType: Literal["Location"] = "Location"
    id: str | None = None
    meta: Meta | None = None
    identifier: list[Identifier] | None = None
    name: str | None = None
    name_element: Element | None = Field(
        default=None, validation_alias=AliasChoices("_name", "name_element"), serialization_alias="_name"
    )
    description: str | None = None
    status: Literal["active", "suspended", "inactive"] | None = None
    position: LocationPosition | None = None
    extension: list[Extension] | None = None
    managingOrganization: Reference | None = None
    partOf: Reference | None = None


class CodeSystem(DomainResource):
    """A FHIR R4 CodeSystem as generated from one DHIS2 option set, one concept per option."""

    resourceType: Literal["CodeSystem"] = "CodeSystem"
    id: str | None = None
    extension: list[Extension] | None = None
    url: str | None = None
    identifier: list[Identifier] | None = None
    name: str | None = None
    title: str | None = None
    title_element: Element | None = Field(
        default=None, validation_alias=AliasChoices("_title", "title_element"), serialization_alias="_title"
    )
    description: str | None = None
    status: Literal["draft", "active", "retired", "unknown"] | None = None
    experimental: bool | None = None
    caseSensitive: bool | None = None
    content: Literal["not-present", "example", "fragment", "complete", "supplement"] | None = None
    count: int | None = None
    valueSet: str | None = None
    property: list[CodeSystemProperty] | None = None
    concept: list[CodeSystemConcept] | None = None


class ValueSet(DomainResource):
    """A FHIR R4 ValueSet as generated from one DHIS2 option set, composing the whole matching CodeSystem."""

    resourceType: Literal["ValueSet"] = "ValueSet"
    id: str | None = None
    extension: list[Extension] | None = None
    url: str | None = None
    identifier: list[Identifier] | None = None
    name: str | None = None
    title: str | None = None
    title_element: Element | None = Field(
        default=None, validation_alias=AliasChoices("_title", "title_element"), serialization_alias="_title"
    )
    description: str | None = None
    status: Literal["draft", "active", "retired", "unknown"] | None = None
    experimental: bool | None = None
    compose: ValueSetCompose | None = None
