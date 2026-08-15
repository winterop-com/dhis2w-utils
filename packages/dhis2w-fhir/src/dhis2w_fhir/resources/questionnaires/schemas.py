"""Questionnaire schemas: the target selection, the emitter projections, and the derived FSH names."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.attributes import AttributeValueIn
from dhis2w_fhir.i18n import (
    ENROLLMENT_DATE_LABEL_PROPERTY,
    EXECUTION_DATE_LABEL_PROPERTY,
    INCIDENT_DATE_LABEL_PROPERTY,
    TranslationIn,
    composed_translations,
    name_translations,
    property_translations,
)
from dhis2w_fhir.names import (
    FHIR_ID_MAX_LENGTH,
    NamingSource,
    StemResolution,
    StemSubject,
    bounded_slug,
    join_id_tokens,
    join_name_segments,
    resolve_identity_stems,
)
from dhis2w_fhir.notes import GenerateNote, GenerateNoteCategory, aggregate_generate_note
from dhis2w_fhir.r4 import DEFAULT_SUBJECT_RESOURCE_TYPE

if TYPE_CHECKING:
    from dhis2w_fhir.config import NamingConfig

#: The form kinds a Questionnaire is generated from, and the D2FormType code each carries.
#:
#: `tracked-entity` names the registration of a tracked entity that joins no program: DHIS2 accepts
#: a bare `trackedEntities` import under plain CREATE, and the person it creates is findable
#: without one. The code names the DHIS2 object the form creates, the way `aggregate` names the
#: shape a data set's values are filed in and `tracker-event` names one visit of an enrollment.
FormKind = Literal["aggregate", "event", "tracker", "tracker-event", "tracked-entity"]

#: The DHIS2 object a form kind's questions are asked from, which decides the support CodeSystem
#: an item's `code` is drawn from: a data set, an event program, and a tracker program stage all
#: ask data elements, while a tracker registration form and a tracked entity type's own form ask
#: tracked entity attributes.
QuestionSubject = Literal["data-element", "tracked-entity-attribute"]

#: The trailing token every organisation-unit assignment List id ends in, after the token and stem.
ASSIGNMENT_ID_SUFFIX = "org-units"

#: The standard R4 extensions constraining the range a numeric question's answer may take.
MINIMUM_VALUE_EXTENSION_URL = "http://hl7.org/fhir/StructureDefinition/minValue"
MAXIMUM_VALUE_EXTENSION_URL = "http://hl7.org/fhir/StructureDefinition/maxValue"

#: The FHIR `Questionnaire.item.type` each DHIS2 value type answers as. Every member of the
#: generated `ValueType` enum on v41, v42, and v43 has an entry here, and a guard test asserts
#: that - so a codegen refresh introducing a new DHIS2 value type is a deliberate mapping
#: decision rather than a silent fall-through to string. The keys stay plain strings, and
#: `_DEFAULT_ITEM_TYPE` still catches an unknown value at runtime: an instance ahead of the
#: generated tree must not crash generation.
ITEM_TYPES_BY_VALUE_TYPE = {
    # Text and text-shaped values. R4 offers no finer item type than `string` for a letter, a
    # phone number, an email, or a username, so they are mapped explicitly rather than by default.
    "TEXT": "string",
    "LONG_TEXT": "text",
    "LETTER": "string",
    "PHONE_NUMBER": "string",
    "EMAIL": "string",
    "USERNAME": "string",
    "MULTI_TEXT": "string",
    # Numbers.
    "NUMBER": "decimal",
    "INTEGER": "integer",
    "INTEGER_POSITIVE": "integer",
    "INTEGER_NEGATIVE": "integer",
    "INTEGER_ZERO_OR_POSITIVE": "integer",
    "PERCENTAGE": "decimal",
    "UNIT_INTERVAL": "decimal",
    # Booleans.
    "BOOLEAN": "boolean",
    "TRUE_ONLY": "boolean",
    # Temporals. `AGE` is a date on the wire - DHIS2 stores the date of birth and renders the
    # age from it, so the age is a display concern and the date is the captured value.
    "DATE": "date",
    "DATETIME": "dateTime",
    "TIME": "time",
    "AGE": "date",
    # Web and binary values.
    "URL": "url",
    "FILE_RESOURCE": "attachment",
    "IMAGE": "attachment",
    # Geography. GeoJSON is a document, not a coordinate pair; `COORDINATE` is DHIS2's
    # `[lon,lat]` string, which no R4 item type expresses.
    "GEOJSON": "text",
    "COORDINATE": "string",
    # References. Only the organisation unit resolves to a FHIR resource; the other two
    # carry a bare UID - this guide publishes no FHIR resource for the referenced object.
    "ORGANISATION_UNIT": "reference",
    "REFERENCE": "string",
    "TRACKER_ASSOCIATE": "string",
}

#: The `value[x]` element a bound lands on, keyed by the item type the question answers as. A
#: question answering as anything else - a `#choice` bound to an option set, say - takes no
#: bound at all, because there is no numeric element on it to constrain.
BOUND_ELEMENTS_BY_ITEM_TYPE = {"integer": "valueInteger", "decimal": "valueDecimal"}

#: What an unmapped value type answers as - reached only by a DHIS2 value type newer than the
#: generated enums, since the table above covers every member of all three.
_DEFAULT_ITEM_TYPE = "string"


class FormKindProfile(BaseModel):
    """What one form kind contributes to its Questionnaire: identifier systems, subject type, and prose label.

    The identifier system is carried twice because the two emitters spell it differently and
    must never disagree: the FSH path writes the `$DHIS2-*` alias `foundation/d2-aliases.fsh`
    declares, and the JSON path writes the absolute URL that alias expands to,
    `{identifier_system_base}/id/{segment}`. A guard test renders the alias file and asserts
    every pair still resolves to the same system.

    `subject_type` is the resource type a form of this kind is answered about when the project
    says nothing else. It is the whole answer on the two organisation-unit kinds and the default
    on the three tracked-entity kinds, where `[generate.tracked_entity_types]` maps a tracked
    entity type onto the resource type it really is; `form_subject_type` is where the two meet.

    `assigned` states whether DHIS2 scopes the form to organisation units. A data set and a
    program carry an assignment, so a form of theirs may publish an assignment `List`; a tracked
    entity type carries none, so every organisation unit the registry publishes may register one.
    """

    model_config = ConfigDict(frozen=True)

    identifier_system: str
    identifier_code_system: str
    identifier_segment: str
    code_identifier_segment: str
    subject_type: str
    label: str
    question_subject: QuestionSubject = "data-element"
    assigned: bool = True


#: The DHIS2 identifier systems, subject type, and prose label each form kind carries. An aggregate
#: or event form is reported for an organisation unit, while a tracker registration form enrols one
#: tracked entity and a tracker program stage captures that entity's visit, so the subject of both
#: tracker forms is whatever the program's tracked entity type is - a person unless the project
#: says otherwise. The registration form is the tracker program's own form, so it rides the
#: program's identifier systems - the very ones its stage forms carry as a grouping identifier.
FORM_KIND_PROFILES: dict[FormKind, FormKindProfile] = {
    "aggregate": FormKindProfile(
        identifier_system="$DHIS2-DS",
        identifier_code_system="$DHIS2-DS-CODE",
        identifier_segment="data-set",
        code_identifier_segment="data-set-code",
        subject_type="Location",
        label="data set",
    ),
    "event": FormKindProfile(
        identifier_system="$DHIS2-PROGRAM",
        identifier_code_system="$DHIS2-PROGRAM-CODE",
        identifier_segment="program",
        code_identifier_segment="program-code",
        subject_type="Location",
        label="event program",
    ),
    "tracker": FormKindProfile(
        identifier_system="$DHIS2-PROGRAM",
        identifier_code_system="$DHIS2-PROGRAM-CODE",
        identifier_segment="program",
        code_identifier_segment="program-code",
        subject_type=DEFAULT_SUBJECT_RESOURCE_TYPE,
        label="tracker program",
        question_subject="tracked-entity-attribute",
    ),
    "tracker-event": FormKindProfile(
        identifier_system="$DHIS2-PS",
        identifier_code_system="$DHIS2-PS-CODE",
        identifier_segment="program-stage",
        code_identifier_segment="program-stage-code",
        subject_type=DEFAULT_SUBJECT_RESOURCE_TYPE,
        label="tracker program stage",
    ),
    "tracked-entity": FormKindProfile(
        identifier_system="$DHIS2-TET",
        identifier_code_system="$DHIS2-TET-CODE",
        identifier_segment="tracked-entity-type",
        code_identifier_segment="tracked-entity-type-code",
        subject_type=DEFAULT_SUBJECT_RESOURCE_TYPE,
        label="tracked entity type",
        question_subject="tracked-entity-attribute",
        assigned=False,
    ),
}

#: The form kinds a capture server accepts a response for and the translator turns into a DHIS2
#: payload. Every generated kind is one: an aggregate response becomes a `/api/dataValueSets`
#: envelope, an event and a tracker-event response become one `/api/tracker` event each, a
#: registration response becomes the `/api/tracker` tracked entity and enrollment it mints, and a
#: tracked-entity response becomes that same tracked entity with no enrollment on it. The tuple
#: stays the single switch the capture surface keys off - serve's index, the conversion gate, the
#: `supportedProfile` declarations, `/metadata`, and the load set all read it.
CAPTURED_FORM_KINDS: tuple[FormKind, ...] = ("aggregate", "event", "tracker", "tracker-event", "tracked-entity")


class TargetSelection(BaseModel):
    """Which DHIS2 objects a data-definition target covers - one table per form kind.

    UIDs only: names are not unique in DHIS2. An empty (or absent) list means all, as it does
    for the terminology targets; a non-empty list filters. Four tables select the form kinds:
    `[generate.data_sets]` picks data sets, `[generate.event_programs]` picks programs without
    registration, `[generate.tracker_programs]` picks programs with registration, and
    `[generate.tracked_entity_forms]` picks the tracked entity types that publish a person-only
    registration form. The whole-instance sweep routes each program to its table by its DHIS2
    `programType`, so a program listed under the table its type does not belong to is refused by
    name.

    `[generate.tracked_entity_forms]` is the one table whose empty default is not the whole
    instance: it is the tracked entity types the selected tracker programs already track, so a
    project selecting programs gets a person-only form for each kind of person those programs
    register and nothing else.
    """

    model_config = ConfigDict(extra="forbid")

    include_ids: list[str] = Field(default_factory=list)


class SupportTerminologyProfile(BaseModel):
    """The fixed prose one data-dictionary support pair publishes under, shared by both emitters.

    The FSH target quotes these into `support-terminology.fsh.jinja` and the JSON target writes
    them onto the built `CodeSystem` and `ValueSet`, so the compiled guide and the served
    documents describe the same terminology in the same words.

    `value_type_property_description` is per-pair because the two pairs that declare a value type
    describe a different DHIS2 object; a pair whose concepts carry no value type never renders it.
    """

    model_config = ConfigDict(frozen=True)

    title: str
    description: str
    code_property_description: str
    value_type_property_description: str = ""


#: The support pair over every data element the generated questionnaires ask a question from.
DATA_ELEMENT_TERMINOLOGY = SupportTerminologyProfile(
    title="DHIS2 data elements",
    description=(
        "DHIS2 data elements captured by the generated questionnaires. Concept codes are DHIS2 data element UIDs."
    ),
    code_property_description="DHIS2 data element code.",
    value_type_property_description="DHIS2 data element value type.",
)

#: The support pair over every tracked entity attribute the generated registration forms ask about.
TRACKED_ENTITY_ATTRIBUTE_TERMINOLOGY = SupportTerminologyProfile(
    title="DHIS2 tracked entity attributes",
    description=(
        "DHIS2 tracked entity attributes captured by the generated tracker registration forms. "
        "Concept codes are DHIS2 tracked entity attribute UIDs."
    ),
    code_property_description="DHIS2 tracked entity attribute code.",
    value_type_property_description="DHIS2 tracked entity attribute value type.",
)

#: The support pair over every tracked entity type the generated forms register an entity as.
TRACKED_ENTITY_TYPE_TERMINOLOGY = SupportTerminologyProfile(
    title="DHIS2 tracked entity types",
    description=(
        "DHIS2 tracked entity types the generated forms register an entity as. "
        "Concept codes are DHIS2 tracked entity type UIDs."
    ),
    code_property_description="DHIS2 tracked entity type code.",
)

#: The prose the tracked-entity-type resource map is published under - what it maps and what a
#: type nobody mapped lands on. `[generate.tracked_entity_types]` is exceptions-only, so the map
#: is where the whole resolution is readable: a consumer holding a type UID reads the resource its
#: registrations are published as without holding the project's `fhir.toml`.
TRACKED_ENTITY_TYPE_RESOURCE_MAP_TITLE = "DHIS2 tracked entity types as FHIR resource types"
TRACKED_ENTITY_TYPE_RESOURCE_MAP_DESCRIPTION = (
    "Every DHIS2 tracked entity type the generated forms register, mapped onto the FHIR resource type its "
    f"registrations are published as. A type this project maps to nothing is a {DEFAULT_SUBJECT_RESOURCE_TYPE}."
)

#: The R4 code system every FHIR resource type is a code of, which is what the resource map targets.
RESOURCE_TYPE_CODE_SYSTEM_URL = "http://hl7.org/fhir/resource-types"

#: The R4 value set holding that code system whole, which the map names as its target value set.
RESOURCE_TYPE_VALUE_SET_URL = "http://hl7.org/fhir/ValueSet/resource-types"

#: How closely a resource-map row holds, in the vocabulary the option-set and category maps use.
#: `equal`: the concept and the resource type name the same thing, since the type is what the
#: project has said its registrations are.
RESOURCE_MAP_EQUIVALENCE: Literal["equal"] = "equal"

#: The support pair over every category option combo the generated questionnaires disaggregate by.
CATEGORY_OPTION_COMBO_TERMINOLOGY = SupportTerminologyProfile(
    title="DHIS2 category option combos",
    description=(
        "DHIS2 category option combos the generated questionnaires disaggregate by. "
        "Concept codes are DHIS2 category option combo UIDs."
    ),
    code_property_description="DHIS2 category option combo code.",
)

#: The description of the `domain` concept property, which only the data-element pair declares.
DOMAIN_PROPERTY_DESCRIPTION = "DHIS2 data element domain type."

#: The description of the `unique` concept property, which only the attribute pair declares. A
#: unique tracked entity attribute is a business identifier - a national id, a case number - so a
#: consumer reading the vocabulary can tell which questions identify the person from which describe them.
#:
#: Uniqueness is a fact about the attribute alone: DHIS2 holds `unique` on the tracked entity
#: attribute itself, so it is the same answer in every form that asks it. Searchability is not,
#: which is why the property beside it is per context.
UNIQUE_PROPERTY_DESCRIPTION = "Whether DHIS2 declares the tracked entity attribute unique."

#: The concept property carrying whether an attribute is searchable anywhere the run publishes.
SEARCHABLE_PROPERTY = "searchable"

#: The description of the `searchable` concept property, which only the attribute pair declares.
SEARCHABLE_PROPERTY_DESCRIPTION = (
    "Whether DHIS2 declares the tracked entity attribute searchable in any context this guide publishes."
)

#: The concept property carrying whether DHIS2 mints the attribute's value itself.
GENERATED_PROPERTY = "generated"

#: The description of the `generated` concept property, which only the attribute pair declares. A
#: generated attribute is one DHIS2 writes for you off a reserved-value pattern - a national
#: identifier, a case number - so a capture client asks nobody for it, and the question the forms
#: publish for it is read-only.
GENERATED_PROPERTY_DESCRIPTION = "Whether DHIS2 mints the tracked entity attribute's value itself."

#: The concept property carrying the reserved-value pattern a generated attribute is minted from.
PATTERN_PROPERTY = "pattern"

#: The description of the `pattern` concept property, carried only by a generated attribute: an
#: attribute nobody generates has no pattern to state, and DHIS2 sends an empty string for it.
PATTERN_PROPERTY_DESCRIPTION = "The DHIS2 reserved-value pattern a generated tracked entity attribute is minted from."

#: The concept property carrying whether an attribute is shown in the person lists DHIS2 renders.
DISPLAY_IN_LIST_PROPERTY = "display-in-list"

#: The description of the `display-in-list` concept property. DHIS2 holds the flag on the join
#: between a form's own object and the attribute, exactly as it holds `searchable` there, so the
#: dictionary states the roll-up over every context this run publishes rather than pretending the
#: answer is a fact about the attribute alone.
DISPLAY_IN_LIST_PROPERTY_DESCRIPTION = (
    "Whether DHIS2 shows the tracked entity attribute in the working lists of any context this guide publishes."
)

#: How a per-context searchability property spells the context it answers for: the property code
#: is this token joined to the DHIS2 UID of the form's own object - a program for a registration
#: form, a tracked entity type for a person-only form.
SEARCHABLE_CONTEXT_PROPERTY_PREFIX = "searchable-"


def searchable_context_property(context_uid: str) -> str:
    """The concept property code carrying one context's searchability answer (e.g. `searchable-IpHINAT79UW`)."""
    return f"{SEARCHABLE_CONTEXT_PROPERTY_PREFIX}{context_uid}"


class AttributeSearchContext(BaseModel):
    """One context's answer to whether a tracked entity attribute is searchable in it.

    A context is the DHIS2 object whose form asks the attribute: a tracker program for a
    registration form, a tracked entity type for a person-only one. Two programs disagree about
    the same attribute - on the DHIS2 demo database `Child Programme` and `Antenatal care` do -
    so a single boolean would state one of them and lie about the other.
    """

    model_config = ConfigDict(frozen=True)

    context_uid: str
    context_label: str
    searchable: bool

    @property
    def property_code(self) -> str:
        """The concept property code this context's answer is published under."""
        return searchable_context_property(self.context_uid)

    @property
    def description(self) -> str:
        """What the declaration of this context's property says it answers for."""
        return f"Whether DHIS2 declares the tracked entity attribute searchable in {self.context_label}."


class NumericBounds(BaseModel):
    """The inclusive range one DHIS2 numeric value type admits, either end open when DHIS2 leaves it open."""

    model_config = ConfigDict(frozen=True)

    minimum_value: int | None = None
    maximum_value: int | None = None


class CategoryOptionComboIn(BaseModel):
    """One category option combo of a data element's disaggregation.

    `category_option_uids` is what the combo is composed of - "Fixed, <1y" is the Fixed option met
    with the <1y option - which is what the published combo concepts decompose themselves into, one
    concept property per category axis.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    code: str | None = None
    category_option_uids: list[str] = Field(default_factory=list)


class CategoryAxisIn(BaseModel):
    """One category a combo splits over, with the category options DHIS2 declares it in order.

    Both lists DHIS2 answers here are ordered lists rather than the unordered sets BUGS.md #63 and
    #64 record: `categoryCombo.categories` and `category.categoryOptions` came back identical over
    25 consecutive reads of the local stack and 12 of play, in an order that is not alphabetical -
    "Location Fixed/Outreach" before "EPI/nutrition age", "Provide access to primary health care"
    before "Provide access to basic education". That is the order the DHIS2 data-entry app lays a
    disaggregated section out in, so it is the order the generated cells take.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    option_uids: list[str] = Field(default_factory=list)


class CategoryComboIn(BaseModel):
    """One DHIS2 category combo, its option combos included - a disaggregation or a data set's own key.

    A data element carries one to say how its question splits into cells; a data set carries one
    to say which attribute option combos its values are keyed under. `code` is the combo's DHIS2
    code, which the attribute-combo terminology resolves its identity stem from.

    `categories` is the ordered list of axes the combo splits over, each carrying its own declared
    category options. The category order is what DHIS2 reads an option combo's name in, so the
    decomposition properties follow it; the option order within each axis is what
    `ordered_option_combos` lays the cells out by.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    code: str | None = None
    is_default: bool = False
    categories: list[CategoryAxisIn] = Field(default_factory=list)
    option_combos: list[CategoryOptionComboIn] = Field(default_factory=list)

    @property
    def category_uids(self) -> list[str]:
        """The UIDs of the categories the combo splits over, in the order DHIS2 declares them."""
        return [axis.uid for axis in self.categories]


def ordered_option_combos(combo: CategoryComboIn) -> list[CategoryOptionComboIn]:
    """One combo's option combos in DHIS2's declared axis order - the grid the data-entry app renders.

    The sort key of a cell is where each of its category options sits in its own category's
    declared option list, read axis by axis in the combo's declared category order: "Fixed, <1y"
    sorts before "Fixed, >1y" before "Outreach, <1y", because location is the first axis and Fixed
    is its first option. A combo the projection could not resolve an axis for keeps its name and
    UID as the tie-break, which is also what orders two cells the declared arrays cannot separate -
    so the order is total, and regeneration stays byte-stable either way.
    """
    positions = [{option_uid: index for index, option_uid in enumerate(axis.option_uids)} for axis in combo.categories]

    def axis_position(axis: dict[str, int], option_uids: list[str]) -> int:
        """Where one cell sits along one axis, or after every declared option when the axis names none of them."""
        found = [axis[option_uid] for option_uid in option_uids if option_uid in axis]
        return min(found) if found else len(axis)

    def sort_key(option_combo: CategoryOptionComboIn) -> tuple[tuple[int, ...], str, str]:
        """The declared grid position of one cell, then its name and UID as the total-order tie-break."""
        along = tuple(axis_position(axis, option_combo.category_option_uids) for axis in positions)
        return (along, option_combo.name, option_combo.uid)

    return sorted(combo.option_combos, key=sort_key)


class QuestionnaireItemIn(BaseModel):
    """One data element or tracked entity attribute as a question: its value type, its option set, its disaggregation.

    `domain_type` is the DHIS2 `AGGREGATE` / `TRACKER` split a data element carries, emitted as a
    concept property on the data-element support CodeSystem. It is empty when the instance sent
    none, and a tracked entity attribute has no domain at all.

    `code` and `unique` are the tracked entity attribute's own facts: DHIS2 codes an attribute the
    way it codes every metadata object, and a unique attribute is a business identifier rather
    than a description. Both ride onto the attribute support CodeSystem as concept properties.

    `searchable` is the fact about the *pair* the way `entity_level` is: DHIS2 holds it on the
    join, so it is this form's answer about this attribute and no other form's. The dictionary
    publishes it per context rather than once per attribute for that reason.

    `entity_level` is the fact about the *pair* - this attribute on this program's tracked entity
    type - that decides where DHIS2 imports the answer: True when the attribute is one of the
    type's own `trackedEntityTypeAttributes`, so its value belongs on the tracked entity, False
    when the program asks it and the type does not collect it, so its value belongs on the
    enrollment. None means the fetch could not say, and every consumer then reads the answer as
    entity-level, which is what a form published before the fact was fetched states.

    A DHIS2 form makes a question mandatory at two grains, and the projection carries both:
    `compulsory` marks the data element itself (a registration form's `mandatory` attribute lands
    here too), and `required_option_combo_uids` marks the single disaggregated cells a data set
    names through a compulsory operand.

    `generated` and `pattern` are the tracked entity attribute's own facts about who writes the
    value: DHIS2 mints a generated attribute's value itself, following the reserved-value pattern,
    so the person filling the form must not be asked for it. A data element is never generated.

    `display_in_list` is a fact about the *pair* the way `searchable` is - DHIS2 holds it on the
    join between the form's object and the attribute - so it is this form's answer, and the
    dictionary rolls the answers of every published context into one property.

    `description` is the DHIS2 free text about the object, which is guidance for the person
    filling the form rather than the label on the question.

    `translations` is the object's own DHIS2 translation list, every property a question is
    labelled or described from: `NAME` names the dictionary concept, `FORM_NAME` labels the
    question where the object carries a form name, and `DESCRIPTION` translates the free text.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    code: str | None = None
    form_name: str | None = None
    description: str | None = None
    translations: list[TranslationIn] = Field(default_factory=list)
    value_type: str
    domain_type: str = ""
    option_set_uid: str | None = None
    compulsory: bool = False
    unique: bool = False
    searchable: bool = False
    generated: bool = False
    pattern: str | None = None
    display_in_list: bool = False
    entity_level: bool | None = None
    required_option_combo_uids: list[str] = Field(default_factory=list)
    category_combo: CategoryComboIn | None = None


def item_type(item: QuestionnaireItemIn) -> str:
    """The item type one question answers as: `choice` when option-set bound, else its value type's."""
    if item.option_set_uid is not None:
        return "choice"
    return value_type_item_type(item.value_type)


def value_type_item_type(value_type: str) -> str:
    """The item type one DHIS2 value type answers as, falling back to `string` for an unmapped one."""
    return ITEM_TYPES_BY_VALUE_TYPE.get(value_type, _DEFAULT_ITEM_TYPE)


class QuestionnaireSectionIn(BaseModel):
    """One section of a data-entry form, holding the data elements it groups.

    `description` is the DHIS2 free text about the section, which the group item carries as
    guidance the way a question carries its own object's.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    description: str | None = None
    translations: list[TranslationIn] = Field(default_factory=list)
    items: list[QuestionnaireItemIn] = Field(default_factory=list)


class ProgramContextIn(BaseModel):
    """The tracker program one stage belongs to.

    The identity its questionnaires carry in titles, identifiers, and intros. `code` is the
    program's DHIS2 code, which the stem plan resolves the program's directory segment from.
    `tracked_entity_type_uid` is what the program tracks, which is what decides the subject type
    of every stage form of the program - a stage captures a visit by the very entity the
    registration form enrolled, so the two forms state the same subject.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    code: str | None = None
    translations: list[TranslationIn] = Field(default_factory=list)
    tracked_entity_type_uid: str | None = None


class ProgramRuleVariableIn(BaseModel):
    """One program rule variable: the name a condition writes as `#{name}` and the question it reads.

    `source_type` is the DHIS2 `programRuleVariableSourceType`, which says which event's value the
    variable holds. Only the three that read one question of the form being filled are translatable
    - the current event's data element, the newest event of the program's, and a tracked entity
    attribute - and even those are only faithful where the question is asked on the same form.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    source_type: str
    data_element_uid: str | None = None
    tracked_entity_attribute_uid: str | None = None

    @property
    def question_uid(self) -> str | None:
        """The UID of the question the variable reads, or None when it reads no single question."""
        return self.data_element_uid or self.tracked_entity_attribute_uid


class ProgramRuleActionIn(BaseModel):
    """One action a program rule takes when its condition holds: what kind, and which question it lands on."""

    model_config = ConfigDict(frozen=True)

    action_type: str
    data_element_uid: str | None = None
    tracked_entity_attribute_uid: str | None = None

    @property
    def question_uid(self) -> str | None:
        """The UID of the question the action lands on, or None when it names no question."""
        return self.data_element_uid or self.tracked_entity_attribute_uid


class ProgramRuleIn(BaseModel):
    """One DHIS2 program rule: the expression the server evaluates and the actions it takes.

    `condition` is the DHIS2 expression exactly as the instance holds it. It is never reformatted:
    a consumer reading the rule this form could not express needs the text the server evaluates,
    and a prettified expression is a different string from the one an administrator can search for.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    description: str | None = None
    condition: str
    translations: list[TranslationIn] = Field(default_factory=list)
    actions: list[ProgramRuleActionIn] = Field(default_factory=list)


class QuestionnaireSourceIn(BaseModel):
    """One DHIS2 data set, event program, or tracker program stage as the projection the emitter consumes.

    `sections` carries the form when it has them and `flat_items` carries the rest, so a
    sectioned form fills the first, an unsectioned form the second, and a form that mixes
    the two fills both (the service notes that). Both empty is a degenerate form with no
    data elements. `period_type` is the data set's DHIS2 reporting period type, which the
    example target resolves its periods from; a program form carries none. `description`
    is the DHIS2 free text, which the narrative pages carry into the form's intro.

    `program` is set exactly when `kind` is `tracker-event`: the source is then one program
    stage, so `uid`, `name`, `code`, and `description` are the stage's own and `program`
    names the tracker program the stage belongs to. A `tracker` source names no program because
    it *is* one: the registration form is the tracker program's own form, so `uid`, `name`, and
    `code` are the program's and its questions are the program's tracked entity attributes.

    `attribute_combo` is the data set's own category combo - the third key of every value it
    holds, beside the organisation unit and the period. Only an aggregate form carries one, and
    a non-default one is what makes the form publish an attribute-option-combo vocabulary and
    its responses name a combo out of it.

    `displays_incident_date` is the tracker program's `displayIncidentDate`, which says whether an
    enrollment states the date of the incident it tracks beside the date it began. Only a `tracker`
    source carries it, and it is what makes a registration response carry the incident-date extension.

    The three date labels are the words the instance puts on the dates the form captures, each
    carried only where DHIS2 states one. A tracker registration form reads its program's
    `enrollmentDateLabel` and `incidentDateLabel`; a program stage form and an event program form
    read the stage's `executionDateLabel`, which is the date the event happened.

    `repeatable` is the program stage's own flag - whether one enrollment may capture the stage
    more than once. Only a `tracker-event` source carries it, and it carries it either way.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    code: str | None = None
    description: str | None = None
    translations: list[TranslationIn] = Field(default_factory=list)
    kind: FormKind
    period_type: str | None = None
    program: ProgramContextIn | None = None
    attribute_combo: CategoryComboIn | None = None
    displays_incident_date: bool = False
    enrollment_date_label: str | None = None
    incident_date_label: str | None = None
    event_date_label: str | None = None
    date_label_translations: list[TranslationIn] = Field(default_factory=list)
    """The translations of whichever object states the labels - the program's, or the stage's."""

    repeatable: bool | None = None
    tracked_entity_type_uid: str | None = None
    """The DHIS2 tracked entity type a registration or person-only form registers an entity as.

    None on the two organisation-unit kinds. A `tracked-entity` source *is* its type, so the value
    repeats `uid`; a stage form of a program carries it on `program` instead, because a stage
    belongs to the program rather than being it. `form_tracked_entity_type_uid` reads whichever of
    the three a form holds.
    """

    sections: list[QuestionnaireSectionIn] = Field(default_factory=list)
    flat_items: list[QuestionnaireItemIn] = Field(default_factory=list)
    attribute_values: list[AttributeValueIn] = Field(default_factory=list)
    program_rules: list[ProgramRuleIn] = Field(default_factory=list)
    """The rules DHIS2 enforces over the program this form belongs to, in the instance's own order.

    A program's rules are the program's, not one stage's, so every form a program publishes carries
    the whole list: a consumer holding one form learns from that form alone which rules the server
    will refuse its answers under. An aggregate form carries none - DHIS2 states program rules over
    programs only.
    """

    program_rule_variables: list[ProgramRuleVariableIn] = Field(default_factory=list)
    """The variables the program's rule conditions read, which name the questions a condition tests."""


class ReferencedObjects(BaseModel):
    """The DHIS2 objects one run's forms reference, gathered into the data dictionary both emitters publish.

    One entry per support pair: the data elements the questions are asked from, the tracked entity
    attributes the forms that ask them ask about, and the category option combos the aggregate
    forms disaggregate by. Each is keyed by UID and holds the first projection that named it, so
    a data element two data sets share becomes one concept rather than two.

    `search_contexts` is the exception to first-projection-wins, because searchability is not a
    fact about the attribute alone: it holds every context that asked the attribute, in the order
    the run reached them, so the dictionary publishes one answer per context and one roll-up over
    the lot.
    """

    data_elements: dict[str, QuestionnaireItemIn] = Field(default_factory=dict)
    tracked_entity_attributes: dict[str, QuestionnaireItemIn] = Field(default_factory=dict)
    option_combos: dict[str, CategoryOptionComboIn] = Field(default_factory=dict)
    search_contexts: dict[str, list[AttributeSearchContext]] = Field(default_factory=dict)
    display_in_list: dict[str, bool] = Field(default_factory=dict)
    """Whether any context that asked an attribute shows it in its working lists, rolled up per attribute."""

    def searchable_anywhere(self, attribute_uid: str) -> bool:
        """Whether any context this run publishes declares the attribute searchable."""
        return any(context.searchable for context in self.search_contexts.get(attribute_uid, []))

    def displayed_in_list_anywhere(self, attribute_uid: str) -> bool:
        """Whether any context this run publishes shows the attribute in its working lists."""
        return self.display_in_list.get(attribute_uid, False)

    def contexts_for(self, attribute_uid: str) -> list[AttributeSearchContext]:
        """Every context that asked one attribute, in the order the run reached them."""
        return self.search_contexts.get(attribute_uid, [])


def source_program(source: QuestionnaireSourceIn) -> ProgramContextIn:
    """The tracker program one source belongs to: a registration form's own identity, else its stage's program."""
    if source.kind == "tracker":
        return ProgramContextIn(
            uid=source.uid,
            name=source.name,
            code=source.code,
            tracked_entity_type_uid=source.tracked_entity_type_uid,
        )
    if source.program is None:
        raise ValueError(
            f"tracker-event source {source.uid} carries no program context: a program stage is named, "
            "grouped, and filed under the tracker program it belongs to"
        )
    return source.program


#: What joins a program stage's two identities into the one name its form is shown under.
DISPLAY_NAME_SEPARATOR = " - "


def source_display_name(source: QuestionnaireSourceIn) -> str:
    """The name one form is shown under: a program stage carries both identities, everything else its own."""
    if source.program is None:
        return source.name
    return f"{source.program.name}{DISPLAY_NAME_SEPARATOR}{source.name}"


def source_title_translations(source: QuestionnaireSourceIn, locales: list[str]) -> list[TranslationIn]:
    """The translations of the name one form is shown under, composed the way the name itself is.

    A program stage's title is `<program> - <stage>`, so a locale reaches the title only by
    translating both halves: `composed_translations` keeps the locales every part carries and drops
    the rest rather than pairing a translated stage with an untranslated program.
    """
    own = name_translations(source.translations, locales)
    if source.program is None:
        return own
    program = name_translations(source.program.translations, locales)
    return composed_translations([program, own], DISPLAY_NAME_SEPARATOR)


class DateLabelIn(BaseModel):
    """One date label a form states: the words the instance holds, and their translations."""

    model_config = ConfigDict(frozen=True)

    value: str
    translations: list[TranslationIn] = Field(default_factory=list)


class FormDateLabels(BaseModel):
    """The words one form's instance puts on the dates it captures, each absent where DHIS2 states none."""

    model_config = ConfigDict(frozen=True)

    enrollment_date: DateLabelIn | None = None
    incident_date: DateLabelIn | None = None
    event_date: DateLabelIn | None = None

    @property
    def stated(self) -> bool:
        """Whether the instance labelled any of the three, and the form therefore carries the extension."""
        return any((self.enrollment_date, self.incident_date, self.event_date))


def form_date_labels(source: QuestionnaireSourceIn, locales: list[str]) -> FormDateLabels:
    """The date labels one form publishes, read off whichever DHIS2 object states each of them.

    A tracker registration form enrols a person, so it states the enrollment and incident labels
    its program holds. A tracker program stage form and an event program form capture an event, so
    each states the event label the stage holds - `executionDateLabel`, which is the date DHIS2
    files the event under. A data set and a person-only registration form label no date: neither
    captures an event, and neither creates an enrollment.
    """
    if source.kind == "tracker":
        return FormDateLabels(
            enrollment_date=_date_label(
                source.enrollment_date_label,
                source.date_label_translations,
                locales,
                ENROLLMENT_DATE_LABEL_PROPERTY,
            ),
            incident_date=_date_label(
                source.incident_date_label, source.date_label_translations, locales, INCIDENT_DATE_LABEL_PROPERTY
            ),
        )
    if source.kind in {"event", "tracker-event"}:
        return FormDateLabels(
            event_date=_date_label(
                source.event_date_label, source.date_label_translations, locales, EXECUTION_DATE_LABEL_PROPERTY
            )
        )
    return FormDateLabels()


def _date_label(
    value: str | None, translations: list[TranslationIn], locales: list[str], property_name: str
) -> DateLabelIn | None:
    """One label as the projection both emitters write, or None when the instance states none."""
    if not value:
        return None
    return DateLabelIn(value=value, translations=property_translations(translations, locales, property_name))


def form_period_type(source: QuestionnaireSourceIn) -> str | None:
    """The DHIS2 period type one form declares, or None when its kind has no reporting frequency.

    Only a data set states one, and it states it whenever the instance holds one: the period type
    is what decides the ISO period format every response of the form has to report under, so a
    client resolving the form knows what to build before it builds one. A data set the instance
    left without a period type declares nothing rather than guessing a frequency for it.
    """
    if source.kind != "aggregate":
        return None
    return source.period_type or None


def form_repeatable(source: QuestionnaireSourceIn) -> bool | None:
    """Whether one enrollment may capture this form more than once, or None off the stage kind.

    Only a tracker program stage repeats: DHIS2 holds the flag on the stage, and a stage of a
    tracker program is the one form whose subject can answer it twice. Every other kind states
    nothing - an aggregate form is keyed by its period, an event program's events stand alone, and
    a registration form is answered once per person it enrols.
    """
    if source.kind != "tracker-event":
        return None
    return bool(source.repeatable)


def question_read_only(item: QuestionnaireItemIn, kind: FormKind) -> bool | None:
    """Whether DHIS2 writes one question's answer itself, or None when the person filling the form does.

    A generated tracked entity attribute is minted by DHIS2 off its reserved-value pattern - a
    national identifier, a case number - so asking a person to type one would invite them to
    contradict the instance. R4 says exactly this with `Questionnaire.item.readOnly`, so the fact
    rides the standard element rather than an extension of this guide's own. Every other question
    leaves the element off, because `readOnly = false` is what an absent element already means.
    """
    if FORM_KIND_PROFILES[kind].question_subject != "tracked-entity-attribute":
        return None
    return True if item.generated else None


def form_tracked_entity_type_uid(source: QuestionnaireSourceIn) -> str | None:
    """The DHIS2 tracked entity type one form is about: the form's own, else its program's."""
    if source.kind in {"tracker", "tracked-entity"}:
        return source.tracked_entity_type_uid
    if source.kind == "tracker-event" and source.program is not None:
        return source.program.tracked_entity_type_uid
    return None


def tracked_entity_type_subject_type(uid: str, tracked_entity_types: Mapping[str, str]) -> str:
    """The FHIR resource type one DHIS2 tracked entity type's registrations are published as.

    The whole rule, in one expression: `[generate.tracked_entity_types]` where the project states
    a type, `Patient` where it states nothing. Every consumer reads the resolution through here -
    the `subjectType` of a registration or person-only form, the `subject.type` of its examples,
    and the resource map the guide publishes over the type vocabulary - so a type's resource is
    one fact rather than a rule copied per surface.
    """
    return tracked_entity_types.get(uid, DEFAULT_SUBJECT_RESOURCE_TYPE)


def form_subject_type(source: QuestionnaireSourceIn, tracked_entity_types: Mapping[str, str]) -> str:
    """The FHIR resource type one form's subject is, resolved once for every consumer of the form.

    A DHIS2 tracked entity type is whatever the project tracks - a person, a household, a
    building, a herd - so `[generate.tracked_entity_types]` maps the type's UID onto the R4
    resource type it really is and every form of every program tracking it follows. A form about
    no tracked entity type keeps its own kind's subject: the reporting `Location` of the two
    organisation-unit kinds. A form that is about one reads `tracked_entity_type_subject_type`,
    which is the same call the published resource map is built from.

    The map is keyed by tracked entity type rather than by program because the type is what owns
    the nature of the thing: two programs tracking the same type agree by construction, and
    naming the type once is what makes a registration form and every stage form of that program
    state the same subject.
    """
    uid = form_tracked_entity_type_uid(source)
    if uid is None:
        return FORM_KIND_PROFILES[source.kind].subject_type
    return tracked_entity_type_subject_type(uid, tracked_entity_types)


class PublishedTrackedEntityType(BaseModel):
    """One DHIS2 tracked entity type the run publishes: its identity, its names, and the resource it is.

    The boundary object between the tracked-entity-type vocabulary and everything that reads it.
    `resource_type` is already resolved through `tracked_entity_type_subject_type`, so a concept,
    a mapping row, and a form's `subjectType` cannot state three different answers, and `mapped`
    says whether the project named the type or the default stood in - which is what the unmapped
    note counts without re-reading the config.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    code: str | None = None
    translations: list[TranslationIn] = Field(default_factory=list)
    resource_type: str
    mapped: bool

    @property
    def label(self) -> str:
        """The type as a note names it: the instance's own name, then the UID that disambiguates it."""
        return f"{self.name} ({self.uid})"


def published_tracked_entity_types(
    sources: list[QuestionnaireSourceIn], tracked_entity_types: Mapping[str, str]
) -> list[PublishedTrackedEntityType]:
    """The tracked entity types one run publishes a vocabulary over, in name order, resource already resolved.

    The set is the run's person-only forms: `[generate.tracked_entity_forms]` where it names
    anything, the types the selected tracker programs register where it does not. A person-only
    form *is* its type, so the form's projection carries the type's own UID, name, DHIS2 code, and
    translations - which is why the vocabulary needs no read of its own and every concept display
    is the name the instance holds rather than a word this project invented.
    """
    published: dict[str, PublishedTrackedEntityType] = {}
    for source in sources:
        if source.kind != "tracked-entity":
            continue
        published.setdefault(
            source.uid,
            PublishedTrackedEntityType(
                uid=source.uid,
                name=source.name,
                code=source.code,
                translations=source.translations,
                resource_type=tracked_entity_type_subject_type(source.uid, tracked_entity_types),
                mapped=source.uid in tracked_entity_types,
            ),
        )
    return sorted(published.values(), key=lambda entry: (entry.name, entry.uid))


#: How many unmapped tracked entity types the note names before the rest are counted. Generous,
#: because the whole point of the note is that the reader writes one config line per type it names.
_UNMAPPED_TYPE_SAMPLE_SIZE = 20


def unmapped_tracked_entity_type_notes(published: list[PublishedTrackedEntityType]) -> list[GenerateNote]:
    """Say that several published types share the default resource, or nothing when at most one does.

    One unmapped type is the ordinary shape: a project tracking people alone maps nothing and every
    form of it is answered about a `Patient`, which is right. Two or more unmapped types is the
    shape worth a word, because they are being published as the same resource while the instance
    holds them apart - and a project tracking households, herds, or water points beside its people
    almost certainly meant to say so.
    """
    unmapped = [entry for entry in published if not entry.mapped]
    if len(unmapped) < 2:
        return []
    example = unmapped[0]
    return [
        aggregate_generate_note(
            GenerateNoteCategory.SELECTION_GAP,
            f"{len(unmapped)} tracked entity types the published forms register are absent from "
            f"[generate.tracked_entity_types], so all of them are published as {DEFAULT_SUBJECT_RESOURCE_TYPE}; map "
            f'the ones that are not people, one line each ({example.uid} = "{DEFAULT_SUBJECT_RESOURCE_TYPE}")',
            [entry.label for entry in unmapped],
            sample_size=_UNMAPPED_TYPE_SAMPLE_SIZE,
        )
    ]


#: The surface label questionnaire-target stem notes and refusals name their offenders under.
QUESTIONNAIRE_STEM_SURFACE = "questionnaire target"

#: The surface label tracker-program stem notes and refusals name their offenders under.
TRACKER_PROGRAM_STEM_SURFACE = "tracker program"


class QuestionnaireStemPlan(BaseModel):
    """The resolved identity stems of one run's questionnaire surface.

    `targets` covers the forms themselves - each stem is the Questionnaire's resource id, its
    canonical URL segment, its file name, and (pascal-collapsed) its FSH name segment. `programs`
    covers the tracker programs the stage files nest under, whose stem is a directory name only.
    Every emitter that names a questionnaire artifact - the FSH target, the JSON documents, the
    examples, the pages - reads this one plan, so the two paths cannot disagree on an identity.
    """

    model_config = ConfigDict(frozen=True)

    targets: StemResolution
    programs: StemResolution

    @property
    def notes(self) -> list[GenerateNote]:
        """The notes resolution raised across both surfaces, targets first."""
        return [*self.targets.notes, *self.programs.notes]


def plan_questionnaire_stems(sources: list[QuestionnaireSourceIn], source: NamingSource) -> QuestionnaireStemPlan:
    """Resolve the questionnaire surface's identity stems once per run - the single source every emitter reads.

    The form targets and the tracker programs resolve as separate surfaces, each over its full
    subject list in one call so the collision scan sees every peer: a target stem is a resource
    id and must be unique among the run's Questionnaires - data sets, event programs, and
    tracker stages together - while a program stem only names the directory its stages are filed
    under. Both stems ride bare, so the budget is the R4 id limit itself - the same number
    validate states for these surfaces.
    """
    target_subjects = [StemSubject(uid=item.uid, code=item.code, label=source_display_name(item)) for item in sources]
    programs: dict[str, ProgramContextIn] = {}
    for item in sources:
        if item.kind == "tracker":
            programs.setdefault(item.uid, source_program(item))
        elif item.program is not None:
            programs.setdefault(item.program.uid, item.program)
    program_subjects = [
        StemSubject(uid=program.uid, code=program.code, label=program.name) for program in programs.values()
    ]
    return QuestionnaireStemPlan(
        targets=resolve_identity_stems(
            target_subjects, source, QUESTIONNAIRE_STEM_SURFACE, max_stem_length=FHIR_ID_MAX_LENGTH
        ),
        programs=resolve_identity_stems(
            program_subjects, source, TRACKER_PROGRAM_STEM_SURFACE, max_stem_length=FHIR_ID_MAX_LENGTH
        ),
    )


class QuestionnaireNaming(BaseModel):
    """Derived FSH names and ids for questionnaire artifacts under the configurable naming tokens.

    Holds the four tokens it needs rather than the whole `[generate.naming]` table, so the
    emitter stays a leaf of the config document instead of a dependency of it. The data-element
    and category-option-combo support terminology takes the registry's fixed `DE` / `COC`
    tokens under the same prefix. Option-set names are not here at all: they are decided by
    `option_set_identities` over the whole selection and read from the identity plan.
    """

    model_config = ConfigDict(frozen=True)

    prefix: str
    data_set: str
    program: str
    program_stage: str
    tracked_entity_type: str

    @classmethod
    def from_naming(cls, naming: NamingConfig) -> QuestionnaireNaming:
        """Project the `[generate.naming]` table onto the tokens questionnaire artifacts use."""
        return cls(
            prefix=naming.prefix,
            data_set=naming.data_set,
            program=naming.program,
            program_stage=naming.program_stage,
            tracked_entity_type=naming.tracked_entity_type,
        )

    def source_token(self, kind: FormKind) -> str:
        """The naming token one form kind composes its name from (`DS`, `PR`, `PS`, `TET`).

        A tracker registration form takes the program token, because the form it names *is* the
        program's own form - `D2PR_<program>` is the form of program X whichever kind of program
        X is, while `D2PS_<stage>` is one visit of a tracker program. A person-only form takes the
        tracked entity type's token for the same reason: the form is the type.
        """
        return {
            "aggregate": self.data_set,
            "event": self.program,
            "tracker": self.program,
            "tracker-event": self.program_stage,
            "tracked-entity": self.tracked_entity_type,
        }[kind]

    def questionnaire_name(self, kind: FormKind, stem_segment: str) -> str:
        """Computational `Questionnaire.name` for one source (e.g. `D2DS_BfMAe6Itzgt`, `D2PS_A03MvHHogjR`).

        `stem_segment` is the FSH-name segment of the form's identity stem
        (`StemResolution.fsh_segment_for`): the DHIS2 id verbatim under `source = "id"`, the
        pascal-collapsed code where a code stem serves.
        """
        return join_name_segments(f"{self.prefix}{self.source_token(kind)}", stem_segment)

    def assignment_list_id(self, container_kind: str, stem: str, uid: str) -> str:
        """FHIR id of one form's assignment List (e.g. `d2-ds-BfMAe6Itzgt-org-units`).

        The List rides the stem of the object the assignment hangs on - the data set for an
        aggregate form, the program for an event form and for every stage of a tracker program -
        under that object's own naming token. An over-long code stem is truncated against the R4
        id limit and re-suffixed with the container UID, so the id stays legal and unique.
        """
        token = self.data_set if container_kind == "data-set" else self.program
        id_stem = join_id_tokens(self.prefix, token)
        slug = f"{stem}-{ASSIGNMENT_ID_SUFFIX}"
        budget = FHIR_ID_MAX_LENGTH - (len(id_stem) + 1 if id_stem else 0)
        if len(slug) > budget:
            slug = bounded_slug(slug, uid, budget)
        return f"{id_stem}-{slug}" if id_stem else slug

    @property
    def data_element_code_system(self) -> str:
        """FSH name of the data-element support CodeSystem (e.g. `D2DE_CS`)."""
        return f"{self.prefix}DE_CS"

    @property
    def data_element_code_system_id(self) -> str:
        """FHIR id of the data-element support CodeSystem (e.g. `d2-de-cs`)."""
        return join_id_tokens(self.prefix, "de", "cs")

    @property
    def data_element_value_set(self) -> str:
        """FSH name of the data-element support ValueSet (e.g. `D2DE_VS`)."""
        return f"{self.prefix}DE_VS"

    @property
    def data_element_value_set_id(self) -> str:
        """FHIR id of the data-element support ValueSet (e.g. `d2-de-vs`)."""
        return join_id_tokens(self.prefix, "de", "vs")

    @property
    def tracked_entity_attribute_code_system(self) -> str:
        """FSH name of the tracked-entity-attribute support CodeSystem (e.g. `D2TEA_CS`)."""
        return f"{self.prefix}TEA_CS"

    @property
    def tracked_entity_attribute_code_system_id(self) -> str:
        """FHIR id of the tracked-entity-attribute support CodeSystem (e.g. `d2-tea-cs`)."""
        return join_id_tokens(self.prefix, "tea", "cs")

    @property
    def tracked_entity_attribute_value_set(self) -> str:
        """FSH name of the tracked-entity-attribute support ValueSet (e.g. `D2TEA_VS`)."""
        return f"{self.prefix}TEA_VS"

    @property
    def tracked_entity_attribute_value_set_id(self) -> str:
        """FHIR id of the tracked-entity-attribute support ValueSet (e.g. `d2-tea-vs`)."""
        return join_id_tokens(self.prefix, "tea", "vs")

    @property
    def tracked_entity_type_code_system(self) -> str:
        """FSH name of the tracked-entity-type support CodeSystem (e.g. `D2TET_CS`).

        The tracked-entity-type token rather than a fixed one, because the token already exists and
        already names the person-only forms: a project that renames it moves the form and its
        vocabulary together. `D2TET_<stem>` is one form; `D2TET_CS` is the list of what a form of
        that kind registers.
        """
        return join_name_segments(f"{self.prefix}{self.tracked_entity_type}", "CS")

    @property
    def tracked_entity_type_code_system_id(self) -> str:
        """FHIR id of the tracked-entity-type support CodeSystem (e.g. `d2-tet-cs`)."""
        return join_id_tokens(self.prefix, self.tracked_entity_type, "cs")

    @property
    def tracked_entity_type_value_set(self) -> str:
        """FSH name of the tracked-entity-type support ValueSet (e.g. `D2TET_VS`)."""
        return join_name_segments(f"{self.prefix}{self.tracked_entity_type}", "VS")

    @property
    def tracked_entity_type_value_set_id(self) -> str:
        """FHIR id of the tracked-entity-type support ValueSet (e.g. `d2-tet-vs`)."""
        return join_id_tokens(self.prefix, self.tracked_entity_type, "vs")

    @property
    def tracked_entity_type_resource_map(self) -> str:
        """FSH name of the ConceptMap taking each published type to its FHIR resource type (e.g. `D2TET_CM`)."""
        return join_name_segments(f"{self.prefix}{self.tracked_entity_type}", "CM")

    @property
    def tracked_entity_type_resource_map_id(self) -> str:
        """FHIR id of that ConceptMap (e.g. `d2-tet-cm`)."""
        return join_id_tokens(self.prefix, self.tracked_entity_type, "cm")

    @property
    def category_option_combo_code_system(self) -> str:
        """FSH name of the category-option-combo support CodeSystem (e.g. `D2COC_CS`)."""
        return f"{self.prefix}COC_CS"

    @property
    def category_option_combo_code_system_id(self) -> str:
        """FHIR id of the category-option-combo support CodeSystem (e.g. `d2-coc-cs`)."""
        return join_id_tokens(self.prefix, "coc", "cs")

    @property
    def category_option_combo_value_set(self) -> str:
        """FSH name of the category-option-combo support ValueSet (e.g. `D2COC_VS`)."""
        return f"{self.prefix}COC_VS"

    @property
    def category_option_combo_value_set_id(self) -> str:
        """FHIR id of the category-option-combo support ValueSet (e.g. `d2-coc-vs`)."""
        return join_id_tokens(self.prefix, "coc", "vs")
