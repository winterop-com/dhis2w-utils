"""Unit tests for `DashboardsAccessor` — respx-mocked."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import respx
from dhis2w_client import BasicAuth, DashboardSlot, Dhis2Client


def _auth() -> BasicAuth:
    return BasicAuth(username="admin", password="district")


@respx.mock
async def test_list_all_orders_by_name_paging_off(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """List all orders by name paging off."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/dashboards").mock(
        return_value=httpx.Response(
            200,
            json={"dashboards": [{"id": "D1", "name": "alpha"}, {"id": "D2", "name": "beta"}]},
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        dashboards = await client.dashboards.list_all()
    finally:
        await client.close()
    assert route.calls.last.request.url.params["order"] == "name:asc"
    assert route.calls.last.request.url.params["paging"] == "false"
    assert [d.name for d in dashboards] == ["alpha", "beta"]


@respx.mock
async def test_get_returns_typed_dashboard_with_items(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Get returns typed dashboard with items."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/dashboards/D1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "D1",
                "name": "x",
                "dashboardItems": [
                    {"id": "I1", "type": "VISUALIZATION", "x": 0, "y": 0, "width": 60, "height": 20},
                ],
            },
        ),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        d = await client.dashboards.get("D1")
    finally:
        await client.close()
    assert d.id == "D1"
    assert d.dashboardItems is not None
    assert len(d.dashboardItems) == 1


@respx.mock
async def test_add_item_auto_stacks_below_existing_items(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Omitting the slot should drop the new item at y = max(existing y + height)."""
    mock_system_info(server_version)
    # First GET — fetch the dashboard to read existing items.
    respx.get("https://dhis2.example/api/dashboards/D1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "D1",
                "name": "Overview",
                "dashboardItems": [
                    {"id": "I1", "type": "VISUALIZATION", "x": 0, "y": 0, "width": 60, "height": 15},
                    {"id": "I2", "type": "VISUALIZATION", "x": 0, "y": 15, "width": 60, "height": 25},
                ],
            },
        ),
    )
    metadata_route = respx.post("https://dhis2.example/api/metadata").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.dashboards.add_item("D1", "VizNew000001")
    finally:
        await client.close()
    assert metadata_route.call_count == 1
    body = metadata_route.calls.last.request.content
    # New item should land at y=40 (15 + 25).
    assert b'"y":40' in body
    assert b'"visualization":{"id":"VizNew000001"}' in body


@respx.mock
async def test_add_item_respects_explicit_slot(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Add item respects explicit slot."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/dashboards/D1").mock(
        return_value=httpx.Response(200, json={"id": "D1", "name": "Empty", "dashboardItems": []}),
    )
    metadata_route = respx.post("https://dhis2.example/api/metadata").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        slot = DashboardSlot(x=20, y=5, width=20, height=10)
        await client.dashboards.add_item("D1", "VizX", slot=slot)
    finally:
        await client.close()
    body = metadata_route.calls.last.request.content
    assert b'"x":20' in body
    assert b'"y":5' in body
    assert b'"width":20' in body
    assert b'"height":10' in body


@respx.mock
async def test_remove_item_drops_matching_uid(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Remove item drops matching uid."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/dashboards/D1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "D1",
                "name": "Overview",
                "dashboardItems": [
                    {"id": "keep", "type": "VISUALIZATION", "x": 0, "y": 0, "width": 60, "height": 20},
                    {"id": "drop", "type": "VISUALIZATION", "x": 0, "y": 20, "width": 60, "height": 20},
                ],
            },
        ),
    )
    metadata_route = respx.post("https://dhis2.example/api/metadata").mock(
        return_value=httpx.Response(200, json={"status": "OK"}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.dashboards.remove_item("D1", "drop")
    finally:
        await client.close()
    body = metadata_route.calls.last.request.content
    assert b'"id":"keep"' in body
    assert b'"id":"drop"' not in body


async def test_accessor_is_bound_on_client() -> None:
    """Accessor is bound on client."""
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        for attr in ("get", "list_all", "add_item", "remove_item"):
            assert hasattr(client.dashboards, attr), f"missing {attr}"
    finally:
        await client.close()


_ = pytest
