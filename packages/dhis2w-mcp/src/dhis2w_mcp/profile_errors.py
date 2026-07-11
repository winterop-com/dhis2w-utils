"""Actionable no-profile errors for MCP tool calls (hard requirement 1).

When no DHIS2 profile is configured, `resolve_profile()` raises `NoProfileError` inside the tool
function. The CLI renders that with a hint block pointing at `d2w profile add <name>` /
`d2w profile bootstrap`; this middleware gives MCP clients the same guidance. FastMCP wraps the
tool's exception in a `ToolError` before it reaches middleware, so the middleware walks the cause
chain for a `NoProfileError` and re-raises a `ToolError` carrying the shared hint text
(`dhis2w_core.profile.NO_PROFILE_HINT_LINES` — one source of truth for both surfaces).
"""

from __future__ import annotations

import mcp.types as mt
from dhis2w_core.profile import NO_PROFILE_HINT_LINES, NoProfileError
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.base import ToolResult


def _find_no_profile_error(exc: BaseException) -> NoProfileError | None:
    """Return the `NoProfileError` in `exc`'s cause/context chain, or None."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        if isinstance(current, NoProfileError):
            return current
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return None


def no_profile_message(error: NoProfileError) -> str:
    """Render the error plus the shared setup hint as one MCP-facing message."""
    hint = "\n".join(f"  {line}" for line in NO_PROFILE_HINT_LINES)
    return f"{error}\nhint:\n{hint}"


class NoProfileHintMiddleware(Middleware):
    """Rewrite `NoProfileError` tool failures into the CLI's actionable setup guidance."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        """Run the tool; if it failed because no profile is configured, surface the setup hint."""
        try:
            return await call_next(context)
        except Exception as exc:
            no_profile = _find_no_profile_error(exc)
            if no_profile is None:
                raise
            raise ToolError(no_profile_message(no_profile)) from exc
