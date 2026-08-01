"""Golden tests for organisation-unit profile, terminology, and instance FSH emission."""

from dhis2w_fhir.models import GenerateConfig, NamingConfig, OrgUnitInput
from dhis2w_fhir.organization import (
    build_org_unit_instances,
    build_org_unit_level_terminology,
    build_org_unit_profiles,
    build_org_unit_terminology,
)

_ROOT = OrgUnitInput(uid="ImspTQPwCqd", name="Sierra Leone", level=1, path="/ImspTQPwCqd", code="SL")
_DISTRICT = OrgUnitInput(
    uid="O6uvpzGd5pu",
    name="Bo",
    short_name="Bo District",
    level=2,
    path="/ImspTQPwCqd/O6uvpzGd5pu",
    parent_uid="ImspTQPwCqd",
    latitude=7.9647,
    longitude=-11.7383,
    email="bo@example.org",
    phone_number="+232 76 000000",
    contact_person="A. Person",
)
_ORPHAN = OrgUnitInput(
    uid="YuQRtpLP10I",
    name="Badjia",
    level=3,
    path="/ImspTQPwCqd/O6uvpzGd5pu/YuQRtpLP10I",
    parent_uid="MissingUid00",
)
_CONFIG = GenerateConfig()

_EXPECTED_DISTRICT = """Instance: OrganizationO6uvpzGd5pu
InstanceOf: D2Organization
Title: "Organization - Bo"
Description: "DHIS2 organisation unit Bo (O6uvpzGd5pu), level 2."
Usage: #example
* identifier[dhis2uid].system = $DHIS2-OU
* identifier[dhis2uid].type = $V2-0203#RI
* identifier[dhis2uid].value = "O6uvpzGd5pu"
* name = "Bo"
* alias = "Bo District"
* type = D2OULevelCS#level-2 "Level 2"
* partOf = Reference(OrganizationImspTQPwCqd)
* telecom[+].system = #phone
* telecom[=].value = "+232 76 000000"
* telecom[+].system = #email
* telecom[=].value = "bo@example.org"
* contact[+].name.text = "A. Person"
* active = true

Instance: LocationO6uvpzGd5pu
InstanceOf: D2Location
Title: "Location - Bo"
Usage: #example
* name = "Bo"
* status = #active
* position.latitude = 7.9647
* position.longitude = -11.7383
* managingOrganization = Reference(OrganizationO6uvpzGd5pu)
"""


def test_profiles_artifact() -> None:
    """The static profiles file defines DHIS2Organization and DHIS2Location."""
    artifact = build_org_unit_profiles(_CONFIG)
    assert artifact.relative_path == "organization/profiles.fsh"
    assert "Profile: D2Organization" in artifact.content
    assert "* identifier contains dhis2uid 1..1 and dhis2code 0..1" in artifact.content
    assert "* partOf only Reference(D2Organization)" in artifact.content
    assert "Profile: D2Location" in artifact.content
    assert "* managingOrganization only Reference(D2Organization)" in artifact.content


def test_level_terminology_covers_observed_levels() -> None:
    """The level CodeSystem lists each observed level once, sorted."""
    artifact = build_org_unit_level_terminology([2, 1, 2, 3], _CONFIG)
    assert artifact.content.count("* #level-") == 3
    assert '* #level-1 "Level 1"' in artifact.content
    assert "ValueSet: D2OULevelVS" in artifact.content


def test_instances_golden_per_level_files() -> None:
    """Instances land in per-level files; a Point-geometry unit also gets a Location."""
    build = build_org_unit_instances([_DISTRICT, _ROOT], _CONFIG)
    assert [artifact.relative_path for artifact in build.artifacts] == [
        "organization/org-units-level-1.fsh",
        "organization/org-units-level-2.fsh",
    ]
    level_two = build.artifacts[1]
    assert level_two.content == _EXPECTED_DISTRICT
    assert build.notes == []


def test_root_has_no_part_of_and_code_slice() -> None:
    """The root instance omits partOf but carries the dhis2code identifier slice."""
    build = build_org_unit_instances([_ROOT], _CONFIG)
    content = build.artifacts[0].content
    assert "partOf" not in content
    assert "* identifier[dhis2code].system = $DHIS2-OU-CODE" in content
    assert '* identifier[dhis2code].value = "SL"' in content


def test_out_of_selection_parent_is_noted() -> None:
    """A parent outside the selection omits partOf and records a note."""
    build = build_org_unit_instances([_ORPHAN], _CONFIG)
    assert "partOf" not in build.artifacts[0].content
    assert any("outside" in note and "MissingUid00" in note for note in build.notes)


def test_org_unit_terminology_properties() -> None:
    """The optional CodeSystem carries level/parent/dhis2-code concept properties."""
    artifact = build_org_unit_terminology([_ROOT, _DISTRICT], _CONFIG)
    content = artifact.content
    assert "CodeSystem: D2OUCS" in content
    assert "* #O6uvpzGd5pu ^property[+].code = #level" in content
    assert "* #O6uvpzGd5pu ^property[=].valueInteger = 2" in content
    assert "* #O6uvpzGd5pu ^property[+].code = #parent" in content
    assert "* #O6uvpzGd5pu ^property[=].valueCode = #ImspTQPwCqd" in content
    assert "* #ImspTQPwCqd ^property[+].code = #dhis2-code" in content
    assert "ValueSet: D2OUVS" in content


def test_naming_tokens_are_configurable() -> None:
    """Custom naming tokens flow into names and ids (e.g. org_unit "OrgUnit" -> D2OrgUnitLevelCS)."""
    config = GenerateConfig(naming=NamingConfig(org_unit="OrgUnit"))
    levels = build_org_unit_level_terminology([1], config)
    assert "CodeSystem: D2OrgUnitLevelCS" in levels.content
    assert "Id: d2-org-unit-level-cs" in levels.content
    instance = build_org_unit_instances([_ROOT], config).artifacts[0].content
    assert "* type = D2OrgUnitLevelCS#level-1" in instance


def test_empty_prefix_keeps_profile_token() -> None:
    """With an empty prefix, terminology goes bare but profiles keep the D2 token (cannot shadow Organization)."""
    config = GenerateConfig(naming=NamingConfig(prefix=""))
    profiles = build_org_unit_profiles(config)
    assert "Profile: D2Organization" in profiles.content
    levels = build_org_unit_level_terminology([1], config)
    assert "CodeSystem: OULevelCS" in levels.content
    assert "Id: ou-level-cs" in levels.content
