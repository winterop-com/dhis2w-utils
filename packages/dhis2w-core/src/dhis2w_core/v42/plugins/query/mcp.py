"""FastMCP tool registration for the `query` plugin."""

from __future__ import annotations

from typing import Any

from dhis2w_ql import to_jsonable

from dhis2w_core.profile import resolve_profile
from dhis2w_core.v42.plugins.query import service
from dhis2w_core.v42.plugins.query.models import QueryExplain


def register(mcp: Any) -> None:
    """Register query tools on the MCP server."""

    @mcp.tool()
    async def query_eval(query: str, define: str | None = None, profile: str | None = None) -> dict[str, Any]:
        """Run a d2ql program against DHIS2 metadata and return the produced rows.

        `query` is a d2ql program, e.g.
        `dataElements | where domainType = "AGGREGATE" | select id, name | limit 20`.
        Use `define` to run a named `define` from a multi-definition program.

        Local file access (`read("...")` sources and `>> "..."` sinks) is rejected on this surface.
        """
        result = await service.run_query(resolve_profile(profile), query, define=define, allow_local_files=False)
        return {
            "count": result.count,
            "scalar": result.scalar,
            "written_to": result.written_to,
            "rows": [to_jsonable(row) for row in result.rows],
        }

    @mcp.tool()
    async def query_explain(query: str, define: str | None = None, profile: str | None = None) -> QueryExplain:
        """Show how a d2ql pipeline splits between DHIS2-native pushdown and local evaluation."""
        return await service.explain_query(resolve_profile(profile), query, define=define)

    @mcp.tool()
    async def query_d2path(expression: str, data: Any) -> list[Any]:
        """Evaluate a bare d2path (FHIRPath/JSONPath-compatible) expression over the given JSON data."""
        return service.evaluate_path(expression, data)
