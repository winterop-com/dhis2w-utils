"""Per-version parity for the `fhir` plugin service - scaffold + generate on all three trees.

Resolves the service per `core_version` (v41/v42/v43) so the v41/v43 copies are actually
executed. Mocked (respx); no live stack. Endpoints derive from the generated resource
accessors: `/api/optionSets` and `/api/organisationUnits`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import httpx
import respx
from dhis2w_core.fhir_core import GENERATED_HEADER, InitOptions, load_project
from dhis2w_core.profile import resolve_profile

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

_ORG_UNITS_PAYLOAD = {
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


async def _scaffold_project(service: ModuleType, directory: Path) -> None:
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


async def test_init_project_parity(
    core_version: str,
    core_profile: None,  # noqa: ARG001
    plugin_service: Callable[[str], ModuleType],
    tmp_path: Path,
) -> None:
    """`init_project` writes the same scaffold on every version tree."""
    service = plugin_service("fhir")
    await _scaffold_project(service, tmp_path / core_version)
    assert (tmp_path / core_version / "ig" / "sushi-config.yaml").exists()


@respx.mock
async def test_generate_option_sets_parity(
    core_version: str,
    core_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
    tmp_path: Path,
) -> None:
    """`generate_option_sets` writes a CodeSystem/ValueSet pair per set, on every version tree."""
    mock_system_info(core_version)
    service = plugin_service("fhir")
    await _scaffold_project(service, tmp_path)
    route = respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))

    report = await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))

    assert route.called
    assert report.option_set_count == 1
    assert report.written_files == ["terminology/birth-type.fsh"]
    content = (tmp_path / "ig" / "input" / "fsh" / "terminology" / "birth-type.fsh").read_text(encoding="utf-8")
    assert content.startswith(GENERATED_HEADER)
    assert "CodeSystem: Dhis2OptionSetBirthTypeCS" in content


@respx.mock
async def test_generate_org_units_parity(
    core_version: str,
    core_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
    tmp_path: Path,
) -> None:
    """`generate_org_units` writes profiles, level terminology, and per-level instances on every tree."""
    mock_system_info(core_version)
    service = plugin_service("fhir")
    await _scaffold_project(service, tmp_path)
    route = respx.get(f"{_HOST}/api/organisationUnits").mock(return_value=httpx.Response(200, json=_ORG_UNITS_PAYLOAD))

    report = await service.generate_org_units(resolve_profile("probe"), load_project(tmp_path))

    assert route.called
    assert report.org_unit_count == 2
    assert report.location_count == 1
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


@respx.mock
async def test_generate_is_idempotent_parity(
    core_version: str,
    core_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
    tmp_path: Path,
) -> None:
    """A second generate run replaces the previously generated files instead of stacking new ones."""
    mock_system_info(core_version)
    service = plugin_service("fhir")
    await _scaffold_project(service, tmp_path)
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))

    first = await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))
    second = await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))

    assert first.deleted_files == []
    assert second.deleted_files == ["birth-type.fsh"]
    terminology = tmp_path / "ig" / "input" / "fsh" / "terminology"
    assert sorted(path.name for path in terminology.glob("*.fsh")) == ["birth-type.fsh"]
