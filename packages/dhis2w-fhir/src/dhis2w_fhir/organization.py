"""FSH emission for DHIS2 organisation units: profiles, level terminology, and per-level instances.

Each organisation unit becomes an Organization instance with DHIS2 UID/code
identifier slices and a `partOf` reference to its parent; units whose geometry
is a GeoJSON Point additionally get a Location instance. An optional toggle
also emits the whole selection as a CodeSystem/ValueSet with `level`,
`parent`, and `dhis2-code` concept properties.

Artifact names honour the configurable `[generate.naming]` tokens. The two
profile names always carry a token (falling back to `D2` when the prefix is
empty) because FSH cannot name a profile identically to its parent core
resource.
"""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.models import FshArtifact, FshBuild, GenerateConfig, NamingConfig, OrgUnitInput
from dhis2w_fhir.names import join_id_tokens, quote

_PROFILE_FALLBACK_PREFIX = "D2"


class OrgUnitNaming(BaseModel):
    """Derived FSH names and ids for org-unit artifacts under the configurable naming tokens."""

    model_config = ConfigDict(frozen=True)

    naming: NamingConfig

    @property
    def profile_prefix(self) -> str:
        """Token for profile names - never empty, a profile cannot shadow its parent resource name."""
        return self.naming.prefix or _PROFILE_FALLBACK_PREFIX

    @property
    def organization_profile(self) -> str:
        """FSH name of the Organization profile."""
        return f"{self.profile_prefix}Organization"

    @property
    def location_profile(self) -> str:
        """FSH name of the Location profile."""
        return f"{self.profile_prefix}Location"

    @property
    def level_code_system(self) -> str:
        """FSH name of the org-unit-level CodeSystem (e.g. `D2OrgUnitLevelCS`, `D2OULevelCS`)."""
        return f"{self.naming.prefix}{self.naming.org_unit}LevelCS"

    @property
    def level_value_set(self) -> str:
        """FSH name of the org-unit-level ValueSet."""
        return f"{self.naming.prefix}{self.naming.org_unit}LevelVS"

    @property
    def org_unit_code_system(self) -> str:
        """FSH name of the optional whole-selection CodeSystem."""
        return f"{self.naming.prefix}{self.naming.org_unit}CS"

    @property
    def org_unit_value_set(self) -> str:
        """FSH name of the optional whole-selection ValueSet."""
        return f"{self.naming.prefix}{self.naming.org_unit}VS"

    @property
    def organization_profile_id(self) -> str:
        """FHIR id of the Organization profile (e.g. `d2-organization`)."""
        return join_id_tokens(self.profile_prefix, "organization")

    @property
    def location_profile_id(self) -> str:
        """FHIR id of the Location profile (e.g. `d2-location`)."""
        return join_id_tokens(self.profile_prefix, "location")

    def terminology_id(self, *suffix_tokens: str) -> str:
        """FHIR id for an org-unit terminology artifact (e.g. `d2-org-unit-level-cs`, `d2-ou-cs`)."""
        return join_id_tokens(self.naming.prefix, self.naming.org_unit, *suffix_tokens)


def _naming(config: GenerateConfig) -> OrgUnitNaming:
    """Build the naming view for a generate config."""
    return OrgUnitNaming(naming=config.naming)


def build_org_unit_profiles(config: GenerateConfig) -> FshArtifact:
    """Build the static `organization/profiles.fsh` defining the Organization and Location profiles."""
    names = _naming(config)
    lines = [
        f"Profile: {names.organization_profile}",
        "Parent: Organization",
        f"Id: {names.organization_profile_id}",
        'Title: "DHIS2 Organization"',
        'Description: "An organisation unit imported from DHIS2."',
        "* identifier ^slicing.discriminator.type = #value",
        '* identifier ^slicing.discriminator.path = "system"',
        "* identifier ^slicing.rules = #open",
        "* identifier contains dhis2uid 1..1 and dhis2code 0..1",
        "* identifier[dhis2uid].system = $DHIS2-OU",
        "* identifier[dhis2code].system = $DHIS2-OU-CODE",
        "* active 1..1",
        "* type 1..*",
        f"* type from {names.level_value_set} (required)",
        "* name 1..1",
        f"* partOf only Reference({names.organization_profile})",
        "",
        f"Profile: {names.location_profile}",
        "Parent: Location",
        f"Id: {names.location_profile_id}",
        'Title: "DHIS2 Location"',
        'Description: "The physical position of a DHIS2 organisation unit with Point geometry."',
        "* name 1..1",
        "* status 1..1",
        "* position 1..1 MS",
        "* managingOrganization 1..1",
        f"* managingOrganization only Reference({names.organization_profile})",
    ]
    return FshArtifact(
        relative_path="organization/profiles.fsh",
        kind="profile",
        fsh_name=names.organization_profile,
        content="\n".join(lines) + "\n",
    )


def build_org_unit_level_terminology(levels: list[int], config: GenerateConfig) -> FshArtifact:
    """Build `organization/org-unit-levels.fsh` covering the levels observed in the selection."""
    names = _naming(config)
    lines = [
        f"CodeSystem: {names.level_code_system}",
        f"Id: {names.terminology_id('level', 'cs')}",
        'Title: "DHIS2 Organisation Unit Levels"',
        'Description: "Hierarchy levels of the DHIS2 organisation unit tree."',
        "* ^status = #active",
        "* ^content = #complete",
        "* ^caseSensitive = true",
    ]
    lines.extend(f'* #level-{level} "Level {level}"' for level in sorted(set(levels)))
    lines.extend(
        [
            "",
            f"ValueSet: {names.level_value_set}",
            f"Id: {names.terminology_id('level', 'vs')}",
            'Title: "DHIS2 Organisation Unit Levels"',
            'Description: "Hierarchy levels of the DHIS2 organisation unit tree."',
            "* ^status = #active",
            f"* include codes from system {names.level_code_system}",
        ]
    )
    return FshArtifact(
        relative_path="organization/org-unit-levels.fsh",
        kind="terminology-pair",
        fsh_name=names.level_code_system,
        content="\n".join(lines) + "\n",
    )


def build_org_unit_instances(org_units: list[OrgUnitInput], config: GenerateConfig) -> FshBuild:
    """Build one `organization/org-units-level-<n>.fsh` per level, each unit an Organization (+ Location)."""
    names = _naming(config)
    build = FshBuild()
    selected_uids = {org_unit.uid for org_unit in org_units}
    by_level: defaultdict[int, list[OrgUnitInput]] = defaultdict(list)
    for org_unit in org_units:
        by_level[org_unit.level].append(org_unit)
    for level in sorted(by_level):
        sections: list[str] = []
        for org_unit in sorted(by_level[level], key=lambda item: (item.path, item.uid)):
            sections.append(_organization_instance(org_unit, names, selected_uids, build.notes))
            if org_unit.latitude is not None and org_unit.longitude is not None:
                sections.append(_location_instance(org_unit, names))
        build.artifacts.append(
            FshArtifact(
                relative_path=f"organization/org-units-level-{level}.fsh",
                kind="instances",
                fsh_name=f"OrgUnitsLevel{level}",
                content="\n".join(sections),
            )
        )
    return build


def _organization_instance(
    org_unit: OrgUnitInput, names: OrgUnitNaming, selected_uids: set[str], notes: list[str]
) -> str:
    """Render one Organization instance for an organisation unit."""
    lines = [
        f"Instance: Organization{org_unit.uid}",
        f"InstanceOf: {names.organization_profile}",
        f"Title: {quote(f'Organization - {org_unit.name}')}",
        f"Description: {quote(f'DHIS2 organisation unit {org_unit.name} ({org_unit.uid}), level {org_unit.level}.')}",
        "Usage: #example",
        "* identifier[dhis2uid].system = $DHIS2-OU",
        "* identifier[dhis2uid].type = $V2-0203#RI",
        f'* identifier[dhis2uid].value = "{org_unit.uid}"',
    ]
    if org_unit.code is not None:
        lines.extend(
            [
                "* identifier[dhis2code].system = $DHIS2-OU-CODE",
                "* identifier[dhis2code].type = $V2-0203#XX",
                f"* identifier[dhis2code].value = {quote(org_unit.code)}",
            ]
        )
    lines.append(f"* name = {quote(org_unit.name)}")
    if org_unit.short_name is not None and org_unit.short_name != org_unit.name:
        lines.append(f"* alias = {quote(org_unit.short_name)}")
    lines.append(f'* type = {names.level_code_system}#level-{org_unit.level} "Level {org_unit.level}"')
    if org_unit.parent_uid is not None:
        if org_unit.parent_uid in selected_uids:
            lines.append(f"* partOf = Reference(Organization{org_unit.parent_uid})")
        else:
            notes.append(
                f"org unit {org_unit.uid} ({org_unit.name}): parent {org_unit.parent_uid} is outside "
                "the selection; partOf omitted"
            )
    if org_unit.phone_number is not None:
        lines.extend(["* telecom[+].system = #phone", f"* telecom[=].value = {quote(org_unit.phone_number)}"])
    if org_unit.email is not None:
        lines.extend(["* telecom[+].system = #email", f"* telecom[=].value = {quote(org_unit.email)}"])
    if org_unit.contact_person is not None:
        lines.append(f"* contact[+].name.text = {quote(org_unit.contact_person)}")
    lines.append("* active = true")
    return "\n".join(lines) + "\n"


def _location_instance(org_unit: OrgUnitInput, names: OrgUnitNaming) -> str:
    """Render the Location instance for an organisation unit with Point geometry."""
    lines = [
        f"Instance: Location{org_unit.uid}",
        f"InstanceOf: {names.location_profile}",
        f"Title: {quote(f'Location - {org_unit.name}')}",
        "Usage: #example",
        f"* name = {quote(org_unit.name)}",
        "* status = #active",
        f"* position.latitude = {org_unit.latitude}",
        f"* position.longitude = {org_unit.longitude}",
        f"* managingOrganization = Reference(Organization{org_unit.uid})",
    ]
    return "\n".join(lines) + "\n"


def build_org_unit_terminology(org_units: list[OrgUnitInput], config: GenerateConfig) -> FshArtifact:
    """Build the optional `organization/org-units-terminology.fsh` CodeSystem/ValueSet over the selection."""
    names = _naming(config)
    lines = [
        f"CodeSystem: {names.org_unit_code_system}",
        f"Id: {names.terminology_id('cs')}",
        'Title: "DHIS2 Organisation Units"',
        'Description: "DHIS2 organisation units. Concept codes are DHIS2 organisation unit UIDs."',
        "* ^status = #active",
        "* ^content = #complete",
        "* ^caseSensitive = true",
        "* ^property[+].code = #level",
        '* ^property[=].description = "DHIS2 organisation unit hierarchy level."',
        "* ^property[=].type = #integer",
        "* ^property[+].code = #parent",
        '* ^property[=].description = "Parent organisation unit UID."',
        "* ^property[=].type = #code",
        "* ^property[+].code = #dhis2-code",
        '* ^property[=].description = "DHIS2 organisation unit code."',
        "* ^property[=].type = #string",
    ]
    for org_unit in sorted(org_units, key=lambda item: (item.path, item.uid)):
        lines.append(f"* #{org_unit.uid} {quote(org_unit.name)}")
        lines.extend(
            [
                f"* #{org_unit.uid} ^property[+].code = #level",
                f"* #{org_unit.uid} ^property[=].valueInteger = {org_unit.level}",
            ]
        )
        if org_unit.parent_uid is not None:
            lines.extend(
                [
                    f"* #{org_unit.uid} ^property[+].code = #parent",
                    f"* #{org_unit.uid} ^property[=].valueCode = #{org_unit.parent_uid}",
                ]
            )
        if org_unit.code is not None:
            lines.extend(
                [
                    f"* #{org_unit.uid} ^property[+].code = #dhis2-code",
                    f"* #{org_unit.uid} ^property[=].valueString = {quote(org_unit.code)}",
                ]
            )
    lines.extend(
        [
            "",
            f"ValueSet: {names.org_unit_value_set}",
            f"Id: {names.terminology_id('vs')}",
            'Title: "DHIS2 Organisation Units"',
            'Description: "All DHIS2 organisation units in the generated selection."',
            "* ^status = #active",
            f"* include codes from system {names.org_unit_code_system}",
        ]
    )
    return FshArtifact(
        relative_path="organization/org-units-terminology.fsh",
        kind="terminology-pair",
        fsh_name=names.org_unit_code_system,
        content="\n".join(lines) + "\n",
    )
