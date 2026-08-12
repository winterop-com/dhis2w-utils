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
from dhis2w_fhir.foundation.schemas import FoundationNaming
from dhis2w_fhir.i18n import TranslationIn, name_translations, text_translations, translated_element
from dhis2w_fhir.names import code_or_uid, flatten_whitespace, page_string
from dhis2w_fhir.notes import GenerateNote, GenerateNoteCategory, aggregate_generate_note
from dhis2w_fhir.r4 import (
    CodeableConcept,
    CodeSystem,
    CodeSystemConcept,
    CodeSystemConceptDesignation,
    CodeSystemConceptProperty,
    CodeSystemProperty,
    Coding,
    Extension,
    Identifier,
    Questionnaire,
    QuestionnaireItem,
    Reference,
    ValueSet,
    ValueSetCompose,
    ValueSetInclude,
)
from dhis2w_fhir.resources.attribute_combos.schemas import AttributeComboPlan
from dhis2w_fhir.resources.option_sets import (
    code_system_canonical,
    option_set_identity_index,
    value_set_canonical,
)
from dhis2w_fhir.resources.questionnaires import (
    BOUND_ELEMENTS_BY_ITEM_TYPE,
    BOUNDS_BY_VALUE_TYPE,
    ITEM_CONTROL_CODE_SYSTEM_URL,
    ITEM_CONTROL_EXTENSION_URL,
    MAXIMUM_VALUE_EXTENSION_URL,
    MINIMUM_VALUE_EXTENSION_URL,
    bound_option_set_uids,
    collect_referenced_objects,
    domain_code,
    grouping_identifiers,
    is_disaggregated,
    is_multi_valued,
    item_type,
    question_entity_level,
    search_context_declarations,
    source_description,
)
from dhis2w_fhir.resources.questionnaires.assignments import AssignmentPlan
from dhis2w_fhir.resources.questionnaires.schemas import (
    CATEGORY_OPTION_COMBO_TERMINOLOGY,
    DATA_ELEMENT_TERMINOLOGY,
    DOMAIN_PROPERTY_DESCRIPTION,
    FORM_KIND_PROFILES,
    SEARCHABLE_PROPERTY,
    SEARCHABLE_PROPERTY_DESCRIPTION,
    TRACKED_ENTITY_ATTRIBUTE_TERMINOLOGY,
    UNIQUE_PROPERTY_DESCRIPTION,
    AttributeSearchContext,
    CategoryOptionComboIn,
    FormKind,
    FormKindProfile,
    QuestionnaireItemIn,
    QuestionnaireNaming,
    QuestionnaireSourceIn,
    QuestionnaireStemPlan,
    ReferencedObjects,
    SupportTerminologyProfile,
    form_subject_type,
    plan_questionnaire_stems,
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

    Both lists are empty when the forms reference nothing of that kind: a run over forms that
    disaggregate no question publishes the data-element pair alone, exactly as the FSH target
    writes only the file it has content for.
    """

    model_config = ConfigDict(frozen=True)

    code_systems: list[CodeSystem] = Field(default_factory=list)
    value_sets: list[ValueSet] = Field(default_factory=list)


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
    assignment_extension_url: str
    attribute_option_combos_extension_url: str
    attribute_value_extension_url: str
    entity_level_extension_url: str
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
            assignment_extension_url=(
                f"{canonical}/StructureDefinition/{foundation.organisation_unit_assignment_extension_id}"
            ),
            attribute_option_combos_extension_url=(
                f"{canonical}/StructureDefinition/{foundation.attribute_option_combos_extension_id}"
            ),
            attribute_value_extension_url=attribute_value_extension_url(config, canonical),
            entity_level_extension_url=f"{canonical}/StructureDefinition/{foundation.entity_level_extension_id}",
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
        )
        for source in sorted(sources, key=lambda item: (item.name, item.uid))
    ]
    notes: list[GenerateNote] = list(plan.targets.notes)
    if index.unplanned_uids:
        notes.append(
            aggregate_generate_note(
                GenerateNoteCategory.SELECTION_GAP,
                f"{len(index.unplanned_uids)} option sets a question binds are absent from the option-set "
                "selection; their answerValueSet names are derived from the UID",
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
        description=page_string(source_description(source, profile)),
        extension=[
            Extension(url=systems.form_type_extension_url, valueCode=source.kind),
            *_assignment_extension(source, systems, assignments),
            *_attribute_option_combos_extension(source, systems, attribute_combos),
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
        item=_items(source, systems, identities, locales) or None,
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


def _items(
    source: QuestionnaireSourceIn,
    systems: _QuestionnaireSystems,
    identities: dict[str, OptionSetIdentity],
    locales: list[str],
) -> list[QuestionnaireItem]:
    """Build the form's item tree: one group per section holding its questions, then the unsectioned tail."""
    items: list[QuestionnaireItem] = []
    for section in source.sections:
        children = [
            child for item in section.items for child in _data_element_items(item, source, systems, identities, locales)
        ]
        items.append(
            QuestionnaireItem(
                linkId=section.uid,
                text=flatten_whitespace(section.name),
                text_element=translated_element(name_translations(section.translations, locales)),
                type="group",
                extension=[_item_control_extension()]
                if any(is_disaggregated(item, source.kind) for item in section.items)
                else None,
                item=children or None,
            )
        )
    for item in source.flat_items:
        items.extend(_data_element_items(item, source, systems, identities, locales))
    return items


def _data_element_items(
    item: QuestionnaireItemIn,
    source: QuestionnaireSourceIn,
    systems: _QuestionnaireSystems,
    identities: dict[str, OptionSetIdentity],
    locales: list[str],
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
    bounds = _bound_extensions(item.value_type, resolved_item_type)
    if not is_disaggregated(item, source.kind):
        extensions = [*bounds, *_entity_level_extension(item, source.kind, systems)]
        return [
            QuestionnaireItem(
                linkId=item.uid,
                code=code,
                text=text,
                text_element=text_element,
                type=resolved_item_type,
                answerValueSet=answer_value_set,
                required=item.compulsory or None,
                repeats=repeats,
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
            required=item.compulsory or None,
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


def _bound_extensions(value_type: str, resolved_item_type: str) -> list[Extension]:
    """The `minValue` / `maxValue` extensions one question carries, on the element its item type asks for."""
    bounds = BOUNDS_BY_VALUE_TYPE.get(value_type)
    element = BOUND_ELEMENTS_BY_ITEM_TYPE.get(resolved_item_type)
    if bounds is None or element is None:
        return []
    extensions: list[Extension] = []
    if bounds.minimum_value is not None:
        extensions.append(_bound_extension(MINIMUM_VALUE_EXTENSION_URL, element, bounds.minimum_value))
    if bounds.maximum_value is not None:
        extensions.append(_bound_extension(MAXIMUM_VALUE_EXTENSION_URL, element, bounds.maximum_value))
    return extensions


def _bound_extension(url: str, element: str, value: int) -> Extension:
    """One bound as its extension, the whole number landing on `valueInteger` or on `valueDecimal`."""
    if element == _INTEGER_BOUND_ELEMENT:
        return Extension(url=url, valueInteger=value)
    return Extension(url=url, valueDecimal=value)


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
            property=_property_declarations(concepts, terminology, config, decomposition, search_contexts),
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
