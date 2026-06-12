"""Browser plugin — Playwright-driven DHIS2 UI automation.

Mounts `d2w browser ...` subcommands only when the optional
`dhis2w-browser` library is importable. Installations that skip the
`[browser]` extra get nothing — the command silently drops out of
`d2w --help` rather than showing a broken entry.
"""

from __future__ import annotations

from importlib.util import find_spec
from typing import Any

from pydantic import BaseModel, ConfigDict


class _BrowserPlugin(BaseModel):
    """Plugin descriptor for Playwright-driven DHIS2 UI automation."""

    model_config = ConfigDict(frozen=True)

    name: str = "browser"
    description: str = (
        "Playwright-driven DHIS2 UI automation. Mounts `d2w browser ...` "
        "for workflows DHIS2 only exposes through the web UI (PAT minting "
        "today; dashboard screenshots + maintenance-app driving planned)."
    )

    def register_cli(self, app: Any) -> None:
        """Mount `d2w browser` on the root CLI if the browser extra is installed."""
        if find_spec("dhis2w_browser") is None:
            return
        from dhis2w_core.v43.plugins.browser import cli as cli_module  # noqa: PLC0415 — optional-extra guard

        cli_module.register(app)

    def register_mcp(self, mcp: Any) -> None:
        """No MCP tools yet — Playwright flows are CLI-only for now."""


plugin = _BrowserPlugin()
