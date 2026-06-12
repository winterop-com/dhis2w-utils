"""Schema plugin — describe a generated type's fields (`d2w schema <type>`)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from dhis2w_core.v43.plugins.schema import cli as cli_module


class _SchemaPlugin(BaseModel):
    """Plugin descriptor for the offline, read-only `schema` command."""

    model_config = ConfigDict(frozen=True)

    name: str = "schema"
    description: str = "Describe a generated type's fields (metadata or instance-side)."

    def register_cli(self, app: Any) -> None:
        """Mount the `schema` command on the root CLI."""
        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """No MCP surface yet — CLI-only plugin."""


plugin = _SchemaPlugin()
