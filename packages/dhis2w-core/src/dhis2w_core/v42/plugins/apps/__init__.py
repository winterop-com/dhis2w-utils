"""Apps plugin — DHIS2 `/api/apps` + `/api/appHub`."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _AppsPlugin(BaseModel):
    """Plugin descriptor for DHIS2 apps — install / uninstall / update / App Hub queries."""

    model_config = ConfigDict(frozen=True)

    name: str = "apps"
    description: str = (
        "DHIS2 apps: `/api/apps` + `/api/appHub`. CLI + MCP surfaces for list, add "
        "(from local zip or App Hub version), remove, update (one / --all), reload."
    )

    def register_cli(self, app: Any) -> None:
        """Mount `d2w apps` on the root CLI."""
        from dhis2w_core.v42.plugins.apps import cli as cli_module

        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """Register `apps_*` tools on the MCP server."""
        from dhis2w_core.v42.plugins.apps import mcp as mcp_module

        mcp_module.register(mcp)


plugin = _AppsPlugin()
