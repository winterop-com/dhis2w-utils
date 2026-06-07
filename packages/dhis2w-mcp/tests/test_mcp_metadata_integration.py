"""MCP metadata tool tests via in-process FastMCP Client against local DHIS2."""

from __future__ import annotations

import json

import pytest
from dhis2w_mcp.server import build_server
from fastmcp import Client

pytestmark = pytest.mark.slow


def _extract_payload(result: object) -> object:
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        if isinstance(structured, dict) and "result" in structured:
            return structured["result"]
        return structured
    data = getattr(result, "data", None)
    if data is not None and hasattr(data, "model_dump"):
        return data.model_dump()
    if data is not None:
        return data
    content = getattr(result, "content", None)
    if isinstance(content, list) and content:
        first = content[0]
        text = getattr(first, "text", None)
        if isinstance(text, str):
            return json.loads(text)
    raise AssertionError(f"unexpected FastMCP result shape: {result!r}")


async def test_list_metadata_types_tool(local_url: str, local_pat: str | None, monkeypatch: pytest.MonkeyPatch) -> None:
    """List metadata types tool."""
    if not local_pat:
        pytest.skip("DHIS2_PAT not set — run `make dhis2-run` to populate")
    monkeypatch.setenv("DHIS2_URL", local_url)
    monkeypatch.setenv("DHIS2_PAT", local_pat)
    server = build_server()
    async with Client(server) as client:
        result = await client.call_tool("metadata_type_list", {})
    types = _extract_payload(result)
    assert isinstance(types, list)
    assert "dataElements" in types
    assert "indicators" in types


async def test_list_metadata_tool_returns_items(
    local_url: str, local_pat: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """List metadata tool returns items."""
    if not local_pat:
        pytest.skip("DHIS2_PAT not set — run `make dhis2-run` to populate")
    monkeypatch.setenv("DHIS2_URL", local_url)
    monkeypatch.setenv("DHIS2_PAT", local_pat)
    server = build_server()
    async with Client(server) as client:
        result = await client.call_tool(
            "metadata_list",
            {"resource": "dataElements", "fields": "id,name", "page_size": 3},
        )
    items = _extract_payload(result)
    assert isinstance(items, list)
    assert len(items) <= 3
