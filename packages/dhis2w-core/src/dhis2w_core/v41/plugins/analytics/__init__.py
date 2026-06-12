"""Analytics plugin — CLI + MCP wrappers over /api/analytics and /api/resourceTables/analytics."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from dhis2w_core.v41.plugins.analytics import cli as cli_module
from dhis2w_core.v41.plugins.analytics import mcp as mcp_module


class _AnalyticsPlugin(BaseModel):
    """Plugin descriptor for DHIS2 analytics queries."""

    model_config = ConfigDict(frozen=True)

    name: str = "analytics"
    description: str = "Run DHIS2 analytics queries (aggregated, raw, dataValueSet) and trigger refresh."

    def register_cli(self, app: Any) -> None:
        """Mount under `d2w analytics`."""
        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """Register analytics tools on the MCP server."""
        mcp_module.register(mcp)


plugin = _AnalyticsPlugin()
