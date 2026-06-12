"""Files plugin — documents + fileResources (uploads, downloads, metadata)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from dhis2w_core.v43.plugins.files import cli as cli_module
from dhis2w_core.v43.plugins.files import mcp as mcp_module


class _FilesPlugin(BaseModel):
    """Plugin descriptor for document management + file-resource binary attachments."""

    model_config = ConfigDict(frozen=True)

    name: str = "files"
    description: str = (
        "DHIS2 document management + file resources. CLI + MCP surfaces for "
        "`/api/documents` (user-uploaded attachments, external URLs) and "
        "`/api/fileResources` (typed binary blobs — DATA_VALUE, ICON, MESSAGE_ATTACHMENT)."
    )

    def register_cli(self, app: Any) -> None:
        """Mount `d2w files` on the root CLI."""
        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """Register `files_*` tools on the MCP server."""
        mcp_module.register(mcp)


plugin = _FilesPlugin()
