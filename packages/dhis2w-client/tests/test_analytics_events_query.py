"""Tests for `Dhis2Client.analytics.event_query` / `.enrollment_query` — event analytics reads."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import respx
from dhis2w_client import BasicAuth, Dhis2ApiError, Dhis2Client


def _auth() -> BasicAuth:
    """Throwaway auth for test clients."""
    return BasicAuth(username="a", password="b")


def _grid() -> dict[str, object]:
    """Canned event-analytics Grid envelope."""
    return {
        "headers": [{"name": "psi", "column": "Event"}, {"name": "value", "column": "value"}],
        "rows": [["evUid000001", "42"]],
        "metaData": {"items": {}, "dimensions": {}},
    }


@respx.mock
async def test_event_query_builds_repeated_dimensions_and_parses_grid(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`event_query(...)` repeats dimension/filter, sends stage + dates, validates a `Grid`."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/analytics/events/query/progUid0001.json").mock(
        return_value=httpx.Response(200, json=_grid()),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        grid = await client.analytics.event_query(
            "progUid0001",
            stage="psUidAAA001",
            dimension=["pe:LAST_12_MONTHS", "ou:ImspTQPwCqd", "deUid000001"],
            filter=["deUid000002:GT:5"],
            start_date="2024-01-01",
            end_date="2024-12-31",
            output_type="EVENT",
            event_status="COMPLETED",
            program_status="ACTIVE",
            page=1,
            page_size=100,
            extra_params={"aggregationType": "COUNT"},
        )
    finally:
        await client.close()

    params = route.calls.last.request.url.params
    assert params.get_list("dimension") == ["pe:LAST_12_MONTHS", "ou:ImspTQPwCqd", "deUid000001"]
    assert params.get_list("filter") == ["deUid000002:GT:5"]
    assert params["stage"] == "psUidAAA001"
    assert params["startDate"] == "2024-01-01"
    assert params["endDate"] == "2024-12-31"
    assert params["outputType"] == "EVENT"
    assert params["eventStatus"] == "COMPLETED"
    assert params["programStatus"] == "ACTIVE"
    assert params["page"] == "1"
    assert params["pageSize"] == "100"
    assert params["aggregationType"] == "COUNT"
    assert grid.headers and grid.headers[0].name == "psi"
    assert grid.rows == [["evUid000001", "42"]]


@respx.mock
async def test_enrollment_query_hits_enrollments_endpoint(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`enrollment_query(...)` targets the enrollments query path and carries no `stage`."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/analytics/enrollments/query/progUid0001.json").mock(
        return_value=httpx.Response(200, json=_grid()),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        grid = await client.analytics.enrollment_query(
            "progUid0001",
            dimension="pe:LAST_12_MONTHS",
            program_status="COMPLETED",
        )
    finally:
        await client.close()

    params = route.calls.last.request.url.params
    assert params.get_list("dimension") == ["pe:LAST_12_MONTHS"]
    assert params["programStatus"] == "COMPLETED"
    assert "stage" not in params
    assert grid.rows == [["evUid000001", "42"]]


@respx.mock
async def test_event_query_omits_none_params(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """A bare event query sends only the program in the path, no query string."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/analytics/events/query/progUid0001.json").mock(
        return_value=httpx.Response(200, json={"headers": [], "rows": []}),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.analytics.event_query("progUid0001")
    finally:
        await client.close()

    assert str(route.calls.last.request.url.params) == ""


@respx.mock
async def test_event_query_raises_on_error(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """A 4xx / 5xx surfaces as `Dhis2ApiError`."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/analytics/events/query/progUid0001.json").mock(
        return_value=httpx.Response(409, json={"message": "bad dimension"}),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        with pytest.raises(Dhis2ApiError):
            await client.analytics.event_query("progUid0001", dimension="bad:dim")
    finally:
        await client.close()
