"""Unit tests for `MetadataAccessor.patch_bulk` + `.patch_bulk_multi` — respx-mocked."""

from __future__ import annotations

import asyncio
import json as _json
from collections.abc import Callable
from typing import Any

import httpx
import respx
from dhis2w_client import BasicAuth, BulkPatchResult, Dhis2Client, ReplaceOp


def _auth() -> BasicAuth:
    return BasicAuth(username="admin", password="district")


def _mock_preamble() -> None:
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.42.0"}),
    )


@respx.mock
async def test_patch_bulk_fans_out_per_uid_and_reports_successes() -> None:
    """Patch bulk fans out per uid and reports successes."""
    _mock_preamble()
    a = respx.patch("https://dhis2.example/api/dataElements/DE_A").mock(return_value=httpx.Response(200, json={}))
    b = respx.patch("https://dhis2.example/api/dataElements/DE_B").mock(return_value=httpx.Response(200, json={}))
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.metadata.patch_bulk(
            "dataElements",
            [
                ("DE_A", [ReplaceOp(op="replace", path="/name", value="Renamed A")]),
                ("DE_B", [ReplaceOp(op="replace", path="/name", value="Renamed B")]),
            ],
        )
    finally:
        await client.close()
    assert a.called and b.called
    assert isinstance(result, BulkPatchResult)
    assert result.ok is True
    assert sorted(result.successful_uids) == ["DE_A", "DE_B"]
    assert result.failures == []


@respx.mock
async def test_patch_bulk_sends_json_patch_body_with_typed_ops() -> None:
    """Patch bulk sends json patch body with typed ops."""
    _mock_preamble()
    route = respx.patch("https://dhis2.example/api/dataElements/DE_A").mock(return_value=httpx.Response(200, json={}))
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.metadata.patch_bulk(
            "dataElements",
            [("DE_A", [ReplaceOp(op="replace", path="/shortName", value="A2")])],
        )
    finally:
        await client.close()
    body: list[dict[str, Any]] = _json.loads(route.calls.last.request.read())
    assert body == [{"op": "replace", "path": "/shortName", "value": "A2"}]
    assert route.calls.last.request.headers["Content-Type"] == "application/json-patch+json"


@respx.mock
async def test_patch_bulk_captures_per_uid_failures_without_raising() -> None:
    """Patch bulk captures per uid failures without raising."""
    _mock_preamble()
    respx.patch("https://dhis2.example/api/dataElements/DE_A").mock(return_value=httpx.Response(200, json={}))
    respx.patch("https://dhis2.example/api/dataElements/DE_B").mock(
        return_value=httpx.Response(
            409,
            json={"status": "ERROR", "message": "conflict on /name", "httpStatusCode": 409},
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.metadata.patch_bulk(
            "dataElements",
            [
                ("DE_A", [{"op": "replace", "path": "/name", "value": "ok"}]),
                ("DE_B", [{"op": "replace", "path": "/name", "value": "bad"}]),
            ],
        )
    finally:
        await client.close()
    assert result.ok is False
    assert result.successful_uids == ["DE_A"]
    assert len(result.failures) == 1
    failure = result.failures[0]
    assert failure.uid == "DE_B"
    assert failure.resource == "dataElements"
    assert failure.status_code == 409
    assert "conflict" in failure.message.lower()


@respx.mock
async def test_patch_bulk_multi_fans_out_across_resource_types() -> None:
    """Patch bulk multi fans out across resource types."""
    _mock_preamble()
    de = respx.patch("https://dhis2.example/api/dataElements/DE_A").mock(return_value=httpx.Response(200, json={}))
    ind = respx.patch("https://dhis2.example/api/indicators/IND_A").mock(return_value=httpx.Response(200, json={}))
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.metadata.patch_bulk_multi(
            {
                "dataElements": [("DE_A", [{"op": "replace", "path": "/name", "value": "de"}])],
                "indicators": [("IND_A", [{"op": "replace", "path": "/name", "value": "ind"}])],
            },
        )
    finally:
        await client.close()
    assert de.called and ind.called
    assert sorted(result.successful_uids) == ["DE_A", "IND_A"]


@respx.mock
async def test_patch_bulk_short_circuits_on_empty_input() -> None:
    """Patch bulk short circuits on empty input."""
    _mock_preamble()
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.metadata.patch_bulk("dataElements", [])
    finally:
        await client.close()
    assert result.ok is True
    assert result.total == 0
    assert result.failures == []


@respx.mock
async def test_patch_bulk_admits_records_through_a_bounded_worker_pool(
    server_version: str,
    mock_system_info: Callable[..., None],
) -> None:
    """The fan-out holds one task per worker, not one per record, while requests are in flight.

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
        admitted.append(request.url.path.rsplit("/", 1)[-1])
        if len(admitted) >= worker_count:
            saturated.set()
        await gate.wait()
        return httpx.Response(200, json={})

    respx.patch(url__regex=r"https://dhis2\.example/api/dataElements/DE_\d+").mock(side_effect=_blocked)

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        patches = [(f"DE_{index}", [{"op": "replace", "path": "/name", "value": f"n{index}"}]) for index in range(64)]
        baseline_task_count = len(asyncio.all_tasks())
        call = asyncio.create_task(client.metadata.patch_bulk("dataElements", patches, concurrency=worker_count))
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

    # One task drives the bulk call and one runs each worker; a task per record would show 65.
    assert parked_task_delta <= worker_count + 3
    assert admitted_while_blocked == worker_count
    assert len(admitted) == record_count
    assert result.ok is True
    assert result.successful_uids == [f"DE_{index}" for index in range(record_count)]


@respx.mock
async def test_patch_bulk_merges_in_input_order_when_responses_are_staggered(
    server_version: str,
    mock_system_info: Callable[..., None],
) -> None:
    """Staggered completion order leaves the merged result in input order."""
    mock_system_info(server_version)
    uids = [f"DE_{index}" for index in range(8)]
    completion_order: list[str] = []

    async def _staggered(request: httpx.Request) -> httpx.Response:
        uid = request.url.path.rsplit("/", 1)[-1]
        index = int(uid.removeprefix("DE_"))
        # Later records answer soonest, so completion runs opposite to input order.
        await asyncio.sleep((len(uids) - index) * 0.005)
        completion_order.append(uid)
        if index % 3 == 0:
            return httpx.Response(
                409,
                json={"status": "ERROR", "message": f"conflict on {uid}", "httpStatusCode": 409},
            )
        return httpx.Response(200, json={})

    respx.patch(url__regex=r"https://dhis2\.example/api/dataElements/DE_\d+").mock(side_effect=_staggered)

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.metadata.patch_bulk(
            "dataElements",
            [(uid, [{"op": "replace", "path": "/name", "value": uid}]) for uid in uids],
            concurrency=8,
        )
    finally:
        await client.close()

    assert completion_order == list(reversed(uids))
    assert result.successful_uids == [uid for index, uid in enumerate(uids) if index % 3]
    assert [failure.uid for failure in result.failures] == [uid for index, uid in enumerate(uids) if index % 3 == 0]
    assert result.total == len(uids)


async def test_bulk_patch_result_helpers() -> None:
    """Bulk patch result helpers."""
    empty = BulkPatchResult()
    assert empty.ok is True
    assert empty.total == 0

    mixed = BulkPatchResult(
        successful_uids=["A", "B"],
        failures=[],
    )
    assert mixed.ok is True
    assert mixed.total == 2
