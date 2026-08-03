"""FSH emission for DHIS2 option sets: one CodeSystem + ValueSet pair per set.

Every concept carries both DHIS2 identifiers: whichever one is the concept
code, the other rides along as a concept property (`dhis2-code` or
`dhis2-id`). With `concept_code_source = "code"`, options whose code is not a
valid FHIR code fall back to the UID with a note in the report.

Concept codes are unique within a set by construction: a first pass computes
each option's desired code, a second assigns them in sortOrder and falls back
to the option UID whenever the desired code is already taken. An option whose
UID fall-back is taken too - a peer carries that UID as its DHIS2 code - is
skipped with a note rather than emitted as a duplicate concept.

With `naming.source = "id"` the slug is the option-set UID verbatim: FHIR ids
and file names both permit mixed case, so the emitted id reads straight back to
the DHIS2 object. Name-sourced slugs are kebab-cased as usual.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.i18n import TRANSLATION_EXTENSION_URL, TranslationIn, name_translations
from dhis2w_fhir.names import (
    code_or_uid,
    fsh_code,
    is_valid_fhir_code,
    join_id_tokens,
    join_name_segments,
    kebab,
    pascal,
    quote,
)
from dhis2w_fhir.notes import aggregate_note
from dhis2w_fhir.resources.option_sets.schemas import (
    ConceptAssignment,
    ConceptAssignmentPlan,
    OptionIn,
    OptionSetIdentity,
    OptionSetIdentityIndex,
    OptionSetIdentityPlan,
    OptionSetIn,
)
from dhis2w_fhir.status import IgStatus, experimental_for_status
from dhis2w_fhir.writer import FshArtifact, FshBuild

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig

__all__ = [
    "build_option_set_artifacts",
    "concept_assignments",
    "max_slug_length",
    "option_set_code_fallback",
    "option_set_fsh_name",
    "option_set_identities",
    "option_set_identity_index",
]

_ENVIRONMENT = Environment(
    loader=PackageLoader("dhis2w_fhir.resources.option_sets", "templates"),
    autoescape=select_autoescape(default=False),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)

# FHIR ids allow at most 64 characters. The longest emitted id is
# `<id-stem><slug>-cs`/`-vs`, so the slug is bounded against the actual stem.
_MAX_FHIR_ID_LENGTH = 64
_ID_SUFFIX = "-vs"


class _Concept(BaseModel):
    """One emitted concept: its code, the companion-identifier property, and its name designations."""

    model_config = ConfigDict(frozen=True)

    code: str
    display: str
    property_code: str | None = None
    property_line: str | None = None
    designations: list[TranslationIn] = Field(default_factory=list)

    @property
    def token(self) -> str:
        """The `#code` token this concept is addressed by in FSH."""
        return fsh_code(self.code)

    @property
    def display_literal(self) -> str:
        """The concept display as a quoted FSH string literal."""
        return quote(self.display)


class _PropertyDeclaration(BaseModel):
    """CodeSystem-level declaration of a concept property."""

    model_config = ConfigDict(frozen=True)

    code: str
    description: str
    type: str


_PROPERTY_DECLARATIONS = (
    _PropertyDeclaration(code="dhis2-code", description="DHIS2 option code.", type="string"),
    _PropertyDeclaration(code="dhis2-id", description="DHIS2 option UID.", type="code"),
)


def option_set_fsh_name(config: GenerateConfig, segment: str) -> str:
    """FSH name stem for one option set: the merged naming tokens, then the UID or the pascal name.

    The emitted CodeSystem and ValueSet append `_CS` and `_VS` to it, so `D2OS_BirthType`
    names the pair `D2OS_BirthType_CS` / `D2OS_BirthType_VS`.
    """
    return join_name_segments(f"{config.naming.prefix}{config.naming.option_set}", segment)


def max_slug_length(config: GenerateConfig) -> int:
    """Longest slug that keeps every emitted id within the FHIR id limit."""
    return _MAX_FHIR_ID_LENGTH - len(_id_stem(config)) - len(_ID_SUFFIX)


def option_set_identities(option_sets: list[OptionSetIn], config: GenerateConfig) -> OptionSetIdentityPlan:
    """Assign every option set its emitted slug, FSH name, and artifact ids, in emission order.

    The one place the slug is decided: the emitter names its files from it and the narrative
    pages link to `CodeSystem-<code_system_id>.html` from it, so the two cannot drift.
    """
    plan = OptionSetIdentityPlan()
    id_stem = _id_stem(config)
    used_slugs: set[str] = set()
    truncated: list[str] = []
    collided: list[str] = []
    slug_limit = max_slug_length(config)
    for option_set in sorted(option_sets, key=lambda item: (item.name, item.uid)):
        if config.naming.source == "id":
            slug = option_set.uid
            base_name = option_set_fsh_name(config, option_set.uid)
        else:
            slug = kebab(option_set.name)
            base_name = option_set_fsh_name(config, pascal(option_set.name))
            if len(slug) > slug_limit:
                slug = _bounded_slug(slug, option_set.uid, slug_limit)
                truncated.append(option_set.name)
            elif slug in used_slugs:
                slug = _bounded_slug(slug, option_set.uid, slug_limit)
                base_name = join_name_segments(base_name, option_set.uid)
                collided.append(option_set.name)
        used_slugs.add(slug)
        plan.identities.append(
            OptionSetIdentity(
                uid=option_set.uid,
                name=option_set.name,
                slug=slug,
                fsh_name=base_name,
                code_system_id=f"{id_stem}{slug}-cs",
                value_set_id=f"{id_stem}{slug}{_ID_SUFFIX}",
            )
        )
    if truncated:
        plan.notes.append(
            aggregate_note(
                f"{len(truncated)} option set names exceed the FHIR id length; ids truncated with a UID suffix",
                truncated,
            )
        )
    if collided:
        plan.notes.append(
            aggregate_note(
                f"{len(collided)} option set names are not unique; ids disambiguated with a UID suffix", collided
            )
        )
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
    option_sets: list[OptionSetIn], config: GenerateConfig, *, ig_status: IgStatus
) -> FshBuild:
    """Build one `terminology/<slug>.fsh` artifact per option set, stable-sorted for clean diffs."""
    build = FshBuild()
    plan = option_set_identities(option_sets, config)
    by_uid = {option_set.uid: option_set for option_set in option_sets}
    for identity in plan.identities:
        option_set = by_uid[identity.uid]
        content = _render_option_set(option_set, identity, config, build.notes, ig_status=ig_status)
        build.artifacts.append(
            FshArtifact(
                relative_path=f"terminology/{identity.slug}.fsh",
                kind="terminology-pair",
                fsh_name=identity.fsh_name,
                content=content,
            )
        )
    build.notes.extend(plan.notes)
    return build


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


def concept_assignments(option_set: OptionSetIn, config: GenerateConfig) -> ConceptAssignmentPlan:
    """Assign one set's concept codes in emission order, falling back to the UID when the desired code is taken.

    Concept codes are unique within a CodeSystem, so an option whose UID fall-back is itself
    taken - a peer carries that UID as its DHIS2 code - has no code left to take and receives
    none: the terminology emitter skips it rather than emit a duplicate concept, and an example
    leaves the answer that selects it unanswered rather than point at a concept nobody wrote.

    Every consumer reads its codes from here, so an emitted coding and an emitted concept can
    never disagree. The notes ride along on the plan; a consumer that is not the terminology
    target discards them, because that is where a fall-back belongs in the report.
    """
    ordered = _ordered_options(option_set)
    notes: list[str] = []
    desired = [_desired_code(option, option_set, config, notes) for option in ordered]
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
        notes.append(aggregate_note(f"{len(collided)} option codes collided; fell back to the UID", collided))
    if skipped:
        notes.append(
            aggregate_note(f"{len(skipped)} options could not receive a unique concept code; skipped", skipped)
        )
    return ConceptAssignmentPlan(assignments=assignments, notes=notes)


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
    )


def _id_stem(config: GenerateConfig) -> str:
    """Build the id stem for option-set artifacts from the configured naming tokens."""
    joined = join_id_tokens(config.naming.prefix, config.naming.option_set)
    return f"{joined}-" if joined else ""


def _bounded_slug(slug: str, uid: str, limit: int) -> str:
    """Truncate an over-long slug and append the UID so bounded slugs stay unique."""
    head_length = limit - len(uid) - 1
    return f"{slug[:head_length].rstrip('-')}-{uid.lower()}"


class _DesiredCode(BaseModel):
    """The concept code one option asks for before uniqueness is enforced."""

    model_config = ConfigDict(frozen=True)

    code: str
    from_dhis2_code: bool


def _desired_code(option: OptionIn, option_set: OptionSetIn, config: GenerateConfig, notes: list[str]) -> _DesiredCode:
    """Pick the concept code an option wants: its DHIS2 code in code mode when FHIR-valid, else the UID."""
    if config.concept_code_source != "code":
        return _DesiredCode(code=option.uid, from_dhis2_code=False)
    if is_valid_fhir_code(option.code):
        return _DesiredCode(code=option.code or "", from_dhis2_code=True)
    detail = "no code" if option.code is None else f"code {option.code!r} is not a valid FHIR code"
    notes.append(f"option set {option_set.name!r}: option {option.uid} has {detail}; falling back to the UID")
    return _DesiredCode(code=option.uid, from_dhis2_code=False)


def _concept_for(option: OptionIn, code: str, config: GenerateConfig) -> _Concept:
    """Build the concept for one option, carrying the complementary DHIS2 identifier as a property.

    Every concept carries the pair: in code mode the UID rides along as `dhis2-id`, in id mode
    the DHIS2 code rides along as `dhis2-code` - falling back to the UID when there is no usable code.
    """
    designations = name_translations(option.translations, config.locales)
    if config.concept_code_source == "code":
        return _Concept(
            code=code,
            display=option.name,
            property_code="dhis2-id",
            property_line=f"^property[=].valueCode = #{option.uid}",
            designations=designations,
        )
    return _Concept(
        code=code,
        display=option.name,
        property_code="dhis2-code",
        property_line=f"^property[=].valueString = {quote(code_or_uid(option.code, option.uid))}",
        designations=designations,
    )


def _ordered_options(option_set: OptionSetIn) -> list[OptionIn]:
    """One set's options in emission order: DHIS2 sort order first, then the UID for the unordered tail."""
    return sorted(option_set.options, key=lambda item: (item.sort_order is None, item.sort_order or 0, item.uid))


def _unique_concepts(option_set: OptionSetIn, config: GenerateConfig, notes: list[str]) -> list[_Concept]:
    """Build one set's concepts from the assigned codes, in emission order, reporting what assignment raised."""
    plan = concept_assignments(option_set, config)
    notes.extend(plan.notes)
    return [
        _concept_for(assignment.option, assignment.code, config)
        for assignment in plan.assignments
        if assignment.code is not None
    ]


def _render_option_set(
    option_set: OptionSetIn,
    identity: OptionSetIdentity,
    config: GenerateConfig,
    notes: list[str],
    *,
    ig_status: IgStatus,
) -> str:
    """Render the CodeSystem + ValueSet FSH for one option set."""
    concepts = _unique_concepts(option_set, config, notes)
    used_property_codes = {concept.property_code for concept in concepts}
    code_kind = "option codes" if config.concept_code_source == "code" else "option UIDs"
    description = quote(f"DHIS2 option set {option_set.name} ({option_set.uid}). Concept codes are DHIS2 {code_kind}.")
    return _ENVIRONMENT.get_template("option-set.fsh.jinja").render(
        code_system_name=identity.code_system_name,
        value_set_name=identity.value_set_name,
        id_stem=_id_stem(config),
        slug=identity.slug,
        title=quote(option_set.name),
        description=description,
        option_set_uid=option_set.uid,
        option_set_code=code_or_uid(option_set.code, option_set.uid),
        property_base=f"{config.identifier_system_base}/property",
        declarations=[declaration for declaration in _PROPERTY_DECLARATIONS if declaration.code in used_property_codes],
        concepts=concepts,
        title_translations=name_translations(option_set.translations, config.locales),
        translation_extension_url=TRANSLATION_EXTENSION_URL,
        ig_status=ig_status,
        experimental=experimental_for_status(ig_status),
    )
