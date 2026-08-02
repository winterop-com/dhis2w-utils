"""FSH emission for the organisation-unit profiles and the per-level Organization/Location instance files.

Each organisation unit becomes an Organization instance with DHIS2 UID/code
identifier slices plus a Location instance - the FHIR pair of legal entity
and physical place - with `partOf` mirroring the hierarchy on both sides.

Artifact names honour the configurable `[generate.naming]` tokens. The two
profile names always carry a token (falling back to `D2` when the prefix is
empty) because FSH cannot name a profile identically to its parent core
resource.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.i18n import TRANSLATION_EXTENSION_URL, TranslationIn, name_translations
from dhis2w_fhir.names import code_or_uid, quote
from dhis2w_fhir.notes import aggregate_note
from dhis2w_fhir.resources.organisation_units.location import (
    BOUNDARY_EXTENSION_URL,
    LocationInstance,
    build_location_instance,
)
from dhis2w_fhir.resources.organisation_units.naming import OrganisationUnitNaming
from dhis2w_fhir.resources.organisation_units.schemas import OrganisationUnitIn
from dhis2w_fhir.status import IgStatus, experimental_for_status
from dhis2w_fhir.writer import FshArtifact, FshBuild

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig

_ENVIRONMENT = Environment(
    loader=PackageLoader("dhis2w_fhir.resources.organisation_units", "templates"),
    autoescape=select_autoescape(default=False),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


class OrganizationInstance(BaseModel):
    """Everything the FSH template needs for one Organization instance, every conditional already resolved."""

    model_config = ConfigDict(frozen=True)

    uid: str
    profile: str
    title_literal: str
    description_literal: str
    name_literal: str
    name_translations: list[TranslationIn] = Field(default_factory=list)
    identifier_code_literal: str
    alias_literal: str | None = None
    level: int
    level_code_system: str
    closed: bool = False
    parent_uid: str | None = None
    phone_literal: str | None = None
    email_literal: str | None = None
    contact_literal: str | None = None


class OrganisationUnitInstancePair(BaseModel):
    """One organisation unit as the Organization/Location pair a per-level file renders."""

    model_config = ConfigDict(frozen=True)

    organization: OrganizationInstance
    location: LocationInstance


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


def build_organisation_unit_instances(organisation_units: list[OrganisationUnitIn], config: GenerateConfig) -> FshBuild:
    """Build one `organization/org-units-level-<n>.fsh` per level, each unit an Organization (+ Location)."""
    names = OrganisationUnitNaming.from_naming(config.naming)
    build = FshBuild()
    selected_uids = {organisation_unit.uid for organisation_unit in organisation_units}
    by_level: defaultdict[int, list[OrganisationUnitIn]] = defaultdict(list)
    for organisation_unit in organisation_units:
        by_level[organisation_unit.level].append(organisation_unit)
    orphaned: list[str] = []
    template = _ENVIRONMENT.get_template("org-units-level.fsh.jinja")
    for level in sorted(by_level):
        pairs = [
            OrganisationUnitInstancePair(
                organization=_build_organization_instance(
                    organisation_unit, names, selected_uids, orphaned, config.locales
                ),
                location=build_location_instance(organisation_unit, names, selected_uids, config.locales),
            )
            for organisation_unit in sorted(by_level[level], key=lambda item: (item.path, item.uid))
        ]
        build.artifacts.append(
            FshArtifact(
                relative_path=f"organization/org-units-level-{level}.fsh",
                kind="instances",
                fsh_name=f"OrgUnitsLevel{level}",
                content=template.render(
                    pairs=pairs,
                    boundary_extension_url=BOUNDARY_EXTENSION_URL,
                    translation_extension_url=TRANSLATION_EXTENSION_URL,
                ),
            )
        )
    if orphaned:
        build.notes.append(
            aggregate_note(
                f"{len(orphaned)} organisation units have a parent outside the selection; partOf omitted", orphaned
            )
        )
    return build


def _build_organization_instance(
    organisation_unit: OrganisationUnitIn,
    names: OrganisationUnitNaming,
    selected_uids: set[str],
    orphaned: list[str],
    locales: list[str],
) -> OrganizationInstance:
    """Build the Organization view, noting units whose parent falls outside the selection."""
    parent_uid: str | None = None
    if organisation_unit.parent_uid is not None:
        if organisation_unit.parent_uid in selected_uids:
            parent_uid = organisation_unit.parent_uid
        else:
            orphaned.append(f"{organisation_unit.name} ({organisation_unit.uid})")
    alias_literal: str | None = None
    if organisation_unit.short_name is not None and organisation_unit.short_name != organisation_unit.name:
        alias_literal = quote(organisation_unit.short_name)
    description = (
        f"DHIS2 organisation unit {organisation_unit.name} ({organisation_unit.uid}), level {organisation_unit.level}."
    )
    return OrganizationInstance(
        uid=organisation_unit.uid,
        profile=names.organization_profile,
        title_literal=quote(f"Organization - {organisation_unit.name}"),
        description_literal=quote(description),
        name_literal=quote(organisation_unit.name),
        name_translations=name_translations(organisation_unit.translations, locales),
        identifier_code_literal=quote(code_or_uid(organisation_unit.code, organisation_unit.uid)),
        alias_literal=alias_literal,
        level=organisation_unit.level,
        level_code_system=names.level_code_system,
        closed=organisation_unit.closed,
        parent_uid=parent_uid,
        phone_literal=quote(organisation_unit.phone_number) if organisation_unit.phone_number is not None else None,
        email_literal=quote(organisation_unit.email) if organisation_unit.email is not None else None,
        contact_literal=quote(organisation_unit.contact_person)
        if organisation_unit.contact_person is not None
        else None,
    )
