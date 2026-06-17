"""Unit tests for the domain-neutral router core (no live MCP servers)."""

from __future__ import annotations

import pytest
from dhis2w_mcp_router.core import Registry, ToolEntry, UpstreamServer


def _entry(name: str, server: str, bare: str, description: str) -> ToolEntry:
    """Build a ToolEntry with an empty schema for search/dispatch tests."""
    return ToolEntry(name=name, server=server, bare=bare, description=description, input_schema={})


def _registry_with(*entries: ToolEntry) -> Registry:
    """A registry pre-seeded with entries, bypassing live upstream connection."""
    registry = Registry([])
    for entry in entries:
        registry._entries[entry.name] = entry  # noqa: SLF001 — test seam for the domain-neutral search
    return registry


def test_upstream_client_config_merges_parent_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The upstream config keeps the parent environment and layers the per-server overrides on top."""
    monkeypatch.setenv("PATH", "/usr/bin")
    server = UpstreamServer(name="dhis2", command="uv", args=["run", "dhis2w-mcp"], env={"DHIS2_PROFILE": "play42"})
    cfg = server.client_config()["mcpServers"]["dhis2"]
    assert cfg["command"] == "uv"
    assert cfg["args"] == ["run", "dhis2w-mcp"]
    assert cfg["env"]["DHIS2_PROFILE"] == "play42"
    assert cfg["env"]["PATH"] == "/usr/bin"  # parent env merged, not replaced


def test_search_ranks_by_term_hits_and_excludes_misses() -> None:
    """Search ranks tools by how many query terms hit, and drops tools with zero hits."""
    registry = _registry_with(
        _entry("dhis2__metadata_data_set_create", "dhis2", "metadata_data_set_create", "Create a data set"),
        _entry("dhis2__metadata_data_element_create", "dhis2", "metadata_data_element_create", "Create a data element"),
        _entry("dhis2__system_info", "dhis2", "system_info", "System information"),
    )
    hits = registry.search("data set", limit=5)
    assert hits[0].name == "dhis2__metadata_data_set_create"  # matches both 'data' and 'set'
    assert all(hit.name != "dhis2__system_info" for hit in hits)  # no term hit -> excluded


def test_search_empty_query_lists_alphabetically() -> None:
    """An empty query is a browse: every tool, name-sorted for determinism."""
    registry = _registry_with(_entry("b__t", "b", "t", "x"), _entry("a__t", "a", "t", "x"))
    assert [hit.name for hit in registry.search("", limit=10)] == ["a__t", "b__t"]


def test_search_honours_limit() -> None:
    """Search returns at most `limit` results."""
    registry = _registry_with(*[_entry(f"s__t{i}", "s", f"t{i}", "a tool") for i in range(5)])
    assert len(registry.search("tool", limit=2)) == 2


async def test_call_unknown_tool_raises() -> None:
    """Dispatching an unregistered name is a clear KeyError pointing at search_tools."""
    registry = _registry_with(_entry("s__t", "s", "t", "x"))
    with pytest.raises(KeyError, match="unknown tool"):
        await registry.call("s__missing", {})


def test_tool_entry_summary_is_the_agent_facing_shape() -> None:
    """summary() returns exactly the name/description/schema the agent needs to call the tool."""
    entry = _entry("dhis2__system_info", "dhis2", "system_info", "System information")
    assert entry.summary() == {
        "name": "dhis2__system_info",
        "description": "System information",
        "input_schema": {},
    }


def test_readonly_registry_hides_and_refuses_writes() -> None:
    """A read-only registry drops write tools from search and refuses them at dispatch."""
    registry = Registry(
        [],
        readonly=True,
    )
    registry._entries["dhis2__metadata_count"] = _entry("dhis2__metadata_count", "dhis2", "metadata_count", "Count")  # noqa: SLF001
    registry._entries["dhis2__data_set_create"] = _entry("dhis2__data_set_create", "dhis2", "data_set_create", "Create")  # noqa: SLF001
    names = [hit.name for hit in registry.search("", limit=10)]
    assert "dhis2__metadata_count" in names  # read survives
    assert "dhis2__data_set_create" not in names  # write hidden


async def test_readonly_call_refuses_write_with_permission_error() -> None:
    """Dispatching a write tool through a read-only registry raises PermissionError."""
    registry = Registry([], readonly=True)
    registry._entries["dhis2__data_set_create"] = _entry("dhis2__data_set_create", "dhis2", "data_set_create", "Create")  # noqa: SLF001
    with pytest.raises(PermissionError, match="read-only"):
        await registry.call("dhis2__data_set_create", {})


def test_is_read_honours_annotation_then_falls_back_to_verb() -> None:
    """is_read uses the readOnlyHint annotation when present, else the bare-name verb."""
    from dhis2w_mcp_router.core import DEFAULT_READ_VERBS, ToolEntry

    by_verb_read = ToolEntry(name="s__system_info", server="s", bare="system_info", description="", input_schema={})
    by_verb_write = _entry("s__data_set_create", "s", "data_set_create", "")
    annotated_write = ToolEntry(
        name="s__looks_get", server="s", bare="looks_get", description="", input_schema={}, read_only_hint=False
    )
    assert by_verb_read.is_read(DEFAULT_READ_VERBS) is True
    assert by_verb_write.is_read(DEFAULT_READ_VERBS) is False
    assert annotated_write.is_read(DEFAULT_READ_VERBS) is False  # annotation overrides the read-looking verb


def test_per_server_readonly_denies_only_that_server() -> None:
    """A server flagged readonly denies its writes; a non-flagged server still permits writes."""
    from dhis2w_mcp_router.core import UpstreamServer

    servers = [UpstreamServer(name="play", command="x", readonly=True), UpstreamServer(name="local", command="x")]
    registry = Registry(servers)
    registry._entries["play__data_set_create"] = _entry("play__data_set_create", "play", "data_set_create", "Create")  # noqa: SLF001
    registry._entries["local__data_set_create"] = _entry("local__data_set_create", "local", "data_set_create", "Create")  # noqa: SLF001
    names = [hit.name for hit in registry.search("create", limit=10)]
    assert "local__data_set_create" in names  # writable server
    assert "play__data_set_create" not in names  # read-only server's write hidden
