"""FastMCP surface tests for the `fhir` plugin (v42 tree; parity is covered in runtime tests)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_fhir import GenerateReport
from dhis2w_fhir.plugin import plugin
from fastmcp import Client, FastMCP


def _server() -> FastMCP:
    """Register the fhir plugin onto a fresh FastMCP server."""
    server: FastMCP = FastMCP("fhir-mcp-test")
    plugin.register_mcp(server)
    return server


async def test_registers_four_tools() -> None:
    """The plugin exposes init, the two generate tools, and the read-only validate tool."""
    async with Client(_server()) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    assert set(tools) == {"fhir_init", "fhir_generate_option_sets", "fhir_generate_org_units", "fhir_validate"}
    annotations = tools["fhir_validate"].annotations
    assert annotations is not None and annotations.readOnlyHint is True


async def test_fhir_init_scaffolds(tmp_path: Path) -> None:
    """`fhir_init` writes the scaffold and returns the report."""
    async with Client(_server()) as client:
        result = await client.call_tool("fhir_init", {"directory": str(tmp_path / "project")})
    assert (tmp_path / "project" / "fhir.toml").exists()
    structured = result.structured_content or {}
    assert "fhir.toml" in structured.get("created_files", [])


async def test_generate_option_sets_dispatches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`fhir_generate_option_sets` loads the project from `project_directory` and calls the service."""
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.setenv("DHIS2_URL", "https://dhis2.example")
    monkeypatch.setenv("DHIS2_PAT", "d2p_test")
    async with Client(_server()) as client:
        await client.call_tool("fhir_init", {"directory": str(tmp_path)})
        report = GenerateReport(project_root=tmp_path, target_directory="terminology")
        mock = AsyncMock(return_value=report)
        with patch("dhis2w_fhir.service.generate_option_sets", new=mock):
            result = await client.call_tool("fhir_generate_option_sets", {"project_directory": str(tmp_path)})
    mock.assert_awaited_once()
    structured = result.structured_content or {}
    assert structured.get("target_directory") == "terminology"
