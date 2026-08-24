"""Pre-built FHIR JSON for the DHIS2 attribute option combos an aggregate form is keyed by.

A DHIS2 data value set is keyed by `(orgUnit, period, attributeOptionCombo)`, and the third
key comes from the data set's own category combo. A data set on the default combo has exactly
one attribute option combo and nothing to choose between; a data set on a non-default combo
has several, and a capture that does not name one is refused with `E8023`. This module
publishes that choice as terminology: one CodeSystem/ValueSet pair per distinct non-default
attribute combo, riding the grammar the categories family already rides - the same shared
concept-code assignment, the same identity-stem resolution, the same pre-built JSON in the
predefined-resource tree, and a ConceptMap taking every concept back to the DHIS2 identifiers
it stands for.

The economy is the assignment target's: **a pair is published only when the data set's category
combo is not the default one.** A default-combo data set publishes nothing, its Questionnaire
carries no `D2AttributeOptionCombos` extension, and its responses carry no
`D2AttributeOptionCombo` - absence means the default combo, which is what a consumer already
assumed. One pair serves every data set on the same combo, because the pair is the combo's and
not the form's.

The pair takes its own naming token (`AOC`) rather than the data dictionary's `COC`. Both
vocabularies are category option combos, but they answer different questions in different
places: `D2COC_CS` codes the disaggregation cells of a question, and `D2AOC_<stem>_VS` codes
the attribute option combo the whole response is filed under. A capture client binds one to an
item's code and the other to a response extension, and collapsing them onto one token would
make a form's two combo vocabularies indistinguishable by name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.coded import DHIS2_CODE_PROPERTY, DHIS2_ID_PROPERTY, code_substitutions
from dhis2w_fhir.i18n import name_translations, translated_element
from dhis2w_fhir.names import (
    FHIR_ID_MAX_LENGTH,
    StemSubject,
    code_or_uid,
    flatten_whitespace,
    is_valid_fhir_code,
    join_id_tokens,
    join_name_segments,
    resolve_identity_stems,
)
from dhis2w_fhir.r4 import (
    CodeSystem,
    CodeSystemConcept,
    CodeSystemProperty,
    ConceptMap,
    ConceptMapGroup,
    ConceptMapGroupElement,
    ConceptMapGroupElementTarget,
    Element,
    Identifier,
    ValueSet,
    ValueSetCompose,
    ValueSetInclude,
)
from dhis2w_fhir.resources.attribute_combos.schemas import (
    AttributeComboIdentity,
    AttributeComboIdentityPlan,
    AttributeComboIn,
    AttributeComboPlan,
)
from dhis2w_fhir.resources.identifier_terminology import build_identifier_code_system_artifacts
from dhis2w_fhir.resources.option_sets import (
    CONCEPT_MAP_DIRECTORY,
    build_concepts,
    code_system_canonical,
    concept_assignments,
    concept_map_canonical,
    value_set_canonical,
)
from dhis2w_fhir.resources.option_sets.schemas import OptionIn
from dhis2w_fhir.status import IgStatus, experimental_for_status
from dhis2w_fhir.writer import JsonArtifact, JsonBuild

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig
    from dhis2w_fhir.notes import GenerateNote
    from dhis2w_fhir.resources.categories.decomposition import CategoryDecomposition
    from dhis2w_fhir.resources.option_sets.schemas import ConceptAssignment, ConceptAssignmentPlan
    from dhis2w_fhir.resources.questionnaires.schemas import QuestionnaireSourceIn

__all__ = [
    "ATTRIBUTE_COMBO_DIRECTORY",
    "AttributeComboBuild",
    "attribute_combo_concept_map_file_prefix",
    "attribute_combo_fsh_name",
    "attribute_combo_identities",
    "attribute_combo_sources",
    "build_attribute_combo_artifacts",
    "build_attribute_combo_concept_map_artifacts",
    "build_attribute_combo_concept_maps",
    "build_attribute_combo_identifier_artifacts",
    "max_attribute_combo_slug_length",
]

#: The `ig/input/resources/` subdirectory the attribute-combo pairs own outright - one JSON file per resource.
ATTRIBUTE_COMBO_DIRECTORY = "attribute-option-combos"

# The longest emitted id is `<id-stem><slug>-cs`/`-vs`, so the slug is bounded against the
# actual stem and the FHIR id limit.
_ID_SUFFIX = "-vs"

#: The concept-property declarations, each of which takes its `uri` from the configured identifier base.
_PROPERTY_DECLARATIONS = (
    CodeSystemProperty(code=DHIS2_CODE_PROPERTY, description="DHIS2 category option combo code.", type="string"),
    CodeSystemProperty(code=DHIS2_ID_PROPERTY, description="DHIS2 category option combo UID.", type="code"),
)


class AttributeComboBuild(JsonBuild):
    """The attribute-combo pairs one run publishes, plus the plan the questionnaire emitters bind them by."""

    plan: AttributeComboPlan = Field(default_factory=AttributeComboPlan)


class _AttributeComboSystems(BaseModel):
    """The absolute URLs a pre-built attribute-combo triple references: canonical base, identifiers, properties."""

    model_config = ConfigDict(frozen=True)

    canonical: str
    identifier_system: str
    code_identifier_system: str
    option_combo_identifier_system: str
    option_combo_code_identifier_system: str
    property_base: str

    @classmethod
    def from_config(cls, config: GenerateConfig, canonical: str) -> _AttributeComboSystems:
        """Derive the emitted URLs from the IG canonical plus the `[generate]` identifier system base."""
        identifier_base = config.identifier_system_base
        return cls(
            canonical=canonical,
            identifier_system=f"{identifier_base}/id/category-combo",
            code_identifier_system=f"{identifier_base}/id/category-combo-code",
            option_combo_identifier_system=f"{identifier_base}/id/category-option-combo",
            option_combo_code_identifier_system=f"{identifier_base}/id/category-option-combo-code",
            property_base=f"{identifier_base}/property",
        )

    def code_system_url(self, code_system_id: str) -> str:
        """Canonical URL of one emitted CodeSystem."""
        return code_system_canonical(self.canonical, code_system_id)

    def value_set_url(self, value_set_id: str) -> str:
        """Canonical URL of one emitted ValueSet."""
        return value_set_canonical(self.canonical, value_set_id)

    def concept_map_url(self, concept_map_id: str) -> str:
        """Canonical URL of one emitted ConceptMap."""
        return concept_map_canonical(self.canonical, concept_map_id)


class _AttributeComboPair(BaseModel):
    """The two resources one attribute combo emits, sharing its identity, title, and publication state."""

    model_config = ConfigDict(frozen=True)

    code_system: CodeSystem
    value_set: ValueSet


class _AttributeComboNarrative(BaseModel):
    """The elements both halves of a pair carry identically: identifiers, title, and publication state."""

    model_config = ConfigDict(frozen=True)

    identifiers: list[Identifier] = Field(default_factory=list)
    title: str
    title_element: Element | None = None
    description: str
    status: IgStatus
    experimental: bool


def attribute_combo_sources(sources: list[QuestionnaireSourceIn]) -> list[AttributeComboIn]:
    """Every distinct non-default attribute category combo the given forms ride, by name then UID.

    Only an aggregate form has one: a data value set is the only DHIS2 wire shape with an
    attribute option combo on it, so an event program and a tracker stage contribute nothing.
    Two data sets on one combo yield one entry, which is what makes them share a published pair.

    The option combos arrive already ordered by name and UID (`CategoryCombo.categoryOptionCombos`
    is a Java `Set` DHIS2 reshuffles per request, BUGS.md #64), and that order is carried across
    as the DHIS2 sort order so the emitted concepts are byte-stable across regenerates.
    """
    combos: dict[str, AttributeComboIn] = {}
    for source in sources:
        combo = source.attribute_combo
        if source.kind != "aggregate" or combo is None or combo.is_default:
            continue
        combos.setdefault(
            combo.uid,
            AttributeComboIn(
                uid=combo.uid,
                code=combo.code,
                name=combo.name,
                options=[
                    OptionIn(uid=option_combo.uid, code=option_combo.code, name=option_combo.name, sort_order=index)
                    for index, option_combo in enumerate(combo.option_combos)
                ],
            ),
        )
    return sorted(combos.values(), key=lambda combo: (combo.name, combo.uid))


def attribute_combo_fsh_name(config: GenerateConfig, segment: str) -> str:
    """FSH name stem for one attribute combo: the merged naming tokens, then the resolved stem segment.

    The emitted CodeSystem and ValueSet append `_CS` and `_VS` to it, so `D2AOC_Project` names
    the pair `D2AOC_Project_CS` / `D2AOC_Project_VS`.
    """
    return join_name_segments(f"{config.naming.prefix}{config.naming.attribute_option_combo}", segment)


def max_attribute_combo_slug_length(config: GenerateConfig) -> int:
    """Longest slug that keeps every emitted attribute-combo id within the FHIR id limit."""
    return FHIR_ID_MAX_LENGTH - len(_id_stem(config)) - len(_ID_SUFFIX)


def attribute_combo_identities(combos: list[AttributeComboIn], config: GenerateConfig) -> AttributeComboIdentityPlan:
    """Assign every attribute combo its emitted slug, FSH name, and artifact ids, in emission order.

    The slug is the identity stem `resolve_identity_stems` assigns over the whole selection, so
    every artifact of one combo follows the one resolved segment and a code-sourced run falls
    back to the UID or refuses the run exactly as the terminology families do.
    """
    plan = AttributeComboIdentityPlan()
    id_stem = _id_stem(config)
    resolution = resolve_identity_stems(
        [StemSubject(uid=combo.uid, code=combo.code, label=combo.name) for combo in combos],
        config.naming.source,
        "attribute category combo",
        max_stem_length=max_attribute_combo_slug_length(config),
    )
    for combo in sorted(combos, key=lambda item: (item.name, item.uid)):
        slug = resolution.stem_for(combo.uid)
        plan.identities.append(
            AttributeComboIdentity(
                uid=combo.uid,
                name=combo.name,
                slug=slug,
                fsh_name=attribute_combo_fsh_name(config, resolution.fsh_segment_for(combo.uid)),
                code_system_id=f"{id_stem}{slug}-cs",
                value_set_id=f"{id_stem}{slug}{_ID_SUFFIX}",
                concept_map_id=f"{id_stem}{slug}-cm",
            )
        )
    plan.notes.extend(resolution.notes)
    return plan


def build_attribute_combo_artifacts(
    sources: list[QuestionnaireSourceIn],
    config: GenerateConfig,
    canonical: str,
    *,
    ig_status: IgStatus,
    decomposition: CategoryDecomposition | None = None,
) -> AttributeComboBuild:
    """Build one CodeSystem/ValueSet pair per non-default attribute combo, plus the per-form plan.

    The plan is what the two questionnaire emitters read their `D2AttributeOptionCombos`
    extension from and what the example paths draw a valid attribute option combo out of, so
    the FSH source, the served documents, and every response name the one published ValueSet.

    `decomposition` states what each attribute option combo is composed of, so every concept
    carries one `Coding`-valued property per category axis into that category's own CodeSystem.
    A caller that only wants the plan passes none and the concepts state their own code alone.
    """
    build = AttributeComboBuild()
    combos = attribute_combo_sources(sources)
    systems = _AttributeComboSystems.from_config(config, canonical)
    plan = attribute_combo_identities(combos, config)
    by_uid = {combo.uid: combo for combo in combos}
    for identity in plan.identities:
        pair = _build_pair(
            by_uid[identity.uid],
            identity,
            config,
            systems,
            build.notes,
            ig_status=ig_status,
            decomposition=decomposition,
        )
        build.artifacts.append(
            _json_artifact(ATTRIBUTE_COMBO_DIRECTORY, f"CodeSystem-{identity.code_system_id}", pair.code_system)
        )
        build.artifacts.append(
            _json_artifact(ATTRIBUTE_COMBO_DIRECTORY, f"ValueSet-{identity.value_set_id}", pair.value_set)
        )
    build.notes.extend(plan.notes)
    build.plan = _combo_plan(sources, plan)
    return build


def build_attribute_combo_concept_maps(
    sources: list[QuestionnaireSourceIn],
    config: GenerateConfig,
    canonical: str,
    *,
    ig_status: IgStatus,
) -> list[ConceptMap]:
    """Build one ConceptMap per attribute combo, taking its concept codes back to the DHIS2 identifiers.

    Two groups per map, both sourced from the combo's own CodeSystem: one onto
    `<base>/id/category-option-combo` carrying the DHIS2 category option combo UID, one onto
    `<base>/id/category-option-combo-code` carrying its DHIS2 code. That second group is what a
    forwarder holding a generated coding resolves the `attributeOptionCombo` of a data value set
    from, whichever of the two DHIS2 identifiers the concept code happens to be.

    The rows come from `concept_assignments`, the very plan the concepts are built from, so a
    mapping can only ever name a concept the emitted CodeSystem really holds.
    """
    combos = attribute_combo_sources(sources)
    systems = _AttributeComboSystems.from_config(config, canonical)
    plan = attribute_combo_identities(combos, config)
    by_uid = {combo.uid: combo for combo in combos}
    concept_maps = [
        _build_concept_map(by_uid[identity.uid], identity, config, systems, ig_status=ig_status)
        for identity in plan.identities
    ]
    return [concept_map for concept_map in concept_maps if concept_map is not None]


def build_attribute_combo_concept_map_artifacts(
    sources: list[QuestionnaireSourceIn],
    config: GenerateConfig,
    canonical: str,
    *,
    ig_status: IgStatus,
) -> list[JsonArtifact]:
    """Build one `concept-maps/ConceptMap-<id>.json` per attribute combo that emitted concepts."""
    return [
        _json_artifact(CONCEPT_MAP_DIRECTORY, f"ConceptMap-{concept_map.id}", concept_map)
        for concept_map in build_attribute_combo_concept_maps(sources, config, canonical, ig_status=ig_status)
    ]


def build_attribute_combo_identifier_artifacts(
    sources: list[QuestionnaireSourceIn],
    config: GenerateConfig,
    canonical: str,
    *,
    ig_status: IgStatus,
) -> list[JsonArtifact]:
    """Build one complete `attribute-option-combos/CodeSystem-<id>.json` per identifier namespace the maps target.

    The combo maps target `<base>/id/category-option-combo` and its code twin, which the foundation
    declares as NamingSystems and nothing more. Enumerating them here is what keeps the publisher
    from asking a terminology server about every mapped option combo in turn.
    """
    return build_identifier_code_system_artifacts(
        ATTRIBUTE_COMBO_DIRECTORY,
        build_attribute_combo_concept_maps(sources, config, canonical, ig_status=ig_status),
        config,
        ig_status=ig_status,
        substitutions=code_substitutions(sources),
    )


def attribute_combo_concept_map_file_prefix(config: GenerateConfig) -> str:
    """The file-name prefix every attribute-combo ConceptMap carries, which is what that family sweeps by.

    `concept-maps/` holds three terminology families behind one publisher glob, so none of them
    owns the directory outright: each sweeps the files its own id stem names.
    """
    return f"ConceptMap-{_id_stem(config)}"


def _combo_plan(sources: list[QuestionnaireSourceIn], plan: AttributeComboIdentityPlan) -> AttributeComboPlan:
    """Index the published identities by combo UID and record which combo each form rides."""
    identities = {identity.uid: identity for identity in plan.identities}
    combo_uids = {
        source.uid: source.attribute_combo.uid
        for source in sources
        if source.attribute_combo is not None and source.attribute_combo.uid in identities
    }
    return AttributeComboPlan(identities=identities, combo_uids=combo_uids)


def _json_artifact(directory: str, stem: str, resource: CodeSystem | ValueSet | ConceptMap) -> JsonArtifact:
    """Serialise one resource as the predefined-resource file the loader reads, in the directory it belongs to."""
    return JsonArtifact(
        relative_path=f"{directory}/{stem}.json",
        content=f"{resource.model_dump_json(exclude_none=True, by_alias=True, indent=2)}\n",
    )


def _build_pair(
    combo: AttributeComboIn,
    identity: AttributeComboIdentity,
    config: GenerateConfig,
    systems: _AttributeComboSystems,
    notes: list[GenerateNote],
    *,
    ig_status: IgStatus,
    decomposition: CategoryDecomposition | None = None,
) -> _AttributeComboPair:
    """Build the CodeSystem and the ValueSet of one attribute combo, reporting what assignment raised."""
    concepts = build_concepts(combo, config, notes, member_properties=decomposition)
    narrative = _narrative(combo, config, systems, ig_status=ig_status)
    code_system_url = systems.code_system_url(identity.code_system_id)
    code_system = CodeSystem(
        id=identity.code_system_id,
        url=code_system_url,
        identifier=narrative.identifiers,
        name=identity.code_system_name,
        title=narrative.title,
        title_element=narrative.title_element,
        description=narrative.description,
        status=narrative.status,
        experimental=narrative.experimental,
        caseSensitive=True,
        content="complete",
        count=len(concepts),
        valueSet=systems.value_set_url(identity.value_set_id),
        property=_declarations(concepts, systems, decomposition) or None,
        concept=concepts or None,
    )
    value_set = ValueSet(
        id=identity.value_set_id,
        url=systems.value_set_url(identity.value_set_id),
        identifier=narrative.identifiers,
        name=identity.value_set_name,
        title=narrative.title,
        title_element=narrative.title_element,
        description=narrative.description,
        status=narrative.status,
        experimental=narrative.experimental,
        compose=ValueSetCompose(include=[ValueSetInclude(system=code_system_url)]),
    )
    return _AttributeComboPair(code_system=code_system, value_set=value_set)


def _narrative(
    combo: AttributeComboIn,
    config: GenerateConfig,
    systems: _AttributeComboSystems,
    *,
    ig_status: IgStatus,
) -> _AttributeComboNarrative:
    """The elements both halves share: both DHIS2 identifiers, the title, and the publication state."""
    code_kind = "category option combo codes" if config.concept_code_source == "code" else "category option combo UIDs"
    return _AttributeComboNarrative(
        identifiers=[
            Identifier(system=systems.identifier_system, value=combo.uid),
            Identifier(system=systems.code_identifier_system, value=code_or_uid(combo.code, combo.uid)),
        ],
        title=flatten_whitespace(combo.name),
        title_element=translated_element(name_translations(combo.translations, config.locales)),
        description=flatten_whitespace(
            f"DHIS2 attribute option combos of category combo {combo.name} ({combo.uid}). A data set on this "
            f"combo keys every value it holds by one of them. Concept codes are DHIS2 {code_kind}."
        ),
        status=ig_status,
        experimental=experimental_for_status(ig_status),
    )


def _build_concept_map(
    combo: AttributeComboIn,
    identity: AttributeComboIdentity,
    config: GenerateConfig,
    systems: _AttributeComboSystems,
    *,
    ig_status: IgStatus,
) -> ConceptMap | None:
    """Build one attribute combo's ConceptMap, or None when the combo emitted no concept to map."""
    groups = _concept_map_groups(concept_assignments(combo, config), identity, systems)
    if not groups:
        return None
    return ConceptMap(
        id=identity.concept_map_id,
        url=systems.concept_map_url(identity.concept_map_id),
        identifier=Identifier(system=systems.identifier_system, value=combo.uid),
        name=identity.concept_map_name,
        title=flatten_whitespace(combo.name),
        title_element=translated_element(name_translations(combo.translations, config.locales)),
        description=flatten_whitespace(
            f"DHIS2 category combo {combo.name} ({combo.uid}). Every concept of {identity.code_system_name} "
            "mapped to its DHIS2 category option combo UID and, where the combo carries one, its DHIS2 "
            "category option combo code."
        ),
        status=ig_status,
        experimental=experimental_for_status(ig_status),
        sourceCanonical=systems.value_set_url(identity.value_set_id),
        group=groups,
    )


def _concept_map_groups(
    plan: ConceptAssignmentPlan, identity: AttributeComboIdentity, systems: _AttributeComboSystems
) -> list[ConceptMapGroup]:
    """One combo's groups: the UID group always, the DHIS2-code group when any option combo has one."""
    mapped = [assignment for assignment in plan.assignments if assignment.code is not None]
    if not mapped:
        return []
    code_system_url = systems.code_system_url(identity.code_system_id)
    groups = [
        ConceptMapGroup(
            source=code_system_url,
            target=systems.option_combo_identifier_system,
            element=[_concept_map_element(assignment, assignment.option.uid) for assignment in mapped],
        )
    ]
    coded = [
        _concept_map_element(assignment, assignment.option.code)
        for assignment in mapped
        if assignment.option.code is not None and is_valid_fhir_code(assignment.option.code)
    ]
    if coded:
        groups.append(
            ConceptMapGroup(source=code_system_url, target=systems.option_combo_code_identifier_system, element=coded)
        )
    return groups


def _concept_map_element(assignment: ConceptAssignment, target_code: str) -> ConceptMapGroupElement:
    """One mapping row: the concept code the combo assigned, and the DHIS2 identifier it stands for."""
    return ConceptMapGroupElement(
        code=assignment.code,
        display=flatten_whitespace(assignment.option.name),
        target=[ConceptMapGroupElementTarget(code=target_code, equivalence="equal")],
    )


def _declarations(
    concepts: list[CodeSystemConcept],
    systems: _AttributeComboSystems,
    decomposition: CategoryDecomposition | None,
) -> list[CodeSystemProperty]:
    """The CodeSystem-level declaration of every concept property the emitted concepts actually carry.

    The DHIS2 identifier pair first, then one declaration per category axis the combo decomposes
    over, each carrying that category's name so the vocabulary alone names its own axes.
    """
    carried = {
        concept_property.code
        for concept in concepts
        for concept_property in concept.property or []
        if concept_property.code is not None
    }
    declarations = [
        declaration.model_copy(update={"uri": f"{systems.property_base}/{declaration.code}"})
        for declaration in _PROPERTY_DECLARATIONS
        if declaration.code in carried
    ]
    if decomposition is not None:
        declarations.extend(decomposition.declarations_for(carried))
    return declarations


def _id_stem(config: GenerateConfig) -> str:
    """Build the id stem for attribute-combo artifacts from the configured naming tokens."""
    joined = join_id_tokens(config.naming.prefix, config.naming.attribute_option_combo)
    return f"{joined}-" if joined else ""
