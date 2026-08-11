"""Foundation schemas: the derived FSH names and ids for the shared aliases and D2Period artifacts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.names import join_id_tokens, page_text, quote
from dhis2w_fhir.r4 import DEFAULT_SUBJECT_RESOURCE_TYPE, SUBJECT_RESOURCE_TYPES, CodeSystemPropertyType

if TYPE_CHECKING:
    from collections.abc import Mapping

    from dhis2w_fhir.config import NamingConfig

_DEFINITION_FALLBACK_PREFIX = "D2"

#: The code a capture server answers the synthetic-response operation under, as
#: `GET|POST [base]/Questionnaire/{id}/$generate`. Deliberately not SDC's `$populate`: that
#: operation means fill-from-real-context, and answering it with invented data would mislead
#: every client that knows what it means.
GENERATE_OPERATION_CODE = "generate"

#: The one input parameter `$generate` takes - the RNG seed that makes a generated response reproducible.
GENERATE_SEED_PARAMETER = "seed"


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
    IdentifierSystemSubject(segment="option", token="Option", label="option"),
    IdentifierSystemSubject(segment="category", token="Category", label="category"),
    IdentifierSystemSubject(segment="category-option", token="CategoryOption", label="category option"),
    IdentifierSystemSubject(segment="category-combo", token="CategoryCombo", label="category combo"),
    IdentifierSystemSubject(segment="data-set", token="DataSet", label="data set"),
    IdentifierSystemSubject(segment="program", token="Program", label="program"),
    IdentifierSystemSubject(segment="data-element", token="DataElement", label="data element"),
    IdentifierSystemSubject(
        segment="category-option-combo", token="CategoryOptionCombo", label="category option combo"
    ),
    IdentifierSystemSubject(segment="program-stage", token="ProgramStage", label="program stage"),
    IdentifierSystemSubject(segment="tracked-entity-type", token="TrackedEntityType", label="tracked entity type"),
    IdentifierSystemSubject(segment="tracked-entity", token="TrackedEntity", label="tracked entity", has_code=False),
    IdentifierSystemSubject(
        segment="tracker-enrollment", token="TrackerEnrollment", label="tracker enrollment", has_code=False
    ),
)


class TerminologyPairProfile(BaseModel):
    """The fixed prose one CodeSystem/ValueSet pair publishes under, shared by both emitters.

    The FSH target quotes these into its template and the JSON target writes them onto the built
    `CodeSystem` and `ValueSet`, so the compiled guide and the served documents describe the same
    terminology in the same words. `value_set_description` is for the pair whose ValueSet
    describes a selection rather than the code system it draws from; left unset the ValueSet
    publishes the code system's own description.
    """

    model_config = ConfigDict(frozen=True)

    title: str
    description: str
    value_set_description: str | None = None

    @property
    def value_set_text(self) -> str:
        """What the ValueSet describes itself as - its own words where it has them, the CodeSystem's otherwise."""
        return self.value_set_description if self.value_set_description is not None else self.description

    @property
    def title_literal(self) -> str:
        """The title as the page-facing FSH `Title:` literal, markup characters HTML-escaped."""
        return page_text(self.title)

    @property
    def description_literal(self) -> str:
        """The CodeSystem description as the page-facing FSH `Description:` literal."""
        return page_text(self.description)

    @property
    def value_set_description_literal(self) -> str:
        """The ValueSet description as the page-facing FSH `Description:` literal."""
        return page_text(self.value_set_text)


class TerminologyPropertyDeclaration(BaseModel):
    """One concept property a generated CodeSystem declares, in the words and the type both emitters use."""

    model_config = ConfigDict(frozen=True)

    code: str
    description: str
    type: CodeSystemPropertyType

    @property
    def description_literal(self) -> str:
        """The description as the quoted FSH literal a `^property[=].description` rule takes."""
        return quote(self.description)


class FormTypeDefinition(BaseModel):
    """One DHIS2 form kind as a concept of the D2FormType terminology."""

    model_config = ConfigDict(frozen=True)

    code: str
    display: str


#: Every DHIS2 form kind a Questionnaire can be generated from. `tracked-entity` is the kind that
#: registers a person without enrolling them in anything, which is why its display names the
#: tracked entity type rather than a program.
FORM_TYPE_DEFINITIONS: tuple[FormTypeDefinition, ...] = (
    FormTypeDefinition(code="aggregate", display="Aggregate data set form"),
    FormTypeDefinition(code="event", display="Event program form"),
    FormTypeDefinition(code="tracker", display="Tracker registration form"),
    FormTypeDefinition(code="tracker-event", display="Tracker program stage form"),
    FormTypeDefinition(code="tracked-entity", display="Tracked entity type registration form"),
)

#: The prose the form-type CodeSystem/ValueSet pair publishes under.
FORM_TYPE_TERMINOLOGY = TerminologyPairProfile(
    title="DHIS2 form types",
    description="The DHIS2 form kinds a Questionnaire is generated from.",
)

#: The prose the period-type CodeSystem/ValueSet pair publishes under.
PERIOD_TYPE_TERMINOLOGY = TerminologyPairProfile(
    title="DHIS2 period types",
    description="The period types DHIS2 registers, each with the ISO period format it is written in.",
)


class TrackerSubjectTypes(BaseModel):
    """The resource types a tracker response's subject may be, as one project's response profiles pin them.

    A response profile is published once for the whole project, so it cannot pin the subject type
    of one program: it admits every type the project's tracked entity types resolve to. The
    default is always among them - a tracked entity type the project maps to nothing is a
    `Patient` - so a project that maps nothing publishes `Reference(Patient)` and a project that
    tracks herds beside people publishes `Reference(Patient or Group)`. The order is the one
    `SUBJECT_RESOURCE_TYPES` declares, so the published constraint is a function of which types
    are configured and not of the order they were written in.
    """

    model_config = ConfigDict(frozen=True)

    resource_types: tuple[str, ...] = (DEFAULT_SUBJECT_RESOURCE_TYPE,)

    @classmethod
    def of_mapping(cls, tracked_entity_types: Mapping[str, str]) -> TrackerSubjectTypes:
        """The admitted set of one project's `[generate.tracked_entity_types]` table."""
        configured = set(tracked_entity_types.values()) | {DEFAULT_SUBJECT_RESOURCE_TYPE}
        return cls(resource_types=tuple(name for name in SUBJECT_RESOURCE_TYPES if name in configured))

    @property
    def reference_targets(self) -> str:
        """The FSH reference-target list a `subject only Reference(...)` rule takes (e.g. `Patient or Group`)."""
        return " or ".join(self.resource_types)

    @property
    def subject_noun(self) -> str:
        """What the profile's prose calls the subject: a person while that is all the project tracks."""
        if self.resource_types == (DEFAULT_SUBJECT_RESOURCE_TYPE,):
            return "person"
        return "tracked entity"


class ResponseProfileDeclaration(BaseModel):
    """One QuestionnaireResponse profile as the responses template renders it.

    `period_required` marks the aggregate contract, whose response reports for a DHIS2
    reporting period; `authored_required` marks the contracts whose response reports the moment
    the data was captured; `tracker_context_required` marks the tracker-event contract, whose
    response carries the tracker enrollment it belongs to, the organisation unit the event was
    captured at, and a tracked-entity subject identified by DHIS2 UID.
    `attribute_option_combo_allowed` marks the contract whose response may name the DHIS2
    attribute option combo its values are keyed under - the aggregate one, since only a data
    value set carries that third key. `registration_context_required` marks the tracker
    registration contract, whose response mints the tracked entity and the enrollment it is
    creating rather than naming ones that already exist, and states when the enrollment began.
    `entity_context_required` marks the person-only contract, which mints the tracked entity and
    stops there: there is no enrollment to name, because the form enrols nobody in anything.
    The flags are what the shared template branches on.
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
    registration_context_required: bool = False
    entity_context_required: bool = False
    attribute_option_combo_allowed: bool = False

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
    def tracked_entity_attribute_value_extension(self) -> str:
        """FSH name of the tracked-entity-attribute-value Extension (e.g. `D2TrackedEntityAttributeValue`)."""
        return f"{self.definition_prefix}TrackedEntityAttributeValue"

    @property
    def tracked_entity_attribute_value_extension_id(self) -> str:
        """FHIR id of the tracked-entity-attribute-value Extension (e.g. `d2-tracked-entity-attribute-value`)."""
        return join_id_tokens(self.definition_prefix, "tracked", "entity", "attribute", "value")

    @property
    def attribute_option_combo_extension(self) -> str:
        """FSH name of the response-side attribute-option-combo Extension (e.g. `D2AttributeOptionCombo`).

        Singular: it carries the one combo a response's values are keyed under. Its plural
        sibling `attribute_option_combos_extension` sits on the Questionnaire and names the
        vocabulary that one is drawn from - the two differ by a single character on purpose,
        the way `D2OrganisationUnit` and `D2OrganisationUnitAssignment` do.
        """
        return f"{self.definition_prefix}AttributeOptionCombo"

    @property
    def attribute_option_combo_extension_id(self) -> str:
        """FHIR id of the response-side attribute-option-combo Extension (e.g. `d2-attribute-option-combo`)."""
        return join_id_tokens(self.definition_prefix, "attribute", "option", "combo")

    @property
    def attribute_option_combos_extension(self) -> str:
        """FSH name of the form-side attribute-option-combo Extension (e.g. `D2AttributeOptionCombos`).

        Plural: it names the ValueSet of every attribute option combo the form admits, which is
        what a capture client picks one from and what a server validates the response's coding
        against.
        """
        return f"{self.definition_prefix}AttributeOptionCombos"

    @property
    def attribute_option_combos_extension_id(self) -> str:
        """FHIR id of the form-side attribute-option-combo Extension (e.g. `d2-attribute-option-combos`)."""
        return join_id_tokens(self.definition_prefix, "attribute", "option", "combos")

    @property
    def organisation_unit_extension(self) -> str:
        """FSH name of the organisation-unit Extension (e.g. `D2OrganisationUnit`)."""
        return f"{self.definition_prefix}OrganisationUnit"

    @property
    def organisation_unit_extension_id(self) -> str:
        """FHIR id of the organisation-unit Extension (e.g. `d2-organisation-unit`)."""
        return join_id_tokens(self.definition_prefix, "organisation", "unit")

    @property
    def organisation_unit_assignment_extension(self) -> str:
        """FSH name of the organisation-unit-assignment Extension (e.g. `D2OrganisationUnitAssignment`)."""
        return f"{self.definition_prefix}OrganisationUnitAssignment"

    @property
    def organisation_unit_assignment_extension_id(self) -> str:
        """FHIR id of the organisation-unit-assignment Extension (e.g. `d2-organisation-unit-assignment`)."""
        return join_id_tokens(self.definition_prefix, "organisation", "unit", "assignment")

    @property
    def organisation_unit_level_extension(self) -> str:
        """FSH name of the organisation-unit-level Extension (e.g. `D2OrganisationUnitLevel`)."""
        return f"{self.definition_prefix}OrganisationUnitLevel"

    @property
    def organisation_unit_level_extension_id(self) -> str:
        """FHIR id of the organisation-unit-level Extension (e.g. `d2-organisation-unit-level`)."""
        return join_id_tokens(self.definition_prefix, "organisation", "unit", "level")

    @property
    def tracker_enrollment_extension(self) -> str:
        """FSH name of the tracker-enrollment Extension (e.g. `D2TrackerEnrollment`)."""
        return f"{self.definition_prefix}TrackerEnrollment"

    @property
    def tracker_enrollment_extension_id(self) -> str:
        """FHIR id of the tracker-enrollment Extension (e.g. `d2-tracker-enrollment`)."""
        return join_id_tokens(self.definition_prefix, "tracker", "enrollment")

    @property
    def enrolled_at_extension(self) -> str:
        """FSH name of the enrollment-date Extension (e.g. `D2EnrolledAt`)."""
        return f"{self.definition_prefix}EnrolledAt"

    @property
    def enrolled_at_extension_id(self) -> str:
        """FHIR id of the enrollment-date Extension (e.g. `d2-enrolled-at`)."""
        return join_id_tokens(self.definition_prefix, "enrolled", "at")

    @property
    def incident_at_extension(self) -> str:
        """FSH name of the incident-date Extension (e.g. `D2IncidentAt`)."""
        return f"{self.definition_prefix}IncidentAt"

    @property
    def incident_at_extension_id(self) -> str:
        """FHIR id of the incident-date Extension (e.g. `d2-incident-at`)."""
        return join_id_tokens(self.definition_prefix, "incident", "at")

    @property
    def entity_level_extension(self) -> str:
        """FSH name of the entity-level Extension (e.g. `D2EntityLevel`)."""
        return f"{self.definition_prefix}EntityLevel"

    @property
    def entity_level_extension_id(self) -> str:
        """FHIR id of the entity-level Extension (e.g. `d2-entity-level`)."""
        return join_id_tokens(self.definition_prefix, "entity", "level")

    @property
    def subject_exists_extension(self) -> str:
        """FSH name of the existing-subject Extension (e.g. `D2SubjectExists`).

        Named for the fact it carries rather than for the act that produced it: the boolean says
        the person the response is subject to is already held by the instance, which is what the
        translator branches on. `D2LinkedSubject` was the alternative and names a capture-client
        gesture - linking - that a reader of the contract has no way to resolve. OWNER REVIEW.
        """
        return f"{self.definition_prefix}SubjectExists"

    @property
    def subject_exists_extension_id(self) -> str:
        """FHIR id of the existing-subject Extension (e.g. `d2-subject-exists`)."""
        return join_id_tokens(self.definition_prefix, "subject", "exists")

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
    def tracker_registration_response_profile(self) -> str:
        """FSH name of the tracker registration QuestionnaireResponse profile (e.g. `D2TrackerRegistrationResponse`)."""
        return f"{self.definition_prefix}TrackerRegistrationResponse"

    @property
    def tracker_registration_response_profile_id(self) -> str:
        """FHIR id of the registration QuestionnaireResponse profile (e.g. `d2-tracker-registration-response`)."""
        return join_id_tokens(self.definition_prefix, "tracker", "registration", "response")

    @property
    def tracked_entity_response_profile(self) -> str:
        """FSH name of the person-only QuestionnaireResponse profile (e.g. `D2TrackedEntityResponse`)."""
        return f"{self.definition_prefix}TrackedEntityResponse"

    @property
    def tracked_entity_response_profile_id(self) -> str:
        """FHIR id of the person-only QuestionnaireResponse profile (e.g. `d2-tracked-entity-response`)."""
        return join_id_tokens(self.definition_prefix, "tracked", "entity", "response")

    @property
    def tracker_event_response_profile(self) -> str:
        """FSH name of the tracker-event QuestionnaireResponse profile (e.g. `D2TrackerEventResponse`)."""
        return f"{self.definition_prefix}TrackerEventResponse"

    @property
    def tracker_event_response_profile_id(self) -> str:
        """FHIR id of the tracker-event QuestionnaireResponse profile (e.g. `d2-tracker-event-response`)."""
        return join_id_tokens(self.definition_prefix, "tracker", "event", "response")

    @property
    def generate_operation(self) -> str:
        """FSH name of the `$generate` OperationDefinition instance (e.g. `D2GenerateOperation`)."""
        return f"{self.definition_prefix}GenerateOperation"

    @property
    def generate_operation_id(self) -> str:
        """FHIR id of the `$generate` OperationDefinition instance (e.g. `d2-generate`)."""
        return join_id_tokens(self.definition_prefix, "generate")

    @property
    def capture_server(self) -> str:
        """FSH name of the capture CapabilityStatement instance (e.g. `D2CaptureServer`)."""
        return f"{self.definition_prefix}CaptureServer"

    @property
    def capture_server_id(self) -> str:
        """FHIR id of the capture CapabilityStatement instance (e.g. `d2-capture-server`)."""
        return join_id_tokens(self.definition_prefix, "capture", "server")
