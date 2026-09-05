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
from typing import TYPE_CHECKING, Any

from dhis2w_client._streaming import stream_to_sink
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
        return await stream_to_sink(
            self._client,
            "GET",
            endpoint,
            destination,
            params=params,
            chunk_size=chunk_size,
        )

    async def event_query(
        self,
        program: str,
        *,
        stage: str | None = None,
        dimension: str | Sequence[str] | None = None,
        filter: str | Sequence[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        output_type: str | None = None,
        event_status: str | None = None,
        program_status: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
        extra_params: Mapping[str, Any] | None = None,
    ) -> Grid:
        """Run an event analytics query and return the parsed `Grid` envelope.

        GET `/api/analytics/events/query/<program>` — the event-level analytics
        read (one row per event). `dimension` and `filter` each accept a single
        pre-formed token (`"pe:LAST_12_MONTHS"`, `"ou:ImspTQPwCqd"`,
        `"<deUid>:GT:5"`) or a sequence, repeating as `dimension=` / `filter=`
        params. `stage` scopes to one program stage. `start_date` / `end_date`
        bound the event date (`YYYY-MM-DD`). `output_type` picks the row grain
        (`EVENT` / `ENROLLMENT` / `TRACKED_ENTITY_INSTANCE`). `event_status`
        and `program_status` filter by state. `extra_params` covers the rest
        (`aggregationType`, `outputIdScheme`, `ouMode`, `coordinatesOnly`, ...).

        Raises `Dhis2ApiError` on 4xx / 5xx.
        """
        return await self._events_query(
            "events",
            program,
            stage=stage,
            dimension=dimension,
            filter=filter,
            start_date=start_date,
            end_date=end_date,
            output_type=output_type,
            event_status=event_status,
            program_status=program_status,
            page=page,
            page_size=page_size,
            extra_params=extra_params,
        )

    async def enrollment_query(
        self,
        program: str,
        *,
        dimension: str | Sequence[str] | None = None,
        filter: str | Sequence[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        output_type: str | None = None,
        program_status: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
        extra_params: Mapping[str, Any] | None = None,
    ) -> Grid:
        """Run an enrollment analytics query and return the parsed `Grid` envelope.

        GET `/api/analytics/enrollments/query/<program>` — the enrollment-level
        analytics read (one row per enrollment, program-indicator and
        repeated-stage values flattened across the enrollment). `dimension` and
        `filter` follow the same single-or-sequence, pre-formed-token shape as
        `event_query`. `start_date` / `end_date` bound the enrollment date.
        `program_status` filters by enrollment state. `extra_params` covers the
        rest of the surface.

        Raises `Dhis2ApiError` on 4xx / 5xx.
        """
        return await self._events_query(
            "enrollments",
            program,
            stage=None,
            dimension=dimension,
            filter=filter,
            start_date=start_date,
            end_date=end_date,
            output_type=output_type,
            event_status=None,
            program_status=program_status,
            page=page,
            page_size=page_size,
            extra_params=extra_params,
        )

    async def _events_query(
        self,
        mode: str,
        program: str,
        *,
        stage: str | None,
        dimension: str | Sequence[str] | None,
        filter: str | Sequence[str] | None,
        start_date: str | None,
        end_date: str | None,
        output_type: str | None,
        event_status: str | None,
        program_status: str | None,
        page: int | None,
        page_size: int | None,
        extra_params: Mapping[str, Any] | None,
    ) -> Grid:
        """Build + run an `/api/analytics/{events,enrollments}/query/<program>` GET."""
        params: dict[str, Any] = {}
        _repeat(params, "dimension", dimension)
        _repeat(params, "filter", filter)
        if stage is not None:
            params["stage"] = stage
        if start_date is not None:
            params["startDate"] = start_date
        if end_date is not None:
            params["endDate"] = end_date
        if output_type is not None:
            params["outputType"] = output_type
        if event_status is not None:
            params["eventStatus"] = event_status
        if program_status is not None:
            params["programStatus"] = program_status
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["pageSize"] = page_size
        if extra_params:
            params.update(extra_params)
        # `.json` suffix keeps the events/enrollments query on the JSON grid
        # response across majors (BUGS.md #1).
        raw = await self._client.get_raw(f"/api/analytics/{mode}/query/{program}.json", params=params)
        return Grid.model_validate(raw)


def _repeat(params: dict[str, Any], key: str, value: str | Sequence[str] | None) -> None:
    """Add `value` as a single-or-repeated query param, skipping `None`."""
    if value is None:
        return
    params[key] = [value] if isinstance(value, str) else list(value)


__all__ = ["AnalyticsAccessor", "AnalyticsQuery"]
