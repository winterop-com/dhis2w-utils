"""The organisation-unit profiles in FSH, and the registry of pre-built Organization/Location JSON.

Each organisation unit becomes an Organization instance with DHIS2 UID/code
identifier slices plus a Location instance - the FHIR pair of legal entity
and physical place - with `partOf` mirroring the hierarchy on both sides.

The two profiles are FSH, because a profile is a StructureDefinition SUSHI
derives from its parent. The instances are written as finished FHIR JSON into
the predefined-resource tree, which the publisher loads verbatim: a registry
of thousands of units never enters the FSH compile at all.

Artifact names honour the configurable `[generate.naming]` tokens. The two
profile names always carry a token (falling back to `D2` when the prefix is
empty) because FSH cannot name a profile identically to its parent core
resource.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.foundation.attribute_values import (
    attribute_value_extension_url,
    attribute_value_extensions,
    attribute_value_identifiers,
)
from dhis2w_fhir.foundation.schemas import FoundationNaming
from dhis2w_fhir.i18n import name_translations, translated_element
from dhis2w_fhir.names import (
    FHIR_ID_MAX_LENGTH,
    NamingSource,
    StemResolution,
    StemSubject,
    code_or_uid,
    flatten_whitespace,
    page_text,
    quote,
    resolve_identity_stems,
)
from dhis2w_fhir.notes import GenerateNoteCategory, aggregate_generate_note
from dhis2w_fhir.r4 import (
    BOUNDARY_EXTENSION_URL,
    CodeableConcept,
    Coding,
    ContactPoint,
    HumanName,
    Identifier,
    Location,
    Meta,
    Organization,
    OrganizationContact,
    Reference,
)
from dhis2w_fhir.resources.organisation_units.location import build_location
from dhis2w_fhir.resources.organisation_units.naming import (
    OrganisationUnitInstanceUrls,
    OrganisationUnitNaming,
)
from dhis2w_fhir.status import IgStatus, experimental_for_status
from dhis2w_fhir.writer import FshArtifact, JsonArtifact, JsonBuild

if TYPE_CHECKING:
    from dhis2w_fhir.attributes import AttributeCodeIndex
    from dhis2w_fhir.config import GenerateConfig
    from dhis2w_fhir.resources.organisation_units.schemas import OrganisationUnitIn

#: The `ig/input/resources/` subdirectory the registry owns outright - one JSON file per resource.
REGISTRY_DIRECTORY = "registry"

#: The surface label organisation-unit stem notes and refusals name their offenders under.
ORGANISATION_UNIT_STEM_SURFACE = "organisation unit"


def organisation_unit_stem_subjects(organisation_units: list[OrganisationUnitIn]) -> list[StemSubject]:
    """Project the fetched selection onto the stem subjects its identity resolution runs over."""
    return [
        StemSubject(uid=organisation_unit.uid, code=organisation_unit.code, label=organisation_unit.name)
        for organisation_unit in organisation_units
    ]


def plan_organisation_unit_stems(subjects: list[StemSubject], source: NamingSource) -> StemResolution:
    """Resolve the org-unit surface's identity stems once per run - the single source every emitter reads.

    A unit's stem is its Organization and Location resource id, both file names, and every
    `Organization/...` / `Location/...` reference the run emits - the registry, the examples,
    and the intro pages all read this one resolution, so a reference can never dangle. The
    subjects come from `organisation_unit_stem_subjects`, or from a lighter id/code/name read
    under the same selection filters when the full projection was not fetched. The whole
    selection resolves in one call, so the collision scan sees every peer. The stem is the whole
    resource id, so the budget is the R4 id limit itself - the same number validate states for
    this surface.
    """
    return resolve_identity_stems(subjects, source, ORGANISATION_UNIT_STEM_SURFACE, max_stem_length=FHIR_ID_MAX_LENGTH)


_ENVIRONMENT = Environment(
    loader=PackageLoader("dhis2w_fhir.resources.organisation_units", "templates"),
    autoescape=select_autoescape(default=False),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def build_organisation_unit_profiles(config: GenerateConfig, *, ig_status: IgStatus) -> FshArtifact:
    """Build the static `organization/profiles.fsh` defining the Organization and Location profiles."""
    names = OrganisationUnitNaming.from_naming(config.naming)
    return FshArtifact(
        relative_path="organization/profiles.fsh",
        kind="profile",
        fsh_name=names.organization_profile,
        content=_ENVIRONMENT.get_template("profiles.fsh.jinja").render(
            names=names,
            boundary_extension_url=BOUNDARY_EXTENSION_URL,
            level_extension=FoundationNaming.from_naming(config.naming).organisation_unit_level_extension,
            ig_status=ig_status,
            experimental=experimental_for_status(ig_status),
        ),
    )


class _RegistryExampleView(BaseModel):
    """The one worked Organization/Location pair the registry profiles are illustrated with."""

    model_config = ConfigDict(frozen=True)

    organization_profile: str
    location_profile: str
    organization_name: str
    location_name: str
    organization_id: str
    location_id: str
    organization_title_literal: str
    location_title_literal: str
    organization_description_literal: str
    location_description_literal: str
    location_description_element_literal: str
    """The same prose as `location_description_literal`, unescaped, for the `description` element.

    A Location carries `description` as data, and the keyword above names the artifact in the
    guide's own pages - the split the Questionnaire emitter makes between its `Title:` keyword and
    its `* title` assignment. An Organization needs no twin: R4 gives it no `description`.
    """

    level_code_system: str
    level: int
    uid_literal: str
    code_literal: str
    name_literal: str
    longitude: float | None = None
    latitude: float | None = None


def build_registry_examples(
    organisation_units: list[OrganisationUnitIn], config: GenerateConfig, *, ig_status: IgStatus
) -> FshArtifact | None:
    """Build `organization/registry-examples.fsh` - one `Usage: #example` per registry profile, or None.

    The registry itself ships as pre-built JSON, which SUSHI loads verbatim and never compiles,
    so `D2Organization` and `D2Location` would otherwise publish no worked example at all. This
    pair fills that gap from the selection's own root unit: real UID, real code, real name, real
    level, so the publisher validates the profiles against data the instance actually holds.

    The exemplar carries what the profiles constrain and nothing more - the level the D2Location
    profile requires 1..1, but no boundary attachment and no attribute values. A base64 GeoJSON
    blob illustrates the encoding rather than the contract, and the registry's JSON instances are
    where a consumer reads a unit in full.

    They live beside the profiles in `organization/`, not in `examples/`: that directory is swept
    by the examples target, whose sync deletes every file it did not produce.

    The exemplar ids (`d2-organization-example`) derive from the profile ids rather than from the
    unit's identity stem: the pair illustrates the profiles, and its `Reference(...)` targets are
    FSH instance names SUSHI resolves, so no stem enters this file under any naming source. The
    unit's DHIS2 id and code appear only as the identifier values they are.
    """
    root = _root_organisation_unit(organisation_units)
    if root is None:
        return None
    names = OrganisationUnitNaming.from_naming(config.naming)
    view = _registry_example_view(root, names)
    return FshArtifact(
        relative_path="organization/registry-examples.fsh",
        kind="instances",
        fsh_name=view.organization_name,
        content=_ENVIRONMENT.get_template("registry-examples.fsh.jinja").render(example=view, ig_status=ig_status),
    )


def _root_organisation_unit(organisation_units: list[OrganisationUnitIn]) -> OrganisationUnitIn | None:
    """The shallowest unit of the selection, ties broken by path - the one every other unit hangs under."""
    if not organisation_units:
        return None
    return min(organisation_units, key=lambda unit: (unit.level, unit.path, unit.uid))


def _registry_example_view(root: OrganisationUnitIn, names: OrganisationUnitNaming) -> _RegistryExampleView:
    """Project the root unit onto the two exemplar instances the registry profiles are illustrated with."""
    label = f"{root.name} ({root.uid})"
    location_description = (
        f"A worked {names.location_profile}: DHIS2 organisation unit {label} as the physical place, "
        f"managed by the {names.organization_profile} of the same unit."
    )
    return _RegistryExampleView(
        organization_profile=names.organization_profile,
        location_profile=names.location_profile,
        organization_name=f"{names.organization_profile}Example",
        location_name=f"{names.location_profile}Example",
        organization_id=f"{names.organization_profile_id}-example",
        location_id=f"{names.location_profile_id}-example",
        organization_title_literal=page_text(f"Example DHIS2 Organization - {label}"),
        location_title_literal=page_text(f"Example DHIS2 Location - {label}"),
        organization_description_literal=page_text(
            f"A worked {names.organization_profile}: DHIS2 organisation unit {label} as the legal entity, "
            "carrying both DHIS2 identifiers and its hierarchy level."
        ),
        location_description_literal=page_text(location_description),
        location_description_element_literal=quote(location_description),
        level_code_system=names.level_code_system,
        level=root.level,
        uid_literal=quote(root.uid),
        code_literal=quote(code_or_uid(root.code, root.uid)),
        name_literal=quote(root.name),
        longitude=root.longitude,
        latitude=root.latitude,
    )


def build_organisation_unit_instances(
    organisation_units: list[OrganisationUnitIn],
    config: GenerateConfig,
    canonical: str,
    *,
    attribute_codes: AttributeCodeIndex,
    stems: StemResolution | None = None,
) -> JsonBuild:
    """Build one `registry/Organization-<stem>.json` and `registry/Location-<stem>.json` per organisation unit.

    `stems` is the org-unit surface's identity resolution; a caller building several targets off
    one fetch passes the run's resolution, and a caller without one gets it resolved here through
    the same `plan_organisation_unit_stems` call. Its fall-back notes surface on this build - the
    registry owns the surface, so the note is raised exactly once per run.
    """
    urls = OrganisationUnitInstanceUrls.from_config(config, canonical)
    extension_url = attribute_value_extension_url(config, canonical)
    build = JsonBuild()
    resolved = (
        stems
        if stems is not None
        else plan_organisation_unit_stems(organisation_unit_stem_subjects(organisation_units), config.naming.source)
    )
    build.notes.extend(resolved.notes)
    selected_uids = {organisation_unit.uid for organisation_unit in organisation_units}
    by_level: defaultdict[int, list[OrganisationUnitIn]] = defaultdict(list)
    for organisation_unit in organisation_units:
        by_level[organisation_unit.level].append(organisation_unit)
    orphaned: list[str] = []
    for level in sorted(by_level):
        for organisation_unit in sorted(by_level[level], key=lambda item: (item.path, item.uid)):
            organization = _build_organization(
                organisation_unit,
                urls,
                selected_uids,
                orphaned,
                config.locales,
                attribute_codes,
                extension_url,
                resolved,
            )
            location = build_location(
                organisation_unit, urls, selected_uids, config.locales, attribute_codes, extension_url, resolved
            )
            stem = resolved.stem_for(organisation_unit.uid)
            build.artifacts.append(_json_artifact(f"Organization-{stem}", organization))
            build.artifacts.append(_json_artifact(f"Location-{stem}", location))
    if orphaned:
        build.notes.append(
            aggregate_generate_note(
                GenerateNoteCategory.SELECTION_GAP,
                f"{len(orphaned)} organisation units have a parent outside the selection; partOf omitted",
                orphaned,
            )
        )
    return build


def _json_artifact(stem: str, resource: Organization | Location) -> JsonArtifact:
    """Serialise one resource as the registry file the predefined-resource loader reads."""
    return JsonArtifact(
        relative_path=f"{REGISTRY_DIRECTORY}/{stem}.json",
        content=f"{resource.model_dump_json(exclude_none=True, by_alias=True, indent=2)}\n",
    )


def _build_organization(
    organisation_unit: OrganisationUnitIn,
    urls: OrganisationUnitInstanceUrls,
    selected_uids: set[str],
    orphaned: list[str],
    locales: list[str],
    attribute_codes: AttributeCodeIndex,
    extension_url: str,
    stems: StemResolution,
) -> Organization:
    """Build the Organization of one unit, noting units whose parent falls outside the selection.

    The identity stem carries the resource id and the `partOf` reference, while the identifier
    slices keep the DHIS2 id and code as data.
    """
    uid = organisation_unit.uid
    parent_uid: str | None = None
    if organisation_unit.parent_uid is not None:
        if organisation_unit.parent_uid in selected_uids:
            parent_uid = organisation_unit.parent_uid
        else:
            orphaned.append(f"{organisation_unit.name} ({uid})")
    alias: list[str] | None = None
    if organisation_unit.short_name is not None and organisation_unit.short_name != organisation_unit.name:
        alias = [flatten_whitespace(organisation_unit.short_name)]
    level = organisation_unit.level
    return Organization(
        id=stems.stem_for(uid),
        meta=Meta(profile=[urls.organization_profile]),
        extension=attribute_value_extensions(organisation_unit.attribute_values, attribute_codes, extension_url)
        or None,
        identifier=[
            Identifier(system=urls.identifier_system, value=uid),
            Identifier(system=urls.code_identifier_system, value=code_or_uid(organisation_unit.code, uid)),
            *attribute_value_identifiers(
                organisation_unit.attribute_values, attribute_codes, urls.identifier_system_base
            ),
        ],
        name=flatten_whitespace(organisation_unit.name),
        name_element=translated_element(name_translations(organisation_unit.translations, locales)),
        alias=alias,
        type=[
            CodeableConcept(
                coding=[
                    Coding(system=urls.level_code_system, code=f"level-{level}", display=f"Level {level}"),
                ]
            )
        ],
        partOf=Reference(reference=f"Organization/{stems.stem_for(parent_uid)}") if parent_uid is not None else None,
        telecom=_telecom(organisation_unit) or None,
        contact=_contact(organisation_unit),
        active=not organisation_unit.closed,
    )


def _telecom(organisation_unit: OrganisationUnitIn) -> list[ContactPoint]:
    """The unit's DHIS2 phone number then email as contact points, either of which may be absent."""
    points: list[ContactPoint] = []
    if organisation_unit.phone_number is not None:
        points.append(ContactPoint(system="phone", value=flatten_whitespace(organisation_unit.phone_number)))
    if organisation_unit.email is not None:
        points.append(ContactPoint(system="email", value=flatten_whitespace(organisation_unit.email)))
    return points


def _contact(organisation_unit: OrganisationUnitIn) -> list[OrganizationContact] | None:
    """The unit's DHIS2 contact person as a contact party, or None when the unit names nobody."""
    if organisation_unit.contact_person is None:
        return None
    return [OrganizationContact(name=HumanName(text=flatten_whitespace(organisation_unit.contact_person)))]
