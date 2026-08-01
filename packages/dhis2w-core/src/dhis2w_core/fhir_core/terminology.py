"""FSH emission for DHIS2 option sets: one CodeSystem + ValueSet pair per set.

Every concept carries both DHIS2 identifiers: whichever one is the concept
code, the other rides along as a concept property (`dhis2-code` or
`dhis2-uid`). With `concept_code_source = "code"`, options whose code is not a
valid FHIR code fall back to the UID with a note in the report.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from dhis2w_core.fhir_core.models import FshArtifact, FshBuild, GenerateConfig, OptionInput, OptionSetInput
from dhis2w_core.fhir_core.names import fsh_code, is_valid_fhir_code, kebab, pascal, quote


class _Concept(BaseModel):
    """One emitted concept: its code plus the companion-identifier property, if any."""

    model_config = ConfigDict(frozen=True)

    code: str
    display: str
    property_code: str | None = None
    property_line: str | None = None


# FHIR ids allow at most 64 characters. The longest emitted id is
# `dhis2-option-set-<slug>-cs`/`-vs`, so the slug itself is bounded to fit.
_MAX_FHIR_ID_LENGTH = 64
_ID_PREFIX = "dhis2-option-set-"
_ID_SUFFIX = "-vs"
_MAX_SLUG_LENGTH = _MAX_FHIR_ID_LENGTH - len(_ID_PREFIX) - len(_ID_SUFFIX)


def _bounded_slug(slug: str, uid: str) -> str:
    """Truncate an over-long slug and append the UID so bounded slugs stay unique."""
    head_length = _MAX_SLUG_LENGTH - len(uid) - 1
    return f"{slug[:head_length].rstrip('-')}-{uid.lower()}"


def build_option_set_artifacts(option_sets: list[OptionSetInput], config: GenerateConfig) -> FshBuild:
    """Build one `terminology/<slug>.fsh` artifact per option set, stable-sorted for clean diffs."""
    build = FshBuild()
    used_slugs: set[str] = set()
    for option_set in sorted(option_sets, key=lambda item: (item.name, item.uid)):
        slug = kebab(option_set.name)
        base_name = f"Dhis2OptionSet{pascal(option_set.name)}"
        if len(slug) > _MAX_SLUG_LENGTH:
            slug = _bounded_slug(slug, option_set.uid)
            build.notes.append(
                f"option set {option_set.uid}: name {option_set.name!r} exceeds the FHIR id length; using {slug!r}"
            )
        elif slug in used_slugs:
            slug = _bounded_slug(slug, option_set.uid)
            base_name = f"{base_name}{option_set.uid}"
            build.notes.append(f"option set {option_set.uid}: name {option_set.name!r} is not unique; using {slug!r}")
        used_slugs.add(slug)
        content = _option_set_fsh(option_set, base_name, slug, config, build.notes)
        build.artifacts.append(
            FshArtifact(
                relative_path=f"terminology/{slug}.fsh",
                kind="terminology-pair",
                fsh_name=base_name,
                content=content,
            )
        )
    return build


def _concept_for(option: OptionInput, option_set: OptionSetInput, config: GenerateConfig, notes: list[str]) -> _Concept:
    """Pick the concept code per `concept_code_source` and carry the other identifier as a property."""
    if config.concept_code_source == "code" and is_valid_fhir_code(option.code):
        return _Concept(
            code=option.code or "",
            display=option.name,
            property_code="dhis2-uid",
            property_line=f"^property[=].valueCode = #{option.uid}",
        )
    if config.concept_code_source == "code":
        detail = "no code" if option.code is None else f"code {option.code!r} is not a valid FHIR code"
        notes.append(f"option set {option_set.name!r}: option {option.uid} has {detail}; falling back to the UID")
    if option.code is None:
        return _Concept(code=option.uid, display=option.name)
    return _Concept(
        code=option.uid,
        display=option.name,
        property_code="dhis2-code",
        property_line=f"^property[=].valueString = {quote(option.code)}",
    )


_PROPERTY_DECLARATIONS = {
    "dhis2-code": ("DHIS2 option code.", "string"),
    "dhis2-uid": ("DHIS2 option UID.", "code"),
}


def _option_set_fsh(
    option_set: OptionSetInput,
    base_name: str,
    slug: str,
    config: GenerateConfig,
    notes: list[str],
) -> str:
    """Render the CodeSystem + ValueSet FSH for one option set."""
    ordered = sorted(option_set.options, key=lambda item: (item.sort_order is None, item.sort_order or 0, item.uid))
    concepts = [_concept_for(option, option_set, config, notes) for option in ordered]
    code_kind = "option codes" if config.concept_code_source == "code" else "option UIDs"
    description = quote(f"DHIS2 option set {option_set.name} ({option_set.uid}). Concept codes are DHIS2 {code_kind}.")

    lines = [
        f"CodeSystem: {base_name}CS",
        f"Id: dhis2-option-set-{slug}-cs",
        f"Title: {quote(option_set.name)}",
        f"Description: {description}",
        "* ^status = #active",
        "* ^content = #complete",
        "* ^caseSensitive = true",
    ]
    for property_code in _PROPERTY_DECLARATIONS:
        if any(concept.property_code == property_code for concept in concepts):
            declaration_description, declaration_type = _PROPERTY_DECLARATIONS[property_code]
            lines.extend(
                [
                    f"* ^property[+].code = #{property_code}",
                    f'* ^property[=].description = "{declaration_description}"',
                    f"* ^property[=].type = #{declaration_type}",
                ]
            )
    for concept in concepts:
        lines.append(f"* {fsh_code(concept.code)} {quote(concept.display)}")
        if concept.property_code is not None:
            lines.append(f"* {fsh_code(concept.code)} ^property[+].code = #{concept.property_code}")
            lines.append(f"* {fsh_code(concept.code)} {concept.property_line}")
    lines.extend(
        [
            "",
            f"ValueSet: {base_name}VS",
            f"Id: dhis2-option-set-{slug}-vs",
            f"Title: {quote(option_set.name)}",
            f"Description: {description}",
            "* ^status = #active",
            f"* include codes from system {base_name}CS",
        ]
    )
    return "\n".join(lines) + "\n"
