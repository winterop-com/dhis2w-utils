"""Metadata plugin — CLI + MCP wrappers over the generated CRUD resources."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _MetadataPlugin(BaseModel):
    """Plugin descriptor for DHIS2 metadata inspection."""

    model_config = ConfigDict(frozen=True)

    name: str = "metadata"
    description: str = "Inspect DHIS2 metadata (lists + get by UID, across every generated resource)."

    def register_cli(self, app: Any) -> None:
        """Mount the metadata sub-app under `d2w metadata`."""
        from dhis2w_core.v41.plugins.metadata import cli as cli_module

        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """Register metadata listing tools on the MCP server."""
        from dhis2w_core.v41.plugins.metadata import mcp as mcp_module

        mcp_module.register(mcp)


plugin = _MetadataPlugin()
