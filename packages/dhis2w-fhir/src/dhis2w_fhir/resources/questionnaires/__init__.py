"""FSH emission for DHIS2 data sets, programs, and tracked entity types: one Questionnaire per form.

A data set, an event program, one stage of a tracker program, the registration
a tracker program enrols a person through, and the person-only registration a
tracked entity type stands up on its own are all data-capture forms, so each
maps onto a `Questionnaire`: sections become `#group` items,
data elements become questions typed from their DHIS2 `valueType`,
option-set-bound elements become `#choice` items answered from the option-set
ValueSet, and a data element disaggregated by a non-default category combo
becomes a group with one child question per category option combo. A tracker
program's registration form asks the program's tracked entity attributes
through the very same typing, so an attribute bound to an option set becomes
the same `#choice` question a data element does.

Every instance is `Usage: #definition` with the bare UID as its `id`, carries
both DHIS2 identifiers, and states which kind of DHIS2 form it came from
twice: through the `D2FormType` extension and as `Questionnaire.code`. A
tracker program stage carries a third, grouping identifier naming the program
it belongs to, so one search selects the program's whole capture surface - the
registration form, whose own identifiers are the program's, answers that same
search. A registration form carries one more: the tracked entity type it
enrols a person as.

The output splits by what it describes: `data-sets/<uid>.fsh`,
`event-programs/<uid>.fsh`, `tracker-programs/<program uid>/<stage uid>.fsh`
with the program's `registration.fsh` beside its stages,
`tracked-entity-types/<uid>.fsh` for the person-only forms, and
`data-dictionary/` for the three support CodeSystem/ValueSet pairs the form
kinds share - one over every data element they reference, one over every
tracked entity attribute a registration form asks about, one over every
category option combo. The attribute pair states searchability per context,
because DHIS2 holds that flag on the join rather than on the attribute. The support pairs live under this target's own
directories, so the option-set terminology target's cleanup can never delete
them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.foundation.attribute_values import (
    ATTRIBUTE_CODE_SUB_EXTENSION,
    ATTRIBUTE_ID_SUB_EXTENSION,
    ATTRIBUTE_VALUE_SUB_EXTENSION,
    attribute_value_identifier_system,
)
from dhis2w_fhir.foundation.schemas import FoundationNaming
from dhis2w_fhir.i18n import TRANSLATION_EXTENSION_URL, TranslationIn, name_translations, text_translations
from dhis2w_fhir.names import code_or_uid, page_text, quote
from dhis2w_fhir.notes import GenerateNoteCategory, aggregate_generate_note
from dhis2w_fhir.resources.attribute_combos.schemas import AttributeComboPlan
from dhis2w_fhir.resources.option_sets import option_set_identity_index
from dhis2w_fhir.resources.option_sets.schemas import OptionSetIdentity, OptionSetIdentityPlan
from dhis2w_fhir.resources.questionnaires.assignments import AssignmentPlan
from dhis2w_fhir.resources.questionnaires.schemas import (
    CATEGORY_OPTION_COMBO_TERMINOLOGY,
    DATA_ELEMENT_TERMINOLOGY,
    DOMAIN_PROPERTY_DESCRIPTION,
    FORM_KIND_PROFILES,
    SEARCHABLE_PROPERTY_DESCRIPTION,
    TRACKED_ENTITY_ATTRIBUTE_TERMINOLOGY,
    UNIQUE_PROPERTY_DESCRIPTION,
    AttributeSearchContext,
    CategoryOptionComboIn,
    FormKind,
    FormKindProfile,
    NumericBounds,
    QuestionnaireItemIn,
    QuestionnaireNaming,
    QuestionnaireSourceIn,
    QuestionnaireStemPlan,
    ReferencedObjects,
    SupportTerminologyProfile,
    form_subject_type,
    plan_questionnaire_stems,
    source_display_name,
    source_program,
    source_title_translations,
)
from dhis2w_fhir.status import IgStatus, experimental_for_status
from dhis2w_fhir.writer import FshArtifact, FshBuild

if TYPE_CHECKING:
    from collections.abc import Mapping

    from dhis2w_fhir.attributes import AttributeCodeIndex, AttributeValueIn
    from dhis2w_fhir.config import GenerateConfig
    from dhis2w_fhir.resources.categories.decomposition import CategoryDecomposition

__all__ = [
    "BOUNDS_BY_VALUE_TYPE",
    "BOUND_ELEMENTS_BY_ITEM_TYPE",
    "DATA_DICTIONARY_DIRECTORY",
    "DATA_SET_DIRECTORY",
    "EVENT_PROGRAM_DIRECTORY",
    "ITEM_CONTROL_CODE_SYSTEM_URL",
    "ITEM_CONTROL_EXTENSION_URL",
    "ITEM_TYPES_BY_VALUE_TYPE",
    "MAXIMUM_VALUE_EXTENSION_URL",
    "MINIMUM_VALUE_EXTENSION_URL",
    "PROGRAM_IDENTIFIER_SEGMENT",
    "QUESTIONNAIRE_DIRECTORIES",
    "REGISTRATION_FILE_STEM",
    "TRACKED_ENTITY_TYPE_DIRECTORY",
    "TRACKED_ENTITY_TYPE_IDENTIFIER_SEGMENT",
    "TRACKER_PROGRAM_DIRECTORY",
    "NumericBounds",
    "QuestionnaireStemPlan",
    "ReferencedObjects",
    "bound_option_set_uids",
    "build_questionnaire_artifacts",
    "collect_referenced_objects",
    "domain_code",
    "is_disaggregated",
    "is_multi_valued",
    "item_type",
    "link_id_collisions",
    "plan_questionnaire_stems",
    "question_code_system",
    "question_entity_level",
    "search_context_declarations",
    "source_description",
    "source_items",
    "source_program",
]

#: Sync directory holding one Questionnaire per DHIS2 data set.
DATA_SET_DIRECTORY = "data-sets"

#: Sync directory holding one Questionnaire per DHIS2 event program.
EVENT_PROGRAM_DIRECTORY = "event-programs"

#: Sync directory holding one Questionnaire per tracker program stage, nested under its program's UID.
TRACKER_PROGRAM_DIRECTORY = "tracker-programs"

#: Sync directory holding one Questionnaire per DHIS2 tracked entity type - the person-only forms.
TRACKED_ENTITY_TYPE_DIRECTORY = "tracked-entity-types"

#: Sync directory holding the support terminology every form kind shares.
DATA_DICTIONARY_DIRECTORY = "data-dictionary"

#: The five sync directories the questionnaire target owns, in report order.
QUESTIONNAIRE_DIRECTORIES = (
    DATA_SET_DIRECTORY,
    EVENT_PROGRAM_DIRECTORY,
    TRACKER_PROGRAM_DIRECTORY,
    TRACKED_ENTITY_TYPE_DIRECTORY,
    DATA_DICTIONARY_DIRECTORY,
)

#: The standard R4 extension declaring how a Questionnaire item is rendered.
ITEM_CONTROL_EXTENSION_URL = "http://hl7.org/fhir/StructureDefinition/questionnaire-itemControl"

#: The CodeSystem the item-control extension's CodeableConcept is coded from (`#gtable` here).
ITEM_CONTROL_CODE_SYSTEM_URL = "http://hl7.org/fhir/questionnaire-item-control"

#: The standard R4 extensions constraining the range a numeric question's answer may take.
MINIMUM_VALUE_EXTENSION_URL = "http://hl7.org/fhir/StructureDefinition/minValue"
MAXIMUM_VALUE_EXTENSION_URL = "http://hl7.org/fhir/StructureDefinition/maxValue"

_ENVIRONMENT = Environment(
    loader=PackageLoader("dhis2w_fhir.resources.questionnaires", "templates"),
    autoescape=select_autoescape(default=False),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)

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

#: The range each bounded DHIS2 numeric value type admits, as the `minValue` / `maxValue`
#: extensions a question carries. Only the value types whose name *is* a constraint appear:
#: `INTEGER` and `NUMBER` are unbounded in DHIS2, so a bound on them would invent a rule the
#: instance does not enforce. A guard test asserts every key is a member of the generated
#: `ValueType` enum across v41, v42, and v43.
BOUNDS_BY_VALUE_TYPE = {
    "INTEGER_POSITIVE": NumericBounds(minimum_value=1),
    "INTEGER_ZERO_OR_POSITIVE": NumericBounds(minimum_value=0),
    "INTEGER_NEGATIVE": NumericBounds(maximum_value=-1),
    "PERCENTAGE": NumericBounds(minimum_value=0, maximum_value=100),
    "UNIT_INTERVAL": NumericBounds(minimum_value=0, maximum_value=1),
}

#: The `value[x]` element a bound lands on, keyed by the item type the question answers as. A
#: question answering as anything else - a `#choice` bound to an option set, say - takes no
#: bound at all, because there is no numeric element on it to constrain.
BOUND_ELEMENTS_BY_ITEM_TYPE = {"integer": "valueInteger", "decimal": "valueDecimal"}

#: What an unmapped value type answers as - reached only by a DHIS2 value type newer than the
#: generated enums, since the table above covers every member of all three.
_DEFAULT_ITEM_TYPE = "string"

#: The one DHIS2 value type that captures several answers to a single question.
_MULTI_VALUE_TYPE = "MULTI_TEXT"


#: The alias a tracker program stage's grouping identifier names its program under.
_PROGRAM_IDENTIFIER_SYSTEM = "$DHIS2-PROGRAM"

#: The identifier-system segment that alias expands to, which the JSON path writes absolutely.
PROGRAM_IDENTIFIER_SEGMENT = "program"

#: The alias a registration form names the tracked entity type it enrols a person as under.
_TRACKED_ENTITY_TYPE_IDENTIFIER_SYSTEM = "$DHIS2-TET"

#: The identifier-system segment that alias expands to, which the JSON path writes absolutely.
TRACKED_ENTITY_TYPE_IDENTIFIER_SEGMENT = "tracked-entity-type"

#: The file name a tracker program's registration form is written under, beside its stage files.
#: A fixed stem rather than the program's: the file already sits in the program's own directory,
#: and `registration.fsh` says what the form is at a glance.
REGISTRATION_FILE_STEM = "registration"


class _BoundView(BaseModel):
    """One `minValue` / `maxValue` extension on a question: its url and the typed literal it carries."""

    model_config = ConfigDict(frozen=True)

    url: str
    element: str
    literal: str


class _ItemView(BaseModel):
    """One emitted Questionnaire item, its FSH soft-index paths already resolved."""

    model_config = ConfigDict(frozen=True)

    new_path: str
    path: str
    link_id: str
    text_literal: str
    text_translations: list[TranslationIn] = Field(default_factory=list)
    """The translations of whichever DHIS2 text the item is labelled with, one extension each."""

    type_code: str
    code_token: str | None = None
    answer_value_set: str | None = None
    required: bool = False
    repeats: bool = False
    item_control: bool = False
    entity_level: bool | None = None
    """Whether the question's answer belongs to the tracked entity, or None when the form states no level."""

    bounds: list[_BoundView] = Field(default_factory=list)


class _AttributeValueView(BaseModel):
    """One DHIS2 attribute value as the FSH literals its D2AttributeValue extension is assigned from.

    `attribute_code_literal` is None for an attribute the instance left uncoded, and the template
    writes no `attributeCode` sub-extension at all for it.
    """

    model_config = ConfigDict(frozen=True)

    attribute_id_literal: str
    attribute_code_literal: str | None = None
    value_literal: str


class GroupingIdentifier(BaseModel):
    """One identifier that groups a Questionnaire under a parent DHIS2 object, spelled for both emitters.

    Carried twice for the reason `FormKindProfile` carries its systems twice: the FSH path writes
    the `$DHIS2-*` alias `foundation/d2-aliases.fsh` declares and the JSON path writes the
    absolute URL that alias expands to, and the two must never disagree.
    """

    model_config = ConfigDict(frozen=True)

    alias: str
    segment: str
    value: str


class _GroupingIdentifierView(BaseModel):
    """One grouping identifier as the FSH literals the template writes."""

    model_config = ConfigDict(frozen=True)

    system: str
    value_literal: str


class _AttributeIdentifierView(BaseModel):
    """One unique DHIS2 attribute value as the identifier slice the template writes, both sides quoted."""

    model_config = ConfigDict(frozen=True)

    system_literal: str
    value_literal: str


class _QuestionnaireView(BaseModel):
    """Everything the Questionnaire template needs for one source, every conditional resolved.

    `stem` is the form's identity stem - the instance name suffix, the `id`, and the segment its
    canonical URL closes on - while `uid` is the DHIS2 id its identifier slice carries as data.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    stem: str
    name: str
    url: str
    title_literal: str
    title_element_literal: str
    title_translations: list[TranslationIn] = Field(default_factory=list)
    """The form's NAME translations, riding the title as one standard translation extension each."""

    description_literal: str
    subject_type: str
    identifier_system: str
    identifier_code_system: str
    identifier_code_literal: str
    grouping_identifiers: list[_GroupingIdentifierView] = Field(default_factory=list)
    attribute_identifiers: list[_AttributeIdentifierView] = Field(default_factory=list)
    form_type_extension: str
    form_type_code_system: str
    form_type_code: str
    assignment_extension: str
    assignment_reference: str | None = None
    """Literal `List/<id>` reference of the form's assignment artifact, or None when it publishes none."""

    attribute_option_combos_extension: str
    attribute_option_combo_value_set: str | None = None
    """FSH name of the ValueSet of attribute option combos the form admits, or None on a default combo."""

    attribute_value_extension: str
    entity_level_extension_url: str
    """Absolute URL of the D2EntityLevel extension a registration question states its level on.

    Written as a URL rather than as the FSH name every other extension of this template takes:
    SUSHI merges a named extension slice into whatever soft-indexed `extension[+]` entry precedes
    it on the same element, and a numeric question already carries its bounds there.
    """

    ig_status: IgStatus
    attribute_values: list[_AttributeValueView] = Field(default_factory=list)
    items: list[_ItemView] = Field(default_factory=list)

    @property
    def experimental(self) -> bool:
        """Whether the Questionnaire is experimental - derived from the IG status."""
        return experimental_for_status(self.ig_status)


class _SupportCategoryProperty(BaseModel):
    """One category axis a category option combo concept decomposes over, as the FSH coding it takes."""

    model_config = ConfigDict(frozen=True)

    property_code: str
    coding_literal: str
    """The `system#code "display"` FSH coding into the category's own published CodeSystem."""


class _SupportBooleanDeclaration(BaseModel):
    """One boolean concept property the support CodeSystem declares, named by the context it answers for."""

    model_config = ConfigDict(frozen=True)

    property_code: str
    uri: str
    description_literal: str


class _SupportCategoryDeclaration(BaseModel):
    """One category axis as the concept property the support CodeSystem declares, named by the category."""

    model_config = ConfigDict(frozen=True)

    property_code: str
    uri: str
    description_literal: str


class _SupportBooleanProperty(BaseModel):
    """One boolean concept property a support concept carries, as the code and literal FSH writes."""

    model_config = ConfigDict(frozen=True)

    property_code: str
    literal: str


class _SupportConcept(BaseModel):
    """One data element, tracked entity attribute, or category option combo as a support CodeSystem concept."""

    model_config = ConfigDict(frozen=True)

    uid: str
    display_literal: str
    code_literal: str | None = None
    """The DHIS2 code as an FSH literal, or None when DHIS2 states none and the property is left off."""

    domain_code: str | None = None
    value_type_code: str | None = None
    unique_literal: str | None = None
    searchable_literal: str | None = None
    searchable_contexts: list[_SupportBooleanProperty] = Field(default_factory=list)
    category_properties: list[_SupportCategoryProperty] = Field(default_factory=list)
    designations: list[TranslationIn] = Field(default_factory=list)
    """The object's NAME translations, which render the concept display in each configured locale."""


class _SupportTerminologyView(BaseModel):
    """A support CodeSystem/ValueSet pair over the objects the generated questionnaires reference."""

    model_config = ConfigDict(frozen=True)

    code_system: str
    code_system_id: str
    value_set: str
    value_set_id: str
    title_literal: str
    description_literal: str
    property_base: str
    property_description_literal: str
    domain_property_description_literal: str
    value_type_property_description_literal: str
    unique_property_description_literal: str
    searchable_property_description_literal: str
    ig_status: IgStatus
    searchable_declarations: list[_SupportBooleanDeclaration] = Field(default_factory=list)
    category_declarations: list[_SupportCategoryDeclaration] = Field(default_factory=list)
    concepts: list[_SupportConcept] = Field(default_factory=list)

    @property
    def experimental(self) -> bool:
        """Whether the support pair is experimental - derived from the IG status."""
        return experimental_for_status(self.ig_status)

    @property
    def declares_code(self) -> bool:
        """Whether any concept carries a DHIS2 code, so the CodeSystem must declare the property."""
        return any(concept.code_literal is not None for concept in self.concepts)

    @property
    def declares_domain(self) -> bool:
        """Whether any concept carries a domain, and the CodeSystem must therefore declare the property."""
        return any(concept.domain_code is not None for concept in self.concepts)

    @property
    def declares_value_type(self) -> bool:
        """Whether any concept carries the value-type property, so the CodeSystem must declare it."""
        return any(concept.value_type_code is not None for concept in self.concepts)

    @property
    def declares_unique(self) -> bool:
        """Whether any concept carries the unique property, so the CodeSystem must declare it."""
        return any(concept.unique_literal is not None for concept in self.concepts)

    @property
    def declares_searchable(self) -> bool:
        """Whether any concept carries the searchable roll-up, so the CodeSystem must declare it."""
        return any(concept.searchable_literal is not None for concept in self.concepts)


def build_questionnaire_artifacts(
    sources: list[QuestionnaireSourceIn],
    config: GenerateConfig,
    canonical: str,
    *,
    ig_status: IgStatus,
    option_set_plan: OptionSetIdentityPlan,
    attribute_codes: AttributeCodeIndex,
    stem_plan: QuestionnaireStemPlan | None = None,
    assignments: AssignmentPlan | None = None,
    attribute_combos: AttributeComboPlan | None = None,
    decomposition: CategoryDecomposition | None = None,
) -> FshBuild:
    """Build one `data-sets/` or `event-programs/` file per target plus the `data-dictionary/` support pairs.

    `option_set_plan` is the identity plan the terminology target emits from, so an
    `answerValueSet` names the ValueSet the same run writes under either naming source.
    `attribute_codes` is the run's `uid -> code` join, which the D2AttributeValue extensions
    read the attribute code out of. `stem_plan` is the questionnaire surface's identity-stem
    plan; a caller building several targets off one fetch passes the run's plan, and a caller
    without one gets it resolved here through the same `plan_questionnaire_stems` call.
    `assignments` names the assignment List each form is scoped by; a form absent from the plan
    carries no assignment extension, which means the whole published registry may report it.
    `attribute_combos` names the attribute-option-combo ValueSet each form's responses are keyed
    from; a form absent from that plan carries no extension either, which means the default
    attribute option combo. `decomposition` states what each category option combo is composed of,
    which is what the data dictionary's combo concepts carry their category axes from.
    """
    build = FshBuild()
    assignment_plan = assignments if assignments is not None else AssignmentPlan()
    attribute_combo_plan = attribute_combos if attribute_combos is not None else AttributeComboPlan()
    plan = stem_plan if stem_plan is not None else plan_questionnaire_stems(sources, config.naming.source)
    build.notes.extend(plan.notes)
    names = QuestionnaireNaming.from_naming(config.naming)
    foundation = FoundationNaming.from_naming(config.naming)
    index = option_set_identity_index(option_set_plan, bound_option_set_uids(sources), config)
    referenced = ReferencedObjects()
    colliding: list[str] = []
    template = _ENVIRONMENT.get_template("questionnaire.fsh.jinja")
    for source in sorted(sources, key=lambda item: (item.name, item.uid)):
        collisions = link_id_collisions(source)
        if collisions:
            colliding.append(f"{source_display_name(source)} ({source.uid}) on {', '.join(collisions)}")
            continue
        collect_referenced_objects(source, referenced)
        view = _questionnaire_view(
            source,
            names,
            foundation,
            canonical,
            index.identities,
            stem_plan=plan,
            ig_status=ig_status,
            attribute_codes=attribute_codes,
            identifier_system_base=config.identifier_system_base,
            assignments=assignment_plan,
            attribute_combos=attribute_combo_plan,
            tracked_entity_types=config.tracked_entity_types,
            locales=config.locales,
        )
        build.artifacts.append(
            FshArtifact(
                relative_path=_source_relative_path(source, plan),
                kind="instances",
                fsh_name=f"Questionnaire-{plan.targets.stem_for(source.uid)}",
                content=template.render(
                    questionnaire=view,
                    translation_extension_url=TRANSLATION_EXTENSION_URL,
                    item_control_extension_url=ITEM_CONTROL_EXTENSION_URL,
                    item_control_code_system_url=ITEM_CONTROL_CODE_SYSTEM_URL,
                    attribute_id_sub_extension=ATTRIBUTE_ID_SUB_EXTENSION,
                    attribute_code_sub_extension=ATTRIBUTE_CODE_SUB_EXTENSION,
                    attribute_value_sub_extension=ATTRIBUTE_VALUE_SUB_EXTENSION,
                ),
            )
        )
    if referenced.data_elements:
        build.artifacts.append(_data_element_terminology(referenced.data_elements, names, config, ig_status=ig_status))
    if referenced.tracked_entity_attributes:
        build.artifacts.append(_tracked_entity_attribute_terminology(referenced, names, config, ig_status=ig_status))
    if referenced.option_combos:
        build.artifacts.append(
            _option_combo_terminology(
                referenced.option_combos, names, config, ig_status=ig_status, decomposition=decomposition
            )
        )
    if colliding:
        build.notes.append(
            aggregate_generate_note(
                GenerateNoteCategory.REFUSED_FORM,
                f"{len(colliding)} forms would emit one linkId twice, which R4 forbids (que-2: link ids are "
                "unique within a Questionnaire); the whole form is skipped rather than published invalid, "
                "because a response answering that linkId would name two questions at once",
                colliding,
            )
        )
    if index.unplanned_uids:
        build.notes.append(
            aggregate_generate_note(
                GenerateNoteCategory.SELECTION_GAP,
                f"{len(index.unplanned_uids)} option sets a question binds are absent from the option-set "
                "selection; their answerValueSet names are derived from the UID",
                index.unplanned_uids,
            )
        )
    return build


def bound_option_set_uids(sources: list[QuestionnaireSourceIn]) -> list[str]:
    """Every option set the given forms bind a question to."""
    return [item.option_set_uid for source in sources for item in source_items(source) if item.option_set_uid]


def source_items(source: QuestionnaireSourceIn) -> list[QuestionnaireItemIn]:
    """Every question one form carries, sectioned and unsectioned alike."""
    return [item for section in source.sections for item in section.items] + list(source.flat_items)


def link_id_collisions(source: QuestionnaireSourceIn) -> list[str]:
    """Every `linkId` one form would emit more than once, in the order the clash is first reached.

    A DHIS2 section UID and a data element UID are drawn from one pool, so a form can reuse one
    UID on a group and on a question - and then two items answer to one `linkId`. R4 forbids that
    outright (`que-2`), and a response answering that `linkId` would name two questions at once,
    so the caller skips the whole form rather than publish an invalid Questionnaire.
    """
    seen: set[str] = set()
    collided: list[str] = []
    for link_id in _emitted_link_ids(source):
        if link_id in seen and link_id not in collided:
            collided.append(link_id)
        seen.add(link_id)
    return collided


def _emitted_link_ids(source: QuestionnaireSourceIn) -> list[str]:
    """Every `linkId` one form's items carry, in emission order: section groups, questions, and cells."""
    link_ids: list[str] = []
    for section in source.sections:
        link_ids.append(section.uid)
        for item in section.items:
            link_ids.extend(_item_link_ids(item, source.kind))
    for item in source.flat_items:
        link_ids.extend(_item_link_ids(item, source.kind))
    return link_ids


def _item_link_ids(item: QuestionnaireItemIn, kind: FormKind) -> list[str]:
    """One data element's `linkId`s: the question itself, plus a cell per option combo when disaggregated."""
    if not is_disaggregated(item, kind) or item.category_combo is None:
        return [item.uid]
    return [item.uid, *(f"{item.uid}.{option_combo.uid}" for option_combo in item.category_combo.option_combos)]


#: The sync directory each form kind is written to.
_DIRECTORIES_BY_KIND: dict[FormKind, str] = {
    "aggregate": DATA_SET_DIRECTORY,
    "event": EVENT_PROGRAM_DIRECTORY,
    "tracker": TRACKER_PROGRAM_DIRECTORY,
    "tracker-event": TRACKER_PROGRAM_DIRECTORY,
    "tracked-entity": TRACKED_ENTITY_TYPE_DIRECTORY,
}


def _source_directory(source: QuestionnaireSourceIn) -> str:
    """The sync directory one form kind is written to."""
    return _DIRECTORIES_BY_KIND[source.kind]


def _source_relative_path(source: QuestionnaireSourceIn, stem_plan: QuestionnaireStemPlan) -> str:
    """The file one form's identity stem names, both tracker forms nested under their program's stem.

    A tracker program's directory holds its registration form beside its stage forms, so one
    program's whole capture surface is one directory: `registration.fsh` names the form that
    enrols the person, and a stage's own stem names each visit captured afterwards.
    """
    if source.kind == "tracker":
        program_stem = stem_plan.programs.stem_for(source.uid)
        return f"{TRACKER_PROGRAM_DIRECTORY}/{program_stem}/{REGISTRATION_FILE_STEM}.fsh"
    stem = stem_plan.targets.stem_for(source.uid)
    if source.kind != "tracker-event":
        return f"{_source_directory(source)}/{stem}.fsh"
    return f"{TRACKER_PROGRAM_DIRECTORY}/{stem_plan.programs.stem_for(source_program(source).uid)}/{stem}.fsh"


def _questionnaire_view(
    source: QuestionnaireSourceIn,
    names: QuestionnaireNaming,
    foundation: FoundationNaming,
    canonical: str,
    identities: dict[str, OptionSetIdentity],
    *,
    stem_plan: QuestionnaireStemPlan,
    ig_status: IgStatus,
    attribute_codes: AttributeCodeIndex,
    identifier_system_base: str,
    assignments: AssignmentPlan,
    attribute_combos: AttributeComboPlan,
    tracked_entity_types: Mapping[str, str],
    locales: list[str],
) -> _QuestionnaireView:
    """Project one source onto the view the Questionnaire template renders.

    The identity stem carries the artifact identity - the instance name, the `id`, the canonical
    URL, the FSH name segment - while `uid` stays the DHIS2 identifier value the resource exposes.
    `tracked_entity_types` is the project's tracked-entity-type map, which is what decides the
    `subjectType` a tracker form declares.
    """
    profile = FORM_KIND_PROFILES[source.kind]
    display_name = source_display_name(source)
    return _QuestionnaireView(
        uid=source.uid,
        stem=stem_plan.targets.stem_for(source.uid),
        name=names.questionnaire_name(source.kind, stem_plan.targets.fsh_segment_for(source.uid)),
        url=f"{canonical}/Questionnaire/{stem_plan.targets.stem_for(source.uid)}",
        title_literal=page_text(f"Questionnaire - {display_name}"),
        title_element_literal=quote(display_name),
        title_translations=source_title_translations(source, locales),
        description_literal=page_text(source_description(source, profile)),
        subject_type=form_subject_type(source, tracked_entity_types),
        identifier_system=profile.identifier_system,
        identifier_code_system=profile.identifier_code_system,
        identifier_code_literal=quote(code_or_uid(source.code, source.uid)),
        grouping_identifiers=[
            _GroupingIdentifierView(system=identifier.alias, value_literal=quote(identifier.value))
            for identifier in grouping_identifiers(source)
        ],
        attribute_identifiers=_attribute_identifier_views(
            source.attribute_values, attribute_codes, identifier_system_base
        ),
        form_type_extension=foundation.form_type_extension,
        form_type_code_system=foundation.form_type_code_system,
        form_type_code=source.kind,
        assignment_extension=foundation.organisation_unit_assignment_extension,
        assignment_reference=assignments.reference_for(source),
        attribute_option_combos_extension=foundation.attribute_option_combos_extension,
        attribute_option_combo_value_set=_attribute_option_combo_value_set(source, attribute_combos),
        attribute_value_extension=foundation.attribute_value_extension,
        entity_level_extension_url=f"{canonical}/StructureDefinition/{foundation.entity_level_extension_id}",
        ig_status=ig_status,
        attribute_values=_attribute_value_views(source.attribute_values, attribute_codes),
        items=_item_views(source, names, identities, locales),
    )


def _attribute_option_combo_value_set(
    source: QuestionnaireSourceIn, attribute_combos: AttributeComboPlan
) -> str | None:
    """The FSH name of the ValueSet one form's responses draw an attribute option combo from, or None."""
    identity = attribute_combos.identity_for(source.uid)
    return None if identity is None else identity.value_set_name


def source_description(source: QuestionnaireSourceIn, profile: FormKindProfile) -> str:
    """The prose one form's Questionnaire describes itself with, a program stage naming its program too."""
    opening = f"DHIS2 {profile.label} {source.name} ({source.uid})"
    if source.kind == "tracked-entity":
        return (
            f"{opening} as a registration form: the tracked entity attributes the type itself collects, "
            "captured when a person is registered without being enrolled in any program."
        )
    if source.kind == "tracker":
        return (
            f"{opening} as a registration form: the tracked entity attributes captured when a person "
            "is enrolled in the program."
        )
    if source.kind != "tracker-event":
        return f"{opening} as a data capture form."
    program = source_program(source)
    return f"{opening} of program {program.name} ({program.uid}) as a data capture form."


def question_code_system(kind: FormKind, names: QuestionnaireNaming) -> str:
    """The support CodeSystem one form kind's questions are coded from - `D2DE_CS`, or `D2TEA_CS`."""
    if FORM_KIND_PROFILES[kind].question_subject == "tracked-entity-attribute":
        return names.tracked_entity_attribute_code_system
    return names.data_element_code_system


def grouping_identifiers(source: QuestionnaireSourceIn) -> list[GroupingIdentifier]:
    """The identifiers grouping one form under a parent DHIS2 object, in emission order.

    Searching `Questionnaire?identifier={base}/id/program|<program uid>` selects a tracker
    program's whole capture surface: every stage carries the program as a grouping identifier,
    and the registration form carries it as its own identity. A registration form adds the
    tracked entity type it enrols a person as, which is what a client needs to know before it
    can name the person the response creates.
    """
    if source.kind == "tracker":
        tracked_entity_type_uid = source.tracked_entity_type_uid
        if tracked_entity_type_uid is None:
            return []
        return [
            GroupingIdentifier(
                alias=_TRACKED_ENTITY_TYPE_IDENTIFIER_SYSTEM,
                segment=TRACKED_ENTITY_TYPE_IDENTIFIER_SEGMENT,
                value=tracked_entity_type_uid,
            )
        ]
    if source.kind != "tracker-event":
        return []
    return [
        GroupingIdentifier(
            alias=_PROGRAM_IDENTIFIER_SYSTEM,
            segment=PROGRAM_IDENTIFIER_SEGMENT,
            value=source_program(source).uid,
        )
    ]


def _attribute_identifier_views(
    attribute_values: list[AttributeValueIn], attribute_codes: AttributeCodeIndex, identifier_system_base: str
) -> list[_AttributeIdentifierView]:
    """Project the values of unique attributes onto the identifier slices the template appends."""
    return [
        _AttributeIdentifierView(
            system_literal=quote(
                attribute_value_identifier_system(identifier_system_base, attribute_value.attribute_uid)
            ),
            value_literal=quote(attribute_value.value),
        )
        for attribute_value in attribute_values
        if attribute_codes.is_unique(attribute_value.attribute_uid)
    ]


def _attribute_value_views(
    attribute_values: list[AttributeValueIn], attribute_codes: AttributeCodeIndex
) -> list[_AttributeValueView]:
    """Project a form's annotating attribute values onto their FSH literals, in the order DHIS2 returned them."""
    views: list[_AttributeValueView] = []
    for attribute_value in attribute_values:
        if attribute_codes.is_unique(attribute_value.attribute_uid):
            continue
        code = attribute_codes.code_for(attribute_value.attribute_uid)
        views.append(
            _AttributeValueView(
                attribute_id_literal=quote(attribute_value.attribute_uid),
                attribute_code_literal=quote(code) if code is not None else None,
                value_literal=quote(attribute_value.value),
            )
        )
    return views


def _item_views(
    source: QuestionnaireSourceIn,
    names: QuestionnaireNaming,
    identities: dict[str, OptionSetIdentity],
    locales: list[str],
) -> list[_ItemView]:
    """Flatten the source's sections and unsectioned items into depth-first FSH item lines."""
    views: list[_ItemView] = []
    for section in source.sections:
        views.append(
            _ItemView(
                new_path=_new_path(0),
                path=_set_path(0),
                link_id=section.uid,
                text_literal=quote(section.name),
                text_translations=name_translations(section.translations, locales),
                type_code="group",
                item_control=any(is_disaggregated(item, source.kind) for item in section.items),
            )
        )
        for item in section.items:
            views.extend(_question_views(item, names, identities, locales, depth=1, kind=source.kind))
    for item in source.flat_items:
        views.extend(_question_views(item, names, identities, locales, depth=0, kind=source.kind))
    return views


def _question_views(
    item: QuestionnaireItemIn,
    names: QuestionnaireNaming,
    identities: dict[str, OptionSetIdentity],
    locales: list[str],
    depth: int,
    kind: FormKind,
) -> list[_ItemView]:
    """Build one question's item lines: a question, or a group with one child per option combo.

    A disaggregated cell asks the very question its data element does, one category option combo
    at a time, so every child takes the element's effective item type, its answer binding, and
    its repeats - only the `linkId`, the text, and the code differ. Only an aggregate source
    disaggregates; see `is_disaggregated` for why event-kind questions stay flat.
    """
    code_token = f"{question_code_system(kind, names)}#{item.uid} {quote(item.name)}"
    text_literal = quote(item.form_name or item.name)
    text_translated = text_translations(item.translations, locales, form_named=item.form_name is not None)
    resolved_item_type = item_type(item)
    answer_value_set = _answer_value_set(item, identities)
    repeats = is_multi_valued(item.value_type, resolved_item_type)
    bounds = _bound_views(item.value_type, resolved_item_type)
    if not is_disaggregated(item, kind):
        return [
            _ItemView(
                new_path=_new_path(depth),
                path=_set_path(depth),
                link_id=item.uid,
                code_token=code_token,
                text_literal=text_literal,
                text_translations=text_translated,
                type_code=resolved_item_type,
                answer_value_set=answer_value_set,
                required=item.compulsory,
                repeats=repeats,
                entity_level=question_entity_level(item, kind),
                bounds=bounds,
            )
        ]
    views = [
        _ItemView(
            new_path=_new_path(depth),
            path=_set_path(depth),
            link_id=item.uid,
            code_token=code_token,
            text_literal=text_literal,
            text_translations=text_translated,
            type_code="group",
            required=item.compulsory,
        )
    ]
    category_combo = item.category_combo
    option_combos = category_combo.option_combos if category_combo is not None else []
    for option_combo in option_combos:
        views.append(
            _ItemView(
                new_path=_new_path(depth + 1),
                path=_set_path(depth + 1),
                link_id=f"{item.uid}.{option_combo.uid}",
                code_token=f"{names.category_option_combo_code_system}#{option_combo.uid} {quote(option_combo.name)}",
                text_literal=quote(option_combo.name),
                type_code=resolved_item_type,
                answer_value_set=answer_value_set,
                required=option_combo.uid in item.required_option_combo_uids,
                repeats=repeats,
                bounds=bounds,
            )
        )
    return views


def _bound_views(value_type: str, item_type: str) -> list[_BoundView]:
    """The `minValue` / `maxValue` extensions one question carries, typed by the item type it answers as."""
    bounds = BOUNDS_BY_VALUE_TYPE.get(value_type)
    element = BOUND_ELEMENTS_BY_ITEM_TYPE.get(item_type)
    if bounds is None or element is None:
        return []
    views: list[_BoundView] = []
    if bounds.minimum_value is not None:
        views.append(_BoundView(url=MINIMUM_VALUE_EXTENSION_URL, element=element, literal=str(bounds.minimum_value)))
    if bounds.maximum_value is not None:
        views.append(_BoundView(url=MAXIMUM_VALUE_EXTENSION_URL, element=element, literal=str(bounds.maximum_value)))
    return views


def question_entity_level(item: QuestionnaireItemIn, kind: FormKind) -> bool | None:
    """Which DHIS2 level one question's answer is imported at, or None when the form states no level.

    Only a registration form has two levels to choose between: a tracked entity attribute of the
    program's tracked entity type is stated on the tracked entity, an attribute only the program
    asks is stated on the enrollment. Every other form kind asks data elements, which have no such
    split, so the extension is written on registration questions and nowhere else. A registration
    question whose projection carries no level - a guide generated before the fact was fetched -
    states none either, and a consumer reads its answer as entity-level.
    """
    if FORM_KIND_PROFILES[kind].question_subject != "tracked-entity-attribute":
        return None
    return item.entity_level


def is_disaggregated(item: QuestionnaireItemIn, kind: FormKind) -> bool:
    """Check whether a question splits into per-option-combo cells - an aggregate-only shape.

    A data set's values land on `/api/dataValueSets`, where every value carries a category
    option combo, so a non-default combo becomes one cell per combo. An event data value -
    event program and tracker stage alike - has no categoryOptionCombo slot on the wire, so
    an event-kind question stays flat whatever combo its data element declares: a form must
    not ask a question the capture endpoint cannot accept an answer to.
    """
    if kind != "aggregate":
        return False
    return item.category_combo is not None and not item.category_combo.is_default


def item_type(item: QuestionnaireItemIn) -> str:
    """The item type one question answers as: `choice` when option-set bound, else its value type's."""
    if item.option_set_uid is not None:
        return "choice"
    return _value_type_item_type(item.value_type)


def domain_code(domain_type: str) -> str | None:
    """The `domain` concept code one DHIS2 `domainType` carries (`aggregate`, `tracker`), or None when absent."""
    return domain_type.strip().lower() or None


def is_multi_valued(value_type: str, item_type: str) -> bool:
    """Whether a question captures several answers - `MULTI_TEXT` bound to its option set, and only that.

    `MULTI_TEXT` *is* multiple selection: DHIS2 stores a comma-separated list of option codes
    against one data element. The type is option-set-bound by definition, so an item that
    somehow answers as anything but `#choice` is a malformed data element and takes no `repeats`.
    """
    return value_type == _MULTI_VALUE_TYPE and item_type == "choice"


def _value_type_item_type(value_type: str) -> str:
    """Map a DHIS2 value type onto the FHIR item type it answers as, defaulting to a string."""
    return ITEM_TYPES_BY_VALUE_TYPE.get(value_type, _DEFAULT_ITEM_TYPE)


def _answer_value_set(item: QuestionnaireItemIn, identities: dict[str, OptionSetIdentity]) -> str | None:
    """The option-set ValueSet an option-set-bound question is answered from, as the run names it."""
    if item.option_set_uid is None:
        return None
    return identities[item.option_set_uid].value_set_name


def _new_path(depth: int) -> str:
    """The FSH path that opens a new item at `depth` (e.g. `item[=].item[+]`)."""
    return f"{'item[=].' * depth}item[+]"


def _set_path(depth: int) -> str:
    """The FSH path that addresses the item just opened at `depth` (e.g. `item[=].item[=]`)."""
    return f"{'item[=].' * depth}item[=]"


def collect_referenced_objects(source: QuestionnaireSourceIn, referenced: ReferencedObjects) -> None:
    """Record every question object and category option combo one source's items reference.

    A form's questions land in the dictionary its kind asks from: a registration form's questions
    are the program's tracked entity attributes, a person-only form's are the tracked entity
    type's, everything else's are data elements.

    An attribute question also records the context that asked it, because searchability is a fact
    about the pair rather than about the attribute: two programs asking one attribute contribute
    two answers, and the dictionary publishes both.
    """
    asks_attributes = FORM_KIND_PROFILES[source.kind].question_subject == "tracked-entity-attribute"
    questions = referenced.tracked_entity_attributes if asks_attributes else referenced.data_elements
    for item in source_items(source):
        questions.setdefault(item.uid, item)
        if asks_attributes:
            _record_search_context(source, item, referenced)
        if not is_disaggregated(item, source.kind) or item.category_combo is None:
            continue
        for option_combo in item.category_combo.option_combos:
            referenced.option_combos.setdefault(option_combo.uid, option_combo)


def _record_search_context(
    source: QuestionnaireSourceIn, item: QuestionnaireItemIn, referenced: ReferencedObjects
) -> None:
    """Record what one form says about whether the attribute it asks is searchable in it."""
    contexts = referenced.search_contexts.setdefault(item.uid, [])
    if any(context.context_uid == source.uid for context in contexts):
        return
    label = f"{FORM_KIND_PROFILES[source.kind].label} {source.name} ({source.uid})"
    contexts.append(AttributeSearchContext(context_uid=source.uid, context_label=label, searchable=item.searchable))


def _data_element_terminology(
    data_elements: dict[str, QuestionnaireItemIn],
    names: QuestionnaireNaming,
    config: GenerateConfig,
    *,
    ig_status: IgStatus,
) -> FshArtifact:
    """Build `data-dictionary/data-elements.fsh` over every data element the questionnaires reference."""
    concepts = [
        _SupportConcept(
            uid=item.uid,
            display_literal=quote(item.name),
            code_literal=quote(item.code) if item.code else None,
            domain_code=domain_code(item.domain_type),
            value_type_code=item.value_type,
            designations=name_translations(item.translations, config.locales),
        )
        for item in sorted(data_elements.values(), key=lambda item: (item.name, item.uid))
    ]
    return _support_terminology_artifact(
        concepts,
        DATA_ELEMENT_TERMINOLOGY,
        config,
        file_stem="data-elements",
        code_system=names.data_element_code_system,
        code_system_id=names.data_element_code_system_id,
        value_set=names.data_element_value_set,
        value_set_id=names.data_element_value_set_id,
        ig_status=ig_status,
    )


def _tracked_entity_attribute_terminology(
    referenced: ReferencedObjects,
    names: QuestionnaireNaming,
    config: GenerateConfig,
    *,
    ig_status: IgStatus,
) -> FshArtifact:
    """Build `data-dictionary/tracked-entity-attributes.fsh` over every attribute the forms ask about.

    The twin of the data-element pair, over the objects a registration form asks its questions
    from: the same `dhis2-code` and `value-type` properties, plus the two that say what the
    attribute does for the person. `unique` marks the business identifier the person is found by;
    `searchable` says whether DHIS2 will find a person by it at all, once as a roll-up over every
    context this run publishes and once per context, because DHIS2 holds the flag on the join and
    two contexts asking one attribute disagree as readily as they agree.
    """
    attributes = referenced.tracked_entity_attributes
    concepts = [
        _SupportConcept(
            uid=item.uid,
            display_literal=quote(item.name),
            code_literal=quote(item.code) if item.code else None,
            value_type_code=item.value_type,
            unique_literal="true" if item.unique else "false",
            searchable_literal="true" if referenced.searchable_anywhere(item.uid) else "false",
            searchable_contexts=[
                _SupportBooleanProperty(
                    property_code=context.property_code, literal="true" if context.searchable else "false"
                )
                for context in referenced.contexts_for(item.uid)
            ],
            designations=name_translations(item.translations, config.locales),
        )
        for item in sorted(attributes.values(), key=lambda item: (item.name, item.uid))
    ]
    return _support_terminology_artifact(
        concepts,
        TRACKED_ENTITY_ATTRIBUTE_TERMINOLOGY,
        config,
        file_stem="tracked-entity-attributes",
        code_system=names.tracked_entity_attribute_code_system,
        code_system_id=names.tracked_entity_attribute_code_system_id,
        value_set=names.tracked_entity_attribute_value_set,
        value_set_id=names.tracked_entity_attribute_value_set_id,
        ig_status=ig_status,
        search_contexts=search_context_declarations(referenced),
    )


def search_context_declarations(referenced: ReferencedObjects) -> list[AttributeSearchContext]:
    """Every context the run publishes a searchability answer for, once each, in context-UID order.

    One declaration per context rather than per attribute-context pair: the property is what the
    CodeSystem declares and the concepts are what carry a value for it, so a program asking twelve
    attributes declares one property and answers it twelve times.
    """
    seen: dict[str, AttributeSearchContext] = {}
    for contexts in referenced.search_contexts.values():
        for context in contexts:
            seen.setdefault(context.context_uid, context)
    return [seen[uid] for uid in sorted(seen)]


def _option_combo_terminology(
    option_combos: dict[str, CategoryOptionComboIn],
    names: QuestionnaireNaming,
    config: GenerateConfig,
    *,
    ig_status: IgStatus,
    decomposition: CategoryDecomposition | None,
) -> FshArtifact:
    """Build `data-dictionary/category-option-combos.fsh` over every option combo the forms disaggregate by.

    Beside its own code, each combo concept states what it is composed of: one `Coding`-valued
    property per category the combo splits over, coding the option into that category's CodeSystem.
    """
    concepts = [
        _SupportConcept(
            uid=option_combo.uid,
            display_literal=quote(option_combo.name),
            code_literal=quote(option_combo.code) if option_combo.code else None,
            category_properties=_category_properties(option_combo.uid, decomposition),
        )
        for option_combo in sorted(option_combos.values(), key=lambda item: (item.name, item.uid))
    ]
    return _support_terminology_artifact(
        concepts,
        CATEGORY_OPTION_COMBO_TERMINOLOGY,
        config,
        file_stem="category-option-combos",
        code_system=names.category_option_combo_code_system,
        code_system_id=names.category_option_combo_code_system_id,
        value_set=names.category_option_combo_value_set,
        value_set_id=names.category_option_combo_value_set_id,
        ig_status=ig_status,
        decomposition=decomposition,
    )


def _category_properties(
    option_combo_uid: str, decomposition: CategoryDecomposition | None
) -> list[_SupportCategoryProperty]:
    """One category option combo's axes as the FSH codings its concept carries, in its combo's category order."""
    if decomposition is None:
        return []
    properties: list[_SupportCategoryProperty] = []
    for concept_property in decomposition.properties_for(option_combo_uid):
        coding = concept_property.valueCoding
        if concept_property.code is None or coding is None or coding.system is None or coding.code is None:
            continue
        display = "" if coding.display is None else f" {quote(coding.display)}"
        properties.append(
            _SupportCategoryProperty(
                property_code=concept_property.code,
                coding_literal=f"{coding.system}#{coding.code}{display}",
            )
        )
    return properties


def _support_terminology_artifact(
    concepts: list[_SupportConcept],
    terminology: SupportTerminologyProfile,
    config: GenerateConfig,
    *,
    file_stem: str,
    code_system: str,
    code_system_id: str,
    value_set: str,
    value_set_id: str,
    ig_status: IgStatus,
    decomposition: CategoryDecomposition | None = None,
    search_contexts: list[AttributeSearchContext] | None = None,
) -> FshArtifact:
    """Render one data-dictionary pair through the template every support pair shares."""
    carried = {
        category_property.property_code for concept in concepts for category_property in concept.category_properties
    }
    declarations = [] if decomposition is None else decomposition.declarations_for(carried)
    property_base = f"{config.identifier_system_base}/property"
    view = _SupportTerminologyView(
        code_system=code_system,
        code_system_id=code_system_id,
        value_set=value_set,
        value_set_id=value_set_id,
        title_literal=quote(terminology.title),
        description_literal=quote(terminology.description),
        property_base=property_base,
        property_description_literal=quote(terminology.code_property_description),
        domain_property_description_literal=quote(DOMAIN_PROPERTY_DESCRIPTION),
        value_type_property_description_literal=quote(terminology.value_type_property_description),
        unique_property_description_literal=quote(UNIQUE_PROPERTY_DESCRIPTION),
        searchable_property_description_literal=quote(SEARCHABLE_PROPERTY_DESCRIPTION),
        ig_status=ig_status,
        searchable_declarations=[
            _SupportBooleanDeclaration(
                property_code=context.property_code,
                uri=f"{property_base}/{context.property_code}",
                description_literal=quote(context.description),
            )
            for context in search_contexts or []
        ],
        category_declarations=[
            _SupportCategoryDeclaration(
                property_code=declaration.code or "",
                uri=declaration.uri or "",
                description_literal=quote(declaration.description or ""),
            )
            for declaration in declarations
        ],
        concepts=concepts,
    )
    return FshArtifact(
        relative_path=f"{DATA_DICTIONARY_DIRECTORY}/{file_stem}.fsh",
        kind="terminology-pair",
        fsh_name=code_system,
        content=_ENVIRONMENT.get_template("support-terminology.fsh.jinja").render(terminology=view),
    )
