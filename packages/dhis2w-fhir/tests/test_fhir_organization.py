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

_EXPECTED_ROOT_LOCATION = """Instance: Location-ImspTQPwCqd
InstanceOf: D2Location
Title: "Location - Sierra Leone"
Description: "DHIS2 organisation unit Sierra Leone (ImspTQPwCqd), level 1 - physical location."
Usage: #definition
* id = "ImspTQPwCqd"
* identifier[dhis2id].system = $DHIS2-OU
* identifier[dhis2id].value = "ImspTQPwCqd"
* identifier[dhis2code].system = $DHIS2-OU-CODE
* identifier[dhis2code].value = "SL"
* name = "Sierra Leone"
* status = #active
* managingOrganization = Reference(Organization-ImspTQPwCqd)
"""

_EXPECTED_DISTRICT = """Instance: Organization-O6uvpzGd5pu
InstanceOf: D2Organization
Title: "Organization - Bo"
Description: "DHIS2 organisation unit Bo (O6uvpzGd5pu), level 2."
Usage: #definition
* id = "O6uvpzGd5pu"
* identifier[dhis2id].system = $DHIS2-OU
* identifier[dhis2id].value = "O6uvpzGd5pu"
* identifier[dhis2code].system = $DHIS2-OU-CODE
* identifier[dhis2code].value = "O6uvpzGd5pu"
* name = "Bo"
* alias = "Bo District"
* type = D2OU_Level_CS#level-2 "Level 2"
* partOf = Reference(Organization-ImspTQPwCqd)
* telecom[+].system = #phone
* telecom[=].value = "+232 76 000000"
* telecom[+].system = #email
* telecom[=].value = "bo@example.org"
* contact[+].name.text = "A. Person"
* active = true

Instance: Location-O6uvpzGd5pu
InstanceOf: D2Location
Title: "Location - Bo"
Description: "DHIS2 organisation unit Bo (O6uvpzGd5pu), level 2 - physical location."
Usage: #definition
* id = "O6uvpzGd5pu"
* identifier[dhis2id].system = $DHIS2-OU
* identifier[dhis2id].value = "O6uvpzGd5pu"
* identifier[dhis2code].system = $DHIS2-OU-CODE
* identifier[dhis2code].value = "O6uvpzGd5pu"
* name = "Bo"
* status = #active
* position.latitude = 7.9647
* position.longitude = -11.7383
* managingOrganization = Reference(Organization-O6uvpzGd5pu)
* partOf = Reference(Location-ImspTQPwCqd)
"""


def test_profiles_artifact() -> None:
    """Both profiles slice the two DHIS2 identifiers and bind level extensibly."""
    artifact = build_organisation_unit_profiles(_CONFIG, ig_status="draft")
    assert artifact.relative_path == "organization/profiles.fsh"
    assert "Profile: D2Organization" in artifact.content
    assert artifact.content.count("* ^status = #draft") == 2
    assert artifact.content.count("* identifier contains dhis2id 1..1 and dhis2code 1..1") == 2
    assert artifact.content.count('* identifier ^slicing.discriminator.path = "system"') == 2
    assert "* type from D2OU_Level_VS (extensible)" in artifact.content
    assert "* partOf only Reference(D2Organization)" in artifact.content
    assert "Profile: D2Location" in artifact.content
    assert "* managingOrganization only Reference(D2Organization)" in artifact.content
    assert "* position 0..1 MS" in artifact.content
    assert "* partOf only Reference(D2Location)" in artifact.content


def test_organisation_unit_artifacts_derive_their_publication_state_from_the_ig_status() -> None:
    """Profiles, the level pair, and the whole-selection pair all take ^status and ^experimental from it."""
    draft_profiles = build_organisation_unit_profiles(_CONFIG, ig_status="draft")
    assert draft_profiles.content.count("* ^status = #draft") == 2
    assert draft_profiles.content.count("* ^experimental = true") == 2
    profiles = build_organisation_unit_profiles(_CONFIG, ig_status="active")
    assert profiles.content.count("* ^status = #active") == 2
    assert profiles.content.count("* ^experimental = false") == 2
    draft_levels = build_organisation_unit_level_terminology([1], _CONFIG, ig_status="draft")
    assert draft_levels.content.count("* ^status = #draft") == 2
    assert draft_levels.content.count("* ^experimental = true") == 2
    levels = build_organisation_unit_level_terminology([1], _CONFIG, ig_status="active")
    assert levels.content.count("* ^status = #active") == 2
    assert levels.content.count("* ^experimental = false") == 2
    draft_selection = build_organisation_unit_terminology([_ROOT], _CONFIG, ig_status="draft")
    assert draft_selection.content.count("* ^status = #draft") == 2
    assert draft_selection.content.count("* ^experimental = true") == 2
    selection = build_organisation_unit_terminology([_ROOT], _CONFIG, ig_status="active")
    assert selection.content.count("* ^status = #active") == 2
    assert selection.content.count("* ^experimental = false") == 2


def test_location_profile_declares_the_boundary_extension() -> None:
    """D2Location declares the GeoJSON boundary extension its instances carry, rather than leaving it loose."""
    content = build_organisation_unit_profiles(_CONFIG, ig_status="draft").content
    assert (
        "* extension contains http://hl7.org/fhir/StructureDefinition/location-boundary-geojson named boundary 0..1"
        in content
    )
    assert "* extension[boundary] ^short = \"The unit's DHIS2 geometry, carried as a GeoJSON Feature" in content


def test_instances_carry_the_bare_uid_as_their_resource_id() -> None:
    """Compiled files and URLs read Organization-<uid>.json / Location-<uid>.json, not the FSH instance name."""
    content = build_organisation_unit_instances([_ROOT], _CONFIG).artifacts[0].content
    assert content.count('* id = "ImspTQPwCqd"') == 2


def test_level_terminology_covers_observed_levels() -> None:
    """The level CodeSystem lists each observed level once, sorted."""
    artifact = build_organisation_unit_level_terminology([2, 1, 2, 3], _CONFIG, ig_status="draft")
    assert artifact.content.count("* #level-") == 3
    assert '* #level-1 "Level 1"' in artifact.content
    assert "ValueSet: D2OU_Level_VS" in artifact.content


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
    artifact = build_organisation_unit_terminology([_ROOT, _DISTRICT], _CONFIG, ig_status="draft")
    content = artifact.content
    assert "CodeSystem: D2OU_CS" in content
    assert "* #O6uvpzGd5pu ^property[+].code = #level" in content
    assert "* #O6uvpzGd5pu ^property[=].valueInteger = 2" in content
    assert "* #O6uvpzGd5pu ^property[+].code = #parent" in content
    assert "* #O6uvpzGd5pu ^property[=].valueCode = #ImspTQPwCqd" in content
    assert "* #ImspTQPwCqd ^property[+].code = #dhis2-code" in content
    assert "ValueSet: D2OU_VS" in content


def test_naming_tokens_are_configurable() -> None:
    """Custom naming tokens flow into names and ids (e.g. organisation_unit "OrgUnit" -> D2OrgUnit_Level_CS)."""
    config = GenerateConfig(naming=NamingConfig(organisation_unit="OrgUnit"))
    levels = build_organisation_unit_level_terminology([1], config, ig_status="draft")
    assert "CodeSystem: D2OrgUnit_Level_CS" in levels.content
    assert "Id: d2-org-unit-level-cs" in levels.content
    instance = build_organisation_unit_instances([_ROOT], config).artifacts[0].content
    assert "* type = D2OrgUnit_Level_CS#level-1" in instance


def test_empty_prefix_keeps_profile_token() -> None:
    """With an empty prefix, terminology goes bare but profiles keep the D2 token (cannot shadow Organization)."""
    config = GenerateConfig(naming=NamingConfig(prefix=""))
    profiles = build_organisation_unit_profiles(config, ig_status="draft")
    assert "Profile: D2Organization" in profiles.content
    levels = build_organisation_unit_level_terminology([1], config, ig_status="draft")
    assert "CodeSystem: OU_Level_CS" in levels.content
    assert "Id: ou-level-cs" in levels.content


def test_org_unit_page_titles_escape_markup_while_the_element_name_stays_raw() -> None:
    """The Organization/Location page metadata escapes markup; `name` carries the DHIS2 text verbatim."""
    unit = _ROOT.model_copy(update={"name": "Region <A> & <B>"})
    content = build_organisation_unit_instances([unit], _CONFIG).artifacts[0].content
    assert 'Title: "Organization - Region &lt;A&gt; &amp; &lt;B&gt;"' in content
    assert 'Title: "Location - Region &lt;A&gt; &amp; &lt;B&gt;"' in content
    assert content.count('* name = "Region <A> & <B>"') == 2
