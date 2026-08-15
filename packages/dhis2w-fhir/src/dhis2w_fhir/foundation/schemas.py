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


#: The identifier-system segment of every declared DHIS2 object kind, keyed by its subject token.
IDENTIFIER_SYSTEM_SEGMENTS: dict[str, str] = {subject.token: subject.segment for subject in IDENTIFIER_SYSTEM_SUBJECTS}


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

#: The sub-extension urls D2Period slices its three facts under, as `d2-period.fsh.jinja` names them.
#: They live with the extension's own declaration, because everything that reads a reporting period -
#: the example builder writing one, the translator reading one back, the published map naming where a
#: DHIS2 period comes from - has to spell these three slices the same way.
PERIOD_ISO_SUB_EXTENSION = "iso"
PERIOD_TYPE_SUB_EXTENSION = "type"
PERIOD_RANGE_SUB_EXTENSION = "period"

#: The sub-extension urls D2DateLabels slices its three labels under, as `d2-date-labels.fsh.jinja`
#: names them. They live with the extension's own declaration because both emitters and every
#: reader of a served form - a capture client labelling its date field, a test asserting the label
#: rode - has to spell the three slices the same way.
DATE_LABEL_ENROLLMENT_SUB_EXTENSION = "enrollmentDate"
DATE_LABEL_INCIDENT_SUB_EXTENSION = "incidentDate"
DATE_LABEL_EVENT_SUB_EXTENSION = "eventDate"

#: The prose the period-type CodeSystem/ValueSet pair publishes under.
PERIOD_TYPE_TERMINOLOGY = TerminologyPairProfile(
    title="DHIS2 period types",
    description="The period types DHIS2 registers, each with the ISO period format it is written in.",
)


class LogicalModelElement(BaseModel):
    """One element of a DHIS2 wire shape published as a logical model, in the words both readers take.

    The FSH template renders these into the `kind = logical` StructureDefinition SUSHI compiles, and
    the conversion contract gate reads the compiled differential back to judge the forwarder's output
    against it. One declaration, two readers, so the published contract and the checked contract
    cannot drift apart without a test saying so.
    """

    model_config = ConfigDict(frozen=True)

    path: str
    """Dotted path relative to the model root, as the FSH rule and the compiled differential spell it."""

    minimum: int
    maximum: str
    """`1` for a single value, `*` for a repeating one - the right half of the FSH cardinality."""

    element_type: str
    """The FHIR type the element carries: `string`, `date`, or `BackboneElement` for a nested group."""

    short: str
    definition: str

    @property
    def cardinality(self) -> str:
        """The FSH cardinality literal (e.g. `0..*`)."""
        return f"{self.minimum}..{self.maximum}"

    @property
    def short_literal(self) -> str:
        """The short label as the quoted FSH literal an element rule takes."""
        return quote(self.short)

    @property
    def definition_literal(self) -> str:
        """The definition as the quoted FSH literal an element rule takes."""
        return quote(self.definition)

    @property
    def required(self) -> bool:
        """Whether the wire shape always carries this element."""
        return self.minimum >= 1

    @property
    def repeats(self) -> bool:
        """Whether the wire shape carries this element more than once."""
        return self.maximum != "1"


#: The `/api/dataValueSets` envelope one aggregate QuestionnaireResponse is imported as, element by
#: element, exactly as `dhis2w_fhir.conversion.payloads.translate_aggregate_response` writes it. The
#: three keys DHIS2 stores a data value under - the data set, the reporting period, and the
#: organisation unit - are the required ones; the attribute option combo is the fourth key only a
#: data set on a non-default category combo carries, and the complete date is the day the response
#: records itself as authored.
DATA_VALUE_SET_ELEMENTS: tuple[LogicalModelElement, ...] = (
    LogicalModelElement(
        path="dataSet",
        minimum=1,
        maximum="1",
        element_type="string",
        short="Data set",
        definition=(
            "The DHIS2 data set the values are reported for, as its UID. It comes off the "
            "`$DHIS2-DS` identifier of the Questionnaire the response answers, never off the "
            "response itself."
        ),
    ),
    LogicalModelElement(
        path="period",
        minimum=1,
        maximum="1",
        element_type="string",
        short="Reporting period",
        definition=(
            "The DHIS2 ISO period the values are reported for (e.g. `202401`), off the `iso` "
            "sub-extension of the response's reporting-period extension."
        ),
    ),
    LogicalModelElement(
        path="orgUnit",
        minimum=1,
        maximum="1",
        element_type="string",
        short="Organisation unit",
        definition=(
            "The DHIS2 organisation unit the values are reported for, as its UID. It is the DHIS2 "
            "identifier of the published Location the response is subject to."
        ),
    ),
    LogicalModelElement(
        path="attributeOptionCombo",
        minimum=0,
        maximum="1",
        element_type="string",
        short="Attribute option combo",
        definition=(
            "The DHIS2 attribute option combo the values are keyed under, as its UID. A data set on "
            "the default category combo carries none, and DHIS2 fills the field itself."
        ),
    ),
    LogicalModelElement(
        path="completeDate",
        minimum=0,
        maximum="1",
        element_type="date",
        short="Complete date",
        definition=(
            "The day the report was completed, as a calendar date. It is the day the response "
            "records itself as authored, read in the project's own time zone."
        ),
    ),
    LogicalModelElement(
        path="dataValues",
        minimum=0,
        maximum="*",
        element_type="BackboneElement",
        short="Data values",
        definition="One cell of the report per answered question of the form.",
    ),
    LogicalModelElement(
        path="dataValues.dataElement",
        minimum=1,
        maximum="1",
        element_type="string",
        short="Data element",
        definition=(
            "The DHIS2 data element the cell reports, as its UID. It is the first segment of the "
            "answered question's link id."
        ),
    ),
    LogicalModelElement(
        path="dataValues.categoryOptionCombo",
        minimum=0,
        maximum="1",
        element_type="string",
        short="Category option combo",
        definition=(
            "The DHIS2 category option combo the cell is disaggregated by, as its UID. It is the "
            "second segment of the answered question's link id, and a question asking an "
            "undisaggregated data element carries none."
        ),
    ),
    LogicalModelElement(
        path="dataValues.value",
        minimum=1,
        maximum="1",
        element_type="string",
        short="Value",
        definition=(
            "The value as DHIS2 stores it. Every DHIS2 data value is a string on the wire, whatever "
            "the data element's value type, so a lexical decimal and a DHIS2 option code both "
            "survive the crossing byte for byte."
        ),
    ),
)


class ArtifactProfile(BaseModel):
    """The fixed prose one definitional artifact publishes under, in the form its FSH template takes."""

    model_config = ConfigDict(frozen=True)

    title: str
    description: str

    @property
    def title_literal(self) -> str:
        """The title as the page-facing FSH `Title:` literal, markup characters HTML-escaped."""
        return page_text(self.title)

    @property
    def description_literal(self) -> str:
        """The description as the page-facing FSH `Description:` literal, markup characters HTML-escaped."""
        return page_text(self.description)


#: The prose the data value set logical model publishes under.
DATA_VALUE_SET_MODEL = ArtifactProfile(
    title="DHIS2 data value set",
    description=(
        "The `/api/dataValueSets` envelope one aggregate QuestionnaireResponse is imported as: the "
        "data set, the reporting period, the organisation unit, and the attribute option combo the "
        "report is keyed by, plus one data value per answered question. This is the DHIS2 wire shape "
        "stated in FHIR terms, so a map targeting it says where each DHIS2 field comes from."
    ),
)

#: The prose the aggregate conversion StructureMap publishes under.
AGGREGATE_CONVERSION_MAP = ArtifactProfile(
    title="DHIS2 aggregate response to data value set",
    description=(
        "How one aggregate QuestionnaireResponse becomes the DHIS2 data value set it is imported as, "
        "element by element. The map is the conversion contract a third party builds their own bridge "
        "from; it is not executed at runtime, and the rules whose meaning exceeds what a transform can "
        "state carry that on their own documentation."
    ),
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
    def period_type_extension(self) -> str:
        """FSH name of the period-type Extension (e.g. `D2PeriodType`).

        The sibling of `D2Period`, one grain up: `D2Period` carries the period a response reports
        for, and this states the period type every response of an aggregate form has to report
        under. Both draw their code from the same `D2PeriodType_VS`, so a client reading the form
        knows which ISO period format the instance will accept before it builds one.
        """
        return f"{self.definition_prefix}PeriodType"

    @property
    def period_type_extension_id(self) -> str:
        """FHIR id of the period-type Extension (e.g. `d2-period-type`)."""
        return join_id_tokens(self.definition_prefix, "period", "type")

    @property
    def date_labels_extension(self) -> str:
        """FSH name of the date-labels Extension (e.g. `D2DateLabels`).

        Plural and named for the dates rather than for the DHIS2 fields spelling them:
        `enrollmentDateLabel`, `incidentDateLabel`, and `executionDateLabel` are three DHIS2
        form-rendering fields on two different objects, and what the published contract states is
        the words this instance puts on the enrollment date, the incident date, and the event date
        of the form. A sub-extension is present only where DHIS2 states the label, so a form
        carrying none of the three carries no extension at all.
        """
        return f"{self.definition_prefix}DateLabels"

    @property
    def date_labels_extension_id(self) -> str:
        """FHIR id of the date-labels Extension (e.g. `d2-date-labels`)."""
        return join_id_tokens(self.definition_prefix, "date", "labels")

    @property
    def repeatable_extension(self) -> str:
        """FSH name of the repeatable Extension (e.g. `D2Repeatable`)."""
        return f"{self.definition_prefix}Repeatable"

    @property
    def repeatable_extension_id(self) -> str:
        """FHIR id of the repeatable Extension (e.g. `d2-repeatable`)."""
        return join_id_tokens(self.definition_prefix, "repeatable")

    @property
    def description_extension(self) -> str:
        """FSH name of the item-description Extension (e.g. `D2Description`)."""
        return f"{self.definition_prefix}Description"

    @property
    def description_extension_id(self) -> str:
        """FHIR id of the item-description Extension (e.g. `d2-description`)."""
        return join_id_tokens(self.definition_prefix, "description")

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
    def collects_incident_date_extension(self) -> str:
        """FSH name of the incident-date declaration Extension (e.g. `D2CollectsIncidentDate`).

        Named for the fact rather than for the DHIS2 field spelling it: `displayIncidentDate` is a
        DHIS2 form-rendering flag, and what the published contract states is that the program
        collects the date of the incident its enrollments follow. A reader of the guide resolves
        the fact without knowing the DHIS2 field, and a registration response carrying `D2IncidentAt`
        is answering exactly this declaration.
        """
        return f"{self.definition_prefix}CollectsIncidentDate"

    @property
    def collects_incident_date_extension_id(self) -> str:
        """FHIR id of the incident-date declaration Extension (e.g. `d2-collects-incident-date`)."""
        return join_id_tokens(self.definition_prefix, "collects", "incident", "date")

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
    def data_value_set_model(self) -> str:
        """FSH name of the data value set logical model (e.g. `D2DataValueSet`)."""
        return f"{self.definition_prefix}DataValueSet"

    @property
    def data_value_set_model_id(self) -> str:
        """FHIR id of the data value set logical model (e.g. `d2-data-value-set`)."""
        return join_id_tokens(self.definition_prefix, "data", "value", "set")

    @property
    def aggregate_conversion_map(self) -> str:
        """FSH name of the aggregate conversion StructureMap (e.g. `D2AggregateResponseToDataValueSet`)."""
        return f"{self.definition_prefix}AggregateResponseToDataValueSet"

    @property
    def aggregate_conversion_map_id(self) -> str:
        """FHIR id of the aggregate conversion StructureMap (e.g. `d2-aggregate-response-to-data-value-set`)."""
        return join_id_tokens(self.definition_prefix, "aggregate", "response", "to", "data", "value", "set")

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
