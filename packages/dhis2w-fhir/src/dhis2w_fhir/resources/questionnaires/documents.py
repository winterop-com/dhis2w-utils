"""FHIR JSON for the forms the FSH target compiles: one `Questionnaire` document per DHIS2 form.

The twin of the FSH emitter next door. Both read the same `QuestionnaireSourceIn` projection and
both decide the same things - the item type a value type answers as, which questions disaggregate
into cells, which option-set ValueSet a `#choice` is answered from - through the very functions
this package exports, so the two paths cannot drift apart. What differs is the target: the FSH
path writes SUSHI source that names an identifier system by its `$DHIS2-*` alias and a ValueSet
by a `Canonical(...)` call, while this path writes the finished R4 documents with every name
already absolute, exactly as SUSHI would have resolved it.

That equality is a test, not a hope: `test_fhir_questionnaire_parity.py` rebuilds the compiled
questionnaires of the local stack straight from the committed source fixtures and asserts each
one equals the SUSHI output byte for byte, key for key.

The data dictionary comes out of the same run: the two support CodeSystem/ValueSet pairs every
form kind shares - one over every data element the forms ask a question from, one over every
category option combo they disaggregate by.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.foundation.attribute_values import (
    attribute_value_extension_url,
    attribute_value_extensions,
    attribute_value_identifiers,
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
    TranslationIn,
    description_translations,
    name_translations,
    text_translations,
    translated_element,
)
from dhis2w_fhir.names import code_or_uid, flatten_whitespace
from dhis2w_fhir.notes import (
    GenerateNote,
    GenerateNoteCategory,
    aggregate_generate_note,
    pluralize,
    verb_for_count,
)
from dhis2w_fhir.r4 import (
    CodeableConcept,
    CodeSystem,
    CodeSystemConcept,
    CodeSystemConceptDesignation,
    CodeSystemConceptProperty,
    CodeSystemProperty,
    Coding,
    ConceptMap,
    ConceptMapGroup,
    ConceptMapGroupElement,
    ConceptMapGroupElementTarget,
    Extension,
    Identifier,
    Questionnaire,
    QuestionnaireItem,
    QuestionnaireItemEnableWhen,
    Reference,
    ValueSet,
    ValueSetCompose,
    ValueSetInclude,
)
from dhis2w_fhir.resources.attribute_combos.schemas import AttributeComboPlan
from dhis2w_fhir.resources.option_sets import (
    code_system_canonical,
    concept_map_canonical,
    option_set_identity_index,
    value_set_canonical,
)
from dhis2w_fhir.resources.questionnaires import (
    ITEM_CONTROL_CODE_SYSTEM_URL,
    ITEM_CONTROL_EXTENSION_URL,
    bound_option_set_uids,
    collect_referenced_objects,
    domain_code,
    enable_behavior_of,
    form_collects_incident_date,
    grouping_identifiers,
    is_disaggregated,
    is_multi_valued,
    item_type,
    question_entity_level,
    question_read_only,
    search_context_declarations,
    source_description,
    value_type_bounds,
)
from dhis2w_fhir.resources.questionnaires.assignments import AssignmentPlan
from dhis2w_fhir.resources.questionnaires.program_rules import (
    EnableWhenCondition,
    FormProgramRules,
    ItemEnableWhen,
    ProgramRuleBound,
    PublishedProgramRule,
    merged_bounds,
    plan_program_rules,
)
from dhis2w_fhir.resources.questionnaires.schemas import (
    CATEGORY_OPTION_COMBO_TERMINOLOGY,
    DATA_ELEMENT_TERMINOLOGY,
    DISPLAY_IN_LIST_PROPERTY,
    DISPLAY_IN_LIST_PROPERTY_DESCRIPTION,
    DOMAIN_PROPERTY_DESCRIPTION,
    FORM_KIND_PROFILES,
    GENERATED_PROPERTY,
    GENERATED_PROPERTY_DESCRIPTION,
    PATTERN_PROPERTY,
    PATTERN_PROPERTY_DESCRIPTION,
    RESOURCE_MAP_EQUIVALENCE,
    RESOURCE_TYPE_CODE_SYSTEM_URL,
    RESOURCE_TYPE_VALUE_SET_URL,
    SEARCHABLE_PROPERTY,
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
    plan_questionnaire_stems,
    published_tracked_entity_types,
    source_display_name,
    source_title_translations,
)
from dhis2w_fhir.status import IgStatus, experimental_for_status

if TYPE_CHECKING:
    from collections.abc import Mapping

    from dhis2w_fhir.attributes import AttributeCodeIndex
    from dhis2w_fhir.config import GenerateConfig
    from dhis2w_fhir.resources.categories.decomposition import CategoryDecomposition
    from dhis2w_fhir.resources.option_sets.schemas import OptionSetIdentity, OptionSetIdentityPlan

__all__ = [
    "DataDictionaryDocumentBuild",
    "QuestionnaireDocumentBuild",
    "build_data_dictionary_documents",
    "build_questionnaire_documents",
]

#: The `Questionnaire.item.enableWhen.operator` codes R4 admits, and how several conditions may join.
#: The translation computes each as a plain string, and a guard test asserts every one it can
#: produce is a member here.
_EnableWhenOperator = Literal["exists", "=", "!=", ">", "<", ">=", "<="]
_EnableBehavior = Literal["all", "any"]

#: The `Questionnaire.item.type` codes R4 admits. `item_type` computes one as a plain string from
#: a DHIS2 value type, and a guard test asserts every string it can produce is a member here.
_ItemTypeCode = Literal[
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

#: The `value[x]` element carrying a whole-number bound, as opposed to the decimal one.
_INTEGER_BOUND_ELEMENT = "valueInteger"

#: The concept property every support CodeSystem declares, carrying the DHIS2 code of its object.
_CODE_PROPERTY = "dhis2-code"

#: The concept property only the data-element CodeSystem declares, carrying the DHIS2 domain type.
_DOMAIN_PROPERTY = "domain"

#: The concept property the data-element and attribute CodeSystems declare, carrying the DHIS2 value type.
_VALUE_TYPE_PROPERTY = "value-type"

#: The concept property only the attribute CodeSystem declares, marking a business identifier.
_UNIQUE_PROPERTY = "unique"


class QuestionnaireDocumentBuild(BaseModel):
    """The Questionnaire documents one run builds, in emission order, with the notes building them raised."""

    model_config = ConfigDict(frozen=True)

    questionnaires: list[Questionnaire] = Field(default_factory=list)
    notes: list[GenerateNote] = Field(default_factory=list)


class DataDictionaryDocumentBuild(BaseModel):
    """The support terminology every generated Questionnaire shares, as the CodeSystem/ValueSet pairs it publishes.

    Every list is empty when the forms reference nothing of that kind: a run over forms that
    disaggregate no question publishes the data-element pair alone, exactly as the FSH target
    writes only the file it has content for.

    `concept_maps` holds the one map the dictionary publishes beside a pair: the resource type each
    tracked entity type's registrations are published as, which rides with the type vocabulary the
    way the FSH target writes both into one file.
    """

    model_config = ConfigDict(frozen=True)

    code_systems: list[CodeSystem] = Field(default_factory=list)
    value_sets: list[ValueSet] = Field(default_factory=list)
    concept_maps: list[ConceptMap] = Field(default_factory=list)


class _QuestionnaireSystems(BaseModel):
    """Every absolute URL a built Questionnaire names, resolved once from the canonical and the naming tokens.

    This is what the FSH path defers to SUSHI: an alias declared in `foundation/d2-aliases.fsh`,
    a `Canonical(D2FormType_CS)` call, a `Canonical(D2OS_..._VS)` binding. A served document
    carries the resolved URL, so the resolution happens here instead.
    """

    model_config = ConfigDict(frozen=True)

    canonical: str
    identifier_base: str
    identifier_system_base: str
    form_type_extension_url: str
    form_type_code_system_url: str
    collects_incident_date_extension_url: str
    period_type_extension_url: str
    repeatable_extension_url: str
    date_labels_extension_url: str
    description_extension_url: str
    assignment_extension_url: str
    attribute_option_combos_extension_url: str
    attribute_value_extension_url: str
    entity_level_extension_url: str
    program_rule_extension_url: str
    data_element_code_system_url: str
    tracked_entity_attribute_code_system_url: str
    category_option_combo_code_system_url: str

    @classmethod
    def from_config(cls, config: GenerateConfig, canonical: str) -> _QuestionnaireSystems:
        """Resolve the run's URLs from the IG canonical plus the `[generate]` identifier system base."""
        names = QuestionnaireNaming.from_naming(config.naming)
        foundation = FoundationNaming.from_naming(config.naming)
        return cls(
            canonical=canonical,
            identifier_base=f"{config.identifier_system_base}/id",
            identifier_system_base=config.identifier_system_base,
            form_type_extension_url=f"{canonical}/StructureDefinition/{foundation.form_type_extension_id}",
            form_type_code_system_url=code_system_canonical(canonical, foundation.form_type_code_system_id),
            collects_incident_date_extension_url=(
                f"{canonical}/StructureDefinition/{foundation.collects_incident_date_extension_id}"
            ),
            period_type_extension_url=f"{canonical}/StructureDefinition/{foundation.period_type_extension_id}",
            repeatable_extension_url=f"{canonical}/StructureDefinition/{foundation.repeatable_extension_id}",
            date_labels_extension_url=f"{canonical}/StructureDefinition/{foundation.date_labels_extension_id}",
            description_extension_url=f"{canonical}/StructureDefinition/{foundation.description_extension_id}",
            assignment_extension_url=(
                f"{canonical}/StructureDefinition/{foundation.organisation_unit_assignment_extension_id}"
            ),
            attribute_option_combos_extension_url=(
                f"{canonical}/StructureDefinition/{foundation.attribute_option_combos_extension_id}"
            ),
            attribute_value_extension_url=attribute_value_extension_url(config, canonical),
            entity_level_extension_url=f"{canonical}/StructureDefinition/{foundation.entity_level_extension_id}",
            program_rule_extension_url=f"{canonical}/StructureDefinition/{foundation.program_rule_extension_id}",
            data_element_code_system_url=code_system_canonical(canonical, names.data_element_code_system_id),
            tracked_entity_attribute_code_system_url=code_system_canonical(
                canonical, names.tracked_entity_attribute_code_system_id
            ),
            category_option_combo_code_system_url=code_system_canonical(
                canonical, names.category_option_combo_code_system_id
            ),
        )

    def identifier_system(self, segment: str) -> str:
        """The DHIS2 identifier system one object kind is named under (e.g. `.../id/data-set`)."""
        return f"{self.identifier_base}/{segment}"

    def question_code_system_url(self, kind: FormKind) -> str:
        """The support CodeSystem URL one form kind's questions are coded from - the twin of `question_code_system`."""
        if FORM_KIND_PROFILES[kind].question_subject == "tracked-entity-attribute":
            return self.tracked_entity_attribute_code_system_url
        return self.data_element_code_system_url

    def questionnaire_url(self, stem: str) -> str:
        """Canonical URL one form's Questionnaire is published at, closing on its identity stem."""
        return f"{self.canonical}/Questionnaire/{stem}"


class _SupportPair(BaseModel):
    """The CodeSystem and the ValueSet one data-dictionary entry publishes, over the same concepts."""

    model_config = ConfigDict(frozen=True)

    code_system: CodeSystem
    value_set: ValueSet


def build_questionnaire_documents(
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
) -> QuestionnaireDocumentBuild:
    """Build one FHIR Questionnaire per data set, event program, and tracker program stage.

    Takes the parameters `build_questionnaire_artifacts` takes and decides the same things from
    them, so a caller can build the FSH source and the served documents off one fetch:
    `option_set_plan` is the identity plan the terminology target emits from, and
    `attribute_codes` is the run's `uid -> code` join the D2AttributeValue extensions read from.
    `stem_plan` is the questionnaire surface's identity-stem plan; left None it resolves here
    through the very `plan_questionnaire_stems` call the FSH target resolves through, so the two
    paths cannot disagree on an id, a canonical URL, or a name. `assignments` names the
    assignment List each form is scoped by, and `attribute_combos` the attribute-option-combo
    ValueSet each form's responses are keyed from - the same two plans the FSH path renders its
    extensions from.
    """
    names = QuestionnaireNaming.from_naming(config.naming)
    systems = _QuestionnaireSystems.from_config(config, canonical)
    assignment_plan = assignments if assignments is not None else AssignmentPlan()
    attribute_combo_plan = attribute_combos if attribute_combos is not None else AttributeComboPlan()
    plan = stem_plan if stem_plan is not None else plan_questionnaire_stems(sources, config.naming.source)
    index = option_set_identity_index(option_set_plan, bound_option_set_uids(sources), config)
    rule_plan = plan_program_rules(sources)
    questionnaires = [
        _questionnaire_document(
            source,
            names,
            systems,
            index.identities,
            stem_plan=plan,
            ig_status=ig_status,
            attribute_codes=attribute_codes,
            assignments=assignment_plan,
            attribute_combos=attribute_combo_plan,
            tracked_entity_types=config.tracked_entity_types,
            locales=config.locales,
            program_rules=rule_plan.for_form(source.uid),
        )
        for source in sorted(sources, key=lambda item: (item.name, item.uid))
    ]
    notes: list[GenerateNote] = list(plan.targets.notes)
    if index.unplanned_uids:
        notes.append(
            aggregate_generate_note(
                GenerateNoteCategory.SELECTION_GAP,
                f"{pluralize(len(index.unplanned_uids), 'option set')} a question binds "
                f"{verb_for_count(len(index.unplanned_uids), 'is', 'are')} absent from the option-set "
                "selection; the answerValueSet names are derived from the UID",
                index.unplanned_uids,
            )
        )
    return QuestionnaireDocumentBuild(questionnaires=questionnaires, notes=notes)


def build_data_dictionary_documents(
    sources: list[QuestionnaireSourceIn],
    config: GenerateConfig,
    canonical: str,
    *,
    ig_status: IgStatus,
    decomposition: CategoryDecomposition | None = None,
) -> DataDictionaryDocumentBuild:
    """Build the support CodeSystem/ValueSet pairs over the objects the given forms reference.

    One pair over every data element a question is asked from, one over every tracked entity
    attribute a registration form asks about, one over every category option combo the aggregate
    forms disaggregate by - the JSON twin of `data-dictionary/`.

    `decomposition` states what each category option combo is composed of, so every combo concept
    carries one `Coding`-valued property per category axis into that category's own CodeSystem.
    """
    names = QuestionnaireNaming.from_naming(config.naming)
    referenced = ReferencedObjects()
    for source in sorted(sources, key=lambda item: (item.name, item.uid)):
        collect_referenced_objects(source, referenced)
    pairs: list[_SupportPair] = []
    if referenced.data_elements:
        pairs.append(
            _support_pair(
                _data_element_concepts(referenced.data_elements, config.locales),
                DATA_ELEMENT_TERMINOLOGY,
                config,
                canonical,
                code_system_name=names.data_element_code_system,
                code_system_id=names.data_element_code_system_id,
                value_set_name=names.data_element_value_set,
                value_set_id=names.data_element_value_set_id,
                ig_status=ig_status,
            )
        )
    if referenced.tracked_entity_attributes:
        pairs.append(
            _support_pair(
                _tracked_entity_attribute_concepts(referenced, config.locales),
                TRACKED_ENTITY_ATTRIBUTE_TERMINOLOGY,
                config,
                canonical,
                code_system_name=names.tracked_entity_attribute_code_system,
                code_system_id=names.tracked_entity_attribute_code_system_id,
                value_set_name=names.tracked_entity_attribute_value_set,
                value_set_id=names.tracked_entity_attribute_value_set_id,
                ig_status=ig_status,
                search_contexts=search_context_declarations(referenced),
            )
        )
    published_types = published_tracked_entity_types(sources, config.tracked_entity_types)
    if published_types:
        pairs.append(
            _support_pair(
                _tracked_entity_type_concepts(published_types, config.locales),
                TRACKED_ENTITY_TYPE_TERMINOLOGY,
                config,
                canonical,
                code_system_name=names.tracked_entity_type_code_system,
                code_system_id=names.tracked_entity_type_code_system_id,
                value_set_name=names.tracked_entity_type_value_set,
                value_set_id=names.tracked_entity_type_value_set_id,
                ig_status=ig_status,
            )
        )
    if referenced.option_combos:
        pairs.append(
            _support_pair(
                _option_combo_concepts(referenced.option_combos, decomposition),
                CATEGORY_OPTION_COMBO_TERMINOLOGY,
                config,
                canonical,
                code_system_name=names.category_option_combo_code_system,
                code_system_id=names.category_option_combo_code_system_id,
                value_set_name=names.category_option_combo_value_set,
                value_set_id=names.category_option_combo_value_set_id,
                ig_status=ig_status,
                decomposition=decomposition,
            )
        )
    return DataDictionaryDocumentBuild(
        code_systems=[pair.code_system for pair in pairs],
        value_sets=[pair.value_set for pair in pairs],
        concept_maps=(
            [_tracked_entity_type_resource_map(published_types, names, canonical, ig_status=ig_status)]
            if published_types
            else []
        ),
    )


def _tracked_entity_type_concepts(
    published: list[PublishedTrackedEntityType], locales: list[str]
) -> list[CodeSystemConcept]:
    """One concept per tracked entity type the run publishes, displayed under the name the instance holds."""
    return [
        CodeSystemConcept(
            code=entry.uid,
            display=flatten_whitespace(entry.name),
            property=_code_property(entry.code) or None,
            designation=_designations(entry.translations, locales),
        )
        for entry in published
    ]


def _tracked_entity_type_resource_map(
    published: list[PublishedTrackedEntityType],
    names: QuestionnaireNaming,
    canonical: str,
    *,
    ig_status: IgStatus,
) -> ConceptMap:
    """Build the map taking every published tracked entity type onto the FHIR resource type it is published as.

    One group, sourced from the type CodeSystem and targeting the R4 resource-type code system, one
    row per published type. The row's target is what `tracked_entity_type_subject_type` resolved -
    the same call the form's `subjectType` came out of - and its display is the instance's own name,
    so a consumer holding a type UID reads both the resource and what the instance calls the thing.
    """
    return ConceptMap(
        id=names.tracked_entity_type_resource_map_id,
        url=concept_map_canonical(canonical, names.tracked_entity_type_resource_map_id),
        name=names.tracked_entity_type_resource_map,
        title=TRACKED_ENTITY_TYPE_RESOURCE_MAP_TITLE,
        description=TRACKED_ENTITY_TYPE_RESOURCE_MAP_DESCRIPTION,
        status=ig_status,
        experimental=experimental_for_status(ig_status),
        sourceCanonical=value_set_canonical(canonical, names.tracked_entity_type_value_set_id),
        targetCanonical=RESOURCE_TYPE_VALUE_SET_URL,
        group=[
            ConceptMapGroup(
                source=code_system_canonical(canonical, names.tracked_entity_type_code_system_id),
                target=RESOURCE_TYPE_CODE_SYSTEM_URL,
                element=[
                    ConceptMapGroupElement(
                        code=entry.uid,
                        display=flatten_whitespace(entry.name),
                        target=[
                            ConceptMapGroupElementTarget(code=entry.resource_type, equivalence=RESOURCE_MAP_EQUIVALENCE)
                        ],
                    )
                    for entry in published
                ],
            )
        ],
    )


def _questionnaire_document(
    source: QuestionnaireSourceIn,
    names: QuestionnaireNaming,
    systems: _QuestionnaireSystems,
    identities: dict[str, OptionSetIdentity],
    *,
    stem_plan: QuestionnaireStemPlan,
    ig_status: IgStatus,
    attribute_codes: AttributeCodeIndex,
    assignments: AssignmentPlan,
    attribute_combos: AttributeComboPlan,
    tracked_entity_types: Mapping[str, str],
    locales: list[str],
    program_rules: FormProgramRules,
) -> Questionnaire:
    """Build one form's Questionnaire, every name already resolved to the URL it is served under.

    The identity stem carries the artifact identity - `id`, the canonical URL, the computational
    `name` - while the identifier slices keep the DHIS2 id and code as the data they are.
    `title` carries the DHIS2 name verbatim because it is data, while `description` is the page
    furniture the IG publisher pastes into HTML and takes the same markup escaping the FSH
    `Description:` keyword does. `tracked_entity_types` is the project's tracked-entity-type map,
    read through the very `form_subject_type` call the FSH path reads it through.
    """
    profile = FORM_KIND_PROFILES[source.kind]
    return Questionnaire(
        id=stem_plan.targets.stem_for(source.uid),
        url=systems.questionnaire_url(stem_plan.targets.stem_for(source.uid)),
        title=flatten_whitespace(source_display_name(source)),
        title_element=translated_element(source_title_translations(source, locales)),
        description=flatten_whitespace(source_description(source, profile)),
        extension=[
            Extension(url=systems.form_type_extension_url, valueCode=source.kind),
            *_collects_incident_date_extension(source, systems),
            *_period_type_extension(source, systems),
            *_repeatable_extension(source, systems),
            *_date_labels_extension(source, systems, locales),
            *_assignment_extension(source, systems, assignments),
            *_attribute_option_combos_extension(source, systems, attribute_combos),
            *_program_rule_extensions(program_rules.published, systems, locales),
            *attribute_value_extensions(
                source.attribute_values, attribute_codes, systems.attribute_value_extension_url
            ),
        ],
        identifier=_identifiers(source, profile, systems, attribute_codes),
        name=names.questionnaire_name(source.kind, stem_plan.targets.fsh_segment_for(source.uid)),
        status=ig_status,
        experimental=experimental_for_status(ig_status),
        subjectType=[form_subject_type(source, tracked_entity_types)],
        code=[Coding(system=systems.form_type_code_system_url, code=source.kind)],
        item=_items(source, systems, identities, locales, program_rules) or None,
    )


def _collects_incident_date_extension(
    source: QuestionnaireSourceIn, systems: _QuestionnaireSystems
) -> tuple[Extension, ...]:
    """The D2CollectsIncidentDate extension a registration form declares, or nothing on every other kind."""
    collects = form_collects_incident_date(source)
    if collects is None:
        return ()
    return (Extension(url=systems.collects_incident_date_extension_url, valueBoolean=collects),)


def _period_type_extension(source: QuestionnaireSourceIn, systems: _QuestionnaireSystems) -> tuple[Extension, ...]:
    """The D2PeriodType extension an aggregate form declares, or nothing on every other kind."""
    period_type = form_period_type(source)
    if period_type is None:
        return ()
    return (Extension(url=systems.period_type_extension_url, valueCode=period_type),)


def _repeatable_extension(source: QuestionnaireSourceIn, systems: _QuestionnaireSystems) -> tuple[Extension, ...]:
    """The D2Repeatable extension a tracker program stage form declares, or nothing on every other kind."""
    repeatable = form_repeatable(source)
    if repeatable is None:
        return ()
    return (Extension(url=systems.repeatable_extension_url, valueBoolean=repeatable),)


def _date_labels_extension(
    source: QuestionnaireSourceIn, systems: _QuestionnaireSystems, locales: list[str]
) -> tuple[Extension, ...]:
    """The D2DateLabels extension one form carries, or nothing when the instance labels none of its dates."""
    labels = form_date_labels(source, locales)
    slices = (
        (DATE_LABEL_ENROLLMENT_SUB_EXTENSION, labels.enrollment_date),
        (DATE_LABEL_INCIDENT_SUB_EXTENSION, labels.incident_date),
        (DATE_LABEL_EVENT_SUB_EXTENSION, labels.event_date),
    )
    carried = [
        Extension(
            url=slice_name,
            valueString=flatten_whitespace(label.value),
            valueString_element=translated_element(label.translations),
        )
        for slice_name, label in slices
        if label is not None
    ]
    if not carried:
        return ()
    return (Extension(url=systems.date_labels_extension_url, extension=carried),)


def _description_extension(
    description: str | None, translations: list[TranslationIn], locales: list[str], systems: _QuestionnaireSystems
) -> tuple[Extension, ...]:
    """The D2Description extension one item carries, or nothing when DHIS2 states no free text for it."""
    if not description:
        return ()
    return (
        Extension(
            url=systems.description_extension_url,
            valueString=flatten_whitespace(description),
            valueString_element=translated_element(description_translations(translations, locales)),
        ),
    )


def _assignment_extension(
    source: QuestionnaireSourceIn, systems: _QuestionnaireSystems, assignments: AssignmentPlan
) -> tuple[Extension, ...]:
    """The D2OrganisationUnitAssignment extension of one form, or nothing when it publishes no assignment."""
    reference = assignments.reference_for(source)
    if reference is None:
        return ()
    return (Extension(url=systems.assignment_extension_url, valueReference=Reference(reference=reference)),)


def _attribute_option_combos_extension(
    source: QuestionnaireSourceIn, systems: _QuestionnaireSystems, attribute_combos: AttributeComboPlan
) -> tuple[Extension, ...]:
    """The D2AttributeOptionCombos extension of one form, or nothing when it rides the default combo."""
    identity = attribute_combos.identity_for(source.uid)
    if identity is None:
        return ()
    return (
        Extension(
            url=systems.attribute_option_combos_extension_url,
            valueCanonical=value_set_canonical(systems.canonical, identity.value_set_id),
        ),
    )


def _identifiers(
    source: QuestionnaireSourceIn,
    profile: FormKindProfile,
    systems: _QuestionnaireSystems,
    attribute_codes: AttributeCodeIndex,
) -> list[Identifier]:
    """One form's DHIS2 identifiers: its UID, its code, whatever groups it, then its unique attribute values."""
    identifiers = [
        Identifier(system=systems.identifier_system(profile.identifier_segment), value=source.uid),
        Identifier(
            system=systems.identifier_system(profile.code_identifier_segment),
            value=code_or_uid(source.code, source.uid),
        ),
    ]
    identifiers.extend(
        Identifier(system=systems.identifier_system(grouping.segment), value=grouping.value)
        for grouping in grouping_identifiers(source)
    )
    identifiers.extend(
        attribute_value_identifiers(source.attribute_values, attribute_codes, systems.identifier_system_base)
    )
    return identifiers


def _program_rule_extensions(
    published: list[PublishedProgramRule], systems: _QuestionnaireSystems, locales: list[str]
) -> list[Extension]:
    """One D2ProgramRule extension per rule this form does not express, in the instance's own order."""
    return [
        Extension(
            url=systems.program_rule_extension_url,
            extension=[
                Extension(url=PROGRAM_RULE_UID_SUB_EXTENSION, valueId=rule.uid),
                Extension(
                    url=PROGRAM_RULE_NAME_SUB_EXTENSION,
                    valueString=flatten_whitespace(rule.name),
                    valueString_element=translated_element(name_translations(rule.translations, locales)),
                ),
                Extension(url=PROGRAM_RULE_CONDITION_SUB_EXTENSION, valueString=rule.condition),
                Extension(url=PROGRAM_RULE_ACTION_SUB_EXTENSION, valueCode=rule.action),
                # Last, because that is where SUSHI puts the optional slice: the compiled guide and
                # the served document have to carry one order, and SUSHI's is the one to match.
                *(
                    [
                        Extension(
                            url=PROGRAM_RULE_DESCRIPTION_SUB_EXTENSION,
                            valueString=flatten_whitespace(rule.description),
                            valueString_element=translated_element(
                                description_translations(rule.translations, locales)
                            ),
                        )
                    ]
                    if rule.description
                    else []
                ),
            ],
        )
        for rule in published
    ]


def _enable_when(
    shown: ItemEnableWhen | None, identities: dict[str, OptionSetIdentity], systems: _QuestionnaireSystems
) -> list[QuestionnaireItemEnableWhen] | None:
    """One question's showing conditions as R4 states them, or None where no rule hides it."""
    if shown is None:
        return None
    return [_enable_when_entry(condition, identities, systems) for condition in shown.conditions]


def _enable_when_entry(
    condition: EnableWhenCondition, identities: dict[str, OptionSetIdentity], systems: _QuestionnaireSystems
) -> QuestionnaireItemEnableWhen:
    """One condition, its answer landing on the `answer[x]` its question's item type compares on."""
    entry = QuestionnaireItemEnableWhen(question=condition.question_link_id, operator=_enable_when_operator(condition))
    if condition.answer_element == "answerCoding":
        identity = identities[condition.option_set_uid] if condition.option_set_uid else None
        system = code_system_canonical(systems.canonical, identity.code_system_id) if identity is not None else None
        return entry.model_copy(update={"answerCoding": Coding(system=system, code=condition.text)})
    if condition.answer_element == "answerBoolean":
        return entry.model_copy(update={"answerBoolean": condition.boolean})
    if condition.answer_element == "answerInteger":
        return entry.model_copy(update={"answerInteger": condition.integer})
    if condition.answer_element == "answerDecimal":
        return entry.model_copy(update={"answerDecimal": _decimal_answer(condition.number)})
    return entry.model_copy(update={condition.answer_element: condition.text})


def _enable_when_operator(condition: EnableWhenCondition) -> _EnableWhenOperator:
    """Read an operator computed as a plain string as the R4 code it is; a guard test pins the two together."""
    return cast(_EnableWhenOperator, condition.operator)


def _decimal_answer(value: float) -> int | float:
    """A decimal answer, kept a whole number where it is one so the document matches what SUSHI compiles."""
    return int(value) if value.is_integer() else value


def _items(
    source: QuestionnaireSourceIn,
    systems: _QuestionnaireSystems,
    identities: dict[str, OptionSetIdentity],
    locales: list[str],
    program_rules: FormProgramRules,
) -> list[QuestionnaireItem]:
    """Build the form's item tree: one group per section holding its questions, then the unsectioned tail."""
    items: list[QuestionnaireItem] = []
    for section in source.sections:
        children = [
            child
            for item in section.items
            for child in _data_element_items(item, source, systems, identities, locales, program_rules)
        ]
        items.append(
            QuestionnaireItem(
                linkId=section.uid,
                text=flatten_whitespace(section.name),
                text_element=translated_element(name_translations(section.translations, locales)),
                type="group",
                enableWhen=_enable_when(program_rules.enable_when_for(section.uid), identities, systems),
                enableBehavior=_enable_behavior(program_rules.enable_when_for(section.uid)),
                extension=[
                    *_description_extension(section.description, section.translations, locales, systems),
                    *(
                        [_item_control_extension()]
                        if any(is_disaggregated(item, source.kind) for item in section.items)
                        else []
                    ),
                ]
                or None,
                item=children or None,
            )
        )
    for item in source.flat_items:
        items.extend(_data_element_items(item, source, systems, identities, locales, program_rules))
    return items


def _data_element_items(
    item: QuestionnaireItemIn,
    source: QuestionnaireSourceIn,
    systems: _QuestionnaireSystems,
    identities: dict[str, OptionSetIdentity],
    locales: list[str],
    program_rules: FormProgramRules,
) -> list[QuestionnaireItem]:
    """Build one data element's items: a question, or a group holding one cell per category option combo.

    A cell asks the very question its data element does, so it takes the element's item type,
    its answer binding, its repeats, and its bounds - only the `linkId`, the text, the code, and
    which cells are required differ.
    """
    code = [
        Coding(
            system=systems.question_code_system_url(source.kind),
            code=item.uid,
            display=flatten_whitespace(item.name),
        )
    ]
    text = flatten_whitespace(item.form_name or item.name)
    text_element = translated_element(
        text_translations(item.translations, locales, form_named=item.form_name is not None)
    )
    resolved_item_type = _item_type_code(item_type(item))
    answer_value_set = _answer_value_set(item, identities, systems.canonical)
    repeats = is_multi_valued(item.value_type, resolved_item_type) or None
    bounds = _bound_extensions(item.value_type, resolved_item_type, program_rules.bounds_for(item.uid))
    shown = program_rules.enable_when_for(item.uid)
    description = _description_extension(item.description, item.translations, locales, systems)
    if not is_disaggregated(item, source.kind):
        extensions = [*description, *bounds, *_entity_level_extension(item, source.kind, systems)]
        return [
            QuestionnaireItem(
                linkId=item.uid,
                code=code,
                text=text,
                text_element=text_element,
                type=resolved_item_type,
                enableWhen=_enable_when(shown, identities, systems),
                enableBehavior=_enable_behavior(shown),
                answerValueSet=answer_value_set,
                required=item.compulsory or None,
                repeats=repeats,
                readOnly=question_read_only(item, source.kind),
                extension=extensions or None,
            )
        ]
    category_combo = item.category_combo
    option_combos = category_combo.option_combos if category_combo is not None else []
    cells = [
        QuestionnaireItem(
            linkId=f"{item.uid}.{option_combo.uid}",
            code=[
                Coding(
                    system=systems.category_option_combo_code_system_url,
                    code=option_combo.uid,
                    display=flatten_whitespace(option_combo.name),
                )
            ],
            text=flatten_whitespace(option_combo.name),
            type=resolved_item_type,
            answerValueSet=answer_value_set,
            required=(option_combo.uid in item.required_option_combo_uids) or None,
            repeats=repeats,
            extension=bounds or None,
        )
        for option_combo in option_combos
    ]
    return [
        QuestionnaireItem(
            linkId=item.uid,
            code=code,
            text=text,
            text_element=text_element,
            type="group",
            enableWhen=_enable_when(shown, identities, systems),
            enableBehavior=_enable_behavior(shown),
            required=item.compulsory or None,
            extension=list(description) or None,
            item=cells or None,
        )
    ]


def _entity_level_extension(
    item: QuestionnaireItemIn, kind: FormKind, systems: _QuestionnaireSystems
) -> tuple[Extension, ...]:
    """The D2EntityLevel extension one registration question carries, or nothing on every other question."""
    entity_level = question_entity_level(item, kind)
    if entity_level is None:
        return ()
    return (Extension(url=systems.entity_level_extension_url, valueBoolean=entity_level),)


def _item_control_extension() -> Extension:
    """The item-control extension rendering a section of disaggregated questions as a grid."""
    return Extension(
        url=ITEM_CONTROL_EXTENSION_URL,
        valueCodeableConcept=CodeableConcept(coding=[Coding(system=ITEM_CONTROL_CODE_SYSTEM_URL, code="gtable")]),
    )


def _answer_value_set(
    item: QuestionnaireItemIn, identities: dict[str, OptionSetIdentity], canonical: str
) -> str | None:
    """The option-set ValueSet an option-set-bound question is answered from, at the URL the run publishes it."""
    if item.option_set_uid is None:
        return None
    return value_set_canonical(canonical, identities[item.option_set_uid].value_set_id)


def _bound_extensions(value_type: str, resolved_item_type: str, rule_bounds: list[ProgramRuleBound]) -> list[Extension]:
    """The `minValue` / `maxValue` extensions one question carries, from its value type and from any rule."""
    return [
        _bound_extension(bound)
        for bound in merged_bounds(value_type_bounds(value_type, resolved_item_type), rule_bounds)
    ]


def _bound_extension(bound: ProgramRuleBound) -> Extension:
    """One bound as its extension, the number landing on `valueInteger` or on `valueDecimal`."""
    if bound.element == _INTEGER_BOUND_ELEMENT:
        return Extension(url=bound.url, valueInteger=bound.integer)
    return Extension(url=bound.url, valueDecimal=_decimal_answer(bound.decimal or 0.0))


def _enable_behavior(shown: ItemEnableWhen | None) -> _EnableBehavior | None:
    """How a question's showing conditions join, read as the R4 code it is."""
    behavior = enable_behavior_of(shown)
    return None if behavior is None else cast(_EnableBehavior, behavior)


def _item_type_code(value: str) -> _ItemTypeCode:
    """Read an item type computed as a plain string as the R4 code it is; a guard test pins the two together."""
    return cast(_ItemTypeCode, value)


def _data_element_concepts(
    data_elements: dict[str, QuestionnaireItemIn], locales: list[str]
) -> list[CodeSystemConcept]:
    """One concept per referenced data element, carrying its DHIS2 code and its domain type."""
    concepts: list[CodeSystemConcept] = []
    for item in sorted(data_elements.values(), key=lambda entry: (entry.name, entry.uid)):
        properties = _code_property(item.code)
        domain = domain_code(item.domain_type)
        if domain is not None:
            properties.append(CodeSystemConceptProperty(code=_DOMAIN_PROPERTY, valueCode=domain))
        properties.append(CodeSystemConceptProperty(code=_VALUE_TYPE_PROPERTY, valueCode=item.value_type))
        concepts.append(
            CodeSystemConcept(
                code=item.uid,
                display=flatten_whitespace(item.name),
                property=properties,
                designation=_designations(item.translations, locales),
            )
        )
    return concepts


def _designations(translations: list[TranslationIn], locales: list[str]) -> list[CodeSystemConceptDesignation] | None:
    """One concept's NAME translations as designations, or None when it carries none in the configured locales."""
    designations = [
        CodeSystemConceptDesignation(language=translation.locale, value=flatten_whitespace(translation.value))
        for translation in name_translations(translations, locales)
    ]
    return designations or None


def _tracked_entity_attribute_concepts(referenced: ReferencedObjects, locales: list[str]) -> list[CodeSystemConcept]:
    """One concept per referenced tracked entity attribute: its code, value type, uniqueness, searchability.

    The searchability answers follow the same order the FSH path writes them in: the roll-up over
    every context the run publishes, then one property per context that asked the attribute.
    """
    return [
        CodeSystemConcept(
            code=item.uid,
            display=flatten_whitespace(item.name),
            property=[
                *_code_property(item.code),
                CodeSystemConceptProperty(code=_VALUE_TYPE_PROPERTY, valueCode=item.value_type),
                CodeSystemConceptProperty(code=_UNIQUE_PROPERTY, valueBoolean=item.unique),
                CodeSystemConceptProperty(
                    code=SEARCHABLE_PROPERTY, valueBoolean=referenced.searchable_anywhere(item.uid)
                ),
                CodeSystemConceptProperty(code=GENERATED_PROPERTY, valueBoolean=item.generated),
                *([CodeSystemConceptProperty(code=PATTERN_PROPERTY, valueString=item.pattern)] if item.pattern else []),
                CodeSystemConceptProperty(
                    code=DISPLAY_IN_LIST_PROPERTY, valueBoolean=referenced.displayed_in_list_anywhere(item.uid)
                ),
                *(
                    CodeSystemConceptProperty(code=context.property_code, valueBoolean=context.searchable)
                    for context in referenced.contexts_for(item.uid)
                ),
            ],
            designation=_designations(item.translations, locales),
        )
        for item in sorted(referenced.tracked_entity_attributes.values(), key=lambda entry: (entry.name, entry.uid))
    ]


def _option_combo_concepts(
    option_combos: dict[str, CategoryOptionComboIn], decomposition: CategoryDecomposition | None
) -> list[CodeSystemConcept]:
    """One concept per referenced category option combo: the DHIS2 code it disaggregates under, then its axes.

    The category properties follow the code so a reader meets the combo's own identity first and
    the parts it was built from after, in the order its category combo splits over them.
    """
    concepts: list[CodeSystemConcept] = []
    for option_combo in sorted(option_combos.values(), key=lambda entry: (entry.name, entry.uid)):
        properties = [
            *_code_property(option_combo.code),
            *([] if decomposition is None else decomposition.properties_for(option_combo.uid)),
        ]
        concepts.append(
            CodeSystemConcept(
                code=option_combo.uid,
                display=flatten_whitespace(option_combo.name),
                property=properties or None,
            )
        )
    return concepts


def _code_property(code: str | None) -> list[CodeSystemConceptProperty]:
    """The `dhis2-code` property one concept carries, or nothing at all when DHIS2 states no code.

    A concept's own code is already the DHIS2 UID, so falling back to it here would publish the UID
    twice - once truthfully, once under a label saying it is the object's DHIS2 code.
    """
    if not code:
        return []
    return [CodeSystemConceptProperty(code=_CODE_PROPERTY, valueString=code)]


def _support_pair(
    concepts: list[CodeSystemConcept],
    terminology: SupportTerminologyProfile,
    config: GenerateConfig,
    canonical: str,
    *,
    code_system_name: str,
    code_system_id: str,
    value_set_name: str,
    value_set_id: str,
    ig_status: IgStatus,
    decomposition: CategoryDecomposition | None = None,
    search_contexts: list[AttributeSearchContext] | None = None,
) -> _SupportPair:
    """Build one support pair: a complete CodeSystem over the concepts, and the ValueSet including it whole."""
    code_system_url = code_system_canonical(canonical, code_system_id)
    value_set_url = value_set_canonical(canonical, value_set_id)
    experimental = experimental_for_status(ig_status)
    return _SupportPair(
        code_system=CodeSystem(
            id=code_system_id,
            url=code_system_url,
            name=code_system_name,
            title=terminology.title,
            description=terminology.description,
            status=ig_status,
            experimental=experimental,
            caseSensitive=True,
            content="complete",
            count=len(concepts),
            valueSet=value_set_url,
            # None rather than an empty list: a pair whose concepts all carry a bare code declares
            # no property, and the FSH template writes no property block at all for that pair.
            property=_property_declarations(concepts, terminology, config, decomposition, search_contexts) or None,
            concept=concepts,
        ),
        value_set=ValueSet(
            id=value_set_id,
            url=value_set_url,
            name=value_set_name,
            title=terminology.title,
            description=terminology.description,
            status=ig_status,
            experimental=experimental,
            compose=ValueSetCompose(include=[ValueSetInclude(system=code_system_url)]),
        ),
    )


def _property_declarations(
    concepts: list[CodeSystemConcept],
    terminology: SupportTerminologyProfile,
    config: GenerateConfig,
    decomposition: CategoryDecomposition | None = None,
    search_contexts: list[AttributeSearchContext] | None = None,
) -> list[CodeSystemProperty]:
    """Declare every concept property the built concepts actually carry, under the configured property base."""
    property_base = f"{config.identifier_system_base}/property"
    declarations: list[CodeSystemProperty] = []
    carries_code = any(
        concept_property.code == _CODE_PROPERTY for concept in concepts for concept_property in concept.property or []
    )
    if carries_code:
        declarations.append(
            CodeSystemProperty(
                code=_CODE_PROPERTY,
                uri=f"{property_base}/{_CODE_PROPERTY}",
                description=terminology.code_property_description,
                type="string",
            )
        )
    carries_domain = any(
        concept_property.code == _DOMAIN_PROPERTY for concept in concepts for concept_property in concept.property or []
    )
    if carries_domain:
        declarations.append(
            CodeSystemProperty(
                code=_DOMAIN_PROPERTY,
                uri=f"{property_base}/{_DOMAIN_PROPERTY}",
                description=DOMAIN_PROPERTY_DESCRIPTION,
                type="code",
            )
        )
    carries_value_type = any(
        concept_property.code == _VALUE_TYPE_PROPERTY
        for concept in concepts
        for concept_property in concept.property or []
    )
    if carries_value_type:
        declarations.append(
            CodeSystemProperty(
                code=_VALUE_TYPE_PROPERTY,
                uri=f"{property_base}/{_VALUE_TYPE_PROPERTY}",
                description=terminology.value_type_property_description,
                type="code",
            )
        )
    carries_unique = any(
        concept_property.code == _UNIQUE_PROPERTY for concept in concepts for concept_property in concept.property or []
    )
    if carries_unique:
        declarations.append(
            CodeSystemProperty(
                code=_UNIQUE_PROPERTY,
                uri=f"{property_base}/{_UNIQUE_PROPERTY}",
                description=UNIQUE_PROPERTY_DESCRIPTION,
                type="boolean",
            )
        )
    carries_searchable = any(
        concept_property.code == SEARCHABLE_PROPERTY
        for concept in concepts
        for concept_property in concept.property or []
    )
    if carries_searchable:
        declarations.append(
            CodeSystemProperty(
                code=SEARCHABLE_PROPERTY,
                uri=f"{property_base}/{SEARCHABLE_PROPERTY}",
                description=SEARCHABLE_PROPERTY_DESCRIPTION,
                type="boolean",
            )
        )
    carries_generated = any(
        concept_property.code == GENERATED_PROPERTY
        for concept in concepts
        for concept_property in concept.property or []
    )
    if carries_generated:
        declarations.append(
            CodeSystemProperty(
                code=GENERATED_PROPERTY,
                uri=f"{property_base}/{GENERATED_PROPERTY}",
                description=GENERATED_PROPERTY_DESCRIPTION,
                type="boolean",
            )
        )
    carries_pattern = any(
        concept_property.code == PATTERN_PROPERTY for concept in concepts for concept_property in concept.property or []
    )
    if carries_pattern:
        declarations.append(
            CodeSystemProperty(
                code=PATTERN_PROPERTY,
                uri=f"{property_base}/{PATTERN_PROPERTY}",
                description=PATTERN_PROPERTY_DESCRIPTION,
                type="string",
            )
        )
    carries_display_in_list = any(
        concept_property.code == DISPLAY_IN_LIST_PROPERTY
        for concept in concepts
        for concept_property in concept.property or []
    )
    if carries_display_in_list:
        declarations.append(
            CodeSystemProperty(
                code=DISPLAY_IN_LIST_PROPERTY,
                uri=f"{property_base}/{DISPLAY_IN_LIST_PROPERTY}",
                description=DISPLAY_IN_LIST_PROPERTY_DESCRIPTION,
                type="boolean",
            )
        )
    declarations.extend(
        CodeSystemProperty(
            code=context.property_code,
            uri=f"{property_base}/{context.property_code}",
            description=context.description,
            type="boolean",
        )
        for context in search_contexts or []
    )
    if decomposition is not None:
        carried = {
            concept_property.code
            for concept in concepts
            for concept_property in concept.property or []
            if concept_property.code is not None
        }
        declarations.extend(decomposition.declarations_for(carried))
    return declarations
