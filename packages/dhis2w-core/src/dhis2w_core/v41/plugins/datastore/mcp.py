"""FastMCP tool registration for the `datastore` plugin."""

from __future__ import annotations

from typing import Any

from dhis2w_core.profile import resolve_profile
from dhis2w_core.v41.plugins.datastore import service


def register(mcp: Any) -> None:
    """Register the `datastore_*` tools on `mcp`."""

    @mcp.tool()
    async def datastore_list_namespaces(user: bool = False, profile: str | None = None) -> list[str]:
        """List every namespace in the DHIS2 data store. `user=True` targets the per-user store."""
        return await service.list_namespaces(resolve_profile(profile), user=user)

    @mcp.tool()
    async def datastore_list_keys(namespace: str, user: bool = False, profile: str | None = None) -> list[str]:
        """List every key in a data-store namespace."""
        return await service.list_keys(resolve_profile(profile), namespace, user=user)

    @mcp.tool()
    async def datastore_get(namespace: str, key: str, user: bool = False, profile: str | None = None) -> Any:
        """Return the value at `namespace/key` — arbitrary user JSON (object, array, or scalar)."""
        return await service.get_value(resolve_profile(profile), namespace, key, user=user)

    @mcp.tool()
    async def datastore_set(
        namespace: str, key: str, value: Any, user: bool = False, profile: str | None = None
    ) -> str:
        """Create or update `namespace/key`. `value` is arbitrary JSON. Returns a status line."""
        await service.set_value(resolve_profile(profile), namespace, key, value, user=user)
        return f"set {namespace}/{key}"

    @mcp.tool()
    async def datastore_delete(namespace: str, key: str, user: bool = False, profile: str | None = None) -> str:
        """Delete `namespace/key` from the data store. Returns a status line."""
        await service.delete_key(resolve_profile(profile), namespace, key, user=user)
        return f"deleted {namespace}/{key}"
