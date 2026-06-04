"""Unit tests for dhis2w-mcp tool registration via FastMCP's in-process Client."""

from __future__ import annotations

from dhis2w_mcp.server import build_server
from fastmcp import Client


async def test_server_registers_expected_tools() -> None:
    """Server registers expected tools."""
    server = build_server()
    async with Client(server) as client:
        tools = await client.list_tools()
        names = {t.name for t in tools}
    expected = {
        "system_whoami",
        "system_info",
        "profile_list",
        "profile_verify",
        "metadata_type_list",
        "metadata_list",
        "metadata_count",
        "metadata_get",
        "analytics_query",
        "maintenance_refresh_analytics",
        "data_aggregate_get",
        "data_aggregate_push",
        "data_tracker_list",
        "data_tracker_event_list",
        "route_list",
        "route_create",
        "route_run",
    }
    missing = expected - names
    assert not missing, f"missing tools: {missing}"
