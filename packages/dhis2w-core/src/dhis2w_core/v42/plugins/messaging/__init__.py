"""Messaging plugin — DHIS2 `/api/messageConversations`."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from dhis2w_core.v42.plugins.messaging import cli as cli_module
from dhis2w_core.v42.plugins.messaging import mcp as mcp_module


class _MessagingPlugin(BaseModel):
    """Plugin descriptor for DHIS2 internal messaging (conversations + attachments)."""

    model_config = ConfigDict(frozen=True)

    name: str = "messaging"
    description: str = (
        "DHIS2 internal messaging. CLI + MCP surfaces for /api/messageConversations — "
        "list, read, send, reply, mark-read, delete. Pairs with the files plugin for "
        "MESSAGE_ATTACHMENT fileResources."
    )

    def register_cli(self, app: Any) -> None:
        """Mount `d2w messaging` on the root CLI."""
        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """Register `messaging_*` tools on the MCP server."""
        mcp_module.register(mcp)


plugin = _MessagingPlugin()
