"""Service tests against every DHIS2 major - the client auto-detects and the service stays version-neutral.

Mocked (respx); no live stack. Endpoints derive from the generated resource
accessors: `/api/optionSets` and `/api/organisationUnits`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import respx
from dhis2w_core.profile import resolve_profile
from dhis2w_fhir import GENERATED_HEADER, InitOptions, load_project, service

_HOST = "https://dhis2.example"

_OPTION_SETS_PAYLOAD = {
    "optionSets": [
        {
            "id": "Xa1b2c3d4e5",
            "name": "Birth type",
            "options": [
                {"id": "kRRUtYaGett", "code": "NB", "name": "Natural Birth", "sortOrder": 1},
                {"id": "EBE0c8sZazS", "code": "CS", "name": "Scheduled Cesarean", "sortOrder": 2},
            ],
        }
    ]
}

_ORGANISATION_UNITS_PAYLOAD = {
    "organisationUnits": [
        {"id": "ImspTQPwCqd", "name": "Sierra Leone", "level": 1, "path": "/ImspTQPwCqd", "code": "SL"},
        {
            "id": "O6uvpzGd5pu",
            "name": "Bo",
            "level": 2,
            "path": "/ImspTQPwCqd/O6uvpzGd5pu",
            "parent": {"id": "ImspTQPwCqd"},
            "geometry": {"type": "Point", "coordinates": [-11.7383, 7.9647]},
        },
    ]
}


async def _scaffold_project(directory: Path) -> None:
    """Scaffold a minimal project so generate targets have a fhir.toml + ig tree."""
    options = InitOptions(
        ig_id="dhis2.fhir.parity",
        canonical="http://example.org/fhir",
        name="Dhis2FhirParity",
        title="Parity IG",
        publisher="Parity Org",
    )
    report = await service.init_project(directory, options)
    assert "fhir.toml" in report.created_files


@respx.mock
async def test_generate_option_sets_across_majors(
    wire_version: str,
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """`generate_option_sets` writes a CodeSystem/ValueSet pair per set against every DHIS2 major."""
    mock_system_info(wire_version)
    await _scaffold_project(tmp_path)
    route = respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))

    report = await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))

    assert route.called
    assert report.option_set_count == 1
    assert report.written_files == ["terminology/xa1b2c3d4e5.fsh"]
    content = (tmp_path / "ig" / "input" / "fsh" / "terminology" / "xa1b2c3d4e5.fsh").read_text(encoding="utf-8")
    assert content.startswith(GENERATED_HEADER)
    assert "CodeSystem: D2OSXa1b2c3d4e5CS" in content
    assert 'Title: "Birth type"' in content


@respx.mock
async def test_generate_organisation_units_across_majors(
    wire_version: str,
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """`generate_organisation_units` writes profiles, level terminology, and per-level instances on every major."""
    mock_system_info(wire_version)
    await _scaffold_project(tmp_path)
    route = respx.get(f"{_HOST}/api/organisationUnits").mock(
        return_value=httpx.Response(200, json=_ORGANISATION_UNITS_PAYLOAD)
    )

    report = await service.generate_organisation_units(resolve_profile("probe"), load_project(tmp_path))

    assert route.called
    assert report.organisation_unit_count == 2
    assert report.position_count == 1
    assert report.boundary_count == 1
    assert report.written_files == [
        "organization/org-unit-levels.fsh",
        "organization/org-units-level-1.fsh",
        "organization/org-units-level-2.fsh",
        "organization/profiles.fsh",
    ]
    level_two = (tmp_path / "ig" / "input" / "fsh" / "organization" / "org-units-level-2.fsh").read_text(
        encoding="utf-8"
    )
    assert "* partOf = Reference(OrganizationImspTQPwCqd)" in level_two
    assert "* position.latitude = 7.9647" in level_two
    assert "* position.longitude = -11.7383" in level_two
    assert '* extension[+].url = "http://hl7.org/fhir/StructureDefinition/location-boundary-geojson"' in level_two
    assert "* partOf = Reference(LocationImspTQPwCqd)" in level_two
    level_one = (tmp_path / "ig" / "input" / "fsh" / "organization" / "org-units-level-1.fsh").read_text(
        encoding="utf-8"
    )
    assert "Instance: LocationImspTQPwCqd" in level_one


@respx.mock
async def test_validate_codes_across_majors(
    wire_version: str,
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
) -> None:
    """`validate_codes` reads option sets and reports FHIR-safety findings on every major."""
    mock_system_info(wire_version)
    payload = {
        "optionSets": [
            {
                "id": "Xa1b2c3d4e5",
                "name": "Sample",
                "options": [{"id": "AcdAzPoqdtd", "code": " bad ", "name": "Bad", "sortOrder": 1}],
            }
        ]
    }
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=payload))
    sweep = {"dataElements": [{"id": "De1aaaaaaaa", "name": "Bad DE", "code": "DE 1  x"}]}
    respx.get(f"{_HOST}/api/metadata").mock(return_value=httpx.Response(200, json=sweep))

    context = service.resolve_validation_context()
    report = await service.validate_codes(resolve_profile("probe"), context.config)

    assert report.error_count == 2
    assert {finding.resource_type for finding in report.findings} == {"options", "dataElements"}
    assert report.resource_type_count == 1
    assert report.object_count == 1


@respx.mock
async def test_generate_is_idempotent(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A second generate run replaces the previously generated files instead of stacking new ones."""
    mock_system_info("v42")
    await _scaffold_project(tmp_path)
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))

    first = await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))
    second = await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))

    assert first.deleted_files == []
    assert first.written_files == ["terminology/xa1b2c3d4e5.fsh"]
    assert second.written_files == []
    assert second.deleted_files == []
    assert second.unchanged_count == 1
    terminology = tmp_path / "ig" / "input" / "fsh" / "terminology"
    assert sorted(path.name for path in terminology.glob("*.fsh")) == ["xa1b2c3d4e5.fsh"]


def test_polygon_centroid_of_a_square() -> None:
    """A square ring's area-weighted centroid is its middle."""
    ring = [[0, 0], [4, 0], [4, 2], [0, 2], [0, 0]]
    centroid = service._polygon_centroid("Polygon", [ring], [])
    assert centroid.longitude == 2.0
    assert centroid.latitude == 1.0


def test_polygon_centroid_of_an_l_shape_is_not_the_bounding_box_midpoint() -> None:
    """An L-shaped ring (area 6) pulls the shoelace centroid off the bounding-box midpoint (2.0, 1.5)."""
    ring = [[0, 0], [4, 0], [4, 1], [1, 1], [1, 3], [0, 3], [0, 0]]
    centroid = service._polygon_centroid("Polygon", [ring], [])
    assert centroid.longitude == 1.5
    assert centroid.latitude == 1.0


def test_polygon_centroid_uses_the_largest_outer_ring() -> None:
    """A MultiPolygon takes the centroid of the outer ring with the largest absolute area."""
    small = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
    large = [[10, 10], [14, 10], [14, 12], [10, 12], [10, 10]]
    centroid = service._polygon_centroid("MultiPolygon", [[small], [large]], [])
    assert centroid.longitude == 12.0
    assert centroid.latitude == 11.0


def test_degenerate_ring_falls_back_to_the_vertex_mean() -> None:
    """A zero-area ring has no shoelace centroid, so its vertices are averaged."""
    ring = [[0, 0], [2, 2], [4, 4], [0, 0]]
    centroid = service._polygon_centroid("Polygon", [ring], [])
    assert centroid.longitude == 1.5
    assert centroid.latitude == 1.5


def test_entry_point_plugin_is_discovered() -> None:
    """The `dhis2.plugins` entry point exposes the fhir plugin to core discovery on every tree."""
    from dhis2w_core.plugin import discover_plugins

    for version_key in ("v41", "v42", "v43"):
        names = {plugin.name for plugin in discover_plugins(version_key)}
        assert "fhir" in names
