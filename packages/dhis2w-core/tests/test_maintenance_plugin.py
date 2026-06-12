"""Unit tests for the `maintenance` plugin (service + CLI wiring via respx)."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
import respx
from dhis2w_cli.main import build_app
from dhis2w_core.profile import Profile
from dhis2w_core.v42.plugins.maintenance import service
from dhis2w_core.v42.plugins.maintenance.service import SoftDeleteTarget
from typer.testing import CliRunner


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Install raw-env profile so `profile_from_env()` resolves without TOML."""
    for key in ("DHIS2_PROFILE", "DHIS2_URL", "DHIS2_PAT", "DHIS2_USERNAME", "DHIS2_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DHIS2_URL", "https://dhis2.example")
    monkeypatch.setenv("DHIS2_PAT", "test-token")
    yield


@pytest.fixture
def profile() -> Profile:
    return Profile(base_url="https://dhis2.example", auth="pat", token="test-token")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _mock_system_info() -> None:
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"})
    )
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text=""))


@respx.mock
async def test_list_task_types_sorts_keys(profile: Profile) -> None:
    """List task types sorts keys."""
    _mock_system_info()
    respx.get("https://dhis2.example/api/system/tasks").mock(
        return_value=httpx.Response(
            200,
            json={"ANALYTICS_TABLE": {}, "HOUSEKEEPING": {}, "DATA_INTEGRITY": {}},
        )
    )
    types = await service.list_task_types(profile)
    assert types == ["ANALYTICS_TABLE", "DATA_INTEGRITY", "HOUSEKEEPING"]


@respx.mock
async def test_list_task_ids_sorts_uids(profile: Profile) -> None:
    """List task ids sorts uids."""
    _mock_system_info()
    respx.get("https://dhis2.example/api/system/tasks/ANALYTICS_TABLE").mock(
        return_value=httpx.Response(200, json={"ccc11111aaa": [], "aaa11111bbb": [], "bbb11111ccc": []})
    )
    ids = await service.list_task_ids(profile, "ANALYTICS_TABLE")
    assert ids == ["aaa11111bbb", "bbb11111ccc", "ccc11111aaa"]


@respx.mock
async def test_get_task_notifications_reverses_order(profile: Profile) -> None:
    """DHIS2 returns notifications newest-first; service reverses to chronological."""
    _mock_system_info()
    respx.get("https://dhis2.example/api/system/tasks/ANALYTICS_TABLE/abc").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"message": "completed", "completed": True, "time": "2026-04-19T08:00:10", "uid": "n2"},
                {"message": "started", "completed": False, "time": "2026-04-19T08:00:01", "uid": "n1"},
            ],
        )
    )
    notifications = await service.get_task_notifications(profile, "ANALYTICS_TABLE", "abc")
    assert [n.message for n in notifications] == ["started", "completed"]
    assert notifications[-1].completed


@respx.mock
async def test_clear_cache_posts_to_maintenance(profile: Profile) -> None:
    """Clear cache posts to maintenance."""
    _mock_system_info()
    route = respx.post("https://dhis2.example/api/maintenance/cache").mock(
        return_value=httpx.Response(204, content=b"")
    )
    await service.clear_cache(profile)
    assert route.called


@respx.mock
@pytest.mark.parametrize(
    ("target", "endpoint"),
    [
        (SoftDeleteTarget.DATA_VALUES, "/api/maintenance/softDeletedDataValueRemoval"),
        (SoftDeleteTarget.EVENTS, "/api/maintenance/softDeletedEventRemoval"),
        (SoftDeleteTarget.ENROLLMENTS, "/api/maintenance/softDeletedEnrollmentRemoval"),
        (SoftDeleteTarget.TRACKED_ENTITIES, "/api/maintenance/softDeletedTrackedEntityRemoval"),
    ],
)
async def test_remove_soft_deleted_hits_correct_endpoint(
    profile: Profile, target: SoftDeleteTarget, endpoint: str
) -> None:
    """Remove soft deleted hits correct endpoint."""
    _mock_system_info()
    route = respx.post(f"https://dhis2.example{endpoint}").mock(return_value=httpx.Response(204, content=b""))
    await service.remove_soft_deleted(profile, target)
    assert route.called


@respx.mock
async def test_list_dataintegrity_checks(profile: Profile) -> None:
    """List dataintegrity checks."""
    _mock_system_info()
    respx.get("https://dhis2.example/api/dataIntegrity").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"name": "check_a", "severity": "WARNING", "section": "Org units"},
                {"name": "check_b", "severity": "SEVERE"},
            ],
        )
    )
    checks = await service.list_dataintegrity_checks(profile)
    assert [c.name for c in checks] == ["check_a", "check_b"]
    assert checks[0].severity == "WARNING"


@respx.mock
async def test_run_dataintegrity_posts_summary_endpoint(profile: Profile) -> None:
    """Run dataintegrity posts summary endpoint."""
    _mock_system_info()
    route = respx.post("https://dhis2.example/api/dataIntegrity").mock(
        return_value=httpx.Response(
            200,
            json={
                "httpStatus": "OK",
                "status": "OK",
                "response": {"id": "taskUid0001", "jobType": "DATA_INTEGRITY"},
            },
        )
    )
    envelope = await service.run_dataintegrity(profile, checks=["check_a"])
    assert route.called
    assert route.calls.last.request.url.params.get_list("checks") == ["check_a"]
    assert envelope.response is not None
    assert envelope.response.get("id") == "taskUid0001"


@respx.mock
async def test_run_dataintegrity_details_hits_details_path(profile: Profile) -> None:
    """Run dataintegrity details hits details path."""
    _mock_system_info()
    route = respx.post("https://dhis2.example/api/dataIntegrity/details").mock(
        return_value=httpx.Response(
            200,
            json={"status": "OK", "response": {"id": "detailsTask2", "jobType": "DATA_INTEGRITY_DETAILS"}},
        )
    )
    envelope = await service.run_dataintegrity(profile, checks=["check_a"], details=True)
    assert route.called
    assert envelope.response is not None
    assert envelope.response.get("id") == "detailsTask2"


@respx.mock
async def test_get_dataintegrity_summary_parses_report(profile: Profile) -> None:
    """Get dataintegrity summary parses report."""
    _mock_system_info()
    respx.get("https://dhis2.example/api/dataIntegrity/summary").mock(
        return_value=httpx.Response(
            200,
            json={
                "check_a": {"name": "check_a", "severity": "WARNING", "count": 3},
                "check_b": {"name": "check_b", "severity": "SEVERE", "count": 0},
            },
        )
    )
    report = await service.get_dataintegrity_summary(profile)
    assert sorted(report.results.keys()) == ["check_a", "check_b"]
    assert report.results["check_a"].count == 3


def test_cli_maintenance_is_mounted(runner: CliRunner) -> None:
    """`d2w maintenance --help` should exist and enumerate task/cache/cleanup/dataintegrity."""
    result = runner.invoke(build_app(), ["maintenance", "--help"])
    assert result.exit_code == 0
    for expected in ("task", "cache", "cleanup", "dataintegrity"):
        assert expected in result.output


@respx.mock
def test_cli_cache_clear_round_trips(runner: CliRunner) -> None:
    """Cli cache clear round trips."""
    _mock_system_info()
    respx.post("https://dhis2.example/api/maintenance/cache").mock(return_value=httpx.Response(204, content=b""))
    result = runner.invoke(build_app(), ["maintenance", "cache"])
    assert result.exit_code == 0
    assert "caches cleared" in result.output


@respx.mock
def test_cli_dataintegrity_run_watch_streams_to_completion(runner: CliRunner) -> None:
    """`--watch` pulls jobType/id from the response envelope and polls until completed=true."""
    _mock_system_info()
    respx.post("https://dhis2.example/api/dataIntegrity").mock(
        return_value=httpx.Response(
            200,
            json={
                "httpStatus": "OK",
                "status": "OK",
                "response": {
                    "id": "watchTask01",
                    "jobType": "DATA_INTEGRITY",
                    "responseType": "JobConfigurationWebMessageResponse",
                },
            },
        )
    )
    respx.get("https://dhis2.example/api/system/tasks/DATA_INTEGRITY/watchTask01").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "message": "done",
                    "completed": True,
                    "level": "INFO",
                    "time": "2026-04-19T08:00:10",
                    "uid": "final",
                },
                {
                    "message": "started",
                    "completed": False,
                    "level": "INFO",
                    "time": "2026-04-19T08:00:01",
                    "uid": "begin",
                },
            ],
        )
    )
    result = runner.invoke(
        build_app(),
        ["maintenance", "dataintegrity", "run", "check_a", "--watch", "--interval", "0.01", "--timeout", "5"],
    )
    assert result.exit_code == 0
    assert "watching DATA_INTEGRITY/watchTask01" in result.output
    assert "started" in result.output
    assert "done" in result.output


@respx.mock
def test_cli_dataintegrity_list_renders_table(runner: CliRunner) -> None:
    """Cli dataintegrity list renders table."""
    _mock_system_info()
    respx.get("https://dhis2.example/api/dataIntegrity").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"name": "check_orgunit", "severity": "WARNING", "section": "Org units"},
            ],
        )
    )
    result = runner.invoke(build_app(), ["maintenance", "dataintegrity", "list"])
    assert result.exit_code == 0
    assert "check_orgunit" in result.output
    assert "WARNING" in result.output
