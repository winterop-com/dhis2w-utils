"""Security plugin — inspect DHIS2 security posture (settings, account authorities)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _SecurityPlugin(BaseModel):
    """Plugin descriptor for the read-only DHIS2 security surface."""

    model_config = ConfigDict(frozen=True)

    name: str = "security"
    description: str = "Inspect DHIS2 security posture (settings, account authorities)."

    def register_cli(self, app: Any) -> None:
        """Mount the security sub-app under `d2w security`."""
        from dhis2w_core.v42.plugins.security import (
            cli as cli_module,
        )

        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """Register the cheap read-only `security_*` tools on the MCP server."""
        from dhis2w_core.v42.plugins.security import mcp as mcp_module

        mcp_module.register(mcp)


plugin = _SecurityPlugin()
