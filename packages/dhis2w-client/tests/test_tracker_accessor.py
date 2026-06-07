"""Unit tests for `Dhis2Client.tracker` — respx-mocked authoring flows."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import respx
from dhis2w_client import BasicAuth, Dhis2Client


def _auth() -> BasicAuth:
    """Throwaway auth for test clients."""
    return BasicAuth(username="a", password="b")


def _ok_response() -> dict[str, Any]:
    """Standard WebMessage envelope for a successful tracker POST."""
    return {
        "httpStatus": "OK",
        "httpStatusCode": 200,
        "status": "OK",
        "response": {"status": "OK", "stats": {"created": 1, "total": 1}},
    }


# ---- TrackerAccessor.register ---------------------------------------------


@respx.mock
async def test_register_posts_te_with_enrollment_and_returns_uids(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`register` POSTs a `{trackedEntities: [{...enrollments: [...]}]}` bundle."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/tracker").mock(return_value=httpx.Response(200, json=_ok_response()))

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.tracker.register(
            program="progUid0001",
            org_unit="ouUidAAA001",
            tracked_entity_type="tetUidAAA01",
            attributes={"attrUid00001": "Jane", "attrUid00002": "Doe"},
            enrolled_at="2024-06-01",
        )
    finally:
        await client.close()

    body = json.loads(route.calls.last.request.content)
    assert "trackedEntities" in body
    tes = body["trackedEntities"]
    assert len(tes) == 1
    te = tes[0]
    assert te["orgUnit"] == "ouUidAAA001"
    assert te["trackedEntityType"] == "tetUidAAA01"
    assert {a["attribute"] for a in te["attributes"]} == {"attrUid00001", "attrUid00002"}
    assert len(te["enrollments"]) == 1
    enrollment = te["enrollments"][0]
    assert enrollment["program"] == "progUid0001"
    assert enrollment["enrolledAt"] == "2024-06-01"
    # Returned result carries the client-generated UIDs.
    assert result.tracked_entity == te["trackedEntity"]
    assert result.enrollment == enrollment["enrollment"]
    assert result.events == []


@respx.mock
async def test_register_with_inline_events_links_them_to_the_new_enrollment(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Inline events carry `enrollment` + `trackedEntity` UIDs for the new TE."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/tracker").mock(return_value=httpx.Response(200, json=_ok_response()))

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.tracker.register(
            program="progUid0001",
            org_unit="ouUidAAA001",
            tracked_entity_type="tetUidAAA01",
            events=[
                {
                    "program_stage": "stageUid001",
                    "occurred_at": "2024-06-05",
                    "data_values": {"deUidAAA001": "5", "deUidBBB002": "3"},
                },
            ],
        )
    finally:
        await client.close()

    body = json.loads(route.calls.last.request.content)
    enrollment = body["trackedEntities"][0]["enrollments"][0]
    event = enrollment["events"][0]
    assert event["programStage"] == "stageUid001"
    assert event["enrollment"] == result.enrollment
    assert event["trackedEntity"] == result.tracked_entity
    assert {dv["dataElement"] for dv in event["dataValues"]} == {"deUidAAA001", "deUidBBB002"}
    assert len(result.events) == 1


# ---- TrackerAccessor.enroll -----------------------------------------------


@respx.mock
async def test_enroll_posts_enrollment_only_with_generated_uid(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`enroll` sends a standalone `{enrollments: [...]}` bundle."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/tracker").mock(return_value=httpx.Response(200, json=_ok_response()))

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.tracker.enroll(
            tracked_entity="teUidAAA0001",
            program="progUid0002",
            org_unit="ouUidAAA001",
            enrolled_at="2024-06-10",
        )
    finally:
        await client.close()

    body = json.loads(route.calls.last.request.content)
    assert list(body.keys()) == ["enrollments"]
    enrollment = body["enrollments"][0]
    assert enrollment["trackedEntity"] == "teUidAAA0001"
    assert enrollment["program"] == "progUid0002"
    assert enrollment["enrollment"] == result.enrollment


# ---- TrackerAccessor.add_event --------------------------------------------


@respx.mock
async def test_add_event_for_tracker_program_carries_enrollment(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Tracker-program event POST carries `enrollment` + `trackedEntity` fields."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/tracker").mock(return_value=httpx.Response(200, json=_ok_response()))

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.tracker.add_event(
            program="progUid0001",
            program_stage="stageUid001",
            org_unit="ouUidAAA001",
            enrollment="enrollUid001",
            tracked_entity="teUidAAA0001",
            data_values={"deUidAAA001": "42"},
            occurred_at="2024-07-15",
        )
    finally:
        await client.close()

    body = json.loads(route.calls.last.request.content)
    assert list(body.keys()) == ["events"]
    event = body["events"][0]
    assert event["enrollment"] == "enrollUid001"
    assert event["trackedEntity"] == "teUidAAA0001"
    assert event["programStage"] == "stageUid001"
    assert event["occurredAt"] == "2024-07-15"
    assert event["event"] == result.event


@respx.mock
async def test_add_event_accepts_date_and_datetime_values(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`occurred_at` normalises `date` / `datetime` to ISO on the wire."""
    import datetime as _dt

    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/tracker").mock(return_value=httpx.Response(200, json=_ok_response()))

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.tracker.add_event(
            program="eventProg01",
            program_stage="stageUid002",
            org_unit="ouUidAAA001",
            occurred_at=_dt.date(2024, 8, 1),
        )
        await client.tracker.add_event(
            program="eventProg01",
            program_stage="stageUid002",
            org_unit="ouUidAAA001",
            occurred_at=_dt.datetime(2024, 8, 2, 9, 30),
        )
    finally:
        await client.close()

    first = json.loads(route.calls[0].request.content)["events"][0]
    second = json.loads(route.calls[1].request.content)["events"][0]
    assert first["occurredAt"] == "2024-08-01"
    assert second["occurredAt"].startswith("2024-08-02T09:30")


@respx.mock
async def test_add_event_for_event_program_omits_enrollment(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Event-only program: no `enrollment` or `trackedEntity` in the payload."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/tracker").mock(return_value=httpx.Response(200, json=_ok_response()))

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.tracker.add_event(
            program="eventProg01",
            program_stage="stageUid002",
            org_unit="ouUidAAA001",
            data_values={"deUidAAA001": "yes"},
            occurred_at="2024-08-01",
        )
    finally:
        await client.close()

    body = json.loads(route.calls.last.request.content)
    event = body["events"][0]
    # Neither field should surface on the wire for event programs.
    assert "enrollment" not in event
    assert "trackedEntity" not in event
    assert event["programStage"] == "stageUid002"
    # Standalone events default to COMPLETED — they're typically one-shot.
    assert event["status"] == "COMPLETED"


@respx.mock
async def test_add_event_for_tracker_program_defaults_to_active_status(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Tracker-program events default to ACTIVE — the visit is open until completed."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/tracker").mock(return_value=httpx.Response(200, json=_ok_response()))

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.tracker.add_event(
            program="progUid0001",
            program_stage="stageUid001",
            org_unit="ouUidAAA001",
            enrollment="enrollUid001",
        )
    finally:
        await client.close()

    event = json.loads(route.calls.last.request.content)["events"][0]
    assert event["status"] == "ACTIVE"


# ---- TrackerAccessor.outstanding ------------------------------------------


@respx.mock
async def test_outstanding_filters_enrollments_missing_non_repeatable_stages(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`outstanding` pulls program stages, then enrollments missing any non-repeatable UID."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/programs/progUid0001").mock(
        return_value=httpx.Response(
            200,
            json={
                "programStages": [
                    {"id": "stage000001", "repeatable": False},
                    {"id": "stage000002", "repeatable": False},
                    {"id": "stage000003", "repeatable": True},  # Skipped from the required set.
                ],
            },
        ),
    )
    respx.get("https://dhis2.example/api/tracker/enrollments").mock(
        return_value=httpx.Response(
            200,
            json={
                "instances": [
                    # Complete — all required stages covered; dropped from result.
                    {
                        "enrollment": "enrl00000A1",
                        "trackedEntity": "te000000A1",
                        "program": "progUid0001",
                        "orgUnit": "ouUidAAA001",
                        "enrolledAt": "2024-01-01",
                        "events": [{"programStage": "stage000001"}, {"programStage": "stage000002"}],
                    },
                    # Missing stage000002 — kept.
                    {
                        "enrollment": "enrl00000B2",
                        "trackedEntity": "te000000B2",
                        "program": "progUid0001",
                        "orgUnit": "ouUidAAA001",
                        "enrolledAt": "2024-02-01",
                        "events": [{"programStage": "stage000001"}],
                    },
                    # Missing both — kept.
                    {
                        "enrollment": "enrl00000C3",
                        "trackedEntity": "te000000C3",
                        "program": "progUid0001",
                        "orgUnit": "ouUidAAA001",
                        "enrolledAt": "2024-03-01",
                        "events": [],
                    },
                ],
            },
        ),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        rows = await client.tracker.outstanding("progUid0001")
    finally:
        await client.close()

    assert [r.enrollment for r in rows] == ["enrl00000B2", "enrl00000C3"]
    assert rows[0].missing_stages == ["stage000002"]
    assert rows[1].missing_stages == ["stage000001", "stage000002"]


@respx.mock
async def test_outstanding_returns_empty_when_program_has_no_required_stages(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """All stages repeatable -> no 'required' concept -> empty result."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/programs/progUid0001").mock(
        return_value=httpx.Response(
            200,
            json={"programStages": [{"id": "stageUid001", "repeatable": True}]},
        ),
    )
    enrollments_route = respx.get("https://dhis2.example/api/tracker/enrollments")

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        rows = await client.tracker.outstanding("progUid0001")
    finally:
        await client.close()

    assert rows == []
    # We short-circuit before querying enrollments when there's no required set.
    assert enrollments_route.call_count == 0
