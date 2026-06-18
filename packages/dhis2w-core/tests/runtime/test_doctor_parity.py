"""Per-version parity for the `doctor` plugin service — exercise its public surface on all trees.

Mirrors the v42-only `tests/doctor/test_doctor_plugin.py` routes + assertions, but resolves the
service per `core_version` (v41/v42/v43) so the v41/v43 service code is actually executed and
counted, not just smoke-imported. The single public function `run_doctor` dispatches to three probe
categories (metadata, integrity, bugs); each test below drives one category path (plus the default
metadata+integrity combination). The three service trees are byte-identical copies (only the import
version differs), so the assertions are the same on every tree. Mocked (respx); no live stack.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

import httpx
import respx
from dhis2w_core.profile import resolve_profile

_HOST = "https://dhis2.example"


def _mock_metadata_endpoints() -> None:
    """Canned all-pass responses for every endpoint the metadata probes hit."""
    respx.get(f"{_HOST}/api/dataSets").mock(
        return_value=httpx.Response(
            200,
            json={
                "dataSets": [
                    {"id": "ds1", "name": "DS1", "dataSetElements": 3, "organisationUnits": 2},
                ]
            },
        ),
    )
    respx.get(f"{_HOST}/api/dataElements").mock(
        return_value=httpx.Response(
            200,
            json={
                "dataElements": [
                    {
                        "id": "de1",
                        "name": "DE1",
                        "domainType": "AGGREGATE",
                        "dataSetElements": 2,
                        "categoryCombo": {"id": "default"},
                    }
                ]
            },
        ),
    )
    respx.get(f"{_HOST}/api/programs").mock(
        return_value=httpx.Response(200, json={"programs": [{"id": "pr1", "programStages": 1}]}),
    )
    respx.get(f"{_HOST}/api/programStages").mock(
        return_value=httpx.Response(
            200, json={"programStages": [{"id": "ps1", "name": "ANC visit", "programStageDataElements": 2}]}
        ),
    )
    respx.get(f"{_HOST}/api/programIndicators").mock(
        return_value=httpx.Response(
            200,
            json={"programIndicators": [{"id": "pi1", "name": "ANC", "expression": "#{ps1.DEanc1}", "filter": ""}]},
        ),
    )
    respx.get(f"{_HOST}/api/userGroups").mock(
        return_value=httpx.Response(200, json={"userGroups": [{"id": "ug1", "name": "Ops", "users": 5}]}),
    )
    respx.get(f"{_HOST}/api/userRoles").mock(
        return_value=httpx.Response(200, json={"userRoles": [{"id": "ur1", "name": "Admin", "users": 1}]}),
    )
    respx.get(f"{_HOST}/api/users").mock(
        return_value=httpx.Response(200, json={"users": [{"id": "admin1", "username": "admin", "userRoles": 2}]}),
    )
    respx.get(f"{_HOST}/api/categoryCombos").mock(
        return_value=httpx.Response(
            200,
            json={
                "categoryCombos": [
                    {"id": "default", "name": "default", "categories": 0},
                    {"id": "cc1", "name": "Age+Sex", "categories": 2},
                ]
            },
        ),
    )
    respx.get(f"{_HOST}/api/organisationUnitGroups").mock(
        return_value=httpx.Response(
            200, json={"organisationUnitGroups": [{"id": "oug1", "name": "Facilities", "organisationUnits": 5}]}
        ),
    )
    respx.get(f"{_HOST}/api/organisationUnitGroupSets").mock(
        return_value=httpx.Response(
            200,
            json={"organisationUnitGroupSets": [{"id": "ougs1", "name": "Type", "organisationUnitGroups": 3}]},
        ),
    )
    respx.get(f"{_HOST}/api/dashboards").mock(
        return_value=httpx.Response(200, json={"dashboards": [{"id": "dash1", "name": "Main", "dashboardItems": 8}]}),
    )
    respx.get(f"{_HOST}/api/visualizations").mock(
        return_value=httpx.Response(
            200, json={"visualizations": [{"id": "v1", "name": "Chart", "dataDimensionItems": 2}]}
        ),
    )
    respx.get(f"{_HOST}/api/indicators").mock(
        return_value=httpx.Response(
            200, json={"indicators": [{"id": "ind1", "name": "ANC1", "numerator": "#{x}", "denominator": "1"}]}
        ),
    )
    respx.get(f"{_HOST}/api/validationRules").mock(
        return_value=httpx.Response(
            200,
            json={
                "validationRules": [
                    {"id": "vr1", "leftSide": {"expression": "#{a}"}, "rightSide": {"expression": "#{b}"}},
                ]
            },
        ),
    )
    respx.get(f"{_HOST}/api/organisationUnits").mock(
        return_value=httpx.Response(
            200,
            json={
                "organisationUnits": [
                    {"id": "ou0", "name": "Root", "level": 1, "parent": None},
                    {"id": "ou1", "name": "Child", "level": 2, "parent": {"id": "ou0"}},
                ]
            },
        ),
    )


def _mock_bugs_endpoints() -> None:
    """Canned all-pass responses for every endpoint the bugs probes hit."""
    respx.get(f"{_HOST}/api/me").mock(
        return_value=httpx.Response(200, json={"id": "admin-uid", "username": "admin"}),
    )
    respx.get(f"{_HOST}/api/loginConfig").mock(
        return_value=httpx.Response(
            200,
            json={
                "applicationTitle": "dhis2-utils local",
                "oidcProviders": [{"id": "dhis2"}],
                "useCustomLogoFront": True,
            },
        ),
    )
    respx.get(f"{_HOST}/.well-known/openid-configuration").mock(
        return_value=httpx.Response(
            200,
            json={
                "issuer": f"{_HOST}",
                "authorization_endpoint": f"{_HOST}/oauth2/authorize",
                "token_endpoint": f"{_HOST}/oauth2/token",
                "jwks_uri": f"{_HOST}/oauth2/jwks",
            },
        ),
    )
    respx.get(f"{_HOST}/api/analytics/rawData").mock(
        return_value=httpx.Response(404, json={"httpStatus": "Not Found", "httpStatusCode": 404}),
    )
    respx.get(f"{_HOST}/api/schemas/userRole").mock(
        return_value=httpx.Response(200, json={"properties": [{"name": "authority", "fieldName": "authorities"}]}),
    )
    respx.get(f"{_HOST}/api/analytics/outlierDetection").mock(
        return_value=httpx.Response(
            400,
            json={
                "httpStatus": "Bad Request",
                "httpStatusCode": 400,
                "message": "Value 'MOD_Z_SCORE' is not valid for parameter algorithm. "
                "Valid values are: [Z_SCORE, MIN_MAX, MODIFIED_Z_SCORE]",
            },
        ),
    )
    respx.get(f"{_HOST}/api/systemSettings/keyUseCustomLogoFront").mock(
        return_value=httpx.Response(200, json={"keyUseCustomLogoFront": "true"}),
    )


@respx.mock
async def test_run_doctor_metadata_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`run_doctor(categories=("metadata",))` runs only the metadata probes, all pass, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("doctor")
    _mock_metadata_endpoints()

    report = await service.run_doctor(resolve_profile("probe"), categories=("metadata",))

    categories = {probe.category for probe in report.probes}
    assert categories == {"metadata"}
    assert all(probe.status == "pass" for probe in report.probes)
    assert report.base_url == _HOST


@respx.mock
async def test_run_doctor_integrity_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`run_doctor(categories=("integrity",))` converts each dataIntegrity check into a probe, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("doctor")
    respx.get(f"{_HOST}/api/dataIntegrity/summary").mock(
        return_value=httpx.Response(
            200,
            json={
                "dashboards_no_items": {"count": 0, "severity": "WARN"},
                "orgunits_no_parent": {"count": 5, "severity": "ERROR"},
            },
        ),
    )

    report = await service.run_doctor(resolve_profile("probe"), categories=("integrity",))

    by_name = {probe.name: probe for probe in report.probes}
    assert by_name["integrity:dashboards_no_items"].status == "pass"
    assert by_name["integrity:orgunits_no_parent"].status == "warn"
    assert "5 issue" in by_name["integrity:orgunits_no_parent"].message


@respx.mock
async def test_run_doctor_bugs_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`run_doctor(categories=("bugs",))` runs only the bug-drift probes, all pass, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("doctor")
    _mock_bugs_endpoints()

    report = await service.run_doctor(resolve_profile("probe"), categories=("bugs",))

    categories = {probe.category for probe in report.probes}
    assert categories == {"bugs"}
    by_name = {probe.name: probe for probe in report.probes}
    # `dhis2-version` is gated on the wire version (v41 < 2.42), so exclude it from the
    # all-pass check — every other bug-drift probe lands on `pass` with the canned responses.
    assert all(probe.status == "pass" for name, probe in by_name.items() if name != "dhis2-version")


@respx.mock
async def test_run_doctor_default_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`run_doctor()` with no filter runs metadata + integrity but never bugs, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("doctor")
    _mock_metadata_endpoints()
    respx.get(f"{_HOST}/api/dataIntegrity/summary").mock(
        return_value=httpx.Response(200, json={"check_a": {"count": 0, "severity": "WARN"}}),
    )

    report = await service.run_doctor(resolve_profile("probe"))

    categories = {probe.category for probe in report.probes}
    assert "bugs" not in categories
    assert categories <= {"metadata", "integrity"}
