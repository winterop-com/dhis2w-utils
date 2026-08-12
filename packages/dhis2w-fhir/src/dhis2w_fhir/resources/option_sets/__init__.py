"""Pre-built FHIR JSON for DHIS2 option sets: one CodeSystem and one ValueSet document per set.

The pair ships as finished FHIR JSON in the predefined-resource tree, which the
publisher loads verbatim, so a registry of hundreds of option sets never enters
the FSH compile. SUSHI fishes a predefined resource by its `name` element, so
each document carries the FSH-style name (`D2OS_BirthType_CS` / `_VS`) that a
questionnaire's `Canonical(...)` binding resolves against.

Every concept carries both DHIS2 identifiers: whichever one is the concept
code, the other rides along as a concept property (`dhis2-code` or
`dhis2-id`). With `concept_code_source = "code"`, options whose code is not a
valid FHIR code fall back to the UID with a note in the report.

Concept codes are unique within a set by construction: a first pass computes
each option's desired code, a second assigns them in sortOrder and falls back
to the option UID whenever the desired code is already taken. An option whose
UID fall-back is taken too - a peer carries that UID as its DHIS2 code - is
skipped with a note rather than emitted as a duplicate concept.

A third document takes the concept codes back to DHIS2: one ConceptMap per set,
in the `concept-maps/` directory the category maps also live in, mapping every
emitted concept onto the DHIS2 option UID and, where the option carries one, the
DHIS2 option code. It is built from the same `concept_assignments` plan the
concepts are, so a mapping can only ever name a concept the CodeSystem really
holds.

All three artifacts of one set carry one identity stem, resolved by
`resolve_identity_stems` under `[generate.naming] source`: with `"id"` the slug
is the option-set UID verbatim (FHIR ids and file names both permit mixed case,
so the emitted id reads straight back to the DHIS2 object), and with the code
sources it is the set's DHIS2 code, falling back to the UID or refusing the run
as the source dictates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.foundation.attribute_values import (
    attribute_value_extension_url,
    attribute_value_extensions,
    attribute_value_identifiers,
)
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
from dhis2w_fhir.notes import GenerateNote, GenerateNoteCategory, aggregate_generate_note, generate_note
from dhis2w_fhir.r4 import (
    CodeSystem,
    CodeSystemConcept,
    CodeSystemConceptDesignation,
    CodeSystemConceptProperty,
    CodeSystemProperty,
    ConceptMap,
    ConceptMapGroup,
    ConceptMapGroupElement,
    ConceptMapGroupElementTarget,
    Element,
    Extension,
    Identifier,
    ValueSet,
    ValueSetCompose,
    ValueSetInclude,
)
from dhis2w_fhir.resources.option_sets.schemas import (
    ConceptAssignment,
    ConceptAssignmentPlan,
    ConceptSourceIn,
    OptionIn,
    OptionSetIdentity,
    OptionSetIdentityIndex,
    OptionSetIdentityPlan,
    OptionSetIn,
)
from dhis2w_fhir.status import IgStatus, experimental_for_status
from dhis2w_fhir.writer import JsonArtifact, JsonBuild

if TYPE_CHECKING:
    from dhis2w_fhir.attributes import AttributeCodeIndex
    from dhis2w_fhir.config import GenerateConfig

__all__ = [
    "CONCEPT_MAP_DIRECTORY",
    "TERMINOLOGY_DIRECTORY",
    "MemberPropertySource",
    "build_concepts",
    "build_option_set_artifacts",
    "build_option_set_concept_map_artifacts",
    "build_option_set_concept_maps",
    "code_system_canonical",
    "concept_assignments",
    "concept_map_canonical",
    "max_slug_length",
    "option_set_code_fallback",
    "option_set_concept_map_file_prefix",
    "option_set_fsh_name",
    "option_set_identities",
    "option_set_identity_index",
    "value_set_canonical",
]


class MemberPropertySource(Protocol):
    """States the extra concept properties one member of a concept source carries beyond its identifier pair.

    Structural rather than imported, so the concept builder stays the bottom of the terminology
    stack: the category decomposition implements it without this module knowing what a category is.
    """

    def properties_for(self, member_uid: str) -> list[CodeSystemConceptProperty]:
        """The extra properties the member with this DHIS2 UID carries, or an empty list when it carries none."""
        ...


#: The `ig/input/resources/` subdirectory the option-set pairs own outright - one JSON file per resource.
TERMINOLOGY_DIRECTORY = "terminology"

#: The `ig/input/resources/` subdirectory both ConceptMap families publish into - one JSON file per source
#: object. A JSON sync deletes every unproduced `*.json` in its target, so the maps sweep a directory apart
#: from the pairs', and the two families each sweep only the file-name prefix their own id stem produces.
CONCEPT_MAP_DIRECTORY = "concept-maps"

# The longest emitted id is `<id-stem><slug>-cs`/`-vs`, so the slug is bounded
# against the actual stem and the FHIR id limit.
_ID_SUFFIX = "-vs"

#: The concept-property declarations, each of which takes its `uri` from the configured identifier base.
_PROPERTY_DECLARATIONS = (
    CodeSystemProperty(code="dhis2-code", description="DHIS2 option code.", type="string"),
    CodeSystemProperty(code="dhis2-id", description="DHIS2 option UID.", type="code"),
)


class _OptionSetSystems(BaseModel):
    """The absolute URLs a pre-built option-set pair references: its canonical base, identifiers, property base.

    A pre-built resource carries what FSH resolves through `$DHIS2-OS` and a `Canonical(...)`
    call, so the canonical of the IG and the configured identifier system base are resolved
    once here and read straight off the model by the emitter.
    """

    model_config = ConfigDict(frozen=True)

    canonical: str
    identifier_system: str
    code_identifier_system: str
    option_identifier_system: str
    option_code_identifier_system: str
    property_base: str

    @classmethod
    def from_config(cls, config: GenerateConfig, canonical: str) -> _OptionSetSystems:
        """Derive the emitted URLs from the IG canonical plus the `[generate]` identifier system base."""
        identifier_base = config.identifier_system_base
        return cls(
            canonical=canonical,
            identifier_system=f"{identifier_base}/id/option-set",
            code_identifier_system=f"{identifier_base}/id/option-set-code",
            option_identifier_system=f"{identifier_base}/id/option",
            option_code_identifier_system=f"{identifier_base}/id/option-code",
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


class _OptionSetPair(BaseModel):
    """The two resources one DHIS2 option set emits, sharing its identity, title, and publication state."""

    model_config = ConfigDict(frozen=True)

    code_system: CodeSystem
    value_set: ValueSet


class _OptionSetNarrative(BaseModel):
    """The elements both halves of a pair carry identically: identifiers, title, and publication state."""

    model_config = ConfigDict(frozen=True)

    identifiers: list[Identifier] = Field(default_factory=list)
    extensions: list[Extension] = Field(default_factory=list)
    title: str
    title_element: Element | None = None
    description: str
    status: IgStatus
    experimental: bool


def code_system_canonical(canonical: str, code_system_id: str) -> str:
    """Canonical URL one emitted CodeSystem is published at, under the IG canonical.

    The one place the shape is written: FSH resolves it through `Canonical(...)` at compile
    time, and every JSON emitter - the option-set pairs, the questionnaires binding an
    `answerValueSet`, the data dictionary - resolves it through here instead.
    """
    return f"{canonical}/CodeSystem/{code_system_id}"


def value_set_canonical(canonical: str, value_set_id: str) -> str:
    """Canonical URL one emitted ValueSet is published at, under the IG canonical."""
    return f"{canonical}/ValueSet/{value_set_id}"


def concept_map_canonical(canonical: str, concept_map_id: str) -> str:
    """Canonical URL one emitted ConceptMap is published at, under the IG canonical."""
    return f"{canonical}/ConceptMap/{concept_map_id}"


def option_set_fsh_name(config: GenerateConfig, segment: str) -> str:
    """FSH name stem for one option set: the merged naming tokens, then the resolved stem segment.

    The emitted CodeSystem and ValueSet append `_CS` and `_VS` to it, so `D2OS_BirthType`
    names the pair `D2OS_BirthType_CS` / `D2OS_BirthType_VS`.
    """
    return join_name_segments(f"{config.naming.prefix}{config.naming.option_set}", segment)


def max_slug_length(config: GenerateConfig) -> int:
    """Longest slug that keeps every emitted id within the FHIR id limit."""
    return FHIR_ID_MAX_LENGTH - len(_id_stem(config)) - len(_ID_SUFFIX)


def option_set_identities(option_sets: list[OptionSetIn], config: GenerateConfig) -> OptionSetIdentityPlan:
    """Assign every option set its emitted slug, FSH name, and artifact ids, in emission order.

    The one place the slug is decided: the emitter names its files from it and the narrative
    pages link to `CodeSystem-<code_system_id>.html` from it, so the two cannot drift. The slug
    is the identity stem `resolve_identity_stems` assigns over the whole selection, so every
    artifact of one set - the CodeSystem, the ValueSet, and the ConceptMap - follows the one
    resolved segment, and a code-sourced run falls back or refuses per the configured source.
    """
    plan = OptionSetIdentityPlan()
    id_stem = _id_stem(config)
    resolution = resolve_identity_stems(
        [StemSubject(uid=option_set.uid, code=option_set.code, label=option_set.name) for option_set in option_sets],
        config.naming.source,
        "option set",
        max_stem_length=max_slug_length(config),
    )
    for option_set in sorted(option_sets, key=lambda item: (item.name, item.uid)):
        slug = resolution.stem_for(option_set.uid)
        plan.identities.append(
            OptionSetIdentity(
                uid=option_set.uid,
                name=option_set.name,
                slug=slug,
                fsh_name=option_set_fsh_name(config, resolution.fsh_segment_for(option_set.uid)),
                code_system_id=f"{id_stem}{slug}-cs",
                value_set_id=f"{id_stem}{slug}{_ID_SUFFIX}",
                concept_map_id=f"{id_stem}{slug}-cm",
            )
        )
    plan.notes.extend(resolution.notes)
    return plan


def option_set_identity_index(
    plan: OptionSetIdentityPlan, bound_uids: list[str], config: GenerateConfig
) -> OptionSetIdentityIndex:
    """Index one plan by UID, deriving an identity from the UID alone for every bound set it omits.

    Every target that names an option set - the questionnaires binding `answerValueSet`, the
    examples coding an answer - resolves through this index, so a run's option-set names are
    decided once, by `option_set_identities`, and read everywhere else.
    """
    identities = {identity.uid: identity for identity in plan.identities}
    unplanned = sorted({uid for uid in bound_uids if uid not in identities})
    for uid in unplanned:
        identities[uid] = _uid_option_set_identity(uid, config)
    return OptionSetIdentityIndex(identities=identities, unplanned_uids=unplanned)


def build_option_set_artifacts(
    option_sets: list[OptionSetIn],
    config: GenerateConfig,
    canonical: str,
    *,
    ig_status: IgStatus,
    attribute_codes: AttributeCodeIndex,
) -> JsonBuild:
    """Build one `terminology/CodeSystem-<id>.json` and `terminology/ValueSet-<id>.json` per option set."""
    build = JsonBuild()
    systems = _OptionSetSystems.from_config(config, canonical)
    extension_url = attribute_value_extension_url(config, canonical)
    plan = option_set_identities(option_sets, config)
    by_uid = {option_set.uid: option_set for option_set in option_sets}
    for identity in plan.identities:
        option_set = by_uid[identity.uid]
        pair = _build_pair(
            option_set,
            identity,
            config,
            systems,
            build.notes,
            ig_status=ig_status,
            attribute_codes=attribute_codes,
            extension_url=extension_url,
        )
        build.artifacts.append(
            _json_artifact(TERMINOLOGY_DIRECTORY, f"CodeSystem-{identity.code_system_id}", pair.code_system)
        )
        build.artifacts.append(
            _json_artifact(TERMINOLOGY_DIRECTORY, f"ValueSet-{identity.value_set_id}", pair.value_set)
        )
    build.notes.extend(plan.notes)
    return build


def build_option_set_concept_maps(
    option_sets: list[OptionSetIn],
    config: GenerateConfig,
    canonical: str,
    *,
    ig_status: IgStatus,
) -> list[ConceptMap]:
    """Build one ConceptMap per option set, taking its concept codes back to the DHIS2 option identifiers.

    Two groups per map, both sourced from the set's own CodeSystem: one onto `<base>/id/option`
    carrying the DHIS2 option UID, one onto `<base>/id/option-code` carrying the DHIS2 option
    code. A consumer holding a generated coding therefore resolves both DHIS2 identifiers from
    one document, whichever of them the concept code happens to be.

    The rows come from `concept_assignments`, the same plan the concepts themselves are built
    from, so a mapping can only ever name a concept the emitted CodeSystem really holds. An
    option set that received no concept at all emits no map: an R4 group requires at least one
    element, and a map with no group states nothing.
    """
    systems = _OptionSetSystems.from_config(config, canonical)
    plan = option_set_identities(option_sets, config)
    by_uid = {option_set.uid: option_set for option_set in option_sets}
    concept_maps = [
        _build_concept_map(by_uid[identity.uid], identity, config, systems, ig_status=ig_status)
        for identity in plan.identities
    ]
    return [concept_map for concept_map in concept_maps if concept_map is not None]


def build_option_set_concept_map_artifacts(
    option_sets: list[OptionSetIn],
    config: GenerateConfig,
    canonical: str,
    *,
    ig_status: IgStatus,
) -> list[JsonArtifact]:
    """Build one `concept-maps/ConceptMap-<id>.json` per option set that emitted concepts."""
    return [
        _json_artifact(CONCEPT_MAP_DIRECTORY, f"ConceptMap-{concept_map.id}", concept_map)
        for concept_map in build_option_set_concept_maps(option_sets, config, canonical, ig_status=ig_status)
    ]


def option_set_concept_map_file_prefix(config: GenerateConfig) -> str:
    """The file-name prefix every option-set ConceptMap carries, which is what that family sweeps by.

    `concept-maps/` holds both terminology families, so neither one owns the directory outright:
    each sweeps the files its own id stem names and leaves the other's alone.
    """
    return f"ConceptMap-{_id_stem(config)}"


def option_set_code_fallback(option_set: OptionSetIn, config: GenerateConfig) -> bool:
    """Whether any concept of one set takes the UID because its DHIS2 code is unusable or already taken.

    Always false in id mode: the UID is the concept code there by choice, not by fall-back.
    """
    if config.concept_code_source != "code":
        return False
    return any(
        not assignment.from_dhis2_code
        for assignment in concept_assignments(option_set, config).assignments
        if assignment.code is not None
    )


def concept_assignments(source: ConceptSourceIn, config: GenerateConfig) -> ConceptAssignmentPlan:
    """Assign one source's concept codes in emission order, falling back to the UID when the code is taken.

    Concept codes are unique within a CodeSystem, so a member whose UID fall-back is itself
    taken - a peer carries that UID as its DHIS2 code - has no code left to take and receives
    none: the terminology emitter skips it rather than emit a duplicate concept, and an example
    leaves the answer that selects it unanswered rather than point at a concept nobody wrote.

    Every consumer reads its codes from here, so an emitted coding and an emitted concept can
    never disagree. The notes ride along on the plan; a consumer that is not the terminology
    target discards them, because that is where a fall-back belongs in the report.
    """
    ordered = _ordered_options(source)
    notes: list[GenerateNote] = []
    desired = [_desired_code(option, source, config, notes) for option in ordered]
    taken: set[str] = set()
    collided: list[str] = []
    skipped: list[str] = []
    assignments: list[ConceptAssignment] = []
    for option, wanted in zip(ordered, desired, strict=True):
        code = wanted.code
        from_dhis2_code = wanted.from_dhis2_code
        if code in taken:
            code = option.uid
            from_dhis2_code = False
            if code in taken:
                skipped.append(f"{wanted.code} ({option.uid})")
                assignments.append(ConceptAssignment(option=option))
                continue
            collided.append(f"{wanted.code} ({option.uid})")
        taken.add(code)
        assignments.append(ConceptAssignment(option=option, code=code, from_dhis2_code=from_dhis2_code))
    if collided:
        notes.append(
            aggregate_generate_note(
                GenerateNoteCategory.CODE_COLLISION,
                f"{len(collided)} {source.member_label} codes collided; fell back to the UID",
                collided,
            )
        )
    if skipped:
        notes.append(
            aggregate_generate_note(
                GenerateNoteCategory.CODE_COLLISION,
                f"{len(skipped)} {source.member_label}s could not receive a unique concept code; skipped",
                skipped,
            )
        )
    return ConceptAssignmentPlan(assignments=assignments, notes=notes)


def _json_artifact(directory: str, stem: str, resource: CodeSystem | ValueSet | ConceptMap) -> JsonArtifact:
    """Serialise one resource as the predefined-resource file the loader reads, in the directory it belongs to."""
    return JsonArtifact(
        relative_path=f"{directory}/{stem}.json",
        content=f"{resource.model_dump_json(exclude_none=True, by_alias=True, indent=2)}\n",
    )


def _build_concept_map(
    option_set: OptionSetIn,
    identity: OptionSetIdentity,
    config: GenerateConfig,
    systems: _OptionSetSystems,
    *,
    ig_status: IgStatus,
) -> ConceptMap | None:
    """Build one option set's ConceptMap, or None when the set emitted no concept to map."""
    groups = _concept_map_groups(concept_assignments(option_set, config), identity, systems)
    if not groups:
        return None
    return ConceptMap(
        id=identity.concept_map_id,
        url=systems.concept_map_url(identity.concept_map_id),
        identifier=Identifier(system=systems.identifier_system, value=option_set.uid),
        name=identity.concept_map_name,
        title=flatten_whitespace(option_set.name),
        title_element=translated_element(name_translations(option_set.translations, config.locales)),
        description=flatten_whitespace(
            f"DHIS2 option set {option_set.name} ({option_set.uid}). Every concept of "
            f"{identity.code_system_name} mapped to its DHIS2 option UID and, where the option carries "
            "one, its DHIS2 option code."
        ),
        status=ig_status,
        experimental=experimental_for_status(ig_status),
        sourceCanonical=systems.value_set_url(identity.value_set_id),
        group=groups,
    )


def _concept_map_groups(
    plan: ConceptAssignmentPlan, identity: OptionSetIdentity, systems: _OptionSetSystems
) -> list[ConceptMapGroup]:
    """The mapping groups of one set: the UID group always, the DHIS2-code group when any option has one.

    An option whose DHIS2 code is not a valid FHIR `code` cannot be a target code and is left out
    of the code group - the pair emitter already reports that code in a note when it is the concept
    code the set asked for.
    """
    mapped = [assignment for assignment in plan.assignments if assignment.code is not None]
    if not mapped:
        return []
    code_system_url = systems.code_system_url(identity.code_system_id)
    groups = [
        ConceptMapGroup(
            source=code_system_url,
            target=systems.option_identifier_system,
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
            ConceptMapGroup(source=code_system_url, target=systems.option_code_identifier_system, element=coded)
        )
    return groups


def _concept_map_element(assignment: ConceptAssignment, target_code: str) -> ConceptMapGroupElement:
    """One mapping row: the concept code the set assigned, and the DHIS2 identifier it stands for.

    The equivalence is `equal`: the concept and the target identifier name the same DHIS2 option,
    read under two identifier conventions rather than translated between two vocabularies.
    """
    return ConceptMapGroupElement(
        code=assignment.code,
        display=flatten_whitespace(assignment.option.name),
        target=[ConceptMapGroupElementTarget(code=target_code, equivalence="equal")],
    )


def _build_pair(
    option_set: OptionSetIn,
    identity: OptionSetIdentity,
    config: GenerateConfig,
    systems: _OptionSetSystems,
    notes: list[GenerateNote],
    *,
    ig_status: IgStatus,
    attribute_codes: AttributeCodeIndex,
    extension_url: str,
) -> _OptionSetPair:
    """Build the CodeSystem and the ValueSet of one option set, reporting what concept assignment raised."""
    concepts = build_concepts(option_set, config, notes)
    narrative = _narrative(
        option_set, config, systems, ig_status=ig_status, attribute_codes=attribute_codes, extension_url=extension_url
    )
    code_system_url = systems.code_system_url(identity.code_system_id)
    code_system = CodeSystem(
        id=identity.code_system_id,
        extension=narrative.extensions or None,
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
        property=_declarations(concepts, systems) or None,
        concept=concepts or None,
    )
    value_set = ValueSet(
        id=identity.value_set_id,
        extension=narrative.extensions or None,
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
    return _OptionSetPair(code_system=code_system, value_set=value_set)


def _narrative(
    option_set: OptionSetIn,
    config: GenerateConfig,
    systems: _OptionSetSystems,
    *,
    ig_status: IgStatus,
    attribute_codes: AttributeCodeIndex,
    extension_url: str,
) -> _OptionSetNarrative:
    """The elements both halves share: both DHIS2 identifiers, the attribute values, the title, the state."""
    code_kind = "option codes" if config.concept_code_source == "code" else "option UIDs"
    return _OptionSetNarrative(
        identifiers=[
            Identifier(system=systems.identifier_system, value=option_set.uid),
            Identifier(
                system=systems.code_identifier_system,
                value=code_or_uid(option_set.code, option_set.uid),
            ),
            *attribute_value_identifiers(option_set.attribute_values, attribute_codes, config.identifier_system_base),
        ],
        extensions=attribute_value_extensions(option_set.attribute_values, attribute_codes, extension_url),
        title=flatten_whitespace(option_set.name),
        title_element=translated_element(name_translations(option_set.translations, config.locales)),
        description=flatten_whitespace(
            f"DHIS2 option set {option_set.name} ({option_set.uid}). Concept codes are DHIS2 {code_kind}."
        ),
        status=ig_status,
        experimental=experimental_for_status(ig_status),
    )


def _declarations(concepts: list[CodeSystemConcept], systems: _OptionSetSystems) -> list[CodeSystemProperty]:
    """The CodeSystem-level declaration of every concept property the emitted concepts actually carry."""
    carried = {
        concept_property.code
        for concept in concepts
        for concept_property in concept.property or []
        if concept_property.code is not None
    }
    return [
        declaration.model_copy(update={"uri": f"{systems.property_base}/{declaration.code}"})
        for declaration in _PROPERTY_DECLARATIONS
        if declaration.code in carried
    ]


def _uid_option_set_identity(uid: str, config: GenerateConfig) -> OptionSetIdentity:
    """One option set's identity from its UID alone - what the index falls back to when the plan omits it.

    A UID the plan does not hold cannot be slug-assigned against its peers, so it takes the UID
    as its slug and as its name segment, which is what `naming.source = "id"` assigns anyway.
    """
    id_stem = _id_stem(config)
    return OptionSetIdentity(
        uid=uid,
        name=uid,
        slug=uid,
        fsh_name=option_set_fsh_name(config, uid),
        code_system_id=f"{id_stem}{uid}-cs",
        value_set_id=f"{id_stem}{uid}{_ID_SUFFIX}",
        concept_map_id=f"{id_stem}{uid}-cm",
    )


def _id_stem(config: GenerateConfig) -> str:
    """Build the id stem for option-set artifacts from the configured naming tokens."""
    joined = join_id_tokens(config.naming.prefix, config.naming.option_set)
    return f"{joined}-" if joined else ""


class _DesiredCode(BaseModel):
    """The concept code one option asks for before uniqueness is enforced."""

    model_config = ConfigDict(frozen=True)

    code: str
    from_dhis2_code: bool


def _desired_code(
    option: OptionIn, source: ConceptSourceIn, config: GenerateConfig, notes: list[GenerateNote]
) -> _DesiredCode:
    """Pick the concept code a member wants: its DHIS2 code in code mode when FHIR-valid, else the UID."""
    if config.concept_code_source != "code":
        return _DesiredCode(code=option.uid, from_dhis2_code=False)
    if is_valid_fhir_code(option.code):
        return _DesiredCode(code=option.code or "", from_dhis2_code=True)
    detail = "no code" if option.code is None else f"code {option.code!r} is not a valid FHIR code"
    notes.append(
        generate_note(
            GenerateNoteCategory.CODE_FALLBACK,
            f"{source.source_label} {source.name!r}: {source.member_label} {option.uid} has {detail}; "
            "falling back to the UID",
        )
    )
    return _DesiredCode(code=option.uid, from_dhis2_code=False)


def _concept_for(option: OptionIn, code: str, config: GenerateConfig) -> CodeSystemConcept:
    """Build the concept for one member, carrying the complementary DHIS2 identifier as a property.

    Every concept carries the pair: in code mode the UID rides along as `dhis2-id`, in id mode
    the DHIS2 code rides along as `dhis2-code` - falling back to the UID when there is no usable code.
    """
    designations = [
        CodeSystemConceptDesignation(language=translation.locale, value=flatten_whitespace(translation.value))
        for translation in name_translations(option.translations, config.locales)
    ]
    if config.concept_code_source == "code":
        carried = CodeSystemConceptProperty(code="dhis2-id", valueCode=option.uid)
    else:
        carried = CodeSystemConceptProperty(code="dhis2-code", valueString=code_or_uid(option.code, option.uid))
    return CodeSystemConcept(
        code=code,
        display=flatten_whitespace(option.name),
        property=[carried],
        designation=designations or None,
    )


def _ordered_options(source: ConceptSourceIn) -> list[OptionIn]:
    """One source's members in emission order: DHIS2 sort order first, then the UID for the unordered tail."""
    return sorted(source.options, key=lambda item: (item.sort_order is None, item.sort_order or 0, item.uid))


def build_concepts(
    source: ConceptSourceIn,
    config: GenerateConfig,
    notes: list[GenerateNote],
    *,
    member_properties: MemberPropertySource | None = None,
) -> list[CodeSystemConcept]:
    """Build one source's concepts from the assigned codes, in emission order, reporting what assignment raised.

    `member_properties` states the extra concept properties a member carries beyond the DHIS2
    identifier pair every concept rides - the category axes a category option combo decomposes
    over are the one source of them today.
    """
    plan = concept_assignments(source, config)
    notes.extend(plan.notes)
    concepts: list[CodeSystemConcept] = []
    for assignment in plan.assignments:
        if assignment.code is None:
            continue
        concept = _concept_for(assignment.option, assignment.code, config)
        extra = [] if member_properties is None else member_properties.properties_for(assignment.option.uid)
        if extra:
            concept = concept.model_copy(update={"property": [*(concept.property or []), *extra]})
        concepts.append(concept)
    return concepts
