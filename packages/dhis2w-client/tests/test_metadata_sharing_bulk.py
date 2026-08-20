"""Unit tests for `MetadataAccessor.apply_sharing_bulk` + `.apply_sharing_bulk_multi` — respx-mocked."""

from __future__ import annotations

import asyncio
import json as _json
from collections.abc import Callable

import httpx
import respx
from dhis2w_client import (
    ACCESS_READ_METADATA,
    ACCESS_READ_WRITE_METADATA,
    BasicAuth,
    BulkSharingResult,
    Dhis2Client,
    SharingBuilder,
)


def _auth() -> BasicAuth:
    return BasicAuth(username="admin", password="district")


def _mock_preamble() -> None:
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.0"}),
    )


@respx.mock
async def test_apply_sharing_bulk_fans_out_per_uid_and_reports_successes() -> None:
    """Apply sharing bulk fans out per uid and reports successes."""
    _mock_preamble()
    route = respx.post("https://dhis2.example/api/sharing").mock(return_value=httpx.Response(200, json={}))
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        builder = SharingBuilder(public_access=ACCESS_READ_METADATA).grant_user_group("UG_PROG", "rwrw----")
        result = await client.metadata.apply_sharing_bulk("dataSet", ["DS_A", "DS_B"], builder)
    finally:
        await client.close()
    assert route.call_count == 2
    assert isinstance(result, BulkSharingResult)
    assert result.ok is True
    assert sorted(result.successful_uids) == ["DS_A", "DS_B"]
    assert result.total == 2


@respx.mock
async def test_apply_sharing_bulk_sends_per_uid_query_params_and_object_payload() -> None:
    """Apply sharing bulk sends per uid query params and object payload."""
    _mock_preamble()
    route = respx.post("https://dhis2.example/api/sharing").mock(return_value=httpx.Response(200, json={}))
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        builder = SharingBuilder(public_access=ACCESS_READ_WRITE_METADATA).grant_user("U_ALICE", "rw------")
        await client.metadata.apply_sharing_bulk("dataSet", ["DS_A"], builder)
    finally:
        await client.close()
    request = route.calls.last.request
    assert request.url.params["type"] == "dataSet"
    assert request.url.params["id"] == "DS_A"
    body = _json.loads(request.read())
    assert body["object"]["publicAccess"] == ACCESS_READ_WRITE_METADATA
    assert body["object"]["userAccesses"] == [{"id": "U_ALICE", "access": "rw------"}]


@respx.mock
async def test_apply_sharing_bulk_captures_per_uid_failures_without_raising() -> None:
    """Apply sharing bulk captures per uid failures without raising."""
    _mock_preamble()
    respx.post("https://dhis2.example/api/sharing", params={"type": "dataSet", "id": "DS_A"}).mock(
        return_value=httpx.Response(200, json={}),
    )
    respx.post("https://dhis2.example/api/sharing", params={"type": "dataSet", "id": "DS_B"}).mock(
        return_value=httpx.Response(
            409,
            json={"status": "ERROR", "message": "conflict on sharing", "httpStatusCode": 409},
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        builder = SharingBuilder(public_access=ACCESS_READ_METADATA)
        result = await client.metadata.apply_sharing_bulk("dataSet", ["DS_A", "DS_B"], builder)
    finally:
        await client.close()
    assert result.ok is False
    assert result.successful_uids == ["DS_A"]
    assert len(result.failures) == 1
    failure = result.failures[0]
    assert failure.uid == "DS_B"
    assert failure.resource == "dataSet"
    assert failure.status_code == 409
    assert "conflict" in failure.message.lower()


@respx.mock
async def test_apply_sharing_bulk_multi_fans_out_across_resource_types() -> None:
    """Apply sharing bulk multi fans out across resource types."""
    _mock_preamble()
    route = respx.post("https://dhis2.example/api/sharing").mock(return_value=httpx.Response(200, json={}))
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.metadata.apply_sharing_bulk_multi(
            {
                "dataSet": ["DS_A"],
                "program": ["PROG_A"],
            },
            SharingBuilder(public_access=ACCESS_READ_METADATA),
        )
    finally:
        await client.close()
    assert route.call_count == 2
    assert sorted(result.successful_uids) == ["DS_A", "PROG_A"]
    assert result.ok is True


@respx.mock
async def test_apply_sharing_bulk_admits_uids_through_a_bounded_worker_pool(
    server_version: str,
    mock_system_info: Callable[..., None],
) -> None:
    """The fan-out holds one task per worker, not one per UID, while requests are in flight.

    Observable: the delta in `len(asyncio.all_tasks())` while every worker is parked on a
    blocked response. Task count is the thing the worker pool bounds — the in-flight request
    count is bounded either way — and the baseline is taken inside the same test task, so the
    delta is exactly the driving task plus its workers.
    """
    mock_system_info(server_version)
    record_count = 64
    worker_count = 4
    gate = asyncio.Event()
    saturated = asyncio.Event()
    admitted: list[str] = []

    async def _blocked(request: httpx.Request) -> httpx.Response:
        admitted.append(request.url.params["id"])
        if len(admitted) >= worker_count:
            saturated.set()
        await gate.wait()
        return httpx.Response(200, json={})

    respx.post("https://dhis2.example/api/sharing").mock(side_effect=_blocked)

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        uids = [f"DS_{index}" for index in range(record_count)]
        baseline_task_count = len(asyncio.all_tasks())
        call = asyncio.create_task(
            client.metadata.apply_sharing_bulk(
                "dataSet",
                uids,
                SharingBuilder(public_access=ACCESS_READ_METADATA),
                concurrency=worker_count,
            ),
        )
        await asyncio.wait_for(saturated.wait(), timeout=5.0)
        for _ in range(5):
            await asyncio.sleep(0)
        parked_task_delta = len(asyncio.all_tasks()) - baseline_task_count
        admitted_while_blocked = len(admitted)
        gate.set()
        result = await asyncio.wait_for(call, timeout=5.0)
    finally:
        gate.set()
        await client.close()

    # One task drives the bulk call and one runs each worker; a task per UID would show 65.
    assert parked_task_delta <= worker_count + 3
    assert admitted_while_blocked == worker_count
    assert len(admitted) == record_count
    assert result.ok is True
    assert result.successful_uids == [f"DS_{index}" for index in range(record_count)]


@respx.mock
async def test_apply_sharing_bulk_merges_in_input_order_when_responses_are_staggered(
    server_version: str,
    mock_system_info: Callable[..., None],
) -> None:
    """Staggered completion order leaves the merged result in input order."""
    mock_system_info(server_version)
    uids = [f"DS_{index}" for index in range(8)]
    completion_order: list[str] = []

    async def _staggered(request: httpx.Request) -> httpx.Response:
        uid = request.url.params["id"]
        index = int(uid.removeprefix("DS_"))
        # Later UIDs answer soonest, so completion runs opposite to input order.
        await asyncio.sleep((len(uids) - index) * 0.005)
        completion_order.append(uid)
        if index % 3 == 0:
            return httpx.Response(
                409,
                json={"status": "ERROR", "message": f"conflict on {uid}", "httpStatusCode": 409},
            )
        return httpx.Response(200, json={})

    respx.post("https://dhis2.example/api/sharing").mock(side_effect=_staggered)

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.metadata.apply_sharing_bulk(
            "dataSet",
            uids,
            SharingBuilder(public_access=ACCESS_READ_METADATA),
            concurrency=8,
        )
    finally:
        await client.close()

    assert completion_order == list(reversed(uids))
    assert result.successful_uids == [uid for index, uid in enumerate(uids) if index % 3]
    assert [failure.uid for failure in result.failures] == [uid for index, uid in enumerate(uids) if index % 3 == 0]
    assert result.total == len(uids)


@respx.mock
async def test_apply_sharing_bulk_short_circuits_on_empty_input() -> None:
    """Apply sharing bulk short circuits on empty input."""
    _mock_preamble()
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.metadata.apply_sharing_bulk(
            "dataSet", [], SharingBuilder(public_access=ACCESS_READ_METADATA)
        )
    finally:
        await client.close()
    assert result.ok is True
    assert result.total == 0
    assert result.successful_uids == []
