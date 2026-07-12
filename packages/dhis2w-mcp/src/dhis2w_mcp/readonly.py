"""Read-only mode for the full dhis2-mcp server (env `DHIS2_MCP_READONLY`).

The typed server has no built-in guard, so this FastMCP middleware enforces read-only at one place: it
hides write tools from `list_tools` and refuses them at call time (exit via `ToolError`). Tools are
classified by their `readOnlyHint` annotation when set, else by a verb heuristic on the tool name — a
write verb anywhere in the name wins first, and only a name with no write verb and a trailing read verb
is a read (fail-closed: anything else is a write). The authoritative control remains the DHIS2
authorities of the profile's credentials; this is a structural convenience guard, like the bridge's.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import mcp.types as mt
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.base import Tool, ToolResult

#: Write verbs: a tool is a write when any of these appears as a segment of its name. Checked FIRST,
#: so a mutating tool whose name happens to trail in a read-looking noun — `..._group_add_members`
#: (list-verb "members"), `messaging_set_status` (read-verb "status") — is still caught as a write.
#: `update_all` is covered by `update`; segment matching never sees the joined form. The write verb
#: sits in verb position (e.g. `add_members`, `set_status`, `set_legend_sets`), so the trailing token
#: is often an object, not the verb — which is exactly why the trailing-verb read check cannot come first.
WRITE_VERBS: frozenset[str] = frozenset(
    {
        "add", "remove", "create", "update", "delete", "set", "rename", "enroll", "push", "import",
        "merge", "move", "reset", "invite", "reinvite", "assign", "unassign", "reorder", "install",
        "uninstall", "apply", "clear", "run", "snapshot", "restore", "retag", "share", "patch",
        "build", "sync", "wait", "clone",
    }
)  # fmt: skip

#: Read verbs: with no write verb present, a tool is read-only when its name ENDS in one of these
#: (fail-closed otherwise). `members`/`status`/`result` are reads here (list-members, task-status,
#: integrity-result) — safe only because the write-verb check runs first and steals `add_members`,
#: `set_status`, and friends before this fallback ever sees them.
READ_VERBS: frozenset[str] = frozenset(
    {
        "get", "list", "ls", "count", "find", "search", "show", "info", "whoami", "me", "tree",
        "members", "query", "namespaces", "keys", "usage", "diff", "verify", "status", "result", "outstanding",
    }
)  # fmt: skip

#: Segments after which `set` is the noun tail of a resource type (`dataSet`, `optionSet`, `legendSet`,
#: `...GroupSet`) rather than the mutation verb — so `metadata_data_set_get` reads while
#: `messaging_set_status` (verb `set`) writes. A write verb elsewhere in such a name still wins
#: (`metadata_data_set_create` is a write via `create`).
_SET_NOUN_PRECEDERS: frozenset[str] = frozenset({"data", "option", "legend", "group"})

#: Truthy env values that enable read-only mode.
_TRUTHY = {"1", "true", "yes", "on"}


def readonly_enabled() -> bool:
    """Whether read-only mode is on, from env `DHIS2_MCP_READONLY`."""
    return os.environ.get("DHIS2_MCP_READONLY", "").strip().lower() in _TRUTHY


def _segment_is_write(segments: list[str], position: int) -> bool:
    """Whether `segments[position]` is a mutation verb, treating a resource-tail `set` as a noun."""
    segment = segments[position]
    if segment not in WRITE_VERBS:
        return False
    # `set` is a mutation verb unless it is the resource-type tail (dataSet, optionSet, ...).
    return not (segment == "set" and position > 0 and segments[position - 1] in _SET_NOUN_PRECEDERS)


def is_read_tool(name: str) -> bool:
    """Classify read-only: any write verb in the name is a write; else the trailing verb must be a read."""
    segments = name.split("_")
    if any(_segment_is_write(segments, position) for position in range(len(segments))):
        return False
    return segments[-1] in READ_VERBS


def _tool_is_read(tool: Tool) -> bool:
    """Read-only by the tool's `readOnlyHint` annotation when set, else by its name's verbs."""
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
        """Refuse any non-read tool before it runs, honouring an explicit `readOnlyHint` when present."""
        name = context.message.name
        if not await self._call_is_read(context, name):
            raise ToolError(f"read-only mode (DHIS2_MCP_READONLY): tool {name!r} is a write and is refused")
        return await call_next(context)

    async def _call_is_read(self, context: MiddlewareContext[mt.CallToolRequestParams], name: str) -> bool:
        """Classify the called tool with the same annotation-then-verb rule the listing uses.

        Looks the tool up so an explicit `readOnlyHint` wins over the name heuristic (mirroring
        `on_list_tools`); falls back to the name-only verb check if the tool cannot be resolved.
        """
        fastmcp_context = getattr(context, "fastmcp_context", None)
        server = getattr(fastmcp_context, "fastmcp", None) if fastmcp_context else None
        if server is not None:
            try:
                tool = await server.get_tool(name)
            except Exception:  # noqa: BLE001 — a lookup miss must not weaken the name-only guard
                tool = None
            if tool is not None:
                return _tool_is_read(tool)
        return is_read_tool(name)
