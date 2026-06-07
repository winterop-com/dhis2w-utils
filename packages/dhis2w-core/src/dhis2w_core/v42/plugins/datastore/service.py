"""Service layer for the `datastore` plugin — namespaced key/value access (CLI + MCP share it)."""

from __future__ import annotations

from typing import Any

from dhis2w_core.profile import Profile
from dhis2w_core.v42.client_context import open_client


async def list_namespaces(profile: Profile, *, user: bool = False) -> list[str]:
    """List every namespace in the store (the per-user store when `user`)."""
    async with open_client(profile) as client:
        return await client.datastore.list_namespaces(user=user)


async def list_keys(profile: Profile, namespace: str, *, user: bool = False) -> list[str]:
    """List every key in a namespace."""
    async with open_client(profile) as client:
        return await client.datastore.list_keys(namespace, user=user)


async def get_value(profile: Profile, namespace: str, key: str, *, user: bool = False) -> Any:
    """Return the value at `namespace/key` (opaque user JSON)."""
    async with open_client(profile) as client:
        return await client.datastore.get(namespace, key, user=user)


async def set_value(profile: Profile, namespace: str, key: str, value: Any, *, user: bool = False) -> None:
    """Create or update the value at `namespace/key`."""
    async with open_client(profile) as client:
        await client.datastore.set(namespace, key, value, user=user)


async def delete_key(profile: Profile, namespace: str, key: str, *, user: bool = False) -> None:
    """Delete `namespace/key`."""
    async with open_client(profile) as client:
        await client.datastore.delete(namespace, key, user=user)


async def delete_namespace(profile: Profile, namespace: str, *, user: bool = False) -> None:
    """Delete an entire namespace and all its keys."""
    async with open_client(profile) as client:
        await client.datastore.delete_namespace(namespace, user=user)
