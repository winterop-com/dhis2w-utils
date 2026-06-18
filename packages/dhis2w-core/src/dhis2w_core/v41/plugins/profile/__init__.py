"""Profile plugin — manage DHIS2 profiles across project and global TOML files."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _ProfilePlugin(BaseModel):
    """Plugin descriptor for DHIS2 profile management."""

    model_config = ConfigDict(frozen=True)

    name: str = "profile"
    description: str = "List, verify, switch, add, and remove DHIS2 profiles."

    def register_cli(self, app: Any) -> None:
        """Mount under `d2w profile`."""
        from dhis2w_core.v41.plugins.profile import cli as cli_module

        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """Register read-only profile tools on the MCP server."""
        from dhis2w_core.v41.plugins.profile import mcp as mcp_module

        mcp_module.register(mcp)


plugin = _ProfilePlugin()
