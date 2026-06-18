"""Data plugin — `d2w data` umbrella covering aggregate + tracker sub-domains."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _DataPlugin(BaseModel):
    """Plugin descriptor for DHIS2 data values (aggregate + tracker)."""

    model_config = ConfigDict(frozen=True)

    name: str = "data"
    description: str = "DHIS2 data values — aggregate (dataValueSets) and tracker (entities, events, ...)."

    def register_cli(self, app: Any) -> None:
        """Mount under `d2w data`."""
        from dhis2w_core.v42.plugins.data import cli as cli_module

        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """Register `data_aggregate_*` and `data_tracker_*` tools on the MCP server."""
        from dhis2w_core.v42.plugins.data import mcp as mcp_module

        mcp_module.register(mcp)


plugin = _DataPlugin()
