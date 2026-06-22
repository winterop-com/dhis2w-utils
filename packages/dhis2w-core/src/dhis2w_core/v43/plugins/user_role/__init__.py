"""User-role plugin — list, get, authorities, grant/revoke users."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _UserRolePlugin(BaseModel):
    """Plugin descriptor for the DHIS2 user-role administration surface."""

    model_config = ConfigDict(frozen=True)

    name: str = "user-role"
    description: str = "List + administer DHIS2 user roles (authorities, user membership)."

    def register_cli(self, app: Any) -> None:
        """CLI is mounted by the `user` plugin under `d2w user role`; no top-level mount."""
        return None

    def register_mcp(self, mcp: Any) -> None:
        """Register user-role tools on the MCP server."""
        from dhis2w_core.v43.plugins.user_role import mcp as mcp_module

        mcp_module.register(mcp)


plugin = _UserRolePlugin()
