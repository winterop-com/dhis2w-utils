"""FastMCP surface tests for the `fhir` plugin - the read-only validate tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_fhir.plugin import plugin
from dhis2w_fhir.validation.schemas import FhirValidationReport
from fastmcp import Client, FastMCP


def _server() -> FastMCP:
    """Register the fhir plugin onto a fresh FastMCP server."""
    server: FastMCP = FastMCP("fhir-mcp-test")
    plugin.register_mcp(server)
    return server


async def test_registers_only_the_read_tool() -> None:
    """Scaffolding/generation are CLI-only; MCP exposes exactly the read-only validate."""
    async with Client(_server()) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    assert set(tools) == {"fhir_validate"}
    annotations = tools["fhir_validate"].annotations
    assert annotations is not None and annotations.readOnlyHint is True


async def test_validate_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    """`fhir_validate` resolves the profile and returns the service report."""
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.setenv("DHIS2_URL", "https://dhis2.example")
    monkeypatch.setenv("DHIS2_PAT", "d2p_test")
    report = FhirValidationReport(option_set_count=2, option_count=9)
    mock = AsyncMock(return_value=report)
    with patch("dhis2w_fhir.service.validate_codes", new=mock):
        async with Client(_server()) as client:
            result = await client.call_tool("fhir_validate", {})
    mock.assert_awaited_once()
    structured = result.structured_content or {}
    assert structured.get("option_set_count") == 2
