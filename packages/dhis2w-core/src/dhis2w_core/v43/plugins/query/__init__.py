"""Query plugin — run d2ql pipelines (and d2path expressions) against a DHIS2 profile."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _QueryPlugin(BaseModel):
    """Plugin descriptor for the d2ql query + transform language."""

    model_config = ConfigDict(frozen=True)

    name: str = "query"
    description: str = "Run d2ql queries/transforms and d2path expressions against DHIS2 metadata."

    def register_cli(self, app: Any) -> None:
        """Mount under `d2w query`."""
        from dhis2w_core.v43.plugins.query import cli as cli_module

        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """Register query tools on the MCP server."""
        from dhis2w_core.v43.plugins.query import mcp as mcp_module

        mcp_module.register(mcp)


plugin = _QueryPlugin()
