"""Maintenance plugin — tasks, cache, soft-delete cleanup, data-integrity."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _MaintenancePlugin(BaseModel):
    """Plugin descriptor for DHIS2 maintenance (tasks, cache, integrity, cleanup)."""

    model_config = ConfigDict(frozen=True)

    name: str = "maintenance"
    description: str = "DHIS2 maintenance: task polling, cache clear, soft-delete cleanup, data-integrity checks."

    def register_cli(self, app: Any) -> None:
        """Mount under `d2w maintenance`."""
        from dhis2w_core.v41.plugins.maintenance import cli as cli_module

        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """Register maintenance tools on the MCP server."""
        from dhis2w_core.v41.plugins.maintenance import mcp as mcp_module

        mcp_module.register(mcp)


plugin = _MaintenancePlugin()
