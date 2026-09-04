"""Streaming a response body to a caller-supplied sink — shared across version trees.

`Dhis2Client.stream(method, path, sink, ...)` GETs (or POSTs) an endpoint and
writes the response body straight to `sink` without buffering the whole body in
memory. `sink` is anything a chunk of bytes can be handed to:

- `pathlib.Path` — parent dirs are created and the file is written.
- a file-like object with `.write(bytes)` (sync or async — an async `write`
  coroutine is awaited).
- a plain callable `chunk -> None` / `chunk -> Awaitable[None]` (async is awaited).

The logic carries no version-specific behaviour — it is pure httpx + auth
plumbing over the duck-typed client — so it lives in one shared module rather
than being copied per version, exactly like `errors.py` and `_dispatch.py`.
`AnalyticsAccessor.stream_to` (Path-only) delegates here; callers that need an
arbitrary endpoint or a non-Path sink call `client.stream` directly.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable

import httpx

from dhis2w_client.errors import AuthenticationError, Dhis2ApiError, format_unauthorized_message

_DEFAULT_CHUNK_SIZE = 64 * 1024  # 64 KiB balances syscall count vs chunk overhead.

StreamParams = Mapping[str, Any] | Sequence[tuple[str, Any]]
"""DHIS2's repeated-param query shape — a mapping with list values or a list of 2-tuples."""


@runtime_checkable
class _Writable(Protocol):
    """A file-like sink: has a `write` accepting a bytes chunk (sync or async).

    `data` is positional-only so `io.BytesIO`, open binary files, and other
    stdlib writers (whose `write` is `(buffer, /)`) satisfy the protocol.
    """

    def write(self, data: bytes, /) -> Any: ...


StreamSink = Path | _Writable | Callable[[bytes], Awaitable[None] | None]
"""Where a streamed body is written: a filesystem `Path`, a `.write`-able, or a chunk callable."""


async def stream_to_sink(
    client: Any,
    method: str,
    path: str,
    sink: StreamSink,
    *,
    params: StreamParams | None = None,
    extra_headers: Mapping[str, str] | None = None,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
) -> int:
    """Stream `method path` through the client's pool into `sink`; return bytes written.

    Uses the client's shared httpx pool and fresh auth headers, so retry /
    pool-tuning / TLS config all still apply. The response body is written to
    `sink` chunk by chunk and never fully buffered.

    Raises `RuntimeError` if the client is not connected, `AuthenticationError`
    on 401, and `Dhis2ApiError` on any other 4xx / 5xx (the small error body is
    buffered so the exception carries it). A Path sink is never created when the
    request fails before the first byte is written.
    """
    http = client._http  # noqa: SLF001 — helper is intentionally tight with the client
    if http is None:
        raise RuntimeError("Dhis2Client is not connected; call connect() first")
    headers = dict(await client._auth.headers())  # noqa: SLF001
    if extra_headers:
        headers.update(extra_headers)
    # httpx.stream accepts a wider union than StreamParams — cast at the boundary
    # rather than re-expressing DHIS2's repeated-key shape.
    query_params = cast("httpx._types.QueryParamTypes | None", params)

    bytes_written = 0
    async with http.stream(method, path, params=query_params, headers=headers) as response:
        if response.status_code >= 400:
            # 4xx / 5xx responses are small; buffer the body for the error.
            await response.aread()
            body: Any
            try:
                body = response.json()
            except ValueError:
                body = response.text
            if response.status_code == 401:
                raise AuthenticationError(
                    format_unauthorized_message(method, path, response.headers.get("WWW-Authenticate"))
                )
            raise Dhis2ApiError(
                status_code=response.status_code,
                message=response.reason_phrase,
                body=body,
            )
        if isinstance(sink, Path):
            sink.parent.mkdir(parents=True, exist_ok=True)
            with sink.open("wb") as handle:
                async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                    handle.write(chunk)
                    bytes_written += len(chunk)
        else:
            write = _resolve_writer(sink)
            async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                result = write(chunk)
                if inspect.isawaitable(result):
                    await result
                bytes_written += len(chunk)
    return bytes_written


def _resolve_writer(sink: StreamSink) -> Callable[[bytes], Any]:
    """Return the per-chunk write callable for a non-Path sink."""
    write = getattr(sink, "write", None)
    if callable(write):
        return cast("Callable[[bytes], Any]", write)
    if callable(sink):
        return sink
    raise TypeError(
        f"unsupported stream sink type: {type(sink).__name__}. "
        "Pass a pathlib.Path, a file-like object with .write(bytes), or a callable taking a bytes chunk.",
    )


__all__ = ["StreamParams", "StreamSink", "stream_to_sink"]
