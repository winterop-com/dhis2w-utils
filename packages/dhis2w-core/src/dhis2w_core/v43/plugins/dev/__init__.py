"""Dev plugin — `d2w dev` for operator / developer one-off tools (codegen, uid, oauth2 client)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _DevPlugin(BaseModel):
    """Plugin descriptor for developer + operator tools."""

    model_config = ConfigDict(frozen=True)

    name: str = "dev"
    description: str = "Developer/operator tools: codegen, UID generation, sample data."

    def register_cli(self, app: Any) -> None:
        """Mount under `d2w dev`."""
        from dhis2w_core.v43.plugins.dev import (
            cli as cli_module,
        )

        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """Dev tools are CLI-only — no MCP surface."""
        return None


plugin = _DevPlugin()
