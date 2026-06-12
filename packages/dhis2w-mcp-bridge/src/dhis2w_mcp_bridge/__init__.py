"""dhis2w-mcp-bridge: expose the `d2w` CLI as a single MCP tool for small local models."""

from dhis2w_mcp_bridge.cli_bridge import READ_ONLY_COMMANDS, CliResult, is_read_only, register, run_cli
from dhis2w_mcp_bridge.server import build_server, main

__all__ = [
    "READ_ONLY_COMMANDS",
    "CliResult",
    "build_server",
    "is_read_only",
    "main",
    "register",
    "run_cli",
]
