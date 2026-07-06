"""MCP tool calls without a configured profile return the CLI's actionable setup guidance."""

from __future__ import annotations

from pathlib import Path

import pytest
from dhis2w_mcp.server import build_server
from fastmcp import Client
from fastmcp.exceptions import ToolError


@pytest.fixture
def _no_profile_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every profile source: env creds, global TOML, and any project TOML above cwd."""
    for key in ("DHIS2_PROFILE", "DHIS2_URL", "DHIS2_PAT", "DHIS2_USERNAME", "DHIS2_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    empty_config = tmp_path / "xdg"
    empty_config.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(empty_config))
    working_dir = tmp_path / "cwd"
    working_dir.mkdir()
    monkeypatch.chdir(working_dir)


async def test_tool_call_without_profile_names_setup_commands(_no_profile_env: None) -> None:
    """The tool error names `d2w profile add <name>` and `d2w profile bootstrap` (hard requirement 1)."""
    server = build_server()
    async with Client(server) as client:
        with pytest.raises(ToolError) as excinfo:
            await client.call_tool("system_info", {})

    message = str(excinfo.value)
    assert "no DHIS2 profile is configured" in message
    assert "d2w profile add" in message
    assert "d2w profile bootstrap" in message
