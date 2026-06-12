"""External plugin example — `d2w hello`.

Registration happens via `[project.entry-points."dhis2.plugins"]` in the
package's `pyproject.toml`. Once this package is installed in the same
environment as `dhis2w-core`, the CLI discovers it automatically — no core
code change needed.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from dhis2_plugin_hello import cli as cli_module
from dhis2_plugin_hello import mcp as mcp_module


class _HelloPlugin(BaseModel):
    """Plugin descriptor — the entry-point attribute dhis2w-core imports."""

    model_config = ConfigDict(frozen=True)

    name: str = "hello"
    description: str = (
        "External plugin example — greets the authenticated user via /api/me. "
        "Install with `uv add --editable examples/plugin-external/` to see it register."
    )

    def register_cli(self, app: Any) -> None:
        """Mount under `d2w hello`."""
        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """Register `hello_say` on the MCP server."""
        mcp_module.register(mcp)


plugin = _HelloPlugin()
