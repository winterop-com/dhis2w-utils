"""DHIS2 key-value store helpers — `Dhis2Client.datastore`.

Wraps DHIS2's two namespaced key/value stores:

- `/api/dataStore` — the instance/app store (shared, sharing-controlled). The default.
- `/api/userDataStore` — the per-user store. Reach it by passing `user=True` to any method.

(There is no `/api/systemDataStore`; instance-wide system config is `systemSettings`, exposed by
`d2w system settings`.) Stored values are arbitrary user JSON — object, array, or scalar — so
reads return `Any`. `set` is create-or-update: DHIS2 splits create (POST) from update (PUT), so
this checks existence first and dispatches accordingly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dhis2w_client.errors import Dhis2ApiError

if TYPE_CHECKING:
    from dhis2w_client.v42.client import Dhis2Client


class DatastoreAccessor:
    """`Dhis2Client.datastore` — namespaced key/value access over /api/dataStore + /api/userDataStore."""

    def __init__(self, client: Dhis2Client) -> None:
        """Bind to the sharing client — reuses its auth + HTTP pool for every request."""
        self._client = client

    @staticmethod
    def _base(user: bool) -> str:
        """The store root: per-user when `user`, else the shared instance store."""
        return "/api/userDataStore" if user else "/api/dataStore"

    async def _read(self, path: str) -> Any:
        """GET arbitrary JSON (object / array / scalar); raise `Dhis2ApiError` with DHIS2's message on non-2xx."""
        response = await self._client.get_response(path)
        if not response.is_success:
            try:
                detail = response.json().get("message") or response.text
            except (ValueError, AttributeError, TypeError):
                detail = response.text
            raise Dhis2ApiError(response.status_code, detail or "datastore request failed")
        return response.json()

    async def list_namespaces(self, *, user: bool = False) -> list[str]:
        """List every namespace in the store."""
        value = await self._read(self._base(user))
        return [str(namespace) for namespace in value] if isinstance(value, list) else []

    async def list_keys(self, namespace: str, *, user: bool = False) -> list[str]:
        """List every key in a namespace."""
        value = await self._read(f"{self._base(user)}/{namespace}")
        return [str(key) for key in value] if isinstance(value, list) else []

    async def get(self, namespace: str, key: str, *, user: bool = False) -> Any:
        """Return the value at `namespace/key` (opaque user JSON). Raises if the key is absent."""
        return await self._read(f"{self._base(user)}/{namespace}/{key}")

    async def exists(self, namespace: str, key: str, *, user: bool = False) -> bool:
        """Whether `namespace/key` exists (status check, no body parse)."""
        response = await self._client.get_response(f"{self._base(user)}/{namespace}/{key}")
        return response.is_success

    async def set(self, namespace: str, key: str, value: Any, *, user: bool = False) -> None:
        """Create or update `namespace/key` — POST when new, PUT when it already exists."""
        path = f"{self._base(user)}/{namespace}/{key}"
        if await self.exists(namespace, key, user=user):
            await self._client.put_raw(path, body=value)
        else:
            await self._client.post_raw(path, body=value)

    async def delete(self, namespace: str, key: str, *, user: bool = False) -> None:
        """Delete `namespace/key`. Raises if it doesn't exist."""
        await self._client.delete_raw(f"{self._base(user)}/{namespace}/{key}")

    async def delete_namespace(self, namespace: str, *, user: bool = False) -> None:
        """Delete an entire namespace and all its keys."""
        await self._client.delete_raw(f"{self._base(user)}/{namespace}")


__all__ = ["DatastoreAccessor"]
