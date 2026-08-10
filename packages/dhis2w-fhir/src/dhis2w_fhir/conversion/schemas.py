"""Conversion schemas: the translation context, the outcome taxonomy, and the typed DHIS2 payloads.

Every type the QR -> DHIS2 translator reads or writes lives here. The context side
(`ConversionNaming`, `OptionTable`, `QuestionSpec`, `FormSpec`, `ConversionContext`) is what a
caller assembles once from the compiled IG artifacts; the outcome side (`ConversionNote`,
`ConversionRefusal`, `ConversionResult`, `ConversionReport`) is what one translated response
answers with.

The DHIS2 payloads themselves are the generated OpenAPI models: `DataValueSet` / `DataValue` for
the aggregate envelope, `TrackerEvent` / `TrackerDataValue` for both event kinds, and
`TrackerTrackedEntity` / `TrackerEnrollment` / `TrackerAttribute` for the registration one.
Nothing is hand-rolled - those schemas carry every field the import endpoints read, and every wire
value they carry is a string, so a lexical decimal and a DHIS2 option code survive untouched.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from dhis2w_client.generated.v42.oas import DataValueSet, TrackerEvent, TrackerTrackedEntity
from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.foundation.schemas import IDENTIFIER_SYSTEM_SUBJECTS, FoundationNaming
from dhis2w_fhir.resources.questionnaires.schemas import FormKind

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig

#: The identifier-system segment of every DHIS2 object kind a response or a form names, by subject token.
_SEGMENTS_BY_TOKEN = {subject.token: subject.segment for subject in IDENTIFIER_SYSTEM_SUBJECTS}

#: The DHIS2 identifier namespace an option-set ConceptMap carries its option codes onto. It is not a
#: declared subject of `IDENTIFIER_SYSTEM_SUBJECTS`, because an option code is a mapping target rather
#: than an identifier any generated resource carries.
_OPTION_CODE_SEGMENT = "option-code"

#: The suffix a ConceptMap's DHIS2-code target namespace takes over its UID sibling's segment.
_CODE_SEGMENT_SUFFIX = "-code"

CONCEPT_CODE_TIER = "concept-code"
"""The spelling the contract asks for: the concept code the served CodeSystem publishes."""

OPTION_UID_TIER = "option-uid"
"""The first lenient fall-back: the DHIS2 UID of the option, sent against a code-mode CodeSystem."""

OPTION_CODE_TIER = "option-code"
"""The second lenient fall-back: the DHIS2 code of the option, sent against an id-mode CodeSystem."""

__all__ = [
    "CONCEPT_CODE_TIER",
    "FORWARD_TARGET_ORDER",
    "OPTION_CODE_TIER",
    "OPTION_UID_TIER",
    "CodedAnswerMode",
    "ConversionContext",
    "ConversionNaming",
    "ConversionNote",
    "ConversionNoteCategory",
    "ConversionRefusal",
    "ConversionRefusalCategory",
    "ConversionReport",
    "ConversionResult",
    "ConversionTargetKind",
    "FormSpec",
    "OptionEntry",
    "OptionLookup",
    "OptionTable",
    "QuestionSpec",
    "ResolvedOption",
    "TARGET_KINDS_BY_FORM_KIND",
    "WireValueKind",
]


class ConversionTargetKind(StrEnum):
    """Which DHIS2 import payload one translated response becomes."""

    #: The `/api/dataValueSets` envelope a data set's response reports as.
    DATA_VALUE_SET = "data-value-set"

    #: The `/api/tracker` event an event program's response reports as.
    EVENT = "event"

    #: The `/api/tracker` tracked entity and enrollment a tracker registration response creates.
    TRACKER = "tracker"

    #: The `/api/tracker` event a tracker program stage's response reports as, on its enrollment.
    TRACKER_EVENT = "tracker-event"


#: The payload each DHIS2 form kind translates into - the one place the two vocabularies meet.
TARGET_KINDS_BY_FORM_KIND: dict[FormKind, ConversionTargetKind] = {
    "aggregate": ConversionTargetKind.DATA_VALUE_SET,
    "event": ConversionTargetKind.EVENT,
    "tracker": ConversionTargetKind.TRACKER,
    "tracker-event": ConversionTargetKind.TRACKER_EVENT,
}

#: The order a drain posts its payloads in. A registration creates the enrollment a stage event of
#: the same drain answers against, and DHIS2 refuses an event whose enrollment it cannot find with
#: `E1313` - so registrations go first and every other payload follows in spool order.
FORWARD_TARGET_ORDER: tuple[ConversionTargetKind, ...] = (
    ConversionTargetKind.TRACKER,
    ConversionTargetKind.DATA_VALUE_SET,
    ConversionTargetKind.EVENT,
    ConversionTargetKind.TRACKER_EVENT,
)


class CodedAnswerMode(StrEnum):
    """How exactly a coded answer has to name its concept before the translator accepts it."""

    #: Only the concept code the served CodeSystem publishes resolves; anything else is refused.
    STRICT = "strict"

    #: The concept code resolves first, then the DHIS2 option UID, then the DHIS2 option code, each noted.
    LENIENT = "lenient"


class WireValueKind(StrEnum):
    """How one question's answers are serialised onto the DHIS2 wire.

    Derived once, at context build, from the question's R4 item type, whether it repeats, whether
    it binds terminology, and - when the caller supplied one - the DHIS2 value type behind it.
    Every serialisation branch dispatches on this and on nothing else.
    """

    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    TRUE_ONLY = "true-only"
    TEXT = "text"
    CODED = "coded"
    MULTI_TEXT = "multi-text"
    DATE = "date"
    DATE_TIME = "date-time"
    TIME = "time"
    URI = "uri"
    ORGANISATION_UNIT = "organisation-unit"
    ATTACHMENT = "attachment"


class ConversionNoteCategory(StrEnum):
    """The kind of interpretation one conversion note records, which is what makes a note reasonable about."""

    #: A coded answer resolved on a spelling the contract does not ask for (lenient mode only).
    CODED_ANSWER_FALLBACK = "coded-answer-fallback"

    #: A coded answer's terminology is not in the context, so its code went to DHIS2 unchecked.
    CODED_ANSWER_UNCHECKED = "coded-answer-unchecked"

    #: A code-mode concept whose code fell back to the UID, so the DHIS2 option code is unrecoverable.
    OPTION_CODE_UNRECOVERABLE = "option-code-unrecoverable"

    #: A `TRUE_ONLY` question answered `false`, which DHIS2 spells as no data value at all.
    TRUE_ONLY_FALSE_DROPPED = "true-only-false-dropped"

    #: The response status maps onto a DHIS2 event status that several statuses map forward onto.
    STATUS_COLLAPSED = "status-collapsed"

    #: A zoned R4 timestamp read back to the zone-less wall clock DHIS2 stores (BUGS.md #62).
    WALL_CLOCK_DERIVED = "wall-clock-derived"

    #: A timestamp carrying no offset, taken as already being the wall clock DHIS2 stores.
    TIMESTAMP_UNZONED = "timestamp-unzoned"

    #: The D2Period date range disagrees with the ISO period it rides beside; the ISO period wins.
    PERIOD_RANGE_IGNORED = "period-range-ignored"

    #: The context carries no Location table, so a `Location/<id>` reference is read as a DHIS2 UID.
    ORGANISATION_UNIT_ASSUMED = "organisation-unit-assumed"

    #: The context knows no DHIS2 value type for a boolean question, so it is read as `BOOLEAN`.
    BOOLEAN_VALUE_TYPE_ASSUMED = "boolean-value-type-assumed"

    #: The data value set's `completeDate` was taken from the response's `authored` instant.
    COMPLETE_DATE_DERIVED = "complete-date-derived"

    #: A tracker response carries a subject reference, which its tracked-entity identifier supersedes.
    SUBJECT_REFERENCE_IGNORED = "subject-reference-ignored"

    #: An item answering a group's link id, which carries no data value of its own.
    GROUP_ITEM_IGNORED = "group-item-ignored"

    #: A response names an attribute option combo its form declares no vocabulary for, so it is not written.
    ATTRIBUTE_OPTION_COMBO_IGNORED = "attribute-option-combo-ignored"


class ConversionRefusalCategory(StrEnum):
    """The kind of refusal one untranslatable response raised, named so a caller can route it."""

    #: The response declares no DHIS2 form type, so there is no contract to translate it under.
    NO_FORM_TYPE = "no-form-type"

    #: The response answers a questionnaire canonical the context holds no form for.
    UNKNOWN_FORM = "unknown-form"

    #: The response declares one form kind and answers a form of another.
    FORM_KIND_MISMATCH = "form-kind-mismatch"

    #: The form's Questionnaire carries no DHIS2 identifier for the object it was generated from.
    MISSING_TARGET_IDENTIFIER = "missing-target-identifier"

    #: An answered item names a link id the form does not ask.
    UNKNOWN_LINK_ID = "unknown-link-id"

    #: An answer carries a `value[x]` element the question does not answer on.
    ANSWER_ELEMENT_MISMATCH = "answer-element-mismatch"

    #: An answered item carries no value at all.
    MISSING_ANSWER_VALUE = "missing-answer-value"

    #: A question storing one DHIS2 data value was answered more than once.
    REPEATED_ANSWER = "repeated-answer"

    #: An answer carries a value DHIS2 has no wire spelling for.
    UNSUPPORTED_ANSWER_VALUE = "unsupported-answer-value"

    #: An aggregate response carries no D2Period extension.
    MISSING_PERIOD = "missing-period"

    #: The form declares an attribute-option-combo vocabulary and the response names no concept of it.
    MISSING_ATTRIBUTE_OPTION_COMBO = "missing-attribute-option-combo"

    #: The response names an attribute option combo the declared vocabulary holds no concept for.
    UNRESOLVABLE_ATTRIBUTE_OPTION_COMBO = "unresolvable-attribute-option-combo"

    #: An aggregate response's ISO period does not read as a DHIS2 period.
    MALFORMED_PERIOD = "malformed-period"

    #: The response names no organisation unit where its kind requires one.
    MISSING_ORGANISATION_UNIT = "missing-organisation-unit"

    #: The response names a Location the context resolves to no DHIS2 organisation unit.
    UNRESOLVABLE_ORGANISATION_UNIT = "unresolvable-organisation-unit"

    #: A coded answer carries no code.
    MISSING_CODING = "missing-coding"

    #: A coded answer names a code the question's terminology does not hold.
    UNRESOLVABLE_CODING = "unresolvable-coding"

    #: A coded answer names a code more than one option of the terminology carries.
    AMBIGUOUS_CODING = "ambiguous-coding"

    #: A tracker response names no tracked entity.
    MISSING_SUBJECT = "missing-subject"

    #: A tracker response names no enrollment.
    MISSING_ENROLLMENT = "missing-enrollment"

    #: A registration form's Questionnaire names no tracked entity type, so there is nothing to enrol a person as.
    MISSING_TRACKED_ENTITY_TYPE = "missing-tracked-entity-type"

    #: A registration response states no enrollment date, which DHIS2 requires of every enrollment.
    MISSING_ENROLLMENT_DATE = "missing-enrollment-date"

    #: A registration response's enrollment or incident date does not read as an instant.
    MALFORMED_ENROLLMENT_DATE = "malformed-enrollment-date"

    #: An event response records no `authored` instant, which is the moment the event occurred.
    MISSING_OCCURRENCE = "missing-occurrence"

    #: The response status names something DHIS2 has no event status for.
    UNMAPPABLE_STATUS = "unmappable-status"


class ConversionNote(BaseModel):
    """One thing the translator had to interpret, recorded rather than left silent."""

    model_config = ConfigDict(frozen=True)

    category: ConversionNoteCategory
    message: str
    link_id: str | None = None
    """The question the note is about, or None when it is about the response as a whole."""


class ConversionRefusal(BaseModel):
    """One reason a response was not translated, naming the element it stumbled on."""

    model_config = ConfigDict(frozen=True)

    category: ConversionRefusalCategory
    reason: str
    link_id: str | None = None
    """The question the refusal is about, or None when it is about the response as a whole."""

    element: str | None = None
    """The FHIR element or DHIS2 field the refusal names, when one is narrower than the link id."""


class ConversionNaming(BaseModel):
    """The extension urls and identifier systems one project's responses and forms are written in.

    Every name is derived from `fhir.toml` - the IG canonical for the extensions the response
    profiles pin, and `[generate] identifier_system_base` for the DHIS2 identifier systems a
    response names its tracked entity, its enrollment, its organisation unit, and its form under.
    """

    model_config = ConfigDict(frozen=True)

    form_type_url: str
    period_url: str
    organisation_unit_url: str
    tracker_enrollment_url: str
    enrolled_at_url: str
    """Canonical of the extension a registration response dates the enrollment it mints from."""

    incident_at_url: str
    """Canonical of the extension a registration response dates the incident that enrollment follows."""

    attribute_option_combos_url: str
    """Canonical of the Questionnaire extension a form declares its attribute-option-combo ValueSet on."""

    attribute_option_combo_url: str
    """Canonical of the QuestionnaireResponse extension one response names its attribute option combo on."""

    organisation_unit_system: str
    data_set_system: str
    program_system: str
    program_stage_system: str
    tracked_entity_type_system: str
    """The DHIS2 identifier system a registration form names the type it enrols a person as under."""

    tracked_entity_system: str
    tracker_enrollment_system: str
    option_code_system: str
    """The DHIS2 identifier namespace an option-set ConceptMap carries its option codes onto."""

    option_uid_system: str
    """The DHIS2 identifier namespace an option-set ConceptMap carries its option UIDs onto."""

    attribute_option_combo_uid_system: str
    """The DHIS2 identifier namespace an attribute-combo ConceptMap carries its option-combo UIDs onto."""

    attribute_option_combo_code_system: str
    """The DHIS2 identifier namespace an attribute-combo ConceptMap carries its option-combo codes onto."""

    @classmethod
    def from_config(cls, config: GenerateConfig, canonical: str) -> ConversionNaming:
        """Derive every conversion name from the IG canonical plus the `[generate]` naming tokens and base."""
        names = FoundationNaming.from_naming(config.naming)
        base = config.identifier_system_base
        return cls(
            form_type_url=_definition_url(canonical, names.form_type_extension_id),
            period_url=_definition_url(canonical, names.period_extension_id),
            organisation_unit_url=_definition_url(canonical, names.organisation_unit_extension_id),
            tracker_enrollment_url=_definition_url(canonical, names.tracker_enrollment_extension_id),
            enrolled_at_url=_definition_url(canonical, names.enrolled_at_extension_id),
            incident_at_url=_definition_url(canonical, names.incident_at_extension_id),
            attribute_option_combos_url=_definition_url(canonical, names.attribute_option_combos_extension_id),
            attribute_option_combo_url=_definition_url(canonical, names.attribute_option_combo_extension_id),
            organisation_unit_system=_identifier_system(base, _SEGMENTS_BY_TOKEN["OrgUnit"]),
            data_set_system=_identifier_system(base, _SEGMENTS_BY_TOKEN["DataSet"]),
            program_system=_identifier_system(base, _SEGMENTS_BY_TOKEN["Program"]),
            program_stage_system=_identifier_system(base, _SEGMENTS_BY_TOKEN["ProgramStage"]),
            tracked_entity_type_system=_identifier_system(base, _SEGMENTS_BY_TOKEN["TrackedEntityType"]),
            tracked_entity_system=_identifier_system(base, _SEGMENTS_BY_TOKEN["TrackedEntity"]),
            tracker_enrollment_system=_identifier_system(base, _SEGMENTS_BY_TOKEN["TrackerEnrollment"]),
            option_code_system=_identifier_system(base, _OPTION_CODE_SEGMENT),
            option_uid_system=_identifier_system(base, _SEGMENTS_BY_TOKEN["Option"]),
            attribute_option_combo_uid_system=_identifier_system(base, _SEGMENTS_BY_TOKEN["CategoryOptionCombo"]),
            attribute_option_combo_code_system=_identifier_system(
                base, f"{_SEGMENTS_BY_TOKEN['CategoryOptionCombo']}{_CODE_SEGMENT_SUFFIX}"
            ),
        )

    def target_identifier_system(self, form_kind: FormKind) -> str:
        """The DHIS2 identifier system one form kind's Questionnaire names the object it was generated from under."""
        if form_kind == "aggregate":
            return self.data_set_system
        if form_kind == "tracker-event":
            return self.program_stage_system
        return self.program_system


def _definition_url(canonical: str, definition_id: str) -> str:
    """The canonical url one generated StructureDefinition is published at, as SUSHI resolves `Canonical(...)`."""
    return f"{canonical}/StructureDefinition/{definition_id}"


def _identifier_system(base: str, segment: str) -> str:
    """The DHIS2 identifier system one object kind is named under, as `d2-aliases.fsh` declares it."""
    return f"{base}/id/{segment}"


class OptionEntry(BaseModel):
    """One DHIS2 option of a served CodeSystem, in every spelling a coded answer may name it by."""

    model_config = ConfigDict(frozen=True)

    concept_code: str
    """The code the served CodeSystem publishes the option under - what the contract asks for."""

    option_uid: str
    option_code: str | None = None
    """The DHIS2 option code, when the artifacts carry it; None when only the UID is recoverable."""

    @property
    def wire_value(self) -> str:
        """What a DHIS2 data value stores for this option: its code, falling back to its UID."""
        return self.option_code or self.option_uid


class ResolvedOption(BaseModel):
    """One option a received code resolved to, and which spelling of it matched."""

    model_config = ConfigDict(frozen=True)

    entry: OptionEntry
    matched_by: str
    """`concept-code`, `option-uid`, or `option-code` - which of the three tiers the code hit."""

    @property
    def matched_contract_spelling(self) -> bool:
        """Whether the received code was the concept code the contract asks for, rather than a fall-back."""
        return self.matched_by == CONCEPT_CODE_TIER


class OptionLookup(BaseModel):
    """The outcome of resolving one received code against a served option table.

    Exactly one of the three states holds: `option` set is a resolution, `ambiguous_option_uids`
    non-empty is a code the table carries more than once at one tier, and both empty is a code
    the table does not carry at all.
    """

    model_config = ConfigDict(frozen=True)

    option: ResolvedOption | None = None
    ambiguous_option_uids: tuple[str, ...] = ()


class OptionTable(BaseModel):
    """Every option of one served CodeSystem, resolvable by each of the three spellings it can arrive as.

    The table is the inverse of what the terminology target emitted. Under
    `concept_code_source = "id"` the concept code is the option UID and the `dhis2-code` property
    carries the DHIS2 code; under `"code"` the concept code is the DHIS2 code and the `dhis2-id`
    property carries the UID. Both spellings identify the same option, which is why a lenient
    resolution accepts either and notes what it did.
    """

    model_config = ConfigDict(frozen=True)

    system: str
    entries: tuple[OptionEntry, ...] = ()


class QuestionSpec(BaseModel):
    """One answerable question of a served form, as the translator writes its DHIS2 data value.

    `data_element_uid` and `category_option_combo_uid` come straight from the link-id grammar:
    a plain question's link id is the data element UID, and a disaggregated aggregate cell's is
    `<dataElement>.<categoryOptionCombo>` - the very key a DHIS2 data value carries. A tracker
    registration form asks tracked entity attributes rather than data elements, and its link ids
    are attribute UIDs, so `data_element_uid` is the attribute a `TrackerAttribute` is keyed by.
    """

    model_config = ConfigDict(frozen=True)

    link_id: str
    data_element_uid: str
    category_option_combo_uid: str | None = None
    item_type: str
    answer_element: str
    wire_kind: WireValueKind
    repeats: bool = False
    option_system: str | None = None
    """Canonical of the CodeSystem a coded answer resolves against, or None when the binding is open."""

    value_type: str | None = None
    """The DHIS2 value type behind the question, when the caller supplied one; the compiled IG publishes none."""


class FormSpec(BaseModel):
    """One served Questionnaire flattened into what a response answering it translates through.

    `attribute_option_combo_value_set` is the vocabulary the form's `D2AttributeOptionCombos`
    extension declares, and its presence is what makes the response-side extension required: a
    data set on the default category combo declares none, and its values are keyed under the one
    attribute option combo it has.
    """

    model_config = ConfigDict(frozen=True)

    canonical: str
    form_kind: FormKind
    target_kind: ConversionTargetKind
    data_set_uid: str | None = None
    program_uid: str | None = None
    program_stage_uid: str | None = None
    tracked_entity_type_uid: str | None = None
    """The DHIS2 type a registration form enrols a person as, off the form's `$DHIS2-TET` identifier."""

    questions: dict[str, QuestionSpec] = Field(default_factory=dict)
    group_link_ids: frozenset[str] = frozenset()
    attribute_option_combo_value_set: str | None = None
    """Canonical of the ValueSet the form declares its responses key their values from, or None."""

    attribute_option_combo_system: str | None = None
    """Canonical of the CodeSystem behind that ValueSet, or None when the context does not carry it."""


class ConversionContext(BaseModel):
    """Everything the QR -> DHIS2 translator reads besides the response itself.

    Assembled once from the compiled IG artifacts - the served Questionnaires, the option-set
    CodeSystems (and their ConceptMaps, where a code-mode guide needs them), the ValueSets that
    bind the two, and the published Locations - plus the two dials a run chooses: how exactly a
    coded answer has to name its concept, and which IANA zone DHIS2's zone-less timestamps are
    wall-clock readings in.
    """

    model_config = ConfigDict(frozen=True)

    naming: ConversionNaming
    forms: dict[str, FormSpec] = Field(default_factory=dict)
    """Every served form, keyed by the questionnaire canonical a response names it under."""

    option_tables: dict[str, OptionTable] = Field(default_factory=dict)
    """Every served option terminology, keyed by its CodeSystem canonical."""

    organisation_unit_uids_by_location_id: dict[str, str] = Field(default_factory=dict)
    """The DHIS2 UID behind every published Location id - a code stem under code-or-id naming."""

    coded_answer_mode: CodedAnswerMode = CodedAnswerMode.LENIENT
    timezone: str | None = None

    @property
    def resolves_organisation_units(self) -> bool:
        """Whether the context was given a Location table to resolve organisation-unit references through."""
        return bool(self.organisation_unit_uids_by_location_id)


class ConversionResult(BaseModel):
    """What one QuestionnaireResponse translated into: a payload, or the reasons there is none.

    Exactly one of `data_value_set`, `event`, and `tracked_entity` is set when `refusals` is empty,
    and `target_kind` names which. A refused response carries none of them: a response the
    translator cannot read whole produces a named refusal rather than a partial payload that would
    import the half of itself that happened to parse.
    """

    model_config = ConfigDict(frozen=True)

    response_id: str | None = None
    questionnaire: str | None = None
    target_kind: ConversionTargetKind | None = None
    data_value_set: DataValueSet | None = None
    event: TrackerEvent | None = None
    tracked_entity: TrackerTrackedEntity | None = None
    """The person and the enrollment a registration response creates, carried whole for one `/api/tracker` post."""

    notes: tuple[ConversionNote, ...] = ()
    refusals: tuple[ConversionRefusal, ...] = ()

    @property
    def is_refused(self) -> bool:
        """Whether the response produced a refusal instead of a payload."""
        return bool(self.refusals)


class ConversionReport(BaseModel):
    """The outcome of translating a batch of spooled responses, in the order they were drained.

    The order here is the spool's, not the posting order: a caller draining into DHIS2 posts
    `FORWARD_TARGET_ORDER` so a registration lands before the stage events of the same drain.
    """

    model_config = ConfigDict(frozen=True)

    results: tuple[ConversionResult, ...] = ()

    @property
    def translated(self) -> tuple[ConversionResult, ...]:
        """Every response that produced a payload."""
        return tuple(result for result in self.results if not result.is_refused)

    @property
    def refused(self) -> tuple[ConversionResult, ...]:
        """Every response that produced a refusal."""
        return tuple(result for result in self.results if result.is_refused)

    @property
    def data_value_sets(self) -> tuple[DataValueSet, ...]:
        """Every aggregate envelope the batch produced, ready to post to `/api/dataValueSets`."""
        return tuple(result.data_value_set for result in self.results if result.data_value_set is not None)

    @property
    def events(self) -> tuple[TrackerEvent, ...]:
        """Every event the batch produced, ready to post to `/api/tracker`."""
        return tuple(result.event for result in self.results if result.event is not None)

    @property
    def tracked_entities(self) -> tuple[TrackerTrackedEntity, ...]:
        """Every registration the batch produced, ready to post to `/api/tracker` before its events."""
        return tuple(result.tracked_entity for result in self.results if result.tracked_entity is not None)
