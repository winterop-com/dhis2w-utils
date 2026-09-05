"""Unit tests for `Dhis2Client.tracker` reads — respx-mocked `/api/tracker/*` queries."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx
from dhis2w_client import BasicAuth, Dhis2ApiError, Dhis2Client


def _auth() -> BasicAuth:
    """Throwaway auth for test clients."""
    return BasicAuth(username="a", password="b")


def _page(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Standard tracker page envelope with rows under `instances`."""
    return {"page": 1, "pageSize": 50, "total": len(rows), "instances": rows}


@respx.mock
async def test_tracked_entities_builds_repeated_params_and_returns_envelope(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`tracked_entities(...)` repeats orgUnit/trackedEntity/filter and maps status -> programStatus."""
    mock_system_info(server_version)
    envelope = _page([{"trackedEntity": "teUid000001"}])
    route = respx.get("https://dhis2.example/api/tracker/trackedEntities").mock(
        return_value=httpx.Response(200, json=envelope),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.tracker.tracked_entities(
            program="progUid0001",
            tracked_entity_type="tetUidAAA01",
            org_unit=["ouUidAAA001", "ouUidBBB002"],
            ou_mode="DESCENDANTS",
            tracked_entity="teUid000001",
            status="ACTIVE",
            fields="trackedEntity,attributes[attribute,value]",
            filter=["attrUid00001:eq:Jane", "attrUid00002:like:Do"],
            page=1,
            page_size=50,
            updated_after="2024-06-01",
        )
    finally:
        await client.close()

    params = route.calls.last.request.url.params
    assert params["program"] == "progUid0001"
    assert params["trackedEntityType"] == "tetUidAAA01"
    assert params.get_list("orgUnit") == ["ouUidAAA001", "ouUidBBB002"]
    assert params["ouMode"] == "DESCENDANTS"
    assert "orgUnitMode" not in params
    assert params.get_list("trackedEntity") == ["teUid000001"]
    assert params["programStatus"] == "ACTIVE"
    assert params["fields"] == "trackedEntity,attributes[attribute,value]"
    assert params.get_list("filter") == ["attrUid00001:eq:Jane", "attrUid00002:like:Do"]
    assert params["page"] == "1"
    assert params["pageSize"] == "50"
    assert params["updatedAfter"] == "2024-06-01"
    assert result["instances"] == [{"trackedEntity": "teUid000001"}]


@respx.mock
async def test_enrollments_maps_status_and_repeats_ids(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`enrollments(...)` maps status -> programStatus and repeats enrollment/trackedEntity."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/tracker/enrollments").mock(
        return_value=httpx.Response(200, json=_page([{"enrollment": "enrUid00001"}])),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.tracker.enrollments(
            program="progUid0001",
            org_unit="ouUidAAA001",
            tracked_entity=["teUid000001", "teUid000002"],
            enrollment="enrUid00001",
            status="COMPLETED",
        )
    finally:
        await client.close()

    params = route.calls.last.request.url.params
    assert params["program"] == "progUid0001"
    assert params["orgUnit"] == "ouUidAAA001"
    assert params.get_list("trackedEntity") == ["teUid000001", "teUid000002"]
    assert params.get_list("enrollment") == ["enrUid00001"]
    assert params["programStatus"] == "COMPLETED"
    assert result["instances"] == [{"enrollment": "enrUid00001"}]


@respx.mock
async def test_events_maps_status_stage_and_occurred_after(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`events(...)` sends programStage/occurredAfter, maps status -> status, and rides the mode on orgUnitMode."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/tracker/events").mock(
        return_value=httpx.Response(200, json=_page([{"event": "evUid000001"}])),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.tracker.events(
            program="progUid0001",
            program_stage="psUidAAA001",
            org_unit="ouUidAAA001",
            ou_mode="DESCENDANTS",
            enrollment="enrUid00001",
            status="COMPLETED",
            occurred_after="2024-01-01",
            updated_after="2024-06-01",
        )
    finally:
        await client.close()

    params = route.calls.last.request.url.params
    assert params["program"] == "progUid0001"
    assert params["programStage"] == "psUidAAA001"
    assert params["orgUnit"] == "ouUidAAA001"
    assert params["orgUnitMode"] == "DESCENDANTS"
    assert "ouMode" not in params
    assert params.get_list("enrollment") == ["enrUid00001"]
    assert params["status"] == "COMPLETED"
    assert "programStatus" not in params
    assert params["occurredAfter"] == "2024-01-01"
    assert params["updatedAfter"] == "2024-06-01"
    assert result["instances"] == [{"event": "evUid000001"}]


@respx.mock
async def test_tracked_entities_omits_none_params(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """A bare read sends no query string; unset params never reach the wire."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/tracker/trackedEntities").mock(
        return_value=httpx.Response(200, json=_page([])),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.tracker.tracked_entities()
    finally:
        await client.close()

    assert str(route.calls.last.request.url.params) == ""


@respx.mock
async def test_events_forwards_extra_params(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """`extra_params` covers the rest of the surface (order, occurredBefore, ...)."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/tracker/events").mock(
        return_value=httpx.Response(200, json=_page([])),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.tracker.events(program="progUid0001", extra_params={"order": "occurredAt:desc"})
    finally:
        await client.close()

    assert route.calls.last.request.url.params["order"] == "occurredAt:desc"


@respx.mock
async def test_tracked_entities_raises_on_error(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """A 4xx / 5xx surfaces as `Dhis2ApiError`."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/tracker/trackedEntities").mock(
        return_value=httpx.Response(409, json={"message": "bad request"}),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        with pytest.raises(Dhis2ApiError):
            await client.tracker.tracked_entities(program="progUid0001")
    finally:
        await client.close()
