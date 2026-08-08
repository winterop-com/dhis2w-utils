"""Golden tests for organisation-unit profile and terminology FSH, and for the pre-built JSON registry."""

import base64
import json
from typing import Any

from dhis2w_fhir.attributes import AttributeCodeIndex, AttributeValueIn
from dhis2w_fhir.config import GenerateConfig, NamingConfig
from dhis2w_fhir.i18n import TranslationIn
from dhis2w_fhir.resources.organisation_units import (
    build_organisation_unit_instances,
    build_organisation_unit_level_terminology,
    build_organisation_unit_profiles,
    build_organisation_unit_terminology,
    build_registry_examples,
)
from dhis2w_fhir.resources.organisation_units.schemas import OrganisationUnitIn
from dhis2w_fhir.writer import JsonArtifact, JsonBuild

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
_CANONICAL = "http://example.org/fhir"

#: One organisation unit with every optional field populated, so both resources reach their full key set.
_RICHEST = OrganisationUnitIn(
    uid="mOsABqg3Cqw",
    name="HC Photang",
    short_name="Photang Health Center",
    code="OUL4HC20170839",
    description="A health centre.",
    level=4,
    path="/ImspTQPwCqd/mOsABqg3Cqw",
    parent_uid="ImspTQPwCqd",
    latitude=21.649026,
    longitude=102.241355,
    boundary_geojson='{"coordinates":[102.241355,21.649026],"type":"Point"}',
    contact_person="T. Thepsombath",
    email="photang@example.org",
    phone_number="98770095, 0309342578",
    closed=False,
    translations=[TranslationIn(locale="lo", property="NAME", value="ຮໝນ ພໍ່ຕັ້ງ")],
    attribute_values=[AttributeValueIn(attribute_uid="ihn1wb9eho8", value="KE03")],
)

_EXPECTED_ROOT_LOCATION = {
    "resourceType": "Location",
    "id": "ImspTQPwCqd",
    "meta": {"profile": ["http://example.org/fhir/StructureDefinition/d2-location"]},
    "identifier": [
        {"system": "http://dhis2.org/fhir/id/org-unit", "value": "ImspTQPwCqd"},
        {"system": "http://dhis2.org/fhir/id/org-unit-code", "value": "SL"},
    ],
    "name": "Sierra Leone",
    "description": "DHIS2 organisation unit Sierra Leone (ImspTQPwCqd), level 1 - physical location.",
    "status": "active",
    "managingOrganization": {"reference": "Organization/ImspTQPwCqd"},
}

_EXPECTED_DISTRICT_ORGANIZATION = {
    "resourceType": "Organization",
    "id": "O6uvpzGd5pu",
    "meta": {"profile": ["http://example.org/fhir/StructureDefinition/d2-organization"]},
    "identifier": [
        {"system": "http://dhis2.org/fhir/id/org-unit", "value": "O6uvpzGd5pu"},
        {"system": "http://dhis2.org/fhir/id/org-unit-code", "value": "O6uvpzGd5pu"},
    ],
    "name": "Bo",
    "alias": ["Bo District"],
    "type": [
        {
            "coding": [
                {
                    "system": "http://example.org/fhir/CodeSystem/d2-ou-level-cs",
                    "code": "level-2",
                    "display": "Level 2",
                }
            ]
        }
    ],
    "partOf": {"reference": "Organization/ImspTQPwCqd"},
    "telecom": [
        {"system": "phone", "value": "+232 76 000000"},
        {"system": "email", "value": "bo@example.org"},
    ],
    "contact": [{"name": {"text": "A. Person"}}],
    "active": True,
}

_EXPECTED_DISTRICT_LOCATION = {
    "resourceType": "Location",
    "id": "O6uvpzGd5pu",
    "meta": {"profile": ["http://example.org/fhir/StructureDefinition/d2-location"]},
    "identifier": [
        {"system": "http://dhis2.org/fhir/id/org-unit", "value": "O6uvpzGd5pu"},
        {"system": "http://dhis2.org/fhir/id/org-unit-code", "value": "O6uvpzGd5pu"},
    ],
    "name": "Bo",
    "description": "DHIS2 organisation unit Bo (O6uvpzGd5pu), level 2 - physical location.",
    "status": "active",
    "position": {"longitude": -11.7383, "latitude": 7.9647},
    "managingOrganization": {"reference": "Organization/O6uvpzGd5pu"},
    "partOf": {"reference": "Location/ImspTQPwCqd"},
}

#: The closed key set of an Organization, verified across 1500 real files.
_ORGANIZATION_KEYS = [
    "resourceType",
    "id",
    "meta",
    "extension",
    "identifier",
    "name",
    "_name",
    "alias",
    "type",
    "partOf",
    "telecom",
    "contact",
    "active",
]

#: The closed key set of a Location - R4 gives Location a description and gives Organization none.
_LOCATION_KEYS = [
    "resourceType",
    "id",
    "meta",
    "identifier",
    "name",
    "_name",
    "description",
    "status",
    "position",
    "extension",
    "managingOrganization",
    "partOf",
]


def _documents(build: JsonBuild) -> dict[str, dict[str, Any]]:
    """Every emitted registry file, keyed by its relative path, parsed back into a plain JSON document."""
    return {artifact.relative_path: json.loads(artifact.content) for artifact in build.artifacts}


def _instances(
    organisation_units: list[OrganisationUnitIn],
    config: GenerateConfig = _CONFIG,
    attribute_codes: AttributeCodeIndex | None = None,
) -> JsonBuild:
    """Build the registry for one selection against the test canonical."""
    return build_organisation_unit_instances(
        organisation_units, config, _CANONICAL, attribute_codes=attribute_codes or AttributeCodeIndex()
    )


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


_REGISTRY_EXAMPLES_GOLDEN = """Instance: D2OrganizationExample
InstanceOf: D2Organization
Title: "Example DHIS2 Organization - Sierra Leone (ImspTQPwCqd)"
Description: "A worked D2Organization: DHIS2 organisation unit Sierra Leone (ImspTQPwCqd) as the legal entity, \
carrying both DHIS2 identifiers and its hierarchy level."
Usage: #example
* id = "d2-organization-example"
* identifier[dhis2id].system = $DHIS2-OU
* identifier[dhis2id].value = "ImspTQPwCqd"
* identifier[dhis2code].system = $DHIS2-OU-CODE
* identifier[dhis2code].value = "SL"
* active = true
* name = "Sierra Leone"
* type = D2OU_Level_CS#level-1 "Level 1"

Instance: D2LocationExample
InstanceOf: D2Location
Title: "Example DHIS2 Location - Sierra Leone (ImspTQPwCqd)"
Description: "A worked D2Location: DHIS2 organisation unit Sierra Leone (ImspTQPwCqd) as the physical place, \
managed by the D2Organization of the same unit."
Usage: #example
* id = "d2-location-example"
* identifier[dhis2id].system = $DHIS2-OU
* identifier[dhis2id].value = "ImspTQPwCqd"
* identifier[dhis2code].system = $DHIS2-OU-CODE
* identifier[dhis2code].value = "SL"
* status = #active
* name = "Sierra Leone"
* managingOrganization = Reference(D2OrganizationExample)
"""


def test_the_registry_profiles_publish_one_worked_example_each() -> None:
    """The registry ships as JSON SUSHI never compiles, so the profiles are illustrated by a curated pair."""
    artifact = build_registry_examples([_DISTRICT, _ROOT], _CONFIG, ig_status="draft")
    assert artifact is not None
    assert artifact.relative_path == "organization/registry-examples.fsh"
    assert artifact.content == _REGISTRY_EXAMPLES_GOLDEN


def test_the_registry_examples_are_drawn_from_the_selections_own_root() -> None:
    """The exemplar is the shallowest unit of the selection, so it validates against data the instance holds."""
    artifact = build_registry_examples([_ORPHAN, _DISTRICT], _CONFIG, ig_status="draft")
    assert artifact is not None
    assert '* identifier[dhis2id].value = "O6uvpzGd5pu"' in artifact.content
    assert '* type = D2OU_Level_CS#level-2 "Level 2"' in artifact.content
    assert "* position.longitude = -11.7383" in artifact.content
    assert "* position.latitude = 7.9647" in artifact.content


def test_the_registry_examples_follow_the_naming_tokens() -> None:
    """The instance names and ids derive from the same profile names the registry references."""
    artifact = build_registry_examples([_ROOT], GenerateConfig(naming=NamingConfig(prefix="Dhis2")), ig_status="draft")
    assert artifact is not None
    assert "Instance: Dhis2OrganizationExample" in artifact.content
    assert "InstanceOf: Dhis2Organization" in artifact.content
    assert '* id = "dhis2-location-example"' in artifact.content
    assert "* managingOrganization = Reference(Dhis2OrganizationExample)" in artifact.content


def test_an_empty_selection_publishes_no_registry_example() -> None:
    """With no unit selected there is no real data to illustrate the profiles with, so nothing is written."""
    assert build_registry_examples([], _CONFIG, ig_status="draft") is None


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
    """The file name and the resource id both read the bare UID, so the compiled URLs do too."""
    documents = _documents(_instances([_ROOT]))
    assert sorted(documents) == ["registry/Location-ImspTQPwCqd.json", "registry/Organization-ImspTQPwCqd.json"]
    assert [document["id"] for document in documents.values()] == ["ImspTQPwCqd", "ImspTQPwCqd"]


def test_level_terminology_covers_observed_levels() -> None:
    """The level CodeSystem lists each observed level once, sorted."""
    artifact = build_organisation_unit_level_terminology([2, 1, 2, 3], _CONFIG, ig_status="draft")
    assert artifact.content.count("* #level-") == 3
    assert '* #level-1 "Level 1"' in artifact.content
    assert "ValueSet: D2OU_Level_VS" in artifact.content


def test_instances_golden_one_file_per_resource_grouped_by_level() -> None:
    """One file per resource, deepest level last; every unit gets a Location, position only with geometry."""
    build = _instances([_DISTRICT, _ROOT])
    assert [artifact.relative_path for artifact in build.artifacts] == [
        "registry/Organization-ImspTQPwCqd.json",
        "registry/Location-ImspTQPwCqd.json",
        "registry/Organization-O6uvpzGd5pu.json",
        "registry/Location-O6uvpzGd5pu.json",
    ]
    documents = _documents(build)
    assert documents["registry/Location-ImspTQPwCqd.json"] == _EXPECTED_ROOT_LOCATION
    assert documents["registry/Organization-O6uvpzGd5pu.json"] == _EXPECTED_DISTRICT_ORGANIZATION
    assert documents["registry/Location-O6uvpzGd5pu.json"] == _EXPECTED_DISTRICT_LOCATION
    assert build.notes == []


def test_every_artifact_is_indented_json_ending_in_a_newline() -> None:
    """The registry files are written as they are read: two-space indented JSON, one trailing newline."""
    artifact: JsonArtifact = _instances([_ROOT]).artifacts[0]
    assert artifact.content.endswith("}\n")
    assert '\n  "id": "ImspTQPwCqd",' in artifact.content


def test_root_has_no_part_of_and_code_slice() -> None:
    """The root instances omit partOf but carry the dhis2code identifier slice on both resources."""
    documents = _documents(_instances([_ROOT]))
    for document in documents.values():
        assert "partOf" not in document
        assert document["identifier"][1] == {"system": "http://dhis2.org/fhir/id/org-unit-code", "value": "SL"}


def test_code_identifier_falls_back_to_the_uid() -> None:
    """A unit without a usable DHIS2 code still carries the code slice, repeating the UID."""
    unassigned = OrganisationUnitIn(uid="Ncd1aaaaaaa", name="Uncoded", level=1, path="/Ncd1aaaaaaa")
    unusable = OrganisationUnitIn(uid="Bad1aaaaaaa", name="Spaced", level=1, path="/Bad1aaaaaaa", code=" not a code ")
    documents = _documents(_instances([unassigned, unusable]))
    for path, document in documents.items():
        uid = path.split("-")[1].removesuffix(".json")
        assert document["identifier"] == [
            {"system": "http://dhis2.org/fhir/id/org-unit", "value": uid},
            {"system": "http://dhis2.org/fhir/id/org-unit-code", "value": uid},
        ]


def test_closed_unit_is_inactive() -> None:
    """A unit whose closedDate has passed emits an inactive Organization and Location."""
    closed = OrganisationUnitIn(uid="Cls1aaaaaaa", name="Closed", level=1, path="/Cls1aaaaaaa", closed=True)
    documents = _documents(_instances([closed]))
    assert documents["registry/Organization-Cls1aaaaaaa.json"]["active"] is False
    assert documents["registry/Location-Cls1aaaaaaa.json"]["status"] == "inactive"


def test_open_unit_is_active() -> None:
    """A unit DHIS2 has not closed emits an active Organization and Location."""
    documents = _documents(_instances([_ROOT]))
    assert documents["registry/Organization-ImspTQPwCqd.json"]["active"] is True
    assert documents["registry/Location-ImspTQPwCqd.json"]["status"] == "active"


def test_out_of_selection_parent_is_noted() -> None:
    """A parent outside the selection omits partOf and lands in one aggregated note."""
    build = _instances([_ORPHAN])
    for document in _documents(build).values():
        assert "partOf" not in document
    assert len(build.notes) == 1
    assert "outside the selection" in build.notes[0]
    assert "Badjia (YuQRtpLP10I)" in build.notes[0]


def test_references_are_resource_type_slash_id() -> None:
    """Every reference is a valid FHIR relative reference, never the hyphenated FSH instance name."""
    documents = _documents(_instances([_ROOT, _DISTRICT]))
    organization = documents["registry/Organization-O6uvpzGd5pu.json"]
    location = documents["registry/Location-O6uvpzGd5pu.json"]
    assert organization["partOf"] == {"reference": "Organization/ImspTQPwCqd"}
    assert location["partOf"] == {"reference": "Location/ImspTQPwCqd"}
    assert location["managingOrganization"] == {"reference": "Organization/O6uvpzGd5pu"}


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
    documents = _documents(_instances([unit]))
    extension = documents["registry/Location-Bnd1aaaaaaa.json"]["extension"][0]
    assert extension["url"] == "http://hl7.org/fhir/StructureDefinition/location-boundary-geojson"
    assert extension["valueAttachment"]["contentType"] == "application/geo+json"
    assert extension["valueAttachment"]["data"]
    assert "extension" not in documents["registry/Organization-Bnd1aaaaaaa.json"]


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
    location = _documents(_instances([unit]))["registry/Location-Pnt1aaaaaaa.json"]
    encoded = base64.b64encode(b'{"coordinates":[-11.7383,7.9647],"type":"Point"}').decode("ascii")
    assert location["extension"] == [
        {
            "url": "http://hl7.org/fhir/StructureDefinition/location-boundary-geojson",
            "valueAttachment": {
                "contentType": "application/geo+json",
                "data": encoded,
                "title": "Pointy (Pnt1aaaaaaa)",
                "size": 48,
            },
        }
    ]
    assert location["position"] == {"longitude": -11.7383, "latitude": 7.9647}


def test_a_unit_without_geometry_omits_position_and_extension() -> None:
    """No geometry means neither the position nor the boundary extension is emitted at all."""
    location = _documents(_instances([_ROOT]))["registry/Location-ImspTQPwCqd.json"]
    assert "position" not in location
    assert "extension" not in location


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
    """Custom naming tokens flow into names and ids (e.g. organisation_unit "OrgUnit" -> d2-org-unit-level-cs)."""
    config = GenerateConfig(naming=NamingConfig(organisation_unit="OrgUnit"))
    levels = build_organisation_unit_level_terminology([1], config, ig_status="draft")
    assert "CodeSystem: D2OrgUnit_Level_CS" in levels.content
    assert "Id: d2-org-unit-level-cs" in levels.content
    organization = _documents(_instances([_ROOT], config))["registry/Organization-ImspTQPwCqd.json"]
    assert organization["type"][0]["coding"][0]["system"] == ("http://example.org/fhir/CodeSystem/d2-org-unit-level-cs")


def test_instance_urls_follow_the_ig_canonical() -> None:
    """The profile and level-code URLs are the IG's own canonical, not the identifier system base."""
    documents = _documents(
        build_organisation_unit_instances(
            [_ROOT], _CONFIG, "https://ig.example/fhir", attribute_codes=AttributeCodeIndex()
        )
    )
    organization = documents["registry/Organization-ImspTQPwCqd.json"]
    location = documents["registry/Location-ImspTQPwCqd.json"]
    assert organization["meta"]["profile"] == ["https://ig.example/fhir/StructureDefinition/d2-organization"]
    assert organization["type"][0]["coding"][0]["system"] == "https://ig.example/fhir/CodeSystem/d2-ou-level-cs"
    assert location["meta"]["profile"] == ["https://ig.example/fhir/StructureDefinition/d2-location"]


def test_identifier_systems_follow_the_configured_base() -> None:
    """Both identifier slices hang off `[generate] identifier_system_base`, matching the $DHIS2-OU aliases."""
    config = GenerateConfig(identifier_system_base="https://dhis2.example/fhir")
    organization = _documents(_instances([_ROOT], config))["registry/Organization-ImspTQPwCqd.json"]
    assert [entry["system"] for entry in organization["identifier"]] == [
        "https://dhis2.example/fhir/id/org-unit",
        "https://dhis2.example/fhir/id/org-unit-code",
    ]


def test_empty_prefix_keeps_profile_token() -> None:
    """With an empty prefix, terminology goes bare but profiles keep the D2 token (cannot shadow Organization)."""
    config = GenerateConfig(naming=NamingConfig(prefix=""))
    profiles = build_organisation_unit_profiles(config, ig_status="draft")
    assert "Profile: D2Organization" in profiles.content
    levels = build_organisation_unit_level_terminology([1], config, ig_status="draft")
    assert "CodeSystem: OU_Level_CS" in levels.content
    assert "Id: ou-level-cs" in levels.content
    organization = _documents(_instances([_ROOT], config))["registry/Organization-ImspTQPwCqd.json"]
    assert organization["meta"]["profile"] == ["http://example.org/fhir/StructureDefinition/d2-organization"]
    assert organization["type"][0]["coding"][0]["system"] == "http://example.org/fhir/CodeSystem/ou-level-cs"


def test_narrative_text_escapes_markup_while_the_element_name_stays_raw() -> None:
    """The Location description escapes markup for the page furniture; `name` carries the DHIS2 text verbatim."""
    unit = _ROOT.model_copy(update={"name": "Region <A> & <B>", "short_name": "Short <A>"})
    documents = _documents(_instances([unit]))
    location = documents["registry/Location-ImspTQPwCqd.json"]
    organization = documents["registry/Organization-ImspTQPwCqd.json"]
    assert location["description"] == (
        "DHIS2 organisation unit Region &lt;A&gt; &amp; &lt;B&gt; (ImspTQPwCqd), level 1 - physical location."
    )
    assert location["name"] == "Region <A> & <B>"
    assert organization["name"] == "Region <A> & <B>"
    assert organization["alias"] == ["Short <A>"]


def test_short_name_equal_to_the_name_emits_no_alias() -> None:
    """An alias repeating the name carries nothing, so it is left off entirely."""
    unit = _ROOT.model_copy(update={"short_name": "Sierra Leone"})
    assert "alias" not in _documents(_instances([unit]))["registry/Organization-ImspTQPwCqd.json"]


def test_name_translations_reach_both_resources_as_primitive_extensions() -> None:
    """Each NAME translation becomes one standard translation extension on the `_name` sibling of both resources."""
    expected = {
        "extension": [
            {
                "url": "http://hl7.org/fhir/StructureDefinition/translation",
                "extension": [
                    {"url": "lang", "valueCode": "lo"},
                    {"url": "content", "valueString": "ຮໝນ ພໍ່ຕັ້ງ"},
                ],
            }
        ]
    }
    documents = _documents(_instances([_ROOT, _RICHEST]))
    assert documents["registry/Organization-mOsABqg3Cqw.json"]["_name"] == expected
    assert documents["registry/Location-mOsABqg3Cqw.json"]["_name"] == expected


def test_a_unit_without_translations_omits_the_name_sibling() -> None:
    """Zero NAME translations means no `_name` key at all, rather than an empty extension array."""
    for document in _documents(_instances([_ROOT])).values():
        assert "_name" not in document


def test_the_richest_unit_emits_exactly_the_closed_key_sets() -> None:
    """Every optional field populated fills the closed key set of each resource - and nothing beyond it."""
    documents = _documents(_instances([_ROOT, _RICHEST]))
    organization = documents["registry/Organization-mOsABqg3Cqw.json"]
    location = documents["registry/Location-mOsABqg3Cqw.json"]
    assert list(organization) == _ORGANIZATION_KEYS
    assert list(location) == _LOCATION_KEYS
    assert "description" not in organization


def test_registry_scale_note_fires_only_past_the_render_cost_threshold() -> None:
    """A large registry warns at generate time about the publisher's rendering pass, naming the dials."""
    from dhis2w_fhir.service import (
        _INSTANCES_PER_ORGANISATION_UNIT,
        _REGISTRY_RENDER_COST_INSTANCES,
        _registry_scale_notes,
    )

    just_under = _REGISTRY_RENDER_COST_INSTANCES // _INSTANCES_PER_ORGANISATION_UNIT - 1
    assert _registry_scale_notes(just_under) == []
    assert _registry_scale_notes(0) == []

    note = _registry_scale_notes(12_581)
    assert len(note) == 1
    assert "12581 organisation units emit 25162 instances" in note[0]
    assert "max_level" in note[0]
    assert "renders a page per resource" in note[0]
    # The registry ships as pre-built JSON, so the SUSHI timeout is no longer the failure it warns about.
    assert "143" not in note[0]
    assert "timeout" not in note[0]
