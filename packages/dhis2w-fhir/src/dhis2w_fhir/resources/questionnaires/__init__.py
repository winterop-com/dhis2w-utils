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
from dhis2w_fhir.foundation.schemas import (
    DATE_LABEL_ENROLLMENT_SUB_EXTENSION,
    DATE_LABEL_EVENT_SUB_EXTENSION,
    DATE_LABEL_INCIDENT_SUB_EXTENSION,
    PROGRAM_RULE_ACTION_SUB_EXTENSION,
    PROGRAM_RULE_CONDITION_SUB_EXTENSION,
    PROGRAM_RULE_DESCRIPTION_SUB_EXTENSION,
    PROGRAM_RULE_NAME_SUB_EXTENSION,
    PROGRAM_RULE_UID_SUB_EXTENSION,
    FoundationNaming,
)
from dhis2w_fhir.i18n import (
    TRANSLATION_EXTENSION_URL,
    TranslationIn,
    description_translations,
    name_translations,
    text_translations,
)
from dhis2w_fhir.names import code_or_uid, flatten_whitespace, page_text, quote, quote_verbatim
from dhis2w_fhir.notes import (
    GenerateNoteCategory,
    aggregate_generate_note,
    pluralize,
    verb_for_count,
)
from dhis2w_fhir.resources.attribute_combos.schemas import AttributeComboPlan
from dhis2w_fhir.resources.option_sets import code_system_canonical, option_set_identity_index
from dhis2w_fhir.resources.option_sets.schemas import OptionSetIdentity, OptionSetIdentityPlan
from dhis2w_fhir.resources.questionnaires.assignments import AssignmentPlan
from dhis2w_fhir.resources.questionnaires.program_rules import (
    EnableWhenCondition,
    FormProgramRules,
    ItemEnableWhen,
    ProgramRuleBound,
    PublishedProgramRule,
    merged_bounds,
    plan_program_rules,
    value_type_bound,
)
from dhis2w_fhir.resources.questionnaires.schemas import (
    BOUND_ELEMENTS_BY_ITEM_TYPE,
    CATEGORY_OPTION_COMBO_TERMINOLOGY,
    DATA_ELEMENT_TERMINOLOGY,
    DISPLAY_IN_LIST_PROPERTY_DESCRIPTION,
    DOMAIN_PROPERTY_DESCRIPTION,
    FORM_KIND_PROFILES,
    GENERATED_PROPERTY_DESCRIPTION,
    ITEM_TYPES_BY_VALUE_TYPE,
    MAXIMUM_VALUE_EXTENSION_URL,
    MINIMUM_VALUE_EXTENSION_URL,
    PATTERN_PROPERTY_DESCRIPTION,
    RESOURCE_MAP_EQUIVALENCE,
    RESOURCE_TYPE_CODE_SYSTEM_URL,
    RESOURCE_TYPE_VALUE_SET_URL,
    SEARCHABLE_PROPERTY_DESCRIPTION,
    TRACKED_ENTITY_ATTRIBUTE_TERMINOLOGY,
    TRACKED_ENTITY_TYPE_RESOURCE_MAP_DESCRIPTION,
    TRACKED_ENTITY_TYPE_RESOURCE_MAP_TITLE,
    TRACKED_ENTITY_TYPE_TERMINOLOGY,
    UNIQUE_PROPERTY_DESCRIPTION,
    AttributeSearchContext,
    CategoryOptionComboIn,
    FormKind,
    FormKindProfile,
    NumericBounds,
    PublishedTrackedEntityType,
    QuestionnaireItemIn,
    QuestionnaireNaming,
    QuestionnaireSourceIn,
    QuestionnaireStemPlan,
    ReferencedObjects,
    SupportTerminologyProfile,
    form_date_labels,
    form_period_type,
    form_repeatable,
    form_subject_type,
    item_type,
    plan_questionnaire_stems,
    published_tracked_entity_types,
    question_read_only,
    source_display_name,
    source_program,
    source_title_translations,
    unmapped_tracked_entity_type_notes,
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
    "form_collects_incident_date",
    "is_disaggregated",
    "is_multi_valued",
    "item_type",
    "link_id_collisions",
    "plan_questionnaire_stems",
    "question_code_system",
    "question_entity_level",
    "question_read_only",
    "registration_subject",
    "enable_behavior_of",
    "search_context_declarations",
    "source_description",
    "source_items",
    "source_program",
    "value_type_bounds",
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

_ENVIRONMENT = Environment(
    loader=PackageLoader("dhis2w_fhir.resources.questionnaires", "templates"),
    autoescape=select_autoescape(default=False),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)

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


class _EnableWhenView(BaseModel):
    """One `enableWhen` entry as the FSH literals its three lines take."""

    model_config = ConfigDict(frozen=True)

    question_literal: str
    operator_token: str
    """The R4 operator as FSH writes a code: `#exists`, and the comparisons quoted because `=` is a symbol."""

    answer_element: str
    answer_literal: str


class _ProgramRuleView(BaseModel):
    """One published program rule as the FSH literals its D2ProgramRule entry is assigned from."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name_literal: str
    description_literal: str | None = None
    condition_literal: str
    action_code: str
    name_translations: list[TranslationIn] = Field(default_factory=list)
    description_translations: list[TranslationIn] = Field(default_factory=list)


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
    read_only: bool = False
    item_control: bool = False
    description_literal: str | None = None
    """The DHIS2 free text about the object the item is asked from, or None when the instance states none."""

    description_translations: list[TranslationIn] = Field(default_factory=list)
    entity_level: bool | None = None
    """Whether the question's answer belongs to the tracked entity, or None when the form states no level."""

    bounds: list[_BoundView] = Field(default_factory=list)
    enable_when: list[_EnableWhenView] = Field(default_factory=list)
    """What shows the question - empty unless a program rule hides it on another question's answer."""

    enable_behavior: str | None = None
    """How several showing conditions join, written only where the question carries more than one."""


class _DateLabelView(BaseModel):
    """One date label as the sub-extension slice and the FSH literals the template writes."""

    model_config = ConfigDict(frozen=True)

    slice_name: str
    value_literal: str
    translations: list[TranslationIn] = Field(default_factory=list)


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
    description_literal: str
    """The `Title:` and `Description:` keyword literals, which name the artifact in the guide's own pages.

    Page furniture, so both carry the markup escaping the publisher's HTML needs. The two element
    literals below assign `title` and `description` on the resource itself, and those are data: a
    served Questionnaire spells the DHIS2 text byte for byte.
    """

    title_element_literal: str
    description_element_literal: str
    title_translations: list[TranslationIn] = Field(default_factory=list)
    """The form's NAME translations, riding the title element as one standard translation extension each."""

    subject_type: str
    identifier_system: str
    identifier_code_system: str
    identifier_code_literal: str
    grouping_identifiers: list[_GroupingIdentifierView] = Field(default_factory=list)
    attribute_identifiers: list[_AttributeIdentifierView] = Field(default_factory=list)
    form_type_extension: str
    form_type_code_system: str
    form_type_code: str
    collects_incident_date_extension: str
    collects_incident_date: bool | None = None
    """Whether the program this registration form enrols into collects an incident date, or None off that kind."""

    period_type_extension: str
    period_type: str | None = None
    """The DHIS2 period type an aggregate form is reported under, or None off that kind."""

    repeatable_extension: str
    repeatable: bool | None = None
    """Whether one enrollment may capture this stage more than once, or None off the stage kind."""

    date_labels_extension: str
    date_labels: list[_DateLabelView] = Field(default_factory=list)
    """The date labels this instance states, one sub-extension slice each; empty writes no extension."""

    description_extension_url: str
    """Absolute URL of the D2Description extension an item's free text rides.

    A URL rather than the FSH name every Questionnaire-level extension of this template takes, for
    the reason `entity_level_extension_url` is one: SUSHI merges a named extension slice into
    whatever soft-indexed `extension[+]` entry precedes it on the same element, and an item already
    carries its bounds and its level there.
    """

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

    program_rule_extension: str
    ig_status: IgStatus
    attribute_values: list[_AttributeValueView] = Field(default_factory=list)
    program_rules: list[_ProgramRuleView] = Field(default_factory=list)
    """The rules of this form's program neither tier expressed, published non-normatively."""

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

    form_name_literal: str | None = None
    """The DHIS2 form name as an FSH literal, or None when DHIS2 states none and the property is left off."""

    domain_code: str | None = None
    value_type_code: str | None = None
    unique_literal: str | None = None
    searchable_literal: str | None = None
    generated_literal: str | None = None
    pattern_literal: str | None = None
    """The reserved-value pattern, carried only by a generated attribute - the rest have none to state."""

    display_in_list_literal: str | None = None
    searchable_contexts: list[_SupportBooleanProperty] = Field(default_factory=list)
    category_properties: list[_SupportCategoryProperty] = Field(default_factory=list)
    designations: list[TranslationIn] = Field(default_factory=list)
    """The object's NAME translations, which render the concept display in each configured locale."""


class _SupportResourceMapping(BaseModel):
    """One published tracked entity type as a row of the resource map: the concept, and the resource it is."""

    model_config = ConfigDict(frozen=True)

    uid: str
    display_literal: str
    resource_type: str


class _SupportResourceMap(BaseModel):
    """The ConceptMap taking one support vocabulary's concepts onto the FHIR resource types they stand for."""

    model_config = ConfigDict(frozen=True)

    fsh_name: str
    concept_map_id: str
    value_set: str
    title_literal: str
    description_literal: str
    source_url: str
    target_code_system_url: str
    target_value_set_url: str
    equivalence: str
    mappings: list[_SupportResourceMapping] = Field(default_factory=list)


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
    form_name_property_description_literal: str
    domain_property_description_literal: str
    value_type_property_description_literal: str
    unique_property_description_literal: str
    searchable_property_description_literal: str
    generated_property_description_literal: str
    pattern_property_description_literal: str
    display_in_list_property_description_literal: str
    ig_status: IgStatus
    searchable_declarations: list[_SupportBooleanDeclaration] = Field(default_factory=list)
    category_declarations: list[_SupportCategoryDeclaration] = Field(default_factory=list)
    concepts: list[_SupportConcept] = Field(default_factory=list)
    resource_map: _SupportResourceMap | None = None
    """The ConceptMap published beside the pair, on the one pair whose concepts stand for a resource type."""

    @property
    def experimental(self) -> bool:
        """Whether the support pair is experimental - derived from the IG status."""
        return experimental_for_status(self.ig_status)

    @property
    def declares_code(self) -> bool:
        """Whether any concept carries a DHIS2 code, so the CodeSystem must declare the property."""
        return any(concept.code_literal is not None for concept in self.concepts)

    @property
    def declares_form_name(self) -> bool:
        """Whether any concept carries a DHIS2 form name, so the CodeSystem must declare the property."""
        return any(concept.form_name_literal is not None for concept in self.concepts)

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

    @property
    def declares_generated(self) -> bool:
        """Whether any concept says who writes its value, so the CodeSystem must declare the property."""
        return any(concept.generated_literal is not None for concept in self.concepts)

    @property
    def declares_pattern(self) -> bool:
        """Whether any concept carries a reserved-value pattern, so the CodeSystem must declare it."""
        return any(concept.pattern_literal is not None for concept in self.concepts)

    @property
    def declares_display_in_list(self) -> bool:
        """Whether any concept carries the working-list roll-up, so the CodeSystem must declare it."""
        return any(concept.display_in_list_literal is not None for concept in self.concepts)


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
    rule_plan = plan_program_rules(sources)
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
            program_rules=rule_plan.for_form(source.uid),
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
                    program_rule_uid_sub_extension=PROGRAM_RULE_UID_SUB_EXTENSION,
                    program_rule_name_sub_extension=PROGRAM_RULE_NAME_SUB_EXTENSION,
                    program_rule_description_sub_extension=PROGRAM_RULE_DESCRIPTION_SUB_EXTENSION,
                    program_rule_condition_sub_extension=PROGRAM_RULE_CONDITION_SUB_EXTENSION,
                    program_rule_action_sub_extension=PROGRAM_RULE_ACTION_SUB_EXTENSION,
                ),
            )
        )
    if referenced.data_elements:
        build.artifacts.append(_data_element_terminology(referenced.data_elements, names, config, ig_status=ig_status))
    if referenced.tracked_entity_attributes:
        build.artifacts.append(_tracked_entity_attribute_terminology(referenced, names, config, ig_status=ig_status))
    published_types = published_tracked_entity_types(sources, config.tracked_entity_types)
    if published_types:
        build.artifacts.append(
            _tracked_entity_type_terminology(published_types, names, config, canonical, ig_status=ig_status)
        )
    build.notes.extend(unmapped_tracked_entity_type_notes(published_types))
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
                f"{pluralize(len(index.unplanned_uids), 'option set')} a question binds "
                f"{verb_for_count(len(index.unplanned_uids), 'is', 'are')} absent from the option-set "
                "selection; the answerValueSet names are derived from the UID",
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
    program_rules: FormProgramRules,
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
        description_literal=page_text(source_description(source, profile)),
        title_element_literal=quote(display_name),
        description_element_literal=quote(source_description(source, profile)),
        title_translations=source_title_translations(source, locales),
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
        collects_incident_date_extension=foundation.collects_incident_date_extension,
        collects_incident_date=form_collects_incident_date(source),
        period_type_extension=foundation.period_type_extension,
        period_type=form_period_type(source),
        repeatable_extension=foundation.repeatable_extension,
        repeatable=form_repeatable(source),
        date_labels_extension=foundation.date_labels_extension,
        date_labels=_date_label_views(source, locales),
        description_extension_url=f"{canonical}/StructureDefinition/{foundation.description_extension_id}",
        assignment_extension=foundation.organisation_unit_assignment_extension,
        assignment_reference=assignments.reference_for(source),
        attribute_option_combos_extension=foundation.attribute_option_combos_extension,
        attribute_option_combo_value_set=_attribute_option_combo_value_set(source, attribute_combos),
        attribute_value_extension=foundation.attribute_value_extension,
        entity_level_extension_url=f"{canonical}/StructureDefinition/{foundation.entity_level_extension_id}",
        program_rule_extension=foundation.program_rule_extension,
        ig_status=ig_status,
        attribute_values=_attribute_value_views(source.attribute_values, attribute_codes),
        program_rules=_program_rule_views(program_rules.published, locales),
        items=_item_views(source, names, identities, locales, program_rules),
    )


def _program_rule_views(published: list[PublishedProgramRule], locales: list[str]) -> list[_ProgramRuleView]:
    """Project the rules this form does not express onto the literals their D2ProgramRule entries take."""
    return [
        _ProgramRuleView(
            uid=rule.uid,
            name_literal=quote(rule.name),
            description_literal=quote(rule.description) if rule.description else None,
            condition_literal=quote_verbatim(rule.condition),
            action_code=rule.action,
            name_translations=name_translations(rule.translations, locales),
            description_translations=description_translations(rule.translations, locales) if rule.description else [],
        )
        for rule in published
    ]


def _enable_when_views(shown: ItemEnableWhen | None, identities: dict[str, OptionSetIdentity]) -> list[_EnableWhenView]:
    """Project one question's showing conditions onto the FSH literals each of its lines takes."""
    if shown is None:
        return []
    return [
        _EnableWhenView(
            question_literal=quote(condition.question_link_id),
            operator_token=_operator_token(condition.operator),
            answer_element=condition.answer_element,
            answer_literal=_answer_literal(condition, identities),
        )
        for condition in shown.conditions
    ]


def _operator_token(operator: str) -> str:
    """One R4 operator as an FSH code: quoted for the comparisons, whose codes are punctuation."""
    return f"#{operator}" if operator.isalpha() else f'#"{operator}"'


def _answer_literal(condition: EnableWhenCondition, identities: dict[str, OptionSetIdentity]) -> str:
    """The typed answer one condition compares against, as the FSH literal its `answer[x]` takes."""
    if condition.answer_element == "answerCoding":
        identity = identities[condition.option_set_uid] if condition.option_set_uid else None
        system = identity.code_system_name if identity is not None else condition.option_set_uid
        return f"{system}#{condition.text}"
    if condition.answer_element == "answerBoolean":
        return "true" if condition.boolean else "false"
    if condition.answer_element == "answerInteger":
        return str(condition.integer)
    if condition.answer_element == "answerDecimal":
        return _decimal_answer_literal(condition.number)
    return quote(condition.text)


def _decimal_answer_literal(value: float) -> str:
    """A decimal answer as FSH writes it, a whole number keeping the value a decimal rather than an integer."""
    return str(int(value)) if value.is_integer() else str(value)


def _date_label_views(source: QuestionnaireSourceIn, locales: list[str]) -> list[_DateLabelView]:
    """Project one form's date labels onto the sub-extension slices the template writes, in slice order."""
    labels = form_date_labels(source, locales)
    slices = (
        (DATE_LABEL_ENROLLMENT_SUB_EXTENSION, labels.enrollment_date),
        (DATE_LABEL_INCIDENT_SUB_EXTENSION, labels.incident_date),
        (DATE_LABEL_EVENT_SUB_EXTENSION, labels.event_date),
    )
    return [
        _DateLabelView(slice_name=slice_name, value_literal=quote(label.value), translations=label.translations)
        for slice_name, label in slices
        if label is not None
    ]


def _attribute_option_combo_value_set(
    source: QuestionnaireSourceIn, attribute_combos: AttributeComboPlan
) -> str | None:
    """The FSH name of the ValueSet one form's responses draw an attribute option combo from, or None."""
    identity = attribute_combos.identity_for(source.uid)
    return None if identity is None else identity.value_set_name


def registration_subject(type_name: str) -> str:
    """One tracked entity type's own name as the sentence subject its registration form is described with.

    A DHIS2 instance registers focus areas, households, commodities, and malaria entities as readily
    as it registers people, so a form description that said "a person" would be describing an
    instance nobody has. The type's own name is what the form is about, so the type's own name is
    what the sentence says.

    The casing is the instance's, minus the capital a list label puts on its first word: a name whose
    remaining words are all lower case reads as a common noun mid-sentence ("Focus area" -> "a focus
    area"), while a name carrying a capital of its own is a proper name the instance means ("Malaria
    Entity" -> "a Malaria Entity"). The article follows the spelling that survives that.
    """
    name = flatten_whitespace(type_name)
    if not name:
        return "a subject"
    if not any(character.isupper() for character in name[1:]):
        name = name[0].lower() + name[1:]
    article = "an" if name[0].lower() in "aeiou" else "a"
    return f"{article} {name}"


def source_description(source: QuestionnaireSourceIn, profile: FormKindProfile) -> str:
    """The prose one form's Questionnaire describes itself with, a program stage naming its program too."""
    opening = f"DHIS2 {profile.label} {source.name} ({source.uid})"
    if source.kind == "tracked-entity":
        return (
            f"{opening} as a registration form: the tracked entity attributes the type itself collects, "
            f"captured when {registration_subject(source.name)} is registered without being enrolled in "
            "any program."
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
    program_rules: FormProgramRules,
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
                description_literal=quote(section.description) if section.description else None,
                description_translations=description_translations(section.translations, locales)
                if section.description
                else [],
            )
        )
        for item in section.items:
            views.extend(
                _question_views(item, names, identities, locales, depth=1, kind=source.kind, rules=program_rules)
            )
    for item in source.flat_items:
        views.extend(_question_views(item, names, identities, locales, depth=0, kind=source.kind, rules=program_rules))
    return views


def _question_views(
    item: QuestionnaireItemIn,
    names: QuestionnaireNaming,
    identities: dict[str, OptionSetIdentity],
    locales: list[str],
    depth: int,
    kind: FormKind,
    rules: FormProgramRules,
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
    bounds = _bound_views(item.value_type, resolved_item_type, rules.bounds_for(item.uid))
    shown = _enable_when_views(rules.enable_when_for(item.uid), identities)
    behavior = enable_behavior_of(rules.enable_when_for(item.uid))
    description_literal = quote(item.description) if item.description else None
    description_translated = description_translations(item.translations, locales) if item.description else []
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
                read_only=bool(question_read_only(item, kind)),
                description_literal=description_literal,
                description_translations=description_translated,
                entity_level=question_entity_level(item, kind),
                bounds=bounds,
                enable_when=shown,
                enable_behavior=behavior,
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
            description_literal=description_literal,
            description_translations=description_translated,
            enable_when=shown,
            enable_behavior=behavior,
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


def _bound_views(value_type: str, item_type: str, rule_bounds: list[ProgramRuleBound]) -> list[_BoundView]:
    """The `minValue` / `maxValue` extensions one question carries, from its value type and from any rule."""
    return [
        _BoundView(url=bound.url, element=bound.element, literal=bound.literal)
        for bound in merged_bounds(value_type_bounds(value_type, item_type), rule_bounds)
    ]


def value_type_bounds(value_type: str, item_type: str) -> list[ProgramRuleBound]:
    """The bounds one DHIS2 value type states on a question, in the element its item type takes."""
    bounds = BOUNDS_BY_VALUE_TYPE.get(value_type)
    element = BOUND_ELEMENTS_BY_ITEM_TYPE.get(item_type)
    if bounds is None or element is None:
        return []
    stated: list[ProgramRuleBound] = []
    if bounds.minimum_value is not None:
        stated.append(value_type_bound(MINIMUM_VALUE_EXTENSION_URL, element, bounds.minimum_value))
    if bounds.maximum_value is not None:
        stated.append(value_type_bound(MAXIMUM_VALUE_EXTENSION_URL, element, bounds.maximum_value))
    return stated


def enable_behavior_of(shown: ItemEnableWhen | None) -> str | None:
    """How a question's showing conditions join, or None when it carries none or only one."""
    return None if shown is None else shown.behavior


def form_collects_incident_date(source: QuestionnaireSourceIn) -> bool | None:
    """Whether the program a registration form enrols into collects an incident date, or None off that kind.

    Only a tracker registration form has an enrollment to date, so only it declares the fact - and it
    declares it either way, true and false alike, because the whole point of publishing it is that a
    reader never has to guess. Every other form kind states nothing: a data set, an event program, a
    stage, and a person-only registration create no enrollment, so there is no incident for one to follow.
    """
    if source.kind != "tracker":
        return None
    return source.displays_incident_date


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
            referenced.display_in_list[item.uid] = (
                referenced.display_in_list.get(item.uid, False) or item.display_in_list
            )
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
            form_name_literal=quote(item.form_name) if item.form_name else None,
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
            form_name_literal=quote(item.form_name) if item.form_name else None,
            value_type_code=item.value_type,
            unique_literal="true" if item.unique else "false",
            searchable_literal="true" if referenced.searchable_anywhere(item.uid) else "false",
            generated_literal="true" if item.generated else "false",
            pattern_literal=quote(item.pattern) if item.pattern else None,
            display_in_list_literal="true" if referenced.displayed_in_list_anywhere(item.uid) else "false",
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


def _tracked_entity_type_terminology(
    published: list[PublishedTrackedEntityType],
    names: QuestionnaireNaming,
    config: GenerateConfig,
    canonical: str,
    *,
    ig_status: IgStatus,
) -> FshArtifact:
    """Build `data-dictionary/tracked-entity-types.fsh`: the type vocabulary plus its resource map.

    The pair is the twin of the attribute pair one file over - the same `dhis2-code` property, the
    same designations under `[generate] locales` - over the objects the forms are *about* rather
    than the ones they ask. The ConceptMap in the same file is what makes the resource each type
    is published as readable off the guide: `[generate.tracked_entity_types]` states only the
    exceptions, so a consumer holding a type UID would otherwise have to hold this project's
    `fhir.toml` to know whether it is a `Patient`.
    """
    concepts = [
        _SupportConcept(
            uid=entry.uid,
            display_literal=quote(entry.name),
            code_literal=quote(entry.code) if entry.code else None,
            designations=name_translations(entry.translations, config.locales),
        )
        for entry in published
    ]
    return _support_terminology_artifact(
        concepts,
        TRACKED_ENTITY_TYPE_TERMINOLOGY,
        config,
        file_stem="tracked-entity-types",
        code_system=names.tracked_entity_type_code_system,
        code_system_id=names.tracked_entity_type_code_system_id,
        value_set=names.tracked_entity_type_value_set,
        value_set_id=names.tracked_entity_type_value_set_id,
        ig_status=ig_status,
        resource_map=_SupportResourceMap(
            fsh_name=names.tracked_entity_type_resource_map,
            concept_map_id=names.tracked_entity_type_resource_map_id,
            value_set=names.tracked_entity_type_value_set,
            title_literal=quote(TRACKED_ENTITY_TYPE_RESOURCE_MAP_TITLE),
            description_literal=quote(TRACKED_ENTITY_TYPE_RESOURCE_MAP_DESCRIPTION),
            source_url=code_system_canonical(canonical, names.tracked_entity_type_code_system_id),
            target_code_system_url=RESOURCE_TYPE_CODE_SYSTEM_URL,
            target_value_set_url=RESOURCE_TYPE_VALUE_SET_URL,
            equivalence=RESOURCE_MAP_EQUIVALENCE,
            mappings=[
                _SupportResourceMapping(
                    uid=entry.uid, display_literal=quote(entry.name), resource_type=entry.resource_type
                )
                for entry in published
            ],
        ),
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
    resource_map: _SupportResourceMap | None = None,
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
        form_name_property_description_literal=quote(terminology.form_name_property_description),
        domain_property_description_literal=quote(DOMAIN_PROPERTY_DESCRIPTION),
        value_type_property_description_literal=quote(terminology.value_type_property_description),
        unique_property_description_literal=quote(UNIQUE_PROPERTY_DESCRIPTION),
        searchable_property_description_literal=quote(SEARCHABLE_PROPERTY_DESCRIPTION),
        generated_property_description_literal=quote(GENERATED_PROPERTY_DESCRIPTION),
        pattern_property_description_literal=quote(PATTERN_PROPERTY_DESCRIPTION),
        display_in_list_property_description_literal=quote(DISPLAY_IN_LIST_PROPERTY_DESCRIPTION),
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
        resource_map=resource_map,
    )
    return FshArtifact(
        relative_path=f"{DATA_DICTIONARY_DIRECTORY}/{file_stem}.fsh",
        kind="terminology-pair",
        fsh_name=code_system,
        content=_ENVIRONMENT.get_template("support-terminology.fsh.jinja").render(terminology=view),
    )
