"""Read-only mode for the full dhis2-mcp server (env DHIS2_MCP_READONLY)."""

from __future__ import annotations

import pytest
from dhis2w_mcp.readonly import is_read_tool, readonly_enabled
from dhis2w_mcp.server import build_server
from fastmcp import Client


@pytest.mark.parametrize(
    ("name", "is_read"),
    [
        ("metadata_count", True),
        ("system_whoami", True),
        ("metadata_data_element_get", True),
        ("metadata_data_element_create", False),
        ("system_settings_set", False),
        ("data_tracker_push", False),
        ("metadata_data_set_delete", False),
    ],
)
def test_is_read_tool_classifies_by_verb(name: str, is_read: bool) -> None:
    """A tool is read-only iff its trailing verb is a known read (fail-closed otherwise)."""
    assert is_read_tool(name) is is_read


@pytest.mark.parametrize(
    ("value", "enabled"),
    [("1", True), ("true", True), ("YES", True), ("on", True), ("", False), ("0", False), ("off", False)],
)
def test_readonly_enabled_reads_env(monkeypatch: pytest.MonkeyPatch, value: str, enabled: bool) -> None:
    """readonly_enabled honours the truthy env conventions."""
    monkeypatch.setenv("DHIS2_MCP_READONLY", value)
    assert readonly_enabled() is enabled


_SECURITY_READ_TOOLS = frozenset({"security_settings", "security_authorities", "security_version"})


async def test_security_read_tools_visible_under_readonly(monkeypatch: pytest.MonkeyPatch) -> None:
    """The three security read tools are visible under DHIS2_MCP_READONLY via readOnlyHint annotation.

    Their trailing verbs (settings/authorities/version) are not in READ_VERBS, so the verb
    heuristic alone would fail-close them. The readOnlyHint=True annotation on each tool
    bypasses the heuristic and keeps them visible under read-only mode.
    """
    monkeypatch.setenv("DHIS2_MCP_READONLY", "1")
    async with Client(build_server()) as client:
        names = {tool.name for tool in await client.list_tools()}
    missing = _SECURITY_READ_TOOLS - names
    assert not missing, f"security read tools hidden under read-only mode: {missing}"


def _client_tool_is_read(tool: object) -> bool:
    """Classify a client-side mcp.types.Tool as read-only: readOnlyHint annotation takes priority."""
    annotations = getattr(tool, "annotations", None)
    hint = getattr(annotations, "readOnlyHint", None) if annotations else None
    if hint is not None:
        return bool(hint)
    return is_read_tool(getattr(tool, "name", ""))


async def test_readonly_server_hides_write_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """With DHIS2_MCP_READONLY set, list_tools exposes only read tools; without it, writes are present."""
    monkeypatch.setenv("DHIS2_MCP_READONLY", "1")
    async with Client(build_server()) as client:
        tools = await client.list_tools()
    names = [tool.name for tool in tools]
    assert names, "expected some read tools"
    assert all(_client_tool_is_read(tool) for tool in tools)
    assert not any(name.endswith(("_create", "_set", "_delete", "_update", "_push", "_import")) for name in names)

    monkeypatch.delenv("DHIS2_MCP_READONLY", raising=False)
    async with Client(build_server()) as client:
        open_names = [tool.name for tool in await client.list_tools()]
    assert any(name.endswith("_create") for name in open_names), "writes should be present without read-only mode"
