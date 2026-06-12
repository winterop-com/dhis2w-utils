"""System plugin — exposes /api/system/info and /api/me as CLI + MCP surfaces."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from dhis2w_core.v42.plugins.system import cli as cli_module
from dhis2w_core.v42.plugins.system import mcp as mcp_module


class _SystemPlugin(BaseModel):
    """Plugin descriptor for the system capability."""

    model_config = ConfigDict(frozen=True)

    name: str = "system"
    description: str = "DHIS2 system info and current-user access."

    def register_cli(self, app: Any) -> None:
        """Mount the system sub-app under `d2w system`."""
        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """Register `whoami` and `system_info` as MCP tools."""
        mcp_module.register(mcp)


plugin = _SystemPlugin()
