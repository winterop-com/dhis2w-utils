"""Tests for the doctor plugin — probe categories, CLI sub-commands, plugin descriptor."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from dhis2w_cli.main import build_app
from dhis2w_core.profile import Profile
from dhis2w_core.v42.plugins.doctor import plugin, service
from typer.testing import CliRunner


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Raw-env profile so `profile_from_env()` resolves without TOML."""
    for key in ("DHIS2_PROFILE", "DHIS2_URL", "DHIS2_PAT", "DHIS2_USERNAME", "DHIS2_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DHIS2_URL", "https://dhis2.example")
    monkeypatch.setenv("DHIS2_PAT", "test-token")
    yield


@pytest.fixture
def profile() -> Profile:
    return Profile(base_url="https://dhis2.example", auth="pat", token="test-token")


def _mock_preamble() -> None:
    """Endpoints Dhis2Client.connect() hits before the per-test routes."""
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text=""))
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"}),
    )


def _mock_bugs_pass() -> None:
    """Canned responses for the `bugs` probes to all land on `pass`."""
    respx.get("https://dhis2.example/api/me").mock(
        return_value=httpx.Response(200, json={"id": "admin-uid", "username": "admin"}),
    )
    respx.get("https://dhis2.example/api/loginConfig").mock(
        return_value=httpx.Response(
            200,
            json={
                "applicationTitle": "dhis2-utils local",
                "oidcProviders": [{"id": "dhis2"}],
                "useCustomLogoFront": True,
            },
        ),
    )
    respx.get("https://dhis2.example/.well-known/openid-configuration").mock(
        return_value=httpx.Response(
            200,
            json={
                "issuer": "https://dhis2.example",
                "authorization_endpoint": "https://dhis2.example/oauth2/authorize",
                "token_endpoint": "https://dhis2.example/oauth2/token",
                "jwks_uri": "https://dhis2.example/oauth2/jwks",
            },
        ),
    )
    respx.get("https://dhis2.example/api/analytics/rawData").mock(
        return_value=httpx.Response(404, json={"httpStatus": "Not Found", "httpStatusCode": 404}),
    )
    respx.get("https://dhis2.example/api/schemas/userRole").mock(
        return_value=httpx.Response(200, json={"properties": [{"name": "authority", "fieldName": "authorities"}]}),
    )
    respx.get("https://dhis2.example/api/analytics/outlierDetection").mock(
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
    respx.get("https://dhis2.example/api/systemSettings/keyUseCustomLogoFront").mock(
        return_value=httpx.Response(200, json={"keyUseCustomLogoFront": "true"}),
    )


def _mock_metadata_probes(
    *,
    orphan_data_elements: int = 0,
    orphan_user_roles: int = 0,
    orphan_program_stages: int = 0,
    empty_program_indicators: int = 0,
    orphan_ref_program_indicators: int = 0,
    users_without_roles: int = 0,
    broken_validation_rules: int = 0,
    org_unit_levels: list[int] | None = None,
) -> None:
    """Canned responses for the `metadata` probes.

    Knobs inject rows with the relevant defect to exercise each probe's warn
    path; defaults leave every probe on the pass path.
    """
    respx.get("https://dhis2.example/api/dataSets").mock(
        return_value=httpx.Response(200, json={"dataSets": [{"id": "ds1", "name": "DS1", "dataSetElements": 3}]}),
    )
    de_rows = [
        {
            "id": "de1",
            "name": "DE1",
            "domainType": "AGGREGATE",
            "dataSetElements": 2,
            "categoryCombo": {"id": "default"},
        }
    ]
    de_rows.extend(
        {
            "id": f"orphanDe{i}",
            "name": f"Orphan{i}",
            "domainType": "AGGREGATE",
            "dataSetElements": 0,
            "categoryCombo": {"id": "default"},
        }
        for i in range(orphan_data_elements)
    )
    respx.get("https://dhis2.example/api/dataElements").mock(
        return_value=httpx.Response(200, json={"dataElements": de_rows}),
    )
    respx.get("https://dhis2.example/api/programs").mock(
        return_value=httpx.Response(200, json={"programs": [{"id": "pr1", "programStages": 1}]}),
    )
    respx.get("https://dhis2.example/api/userGroups").mock(
        return_value=httpx.Response(200, json={"userGroups": [{"id": "ug1", "name": "Ops", "users": 5}]}),
    )
    ur_rows = [{"id": "ur1", "name": "Admin", "users": 1}]
    ur_rows.extend({"id": f"deadUr{i}", "name": f"Dead{i}", "users": 0} for i in range(orphan_user_roles))
    respx.get("https://dhis2.example/api/userRoles").mock(
        return_value=httpx.Response(200, json={"userRoles": ur_rows}),
    )
    respx.get("https://dhis2.example/api/categoryCombos").mock(
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
    respx.get("https://dhis2.example/api/organisationUnitGroups").mock(
        return_value=httpx.Response(
            200, json={"organisationUnitGroups": [{"id": "oug1", "name": "Facilities", "organisationUnits": 5}]}
        ),
    )
    respx.get("https://dhis2.example/api/organisationUnitGroupSets").mock(
        return_value=httpx.Response(
            200,
            json={"organisationUnitGroupSets": [{"id": "ougs1", "name": "Facility type", "organisationUnitGroups": 3}]},
        ),
    )
    respx.get("https://dhis2.example/api/dashboards").mock(
        return_value=httpx.Response(200, json={"dashboards": [{"id": "dash1", "name": "Main", "dashboardItems": 8}]}),
    )
    respx.get("https://dhis2.example/api/visualizations").mock(
        return_value=httpx.Response(
            200, json={"visualizations": [{"id": "v1", "name": "Chart", "dataDimensionItems": 2}]}
        ),
    )
    respx.get("https://dhis2.example/api/indicators").mock(
        return_value=httpx.Response(
            200,
            json={
                "indicators": [
                    {"id": "ind1", "name": "ANC1", "numerator": "#{DEancVisit1}", "denominator": "1"},
                ],
            },
        ),
    )
    level_list = org_unit_levels if org_unit_levels is not None else [1, 2]
    ou_rows: list[dict[str, Any]] = []
    for idx, level in enumerate(level_list):
        parent = None if level == 1 else {"id": "root"}
        ou_rows.append({"id": f"ou{idx}", "name": f"OU{idx}", "level": level, "parent": parent})
    respx.get("https://dhis2.example/api/organisationUnits").mock(
        return_value=httpx.Response(200, json={"organisationUnits": ou_rows}),
    )

    # programStages — used by probe_program_stages_without_data_elements and
    # probe_program_indicators_orphan_refs (the latter only reads `id`).
    ps_rows: list[dict[str, Any]] = [
        {"id": "ps1", "name": "ANC visit", "programStageDataElements": 2},
    ]
    ps_rows.extend(
        {"id": f"orphanPs{i}", "name": f"OrphanPS{i}", "programStageDataElements": 0}
        for i in range(orphan_program_stages)
    )
    respx.get("https://dhis2.example/api/programStages").mock(
        return_value=httpx.Response(200, json={"programStages": ps_rows}),
    )

    # programIndicators — used by both expression + orphan-ref probes.
    pi_rows: list[dict[str, Any]] = [
        {
            "id": "pi1",
            "name": "ANC coverage",
            "expression": "#{ps1.DEancVisit1}",
            "filter": "",
        },
    ]
    pi_rows.extend(
        {"id": f"emptyPi{i}", "name": f"EmptyPI{i}", "expression": "", "filter": ""}
        for i in range(empty_program_indicators)
    )
    # UID refs are strictly 11 chars matching `[A-Za-z][A-Za-z0-9]{10}`. Neither
    # `ghostStage1` nor `ghostDeUid0` sit in the mocked programStages /
    # dataElements fixtures, so the regex matches and flags the ref as orphan.
    pi_rows.extend(
        {
            "id": f"orphanRefPi{i}",
            "name": f"OrphanRefPI{i}",
            "expression": "#{ghostStage1.ghostDeUid0}",
            "filter": "",
        }
        for i in range(orphan_ref_program_indicators)
    )
    respx.get("https://dhis2.example/api/programIndicators").mock(
        return_value=httpx.Response(200, json={"programIndicators": pi_rows}),
    )

    # users — used by probe_users_without_user_roles.
    user_rows: list[dict[str, Any]] = [{"id": "admin1", "username": "admin", "userRoles": 2}]
    user_rows.extend(
        {"id": f"noRoleUser{i}", "username": f"user{i}", "userRoles": 0} for i in range(users_without_roles)
    )
    respx.get("https://dhis2.example/api/users").mock(
        return_value=httpx.Response(200, json={"users": user_rows}),
    )

    # validationRules — used by probe_validation_rules_without_expressions.
    vr_rows: list[dict[str, Any]] = [
        {
            "id": "vr1",
            "name": "Valid rule",
            "leftSide": {"expression": "#{dsAncTotal}"},
            "rightSide": {"expression": "#{dsAncTarget}"},
        },
    ]
    vr_rows.extend(
        {
            "id": f"brokenVr{i}",
            "name": f"Broken{i}",
            "leftSide": {"expression": ""},
            "rightSide": {"expression": "#{dsAncTarget}"},
        }
        for i in range(broken_validation_rules)
    )
    respx.get("https://dhis2.example/api/validationRules").mock(
        return_value=httpx.Response(200, json={"validationRules": vr_rows}),
    )


def _mock_integrity(summary: dict[str, object] | None) -> None:
    """Canned `/api/dataIntegrity/summary` — pass None for the empty-response skip case."""
    respx.get("https://dhis2.example/api/dataIntegrity/summary").mock(
        return_value=httpx.Response(200, json=summary if summary is not None else {}),
    )


def test_plugin_descriptor() -> None:
    """Plugin registers under the right name + has a description."""
    assert plugin.name == "doctor"
    assert "probe" in plugin.description.lower() or "check" in plugin.description.lower()


@respx.mock
async def test_default_runs_metadata_and_integrity_only(profile: Profile) -> None:
    """Default (no categories arg) runs metadata + integrity but NOT bugs."""
    _mock_preamble()
    _mock_metadata_probes()
    _mock_integrity({"check_a": {"count": 0, "severity": "WARN"}})
    report = await service.run_doctor(profile)
    # Every probe should be in metadata or integrity, none in bugs.
    categories = {probe.category for probe in report.probes}
    assert "bugs" not in categories
    assert categories <= {"metadata", "integrity"}


@respx.mock
async def test_metadata_probe_flags_orphan_data_elements(profile: Profile) -> None:
    """Orphan aggregate DEs → `warn` with UIDs listed in `offending_uids`."""
    _mock_preamble()
    _mock_metadata_probes(orphan_data_elements=3)
    report = await service.run_doctor(profile, categories=("metadata",))
    probe = next(p for p in report.probes if p.name == "dataElements")
    assert probe.status == "warn"
    assert probe.offending_uids == ["orphanDe0", "orphanDe1", "orphanDe2"]


@respx.mock
async def test_metadata_probe_passes_when_no_orphans(profile: Profile) -> None:
    """All DEs have dataSetElements → `pass`, empty offending_uids."""
    _mock_preamble()
    _mock_metadata_probes()
    report = await service.run_doctor(profile, categories=("metadata",))
    probe = next(p for p in report.probes if p.name == "dataElements")
    assert probe.status == "pass"
    assert probe.offending_uids == []


@respx.mock
async def test_metadata_probe_flags_program_stages_without_data_elements(profile: Profile) -> None:
    """Program stages with zero programStageDataElements → `warn` with UIDs."""
    _mock_preamble()
    _mock_metadata_probes(orphan_program_stages=2)
    report = await service.run_doctor(profile, categories=("metadata",))
    probe = next(p for p in report.probes if p.name == "programStages:dataElements")
    assert probe.status == "warn"
    assert probe.offending_uids == ["orphanPs0", "orphanPs1"]


@respx.mock
async def test_metadata_probe_flags_program_indicators_without_expression(profile: Profile) -> None:
    """Program indicators with empty `expression` → `warn` with UIDs."""
    _mock_preamble()
    _mock_metadata_probes(empty_program_indicators=2)
    report = await service.run_doctor(profile, categories=("metadata",))
    probe = next(p for p in report.probes if p.name == "programIndicators:expression")
    assert probe.status == "warn"
    assert probe.offending_uids == ["emptyPi0", "emptyPi1"]


@respx.mock
async def test_metadata_probe_flags_program_indicators_with_orphan_refs(profile: Profile) -> None:
    """PIs referencing unknown stage+DE UIDs → `warn`; valid refs stay on pass."""
    _mock_preamble()
    _mock_metadata_probes(orphan_ref_program_indicators=1)
    report = await service.run_doctor(profile, categories=("metadata",))
    probe = next(p for p in report.probes if p.name == "programIndicators:orphanRefs")
    assert probe.status == "warn"
    assert probe.offending_uids == ["orphanRefPi0"]


@respx.mock
async def test_metadata_probe_flags_users_without_user_roles(profile: Profile) -> None:
    """Users with empty userRoles → `warn` with UIDs."""
    _mock_preamble()
    _mock_metadata_probes(users_without_roles=2)
    report = await service.run_doctor(profile, categories=("metadata",))
    probe = next(p for p in report.probes if p.name == "users:userRoles")
    assert probe.status == "warn"
    assert probe.offending_uids == ["noRoleUser0", "noRoleUser1"]


@respx.mock
async def test_metadata_probe_flags_validation_rules_without_expressions(profile: Profile) -> None:
    """Validation rules with empty leftSide or rightSide expression → `warn`."""
    _mock_preamble()
    _mock_metadata_probes(broken_validation_rules=1)
    report = await service.run_doctor(profile, categories=("metadata",))
    probe = next(p for p in report.probes if p.name == "validationRules:expressions")
    assert probe.status == "warn"
    assert probe.offending_uids == ["brokenVr0"]


@respx.mock
async def test_metadata_probe_hierarchy_depth_flags_level_gaps(profile: Profile) -> None:
    """Distinct levels {1, 2, 4} — level 3 missing → `warn` with a gap message."""
    _mock_preamble()
    _mock_metadata_probes(org_unit_levels=[1, 2, 4])
    report = await service.run_doctor(profile, categories=("metadata",))
    probe = next(p for p in report.probes if p.name == "organisationUnits:hierarchyDepth")
    assert probe.status == "warn"
    assert "missing level" in probe.message
    assert "3" in probe.message


@respx.mock
async def test_metadata_probe_hierarchy_depth_flags_absurd_depth(profile: Profile) -> None:
    """Depth > 10 → `warn` regardless of contiguity."""
    _mock_preamble()
    _mock_metadata_probes(org_unit_levels=list(range(1, 13)))
    report = await service.run_doctor(profile, categories=("metadata",))
    probe = next(p for p in report.probes if p.name == "organisationUnits:hierarchyDepth")
    assert probe.status == "warn"
    assert "12 levels deep" in probe.message


@respx.mock
async def test_metadata_probe_hierarchy_depth_pass_on_normal_tree(profile: Profile) -> None:
    """Contiguous 1..4 hierarchy → `pass`."""
    _mock_preamble()
    _mock_metadata_probes(org_unit_levels=[1, 2, 3, 4])
    report = await service.run_doctor(profile, categories=("metadata",))
    probe = next(p for p in report.probes if p.name == "organisationUnits:hierarchyDepth")
    assert probe.status == "pass"


@respx.mock
async def test_metadata_probe_category_combos_excludes_default(profile: Profile) -> None:
    """The built-in `default` category combo has 0 categories — don't flag it."""
    _mock_preamble()
    _mock_metadata_probes()
    report = await service.run_doctor(profile, categories=("metadata",))
    probe = next(p for p in report.probes if p.name == "categoryCombos")
    assert probe.status == "pass"  # only the non-default one is counted


@respx.mock
async def test_integrity_empty_response_is_skip(profile: Profile) -> None:
    """DHIS2's dataIntegrity hasn't been run yet → `skip` with a hint."""
    _mock_preamble()
    _mock_integrity(None)  # {} response
    report = await service.run_doctor(profile, categories=("integrity",))
    assert len(report.probes) == 1
    assert report.probes[0].status == "skip"
    assert "maintenance dataintegrity run" in report.probes[0].message


@respx.mock
async def test_integrity_converts_each_check_to_a_probe(profile: Profile) -> None:
    """Each DHIS2 check becomes one `ProbeResult`; 0 issues → pass, >0 → warn."""
    _mock_preamble()
    _mock_integrity(
        {
            "dashboards_no_items": {"count": 0, "severity": "WARN"},
            "orgunits_no_parent": {"count": 5, "severity": "ERROR"},
        }
    )
    report = await service.run_doctor(profile, categories=("integrity",))
    by_name = {p.name: p for p in report.probes}
    assert by_name["integrity:dashboards_no_items"].status == "pass"
    assert by_name["integrity:orgunits_no_parent"].status == "warn"
    assert "5 issue" in by_name["integrity:orgunits_no_parent"].message
    assert "severity=ERROR" in by_name["integrity:orgunits_no_parent"].message


@respx.mock
async def test_doctor_refuses_pre_v41_dhis2(profile: Profile) -> None:
    """Pre-2.41 DHIS2 → connect fails up-front; doctor never runs.

    The workspace ships generated trees for v41, v42, v43. A reported
    DHIS2 below 2.41 has no compatible generated module and no lower
    fallback to choose from, so `Dhis2Client.connect()` raises
    `UnsupportedVersionError` before the doctor's probes get a chance.
    """
    from dhis2w_client.errors import UnsupportedVersionError

    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text=""))
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.40.5"}),
    )
    with pytest.raises(UnsupportedVersionError, match="2.40.5"):
        await service.run_doctor(profile, categories=("bugs",))


@respx.mock
async def test_bugs_rawdata_warns_when_fix_appears_upstream(profile: Profile) -> None:
    """BUGS #1 — if /api/analytics/rawData stops 404'ing, bug may be fixed upstream."""
    _mock_preamble()
    _mock_bugs_pass()
    respx.get("https://dhis2.example/api/analytics/rawData").mock(
        return_value=httpx.Response(200, json={"rows": []}),
    )
    report = await service.run_doctor(profile, categories=("bugs",))
    probe = next(p for p in report.probes if p.name == "analytics-rawdata-json-suffix")
    assert probe.status == "warn"
    assert probe.bugs_ref == "BUGS.md #1"


@respx.mock
def test_cli_metadata_subcommand_runs_only_metadata() -> None:
    """`dhis2 doctor metadata` doesn't hit integrity or bugs endpoints."""
    _mock_preamble()
    _mock_metadata_probes(orphan_data_elements=1)
    result = CliRunner().invoke(build_app(), ["doctor", "metadata"])
    # Exit 0 even with warn — only fail changes exit code.
    assert result.exit_code == 0, result.output
    # The integrity endpoint should NOT have been called — prove it via the category field in JSON.
    json_result = CliRunner().invoke(build_app(), ["--json", "doctor", "metadata"])
    assert '"category": "metadata"' in json_result.output
    assert '"category": "integrity"' not in json_result.output
    assert '"category": "bugs"' not in json_result.output


@respx.mock
def test_cli_bugs_subcommand_runs_only_bugs() -> None:
    """`dhis2 doctor bugs` only runs bug-drift probes."""
    _mock_preamble()
    _mock_bugs_pass()
    result = CliRunner().invoke(build_app(), ["--json", "doctor", "bugs"])
    assert result.exit_code == 0, result.output
    assert '"category": "bugs"' in result.output
    assert '"category": "metadata"' not in result.output


@respx.mock
def test_cli_all_flag_runs_every_category() -> None:
    """`dhis2 doctor --all` includes bugs."""
    _mock_preamble()
    _mock_bugs_pass()
    _mock_metadata_probes()
    _mock_integrity({})
    result = CliRunner().invoke(build_app(), ["--json", "doctor", "--all"])
    assert result.exit_code == 0, result.output
    assert '"category": "bugs"' in result.output
    assert '"category": "metadata"' in result.output


@respx.mock
def test_cli_default_is_metadata_plus_integrity_no_bugs() -> None:
    """`dhis2 doctor` (no sub-command, no --all) runs metadata + integrity, skips bugs."""
    _mock_preamble()
    _mock_metadata_probes()
    _mock_integrity({})
    result = CliRunner().invoke(build_app(), ["--json", "doctor"])
    assert result.exit_code == 0, result.output
    assert '"category": "metadata"' in result.output
    assert '"category": "bugs"' not in result.output
