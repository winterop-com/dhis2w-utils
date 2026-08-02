"""Foundation schemas: the derived FSH names and ids for the shared aliases and D2Period artifacts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.names import join_id_tokens, page_text

if TYPE_CHECKING:
    from dhis2w_fhir.config import NamingConfig

_DEFINITION_FALLBACK_PREFIX = "D2"


class IdentifierSystemSubject(BaseModel):
    """One DHIS2 object kind whose UID and code each get an identifier system."""

    model_config = ConfigDict(frozen=True)

    segment: str
    token: str
    label: str


#: The object kinds that carry a DHIS2 identifier system today; each yields a UID and a code system.
IDENTIFIER_SYSTEM_SUBJECTS = (
    IdentifierSystemSubject(segment="org-unit", token="OrgUnit", label="organisation unit"),
    IdentifierSystemSubject(segment="option-set", token="OptionSet", label="option set"),
    IdentifierSystemSubject(segment="data-set", token="DataSet", label="data set"),
    IdentifierSystemSubject(segment="program", token="Program", label="program"),
    IdentifierSystemSubject(segment="data-element", token="DataElement", label="data element"),
    IdentifierSystemSubject(
        segment="category-option-combo", token="CategoryOptionCombo", label="category option combo"
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
    reporting period; `authored_required` marks the event contract, whose response reports
    the moment the event occurred. The two flags are what the shared template branches on.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    profile_id: str
    form_type_code: str
    title: str
    description: str
    period_required: bool = False
    authored_required: bool = False

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
    def capture_server(self) -> str:
        """FSH name of the capture CapabilityStatement instance (e.g. `D2CaptureServer`)."""
        return f"{self.definition_prefix}CaptureServer"

    @property
    def capture_server_id(self) -> str:
        """FHIR id of the capture CapabilityStatement instance (e.g. `d2-capture-server`)."""
        return join_id_tokens(self.definition_prefix, "capture", "server")
