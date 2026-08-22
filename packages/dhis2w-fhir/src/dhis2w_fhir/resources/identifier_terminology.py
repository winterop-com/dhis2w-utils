"""The DHIS2 identifier namespaces a guide's ConceptMaps target, published as complete CodeSystems.

The foundation target declares every DHIS2 identifier namespace - `<base>/id/option`,
`<base>/id/category-option-combo`, and the rest - as a NamingSystem. A NamingSystem states what a
namespace is; it enumerates nothing, and it answers no `$validate-code`. Every ConceptMap row is
validated against the system its target code sits in, so a guide whose namespaces exist only as
NamingSystems sends the terminology server one un-batched request per row and is told
UNKNOWN_CODESYSTEM every time: on a national selection that was 4,779 requests, 57 percent of them
byte-identical repeats, and the publisher spent the wait idle rather than working.

Beside each namespace a map targets, this emits a CodeSystem at the same URL with
`content: complete` and every targeted identifier enumerated, so the publisher answers the question
out of the guide instead of over the network. `content: not-present` does not do it - the publisher
reads that as "the codes are elsewhere" and asks the server anyway.

The two declarations coexist by design: the NamingSystem says the URL identifies DHIS2 objects, the
CodeSystem says which identifiers this guide actually uses. Each family owns the CodeSystems for the
namespaces its own maps target, and writes them into its own resource directory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.foundation.schemas import IDENTIFIER_SYSTEM_SUBJECTS, FoundationNaming
from dhis2w_fhir.names import join_id_tokens
from dhis2w_fhir.r4 import CodeSystem, CodeSystemConcept
from dhis2w_fhir.status import experimental_for_status
from dhis2w_fhir.writer import JsonArtifact

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig
    from dhis2w_fhir.r4 import ConceptMap
    from dhis2w_fhir.status import IgStatus

__all__ = [
    "build_identifier_code_system_artifacts",
    "build_identifier_code_systems",
]


class _IdentifierSystemProfile(BaseModel):
    """The identity and prose one identifier namespace publishes its CodeSystem under."""

    model_config = ConfigDict(frozen=True)

    url: str
    code_system_id: str
    name: str
    title: str
    description: str


class _TargetedIdentifier(BaseModel):
    """One identifier a ConceptMap targets, and what the mapped concept calls it."""

    model_config = ConfigDict(frozen=True)

    code: str
    display: str | None = None


def build_identifier_code_systems(
    concept_maps: list[ConceptMap], config: GenerateConfig, *, ig_status: IgStatus
) -> list[CodeSystem]:
    """Build one complete CodeSystem per DHIS2 identifier namespace the given ConceptMaps target.

    The namespaces are read off the maps rather than assumed, so a family that grows a group can
    never leave its new target system un-enumerated. A target system that is not a declared DHIS2
    identifier namespace - the core FHIR resource-type system the tracked entity type map targets,
    say - is left alone: the publisher already holds it.
    """
    profiles = _identifier_system_profiles(config)
    gathered = _targeted_identifiers(concept_maps)
    return [
        _build_code_system(profiles[url], identifiers, ig_status=ig_status)
        for url, identifiers in sorted(gathered.items())
        if url in profiles
    ]


def build_identifier_code_system_artifacts(
    directory: str, concept_maps: list[ConceptMap], config: GenerateConfig, *, ig_status: IgStatus
) -> list[JsonArtifact]:
    """Build one `<directory>/CodeSystem-<id>.json` per identifier namespace the given ConceptMaps target."""
    return [
        JsonArtifact(
            relative_path=f"{directory}/CodeSystem-{code_system.id}.json",
            content=f"{code_system.model_dump_json(exclude_none=True, by_alias=True, indent=2)}\n",
        )
        for code_system in build_identifier_code_systems(concept_maps, config, ig_status=ig_status)
    ]


def _build_code_system(
    profile: _IdentifierSystemProfile, identifiers: list[_TargetedIdentifier], *, ig_status: IgStatus
) -> CodeSystem:
    """Build one namespace's CodeSystem: every targeted identifier, enumerated once and marked complete."""
    concepts = _distinct_concepts(identifiers)
    return CodeSystem(
        id=profile.code_system_id,
        url=profile.url,
        name=profile.name,
        title=profile.title,
        description=profile.description,
        status=ig_status,
        experimental=experimental_for_status(ig_status),
        caseSensitive=True,
        content="complete",
        count=len(concepts),
        concept=concepts,
    )


def _distinct_concepts(identifiers: list[_TargetedIdentifier]) -> list[CodeSystemConcept]:
    """One concept per identifier, the first display a code was seen under winning, in the order given.

    A namespace is enumerated off every map that targets it, and two DHIS2 objects legitimately
    share one code across the sets they belong to - two option sets both holding a `Preeclampsia`
    option, say. One code is one concept: the IG publisher anchors a concept row by its code, so a
    code stated twice yields two rows carrying one anchor id, which its own QA pass reports as a
    duplicate anchor on the rendered page. The invariant is enforced here, at the one place a
    concept list is built, rather than left to each caller's gathering step.
    """
    concepts: dict[str, CodeSystemConcept] = {}
    for entry in identifiers:
        concepts.setdefault(entry.code, CodeSystemConcept(code=entry.code, display=entry.display))
    return list(concepts.values())


def _targeted_identifiers(concept_maps: list[ConceptMap]) -> dict[str, list[_TargetedIdentifier]]:
    """Collect every target code the given maps carry, keyed by the system it sits in, sorted by code.

    The first display a code is seen under wins and the rows sort by code, so a regenerate of an
    unchanged selection produces byte-identical files whatever order the maps arrived in.
    """
    gathered: dict[str, dict[str, str | None]] = {}
    for concept_map in concept_maps:
        for group in concept_map.group or []:
            if group.target is None:
                continue
            bucket = gathered.setdefault(group.target, {})
            for element in group.element or []:
                for target in element.target or []:
                    if target.code is None or target.code in bucket:
                        continue
                    bucket[target.code] = element.display
    return {
        system: [_TargetedIdentifier(code=code, display=display) for code, display in sorted(bucket.items())]
        for system, bucket in gathered.items()
    }


def _identifier_system_profiles(config: GenerateConfig) -> dict[str, _IdentifierSystemProfile]:
    """Every declared DHIS2 identifier namespace, keyed by URL, in the words its CodeSystem publishes under.

    Walks the same subject list `build_naming_system_declarations` walks, so the CodeSystem and the
    NamingSystem of one namespace can never name different URLs.
    """
    prefix = FoundationNaming.from_naming(config.naming).definition_prefix
    base = config.identifier_system_base
    profiles: dict[str, _IdentifierSystemProfile] = {}
    for subject in IDENTIFIER_SYSTEM_SUBJECTS:
        profiles[f"{base}/id/{subject.segment}"] = _IdentifierSystemProfile(
            url=f"{base}/id/{subject.segment}",
            code_system_id=join_id_tokens(prefix, subject.token, "id-cs"),
            name=f"{prefix}{subject.token}IdentifierSystem_CS",
            title=f"DHIS2 {subject.label} UIDs in use",
            description=_description(subject.label, "UID", f"{prefix}{subject.token}IdentifierSystem"),
        )
        if not subject.has_code:
            continue
        profiles[f"{base}/id/{subject.segment}-code"] = _IdentifierSystemProfile(
            url=f"{base}/id/{subject.segment}-code",
            code_system_id=join_id_tokens(prefix, subject.token, "code-id-cs"),
            name=f"{prefix}{subject.token}CodeIdentifierSystem_CS",
            title=f"DHIS2 {subject.label} codes in use",
            description=_description(subject.label, "code", f"{prefix}{subject.token}CodeIdentifierSystem"),
        )
    return profiles


def _description(label: str, identifier_kind: str, naming_system_name: str) -> str:
    """The prose one identifier CodeSystem publishes under, naming its NamingSystem twin and its purpose."""
    return (
        f"Every DHIS2 {label} {identifier_kind} this guide's concept maps target, enumerated. "
        f"{naming_system_name} declares the same URL as an identifier system, which states what the "
        "namespace is without listing what is in it; this code system lists it, so a consumer - and "
        "the IG publisher - validates a mapped identifier out of the guide rather than against a "
        "terminology server."
    )
