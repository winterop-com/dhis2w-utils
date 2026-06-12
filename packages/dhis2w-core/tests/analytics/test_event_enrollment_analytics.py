"""Route + URL tests for event / enrollment analytics CLI + service."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
import respx
from dhis2w_cli.main import build_app
from dhis2w_core.profile import Profile
from dhis2w_core.v42.plugins.analytics import service
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


def _mock_system_info() -> None:
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.4"})
    )
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text=""))


def _mock_event_query_body() -> dict[str, object]:
    return {
        "headers": [{"name": "psi", "column": "Event"}, {"name": "ou", "column": "Organisation unit"}],
        "rows": [["evt1", "ouX"], ["evt2", "ouY"]],
        "metaData": {"items": {}, "dimensions": {}},
        "width": 2,
        "height": 2,
    }


@respx.mock
async def test_query_events_hits_query_path_by_default(profile: Profile) -> None:
    """Query events hits query path by default."""
    _mock_system_info()
    route = respx.get("https://dhis2.example/api/analytics/events/query/progUID").mock(
        return_value=httpx.Response(200, json=_mock_event_query_body())
    )
    response = await service.query_events(
        profile,
        program="progUID",
        dimensions=["pe:LAST_12_MONTHS", "ou:ouRoot"],
        stage="stageUID",
    )
    assert route.called
    request = route.calls.last.request
    assert request.url.params.get_list("dimension") == ["pe:LAST_12_MONTHS", "ou:ouRoot"]
    assert request.url.params["stage"] == "stageUID"
    assert response.rows is not None
    assert len(response.rows) == 2


@respx.mock
async def test_query_events_aggregate_mode_uses_aggregate_path(profile: Profile) -> None:
    """Query events aggregate mode uses aggregate path."""
    _mock_system_info()
    route = respx.get("https://dhis2.example/api/analytics/events/aggregate/progUID").mock(
        return_value=httpx.Response(200, json=_mock_event_query_body())
    )
    await service.query_events(
        profile,
        program="progUID",
        mode="aggregate",
        dimensions=["dx:dxUID"],
    )
    assert route.called


async def test_query_events_rejects_unknown_mode(profile: Profile) -> None:
    """Query events rejects unknown mode."""
    with pytest.raises(ValueError, match="unknown event analytics mode"):
        await service.query_events(profile, program="progUID", mode="bogus")


@respx.mock
async def test_query_enrollments_hits_enrollments_query_path(profile: Profile) -> None:
    """Query enrollments hits enrollments query path."""
    _mock_system_info()
    route = respx.get("https://dhis2.example/api/analytics/enrollments/query/progUID").mock(
        return_value=httpx.Response(200, json=_mock_event_query_body())
    )
    response = await service.query_enrollments(
        profile,
        program="progUID",
        dimensions=["pe:THIS_YEAR"],
        start_date="2026-01-01",
        end_date="2026-06-30",
    )
    assert route.called
    request = route.calls.last.request
    assert request.url.params["startDate"] == "2026-01-01"
    assert request.url.params["endDate"] == "2026-06-30"
    assert response.rows is not None
    assert len(response.rows) == 2


@respx.mock
def test_cli_events_query_round_trips() -> None:
    """Cli events query round trips."""
    _mock_system_info()
    respx.get("https://dhis2.example/api/analytics/events/query/progUID").mock(
        return_value=httpx.Response(200, json=_mock_event_query_body())
    )
    runner = CliRunner()
    result = runner.invoke(
        build_app(),
        [
            "--json",
            "analytics",
            "events",
            "query",
            "progUID",
            "--dim",
            "pe:LAST_12_MONTHS",
            "--dim",
            "ou:ouRoot",
            "--stage",
            "stageUID",
        ],
    )
    assert result.exit_code == 0, result.output
    assert '"rows"' in result.output
    assert '"evt1"' in result.output


@respx.mock
def test_cli_events_query_rejects_bad_mode() -> None:
    """Cli events query rejects bad mode."""
    _mock_system_info()
    runner = CliRunner()
    result = runner.invoke(
        build_app(),
        ["analytics", "events", "query", "progUID", "--mode", "bogus"],
    )
    assert result.exit_code == 1
    assert "unknown event analytics mode" in result.output


@respx.mock
def test_cli_enrollments_query_round_trips() -> None:
    """Cli enrollments query round trips."""
    _mock_system_info()
    respx.get("https://dhis2.example/api/analytics/enrollments/query/progUID").mock(
        return_value=httpx.Response(200, json=_mock_event_query_body())
    )
    runner = CliRunner()
    result = runner.invoke(
        build_app(),
        ["--json", "analytics", "enrollments", "query", "progUID", "--dim", "pe:THIS_YEAR"],
    )
    assert result.exit_code == 0, result.output
    assert '"rows"' in result.output
