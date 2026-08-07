"""Foundation schemas: the derived FSH names and ids for the shared aliases and D2Period artifacts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.names import join_id_tokens, page_text

if TYPE_CHECKING:
    from dhis2w_fhir.config import NamingConfig

_DEFINITION_FALLBACK_PREFIX = "D2"


class IdentifierSystemSubject(BaseModel):
    """One DHIS2 object kind whose UID, and optionally whose code, gets an identifier system."""

    model_config = ConfigDict(frozen=True)

    segment: str
    token: str
    label: str
    has_code: bool = True
    """Whether the DHIS2 object carries a `code` attribute; a subject without one declares only the UID system."""


#: The object kinds that carry a DHIS2 identifier system. A metadata object yields both a UID system
#: and a code system; a data object (a tracked entity, an enrollment) carries no code and declares the
#: UID system alone.
IDENTIFIER_SYSTEM_SUBJECTS = (
    IdentifierSystemSubject(segment="org-unit", token="OrgUnit", label="organisation unit"),
    IdentifierSystemSubject(segment="option-set", token="OptionSet", label="option set"),
    IdentifierSystemSubject(segment="category", token="Category", label="category"),
    IdentifierSystemSubject(segment="data-set", token="DataSet", label="data set"),
    IdentifierSystemSubject(segment="program", token="Program", label="program"),
    IdentifierSystemSubject(segment="data-element", token="DataElement", label="data element"),
    IdentifierSystemSubject(
        segment="category-option-combo", token="CategoryOptionCombo", label="category option combo"
    ),
    IdentifierSystemSubject(segment="program-stage", token="ProgramStage", label="program stage"),
    IdentifierSystemSubject(segment="tracked-entity", token="TrackedEntity", label="tracked entity", has_code=False),
    IdentifierSystemSubject(
        segment="tracker-enrollment", token="TrackerEnrollment", label="tracker enrollment", has_code=False
    ),
)


class FormTypeDefinition(BaseModel):
    """One DHIS2 form kind as a concept of the D2FormType terminology."""

    model_config = ConfigDict(frozen=True)

    code: str
    display: str


#: Every DHIS2 form kind a Questionnaire can be generated from. `tracker` and `tracker-event`
#: are declared ahead of their generators so the terminology is stable once those land.
FORM_TYPE_DEFINITIONS: tuple[FormTypeDefinition, ...] = (
    FormTypeDefinition(code="aggregate", display="Aggregate data set form"),
    FormTypeDefinition(code="event", display="Event program form"),
    FormTypeDefinition(code="tracker", display="Tracker registration form"),
    FormTypeDefinition(code="tracker-event", display="Tracker program stage form"),
)


class ResponseProfileDeclaration(BaseModel):
    """One QuestionnaireResponse profile as the responses template renders it.

    `period_required` marks the aggregate contract, whose response reports for a DHIS2
    reporting period; `authored_required` marks the contracts whose response reports the moment
    the data was captured; `tracker_context_required` marks the tracker-event contract, whose
    response carries the tracker enrollment it belongs to, the organisation unit the event was
    captured at, and a Patient subject identified by tracked-entity UID. The flags are what the
    shared template branches on.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    profile_id: str
    form_type_code: str
    title: str
    description: str
    period_required: bool = False
    authored_required: bool = False
    tracker_context_required: bool = False

    @property
    def title_literal(self) -> str:
        """The title as the page-facing FSH `Title:` literal, markup characters HTML-escaped."""
        return page_text(self.title)

    @property
    def description_literal(self) -> str:
        """The description as the page-facing FSH `Description:` literal, markup characters HTML-escaped."""
        return page_text(self.description)


class NamingSystemDeclaration(BaseModel):
    """One DHIS2 identifier system as the NamingSystem instance the foundation template renders."""

    model_config = ConfigDict(frozen=True)

    name: str
    title: str
    description: str
    url: str

    @property
    def title_literal(self) -> str:
        """The title as the page-facing FSH `Title:` literal, markup characters HTML-escaped."""
        return page_text(self.title)

    @property
    def description_literal(self) -> str:
        """The description as the page-facing FSH `Description:` literal, markup characters HTML-escaped."""
        return page_text(self.description)


class FoundationNaming(BaseModel):
    """Derived FSH names and ids for the foundation artifacts under the configurable prefix token.

    The foundation artifacts take the `[generate.naming]` prefix and no token of their own.
    An empty prefix falls back to `D2` for the same reason the profiles do: `Period` is a core
    FHIR datatype name, and an Extension cannot shadow it.
    """

    model_config = ConfigDict(frozen=True)

    prefix: str

    @classmethod
    def from_naming(cls, naming: NamingConfig) -> FoundationNaming:
        """Project the `[generate.naming]` table onto the token the foundation artifacts use."""
        return cls(prefix=naming.prefix)

    @property
    def definition_prefix(self) -> str:
        """Token for definitional names - never empty, a definition cannot shadow a core FHIR name."""
        return self.prefix or _DEFINITION_FALLBACK_PREFIX

    @property
    def period_extension(self) -> str:
        """FSH name of the reporting-period Extension (e.g. `D2Period`)."""
        return f"{self.definition_prefix}Period"

    @property
    def period_extension_id(self) -> str:
        """FHIR id of the reporting-period Extension (e.g. `d2-period`)."""
        return join_id_tokens(self.definition_prefix, "period")

    @property
    def period_type_code_system(self) -> str:
        """FSH name of the period-type CodeSystem (e.g. `D2PeriodType_CS`)."""
        return f"{self.definition_prefix}PeriodType_CS"

    @property
    def period_type_code_system_id(self) -> str:
        """FHIR id of the period-type CodeSystem (e.g. `d2-period-type-cs`)."""
        return join_id_tokens(self.definition_prefix, "period", "type", "cs")

    @property
    def period_type_value_set(self) -> str:
        """FSH name of the period-type ValueSet (e.g. `D2PeriodType_VS`)."""
        return f"{self.definition_prefix}PeriodType_VS"

    @property
    def period_type_value_set_id(self) -> str:
        """FHIR id of the period-type ValueSet (e.g. `d2-period-type-vs`)."""
        return join_id_tokens(self.definition_prefix, "period", "type", "vs")

    @property
    def form_type_extension(self) -> str:
        """FSH name of the form-type Extension (e.g. `D2FormType`)."""
        return f"{self.definition_prefix}FormType"

    @property
    def form_type_extension_id(self) -> str:
        """FHIR id of the form-type Extension (e.g. `d2-form-type`)."""
        return join_id_tokens(self.definition_prefix, "form", "type")

    @property
    def form_type_code_system(self) -> str:
        """FSH name of the form-type CodeSystem (e.g. `D2FormType_CS`)."""
        return f"{self.definition_prefix}FormType_CS"

    @property
    def form_type_code_system_id(self) -> str:
        """FHIR id of the form-type CodeSystem (e.g. `d2-form-type-cs`)."""
        return join_id_tokens(self.definition_prefix, "form", "type", "cs")

    @property
    def form_type_value_set(self) -> str:
        """FSH name of the form-type ValueSet (e.g. `D2FormType_VS`)."""
        return f"{self.definition_prefix}FormType_VS"

    @property
    def form_type_value_set_id(self) -> str:
        """FHIR id of the form-type ValueSet (e.g. `d2-form-type-vs`)."""
        return join_id_tokens(self.definition_prefix, "form", "type", "vs")

    @property
    def attribute_value_extension(self) -> str:
        """FSH name of the attribute-value Extension (e.g. `D2AttributeValue`)."""
        return f"{self.definition_prefix}AttributeValue"

    @property
    def attribute_value_extension_id(self) -> str:
        """FHIR id of the attribute-value Extension (e.g. `d2-attribute-value`)."""
        return join_id_tokens(self.definition_prefix, "attribute", "value")

    @property
    def organisation_unit_extension(self) -> str:
        """FSH name of the organisation-unit Extension (e.g. `D2OrganisationUnit`)."""
        return f"{self.definition_prefix}OrganisationUnit"

    @property
    def organisation_unit_extension_id(self) -> str:
        """FHIR id of the organisation-unit Extension (e.g. `d2-organisation-unit`)."""
        return join_id_tokens(self.definition_prefix, "organisation", "unit")

    @property
    def tracker_enrollment_extension(self) -> str:
        """FSH name of the tracker-enrollment Extension (e.g. `D2TrackerEnrollment`)."""
        return f"{self.definition_prefix}TrackerEnrollment"

    @property
    def tracker_enrollment_extension_id(self) -> str:
        """FHIR id of the tracker-enrollment Extension (e.g. `d2-tracker-enrollment`)."""
        return join_id_tokens(self.definition_prefix, "tracker", "enrollment")

    @property
    def aggregate_response_profile(self) -> str:
        """FSH name of the aggregate QuestionnaireResponse profile (e.g. `D2AggregateResponse`)."""
        return f"{self.definition_prefix}AggregateResponse"

    @property
    def aggregate_response_profile_id(self) -> str:
        """FHIR id of the aggregate QuestionnaireResponse profile (e.g. `d2-aggregate-response`)."""
        return join_id_tokens(self.definition_prefix, "aggregate", "response")

    @property
    def event_response_profile(self) -> str:
        """FSH name of the event QuestionnaireResponse profile (e.g. `D2EventResponse`)."""
        return f"{self.definition_prefix}EventResponse"

    @property
    def event_response_profile_id(self) -> str:
        """FHIR id of the event QuestionnaireResponse profile (e.g. `d2-event-response`)."""
        return join_id_tokens(self.definition_prefix, "event", "response")

    @property
    def tracker_event_response_profile(self) -> str:
        """FSH name of the tracker-event QuestionnaireResponse profile (e.g. `D2TrackerEventResponse`)."""
        return f"{self.definition_prefix}TrackerEventResponse"

    @property
    def tracker_event_response_profile_id(self) -> str:
        """FHIR id of the tracker-event QuestionnaireResponse profile (e.g. `d2-tracker-event-response`)."""
        return join_id_tokens(self.definition_prefix, "tracker", "event", "response")

    @property
    def capture_server(self) -> str:
        """FSH name of the capture CapabilityStatement instance (e.g. `D2CaptureServer`)."""
        return f"{self.definition_prefix}CaptureServer"

    @property
    def capture_server_id(self) -> str:
        """FHIR id of the capture CapabilityStatement instance (e.g. `d2-capture-server`)."""
        return join_id_tokens(self.definition_prefix, "capture", "server")
