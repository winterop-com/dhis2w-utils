"""Unit tests for `SectionsAccessor` — respx-mocked."""

from __future__ import annotations

import json as _json
from collections.abc import Callable
from typing import Any

import httpx
import respx
from dhis2w_client import BasicAuth, Dhis2Client


def _auth() -> BasicAuth:
    return BasicAuth(username="admin", password="district")


@respx.mock
async def test_list_all_orders_by_sort_order(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """List all orders by sort order."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/sections").mock(
        return_value=httpx.Response(
            200,
            json={
                "sections": [
                    {"id": "SEC1", "name": "A", "sortOrder": 1},
                    {"id": "SEC2", "name": "B", "sortOrder": 2},
                ],
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        rows = await client.sections.list_all()
    finally:
        await client.close()
    assert route.calls.last.request.url.params["order"] == "sortOrder:asc"
    assert [s.id for s in rows] == ["SEC1", "SEC2"]


@respx.mock
async def test_list_for_filters_by_parent_and_disables_paging(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """List for filters by parent and disables paging."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/sections").mock(
        return_value=httpx.Response(200, json={"sections": []}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.sections.list_for("DS001")
    finally:
        await client.close()
    params = route.calls.last.request.url.params
    assert params["filter"] == "dataSet.id:eq:DS001"
    assert params["paging"] == "false"
    assert params["order"] == "sortOrder:asc"


@respx.mock
async def test_create_posts_payload_with_ordered_data_elements(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Create posts payload with ordered data elements."""
    mock_system_info(server_version)
    post = respx.post("https://dhis2.example/api/sections").mock(
        return_value=httpx.Response(201, json={"response": {"uid": "SEC_NEW0001"}}),
    )
    respx.get("https://dhis2.example/api/sections/SEC_NEW0001").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "SEC_NEW0001",
                "name": "Stock",
                "sortOrder": 1,
                "dataSet": {"id": "DS001"},
                "dataElements": [{"id": "DE_A"}, {"id": "DE_B"}],
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        section = await client.sections.create(
            name="Stock",
            data_set_uid="DS001",
            sort_order=1,
            data_element_uids=["DE_A", "DE_B"],
        )
    finally:
        await client.close()
    body: dict[str, Any] = _json.loads(post.calls.last.request.read())
    assert body["name"] == "Stock"
    assert body["dataSet"] == {"id": "DS001"}
    assert body["sortOrder"] == 1
    assert body["dataElements"] == [{"id": "DE_A"}, {"id": "DE_B"}]
    assert section.id == "SEC_NEW0001"


@respx.mock
async def test_add_element_appends_by_default(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Add element appends by default."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/sections/SEC1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "SEC1",
                "name": "Stock",
                "dataSet": {"id": "DS001"},
                "dataElements": [{"id": "DE_A"}],
            },
        ),
    )
    put = respx.put("https://dhis2.example/api/sections/SEC1").mock(return_value=httpx.Response(200, json={}))
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.sections.add_element("SEC1", "DE_B")
    finally:
        await client.close()
    body: dict[str, Any] = _json.loads(put.calls.last.request.read())
    assert body["dataElements"] == [{"id": "DE_A"}, {"id": "DE_B"}]


@respx.mock
async def test_add_element_inserts_at_position(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Add element inserts at position."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/sections/SEC1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "SEC1",
                "name": "Stock",
                "dataSet": {"id": "DS001"},
                "dataElements": [{"id": "DE_A"}, {"id": "DE_C"}],
            },
        ),
    )
    put = respx.put("https://dhis2.example/api/sections/SEC1").mock(return_value=httpx.Response(200, json={}))
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.sections.add_element("SEC1", "DE_B", position=1)
    finally:
        await client.close()
    body: dict[str, Any] = _json.loads(put.calls.last.request.read())
    assert body["dataElements"] == [{"id": "DE_A"}, {"id": "DE_B"}, {"id": "DE_C"}]


@respx.mock
async def test_reorder_replaces_data_elements_verbatim(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Reorder replaces data elements verbatim."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/sections/SEC1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "SEC1",
                "name": "Stock",
                "dataSet": {"id": "DS001"},
                "dataElements": [{"id": "DE_A"}, {"id": "DE_B"}, {"id": "DE_C"}],
            },
        ),
    )
    put = respx.put("https://dhis2.example/api/sections/SEC1").mock(return_value=httpx.Response(200, json={}))
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.sections.reorder("SEC1", ["DE_C", "DE_A", "DE_B"])
    finally:
        await client.close()
    body: dict[str, Any] = _json.loads(put.calls.last.request.read())
    assert body["dataElements"] == [{"id": "DE_C"}, {"id": "DE_A"}, {"id": "DE_B"}]


@respx.mock
async def test_remove_element_drops_the_uid(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Remove element drops the uid."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/sections/SEC1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "SEC1",
                "name": "Stock",
                "dataSet": {"id": "DS001"},
                "dataElements": [{"id": "DE_A"}, {"id": "DE_B"}],
            },
        ),
    )
    put = respx.put("https://dhis2.example/api/sections/SEC1").mock(return_value=httpx.Response(200, json={}))
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.sections.remove_element("SEC1", "DE_A")
    finally:
        await client.close()
    body: dict[str, Any] = _json.loads(put.calls.last.request.read())
    assert body["dataElements"] == [{"id": "DE_B"}]


@respx.mock
async def test_delete_routes_to_sections_uid(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Delete routes to sections uid."""
    mock_system_info(server_version)
    route = respx.delete("https://dhis2.example/api/sections/SEC1").mock(return_value=httpx.Response(204))
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.sections.delete("SEC1")
    finally:
        await client.close()
    assert route.called


async def test_accessor_is_bound_on_client() -> None:
    """Accessor is bound on client."""
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        assert client.sections is not None
    finally:
        await client.close()
