"""Reverse-proxy helper for `/api/routes/<id>/run` — `Dhis2Client.routes`.

DHIS2's `/api/routes` resource is a server-side reverse-proxy registry:
each `Route` declares an upstream target URL + auth scheme, and DHIS2
proxies GETs at `/api/routes/{id}/run[/<path>]` through to that target.
Routes are addressed in the wire endpoint by UID; users typically know
them by `code`. This accessor resolves `code -> uid` once per client
(cached for the lifetime of the connection) and delegates the actual
GET to `Dhis2Client.get_response()` so callers see the raw
`httpx.Response` and can do their own status-based handling (a 502
from the proxy means "DHIS2 reached, downstream didn't" — that's a
fact to report, not an exception to raise).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from dhis2w_client.generated.v41.schemas import Route
from dhis2w_client.v41._collection import parse_collection

if TYPE_CHECKING:
    from collections.abc import Mapping

    from dhis2w_client.v41.client import Dhis2Client


class RoutesAccessor:
    """`Dhis2Client.routes` — typed reverse-proxy GET against `/api/routes/<code>/run/<path>`."""

    def __init__(self, client: Dhis2Client) -> None:
        """Bind to the parent client and start with an empty code->uid cache."""
        self._client = client
        self._code_to_uid: dict[str, str] = {}

    async def list_all(self, *, page: int = 1, page_size: int = 50) -> list[Route]:
        """Page through the configured reverse-proxy Routes."""
        raw = await self._client.get_raw(
            "/api/routes",
            params={"fields": "id,code,name,url,disabled", "page": str(page), "pageSize": str(page_size)},
        )
        return parse_collection(raw, "routes", Route)

    async def run(
        self,
        code: str,
        path: str = "",
        *,
        params: Mapping[str, str] | None = None,
        extra_headers: Mapping[str, str] | None = None,
        use_cache: bool = True,
    ) -> httpx.Response:
        """GET `/api/routes/<resolved-uid>/run[/<path>]` via the DHIS2 proxy.

        `code` is the user-set `Route.code`. The UID is resolved once via
        `GET /api/routes?filter=code:eq:<code>` and cached for the rest of
        this client's lifetime; pass `use_cache=False` to force a fresh
        lookup (e.g. after a Route was renamed or re-pointed). `path` is
        appended after `/run/` — empty path hits `/run` directly with no
        suffix.

        Returns the raw `httpx.Response`. The status code is the caller's
        problem: 200 means the upstream responded, 502 means DHIS2
        reached but the upstream didn't, 404 means the Route's `id`
        no longer resolves (cached UID is stale — retry with
        `use_cache=False`).

        Raises `LookupError` when no Route with that `code` exists.
        """
        uid = await self._resolve_uid(code, use_cache=use_cache)
        suffix = f"/{path.lstrip('/')}" if path else ""
        return await self._client.get_response(
            f"/api/routes/{uid}/run{suffix}",
            params=dict(params) if params else None,
            extra_headers=dict(extra_headers) if extra_headers else None,
        )

    def invalidate_cache(self, code: str | None = None) -> None:
        """Drop the cached `code -> uid` mapping for one code (or every code when None)."""
        if code is None:
            self._code_to_uid.clear()
            return
        self._code_to_uid.pop(code, None)

    async def _resolve_uid(self, code: str, *, use_cache: bool) -> str:
        """Look up a Route's UID by its `code`, caching the result by default."""
        if use_cache:
            cached = self._code_to_uid.get(code)
            if cached is not None:
                return cached
        envelope = await self._client.get_raw(
            "/api/routes",
            params={"filter": f"code:eq:{code}", "fields": "id,code", "pageSize": "1"},
        )
        routes = envelope.get("routes")
        if not isinstance(routes, list) or not routes:
            raise LookupError(f"no route found with code={code!r}")
        first = routes[0]
        uid = first.get("id") if isinstance(first, dict) else None
        if not isinstance(uid, str):
            raise LookupError(f"route lookup for code={code!r} returned no usable id: {first!r}")
        self._code_to_uid[code] = uid
        return uid


__all__ = ["RoutesAccessor"]
