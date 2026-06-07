"""Tests for `Dhis2Client.data_values.stream` — streaming `/api/dataValueSets` uploads."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import httpx
import pytest
import respx
from dhis2w_client import BasicAuth, Dhis2Client


def _auth() -> BasicAuth:
    """Throwaway auth for test clients."""
    return BasicAuth(username="a", password="b")


def _success_envelope() -> httpx.Response:
    """Canned /api/dataValueSets success envelope with an ImportCount."""
    return httpx.Response(
        200,
        json={
            "status": "OK",
            "httpStatus": "OK",
            "httpStatusCode": 200,
            "response": {
                "status": "OK",
                "importCount": {"imported": 2, "updated": 0, "ignored": 0, "deleted": 0},
            },
        },
    )


@respx.mock
async def test_stream_from_bytes_sends_payload_and_content_type(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Single-shot bytes upload — body + Content-Type header reach DHIS2 intact."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/dataValueSets").mock(
        return_value=_success_envelope(),
    )

    payload = b'{"dataValues":[{"dataElement":"DEancVisit1","value":"5"}]}'
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        envelope = await client.data_values.stream(payload, content_type="application/json")
    finally:
        await client.close()

    assert route.call_count == 1
    call = route.calls.last
    assert call.request.headers["content-type"] == "application/json"
    assert call.request.content == payload
    count = envelope.import_count()
    assert count is not None
    assert count.imported == 2


@respx.mock
async def test_stream_from_path_reads_and_uploads_file(
    tmp_path: Path, server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`Path` source reads the file in chunks and forwards every byte to DHIS2."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/dataValueSets").mock(
        return_value=_success_envelope(),
    )

    file_path = tmp_path / "values.csv"
    file_path.write_bytes(
        b"dataelement,period,orgunit,value\nDEancVisit1,202512,NORNorway01,5\nDEancVisit2,202512,NORNorway01,7\n"
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.data_values.stream(
            file_path,
            content_type="application/csv",
            chunk_size=32,  # Force multi-chunk read.
        )
    finally:
        await client.close()

    # Body should be the full file contents — httpx stitches the chunks back together.
    assert route.calls.last.request.content == file_path.read_bytes()
    assert route.calls.last.request.headers["content-type"] == "application/csv"


@respx.mock
async def test_stream_from_sync_iterable_passes_through(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Generator-style sync iterable streams without buffering the full payload in Python."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/dataValueSets").mock(
        return_value=_success_envelope(),
    )

    def chunks() -> Iterator[bytes]:
        yield b'{"dataValues":['
        yield b'{"dataElement":"DEancVisit1","value":"5"},'
        yield b'{"dataElement":"DEancVisit2","value":"7"}'
        yield b"]}"

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.data_values.stream(chunks(), content_type="application/json")
    finally:
        await client.close()

    expected = b'{"dataValues":[{"dataElement":"DEancVisit1","value":"5"},{"dataElement":"DEancVisit2","value":"7"}]}'
    assert route.calls.last.request.content == expected


@respx.mock
async def test_stream_from_async_iterable_passes_through(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Async generator source is consumed by httpx's chunked upload."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/dataValueSets").mock(
        return_value=_success_envelope(),
    )

    async def chunks() -> AsyncIterator[bytes]:
        for line in (b'{"dataValues":[', b'{"dataElement":"X","value":"1"}', b"]}"):
            yield line

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.data_values.stream(chunks(), content_type="application/json")
    finally:
        await client.close()

    assert route.calls.last.request.content == b'{"dataValues":[{"dataElement":"X","value":"1"}]}'


@respx.mock
async def test_stream_forwards_every_query_parameter(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Every knob (dry_run / preheat / strategy / id-schemes / skip-audit / async) flows to DHIS2."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/dataValueSets").mock(
        return_value=_success_envelope(),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.data_values.stream(
            b"{}",
            content_type="application/json",
            dry_run=True,
            preheat_cache=False,
            import_strategy="CREATE_AND_UPDATE",
            id_scheme="UID",
            data_element_id_scheme="CODE",
            org_unit_id_scheme="NAME",
            skip_audit=True,
            async_job=True,
        )
    finally:
        await client.close()

    params = route.calls.last.request.url.params
    assert params["dryRun"] == "true"
    assert params["preheatCache"] == "false"
    assert params["importStrategy"] == "CREATE_AND_UPDATE"
    assert params["idScheme"] == "UID"
    assert params["dataElementIdScheme"] == "CODE"
    assert params["orgUnitIdScheme"] == "NAME"
    assert params["skipAudit"] == "true"
    assert params["async"] == "true"


@respx.mock
async def test_stream_default_params_omit_optional_flags(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Defaults don't emit stray parameters — dryRun / async / skipAudit absent unless set."""
    mock_system_info(server_version)
    route = respx.post("https://dhis2.example/api/dataValueSets").mock(
        return_value=_success_envelope(),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.data_values.stream(b"{}", content_type="application/json")
    finally:
        await client.close()

    params = route.calls.last.request.url.params
    assert "dryRun" not in params
    assert "preheatCache" not in params
    assert "importStrategy" not in params
    assert "async" not in params


async def test_stream_rejects_unknown_source_type() -> None:
    """Passing an int / dict / other surfaces a clear TypeError."""
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    with pytest.raises(TypeError, match="unsupported stream source type"):
        await client.data_values.stream(12345)  # type: ignore[arg-type]
