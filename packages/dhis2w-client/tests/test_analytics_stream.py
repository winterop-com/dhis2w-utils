"""Tests for `Dhis2Client.analytics.stream_to` — streaming analytics exports."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import respx
from dhis2w_client import AuthenticationError, BasicAuth, Dhis2ApiError, Dhis2Client


def _auth() -> BasicAuth:
    """Throwaway auth for test clients."""
    return BasicAuth(username="a", password="b")


@respx.mock
async def test_aggregate_returns_parsed_grid_with_repeated_dimensions(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`aggregate(dx=, pe=, ou=)` builds repeated `dimension=` params and validates the response into a `Grid`."""
    mock_system_info(server_version)
    grid_payload = {
        "headers": [{"name": "dx", "column": "dx"}, {"name": "value", "column": "value"}],
        "rows": [["fbfJHSPpUQD", "42"]],
        "metaData": {"items": {}, "dimensions": {}},
    }
    route = respx.get("https://dhis2.example/api/analytics.json").mock(
        return_value=httpx.Response(200, json=grid_payload),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        grid = await client.analytics.aggregate(
            dx=["fbfJHSPpUQD", "cYeuwXTCPkU"],
            pe="LAST_12_MONTHS",
            ou="ImspTQPwCqd",
            extra_params={"aggregationType": "SUM"},
        )
    finally:
        await client.close()

    request_url = route.calls.last.request.url
    dimension_values = request_url.params.get_list("dimension")
    assert dimension_values == ["dx:fbfJHSPpUQD;cYeuwXTCPkU", "pe:LAST_12_MONTHS", "ou:ImspTQPwCqd"]
    assert request_url.params["aggregationType"] == "SUM"
    assert grid.headers and grid.headers[0].name == "dx"
    assert grid.rows == [["fbfJHSPpUQD", "42"]]


@respx.mock
async def test_aggregate_omits_dimensions_that_are_none(
    server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`None` arguments don't add empty dimension entries."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/analytics.json").mock(
        return_value=httpx.Response(200, json={"headers": [], "rows": []}),
    )
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.analytics.aggregate(dx="fbfJHSPpUQD")
    finally:
        await client.close()

    dimension_values = route.calls.last.request.url.params.get_list("dimension")
    assert dimension_values == ["dx:fbfJHSPpUQD"]


@respx.mock
async def test_stream_to_writes_full_body_to_disk(
    tmp_path: Path, server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Single-chunk response streams end-to-end; bytes-on-disk match the canned body."""
    mock_system_info(server_version)
    payload = b'{"headers":[],"rows":[[1],[2],[3]]}'
    respx.get("https://dhis2.example/api/analytics.json").mock(
        return_value=httpx.Response(200, content=payload),
    )

    destination = tmp_path / "out.json"
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        written = await client.analytics.stream_to(
            destination,
            params={"dimension": ["dx:DEancVisit1", "pe:LAST_12_MONTHS"]},
        )
    finally:
        await client.close()

    assert written == len(payload)
    assert destination.read_bytes() == payload


@respx.mock
async def test_stream_to_forwards_repeated_dimension_params(
    tmp_path: Path, server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """List-value params land on the wire as repeated query params, as DHIS2 expects."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/analytics.json").mock(
        return_value=httpx.Response(200, content=b"{}"),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.analytics.stream_to(
            tmp_path / "out.json",
            params={"dimension": ["dx:X", "pe:Y", "ou:Z"]},
        )
    finally:
        await client.close()

    dimension_values = route.calls.last.request.url.params.get_list("dimension")
    assert dimension_values == ["dx:X", "pe:Y", "ou:Z"]


@respx.mock
async def test_stream_to_accepts_list_of_tuples_params(
    tmp_path: Path, server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`params` also accepts `list[tuple[str, Any]]` — same repeated-param semantics."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/analytics.csv").mock(
        return_value=httpx.Response(200, content=b"a,b,c\n1,2,3\n"),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.analytics.stream_to(
            tmp_path / "out.csv",
            params=[("dimension", "dx:X"), ("dimension", "pe:Y")],
            endpoint="/api/analytics.csv",
        )
    finally:
        await client.close()

    assert route.calls.last.request.url.params.get_list("dimension") == ["dx:X", "pe:Y"]


@respx.mock
async def test_stream_to_writes_large_body_without_buffering(
    tmp_path: Path, server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """A payload larger than the chunk_size reassembles correctly on disk."""
    mock_system_info(server_version)
    # 10 KB synthetic CSV — larger than chunk_size so aiter_bytes loops.
    payload = b"a,b,c,d\n" + (b"1,2,3,4\n" * 1000)
    respx.get("https://dhis2.example/api/analytics.csv").mock(
        return_value=httpx.Response(200, content=payload),
    )

    destination = tmp_path / "big.csv"
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        written = await client.analytics.stream_to(
            destination,
            params={"dimension": ["dx:X"]},
            endpoint="/api/analytics.csv",
            chunk_size=512,  # force multi-iteration read
        )
    finally:
        await client.close()

    assert written == len(payload)
    assert destination.read_bytes() == payload


@respx.mock
async def test_stream_to_creates_missing_parent_dirs(
    tmp_path: Path, server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Destination's parent directories are created if missing — no pre-mkdir needed."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/analytics.json").mock(
        return_value=httpx.Response(200, content=b"{}"),
    )

    destination = tmp_path / "nested" / "deeper" / "out.json"
    assert not destination.parent.exists()

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        await client.analytics.stream_to(destination, params={"dimension": ["dx:X"]})
    finally:
        await client.close()

    assert destination.parent.is_dir()
    assert destination.read_bytes() == b"{}"


@respx.mock
async def test_stream_to_raises_dhis2_api_error_on_4xx(
    tmp_path: Path, server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Server 4xx short-circuits without writing a partial file."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/analytics.json").mock(
        return_value=httpx.Response(400, json={"httpStatus": "Bad Request", "message": "invalid dimension"}),
    )

    destination = tmp_path / "out.json"
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        with pytest.raises(Dhis2ApiError) as exc_info:
            await client.analytics.stream_to(destination, params={"dimension": ["bad"]})
    finally:
        await client.close()

    assert exc_info.value.status_code == 400
    assert not destination.exists()


@respx.mock
async def test_stream_to_raises_authentication_error_on_401(
    tmp_path: Path, server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """401 on the analytics endpoint surfaces as `AuthenticationError`, not `Dhis2ApiError`."""
    mock_system_info(server_version)
    respx.get("https://dhis2.example/api/analytics.json").mock(
        return_value=httpx.Response(401, text="unauthorized"),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        with pytest.raises(AuthenticationError):
            await client.analytics.stream_to(tmp_path / "out.json", params={"dimension": ["dx:X"]})
    finally:
        await client.close()


@respx.mock
async def test_stream_to_supports_non_standard_endpoint(
    tmp_path: Path, server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """`/api/analytics/rawData.json` and similar sub-endpoints work via the `endpoint` arg."""
    mock_system_info(server_version)
    route = respx.get("https://dhis2.example/api/analytics/rawData.json").mock(
        return_value=httpx.Response(200, content=b'{"rows":[]}'),
    )

    client = Dhis2Client("https://dhis2.example", auth=_auth())
    try:
        await client.connect()
        written = await client.analytics.stream_to(
            tmp_path / "raw.json",
            params={"dimension": ["dx:X"]},
            endpoint="/api/analytics/rawData.json",
        )
    finally:
        await client.close()

    assert route.call_count == 1
    assert written == 11  # len(b'{"rows":[]}')


async def test_stream_to_rejects_unconnected_client(
    tmp_path: Path, server_version: str, mock_system_info: Callable[..., None]
) -> None:
    """Calling before `connect()` raises a clear RuntimeError."""
    client = Dhis2Client("https://dhis2.example", auth=_auth())
    with pytest.raises(RuntimeError, match="not connected"):
        await client.analytics.stream_to(tmp_path / "out.json", params={"dimension": ["dx:X"]})
