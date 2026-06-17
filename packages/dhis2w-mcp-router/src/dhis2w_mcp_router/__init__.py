"""Domain-neutral MCP router: search + dispatch over many upstream MCP servers."""

from dhis2w_mcp_router.core import Registry, ToolEntry, UpstreamServer

__all__ = ["Registry", "ToolEntry", "UpstreamServer"]
