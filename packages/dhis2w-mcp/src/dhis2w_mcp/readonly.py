"""Read-only mode for the full dhis2-mcp server (env `DHIS2_MCP_READONLY`).

The typed server has no built-in guard, so this FastMCP middleware enforces read-only at one place: it
hides write tools from `list_tools` and refuses them at call time (exit via `ToolError`). Tools are
classified by their `readOnlyHint` annotation when set, else by a read-verb heuristic on the tool name
— fail-closed: an unrecognized verb is treated as a write. The authoritative control remains the DHIS2
authorities of the profile's credentials; this is a structural convenience guard, like the bridge's.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import mcp.types as mt
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.base import Tool, ToolResult

#: Read-verb suffixes: a tool is read-only when its name ends in one of these (fail-closed otherwise).
READ_VERBS: frozenset[str] = frozenset(
    {
        "get", "list", "ls", "count", "find", "search", "show", "info", "whoami", "me", "tree",
        "members", "query", "namespaces", "keys", "usage", "diff", "verify", "status", "result", "outstanding",
    }
)  # fmt: skip

#: Truthy env values that enable read-only mode.
_TRUTHY = {"1", "true", "yes", "on"}


def readonly_enabled() -> bool:
    """Whether read-only mode is on, from env `DHIS2_MCP_READONLY`."""
    return os.environ.get("DHIS2_MCP_READONLY", "").strip().lower() in _TRUTHY


def is_read_tool(name: str) -> bool:
    """Classify a tool read-only by its trailing verb (the segment after the last underscore)."""
    return name.rsplit("_", 1)[-1] in READ_VERBS


def _tool_is_read(tool: Tool) -> bool:
    """Read-only by the tool's `readOnlyHint` annotation when set, else by its name's verb."""
    annotations = getattr(tool, "annotations", None)
    hint = getattr(annotations, "readOnlyHint", None) if annotations else None
    return bool(hint) if hint is not None else is_read_tool(tool.name)


class ReadOnlyMiddleware(Middleware):
    """Hide write tools from listing and refuse them at call time, enforcing read-only at one chokepoint."""

    async def on_list_tools(
        self,
        context: MiddlewareContext[mt.ListToolsRequest],
        call_next: CallNext[mt.ListToolsRequest, Sequence[Tool]],
    ) -> Sequence[Tool]:
        """Drop write tools from the listing so a client never sees them."""
        tools = await call_next(context)
        return [tool for tool in tools if _tool_is_read(tool)]

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        """Refuse any non-read tool before it runs."""
        name = context.message.name
        if not is_read_tool(name):
            raise ToolError(f"read-only mode (DHIS2_MCP_READONLY): tool {name!r} is a write and is refused")
        return await call_next(context)
