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

from dhis2w_fhir.i18n import name_translations, translated_name_element
from dhis2w_fhir.names import code_or_uid, flatten_whitespace
from dhis2w_fhir.notes import aggregate_note
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
    from dhis2w_fhir.config import GenerateConfig
    from dhis2w_fhir.resources.organisation_units.schemas import OrganisationUnitIn

#: The `ig/input/resources/` subdirectory the registry owns outright - one JSON file per resource.
REGISTRY_DIRECTORY = "registry"

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
            ig_status=ig_status,
            experimental=experimental_for_status(ig_status),
        ),
    )


def build_organisation_unit_instances(
    organisation_units: list[OrganisationUnitIn], config: GenerateConfig, canonical: str
) -> JsonBuild:
    """Build one `registry/Organization-<uid>.json` and `registry/Location-<uid>.json` per organisation unit."""
    urls = OrganisationUnitInstanceUrls.from_config(config, canonical)
    build = JsonBuild()
    selected_uids = {organisation_unit.uid for organisation_unit in organisation_units}
    by_level: defaultdict[int, list[OrganisationUnitIn]] = defaultdict(list)
    for organisation_unit in organisation_units:
        by_level[organisation_unit.level].append(organisation_unit)
    orphaned: list[str] = []
    for level in sorted(by_level):
        for organisation_unit in sorted(by_level[level], key=lambda item: (item.path, item.uid)):
            organization = _build_organization(organisation_unit, urls, selected_uids, orphaned, config.locales)
            location = build_location(organisation_unit, urls, selected_uids, config.locales)
            build.artifacts.append(_json_artifact(f"Organization-{organisation_unit.uid}", organization))
            build.artifacts.append(_json_artifact(f"Location-{organisation_unit.uid}", location))
    if orphaned:
        build.notes.append(
            aggregate_note(
                f"{len(orphaned)} organisation units have a parent outside the selection; partOf omitted", orphaned
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
) -> Organization:
    """Build the Organization of one unit, noting units whose parent falls outside the selection."""
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
        id=uid,
        meta=Meta(profile=[urls.organization_profile]),
        identifier=[
            Identifier(system=urls.identifier_system, value=uid),
            Identifier(system=urls.code_identifier_system, value=code_or_uid(organisation_unit.code, uid)),
        ],
        name=flatten_whitespace(organisation_unit.name),
        name_element=translated_name_element(name_translations(organisation_unit.translations, locales)),
        alias=alias,
        type=[
            CodeableConcept(
                coding=[
                    Coding(system=urls.level_code_system, code=f"level-{level}", display=f"Level {level}"),
                ]
            )
        ],
        partOf=Reference(reference=f"Organization/{parent_uid}") if parent_uid is not None else None,
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
