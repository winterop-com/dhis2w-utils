"""FastMCP server entrypoint for dhis2w-mcp-bridge — the single-tool `dhis2` CLI bridge."""

from __future__ import annotations

from fastmcp import FastMCP

from dhis2w_mcp_bridge.cli_bridge import register


def build_server() -> FastMCP:
    """Create the FastMCP instance exposing the single `dhis2_cli` bridge tool."""
    server = FastMCP(name="dhis2-cli-bridge")
    register(server)
    return server


def main() -> None:
    """Console-script entrypoint: build the bridge server and run it over stdio."""
    build_server().run()


if __name__ == "__main__":
    main()
