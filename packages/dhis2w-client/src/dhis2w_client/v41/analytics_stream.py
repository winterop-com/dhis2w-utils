"""`/api/analytics*` access — `client.analytics.aggregate` + `client.analytics.stream_to`.

Two flavours of analytics call live here:

- `aggregate(dx=..., pe=..., ou=...)` returns a parsed `Grid`. Right for
  small / medium responses where you want typed cells immediately.
- `stream_to(destination=...)` writes the response straight to disk
  without buffering. Right for very large responses (yearly
  district-level pivots, etc.).

DHIS2's analytics endpoint family can return very large responses on
reasonable queries. The two methods cover the speed/memory trade-off
explicitly so callers don't have to think about it.

Endpoints covered (pass the full path including extension / sub-resource):

- `/api/analytics.json` (default)
- `/api/analytics.csv`
- `/api/analytics.xlsx`
- `/api/analytics/rawData.json` (requires `.json` suffix, see BUGS.md #1)
- `/api/analytics/dataValueSet.json` (same)
- `/api/analytics/events/query/<program>.json`

`params` (on `stream_to`) is forwarded verbatim — DHIS2's repeated-param
pattern (`dimension=dx:...&dimension=pe:...&dimension=ou:...`) expects
either a mapping with list values (`{"dimension": ["dx:...", ...]}`) or
a list of 2-tuples (`[("dimension", "dx:..."), ...]`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import httpx

from dhis2w_client.v41.analytics import Grid

if TYPE_CHECKING:
    from dhis2w_client.v41.client import Dhis2Client


_DEFAULT_CHUNK_SIZE = 64 * 1024  # 64 KiB balances syscall count vs chunk overhead.

AnalyticsQuery = Mapping[str, Any] | Sequence[tuple[str, Any]]


class AnalyticsAccessor:
    """`Dhis2Client.analytics` — typed query (`aggregate`) + streaming download (`stream_to`).

    Use `aggregate(...)` for a parsed `Grid` (small / medium responses);
    `stream_to(...)` writes straight to disk for very large pivots
    without buffering. Both accept the same dimension dx/pe/ou
    convenience kwargs plus arbitrary extra params for the rest of
    DHIS2's analytics flag surface.
    """

    def __init__(self, client: Dhis2Client) -> None:
        """Bind to the sharing client."""
        self._client = client

    async def aggregate(
        self,
        *,
        dx: str | Sequence[str] | None = None,
        pe: str | Sequence[str] | None = None,
        ou: str | Sequence[str] | None = None,
        endpoint: str = "/api/analytics.json",
        extra_params: Mapping[str, Any] | None = None,
    ) -> Grid:
        """Run an analytics query and return the parsed `Grid` envelope.

        `dx` / `pe` / `ou` are convenience for the three core dimensions.
        Each accepts a single id (`"fbfJHSPpUQD"`), a colon-joined token
        (`"LAST_12_MONTHS"`), a list of ids (`["fbfJHSPpUQD", "cYeuwXTCPkU"]`),
        or `None`. Multiple values within a dimension are colon-joined into
        the single `dimension=<axis>:v1;v2;v3` form DHIS2 expects.

        `extra_params` covers the rest (`aggregationType`, `outputIdScheme`,
        `displayProperty`, `skipMeta`, etc.). Pass either a flat
        `{"aggregationType": "SUM"}` or a list of 2-tuples for repeated keys.

        Raises `Dhis2ApiError` on 4xx / 5xx.
        """
        dimension: list[str] = []
        for axis, value in (("dx", dx), ("pe", pe), ("ou", ou)):
            if value is None:
                continue
            ids = [value] if isinstance(value, str) else list(value)
            if ids:
                dimension.append(f"{axis}:{';'.join(ids)}")
        params: dict[str, Any] = {"dimension": dimension} if dimension else {}
        if extra_params:
            params.update(extra_params)
        raw = await self._client.get_raw(endpoint, params=params)
        return Grid.model_validate(raw)

    async def stream_to(
        self,
        destination: Path,
        *,
        params: AnalyticsQuery,
        endpoint: str = "/api/analytics.json",
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
    ) -> int:
        """Stream a GET on `endpoint` straight to `destination`; return bytes written.

        `params` forwards exactly what DHIS2 accepts — use a list of
        2-tuples when you need repeated `dimension=` params, or a mapping
        whose values are lists when a key can appear more than once.

        `endpoint` is the full path including extension + sub-resource
        (`/api/analytics.csv`, `/api/analytics/rawData.json`, ...).
        `client.system.info()` uses the same httpx pool, so auth + retry +
        pool-tuning all still apply.

        Raises `Dhis2ApiError` on 4xx / 5xx (the error body is buffered —
        errors are small and readable).
        """
        headers = await self._client._auth.headers()  # noqa: SLF001 — accessor is tight with the client
        http = self._client._http  # noqa: SLF001
        if http is None:
            raise RuntimeError("Dhis2Client is not connected; call connect() first")

        destination.parent.mkdir(parents=True, exist_ok=True)
        bytes_written = 0
        # httpx.stream accepts a wider union than our typed StreamSource — cast
        # at the boundary rather than re-expressing DHIS2's repeated-key shape.
        query_params = cast(httpx._types.QueryParamTypes, params)
        async with http.stream("GET", endpoint, params=query_params, headers=headers) as response:
            if response.status_code >= 400:
                # 4xx / 5xx responses are small; buffer the body for the error.
                await response.aread()
                body: Any
                try:
                    body = response.json()
                except ValueError:
                    body = response.text
                from dhis2w_client.errors import AuthenticationError, Dhis2ApiError, format_unauthorized_message

                if response.status_code == 401:
                    raise AuthenticationError(
                        format_unauthorized_message("GET", endpoint, response.headers.get("WWW-Authenticate"))
                    )
                raise Dhis2ApiError(
                    status_code=response.status_code,
                    message=response.reason_phrase,
                    body=body,
                )
            with destination.open("wb") as handle:
                async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                    handle.write(chunk)
                    bytes_written += len(chunk)
        return bytes_written


__all__ = ["AnalyticsAccessor", "AnalyticsQuery"]
