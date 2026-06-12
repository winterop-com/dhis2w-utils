"""Customize plugin — brand + theme a DHIS2 instance.

CLI is mounted under `d2w dev customize` (see `plugins/dev/cli.py`),
alongside the other rarely-run setup utilities (`dev pat`, `dev oauth2`,
`dev sample`, `dev codegen`). MCP tools are registered at the top level
(`customize_*`) since MCP has no nested-namespace convention.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from dhis2w_core.v43.plugins.customize import cli as cli_module
from dhis2w_core.v43.plugins.customize import mcp as mcp_module


class _CustomizePlugin(BaseModel):
    """Plugin descriptor for DHIS2 branding + theming."""

    model_config = ConfigDict(frozen=True)

    name: str = "customize"
    description: str = (
        "DHIS2 branding + theming: login-page logos, system-setting copy, CSS stylesheet. "
        "Applies preset directories so `d2w dev customize apply DIR` re-brands an instance."
    )

    def register_cli(self, app: Any) -> None:
        """Mount the customize sub-app under `d2w customize`."""
        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """Register `customize_*` tools on the MCP server."""
        mcp_module.register(mcp)


plugin = _CustomizePlugin()
