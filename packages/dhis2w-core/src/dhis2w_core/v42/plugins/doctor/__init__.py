"""Doctor plugin — probe a DHIS2 instance for known BUGS.md gotchas + workspace hard requirements."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _DoctorPlugin(BaseModel):
    """Plugin descriptor for `d2w doctor`."""

    model_config = ConfigDict(frozen=True)

    name: str = "doctor"
    description: str = (
        "Probe a DHIS2 instance for known BUGS.md gotchas + workspace hard requirements. "
        "One command, pure reads, pass/warn/fail per probe with BUGS.md cross-refs."
    )

    def register_cli(self, app: Any) -> None:
        """Mount under `d2w doctor`."""
        from dhis2w_core.v42.plugins.doctor import cli as cli_module

        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """Register `doctor_run` MCP tool."""
        from dhis2w_core.v42.plugins.doctor import mcp as mcp_module

        mcp_module.register(mcp)


plugin = _DoctorPlugin()
