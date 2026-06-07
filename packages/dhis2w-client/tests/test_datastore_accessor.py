"""Tests for `Dhis2Client.datastore` — namespaced key/value over /api/dataStore + /api/userDataStore."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import respx
from dhis2w_client import BasicAuth, Dhis2Client


def _auth() -> BasicAuth:
    """Throwaway auth for test clients."""
    return BasicAuth(username="a", password="b")


@respx.mock
async def test_list_namespaces_and_keys(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """list_namespaces + list_keys parse the JSON arrays across every tree."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/dataStore").mock(return_value=httpx.Response(200, json=["ns1", "ns2"]))
    respx.get("https://dhis2.example/api/dataStore/ns1").mock(return_value=httpx.Response(200, json=["k1", "k2"]))
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        assert await client.datastore.list_namespaces() == ["ns1", "ns2"]
        assert await client.datastore.list_keys("ns1") == ["k1", "k2"]


@respx.mock
async def test_get_returns_opaque_json(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """get returns the raw stored value verbatim — here a nested object."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/dataStore/ns1/k1").mock(
        return_value=httpx.Response(200, json={"a": 1, "b": [2, 3]})
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        value = await client.datastore.get("ns1", "k1")
    assert value == {"a": 1, "b": [2, 3]}


@respx.mock
async def test_set_posts_when_new_puts_when_exists(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """set POSTs a new key and PUTs an existing one (existence checked via a GET first)."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/dataStore/ns1/new").mock(return_value=httpx.Response(404))
    post_route = respx.post("https://dhis2.example/api/dataStore/ns1/new").mock(
        return_value=httpx.Response(201, json={"httpStatus": "Created"})
    )
    respx.get("https://dhis2.example/api/dataStore/ns1/old").mock(return_value=httpx.Response(200, json={"old": True}))
    put_route = respx.put("https://dhis2.example/api/dataStore/ns1/old").mock(
        return_value=httpx.Response(200, json={"httpStatus": "OK"})
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        await client.datastore.set("ns1", "new", {"x": 1})
        await client.datastore.set("ns1", "old", {"x": 2})
    assert post_route.called
    assert put_route.called


@respx.mock
async def test_delete_and_user_store_base(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """delete issues a DELETE, and user=True targets the per-user store path."""
    mock_system_info(server_version)
    delete_route = respx.delete("https://dhis2.example/api/dataStore/ns1/k1").mock(
        return_value=httpx.Response(200, json={"httpStatus": "OK"})
    )
    user_route = respx.get("https://dhis2.example/api/userDataStore").mock(
        return_value=httpx.Response(200, json=["mine"])
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        await client.datastore.delete("ns1", "k1")
        assert await client.datastore.list_namespaces(user=True) == ["mine"]
    assert delete_route.called
    assert user_route.called
