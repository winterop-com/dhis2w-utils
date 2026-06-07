"""User-group plugin — list, get, membership edits, sharing."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from dhis2w_core.v43.plugins.user_group import mcp as mcp_module


class _UserGroupPlugin(BaseModel):
    """Plugin descriptor for the DHIS2 user-group administration surface."""

    model_config = ConfigDict(frozen=True)

    name: str = "user-group"
    description: str = "List + administer DHIS2 user groups (membership, sharing)."

    def register_cli(self, app: Any) -> None:
        """CLI is mounted by the `user` plugin under `dhis2 user group`; no top-level mount."""
        return None

    def register_mcp(self, mcp: Any) -> None:
        """Register user-group tools on the MCP server."""
        mcp_module.register(mcp)


plugin = _UserGroupPlugin()
