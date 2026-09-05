"""Tests for `Dhis2Client.data_values.export` and the generic `Dhis2Client.stream` sink."""

from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import respx
from dhis2w_client import AuthenticationError, BasicAuth, Dhis2ApiError, Dhis2Client


def _auth() -> BasicAuth:
    """Throwaway auth for test clients."""
    return BasicAuth(username="a", password="b")


def _dvs_payload() -> dict[str, object]:
    """Canned /api/dataValueSets export envelope."""
    return {
        "dataSet": "BfMAe6Itzgt",
        "period": "202401",
        "orgUnit": "DiszpKrYNg8",
        "dataValues": [
            {"dataElement": "FTRrcoaog83", "value": "12"},
            {"dataElement": "eY5ehpbEsB7", "value": "34"},
        ],
    }


@respx.mock
async def test_export_builds_repeated_params_and_parses_envelope(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`export(...)` repeats dataSet/period/orgUnit params and validates into a `DataValueSet`."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/dataValueSets").mock(
        return_value=httpx.Response(200, json=_dvs_payload()),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        result = await client.data_values.export(
            data_set=["BfMAe6Itzgt", "V8MHeZHIrcP"],
            period="202401",
            org_unit="DiszpKrYNg8",
            children=True,
            last_updated_duration="2h",
        )
    finally:
        await client.close()

    params = route.calls.last.request.url.params
    assert params.get_list("dataSet") == ["BfMAe6Itzgt", "V8MHeZHIrcP"]
    assert params.get_list("period") == ["202401"]
    assert params["orgUnit"] == "DiszpKrYNg8"
    assert params["children"] == "true"
    assert params["lastUpdatedDuration"] == "2h"
    assert result.dataSet == "BfMAe6Itzgt"
    assert result.dataValues is not None
    assert [dv.value for dv in result.dataValues] == ["12", "34"]


@respx.mock
async def test_export_omits_none_params(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """Unset params never reach the wire; a bare export sends no query string."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/dataValueSets").mock(
        return_value=httpx.Response(200, json={"dataValues": []}),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.data_values.export()
    finally:
        await client.close()

    assert str(route.calls.last.request.url.params) == ""


@respx.mock
async def test_export_forwards_extra_params(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """`extra_params` covers the rest of the surface (idScheme, includeDeleted, ...)."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/dataValueSets").mock(
        return_value=httpx.Response(200, json={"dataValues": []}),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.data_values.export(
            data_set="BfMAe6Itzgt",
            extra_params={"idScheme": "CODE", "includeDeleted": "true"},
        )
    finally:
        await client.close()

    params = route.calls.last.request.url.params
    assert params["idScheme"] == "CODE"
    assert params["includeDeleted"] == "true"


@respx.mock
async def test_stream_writes_export_to_file_like_sink(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """The dirigent case: stream a dataValueSet export straight to a file-like sink, unbuffered."""
    mock_system_info(server_version)
    payload = b'{"dataValues":[{"dataElement":"FTRrcoaog83","value":"12"}]}'
    route = respx.get("https://dhis2.example/api/dataValueSets.json").mock(
        return_value=httpx.Response(200, content=payload),
    )

    sink = io.BytesIO()
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        written = await client.stream(
            "GET",
            "/api/dataValueSets.json",
            sink,
            params={"dataSet": ["BfMAe6Itzgt"], "period": ["202401"]},
        )
    finally:
        await client.close()

    assert written == len(payload)
    assert sink.getvalue() == payload
    assert route.calls.last.request.url.params.get_list("dataSet") == ["BfMAe6Itzgt"]


@respx.mock
async def test_stream_writes_to_callable_sink(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """A plain callable sink receives each chunk; multi-chunk bodies reassemble in order."""
    mock_system_info(server_version)
    payload = b"a,b,c\n" + (b"1,2,3\n" * 500)  # larger than chunk_size below
    respx.get("https://dhis2.example/api/analytics.csv").mock(
        return_value=httpx.Response(200, content=payload),
    )

    chunks: list[bytes] = []
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        written = await client.stream(
            "GET",
            "/api/analytics.csv",
            chunks.append,
            params=[("dimension", "dx:X")],
            chunk_size=256,
        )
    finally:
        await client.close()

    assert len(chunks) > 1
    assert b"".join(chunks) == payload
    assert written == len(payload)


@respx.mock
async def test_stream_awaits_async_writer_sink(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """An async `.write` coroutine is awaited for every chunk."""
    mock_system_info(server_version)
    payload = b'{"rows":[]}'
    respx.get("https://dhis2.example/api/dataValueSets.json").mock(
        return_value=httpx.Response(200, content=payload),
    )

    class AsyncSink:
        def __init__(self) -> None:
            self.buffer = bytearray()

        async def write(self, data: bytes) -> None:
            self.buffer.extend(data)

    sink = AsyncSink()
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        written = await client.stream("GET", "/api/dataValueSets.json", sink)
    finally:
        await client.close()

    assert bytes(sink.buffer) == payload
    assert written == len(payload)


@respx.mock
async def test_stream_writes_to_path_sink(
    tmp_path: Path, server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """A Path sink creates parent dirs and writes the body — same as `analytics.stream_to`."""
    mock_system_info(server_version)
    payload = b'{"dataValues":[]}'
    respx.get("https://dhis2.example/api/dataValueSets.json").mock(
        return_value=httpx.Response(200, content=payload),
    )

    destination = tmp_path / "nested" / "export.json"
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        written = await client.stream("GET", "/api/dataValueSets.json", destination)
    finally:
        await client.close()

    assert written == len(payload)
    assert destination.read_bytes() == payload


@respx.mock
async def test_stream_raises_dhis2_api_error_on_4xx(server_version: str, mock_system_info: Callable[..., None]) -> None:
    """A 4xx short-circuits before any chunk is written to the sink."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/dataValueSets.json").mock(
        return_value=httpx.Response(409, json={"httpStatus": "Conflict", "message": "boom"}),
    )

    sink = io.BytesIO()
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        with pytest.raises(Dhis2ApiError) as exc_info:
            await client.stream("GET", "/api/dataValueSets.json", sink)
    finally:
        await client.close()

    assert exc_info.value.status_code == 409
    assert sink.getvalue() == b""


@respx.mock
async def test_stream_raises_authentication_error_on_401(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """401 surfaces as `AuthenticationError`, not `Dhis2ApiError`."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/dataValueSets.json").mock(
        return_value=httpx.Response(401, text="unauthorized"),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        with pytest.raises(AuthenticationError):
            await client.stream("GET", "/api/dataValueSets.json", io.BytesIO())
    finally:
        await client.close()


async def test_stream_rejects_unconnected_client() -> None:
    """Calling before `connect()` raises a clear RuntimeError."""
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    with pytest.raises(RuntimeError, match="not connected"):
        await client.stream("GET", "/api/dataValueSets.json", io.BytesIO())
