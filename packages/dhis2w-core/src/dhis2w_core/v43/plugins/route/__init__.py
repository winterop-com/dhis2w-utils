"""Route plugin — CLI + MCP wrappers over /api/routes (DHIS2 integration routes)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from dhis2w_core.v43.plugins.route import cli as cli_module
from dhis2w_core.v43.plugins.route import mcp as mcp_module


class _RoutePlugin(BaseModel):
    """Plugin descriptor for the DHIS2 Route API."""

    model_config = ConfigDict(frozen=True)

    name: str = "route"
    description: str = "DHIS2 Route API — register + run integration routes (proxies to external services)."

    def register_cli(self, app: Any) -> None:
        """Mount under `d2w route`."""
        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """Register `route_*` tools on the MCP server."""
        mcp_module.register(mcp)


plugin = _RoutePlugin()
