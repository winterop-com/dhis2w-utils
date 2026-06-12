"""User plugin — list, get, invite, reinvite, and password-reset for DHIS2 users."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from dhis2w_core.v42.plugins.user import cli as cli_module
from dhis2w_core.v42.plugins.user import mcp as mcp_module


class _UserPlugin(BaseModel):
    """Plugin descriptor for the DHIS2 user administration surface."""

    model_config = ConfigDict(frozen=True)

    name: str = "user"
    description: str = "List + administer DHIS2 users (invite, reinvite, password reset)."

    def register_cli(self, app: Any) -> None:
        """Mount the user sub-app under `d2w user`."""
        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """Register user tools on the MCP server."""
        mcp_module.register(mcp)


plugin = _UserPlugin()
