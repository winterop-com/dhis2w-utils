"""FastMCP server exposing the router's two meta-tools: `search_tools` and `call_tool`.

An agent points at this one server and sees two tools instead of the hundreds across every upstream:
it calls `search_tools(query)` to discover the handful it needs (with their schemas), then
`call_tool(name, arguments)` to run one. The upstream registry is built lazily on the first call.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from dhis2w_mcp_router.config import load_servers
from dhis2w_mcp_router.core import Registry

mcp: FastMCP = FastMCP(
    "dhis2w-mcp-router",
    instructions=(
        "This server fronts a large federated MCP tool surface. Call search_tools(query) to find the "
        "tools you need (returns their namespaced 'server__tool' names + input schemas), then "
        "call_tool(name, arguments) to run one. Do not guess tool names — search first."
    ),
)

#: Lazily-built registry so importing this module never requires a config file (tests, --help).
_registry: Registry | None = None


def _get_registry() -> Registry:
    """Return the process registry, constructing it from the config on first use."""
    global _registry
    if _registry is None:
        _registry = Registry(load_servers())
    return _registry


@mcp.tool
async def search_tools(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search the federated tool surface by keyword; returns matching tools with their input schemas."""
    registry = _get_registry()
    await registry.ensure_built()
    return [entry.summary() for entry in registry.search(query, limit)]


@mcp.tool
async def call_tool(name: str, arguments: dict[str, Any]) -> str:
    """Dispatch one federated tool by its namespaced `server__tool` name and return its result text."""
    registry = _get_registry()
    await registry.ensure_built()
    return await registry.call(name, arguments)


def main() -> None:
    """Console entry point: run the router as a stdio MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
