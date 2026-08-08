"""FHIR R4 schemas for the resources this package emits and serves, plus the elements they are built from.

The models mirror the JSON SUSHI produces for the generated implementation guide, so every
model round-trips: `Model.model_validate(payload).model_dump_json(exclude_none=True, by_alias=True)`
reproduces the input document key for key. The primitive-extension keys `_name` and `_title` are not
legal Pydantic field names, so they are carried by `name_element` and `title_element`: validation
accepts either the underscore key or the field name, and serialisation under `by_alias=True` writes
the underscore key back.

Every optional field defaults to `None`, never to an empty list: FHIR has no empty collection, so a
field either carries values or is absent from the document, and `exclude_none=True` is what makes
that true of the emitted JSON. `extra="forbid"` is the other half of the contract - a key the model
does not name is a typo or an element this package does not serve, and either way it is an error
rather than something to carry silently. `JsonResource` is the single exception: it is the open
carrier for a wire document that is passed through verbatim.
"""

from __future__ import annotations

import json
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
    """A reference to another resource - a literal `Organization/mOsABqg3Cqw`, or a business identifier."""

    reference: str | None = None
    type: str | None = None
    identifier: Identifier | None = None
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


class Period(Element):
    """A time range with inclusive bounds - the reporting period a captured data value set covers."""

    start: str | None = None
    end: str | None = None


class Narrative(Element):
    """`DomainResource.text` - the human-readable XHTML rendering of a resource."""

    status: Literal["generated", "extensions", "additional", "empty"] | None = None
    div: str | None = None


class Extension(Element):
    """One extension: either a nested set of extensions or a single `value[x]` choice.

    Only the choices this package emits or reads are modelled. `valueDecimal` is typed as
    `int | float` rather than `float` so a whole number survives the round trip: `float`
    would coerce the wire value `2896` to `2896.0` and change the document.
    """

    url: str
    extension: list[Extension] | None = None
    valueCode: str | None = None
    valueString: str | None = None
    valueInteger: int | None = None
    valueDecimal: int | float | None = None
    valueAttachment: Attachment | None = None
    valueCodeableConcept: CodeableConcept | None = None
    valueIdentifier: Identifier | None = None
    valueReference: Reference | None = None
    valuePeriod: Period | None = None


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


class QuestionnaireItem(BackboneElement):
    """`Questionnaire.item` - one question, or a group nesting the questions of a section or a disaggregation."""

    linkId: str | None = None
    code: list[Coding] | None = None
    text: str | None = None
    type: (
        Literal[
            "group",
            "display",
            "boolean",
            "decimal",
            "integer",
            "date",
            "dateTime",
            "time",
            "string",
            "text",
            "url",
            "choice",
            "open-choice",
            "attachment",
            "reference",
            "quantity",
        ]
        | None
    ) = None
    answerValueSet: str | None = None
    required: bool | None = None
    repeats: bool | None = None
    extension: list[Extension] | None = None
    item: list[QuestionnaireItem] | None = None


class Questionnaire(DomainResource):
    """A FHIR R4 Questionnaire as generated from one DHIS2 data set, event program, or program stage."""

    resourceType: Literal["Questionnaire"] = "Questionnaire"
    id: str | None = None
    url: str | None = None
    title: str | None = None
    description: str | None = None
    extension: list[Extension] | None = None
    identifier: list[Identifier] | None = None
    name: str | None = None
    status: Literal["draft", "active", "retired", "unknown"] | None = None
    experimental: bool | None = None
    subjectType: list[str] | None = None
    code: list[Coding] | None = None
    item: list[QuestionnaireItem] | None = None


class QuestionnaireResponseAnswer(BackboneElement):
    """`QuestionnaireResponse.item.answer` - one captured value on the `value[x]` element its type asks for."""

    valueBoolean: bool | None = None
    valueDecimal: int | float | None = None
    valueInteger: int | None = None
    valueDate: str | None = None
    valueDateTime: str | None = None
    valueTime: str | None = None
    valueString: str | None = None
    valueUri: str | None = None
    valueAttachment: Attachment | None = None
    valueCoding: Coding | None = None
    valueReference: Reference | None = None
    item: list[QuestionnaireResponseItem] | None = None


class QuestionnaireResponseItem(BackboneElement):
    """`QuestionnaireResponse.item` - one answered question, or a group mirroring the questionnaire's tree."""

    linkId: str | None = None
    definition: str | None = None
    text: str | None = None
    answer: list[QuestionnaireResponseAnswer] | None = None
    item: list[QuestionnaireResponseItem] | None = None


class QuestionnaireResponse(DomainResource):
    """A FHIR R4 QuestionnaireResponse - one captured DHIS2 data value set, event, or tracker event."""

    resourceType: Literal["QuestionnaireResponse"] = "QuestionnaireResponse"
    id: str | None = None
    meta: Meta | None = None
    language: str | None = None
    text: Narrative | None = None
    extension: list[Extension] | None = None
    identifier: Identifier | None = None
    basedOn: list[Reference] | None = None
    partOf: list[Reference] | None = None
    questionnaire: str | None = None
    status: Literal["in-progress", "completed", "amended", "entered-in-error", "stopped"] | None = None
    subject: Reference | None = None
    encounter: Reference | None = None
    authored: str | None = None
    author: Reference | None = None
    source: Reference | None = None
    item: list[QuestionnaireResponseItem] | None = None


class OperationOutcomeIssue(BackboneElement):
    """`OperationOutcome.issue` - one thing that went wrong, at the severity and issue type R4 names for it."""

    severity: Literal["fatal", "error", "warning", "information"] | None = None
    code: (
        Literal[
            "invalid",
            "structure",
            "required",
            "value",
            "invariant",
            "security",
            "login",
            "unknown",
            "expired",
            "forbidden",
            "suppressed",
            "processing",
            "not-supported",
            "duplicate",
            "multiple-matches",
            "not-found",
            "deleted",
            "too-long",
            "code-invalid",
            "extension",
            "too-costly",
            "business-rule",
            "conflict",
            "transient",
            "lock-error",
            "no-store",
            "exception",
            "timeout",
            "incomplete",
            "throttled",
            "informational",
        ]
        | None
    ) = None
    details: CodeableConcept | None = None
    diagnostics: str | None = None
    expression: list[str] | None = None


class OperationOutcome(DomainResource):
    """A FHIR R4 OperationOutcome - the error body every failed interaction answers with."""

    resourceType: Literal["OperationOutcome"] = "OperationOutcome"
    id: str | None = None
    issue: list[OperationOutcomeIssue] | None = None


class JsonResource(FhirBase):
    """The one open model here: a wire document carried verbatim, keyed only by its `resourceType`.

    A Bundle entry and a compiled-store body hold whatever resource the document happens to be, so
    modelling their contents would mean naming every resource type in advance. This is the typed
    wrapper the house style asks for over a genuinely dynamic wire shape: `extra="allow"` keeps
    every key the document carried, and `resourceType` is the one fact that is always there.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="allow")

    resourceType: str


def json_resource(resource: FhirBase) -> JsonResource:
    """Carry a typed resource as a `JsonResource`, exactly as the emitter would have written it."""
    return JsonResource.model_validate(json.loads(resource.model_dump_json(exclude_none=True, by_alias=True)))


class BundleLink(BackboneElement):
    """`Bundle.link` - one relation of a search result set, such as `self`."""

    relation: str | None = None
    url: str | None = None


class BundleEntrySearch(BackboneElement):
    """`Bundle.entry.search` - why an entry is in a search result set."""

    mode: Literal["match", "include", "outcome"] | None = None


class BundleEntry(BackboneElement):
    """`Bundle.entry` - one resource in a bundle, at the URL it is served from."""

    fullUrl: str | None = None
    resource: JsonResource | None = None
    search: BundleEntrySearch | None = None


class Bundle(Resource):
    """A FHIR R4 Bundle - the container a search answers with."""

    resourceType: Literal["Bundle"] = "Bundle"
    id: str | None = None
    type: (
        Literal[
            "searchset",
            "collection",
            "document",
            "message",
            "history",
            "transaction",
            "transaction-response",
            "batch",
            "batch-response",
        ]
        | None
    ) = None
    total: int | None = None
    link: list[BundleLink] | None = None
    entry: list[BundleEntry] | None = None


class CapabilityStatementSoftware(BackboneElement):
    """`CapabilityStatement.software` - the software the described endpoint runs."""

    name: str | None = None
    version: str | None = None


class CapabilityStatementImplementation(BackboneElement):
    """`CapabilityStatement.implementation` - the specific installation the statement describes."""

    description: str | None = None
    url: str | None = None


class CapabilityStatementInteraction(BackboneElement):
    """`CapabilityStatement.rest.resource.interaction` - one RESTful interaction supported on a resource type."""

    code: (
        Literal[
            "read", "vread", "update", "patch", "delete", "history-instance", "history-type", "create", "search-type"
        ]
        | None
    ) = None
    documentation: str | None = None


class CapabilityStatementSearchParam(BackboneElement):
    """`CapabilityStatement.rest.resource.searchParam` - one search parameter supported on a resource type."""

    name: str | None = None
    definition: str | None = None
    type: (
        Literal["number", "date", "string", "token", "reference", "composite", "quantity", "uri", "special"] | None
    ) = None
    documentation: str | None = None


class CapabilityStatementResource(BackboneElement):
    """`CapabilityStatement.rest.resource` - one resource type the endpoint serves, and how."""

    type: str | None = None
    profile: str | None = None
    supportedProfile: list[str] | None = None
    documentation: str | None = None
    interaction: list[CapabilityStatementInteraction] | None = None
    searchParam: list[CapabilityStatementSearchParam] | None = None


class CapabilityStatementRest(BackboneElement):
    """`CapabilityStatement.rest` - the RESTful behaviour of one end of the conversation."""

    mode: Literal["client", "server"] | None = None
    documentation: str | None = None
    resource: list[CapabilityStatementResource] | None = None


class CapabilityStatement(DomainResource):
    """A FHIR R4 CapabilityStatement - what a DHIS2 capture server accepts and serves."""

    resourceType: Literal["CapabilityStatement"] = "CapabilityStatement"
    id: str | None = None
    url: str | None = None
    name: str | None = None
    title: str | None = None
    status: Literal["draft", "active", "retired", "unknown"] | None = None
    experimental: bool | None = None
    date: str | None = None
    description: str | None = None
    kind: Literal["instance", "capability", "requirements"] | None = None
    instantiates: list[str] | None = None
    software: CapabilityStatementSoftware | None = None
    implementation: CapabilityStatementImplementation | None = None
    fhirVersion: str | None = None
    format: list[str] | None = None
    rest: list[CapabilityStatementRest] | None = None
