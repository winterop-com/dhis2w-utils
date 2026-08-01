"""Golden tests for organisation-unit profile, terminology, and instance FSH emission."""

import base64

from dhis2w_fhir.config import GenerateConfig, NamingConfig
from dhis2w_fhir.resources.organisation_units import (
    build_organisation_unit_instances,
    build_organisation_unit_level_terminology,
    build_organisation_unit_profiles,
    build_organisation_unit_terminology,
)
from dhis2w_fhir.resources.organisation_units.schemas import OrganisationUnitIn

_ROOT = OrganisationUnitIn(uid="ImspTQPwCqd", name="Sierra Leone", level=1, path="/ImspTQPwCqd", code="SL")
_DISTRICT = OrganisationUnitIn(
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
_ORPHAN = OrganisationUnitIn(
    uid="YuQRtpLP10I",
    name="Badjia",
    level=3,
    path="/ImspTQPwCqd/O6uvpzGd5pu/YuQRtpLP10I",
    parent_uid="MissingUid00",
)
_CONFIG = GenerateConfig()

_EXPECTED_ROOT_LOCATION = """Instance: LocationImspTQPwCqd
InstanceOf: D2Location
Title: "Location - Sierra Leone"
Description: "DHIS2 organisation unit Sierra Leone (ImspTQPwCqd), level 1 - physical location."
Usage: #definition
* identifier[dhis2uid].system = $DHIS2-OU
* identifier[dhis2uid].value = "ImspTQPwCqd"
* identifier[dhis2code].system = $DHIS2-OU-CODE
* identifier[dhis2code].value = "SL"
* name = "Sierra Leone"
* status = #active
* managingOrganization = Reference(OrganizationImspTQPwCqd)
"""

_EXPECTED_DISTRICT = """Instance: OrganizationO6uvpzGd5pu
InstanceOf: D2Organization
Title: "Organization - Bo"
Description: "DHIS2 organisation unit Bo (O6uvpzGd5pu), level 2."
Usage: #definition
* identifier[dhis2uid].system = $DHIS2-OU
* identifier[dhis2uid].value = "O6uvpzGd5pu"
* identifier[dhis2code].system = $DHIS2-OU-CODE
* identifier[dhis2code].value = "O6uvpzGd5pu"
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
Description: "DHIS2 organisation unit Bo (O6uvpzGd5pu), level 2 - physical location."
Usage: #definition
* identifier[dhis2uid].system = $DHIS2-OU
* identifier[dhis2uid].value = "O6uvpzGd5pu"
* identifier[dhis2code].system = $DHIS2-OU-CODE
* identifier[dhis2code].value = "O6uvpzGd5pu"
* name = "Bo"
* status = #active
* position.latitude = 7.9647
* position.longitude = -11.7383
* managingOrganization = Reference(OrganizationO6uvpzGd5pu)
* partOf = Reference(LocationImspTQPwCqd)
"""


def test_profiles_artifact() -> None:
    """Both profiles are active, slice the two DHIS2 identifiers, and bind level extensibly."""
    artifact = build_organisation_unit_profiles(_CONFIG)
    assert artifact.relative_path == "organization/profiles.fsh"
    assert "Profile: D2Organization" in artifact.content
    assert artifact.content.count("* ^status = #active") == 2
    assert artifact.content.count("* identifier contains dhis2uid 1..1 and dhis2code 1..1") == 2
    assert artifact.content.count('* identifier ^slicing.discriminator.path = "system"') == 2
    assert "* type from D2OULevelVS (extensible)" in artifact.content
    assert "* partOf only Reference(D2Organization)" in artifact.content
    assert "Profile: D2Location" in artifact.content
    assert "* managingOrganization only Reference(D2Organization)" in artifact.content
    assert "* position 0..1 MS" in artifact.content
    assert "* partOf only Reference(D2Location)" in artifact.content


def test_level_terminology_covers_observed_levels() -> None:
    """The level CodeSystem lists each observed level once, sorted."""
    artifact = build_organisation_unit_level_terminology([2, 1, 2, 3], _CONFIG)
    assert artifact.content.count("* #level-") == 3
    assert '* #level-1 "Level 1"' in artifact.content
    assert "ValueSet: D2OULevelVS" in artifact.content


def test_instances_golden_per_level_files() -> None:
    """Instances land in per-level files; every unit gets a Location, position only with geometry."""
    build = build_organisation_unit_instances([_DISTRICT, _ROOT], _CONFIG)
    assert [artifact.relative_path for artifact in build.artifacts] == [
        "organization/org-units-level-1.fsh",
        "organization/org-units-level-2.fsh",
    ]
    assert _EXPECTED_ROOT_LOCATION in build.artifacts[0].content
    level_two = build.artifacts[1]
    assert level_two.content == _EXPECTED_DISTRICT
    assert build.notes == []


def test_root_has_no_part_of_and_code_slice() -> None:
    """The root instance omits partOf but carries the dhis2code identifier slice on both resources."""
    build = build_organisation_unit_instances([_ROOT], _CONFIG)
    content = build.artifacts[0].content
    assert "partOf" not in content
    assert content.count("* identifier[dhis2code].system = $DHIS2-OU-CODE") == 2
    assert content.count('* identifier[dhis2code].value = "SL"') == 2


def test_code_identifier_falls_back_to_the_uid() -> None:
    """A unit without a usable DHIS2 code still carries the code slice, repeating the UID."""
    unassigned = OrganisationUnitIn(uid="Ncd1aaaaaaa", name="Uncoded", level=1, path="/Ncd1aaaaaaa")
    unusable = OrganisationUnitIn(uid="Bad1aaaaaaa", name="Spaced", level=1, path="/Bad1aaaaaaa", code=" not a code ")
    content = build_organisation_unit_instances([unassigned, unusable], _CONFIG).artifacts[0].content
    assert content.count('* identifier[dhis2code].value = "Ncd1aaaaaaa"') == 2
    assert content.count('* identifier[dhis2code].value = "Bad1aaaaaaa"') == 2


def test_closed_unit_is_inactive() -> None:
    """A unit whose closedDate has passed emits an inactive Organization and Location."""
    closed = OrganisationUnitIn(uid="Cls1aaaaaaa", name="Closed", level=1, path="/Cls1aaaaaaa", closed=True)
    content = build_organisation_unit_instances([closed], _CONFIG).artifacts[0].content
    assert "* active = false" in content
    assert "* status = #inactive" in content


def test_out_of_selection_parent_is_noted() -> None:
    """A parent outside the selection omits partOf and lands in one aggregated note."""
    build = build_organisation_unit_instances([_ORPHAN], _CONFIG)
    assert "partOf" not in build.artifacts[0].content
    assert len(build.notes) == 1
    assert "outside the selection" in build.notes[0]
    assert "Badjia (YuQRtpLP10I)" in build.notes[0]


def test_boundary_extension_emitted() -> None:
    """A unit with boundary GeoJSON gets the location-boundary-geojson attachment on its Location."""
    unit = OrganisationUnitIn(
        uid="Bnd1aaaaaaa",
        name="Bounded",
        level=2,
        path="/ImspTQPwCqd/Bnd1aaaaaaa",
        latitude=8.0,
        longitude=-11.0,
        boundary_geojson='{"coordinates":[[[0,0],[1,0],[1,1],[0,0]]],"type":"Polygon"}',
    )
    build = build_organisation_unit_instances([unit], _CONFIG)
    content = build.artifacts[0].content
    assert '* extension[+].url = "http://hl7.org/fhir/StructureDefinition/location-boundary-geojson"' in content
    assert "* extension[=].valueAttachment.contentType = #application/geo+json" in content
    assert "* extension[=].valueAttachment.data =" in content


def test_boundary_extension_emitted_for_point_geometry() -> None:
    """The extension is unconditional: a Point unit carries its geometry as an attachment too."""
    unit = OrganisationUnitIn(
        uid="Pnt1aaaaaaa",
        name="Pointy",
        level=2,
        path="/ImspTQPwCqd/Pnt1aaaaaaa",
        latitude=7.9647,
        longitude=-11.7383,
        boundary_geojson='{"coordinates":[-11.7383,7.9647],"type":"Point"}',
    )
    content = build_organisation_unit_instances([unit], _CONFIG).artifacts[0].content
    encoded = base64.b64encode(b'{"coordinates":[-11.7383,7.9647],"type":"Point"}').decode("ascii")
    assert '* extension[+].url = "http://hl7.org/fhir/StructureDefinition/location-boundary-geojson"' in content
    assert "* extension[=].valueAttachment.contentType = #application/geo+json" in content
    assert f'* extension[=].valueAttachment.data = "{encoded}"' in content
    assert '* extension[=].valueAttachment.title = "Pointy (Pnt1aaaaaaa)"' in content
    assert "* extension[=].valueAttachment.size = 48" in content
    assert "* position.latitude = 7.9647" in content


def test_organisation_unit_terminology_properties() -> None:
    """The optional CodeSystem carries level/parent/dhis2-code concept properties."""
    artifact = build_organisation_unit_terminology([_ROOT, _DISTRICT], _CONFIG)
    content = artifact.content
    assert "CodeSystem: D2OUCS" in content
    assert "* #O6uvpzGd5pu ^property[+].code = #level" in content
    assert "* #O6uvpzGd5pu ^property[=].valueInteger = 2" in content
    assert "* #O6uvpzGd5pu ^property[+].code = #parent" in content
    assert "* #O6uvpzGd5pu ^property[=].valueCode = #ImspTQPwCqd" in content
    assert "* #ImspTQPwCqd ^property[+].code = #dhis2-code" in content
    assert "ValueSet: D2OUVS" in content


def test_naming_tokens_are_configurable() -> None:
    """Custom naming tokens flow into names and ids (e.g. organisation_unit "OrgUnit" -> D2OrgUnitLevelCS)."""
    config = GenerateConfig(naming=NamingConfig(organisation_unit="OrgUnit"))
    levels = build_organisation_unit_level_terminology([1], config)
    assert "CodeSystem: D2OrgUnitLevelCS" in levels.content
    assert "Id: d2-org-unit-level-cs" in levels.content
    instance = build_organisation_unit_instances([_ROOT], config).artifacts[0].content
    assert "* type = D2OrgUnitLevelCS#level-1" in instance


def test_empty_prefix_keeps_profile_token() -> None:
    """With an empty prefix, terminology goes bare but profiles keep the D2 token (cannot shadow Organization)."""
    config = GenerateConfig(naming=NamingConfig(prefix=""))
    profiles = build_organisation_unit_profiles(config)
    assert "Profile: D2Organization" in profiles.content
    levels = build_organisation_unit_level_terminology([1], config)
    assert "CodeSystem: OULevelCS" in levels.content
    assert "Id: ou-level-cs" in levels.content
