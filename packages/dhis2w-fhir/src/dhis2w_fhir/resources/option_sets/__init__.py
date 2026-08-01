"""FSH emission for DHIS2 option sets: one CodeSystem + ValueSet pair per set.

Every concept carries both DHIS2 identifiers: whichever one is the concept
code, the other rides along as a concept property (`dhis2-code` or
`dhis2-uid`). With `concept_code_source = "code"`, options whose code is not a
valid FHIR code fall back to the UID with a note in the report.

Concept codes are unique within a set by construction: a first pass computes
each option's desired code, a second assigns them in sortOrder and falls back
to the option UID whenever the desired code is already taken.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.names import code_or_uid, fsh_code, is_valid_fhir_code, join_id_tokens, kebab, pascal, quote
from dhis2w_fhir.notes import aggregate_note
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIn
from dhis2w_fhir.writer import FshArtifact, FshBuild

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig

__all__ = ["build_option_set_artifacts", "max_slug_length"]

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
    """One emitted concept: its code plus the companion-identifier property, if any."""

    model_config = ConfigDict(frozen=True)

    code: str
    display: str
    property_code: str | None = None
    property_line: str | None = None

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
    _PropertyDeclaration(code="dhis2-uid", description="DHIS2 option UID.", type="code"),
)


def max_slug_length(config: GenerateConfig) -> int:
    """Longest slug that keeps every emitted id within the FHIR id limit."""
    return _MAX_FHIR_ID_LENGTH - len(_id_stem(config)) - len(_ID_SUFFIX)


def build_option_set_artifacts(option_sets: list[OptionSetIn], config: GenerateConfig) -> FshBuild:
    """Build one `terminology/<slug>.fsh` artifact per option set, stable-sorted for clean diffs."""
    build = FshBuild()
    used_slugs: set[str] = set()
    truncated: list[str] = []
    collided: list[str] = []
    slug_limit = max_slug_length(config)
    for option_set in sorted(option_sets, key=lambda item: (item.name, item.uid)):
        if config.naming.source == "uid":
            slug = option_set.uid.lower()
            base_name = f"{config.naming.prefix}{config.naming.option_set}{option_set.uid}"
        else:
            slug = kebab(option_set.name)
            base_name = f"{config.naming.prefix}{config.naming.option_set}{pascal(option_set.name)}"
            if len(slug) > slug_limit:
                slug = _bounded_slug(slug, option_set.uid, slug_limit)
                truncated.append(option_set.name)
            elif slug in used_slugs:
                slug = _bounded_slug(slug, option_set.uid, slug_limit)
                base_name = f"{base_name}{option_set.uid}"
                collided.append(option_set.name)
        used_slugs.add(slug)
        content = _render_option_set(option_set, base_name, slug, config, build.notes)
        build.artifacts.append(
            FshArtifact(
                relative_path=f"terminology/{slug}.fsh",
                kind="terminology-pair",
                fsh_name=base_name,
                content=content,
            )
        )
    if truncated:
        build.notes.append(
            aggregate_note(
                f"{len(truncated)} option set names exceed the FHIR id length; ids truncated with a UID suffix",
                truncated,
            )
        )
    if collided:
        build.notes.append(
            aggregate_note(
                f"{len(collided)} option set names are not unique; ids disambiguated with a UID suffix", collided
            )
        )
    return build


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


def _concept_for(option: OptionIn, assigned: _DesiredCode, config: GenerateConfig) -> _Concept:
    """Build the concept for one option, carrying the complementary DHIS2 identifier as a property.

    Every concept carries the pair: in code mode the UID rides along as `dhis2-uid`, in uid mode
    the DHIS2 code rides along as `dhis2-code` - falling back to the UID when there is no usable code.
    """
    if config.concept_code_source == "code":
        return _Concept(
            code=assigned.code,
            display=option.name,
            property_code="dhis2-uid",
            property_line=f"^property[=].valueCode = #{option.uid}",
        )
    return _Concept(
        code=assigned.code,
        display=option.name,
        property_code="dhis2-code",
        property_line=f"^property[=].valueString = {quote(code_or_uid(option.code, option.uid))}",
    )


def _unique_concepts(
    ordered: list[OptionIn], option_set: OptionSetIn, config: GenerateConfig, notes: list[str]
) -> list[_Concept]:
    """Assign concept codes in order, falling back to the UID whenever the desired code is already taken."""
    desired = [_desired_code(option, option_set, config, notes) for option in ordered]
    taken: set[str] = set()
    collided: list[str] = []
    concepts: list[_Concept] = []
    for option, wanted in zip(ordered, desired, strict=True):
        assigned = wanted
        if wanted.code in taken:
            collided.append(f"{wanted.code} ({option.uid})")
            assigned = _DesiredCode(code=option.uid, from_dhis2_code=False)
        taken.add(assigned.code)
        concepts.append(_concept_for(option, assigned, config))
    if collided:
        notes.append(aggregate_note(f"{len(collided)} option codes collided; fell back to the UID", collided))
    return concepts


def _render_option_set(
    option_set: OptionSetIn,
    base_name: str,
    slug: str,
    config: GenerateConfig,
    notes: list[str],
) -> str:
    """Render the CodeSystem + ValueSet FSH for one option set."""
    ordered = sorted(option_set.options, key=lambda item: (item.sort_order is None, item.sort_order or 0, item.uid))
    concepts = _unique_concepts(ordered, option_set, config, notes)
    used_property_codes = {concept.property_code for concept in concepts}
    code_kind = "option codes" if config.concept_code_source == "code" else "option UIDs"
    description = quote(f"DHIS2 option set {option_set.name} ({option_set.uid}). Concept codes are DHIS2 {code_kind}.")
    return _ENVIRONMENT.get_template("option-set.fsh.jinja").render(
        base_name=base_name,
        id_stem=_id_stem(config),
        slug=slug,
        title=quote(option_set.name),
        description=description,
        identifiers=_business_identifiers(option_set, config),
        declarations=[declaration for declaration in _PROPERTY_DECLARATIONS if declaration.code in used_property_codes],
        concepts=concepts,
    )


class _BusinessIdentifier(BaseModel):
    """One `^identifier` pair on a generated CodeSystem/ValueSet: the system URI and the value."""

    model_config = ConfigDict(frozen=True)

    system: str
    value: str


def _business_identifiers(option_set: OptionSetIn, config: GenerateConfig) -> list[_BusinessIdentifier]:
    """Both DHIS2 identifiers of the source option set, the code slot falling back to the UID."""
    base = config.identifier_system_base
    return [
        _BusinessIdentifier(system=f"{base}/id/option-set", value=option_set.uid),
        _BusinessIdentifier(system=f"{base}/id/option-set-code", value=code_or_uid(option_set.code, option_set.uid)),
    ]
