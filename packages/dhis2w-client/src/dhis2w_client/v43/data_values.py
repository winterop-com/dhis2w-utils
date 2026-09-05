"""Streaming data-value-set import — `client.data_values.stream`.

DHIS2's `POST /api/dataValueSets` accepts JSON, XML, CSV, and ADX payloads.
For a 100k-row push (a typical month-end aggregate upload), buffering the
whole body in Python memory before the POST is the thing to avoid:

- A 100k-row JSON payload sits at ~30-60 MB on the wire, and the Python
  parsed shape is 3-5x that — so ~150 MB resident just to stage the
  request.
- The same payload on CSV is ~8 MB; XML is in between.

`client.data_values.stream(source, content_type)` feeds httpx's chunked
transfer encoding directly, so the payload never sits fully in memory
on the client side. The server consumes it as it arrives.

`source` accepts any of:

- `pathlib.Path` — opens the file and chunks it through.
- `bytes` / `bytearray` — single-shot for callers who already have the
  body assembled but want the typed `WebMessageResponse` envelope.
- `Iterable[bytes]` / `AsyncIterable[bytes]` — pass-through for
  generators that build the body on the fly (e.g. DB-row → CSV line).
- File-like with `.read(size) -> bytes` (sync or async) — adapted to a
  chunk iterator.

Supported `content_type` values map to the DHIS2-accepted MIME types:

- `application/json` (default)
- `application/xml`
- `application/csv` (also accepted: `text/csv`)
- `application/adx+xml`
"""

from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator, Iterable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dhis2w_client.generated.v43.oas import DataValue, DataValueSet
from dhis2w_client.v43.envelopes import WebMessageResponse

if TYPE_CHECKING:
    from dhis2w_client.v43.client import Dhis2Client


_DEFAULT_CHUNK_SIZE = 64 * 1024  # 64 KiB — balances syscall count vs chunk overhead.

StreamSource = Path | bytes | bytearray | memoryview | Iterable[bytes] | AsyncIterable[bytes]


class DataValuesAccessor:
    """`Dhis2Client.data_values` — streaming uploads to `/api/dataValueSets`.

    Stateless wrapper over the streaming POST path. Stay here for the large
    import cases; use `dhis2w_core.plugins.aggregate.service.push_data_values`
    when the payload is already a small in-memory list of typed data values.
    """

    def __init__(self, client: Dhis2Client) -> None:
        """Bind to the sharing client."""
        self._client = client

    async def stream(
        self,
        source: StreamSource,
        *,
        content_type: str = "application/json",
        dry_run: bool = False,
        preheat_cache: bool = True,
        import_strategy: str | None = None,
        id_scheme: str | None = None,
        data_element_id_scheme: str | None = None,
        org_unit_id_scheme: str | None = None,
        skip_audit: bool = False,
        async_job: bool = False,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
    ) -> WebMessageResponse:
        """Stream `source` to `POST /api/dataValueSets` and return the typed envelope.

        `content_type` picks which DHIS2 parser handles the body (JSON / XML /
        CSV / ADX). Every param from the standard `/api/dataValueSets` surface
        is forwarded via query string:

        - `dry_run` → `dryRun=true`: validate without committing.
        - `preheat_cache=False` → `preheatCache=false`.
        - `import_strategy`: `CREATE` / `UPDATE` / `CREATE_AND_UPDATE` / `DELETE`.
        - `id_scheme` / `data_element_id_scheme` / `org_unit_id_scheme`: pick
          the identifier scheme for the payload (`UID` / `CODE` / `NAME` / ...).
        - `skip_audit=True` → `skipAudit=true`.
        - `async_job=True` → `async=true`: DHIS2 queues the import as a job
          and the returned envelope carries `response.jobType` / `response.id`.
          Poll with `client.tasks.await_completion(envelope.task_ref())`.

        Returns a `WebMessageResponse`. For synchronous imports,
        `envelope.import_count()` gives `ImportCount.imported / updated /
        ignored / deleted`; `envelope.conflicts()` lists per-row rejections.
        Async imports return the task-ref envelope — poll it to completion
        to get the final report from DHIS2.
        """
        params: dict[str, Any] = {}
        if dry_run:
            params["dryRun"] = "true"
        if not preheat_cache:
            params["preheatCache"] = "false"
        if import_strategy is not None:
            params["importStrategy"] = import_strategy
        if id_scheme is not None:
            params["idScheme"] = id_scheme
        if data_element_id_scheme is not None:
            params["dataElementIdScheme"] = data_element_id_scheme
        if org_unit_id_scheme is not None:
            params["orgUnitIdScheme"] = org_unit_id_scheme
        if skip_audit:
            params["skipAudit"] = "true"
        if async_job:
            params["async"] = "true"

        content = _coerce_stream_source(source, chunk_size=chunk_size)
        response = await self._client._request(  # noqa: SLF001 — accessor is intentionally tight with the client
            "POST",
            "/api/dataValueSets",
            params=params,
            content=content,
            extra_headers={"Content-Type": content_type},
        )
        raw = response.json() if response.content else {}
        return WebMessageResponse.model_validate(raw)

    async def export(
        self,
        *,
        data_set: str | Sequence[str] | None = None,
        period: str | Sequence[str] | None = None,
        org_unit: str | Sequence[str] | None = None,
        children: bool = False,
        start_date: str | None = None,
        end_date: str | None = None,
        last_updated: str | None = None,
        last_updated_duration: str | None = None,
        extra_params: Mapping[str, Any] | None = None,
    ) -> DataValueSet:
        """GET `/api/dataValueSets` and return the parsed `DataValueSet` envelope.

        The read side of the import handled by `stream()`. `data_set`, `period`,
        and `org_unit` each accept a single id or a sequence of ids, and repeat
        as `dataSet=`/`period=`/`orgUnit=` query params the way DHIS2 expects.

        - `children=True` -> `children=true`: include the org units below each
          `org_unit` in the export.
        - `start_date` / `end_date` (`YYYY-MM-DD`): export by date range instead
          of by `period`.
        - `last_updated` (`YYYY-MM-DD`) / `last_updated_duration` (e.g. `2h`,
          `1d`): export only values touched since then.
        - `extra_params` covers the rest of the surface (`idScheme`,
          `dataElementIdScheme`, `includeDeleted`, `dataElementGroup`,
          `orgUnitGroup`, ...). Pass a flat mapping or a list of 2-tuples.

        Buffers the whole response into a typed `DataValueSet`. For a large
        export, stream it straight to storage with
        `client.stream("GET", "/api/dataValueSets.json", sink, params=...)`
        instead of materialising every row in memory.

        Raises `Dhis2ApiError` on 4xx / 5xx.
        """
        params: dict[str, Any] = {}
        for key, value in (("dataSet", data_set), ("period", period), ("orgUnit", org_unit)):
            if value is None:
                continue
            params[key] = [value] if isinstance(value, str) else list(value)
        if children:
            params["children"] = "true"
        if start_date is not None:
            params["startDate"] = start_date
        if end_date is not None:
            params["endDate"] = end_date
        if last_updated is not None:
            params["lastUpdated"] = last_updated
        if last_updated_duration is not None:
            params["lastUpdatedDuration"] = last_updated_duration
        if extra_params:
            params.update(extra_params)
        raw = await self._client.get_raw("/api/dataValueSets", params=params)
        return DataValueSet.model_validate(raw)

    async def import_grouped_by_dataset(
        self,
        values: Sequence[DataValue],
        *,
        chunk_size: int = 1000,
        force: bool = False,
        skip_audit: bool = False,
    ) -> list[WebMessageResponse]:
        """Import typed `DataValue`s grouped by dataset — BUGS.md #35 workaround for v43.

        v43 added auto-target dataset detection on `POST /api/dataValueSets`
        (`DefaultDataEntryService.autoTargetDataSet`). When a posted DataValue's
        DataElement is referenced by 2+ DataSets, v43 aborts the entire chunk
        with `409 E8002 Data set detection failed`. v41 + v42 silently picked
        one matching dataset and imported the row.

        Workaround: pre-fetch the DataElement → DataSet membership map, group
        the input values by their DataSet (lexicographically-first DataSet id
        when a DE belongs to multiple — deterministic across runs), and POST
        each group with an explicit envelope `{"dataSet": "<id>", "dataValues":
        [...]}`. This shape is accepted by every DHIS2 major.

        Splits each per-dataset group into `chunk_size` rows per POST so the
        body stays inside httpx's 300 s read timeout. Returns one
        `WebMessageResponse` per chunk; callers that want aggregate counts
        should walk `import_count()` across the list and sum.

        Skips values whose DataElement isn't in any DataSet (counted in the
        first response's import-count under `ignored`).
        """
        dataelement_to_dataset = await self._build_dataelement_to_dataset()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for value in values:
            if value.dataElement is None:
                continue
            dataset_id = dataelement_to_dataset.get(value.dataElement)
            if dataset_id is None:
                continue
            grouped.setdefault(dataset_id, []).append(value.model_dump(by_alias=True, exclude_none=True, mode="json"))
        params: dict[str, Any] = {}
        if force:
            params["force"] = "true"
        if skip_audit:
            params["skipAudit"] = "true"
        responses: list[WebMessageResponse] = []
        for dataset_id, dumped in grouped.items():
            for start in range(0, len(dumped), chunk_size):
                chunk = dumped[start : start + chunk_size]
                raw = await self._client._request(  # noqa: SLF001
                    "POST",
                    "/api/dataValueSets",
                    params=params,
                    json={"dataSet": dataset_id, "dataValues": chunk},
                )
                body = raw.json() if raw.content else {}
                responses.append(WebMessageResponse.model_validate(body))
        return responses

    async def _build_dataelement_to_dataset(self) -> dict[str, str]:
        """Map every DE id to one of its DataSets (lexicographically-first when multiple).

        Used by `import_grouped_by_dataset` to scope each POST chunk to a
        single DataSet, avoiding v43's auto-target rejection (BUGS.md #35).
        """
        raw = await self._client.get_raw(
            "/api/dataSets",
            params={"fields": "id,dataSetElements[dataElement[id]]", "paging": "false"},
        )
        members: dict[str, list[str]] = {}
        for dataset in raw.get("dataSets") or []:
            dataset_id = dataset.get("id")
            if not isinstance(dataset_id, str):
                continue
            for entry in dataset.get("dataSetElements") or []:
                element = (entry.get("dataElement") or {}).get("id")
                if isinstance(element, str):
                    members.setdefault(element, []).append(dataset_id)
        return {element_id: sorted(dataset_ids)[0] for element_id, dataset_ids in members.items()}


def _coerce_stream_source(source: StreamSource, *, chunk_size: int) -> bytes | AsyncIterable[bytes]:
    """Map `StreamSource` to an httpx-compatible `content=` shape.

    `httpx.AsyncClient` requires streamed bodies to be `AsyncIterable[bytes]`
    (sync iterables are rejected). Every non-bytes source normalises to an
    async iterator that yields chunks; single-shot bytes pass through
    unchanged for the common "already have the body" case.
    """
    if isinstance(source, Path):
        return _async_file_chunks(source, chunk_size=chunk_size)
    if isinstance(source, (bytes, bytearray, memoryview)):
        return bytes(source)
    if isinstance(source, AsyncIterable):
        return _passthrough_async(source)
    if isinstance(source, Iterable):  # pyright: ignore[reportUnnecessaryIsInstance]
        return _sync_to_async(source)
    # Runtime fallback for callers that bypass the StreamSource type annotation.
    raise TypeError(
        f"unsupported stream source type: {type(source).__name__}. "
        "Pass a pathlib.Path, bytes, Iterable[bytes], or AsyncIterable[bytes].",
    )


async def _async_file_chunks(path: Path, *, chunk_size: int) -> AsyncIterator[bytes]:
    """Yield `chunk_size` bytes at a time from `path` via an async iterator.

    File IO itself is synchronous (Python's stdlib can't do true async file
    reads without `aiofiles`); the async iterator surface is what httpx's
    streamed-upload path requires.
    """
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                return
            yield chunk


def _sync_to_async(source: Iterable[bytes]) -> AsyncIterator[bytes]:
    """Wrap a sync iterable as async — needed for httpx.AsyncClient streaming."""

    async def _generator() -> AsyncIterator[bytes]:
        for chunk in source:
            yield bytes(chunk)

    return _generator()


async def _passthrough_async(source: AsyncIterable[bytes]) -> AsyncIterator[bytes]:
    """Adapt an async iterable into one that httpx consumes."""
    async for chunk in source:
        yield bytes(chunk)


__all__ = ["DataValuesAccessor", "StreamSource"]
